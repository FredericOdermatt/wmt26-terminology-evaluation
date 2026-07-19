import re

# The laniqo CSVs and references contain stray zero-width spaces and double
# spaces; matching must be robust to them.
_ZERO_WIDTH = dict.fromkeys(map(ord, "​﻿"), None)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_ZERO_WIDTH)).strip().lower()


def find_spans(text: str, alternative: str) -> list[int]:
    """All occurrences of `alternative` in `text` as character-level binary
    masks (match_accuracy construction). Word boundaries use unicode \\w rather
    than the original ASCII class so accented letters block matches too."""
    if not alternative:
        return []
    pattern = r"(?<!\w)" + re.escape(alternative) + r"(?!\w)"
    masks = []
    for match in re.finditer(pattern, text, re.IGNORECASE):
        length = match.end() - match.start()
        masks.append(((1 << length) - 1) << (len(text) - match.end()))
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
