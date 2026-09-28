"""Export and import a project, so a deployment is never a one-way door.

The reason this exists: a free platform database is time-limited, and moving to
your own server later should not mean starting over. An export is a single JSON
file containing everything that took work to produce - the business profile, the
keyword universe, the backlink index, the opportunity pipeline with its statuses,
campaigns, submissions, outreach and the AI prompt set.

What is deliberately left out: the link source catalog (it ships with the code
and reloads itself), job history, and anything secret. An export file is safe to
move around, but it does contain your business contact details, so treat it the
way you would treat any business record.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from draken import __version__
from draken.core.logging import get_logger
from draken.core.models import (
    AIPrompt,
    AIVisibilityRun,
    Backlink,
    BusinessProfile,
    Campaign,
    CompetitorBacklink,
    Keyword,
    KeywordCluster,
    LinkOpportunity,
    LinkSource,
    OutreachMessage,
    OutreachTemplate,
    Project,
    RankSnapshot,
    Submission,
)

log = get_logger(__name__)

FORMAT_VERSION = 1


def _serialise(model) -> dict:
    """Row to plain JSON, with dates as ISO strings."""
    out: dict[str, Any] = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name)
        if isinstance(value, datetime | date):
            value = value.isoformat()
        out[column.name] = value
    return out


def _parse(value, column) -> Any:
    """ISO string back to a date or datetime where the column expects one."""
    if value is None or not isinstance(value, str):
        return value
    python_type = getattr(column.type, "python_type", None)
    try:
        if python_type is datetime:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        if python_type is date:
            return date.fromisoformat(value[:10])
    except (ValueError, NotImplementedError):
        return value
    return value


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def export_project(db: Session, *, project: Project) -> dict:
    """Everything about one project, as a portable dict."""
    keywords = list(
        db.execute(select(Keyword).where(Keyword.project_id == project.id)).scalars()
    )
    keyword_ids = [k.id for k in keywords]

    clusters = list(
        db.execute(select(KeywordCluster).where(KeywordCluster.project_id == project.id)).scalars()
    )
    snapshots = (
        list(
            db.execute(
                select(RankSnapshot).where(RankSnapshot.keyword_id.in_(keyword_ids))
            ).scalars()
        )
        if keyword_ids
        else []
    )
    opportunities = list(
        db.execute(select(LinkOpportunity).where(LinkOpportunity.project_id == project.id)).scalars()
    )
    submissions = list(
        db.execute(select(Submission).where(Submission.project_id == project.id)).scalars()
    )
    prompts = list(
        db.execute(select(AIPrompt).where(AIPrompt.project_id == project.id)).scalars()
    )

    # Opportunities reference catalog rows by id, which differ between installs.
    # Carry the slug instead and re-resolve it on import.
    source_slugs = {
        s.id: s.slug
        for s in db.execute(
            select(LinkSource).where(
                LinkSource.id.in_([o.source_id for o in opportunities if o.source_id])
            )
        ).scalars()
    }

    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.project_id == project.id)
    ).scalar_one_or_none()

    payload = {
        "format": "draken-export",
        "format_version": FORMAT_VERSION,
        "draken_version": __version__,
        "exported_at": datetime.now(UTC).isoformat(),
        "project": _serialise(project),
        "business_profile": _serialise(profile) if profile else None,
        "keywords": [_serialise(k) for k in keywords],
        "keyword_clusters": [_serialise(c) for c in clusters],
        "rank_snapshots": [_serialise(s) for s in snapshots],
        "backlinks": [
            _serialise(b)
            for b in db.execute(
                select(Backlink).where(Backlink.project_id == project.id)
            ).scalars()
        ],
        "competitor_backlinks": [
            _serialise(c)
            for c in db.execute(
                select(CompetitorBacklink).where(CompetitorBacklink.project_id == project.id)
            ).scalars()
        ],
        "campaigns": [
            _serialise(c)
            for c in db.execute(
                select(Campaign).where(Campaign.project_id == project.id)
            ).scalars()
        ],
        "opportunities": [
            {**_serialise(o), "_source_slug": source_slugs.get(o.source_id)}
            for o in opportunities
        ],
        "submissions": [_serialise(s) for s in submissions],
        "outreach_templates": [
            _serialise(t)
            for t in db.execute(
                select(OutreachTemplate).where(OutreachTemplate.project_id == project.id)
            ).scalars()
        ],
        "outreach_messages": [
            _serialise(m)
            for m in db.execute(
                select(OutreachMessage).where(OutreachMessage.project_id == project.id)
            ).scalars()
        ],
        "ai_prompts": [_serialise(p) for p in prompts],
        "ai_visibility_runs": [
            _serialise(r)
            for r in db.execute(
                select(AIVisibilityRun).where(AIVisibilityRun.project_id == project.id)
            ).scalars()
        ],
    }
    payload["counts"] = {
        key: len(value)
        for key, value in payload.items()
        if isinstance(value, list)
    }
    log.info("exported project %s: %s", project.domain, payload["counts"])
    return payload


def export_all(db: Session) -> dict:
    projects = list(db.execute(select(Project)).scalars())
    return {
        "format": "draken-export-all",
        "format_version": FORMAT_VERSION,
        "draken_version": __version__,
        "exported_at": datetime.now(UTC).isoformat(),
        "projects": [export_project(db, project=p) for p in projects],
    }


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

# (payload key, model, the column that points back at the project)
_CHILD_TABLES: list[tuple[str, Any, str]] = [
    ("backlinks", Backlink, "project_id"),
    ("competitor_backlinks", CompetitorBacklink, "project_id"),
    ("campaigns", Campaign, "project_id"),
    ("outreach_templates", OutreachTemplate, "project_id"),
    ("ai_prompts", AIPrompt, "project_id"),
]


def import_project(db: Session, payload: dict, *, overwrite: bool = False) -> dict:
    """Restore a project from an export. Ids are reassigned, not reused."""
    if payload.get("format") != "draken-export":
        raise ValueError("This file is not a Draken project export.")
    if int(payload.get("format_version", 0)) > FORMAT_VERSION:
        raise ValueError(
            f"The file uses format version {payload['format_version']}, but this Draken "
            f"understands up to {FORMAT_VERSION}. Update Draken first."
        )

    project_data = dict(payload["project"])
    domain = project_data.get("domain")
    if not domain:
        raise ValueError("The export has no project domain.")

    existing = db.execute(select(Project).where(Project.domain == domain)).scalars().first()
    if existing is not None and not overwrite:
        raise ValueError(
            f"A project for {domain} already exists. Re-run with overwrite to replace it."
        )
    if existing is not None:
        db.delete(existing)
        db.flush()

    project = Project()
    _assign(project, project_data, skip={"id"})
    db.add(project)
    db.flush()
    report = {"project": project.domain, "project_id": project.id}

    if payload.get("business_profile"):
        profile = BusinessProfile(project_id=project.id)
        _assign(profile, payload["business_profile"], skip={"id", "project_id"})
        db.add(profile)

    # Clusters before keywords, so keyword.cluster_id can be remapped.
    cluster_map: dict[int, int] = {}
    for row in payload.get("keyword_clusters", []):
        cluster = KeywordCluster(project_id=project.id)
        _assign(cluster, row, skip={"id", "project_id"})
        db.add(cluster)
        db.flush()
        cluster_map[row["id"]] = cluster.id
    report["keyword_clusters"] = len(cluster_map)

    keyword_map: dict[int, int] = {}
    for row in payload.get("keywords", []):
        keyword = Keyword(project_id=project.id)
        _assign(keyword, row, skip={"id", "project_id", "cluster_id"})
        old_cluster = row.get("cluster_id")
        keyword.cluster_id = cluster_map.get(old_cluster) if old_cluster else None
        db.add(keyword)
        db.flush()
        keyword_map[row["id"]] = keyword.id
    report["keywords"] = len(keyword_map)

    snapshots = 0
    for row in payload.get("rank_snapshots", []):
        new_keyword_id = keyword_map.get(row.get("keyword_id"))
        if new_keyword_id is None:
            continue
        snapshot = RankSnapshot(keyword_id=new_keyword_id)
        _assign(snapshot, row, skip={"id", "keyword_id"})
        db.add(snapshot)
        snapshots += 1
    report["rank_snapshots"] = snapshots

    for key, model, fk in _CHILD_TABLES:
        count = 0
        for row in payload.get(key, []):
            instance = model(**{fk: project.id})
            _assign(instance, row, skip={"id", fk})
            db.add(instance)
            count += 1
        report[key] = count
    db.flush()

    # Campaigns keep their own ids inside opportunities; remap by name.
    campaign_map = {
        c.name: c.id
        for c in db.execute(select(Campaign).where(Campaign.project_id == project.id)).scalars()
    }
    campaign_names = {row["id"]: row.get("name") for row in payload.get("campaigns", [])}

    # Catalog ids differ per install; resolve the carried slug instead. The
    # catalog ships with the code, so load it if this install has never done so -
    # otherwise every restored opportunity would lose its source.
    if not db.execute(select(LinkSource.id).limit(1)).first():
        from draken.services.opportunities import sync_catalog

        log.info("link source catalog is empty; loading it before import")
        sync_catalog(db)

    slugs = {row.get("_source_slug") for row in payload.get("opportunities", [])}
    source_map = {
        s.slug: s.id
        for s in db.execute(
            select(LinkSource).where(LinkSource.slug.in_([s for s in slugs if s]))
        ).scalars()
    }

    opportunity_map: dict[int, int] = {}
    for row in payload.get("opportunities", []):
        opportunity = LinkOpportunity(project_id=project.id)
        _assign(opportunity, row, skip={"id", "project_id", "source_id", "campaign_id",
                                        "_source_slug"})
        opportunity.source_id = source_map.get(row.get("_source_slug"))
        old_campaign = row.get("campaign_id")
        opportunity.campaign_id = campaign_map.get(campaign_names.get(old_campaign)) \
            if old_campaign else None
        db.add(opportunity)
        db.flush()
        opportunity_map[row["id"]] = opportunity.id
    report["opportunities"] = len(opportunity_map)

    submissions = 0
    for row in payload.get("submissions", []):
        new_opportunity = opportunity_map.get(row.get("opportunity_id"))
        if new_opportunity is None:
            continue
        submission = Submission(project_id=project.id, opportunity_id=new_opportunity)
        _assign(submission, row, skip={"id", "project_id", "opportunity_id"})
        db.add(submission)
        submissions += 1
    report["submissions"] = submissions

    prompt_map: dict[int, int] = {}
    for prompt in db.execute(
        select(AIPrompt).where(AIPrompt.project_id == project.id)
    ).scalars():
        for row in payload.get("ai_prompts", []):
            if row.get("prompt") == prompt.prompt:
                prompt_map[row["id"]] = prompt.id
                break

    runs = 0
    for row in payload.get("ai_visibility_runs", []):
        new_prompt = prompt_map.get(row.get("prompt_id"))
        if new_prompt is None:
            continue
        run = AIVisibilityRun(project_id=project.id, prompt_id=new_prompt)
        _assign(run, row, skip={"id", "project_id", "prompt_id"})
        db.add(run)
        runs += 1
    report["ai_visibility_runs"] = runs

    messages = 0
    for row in payload.get("outreach_messages", []):
        message = OutreachMessage(project_id=project.id)
        _assign(message, row, skip={"id", "project_id", "opportunity_id", "template_id"})
        message.opportunity_id = opportunity_map.get(row.get("opportunity_id"))
        db.add(message)
        messages += 1
    report["outreach_messages"] = messages

    db.commit()
    log.info("imported project %s: %s", project.domain, report)
    return report


def import_all(db: Session, payload: dict, *, overwrite: bool = False) -> list[dict]:
    if payload.get("format") == "draken-export":
        return [import_project(db, payload, overwrite=overwrite)]
    if payload.get("format") != "draken-export-all":
        raise ValueError("This file is not a Draken export.")
    return [
        import_project(db, project_payload, overwrite=overwrite)
        for project_payload in payload.get("projects", [])
    ]


def _assign(instance, row: dict, *, skip: set[str]) -> None:
    """Copy known columns, parsing dates and ignoring unknown ones.

    Unknown keys are skipped rather than raising, so an export from an older
    version still imports into a newer schema.
    """
    columns = {c.name: c for c in instance.__table__.columns}
    for key, value in row.items():
        if key in skip or key.startswith("_") or key not in columns:
            continue
        setattr(instance, key, _parse(value, columns[key]))


def to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)
