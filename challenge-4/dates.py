"""AI job #2 — read the executed contract (and any date-bearing emails) and pull
out every milestone into typed calendar events.

The contract is the source of truth; deadlines are scattered through legal prose
("shall expire at 5:00 PM on July 18, 2026"). A forced `tool_use` call returns
each milestone as a normalized event — name, ISO date, category, and how many
days ahead to remind — so the calendar builder never has to parse dates itself.

The milestone taxonomy and reminder policy live in
`.claude/skills/build-deal-calendar.md`.
"""

import json
import os
import sys

CLAUDE_MODEL = os.environ.get("DEAL_MODEL", "claude-sonnet-5")

CATEGORIES = [
    "Attorney Review",
    "Inspection",
    "Appraisal",
    "Financing",
    "Walk-Through",
    "Closing",
    "Other",
]

SYSTEM_PROMPT = """You extract the deadline calendar for a real-estate transaction from its
contract and emails. Real estate runs on dates, and a missed contingency date
can cost a client the deal or their deposit.

Rules:
- Extract EVERY dated milestone: effective date, attorney-review expiration,
  inspection contingency, appraisal contingency, mortgage/financing commitment,
  final walk-through, and closing. Include any other explicit deadline you find.
- `date` MUST be ISO format YYYY-MM-DD. Resolve phrases like "on July 18, 2026".
- Do NOT invent dates. Only include a milestone if a real date is stated. If a
  contingency is described but no date is given, skip it.
- `reminder_days_before`: how many days ahead the agent should be reminded.
  Contingency deadlines (inspection, appraisal, financing, attorney review): 3.
  Closing and final walk-through: 7. Informational dates (effective date): 0.
- `source`: the document/email the date came from (e.g. "Purchase Agreement").
- Prefer the contract when the same date appears in both a contract and an email.
- Always answer by calling the extract_milestones tool. Never reply in plain text.
"""

MILESTONES_TOOL = {
    "name": "extract_milestones",
    "description": "Every dated milestone for the deal, as calendar events.",
    "input_schema": {
        "type": "object",
        "properties": {
            "milestones": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Human title, e.g. 'Inspection Contingency Deadline'.",
                        },
                        "date": {
                            "type": "string",
                            "description": "ISO date YYYY-MM-DD.",
                        },
                        "category": {"type": "string", "enum": CATEGORIES},
                        "source": {"type": "string"},
                        "reminder_days_before": {"type": "integer"},
                        "note": {
                            "type": "string",
                            "description": "One short line of context for the event, or empty.",
                        },
                    },
                    "required": [
                        "name",
                        "date",
                        "category",
                        "source",
                        "reminder_days_before",
                        "note",
                    ],
                },
            }
        },
        "required": ["milestones"],
    },
}


def _source_text(inbox: dict) -> str:
    """Feed the model the contract (primary) + every attachment's text + the email
    bodies, so it can cross-check dates. Contract first so it wins ties."""
    parts = [f"DEAL: {inbox.get('deal', {}).get('property', '')}"]
    contracts, others = [], []
    for e in inbox.get("emails", []):
        for a in e.get("attachments", []):
            block = f"--- ATTACHMENT: {a['filename']} ---\n{a.get('text', '')}"
            if "agreement" in a["filename"].lower() or "contract" in a["filename"].lower():
                contracts.append(block)
            else:
                others.append(block)
    for e in inbox.get("emails", []):
        if e.get("body"):
            others.append(f"--- EMAIL from {e.get('from')} ({e.get('date')}): {e.get('subject')} ---\n{e['body']}")
    return "\n\n".join(parts + contracts + others)


def _via_sdk(inbox: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        tools=[MILESTONES_TOOL],
        tool_choice={"type": "tool", "name": "extract_milestones"},
        messages=[
            {
                "role": "user",
                "content": "Extract the milestone calendar from these documents:\n\n"
                + _source_text(inbox),
            }
        ],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_milestones":
            return block.input
    raise RuntimeError(f"Claude did not call extract_milestones. Response: {response}")


CLI_PROMPT = """You extract a real-estate deal's deadline calendar from its contract and
emails. Read the documents below and return every dated milestone.

Rules: date MUST be ISO YYYY-MM-DD; never invent a date; category from
{categories}; reminder_days_before = 3 for contingencies, 7 for closing and
walk-through, 0 for informational dates.

Documents:
{docs}

Return ONLY this JSON on stdout — no prose, no markdown fences:
{{
  "milestones": [
    {{"name": "...", "date": "2026-07-18", "category": "Inspection", "source": "Purchase Agreement", "reminder_days_before": 3, "note": "..."}}
  ]
}}"""


def _via_cli(inbox: dict) -> dict:
    from claude_cli import run_cli_json

    return run_cli_json(CLI_PROMPT.format(categories=CATEGORIES, docs=_source_text(inbox)))


def extract(inbox: dict) -> dict:
    """Return {milestones:[...]}. Prefer SDK; fall back to CLI on auth failure."""
    try:
        return _via_sdk(inbox)
    except Exception as e:
        msg = str(e).lower()
        if any(k in msg for k in ("401", "auth", "api key", "x-api-key", "credit")):
            print("  (SDK auth failed — falling back to claude CLI)", file=sys.stderr)
            return _via_cli(inbox)
        raise


if __name__ == "__main__":
    import fetch

    box = fetch.load_inbox(sys.argv[1] if len(sys.argv) > 1 else "examples")
    print(json.dumps(extract(box), indent=2))
