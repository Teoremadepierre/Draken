"""Outreach templates, drafting, contact discovery and sending."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.api.deps import current_user, get_project
from draken.core.config import settings
from draken.core.database import get_db
from draken.core.models import (
    BusinessProfile,
    LinkOpportunity,
    OutreachMessage,
    OutreachTemplate,
    Project,
    utcnow,
)
from draken.core.schemas import (
    DraftOutreachRequest,
    OutreachMessageOut,
    OutreachTemplateIn,
    OutreachTemplateOut,
)
from draken.engines.outreach import engine as outreach

router = APIRouter(tags=["outreach"])

templates_router = APIRouter(prefix="/api/outreach", tags=["outreach"])
project_router = APIRouter(prefix="/api/projects/{project_id}/outreach", tags=["outreach"])


@templates_router.get("/templates")
def list_builtin_templates(
    tactic: str = "", language: str = "", _user: str = Depends(current_user)
):
    """The built-in template library from data/seeds/outreach_templates.json."""
    rows = outreach.builtin_templates(tactic or None, language or None)
    return {
        "templates": [
            {**t, "variables": outreach.template_variables(t.get("subject", "") + " " + t.get("body", ""))}
            for t in rows
        ],
        "tactics": sorted({t.get("tactic", "generic") for t in outreach.builtin_templates()}),
    }


@templates_router.get("/settings")
def outreach_settings(_user: str = Depends(current_user)):
    return {
        "send_enabled": settings.outreach_send_enabled,
        "smtp_configured": outreach.smtp_configured(),
        "from_address": settings.smtp_from,
        "note": (
            "Sending is opt-in. Draft, review and personalise first - a generic mail-merge gets "
            "filtered and burns the domain you send from."
        ),
    }


@project_router.get("/templates", response_model=list[OutreachTemplateOut])
def list_templates(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return list(
        db.execute(
            select(OutreachTemplate).where(
                (OutreachTemplate.project_id == project.id) | (OutreachTemplate.project_id.is_(None))
            ).order_by(OutreachTemplate.step_number, OutreachTemplate.id)
        ).scalars()
    )


@project_router.post("/templates", response_model=OutreachTemplateOut, status_code=201)
def create_template(
    payload: OutreachTemplateIn,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    template = OutreachTemplate(
        project_id=project.id,
        name=payload.name,
        tactic=payload.tactic,
        subject=payload.subject,
        body=payload.body,
        step_number=payload.step_number,
        delay_days=payload.delay_days,
        language=payload.language,
        variables=outreach.template_variables(payload.subject + " " + payload.body),
    )
    db.add(template)
    db.commit()
    return template


@project_router.post("/find-contacts")
async def find_contacts(
    opportunity_ids: list[int],
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Look for a contact email or contact form for each opportunity."""
    opps = list(
        db.execute(
            select(LinkOpportunity).where(
                LinkOpportunity.project_id == project.id,
                LinkOpportunity.id.in_(opportunity_ids),
            )
        ).scalars()
    )
    if not opps:
        return {"found": 0, "results": []}

    urls = [o.target_url or f"https://{o.target_domain}" for o in opps]
    contacts = await outreach.find_contacts(urls)

    results = []
    for opp, url in zip(opps, urls, strict=False):
        contact = contacts.get(url)
        if contact and contact.email:
            opp.contact_email = contact.email
            opp.contact_form_url = contact.form_url or opp.contact_form_url
        elif contact and contact.form_url:
            opp.contact_form_url = contact.form_url
        results.append(
            {
                "opportunity_id": opp.id,
                "domain": opp.target_domain,
                **(contact.as_dict() if contact else {}),
            }
        )
    db.commit()
    return {
        "found": sum(1 for r in results if r.get("email")),
        "checked": len(results),
        "results": results,
    }


