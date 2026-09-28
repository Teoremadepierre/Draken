"""Scanner, real-data status, diagnostics, assistant, users and sharing.

No outbound network is needed: the connectivity probes are allowed to fail, which
is itself what the diagnostics are meant to report.
"""

from __future__ import annotations

import pytest

# --- domain normalisation regressions ------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://127.0.0.1:8177/", "127.0.0.1"),
        ("192.168.1.50:3000", "192.168.1.50"),
        ("localhost:8000", "localhost"),
        ("[::1]:8080", "::1"),
        ("http://[2001:db8::1]:443/x", "2001:db8::1"),
        ("https://user:pw@example.com:8443/x", "example.com"),
    ],
)
def test_ip_and_port_hosts_are_not_mangled(raw, expected):
    """An IP literal is the whole host: "127.0.0.1" must not become "0.1"."""
    from draken.core.urls import normalize_domain

    assert normalize_domain(raw) == expected


# --- SERP provider selection ---------------------------------------------


def test_provider_availability_lists_keyless_engines():
    from draken.engines.serp import fetcher

    available = fetcher.provider_availability()
    assert available["duckduckgo_html"] is True
    assert available["mojeek"] is True
    assert available["serpapi"] is False


def test_fallback_chain_starts_with_the_active_provider():
    from draken.engines.serp import fetcher

    chain = fetcher.fallback_chain()
    assert chain[0] == fetcher.active_provider()
    assert len(chain) == len(set(chain)), "no provider should appear twice"
    assert all(name in fetcher._PROVIDERS for name in chain)


def test_pinned_provider_is_honoured(monkeypatch):
    from draken.core.config import settings
    from draken.engines.serp import fetcher

    monkeypatch.setattr(settings, "serp_provider", "mojeek")
    assert fetcher.active_provider() == "mojeek"

    # A pin that is not available falls back rather than breaking.
    monkeypatch.setattr(settings, "serp_provider", "serpapi")
    assert fetcher.active_provider() != "serpapi"


# --- real data status ----------------------------------------------------


def test_data_quality_reports_level_one_with_no_keys(db):
    from draken.services import realdata

    status = realdata.data_sources_status(db)
    assert status["quality"]["level"] == 1
    assert status["quality"]["label"] == "estimated"
    assert len(status["quality"]["missing"]) == 3
    assert status["serp_active"]


def test_data_quality_rises_when_search_console_is_configured(db, monkeypatch, tmp_path):
    from draken.core.config import settings
    from draken.services import realdata

    key = tmp_path / "sa.json"
    key.write_text("{}")
    monkeypatch.setattr(settings, "gsc_service_account_file", str(key))

    status = realdata.data_sources_status(db)
    assert status["first_party"]["search_console"] is True
    assert status["quality"]["level"] >= 3


def test_providers_report_their_own_configuration_hints():
    from draken.engines.providers import bing_webmaster, search_console

    assert not search_console.is_configured()
    assert "DRAKEN_GSC" in search_console.configuration_hint()
    assert not bing_webmaster.is_configured()
    assert "DRAKEN_BING_WEBMASTER_API_KEY" in bing_webmaster.configuration_hint()


async def test_search_console_import_refuses_cleanly_when_unconfigured(db, project):
    from draken.services import realdata

    result = await realdata.import_search_console(db, project=project)
    assert result["configured"] is False
    assert result["imported"] == 0
    assert "DRAKEN_GSC" in result["error"]


# --- diagnostics ---------------------------------------------------------


async def test_connectivity_check_reports_every_probe():
    from draken.services import diagnostics

    result = await diagnostics.run_connectivity_check(timeout=3.0)
    assert result["total"] >= 6
    assert len(result["probes"]) == result["total"]
    assert result["severity"] in {"good", "warn", "bad"}
    for probe in result["probes"]:
        assert probe["name"] and probe["host"]
        assert probe["enables"]
        assert isinstance(probe["reachable"], bool)


