"""Turn listing facts into polished flyer copy with the Claude API.

A single `tool_use` call (forced via `tool_choice`) coerces the model into a
strict JSON shape so the renderer never has to parse prose. The model writes
the marketing voice; it does NOT invent facts — every number it prints must
come from the listing dict it is given.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

CLAUDE_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a senior real-estate copywriter producing the text for a single-page
open-house flyer. You are given a JSON fact sheet for one property.

Voice: warm, aspirational, concrete. Sell the lifestyle, not just the specs.
Short, punchy sentences. No clichés like "must see" or "won't last".

Hard rules:
- NEVER invent facts. Only reference beds/baths/sqft/year/lot/price that appear
  in the fact sheet. If a number is missing, write around it — do not guess.
- Keep it FAIR-HOUSING SAFE. Describe the PROPERTY, never the buyer or who would
  live there. Do not reference family/children, race, religion, national origin,
  disability, sex, or a neighborhood's "safety", "exclusivity", or demographics.
  Say "spacious primary suite", never "perfect for a growing family".
- features: 4 to 6 bullets, each <= 6 words, each a concrete property feature.
  If the fact sheet lists features, polish those; otherwise infer reasonable
  ones ONLY from stated facts (e.g. large sqft -> "Generous open floor plan").
- socialCaption: 1-3 short lines for Instagram/Facebook, may use 1-2 tasteful
  emoji, end with 4-6 relevant hashtags.
- Always answer by calling the write_flyer_copy tool. Never reply in plain text.
"""

FLYER_COPY_TOOL = {
    "name": "write_flyer_copy",
    "description": "The finished copy blocks for an open-house flyer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "string",
                "description": "5-8 word hero headline for the property.",
            },
            "subheadline": {
                "type": "string",
                "description": "One line, e.g. a location or single best selling point.",
            },
            "statLine": {
                "type": "string",
                "description": "Compact spec line built ONLY from given facts, "
                "e.g. '4 Bed  •  3 Bath  •  2,450 SqFt'. Omit any spec not provided.",
            },
            "description": {
                "type": "string",
                "description": "2-3 sentence property description paragraph.",
            },
            "features": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4-6 short feature bullets.",
            },
            "openHouseLine": {
                "type": "string",
                "description": "Open-house call-out if a date/time was given, "
                "else an empty string.",
            },
            "callToAction": {
                "type": "string",
                "description": "One short closing line inviting a tour/contact.",
            },
            "socialCaption": {
                "type": "string",
                "description": "Caption for social posts with hashtags.",
            },
        },
        "required": [
            "headline",
            "subheadline",
            "statLine",
            "description",
            "features",
            "openHouseLine",
            "callToAction",
            "socialCaption",
        ],
    },
}


def _facts_for_prompt(listing: dict) -> str:
    """Strip the photo path and internal keys before showing facts to the model."""
    clean = {k: v for k, v in listing.items() if not k.startswith("_") and k != "photo"}
    return json.dumps(clean, indent=2)


def _via_sdk(listing: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[FLYER_COPY_TOOL],
        tool_choice={"type": "tool", "name": "write_flyer_copy"},
        messages=[
            {
                "role": "user",
                "content": "Write the flyer copy for this listing:\n\n"
                + _facts_for_prompt(listing),
            }
        ],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "write_flyer_copy":
            return block.input
    raise RuntimeError(f"Claude did not call write_flyer_copy. Response: {response}")


CLI_PROMPT = """You are a senior real-estate copywriter. Using ONLY the facts in the JSON
below, write open-house flyer copy. Never invent specs. Keep it Fair-Housing
safe (describe the property, never who would live there; no family/safety/
demographic language).

Facts:
{facts}

Return ONLY this JSON object on stdout — no prose, no markdown fences:
{{
  "headline": "...",
  "subheadline": "...",
  "statLine": "4 Bed  •  3 Bath  •  2,450 SqFt",
  "description": "2-3 sentences.",
  "features": ["...", "...", "...", "..."],
  "openHouseLine": "Open House: ... (or empty string)",
  "callToAction": "...",
  "socialCaption": "... #hashtags"
}}"""


def _via_cli(listing: dict) -> dict:
    """Fallback when the SDK key is missing/rotated: use Claude Code's OAuth."""
    from claude_cli import run_cli_json
    return run_cli_json(CLI_PROMPT.format(facts=_facts_for_prompt(listing)))


def write_copy(listing: dict) -> dict:
    """Return the flyer copy dict. Prefer SDK; fall back to CLI on auth failure."""
    try:
        return _via_sdk(listing)
    except Exception as e:
        msg = str(e).lower()
        if "401" in msg or "auth" in msg or "api key" in msg or "x-api-key" in msg:
            print("  (SDK auth failed — falling back to claude CLI)", file=sys.stderr)
            return _via_cli(listing)
        raise


if __name__ == "__main__":
    data = json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else json.load(sys.stdin)
    print(json.dumps(write_copy(data), indent=2))
