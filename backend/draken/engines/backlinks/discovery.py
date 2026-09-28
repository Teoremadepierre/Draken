"""Backlink discovery without a paid link index.

Four independent sources, all free:

1. **Common Crawl** - the public web corpus. Its columnar index lets you ask
   "which URLs on the web are on domain X", and its captures can be searched for
   outbound links. We use the CDX API for host-level discovery.
2. **Mention search** - query search engines for the brand name and check which
   results already link to you. This is what powers unlinked-mention reclamation.
3. **Direct verification crawl** - given a candidate source URL, fetch it and
   confirm whether the link exists, its anchor and its rel attributes. This is
   ground truth and is what keeps the index honest.
4. **Import** - CSV/rows from Search Console, Ahrefs, Semrush or any other tool.

The verification crawl (3) is the important one: it is the only component that
produces facts rather than candidates.
"""

from __future__ import annotations

import asyncio
import csv
import io
from dataclasses import dataclass, field

from draken.core.config import settings
from draken.core.http import PoliteClient
from draken.core.logging import get_logger
from draken.core.models import LinkStatus, LinkType
from draken.core.urls import normalize_domain, normalize_url, same_site
from draken.engines.crawler.parser import parse_html
from draken.engines.serp import authority, fetcher

log = get_logger(__name__)

CC_INDEX = "https://index.commoncrawl.org/CC-MAIN-2024-33-index"


@dataclass
class DiscoveredLink:
    source_url: str
    source_domain: str
    target_url: str = ""
    anchor_text: str = ""
    link_type: str = LinkType.unknown.value
    status: str = LinkStatus.pending.value
    domain_authority: float = 0.0
    is_sitewide: bool = False
    discovered_via: str = "unknown"
    meta: dict = field(default_factory=dict)

    def key(self) -> tuple[str, str]:
        return (self.source_url, self.target_url)


def rel_to_link_type(rel: str) -> str:
    rel = (rel or "").lower()
    if "sponsored" in rel:
        return LinkType.sponsored.value
    if "ugc" in rel:
        return LinkType.ugc.value
    if "nofollow" in rel:
        return LinkType.nofollow.value
    return LinkType.dofollow.value


# ---------------------------------------------------------------------------
# 3. Verification crawl - ground truth
# ---------------------------------------------------------------------------


async def verify_links(
    candidates: list[tuple[str, str]],
    *,
    client: PoliteClient | None = None,
) -> list[DiscoveredLink]:
    """Given ``[(source_url, target_domain_or_url), ...]`` confirm each link.

    Returns one DiscoveredLink per candidate with ``status`` set to live, lost or
    broken, plus the real anchor text and rel attributes read off the page.
    """

    async def check(c: PoliteClient, source_url: str, target: str) -> DiscoveredLink:
        link = DiscoveredLink(
            source_url=normalize_url(source_url),
            source_domain=normalize_domain(source_url),
            target_url=target,
            discovered_via="verification",
        )
        res = await c.fetch(source_url, retries=1)
        if not res.ok:
            link.status = LinkStatus.broken.value
            link.meta["http_status"] = res.status
            link.meta["error"] = res.error
            return link

        parsed = parse_html(res.final_url or source_url, res.text)
        target_domain = normalize_domain(target)
        matches = [
            e for e in parsed.external_links
            if normalize_domain(e["url"]) == target_domain
            and (target_domain == normalize_domain(target) if "//" not in target
                 else normalize_url(e["url"]) == normalize_url(target))
        ]
        if not matches:
            # Retry the looser domain-level match (link may point at a different path).
            matches = [e for e in parsed.external_links if normalize_domain(e["url"]) == target_domain]

        if not matches:
            link.status = LinkStatus.lost.value
            link.meta["http_status"] = res.status
            # Unlinked mention? Very valuable to know.
            brand_guess = target_domain.split(".")[0]
            if brand_guess and brand_guess.lower() in parsed.text.lower():
                link.meta["unlinked_mention"] = True
            return link

        best = matches[0]
        link.status = LinkStatus.live.value
        link.target_url = normalize_url(best["url"])
        link.anchor_text = best["anchor"][:600]
        link.link_type = rel_to_link_type(best["rel"])
        link.meta["http_status"] = res.status
        link.meta["occurrences"] = len(matches)
        return link

    async def run(c: PoliteClient) -> list[DiscoveredLink]:
        results = await asyncio.gather(
            *(check(c, s, t) for s, t in candidates), return_exceptions=True
        )
        out: list[DiscoveredLink] = []
        for (source, target), r in zip(candidates, results, strict=False):
            if isinstance(r, Exception):
                out.append(
                    DiscoveredLink(
                        source_url=normalize_url(source),
                        source_domain=normalize_domain(source),
                        target_url=target,
                        status=LinkStatus.broken.value,
                        discovered_via="verification",
                        meta={"error": str(r)},
                    )
                )
            else:
                out.append(r)
        return out

    if not candidates:
        return []
    if client is not None:
        links = await run(client)
    else:
        async with PoliteClient(concurrency=4, delay=0.8, timeout=20) as c:
            links = await run(c)

    auth_map = await authority.authority_for([link.source_domain for link in links])
    for link in links:
        link.domain_authority = auth_map.get(link.source_domain, 0.0)
    return links


