import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "negative";
export type ButtonSize = "sm" | "md" | "lg";

/** The class list of a button-looking control, for the few links that must look like buttons. */
export function buttonClass(variant: ButtonVariant = "secondary", size: ButtonSize = "md", extra = "") {
  return `btn btn-${variant} btn-${size}${extra ? ` ${extra}` : ""}`;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** A spinner takes the icon slot and the control is disabled; the label stays, so it can say what is happening. */
  loading?: boolean;
  icon?: ReactNode;
  /** The icon comes after the label (arrows, "opens in a new tab"). */
  trailing?: boolean;
  /** No visible label: `aria-label` is required and the control is square. */
  iconOnly?: boolean;
};

/**
 * Every button of the product: one shape, four variants, three sizes, and the whole state grid in CSS
 * (`.btn` in app/globals.css): hover, focus-visible, active, disabled, loading. `type` defaults to
 * "button" so a button inside a form never submits it by accident.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    loading = false,
    icon,
    trailing = false,
    iconOnly = false,
    className = "",
    type = "button",
    children,
    disabled,
    ...rest
  },
  ref,
) {
  const slot = loading ? <span className="btn-spinner" aria-hidden="true" /> : icon;
  return (
    <button
      ref={ref}
      type={type}
      className={buttonClass(variant, size, `${iconOnly ? "btn-icon " : ""}${className}`.trim())}
      data-loading={loading || undefined}
      aria-busy={loading || undefined}
      disabled={disabled || loading}
      {...rest}
    >
      {!trailing && slot}
      {children != null && children !== false && <span className="btn-label">{children}</span>}
      {trailing && slot}
    </button>
  );
});

type IconButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> & {
  /** The accessible name; the visible tooltip (components/ui/tooltip.tsx) repeats it for sighted people. */
  label: string;
};

/** A square, borderless button that is only an icon: close, previous, next, remove. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, className = "", type = "button", children, ...rest },
  ref,
) {
  return (
    <button ref={ref} type={type} className={`icon-button${className ? ` ${className}` : ""}`} aria-label={label} {...rest}>
      {children}
    </button>
  );
});
