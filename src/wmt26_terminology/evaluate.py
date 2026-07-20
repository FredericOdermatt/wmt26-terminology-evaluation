import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from wmt26_terminology.metrics.chrf import document_chrf, paragraph_chrf
from wmt26_terminology.metrics.lemma import Lemmatizer
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


def evaluate_submission(test_set: TestSet, submission: Submission, lemmatizer: Lemmatizer | None = None) -> EvaluationResult:
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
        terms=term_success(test_set, submission, lemmatizer),
    )


def _lemmatizer_for(test_set: TestSet, cache: dict, skip: bool) -> Lemmatizer | None:
    has_terms = test_set.glossary is not None or any(
        s.terms for d in test_set.documents for p in d.paragraphs for s in p.segments
    )
    if skip or not has_terms:
        return None
    if test_set.target_lang not in cache:
        cache[test_set.target_lang] = Lemmatizer(test_set.target_lang)
    return cache[test_set.target_lang]


def load_test_sets() -> list[TestSet]:
    return [TestSet.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted(UNIFIED_PRIVATE.glob("*.json"))]


def oracle_submission(test_set: TestSet) -> Submission:
    documents = [[p.reference or "" for p in doc.paragraphs] for doc in test_set.documents]
    return Submission(system="oracle", mode="oracle", documents=documents)


def _results_for(test_set: TestSet, submissions_dir: Path | None, lemmatizer: Lemmatizer | None) -> list[EvaluationResult]:
    if submissions_dir is None:
        return [evaluate_submission(test_set, oracle_submission(test_set), lemmatizer)]
    paths = sorted(submissions_dir.glob(f"*.*.{test_set.domain}.{test_set.pair}.json"))
    return [evaluate_submission(test_set, load_submission(path, test_set), lemmatizer) for path in paths]


def _format_row(r: EvaluationResult) -> str:
    terms = "-"
    if r.terms:
        t = r.terms
        terms = (
            f"{t.base_match:6.1%} {t.inflection_match:9.1%} {t.lemma_match:6.1%} "
            f"{t.base_or_inflection_match:8.1%} {t.exclusive_match:8.1%} n={t.occurrences}"
        )
    test_set = f"{r.pair} t{r.track} {r.domain}"
    return f"{test_set:<33} {r.system:<10} {r.mode:<8} {r.document_chrf:6.2f} {r.paragraph_chrf:6.2f}  {terms}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submissions", type=Path, help="folder with {system}.{mode}.{domain}.{pair}.json files")
    parser.add_argument("--oracle", action="store_true", help="score the references against themselves as a pipeline check")
    parser.add_argument("--track", type=int, choices=[1, 2])
    parser.add_argument("--json-out", type=Path, help="write results as JSON to this path")
    parser.add_argument("--skip-lemma", action="store_true", help="skip the stanza lemma tier (faster)")
    args = parser.parse_args()
    if args.oracle == (args.submissions is not None):
        parser.error("pass exactly one of --oracle or --submissions")

    print(
        f"{'set':<33} {'system':<10} {'mode':<8} {'docCF':>6} {'parCF':>6}  "
        f"{'base':>6} {'inflectn':>9} {'lemma':>6} {'either':>8} {'exclusiv':>8}"
    )
    results = []
    lemmatizers: dict = {}
    for test_set in load_test_sets():
        if args.track and test_set.track != args.track:
            continue
        lemmatizer = _lemmatizer_for(test_set, lemmatizers, args.skip_lemma)
        for result in _results_for(test_set, args.submissions, lemmatizer):
            results.append(result)
            print(_format_row(result))
    if args.json_out:
        args.json_out.write_text(json.dumps([r.model_dump() for r in results], indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
