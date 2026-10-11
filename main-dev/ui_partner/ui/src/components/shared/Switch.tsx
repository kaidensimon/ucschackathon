import { ToggleGroup } from "radix-ui";

export interface SwitchOption<T extends string> {
  value: T;
  label: string;
}

/** Two or three options, one always chosen. Arrow keys move between them; Enter or Space chooses. */
export function Switch<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  /** what the switch sets, read aloud ("View", "Theme") */
  label: string;
  value: T;
  options: readonly [SwitchOption<T>, SwitchOption<T>, ...SwitchOption<T>[]];
  onChange: (value: T) => void;
}) {
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      // pressing the chosen side again must not leave the switch with nothing chosen
      onValueChange={(next) => {
        if (next) onChange(next as T);
      }}
      aria-label={label}
      className="inline-flex shrink-0 rounded-full border border-line p-0.75"
    >
      {options.map((o) => (
        <ToggleGroup.Item
          key={o.value}
          value={o.value}
          className="h-7 cursor-pointer rounded-full px-3.5 text-label font-medium text-ink transition-colors duration-(--quick) data-[state=off]:hover:bg-hover data-[state=on]:bg-accent data-[state=on]:text-on-accent"
        >
          {o.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