async def test_blocked_hosts_name_the_features_they_disable():
    from draken.services import diagnostics

    result = await diagnostics.run_connectivity_check(timeout=3.0)
    if result["blocked"]:
        assert result["disabled_features"], "a blocked host must say what it disables"
        for entry in result["disabled_features"]:
            assert entry["feature"] and entry["because"]
        assert result["general_remediation"]


# --- scanner -------------------------------------------------------------


async def test_ensure_project_creates_and_reuses(db):
    from draken.services import scanner

    project, created = await scanner.ensure_project(db, url="https://scan-demo.example/x")
    assert created is True
    assert project.domain == "scan-demo.example"

    again, created_again = await scanner.ensure_project(db, url="http://www.scan-demo.example/")
    assert created_again is False
    assert again.id == project.id


async def test_ensure_project_rejects_an_unparseable_url(db):
    from draken.services import scanner

    with pytest.raises(ValueError):
        await scanner.ensure_project(db, url="   ")


def test_report_shape_before_any_scan(db, project):
    from draken.services import scanner

    report = scanner.build_report(db, project=project)
    for key in ("project", "scores", "headline", "fixes", "backlinks",
                "link_profile", "ai_visibility", "data_sources"):
        assert key in report
    assert report["scores"]["overall"] is not None
    assert isinstance(report["fixes"], list)


def test_report_flags_a_site_with_no_backlinks(db, project):
    from draken.services import scanner

    report = scanner.build_report(db, project=project)
    ids = [f["id"] for f in report["fixes"]]
    assert "links:none" in ids
    top = report["fixes"][0]
    assert top["severity"] == "critical"
    assert top["priority"] == 1


def test_immediate_backlinks_group_by_effort(db, project):
    from draken.services import opportunities as opportunity_service
    from draken.services import scanner

    opportunity_service.generate_from_catalog(db, project=project, limit=300)
    report = scanner.build_report(db, project=project)
    links = report["backlinks"]

    assert links["summary"]["available_now"] > 0
    assert all(r["effort"] <= 2 for r in links["now"])
    assert all(r["effort"] == 3 for r in links["soon"])
    assert all(r["effort"] >= 4 for r in links["campaign"])
    assert links["summary"]["highest_authority_now"] >= links["summary"]["avg_authority_now"]
    assert links["explanation"]


def test_industry_detection_needs_two_signals():
    from draken.services.scanner import _guess_industry

    assert _guess_industry("nuestra plataforma software con api y dashboard") == "software"
    assert _guess_industry("una sola palabra software") == ""


# --- assistant -----------------------------------------------------------


def test_brief_is_self_contained_and_carries_the_finding(db, project):
    from draken.services import assistant

    context = assistant.project_context(db, project=project)
    brief = assistant.build_brief(
        context=context,
        finding={"code": "missing_h1", "severity": "error", "affected_pages": 3},
        language="es",
    )
    assert "acme.example" in brief
    assert "missing_h1" in brief
    assert "Contexto del sitio" in brief
    # It must tell the model not to invent data, since it will be pasted elsewhere.
    assert "No inventes" in brief
    assert "comprar enlaces" in brief


def test_brief_switches_language():
    from draken.services import assistant

    brief = assistant.build_brief(context={"site": "x"}, question="", language="en")
    assert "Site context" in brief
    assert "Do not invent" in brief


async def test_assistant_returns_the_brief_when_no_engine_is_configured(db, project):
    from draken.services import assistant

    assert assistant.available() is False
    result = await assistant.ask(db, project=project, finding_id="", language="es")
    assert result["answered"] is False
    assert result["brief"]
    assert "Claude" in result["reason"]


def test_finding_context_degrades_for_an_unknown_id(db, project):
    from draken.services import assistant

    assert assistant.finding_context(db, project=project, finding_id="links:none") == {
        "finding_id": "links:none"
    }


# --- users ---------------------------------------------------------------


