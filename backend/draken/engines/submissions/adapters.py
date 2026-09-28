"""Submission adapters: how a payload gets from your business profile to a source.

Three methods, chosen per source:

``manual``
    Draken renders a filled-in, copy-paste-ready brief and a checklist. You open
    the URL and paste. This is the default and it is the right default: most
    directories require account creation, email verification or a CAPTCHA, and
    anything that tries to defeat those is both fragile and against their terms.

``http_form``
    For sources explicitly marked ``automatable`` in the catalog, with a declared
    field mapping. Draken POSTs the form. Runs dry by default.

``api``
    Where a source offers a real API, the adapter calls it with your credentials.

What this module deliberately does not do: solve CAPTCHAs, create accounts under
false identities, rotate IPs or spin content. Those are the techniques that get
a link profile penalised, and they are the difference between a submission tool
and a spam cannon.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from draken.core.http import PoliteClient
from draken.core.logging import get_logger

log = get_logger(__name__)

# Canonical field name -> the label it usually carries on a submission form.
FIELD_LABELS = {
    "display_name": "Business / product name",
    "legal_name": "Registered legal name",
    "website": "Website URL",
    "email": "Contact email",
    "phone": "Phone number",
    "street": "Street address",
    "city": "City",
    "region": "State / region",
    "postal_code": "Postal code",
    "country": "Country",
    "short_description": "Short description (under 160 chars)",
    "long_description": "Full description",
    "categories": "Categories / tags",
    "logo_url": "Logo image URL",
    "tagline": "Tagline",
    "founded_year": "Year founded",
    "employee_count": "Company size",
    "keywords": "Keywords",
    "social_profiles": "Social profile links",
    "opening_hours": "Opening hours",
}

# Declarative form mappings for sources whose submission form is a plain POST.
# Kept small on purpose: each entry has to be verified by hand before it is
# trustworthy, and a wrong mapping means submitting garbage under your brand.
FORM_MAPPINGS: dict[str, dict] = {
    # slug: {"url": ..., "method": "POST", "fields": {form_field: profile_field}}
}


@dataclass
class SubmissionPayload:
    fields: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    method: str = "manual"
    target_url: str = ""

    def as_dict(self) -> dict:
        return {
            "fields": self.fields,
            "missing": self.missing,
            "warnings": self.warnings,
            "method": self.method,
            "target_url": self.target_url,
        }


def _profile_value(profile: dict, key: str) -> str:
    value = profile.get(key)
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items() if v)
    return str(value)


def build_payload(
    *,
    source: dict,
    profile: dict,
    landing_url: str = "",
    suggested_anchor: str = "",
) -> SubmissionPayload:
    """Map the canonical business profile onto a source's required fields."""
    required = list(source.get("required_fields") or ["display_name", "website", "short_description"])
    payload = SubmissionPayload(target_url=source.get("submit_url") or "")

    for key in required:
        value = _profile_value(profile, key)
        if key == "website" and not value:
            value = landing_url
        if value:
            payload.fields[key] = value
        else:
            payload.missing.append(key)

    if landing_url:
        payload.fields.setdefault("website", landing_url)
    if suggested_anchor:
        payload.fields["anchor_text"] = suggested_anchor

    short = payload.fields.get("short_description", "")
    if short and len(short) > 160:
        payload.warnings.append(
            f"Short description is {len(short)} characters; most forms cap it at 160. "
            "A truncated description reads badly - shorten it yourself."
        )
    if source.get("requires_account"):
        payload.warnings.append(
            "This source requires an account and usually email verification, so it cannot be "
            "fully automated. Draken prepares the content; a human completes the signup."
        )
    if source.get("slug") in FORM_MAPPINGS and source.get("automatable"):
        payload.method = "http_form"
    elif source.get("automatable") and not source.get("requires_account"):
        payload.method = "manual"
        payload.warnings.append(
            "Marked automatable but no verified form mapping exists yet, so this stays manual. "
            "Add one to FORM_MAPPINGS in engines/submissions/adapters.py once you have checked the form."
        )
    return payload


def render_instructions(
    *,
    source: dict,
    payload: SubmissionPayload,
    landing_url: str = "",
    suggested_anchor: str = "",
) -> str:
    """A copy-paste brief for the human completing the submission."""
    lines: list[str] = []
    name = source.get("name") or source.get("domain") or "source"
    lines.append(f"# Submit to: {name}")
    lines.append("")
    lines.append(f"- URL:         {source.get('submit_url') or 'https://' + (source.get('domain') or '')}")
    lines.append(f"- Category:    {source.get('category', '')}")
    lines.append(f"- Link type:   {source.get('link_type', 'unknown')}")
    lines.append(f"- Authority:   {source.get('authority', 0):.0f}/100")
    lines.append(f"- Effort:      {source.get('effort', 3)}/5")
    if source.get("guidelines_url"):
        lines.append(f"- Guidelines:  {source['guidelines_url']}")
    lines.append("")

    lines.append("## Fields to enter")
    if payload.fields:
        width = max(len(FIELD_LABELS.get(k, k)) for k in payload.fields)
        for key, value in payload.fields.items():
            label = FIELD_LABELS.get(key, key.replace("_", " ").title())
            lines.append(f"  {label.ljust(width)}  {value}")
    else:
        lines.append("  (no fields resolved - fill in the business profile first)")
    lines.append("")

    if landing_url:
        lines.append(f"Link to:      {landing_url}")
    if suggested_anchor:
        lines.append(f"Anchor text:  {suggested_anchor}")
    if landing_url or suggested_anchor:
        lines.append("")

    if payload.missing:
        lines.append("## Missing from your business profile")
        for key in payload.missing:
            lines.append(f"  - {FIELD_LABELS.get(key, key)}")
        lines.append("")

    if payload.warnings:
        lines.append("## Notes")
        for w in payload.warnings:
            lines.append(f"  - {w}")
        lines.append("")

    if source.get("notes"):
        lines.append("## Guidance")
        lines.append(f"  {source['notes']}")
        lines.append("")

    lines.append("## After submitting")
    lines.append("  1. Mark the submission as Submitted in Draken.")
    lines.append("  2. Paste the live listing URL once it is approved.")
    lines.append("  3. Draken will verify the link and add it to your backlink profile.")
    return "\n".join(lines)


async def execute_http_form(
    *,
    slug: str,
    payload: SubmissionPayload,
    dry_run: bool = True,
) -> tuple[bool, int | None, str]:
    """POST a declared form mapping. Returns ``(ok, status, excerpt)``."""
    mapping = FORM_MAPPINGS.get(slug)
    if not mapping:
        return False, None, f"no verified form mapping for '{slug}'"

    form_data = {
        form_field: payload.fields.get(profile_field, "")
        for form_field, profile_field in (mapping.get("fields") or {}).items()
    }
    url = mapping.get("url") or payload.target_url

    if dry_run:
        preview = ", ".join(f"{k}={v!r}" for k, v in form_data.items())
        return True, None, f"DRY RUN - would POST to {url} with: {preview}"

    async with PoliteClient(concurrency=1, delay=2.0, timeout=30) as client:
        res = await client.fetch(
            url,
            method=mapping.get("method", "POST"),
            data=form_data,
            retries=0,
        )
    excerpt = (res.text or "")[:800]
    if res.ok:
        return True, res.status, excerpt
    return False, res.status, res.error or excerpt
