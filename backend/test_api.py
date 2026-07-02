"""Quick API test script for Phase 3 endpoints."""
import requests
import json

BASE = "http://127.0.0.1:5000"

# Test 1: Health check
print("=" * 50)
print("TEST 1: Health Check")
print("=" * 50)
r = requests.get(f"{BASE}/api/health")
print(f"Status: {r.status_code}")
print(json.dumps(r.json(), indent=2))

# Test 2: Get filters
print("\n" + "=" * 50)
print("TEST 2: Available Filters")
print("=" * 50)
r = requests.get(f"{BASE}/api/filters")
data = r.json()
print(f"Status: {r.status_code}")
print(f"Total restaurants: {data['total_restaurants']}")
print(f"Cities: {len(data['cities'])} (top 5: {[c['name'] for c in data['cities'][:5]]})")
print(f"Cuisines: {len(data['cuisines'])}")
print(f"Highlights: {data['highlights']}")
print(f"Rating range: {data['rating_range']}")

# Test 3: Recommend with filters
print("\n" + "=" * 50)
print("TEST 3: Recommend (Indiranagar + Medium + Italian/Chinese + 4.0+)")
print("=" * 50)
r = requests.post(f"{BASE}/api/recommend", json={
    "location": "Indiranagar",
    "budget": "Medium",
    "cuisines": ["Italian", "Chinese"],
    "min_rating": 4.0,
    "extras": ["Dine-out"],
})
data = r.json()
print(f"Status: {r.status_code}")
print(f"Query: {data.get('query_summary')}")
print(f"Total matches: {data.get('total_matches')}")
print(f"Returned: {len(data.get('recommendations', []))}")
for i, rec in enumerate(data.get("recommendations", []), 1):
    print(f"  #{i} {rec['name']} | {rec['rating']} | {rec['cuisines'][:50]} | {rec['budget']}")

# Test 4: Empty body (should return top restaurants)
print("\n" + "=" * 50)
print("TEST 4: Empty preferences (top restaurants globally)")
print("=" * 50)
r = requests.post(f"{BASE}/api/recommend", json={})
data = r.json()
print(f"Status: {r.status_code}")
print(f"Total matches: {data.get('total_matches')}")
print(f"Returned: {len(data.get('recommendations', []))}")
for i, rec in enumerate(data.get("recommendations", [])[:3], 1):
    print(f"  #{i} {rec['name']} | {rec['rating']}")

# Test 5: No matches (impossible combo)
print("\n" + "=" * 50)
print("TEST 5: No matches (impossible filters)")
print("=" * 50)
r = requests.post(f"{BASE}/api/recommend", json={
    "location": "Timbuktu",
    "budget": "High",
    "min_rating": 5.0,
})
data = r.json()
print(f"Status: {r.status_code}")
print(f"Total matches: {data.get('total_matches')}")
print(f"Suggestion: {data.get('suggestion')}")

# Test 6: Malformed JSON
print("\n" + "=" * 50)
print("TEST 6: Malformed JSON")
print("=" * 50)
r = requests.post(f"{BASE}/api/recommend", data="{broken json", headers={"Content-Type": "application/json"})
print(f"Status: {r.status_code}")
print(f"Error: {r.json().get('error')}")

# Test 7: Fuzzy cuisine matching (typo)
print("\n" + "=" * 50)
print("TEST 7: Cuisine typo ('Italain' -> 'Italian')")
print("=" * 50)
r = requests.post(f"{BASE}/api/recommend", json={
    "cuisines": ["Italain"],
    "min_rating": 4.0,
})
data = r.json()
print(f"Status: {r.status_code}")
print(f"Total matches: {data.get('total_matches')}")
print(f"Filters: {data.get('filters_applied')}")
if data.get("recommendations"):
    print(f"  Top result: {data['recommendations'][0]['name']} | {data['recommendations'][0]['cuisines'][:50]}")

print("\n" + "=" * 50)
print("ALL TESTS COMPLETE")
print("=" * 50)
