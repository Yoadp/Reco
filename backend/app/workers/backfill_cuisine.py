"""
Backfill cuisine array for all places that have Google raw_json but no cuisine set.

Usage:
    poetry run python -m app.workers.backfill_cuisine
"""

import asyncio
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.place import Place, DataSource

# Maps Google's Hebrew primaryTypeDisplayName → our cuisine tags
TYPE_TO_CUISINE: dict[str, list[str]] = {
    # Cafe / breakfast
    "בית קפה":                      ["קפה"],
    "מאפייה":                        ["מאפים", "קפה"],
    "מסעדת ארוחות בוקר":             ["ארוחת בוקר", "קפה"],
    "מזנון מהיר":                    ["קפה"],
    # Bar / drinks
    "בר":                            ["בר"],
    "באר-מסעדה":                     ["בר"],
    "בר קוקטיילים":                  ["בר", "קוקטיילים"],
    "בר יינות":                      ["בר", "יין"],
    "פאב":                           ["פאב", "בר"],
    "פאב אירי":                      ["פאב", "בר"],
    "בר נרגילה":                     ["בר"],
    "בר ספורט":                      ["בר"],
    "חנות יין ואלכוהול":             ["יין"],
    "מסבאה":                         ["בר"],
    # Japanese / sushi
    "מסעדת סושי":                    ["סושי", "יפני"],
    "מסעדה יפנית":                   ["יפני"],
    # Asian
    "מסעדה אסייתית":                  ["אסייתי"],
    "מסעדה סינית":                   ["סיני", "אסייתי"],
    "מסעדה תאילנדית":                ["תאילנדי", "אסייתי"],
    "מסעדה פיוז'ן אסייתית":          ["פיוז'ן אסייתי", "אסייתי"],
    # Italian / pizza
    "מסעדה איטלקית":                 ["איטלקי"],
    "פיצרייה":                       ["פיצה", "איטלקי"],
    "פיצריה עם שירות משלוחים":       ["פיצה", "איטלקי"],
    # Burger / fast food
    "מסעדת המבורגרים":               ["המבורגר"],
    "מסעדת מזון מהיר":               ["מזון מהיר"],
    "אזור מזון מהיר":                ["מזון מהיר"],
    # Middle Eastern / Israeli
    "מסעדה מזרח תיכונית":            ["מזרח תיכוני"],
    "מסעדת שווארמה":                 ["שווארמה", "מזרח תיכוני"],
    "מסעדת פלאפל":                   ["פלאפל", "מזרח תיכוני"],
    "מסעדה מרוקנית":                 ["מרוקאי", "מזרח תיכוני"],
    "מסעדה לבנונית":                 ["לבנוני", "מזרח תיכוני"],
    "מסעדה ישראלית":                 ["ישראלי"],
    # Meat / grill
    "מסעדת גריל":                    ["גריל", "בשר"],
    "סטקייה":                        ["סטייק", "בשר"],
    "מסעדה ארגנטינאית":              ["ארגנטינאי", "בשר"],
    "מסעדה דרום אמריקאית":           ["דרום אמריקאי", "בשר"],
    # Mediterranean / seafood
    "מסעדה ים-תיכונית":              ["ים תיכוני"],
    "מסעדת מאכלי ים":                ["פירות ים", "ים תיכוני"],
    # European / French
    "מסעדה צרפתית":                  ["צרפתי", "אירופאי"],
    "ביסטרו":                        ["ביסטרו", "צרפתי"],
    "מסעדה יוונית":                  ["יווני", "אירופאי"],
    "מסעדה מזרח אירופאית":           ["אירופאי"],
    "מסעדה אירופאית":                ["אירופאי"],
    "מסעדה צ'כית":                   ["אירופאי"],
    # Gourmet / fine dining
    "מסעדה גורמה":                   ["גורמה"],
    "מסעדת קינוחים":                 ["קינוחים"],
    # Desserts
    # Misc
    "מסעדה עם שירות משלוחים":        ["ישראלי"],
    "מסעדה":                         ["ישראלי"],   # generic fallback
}


def map_type_to_cuisine(type_text: str | None) -> list[str] | None:
    if not type_text:
        return None
    return TYPE_TO_CUISINE.get(type_text.strip())


async def backfill():
    async with AsyncSessionLocal() as db:
        # Load all places with no cuisine that have google data_source raw_json
        result = await db.execute(
            select(Place, DataSource)
            .join(DataSource, DataSource.place_id == Place.id)
            .where(
                DataSource.source_type == "google_places",
                DataSource.raw_json.isnot(None),
            )
        )
        rows = result.fetchall()

        updated = 0
        skipped = 0
        for place, source in rows:
            if place.cuisine:
                skipped += 1
                continue

            type_text = None
            raw = source.raw_json
            if isinstance(raw, dict):
                type_display = raw.get("primaryTypeDisplayName", {})
                if isinstance(type_display, dict):
                    type_text = type_display.get("text")

            cuisine = map_type_to_cuisine(type_text)
            if cuisine:
                place.cuisine = cuisine
                updated += 1
            else:
                # Unknown type — store generic
                place.cuisine = ["ישראלי"]
                updated += 1

        await db.commit()
        print(f"Updated {updated} places (skipped {skipped} that already had cuisine)")


if __name__ == "__main__":
    asyncio.run(backfill())
