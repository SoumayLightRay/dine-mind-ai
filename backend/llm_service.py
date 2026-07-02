"""
LLM Service — Phase 4: LLM Integration
========================================

Handles communication with Google Gemini to rank filtered restaurants
and generate human-like explanations.

Uses `google-genai`. Requires GEMINI_API_KEY env var.
"""

import os
import json
import logging
import requests
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configure LLMs
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL")
OLLAMA_URL = "http://localhost:11434/api/generate"

client = None
LLM_PROVIDER = None
LLM_AVAILABLE = False

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
    LLM_PROVIDER = "gemini"
    LLM_AVAILABLE = True
    logger.info("Using Gemini API for LLM.")
elif OLLAMA_MODEL:
    LLM_PROVIDER = "ollama"
    LLM_AVAILABLE = True
    logger.info(f"Using local Ollama with model: {OLLAMA_MODEL}")
else:
    logger.warning("Neither GEMINI_API_KEY nor OLLAMA_MODEL found. LLM features disabled.")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class LLMRestaurantRecommendation(BaseModel):
    name: str
    rank: int
    explanation: str
    match_score: int


class LLMResponse(BaseModel):
    recommendations: list[LLMRestaurantRecommendation]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are a knowledgeable food critic and restaurant advisor.
You will be provided with a user's dining preferences and a list of restaurants that already match their basic filters.
Your job is to rank these restaurants from BEST fit (1) to worst fit based on how well they align with the user's specific vibe and preferences.
For each restaurant, provide a 2-3 sentence explanation of why it's a good match, specifically referencing their preferences.

You MUST respond in valid JSON format matching this exact schema:
{
  "recommendations": [
    {
      "name": "Exact Name of Restaurant",
      "rank": 1,
      "explanation": "Why this is a great pick...",
      "match_score": 95
    }
  ]
}

CRITICAL RULES:
1. ONLY return the JSON object. Do NOT wrap it in markdown code blocks (e.g. ```json). Do NOT add conversational text before or after the JSON.
2. ONLY include restaurants that were provided in the RESTAURANTS list. Do NOT hallucinate or invent new restaurants.
3. The "name" field must EXACTLY MATCH the name provided in the RESTAURANTS list.
4. "match_score" should be an integer between 0 and 100.
5. Do not make assumptions based on stereotypes. Focus on the food, budget, and features.
"""


def _build_prompt(preferences: dict, restaurants: list[dict]) -> str:
    """Build the final text prompt to send to the LLM."""
    prefs_str = "\n".join([f"- {k.title()}: {v}" for k, v in preferences.items()])
    
    # Format restaurants as a clean list of dictionaries
    # We only include relevant fields to save context window space
    slim_restaurants = []
    for r in restaurants:
        slim = {
            "name": r.get("name"),
            "cuisines": r.get("cuisines"),
            "rating": r.get("rating"),
            "cost_for_two": r.get("cost_for_two"),
            "highlights": r.get("highlights")
        }
        slim_restaurants.append(slim)

    rest_str = json.dumps(slim_restaurants, indent=2)

    return f"""
USER PREFERENCES:
{prefs_str}

RESTAURANTS TO RANK:
{rest_str}
"""


def _clean_json_response(raw_text: str) -> str:
    """Strip markdown code blocks if the LLM ignores instructions and adds them."""
    text = raw_text.strip()
    if text.startswith("```"):
        # Find the first newline and the last newline to strip the ```json and ```
        first_newline = text.find("\n")
        last_newline = text.rfind("\n")
        if first_newline != -1 and last_newline != -1 and last_newline > first_newline:
            text = text[first_newline:last_newline].strip()
    return text


# ---------------------------------------------------------------------------
# Core Service Function
# ---------------------------------------------------------------------------

def enhance_recommendations(preferences: dict, restaurants: list[dict]) -> list[dict]:
    """
    Takes the filtered restaurants, sends them to Gemini for ranking and explanations,
    and returns the enhanced list.

    If LLM is unavailable or fails, returns the original list unmodified but adds
    a default explanation indicating AI was unavailable.
    """
    if not LLM_AVAILABLE or not restaurants:
        return _fallback_recommendations(restaurants)

    prompt = _build_prompt(preferences, restaurants)
    
    try:
        logger.info(f"Sending {len(restaurants)} restaurants to {LLM_PROVIDER} for ranking...")
        
        raw_text = ""
        
        if LLM_PROVIDER == "gemini":
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.7,
                    response_mime_type="application/json"
                )
            )
            raw_text = response.text
            
        elif LLM_PROVIDER == "ollama":
            # For Ollama, we send the system prompt + user prompt combined
            full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": full_prompt,
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": 0.7
                }
            }
            res = requests.post(OLLAMA_URL, json=payload, timeout=45)
            res.raise_for_status()
            raw_text = res.json().get("response", "")
        
        # Parse and validate
        clean_text = _clean_json_response(raw_text)
        data = json.loads(clean_text)
        
        # Validate schema using Pydantic
        validated_data = LLMResponse(**data)
        
        # Merge LLM data with original data
        enhanced = _merge_results(restaurants, validated_data.recommendations)
        return enhanced

    except Exception as e:
        logger.error(f"LLM enhancement failed: {e}")
        return _fallback_recommendations(restaurants)


def _merge_results(original: list[dict], llm_results: list[LLMRestaurantRecommendation]) -> list[dict]:
    """
    Merge the LLM's ranking and explanations into the original restaurant data.
    Removes hallucinations. Sorts by the LLM's rank.
    """
    # Create a lookup dictionary for fast access by name
    orig_map = {r["name"].lower().strip(): r for r in original}
    
    enhanced = []
    for llm_rec in llm_results:
        key = llm_rec.name.lower().strip()
        if key in orig_map:
            # It's a valid restaurant from our list
            r = orig_map[key].copy()
            r["ai_explanation"] = llm_rec.explanation
            r["match_score"] = llm_rec.match_score
            r["rank"] = llm_rec.rank
            enhanced.append(r)
        else:
            logger.warning(f"LLM hallucinated a restaurant: {llm_rec.name}")
            
    # Sort by rank
    enhanced.sort(key=lambda x: x.get("rank", 999))
    
    # If the LLM missed some restaurants, append them at the end without AI data
    enhanced_names = {r["name"].lower().strip() for r in enhanced}
    for r in original:
        if r["name"].lower().strip() not in enhanced_names:
            unranked = r.copy()
            unranked["ai_explanation"] = "No AI review available for this pick."
            enhanced.append(unranked)

    return enhanced


def _fallback_recommendations(restaurants: list[dict]) -> list[dict]:
    """Fallback if LLM fails: just return the original list."""
    res = []
    for r in restaurants:
        r_copy = r.copy()
        r_copy["ai_explanation"] = None
        res.append(r_copy)
    return res
