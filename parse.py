"""Parse English real-estate prompts into structured JSON via the Claude API.

Demonstrates Claude API **tool use** — the model is forced to answer through a
typed schema (`create_draft_transaction`) so downstream code can rely on the
shape instead of writing a free-text JSON parser.
"""

import json
import sys

import anthropic

CLAUDE_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You parse natural-language descriptions of real-estate deals into structured fields for a transaction-management system.

Rules:
- Every named person who is splitting the commission is a coAgent. Set isMe=true on the entry that refers to "me" / "I".
- People described as a "referral" go in referrals, not coAgents.
- Co-agent splitPercents must sum to 100. Referral percents are independent of that sum.
- US state names must be returned in arrakis enum form, all caps with underscores: "New York" -> "NEW_YORK", "New Jersey" -> "NEW_JERSEY", "Texas" -> "TEXAS".
- representationType defaults to BUYER unless the prompt clearly indicates SELLER, LANDLORD, TENANT, or DUAL.
- Always answer through the create_draft_transaction tool. Never reply in plain text.
"""

TOOL = {
    "name": "create_draft_transaction",
    "description": "Create a draft real-estate transaction from extracted fields.",
    "input_schema": {
        "type": "object",
        "properties": {
            "grossCommission": {
                "type": "number",
                "description": "Gross commission in USD (total commission for the deal, before splits).",
            },
            "representationType": {
                "type": "string",
                "enum": ["BUYER", "SELLER", "DUAL", "LANDLORD", "TENANT"],
            },
            "address": {
                "type": "object",
                "properties": {
                    "street": {"type": "string"},
                    "city": {"type": "string"},
                    "state": {
                        "type": "string",
                        "description": "Arrakis enum form, e.g. NEW_YORK, NEW_JERSEY, TEXAS.",
                    },
                    "zip": {"type": "string"},
                },
                "required": ["street", "city", "state", "zip"],
            },
            "coAgents": {
                "type": "array",
                "description": "Agents on the deal. splitPercent values must sum to 100.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "splitPercent": {"type": "number"},
                        "isMe": {"type": "boolean"},
                    },
                    "required": ["name", "splitPercent", "isMe"],
                },
            },
            "referrals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "splitPercent": {"type": "number"},
                    },
                    "required": ["name", "splitPercent"],
                },
            },
        },
        "required": [
            "grossCommission",
            "representationType",
            "address",
            "coAgents",
            "referrals",
        ],
    },
}


def parse_prompt(prompt: str) -> dict:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "create_draft_transaction"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == "create_draft_transaction":
            return block.input
    raise RuntimeError(f"Claude did not return the expected tool_use block: {response}")


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]).strip() or sys.stdin.read().strip()
    print(json.dumps(parse_prompt(prompt), indent=2))
