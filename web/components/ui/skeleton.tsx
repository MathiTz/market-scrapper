import type { CSSProperties } from "react";

/** A grey bar with a wave crossing it (transform only), the shape of the text or image it stands in for. */
export function Skeleton({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return <span aria-hidden="true" className={`skeleton${className ? ` ${className}` : ""}`} style={style} />;
}

/** The silhouette of a compact product card (photo, name, pack, price, store, actions), same height as the real one. */
export function ProductCardSkeleton() {
  return (
    <article className="product-card compact-product skeleton-card" aria-hidden="true">
      <div className="product-open">
        <Skeleton className="skeleton-photo" />
        <div className="product-summary">
          <Skeleton style={{ width: "88%", height: 18 }} />
          <Skeleton style={{ width: "40%", height: 12, marginTop: 6 }} />
          <Skeleton style={{ width: "52%", height: 26, marginTop: 10 }} />
        </div>
      </div>
      <Skeleton style={{ width: "55%", height: 13, marginTop: 12 }} />
      <Skeleton style={{ width: "80%", height: 12, marginTop: 6 }} />
      <div className="product-actions">
        <Skeleton style={{ flex: 1, height: 44, borderRadius: "var(--md-radius-sm)" }} />
        <Skeleton style={{ width: 44, height: 44, borderRadius: "var(--md-radius-sm)" }} />
        <Skeleton style={{ width: 38, height: 44, borderRadius: "var(--md-radius-sm)" }} />
      </div>
    </article>
  );
}

/** The rail of the day's deals while the snapshot loads: four silhouettes in the same horizontal track. */
export function RailSkeleton({ count = 4 }: { count?: number }) {
  return (
    <section className="offer-rail" aria-hidden="true">
      <div className="product-grid daily-grid">
        {Array.from({ length: count }, (_, i) => (
          <ProductCardSkeleton key={i} />
        ))}
      </div>
    </section>
  );
}

/** The search grid while the snapshot loads. */
export function GridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="product-grid" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <ProductCardSkeleton key={i} />
      ))}
    </div>
  );
}

/** A flyer card: the 4:5 cover and two lines of text. */
export function FlyerCardSkeleton() {
  return (
    <article className="flyer-card skeleton-card" aria-hidden="true">
      <Skeleton className="skeleton-cover" />
      <div className="flyer-body">
        <Skeleton style={{ width: "70%", height: 18 }} />
        <Skeleton style={{ width: "45%", height: 12, marginTop: 8 }} />
      </div>
    </article>
  );
}

export function FlyerGridSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="flyer-grid" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <FlyerCardSkeleton key={i} />
      ))}
    </div>
  );
}
