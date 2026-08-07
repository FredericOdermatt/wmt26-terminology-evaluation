import json
import secrets
from typing import Annotated, NamedTuple

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from wmt26_terminology.schema import TestSet
from wmt26_terminology.server.config import settings
from wmt26_terminology.server.models import (
    EXTERNAL_METRIC_KEYS,
    ExternalScoresPost,
    ExternalScoresResult,
    SubmissionTriples,
    UnitScoreResult,
    WorkItem,
)
from wmt26_terminology.server.pb import PocketBase
from wmt26_terminology.server.submissions import TRACK_MODES, Slot
from wmt26_terminology.server.worker import upsert_score

_bearer = HTTPBearer()

_ID_PARTS = 7
_ID_SHAPE = "{system_id}:{track}:{mode}:{domain}:{direction}:{doc_idx}:{para_idx}"
_MAX_CONFLICTS_SHOWN = 5
_HTTP_UNPROCESSABLE = 422
_HTTP_CONFLICT = 409


def _check_worker_key(credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)]) -> None:
    if not settings.worker_api_key:
        raise HTTPException(503, "external scorer API is not configured")
    if not secrets.compare_digest(credentials.credentials.encode(), settings.worker_api_key.encode()):
        raise HTTPException(403, "invalid worker API key")


router = APIRouter(prefix="/v1/external", dependencies=[Depends(_check_worker_key)])


class _Unit(NamedTuple):
    system_id: str
    track: int
    mode: str
    domain: str
    direction: str


def _expected_units(test_sets: list[TestSet], track: int, direction: str) -> list[tuple[str, str]]:
    return sorted(
        (mode, ts.domain) for ts in test_sets if ts.track == track and ts.pair == direction for mode in TRACK_MODES[track]
    )


@router.get("/work")
async def work(request: Request) -> list[WorkItem]:
    """Every (system, track, direction) whose slots are all uploaded and valid,
    with per-metric counts of units already scored."""
    pb: PocketBase = request.app.state.pb
    test_sets: list[TestSet] = request.app.state.test_sets
    systems = {s["id"]: s for s in await pb.list("systems", "blocked = false")}
    files = await pb.list("submission_files", "valid = true")
    uploaded: dict[tuple[str, int, str], set[tuple[str, str]]] = {}
    for f in files:
        if f["system"] in systems:
            uploaded.setdefault((f["system"], f["track"], f["direction"]), set()).add((f["mode"], f["domain"]))
    scores: dict[tuple[str, int, str], list[dict]] = {}
    for s in await pb.list("scores"):
        scores.setdefault((s["system"], s["track"], s["direction"]), []).append(s.get("metrics") or {})

    items = []
    for (system_id, track, direction), have in sorted(uploaded.items()):
        expected = _expected_units(test_sets, track, direction)
        if not expected or set(expected) != have:
            continue
        unit_metrics = scores.get((system_id, track, direction), [])
        units_scored = {key: sum(1 for metrics in unit_metrics if metrics.get(key)) for key in EXTERNAL_METRIC_KEYS}
        items.append(
            WorkItem(
                system_id=system_id,
                system=systems[system_id]["name"],
                track=track,
                direction=direction,
                units_total=len(expected),
                units_scored=units_scored,
            )
        )
    return items


@router.get("/submissions/{track}/{system_id}/{direction}")
async def submission_triples(request: Request, track: int, system_id: str, direction: str) -> SubmissionTriples:
    """Parallel (id, source, hypothesis, reference) lists over all units of the
    direction. Paragraphs without a reference are dropped on both sides; ids
    keep the original document/paragraph indices."""
    pb: PocketBase = request.app.state.pb
    system = await pb.first("systems", f'id = "{system_id}"')
    if system is None or system.get("blocked"):
        raise HTTPException(404, "unknown system")
    test_sets: list[TestSet] = request.app.state.test_sets
    sets_by_domain = {ts.domain: ts for ts in test_sets if ts.track == track and ts.pair == direction}
    expected = _expected_units(test_sets, track, direction)
    if not expected:
        raise HTTPException(404, f"no test sets for track {track} direction {direction}")
    files = await pb.list(
        "submission_files", f'system = "{system_id}" && track = {track} && direction = "{direction}" && valid = true'
    )
    by_slot = {(f["mode"], f["domain"]): f for f in files}
    missing = [f"{mode}.{domain}" for mode, domain in expected if (mode, domain) not in by_slot]
    if missing:
        raise HTTPException(
            _HTTP_CONFLICT, f"direction {direction} is not complete for this system; missing: {', '.join(missing)}"
        )

    ids: list[str] = []
    source: list[str] = []
    hypothesis: list[str] = []
    reference: list[str] = []
    for mode, domain in expected:
        record = by_slot[mode, domain]
        documents = json.loads(await pb.file_bytes("submission_files", record, record["file"]))["documents"]
        for doc_idx, (doc, hyp_paragraphs) in enumerate(zip(sets_by_domain[domain].documents, documents, strict=True)):
            for para_idx, (paragraph, hyp) in enumerate(zip(doc.paragraphs, hyp_paragraphs, strict=True)):
                if paragraph.reference is None:
                    continue
                ids.append(f"{system_id}:{track}:{mode}:{domain}:{direction}:{doc_idx}:{para_idx}")
                source.append(paragraph.source)
                hypothesis.append(hyp)
                reference.append(paragraph.reference)
    return SubmissionTriples(
        system_id=system_id,
        system=system["name"],
        track=track,
        direction=direction,
        ids=ids,
        source=source,
        hypothesis=hypothesis,
        reference=reference,
    )


