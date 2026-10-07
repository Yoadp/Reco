"""
Menu Structurer — converts unstructured menu excerpts + review text into
structured menu_items rows using Groq.

Run: poetry run python -m app.workers.menu_structurer          # only places with menu sources
     poetry run python -m app.workers.menu_structurer --all    # all places using google excerpts
"""
import asyncio
import json
import sys
import httpx
from sqlalchemy import select, delete

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.place import Place, DataSource
from app.models.menu_item import MenuItem

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.8-27b"
CALL_DELAY = 5.0


PRICE_RANGE_ESTIMATE = {
    1: "20-50",
    2: "50-100",
    3: "100-180",
    4: "180-300",
}


async def extract_menu_items(
    place_name: str,
    cuisine: list[str],
    price_range: int | None,
    menu_excerpt: str | None,
    review_excerpts: list[str],
) -> list[dict]:
    """Ask Groq to extract structured menu items from available text."""
    price_hint = PRICE_RANGE_ESTIMATE.get(price_range or 2, "50-120")
    cuisine_str = ", ".join(cuisine or [])

    context_parts = []
    if menu_excerpt:
        context_parts.append(f"תפריט: {menu_excerpt}")
    if review_excerpts:
        combined = " | ".join(review_excerpts[:5])
        context_parts.append(f"מביקורות גולשים: {combined[:600]}")

    if not context_parts:
        return []

    context = "\n".join(context_parts)

    prompt = f"""אתה מנתח מידע על מסעדות ישראליות ויוצר רשימת מנות.

מסעדה: {place_name}
מטבח: {cuisine_str}
טווח מחיר משוער לפריט: {price_hint} ₪

מידע על המסעדה:
{context}

משימה: צור רשימת 3-5 מנות אופייניות למסעדה זו.
- אם מנות מוזכרות בטקסט — השתמש בהן.
- אם לא — הסק 3-5 מנות מייצגות לפי סוג המטבח ושם המסעדה.

עבור כל מנה החזר אובייקט JSON עם:
- name: שם המנה בעברית
- price_ils: מחיר משוער בשקלים (מספר שלם)
- category: אחת מ: "ראשונות", "עיקריות", "צדדיות", "קינוחים", "שתייה", "פיצות", "פסטות", "סושי"

החזר מערך JSON בלבד, ללא markdown, ללא טקסט נוסף:
[{{"name": "ספגטי קרבונרה", "price_ils": 78, "category": "פסטות"}}]
"""

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {settings.gemini_api_key}"},
                    json={
                        "model": GROQ_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 400,
                        "temperature": 0.2,
                    },
                )
            if resp.status_code == 429:
                wait = 60 + attempt * 30
                print(f"  429 rate limit, waiting {wait}s...")
                await asyncio.sleep(wait)
                continue
            if resp.status_code >= 400:
                print(f"  Groq HTTP {resp.status_code}, skipping")
                return []
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            # Strip markdown code fences if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            # Find JSON array in the response
            start = content.find("[")
            end = content.rfind("]") + 1
            if start == -1 or end == 0:
                return []
            parsed = json.loads(content[start:end])
            if isinstance(parsed, list):
                return parsed
            return []
        except Exception as e:
            print(f"  Groq error (attempt {attempt+1}): {e}")
            if attempt < 2:
                await asyncio.sleep(5)
    return []


async def process_places(places: list, db, label: str) -> int:
    total_items = 0
    for idx, place in enumerate(places, 1):
        # Get menu excerpts (dedicated menu source, highest quality)
        menu_result = await db.execute(
            select(DataSource.excerpt)
            .where(DataSource.place_id == place.id)
            .where(DataSource.source_type == "menu")
            .where(DataSource.excerpt != None)
        )
        menu_excerpts = [r[0] for r in menu_result.all() if r[0]]

        # Get google review excerpts
        review_result = await db.execute(
            select(DataSource.excerpt)
            .where(DataSource.place_id == place.id)
            .where(DataSource.source_type == "google_places")
            .where(DataSource.excerpt != None)
            .limit(3)
        )
        review_excerpts = [r[0] for r in review_result.all() if r[0]]

        if not menu_excerpts and not review_excerpts:
            continue

        menu_text = menu_excerpts[0] if menu_excerpts else None

        progress = f"[{idx}/{len(places)}]"
        print(f"\n{progress} {place.name}:")
        if menu_text:
            print(f"  menu: {menu_text[:80]}")
        elif review_excerpts:
            print(f"  review: {review_excerpts[0][:80]}")

        items = await extract_menu_items(
            place_name=place.name,
            cuisine=place.cuisine or [],
            price_range=place.price_range,
            menu_excerpt=menu_text,
            review_excerpts=review_excerpts,
        )

        if not items:
            print(f"  → no items extracted")
            await asyncio.sleep(CALL_DELAY)
            continue

        # Clear existing AI menu items for this place (idempotent)
        await db.execute(
            delete(MenuItem)
            .where(MenuItem.place_id == place.id)
            .where(MenuItem.source == "ai")
        )

        for item in items:
            name = str(item.get("name", "")).strip()
            if not name or len(name) < 2:
                continue
            price = item.get("price_ils")
            try:
                price = int(price) if price else None
            except (TypeError, ValueError):
                price = None

            mi = MenuItem(
                place_id=place.id,
                name=name,
                price_ils=price,
                description=None,
                category=item.get("category"),
                source="ai",
            )
            db.add(mi)

        await db.commit()
        total_items += len(items)
        print(f"  → {len(items)} items: {[i.get('name','') for i in items[:4]]}")

        await asyncio.sleep(CALL_DELAY)

    return total_items


async def main(all_places: bool = False):
    async with AsyncSessionLocal() as db:
        if all_places:
            # Process ALL places that don't already have menu items, using google excerpts
            already_done = select(MenuItem.place_id).distinct()
            has_excerpt = (
                select(DataSource.place_id)
                .where(DataSource.source_type == "google_places")
                .where(DataSource.excerpt != None)
                .distinct()
            )
            result = await db.execute(
                select(Place)
                .where(Place.id.not_in(already_done))
                .where(Place.id.in_(has_excerpt))
                .order_by(Place.name)
            )
            places = list(result.scalars().all())
            print(f"Processing {len(places)} places without menu items (using google excerpts)...")
        else:
            # Only process places with dedicated menu sources
            menu_place_ids_q = (
                select(DataSource.place_id)
                .where(DataSource.source_type == "menu")
                .distinct()
            )
            result = await db.execute(
                select(Place)
                .where(Place.id.in_(menu_place_ids_q))
                .order_by(Place.name)
            )
            places = list(result.scalars().all())
            print(f"Processing {len(places)} places with menu sources...")

        total = await process_places(places, db, label="all" if all_places else "menu")
        print(f"\nDone. Total menu items stored: {total}")


if __name__ == "__main__":
    run_all = "--all" in sys.argv
    asyncio.run(main(all_places=run_all))
