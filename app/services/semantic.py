from google import genai
from pydantic import BaseModel, Field
from typing import Literal

from app.config import settings


client = genai.Client(
    api_key=settings.gemini_api_key
)

MODEL = settings.gemini_model

class ChangeAnalysis(BaseModel):
    importance: Literal["low", "medium", "high", "critical"]
    change_type: Literal[
        "cosmetic",
        "content",
        "deadline",
        "requirement",
        "eligibility",
        "price",
        "availability",
        "policy",
        "other",
    ]
    summary: str
    why_it_matters: str
    should_notify: bool
    entities: list[str] = Field(default_factory=list)


def analyze_change(
    source_name: str,
    category: str,
    added: list[str],
    removed: list[str],
    replaced: list[dict[str, list[str]]],
) -> ChangeAnalysis:

    prompt = f"""
You are Sentinel's change-intelligence engine.

Analyze ONLY the website changes provided below.

Source: {source_name}
Category: {category}

Rules:
- Ignore navigation, menus, cookie banners, timestamps, footers,
  tracking text, and other cosmetic changes.
- Do not invent facts.
- Identify concrete changes such as deadlines, requirements,
  eligibility, prices, availability, policies, or important content.
- Compare OLD vs NEW carefully for replacements.
- "critical" is reserved for changes requiring very urgent attention.
- Set should_notify=true only when the change is meaningful to a user.
- Keep summary and why_it_matters concise.

ADDED:
{added}

REMOVED:
{removed}

REPLACED:
{replaced}
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": ChangeAnalysis,
        },
    )

    if response.parsed is None:
        raise RuntimeError("Gemini returned no structured change analysis.")

    return response.parsed
