/**
 * Zomato AI Restaurant Recommender — Frontend Logic
 * ==================================================
 * Phase 2: User Interface
 *
 * Handles:
 *  - Dynamic form population (cities, cuisines, extras)
 *  - Budget toggle, cuisine chip, and rating slider interactions
 *  - Form validation & submission
 *  - Loading skeletons and result card rendering
 *  - Offline detection
 *  - Debounced submit protection
 */

// ═══════════════════════════════════════════════════════════════
// CONFIG
// ═══════════════════════════════════════════════════════════════

const API_BASE = "http://localhost:5000/api";   // Phase 3 backend
const REQUEST_TIMEOUT_MS = 30_000;              // 30s max wait
const SKELETON_COUNT = 3;                       // Loading skeletons

// ═══════════════════════════════════════════════════════════════
// DATA — Extracted from restaurants_clean.csv (Phase 1 output)
// These will be served by the backend in Phase 3. For now,
// we embed them directly so the UI is fully functional standalone.
// ═══════════════════════════════════════════════════════════════

// These will be fetched dynamically from the backend
let CITIES = [];
let CUISINES = [];
let EXTRAS = [];

// ═══════════════════════════════════════════════════════════════
// DOM REFERENCES
// ═══════════════════════════════════════════════════════════════

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
  form:             $("#preference-form"),
  locationInput:    $("#location-input"),
  locationDatalist: $("#location-datalist"),
  budgetGroup:      $("#budget-group"),
  cuisineInput:     $("#cuisine-input"),
  cuisineDatalist:  $("#cuisine-datalist"),
  cuisineChips:     $("#cuisine-chips"),
  ratingSlider:   $("#rating-slider"),
  ratingValue:    $("#rating-value"),
  extrasGroup:    $("#extras-group"),
  submitBtn:      $("#submit-btn"),
  resultsSection: $("#results-section"),
  resultsHeader:  $("#results-header"),
  resultsTitle:   $("#results-title"),
  resultsCount:   $("#results-count"),
  resultsGrid:    $("#results-grid"),
  offlineBanner:  $("#offline-banner"),
};


// ═══════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════

const state = {
  selectedBudget: null,         // "Low" | "Medium" | "High" | null
  selectedCuisines: new Set(),  // Set of cuisine strings
  selectedExtras: new Set(),    // Set of extra ids
  isLoading: false,
  abortController: null,        // For cancelling in-flight requests
};


// ═══════════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════════

document.addEventListener("DOMContentLoaded", async () => {
  setupBudgetToggles();
  setupRatingSlider();
  setupFormSubmission();
  setupOfflineDetection();
  
  await fetchAndPopulateFilters();
});

async function fetchAndPopulateFilters() {
  try {
    const res = await fetch(`${API_BASE}/filters`);
    if (!res.ok) throw new Error("Failed to load filters");
    
    const data = await res.json();
    // The backend /api/filters returns cities as objects e.g. { name: "Bangalore", count: 123 }
    CITIES = data.cities.map(c => c.name);
    CUISINES = data.cuisines;
    EXTRAS = data.highlights.map(h => ({
      id: h.toLowerCase().replace(/[^a-z0-9]/g, '-'),
      label: h
    }));
    
    // Fallback to top if too many extras
    if (EXTRAS.length > 10) EXTRAS = EXTRAS.slice(0, 10);
  } catch (err) {
    console.warn("Could not fetch filters from backend, using basic defaults.", err);
    CITIES = ["Indiranagar", "Koramangala", "Whitefield", "Marathahalli", "Jayanagar"];
    CUISINES = ["North Indian", "South Indian", "Chinese", "Italian", "Cafe"];
    EXTRAS = [{id: "dine-out", label: "Dine-out"}, {id: "delivery", label: "Delivery"}];
  }

  populateLocations();
  populateCuisines();
  populateExtras();
}


// ─── Populate Location Datalist ───
function populateLocations() {
  const frag = document.createDocumentFragment();
  CITIES.forEach((city) => {
    const opt = document.createElement("option");
    opt.value = city;
    frag.appendChild(opt);
  });
  dom.locationDatalist.innerHTML = "";
  dom.locationDatalist.appendChild(frag);
}


