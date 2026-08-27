# /// script
# requires-python = ">=3.12"
# dependencies = ["unbabel-comet>=2.2.7", "httpx", "setuptools<81"]
# ///
# Async execution: WMT26_API=... WMT26_SCORER_KEY=... uv run src/wmt26_terminology/comet.py [--dry-run]

import argparse
import os
import platform
import sys
import time
from collections import defaultdict
from importlib.metadata import version

import httpx
import torch
from comet import download_model, load_from_checkpoint
from comet.models import CometModel

MODEL = os.environ.get("WMT26_COMET_MODEL", "Unbabel/wmt22-comet-da")
VERSION = os.environ.get("WMT26_COMET_VERSION", MODEL.rsplit("/", 1)[-1].lower())
METRIC = os.environ.get("WMT26_METRIC", "comet")
FETCH = int(os.environ.get("WMT26_FETCH", "1000"))
BATCH = int(os.environ.get("WMT26_BATCH", "256"))
# e.g. "zhen": document-level directions whose truncated units the model cannot score sanely.
SKIP_DIRECTIONS = {d for d in os.environ.get("WMT26_SKIP_DIRECTIONS", "").split(",") if d}

API = os.environ.get("WMT26_API", "http://127.0.0.1:8092")
KEY = os.environ["WMT26_SCORER_KEY"]

client = httpx.Client(base_url=API, headers={"authorization": f"Bearer {KEY}"}, timeout=300)


def load_model(precision: str) -> CometModel:
    model = load_from_checkpoint(download_model(MODEL))
    model.eval()
    if precision == "fp16":
        model.half()
    elif precision == "bf16":
        model.to(torch.bfloat16)
    return model


def score_batch(model: CometModel, units: list[dict]) -> list[dict]:
    """Empty hypotheses score 0 without a model call (COMET would give them ~0.3)."""
    scores, model_input, model_slots = [], [], []
    for i, u in enumerate(units):
        if not u["hypothesis"].strip():
            scores.append({"id": u["id"], "value": 0.0, "payload": {"forced_zero": "empty hypothesis"}})
        else:
            model_input.append({"src": u["source"], "mt": u["hypothesis"], "ref": u["reference"]})
            model_slots.append(i)
    if model_input:
        out = model.predict(model_input, batch_size=BATCH, gpus=1, progress_bar=False)
        spans = (out.metadata or {}).get("error_spans") if hasattr(out, "metadata") else None
        for j, (i, value) in enumerate(zip(model_slots, out.scores, strict=True)):
            score = {"id": units[i]["id"], "value": float(value)}
            if spans and spans[j]:
                score["payload"] = {"error_spans": spans[j]}
            scores.append(score)
    return scores


def meta(precision: str) -> dict:
    return {
        "model": MODEL,
        "unbabel_comet": version("unbabel-comet"),
        "python": platform.python_version(),
        "precision": precision,
        "batch_size": BATCH,
        "empty_hypotheses": "forced to 0.0 (Zouhar et al. 2024)",
    }


def dry_run(model: CometModel) -> None:
    """Time one file's worth of units end to end; nothing is posted."""
    units = client.get(
        "/v1/external/units", params={"metric": METRIC, "version": VERSION, "level": "paragraph", "limit": FETCH}
    ).json()
    by_file = defaultdict(list)
    for u in units:
        by_file[u["id"].split(":")[0]].append(u)
    file_units = next(iter(by_file.values()))
    label = f"{file_units[0]['system']} {file_units[0]['mode']}.{file_units[0]['domain']}.{file_units[0]['direction']}"
    empties = sum(1 for u in file_units if not u["hypothesis"].strip())
    start = time.time()
    scores = score_batch(model, file_units)
    elapsed = time.time() - start
    print(
        f"file {label}: {len(file_units)} units ({empties} empty), {elapsed:.1f}s "
        f"-> {elapsed / max(1, len(file_units) - empties) * 1000:.0f} ms/unit"
    )
    print("sample scores:", [round(s["value"], 4) for s in scores[:8]])


def run(model: CometModel, precision: str) -> None:
    total = 0
    while True:
        units = client.get(
            "/v1/external/units", params={"metric": METRIC, "version": VERSION, "level": "paragraph", "limit": FETCH}
        ).json()
        if not units:
            break
        units = [u for u in units if u["direction"] not in SKIP_DIRECTIONS]
        if not units:
            break
        scores = score_batch(model, units)
        response = client.post(
            "/v1/external/scores", json={"metric": METRIC, "version": VERSION, "meta": meta(precision), "scores": scores}
        )
        response.raise_for_status()
        total += response.json()["written"]
        print(f"posted {total} unit scores so far ({units[0]['system']} {units[0]['domain']}.{units[0]['direction']})")
    print(f"done, {total} unit scores posted")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="time one file, post nothing")
    parser.add_argument("--precision", choices=("fp16", "bf16", "fp32"), default=os.environ.get("WMT26_PRECISION", "fp16"))
    args = parser.parse_args()
    model = load_model(args.precision)
    if args.dry_run:
        dry_run(model)
    else:
        run(model, args.precision)


if __name__ == "__main__":
    sys.exit(main())
