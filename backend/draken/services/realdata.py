"""Import measured first-party data and merge it over the estimates.

The rule this module implements: **a measured number always wins over an
estimate, and the confidence flag is set to 1.0 so the interface stops labelling
it as approximate.**

Two sources:
  * Google Search Console - real impressions, clicks, CTR and average position
    per query and per page.
  * Bing Webmaster Tools  - the same for Bing, plus a free inbound-link report.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.core.logging import get_logger
from draken.core.models import (
    ActivityLog,
    Backlink,
    Keyword,
    LinkStatus,
    LinkType,
    Project,
    RankSnapshot,
    utcnow,
)
from draken.engines.backlinks import toxicity
from draken.engines.keywords import metrics
from draken.engines.providers import bing_webmaster, search_console
from draken.engines.serp import authority as authority_mod

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Search Console
# ---------------------------------------------------------------------------


async def import_search_console(
    db: Session,
    *,
    project: Project,
    days: int = 28,
    limit: int = 2000,
    track_top: int = 0,
) -> dict:
    """Pull real query performance and overwrite the estimated numbers.

    ``track_top`` marks the N highest-impression queries as tracked, which is
    usually what you want on a first import: they are, by definition, the terms
    you already rank for.
    """
    if not search_console.is_configured():
        return {
            "imported": 0,
            "error": search_console.configuration_hint(),
            "configured": False,
        }

    result = await search_console.top_queries(domain=project.domain, days=days, limit=limit)
    if not result.ok:
        return {"imported": 0, "error": result.error, "configured": True,
                "site_url": result.site_url}

    existing = {
        (k.term, k.country): k
        for k in db.execute(select(Keyword).where(Keyword.project_id == project.id)).scalars()
    }

    created = updated = snapshots = 0
    today = datetime.now(UTC).date()
    rows = sorted(result.rows, key=lambda r: -r.impressions)

    for i, row in enumerate(rows):
        term = " ".join((row.query or "").split()).lower()
        if not term:
            continue

        keyword = existing.get((term, project.country))
        if keyword is None:
            intent = metrics.classify_intent(term, brand_terms=list(project.brand_terms or []))
            keyword = Keyword(
                project_id=project.id,
                term=term,
                country=project.country,
                language=project.language,
                intent=intent.value,
                word_count=len(metrics.tokenize(term)),
                is_question=metrics.is_question(term),
                is_branded=any(b and b.lower() in term for b in (project.brand_terms or [])),
                source="search_console",
            )
            db.add(keyword)
            db.flush()
            existing[(term, project.country)] = keyword
            created += 1
        else:
            updated += 1

        # Impressions over the window, projected to a monthly figure. This is a
        # measurement of demand we actually received, not a modelled estimate.
        monthly = int(round(row.impressions * (30.0 / max(days, 1))))
        keyword.volume = monthly
        keyword.volume_confidence = 1.0
        keyword.source = "search_console" if keyword.source in ("", "expansion", "modifier") else keyword.source
        keyword.meta_json = {
            **(keyword.meta_json or {}),
            "gsc": {
                "clicks": row.clicks,
                "impressions": row.impressions,
                "ctr": round(row.ctr, 4),
                "position": round(row.position, 2),
                "window_days": days,
                "imported_at": utcnow().isoformat(),
            },
        }
        keyword.opportunity_score = metrics.opportunity_score(
            volume=keyword.volume,
            difficulty=keyword.difficulty or 50.0,
            intent=keyword.intent,
            current_position=int(round(row.position)) if row.position else None,
            is_branded=keyword.is_branded,
        )
        if track_top and i < track_top:
            keyword.is_tracked = True

        # Record the measured position as a snapshot so the trend is real data.
        if row.position:
            position = int(round(row.position))
            previous = db.execute(
                select(RankSnapshot)
                .where(RankSnapshot.keyword_id == keyword.id, RankSnapshot.captured_on < today)
                .order_by(RankSnapshot.captured_on.desc())
            ).scalars().first()
            snapshot = db.execute(
                select(RankSnapshot).where(
                    RankSnapshot.keyword_id == keyword.id,
                    RankSnapshot.captured_on == today,
                    RankSnapshot.device == "gsc",
                )
            ).scalars().first()
            if snapshot is None:
                snapshot = RankSnapshot(
                    keyword_id=keyword.id, captured_on=today, device="gsc"
                )
                db.add(snapshot)
                snapshots += 1
            snapshot.position = position
            snapshot.previous_position = previous.position if previous else None
            snapshot.url = row.page or ""
            snapshot.estimated_traffic = float(row.clicks)   # measured, not estimated
            snapshot.provider = "search_console"

    db.add(
        ActivityLog(
            project_id=project.id,
            actor="search_console",
            action="realdata.gsc_imported",
            entity_type="project",
            entity_id=project.id,
            detail={"rows": len(rows), "created": created, "updated": updated, "days": days},
        )
    )
    db.commit()

    total_clicks = sum(r.clicks for r in rows)
    total_impressions = sum(r.impressions for r in rows)
    return {
        "configured": True,
        "site_url": result.site_url,
        "window_days": days,
        "rows": len(rows),
        "imported": created + updated,
        "created": created,
        "updated": updated,
        "snapshots": snapshots,
        "total_clicks": total_clicks,
        "total_impressions": total_impressions,
        "avg_ctr": round(total_clicks / total_impressions, 4) if total_impressions else 0.0,
        "note": (
            "These are measured numbers from Google, not estimates. Volume confidence "
            "for these keywords is now 1.0."
        ),
    }


async def import_search_console_pages(
    db: Session, *, project: Project, days: int = 28, limit: int = 2000
) -> dict:
    """Query/page pairs: which of your pages actually ranks for which query."""
    if not search_console.is_configured():
        return {"error": search_console.configuration_hint(), "configured": False}

    result = await search_console.query_page_pairs(domain=project.domain, days=days, limit=limit)
    if not result.ok:
        return {"error": result.error, "configured": True}

    by_page: dict[str, dict] = {}
    for row in result.rows:
        page = by_page.setdefault(
            row.page,
            {"url": row.page, "clicks": 0, "impressions": 0, "queries": [], "best_position": 999.0},
        )
        page["clicks"] += row.clicks
        page["impressions"] += row.impressions
        page["best_position"] = min(page["best_position"], row.position or 999.0)
        page["queries"].append(
            {"query": row.query, "clicks": row.clicks, "impressions": row.impressions,
             "position": round(row.position, 1)}
        )

    pages = sorted(by_page.values(), key=lambda p: -p["clicks"])
    for page in pages:
        page["queries"].sort(key=lambda q: -q["impressions"])
        page["queries"] = page["queries"][:25]
        page["best_position"] = round(page["best_position"], 1)

    # Cannibalisation: one query where several pages take meaningful impressions.
    by_query: dict[str, list] = {}
    for row in result.rows:
        by_query.setdefault(row.query, []).append(row)
    cannibalisation = []
    for query, rows in by_query.items():
        competing = [r for r in rows if r.impressions >= 10]
        if len(competing) > 1:
            competing.sort(key=lambda r: -r.impressions)
            cannibalisation.append(
                {
                    "query": query,
                    "pages": [
                        {"url": r.page, "impressions": r.impressions, "clicks": r.clicks,
                         "position": round(r.position, 1)}
                        for r in competing[:5]
                    ],
                    "total_impressions": sum(r.impressions for r in competing),
                }
            )
    cannibalisation.sort(key=lambda c: -c["total_impressions"])

    return {
        "configured": True,
        "window_days": days,
        "pages": pages[:200],
        "cannibalisation": cannibalisation[:50],
        "note": (
            "Cannibalisation means two of your own pages compete for the same query. "
            "Usually the fix is to consolidate them and redirect the weaker one."
        ),
    }


# ---------------------------------------------------------------------------
# Bing Webmaster
# ---------------------------------------------------------------------------


async def import_bing_links(db: Session, *, project: Project) -> dict:
    """Bing's inbound-link report: the best free source of real backlink data."""
    if not bing_webmaster.is_configured():
        return {"imported": 0, "error": bing_webmaster.configuration_hint(), "configured": False}

    result = await bing_webmaster.inbound_links(domain=project.domain)
    if not result.ok:
        return {"imported": 0, "error": result.error, "configured": True}

    if not result.links:
        return {"imported": 0, "configured": True,
                "note": "Bing reported no inbound links for this property yet."}

    domains = [link.source_domain for link in result.links if link.source_domain]
    auth_map = await authority_mod.authority_for(domains)

    created = updated = 0
    for link in result.links:
        if not link.source_url or not link.source_domain:
            continue
        da = auth_map.get(link.source_domain, 0.0)
        tox, reasons = toxicity.score_link(
            source_url=link.source_url,
            source_domain=link.source_domain,
            anchor_text=link.anchor_text,
            link_type=LinkType.unknown.value,
            domain_authority=da,
            target_domain=project.domain,
        )
        existing = db.execute(
            select(Backlink).where(
                Backlink.project_id == project.id,
                Backlink.source_url == link.source_url,
            )
        ).scalars().first()
        if existing is None:
            db.add(
                Backlink(
                    project_id=project.id,
                    source_url=link.source_url,
                    source_domain=link.source_domain,
                    target_url=link.target_url,
                    anchor_text=link.anchor_text[:600],
                    link_type=LinkType.unknown.value,
                    status=LinkStatus.live.value,
                    domain_authority=da,
                    spam_score=toxicity.spam_score(link.source_domain, domain_authority=da),
                    toxicity_score=tox,
                    toxicity_reasons=reasons,
                    discovered_via="bing_webmaster",
                    last_checked=utcnow(),
                )
            )
            created += 1
        else:
            existing.anchor_text = link.anchor_text or existing.anchor_text
            existing.domain_authority = da or existing.domain_authority
            existing.status = LinkStatus.live.value
            existing.last_checked = utcnow()
            updated += 1

    db.add(
        ActivityLog(
            project_id=project.id,
            actor="bing_webmaster",
            action="realdata.bing_links_imported",
            entity_type="project",
            entity_id=project.id,
            detail={"links": len(result.links), "created": created, "updated": updated},
        )
    )
    db.commit()
    return {
        "configured": True,
        "found": len(result.links),
        "imported": created + updated,
        "created": created,
        "updated": updated,
        "referring_domains": len({link.source_domain for link in result.links}),
        "note": "Real inbound links reported by Bing for your verified property.",
    }


