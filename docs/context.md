# Project Context: AI-Powered Restaurant Recommendation System

## Overview

This project is an **AI-powered restaurant recommendation service** inspired by Zomato. The system intelligently suggests restaurants based on user preferences by combining **structured restaurant data** with a **Large Language Model (LLM)** to produce personalized, human-like recommendations.

---

## Objective

Design and implement an application that:

1. Accepts user preferences (location, budget, cuisine, ratings, and more)
2. Uses a real-world restaurant dataset
3. Leverages an LLM to generate personalized, human-like recommendations
4. Displays clear and useful results to the user

---

## Dataset

| Property | Value |
|----------|-------|
| **Source** | Hugging Face |
| **URL** | https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation |
| **Key fields** | Restaurant name, location, cuisine, cost, rating, and related metadata |

---

## System Workflow

### 1. Data Ingestion

- Load and preprocess the Zomato dataset from Hugging Face
- Extract relevant fields: restaurant name, location, cuisine, cost, rating, etc.

### 2. User Input

Collect the following preferences from the user:

| Input | Examples / Options |
|-------|-------------------|
| **Location** | Delhi, Bangalore |
| **Budget** | Low, medium, high |
| **Cuisine** | Italian, Chinese |
| **Minimum rating** | Numeric threshold |
| **Additional preferences** | Family-friendly, quick service, etc. |

### 3. Integration Layer

- Filter and prepare relevant restaurant data based on user input
- Pass structured results into an LLM prompt
- Design a prompt that helps the LLM reason and rank options

### 4. Recommendation Engine

Use the LLM to:

- **Rank** restaurants by relevance to user preferences
- **Explain** why each recommendation fits the user
- **Optionally summarize** the overall set of choices

### 5. Output Display

Present top recommendations in a user-friendly format. Each result should include:

| Field | Description |
|-------|-------------|
| **Restaurant Name** | Name of the recommended restaurant |
| **Cuisine** | Type of cuisine offered |
| **Rating** | Restaurant rating |
| **Estimated Cost** | Approximate cost for the user |
| **AI-generated explanation** | Why this restaurant was recommended |

---

## Architecture Summary

```
User Preferences
       │
       ▼
┌──────────────────┐
│  Data Ingestion  │  ← Zomato dataset (Hugging Face)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│   User Input     │  ← Location, budget, cuisine, rating, extras
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Integration Layer│  ← Filter data → build LLM prompt
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Recommendation   │  ← LLM ranks, explains, summarizes
│     Engine       │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Output Display   │  ← Top recommendations with details
└──────────────────┘
```

---

## Key Requirements Checklist

- [ ] Load and preprocess Zomato dataset from Hugging Face
- [ ] Accept user preferences (location, budget, cuisine, min rating, extras)
- [ ] Filter restaurant data based on user input
- [ ] Build LLM prompt with structured filtered data
- [ ] Use LLM to rank restaurants and generate explanations
- [ ] Display results: name, cuisine, rating, cost, AI explanation

---

## Source

This context is derived from `docs/prblmstatement.txt`.
