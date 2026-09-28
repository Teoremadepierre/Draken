"""The site audit crawler: BFS over a site, page analysis, issue aggregation."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field

from draken.core.config import settings
from draken.core.http import PoliteClient
from draken.core.logging import get_logger
from draken.core.urls import (
    is_probably_binary,
    normalize_url,
    same_site,
    url_depth,
)
from draken.engines.crawler import checks
from draken.engines.crawler import robots as robots_mod
from draken.engines.crawler.parser import parse_html

log = get_logger(__name__)


@dataclass
class CrawlResult:
    base_url: str
    pages: list[dict] = field(default_factory=list)
    issues: list[checks.Issue] = field(default_factory=list)
    health_score: float = 0.0
    robots_exists: bool = False
    sitemap_urls: int = 0
    external_links: list[dict] = field(default_factory=list)
    error: str = ""

    def issue_counts(self) -> dict:
        counts: dict[str, int] = {}
        for i in self.issues:
            counts[i.severity] = counts.get(i.severity, 0) + 1
        return counts

    def summary(self) -> dict:
        html = [p for p in self.pages if "html" in (p.get("content_type") or "")]
        indexable = [
            p for p in html
            if 200 <= int(p.get("status_code") or 0) < 300
            and "noindex" not in (p.get("robots_meta") or "")
        ]
        total_words = sum(int(p.get("word_count") or 0) for p in html)
        by_code: dict[str, int] = {}
        for i in self.issues:
            by_code[i.code] = by_code.get(i.code, 0) + 1
        return {
            "pages_crawled": len(self.pages),
            "html_pages": len(html),
            "indexable_pages": len(indexable),
            "broken_pages": sum(1 for p in self.pages if int(p.get("status_code") or 0) >= 400),
            "redirects": sum(1 for p in self.pages if 300 <= int(p.get("status_code") or 0) < 400),
            "avg_word_count": int(total_words / len(html)) if html else 0,
            "avg_response_ms": int(
                sum(int(p.get("response_ms") or 0) for p in self.pages) / max(1, len(self.pages))
            ),
            "pages_with_schema": sum(1 for p in html if p.get("has_schema")),
            "avg_ai_readiness": round(
                sum(float(p.get("ai_readiness") or 0) for p in html) / len(html), 1
            ) if html else 0.0,
            "external_domains": len({e.get("domain") for e in self.external_links if e.get("domain")}),
            "robots_txt": self.robots_exists,
            "sitemap_urls": self.sitemap_urls,
            "top_issues": sorted(by_code.items(), key=lambda kv: -kv[1])[:12],
        }


async def crawl_site(
    base_url: str,
    *,
    max_pages: int | None = None,
    max_depth: int = 4,
    progress=None,
) -> CrawlResult:
    """Breadth-first crawl of one site, then run the full check suite."""
    base_url = base_url if "//" in base_url else f"https://{base_url}"
    base_url = normalize_url(base_url)
    max_pages = min(max_pages or settings.max_pages_per_audit, settings.max_pages_per_audit)
    result = CrawlResult(base_url=base_url)

    async with PoliteClient(
        concurrency=settings.crawl_concurrency, delay=settings.crawl_delay_seconds
    ) as client:
        try:
            sitemap_urls, robots_info = await robots_mod.discover_start_urls(
                base_url, client, limit=max_pages * 2
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("sitemap discovery failed for %s: %s", base_url, exc)
            sitemap_urls, robots_info = [base_url], robots_mod.RobotsInfo(url="")

        result.robots_exists = robots_info.exists
        result.sitemap_urls = len([u for u in sitemap_urls if u != base_url])

        if robots_info.crawl_delay and robots_info.crawl_delay > client.throttle.delay:
            client.throttle.delay = min(robots_info.crawl_delay, 5.0)
            log.info("honouring robots.txt crawl-delay of %ss", client.throttle.delay)

        queue: deque[tuple[str, int]] = deque()
        seen: set[str] = set()

        def enqueue(url: str, depth: int) -> None:
            url = normalize_url(url)
            if (
                not url
                or url in seen
                or depth > max_depth
                or not same_site(base_url, url)
                or is_probably_binary(url)
            ):
                return
            if not robots_info.allows(url):
                return
            seen.add(url)
            queue.append((url, depth))

        enqueue(base_url, 0)
        for u in sitemap_urls[: max_pages * 2]:
            enqueue(u, min(1, max_depth))

        crawled = 0
        while queue and crawled < max_pages:
            batch: list[tuple[str, int]] = []
            while queue and len(batch) < settings.crawl_concurrency and crawled + len(batch) < max_pages:
                batch.append(queue.popleft())

            fetched = await asyncio.gather(
                *(client.fetch(url, retries=1) for url, _ in batch), return_exceptions=True
            )

            for (url, depth), res in zip(batch, fetched, strict=False):
                crawled += 1
                if isinstance(res, Exception):
                    result.pages.append(
                        {"url": url, "status_code": 0, "depth": depth, "content_type": "", "outlinks": []}
                    )
                    continue

                content_type = (res.headers.get("content-type") or "").split(";")[0].lower()
                record: dict = {
                    "url": url,
                    "status_code": res.status,
                    "content_type": content_type,
                    "response_ms": res.elapsed_ms,
                    "size_bytes": len(res.text.encode("utf-8", "ignore")),
                    "depth": depth if depth else url_depth(url),
                    "outlinks": [],
                }

                if res.ok and "html" in content_type:
                    parsed = parse_html(res.final_url or url, res.text)
                    record.update(
                        {
                            "title": parsed.title,
                            "meta_description": parsed.meta_description,
                            "h1": parsed.h1,
                            "h1_count": parsed.h1_count,
                            "h2_count": parsed.h2_count,
                            "word_count": parsed.word_count,
                            "internal_links": len(parsed.internal_links),
                            "external_links": len(parsed.external_links),
                            "images_without_alt": parsed.images_without_alt,
                            "canonical": parsed.canonical,
                            "robots_meta": parsed.robots_meta,
                            "has_schema": bool(parsed.schema_types),
                            "schema_types": parsed.schema_types,
                            "hreflang": parsed.hreflang,
                            "outlinks": parsed.internal_links[:300],
                        }
                    )
                    record["ai_readiness"] = checks.ai_readiness_score(record)
                    for ext in parsed.external_links:
                        from draken.core.urls import normalize_domain

                        result.external_links.append(
                            {
                                "from": url,
                                "url": ext["url"],
                                "domain": normalize_domain(ext["url"]),
                                "anchor": ext["anchor"],
                                "rel": ext["rel"],
                            }
                        )
                    for link in parsed.internal_links:
                        enqueue(link, depth + 1)

                result.pages.append(record)

            if progress:
                try:
                    progress(crawled, max_pages)
                except Exception:  # noqa: BLE001
                    pass

    # inlink counts
    inlinks: dict[str, int] = {}
    for p in result.pages:
        for link in p.get("outlinks") or []:
            key = normalize_url(link)
            inlinks[key] = inlinks.get(key, 0) + 1
    for p in result.pages:
        p["inlinks"] = inlinks.get(normalize_url(p["url"]), 0)

    for p in result.pages:
        result.issues.extend(checks.page_issues(p))
    result.issues.extend(
        checks.site_issues(
            result.pages, robots_exists=result.robots_exists, sitemap_count=result.sitemap_urls
        )
    )
    result.health_score = checks.health_score(result.issues, len(result.pages))
    log.info(
        "audit finished %s: %d pages, %d issues, health %.1f",
        base_url, len(result.pages), len(result.issues), result.health_score,
    )
    return result


async def fetch_single_page(url: str) -> tuple[dict, object]:
    """Fetch and parse one page - used by the on-page analyzer."""
    url = normalize_url(url if "//" in url else f"https://{url}")
    async with PoliteClient(concurrency=2, delay=0.2) as client:
        res = await client.fetch(url)
    if not res.ok:
        return {"url": url, "status_code": res.status, "error": res.error}, None
    parsed = parse_html(res.final_url or url, res.text)
    record = {
        "url": url,
        "final_url": res.final_url,
        "status_code": res.status,
        "response_ms": res.elapsed_ms,
        "size_bytes": len(res.text.encode("utf-8", "ignore")),
        "content_type": (res.headers.get("content-type") or "").split(";")[0],
        "title": parsed.title,
        "meta_description": parsed.meta_description,
        "h1": parsed.h1,
        "h1_count": parsed.h1_count,
        "h2_count": parsed.h2_count,
        "word_count": parsed.word_count,
        "internal_links": len(parsed.internal_links),
        "external_links": len(parsed.external_links),
        "images_without_alt": parsed.images_without_alt,
        "canonical": parsed.canonical,
        "robots_meta": parsed.robots_meta,
        "has_schema": bool(parsed.schema_types),
        "schema_types": parsed.schema_types,
    }
    record["ai_readiness"] = checks.ai_readiness_score(record)
    return record, parsed
