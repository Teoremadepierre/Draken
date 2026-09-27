"""robots.txt and sitemap handling. We obey robots by default - always."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from draken.core.config import settings
from draken.core.http import PoliteClient
from draken.core.logging import get_logger
from draken.core.urls import normalize_url

log = get_logger(__name__)


@dataclass
class RobotsInfo:
    url: str
    exists: bool = False
    content: str = ""
    sitemaps: list[str] = field(default_factory=list)
    crawl_delay: float | None = None
    parser: RobotFileParser | None = None

    def allows(self, url: str, user_agent: str | None = None) -> bool:
        if not settings.respect_robots or not self.parser:
            return True
        return self.parser.can_fetch(user_agent or settings.user_agent, url)


async def fetch_robots(base_url: str, client: PoliteClient) -> RobotsInfo:
    robots_url = urljoin(base_url, "/robots.txt")
    info = RobotsInfo(url=robots_url)
    res = await client.fetch(robots_url, retries=1)
    if not res.ok or not res.text.strip():
        return info
    info.exists = True
    info.content = res.text[:200_000]
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.parse(info.content.splitlines())
        info.parser = parser
    except Exception as exc:  # noqa: BLE001
        log.warning("could not parse robots.txt at %s: %s", robots_url, exc)
    for line in info.content.splitlines():
        low = line.strip().lower()
        if low.startswith("sitemap:"):
            sm = line.split(":", 1)[1].strip()
            if sm:
                info.sitemaps.append(sm)
        elif low.startswith("crawl-delay:"):
            try:
                info.crawl_delay = float(low.split(":", 1)[1].strip())
            except ValueError:
                pass
    return info


async def fetch_sitemap_urls(
    sitemap_url: str, client: PoliteClient, *, max_urls: int = 5000, depth: int = 0
) -> list[str]:
    """Read a sitemap (or sitemap index, recursively) and return page URLs."""
    if depth > 3:
        return []
    res = await client.fetch(sitemap_url, retries=1)
    if not res.ok:
        return []
    soup = BeautifulSoup(res.text, "xml")
    urls: list[str] = []

    for sm in soup.find_all("sitemap"):
        loc = sm.find("loc")
        if loc and loc.text.strip():
            urls.extend(
                await fetch_sitemap_urls(
                    loc.text.strip(), client, max_urls=max_urls - len(urls), depth=depth + 1
                )
            )
            if len(urls) >= max_urls:
                return urls[:max_urls]

    for entry in soup.find_all("url"):
        loc = entry.find("loc")
        if loc and loc.text.strip():
            urls.append(normalize_url(loc.text.strip()))
            if len(urls) >= max_urls:
                break
    return urls[:max_urls]


async def discover_start_urls(base_url: str, client: PoliteClient, *, limit: int = 2000) -> tuple[list[str], RobotsInfo]:
    """Prefer sitemap URLs as crawl seeds; fall back to the homepage."""
    robots = await fetch_robots(base_url, client)
    urls: list[str] = []
    candidates = list(robots.sitemaps) or [
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml"),
    ]
    for sm in candidates:
        urls.extend(await fetch_sitemap_urls(sm, client, max_urls=limit - len(urls)))
        if len(urls) >= limit:
            break
    if not urls:
        urls = [normalize_url(base_url)]
    return list(dict.fromkeys(urls))[:limit], robots
