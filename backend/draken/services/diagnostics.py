"""Connectivity and capability diagnostics.

Answers, in one call: what can this deployment actually reach, what does that
enable or disable, and what exactly do I change to fix it.

Written because a blocked outbound host degrades results silently otherwise -
keyword research returns fewer terms, rank tracking returns nothing, and nothing
says why.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from draken.core.config import settings
from draken.core.http import PoliteClient
from draken.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class Probe:
    key: str
    name: str
    url: str
    enables: str
    required_for: list[str] = field(default_factory=list)
    method: str = "GET"
    params: dict | None = None
    needs_key: str = ""            # the env var, if this host needs one
    optional: bool = True
    remediation: str = ""

    # filled in by the run
    reachable: bool = False
    status: int = 0
    latency_ms: int = 0
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "host": self.url.split("/")[2] if "//" in self.url else self.url,
            "enables": self.enables,
            "required_for": self.required_for,
            "needs_key": self.needs_key,
            "optional": self.optional,
            "reachable": self.reachable,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "remediation": self.remediation,
        }


def _probes(target_url: str = "") -> list[Probe]:
    probes = [
        Probe(
            key="google_suggest",
            name="Google autocomplete",
            url="https://suggestqueries.google.com/complete/search",
            params={"client": "chrome", "q": "seo"},
            enables="Keyword expansion with real popularity ordering",
            required_for=["Keyword research"],
            remediation=(
                "Allow suggestqueries.google.com. Without it, keyword research still runs "
                "but only on generated variants, with lower confidence."
            ),
        ),
        Probe(
            key="bing_suggest",
            name="Bing autocomplete",
            url="https://api.bing.com/osjson.aspx",
            params={"query": "seo"},
            enables="A second independent suggestion source",
            required_for=["Keyword research"],
            remediation="Allow api.bing.com.",
        ),
        Probe(
            key="duckduckgo_suggest",
            name="DuckDuckGo autocomplete",
            url="https://duckduckgo.com/ac/",
            params={"q": "seo", "type": "list"},
            enables="A third suggestion source",
            required_for=["Keyword research"],
            remediation="Allow duckduckgo.com.",
        ),
        Probe(
            key="duckduckgo_serp",
            name="DuckDuckGo results (free SERP)",
            url="https://html.duckduckgo.com/html/",
            enables="Rank tracking and competitor recon with no API key",
            required_for=["Rank tracking", "Keyword gap", "Competitor prospecting",
                          "Unlinked mentions"],
            optional=False,
            remediation=(
                "Allow html.duckduckgo.com, or configure a paid provider "
                "(DRAKEN_SERPAPI_KEY / DataForSEO) or your own SearXNG "
                "(DRAKEN_SEARXNG_URL), which also gives exact Google positions."
            ),
        ),
        Probe(
            key="mojeek_serp",
            name="Mojeek results (free SERP fallback)",
            url="https://www.mojeek.com/search",
            params={"q": "seo"},
            enables="An independent index used when the primary SERP source fails",
            required_for=["Rank tracking"],
            remediation="Allow www.mojeek.com.",
        ),
        Probe(
            key="commoncrawl",
            name="Common Crawl index",
            url="https://index.commoncrawl.org/collinfo.json",
            enables="Historic URL discovery for competitor recon",
            required_for=["Competitor recon (optional)"],
            remediation="Allow index.commoncrawl.org. Entirely optional.",
        ),
    ]

    if target_url:
        probes.insert(
            0,
            Probe(
                key="target_site",
                name="Your own site",
                url=target_url,
                enables="Site audit, on-page analysis, link verification",
                required_for=["Site audit", "On-page analysis", "Link verification"],
                optional=False,
                remediation=(
                    "The server cannot reach your site. Check DNS, TLS, firewall rules and "
                    "whether the site blocks unknown user agents."
                ),
            ),
        )

    if settings.serpapi_key:
        probes.append(Probe(
            key="serpapi", name="SerpApi", url="https://serpapi.com/account",
            params={"api_key": settings.serpapi_key},
            enables="Exact Google positions and SERP features",
            required_for=["Rank tracking (exact)"], needs_key="DRAKEN_SERPAPI_KEY",
            remediation="Allow serpapi.com and check the key is valid and in quota.",
        ))
    if settings.brave_api_key:
        probes.append(Probe(
            key="brave", name="Brave Search API", url="https://api.search.brave.com/res/v1/web/search",
            params={"q": "seo"},
            enables="An independent SERP index (free tier available)",
            required_for=["Rank tracking"], needs_key="DRAKEN_BRAVE_API_KEY",
            remediation="Allow api.search.brave.com and check the subscription token.",
        ))
    if settings.searxng_url:
        probes.append(Probe(
            key="searxng", name="Your SearXNG instance",
            url=f"{settings.searxng_url.rstrip('/')}/search",
            params={"q": "seo", "format": "json"},
            enables="SERP data aggregated from several engines, under your control",
            required_for=["Rank tracking"], needs_key="DRAKEN_SEARXNG_URL",
            remediation=(
                "Check the instance is up and that its settings.yml enables the json format "
                "under search.formats."
            ),
        ))

    first_party = settings.first_party_data_configured()
    if first_party["search_console"]:
        probes.append(Probe(
            key="search_console", name="Google Search Console API",
            url="https://searchconsole.googleapis.com/$discovery/rest",
            params={"version": "v1"},
            enables="REAL impressions, clicks, CTR and positions for your own site",
            required_for=["Real keyword data"], needs_key="DRAKEN_GSC_SERVICE_ACCOUNT_FILE",
            optional=False,
            remediation=(
                "Allow searchconsole.googleapis.com and oauth2.googleapis.com, and make sure "
                "the service-account email is added as a user on the property."
            ),
        ))
    if first_party["bing_webmaster"]:
        probes.append(Probe(
            key="bing_webmaster", name="Bing Webmaster API",
            url="https://ssl.bing.com/webmaster/api.svc/json/GetUserSites",
            params={"apikey": settings.bing_webmaster_api_key},
            enables="REAL inbound links and query performance from Bing, free",
            required_for=["Real backlink data"], needs_key="DRAKEN_BING_WEBMASTER_API_KEY",
            remediation="Allow ssl.bing.com and check the API key in Webmaster Tools.",
        ))

    ai = settings.ai_engines_configured()
    if ai["anthropic"]:
        probes.append(Probe(
            key="anthropic", name="Anthropic API", url="https://api.anthropic.com/v1/models",
            enables="AI visibility measurement and the in-app fix assistant",
            required_for=["AI visibility", "AI assistant"], needs_key="DRAKEN_ANTHROPIC_API_KEY",
            remediation="Allow api.anthropic.com and check the key.",
        ))
    if ai["openai"]:
        probes.append(Probe(
            key="openai", name="OpenAI API", url="https://api.openai.com/v1/models",
            enables="AI visibility measurement", required_for=["AI visibility"],
            needs_key="DRAKEN_OPENAI_API_KEY",
            remediation="Allow api.openai.com and check the key.",
        ))
    if ai["perplexity"]:
        probes.append(Probe(
            key="perplexity", name="Perplexity API", url="https://api.perplexity.ai/chat/completions",
            method="POST",
            enables="AI visibility with the grounding sources the model actually used",
            required_for=["AI visibility"], needs_key="DRAKEN_PERPLEXITY_API_KEY",
            remediation="Allow api.perplexity.ai and check the key.",
        ))
    if ai["gemini"]:
        probes.append(Probe(
            key="gemini", name="Google Gemini API",
            url="https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": settings.gemini_api_key},
            enables="AI visibility measurement", required_for=["AI visibility"],
            needs_key="DRAKEN_GEMINI_API_KEY",
            remediation="Allow generativelanguage.googleapis.com and check the key.",
        ))

    return probes


async def _run_probe(client: PoliteClient, probe: Probe) -> Probe:
    started = time.monotonic()
    headers = {}
    if probe.key == "anthropic":
        headers = {"x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01"}
    elif probe.key == "openai":
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    elif probe.key == "perplexity":
        headers = {"Authorization": f"Bearer {settings.perplexity_api_key}"}
    elif probe.key == "brave":
        headers = {"X-Subscription-Token": settings.brave_api_key}

    res = await client.fetch(
        probe.url, method=probe.method, params=probe.params, headers=headers or None,
        retries=0, max_bytes=20_000,
    )
    probe.latency_ms = int((time.monotonic() - started) * 1000)
    probe.status = res.status

    if res.error:
        probe.error = res.error
        probe.reachable = False
    elif res.status == 0:
        probe.error = "no response"
        probe.reachable = False
    else:
        # 4xx from an API usually means "reached it, but the key/method is wrong",
        # which is a different problem from "cannot reach the host at all".
        probe.reachable = True
        if res.status == 401 or res.status == 403:
            probe.error = f"reachable but rejected (HTTP {res.status}) - check the key"
        elif res.status >= 500:
            probe.error = f"remote error (HTTP {res.status})"
    return probe


async def run_connectivity_check(*, target_url: str = "", timeout: float = 12.0) -> dict:
    """Probe every host this deployment might need. Safe to run any time."""
    probes = _probes(target_url)
    async with PoliteClient(concurrency=6, delay=0.0, timeout=timeout) as client:
        results = await asyncio.gather(
            *(_run_probe(client, p) for p in probes), return_exceptions=True
        )

    checked: list[Probe] = []
    for probe, outcome in zip(probes, results, strict=False):
        if isinstance(outcome, Exception):
            probe.reachable = False
            probe.error = f"{type(outcome).__name__}: {outcome}"
        checked.append(probe)

    blocked = [p for p in checked if not p.reachable]
    blocking_required = [p for p in blocked if not p.optional]

    disabled_features: dict[str, list[str]] = {}
    for probe in blocked:
        for feature in probe.required_for:
            disabled_features.setdefault(feature, []).append(probe.name)

    # A proxy answering 403 to CONNECT is the unmistakable signature of an egress
    # policy rather than anything wrong with the individual services.
    proxy_blocked = [
        p for p in blocked
        if "proxyerror" in p.error.lower() or "connect_rejected" in p.error.lower()
        or "407" in p.error or ("403" in p.error and "proxy" in p.error.lower())
    ]

    if not blocked:
        verdict = "Everything this deployment needs is reachable."
        severity = "good"
    elif blocking_required:
        verdict = (
            f"{len(blocking_required)} required host(s) unreachable. "
            "Core features will return empty or partial results."
        )
        severity = "bad"
    else:
        verdict = (
            f"{len(blocked)} optional host(s) unreachable. Draken still works, with "
            "lower-confidence data where those sources would have been used."
        )
        severity = "warn"

    diagnosis = ""
    if len(proxy_blocked) >= 2:
        diagnosis = (
            f"{len(proxy_blocked)} hosts were refused by an outbound proxy, not by the services "
            "themselves. That is a network egress policy on the machine or container running "
            "Draken. Nothing in the configuration or the code will work around it: the hosts "
            "have to be allowed, or Draken has to run somewhere with unfiltered outbound HTTPS. "
            "Configuring Search Console and Bing Webmaster is the best move meanwhile, because "
            "they give real measured data for your own site from a single allowed host each."
        )
    elif blocking_required:
        diagnosis = (
            "The failures look host-specific rather than policy-wide. Check each remediation "
            "below individually."
        )

    return {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "probes": [p.as_dict() for p in checked],
        "proxy_blocked": len(proxy_blocked),
        "diagnosis": diagnosis,
        "reachable": len(checked) - len(blocked),
        "total": len(checked),
        "blocked": [p.as_dict() for p in blocked],
        "disabled_features": [
            {"feature": k, "because": v} for k, v in sorted(disabled_features.items())
        ],
        "verdict": verdict,
        "severity": severity,
        "general_remediation": (
            "If several unrelated hosts fail at once, it is almost always an outbound "
            "network policy (corporate proxy, container egress rules, firewall) rather than "
            "the individual services. Allow the hosts listed above, or run Draken where "
            "outbound HTTPS is not filtered."
        ),
    }
