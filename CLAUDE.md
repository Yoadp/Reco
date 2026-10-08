# Reco — Claude Code Guide

Hebrew restaurant recommendation app for Israel. Full-stack: FastAPI backend + Next.js frontend.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router), TypeScript, TailwindCSS v4, React Query, RTL Hebrew |
| Backend | FastAPI (Python 3.13), SQLAlchemy async, Alembic, Poetry |
| Database | PostgreSQL 15 (PostGIS image via Docker) |
| Cache | Redis 7 (Docker, currently unused in code) |
| AI | Groq API — model `qwen/qwen3.8-27b`, raw httpx calls (no SDK) |
| Maps | Google Maps (`@react-google-maps/api`), Google Places API (New) |
| ML (planned) | Fine-tuned mT5-small for local Hebrew query parsing — see `backend/app/ml/` |

---

## Running Locally

```bash
# Start DB + Redis
docker-compose up -d

# Backend (from /backend)
poetry install
poetry run uvicorn app.main:app --reload --port 8000

# Frontend (from /frontend)
npm install
npm run dev        # → http://localhost:3000
```

---

## Environment Variables

### `backend/.env`
```
DATABASE_URL=postgresql+asyncpg://reco:reco@localhost:5432/reco
SECRET_KEY=change-me
GEMINI_API_KEY=gsk_...        # Groq key (named GEMINI for historical reasons)
GOOGLE_PLACES_API_KEY=AIza... # Same key as frontend Maps key
```

### `frontend/.env.local`
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=AIza...
```

**Note:** `GEMINI_API_KEY` is actually a Groq key (starts with `gsk_`). The name is a legacy artifact — do not rename it without updating `app/core/config.py` and `app/api/ai.py`.

---

## Project Structure

```
Reco/
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, router registration, CORS
│   │   ├── core/
│   │   │   ├── config.py        # pydantic-settings (reads .env)
│   │   │   ├── database.py      # async SQLAlchemy engine + get_db()
│   │   │   └── security.py      # bcrypt hashing, JWT creation/verification
│   │   ├── models/
│   │   │   ├── place.py         # Place model (main entity)
│   │   │   ├── user.py          # User model + cuisine_preferences, dietary_restrictions, price_preference
│   │   │   ├── recommendation.py
│   │   │   ├── rating.py        # PlaceRating (1–10 visit scores)
│   │   │   ├── saved_place.py   # SavedPlace (wishlist/favorites)
│   │   │   └── __init__.py      # imports all models for Alembic
│   │   ├── api/
│   │   │   ├── auth.py          # POST /auth/register, POST /auth/login
│   │   │   ├── places.py        # GET /places, GET /places/{slug}
│   │   │   ├── recommendations.py
│   │   │   ├── ratings.py       # POST /ratings, GET /ratings/place/{id}
│   │   │   ├── users.py         # GET /users/me, PATCH /users/me/preferences
│   │   │   ├── saved.py         # POST/DELETE/GET /saved — wishlist & favorites
│   │   │   ├── ai.py            # POST /ai/summarize (Groq)
│   │   │   └── deps.py          # get_current_user, optional bearer
│   │   ├── services/
│   │   │   └── places.py        # search_places(), nlp_parse_query(), smart_search_places()
│   │   ├── ml/
│   │   │   ├── data_generator.py  # Generate synthetic Hebrew training data
│   │   │   ├── train.py           # Fine-tune mT5-small
│   │   │   ├── inference.py       # Local model inference (drop-in for Groq)
│   │   │   └── evaluate.py        # Evaluate model accuracy
│   │   └── workers/
│   │       ├── seed.py                  # Seeds restaurants
│   │       ├── google_places_photos.py  # Fetches real photos + websiteUri from Places API
│   │       ├── menu_structurer.py       # Builds menu_items from google_places excerpts via Groq
│   │       ├── image_scraper.py         # Playwright-based image scraper
│   │       ├── google_ingestion.py
│   │       ├── article_scraper.py
│   │       └── menu_scraper.py
│   ├── alembic/                 # DB migrations
│   ├── data/                    # ML training data (gitignored) — train.jsonl, eval.jsonl
│   ├── models/                  # Trained ML models (gitignored) — models/query-parser/
│   └── pyproject.toml
└── frontend/
    ├── app/
    │   ├── layout.tsx            # Root layout: Navbar + Providers
    │   ├── page.tsx              # Discovery home page (trending, hidden gems, new)
    │   ├── restaurants/page.tsx  # Restaurant list + search + map + open-now + near-me
    │   ├── places/[slug]/page.tsx # Restaurant detail page
    │   ├── login/page.tsx
    │   ├── register/page.tsx
    │   └── profile/page.tsx      # Activity + Wishlist + Favorites + Preferences tabs
    ├── components/
    │   ├── Navbar.tsx            # Auth state from localStorage on mount
    │   ├── PlaceGrid.tsx         # Restaurant card grid (open badge, distance badge, heart button)
    │   ├── PhotoGallery.tsx      # Horizontal strip + lightbox
    │   ├── AISummaryCard.tsx     # AI summary with preference chips + match score + profile auto-fill
    │   ├── VisitRating.tsx       # 1–10 visit rating widget
    │   ├── MenuButton.tsx        # Floating button → source links
    │   ├── MapView.tsx           # Google Maps view (lazy-loaded)
    │   ├── CategoryRow.tsx       # Category filter row (solidActive colors)
    │   └── SubcategoryChips.tsx
    └── lib/
        ├── api.ts                # Axios instance + all API helpers + types
        ├── providers.tsx         # React Query provider
        └── categories.ts         # Category/subcategory definitions + solidActive colors
