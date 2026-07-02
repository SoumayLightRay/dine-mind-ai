"""
Flask API Server — Phase 3: Filter & Query Engine
===================================================

REST API for the Zomato AI Restaurant Recommender.

Endpoints:
    POST /api/recommend      — Get filtered restaurant recommendations
    GET  /api/filters        — Get available filter values (cities, cuisines, etc.)
    GET  /api/health         — Health check

Edge cases handled:
    - Malformed JSON (400)
    - Empty request body (400)
    - Wrong HTTP method (405)
    - Missing Content-Type (415)
    - CSV file missing at runtime (503)
    - CORS for cross-origin frontend requests

Usage:
    python app.py                        # Run on default port 5000
    python app.py --port 8000            # Run on custom port
    python app.py --host 0.0.0.0         # Bind to all interfaces
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS

from filter_engine import (
    sanitize_preferences,
    filter_restaurants,
    get_available_filters,
)
from llm_service import enhance_recommendations, LLM_AVAILABLE

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
CLEAN_CSV = DATA_DIR / "restaurants_clean.csv"

# ---------------------------------------------------------------------------
# Flask App Setup
# ---------------------------------------------------------------------------
app = Flask(__name__)

# CORS — allow all origins in development. Tighten for production.
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"],
    }
})

# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------
_df: pd.DataFrame | None = None
_data_loaded_at: str | None = None
_filters_cache = None


def load_data() -> pd.DataFrame:
    """Load the clean CSV into a DataFrame. Cache in memory."""
    global _df, _data_loaded_at

    if _df is not None:
        return _df

    if not CLEAN_CSV.exists():
        logger.error(f"Clean CSV not found at {CLEAN_CSV}")
        logger.error("Run `python data_loader.py` first to generate it.")
        raise FileNotFoundError(f"Restaurant data file not found: {CLEAN_CSV}")

    logger.info(f"Loading restaurant data from {CLEAN_CSV}")
    _df = pd.read_csv(CLEAN_CSV, encoding="utf-8")
    _data_loaded_at = datetime.utcnow().isoformat() + "Z"

    logger.info(f"Loaded {len(_df)} restaurants into memory")
    return _df


def get_df() -> pd.DataFrame:
    """Get the cached DataFrame, loading if necessary."""
    if _df is None:
        return load_data()
    return _df


# ═══════════════════════════════════════════════════════════════
# Error Handlers
# ═══════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed. Use POST for /api/recommend."}), 405


@app.errorhandler(500)
def internal_error(e):
    logger.exception("Internal server error")
    return jsonify({"error": "Internal server error"}), 500


# ═══════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════

@app.route("/api/recommend", methods=["POST"])
def recommend():
    """
    POST /api/recommend

    Accepts user preferences and returns filtered restaurant recommendations.

    Request Body (JSON):
        {
            "location": "Indiranagar",         // optional
            "budget": "Medium",                 // optional: "Low"|"Medium"|"High"
            "cuisines": ["Italian", "Chinese"], // optional
            "min_rating": 4.0,                  // optional: 0-5
            "extras": ["Dine-out"]              // optional
        }

    Response (JSON):
        {
            "recommendations": [...],
            "total_matches": 12,
            "query_summary": "Top Italian restaurants in Indiranagar, rated 4.0+",
            "filters_applied": [...],
            "data_last_updated": "2026-07-02T18:30:00Z"
        }
    """
    # ─── Validate Content-Type ───
    content_type = request.content_type or ""
    if "application/json" not in content_type and request.data:
        return jsonify({
            "error": "Content-Type must be application/json",
        }), 415

    # ─── Parse JSON body ───
    try:
        body = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({
            "error": "Invalid JSON in request body",
        }), 400

    if body is None:
        return jsonify({
            "error": "Request body is required. Send a JSON object with your preferences.",
        }), 400

    if not isinstance(body, dict):
        return jsonify({
            "error": "Request body must be a JSON object.",
        }), 400

    # ─── Load data ───
    try:
        df = get_df()
    except FileNotFoundError:
        return jsonify({
            "error": "Restaurant data is unavailable. Please try again later.",
        }), 503

    # ─── Sanitize & filter ───
    preferences = sanitize_preferences(body)
    result = filter_restaurants(df, preferences)

    # ─── LLM Enhancement (Phase 4) ───
    if result["total_matches"] > 0:
        # Pass the top results (from filter engine) to the LLM
        enhanced = enhance_recommendations(preferences, result["recommendations"])
        result["recommendations"] = enhanced
        
        # Determine if AI actually provided explanations
        has_ai = any(r.get("ai_explanation") for r in enhanced)
        result["ai_available"] = has_ai
    else:
        result["ai_available"] = False

    # Add metadata
    result["data_last_updated"] = _data_loaded_at

    return jsonify(result), 200


@app.route("/api/filters", methods=["GET"])
def api_filters():
    """Return dynamically extracted available filters from the dataset."""
    global _filters_cache
    
    # Use cached filters if available
    if _filters_cache is not None:
        return jsonify(_filters_cache), 200

    try:
        df = get_df()
        _filters_cache = get_available_filters(df)
        return jsonify(_filters_cache), 200
    except Exception as e:
        logger.error(f"Error serving filters: {e}")
        return jsonify({"error": "Failed to load filter metadata"}), 500


@app.route("/api/health", methods=["GET"])
def health():
    """
    GET /api/health

    Simple health check endpoint.
    """
    try:
        df = get_df()
        return jsonify({
            "status": "healthy",
            "restaurants_loaded": len(df),
            "data_last_updated": _data_loaded_at,
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
        }), 503


# ═══════════════════════════════════════════════════════════════
# Startup
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Zomato Recommender API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5000, help="Port to run on")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    # Pre-load data at startup so first request isn't slow
    try:
        load_data()
    except FileNotFoundError:
        logger.error(
            "Cannot start: restaurant data not found.\n"
            "Run `python data_loader.py` first to generate the clean CSV."
        )
        sys.exit(1)

    logger.info(f"Starting server on http://{args.host}:{args.port}")
    logger.info("Endpoints:")
    logger.info(f"  POST http://{args.host}:{args.port}/api/recommend")
    logger.info(f"  GET  http://{args.host}:{args.port}/api/filters")
    logger.info(f"  GET  http://{args.host}:{args.port}/api/health")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
