// The chat screen: one owner talks to one model. #/chat/new is an empty chat; #/chat/<id> is
// a saved one. Everything shown comes from useEngine() (in this phase an in-memory stand-in):
// the chat through React Query, the answer being written through engine.streamRun.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import { AppFrame } from "../../components/frame/AppFrame";
import { useUrlState } from "../../components/frame/hooks";
import { useShortcuts } from "../../components/frame/useShortcuts";
import { Button } from "../../components/shared/Button";
import { Notice } from "../../components/shared/Notice";
import { Switch } from "../../components/shared/Switch";
import { wght } from "../../components/shared/words";
import { type Chat, EngineError, type Message, type RunStarted } from "../../engine/client";
import { useEngine } from "../../engine/EngineProvider";
import { HttpEngine } from "../../engine/http";
import { ChatBody } from "./ChatBody";
import { ChatTopBar, chooseSeats, ModelPill, SeatSlider, seatsOf, useSeatChoice } from "./ChatTopBar";
import { STOPPED } from "./Conversation";
import { chatKeys } from "./keys";
import { LiveStage } from "./LiveStage";
import { MessageBox } from "./MessageBox";
import { useLiveAnswer } from "./useLiveAnswer";

export const NEW_CHAT = "New chat";
export const APP_NAME = "Syndicate";
export const MISSING_LINE = "That chat does not exist any more.";
export const NOT_OPENED_LINE = "This chat could not be opened.";
/** under the empty seats: the owner chooses how many, never which */
export const ROUTER_HINT = "The router picks the models when you ask";
export const ROUTER_PICKING = "The router is picking the models";
/** when something fails without words of its own */
export const DID_NOT_WORK = "That did not work. Try again.";

const isMissing = (error: unknown) => error instanceof EngineError && error.status === 404;
const wordsOf = (error: unknown) => (error instanceof EngineError && error.message ? error.message : DID_NOT_WORK);

/** What a screen reader hears when the newest answer changes state. Never each word. */
function useSaid(newest: Message | undefined): string {
  const before = useRef<string | null>(null);
  const [said, setSaid] = useState("");
  const now = newest?.role === "assistant" ? `${newest.id}:${newest.status}` : null;
  const status = newest?.status;
  useEffect(() => {
    const was = before.current;
    before.current = now;
    // opening a chat is not news; the failed answer speaks for itself (it is an alert)
    if (was === null || now === null || was === now) return;
    if (status === "writing") setSaid("Writing the answer");
    else if (status === "complete") setSaid("The answer is ready");
    else if (status === "stopped") setSaid(STOPPED);
  }, [now, status]);
  return said;
}

