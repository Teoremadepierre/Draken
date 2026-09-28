"""API contract tests. No network: every endpoint exercised here works offline."""

from __future__ import annotations


def test_health_reports_capabilities(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "serp_provider" in body
    assert body["submissions"]["dry_run"] is True
    assert "site_audit" in body["job_kinds"]


def test_client_config_exposes_deployment_flags(client):
    body = client.get("/api/config").json()
    for key in (
        "auth_enabled", "serp_provider", "ai_engines_configured",
        "submissions_dry_run", "outreach_send_enabled",
    ):
        assert key in body


def test_project_lifecycle(client):
    created = client.post("/api/projects", json={
        "name": "Acme SEO", "domain": "https://www.acme.example/",
        "country": "es", "language": "ES", "industry": "software",
        "competitors": ["https://competitor-one.example/x"],
        "brand_terms": ["Acme SEO"],
    })
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["domain"] == "acme.example", "domain should be normalised"
    assert project["country"] == "ES"
    assert project["competitors"] == ["competitor-one.example"]
    pid = project["id"]

    assert client.get("/api/projects").json()[0]["id"] == pid
    assert client.get(f"/api/projects/{pid}").json()["name"] == "Acme SEO"

    patched = client.patch(f"/api/projects/{pid}", json={"industry": "saas"})
    assert patched.json()["industry"] == "saas"

    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_duplicate_domain_is_rejected(client):
    payload = {"name": "A", "domain": "dup.example"}
    assert client.post("/api/projects", json=payload).status_code == 201
    r = client.post("/api/projects", json=payload)
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_unparseable_domain_is_rejected(client):
    r = client.post("/api/projects", json={"name": "A", "domain": "   "})
    assert r.status_code == 422


def test_new_project_gets_a_scored_opportunity_queue(client):
    pid = client.post("/api/projects", json={
        "name": "Acme", "domain": "acme2.example", "country": "ES",
        "language": "es", "industry": "software",
    }).json()["id"]

    opportunities = client.get(f"/api/projects/{pid}/opportunities").json()
    assert len(opportunities) > 50, "catalog should seed a real work queue immediately"
    scores = [o["score"] for o in opportunities]
    assert scores == sorted(scores, reverse=True)
    assert all(0 <= s <= 100 for s in scores)
    top = opportunities[0]
    assert top["suggested_anchor"]
    assert set(top["score_breakdown"]) >= {"authority", "relevance", "ease", "follow"}


def test_source_catalog_endpoints(client):
    stats = client.get("/api/sources/stats").json()
    assert stats["total"] >= 300
    assert stats["dofollow"] > 0
    assert stats["by_category"]

    dofollow = client.get("/api/sources", params={"only_dofollow": True, "limit": 50}).json()
    assert dofollow and all(s["link_type"] == "dofollow" for s in dofollow)

    easy = client.get("/api/sources", params={"max_effort": 2, "limit": 100}).json()
    assert easy and all(s["effort"] <= 2 for s in easy)

    spanish = client.get("/api/sources", params={"country": "ES", "limit": 200}).json()
    assert spanish

    playbook = client.get("/api/sources/playbook").json()["tactics"]
    assert playbook and any("mention" in t["slug"] for t in playbook)


def test_business_profile_round_trip_and_completeness(client):
    pid = client.post("/api/projects", json={"name": "Acme", "domain": "acme3.example"}).json()["id"]

    blank = client.get(f"/api/projects/{pid}/profile/completeness").json()
    assert blank["completeness"] < 1.0
    assert blank["missing_fields"]

    client.put(f"/api/projects/{pid}/profile", json={
        "display_name": "Acme SEO", "short_description": "SEO software.",
        "long_description": "A longer description of the product.",
        "website": "https://acme3.example", "email": "hola@acme3.example",
        "phone": "+34 910 000 000", "city": "Madrid", "country": "ES",
        "categories": ["SEO software"], "logo_url": "https://acme3.example/logo.png",
    })
    full = client.get(f"/api/projects/{pid}/profile/completeness").json()
    assert full["completeness"] == 1.0
    assert full["ready_for_submissions"] is True


def test_keyword_flow_without_network(client):
    pid = client.post("/api/projects", json={
        "name": "Acme", "domain": "acme4.example", "language": "en",
    }).json()["id"]

    research = client.post(
        f"/api/projects/{pid}/keywords/research",
        json={"seeds": ["seo software", "keyword tool"], "max_results": 80,
              "use_live_suggest": False},
    )
    assert research.status_code == 200, research.text
    assert research.json()["created"] > 20

    keywords = client.get(f"/api/projects/{pid}/keywords", params={"limit": 20}).json()
    assert keywords
    assert [k["opportunity_score"] for k in keywords] == sorted(
        (k["opportunity_score"] for k in keywords), reverse=True
    )

    by_volume = client.get(
        f"/api/projects/{pid}/keywords", params={"sort": "volume", "limit": 10}
    ).json()
    assert [k["volume"] for k in by_volume] == sorted(
        (k["volume"] for k in by_volume), reverse=True
    )

    clusters = client.post(f"/api/projects/{pid}/clusters/rebuild").json()
    assert clusters["clusters"] >= 2
    assert clusters["topics"]

    listed = client.get(f"/api/projects/{pid}/clusters").json()
    assert listed and listed[0]["recommended_page_type"]

    # Track the top keywords, then confirm the overview reflects it.
    ids = [k["id"] for k in keywords[:5]]
    tracked = client.post(f"/api/projects/{pid}/keywords/track-bulk", json=ids).json()
    assert tracked["updated"] == 5
    overview = client.get(f"/api/projects/{pid}/rankings/overview").json()
    assert overview["tracked_keywords"] == 5


def test_manual_keyword_add_is_idempotent(client):
    pid = client.post("/api/projects", json={"name": "A", "domain": "acme5.example"}).json()["id"]
    first = client.post(f"/api/projects/{pid}/keywords",
                        json={"terms": ["seo audit", "seo audit"], "track": True}).json()
    assert first["created"] == 1
    second = client.post(f"/api/projects/{pid}/keywords", json={"terms": ["seo audit"]}).json()
    assert second["created"] == 0 and second["skipped"] == 1


def test_backlink_import_and_profile(client):
    pid = client.post("/api/projects", json={
        "name": "Acme", "domain": "acme6.example", "brand_terms": ["Acme"],
    }).json()["id"]

    csv_text = (
        "Referring Page URL;Anchor;Domain Rating;Type\n"
        "https://good-blog.example/review;Acme;71;dofollow\n"
        "https://directory.example/listing;acme6.example;45;nofollow\n"
        "https://buy-cheap-seo-links.xyz/p?replytocom=2;buy cheap backlinks;4;dofollow\n"
    )
    imported = client.post(f"/api/projects/{pid}/backlinks/import",
                           json={"csv_text": csv_text}).json()
    assert imported["imported"] == 3

    profile = client.get(f"/api/projects/{pid}/backlinks/profile").json()
    assert profile["referring_domains"] == 3
    assert profile["dofollow_links"] == 2
    assert profile["toxic_links"] == 1
    assert profile["recommendations"]
    buckets = {r["bucket"]: r["count"] for r in profile["anchor_distribution"]}
    assert buckets["branded"] >= 1
    assert buckets["naked_url"] >= 1

    toxic = client.get(f"/api/projects/{pid}/backlinks/toxic").json()
    assert toxic["count"] == 1
    assert toxic["links"][0]["recommended_action"] in {"disavow", "request_removal"}
    assert toxic["links"][0]["reasons"]

    disavow = client.get(f"/api/projects/{pid}/backlinks/disavow")
    assert disavow.status_code == 200
    assert "buy-cheap-seo-links.xyz" in disavow.text
    assert disavow.text.startswith("# Disavow file")


def test_manual_backlink_add_and_delete(client):
    pid = client.post("/api/projects", json={"name": "A", "domain": "acme7.example"}).json()["id"]
    added = client.post(f"/api/projects/{pid}/backlinks", params={
        "source_url": "editorial.example/post", "anchor_text": "Acme",
        "link_type": "dofollow", "domain_authority": 70,
    }).json()
    assert added["source_domain"] == "editorial.example"

    duplicate = client.post(f"/api/projects/{pid}/backlinks",
                            params={"source_url": "https://editorial.example/post"})
    assert duplicate.status_code == 409

    assert client.delete(f"/api/projects/{pid}/backlinks/{added['id']}").status_code == 204


def test_opportunity_generation_filters_and_status_flow(client):
    pid = client.post("/api/projects", json={
        "name": "Acme", "domain": "acme8.example", "country": "ES",
        "language": "es", "industry": "software",
    }).json()["id"]

    generated = client.post(f"/api/projects/{pid}/opportunities/generate", json={
        "only_dofollow": True, "max_effort": 2, "limit": 40,
    }).json()
    assert generated["generated"] > 0

    dofollow_only = client.get(f"/api/projects/{pid}/opportunities",
                               params={"max_effort": 2, "limit": 100}).json()
    assert all(o["effort"] <= 2 for o in dofollow_only)

    opp = dofollow_only[0]
    updated = client.patch(f"/api/projects/{pid}/opportunities/{opp['id']}", json={
        "status": "qualified", "notes": "Good fit", "suggested_anchor": "Acme SEO",
    }).json()
    assert updated["status"] == "qualified"
    assert updated["notes"] == "Good fit"

    bad = client.patch(f"/api/projects/{pid}/opportunities/{opp['id']}",
                       json={"status": "not-a-status"})
    assert bad.status_code == 422

    pipeline = client.get(f"/api/projects/{pid}/opportunities/pipeline").json()
    assert pipeline["total"] > 0
    assert "qualified" in pipeline["by_status"]

    detail = client.get(f"/api/projects/{pid}/opportunities/{opp['id']}").json()
    assert detail["opportunity"]["id"] == opp["id"]
    assert detail["source"] is None or detail["source"]["slug"]


def test_submission_pipeline_requires_a_complete_profile(client):
    pid = client.post("/api/projects", json={"name": "Acme", "domain": "acme9.example"}).json()["id"]

    blocked = client.post(f"/api/projects/{pid}/submissions/prepare", json={"limit": 3}).json()
    assert blocked["prepared"] == 0
    assert any("complete" in m for m in blocked["messages"])

    client.put(f"/api/projects/{pid}/profile", json={
        "display_name": "Acme SEO", "short_description": "SEO software for small teams.",
        "long_description": "Longer description.", "website": "https://acme9.example",
        "email": "hola@acme9.example", "phone": "+34 910 000 000", "city": "Madrid",
        "country": "ES", "categories": ["SEO software"],
        "logo_url": "https://acme9.example/logo.png",
    })

    prepared = client.post(f"/api/projects/{pid}/submissions/prepare", json={"limit": 3}).json()
    assert prepared["prepared"] == 3
    submissions = prepared["submissions"]
    assert all(s["state"] == "awaiting_approval" for s in submissions)
    brief = submissions[0]["rendered_instructions"]
    assert "## Fields to enter" in brief
    assert "Acme SEO" in brief
    assert "## After submitting" in brief

    # Re-preparing must not duplicate work already queued.
    again = client.post(f"/api/projects/{pid}/submissions/prepare", json={
        "opportunity_ids": [s["opportunity_id"] for s in submissions],
    }).json()
    assert again["prepared"] == 0 and again["skipped"] == 3

    approved = client.post(f"/api/projects/{pid}/submissions/approve", json={
        "submission_ids": [s["id"] for s in submissions], "approved_by": "tester",
    }).json()
    assert approved["prepared"] == 3

    listed = client.get(f"/api/projects/{pid}/submissions",
                        params={"state": "approved"}).json()
    assert len(listed) == 3

    settings_body = client.get(f"/api/projects/{pid}/submissions/settings").json()
    assert settings_body["dry_run"] is True
    assert settings_body["require_approval"] is True


def test_recording_a_live_url_marks_the_link_won(client):
    pid = client.post("/api/projects", json={"name": "A", "domain": "acme10.example"}).json()["id"]
    client.put(f"/api/projects/{pid}/profile", json={
        "display_name": "Acme", "short_description": "s", "long_description": "l",
        "website": "https://acme10.example", "email": "a@acme10.example",
        "phone": "1", "city": "Madrid", "country": "ES", "categories": ["x"],
        "logo_url": "https://acme10.example/l.png",
    })
    sub = client.post(f"/api/projects/{pid}/submissions/prepare",
                      json={"limit": 1, "auto_approve": True}).json()["submissions"][0]

    recorded = client.post(
        f"/api/projects/{pid}/submissions/{sub['id']}/live-url",
        params={"live_url": "https://directory.example/acme"},
    ).json()
    assert recorded["live_url"] == "https://directory.example/acme"

    opp = client.get(f"/api/projects/{pid}/opportunities/{sub['opportunity_id']}").json()
    assert opp["opportunity"]["status"] == "won"


def test_campaign_crud_and_progress(client):
    pid = client.post("/api/projects", json={"name": "A", "domain": "acme11.example"}).json()["id"]
    campaign = client.post(f"/api/projects/{pid}/campaigns", json={
        "name": "Q4 foundation", "goal": "30 referring domains",
        "tactics": ["directory", "local_citation"], "monthly_link_target": 30,
    }).json()
    assert campaign["monthly_link_target"] == 30
    assert campaign["anchor_plan"]["branded"] > 0

    progress = client.get(f"/api/projects/{pid}/campaigns/{campaign['id']}/progress").json()
    assert progress["remaining_to_target"] == 30

    assert client.delete(f"/api/projects/{pid}/campaigns/{campaign['id']}").status_code == 204


def test_ai_visibility_endpoints_degrade_without_keys(client):
    pid = client.post("/api/projects", json={
        "name": "Acme", "domain": "acme12.example", "industry": "software",
        "language": "es", "competitors": ["competitor-one.example"],
    }).json()["id"]

    engines = client.get(f"/api/projects/{pid}/ai/engines").json()
    assert engines["any_configured"] is False
    assert engines["setup_hint"]

    generated = client.post(f"/api/projects/{pid}/ai/prompts/generate",
                            json={"limit": 15}).json()
    assert generated["created"] > 0
    assert all("{" not in p["prompt"] for p in generated["prompts"])

    prompts = client.get(f"/api/projects/{pid}/ai/prompts").json()
    assert prompts

    # Running without a configured engine must fail loudly, not silently.
    blocked = client.post(f"/api/projects/{pid}/ai/run", json={"limit": 5})
    assert blocked.status_code == 422
    assert "API key" in blocked.json()["detail"] or "configured" in blocked.json()["detail"]

    summary = client.get(f"/api/projects/{pid}/ai/summary").json()
    assert summary["prompts_tracked"] > 0
    assert summary["runs"] == 0
    assert summary["recommendations"]

    assert client.delete(f"/api/projects/{pid}/ai/prompts/{prompts[0]['id']}").status_code == 204


def test_geo_assets_are_generated(client):
    pid = client.post("/api/projects", json={
        "name": "Acme SEO", "domain": "acme13.example", "industry": "software",
    }).json()["id"]
    client.put(f"/api/projects/{pid}/profile", json={
        "display_name": "Acme SEO", "legal_name": "Acme Analytics SL",
        "tagline": "SEO for small teams", "short_description": "SEO software.",
        "long_description": "A self-serve SEO platform.", "categories": ["SEO software"],
        "email": "hola@acme13.example", "phone": "+34 910 000 000",
        "street": "Gran Via 1", "city": "Madrid", "postal_code": "28013",
        "country": "ES", "founded_year": 2024, "logo_url": "https://acme13.example/l.png",
        "website": "https://acme13.example",
        "social_profiles": {"linkedin": "https://linkedin.com/company/acme"},
    })

    assets = client.get(f"/api/projects/{pid}/ai/assets").json()
    assert assets["llms_txt"].startswith("# Acme SEO")
    assert "Madrid" in assets["llms_txt"]
    assert assets["schema"]["organization"]["@type"] == "LocalBusiness"
    assert assets["schema"]["script_tag"].startswith("<script")
    assert assets["profile_gaps"] == []

    download = client.get(f"/api/projects/{pid}/ai/assets/llms.txt")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/plain")

    consistency = client.post(f"/api/projects/{pid}/ai/entity-consistency", json=[
        {"source": "yelp.com", "name": "Acme SEO", "phone": "+34 910 000 000"},
        {"source": "hotfrog.com", "name": "Acme S.E.O.", "phone": "+34 911 111 111"},
    ]).json()
    assert consistency["listings_checked"] == 2
    assert consistency["mismatches"]


def test_onpage_endpoint_handles_an_unreachable_url(client):
    pid = client.post("/api/projects", json={"name": "A", "domain": "acme14.example"}).json()["id"]
    report = client.post(f"/api/projects/{pid}/onpage", json={
        "url": "http://127.0.0.1:9/nothing-here", "target_keyword": "seo",
    }).json()
    assert report["error"]
    assert report["recommendations"][0]["area"] == "availability"


def test_outreach_drafting_flags_placeholders(client):
    pid = client.post("/api/projects", json={
        "name": "Acme SEO", "domain": "acme15.example", "language": "en",
    }).json()["id"]
    client.put(f"/api/projects/{pid}/profile", json={
        "display_name": "Acme SEO", "short_description": "SEO software.",
        "email": "hola@acme15.example",
    })
    opp = client.get(f"/api/projects/{pid}/opportunities", params={"limit": 1}).json()[0]

    drafted = client.post(f"/api/projects/{pid}/outreach/draft", json={
        "opportunity_ids": [opp["id"]], "tactic": "resource_page",
        "sender_name": "Ada", "sender_role": "Head of SEO",
    }).json()
    assert drafted["drafted"] == 1
    message = drafted["messages"][0]
    assert "Ada" in message["body"] or "Acme SEO" in message["body"]
    # The template has fields only a human can fill; they must be surfaced.
    assert message["unresolved_variables"]
    assert not message["ready_to_send"]

    listed = client.get(f"/api/projects/{pid}/outreach/messages").json()
    assert len(listed) == 1

    edited = client.patch(
        f"/api/projects/{pid}/outreach/messages/{message['message_id']}",
        params={"subject": "Personalised subject", "to_email": "editor@site.example"},
    ).json()
    assert edited["subject"] == "Personalised subject"

    # Sending is disabled by default: the endpoint must refuse rather than pretend.
    send = client.post(
        f"/api/projects/{pid}/outreach/messages/{message['message_id']}/send"
    ).json()
    assert send["sent"] is False
    assert "disabled" in send["detail"].lower()


def test_outreach_template_library_is_exposed(client):
    body = client.get("/api/outreach/templates").json()
    assert body["templates"]
    assert "unlinked_mention" in body["tactics"]
    assert all("variables" in t for t in body["templates"])


def test_project_overview_assembles_every_module(client):
    pid = client.post("/api/projects", json={
        "name": "Acme", "domain": "acme16.example", "industry": "software",
    }).json()["id"]

    overview = client.get(f"/api/projects/{pid}/overview").json()
    for section in (
        "project", "counts", "site_health", "link_profile",
        "rankings", "pipeline", "ai_visibility", "next_actions",
    ):
        assert section in overview, f"missing {section}"
    assert overview["counts"]["opportunities"] > 0
    assert overview["counts"]["referring_domains"] == 0
    # With no links at all, the first action must be the foundation tier.
    assert overview["next_actions"]
    assert any("no backlinks" in a["action"] for a in overview["next_actions"])


def test_job_endpoints(client):
    pid = client.post("/api/projects", json={"name": "A", "domain": "acme17.example"}).json()["id"]
    kinds = client.get("/api/jobs/kinds").json()["kinds"]
    assert "site_audit" in kinds and "full_sweep" in kinds

    bad = client.post(f"/api/projects/{pid}/jobs/not-a-real-job")
    assert bad.status_code == 422

    assert client.get("/api/jobs").status_code == 200
    assert client.get("/api/jobs/999999").status_code == 404
    assert client.get(f"/api/projects/{pid}/activity").json() == []


def test_audit_endpoints_before_any_run(client):
    pid = client.post("/api/projects", json={"name": "A", "domain": "acme18.example"}).json()["id"]
    latest = client.get(f"/api/projects/{pid}/audits/latest").json()
    assert latest["audit"] is None
    assert "No audit yet" in latest["message"]
    assert client.get(f"/api/projects/{pid}/audits").json() == []


def test_cross_project_access_is_blocked(client):
    a = client.post("/api/projects", json={"name": "A", "domain": "one.example"}).json()["id"]
    b = client.post("/api/projects", json={"name": "B", "domain": "two.example"}).json()["id"]

    opp_b = client.get(f"/api/projects/{b}/opportunities", params={"limit": 1}).json()[0]
    # Project A must not be able to read project B's opportunity.
    assert client.get(f"/api/projects/{a}/opportunities/{opp_b['id']}").status_code == 404


def test_dashboard_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
