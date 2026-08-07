import json
from pathlib import Path

from pydantic import BaseModel, RootModel, ValidationInfo, model_validator

from wmt26_terminology.schema import TestSet


class Submission(BaseModel):
    system: str
    mode: str
    documents: list[list[str]]


def split_paragraphs(text: str) -> list[str]:
    # Mirrors the delimiter heuristic of the official validation-26.py.
    return text.split("\n\n") if "\n\n" in text else text.split("\n")


class SubmissionUpload(RootModel[list[str]]):
    """The competitor-facing submission file as the official validation-26.py
    accepts it: a JSON array with one string per translated document. Validate
    against a test set by passing it as context:
    `SubmissionUpload.model_validate(raw, context={"test_set": test_set})`."""

    @model_validator(mode="after")
    def _against_test_set(self, info: ValidationInfo) -> "SubmissionUpload":
        test_set: TestSet | None = (info.context or {}).get("test_set")
        if test_set is None:
            return self
        if len(self.root) != len(test_set.documents):
            raise ValueError(
                f"expected {len(test_set.documents)} documents (strings) as in the input file, got {len(self.root)}"
            )
        for index, (text, doc) in enumerate(zip(self.root, test_set.documents, strict=True)):
            paragraphs = split_paragraphs(text)
            if len(paragraphs) != len(doc.paragraphs):
                raise ValueError(
                    f"document {index}: expected {len(doc.paragraphs)} paragraphs as in the input file, "
                    f"got {len(paragraphs)} (paragraphs split on \\n\\n if present, else \\n)"
                )
        return self

    def paragraphs(self) -> list[list[str]]:
        return [split_paragraphs(text) for text in self.root]


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
