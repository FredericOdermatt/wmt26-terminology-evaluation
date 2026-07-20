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
    (combinations x cartesian products), with three additions to stay tractable
    at paragraph scale: repeated occurrences of the same term have identical
    candidate sets and are assigned as index-increasing subsets (combinations,
    not permutations), a greedy assignment seeds the bound, and a node budget
    caps pathological instances (returning the best assignment found, a lower
    bound of the true maximum).
    """
    groups: dict[tuple[int, ...], int] = {}
    for requirement in requirements:
        if requirement:
            key = tuple(sorted(set(requirement)))
            groups[key] = groups.get(key, 0) + 1
    items = sorted(((list(masks), count) for masks, count in groups.items()), key=lambda item: len(item[0]))
    capacity = [min(len(masks), count) for masks, count in items]
    suffix = [0] * (len(items) + 1)
    for i in range(len(items) - 1, -1, -1):
        suffix[i] = suffix[i + 1] + capacity[i]
    n = sum(count for _, count in items)

    best = 0
    used_greedy = 0
    for masks, count in items:
        for mask in masks:
            if count == 0:
                break
            if used_greedy & mask == 0:
                used_greedy |= mask
                count -= 1
                best += 1

    budget = 1_000_000

    def descend(group: int, mask_index: int, picks_left: int, used: int, count: int) -> None:
        nonlocal best, budget
        best = max(best, count)
        if best == n or budget <= 0:
            return
        budget -= 1
        if group == len(items):
            return
        masks, _ = items[group]
        if picks_left == 0 or mask_index == len(masks):
            descend(group + 1, 0, items[group + 1][1] if group + 1 < len(items) else 0, used, count)
            return
        if count + min(picks_left, len(masks) - mask_index) + suffix[group + 1] <= best:
            return
        mask = masks[mask_index]
        if used & mask == 0:
            descend(group, mask_index + 1, picks_left - 1, used | mask, count + 1)
        descend(group, mask_index + 1, picks_left, used, count)

    if items:
        descend(0, 0, items[0][1], 0, 0)
    return best
