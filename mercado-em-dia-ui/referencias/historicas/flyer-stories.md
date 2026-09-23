# Encartes: stories, validade e correção no iPhone

Revisão local de 20/09/2026, a pedido do usuário. Sem deploy público.

## O que mudou

- Abas por rede, com contagens, rolagem horizontal e teclas de direção/Home/End.
- **Válidos agora** inclui todos os encartes vigentes, mesmo de uma mesma rede. **Em breve** e **Sem validade confirmada** são grupos próprios. **Arquivados** contém somente vencidos, filtráveis por mês e semana.
- Cartões exibem as ofertas das páginas oficiais num carrossel, com setas, gesto lateral, indicador de página e temporizador de 8 segundos. A contagem de validade é independente do tempo de leitura.
- Pop-up em stories, troca de rede, pausa, gesto lateral, teclado, ampliação de 100% a 300%, origem, download e compartilhamento da página atual. O PDF completo, quando cadastrado, é o alvo do download. Arquivos de outro domínio abrem na origem para usar a opção de salvar do navegador; não há proxy ou requisição que contorne CORS.
- Movimento reduzido inicia pausado. Páginas não avançam antes da imagem carregar, fora da tela, com a aba oculta, durante zoom/compartilhamento/download ou segurando a imagem. No fim da sequência do leitor, a reprodução para. A sequência aberta permanece estável caso outra edição vença durante a leitura.
- Migração 006 preserva o arquivo principal e acrescenta uma lista ordenada de imagens. Administração aceita até 30 URLs de imagem, todas no mesmo domínio HTTPS oficial. Demo continua separado e tem duas páginas fictícias por edição.

## Documentos oficiais revistos

Todas as 11 imagens foram abertas e inspecionadas; as datas impressas correspondem ao cadastro. URLs obtidas dos links de galeria das próprias páginas públicas, após verificar robots.txt. Não houve extração de preços estruturados, alteração de estoque, confirmação de lojas por inferência ou ativação do coletor Frangolândia.

| Edição e origem | Período anunciado | Imagens | PDF completo |
| --- | --- | ---: | --- |
| [Dia da Banana](https://frangolandia.com/encarte/festival-da-limpeza/) | 20–22/09/2026 | 2 | Não |
| [Ofertas Horti](https://frangolandia.com/encarte/ofertas-de-frutas-e-verduras/) | 20–22/09/2026 | 2 | Sim |
| [Dia da Limpeza](https://frangolandia.com/encarte/dia-do-hotdog/) | 19–21/09/2026 | 3 | Não |
| [Arrastão de Ofertas](https://frangolandia.com/encarte/horti-26-a-28-10-25/) | 18–20/09/2026 | 2 | Sim |
| [BBQ e Peixes](https://frangolandia.com/encarte/carnes-%F0%9F%8D%96-2/) | 18–20/09/2026 | 2 | Não |

Os caminhos reaproveitados das páginas não foram usados para inferir os títulos. As mídias são carregadas diretamente da origem; não foram copiadas para hospedagem pública. A abrangência por loja continua explicitamente não confirmada. Os preços impressos são consultados como parte do documento e não viram produtos comparáveis automaticamente.

Evidências locais: `data/flyer-audit/pages.json`, HTML das cinco páginas, `robots.txt` e `registered-media.json`. O registro único ocorreu por `scripts/register-reviewed-flyer-media.ts --apply`, com estado anterior guardado na auditoria SQLite (`reviewed_flyer_media`). O script não faz novas coletas e recusa produção/PostgreSQL, URLs fora da rede ou mídias já diferentes. Não deve ser reutilizado para campanhas futuras.

## Erro apresentado no iPhone

O log real de desenvolvimento continha somente diferenças nos atributos `__gcrremoteframetoken` e `__gcruniqueid`, introduzidos pelo preenchimento automático do Chrome iOS antes da hidratação. Correspondem às [constantes oficiais do Chromium](https://raw.githubusercontent.com/chromium/chromium/main/components/autofill/ios/form_util/resources/fill_constants.ts) e ao [registro de IDs de formulários](https://raw.githubusercontent.com/chromium/chromium/main/components/autofill/ios/form_util/resources/renderer_id.ts).

A correção limita `suppressHydrationWarning` a `html` e aos formulários/campos nativos presentes no log. Não remove os atributos do navegador nem altera IDs acessíveis ou a renderização dos filhos. A [documentação do React](https://react.dev/reference/react-dom/client/hydrateRoot#suppressing-unavoidable-hydration-mismatch-errors) descreve essa exceção de um nível. A regressão injeta os mesmos atributos antes de o React carregar e verifica ausência de erros, preservação dos atributos e uso da busca/endereço.

## Verificação

Cobertura automatizada: classificação por validade, datas inválidas, URLs oficiais, páginas demonstrativas isoladas, múltiplas edições vigentes da mesma rede, futuro/desconhecido/arquivo, avanço e pausa, movimento reduzido, gesto, zoom, download, compartilhamento da página atual, foco ao fechar, rede por teclado, documento indisponível e edição expirando com o leitor aberto. A suíte inclui Chromium desktop e WebKit emulando iPhone 13, além de larguras de 320 px e paisagem.

Resultado consolidado e capturas ficam no [relatório de testes](test-report.md). A reprodução controlada do erro não substitui uma nova abertura no iPhone físico que mostrou a mensagem. Instalação PWA e envio efetivo para outro aplicativo continuam fora dessa verificação.
