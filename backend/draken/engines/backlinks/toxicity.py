"""Link toxicity scoring - which links are worth disavowing or removing.

The model is a transparent additive one: every point of toxicity has a reason
string attached, because "this link is 73% toxic" is useless without the why.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from draken.core.urls import normalize_domain
from draken.data import loader


def score_link(
    *,
    source_url: str,
    source_domain: str = "",
    anchor_text: str = "",
    link_type: str = "unknown",
    domain_authority: float = 0.0,
    is_sitewide: bool = False,
    target_domain: str = "",
) -> tuple[float, list[str]]:
    """Return ``(toxicity 0-100, reasons)``."""
    rules = loader.toxicity_rules()
    domain = normalize_domain(source_domain or source_url)
    url_l = (source_url or "").lower()
    anchor_l = (anchor_text or "").lower()
    reasons: list[str] = []
    score = 0.0

    if any(domain.endswith(tld) for tld in rules.get("spam_tld", [])):
        score += 22
        reasons.append("Domain uses a TLD heavily associated with spam")

    for pattern in rules.get("spam_patterns", []):
        if pattern in domain or pattern in url_l:
            score += 30
            reasons.append(f"URL or domain contains the spam marker '{pattern}'")
            break

    for pattern in rules.get("low_value_patterns", []):
        if pattern in url_l:
            score += 12
            reasons.append(f"Link sits on a low-value page type ({pattern})")
            break

    if domain_authority and domain_authority < 12:
        score += 18
        reasons.append(f"Very low domain authority ({domain_authority:.0f})")
    elif domain_authority and domain_authority < 22:
        score += 8
        reasons.append(f"Low domain authority ({domain_authority:.0f})")

    if is_sitewide:
        score += 14
        reasons.append("Sitewide/footer link - a classic paid-link footprint")

    if domain.count("-") >= 3:
        score += 10
        reasons.append("Domain is heavily hyphenated (exact-match-domain pattern)")

    if re.search(r"\d{4,}", domain):
        score += 6
        reasons.append("Domain contains a long numeric string")

    # Over-optimised commercial anchors from weak domains are the main risk signal.
    commercial = {"buy", "cheap", "best price", "discount", "for sale", "order now",
                  "comprar", "barato", "mejor precio"}
    if any(c in anchor_l for c in commercial) and domain_authority < 40:
        score += 12
        reasons.append("Over-optimised commercial anchor on a weak domain")

    if anchor_l and target_domain:
        # Anchor that is an exact naked keyword match with no brand present.
        if len(anchor_l.split()) <= 4 and normalize_domain(target_domain).split(".")[0] not in anchor_l:
            score += 4

    path = urlparse(url_l).path
    if path.count("/") > 7:
        score += 5
        reasons.append("Link buried very deep in the site structure")

    if link_type in {"nofollow", "ugc", "sponsored"}:
        # Not toxic, just non-transferring; reduce the penalty since it can't hurt rankings.
        score *= 0.55
        reasons.append(f"Link is {link_type}, so risk is limited")

    return round(min(100.0, max(0.0, score)), 1), reasons


def spam_score(domain: str, *, domain_authority: float = 0.0) -> float:
    """Domain-level spam probability, independent of a specific link."""
    score, _ = score_link(
        source_url=f"https://{domain}/",
        source_domain=domain,
        domain_authority=domain_authority,
    )
    return score


def classify_action(toxicity: float, *, link_type: str = "unknown") -> str:
    """What to actually do about a link."""
    if toxicity >= 70:
        return "disavow"
    if toxicity >= 50:
        return "request_removal"
    if toxicity >= 30:
        return "monitor"
    return "keep"
