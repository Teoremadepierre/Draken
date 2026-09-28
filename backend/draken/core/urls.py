"""URL and domain helpers used across the crawler, backlink index and catalog."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse

import tldextract

# Offline-safe: use the snapshot bundled with tldextract, never fetch the PSL.
_extractor = tldextract.TLDExtract(suffix_list_urls=(), fallback_to_snapshot=True)

_TRACKING_PARAMS = re.compile(
    r"^(utm_|fbclid|gclid|gbraid|wbraid|msclkid|mc_cid|mc_eid|ref|ref_src|igshid|_ga)", re.I
)


def normalize_domain(value: str) -> str:
    """``https://WWW.Example.co.uk/path`` -> ``example.co.uk``."""
    if not value:
        return ""
    value = value.strip()
    if "//" not in value:
        value = f"http://{value}"
    host = urlparse(value).netloc or urlparse(value).path
    host = host.split("@")[-1].split(":")[0].lower().rstrip(".")
    parts = _extractor(host)
    if parts.registered_domain:
        return parts.registered_domain
    # Suffix not in the public suffix list (a reserved TLD like .example, an
    # internal .local, a brand-new gTLD the snapshot predates). Fall back to the
    # last two labels so "www.a.example" and "a.example" still compare equal.
    labels = [label for label in host.split(".") if label]
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def subdomain_of(value: str) -> str:
    host = urlparse(value if "//" in value else f"http://{value}").netloc.lower()
    return _extractor(host).subdomain


def normalize_url(url: str, *, drop_fragment: bool = True, drop_tracking: bool = True) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower().rstrip(".")
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = re.sub(r"/{2,}", "/", parsed.path) or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    query = parsed.query
    if drop_tracking and query:
        kept = [
            pair
            for pair in query.split("&")
            if pair and not _TRACKING_PARAMS.match(pair.split("=", 1)[0])
        ]
        query = "&".join(sorted(kept))
    fragment = "" if drop_fragment else parsed.fragment
    return urlunparse((scheme, netloc, path, parsed.params, query, fragment))


def same_site(a: str, b: str) -> bool:
    return normalize_domain(a) == normalize_domain(b) and bool(normalize_domain(a))


def absolutize(base: str, href: str) -> str:
    try:
        return urljoin(base, href)
    except Exception:
        return ""


def is_http_url(url: str) -> bool:
    return urlparse(url).scheme in {"http", "https"}


def url_depth(url: str) -> int:
    path = urlparse(url).path.strip("/")
    return 0 if not path else len(path.split("/"))


def is_probably_binary(url: str) -> bool:
    return bool(
        re.search(
            r"\.(pdf|zip|rar|7z|tar|gz|mp4|mp3|avi|mov|wmv|dmg|exe|iso|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|eot|css|js|json|xml)$",
            urlparse(url).path,
            re.I,
        )
    )
