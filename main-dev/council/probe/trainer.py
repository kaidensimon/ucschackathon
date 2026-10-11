"""Activation probe training and scoring (ARCHITECTURE 28.4).

Standardisation is folded into the stored weights, so `score` takes raw
activations: w' = w / std, b' = b - sum(w * mean / std).

How a probe is validated
- Rows are split BY TASK, so the honest and the lie row of one task never sit on two sides.
- Three parts: train (fit), select (pick the layer), gate (the reported held-out AUROC).
  The layer is never picked on the rows that gate it. With one layer there is nothing to
  pick, so the select part joins the gate.
- `validated` needs gate AUROC >= min_auroc AND at least `min_gate_per_class` gate rows of
  each class. With fewer rows the AUROC is too coarse to mean anything (on 2 rows it is 0 or
  1): the probe is a `candidate` at best and produces no live score.

train_from_pairs is the same idea for the instruction-free pairs of probe/dataset.py, with two
controls next to every number: probes fitted on shuffled labels (their mean should sit near 0.5) and a
probe fitted on answer length and token counts only (the cheap baseline). A probe that does
not beat the cheap baseline by BASELINE_MARGIN has learned the wording, not the model state.
The switch-on decision is probe/gate.py decide_active; the report also carries a Platt pair
(probe/calibration.py) that maps the truth score 1 - P(lie) to a calibrated one.

One text layout (1.5): every training row and every live claim is the text of
probe/layout.py probe_messages(task, statement), which ends with "The statement above is".
LAYOUT names that layout. A probe stored under another LAYOUT is not used.
"""
from __future__ import annotations

import math
import random
import re
from typing import Any, Callable, Optional

from council.core.schemas import BenchTask, Probe
from council.probe import calibration
from council.probe.dataset import Pair, split_by_task, statement_pairs
from council.probe.gate import decide_active
from council.probe.layout import LAYOUT_VERSION, probe_messages
from council.probe.logreg import (
    auroc,
    predict_proba,
    standardize,
    top_dimensions,
    train_logreg,
)

# The layout mark of a probe in the store (probe/service.py writes and checks it). Layout 1,
# never marked, was "<role>: <content>" lines of a bare statement (training) or of system +
# task + answer (live). From 2 on it is layout.probe_messages on both sides, and it follows
# LAYOUT_VERSION, so a change of the text there also retires the stored probes.
LAYOUT = LAYOUT_VERSION + 1
STATEMENT_TASK = "Is this statement true or false?"  # the question of a statement that has none
_QA_HEAD, _QA_SEP = "Question: ", "\nAnswer: "


def _marked(messages: list[dict], lie: bool) -> list[dict]:
    """The lie mark is for the mock source only: it is not text, and no real source reads it."""
    if lie:
        messages[-1]["meta"] = {"lie": True}
    return messages


def honest_messages(task_prompt: str, answer: str) -> list[dict]:
    return probe_messages(task_prompt, answer)


def lie_messages(task_prompt: str, false_answer: str) -> list[dict]:
    """The same layout as the honest row: no instruction to deceive, only the false statement."""
    return _marked(probe_messages(task_prompt, false_answer), True)


def split_pair_text(text: str) -> tuple[str, str]:
    """(task, statement) of one pair text: "Question: q\\nAnswer: a" is split, a bare statement
    gets STATEMENT_TASK."""
    text = str(text if text is not None else "")
    if text.startswith(_QA_HEAD) and _QA_SEP in text:
        task, statement = text[len(_QA_HEAD):].split(_QA_SEP, 1)
        return task, statement
    return STATEMENT_TASK, text


MIN_GATE_PER_CLASS = 10  # gate rows of each class needed before a probe may be validated
MAX_CONTROL = 0.62  # a shuffled-label AUROC above this means the rows leak (gate.decide_active)
CONTROL_REPEATS = 5  # shuffled-label probes per layer; their mean AUROC is the control
PLATT_ITERS = 2000
PLATT_LR = 0.5
BUILTIN_PAIRS = 600  # default size of builtin_pairs: 200 of dataset.py, 400 of truth_set.py
SELECT_FRACTION = 0.15
GATE_FRACTION = 0.25
PAIR_TEST_FRACTION = 0.3
BASELINE_MARGIN = 0.1  # a probe must beat the cheap-feature baseline by this much
SHUFFLE_TOLERANCE = 0.2  # a shuffled-label AUROC further than this from 0.5 gets a warning


