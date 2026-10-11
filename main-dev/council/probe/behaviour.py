"""Behavioural reliability score, no activations needed (ARCHITECTURE 28.3). Pure."""
from __future__ import annotations

import math
from collections import Counter
from typing import Optional

from council.core.schemas import BehaviourSignals, CallResult, Draft
from council.probe.logreg import train_logreg

SIGNAL_NAMES = ("mean_logprob", "entropy", "self_agreement", "stated_confidence", "track_record")
MIN_FIT_ROWS = 50

# Features are centred at 0.5, so a missing signal adds nothing. Entropy has a negative weight.
DEFAULT_WEIGHTS: dict[str, float] = {
    "mean_logprob": 3.0,
    "entropy": -2.0,
    "self_agreement": 3.0,
    "stated_confidence": 1.5,
    "track_record": 2.5,
    "bias": 0.0,
}


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def signals_from(
    result: Optional[CallResult],
    draft: Optional[Draft],
    resample_keys: Optional[list[Optional[str]]],
    track: Optional[tuple[float, float]],
) -> BehaviourSignals:
    """Build signals. Anything that cannot be worked out stays None."""
    mean_lp = None
    entropy = None
    lps = [lp for lp in (result.logprobs or []) if isinstance(lp, (int, float)) and math.isfinite(lp)] if result else []
    if lps:
        lps = [min(lp, 0.0) for lp in lps]
        mean_lp = sum(lps) / len(lps)
        entropy = sum(1.0 - math.exp(lp) for lp in lps) / len(lps)  # 0 sure .. 1 lost

    agree = None
    keys = [k for k in (resample_keys or []) if k is not None]
    if keys:
        ref = draft.answer_key if draft is not None and draft.answer_key is not None else None
        if ref is None:
            ref = Counter(keys).most_common(1)[0][0]
        agree = sum(1 for k in keys if k == ref) / len(keys)

    stated = _clamp(float(draft.confidence)) if draft is not None else None

    rec = None
    if track is not None:
        t, f = max(float(track[0]), 0.0), max(float(track[1]), 0.0)
        rec = (t + 1.0) / (t + f + 2.0)

    return BehaviourSignals(
        mean_logprob=mean_lp,
        entropy=entropy,
        self_agreement=agree,
        stated_confidence=stated,
        track_record=rec,
    )


def _features(signals: BehaviourSignals) -> dict[str, float]:
    """Each present signal as a 0..1 feature (higher = more trustworthy except entropy)."""
    out: dict[str, float] = {}
    if signals.mean_logprob is not None:
        out["mean_logprob"] = _clamp(math.exp(min(signals.mean_logprob, 0.0)))
    if signals.entropy is not None:
        out["entropy"] = _clamp(signals.entropy)
    for name in ("self_agreement", "stated_confidence", "track_record"):
        v = getattr(signals, name)
        if v is not None:
            out[name] = _clamp(v)
    return out


def reliability(signals: BehaviourSignals, weights: Optional[dict] = None) -> float:
    """sigmoid(bias + rescaled sum of w * (feature - 0.5)) over present signals; result in 0..1."""
    w = weights or DEFAULT_WEIGHTS
    feats = _features(signals)
    total = sum(abs(w.get(n, 0.0)) for n in SIGNAL_NAMES)
    present = sum(abs(w.get(n, 0.0)) for n in feats)
    if not feats or present <= 0.0:
        return _clamp(_sigmoid(float(w.get("bias", 0.0))))
    scale = total / present  # renormalise after dropping missing signals
    z = sum(w.get(n, 0.0) * (v - 0.5) for n, v in feats.items()) * scale
    return _clamp(_sigmoid(float(w.get("bias", 0.0)) + z))


def fit_weights(rows: list[tuple[BehaviourSignals, int]]) -> dict:
    """Refit by logistic regression once 50+ labelled rows exist; else the defaults."""
    if len(rows) < MIN_FIT_ROWS:
        return dict(DEFAULT_WEIGHTS)
    y = [1 if lab else 0 for _, lab in rows]
    if len(set(y)) < 2:
        return dict(DEFAULT_WEIGHTS)
    X = []
    for sig, _ in rows:
        f = _features(sig)
        X.append([f.get(n, 0.5) - 0.5 for n in SIGNAL_NAMES])  # missing -> 0
    ws, bias = train_logreg(X, y, lr=1.0, epochs=500)
    out = {n: float(w) for n, w in zip(SIGNAL_NAMES, ws)}
    out["bias"] = float(bias)
    return out
