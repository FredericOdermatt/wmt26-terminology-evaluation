from pydantic import BaseModel, Field


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


class LeaderboardRow(BaseModel):
    system: str
    track: int
    mode: str
    chrf_doc: float | None = None
    chrf_para: float | None = None
    exact_term_success: float | None = None
    lemma_term_success: float | None = None
    sets_scored: int


class Meta(BaseModel):
    tracks: dict[int, list[str]]  # track -> expected {mode}.{domain}.{direction} suffixes
