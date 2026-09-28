"""Opportunity generation: turn the catalog plus competitor recon into a work queue."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from draken.core.logging import get_logger
from draken.core.models import LinkType, OpportunityStatus
from draken.core.urls import normalize_domain
from draken.data import loader
from draken.engines.backlinks import discovery
from draken.engines.keywords.cluster import content_tokens
from draken.engines.opportunities import scoring
from draken.engines.serp import authority as authority_mod

log = get_logger(__name__)


@dataclass
class GeneratedOpportunity:
    target_domain: str
    source_slug: str = ""
    target_url: str = ""
    tactic: str = "directory"
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    authority: float = 0.0
    relevance: float = 0.0
    effort: int = 3
    suggested_anchor: str = ""
    discovered_via: str = "catalog"
    competitor_links: int = 0
    notes: str = ""
    contact_form_url: str = ""
    meta: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["status"] = OpportunityStatus.new.value
        return d


def from_catalog(
    *,
    project_country: str = "US",
    project_language: str = "en",
    project_industry: str = "",
    brand: str = "",
    target_keyword: str = "",
    existing_domains: set[str] | None = None,
    anchor_mix: dict[str, int] | None = None,
    categories: list[str] | None = None,
    countries: list[str] | None = None,
    max_effort: int = 5,
    only_free: bool = True,
    only_dofollow: bool = False,
    include_ai_sources: bool = True,
    competitor_domain_counts: dict[str, int] | None = None,
    limit: int = 200,
) -> list[GeneratedOpportunity]:
    """Score every catalog source for this project and return the best N."""
    sources = loader.link_sources()
    existing_domains = existing_domains or set()
    competitor_domain_counts = competitor_domain_counts or {}
    wanted_categories = {c.lower() for c in (categories or [])}
    wanted_countries = {c.upper() for c in (countries or [])}

    out: list[GeneratedOpportunity] = []
    for src in sources:
        if not src.get("is_enabled", True):
            continue
        if src.get("domain") == "*":
            # Tactic template, not a submittable destination - surfaced separately.
            continue
        if wanted_categories and (src.get("category") or "").lower() not in wanted_categories:
            continue
        if wanted_countries:
            src_countries = {c.upper() for c in (src.get("countries") or [])}
            if "*" not in src_countries and not (src_countries & wanted_countries):
                continue
        if int(src.get("effort") or 3) > max_effort:
            continue
        if only_free and not src.get("is_free", True):
            continue
        if only_dofollow and src.get("link_type") != LinkType.dofollow.value:
            continue
        if not include_ai_sources and src.get("category") == "ai_dataset":
            continue

        domain = src.get("domain") or ""
        scored = scoring.score_source(
            src,
            project_country=project_country,
            project_language=project_language,
            project_industry=project_industry,
            competitor_links=competitor_domain_counts.get(domain, 0),
            already_have_domains=existing_domains,
        )
        if scored.score <= 0:
            continue

        out.append(
            GeneratedOpportunity(
                target_domain=domain,
                source_slug=src.get("slug", ""),
                target_url=src.get("submit_url") or f"https://{domain}",
                tactic=src.get("category") or "directory",
                score=scored.score,
                score_breakdown=scored.breakdown,
                authority=scored.authority,
                relevance=scored.relevance,
                effort=scored.effort,
                suggested_anchor=scoring.suggest_anchor(
                    brand=brand or domain.split(".")[0],
                    target_keyword=target_keyword,
                    tactic=src.get("category") or "directory",
                    existing_anchor_mix=anchor_mix,
                ),
                discovered_via="catalog",
                competitor_links=competitor_domain_counts.get(domain, 0),
                notes=src.get("notes", ""),
                meta={
                    "required_fields": src.get("required_fields") or [],
                    "guidelines_url": src.get("guidelines_url", ""),
                    "requires_account": src.get("requires_account", True),
                    "automatable": src.get("automatable", False),
                    "llm_citation_weight": src.get("llm_citation_weight", 0.0),
                    "ai_training_signal": src.get("ai_training_signal", False),
                    "link_type": src.get("link_type"),
                    "source_name": src.get("name"),
                },
            )
        )

    out.sort(key=lambda o: (-o.score, o.effort, o.target_domain))
    return out[:limit]


def tactic_playbook() -> list[dict]:
    """The non-submittable tactics from the catalog, as a work checklist."""
    return [
        {
            "slug": s["slug"],
            "name": s["name"],
            "tactic": s["category"],
            "effort": s["effort"],
            "link_type": s["link_type"],
            "tags": s.get("tags") or [],
            "notes": s.get("notes", ""),
        }
        for s in loader.link_sources()
        if s.get("domain") == "*"
    ]


def _topical_match(anchor_and_title: str, project_tokens: set[str]) -> float:
    """How topically close a prospect page is to what we do."""
    if not project_tokens:
        return 0.5
    tokens = content_tokens(anchor_and_title)
    if not tokens:
        return 0.4
    overlap = len(tokens & project_tokens) / max(1, min(len(tokens), len(project_tokens)))
    return round(min(1.0, 0.3 + overlap * 0.8), 3)


async def from_competitors(
    *,
    competitors: list[str],
    project_domain: str,
    project_keywords: list[str] | None = None,
    brand: str = "",
    existing_domains: set[str] | None = None,
    anchor_mix: dict[str, int] | None = None,
    country: str = "US",
    language: str = "en",
    limit: int = 150,
    min_competitors: int = 1,
) -> tuple[list[GeneratedOpportunity], list[dict]]:
    """Link intersect: find domains linking to competitors but not to us.

    Returns ``(opportunities, raw_competitor_links)``. The second value is stored
    so the same recon does not have to be repeated on the next run.
    """
    existing_domains = existing_domains or set()
    project_domain = normalize_domain(project_domain)
    competitors = [normalize_domain(c) for c in competitors if c]
    competitors = [c for c in competitors if c and c != project_domain]
    if not competitors:
        return [], []

    project_tokens: set[str] = set()
    for kw in (project_keywords or [])[:60]:
        project_tokens |= content_tokens(kw)

    raw_links: list[dict] = []
    domain_hits: dict[str, set[str]] = {}
    domain_context: dict[str, str] = {}
    domain_link_type: dict[str, str] = {}

    for competitor in competitors[:6]:
        try:
            links = await discovery.discover_competitor_links(
                competitor, country=country, language=language
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("competitor recon failed for %s: %s", competitor, exc)
            continue
        for link in links:
            src_domain = link.source_domain
            if not src_domain or src_domain == project_domain or src_domain in competitors:
                continue
            raw_links.append(
                {
                    "competitor_domain": competitor,
                    "source_url": link.source_url,
                    "source_domain": src_domain,
                    "anchor_text": link.anchor_text,
                    "link_type": link.link_type,
                    "domain_authority": link.domain_authority,
                    "discovered_via": link.discovered_via,
                }
            )
            domain_hits.setdefault(src_domain, set()).add(competitor)
            if link.anchor_text:
                domain_context[src_domain] = f"{domain_context.get(src_domain, '')} {link.anchor_text}".strip()
            if link.link_type == LinkType.dofollow.value:
                domain_link_type[src_domain] = LinkType.dofollow.value
            else:
                domain_link_type.setdefault(src_domain, link.link_type)

    gap_domains = {
        d: comps for d, comps in domain_hits.items()
        if len(comps) >= min_competitors and d not in existing_domains
    }
    if not gap_domains:
        return [], raw_links

    auth_map = await authority_mod.authority_for(list(gap_domains))

    out: list[GeneratedOpportunity] = []
    for domain, comps in gap_domains.items():
        auth = auth_map.get(domain, 0.0)
        match = _topical_match(domain_context.get(domain, domain), project_tokens)
        tactic = "resource_page"
        ctx = (domain_context.get(domain, "") + " " + domain).lower()
        if any(k in ctx for k in ("alternative", "vs", "compare", "review")):
            tactic = "resource_page"
        elif any(k in ctx for k in ("blog", "guest", "contributor")):
            tactic = "guest_post"

        scored = scoring.score_prospect(
            domain=domain,
            authority=auth,
            competitor_links=len(comps),
            link_type=domain_link_type.get(domain, LinkType.unknown.value),
            topical_match=match,
            tactic=tactic,
            already_have_domains=existing_domains,
        )
        out.append(
            GeneratedOpportunity(
                target_domain=domain,
                target_url=next(
                    (
                        row["source_url"]
                        for row in raw_links
                        if row["source_domain"] == domain
                    ),
                    f"https://{domain}",
                ),
                tactic=tactic,
                score=scored.score,
                score_breakdown=scored.breakdown,
                authority=auth,
                relevance=scored.relevance,
                effort=scored.effort,
                suggested_anchor=scoring.suggest_anchor(
                    brand=brand or project_domain.split(".")[0],
                    tactic=tactic,
                    existing_anchor_mix=anchor_mix,
                ),
                discovered_via="link_intersect",
                competitor_links=len(comps),
                notes=(
                    f"Links to {len(comps)} of your competitors ({', '.join(sorted(comps))}) but not to you. "
                    "That is proof the link is obtainable for a site like yours."
                ),
                meta={"competitors": sorted(comps), "link_type": domain_link_type.get(domain)},
            )
        )

    out.sort(key=lambda o: (-o.score, -o.competitor_links))
    log.info(
        "link intersect: %d competitor links -> %d gap domains -> %d opportunities",
        len(raw_links), len(gap_domains), len(out),
    )
    return out[:limit], raw_links


async def from_unlinked_mentions(
    *,
    project_domain: str,
    brand_terms: list[str],
    brand: str = "",
    country: str = "US",
    language: str = "en",
    existing_domains: set[str] | None = None,
    limit: int = 60,
) -> list[GeneratedOpportunity]:
    """The fastest-converting tactic: pages that name us but do not link to us."""
    existing_domains = existing_domains or set()
    links = await discovery.discover_mentions(
        domain=project_domain, brand_terms=brand_terms, country=country, language=language
    )
    candidates = [
        link for link in links
        if link.meta.get("unlinked_mention") and link.source_domain not in existing_domains
    ]
    if not candidates:
        return []

    auth_map = await authority_mod.authority_for([link.source_domain for link in candidates])
    out: list[GeneratedOpportunity] = []
    for link in candidates:
        auth = auth_map.get(link.source_domain, 0.0)
        scored = scoring.score_prospect(
            domain=link.source_domain,
            authority=auth,
            competitor_links=0,
            topical_match=0.8,        # they already wrote about us
            tactic="unlinked_mention",
            already_have_domains=existing_domains,
        )
        # Reclamation converts far better than cold outreach - reflect that.
        scored.score = round(min(100.0, scored.score + 18.0), 1)
        out.append(
            GeneratedOpportunity(
                target_domain=link.source_domain,
                target_url=link.source_url,
                tactic="unlinked_mention",
                score=scored.score,
                score_breakdown=scored.breakdown,
                authority=auth,
                relevance=80.0,
                effort=2,
                suggested_anchor=brand or project_domain.split(".")[0],
                discovered_via="mention_search",
                notes="This page mentions your brand without linking. One short email is usually enough.",
                meta={"source_url": link.source_url},
            )
        )
    out.sort(key=lambda o: -o.score)
    return out[:limit]


def summarise(opportunities: list[dict]) -> dict:
    """Pipeline overview for the dashboard."""
    by_status = Counter(o.get("status", "new") for o in opportunities)
    by_tactic = Counter(o.get("tactic", "other") for o in opportunities)
    scores = [float(o.get("score") or 0) for o in opportunities]
    won = [o for o in opportunities if o.get("status") == OpportunityStatus.won.value]
    worked = [
        o for o in opportunities
        if o.get("status") in {
            OpportunityStatus.submitted.value, OpportunityStatus.awaiting_review.value,
            OpportunityStatus.won.value, OpportunityStatus.rejected.value,
        }
    ]
    return {
        "total": len(opportunities),
        "by_status": dict(by_status),
        "by_tactic": dict(by_tactic),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        "high_priority": sum(1 for s in scores if s >= 60),
        "quick_wins": sum(
            1 for o in opportunities
            if float(o.get("score") or 0) >= 45 and int(o.get("effort") or 3) <= 2
        ),
        "won": len(won),
        "conversion_rate": round(len(won) / len(worked), 3) if worked else 0.0,
    }
