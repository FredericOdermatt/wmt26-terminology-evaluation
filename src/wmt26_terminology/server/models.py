from typing import Literal

from pydantic import BaseModel, Field, model_validator

ExternalMetric = Literal["comet", "metricx", "llm_judge_fsp"]
# Displayed as COMET, MetricX and LLM Judge (Focus Sentence Prompting).
EXTERNAL_METRIC_KEYS: tuple[str, ...] = ("comet", "metricx", "llm_judge_fsp")


class SystemCreate(BaseModel):
    email: str = Field(max_length=200)
    turnstile_token: str = ""
    # Honeypot: real users never fill this hidden field.
    website: str = ""


class SystemCreated(BaseModel):
    id: str
    token: str


class SlotView(BaseModel):
    track: int
    mode: str
    domain: str
    direction: str
    expected_filename: str
    status: str  # missing | valid | invalid
    error: str | None = None


class EvaluationView(BaseModel):
    id: str
    track: int
    status: str
    stage: str
    percentage: int
    error: str | None = None


class SystemView(BaseModel):
    id: str
    name: str
    # True until the first accepted upload names the system.
    pending: bool
    slots: list[SlotView]
    evaluations: list[EvaluationView]


class UploadVerdict(BaseModel):
    filename: str
    accepted: bool
    track: int | None = None
    mode: str | None = None
    domain: str | None = None
    direction: str | None = None
    error: str | None = None
    track_complete: bool = False
    system: SystemView


class MetricBlock(BaseModel):
    chrf_doc: float | None = None
    chrf_para: float | None = None
    exact_term_success: float | None = None
    lemma_term_success: float | None = None
    judge_score: float | None = None


class LeaderboardRow(BaseModel):
    system: str
    track: int
    mode: str
    directions: dict[str, MetricBlock]
    # Per metric, filled only when every direction that can produce the metric
    # has a value; otherwise the leaderboard shows per-direction values only.
    overall: MetricBlock


class WorkItem(BaseModel):
    system_id: str
    system: str
    track: int
    direction: str
    units_total: int
    # Per external metric: how many of the units already carry it.
    units_scored: dict[str, int]


class SubmissionTriples(BaseModel):
    """Parallel per-paragraph lists over every (mode, domain) unit of one
    complete (system, track, direction); ids carry the unit and indices."""

    system_id: str
    system: str
    track: int
    direction: str
    ids: list[str]
    source: list[str]
    hypothesis: list[str]
    reference: list[str]

    @model_validator(mode="after")
    def _parallel(self) -> "SubmissionTriples":
        lengths = {len(self.ids), len(self.source), len(self.hypothesis), len(self.reference)}
        if len(lengths) > 1:
            raise ValueError("ids/source/hypothesis/reference must be parallel lists of equal length")
        return self


class ExternalScoresPost(BaseModel):
    metric: ExternalMetric
    # Model name/checkpoint + settings, stored verbatim next to the scores.
    meta: dict = Field(min_length=1)
    # Paragraph id -> score; any subset of the ids served by GET /submissions.
    scores: dict[str, float] = Field(min_length=1)
    danger_overwrite: bool = False


class UnitScoreResult(BaseModel):
    track: int
    mode: str
    domain: str
    direction: str
    segments_written: int
    mean: float


class ExternalScoresResult(BaseModel):
    metric: str
    units_updated: int
    segments_written: int
    units: list[UnitScoreResult]


class EvaluateRequest(BaseModel):
    track: int


class Meta(BaseModel):
    tracks: dict[int, list[str]]  # track -> expected {mode}.{domain}.{direction} suffixes
    track_directions: dict[int, list[str]]
