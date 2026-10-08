"""
Synthetic training data generator for the Hebrew restaurant query parser.

Generates (input_query, output_json) pairs for fine-tuning.

Usage:
    poetry run python -m app.ml.data_generator --count 10000 --out data/train.jsonl
"""

import json
import random
import argparse
from pathlib import Path
from itertools import product

# ── Vocabulary ────────────────────────────────────────────────────────────────

CITIES = [
    "תל אביב", "יפו", "חיפה", "ירושלים", "באר שבע", "נתניה", "פתח תקווה",
    "ראשון לציון", "אשדוד", "חולון", "בני ברק", "רמת גן", "גבעתיים",
    "הרצליה", "רעננה", "כפר סבא", "הוד השרון", "מודיעין", "נס ציונה",
    "רחובות", "בת ים", "רמת השרון", "לוד", "רמלה", "אשקלון", "אילת",
    "עכו", "נהריה", "קריית גת", "קריית ביאליק", "קריית ים", "אור יהודה",
    "גבעת שמואל",
]

# (Hebrew dish/term, cuisine_category)
DISHES = [
    # Japanese
    ("סושי", "יפני"), ("ראמן", "יפני"), ("סשימי", "יפני"), ("טמפורה", "יפני"),
    ("אוניגירי", "יפני"), ("מאקי", "יפני"), ("אדמאמה", "יפני"), ("מיסו", "יפני"),
    # Italian
    ("פסטה", "איטלקי"), ("פיצה", "איטלקי"), ("ריזוטו", "איטלקי"), ("לזניה", "איטלקי"),
    ("גנוצ'י", "איטלקי"), ("טירמיסו", "איטלקי"), ("ברוסקטה", "איטלקי"), ("קרבונרה", "איטלקי"),
    # American
    ("המבורגר", "אמריקאי"), ("צ'יזבורגר", "אמריקאי"), ("כנפיים", "אמריקאי"),
    ("צ'יפס", "אמריקאי"), ("ברביקיו", "אמריקאי"), ("סנדוויץ'", "אמריקאי"),
    # Israeli
    ("חומוס", "ישראלי"), ("פלאפל", "ישראלי"), ("שקשוקה", "ישראלי"), ("סביח", "ישראלי"),
    ("סלט ישראלי", "ישראלי"), ("מלאווח", "ישראלי"), ("ג'חנון", "ישראלי"), ("פיתה", "ישראלי"),
    ("בורקס", "ישראלי"), ("כריך", "ישראלי"),
    # Middle Eastern
    ("שווארמה", "מזרח תיכוני"), ("לחמעג'ון", "מזרח תיכוני"), ("קבב", "מזרח תיכוני"),
    ("מנסף", "מזרח תיכוני"), ("מוסקה", "מזרח תיכוני"), ("טחינה", "מזרח תיכוני"),
    ("פלאפל ערבי", "מזרח תיכוני"), ("קושרי", "מזרח תיכוני"),
    # Meat
    ("סטייק", "בשר"), ("אנטרקוט", "בשר"), ("אסאדו", "בשר"), ("בורגר", "בשר"),
    ("צלעות", "בשר"), ("שניצל", "בשר"), ("כבד", "בשר"), ("פרגית", "בשר"),
    ("קציצות", "בשר"), ("ריבאי", "בשר"),
    # Mediterranean / Fish
    ("דג", "ים תיכוני"), ("שרימפס", "ים תיכוני"), ("קלמארי", "ים תיכוני"),
    ("דניס", "ים תיכוני"), ("לברק", "ים תיכוני"), ("סלמון", "ים תיכוני"),
    ("צדפות", "ים תיכוני"), ("דג מלוח", "ים תיכוני"),
    # Asian
    ("פד תאי", "תאילנדי"), ("קרי ירוק", "תאילנדי"), ("טום יאם", "תאילנדי"),
    ("קרי", "הודי"), ("נאן", "הודי"), ("ביריאני", "הודי"), ("סמוסה", "הודי"),
    ("דים סאם", "סיני"), ("אוטופף", "סיני"), ("אורז מוקפץ", "סיני"),
    # Mexican
    ("טאקו", "מקסיקני"), ("בוריטו", "מקסיקני"), ("נאצ'וס", "מקסיקני"),
    ("גואקמולה", "מקסיקני"), ("קסדייה", "מקסיקני"),
    # Cafe / Brunch
    ("קרואסון", "קפה"), ("קפה", "קפה"), ("עוגה", "קפה"),
    ("ביצים בנדיקט", "קפה"), ("פנקייק", "קפה"), ("וופל", "קפה"),
    ("אבוקדו טוסט", "קפה"), ("גרנולה", "קפה"), ("צ'יה", "קפה"),
    # Vegan / Healthy
    ("בודהה בול", "טבעוני"), ("קינואה", "טבעוני"), ("טופו", "טבעוני"),
    ("סלט", "בריא"), ("שייק", "בריא"), ("אקאי", "בריא"),
]

