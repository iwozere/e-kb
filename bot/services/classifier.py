"""Auto-classify entry type and generate titles via Claude."""
import json
import logging

from bot.services.llm import complete

logger = logging.getLogger(__name__)

_VALID_TYPES = {"note", "book", "health", "sport"}

CLASSIFY_PROMPT = """Classify this note into exactly one type:
- note      (general thought, observation, idea)
- book      (reading, book review, learning from a book)
- health    (medical, sleep, weight, lab results, symptoms)
- sport     (workout, run, gym, physical activity)

Return ONLY valid JSON with no extra text: {{"type": "...", "confidence": 0.0-1.0}}

Note: {text}"""

_STRUCTURED_PROMPTS = {
    "book": (
        'Extract book info from this note: "{text}"\n\n'
        'Return ONLY valid JSON: {{"title": "...", "author": "...", '
        '"status": "reading|finished|abandoned", "rating": null_or_1_to_10}}'
    ),
    "health": (
        'Extract health metric from this note: "{text}"\n\n'
        'Return ONLY valid JSON: {{"metric_type": "weight|sleep|blood_pressure|glucose|custom", '
        '"value": number_or_null, "unit": "kg|lbs|hours|...", "notes": "..."}}'
    ),
    "sport": (
        'Extract sport activity from this note: "{text}"\n\n'
        'Return ONLY valid JSON: {{"activity": "run|gym|swim|bike|yoga|custom", '
        '"duration_min": number_or_null, "intensity": "low|medium|high|null", '
        '"distance_km": number_or_null}}'
    ),
}


async def classify_entry(text: str) -> str:
    """
    Classify text into an entry type.  Returns one of: note, book, health, sport.
    Defaults to 'note' on errors or low confidence (< 0.7).
    """
    try:
        response = await complete(
            system="You are a text classifier. Return only valid JSON, no prose.",
            user=CLASSIFY_PROMPT.format(text=text[:500]),
            max_tokens=50,
        )
        data = json.loads(response.strip())
        entry_type = str(data.get("type", "note")).lower()
        confidence = float(data.get("confidence", 0.0))

        if entry_type not in _VALID_TYPES or confidence < 0.7:
            return "note"
        return entry_type
    except Exception:
        logger.exception("Classification failed — defaulting to 'note'")
        return "note"


async def generate_title(text: str) -> str:
    """Generate a concise 5-word title for an entry."""
    try:
        response = await complete(
            system=(
                "Generate a concise 5-word title for the following note. "
                "Return ONLY the title text, nothing else."
            ),
            user=text[:500],
            max_tokens=20,
        )
        return response.strip().strip('"').strip("'")
    except Exception:
        logger.exception("Title generation failed — using text prefix")
        # Fallback: first 50 printable chars
        return text[:50].replace("\n", " ").strip()


async def extract_structured(entry_type: str, text: str) -> dict:
    """
    Extract structured fields from text for book/health/sport entries.
    Returns an empty dict if the type is not structured or extraction fails.
    """
    prompt_template = _STRUCTURED_PROMPTS.get(entry_type)
    if not prompt_template:
        return {}

    try:
        response = await complete(
            system="You are a data extractor. Return ONLY valid JSON, no prose.",
            user=prompt_template.format(text=text[:400]),
            max_tokens=150,
        )
        return json.loads(response.strip())
    except Exception:
        logger.warning("Structured extraction failed for type '%s'", entry_type)
        return {}