```

---

## Database Tables

| Table | Purpose |
|---|---|
| `places` | Core restaurant data (name, slug, address, city, lat/lng, cuisine[], photos[], website, hours JSON) |
| `data_sources` | External review sources linked to a place (Google, Yelp, article, Tabit, etc.) |
| `users` | Auth users — email, username, bcrypt password, points, tier, cuisine_preferences[], dietary_restrictions[], price_preference |
| `recommendations` | User-submitted text recommendations for a place |
| `votes` | Up/down votes on recommendations |
| `points_transactions` | Points ledger |
| `place_ratings` | 1–10 visit scores (one per user per place, upserted) |
| `user_visits` | Visit log per user per place |
| `menu_items` | Structured menu items (name, price_ils, category, source='ai') populated by menu_structurer worker |
| `saved_places` | User wishlist/favorites — user_id, place_id, list_type ('wishlist'|'favorite') |

---

## Key API Endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/auth/register` | Returns JWT |
| `POST` | `/auth/login` | Returns JWT |
| `GET` | `/places` | Search: `?q=`, `?city=`, `?cuisine=`, `?price_range=`, `?nlp=true`, `?open_now=true`, `?lat=`, `?lng=`, `?radius_km=`, `?sort=trending|hidden_gems|new` |
| `GET` | `/places/smart` | NLP smart search: `?q=`, `?city=` → `{exact, similar, parsed}` |
| `GET` | `/places/{slug}` | Detail with sources |
| `GET` | `/places/{slug}/menu` | Menu items |
| `GET` | `/recommendations/place/{id}` | |
| `POST` | `/recommendations` | Requires auth |
| `POST` | `/recommendations/{id}/vote` | `?value=1` or `-1` |
| `POST` | `/ratings` | Upsert 1–10 score, requires auth |
| `GET` | `/ratings/place/{id}` | `{avg_score, count, user_score}` |
| `POST` | `/ai/summarize` | Groq summary + match score |
| `GET` | `/users/me` | Requires auth — includes cuisine_preferences, dietary_restrictions, price_preference |
| `PATCH` | `/users/me/preferences` | Update taste profile, requires auth |
| `POST` | `/saved` | Save a place, requires auth: `{place_id, list_type}` |
| `DELETE` | `/saved/{place_id}` | Unsave, requires auth, `?list_type=` |
| `GET` | `/saved` | List saved place IDs for current user |
| `GET` | `/saved/places` | List saved places with full place data, `?list_type=` |

---

## Search Architecture

Three layers, each faster and less capable than the previous:

### 1. Fast SQL (while typing, debounced 400ms, `nlp=false`)
- Runs `_local_parse_query(q)` to extract city + dish without any API call
- Applies extracted city as a proper SQL filter, searches food term with ILIKE
- No external calls, instant response

### 2. Smart Search (on button click, `GET /places/smart`)
- Calls `nlp_parse_query(q)`:
  - If Groq available: full NLP → `{city, cuisine, dish, price_min_ils, price_max_ils}`
  - If Groq rate-limited (429): tries local ML model (`app/ml/inference.py`) → falls back to `_local_parse_query()`
- Location-first cascade (city is a hard constraint — never escaped):
  1. city + dish + price → exact
  2. city + dish (relax price) → exact/similar
  3. city + cuisine + price → similar
  4. city + cuisine → similar
  5. city only (top rated) → similar fill
  6. No city only: global food search (last resort)

### 3. Local Python Parser (`_local_parse_query` in services/places.py)
- Matches city names against hardcoded list of ~35 Israeli cities
- Strips "ב" prepositional prefix ("במודיעין" → city="מודיעין", dish remainder)
- Extracts price keywords ("זול", "עד 100 שקל", etc.)
- Zero-cost, ~0ms, used for both fast typing and Groq fallback

### Discovery Sort Modes (`?sort=`)
- `trending` — places with most ratings in last 14 days, fills with top-rated
- `hidden_gems` — aggregated_score ≥ 4.3 AND few data sources (≤ 2)
- `new` — sorted by `created_at DESC`

---

## ML Pipeline (training planned, not yet trained)

**Goal:** Replace Groq NLP with a local fine-tuned model for zero-latency, zero-cost, no-rate-limit query parsing.

**Files:** `backend/app/ml/`

