# 🍽️ AI-Powered Restaurant Recommendation System

> **Inspired by Zomato** — A smart dining assistant that pairs structured restaurant data with LLM intelligence to deliver personalized, conversational recommendations.

---

## 🎯 Objective

Build an application that understands what a user is craving and surfaces the best restaurant matches — not just as raw data, but as thoughtful, human-like suggestions.

The system should:

- **Accept user preferences** — location, budget, cuisine, ratings, and more
- **Query a real-world dataset** of restaurants (Zomato)
- **Leverage an LLM** to reason over filtered results and generate personalized recommendations
- **Present results clearly** with explanations for *why* each restaurant was chosen

---

## ⚙️ System Workflow

### 1. Data Ingestion

| Step | Detail |
|------|--------|
| **Source** | [Zomato Restaurant Recommendation Dataset](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation) on Hugging Face |
| **Preprocess** | Clean and normalize the raw dataset |
| **Extract** | Restaurant name, location, cuisine, cost, rating, and other relevant fields |

### 2. User Input

Collect the following preferences from the user:

| Preference | Examples |
|------------|----------|
| 📍 Location | Delhi, Bangalore, Mumbai |
| 💰 Budget | Low, Medium, High |
| 🍕 Cuisine | Italian, Chinese, North Indian |
| ⭐ Minimum Rating | 3.5+, 4.0+ |
| 🏷️ Additional Filters | Family-friendly, Quick service, Outdoor seating |

### 3. Integration Layer

This is the bridge between raw data and intelligent output:

1. **Filter** the dataset based on user-specified criteria
2. **Structure** the filtered results into a well-designed LLM prompt
3. **Prompt engineering** — guide the LLM to reason, compare, and rank options meaningfully

### 4. Recommendation Engine (LLM)

The LLM acts as the brain of the system. It should:

- **Rank** the filtered restaurants based on overall fit to user preferences
- **Explain** each recommendation — *"This restaurant is perfect for you because…"*
- **Summarize** the top choices for quick decision-making

### 5. Output Display

Present the top recommendations in a clean, user-friendly format:

| Field | Description |
|-------|-------------|
| 🏪 Restaurant Name | Name of the recommended restaurant |
| 🍽️ Cuisine | Type(s) of cuisine served |
| ⭐ Rating | Aggregate user rating |
| 💰 Estimated Cost | Approximate cost for two |
| 🤖 AI Explanation | Why this restaurant was recommended for the user |

---

## 🧩 High-Level Architecture

```
User Input → Filter Engine → LLM Prompt Builder → LLM → Formatted Recommendations
     ↑                                                          ↓
     └──────────────────── Feedback Loop ───────────────────────┘
```

---

## ✅ Success Criteria

- Recommendations feel **personalized and conversational**, not like database dumps
- The system handles **edge cases** gracefully (e.g., no matches found, vague preferences)
- Results are returned **quickly** with a responsive user experience
- The LLM explanations are **accurate** and grounded in the actual restaurant data