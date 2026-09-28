"""Outreach: contact discovery, template rendering, sequencing, sending.

Sending is off by default (``DRAKEN_OUTREACH_SEND_ENABLED=false``) and there is no
bulk blast: messages are drafted per opportunity, personalised from real page
data, and queued with a delay. A generic mail-merge to 500 webmasters gets you
spam-filtered and ignored; twenty specific emails get you links.
"""

from __future__ import annotations

import re
import smtplib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from bs4 import BeautifulSoup

from draken.core.config import settings
from draken.core.http import PoliteClient
from draken.core.logging import get_logger
from draken.core.urls import absolutize, normalize_domain
from draken.data import loader

log = get_logger(__name__)

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Addresses that are never the right person to pitch.
_JUNK_LOCAL_PARTS = {
    "noreply", "no-reply", "donotreply", "postmaster", "abuse", "webmaster@example",
    "privacy", "legal", "dmca", "unsubscribe", "bounce", "mailer-daemon",
}
_PREFERRED_LOCAL_PARTS = [
    "editor", "editorial", "content", "press", "media", "hello", "hi", "team",
    "contact", "info", "marketing", "partnerships", "submissions", "tips",
]


@dataclass
class Contact:
    email: str = ""
    name: str = ""
    form_url: str = ""
    source: str = ""
    confidence: float = 0.0
    all_emails: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def template_variables(text: str) -> list[str]:
    return sorted(set(_VAR_RE.findall(text or "")))


def render(text: str, context: dict) -> tuple[str, list[str]]:
    """Substitute ``{{var}}`` placeholders. Returns ``(rendered, unresolved)``."""
    unresolved: list[str] = []

    def sub(match: re.Match) -> str:
        key = match.group(1)
        value = context.get(key)
        if value in (None, ""):
            unresolved.append(key)
            return f"[[{key}]]"
        return str(value)

    return _VAR_RE.sub(sub, text or ""), sorted(set(unresolved))


def builtin_templates(tactic: str | None = None, language: str | None = None) -> list[dict]:
    templates = loader.outreach_templates()
    out = templates
    if tactic:
        matched = [t for t in out if t.get("tactic") == tactic]
        out = matched or [t for t in out if t.get("tactic") == "generic"] or out
    if language:
        lang_matched = [t for t in out if t.get("language", "en") == language]
        out = lang_matched or out
    return sorted(out, key=lambda t: (t.get("step_number", 1), t.get("name", "")))


# ---------------------------------------------------------------------------
# contact discovery
# ---------------------------------------------------------------------------


def _rank_email(email: str, domain: str) -> float:
    local, _, host = email.lower().partition("@")
    if any(j in local for j in _JUNK_LOCAL_PARTS):
        return 0.0
    score = 0.35
    if normalize_domain(host) == normalize_domain(domain):
        score += 0.3          # on-domain address, not a gmail scraped from a comment
    for i, preferred in enumerate(_PREFERRED_LOCAL_PARTS):
        if local == preferred or local.startswith(preferred):
            score += max(0.1, 0.32 - i * 0.015)
            break
    if "." in local and len(local) > 4:
        score += 0.12         # firstname.lastname looks like a real person
    return round(min(1.0, score), 3)


async def find_contact(page_url: str, *, client: PoliteClient | None = None) -> Contact:
    """Look for a contact email or contact form on a page and its contact page."""
    domain = normalize_domain(page_url)
    contact = Contact(source=page_url)

    async def scan(c: PoliteClient, url: str) -> tuple[list[str], str]:
        res = await c.fetch(url, retries=1)
        if not res.ok:
            return [], ""
        emails = [e for e in _EMAIL_RE.findall(res.text) if len(e) < 120]
        soup = BeautifulSoup(res.text, "lxml")
        form_url = ""
        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").lower()
            text = a.get_text(" ", strip=True).lower()
            if any(k in href or k in text for k in ("contact", "contacto", "kontakt", "about", "write-for-us", "submit")):
                form_url = absolutize(url, a["href"])
                break
        for a in soup.select('a[href^="mailto:"]'):
            mail = (a.get("href") or "")[7:].split("?")[0]
            if mail:
                emails.insert(0, mail)
        return emails, form_url

    async def run(c: PoliteClient) -> None:
        emails, form_url = await scan(c, page_url)
        if form_url:
            contact.form_url = form_url
        if not emails and form_url and normalize_domain(form_url) == domain:
            more, _ = await scan(c, form_url)
            emails.extend(more)
        if not emails:
            for path in ("/contact", "/contacto", "/about", "/contact-us"):
                more, _ = await scan(c, f"https://{domain}{path}")
                if more:
                    emails.extend(more)
                    break

        ranked = sorted(
            {e.lower() for e in emails}, key=lambda e: -_rank_email(e, domain)
        )
        ranked = [e for e in ranked if _rank_email(e, domain) > 0]
        contact.all_emails = ranked[:8]
        if ranked:
            contact.email = ranked[0]
            contact.confidence = _rank_email(ranked[0], domain)

    if client is not None:
        await run(client)
    else:
        async with PoliteClient(concurrency=2, delay=1.0, timeout=18) as c:
            await run(c)
    return contact


