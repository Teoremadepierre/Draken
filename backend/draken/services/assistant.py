"""The in-app AI assistant: explain a finding, and say exactly what to change.

Two ways to use it, because not everyone will have an API key in the tool:

1. **Connected.** With an AI key configured, ``ask()`` sends the finding plus the
   project context to the model and returns the answer in the panel.
2. **Portable.** ``build_brief()`` produces a complete, self-contained prompt you
   can paste into Claude, ChatGPT or anything else. It carries the facts the
   assistant needs, so the answer does not depend on it guessing your setup.

The portable path matters for sharing: a colleague opening a shared report gets
a brief they can take to their own assistant without needing access to yours.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.core.config import settings
from draken.core.logging import get_logger
from draken.core.models import AuditIssue, BusinessProfile, Project, SiteAudit
from draken.engines.geo import engines as ai_engines

log = get_logger(__name__)

SYSTEM_PROMPT = """You are an SEO engineer reviewing a specific finding from an \
automated site audit. You are talking to the person who owns the site.

Rules:
- Be specific to the data given. Never invent URLs, numbers or page content.
- Give the actual change to make: the tag, the snippet, the setting, the file.
- If the fix depends on the stack (WordPress, Next.js, Shopify, custom), say what \
you would need to know and give the two most likely variants.
- State the real impact honestly. If a finding is cosmetic, say so rather than \
inflating it.
- Never recommend buying links, private blog networks, cloaking, or anything that \
violates search engine guidelines.
- Answer in the same language the question is written in.
- Keep it under 400 words unless the fix genuinely needs more."""


def available() -> bool:
    return any(settings.ai_engines_configured().values())


def preferred_engine() -> str:
    for name in ("anthropic", "openai", "gemini", "perplexity"):
        if settings.ai_engines_configured().get(name):
            return name
    return ""


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------


def project_context(db: Session, *, project: Project) -> dict:
    """The facts an assistant needs to give a non-generic answer."""
    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.project_id == project.id)
    ).scalar_one_or_none()
    audit = db.execute(
        select(SiteAudit)
        .where(SiteAudit.project_id == project.id)
        .order_by(SiteAudit.id.desc())
    ).scalars().first()

    context = {
        "site": project.base_url or f"https://{project.domain}",
        "domain": project.domain,
        "business": project.name,
        "industry": project.industry or "unknown",
        "country": project.country,
        "language": project.language,
        "competitors": list(project.competitors or []),
    }
    if profile:
        context["what_they_do"] = profile.short_description or profile.long_description or ""
    if audit:
        context["site_health_score"] = audit.health_score
        context["pages_crawled"] = audit.pages_crawled
        summary = audit.summary or {}
        context["tech_signals"] = {
            "avg_words_per_page": summary.get("avg_word_count"),
            "pages_with_structured_data": summary.get("pages_with_schema"),
            "html_pages": summary.get("html_pages"),
            "avg_response_ms": summary.get("avg_response_ms"),
            "has_robots_txt": summary.get("robots_txt"),
            "sitemap_urls": summary.get("sitemap_urls"),
        }
    return context


def finding_context(db: Session, *, project: Project, finding_id: str) -> dict:
    """Resolve a report finding id back to its underlying data."""
    if not finding_id.startswith("audit:"):
        return {"finding_id": finding_id}

    code = finding_id.split(":", 1)[1]
    audit = db.execute(
        select(SiteAudit)
        .where(SiteAudit.project_id == project.id)
        .order_by(SiteAudit.id.desc())
    ).scalars().first()
    if audit is None:
        return {"finding_id": finding_id}

    rows = list(
        db.execute(
            select(AuditIssue)
            .where(AuditIssue.audit_id == audit.id, AuditIssue.code == code)
            .limit(30)
        ).scalars()
    )
    if not rows:
        return {"finding_id": finding_id}

    first = rows[0]
    return {
        "finding_id": finding_id,
        "code": first.code,
        "severity": first.severity,
        "title": first.title,
        "description": first.description,
        "standard_fix": first.how_to_fix,
        "affected_pages": len(rows),
        "examples": [
            {"url": r.url, "detail": r.detail} for r in rows[:8] if r.url
        ],
    }


# ---------------------------------------------------------------------------
# portable brief
# ---------------------------------------------------------------------------


def build_brief(
    *,
    context: dict,
    finding: dict | None = None,
    question: str = "",
    language: str = "es",
) -> str:
    """A self-contained prompt for any assistant, including ones we cannot call."""
    es = language.startswith("es")
    lines: list[str] = []

    lines.append(
        "Actúa como ingeniero SEO. Analiza el siguiente hallazgo real de una auditoría "
        "automatizada y dime exactamente qué cambiar."
        if es else
        "Act as an SEO engineer. Analyse the following real finding from an automated audit "
        "and tell me exactly what to change."
    )
    lines.append("")
    lines.append("## " + ("Contexto del sitio" if es else "Site context"))
    lines.append("```json")
    lines.append(json.dumps(context, indent=2, ensure_ascii=False))
    lines.append("```")

    if finding:
        lines.append("")
        lines.append("## " + ("Hallazgo" if es else "Finding"))
        lines.append("```json")
        lines.append(json.dumps(finding, indent=2, ensure_ascii=False, default=str))
        lines.append("```")

    lines.append("")
    lines.append("## " + ("Lo que necesito" if es else "What I need"))
    if question:
        lines.append(question)
    elif finding:
        lines.append(
            "1. Qué significa esto en la práctica y cuánto importa de verdad.\n"
            "2. El cambio concreto: la etiqueta, el fragmento de código o el ajuste.\n"
            "3. Cómo compruebo que ha quedado arreglado.\n"
            "4. Si el arreglo depende del stack, dime las dos variantes más probables."
            if es else
            "1. What this means in practice and how much it actually matters.\n"
            "2. The concrete change: the tag, the code snippet or the setting.\n"
            "3. How I verify it is fixed.\n"
            "4. If the fix depends on the stack, give the two most likely variants."
        )
    else:
        lines.append(
            "Dame un plan priorizado para las próximas dos semanas."
            if es else
            "Give me a prioritised plan for the next two weeks."
        )

    lines.append("")
    lines.append(
        "No inventes URLs ni datos que no estén arriba. No recomiendes comprar enlaces "
        "ni ninguna técnica contraria a las directrices de los buscadores."
        if es else
        "Do not invent URLs or data that is not above. Do not recommend buying links or any "
        "technique that violates search engine guidelines."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# connected path
# ---------------------------------------------------------------------------


async def ask(
    db: Session,
    *,
    project: Project,
    question: str = "",
    finding_id: str = "",
    language: str = "es",
    engine: str = "",
) -> dict:
    """Send the finding to the configured model and return its answer."""
    context = project_context(db, project=project)
    finding = finding_context(db, project=project, finding_id=finding_id) if finding_id else None
    brief = build_brief(context=context, finding=finding, question=question, language=language)

    if not available():
        return {
            "answered": False,
            "brief": brief,
            "engine": "",
            "answer": "",
            "reason": (
                "No hay ninguna API de IA configurada. Copia el informe de abajo y pégalo en "
                "Claude, ChatGPT o el asistente que uses: lleva todo el contexto necesario."
                if language.startswith("es") else
                "No AI API is configured. Copy the brief below into Claude, ChatGPT or whichever "
                "assistant you use: it carries all the context needed."
            ),
        }

    name = engine or preferred_engine()
    answers = await ai_engines.ask_all(brief, engines=[name])
    answer = answers[0] if answers else None

    if answer is None or not answer.ok:
        return {
            "answered": False,
            "brief": brief,
            "engine": name,
            "answer": "",
            "reason": (answer.error if answer else "no response from the engine"),
        }

    return {
        "answered": True,
        "engine": answer.engine,
        "model": answer.model,
        "answer": answer.answer,
        "brief": brief,
    }


async def plan(db: Session, *, project: Project, language: str = "es") -> dict:
    """Ask the model for a two-week plan from the whole report."""
    from draken.services.scanner import build_report

    report = build_report(db, project=project)
    compact = {
        "scores": report["scores"],
        "headline": report["headline"],
        "top_fixes": [
            {k: f[k] for k in ("priority", "severity", "title", "affected", "category")}
            for f in report["fixes"][:15]
        ],
        "backlinks_available_now": report["backlinks"]["summary"],
        "link_profile": {
            k: report["link_profile"][k]
            for k in ("referring_domains", "authority_score", "dofollow_links", "toxic_links")
        },
        "ai_visibility": {
            k: report["ai_visibility"][k] for k in ("mention_rate", "citation_rate", "runs")
        },
    }
    question = (
        "Dame un plan de dos semanas, día a día, con las acciones concretas en orden de "
        "impacto. Sé realista con el tiempo que lleva cada cosa."
        if language.startswith("es") else
        "Give me a two-week, day-by-day plan with concrete actions in order of impact. "
        "Be realistic about how long each one takes."
    )
    context = {**project_context(db, project=project), "report": compact}
    brief = build_brief(context=context, question=question, language=language)

    if not available():
        return {"answered": False, "brief": brief, "engine": "", "answer": "",
                "reason": "no AI engine configured"}

    answers = await ai_engines.ask_all(brief, engines=[preferred_engine()])
    answer = answers[0] if answers else None
    if answer is None or not answer.ok:
        return {"answered": False, "brief": brief, "engine": preferred_engine(),
                "answer": "", "reason": answer.error if answer else "no response"}
    return {"answered": True, "engine": answer.engine, "model": answer.model,
            "answer": answer.answer, "brief": brief}
