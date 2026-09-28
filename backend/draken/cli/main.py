"""Draken command line interface.

Everything the dashboard can do is available headless, so audits, rank tracking
and link sweeps can run from cron without a browser.

    draken serve
    draken init-db
    draken hash-password 'secret'
    draken project add --name "Acme" --domain acme.com --country ES --language es
    draken keywords research 1 "seo software" "keyword tool"
    draken audit 1 --max-pages 200
    draken opportunities generate 1
    draken submissions prepare 1 --limit 20
    draken ai run 1
    draken sweep 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from draken.core.config import settings
from draken.core.database import init_db, session_scope
from draken.core.logging import setup_logging
from draken.core.models import Project
from draken.core.security import hash_password
from draken.core.urls import normalize_domain


def _out(data) -> None:
    print(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def _get_project(db, identifier: str) -> Project:
    from sqlalchemy import select

    if identifier.isdigit():
        project = db.get(Project, int(identifier))
    else:
        project = db.execute(
            select(Project).where(Project.domain == normalize_domain(identifier))
        ).scalars().first()
    if project is None:
        raise SystemExit(f"error: no project matching {identifier!r}")
    return project


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        "draken.api.app:app",
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )


def cmd_init_db(_args: argparse.Namespace) -> None:
    init_db()
    from draken.services.opportunities import sync_catalog

    with session_scope() as db:
        result = sync_catalog(db)
    _out({"database": settings.database_url, "catalog": result})


def cmd_hash_password(args: argparse.Namespace) -> None:
    print(hash_password(args.password))
    print(
        "\nAdd this to your .env as:\nDRAKEN_ADMIN_PASSWORD_HASH=<the line above>",
        file=sys.stderr,
    )


def cmd_project_add(args: argparse.Namespace) -> None:
    init_db()
    domain = normalize_domain(args.domain)
    if not domain:
        raise SystemExit(f"error: could not parse a domain from {args.domain!r}")
    with session_scope() as db:
        from sqlalchemy import select

        if db.execute(select(Project).where(Project.domain == domain)).scalars().first():
            raise SystemExit(f"error: project for {domain} already exists")
        project = Project(
            name=args.name,
            domain=domain,
            base_url=args.base_url or f"https://{domain}",
            country=(args.country or "US").upper(),
            language=(args.language or "en").lower(),
            industry=args.industry or "",
            competitors=[normalize_domain(c) for c in (args.competitor or []) if normalize_domain(c)],
            brand_terms=[args.name],
        )
        db.add(project)
        db.flush()
        from draken.core.models import BusinessProfile

        db.add(
            BusinessProfile(
                project_id=project.id, display_name=args.name,
                website=project.base_url, country=project.country,
            )
        )
        db.flush()
        from draken.services.opportunities import generate_from_catalog

        opportunities = generate_from_catalog(db, project=project, limit=250)
        opportunities.pop("tactic_playbook", None)
        _out({"project_id": project.id, "domain": domain, "opportunities": opportunities})


def cmd_project_list(_args: argparse.Namespace) -> None:
    from sqlalchemy import select

    with session_scope() as db:
        rows = list(db.execute(select(Project).order_by(Project.id)).scalars())
        _out([
            {
                "id": p.id, "name": p.name, "domain": p.domain,
                "country": p.country, "language": p.language,
                "competitors": p.competitors,
            }
            for p in rows
        ])


def cmd_keywords_research(args: argparse.Namespace) -> None:
    from draken.services import keywords as keyword_service

    async def run() -> None:
        with session_scope() as db:
            project = _get_project(db, args.project)
            result = await keyword_service.research(
                db, project=project, seeds=args.seeds,
                country=args.country or project.country,
                language=args.language or project.language,
                max_results=args.max_results,
                include_alphabet_soup=args.alphabet_soup,
                use_live_suggest=not args.offline,
            )
            result.pop("keywords", None)
            if not args.no_cluster:
                result["clustering"] = keyword_service.rebuild_clusters(db, project=project)
            _out(result)

    asyncio.run(run())


def cmd_keywords_track(args: argparse.Namespace) -> None:
    from draken.services import keywords as keyword_service

    async def run() -> None:
        with session_scope() as db:
            project = _get_project(db, args.project)
            result = await keyword_service.track_rankings(db, project=project)
            result.pop("results", None)
            _out(result)

    asyncio.run(run())


def cmd_audit(args: argparse.Namespace) -> None:
    from draken.services import audits as audit_service

    async def run() -> None:
        with session_scope() as db:
            project = _get_project(db, args.project)
            audit = audit_service.create_audit(db, project=project)
            audit_id = audit.id
        with session_scope() as db:
            _out(await audit_service.run_audit(
                db, audit_id=audit_id, max_pages=args.max_pages, max_depth=args.max_depth
            ))

    asyncio.run(run())


def cmd_opportunities_generate(args: argparse.Namespace) -> None:
    from draken.services.opportunities import generate_from_catalog

    with session_scope() as db:
        project = _get_project(db, args.project)
        result = generate_from_catalog(
            db, project=project, limit=args.limit, max_effort=args.max_effort,
            only_dofollow=args.dofollow_only,
        )
        result.pop("tactic_playbook", None)
        _out(result)


def cmd_opportunities_prospect(args: argparse.Namespace) -> None:
    from draken.services.opportunities import (
        prospect_from_competitors,
        prospect_unlinked_mentions,
    )

    async def run() -> None:
        with session_scope() as db:
            project = _get_project(db, args.project)
            _out(
                {
                    "competitors": await prospect_from_competitors(db, project=project),
                    "unlinked_mentions": await prospect_unlinked_mentions(db, project=project),
                }
            )

    asyncio.run(run())


def cmd_submissions_prepare(args: argparse.Namespace) -> None:
    from draken.engines.submissions import runner

    with session_scope() as db:
        project = _get_project(db, args.project)
        created, report = runner.prepare(
            db, project_id=project.id, limit=args.limit, auto_approve=args.auto_approve
        )
        _out({**report.as_dict(), "submission_ids": [s.id for s in created]})


def cmd_submissions_run(args: argparse.Namespace) -> None:
    from draken.engines.submissions import runner

    async def run() -> None:
        with session_scope() as db:
            project = _get_project(db, args.project)
            report = await runner.run(
                db, project_id=project.id, limit=args.limit,
                dry_run=None if args.live is None else not args.live,
            )
            _out(report.as_dict())

    asyncio.run(run())


def cmd_ai_generate(args: argparse.Namespace) -> None:
    from draken.services.geo import generate_prompt_set

    with session_scope() as db:
        project = _get_project(db, args.project)
        result = generate_prompt_set(db, project=project, limit=args.limit)
        result.pop("prompts", None)
        _out(result)


def cmd_ai_run(args: argparse.Namespace) -> None:
    from draken.services.geo import run_visibility, summary

    async def run() -> None:
        with session_scope() as db:
            project = _get_project(db, args.project)
            result = await run_visibility(db, project=project, limit=args.limit)
            _out({"run": result, "summary": summary(db, project=project)})

    asyncio.run(run())


def cmd_geo_assets(args: argparse.Namespace) -> None:
    from draken.services.geo import geo_assets

    with session_scope() as db:
        project = _get_project(db, args.project)
        data = geo_assets(db, project=project)
    if args.llms_txt:
        print(data["llms_txt"])
    elif args.schema:
        print(data["schema"]["script_tag"])
    else:
        _out({k: v for k, v in data.items() if k != "schema"})


def cmd_sweep(args: argparse.Namespace) -> None:
    """The cron entry point: run everything for a project."""
    from draken.engines.scheduler.handlers import full_sweep

    async def run() -> None:
        with session_scope() as db:
            project = _get_project(db, args.project)
            project_id = project.id
        _out(await full_sweep(project_id, {"max_pages": args.max_pages}))

    asyncio.run(run())


def cmd_report(args: argparse.Namespace) -> None:
    from draken.services import backlinks as backlink_service
    from draken.services import geo as geo_service
    from draken.services import keywords as keyword_service
    from draken.services import opportunities as opportunity_service

    with session_scope() as db:
        project = _get_project(db, args.project)
        _out(
            {
                "project": {"id": project.id, "name": project.name, "domain": project.domain},
                "link_profile": backlink_service.profile_report(db, project=project),
                "rankings": keyword_service.ranking_overview(db, project=project),
                "pipeline": opportunity_service.pipeline(db, project_id=project.id),
                "ai_visibility": geo_service.summary(db, project=project),
            }
        )


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="draken", description="Draken SEO Suite CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="run the API + dashboard")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("init-db", help="create tables and seed the link source catalog")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("hash-password", help="generate a password hash for DRAKEN_ADMIN_PASSWORD_HASH")
    p.add_argument("password")
    p.set_defaults(func=cmd_hash_password)

    project = sub.add_parser("project", help="manage projects").add_subparsers(
        dest="project_command", required=True
    )
    p = project.add_parser("add")
    p.add_argument("--name", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--base-url")
    p.add_argument("--country", default="US")
    p.add_argument("--language", default="en")
    p.add_argument("--industry")
    p.add_argument("--competitor", action="append", help="repeatable")
    p.set_defaults(func=cmd_project_add)
    p = project.add_parser("list")
    p.set_defaults(func=cmd_project_list)

    kw = sub.add_parser("keywords", help="keyword research and tracking").add_subparsers(
        dest="keywords_command", required=True
    )
    p = kw.add_parser("research")
    p.add_argument("project")
    p.add_argument("seeds", nargs="+")
    p.add_argument("--country")
    p.add_argument("--language")
    p.add_argument("--max-results", type=int, default=400)
    p.add_argument("--alphabet-soup", action="store_true")
    p.add_argument("--offline", action="store_true", help="skip live autocomplete")
    p.add_argument("--no-cluster", action="store_true")
    p.set_defaults(func=cmd_keywords_research)
    p = kw.add_parser("track")
    p.add_argument("project")
    p.set_defaults(func=cmd_keywords_track)

    p = sub.add_parser("audit", help="run a site audit")
    p.add_argument("project")
    p.add_argument("--max-pages", type=int, default=100)
    p.add_argument("--max-depth", type=int, default=4)
    p.set_defaults(func=cmd_audit)

    opp = sub.add_parser("opportunities", help="link opportunities").add_subparsers(
        dest="opportunities_command", required=True
    )
    p = opp.add_parser("generate")
    p.add_argument("project")
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--max-effort", type=int, default=5)
    p.add_argument("--dofollow-only", action="store_true")
    p.set_defaults(func=cmd_opportunities_generate)
    p = opp.add_parser("prospect", help="competitor link intersect + unlinked mentions")
    p.add_argument("project")
    p.set_defaults(func=cmd_opportunities_prospect)

    sb = sub.add_parser("submissions", help="link submissions").add_subparsers(
        dest="submissions_command", required=True
    )
    p = sb.add_parser("prepare")
    p.add_argument("project")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--auto-approve", action="store_true")
    p.set_defaults(func=cmd_submissions_prepare)
    p = sb.add_parser("run")
    p.add_argument("project")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--live", action="store_true", default=None,
                   help="actually submit (overrides DRAKEN_SUBMISSIONS_DRY_RUN)")
    p.set_defaults(func=cmd_submissions_run)

    ai = sub.add_parser("ai", help="AI visibility").add_subparsers(
        dest="ai_command", required=True
    )
    p = ai.add_parser("generate-prompts")
    p.add_argument("project")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_ai_generate)
    p = ai.add_parser("run")
    p.add_argument("project")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_ai_run)
    p = ai.add_parser("assets")
    p.add_argument("project")
    p.add_argument("--llms-txt", action="store_true")
    p.add_argument("--schema", action="store_true")
    p.set_defaults(func=cmd_geo_assets)

    p = sub.add_parser("sweep", help="run every module for a project (cron entry point)")
    p.add_argument("project")
    p.add_argument("--max-pages", type=int, default=150)
    p.set_defaults(func=cmd_sweep)

    p = sub.add_parser("report", help="print the full project report as JSON")
    p.add_argument("project")
    p.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
