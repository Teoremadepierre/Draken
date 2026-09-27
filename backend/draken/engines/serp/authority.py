"""Domain authority estimation.

If DRAKEN_OPENPAGERANK_KEY is set we use Open PageRank (free tier, real data).
Otherwise we fall back to a structural estimate from the domain itself, plus any
authority we have already observed in our own backlink index. Results are cached
in-process so a SERP scoring pass does not re-estimate the same domain 200 times.
"""

from __future__ import annotations

import re

from draken.core.config import settings
from draken.core.http import PoliteClient
from draken.core.logging import get_logger
from draken.core.urls import normalize_domain

log = get_logger(__name__)

_cache: dict[str, float] = {}

# Domains whose authority is not in question; saves API calls and anchors the scale.
_KNOWN: dict[str, float] = {
    "wikipedia.org": 100.0, "youtube.com": 100.0, "google.com": 100.0,
    "facebook.com": 96.0, "amazon.com": 96.0, "x.com": 94.0, "twitter.com": 94.0,
    "linkedin.com": 98.0, "instagram.com": 94.0, "reddit.com": 96.0,
    "github.com": 96.0, "stackoverflow.com": 96.0, "apple.com": 97.0,
    "microsoft.com": 97.0, "nytimes.com": 95.0, "bbc.co.uk": 95.0,
    "forbes.com": 93.0, "medium.com": 94.0, "wordpress.org": 96.0,
    "quora.com": 92.0, "pinterest.com": 94.0, "yelp.com": 94.0,
    "tripadvisor.com": 94.0, "crunchbase.com": 92.0, "g2.com": 92.0,
    "trustpilot.com": 93.0, "producthunt.com": 91.0, "huggingface.co": 91.0,
    "elpais.com": 92.0, "elmundo.es": 90.0, "lavanguardia.com": 88.0,
    "20minutos.es": 87.0, "marca.com": 90.0, "eleconomista.es": 84.0,
}

_HIGH_TRUST_TLD = {".gov": 22.0, ".edu": 20.0, ".ac.uk": 20.0, ".gob.es": 20.0, ".gov.uk": 22.0}
_SPAMMY_TLD = {".xyz", ".top", ".click", ".work", ".loan", ".tk", ".ml", ".gq", ".cf", ".buzz"}


def structural_estimate(domain: str) -> float:
    """A defensible guess when no authority API is available.

    Signals: known-domain table, TLD trust, domain length, hyphen/digit spam
    markers, and subdomain hosting on a free platform.
    """
    domain = normalize_domain(domain)
    if not domain:
        return 0.0
    if domain in _KNOWN:
        return _KNOWN[domain]

    score = 32.0
    for tld, bonus in _HIGH_TRUST_TLD.items():
        if domain.endswith(tld):
            score += bonus
            break
    if any(domain.endswith(t) for t in _SPAMMY_TLD):
        score -= 18.0
    if domain.endswith((".com", ".org", ".net")):
        score += 5.0
    if domain.count("-") >= 2:
        score -= 8.0
    if re.search(r"\d{3,}", domain):
        score -= 6.0

    name = domain.split(".")[0]
    if len(name) <= 6:
        score += 7.0       # short, memorable names skew established
    elif len(name) >= 22:
        score -= 6.0

    return round(max(1.0, min(85.0, score)), 1)


async def fetch_openpagerank(domains: list[str]) -> dict[str, float]:
    """Open PageRank exposes a real 0-10 rank; we rescale it to 0-100."""
    if not settings.openpagerank_key or not domains:
        return {}
    out: dict[str, float] = {}
    async with PoliteClient(delay=0.5, concurrency=2, timeout=20) as client:
        for chunk_start in range(0, len(domains), 100):
            chunk = domains[chunk_start : chunk_start + 100]
            params = [("domains[]", d) for d in chunk]
            data, _res = await client.fetch_json(
                "https://openpagerank.com/api/v1.0/getPageRank",
                params=params,
                headers={"API-OPR": settings.openpagerank_key},
            )
            if not isinstance(data, dict):
                continue
            for row in data.get("response") or []:
                dom = row.get("domain")
                rank = row.get("page_rank_decimal")
                if dom and rank not in (None, "", "0"):
                    try:
                        out[dom] = round(min(100.0, float(rank) * 10.0), 1)
                    except (TypeError, ValueError):
                        continue
    return out


async def authority_for(domains: list[str], *, use_api: bool = True) -> dict[str, float]:
    """Best available authority per domain, with caching."""
    normalized = [normalize_domain(d) for d in domains if d]
    wanted = [d for d in dict.fromkeys(normalized) if d]
    result: dict[str, float] = {}
    missing: list[str] = []

    for d in wanted:
        if d in _cache:
            result[d] = _cache[d]
        else:
            missing.append(d)

    if missing and use_api and settings.openpagerank_key:
        try:
            api = await fetch_openpagerank(missing)
            for d, v in api.items():
                _cache[d] = v
                result[d] = v
            missing = [d for d in missing if d not in api]
        except Exception as exc:  # noqa: BLE001
            log.warning("openpagerank lookup failed: %s", exc)

    for d in missing:
        v = structural_estimate(d)
        _cache[d] = v
        result[d] = v
    return result


def authority_sync(domain: str) -> float:
    """Non-async accessor for code paths that cannot await (uses cache/estimate)."""
    d = normalize_domain(domain)
    if d in _cache:
        return _cache[d]
    v = structural_estimate(d)
    _cache[d] = v
    return v


def prime_cache(values: dict[str, float]) -> None:
    for d, v in values.items():
        nd = normalize_domain(d)
        if nd:
            _cache[nd] = float(v)
