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
