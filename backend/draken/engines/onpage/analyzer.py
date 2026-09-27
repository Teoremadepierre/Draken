"""On-page analyzer: score one URL against one target keyword.

Equivalent of the "on page SEO checker" in a commercial suite. Returns a
prioritised list of concrete edits rather than a vague grade.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from draken.engines.crawler.crawler import fetch_single_page
from draken.engines.keywords.cluster import content_tokens
from draken.engines.keywords.metrics import tokenize


@dataclass
class Recommendation:
    priority: str          # high | medium | low
    area: str
    issue: str
    action: str
    current: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class OnPageReport:
    url: str
    target_keyword: str
    score: float = 0.0
    status_code: int = 0
    error: str = ""
    metrics: dict = field(default_factory=dict)
    recommendations: list[dict] = field(default_factory=list)
    keyword_placement: dict = field(default_factory=dict)
    entities: list[dict] = field(default_factory=list)
    readability: dict = field(default_factory=dict)
    ai_readiness: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "target_keyword": self.target_keyword,
            "score": self.score,
            "status_code": self.status_code,
            "error": self.error,
            "metrics": self.metrics,
            "recommendations": self.recommendations,
            "keyword_placement": self.keyword_placement,
            "entities": self.entities,
            "readability": self.readability,
            "ai_readiness": self.ai_readiness,
        }


_SENTENCE_RE = re.compile(r"[.!?]+(?:\s|$)")


def _readability(text: str) -> dict:
    words = [w for w in text.split() if w.strip()]
    sentences = [s for s in _SENTENCE_RE.split(text) if s.strip()]
    if not words or not sentences:
        return {"words": len(words), "sentences": len(sentences), "avg_sentence_length": 0,
                "long_sentence_share": 0.0, "verdict": "insufficient text"}
    lengths = [len(s.split()) for s in sentences]
    avg = sum(lengths) / len(lengths)
    long_share = sum(1 for n in lengths if n > 30) / len(lengths)
    if avg <= 16 and long_share < 0.15:
        verdict = "easy to scan"
    elif avg <= 24:
        verdict = "acceptable"
    else:
        verdict = "hard to read - split long sentences"
    return {
        "words": len(words),
        "sentences": len(sentences),
        "avg_sentence_length": round(avg, 1),
        "long_sentence_share": round(long_share, 3),
        "verdict": verdict,
    }


def _density(text: str, phrase: str) -> tuple[int, float]:
    if not phrase:
        return 0, 0.0
    words = tokenize(text)
    phrase_tokens = tokenize(phrase)
    if not words or not phrase_tokens:
        return 0, 0.0
    n = len(phrase_tokens)
    count = sum(
        1 for i in range(len(words) - n + 1) if words[i : i + n] == phrase_tokens
    )
    return count, round(count * n / len(words) * 100, 2)


async def analyse_url(
    url: str, *, target_keyword: str = "", secondary_keywords: list[str] | None = None
) -> OnPageReport:
    secondary_keywords = [k for k in (secondary_keywords or []) if k.strip()]
    record, parsed = await fetch_single_page(url)
    report = OnPageReport(url=record.get("url", url), target_keyword=target_keyword)
    report.status_code = int(record.get("status_code") or 0)

    if parsed is None:
        report.error = record.get("error") or f"HTTP {report.status_code}"
        report.recommendations = [
            Recommendation(
                "high", "availability", "The page could not be fetched",
                "Fix availability first - nothing else matters until the page responds with 200.",
                report.error,
            ).as_dict()
        ]
        return report

    text = parsed.text
    kw = target_keyword.strip().lower()
    recs: list[Recommendation] = []

    title = parsed.title
    desc = parsed.meta_description
    h1 = parsed.h1
    h2s = [t for lvl, t in parsed.headings if lvl == 2]

    in_title = kw in title.lower() if kw else False
    in_desc = kw in desc.lower() if kw else False
    in_h1 = kw in h1.lower() if kw else False
    in_h2 = any(kw in h.lower() for h in h2s) if kw else False
    in_url = kw.replace(" ", "-") in report.url.lower() if kw else False
    first_100 = " ".join(text.split()[:100]).lower()
    in_intro = kw in first_100 if kw else False

    count, density = _density(text, kw)

    report.keyword_placement = {
        "in_title": in_title, "in_meta_description": in_desc, "in_h1": in_h1,
        "in_h2": in_h2, "in_url": in_url, "in_first_100_words": in_intro,
        "occurrences": count, "density_percent": density,
    }

    if kw:
        if not in_title:
            recs.append(Recommendation("high", "title", f"'{target_keyword}' is not in the title tag",
                f"Rewrite the title to lead with '{target_keyword}'.", title))
        if not in_h1:
            recs.append(Recommendation("high", "h1", f"'{target_keyword}' is not in the H1",
                f"Put '{target_keyword}' in the H1, phrased naturally.", h1))
        if not in_intro:
            recs.append(Recommendation("high", "intro", f"'{target_keyword}' does not appear in the first 100 words",
                "State the topic in the opening paragraph - both readers and extractive models weight it heavily."))
        if not in_desc:
            recs.append(Recommendation("medium", "meta", f"'{target_keyword}' is not in the meta description",
                f"Include '{target_keyword}' plus a reason to click, within 155 characters.", desc))
        if not in_url:
            recs.append(Recommendation("low", "url", "Keyword is not in the URL slug",
                "Only change the slug on a new page; retro-fitting means a redirect, which is rarely worth it."))
        if density > 3.5:
            recs.append(Recommendation("medium", "content", f"Keyword density is {density}% - over-optimised",
                "Cut repetitions and use synonyms and related entities instead.", f"{count} occurrences"))
        elif count == 0:
            recs.append(Recommendation("high", "content", "Keyword never appears in the body copy",
                f"Work '{target_keyword}' into the body naturally, including one H2."))
        if not in_h2 and h2s:
            recs.append(Recommendation("low", "structure", "No H2 contains the keyword or a variant",
                "Use subheadings that mirror the questions people ask about this topic."))

    if not title:
        recs.append(Recommendation("high", "title", "Missing title tag", "Add a 40-60 character title."))
    elif len(title) > 65:
        recs.append(Recommendation("low", "title", f"Title is {len(title)} characters",
            "Trim to about 60 so it is not truncated.", title))
    if not desc:
        recs.append(Recommendation("medium", "meta", "Missing meta description",
            "Write 140-160 characters that earn the click."))
    if parsed.h1_count > 1:
        recs.append(Recommendation("low", "h1", f"{parsed.h1_count} H1 tags",
            "Keep one H1 and demote the rest."))
    if len(h2s) < 2 and parsed.word_count > 400:
        recs.append(Recommendation("medium", "structure", "Very few H2 subheadings",
            "Add an H2 every 200-300 words. Scannable structure is what answer engines extract."))
    if parsed.word_count < 300:
        recs.append(Recommendation("high", "content", f"Only {parsed.word_count} words of copy",
            "Expand to genuinely answer the query, or consolidate this page into a stronger one."))
    if parsed.images_without_alt:
        recs.append(Recommendation("low", "accessibility", f"{parsed.images_without_alt} images without alt text",
            "Describe each image; it is an accessibility requirement and an image-search signal."))
    if not parsed.schema_types:
        recs.append(Recommendation("high", "ai-readiness", "No JSON-LD structured data",
            "Add JSON-LD for the page type. This is the main machine-readable description of your entity."))
    if len(parsed.internal_links) < 3:
        recs.append(Recommendation("medium", "internal-links", f"Only {len(parsed.internal_links)} internal links",
            "Link to 3-8 related pages with descriptive anchors to pass equity and context."))
    if not parsed.open_graph.get("og:title"):
        recs.append(Recommendation("low", "social", "No Open Graph tags",
            "Add og:title, og:description and og:image so shares render properly."))

    for sk in secondary_keywords[:10]:
        c, _ = _density(text, sk)
        if c == 0:
            recs.append(Recommendation("low", "content", f"Secondary keyword '{sk}' is absent",
                f"Cover '{sk}' in a subsection if it is genuinely part of this topic."))

    report.readability = _readability(text)
    if report.readability.get("verdict", "").startswith("hard"):
        recs.append(Recommendation("medium", "readability",
            f"Average sentence length is {report.readability['avg_sentence_length']} words",
            "Split sentences over 30 words. Short sentences get quoted; long ones get skipped."))

    # Entities / topical coverage: what the page is actually about.
    tokens = [t for t in content_tokens(text) if len(t) > 3]
    freq = Counter(t for t in tokenize(text) if len(t) > 3 and t in tokens)
    report.entities = [{"term": t, "count": n} for t, n in freq.most_common(25)]

    report.ai_readiness = {
        "score": record.get("ai_readiness", 0.0),
        "has_schema": bool(parsed.schema_types),
        "schema_types": parsed.schema_types,
        "has_faq_schema": any(s in {"FAQPage", "QAPage"} for s in parsed.schema_types),
        "has_organization_schema": "Organization" in parsed.schema_types,
        "heading_structure_depth": len({lvl for lvl, _ in parsed.headings}),
        "quotable_sections": len(h2s),
        "notes": _ai_notes(parsed),
    }

    report.metrics = {
        "status_code": report.status_code,
        "title_length": len(title),
        "meta_description_length": len(desc),
        "word_count": parsed.word_count,
        "h2_count": len(h2s),
        "internal_links": len(parsed.internal_links),
        "external_links": len(parsed.external_links),
        "images": parsed.images,
        "images_without_alt": parsed.images_without_alt,
        "response_ms": record.get("response_ms", 0),
        "schema_types": parsed.schema_types,
        "canonical": parsed.canonical,
        "lang": parsed.lang,
    }

    order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: order.get(r.priority, 3))
    report.recommendations = [r.as_dict() for r in recs]
    report.score = _score(report, recs)
    return report


def _ai_notes(parsed) -> list[str]:
    notes: list[str] = []
    if not parsed.schema_types:
        notes.append("No structured data: answer engines have to infer your entity from prose.")
    if "FAQPage" not in parsed.schema_types and any(
        h.strip().endswith("?") for _lvl, h in parsed.headings
    ):
        notes.append("You have question-shaped headings but no FAQPage schema - add it.")
    if parsed.word_count and not any(lvl == 2 for lvl, _ in parsed.headings):
        notes.append("No H2s: there are no extractable sections for an answer engine to quote.")
    if not parsed.open_graph:
        notes.append("No Open Graph metadata, which several crawlers use as a title/description fallback.")
    if not notes:
        notes.append("Structure is machine-readable. Next lever is citations from sources models trust.")
    return notes


def _score(report: OnPageReport, recs: list[Recommendation]) -> float:
    penalty = sum({"high": 12.0, "medium": 5.0, "low": 1.5}.get(r.priority, 1.0) for r in recs)
    return round(max(0.0, min(100.0, 100.0 - penalty)), 1)
