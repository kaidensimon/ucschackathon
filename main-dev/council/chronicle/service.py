"""Chronicle service (spec 15.6, 15.7): recall for a task, list, user edit, delete, export.

The store is any object with chronicle_list(), chronicle_put(entry), chronicle_delete(id).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from council.chronicle import recall
from council.core.schemas import ChronicleEntry, EvidenceRef
from council.core.workspace import project_id

KIND_ORDER = ("preference", "project_fact", "precedent", "lesson", "open_question")
_USER_RUN = "user"


class Chronicle:
    def __init__(
        self,
        store: Any,
        embed: Callable[[list[str]], Awaitable[list[list[float]]]],
        cfg: Any = None,
    ) -> None:
        self.store = store
        self.embed = embed
        self.cfg = cfg

    def _recall_k(self) -> int:
        return int(getattr(self.cfg, "recall_k", 8) or 8)

    async def record_for(
        self, task: str, workspace: str | Path, categories: list[str]
    ) -> tuple[str, list[ChronicleEntry]]:
        project = project_id(workspace)
        try:
            vectors = await self.embed([task])
            query = list(vectors[0]) if vectors else []
        except Exception:
            query = []
        entries = self.store.chronicle_list()
        if query and any(query):
            top = recall.rank(entries, query, project, list(categories), k=self._recall_k())
        else:  # no embedding model: match on words instead of returning nothing
            top = recall.rank_text(entries, task, project, list(categories), k=self._recall_k())
        return recall.render_record(top), top

    def list(self, project: str | None = None) -> list[ChronicleEntry]:
        entries = self.store.chronicle_list()
        if project is None:
            return list(entries)
        return [
            e for e in entries
            if not e.scope.startswith("project:") or e.scope == f"project:{project}"
        ]

    def user_edit(self, entry_id: str, patch: dict, now: float) -> ChronicleEntry | None:
        entry = next((e for e in self.store.chronicle_list() if e.id == entry_id), None)
        if entry is None:
            return None
        patch = dict(patch)
        patch.pop("id", None)
        pin = bool(patch.pop("pin", False))
        demote = bool(patch.pop("demote", False))
        data = entry.model_dump(mode="json")
        data.update(patch)
        if pin:
            data["status"] = "active"
            data["confidence"] = 1.0
        elif demote:
            data["status"] = "provisional"
        elif "status" not in patch:
            data["status"] = "active"
        quote = json.dumps(
            {k: v for k, v in patch.items()} | ({"pin": True} if pin else {}) | ({"demote": True} if demote else {}),
            sort_keys=True, default=str,
        )
        evidence = list(data.get("evidence") or [])
        evidence.append(EvidenceRef(run_id=_USER_RUN, quote=f"user edit: {quote}").model_dump(mode="json"))
        data["evidence"] = evidence
        data["last_confirmed_at"] = now
        new = ChronicleEntry.model_validate(data)
        self.store.chronicle_put(new)
        return new

    def delete(self, entry_id: str) -> bool:
        if not any(e.id == entry_id for e in self.store.chronicle_list()):
            return False
        self.store.chronicle_delete(entry_id)
        return True

    def export_markdown(self, project: str | None = None) -> str:
        entries = self.list(project)
        lines = ["# Chronicle", ""]
        if not entries:
            lines.append("(no entries)")
            return "\n".join(lines) + "\n"
        kinds = list(KIND_ORDER) + sorted({e.kind for e in entries} - set(KIND_ORDER))
        for kind in kinds:
            group = [e for e in entries if e.kind == kind]
            if not group:
                continue
            lines.append(f"## {kind}")
            lines.append("")
            for e in group:
                lines.append(f"- [{e.status} {e.confidence:.2f}] {e.statement} ({e.id}, {e.scope})")
                if e.rationale:
                    lines.append(f"  - why: {e.rationale}")
                for ev in e.evidence:
                    if ev.quote:
                        lines.append(f"  - evidence ({ev.run_id}): {ev.quote}")
            lines.append("")
        return "\n".join(lines)
