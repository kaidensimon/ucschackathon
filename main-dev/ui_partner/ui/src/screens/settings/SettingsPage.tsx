// The Settings screen (#/settings): theme, whether a model is answering, how answers are
// written, and what this build is. The data comes from useEngine() only; in this build that
// is the in-memory stand-in, so what is saved here lasts until the app closes.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert } from "lucide-react";
import { type FormEvent, type ReactNode, type RefObject, useEffect, useId, useRef, useState } from "react";
import { AppFrame } from "../../components/frame/AppFrame";
import { currentTheme, THEMES, type Theme, useTheme, useUrlState } from "../../components/frame/hooks";
import { TopBar } from "../../components/frame/TopBar";
import { useShortcuts } from "../../components/frame/useShortcuts";
import { Button } from "../../components/shared/Button";
import { CheckGlyph } from "../../components/shared/Glyph";
import { Notice } from "../../components/shared/Notice";
import { Switch } from "../../components/shared/Switch";
import { wght } from "../../components/shared/words";
import { EngineError, type ModelStatus, type Settings } from "../../engine/client";
import { useEngine, useEngineLive } from "../../engine/EngineProvider";
import { chatKeys } from "../chat/keys";
import { FIELD } from "../history/field";

export const SHORTEST = 64;
export const LONGEST = 8192;
const SETTINGS_KEY = ["settings"] as const;
const NOTE_MS = 6000;

const shownTheme = currentTheme;

/**
 * The theme that is on, wherever it was changed. This pill is the only place the owner picks it; the
 * frame's useTheme() keeps one copy per caller, so this one watches the page itself.
 */
function useShownTheme(): Theme {
  const [theme, setTheme] = useState<Theme>(shownTheme);
  useEffect(() => {
    const watch = new MutationObserver(() => setTheme(shownTheme()));
    watch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    setTheme(shownTheme());
    return () => watch.disconnect();
  }, []);
  return theme;
}

interface Note {
  tone: "quiet" | "error";
  words: string;
}

/** Everything the Answers part holds while it is being edited. Lives above the frame (see SettingsPage). */
export interface AnswersForm {
  loaded: boolean;
  longest: string;
  instructions: string;
  setLongest: (value: string) => void;
  setInstructions: (value: string) => void;
  /** the number box holds something that cannot be saved */
  badNumber: boolean;
  saving: boolean;
  note: Note | null;
  save: () => void;
}

export function useAnswersForm(): AnswersForm {
  const engine = useEngine();
  const queries = useQueryClient();
  const settings = useQuery({ queryKey: SETTINGS_KEY, queryFn: () => engine.getSettings() });
  // null = not touched: the box shows what is saved
  const [longest, setLongest] = useState<string | null>(null);
  const [instructions, setInstructions] = useState<string | null>(null);
  const [badNumber, setBadNumber] = useState(false);
  const [note, setNote] = useState<Note | null>(null);
  useEffect(() => {
    if (!note || note.tone === "error") return;
    const timer = setTimeout(() => setNote(null), NOTE_MS);
    return () => clearTimeout(timer);
  }, [note]);

  const saved = settings.data;
  const shownLongest = longest ?? (saved ? String(saved.maxAnswerTokens) : "");
  const shownInstructions = instructions ?? saved?.systemPrompt ?? "";

  const update = useMutation({
    mutationFn: (change: { maxAnswerTokens: number; systemPrompt: string }) => engine.updateSettings(change),
    onSuccess: (next: Settings) => {
      queries.setQueryData(SETTINGS_KEY, next);
      setLongest(null);
      setInstructions(null);
      setNote({ tone: "quiet", words: "Saved" });
    },
    onError: (error) =>
      setNote({
        tone: "error",
        words: error instanceof EngineError ? error.message : "The settings were not saved. Try again.",
      }),
  });

  const save = () => {
    const n = Number(shownLongest);
    if (shownLongest.trim() === "" || !Number.isInteger(n) || n < SHORTEST || n > LONGEST) {
      setBadNumber(true);
      setNote({ tone: "error", words: `Longest answer must be a whole number from ${SHORTEST} to ${LONGEST}.` });
      return;
    }
    setBadNumber(false);
    update.mutate({ maxAnswerTokens: n, systemPrompt: shownInstructions });
  };

  return {
    loaded: saved !== undefined,
    longest: shownLongest,
    instructions: shownInstructions,
    setLongest: (value) => {
      setLongest(value);
      setBadNumber(false);
    },
    setInstructions,
    badNumber,
    saving: update.isPending,
    note,
    save,
  };
}

function Part({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section
      data-part="settings-part"
      aria-labelledby={id}
      // the first part sits straight under the title: no rule there
      className="grid grid-cols-4 gap-x-6 border-hairline border-t py-6 first-of-type:border-t-0 first-of-type:pt-0"
    >
      <h2 id={id} style={wght.name} className="text-ink text-label">
        {title}
      </h2>
      <div className="col-span-3 flex min-w-0 flex-col items-start gap-2">{children}</div>
    </section>
  );
}

const QUIET = "text-label text-muted";
/** A first line in body size: lifted 4 px, so its words sit level with the part's name beside it. */
const LEAD = "-mt-1 text-body text-ink";

/** Whether a model is answering, in words with a mark. Read only. */
function ModelLine({ model }: { model: ModelStatus | null }) {
  const state = model?.state ?? "unreachable";
  if (state === "ready")
    return (
      <p data-part="model-status" data-state={state} className={`${LEAD} flex items-center gap-2`}>
        <CheckGlyph size={16} className="shrink-0" />
        <span className="font-medium">{model?.name ?? "Model"}</span>
        <span className="text-muted">ready</span>
      </p>
    );
  if (state === "loading")
    return (
      <p data-part="model-status" data-state={state} className={LEAD}>
        Model is loading
      </p>
    );
  return (
    <p data-part="model-status" data-state={state} className={`${LEAD} flex items-center gap-2`}>
      <CircleAlert size={16} aria-hidden="true" className="shrink-0 text-error" />
      No model is answering
    </p>
  );
}

