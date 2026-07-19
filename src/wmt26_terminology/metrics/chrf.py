from sacrebleu.metrics import CHRF

from wmt26_terminology.metrics.submission import Submission
from wmt26_terminology.schema import TestSet

_CHRF = CHRF(word_order=2)


def _aligned_paragraphs(test_set: TestSet, submission: Submission) -> list[list[tuple[str, str]]]:
    """Per document: (reference, hypothesis) paragraph pairs, dropping the few
    paragraphs without a recoverable reference on both sides."""
    per_document = []
    for doc, hyp_paragraphs in zip(test_set.documents, submission.documents, strict=True):
        pairs = [
            (paragraph.reference, hyp)
            for paragraph, hyp in zip(doc.paragraphs, hyp_paragraphs, strict=True)
            if paragraph.reference is not None
        ]
        per_document.append(pairs)
    return per_document


def document_chrf(test_set: TestSet, submission: Submission) -> float:
    delimiter = test_set.paragraph_delimiter or "\n"
    references, hypotheses = [], []
    for pairs in _aligned_paragraphs(test_set, submission):
        if pairs:
            references.append(delimiter.join(ref for ref, _ in pairs))
            hypotheses.append(delimiter.join(hyp for _, hyp in pairs))
    return _CHRF.corpus_score(hypotheses, [references]).score


def paragraph_chrf(test_set: TestSet, submission: Submission) -> float:
    flat = [pair for pairs in _aligned_paragraphs(test_set, submission) for pair in pairs]
    return _CHRF.corpus_score([hyp for _, hyp in flat], [[ref for ref, _ in flat]]).score
