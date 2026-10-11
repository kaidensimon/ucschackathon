import { useState } from "react";
import type { Message } from "../../engine/client";
import type { GalleryEntry } from "../../gallery/entry";
import { ChatBody } from "./ChatBody";
import { ChatTopBar, ModelPill } from "./ChatTopBar";
import { MessageBox } from "./MessageBox";

const AT = "2026-10-10T18:00:00.000Z";

const message = (id: string, role: Message["role"], text: string, extra: Partial<Message> = {}): Message => ({
  id,
  chatId: "sample",
  role,
  text,
  status: "complete",
  createdAt: AT,
  model: role === "assistant" ? "stand-in-model" : null,
  tokensPerSecond: role === "assistant" ? 41.5 : null,
  answerTokens: null,
  error: null,
  runId: null,
  ...extra,
});

const QUESTION = message("q", "user", "Give me a packing list for a week in a cold city.");
const FULL = "- Warm coat\n- Two jumpers\n- Waterproof shoes\n- Gloves, hat, scarf\n- Chargers and an adapter";
// cut off inside the bold words, as it is while the words arrive
const HALF = "Pack for the cold first:\n\n- Warm coat\n- Two jumpers\n- **Waterproof sh";

function Sample({
  messages,
  liveText,
  height = 420,
}: {
  messages: Message[];
  /** the words so far of the answer being written */
  liveText?: string;
  height?: number;
}) {
  const [text, setText] = useState("");
  const writing = messages.at(-1)?.status === "writing";
  return (
    <div className="overflow-hidden rounded-control border border-hairline" style={{ height }}>
      <ChatBody
        chatKey="sample"
        messages={messages}
        live={liveText === undefined ? null : { runId: "r", text: liveText }}
        onWriteAgain={() => {}}
        box={
          <MessageBox value={text} onChange={setText} onAsk={() => setText("")} onStop={() => {}} writing={writing} />
        }
      />
    </div>
  );
}

export const entries: GalleryEntry[] = [
  {
    name: "Chat, empty",
    note: "Before the first question. Ask is dashed until something is typed.",
    render: () => <Sample messages={[]} height={300} />,
  },
  {
    name: "Chat, one exchange",
    note: "Under the answer: the model, its speed, Copy and Write again.",
    render: () => <Sample messages={[QUESTION, message("a", "assistant", FULL)]} />,
  },
  {
    name: "Chat, writing",
    note: "The words grow; half-written bold is closed for the moment. The button stops the answer.",
    render: () => (
      <Sample
        messages={[QUESTION, message("a", "assistant", "", { status: "writing", runId: "r", tokensPerSecond: null })]}
        liveText={HALF}
      />
    ),
  },
  {
    name: "Chat, stopped",
    note: "The words so far stay.",
    render: () => (
      <Sample
        messages={[
          QUESTION,
          message("a", "assistant", "Pack for the cold first:\n\n- Warm coat\n- Two jumpers", { status: "stopped" }),
        ]}
      />
    ),
  },
  {
    name: "Chat, failed",
    note: "What happened and what to do, in the engine's words.",
    render: () => (
      <Sample
        messages={[
          QUESTION,
          message("a", "assistant", "", {
            status: "failed",
            tokensPerSecond: null,
            error: "The model server did not answer. Check that llama-server is running, then try again.",
          }),
        ]}
        height={300}
      />
    ),
  },
  {
    name: "Chat, top bar",
    note: "The chat's title, and whether a model is answering.",
    wide: true,
    render: () => (
      <div className="flex flex-col gap-3">
        <ChatTopBar
          title="Packing list for a week away"
          pill={
            <ModelPill
              model={{
                state: "ready",
                address: "",
                name: "stand-in-model",
                contextTokens: 8192,
                detail: null,
                checkedAt: AT,
              }}
            />
          }
        />
        <ChatTopBar title="New chat" pill={<ModelPill model={null} />} />
      </div>
    ),
  },
];
