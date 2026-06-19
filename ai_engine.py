"""
ai_engine.py
Groq LLM integration for carbon-footprint insights.
Returns a validated JSON object – never raw markdown or prose.
"""

import json
import os
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.1-8b-instant"

REQUIRED_KEYS = {"summary", "top_emission_sources", "suggestions", "eco_score", "motivation"}

# ── Fallback used when the API is unavailable ────────────────────────────────
FALLBACK_RESPONSE: dict[str, Any] = {
    "summary":              "Unable to reach the AI service. Please try again later.",
    "top_emission_sources": [],
    "suggestions":          [
        "Reduce car travel and prefer public transport.",
        "Switch to a plant-based diet a few days a week.",
        "Turn off appliances when not in use to lower electricity consumption.",
    ],
    "eco_score":  50,
    "motivation": "Every small action counts towards a greener planet!",
}


def _build_prompt(activities: list[dict], daily_total: float,
                  category_breakdown: dict) -> str:
    """Construct the system + user prompt sent to the LLM."""
    activity_lines = "\n".join(
        f"  - {a['activity_type']} | qty: {a['quantity']} | "
        f"CO2: {a['co2_kg']} kg | {a['timestamp']}"
        for a in activities
    ) or "  (no activities logged yet)"

    breakdown_lines = "\n".join(
        f"  - {cat}: {val} kg CO2" for cat, val in category_breakdown.items()
    )

    return (
        "You are an environmental AI assistant. "
        "Analyse the user's carbon footprint data and respond with ONLY valid JSON – "
        "no markdown fences, no explanatory text before or after.\n\n"
        "Required JSON schema (all keys mandatory):\n"
        "{\n"
        '  "summary": "<2-3 sentence overview>",\n'
        '  "top_emission_sources": ["<source1>", "<source2>"],\n'
        '  "suggestions": ["<action1>", "<action2>", "<action3>"],\n'
        '  "eco_score": <integer 0-100>,\n'
        '  "motivation": "<one encouraging sentence>"\n'
        "}\n\n"
        "Rules:\n"
        "- eco_score: 100 = zero emissions, 0 = very high emissions. "
        "  Score above 70 if daily total < 5 kg, 40-70 if 5-15 kg, below 40 if > 15 kg.\n"
        "- suggestions: provide 3-5 specific, actionable steps.\n"
        "- top_emission_sources: list the 1-3 biggest contributors.\n\n"
        f"User activity log (last 7 days):\n{activity_lines}\n\n"
        f"Category breakdown (last 7 days):\n{breakdown_lines}\n\n"
        f"Today's total CO2: {daily_total:.2f} kg\n\n"
        "Respond with ONLY the JSON object."
    )


def _parse_and_validate(raw: str) -> dict[str, Any]:
    """Extract a valid JSON object from *raw*, stripping any surrounding text."""
    # Strip accidental markdown fences
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(
            line for line in lines
            if not line.strip().startswith("```")
        ).strip()

    # Find the outermost { … }
    start = text.find("{")
    end   = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in LLM response.")

    payload = json.loads(text[start : end + 1])

    missing = REQUIRED_KEYS - payload.keys()
    if missing:
        raise ValueError(f"LLM response missing keys: {missing}")

    # Coerce eco_score to int in [0, 100]
    payload["eco_score"] = max(0, min(100, int(payload["eco_score"])))

    # Ensure list fields are lists
    for key in ("top_emission_sources", "suggestions"):
        if not isinstance(payload[key], list):
            payload[key] = [str(payload[key])]

    return payload


def get_ai_insights(
    activities: list[dict],
    daily_total: float,
    category_breakdown: dict,
) -> dict[str, Any]:
    """Call Groq LLM and return a validated insights dict.

    Args:
        activities:         List of activity dicts from the DB.
        daily_total:        Today's CO2 total in kg.
        category_breakdown: {"travel": x, "food": y, "electricity": z}

    Returns:
        Dict with keys: summary, top_emission_sources, suggestions,
                        eco_score, motivation.
        Falls back to FALLBACK_RESPONSE on any error.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        logger.warning("GROQ_API_KEY not set – returning fallback response.")
        return FALLBACK_RESPONSE.copy()

    prompt = _build_prompt(activities, daily_total, category_breakdown)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       GROQ_MODEL,
        "messages":    [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens":  800,
    }

    try:
        response = requests.post(
            GROQ_API_URL, headers=headers, json=payload, timeout=30
        )
        response.raise_for_status()
        raw_text = response.json()["choices"][0]["message"]["content"]
        return _parse_and_validate(raw_text)

    except requests.exceptions.Timeout:
        logger.error("Groq API request timed out.")
    except requests.exceptions.HTTPError as exc:
        err_msg = exc.response.text if exc.response is not None else ""
        logger.error("Groq API HTTP error: %s | Response: %s", exc, err_msg)
    except (KeyError, IndexError) as exc:
        logger.error("Unexpected Groq response structure: %s", exc)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to parse Groq response as JSON: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error calling Groq: %s", exc)

    return FALLBACK_RESPONSE.copy()
