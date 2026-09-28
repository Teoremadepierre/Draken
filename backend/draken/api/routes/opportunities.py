"""Link opportunities, the source catalog, campaigns and submissions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.api.deps import current_user, get_project
from draken.core.config import settings
from draken.core.database import get_db
from draken.core.models import (
    Campaign,
    LinkOpportunity,
    LinkSource,
    Project,
    Submission,
)
from draken.core.schemas import (
    ApproveSubmissionsRequest,
    CampaignCreate,
    CampaignOut,
    GenerateOpportunitiesRequest,
    LinkSourceOut,
    OpportunityOut,
    OpportunityStatusUpdate,
    PrepareSubmissionsRequest,
    RunSubmissionsRequest,
    SubmissionOut,
)
from draken.engines.opportunities import generator
from draken.engines.scheduler import jobs
from draken.engines.submissions import runner as submission_runner
from draken.services import opportunities as opportunity_service

router = APIRouter(tags=["link building"])


# ---------------------------------------------------------------------------
# Source catalog (global, not project-scoped)
# ---------------------------------------------------------------------------

catalog = APIRouter(prefix="/api/sources", tags=["link building"])


@catalog.get("", response_model=list[LinkSourceOut])
def list_sources(
    db: Session = Depends(get_db),
    _user: str = Depends(current_user),
    category: str = "",
    country: str = "",
    industry: str = "",
    q: str = "",
    max_effort: int = Query(5, ge=1, le=5),
    only_free: bool = False,
    only_dofollow: bool = False,
    only_automatable: bool = False,
    sort: str = Query("authority", pattern="^(authority|effort|name|llm)$"),
    limit: int = Query(400, ge=1, le=2000),
    offset: int = 0,
):
    if not db.execute(select(LinkSource.id).limit(1)).first():
        opportunity_service.sync_catalog(db)

    query = select(LinkSource).where(LinkSource.effort <= max_effort)
    if category:
        query = query.where(LinkSource.category == category)
    if q:
        query = query.where(LinkSource.name.contains(q) | LinkSource.domain.contains(q.lower()))
    if only_free:
        query = query.where(LinkSource.is_free.is_(True))
    if only_dofollow:
        query = query.where(LinkSource.link_type == "dofollow")
    if only_automatable:
        query = query.where(LinkSource.automatable.is_(True))

    order = {
        "authority": LinkSource.authority.desc(),
        "effort": LinkSource.effort.asc(),
        "name": LinkSource.name.asc(),
        "llm": LinkSource.llm_citation_weight.desc(),
    }[sort]
    rows = list(db.execute(query.order_by(order).offset(offset).limit(limit + 200)).scalars())

    # JSON-array filters are applied in Python so the same code works on SQLite and Postgres.
    if country:
        c = country.upper()
        rows = [r for r in rows if not r.countries or "*" in r.countries or c in [x.upper() for x in r.countries]]
    if industry:
        i = industry.lower()
        rows = [
            r for r in rows
            if not r.industries or "*" in r.industries
            or any(i in x.lower() or x.lower() in i for x in r.industries)
        ]
    return rows[:limit]


@catalog.get("/stats")
def source_stats(db: Session = Depends(get_db), _user: str = Depends(current_user)):
    if not db.execute(select(LinkSource.id).limit(1)).first():
        opportunity_service.sync_catalog(db)
    rows = list(db.execute(select(LinkSource)).scalars())
    by_category: dict[str, dict] = {}
    for r in rows:
        row = by_category.setdefault(
            r.category, {"category": r.category, "count": 0, "dofollow": 0, "avg_authority": 0.0, "_sum": 0.0}
        )
        row["count"] += 1
        row["_sum"] += r.authority
        if r.link_type == "dofollow":
            row["dofollow"] += 1
    for row in by_category.values():
        row["avg_authority"] = round(row["_sum"] / row["count"], 1)
        row.pop("_sum")
    return {
        "total": len(rows),
        "free": sum(1 for r in rows if r.is_free),
        "dofollow": sum(1 for r in rows if r.link_type == "dofollow"),
        "automatable": sum(1 for r in rows if r.automatable),
        "ai_training_signal": sum(1 for r in rows if r.ai_training_signal),
        "quick_wins": sum(1 for r in rows if r.effort <= 2 and r.authority >= 60),
        "by_category": sorted(by_category.values(), key=lambda r: -r["count"]),
        "countries_covered": len({c for r in rows for c in (r.countries or []) if c != "*"}),
    }


@catalog.post("/sync")
def sync_sources(db: Session = Depends(get_db), _user: str = Depends(current_user)):
    """Reload data/seeds/link_sources.json into the database."""
    return opportunity_service.sync_catalog(db)


@catalog.get("/playbook")
def playbook(_user: str = Depends(current_user)):
    """The tactics that are prospected rather than submitted to."""
    return {"tactics": generator.tactic_playbook()}


# ---------------------------------------------------------------------------
# Project opportunities
# ---------------------------------------------------------------------------

project_router = APIRouter(prefix="/api/projects/{project_id}", tags=["link building"])


@project_router.get("/opportunities", response_model=list[OpportunityOut])
def list_opportunities(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    status: str = "",
    tactic: str = "",
    campaign_id: int | None = None,
    min_score: float = 0.0,
    max_effort: int = Query(5, ge=1, le=5),
    q: str = "",
    sort: str = Query("score", pattern="^(score|effort|authority|domain)$"),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = 0,
):
    query = select(LinkOpportunity).where(
        LinkOpportunity.project_id == project.id,
        LinkOpportunity.score >= min_score,
        LinkOpportunity.effort <= max_effort,
    )
    if status:
        query = query.where(LinkOpportunity.status == status)
    if tactic:
        query = query.where(LinkOpportunity.tactic == tactic)
    if campaign_id is not None:
        query = query.where(LinkOpportunity.campaign_id == campaign_id)
    if q:
        query = query.where(LinkOpportunity.target_domain.contains(q.lower()))
    order = {
        "score": LinkOpportunity.score.desc(),
        "effort": LinkOpportunity.effort.asc(),
        "authority": LinkOpportunity.authority.desc(),
        "domain": LinkOpportunity.target_domain.asc(),
    }[sort]
    return list(db.execute(query.order_by(order).offset(offset).limit(limit)).scalars())


@project_router.post("/opportunities/generate")
def generate(
    payload: GenerateOpportunitiesRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Score the 355-source catalog for this project and create the work queue."""
    return opportunity_service.generate_from_catalog(
        db,
        project=project,
        categories=payload.categories or None,
        countries=payload.countries or None,
        max_effort=payload.max_effort,
        only_free=payload.only_free,
        only_dofollow=payload.only_dofollow,
        include_ai_sources=payload.include_ai_sources,
        limit=payload.limit,
        campaign_id=payload.campaign_id,
    )


