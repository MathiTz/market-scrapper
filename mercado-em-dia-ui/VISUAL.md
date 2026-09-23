# Referência visual
## Fonte de verdade
Componentes e app/globals.css são a implementação recebida. Capturas são apoio. referencias/historicas contém estados de momentos diferentes do projeto; para divergências, priorize código atual e referencias/preview.
## Estilo
Arial, Helvetica, sans-serif. Ícones lucide-react.
Tokens: --green #116249; --dark #173d30; --lime #d9ed92; --bg #f6f8f7; --line #dde6e1; --text #1e332a; --muted #66776d; --white #fff; --amber #865510.
Base 16px, entrelinha 1.5. CSS inclui foco visível e redução de movimento.
Quebras de layout: 1200, 760 e 460px, além de regras para pouca altura.
## Mapa
| Experiência | Arquivos em components/ |
|---|---|
| Navegação, Hoje, Buscar, comparação e lista | market.tsx |
| Cartões e fotos/fallback | product-card.tsx |
| Faixa horizontal de ofertas | offer-rail.tsx |
| Endereço/GPS | nearby-filter.tsx |
| Loja e contato | store-location.tsx; store-contact.tsx |
| Compartilhar | offer-share.tsx |
| Redes, períodos e arquivo de encartes | flyers.tsx |
| Leitor, zoom e navegação | flyer-stories.tsx; flyer-player.tsx |
| Administração | admin.tsx |
## Aceite após integração
- Conferir 320, 390 e 1280px; sem rolagem horizontal da página (a faixa de ofertas tem rolagem própria).
- Preservar hierarquia de preço, embalagem, condições, origem, endereço e distância.
- Conferir Hoje, Buscar, comparação, Minha lista e Encartes.
- Conferir oferta antiga, clube, ausência de foto, busca vazia e falha de API.
- Conferir quantidade e persistência da lista após recarregar.
- Conferir modais, foco de teclado, leitor de encartes, pausa, zoom e arquivo.
- Conferir compartilhar e reabrir produto/encarte.
As capturas novas usam dados fictícios e o aviso de demonstração original.