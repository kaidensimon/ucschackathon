// The History screen without its frame: the title, the search box, and every chat under a
// plain heading (Pinned, Today, Yesterday, Earlier). A chat's title is its link; what can be
// done with it sits beside the title in a menu. The data comes from useEngine() only.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { Fragment, type ReactNode, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { carried } from "../../components/frame/Sidebar";
import { Button } from "../../components/shared/Button";
import { IconButton } from "../../components/shared/IconButton";
import { Notice } from "../../components/shared/Notice";
import { wght } from "../../components/shared/words";
import { type ChatSummary, type ChatUpdate, EngineError } from "../../engine/client";
import { useEngine } from "../../engine/EngineProvider";
import { chatKeys } from "../chat/keys";
import { ChatMenu, type ExportFormat, moreId } from "./ChatMenu";
import { DeleteDialog, RenameDialog } from "./dialogs";
import { FIELD } from "./field";
import { type GroupName, groupChats, plainWords, whenWords } from "./groups";
import { saveFile } from "./saveFile";

/** how long the list waits after the last key before it searches */
const SEARCH_WAIT_MS = 200;
/** how long focus is held on a row's menu button while the row moves to another heading */
const MOVE_MS = 2000;
/** how long a quiet line such as "Saved lease.md" stays */
const NOTE_MS = 6000;

interface Note {
  tone: "quiet" | "error";
  words: string;
}

/** The engine explains its own failures in plain words; anything else gets ours. */
const said = (error: unknown, ours: string) => (error instanceof EngineError ? error.message : ours);

/** The words of a search hit, with each place the search matches set heavier. */
function Marked({ text, query }: { text: string; query: string }) {
  const q = query.toLowerCase();
  if (!q) return text;
  const lower = text.toLowerCase();
  const parts: ReactNode[] = [];
  let from = 0;
  for (let at = lower.indexOf(q); at !== -1; at = lower.indexOf(q, from)) {
    parts.push(
      <Fragment key={at}>
        {text.slice(from, at)}
        <mark style={wght.name} className="bg-transparent text-ink">
          {text.slice(at, at + q.length)}
        </mark>
      </Fragment>,
    );
    from = at + q.length;
  }
  parts.push(text.slice(from));
  return parts;
}

function Row({
  chat,
  under,
  now,
  query,
  keep,
  onRename,
  onPin,
  onExport,
  onDelete,
}: {
  chat: ChatSummary;
  under: GroupName;
  now: Date;
  query: string;
  /** the address options links take along */
  keep: string;
  onRename: () => void;
  onPin: () => void;
  onExport: (format: ExportFormat) => void;
  onDelete: () => void;
}) {
  return (
    <li data-part="history-row" className="flex items-center gap-3 border-hairline border-b py-3 last:border-b-0">
      <div className="min-w-0 flex-1">
        <Link
          to={{ pathname: `/chat/${chat.id}`, search: keep }}
          className="inline-block max-w-full truncate rounded-control align-top font-medium text-body text-ink underline-offset-4 hover:underline"
        >
          {chat.title}
        </Link>
        <p data-part="history-preview" className="truncate text-label text-muted">
          {chat.match ? <Marked text={plainWords(chat.match)} query={query} /> : plainWords(chat.preview)}
        </p>
      </div>
      {/* one width for every row, so each preview ends at the same edge ("Yesterday 16:00" is the longest) */}
      <time
        dateTime={chat.updatedAt}
        style={{ minWidth: 88 }}
        className="shrink-0 whitespace-nowrap text-right text-meta text-muted"
      >
        {whenWords(chat.updatedAt, now, under)}
      </time>
      <ChatMenu chat={chat} onRename={onRename} onPin={onPin} onExport={onExport} onDelete={onDelete} />
    </li>
  );
}