async def find_contacts(page_urls: list[str], *, limit: int = 40) -> dict[str, Contact]:
    import asyncio

    urls = page_urls[:limit]
    async with PoliteClient(concurrency=3, delay=1.0, timeout=18) as c:
        results = await asyncio.gather(
            *(find_contact(u, client=c) for u in urls), return_exceptions=True
        )
    out: dict[str, Contact] = {}
    for url, res in zip(urls, results, strict=False):
        out[url] = res if isinstance(res, Contact) else Contact(source=url)
    return out


# ---------------------------------------------------------------------------
# drafting
# ---------------------------------------------------------------------------


def build_context(
    *,
    project: dict,
    opportunity: dict,
    profile: dict | None = None,
    sender_name: str = "",
    sender_role: str = "",
    extra: dict | None = None,
) -> dict:
    profile = profile or {}
    brand = profile.get("display_name") or project.get("name") or project.get("domain", "")
    contact_name = opportunity.get("contact_name") or ""
    first_name = contact_name.split()[0] if contact_name else "there"

    context = {
        "brand": brand,
        "sender_name": sender_name or profile.get("display_name") or brand,
        "sender_role": sender_role or "",
        "sender_email": profile.get("email") or settings.smtp_from or "",
        "contact_first_name": first_name,
        "contact_name": contact_name,
        "target_site": opportunity.get("target_domain", ""),
        "source_url": opportunity.get("target_url", ""),
        "landing_url": opportunity.get("landing_url") or project.get("base_url") or f"https://{project.get('domain','')}",
        "short_description": profile.get("short_description", ""),
        "city": profile.get("city", ""),
        "topic": project.get("industry", ""),
        "page_title": opportunity.get("meta_json", {}).get("page_title", "") if isinstance(opportunity.get("meta_json"), dict) else "",
        "submitted_on": datetime.now(UTC).strftime("%d %b %Y"),
    }
    context.update(extra or {})
    return context


def draft_message(
    *,
    template: dict,
    context: dict,
) -> dict:
    subject, missing_subject = render(template.get("subject", ""), context)
    body, missing_body = render(template.get("body", ""), context)
    unresolved = sorted(set(missing_subject) | set(missing_body))
    return {
        "subject": subject,
        "body": body,
        "step_number": template.get("step_number", 1),
        "delay_days": template.get("delay_days", 0),
        "unresolved_variables": unresolved,
        "ready_to_send": not unresolved,
        "template_name": template.get("name", ""),
    }


def schedule_for(step_number: int, delay_days: int, *, base: datetime | None = None) -> datetime:
    base = base or datetime.now(UTC)
    return base + timedelta(days=max(0, delay_days))


# ---------------------------------------------------------------------------
# sending
# ---------------------------------------------------------------------------


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def send_email(*, to_email: str, subject: str, body: str, reply_to: str = "") -> tuple[bool, str]:
    """Send one message. Refuses unless sending has been explicitly enabled."""
    if not settings.outreach_send_enabled:
        return False, (
            "Sending is disabled. Set DRAKEN_OUTREACH_SEND_ENABLED=true once you have reviewed "
            "the drafts - this is deliberately opt-in."
        )
    if not smtp_configured():
        return False, "SMTP is not configured (DRAKEN_SMTP_HOST / DRAKEN_SMTP_FROM)."
    if not to_email or "@" not in to_email:
        return False, f"invalid recipient: {to_email!r}"
    if "[[" in subject or "[[" in body:
        return False, "Message still contains unresolved [[variables]] - fix before sending."

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
            server.ehlo()
            try:
                server.starttls()
                server.ehlo()
            except smtplib.SMTPNotSupportedError:
                log.warning("SMTP server does not support STARTTLS; continuing unencrypted")
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True, "sent"
    except Exception as exc:  # noqa: BLE001
        log.error("outreach send failed to %s: %s", to_email, exc)
        return False, f"{type(exc).__name__}: {exc}"
