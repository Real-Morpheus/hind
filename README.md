# HindMovie Scraper API 🚀

FastAPI wrapper around the HindMovie scraper — free deployment on Render.

---

## Files

```
hindmovie-api/
├── main.py           ← FastAPI app
├── requirements.txt  ← Python dependencies
├── render.yaml       ← Render config (optional)
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/search?q=...` | Search movies/series |
| GET | `/links?q=...` | Get download links for a movie |
| GET | `/links?q=...&season=1&episode=7` | Get links for a specific episode |
| GET | `/docs` | Interactive Swagger UI |

### Examples

```
GET /search?q=Inception
GET /links?q=Inception
GET /links?q=Queen+Of+Tears&season=1&episode=7
```

---

## Deploy on Render (Free) — Step by Step

### Step 1 — Create a GitHub repo

1. Go to https://github.com and log in (or create a free account).
2. Click **New repository** (top-right **+** button).
3. Name it `hindmovie-api`, set it to **Public**, click **Create repository**.
4. Upload the three files (`main.py`, `requirements.txt`, `render.yaml`) via the GitHub web UI
   or push with git:

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/hindmovie-api.git
git branch -M main
git push -u origin main
```

---

### Step 2 — Sign up / Log in to Render

1. Go to https://render.com
2. Click **Get Started for Free**.
3. Sign in with your GitHub account (recommended — makes connecting repos easy).

---

### Step 3 — Create a new Web Service

1. From the Render dashboard, click **+ New** → **Web Service**.
2. Click **Connect a repository** and select `hindmovie-api`.
   - If you don't see it, click **Configure account** and grant Render access to that repo.
3. Click **Connect**.

---

### Step 4 — Configure the service

Fill in the fields as follows:

| Field | Value |
|-------|-------|
| **Name** | `hindmovie-api` (or anything you like) |
| **Region** | Any (Singapore is fastest from India) |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Plan** | **Free** |

> ⚠️ Make sure **Plan = Free** before continuing.

Click **Create Web Service**.

---

### Step 5 — Wait for the build

Render will:
1. Clone your repo.
2. Run `pip install -r requirements.txt`.
3. Start the server with `uvicorn`.

You'll see live build logs. The first deploy takes ~2–3 minutes.
When it says **"Your service is live 🎉"**, you're done.

---

### Step 6 — Use your API

Your live URL will be something like:
```
https://hindmovie-api.onrender.com
```

Test it:
```
https://hindmovie-api.onrender.com/docs          ← Swagger UI
https://hindmovie-api.onrender.com/search?q=Jawan
https://hindmovie-api.onrender.com/links?q=Jawan
https://hindmovie-api.onrender.com/links?q=Queen+Of+Tears&season=1&episode=7
```

---

## ⚠️ Render Free Plan Notes

- **Sleeps after 15 min of inactivity** — first request after sleep takes ~30s to wake up.
- **750 free hours/month** — enough for one always-on service.
- **No credit card required.**

To avoid sleep, use a free uptime monitor like https://uptimerobot.com
to ping your `/` endpoint every 10 minutes.

---

## Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload
# Open http://localhost:8000/docs
```