export function HistoryList({
  initialQuery = "",
  onQuery,
  now: fixedNow,
}: {
  /** what the search box holds when the screen opens */
  initialQuery?: string;
  /** told each search once it has been made (the page keeps it in the address) */
  onQuery?: (query: string) => void;
  /** a fixed "now" for tests and the gallery */
  now?: Date;
}) {
  const engine = useEngine();
  const queries = useQueryClient();
  const navigate = useNavigate();
  const keep = carried(useLocation().search);
  const titleId = useId();
  const heading = useRef<HTMLHeadingElement>(null);

  // ---- search: the box is typed in at once, the list follows 200 ms after the last key
  const [text, setText] = useState(initialQuery);
  const [query, setQuery] = useState(initialQuery.trim());
  const told = useRef(query);
  const tell = useRef(onQuery);
  tell.current = onQuery;
  useEffect(() => {
    const timer = setTimeout(() => setQuery(text.trim()), SEARCH_WAIT_MS);
    return () => clearTimeout(timer);
  }, [text]);
  useEffect(() => {
    if (told.current === query) return;
    told.current = query;
    tell.current?.(query);
  }, [query]);

  const list = useQuery({
    queryKey: [...chatKeys.lists, query],
    queryFn: () => engine.listChats(query || undefined),
    // while the next search is on its way the last list stays, so the screen does not blink
    placeholderData: keepPreviousData,
  });
  const health = useQuery({ queryKey: chatKeys.health, queryFn: () => engine.health() });

  // "Now" for the day headings. The sample data is stamped by the stand-in's own fixed clock,
  // and the only place that clock shows is the time of its last model check; the headings are
  // worked out against it, so the sample chats sit under the same headings on any day.
  const checkedAt = health.data?.model.checkedAt;
  const healthSettled = health.isSuccess || health.isError;
  const now = useMemo(
    () => fixedNow ?? (checkedAt ? new Date(checkedAt) : healthSettled ? new Date() : null),
    [fixedNow, checkedAt, healthSettled],
  );

  // ---- the one quiet line that answers what was just done
  const [note, setNote] = useState<Note | null>(null);
  useEffect(() => {
    if (!note || note.tone === "error") return;
    const timer = setTimeout(() => setNote(null), NOTE_MS);
    return () => clearTimeout(timer);
  }, [note]);

  const [renaming, setRenaming] = useState<ChatSummary | null>(null);
  const [deleting, setDeleting] = useState<ChatSummary | null>(null);
  /** the chat whose menu opened a dialog: focus goes back to its button, or to the title if it is gone */
  const openedFrom = useRef<string | null>(null);
  /**
   * The chat whose row is moving to another heading (pin, unpin). The row is drawn anew there,
   * so the keyboard would be left on nothing: for a moment it is put back on the row's menu button.
   */
  const moving = useRef<{ id: string; until: number } | null>(null);
  useEffect(() => {
    const move = moving.current;
    if (!move) return;
    if (Date.now() > move.until) {
      moving.current = null;
      return;
    }
    const at = document.activeElement;
    const lost = !at || at === document.body || at.closest("[data-part=chat-menu]") !== null;
    if (lost) document.getElementById(moreId(move.id))?.focus();
  });
  /** chats being deleted: their rows are about to go, so focus must not be sent back to them */
  const leaving = useRef(new Set<string>());

  const refresh = (id: string) => {
    void queries.invalidateQueries({ queryKey: chatKeys.lists });
    void queries.invalidateQueries({ queryKey: chatKeys.chat(id) });
  };

  const update = useMutation({
    mutationFn: ({ chat, change }: { chat: ChatSummary; change: ChatUpdate; failed: string }) =>
      engine.updateChat(chat.id, change),
    // the list shows the change at once; if the engine says no, the old list comes back
    onMutate: async ({ chat, change }) => {
      await queries.cancelQueries({ queryKey: chatKeys.lists });
      const before = queries.getQueriesData<ChatSummary[]>({ queryKey: chatKeys.lists });
      queries.setQueriesData<ChatSummary[]>({ queryKey: chatKeys.lists }, (old) =>
        old?.map((c) => (c.id === chat.id ? { ...c, ...change } : c)),
      );
      return { before };
    },
    onError: (error, { failed }, context) => {
      for (const [key, data] of context?.before ?? []) queries.setQueryData(key, data);
      setNote({ tone: "error", words: said(error, failed) });
    },
    onSuccess: () => setNote(null),
    onSettled: (_data, _error, { chat }) => refresh(chat.id),
  });

  const remove = useMutation({
    mutationFn: (chat: ChatSummary) => engine.deleteChat(chat.id),
    onSuccess: (_nothing, chat) => {
      queries.setQueriesData<ChatSummary[]>({ queryKey: chatKeys.lists }, (old) =>
        old?.filter((c) => c.id !== chat.id),
      );
      setNote({ tone: "quiet", words: `Deleted ${chat.title}` });
    },
    onError: (error) => setNote({ tone: "error", words: said(error, "The chat was not deleted. Try again.") }),
    onSettled: (_data, _error, chat) => {
      leaving.current.delete(chat.id);
      refresh(chat.id);
    },
  });

  const save = useMutation({
    mutationFn: ({ chat, format }: { chat: ChatSummary; format: ExportFormat }) => engine.exportChat(chat.id, format),
    onSuccess: (file) => setNote({ tone: "quiet", words: `Saved ${saveFile(file)}` }),
    onError: (error) => setNote({ tone: "error", words: said(error, "The chat was not saved to a file. Try again.") }),
  });

  const pin = (chat: ChatSummary) => {
    moving.current = { id: chat.id, until: Date.now() + MOVE_MS };
    update.mutate({
      chat,
      change: { pinned: !chat.pinned },
      failed: chat.pinned ? "The chat was not unpinned. Try again." : "The chat was not pinned. Try again.",
    });
  };
  const rename = (title: string) => {
    const chat = renaming;
    setRenaming(null);
    if (!chat || title === chat.title) return;
    update.mutate({ chat, change: { title }, failed: "The new name was not saved. Try again." });
  };
  // a dialog has closed: the keyboard goes back to the row's menu button, or to the title when
  // the row is gone or going
  const backToRow = () => {
    const id = openedFrom.current;
    openedFrom.current = null;
    const button = id && !leaving.current.has(id) ? document.getElementById(moreId(id)) : null;
    (button ?? heading.current)?.focus();
  };

  const chats = list.data;
  // a list still on show from the search before says nothing about this one
  const settled = chats !== undefined && !list.isPlaceholderData;
  const noChats = settled && chats.length === 0 && query === "";
  const noHits = settled && chats.length === 0 && query !== "";
  const groups = useMemo(() => (chats && now ? groupChats(chats, now) : []), [chats, now]);

  return (
    <section
      data-part="history"
      aria-labelledby={titleId}
      // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrolling area must be reachable so the keyboard can scroll it
      tabIndex={0}
      className="h-full overflow-y-auto focus-visible:-outline-offset-2"
    >
      <div className="mx-auto w-full max-w-180 px-6 pt-10 pb-16">
        <h1
          ref={heading}
          id={titleId}
          tabIndex={-1}
          style={wght.title}
          className="w-fit rounded-control text-ink text-title"
        >
          History
        </h1>

        {noChats ? null : (
          <search className="relative mt-5 block">
            <input
              type="search"
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                // Esc empties the box; with nothing in it Esc is left to the page
                if (e.key === "Escape" && text) setText("");
              }}
              placeholder="Search your chats"
              aria-label="Search your chats"
              autoComplete="off"
              spellCheck={false}
              // the browser's own clear mark is left out: the Clear button beside it follows the theme and the keyboard
              className={`${FIELD} h-11 w-full pr-11 [&::-webkit-search-cancel-button]:hidden`}
            />
            {text ? (
              <IconButton
                label="Clear the search"
                onClick={() => setText("")}
                className="absolute top-1 right-1"
                tooltipSide="left"
              >
                <X size={18} aria-hidden="true" />
              </IconButton>
            ) : null}
          </search>
        )}

        {/* always here, so a screen reader hears each new line and the list does not jump */}
        <Notice data-part="history-note" tone={note?.tone ?? "quiet"} className="mt-2 min-h-4">
          {note?.words}
        </Notice>

        {list.isError && !chats ? (
          <div className="mt-6 flex flex-col items-start gap-3">
            <Notice tone="error" className="text-label">
              {said(list.error, "Your chats did not load.")}
            </Notice>
            <Button onClick={() => void list.refetch()}>Try again</Button>
          </div>
        ) : null}

        {noChats ? (
          <div data-part="history-empty" className="mt-4 flex flex-col items-start gap-4">
            <p className="text-body text-muted">No chats yet.</p>
            <Button variant="ink" onClick={() => navigate({ pathname: "/chat/new", search: keep })}>
              Start a new chat
            </Button>
          </div>
        ) : null}

        {noHits ? (
          <p data-part="history-no-hits" className="mt-6 break-words text-body text-muted">
            No chat mentions <span className="font-medium text-ink">{query}</span>.
          </p>
        ) : null}

        {groups.map((group) => (
          <section key={group.name} data-part="history-group" aria-labelledby={`${titleId}-${group.name}`}>
            <h2
              id={`${titleId}-${group.name}`}
              className="mt-6 border-hairline border-b pb-2 font-medium text-label text-muted"
            >
              {group.name}
            </h2>
            <ul>
              {group.chats.map((chat) => (
                <Row
                  key={chat.id}
                  chat={chat}
                  under={group.name}
                  now={now ?? new Date(chat.updatedAt)}
                  query={query}
                  keep={keep}
                  onRename={() => {
                    openedFrom.current = chat.id;
                    setRenaming(chat);
                  }}
                  onPin={() => pin(chat)}
                  onExport={(format) => save.mutate({ chat, format })}
                  onDelete={() => {
                    openedFrom.current = chat.id;
                    setDeleting(chat);
                  }}
                />
              ))}
            </ul>
          </section>
        ))}
      </div>

      <RenameDialog chat={renaming} onSave={rename} onClose={() => setRenaming(null)} onClosed={backToRow} />
      <DeleteDialog
        chat={deleting}
        onDelete={() => {
          if (!deleting) return;
          leaving.current.add(deleting.id);
          remove.mutate(deleting);
        }}
        onClose={() => setDeleting(null)}
        onClosed={backToRow}
      />
    </section>
  );
}