# ---------------------------------------------------------------------------
# 2. Mention discovery via search engines
# ---------------------------------------------------------------------------


async def discover_mentions(
    *,
    domain: str,
    brand_terms: list[str],
    country: str = "US",
    language: str = "en",
    max_queries: int = 8,
) -> list[DiscoveredLink]:
    """Find pages that mention the brand, then verify whether they link to us.

    Pages that mention but do not link are the highest-converting link
    opportunity that exists, so they are returned with ``unlinked_mention`` set.
    """
    domain = normalize_domain(domain)
    terms = [t for t in (brand_terms or []) if t][:4] or [domain.split(".")[0]]

    queries: list[str] = []
    for t in terms:
        queries.append(f'"{t}"')
        queries.append(f'"{t}" -site:{domain}')
    queries.append(f'"{domain}" -site:{domain}')
    queries = queries[:max_queries]

    pages = await fetcher.fetch_many(queries, country=country, language=language)

    candidate_urls: list[str] = []
    for page in pages.values():
        for item in page.items:
            if not item.url or same_site(item.url, f"https://{domain}"):
                continue
            if item.url not in candidate_urls:
                candidate_urls.append(item.url)

    if not candidate_urls:
        return []

    links = await verify_links([(u, domain) for u in candidate_urls[:80]])
    for link in links:
        link.discovered_via = "mention_search"
    return links


# ---------------------------------------------------------------------------
# 1. Common Crawl host discovery
# ---------------------------------------------------------------------------


async def commoncrawl_urls(domain: str, *, limit: int = 200) -> list[str]:
    """List URLs Common Crawl has seen for a host. Useful for competitor recon."""
    if not settings.commoncrawl_enabled:
        return []
    domain = normalize_domain(domain)
    out: list[str] = []
    async with PoliteClient(concurrency=1, delay=1.2, timeout=30) as client:
        res = await client.fetch(
            CC_INDEX,
            params={"url": f"*.{domain}/*", "output": "json", "limit": limit},
            retries=1,
        )
        if not res.ok:
            log.info("common crawl index unavailable (%s)", res.error or res.status)
            return []
        import json

        for line in res.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            url = row.get("url")
            if url:
                out.append(normalize_url(url))
    return list(dict.fromkeys(out))[:limit]


# ---------------------------------------------------------------------------
# Competitor link discovery (prospecting input)
# ---------------------------------------------------------------------------


