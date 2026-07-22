import hashlib
import io
import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from wmt26_terminology.evaluate import load_test_sets
from wmt26_terminology.server import turnstile
from wmt26_terminology.server.config import settings
from wmt26_terminology.server.models import (
    EvaluationView,
    LeaderboardRow,
    Meta,
    SlotView,
    SystemCreate,
    SystemCreated,
    SystemView,
    UploadVerdict,
)
from wmt26_terminology.server.pb import PocketBase
from wmt26_terminology.server.ratelimit import limiter
from wmt26_terminology.server.submissions import ParsedUpload, UploadError, expected_slots, parse_upload
from wmt26_terminology.server.worker import Evaluator

_bearer = HTTPBearer()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.pb = PocketBase()
    app.state.test_sets = load_test_sets(Path(settings.unified_data_dir))
    app.state.slots = expected_slots(app.state.test_sets)
    app.state.evaluator = Evaluator(app.state.pb, app.state.test_sets)
    await app.state.evaluator.start()
    try:
        yield
    finally:
        await app.state.pb.close()


app = FastAPI(title="WMT26 Terminology Submission API", lifespan=_lifespan)


async def _authed_system(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)], system_id: str
) -> dict:
    pb: PocketBase = request.app.state.pb
    system = await pb.first("systems", f'id = "{system_id}"')
    if system is None or system.get("blocked"):
        raise HTTPException(404, "unknown system")
    if not secrets.compare_digest(system["token_hash"], _hash(credentials.credentials)):
        raise HTTPException(403, "invalid token for this system")
    return system


async def _system_view(request: Request, system: dict) -> SystemView:
    pb: PocketBase = request.app.state.pb
    files = await pb.list("submission_files", f'system = "{system["id"]}"')
    by_slot = {(f["track"], f["mode"], f["domain"], f["direction"]): f for f in files}
    slots = []
    for slot in request.app.state.slots:
        record = by_slot.get((slot.track, slot.mode, slot.domain, slot.direction))
        status = "missing" if record is None else ("valid" if record["valid"] else "invalid")
        slots.append(
            SlotView(
                track=slot.track,
                mode=slot.mode,
                domain=slot.domain,
                direction=slot.direction,
                expected_filename=f"{system['name']}.{slot.filename_suffix}",
                status=status,
                error=(record or {}).get("error") or None,
            )
        )
    evaluations = [
        EvaluationView(
            id=e["id"],
            track=e["track"],
            status=e["status"],
            stage=e["stage"],
            percentage=e["percentage"],
            error=e.get("error") or None,
        )
        for e in await pb.list("evaluations", f'system = "{system["id"]}"', sort="created")
    ]
    return SystemView(id=system["id"], name=system["name"], slots=slots, evaluations=evaluations)


@app.get("/v1/meta")
async def meta(request: Request) -> Meta:
    tracks: dict[int, list[str]] = {}
    for slot in request.app.state.slots:
        tracks.setdefault(slot.track, []).append(slot.filename_suffix)
    return Meta(tracks=tracks)


@app.post("/v1/systems")
async def create_system(request: Request, body: SystemCreate) -> SystemCreated:
    ip = _client_ip(request)
    if body.website:
        raise HTTPException(400, "rejected")
    if not limiter.allow(f"create:{ip}", settings.systems_per_ip_per_hour, 3600):
        raise HTTPException(429, "too many systems created from this address; try again later")
    if not await turnstile.verify(body.turnstile_token, ip):
        raise HTTPException(400, "turnstile verification failed")
    pb: PocketBase = request.app.state.pb
    if await pb.first("systems", f'name = "{body.name}"'):
        raise HTTPException(409, f"system name '{body.name}' is already taken")
    token = secrets.token_urlsafe(32)
    record = await pb.create("systems", {"name": body.name, "email": body.email, "token_hash": _hash(token), "blocked": False})
    return SystemCreated(id=record["id"], name=body.name, token=token)


@app.get("/v1/systems/{system_id}")
async def get_system(request: Request, system_id: str) -> SystemView:
    pb: PocketBase = request.app.state.pb
    system = await pb.first("systems", f'id = "{system_id}"')
    if system is None or system.get("blocked"):
        raise HTTPException(404, "unknown system")
    return await _system_view(request, system)


