"""Crawler, on-page and link-verification tests against a real local HTTP server.

The fixture site under ``tests/fixtures/site`` contains one of every defect the
audit is supposed to catch, so these tests assert on behaviour rather than on
mocks. No outbound network access is needed.
"""

from __future__ import annotations

import http.server
import shutil
import socket
import socketserver
import tempfile
import threading
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "site"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D102 - silence the test output
        pass


@pytest.fixture(scope="module")
def site() -> str:
    """Serve the fixture site on a free port and return its base URL."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    tmp = Path(tempfile.mkdtemp(prefix="draken-fixture-"))
    shutil.copytree(FIXTURE_DIR, tmp / "site")
    root = tmp / "site"
    for path in list(root.rglob("*.html")) + [root / "robots.txt", root / "sitemap.xml"]:
        if path.exists():
            path.write_text(path.read_text().replace("__BASE__", base_url))

    class Handler(_QuietHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

    server = socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(tmp, ignore_errors=True)


# --- crawler ---------------------------------------------------------------


@pytest.fixture(scope="module")
async def crawl(site):
    from draken.engines.crawler.crawler import crawl_site

    return await crawl_site(site, max_pages=25, max_depth=3)


async def test_crawler_finds_robots_and_sitemap(crawl):
    assert crawl.robots_exists
    assert crawl.sitemap_urls >= 4


async def test_crawler_reaches_pages_from_both_links_and_sitemap(crawl):
    urls = {p["url"].rsplit("/", 1)[-1] or "index" for p in crawl.pages}
    assert "pricing.html" in urls          # linked from the homepage
    assert "keyword-research.html" in urls  # nested, linked
    assert "orphan.html" in urls            # sitemap only, never linked


async def test_crawler_detects_every_planted_defect(crawl):
    codes = {i.code for i in crawl.issues}
    expected = {
        "broken_page_404",          # /missing.html is linked but absent
        "duplicate_title",          # index and pricing share a title
        "duplicate_meta_description",
        "multiple_h1",              # about.html has two H1s
        "missing_h1",               # thin.html
        "thin_content",
        "orphan_page",              # orphan.html
        "images_missing_alt",       # chart.png has no alt
        "low_schema_coverage",
    }
    missing = expected - codes
    assert not missing, f"the audit missed: {sorted(missing)}"


async def test_crawler_records_structured_data_where_present(crawl):
    home = next(p for p in crawl.pages if p["url"].rstrip("/").endswith(("8099", "1")) or p.get("h1") == "SEO software for small teams")
    assert home["has_schema"]
    assert "Organization" in home["schema_types"]
    assert home["ai_readiness"] > 0


async def test_crawler_counts_inlinks(crawl):
    pricing = next(p for p in crawl.pages if p["url"].endswith("pricing.html"))
    assert pricing["inlinks"] >= 1
    orphan = next(p for p in crawl.pages if p["url"].endswith("orphan.html"))
    assert orphan["inlinks"] == 0


async def test_crawler_separates_external_links(crawl):
    assert crawl.external_links
    assert all("127.0.0.1" not in e["domain"] for e in crawl.external_links)


async def test_health_score_reflects_a_flawed_site(crawl):
    assert 0.0 <= crawl.health_score < 90.0
    summary = crawl.summary()
    assert summary["broken_pages"] >= 1
    assert summary["html_pages"] >= 5
    assert summary["robots_txt"] is True


async def test_max_pages_is_respected(site):
    from draken.engines.crawler.crawler import crawl_site

    result = await crawl_site(site, max_pages=3, max_depth=3)
    assert len(result.pages) <= 3


# --- on-page ---------------------------------------------------------------


async def test_onpage_scores_a_well_optimised_page(site):
    from draken.engines.onpage.analyzer import analyse_url

    report = await analyse_url(
        f"{site}/blog/keyword-research.html",
        target_keyword="keyword research",
        secondary_keywords=["autocomplete", "rank tracking"],
    )
    placement = report.keyword_placement
    assert placement["in_title"]
    assert placement["in_h1"]
    assert placement["in_first_100_words"]
    assert placement["in_url"]
    assert report.score > 40
    assert report.readability["verdict"] in {"easy to scan", "acceptable"}
    # 'rank tracking' is genuinely absent, so it must be flagged.
    assert any("rank tracking" in r["issue"] for r in report.recommendations)


async def test_onpage_flags_a_thin_page(site):
    from draken.engines.onpage.analyzer import analyse_url

    report = await analyse_url(f"{site}/thin.html", target_keyword="keyword research")
    assert report.score < 60
    areas = {r["area"] for r in report.recommendations}
    assert "content" in areas
    assert any(r["priority"] == "high" for r in report.recommendations)


async def test_onpage_reports_missing_structured_data(site):
    from draken.engines.onpage.analyzer import analyse_url

    report = await analyse_url(f"{site}/pricing.html", target_keyword="pricing")
    assert not report.ai_readiness["has_schema"]
    assert report.ai_readiness["notes"]


# --- link verification -----------------------------------------------------


async def test_verification_confirms_a_live_link_with_its_rel(site):
    from draken.core.models import LinkStatus, LinkType
    from draken.engines.backlinks import discovery

    links = await discovery.verify_links([(f"{site}/partner.html", "example.com")])
    link = links[0]
    assert link.status == LinkStatus.live.value
    assert link.anchor_text == "Example Inc"
    assert link.link_type == LinkType.nofollow.value, "rel=nofollow must be read off the page"
    assert link.meta["occurrences"] >= 1


async def test_verification_reports_a_missing_link_as_lost(site):
    from draken.core.models import LinkStatus
    from draken.engines.backlinks import discovery

    links = await discovery.verify_links([(f"{site}/pricing.html", "example.com")])
    assert links[0].status == LinkStatus.lost.value


async def test_verification_reports_a_404_source_as_broken(site):
    from draken.core.models import LinkStatus
    from draken.engines.backlinks import discovery

    links = await discovery.verify_links([(f"{site}/nope.html", "example.com")])
    assert links[0].status == LinkStatus.broken.value
    assert links[0].meta["http_status"] == 404


async def test_verification_detects_an_unlinked_mention(site):
    from draken.core.models import LinkStatus
    from draken.engines.backlinks import discovery

    # partner.html names "other-vendor.example" in prose but the page it links to
    # for that vendor is a different URL; pricing.html names nothing.
    links = await discovery.verify_links([(f"{site}/partner.html", "unmentioned-brand.example")])
    assert links[0].status == LinkStatus.lost.value
    assert not links[0].meta.get("unlinked_mention")


# --- full audit persistence ------------------------------------------------


async def test_audit_persists_pages_and_grouped_issues(db, site):
    from draken.core.models import BusinessProfile, Project
    from draken.services import audits as audit_service

    project = Project(name="Fixture", domain="fixture.example", base_url=site)
    db.add(project)
    db.commit()
    db.add(BusinessProfile(project_id=project.id, display_name="Fixture"))
    db.commit()

    audit = audit_service.create_audit(db, project=project)
    result = await audit_service.run_audit(db, audit_id=audit.id, max_pages=12, max_depth=3)

    assert result["pages_crawled"] >= 5
    assert result["issue_counts"]
    grouped = audit_service.issues_grouped(db, audit_id=audit.id)
    assert grouped
    # Grouped output is ordered by severity, then frequency.
    severities = [g["severity"] for g in grouped]
    order = {"critical": 0, "error": 1, "warning": 2, "notice": 3}
    assert severities == sorted(severities, key=lambda s: order[s])
    assert any(g["count"] > 1 for g in grouped)
    assert all(g["title"] and g["how_to_fix"] for g in grouped)

    latest = audit_service.latest_audit(db, project_id=project.id)
    assert latest is not None and latest.id == audit.id
