"""
Local model inference — drop-in replacement for Groq NLP in nlp_parse_query().

The model is loaded once on first use (lazy singleton).
If the model directory doesn't exist, returns None and the caller
falls back to _local_parse_query() or Groq.

Usage in services/places.py:
    from app.ml.inference import local_model_parse

    result = local_model_parse("סושי במודיעין")
    # → {"city": "מודיעין", "cuisine": "יפני", "dish": "סושי", ...}
    # → None if model not loaded yet
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent.parent / "models" / "query-parser"
INPUT_PREFIX = "parse restaurant query: "

_model = None
_tokenizer = None
_loaded: bool = False


def _load_model() -> bool:
    """Load model into memory once. Returns True if successful."""
    global _model, _tokenizer, _loaded

    if _loaded:
        return _model is not None

    _loaded = True  # prevent retry loops on import error

    if not MODEL_DIR.exists():
        logger.info("Local query-parser model not found at %s — using Groq/local-parser fallback", MODEL_DIR)
        return False

    try:
        from transformers import T5Tokenizer, MT5ForConditionalGeneration
        import torch

        logger.info("Loading local query-parser model from %s ...", MODEL_DIR)
        _tokenizer = T5Tokenizer.from_pretrained(str(MODEL_DIR), legacy=False)
        _model = MT5ForConditionalGeneration.from_pretrained(str(MODEL_DIR))
        _model.eval()

        # Move to MPS (Apple Silicon) or CPU
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        _model = _model.to(device)
        logger.info("Local query-parser ready on %s", device)
        return True
    except Exception as exc:
        logger.warning("Failed to load local query-parser: %s", exc)
        _model = None
        _tokenizer = None
        return False


def local_model_parse(query: str, max_new_tokens: int = 100) -> Optional[dict]:
    """
    Parse a Hebrew restaurant query using the local fine-tuned model.
    Returns structured dict or None if model is unavailable.
    """
    if not _load_model() or _model is None or _tokenizer is None:
        return None

    try:
        import torch
        device = next(_model.parameters()).device

        input_text = INPUT_PREFIX + query
        inputs = _tokenizer(
            input_text,
            return_tensors="pt",
            max_length=64,
            truncation=True,
        ).to(device)

        with torch.no_grad():
            outputs = _model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                num_beams=4,
                early_stopping=True,
            )

        decoded = _tokenizer.decode(outputs[0], skip_special_tokens=True)

        # Parse JSON output
        parsed = json.loads(decoded)

        # Normalise: ensure all expected keys exist
        return {
            "city": parsed.get("city"),
            "cuisine": parsed.get("cuisine"),
            "dish": parsed.get("dish"),
            "price_min_ils": parsed.get("price_min_ils"),
            "price_max_ils": parsed.get("price_max_ils"),
        }
    except Exception as exc:
        logger.debug("Local model parse failed for %r: %s", query, exc)
        return None


def is_model_available() -> bool:
    """Check whether the local model is loaded and ready."""
    return _load_model()
