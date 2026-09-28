import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from "react";

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "className"> & {
  label: ReactNode;
  /** A short line under the field: help by default, the error message when `invalid`. */
  hint?: ReactNode;
  invalid?: boolean;
  /** The label is only for assistive technology (the context already says what the field is). */
  hideLabel?: boolean;
  /** Extra classes on the wrapper, for layout. */
  className?: string;
  /** Extra classes on the input itself. */
  inputClassName?: string;
};

/**
 * A labelled text box with the field's state grid in CSS (`.field` in app/globals.css): hover,
 * focus-visible, invalid, disabled. The hint is linked to the input with aria-describedby.
 */
export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { label, hint, invalid = false, hideLabel = false, className = "", inputClassName = "", ...rest },
  ref,
) {
  const id = useId();
  const hintId = `${id}-hint`;
  return (
    <div className={`field${className ? ` ${className}` : ""}`} data-invalid={invalid || undefined}>
      <label htmlFor={id} className={hideLabel ? "sr-only" : "field-label"}>
        {label}
      </label>
      <input
        ref={ref}
        id={id}
        className={`field-input${inputClassName ? ` ${inputClassName}` : ""}`}
        aria-invalid={invalid || undefined}
        aria-describedby={hint ? hintId : undefined}
        {...rest}
      />
      {hint && (
        <small id={hintId} className={invalid ? "field-hint field-error" : "field-hint"}>
          {hint}
        </small>
      )}
    </div>
  );
});