@project_router.post("/opportunities/prospect-competitors")
def prospect_competitors(
    limit: int = Query(150, ge=1, le=500),
    project: Project = Depends(get_project),
):
    """Link intersect against competitors (background: uses live search)."""
    job_id = jobs.enqueue_and_spawn(
        kind="competitor_prospecting", project_id=project.id, params={"limit": limit}
    )
    return {"job_id": job_id, "state": "queued"}


@project_router.post("/opportunities/prospect-mentions")
def prospect_mentions(
    limit: int = Query(60, ge=1, le=200),
    project: Project = Depends(get_project),
):
    """Find unlinked brand mentions - the fastest-converting tactic."""
    job_id = jobs.enqueue_and_spawn(
        kind="unlinked_mentions", project_id=project.id, params={"limit": limit}
    )
    return {"job_id": job_id, "state": "queued"}


@project_router.get("/opportunities/pipeline")
def pipeline(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return opportunity_service.pipeline(db, project_id=project.id)


@project_router.get("/opportunities/{opportunity_id}")
def read_opportunity(
    opportunity_id: int,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    opp = db.get(LinkOpportunity, opportunity_id)
    if opp is None or opp.project_id != project.id:
        raise HTTPException(status_code=404, detail="Opportunity not found in this project")
    source = db.get(LinkSource, opp.source_id) if opp.source_id else None
    submissions = list(
        db.execute(select(Submission).where(Submission.opportunity_id == opp.id)).scalars()
    )
    return {
        "opportunity": OpportunityOut.model_validate(opp).model_dump(),
        "source": LinkSourceOut.model_validate(source).model_dump() if source else None,
        "submissions": [SubmissionOut.model_validate(s).model_dump() for s in submissions],
    }


@project_router.patch("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def update_opportunity(
    opportunity_id: int,
    payload: OpportunityStatusUpdate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    opp = db.get(LinkOpportunity, opportunity_id)
    if opp is None or opp.project_id != project.id:
        raise HTTPException(status_code=404, detail="Opportunity not found in this project")
    try:
        updated = opportunity_service.update_status(
            db,
            opportunity_id=opportunity_id,
            status=payload.status,
            notes=payload.notes,
            landing_url=payload.landing_url,
            suggested_anchor=payload.suggested_anchor,
            campaign_id=payload.campaign_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return updated


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------


@project_router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    state: str = "",
    limit: int = Query(200, ge=1, le=2000),
):
    query = select(Submission).where(Submission.project_id == project.id)
    if state:
        query = query.where(Submission.state == state)
    return list(db.execute(query.order_by(Submission.id.desc()).limit(limit)).scalars())


@project_router.post("/submissions/prepare")
def prepare_submissions(
    payload: PrepareSubmissionsRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Build submission drafts with a filled-in brief for each opportunity."""
    created, report = submission_runner.prepare(
        db,
        project_id=project.id,
        opportunity_ids=payload.opportunity_ids or None,
        limit=payload.limit,
        auto_approve=payload.auto_approve,
    )
    return {
        **report.as_dict(),
        "submissions": [SubmissionOut.model_validate(s).model_dump() for s in created],
    }


@project_router.post("/submissions/approve")
def approve_submissions(
    payload: ApproveSubmissionsRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    return submission_runner.approve(
        db, submission_ids=payload.submission_ids, approved_by=payload.approved_by
    ).as_dict()


@project_router.post("/submissions/run")
def run_submissions(
    payload: RunSubmissionsRequest,
    project: Project = Depends(get_project),
):
    """Execute approved submissions in the background, subject to the daily caps."""
    job_id = jobs.enqueue_and_spawn(
        kind="run_submissions",
        project_id=project.id,
        params={
            "submission_ids": payload.submission_ids or None,
            "limit": payload.limit,
            "dry_run": payload.dry_run,
        },
    )
    return {
        "job_id": job_id,
        "state": "queued",
        "dry_run": settings.submissions_dry_run if payload.dry_run is None else payload.dry_run,
        "caps": {
            "per_domain_daily": settings.submissions_per_domain_daily_cap,
            "global_daily": settings.submissions_global_daily_cap,
        },
    }


@project_router.post("/submissions/{submission_id}/live-url")
def record_live_url(
    submission_id: int,
    live_url: str,
    mark_won: bool = True,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    s = db.get(Submission, submission_id)
    if s is None or s.project_id != project.id:
        raise HTTPException(status_code=404, detail="Submission not found in this project")
    updated = submission_runner.record_live_url(
        db, submission_id=submission_id, live_url=live_url, mark_won=mark_won
    )
    return SubmissionOut.model_validate(updated).model_dump()


@project_router.post("/submissions/verify")
def verify_submissions(
    limit: int = Query(25, ge=1, le=200),
    project: Project = Depends(get_project),
):
    """Check recorded listing URLs for the live link, then index what is found."""
    job_id = jobs.enqueue_and_spawn(
        kind="verify_submissions", project_id=project.id, params={"limit": limit}
    )
    return {"job_id": job_id, "state": "queued"}


@project_router.get("/submissions/settings")
def submission_settings(_project: Project = Depends(get_project)):
    return {
        "dry_run": settings.submissions_dry_run,
        "require_approval": settings.submissions_require_approval,
        "per_domain_daily_cap": settings.submissions_per_domain_daily_cap,
        "global_daily_cap": settings.submissions_global_daily_cap,
        "note": (
            "These rails are enforced server-side. Turning off dry-run means Draken will POST to "
            "third-party forms on your behalf - review every prepared submission first."
        ),
    }


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------


@project_router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return list(
        db.execute(
            select(Campaign).where(Campaign.project_id == project.id).order_by(Campaign.id.desc())
        ).scalars()
    )


@project_router.post("/campaigns", response_model=CampaignOut, status_code=201)
def create_campaign(
    payload: CampaignCreate,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    campaign = Campaign(
        project_id=project.id,
        name=payload.name,
        goal=payload.goal,
        tactics=payload.tactics,
        target_keywords=payload.target_keywords,
        landing_urls=payload.landing_urls,
        monthly_link_target=payload.monthly_link_target,
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        anchor_plan={
            "branded": 0.55, "naked_url": 0.15, "generic": 0.12,
            "partial_match": 0.13, "exact_match": 0.05,
        },
    )
    db.add(campaign)
    db.commit()
    return campaign


@project_router.get("/campaigns/{campaign_id}/progress")
def campaign_progress(
    campaign_id: int,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.project_id != project.id:
        raise HTTPException(status_code=404, detail="Campaign not found in this project")
    return opportunity_service.campaign_progress(db, campaign=campaign)


@project_router.delete("/campaigns/{campaign_id}", status_code=204)
def delete_campaign(
    campaign_id: int,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.project_id != project.id:
        raise HTTPException(status_code=404, detail="Campaign not found in this project")
    db.delete(campaign)
    db.commit()


router.include_router(catalog)
router.include_router(project_router)
