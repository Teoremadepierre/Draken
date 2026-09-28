"""Engine-level tests: keyword metrics, clustering, scoring, toxicity, GEO."""

from __future__ import annotations

import pytest

from draken.core.models import LinkStatus, LinkType, SearchIntent
from draken.engines.backlinks import profile, toxicity
from draken.engines.crawler import checks
from draken.engines.crawler.parser import parse_html
from draken.engines.geo import assets, visibility
from draken.engines.keywords import cluster, expand, metrics
from draken.engines.opportunities import scoring
from draken.engines.outreach import engine as outreach

# --- keyword metrics -------------------------------------------------------


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("buy seo software", SearchIntent.transactional),
        ("best seo software", SearchIntent.commercial),
        ("what is a backlink", SearchIntent.informational),
        ("seo agency near me", SearchIntent.local),
        ("comprar software seo", SearchIntent.transactional),
        ("qué es un backlink", SearchIntent.informational),
        ("mejores herramientas seo", SearchIntent.commercial),
    ],
)
def test_intent_classification(term, expected):
    assert metrics.classify_intent(term) is expected


def test_branded_terms_resolve_to_navigational():
    assert metrics.classify_intent("acme login", brand_terms=["acme"]) is SearchIntent.navigational
    assert metrics.classify_intent("best acme alternative", brand_terms=["acme"]) is SearchIntent.commercial


def test_question_detection():
    assert metrics.is_question("how to build backlinks")
    assert metrics.is_question("¿qué es seo?")
    assert not metrics.is_question("backlink checker tool")


def test_volume_decays_with_word_count():
    short, _ = metrics.estimate_volume("seo software")
    long, _ = metrics.estimate_volume("seo software for small marketing teams in spain")
    assert short > long


def test_volume_confidence_rises_with_provider_agreement():
    _, low = metrics.estimate_volume("seo tool", provider_count=1)
    _, high = metrics.estimate_volume("seo tool", provider_count=3)
    assert high > low
    _, exact = metrics.estimate_volume("seo tool", seed_volume=5000)
    assert exact == 1.0


def test_difficulty_uses_real_serp_authority_when_available():
    weak = metrics.estimate_difficulty("x y z", serp_authorities=[10, 12, 8, 15, 11])
    strong = metrics.estimate_difficulty("x y z", serp_authorities=[95, 98, 92, 96, 94])
    assert strong > weak + 40


def test_difficulty_is_bounded():
    for authorities in ([], [0] * 10, [100] * 10):
        score = metrics.estimate_difficulty("test term", serp_authorities=authorities or None)
        assert 1.0 <= score <= 100.0


def test_opportunity_score_rewards_striking_distance():
    kwargs = {"volume": 5000, "difficulty": 40.0, "intent": SearchIntent.commercial}
    striking = metrics.opportunity_score(**kwargs, current_position=14)
    already_won = metrics.opportunity_score(**kwargs, current_position=2)
    unranked = metrics.opportunity_score(**kwargs, current_position=None)
    assert striking > unranked > already_won


def test_opportunity_score_discounts_branded_terms():
    kwargs = {"volume": 5000, "difficulty": 30.0, "intent": SearchIntent.commercial}
    assert metrics.opportunity_score(**kwargs, is_branded=True) < metrics.opportunity_score(**kwargs)


def test_traffic_estimate_follows_ctr_curve():
    assert metrics.estimate_traffic(10_000, 1) > metrics.estimate_traffic(10_000, 5)
    assert metrics.estimate_traffic(10_000, None) == 0.0


# --- expansion / clustering ------------------------------------------------


def test_seed_variants_include_modifiers_and_questions():
    variants = build = expand.build_seed_variants(
        ["seo software"], language="en", include_questions=True, include_modifiers=True
    )
    assert "seo software" in variants
    assert any(v.startswith("best ") for v in variants)
    assert any(v.startswith("how ") or v.startswith("what ") for v in variants)
    assert len(build) > 30


def test_seed_variants_localise_for_spanish():
    variants = expand.build_seed_variants(["software seo"], language="es")
    assert any("mejor" in v for v in variants)
    assert any(v.startswith("qué") or v.startswith("que") for v in variants)


