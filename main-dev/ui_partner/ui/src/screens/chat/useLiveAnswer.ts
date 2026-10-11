// The answer that is being written right now. The words arrive a few at a time from
// engine.streamRun and are kept here, in the screen's own state, until the run ends; then the
// saved message replaces them in the chat. Leaving the screen stops the listening, not the run.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { Chat, Message, RunEvent } from "../../engine/client";
import { useEngine } from "../../engine/EngineProvider";
import { chatKeys } from "./keys";

export interface LiveAnswer {
  runId: string;
  /** every word that has arrived so far */
  text: string;
}

/** The chat with one of its messages swapped for a newer copy of it. */
export function withMessage(chat: Chat, message: Message): Chat {
  return { ...chat, messages: chat.messages.map((m) => (m.id === message.id ? message : m)) };
}

export function useLiveAnswer(chatId: string | undefined, runId: string | null): LiveAnswer | null {
  const engine = useEngine();
  const queries = useQueryClient();
  const [live, setLive] = useState<LiveAnswer | null>(null);

  useEffect(() => {
    if (!chatId || !runId) return;
    const leave = new AbortController();
    // the engine hands over the run from its first word, so the text always starts empty
    let text = "";
    setLive({ runId, text });
    const onEvent = (event: RunEvent) => {
      if (leave.signal.aborted) return;
      if (event.type === "delta") {
        text += event.text;
        setLive({ runId, text });
        return;
      }
      if (event.type === "run.done" || event.type === "run.error") {
        queries.setQueryData<Chat>(chatKeys.chat(chatId), (chat) => chat && withMessage(chat, event.message));
        void queries.invalidateQueries({ queryKey: chatKeys.lists });
        // a failed answer is news about the model: ask again whether it is there
        if (event.type === "run.error") void queries.invalidateQueries({ queryKey: chatKeys.health });
      }
    };
    engine.streamRun(runId, onEvent, leave.signal).catch(() => {
      // the run can no longer be followed: read the chat again and show what was saved
      if (!leave.signal.aborted) void queries.invalidateQueries({ queryKey: chatKeys.chat(chatId) });
    });
    return () => leave.abort();
  }, [engine, queries, chatId, runId]);

  return live && live.runId === runId ? live : null;
}
