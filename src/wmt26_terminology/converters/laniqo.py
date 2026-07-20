import csv
import difflib
import json
import re
import unicodedata
from collections import OrderedDict
from pathlib import Path

from wmt26_terminology.schema import BitextSample, Document, Glossary, Paragraph, Segment, TermEntry, TermPair, TestSet

_DOMAINS = {"ME": "mechanical-engineering", "medical": "medical"}
_CSV_FILES = {
    "ME": "WMT26_terminlogy_testset1 - ALL_documents_sentences.csv",
    "medical": "WMT26_terminlogy_testset2 - ALL_documents_sentences.csv",
}
# Track split by position in first-appearance document order, mirroring the provider's build.py.
_TRACK1_DOC_SLICES = {"ME": slice(7, None), "medical": slice(0, 6)}

# Documented glossary typos released to competitors (reports/laniqo-data-issues.csv, issue 1).
_SOURCE_CLEAN_FIXES = {
    "acquired immune system)": "acquired immune system",
    "atrioventricular node (or AV node)": "atrioventricular node",
    "echocardiography.": "echocardiography",
    "lupus.": "lupus",
    "monoclonal antibody.": "monoclonal antibody",
}

# The postedit pass introduced "3,0" where the raw translation and the released
# build both have "3.0" (reports/laniqo-data-issues.csv, issue 3).
_REFERENCE_PATCHES = [("9- Ophthalmology & Otolaryngology", "3,0 OCENA", "3.0 OCENA")]

_SECTION_HEADER = re.compile(r"^\d+\.\d+")
_RECONCILE_THRESHOLD = 0.85