@pytest.mark.asyncio
async def test_expand_works_without_network():
    results = await expand.expand(
        ["seo software"], max_results=60, use_live_suggest=False, language="en"
    )
    assert results
    assert all(0 <= r.opportunity_score <= 100 for r in results)
    assert all(r.word_count >= 1 for r in results)
    # Sorted by priority, descending.
    assert results == sorted(results, key=lambda k: (-k.opportunity_score, -k.volume, k.term))


def test_core_tokens_strip_modifiers_in_both_languages():
    assert cluster.core_tokens("best seo software") == cluster.core_tokens("cheap seo software")
    assert cluster.core_tokens("software seo barato") == cluster.core_tokens("gratis software seo")
    assert cluster.core_tokens("qué es software seo") == cluster.core_tokens("software seo")


def test_clustering_separates_distinct_topics():
    keywords = [
        {"term": "seo software", "volume": 9000, "difficulty": 60, "intent": "commercial"},
        {"term": "best seo software", "volume": 3000, "difficulty": 65, "intent": "commercial"},
        {"term": "cheap seo software", "volume": 1200, "difficulty": 55, "intent": "commercial"},
        {"term": "email marketing platform", "volume": 7000, "difficulty": 70, "intent": "commercial"},
        {"term": "best email marketing platform", "volume": 2500, "difficulty": 72, "intent": "commercial"},
        {"term": "how to build backlinks", "volume": 4000, "difficulty": 40, "intent": "informational"},
    ]
    clusters = cluster.cluster_keywords(keywords)
    assert len(clusters) >= 3, "three distinct topics should not collapse into one"

    labels = {c.label for c in clusters}
    # The seo-software variants belong together.
    seo_cluster = next(c for c in clusters if "seo" in c.label)
    terms = {m["term"] for m in seo_cluster.members}
    assert {"seo software", "best seo software", "cheap seo software"} <= terms
    assert "email marketing platform" not in terms
    assert labels


def test_clustering_is_deterministic():
    keywords = [
        {"term": f"topic {i} variant {j}", "volume": 100 * i, "difficulty": 50, "intent": "commercial"}
        for i in range(1, 6)
        for j in range(3)
    ]
    first = [(c.label, len(c.members)) for c in cluster.cluster_keywords(keywords)]
    second = [(c.label, len(c.members)) for c in cluster.cluster_keywords(keywords)]
    assert first == second


def test_cluster_recommends_a_page_type():
    clusters = cluster.cluster_keywords([
        {"term": "buy seo software", "volume": 900, "difficulty": 50, "intent": "transactional"},
    ])
    assert clusters[0].recommended_page_type() == "product / signup page"


def test_topic_map_groups_clusters():
    clusters = cluster.cluster_keywords([
        {"term": "seo software", "volume": 9000, "difficulty": 60, "intent": "commercial"},
        {"term": "seo software pricing", "volume": 400, "difficulty": 40, "intent": "commercial"},
        {"term": "email platform", "volume": 5000, "difficulty": 60, "intent": "commercial"},
    ])
    topics = cluster.build_topic_map(clusters)
    assert topics
    assert all("pillar" in t and "supporting" in t for t in topics)
    assert topics == sorted(topics, key=lambda t: -t["total_volume"])


# --- html parsing / audit checks ------------------------------------------

HTML = """<!doctype html><html lang="es"><head>
<title>Acme SEO - software para equipos pequeños</title>
<meta name="description" content="Software SEO para equipos pequeños.">
<link rel="canonical" href="https://acme.example/">
<link rel="alternate" hreflang="en" href="https://acme.example/en/">
<meta property="og:title" content="Acme SEO">
<script type="application/ld+json">{"@type":"Organization","name":"Acme"}</script>
</head><body>
<h1>Software SEO</h1><h2>Keywords</h2><h2>Enlaces</h2>
<p>Una herramienta para investigar palabras clave y enlaces.</p>
<a href="/precios">Precios</a>
<a href="https://other.example/x" rel="nofollow ugc">Externo</a>
<a href="mailto:a@b.com">Mail</a>
<img src="a.png" alt="ok"><img src="b.png">
</body></html>"""


