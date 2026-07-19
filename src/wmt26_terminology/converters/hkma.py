import json
from pathlib import Path

from wmt26_terminology.schema import BitextSample, Document, Paragraph, TestSet

# The released text collapsed a double space present in the provider data (doc 11, seg 4);
# the released form is canonical.
_SOURCE_PATCHES = [((11, 4), "-  為", "- 為")]


def convert(original_root: Path) -> list[TestSet]:
    rows = [
        json.loads(line)
        for line in (original_root / "private" / "gold-data" / "doc-level" / "hkma" / "test_with_ref.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    for row in rows:
        for (doc, seg), bad, good in _SOURCE_PATCHES:
            if row["doc"] == doc and row["seg"] == seg:
                row["zh"] = row["zh"].replace(bad, good, 1)

    # Competitors see each (doc, seg) row as an independent single-paragraph document;
    # the true document grouping is retained in the document_id.
    documents = [
        Document(
            document_id=f"doc{row['doc']}-seg{row['seg']}",
            paragraphs=[Paragraph(source=row["zh"], reference=row["en"])],
        )
        for row in rows
    ]
    samples = [
        BitextSample(source=s["zh"], target=s["en"])
        for s in json.loads((original_root / "public" / "track2" / "sample.finance.zhen.json").read_text(encoding="utf-8"))
    ]
    return [
        TestSet(
            provider="hkma",
            track=2,
            pair="zhen",
            domain="finance",
            source_lang="zh",
            target_lang="en",
            paragraph_delimiter=None,
            documents=documents,
            samples=samples,
        )
    ]
