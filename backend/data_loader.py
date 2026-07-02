"""
Data Loader & Preprocessor — Phase 1: Data Foundation
=====================================================

Loads the Zomato restaurant dataset from HuggingFace, cleans and normalizes
the data, derives budget buckets, and exports a clean CSV for downstream use.

Target Schema (restaurants_clean.csv):
    - name          : str   — Restaurant name
    - city          : str   — City / locality (title-cased)
    - cuisines      : str   — Comma-separated cuisine types
    - cost_for_two  : float — Average cost for two people (INR)
    - budget        : str   — Low | Medium | High (derived from cost_for_two)
    - rating        : float — Aggregate rating (0–5)
    - votes         : int   — Number of user votes
    - highlights    : str   — Tags like "Family Friendly", "Outdoor Seating"

Usage:
    python data_loader.py              # Full pipeline: fetch → clean → export
    python data_loader.py --explore    # Just explore the raw schema and stats
"""

import os
import sys
import argparse
import logging
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CLEAN_CSV = DATA_DIR / "restaurants_clean.csv"

DATASET_ID = "ManikaSaini/zomato-restaurant-recommendation"

# ---------------------------------------------------------------------------
# Budget thresholds (INR for two people)
# ---------------------------------------------------------------------------
BUDGET_LOW_MAX = 500       # 0 – 500   → Low
BUDGET_MEDIUM_MAX = 1500   # 501 – 1500 → Medium
                           # 1501+      → High


# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Fetch dataset from HuggingFace
# ═══════════════════════════════════════════════════════════════════════════

def fetch_dataset() -> pd.DataFrame:
    """
    Download the Zomato dataset from HuggingFace using the `datasets` library.
    Falls back to a locally cached CSV if the download fails.
    """
    # Try loading from local cache first (if already downloaded previously)
    raw_csv = RAW_DIR / "zomato_raw.csv"
    if raw_csv.exists():
        logger.info(f"Loading cached raw dataset from {raw_csv}")
        return pd.read_csv(raw_csv)

    logger.info(f"Fetching dataset from HuggingFace: {DATASET_ID}")
    try:
        from datasets import load_dataset

        dataset = load_dataset(DATASET_ID)

        # Most HF datasets have a 'train' split
        split_name = "train" if "train" in dataset else list(dataset.keys())[0]
        df = dataset[split_name].to_pandas()

        # Cache raw data locally
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(raw_csv, index=False)
        logger.info(f"Raw dataset cached → {raw_csv}  ({len(df)} rows)")

        return df

    except Exception as e:
        # Check if clean CSV already exists as ultimate fallback
        if CLEAN_CSV.exists():
            logger.warning(
                f"HuggingFace download failed ({e}). "
                f"Falling back to existing clean CSV: {CLEAN_CSV}"
            )
            return pd.read_csv(CLEAN_CSV)

        logger.error(
            f"Failed to fetch dataset and no local fallback found.\n"
            f"Error: {e}\n"
            f"Make sure you have internet access and the `datasets` package installed:\n"
            f"  pip install datasets"
        )
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Explore schema (optional, for development)
# ═══════════════════════════════════════════════════════════════════════════

def explore_schema(df: pd.DataFrame) -> None:
    """Print a detailed overview of the raw dataset for development use."""
    print("\n" + "=" * 70)
    print("  DATASET SCHEMA EXPLORATION")
    print("=" * 70)

    print(f"\n[SHAPE] {df.shape[0]} rows x {df.shape[1]} columns\n")

    print("[COLUMNS & DATA TYPES]")
    print("-" * 50)
    for col in df.columns:
        dtype = df[col].dtype
        nulls = df[col].isnull().sum()
        null_pct = (nulls / len(df)) * 100
        unique = df[col].nunique()
        print(f"  {col:30s}  {str(dtype):10s}  nulls: {nulls:5d} ({null_pct:5.1f}%)  unique: {unique}")

    print(f"\n[FIRST 3 ROWS]")
    print("-" * 50)
    print(df.head(3).to_string())

    # Show sample values for key text columns
    text_cols = df.select_dtypes(include=["object"]).columns[:5]
    for col in text_cols:
        sample = df[col].dropna().unique()[:5]
        print(f"\n[SAMPLE] '{col}': {list(sample)}")

    print("\n" + "=" * 70)


# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Clean & Normalize
# ═══════════════════════════════════════════════════════════════════════════

# Mapping of possible raw column names → our target column names.
# This handles schema drift if HuggingFace column names change slightly.
COLUMN_MAP = {
    # name
    "name": "name",
    "restaurant_name": "name",
    "restaurant name": "name",
    "Name": "name",
    # city
    "city": "city",
    "location": "city",
    "locality": "city",
    "City": "city",
    "Location": "city",
    # cuisines
    "cuisines": "cuisines",
    "cuisine": "cuisines",
    "Cuisines": "cuisines",
    "Cuisine": "cuisines",
    # cost
    "cost_for_two": "cost_for_two",
    "average_cost_for_two": "cost_for_two",
    "approx_cost(for two people)": "cost_for_two",
    "approx_cost": "cost_for_two",
    "Average Cost for two": "cost_for_two",
    "cost": "cost_for_two",
    "Cost": "cost_for_two",
    # rating
    "rating": "rating",
    "aggregate_rating": "rating",
    "rate": "rating",
    "Rating": "rating",
    "Aggregate rating": "rating",
    # votes
    "votes": "votes",
    "Votes": "votes",
    "vote_count": "votes",
    # highlights / tags
    "highlights": "highlights",
    "listed_in(type)": "highlights",
    "type": "highlights",
    "Type": "highlights",
}

# Required columns in the final clean dataset
REQUIRED_COLUMNS = ["name", "city", "cuisines", "cost_for_two", "rating"]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw column names to standardized target names."""
    rename_map = {}
    for raw_col in df.columns:
        # Try exact match first, then lowercase match
        if raw_col in COLUMN_MAP:
            rename_map[raw_col] = COLUMN_MAP[raw_col]
        elif raw_col.lower().strip() in {k.lower(): k for k in COLUMN_MAP}:
            # Fuzzy: find by lowercase
            for key, val in COLUMN_MAP.items():
                if raw_col.lower().strip() == key.lower():
                    rename_map[raw_col] = val
                    break

    df = df.rename(columns=rename_map)
    logger.info(f"Column mapping applied: {rename_map}")
    return df


def _validate_required_columns(df: pd.DataFrame) -> None:
    """Ensure all required columns exist after mapping."""
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        logger.error(
            f"Missing required columns after mapping: {missing}\n"
            f"Available columns: {list(df.columns)}\n"
            f"You may need to update COLUMN_MAP in data_loader.py."
        )
        sys.exit(1)


def _clean_name(df: pd.DataFrame) -> pd.DataFrame:
    """Clean restaurant names: strip whitespace, remove HTML entities."""
    df["name"] = (
        df["name"]
        .astype(str)
        .str.strip()
        .str.replace(r"<[^>]+>", "", regex=True)   # Strip HTML tags
        .str.replace(r"&amp;", "&", regex=False)
        .str.replace(r"&lt;", "<", regex=False)
        .str.replace(r"&gt;", ">", regex=False)
    )
    return df


def _clean_city(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize city names to title case and handle common aliases."""
    city_aliases = {
        "ncr": "New Delhi",
        "new delhi": "New Delhi",
        "delhi": "New Delhi",
        "bengaluru": "Bangalore",
        "bombay": "Mumbai",
        "madras": "Chennai",
        "calcutta": "Kolkata",
    }

    df["city"] = df["city"].astype(str).str.strip().str.title()

    # Apply alias mapping
    df["city"] = df["city"].apply(
        lambda x: city_aliases.get(x.lower(), x) if pd.notna(x) else x
    )
    return df


