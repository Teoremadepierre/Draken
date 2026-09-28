"""Backlink index, profile, competitor comparison and disavow endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.api.deps import get_project
from draken.core.database import get_db
from draken.core.models import Backlink, LinkStatus, Project
from draken.core.schemas import BacklinkImport, BacklinkOut, BacklinkProfileOut
from draken.engines.backlinks import toxicity
from draken.engines.scheduler import jobs
from draken.services import backlinks as backlink_service

router = APIRouter(prefix="/api/projects/{project_id}/backlinks", tags=["backlinks"])


@router.get("", response_model=list[BacklinkOut])
def list_backlinks(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    status: str = "",
    link_type: str = "",
    min_authority: float = 0.0,
    min_toxicity: float = 0.0,
    q: str = "",
    sort: str = Query("authority", pattern="^(authority|toxicity|first_seen|domain)$"),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = 0,
):
    query = select(Backlink).where(Backlink.project_id == project.id)
    if status:
        query = query.where(Backlink.status == status)
    if link_type:
        query = query.where(Backlink.link_type == link_type)
    if min_authority:
        query = query.where(Backlink.domain_authority >= min_authority)
    if min_toxicity:
        query = query.where(Backlink.toxicity_score >= min_toxicity)
    if q:
        query = query.where(Backlink.source_domain.contains(q.lower()))
    order = {
        "authority": Backlink.domain_authority.desc(),
        "toxicity": Backlink.toxicity_score.desc(),
        "first_seen": Backlink.first_seen.desc(),
        "domain": Backlink.source_domain.asc(),
    }[sort]
    return list(db.execute(query.order_by(order).offset(offset).limit(limit)).scalars())


@router.get("/profile", response_model=BacklinkProfileOut)
def profile(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return backlink_service.profile_report(db, project=project)


@router.post("/import")
async def import_links(
    payload: BacklinkImport,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    verify: bool = False,
):
    """Import from Search Console, Ahrefs, Semrush or any CSV. Columns are matched loosely."""
    return await backlink_service.import_links(
        db,
        project=project,
        rows=payload.rows,
        csv_text=payload.csv_text,
        discovered_via=payload.discovered_via,
        verify=verify,
    )


@router.post("/discover")
def discover(project: Project = Depends(get_project)):
    """Search public results for pages that mention or link to us (runs in background)."""
    job_id = jobs.enqueue_and_spawn(kind="backlink_discovery", project_id=project.id)
    return {"job_id": job_id, "state": "queued"}


@router.post("/recheck")
def recheck(
    limit: int = Query(100, ge=1, le=1000),
    project: Project = Depends(get_project),
):
    """Re-verify indexed links to catch lost ones (runs in background)."""
    job_id = jobs.enqueue_and_spawn(
        kind="backlink_recheck", project_id=project.id, params={"limit": limit}
    )
    return {"job_id": job_id, "state": "queued"}


@router.get("/competitors")
def competitors(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return backlink_service.competitor_comparison(db, project=project)


@router.get("/toxic")
def toxic_links(
    threshold: float = Query(50.0, ge=0, le=100),
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    rows = list(
        db.execute(
            select(Backlink)
            .where(Backlink.project_id == project.id, Backlink.toxicity_score >= threshold)
            .order_by(Backlink.toxicity_score.desc())
        ).scalars()
    )
    return {
        "threshold": threshold,
        "count": len(rows),
        "links": [
            {
                "id": b.id,
                "source_url": b.source_url,
                "source_domain": b.source_domain,
                "anchor_text": b.anchor_text,
                "link_type": b.link_type,
                "domain_authority": b.domain_authority,
                "toxicity_score": b.toxicity_score,
                "reasons": b.toxicity_reasons,
                "recommended_action": toxicity.classify_action(
                    b.toxicity_score, link_type=b.link_type
                ),
            }
            for b in rows
        ],
        "guidance": (
            "Try removal requests before disavowing. Google's own guidance is that most sites never "
            "need a disavow file - only use one if you have a manual action or clear evidence of harm."
        ),
    }


@router.get("/disavow")
def disavow(
    threshold: float = Query(70.0, ge=0, le=100),
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    content = backlink_service.disavow_file(db, project=project, threshold=threshold)
    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="disavow-{project.domain}.txt"'},
    )


@router.post("")
def add_backlink(
    source_url: str,
    anchor_text: str = "",
    target_url: str = "",
    link_type: str = "unknown",
    domain_authority: float = 0.0,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Record a link manually (for example one you just earned)."""
    from draken.core.urls import normalize_domain, normalize_url

    url = normalize_url(source_url if "//" in source_url else f"https://{source_url}")
    domain = normalize_domain(url)
    if not domain:
        raise HTTPException(status_code=422, detail=f"Could not parse a domain from {source_url!r}")
    exists = db.execute(
        select(Backlink).where(Backlink.project_id == project.id, Backlink.source_url == url)
    ).scalars().first()
    if exists:
        raise HTTPException(status_code=409, detail="That source URL is already indexed")

    tox, reasons = toxicity.score_link(
        source_url=url,
        source_domain=domain,
        anchor_text=anchor_text,
        link_type=link_type,
        domain_authority=domain_authority,
        target_domain=project.domain,
    )
    link = Backlink(
        project_id=project.id,
        source_url=url,
        source_domain=domain,
        target_url=target_url or project.base_url,
        anchor_text=anchor_text,
        link_type=link_type,
        status=LinkStatus.live.value,
        domain_authority=domain_authority,
        toxicity_score=tox,
        toxicity_reasons=reasons,
        discovered_via="manual",
    )
    db.add(link)
    db.commit()
    return {"id": link.id, "source_domain": domain, "toxicity_score": tox}


@router.delete("/{backlink_id}", status_code=204)
def delete_backlink(
    backlink_id: int, project: Project = Depends(get_project), db: Session = Depends(get_db)
):
    link = db.get(Backlink, backlink_id)
    if link is None or link.project_id != project.id:
        raise HTTPException(status_code=404, detail="Backlink not found in this project")
    db.delete(link)
    db.commit()
