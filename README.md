
# OTT Thumbnail Extractor (Pro, Web)

A small Flask-based web app that extracts **HD episode thumbnails** from OTT pages (ZEE5 + Hotstar).  
Works by server-side fetching of the episode page, then parsing **CDN image URLs** containing `pr_` tokens.

> ⚠️ If an episode page requires **login/DRM**, provide cookies from your account via the UI (optional).

## Features
- Paste episode URL → get HD thumbnail URLs
- Server-side fetch (bypasses browser CORS)
- ZEE5 & Hotstar patterns supported
- Optional custom headers/cookies (for protected pages)

## Quick Start (Local)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
# open http://localhost:8000
```

## Deploy (Render free tier suggested)
1. Push this folder to a GitHub repo.
2. Create a new **Web Service** on Render:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python app.py` (or use Procfile with `gunicorn` if preferred)
   - Port: 8000 (Render auto-detects)
3. Add **Environment**:
   - `PYTHON_VERSION` = `3.11`
4. Deploy and open the URL.

### Railway (alternative)
- Create a new service from repo, it will detect Python.
- Set Start Command: `python app.py`.

### Notes
- If you see "No thumbnail found", try opening the page in a normal browser and confirm the episode is public.
- For login-only pages, copy your cookies (e.g., via DevTools → Application → Cookies) and paste JSON into the UI's **Cookies** box.

## Security
- Cookies you paste are sent to **your own server** only (where you deploy). Do **not** paste personal cookies into someone else's server you don't control.
- This code does **not** store cookies; it just forwards them to the target site for the single request.

## Extend
- Add more regex patterns for SonyLiv/JioCinema CDNs.
- Parse embedded JSON-LD to pull canonical images even if no `pr_` in HTML.
