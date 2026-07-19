import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from wmt26_terminology.metrics.chrf import document_chrf, paragraph_chrf
from wmt26_terminology.metrics.submission import Submission, load_submission
from wmt26_terminology.metrics.terms import TermScores, term_success
from wmt26_terminology.schema import TestSet

UNIFIED_PRIVATE = Path("data/unified") / "private"


class EvaluationResult(BaseModel):
    system: str
    mode: str
    provider: str
    domain: str
    pair: str
    track: int
    document_chrf: float
    paragraph_chrf: float
    terms: TermScores | None


def evaluate_submission(test_set: TestSet, submission: Submission) -> EvaluationResult:
    """Pure pydantic-in/pydantic-out so a future FastAPI service can wrap it directly."""
    return EvaluationResult(
        system=submission.system,
        mode=submission.mode,
        provider=test_set.provider,
        domain=test_set.domain,
        pair=test_set.pair,
        track=test_set.track,
        document_chrf=document_chrf(test_set, submission),
        paragraph_chrf=paragraph_chrf(test_set, submission),
        terms=term_success(test_set, submission),
    )


def load_test_sets() -> list[TestSet]:
    return [TestSet.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted(UNIFIED_PRIVATE.glob("*.json"))]


def oracle_submission(test_set: TestSet) -> Submission:
    documents = [[p.reference or "" for p in doc.paragraphs] for doc in test_set.documents]
    return Submission(system="oracle", mode="oracle", documents=documents)


def _results_for(test_set: TestSet, submissions_dir: Path | None) -> list[EvaluationResult]:
    if submissions_dir is None:
        return [evaluate_submission(test_set, oracle_submission(test_set))]
    paths = sorted(submissions_dir.glob(f"*.*.{test_set.domain}.{test_set.pair}.json"))
    return [evaluate_submission(test_set, load_submission(path, test_set)) for path in paths]


def _format_row(r: EvaluationResult) -> str:
    terms = "-"
    if r.terms:
        terms = f"{r.terms.base_rate:6.1%} {r.terms.attested_rate:9.1%} {r.terms.surface_rate:8.1%} n={r.terms.occurrences}"
    test_set = f"{r.pair} t{r.track} {r.domain}"
    return f"{test_set:<33} {r.system:<10} {r.mode:<8} {r.document_chrf:6.2f} {r.paragraph_chrf:6.2f}  {terms}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submissions", type=Path, help="folder with {system}.{mode}.{domain}.{pair}.json files")
    parser.add_argument("--oracle", action="store_true", help="score the references against themselves as a pipeline check")
    parser.add_argument("--track", type=int, choices=[1, 2])
    parser.add_argument("--json-out", type=Path, help="write results as JSON to this path")
    args = parser.parse_args()
    if args.oracle == (args.submissions is not None):
        parser.error("pass exactly one of --oracle or --submissions")

    print(f"{'set':<33} {'system':<10} {'mode':<8} {'docCF':>6} {'parCF':>6}  {'base':>6} {'attested':>9} {'surface':>8}")
    results = []
    for test_set in load_test_sets():
        if args.track and test_set.track != args.track:
            continue
        for result in _results_for(test_set, args.submissions):
            results.append(result)
            print(_format_row(result))
    if args.json_out:
        args.json_out.write_text(json.dumps([r.model_dump() for r in results], indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