export function ChatPage() {
  const { id: inAddress } = useParams();
  // After the first Ask the address takes a moment to change to the new chat. Until it has,
  // this is the chat on screen, so words typed in that moment go to it and not to another new chat.
  const [justMade, setJustMade] = useState<string | null>(null);
  useEffect(() => {
    if (inAddress !== undefined) setJustMade(null);
  }, [inAddress]);
  const id = inAddress ?? justMade ?? undefined;
  const where = id ?? "new";
  const engine = useEngine();
  const queries = useQueryClient();
  const navigate = useNavigate();
  const { search: query } = useLocation();
  const [search, change] = useUrlState();
  const box = useRef<HTMLTextAreaElement>(null);
  // words typed in one chat stay with that chat
  const [draft, setDraft] = useState({ at: where, text: "" });
  const [problem, setProblem] = useState<{ at: string; words: string } | null>(null);
  // an empty chat made by a press that then failed: the next press uses it again
  const made = useRef<Chat | null>(null);

  // How many models sit at the table: one number (useSeatChoice), sent with every question and
  // drawn by the idle table. "?seats=N" in the address sets it too, and follows the slider.
  const [seats, setSeats] = useSeatChoice();
  // "Web search" switch: off unless the owner turns it on; remembered on this computer. When on, the
  // engine runs one plain web search for the question and hands the first results to the council.
  const [webSearch, setWebSearch] = useState<boolean>(() => {
    try {
      return localStorage.getItem("council.search") === "on";
    } catch {
      return false;
    }
  });
  const chooseWebSearch = useCallback((value: "off" | "on") => {
    setWebSearch(value === "on");
    try {
      localStorage.setItem("council.search", value);
    } catch {
      // private mode: the choice lasts until the window closes
    }
  }, []);
  const seatsInAddress = search.get("seats");
  useEffect(() => {
    chooseSeats(seatsInAddress);
  }, [seatsInAddress]);
  const onSeats = (next: number) => {
    setSeats(next);
    if (seatsInAddress !== null) change({ seats: String(next) });
  };
  // the runs this screen started, with the seats it asked for; and the run behind each answer,
  // kept after the answer is written so its debate stays on screen
  const askedSeats = useRef(new Map<string, number>());
  const runOf = useRef(new Map<string, string>());

  const health = useQuery({ queryKey: chatKeys.health, queryFn: () => engine.health() });
  const chat = useQuery({
    queryKey: chatKeys.chat(where),
    queryFn: () => engine.getChat(where),
    enabled: id !== undefined,
    retry: (failures, error) => !isMissing(error) && failures < 1,
  });

  const messages = (id !== undefined && chat.data?.messages) || [];
  const newest = messages.at(-1);
  const writing = newest?.role === "assistant" && newest.status === "writing";
  const live = useLiveAnswer(id, writing ? newest.runId : null);
  const said = useSaid(newest);

  const failed = (error: unknown) => setProblem({ at: where, words: wordsOf(error) });

  const ask = useMutation({
    mutationFn: async (text: string) => {
      let fresh: Chat | null = null;
      if (id === undefined) {
        made.current ??= await engine.createChat();
        fresh = made.current;
      }
      const chatId = fresh?.id ?? where;
      // an address that names a size wins over a choice it has not reached yet (first render)
      const asked = seatsOf(seatsInAddress) ?? seats;
      // Web search on: the desktop shell (a real browser) runs the search and the results travel
      // with the question. In a plain browser tab there is no shell, and the engine tries itself.
      let found: { title: string; url: string; snippet: string }[] | undefined;
      if (webSearch) {
        const shell = (window as unknown as { gx10?: { webSearch?: (q: string) => Promise<unknown> } }).gx10;
        if (shell?.webSearch) {
          try {
            const got = await shell.webSearch(text);
            if (Array.isArray(got)) found = got as { title: string; url: string; snippet: string }[];
          } catch {
            found = undefined;
          }
        }
      }
      const run = await engine.sendMessage(chatId, text, asked, webSearch, found);
      askedSeats.current.set(run.runId, asked);
      return { chatId, fresh, run };
    },
    onMutate: () => setProblem(null),
    onError: failed,
    onSuccess: ({ chatId, fresh, run }) => {
      made.current = null;
      queries.setQueryData<Chat>(chatKeys.chat(chatId), (old) => {
        const base = old ?? fresh;
        if (!base) return old;
        return {
          ...base,
          title: run.chat.title,
          updatedAt: run.chat.updatedAt,
          messageCount: run.chat.messageCount,
          messages: [...base.messages, ...(run.userMessage ? [run.userMessage] : []), run.assistantMessage],
        };
      });
      void queries.invalidateQueries({ queryKey: chatKeys.lists });
      setDraft({ at: chatId, text: "" });
      if (fresh) {
        setJustMade(chatId);
        // the address keeps its options (?fast=1 and the like)
        navigate({ pathname: `/chat/${chatId}`, search: query });
      }
    },
  });

  const again = useMutation({
    mutationFn: async (chatId: string): Promise<{ chatId: string; run: RunStarted }> => ({
      chatId,
      run: await engine.regenerate(chatId),
    }),
    onMutate: () => setProblem(null),
    onError: failed,
    onSuccess: ({ chatId, run }) => {
      queries.setQueryData<Chat>(
        chatKeys.chat(chatId),
        (old) =>
          old && {
            ...old,
            updatedAt: run.chat.updatedAt,
            // the newest answer is the one written again
            messages: [...old.messages.slice(0, -1), run.assistantMessage],
          },
      );
      void queries.invalidateQueries({ queryKey: chatKeys.lists });
    },
  });

  const stop = useMutation({
    mutationFn: (runId: string) => engine.stopRun(runId),
    onError: failed,
  });

  const { mutate: writeAgain } = again;
  const onWriteAgain = useCallback(() => writeAgain(where), [writeAgain, where]);
  const busy = ask.isPending || again.isPending;

  const help = search.get("help") === "1";
  useShortcuts((s) => {
    if (s.kind === "close") {
      if (help) change({ help: null });
      return help;
    }
    if (help) return false; // the sheet is open: its own keys only
    if (s.kind === "help") {
      change({ help: "1" });
      return true;
    }
    if (s.kind === "message" && box.current) {
      box.current.focus();
      return true;
    }
    return false;
  });

  const real = engine instanceof HttpEngine;
  // The debate on screen: the run being written, or the run behind the newest answer (kept
  // until the next question is sent). The engine may drop runId once the answer is saved.
  if (newest?.role === "assistant" && newest.runId) runOf.current.set(newest.id, newest.runId);
  const stageRun = newest?.role === "assistant" ? (newest.runId ?? runOf.current.get(newest.id) ?? null) : null;
  // before the debate has seats of its own: the chosen council in an empty chat, and the seats
  // this screen asked for while they are being filled (Write again seats the engine's own number)
  const seatingFor = writing && stageRun ? askedSeats.current.get(stageRun) : undefined;
  const waiting = messages.length === 0 ? "idle" : seatingFor !== undefined ? "seating" : null;
  const waitingNow = ask.isPending ? "seating" : waiting;
  const stage = real ? (
    <>
      <LiveStage
        // the next question gets a stage of its own: the old debate goes at once
        key={ask.isPending ? "asking" : (stageRun ?? "none")}
        runId={ask.isPending ? null : stageRun}
        running={writing}
        seats={seatingFor ?? seats}
        waiting={waitingNow}
      />
      {/* the owner picks how many; the router picks who */}
      {waitingNow === "idle" || waitingNow === "seating" ? (
        <p data-part="router-hint" className="shrink-0 px-6 pt-2 text-center text-meta text-muted">
          {waitingNow === "idle" ? ROUTER_HINT : ROUTER_PICKING}
        </p>
      ) : null}
    </>
  ) : null;
  const council = real ? (
    <div className="flex items-center gap-3">
      <SeatSlider seats={seats} onSeats={onSeats} />
      <Switch
        label="Web search"
        value={webSearch ? "on" : "off"}
        options={[
          { value: "off", label: "No web" },
          { value: "on", label: "Web search" },
        ]}
        onChange={chooseWebSearch}
      />
    </div>
  ) : null;

  const pill = <ModelPill model={health.data ? health.data.model : health.isError ? null : undefined} />;

  if (id !== undefined && chat.isError) {
    const gone = isMissing(chat.error);
    return (
      <AppFrame top={<ChatTopBar title={APP_NAME} pill={pill} />}>
        <section data-part={gone ? "chat-missing" : "chat-not-opened"} className="h-full px-6">
          {/* the same 640 px column the messages keep */}
          <div className="mx-auto flex h-full max-w-160 flex-col items-start justify-center pb-24">
            <h1 style={wght.title} className="text-ink text-title">
              {gone ? MISSING_LINE : NOT_OPENED_LINE}
            </h1>
            {/* one way on: the address keeps its options (?fast=1 and the like) */}
            {gone ? (
              <Button variant="ink" className="mt-5" onClick={() => navigate({ pathname: "/chat/new", search: query })}>
                Start a new chat
              </Button>
            ) : (
              <Button variant="ink" className="mt-5" onClick={() => void chat.refetch()}>
                Try again
              </Button>
            )}
          </div>
        </section>
      </AppFrame>
    );
  }

  const title = id === undefined ? NEW_CHAT : (chat.data?.title ?? APP_NAME);
  const shownProblem = problem && problem.at === where ? problem.words : null;

  return (
    <AppFrame top={<ChatTopBar title={title} heading={messages.length > 0} council={council} pill={pill} />}>
      {id !== undefined && chat.isPending ? null : (
        <ChatBody
          chatKey={where}
          messages={messages}
          live={live}
          busy={busy}
          onWriteAgain={onWriteAgain}
          stage={stage}
          box={
            <MessageBox
              value={draft.at === where ? draft.text : ""}
              onChange={(text) => setDraft({ at: where, text })}
              onAsk={() => ask.mutate(draft.text.trim())}
              onStop={() => {
                if (writing && newest.runId) stop.mutate(newest.runId);
              }}
              writing={writing}
              busy={busy}
              notice={shownProblem ? <Notice tone="error">{shownProblem}</Notice> : null}
              inputRef={box}
            />
          }
        />
      )}
      <div data-part="chat-live-region" aria-live="polite" aria-atomic="true" className="sr-only">
        {said}
      </div>
    </AppFrame>
  );
}
