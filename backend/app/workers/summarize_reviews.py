"""
Use Groq to translate/summarize existing English Google review excerpts into Hebrew.

Only processes `google_places` DataSource rows whose excerpt is in English.
Skips rows already in Hebrew (idempotent — safe to re-run).
Respects Groq's 30 RPM limit with 2.2s between requests + backoff on 429.

Usage:
    poetry run python -m app.workers.summarize_reviews
    poetry run python -m app.workers.summarize_reviews --force   # reprocess everything
"""

import asyncio
import sys
import io
import httpx
from sqlalchemy import select

# Force line-buffered stdout even when not connected to a TTY
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, line_buffering=True)

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.place import DataSource

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.8-27b"

FORCE = "--force" in sys.argv
CALL_DELAY = 2.2   # seconds between calls; keeps us under 30 RPM


def _is_hebrew(text: str) -> bool:
    hebrew_count = sum(1 for c in text if "א" <= c <= "ת")
    return hebrew_count > len(text) * 0.2


async def summarize(client: httpx.AsyncClient, text: str, retries: int = 2) -> str | None:
    if not text.strip() or len(text) < 20:
        return None
    prompt = (
        "אתה כותב סיכומי ביקורות מסעדות. "
        "בהינתן הטקסט הבא (ביקורות של גולשים), כתוב סיכום תמציתי ב-2 משפטים בעברית בלבד. "
        "אל תציין שם מקור. אל תשתמש בניקוד. רק עברית.\n\n"
        f"{text[:1500]}"
    )
    for attempt in range(retries + 1):
        try:
            r = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.gemini_api_key}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150,
                    "temperature": 0.3,
                },
                timeout=25,
            )
            if r.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"    ⏳ 429 rate limit — waiting {wait}s…")
                await asyncio.sleep(wait)
                continue
            r.raise_for_status()
            result = r.json()["choices"][0]["message"]["content"].strip()
            return result if result else None
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < retries:
                wait = 60 * (attempt + 1)
                print(f"    ⏳ 429 rate limit — waiting {wait}s…")
                await asyncio.sleep(wait)
            else:
                print(f"    Groq HTTP error: {e.response.status_code}")
                return None
        except Exception as e:
            print(f"    Groq error: {e}")
            return None
    return None


async def run():
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY not set")
        return

    async with AsyncSessionLocal() as db:
        # Only process google_places sources with non-null excerpts
        result = await db.execute(
            select(DataSource).where(
                DataSource.source_type == "google_places",
                DataSource.excerpt.isnot(None),
            )
        )
        all_rows = result.scalars().all()

    if FORCE:
        rows = list(all_rows)
    else:
        rows = [r for r in all_rows if not _is_hebrew(r.excerpt or "")]

    print(f"Summarizing {len(rows)} Google reviews in Hebrew{'  (FORCE)' if FORCE else ''}…")
    if not rows:
        print("Nothing to do.")
        return

    ok = fail = 0
    async with httpx.AsyncClient() as client:
        for i, row in enumerate(rows):
            summary = await summarize(client, row.excerpt)
            if summary:
                async with AsyncSessionLocal() as db:
                    ds = await db.get(DataSource, row.id)
                    if ds:
                        ds.excerpt = summary
                    await db.commit()
                ok += 1
                status = "✓"
            else:
                fail += 1
                status = "—"

            place_hint = str(row.place_id)[:8]
            print(f"  [{i+1}/{len(rows)}] {place_hint} {status}")

            await asyncio.sleep(CALL_DELAY)

    print(f"\nDone. ✓ {ok} updated, — {fail} skipped/failed.")


if __name__ == "__main__":
    asyncio.run(run())
