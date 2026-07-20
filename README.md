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
make convert-datasets                    # build data/unified/ from data/original/, verified against the release
make evaluate SUBMISSIONS=path/to/dir    # score {system}.{mode}.{domain}.{pair}.json files
make evaluate-oracle                     # score the references against themselves (pipeline self-check)
```

Evaluation reports document- and paragraph-level chrF++ plus term success rates
(base / inflection / lemma tiers and exclusive maximal matching; see
docs/term-matching.md). Pass `--skip-lemma` to `wmt26_terminology.evaluate` to
skip the stanza lemma tier.