def default_false_answer(task: BenchTask) -> str:
    """A wrong answer for a task with a known answer."""
    kind = task.answer_type
    ans = (task.answer or "").strip()
    if kind == "mcq":
        letters = [chr(ord("A") + i) for i in range(len(task.choices or []))] or list("ABCD")
        for letter in letters:
            if letter.upper() != ans.upper():
                return letter
        return "A"
    if kind == "numeric":
        try:
            v = float(ans)
            return str(int(v) + 1) if v == int(v) else str(v + 1)
        except ValueError:
            return ans + "1"
    return "not " + ans if ans else "none"


async def bootstrap_dataset(
    source: Any,
    model_id: str,
    tasks: list[BenchTask],
    layers: list[int],
    false_answer: Callable[[BenchTask], str] | None = None,
) -> dict[int, tuple[list[list[float]], list[int]]]:
    """Honest (label 0) and lie (label 1) activations per layer, two rows per task in that order."""
    fa = false_answer or default_false_answer
    data: dict[int, tuple[list[list[float]], list[int]]] = {l: ([], []) for l in layers}
    for task in tasks:
        honest = await source.capture(model_id, honest_messages(task.prompt, task.answer), layers)
        lie = await source.capture(model_id, lie_messages(task.prompt, fa(task)), layers)
        for l in layers:
            if l in honest and l in lie:
                X, y = data[l]
                X.append(list(honest[l]))
                y.append(0)
                X.append(list(lie[l]))
                y.append(1)
    return data


