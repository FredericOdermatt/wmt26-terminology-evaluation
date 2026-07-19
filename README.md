# WMT26 Terminology Shared Task — Evaluation

Evaluation tooling for the [WMT26 terminology shared task](https://www2.statmt.org/wmt26/terminology.html):
document-level MT with terminology guidance for en→pl, es→eu, and zh→en.

- `data/original/public/` — released competitor-facing data and the official validation script
- `data/original/private/` — provider gold data (git-ignored, synced separately)
- `data/unified/` — generated unified datasets, verified against the public release on conversion
- `reports/` — data issue reports for the providing teams

## Usage

```bash
make install
make convert-datasets
```
