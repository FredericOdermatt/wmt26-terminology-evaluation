import json
from pathlib import Path

from wmt26_terminology.converters import laniqo
from wmt26_terminology.schema import TestSet

ORIGINAL = Path("data/original")
UNIFIED_PRIVATE = Path("data/unified") / "private"


def _assert_matches_release(ts: TestSet) -> None:
    public = ORIGINAL / "public" / f"track{ts.track}"

    def released(prefix: str) -> object:
        return json.loads((public / f"{prefix}.{ts.domain}.{ts.pair}.json").read_text(encoding="utf-8"))

    assert ts.public_texts() == released("text"), f"text mismatch: {ts.domain} track{ts.track}"
    if ts.glossary is not None:
        assert ts.public_terms() == released("terms"), f"terms mismatch: {ts.domain} track{ts.track}"
    if ts.samples is not None:
        assert ts.public_samples() == released("sample"), f"samples mismatch: {ts.domain} track{ts.track}"


def main() -> None:
    UNIFIED_PRIVATE.mkdir(parents=True, exist_ok=True)
    for ts in laniqo.convert(ORIGINAL):
        _assert_matches_release(ts)
        out = UNIFIED_PRIVATE / f"{ts.provider}.{ts.domain}.{ts.pair}.track{ts.track}.json"
        out.write_text(ts.model_dump_json(indent=2), encoding="utf-8")
        print(f"verified against release, wrote {out}")


if __name__ == "__main__":
    main()
