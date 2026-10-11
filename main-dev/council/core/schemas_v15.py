"""Shared types for the 1.5 features: lie detector, speculative decoding, memory plan, solo comparison,
steering vectors.

Frozen contract. Modules import from here; they do not redefine these shapes.
Kept apart from schemas.py so the 1.5 work does not touch the 1.0 contract.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())


# --------------------------------------------------------------------------------------
# Lie detector
# --------------------------------------------------------------------------------------

LieLevel = Literal["ok", "watch", "flag"]


class ClaimSpan(_Model):
    """One checkable statement cut out of a seat's answer."""

    claim_id: str  # "c1", "c2", ... in order of appearance
    text: str
    start: int = 0  # character offsets in the answer text
    end: int = 0


class LieFlag(_Model):
    """What the engine thinks of one claim. Every score reads 0 = likely false, 1 = likely true."""

    run_id: str = ""
    seat_no: int = 0
    model_id: str = ""
    claim_id: str = ""
    text: str = ""
    probe_score: Optional[float] = None  # from the model's own activations; None = no active probe
    behaviour_score: Optional[float] = None  # from behaviour signals (hedging, self-consistency)
    track_record: Optional[float] = None  # share of this model's past labelled claims that were true
    stated_confidence: Optional[float] = None  # what the seat said, 0..1
    bluff_gap: Optional[float] = None  # stated_confidence - probe_score; high = says sure, looks unsure
    level: LieLevel = "ok"
    reasons: list[str] = Field(default_factory=list)


class SeatHonesty(_Model):
    seat_no: int
    model_id: str = ""
    claims: int = 0
    flagged: int = 0
    watched: int = 0
    mean_probe: Optional[float] = None
    mean_gap: Optional[float] = None
    level: LieLevel = "ok"


class LieReport(_Model):
    run_id: str = ""
    seats: list[SeatHonesty] = Field(default_factory=list)
    flags: list[LieFlag] = Field(default_factory=list)  # every scored claim, worst first
    probe_models: list[str] = Field(default_factory=list)  # models that had an active probe
    note: str = ""  # e.g. "no active probe: behaviour signals only"


class ProbeCard(_Model):
    """One trained probe, as shown to the user."""

    model_id: str
    version: int = 1
    source: str = "mock"  # mock | ollama_embed | llamacpp
    layers: list[int] = Field(default_factory=list)
    auroc: Optional[float] = None
    accuracy: Optional[float] = None
    control_auroc: Optional[float] = None  # same probe trained on shuffled labels; should be near 0.5
    baseline_auroc: Optional[float] = None  # surface-feature baseline; the probe must beat it
    ece: Optional[float] = None
    n_train: int = 0
    n_test: int = 0
    trained_at: float = 0.0
    active: bool = False
    reason: str = ""  # why it is or is not active


# --------------------------------------------------------------------------------------
# Speculative decoding
# --------------------------------------------------------------------------------------


class DraftPair(_Model):
    target_id: str  # the seat model
    draft_id: str  # the small model that guesses ahead
    family: str = ""
    size_ratio: float = 0.0  # draft size / target size
    verified: bool = False  # True once measured on the box
    speedup: Optional[float] = None  # measured tokens/s with draft divided by without
    note: str = ""


# --------------------------------------------------------------------------------------
# Memory plan
# --------------------------------------------------------------------------------------


class MeasuredModel(_Model):
    """One row of the on-box model check (tools/box/check_models.py)."""

    model_id: str = ""
    tag: str = ""
    ok: bool = True
    reported_gib: Optional[float] = None  # what Ollama reports
    ram_gib: Optional[float] = None  # real memory taken
    tps: Optional[float] = None  # tokens per second alone
    json_ok: Optional[bool] = None
    think_ok: Optional[bool] = None
    error: str = ""


class MemoryPlan(_Model):
    fits: bool = True
    budget_gib: float = 0.0
    total_gib: float = 0.0
    per_model: dict[str, float] = Field(default_factory=dict)  # model id -> GiB at the chosen context
    num_ctx: dict[str, int] = Field(default_factory=dict)  # model id -> context window
    roles: dict[str, str] = Field(default_factory=dict)  # planner/worker/senior_worker/clerk -> model id
    shared_roles: list[str] = Field(default_factory=list)  # roles given to an already seated model
    dropped: list[str] = Field(default_factory=list)  # models that could not be kept
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Steering vectors (llama.cpp control vectors, one per project and model)
# --------------------------------------------------------------------------------------


class SteerCard(_Model):
    """One trained steering vector, as shown to the user."""

    project: str
    model_id: str
    version: int = 1
    layers: list[int] = Field(default_factory=list)
    scale: Optional[float] = None  # the strength the search chose; None = none passed the sanity check
    examples: int = 0  # contrast pairs it was built from
    fraction: float = 0.0  # vector size as a share of the hidden-state size
    active: bool = False
    reason: str = ""  # why it is or is not active
    trained_at: float = 0.0
    path: str = ""  # the control-vector GGUF


# --------------------------------------------------------------------------------------
# Council against solo models
# --------------------------------------------------------------------------------------


class SoloScore(_Model):
    """One model answering one benchmark task alone."""

    model_id: str
    task_id: str
    correct: Optional[bool] = None
    score: Optional[float] = None  # 0..1 when the grader is not yes/no
    answer: str = ""
    category: str = ""
    latency_s: Optional[float] = None
    tokens_out: Optional[int] = None


class CompareRow(_Model):
    name: str  # a model id, "council", "majority_vote", "oracle", "mean_solo"
    kind: Literal["solo", "council", "baseline"] = "solo"
    n: int = 0
    accuracy: float = 0.0
    by_category: dict[str, float] = Field(default_factory=dict)
    mean_latency_s: Optional[float] = None


class CompareReport(_Model):
    rows: list[CompareRow] = Field(default_factory=list)
    n_tasks: int = 0  # tasks every system answered
    best_solo: str = ""
    council_minus_best: Optional[float] = None  # accuracy difference, in points 0..1
    council_minus_mean: Optional[float] = None
    council_minus_vote: Optional[float] = None  # against a plain majority vote of the same models
    council_only_right: list[str] = Field(default_factory=list)  # task ids
    council_only_wrong: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


__all__ = [
    "LieLevel", "ClaimSpan", "LieFlag", "SeatHonesty", "LieReport", "ProbeCard",
    "DraftPair", "MeasuredModel", "MemoryPlan", "SteerCard",
    "SoloScore", "CompareRow", "CompareReport",
]
