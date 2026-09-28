import NumberFlow from "@number-flow/react";

/** 300 ms on the product's exit curve, for every animated figure; NumberFlow itself honours reduced motion. */
const timing = { duration: 300, easing: "cubic-bezier(0.23, 1, 0.32, 1)" };

/** A count whose digits slide into place when it changes (a quantity, the items badge). */
export function Count({ value, className }: { value: number; className?: string }) {
  return (
    <NumberFlow
      value={value}
      locales="pt-BR"
      className={className}
      transformTiming={timing}
      spinTiming={timing}
      opacityTiming={{ duration: 200, easing: "ease-out" }}
    />
  );
}

/** A price in reais whose digits slide when the amount changes (the estimate of a chain). */
export function Money({ cents, className }: { cents: number; className?: string }) {
  return (
    <NumberFlow
      value={cents / 100}
      locales="pt-BR"
      format={{ style: "currency", currency: "BRL" }}
      className={className}
      transformTiming={timing}
      spinTiming={timing}
      opacityTiming={{ duration: 200, easing: "ease-out" }}
    />
  );
}
