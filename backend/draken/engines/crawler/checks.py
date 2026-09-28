"""Technical SEO rule set applied to crawled pages.

Each rule is a small function so the catalogue is auditable and extendable: add
a function, append it to ``PAGE_RULES`` or ``SITE_RULES``, done.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from draken.core.models import IssueSeverity
from draken.core.urls import normalize_url


@dataclass
class Issue:
    code: str
    severity: str
    title: str
    description: str
    how_to_fix: str
    url: str = ""
    category: str = "technical"
    detail: dict | None = None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "how_to_fix": self.how_to_fix,
            "url": self.url,
            "category": self.category,
            "detail": self.detail or {},
        }


C = IssueSeverity.critical.value
E = IssueSeverity.error.value
W = IssueSeverity.warning.value
N = IssueSeverity.notice.value

# Weights used for the 0-100 site health score.
SEVERITY_WEIGHT = {C: 10.0, E: 4.0, W: 1.5, N: 0.4}


def page_issues(page: dict) -> list[Issue]:
    """Rules evaluated against a single crawled page dict."""
    out: list[Issue] = []
    url = page.get("url", "")
    status = int(page.get("status_code") or 0)
    title = (page.get("title") or "").strip()
    desc = (page.get("meta_description") or "").strip()
    h1 = (page.get("h1") or "").strip()
    words = int(page.get("word_count") or 0)
    robots_meta = (page.get("robots_meta") or "").lower()
    is_html = "html" in (page.get("content_type") or "")

    if status == 0:
        out.append(Issue("fetch_failed", C, "Page could not be fetched",
                         "The crawler received no response.",
                         "Check DNS, TLS certificate, firewall rules and server availability.", url))
        return out
    if status >= 500:
        out.append(Issue("server_error_5xx", C, f"Server error ({status})",
                         "The server returned a 5xx status, so this page cannot be indexed.",
                         "Check application logs and fix the server-side error.", url))
        return out
    if status == 404:
        out.append(Issue("broken_page_404", E, "Broken internal page (404)",
                         "An internally linked URL returns 404, wasting crawl budget and any link equity pointing at it.",
                         "Restore the page, or 301-redirect it to the closest equivalent and update the internal links.",
                         url))
        return out
    if status in (401, 403):
        out.append(Issue("blocked_page", E, f"Page blocked ({status})",
                         "The crawler was denied access, which search engines will be too.",
                         "Allow crawler access, or remove the internal links pointing here.", url))
        return out
    if 300 <= status < 400:
        out.append(Issue("internal_redirect", W, "Internal link points at a redirect",
                         "Internal links should point at the final URL - each hop loses a little equity and slows crawling.",
                         "Update internal links to the destination URL.", url))

    if not is_html:
        return out

    if "noindex" in robots_meta:
        out.append(Issue("noindex", W, "Page is set to noindex",
                         "This page has been excluded from the index by a robots meta tag.",
                         "Intentional? Fine. If not, remove the noindex directive.", url,
                         detail={"robots": robots_meta}))
    if "nofollow" in robots_meta:
        out.append(Issue("meta_nofollow", N, "Page-level nofollow",
                         "All links on this page are nofollowed, so internal equity stops here.",
                         "Remove the page-level nofollow unless it is deliberate.", url))

    if not title:
        out.append(Issue("missing_title", C, "Missing title tag",
                         "The title is the single strongest on-page ranking element and the clickable line in results.",
                         "Write a unique 40-60 character title with the primary keyword near the front.", url,
                         category="on-page"))
    elif len(title) < 25:
        out.append(Issue("short_title", W, "Title is too short",
                         f"Title is {len(title)} characters - room is being wasted.",
                         "Expand to 40-60 characters and include the primary keyword and a differentiator.", url,
                         category="on-page", detail={"length": len(title)}))
    elif len(title) > 65:
        out.append(Issue("long_title", N, "Title may be truncated",
                         f"Title is {len(title)} characters and will likely be cut off in results.",
                         "Trim to about 60 characters, front-loading the important words.", url,
                         category="on-page", detail={"length": len(title)}))

    if not desc:
        out.append(Issue("missing_meta_description", W, "Missing meta description",
                         "Without one, the engine writes its own snippet and click-through usually suffers.",
                         "Write a 140-160 character description with the keyword and a reason to click.", url,
                         category="on-page"))
    elif len(desc) > 165:
        out.append(Issue("long_meta_description", N, "Meta description may be truncated",
                         f"Description is {len(desc)} characters.",
                         "Trim to about 155 characters.", url, category="on-page",
                         detail={"length": len(desc)}))

    h1_count = int(page.get("h1_count") or (1 if h1 else 0))
    if not h1:
        out.append(Issue("missing_h1", E, "Missing H1",
                         "No H1 means neither users nor parsers get a clear statement of the page topic.",
                         "Add exactly one H1 that states what the page is about.", url, category="on-page"))
    elif h1_count > 1:
        out.append(Issue("multiple_h1", N, "Multiple H1 tags",
                         f"Found {h1_count} H1 elements, which blurs the page's topic signal.",
                         "Keep one H1; demote the rest to H2.", url, category="on-page",
                         detail={"count": h1_count}))

    if words < 150:
        out.append(Issue("thin_content", W, "Thin content",
                         f"Only {words} words of body copy - usually too little to satisfy a query or to be cited.",
                         "Either expand it to genuinely answer the query, consolidate it into a stronger page, or noindex it.",
                         url, category="content", detail={"word_count": words}))

    if not page.get("canonical"):
        out.append(Issue("missing_canonical", N, "No canonical tag",
                         "Without a canonical, parameterised or duplicated variants can compete with each other.",
                         "Add a self-referencing canonical link to every indexable page.", url))

    if int(page.get("images_without_alt") or 0) > 0:
        out.append(Issue("images_missing_alt", N, "Images without alt text",
                         f"{page['images_without_alt']} image(s) have no alt attribute.",
                         "Describe each image's content; it is both an accessibility and an image-search requirement.",
                         url, category="accessibility",
                         detail={"count": page.get("images_without_alt")}))

    if not page.get("has_schema"):
        out.append(Issue("missing_structured_data", W, "No structured data",
                         "No JSON-LD found. Structured data is how both rich results and AI answer engines identify entities.",
                         "Add JSON-LD appropriate to the page: Organization, Product, Article, FAQPage, LocalBusiness.",
                         url, category="ai-readiness"))

    if int(page.get("response_ms") or 0) > 2500:
        out.append(Issue("slow_response", W, "Slow server response",
                         f"Time to first byte was {page['response_ms']} ms.",
                         "Add caching, a CDN, or reduce server-side work. Target under 600 ms.",
                         url, category="performance", detail={"response_ms": page.get("response_ms")}))

    if int(page.get("size_bytes") or 0) > 3_000_000:
        out.append(Issue("heavy_page", N, "Very large HTML payload",
                         f"HTML is {round(page['size_bytes'] / 1_048_576, 1)} MB.",
                         "Move inline scripts/styles to external cached files and trim unused markup.",
                         url, category="performance"))

    if int(page.get("internal_links") or 0) == 0:
        out.append(Issue("orphan_outlinks", N, "Page links nowhere internally",
                         "A page with no internal outlinks is a dead end for crawlers and users.",
                         "Add contextual links to related pages.", url, category="architecture"))

    if int(page.get("depth") or 0) >= 5:
        out.append(Issue("deep_page", N, "Page is buried deep in the architecture",
                         f"It takes {page['depth']} clicks from the homepage to reach this page.",
                         "Flatten the structure: link important pages from hubs no more than 3 clicks deep.",
                         url, category="architecture", detail={"depth": page.get("depth")}))
    return out


def site_issues(pages: list[dict], *, robots_exists: bool, sitemap_count: int) -> list[Issue]:
    """Rules that only make sense across the whole crawl."""
    out: list[Issue] = []
    html_pages = [p for p in pages if "html" in (p.get("content_type") or "") and 200 <= int(p.get("status_code") or 0) < 300]

    if not robots_exists:
        out.append(Issue("no_robots_txt", W, "No robots.txt",
                         "Crawlers cannot find crawl directives or your sitemap reference.",
                         "Publish /robots.txt with a Sitemap: line.", category="technical"))
    if sitemap_count == 0:
        out.append(Issue("no_sitemap", W, "No XML sitemap found",
                         "Without a sitemap, discovery of new and deep pages relies entirely on internal links.",
                         "Generate /sitemap.xml and reference it from robots.txt and Search Console.",
                         category="technical"))

    titles: dict[str, list[str]] = defaultdict(list)
    descs: dict[str, list[str]] = defaultdict(list)
    for p in html_pages:
        t = (p.get("title") or "").strip().lower()
        d = (p.get("meta_description") or "").strip().lower()
        if t:
            titles[t].append(p["url"])
        if d:
            descs[d].append(p["url"])

    for t, urls in titles.items():
        if len(urls) > 1:
            out.append(Issue("duplicate_title", E, "Duplicate title tag",
                             f"{len(urls)} pages share the title \"{t[:80]}\".",
                             "Give every page a title that describes only that page; consolidate true duplicates.",
                             urls[0], category="on-page", detail={"urls": urls[:20], "count": len(urls)}))
    for urls in descs.values():
        if len(urls) > 1:
            out.append(Issue("duplicate_meta_description", W, "Duplicate meta description",
                             f"{len(urls)} pages share the same description.",
                             "Write a unique description per page, or remove them and let the engine generate snippets.",
                             urls[0], category="on-page", detail={"urls": urls[:20], "count": len(urls)}))

    # Orphans: crawled (from sitemap) but never linked to internally.
    linked: Counter[str] = Counter()
    for p in pages:
        for link in p.get("outlinks") or []:
            linked[normalize_url(link)] += 1
    for p in html_pages:
        if linked.get(normalize_url(p["url"]), 0) == 0 and int(p.get("depth") or 0) > 0:
            out.append(Issue("orphan_page", W, "Orphan page",
                             "This page is in the sitemap but nothing on the site links to it.",
                             "Link to it from a relevant hub or category page, or remove it from the sitemap.",
                             p["url"], category="architecture"))

    schema_pages = sum(1 for p in html_pages if p.get("has_schema"))
    if html_pages and schema_pages / len(html_pages) < 0.3:
        out.append(Issue("low_schema_coverage", W, "Structured data coverage is low",
                         f"Only {schema_pages} of {len(html_pages)} pages carry JSON-LD.",
                         "Roll out JSON-LD by template rather than page by page; start with Organization sitewide.",
                         category="ai-readiness",
                         detail={"with_schema": schema_pages, "total": len(html_pages)}))

    if html_pages:
        avg_words = sum(int(p.get("word_count") or 0) for p in html_pages) / len(html_pages)
        if avg_words < 300:
            out.append(Issue("sitewide_thin_content", W, "Sitewide content depth is low",
                             f"Average body copy is {int(avg_words)} words per page.",
                             "Prioritise depth on the pages that target commercial keywords; consolidate near-duplicates.",
                             category="content", detail={"avg_words": int(avg_words)}))
    return out


def health_score(issues: list[Issue], page_count: int) -> float:
    """0-100 health score, penalty-weighted and normalised by crawl size."""
    if page_count <= 0:
        return 0.0
    penalty = sum(SEVERITY_WEIGHT.get(i.severity, 1.0) for i in issues)
    normalized = penalty / page_count
    return round(max(0.0, min(100.0, 100.0 - normalized * 9.0)), 1)


def ai_readiness_score(page: dict) -> float:
    """How easy this page is for an answer engine to quote correctly."""
    score = 0.0
    if page.get("has_schema"):
        score += 26
    if page.get("title"):
        score += 12
    if page.get("meta_description"):
        score += 8
    if page.get("h1"):
        score += 10
    if int(page.get("h2_count") or 0) >= 2:
        score += 12          # scannable structure is what gets extracted
    words = int(page.get("word_count") or 0)
    if words >= 300:
        score += 12
    if words >= 800:
        score += 6
    if "noindex" not in (page.get("robots_meta") or ""):
        score += 8
    if int(page.get("response_ms") or 9999) < 1200:
        score += 6
    return round(min(100.0, score), 1)
