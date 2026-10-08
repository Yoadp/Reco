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
CALL_DELAY = 3.0
BATCH_SIZE = 3  # restaurants per Groq call


PRICE_RANGE_ESTIMATE = {
    1: "20-50",
    2: "50-100",
    3: "100-180",
    4: "180-300",
}


def _build_batch_prompt(batch: list[dict]) -> str:
    """Build a single prompt for multiple restaurants."""
    lines = []
    for i, r in enumerate(batch):
        price_hint = PRICE_RANGE_ESTIMATE.get(r["price_range"] or 2, "50-120")
        cuisine_str = ", ".join(r["cuisine"] or [])
        context_parts = []
        if r["menu_excerpt"]:
            context_parts.append(f"תפריט: {r['menu_excerpt'][:500]}")
        if r["review_excerpts"]:
            combined = " | ".join(r["review_excerpts"][:3])
            context_parts.append(f"ביקורות: {combined[:500]}")
        context = " ".join(context_parts)
        lines.append(f'{i+1}. "{r["name"]}" | מטבח: {cuisine_str} | טווח מחיר: {price_hint}₪\n   {context}')

    restaurants_block = "\n\n".join(lines)
    return f"""אתה מנתח ביקורות ותפריטים של מסעדות ישראליות.

עבור כל מסעדה:
1. **חלץ שמות מנות ספציפיות** שמוזכרות בטקסט הביקורות/תפריט (אם קיים). אל תשתמש בשמות גנריים כמו "עיקרית" או "מנה ראשונה" — רק שמות אמיתיים.
2. אם הטקסט לא מזכיר מנות ספציפיות, **המצא מנות ריאליסטיות** אופייניות למטבח ולסגנון (ספציפיות, לא גנריות — כגון "פילה סלמון בשמן לימון" ולא סתם "דגים").
3. לכל מנה הוסף `description` קצר (3-6 מילים) המתאר את הטעם/סגנון שלה.
4. בחר 4-6 מנות שמייצגות **הכי טוב** את אופי המסעדה.

{restaurants_block}

החזר אובייקט JSON בלבד ללא markdown, בפורמט זה בדיוק:
{{"1": [{{"name": "פסטה ברוטב עגבניות שרי", "price_ils": 68, "category": "פסטות", "description": "קלאסי ועדין, עם בזיליקום טרי"}}], "2": [...], ...}}

קטגוריות חוקיות: "ראשונות", "סלטים", "מרקים", "פיצות", "פסטות", "סושי", "עיקריות", "גריל", "צדדיות", "קינוחים", "שתייה"
"""


async def extract_menu_items_batch(batch: list[dict]) -> dict[int, list[dict]]:
    """Send one Groq call for a batch of restaurants. Returns {index: [items]}."""
    prompt = _build_batch_prompt(batch)

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {settings.gemini_api_key}"},
                    json={
                        "model": GROQ_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 1600,
                        "temperature": 0.2,
                    },
                )
            if resp.status_code == 429:
                wait = 60 + attempt * 30
                print(f"  429 rate limit, waiting {wait}s...")
                await asyncio.sleep(wait)
                continue
            if resp.status_code >= 400:
                print(f"  Groq HTTP {resp.status_code}, skipping batch")
                return {}
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            start = content.find("{")
            end = content.rfind("}") + 1
            if start == -1 or end == 0:
                return {}
            parsed = json.loads(content[start:end])
            # Normalise keys to int
            return {int(k): v for k, v in parsed.items() if isinstance(v, list)}
        except Exception as e:
            print(f"  Groq error (attempt {attempt+1}): {e}")
            if attempt < 2:
                await asyncio.sleep(5)
    return {}


async def _load_excerpts(place, db) -> dict | None:
    """Load menu + review excerpts for one place. Returns None if nothing available."""
    menu_result = await db.execute(
        select(DataSource.excerpt)
        .where(DataSource.place_id == place.id)
        .where(DataSource.source_type == "menu")
        .where(DataSource.excerpt != None)
    )
    menu_excerpts = [r[0] for r in menu_result.all() if r[0]]

    review_result = await db.execute(
        select(DataSource.excerpt)
        .where(DataSource.place_id == place.id)
        .where(DataSource.source_type == "google_places")
        .where(DataSource.excerpt != None)
        .limit(3)
    )
    review_excerpts = [r[0] for r in review_result.all() if r[0]]

    if not menu_excerpts and not review_excerpts:
        return None

    return {
        "place": place,
        "name": place.name,
        "cuisine": place.cuisine or [],
        "price_range": place.price_range,
        "menu_excerpt": menu_excerpts[0] if menu_excerpts else None,
        "review_excerpts": review_excerpts,
    }


