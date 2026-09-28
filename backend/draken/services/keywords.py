"""Persistence orchestration for keyword research, clustering and rank tracking."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from draken.core.logging import get_logger
from draken.core.models import Keyword, KeywordCluster, Project, RankSnapshot, SerpResult
from draken.core.urls import normalize_domain
from draken.data import loader
from draken.engines.keywords import cluster as cluster_mod
from draken.engines.keywords import expand as expand_mod
from draken.engines.keywords import metrics
from draken.engines.serp import authority as authority_mod
from draken.engines.serp import fetcher

log = get_logger(__name__)


async def research(
    db: Session,
    *,
    project: Project,
    seeds: list[str],
    country: str = "US",
    language: str = "en",
    include_questions: bool = True,
    include_modifiers: bool = True,
    include_alphabet_soup: bool = False,
    max_results: int = 400,
    persist: bool = True,
    use_live_suggest: bool = True,
) -> dict:
    """Expand seeds, score them, and (optionally) store them against the project."""
    expanded = await expand_mod.expand(
        seeds,
        country=country or project.country,
        language=language or project.language,
        include_questions=include_questions,
        include_modifiers=include_modifiers,
        include_alphabet_soup=include_alphabet_soup,
        max_results=max_results,
        use_live_suggest=use_live_suggest,
        brand_terms=list(project.brand_terms or []),
    )

    created = updated = 0
    if persist and expanded:
        existing = {
            (k.term, k.country): k
            for k in db.execute(
                select(Keyword).where(Keyword.project_id == project.id)
            ).scalars()
        }
        for kw in expanded:
            key = (kw.term, country)
            row = existing.get(key)
            if row is None:
                db.add(
                    Keyword(
                        project_id=project.id,
                        term=kw.term,
                        country=country,
                        language=language,
                        volume=kw.volume,
                        volume_confidence=kw.volume_confidence,
                        difficulty=kw.difficulty,
                        opportunity_score=kw.opportunity_score,
                        cpc=kw.cpc,
                        competition=kw.competition,
                        intent=kw.intent,
                        word_count=kw.word_count,
                        is_question=kw.is_question,
                        is_branded=kw.is_branded,
                        source=kw.source,
                        meta_json={"providers": sorted(kw.providers), "suggest_rank": kw.suggest_rank},
                    )
                )
                created += 1
            else:
                # Keep the better-evidenced estimate.
                if kw.volume_confidence >= row.volume_confidence:
                    row.volume = kw.volume
                    row.volume_confidence = kw.volume_confidence
                row.difficulty = kw.difficulty
                row.opportunity_score = kw.opportunity_score
                row.cpc = kw.cpc
                row.competition = kw.competition
                row.intent = kw.intent
                updated += 1
        db.commit()

    return {
        "seeds": seeds,
        "country": country,
        "found": len(expanded),
        "created": created,
        "updated": updated,
        "persisted": persist,
        "live_suggest_used": use_live_suggest,
        "keywords": [kw.as_dict() for kw in expanded],
    }


def add_manual(
    db: Session, *, project: Project, terms: list[str], country: str = "US", track: bool = False
) -> dict:
    created = 0
    skipped = 0
    # Duplicates inside one request are as likely as duplicates against the table
    # (a pasted list), and pending inserts are not visible to a SELECT yet.
    seen_in_batch: set[str] = set()
    for raw in terms:
        term = " ".join((raw or "").split()).lower()
        if not term:
            continue
        if term in seen_in_batch:
            skipped += 1
            continue
        seen_in_batch.add(term)
        exists = db.execute(
            select(Keyword).where(
                Keyword.project_id == project.id, Keyword.term == term, Keyword.country == country
            )
        ).scalars().first()
        if exists:
            if track and not exists.is_tracked:
                exists.is_tracked = True
            skipped += 1
            continue
        intent = metrics.classify_intent(term, brand_terms=list(project.brand_terms or []))
        volume, confidence = metrics.estimate_volume(term)
        difficulty = metrics.estimate_difficulty(term, volume=volume, intent=intent)
        db.add(
            Keyword(
                project_id=project.id,
                term=term,
                country=country,
                language=project.language,
                volume=volume,
                volume_confidence=confidence,
                difficulty=difficulty,
                cpc=metrics.estimate_cpc(term, intent, difficulty),
                competition=round(difficulty / 100, 2),
                intent=intent.value,
                word_count=len(metrics.tokenize(term)),
                is_question=metrics.is_question(term),
                is_branded=any(
                    b and b.lower() in term for b in (project.brand_terms or [])
                ),
                opportunity_score=metrics.opportunity_score(
                    volume=volume, difficulty=difficulty, intent=intent
                ),
                source="manual",
                is_tracked=track,
            )
        )
        created += 1
    db.commit()
    return {"created": created, "skipped": skipped}


def rebuild_clusters(db: Session, *, project: Project, threshold: float = 0.6) -> dict:
    """Recompute clusters for all of a project's keywords."""
    keywords = list(
        db.execute(select(Keyword).where(Keyword.project_id == project.id)).scalars()
    )
    if not keywords:
        return {"clusters": 0, "keywords": 0, "topics": []}

    payload = [
        {
            "id": k.id,
            "term": k.term,
            "volume": k.volume,
            "difficulty": k.difficulty,
            "intent": k.intent,
            "is_question": k.is_question,
        }
        for k in keywords
    ]
    clusters = cluster_mod.cluster_keywords(payload, threshold=threshold)

    # Detach keywords before dropping the old clusters: the FK is ON DELETE SET NULL
    # on new databases, but doing it explicitly keeps older ones working too.
    for kw in keywords:
        kw.cluster_id = None
        kw.parent_topic = ""
    db.flush()
    db.execute(delete(KeywordCluster).where(KeywordCluster.project_id == project.id))
    db.flush()

    by_id = {k.id: k for k in keywords}
    for c in clusters:
        row = KeywordCluster(
            project_id=project.id,
            label=c.label[:300],
            head_term=c.head_term[:400],
            total_volume=c.total_volume,
            avg_difficulty=c.avg_difficulty,
            dominant_intent=c.dominant_intent,
            keyword_count=len(c.members),
            recommended_page_type=c.recommended_page_type(),
        )
        db.add(row)
        db.flush()
        for member in c.members:
            kw = by_id.get(member.get("id"))
            if kw is not None:
                kw.cluster_id = row.id
                kw.parent_topic = c.label[:400]
    db.commit()

    return {
        "clusters": len(clusters),
        "keywords": len(keywords),
        "topics": cluster_mod.build_topic_map(clusters)[:40],
    }


