"""Keyword clustering and topic-map construction.

Approach: lexical clustering on normalised token sets, seeded by the highest
volume terms. It is deterministic, needs no embedding model, and groups the way
an SEO would - by shared head noun plus modifier overlap. Good enough to turn
2,000 keywords into ~80 page briefs, which is the actual job.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from draken.engines.keywords.metrics import tokenize

_STOPWORDS = {
    # English
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "at", "by", "with",
    "is", "are", "be", "do", "does", "how", "what", "why", "when", "where", "which",
    "who", "can", "i", "my", "your", "you", "it", "that", "this", "vs", "versus",
    # Spanish
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "y", "o",
    "para", "por", "en", "con", "es", "son", "que", "como", "cual", "cuales",
    "donde", "cuando", "quien", "se", "mi", "tu", "su", "lo", "al",
    "qué", "cómo", "cuál", "cuáles", "dónde", "cuándo", "quién", "cuanto",
    "cuánto", "cuanta", "cuánta", "más", "mas", "muy", "sin", "sobre",
}

_PLURAL_RE = re.compile(r"(es|s)$")


def _normalize(token: str) -> str:
    """Crude but stable stemming so 'tools' and 'tool' land in one bucket."""
    if len(token) > 4:
        token = _PLURAL_RE.sub("", token)
    return token


def content_tokens(term: str) -> set[str]:
    return {_normalize(t) for t in tokenize(term) if t not in _STOPWORDS and len(t) > 1}


@dataclass
class Cluster:
    label: str
    head_term: str
    members: list[dict] = field(default_factory=list)
    signature: set[str] = field(default_factory=set)

    @property
    def total_volume(self) -> int:
        return sum(int(m.get("volume", 0)) for m in self.members)

    @property
    def avg_difficulty(self) -> float:
        if not self.members:
            return 0.0
        return round(sum(float(m.get("difficulty", 0)) for m in self.members) / len(self.members), 1)

    @property
    def dominant_intent(self) -> str:
        counts = Counter(m.get("intent", "informational") for m in self.members)
        return counts.most_common(1)[0][0] if counts else "informational"

    def recommended_page_type(self) -> str:
        intent = self.dominant_intent
        questions = sum(1 for m in self.members if m.get("is_question"))
        if intent == "transactional":
            return "product / signup page"
        if intent == "commercial":
            if any("vs" in m["term"] or "alternative" in m["term"] for m in self.members):
                return "comparison page"
            return "category / best-of page"
        if intent == "local":
            return "location landing page"
        if intent == "navigational":
            return "brand / docs page"
        if questions >= max(2, len(self.members) // 3):
            return "FAQ / answer hub"
        return "pillar guide"

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "head_term": self.head_term,
            "total_volume": self.total_volume,
            "avg_difficulty": self.avg_difficulty,
            "dominant_intent": self.dominant_intent,
            "keyword_count": len(self.members),
            "recommended_page_type": self.recommended_page_type(),
            "terms": [m["term"] for m in self.members],
            "top_terms": [m["term"] for m in sorted(
                self.members, key=lambda m: -int(m.get("volume", 0))
            )[:8]],
        }


# Intent, price, quality and question modifiers. Stripped when deriving a cluster's
# "core" so that "best seo software", "cheap seo software" and "seo software for
# small business" all resolve to the same topic. Deliberately excludes category
# nouns (software, tool, agency, course, ...) because those ARE head terms.
_MODIFIERS = {
    # English - commercial / transactional
    "best", "top", "cheap", "cheapest", "affordable", "premium", "professional",
    "leading", "trusted", "recommended", "popular", "buy", "order", "hire", "book",
    "booking", "get", "purchase", "shop", "sale", "subscribe", "signup", "download",
    "install", "free", "trial", "demo", "review", "reviews", "rated", "price",
    "prices", "pricing", "cost", "costs", "quote", "quotes", "deal", "deals",
    "discount", "coupon", "compare", "comparison", "versus", "alternative",
    "alternatives", "difference", "differences",
    # English - informational / question
    "guide", "tutorial", "tips", "ideas", "examples", "example", "checklist",
    "template", "templates", "meaning", "definition", "benefits", "types", "type",
    "list", "statistics", "trends", "steps", "way", "ways",
    # English - local / qualifier
    "near", "nearby", "local", "area", "online", "emergency", "same", "day",
    "hour", "hours", "beginners", "beginner", "small", "startups", "enterprise",
    "ecommerce", "agencies", "nonprofits", "business", "businesses", "teams",
    "team", "2025", "2026", "2027",
    # Spanish
    "mejor", "mejores", "barato", "baratos", "barata", "baratas", "precio",
    "precios", "comparativa", "opiniones", "resenas", "reseñas", "gratis",
    "gratuito", "oferta", "ofertas", "descuento", "presupuesto", "comprar",
    "contratar", "reservar", "pedir", "descargar", "prueba", "guia", "guía",
    "ejemplos", "ejemplo", "tipos", "ventajas", "pasos", "plantilla", "plantillas",
    "cerca", "domicilio", "urgente", "sirve", "significa",
}

# Category nouns that are too generic to be a cluster on their own.
_WEAK_CORE = {"software", "tool", "tools", "platform", "app", "service", "services",
              "company", "companies", "agency", "solution", "solutions", "system"}


# content_tokens() stems its output, so the modifier set has to be stemmed the same
# way or entries like "gratis" -> "grati" would never match and would leak into labels.
_MODIFIERS_STEMMED = {_normalize(m) for m in _MODIFIERS} | _MODIFIERS
_WEAK_CORE_STEMMED = {_normalize(w) for w in _WEAK_CORE} | _WEAK_CORE


def core_tokens(term: str) -> set[str]:
    """The topic-bearing tokens of a term, with modifiers stripped."""
    tokens = content_tokens(term)
    core = {t for t in tokens if t not in _MODIFIERS_STEMMED}
    # Never return an empty core: fall back progressively.
    if not core:
        return tokens
    if core <= _WEAK_CORE_STEMMED and len(tokens) > len(core):
        return tokens - _MODIFIERS_STEMMED or tokens
    return core


def _similarity(a: set[str], b: set[str]) -> float:
    """Jaccard similarity. Unlike an overlap coefficient it will not let a
    one-token signature swallow every longer term that happens to contain it."""
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def cluster_keywords(
    keywords: list[dict],
    *,
    threshold: float = 0.6,
    max_clusters: int = 300,
) -> list[Cluster]:
    """Group keyword dicts (``term``, ``volume``, ``difficulty``, ``intent``).

    Two passes:

    1. Bucket by exact core-token signature. This is what puts "best seo software",
       "seo software pricing" and "software seo barato" in one place.
    2. Merge buckets whose cores are similar enough (Jaccard >= ``threshold``),
       largest first, so near-identical topics do not end up as separate briefs.

    Deterministic: the same input always produces the same clusters.
    """
    prepared: list[dict] = []
    for kw in keywords:
        term = (kw.get("term") or "").strip().lower()
        if not term:
            continue
        core = core_tokens(term)
        if not core:
            continue
        prepared.append({**kw, "term": term, "_core": core})

    if not prepared:
        return []

    prepared.sort(key=lambda k: (-int(k.get("volume", 0)), len(k["_core"]), k["term"]))

    # --- pass 1: exact core signature ------------------------------------
    buckets: dict[frozenset[str], Cluster] = {}
    for kw in prepared:
        signature = frozenset(kw["_core"])
        member = {k: v for k, v in kw.items() if k != "_core"}
        bucket = buckets.get(signature)
        if bucket is None:
            buckets[signature] = Cluster(
                label=kw["term"], head_term=kw["term"], members=[member], signature=set(signature)
            )
        else:
            bucket.members.append(member)

    clusters = sorted(buckets.values(), key=lambda c: (-c.total_volume, -len(c.members)))

    # --- pass 2: merge near-duplicate cores ------------------------------
    merged: list[Cluster] = []
    for cluster in clusters:
        target: Cluster | None = None
        best_score = 0.0
        for candidate in merged:
            score = _similarity(cluster.signature, candidate.signature)
            if score > best_score:
                target, best_score = candidate, score
        if target is not None and best_score >= threshold:
            target.members.extend(cluster.members)
            target.signature |= cluster.signature
        elif len(merged) < max_clusters:
            merged.append(cluster)
        else:
            (target or merged[0]).members.extend(cluster.members)

    for c in merged:
        c.label = _label_for(c)
    merged.sort(key=lambda c: (-c.total_volume, -len(c.members)))
    return merged


def _label_for(cluster: Cluster) -> str:
    """Name a cluster after the core tokens most of its members share."""
    counts: Counter[str] = Counter()
    for m in cluster.members:
        counts.update(core_tokens(m["term"]))
    if not counts:
        return cluster.head_term
    cutoff = max(1, len(cluster.members) // 2)
    shared = {t for t, n in counts.most_common() if n >= cutoff}
    if not shared:
        shared = {t for t, _ in counts.most_common(3)}
    # Preserve the head term's word order so the label reads naturally.
    head_tokens = [t for t in tokenize(cluster.head_term) if _normalize(t) in shared]
    if head_tokens:
        return " ".join(dict.fromkeys(head_tokens))
    return " ".join(sorted(shared)[:3])


def build_topic_map(clusters: list[Cluster]) -> list[dict]:
    """Group clusters into pillar/supporting structure for internal linking."""
    by_root: dict[str, list[Cluster]] = defaultdict(list)
    for c in clusters:
        tokens = [t for t in tokenize(c.label) if t not in _STOPWORDS]
        root = _normalize(tokens[-1]) if tokens else c.label
        by_root[root].append(c)

    topics = []
    for root, group in by_root.items():
        group.sort(key=lambda c: -c.total_volume)
        pillar = group[0]
        topics.append(
            {
                "topic": root,
                "pillar": pillar.as_dict(),
                "supporting": [c.as_dict() for c in group[1:]],
                "total_volume": sum(c.total_volume for c in group),
                "cluster_count": len(group),
                "internal_links_needed": max(0, len(group) - 1) * 2,
            }
        )
    topics.sort(key=lambda t: -t["total_volume"])
    return topics
