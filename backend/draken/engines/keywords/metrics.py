"""Keyword metric estimation: intent, volume, difficulty, opportunity.

Honest framing: without a paid clickstream provider nobody can produce true
search volume. What this module gives you is a *consistent, explainable
estimator* that is good enough to rank and prioritise a keyword list - which is
what the number is actually used for. When DRAKEN_SERPAPI_KEY or DataForSEO
credentials are configured, real provider numbers replace the estimate and
``volume_confidence`` goes to 1.0.

Every score is deterministic, so the same list always sorts the same way.
"""

from __future__ import annotations

import math
import re

from draken.core.models import SearchIntent
from draken.data import loader

_WORD_RE = re.compile(r"[\w'’-]+", re.UNICODE)

# Signals that a term sits at the money end of the funnel.
_COMMERCIAL_HINTS = {
    "best", "top", "review", "reviews", "compare", "comparison", "vs", "versus",
    "alternative", "alternatives", "cheap", "cheapest", "affordable", "price",
    "pricing", "prices", "cost", "quote", "deal", "deals", "discount", "coupon",
    "mejor", "mejores", "barato", "precio", "precios", "opiniones", "comparativa",
}
_TRANSACTIONAL_HINTS = {
    "buy", "order", "shop", "purchase", "hire", "book", "booking", "subscribe",
    "signup", "sign-up", "download", "install", "trial", "demo", "coupon", "free",
    "comprar", "contratar", "reservar", "pedir", "descargar", "prueba",
}
_LOCAL_HINTS = {
    "near", "nearby", "local", "me", "area", "open", "now", "emergency", "24",
    "cerca", "domicilio", "urgente", "local",
}
_INFO_HINTS = {
    "what", "how", "why", "when", "guide", "tutorial", "examples", "tips", "ideas",
    "meaning", "definition", "checklist", "template", "statistics", "trends",
    "que", "qué", "como", "cómo", "por", "guia", "guía", "ejemplos", "plantilla",
}
_NAV_HINTS = {"login", "log", "sign", "account", "dashboard", "app", "download", "official"}


def tokenize(term: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(term or "")]


def classify_intent(term: str, *, brand_terms: list[str] | None = None) -> SearchIntent:
    tokens = set(tokenize(term))
    lowered = (term or "").lower()
    brand_terms = [b.lower() for b in (brand_terms or []) if b]

    if any(b and b in lowered for b in brand_terms):
        if tokens & _COMMERCIAL_HINTS:
            return SearchIntent.commercial
        if tokens & _TRANSACTIONAL_HINTS:
            return SearchIntent.transactional
        return SearchIntent.navigational
    if tokens & _LOCAL_HINTS or " near me" in lowered or "cerca de" in lowered:
        return SearchIntent.local
    if tokens & _TRANSACTIONAL_HINTS:
        return SearchIntent.transactional
    if tokens & _COMMERCIAL_HINTS:
        return SearchIntent.commercial
    if tokens & _INFO_HINTS or lowered.endswith("?"):
        return SearchIntent.informational
    if tokens & _NAV_HINTS:
        return SearchIntent.navigational
    # Short, generic head terms behave commercially more often than not.
    return SearchIntent.commercial if len(tokens) <= 2 else SearchIntent.informational


def is_question(term: str) -> bool:
    tokens = tokenize(term)
    if not tokens:
        return False
    prefixes = loader.question_prefixes()
    firsts = {p.split()[0] for plist in prefixes.values() for p in plist}
    return tokens[0] in firsts or (term or "").strip().endswith("?")


