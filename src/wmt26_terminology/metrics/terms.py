from pydantic import BaseModel

from wmt26_terminology.metrics.matching import find_spans, max_disjoint, normalize
from wmt26_terminology.metrics.submission import Submission
from wmt26_terminology.schema import TestSet


class TermScores(BaseModel):
    """Rates over annotated term occurrences, matched word-boundary-anchored in
    the expected paragraph. `overlap_rate` allows span reuse across occurrences;
    `exclusive_rate` requires pairwise disjoint spans (maximal matching) and is
    the primary score."""

    occurrences: int
    base_rate: float
    attested_rate: float
    overlap_rate: float
    exclusive_rate: float


def _glossary_alternatives(test_set: TestSet) -> dict[str, list[str]]:
    if test_set.glossary is None:
        return {}
    return {normalize(entry.match_source): entry.targets for entry in test_set.glossary.proper}


def term_success(test_set: TestSet, submission: Submission) -> TermScores | None:
    alternatives = _glossary_alternatives(test_set)
    occurrences = base = attested = overlap = exclusive = 0
    for doc, hyp_paragraphs in zip(test_set.documents, submission.documents, strict=True):
        for paragraph, hyp in zip(doc.paragraphs, hyp_paragraphs, strict=True):
            hyp_norm = normalize(hyp)
            requirements = []
            for segment in paragraph.segments:
                for term in segment.terms:
                    occurrences += 1
                    base_forms = {normalize(t) for t in alternatives.get(normalize(term.source), [])}
                    base_forms.add(normalize(term.target))
                    base_spans = [span for form in base_forms for span in find_spans(hyp_norm, form)]
                    attested_spans = find_spans(hyp_norm, normalize(term.target_inflected)) if term.target_inflected else []
                    base += bool(base_spans)
                    attested += bool(attested_spans)
                    overlap += bool(base_spans or attested_spans)
                    requirements.append(base_spans + attested_spans)
            exclusive += max_disjoint(requirements)
    if not occurrences:
        return None
    return TermScores(
        occurrences=occurrences,
        base_rate=base / occurrences,
        attested_rate=attested / occurrences,
        overlap_rate=overlap / occurrences,
        exclusive_rate=exclusive / occurrences,
    )
