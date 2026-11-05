# Conta do usuário

A área `/conta` guarda duas coisas que hoje só existiam neste navegador: **cópias das listas de compras** e
**o local de onde a pessoa compara preços** (o "Perto de você"). O cadastro é por e-mail e senha, ou por
Google. A lista continua funcionando sem conta.

## O que a conta é (e o que ela não é)

- **É** uma forma de levar a lista e o local preferido para outro aparelho sem depender do `localStorage`.
- **Não é** um requisito para usar o site: busca, filtros, encartes e a lista local seguem abertos e continuam
  funcionando sem conta. A única diferença visível deslogado é o link de entrar no cabeçalho e o aviso na lista
  lembrando que é possível entrar para guardar cópias na conta.
- **Não é** o login administrativo. `/api/session` e `/admin` continuam como estavam (placeholder, sem
  autorização); a conta do usuário vive em `/api/auth/*` e `/api/account/*`.

## Por que "localização preferida" é o local, não o idioma

O produto é escrito em português e atende uma cidade (Fortaleza); a interface não tem tradução. O termo
"localização" no produto sempre significou a referência geográfica do filtro "Perto de você"
(`components/nearby-filter.tsx`, `lib/location.ts`). Guardar essa referência na conta é o que resolve um
problema real: hoje ela vive em `sessionStorage` e some ao trocar de aparelho ou ao fechar a aba. Uma
preferência de idioma sem tradução seria um seletor de uma opção só.

## Modelo de dados

Produção (Postgres, `scraping/db/schema.sql`):

- `users` — e-mail normalizado (único), `password_hash` (nulo para conta só-Google), `google_sub` (único),
  nome, data de criação.
- `sessions` — `token_hash` (SHA-256 do valor do cookie), usuário, expiração. Índice em `sessions(expires_at)`.
- `user_preferences` — uma linha por pessoa: `region` (a cidade para a qual o local foi salvo; a referência só é
  aplicada enquanto a pessoa navega nessa mesma região), `location_label`, `latitude`, `longitude`, `radius_km`.
- `saved_lists` — uma linha por lista: nome, `lines` em JSONB com o mesmo formato do `localStorage`
  (`[{product_id, name, quantity, checked}]`), datas.

Desenvolvimento (SQLite, `scraping/models/user.py`) repete as mesmas tabelas; o Flask local
(`scraping/local_api/accounts.py`) serve as mesmas rotas e as mesmas mensagens que o Worker.

## Segurança

- Senha: PBKDF2-SHA-256, 210 000 iterações, sal de 16 bytes por conta; nunca é gravada em claro. O
  `crypto.subtle` do Worker e o `hashlib` do Flask produzem o mesmo formato `pbkdf2-sha256$...`. A contagem
  de caracteres da senha considera pontos de código Unicode nos dois backends.
- Sessão: token aleatório de 32 bytes no cookie `med_session` (`HttpOnly`, `SameSite=Lax`, `Secure` quando
  HTTPS); o banco guarda só o SHA-256. Expira em 30 dias e o logout apaga a linha. Ao iniciar uma nova sessão,
  o Worker descarta sessões expiradas (`pruneSessions`), e o Flask remove linhas expiradas ao checar a sessão;
  no Postgres há um índice em `sessions(expires_at)`. O repositório em memória de testes do Worker também
  faz pruning.
- Login: valida o formato de e-mail e de senha (400) antes de checar as credenciais. Para credenciais inválidas,
  responde a mesma mensagem genérica 401 ("E-mail ou senha incorretos."), sem revelar se o e-mail existe
  (usando hash de temporização quando necessário). Ambos os backends possuem freio em memória com mapa limitado:
  até 10 falhas em 15 minutos por IP+e-mail (retorna 429), zerado no primeiro login com sucesso. No Worker o freio
  é por isolate; no Flask é em memória para o servidor de desenvolvimento local.
- Requisições que mudam estado (POST, PUT, DELETE) recusam `Origin` de outro site (403 "Origem inválida.");
  o cookie é `SameSite=Lax`.
