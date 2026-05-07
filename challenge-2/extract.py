from __future__ import annotations

"""Extract structured fields from a contract or listing-agreement PDF/image.

Two backends, picked at runtime:

1) **Anthropic SDK (preferred)** — direct Claude API call with vision/document
   blocks and `tool_use` to coerce structured output. Requires a working
   `ANTHROPIC_API_KEY`.

2) **`claude` CLI fallback** — when the env key is missing/invalid we shell
   out to Claude Code (`claude -p ... --output-format json`) which uses its
   own OAuth credentials. The CLI reads the file via its built-in Read tool
   and returns JSON. Tool-use isn't available through the CLI, so we constrain
   output via prompt + JSON-mode and parse the result.

The fallback lets the demo run end-to-end even when the SDK key is rotated.
"""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

CLAUDE_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You read real-estate documents and extract structured fields for reZen.

Two document types:
  - CONTRACT (purchase agreement / buyer's contract): use the extract_contract tool.
  - LISTING (listing agreement / seller's listing): use the extract_listing tool.

Decide which tool to use from the document itself. If it talks about the SELLER engaging
a broker to MARKET / LIST a property -> listing. If it talks about a BUYER agreeing to
PURCHASE a property at a sale price -> contract. When unclear, prefer contract.

Rules:
- US states must be returned in arrakis enum form: all caps with underscores.
  "New York" -> "NEW_YORK", "New Jersey" -> "NEW_JERSEY", "Texas" -> "TEXAS".
- Dates must be ISO format (YYYY-MM-DD).
- Money values are numeric USD amounts (no $ or commas).
- If a field is genuinely missing from the document, omit it rather than fabricating.
- Always answer through one of the two tools. Never reply in plain text.
"""

ADDRESS_SCHEMA = {
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
}

PARTY_SCHEMA = {
    "type": "object",
    "properties": {
        "firstName": {"type": "string"},
        "lastName": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
    },
    "required": ["firstName", "lastName"],
}

CONTRACT_TOOL = {
    "name": "extract_contract",
    "description": "Extract fields from a real-estate purchase contract.",
    "input_schema": {
        "type": "object",
        "properties": {
            "address": ADDRESS_SCHEMA,
            "salePrice": {"type": "number"},
            "contractDate": {"type": "string"},
            "closingDate": {"type": "string"},
            "buyer": PARTY_SCHEMA,
            "seller": PARTY_SCHEMA,
            "commissionPercent": {"type": "number"},
        },
        "required": ["address", "salePrice", "contractDate", "closingDate", "buyer", "seller"],
    },
}

LISTING_TOOL = {
    "name": "extract_listing",
    "description": "Extract fields from a real-estate listing agreement.",
    "input_schema": {
        "type": "object",
        "properties": {
            "address": ADDRESS_SCHEMA,
            "listPrice": {"type": "number"},
            "listingDate": {"type": "string"},
            "expirationDate": {"type": "string"},
            "seller": PARTY_SCHEMA,
            "mlsNumber": {"type": "string"},
            "commissionPercent": {"type": "number"},
        },
        "required": ["address", "listPrice", "listingDate", "expirationDate", "seller"],
    },
}

MEDIA_TYPES = {
    ".pdf": ("document", "application/pdf"),
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
    ".gif": ("image", "image/gif"),
}


def _build_doc_block(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix not in MEDIA_TYPES:
        raise SystemExit(
            f"Unsupported file type {suffix!r}. Supported: {', '.join(MEDIA_TYPES)}"
        )
    block_type, media_type = MEDIA_TYPES[suffix]
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
    return {
        "type": block_type,
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def _extract_via_sdk(path: Path) -> tuple[str, dict]:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[CONTRACT_TOOL, LISTING_TOOL],
        tool_choice={"type": "any"},
        messages=[
            {
                "role": "user",
                "content": [
                    _build_doc_block(path),
                    {
                        "type": "text",
                        "text": "Extract the relevant fields by calling either extract_contract or extract_listing.",
                    },
                ],
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_contract":
            return "contract", block.input
        if block.type == "tool_use" and block.name == "extract_listing":
            return "listing", block.input

    raise RuntimeError(f"Claude did not call either extraction tool. Response: {response}")


CLI_PROMPT = """Read the file at {path} and extract real-estate transaction fields.

Decide if it is a CONTRACT (purchase / buyer side) or a LISTING (listing agreement / seller side).

Return ONLY a single JSON object on stdout, with this exact shape — no prose, no markdown fences:

For a contract:
{{
  "docType": "contract",
  "fields": {{
    "address": {{"street": "...", "city": "...", "state": "<ARRAKIS_ENUM>", "zip": "..."}},
    "salePrice": <number>,
    "contractDate": "YYYY-MM-DD",
    "closingDate": "YYYY-MM-DD",
    "buyer":  {{"firstName": "...", "lastName": "...", "email": "...", "phone": "..."}},
    "seller": {{"firstName": "...", "lastName": "...", "email": "...", "phone": "..."}},
    "commissionPercent": <number>
  }}
}}

For a listing:
{{
  "docType": "listing",
  "fields": {{
    "address": {{"street": "...", "city": "...", "state": "<ARRAKIS_ENUM>", "zip": "..."}},
    "listPrice": <number>,
    "listingDate": "YYYY-MM-DD",
    "expirationDate": "YYYY-MM-DD",
    "seller": {{"firstName": "...", "lastName": "...", "email": "...", "phone": "..."}},
    "mlsNumber": "...",
    "commissionPercent": <number>
  }}
}}

Rules:
- US state must be ALL_CAPS_WITH_UNDERSCORES (e.g. NEW_YORK, NEW_JERSEY).
- Dates are ISO YYYY-MM-DD.
- Money values are plain numbers (no $ or commas).
- Omit any field genuinely missing from the document — do NOT invent.
- Output the JSON only. No explanations."""


def _extract_via_cli(path: Path) -> tuple[str, dict]:
    """Fallback: invoke Claude Code CLI which uses OAuth (no env API key needed)."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    cmd = [
        "claude",
        "-p",
        CLI_PROMPT.format(path=str(path)),
        "--output-format",
        "json",
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, env=env, timeout=180, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {proc.returncode} {proc.stderr[:500]}")

    cli_output = json.loads(proc.stdout)
    if cli_output.get("is_error"):
        raise RuntimeError(f"claude CLI error: {cli_output.get('result')}")

    raw = (cli_output.get("result") or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    payload = json.loads(raw)
    return payload["docType"], payload["fields"]


def extract_document(path: Path) -> tuple[str, dict]:
    """Return (doc_type, fields). Prefer SDK; fall back to CLI on auth failure."""
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    try:
        return _extract_via_sdk(path)
    except Exception as e:
        msg = str(e).lower()
        if "401" in msg or "auth" in msg or "api key" in msg or "x-api-key" in msg:
            print(
                f"  (SDK auth failed — falling back to claude CLI)",
                file=sys.stderr,
            )
            return _extract_via_cli(path)
        raise


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: extract.py <path-to-pdf-or-image>")
    doc_type, fields = extract_document(Path(sys.argv[1]))
    print(json.dumps({"docType": doc_type, "fields": fields}, indent=2))