async def import_bing_queries(db: Session, *, project: Project, days: int = 30) -> dict:
    """Bing query performance. Complements Search Console rather than replacing it."""
    if not bing_webmaster.is_configured():
        return {"imported": 0, "error": bing_webmaster.configuration_hint(), "configured": False}

    result = await bing_webmaster.query_performance(domain=project.domain, days=days)
    if not result.ok:
        return {"imported": 0, "error": result.error, "configured": True}

    existing = {
        k.term: k
        for k in db.execute(select(Keyword).where(Keyword.project_id == project.id)).scalars()
    }
    created = updated = 0
    for row in result.queries:
        term = " ".join((row.query or "").split()).lower()
        if not term:
            continue
        keyword = existing.get(term)
        if keyword is None:
            intent = metrics.classify_intent(term, brand_terms=list(project.brand_terms or []))
            monthly = int(round(row.impressions * (30.0 / max(days, 1))))
            keyword = Keyword(
                project_id=project.id, term=term, country=project.country,
                language=project.language, intent=intent.value,
                word_count=len(metrics.tokenize(term)),
                is_question=metrics.is_question(term),
                volume=monthly, volume_confidence=0.9,  # Bing share is smaller than Google's
                source="bing_webmaster",
            )
            db.add(keyword)
            created += 1
        else:
            updated += 1
        keyword.meta_json = {
            **(keyword.meta_json or {}),
            "bing": {
                "clicks": row.clicks, "impressions": row.impressions,
                "position": round(row.position, 2), "ctr": row.ctr,
                "window_days": days,
            },
        }
    db.commit()
    return {
        "configured": True,
        "rows": len(result.queries),
        "imported": created + updated,
        "created": created,
        "updated": updated,
    }


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def data_sources_status(db: Session, *, project: Project | None = None) -> dict:
    """What kind of data this deployment is currently producing."""
    from draken.core.config import settings
    from draken.engines.serp import fetcher

    first_party = settings.first_party_data_configured()
    serp = fetcher.provider_availability()
    active = fetcher.active_provider()

    measured_keywords = 0
    measured_links = 0
    if project is not None:
        from sqlalchemy import func

        measured_keywords = db.execute(
            select(func.count(Keyword.id)).where(
                Keyword.project_id == project.id, Keyword.volume_confidence >= 1.0
            )
        ).scalar() or 0
        measured_links = db.execute(
            select(func.count(Backlink.id)).where(
                Backlink.project_id == project.id,
                Backlink.discovered_via.in_(
                    ["bing_webmaster", "search_console", "verification", "submission"]
                ),
            )
        ).scalar() or 0

    return {
        "first_party": first_party,
        "serp_providers": serp,
        "serp_active": active,
        "serp_exact": active in fetcher.EXACT_PROVIDERS,
        "serp_chain": fetcher.fallback_chain(),
        "ai_engines": settings.ai_engines_configured(),
        "measured_keywords": measured_keywords,
        "measured_links": measured_links,
        "quality": _quality_level(first_party, serp),
    }


def _quality_level(first_party: dict, serp: dict) -> dict:
    """A plain answer to 'how real is my data right now'."""
    exact_serp = serp.get("serpapi") or serp.get("dataforseo")
    gsc = first_party.get("search_console")
    bing = first_party.get("bing_webmaster")

    if gsc and exact_serp:
        level, label = 4, "complete"
    elif gsc:
        level, label = 3, "real for your own site"
    elif exact_serp or serp.get("brave") or serp.get("searxng"):
        level, label = 2, "real positions, estimated volume"
    else:
        level, label = 1, "estimated"

    missing = []
    if not gsc:
        missing.append("Search Console (real impressions, clicks and positions for your site)")
    if not bing:
        missing.append("Bing Webmaster (real inbound links, free)")
    if not exact_serp:
        missing.append("A paid SERP provider (exact Google positions for any keyword)")

    return {"level": level, "max_level": 4, "label": label, "missing": missing}
