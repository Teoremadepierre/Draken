"""The one-button scan: paste a URL, get everything.

Runs every module in the right order against one site and returns a single
report that answers three questions:

  1. What is wrong with the site, in priority order, and how do I fix each thing?
  2. Which backlinks can I get right now, from what authority, and how?
  3. How do the assistants describe me, and what moves that?

Each stage is isolated: a stage that fails records its error and the scan carries
on, because a blocked SERP endpoint should not cost you the site audit.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.core.config import settings
from draken.core.database import session_scope
from draken.core.logging import get_logger
from draken.core.models import (
    BusinessProfile,
    LinkOpportunity,
    OpportunityStatus,
    Project,
)
from draken.core.urls import normalize_domain, normalize_url
from draken.engines.crawler.crawler import fetch_single_page
from draken.engines.scheduler import jobs as job_runner
from draken.services import audits as audit_service
from draken.services import backlinks as backlink_service
from draken.services import diagnostics as diagnostics_service
from draken.services import geo as geo_service
from draken.services import keywords as keyword_service
from draken.services import opportunities as opportunity_service
from draken.services import realdata

log = get_logger(__name__)

# Effort 1-2 is the tier a person can finish in an afternoon.
IMMEDIATE_EFFORT = 2


# ---------------------------------------------------------------------------
# project bootstrap
# ---------------------------------------------------------------------------


async def ensure_project(db: Session, *, url: str, name: str = "") -> tuple[Project, bool]:
    """Find or create the project for a URL, filling in what we can detect."""
    url = normalize_url(url if "//" in url else f"https://{url}")
    domain = normalize_domain(url)
    if not domain:
        raise ValueError(f"Could not parse a domain from {url!r}")

    existing = db.execute(select(Project).where(Project.domain == domain)).scalars().first()
    if existing is not None:
        return existing, False

    detected = await _detect_site_identity(url)
    project = Project(
        name=name or detected.get("name") or domain.split(".")[0].title(),
        domain=domain,
        base_url=url,
        description=detected.get("description", "")[:500],
        country=detected.get("country", "US"),
        language=detected.get("language", "en"),
        industry=detected.get("industry", ""),
        brand_terms=[name or detected.get("name") or domain.split(".")[0]],
        competitors=[],
    )
    db.add(project)
    db.commit()

    db.add(
        BusinessProfile(
            project_id=project.id,
            display_name=project.name,
            website=project.base_url,
            country=project.country,
            short_description=detected.get("description", "")[:300],
            logo_url=detected.get("logo", ""),
            social_profiles=detected.get("social", {}),
        )
    )
    db.commit()
    log.info("scanner created project %s for %s", project.id, domain)
    return project, True


async def _detect_site_identity(url: str) -> dict:
    """Read the homepage once and pre-fill whatever it tells us.

    Saves the user from typing what the page already states, which is the
    difference between "paste a URL" and "fill in a form".
    """
    out: dict = {}
    try:
        record, parsed = await fetch_single_page(url)
    except Exception as exc:  # noqa: BLE001
        log.info("identity detection failed for %s: %s", url, exc)
        return out
    if parsed is None:
        return out

    out["name"] = (
        parsed.open_graph.get("og:site_name")
        or (parsed.title.split("|")[0].split("-")[0].strip() if parsed.title else "")
    )[:120]
    out["description"] = (
        parsed.meta_description or parsed.open_graph.get("og:description") or ""
    )
    out["logo"] = parsed.open_graph.get("og:image", "")

    lang = (parsed.lang or "").split("-")
    if lang and lang[0]:
        out["language"] = lang[0].lower()
        if len(lang) > 1:
            out["country"] = lang[1].upper()

    # Organization schema is the most reliable identity source when present.
    for block in parsed.schema_blocks:
        types = block.get("@type")
        types = types if isinstance(types, list) else [types]
        if any(t in {"Organization", "LocalBusiness", "Corporation"} for t in types if t):
            out["name"] = block.get("name") or out.get("name", "")
            out["description"] = block.get("description") or out.get("description", "")
            same_as = block.get("sameAs") or []
            if isinstance(same_as, list):
                out["social"] = {
                    normalize_domain(u).split(".")[0]: u for u in same_as if isinstance(u, str)
                }
            address = block.get("address") or {}
            if isinstance(address, dict) and address.get("addressCountry"):
                out["country"] = str(address["addressCountry"])[:2].upper()
            break

    text = f"{parsed.title} {parsed.meta_description} {parsed.text[:2000]}".lower()
    out["industry"] = _guess_industry(text)
    return out


_INDUSTRY_HINTS = {
    "software": ["software", "saas", "api", "plataforma", "platform", "app", "dashboard"],
    "ai": ["inteligencia artificial", "artificial intelligence", " ai ", "machine learning", "llm"],
    "ecommerce": ["tienda", "shop", "carrito", "cart", "checkout", "envío gratis", "free shipping"],
    "restaurant": ["restaurante", "restaurant", "menú", "menu", "reservar mesa", "book a table"],
    "legal": ["abogado", "lawyer", "attorney", "bufete", "law firm", "jurídic"],
    "health": ["clínica", "clinic", "doctor", "médic", "dentist", "salud", "health"],
    "real-estate": ["inmobiliaria", "real estate", "piso", "property", "alquiler", "for sale"],
    "home-services": ["reforma", "fontaner", "plumber", "electricista", "electrician", "cerrajer"],
    "education": ["curso", "course", "formación", "training", "academia", "bootcamp"],
    "travel": ["hotel", "viaje", "travel", "tour", "booking", "vuelo", "flight"],
    "agency": ["agencia", "agency", "consultor", "consulting", "marketing"],
}


def _guess_industry(text: str) -> str:
    best, best_hits = "", 0
    for industry, hints in _INDUSTRY_HINTS.items():
        hits = sum(1 for h in hints if h in text)
        if hits > best_hits:
            best, best_hits = industry, hits
    return best if best_hits >= 2 else ""


# ---------------------------------------------------------------------------
# the scan
# ---------------------------------------------------------------------------


@job_runner.register("full_scan")
async def full_scan(project_id: int, params: dict) -> dict:
    """Every module, in dependency order, tolerant of individual failures."""
    max_pages = int(params.get("max_pages") or 120)
    deep = bool(params.get("deep", False))
    stages: dict = {}
    started = datetime.now(UTC)

    def record(name: str, value):
        stages[name] = value

    # 0. Connectivity first, so the report can explain any empty stage.
    try:
        with session_scope() as db:
            project = db.get(Project, project_id)
            base = project.base_url or f"https://{project.domain}"
        record("connectivity", await diagnostics_service.run_connectivity_check(target_url=base))
    except Exception as exc:  # noqa: BLE001
        record("connectivity", {"error": str(exc)})

    # 1. Real first-party data, if configured: it changes every later estimate.
    for key, fn in (
        ("search_console", realdata.import_search_console),
        ("bing_links", realdata.import_bing_links),
    ):
        try:
            with session_scope() as db:
                project = db.get(Project, project_id)
                kwargs = {"track_top": 25} if key == "search_console" else {}
                outcome = await fn(db, project=project, **kwargs)
            # "Not configured" is a choice, not a failure: report it as skipped so
            # the report does not cry wolf about something the operator opted out of.
            if not outcome.get("configured"):
                outcome = {
                    "configured": False,
                    "skipped": "not configured",
                    "how_to_enable": outcome.get("error", ""),
                }
            record(key, outcome)
        except Exception as exc:  # noqa: BLE001
            log.warning("scan stage %s failed: %s", key, exc)
            record(key, {"error": f"{type(exc).__name__}: {exc}"})

    # 2. Site audit.
    try:
        with session_scope() as db:
            project = db.get(Project, project_id)
            audit = audit_service.create_audit(db, project=project)
            audit_id = audit.id
        with session_scope() as db:
            record("audit", await audit_service.run_audit(
                db, audit_id=audit_id, max_pages=max_pages, max_depth=4
            ))
    except Exception as exc:  # noqa: BLE001
        record("audit", {"error": f"{type(exc).__name__}: {exc}"})

    # 3. Keywords, seeded from what the site itself is about.
    try:
        with session_scope() as db:
            project = db.get(Project, project_id)
            seeds = params.get("seeds") or _seeds_from_project(db, project)
            if seeds:
                result = await keyword_service.research(
                    db, project=project, seeds=seeds,
                    country=project.country, language=project.language,
                    max_results=400 if deep else 200,
                )
                result.pop("keywords", None)
                result["clustering"] = keyword_service.rebuild_clusters(db, project=project)
                record("keywords", result)
            else:
                record("keywords", {"skipped": "no seed terms could be derived from the site"})
    except Exception as exc:  # noqa: BLE001
        record("keywords", {"error": f"{type(exc).__name__}: {exc}"})

    # 4. Backlinks: what exists today.
    try:
        with session_scope() as db:
            project = db.get(Project, project_id)
            record("backlink_discovery", await backlink_service.discover_own_links(db, project=project))
    except Exception as exc:  # noqa: BLE001
        record("backlink_discovery", {"error": f"{type(exc).__name__}: {exc}"})

    # 5. Opportunities: what you can get.
    try:
        with session_scope() as db:
            project = db.get(Project, project_id)
            result = opportunity_service.generate_from_catalog(db, project=project, limit=350)
            result.pop("tactic_playbook", None)
            record("opportunities", result)
    except Exception as exc:  # noqa: BLE001
        record("opportunities", {"error": f"{type(exc).__name__}: {exc}"})

    # 6. Unlinked mentions: the fastest wins available.
    try:
        with session_scope() as db:
            project = db.get(Project, project_id)
            record("unlinked_mentions",
                   await opportunity_service.prospect_unlinked_mentions(db, project=project))
    except Exception as exc:  # noqa: BLE001
        record("unlinked_mentions", {"error": f"{type(exc).__name__}: {exc}"})

    # 7. AI visibility baseline.
    try:
        with session_scope() as db:
            project = db.get(Project, project_id)
            prompts = geo_service.generate_prompt_set(db, project=project, limit=25)
            prompts.pop("prompts", None)
            record("ai_prompts", prompts)
            if any(settings.ai_engines_configured().values()):
                record("ai_visibility",
                       await geo_service.run_visibility(db, project=project, limit=12))
            else:
                record("ai_visibility", {
                    "runs": 0,
                    "skipped": "no AI engine configured; prompt set created for later",
                })
    except Exception as exc:  # noqa: BLE001
        record("ai_visibility", {"error": f"{type(exc).__name__}: {exc}"})

    finished = datetime.now(UTC)
    return {
        "project_id": project_id,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": int((finished - started).total_seconds()),
        "stages": stages,
    }


def _seeds_from_project(db: Session, project: Project) -> list[str]:
    """Derive keyword seeds from the site rather than asking the user."""
    seeds: list[str] = []
    profile = db.execute(
        select(BusinessProfile).where(BusinessProfile.project_id == project.id)
    ).scalar_one_or_none()

    if profile and profile.categories:
        seeds.extend([str(c) for c in profile.categories][:3])
    if project.industry:
        seeds.append(project.industry)
    if profile and profile.short_description:
        # The first noun phrase of the description is usually the category.
        words = [w for w in profile.short_description.lower().split() if len(w) > 3]
        if len(words) >= 2:
            seeds.append(" ".join(words[:2]))

    seen: set[str] = set()
    out: list[str] = []
    for seed in seeds:
        s = " ".join(str(seed).split()).lower()
        if s and s not in seen and len(s) > 2:
            seen.add(s)
            out.append(s)
    return out[:4]


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------


def build_report(db: Session, *, project: Project) -> dict:
    """The single screen a person reads after a scan."""
    audit = audit_service.latest_audit(db, project_id=project.id)
    issues = audit_service.issues_grouped(db, audit_id=audit.id) if audit else []
    profile = backlink_service.profile_report(db, project=project)
    pipeline = opportunity_service.pipeline(db, project_id=project.id)
    geo = geo_service.summary(db, project=project)
    sources = realdata.data_sources_status(db, project=project)
    rankings = keyword_service.ranking_overview(db, project=project)

    fixes = _prioritised_fixes(issues, profile, geo, audit)
    immediate = _immediate_backlinks(db, project=project)

    from sqlalchemy import func

    from draken.core.models import Keyword

    keyword_total = db.execute(
        select(func.count(Keyword.id)).where(Keyword.project_id == project.id)
    ).scalar() or 0

    return {
        "project": {
            "id": project.id, "name": project.name, "domain": project.domain,
            "base_url": project.base_url, "country": project.country,
            "language": project.language, "industry": project.industry,
        },
        "scanned_at": audit.finished_at.isoformat() if audit and audit.finished_at else None,
        "scores": {
            "site_health": audit.health_score if audit else None,
            "link_authority": profile["authority_score"],
            "ai_visibility": geo["avg_visibility_score"],
            "overall": _overall_score(audit, profile, geo),
            "data_quality": sources["quality"],
        },
        "headline": {
            "pages_crawled": audit.pages_crawled if audit else 0,
            "issues_found": sum((audit.issue_counts or {}).values()) if audit else 0,
            "critical_issues": (audit.issue_counts or {}).get("critical", 0) if audit else 0,
            "referring_domains": profile["referring_domains"],
            "backlinks_available_now": len(immediate["now"]),
            "keywords_found": keyword_total,
            "keywords_tracked": rankings["tracked_keywords"],
            "ai_mention_rate": geo["mention_rate"],
        },
        "fixes": fixes,
        "backlinks": immediate,
        "link_profile": {
            "referring_domains": profile["referring_domains"],
            "authority_score": profile["authority_score"],
            "dofollow_links": profile["dofollow_links"],
            "toxic_links": profile["toxic_links"],
            "anchor_warnings": profile["anchor_health"]["warnings"],
            "recommendations": profile["recommendations"],
        },
        "ai_visibility": {
            "mention_rate": geo["mention_rate"],
            "citation_rate": geo["citation_rate"],
            "prompts_tracked": geo["prompts_tracked"],
            "runs": geo["runs"],
            "recommendations": geo["recommendations"],
            "top_cited_domains": geo.get("top_cited_domains", [])[:10],
            "engines_configured": geo["engines_configured"],
        },
        "pipeline": pipeline,
        "data_sources": sources,
        "audit_id": audit.id if audit else None,
    }


def _overall_score(audit, profile: dict, geo: dict) -> float:
    """One number, weighted the way the work actually matters."""
    health = audit.health_score if audit else 0.0
    authority = profile["authority_score"]
    ai = geo["avg_visibility_score"]
    return round(0.4 * health + 0.4 * authority + 0.2 * ai, 1)


SEVERITY_ORDER = {"critical": 0, "error": 1, "warning": 2, "notice": 3}


def _prioritised_fixes(issues: list[dict], profile: dict, geo: dict, audit) -> list[dict]:
    """Everything wrong, in the order a person should actually work it."""
    fixes: list[dict] = []

    for issue in issues:
        fixes.append(
            {
                "id": f"audit:{issue['code']}",
                "kind": "technical",
                "severity": issue["severity"],
                "title": issue["title"],
                "detail": issue["description"],
                "how": issue["how_to_fix"],
                "affected": issue["count"],
                "examples": [e["url"] for e in issue.get("examples", [])][:5],
                "category": issue["category"],
                "can_ask_ai": True,
            }
        )

    if profile["referring_domains"] == 0:
        fixes.append({
            "id": "links:none",
            "kind": "backlinks",
            "severity": "critical",
            "title": "No backlinks at all",
            "detail": (
                "Nothing links to this site, so there is no authority signal and new pages are "
                "discovered only through the sitemap."
            ),
            "how": (
                "Work the foundation tier in the Backlinks section below: business and brand "
                "profiles first, then the free dofollow directories. Target 30 referring "
                "domains in the first month."
            ),
            "affected": 0,
            "examples": [],
            "category": "backlinks",
            "can_ask_ai": True,
        })
    elif profile["referring_domains"] < 10:
        fixes.append({
            "id": "links:thin",
            "kind": "backlinks",
            "severity": "error",
            "title": f"Only {profile['referring_domains']} referring domains",
            "detail": "Too few for any competitive term.",
            "how": "Finish the foundation tier before spending time on editorial outreach.",
            "affected": profile["referring_domains"],
            "examples": [], "category": "backlinks", "can_ask_ai": True,
        })

    if profile["toxic_links"]:
        fixes.append({
            "id": "links:toxic",
            "kind": "backlinks",
            "severity": "warning",
            "title": f"{profile['toxic_links']} link(s) score high on toxicity",
            "detail": "Links from domains with spam markers, very low authority or a paid-link footprint.",
            "how": "Request removal first. Disavow only what you cannot get removed.",
            "affected": profile["toxic_links"],
            "examples": [], "category": "backlinks", "can_ask_ai": True,
        })

    for warning in profile["anchor_health"]["warnings"]:
        fixes.append({
            "id": f"links:anchor:{abs(hash(warning)) % 10000}",
            "kind": "backlinks", "severity": "warning",
            "title": "Anchor distribution risk", "detail": warning,
            "how": "Correct it with the anchor mix on your next campaign, not retroactively.",
            "affected": 0, "examples": [], "category": "backlinks", "can_ask_ai": True,
        })

    if geo["prompts_tracked"] and geo["runs"] == 0:
        fixes.append({
            "id": "ai:unmeasured", "kind": "ai", "severity": "warning",
            "title": "AI visibility has never been measured",
            "detail": "Prompts exist but no engine is configured, so there is no baseline.",
            "how": (
                "Add one API key (Perplexity is the most informative because it returns its "
                "sources) and run the prompt set."
            ),
            "affected": geo["prompts_tracked"], "examples": [], "category": "ai-readiness",
            "can_ask_ai": False,
        })
    elif geo["runs"] and geo["mention_rate"] < 0.2:
        fixes.append({
            "id": "ai:invisible", "kind": "ai", "severity": "error",
            "title": f"Named in only {geo['mention_rate']:.0%} of AI answers",
            "detail": "Assistants do not know this brand well enough to recommend it.",
            "how": (
                "Get listed and reviewed on the review platforms, publish original data on your "
                "own domain, and answer real questions where the models read."
            ),
            "affected": geo["prompts_tracked"], "examples": [], "category": "ai-readiness",
            "can_ask_ai": True,
        })

    fixes.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), -f["affected"]))
    for i, fix in enumerate(fixes, start=1):
        fix["priority"] = i
    return fixes


def _immediate_backlinks(db: Session, *, project: Project) -> dict:
    """Which links are available right now, grouped by how soon you can have them."""
    rows = list(
        db.execute(
            select(LinkOpportunity)
            .where(
                LinkOpportunity.project_id == project.id,
                LinkOpportunity.status.in_([
                    OpportunityStatus.new.value,
                    OpportunityStatus.qualified.value,
                    OpportunityStatus.queued.value,
                ]),
            )
            .order_by(LinkOpportunity.score.desc())
            .limit(400)
        ).scalars()
    )

    def row(o: LinkOpportunity) -> dict:
        meta = o.meta_json or {}
        return {
            "id": o.id,
            "domain": o.target_domain,
            "name": meta.get("source_name") or o.target_domain,
            "url": o.target_url,
            "authority": o.authority,
            "score": o.score,
            "effort": o.effort,
            "tactic": o.tactic,
            "link_type": meta.get("link_type", "unknown"),
            "anchor": o.suggested_anchor,
            "requires_account": meta.get("requires_account", True),
            "required_fields": meta.get("required_fields", []),
            "ai_weight": meta.get("llm_citation_weight", 0.0),
            "notes": o.notes,
            "status": o.status,
        }

    now = [row(o) for o in rows if o.effort <= IMMEDIATE_EFFORT]
    soon = [row(o) for o in rows if o.effort == 3]
    campaign = [row(o) for o in rows if o.effort >= 4]

    dofollow_now = [r for r in now if r["link_type"] == "dofollow"]
    return {
        "now": now[:120],
        "soon": soon[:80],
        "campaign": campaign[:60],
        "summary": {
            "available_now": len(now),
            "dofollow_now": len(dofollow_now),
            "avg_authority_now": round(
                sum(r["authority"] for r in now) / len(now), 1
            ) if now else 0.0,
            "highest_authority_now": max((r["authority"] for r in now), default=0.0),
            "estimated_hours": round(sum(r["effort"] * 0.35 for r in now), 1),
        },
        "explanation": (
            "'Now' means effort 1-2: a form you can fill in today. 'Soon' needs an account or "
            "review. 'Campaign' needs content or a relationship first."
        ),
    }
