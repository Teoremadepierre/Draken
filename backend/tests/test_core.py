"""URL normalisation, security primitives and seed data integrity."""

from __future__ import annotations

import pytest

from draken.core.security import hash_password, issue_token, verify_password, verify_token
from draken.core.urls import (
    is_probably_binary,
    normalize_domain,
    normalize_url,
    same_site,
    url_depth,
)
from draken.data import loader


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://WWW.Example.co.uk/path?a=1", "example.co.uk"),
        ("example.com", "example.com"),
        ("http://sub.blog.example.com/", "example.com"),
        ("https://user:pw@example.com:8443/x", "example.com"),
        ("", ""),
    ],
)
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


def test_normalize_url_strips_tracking_and_fragment():
    url = normalize_url("https://Example.com/a//b/?utm_source=x&id=7&fbclid=9#section")
    assert url == "https://example.com/a/b?id=7"


def test_normalize_url_keeps_meaningful_query_sorted():
    assert normalize_url("https://e.com/x?b=2&a=1") == "https://e.com/x?a=1&b=2"


def test_same_site_and_depth():
    assert same_site("https://a.example/x", "http://www.a.example/y")
    assert not same_site("https://a.example", "https://b.example")
    assert url_depth("https://e.com/a/b/c") == 3
    assert url_depth("https://e.com/") == 0


def test_binary_detection():
    assert is_probably_binary("https://e.com/file.pdf")
    assert is_probably_binary("https://e.com/img.PNG")
    assert not is_probably_binary("https://e.com/page")


def test_password_round_trip():
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)
    assert not verify_password("x", "not-a-hash")


def test_token_round_trip_and_tamper_detection():
    token = issue_token("admin")
    assert verify_token(token) == "admin"
    assert verify_token(token[:-2] + "xy") is None
    assert verify_token("garbage") is None


def test_link_source_catalog_is_well_formed():
    sources = loader.link_sources()
    assert len(sources) >= 300, "catalog should be substantial"

    slugs = [s["slug"] for s in sources]
    assert len(slugs) == len(set(slugs)), "slugs must be unique"

    required = {"slug", "name", "domain", "category", "authority", "link_type", "effort"}
    for s in sources:
        assert required <= set(s), f"{s.get('slug')} is missing keys"
        assert 0 <= s["authority"] <= 100
        assert 1 <= s["effort"] <= 5
        assert s["link_type"] in {"dofollow", "nofollow", "ugc", "sponsored", "unknown"}
        assert isinstance(s["countries"], list)
        assert 0.0 <= s.get("llm_citation_weight", 0) <= 1.0


def test_catalog_covers_the_important_categories():
    categories = {s["category"] for s in loader.link_sources()}
    for expected in (
        "local_citation", "business_profile", "developer_profile", "review_platform",
        "startup_listing", "product_listing", "ai_dataset", "wiki", "qa_community",
    ):
        assert expected in categories


def test_catalog_has_spanish_market_coverage():
    spanish = [
        s for s in loader.link_sources()
        if "ES" in (s.get("countries") or []) or "es" in (s.get("languages") or [])
    ]
    assert len(spanish) >= 15


def test_ctr_curve_is_monotonic_over_the_first_page():
    positions = list(range(1, 11))
    values = [loader.ctr_for_position(p) for p in positions]
    assert values == sorted(values, reverse=True)
    assert values[0] > 0.2
    assert loader.ctr_for_position(None) == 0.0
    assert loader.ctr_for_position(0) == 0.0


def test_outreach_templates_have_bodies_and_variables():
    templates = loader.outreach_templates()
    assert len(templates) >= 10
    for t in templates:
        assert t["subject"] and t["body"]
        assert "{{" in t["body"], f"{t['name']} has no personalisation variables"
