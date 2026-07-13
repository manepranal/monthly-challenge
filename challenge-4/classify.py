"""AI job #1 — read the whole inbox and decide (a) where each attachment should
be filed and (b) what still needs a human follow-up.

A single forced `tool_use` call turns a messy inbox into a typed plan the filer
can execute without parsing prose. The model classifies each attachment into a
fixed set of categories and routes it to one of a fixed set of destination
folders (an enum, so routing is deterministic), and separately surfaces
action items from messages that ask the agent to do something.

The destination taxonomy is the domain rule in
`.claude/skills/file-documents.md`.
"""

import json
import os
import sys
from pathlib import Path

CLAUDE_MODEL = os.environ.get("DEAL_MODEL", "claude-sonnet-5")

DESTINATIONS = [
    "Contracts & Agreements",
    "Inspections",
    "Financing & Appraisal",
    "Accounting & Commissions",
    "Disclosures",
    "Correspondence",
]

CATEGORIES = [
    "Contract",
    "Inspection Report",
    "Appraisal",
    "Commission Statement",
    "Disclosure",
    "Correspondence",
    "Other",
]

SYSTEM_PROMPT = """You are a transaction coordinator's filing assistant for a real-estate agent.
You are given every email in the inbox for ONE deal, including the text of each
attachment. Your job is to get the deal organized.

Do two things:

1. FILE every attachment. For each attachment, choose the single best `category`
   and route it to exactly one `destination` folder from the allowed list. Use
   the document's own content, not just its filename. Routing rules:
     - Purchase/sale agreements, contracts, amendments  -> "Contracts & Agreements"
     - Home/pest/radon inspection reports                -> "Inspections"
     - Appraisals, mortgage/financing paperwork          -> "Financing & Appraisal"
     - Commission statements, CDAs, invoices, payouts    -> "Accounting & Commissions"
     - Seller disclosures, lead-paint, HOA docs          -> "Disclosures"
     - Anything that is really just a letter/message      -> "Correspondence"

2. SURFACE action items. Scan the messages for anything that needs the agent to
   DO something (reply to a client, share a document by a deadline, send a doc to
   title, etc.). Do not invent tasks; only include ones grounded in a message.
   Give each a priority and, if the message implies timing, a short `due_hint`.

Always answer by calling the organize_inbox tool. Never reply in plain text.
"""

ORGANIZE_TOOL = {
    "name": "organize_inbox",
    "description": "The filing plan and follow-up list for one deal's inbox.",
    "input_schema": {
        "type": "object",
        "properties": {
            "filings": {
                "type": "array",
                "description": "One entry per attachment to be filed.",
                "items": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string"},
                        "category": {"type": "string", "enum": CATEGORIES},
                        "destination": {"type": "string", "enum": DESTINATIONS},
                        "confidence": {
                            "type": "number",
                            "description": "0.0-1.0 confidence in the routing.",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "One short clause on why it goes there.",
                        },
                    },
                    "required": [
                        "filename",
                        "category",
                        "destination",
                        "confidence",
                        "reasoning",
                    ],
                },
            },
            "action_items": {
                "type": "array",
                "description": "Follow-ups the agent still needs to do.",
                "items": {
                    "type": "object",
                    "properties": {
                        "email_id": {"type": "string"},
                        "task": {"type": "string"},
                        "priority": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                        "due_hint": {
                            "type": "string",
                            "description": "Short timing hint, or empty string.",
                        },
                    },
                    "required": ["email_id", "task", "priority", "due_hint"],
                },
            },
        },
        "required": ["filings", "action_items"],
    },
}


def _inbox_for_prompt(inbox: dict) -> str:
    """Compact, model-friendly view: deal facts + each email with attachment
    filename and a text preview."""
    view = {"deal": inbox.get("deal", {}), "emails": []}
    for e in inbox.get("emails", []):
        view["emails"].append(
            {
                "id": e.get("id"),
                "from": e.get("from"),
                "date": e.get("date"),
                "subject": e.get("subject"),
                "body": (e.get("body") or "")[:800],
                "attachments": [
                    {
                        "filename": a["filename"],
                        "text_preview": (a.get("text") or "")[:700],
                    }
                    for a in e.get("attachments", [])
                ],
            }
        )
    return json.dumps(view, indent=2)


def _via_sdk(inbox: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        tools=[ORGANIZE_TOOL],
        tool_choice={"type": "tool", "name": "organize_inbox"},
        messages=[
            {
                "role": "user",
                "content": "Organize this deal's inbox:\n\n" + _inbox_for_prompt(inbox),
            }
        ],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "organize_inbox":
            return block.input
    raise RuntimeError(f"Claude did not call organize_inbox. Response: {response}")


CLI_PROMPT = """You are a real-estate transaction coordinator's filing assistant. Given the
inbox JSON below (emails + attachment text for one deal), produce a filing plan.

For each attachment choose a `category` from {categories} and a `destination`
folder from {destinations} based on the document content. Also list `action_items`
for anything a message asks the agent to do (do not invent tasks).

Inbox:
{inbox}

Return ONLY this JSON on stdout — no prose, no markdown fences:
{{
  "filings": [
    {{"filename": "...", "category": "...", "destination": "...", "confidence": 0.9, "reasoning": "..."}}
  ],
  "action_items": [
    {{"email_id": "...", "task": "...", "priority": "high", "due_hint": "..."}}
  ]
}}"""


def _via_cli(inbox: dict) -> dict:
    from claude_cli import run_cli_json

    return run_cli_json(
        CLI_PROMPT.format(
            categories=CATEGORIES,
            destinations=DESTINATIONS,
            inbox=_inbox_for_prompt(inbox),
        )
    )


def organize(inbox: dict) -> dict:
    """Return {filings, action_items}. Prefer SDK; fall back to CLI on auth failure."""
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
    print(json.dumps(organize(box), indent=2))
