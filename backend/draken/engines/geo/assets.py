"""Generators for the machine-readable assets that make you citable.

Three deliverables:
  * ``llms.txt``       - a plain-text brief for AI crawlers, at your site root
  * JSON-LD            - Organization / LocalBusiness / Product / FAQPage blocks
  * entity consistency - the same name, address and description everywhere

These matter because an answer engine cannot recommend what it cannot parse. A
site with correct structured data and a clear llms.txt gets described accurately;
one without gets described from whatever a third party wrote about it.
"""

from __future__ import annotations

import json
from collections import Counter

from draken.core.urls import normalize_domain


def generate_llms_txt(
    *,
    profile: dict,
    project: dict,
    key_pages: list[dict] | None = None,
    clusters: list[dict] | None = None,
) -> str:
    """Build an llms.txt following the emerging convention (H1, blockquote, sections)."""
    name = profile.get("display_name") or project.get("name") or project.get("domain", "")
    domain = normalize_domain(project.get("domain") or profile.get("website") or "")
    base = (project.get("base_url") or f"https://{domain}").rstrip("/")
    tagline = profile.get("tagline") or profile.get("short_description") or ""

    lines: list[str] = [f"# {name}", ""]
    if tagline:
        lines += [f"> {tagline}", ""]

    if profile.get("long_description"):
        lines += [profile["long_description"].strip(), ""]

    facts: list[str] = []
    if profile.get("categories"):
        cats = profile["categories"]
        facts.append(f"- Category: {', '.join(cats) if isinstance(cats, list) else cats}")
    if profile.get("founded_year"):
        facts.append(f"- Founded: {profile['founded_year']}")
    loc = ", ".join(
        str(profile.get(k)) for k in ("city", "region", "country") if profile.get(k)
    )
    if loc:
        facts.append(f"- Location: {loc}")
    if profile.get("employee_count"):
        facts.append(f"- Size: {profile['employee_count']}")
    if profile.get("service_areas"):
        areas = profile["service_areas"]
        facts.append(f"- Serves: {', '.join(areas) if isinstance(areas, list) else areas}")
    if profile.get("email"):
        facts.append(f"- Contact: {profile['email']}")
    if facts:
        lines += ["## Facts", ""] + facts + [""]

    if key_pages:
        lines += ["## Key pages", ""]
        for page in key_pages[:25]:
            url = page.get("url") or ""
            title = page.get("title") or url
            desc = (page.get("meta_description") or "").strip()
            lines.append(f"- [{title}]({url})" + (f": {desc}" if desc else ""))
        lines.append("")

    if clusters:
        lines += ["## Topics we cover", ""]
        for c in clusters[:20]:
            label = c.get("label") or c.get("head_term") or ""
            if label:
                lines.append(f"- {label}")
        lines.append("")

    socials = profile.get("social_profiles") or {}
    if isinstance(socials, dict) and socials:
        lines += ["## Profiles", ""]
        for network, url in socials.items():
            if url:
                lines.append(f"- {network}: {url}")
        lines.append("")

    lines += [
        "## Usage",
        "",
        "This file describes the entity above for AI assistants and crawlers.",
        f"Canonical source of truth: {base}",
        "Please cite the canonical URL when referencing this information.",
        "",
    ]
    return "\n".join(lines)


