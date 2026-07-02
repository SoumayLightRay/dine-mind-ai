"""
Filter Engine — Phase 3: Filter & Query Engine
================================================

Filters the cleaned restaurant dataset based on user preferences.
Pipeline: Location → Budget → Cuisine → Rating → Extras → Sort → Top N

Handles edge cases:
    - Empty/null filter values (skip filter)
    - Cuisine typos via fuzzy matching
    - XSS/injection sanitization
    - NaN handling in cost/rating columns
    - Broad location matches (min 2 chars)
    - Returns filter diagnostics when 0 results found
"""

import re
import logging
from difflib import get_close_matches
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Max results to return (controls LLM context size)
MAX_RESULTS = 10


# ═══════════════════════════════════════════════════════════════
# Input Sanitization
# ═══════════════════════════════════════════════════════════════

def sanitize_string(value: Any) -> str | None:
    """Strip XSS payloads and normalize a string input."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Remove HTML tags
    s = re.sub(r"<[^>]+>", "", s)
    # Remove common XSS patterns
    s = re.sub(r"javascript:", "", s, flags=re.IGNORECASE)
    s = re.sub(r"on\w+\s*=", "", s, flags=re.IGNORECASE)
    return s if s else None


def sanitize_preferences(raw: dict) -> dict:
    """
    Validate and sanitize incoming user preferences.
    Returns a clean dict with only known fields.
    """
    clean = {}

    # Location
    location = sanitize_string(raw.get("location"))
    if location and len(location) >= 2:
        clean["location"] = location
    elif location and len(location) < 2:
        logger.warning(f"Location too short ('{location}'), ignoring")

    # Budget
    budget = raw.get("budget")
    if budget in ("Low", "Medium", "High"):
        clean["budget"] = budget

    # Cuisines
    cuisines_raw = raw.get("cuisines", [])
    if isinstance(cuisines_raw, list):
        # Strip empty strings and nulls
        cuisines = [
            sanitize_string(c)
            for c in cuisines_raw
            if c and sanitize_string(c)
        ]
        if cuisines:
            clean["cuisines"] = cuisines

    # Min rating — clamp to [0, 5]
    min_rating = raw.get("min_rating")
    if min_rating is not None:
        try:
            rating = float(min_rating)
            clean["min_rating"] = max(0.0, min(5.0, rating))
        except (ValueError, TypeError):
            pass

    # Extras
    extras_raw = raw.get("extras", [])
    if isinstance(extras_raw, list):
        extras = [sanitize_string(e) for e in extras_raw if e and sanitize_string(e)]
        if extras:
            clean["extras"] = extras

    return clean


# ═══════════════════════════════════════════════════════════════
# Fuzzy Cuisine Matching
# ═══════════════════════════════════════════════════════════════

def fuzzy_match_cuisines(requested: list[str], available: list[str]) -> list[str]:
    """
    For each requested cuisine, find the closest match in the available
    cuisines list. Handles typos like 'Italain' → 'Italian'.
    """
    matched = []
    corrections = {}

    for req in requested:
        # Exact match (case-insensitive)
        exact = [a for a in available if a.lower() == req.lower()]
        if exact:
            matched.append(exact[0])
            continue

        # Fuzzy match
        close = get_close_matches(req, available, n=1, cutoff=0.7)
        if close:
            matched.append(close[0])
            corrections[req] = close[0]
        else:
            # No match at all — still use original (might partially match)
            matched.append(req)

    if corrections:
        logger.info(f"Cuisine corrections applied: {corrections}")

    return matched


# ═══════════════════════════════════════════════════════════════
# Core Filter Pipeline
# ═══════════════════════════════════════════════════════════════

def filter_restaurants(df: pd.DataFrame, preferences: dict) -> dict:
    """
    Filter restaurants based on user preferences.

    Args:
        df: Clean restaurant DataFrame
        preferences: Sanitized user preferences dict

    Returns:
        dict with keys:
            - recommendations: list of restaurant dicts (max MAX_RESULTS)
            - total_matches: total count before truncation
            - query_summary: human-readable summary of the query
            - filters_applied: list of filters that were active
            - suggestion: hint if no results found
    """
    filtered = df.copy()
    filters_applied = []
    filter_counts = {}  # Track how each filter reduces the count

    initial_count = len(filtered)

    # ─── 1. Location Filter ───
    location = preferences.get("location")
    if location:
        mask = filtered["city"].str.contains(location, case=False, na=False)
        filtered = filtered[mask]
        filters_applied.append(f"location={location}")
        filter_counts["location"] = len(filtered)

    # ─── 2. Budget Filter ───
    budget = preferences.get("budget")
    if budget:
        filtered = filtered[filtered["budget"] == budget]
        filters_applied.append(f"budget={budget}")
        filter_counts["budget"] = len(filtered)

    # ─── 3. Cuisine Filter ───
    cuisines = preferences.get("cuisines")
    if cuisines:
        # Get all unique cuisines from the dataset for fuzzy matching
        all_cuisines = (
            df["cuisines"]
            .dropna()
            .str.split(", ")
            .explode()
            .str.strip()
            .unique()
            .tolist()
        )
        matched_cuisines = fuzzy_match_cuisines(cuisines, all_cuisines)

        # Build regex pattern (OR match — any cuisine matches)
        pattern = "|".join(re.escape(c) for c in matched_cuisines)
        mask = filtered["cuisines"].str.contains(pattern, case=False, na=False)
        filtered = filtered[mask]
        filters_applied.append(f"cuisines={matched_cuisines}")
        filter_counts["cuisines"] = len(filtered)

    # ─── 4. Rating Filter ───
    min_rating = preferences.get("min_rating")
    if min_rating is not None and min_rating > 0:
        filtered = filtered[filtered["rating"] >= min_rating]
        filters_applied.append(f"min_rating={min_rating}")
        filter_counts["rating"] = len(filtered)

    # ─── 5. Extras / Highlights Filter ───
    extras = preferences.get("extras")
    if extras and "highlights" in filtered.columns:
        pattern = "|".join(re.escape(e) for e in extras)
        mask = filtered["highlights"].str.contains(pattern, case=False, na=False)
        filtered = filtered[mask]
        filters_applied.append(f"extras={extras}")
        filter_counts["extras"] = len(filtered)

    # ─── Sort & Truncate ───
    total_matches = len(filtered)

    if total_matches > 0:
        # Sort by rating (desc), then by votes (desc) as tiebreaker
        filtered = filtered.sort_values(
            ["rating", "votes"], ascending=[False, False]
        )
        top_results = filtered.head(MAX_RESULTS)
    else:
        top_results = filtered

    # ─── Build Response ───
    recommendations = _df_to_dicts(top_results)
    query_summary = _build_query_summary(preferences, total_matches)
    suggestion = _build_suggestion(preferences, filter_counts, initial_count) if total_matches == 0 else None

    result = {
        "recommendations": recommendations,
        "total_matches": total_matches,
        "query_summary": query_summary,
        "filters_applied": filters_applied,
    }

    if suggestion:
        result["suggestion"] = suggestion

    logger.info(
        f"Filter result: {total_matches} matches "
        f"(returning {len(recommendations)}) | Filters: {filters_applied}"
    )

    return result


# ═══════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════

def _df_to_dicts(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame rows to a list of clean JSON-serializable dicts."""
    records = []
    for _, row in df.iterrows():
        record = {
            "name": str(row.get("name", "")),
            "city": str(row.get("city", "")),
            "cuisines": str(row.get("cuisines", "")),
            "rating": _safe_float(row.get("rating")),
            "cost_for_two": _safe_float(row.get("cost_for_two")),
            "budget": str(row.get("budget", "Unknown")),
            "votes": int(row.get("votes", 0)) if pd.notna(row.get("votes")) else 0,
        }
        if "highlights" in row.index and pd.notna(row.get("highlights")):
            record["highlights"] = str(row["highlights"])
        records.append(record)
    return records


