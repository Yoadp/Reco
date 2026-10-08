"""
Fine-tune mT5-small on the Hebrew restaurant query parsing task.

Requires: pip install transformers datasets torch sentencepiece

Usage:
    # 1. Generate data first:
    poetry run python -m app.ml.data_generator --count 15000

    # 2. Train:
    poetry run python -m app.ml.train \
        --train data/train.jsonl \
        --eval  data/eval.jsonl  \
        --out   models/query-parser \
        --epochs 5

The trained model is saved to `models/query-parser/` and can be loaded
by `app.ml.inference` to replace Groq NLP calls.
"""

import json
import argparse
from pathlib import Path

# ── Training ──────────────────────────────────────────────────────────────────

INPUT_PREFIX = "parse restaurant query: "
BASE_MODEL = "google/mt5-small"   # 300MB multilingual T5


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_with_real_queries(train_path: str, real_path: str | None) -> list[dict]:
    """Load synthetic training data and merge in real Groq-answered queries (deduplicated)."""
    data = load_jsonl(train_path)
    if not real_path:
        return data
    real_path_obj = Path(real_path)
    if not real_path_obj.exists():
        print(f"No real queries file at {real_path} — using synthetic data only")
        return data
    real = load_jsonl(real_path)
    # Real queries go first so they're weighted more; dedup by input
    seen = {ex["input"] for ex in real}
    merged = real + [ex for ex in data if ex["input"] not in seen]
    print(f"Merged {len(real)} real queries + {len(data)} synthetic = {len(merged)} total")
    return merged


def train(
    train_path: str,
    eval_path: str,
    output_dir: str,
    epochs: int = 5,
    batch_size: int = 16,
    lr: float = 5e-4,
    max_input_len: int = 64,
    max_output_len: int = 128,
    real_queries_path: str | None = None,
) -> None:
    # Late imports so the module loads without torch installed
    from transformers import (
        T5Tokenizer,
        MT5ForConditionalGeneration,
        Seq2SeqTrainer,
        Seq2SeqTrainingArguments,
        DataCollatorForSeq2Seq,
        EarlyStoppingCallback,
    )
    from datasets import Dataset

    print(f"Loading base model: {BASE_MODEL}")
    tokenizer = T5Tokenizer.from_pretrained(BASE_MODEL, legacy=False)
    model = MT5ForConditionalGeneration.from_pretrained(BASE_MODEL)

    train_raw = load_with_real_queries(train_path, real_queries_path)
    eval_raw = load_jsonl(eval_path)
    print(f"Train: {len(train_raw)} | Eval: {len(eval_raw)}")

    def preprocess(examples):
        inputs = [INPUT_PREFIX + q for q in examples["input"]]
        targets = examples["output"]

        model_inputs = tokenizer(
            inputs,
            max_length=max_input_len,
            truncation=True,
            padding="max_length",
        )
        labels = tokenizer(
            text_target=targets,
            max_length=max_output_len,
            truncation=True,
            padding="max_length",
        )
        # Replace padding token id with -100 so loss ignores them
        labels["input_ids"] = [
            [(t if t != tokenizer.pad_token_id else -100) for t in label]
            for label in labels["input_ids"]
        ]
        model_inputs["labels"] = labels["input_ids"]
        return model_inputs

    train_ds = Dataset.from_list(train_raw).map(preprocess, batched=True, remove_columns=["input", "output"])
    eval_ds = Dataset.from_list(eval_raw).map(preprocess, batched=True, remove_columns=["input", "output"])

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    warmup_steps = max(1, int(0.1 * (len(train_raw) // batch_size) * epochs))
    args = Seq2SeqTrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=lr,
        warmup_steps=warmup_steps,
        weight_decay=0.01,
        generation_max_length=max_output_len,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=50,
        report_to="none",
        fp16=False,
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        data_collator=DataCollatorForSeq2Seq(tokenizer, model=model, padding=True),
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    # Resume from the latest checkpoint if one exists
    checkpoints = sorted(Path(output_dir).glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1]))
    resume_from = str(checkpoints[-1]) if checkpoints else None
    if resume_from:
        print(f"Resuming from checkpoint: {resume_from}")

    print("Starting training...")
    trainer.train(resume_from_checkpoint=resume_from)

    print(f"Saving model to {output_dir}")
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", default="data/train.jsonl")
    parser.add_argument("--eval", default="data/eval.jsonl")
    parser.add_argument("--real", default="data/real_queries.jsonl", help="Real Groq-answered queries to merge in")
    parser.add_argument("--out", default="models/query-parser")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=5e-4)
    args = parser.parse_args()

    train(
        train_path=args.train,
        eval_path=args.eval,
        output_dir=args.out,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        real_queries_path=args.real,
    )
