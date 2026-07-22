import asyncio
import re

import httpx

from wmt26_terminology.metrics.submission import Submission
from wmt26_terminology.schema import TestSet
from wmt26_terminology.server.config import settings

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "google/gemma-4-31b-it"
# Pinned provider for reproducible scoring; bf16 to avoid quantization drift.
_PROVIDER = {"order": ["wandb"], "allow_fallbacks": False, "quantizations": ["bf16"]}
_CONCURRENCY = 8
_MAX_TOKENS = 2000
_SCORE_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*$")

_PROMPT = """A system was asked to translate the following document from {source_lang} to {target_lang}.

```document
{source}
```
{dict_section}
It produced the following translation:

```output
{hypothesis}
```

Reason briefly about the quality of the translation and its terminology usage, then score.
Your final line must contain only a single number from 0 to 100, where 0 is given for poor
translations that make no or wrong use of the terminology and 100 is the best score, for
translations that translate perfectly using the given terminology."""

_DICT_SECTION = """
It was given the following terminology dictionary:

```dict
{entries}
```
"""


def _dict_section(test_set: TestSet, mode: str) -> str:
    if test_set.glossary is None or mode not in {"proper", "random"}:
        return ""
    entries = getattr(test_set.glossary, mode)
    lines = "\n".join(f"{entry.source}: {'; '.join(entry.targets)}" for entry in entries)
    return _DICT_SECTION.format(entries=lines)


def _parse_score(text: str) -> float | None:
    match = _SCORE_RE.search(text.strip())
    if not match:
        return None
    score = float(match.group(1))
    return score if 0 <= score <= 100 else None


async def _judge_document(client: httpx.AsyncClient, prompt: str) -> float | None:
    payload = {
        "model": _MODEL,
        "provider": _PROVIDER,
        "reasoning": {"enabled": True},
        "temperature": 0,
        "top_p": 1,
        "seed": 42,
        "max_tokens": _MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    for attempt in range(2):
        try:
            response = await client.post(
                _OPENROUTER_URL,
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return _parse_score(content)
        except (httpx.HTTPError, KeyError, IndexError):
            if attempt == 1:
                return None
            await asyncio.sleep(3)
    return None


async def judge_submission(test_set: TestSet, submission: Submission, mode: str) -> dict:
    """Document-level LLM-as-a-judge scores (0-100) via OpenRouter. Sampling
    and provider are pinned and recorded with the scores; the prompt is a
    first iteration and will be refined."""
    delimiter = test_set.paragraph_delimiter or "\n"
    dict_section = _dict_section(test_set, mode)
    prompts = [
        _PROMPT.format(
            source_lang=test_set.source_lang,
            target_lang=test_set.target_lang,
            source=doc.source_text(delimiter),
            dict_section=dict_section,
            hypothesis=delimiter.join(hyp_paragraphs),
        )
        for doc, hyp_paragraphs in zip(test_set.documents, submission.documents, strict=True)
    ]
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(timeout=180.0) as client:

        async def bounded(prompt: str) -> float | None:
            async with semaphore:
                return await _judge_document(client, prompt)

        results = await asyncio.gather(*(bounded(prompt) for prompt in prompts))
    scores = [score for score in results if score is not None]
    return {
        "model": _MODEL,
        "provider": "wandb/bf16",
        "reasoning": True,
        "seed": 42,
        "mean": round(sum(scores) / len(scores), 2) if scores else None,
        "documents": results,
        "n_failed": sum(1 for score in results if score is None),
    }
