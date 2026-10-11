"""Make one steering vector for (project, model). Method proven by tools/box/steer_test.py.

Contrast chats -> the model's own chat template -> last-token activations -> mean difference
per layer -> scaled to a small share of the hidden-state size -> control-vector GGUF -> the
strength is searched with a sanity check on neutral prompts.

Nothing here talks to a model: `source` reads activations, `render` applies the chat template
and `generate` runs the model with the vector. All three are injected.
"""
from __future__ import annotations

import inspect
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from council.core.event_types import STEER_TRAINED
from council.core.schemas_v15 import SteerCard
from council.steer import contrast, sanity, tune, vectors
from council.steer.cvec_file import write_cvec

__all__ = ["MIN_SEPARATION", "NEUTRAL_PROMPTS", "SteerService"]

MIN_SEPARATION = 0.75  # a layer below this does not tell the two sides apart
REASON_LIMIT = 300

# No system instruction, nothing to do with any rule: only "does the model still talk sense".
NEUTRAL_PROMPTS = [
    "What is the moon made of?",
    "How do bees make honey?",
    "Why do people need water?",
    "Write a Python function that counts the even numbers in a list.",
]

Render = Callable[[str, list[dict]], Awaitable[str]]
Generate = Callable[[str, Optional[Path], float, list[str]], Awaitable[list[str]]]


class SteerService:
    def __init__(self, source: Any, store: Any, render: Render, generate: Generate, cfg: Any,
                 emit: Optional[Callable[[str, dict], Any]] = None,
                 now: Callable[[], float] = time.time) -> None:
        self.source = source
        self.store = store
        self.render = render
        self.generate = generate
        self.cfg = cfg
        self.emit = emit
        self.now = now

    # ------------------------------------------------------------------ helpers

    def _card(self, project: str, model_id: str, reason: str, **fields: Any) -> SteerCard:
        return SteerCard(project=project, model_id=model_id, reason=reason[:REASON_LIMIT],
                         trained_at=float(self.now()), **fields)

    def _emit(self, card: SteerCard) -> None:
        if self.emit is None:
            return
        try:
            self.emit(STEER_TRAINED, dict(
                project=card.project, model_id=card.model_id, examples=card.examples,
                scale=card.scale, active=card.active, reason=card.reason))
        except Exception:
            pass  # a dead event bus must not lose the card

    async def _capture(self, model_id: str, text: str, layers: list[int]) -> dict[int, list[float]]:
        """Activations of one rendered prompt.

        A source with capture_text gets the text as it is. The ActivationSource protocol only
        takes messages, so there the whole rendered prompt rides in one user message.
        """
        direct = getattr(self.source, "capture_text", None)
        if direct is not None:
            got = await direct(model_id, text, layers)
        else:
            got = await self.source.capture(
                model_id, [{"role": "user", "content": text}], layers)
        return {int(k): [float(x) for x in v] for k, v in got.items()}

    async def _n_layer(self, model_id: str) -> int:
        info = self.source.info(model_id)
        if inspect.isawaitable(info):
            info = await info
        return int(info["n_layer"])

    # ------------------------------------------------------------------ train

    async def train(self, project: str, model_id: str, rule_pairs: list[tuple[str, str]],
                    n_layer: Optional[int] = None) -> SteerCard:
        """Never raises. The card says whether a vector is active and why."""
        try:
            card = await self._train(project, model_id, rule_pairs, n_layer)
        except Exception as e:
            card = self._card(str(project), str(model_id), f"training failed: {e}", version=0)
        self._emit(card)
        return card

    async def _train(self, project: str, model_id: str, rule_pairs: list[tuple[str, str]],
                     n_layer: Optional[int]) -> SteerCard:
        cfg = self.cfg
        if not cfg.enabled:
            return self._card(project, model_id, "steering is switched off", version=0)
        pairs = list(rule_pairs or [])
        if not contrast.enough(pairs, cfg.min_examples):
            return self._card(project, model_id, version=0, examples=len(pairs),
                              reason=f"not enough examples: {len(pairs)} of {cfg.min_examples}")

        if n_layer is None:
            n_layer = await self._n_layer(model_id)
        layers = vectors.pick_layers(int(n_layer), cfg.layers)
        if not layers:
            return self._card(project, model_id, version=0, examples=len(pairs),
                              reason=f"no layers to steer ({cfg.layers!r} of {n_layer})")

        pos_chats, neg_chats = contrast.prompts_for(pairs)
        examples = len(pos_chats)
        pos = [await self._capture(model_id, await self.render(model_id, c), layers)
               for c in pos_chats]
        neg = [await self._capture(model_id, await self.render(model_id, c), layers)
               for c in neg_chats]

        direction = vectors.mean_diff(pos, neg)
        direction = vectors.scale_to_fraction(
            direction, vectors.hidden_norms(pos + neg), cfg.target_fraction)
        sep = vectors.separation(pos, neg, direction)
        direction = {k: v for k, v in direction.items() if sep.get(k, 0.0) >= MIN_SEPARATION}
        if not direction:
            return self._card(project, model_id, "no layer separates the two sides",
                              version=0, examples=examples)

        version = self.store.next_version(project, model_id)
        path = Path(self.store.path_for(project, model_id, version))
        path.parent.mkdir(parents=True, exist_ok=True)
        write_cvec(path, direction, model_id)

        async def run(scale: float) -> list[str]:
            return await self.generate(model_id, path, scale, list(NEUTRAL_PROMPTS))

        picked = await tune.pick_scale(list(cfg.scales), run, is_broken=sanity.looks_broken)
        scale = picked.get("scale")
        card = self._card(
            project, model_id, str(picked.get("reason", "")), version=version,
            layers=sorted(direction), scale=scale, examples=examples,
            fraction=float(cfg.target_fraction), active=scale is not None, path=str(path))
        return self.store.save(card)

    # ------------------------------------------------------------------ read

    def active_for(self, project: str, model_id: str) -> Optional[tuple[Path, float]]:
        """(control-vector file, strength) to serve this model with, or None."""
        try:
            card = self.store.active(project, model_id)
        except Exception:
            return None
        if card is None or not card.active or card.scale is None or not card.path:
            return None
        path = Path(card.path)
        return (path, float(card.scale)) if path.is_file() else None
