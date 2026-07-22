import json

from pydantic import BaseModel

from wmt26_terminology.metrics.submission import Submission, split_paragraphs
from wmt26_terminology.schema import TestSet

TRACK_MODES = {1: ("noterm", "proper", "random"), 2: ("noterm", "sample")}
_FILENAME_PARTS = 5


class Slot(BaseModel):
    track: int
    mode: str
    domain: str
    direction: str

    @property
    def filename_suffix(self) -> str:
        return f"{self.mode}.{self.domain}.{self.direction}.json"


class ParsedUpload(BaseModel):
    system: str
    slot: Slot
    documents: list[list[str]]


class UploadError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def expected_slots(test_sets: list[TestSet]) -> list[Slot]:
    return [
        Slot(track=ts.track, mode=mode, domain=ts.domain, direction=ts.pair)
        for ts in test_sets
        for mode in TRACK_MODES[ts.track]
    ]


def _candidate_tracks(test_sets: list[TestSet], mode: str, domain: str, direction: str) -> list[TestSet]:
    return [ts for ts in test_sets if ts.domain == domain and ts.pair == direction and mode in TRACK_MODES[ts.track]]


def _validate_documents(raw: object, test_set: TestSet) -> list[list[str]] | str:
    """Returns parsed paragraphs per document, or a human-readable problem."""
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        return "the file must be a JSON list of strings (one string per translated document)"
    if len(raw) != len(test_set.documents):
        return f"expected {len(test_set.documents)} documents (strings) as in the input file, got {len(raw)}"
    documents = []
    for index, (text, doc) in enumerate(zip(raw, test_set.documents, strict=True)):
        paragraphs = split_paragraphs(text)
        if len(paragraphs) != len(doc.paragraphs):
            return (
                f"document {index}: expected {len(doc.paragraphs)} paragraphs as in the input file, "
                f"got {len(paragraphs)} (paragraphs split on \\n\\n if present, else \\n)"
            )
        documents.append(paragraphs)
    return documents


def parse_upload(filename: str, content: bytes, test_sets: list[TestSet]) -> ParsedUpload:
    """Parses {system}.{mode}.{domain}.{direction}.json and validates the
    content against the matching test set. The track is inferred from the
    slot; a noterm enpl file could belong to either track, so both candidates
    are tried and the validating one wins."""
    parts = filename.split(".")
    if len(parts) != _FILENAME_PARTS or parts[4] != "json":
        raise UploadError(
            f"file name '{filename}' does not match the expected pattern {{system}}.{{mode}}.{{domain}}.{{direction}}.json"
        )
    system, mode, domain, direction = parts[:4]
    all_modes = {m for modes in TRACK_MODES.values() for m in modes}
    if mode not in all_modes:
        raise UploadError(f"unknown mode '{mode}'; expected one of {sorted(all_modes)}")
    candidates = _candidate_tracks(test_sets, mode, domain, direction)
    if not candidates:
        known = sorted({f"{ts.domain}.{ts.pair}" for ts in test_sets})
        raise UploadError(f"unknown domain/direction '{domain}.{direction}' for mode '{mode}'; expected one of {known}")

    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UploadError(f"not valid UTF-8 JSON: {error}") from error

    problems = []
    for test_set in candidates:
        result = _validate_documents(raw, test_set)
        if isinstance(result, list):
            slot = Slot(track=test_set.track, mode=mode, domain=domain, direction=direction)
            return ParsedUpload(system=system, slot=slot, documents=result)
        problems.append(f"track {test_set.track}: {result}")
    raise UploadError("; ".join(problems))


def to_submission(system: str, mode: str, documents: list[list[str]]) -> Submission:
    return Submission(system=system, mode=mode, documents=documents)