async def track_rankings(
    db: Session, *, project: Project, keyword_ids: list[int] | None = None, device: str = "desktop"
) -> dict:
    """Fetch current SERPs for tracked keywords and store today's positions."""
    query = select(Keyword).where(Keyword.project_id == project.id)
    if keyword_ids:
        query = query.where(Keyword.id.in_(keyword_ids))
    else:
        query = query.where(Keyword.is_tracked.is_(True))
    keywords = list(db.execute(query.limit(120)).scalars())
    if not keywords:
        return {
            "tracked": 0,
            "provider": fetcher.active_provider(),
            "message": "No tracked keywords. Mark keywords as tracked first.",
        }

    pages = await fetcher.fetch_many(
        [k.term for k in keywords], country=project.country, language=project.language
    )

    today = datetime.now(UTC).date()
    improved = declined = unchanged = new = 0
    rows: list[dict] = []
    all_domains: set[str] = set()

    for kw in keywords:
        page = pages.get(kw.term)
        if page is None or page.error:
            continue
        position, url = page.position_of(project.domain)

        previous = db.execute(
            select(RankSnapshot)
            .where(RankSnapshot.keyword_id == kw.id, RankSnapshot.captured_on < today)
            .order_by(RankSnapshot.captured_on.desc())
        ).scalars().first()
        prev_pos = previous.position if previous else None

        existing_today = db.execute(
            select(RankSnapshot).where(
                RankSnapshot.keyword_id == kw.id,
                RankSnapshot.captured_on == today,
                RankSnapshot.device == device,
            )
        ).scalars().first()

        snapshot = existing_today or RankSnapshot(keyword_id=kw.id, captured_on=today, device=device)
        snapshot.position = position
        snapshot.previous_position = prev_pos
        snapshot.url = url
        snapshot.serp_features = page.features
        snapshot.estimated_traffic = metrics.estimate_traffic(kw.volume, position)
        snapshot.provider = page.provider
        if existing_today is None:
            db.add(snapshot)

        kw.serp_features = page.features
        kw.opportunity_score = metrics.opportunity_score(
            volume=kw.volume,
            difficulty=kw.difficulty,
            intent=kw.intent,
            current_position=position,
            is_branded=kw.is_branded,
        )

        if prev_pos is None:
            new += 1
        elif position is None:
            declined += 1
        elif position < prev_pos:
            improved += 1
        elif position > prev_pos:
            declined += 1
        else:
            unchanged += 1

        # Cache the SERP for difficulty recalculation and gap analysis.
        db.execute(
            delete(SerpResult).where(SerpResult.term == kw.term, SerpResult.country == project.country)
        )
        for item in page.items[:20]:
            all_domains.add(item.domain)
            db.add(
                SerpResult(
                    term=kw.term,
                    country=project.country,
                    position=item.position,
                    url=item.url,
                    domain=item.domain,
                    title=item.title[:500],
                    snippet=item.snippet[:2000],
                    result_type=item.result_type,
                    provider=page.provider,
                )
            )

        rows.append(
            {
                "keyword_id": kw.id,
                "term": kw.term,
                "position": position,
                "previous_position": prev_pos,
                "url": url,
                "estimated_traffic": snapshot.estimated_traffic,
                "features": page.features,
            }
        )

    db.commit()

    # Recompute difficulty from the real SERPs we just fetched.
    if all_domains:
        auth_map = await authority_mod.authority_for(sorted(all_domains))
        for kw in keywords:
            cached = list(
                db.execute(
                    select(SerpResult).where(
                        SerpResult.term == kw.term, SerpResult.country == project.country
                    )
                ).scalars()
            )
            if not cached:
                continue
            authorities = [auth_map.get(r.domain, 0.0) for r in cached[:10]]
            for r in cached:
                r.domain_authority = auth_map.get(r.domain, 0.0)
            kw.difficulty = metrics.estimate_difficulty(
                kw.term, serp_authorities=authorities, volume=kw.volume, intent=kw.intent
            )
        db.commit()

    provider = fetcher.active_provider()
    return {
        "tracked": len(rows),
        "improved": improved,
        "declined": declined,
        "unchanged": unchanged,
        "new": new,
        "provider": provider,
        "approximate": provider not in {"serpapi", "dataforseo"},
        "results": rows,
    }


