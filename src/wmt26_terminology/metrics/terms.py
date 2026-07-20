from collections import Counter
from typing import TYPE_CHECKING

from pydantic import BaseModel

from wmt26_terminology.metrics.matching import MaskSpace, max_disjoint, normalize
from wmt26_terminology.metrics.submission import Submission
from wmt26_terminology.schema import Paragraph, TestSet

if TYPE_CHECKING:
    from wmt26_terminology.metrics.lemma import Lemmatizer


class TermScores(BaseModel):
    """Rates over annotated term occurrences, matched word-boundary-anchored in
    the expected paragraph. The first four tiers judge occurrences
    independently; `exclusive_match` requires pairwise disjoint spans (maximal
    matching over base, inflection, and lemma candidates) and is the primary
    score."""

    occurrences: int
    base_match: float
    inflection_match: float
    lemma_match: float
    base_or_inflection_match: float
    exclusive_match: float


def _glossary_alternatives(test_set: TestSet) -> dict[str, list[str]]:
    if test_set.glossary is None:
        return {}
    return {normalize(entry.match_source): entry.targets + entry.targets_extra for entry in test_set.glossary.proper}


def _base_forms(term_source: str, term_target: str, alternatives: dict[str, list[str]]) -> set[str]:
    forms = {normalize(t) for t in alternatives.get(normalize(term_source), [])}
    forms.add(normalize(term_target))
    return forms


def _paragraph_pairs(test_set: TestSet, submission: Submission) -> list[tuple[Paragraph, str]]:
    return [
        (paragraph, normalize(hyp))
        for doc, hyp_paragraphs in zip(test_set.documents, submission.documents, strict=True)
        for paragraph, hyp in zip(doc.paragraphs, hyp_paragraphs, strict=True)
    ]


def _lemma_forms(
    pairs: list[tuple[Paragraph, str]], alternatives: dict[str, list[str]], lemmatizer: "Lemmatizer"
) -> dict[str, str]:
    forms: set[str] = set()
    for paragraph, _ in pairs:
        for segment in paragraph.segments:
            for term in segment.terms:
                forms |= _base_forms(term.source, term.target, alternatives)
    return lemmatizer.phrases(sorted(forms))


def _score_paragraph(
    space: MaskSpace,
    paragraph: Paragraph,
    alternatives: dict[str, list[str]],
    lemma_forms: dict[str, str],
    counts: Counter,
) -> list[list[int]]:
    requirements = []
    for segment in paragraph.segments:
        for term in segment.terms:
            counts["occurrences"] += 1
            base_forms = _base_forms(term.source, term.target, alternatives)
            base_spans = [mask for form in base_forms for mask in space.surface_masks(form)]
            inflection_spans = space.surface_masks(normalize(term.target_inflected)) if term.target_inflected else []
            lemma_spans = [
                mask for form in base_forms if (lemmatized := lemma_forms.get(form)) for mask in space.lemma_masks(lemmatized)
            ]
            counts["base"] += bool(base_spans)
            counts["inflection"] += bool(inflection_spans)
            counts["lemma"] += bool(lemma_spans)
            counts["either_surface"] += bool(base_spans or inflection_spans)
            requirements.append(base_spans + inflection_spans + lemma_spans)
    return requirements


def term_success(test_set: TestSet, submission: Submission, lemmatizer: "Lemmatizer | None" = None) -> TermScores | None:
    alternatives = _glossary_alternatives(test_set)
    pairs = _paragraph_pairs(test_set, submission)
    views = lemmatizer.views([hyp for _, hyp in pairs]) if lemmatizer else [None] * len(pairs)
    lemma_forms = _lemma_forms(pairs, alternatives, lemmatizer) if lemmatizer else {}

    counts: Counter = Counter()
    for (paragraph, hyp_norm), view in zip(pairs, views, strict=True):
        requirements = _score_paragraph(MaskSpace(hyp_norm, view), paragraph, alternatives, lemma_forms, counts)
        counts["exclusive"] += max_disjoint(requirements)
    total = counts["occurrences"]
    if not total:
        return None
    return TermScores(
        occurrences=total,
        base_match=counts["base"] / total,
        inflection_match=counts["inflection"] / total,
        lemma_match=counts["lemma"] / total,
        base_or_inflection_match=counts["either_surface"] / total,
        exclusive_match=counts["exclusive"] / total,
    )
