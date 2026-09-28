"""Opportunity pipeline persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.core.logging import get_logger
from draken.core.models import (
    Campaign,
    Keyword,
    LinkOpportunity,
    LinkSource,
    OpportunityStatus,
    Project,
    utcnow,
)
from draken.data import loader
from draken.engines.opportunities import generator
from draken.services import backlinks as backlink_service

log = get_logger(__name__)


def sync_catalog(db: Session) -> dict:
    """Load/refresh the link source catalog from data/seeds into the database."""
    loader.clear_caches()
    sources = loader.link_sources()
    existing = {s.slug: s for s in db.execute(select(LinkSource)).scalars()}
    created = updated = 0
    for row in sources:
        slug = row.get("slug")
        if not slug:
            continue
        fields = {
            "name": row.get("name", "")[:240],
            "domain": row.get("domain", "")[:255],
            "submit_url": (row.get("submit_url") or "")[:800],
            "category": row.get("category", "directory"),
            "authority": float(row.get("authority") or 0),
            "link_type": row.get("link_type", "unknown"),
            "is_free": bool(row.get("is_free", True)),
            "requires_account": bool(row.get("requires_account", False)),
            "requires_moderation": bool(row.get("requires_moderation", True)),
            "automatable": bool(row.get("automatable", False)),
            "effort": int(row.get("effort") or 3),
            "countries": row.get("countries") or [],
            "languages": row.get("languages") or [],
            "industries": row.get("industries") or [],
            "tags": row.get("tags") or [],
            "required_fields": row.get("required_fields") or [],
            "guidelines_url": (row.get("guidelines_url") or "")[:800],
            "notes": row.get("notes", ""),
            "ai_training_signal": bool(row.get("ai_training_signal", False)),
            "llm_citation_weight": float(row.get("llm_citation_weight") or 0),
            "adapter": row.get("adapter", ""),
        }
        current = existing.get(slug)
        if current is None:
            db.add(LinkSource(slug=slug, **fields))
            created += 1
        else:
            for k, v in fields.items():
                setattr(current, k, v)
            updated += 1
    db.commit()
    return {"created": created, "updated": updated, "total": len(sources)}


def _brand_for(db: Session, project: Project) -> str:
    """The name to use in anchors and listings, in order of reliability."""
    from draken.core.models import BusinessProfile

    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.project_id == project.id)
    ).scalar_one_or_none()
    if profile and profile.display_name:
        return profile.display_name
    brand_terms = list(project.brand_terms or [])
    if brand_terms:
        return brand_terms[0]
    return project.name or project.domain.split(".")[0]


def _primary_keyword(db: Session, project_id: int) -> str:
    kw = db.execute(
        select(Keyword)
        .where(Keyword.project_id == project_id, Keyword.is_branded.is_(False))
        .order_by(Keyword.opportunity_score.desc())
    ).scalars().first()
    return kw.term if kw else ""


def generate_from_catalog(
    db: Session,
    *,
    project: Project,
    categories: list[str] | None = None,
    countries: list[str] | None = None,
    max_effort: int = 5,
    only_free: bool = True,
    only_dofollow: bool = False,
    include_ai_sources: bool = True,
    limit: int = 200,
    campaign_id: int | None = None,
) -> dict:
    """Score the catalog for this project and persist the resulting opportunities."""
    if not db.execute(select(LinkSource.id).limit(1)).first():
        sync_catalog(db)

    have = backlink_service.existing_domains(db, project_id=project.id)
    mix = backlink_service.anchor_mix(db, project=project)

    generated = generator.from_catalog(
        project_country=project.country,
        project_language=project.language,
        project_industry=project.industry,
        brand=_brand_for(db, project),
        target_keyword=_primary_keyword(db, project.id),
        existing_domains=have,
        anchor_mix=mix,
        categories=categories,
        countries=countries or [project.country],
        max_effort=max_effort,
        only_free=only_free,
        only_dofollow=only_dofollow,
        include_ai_sources=include_ai_sources,
        limit=limit,
    )

    sources_by_slug = {s.slug: s for s in db.execute(select(LinkSource)).scalars()}
    landing = project.base_url or f"https://{project.domain}"

    created = skipped = 0
    for opp in generated:
        source = sources_by_slug.get(opp.source_slug)
        existing = db.execute(
            select(LinkOpportunity).where(
                LinkOpportunity.project_id == project.id,
                LinkOpportunity.target_domain == opp.target_domain,
                LinkOpportunity.source_id == (source.id if source else None),
            )
        ).scalars().first()
        if existing is not None:
            existing.score = opp.score
            existing.score_breakdown = opp.score_breakdown
            existing.authority = opp.authority
            existing.relevance = opp.relevance
            skipped += 1
            continue
        db.add(
            LinkOpportunity(
                project_id=project.id,
                source_id=source.id if source else None,
                campaign_id=campaign_id,
                target_domain=opp.target_domain,
                target_url=opp.target_url,
                landing_url=landing,
                suggested_anchor=opp.suggested_anchor,
                tactic=opp.tactic,
                status=OpportunityStatus.new.value,
                score=opp.score,
                score_breakdown=opp.score_breakdown,
                authority=opp.authority,
                relevance=opp.relevance,
                effort=opp.effort,
                discovered_via=opp.discovered_via,
                competitor_links=opp.competitor_links,
                notes=opp.notes,
                meta_json=opp.meta,
            )
        )
        created += 1
    db.commit()
    return {
        "generated": len(generated),
        "created": created,
        "already_present": skipped,
        "tactic_playbook": generator.tactic_playbook(),
    }


async def prospect_from_competitors(
    db: Session, *, project: Project, limit: int = 150, campaign_id: int | None = None
) -> dict:
    """Link intersect against the project's competitor list."""
    competitors = list(project.competitors or [])
    if not competitors:
        return {"created": 0, "message": "Add competitor domains to the project first."}

    keywords = [
        k.term
        for k in db.execute(
            select(Keyword)
            .where(Keyword.project_id == project.id)
            .order_by(Keyword.volume.desc())
            .limit(60)
        ).scalars()
    ]
    have = backlink_service.existing_domains(db, project_id=project.id)
    mix = backlink_service.anchor_mix(db, project=project)

    generated, raw_links = await generator.from_competitors(
        competitors=competitors,
        project_domain=project.domain,
        project_keywords=keywords,
        brand=_brand_for(db, project),
        existing_domains=have,
        anchor_mix=mix,
        country=project.country,
        language=project.language,
        limit=limit,
    )

    stored_raw = backlink_service.store_competitor_links(
        db, project_id=project.id, raw_links=raw_links
    )

    landing = project.base_url or f"https://{project.domain}"
    created = 0
    for opp in generated:
        exists = db.execute(
            select(LinkOpportunity).where(
                LinkOpportunity.project_id == project.id,
                LinkOpportunity.target_domain == opp.target_domain,
                LinkOpportunity.source_id.is_(None),
            )
        ).scalars().first()
        if exists is not None:
            exists.score = opp.score
            exists.competitor_links = opp.competitor_links
            continue
        db.add(
            LinkOpportunity(
                project_id=project.id,
                campaign_id=campaign_id,
                target_domain=opp.target_domain,
                target_url=opp.target_url,
                landing_url=landing,
                suggested_anchor=opp.suggested_anchor,
                tactic=opp.tactic,
                status=OpportunityStatus.new.value,
                score=opp.score,
                score_breakdown=opp.score_breakdown,
                authority=opp.authority,
                relevance=opp.relevance,
                effort=opp.effort,
                discovered_via=opp.discovered_via,
                competitor_links=opp.competitor_links,
                notes=opp.notes,
                meta_json=opp.meta,
            )
        )
        created += 1
    db.commit()
    return {
        "competitors_analysed": len(competitors),
        "competitor_links_stored": stored_raw,
        "opportunities_found": len(generated),
        "created": created,
    }


