# Streamlit Deployment Plan

This document outlines the step-by-step procedure to deploy the **Zomato AI Restaurant Recommendation** application. The primary deployment path is **Streamlit Community Cloud**, with fallback/hybrid options for containerized deployment (e.g., Docker) and running a split API backend.

---

## 1. Prerequisites

Before starting the deployment, ensure you have:
1. A **GitHub account** containing the repository.
2. A **Streamlit Community Cloud account** linked to your GitHub account (sign up at [share.streamlit.io](https://share.streamlit.io/)).
3. A **Groq API key** (from [console.groq.com](https://console.groq.com/)) to power the LLM ranking and explanation engine.
4. Access to the Hugging Face dataset (no token required as the dataset `ManikaSaini/zomato-restaurant-recommendation` is public, but the app must have outbound internet access).

---

## 2. Deployment Architecture

The application can be deployed in two modes:

### Mode A: Standalone Streamlit App (Recommended & Simplest)
In this mode, Streamlit runs the application logic directly on its server, bypassing the FastAPI backend entirely by importing the core python modules (`src.data`, `src.services`, `src.llm`).

```
GitHub (Code) ──► Streamlit Community Cloud (Front-end + Back-end logic)
                                   │
                                   ├──► Hugging Face (Dataset Ingestion)
                                   └──► Groq API (LLM Ranker)
```

### Mode B: Connected (API + Streamlit Frontend)
In this mode, the FastAPI backend is hosted on a container hosting platform (e.g., Railway, Render, or Fly.io) and Streamlit is deployed separately, communicating with FastAPI via HTTP requests.

```
Streamlit Cloud (Frontend UI)
       │
       ▼ (HTTP request with API_BASE_URL)
Railway / Render / Fly.io (FastAPI Backend)
       │
       ├──► Hugging Face (Dataset Ingestion)
       └──► Groq API (LLM Ranker)
```

---

## 3. Step-by-Step Deployment Guide (Mode A: Standalone)

This is the standard and most cost-effective deployment path.

### Step 3.1: Prepare the Repository
Ensure that the codebase is clean and contains the following files at the root level:
- `requirements.txt`: Streamlit Cloud automatically reads this file to install Python dependencies.
- `src/ui/app.py`: The entrypoint to the Streamlit user interface.
- `.gitignore`: Confirm `.env` and `data/` are excluded to avoid committing secrets or heavy cache files.

> [!NOTE]  
> The import fallbacks in [app.py](file:///d:/OneDrive/Desktop/Zomato%20Recommendation/src/ui/app.py) will automatically bypass the local Windows paths and import the modules from the current directory, which works seamlessly on the Streamlit Linux container.

### Step 3.2: Configure Secrets in Streamlit Community Cloud
Streamlit Community Cloud provides a secure secrets manager that populates environment variables at runtime.

1. Go to the [Streamlit Share Dashboard](https://share.streamlit.io/).
2. Click **New app** in the top right corner.
3. Select your repository, branch (e.g., `main`), and set the Main file path to:
   ```text
   src/ui/app.py
   ```
4. Click on **Advanced settings...** before deploying.
5. In the **Secrets** text area, enter your environment variables in TOML format:

```toml
# Groq API Configuration
LLM_PROVIDER = "groq"
LLM_API_KEY = "gsk_your_actual_groq_api_key_here"
LLM_MODEL = "llama-3.3-70b-versatile"
LLM_TIMEOUT = 15.0

# Ingestion Configuration
HF_DATASET_NAME = "ManikaSaini/zomato-restaurant-recommendation"
MAX_CANDIDATES = 30
DEFAULT_TOP_K = 5
DATA_CACHE_PATH = "data/cache.parquet"
```

6. Click **Save** and then click **Deploy!**

---

## 4. Step-by-Step Deployment Guide (Mode B: Connected API)

If you wish to deploy the FastAPI application separately to serve multiple clients, follow this approach.

### Step 4.1: Deploy the FastAPI Backend
You can deploy the FastAPI server using the provided `Dockerfile`.

1. **Deploy to Render / Railway**:
   - Link your GitHub repository.
   - Choose **Web Service** (Render) or **New Service** (Railway).
   - Set the build settings to use the `Dockerfile` at the root of the project.
   - Add the following Environment Variables in the platform's configuration dashboard:
     - `PORT` = `8000` (or the port defined by the host)
     - `LLM_PROVIDER` = `groq`
     - `LLM_API_KEY` = `gsk_your_groq_key`
     - `LLM_MODEL` = `llama-3.3-70b-versatile`
     - `HF_DATASET_NAME` = `ManikaSaini/zomato-restaurant-recommendation`
     - `DATA_CACHE_PATH` = `/tmp/cache.parquet` (to ensure write permissions in read-only containers)
2. Verify that the health check endpoint returns 200: `https://your-api-url.onrender.com/health`

### Step 4.2: Deploy Streamlit to Streamlit Cloud
1. Create a new app on Streamlit Community Cloud pointing to `src/ui/app.py`.
2. In **Advanced settings... -> Secrets**, specify the backend URL:
```toml
API_BASE_URL = "https://your-api-url.onrender.com"
```
3. Deploy! The frontend will auto-detect the FastAPI backend via the health check and switch to **CONNECTED TO API** mode.

---

## 5. Performance and Resource Management

### Ingestion Cold Starts
Streamlit containers are ephemeral. The first request will trigger a cold-start ingestion:
- **Hugging Face Download**: The CSV dataset (~10-50MB) is downloaded.
- **Preprocessing & Caching**: The data is preprocessed, normalized, and saved to `data/cache.parquet` or `/tmp/cache.parquet`.
- **Index Construction**: The index is loaded in memory.
- **Duration**: The initial startup might take 10-15 seconds. Subsequent recommendation requests will execute in sub-second times (local indexing) + the Groq API completion time (2-5s).

### Memory Constraints
Streamlit Community Cloud offers up to **1 GB of RAM** per application.
- The preprocessed restaurant dataset is highly optimized and stored as normalized structures.
- It consumes approximately **~80-150 MB** of RAM once loaded, leaving ample headroom for session states and concurrently handling requests.

---

## 6. Resilience and Troubleshooting

### Common Deployment Issues

| Issue | Cause | Resolution |
|-------|-------|------------|
| **App fails on launch with `ModuleNotFoundError`** | Missing dependencies in the deployment container | Streamlit Cloud automatically installs packages listed in `requirements.txt`. Ensure all imports are represented. |
| **App runs in "Offline Mode" when API is expected** | Streamlit cannot connect to the FastAPI URL | Check that the `API_BASE_URL` secret has no trailing slashes and the FastAPI container is not sleeping (e.g. Render free tier spin-down). |
| **`Authentication Error` from LLM** | Groq key is missing or invalid | Verify the `LLM_API_KEY` is configured correctly in the Streamlit Secrets manager and contains the `gsk_` prefix. |
| **Exceeded Memory Limit (Crash)** | Cache bloating or large candidate arrays | The application caps candidate parameters (`MAX_CANDIDATES` default = 30) and implements an LRU cache with eviction rules. Do not increase `MAX_CANDIDATES` above 100 on Streamlit Cloud. |
| **"Degraded Mode" is always active** | Groq API rate limits or network issues | Check Groq API console limits. If requests repeatedly time out, increase `LLM_TIMEOUT` to `25.0` in the Secrets. |
