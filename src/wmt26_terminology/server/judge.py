import httpx

from wmt26_terminology.metrics.submission import Submission
from wmt26_terminology.schema import TestSet
from wmt26_terminology.server.config import settings

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "google/gemma-4-31b-it"

_PROMPT = """You are a professional translation quality rater.
Source paragraph ({source_lang}):
{source}

Candidate translation ({target_lang}):
{hypothesis}

Rate the translation quality on a 0-100 scale considering adequacy and fluency.
Answer with only the integer."""


async def judge_submission(test_set: TestSet, submission: Submission) -> dict:
    """Paragraph-level LLM-as-a-judge scores via OpenRouter. Disabled by
    default (settings.judge_enabled); sampling is pinned for reproducibility
    and the model slug is logged with the scores."""
    assert settings.judge_enabled and settings.openrouter_api_key
    scores: list[int] = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for doc, hyp_paragraphs in zip(test_set.documents, submission.documents, strict=True):
            for paragraph, hypothesis in zip(doc.paragraphs, hyp_paragraphs, strict=True):
                response = await client.post(
                    _OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                    json={
                        "model": _MODEL,
                        "temperature": 0,
                        "top_p": 1,
                        "messages": [
                            {
                                "role": "user",
                                "content": _PROMPT.format(
                                    source_lang=test_set.source_lang,
                                    target_lang=test_set.target_lang,
                                    source=paragraph.source,
                                    hypothesis=hypothesis,
                                ),
                            }
                        ],
                    },
                )
                content = response.json()["choices"][0]["message"]["content"].strip()
                scores.append(int(content) if content.isdigit() else 0)
    return {"model": _MODEL, "mean": sum(scores) / len(scores) if scores else None, "n": len(scores)}
