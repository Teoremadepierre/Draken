"""Site audit and on-page analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.api.deps import current_user, get_project
from draken.core.database import get_db
from draken.core.models import AuditIssue, CrawledPage, Project, SiteAudit
from draken.core.schemas import AuditRequest, OnPageRequest, SiteAuditOut
from draken.engines.onpage.analyzer import analyse_url
from draken.engines.scheduler import jobs
from draken.services import audits as audit_service

router = APIRouter(prefix="/api/projects/{project_id}", tags=["site audit"])


@router.get("/audits", response_model=list[SiteAuditOut])
def list_audits(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return list(
        db.execute(
            select(SiteAudit).where(SiteAudit.project_id == project.id).order_by(SiteAudit.id.desc())
        ).scalars()
    )


@router.post("/audits")
def start_audit(
    payload: AuditRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Crawls run in the background - poll /api/jobs/{id} or the audit record."""
    audit = audit_service.create_audit(db, project=project)
    job_id = jobs.enqueue_and_spawn(
        kind="site_audit",
        project_id=project.id,
        params={
            "audit_id": audit.id,
            "max_pages": payload.max_pages,
            "max_depth": payload.max_depth,
        },
    )
    return {"audit_id": audit.id, "job_id": job_id, "state": "queued"}


@router.get("/audits/latest")
def latest(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    audit = audit_service.latest_audit(db, project_id=project.id)
    if audit is None:
        return {"audit": None, "issues": [], "message": "No audit yet. Start one to see results."}
    return {
        "audit": SiteAuditOut.model_validate(audit).model_dump(),
        "issues": audit_service.issues_grouped(db, audit_id=audit.id),
    }


@router.get("/audits/{audit_id}")
def read_audit(
    audit_id: int, project: Project = Depends(get_project), db: Session = Depends(get_db)
):
    audit = db.get(SiteAudit, audit_id)
    if audit is None or audit.project_id != project.id:
        raise HTTPException(status_code=404, detail="Audit not found in this project")
    return {
        "audit": SiteAuditOut.model_validate(audit).model_dump(),
        "issues": audit_service.issues_grouped(db, audit_id=audit.id),
    }


@router.get("/audits/{audit_id}/pages")
def audit_pages(
    audit_id: int,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    status_code: int | None = None,
    min_words: int | None = None,
    sort: str = Query("inlinks", pattern="^(inlinks|words|depth|response|ai)$"),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = 0,
):
    audit = db.get(SiteAudit, audit_id)
    if audit is None or audit.project_id != project.id:
        raise HTTPException(status_code=404, detail="Audit not found in this project")

    query = select(CrawledPage).where(CrawledPage.audit_id == audit_id)
    if status_code is not None:
        query = query.where(CrawledPage.status_code == status_code)
    if min_words is not None:
        query = query.where(CrawledPage.word_count >= min_words)
    order = {
        "inlinks": CrawledPage.inlinks.desc(),
        "words": CrawledPage.word_count.desc(),
        "depth": CrawledPage.depth.asc(),
        "response": CrawledPage.response_ms.desc(),
        "ai": CrawledPage.ai_readiness.desc(),
    }[sort]
    pages = list(db.execute(query.order_by(order).offset(offset).limit(limit)).scalars())
    return [
        {
            "id": p.id, "url": p.url, "status_code": p.status_code, "title": p.title,
            "meta_description": p.meta_description, "h1": p.h1, "h2_count": p.h2_count,
            "word_count": p.word_count, "internal_links": p.internal_links,
            "external_links": p.external_links, "inlinks": p.inlinks,
            "images_without_alt": p.images_without_alt, "canonical": p.canonical,
            "robots_meta": p.robots_meta, "response_ms": p.response_ms, "depth": p.depth,
            "has_schema": p.has_schema, "schema_types": p.schema_types,
            "ai_readiness": p.ai_readiness,
        }
        for p in pages
    ]


@router.get("/audits/{audit_id}/issues/{code}")
def issue_detail(
    code: str,
    audit_id: int,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    limit: int = Query(500, ge=1, le=5000),
):
    audit = db.get(SiteAudit, audit_id)
    if audit is None or audit.project_id != project.id:
        raise HTTPException(status_code=404, detail="Audit not found in this project")
    rows = list(
        db.execute(
            select(AuditIssue)
            .where(AuditIssue.audit_id == audit_id, AuditIssue.code == code)
            .limit(limit)
        ).scalars()
    )
    if not rows:
        return {"code": code, "count": 0, "urls": []}
    first = rows[0]
    return {
        "code": code,
        "severity": first.severity,
        "title": first.title,
        "description": first.description,
        "how_to_fix": first.how_to_fix,
        "category": first.category,
        "count": len(rows),
        "urls": [{"url": r.url, "detail": r.detail} for r in rows],
    }


@router.post("/onpage")
async def onpage(
    payload: OnPageRequest,
    project: Project = Depends(get_project),
    _user: str = Depends(current_user),
):
    """Score a single URL against a target keyword."""
    report = await analyse_url(
        payload.url,
        target_keyword=payload.target_keyword,
        secondary_keywords=payload.secondary_keywords,
    )
    return report.as_dict()
