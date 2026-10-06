"""
AI summarization endpoint — uses Groq (free tier, Llama 3.3) to summarize
restaurant sources and produce a personalized match score based on user preferences.
"""
import json
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.places import get_place_by_slug

router = APIRouter(prefix="/ai", tags=["ai"])

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3.8-27b"


class SummarizeRequest(BaseModel):
    place_slug: str
    preferences: str | None = None


class AISummaryResponse(BaseModel):
    summary: str
    match_score: int
    highlights: list[str]
    warnings: list[str]


def _build_prompt(name: str, excerpts: list[str], preferences: str | None) -> str:
    excerpts_text = "\n".join(f"• {e}" for e in excerpts if e)
    pref_text = preferences or "כללי, ללא העדפה מיוחדת"
    return f"""אתה מומחה מסעדות ישראלי. קיבלת ביקורות ומידע על המסעדה "{name}".

מקורות:
{excerpts_text}

העדפות המשתמש: {pref_text}

ענה ב-JSON בלבד, ללא markdown, ללא טקסט נוסף:
{{"summary":"סיכום 2-3 משפטים בעברית","match_score":<0-100>,"highlights":["נקודה חיובית 1","נקודה חיובית 2"],"warnings":["אזהרה אם יש"]}}"""


@router.post("/summarize", response_model=AISummaryResponse)
async def summarize(body: SummarizeRequest, db: AsyncSession = Depends(get_db)):
    api_key = settings.gemini_api_key
    if not api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY not configured")

    place = await get_place_by_slug(db, body.place_slug)
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")

    excerpts = [s.excerpt for s in place.sources if s.excerpt]
    if not excerpts:
        raise HTTPException(status_code=422, detail="No source content available to summarize")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": _build_prompt(place.name, excerpts, body.preferences)}],
                    "max_tokens": 512,
                    "temperature": 0.4,
                    "response_format": {"type": "json_object"},
                },
            )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        data = json.loads(raw)
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:200] if e.response else str(e)
        raise HTTPException(status_code=502, detail=f"Groq API error: {detail}")
    except (KeyError, IndexError):
        raise HTTPException(status_code=502, detail="Unexpected Groq response shape")
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="AI returned invalid JSON")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI error: {str(e)}")

    return AISummaryResponse(
        summary=data.get("summary", ""),
        match_score=max(0, min(100, int(data.get("match_score", 50)))),
        highlights=data.get("highlights", []),
        warnings=data.get("warnings", []),
    )