async def _save_items(place, items: list[dict], db) -> int:
    if not items:
        return 0
    await db.execute(
        delete(MenuItem)
        .where(MenuItem.place_id == place.id)
        .where(MenuItem.source == "ai")
    )
    count = 0
    for item in items:
        name = str(item.get("name", "")).strip()
        if not name or len(name) < 2:
            continue
        price = item.get("price_ils")
        try:
            price = int(price) if price else None
        except (TypeError, ValueError):
            price = None
        desc = str(item.get("description", "")).strip() or None
        db.add(MenuItem(
            place_id=place.id,
            name=name,
            price_ils=price,
            description=desc,
            category=item.get("category"),
            source="ai",
        ))
        count += 1
    await db.commit()
    return count


async def process_places(places: list, db, label: str) -> int:
    total_items = 0
    total = len(places)

    # Load all excerpts first, skip places with no data
    rich = []
    for place in places:
        data = await _load_excerpts(place, db)
        if data:
            rich.append(data)

    print(f"{len(rich)}/{total} places have text data to process")

    # Process in batches of BATCH_SIZE
    for batch_start in range(0, len(rich), BATCH_SIZE):
        batch = rich[batch_start: batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        total_batches = (len(rich) + BATCH_SIZE - 1) // BATCH_SIZE

        names = ", ".join(r["name"] for r in batch)
        print(f"\n[batch {batch_num}/{total_batches}] {names}")

        results = await extract_menu_items_batch(batch)

        # If batch returned nothing, fall back to one-by-one
        if not results:
            print(f"  batch failed — retrying individually")
            for data in batch:
                single = await extract_menu_items_batch([data])
                items = single.get(1, [])
                count = await _save_items(data["place"], items, db)
                total_items += count
                print(f"  {data['name']}: {count} items")
                await asyncio.sleep(CALL_DELAY)
            continue

        for i, data in enumerate(batch, 1):
            items = results.get(i, [])
            count = await _save_items(data["place"], items, db)
            total_items += count
            print(f"  {data['name']}: {count} items")

        await asyncio.sleep(CALL_DELAY)

    return total_items


async def main(all_places: bool = False, redo: bool = False, slugs: list[str] | None = None):
    async with AsyncSessionLocal() as db:
        if slugs:
            result = await db.execute(
                select(Place).where(Place.slug.in_(slugs)).order_by(Place.name)
            )
            places = list(result.scalars().all())
            print(f"Processing {len(places)} specific place(s)...")
        elif all_places:
            has_excerpt = (
                select(DataSource.place_id)
                .where(DataSource.source_type == "google_places")
                .where(DataSource.excerpt != None)
                .distinct()
            )
            if redo:
                # Re-process everything, overwriting existing AI items
                stmt = select(Place).where(Place.id.in_(has_excerpt)).order_by(Place.name)
                print("--redo: overwriting existing menu items for all places with excerpts...")
            else:
                already_done = select(MenuItem.place_id).distinct()
                stmt = (
                    select(Place)
                    .where(Place.id.not_in(already_done))
                    .where(Place.id.in_(has_excerpt))
                    .order_by(Place.name)
                )
            result = await db.execute(stmt)
            places = list(result.scalars().all())
            print(f"Processing {len(places)} places (using google excerpts)...")
        else:
            menu_place_ids_q = (
                select(DataSource.place_id)
                .where(DataSource.source_type == "menu")
                .distinct()
            )
            if not redo:
                already_done = select(MenuItem.place_id).distinct()
                menu_place_ids_q = menu_place_ids_q.where(
                    DataSource.place_id.not_in(already_done)
                )
            result = await db.execute(
                select(Place).where(Place.id.in_(menu_place_ids_q)).order_by(Place.name)
            )
            places = list(result.scalars().all())
            print(f"Processing {len(places)} places with menu sources...")

        total = await process_places(places, db, label="all" if all_places else "menu")
        print(f"\nDone. Total menu items stored: {total}")


if __name__ == "__main__":
    args = sys.argv[1:]
    run_all = "--all" in args
    redo = "--redo" in args
    slugs = [a for a in args if not a.startswith("--")] or None
    asyncio.run(main(all_places=run_all, redo=redo, slugs=slugs))
