"""Chat storage for the partner UI. Lives in the store's kv table.

Namespaces: "ui_chats" (one document per chat, key = chat id) and "ui_settings" (key "settings").
Every dict that leaves this module uses the UI's camelCase names (ui_partner/ui/src/engine/contract.ts).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

CHATS = "ui_chats"
SETTINGS = "ui_settings"
SETTINGS_KEY = "settings"
UNTITLED = "New chat"
TITLE_CHARS = 48
PREVIEW_CHARS = 80
MATCH_CHARS = 120

DEFAULTS: dict[str, Any] = {
    "modelAddress": "http://127.0.0.1:8080",
    "maxAnswerTokens": 1024,
    "systemPrompt": (
        "You are a careful assistant running on the owner's own computer. "
        "Answer plainly and briefly. If you are not sure, say so."
    ),
}

MESSAGE_FIELDS = ("text", "status", "error", "model", "tokensPerSecond", "answerTokens", "runId")
_SNAKE = {"tokens_per_second": "tokensPerSecond", "answer_tokens": "answerTokens", "run_id": "runId"}


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
    else:
        dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _one_line(text: str) -> str:
    return " ".join((text or "").split())


class UiChats:
    def __init__(self, store: Any, now: Callable[[], Any] = time.time):
        self._store = store
        self._now = now
        self._lock = threading.RLock()

    # ------------------------------------------------------------ internals

    def _stamp(self) -> str:
        return _iso(self._now())

    def _load(self, chat_id: str) -> Optional[dict]:
        if not chat_id:
            return None
        return self._store.kv_get(CHATS, chat_id)

    def _save(self, doc: dict) -> None:
        self._store.kv_put(CHATS, doc["id"], doc)

    @staticmethod
    def _chat(doc: dict) -> dict:
        return {
            "id": doc["id"],
            "title": doc["title"],
            "pinned": bool(doc.get("pinned", False)),
            "createdAt": doc["createdAt"],
            "updatedAt": doc["updatedAt"],
            "messageCount": len(doc.get("messages", [])),
            "messages": [dict(m) for m in doc.get("messages", [])],
        }

    @staticmethod
    def _summary(doc: dict, match: Optional[str] = None) -> dict:
        msgs = doc.get("messages", [])
        preview = _one_line(msgs[-1]["text"])[:PREVIEW_CHARS] if msgs else ""
        return {
            "id": doc["id"],
            "title": doc["title"],
            "pinned": bool(doc.get("pinned", False)),
            "createdAt": doc["createdAt"],
            "updatedAt": doc["updatedAt"],
            "messageCount": len(msgs),
            "preview": preview,
            "match": match,
        }

    @staticmethod
    def _passage(text: str, query: str) -> Optional[str]:
        flat = _one_line(text)
        at = flat.lower().find(query.lower())
        if at < 0:
            return None
        start = max(0, at - (MATCH_CHARS - len(query)) // 2)
        start = min(start, max(0, len(flat) - MATCH_CHARS))
        return flat[start:start + MATCH_CHARS]

    # ------------------------------------------------------------ chats

    def create(self, title: Optional[str] = None) -> dict:
        with self._lock:
            ts = self._stamp()
            clean = (title or "").strip()
            doc = {
                "id": uuid.uuid4().hex,
                "title": clean or UNTITLED,
                "untitled": not clean,
                "pinned": False,
                "createdAt": ts,
                "updatedAt": ts,
                "messages": [],
            }
            self._save(doc)
            return self._chat(doc)

    def get(self, id: str) -> Optional[dict]:
        doc = self._load(id)
        return self._chat(doc) if doc else None

    def summary(self, id: str) -> Optional[dict]:
        doc = self._load(id)
        return self._summary(doc) if doc else None

    def list(self, query: Optional[str] = None) -> list[dict]:
        docs = list(self._store.kv_list(CHATS).values())
        docs.sort(key=lambda d: (d.get("updatedAt", ""), d.get("createdAt", "")), reverse=True)
        q = (query or "").strip()
        if not q:
            return [self._summary(d) for d in docs]
        out = []
        for d in docs:
            hit = self._passage(d.get("title", ""), q)
            if hit is None:
                for m in reversed(d.get("messages", [])):
                    hit = self._passage(m.get("text", ""), q)
                    if hit is not None:
                        break
            if hit is not None:
                out.append(self._summary(d, match=hit))
        return out

    def update(self, id: str, title: Optional[str] = None, pinned: Optional[bool] = None) -> Optional[dict]:
        with self._lock:
            doc = self._load(id)
            if doc is None:
                return None
            if title is not None and title.strip():
                doc["title"] = title.strip()
                doc["untitled"] = False
            if pinned is not None:
                doc["pinned"] = bool(pinned)
            doc["updatedAt"] = self._stamp()
            self._save(doc)
            return self._chat(doc)

    def delete(self, id: str) -> bool:
        with self._lock:
            if self._load(id) is None:
                return False
            self._store.kv_delete(CHATS, id)
            return True

    # ------------------------------------------------------------ messages

    def add_message(
        self, chat_id: str, role: str, text: str, status: str = "complete",
        run_id: Optional[str] = None, model: Optional[str] = None,
    ) -> dict:
        with self._lock:
            doc = self._load(chat_id)
            if doc is None:
                raise KeyError(f"no chat {chat_id}")
            ts = self._stamp()
            msg = {
                "id": uuid.uuid4().hex,
                "chatId": chat_id,
                "role": role,
                "text": text or "",
                "status": status,
                "createdAt": ts,
                "model": model,
                "tokensPerSecond": None,
                "answerTokens": None,
                "error": None,
                "runId": run_id,
            }
            doc["messages"].append(msg)
            if doc.get("untitled") and role == "user":
                named = _one_line(text)[:TITLE_CHARS]
                if named:
                    doc["title"] = named
                    doc["untitled"] = False
            doc["updatedAt"] = ts
            self._save(doc)
            return dict(msg)

    def set_message(self, chat_id: str, message_id: str, **fields: Any) -> Optional[dict]:
        with self._lock:
            doc = self._load(chat_id)
            if doc is None:
                return None
            for msg in doc["messages"]:
                if msg["id"] == message_id:
                    for name, value in fields.items():
                        name = _SNAKE.get(name, name)
                        if name not in MESSAGE_FIELDS:
                            raise ValueError(f"unknown message field: {name}")
                        msg[name] = value
                    doc["updatedAt"] = self._stamp()
                    self._save(doc)
                    return dict(msg)
            return None

    def last_user_message(self, chat_id: str) -> Optional[dict]:
        doc = self._load(chat_id)
        if doc is None:
            return None
        for msg in reversed(doc["messages"]):
            if msg["role"] == "user":
                return dict(msg)
        return None

    def remove_last_assistant(self, chat_id: str) -> None:
        """Drop the newest assistant message when it is the last message of the chat."""
        with self._lock:
            doc = self._load(chat_id)
            if doc is None or not doc["messages"]:
                return
            if doc["messages"][-1]["role"] != "assistant":
                return
            doc["messages"].pop()
            doc["updatedAt"] = self._stamp()
            self._save(doc)

    def history_block(self, chat_id: str, max_messages: int = 6, clip: int = 600) -> str:
        """Earlier turns as text for the council task. Empty string when there are none."""
        doc = self._load(chat_id)
        if doc is None:
            return ""
        msgs = [m for m in doc["messages"] if (m.get("text") or "").strip() and m.get("status") != "writing"]
        msgs = msgs[-max_messages:] if max_messages > 0 else []
        if not msgs:
            return ""
        lines = ["Conversation so far:"]
        for m in msgs:
            who = "User" if m["role"] == "user" else "Council"
            text = m["text"].strip()
            if len(text) > clip:
                text = text[:clip] + "..."
            lines.append(f"{who}: {text}")
        return "\n".join(lines)

    # ------------------------------------------------------------ export

    def export(self, chat_id: str, fmt: str = "markdown") -> Optional[dict]:
        doc = self._load(chat_id)
        if doc is None:
            return None
        chat = self._chat(doc)
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in chat["title"]).strip("-")[:60]
        safe = safe or "chat"
        if fmt == "json":
            return {
                "filename": f"{safe}.json",
                "mime": "application/json",
                "text": json.dumps(chat, ensure_ascii=False, indent=2),
            }
        if fmt != "markdown":
            raise ValueError(f"unknown export format: {fmt}")
        parts = [f"# {chat['title']}"]
        for m in chat["messages"]:
            who = "You" if m["role"] == "user" else "Council"
            parts.append(f"**{who}:** {m['text']}")
        return {"filename": f"{safe}.md", "mime": "text/markdown", "text": "\n\n".join(parts) + "\n"}

    # ------------------------------------------------------------ settings

    def _settings_doc(self) -> dict:
        return self._store.kv_get(SETTINGS, SETTINGS_KEY) or {}

    def settings(self) -> dict:
        doc = self._settings_doc()
        return {
            "modelAddress": doc.get("modelAddress", DEFAULTS["modelAddress"]),
            "hasModelKey": bool(doc.get("modelKey")),
            "systemPrompt": doc.get("systemPrompt", DEFAULTS["systemPrompt"]),
            "maxAnswerTokens": int(doc.get("maxAnswerTokens", DEFAULTS["maxAnswerTokens"])),
        }

    def update_settings(self, **update: Any) -> dict:
        with self._lock:
            doc = self._settings_doc()
            for name in ("modelAddress", "modelKey", "systemPrompt", "maxAnswerTokens"):
                value = update.get(name)
                if value is None:
                    continue
                doc[name] = int(value) if name == "maxAnswerTokens" else str(value)
            self._store.kv_put(SETTINGS, SETTINGS_KEY, doc)
            return self.settings()


__all__ = ["UiChats", "DEFAULTS"]
