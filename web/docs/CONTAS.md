# Conta do usuário

A área `/conta` guarda duas coisas que hoje só existiam neste navegador: **cópias das listas de compras** e
**o local de onde a pessoa compara preços** (o "Perto de você"). O cadastro é por e-mail e senha, ou por
Google. A lista continua funcionando sem conta.

## O que a conta é (e o que ela não é)

- **É** uma forma de levar a lista e o local preferido para outro aparelho sem depender do `localStorage`.
- **Não é** um requisito para usar o site: busca, filtros, encartes e a lista local seguem abertos. Sem conta,
  o comportamento é exatamente o anterior.
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
- `sessions` — `token_hash` (SHA-256 do valor do cookie), usuário, expiração.
- `user_preferences` — uma linha por pessoa: `region`, `location_label`, `latitude`, `longitude`, `radius_km`.
- `saved_lists` — uma linha por lista: nome, `lines` em JSONB com o mesmo formato do `localStorage`
  (`[{product_id, name, quantity, checked}]`), datas.

Desenvolvimento (SQLite, `scraping/models/user.py`) repete as mesmas tabelas; o Flask local
(`scraping/local_api/accounts.py`) serve as mesmas rotas e as mesmas mensagens que o Worker.

## Segurança

- Senha: PBKDF2-SHA-256, 210 000 iterações, sal de 16 bytes por conta; nunca é gravada em claro. O
  `crypto.subtle` do Worker e o `hashlib` do Flask produzem o mesmo formato `pbkdf2-sha256$...`.
- Sessão: token aleatório de 32 bytes no cookie `med_session` (`HttpOnly`, `SameSite=Lax`, `Secure` quando
  HTTPS); o banco guarda só o SHA-256. Expira em 30 dias e o logout apaga a linha.
- Login responde a mesma mensagem para e-mail desconhecido e senha errada, e há um freio em memória por
  isolate (10 falhas / 15 min) no Worker.
- Requisições que mudam estado recusam `Origin` de outro site; o cookie é `SameSite=Lax`.
- Google: fluxo `authorization-code` com `state` em cookie de curta duração; os claims do `id_token` são
  aceitos depois que `iss`, `aud`, `exp` e `email_verified` conferem. Uma conta que já existe com o mesmo
  e-mail verificado recebe o vínculo com o Google em vez de uma conta duplicada.
- O snapshot público continua somente-leitura. As tabelas de conta exigem uma conexão com permissão de
  escrita: `ACCOUNTS_HYPERDRIVE` (ou a mesma `HYPERDRIVE` em desenvolvimento).

## Interface

- `components/account.tsx`: entrar/criar conta, sair, local preferido (GPS ou busca de endereço) e lista de
  listas salvas.
- `components/saved-lists.tsx`: no "Minha lista", salva a lista atual (mesmo nome atualiza a existente), abre
  uma lista salva e exclui. Deslogado, mostra só o convite para entrar.
- `lib/account.ts` (validação e conversões, testado em `lib/account.test.ts`) e `lib/account-api.ts`
  (chamadas e `useAccount`).
- O local preferido é aplicado uma vez ao abrir `/`, e nunca sobre uma referência já escolhida naquela aba.

## Limites conhecidos

- O freio de tentativas é por isolate; um limite global exigiria um armazenamento compartilhado.
- Não há "esqueci minha senha", troca de e-mail nem exclusão de conta na interface (as linhas têm
  `ON DELETE CASCADE`, então apagar o usuário remove sessões, preferências e listas).
- Não há sincronização automática da lista: salvar é explícito, para que uma edição local não sobrescreva a
  lista da conta sem a pessoa pedir.
- `receiptocr` continua só no Flask local, como antes.