async def prospect_unlinked_mentions(
    db: Session, *, project: Project, limit: int = 60
) -> dict:
    have = backlink_service.existing_domains(db, project_id=project.id)
    generated = await generator.from_unlinked_mentions(
        project_domain=project.domain,
        brand_terms=list(project.brand_terms or []) or [project.domain.split(".")[0]],
        brand=_brand_for(db, project),
        country=project.country,
        language=project.language,
        existing_domains=have,
        limit=limit,
    )
    landing = project.base_url or f"https://{project.domain}"
    created = 0
    for opp in generated:
        exists = db.execute(
            select(LinkOpportunity).where(
                LinkOpportunity.project_id == project.id,
                LinkOpportunity.target_domain == opp.target_domain,
                LinkOpportunity.tactic == "unlinked_mention",
            )
        ).scalars().first()
        if exists:
            continue
        db.add(
            LinkOpportunity(
                project_id=project.id,
                target_domain=opp.target_domain,
                target_url=opp.target_url,
                landing_url=landing,
                suggested_anchor=opp.suggested_anchor,
                tactic=opp.tactic,
                status=OpportunityStatus.qualified.value,
                score=opp.score,
                score_breakdown=opp.score_breakdown,
                authority=opp.authority,
                relevance=opp.relevance,
                effort=opp.effort,
                discovered_via=opp.discovered_via,
                notes=opp.notes,
                meta_json=opp.meta,
            )
        )
        created += 1
    db.commit()
    return {"found": len(generated), "created": created}


