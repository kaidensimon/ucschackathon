"""Config loading (spec 20, 5.4, 27.8, 28.5). Missing files yield full defaults."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from council.core.schemas import MODE_DEFAULTS, ModeConfig, ModelEntry


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="ignore", protected_namespaces=())


HOST_DRIVERS: tuple[str, ...] = ("llama_router", "llama_process", "ollama", "llamacpp")


class HostConfig(_Cfg):
    driver: str = "llama_router"  # one of HOST_DRIVERS
    headroom_gib: float = 12
    core_models: list[str] = Field(default_factory=list)


class GatewayConfig(_Cfg):
    mock: bool = False
    max_concurrent_models: int = 2
    default_timeout_s: float = 120
    cache: bool = True


class RouterWeights(_Cfg):
    merit: float = 0.0
    vote: float = 0.0
    cover: float = 0.0
    div: float = 0.0
    load: float = 0.0
    repeat: float = 0.0


class RouterConfig(_Cfg):
    k: int = 6
    max_per_lab: int = 1
    floor_delta: float = 0.10
    wildcard_floor_delta: float = 0.20
    tau: float = 0.05
    top_n_sample: int = 20
    repeat_window: int = 5
    neighbours: int = 30
    weights_tier_a: RouterWeights = Field(
        default_factory=lambda: RouterWeights(merit=0.55, vote=0.0, cover=0.0, div=0.45, load=0.10, repeat=0.10)
    )
    weights_tier_b: RouterWeights = Field(
        default_factory=lambda: RouterWeights(merit=0.30, vote=0.30, cover=0.15, div=0.25, load=0.10, repeat=0.10)
    )


class ChamberConfig(_Cfg):
    consensus_threshold: float = 0.80
    quorum_fraction: float = 0.60
    early_exit_min_confidence: float = 0.70
    blocking_objections_to_veto: int = 2
    max_checks_per_round: int = 6
    chair_external: bool = False
    ratify_in_plan_mode: bool = True
    ratify_min_approval: float = 0.60
    adaptive: bool = True  # scale rounds, deadline and reasoning to the task (EffortPlan)
    chair_pick: Literal["random", "router"] = "random"
    protocol: Literal["structured", "open"] = "structured"  # open = free text + a card per message
    max_extra_rounds: int = 2  # extra voting rounds a close vote may add
    extend_min_agreement: float = 0.5  # extend only when agreement is at least this
    deadline_slack: float = 1.6  # deadline = estimated time x this
    min_deadline_s: float = 90
    max_deadline_s: float = 3600
    modes: dict[str, ModeConfig] = Field(default_factory=lambda: {k: v.model_copy(deep=True) for k, v in MODE_DEFAULTS.items()})


class ForemanConfig(_Cfg):
    auto_delegate: bool = False
    max_tasks_per_decompose_call: int = 12
    max_task_input_tokens: int = 4000
    max_task_output_tokens: int = 1500
    max_files_per_task: int = 2


class WorkersConfig(_Cfg):
    slots: int = 16
    max_attempts: int = 3


class InspectorConfig(_Cfg):
    max_parallel_checks: int = 8
    check_timeout_s: float = 60
    allowed_executables: list[str] = Field(default_factory=lambda: ["python3", "pytest"])
    network: bool = False


class ReviewConfig(_Cfg):
    max_cycles: int = 2
    debate: bool = True  # one rebuttal round when the first review vote is split
    final_say: Literal["random_seat", "user"] = "random_seat"  # who decides with no agreement
    deadline_s: float = 900


class ChronicleConfig(_Cfg):
    panel_size: int = 3
    recall_k: int = 8
    review_after_runs: int = 10
    decay: float = 0.9
    retract_below: float = 0.3


class TelemetryConfig(_Cfg):
    tick_s: float = 1
    reference_price_per_million_tokens: float = 0.0


class TribunalConfig(_Cfg):
    enabled: bool = True
    questions: int = 3
    min_agreement: float = 0.80
    in_bench: bool = False


class ProbeConfig(_Cfg):
    enabled: bool = True
    min_auroc: float = 0.80
    min_labelled: int = 50
    layers: list[int] = Field(default_factory=lambda: [8, 12, 16, 20])
    show_to_council: bool = True
    # "mock" | "ollama_embed" | "llamacpp". layers = [] means: pick from the model depth
    # (needs a source that knows the depth, which is "llamacpp").
    source: str = "mock"
    actdump_path: str = "~/council/tap-build/actdump"  # source = "llamacpp" only
    ollama_models_dir: str = ""  # "" = find it (OLLAMA_MODELS, the service dir, ~/.ollama)
    max_models: int = 1  # actdump processes alive at once; each holds a full model copy
    pool: str = "last"  # "last" token or "mean" over tokens


class BenchConfig(_Cfg):
    default_split: str = "test"
    calibration_split: str = "calibration"
    self_consistency_k: int = 5
    solo_max_output_tokens: int = 1200
    solo_max_reasoning_tokens: int = 4000


class OllamaConfig(_Cfg):
    base_url: str = "http://127.0.0.1:11434"
    keep_alive: str = "-1"
    num_ctx_live: int = 16384
    num_ctx_batch: int = 8192
    default_draft_num_predict: int = 0  # 0 = leave to Ollama; applies to speculative entries only


class LlamaCppConfig(_Cfg):
    """host.driver = "llamacpp": one llama-server process per model, on the Ollama blob."""

    server_bin: str = "~/llama.cpp/build/bin/llama-server"
    base_port: int = 18100  # model n listens on base_port + n
    ctx: int = 8192
    parallel: int = 1
    health_timeout_s: float = 240
    ollama_models_dir: str = ""  # "" = find it (OLLAMA_MODELS, the service dir, ~/.ollama)
    extra_args: list[str] = Field(default_factory=list)


class SteerConfig(_Cfg):
    """Per-project steering vectors (llama.cpp control vectors)."""

    enabled: bool = True
    layers: str = "auto"  # "auto" or a range such as "14-26"
    target_fraction: float = 0.06  # vector size as a share of the hidden-state size
    scales: list[float] = Field(default_factory=lambda: [0.5, 1.0, 1.5, 2.0])  # strengths searched
    min_examples: int = 6
    max_tokens_probe: int = 80  # tokens generated per sanity check


class LieConfig(_Cfg):
    enabled: bool = True
    show_to_council: bool = True
    max_claims: int = 8  # claims scored per answer
    flag_below: float = 0.30  # truth score under this = flag
    watch_below: float = 0.45
    gap_flag: float = 0.45  # stated confidence minus truth score over this = flag
    gap_watch: float = 0.30
    timeout_s: float = 20


class MemoryConfig(_Cfg):
    reserve_gib: float = 10.0  # kept free for the system
    overhead: float = 1.35  # real memory / file size, when a model was not measured
    share_roles: Literal["auto", "always", "never"] = "auto"  # give work roles to seated models
    measured_file: str = ""  # "" = <home>/model_checks.json


class Config(_Cfg):
    host: HostConfig = Field(default_factory=HostConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    router: RouterConfig = Field(default_factory=RouterConfig)
    chamber: ChamberConfig = Field(default_factory=ChamberConfig)
    foreman: ForemanConfig = Field(default_factory=ForemanConfig)
    workers: WorkersConfig = Field(default_factory=WorkersConfig)
    inspector: InspectorConfig = Field(default_factory=InspectorConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    chronicle: ChronicleConfig = Field(default_factory=ChronicleConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    tribunal: TribunalConfig = Field(default_factory=TribunalConfig)
    probe: ProbeConfig = Field(default_factory=ProbeConfig)
    bench: BenchConfig = Field(default_factory=BenchConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    llamacpp: LlamaCppConfig = Field(default_factory=LlamaCppConfig)
    steer: SteerConfig = Field(default_factory=SteerConfig)
    lie: LieConfig = Field(default_factory=LieConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    def mode(self, name: str) -> ModeConfig:
        try:
            return self.chamber.modes[name]
        except KeyError:
            raise KeyError(f"unknown mode: {name}") from None


def home() -> Path:
    env = os.environ.get("COUNCIL_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2]


def _merge_modes(raw_modes: Any) -> dict[str, ModeConfig]:
    modes = {k: v.model_copy(deep=True) for k, v in MODE_DEFAULTS.items()}
    if not isinstance(raw_modes, dict):
        return modes
    for name, over in raw_modes.items():
        base = modes[name].model_dump() if name in modes else {"name": name}
        if isinstance(over, dict):
            base.update(over)
        base["name"] = name
        modes[name] = ModeConfig(**base)
    return modes


def load_config(path: Path | None = None) -> Config:
    p = Path(path) if path is not None else home() / "config" / "council.toml"
    data: dict[str, Any] = {}
    if p.is_file():
        with open(p, "rb") as f:
            data = tomllib.load(f)
    chamber = dict(data.get("chamber", {}) or {})
    chamber["modes"] = _merge_modes(chamber.get("modes"))
    data["chamber"] = chamber
    return Config(**data)


def load_registry(path: Path | None = None) -> list[ModelEntry]:
    p = Path(path) if path is not None else home() / "config" / "models.json"
    if not p.is_file():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("models", [])
    return [ModelEntry(**item) for item in raw]


def load_lenses(path: Path | None = None) -> dict[str, str]:
    p = Path(path) if path is not None else home() / "config" / "lenses.json"
    if not p.is_file():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in raw.items()}


__all__ = [
    "Config", "HostConfig", "GatewayConfig", "RouterWeights", "RouterConfig", "ChamberConfig",
    "ForemanConfig", "WorkersConfig", "InspectorConfig", "ReviewConfig", "ChronicleConfig",
    "TelemetryConfig", "TribunalConfig", "ProbeConfig", "BenchConfig",
    "OllamaConfig", "LlamaCppConfig", "SteerConfig", "LieConfig", "MemoryConfig", "HOST_DRIVERS",
    "home", "load_config", "load_registry", "load_lenses",
]
