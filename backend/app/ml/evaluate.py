"""
Evaluate the trained model against the eval set and real queries.

Usage:
    poetry run python -m app.ml.evaluate --eval data/eval.jsonl
    poetry run python -m app.ml.evaluate --query "סושי במודיעין"
"""

import json
import argparse


def evaluate_file(eval_path: str) -> None:
    from app.ml.inference import local_model_parse

    with open(eval_path, encoding="utf-8") as f:
        examples = [json.loads(line) for line in f if line.strip()]

    correct_city = correct_dish = correct_cuisine = total = 0

    for ex in examples:
        total += 1
        expected = json.loads(ex["output"])
        predicted = local_model_parse(ex["input"])

        if predicted is None:
            continue

        if predicted.get("city") == expected.get("city"):
            correct_city += 1
        if predicted.get("dish") == expected.get("dish"):
            correct_dish += 1
        if predicted.get("cuisine") == expected.get("cuisine"):
            correct_cuisine += 1

    print(f"Evaluated {total} examples")
    print(f"  City accuracy:    {correct_city/total*100:.1f}%")
    print(f"  Dish accuracy:    {correct_dish/total*100:.1f}%")
    print(f"  Cuisine accuracy: {correct_cuisine/total*100:.1f}%")


def evaluate_query(query: str) -> None:
    from app.ml.inference import local_model_parse, is_model_available

    if not is_model_available():
        print("Model not available. Train it first with app.ml.train")
        return

    result = local_model_parse(query)
    print(f"Query:  {query!r}")
    print(f"Result: {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", help="Path to eval.jsonl")
    parser.add_argument("--query", help="Single query to test")
    args = parser.parse_args()

    if args.query:
        evaluate_query(args.query)
    elif args.eval:
        evaluate_file(args.eval)
    else:
        parser.print_help()
