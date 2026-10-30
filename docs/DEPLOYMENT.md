# TwinVolt — Production Deployment Guide

## Architecture Overview

TwinVolt has a **split deployment architecture** for production:

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser                                                            │
│  ├─ UI (HTML/CSS/JS ES Modules)  ←──── Vercel CDN (static files)   │
│  ├─ REST API calls (fetch)       ────► FastAPI Backend              │
│  ├─ WebSocket (wss://)           ────► FastAPI Backend              │
│  ├─ Web Serial API               ────► Local USB device (direct)    │
│  └─ Web Bluetooth API            ────► Local BLE device (direct)    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI Backend  (Railway / Render / Docker / VPS / local)        │
│  ├─ REST API  (/api/v1/*)                                           │
│  ├─ WebSocket  (/api/v1/ws/*)                                       │
│  ├─ Mock Telemetry Generator                                        │
│  ├─ Digital Twin Runtime (in-memory, stateful)                     │
│  ├─ Gateway Daemon (TCP/UDP adapters)                               │
│  └─ Python Serial Gateway (USB → backend → WebSocket)              │
└─────────────────────────────────────────────────────────────────────┘
```

> **Why split?** The FastAPI backend maintains **persistent in-memory state**
> (Digital Twin runtime, WebSocket connections, Mock Generator, Gateway Daemon)
> that cannot survive Vercel's serverless cold-start / function isolation model.
> The static frontend (pure HTML + ES Modules) IS a perfect fit for Vercel's CDN.

---

## Option A — Full Local Development (Recommended Starting Point)

Everything runs on a single Python server. No Vercel, no separate backend needed.

```bash
# 1. Clone repository
git clone <repo-url>
cd "DIGITAL TWIN_latest"

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and review environment config
cp .env.example .env
# Edit .env if needed (defaults work out-of-the-box)

# 5. Start server
python -m src.server

# UI:      http://localhost:8000/
# API:     http://localhost:8000/docs
# WS:      ws://localhost:8000/api/v1/ws
```

All 11 navigation views are available. Hardware, Mock Generator, Digital Twin,
WebSocket — everything works. This is the reference baseline.

---

## Option B — Docker Deployment (Edge / Self-Hosted)

```bash
# Build image
docker build -f deploy/docker/Dockerfile -t twinvolt:latest .

# Run container
docker run -d \
  --name twinvolt \
  -p 8000:8000 \
  -e TWINVOLT_SEED_DEFAULTS=true \
  -e CORS_ORIGINS=https://your-vercel-app.vercel.app \
  twinvolt:latest

# Or use docker-compose
docker-compose -f deploy/docker/docker-compose.yml up -d
```

---

## Option C — Vercel Frontend + Railway/Render Backend (Full Production)

### Step 1 — Deploy the Backend

Deploy the FastAPI backend to **Railway** (recommended) or **Render**:

**Railway:**
1. Create a new Railway project
2. Connect your GitHub repo
3. Set the start command: `python -m src.server`
4. Set environment variables:
   ```
   TWINVOLT_HOST=0.0.0.0
   TWINVOLT_PORT=8000
   TWINVOLT_SEED_DEFAULTS=true
   TWINVOLT_LOG_LEVEL=INFO
   CORS_ORIGINS=https://your-app.vercel.app
   ```
5. Deploy — Railway gives you a URL like `https://twinvolt-production.up.railway.app`

**Render:**
1. Create a new Web Service
2. Build command: `pip install -r requirements.txt`
3. Start command: `python -m src.server`
4. Set the same environment variables as above

### Step 2 — Generate the Frontend Config

```bash
# Set your backend URLs
export TWINVOLT_API_BASE_URL="https://twinvolt-production.up.railway.app"
export TWINVOLT_WS_BASE_URL="wss://twinvolt-production.up.railway.app"

# Generate config.js with injected URLs
python scripts/build-config.py
```

This writes `src/ui/js/config.js` with your backend URLs embedded.

### Step 3 — Deploy the Frontend to Vercel

**Option 3a — Vercel CLI:**
```bash
npx vercel --prod
```

**Option 3b — Vercel Dashboard:**
1. Import your GitHub repository
2. Vercel auto-detects `vercel.json` and uses:
   - Output directory: `src/ui`
   - No build command (pure static files)
3. Add environment variables in Vercel Dashboard → Settings → Environment Variables:
   ```
   TWINVOLT_API_BASE_URL = https://twinvolt-production.up.railway.app
   TWINVOLT_WS_BASE_URL  = wss://twinvolt-production.up.railway.app
   ```
4. Add a build hook that runs `python scripts/build-config.py` before each deploy

**Option 3c — GitHub Actions (Fully Automated):**

Add this to your CI pipeline (after the test job):

```yaml
deploy-frontend:
  needs: test
  runs-on: ubuntu-latest
  if: github.ref == 'refs/heads/main'
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'
    - name: Inject backend URLs into config.js
      env:
        TWINVOLT_API_BASE_URL: ${{ secrets.TWINVOLT_API_BASE_URL }}
        TWINVOLT_WS_BASE_URL: ${{ secrets.TWINVOLT_WS_BASE_URL }}
      run: python scripts/build-config.py
    - name: Deploy to Vercel
      uses: amondnet/vercel-action@v25
      with:
        vercel-token: ${{ secrets.VERCEL_TOKEN }}
        vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
        vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
        vercel-args: '--prod'
```

Add `TWINVOLT_API_BASE_URL`, `TWINVOLT_WS_BASE_URL`, `VERCEL_TOKEN`,
`VERCEL_ORG_ID`, and `VERCEL_PROJECT_ID` as GitHub repository secrets.

---

## Hardware Access Notes

### Web Serial (USB) — Browser Direct

Web Serial API works **directly from the browser** when the page is served over HTTPS.

- ✅ Works on Vercel (HTTPS) with Chrome / Edge
- ✅ Works on local dev (localhost is a secure context)
- ❌ Does NOT work on Firefox or Safari
- ❌ Cannot work through a serverless function (browser API only)

The browser connects directly to the USB device. No backend involvement.

### Web Bluetooth (BLE) — Browser Direct

Web Bluetooth GATT API works **directly from the browser**.

- ✅ Works on Vercel (HTTPS) with Chrome / Edge
- ✅ Works on local dev (localhost is a secure context)
- ❌ Does NOT work on Firefox or Safari

### Python Serial Gateway (Backend USB → WebSocket)

The `src/gateway/` Python serial gateway runs on the **backend server**.
It reads from the local USB port on the machine where the backend is deployed
and streams telemetry to the Digital Twin via the WebSocket connection.

- ✅ Works in local dev / Docker / VPS / Railway (if hardware is attached)
- ❌ Does NOT work on serverless Vercel functions

---

## Environment Variables Reference

| Variable | Where | Description |
|---|---|---|
| `TWINVOLT_API_BASE_URL` | Vercel + CI/CD | Backend HTTPS URL (no trailing slash) |
| `TWINVOLT_WS_BASE_URL` | Vercel + CI/CD | Backend WSS URL (no trailing slash) |
| `CORS_ORIGINS` | Backend | Comma-separated allowed frontend origins |
| `TWINVOLT_HOST` | Backend | Bind host (default: 0.0.0.0) |
| `TWINVOLT_PORT` | Backend | Bind port (default: 8000) |
| `TWINVOLT_LOG_LEVEL` | Backend | Log level (INFO / DEBUG / WARNING) |
| `TWINVOLT_SEED_DEFAULTS` | Backend | Seed sample twin on startup (true/false) |
| `TWINVOLT_GATEWAY_AUTOSTART` | Backend | Auto-start gateway daemon (true/false) |
| `TWINVOLT_STORAGE_DIR` | Backend | Filesystem storage directory |

---

## Vercel Configuration (`vercel.json`)

The `vercel.json` at the repository root configures Vercel to:
- Serve `src/ui/` as the output directory (the complete SPA)
- Rewrite all routes to `index.html` (client-side routing)
- Set correct MIME types for JS modules (critical for `type="module"` imports)
- Apply security headers

No build step is required — TwinVolt's frontend is a vanilla ES Module SPA
with no bundler, no npm packages, and no build process.

---

## Troubleshooting

### "Cannot reach the TwinVolt API" in console
- Backend is not running or URL is wrong
- Check `window.TWINVOLT_API_BASE_URL` in the browser console
- Verify `scripts/build-config.py` was run before the Vercel deploy
- Check CORS: your Vercel URL must be in `CORS_ORIGINS` on the backend

### WebSocket stuck at RECONNECTING
- Backend WebSocket endpoint requires a persistent connection (not serverless)
- Verify the backend is running on Railway/Render (not a Vercel function)
- Check `window.TWINVOLT_WS_BASE_URL` is set to `wss://` (not `https://`)

### Navigation items show but views are blank
- JavaScript module import error — open browser DevTools → Console
- Usually means a JS file is 404 (check the Vercel output directory)
- Verify `vercel.json` outputDirectory is `src/ui`

### Mock Generator not starting
- Mock Generator requires the FastAPI backend (POST /api/v1/mock/start)
- Connect to the backend first (check API URL configuration)

### Web Serial / BLE not available
- Must be on HTTPS (Vercel provides this automatically)
- Must use Chrome or Edge (Firefox/Safari do not support these APIs)
- User must click a button to trigger the browser permission dialog

