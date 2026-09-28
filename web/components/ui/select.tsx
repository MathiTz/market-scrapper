import { useId } from "react";
import { Check, ChevronDown } from "lucide-react";
import { Select } from "@base-ui-components/react/select";

export type SelectOption<T extends string> = { value: T; label: string; disabled?: boolean };

/**
 * A labelled single-choice list (ordering, discount, flyer month and week). Base UI gives it the keyboard
 * and screen-reader behaviour of a native select; the popup is ours, and grows out of the trigger
 * (`--transform-origin`) instead of appearing from nowhere. Nothing else imports @base-ui-components/react
 * for selects: if the API changes, only this file changes.
 */
export function SelectField<T extends string>({
  label,
  hideLabel = false,
  value,
  onChange,
  options,
  disabled = false,
  className = "",
}: {
  label: string;
  hideLabel?: boolean;
  value: T;
  onChange: (value: T) => void;
  options: SelectOption<T>[];
  disabled?: boolean;
  /** Extra classes on the wrapper, for layout. */
  className?: string;
}) {
  const id = useId();
  const labels = Object.fromEntries(options.map((option) => [option.value, option.label])) as Record<T, string>;
  return (
    <div className={`field select-field${className ? ` ${className}` : ""}`}>
      <label htmlFor={id} className={hideLabel ? "sr-only" : "field-label"}>
        {label}
      </label>
      <Select.Root<T>
        value={value}
        onValueChange={(next) => {
          if (next !== null) onChange(next);
        }}
        items={options}
        disabled={disabled}
      >
        <Select.Trigger id={id} className="select-trigger">
          <Select.Value className="select-value">{(current: T | null) => (current === null ? "" : labels[current])}</Select.Value>
          <Select.Icon className="select-icon">
            <ChevronDown size={16} aria-hidden="true" />
          </Select.Icon>
        </Select.Trigger>
        <Select.Portal>
          <Select.Positioner className="select-positioner" sideOffset={6} alignItemWithTrigger={false}>
            <Select.Popup className="select-popup">
              <Select.List className="select-list">
                {options.map((option) => (
                  <Select.Item key={option.value} value={option.value} disabled={option.disabled} className="select-item">
                    <Select.ItemIndicator className="select-check">
                      <Check size={16} aria-hidden="true" />
                    </Select.ItemIndicator>
                    <Select.ItemText className="select-item-text">{option.label}</Select.ItemText>
                  </Select.Item>
                ))}
              </Select.List>
            </Select.Popup>
          </Select.Positioner>
        </Select.Portal>
      </Select.Root>
    </div>
  );
}