/** The screen without its frame. `form` comes from useAnswersForm(). */
export function SettingsView({
  form,
  onTheme,
  focusTheme,
}: {
  form: AnswersForm;
  /** called after the theme was changed here */
  onTheme?: () => void;
  /** set to true by the page when this view is drawn anew after a theme change: focus goes back to the switch */
  focusTheme?: RefObject<boolean>;
}) {
  const engine = useEngine();
  const live = useEngineLive();
  const health = useQuery({ queryKey: chatKeys.health, queryFn: () => engine.health() });
  const [, setTheme] = useTheme();
  const theme = useShownTheme();
  const root = useRef<HTMLElement>(null);
  const titleId = useId();
  const numberId = useId();
  const hintId = useId();
  const textId = useId();

  useEffect(() => {
    if (!focusTheme?.current) return;
    focusTheme.current = false;
    root.current?.querySelector<HTMLElement>("[data-part=theme-switch] [aria-checked=true]")?.focus();
  }, [focusTheme]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    form.save();
  };

  return (
    <section
      ref={root}
      data-part="settings"
      aria-labelledby={titleId}
      // biome-ignore lint/a11y/noNoninteractiveTabindex: a scrolling area must be reachable so the keyboard can scroll it
      tabIndex={0}
      className="h-full overflow-y-auto focus-visible:-outline-offset-2"
    >
      <div className="mx-auto w-full max-w-180 px-6 pt-10 pb-16">
        <h1 id={titleId} style={wght.title} className="mb-6 text-ink text-title">
          Settings
        </h1>

        <Part title="Theme">
          {/* the switch is taller than the word beside it: lifted 8 px, so the two share one middle line */}
          <div data-part="theme-switch" className="-mt-2">
            <Switch
              label="Theme"
              value={theme}
              options={THEMES}
              onChange={(next) => {
                setTheme(next);
                onTheme?.();
              }}
            />
          </div>
        </Part>

        <Part title="Model">
          {health.isPending ? null : <ModelLine model={health.data?.model ?? null} />}
          <p className={QUIET}>
            {live
              ? "The council's models run on this computer."
              : "This build shows the screens only. It does not talk to a model yet."}
          </p>
        </Part>

        <Part title="Answers">
          <form onSubmit={submit} noValidate className="flex w-full flex-col items-start gap-2">
            <label htmlFor={numberId} className="font-medium text-ink text-label">
              Longest answer
            </label>
            <input
              id={numberId}
              type="number"
              inputMode="numeric"
              min={SHORTEST}
              max={LONGEST}
              step={1}
              value={form.longest}
              onChange={(e) => form.setLongest(e.target.value)}
              disabled={!form.loaded}
              aria-describedby={hintId}
              aria-invalid={form.badNumber || undefined}
              className={`${FIELD} h-10 w-32`}
            />
            <p id={hintId} className={QUIET}>
              In tokens, {SHORTEST} to {LONGEST}. A token is a word or part of a word.
            </p>

            <label htmlFor={textId} className="mt-4 font-medium text-ink text-label">
              Instructions for the model
            </label>
            <textarea
              id={textId}
              rows={4}
              value={form.instructions}
              onChange={(e) => form.setInstructions(e.target.value)}
              disabled={!form.loaded}
              className={`${FIELD} field-sizing-content max-h-80 min-h-28 w-full resize-none py-2`}
            />

            <div className="mt-2 flex items-center gap-4">
              <Button type="submit" variant="ink" disabled={!form.loaded || form.saving}>
                Save
              </Button>
              {/* always here, so a screen reader hears each new line */}
              <Notice data-part="settings-note" tone={form.note?.tone ?? "quiet"}>
                {form.note?.words}
              </Notice>
            </div>
            {live ? null : <p className={QUIET}>Kept until the app closes in this build.</p>}
          </form>
        </Part>

        <Part title="About">
          <p className={`${LEAD} font-medium`}>Syndicate</p>
          {live ? null : <p className={QUIET}>Phase 2 preview</p>}
          <p className={QUIET}>
            {live ? "Running on this computer. Nothing leaves it." : "Sample data. Nothing leaves this computer."}
          </p>
        </Part>
      </div>
    </section>
  );
}

/** The screen with its own form state: for the gallery and tests. */
export function SettingsBody() {
  return <SettingsView form={useAnswersForm()} />;
}

export function SettingsPage() {
  const [, change] = useUrlState();
  useShortcuts((s) => {
    if (s.kind === "help") change({ help: "1" });
    else if (s.kind === "close") change({ help: null });
    else return false;
    return true;
  });
  const form = useAnswersForm();
  // The sidebar keeps its own copy of the theme (useTheme has one per caller), so after a change
  // made here its "Theme" word would be stale. Drawing the frame anew makes it read the theme
  // again. What is typed in the form lives up here, so it is not lost, and focus is put back.
  const [drawn, setDrawn] = useState(0);
  const focusTheme = useRef(false);
  return (
    <AppFrame key={drawn} top={<TopBar seats={[]} />}>
      <SettingsView
        form={form}
        focusTheme={focusTheme}
        onTheme={() => {
          focusTheme.current = true;
          setDrawn((n) => n + 1);
        }}
      />
    </AppFrame>
  );
}
