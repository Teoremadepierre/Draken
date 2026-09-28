"""Bing Webmaster Tools: real performance data **and a free backlink report**.

The backlink part matters more than it sounds. Bing gives you the full inbound
link report for your verified sites at no cost, which is the one piece of data
the commercial suites charge most for. It is not a complete index of the web, but
for your own site it is real, measured data rather than an estimate.

    DRAKEN_BING_WEBMASTER_API_KEY=...      (Webmaster Tools -> Settings -> API access)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from draken.core.config import settings
from draken.core.http import PoliteClient
from draken.core.logging import get_logger
from draken.core.urls import normalize_domain, normalize_url

log = get_logger(__name__)

API_BASE = "https://ssl.bing.com/webmaster/api.svc/json"


@dataclass
class BingQueryRow:
    query: str = ""
    clicks: int = 0
    impressions: int = 0
    position: float = 0.0
    ctr: float = 0.0


@dataclass
class BingLinkRow:
    source_url: str = ""
    source_domain: str = ""
    target_url: str = ""
    anchor_text: str = ""


@dataclass
class BingResult:
    queries: list[BingQueryRow] = field(default_factory=list)
    links: list[BingLinkRow] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def is_configured() -> bool:
    return bool(settings.bing_webmaster_api_key)


def configuration_hint() -> str:
    return (
        "Set DRAKEN_BING_WEBMASTER_API_KEY. Get it from Bing Webmaster Tools -> "
        "Settings -> API access -> API key, on a site you have verified. "
        "Bing's inbound-link report is free and is real measured data."
    )


def _site_url(domain: str) -> str:
    explicit = settings.bing_site_url
    if explicit:
        return explicit
    return f"https://{normalize_domain(domain)}"


async def _call(client: PoliteClient, method: str, params: dict) -> tuple[dict | list | None, str]:
    data, res = await client.fetch_json(
        f"{API_BASE}/{method}",
        params={**params, "apikey": settings.bing_webmaster_api_key},
    )
    if not isinstance(data, dict):
        return None, res.error or f"HTTP {res.status}: {res.text[:200]}"
    if "ErrorCode" in data and data.get("ErrorCode"):
        return None, str(data.get("Message") or data.get("ErrorCode"))
    return data.get("d", data), ""


async def query_performance(*, domain: str, days: int = 30) -> BingResult:
    """Real clicks, impressions and average position from Bing."""
    result = BingResult()
    if not is_configured():
        result.error = configuration_hint()
        return result

    end = datetime.now(UTC).date()
    start = end - timedelta(days=days)

    async with PoliteClient(concurrency=2, delay=0.4, timeout=45) as client:
        payload, error = await _call(client, "GetQueryStats", {
            "siteUrl": _site_url(domain),
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
        })
    if error:
        result.error = error
        return result

    for row in payload or []:
        if not isinstance(row, dict):
            continue
        impressions = int(row.get("Impressions") or 0)
        clicks = int(row.get("Clicks") or 0)
        result.queries.append(
            BingQueryRow(
                query=row.get("Query") or "",
                clicks=clicks,
                impressions=impressions,
                position=float(row.get("AvgImpressionPosition") or 0.0),
                ctr=round(clicks / impressions, 4) if impressions else 0.0,
            )
        )
    log.info("bing webmaster: %d query rows for %s", len(result.queries), domain)
    return result


async def inbound_links(*, domain: str, page_limit: int = 5) -> BingResult:
    """Bing's inbound link report. Free, real, and the best free backlink source."""
    result = BingResult()
    if not is_configured():
        result.error = configuration_hint()
        return result

    site = _site_url(domain)
    async with PoliteClient(concurrency=1, delay=0.6, timeout=60) as client:
        payload, error = await _call(client, "GetLinkCounts", {"siteUrl": site, "page": 0})
        if error:
            result.error = error
            return result

        # GetLinkCounts returns pages of the site with their inbound link counts;
        # GetUrlLinks then returns the actual linking URLs for one of those pages.
        targets: list[str] = []
        for row in payload or []:
            if isinstance(row, dict) and row.get("Url"):
                targets.append(row["Url"])
        if not targets:
            targets = [site]

        for target in targets[:page_limit]:
            detail, detail_error = await _call(
                client, "GetUrlLinks", {"siteUrl": site, "link": target, "page": 0}
            )
            if detail_error:
                log.debug("bing GetUrlLinks failed for %s: %s", target, detail_error)
                continue
            for row in detail or []:
                if not isinstance(row, dict):
                    continue
                source = row.get("Url") or ""
                if not source:
                    continue
                result.links.append(
                    BingLinkRow(
                        source_url=normalize_url(source),
                        source_domain=normalize_domain(source),
                        target_url=normalize_url(target),
                        anchor_text=row.get("AnchorText") or "",
                    )
                )

    log.info("bing webmaster: %d inbound links for %s", len(result.links), domain)
    return result