def _groups(entry: tuple, n: int) -> list[Any]:
    """One group id per row. Given as a third element, else honest/lie pairs, else one per row."""
    if len(entry) >= 3 and entry[2] is not None and len(entry[2]) == n:
        return list(entry[2])
    y = entry[1]
    if n % 2 == 0 and all(y[i] == 0 and y[i + 1] == 1 for i in range(0, n, 2)):
        return [i // 2 for i in range(n)]
    return list(range(n))


def _split_groups(groups: list[Any], seed: int, with_select: bool) -> Optional[tuple[set, set, set]]:
    """(train, select, gate) group ids, or None when there are too few groups to hold any out."""
    ids = sorted(set(groups), key=str)
    random.Random(seed).shuffle(ids)
    n = len(ids)
    n_gate = max(1, int(round(n * GATE_FRACTION)))
    n_sel = max(1, int(round(n * SELECT_FRACTION)))
    if not with_select:
        n_gate, n_sel = n_gate + n_sel, 0
    if n - n_gate - n_sel < 1:
        return None
    gate = set(ids[:n_gate])
    select = set(ids[n_gate:n_gate + n_sel])
    return set(ids[n_gate + n_sel:]), select, gate


def _rows(X, y, groups, keep: set):
    idx = [i for i, g in enumerate(groups) if g in keep]
    return [X[i] for i in idx], [y[i] for i in idx]


def evaluate(
    model_id: str,
    data: dict[int, tuple],
    min_auroc: float,
    now: float,
    seed: int = 0,
    min_gate_per_class: int = MIN_GATE_PER_CLASS,
) -> tuple[Probe, dict[int, float]]:
    """Train per layer and gate the best one. Returns (probe, {layer: AUROC used to pick it}).

    probe.auroc is the gate AUROC: measured on rows that neither fitted nor picked the layer.
    """
    usable = [l for l in sorted(data) if len(data[l][0]) >= 4 and len(set(data[l][1])) >= 2]
    with_select = len(usable) > 1
    fits: dict[int, dict[str, Any]] = {}
    picked: dict[int, float] = {}
    for layer in usable:
        X, y = data[layer][0], data[layer][1]
        groups = _groups(data[layer], len(X))
        parts = _split_groups(groups, seed, with_select)
        if parts is None:
            continue
        train, select, gate = parts
        Xtr, ytr = _rows(X, y, groups, train)
        Xga, yga = _rows(X, y, groups, gate)
        if len(set(ytr)) < 2 or not Xga:
            continue
        Xs, means, stds = standardize(Xtr)
        w, b = train_logreg(Xs, ytr, seed=seed)
        raw_w = [wi / s for wi, s in zip(w, stds)]
        raw_b = b - sum(wi * m / s for wi, m, s in zip(w, means, stds))
        gate_auroc = auroc([predict_proba(raw_w, raw_b, r) for r in Xga], yga)
        if with_select:
            Xse, yse = _rows(X, y, groups, select)
            picked[layer] = auroc([predict_proba(raw_w, raw_b, r) for r in Xse], yse)
        else:
            picked[layer] = gate_auroc
        fits[layer] = {
            "w": raw_w, "b": raw_b, "gate": gate_auroc, "n_train": len(Xtr),
            "pos": sum(1 for v in yga if v == 1), "neg": sum(1 for v in yga if v == 0),
        }
    if not fits:
        return Probe(model_id=model_id, trained_at=now, status="rejected"), picked

    layer = sorted(fits, key=lambda l: (-picked[l], l))[0]
    fit = fits[layer]
    enough = min(fit["pos"], fit["neg"]) >= max(1, int(min_gate_per_class))
    if fit["gate"] < min_auroc:
        status = "rejected"
    else:
        status = "validated" if enough else "candidate"
    probe = Probe(
        model_id=model_id, layer=layer, weights=fit["w"], bias=fit["b"], auroc=fit["gate"],
        n_train=fit["n_train"], trained_at=now, status=status,
    )
    return probe, picked


def train_probe(
    model_id: str,
    data: dict[int, tuple],
    min_auroc: float,
    now: float,
    seed: int = 0,
    min_gate_per_class: int = MIN_GATE_PER_CLASS,
) -> Probe:
    """Train per layer, keep the best, gate it on rows it never saw. See the module text."""
    return evaluate(model_id, data, min_auroc, now, seed, min_gate_per_class)[0]


def score(probe: Probe, activations: dict[int, list[float]]) -> float | None:
    """P(lie) from a validated probe, else None."""
    if probe.status != "validated":
        return None
    x = activations.get(probe.layer)
    if x is None or len(x) != len(probe.weights):
        return None
    return predict_proba(probe.weights, probe.bias, x)


def attribution(probe: Probe, n: int = 10) -> list[tuple[int, float]]:
    """Top-weighted dimensions: a direction, not a neuron."""
    return top_dimensions(probe.weights, n)


# ---------------------------------------------------------------------- pairs (dataset.py)

_TOKEN_RE = re.compile(r"\w+|[^\w\s]")
_sumprod = getattr(math, "sumprod", None)


def pair_messages(text: str, lie: bool = False) -> list[dict]:
    """One pair text in the probe layout, as one user message. See split_pair_text."""
    task, statement = split_pair_text(text)
    return _marked(probe_messages(task, statement), lie)


def builtin_pairs(seed: int = 0, n: int = BUILTIN_PAIRS) -> list[Pair]:
    """n built-in statement pairs: a third from dataset.statement_pairs (4 kinds), the rest from
    truth_set.more_statement_pairs (12 kinds). When one runs short the other fills up."""
    from council.probe.truth_set import more_statement_pairs  # it imports dataset, not trainer

    n = max(0, int(n))
    basic = statement_pairs(seed, n)
    more = more_statement_pairs(seed, n)
    n_basic = min(len(basic), max((n + 2) // 3, n - len(more)))
    out = basic[:n_basic] + more[:n - n_basic]
    seen: set[str] = set()
    return [p for p in out if not (p.task_id in seen or seen.add(p.task_id))]


def cheap_features(text: str, answer: str) -> list[float]:
    """What a probe could cheat on: answer length, answer tokens, text length, text tokens."""
    return [float(len(answer)), float(len(_TOKEN_RE.findall(answer))),
            float(len(text)), float(len(_TOKEN_RE.findall(text)))]


def _dot(a: list[float], b: list[float]) -> float:
    if _sumprod is not None:
        return _sumprod(a, b)
    return sum(x * y for x, y in zip(a, b))


def _sig(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _fit_dual(K: list[list[float]], Xs: list[list[float]], y: list[int],
              l2: float = 0.01, lr: float = 0.1, epochs: int = 200) -> tuple[list[float], float]:
    """The same gradient descent as logreg.train_logreg (from zero weights), run on the Gram
    matrix K = Xs Xs^T. With w = Xs^T a the update of w is an update of a, so an epoch costs
    n*n and not n*d: real activations have thousands of dimensions and a few hundred rows."""
    n = len(y)
    a = [0.0] * n
    b = 0.0
    keep = 1.0 - lr * l2
    for _ in range(epochs):
        err = [_sig(b + _dot(K[i], a)) - y[i] for i in range(n)]
        a = [keep * ai - lr * e / n for ai, e in zip(a, err)]
        b -= lr * sum(err) / n
    w = [0.0] * len(Xs[0])
    for ai, row in zip(a, Xs):
        if ai:
            w = [wj + ai * x for wj, x in zip(w, row)]
    return w, b


def _fit_many(X: list[list[float]], labelings: list[list[int]], seed: int
              ) -> list[tuple[list[float], float]]:
    """One probe per labeling of the same rows, as (weights, bias) on RAW rows."""
    Xs, means, stds = standardize(X)
    n, d = len(Xs), len(Xs[0])
    K = [[_dot(Xs[i], Xs[j]) for j in range(n)] for i in range(n)] if d > n else None
    out = []
    for y in labelings:
        w, b = _fit_dual(K, Xs, y) if K is not None else train_logreg(Xs, y, seed=seed)
        raw_w = [wi / s for wi, s in zip(w, stds)]
        out.append((raw_w, b - sum(wi * m / s for wi, m, s in zip(w, means, stds))))
    return out


def _auroc_of(fit: tuple[list[float], float], X: list[list[float]], y: list[int]) -> float:
    return auroc([predict_proba(fit[0], fit[1], r) for r in X], y)


async def capture_pairs(source: Any, model_id: str, pairs: list[Pair], layers: list[int],
                        progress: Callable[[int, int], None] | None = None
                        ) -> tuple[dict[str, tuple[dict, dict]], list[str]]:
    """({task_id: (honest activations, lie activations)}, errors). One text at a time.

    A pair whose capture fails, or that lacks a wanted layer, is left out and its error kept.
    When no pair at all can be captured the first error is raised."""
    acts: dict[str, tuple[dict, dict]] = {}
    errors: list[str] = []
    first: Exception | None = None
    for i, pair in enumerate(pairs):
        try:
            honest = await source.capture(model_id, pair_messages(pair.honest_text), layers)
            lie = await source.capture(model_id, pair_messages(pair.lie_text, True), layers)
            missing = [l for l in layers if l not in honest or l not in lie]
            if missing:
                raise ValueError(f"no activations for layers {missing}")
            acts[pair.task_id] = (honest, lie)
        except Exception as e:
            first = first or e
            errors.append(f"{pair.task_id}: {e}")
        if progress is not None:
            progress(i + 1, len(pairs))
    if pairs and not acts and first is not None:
        raise first
    return acts, errors


def _pair_rows(pairs: list[Pair], acts: dict, layer: int) -> tuple[list[list[float]], list[int]]:
    X: list[list[float]] = []
    y: list[int] = []
    for p in pairs:
        honest, lie = acts[p.task_id]
        X.append(list(honest[layer]))
        y.append(0)
        X.append(list(lie[layer]))
        y.append(1)
    return X, y


def _flip_half(y: list[int], rng: random.Random) -> list[int]:
    """The shuffled-label control: the two labels of a random half of the questions swapped.

    Rows come two per question (honest, lie). Swapping exactly half leaves the new labels with
    no correlation to the true ones. A plain shuffle keeps a small chance correlation, and on
    a strong true signal that is enough to push the control far from 0.5 in either direction.
    """
    n_pairs = len(y) // 2
    flip = set(rng.sample(range(n_pairs), n_pairs // 2))
    out = list(y)
    for i in flip:
        out[2 * i], out[2 * i + 1] = out[2 * i + 1], out[2 * i]
    return out


def _cheap_rows(pairs: list[Pair]) -> tuple[list[list[float]], list[int]]:
    X: list[list[float]] = []
    y: list[int] = []
    for p in pairs:
        X.append(cheap_features(p.honest_text, p.truth))
        y.append(0)
        X.append(cheap_features(p.lie_text, p.false_answer))
        y.append(1)
    return X, y


async def train_from_pairs(
    source: Any,
    model_id: str,
    pairs: list[Pair],
    layers: list[int],
    min_auroc: float,
    now: float,
    seed: int = 0,
    test_fraction: float = PAIR_TEST_FRACTION,
    min_test_per_class: int = MIN_GATE_PER_CLASS,
    margin: float = BASELINE_MARGIN,
    progress: Callable[[int, int], None] | None = None,
    max_control: float = MAX_CONTROL,
) -> dict[str, Any]:
    """Train one probe per layer on instruction-free pairs and say whether the best can be trusted.

    Questions are split three ways, never a question on two sides: train (fit), select (pick
    the layer; only with more than one layer) and test (every reported AUROC). The report:

        layers: [{layer, n_train, n_test, auroc, select_auroc, shuffled_auroc, cheap_auroc, picked}]
        best_layer, auroc, shuffled_auroc, cheap_auroc, status, validated, reasons, warnings,
        n_pairs, n_used, n_train_pairs, n_select_pairs, n_test_pairs, capture_errors, probe

    n_train and n_test count rows (two per question). `probe` is Probe.model_dump().
    validated needs: test AUROC >= min_auroc, AND >= cheap baseline + margin, AND shuffled-label
    AUROC <= max_control, AND at least min_test_per_class test questions (fewer: `candidate`, no
    live score). gate.decide_active has the last word: `active`, `gate_reason`.

    Also in the report: layout (LAYOUT), accuracy (test rows, P(lie) cut at 0.5), platt ([a, b]
    for the truth score 1 - P(lie), or None), platt_on ("select" or "test": the rows it was
    fitted on) and ece (test rows, after Platt).
    """
    layers = [int(l) for l in dict.fromkeys(layers)]
    acts, errors = await capture_pairs(source, model_id, pairs, layers, progress)
    used = [p for p in dict((p.task_id, p) for p in pairs).values() if p.task_id in acts]
    rest, test = split_by_task(used, test_fraction, seed)
    select: list[Pair] = []
    train = rest
    if len(layers) > 1 and len(rest) >= 3:
        train, select = split_by_task(rest, SELECT_FRACTION / max(1e-9, 1.0 - test_fraction),
                                      seed + 1)
    report: dict[str, Any] = {
        "model_id": model_id, "seed": seed, "min_auroc": float(min_auroc), "margin": float(margin),
        "min_test_per_class": int(min_test_per_class), "trained_at": now,
        "n_pairs": len(pairs), "n_used": len(used), "n_train_pairs": len(train),
        "n_select_pairs": len(select), "n_test_pairs": len(test),
        "capture_errors": errors[:20], "n_capture_errors": len(errors),
        "layers": [], "best_layer": None, "auroc": None, "shuffled_auroc": None,
        "cheap_auroc": None, "status": "rejected", "validated": False,
        "reasons": [], "warnings": [],
        "layout": LAYOUT, "max_control": float(max_control), "active": False,
        "gate_reason": "not trained", "accuracy": None, "platt": None, "platt_on": None,
        "ece": None,
    }
    if len(train) < 2 or not test or not layers:
        report["reasons"].append(
            f"too few questions to train and hold out ({len(used)} usable, {len(layers)} layers)")
        report["probe"] = Probe(model_id=model_id, trained_at=now, status="rejected").model_dump()
        return report

    cX, cy = _cheap_rows(train)
    tX, ty = _cheap_rows(test)
    cheap = _auroc_of(_fit_many(cX, [cy], seed)[0], tX, ty)
    report["cheap_auroc"] = cheap

    fits: dict[int, tuple[list[float], float]] = {}
    rows: dict[int, dict[str, Any]] = {}
    for layer in layers:
        Xtr, ytr = _pair_rows(train, acts, layer)
        Xte, yte = _pair_rows(test, acts, layer)
        flip_rng = random.Random(f"{seed}|shuffle|{layer}")
        shuffled = [_flip_half(ytr, flip_rng) for _ in range(CONTROL_REPEATS)]
        real, *controls = _fit_many(Xtr, [ytr] + shuffled, seed)
        test_auroc = _auroc_of(real, Xte, yte)
        if select:
            Xse, yse = _pair_rows(select, acts, layer)
            select_auroc = _auroc_of(real, Xse, yse)
        else:
            select_auroc = test_auroc
        fits[layer] = real
        rows[layer] = {
            "layer": layer, "n_train": len(Xtr), "n_test": len(Xte), "auroc": test_auroc,
            "select_auroc": select_auroc, "shuffled_auroc": sum(_auroc_of(c, Xte, yte) for c in controls) / len(controls),
            "cheap_auroc": cheap, "picked": False,
        }
    best = sorted(rows, key=lambda l: (-rows[l]["select_auroc"], l))[0]
    row = rows[best]
    row["picked"] = True
    report["layers"] = [rows[l] for l in layers]
    report["best_layer"] = best
    report["auroc"] = row["auroc"]
    report["shuffled_auroc"] = row["shuffled_auroc"]

    reasons: list[str] = report["reasons"]
    if row["auroc"] < min_auroc:
        status = "rejected"
        reasons.append(f"held-out AUROC {row['auroc']:.3f} is below the minimum {min_auroc:.2f}")
    elif row["auroc"] < cheap + margin:
        status = "rejected"
        reasons.append(f"held-out AUROC {row['auroc']:.3f} is not {margin:.2f} above the "
                       f"cheap-feature baseline {cheap:.3f}")
    elif len(test) < max(1, int(min_test_per_class)):
        status = "candidate"
        reasons.append(f"only {len(test)} held-out questions, {int(min_test_per_class)} needed")
    elif row["shuffled_auroc"] > max_control:
        status = "rejected"
        reasons.append(f"shuffled-label control {row['shuffled_auroc']:.3f} is above "
                       f"{max_control:.2f}: the probe finds signal where there is none")
    else:
        status = "validated"
    active, gate_reason = decide_active(
        row["auroc"], row["n_test"], row["shuffled_auroc"], cheap, min_auroc=float(min_auroc),
        min_test=2 * max(1, int(min_test_per_class)), max_control=float(max_control),
        min_margin=float(margin))
    if status == "validated" and not active:  # the gate has the last word
        status = "rejected"
        reasons.append(gate_reason)
    report["active"] = bool(active and status == "validated")
    report["gate_reason"] = gate_reason

    # Accuracy and calibration. Platt is fitted on the select rows when there are any (they did
    # not fit the weights), else on the test rows; either way ece is measured on the test rows.
    Xte, yte = _pair_rows(test, acts, best)
    p_lie = [predict_proba(fits[best][0], fits[best][1], r) for r in Xte]
    report["accuracy"] = sum(1 for p, y in zip(p_lie, yte) if (p >= 0.5) == (y == 1)) / len(yte)
    truth_scores = [1.0 - p for p in p_lie]
    truth_labels = [1 - y for y in yte]
    fit_scores, fit_labels, fit_on = truth_scores, truth_labels, "test"
    if select:
        Xse, yse = _pair_rows(select, acts, best)
        fit_scores = [1.0 - predict_proba(fits[best][0], fits[best][1], r) for r in Xse]
        fit_labels, fit_on = [1 - y for y in yse], "select"
    if len(set(fit_labels)) == 2:  # one class: fit_platt gives (1, 0), which is not "unchanged"
        ab = calibration.fit_platt(fit_scores, fit_labels, PLATT_ITERS, PLATT_LR)
        if all(math.isfinite(v) for v in ab) and ab[0] > 0:
            report["platt"] = [float(ab[0]), float(ab[1])]
            report["platt_on"] = fit_on
            truth_scores = [calibration.apply_platt(v, ab) for v in truth_scores]
    report["ece"] = calibration.ece(truth_scores, truth_labels)

    if not select and len(layers) > 1:
        report["warnings"].append("too few questions to pick the layer apart from the test rows")
    if abs(row["shuffled_auroc"] - 0.5) > SHUFFLE_TOLERANCE:
        report["warnings"].append(
            f"shuffled-label control is {row['shuffled_auroc']:.3f}, far from 0.5: "
            "the held-out set is small or the rows leak")
    probe = Probe(model_id=model_id, layer=best, weights=fits[best][0], bias=fits[best][1],
                  auroc=row["auroc"], n_train=row["n_train"], trained_at=now, status=status)
    report["status"] = status
    report["validated"] = status == "validated"
    report["probe"] = probe.model_dump()
    return report
