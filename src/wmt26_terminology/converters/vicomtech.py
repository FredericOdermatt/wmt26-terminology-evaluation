import difflib
import json
import re
from pathlib import Path

from wmt26_terminology.schema import BitextSample, Document, Glossary, Paragraph, Segment, TermEntry, TermPair, TestSet

_DOMAIN_TRACKS = {"energy": 1, "automotion": 1, "machine-tool": 2, "railways": 2}

_SEG_RE = re.compile(r'<seg id="(\d+)">\s?(.*?)\s?</seg>')
_TERM_RE = re.compile(r'<term src="([^"]*)" tgt="([^"]*)">')
_CITATION_RE = re.compile(r"\[\s*\d+\s*\]")

_FUZZY_THRESHOLD = 0.85
_MIN_ALIGNED_FRACTION = 0.97


def _read_segs(path: Path) -> dict[int, str]:
    return {
        int(m.group(1)): m.group(2)
        for line in path.read_text(encoding="utf-8").splitlines()
        if (m := _SEG_RE.match(line.strip()))
    }


def _strip_term_tags(seg: str) -> str:
    return re.sub(r"\s*</term>", "", re.sub(r"<term [^>]*>\s*", "", seg))


def _clean(seg: str) -> str:
    return re.sub(r"\s+", " ", _CITATION_RE.sub("", _strip_term_tags(seg))).strip()


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", _CITATION_RE.sub("", text))


def _detok(text: str) -> str:
    text = re.sub(r" ([,.;:!?%)\]»])", r"\1", text)
    return re.sub(r"([(\[«]) ", r"\1", text)


class _Aligner:
    """Maps released paragraphs back to contiguous spans of the provider seg stream.

    The release is a curated subset: citation markers were removed, 'Véase
    también' sections dropped, and some passages lightly rewritten, so matching
    is done in a whitespace- and citation-free space with a fuzzy fallback.
    """

    def __init__(self, segs: list[str]) -> None:
        self.norm_segs = [_norm(_strip_term_tags(s)) for s in segs]
        self.prefix_index: dict[str, list[int]] = {}
        for i, seg in enumerate(self.norm_segs):
            self.prefix_index.setdefault(seg[:20], []).append(i)
        self.pos: int | None = None

    def _candidates(self, norm_para: str) -> list[int]:
        cands = [] if self.pos is None else [self.pos]
        return cands + [c for c in self.prefix_index.get(norm_para[:20], []) if c not in cands]

    def _exact(self, norm_para: str) -> tuple[int, int] | None:
        for start in self._candidates(norm_para):
            acc, end = "", start
            while end < len(self.norm_segs) and len(acc) < len(norm_para):
                acc += self.norm_segs[end]
                end += 1
            if acc == norm_para:
                return start, end - 1
        return None

    def _fuzzy(self, norm_para: str) -> tuple[int, int] | None:
        best: tuple[float, int, int] | None = None
        candidates = self._candidates(norm_para)
        if not candidates:
            close = difflib.get_close_matches(norm_para, self.norm_segs, n=1, cutoff=_FUZZY_THRESHOLD)
            if close:
                candidates = [self.norm_segs.index(close[0])]
        for start in candidates:
            acc, end = "", start
            while end < len(self.norm_segs) and len(acc) < len(norm_para) * 0.9:
                acc += self.norm_segs[end]
                end += 1
            for stop in {end, end + 1, max(start + 1, end - 1)}:
                span = "".join(self.norm_segs[start:stop])
                if span:
                    ratio = difflib.SequenceMatcher(None, norm_para, span).ratio()
                    if best is None or ratio > best[0]:
                        best = (ratio, start, stop - 1)
        if best and best[0] >= _FUZZY_THRESHOLD:
            return best[1], best[2]
        return None

    def align(self, paragraph: str) -> tuple[str, tuple[int, int] | None]:
        norm_para = _norm(paragraph)
        if span := self._exact(norm_para):
            self.pos = span[1] + 1
            return "exact", span
        if span := self._fuzzy(norm_para):
            self.pos = span[1] + 1
            return "fuzzy", span
        self.pos = None
        return "unaligned", None


