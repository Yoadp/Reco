# Reco — Claude Code Guide

Hebrew restaurant recommendation app for Tel Aviv. Full-stack: FastAPI backend + Next.js frontend.

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
│   │   │   ├── user.py          # User model
│   │   │   ├── recommendation.py
│   │   │   ├── rating.py        # PlaceRating (1–10 visit scores)
│   │   │   └── __init__.py      # imports all models for Alembic
│   │   ├── api/
│   │   │   ├── auth.py          # POST /auth/register, POST /auth/login
│   │   │   ├── places.py        # GET /places, GET /places/{slug}
│   │   │   ├── recommendations.py
│   │   │   ├── ratings.py       # POST /ratings, GET /ratings/place/{id}
│   │   │   ├── users.py         # GET /users/me
│   │   │   ├── ai.py            # POST /ai/summarize (Groq)
│   │   │   └── deps.py          # get_current_user, optional bearer
│   │   ├── services/
│   │   │   └── places.py        # search_places(), nlp_parse_query(), get_place_by_slug()
│   │   └── workers/
│   │       ├── seed.py                  # Seeds 30 restaurants
│   │       ├── google_places_photos.py  # Fetches real photos + websiteUri from Places API
│   │       ├── image_scraper.py         # Playwright-based image scraper
│   │       ├── google_ingestion.py
│   │       ├── article_scraper.py
│   │       └── menu_scraper.py
│   ├── alembic/                 # DB migrations
│   └── pyproject.toml
└── frontend/
    ├── app/
    │   ├── layout.tsx            # Root layout: Navbar + Providers
    │   ├── page.tsx              # Home page with hero search
    │   ├── restaurants/page.tsx  # Restaurant list + search + map
    │   ├── places/[slug]/page.tsx # Restaurant detail page
    │   ├── login/page.tsx
    │   ├── register/page.tsx
    │   └── profile/page.tsx
    ├── components/
    │   ├── Navbar.tsx            # Auth state from localStorage on mount
    │   ├── PlaceGrid.tsx         # Restaurant card grid
    │   ├── PhotoGallery.tsx      # Horizontal strip + lightbox
    │   ├── AISummaryCard.tsx     # AI summary with preference chips + match score
    │   ├── VisitRating.tsx       # 1–10 visit rating widget
    │   ├── MenuButton.tsx        # Floating button → source links
    │   ├── MapView.tsx           # Google Maps view (lazy-loaded)
    │   ├── CategoryRow.tsx       # Category filter row
    │   └── SubcategoryChips.tsx
    └── lib/
        ├── api.ts                # Axios instance + all API helpers + types
        ├── providers.tsx         # React Query provider
        └── categories.ts         # Category/subcategory definitions
```

---

## Database Tables

| Table | Purpose |
|---|---|
| `places` | Core restaurant data (name, slug, address, city, lat/lng, cuisine[], photos[], website) |
| `data_sources` | External review sources linked to a place (Google, Yelp, article, Tabit, etc.) |
| `users` | Auth users (email, username, bcrypt password, points, tier) |
| `recommendations` | User-submitted text recommendations for a place |
| `votes` | Up/down votes on recommendations |
| `points_transactions` | Points ledger |
| `place_ratings` | 1–10 visit scores (one per user per place, upserted) |

---

## Key API Endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/auth/register` | Returns JWT |
| `POST` | `/auth/login` | Returns JWT |
| `GET` | `/places` | Search: `?q=`, `?city=`, `?cuisine=`, `?price_range=`, `?nlp=true` |
| `GET` | `/places/{slug}` | Detail with sources |
| `GET` | `/recommendations/place/{id}` | |
| `POST` | `/recommendations` | Requires auth |
| `POST` | `/recommendations/{id}/vote` | `?value=1` or `-1` |
| `POST` | `/ratings` | Upsert 1–10 score, requires auth |
| `GET` | `/ratings/place/{id}` | `{avg_score, count, user_score}` |
| `POST` | `/ai/summarize` | Groq summary + match score |
| `GET` | `/users/me` | Requires auth |

---

## Search Architecture

The `GET /places` endpoint supports two search modes controlled by `?nlp=true`:

**Fast SQL mode** (typing / debounce, default):
- Plain `ILIKE` on `name`, `address`, and `array_to_string(cuisine)`
- No external calls, instant response

**NLP mode** (`?nlp=true`, triggered by clicking "חיפוש" or Enter):
- Sends the query to Groq which returns `{city, cuisine, price, term}` as JSON
- Results are cached in-memory (up to 200 entries, keyed on normalized query)
- Falls back to plain ILIKE if Groq fails
- City filter checks both `city` column and `address` column (handles "יפו" inside Tel Aviv addresses)

The frontend debounce is 400ms and sets `nlp=false`. Form submit sets `nlp=true`.

---

## Auth Flow

- JWT stored in `localStorage` under key `"token"`
- Axios interceptor in `lib/api.ts` attaches it as `Authorization: Bearer <token>`
- After login/register, `window.location.href = "/"` is used (not `router.push`) to force a full page reload so `Navbar` re-reads localStorage
- CORS allows `localhost:3000` and `localhost:3001`

---

## Workers (run manually from `/backend`)

```bash
# Seed 30 restaurants
poetry run python -m app.workers.seed

# Fetch real Google Places photos + website URLs for all restaurants
poetry run python -m app.workers.google_places_photos

# Fetch photos for a specific restaurant by slug
poetry run python -m app.workers.google_places_photos --slug romano

# Scrape images from a restaurant's own website
poetry run python -m app.workers.image_scraper
```

**Google Places API note:** The key has an HTTP referrer restriction. All requests from backend workers must include the header `Referer: http://localhost:3000`. Uses the **New Places API** (`places.googleapis.com/v1/places:searchText`), not the legacy endpoint.

---

## Implemented Features

1. **30 restaurants** seeded with real Google Places photos (4 per restaurant) and website URLs
2. **Smart Hebrew search** — NLP via Groq parses freeform queries like "פסטה בתל אביב" or "מקום זול"
3. **Fast live search** — debounced SQL ILIKE while typing (no Groq)
4. **Visit ratings (1–10)** — colored buttons, community average, user's own score highlighted
5. **Review helpfulness** — "👍 עזר לי / 👎 לא עזר" voting on community recommendations
6. **Website links** — fetched from Google Places, shown in detail header
7. **Navigation buttons** — Waze + Google Maps deep-links using lat/lng
8. **AI Summary Card** — Groq generates Hebrew summary + match score based on user preferences
9. **Photo gallery** — horizontal strip with lightbox
10. **Floating menu button** — links to Tabit/Ontopo/Wolt ordering sources
11. **Category + subcategory filters** — on the restaurants list page
12. **Map view** — Google Maps with restaurant pins (toggle grid/map)
13. **Points system** — users earn points for recommendations
14. **Auth** — register/login with JWT, Navbar updates on page load

---

## Known Quirks

- `GEMINI_API_KEY` in `.env` is actually a **Groq** key. Historical naming — don't change the env var name without updating code.
- The Google Maps API key has HTTP referrer restrictions — backend scripts must send `Referer: http://localhost:3000`.
- `pydantic-settings` does NOT populate `os.environ` — always use `settings.field_name`, never `os.getenv()`.
- Alembic autogenerate only picks up models imported in `backend/app/models/__init__.py` — add new models there.
- Next.js 16: `useSearchParams()` requires a `<Suspense>` boundary in the parent component.