@app.post("/v1/systems/{system_id}/files")
async def upload_file(
    request: Request, system_id: str, file: UploadFile, credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)]
) -> UploadVerdict:
    system = await _authed_system(request, credentials, system_id)
    ip = _client_ip(request)
    if not limiter.allow(f"upload:{ip}", settings.uploads_per_ip_per_minute, 60):
        raise HTTPException(429, "too many uploads; slow down")
    if not limiter.allow(f"uploads:{system_id}", settings.uploads_per_system_per_day, 86400):
        raise HTTPException(429, "daily upload quota for this system reached")
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, f"file exceeds {settings.max_upload_bytes // 1024 // 1024} MB")

    filename = file.filename or ""
    try:
        parsed = parse_upload(filename, content, request.app.state.test_sets)
        if parsed.system != system["name"]:
            raise UploadError(f"file is named for system '{parsed.system}' but you are uploading to '{system['name']}'")
    except UploadError as upload_error:
        return UploadVerdict(
            filename=filename, accepted=False, error=upload_error.message, system=await _system_view(request, system)
        )
    return await _store_upload(request, system, filename, parsed)


async def _store_upload(request: Request, system: dict, filename: str, parsed: ParsedUpload) -> UploadVerdict:
    pb: PocketBase = request.app.state.pb
    slot = parsed.slot
    canonical = json.dumps({"documents": parsed.documents}, ensure_ascii=False).encode()
    data = {
        "system": system["id"],
        "track": slot.track,
        "mode": slot.mode,
        "domain": slot.domain,
        "direction": slot.direction,
        "valid": True,
        "error": "",
    }
    files = {"file": (filename, io.BytesIO(canonical), "application/json")}
    slot_filter = (
        f'system = "{system["id"]}" && track = {slot.track} && mode = "{slot.mode}" '
        f'&& domain = "{slot.domain}" && direction = "{slot.direction}"'
    )
    existing = await pb.first("submission_files", slot_filter)
    if existing:
        await pb.update("submission_files", existing["id"], data, files=files)
    else:
        await pb.create("submission_files", data, files=files)

    view = await _system_view(request, system)
    complete = all(s.status == "valid" for s in view.slots if s.track == slot.track)
    if complete:
        await request.app.state.evaluator.enqueue(system["id"], slot.track)
        view = await _system_view(request, system)
    return UploadVerdict(
        filename=filename,
        accepted=True,
        track=slot.track,
        mode=slot.mode,
        domain=slot.domain,
        direction=slot.direction,
        track_complete=complete,
        system=view,
    )


@app.get("/v1/evaluations/{evaluation_id}")
async def get_evaluation(request: Request, evaluation_id: str) -> EvaluationView:
    pb: PocketBase = request.app.state.pb
    record = await pb.first("evaluations", f'id = "{evaluation_id}"')
    if record is None:
        raise HTTPException(404, "unknown evaluation")
    return EvaluationView(
        id=record["id"],
        track=record["track"],
        status=record["status"],
        stage=record["stage"],
        percentage=record["percentage"],
        error=record.get("error") or None,
    )


@app.get("/v1/leaderboard")
async def leaderboard(request: Request) -> list[LeaderboardRow]:
    pb: PocketBase = request.app.state.pb
    systems = {s["id"]: s for s in await pb.list("systems", "blocked = false")}
    rows: dict[tuple[str, int, str], list[dict]] = {}
    for score in await pb.list("scores"):
        if score["system"] not in systems:
            continue
        rows.setdefault((score["system"], score["track"], score["mode"]), []).append(score["metrics"])

    def _mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    result = []
    for (system_id, track, mode), metrics in sorted(rows.items()):
        exact = [m["exact"]["exclusive_match"] for m in metrics if m.get("exact")]
        lemma = [m["lemma"]["exclusive_match"] for m in metrics if m.get("lemma")]
        result.append(
            LeaderboardRow(
                system=systems[system_id]["name"],
                track=track,
                mode=mode,
                chrf_doc=_mean([m["chrf_doc"] for m in metrics if "chrf_doc" in m]),
                chrf_para=_mean([m["chrf_para"] for m in metrics if "chrf_para" in m]),
                exact_term_success=_mean(exact),
                lemma_term_success=_mean(lemma),
                sets_scored=len(metrics),
            )
        )
    return result