def _invalid_id(id_: str, reason: str) -> HTTPException:
    return HTTPException(_HTTP_UNPROCESSABLE, f"invalid id '{id_}': {reason} (expected {_ID_SHAPE})")


def _parse_id(id_: str, sets_by_key: dict[tuple[int, str, str], TestSet]) -> tuple[_Unit, str]:
    parts = id_.split(":")
    if len(parts) != _ID_PARTS:
        raise _invalid_id(id_, f"{len(parts)} colon-separated parts")
    system_id, track_raw, mode, domain, direction, doc_raw, para_raw = parts
    try:
        track, doc_idx, para_idx = int(track_raw), int(doc_raw), int(para_raw)
    except ValueError as error:
        raise _invalid_id(id_, "track/doc/para must be integers") from error
    test_set = sets_by_key.get((track, domain, direction))
    if test_set is None:
        raise _invalid_id(id_, f"no test set for track {track} domain '{domain}' direction '{direction}'")
    if mode not in TRACK_MODES[track]:
        raise _invalid_id(id_, f"mode '{mode}' is not valid for track {track}")
    if not 0 <= doc_idx < len(test_set.documents):
        raise _invalid_id(id_, f"document index out of range (0..{len(test_set.documents) - 1})")
    paragraphs = test_set.documents[doc_idx].paragraphs
    if not 0 <= para_idx < len(paragraphs):
        raise _invalid_id(id_, f"paragraph index out of range (0..{len(paragraphs) - 1})")
    if paragraphs[para_idx].reference is None:
        raise _invalid_id(id_, "paragraph has no reference and is not scored")
    return _Unit(system_id, track, mode, domain, direction), f"{doc_idx}:{para_idx}"


async def _existing_records(pb: PocketBase, units: dict[_Unit, dict[str, float]]) -> dict[_Unit, dict | None]:
    known_systems: set[str] = set()
    records: dict[_Unit, dict | None] = {}
    for unit in units:
        if unit.system_id not in known_systems:
            system = await pb.first("systems", f'id = "{unit.system_id}"')
            if system is None or system.get("blocked"):
                raise HTTPException(_HTTP_UNPROCESSABLE, f"unknown system '{unit.system_id}'")
            known_systems.add(unit.system_id)
        slot_filter = (
            f'system = "{unit.system_id}" && track = {unit.track} && mode = "{unit.mode}" '
            f'&& domain = "{unit.domain}" && direction = "{unit.direction}"'
        )
        if await pb.first("submission_files", f"{slot_filter} && valid = true") is None:
            raise HTTPException(
                _HTTP_UNPROCESSABLE,
                f"no valid submission for {unit.mode}.{unit.domain}.{unit.direction} of system '{unit.system_id}'",
            )
        records[unit] = await pb.first("scores", slot_filter)
    return records


def _require_no_conflicts(
    body: ExternalScoresPost, units: dict[_Unit, dict[str, float]], existing: dict[_Unit, dict | None]
) -> None:
    if body.danger_overwrite:
        return
    problems = []
    for unit, segments in sorted(units.items()):
        current = ((existing[unit] or {}).get("metrics") or {}).get(body.metric)
        if not current:
            continue
        label = f"{unit.mode}.{unit.domain}.{unit.direction}"
        overlap = sorted(set(segments) & set(current.get("segments", {})))
        if overlap:
            shown = ", ".join(overlap[:_MAX_CONFLICTS_SHOWN])
            extra = f" (+{len(overlap) - _MAX_CONFLICTS_SHOWN} more)" if len(overlap) > _MAX_CONFLICTS_SHOWN else ""
            problems.append(f"{label} already has scores for doc:para {shown}{extra}")
        elif current.get("meta") != body.meta:
            problems.append(f"{label} was scored with different meta {current.get('meta')}")
    if problems:
        raise HTTPException(
            _HTTP_CONFLICT,
            f"refusing to overwrite existing '{body.metric}' values: " + "; ".join(problems) + ". "
            "Pass danger_overwrite=true to overwrite deliberately.",
        )


@router.post("/scores")
async def post_scores(request: Request, body: ExternalScoresPost) -> ExternalScoresResult:
    """Idempotent per paragraph id; a subset of a unit's paragraphs is fine and
    later posts fill in the rest. The per-unit mean is recomputed over all
    segments stored so far."""
    pb: PocketBase = request.app.state.pb
    sets_by_key = {(ts.track, ts.domain, ts.pair): ts for ts in request.app.state.test_sets}
    units: dict[_Unit, dict[str, float]] = {}
    for id_, score in body.scores.items():
        unit, segment = _parse_id(id_, sets_by_key)
        units.setdefault(unit, {})[segment] = score

    existing = await _existing_records(pb, units)
    _require_no_conflicts(body, units, existing)

    results = []
    for unit, segments in sorted(units.items()):
        current = ((existing[unit] or {}).get("metrics") or {}).get(body.metric) or {}
        merged = {**current.get("segments", {}), **segments}
        mean = round(sum(merged.values()) / len(merged), 4)
        value = {"meta": body.meta, "segments": merged, "mean": mean, "n_segments": len(merged)}
        slot = Slot(track=unit.track, mode=unit.mode, domain=unit.domain, direction=unit.direction)
        await upsert_score(pb, unit.system_id, slot, {body.metric: value})
        results.append(
            UnitScoreResult(
                track=unit.track,
                mode=unit.mode,
                domain=unit.domain,
                direction=unit.direction,
                segments_written=len(segments),
                mean=mean,
            )
        )
    return ExternalScoresResult(
        metric=body.metric,
        units_updated=len(results),
        segments_written=sum(r.segments_written for r in results),
        units=results,
    )
