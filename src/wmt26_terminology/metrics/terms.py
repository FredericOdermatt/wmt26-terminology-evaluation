from pydantic import BaseModel

from wmt26_terminology.metrics.submission import Submission
from wmt26_terminology.schema import TestSet


class TermScores(BaseModel):
    occurrences: int
    base_rate: float
    attested_rate: float
    surface_rate: float


def _glossary_alternatives(test_set: TestSet) -> dict[str, list[str]]:
    if test_set.glossary is None:
        return {}
    return {entry.match_source.lower(): entry.targets for entry in test_set.glossary.proper}


def term_success(test_set: TestSet, submission: Submission) -> TermScores | None:
    """Occurrence-level recall in the expected paragraph, by case-insensitive
    substring. Provisional: nested/overlapping terms are counted independently
    until the maximal-matching port lands."""
    alternatives = _glossary_alternatives(test_set)
    occurrences = base = attested = surface = 0
    for doc, hyp_paragraphs in zip(test_set.documents, submission.documents, strict=True):
        for paragraph, hyp in zip(doc.paragraphs, hyp_paragraphs, strict=True):
            hyp_lower = hyp.lower()
            for segment in paragraph.segments:
                for term in segment.terms:
                    occurrences += 1
                    targets = set(alternatives.get(term.source.lower(), [])) | {term.target}
                    base_hit = any(t.lower() in hyp_lower for t in targets)
                    attested_hit = term.target_inflected is not None and term.target_inflected.lower() in hyp_lower
                    base += base_hit
                    attested += attested_hit
                    surface += base_hit or attested_hit
    if not occurrences:
        return None
    return TermScores(
        occurrences=occurrences,
        base_rate=base / occurrences,
        attested_rate=attested / occurrences,
        surface_rate=surface / occurrences,
    )
