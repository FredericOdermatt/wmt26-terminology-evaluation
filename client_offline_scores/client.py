# /// script
# requires-python = ">=3.10"
# dependencies = ["httpx"]
# ///
"""Example client for the WMT26 external scorer API.

    export WMT26_WORKER_API_KEY=...
    uv run client.py                        # list open work
    uv run client.py --metric comet         # score everything lacking COMET and post

Replace the compute_* stubs with real inference. Each receives parallel
per-paragraph lists (source, hypothesis, reference) and must return one float
per paragraph; return None for a paragraph to skip it (subsets are fine, later
runs fill in the rest). Already-scored values are never overwritten unless
--danger-overwrite is passed.
"""

import argparse
import os
from collections.abc import Sequence

import httpx

BASE_URL = os.environ.get("WMT26_API_URL", "https://wmt26.odermatt.dev/api")
API_KEY = os.environ.get("WMT26_WORKER_API_KEY", "")


def compute_comet(source: Sequence[str], hypothesis: Sequence[str], reference: Sequence[str]) -> list[float | None]:
    # Replace with e.g. Unbabel/wmt22-comet-da:
    #   model = load_from_checkpoint(download_model("Unbabel/wmt22-comet-da"))
    #   data = [{"src": s, "mt": h, "ref": r} for s, h, r in zip(source, hypothesis, reference)]
    #   return model.predict(data, batch_size=64, gpus=1).scores
    return [0.5 for _ in hypothesis]


def compute_metricx(source: Sequence[str], hypothesis: Sequence[str], reference: Sequence[str]) -> list[float | None]:
    # Replace with e.g. google/metricx-24-hybrid-xl-v2p6 (lower is better).
    return [5.0 for _ in hypothesis]


def compute_llm_judge_fsp(source: Sequence[str], hypothesis: Sequence[str], reference: Sequence[str]) -> list[float | None]:
    # Replace with the Focus Sentence Prompting judge.
    return [50.0 for _ in hypothesis]


METRICS = {
    "comet": (compute_comet, {"model": "dummy-comet", "note": "replace compute_comet"}),
    "metricx": (compute_metricx, {"model": "dummy-metricx", "note": "replace compute_metricx"}),
    "llm_judge_fsp": (compute_llm_judge_fsp, {"model": "dummy-fsp-judge", "note": "replace compute_llm_judge_fsp"}),
}


def _client() -> httpx.Client:
    if not API_KEY:
        raise SystemExit("set WMT26_WORKER_API_KEY")
    return httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=120.0)


def list_work(client: httpx.Client) -> list[dict]:
    response = client.get("/v1/external/work")
    response.raise_for_status()
    return response.json()


def fetch_submission(client: httpx.Client, track: int, system_id: str, direction: str) -> dict:
    response = client.get(f"/v1/external/submissions/{track}/{system_id}/{direction}")
    response.raise_for_status()
    return response.json()


def post_scores(
    client: httpx.Client, metric: str, meta: dict, scores: dict[str, float], danger_overwrite: bool = False
) -> dict:
    response = client.post(
        "/v1/external/scores",
        json={"metric": metric, "meta": meta, "scores": scores, "danger_overwrite": danger_overwrite},
    )
    if response.status_code == 409:
        raise SystemExit(f"conflict: {response.json()['detail']}")
    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metric", choices=sorted(METRICS))
    parser.add_argument("--danger-overwrite", action="store_true", help="overwrite values that are already set")
    args = parser.parse_args()

    with _client() as client:
        work = list_work(client)
        if args.metric is None:
            for item in work:
                print(f"track {item['track']} {item['direction']} {item['system']} ({item['system_id']}): "
                      f"{item['units_total']} units, scored {item['units_scored']}")
            return

        compute, meta = METRICS[args.metric]
        for item in work:
            if not args.danger_overwrite and item["units_scored"][args.metric] >= item["units_total"]:
                continue
            sub = fetch_submission(client, item["track"], item["system_id"], item["direction"])
            values = compute(sub["source"], sub["hypothesis"], sub["reference"])
            scores = {id_: value for id_, value in zip(sub["ids"], values) if value is not None}
            if not scores:
                continue
            result = post_scores(client, args.metric, meta, scores, args.danger_overwrite)
            print(f"{item['system']} {item['direction']}: wrote {result['segments_written']} segments "
                  f"across {result['units_updated']} units")


if __name__ == "__main__":
    main()