def test_parser_extracts_the_full_picture():
    page = parse_html("https://acme.example/", HTML)
    assert page.title.startswith("Acme SEO")
    assert page.meta_description
    assert page.h1 == "Software SEO"
    assert page.h1_count == 1
    assert page.h2_count == 2
    assert page.lang == "es"
    assert page.canonical == "https://acme.example/"
    assert page.hreflang and page.hreflang[0]["hreflang"] == "en"
    assert page.schema_types == ["Organization"]
    assert page.open_graph["og:title"] == "Acme SEO"
    assert page.images == 2 and page.images_without_alt == 1
    assert page.internal_links == ["https://acme.example/precios"]
    assert len(page.external_links) == 1
    assert "nofollow" in page.external_links[0]["rel"]
    assert page.word_count > 5


def test_page_rules_flag_the_obvious_failures():
    codes = {i.code for i in checks.page_issues({
        "url": "https://e.com/x", "status_code": 200, "content_type": "text/html",
        "title": "", "meta_description": "", "h1": "", "word_count": 20,
        "images_without_alt": 3, "has_schema": False, "response_ms": 4000,
        "internal_links": 0, "depth": 6,
    })}
    for expected in (
        "missing_title", "missing_meta_description", "missing_h1", "thin_content",
        "images_missing_alt", "missing_structured_data", "slow_response",
        "orphan_outlinks", "deep_page", "missing_canonical",
    ):
        assert expected in codes


def test_page_rules_stay_quiet_on_a_good_page():
    codes = {i.code for i in checks.page_issues({
        "url": "https://e.com/x", "status_code": 200, "content_type": "text/html",
        "title": "A perfectly reasonable title for this page here", "h1_count": 1,
        "meta_description": "A description of about the right length, giving a reason to click through.",
        "h1": "A heading", "h2_count": 4, "word_count": 900, "images_without_alt": 0,
        "has_schema": True, "response_ms": 300, "internal_links": 8,
        "canonical": "https://e.com/x", "depth": 1,
    })}
    assert codes == set()


def test_server_errors_short_circuit_other_rules():
    issues = checks.page_issues({"url": "https://e.com", "status_code": 503, "content_type": "text/html"})
    assert [i.code for i in issues] == ["server_error_5xx"]
    assert issues[0].severity == "critical"


def test_site_rules_detect_duplicates_and_orphans():
    pages = [
        {"url": "https://e.com/a", "status_code": 200, "content_type": "text/html",
         "title": "Same title", "meta_description": "Same description", "word_count": 500,
         "outlinks": ["https://e.com/b"], "depth": 0},
        {"url": "https://e.com/b", "status_code": 200, "content_type": "text/html",
         "title": "Same title", "meta_description": "Same description", "word_count": 500,
         "outlinks": [], "depth": 1},
        {"url": "https://e.com/c", "status_code": 200, "content_type": "text/html",
         "title": "Unique", "meta_description": "Unique", "word_count": 500,
         "outlinks": [], "depth": 2},
    ]
    codes = {i.code for i in checks.site_issues(pages, robots_exists=False, sitemap_count=0)}
    assert {"duplicate_title", "duplicate_meta_description", "orphan_page",
            "no_robots_txt", "no_sitemap"} <= codes


def test_health_score_penalises_severity():
    clean = checks.health_score([], 10)
    critical = checks.health_score(
        [checks.Issue("x", "critical", "t", "d", "f")] * 5, 10
    )
    assert clean == 100.0
    assert critical < clean


def test_ai_readiness_rewards_structure():
    bare = checks.ai_readiness_score({"word_count": 100})
    rich = checks.ai_readiness_score({
        "has_schema": True, "title": "t", "meta_description": "d", "h1": "h",
        "h2_count": 5, "word_count": 1200, "robots_meta": "", "response_ms": 400,
    })
    assert rich > bare
    assert rich <= 100.0


