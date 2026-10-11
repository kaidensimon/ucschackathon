// What can be done with one chat in the History list. A button beside the title (never inside
// the link) opens a menu: Rename, Pin or Unpin, Export (as Markdown or JSON), Delete.
// Keyboard: Enter or Space opens it, arrows move, Esc closes and focus goes back to the button.
import { ChevronRight, Ellipsis } from "lucide-react";
import { DropdownMenu } from "radix-ui";
import { useRef } from "react";
import { IconButton } from "../../components/shared/IconButton";
import type { ChatSummary } from "../../engine/client";

export type ExportFormat = "markdown" | "json";

/** the id of a chat's menu button, so focus can be sent back to it */
export const moreId = (chatId: string) => `more-${chatId}`;

const SHEET = "z-50 min-w-44 rounded-control border border-line bg-surface p-1 text-ink";
// the item under the pointer or the keys is tinted, and the keyboard's ring is drawn inside it
const ITEM =
  "flex h-8 cursor-pointer select-none items-center justify-between gap-6 rounded-control px-2.5 text-label font-medium text-ink -outline-offset-2 data-highlighted:bg-hover data-[state=open]:bg-hover";

export function ChatMenu({
  chat,
  onRename,
  onPin,
  onExport,
  onDelete,
}: {
  chat: ChatSummary;
  /** these two open a dialog: focus is theirs to place, so the menu does not take it back */
  onRename: () => void;
  onDelete: () => void;
  onPin: () => void;
  onExport: (format: ExportFormat) => void;
}) {
  // set by an item that opens a dialog, read once when the menu has closed
  const handsOver = useRef(false);
  return (
    // not modal: the dialogs opened from here bring their own focus trap
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger asChild>
        <IconButton id={moreId(chat.id)} label={`More for ${chat.title}`} className="aria-expanded:bg-hover">
          <Ellipsis size={18} aria-hidden="true" />
        </IconButton>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          data-part="chat-menu"
          align="end"
          sideOffset={4}
          className={SHEET}
          onCloseAutoFocus={(e) => {
            if (handsOver.current) e.preventDefault();
            handsOver.current = false;
          }}
        >
          <DropdownMenu.Item
            className={ITEM}
            onSelect={() => {
              handsOver.current = true;
              onRename();
            }}
          >
            Rename
          </DropdownMenu.Item>
          <DropdownMenu.Item className={ITEM} onSelect={onPin}>
            {chat.pinned ? "Unpin" : "Pin"}
          </DropdownMenu.Item>
          <DropdownMenu.Sub>
            <DropdownMenu.SubTrigger className={ITEM}>
              Export
              <ChevronRight size={14} aria-hidden="true" className="-mr-1 text-muted" />
            </DropdownMenu.SubTrigger>
            <DropdownMenu.Portal>
              <DropdownMenu.SubContent sideOffset={6} alignOffset={-5} className={SHEET}>
                <DropdownMenu.Item className={ITEM} onSelect={() => onExport("markdown")}>
                  As Markdown
                </DropdownMenu.Item>
                <DropdownMenu.Item className={ITEM} onSelect={() => onExport("json")}>
                  As JSON
                </DropdownMenu.Item>
              </DropdownMenu.SubContent>
            </DropdownMenu.Portal>
          </DropdownMenu.Sub>
          <DropdownMenu.Separator className="mx-1 my-1 h-px bg-hairline" />
          <DropdownMenu.Item
            className={ITEM}
            onSelect={() => {
              handsOver.current = true;
              onDelete();
            }}
          >
            Delete
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
