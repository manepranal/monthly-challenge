"""Create a fully-submitted transaction (contract) or listing in reZen via the arrakis API.

Builder pattern: create-builder -> populate steps -> submit -> transactionId.
The submitted transactionId is what the dropbox/checklist endpoints attach to.

Steps:
  1) POST /transaction-builder                   -> builderId
  2) PUT  /transaction-builder/{id}/location-info
  3) PUT  /transaction-builder/{id}/owner-info
  4) PUT  /transaction-builder/{id}/price-date-info
  5) PUT  /transaction-builder/{id}/buyer-seller-info
  6) PUT  /transaction-builder/{id}/commission-payer  (multipart)
  7) PUT  /transaction-builder/{id}/personal-deal-info
  8) POST /transaction-builder/{id}/submit       -> transactionId
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests

ENV = os.environ.get("DRAFT_TX_ENV", "team2")
ARRAKIS_BASE = f"https://arrakis.{ENV}realbrokerage.com"
KEYMAKER_BASE = f"https://keymaker.{ENV}realbrokerage.com"
YENTA_BASE = f"https://yenta.{ENV}realbrokerage.com"
BOLT_BASE = f"https://bolt.{ENV}realbrokerage.com"

DEFAULT_AGENT_ID = "767fbf84-afbf-4346-aad0-5e262259c657"
DEFAULT_COMMISSION_PERCENT = 3


def get_token() -> str:
    """Fresh admin token via pwadmin (per memory feedback_token_via_pwadmin)."""
    try:
        r = requests.post(
            f"{KEYMAKER_BASE}/api/v1/auth/signin",
            json={"usernameOrEmail": "pwadmin", "password": "P@ssw0rd"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["accessToken"]
    except Exception:
        token_file = Path.home() / ".bolt-api-token"
        if token_file.exists():
            return token_file.read_text().strip()
        raise


def get_office_id(token: str, agent_id: str, state: str) -> str:
    r = requests.get(
        f"{YENTA_BASE}/api/v1/agents/{agent_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    r.raise_for_status()
    profile = r.json()
    licensed = []
    for office in profile.get("offices", []):
        s = office.get("address", {}).get("stateOrProvince")
        licensed.append(s)
        if s == state:
            return office["id"]
    raise RuntimeError(
        f"Agent {agent_id} not licensed in {state}. Licensed: {licensed}"
    )


def _builder_id_from_response(r: requests.Response) -> str:
    body = r.text.strip().strip('"')
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict) and "id" in parsed:
            return parsed["id"]
    except json.JSONDecodeError:
        pass
    return body


def _create_builder(headers: dict, is_listing: bool) -> str:
    url = f"{ARRAKIS_BASE}/api/v1/transaction-builder"
    if is_listing:
        url += "?type=LISTING"
    r = requests.post(url, headers=headers, timeout=15)
    r.raise_for_status()
    return _builder_id_from_response(r)


def _put(headers: dict, path: str, body: dict) -> None:
    r = requests.put(
        f"{ARRAKIS_BASE}{path}", headers=headers, json=body, timeout=15
    )
    if r.status_code >= 400:
        raise RuntimeError(f"PUT {path} -> {r.status_code}: {r.text}")


def _put_location(headers, builder_id, addr, mls):
    _put(
        headers,
        f"/api/v1/transaction-builder/{builder_id}/location-info",
        {
            "street": addr["street"],
            "city": addr["city"],
            "state": addr["state"],
            "zip": addr["zip"],
            "yearBuilt": 2000,
            "mlsNumber": mls or "DRAFT-DEMO",
        },
    )


def _put_owner(headers, builder_id, agent_id, office_id):
    _put(
        headers,
        f"/api/v1/transaction-builder/{builder_id}/owner-info",
        {
            "ownerAgent": {"agentId": agent_id, "role": "REAL"},
            "officeId": office_id,
        },
    )


def _put_price_date(headers, builder_id, body):
    _put(headers, f"/api/v1/transaction-builder/{builder_id}/price-date-info", body)


def _put_buyer_seller(headers, builder_id, buyers, sellers):
    body = {
        "buyers": [
            {
                "firstName": b["firstName"],
                "lastName": b["lastName"],
                "email": b.get("email", ""),
                "phoneNumber": b.get("phone", ""),
            }
            for b in (buyers or [])
        ],
        "sellers": [
            {
                "firstName": s["firstName"],
                "lastName": s["lastName"],
                "email": s.get("email", ""),
                "phoneNumber": s.get("phone", ""),
            }
            for s in (sellers or [])
        ],
    }
    _put(headers, f"/api/v1/transaction-builder/{builder_id}/buyer-seller-info", body)


def _put_commission_payer(headers_no_ct, builder_id, role, party):
    """commission-payer accepts multipart/form-data."""
    full_name = f"{party['firstName']} {party['lastName']}".strip()
    fields = {
        "role": (None, role),
        "firstName": (None, party["firstName"]),
        "lastName": (None, party["lastName"]),
        "companyName": (None, full_name),
        "email": (None, party.get("email", "")),
        "phoneNumber": (None, party.get("phone", "")),
        "receivesInvoice": (None, "false"),
    }
    r = requests.put(
        f"{ARRAKIS_BASE}/api/v1/transaction-builder/{builder_id}/commission-payer",
        headers=headers_no_ct,
        files=fields,
        timeout=15,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"PUT /commission-payer -> {r.status_code}: {r.text}")


def _put_personal_deal(headers, builder_id):
    _put(
        headers,
        f"/api/v1/transaction-builder/{builder_id}/personal-deal-info",
        {"personalDeal": False, "representedByAgent": False},
    )


def _put_commission_splits(headers, builder_id, splits):
    r = requests.put(
        f"{ARRAKIS_BASE}/api/v1/transaction-builder/{builder_id}/commission-info",
        headers=headers,
        json=splits,
        timeout=15,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"PUT /commission-info -> {r.status_code}: {r.text}")


def _get_builder(headers, builder_id) -> dict:
    r = requests.get(
        f"{ARRAKIS_BASE}/api/v1/transaction-builder/{builder_id}",
        headers=headers,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _owner_participant_id(builder: dict, agent_id: str) -> str:
    for p in builder.get("allParticipants") or []:
        if p.get("yentaId") == agent_id or p.get("agentId") == agent_id or p.get("id") == agent_id:
            return p["id"]
    # fall back to first participant
    parts = builder.get("allParticipants") or []
    if parts:
        return parts[0]["id"]
    raise RuntimeError("No participants found on builder; cannot set commission split.")


def _submit(headers, builder_id) -> str:
    r = requests.post(
        f"{ARRAKIS_BASE}/api/v1/transaction-builder/{builder_id}/submit",
        headers=headers,
        timeout=60,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"POST /submit -> {r.status_code}: {r.text}")
    body = r.json() if r.text else {}
    return body.get("id") or body.get("transactionId") or body.get("transaction", {}).get("id")


def _build_common(fields: dict, is_listing: bool, agent_id: str):
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    headers_no_ct = {"Authorization": f"Bearer {token}"}

    addr = fields["address"]
    office_id = get_office_id(token, agent_id, addr["state"])
    builder_id = _create_builder(headers, is_listing=is_listing)
    _put_location(headers, builder_id, addr, fields.get("mlsNumber"))
    _put_owner(headers, builder_id, agent_id, office_id)
    return token, headers, headers_no_ct, office_id, builder_id


def create_from_contract(fields: dict, agent_id: str = DEFAULT_AGENT_ID, submit: bool = True) -> dict:
    token, headers, headers_no_ct, office_id, builder_id = _build_common(
        fields, is_listing=False, agent_id=agent_id
    )

    sale_price = round(fields["salePrice"])
    commission_pct = fields.get("commissionPercent", DEFAULT_COMMISSION_PERCENT)

    _put_price_date(
        headers,
        builder_id,
        {
            "dealType": "SALE",
            "representationType": "BUYER",
            "salePrice": {"amount": sale_price, "currency": "USD"},
            "saleCommission": {
                "commissionPercent": commission_pct,
                "percentEnabled": True,
            },
            "closingDate": fields["closingDate"],
        },
    )

    result = {
        "docType": "contract",
        "builderId": builder_id,
        "transactionId": builder_id,
        "boltUrl": f"{BOLT_BASE}/transactions/drafts/{builder_id}",
        "officeId": office_id,
        "agentId": agent_id,
        "salePrice": sale_price,
        "commissionPercent": commission_pct,
        "env": ENV,
        "submitted": False,
    }

    if not submit:
        return result

    _put_buyer_seller(headers, builder_id, [fields["buyer"]], [fields["seller"]])
    # Buyer-rep deal: seller pays the buyer's broker commission.
    _put_commission_payer(headers_no_ct, builder_id, "SELLER", fields["seller"])
    _put_personal_deal(headers, builder_id)

    builder = _get_builder(headers, builder_id)
    participant_id = _owner_participant_id(builder, agent_id)
    _put_commission_splits(
        headers,
        builder_id,
        [
            {
                "participantId": participant_id,
                "commission": {"commissionPercent": 100, "percentEnabled": True},
            }
        ],
    )

    transaction_id = _submit(headers, builder_id)
    if not transaction_id:
        raise RuntimeError("submit succeeded but response had no transactionId")

    result["transactionId"] = transaction_id
    result["submitted"] = True
    result["boltUrl"] = f"{BOLT_BASE}/transactions/{transaction_id}"
    return result


def create_from_listing(fields: dict, agent_id: str = DEFAULT_AGENT_ID, submit: bool = True) -> dict:
    token, headers, headers_no_ct, office_id, builder_id = _build_common(
        fields, is_listing=True, agent_id=agent_id
    )

    list_price = round(fields["listPrice"])
    commission_pct = fields.get("commissionPercent", DEFAULT_COMMISSION_PERCENT)
    listing_date = fields["listingDate"]
    expiration_date = fields.get("expirationDate") or (
        date.today() + timedelta(days=365)
    ).isoformat()

    _put_price_date(
        headers,
        builder_id,
        {
            "dealType": "SALE",
            "representationType": "SELLER",
            "salePrice": {"amount": list_price, "currency": "USD"},
            "saleCommission": {
                "commissionPercent": commission_pct,
                "percentEnabled": True,
            },
            "listingCommission": {
                "commissionPercent": commission_pct,
                "percentEnabled": True,
            },
            "listingDate": listing_date,
            "listingExpirationDate": expiration_date,
            "closingDate": expiration_date,
        },
    )

    result = {
        "docType": "listing",
        "builderId": builder_id,
        "transactionId": builder_id,
        "boltUrl": f"{BOLT_BASE}/transactions/drafts/{builder_id}",
        "officeId": office_id,
        "agentId": agent_id,
        "listPrice": list_price,
        "commissionPercent": commission_pct,
        "listingDate": listing_date,
        "expirationDate": expiration_date,
        "env": ENV,
        "submitted": False,
    }

    if not submit:
        return result

    # For a listing-side deal, only the seller is required.
    _put_buyer_seller(headers, builder_id, [], [fields["seller"]])
    # Listing-side: seller pays commission.
    _put_commission_payer(headers_no_ct, builder_id, "SELLER", fields["seller"])
    _put_personal_deal(headers, builder_id)

    builder = _get_builder(headers, builder_id)
    participant_id = _owner_participant_id(builder, agent_id)
    _put_commission_splits(
        headers,
        builder_id,
        [
            {
                "participantId": participant_id,
                "commission": {"commissionPercent": 100, "percentEnabled": True},
            }
        ],
    )

    transaction_id = _submit(headers, builder_id)
    if not transaction_id:
        raise RuntimeError("submit succeeded but response had no transactionId")

    result["transactionId"] = transaction_id
    result["submitted"] = True
    result["boltUrl"] = f"{BOLT_BASE}/transactions/{transaction_id}"
    return result


if __name__ == "__main__":
    payload = json.loads(sys.stdin.read())
    doc_type = payload["docType"]
    fields = payload["fields"]
    submit = os.environ.get("SUBMIT", "1") != "0"
    if doc_type == "contract":
        print(json.dumps(create_from_contract(fields, submit=submit), indent=2))
    elif doc_type == "listing":
        print(json.dumps(create_from_listing(fields, submit=submit), indent=2))
    else:
        raise SystemExit(f"Unknown docType: {doc_type}")
