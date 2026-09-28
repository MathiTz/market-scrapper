import { useEffect, useState } from "react";
import { parseReais } from "@/lib/filters";
import { TextField } from "@/components/ui/field";

/** A price box in reais that keeps what is being typed ("12,") and reports cents (null when empty). */
export function PriceInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (cents: number | null) => void;
}) {
  const [text, setText] = useState(value === null ? "" : String(value / 100).replace(".", ","));
  const invalid = text.trim() !== "" && parseReais(text) === null;
  // Cleared from outside (a removed filter chip, "Limpar filtros"): empty the box too. Text that simply does
  // not parse yet also reports null, and is kept so the person can finish or fix it.
  useEffect(() => {
    if (value === null && parseReais(text) !== null) setText("");
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <TextField
      label={label}
      inputMode="decimal"
      placeholder="0,00"
      value={text}
      invalid={invalid}
      hint={invalid ? "Use apenas números, como 12,50." : undefined}
      onChange={(e) => {
        setText(e.target.value);
        onChange(parseReais(e.target.value));
      }}
    />
  );
}
