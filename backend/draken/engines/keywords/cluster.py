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


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    # Overlap coefficient: a 2-word term inside a 5-word term should still match.
    return inter / min(len(a), len(b))


def cluster_keywords(
    keywords: list[dict],
    *,
    threshold: float = 0.6,
    max_clusters: int = 300,
) -> list[Cluster]:
    """Group keyword dicts (``term``, ``volume``, ``difficulty``, ``intent``).

    Seeds clusters from the highest-volume keywords so the label is the head term
    rather than an arbitrary long-tail phrase.
    """
    prepared = []
    for kw in keywords:
        term = (kw.get("term") or "").strip().lower()
        if not term:
            continue
        prepared.append({**kw, "term": term, "_tokens": content_tokens(term)})

    prepared.sort(key=lambda k: (-int(k.get("volume", 0)), len(k["_tokens"]), k["term"]))

    clusters: list[Cluster] = []
    for kw in prepared:
        tokens = kw["_tokens"]
        if not tokens:
            continue
        best: Cluster | None = None
        best_score = 0.0
        for c in clusters:
            score = _similarity(tokens, c.signature)
            if score > best_score:
                best, best_score = c, score
        member = {k: v for k, v in kw.items() if k != "_tokens"}
        if best is not None and best_score >= threshold:
            best.members.append(member)
            # Keep the signature tight: only tokens shared by most members.
            best.signature &= tokens if len(best.members) <= 2 else best.signature
            if not best.signature:
                best.signature = tokens
        elif len(clusters) < max_clusters:
            clusters.append(
                Cluster(label=kw["term"], head_term=kw["term"], members=[member], signature=set(tokens))
            )
        else:
            # Catalogue overflow into the nearest cluster rather than dropping it.
            (best or clusters[0]).members.append(member)

    for c in clusters:
        c.label = _label_for(c)
    clusters.sort(key=lambda c: (-c.total_volume, -len(c.members)))
    return clusters


def _label_for(cluster: Cluster) -> str:
    """Name a cluster after the tokens its members actually share."""
    counts: Counter[str] = Counter()
    for m in cluster.members:
        counts.update(content_tokens(m["term"]))
    if not counts:
        return cluster.head_term
    threshold = max(1, len(cluster.members) // 2)
    shared = [t for t, n in counts.most_common() if n >= threshold]
    if not shared:
        return cluster.head_term
    # Preserve the word order of the head term for readability.
    head_tokens = [t for t in tokenize(cluster.head_term) if _normalize(t) in set(shared[:4])]
    return " ".join(head_tokens) if head_tokens else " ".join(shared[:3])


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
