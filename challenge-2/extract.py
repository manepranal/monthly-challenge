"""Extract structured fields from a contract or listing-agreement PDF/image via the Claude API.

Demonstrates Claude API **vision / document** input + **tool use**:
- PDFs go in as a `document` content block.
- Images (jpg/png) go in as an `image` content block.
- The model is forced to answer through one of two typed tools so downstream
  code can rely on the shape instead of writing a free-text JSON parser.
"""

import base64
import json
import sys
from pathlib import Path

import anthropic

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
            "salePrice": {"type": "number", "description": "Sale price in USD."},
            "contractDate": {"type": "string", "description": "ISO date the contract was signed."},
            "closingDate": {"type": "string", "description": "ISO expected/agreed closing date."},
            "buyer": PARTY_SCHEMA,
            "seller": PARTY_SCHEMA,
            "commissionPercent": {
                "type": "number",
                "description": "Buyer-side commission percent if stated; otherwise omit.",
            },
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
            "listPrice": {"type": "number", "description": "List price in USD."},
            "listingDate": {"type": "string", "description": "ISO date the listing began."},
            "expirationDate": {"type": "string", "description": "ISO listing expiration date."},
            "seller": PARTY_SCHEMA,
            "mlsNumber": {"type": "string"},
            "commissionPercent": {
                "type": "number",
                "description": "Listing-side commission percent if stated; otherwise omit.",
            },
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


def extract_document(path: Path) -> tuple[str, dict]:
    """Return (doc_type, fields). doc_type is 'contract' or 'listing'."""
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

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

    raise RuntimeError(
        f"Claude did not call either extraction tool. Response: {response}"
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: extract.py <path-to-pdf-or-image>")
    doc_type, fields = extract_document(Path(sys.argv[1]))
    print(json.dumps({"docType": doc_type, "fields": fields}, indent=2))
