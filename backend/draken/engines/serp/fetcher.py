"""SERP retrieval.

Three tiers, in preference order:
  1. SerpApi        - if DRAKEN_SERPAPI_KEY is set (accurate, paid)
  2. DataForSEO     - if credentials are set (accurate, paid)
  3. DuckDuckGo HTML - free fallback, no key, approximate but real organic results

Tier 3 exists so the platform is useful on day one. It is clearly labelled in
the UI as approximate so nobody reports a DuckDuckGo position as a Google one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from draken.core.config import settings
from draken.core.http import PoliteClient
from draken.core.logging import get_logger
from draken.core.urls import normalize_domain, normalize_url

log = get_logger(__name__)


@dataclass
class SerpItem:
    position: int
    url: str
    domain: str
    title: str = ""
    snippet: str = ""
    result_type: str = "organic"


@dataclass
class SerpPage:
    term: str
    country: str
    provider: str
    items: list[SerpItem] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def approximate(self) -> bool:
        return self.provider not in {"serpapi", "dataforseo"}

    def position_of(self, domain: str) -> tuple[int | None, str]:
        target = normalize_domain(domain)
        for item in self.items:
            if item.domain == target:
                return item.position, item.url
        return None, ""

    def domains(self) -> list[str]:
        seen: list[str] = []
        for i in self.items:
            if i.domain and i.domain not in seen:
                seen.append(i.domain)
        return seen


def active_provider() -> str:
    if settings.serpapi_key:
        return "serpapi"
    if settings.dataforseo_login and settings.dataforseo_password:
        return "dataforseo"
    return "duckduckgo_html"


async def _serpapi(client: PoliteClient, term: str, country: str, language: str) -> SerpPage:
    params = {
        "engine": "google",
        "q": term,
        "gl": country.lower(),
        "hl": language,
        "num": 20,
        "api_key": settings.serpapi_key,
    }
    data, res = await client.fetch_json("https://serpapi.com/search.json", params=params)
    page = SerpPage(term=term, country=country, provider="serpapi")
    if not isinstance(data, dict):
        page.error = res.error or f"serpapi HTTP {res.status}"
        return page
    if data.get("error"):
        page.error = str(data["error"])
        return page
    for i, row in enumerate(data.get("organic_results") or [], start=1):
        url = row.get("link") or ""
        page.items.append(
            SerpItem(
                position=row.get("position") or i,
                url=normalize_url(url),
                domain=normalize_domain(url),
                title=row.get("title") or "",
                snippet=row.get("snippet") or "",
            )
        )
    for key, label in (
        ("answer_box", "featured_snippet"),
        ("knowledge_graph", "knowledge_panel"),
        ("local_results", "local_pack"),
        ("related_questions", "people_also_ask"),
        ("inline_videos", "video"),
        ("inline_images", "images"),
        ("shopping_results", "shopping"),
        ("ai_overview", "ai_overview"),
    ):
        if data.get(key):
            page.features.append(label)
    return page


async def _dataforseo(client: PoliteClient, term: str, country: str, language: str) -> SerpPage:
    import base64

    page = SerpPage(term=term, country=country, provider="dataforseo")
    auth = base64.b64encode(
        f"{settings.dataforseo_login}:{settings.dataforseo_password}".encode()
    ).decode()
    payload = [{"keyword": term, "location_name": country, "language_code": language, "depth": 20}]
    data, res = await client.fetch_json(
        "https://api.dataforseo.com/v3/serp/google/organic/live/advanced",
        method="POST",
        json=payload,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
    )
    if not isinstance(data, dict):
        page.error = res.error or f"dataforseo HTTP {res.status}"
        return page
    try:
        items = data["tasks"][0]["result"][0]["items"] or []
    except Exception:
        page.error = "unexpected dataforseo response shape"
        return page
    pos = 0
    for row in items:
        if row.get("type") != "organic":
            if row.get("type"):
                page.features.append(str(row["type"]))
            continue
        pos += 1
        url = row.get("url") or ""
        page.items.append(
            SerpItem(
                position=row.get("rank_absolute") or pos,
                url=normalize_url(url),
                domain=normalize_domain(url),
                title=row.get("title") or "",
                snippet=row.get("description") or "",
            )
        )
    page.features = sorted(set(page.features))
    return page


_DDG_UDDG = re.compile(r"uddg=([^&]+)")


async def _duckduckgo_html(client: PoliteClient, term: str, country: str, language: str) -> SerpPage:
    """Free fallback. DuckDuckGo's HTML endpoint returns real organic results."""
    page = SerpPage(term=term, country=country, provider="duckduckgo_html")
    res = await client.fetch(
        "https://html.duckduckgo.com/html/",
        method="POST",
        data={"q": term, "kl": f"{country.lower()}-{language}"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if not res.ok:
        page.error = res.error or f"HTTP {res.status}"
        return page

    soup = BeautifulSoup(res.text, "lxml")
    position = 0
    for result in soup.select(".result, .web-result"):
        if "result--ad" in (result.get("class") or []):
            continue
        anchor = result.select_one("a.result__a")
        if not anchor:
            continue
        href = anchor.get("href") or ""
        # DuckDuckGo wraps outbound links in /l/?uddg=<encoded>
        m = _DDG_UDDG.search(href)
        if m:
            from urllib.parse import unquote

            href = unquote(m.group(1))
        if not href.startswith("http"):
            continue
        position += 1
        snippet_el = result.select_one(".result__snippet")
        page.items.append(
            SerpItem(
                position=position,
                url=normalize_url(href),
                domain=normalize_domain(href),
                title=anchor.get_text(" ", strip=True),
                snippet=snippet_el.get_text(" ", strip=True) if snippet_el else "",
            )
        )
        if position >= 30:
            break
    if not page.items:
        page.error = "no organic results parsed"
    return page


_PROVIDERS = {
    "serpapi": _serpapi,
    "dataforseo": _dataforseo,
    "duckduckgo_html": _duckduckgo_html,
}


async def fetch_serp(
    term: str,
    *,
    country: str = "US",
    language: str = "en",
    provider: str | None = None,
    client: PoliteClient | None = None,
) -> SerpPage:
    name = provider or active_provider()
    fn = _PROVIDERS.get(name, _duckduckgo_html)

    async def run(c: PoliteClient) -> SerpPage:
        return await fn(c, term, country, language)

    if client is not None:
        return await run(client)
    async with PoliteClient(delay=1.5, concurrency=2, timeout=25) as c:
        return await run(c)


async def fetch_many(
    terms: list[str],
    *,
    country: str = "US",
    language: str = "en",
    provider: str | None = None,
) -> dict[str, SerpPage]:
    """Fetch several SERPs with a conservative delay (these are shared endpoints)."""
    import asyncio

    name = provider or active_provider()
    delay = 0.4 if name in {"serpapi", "dataforseo"} else 2.0
    concurrency = 5 if name in {"serpapi", "dataforseo"} else 2
    out: dict[str, SerpPage] = {}
    async with PoliteClient(delay=delay, concurrency=concurrency, timeout=25) as client:
        results = await asyncio.gather(
            *(fetch_serp(t, country=country, language=language, provider=name, client=client) for t in terms),
            return_exceptions=True,
        )
    for term, res in zip(terms, results, strict=False):
        if isinstance(res, Exception):
            out[term] = SerpPage(term=term, country=country, provider=name, error=str(res))
        else:
            out[term] = res
    return out