# --- toxicity / link profile ----------------------------------------------


def test_toxicity_flags_a_spam_link_with_reasons():
    score, reasons = toxicity.score_link(
        source_url="https://buy-cheap-seo-links.xyz/page?replytocom=3",
        source_domain="buy-cheap-seo-links.xyz",
        anchor_text="buy cheap backlinks",
        link_type=LinkType.dofollow.value,
        domain_authority=4.0,
        is_sitewide=True,
    )
    assert score >= 70
    assert len(reasons) >= 4
    assert toxicity.classify_action(score) == "disavow"


def test_toxicity_leaves_a_good_link_alone():
    score, _ = toxicity.score_link(
        source_url="https://www.theguardian.com/technology/article",
        source_domain="theguardian.com",
        anchor_text="Acme SEO",
        link_type=LinkType.dofollow.value,
        domain_authority=92.0,
    )
    assert score < 20
    assert toxicity.classify_action(score) == "keep"


def test_nofollow_reduces_risk():
    kwargs = dict(
        source_url="https://weak-site.xyz/p", source_domain="weak-site.xyz",
        anchor_text="buy cheap", domain_authority=8.0,
    )
    follow, _ = toxicity.score_link(**kwargs, link_type=LinkType.dofollow.value)
    nofollow, _ = toxicity.score_link(**kwargs, link_type=LinkType.nofollow.value)
    assert nofollow < follow


@pytest.mark.parametrize(
    ("anchor", "expected"),
    [
        ("Acme SEO", "branded"),
        ("https://acme.example", "naked_url"),
        ("click here", "generic"),
        ("seo software", "exact_match"),
        ("", "image_empty"),
        ("the best seo software for small teams", "partial_match"),
    ],
)
def test_anchor_classification(anchor, expected):
    assert profile.classify_anchor(
        anchor, brand_terms=["Acme SEO", "Acme"], target_domain="acme.example"
    ) == expected


def test_profile_analysis_reports_anchor_risk():
    links = [
        {"source_domain": f"site{i}.example", "source_url": f"https://site{i}.example/p",
         "anchor_text": "seo software", "link_type": LinkType.dofollow.value,
         "status": LinkStatus.live.value, "domain_authority": 40, "toxicity_score": 0,
         "source_category": "resource_page", "first_seen": None, "lost_at": None}
        for i in range(10)
    ]
    report = profile.analyse(links, target_domain="acme.example", brand_terms=["Acme"])
    assert report["referring_domains"] == 10
    assert report["dofollow_links"] == 10
    exact = next(r for r in report["anchor_distribution"] if r["bucket"] == "exact_match")
    assert exact["verdict"] == "too_high"
    assert any("exact match" in w for w in report["anchor_health"]["warnings"])
    assert report["recommendations"]


def test_authority_score_is_logarithmic_and_bounded():
    def links(n, da):
        return [
            {"source_domain": f"s{i}.example", "source_url": f"https://s{i}.example/",
             "anchor_text": "Acme", "link_type": LinkType.dofollow.value,
             "status": LinkStatus.live.value, "domain_authority": da, "toxicity_score": 0}
            for i in range(n)
        ]

    assert profile.authority_score([]) == 0.0
    small = profile.authority_score(links(10, 50))
    big = profile.authority_score(links(200, 50))
    assert 0 < small < big <= 100
    # The documented property: the same +10 domains is worth far more at 10 than at 500.
    early_gain = profile.authority_score(links(20, 50)) - small
    late_gain = profile.authority_score(links(510, 50)) - profile.authority_score(links(500, 50))
    assert early_gain > late_gain * 5

    # Quality matters independently of count.
    assert profile.authority_score(links(50, 80)) > profile.authority_score(links(50, 20))


def test_recommendations_lead_with_the_zero_link_case():
    recs = profile.recommendations(
        referring_domains=0, avg_da=0, dofollow_ratio=0, toxic_count=0,
        anchor_warnings=[], lost_count=0, category_mix=[],
    )
    assert recs and "zero referring domains" in recs[0]


# --- opportunity scoring ---------------------------------------------------


