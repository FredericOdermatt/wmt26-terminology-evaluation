# WMT26 Terminology Shared Task

Evaluation tooling for the [WMT26 terminology shared task](https://www2.statmt.org/wmt26/terminology.html):
document-level MT with terminology guidance for en→pl, es→eu (tracks 1 and 2) and zh→en (track 2).

- `data/public/`: the released competitor-facing data and the official validation script
- `data/unified/`: unified test sets **with gold data**

```bash
make install
make evaluate-gold                                # score the references against themselves
make evaluate SUBMISSIONS=dir OUT=results         # score {system}.{mode}.{domain}.{pair}.json files
```

## Neural metrics

COMET-22, CometKiwi-22, XCOMET-XXL and MetricX-24 XL are scored on aligned segments: gold source and
reference segments come from the providers, the hypothesis paragraph is cut onto them with
[mweralign](https://github.com/mjpost/mweralign) (`src/wmt26_terminology/units.py`). Every checkpoint is
pinned by Hugging Face revision and sha256 in `src/wmt26_terminology/models.py`. The scorer clients in
`src/wmt26_terminology/metrics/comet.py` and `metrics/metricx.py` fetch units from the portal, score them
on a GPU and post the values back:

```bash
uv venv --python 3.12 && uv pip install -e ".[neural]"
WMT26_API=... WMT26_SCORER_KEY=... python -m wmt26_terminology.metrics.comet --metric comet
```

CometKiwi and XCOMET are gated on Hugging Face: accept the license on the model page and log in with
`hf auth login`. torch compiles a small CUDA helper at first use, which needs the Python development
headers; a uv-managed Python (`uv python install 3.12`) ships them, a bare system Python may not.

