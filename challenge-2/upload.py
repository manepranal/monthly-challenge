"""Upload the source document to a transaction's checklist in reZen.

Modern (V2) checklists separate file storage from checklist references:

  1) The file is stored in the transaction's **dropbox** (storage backend).
  2) A **file-reference** is added on a specific **checklist item** so the file
     shows up under that item in bolt's "Checklist" tab.

Flow:
  1) GET  {arrakis}/api/v1/transactions/{transactionId}        -> read checklistId, dropboxId
  2) POST {dropbox}/api/v1/dropboxes/{dropboxId}/files          -> upload file, returns fileId
  3) GET  {sherlock}/api/v1/checklists/{checklistId}            -> list items
  4) Pick an item by name keyword (contract / listing) — fall back to first item.
  5) POST {sherlock}/api/v1/checklists/checklist-items/{itemId}/file-references
        body: {"references": [{"fileId": ..., "filename": ...}]}
"""

import json
import os
import sys
from pathlib import Path

import requests

ENV = os.environ.get("DRAFT_TX_ENV", "team2")
ARRAKIS_BASE = f"https://arrakis.{ENV}realbrokerage.com"
DROPBOX_BASE = f"https://dropbox.{ENV}realbrokerage.com"
SHERLOCK_BASE = f"https://sherlock.{ENV}realbrokerage.com"

DEFAULT_UPLOADER_ID = os.environ.get(
    "UPLOADER_ID", "767fbf84-afbf-4346-aad0-5e262259c657"
)

CONTRACT_KEYWORDS = ("purchase contract", "purchase agreement", "contract")
LISTING_KEYWORDS = ("listing agreement", "listing")


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


def get_transaction(token: str, transaction_id: str) -> dict:
    r = requests.get(
        f"{ARRAKIS_BASE}/api/v1/transactions/{transaction_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def get_checklist(token: str, checklist_id: str) -> dict:
    r = requests.get(
        f"{SHERLOCK_BASE}/api/v1/checklists/{checklist_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def pick_checklist_item(checklist: dict, doc_type: str) -> dict:
    items = checklist.get("items") or []
    if not items:
        raise RuntimeError(
            f"Checklist {checklist.get('id')} has no items; cannot upload."
        )
    keywords = LISTING_KEYWORDS if doc_type == "listing" else CONTRACT_KEYWORDS
    for item in items:
        name = (item.get("name") or "").lower()
        if any(kw in name for kw in keywords):
            return item
    return items[0]


def upload_file_to_dropbox(
    token: str, dropbox_id: str, path: Path, uploaded_by: str = DEFAULT_UPLOADER_ID
) -> dict:
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
        raise RuntimeError(f"dropbox upload -> {r.status_code}: {r.text[:1500]}")
    return r.json() if r.text else {}


def add_file_reference(
    token: str, item_id: str, file_id: str, filename: str
) -> dict:
    body = {"references": [{"fileId": file_id, "filename": filename}]}
    r = requests.post(
        f"{SHERLOCK_BASE}/api/v1/checklists/checklist-items/{item_id}/file-references",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(
            f"sherlock file-references -> {r.status_code}: {r.text[:1500]}"
        )
    return r.json() if r.text else {}


def upload_to_checklist(
    token: str, transaction_id: str, path: Path, doc_type: str = "contract"
) -> dict:
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    tx = get_transaction(token, transaction_id)
    checklist_id = tx.get("checklistId")
    dropbox_id = tx.get("dropboxId")
    if not checklist_id or not dropbox_id:
        raise RuntimeError(
            f"Transaction {transaction_id} missing checklistId/dropboxId — was it submitted?"
        )

    file_response = upload_file_to_dropbox(token, dropbox_id, path)
    file_id = file_response.get("id") or file_response.get("fileId")
    if not file_id:
        raise RuntimeError(f"dropbox upload returned no fileId: {file_response}")

    checklist = get_checklist(token, checklist_id)
    item = pick_checklist_item(checklist, doc_type)
    add_file_reference(token, item["id"], file_id, path.name)

    return {
        "checklistId": checklist_id,
        "dropboxId": dropbox_id,
        "fileId": file_id,
        "checklistItemId": item["id"],
        "checklistItemName": item.get("name"),
        "filename": path.name,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(
            "Usage: upload.py <transactionId> <path-to-doc> [contract|listing]"
        )
    from create import get_token

    doc_type = sys.argv[3] if len(sys.argv) > 3 else "contract"
    out = upload_to_checklist(get_token(), sys.argv[1], Path(sys.argv[2]), doc_type)
    print(json.dumps(out, indent=2))