def _source(**over):
    base = {
        "slug": "s", "name": "S", "domain": "s.example", "category": "directory",
        "authority": 60.0, "link_type": LinkType.dofollow.value, "is_free": True,
        "requires_account": False, "automatable": True, "effort": 2,
        "countries": ["*"], "languages": ["*"], "industries": ["*"], "tags": [],
        "llm_citation_weight": 0.0, "ai_training_signal": False,
    }
    base.update(over)
    return base


def test_country_match_drives_relevance():
    matched = scoring.relevance_for(_source(countries=["ES"]), project_country="ES")
    mismatched = scoring.relevance_for(_source(countries=["JP"]), project_country="ES")
    assert matched > mismatched


def test_industry_match_beats_a_foreign_vertical():
    same = scoring.relevance_for(_source(industries=["software"]), project_industry="software")
    other = scoring.relevance_for(_source(industries=["restaurant"]), project_industry="software")
    assert same > other


def test_low_value_tag_is_penalised():
    assert scoring.relevance_for(_source(tags=["low-value"])) < scoring.relevance_for(_source())


def test_scoring_prefers_authority_dofollow_and_low_effort():
    good = scoring.score_source(_source(authority=90, effort=1))
    weak = scoring.score_source(
        _source(authority=20, effort=5, link_type=LinkType.nofollow.value)
    )
    assert good.score > weak.score
    assert set(good.breakdown) >= {"authority", "relevance", "ease", "follow", "evidence"}


def test_competitor_evidence_raises_the_score():
    without = scoring.score_source(_source())
    with_evidence = scoring.score_source(_source(), competitor_links=3)
    assert with_evidence.score > without.score


def test_duplicate_domain_is_heavily_penalised():
    scored = scoring.score_source(_source(), already_have_domains={"s.example"})
    assert scored.score < scoring.score_source(_source()).score - 30


def test_geo_bonus_applies_to_ai_cited_sources():
    plain = scoring.score_source(_source())
    cited = scoring.score_source(_source(llm_citation_weight=0.8, ai_training_signal=True))
    assert cited.score > plain.score
    assert cited.breakdown["geo_bonus"] > 0


def test_listings_always_get_a_branded_anchor():
    for tactic in ("directory", "local_citation", "review_platform", "social_profile"):
        assert scoring.suggest_anchor(
            brand="Acme", target_keyword="seo software", tactic=tactic
        ) == "Acme"


def test_exact_match_anchor_only_when_profile_can_take_it():
    saturated = scoring.suggest_anchor(
        brand="Acme", target_keyword="seo software", tactic="resource_page",
        existing_anchor_mix={"branded": 5, "exact_match": 5},
    )
    assert saturated != "seo software"

    room = scoring.suggest_anchor(
        brand="Acme", target_keyword="seo software", tactic="resource_page",
        existing_anchor_mix={"branded": 40, "exact_match": 0},
    )
    assert room == "seo software"


def test_bare_profile_defaults_to_brand_anchor():
    assert scoring.suggest_anchor(brand="Acme", tactic="resource_page") == "Acme"


# --- GEO -------------------------------------------------------------------


ANSWER = (
    "For small teams the strongest options are Acme SEO, which is built for "
    "exactly that case, followed by Competitor One and Competitor Two. Acme SEO "
    "is excellent value and widely recommended. See https://acme.example/pricing "
    "and https://competitor-one.example for details."
)


def test_answer_analysis_detects_mention_position_and_citation():
    result = visibility.analyse_answer(
        engine="anthropic", model="m", answer=ANSWER,
        citations=["https://acme.example/pricing", "https://competitor-one.example"],
        brand_terms=["Acme SEO", "Acme"], domain="acme.example",
        competitors=["competitor-one.example", "competitor-two.example"],
    )
    assert result.brand_mentioned
    assert result.brand_position == 1
    assert result.domain_cited
    assert set(result.competitors_mentioned) == {"competitor-one.example", "competitor-two.example"}
    assert result.sentiment == "positive"
    assert result.visibility_score > 60
    assert result.share_of_voice == pytest.approx(1 / 3, abs=0.01)


