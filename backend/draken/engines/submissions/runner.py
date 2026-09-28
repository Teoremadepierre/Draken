"""The submission runner: prepare, gate, execute and verify link submissions.

Safety rails, all enforced here rather than in the UI:

  * ``DRAKEN_SUBMISSIONS_DRY_RUN``            nothing is POSTed until you turn it off
  * ``DRAKEN_SUBMISSIONS_REQUIRE_APPROVAL``   a human approves each submission
  * per-domain daily cap                      never hammer one host
  * global daily cap                          bounds the whole system's footprint
  * every action is written to ActivityLog     so there is an audit trail

The runner is the only place in Draken that writes to third-party sites, and it
refuses to run if the business profile is incomplete: submitting placeholder data
under your own brand is worse than not submitting at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from draken.core.config import settings
from draken.core.logging import get_logger
from draken.core.models import (
    ActivityLog,
    Backlink,
    BusinessProfile,
    LinkOpportunity,
    LinkSource,
    LinkStatus,
    OpportunityStatus,
    Project,
    Submission,
    SubmissionState,
    utcnow,
)
from draken.core.urls import normalize_domain, normalize_url
from draken.engines.backlinks import discovery, toxicity
from draken.engines.submissions import adapters

log = get_logger(__name__)


@dataclass
class RunReport:
    prepared: int = 0
    executed: int = 0
    submitted: int = 0
    failed: int = 0
    skipped: int = 0
    verified: int = 0
    dry_run: bool = True
    messages: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.messages is None:
            self.messages = []

    def as_dict(self) -> dict:
        return {
            "prepared": self.prepared,
            "executed": self.executed,
            "submitted": self.submitted,
            "failed": self.failed,
            "skipped": self.skipped,
            "verified": self.verified,
            "dry_run": self.dry_run,
            "messages": self.messages,
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _log(db: Session, *, project_id: int | None, action: str, entity_id: int | None, detail: dict) -> None:
    db.add(
        ActivityLog(
            project_id=project_id,
            actor="submission_runner",
            action=action,
            entity_type="submission",
            entity_id=entity_id,
            detail=detail,
        )
    )


def profile_to_dict(profile: BusinessProfile | None) -> dict:
    if profile is None:
        return {}
    return {
        c.name: getattr(profile, c.name)
        for c in BusinessProfile.__table__.columns
        if c.name not in {"id", "project_id", "created_at", "updated_at"}
    }


def profile_completeness(profile: BusinessProfile | None) -> tuple[float, list[str]]:
    """Fraction of the important NAP/brand fields that are filled in."""
    important = [
        "display_name", "short_description", "long_description", "website", "email",
        "phone", "city", "country", "categories", "logo_url",
    ]
    if profile is None:
        return 0.0, important
    data = profile_to_dict(profile)
    missing = [k for k in important if not data.get(k)]
    return round((len(important) - len(missing)) / len(important), 2), missing


def _daily_counts(db: Session) -> tuple[int, dict[str, int]]:
    since = datetime.now(UTC) - timedelta(days=1)
    rows = db.execute(
        select(LinkOpportunity.target_domain, func.count(Submission.id))
        .join(LinkOpportunity, Submission.opportunity_id == LinkOpportunity.id)
        .where(
            Submission.executed_at.is_not(None),
            Submission.executed_at >= since,
            Submission.dry_run.is_(False),
        )
        .group_by(LinkOpportunity.target_domain)
    ).all()
    per_domain = {row[0]: int(row[1]) for row in rows}
    return sum(per_domain.values()), per_domain


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------


def prepare(
    db: Session,
    *,
    project_id: int,
    opportunity_ids: list[int] | None = None,
    limit: int = 25,
    auto_approve: bool = False,
) -> tuple[list[Submission], RunReport]:
    """Build submission drafts (payload + human brief) for opportunities."""
    report = RunReport(dry_run=settings.submissions_dry_run)
    project = db.get(Project, project_id)
    if project is None:
        report.messages.append(f"project {project_id} not found")
        return [], report

    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.project_id == project_id)
    ).scalar_one_or_none()
    completeness, missing = profile_completeness(profile)
    if completeness < 0.5:
        report.messages.append(
            "Business profile is only "
            f"{completeness:.0%} complete (missing: {', '.join(missing)}). "
            "Fill it in before preparing submissions - placeholder data under your own brand is worse "
            "than no listing."
        )
        return [], report

    profile_data = profile_to_dict(profile)

    query = select(LinkOpportunity).where(LinkOpportunity.project_id == project_id)
    if opportunity_ids:
        query = query.where(LinkOpportunity.id.in_(opportunity_ids))
    else:
        query = query.where(
            LinkOpportunity.status.in_(
                [OpportunityStatus.new.value, OpportunityStatus.qualified.value, OpportunityStatus.queued.value]
            )
        ).order_by(LinkOpportunity.score.desc())
    opportunities = list(db.execute(query.limit(limit)).scalars())

    created: list[Submission] = []
    for opp in opportunities:
        source = db.get(LinkSource, opp.source_id) if opp.source_id else None
        source_data = (
            {
                c.name: getattr(source, c.name)
                for c in LinkSource.__table__.columns
                if c.name not in {"created_at", "updated_at", "last_verified_at"}
            }
            if source
            else {
                "name": opp.target_domain,
                "domain": opp.target_domain,
                "submit_url": opp.target_url,
                "category": opp.tactic,
                "authority": opp.authority,
                "effort": opp.effort,
                "link_type": (opp.meta_json or {}).get("link_type", "unknown"),
                "required_fields": (opp.meta_json or {}).get("required_fields")
                or ["display_name", "website", "short_description"],
                "requires_account": (opp.meta_json or {}).get("requires_account", True),
                "automatable": (opp.meta_json or {}).get("automatable", False),
                "notes": opp.notes,
                "guidelines_url": (opp.meta_json or {}).get("guidelines_url", ""),
                "slug": "",
            }
        )

        existing = db.execute(
            select(Submission).where(
                Submission.opportunity_id == opp.id,
                Submission.state.notin_([SubmissionState.failed.value, SubmissionState.rejected.value]),
            )
        ).scalars().first()
        if existing:
            report.skipped += 1
            continue

        landing = opp.landing_url or project.base_url or f"https://{project.domain}"
        payload = adapters.build_payload(
            source=source_data,
            profile=profile_data,
            landing_url=landing,
            suggested_anchor=opp.suggested_anchor,
        )
        instructions = adapters.render_instructions(
            source=source_data,
            payload=payload,
            landing_url=landing,
            suggested_anchor=opp.suggested_anchor,
        )

        state = SubmissionState.draft.value
        if settings.submissions_require_approval and not auto_approve:
            state = SubmissionState.awaiting_approval.value
        elif auto_approve:
            state = SubmissionState.approved.value

        submission = Submission(
            opportunity_id=opp.id,
            project_id=project_id,
            state=state,
            method=payload.method,
            payload=payload.as_dict(),
            rendered_instructions=instructions,
            dry_run=settings.submissions_dry_run,
            approved_at=utcnow() if state == SubmissionState.approved.value else None,
            approved_by="auto" if state == SubmissionState.approved.value else "",
        )
        db.add(submission)
        opp.status = OpportunityStatus.queued.value
        created.append(submission)
        report.prepared += 1

    db.flush()
    for s in created:
        _log(
            db,
            project_id=project_id,
            action="submission.prepared",
            entity_id=s.id,
            detail={"opportunity_id": s.opportunity_id, "method": s.method, "state": s.state},
        )
    db.commit()
    if report.prepared:
        report.messages.append(
            f"Prepared {report.prepared} submission(s). "
            + (
                "Each one needs approval before it can run."
                if settings.submissions_require_approval and not auto_approve
                else "Ready to run."
            )
        )
    if report.skipped:
        report.messages.append(f"Skipped {report.skipped} opportunity/ies that already have a submission.")
    return created, report


def approve(db: Session, *, submission_ids: list[int], approved_by: str = "operator") -> RunReport:
    report = RunReport(dry_run=settings.submissions_dry_run)
    submissions = list(
        db.execute(select(Submission).where(Submission.id.in_(submission_ids))).scalars()
    )
    for s in submissions:
        if s.state not in {SubmissionState.draft.value, SubmissionState.awaiting_approval.value}:
            report.skipped += 1
            continue
        s.state = SubmissionState.approved.value
        s.approved_by = approved_by
        s.approved_at = utcnow()
        report.prepared += 1
        _log(db, project_id=s.project_id, action="submission.approved", entity_id=s.id,
             detail={"approved_by": approved_by})
    db.commit()
    report.messages.append(f"Approved {report.prepared} submission(s).")
    return report


# ---------------------------------------------------------------------------
# execute
# ---------------------------------------------------------------------------


async def run(
    db: Session,
    *,
    project_id: int,
    submission_ids: list[int] | None = None,
    limit: int = 10,
    dry_run: bool | None = None,
) -> RunReport:
    """Execute approved submissions, honouring every rail."""
    effective_dry_run = settings.submissions_dry_run if dry_run is None else dry_run
    report = RunReport(dry_run=effective_dry_run)

    query = select(Submission).where(
        Submission.project_id == project_id,
        Submission.state == SubmissionState.approved.value,
    )
    if submission_ids:
        query = query.where(Submission.id.in_(submission_ids))
    submissions = list(db.execute(query.order_by(Submission.id).limit(limit)).scalars())
    if not submissions:
        report.messages.append("No approved submissions to run.")
        return report

    global_count, per_domain = _daily_counts(db)

    for s in submissions:
        opp = db.get(LinkOpportunity, s.opportunity_id)
        if opp is None:
            s.state = SubmissionState.failed.value
            s.error = "opportunity no longer exists"
            report.failed += 1
            continue

        domain = opp.target_domain

        if not effective_dry_run:
            if global_count >= settings.submissions_global_daily_cap:
                report.skipped += 1
                report.messages.append(
                    f"Global daily cap ({settings.submissions_global_daily_cap}) reached - "
                    f"stopping. {domain} and the rest stay approved for the next run."
                )
                break
            if per_domain.get(domain, 0) >= settings.submissions_per_domain_daily_cap:
                report.skipped += 1
                report.messages.append(
                    f"Per-domain daily cap reached for {domain}; skipped."
                )
                continue

        payload = adapters.SubmissionPayload(
            fields=(s.payload or {}).get("fields", {}),
            missing=(s.payload or {}).get("missing", []),
            warnings=(s.payload or {}).get("warnings", []),
            method=(s.payload or {}).get("method", s.method),
            target_url=(s.payload or {}).get("target_url", opp.target_url),
        )

        s.attempts += 1
        s.executed_at = utcnow()
        s.dry_run = effective_dry_run
        report.executed += 1

        if payload.method == "manual":
            # Nothing to automate: hand it to the operator with the brief already written.
            s.state = SubmissionState.manual_required.value
            s.response_excerpt = (
                "Manual submission required. Open the target URL and use the prepared brief; "
                "then record the live URL here."
            )
            opp.status = OpportunityStatus.in_progress.value
            report.submitted += 1
            _log(db, project_id=project_id, action="submission.manual_required", entity_id=s.id,
                 detail={"domain": domain})
            continue

        source = db.get(LinkSource, opp.source_id) if opp.source_id else None
        slug = source.slug if source else ""
        try:
            ok, status, excerpt = await adapters.execute_http_form(
                slug=slug, payload=payload, dry_run=effective_dry_run
            )
        except Exception as exc:  # noqa: BLE001
            ok, status, excerpt = False, None, f"{type(exc).__name__}: {exc}"

        s.response_status = status
        s.response_excerpt = (excerpt or "")[:2000]
        if ok:
            s.state = SubmissionState.submitted.value
            opp.status = OpportunityStatus.submitted.value
            report.submitted += 1
            if not effective_dry_run:
                global_count += 1
                per_domain[domain] = per_domain.get(domain, 0) + 1
        else:
            s.state = SubmissionState.failed.value
            s.error = (excerpt or "unknown error")[:2000]
            report.failed += 1

        _log(db, project_id=project_id, action="submission.executed", entity_id=s.id,
             detail={"domain": domain, "ok": ok, "status": status, "dry_run": effective_dry_run})

    db.commit()
    if effective_dry_run:
        report.messages.append(
            "DRY RUN: nothing was actually sent. Set DRAKEN_SUBMISSIONS_DRY_RUN=false to go live."
        )
    return report


def record_live_url(
    db: Session, *, submission_id: int, live_url: str, mark_won: bool = True
) -> Submission | None:
    """Operator pastes the published listing URL; we take it from there."""
    s = db.get(Submission, submission_id)
    if s is None:
        return None
    s.live_url = normalize_url(live_url)
    s.state = SubmissionState.submitted.value
    opp = db.get(LinkOpportunity, s.opportunity_id)
    if opp is not None:
        opp.status = (
            OpportunityStatus.won.value if mark_won else OpportunityStatus.awaiting_review.value
        )
        if mark_won:
            opp.won_at = utcnow()
    _log(db, project_id=s.project_id, action="submission.live_url_recorded", entity_id=s.id,
         detail={"live_url": s.live_url})
    db.commit()
    return s


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------


async def verify(db: Session, *, project_id: int, limit: int = 25) -> RunReport:
    """Check whether submitted links actually went live, and index the ones that did."""
    report = RunReport(dry_run=False)
    project = db.get(Project, project_id)
    if project is None:
        report.messages.append("project not found")
        return report

    submissions = list(
        db.execute(
            select(Submission)
            .where(
                Submission.project_id == project_id,
                Submission.state == SubmissionState.submitted.value,
                Submission.live_url != "",
            )
            .limit(limit)
        ).scalars()
    )
    if not submissions:
        report.messages.append("No submitted links with a recorded URL to verify.")
        return report

    candidates = [(s.live_url, project.domain) for s in submissions]
    links = await discovery.verify_links(candidates)

    by_source = {normalize_url(link.source_url): link for link in links}
    for s in submissions:
        found = by_source.get(normalize_url(s.live_url))
        opp = db.get(LinkOpportunity, s.opportunity_id)
        if found is None:
            continue
        if found.status == LinkStatus.live.value:
            s.state = SubmissionState.verified.value
            s.verified_at = utcnow()
            report.verified += 1
            if opp is not None:
                opp.status = OpportunityStatus.won.value
                opp.won_at = opp.won_at or utcnow()

            tox, reasons = toxicity.score_link(
                source_url=found.source_url,
                source_domain=found.source_domain,
                anchor_text=found.anchor_text,
                link_type=found.link_type,
                domain_authority=found.domain_authority,
                target_domain=project.domain,
            )
            already = db.execute(
                select(Backlink).where(
                    Backlink.project_id == project_id,
                    Backlink.source_url == found.source_url,
                )
            ).scalars().first()
            if already is None:
                db.add(
                    Backlink(
                        project_id=project_id,
                        source_url=found.source_url,
                        source_domain=found.source_domain,
                        target_url=found.target_url,
                        anchor_text=found.anchor_text,
                        link_type=found.link_type,
                        status=LinkStatus.live.value,
                        domain_authority=found.domain_authority,
                        toxicity_score=tox,
                        toxicity_reasons=reasons,
                        source_category=opp.tactic if opp else "",
                        discovered_via="submission",
                        opportunity_id=s.opportunity_id,
                        last_checked=utcnow(),
                    )
                )
            else:
                already.status = LinkStatus.live.value
                already.anchor_text = found.anchor_text or already.anchor_text
                already.link_type = found.link_type
                already.last_checked = utcnow()
        else:
            s.response_excerpt = (
                f"Link not found on {s.live_url} (status: {found.status}). "
                "The listing may still be in moderation, or the link was stripped."
            )
            if opp is not None and opp.status != OpportunityStatus.won.value:
                opp.status = OpportunityStatus.awaiting_review.value

        _log(db, project_id=project_id, action="submission.verified", entity_id=s.id,
             detail={"live_url": s.live_url, "result": found.status})

    db.commit()
    report.messages.append(f"Verified {report.verified} live link(s) out of {len(submissions)} checked.")
    return report


async def recheck_backlinks(db: Session, *, project_id: int, limit: int = 100) -> dict:
    """Re-verify the existing backlink index: catch lost links early."""
    project = db.get(Project, project_id)
    if project is None:
        return {"error": "project not found"}

    links = list(
        db.execute(
            select(Backlink)
            .where(Backlink.project_id == project_id)
            .order_by(Backlink.last_checked.asc().nulls_first())
            .limit(limit)
        ).scalars()
    )
    if not links:
        return {"checked": 0, "still_live": 0, "newly_lost": 0, "recovered": 0}

    results = await discovery.verify_links([(link.source_url, project.domain) for link in links])
    by_url = {normalize_url(r.source_url): r for r in results}

    still_live = newly_lost = recovered = 0
    for link in links:
        res = by_url.get(normalize_url(link.source_url))
        if res is None:
            continue
        link.last_checked = utcnow()
        link.domain_authority = res.domain_authority or link.domain_authority
        if res.status == LinkStatus.live.value:
            if link.status != LinkStatus.live.value:
                recovered += 1
            still_live += 1
            link.status = LinkStatus.live.value
            link.anchor_text = res.anchor_text or link.anchor_text
            link.link_type = res.link_type
            link.lost_at = None
        else:
            if link.status == LinkStatus.live.value:
                newly_lost += 1
                link.lost_at = utcnow()
            link.status = res.status
        tox, reasons = toxicity.score_link(
            source_url=link.source_url,
            source_domain=link.source_domain,
            anchor_text=link.anchor_text,
            link_type=link.link_type,
            domain_authority=link.domain_authority,
            is_sitewide=link.is_sitewide,
            target_domain=project.domain,
        )
        link.toxicity_score = tox
        link.toxicity_reasons = reasons
        link.spam_score = toxicity.spam_score(
            normalize_domain(link.source_domain), domain_authority=link.domain_authority
        )

    db.add(
        ActivityLog(
            project_id=project_id,
            actor="backlink_monitor",
            action="backlinks.rechecked",
            entity_type="project",
            entity_id=project_id,
            detail={"checked": len(links), "still_live": still_live, "newly_lost": newly_lost},
        )
    )
    db.commit()
    return {
        "checked": len(links),
        "still_live": still_live,
        "newly_lost": newly_lost,
        "recovered": recovered,
    }
