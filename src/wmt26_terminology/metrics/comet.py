# /// script
# requires-python = ">=3.12"
# dependencies = ["wmt26-terminology-evaluation[neural]"]
# ///
"""COMET family scorer on aligned segment units.

WMT26_API=... WMT26_SCORER_KEY=... python -m wmt26_terminology.metrics.comet --metric comet [--dry-run]
"""

import argparse
import platform
from importlib.metadata import version

import torch
from comet import load_from_checkpoint
from comet.models import CometModel

from wmt26_terminology.metrics.scorer_api import ScoreFn, ScorerClient
from wmt26_terminology.models import COMET_DA, Artifact, fetch_snapshot

NAME = "comet"
EXTERNAL = True
WORST_SCORE = 0.0

MODELS: dict[str, tuple[tuple[Artifact, ...], str, str]] = {
    # metric -> (artifacts, version posted to the portal, default precision)
    "comet": (COMET_DA, "wmt22-comet-da-seg", "fp32"),
}
_DTYPES = {"fp32": torch.float32, "fp16": torch.float16, "bf16": torch.bfloat16}


def load(metric: str, precision: str) -> CometModel:
    artifacts = MODELS[metric][0]
    model = load_from_checkpoint(str(fetch_snapshot(artifacts) / artifacts[0].filename))
    model.eval()
    return model.to(_DTYPES[precision])


def scorer(model: CometModel, batch_size: int) -> ScoreFn:
    def score(units: list[dict]) -> list[dict]:
        if not units:
            return []
        samples = [{"src": u["source"], "mt": u["hypothesis"], "ref": u["reference"]} for u in units]
        out = model.predict(samples, batch_size=batch_size, gpus=1, progress_bar=False)
        spans = (out.metadata or {}).get("error_spans") if hasattr(out, "metadata") else None
        scores = []
        for i, (unit, value) in enumerate(zip(units, out.scores, strict=True)):
            score = {"id": unit["id"], "value": float(value)}
            if spans and spans[i]:
                score["payload"] = {"error_spans": spans[i]}
            scores.append(score)
        return scores

    return score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metric", choices=sorted(MODELS), default="comet")
    parser.add_argument("--precision", choices=sorted(_DTYPES))
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--fetch", type=int, default=2000, help="units per API round trip")
    parser.add_argument("--dry-run", action="store_true", help="time one file, post nothing")
    args = parser.parse_args()
    artifacts, api_version, default_precision = MODELS[args.metric]
    precision = args.precision or default_precision
    model = load(args.metric, precision)
    score = scorer(model, args.batch_size)
    client = ScorerClient(args.metric, api_version)
    if args.dry_run:
        client.dry_run(score, limit=args.fetch)
        return
    meta = {
        "model": artifacts[0].repo,
        "revision": artifacts[0].revision,
        "unbabel_comet": version("unbabel-comet"),
        "torch": torch.__version__,
        "python": platform.python_version(),
        "precision": precision,
        "batch_size": args.batch_size,
        "level": "segment",
        "forced": f"empty and over-cap pieces take {WORST_SCORE}",
    }
    total = client.run(score, meta, WORST_SCORE, limit=args.fetch)
    print(f"done, {total} unit scores posted")


if __name__ == "__main__":
    main()
