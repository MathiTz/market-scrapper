import { useState } from "react";
import { parseReais } from "@/lib/filters";

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
  return (
    <label>
      {label}
      <input
        inputMode="decimal"
        placeholder="0,00"
        value={text}
        aria-invalid={invalid || undefined}
        onChange={(e) => {
          setText(e.target.value);
          onChange(parseReais(e.target.value));
        }}
      />
    </label>
  );
}
