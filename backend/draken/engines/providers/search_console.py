"""Google Search Console: the single best source of real data about your own site.

This is not an estimate. Search Console reports the impressions, clicks, CTR and
average position Google actually recorded, per query and per page. For your own
properties it is strictly better than any third-party estimate, including the
commercial suites, because those are modelling what this API measures.

Authentication: a Google service account with the Search Console API enabled and
the service account's email added as a user on the property. That avoids an
interactive OAuth flow, which does not fit a headless internal tool.

    DRAKEN_GSC_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
    DRAKEN_GSC_SITE_URL=https://example.com/        (or sc-domain:example.com)

A refresh token from an installed-app OAuth flow also works:

    DRAKEN_GSC_CLIENT_ID / DRAKEN_GSC_CLIENT_SECRET / DRAKEN_GSC_REFRESH_TOKEN
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from draken.core.config import settings
from draken.core.http import PoliteClient
from draken.core.logging import get_logger

log = get_logger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://searchconsole.googleapis.com/webmasters/v3"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"

_token_cache: dict[str, tuple[str, float]] = {}


@dataclass
class SearchAnalyticsRow:
    """One row of real measured performance."""

    query: str = ""
    page: str = ""
    country: str = ""
    device: str = ""
    date: str = ""
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class GscResult:
    rows: list[SearchAnalyticsRow] = field(default_factory=list)
    error: str = ""
    site_url: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def is_configured() -> bool:
    return bool(
        (settings.gsc_service_account_file and Path(settings.gsc_service_account_file).exists())
        or (settings.gsc_client_id and settings.gsc_client_secret and settings.gsc_refresh_token)
    )


def configuration_hint() -> str:
    if settings.gsc_service_account_file and not Path(settings.gsc_service_account_file).exists():
        return (
            f"DRAKEN_GSC_SERVICE_ACCOUNT_FILE points at {settings.gsc_service_account_file}, "
            "which does not exist."
        )
    return (
        "Set DRAKEN_GSC_SERVICE_ACCOUNT_FILE to a Google service-account JSON key (with the "
        "Search Console API enabled, and the service-account email added as a user on the "
        "property), or set DRAKEN_GSC_CLIENT_ID / _CLIENT_SECRET / _REFRESH_TOKEN. "
        "Then set DRAKEN_GSC_SITE_URL to the property, e.g. sc-domain:example.com"
    )


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _sign_service_account_jwt(key_data: dict) -> str:
    """Build and sign the assertion a service account exchanges for a token.

    Uses `cryptography`, which is already present via httpx's TLS stack in every
    realistic deployment; if it is missing we say so rather than failing opaquely.
    """
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "Service-account auth needs the `cryptography` package: pip install cryptography"
        ) from exc

    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": key_data["client_email"],
        "scope": SCOPE,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    signing_input = (
        f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
    ).encode()

    private_key = serialization.load_pem_private_key(
        key_data["private_key"].encode(), password=None
    )
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input.decode()}.{_b64url(signature)}"


async def _access_token(client: PoliteClient) -> tuple[str, str]:
    """Return ``(token, error)``. Tokens are cached until shortly before expiry."""
    cache_key = settings.gsc_service_account_file or settings.gsc_client_id
    cached = _token_cache.get(cache_key or "")
    if cached and cached[1] > time.time() + 60:
        return cached[0], ""

    if settings.gsc_service_account_file:
        path = Path(settings.gsc_service_account_file)
        if not path.exists():
            return "", f"service account file not found: {path}"
        try:
            key_data = json.loads(path.read_text(encoding="utf-8"))
            assertion = _sign_service_account_jwt(key_data)
        except Exception as exc:  # noqa: BLE001
            return "", f"could not read or sign with the service account key: {exc}"
        payload = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }
    elif settings.gsc_refresh_token:
        payload = {
            "grant_type": "refresh_token",
            "client_id": settings.gsc_client_id,
            "client_secret": settings.gsc_client_secret,
            "refresh_token": settings.gsc_refresh_token,
        }
    else:
        return "", "Search Console is not configured"

    data, res = await client.fetch_json(TOKEN_URL, method="POST", data=payload)
    if not isinstance(data, dict) or "access_token" not in data:
        detail = ""
        if isinstance(data, dict):
            detail = str(data.get("error_description") or data.get("error") or "")
        return "", detail or res.error or f"token request failed (HTTP {res.status})"

    token = data["access_token"]
    if cache_key:
        _token_cache[cache_key] = (token, time.time() + int(data.get("expires_in", 3600)))
    return token, ""


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------


def _resolve_site_url(domain: str, explicit: str = "") -> str:
    site = explicit or settings.gsc_site_url
    if site:
        return site
    # Domain properties are the common case and cover every subdomain/protocol.
    return f"sc-domain:{domain}"


async def list_sites() -> tuple[list[str], str]:
    """The properties this credential can read. Useful for setup validation."""
    if not is_configured():
        return [], configuration_hint()
    async with PoliteClient(concurrency=2, delay=0.2, timeout=30) as client:
        token, error = await _access_token(client)
        if error:
            return [], error
        data, res = await client.fetch_json(
            f"{API_BASE}/sites", headers={"Authorization": f"Bearer {token}"}
        )
        if not isinstance(data, dict):
            return [], res.error or f"HTTP {res.status}"
        return [
            entry.get("siteUrl", "")
            for entry in data.get("siteEntry") or []
            if entry.get("siteUrl")
        ], ""


async def search_analytics(
    *,
    domain: str,
    site_url: str = "",
    days: int = 28,
    dimensions: list[str] | None = None,
    row_limit: int = 5000,
    search_type: str = "web",
) -> GscResult:
    """Fetch real measured performance.

    ``dimensions`` defaults to ``["query"]``. Use ``["query", "page"]`` to know
    which page is ranking for what, or ``["date"]`` for a trend.
    """
    result = GscResult(site_url=_resolve_site_url(domain, site_url))
    if not is_configured():
        result.error = configuration_hint()
        return result

    dimensions = dimensions or ["query"]
    end = datetime.now(UTC).date() - timedelta(days=2)   # GSC lags ~2 days
    start = end - timedelta(days=days)

    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": dimensions,
        "rowLimit": min(row_limit, 25000),
        "type": search_type,
        "dataState": "final",
    }

    async with PoliteClient(concurrency=2, delay=0.3, timeout=60) as client:
        token, error = await _access_token(client)
        if error:
            result.error = error
            return result

        from urllib.parse import quote

        url = f"{API_BASE}/sites/{quote(result.site_url, safe='')}/searchAnalytics/query"
        data, res = await client.fetch_json(
            url,
            method="POST",
            json=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )

    if not isinstance(data, dict):
        result.error = res.error or f"HTTP {res.status}: {res.text[:300]}"
        return result
    if data.get("error"):
        message = data["error"].get("message", str(data["error"]))
        if "does not have sufficient permission" in message.lower():
            message += (
                " - add the service-account email as a user on the property in "
                "Search Console settings."
            )
        result.error = message
        return result

    for row in data.get("rows") or []:
        keys = row.get("keys") or []
        entry = SearchAnalyticsRow(
            clicks=int(row.get("clicks") or 0),
            impressions=int(row.get("impressions") or 0),
            ctr=float(row.get("ctr") or 0.0),
            position=float(row.get("position") or 0.0),
        )
        for dimension, value in zip(dimensions, keys, strict=False):
            setattr(entry, dimension if dimension != "country" else "country", value)
        result.rows.append(entry)

    log.info(
        "search console: %d rows for %s over %d days", len(result.rows), result.site_url, days
    )
    return result


async def top_queries(*, domain: str, days: int = 28, limit: int = 1000) -> GscResult:
    return await search_analytics(domain=domain, days=days, dimensions=["query"], row_limit=limit)


async def query_page_pairs(*, domain: str, days: int = 28, limit: int = 5000) -> GscResult:
    """Which page ranks for which query - the input for consolidation decisions."""
    return await search_analytics(
        domain=domain, days=days, dimensions=["query", "page"], row_limit=limit
    )


async def daily_trend(*, domain: str, days: int = 90) -> GscResult:
    return await search_analytics(domain=domain, days=days, dimensions=["date"], row_limit=days + 5)