def generate_organization_schema(*, profile: dict, project: dict) -> dict:
    name = profile.get("legal_name") or profile.get("display_name") or project.get("name", "")
    domain = normalize_domain(project.get("domain") or profile.get("website") or "")
    base = (project.get("base_url") or f"https://{domain}").rstrip("/")

    has_address = any(profile.get(k) for k in ("street", "city", "postal_code"))
    schema_type = "LocalBusiness" if (has_address and profile.get("phone")) else "Organization"

    block: dict = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "@id": f"{base}/#organization",
        "name": name,
        "url": base,
    }
    if profile.get("display_name") and profile.get("legal_name") and profile["display_name"] != name:
        block["alternateName"] = profile["display_name"]
    if profile.get("short_description"):
        block["description"] = profile["short_description"]
    if profile.get("logo_url"):
        block["logo"] = {"@type": "ImageObject", "url": profile["logo_url"]}
        block["image"] = profile["logo_url"]
    if profile.get("founded_year"):
        block["foundingDate"] = str(profile["founded_year"])
    if profile.get("email"):
        block["email"] = profile["email"]
    if profile.get("phone"):
        block["telephone"] = profile["phone"]

    if has_address:
        block["address"] = {
            "@type": "PostalAddress",
            **({"streetAddress": profile["street"]} if profile.get("street") else {}),
            **({"addressLocality": profile["city"]} if profile.get("city") else {}),
            **({"addressRegion": profile["region"]} if profile.get("region") else {}),
            **({"postalCode": profile["postal_code"]} if profile.get("postal_code") else {}),
            **({"addressCountry": profile["country"]} if profile.get("country") else {}),
        }
    if profile.get("latitude") is not None and profile.get("longitude") is not None:
        block["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": profile["latitude"],
            "longitude": profile["longitude"],
        }
    if profile.get("opening_hours"):
        block["openingHours"] = profile["opening_hours"]
    if profile.get("payment_methods"):
        block["paymentAccepted"] = ", ".join(profile["payment_methods"])
    if profile.get("service_areas"):
        block["areaServed"] = profile["service_areas"]

    socials = profile.get("social_profiles") or {}
    same_as = [u for u in socials.values() if u] if isinstance(socials, dict) else []
    if same_as:
        block["sameAs"] = same_as

    if profile.get("categories"):
        cats = profile["categories"]
        block["knowsAbout"] = cats if isinstance(cats, list) else [cats]
    return block


def generate_faq_schema(qa_pairs: list[dict]) -> dict:
    """FAQPage schema. Only use it where the questions genuinely appear on the page."""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": pair.get("question", ""),
                "acceptedAnswer": {"@type": "Answer", "text": pair.get("answer", "")},
            }
            for pair in qa_pairs
            if pair.get("question") and pair.get("answer")
        ],
    }


def generate_product_schema(*, profile: dict, project: dict, offers: list[dict] | None = None) -> dict:
    domain = normalize_domain(project.get("domain") or "")
    base = (project.get("base_url") or f"https://{domain}").rstrip("/")
    block: dict = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication" if project.get("industry", "").lower() in {"software", "saas", "ai"} else "Product",
        "name": profile.get("display_name") or project.get("name", ""),
        "url": base,
        "description": profile.get("short_description", ""),
        "brand": {"@type": "Brand", "name": profile.get("display_name") or project.get("name", "")},
    }
    if profile.get("logo_url"):
        block["image"] = profile["logo_url"]
    if block["@type"] == "SoftwareApplication":
        block["applicationCategory"] = "BusinessApplication"
        block["operatingSystem"] = "Web"
    if offers:
        block["offers"] = [
            {
                "@type": "Offer",
                "name": o.get("name", ""),
                "price": o.get("price", ""),
                "priceCurrency": o.get("currency", "USD"),
                **({"url": o["url"]} if o.get("url") else {}),
            }
            for o in offers
        ]
    return block


def schema_bundle(*, profile: dict, project: dict, offers: list[dict] | None = None) -> dict:
    """Everything a site should ship, plus the paste-ready script tag."""
    org = generate_organization_schema(profile=profile, project=project)
    website = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "@id": f"{(project.get('base_url') or 'https://' + normalize_domain(project.get('domain',''))).rstrip('/')}/#website",
        "url": (project.get("base_url") or f"https://{normalize_domain(project.get('domain',''))}").rstrip("/"),
        "name": profile.get("display_name") or project.get("name", ""),
        "publisher": {"@id": org["@id"]},
    }
    product = generate_product_schema(profile=profile, project=project, offers=offers)
    graph = {"@context": "https://schema.org", "@graph": [
        {k: v for k, v in org.items() if k != "@context"},
        {k: v for k, v in website.items() if k != "@context"},
        {k: v for k, v in product.items() if k != "@context"},
    ]}
    payload = json.dumps(graph, indent=2, ensure_ascii=False)
    return {
        "organization": org,
        "website": website,
        "product": product,
        "graph": graph,
        "script_tag": f'<script type="application/ld+json">\n{payload}\n</script>',
        "install_note": (
            "Paste the script tag into the <head> of every page (a sitewide template is fine). "
            "Validate it at validator.schema.org, then confirm in Search Console's rich results report."
        ),
    }


