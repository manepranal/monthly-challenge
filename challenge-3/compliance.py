"""Fair-Housing gate: review (and if needed, sanitize) the flyer copy before it
is ever rendered.

The Fair Housing Act (and most state equivalents) prohibits real-estate
advertising that states a preference, limitation, or discrimination based on a
protected class — or that describes the likely OCCUPANTS rather than the
property. Realtor.com / NAR enforce this strictly; a non-compliant flyer is a
real legal exposure for the agent, so this gate is the whole reason a QA-built
A4A skill is trustworthy.

The copywriter is already prompted to stay compliant; this is the independent
second check (defense in depth) — a different Claude call whose ONLY job is to
hunt for violations and rewrite the offending lines while preserving meaning.

Rules live in `.claude/skills/validate-fair-housing.md`.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

CLAUDE_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a Fair Housing compliance reviewer for real-estate marketing copy.

You will be given the JSON copy blocks for an open-house flyer. Flag any text
that violates the Fair Housing Act or reads as steering. Violations include:

- References to a protected class: race, color, religion, national origin, sex,
  disability/handicap, or FAMILIAL STATUS (children/families/empty-nesters).
- Describing the likely OCCUPANT instead of the property: "perfect for a growing
  family", "ideal for newlyweds", "great for retirees", "bachelor pad".
- Coded neighborhood/demographic language: "safe neighborhood", "exclusive",
  "private community", "good schools nearby", "walking distance to church/temple",
  "integrated", "traditional".
- Ability/access assumptions: "perfect for active adults", "no wheelchair access".

NOT violations (leave alone): neutral PROPERTY features and amenities, prices,
specs, location names, "spacious", "open floor plan", "primary suite", "move-in
ready", school district stated only as a neutral fact is borderline — prefer to
soften it to a neutral amenity if present.

For every field, return a sanitized version that fixes violations while keeping
the marketing intent and the property facts intact. If a field is already clean,
return it unchanged. Always answer by calling the report_compliance tool.
"""

COMPLIANCE_TOOL = {
    "name": "report_compliance",
    "description": "Fair-Housing review result with a sanitized copy of every field.",
    "input_schema": {
        "type": "object",
        "properties": {
            "compliant": {
                "type": "boolean",
                "description": "true if the ORIGINAL copy had zero violations.",
            },
            "violations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "text": {"type": "string", "description": "the offending excerpt"},
                        "protectedClass": {"type": "string"},
                        "issue": {"type": "string"},
                    },
                    "required": ["field", "text", "issue"],
                },
            },
            "sanitized": {
                "type": "object",
                "description": "The full copy object with every violation rewritten. "
                "Same keys as the input copy.",
                "properties": {
                    "headline": {"type": "string"},
                    "subheadline": {"type": "string"},
                    "statLine": {"type": "string"},
                    "description": {"type": "string"},
                    "features": {"type": "array", "items": {"type": "string"}},
                    "openHouseLine": {"type": "string"},
                    "callToAction": {"type": "string"},
                    "socialCaption": {"type": "string"},
                },
                "required": [
                    "headline", "subheadline", "statLine", "description",
                    "features", "openHouseLine", "callToAction", "socialCaption",
                ],
            },
        },
        "required": ["compliant", "violations", "sanitized"],
    },
}


def _via_sdk(copy: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        system=[{"type": "text", "text": SYSTEM_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        tools=[COMPLIANCE_TOOL],
        tool_choice={"type": "tool", "name": "report_compliance"},
        messages=[{"role": "user",
                   "content": "Review this flyer copy:\n\n" + json.dumps(copy, indent=2)}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "report_compliance":
            return block.input
    raise RuntimeError(f"Claude did not call report_compliance. Response: {response}")


CLI_PROMPT = """You are a Fair Housing compliance reviewer. Review the flyer copy JSON below.
Flag any text referencing a protected class (race, religion, national origin,
sex, disability, FAMILIAL STATUS/children/families) or describing the likely
occupant instead of the property, or coded language ("safe", "exclusive",
"good schools", "perfect for families"). Rewrite violations to be neutral
property descriptions while keeping the facts and marketing intent.

Copy:
{copy}

Return ONLY this JSON on stdout, no prose, no fences:
{{
  "compliant": true_or_false,
  "violations": [{{"field":"...","text":"...","protectedClass":"...","issue":"..."}}],
  "sanitized": {{ ...the full copy object with the same keys, violations fixed... }}
}}"""


def _via_cli(copy: dict) -> dict:
    from claude_cli import run_cli_json
    return run_cli_json(CLI_PROMPT.format(copy=json.dumps(copy, indent=2)))


def review(copy: dict) -> dict:
    """Return {compliant, violations, sanitized}. Prefer SDK; CLI on auth fail."""
    try:
        result = _via_sdk(copy)
    except Exception as e:
        msg = str(e).lower()
        if "401" in msg or "auth" in msg or "api key" in msg or "x-api-key" in msg:
            print("  (SDK auth failed — falling back to claude CLI)", file=sys.stderr)
            result = _via_cli(copy)
        else:
            raise
    # Guard: if the reviewer dropped a key, fall back to the original for it.
    sanitized = {**copy, **(result.get("sanitized") or {})}
    result["sanitized"] = sanitized
    return result


if __name__ == "__main__":
    data = json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else json.load(sys.stdin)
    print(json.dumps(review(data), indent=2))
