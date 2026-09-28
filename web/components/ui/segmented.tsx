import { useId, type ReactNode } from "react";
import { useIndicator } from "@/components/ui/use-indicator";

/**
 * A row of radio buttons drawn as one control with a pill that slides to the choice (the search radius).
 * The radios stay real: arrow keys move the choice, the fieldset carries the legend, a disabled fieldset
 * disables every option. The pill is measured from the selected label, so any number of options works.
 */
export function Segmented<T extends string | number>({
  legend,
  options,
  value,
  onChange,
  onPick,
  disabled = false,
  className = "",
}: {
  legend: ReactNode;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  /** After a pointer click on an option (not the arrow keys), so a dialog can close on a tap and stay open while arrowing. */
  onPick?: (value: T, byPointer: boolean) => void;
  disabled?: boolean;
  className?: string;
}) {
  const id = useId();
  const pill = useIndicator<HTMLDivElement>(".segmented-option[data-selected]", [value, options.length]);
  return (
    <fieldset className={`segmented${className ? ` ${className}` : ""}`} disabled={disabled}>
      <legend className="segmented-legend">{legend}</legend>
      <div ref={pill.ref} className="segmented-track" data-ready={pill.ready ? "" : undefined} style={pill.style}>
        <span className="segmented-pill" aria-hidden="true" />
        {options.map((option) => (
          <label key={String(option.value)} className="segmented-option" data-selected={value === option.value || undefined}>
            <input
              type="radio"
              name={id}
              value={String(option.value)}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              onClick={(event) => onPick?.(option.value, event.detail > 0)}
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
