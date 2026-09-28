"""Test fixtures. Every test runs against an isolated in-memory database."""

from __future__ import annotations

import os

os.environ.setdefault("DRAKEN_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DRAKEN_AUTH_ENABLED", "false")
os.environ.setdefault("DRAKEN_SUBMISSIONS_DRY_RUN", "true")
os.environ.setdefault("DRAKEN_SUBMISSIONS_REQUIRE_APPROVAL", "true")
os.environ.setdefault("DRAKEN_OUTREACH_SEND_ENABLED", "false")
os.environ.setdefault("DRAKEN_SCHEDULER_ENABLED", "false")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from draken.core.database import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_schema():
    from draken.core import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    from draken.api.app import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def project(db):
    from draken.core.models import BusinessProfile, Project

    p = Project(
        name="Acme SEO",
        domain="acme.example",
        base_url="https://acme.example",
        country="ES",
        language="es",
        industry="software",
        competitors=["competitor-one.example", "competitor-two.example"],
        brand_terms=["Acme SEO", "Acme"],
    )
    db.add(p)
    db.commit()
    db.add(
        BusinessProfile(
            project_id=p.id,
            display_name="Acme SEO",
            legal_name="Acme Analytics SL",
            tagline="SEO software for small teams",
            short_description="SEO software for small teams: keywords, ranks and backlinks.",
            long_description="Acme SEO is a self-serve platform for teams under ten people.",
            categories=["SEO software"],
            email="hola@acme.example",
            phone="+34 910 000 000",
            street="Calle Gran Via 1",
            city="Madrid",
            region="Madrid",
            postal_code="28013",
            country="ES",
            founded_year=2024,
            logo_url="https://acme.example/logo.png",
            website="https://acme.example",
        )
    )
    db.commit()
    return p
