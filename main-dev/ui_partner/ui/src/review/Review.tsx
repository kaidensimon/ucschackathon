// The page Lucas opens at the Phase 1 review: every scene, and the questions to answer.
import { Link } from "react-router";
import { wght } from "../components/shared/words";
import { scenes } from "./states";

const QUESTIONS: string[] = [
  "Calm and readable, or control panel?",
  "Still the look you picked? Does dark read as well as light? Is there one thing that bothers you in it?",
  "Table View: can you tell at a glance who is speaking, who agreed and how close they are?",
  "Are the names in the heads readable with 3, 5 and 7 seats?",
  "Bubbles: is one short sentence enough, and is the fade speed right (press Play)? Judge the fades, not how fast the debate moves: the sample's pace is the best case.",
  "One speaker at a time and several at once are both shown, because the engine has not been built. Does either look wrong?",
  "After a vote, the check or cross stays on each head until the next round starts, as your PDF says, so during a round the heads are bare while the table still shows the last count. Keep that, or leave the marks up until the next vote?",
  "Chat View and the answer: right, or change what?",
  "When time runs out, the mock releases the best-supported answer marked “No consensus”. Keep that, or should the council keep going?",
  "Chat View switches to columns only on a wide window. Is that what you meant by “based on resolution”?",
  "When a model fails to load, the mock stops and asks you (Try again, Continue with 4, Stop). Keep that, or should the council carry on by itself with the seats that loaded?",
  "A seat’s colour belongs to its place at the table, so a model’s colour can differ from one debate to the next. Keep that, or should a model keep its own colour?",
  "Go on to Phase 2?",
];

const GROUPS: [string, string[]][] = [
  [
    "Chat, history and settings (stand-in data, no model)",
    ["real-chat-new", "real-chat", "real-chat-no-model", "history", "history-empty", "settings"],
  ],
  [
    "A debate from start to answer",
    [
      "chat-new",
      "chat-asking",
      "spooling",
      "researching",
      "debating-table",
      "vote",
      "paused",
      "owner-note",
      "agreed",
      "released",
      "released-open",
    ],
  ],
  ["Chat View", ["debating-columns", "debating-thread", "note-delivered"]],
  ["Three and seven seats", ["table-3", "table-7", "table-7-busy"]],
  ["When things go differently", ["no-consensus", "model-failed"]],
  ["Around the debate", ["seat-sheet", "shortcuts", "later-page", "gallery"]],
];

export function Review() {
  const byId = new Map(scenes.map((s) => [s.id, s]));
  const total = scenes.filter((s) => s.id !== "placeholder").length;
  const built = scenes.filter((s) => s.built && s.id !== "placeholder").length;
  return (
    <main data-part="review" className="h-full overflow-y-auto bg-page text-ink">
      <div className="mx-auto max-w-200 px-8 py-12">
        <h1 className="text-title" style={wght.title}>
          Syndicate: every screen
        </h1>
        <p className="mt-3 text-label">
          <Link to="/chat/new" className="underline underline-offset-2">
            Back to the app
          </Link>
        </p>
        <p className="mt-3 max-w-160 text-body">
          These are screens only. Nothing talks to a model and nothing is saved. The chat screens run on stand-in data;
          the debate screens show one invented debate about an apartment lease, at one moment.
        </p>
        <p className="mt-2 max-w-160 text-label text-muted">
          A slim bar at the top of each screen lets you switch theme and seat count, jump to another moment, and press
          Play. {built} of {total} screens are ready.
        </p>

        {GROUPS.map(([title, ids]) => (
          <section key={title} className="mt-8">
            <h2 className="text-heading" style={wght.name}>
              {title}
            </h2>
            <ul className="mt-2">
              {ids.map((id) => {
                const s = byId.get(id);
                if (!s) return null;
                const sep = s.route.includes("?") ? "&" : "?";
                return (
                  <li key={id} className="border-b border-hairline py-2 text-body">
                    {s.built ? (
                      <Link to={`${s.route}${sep}review=1`} className="underline underline-offset-2">
                        {s.title}
                      </Link>
                    ) : (
                      <span className="text-muted">{s.title} (not built yet)</span>
                    )}
                    {s.onlyAt ? <span className="ml-2 text-meta text-muted">best in a narrow window</span> : null}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}

        <section className="mt-10 rounded-card border border-line p-6">
          <h2 className="text-heading" style={wght.name}>
            Questions, answered by number in the chat
          </h2>
          <ol className="mt-3 list-decimal space-y-2 pl-6 text-body">
            {QUESTIONS.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ol>
        </section>
      </div>
    </main>
  );
}