def _reference_for(paragraph: str, es_clean: list[str], eu_clean: dict[int, str], span: tuple[int, int]) -> str:
    """Mirror onto the eu side whichever spacing transform reproduces the
    released es paragraph; the release mixes raw and detokenized spacing."""
    start, end = span
    es_joined = " ".join(es_clean[start : end + 1])
    eu_joined = " ".join(eu_clean[i] for i in range(start, end + 1) if i in eu_clean)
    if es_joined == paragraph:
        return eu_joined
    return _detok(eu_joined)


def _build_documents(
    domain: str, released_docs: list[str], es_segs: list[str], es_clean: list[str], eu_clean: dict[int, str]
) -> list[Document]:
    aligner = _Aligner(es_segs)
    documents = []
    counts = {"exact": 0, "fuzzy": 0, "unaligned": 0}
    for doc_index, released_doc in enumerate(released_docs):
        paragraphs = []
        for para_text in released_doc.split("\n"):
            alignment, span = aligner.align(para_text)
            counts[alignment] += 1
            segments = []
            reference = None
            if span is not None:
                reference = _reference_for(para_text, es_clean, eu_clean, span)
                segments = [
                    Segment(
                        source=es_clean[i],
                        reference=eu_clean.get(i),
                        terms=[TermPair(source=s, target=t) for s, t in _TERM_RE.findall(es_segs[i])],
                    )
                    for i in range(span[0], span[1] + 1)
                ]
            paragraphs.append(
                Paragraph(source=para_text, reference=reference, segments=segments, alignment=alignment, seg_span=span)
            )
        documents.append(Document(document_id=f"{domain}-doc{doc_index:02d}", paragraphs=paragraphs))

    aligned_fraction = (counts["exact"] + counts["fuzzy"]) / sum(counts.values())
    print(f"vicomtech {domain}: {counts['exact']} exact, {counts['fuzzy']} fuzzy, {counts['unaligned']} unaligned paragraphs")
    assert aligned_fraction >= _MIN_ALIGNED_FRACTION, f"{domain}: only {aligned_fraction:.1%} of paragraphs aligned"
    return documents


def _load_glossary(path: Path) -> Glossary:
    released_terms = json.loads(path.read_text(encoding="utf-8"))
    return Glossary(
        proper=[TermEntry(source=src, targets=tgts) for src, tgts in released_terms["proper"].items()],
        random=[TermEntry(source=src, targets=tgts) for src, tgts in released_terms["random"].items()],
    )


def _load_samples(path: Path) -> list[BitextSample]:
    return [BitextSample(source=s["es"], target=s["eu"]) for s in json.loads(path.read_text(encoding="utf-8"))]


def _convert_domain(domain: str, track: int, original_root: Path) -> TestSet:
    stem = domain.replace("-", "_")
    seg_dir = original_root / "private" / "gold-data" / "sentence-level" / "vicomtech" / domain
    public = original_root / "public" / f"track{track}"
    es_by_id = _read_segs(seg_dir / f"{stem}.es2eu_annotated.es")
    assert sorted(es_by_id) == list(range(len(es_by_id))), f"{domain}: es seg ids not contiguous"
    es_segs = [es_by_id[i] for i in range(len(es_by_id))]
    # The eu side may have gaps (railways is missing seg 1741, an untranslated heading).
    eu_clean = {i: _clean(s) for i, s in _read_segs(seg_dir / f"{stem}.es2eu_annotated.eu").items()}
    released_docs = json.loads((public / f"text.{domain}.eseu.json").read_text(encoding="utf-8"))
    documents = _build_documents(domain, released_docs, es_segs, [_clean(s) for s in es_segs], eu_clean)
    return TestSet(
        provider="vicomtech",
        track=track,
        pair="eseu",
        domain=domain,
        source_lang="es",
        target_lang="eu",
        paragraph_delimiter="\n",
        documents=documents,
        glossary=_load_glossary(public / f"terms.{domain}.eseu.json") if track == 1 else None,
        samples=_load_samples(public / f"sample.{domain}.eseu.json") if track != 1 else None,
    )


def convert(original_root: Path) -> list[TestSet]:
    return [_convert_domain(domain, track, original_root) for domain, track in _DOMAIN_TRACKS.items()]
