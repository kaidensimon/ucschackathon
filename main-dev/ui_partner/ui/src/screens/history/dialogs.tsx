// The two small dialogs of the History list. Both trap focus while open. Esc closes them;
// where focus goes afterwards is the list's to say (`onClosed`), because the row that opened
// the dialog may be gone.
import { AlertDialog, Dialog } from "radix-ui";
import { type FormEvent, useId, useState } from "react";
import { Button } from "../../components/shared/Button";
import { wght } from "../../components/shared/words";
import type { ChatSummary } from "../../engine/client";
import { DIALOG_CARD, DIALOG_FIT, DIALOG_OVERLAY, FIELD } from "./field";
import { messagesWords } from "./groups";

function RenameForm({ title, onSave }: { title: string; onSave: (title: string) => void }) {
  const [name, setName] = useState(title);
  const id = useId();
  const clean = name.trim();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (clean) onSave(clean);
  };
  return (
    // Enter in the box saves: it is the form's own submit
    <form onSubmit={submit} className="mt-4 flex flex-col gap-2">
      <label htmlFor={id} className="font-medium text-ink text-label">
        Name
      </label>
      <input
        id={id}
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        // the whole old name is picked, so typing replaces it
        onFocus={(e) => e.currentTarget.select()}
        maxLength={120}
        autoComplete="off"
        className={`${FIELD} h-10 w-full`}
      />
      <div className="mt-4 flex justify-end gap-2">
        <Dialog.Close asChild>
          <Button>Cancel</Button>
        </Dialog.Close>
        <Button type="submit" variant="ink" disabled={!clean}>
          Save name
        </Button>
      </div>
    </form>
  );
}

export function RenameDialog({
  chat,
  onSave,
  onClose,
  onClosed,
}: {
  /** the chat being renamed; null keeps the dialog shut */
  chat: ChatSummary | null;
  onSave: (title: string) => void;
  onClose: () => void;
  /** the dialog is gone: put focus somewhere sensible */
  onClosed: () => void;
}) {
  return (
    <Dialog.Root
      open={chat !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className={DIALOG_OVERLAY} />
        <Dialog.Content
          data-part="rename-dialog"
          aria-describedby={undefined}
          style={DIALOG_FIT}
          className={DIALOG_CARD}
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            onClosed();
          }}
        >
          <Dialog.Title style={wght.name} className="text-heading">
            Rename this chat
          </Dialog.Title>
          {chat ? <RenameForm key={chat.id} title={chat.title} onSave={onSave} /> : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function DeleteDialog({
  chat,
  onDelete,
  onClose,
  onClosed,
}: {
  /** the chat about to be deleted; null keeps the dialog shut */
  chat: ChatSummary | null;
  onDelete: () => void;
  onClose: () => void;
  onClosed: () => void;
}) {
  return (
    <AlertDialog.Root
      open={chat !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <AlertDialog.Portal>
        <AlertDialog.Overlay className={DIALOG_OVERLAY} />
        <AlertDialog.Content
          data-part="delete-dialog"
          style={DIALOG_FIT}
          className={DIALOG_CARD}
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            onClosed();
          }}
        >
          <AlertDialog.Title style={wght.name} className="text-heading">
            Delete this chat?
          </AlertDialog.Title>
          <AlertDialog.Description className="mt-2 break-words text-label text-muted">
            <span className="font-medium text-ink">{chat?.title}</span>
            {chat && chat.messageCount > 0 ? ` and its ${messagesWords(chat.messageCount)}` : ""} will be gone. This
            cannot be undone.
          </AlertDialog.Description>
          <div className="mt-6 flex justify-end gap-2">
            {/* focus starts here: the safe choice is the one under Enter */}
            <AlertDialog.Cancel asChild>
              <Button>Keep it</Button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <Button variant="ink" onClick={onDelete}>
                Delete chat
              </Button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
