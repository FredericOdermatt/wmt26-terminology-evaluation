import json
import re
import unicodedata
from collections import OrderedDict
from pathlib import Path

from wmt26_terminology.schema import BitextSample, Document, Glossary, Paragraph, Segment, TermEntry, TermPair, TestSet

_DOMAINS = {"ME": "mechanical-engineering", "medical": "medical"}
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
                        segments=[
                            Segment(
                                source=r["en"],
                                reference=r["pl"],
                                terms=[
                                    TermPair(source=t["en"].strip(), target=t["pl"].strip())
                                    for t in (r.get("proper_terms") or [])
                                ],
                            )
                            for r in para
                        ],
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
    jsons_dir = original_root / "private" / "gold-data" / "doc-level" / "laniqo" / "jsons"
    test_sets = []
    for provider_domain, domain in _DOMAINS.items():
        rows = _load_rows(jsons_dir / f"WMT26_terminology_{provider_domain}.json")
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
                    BitextSample(
                        source=row["en"],
                        target=row["pl"],
                        document_id=row["document_id"],
                        terms=[
                            TermPair(source=t["en"].strip(), target=t["pl"].strip()) for t in (row.get("proper_terms") or [])
                        ],
                    )
                    for row in rows
                    if row["document_id"] in track2_ids and row["step"] == "extraction"
                ],
            )
        )
    return test_sets