def _load_rows(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        # Document ids stem from macOS filenames and arrive NFD while the text is NFC.
        row["document_id"] = unicodedata.normalize("NFC", row["document_id"])
        row["en"] = row["en"].strip()
        row["pl"] = row["pl"].strip()
        for doc_id, bad_prefix, good_prefix in _REFERENCE_PATCHES:
            if row["document_id"] == doc_id and row["pl"].startswith(bad_prefix):
                row["pl"] = good_prefix + row["pl"][len(bad_prefix) :]
    return [row for row in rows if row["en"]]


_ZERO_WIDTH = dict.fromkeys(map(ord, "​﻿"), None)


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").translate(_ZERO_WIDTH)).strip()


def _split_terms(cell: str) -> list[str]:
    return [term for term in (part.strip() for part in (cell or "").split(",")) if term]


def _attach_inflections(rows: list[dict], csv_path: Path) -> None:
    """Join the annotation CSV's 'term (PL - inflection)' column onto the rows
    (same order, empty-EN rows dropped on both sides). The term columns are
    comma-separated and not always parallel (two EN synonyms may share one PL
    entry), so a base-form-keyed map is kept as fallback: base and inflection
    columns usually stay parallel even when the EN column does not
    (reports/laniqo-data-issues.csv, issue 9 discussion)."""
    csv_rows = [r for r in csv.DictReader(csv_path.open(newline="", encoding="utf-8")) if _norm_ws(r["source sentence (EN)"])]
    if len(csv_rows) != len(rows):
        return
    for row, csv_row in zip(rows, csv_rows, strict=True):
        if _norm_ws(csv_row["source sentence (EN)"]) != _norm_ws(row["en"]):
            continue
        en_terms = _split_terms(csv_row["term (EN)"])
        bases = _split_terms(csv_row["term (PL - base)"])
        inflected = _split_terms(csv_row["term (PL - inflection)"])
        if en_terms and len(en_terms) == len(inflected):
            row["inflections"] = {en.lower(): pl for en, pl in zip(en_terms, inflected, strict=True)}
        elif bases and len(bases) == len(inflected):
            row["inflections_by_base"] = {base.lower(): pl for base, pl in zip(bases, inflected, strict=True)}


def _reconcile_with_reference(form: str, reference: str) -> str | None:
    """Return the reference's actual rendering of `form`, tolerating small
    typos on either side ('rozrzędu' vs 'rozrządu', stray diacritics, double
    spaces; issue 9). `target_inflected` means "the surface form the reference
    used", so the reference span is authoritative when the two disagree."""
    form_norm = _norm_ws(form).lower()
    tokens = _norm_ws(reference).split()
    width = len(form_norm.split())
    best: tuple[float, str] | None = None
    for start in range(len(tokens) - width + 1):
        window = " ".join(tokens[start : start + width])
        candidate = window.strip(".,;:()!?\"'")
        ratio = difflib.SequenceMatcher(None, form_norm, candidate.lower()).ratio()
        if ratio >= _RECONCILE_THRESHOLD and (best is None or ratio > best[0]):
            best = (ratio, candidate)
    return best[1] if best else None


def _attested_form(term: dict, row: dict) -> str | None:
    inflections = row.get("inflections") or {}
    by_base = row.get("inflections_by_base") or {}
    candidate = inflections.get(term["en"].strip().lower()) or by_base.get(_norm_ws(term["pl"]).lower())
    if candidate is None or _norm_ws(candidate).lower() in _norm_ws(row["pl"]).lower():
        return candidate
    # Cell and reference disagree: reconcile typos to the reference span, but
    # keep the annotated form when the reference genuinely went another way
    # (synonym drift) - it remains a valid rendition for scoring submissions.
    return _reconcile_with_reference(candidate, row["pl"]) or candidate


def _term_pairs(row: dict) -> list[TermPair]:
    return [
        TermPair(source=t["en"].strip(), target=t["pl"].strip(), target_inflected=_attested_form(t, row))
        for t in (row.get("proper_terms") or [])
    ]


def _doc_order(rows: list[dict]) -> list[str]:
    return list(OrderedDict.fromkeys(row["document_id"] for row in rows))


def _build_documents(rows: list[dict], doc_ids: set[str]) -> list[Document]:
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for row in rows:
        if row["document_id"] in doc_ids:
            grouped.setdefault(row["document_id"], []).append(row)

    documents = []
    for doc_id, entries in grouped.items():
        paragraphs: list[list[dict]] = []
        for row in entries:
            if not paragraphs or _SECTION_HEADER.match(row["en"]):
                paragraphs.append([])
            paragraphs[-1].append(row)
        documents.append(
            Document(
                document_id=doc_id,
                paragraphs=[
                    Paragraph(
                        source=" ".join(r["en"] for r in para),
                        reference=" ".join(r["pl"] for r in para),
                        segments=[Segment(source=r["en"], reference=r["pl"], terms=_term_pairs(r)) for r in para],
                    )
                    for para in paragraphs
                ],
            )
        )
    return documents


def _load_glossary(public_terms_path: Path) -> Glossary:
    released = json.loads(public_terms_path.read_text(encoding="utf-8"))
    return Glossary(
        proper=[
            TermEntry(source=src, targets=targets, source_clean=_SOURCE_CLEAN_FIXES.get(src))
            for src, targets in released["proper"].items()
        ],
        random=[TermEntry(source=src, targets=targets) for src, targets in released["random"].items()],
    )


def convert(original_root: Path) -> list[TestSet]:
    laniqo_dir = original_root / "private" / "gold-data"
    jsons_dir = laniqo_dir / "doc-level" / "laniqo" / "jsons"
    test_sets = []
    for provider_domain, domain in _DOMAINS.items():
        rows = _load_rows(jsons_dir / f"WMT26_terminology_{provider_domain}.json")
        _attach_inflections(rows, laniqo_dir / "sentence-level" / "laniqo" / _CSV_FILES[provider_domain])
        order = _doc_order(rows)
        track1_ids = set(order[_TRACK1_DOC_SLICES[provider_domain]])

        common = {"provider": "laniqo", "pair": "enpl", "domain": domain, "source_lang": "en", "target_lang": "pl"}
        test_sets.append(
            TestSet(
                **common,
                track=1,
                paragraph_delimiter="\n\n",
                documents=_build_documents(rows, track1_ids),
                glossary=_load_glossary(original_root / "public" / "track1" / f"terms.{domain}.enpl.json"),
            )
        )
        track2_ids = set(order) - track1_ids
        test_sets.append(
            TestSet(
                **common,
                track=2,
                paragraph_delimiter="\n\n",
                documents=_build_documents(rows, track2_ids),
                samples=[
                    BitextSample(source=row["en"], target=row["pl"], document_id=row["document_id"], terms=_term_pairs(row))
                    for row in rows
                    if row["document_id"] in track2_ids and row["step"] == "extraction"
                ],
            )
        )
    return test_sets