@project_router.post("/draft")
def draft(
    payload: DraftOutreachRequest,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    """Draft personalised messages. Nothing is sent - review them first."""
    opps = list(
        db.execute(
            select(LinkOpportunity).where(
                LinkOpportunity.project_id == project.id,
                LinkOpportunity.id.in_(payload.opportunity_ids),
            )
        ).scalars()
    )
    if not opps:
        raise HTTPException(status_code=404, detail="No matching opportunities in this project")

    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.project_id == project.id)
    ).scalar_one_or_none()
    profile_data = (
        {
            c.name: getattr(profile, c.name)
            for c in BusinessProfile.__table__.columns
            if c.name not in {"id", "project_id", "created_at", "updated_at"}
        }
        if profile
        else {}
    )
    project_data = {
        "name": project.name, "domain": project.domain,
        "base_url": project.base_url, "industry": project.industry,
    }

    drafted: list[dict] = []
    for opp in opps:
        if payload.template_id:
            template_row = db.get(OutreachTemplate, payload.template_id)
            if template_row is None:
                raise HTTPException(status_code=404, detail="Template not found")
            template = {
                "name": template_row.name, "subject": template_row.subject,
                "body": template_row.body, "step_number": template_row.step_number,
                "delay_days": template_row.delay_days,
            }
        else:
            tactic = _tactic_to_template(opp.tactic, payload.tactic)
            candidates = outreach.builtin_templates(tactic, project.language)
            first_step = [t for t in candidates if t.get("step_number", 1) == 1]
            if not first_step:
                raise HTTPException(
                    status_code=422,
                    detail=f"No template available for tactic {tactic!r}. Create one first.",
                )
            template = first_step[0]

        context = outreach.build_context(
            project=project_data,
            opportunity={
                "target_domain": opp.target_domain,
                "target_url": opp.target_url,
                "landing_url": opp.landing_url,
                "contact_name": opp.contact_name,
                "meta_json": opp.meta_json,
            },
            profile=profile_data,
            sender_name=payload.sender_name,
            sender_role=payload.sender_role,
        )
        message = outreach.draft_message(template=template, context=context)

        row = OutreachMessage(
            project_id=project.id,
            opportunity_id=opp.id,
            template_id=payload.template_id,
            to_email=opp.contact_email,
            to_name=opp.contact_name,
            subject=message["subject"][:400],
            body=message["body"],
            state="draft",
            step_number=message["step_number"],
            scheduled_for=outreach.schedule_for(message["step_number"], message["delay_days"]),
        )
        db.add(row)
        db.flush()
        drafted.append(
            {
                "message_id": row.id,
                "opportunity_id": opp.id,
                "domain": opp.target_domain,
                "to_email": row.to_email,
                **message,
            }
        )
    db.commit()
    return {
        "drafted": len(drafted),
        "messages": drafted,
        "needs_personalisation": [
            d for d in drafted if d["unresolved_variables"]
        ],
        "note": (
            "Fill in the [[placeholders]] before sending. The specific detail in those fields is the "
            "entire difference between an email that works and one that does not."
        ),
    }


def _tactic_to_template(opportunity_tactic: str, fallback: str) -> str:
    mapping = {
        "unlinked_mention": "unlinked_mention",
        "resource_page": "resource_page",
        "guest_post": "guest_post",
        "podcast": "podcast",
        "press_release": "digital_pr",
        "review_platform": "partner_link",
        "product_listing": "partner_link",
    }
    return mapping.get(opportunity_tactic, fallback if fallback != "generic" else "resource_page")


@project_router.get("/messages", response_model=list[OutreachMessageOut])
def list_messages(
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
    state: str = "",
    limit: int = Query(200, ge=1, le=2000),
):
    query = select(OutreachMessage).where(OutreachMessage.project_id == project.id)
    if state:
        query = query.where(OutreachMessage.state == state)
    return list(db.execute(query.order_by(OutreachMessage.id.desc()).limit(limit)).scalars())


@project_router.patch("/messages/{message_id}", response_model=OutreachMessageOut)
def update_message(
    message_id: int,
    subject: str | None = None,
    body: str | None = None,
    to_email: str | None = None,
    state: str | None = None,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    row = db.get(OutreachMessage, message_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Message not found in this project")
    if subject is not None:
        row.subject = subject
    if body is not None:
        row.body = body
    if to_email is not None:
        row.to_email = to_email
    if state is not None:
        row.state = state
    db.commit()
    return row


@project_router.post("/messages/{message_id}/send")
def send_message(
    message_id: int,
    project: Project = Depends(get_project),
    db: Session = Depends(get_db),
):
    row = db.get(OutreachMessage, message_id)
    if row is None or row.project_id != project.id:
        raise HTTPException(status_code=404, detail="Message not found in this project")

    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.project_id == project.id)
    ).scalar_one_or_none()
    ok, detail = outreach.send_email(
        to_email=row.to_email,
        subject=row.subject,
        body=row.body,
        reply_to=(profile.email if profile else ""),
    )
    if ok:
        row.state = "sent"
        row.sent_at = utcnow()
        row.error = ""
    else:
        row.error = detail
    db.commit()
    return {"sent": ok, "detail": detail, "message_id": row.id, "state": row.state}


router.include_router(templates_router)
router.include_router(project_router)
