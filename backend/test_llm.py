"""
Test script for LLM Service
"""
import os
import json
from llm_service import enhance_recommendations, LLM_AVAILABLE

# Dummy preferences
preferences = {
    "location": "Indiranagar",
    "budget": "Medium",
    "cuisines": ["Italian"],
    "min_rating": 4.0
}

# Dummy filtered restaurants
restaurants = [
    {
        "name": "Toit",
        "city": "Indiranagar",
        "cuisines": "Italian, American, Pizza",
        "rating": 4.7,
        "cost_for_two": 1500,
        "budget": "Medium",
        "highlights": "Dine-out, Pubs"
    },
    {
        "name": "Chianti",
        "city": "Indiranagar",
        "cuisines": "Italian",
        "rating": 4.6,
        "cost_for_two": 1500,
        "budget": "Medium",
        "highlights": "Dine-out"
    }
]

print("="*50)
print("TESTING LLM SERVICE")
print("="*50)
print(f"LLM_AVAILABLE: {LLM_AVAILABLE}")
if not LLM_AVAILABLE:
    print("Warning: GEMINI_API_KEY not set. Testing fallback mode only.")

enhanced = enhance_recommendations(preferences, restaurants)

print("\nRESULTS:")
for idx, r in enumerate(enhanced, 1):
    print(f"\n#{idx} {r['name']} (Rank: {r.get('rank', 'N/A')})")
    print(f"Match Score: {r.get('match_score', 'N/A')}")
    print(f"AI Explanation: {r.get('ai_explanation')}")