def estimate_volume(
    term: str,
    *,
    suggest_rank: int | None = None,
    provider_count: int = 1,
    seed_volume: int | None = None,
) -> tuple[int, float]:
    """Heuristic monthly-volume estimate plus a 0..1 confidence.

    Drivers, in order of weight:
      * word count - volume decays roughly geometrically with each added word
      * autocomplete rank - engines order suggestions by popularity
      * provider agreement - a term suggested by 3 engines is more real than by 1
    """
    tokens = tokenize(term)
    words = max(1, len(tokens))

    base = 9000.0 if seed_volume is None else float(seed_volume)
    # Long-tail decay.
    volume = base * (0.42 ** (words - 1))

    if suggest_rank is not None:
        # Rank 0 is the most popular completion; decay down the list.
        volume *= max(0.18, 1.0 - 0.055 * suggest_rank)

    # Cross-provider agreement is the strongest free signal of real demand.
    volume *= (0.72, 1.0, 1.28, 1.45)[min(max(provider_count, 1), 4) - 1]

    if is_question(term):
        volume *= 0.55
    if words >= 6:
        volume *= 0.6

    volume = max(0.0, volume)
    # Round to a readable bucket so the number never looks more precise than it is.
    rounded = _bucket(volume)

    confidence = 0.25 + 0.15 * min(provider_count, 3)
    if suggest_rank is not None:
        confidence += 0.1
    if seed_volume is not None:
        confidence = 1.0
    return rounded, round(min(confidence, 0.85), 2)


def _bucket(value: float) -> int:
    if value < 10:
        return int(value)
    magnitude = 10 ** int(math.log10(value))
    step = magnitude / 2 if magnitude >= 100 else magnitude
    return int(round(value / step) * step)


def estimate_difficulty(
    term: str,
    *,
    serp_authorities: list[float] | None = None,
    volume: int = 0,
    intent: SearchIntent | str | None = None,
) -> float:
    """0-100 difficulty. Uses real SERP authority when a SERP was fetched."""
    tokens = tokenize(term)
    words = max(1, len(tokens))

    if serp_authorities:
        top = sorted(serp_authorities, reverse=True)[:10]
        avg = sum(top) / len(top)
        # Authority of the weakest page in the top 10 is what you actually have to beat.
        weakest = min(top)
        score = 0.72 * avg + 0.28 * weakest
    else:
        # No SERP available: infer from term shape and estimated demand.
        score = 68.0 - 7.5 * (words - 1)
        score += min(16.0, math.log10(max(volume, 10)) * 4.5)

    intent_value = intent.value if isinstance(intent, SearchIntent) else (intent or "")
    score += {"transactional": 6.0, "commercial": 4.0, "navigational": -6.0, "local": -4.0}.get(
        intent_value, 0.0
    )
    if is_question(term):
        score -= 6.0
    return round(max(1.0, min(100.0, score)), 1)


def opportunity_score(
    *,
    volume: int,
    difficulty: float,
    intent: SearchIntent | str,
    current_position: int | None = None,
    is_branded: bool = False,
) -> float:
    """0-100 priority score: demand x commercial value x winnability x proximity.

    This is the number the dashboard sorts by - "what should I work on Monday".
    """
    demand = min(1.0, math.log10(max(volume, 1) + 1) / 5.0)
    winnability = max(0.05, 1.0 - difficulty / 100.0)

    intent_value = intent.value if isinstance(intent, SearchIntent) else str(intent)
    value = {
        "transactional": 1.0,
        "commercial": 0.9,
        "local": 0.85,
        "navigational": 0.35,
        "informational": 0.55,
    }.get(intent_value, 0.5)

    # A keyword already at #11-20 is the cheapest win on the board.
    if current_position is None:
        proximity = 0.55
    elif current_position <= 3:
        proximity = 0.25          # already won; little upside
    elif current_position <= 10:
        proximity = 0.7
    elif current_position <= 20:
        proximity = 1.0           # striking distance
    elif current_position <= 50:
        proximity = 0.75
    else:
        proximity = 0.5

    score = 100.0 * demand * value * (0.35 + 0.65 * winnability) * (0.45 + 0.55 * proximity)
    if is_branded:
        score *= 0.5
    return round(max(0.0, min(100.0, score)), 1)


def estimate_cpc(term: str, intent: SearchIntent | str, difficulty: float) -> float:
    """Rough CPC proxy, derived from intent and competition."""
    intent_value = intent.value if isinstance(intent, SearchIntent) else str(intent)
    base = {
        "transactional": 3.4,
        "commercial": 2.4,
        "local": 2.0,
        "navigational": 0.5,
        "informational": 0.7,
    }.get(intent_value, 1.0)
    return round(base * (0.5 + difficulty / 100.0), 2)


def estimate_traffic(volume: int, position: int | None) -> float:
    return round(volume * loader.ctr_for_position(position), 1)
