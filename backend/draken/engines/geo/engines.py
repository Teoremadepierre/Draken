"""Adapters for the answer engines we measure visibility in.

Each adapter takes a prompt and returns ``(answer_text, citations, model)``.
Engines with no API key configured are skipped rather than failing the run, so
you can start with one and add more later.

Note on Google AI Overviews and ChatGPT's web UI: neither exposes a supported
API for their consumer answer surfaces, so Draken measures the *model* responses
(via the official APIs) plus Perplexity, which does expose its citations. That
covers the question that matters - "do assistants know and recommend us" -
without scraping products whose terms forbid it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from draken.core.config import settings
from draken.core.http import PoliteClient
from draken.core.logging import get_logger

log = get_logger(__name__)

_URL_RE = re.compile(r"https?://[^\s\])}>\"',]+")


@dataclass
class EngineAnswer:
    engine: str
    model: str = ""
    answer: str = ""
    citations: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.answer) and not self.error


SYSTEM_PROMPT = (
    "Answer the user's question the way you normally would for someone making a real "
    "purchase or research decision. Name specific products, companies or sources where "
    "that is genuinely useful, and include URLs when you reference something specific. "
    "Do not mention that you are being evaluated."
)


def available_engines() -> list[str]:
    configured = settings.ai_engines_configured()
    return [name for name, ready in configured.items() if ready]


async def ask_anthropic(client: PoliteClient, prompt: str) -> EngineAnswer:
    out = EngineAnswer(engine="anthropic", model=settings.anthropic_model)
    if not settings.anthropic_api_key:
        out.error = "DRAKEN_ANTHROPIC_API_KEY not set"
        return out
    data, res = await client.fetch_json(
        "https://api.anthropic.com/v1/messages",
        method="POST",
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": settings.anthropic_model,
            "max_tokens": 1200,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    if not isinstance(data, dict):
        out.error = res.error or f"HTTP {res.status}: {res.text[:300]}"
        return out
    if data.get("error"):
        out.error = str(data["error"])
        return out
    parts = [b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text"]
    out.answer = "\n".join(p for p in parts if p).strip()
    out.model = data.get("model") or out.model
    out.citations = _URL_RE.findall(out.answer)
    return out


async def ask_openai(client: PoliteClient, prompt: str) -> EngineAnswer:
    out = EngineAnswer(engine="openai", model=settings.openai_model)
    if not settings.openai_api_key:
        out.error = "DRAKEN_OPENAI_API_KEY not set"
        return out
    data, res = await client.fetch_json(
        "https://api.openai.com/v1/chat/completions",
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.openai_model,
            "max_tokens": 1200,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
    )
    if not isinstance(data, dict):
        out.error = res.error or f"HTTP {res.status}: {res.text[:300]}"
        return out
    if data.get("error"):
        out.error = str(data["error"].get("message", data["error"]))
        return out
    try:
        out.answer = (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        out.error = "unexpected response shape"
        return out
    out.model = data.get("model") or out.model
    out.citations = _URL_RE.findall(out.answer)
    return out


async def ask_perplexity(client: PoliteClient, prompt: str) -> EngineAnswer:
    """Perplexity is the most informative engine here: it returns its sources."""
    out = EngineAnswer(engine="perplexity", model="sonar")
    if not settings.perplexity_api_key:
        out.error = "DRAKEN_PERPLEXITY_API_KEY not set"
        return out
    data, res = await client.fetch_json(
        "https://api.perplexity.ai/chat/completions",
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.perplexity_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "sonar",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
    )
    if not isinstance(data, dict):
        out.error = res.error or f"HTTP {res.status}: {res.text[:300]}"
        return out
    if data.get("error"):
        out.error = str(data["error"])
        return out
    try:
        out.answer = (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        out.error = "unexpected response shape"
        return out
    out.model = data.get("model") or out.model
    # Perplexity returns the grounding sources separately - the useful part.
    out.citations = list(data.get("citations") or []) or _URL_RE.findall(out.answer)
    return out


async def ask_gemini(client: PoliteClient, prompt: str) -> EngineAnswer:
    out = EngineAnswer(engine="gemini", model="gemini-2.0-flash")
    if not settings.gemini_api_key:
        out.error = "DRAKEN_GEMINI_API_KEY not set"
        return out
    data, res = await client.fetch_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{out.model}:generateContent",
        method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": settings.gemini_api_key},
        json={
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
        },
    )
    if not isinstance(data, dict):
        out.error = res.error or f"HTTP {res.status}: {res.text[:300]}"
        return out
    if data.get("error"):
        out.error = str(data["error"].get("message", data["error"]))
        return out
    try:
        parts = data["candidates"][0]["content"]["parts"]
        out.answer = "\n".join(p.get("text", "") for p in parts).strip()
    except Exception:
        out.error = "unexpected response shape"
        return out
    out.citations = _URL_RE.findall(out.answer)
    return out


ENGINES = {
    "anthropic": ask_anthropic,
    "openai": ask_openai,
    "perplexity": ask_perplexity,
    "gemini": ask_gemini,
}


async def ask_all(
    prompt: str, *, engines: list[str] | None = None
) -> list[EngineAnswer]:
    import asyncio

    names = [e for e in (engines or available_engines()) if e in ENGINES]
    if not names:
        return [
            EngineAnswer(
                engine="none",
                error=(
                    "No AI engine is configured. Add at least one of DRAKEN_ANTHROPIC_API_KEY, "
                    "DRAKEN_OPENAI_API_KEY, DRAKEN_PERPLEXITY_API_KEY or DRAKEN_GEMINI_API_KEY."
                ),
            )
        ]
    async with PoliteClient(concurrency=4, delay=0.2, timeout=90) as client:
        results = await asyncio.gather(
            *(ENGINES[n](client, prompt) for n in names), return_exceptions=True
        )
    out: list[EngineAnswer] = []
    for name, res in zip(names, results, strict=False):
        if isinstance(res, Exception):
            out.append(EngineAnswer(engine=name, error=f"{type(res).__name__}: {res}"))
        else:
            out.append(res)
    return out
