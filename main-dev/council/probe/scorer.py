"""The live lie-detector call: read a model's activations for each claim, score with its probes.

Score direction
- trainer.score gives P(lie). Everything here returns the 1.5 reading: 0 = likely false,
  1 = likely true. So a layer score is 1 - P(lie).
- Several probes (layers) for one model: the layer scores are averaged (mean of probabilities).
- Platt (a, b), when given, is applied to the averaged score s: sigmoid(a * s + b).

Text layout
- The default text is one user message
      "Question: <task>\nStatement: <statement>\nThe statement above is"
  built by council/probe/layout.py probe_messages (task squeezed and clipped to 600, statement
  clipped to 400). A probe must be scored on text laid out the way it was trained.

Only probes with status "validated" count. A model with none gets {} and no capture is made.
One capture per claim, one claim at a time for one model: the source holds one process per
model. Nothing here raises: a claim that fails or times out scores None.

Readings (read_one, read_many): one statement per member, with the reason when there is no
score ("no_probe", "timeout", "error"). timeout_s bounds each member's OWN load + capture: the
clock of a member starts when its capture starts, never while it waits for another member.
A source that holds one model at a time (max_models 1, or unknown) gets one capture at a time,
in the order given. The whole batch is bounded by budget_s (default timeout_s * members):
members not reached by then come back "timeout" without a capture.
"""
from __future__ import annotations

import asyncio
import math
from typing import Any, Callable, Optional

from council.core.schemas import Probe
from council.core.schemas_v15 import ClaimSpan
from council.probe.layout import probe_messages
from council.probe.trainer import score as probe_score

Platt = tuple[float, float]
Reading = tuple[Optional[float], str]  # (score 0..1 or None, READ_*)

READ_OK = "ok"
READ_NO_PROBE = "no_probe"  # no validated probe for the model: no capture was made
READ_TIMEOUT = "timeout"  # its own capture took too long, or the batch budget ran out
READ_ERROR = "error"  # the capture or the probe failed


def default_text_for(task: str, statement: str) -> list[dict]:
    """The layout module's text, as one user message. Never build this text anywhere else."""
    return probe_messages(task, statement)


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def apply_platt(s: float, platt: Optional[Platt]) -> float:
    """sigmoid(a * s + b), or s unchanged with no Platt pair."""
    if platt is None:
        return s
    a, b = platt
    return _sigmoid(float(a) * s + float(b))


def truth_score(probes: list[Probe], activations: dict[int, list[float]]) -> Optional[float]:
    """Mean over probes of 1 - P(lie). None when no probe could score. Pure."""
    vals: list[float] = []
    for p in probes:
        lie = probe_score(p, activations)
        if lie is not None and math.isfinite(lie):
            vals.append(1.0 - lie)
    if not vals:
        return None
    return min(1.0, max(0.0, sum(vals) / len(vals)))