def test_absent_brand_scores_zero():
    result = visibility.analyse_answer(
        engine="openai", model="m",
        answer="Consider Competitor One or Competitor Two.",
        citations=[], brand_terms=["Acme SEO"], domain="acme.example",
        competitors=["competitor-one.example"],
    )
    assert not result.brand_mentioned
    assert result.visibility_score == 0.0
    assert result.share_of_voice == 0.0


def test_mention_matching_respects_word_boundaries():
    result = visibility.analyse_answer(
        engine="x", model="m", answer="Use the spacebar for interspace navigation.",
        citations=[], brand_terms=["ace"], domain="ace.example", competitors=[],
    )
    assert not result.brand_mentioned


def test_being_first_beats_being_listed_later():
    first = visibility.visibility_score(
        brand_mentioned=True, brand_position=1, domain_cited=False,
        sentiment="neutral", competitor_count=2,
    )
    fifth = visibility.visibility_score(
        brand_mentioned=True, brand_position=5, domain_cited=False,
        sentiment="neutral", competitor_count=2,
    )
    assert first > fifth


def test_citation_is_worth_more_than_a_bare_mention():
    cited = visibility.visibility_score(
        brand_mentioned=True, brand_position=3, domain_cited=True,
        sentiment="neutral", competitor_count=1,
    )
    mentioned = visibility.visibility_score(
        brand_mentioned=True, brand_position=3, domain_cited=False,
        sentiment="neutral", competitor_count=1,
    )
    assert cited > mentioned + 20


def test_prompt_generation_fills_every_placeholder():
    prompts = visibility.generate_prompts(
        brand="Acme SEO", category="seo software",
        competitors=["competitor-one.example"], city="Madrid",
        keywords=["keyword research"], language="en", limit=30,
    )
    assert prompts
    for p in prompts:
        assert "{" not in p["prompt"] and "}" not in p["prompt"]
        assert p["category"] and p["intent"]


def test_spanish_projects_get_spanish_prompts():
    prompts = visibility.generate_prompts(
        brand="Acme", category="software seo", language="es", limit=30
    )
    assert any(p["language"] == "es" for p in prompts)
    assert any("¿" in p["prompt"] for p in prompts)


def test_english_templates_keep_english_defaults():
    prompts = visibility.generate_prompts(
        brand="Acme", category="software seo", language="es", limit=60
    )
    english = [p["prompt"] for p in prompts if p["language"] != "es"]
    assert not any("pymes" in p for p in english), "Spanish defaults leaked into English prompts"


def test_summary_rolls_runs_up():
    runs = [
        {"engine": "anthropic", "brand_mentioned": True, "brand_position": 1,
         "domain_cited": True, "competitors_mentioned": ["c1.example"],
         "visibility_score": 80.0, "error": ""},
        {"engine": "openai", "brand_mentioned": False, "brand_position": None,
         "domain_cited": False, "competitors_mentioned": ["c1.example", "c2.example"],
         "visibility_score": 0.0, "error": ""},
        {"engine": "openai", "brand_mentioned": False, "error": "rate limited"},
    ]
    out = visibility.summarise(runs, prompts_tracked=2, competitors=["c1.example"])
    assert out["runs"] == 2                      # the errored run is excluded
    assert out["mention_rate"] == 0.5
    assert out["citation_rate"] == 0.5
    assert len(out["by_engine"]) == 2
    assert out["competitor_share"][0]["competitor"] == "c1.example"
    assert out["recommendations"]


def test_llms_txt_contains_the_entity_facts():
    text = assets.generate_llms_txt(
        profile={
            "display_name": "Acme SEO", "tagline": "SEO for small teams",
            "long_description": "A self-serve platform.", "categories": ["SEO software"],
            "city": "Madrid", "country": "ES", "founded_year": 2024,
            "email": "hola@acme.example",
            "social_profiles": {"linkedin": "https://linkedin.com/company/acme"},
        },
        project={"name": "Acme", "domain": "acme.example", "base_url": "https://acme.example"},
        key_pages=[{"url": "https://acme.example/pricing", "title": "Pricing",
                    "meta_description": "Plans"}],
        clusters=[{"label": "seo software"}],
    )
    assert text.startswith("# Acme SEO")
    assert "> SEO for small teams" in text
    assert "Madrid" in text and "2024" in text
    assert "## Key pages" in text and "/pricing" in text
    assert "## Topics we cover" in text
    assert "linkedin" in text


