"""Keyword research, clustering, rank tracking and gap analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.api.deps import current_user, get_project
from draken.core.database import get_db
from draken.core.models import Keyword, KeywordCluster, Project, RankSnapshot
from draken.core.schemas import (
    KeywordClusterOut,
    KeywordGapRequest,
    KeywordManualAdd,
    KeywordOut,
    KeywordResearchRequest,
    RankSnapshotOut,
    TrackRequest,
)
from draken.engines.keywords import suggest
from draken.engines.scheduler import jobs
from draken.services import keywords as keyword_service

router = APIRouter(prefix="/api/projects/{project_id}", tags=["keywords"])


@router.get("/keywords", response_model=list[KeywordOut])
def list_keywords(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    q: str = "",
    intent: str = "",
    cluster_id: int | None = None,
    tracked_only: bool = False,
    min_volume: int = 0,
    max_difficulty: float = 100.0,
    sort: str = Query("opportunity", pattern="^(opportunity|volume|difficulty|term)$"),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = 0,
):
    query = select(Keyword).where(Keyword.project_id == project.id)
    if q:
        query = query.where(Keyword.term.contains(q.lower()))
    if intent:
        query = query.where(Keyword.intent == intent)
    if cluster_id is not None:
        query = query.where(Keyword.cluster_id == cluster_id)
    if tracked_only:
        query = query.where(Keyword.is_tracked.is_(True))
    if min_volume:
        query = query.where(Keyword.volume >= min_volume)
    if max_difficulty < 100:
        query = query.where(Keyword.difficulty <= max_difficulty)

    order = {
        "opportunity": Keyword.opportunity_score.desc(),
        "volume": Keyword.volume.desc(),
        "difficulty": Keyword.difficulty.asc(),
        "term": Keyword.term.asc(),
    }[sort]
    return list(db.execute(query.order_by(order).offset(offset).limit(limit)).scalars())


@router.post("/keywords/research")
async def research(
    payload: KeywordResearchRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    background: bool = False,
):
    """Expand seed terms into a scored keyword universe.

    Set ``background=true`` for large expansions; poll /api/jobs/{id} for the result.
    """
    if background:
        job_id = jobs.enqueue_and_spawn(
            kind="keyword_research",
            project_id=project.id,
            params=payload.model_dump(),
        )
        return {"job_id": job_id, "state": "queued"}

    result = await keyword_service.research(
        db,
        project=project,
        seeds=payload.seeds,
        country=payload.country or project.country,
        language=payload.language or project.language,
        include_questions=payload.include_questions,
        include_modifiers=payload.include_modifiers,
        include_alphabet_soup=payload.include_alphabet_soup,
        max_results=payload.max_results,
        persist=payload.persist,
        use_live_suggest=payload.use_live_suggest,
    )
    return result


@router.post("/keywords")
def add_keywords(
    payload: KeywordManualAdd,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    return keyword_service.add_manual(
        db, project=project, terms=payload.terms, country=payload.country, track=payload.track
    )


@router.patch("/keywords/{keyword_id}")
def update_keyword(
    keyword_id: int,
    is_tracked: bool | None = None,
    notes: str | None = None,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    kw = db.get(Keyword, keyword_id)
    if kw is None or kw.project_id != project.id:
        raise HTTPException(status_code=404, detail="Keyword not found in this project")
    if is_tracked is not None:
        kw.is_tracked = is_tracked
    if notes is not None:
        kw.notes = notes
    db.commit()
    return {"id": kw.id, "term": kw.term, "is_tracked": kw.is_tracked}


@router.post("/keywords/track-bulk")
def track_bulk(
    keyword_ids: list[int],
    tracked: bool = True,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    rows = list(
        db.execute(
            select(Keyword).where(Keyword.project_id == project.id, Keyword.id.in_(keyword_ids))
        ).scalars()
    )
    for kw in rows:
        kw.is_tracked = tracked
    db.commit()
    return {"updated": len(rows), "tracked": tracked}


@router.delete("/keywords/{keyword_id}", status_code=204)
def delete_keyword(
    keyword_id: int,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    kw = db.get(Keyword, keyword_id)
    if kw is None or kw.project_id != project.id:
        raise HTTPException(status_code=404, detail="Keyword not found in this project")
    db.delete(kw)
    db.commit()


# --- clustering ------------------------------------------------------------


@router.get("/clusters", response_model=list[KeywordClusterOut])
def list_clusters(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return list(
        db.execute(
            select(KeywordCluster)
            .where(KeywordCluster.project_id == project.id)
            .order_by(KeywordCluster.total_volume.desc())
        ).scalars()
    )


@router.post("/clusters/rebuild")
def rebuild_clusters(
    threshold: float = Query(0.6, ge=0.1, le=0.95),
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    return keyword_service.rebuild_clusters(db, project=project, threshold=threshold)


@router.patch("/clusters/{cluster_id}")
def update_cluster(
    cluster_id: int,
    target_url: str | None = None,
    label: str | None = None,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    cluster = db.get(KeywordCluster, cluster_id)
    if cluster is None or cluster.project_id != project.id:
        raise HTTPException(status_code=404, detail="Cluster not found in this project")
    if target_url is not None:
        cluster.target_url = target_url
    if label is not None:
        cluster.label = label
    db.commit()
    return {"id": cluster.id, "label": cluster.label, "target_url": cluster.target_url}


# --- rank tracking ---------------------------------------------------------


@router.post("/rankings/track")
async def track(
    payload: TrackRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    background: bool = False,
):
    if background:
        job_id = jobs.enqueue_and_spawn(
            kind="rank_tracking", project_id=project.id, params=payload.model_dump()
        )
        return {"job_id": job_id, "state": "queued"}
    return await keyword_service.track_rankings(
        db, project=project, keyword_ids=payload.keyword_ids or None, device=payload.device
    )


@router.get("/rankings/overview")
def rankings_overview(
    days: int = Query(30, ge=1, le=365),
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    return keyword_service.ranking_overview(db, project=project, days=days)


@router.get("/keywords/{keyword_id}/history", response_model=list[RankSnapshotOut])
def keyword_history(
    keyword_id: int,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    kw = db.get(Keyword, keyword_id)
    if kw is None or kw.project_id != project.id:
        raise HTTPException(status_code=404, detail="Keyword not found in this project")
    return list(
        db.execute(
            select(RankSnapshot)
            .where(RankSnapshot.keyword_id == keyword_id)
            .order_by(RankSnapshot.captured_on.asc())
        ).scalars()
    )


# --- gap analysis ----------------------------------------------------------


@router.post("/keywords/gap")
async def gap(
    payload: KeywordGapRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    return await keyword_service.keyword_gap(
        db, project=project, competitors=payload.competitors or None, limit=payload.limit
    )


# --- raw suggest passthrough ----------------------------------------------


@router.get("/keywords/suggest")
async def live_suggest(
    seed: str,
    project: Project = Depends(get_project),
    _user: str = Depends(current_user),
):
    """Raw autocomplete lookup - useful for exploring before committing to research."""
    result = await suggest.fetch_suggestions(
        [seed], country=project.country, language=project.language
    )
    return {"seed": seed, "suggestions": result.get(seed, [])}
