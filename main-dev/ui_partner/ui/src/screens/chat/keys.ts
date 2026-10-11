// The names React Query keeps the chat data under. Any screen that changes a chat
// invalidates these, so every list and every open chat shows the change.
export const chatKeys = {
  /** is a model answering */
  health: ["health"] as const,
  /** every list of chats (History, search) */
  lists: ["chats"] as const,
  /** one chat with its messages */
  chat: (id: string) => ["chat", id] as const,
};