def pipeline(db: Session, *, project_id: int) -> dict:
    rows = list(
        db.execute(
            select(LinkOpportunity).where(LinkOpportunity.project_id == project_id)
        ).scalars()
    )
    payload = [
        {
            "id": o.id,
            "status": o.status,
            "tactic": o.tactic,
            "score": o.score,
            "effort": o.effort,
        }
        for o in rows
    ]
    return generator.summarise(payload)


def update_status(
    db: Session,
    *,
    opportunity_id: int,
    status: str | None = None,
    notes: str | None = None,
    landing_url: str | None = None,
    suggested_anchor: str | None = None,
    campaign_id: int | None = None,
) -> LinkOpportunity | None:
    opp = db.get(LinkOpportunity, opportunity_id)
    if opp is None:
        return None
    if status:
        valid = {s.value for s in OpportunityStatus}
        if status not in valid:
            raise ValueError(f"invalid status {status!r}; expected one of {sorted(valid)}")
        opp.status = status
        if status == OpportunityStatus.won.value and not opp.won_at:
            opp.won_at = utcnow()
    if notes is not None:
        opp.notes = notes
    if landing_url is not None:
        opp.landing_url = landing_url
    if suggested_anchor is not None:
        opp.suggested_anchor = suggested_anchor
    if campaign_id is not None:
        opp.campaign_id = campaign_id or None
    db.commit()
    return opp


def campaign_progress(db: Session, *, campaign: Campaign) -> dict:
    opps = list(
        db.execute(
            select(LinkOpportunity).where(LinkOpportunity.campaign_id == campaign.id)
        ).scalars()
    )
    won = [o for o in opps if o.status == OpportunityStatus.won.value]
    in_flight = [
        o for o in opps
        if o.status in {
            OpportunityStatus.queued.value,
            OpportunityStatus.in_progress.value,
            OpportunityStatus.submitted.value,
            OpportunityStatus.awaiting_review.value,
        }
    ]
    return {
        "campaign_id": campaign.id,
        "name": campaign.name,
        "monthly_link_target": campaign.monthly_link_target,
        "opportunities": len(opps),
        "won": len(won),
        "in_flight": len(in_flight),
        "remaining_to_target": max(0, campaign.monthly_link_target - len(won)),
        "avg_won_authority": round(
            sum(o.authority for o in won) / len(won), 1
        ) if won else 0.0,
        "by_tactic": {
            t: sum(1 for o in opps if o.tactic == t) for t in {o.tactic for o in opps}
        },
    }