- Google: fluxo `authorization-code` com `state` em cookie de curta duração; os claims do `id_token` são
  aceitos depois que `iss`, `aud`, `exp` e `email_verified` conferem. O login com Google NUNCA vincula
  automaticamente a uma conta existente por e-mail: se o `sub` do Google for desconhecido mas o e-mail já
  existir, tanto o Worker quanto o Flask redirecionam para `/conta?erro=google-conta-existente` e não criam
  sessão. A pessoa deve entrar pelo método já cadastrado (a senha; ou a mesma conta Google, se a conta for
  só-Google). Isso impede ataques de pré-sequestro de contas (pre-hijacking,
  onde um atacante cadastra previamente o e-mail da vítima). Vincular a conta Google a uma conta existente
  será uma etapa autenticada futura.
- Listas salvas: rotas com `:id` (PUT e DELETE) possuem proteção de UUID: identificadores malformados ou
  desconhecidos retornam 404 ("Lista não encontrada.") em vez de causar erro 500 no Postgres.
- O snapshot público continua somente-leitura. As tabelas de conta exigem uma conexão com permissão de
  escrita: `ACCOUNTS_HYPERDRIVE` (ou a mesma `HYPERDRIVE` em desenvolvimento). Se a conexão de contas
  estiver ausente ou for somente-leitura (código Postgres 42501 `insufficient_privilege`), o Worker retorna
  HTTP 503 `{"error":"As contas não estão configuradas neste servidor."}` em vez de um erro 500 genérico.
- O formulário da conta em `components/account.tsx` é marcado com a classe `ph-no-capture` para autocaptura do PostHog.

## Interface

- `components/account.tsx`: entrar/criar conta, sair, local preferido (GPS ou busca de endereço) e lista de
  listas salvas. Exibe mensagens de erro retornadas pela API. Explica quando o local salvo pertence a outra cidade.
- `components/saved-lists.tsx`: no "Minha lista", salva a lista atual (mesmo nome atualiza a existente), abre
  uma lista salva e exclui. Deslogado, mostra o aviso/convite para entrar. Exibe mensagens de erro da API.
  Ao abrir uma lista salva, pede confirmação antes de substituir uma lista não-vazia do aparelho; ao excluir,
  pede confirmação antes da remoção.
- `lib/account.ts` (validação e conversões, testado em `lib/account.test.ts`) e `lib/account-api.ts`
  (chamadas e `useAccount`). A função `browsingRegion` lê a região do `localStorage` (`med-region`), caindo
  de volta para `BRAND.city`.
- Regra de região: o local preferido é salvo associado à região de navegação ativa (`region`), e só é aplicado
  ao abrir `/` se `preferences.region` coincidir com a região atual da navegação. O local salvo nunca sobrescreve
  uma referência já escolhida naquela aba.

## Limites conhecidos

- Sem verificação de e-mail: o cadastro não envia e-mail de confirmação. Um cadastro feito com o e-mail de outra
  pessoa faz com que a tentativa posterior de cadastro pelo legítimo dono falhe com 409 ("Já existe uma conta
  com este e-mail"), embora o atacante não consiga entrar na conta sem a senha. Enquanto não houver
  verificação de e-mail, o dono também não tem como recuperar esse cadastro (não há "esqueci minha senha").
- Sem vínculo do Google a contas existentes: uma conta criada com e-mail e senha não pode ser vinculada ao
  Google no momento.
- PBKDF2 mantido em 210 000 iterações (abaixo das 600 000 recomendadas pela OWASP para PBKDF2-SHA-256) como
  compromisso deliberado com o tempo de CPU dos Cloudflare Workers; é um limite conhecido de hardening, não um bug.
- O freio de tentativas de login é em memória por isolate no Worker e por processo no Flask; um limite global
  exigiria um armazenamento compartilhado.
- Não há "esqueci minha senha", troca de e-mail nem exclusão de conta na interface (as linhas têm
  `ON DELETE CASCADE`, então apagar o usuário no banco remove sessões, preferências e listas).
- Não há sincronização automática da lista: salvar é explícito, para que uma edição local não sobrescreva a
  lista da conta sem a pessoa pedir.
- `receiptocr` continua só no Flask local, como antes.
