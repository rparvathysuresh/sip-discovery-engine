# Deployment Plan: SIP Discovery Engine

This document provides a comprehensive, step-by-step guide to deploying the **SIP Discovery Engine**:
- **Backend API**: Hosted on **[Render](https://render.com)** (FastAPI, SQLite, ChromaDB vector store).
- **Frontend Web UI**: Hosted on **[Vercel](https://vercel.com)** (Edge static hosting with seamless API reverse proxying).

---

## Architecture Overview

```
                      ┌────────────────────────────────────────┐
                      │             User Browser               │
                      └──────────────────┬─────────────────────┘
                                         │
                   HTTPS Request: /      │    HTTPS: /api/v1/*
                   (HTML, CSS, JS)       │    (Proxy Rewrites)
                                         ▼
                      ┌────────────────────────────────────────┐
                      │         Vercel Edge Network            │
                      │  (Static assets from src/ui & rewrites)│
                      └──────────────────┬─────────────────────┘
                                         │  Reverse Proxy
                                         │  Forwarding
                                         ▼
                      ┌────────────────────────────────────────┐
                      │          Render Web Service            │
                      │    FastAPI + Uvicorn ($PORT)           │
                      │  ├─ SQLite Engine (Auto-Seeded)        │
                      │  ├─ ChromaDB Vector Store              │
                      │  └─ Groq LLM Client / Guardrails       │
                      └────────────────────────────────────────┘
```

### Why This Architecture?
1. **Zero CORS Issues**: Vercel rewrites `/api/:path*` directly to the Render backend domain at the edge. The browser communicates with a single origin, avoiding CORS blocks and mixed-content issues.
2. **Lightning Fast UI**: Static assets (HTML, CSS, modern JS) are cached globally across Vercel’s worldwide CDN.
3. **Resilient Cold Starts**: `scripts/seed_db.py` and the FastAPI `lifespan` handler automatically seed the SQLite database and warm up ChromaDB in under **0.3 seconds** even on Render's free tier.

---

## Prerequisites

Before starting, ensure you have:
1. The project repository pushed to GitHub:
   `https://github.com/rparvathysuresh/sip-discovery-engine.git`
2. A free account on **[Render](https://render.com)**.
3. A free account on **[Vercel](https://vercel.com)**.
4. A **Groq API Key** from [console.groq.com](https://console.groq.com) (for conversational synthesis).

---

## Phase 1: Deploy Backend on Render

### Method A: 1-Click Blueprint (Recommended)

The repository includes a ready-to-use [`render.yaml`](render.yaml).

1. Log in to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** in the top right and select **Blueprint**.
3. Connect your GitHub account and select **`rparvathysuresh/sip-discovery-engine`**.
4. Render will read `render.yaml` and configure:
   * **Service Name**: `sip-discovery-engine-api`
   * **Runtime**: `Python 3`
   * **Build Command**: `pip install -r requirements.txt && python scripts/seed_db.py`
   * **Start Command**: `uvicorn src.api.app:app --host 0.0.0.0 --port $PORT`
   * **Health Check Path**: `/api/v1/metadata`
5. Under Environment Variables, enter your **`GROQ_API_KEY`**.
6. Click **Apply**.
7. Once deployed, note your service URL (e.g., `https://sip-discovery-engine-api.onrender.com`).

---

### Method B: Manual Web Service Setup

If you prefer manual configuration via the Render Dashboard:

1. Click **New +** -> **Web Service**.
2. Select **Build and deploy from a Git repository**, then choose `sip-discovery-engine`.
3. Configure the following settings:
   * **Name**: `sip-discovery-engine-api`
   * **Region**: Choose closest to you (e.g., *Singapore*, *Oregon*, or *Frankfurt*).
   * **Branch**: `main`
   * **Root Directory**: *(Leave blank - defaults to repository root)*
   * **Runtime**: `Python 3`
   * **Build Command**:
     ```bash
     pip install -r requirements.txt && python scripts/seed_db.py
     ```
   * **Start Command**:
     ```bash
     uvicorn src.api.app:app --host 0.0.0.0 --port $PORT
     ```
   * **Instance Type**: `Free`
4. Expand **Advanced** -> **Add Environment Variable**:
   | Key | Value | Description |
   |---|---|---|
   | `PYTHON_VERSION` | `3.11.10` | Supported stable Python version |
   | `GROQ_API_KEY` | `gsk_...` | Your Groq API key from console.groq.com |
   | `DATABASE_PATH` | `data/sip_discovery.db` | Local SQLite database path |
5. In **Health Check Path**, enter: `/api/v1/metadata`.
6. Click **Create Web Service**.

### Verify Backend Deployment
Once the build completes (takes ~2 minutes):
1. Open `https://sip-discovery-engine-api.onrender.com/docs` in your browser. You should see the interactive Swagger UI.
2. Open `https://sip-discovery-engine-api.onrender.com/api/v1/metadata`. It should return a JSON response with:
   * `total_filtered_items: 1742`
   * `total_opportunity_areas: 8`

---

## Phase 2: Deploy Frontend on Vercel

### Step 1: Configure Backend URL in `vercel.json` (Completed)

The files `src/ui/vercel.json` and `vercel.json` are now configured with your active Render service:

```json
{
  "cleanUrls": true,
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://sip-discovery-engine-api.onrender.com/api/:path*"
    }
  ]
}
```

Commit and push this change to GitHub:
```bash
git add vercel.json src/ui/vercel.json
git commit -m "chore: configure Render backend URL in Vercel rewrites"
git push origin main
```

*(Note: If you ever want to bypass rewrites and point directly from JavaScript, you can also set `window.API_BASE_URL = "https://sip-discovery-engine-api.onrender.com"` in [`src/ui/js/config.js`](src/ui/js/config.js).)*

---

### Step 2: Import into Vercel

1. Log in to your [Vercel Dashboard](https://vercel.com/dashboard).
2. Click **Add New...** -> **Project**.
3. Select your GitHub repository: **`sip-discovery-engine`**.
4. In the **Configure Project** screen:
   * **Project Name**: `sip-discovery-engine`
   * **Framework Preset**: `Other`
   * **Root Directory**: Click *Edit* and select **`src/ui`** (or leave as root if using the root `vercel.json`).
   * **Build Command**: *(Leave empty — it's plain HTML/CSS/JS)*
   * **Output Directory**: *(Leave empty)*
5. Click **Deploy**.

Vercel will deploy your site in less than 15 seconds.

---

### Step 3: Verify the Live Application

Open your Vercel deployment URL (e.g. `https://sip-discovery-engine.vercel.app`):

1. **Persistent Data Scope Banner**:
   Verify it displays:
   * `1,742 conversations` (Filtered Corpus)
   * `5,268 items` (Raw Collected)
   * `Live SQLite Engine Active` status dot
2. **Opportunity Explorer Tab**:
   * Verify all 8 ranked opportunity cards load with percentage scores (`71%`, `28%`, `17%`).
   * Verify category dropdown filter works.
   * Verify slider filter works.
   * Click **Drill-Down Evidence** on any card: ensure the modal loads verbatim citations and highlights.
3. **Assistant Chat Tab**:
   * Click any prompt suggestion chip (e.g., *"What confuses investors about XIRR?"*).
   * Verify the assistant returns a complete, fully closed response with citations.
4. **AI Evidence Log Tab**:
   * Verify the audit timeline displays pipeline events across collection, preprocessing, and analysis.

---

## Production Considerations & Best Practices

### 1. Render Free Tier Spin-Down (Cold Starts)
* On Render's free tier, the web service enters sleep mode after 15 minutes of inactivity.
* When a new request arrives, Render takes **~30–50 seconds** to wake up the container.
* The frontend includes automatic loading skeletons and retry states to gracefully inform the user while the server wakes up.
* *Tip:* To prevent sleep, you can use a free uptime monitor (such as [UptimeRobot](https://uptimerobot.com) or [Cron-Job.org](https://cron-job.org)) to ping `https://<your-render-service>.onrender.com/api/v1/metadata` every 10 minutes.

### 2. Ephemeral Storage on Render
* Free-tier containers on Render have ephemeral disk storage (any file written during runtime is reset if the container restarts).
* To handle this seamlessly:
  * All 1,742 filtered items, 5,268 raw items, 8 opportunity areas, and structured seed records are stored in versioned JSON files in `data/`.
  * [`scripts/seed_db.py`](scripts/seed_db.py) and [`src/api/app.py`](src/api/app.py) automatically re-populate the SQLite database and index ChromaDB in memory on startup in **< 0.3s**.
  * No external database server (PostgreSQL/MySQL) is needed.

### 3. Custom Domain Configuration (Optional)
* **Frontend**: You can attach a custom domain (e.g., `discovery.yourdomain.com`) in **Vercel Project Settings -> Domains**.
* **Backend**: You can attach `api.yourdomain.com` in **Render Service Settings -> Custom Domains**.

---

## Deployment Checklist Summary

- [ ] Repository pushed to GitHub with `scripts/seed_db.py`, `render.yaml`, and `src/ui/js/config.js`
- [ ] Render Web Service created with `pip install -r requirements.txt && python scripts/seed_db.py`
- [ ] `GROQ_API_KEY` set in Render environment variables
- [ ] Render Health Check `/api/v1/metadata` verified
- [ ] Render URL inserted into `vercel.json` rewrites
- [ ] Vercel project created and deployed
- [ ] Full end-to-end user flows verified on the live Vercel URL

