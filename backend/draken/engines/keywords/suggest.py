"""Live keyword suggestion providers.

These are the public autocomplete endpoints search engines expose for their own
search boxes. They are free, need no key, and are the same data source every
"free keyword tool" is built on. Requests are throttled by PoliteClient.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from draken.core.config import settings
from draken.core.http import PoliteClient
from draken.core.logging import get_logger

log = get_logger(__name__)

GOOGLE_SUGGEST = "https://suggestqueries.google.com/complete/search"
BING_SUGGEST = "https://api.bing.com/osjson.aspx"
DDG_SUGGEST = "https://duckduckgo.com/ac/"
YOUTUBE_SUGGEST = "https://suggestqueries.google.com/complete/search"


@dataclass
class Suggestion:
    term: str
    provider: str


def _clean(term: str) -> str:
    term = re.sub(r"\s+", " ", (term or "").strip().lower())
    return term


async def google(client: PoliteClient, seed: str, *, country: str = "US", language: str = "en") -> list[str]:
    params = {"client": "chrome", "q": seed, "hl": language, "gl": country.lower()}
    data, res = await client.fetch_json(GOOGLE_SUGGEST, params=params)
    if data is None and res.text:
        try:  # some responses come back as JSONP-ish arrays
            data = json.loads(res.text[res.text.find("[") :])
        except Exception:
            return []
    if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
        return [_clean(t) for t in data[1] if isinstance(t, str)]
    return []


async def bing(client: PoliteClient, seed: str, *, country: str = "US", language: str = "en") -> list[str]:
    data, _ = await client.fetch_json(BING_SUGGEST, params={"query": seed, "market": f"{language}-{country}"})
    if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
        return [_clean(t) for t in data[1] if isinstance(t, str)]
    return []


async def duckduckgo(client: PoliteClient, seed: str, *, country: str = "US", language: str = "en") -> list[str]:
    data, _ = await client.fetch_json(DDG_SUGGEST, params={"q": seed, "type": "list", "kl": f"{country.lower()}-{language}"})
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            return [_clean(d.get("phrase", "")) for d in data if isinstance(d, dict)]
        if len(data) > 1 and isinstance(data[1], list):
            return [_clean(t) for t in data[1] if isinstance(t, str)]
    return []


async def youtube(client: PoliteClient, seed: str, *, country: str = "US", language: str = "en") -> list[str]:
    params = {"client": "firefox", "ds": "yt", "q": seed, "hl": language, "gl": country.lower()}
    data, _ = await client.fetch_json(YOUTUBE_SUGGEST, params=params)
    if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
        return [_clean(t) for t in data[1] if isinstance(t, str)]
    return []


PROVIDERS = {
    "google": google,
    "bing": bing,
    "duckduckgo": duckduckgo,
    "youtube": youtube,
}


async def fetch_suggestions(
    seeds: list[str],
    *,
    country: str = "US",
    language: str = "en",
    providers: list[str] | None = None,
    client: PoliteClient | None = None,
) -> dict[str, list[str]]:
    """Return ``{seed: [suggestion, ...]}`` merged across the enabled providers."""
    import asyncio

    provider_names = [p for p in (providers or settings.suggest_provider_list) if p in PROVIDERS]
    if not provider_names or not seeds:
        return {s: [] for s in seeds}

    async def run(c: PoliteClient) -> dict[str, list[str]]:
        tasks = []
        index: list[tuple[str, str]] = []
        for seed in seeds:
            for name in provider_names:
                tasks.append(PROVIDERS[name](c, seed, country=country, language=language))
                index.append((seed, name))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: dict[str, list[str]] = {s: [] for s in seeds}
        for (seed, name), out in zip(index, results, strict=False):
            if isinstance(out, Exception):
                log.debug("suggest provider %s failed for %r: %s", name, seed, out)
                continue
            for term in out:
                if term and term not in merged[seed]:
                    merged[seed].append(term)
        return merged

    if client is not None:
        return await run(client)
    async with PoliteClient(delay=0.35, concurrency=6) as c:
        return await run(c)
