"""Pydantic schemas mirroring docs/api_contract.md v1.1.

Acts as the executable contract for request/response validation.
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class BaseContractModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class StageItem(BaseContractModel):
    id: int
    key: str
    label: str
    tactic: str = ""
    color: str


class ModelMetrics(BaseContractModel):
    f1: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    fpr: float = 0.0
    pr_auc: float = 0.0
    mean_lead_time_windows: float = 0.0
    baseline_f1: float = 0.0


class ModelResponse(BaseContractModel):
    name: str
    trained_on: str
    window_s: float
    stride_s: float
    horizon_k: int
    params: int
    git_sha: str
    stages: list[StageItem]
    metrics: ModelMetrics
    feature_count: int


class HealthResponse(BaseContractModel):
    status: str = "ok"
    model_loaded: bool = False
    active_checkpoint: Optional[str] = None
    offline: bool = True


class DemoItem(BaseContractModel):
    id: str
    day: str
    start: str
    end: str
    description: str
    flows: int
    size_mb: float
    labels: dict[str, int]
    file: str


class JobCreatedResponse(BaseContractModel):
    job_id: str
    state: str = "queued"


class JobStatusResponse(BaseContractModel):
    id: str
    state: str  # queued | running | done | error
    progress: float = 0.0  # 0.0 to 1.0
    stage_text: str = ""
    error: Optional[dict[str, str]] = None


class TopTalkerItem(BaseContractModel):
    ip: str
    flows: int
    bytes_out: int


class TopFeatureItem(BaseContractModel):
    name: str
    value: float
    attribution: float
    direction: str = "up"


class ForecastItem(BaseContractModel):
    p_cum: list[float]
    p_lo: list[float]
    p_hi: list[float]
    p_step: Optional[list[float]] = None
    p_cum_attack: Optional[list[float]] = None
    p_cum_escalate: Optional[list[float]] = None


class TimelineEntry(BaseContractModel):
    t: int
    ts: str
    observed_stage: Optional[int] = None
    observed_stage_conf: Optional[float] = None
    pred_stage: int
    stage_probs: list[float]
    forecast: ForecastItem
    alarm: bool
    surprise: float
    p_max: Optional[float] = None
    p_max_mc: Optional[float] = None
    top_features: list[TopFeatureItem] = Field(default_factory=list)
    attention: list[float] = Field(default_factory=list)
    flow_count: int = 0
    top_talkers: list[TopTalkerItem] = Field(default_factory=list)


class StageSpanItem(BaseContractModel):
    start_t: int
    end_t: int
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None
    stage: int
    label: str


class OnsetItem(BaseContractModel):
    t: int
    ts: str
    label: Optional[str] = None


class GroundTruthItem(BaseContractModel):
    available: bool
    spans: Optional[list[StageSpanItem]] = None
    onsets: Optional[list[OnsetItem]] = None
    compromise_windows: Optional[int] = None


class AlarmItem(BaseContractModel):
    t: int
    ts: str
    p: float
    pred_stage: Optional[int] = None
    until_t: Optional[int] = None
    onset_t: Optional[int] = None
    lead_windows: Optional[int] = None
    lead_seconds: Optional[float] = None
    windows: Optional[int] = None
    sustained: Optional[bool] = None


class ExplanationGlobalItem(BaseContractModel):
    feature_names: list[str]
    mean_abs_attribution: list[float]


class PerEpisodeItem(BaseContractModel):
    onset: int
    onset_ts: Optional[str] = None
    first_alarm: Optional[int] = None
    first_alarm_ts: Optional[str] = None
    lead_windows: int
    lead_seconds: float
    detected_early: bool


class LeadTimeSummaryItem(BaseContractModel):
    episodes: int
    persistence_windows: int = 2
    warned_early: int
    mean_lead_windows: float = 0.0
    mean_lead_seconds: float = 0.0
    per_episode: list[PerEpisodeItem] = Field(default_factory=list)


class SourceItem(BaseContractModel):
    filename: Optional[str] = None
    kind: Optional[str] = None
    flows: int
    windows: int
    t0: str
    window_s: float
    stride_s: float


class AnalysisResultPayload(BaseContractModel):
    payload_version: str = "1.1"
    alarm_statistic: str = "p_max (mean path)"
    threshold_policy: str = "self-budget-10pct"
    source: SourceItem
    threshold: float
    horizon_k: int
    stages: list[StageItem]
    timeline: list[TimelineEntry]
    explanation_global: ExplanationGlobalItem
    ground_truth: GroundTruthItem
    alarms: list[AlarmItem] = Field(default_factory=list)
    lead_time_summary: Optional[LeadTimeSummaryItem] = None
    mock: Optional[bool] = None
    dev_only: Optional[bool] = None
    note: Optional[str] = None


class FlowItem(BaseContractModel):
    ts: str
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    protocol: int
    flags: str
    pkts: int
    bytes: int
    duration_ms: float
    score: Optional[float] = None
    stage_hint: Optional[int] = None


class FlowsResponse(BaseContractModel):
    window: int
    total: int
    flows: list[FlowItem]