# (Hebrew expression, price_min, price_max)
PRICE_EXPRESSIONS = [
    ("זול", None, 50), ("זולה", None, 50), ("זולים", None, 50),
    ("במחיר טוב", None, 70), ("בסביריות מחיר", None, 80),
    ("עד 50 שקל", None, 50), ("עד 60 שקל", None, 60),
    ("עד 80 שקל", None, 80), ("עד 100 שקל", None, 100),
    ("עד 120 שקל", None, 120), ("עד 150 שקל", None, 150),
    ("עד 200 שקל", None, 200), ("עד 250 שקל", None, 250),
    ("60-80 שקל", 60, 80), ("80-120 שקל", 80, 120),
    ("100-150 שקל", 100, 150), ("150-200 שקל", 150, 200),
    ("בינוני", 60, 120), ("בינונית", 60, 120),
    ("יקר", 150, None), ("יוקרתי", 200, None), ("פרימיום", 200, None),
    ("מ-60 שקל", 60, None), ("מ-80 שקל", 80, None), ("מ-100 שקל", 100, None),
    ("בסביבות 80 שקל", 60, 100), ("בסביבות 100 שקל", 80, 120),
    ("לא יקר", None, 80), ("לא יקרה", None, 80),
    ("משתלם", None, 70), ("משתלמת", None, 70),
]

# City prepositional phrases in Hebrew
CITY_PREPS = ["ב{}", "ב{}", "באיזור {}", "ליד {}", "בעיר {}", "באזור {}"]

# Sentence templates: {dish}, {cuisine}, {city}, {price} are slots
TEMPLATES = [
    # Dish only
    "{dish}",
    "מסעדת {dish}",
    "מקום עם {dish} טוב",
    "איפה אפשר לאכול {dish}",
    "מחפש {dish}",
    "יש {dish} טוב",
    "הכי טוב {dish}",
    "המלצה על {dish}",
    # City only
    "מסעדות {city_prep}",
    "מה טוב {city_prep}",
    "מקומות לאכול {city_prep}",
    "המלצה על מסעדה {city_prep}",
    "איפה לאכול {city_prep}",
    "מסעדה טובה {city_prep}",
    # Dish + City
    "{dish} {city_prep}",
    "{dish} טוב {city_prep}",
    "מסעדה עם {dish} {city_prep}",
    "איפה {dish} {city_prep}",
    "רוצה {dish} {city_prep}",
    "מחפש {dish} {city_prep}",
    "יש {dish} {city_prep}",
    "הכי טוב {dish} {city_prep}",
    "המלצה {dish} {city_prep}",
    "איפה אפשר {dish} {city_prep}",
    "מקום ל{dish} {city_prep}",
    # Price + City
    "מסעדה {price} {city_prep}",
    "לאכול {price} {city_prep}",
    "מקום {price} {city_prep}",
    "מקום לאכול {price} {city_prep}",
    # Dish + Price
    "{dish} {price}",
    "{dish} במחיר {price}",
    "{dish} {price} בערך",
    "מחפש {dish} {price}",
    # Dish + City + Price
    "{dish} {city_prep} {price}",
    "{dish} {price} {city_prep}",
    "רוצה {dish} {city_prep} במחיר {price}",
    "חפש לי {dish} {city_prep} {price}",
    "מחפש {dish} {price} {city_prep}",
    "איפה {dish} {price} {city_prep}",
    "יש {dish} {city_prep} {price}",
    # Cuisine-based
    "מסעדה {cuisine} {city_prep}",
    "מטבח {cuisine} {city_prep}",
    "{cuisine} טוב {city_prep}",
    "אוכל {cuisine} {city_prep}",
    "{cuisine} {city_prep} {price}",
    "מסעדה {cuisine} {price}",
    "מחפש {cuisine} {city_prep}",
    "המלצה על {cuisine} {city_prep}",
    "אוכל {cuisine} טוב {city_prep}",
    "מסעדת {cuisine} {city_prep}",
    # Cuisine + Dish + City
    "{dish} {cuisine} {city_prep}",
    "{cuisine} עם {dish} {city_prep}",
    # Natural / conversational
    "מקום רומנטי {city_prep}",
    "ארוחת ערב {city_prep}",
    "ברנץ' {city_prep}",
    "אוכל טוב {city_prep}",
    "ארוחת צהריים {city_prep}",
    "ארוחת בוקר {city_prep}",
    "יציאה לאכול {city_prep}",
    "לאן לצאת לאכול {city_prep}",
    "מסעדה מומלצת {city_prep}",
    "אוכל עם חברים {city_prep}",
    "מקום לאכול עם משפחה {city_prep}",
]