// ─── Populate Cuisine Datalist & Chips ───
function populateCuisines() {
  // Populate datalist
  const listFrag = document.createDocumentFragment();
  CUISINES.forEach((cuisine) => {
    const opt = document.createElement("option");
    opt.value = cuisine;
    listFrag.appendChild(opt);
  });
  dom.cuisineDatalist.innerHTML = "";
  dom.cuisineDatalist.appendChild(listFrag);

  // Populate popular chips (first 10)
  const chipsFrag = document.createDocumentFragment();
  const popularCuisines = CUISINES.slice(0, 10);
  popularCuisines.forEach((cuisine) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cuisine-chip";
    btn.textContent = cuisine;
    btn.dataset.cuisine = cuisine;
    btn.setAttribute("role", "option");
    btn.setAttribute("aria-selected", "false");

    btn.addEventListener("click", () => {
      btn.classList.toggle("active");
      const isActive = btn.classList.contains("active");
      btn.setAttribute("aria-selected", isActive);

      if (isActive) {
        state.selectedCuisines.add(cuisine);
      } else {
        state.selectedCuisines.delete(cuisine);
      }
    });

    chipsFrag.appendChild(btn);
  });
  dom.cuisineChips.innerHTML = "";
  dom.cuisineChips.appendChild(chipsFrag);
}


// ─── Populate Extras Checkboxes ───
function populateExtras() {
  const frag = document.createDocumentFragment();
  EXTRAS.forEach(({ id, label }) => {
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "extra-checkbox";
    checkbox.id = `extra-${id}`;
    checkbox.value = label;

    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        state.selectedExtras.add(label);
      } else {
        state.selectedExtras.delete(label);
      }
    });

    const lbl = document.createElement("label");
    lbl.className = "extra-label";
    lbl.htmlFor = `extra-${id}`;
    lbl.textContent = label;

    frag.appendChild(checkbox);
    frag.appendChild(lbl);
  });
  dom.extrasGroup.appendChild(frag);
}


// ─── Budget Toggle Buttons ───
function setupBudgetToggles() {
  const btns = dom.budgetGroup.querySelectorAll(".budget-btn");
  btns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const wasActive = btn.classList.contains("active");

      // Deactivate all
      btns.forEach((b) => b.classList.remove("active"));

      if (!wasActive) {
        btn.classList.add("active");
        state.selectedBudget = btn.dataset.budget;
      } else {
        // Toggle off
        state.selectedBudget = null;
      }
    });
  });
}


// ─── Rating Slider ───
function setupRatingSlider() {
  const updateDisplay = () => {
    const val = parseFloat(dom.ratingSlider.value).toFixed(1);
    dom.ratingValue.textContent = `${val} ★`;

    // Update slider fill via background gradient
    const pct = ((val - 1) / 4) * 100;
    dom.ratingSlider.style.background =
      `linear-gradient(to right, #e23744 0%, #ff6b6b ${pct}%, rgba(255,255,255,0.04) ${pct}%)`;
  };

  dom.ratingSlider.addEventListener("input", updateDisplay);
  updateDisplay(); // Initial state
}


// ═══════════════════════════════════════════════════════════════
// FORM SUBMISSION
// ═══════════════════════════════════════════════════════════════

function setupFormSubmission() {
  dom.form.addEventListener("submit", async (e) => {
    e.preventDefault();

    // Debounce: prevent double-submit
    if (state.isLoading) return;

    // Cancel any in-flight request
    if (state.abortController) {
      state.abortController.abort();
    }

    const preferences = gatherPreferences();

    // Validation: at least one preference should be set
    if (!preferences.location && !preferences.budget
        && preferences.cuisines.length === 0
        && !preferences.min_rating
        && preferences.extras.length === 0) {
      showEmptyState(
        "🤔",
        "Tell us what you like!",
        "Select at least one preference to get personalized recommendations."
      );
      return;
    }

    await fetchRecommendations(preferences);
  });
}


function gatherPreferences() {
  // Combine chip selections with typed input
  const allCuisines = Array.from(state.selectedCuisines);
  const typedCuisine = dom.cuisineInput.value.trim();
  if (typedCuisine && !allCuisines.includes(typedCuisine)) {
    allCuisines.push(typedCuisine);
  }

  return {
    location: dom.locationInput.value.trim() || null,
    budget: state.selectedBudget,
    cuisines: allCuisines,
    min_rating: parseFloat(dom.ratingSlider.value),
    extras: Array.from(state.selectedExtras),
  };
}


