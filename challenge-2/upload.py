"""Upload the source document to a transaction's checklist (dropbox) in reZen.

In reZen the per-transaction file storage is the **dropbox** service. Each
submitted transaction can have a dropbox associated to it (created on demand
via arrakis), and files go into that dropbox.

Flow:
  1) POST {arrakis}/api/v1/transactions/{transactionId}/dropbox
       -> returns / creates the dropbox for the transaction.
  2) Look up the dropbox via {dropbox}/api/v1/dropboxes?ownerType=TRANSACTION&ownerId=...
       to get its dropboxId.
  3) POST {dropbox}/api/v1/dropboxes/{dropboxId}/files (multipart) with the file.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests

ENV = os.environ.get("DRAFT_TX_ENV", "team2")
ARRAKIS_BASE = f"https://arrakis.{ENV}realbrokerage.com"
DROPBOX_BASE = f"https://dropbox.{ENV}realbrokerage.com"


def _content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "application/octet-stream")


def ensure_dropbox(token: str, transaction_id: str, email_hint: str = "pwadmin") -> str:
    """Create-or-fetch the dropbox tied to a transaction and return its id."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "name": f"transaction-{transaction_id}",
        "owner": {"id": transaction_id, "type": "TRANSACTION"},
        "emailHint": email_hint,
    }
    r = requests.post(
        f"{ARRAKIS_BASE}/api/v1/transactions/{transaction_id}/dropbox",
        headers=headers,
        json=body,
        timeout=20,
    )
    if r.status_code < 400:
        try:
            data = r.json()
            for key in ("id", "dropboxId", "newDropboxId"):
                if key in data and data[key]:
                    return data[key]
        except (ValueError, AttributeError):
            pass

    # Fallback: list dropboxes for this owner.
    r = requests.get(
        f"{DROPBOX_BASE}/api/v1/dropboxes",
        params={"ownerType": "TRANSACTION", "ownerId": transaction_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    items = data if isinstance(data, list) else data.get("results") or data.get("items") or []
    if not items:
        raise RuntimeError(
            f"No dropbox found for transaction {transaction_id}. Last create attempt: "
            f"{r.status_code} {r.text[:200]}"
        )
    return items[0]["id"]


DEFAULT_UPLOADER_ID = os.environ.get(
    "UPLOADER_ID", "767fbf84-afbf-4346-aad0-5e262259c657"
)


def upload_file(token: str, dropbox_id: str, path: Path, uploaded_by: str = DEFAULT_UPLOADER_ID) -> dict:
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    files = {
        "file": (path.name, path.read_bytes(), _content_type_for(path)),
        "filename": (None, path.name),
        "uploadedBy": (None, uploaded_by),
        "description": (None, f"Source document: {path.name}"),
    }
    r = requests.post(
        f"{DROPBOX_BASE}/api/v1/dropboxes/{dropbox_id}/files",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"file upload -> {r.status_code}: {r.text[:1500]}")
    return r.json() if r.text else {}


def upload_to_checklist(token: str, transaction_id: str, path: Path) -> dict:
    dropbox_id = ensure_dropbox(token, transaction_id)
    uploaded = upload_file(token, dropbox_id, path)
    return {
        "dropboxId": dropbox_id,
        "fileId": uploaded.get("id") or uploaded.get("fileId"),
        "filename": path.name,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: upload.py <transactionId> <path-to-doc>")
    from create import get_token

    out = upload_to_checklist(get_token(), sys.argv[1], Path(sys.argv[2]))
    print(json.dumps(out, indent=2))
