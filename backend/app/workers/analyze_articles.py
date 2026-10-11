"""
Analyze article DataSources with Groq: generates a Hebrew AI summary and detects
whether the article is sponsored/promotional.

Adds:
  DataSource.ai_summary  — 1-sentence Hebrew opinion summary
  DataSource.is_sponsored — True=sponsored, False=genuine, None=uncertain

Usage:
  poetry run python -m app.workers.analyze_articles           # all articles missing ai_summary
  poetry run python -m app.workers.analyze_articles --redo    # re-analyze all
  poetry run python -m app.workers.analyze_articles --limit 50
"""

import asyncio
import argparse
import json
import re
import time
import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.place import Place, DataSource

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.8-27b"
CALL_DELAY = 2.5  # seconds between Groq calls (30 RPM limit)


def _build_prompt(place_name: str, city: str | None, excerpt: str) -> str:
    return f"""אתה מנתח ביקורות מסעדות ישראליות.

מסעדה: {place_name}{f", {city}" if city else ""}
קטע מהביקורת:
"{excerpt}"

בצע שתי משימות:

1. כתוב משפט אחד בעברית שמסכם את דעת הכותב (איכות האוכל, אווירה, שווי הכסף). היה ספציפי ולא גנרי.
2. האם המאמר ממומן/פרסומי? השב: "yes", "no", או "uncertain".
   סימני מאמר ממומן: רק שבחים ללא כל ביקורת, שפה שיווקית, תיאורים גנריים ללא חוויה אישית, טון PR.

החזר JSON בלבד, ללא markdown:
{{"summary": "...", "is_sponsored": "yes|no|uncertain"}}"""


async def analyze_one(
    client: httpx.AsyncClient,
    place_name: str,
    city: str | None,
    excerpt: str,
) -> tuple[str | None, bool | None]:
    """Returns (ai_summary, is_sponsored). is_sponsored is None for 'uncertain'."""
    prompt = _build_prompt(place_name, city, excerpt)
    for attempt in range(3):
        try:
            resp = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.gemini_api_key}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                    "temperature": 0.1,
                },
                timeout=15.0,
            )
            if resp.status_code == 429:
                wait = 60 + attempt * 30
                print(f"    429 rate limit, waiting {wait}s...")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            # Strip markdown fences if present
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)
            start, end = content.find("{"), content.rfind("}") + 1
            if start == -1 or end == 0:
                return None, None
            data = json.loads(content[start:end])
            summary = data.get("summary", "").strip() or None
            raw_sponsored = data.get("is_sponsored", "uncertain")
            is_sponsored = True if raw_sponsored == "yes" else (False if raw_sponsored == "no" else None)
            return summary, is_sponsored
        except Exception as e:
            if attempt == 2:
                print(f"    Groq error: {e}")
            await asyncio.sleep(3)
    return None, None


async def run(redo: bool = False, limit: int | None = None):
    async with AsyncSessionLocal() as db:
        stmt = (
            select(DataSource, Place)
            .join(Place, Place.id == DataSource.place_id)
            .where(DataSource.source_type == "article")
            .where(DataSource.excerpt.isnot(None))
        )
        if not redo:
            stmt = stmt.where(DataSource.ai_summary.is_(None))
        result = await db.execute(stmt)
        rows = result.all()

    if limit:
        rows = rows[:limit]

    print(f"Analyzing {len(rows)} article sources...")
    updated = 0

    async with httpx.AsyncClient() as client:
        for i, (source, place) in enumerate(rows, 1):
            print(f"[{i}/{len(rows)}] {place.name} — {source.source_name or 'article'}")
            summary, is_sponsored = await analyze_one(client, place.name, place.city, source.excerpt)
            if summary:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(DataSource).where(DataSource.id == source.id)
                    )
                    ds = result.scalar_one_or_none()
                    if ds:
                        ds.ai_summary = summary
                        ds.is_sponsored = is_sponsored
                        await db.commit()
                        updated += 1
                badge = (
                    "✓ עצמאי" if is_sponsored is False else
                    "★ ממומן" if is_sponsored is True else
                    "? לא ידוע"
                )
                print(f"  {badge} — {summary[:80]}")
            else:
                print("  ✗ לא הצלחנו לנתח")
            await asyncio.sleep(CALL_DELAY)

    print(f"\nסיום. עודכנו {updated} מקורות.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--redo", action="store_true", help="Re-analyze articles that already have ai_summary")
    parser.add_argument("--limit", type=int, help="Max articles to process")
    args = parser.parse_args()
    asyncio.run(run(redo=args.redo, limit=args.limit))