```bash
# Step 1 — Generate synthetic training data
poetry run python -m app.ml.data_generator --count 15000

# Step 2 — Train (merges synthetic + real Groq-answered queries automatically)
# Requires: pip install transformers datasets torch sentencepiece
poetry run python -m app.ml.train \
    --train data/train.jsonl \
    --eval  data/eval.jsonl  \
    --real  data/real_queries.jsonl \
    --out   models/query-parser \
    --epochs 5

# Step 3 — Evaluate
poetry run python -m app.ml.evaluate --eval data/eval.jsonl
poetry run python -m app.ml.evaluate --query "סושי במודיעין"
```

**Model:** `google/mt5-small` (300MB, multilingual T5).  
**Task:** Text-to-JSON — `"parse restaurant query: סושי במודיעין"` → `{"city":"מודיעין","cuisine":"יפני","dish":"סושי",...}`  
**Inference:** `app/ml/inference.py` — lazy-loads the model on first use, falls back gracefully if `models/query-parser/` doesn't exist.  
**Integration:** `nlp_parse_query()` in `services/places.py` tries the local model before falling back to `_local_parse_query()`.

---

## Implemented Features

1. **~694 restaurants** across Israel with real Google Places photos and website URLs
2. **Menu data** — structured menu items from Google Places excerpts via Groq (worker: `menu_structurer.py`)
3. **Smart Hebrew search** — NLP parses queries like "פסטה בתל אביב" or "סושי זול במודיעין"
4. **Fast live search** — debounced, uses local Python parser for city detection (no API)
5. **Location-first search** — city is always a hard constraint; never escapes to other cities
6. **Open Now filter** — "פתוח עכשיו" toggle using Google's regularOpeningHours JSON; open/closed badge on every card
7. **Near Me search** — GPS button; sorts by Haversine distance; distance badge on cards
8. **Saved places** — ❤️ heart button on cards; wishlist + favorites; profile page tabs
9. **Discovery home page** — "חם עכשיו", "פנינים נסתרות", "חדש ב-Reco" sections
10. **Taste profile** — cuisine preferences, dietary restrictions, price preference saved on user; AI Summary Card auto-loads from profile
11. **Visit ratings (1–10)** — colored buttons, community average, user's own score highlighted
12. **Review helpfulness** — voting on community recommendations
13. **Website links** — fetched from Google Places
14. **Navigation** — Waze + Google Maps deep-links using lat/lng
15. **AI Summary Card** — Groq generates Hebrew summary + match score
16. **Photo gallery** — horizontal strip with lightbox
17. **Category + subcategory filters** — solid-color active state (per-category colors)
18. **Map view** — Google Maps with restaurant pins
19. **Points system** — users earn points for recommendations
20. **Auth** — register/login with JWT

---

## Workers (run manually from `/backend`)

```bash
# Seed restaurants
poetry run python -m app.workers.seed

# Fetch Google Places photos + website URLs
poetry run python -m app.workers.google_places_photos
poetry run python -m app.workers.google_places_photos --slug romano

# Build menu items from Google excerpts (long-running, ~675 restaurants)
poetry run python -u -m app.workers.menu_structurer --all

# Find and store direct menu URLs (website crawl + Wolt/ontopo promotion)
poetry run python -m app.workers.menu_link_finder           # all places
poetry run python -m app.workers.menu_link_finder romano    # single slug
poetry run python -m app.workers.menu_link_finder --redo    # overwrite existing

# Scrape images from restaurant websites
poetry run python -m app.workers.image_scraper
```

**Google Places API note:** The key has an HTTP referrer restriction. All requests from backend workers must include the header `Referer: http://localhost:3000`. Uses the **New Places API** (`places.googleapis.com/v1/places:searchText`).

---

## Auth Flow

- JWT stored in `localStorage` under key `"token"`
- Axios interceptor in `lib/api.ts` attaches it as `Authorization: Bearer <token>`
- After login/register, `window.location.href = "/"` forces a full page reload so `Navbar` re-reads localStorage
- CORS allows `localhost:3000` and `localhost:3001`

---

## Known Quirks

- `GEMINI_API_KEY` in `.env` is actually a **Groq** key. Historical naming — don't change the env var name without updating code.
- The Google Maps API key has HTTP referrer restrictions — backend scripts must send `Referer: http://localhost:3000`.
- `pydantic-settings` does NOT populate `os.environ` — always use `settings.field_name`, never `os.getenv()`.
- Alembic autogenerate only picks up models imported in `backend/app/models/__init__.py` — add new models there.
- Alembic `env.py` has an `OUR_TABLES` allowlist — add new table names there too or autogenerate will ignore them.
- Next.js 16: `useSearchParams()` requires a `<Suspense>` boundary in the parent component.
- Groq rate limits (free tier): ~1000 req/11h. The `menu_structurer` background job consumes quota — smart search has a 429 fallback that uses the local parser + local ML model so search always works even when rate-limited.
- `_local_parse_query()` in `services/places.py` is the zero-cost Hebrew city/price extractor. It's used for: fast SQL search (while typing), Groq 429 fallback, and as a last resort after local ML model.
- The local ML model at `backend/models/query-parser/` doesn't exist yet — needs to be trained. Until then the code silently skips it and uses `_local_parse_query()`.
