import streamlit as st
import os

# Important: Streamlit runs from the root, but our backend modules are inside `backend/`
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from filter_engine import get_available_filters, filter_restaurants
from llm_service import enhance_recommendations
from data_loader import load_data, clean_and_normalize, CACHE_FILE

st.set_page_config(page_title="Zomato AI Recommender", page_icon="🍽️", layout="centered")

st.title("🍽️ Zomato AI Recommender")
st.write("Tell us what you're craving — our AI finds the perfect restaurant for you.")

@st.cache_data
def load_and_cache_data():
    if not os.path.exists(CACHE_FILE):
        df = load_data()
        clean_and_normalize(df)
    import pandas as pd
    return pd.read_csv(CACHE_FILE)

df = load_and_cache_data()
filters = get_available_filters(df)

# Sidebar for inputs
with st.sidebar:
    st.header("Your Preferences")
    
    # Location
    cities = [c["name"] for c in filters["cities"]]
    location = st.selectbox("📍 Location", options=["All Locations"] + cities)
    if location == "All Locations":
        location = None
        
    # Budget
    budget = st.selectbox("💰 Budget", options=["Medium", "Low", "High"])
    
    # Cuisines
    cuisines = st.multiselect("🍕 Cuisines", options=filters["cuisines"])
    
    # Rating
    min_rating = st.slider("⭐ Minimum Rating", min_value=1.0, max_value=5.0, value=3.0, step=0.5)
    
    # Extras
    extras = st.multiselect("🏷️ Type", options=filters["highlights"])
    
    search_clicked = st.button("🔍 Get Recommendations", use_container_width=True)

# Main Area
if search_clicked:
    prefs = {
        "location": location,
        "budget": budget,
        "cuisines": cuisines,
        "min_rating": min_rating,
        "extras": extras
    }
    
    with st.spinner("Searching and ranking via AI..."):
        # Filter data locally
        results_df = filter_restaurants(df, prefs)
        restaurants_list = results_df.to_dict("records")
        
        if not restaurants_list:
            st.warning("No restaurants found matching your exact criteria! Try broadening your search.")
        else:
            # Enhance with LLM
            enhanced = enhance_recommendations(prefs, restaurants_list)
            
            st.success(f"Found {len(enhanced)} top recommendations!")
            
            for rec in enhanced:
                with st.container():
                    st.subheader(f"#{rec['rank']} {rec['name']} (Match: {rec['match_score']}%)")
                    st.write(f"**Why you'll love it:** {rec['explanation']}")
                    st.divider()
