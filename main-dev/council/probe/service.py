"""Reliability service (ARCHITECTURE 28.3, 28.5): ledger + behaviour score + activation probe.

1.5, the lie detector as one feature:
- One text layout. Training rows (trainer.py) and live claims (scorer.py) are both the text of
  layout.probe_messages(task, statement). A stored probe carries the layout it was trained on;
  one trained on another layout is never used for a live score:
    store record: "layout" must be trainer.LAYOUT. Records written before 1.5 have no such
      field (they were trained on "<role>: <content>" lines), so they are all retired.
    probe file: its layout_version must be layout.LAYOUT_VERSION. The files are new in 1.5 and
      have only ever held probes of layout.py texts.
- Where a probe lives: the store kv namespace "probes" under the model id (the Probe dump plus
  "layout", "platt" and "card"), and, when the service knows its home, <home>/probes as files
  (probe_files.ProbeFiles). For a model that has probe files the files decide: its active
  version is used, and no active version means the probe is switched off (the API toggle). A
  model with no file is served from the store.
- lie_report cuts every draft into claims, scores them with the model's own probe, adds the
  behaviour score and the track record, and rolls the flags up into a LieReport. It is kept in
  memory and in the store under "lie_reports", and sent as a "lie.report" event.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Optional

from council.core import event_types as ET
from council.core.schemas import BenchTask, CallResult, ClaimScore, Draft, Probe, SeatAssignment
from council.core.schemas_v15 import ClaimSpan, LieReport, ProbeCard
from council.host import ollama_blobs
from council.probe import behaviour, trainer
from council.probe import flags as flags_mod
from council.probe.activations import MockActivationSource, OllamaEmbedSource
from council.probe.claims import claims_from_draft
from council.probe.layout import LAYOUT_VERSION as FILE_LAYOUT
from council.probe.layout import STATEMENT_CLIP
from council.probe.lie_report import build_report
from council.probe.llamacpp_source import LlamaCppActivationSource, pick_layers
from council.probe.probe_files import ProbeFiles
from council.probe.scorer import LiveScorer

NS = "probes"
REPORT_NS = "lie_reports"
LIE_REPORT = getattr(ET, "LIE_REPORT", "lie.report")
DEFAULT_LAYERS = [8, 12, 16, 20]  # used when the config names none and the depth is unknown
WEIGHTS_KEY = "behaviour_weights:"
ANSWER_REF = "answer"
MAX_REPORTS = 200  # lie reports kept in memory; older ones are read back from the store
OLD_LAYOUT_REASON = "trained on an old text layout: train it again"
Platt = tuple[float, float]


def _g(cfg: Any, name: str, default: Any) -> Any:
    if isinstance(cfg, dict):
        return cfg.get(name, default)
    return getattr(cfg, name, default)


def source_kind(source: Any) -> str:
    """The ProbeCard.source name of an activation source."""
    if isinstance(source, LlamaCppActivationSource):
        return "llamacpp"
    if isinstance(source, OllamaEmbedSource):
        return "ollama_embed"
    if source is None or isinstance(source, MockActivationSource):
        return "mock"
    return type(source).__name__


def _platt_of(raw: Any) -> Optional[Platt]:
    try:
        return (float(raw[0]), float(raw[1])) if raw else None
    except (TypeError, ValueError, IndexError, KeyError):
        return None


def probe_record(probe: Probe, platt: Optional[Platt] = None,
                 card: Optional[ProbeCard] = None) -> dict:
    """What goes into the store for one model: the Probe dump plus layout, platt and card."""
    rec = probe.model_dump()
    rec["layout"] = trainer.LAYOUT
    rec["platt"] = [float(platt[0]), float(platt[1])] if platt is not None else None
    rec["card"] = card.model_dump() if card is not None else None
    return rec


def card_from_report(model_id: str, report: dict, source: str = "mock") -> ProbeCard:
    """The card of one trainer.train_from_pairs report. Active is what gate.decide_active said."""
    probe = report.get("probe") or {}
    best = report.get("best_layer")
    row = next((r for r in report.get("layers", []) if r.get("layer") == best), {})
    reasons = [str(r) for r in report.get("reasons", [])]
    return ProbeCard(
        model_id=model_id, source=source, layers=[int(best)] if best is not None else [],
        auroc=report.get("auroc"), accuracy=report.get("accuracy"),
        control_auroc=report.get("shuffled_auroc"), baseline_auroc=report.get("cheap_auroc"),
        ece=report.get("ece"), n_train=int(probe.get("n_train", 0) or 0),
        n_test=int(row.get("n_test", 0) or 0), trained_at=float(report.get("trained_at") or 0.0),
        active=bool(report.get("active", report.get("status") == "validated")),
        reason="; ".join(reasons) or str(report.get("gate_reason") or report.get("status", "")))


def card_from_probe(probe: Probe, source: str = "mock") -> ProbeCard:
    """The card of a probe that has no report (trained from benchmark tasks, or an old record)."""
    active = probe.status == "validated"
    return ProbeCard(
        model_id=probe.model_id, source=source, layers=[probe.layer] if probe.weights else [],
        auroc=probe.auroc if probe.weights else None, n_train=probe.n_train,
        trained_at=float(probe.trained_at or 0.0), active=active,
        reason=f"auroc {probe.auroc:.2f} held out, no control" if active else f"status {probe.status}")


def persist(store: Any, files: Optional[ProbeFiles], probe: Probe, card: ProbeCard,
            platt: Optional[Platt] = None) -> ProbeCard:
    """Save one trained probe to the files (when there are any) and to the store. Returns the
    card as saved (the files give it its version). A file error never loses the store copy."""
    if files is not None:
        try:
            card = files.save(card, [probe], platt, layout_version=FILE_LAYOUT)
        except Exception:
            pass
    store.kv_put(NS, probe.model_id or card.model_id, probe_record(probe, platt, card))
    return card


def persist_report(store: Any, files: Optional[ProbeFiles], model_id: str, report: dict,
                   source: str = "mock") -> ProbeCard:
    """persist() for a trainer.train_from_pairs report."""
    probe = Probe.model_validate(report["probe"])
    if not probe.model_id:
        probe = probe.model_copy(update={"model_id": model_id})
    return persist(store, files, probe, card_from_report(model_id, report, source),
                   _platt_of(report.get("platt")))


class ReliabilityService:
    def __init__(self, ledger, store, source, cfg, emit: Callable[[str, dict], None],
                 home: Optional[Path] = None, lie_cfg: Any = None,
                 files: Optional[ProbeFiles] = None) -> None:
        self.ledger = ledger
        self.store = store
        self.source = source
        self.cfg = cfg  # the [probe] section
        self.emit = emit
        self.files = files if files is not None else (ProbeFiles(Path(home)) if home else None)
        self.lie_cfg = lie_cfg if lie_cfg is not None else _g(cfg, "lie", None)  # the [lie] section
        self._weights: dict[str, dict] = {}
        self._reports: dict[str, LieReport] = {}  # shared by the per-run copies of the service

    # ------------------------------------------------------------------ probes

    def get_probe(self, model_id: str) -> Optional[Probe]:
        """The probe in the store, whatever its layout. Live scoring uses active_probes."""
        raw = self.store.kv_get(NS, model_id)
        if not raw:
            return None
        try:
            return Probe.model_validate(raw)
        except Exception:
            return None

    def _from_files(self, model_id: str) -> Optional[tuple[list[Probe], Optional[Platt]]]:
        """None: this model has no probe file, ask the store. ([], None): it has files and
        none is usable (switched off, another layout, not validated)."""
        if self.files is None:
            return None
        try:
            if not any(c.model_id == model_id for c in self.files.cards()):
                return None
            got = self.files.load(model_id)
            if got is None or self.files.layout_version(model_id) != FILE_LAYOUT:
                return [], None
        except Exception:
            return None
        probes = [p for p in got[1] if p.status == "validated" and p.weights]
        return (probes, got[2]) if probes else ([], None)

    def _from_store(self, model_id: str) -> Optional[tuple[list[Probe], Optional[Platt]]]:
        try:
            raw = self.store.kv_get(NS, model_id)
            if not isinstance(raw, dict) or raw.get("layout") != trainer.LAYOUT:
                return None
            probe = Probe.model_validate(raw)
        except Exception:
            return None
        if probe.status != "validated" or not probe.weights:
            return None
        return [probe], _platt_of(raw.get("platt"))

    def _active(self, model_id: str) -> tuple[list[Probe], Optional[Platt]]:
        found = self._from_files(model_id)
        if found is None:
            found = self._from_store(model_id)
        return found or ([], None)

    def active_probes(self, model_id: str) -> list[Probe]:
        """Validated probes of the current text layout. See the module text for files and store."""
        return self._active(model_id)[0]

    def platt_for(self, model_id: str) -> Optional[Platt]:
        return self._active(model_id)[1]

    def probe_state(self, model_id: str) -> str:
        """"active": a validated probe of the current layout scores this model. "untrusted":
        a probe exists and is not used (failed its control, switched off, old layout).
        "none": nothing was ever trained for it. Never raises."""
        try:
            if self.active_probes(model_id):
                return "active"
        except Exception:
            pass
        try:
            if self.files is not None and any(c.model_id == model_id for c in self.files.cards()):
                return "untrusted"
        except Exception:
            pass
        try:
            if self.store.kv_get(NS, model_id):
                return "untrusted"
        except Exception:
            pass
        return "none"

    def cards(self) -> list[ProbeCard]:
        """One card per model that has a probe, for the API. Never raises."""
        try:
            return self._cards()
        except Exception:
            return []

    def _cards(self) -> list[ProbeCard]:
        old = {"active": False, "reason": OLD_LAYOUT_REASON}
        out: dict[str, ProbeCard] = {}
        if self.files is not None:  # the newest version of each model, with its on/off state
            for card in self.files.cards():
                ok = self.files.layout_version(card.model_id, card.version) == FILE_LAYOUT
                out[card.model_id] = card if ok else card.model_copy(update=old)
        for key, raw in (self.store.kv_list(NS) or {}).items():
            if key.startswith(WEIGHTS_KEY) or not isinstance(raw, dict) or key in out:
                continue
            try:
                card = (ProbeCard.model_validate(raw["card"]) if raw.get("card")
                        else card_from_probe(Probe.model_validate(raw), source_kind(self.source)))
            except Exception:
                continue
            card = card.model_copy(update={"model_id": key})
            out[key] = card if raw.get("layout") == trainer.LAYOUT else card.model_copy(update=old)
        return [out[model_id] for model_id in sorted(out)]

    async def layers_for(self, model_id: str) -> list[int]:
        """The layers to train on for this model.

        An embedding source has one pseudo-layer, whatever the config says. A source that knows
        the model depth (it has info()) gets the configured layers the model really has, or,
        when the config names none (or none exist), layers picked from the depth. Any other
        source gets the configured layers, or DEFAULT_LAYERS when the config names none."""
        pseudo = getattr(self.source, "PSEUDO_LAYER", None)
        if pseudo is not None:
            return [pseudo]
        layers = [int(l) for l in (_g(self.cfg, "layers", DEFAULT_LAYERS) or [])]
        info = getattr(self.source, "info", None)
        if callable(info):
            n_layer = int((await info(model_id)).get("n_layer", 0))
            if n_layer > 0:
                layers = [l for l in layers if 0 <= l < n_layer]
                return layers or pick_layers(n_layer)
        return layers or list(DEFAULT_LAYERS)

    async def _release(self) -> None:
        """Let a source that holds a model in memory (llamacpp) give it back."""
        close = getattr(self.source, "close", None)
        if callable(close):
            try:
                await close()
            except Exception:
                pass

    def _trained(self, probe: Probe, layers_tried: list[int], by_layer: dict, t0: float,
                 card: ProbeCard) -> None:
        top = [d for d, _ in trainer.attribution(probe)] if probe.weights else []
        self.emit("probe.trained", {
            "probe": probe.model_dump(), "model_id": probe.model_id,
            "validated": probe.status == "validated", "layers_tried": layers_tried,
            "auroc_by_layer": by_layer, "top_dims": top,
            "ms": (time.monotonic() - t0) * 1000.0, "card": card.model_dump(),
        })

    async def train_for(self, model_id: str, tasks: list[BenchTask], now: float) -> Probe:
        """Train from benchmark tasks (right answer against a wrong one, same layout)."""
        if self.source is None:
            raise ValueError("no activation source")
        t0 = time.monotonic()
        min_auroc = float(_g(self.cfg, "min_auroc", 0.80))
        min_gate = int(_g(self.cfg, "min_gate_per_class", trainer.MIN_GATE_PER_CLASS))
        try:
            layers = await self.layers_for(model_id)
            data = await trainer.bootstrap_dataset(self.source, model_id, tasks, layers)
        finally:
            await self._release()
        probe, picked = trainer.evaluate(model_id, data, min_auroc, now, 0, min_gate)
        layers_tried = sorted(picked)
        by_layer = {str(l): picked[l] for l in layers_tried}  # the AUROC that picked the layer
        card = persist(self.store, self.files, probe,
                       card_from_probe(probe, source_kind(self.source)))
        self._trained(probe, layers_tried, by_layer, t0, card)
        return probe

    async def train_statements(self, model_id: str, now: Optional[float] = None, seed: int = 0,
                               n: int = trainer.BUILTIN_PAIRS) -> ProbeCard:
        """Train from the built-in statement pairs (dataset.py plus truth_set.py), with the
        shuffled-label control, the surface-feature baseline, the gate and Platt calibration."""
        if self.source is None:
            raise ValueError("no activation source")
        t0 = time.monotonic()
        now = time.time() if now is None else now
        try:
            layers = await self.layers_for(model_id)
            report = await trainer.train_from_pairs(
                self.source, model_id, trainer.builtin_pairs(seed, n), layers,
                float(_g(self.cfg, "min_auroc", 0.80)), now, seed)
        finally:
            await self._release()
        card = persist_report(self.store, self.files, model_id, report, source_kind(self.source))
        rows = report.get("layers", [])
        self._trained(Probe.model_validate(report["probe"]), sorted(r["layer"] for r in rows),
                      {str(r["layer"]): r["select_auroc"] for r in rows}, t0, card)
        return card

    # ------------------------------------------------------------------ behaviour

    def _weights_for(self, model_id: str) -> Optional[dict]:
        if model_id in self._weights:
            return self._weights[model_id]
        raw = self.store.kv_get(NS, WEIGHTS_KEY + model_id)
        w = raw.get("weights") if isinstance(raw, dict) else None
        if w:
            self._weights[model_id] = w
        return w or None

    def refit_behaviour(self, model_id: str) -> dict:
        """Refit weights when enough labelled claims exist; else return current weights."""
        min_rows = int(_g(self.cfg, "min_labelled", behaviour.MIN_FIT_ROWS))
        recs = self.ledger.labelled(model_id)
        if len(recs) < min_rows:
            return self._weights_for(model_id) or dict(behaviour.DEFAULT_WEIGHTS)
        rows = []
        for r in recs:
            sig = behaviour.signals_from(None, None, None, None)
            sig = sig.model_copy(update={"stated_confidence": max(0.0, min(1.0, r.confidence))})
            rows.append((sig, 1 if r.label == "true" else 0))
        # fit uses behaviour.MIN_FIT_ROWS internally; pad nothing, caller threshold >= it in practice
        w = behaviour.fit_weights(rows)
        self._weights[model_id] = w
        self.store.kv_put(NS, WEIGHTS_KEY + model_id, {"weights": w, "n": len(rows)})
        return w

    def _behaviour(self, model_id: str, draft: Optional[Draft],
                   result: Optional[CallResult]) -> tuple[float, Optional[float]]:
        """(behaviour reliability, track record). The track record is None with no labelled claim."""
        try:
            track = self.ledger.track_record(model_id)
        except Exception:
            track = None
        sig = behaviour.signals_from(result, draft, None, track)
        rel = behaviour.reliability(sig, self._weights_for(model_id))
        has_track = track is not None and (float(track[0]) + float(track[1])) > 0
        return rel, (sig.track_record if has_track else None)

    # ------------------------------------------------------------------ lie report

    async def lie_report(self, run_id: str, task: str, seats: list[SeatAssignment],
                         drafts: dict[int, Draft], stated_confidence: Any = None) -> LieReport:
        """Every claim of every draft, scored and flagged. Never raises.

        stated_confidence: {seat_no: 0..1}, one number for all seats, or None (then the
        confidence of each draft). With no active probe the report still comes, from the
        behaviour signals, and its note says so."""
        try:
            try:
                report = await self._lie_report(run_id, task, seats, drafts, stated_confidence, {})
            finally:
                await self._release()
        except Exception as e:
            report = LieReport(run_id=str(run_id), note=f"lie report failed: {type(e).__name__}")
        self._publish(report)
        return report

    def _thresholds(self) -> dict[str, float]:
        out = {}
        for key, default in flags_mod.DEFAULT_THRESHOLDS.items():
            try:
                out[key] = float(_g(self.lie_cfg, key, default))
            except (TypeError, ValueError):
                out[key] = default
        return out

    @staticmethod
    def _stated(stated: Any, seat_no: int, draft: Any) -> Optional[float]:
        value = stated
        if isinstance(stated, dict):
            value = stated.get(seat_no, stated.get(str(seat_no)))
        if value is None:
            value = getattr(draft, "confidence", None)
        try:
            return max(0.0, min(1.0, float(value))) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _claims(draft: Any) -> list[ClaimSpan]:
        """The claims of a draft. An answer with no claim to cut out is one claim itself."""
        claims = claims_from_draft(draft)
        if claims:
            return claims
        answer = str(getattr(draft, "answer", "") or "").strip()
        if not answer:
            return []
        text = answer[:STATEMENT_CLIP]
        return [ClaimSpan(claim_id=ANSWER_REF, text=text, start=0, end=len(text))]

    async def _lie_report(self, run_id: str, task: str, seats: list[SeatAssignment],
                          drafts: dict[int, Draft], stated_confidence: Any,
                          known: dict[int, tuple[float, Optional[float]]]) -> LieReport:
        """`known` holds (behaviour, track record) of seats the caller already worked out."""
        ordered = sorted(seats, key=lambda s: s.seat_no)
        claims: dict[int, list[ClaimSpan]] = {}
        for seat in ordered:
            draft = drafts.get(seat.seat_no)
            if draft is not None:
                claims[seat.seat_no] = self._claims(draft)

        on = bool(_g(self.lie_cfg, "enabled", True)) and self.source is not None
        with_probe = {s.model_id for s in ordered
                      if on and claims.get(s.seat_no) and self.active_probes(s.model_id)}
        scores: dict[int, dict[str, Optional[float]]] = {}
        if with_probe:
            scorer = LiveScorer(
                self.source, self.active_probes, platt_for=self.platt_for,
                timeout_s=float(_g(self.lie_cfg, "timeout_s", 20.0)),
                max_claims=int(_g(self.lie_cfg, "max_claims", 8)))
            scores = await scorer.score_seats(str(task or ""), {
                s.seat_no: (s.model_id, claims[s.seat_no]) for s in ordered
                if s.model_id in with_probe and claims.get(s.seat_no)})

        thresholds = self._thresholds()
        flags = []
        for seat in ordered:
            draft = drafts.get(seat.seat_no)
            if draft is None:
                continue
            rel, track = known.get(seat.seat_no) or self._behaviour(seat.model_id, draft, None)
            stated = self._stated(stated_confidence, seat.seat_no, draft)
            mine = scores.get(seat.seat_no) or {}
            for claim in claims[seat.seat_no]:
                flags.append(flags_mod.make_flag(
                    str(run_id), seat.seat_no, seat.model_id, claim, mine.get(claim.claim_id),
                    rel, track, stated, thresholds))
        return build_report(str(run_id), flags, [(s.seat_no, s.model_id) for s in ordered],
                            sorted(with_probe))

    def _publish(self, report: LieReport) -> None:
        """Keep the report (memory and store) and send the event. Nothing here may raise."""
        data = report.model_dump(mode="json")
        self._reports[report.run_id] = report
        while len(self._reports) > MAX_REPORTS:
            self._reports.pop(next(iter(self._reports)))
        try:
            self.store.kv_put(REPORT_NS, report.run_id, data)
        except Exception:
            pass
        try:
            self.emit(LIE_REPORT, {
                "report": data,
                "flagged": sum(1 for f in report.flags if f.level == "flag"),
                "watched": sum(1 for f in report.flags if f.level == "watch"),
            })
        except Exception:
            pass

    def last_report(self, run_id: str) -> Optional[LieReport]:
        """The lie report of a run: from memory, else from the store, else None."""
        found = self._reports.get(run_id)
        if found is not None:
            return found
        try:
            raw = self.store.kv_get(REPORT_NS, run_id)
            return LieReport.model_validate(raw) if raw else None
        except Exception:
            return None

    # ------------------------------------------------------------------ scoring

    async def score_round0(self, run_id: str, project: str, seats: list[SeatAssignment],
                           drafts: dict[int, Draft], results: dict[int, CallResult],
                           messages_for: Optional[Callable[[int], list[dict]]] = None,
                           task: Optional[str] = None) -> list[ClaimScore]:
        """ClaimScore rows for the deliberation, and the lie report of the round as a side effect.

        The probe text is layout.probe_messages(task, claim): `messages_for` is only read for
        the task (the first user message) when `task` is not given."""
        try:
            return await self._score_round0(run_id, project, seats, drafts, results,
                                            messages_for, task)
        finally:
            await self._release()

    @staticmethod
    def _task_of(messages_for: Optional[Callable[[int], list[dict]]],
                 seats: list[SeatAssignment]) -> str:
        if messages_for is None:
            return ""
        for seat in seats:
            try:
                for m in messages_for(seat.seat_no) or []:
                    if m.get("role") == "user" and m.get("content"):
                        return str(m["content"])
            except Exception:
                continue
        return ""

    async def _score_round0(self, run_id: str, project: str, seats: list[SeatAssignment],
                            drafts: dict[int, Draft], results: dict[int, CallResult],
                            messages_for: Optional[Callable[[int], list[dict]]] = None,
                            task: Optional[str] = None) -> list[ClaimScore]:
        ordered = [s for s in sorted(seats, key=lambda s: s.seat_no) if drafts.get(s.seat_no) is not None]
        known: dict[int, tuple[float, Optional[float]]] = {}
        for seat in ordered:
            draft = drafts[seat.seat_no]
            self.ledger.log_draft(run_id, project, seat.model_id, seat.seat_no, draft)
            known[seat.seat_no] = self._behaviour(seat.model_id, draft, results.get(seat.seat_no))

        report: Optional[LieReport] = None
        try:
            text = task if task is not None else self._task_of(messages_for, ordered)
            report = await self._lie_report(run_id, text, ordered, drafts, None, known)
        except Exception:
            report = None  # scores are advisory: the behaviour score below still goes out

        out: list[ClaimScore] = []
        show = bool(_g(self.cfg, "show_to_council", True))
        for seat in ordered:
            draft = drafts[seat.seat_no]
            by_claim = {f.claim_id: f.probe_score for f in (report.flags if report else [])
                        if f.seat_no == seat.seat_no and f.probe_score is not None}
            # ClaimScore.probe reads like reliability: 0 = likely wrong, 1 = likely right.
            whole = by_claim.get(ANSWER_REF)
            if whole is None and by_claim:
                whole = sum(by_claim.values()) / len(by_claim)
            auroc = None
            if by_claim:
                active = self.active_probes(seat.model_id)
                auroc = active[0].auroc if active else None
            seat_scores = []
            for ref in [ANSWER_REF] + [c.id for c in draft.claims]:
                p_score = whole if ref == ANSWER_REF else by_claim.get(ref)
                seat_scores.append(ClaimScore(
                    claim_ref=ref, reliability=known[seat.seat_no][0], probe=p_score,
                    probe_auroc=auroc if p_score is not None else None, seat_no=seat.seat_no))
            out.extend(seat_scores)
            probe_used = self.get_probe(seat.model_id)
            self.emit("probe.scores", {
                "seat_no": seat.seat_no, "model_id": seat.model_id, "round": 0,
                "scores": [s.model_dump() for s in seat_scores],
                "probe_status": probe_used.status if probe_used is not None else None,
                "shown_to_council": show,
            })
        if report is not None:
            self._publish(report)
        return out


def _tag_for(gateway: Any) -> Callable[[str], str]:
    """model id -> Ollama tag, from the gateway (its tag_for, else its registry)."""
    tag_for = getattr(gateway, "tag_for", None)
    if tag_for is not None:
        return tag_for
    reg = getattr(gateway, "registry", None) or {}
    if not isinstance(reg, dict):
        reg = {getattr(e, "id", None): e for e in reg}
    return lambda m: (getattr(reg.get(m), "ollama_tag", None) or m)


def build_source(config: Any, gateway: Any = None):
    """config is the probe section or the whole config. Returns a source or None."""
    cfg = getattr(config, "probe", config)
    if not bool(_g(cfg, "enabled", True)):
        return None
    kind = str(_g(cfg, "source", "mock")).lower()
    if kind == "mock":
        return MockActivationSource()
    if kind == "ollama_embed":
        client = None
        for name in ("ollama_client", "client", "ollama"):
            c = getattr(gateway, name, None)
            if c is not None and hasattr(c, "embed"):
                client = c
                break
        if client is None:
            return None
        return OllamaEmbedSource(client, _tag_for(gateway))
    if kind == "llamacpp":
        # Nothing is started or checked here: the tool runs on first use, and a missing binary
        # or model is an ActivationError then.
        tag_for = _tag_for(gateway)
        raw_dir = str(_g(cfg, "ollama_models_dir", "") or "").strip()
        models_dir = Path(raw_dir).expanduser() if raw_dir else ollama_blobs.default_models_dir()
        binary = Path(str(_g(cfg, "actdump_path", "~/council/tap-build/actdump"))).expanduser()
        return LlamaCppActivationSource(
            binary, lambda m: ollama_blobs.blob_for_tag(tag_for(m), models_dir),
            pool=str(_g(cfg, "pool", "last") or "last"),
            max_models=int(_g(cfg, "max_models", 1) or 1))
    return None
