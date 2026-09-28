# 004 — Skeletons no carregamento, fotos que entram em fade e busca que não salta

- **Status**: DONE 28/09 (`components/ui/skeleton.tsx`; `.loading` virou só para leitor de tela; `searching` é derivado de `query !== search`, não um estado; fotos com `data-loaded` e `complete` no mount)
- **Commit**: `12e46d0` + alterações locais de `ux/auditoria-experiencia`
- **Severity**: HIGH
- **Category**: Missed opportunities · Performance
- **Estimated scope**: `components/ui/skeleton.tsx` (novo), `components/market.tsx` (4 pontos), `components/product-card.tsx`, `components/flyers.tsx`, `app/globals.css`

## Problem

Enquanto carrega, a interface mostra caixas de texto pulsando; as fotos aparecem de repente; ao filtrar, a
grade inteira é substituída por um bloco "Filtrando…" e volta, com salto de layout a cada tecla.

```tsx
// components/market.tsx:1169-1172 — atual
{loading ? (
  <div className="loading" role="status">
    Carregando as ofertas publicadas…
  </div>
// components/market.tsx:1476-1478 — atual
) : searching ? (
  <div role="status" className="loading">
    Filtrando…
  </div>
) : (
```

```css
/* app/globals.css:545-557 — atual */
.loading {
  padding: 60px;
  text-align: center;
  color: var(--muted);
  background: #eaf1ed;
  border-radius: 14px;
  animation: pulse 1s infinite alternate;
}
@keyframes pulse {
  to {
    opacity: 0.55;
  }
}
```

```tsx
// components/product-card.tsx:11-32 — atual: a <img> aparece assim que carrega, sem estado intermediário
<img src={product.image_url} alt="" loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={…} />
```

## Target

Portão: primeira carga (skeleton) e por cartão (foto) → "indicar estado" / "evitar salto"; filtragem
(dezenas/dia) → só um véu de 200 ms, sem stagger. Ferramenta: CSS.

```tsx
// components/ui/skeleton.tsx — alvo
export function Skeleton({ className = "", style }: { className?: string; style?: React.CSSProperties }) {
  return <span aria-hidden="true" className={`skeleton ${className}`} style={style} />;
}
export function ProductCardSkeleton() {
  return (
    <article className="product-card compact-product" aria-hidden="true">
      <div className="product-open skeleton-card">
        <Skeleton className="skeleton-photo" />
        <div className="product-summary">
          <Skeleton style={{ width: "88%", height: 18 }} />
          <Skeleton style={{ width: "40%", height: 13, marginTop: 6 }} />
          <Skeleton style={{ width: "52%", height: 28, marginTop: 10 }} />
        </div>
      </div>
      <Skeleton style={{ width: "60%", height: 13, marginTop: 12 }} />
      <Skeleton style={{ width: "100%", height: 44, marginTop: 14, borderRadius: "var(--md-radius-sm)" }} />
    </article>
  );
}
export const RailSkeleton = ({ count = 4 }) => (
  <div className="product-grid daily-grid" aria-hidden="true">{Array.from({ length: count }, (_, i) => <ProductCardSkeleton key={i} />)}</div>
);
export const GridSkeleton = ({ count = 6 }) => (
  <div className="product-grid" aria-hidden="true">{Array.from({ length: count }, (_, i) => <ProductCardSkeleton key={i} />)}</div>
);
```

```css
/* app/globals.css — alvo */
.skeleton { position: relative; display: block; overflow: hidden; border-radius: var(--md-radius-xs); background: var(--md-surface-level-2); }
.skeleton::after {
  content: ""; position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent 0%, var(--md-neutral-0) 50%, transparent 100%);
  opacity: 0.6;
  transform: translateX(-100%);
  animation: skeleton-wave 1.5s linear infinite;   /* transform only: no paint per frame */
}
@keyframes skeleton-wave { to { transform: translateX(100%); } }
.skeleton-photo { width: 62px; height: 78px; border-radius: 8px; }
.loading { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); } /* the text stays for screen readers only */
/* photo: fades in over the placeholder once decoded */
.product-photo { background: var(--md-surface-level-2); }
.product-photo img { opacity: 0; transition: opacity var(--dur-state) var(--ease-out); }
.product-photo img[data-loaded="true"] { opacity: 1; }
/* search: the current grid stays, veiled, while the next result is computed */
.results { transition: opacity var(--dur-state) var(--ease), filter var(--dur-state) var(--ease); }
.results[data-busy="true"] { opacity: 0.7; filter: blur(2px); pointer-events: none; }
```

