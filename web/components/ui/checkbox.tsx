import { useId, type ReactNode } from "react";

/**
 * A checkbox drawn by the product: a native <input> (label association, keyboard and screen readers for
 * free) under a box whose tick draws itself in 160 ms (`.checkbox-box` in app/globals.css). The native
 * control was kept on purpose: it needs no library and is the most robust option for a form control.
 */
export function CheckboxField({
  label,
  checked,
  onChange,
  disabled = false,
  className = "",
}: {
  label: ReactNode;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
}) {
  const id = useId();
  return (
    <label
      htmlFor={id}
      className={`checkbox-field${className ? ` ${className}` : ""}`}
      data-disabled={disabled || undefined}
    >
      <span className="checkbox-box">
        <input
          id={id}
          type="checkbox"
          className="checkbox-input"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
        />
        <svg className="checkbox-mark" viewBox="0 0 16 16" aria-hidden="true">
          <path
            d="M2.5 8.5 6 12l7.5-8"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span className="checkbox-label">{label}</span>
    </label>
  );
}
