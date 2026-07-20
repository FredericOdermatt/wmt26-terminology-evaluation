import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wmt26_terminology.metrics.lemma import LemmaView

# The laniqo CSVs and references contain stray zero-width spaces and double
# spaces; matching must be robust to them.
_ZERO_WIDTH = dict.fromkeys(map(ord, "​﻿"), None)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_ZERO_WIDTH)).strip().lower()


def _char_spans(text: str, alternative: str) -> list[tuple[int, int]]:
    """Word-boundary-anchored occurrences, using unicode \\w rather than the
    original ASCII class so accented letters block matches too."""
    if not alternative:
        return []
    pattern = r"(?<!\w)" + re.escape(alternative) + r"(?!\w)"
    return [(m.start(), m.end()) for m in re.finditer(pattern, text, re.IGNORECASE)]


def _span_mask(text_length: int, start: int, end: int) -> int:
    return ((1 << (end - start)) - 1) << (text_length - end)


def find_spans(text: str, alternative: str) -> list[int]:
    """All occurrences of `alternative` in `text` as character-level binary
    masks (match_accuracy construction)."""
    return [_span_mask(len(text), start, end) for start, end in _char_spans(text, alternative)]


class MaskSpace:
    """Combined surface+lemma masks for one hypothesis paragraph: a match in
    either space also blocks the mapped span in the other, so exclusivity
    holds across spaces. Lemma bits sit above the surface bits."""

    def __init__(self, surface: str, view: "LemmaView | None") -> None:
        self.surface = surface
        self.view = view
        self._shift = len(surface) + 1

    def surface_masks(self, form: str) -> list[int]:
        masks = []
        for start, end in _char_spans(self.surface, form):
            mask = _span_mask(len(self.surface), start, end)
            if self.view is not None:
                for span in {self.view.to_lemma[i] for i in range(start, end)} - {None}:
                    mask |= _span_mask(len(self.view.lemma_text), *span) << self._shift
            masks.append(mask)
        return masks

    def lemma_masks(self, lemma_form: str) -> list[int]:
        if self.view is None:
            return []
        masks = []
        for start, end in _char_spans(self.view.lemma_text, lemma_form):
            mask = _span_mask(len(self.view.lemma_text), start, end) << self._shift
            for span in {self.view.to_surface[i] for i in range(start, end)} - {None}:
                mask |= _span_mask(len(self.surface), *span)
            masks.append(mask)
        return masks


def max_disjoint(requirements: list[list[int]]) -> int:
    """Maximum number of requirements satisfiable with pairwise disjoint spans.

    Computes the same quantity as match_accuracy's exhaustive top-down search
    (combinations x cartesian products), but with branch-and-bound so that
    paragraph-scale inputs (30+ occurrences) stay tractable.
    """
    active = sorted((r for r in requirements if r), key=len)
    n = len(active)
    best = 0

    def descend(index: int, used: int, count: int) -> None:
        nonlocal best
        best = max(best, count)
        if best == n or count + (n - index) <= best:
            return
        for mask in active[index]:
            if used & mask == 0:
                descend(index + 1, used | mask, count + 1)
        descend(index + 1, used, count)

    if n:
        descend(0, 0, 0)
    return best