async function fetchRecommendations(preferences) {
  setLoading(true);
  showSkeletons();

  state.abortController = new AbortController();
  const timeoutId = setTimeout(() => state.abortController.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE}/recommend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(preferences),
      signal: state.abortController.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`Server error: ${response.status}`);
    }

    const data = await response.json();
    renderResults(data);

  } catch (err) {
    clearTimeout(timeoutId);

    if (err.name === "AbortError") {
      showErrorState(
        "Request timed out",
        "The server took too long to respond. Please try again."
      );
    } else if (!navigator.onLine) {
      showErrorState(
        "You're offline",
        "Please check your internet connection and try again."
      );
    } else {
      // Backend not running yet — show mock data for Phase 2 demo
      console.warn("Backend not available, showing mock results:", err.message);
      renderMockResults(preferences);
    }
  } finally {
    setLoading(false);
    state.abortController = null;
  }
}


// ═══════════════════════════════════════════════════════════════
// RENDERING
// ═══════════════════════════════════════════════════════════════

function renderResults(data) {
  const { recommendations = [], query_summary = "", total_matches = 0 } = data;

  if (recommendations.length === 0) {
    showEmptyState(
      "🍽️",
      "No matches found",
      "Try relaxing your filters — fewer restrictions means more options!"
    );
    return;
  }

  // Show results header
  dom.resultsHeader.classList.add("visible");
  dom.resultsTitle.textContent = query_summary || "Top Picks For You";
  dom.resultsCount.textContent = `${recommendations.length} of ${total_matches} matches`;

  // Render cards with stagger animation
  dom.resultsGrid.innerHTML = "";
  recommendations.forEach((restaurant, idx) => {
    const card = createRestaurantCard(restaurant, idx + 1);
    card.style.animationDelay = `${idx * 0.1}s`;
    dom.resultsGrid.appendChild(card);
  });

  // Smooth scroll to results
  dom.resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}


function createRestaurantCard(r, rank) {
  const card = document.createElement("article");
  card.className = "restaurant-card";
  card.setAttribute("aria-label", `Recommendation #${rank}: ${r.name}`);

  const budgetClass = r.budget
    ? `card__tag--budget-${r.budget.toLowerCase()}`
    : "";

  const costDisplay = r.cost_for_two
    ? `₹${Number(r.cost_for_two).toLocaleString("en-IN")} for two`
    : "Price N/A";

  const explanation = r.explanation || r.ai_explanation || "";

  card.innerHTML = `
    <div class="card__rank">${rank}</div>
    <h3 class="card__name">${escapeHtml(r.name)}</h3>
    <div class="card__meta">
      <span class="card__tag card__tag--rating">⭐ ${r.rating ?? "N/A"}</span>
      <span class="card__tag">${escapeHtml(r.cuisines || "Unknown")}</span>
      <span class="card__tag ${budgetClass}">💰 ${costDisplay}</span>
      ${r.city ? `<span class="card__tag">📍 ${escapeHtml(r.city)}</span>` : ""}
      ${r.highlights ? `<span class="card__tag">🏷️ ${escapeHtml(r.highlights)}</span>` : ""}
    </div>
    ${explanation ? `
      <div class="card__explanation">
        🤖 <strong>Why this pick:</strong> ${escapeHtml(explanation)}
      </div>
    ` : ""}
  `;

  return card;
}


