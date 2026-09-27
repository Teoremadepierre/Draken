"""HTML parsing for the site auditor: everything we extract from one page."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from draken.core.urls import absolutize, is_probably_binary, normalize_url, same_site


@dataclass
class ParsedPage:
    url: str
    title: str = ""
    meta_description: str = ""
    h1: str = ""
    h1_count: int = 0
    h2_count: int = 0
    headings: list[tuple[int, str]] = field(default_factory=list)
    word_count: int = 0
    text: str = ""
    canonical: str = ""
    robots_meta: str = ""
    lang: str = ""
    hreflang: list[dict] = field(default_factory=list)
    internal_links: list[str] = field(default_factory=list)
    external_links: list[dict] = field(default_factory=list)
    images: int = 0
    images_without_alt: int = 0
    schema_types: list[str] = field(default_factory=list)
    schema_blocks: list[dict] = field(default_factory=list)
    open_graph: dict = field(default_factory=dict)
    has_viewport: bool = False
    inline_script_bytes: int = 0
    anchor_texts: list[str] = field(default_factory=list)


_WS = re.compile(r"\s+")


def _text_of(el) -> str:
    return _WS.sub(" ", el.get_text(" ", strip=True)) if el else ""


def parse_html(url: str, html: str) -> ParsedPage:
    soup = BeautifulSoup(html or "", "lxml")
    page = ParsedPage(url=url)

    if soup.title:
        page.title = _text_of(soup.title)[:600]

    html_tag = soup.find("html")
    if html_tag:
        page.lang = (html_tag.get("lang") or "").strip()

    for meta in soup.find_all("meta"):
        name = (meta.get("name") or "").lower()
        prop = (meta.get("property") or "").lower()
        content = (meta.get("content") or "").strip()
        if name == "description":
            page.meta_description = content[:1000]
        elif name == "robots":
            page.robots_meta = content.lower()
        elif name == "viewport":
            page.has_viewport = True
        elif prop.startswith("og:"):
            page.open_graph[prop] = content

    for link in soup.find_all("link"):
        rels = [r.lower() for r in (link.get("rel") or [])]
        href = link.get("href") or ""
        if "canonical" in rels and href:
            page.canonical = normalize_url(absolutize(url, href))
        if "alternate" in rels and link.get("hreflang"):
            page.hreflang.append(
                {"hreflang": link.get("hreflang"), "href": absolutize(url, href)}
            )

    for level in range(1, 7):
        for h in soup.find_all(f"h{level}"):
            txt = _text_of(h)
            if txt:
                page.headings.append((level, txt[:300]))
    h1s = [t for lvl, t in page.headings if lvl == 1]
    page.h1_count = len(h1s)
    page.h1 = h1s[0][:600] if h1s else ""
    page.h2_count = sum(1 for lvl, _ in page.headings if lvl == 2)

    for tag in soup(["script", "style", "noscript", "template"]):
        if tag.name == "script" and not tag.get("src"):
            page.inline_script_bytes += len(tag.get_text() or "")
        tag.decompose()

    body = soup.find("main") or soup.find("article") or soup.find("body") or soup
    page.text = _text_of(body)
    page.word_count = len([w for w in page.text.split() if len(w) > 1])

    for img in soup.find_all("img"):
        page.images += 1
        if not (img.get("alt") or "").strip():
            page.images_without_alt += 1

    seen_internal: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        absolute = absolutize(url, href)
        if not absolute.startswith(("http://", "https://")):
            continue
        anchor = _text_of(a)[:300]
        rel = " ".join(r.lower() for r in (a.get("rel") or []))
        if same_site(url, absolute):
            clean = normalize_url(absolute)
            if clean not in seen_internal and not is_probably_binary(clean):
                seen_internal.add(clean)
                page.internal_links.append(clean)
        else:
            page.external_links.append(
                {"url": normalize_url(absolute), "anchor": anchor, "rel": rel}
            )
        if anchor:
            page.anchor_texts.append(anchor)

    # JSON-LD structured data - the main thing AI crawlers read.
    for script in BeautifulSoup(html or "", "lxml").find_all(
        "script", attrs={"type": re.compile("application/ld\\+json", re.I)}
    ):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for block in data if isinstance(data, list) else [data]:
            if not isinstance(block, dict):
                continue
            page.schema_blocks.append(block)
            t = block.get("@type")
            for name in t if isinstance(t, list) else [t]:
                if isinstance(name, str):
                    page.schema_types.append(name)
            for nested in block.get("@graph") or []:
                if isinstance(nested, dict):
                    page.schema_blocks.append(nested)
                    nt = nested.get("@type")
                    for name in nt if isinstance(nt, list) else [nt]:
                        if isinstance(name, str):
                            page.schema_types.append(name)
    page.schema_types = sorted(set(page.schema_types))
    return page


def extract_links_only(url: str, html: str) -> tuple[list[str], list[dict]]:
    """Cheap link extraction used by the backlink discovery crawler."""
    p = parse_html(url, html)
    return p.internal_links, p.external_links
