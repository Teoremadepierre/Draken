"""Project CRUD, business profile and dashboard overview."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from draken.api.deps import current_user, get_project
from draken.core.database import get_db
from draken.core.models import (
    AIPrompt,
    Backlink,
    BusinessProfile,
    Campaign,
    Keyword,
    LinkOpportunity,
    LinkStatus,
    OpportunityStatus,
    Project,
    RankSnapshot,
    Submission,
)
from draken.core.schemas import (
    BusinessProfileIn,
    BusinessProfileOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
)
from draken.core.urls import normalize_domain
from draken.engines.submissions import runner as submission_runner
from draken.services import audits as audit_service
from draken.services import backlinks as backlink_service
from draken.services import geo as geo_service
from draken.services import keywords as keyword_service
from draken.services import opportunities as opportunity_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), _user: str = Depends(current_user)):
    return list(db.execute(select(Project).order_by(Project.id)).scalars())


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate, db: Session = Depends(get_db), _user: str = Depends(current_user)
):
    domain = normalize_domain(payload.domain)
    if not domain:
        raise HTTPException(status_code=422, detail=f"Could not parse a domain from {payload.domain!r}")
    if db.execute(select(Project).where(Project.domain == domain)).scalars().first():
        raise HTTPException(status_code=409, detail=f"A project for {domain} already exists")

    project = Project(
        name=payload.name,
        domain=domain,
        base_url=payload.base_url or f"https://{domain}",
        description=payload.description,
        country=payload.country.upper(),
        language=payload.language.lower(),
        industry=payload.industry,
        competitors=[normalize_domain(c) for c in payload.competitors if normalize_domain(c)],
        brand_terms=payload.brand_terms or [payload.name],
    )
    db.add(project)
    db.commit()

    # Give the project a business profile shell and a scored opportunity list immediately.
    db.add(
        BusinessProfile(
            project_id=project.id,
            display_name=payload.name,
            website=project.base_url,
            country=project.country,
            short_description=payload.description[:300],
        )
    )
    db.commit()
    opportunity_service.generate_from_catalog(db, project=project, limit=250)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def read_project(project: Project = Depends(get_project)):
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    payload: ProjectUpdate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    if "competitors" in data and data["competitors"] is not None:
        data["competitors"] = [normalize_domain(c) for c in data["competitors"] if normalize_domain(c)]
    for key, value in data.items():
        setattr(project, key, value)
    db.commit()
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    db.delete(project)
    db.commit()


# --- business profile ------------------------------------------------------


@router.get("/{project_id}/profile", response_model=BusinessProfileOut)
def read_profile(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.project_id == project.id)
    ).scalar_one_or_none()
    if profile is None:
        profile = BusinessProfile(project_id=project.id, display_name=project.name,
                                 website=project.base_url, country=project.country)
        db.add(profile)
        db.commit()
    return profile


@router.put("/{project_id}/profile", response_model=BusinessProfileOut)
def update_profile(
    payload: BusinessProfileIn,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.project_id == project.id)
    ).scalar_one_or_none()
    if profile is None:
        profile = BusinessProfile(project_id=project.id)
        db.add(profile)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    db.commit()
    return profile


@router.get("/{project_id}/profile/completeness")
def profile_completeness(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.project_id == project.id)
    ).scalar_one_or_none()
    score, missing = submission_runner.profile_completeness(profile)
    return {
        "completeness": score,
        "missing_fields": missing,
        "ready_for_submissions": score >= 0.5,
        "note": (
            "Submissions are blocked below 50% completeness: an incomplete listing under your own "
            "brand is worse than no listing."
        ),
    }


# --- overview --------------------------------------------------------------


@router.get("/{project_id}/overview")
def overview(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    """Everything the dashboard home screen needs, in one call."""
    keyword_count = db.execute(
        select(func.count(Keyword.id)).where(Keyword.project_id == project.id)
    ).scalar() or 0
    tracked_count = db.execute(
        select(func.count(Keyword.id)).where(
            Keyword.project_id == project.id, Keyword.is_tracked.is_(True)
        )
    ).scalar() or 0
    backlink_count = db.execute(
        select(func.count(Backlink.id)).where(
            Backlink.project_id == project.id, Backlink.status == LinkStatus.live.value
        )
    ).scalar() or 0
    referring_domains = db.execute(
        select(func.count(func.distinct(Backlink.source_domain))).where(
            Backlink.project_id == project.id, Backlink.status == LinkStatus.live.value
        )
    ).scalar() or 0
    opportunity_count = db.execute(
        select(func.count(LinkOpportunity.id)).where(LinkOpportunity.project_id == project.id)
    ).scalar() or 0
    won_count = db.execute(
        select(func.count(LinkOpportunity.id)).where(
            LinkOpportunity.project_id == project.id,
            LinkOpportunity.status == OpportunityStatus.won.value,
        )
    ).scalar() or 0
    pending_submissions = db.execute(
        select(func.count(Submission.id)).where(
            Submission.project_id == project.id,
            Submission.state.in_(["awaiting_approval", "approved", "manual_required"]),
        )
    ).scalar() or 0
    prompt_count = db.execute(
        select(func.count(AIPrompt.id)).where(AIPrompt.project_id == project.id)
    ).scalar() or 0
    campaign_count = db.execute(
        select(func.count(Campaign.id)).where(Campaign.project_id == project.id)
    ).scalar() or 0
    last_rank_date = db.execute(
        select(func.max(RankSnapshot.captured_on))
        .join(Keyword, RankSnapshot.keyword_id == Keyword.id)
        .where(Keyword.project_id == project.id)
    ).scalar()

    audit = audit_service.latest_audit(db, project_id=project.id)
    link_profile = backlink_service.profile_report(db, project=project)
    rankings = keyword_service.ranking_overview(db, project=project)
    pipeline = opportunity_service.pipeline(db, project_id=project.id)
    geo = geo_service.summary(db, project=project)

    # Top of the to-do list, assembled from whatever each module flagged.
    next_actions: list[dict] = []
    if referring_domains == 0:
        next_actions.append({
            "priority": 1,
            "area": "backlinks",
            "action": "You have no backlinks yet. Open Link Opportunities, filter to effort <= 2, "
                      "and work the foundation tier (business profiles, then free dofollow directories).",
        })
    if not audit:
        next_actions.append({"priority": 2, "area": "site", "action": "Run your first site audit."})
    elif audit.health_score < 70:
        next_actions.append({
            "priority": 2, "area": "site",
            "action": f"Site health is {audit.health_score:.0f}/100. Fix the critical and error issues first.",
        })
    if keyword_count == 0:
        next_actions.append({
            "priority": 1, "area": "keywords",
            "action": "Run keyword research from 2-5 seed terms to build your keyword universe.",
        })
    elif tracked_count == 0:
        next_actions.append({
            "priority": 3, "area": "keywords",
            "action": "Mark your 20 highest-opportunity keywords as tracked so ranking history starts accumulating.",
        })
    if prompt_count == 0:
        next_actions.append({
            "priority": 3, "area": "ai-visibility",
            "action": "Generate an AI prompt set to baseline how assistants describe you.",
        })
    if pending_submissions:
        next_actions.append({
            "priority": 2, "area": "submissions",
            "action": f"{pending_submissions} submission(s) are waiting on you.",
        })
    for rec in (link_profile.get("recommendations") or [])[:2]:
        next_actions.append({"priority": 4, "area": "backlinks", "action": rec})
    for rec in (geo.get("recommendations") or [])[:1]:
        next_actions.append({"priority": 4, "area": "ai-visibility", "action": rec})
    next_actions.sort(key=lambda a: a["priority"])

    return {
        "project": {
            "id": project.id, "name": project.name, "domain": project.domain,
            "base_url": project.base_url, "country": project.country,
            "language": project.language, "industry": project.industry,
            "competitors": project.competitors, "brand_terms": project.brand_terms,
        },
        "counts": {
            "keywords": keyword_count,
            "tracked_keywords": tracked_count,
            "backlinks": backlink_count,
            "referring_domains": referring_domains,
            "opportunities": opportunity_count,
            "links_won": won_count,
            "pending_submissions": pending_submissions,
            "ai_prompts": prompt_count,
            "campaigns": campaign_count,
        },
        "site_health": {
            "score": audit.health_score if audit else None,
            "pages_crawled": audit.pages_crawled if audit else 0,
            "issue_counts": audit.issue_counts if audit else {},
            "last_run": audit.finished_at if audit else None,
            "audit_id": audit.id if audit else None,
        },
        "link_profile": {
            "authority_score": link_profile["authority_score"],
            "referring_domains": link_profile["referring_domains"],
            "dofollow_links": link_profile["dofollow_links"],
            "toxic_links": link_profile["toxic_links"],
            "avg_domain_authority": link_profile["avg_domain_authority"],
            "velocity": link_profile["velocity"][-6:],
            "anchor_warnings": link_profile["anchor_health"]["warnings"],
        },
        "rankings": {
            "visibility_index": rankings["visibility_index"],
            "estimated_traffic": rankings["estimated_traffic"],
            "distribution": rankings["distribution"],
            "trend": rankings["trend"][-14:],
            "movers": rankings["movers"],
            "last_updated": str(last_rank_date) if last_rank_date else None,
        },
        "pipeline": pipeline,
        "ai_visibility": {
            "mention_rate": geo["mention_rate"],
            "citation_rate": geo["citation_rate"],
            "avg_visibility_score": geo["avg_visibility_score"],
            "by_engine": geo["by_engine"],
            "competitor_share": geo["competitor_share"][:5],
            "engines_configured": geo["engines_configured"],
        },
        "next_actions": next_actions[:8],
    }