async def keyword_gap(
    db: Session, *, project: Project, competitors: list[str] | None = None, limit: int = 200
) -> dict:
    """Which keywords do competitors rank for that we do not.

    Works off the cached SERP table, so run rank tracking first (or pass terms and
    it will fetch them).
    """
    competitors = [normalize_domain(c) for c in (competitors or project.competitors or []) if c]
    competitors = [c for c in competitors if c]
    if not competitors:
        return {"competitors": [], "gaps": [], "message": "Add competitor domains to the project first."}

    own = normalize_domain(project.domain)
    rows = list(
        db.execute(
            select(SerpResult).where(SerpResult.country == project.country)
        ).scalars()
    )
    if not rows:
        return {
            "competitors": competitors,
            "gaps": [],
            "message": "No cached SERP data yet. Run rank tracking on your keywords first.",
        }

    by_term: dict[str, list[SerpResult]] = {}
    for r in rows:
        by_term.setdefault(r.term, []).append(r)

    keyword_meta = {
        k.term: k
        for k in db.execute(select(Keyword).where(Keyword.project_id == project.id)).scalars()
    }

    gaps: list[dict] = []
    for term, results in by_term.items():
        domains = {r.domain: r for r in results}
        if own in domains:
            own_pos = domains[own].position
        else:
            own_pos = None
        competitor_hits = [
            {"domain": c, "position": domains[c].position, "url": domains[c].url}
            for c in competitors
            if c in domains
        ]
        if not competitor_hits:
            continue
        best_competitor = min(competitor_hits, key=lambda h: h["position"])
        if own_pos is not None and own_pos <= best_competitor["position"]:
            continue

        kw = keyword_meta.get(term)
        gaps.append(
            {
                "term": term,
                "volume": kw.volume if kw else 0,
                "difficulty": kw.difficulty if kw else 0.0,
                "intent": kw.intent if kw else "",
                "our_position": own_pos,
                "best_competitor": best_competitor["domain"],
                "best_competitor_position": best_competitor["position"],
                "competitors_ranking": len(competitor_hits),
                "competitor_detail": competitor_hits,
                "gap_type": "not_ranking" if own_pos is None else "outranked",
                "priority": metrics.opportunity_score(
                    volume=kw.volume if kw else 0,
                    difficulty=kw.difficulty if kw else 50.0,
                    intent=kw.intent if kw else "informational",
                    current_position=own_pos,
                ),
            }
        )

    gaps.sort(key=lambda g: (-g["priority"], -g["volume"]))
    return {
        "competitors": competitors,
        "terms_analysed": len(by_term),
        "gaps": gaps[:limit],
        "not_ranking": sum(1 for g in gaps if g["gap_type"] == "not_ranking"),
        "outranked": sum(1 for g in gaps if g["gap_type"] == "outranked"),
    }