# ── Generator ─────────────────────────────────────────────────────────────────

def _make_city_prep(city: str) -> str:
    tmpl = random.choice(CITY_PREPS)
    return tmpl.format(city)


def generate_example() -> tuple[str, dict]:
    """Returns (input_query, structured_output_dict)."""
    template = random.choice(TEMPLATES)

    city = random.choice(CITIES) if random.random() < 0.6 else None
    dish_entry = random.choice(DISHES) if random.random() < 0.7 else None
    price_entry = random.choice(PRICE_EXPRESSIONS) if random.random() < 0.4 else None

    dish = dish_entry[0] if dish_entry else None
    cuisine = dish_entry[1] if dish_entry else None

    city_prep = _make_city_prep(city) if city else ""

    price_expr = price_entry[0] if price_entry else ""
    price_min = price_entry[1] if price_entry else None
    price_max = price_entry[2] if price_entry else None

    query = template.format(
        dish=dish or "אוכל",
        cuisine=cuisine or "מקומי",
        city_prep=city_prep,
        price=price_expr,
    ).strip()

    # Clean up double spaces
    import re
    query = re.sub(r"\s+", " ", query).strip()

    output = {
        "city": city,
        "cuisine": cuisine,
        "dish": dish,
        "price_min_ils": price_min,
        "price_max_ils": price_max,
    }

    return query, output


def generate_dataset(count: int) -> list[dict]:
    seen: set[str] = set()
    examples = []
    attempts = 0

    while len(examples) < count and attempts < count * 10:
        attempts += 1
        query, output = generate_example()
        if query in seen or len(query) < 2:
            continue
        seen.add(query)
        examples.append({
            "input": query,
            "output": json.dumps(output, ensure_ascii=False),
            "label": output,
        })

    return examples


def save_dataset(examples: list[dict], path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps({"input": ex["input"], "output": ex["output"]}, ensure_ascii=False) + "\n")
    print(f"Saved {len(examples)} examples → {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10000)
    parser.add_argument("--out", default="data/train.jsonl")
    parser.add_argument("--eval-out", default="data/eval.jsonl")
    parser.add_argument("--eval-ratio", type=float, default=0.1)
    args = parser.parse_args()

    print(f"Generating {args.count} examples...")
    all_data = generate_dataset(args.count)
    random.shuffle(all_data)

    split = int(len(all_data) * (1 - args.eval_ratio))
    train_data = all_data[:split]
    eval_data = all_data[split:]

    save_dataset(train_data, args.out)
    save_dataset(eval_data, args.eval_out)

    # Quick sanity check
    print("\nSample examples:")
    for ex in random.sample(train_data, min(5, len(train_data))):
        print(f"  input:  {ex['input']!r}")
        print(f"  output: {ex['output']}")
        print()
