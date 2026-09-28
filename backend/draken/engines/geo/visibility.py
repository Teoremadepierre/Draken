"""AI visibility measurement and scoring (GEO - generative engine optimisation).

What we measure, per prompt and engine:
  * was the brand mentioned at all
  * how early (position in the answer is a strong proxy for recommendation strength)
  * was our domain actually cited as a source
  * which competitors were named alongside us
  * in what tone

From those we derive a per-run visibility score and a share of voice against the
competitor set, which is the number worth tracking over time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from draken.core.urls import normalize_domain
from draken.data import loader

_POSITIVE = {
    "best", "excellent", "great", "recommended", "reliable", "leading", "strong",
    "popular", "trusted", "powerful", "impressive", "solid", "top", "favourite",
    "favorite", "robust", "mejor", "excelente", "recomendado", "fiable", "potente",
}
_NEGATIVE = {
    "worst", "poor", "avoid", "unreliable", "outdated", "expensive", "limited",
    "lacking", "buggy", "disappointing", "weak", "caution", "complaints", "scam",
    "peor", "evitar", "caro", "limitado", "deficiente",
}


@dataclass
class RunAnalysis:
    engine: str
    model: str = ""
    answer: str = ""
    brand_mentioned: bool = False
    brand_position: int | None = None
    domain_cited: bool = False
    citations: list[str] = field(default_factory=list)
    cited_domains: list[str] = field(default_factory=list)
    competitors_mentioned: list[str] = field(default_factory=list)
    sentiment: str = "neutral"
    visibility_score: float = 0.0
    share_of_voice: float = 0.0
    error: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def name_variants(identifier: str) -> list[str]:
    """Plausible written forms of a brand given a domain or a name.

    ``search-engine-journal.com`` is written "Search Engine Journal" in prose, so
    matching only the raw domain label would miss almost every real mention.
    """
    out: list[str] = []
    raw = (identifier or "").strip()
    if not raw:
        return out
    out.append(raw)
    label = normalize_domain(raw).split(".")[0] if "." in raw else raw
    if label:
        out.append(label)
        if "-" in label:
            out.append(label.replace("-", " "))
            out.append(label.replace("-", ""))
        if "_" in label:
            out.append(label.replace("_", " "))
    # Longest first so a specific form wins over a substring of it.
    return sorted(dict.fromkeys(v for v in out if len(v) >= 2), key=len, reverse=True)


def _mention_index(text: str, terms: list[str]) -> int | None:
    """Character index of the earliest mention of any of ``terms``."""
    low = text.lower()
    best: int | None = None
    for term in terms:
        t = (term or "").strip().lower()
        if not t:
            continue
        # Word-boundary match so 'ace' does not match 'space'.
        m = re.search(rf"(?<![a-z0-9]){re.escape(t)}(?![a-z0-9])", low)
        if m and (best is None or m.start() < best):
            best = m.start()
    return best


def _ordinal_position(text: str, brand_terms: list[str], competitors: list[str]) -> int | None:
    """Where the brand sits in the list of named entities - 1 is first mentioned."""
    entities: list[tuple[int, str]] = []
    brand_idx = _mention_index(text, brand_terms)
    if brand_idx is None:
        return None
    entities.append((brand_idx, "__brand__"))
    for comp in competitors:
        idx = _mention_index(text, name_variants(comp))
        if idx is not None:
            entities.append((idx, comp))
    entities.sort(key=lambda e: e[0])
    for rank, (_idx, name) in enumerate(entities, start=1):
        if name == "__brand__":
            return rank
    return None


def _sentiment_near(text: str, brand_terms: list[str], window: int = 320) -> str:
    idx = _mention_index(text, brand_terms)
    if idx is None:
        return "neutral"
    segment = text[max(0, idx - window // 2) : idx + window].lower()
    tokens = set(re.findall(r"[a-záéíóúñü]+", segment))
    pos = len(tokens & _POSITIVE)
    neg = len(tokens & _NEGATIVE)
    if pos > neg + 1:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def visibility_score(
    *,
    brand_mentioned: bool,
    brand_position: int | None,
    domain_cited: bool,
    sentiment: str,
    competitor_count: int,
) -> float:
    """0-100. Being cited as a source is weighted heavily: that is the durable win."""
    if not brand_mentioned and not domain_cited:
        return 0.0
    score = 0.0
    if brand_mentioned:
        score += 34.0
        if brand_position == 1:
            score += 26.0
        elif brand_position == 2:
            score += 18.0
        elif brand_position == 3:
            score += 12.0
        elif brand_position:
            score += max(2.0, 10.0 - brand_position)
    if domain_cited:
        score += 30.0          # an actual link in the answer
    score += {"positive": 10.0, "neutral": 0.0, "negative": -14.0}[sentiment]
    if competitor_count >= 5 and brand_mentioned:
        score -= 6.0           # named in a crowd counts for less
    return round(max(0.0, min(100.0, score)), 1)


def analyse_answer(
    *,
    engine: str,
    model: str,
    answer: str,
    citations: list[str],
    brand_terms: list[str],
    domain: str,
    competitors: list[str],
    error: str = "",
) -> RunAnalysis:
    result = RunAnalysis(engine=engine, model=model, answer=answer, error=error)
    if error or not answer:
        return result

    domain = normalize_domain(domain)
    terms: list[str] = []
    for candidate in (brand_terms or []) or [domain]:
        terms.extend(name_variants(candidate))
    terms = sorted(dict.fromkeys(terms), key=len, reverse=True)

    result.brand_mentioned = _mention_index(answer, terms) is not None
    result.brand_position = _ordinal_position(answer, terms, competitors or [])

    result.citations = list(dict.fromkeys(c for c in (citations or []) if c))
    result.cited_domains = list(
        dict.fromkeys(d for d in (normalize_domain(c) for c in result.citations) if d)
    )
    result.domain_cited = domain in result.cited_domains or domain in answer.lower()

    named: list[str] = []
    for comp in competitors or []:
        if _mention_index(answer, name_variants(comp)) is not None:
            named.append(normalize_domain(comp) or comp)
    result.competitors_mentioned = named

    result.sentiment = _sentiment_near(answer, terms)
    result.visibility_score = visibility_score(
        brand_mentioned=result.brand_mentioned,
        brand_position=result.brand_position,
        domain_cited=result.domain_cited,
        sentiment=result.sentiment,
        competitor_count=len(named),
    )
    total_named = len(named) + (1 if result.brand_mentioned else 0)
    result.share_of_voice = round(1.0 / total_named, 3) if total_named and result.brand_mentioned else 0.0
    return result


# ---------------------------------------------------------------------------
# prompt-set generation
# ---------------------------------------------------------------------------


def generate_prompts(
    *,
    brand: str,
    category: str,
    competitors: list[str] | None = None,
    city: str = "",
    audience: str = "",
    use_case: str = "",
    keywords: list[str] | None = None,
    language: str = "en",
    year: int = 2026,
    limit: int = 40,
) -> list[dict]:
    """Build the prompt set a real buyer would type into an assistant."""
    templates = loader.geo_prompt_templates()
    is_es = language.lower().startswith("es")
    groups = (
        ["discovery_es", "brand_es", "local_es", "discovery", "comparison", "brand", "problem"]
        if is_es
        else ["discovery", "comparison", "brand", "problem", "local"]
    )
    competitors = [c for c in (competitors or []) if c]
    out: list[dict] = []
    seen: set[str] = set()

    def push(text: str, group: str) -> None:
        text = " ".join(text.split())
        if "{" in text or not text or text.lower() in seen:
            return
        seen.add(text.lower())
        out.append(
            {
                "prompt": text,
                "category": group.replace("_es", ""),
                "intent": {
                    "discovery": "commercial", "comparison": "commercial",
                    "brand": "navigational", "problem": "informational", "local": "local",
                }.get(group.replace("_es", ""), "commercial"),
                "language": "es" if group.endswith("_es") else language,
                "priority": {"discovery": 1, "comparison": 2, "brand": 2, "problem": 3, "local": 2}.get(
                    group.replace("_es", ""), 3
                ),
            }
        )

    def context_for(group: str) -> dict:
        """Defaults follow the template's own language, not the project's."""
        group_is_es = group.endswith("_es")
        default_audience = "pymes" if group_is_es else "small businesses"
        return {
            "brand": brand,
            "category": category,
            "city": city,
            "audience": audience or default_audience,
            "use_case": use_case or category,
            "year": str(year),
            "job_to_be_done": use_case or category,
            "pain_point": use_case or category,
        }

    for group in groups:
        base_ctx = context_for(group)
        for template in templates.get(group, []):
            if "{competitor}" in template:
                for comp in competitors[:3]:
                    ctx = {**base_ctx, "competitor": normalize_domain(comp).split(".")[0] or comp}
                    push(_fill(template, ctx), group)
            elif "{city}" in template and not city:
                continue
            else:
                push(_fill(template, base_ctx), group)

    # Keyword-derived prompts: the actual questions people search for.
    for kw in (keywords or [])[:40]:
        kw = kw.strip()
        if not kw:
            continue
        if is_es:
            push(f"¿Cuál es la mejor opción para {kw}?", "discovery_es")
            push(f"¿Cómo elegir {kw}?", "problem")
        else:
            push(f"What is the best option for {kw}?", "discovery")
            push(f"How do I choose {kw}?", "problem")
        if len(out) >= limit * 2:
            break

    out.sort(key=lambda p: (p["priority"], p["category"]))
    return out[:limit]


def _fill(template: str, ctx: dict) -> str:
    text = template
    for key, value in ctx.items():
        text = text.replace("{" + key + "}", str(value or ""))
    return text


# ---------------------------------------------------------------------------
# aggregate reporting
# ---------------------------------------------------------------------------


def summarise(
    runs: list[dict],
    *,
    prompts_tracked: int,
    competitors: list[str] | None = None,
    engines_configured: dict | None = None,
    uncovered: list[dict] | None = None,
) -> dict:
    """Roll individual runs up into the dashboard summary."""
    valid = [r for r in runs if not r.get("error")]
    total = len(valid)
    mentioned = sum(1 for r in valid if r.get("brand_mentioned"))
    cited = sum(1 for r in valid if r.get("domain_cited"))
    scores = [float(r.get("visibility_score") or 0) for r in valid]

    by_engine: dict[str, dict] = {}
    for r in valid:
        e = r.get("engine", "unknown")
        row = by_engine.setdefault(
            e, {"engine": e, "runs": 0, "mentions": 0, "citations": 0, "score_sum": 0.0}
        )
        row["runs"] += 1
        row["mentions"] += 1 if r.get("brand_mentioned") else 0
        row["citations"] += 1 if r.get("domain_cited") else 0
        row["score_sum"] += float(r.get("visibility_score") or 0)
    engine_rows = [
        {
            "engine": row["engine"],
            "runs": row["runs"],
            "mention_rate": round(row["mentions"] / row["runs"], 3),
            "citation_rate": round(row["citations"] / row["runs"], 3),
            "avg_visibility_score": round(row["score_sum"] / row["runs"], 1),
        }
        for row in sorted(by_engine.values(), key=lambda r: -r["score_sum"])
    ]

    # Competitor share of voice: how often each rival is named in our own prompt set.
    comp_counts: dict[str, int] = {}
    for r in valid:
        for comp in r.get("competitors_mentioned") or []:
            comp_counts[comp] = comp_counts.get(comp, 0) + 1
    denominator = max(1, total)
    competitor_share = sorted(
        (
            {"competitor": c, "mentions": n, "share": round(n / denominator, 3)}
            for c, n in comp_counts.items()
        ),
        key=lambda r: -r["mentions"],
    )

    own_share = round(mentioned / denominator, 3) if total else 0.0

    return {
        "prompts_tracked": prompts_tracked,
        "runs": total,
        "mention_rate": own_share,
        "citation_rate": round(cited / denominator, 3) if total else 0.0,
        "avg_visibility_score": round(sum(scores) / total, 1) if total else 0.0,
        "share_of_voice": own_share,
        "by_engine": engine_rows,
        "competitor_share": competitor_share,
        "uncovered_prompts": uncovered or [],
        "engines_configured": engines_configured or {},
        "recommendations": recommendations(
            mention_rate=own_share,
            citation_rate=round(cited / denominator, 3) if total else 0.0,
            competitor_share=competitor_share,
            runs=total,
        ),
    }


def recommendations(
    *, mention_rate: float, citation_rate: float, competitor_share: list[dict], runs: int
) -> list[str]:
    out: list[str] = []
    if runs == 0:
        return [
            "No runs yet. Configure at least one AI engine API key and run the prompt set to get a baseline."
        ]

    if mention_rate < 0.1:
        out.append(
            f"You are named in only {mention_rate:.0%} of answers. Models name entities they have "
            "read about in sources they trust. The fastest levers, in order: get listed and reviewed "
            "on the review platforms (G2, Trustpilot, Capterra), get a Wikidata item once you have "
            "independent references, and answer real questions on Reddit and Stack Exchange."
        )
    elif mention_rate < 0.4:
        out.append(
            f"Mentioned in {mention_rate:.0%} of answers. You are on the map but not the default. "
            "Publish comparison pages that state plainly who you are and are not for - models quote "
            "explicit, structured positioning far more readily than marketing copy."
        )
    else:
        out.append(
            f"Strong presence: named in {mention_rate:.0%} of answers. Defend it by keeping pricing, "
            "features and positioning pages current - assistants repeat stale facts for a long time."
        )

    if citation_rate < mention_rate * 0.5:
        out.append(
            f"You are mentioned more often ({mention_rate:.0%}) than cited ({citation_rate:.0%}). "
            "That means models know of you but do not treat your site as the source. Add JSON-LD "
            "(Organization, Product, FAQPage), publish an llms.txt, and put original data on your own "
            "domain so there is a reason to link to you rather than to a reviewer."
        )

    leaders = [c for c in competitor_share if c["share"] > mention_rate][:3]
    if leaders:
        names = ", ".join(c["competitor"] for c in leaders)
        out.append(
            f"These competitors are named more often than you: {names}. Pull their citation sources "
            "with the backlink link-intersect tool - in AI answers the source list and the link graph "
            "overlap heavily."
        )

    out.append(
        "Re-run this prompt set weekly. Answer engines change output faster than search rankings move, "
        "so a single snapshot is not a trend."
    )
    return out