def ranking_overview(db: Session, *, project: Project, days: int = 30) -> dict:
    """Visibility trend and position distribution for the dashboard."""
    keywords = list(
        db.execute(
            select(Keyword).where(Keyword.project_id == project.id, Keyword.is_tracked.is_(True))
        ).scalars()
    )
    if not keywords:
        return {
            "tracked_keywords": 0, "visibility_index": 0.0, "estimated_traffic": 0.0,
            "distribution": {}, "trend": [], "movers": {"up": [], "down": []},
        }

    kw_by_id = {k.id: k for k in keywords}
    snapshots = list(
        db.execute(
            select(RankSnapshot)
            .where(RankSnapshot.keyword_id.in_(list(kw_by_id)))
            .order_by(RankSnapshot.captured_on.asc())
        ).scalars()
    )

    latest: dict[int, RankSnapshot] = {}
    by_date: dict[str, list[RankSnapshot]] = {}
    for s in snapshots:
        latest[s.keyword_id] = s
        by_date.setdefault(str(s.captured_on), []).append(s)

    distribution = {"top3": 0, "top10": 0, "top20": 0, "top50": 0, "beyond": 0, "unranked": 0}
    traffic = 0.0
    visibility = 0.0
    for snap in latest.values():
        pos = snap.position
        traffic += snap.estimated_traffic or 0.0
        if pos is None:
            distribution["unranked"] += 1
            continue
        visibility += loader.ctr_for_position(pos) * 100
        if pos <= 3:
            distribution["top3"] += 1
        elif pos <= 10:
            distribution["top10"] += 1
        elif pos <= 20:
            distribution["top20"] += 1
        elif pos <= 50:
            distribution["top50"] += 1
        else:
            distribution["beyond"] += 1

    trend = []
    for date_str in sorted(by_date)[-days:]:
        day = by_date[date_str]
        ranked = [s for s in day if s.position]
        trend.append(
            {
                "date": date_str,
                "avg_position": round(sum(s.position for s in ranked) / len(ranked), 1) if ranked else None,
                "visibility": round(sum(loader.ctr_for_position(s.position) * 100 for s in ranked), 2),
                "estimated_traffic": round(sum(s.estimated_traffic or 0 for s in day), 1),
                "ranked_keywords": len(ranked),
            }
        )

    movers_up, movers_down = [], []
    for kid, snap in latest.items():
        if snap.position is None or snap.previous_position is None:
            continue
        delta = snap.previous_position - snap.position
        entry = {
            "term": kw_by_id[kid].term,
            "position": snap.position,
            "previous_position": snap.previous_position,
            "change": delta,
            "volume": kw_by_id[kid].volume,
        }
        (movers_up if delta > 0 else movers_down).append(entry)
    movers_up.sort(key=lambda e: -e["change"])
    movers_down.sort(key=lambda e: e["change"])

    return {
        "tracked_keywords": len(keywords),
        "visibility_index": round(visibility, 2),
        "estimated_traffic": round(traffic, 1),
        "distribution": distribution,
        "trend": trend,
        "movers": {"up": movers_up[:15], "down": movers_down[:15]},
        "last_updated": str(max(by_date)) if by_date else None,
    }
