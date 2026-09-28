"""Opportunity scoring - the model that decides what to work on first.

Five weighted factors, all normalised 0-1, every one returned in a breakdown so
the number is auditable in the UI:

  authority   how strong is the linking domain
  relevance   does it match our country / language / industry
  ease        how little work is it (inverse of effort, plus automatability)
  follow      does the link actually transfer equity
  evidence    do competitors already have this link (proof it is obtainable)

Plus a GEO bonus for sources that feed AI training data and answer citations,
because a link that gets you quoted by an assistant is worth more than its
PageRank suggests.
"""

from __future__ import annotations

from dataclasses import dataclass

from draken.core.models import LinkType

WEIGHTS = {
    "authority": 0.30,
    "relevance": 0.24,
    "ease": 0.16,
    "follow": 0.14,
    "evidence": 0.16,
}

GEO_BONUS_MAX = 12.0


@dataclass
class ScoredOpportunity:
    score: float
    breakdown: dict
    authority: float
    relevance: float
    effort: int
    tactic: str


def relevance_for(
    source: dict,
    *,
    project_country: str = "",
    project_language: str = "",
    project_industry: str = "",
) -> float:
    """0-1 relevance of a catalog source to this specific project."""
    score = 0.35  # a generic but legitimate source is still somewhat relevant

    countries = [c.upper() for c in (source.get("countries") or [])]
    if not countries or "*" in countries:
        score += 0.12
    elif project_country and project_country.upper() in countries:
        score += 0.28
    else:
        score -= 0.22  # wrong country directory is close to worthless

    languages = [link.lower() for link in (source.get("languages") or [])]
    if not languages or "*" in languages:
        score += 0.08
    elif project_language and project_language.lower() in languages:
        score += 0.18
    else:
        score -= 0.10

    industries = [i.lower() for i in (source.get("industries") or [])]
    if project_industry:
        pi = project_industry.lower()
        if any(pi in i or i in pi for i in industries if i != "*"):
            score += 0.30       # a vertical directory in our own vertical
        elif "*" in industries or not industries:
            score += 0.05
        else:
            score -= 0.18       # a vertical directory in someone else's vertical
    elif "*" in industries or not industries:
        score += 0.05

    tags = {t.lower() for t in (source.get("tags") or [])}
    if "foundation" in tags:
        score += 0.15
    if "low-value" in tags:
        score -= 0.30
    if "high-risk" in tags:
        score -= 0.10

    return round(max(0.0, min(1.0, score)), 3)


def score_source(
    source: dict,
    *,
    project_country: str = "",
    project_language: str = "",
    project_industry: str = "",
    competitor_links: int = 0,
    already_have_domains: set[str] | None = None,
) -> ScoredOpportunity:
    already_have_domains = already_have_domains or set()

    authority = float(source.get("authority") or 0.0)
    authority_n = min(1.0, authority / 95.0)

    relevance_n = relevance_for(
        source,
        project_country=project_country,
        project_language=project_language,
        project_industry=project_industry,
    )

    effort = int(source.get("effort") or 3)
    ease_n = (6 - max(1, min(5, effort))) / 5.0
    if source.get("automatable"):
        ease_n = min(1.0, ease_n + 0.15)
    if source.get("requires_account"):
        ease_n = max(0.0, ease_n - 0.08)
    if not source.get("is_free", True):
        ease_n = max(0.0, ease_n - 0.20)

    link_type = source.get("link_type") or LinkType.unknown.value
    follow_n = {
        LinkType.dofollow.value: 1.0,
        LinkType.unknown.value: 0.5,
        LinkType.ugc.value: 0.28,
        LinkType.nofollow.value: 0.25,
        LinkType.sponsored.value: 0.15,
    }.get(link_type, 0.4)

    # Evidence: competitors having the link proves it is obtainable for a site like ours.
    evidence_n = min(1.0, competitor_links / 3.0) if competitor_links else 0.0

    base = 100.0 * sum(
        WEIGHTS[k] * v
        for k, v in (
            ("authority", authority_n),
            ("relevance", relevance_n),
            ("ease", ease_n),
            ("follow", follow_n),
            ("evidence", evidence_n),
        )
    )

    geo_bonus = GEO_BONUS_MAX * float(source.get("llm_citation_weight") or 0.0)
    if source.get("ai_training_signal"):
        geo_bonus += 2.0

    penalty = 0.0
    if source.get("domain") in already_have_domains:
        penalty += 45.0   # we already have this link; near-zero marginal value

    total = round(max(0.0, min(100.0, base + geo_bonus - penalty)), 1)

    return ScoredOpportunity(
        score=total,
        breakdown={
            "authority": round(authority_n, 3),
            "relevance": relevance_n,
            "ease": round(ease_n, 3),
            "follow": round(follow_n, 3),
            "evidence": round(evidence_n, 3),
            "geo_bonus": round(geo_bonus, 2),
            "duplicate_penalty": penalty,
            "weights": WEIGHTS,
            "base": round(base, 1),
        },
        authority=authority,
        relevance=round(relevance_n * 100, 1),
        effort=effort,
        tactic=source.get("category") or "directory",
    )


def score_prospect(
    *,
    domain: str,
    authority: float,
    competitor_links: int,
    link_type: str = LinkType.unknown.value,
    topical_match: float = 0.5,
    tactic: str = "resource_page",
    already_have_domains: set[str] | None = None,
) -> ScoredOpportunity:
    """Score a prospected (non-catalog) opportunity found via competitor links."""
    pseudo_source = {
        "domain": domain,
        "authority": authority,
        "link_type": link_type,
        "effort": 4 if tactic in {"guest_post", "resource_page"} else 3,
        "automatable": False,
        "requires_account": False,
        "is_free": True,
        "countries": ["*"],
        "languages": ["*"],
        "industries": ["*"],
        "tags": [],
        "llm_citation_weight": 0.0,
        "category": tactic,
    }
    scored = score_source(
        pseudo_source,
        competitor_links=competitor_links,
        already_have_domains=already_have_domains,
    )
    # Replace the generic relevance with the measured topical match.
    adjusted = scored.score + (topical_match - 0.5) * 20.0
    scored.score = round(max(0.0, min(100.0, adjusted)), 1)
    scored.relevance = round(topical_match * 100, 1)
    scored.breakdown["topical_match"] = round(topical_match, 3)
    scored.tactic = tactic
    return scored


def suggest_anchor(
    *,
    brand: str,
    target_keyword: str = "",
    tactic: str,
    existing_anchor_mix: dict[str, int] | None = None,
) -> str:
    """Pick an anchor that keeps the overall profile in a healthy range.

    Most of the time the right answer is the brand name. Exact-match anchors are
    only ever suggested when the profile is short of them AND the tactic is one
    where an editorial anchor is natural.
    """
    mix = existing_anchor_mix or {}
    total = sum(mix.values()) or 1
    exact_share = mix.get("exact_match", 0) / total
    branded_share = mix.get("branded", 0) / total

    if tactic in {"directory", "local_citation", "business_profile", "social_profile",
                  "developer_profile", "review_platform", "startup_listing",
                  "product_listing", "aggregator", "podcast"}:
        return brand           # listings should always be branded; anything else is a footprint

    if branded_share < 0.4:
        return brand
    if target_keyword and exact_share < 0.06 and tactic in {"resource_page", "guest_post", "blog_platform"}:
        return target_keyword
    if target_keyword:
        return f"{brand} {target_keyword}".strip()
    return brand
