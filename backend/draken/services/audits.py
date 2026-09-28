"""Site audit persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.core.logging import get_logger
from draken.core.models import AuditIssue, CrawledPage, JobState, Project, SiteAudit, utcnow
from draken.engines.crawler.crawler import crawl_site

log = get_logger(__name__)


def create_audit(db: Session, *, project: Project) -> SiteAudit:
    audit = SiteAudit(project_id=project.id, state=JobState.pending.value)
    db.add(audit)
    db.commit()
    return audit


async def run_audit(
    db: Session, *, audit_id: int, max_pages: int = 100, max_depth: int = 4
) -> dict:
    audit = db.get(SiteAudit, audit_id)
    if audit is None:
        return {"error": "audit not found"}
    project = db.get(Project, audit.project_id)
    if project is None:
        return {"error": "project not found"}

    audit.state = JobState.running.value
    audit.started_at = utcnow()
    db.commit()

    base = project.base_url or f"https://{project.domain}"
    try:
        result = await crawl_site(base, max_pages=max_pages, max_depth=max_depth)
    except Exception as exc:  # noqa: BLE001
        audit.state = JobState.failed.value
        audit.error = f"{type(exc).__name__}: {exc}"
        audit.finished_at = utcnow()
        db.commit()
        log.error("audit %s failed: %s", audit_id, exc)
        return {"error": audit.error}

    for page in result.pages:
        db.add(
            CrawledPage(
                audit_id=audit.id,
                url=page.get("url", "")[:1000],
                status_code=int(page.get("status_code") or 0),
                content_type=(page.get("content_type") or "")[:120],
                title=(page.get("title") or "")[:600],
                meta_description=(page.get("meta_description") or "")[:2000],
                h1=(page.get("h1") or "")[:600],
                h2_count=int(page.get("h2_count") or 0),
                word_count=int(page.get("word_count") or 0),
                internal_links=int(page.get("internal_links") or 0),
                external_links=int(page.get("external_links") or 0),
                inlinks=int(page.get("inlinks") or 0),
                images_without_alt=int(page.get("images_without_alt") or 0),
                canonical=(page.get("canonical") or "")[:1000],
                robots_meta=(page.get("robots_meta") or "")[:200],
                response_ms=int(page.get("response_ms") or 0),
                size_bytes=int(page.get("size_bytes") or 0),
                depth=int(page.get("depth") or 0),
                has_schema=bool(page.get("has_schema")),
                schema_types=page.get("schema_types") or [],
                hreflang=page.get("hreflang") or [],
                outlinks=(page.get("outlinks") or [])[:120],
                ai_readiness=float(page.get("ai_readiness") or 0.0),
            )
        )

    for issue in result.issues:
        db.add(
            AuditIssue(
                audit_id=audit.id,
                code=issue.code[:80],
                severity=issue.severity,
                title=issue.title[:300],
                description=issue.description,
                how_to_fix=issue.how_to_fix,
                url=(issue.url or "")[:1000],
                detail=issue.detail or {},
                category=issue.category[:40],
            )
        )

    audit.state = JobState.succeeded.value
    audit.finished_at = utcnow()
    audit.pages_crawled = len(result.pages)
    audit.health_score = result.health_score
    audit.issue_counts = result.issue_counts()
    audit.summary = result.summary()
    db.commit()

    return {
        "audit_id": audit.id,
        "pages_crawled": audit.pages_crawled,
        "health_score": audit.health_score,
        "issues": len(result.issues),
        "issue_counts": audit.issue_counts,
        "summary": audit.summary,
    }


def latest_audit(db: Session, *, project_id: int) -> SiteAudit | None:
    return db.execute(
        select(SiteAudit)
        .where(SiteAudit.project_id == project_id)
        .order_by(SiteAudit.id.desc())
    ).scalars().first()


def issues_grouped(db: Session, *, audit_id: int) -> list[dict]:
    """Group issues by code so the UI shows '37 pages missing a title', not 37 rows."""
    issues = list(
        db.execute(select(AuditIssue).where(AuditIssue.audit_id == audit_id)).scalars()
    )
    grouped: dict[str, dict] = {}
    for i in issues:
        row = grouped.setdefault(
            i.code,
            {
                "code": i.code,
                "severity": i.severity,
                "title": i.title,
                "description": i.description,
                "how_to_fix": i.how_to_fix,
                "category": i.category,
                "count": 0,
                "examples": [],
            },
        )
        row["count"] += 1
        if i.url and len(row["examples"]) < 10:
            row["examples"].append({"url": i.url, "detail": i.detail})
    order = {"critical": 0, "error": 1, "warning": 2, "notice": 3}
    return sorted(grouped.values(), key=lambda r: (order.get(r["severity"], 9), -r["count"]))
