from typing import Literal

from pydantic import BaseModel, model_validator

Alignment = Literal["exact", "fuzzy", "unaligned"]

Provider = Literal["laniqo", "vicomtech", "hkma"]
LanguagePair = Literal["enpl", "eseu", "zhen"]


class TermPair(BaseModel):
    """`target` is the base/citation form as annotated by the provider;
    `target_inflected` is the surface form attested in the reference (laniqo:
    per-sentence CSV column; vicomtech: the eu-side term tag span)."""

    source: str
    target: str
    target_inflected: str | None = None


class TermEntry(BaseModel):
    """`source` is verbatim as released; `source_clean` is set only where a
    documented data issue exists (see reports/) and is the form to use for
    locating the term in the source text."""

    source: str
    targets: list[str]
    source_clean: str | None = None

    @property
    def match_source(self) -> str:
        return self.source_clean if self.source_clean is not None else self.source


class Segment(BaseModel):
    source: str
    reference: str | None = None
    terms: list[TermPair] = []


class Paragraph(BaseModel):
    """`alignment`/`seg_span` are set by converters that recover the paragraph
    from a provider-side segment stream (vicomtech): the released paragraph text
    was hand-edited after extraction, so provenance is recorded per paragraph."""

    source: str
    reference: str | None = None
    segments: list[Segment] = []
    alignment: Alignment | None = None
    seg_span: tuple[int, int] | None = None


class Document(BaseModel):
    document_id: str
    paragraphs: list[Paragraph]

    def source_text(self, delimiter: str) -> str:
        return delimiter.join(p.source for p in self.paragraphs)

    def reference_text(self, delimiter: str) -> str:
        assert all(p.reference is not None for p in self.paragraphs), "document has no complete reference"
        return delimiter.join(p.reference or "" for p in self.paragraphs)


class BitextSample(BaseModel):
    """A track-2 sample bitext pair; document_id and terms are private-side extras."""

    source: str
    target: str
    document_id: str | None = None
    terms: list[TermPair] = []


class Glossary(BaseModel):
    proper: list[TermEntry]
    random: list[TermEntry]


class TestSet(BaseModel):
    provider: Provider
    track: Literal[1, 2]
    pair: LanguagePair
    domain: str
    source_lang: str
    target_lang: str
    paragraph_delimiter: str | None
    documents: list[Document]
    glossary: Glossary | None = None
    samples: list[BitextSample] | None = None

    @model_validator(mode="after")
    def _track_payload(self) -> "TestSet":
        if self.track == 1 and self.glossary is None:
            raise ValueError("track 1 requires a glossary")
        if self.track != 1 and self.samples is None:
            raise ValueError("track 2 requires samples")
        return self

    def public_texts(self) -> list[str]:
        """The released `text.{domain}.{pair}.json` content."""
        delim = self.paragraph_delimiter
        if delim is None:
            assert all(len(d.paragraphs) == 1 for d in self.documents), "delimiter-less set must be single-paragraph"
            return [d.paragraphs[0].source for d in self.documents]
        return [d.source_text(delim) for d in self.documents]

    def public_terms(self) -> dict[str, dict[str, list[str]]]:
        """The released `terms.{domain}.{pair}.json` content (verbatim keys)."""
        assert self.glossary is not None
        return {
            mode: {e.source: e.targets for e in entries}
            for mode, entries in (("proper", self.glossary.proper), ("random", self.glossary.random))
        }

    def public_samples(self) -> list[dict[str, str]]:
        """The released `sample.{domain}.{pair}.json` content."""
        assert self.samples is not None
        return [{self.source_lang: s.source, self.target_lang: s.target} for s in self.samples]