def test_schema_upgrades_to_localbusiness_with_an_address():
    profile_data = {
        "display_name": "Acme SEO", "legal_name": "Acme Analytics SL",
        "short_description": "SEO software.", "street": "Calle Gran Via 1",
        "city": "Madrid", "postal_code": "28013", "country": "ES",
        "phone": "+34 910 000 000", "logo_url": "https://acme.example/logo.png",
        "social_profiles": {"x": "https://x.com/acme"},
    }
    project_data = {"name": "Acme", "domain": "acme.example", "base_url": "https://acme.example"}
    block = assets.generate_organization_schema(profile=profile_data, project=project_data)
    assert block["@type"] == "LocalBusiness"
    assert block["address"]["postalCode"] == "28013"
    assert block["sameAs"] == ["https://x.com/acme"]

    bundle = assets.schema_bundle(profile=profile_data, project=project_data)
    assert "@graph" in bundle["graph"]
    assert bundle["script_tag"].startswith('<script type="application/ld+json">')


def test_schema_stays_organization_without_an_address():
    block = assets.generate_organization_schema(
        profile={"display_name": "Acme"},
        project={"name": "Acme", "domain": "acme.example", "base_url": "https://acme.example"},
    )
    assert block["@type"] == "Organization"


def test_entity_consistency_finds_nap_drift():
    report = assets.check_entity_consistency(
        profile={"display_name": "Acme SEO", "phone": "+34 910 000 000",
                 "city": "Madrid", "website": "https://acme.example"},
        listings=[
            {"source": "yelp.com", "name": "Acme SEO", "phone": "+34 910 000 000", "city": "Madrid"},
            {"source": "hotfrog.com", "name": "Acme S.E.O.", "phone": "+34 911 111 111", "city": "Madrid"},
        ],
    )
    assert report["listings_checked"] == 2
    assert report["consistent_listings"] == 1
    assert {m["field"] for m in report["mismatches"]} == {"name", "phone"}
    assert report["recommendations"]


def test_phone_comparison_ignores_formatting():
    report = assets.check_entity_consistency(
        profile={"display_name": "Acme", "phone": "+34 910 000 000"},
        listings=[{"source": "a.example", "name": "Acme", "phone": "(0034) 910-000-000"}],
    )
    assert not [m for m in report["mismatches"] if m["field"] == "phone"]


# --- outreach --------------------------------------------------------------


def test_template_rendering_reports_unresolved_variables():
    text, missing = outreach.render("Hi {{name}}, about {{topic}}", {"name": "Ada"})
    assert "Ada" in text
    assert "[[topic]]" in text
    assert missing == ["topic"]


def test_draft_is_not_ready_while_placeholders_remain():
    draft = outreach.draft_message(
        template={"subject": "About {{page_title}}", "body": "Hi {{contact_first_name}}",
                  "step_number": 1, "delay_days": 0},
        context={"contact_first_name": "Ada"},
    )
    assert not draft["ready_to_send"]
    assert "page_title" in draft["unresolved_variables"]


def test_builtin_templates_cover_the_core_tactics():
    for tactic in ("unlinked_mention", "broken_link", "resource_page", "digital_pr", "guest_post"):
        assert outreach.builtin_templates(tactic), f"no template for {tactic}"


def test_spanish_template_is_selected_for_spanish():
    templates = outreach.builtin_templates("unlinked_mention", "es")
    assert templates
    assert all(t["language"] == "es" for t in templates)


def test_sending_is_refused_while_disabled():
    ok, detail = outreach.send_email(
        to_email="a@b.example", subject="s", body="b"
    )
    assert not ok
    assert "disabled" in detail.lower()
