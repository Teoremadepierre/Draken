"""Deployment paths: bootstrap credentials, entrypoint contract, platform configs.

These guard the "how do I get a URL" story: if a template drifts from what the
app actually reads, a deploy fails in a way that is painful to debug remotely.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


# --- bootstrap credentials ------------------------------------------------


def test_plain_text_admin_password_is_accepted(db, monkeypatch):
    """Platforms take env vars typed into a dashboard, where hashing first is awkward."""
    from draken.core.config import settings
    from draken.services import accounts

    monkeypatch.setattr(settings, "admin_user", "admin")
    monkeypatch.setattr(settings, "admin_password_hash", "")
    monkeypatch.setattr(settings, "admin_password", "una-clave-larga")
    monkeypatch.setattr(accounts, "settings", settings)

    assert settings.has_admin_credentials is True
    assert accounts.authenticate(db, username="admin", password="una-clave-larga") is not None
    assert accounts.authenticate(db, username="admin", password="otra") is None
    assert accounts.authenticate(db, username="otro", password="una-clave-larga") is None


def test_the_hash_wins_over_the_plain_text_value(db, monkeypatch):
    """With both set, the hash is authoritative: it is the safer of the two."""
    from draken.core.config import settings
    from draken.core.security import hash_password
    from draken.services import accounts

    monkeypatch.setattr(settings, "admin_user", "admin")
    monkeypatch.setattr(settings, "admin_password_hash", hash_password("la-del-hash"))
    monkeypatch.setattr(settings, "admin_password", "la-en-claro")
    monkeypatch.setattr(accounts, "settings", settings)

    assert accounts.authenticate(db, username="admin", password="la-del-hash") is not None
    assert accounts.authenticate(db, username="admin", password="la-en-claro") is None


def test_no_credentials_means_no_bootstrap_login(db, monkeypatch):
    from draken.core.config import settings
    from draken.services import accounts

    monkeypatch.setattr(settings, "admin_password_hash", "")
    monkeypatch.setattr(settings, "admin_password", "")
    monkeypatch.setattr(accounts, "settings", settings)

    assert settings.has_admin_credentials is False
    assert accounts.authenticate(db, username="admin", password="cualquiera") is None


def test_auth_status_reports_missing_credentials(client, monkeypatch):
    from draken.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "admin_password_hash", "")
    monkeypatch.setattr(settings, "admin_password", "")

    body = client.get("/api/auth/status").json()
    assert body["auth_enabled"] is True
    assert body["configured"] is False
    assert "DRAKEN_ADMIN_PASSWORD" in body["hint"]


def test_login_refuses_when_no_password_is_configured(client, monkeypatch):
    from draken.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "admin_password_hash", "")
    monkeypatch.setattr(settings, "admin_password", "")

    response = client.post("/api/auth/login", json={"username": "admin", "password": "x"})
    assert response.status_code == 503
    assert "DRAKEN_ADMIN_PASSWORD" in response.json()["detail"]


# --- entrypoint -----------------------------------------------------------


def test_entrypoint_exists_and_is_executable():
    entrypoint = REPO / "deploy" / "entrypoint.sh"
    assert entrypoint.exists()
    assert os.stat(entrypoint).st_mode & stat.S_IXUSR, "entrypoint must be executable"


def test_entrypoint_honours_the_injected_port():
    """Every platform injects PORT and expects the process to bind it."""
    body = (REPO / "deploy" / "entrypoint.sh").read_text()
    assert 'PORT="${PORT:-${DRAKEN_PORT:-8000}}"' in body
    assert '--port "${PORT}"' in body
    assert "--host 0.0.0.0" in body
    # It must prepare the database, or a fresh deploy comes up with no tables.
    assert "init-db" in body
    # And warn when it is about to serve an unauthenticated app publicly.
    assert "authentication is OFF" in body


def test_installer_is_executable_and_valid_bash():
    import subprocess

    installer = REPO / "install.sh"
    assert installer.exists()
    assert os.stat(installer).st_mode & stat.S_IXUSR
    result = subprocess.run(["bash", "-n", str(installer)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_installer_generates_its_own_secrets():
    """It must never ship a default secret key or password."""
    body = (REPO / "install.sh").read_text()
    assert "openssl rand -hex 32" in body, "the secret key has to be generated"
    assert "DRAKEN_AUTH_ENABLED=true" in body, "a public install must require a login"
    assert "DRAKEN_SUBMISSIONS_DRY_RUN=true" in body, "submissions must stay dry-run"


# --- platform templates ---------------------------------------------------


def test_dockerfile_uses_the_entrypoint_and_a_non_root_user():
    body = (REPO / "Dockerfile").read_text()
    assert 'ENTRYPOINT ["/app/entrypoint.sh"]' in body
    assert "USER draken" in body
    assert "HEALTHCHECK" in body


def test_render_blueprint_matches_the_settings_the_app_reads():
    import yaml

    blueprint = yaml.safe_load((REPO / "render.yaml").read_text())
    service = blueprint["services"][0]
    assert service["healthCheckPath"] == "/api/health"

    keys = {v["key"] for v in service["envVars"]}
    for required in ("DRAKEN_DATABASE_URL", "DRAKEN_SECRET_KEY",
                     "DRAKEN_AUTH_ENABLED", "DRAKEN_ADMIN_PASSWORD"):
        assert required in keys, f"{required} missing from render.yaml"

    # Free-tier disks are ephemeral, so the database must not be SQLite.
    db_var = next(v for v in service["envVars"] if v["key"] == "DRAKEN_DATABASE_URL")
    assert "fromDatabase" in db_var, "Render must use Postgres, not a disposable SQLite file"

    # The password must not be committed.
    password_var = next(v for v in service["envVars"] if v["key"] == "DRAKEN_ADMIN_PASSWORD")
    assert password_var.get("sync") is False


def test_fly_config_persists_data_and_checks_health():
    body = (REPO / "fly.toml").read_text()
    assert "[[mounts]]" in body, "without a volume the database dies on restart"
    assert 'destination = "/data"' in body
    assert 'DRAKEN_DATABASE_URL = "sqlite:////data/draken.db"' in body
    assert 'path = "/api/health"' in body
    assert "force_https = true" in body


def test_railway_config_is_valid_json_with_a_healthcheck():
    config = json.loads((REPO / "railway.json").read_text())
    assert config["build"]["builder"] == "DOCKERFILE"
    assert config["deploy"]["healthcheckPath"] == "/api/health"


def test_caddyfile_proxies_the_right_port_and_blocks_indexing():
    body = (REPO / "deploy" / "caddy" / "Caddyfile").read_text()
    assert "reverse_proxy 127.0.0.1:8000" in body
    assert "noindex" in body, "an internal tool must not be indexable"
    assert "600s" in body, "audits take minutes; the proxy must not time out"


@pytest.mark.parametrize("name", ["render.yaml", "fly.toml", "railway.json", "install.sh"])
def test_deploy_templates_carry_no_real_secrets(name):
    """Guards against a key being pasted into a template and committed."""
    body = (REPO / name).read_text()
    for marker in ("sk-ant-", "sk-proj-", "-----BEGIN PRIVATE KEY-----", "AKIA"):
        assert marker not in body, f"{name} appears to contain a real credential"


def test_publish_guide_documents_every_template():
    guide = (REPO / "docs" / "PUBLICAR.md").read_text()
    for needle in ("install.sh", "render.yaml", "fly.toml", "cloudflared",
                   "DRAKEN_AUTH_ENABLED", "DRAKEN_SECRET_KEY"):
        assert needle in guide, f"PUBLICAR.md does not mention {needle}"


# --- portability (export / import) ----------------------------------------


def _seed_project(db):
    """A project with something in every table the export is supposed to carry."""
    from draken.core.models import (
        AIPrompt,
        Backlink,
        BusinessProfile,
        Campaign,
        Keyword,
        KeywordCluster,
        LinkOpportunity,
        LinkSource,
        Project,
        RankSnapshot,
        Submission,
    )

    project = Project(domain="ejemplo.com", name="Ejemplo", base_url="https://ejemplo.com",
                      country="ES", language="es", competitors=["otro.com"])
    db.add(project)
    db.flush()

    db.add(BusinessProfile(project_id=project.id, legal_name="Ejemplo SL",
                           email="hola@ejemplo.com", phone="+34 910 000 000"))

    cluster = KeywordCluster(project_id=project.id, label="zapatos", recommended_page_type="category")
    db.add(cluster)
    db.flush()

    keyword = Keyword(project_id=project.id, term="zapatos rojos", cluster_id=cluster.id,
                      volume=320, volume_confidence=0.6)
    db.add(keyword)
    db.flush()
    db.add(RankSnapshot(keyword_id=keyword.id, position=12, url="https://ejemplo.com/x"))

    db.add(Backlink(project_id=project.id, source_url="https://blog.example/a",
                    target_url="https://ejemplo.com/", source_domain="blog.example",
                    anchor_text="ejemplo"))

    campaign = Campaign(project_id=project.id, name="Directorios Q1")
    db.add(campaign)

    source = LinkSource(slug="una-fuente", name="Una fuente", domain="fuente.example",
                        category="directory", authority=55)
    db.add(source)
    db.flush()

    opportunity = LinkOpportunity(project_id=project.id, source_id=source.id,
                                  campaign_id=campaign.id, target_domain="fuente.example",
                                  score=71.5, status="queued")
    db.add(opportunity)
    db.flush()
    db.add(Submission(project_id=project.id, opportunity_id=opportunity.id,
                      state="prepared", dry_run=True))
    db.add(AIPrompt(project_id=project.id, prompt="mejores zapatos rojos"))
    db.commit()
    return project


def test_export_import_round_trip_keeps_the_work(db):
    """The whole point: moving host must not mean starting over."""
    from draken.core.models import (
        Backlink,
        BusinessProfile,
        Keyword,
        LinkOpportunity,
        Project,
        Submission,
    )
    from draken.services.portability import export_project, import_project

    project = _seed_project(db)
    payload = export_project(db, project=project)
    assert payload["counts"]["keywords"] == 1
    assert payload["opportunities"][0]["_source_slug"] == "una-fuente"

    # Simulate the other install: the project is gone, ids will differ.
    db.delete(project)
    db.commit()

    report = import_project(db, payload)
    assert report["keywords"] == 1
    assert report["opportunities"] == 1
    assert report["submissions"] == 1

    restored = db.query(Project).filter_by(domain="ejemplo.com").one()
    assert restored.competitors == ["otro.com"]
    assert db.query(BusinessProfile).filter_by(project_id=restored.id).one().legal_name == "Ejemplo SL"

    keyword = db.query(Keyword).filter_by(project_id=restored.id).one()
    assert keyword.term == "zapatos rojos"
    assert keyword.cluster_id is not None, "the keyword lost its cluster"
    assert keyword.volume == 320

    assert db.query(Backlink).filter_by(project_id=restored.id).count() == 1
    opportunity = db.query(LinkOpportunity).filter_by(project_id=restored.id).one()
    assert opportunity.status == "queued"
    assert opportunity.campaign_id is not None, "the opportunity lost its campaign"
    submission = db.query(Submission).filter_by(project_id=restored.id).one()
    assert submission.opportunity_id == opportunity.id


def test_import_resolves_sources_by_slug_not_by_id(db):
    """Catalog ids differ per install, so a carried id would point at the wrong source."""
    from draken.core.models import LinkOpportunity, LinkSource, Project
    from draken.services.portability import export_project, import_project

    project = _seed_project(db)
    payload = export_project(db, project=project)
    db.delete(project)
    db.commit()

    # Shift the catalog ids: the same slug now lives at a different id.
    db.query(LinkSource).delete()
    db.commit()
    for index in range(4):
        db.add(LinkSource(slug=f"relleno-{index}", name=f"Relleno {index}",
                          domain=f"relleno{index}.example", category="directory"))
    db.add(LinkSource(slug="una-fuente", name="Una fuente", domain="fuente.example",
                      category="directory", authority=55))
    db.commit()
    moved = db.query(LinkSource).filter_by(slug="una-fuente").one()

    import_project(db, payload)
    restored = db.query(Project).filter_by(domain="ejemplo.com").one()
    opportunity = db.query(LinkOpportunity).filter_by(project_id=restored.id).one()
    assert opportunity.source_id == moved.id


def test_import_refuses_to_replace_a_project_unless_told_to(db):
    from draken.services.portability import export_project, import_project

    project = _seed_project(db)
    payload = export_project(db, project=project)

    with pytest.raises(ValueError, match="already exists"):
        import_project(db, payload)

    report = import_project(db, payload, overwrite=True)
    assert report["keywords"] == 1


def test_import_rejects_a_file_that_is_not_an_export(db):
    from draken.services.portability import import_project

    with pytest.raises(ValueError, match="not a Draken project export"):
        import_project(db, {"hello": "world"})


def test_import_rejects_a_newer_format_version(db):
    from draken.services.portability import FORMAT_VERSION, import_project

    payload = {"format": "draken-export", "format_version": FORMAT_VERSION + 1,
               "project": {"domain": "x.com"}}
    with pytest.raises(ValueError, match="Update Draken first"):
        import_project(db, payload)


def test_an_export_carries_no_secrets(db):
    """Export files get emailed and dropped in cloud storage. Keys must not ride along."""
    from draken.services.portability import export_project, to_json

    project = _seed_project(db)
    text = to_json(export_project(db, project=project))
    for marker in ("api_key", "password", "secret", "token"):
        assert marker not in text.lower(), f"the export leaks {marker}"


def test_render_guide_covers_the_free_tier_traps():
    guide = (REPO / "docs" / "RENDER.md").read_text()
    for needle in ("DRAKEN_ADMIN_PASSWORD", "Blueprint", "draken import",
                   "DRAKEN_GSC_SERVICE_ACCOUNT_JSON", "caduca"):
        assert needle in guide, f"RENDER.md does not cover {needle}"


def test_the_local_launcher_is_safe_and_self_contained():
    import subprocess

    script = REPO / "scripts" / "empezar.sh"
    assert script.exists()
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    body = script.read_text()
    assert "secrets.token_hex" in body, "the secret key must be generated, never shipped"
    assert "DRAKEN_AUTH_ENABLED=false" in body, "a localhost-only try-out skips the login"
    assert "127.0.0.1" in body, "it must not advertise a public address"
