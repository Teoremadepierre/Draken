"""Background job status and control."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.api.deps import current_user, get_project
from draken.core.database import get_db
from draken.core.models import ActivityLog, Job, Project
from draken.core.schemas import JobOut
from draken.engines.scheduler import jobs as job_runner

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    _user: str = Depends(current_user),
    project_id: int | None = None,
    state: str = "",
    kind: str = "",
    limit: int = Query(50, ge=1, le=500),
):
    query = select(Job)
    if project_id is not None:
        query = query.where(Job.project_id == project_id)
    if state:
        query = query.where(Job.state == state)
    if kind:
        query = query.where(Job.kind == kind)
    return list(db.execute(query.order_by(Job.id.desc()).limit(limit)).scalars())


@router.get("/jobs/kinds")
def job_kinds(_user: str = Depends(current_user)):
    return {"kinds": job_runner.registered_kinds()}


@router.get("/jobs/{job_id}", response_model=JobOut)
def read_job(job_id: int, db: Session = Depends(get_db), _user: str = Depends(current_user)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, _user: str = Depends(current_user)):
    return {"cancelled": job_runner.cancel(job_id)}


@router.post("/projects/{project_id}/jobs/{kind}")
def enqueue_job(
    kind: str,
    params: dict | None = None,
    project: Project = Depends(get_project),
):
    """Kick off any registered job for this project."""
    try:
        job_id = job_runner.enqueue_and_spawn(
            kind=kind, project_id=project.id, params=params or {}
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"job_id": job_id, "kind": kind, "state": "queued"}


@router.get("/projects/{project_id}/activity")
def activity(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000),
):
    """The audit trail: everything Draken did that touched the outside world."""
    rows = list(
        db.execute(
            select(ActivityLog)
            .where(ActivityLog.project_id == project.id)
            .order_by(ActivityLog.id.desc())
            .limit(limit)
        ).scalars()
    )
    return [
        {
            "id": r.id, "actor": r.actor, "action": r.action,
            "entity_type": r.entity_type, "entity_id": r.entity_id,
            "detail": r.detail, "created_at": r.created_at,
        }
        for r in rows
    ]