def _safe_float(val) -> float | None:
    """Convert a value to float safely, returning None for NaN."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return round(float(val), 1)
    except (ValueError, TypeError):
        return None


def _build_query_summary(prefs: dict, total: int) -> str:
    """Build a human-readable summary of the query for the results header."""
    parts = []

    if prefs.get("cuisines"):
        cuisine_str = ", ".join(prefs["cuisines"][:3])
        if len(prefs["cuisines"]) > 3:
            cuisine_str += f" +{len(prefs['cuisines']) - 3} more"
        parts.append(cuisine_str)

    if prefs.get("budget"):
        parts.append(f"{prefs['budget']} budget")

    location = prefs.get("location", "")

    if parts:
        summary = f"Top {' & '.join(parts)} restaurants"
    else:
        summary = "Top restaurants"

    if location:
        summary += f" in {location}"

    if prefs.get("min_rating"):
        summary += f", rated {prefs['min_rating']}+"

    return summary


def _build_suggestion(prefs: dict, filter_counts: dict, initial_count: int) -> str:
    """
    When 0 results are found, suggest which filter to relax.
    Identifies the most restrictive filter (biggest drop in count).
    """
    if not filter_counts:
        return "Try selecting different preferences."

    # Find which filter caused the biggest drop
    prev_count = initial_count
    biggest_drop_filter = None
    biggest_drop = 0

    for filter_name, remaining in filter_counts.items():
        drop = prev_count - remaining
        if drop > biggest_drop:
            biggest_drop = drop
            biggest_drop_filter = filter_name
        prev_count = remaining

    suggestions = {
        "location": "Try a different location or select 'All locations'.",
        "budget": "Try removing the budget filter for more options.",
        "cuisines": "Try fewer cuisine types or different ones.",
        "rating": "Try lowering the minimum rating.",
        "extras": "Try removing the type/extras filter.",
    }

    if biggest_drop_filter and biggest_drop_filter in suggestions:
        return f"No matches found. {suggestions[biggest_drop_filter]}"

    return "No matches found. Try relaxing your filters for more options."


# ═══════════════════════════════════════════════════════════════
# Metadata endpoint helpers
# ═══════════════════════════════════════════════════════════════

def get_available_filters(df: pd.DataFrame) -> dict:
    """
    Return all unique values for each filter field.
    Used by the frontend to populate dropdowns/chips dynamically.
    """
    # Cities sorted by restaurant count (desc)
    city_counts = df["city"].value_counts()
    cities = [
        {"name": city, "count": int(count)}
        for city, count in city_counts.items()
    ]

    # Unique cuisines sorted alphabetically
    all_cuisines = sorted(
        df["cuisines"]
        .dropna()
        .str.split(", ")
        .explode()
        .str.strip()
        .unique()
        .tolist()
    )
    # Remove "Unknown"
    all_cuisines = [c for c in all_cuisines if c and c != "Unknown"]

    # Highlights
    highlights = sorted(
        df["highlights"]
        .dropna()
        .unique()
        .tolist()
    ) if "highlights" in df.columns else []

    # Budget options
    budgets = ["Low", "Medium", "High"]

    return {
        "cities": cities,
        "cuisines": all_cuisines,
        "budgets": budgets,
        "highlights": highlights,
        "total_restaurants": len(df),
        "rating_range": {
            "min": float(df["rating"].min()) if len(df) > 0 else 0,
            "max": float(df["rating"].max()) if len(df) > 0 else 5,
        },
    }