class LiveScorer:
    def __init__(
        self,
        source: Any,
        probes_for: Callable[[str], list[Probe]],
        text_for: Callable[[str, str], list[dict]] | None = None,
        platt_for: Callable[[str], Optional[Platt]] | None = None,
        timeout_s: float = 20.0,
        max_claims: int = 8,
    ) -> None:
        self.source = source
        self.probes_for = probes_for
        self.text_for = text_for or default_text_for
        self.platt_for = platt_for
        self.timeout_s = float(timeout_s)
        self.max_claims = max(0, int(max_claims))

    def _probes(self, model_id: str) -> list[Probe]:
        try:
            found = list(self.probes_for(model_id) or [])
        except Exception:
            return []
        return [p for p in found if getattr(p, "status", "") == "validated" and p.weights]

    def _platt(self, model_id: str) -> Optional[Platt]:
        if self.platt_for is None:
            return None
        try:
            pair = self.platt_for(model_id)
            if pair is None:
                return None
            a, b = float(pair[0]), float(pair[1])
            return (a, b) if math.isfinite(a) and math.isfinite(b) else None
        except Exception:
            return None

    async def _one(self, model_id: str, task: str, claim: ClaimSpan, probes: list[Probe],
                   layers: list[int], platt: Optional[Platt]) -> Optional[float]:
        try:
            messages = self.text_for(task, claim.text)
            acts = await asyncio.wait_for(
                self.source.capture(model_id, messages, list(layers)), self.timeout_s)
            s = truth_score(probes, acts)
            if s is None:
                return None
            s = apply_platt(s, platt)
            return s if math.isfinite(s) else None
        except Exception:  # includes asyncio.TimeoutError
            return None

    async def score_claims(
        self, model_id: str, task: str, claims: list[ClaimSpan]
    ) -> dict[str, Optional[float]]:
        """claim_id -> 0..1 (1 = likely true), None when it could not be scored.

        Claims past max_claims are not captured and score None. No validated probe: {}.
        Each claim is bounded by timeout_s, so the call by timeout_s * number of claims.
        """
        try:
            claims = list(claims or [])
            probes = self._probes(model_id)
            if not probes or not claims:
                return {}
            layers = sorted({int(p.layer) for p in probes})
            platt = self._platt(model_id)
            out: dict[str, Optional[float]] = {c.claim_id: None for c in claims}
            for claim in claims[: self.max_claims]:
                out[claim.claim_id] = await self._one(model_id, task, claim, probes, layers, platt)
            return out
        except Exception:
            return {}

    def _room(self) -> int:
        """Captures the source can run at once. Unknown: one."""
        room = getattr(self.source, "max_models", None)
        if isinstance(room, int) and not isinstance(room, bool):
            return max(1, room)
        return 1

    async def read_one(self, model_id: str, task: str, statement: str,
                       timeout_s: Optional[float] = None) -> Reading:
        """One statement of one model: (score, READ_OK) or (None, why). Never raises.

        The capture (model load included) is bounded by the smaller of self.timeout_s and
        timeout_s. A limit of 0 or less makes no capture and answers READ_TIMEOUT."""
        try:
            probes = self._probes(model_id)
            if not probes:
                return None, READ_NO_PROBE
            limit = self.timeout_s if timeout_s is None else min(self.timeout_s, float(timeout_s))
            if not limit > 0:
                return None, READ_TIMEOUT
            layers = sorted({int(p.layer) for p in probes})
            messages = self.text_for(task, statement)
            try:
                acts = await asyncio.wait_for(
                    self.source.capture(model_id, messages, list(layers)), limit)
            except asyncio.TimeoutError:
                return None, READ_TIMEOUT
            s = truth_score(probes, acts)
            if s is None:
                return None, READ_ERROR
            s = apply_platt(s, self._platt(model_id))
            return (s, READ_OK) if math.isfinite(s) else (None, READ_ERROR)
        except Exception:
            return None, READ_ERROR

    async def read_many(
        self, task: str, items: list[tuple[str, str, str]],
        budget_s: Optional[float] = None, clock: Callable[[], float] | None = None,
    ) -> dict[str, Reading]:
        """key -> reading for (key, model_id, statement) items. Never raises.

        Models go in the order they first appear, one model's items together. No more than the
        source's max_models captures run at once (one when it is 1 or unknown). Every item gets
        its own timeout_s; the batch ends by budget_s (default timeout_s * items)."""
        items = [(str(k), str(m), str(t)) for k, m, t in (items or [])]
        out: dict[str, Reading] = {k: (None, READ_TIMEOUT) for k, _m, _t in items}
        if not items:
            return out
        now = clock or asyncio.get_running_loop().time
        budget = self.timeout_s * len(items) if budget_s is None else float(budget_s)
        deadline = now() + max(0.0, budget)
        groups: dict[str, list[tuple[str, str]]] = {}
        for key, model_id, text in items:
            groups.setdefault(model_id, []).append((key, text))

        async def run_model(model_id: str) -> None:
            for key, text in groups[model_id]:
                out[key] = await self.read_one(model_id, task, text, deadline - now())

        room = self._room()
        if room <= 1 or len(groups) <= 1:
            for model_id in groups:
                await run_model(model_id)
            return out
        gate = asyncio.Semaphore(room)

        async def gated(model_id: str) -> None:
            async with gate:  # the wait here is not on the member's own clock
                await run_model(model_id)

        await asyncio.gather(*(gated(m) for m in groups), return_exceptions=True)
        return out

    async def score_seats(
        self, task: str, by_seat: dict[int, tuple[str, list[ClaimSpan]]]
    ) -> dict[int, dict[str, Optional[float]]]:
        """seat_no -> claim scores. Different models run at once, one model's seats in turn."""
        by_model: dict[str, list[int]] = {}
        for seat_no, (model_id, _claims) in by_seat.items():
            by_model.setdefault(model_id, []).append(seat_no)

        async def run_model(model_id: str, seats: list[int]) -> dict[int, dict]:
            done: dict[int, dict[str, Optional[float]]] = {}
            for seat_no in seats:
                done[seat_no] = await self.score_claims(model_id, task, by_seat[seat_no][1])
            return done

        # A source that keeps fewer models loaded than there are here would evict and reload
        # a model on every claim when they run at once: then the models go one after another.
        room = getattr(self.source, "max_models", None)
        if isinstance(room, int) and not isinstance(room, bool) and room < len(by_model):
            parts: list = []
            for m, seats in by_model.items():
                try:
                    parts.append(await run_model(m, seats))
                except Exception as exc:  # noqa: BLE001
                    parts.append(exc)
        else:
            parts = await asyncio.gather(
                *(run_model(m, seats) for m, seats in by_model.items()), return_exceptions=True)
        out: dict[int, dict[str, Optional[float]]] = {seat_no: {} for seat_no in by_seat}
        for part in parts:
            if isinstance(part, dict):
                out.update(part)
        return out


__all__ = ["LiveScorer", "READ_ERROR", "READ_NO_PROBE", "READ_OK", "READ_TIMEOUT", "Reading",
           "apply_platt", "default_text_for", "truth_score"]