```tsx
// components/product-card.tsx — alvo (ProductPhoto e ProductHero)
const [loaded, setLoaded] = useState(false);
<img … data-loaded={loaded} onLoad={() => setLoaded(true)}
  ref={(el) => { if (el?.complete && el.naturalWidth) setLoaded(true); }} />   // cached images fire no onLoad
```

```tsx
// components/market.tsx — alvo nos quatro pontos
{loading ? (<><p className="loading" role="status">Carregando as ofertas publicadas…</p><RailSkeleton /></>) : …}
{loading ? <Skeleton style={{ width: 240, height: 13 }} /> : `${count(coverageNow.networks)} redes · …`}
{loading ? <div className="flyer-grid" aria-hidden="true">{[0,1,2].map((i) => <FlyerCardSkeleton key={i} />)}</div> : …}
{loading ? <GridSkeleton /> : (
  <div className="results" data-busy={searching}>
    {/* grade atual, sempre montada; "Atualizando resultados…" fica na contagem, que já existe */}
  </div>
)}
```

## Repo conventions to follow

- Componentes de UI genéricos vivem em `components/`; criar a subpasta `components/ui/` para primitivos
  (skeleton, use-dialog, button) e importar com o alias `@/components/ui/...`.
- O texto de status para leitor de tela já existe (`role="status"`); manter o texto, esconder visualmente.
- Fotos usam `referrerPolicy="no-referrer"` e `loading="lazy"`: manter.

## Steps

1. Criar `components/ui/skeleton.tsx` com `Skeleton`, `ProductCardSkeleton`, `RailSkeleton`, `GridSkeleton`,
   `FlyerCardSkeleton` (capa 4:5 + duas linhas) e `ListRowSkeleton`.
2. CSS do alvo; remover `@keyframes pulse` e a caixa `.loading` visual (vira sr-only). O spinner
   `nearby-spin` fica.
3. `market.tsx`: trocar os quatro pontos (1169, 1255, 1286, 1476) como no alvo; o bloco `searching` deixa
   de desmontar a grade: remover o ramo `: searching ? (…)` e aplicar `data-busy={searching}` ao contêiner.
4. `product-card.tsx`: `data-loaded` + `onLoad` + `ref` com `complete` nas duas imagens.
5. `flyers.tsx`: a capa do encarte já tem `onLoad`; aplicar o mesmo `data-loaded` e fade.
6. Conferir que a página inicial não "pula" quando o skeleton dá lugar aos cartões reais: as alturas do
   `ProductCardSkeleton` devem bater com um cartão real a 390 px (medir e ajustar `height` das linhas).

## Boundaries

- Não animar a entrada de cada cartão a cada busca (só o véu). A entrada escalonada da faixa Hoje é do plano 006.
- Não trocar `loading="lazy"` por carregamento imediato.
- Não usar `background-position` animado (pinta a cada frame); só `transform`.

## Verification

- **Mechanical**: `npm run typecheck && npm test`; captura `390-estado-carregando` refeita com o mock em
  modo `slow` mostra skeletons, não texto; Lighthouse CLS ≤ 0,05 na Hoje.
- **Feel check**: com "Slow 3G", a Hoje mostra a faixa de 4 esqueletos com a onda passando (1,5 s por
  volta), depois os cartões reais entram e cada foto surge em 200 ms sobre o bloco cinza; digitar "leite"
  letra a letra: a grade escurece e desfoca de leve e volta, sem nenhum salto vertical; com reduced motion a
  onda para (o bloco fica estático) e o véu continua.
- **Done when**: nenhum `.loading` visível na tela em nenhum estado; `@keyframes` no CSS são só
  `skeleton-wave`, `nearby-spin` e os do leitor de encartes.