def _clean_cuisines(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize cuisines: trim each cuisine, title case, handle missing."""
    def normalize_cuisine_str(val):
        if pd.isna(val) or str(val).strip().lower() in ("", "na", "n/a", "nan", "none"):
            return "Unknown"
        # Split by comma, trim each, title case, rejoin
        parts = [c.strip().title() for c in str(val).split(",") if c.strip()]
        return ", ".join(parts) if parts else "Unknown"

    df["cuisines"] = df["cuisines"].apply(normalize_cuisine_str)
    return df


def _clean_cost(df: pd.DataFrame) -> pd.DataFrame:
    """Parse cost_for_two into a clean float. Handle strings, commas, currency symbols."""
    def parse_cost(val):
        if pd.isna(val):
            return None
        val_str = str(val).strip()
        # Remove currency symbols and commas
        val_str = val_str.replace("₹", "").replace(",", "").replace("$", "").strip()
        try:
            cost = float(val_str)
            # Clamp outliers
            if cost < 0:
                return None
            if cost > 100_000:
                return None  # Likely data error
            return cost
        except (ValueError, TypeError):
            return None

    df["cost_for_two"] = df["cost_for_two"].apply(parse_cost)
    return df


def _clean_rating(df: pd.DataFrame) -> pd.DataFrame:
    """Parse rating into a clean float (0–5 scale)."""
    def parse_rating(val):
        if pd.isna(val):
            return None
        val_str = str(val).strip().lower()

        # Handle text ratings
        text_map = {
            "excellent": 4.8,
            "very good": 4.2,
            "good": 3.5,
            "average": 2.5,
            "poor": 1.5,
            "not rated": None,
            "new": None,
            "-": None,
        }
        if val_str in text_map:
            return text_map[val_str]

        # Handle "4.5/5" format
        if "/" in val_str:
            val_str = val_str.split("/")[0].strip()

        try:
            rating = float(val_str)
            if rating < 0:
                return 0.0
            if rating > 5:
                return 5.0
            return round(rating, 1)
        except (ValueError, TypeError):
            return None

    df["rating"] = df["rating"].apply(parse_rating)
    return df


def _clean_votes(df: pd.DataFrame) -> pd.DataFrame:
    """Parse votes to integer; default to 0 if missing."""
    if "votes" not in df.columns:
        df["votes"] = 0
        return df

    def parse_votes(val):
        if pd.isna(val):
            return 0
        try:
            return max(0, int(float(str(val).replace(",", "").strip())))
        except (ValueError, TypeError):
            return 0

    df["votes"] = df["votes"].apply(parse_votes)
    return df


def _clean_highlights(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize highlights/tags; default to empty string."""
    if "highlights" not in df.columns:
        df["highlights"] = ""
        return df

    df["highlights"] = (
        df["highlights"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    return df


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Master cleaning pipeline — runs all individual cleaners in order."""
    initial_count = len(df)
    logger.info(f"Starting data cleaning ({initial_count} rows)")

    # 1. Normalize column names
    df = _normalize_columns(df)
    _validate_required_columns(df)

    # 2. Clean individual fields
    df = _clean_name(df)
    df = _clean_city(df)
    df = _clean_cuisines(df)
    df = _clean_cost(df)
    df = _clean_rating(df)
    df = _clean_votes(df)
    df = _clean_highlights(df)

    # 3. Drop rows with null rating or null name (unusable)
    df = df.dropna(subset=["name", "rating"])
    df = df[df["name"].str.strip() != ""]

    # 4. Drop exact duplicates on (name, city)
    before_dedup = len(df)
    df = df.sort_values("votes", ascending=False).drop_duplicates(
        subset=["name", "city"], keep="first"
    )
    dupes_removed = before_dedup - len(df)
    if dupes_removed > 0:
        logger.info(f"Removed {dupes_removed} duplicate entries (by name + city)")

    # 5. Reset index
    df = df.reset_index(drop=True)

    logger.info(
        f"Cleaning complete: {initial_count} → {len(df)} rows "
        f"({initial_count - len(df)} removed)"
    )

    return df


# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Derive budget buckets
# ═══════════════════════════════════════════════════════════════════════════

def derive_budget(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map cost_for_two into budget categories:
        Low    : ₹0 – ₹500
        Medium : ₹501 – ₹1500
        High   : ₹1501+
    Rows with null cost default to "Unknown".
    """
    def categorize(cost):
        if pd.isna(cost):
            return "Unknown"
        if cost <= BUDGET_LOW_MAX:
            return "Low"
        if cost <= BUDGET_MEDIUM_MAX:
            return "Medium"
        return "High"

    df["budget"] = df["cost_for_two"].apply(categorize)

    # Log distribution
    dist = df["budget"].value_counts()
    logger.info(f"Budget distribution:\n{dist.to_string()}")

    return df


# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Select final columns & export
# ═══════════════════════════════════════════════════════════════════════════

FINAL_COLUMNS = [
    "name",
    "city",
    "cuisines",
    "cost_for_two",
    "budget",
    "rating",
    "votes",
    "highlights",
]


def export_clean_csv(df: pd.DataFrame) -> Path:
    """Select final columns and export to CSV."""
    # Only keep columns that exist (highlights/votes may be absent in some datasets)
    available_cols = [c for c in FINAL_COLUMNS if c in df.columns]
    df_final = df[available_cols].copy()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(CLEAN_CSV, index=False, encoding="utf-8")

    logger.info(f"[OK] Clean dataset exported -> {CLEAN_CSV}")
    logger.info(f"   Rows: {len(df_final)}  |  Columns: {list(df_final.columns)}")

    return CLEAN_CSV


# ═══════════════════════════════════════════════════════════════════════════
# Validation summary
# ═══════════════════════════════════════════════════════════════════════════

def print_summary(df: pd.DataFrame) -> None:
    """Print a quick validation summary of the clean dataset."""
    print("\n" + "=" * 60)
    print("  [OK] CLEAN DATASET SUMMARY")
    print("=" * 60)
    print(f"  Total restaurants : {len(df):,}")
    print(f"  Unique cities     : {df['city'].nunique()}")
    print(f"  Unique cuisines   : {df['cuisines'].nunique()}")
    print(f"  Rating range      : {df['rating'].min():.1f} - {df['rating'].max():.1f}")

    if "cost_for_two" in df.columns:
        valid_cost = df["cost_for_two"].dropna()
        if len(valid_cost) > 0:
            print(f"  Cost range        : Rs.{valid_cost.min():,.0f} - Rs.{valid_cost.max():,.0f}")

    if "budget" in df.columns:
        print(f"\n  Budget breakdown:")
        for budget, count in df["budget"].value_counts().items():
            pct = (count / len(df)) * 100
            print(f"    {budget:10s} : {count:5,} ({pct:.1f}%)")

    print(f"\n  Top 5 cities:")
    for city, count in df["city"].value_counts().head(5).items():
        print(f"    {city:20s} : {count:,} restaurants")

    print(f"\n  Sample rows:")
    try:
        sample_str = df.head(3).to_string(index=False)
        # Replace characters that cp1252 can't handle
        print(sample_str.encode("ascii", errors="replace").decode("ascii"))
    except Exception:
        print("    (Could not display sample rows due to encoding issues)")
    print("=" * 60 + "\n")


# ═══════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline() -> pd.DataFrame:
    """Run the full data pipeline: fetch → clean → derive budget → export."""
    logger.info("=" * 50)
    logger.info("  Phase 1: Data Foundation Pipeline")
    logger.info("=" * 50)

    # Step 1: Fetch
    df_raw = fetch_dataset()

    # Step 2: Clean & normalize
    df_clean = clean_data(df_raw)

    # Step 3: Derive budget
    df_clean = derive_budget(df_clean)

    # Step 4: Export
    export_clean_csv(df_clean)

    # Step 5: Print summary
    print_summary(df_clean)

    return df_clean


def main():
    parser = argparse.ArgumentParser(
        description="Zomato Dataset Loader & Preprocessor (Phase 1)"
    )
    parser.add_argument(
        "--explore",
        action="store_true",
        help="Just explore the raw dataset schema without cleaning",
    )
    args = parser.parse_args()

    if args.explore:
        df = fetch_dataset()
        explore_schema(df)
    else:
        run_pipeline()


if __name__ == "__main__":
    main()
