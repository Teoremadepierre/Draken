"""Keyword expansion: turn a handful of seeds into a scored keyword universe."""

from __future__ import annotations

import string
from dataclasses import dataclass, field

from draken.core.http import PoliteClient
from draken.core.logging import get_logger
from draken.data import loader
from draken.engines.keywords import metrics, suggest

log = get_logger(__name__)


@dataclass
class ExpandedKeyword:
    term: str
    volume: int = 0
    volume_confidence: float = 0.0
    difficulty: float = 0.0
    opportunity_score: float = 0.0
    cpc: float = 0.0
    competition: float = 0.0
    intent: str = "informational"
    word_count: int = 0
    is_question: bool = False
    is_branded: bool = False
    source: str = "expansion"
    providers: set[str] = field(default_factory=set)
    suggest_rank: int | None = None

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        d["providers"] = sorted(self.providers)
        return d


def _modifier_terms(language: str) -> dict[str, list[str]]:
    mods = loader.keyword_modifiers()
    if language.lower().startswith("es"):
        return {
            "commercial": mods.get("spanish_commercial", []) + mods.get("commercial", []),
            "informational": mods.get("spanish_informational", []) + mods.get("informational", []),
            "local": mods.get("spanish_local", []) + mods.get("local", []),
            "transactional": mods.get("transactional", []),
            "qualifier": mods.get("qualifier", []),
            "comparison": mods.get("comparison", []),
        }
    return {k: v for k, v in mods.items() if not k.startswith("spanish_")}


def build_seed_variants(
    seeds: list[str],
    *,
    language: str = "en",
    include_questions: bool = True,
    include_modifiers: bool = True,
    include_alphabet_soup: bool = False,
) -> list[str]:
    """Construct the query list we will send to the autocomplete providers.

    Autocomplete only returns ~10 completions per query, so the way to get a
    large universe is to ask many differently-prefixed questions.
    """
    variants: list[str] = []
    seen: set[str] = set()

    def push(term: str) -> None:
        term = " ".join(term.split()).lower()
        if term and term not in seen:
            seen.add(term)
            variants.append(term)

    mods = _modifier_terms(language)
    prefixes = loader.question_prefixes()
    q_prefixes = prefixes.get("es" if language.lower().startswith("es") else "en", [])

    for seed in seeds:
        seed = seed.strip().lower()
        if not seed:
            continue
        push(seed)
        if include_modifiers:
            for group in ("commercial", "transactional", "local"):
                for m in mods.get(group, [])[:14]:
                    push(f"{m} {seed}")
            for m in mods.get("qualifier", [])[:14]:
                push(f"{seed} {m}")
            for m in mods.get("comparison", [])[:6]:
                push(f"{seed} {m}")
        if include_questions:
            for q in q_prefixes[:16]:
                push(f"{q} {seed}")
        if include_alphabet_soup:
            for ch in string.ascii_lowercase:
                push(f"{seed} {ch}")
    return variants


async def expand(
    seeds: list[str],
    *,
    country: str = "US",
    language: str = "en",
    include_questions: bool = True,
    include_modifiers: bool = True,
    include_alphabet_soup: bool = False,
    max_results: int = 400,
    use_live_suggest: bool = True,
    brand_terms: list[str] | None = None,
    providers: list[str] | None = None,
) -> list[ExpandedKeyword]:
    """Expand seeds into a deduplicated, scored keyword list."""
    seeds = [s.strip() for s in seeds if s and s.strip()]
    if not seeds:
        return []

    variants = build_seed_variants(
        seeds,
        language=language,
        include_questions=include_questions,
        include_modifiers=include_modifiers,
        include_alphabet_soup=include_alphabet_soup,
    )

    collected: dict[str, ExpandedKeyword] = {}

    def record(term: str, *, source: str, provider: str = "", rank: int | None = None) -> None:
        term = " ".join((term or "").split()).lower()
        if not term or len(term) < 2 or len(term) > 180:
            return
        kw = collected.get(term)
        if kw is None:
            kw = ExpandedKeyword(term=term, source=source)
            collected[term] = kw
        if provider:
            kw.providers.add(provider)
        if rank is not None and (kw.suggest_rank is None or rank < kw.suggest_rank):
            kw.suggest_rank = rank

    # The generated variants are themselves valid keywords.
    for v in variants:
        record(v, source="modifier" if v not in seeds else "seed")

    if use_live_suggest:
        # Cap the number of live queries: politeness plus diminishing returns.
        query_budget = min(len(variants), max(24, max_results // 6))
        queries = variants[:query_budget]
        try:
            async with PoliteClient(delay=0.3, concurrency=6, timeout=12) as client:
                suggestions = await suggest.fetch_suggestions(
                    queries, country=country, language=language,
                    providers=providers, client=client,
                )
            for _seed, terms in suggestions.items():
                for rank, term in enumerate(terms):
                    record(term, source="autocomplete", provider="suggest", rank=rank)
            log.info(
                "keyword expansion: %d queries -> %d unique terms", len(queries), len(collected)
            )
        except Exception as exc:  # noqa: BLE001 - offline must not break the tool
            log.warning("live suggest unavailable (%s); using generated variants only", exc)

    brand_terms = brand_terms or []
    results: list[ExpandedKeyword] = []
    for kw in collected.values():
        tokens = metrics.tokenize(kw.term)
        kw.word_count = len(tokens)
        kw.is_question = metrics.is_question(kw.term)
        kw.is_branded = any(b and b.lower() in kw.term for b in brand_terms)
        intent = metrics.classify_intent(kw.term, brand_terms=brand_terms)
        kw.intent = intent.value
        kw.volume, kw.volume_confidence = metrics.estimate_volume(
            kw.term,
            suggest_rank=kw.suggest_rank,
            provider_count=max(1, len(kw.providers) + (1 if kw.suggest_rank is not None else 0)),
        )
        kw.difficulty = metrics.estimate_difficulty(kw.term, volume=kw.volume, intent=intent)
        kw.cpc = metrics.estimate_cpc(kw.term, intent, kw.difficulty)
        kw.competition = round(min(1.0, kw.difficulty / 100.0), 2)
        kw.opportunity_score = metrics.opportunity_score(
            volume=kw.volume, difficulty=kw.difficulty, intent=intent, is_branded=kw.is_branded
        )
        results.append(kw)

    results.sort(key=lambda k: (-k.opportunity_score, -k.volume, k.term))
    return results[:max_results]
