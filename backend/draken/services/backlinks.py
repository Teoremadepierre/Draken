"""Backlink index persistence and profile reporting."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.core.logging import get_logger
from draken.core.models import (
    Backlink,
    CompetitorBacklink,
    LinkStatus,
    Project,
    utcnow,
)
from draken.core.urls import normalize_domain
from draken.engines.backlinks import discovery, toxicity
from draken.engines.backlinks import profile as profile_mod
from draken.engines.serp import authority as authority_mod

log = get_logger(__name__)


def _to_dicts(rows: list[Backlink]) -> list[dict]:
    return [
        {
            "id": b.id,
            "source_url": b.source_url,
            "source_domain": b.source_domain,
            "target_url": b.target_url,
            "anchor_text": b.anchor_text,
            "link_type": b.link_type,
            "status": b.status,
            "domain_authority": b.domain_authority,
            "toxicity_score": b.toxicity_score,
            "source_category": b.source_category,
            "first_seen": b.first_seen,
            "lost_at": b.lost_at,
        }
        for b in rows
    ]


def profile_report(db: Session, *, project: Project) -> dict:
    rows = list(
        db.execute(select(Backlink).where(Backlink.project_id == project.id)).scalars()
    )
    return profile_mod.analyse(
        _to_dicts(rows),
        target_domain=project.domain,
        brand_terms=list(project.brand_terms or []),
    )


def anchor_mix(db: Session, *, project: Project) -> dict[str, int]:
    """Current anchor bucket counts - fed into anchor suggestions."""
    rows = list(
        db.execute(
            select(Backlink).where(
                Backlink.project_id == project.id, Backlink.status == LinkStatus.live.value
            )
        ).scalars()
    )
    mix: dict[str, int] = {}
    for b in rows:
        bucket = profile_mod.classify_anchor(
            b.anchor_text, brand_terms=list(project.brand_terms or []), target_domain=project.domain
        )
        mix[bucket] = mix.get(bucket, 0) + 1
    return mix


def existing_domains(db: Session, *, project_id: int) -> set[str]:
    return {
        d for (d,) in db.execute(
            select(Backlink.source_domain).where(Backlink.project_id == project_id).distinct()
        ).all() if d
    }


async def import_links(
    db: Session,
    *,
    project: Project,
    rows: list[dict] | None = None,
    csv_text: str = "",
    discovered_via: str = "import",
    verify: bool = False,
) -> dict:
    """Import backlinks from any tool export, optionally verifying each one."""
    parsed = discovery.parse_import(csv_text=csv_text, rows=rows)
    if not parsed:
        return {"imported": 0, "updated": 0, "message": "No usable rows found in the input."}

    if verify:
        verified = await discovery.verify_links(
            [(link.source_url, project.domain) for link in parsed[:200]]
        )
        by_url = {v.source_url: v for v in verified}
        for link in parsed:
            v = by_url.get(link.source_url)
            if v:
                link.status = v.status
                link.anchor_text = v.anchor_text or link.anchor_text
                link.link_type = v.link_type
                link.domain_authority = v.domain_authority or link.domain_authority
                link.meta.update(v.meta)
    else:
        auth_map = await authority_mod.authority_for([link.source_domain for link in parsed])
        for link in parsed:
            if not link.domain_authority:
                link.domain_authority = auth_map.get(link.source_domain, 0.0)
            link.status = LinkStatus.live.value

    imported = updated = 0
    for link in parsed:
        tox, reasons = toxicity.score_link(
            source_url=link.source_url,
            source_domain=link.source_domain,
            anchor_text=link.anchor_text,
            link_type=link.link_type,
            domain_authority=link.domain_authority,
            target_domain=project.domain,
        )
        existing = db.execute(
            select(Backlink).where(
                Backlink.project_id == project.id,
                Backlink.source_url == link.source_url,
                Backlink.target_url == link.target_url,
            )
        ).scalars().first()
        if existing is None:
            db.add(
                Backlink(
                    project_id=project.id,
                    source_url=link.source_url,
                    source_domain=link.source_domain,
                    target_url=link.target_url,
                    anchor_text=link.anchor_text,
                    link_type=link.link_type,
                    status=link.status,
                    domain_authority=link.domain_authority,
                    spam_score=toxicity.spam_score(
                        link.source_domain, domain_authority=link.domain_authority
                    ),
                    toxicity_score=tox,
                    toxicity_reasons=reasons,
                    discovered_via=discovered_via or link.discovered_via,
                    last_checked=utcnow() if verify else None,
                    meta_json=link.meta,
                )
            )
            imported += 1
        else:
            existing.anchor_text = link.anchor_text or existing.anchor_text
            existing.link_type = (
                link.link_type if link.link_type != "unknown" else existing.link_type
            )
            existing.domain_authority = link.domain_authority or existing.domain_authority
            existing.status = link.status
            existing.toxicity_score = tox
            existing.toxicity_reasons = reasons
            if verify:
                existing.last_checked = utcnow()
            updated += 1
    db.commit()
    return {
        "imported": imported,
        "updated": updated,
        "verified": verify,
        "total_parsed": len(parsed),
    }


async def discover_own_links(db: Session, *, project: Project) -> dict:
    """Find links and unlinked mentions pointing at us, via public search."""
    brand_terms = list(project.brand_terms or []) or [project.domain.split(".")[0]]
    links = await discovery.discover_mentions(
        domain=project.domain,
        brand_terms=brand_terms,
        country=project.country,
        language=project.language,
    )
    live = [link for link in links if link.status == LinkStatus.live.value]
    unlinked = [link for link in links if link.meta.get("unlinked_mention")]

    added = 0
    for link in live:
        exists = db.execute(
            select(Backlink).where(
                Backlink.project_id == project.id, Backlink.source_url == link.source_url
            )
        ).scalars().first()
        if exists:
            exists.last_checked = utcnow()
            exists.status = LinkStatus.live.value
            continue
        tox, reasons = toxicity.score_link(
            source_url=link.source_url,
            source_domain=link.source_domain,
            anchor_text=link.anchor_text,
            link_type=link.link_type,
            domain_authority=link.domain_authority,
            target_domain=project.domain,
        )
        db.add(
            Backlink(
                project_id=project.id,
                source_url=link.source_url,
                source_domain=link.source_domain,
                target_url=link.target_url,
                anchor_text=link.anchor_text,
                link_type=link.link_type,
                status=LinkStatus.live.value,
                domain_authority=link.domain_authority,
                toxicity_score=tox,
                toxicity_reasons=reasons,
                discovered_via="mention_search",
                last_checked=utcnow(),
            )
        )
        added += 1
    db.commit()
    return {
        "candidates_checked": len(links),
        "live_links_found": len(live),
        "new_links_added": added,
        "unlinked_mentions": [
            {"url": link.source_url, "domain": link.source_domain, "authority": link.domain_authority}
            for link in unlinked
        ],
        "provider_note": (
            "Discovery uses public search results, so coverage is partial. For a complete index, "
            "import your Search Console links export as well."
        ),
    }


def store_competitor_links(db: Session, *, project_id: int, raw_links: list[dict]) -> int:
    stored = 0
    for row in raw_links:
        exists = db.execute(
            select(CompetitorBacklink).where(
                CompetitorBacklink.project_id == project_id,
                CompetitorBacklink.competitor_domain == row["competitor_domain"],
                CompetitorBacklink.source_url == row["source_url"],
            )
        ).scalars().first()
        if exists:
            continue
        db.add(
            CompetitorBacklink(
                project_id=project_id,
                competitor_domain=row["competitor_domain"],
                source_url=row["source_url"],
                source_domain=row["source_domain"],
                anchor_text=row.get("anchor_text", "")[:600],
                link_type=row.get("link_type", "unknown"),
                domain_authority=float(row.get("domain_authority") or 0),
                discovered_via=row.get("discovered_via", "competitor_serp"),
            )
        )
        stored += 1
    db.commit()
    return stored


def competitor_comparison(db: Session, *, project: Project) -> dict:
    """Side-by-side referring-domain comparison against each competitor."""
    own = list(
        db.execute(
            select(Backlink).where(
                Backlink.project_id == project.id, Backlink.status == LinkStatus.live.value
            )
        ).scalars()
    )
    own_domains = {b.source_domain for b in own if b.source_domain}

    comp_rows = list(
        db.execute(
            select(CompetitorBacklink).where(CompetitorBacklink.project_id == project.id)
        ).scalars()
    )
    by_competitor: dict[str, set[str]] = {}
    authority_by_domain: dict[str, float] = {}
    for r in comp_rows:
        by_competitor.setdefault(r.competitor_domain, set()).add(r.source_domain)
        authority_by_domain[r.source_domain] = max(
            authority_by_domain.get(r.source_domain, 0.0), r.domain_authority or 0.0
        )

    competitors = [
        {
            "domain": comp,
            "referring_domains_found": len(domains),
            "shared_with_us": len(domains & own_domains),
            "gap": len(domains - own_domains),
        }
        for comp, domains in sorted(by_competitor.items(), key=lambda kv: -len(kv[1]))
    ]

    # Domains linking to 2+ competitors but not us: the strongest prospects.
    hit_counts: dict[str, int] = {}
    for domains in by_competitor.values():
        for d in domains:
            hit_counts[d] = hit_counts.get(d, 0) + 1
    intersect = sorted(
        (
            {
                "domain": d,
                "competitors_linking": n,
                "authority": authority_by_domain.get(d, 0.0),
                "we_have_it": d in own_domains,
            }
            for d, n in hit_counts.items()
        ),
        key=lambda r: (-r["competitors_linking"], -r["authority"]),
    )

    return {
        "own_referring_domains": len(own_domains),
        "competitors": competitors,
        "link_intersect": [r for r in intersect if not r["we_have_it"]][:100],
        "shared_links": [r for r in intersect if r["we_have_it"]][:50],
        "note": (
            "Competitor data comes from public search recon, so it is a sample rather than a full "
            "index. Domains linking to two or more competitors are the highest-confidence prospects."
        ),
    }


def disavow_file(db: Session, *, project: Project, threshold: float = 70.0) -> str:
    """Generate a Google-format disavow file for the worst links."""
    rows = list(
        db.execute(
            select(Backlink).where(
                Backlink.project_id == project.id, Backlink.toxicity_score >= threshold
            )
        ).scalars()
    )
    lines = [
        f"# Disavow file for {project.domain}",
        f"# Generated by Draken - {len(rows)} link(s) at toxicity >= {threshold}",
        "# Review every line before uploading. Disavowing good links costs you rankings,",
        "# and disavowal should be a last resort after trying removal requests.",
        "",
    ]
    by_domain: dict[str, list[Backlink]] = {}
    for b in rows:
        by_domain.setdefault(normalize_domain(b.source_domain), []).append(b)
    for domain, links in sorted(by_domain.items()):
        reasons = sorted({r for b in links for r in (b.toxicity_reasons or [])})
        if reasons:
            lines.append(f"# {domain}: {reasons[0]}")
        # Domain-level disavow when several links share the domain, else URL-level.
        if len(links) > 2:
            lines.append(f"domain:{domain}")
        else:
            lines.extend(b.source_url for b in links)
    return "\n".join(lines) + "\n"
