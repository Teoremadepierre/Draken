"""Job handlers - the long-running work, registered with the job runner."""

from __future__ import annotations

from draken.core.database import session_scope
from draken.core.logging import get_logger
from draken.core.models import Project, SiteAudit
from draken.engines.scheduler.jobs import register
from draken.engines.submissions import runner as submission_runner
from draken.services import audits as audit_service
from draken.services import backlinks as backlink_service
from draken.services import geo as geo_service
from draken.services import keywords as keyword_service
from draken.services import opportunities as opportunity_service

log = get_logger(__name__)


def _project(db, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError(f"project {project_id} not found")
    return project


@register("site_audit")
async def site_audit(project_id: int, params: dict) -> dict:
    with session_scope() as db:
        project = _project(db, project_id)
        audit_id = params.get("audit_id")
        if not audit_id:
            audit = SiteAudit(project_id=project.id)
            db.add(audit)
            db.flush()
            audit_id = audit.id
    with session_scope() as db:
        return await audit_service.run_audit(
            db,
            audit_id=audit_id,
            max_pages=int(params.get("max_pages") or 100),
            max_depth=int(params.get("max_depth") or 4),
        )


@register("keyword_research")
async def keyword_research(project_id: int, params: dict) -> dict:
    with session_scope() as db:
        project = _project(db, project_id)
        result = await keyword_service.research(
            db,
            project=project,
            seeds=params.get("seeds") or [],
            country=params.get("country") or project.country,
            language=params.get("language") or project.language,
            include_questions=bool(params.get("include_questions", True)),
            include_modifiers=bool(params.get("include_modifiers", True)),
            include_alphabet_soup=bool(params.get("include_alphabet_soup", False)),
            max_results=int(params.get("max_results") or 400),
            persist=True,
            use_live_suggest=bool(params.get("use_live_suggest", True)),
        )
        # Keep the response small: the keyword rows are already in the database.
        result.pop("keywords", None)
        if params.get("cluster", True):
            result["clustering"] = keyword_service.rebuild_clusters(db, project=project)
        return result


@register("rank_tracking")
async def rank_tracking(project_id: int, params: dict) -> dict:
    with session_scope() as db:
        project = _project(db, project_id)
        result = await keyword_service.track_rankings(
            db,
            project=project,
            keyword_ids=params.get("keyword_ids") or None,
            device=params.get("device") or "desktop",
        )
        result.pop("results", None)
        return result


@register("competitor_prospecting")
async def competitor_prospecting(project_id: int, params: dict) -> dict:
    with session_scope() as db:
        project = _project(db, project_id)
        return await opportunity_service.prospect_from_competitors(
            db, project=project, limit=int(params.get("limit") or 150)
        )


@register("unlinked_mentions")
async def unlinked_mentions(project_id: int, params: dict) -> dict:
    with session_scope() as db:
        project = _project(db, project_id)
        return await opportunity_service.prospect_unlinked_mentions(
            db, project=project, limit=int(params.get("limit") or 60)
        )


@register("backlink_discovery")
async def backlink_discovery(project_id: int, params: dict) -> dict:
    with session_scope() as db:
        project = _project(db, project_id)
        return await backlink_service.discover_own_links(db, project=project)


@register("backlink_recheck")
async def backlink_recheck(project_id: int, params: dict) -> dict:
    with session_scope() as db:
        return await submission_runner.recheck_backlinks(
            db, project_id=project_id, limit=int(params.get("limit") or 100)
        )


@register("run_submissions")
async def run_submissions(project_id: int, params: dict) -> dict:
    with session_scope() as db:
        report = await submission_runner.run(
            db,
            project_id=project_id,
            submission_ids=params.get("submission_ids") or None,
            limit=int(params.get("limit") or 10),
            dry_run=params.get("dry_run"),
        )
        return report.as_dict()


@register("verify_submissions")
async def verify_submissions(project_id: int, params: dict) -> dict:
    with session_scope() as db:
        report = await submission_runner.verify(
            db, project_id=project_id, limit=int(params.get("limit") or 25)
        )
        return report.as_dict()


@register("ai_visibility")
async def ai_visibility(project_id: int, params: dict) -> dict:
    with session_scope() as db:
        project = _project(db, project_id)
        return await geo_service.run_visibility(
            db,
            project=project,
            engines=params.get("engines") or None,
            prompt_ids=params.get("prompt_ids") or None,
            limit=int(params.get("limit") or 20),
        )


@register("full_sweep")
async def full_sweep(project_id: int, params: dict) -> dict:
    """The weekly "do everything" job: audit, ranks, links, opportunities, GEO."""
    out: dict = {}
    for name, fn, args in (
        ("site_audit", site_audit, {"max_pages": params.get("max_pages", 150)}),
        ("rank_tracking", rank_tracking, {}),
        ("backlink_recheck", backlink_recheck, {"limit": 150}),
        ("backlink_discovery", backlink_discovery, {}),
        ("unlinked_mentions", unlinked_mentions, {}),
        ("competitor_prospecting", competitor_prospecting, {"limit": 100}),
        ("ai_visibility", ai_visibility, {"limit": params.get("ai_prompt_limit", 15)}),
    ):
        try:
            out[name] = await fn(project_id, args)
        except Exception as exc:  # noqa: BLE001 - one failing stage must not abort the sweep
            log.error("full_sweep stage %s failed: %s", name, exc)
            out[name] = {"error": f"{type(exc).__name__}: {exc}"}

    with session_scope() as db:
        project = _project(db, project_id)
        try:
            out["catalog_opportunities"] = opportunity_service.generate_from_catalog(
                db, project=project, limit=int(params.get("opportunity_limit") or 200)
            )
            out["catalog_opportunities"].pop("tactic_playbook", None)
        except Exception as exc:  # noqa: BLE001
            out["catalog_opportunities"] = {"error": str(exc)}
    return out
