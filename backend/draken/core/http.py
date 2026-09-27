"""Shared polite HTTP client.

Every outbound request in Draken goes through here so that user-agent,
timeouts, retries and per-host rate limiting are enforced in exactly one place.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field

import httpx

from draken.core.config import settings
from draken.core.logging import get_logger
from draken.core.urls import normalize_domain

log = get_logger(__name__)

_RETRYABLE = {429, 500, 502, 503, 504}


@dataclass
class HostThrottle:
    """Per-host minimum delay between requests."""

    delay: float
    _last: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    def _lock(self, host: str) -> asyncio.Lock:
        if host not in self._locks:
            self._locks[host] = asyncio.Lock()
        return self._locks[host]

    async def wait(self, url: str) -> None:
        host = normalize_domain(url) or url
        async with self._lock(host):
            elapsed = time.monotonic() - self._last[host]
            if elapsed < self.delay:
                await asyncio.sleep(self.delay - elapsed)
            self._last[host] = time.monotonic()


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    text: str
    headers: dict
    elapsed_ms: int
    error: str = ""
    redirect_chain: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.error and 200 <= self.status < 300


class PoliteClient:
    """Async HTTP client with throttling and bounded retries."""

    def __init__(
        self,
        *,
        concurrency: int | None = None,
        delay: float | None = None,
        timeout: float | None = None,
        user_agent: str | None = None,
        follow_redirects: bool = True,
    ) -> None:
        self.semaphore = asyncio.Semaphore(concurrency or settings.crawl_concurrency)
        self.throttle = HostThrottle(delay if delay is not None else settings.crawl_delay_seconds)
        self.timeout = timeout or settings.request_timeout
        self.user_agent = user_agent or settings.user_agent
        self.follow_redirects = follow_redirects
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> PoliteClient:
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=self.follow_redirects,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en;q=0.9,*;q=0.5",
            },
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("PoliteClient must be used as an async context manager")
        return self._client

    async def fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        retries: int = 2,
        max_bytes: int = 3_000_000,
        **kwargs,
    ) -> FetchResult:
        last_error = ""
        for attempt in range(retries + 1):
            await self.throttle.wait(url)
            started = time.monotonic()
            try:
                async with self.semaphore:
                    resp = await self.client.request(method, url, **kwargs)
                elapsed = int((time.monotonic() - started) * 1000)
                body = resp.text if len(resp.content) <= max_bytes else resp.text[:max_bytes]
                result = FetchResult(
                    url=url,
                    final_url=str(resp.url),
                    status=resp.status_code,
                    text=body,
                    headers=dict(resp.headers),
                    elapsed_ms=elapsed,
                    redirect_chain=[str(r.url) for r in resp.history],
                )
                if resp.status_code in _RETRYABLE and attempt < retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    last_error = f"HTTP {resp.status_code}"
                    continue
                return result
            except Exception as exc:  # noqa: BLE001 - network errors are expected
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
        log.debug("fetch failed url=%s error=%s", url, last_error)
        return FetchResult(url, url, 0, "", {}, 0, error=last_error)

    async def fetch_json(self, url: str, **kwargs) -> tuple[dict | list | None, FetchResult]:
        res = await self.fetch(url, **kwargs)
        if not res.ok:
            return None, res
        import json

        try:
            return json.loads(res.text), res
        except Exception:
            # Some suggest endpoints return JSONP or non-strict JSON.
            return None, res

    async def head_status(self, url: str) -> int:
        res = await self.fetch(url, method="HEAD", retries=0)
        if res.status in (0, 405, 403):
            res = await self.fetch(url, method="GET", retries=0)
        return res.status