// ─── Mock Results (Phase 2 standalone demo) ───
function renderMockResults(prefs) {
  const location = prefs.location || "Bangalore";
  const cuisine = prefs.cuisines.length > 0
    ? prefs.cuisines[0]
    : "North Indian";

  const mockData = {
    query_summary: `Top ${cuisine} restaurants in ${location}`,
    total_matches: 5,
    recommendations: [
      {
        name: "Byg Brewski Brewing Company",
        city: location,
        cuisines: `${cuisine}, Continental`,
        cost_for_two: 1600,
        budget: "High",
        rating: 4.9,
        highlights: "Dine-out",
        explanation: `A top-rated spot in ${location} known for its vibrant ambiance and excellent ${cuisine} options. Perfect for a memorable dining experience with friends and family.`,
      },
      {
        name: "Toit",
        city: location,
        cuisines: `${cuisine}, American, Pizza`,
        cost_for_two: 1500,
        budget: "Medium",
        rating: 4.7,
        highlights: "Dine-out",
        explanation: `One of ${location}'s most loved restaurants with consistently high ratings. Great craft beverages and a lively atmosphere complement the ${cuisine.toLowerCase()} menu.`,
      },
      {
        name: "Truffles",
        city: location,
        cuisines: "Cafe, American, Burger",
        cost_for_two: 900,
        budget: "Medium",
        rating: 4.7,
        highlights: "Dine-out",
        explanation: "Famous for its burgers and generous portions. An ideal choice for budget-conscious foodies who don't want to compromise on taste.",
      },
      {
        name: "AB's - Absolute Barbecues",
        city: location,
        cuisines: "European, Mediterranean, BBQ",
        cost_for_two: 1600,
        budget: "High",
        rating: 4.8,
        highlights: "Buffet",
        explanation: "An all-you-can-eat barbecue paradise with live grills at your table. Perfect for groups and special occasions.",
      },
      {
        name: "The Black Pearl",
        city: location,
        cuisines: "North Indian, European, Mediterranean",
        cost_for_two: 1400,
        budget: "Medium",
        rating: 4.7,
        highlights: "Pubs and bars",
        explanation: `A fantastic pub with a pirate-themed ambiance, offering a blend of Indian and European cuisines. Your ${prefs.budget || "medium"} budget fits perfectly here.`,
      },
    ],
  };

  // Filter mock results by budget if selected
  if (prefs.budget) {
    mockData.recommendations = mockData.recommendations.filter(
      (r) => r.budget === prefs.budget || prefs.budget === null
    );
    mockData.total_matches = mockData.recommendations.length;
  }

  renderResults(mockData);
}


// ═══════════════════════════════════════════════════════════════
// UI STATES
// ═══════════════════════════════════════════════════════════════

function setLoading(isLoading) {
  state.isLoading = isLoading;
  dom.submitBtn.disabled = isLoading;
  dom.submitBtn.classList.toggle("loading", isLoading);
}


function showSkeletons() {
  dom.resultsHeader.classList.remove("visible");
  dom.resultsGrid.innerHTML = "";

  for (let i = 0; i < SKELETON_COUNT; i++) {
    const skeleton = document.createElement("div");
    skeleton.className = "skeleton-card";
    skeleton.style.animationDelay = `${i * 0.1}s`;
    skeleton.innerHTML = `
      <div class="skeleton-line skeleton-line--title"></div>
      <div class="skeleton-line skeleton-line--short"></div>
      <div class="skeleton-line skeleton-line--medium"></div>
      <div class="skeleton-line skeleton-line--long"></div>
    `;
    dom.resultsGrid.appendChild(skeleton);
  }

  dom.resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}


function showEmptyState(icon, title, description) {
  dom.resultsHeader.classList.remove("visible");
  dom.resultsGrid.innerHTML = `
    <div class="empty-state">
      <div class="empty-state__icon">${icon}</div>
      <h3 class="empty-state__title">${escapeHtml(title)}</h3>
      <p class="empty-state__desc">${escapeHtml(description)}</p>
    </div>
  `;
}


function showErrorState(title, description) {
  dom.resultsHeader.classList.remove("visible");
  dom.resultsGrid.innerHTML = `
    <div class="error-state">
      <h3 class="error-state__title">${escapeHtml(title)}</h3>
      <p class="error-state__desc">${escapeHtml(description)}</p>
      <button class="retry-btn" onclick="document.getElementById('preference-form').requestSubmit()">
        Try Again
      </button>
    </div>
  `;
}


// ═══════════════════════════════════════════════════════════════
// OFFLINE DETECTION
// ═══════════════════════════════════════════════════════════════

function setupOfflineDetection() {
  const update = () => {
    dom.offlineBanner.classList.toggle("visible", !navigator.onLine);
  };

  window.addEventListener("online", update);
  window.addEventListener("offline", update);
  update();
}


// ═══════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════

function escapeHtml(text) {
  if (!text) return "";
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
  return String(text).replace(/[&<>"']/g, (c) => map[c]);
}
