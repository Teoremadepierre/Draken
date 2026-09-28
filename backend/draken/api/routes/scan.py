"""The one-button scan, its report, the AI assistant and share links."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from draken.api.deps import current_user, get_project
from draken.core.database import get_db
from draken.core.models import Project, ShareScope
from draken.engines.scheduler import jobs as job_runner
from draken.services import accounts, assistant, diagnostics, realdata, scanner

router = APIRouter(tags=["scan"])


# ---------------------------------------------------------------------------
# schemas
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    url: str = Field(..., description="Any URL on the site. The domain is derived from it.")
    name: str = ""
    max_pages: int = Field(120, ge=1, le=2000)
    deep: bool = False
    seeds: list[str] = Field(default_factory=list)


class AssistRequest(BaseModel):
    question: str = ""
    finding_id: str = ""
    language: str = "es"
    engine: str = ""


class ShareRequest(BaseModel):
    label: str = ""
    scope: str = ShareScope.report.value
    valid_days: int | None = 30
    allow_ai_brief: bool = True


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


scan_router = APIRouter(prefix="/api/scan", tags=["scan"])


@scan_router.post("")
async def start_scan(
    payload: ScanRequest,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    """Paste a URL, get everything.

    Creates the project if it does not exist (pre-filling what the homepage
    states), then runs every module in one background job.
    """
    try:
        project, created = await scanner.ensure_project(db, url=payload.url, name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = job_runner.enqueue_and_spawn(
        kind="full_scan",
        project_id=project.id,
        params={
            "max_pages": payload.max_pages,
            "deep": payload.deep,
            "seeds": payload.seeds,
        },
    )
    return {
        "job_id": job_id,
        "project_id": project.id,
        "project_created": created,
        "domain": project.domain,
        "detected": {
            "name": project.name,
            "industry": project.industry,
            "language": project.language,
            "country": project.country,
        },
        "state": "queued",
        "stages": [
            "connectivity", "search_console", "bing_links", "audit", "keywords",
            "backlink_discovery", "opportunities", "unlinked_mentions",
            "ai_prompts", "ai_visibility",
        ],
    }


@scan_router.get("/{project_id}/report")
def scan_report(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """The single screen: scores, what is wrong, and what links you can get now."""
    return scanner.build_report(db, project=project)


# ---------------------------------------------------------------------------
# diagnostics and data sources
# ---------------------------------------------------------------------------


system_router = APIRouter(prefix="/api/system", tags=["system"])


@system_router.get("/connectivity")
async def connectivity(
    target_url: str = "",
    _user: str = Depends(current_user),
):
    """Probe every host this deployment needs, and say what each failure disables."""
    return await diagnostics.run_connectivity_check(target_url=target_url)


@system_router.get("/data-sources")
def data_sources(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    _user: str = Depends(current_user),
):
    """How real the current data is, and what would make it more real."""
    project = db.get(Project, project_id) if project_id else None
    return realdata.data_sources_status(db, project=project)


# ---------------------------------------------------------------------------
# real data import
# ---------------------------------------------------------------------------


data_router = APIRouter(prefix="/api/projects/{project_id}/data", tags=["real data"])


@data_router.post("/search-console")
async def import_gsc(
    days: int = Query(28, ge=1, le=480),
    track_top: int = Query(25, ge=0, le=500),
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Import measured impressions, clicks and positions from Search Console."""
    return await realdata.import_search_console(
        db, project=project, days=days, track_top=track_top
    )


