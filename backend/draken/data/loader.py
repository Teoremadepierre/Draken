"""Loads and caches the JSON seed datasets under ``data/seeds/``.

These files are the editable source of truth: drop in your own directories,
templates or prompt sets and restart - no code change needed.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from draken.core.config import SEEDS_DIR
from draken.core.logging import get_logger

log = get_logger(__name__)


def _read(name: str, default: Any) -> Any:
    path: Path = SEEDS_DIR / name
    if not path.exists():
        log.warning("seed file missing: %s (using default)", path)
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.error("seed file %s is invalid JSON: %s", path, exc)
        return default


@functools.lru_cache(maxsize=1)
def link_sources() -> list[dict]:
    return _read("link_sources.json", [])


@functools.lru_cache(maxsize=1)
def keyword_modifiers() -> dict[str, list[str]]:
    return _read("keyword_modifiers.json", {})


@functools.lru_cache(maxsize=1)
def question_prefixes() -> dict[str, list[str]]:
    return _read("question_prefixes.json", {"en": ["what", "how", "why"]})


@functools.lru_cache(maxsize=1)
def ctr_curve() -> dict[int, float]:
    raw = _read("ctr_curve.json", {})
    return {int(k): float(v) for k, v in raw.items()}


@functools.lru_cache(maxsize=1)
def toxicity_rules() -> dict[str, list[str]]:
    return _read(
        "toxicity_rules.json",
        {"spam_tld": [], "spam_patterns": [], "low_value_patterns": [], "footprint_patterns": []},
    )


@functools.lru_cache(maxsize=1)
def outreach_templates() -> list[dict]:
    return _read("outreach_templates.json", [])


@functools.lru_cache(maxsize=1)
def geo_prompt_templates() -> dict[str, list[str]]:
    return _read("geo_prompt_templates.json", {})


def ctr_for_position(position: int | None) -> float:
    """Estimated click-through rate for an organic position."""
    if not position or position < 1:
        return 0.0
    curve = ctr_curve()
    if position in curve:
        return curve[position]
    return 0.0005 if position > 100 else 0.001


def clear_caches() -> None:
    for fn in (
        link_sources,
        keyword_modifiers,
        question_prefixes,
        ctr_curve,
        toxicity_rules,
        outreach_templates,
        geo_prompt_templates,
    ):
        fn.cache_clear()
