"""AI-visibility persistence and reporting."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.core.config import settings
from draken.core.logging import get_logger
from draken.core.models import (
    AIPrompt,
    AIVisibilityRun,
    BusinessProfile,
    CrawledPage,
    Keyword,
    KeywordCluster,
    Project,
    SiteAudit,
)
from draken.engines.geo import assets, visibility
from draken.engines.geo import engines as engine_mod

log = get_logger(__name__)


def _profile_dict(db: Session, project_id: int) -> dict:
    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.project_id == project_id)
    ).scalar_one_or_none()
    if profile is None:
        return {}
    return {
        c.name: getattr(profile, c.name)
        for c in BusinessProfile.__table__.columns
        if c.name not in {"id", "project_id", "created_at", "updated_at"}
    }


def _project_dict(project: Project) -> dict:
    return {
        "name": project.name,
        "domain": project.domain,
        "base_url": project.base_url,
        "industry": project.industry,
        "country": project.country,
        "language": project.language,
    }


def generate_prompt_set(
    db: Session,
    *,
    project: Project,
    from_keywords: bool = True,
    limit: int = 40,
    extra_topics: list[str] | None = None,
) -> dict:
    profile = _profile_dict(db, project.id)
    keywords: list[str] = list(extra_topics or [])
    if from_keywords:
        keywords += [
            k.term
            for k in db.execute(
                select(Keyword)
                .where(Keyword.project_id == project.id, Keyword.is_branded.is_(False))
                .order_by(Keyword.opportunity_score.desc())
                .limit(30)
            ).scalars()
        ]

    brand = profile.get("display_name") or project.name or project.domain
    category = project.industry or (profile.get("categories") or [""])[0] if profile.get("categories") else project.industry

    prompts = visibility.generate_prompts(
        brand=brand,
        category=category or "your category",
        competitors=list(project.competitors or []),
        city=profile.get("city", ""),
        keywords=keywords,
        language=project.language,
        limit=limit,
    )

    existing = {
        p.prompt.strip().lower()
        for p in db.execute(select(AIPrompt).where(AIPrompt.project_id == project.id)).scalars()
    }
    created = 0
    for p in prompts:
        if p["prompt"].strip().lower() in existing:
            continue
        db.add(
            AIPrompt(
                project_id=project.id,
                prompt=p["prompt"],
                category=p["category"],
                intent=p["intent"],
                language=p["language"],
                priority=p["priority"],
            )
        )
        created += 1
    db.commit()
    return {"generated": len(prompts), "created": created, "prompts": prompts}


async def run_visibility(
    db: Session,
    *,
    project: Project,
    engines: list[str] | None = None,
    prompt_ids: list[int] | None = None,
    limit: int = 20,
) -> dict:
    """Ask each configured engine the prompt set and score the answers."""
    configured = settings.ai_engines_configured()
    wanted = [e for e in (engines or engine_mod.available_engines())]
    if not any(configured.get(e) for e in wanted):
        return {
            "runs": 0,
            "engines_configured": configured,
            "message": (
                "No AI engine API key is configured. Add DRAKEN_ANTHROPIC_API_KEY, "
                "DRAKEN_OPENAI_API_KEY, DRAKEN_PERPLEXITY_API_KEY or DRAKEN_GEMINI_API_KEY "
                "to measure AI visibility."
            ),
        }

    query = select(AIPrompt).where(
        AIPrompt.project_id == project.id, AIPrompt.is_active.is_(True)
    )
    if prompt_ids:
        query = query.where(AIPrompt.id.in_(prompt_ids))
    prompts = list(db.execute(query.order_by(AIPrompt.priority).limit(limit)).scalars())
    if not prompts:
        return {"runs": 0, "message": "No active prompts. Generate a prompt set first."}

    profile = _profile_dict(db, project.id)
    brand_terms = list(project.brand_terms or [])
    if profile.get("display_name"):
        brand_terms.append(profile["display_name"])
    if project.name:
        brand_terms.append(project.name)
    brand_terms = list(dict.fromkeys(t for t in brand_terms if t))

    competitors = list(project.competitors or [])
    stored = 0
    errors: list[str] = []

    for prompt in prompts:
        answers = await engine_mod.ask_all(prompt.prompt, engines=wanted)
        for answer in answers:
            analysis = visibility.analyse_answer(
                engine=answer.engine,
                model=answer.model,
                answer=answer.answer,
                citations=answer.citations,
                brand_terms=brand_terms,
                domain=project.domain,
                competitors=competitors,
                error=answer.error,
            )
            db.add(
                AIVisibilityRun(
                    prompt_id=prompt.id,
                    project_id=project.id,
                    engine=analysis.engine,
                    model=analysis.model,
                    answer=analysis.answer[:20000],
                    brand_mentioned=analysis.brand_mentioned,
                    brand_position=analysis.brand_position,
                    domain_cited=analysis.domain_cited,
                    citations=analysis.citations[:60],
                    competitors_mentioned=analysis.competitors_mentioned,
                    sentiment=analysis.sentiment,
                    visibility_score=analysis.visibility_score,
                    share_of_voice=analysis.share_of_voice,
                    error=analysis.error[:1000],
                )
            )
            stored += 1
            if analysis.error:
                errors.append(f"{analysis.engine}: {analysis.error}")
    db.commit()

    return {
        "prompts_run": len(prompts),
        "runs": stored,
        "engines": wanted,
        "engines_configured": configured,
        "errors": sorted(set(errors))[:10],
    }


def summary(db: Session, *, project: Project, days: int = 30) -> dict:
    prompts = list(
        db.execute(select(AIPrompt).where(AIPrompt.project_id == project.id)).scalars()
    )
    runs = list(
        db.execute(
            select(AIVisibilityRun)
            .where(AIVisibilityRun.project_id == project.id)
            .order_by(AIVisibilityRun.captured_at.desc())
            .limit(2000)
        ).scalars()
    )

    # Latest run per (prompt, engine) so the summary reflects current state.
    latest: dict[tuple[int, str], AIVisibilityRun] = {}
    for r in runs:
        key = (r.prompt_id, r.engine)
        if key not in latest:
            latest[key] = r

    payload = [
        {
            "engine": r.engine,
            "brand_mentioned": r.brand_mentioned,
            "brand_position": r.brand_position,
            "domain_cited": r.domain_cited,
            "competitors_mentioned": r.competitors_mentioned or [],
            "visibility_score": r.visibility_score,
            "error": r.error,
        }
        for r in latest.values()
    ]

    prompt_by_id = {p.id: p for p in prompts}
    covered = {pid for (pid, _e), r in latest.items() if r.brand_mentioned or r.domain_cited}
    uncovered = [
        {"id": p.id, "prompt": p.prompt, "category": p.category, "priority": p.priority}
        for p in prompts
        if p.id not in covered and p.id in {pid for pid, _ in latest}
    ][:25]

    result = visibility.summarise(
        payload,
        prompts_tracked=len(prompts),
        competitors=list(project.competitors or []),
        engines_configured=settings.ai_engines_configured(),
        uncovered=uncovered,
    )

    # Which external domains the engines cite most - your GEO link target list.
    cited: dict[str, int] = {}
    for r in runs:
        for c in r.citations or []:
            from draken.core.urls import normalize_domain

            d = normalize_domain(c)
            if d and d != project.domain:
                cited[d] = cited.get(d, 0) + 1
    result["top_cited_domains"] = sorted(
        ({"domain": d, "citations": n} for d, n in cited.items()),
        key=lambda r: -r["citations"],
    )[:30]

    trend: dict[str, list[float]] = {}
    for r in runs:
        day = r.captured_at.date().isoformat() if r.captured_at else ""
        if day and not r.error:
            trend.setdefault(day, []).append(r.visibility_score)
    result["trend"] = [
        {"date": d, "avg_visibility_score": round(sum(v) / len(v), 1), "runs": len(v)}
        for d, v in sorted(trend.items())[-days:]
    ]
    result["prompts_total"] = len(prompt_by_id)
    return result


def geo_assets(db: Session, *, project: Project) -> dict:
    """Generate llms.txt and the JSON-LD bundle from stored data."""
    profile = _profile_dict(db, project.id)
    project_data = _project_dict(project)

    audit = db.execute(
        select(SiteAudit)
        .where(SiteAudit.project_id == project.id)
        .order_by(SiteAudit.id.desc())
    ).scalars().first()

    key_pages: list[dict] = []
    if audit is not None:
        pages = list(
            db.execute(
                select(CrawledPage)
                .where(CrawledPage.audit_id == audit.id, CrawledPage.status_code == 200)
                .order_by(CrawledPage.inlinks.desc(), CrawledPage.word_count.desc())
                .limit(25)
            ).scalars()
        )
        key_pages = [
            {"url": p.url, "title": p.title, "meta_description": p.meta_description}
            for p in pages
        ]

    clusters = [
        {"label": c.label, "head_term": c.head_term}
        for c in db.execute(
            select(KeywordCluster)
            .where(KeywordCluster.project_id == project.id)
            .order_by(KeywordCluster.total_volume.desc())
            .limit(20)
        ).scalars()
    ]

    llms_txt = assets.generate_llms_txt(
        profile=profile, project=project_data, key_pages=key_pages, clusters=clusters
    )
    bundle = assets.schema_bundle(profile=profile, project=project_data)

    missing = [
        k for k in ("display_name", "short_description", "long_description", "logo_url", "email")
        if not profile.get(k)
    ]
    return {
        "llms_txt": llms_txt,
        "llms_txt_install_path": "/llms.txt",
        "schema": bundle,
        "profile_gaps": missing,
        "key_pages_used": len(key_pages),
        "notes": [
            "Serve llms.txt at your site root as text/plain, exactly like robots.txt.",
            "Add the JSON-LD script tag to your sitewide <head> template.",
            "Re-generate both whenever your positioning, pricing or address changes - stale "
            "structured data is repeated by assistants for months.",
        ] + (
            [f"Fill these business-profile fields for a complete output: {', '.join(missing)}."]
            if missing else []
        ),
    }


def entity_consistency(db: Session, *, project: Project, listings: list[dict] | None = None) -> dict:
    """Compare canonical NAP against recorded live listings."""
    profile = _profile_dict(db, project.id)
    if listings is None:
        from draken.core.models import LinkOpportunity, OpportunityStatus

        won = list(
            db.execute(
                select(LinkOpportunity).where(
                    LinkOpportunity.project_id == project.id,
                    LinkOpportunity.status == OpportunityStatus.won.value,
                )
            ).scalars()
        )
        # Submitted listings were filled from the canonical profile, so they should match.
        listings = [
            {
                "source": o.target_domain,
                "name": (o.meta_json or {}).get("submitted_name", ""),
                "phone": (o.meta_json or {}).get("submitted_phone", ""),
                "website": o.landing_url,
            }
            for o in won
        ]
        listings = [link for link in listings if any(v for k, v in link.items() if k != "source")]
    return assets.check_entity_consistency(profile=profile, listings=listings)
