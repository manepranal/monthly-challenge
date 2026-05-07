"""Orchestrator: doc -> extract -> create+submit -> upload to dropbox -> print summary."""

import sys
from pathlib import Path

import requests

from create import (
    ENV,
    create_from_contract,
    create_from_listing,
    get_token,
)
from extract import extract_document
from upload import upload_to_checklist


def fmt_money(n: float) -> str:
    return f"${n:,.0f}"


def print_contract(fields: dict) -> None:
    a = fields["address"]
    print("Parsed (contract):")
    print(f"  Address:      {a['street']}, {a['city']}, {a['state']} {a['zip']}")
    print(f"  Sale price:   {fmt_money(fields['salePrice'])}")
    print(f"  Contract:     {fields['contractDate']}")
    print(f"  Closing:      {fields['closingDate']}")
    b = fields["buyer"]
    s = fields["seller"]
    print(f"  Buyer:        {b['firstName']} {b['lastName']}")
    print(f"  Seller:       {s['firstName']} {s['lastName']}")
    if "commissionPercent" in fields:
        print(f"  Commission:   {fields['commissionPercent']}%")


def print_listing(fields: dict) -> None:
    a = fields["address"]
    print("Parsed (listing):")
    print(f"  Address:      {a['street']}, {a['city']}, {a['state']} {a['zip']}")
    print(f"  List price:   {fmt_money(fields['listPrice'])}")
    print(f"  Listing:      {fields['listingDate']}")
    print(f"  Expiration:   {fields['expirationDate']}")
    s = fields["seller"]
    print(f"  Seller:       {s['firstName']} {s['lastName']}")
    if fields.get("mlsNumber"):
        print(f"  MLS:          {fields['mlsNumber']}")
    if "commissionPercent" in fields:
        print(f"  Commission:   {fields['commissionPercent']}%")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: main.py <path-to-contract-or-listing.pdf|.png|.jpg>"
        )
    path = Path(sys.argv[1]).expanduser().resolve()

    print(f"\nReading {path.name} with claude-sonnet-4-6...\n")
    doc_type, fields = extract_document(path)

    if doc_type == "contract":
        print_contract(fields)
        print(f"\nSubmitting transaction (contract) on {ENV}...")
        result = create_from_contract(fields)
    else:
        print_listing(fields)
        print(f"\nSubmitting listing on {ENV}...")
        result = create_from_listing(fields)

    print("\nTransaction submitted")
    print(f"  Type:        {result['docType']}")
    print(f"  Builder ID:  {result['builderId']}")
    print(f"  Tx ID:       {result['transactionId']}")
    print(f"  Bolt URL:    {result['boltUrl']}")

    print(f"\nUploading {path.name} to checklist...")
    token = get_token()
    upload = upload_to_checklist(token, result["transactionId"], path, doc_type)
    print(f"  Checklist:   {upload['checklistId']}")
    print(f"  Item:        {upload['checklistItemName']!r} ({upload['checklistItemId']})")
    print(f"  File ID:     {upload['fileId']}")
    print(f"  ✓ uploaded to checklist item")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(
            f"\nAPI error {e.response.status_code}: {e.response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"\n{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