async def discover_competitor_links(
    competitor_domain: str,
    *,
    country: str = "US",
    language: str = "en",
    max_queries: int = 6,
) -> list[DiscoveredLink]:
    """Find pages that link to a competitor - these are your prospect list.

    Uses public search operators that surface the page types which habitually
    link out (resource lists, comparisons, roundups, "best of" posts).
    """
    competitor_domain = normalize_domain(competitor_domain)
    brand = competitor_domain.split(".")[0]
    queries = [
        f'"{competitor_domain}" -site:{competitor_domain}',
        f'"{brand}" alternatives -site:{competitor_domain}',
        f'"{brand}" review -site:{competitor_domain}',
        f'intitle:resources "{brand}" -site:{competitor_domain}',
        f'intitle:"best" "{brand}" -site:{competitor_domain}',
        f'"{brand}" vs -site:{competitor_domain}',
    ][:max_queries]

    pages = await fetcher.fetch_many(queries, country=country, language=language)
    urls: list[str] = []
    for page in pages.values():
        for item in page.items:
            if item.url and normalize_domain(item.url) != competitor_domain and item.url not in urls:
                urls.append(item.url)

    links = await verify_links([(u, competitor_domain) for u in urls[:80]])
    live = [link for link in links if link.status == LinkStatus.live.value]
    for link in live:
        link.discovered_via = "competitor_serp"
    log.info(
        "competitor discovery %s: %d candidates -> %d confirmed links",
        competitor_domain, len(urls), len(live),
    )
    return live


# ---------------------------------------------------------------------------
# 4. Import from any external tool
# ---------------------------------------------------------------------------

_COLUMN_ALIASES = {
    "source_url": {"source_url", "source url", "referring page url", "url from", "from",
                    "page", "source", "referring page", "url"},
    "target_url": {"target_url", "target url", "url to", "to", "destination",
                   "target page url", "link url"},
    "anchor_text": {"anchor", "anchor_text", "anchor text", "link anchor", "anchor/text"},
    "link_type": {"link_type", "type", "nofollow", "follow", "rel", "link type"},
    "domain_authority": {"domain_authority", "da", "dr", "domain rating", "domain authority",
                         "authority", "domain_rating"},
    "first_seen": {"first_seen", "first seen", "discovered", "date", "first_indexed"},
}


def _map_columns(fieldnames: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw in fieldnames or []:
        key = (raw or "").strip().lower()
        for canonical, aliases in _COLUMN_ALIASES.items():
            if key in aliases and canonical not in mapping.values():
                mapping[raw] = canonical
                break
    return mapping


def parse_import(csv_text: str = "", rows: list[dict] | None = None) -> list[DiscoveredLink]:
    """Accept an export from Search Console / Ahrefs / Semrush / anything.

    Column names are matched loosely so you can paste a CSV without reformatting.
    """
    records: list[dict] = list(rows or [])

    if csv_text and csv_text.strip():
        # Sniff the delimiter: exports use comma, semicolon or tab.
        sample = csv_text[:4000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(csv_text), dialect=dialect)
        mapping = _map_columns(reader.fieldnames or [])
        for row in reader:
            if not row:
                continue
            mapped = {mapping[k]: v for k, v in row.items() if k in mapping and v is not None}
            if mapped:
                records.append(mapped)

    out: list[DiscoveredLink] = []
    seen: set[tuple[str, str]] = set()
    for rec in records:
        source = str(rec.get("source_url") or rec.get("source") or "").strip()
        if not source:
            continue
        if "//" not in source:
            source = f"https://{source}"
        source = normalize_url(source)
        target = normalize_url(str(rec.get("target_url") or "").strip()) if rec.get("target_url") else ""

        raw_type = str(rec.get("link_type") or "").strip().lower()
        if raw_type in {"dofollow", "follow", "true", "yes", "1"}:
            link_type = LinkType.dofollow.value
        elif raw_type in {"nofollow", "false", "no", "0"}:
            link_type = LinkType.nofollow.value
        elif raw_type in {"ugc", "sponsored"}:
            link_type = raw_type
        else:
            link_type = LinkType.unknown.value

        try:
            da = float(str(rec.get("domain_authority") or 0).replace(",", "."))
        except ValueError:
            da = 0.0

        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            DiscoveredLink(
                source_url=source,
                source_domain=normalize_domain(source),
                target_url=target,
                anchor_text=str(rec.get("anchor_text") or "")[:600],
                link_type=link_type,
                status=LinkStatus.pending.value,
                domain_authority=da,
                discovered_via="import",
            )
        )
    return out