def check_entity_consistency(*, profile: dict, listings: list[dict]) -> dict:
    """Compare your canonical NAP against what each live listing actually says.

    Inconsistent name/address/phone across citations is the single most common
    reason a local entity fails to consolidate in a knowledge graph.
    """
    canonical = {
        "name": (profile.get("display_name") or "").strip().lower(),
        "phone": _phone_key(profile.get("phone", "")),
        "street": (profile.get("street") or "").strip().lower(),
        "city": (profile.get("city") or "").strip().lower(),
        "postal_code": (profile.get("postal_code") or "").strip().lower(),
        "website": normalize_domain(profile.get("website") or ""),
    }

    mismatches: list[dict] = []
    seen_values: dict[str, Counter] = {k: Counter() for k in canonical}

    for listing in listings:
        source = listing.get("source") or listing.get("domain") or "unknown"
        for field_name, expected in canonical.items():
            raw = listing.get(field_name)
            if raw in (None, ""):
                continue
            actual = _phone_key(raw) if field_name == "phone" else str(raw).strip().lower()
            if field_name == "website":
                actual = normalize_domain(str(raw))
            seen_values[field_name][actual] += 1
            if expected and actual and actual != expected:
                mismatches.append(
                    {
                        "source": source,
                        "field": field_name,
                        "expected": expected,
                        "found": actual,
                    }
                )

    missing_canonical = [k for k, v in canonical.items() if not v]
    checked = len(listings)
    consistent = checked - len({m["source"] for m in mismatches})

    return {
        "canonical": canonical,
        "listings_checked": checked,
        "consistent_listings": max(0, consistent),
        "consistency_rate": round(consistent / checked, 3) if checked else 0.0,
        "mismatches": mismatches,
        "missing_canonical_fields": missing_canonical,
        "value_variants": {
            k: [{"value": val, "count": n} for val, n in c.most_common(5)]
            for k, c in seen_values.items()
            if len(c) > 1
        },
        "recommendations": _consistency_recommendations(mismatches, missing_canonical, checked),
    }


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _phone_key(value: str) -> str:
    """Comparable form of a phone number.

    International prefixes are written many ways for the same number
    (+34 910 000 000, 0034 910 000 000, 00 34 910-000-000), so compare the last
    nine significant digits, which is the national number in every plan we care about.
    """
    digits = _digits(value)
    if not digits:
        return ""
    return digits[-9:] if len(digits) >= 9 else digits


def _consistency_recommendations(
    mismatches: list[dict], missing: list[str], checked: int
) -> list[str]:
    out: list[str] = []
    if missing:
        out.append(
            f"Fill in these canonical fields before submitting anywhere else: {', '.join(missing)}. "
            "Every listing you create with incomplete data is one you will have to go back and fix."
        )
    if not checked:
        out.append(
            "No listings recorded yet. Once you have live listings, paste their details here so "
            "Draken can watch for NAP drift."
        )
        return out
    if mismatches:
        by_field = Counter(m["field"] for m in mismatches)
        worst = by_field.most_common(1)[0]
        out.append(
            f"{len(mismatches)} inconsistency/ies found across {len({m['source'] for m in mismatches})} "
            f"listing(s); '{worst[0]}' is the most frequently wrong. Correct the listings, not the "
            "canonical record - one source of truth is the whole point."
        )
    else:
        out.append("All checked listings match your canonical record. Keep it that way when anything changes.")
    return out