@data_router.get("/search-console/pages")
async def gsc_pages(
    days: int = Query(28, ge=1, le=480),
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Query/page pairs plus detected cannibalisation."""
    return await realdata.import_search_console_pages(db, project=project, days=days)


@data_router.post("/bing-links")
async def import_bing(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Import Bing's free inbound-link report: real, measured backlinks."""
    return await realdata.import_bing_links(db, project=project)


@data_router.post("/bing-queries")
async def import_bing_queries(
    days: int = Query(30, ge=1, le=180),
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    return await realdata.import_bing_queries(db, project=project, days=days)


# ---------------------------------------------------------------------------
# AI assistant
# ---------------------------------------------------------------------------


assist_router = APIRouter(prefix="/api/projects/{project_id}/assist", tags=["assistant"])


@assist_router.get("/status")
def assist_status(_project: Project = Depends(get_project)):
    return {
        "available": assistant.available(),
        "engine": assistant.preferred_engine(),
        "note": (
            "With no key configured, every answer still produces a self-contained brief you "
            "can paste into any assistant."
        ),
    }


@assist_router.post("")
async def assist(
    payload: AssistRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Explain a finding and say exactly what to change."""
    return await assistant.ask(
        db,
        project=project,
        question=payload.question,
        finding_id=payload.finding_id,
        language=payload.language,
        engine=payload.engine,
    )


@assist_router.post("/plan")
async def assist_plan(
    language: str = "es",
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """A two-week plan derived from the whole report."""
    return await assistant.plan(db, project=project, language=language)


# ---------------------------------------------------------------------------
# sharing
# ---------------------------------------------------------------------------


share_router = APIRouter(prefix="/api/projects/{project_id}/shares", tags=["sharing"])


@share_router.get("")
def list_shares(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    links = accounts.list_share_links(db, project_id=project.id)
    return [
        {
            "id": link.id, "label": link.label, "scope": link.scope,
            "path": f"/shared/{link.token}", "token": link.token,
            "expires_at": link.expires_at, "revoked": link.revoked,
            "valid": link.is_valid, "view_count": link.view_count,
            "last_viewed_at": link.last_viewed_at, "created_by": link.created_by,
            "allow_ai_brief": link.allow_ai_brief,
        }
        for link in links
    ]


@share_router.post("", status_code=201)
def create_share(
    payload: ShareRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    """A read-only link so a colleague can open this report without an account."""
    link = accounts.create_share_link(
        db, project=project, label=payload.label, scope=payload.scope,
        created_by=user, valid_days=payload.valid_days,
        allow_ai_brief=payload.allow_ai_brief,
    )
    return {
        "id": link.id, "token": link.token, "path": f"/shared/{link.token}",
        "expires_at": link.expires_at, "scope": link.scope,
        "note": (
            "Anyone with this link can read the report. It carries no write access and no "
            "API keys. Revoke it at any time."
        ),
    }


@share_router.delete("/{link_id}", status_code=204)
def revoke_share(
    link_id: int,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    if not accounts.revoke_share_link(db, link_id=link_id):
        raise HTTPException(status_code=404, detail="Share link not found")


# --- public (token) endpoint, no auth -------------------------------------

public_router = APIRouter(prefix="/api/shared", tags=["sharing"])


@public_router.get("/{token}")
def read_shared_report(token: str, request: Request, db: Session = Depends(get_db)):
    """Read a shared report by token. No account, no keys, read-only."""
    link, project = accounts.resolve_share_link(db, token=token)
    if link is None or project is None:
        raise HTTPException(status_code=404, detail="This link is not valid or has expired")

    report = scanner.build_report(db, project=project)

    if link.scope == ShareScope.backlinks.value:
        report = {
            "project": report["project"], "scores": report["scores"],
            "headline": report["headline"], "backlinks": report["backlinks"],
            "link_profile": report["link_profile"],
        }
    elif link.scope == ShareScope.report.value:
        report.pop("pipeline", None)

    payload = {
        "shared": True,
        "label": link.label,
        "scope": link.scope,
        "expires_at": link.expires_at,
        "report": report,
    }

    if link.allow_ai_brief:
        context = assistant.project_context(db, project=project)
        compact = {
            "scores": report["scores"],
            "headline": report.get("headline"),
            "top_fixes": [
                {k: f[k] for k in ("priority", "severity", "title", "affected", "category")}
                for f in report.get("fixes", [])[:15]
            ],
        }
        payload["ai_brief"] = assistant.build_brief(
            context={**context, "report": compact},
            question=(
                "Dame un plan priorizado de dos semanas para este sitio, con acciones concretas."
            ),
            language=project.language,
        )
        payload["ai_brief_note"] = (
            "Copia esto y pégalo en Claude o en el asistente que uses: lleva todo el contexto "
            "necesario para trabajar el mismo informe."
        )
    return payload


router.include_router(scan_router)
router.include_router(system_router)
router.include_router(data_router)
router.include_router(assist_router)
router.include_router(share_router)
router.include_router(public_router)
