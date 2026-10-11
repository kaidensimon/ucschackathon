// The list of keys, in a side sheet. Esc closes it and focus goes back to where it was.
import { Dialog } from "radix-ui";
import { Button } from "../shared/Button";
import { wght } from "../shared/words";

export const SHORTCUTS: { keys: string[]; joiner?: string; does: string }[] = [
  { keys: ["?"], does: "Show this list" },
  { keys: ["/"], does: "Go to the message box" },
  { keys: ["T"], does: "Show Table View" },
  { keys: ["C"], does: "Show Chat View" },
  { keys: ["Space"], does: "Pause or resume" },
  { keys: ["1", "7"], joiner: "to", does: "Open that seat" },
  { keys: ["Esc"], does: "Close what is open" },
  { keys: ["Enter"], does: "Send your message" },
  { keys: ["Shift", "Enter"], joiner: "and", does: "Start a new line" },
];

export function ShortcutsList() {
  return (
    <dl className="flex flex-col">
      {SHORTCUTS.map((s) => (
        <div
          key={s.does}
          className="flex items-center justify-between gap-4 border-hairline border-b py-2.5 last:border-b-0"
        >
          <dt className="text-label text-ink">{s.does}</dt>
          <dd className="flex shrink-0 items-center gap-1.5 text-meta text-muted">
            {s.keys.map((key, i) => (
              <span key={key} className="flex items-center gap-1.5">
                {i > 0 && s.joiner ? <span>{s.joiner}</span> : null}
                <kbd className="inline-flex h-6 min-w-6 items-center justify-center rounded-control border border-line px-1.5 font-medium font-sans text-ink text-meta">
                  {key}
                </kbd>
              </span>
            ))}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function ShortcutsSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-page/70" />
        <Dialog.Content
          data-part="shortcuts-sheet"
          className="fixed inset-y-0 right-0 z-50 flex w-90 max-w-full flex-col gap-3 overflow-y-auto border-line border-l bg-surface p-6 text-ink"
        >
          <div className="flex items-center justify-between gap-4">
            <Dialog.Title style={wght.name} className="text-heading">
              Shortcuts
            </Dialog.Title>
            <Dialog.Close asChild>
              <Button size="small">Close</Button>
            </Dialog.Close>
          </div>
          <Dialog.Description className="text-label text-muted">
            Keys work when you are not typing in a box.
          </Dialog.Description>
          <ShortcutsList />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
