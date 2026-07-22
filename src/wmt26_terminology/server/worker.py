import asyncio
import gc
import json

from wmt26_terminology.metrics.chrf import document_chrf, paragraph_chrf
from wmt26_terminology.metrics.lemma import Lemmatizer
from wmt26_terminology.metrics.submission import Submission
from wmt26_terminology.metrics.terms import term_success
from wmt26_terminology.schema import TestSet
from wmt26_terminology.server.pb import PocketBase
from wmt26_terminology.server.submissions import TRACK_MODES

# A lemma unit costs roughly this many exact units of wall time; used only
# for smooth progress percentages.
_LEMMA_WEIGHT = 8


class Evaluator:
    """Single sequential evaluation queue. State lives in the `evaluations`
    collection so a restart resumes anything left QUEUED or RUNNING."""

    def __init__(self, pb: PocketBase, test_sets: list[TestSet]) -> None:
        self._pb = pb
        self._test_sets = test_sets
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        for record in await self._pb.list("evaluations", 'status = "QUEUED" || status = "RUNNING"', sort="created"):
            await self._queue.put(record["id"])
        self._task = asyncio.create_task(self._run())

    async def enqueue(self, system_id: str, track: int) -> dict:
        existing = await self._pb.first(
            "evaluations", f'system = "{system_id}" && track = {track} && (status = "QUEUED" || status = "RUNNING")'
        )
        if existing:
            return existing
        record = await self._pb.create(
            "evaluations", {"system": system_id, "track": track, "status": "QUEUED", "percentage": 0, "stage": ""}
        )
        await self._queue.put(record["id"])
        return record

    async def _run(self) -> None:
        while True:
            evaluation_id = await self._queue.get()
            try:
                await self._evaluate(evaluation_id)
            except Exception as error:
                await self._pb.update("evaluations", evaluation_id, {"status": "FAILED", "error": str(error)[:500]})

    async def _load_submissions(self, system_id: str, track: int) -> dict[tuple[str, str, str], Submission]:
        system = await self._pb.first("systems", f'id = "{system_id}"')
        assert system is not None
        files = await self._pb.list("submission_files", f'system = "{system_id}" && track = {track} && valid = true')
        submissions = {}
        for record in files:
            content = await self._pb.file_bytes("submission_files", record, record["file"])
            documents = json.loads(content)["documents"]
            submissions[record["mode"], record["domain"], record["direction"]] = Submission(
                system=system["name"], mode=record["mode"], documents=documents
            )
        return submissions

    async def _upsert_score(self, system_id: str, test_set: TestSet, mode: str, metrics: dict) -> None:
        filter_ = (
            f'system = "{system_id}" && track = {test_set.track} && domain = "{test_set.domain}" '
            f'&& direction = "{test_set.pair}" && mode = "{mode}"'
        )
        existing = await self._pb.first("scores", filter_)
        if existing:
            merged = {**existing.get("metrics", {}), **metrics}
            await self._pb.update("scores", existing["id"], {"metrics": merged})
        else:
            await self._pb.create(
                "scores",
                {
                    "system": system_id,
                    "track": test_set.track,
                    "domain": test_set.domain,
                    "direction": test_set.pair,
                    "mode": mode,
                    "metrics": metrics,
                },
            )

    async def _evaluate(self, evaluation_id: str) -> None:
        record = await self._pb.first("evaluations", f'id = "{evaluation_id}"')
        assert record is not None
        system_id, track = record["system"], record["track"]
        track_sets = [ts for ts in self._test_sets if ts.track == track]
        submissions = await self._load_submissions(system_id, track)
        units = [(ts, mode) for ts in track_sets for mode in TRACK_MODES[track] if (mode, ts.domain, ts.pair) in submissions]
        lemma_units = [(ts, mode) for ts, mode in units if ts.target_lang in {"pl", "eu"}]
        total = len(units) + _LEMMA_WEIGHT * len(lemma_units)
        done = 0

        async def progress(stage: str) -> None:
            await self._pb.update(
                "evaluations",
                evaluation_id,
                {"status": "RUNNING", "stage": stage, "percentage": round(100 * done / total)},
            )

        await progress("exact")
        for test_set, mode in units:
            submission = submissions[mode, test_set.domain, test_set.pair]
            scores = await asyncio.to_thread(self._exact_metrics, test_set, submission)
            await self._upsert_score(system_id, test_set, mode, scores)
            done += 1
            await progress("exact")

        for lang in ("pl", "eu"):
            lang_units = [(ts, mode) for ts, mode in lemma_units if ts.target_lang == lang]
            if not lang_units:
                continue
            await progress(f"lemma-{lang}")
            lemmatizer = await asyncio.to_thread(self._make_lemmatizer, lang)
            for test_set, mode in lang_units:
                submission = submissions[mode, test_set.domain, test_set.pair]
                scores = await asyncio.to_thread(self._lemma_metrics, test_set, submission, lemmatizer)
                await self._upsert_score(system_id, test_set, mode, scores)
                done += _LEMMA_WEIGHT
                await progress(f"lemma-{lang}")
            del lemmatizer
            gc.collect()

        # Judge stage (LLM as a judge via OpenRouter) is prepared but disabled:
        # if settings.judge_enabled:
        #     from wmt26_terminology.server.judge import judge_submission
        #     for test_set, mode in units:
        #         verdicts = await judge_submission(test_set, submissions[(mode, test_set.domain, test_set.pair)])
        #         await self._upsert_score(system_id, test_set, mode, {"judge": verdicts})

        await self._pb.update("evaluations", evaluation_id, {"status": "DONE", "percentage": 100, "stage": "done"})

    @staticmethod
    def _exact_metrics(test_set: TestSet, submission: Submission) -> dict:
        terms = term_success(test_set, submission)
        return {
            "chrf_doc": round(document_chrf(test_set, submission), 2),
            "chrf_para": round(paragraph_chrf(test_set, submission), 2),
            "exact": terms.model_dump() if terms else None,
        }

    @staticmethod
    def _make_lemmatizer(lang: str) -> Lemmatizer:
        return Lemmatizer(lang)

    @staticmethod
    def _lemma_metrics(test_set: TestSet, submission: Submission, lemmatizer: Lemmatizer) -> dict:
        terms = term_success(test_set, submission, lemmatizer)
        return {"lemma": terms.model_dump() if terms else None}
