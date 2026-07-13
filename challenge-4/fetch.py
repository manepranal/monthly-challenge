"""Load the agent's inbox for a deal — the raw material the rest of the agent
organizes.

A real deployment would pull these straight from Gmail (see CLAUDE.md for the
live-MCP path). For a portable, reproducible demo we read a fixtures folder that
mirrors the same shape: an `inbox.json` describing the messages plus the actual
attachment files sitting next to it.

`load_inbox()` returns a normalized dict:

    {
      "deal":   {...},                      # the deal this inbox belongs to
      "emails": [
        {
          "id", "from", "to", "date", "subject", "body",
          "attachments": [ {"filename", "path", "text"} ]   # text extracted
        }, ...
      ]
    }

The extracted `text` is what Claude reads to classify and to pull dates from; the
`path` (a real PDF) is what actually gets filed.
"""

import json
import sys
from pathlib import Path


def _extract_text(path: Path) -> str:
    """Best-effort text for an attachment. Reads the PDF; if that yields nothing
    (or pypdf is unavailable), falls back to a same-named .txt sidecar so the
    demo never breaks on extraction."""
    text = ""
    if path.suffix.lower() == ".pdf" and path.exists():
        try:
            import pypdf

            reader = pypdf.PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            text = ""
    elif path.suffix.lower() in (".txt", ".md") and path.exists():
        text = path.read_text(errors="replace")

    if not text.strip():
        sidecar = path.with_suffix(".txt")
        if sidecar.exists():
            text = sidecar.read_text(errors="replace")
    return text.strip()


def load_inbox(source: str) -> dict:
    """Load an inbox from a fixtures folder (containing inbox.json + attachments/)
    or directly from an inbox.json path."""
    src = Path(source)
    if src.is_dir():
        inbox_path = src / "inbox.json"
    else:
        inbox_path = src
    if not inbox_path.exists():
        raise FileNotFoundError(f"No inbox.json found at {inbox_path}")

    root = inbox_path.parent
    attach_dir = root / "attachments"
    data = json.loads(inbox_path.read_text())

    for email in data.get("emails", []):
        enriched = []
        for name in email.get("attachments", []):
            path = attach_dir / name
            enriched.append(
                {
                    "filename": name,
                    "path": str(path),
                    "text": _extract_text(path),
                }
            )
        email["attachments"] = enriched
    return data


def attachment_count(inbox: dict) -> int:
    return sum(len(e.get("attachments", [])) for e in inbox.get("emails", []))


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "examples"
    box = load_inbox(src)
    print(f"Deal: {box['deal']['property']}")
    print(f"Emails: {len(box['emails'])}  Attachments: {attachment_count(box)}")
    for e in box["emails"]:
        atts = ", ".join(a["filename"] for a in e["attachments"]) or "(none)"
        print(f"  - [{e['id']}] {e['subject']}  ->  {atts}")
