import json
from pathlib import Path

from pydantic import BaseModel

from wmt26_terminology.schema import TestSet


class Submission(BaseModel):
    system: str
    mode: str
    documents: list[list[str]]


def split_paragraphs(text: str) -> list[str]:
    # Mirrors the delimiter heuristic of the official validation-26.py.
    return text.split("\n\n") if "\n\n" in text else text.split("\n")


def load_submission(path: Path, test_set: TestSet) -> Submission:
    system, mode = path.name.split(".")[:2]
    raw = json.loads(path.read_text(encoding="utf-8"))
    if len(raw) != len(test_set.documents):
        raise ValueError(f"{path.name}: {len(raw)} documents, expected {len(test_set.documents)}")
    documents = []
    for index, (text, doc) in enumerate(zip(raw, test_set.documents, strict=True)):
        paragraphs = split_paragraphs(text)
        if len(paragraphs) != len(doc.paragraphs):
            raise ValueError(f"{path.name} doc {index}: {len(paragraphs)} paragraphs, expected {len(doc.paragraphs)}")
        documents.append(paragraphs)
    return Submission(system=system, mode=mode, documents=documents)
