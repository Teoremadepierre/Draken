"""Backlink profile analytics: the numbers you actually act on."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from draken.core.models import LinkStatus, LinkType
from draken.core.urls import normalize_domain

# What a healthy anchor distribution looks like for a site not trying to get caught.
ANCHOR_TARGETS = {
    "branded": (0.40, 0.65),
    "naked_url": (0.10, 0.25),
    "generic": (0.05, 0.20),
    "partial_match": (0.05, 0.20),
    "exact_match": (0.00, 0.08),
    "image_empty": (0.00, 0.10),
}

_GENERIC_ANCHORS = {
    "click here", "here", "read more", "learn more", "this site", "website",
    "link", "this link", "more info", "more", "source", "visit", "homepage",
    "aqui", "aquí", "aqui mismo", "leer mas", "leer más", "ver mas", "ver más",
    "saber mas", "saber más", "sitio web", "enlace", "fuente",
}


def classify_anchor(anchor: str, *, brand_terms: list[str], target_domain: str) -> str:
    a = (anchor or "").strip().lower()
    if not a:
        return "image_empty"
    if a.startswith(("http://", "https://", "www.")) or normalize_domain(a) == normalize_domain(target_domain):
        return "naked_url"
    brand_tokens = {b.lower() for b in brand_terms if b} | {normalize_domain(target_domain).split(".")[0]}
    if any(b and b in a for b in brand_tokens):
        return "branded"
    if a in _GENERIC_ANCHORS:
        return "generic"
    if len(a.split()) <= 3:
        return "exact_match"
    return "partial_match"


def authority_score(backlinks: list[dict]) -> float:
    """0-100 composite of referring-domain count, quality and diversity.

    Deliberately logarithmic: going from 10 to 20 referring domains matters far
    more than going from 500 to 510.
    """
    live = [b for b in backlinks if b.get("status") == LinkStatus.live.value]
    if not live:
        return 0.0

    by_domain: dict[str, float] = {}
    for b in live:
        d = b.get("source_domain") or ""
        da = float(b.get("domain_authority") or 0)
        if d:
            by_domain[d] = max(by_domain.get(d, 0.0), da)

    if not by_domain:
        return 0.0

    rd = len(by_domain)
    breadth = min(1.0, math.log10(rd + 1) / math.log10(1001))       # 1000 RDs ~ saturation
    quality = sum(by_domain.values()) / (rd * 100.0)
    dofollow = sum(1 for b in live if b.get("link_type") == LinkType.dofollow.value)
    follow_ratio = dofollow / len(live)
    toxic = sum(1 for b in live if float(b.get("toxicity_score") or 0) >= 50)
    toxic_drag = 1.0 - min(0.4, toxic / max(1, len(live)))

    score = 100.0 * (0.45 * breadth + 0.35 * quality + 0.20 * follow_ratio) * toxic_drag
    return round(max(0.0, min(100.0, score)), 1)


def analyse(
    backlinks: list[dict],
    *,
    target_domain: str,
    brand_terms: list[str] | None = None,
) -> dict:
    brand_terms = brand_terms or []
    total = len(backlinks)
    live = [b for b in backlinks if b.get("status") == LinkStatus.live.value]
    lost = [b for b in backlinks if b.get("status") == LinkStatus.lost.value]

    domains = {b.get("source_domain") for b in live if b.get("source_domain")}
    dofollow = [b for b in live if b.get("link_type") == LinkType.dofollow.value]
    nofollow = [b for b in live if b.get("link_type") in {LinkType.nofollow.value, LinkType.ugc.value, LinkType.sponsored.value}]

    # Anchor distribution
    anchor_buckets: Counter[str] = Counter()
    anchor_texts: Counter[str] = Counter()
    for b in live:
        bucket = classify_anchor(b.get("anchor_text", ""), brand_terms=brand_terms, target_domain=target_domain)
        anchor_buckets[bucket] += 1
        text = (b.get("anchor_text") or "").strip().lower()
        if text:
            anchor_texts[text] += 1

    live_count = max(1, len(live))
    anchor_distribution = [
        {
            "bucket": bucket,
            "count": anchor_buckets.get(bucket, 0),
            "share": round(anchor_buckets.get(bucket, 0) / live_count, 3),
            "target_min": lo,
            "target_max": hi,
            "verdict": _anchor_verdict(anchor_buckets.get(bucket, 0) / live_count, lo, hi),
        }
        for bucket, (lo, hi) in ANCHOR_TARGETS.items()
    ]

    warnings: list[str] = []
    for row in anchor_distribution:
        if row["verdict"] == "too_high":
            warnings.append(
                f"{row['bucket'].replace('_', ' ')} anchors are {row['share']:.0%} of the profile "
                f"(healthy range {row['target_min']:.0%}-{row['target_max']:.0%})"
            )
        elif row["verdict"] == "too_low" and row["bucket"] == "branded":
            warnings.append(
                f"Branded anchors are only {row['share']:.0%}; a natural profile is mostly brand mentions"
            )

    # Top referring domains by authority
    per_domain: dict[str, dict] = defaultdict(lambda: {"links": 0, "authority": 0.0, "dofollow": 0})
    for b in live:
        d = b.get("source_domain") or ""
        if not d:
            continue
        row = per_domain[d]
        row["links"] += 1
        row["authority"] = max(row["authority"], float(b.get("domain_authority") or 0))
        if b.get("link_type") == LinkType.dofollow.value:
            row["dofollow"] += 1
    top_domains = sorted(
        ({"domain": d, **v} for d, v in per_domain.items()),
        key=lambda r: (-r["authority"], -r["links"]),
    )[:50]

    category_mix = [
        {"category": cat or "unclassified", "count": n}
        for cat, n in Counter(b.get("source_category") or "" for b in live).most_common()
    ]

    # Link velocity, last 12 months
    now = datetime.now(UTC)
    velocity: list[dict] = []
    for i in range(11, -1, -1):
        month_start = (now.replace(day=1) - timedelta(days=31 * i)).replace(day=1)
        month_end = (month_start + timedelta(days=32)).replace(day=1)
        gained = sum(1 for b in backlinks if _in_range(b.get("first_seen"), month_start, month_end))
        dropped = sum(1 for b in backlinks if _in_range(b.get("lost_at"), month_start, month_end))
        velocity.append(
            {"month": month_start.strftime("%Y-%m"), "gained": gained, "lost": dropped, "net": gained - dropped}
        )

    toxic = [b for b in live if float(b.get("toxicity_score") or 0) >= 50]
    avg_da = round(sum(float(b.get("domain_authority") or 0) for b in live) / live_count, 1)

    return {
        "total_links": total,
        "referring_domains": len(domains),
        "dofollow_links": len(dofollow),
        "nofollow_links": len(nofollow),
        "live_links": len(live),
        "lost_links": len(lost),
        "avg_domain_authority": avg_da,
        "authority_score": authority_score(backlinks),
        "anchor_distribution": anchor_distribution,
        "anchor_health": {
            "warnings": warnings,
            "unique_anchors": len(anchor_texts),
            "most_common": [{"anchor": a, "count": n} for a, n in anchor_texts.most_common(20)],
            "diversity": round(len(anchor_texts) / live_count, 3),
        },
        "top_domains": top_domains,
        "category_mix": category_mix,
        "toxic_links": len(toxic),
        "velocity": velocity,
        "recommendations": recommendations(
            referring_domains=len(domains),
            avg_da=avg_da,
            dofollow_ratio=len(dofollow) / live_count,
            toxic_count=len(toxic),
            anchor_warnings=warnings,
            lost_count=len(lost),
            category_mix=category_mix,
        ),
    }


def _anchor_verdict(share: float, lo: float, hi: float) -> str:
    if share > hi:
        return "too_high"
    if share < lo:
        return "too_low"
    return "healthy"


def _in_range(value, start: datetime, end: datetime) -> bool:
    if not value:
        return False
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return start <= value < end


def recommendations(
    *,
    referring_domains: int,
    avg_da: float,
    dofollow_ratio: float,
    toxic_count: int,
    anchor_warnings: list[str],
    lost_count: int,
    category_mix: list[dict],
) -> list[str]:
    """Prioritised, specific next actions - not generic advice."""
    out: list[str] = []

    if referring_domains == 0:
        out.append(
            "You have zero referring domains. Do not start with outreach - start with the "
            "foundation tier: claim every brand and business profile, then the free "
            "dofollow directories. Target 30 referring domains in month one."
        )
    elif referring_domains < 10:
        out.append(
            f"Only {referring_domains} referring domains. Finish the foundation tier "
            "(profiles, citations, marketplaces) before spending time on editorial outreach."
        )
    elif referring_domains < 50:
        out.append(
            f"{referring_domains} referring domains. Foundation is in place - shift effort to "
            "unlinked-mention reclamation and resource-page prospecting, which convert fastest."
        )
    else:
        out.append(
            f"{referring_domains} referring domains. You are past the foundation: the marginal link "
            "now has to be more relevant, not just more. Prioritise topical authority over volume."
        )

    if avg_da < 30 and referring_domains > 5:
        out.append(
            f"Average referring-domain authority is {avg_da:.0f}. Skew the next 20 links towards "
            "authority: review platforms, integration marketplaces, research/dataset platforms."
        )
    if dofollow_ratio < 0.25 and referring_domains > 10:
        out.append(
            f"Only {dofollow_ratio:.0%} of links are dofollow. Filter the opportunity list to "
            "dofollow sources - AI directories, dev platforms and package registries are the reliable ones."
        )
    if toxic_count:
        out.append(
            f"{toxic_count} link(s) score 50+ on toxicity. Request removal first; disavow only what "
            "you cannot get removed and only if you see an actual ranking problem."
        )
    for w in anchor_warnings[:3]:
        out.append(f"Anchor risk: {w}. Correct it with the anchor mix on your next campaign, not retroactively.")
    if lost_count > max(3, referring_domains * 0.1):
        out.append(
            f"{lost_count} links have been lost. Run link reclamation on these first - recovering an "
            "existing link is cheaper than earning a new one."
        )

    cats = {c["category"] for c in category_mix}
    if len(cats) <= 2 and referring_domains > 15:
        out.append(
            "Your profile comes from very few source types, which is itself a footprint. "
            "Diversify across categories: editorial, community, marketplace, local, research."
        )
    return out