def test_bootstrap_owner_is_created_once(db):
    from draken.services import accounts

    first = accounts.ensure_bootstrap_owner(db)
    second = accounts.ensure_bootstrap_owner(db)
    assert first is not None
    assert first.id == second.id
    assert first.role == "owner"


def test_invite_creates_an_inactive_user_with_a_token(db):
    from draken.services import accounts

    invite = accounts.invite_user(db, username="pierre", role="editor", invited_by="admin")
    assert invite["invite_path"].startswith("/invite/")

    user = accounts.get_user(db, "pierre")
    assert user.is_active is False
    assert user.invite_token
    assert not user.password_hash


def test_invite_rejects_duplicates_and_bad_roles(db):
    from draken.services import accounts

    accounts.invite_user(db, username="pierre")
    with pytest.raises(ValueError):
        accounts.invite_user(db, username="pierre")
    with pytest.raises(ValueError):
        accounts.invite_user(db, username="otro", role="superuser")


def test_accepting_an_invite_activates_the_account_once(db):
    from draken.services import accounts

    invite = accounts.invite_user(db, username="pierre")
    token = invite["invite_path"].split("/")[-1]

    user = accounts.accept_invite(db, token=token, password="unaclavelarga")
    assert user is not None
    assert user.is_active is True
    assert user.password_hash
    assert not user.invite_token

    # The token is single use.
    assert accounts.accept_invite(db, token=token, password="otraclavelarga") is None


def test_accepting_an_invite_enforces_a_minimum_password(db):
    from draken.services import accounts

    invite = accounts.invite_user(db, username="pierre")
    token = invite["invite_path"].split("/")[-1]
    with pytest.raises(ValueError):
        accounts.accept_invite(db, token=token, password="corta")


def test_authentication_uses_the_user_row(db):
    from draken.services import accounts

    invite = accounts.invite_user(db, username="pierre")
    accounts.accept_invite(
        db, token=invite["invite_path"].split("/")[-1], password="unaclavelarga"
    )
    assert accounts.authenticate(db, username="pierre", password="unaclavelarga") is not None
    assert accounts.authenticate(db, username="pierre", password="incorrecta") is None


def test_the_last_owner_cannot_be_deleted(db):
    from draken.services import accounts

    owner = accounts.ensure_bootstrap_owner(db)
    with pytest.raises(ValueError):
        accounts.delete_user(db, user_id=owner.id)


def test_role_permissions_are_ordered(db):
    from draken.core.models import User
    from draken.services import accounts

    viewer = User(username="v", role="viewer")
    editor = User(username="e", role="editor")
    owner = User(username="o", role="owner")

    assert accounts.can(viewer, "read") and not accounts.can(viewer, "write")
    assert accounts.can(editor, "write") and not accounts.can(editor, "admin")
    assert accounts.can(owner, "admin")
    assert accounts.can(None, "admin"), "auth disabled means no restriction"


# --- sharing -------------------------------------------------------------


def test_share_link_round_trip(db, project):
    from draken.services import accounts

    link = accounts.create_share_link(db, project=project, label="Para Pierre", created_by="admin")
    assert link.is_valid

    resolved, resolved_project = accounts.resolve_share_link(db, token=link.token)
    assert resolved is not None
    assert resolved_project.id == project.id
    assert resolved.view_count == 1


def test_revoked_and_expired_links_stop_resolving(db, project):
    from datetime import UTC, datetime, timedelta

    from draken.services import accounts

    link = accounts.create_share_link(db, project=project)
    accounts.revoke_share_link(db, link_id=link.id)
    assert accounts.resolve_share_link(db, token=link.token) == (None, None)

    expired = accounts.create_share_link(db, project=project, valid_days=1)
    expired.expires_at = datetime.now(UTC) - timedelta(days=2)
    db.commit()
    assert accounts.resolve_share_link(db, token=expired.token) == (None, None)


def test_unknown_token_does_not_resolve(db):
    from draken.services import accounts

    assert accounts.resolve_share_link(db, token="nope") == (None, None)


# --- API -----------------------------------------------------------------


