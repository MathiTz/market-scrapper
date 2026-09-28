import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Check, X } from "lucide-react";

type ChipProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  selected?: boolean;
  icon?: ReactNode;
  /** An active filter that this chip removes when pressed: it shows an × and says so to assistive technology. */
  removable?: boolean;
};

/**
 * A pill that toggles (a category, a network) or removes an active filter. One implementation for the
 * three chips the product had; a selected chip gets a tick that slides in (`.chip` in app/globals.css).
 */
export const Chip = forwardRef<HTMLButtonElement, ChipProps>(function Chip(
  { selected = false, icon, removable = false, className = "", children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      className={`chip${className ? ` ${className}` : ""}`}
      data-selected={selected || undefined}
      data-removable={removable || undefined}
      aria-pressed={removable ? undefined : selected}
      {...rest}
    >
      {!removable && (
        <span className="chip-tick" aria-hidden="true">
          <Check size={14} />
        </span>
      )}
      {icon}
      <span className="chip-label">{children}</span>
      {removable && <X size={14} aria-hidden="true" />}
    </button>
  );
});

/** The same pill as a real checkbox, for a group of toggles inside a fieldset (the chains filter). */
export function ChipCheckbox({
  checked,
  onChange,
  disabled = false,
  children,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="chip" data-selected={checked || undefined} data-disabled={disabled || undefined}>
      <input
        type="checkbox"
        className="chip-input"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="chip-tick" aria-hidden="true">
        <Check size={14} />
      </span>
      <span className="chip-label">{children}</span>
    </label>
  );
}