def test_scan_endpoint_creates_the_project_and_queues_a_job(client):
    response = client.post("/api/scan", json={
        "url": "https://scan-api.example/", "max_pages": 10,
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project_created"] is True
    assert body["domain"] == "scan-api.example"
    assert body["job_id"]
    assert "audit" in body["stages"]


def test_scan_endpoint_rejects_a_bad_url(client):
    assert client.post("/api/scan", json={"url": "  "}).status_code == 422


def test_report_endpoint_returns_the_full_shape(client):
    pid = client.post("/api/projects", json={
        "name": "Acme", "domain": "report-api.example", "industry": "software",
    }).json()["id"]
    report = client.get(f"/api/scan/{pid}/report").json()
    assert report["headline"]["backlinks_available_now"] > 0
    assert report["scores"]["data_quality"]["level"] == 1


def test_data_sources_endpoint(client):
    body = client.get("/api/system/data-sources").json()
    assert body["quality"]["level"] >= 1
    assert "serp_providers" in body
    assert "first_party" in body


def test_connectivity_endpoint(client):
    body = client.get("/api/system/connectivity").json()
    assert body["total"] >= 6
    assert "verdict" in body


def test_assist_endpoint_falls_back_to_the_brief(client):
    pid = client.post("/api/projects", json={"name": "A", "domain": "assist.example"}).json()["id"]
    body = client.post(f"/api/projects/{pid}/assist", json={
        "question": "¿por dónde empiezo?", "language": "es",
    }).json()
    assert body["answered"] is False
    assert body["brief"]


def test_share_endpoint_is_readable_without_auth(client):
    pid = client.post("/api/projects", json={
        "name": "Acme", "domain": "share-api.example",
    }).json()["id"]
    created = client.post(f"/api/projects/{pid}/shares", json={
        "label": "Para Pierre", "scope": "report", "valid_days": 30, "allow_ai_brief": True,
    }).json()

    shared = client.get(f"/api/shared/{created['token']}").json()
    assert shared["shared"] is True
    assert shared["report"]["project"]["domain"] == "share-api.example"
    assert shared["ai_brief"]
    # A read-only report must not leak the internal pipeline view.
    assert "pipeline" not in shared["report"]

    assert client.delete(f"/api/projects/{pid}/shares/{created['id']}").status_code == 204
    assert client.get(f"/api/shared/{created['token']}").status_code == 404


def test_share_scope_backlinks_only_returns_links(client):
    pid = client.post("/api/projects", json={
        "name": "Acme", "domain": "share-scope.example",
    }).json()["id"]
    created = client.post(f"/api/projects/{pid}/shares", json={
        "scope": "backlinks", "valid_days": 7, "allow_ai_brief": False,
    }).json()
    shared = client.get(f"/api/shared/{created['token']}").json()
    assert "backlinks" in shared["report"]
    assert "fixes" not in shared["report"]
    assert "ai_brief" not in shared


def test_invalid_share_token_is_a_404(client):
    assert client.get("/api/shared/not-a-real-token").status_code == 404


def test_user_endpoints(client):
    assert client.get("/api/users/me").status_code == 200

    invite = client.post("/api/users/invite", json={
        "username": "pierre", "display_name": "Pierre", "role": "editor",
    })
    assert invite.status_code == 201, invite.text
    token = invite.json()["invite_path"].split("/")[-1]

    users = client.get("/api/users").json()
    assert any(u["username"] == "pierre" and u["pending_invite"] for u in users)

    accepted = client.post("/api/users/accept-invite", json={
        "token": token, "password": "unaclavelarga",
    }).json()
    assert accepted["ok"] is True
    assert accepted["token"]

    # The API must never hand back a stored API key.
    listed = client.get("/api/users").json()
    assert all("ai_api_key" not in u for u in listed)


def test_health_reports_the_new_capabilities(client):
    body = client.get("/api/health").json()
    assert "first_party_data" in body
    assert "serp_providers" in body
    assert "full_scan" in body["job_kinds"]
