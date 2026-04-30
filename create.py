"""Create a draft transaction on arrakis from parsed fields.

A "draft" is a transaction-builder that has been populated with location, owner,
and price/commission info but has *not* been submitted. It shows up in bolt's
draft list and can be opened/edited there.

The submit step (`POST /transaction-builder/{id}/submit`) is intentionally
skipped — that is what keeps the result a draft.
"""

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

ENV = os.environ.get("DRAFT_TX_ENV", "team2")
ARRAKIS_BASE = f"https://arrakis.{ENV}realbrokerage.com"
KEYMAKER_BASE = f"https://keymaker.{ENV}realbrokerage.com"
YENTA_BASE = f"https://yenta.{ENV}realbrokerage.com"
BOLT_BASE = f"https://bolt.{ENV}realbrokerage.com"

DEFAULT_AGENT_ID = "767fbf84-afbf-4346-aad0-5e262259c657"
DEFAULT_COMMISSION_PERCENT = 3


def get_token() -> str:
    """Fresh admin token via pwadmin login (preferred, per memory feedback_token_via_pwadmin).
    Falls back to ~/.bolt-api-token if keymaker is unreachable."""
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
        f"Agent {agent_id} not licensed in {state}. Licensed states: {licensed}"
    )


def _builder_id_from_response(r: requests.Response) -> str:
    """create-builder may return JSON {id: ...} or a plain UUID string. Handle both."""
    body = r.text.strip().strip('"')
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict) and "id" in parsed:
            return parsed["id"]
    except json.JSONDecodeError:
        pass
    return body


def create_draft(data: dict, agent_id: str = DEFAULT_AGENT_ID) -> dict:
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    addr = data["address"]
    state = addr["state"]
    rep_type = data["representationType"]
    is_listing_side = rep_type in ("SELLER", "LANDLORD")

    office_id = get_office_id(token, agent_id, state)

    # 1) Create empty builder
    create_url = f"{ARRAKIS_BASE}/api/v1/transaction-builder"
    if is_listing_side:
        create_url += "?type=LISTING"
    r = requests.post(create_url, headers=headers, timeout=15)
    r.raise_for_status()
    builder_id = _builder_id_from_response(r)

    # 2) Location-info — must come before owner-info
    location_body = {
        "street": addr["street"],
        "city": addr["city"],
        "state": state,
        "zip": addr["zip"],
        "yearBuilt": 2000,
        "mlsNumber": "DRAFT-DEMO",
    }
    r = requests.put(
        f"{ARRAKIS_BASE}/api/v1/transaction-builder/{builder_id}/location-info",
        headers=headers,
        json=location_body,
        timeout=15,
    )
    r.raise_for_status()

    # 3) Owner-info — ownerAgent.role MUST be "REAL" (omitting causes NPE server-side)
    owner_body = {
        "ownerAgent": {"agentId": agent_id, "role": "REAL"},
        "officeId": office_id,
    }
    r = requests.put(
        f"{ARRAKIS_BASE}/api/v1/transaction-builder/{builder_id}/owner-info",
        headers=headers,
        json=owner_body,
        timeout=15,
    )
    r.raise_for_status()

    # 4) Price + commission — back-compute salePrice so 3% ≈ grossCommission
    sale_price = round(data["grossCommission"] / (DEFAULT_COMMISSION_PERCENT / 100))
    closing_date = (date.today() + timedelta(days=180)).isoformat()

    deal_type = "LEASE" if rep_type in ("TENANT", "LANDLORD") else "SALE"
    price_body = {
        "dealType": deal_type,
        "representationType": rep_type,
        "salePrice": {"amount": sale_price, "currency": "USD"},
        "saleCommission": {
            "commissionPercent": DEFAULT_COMMISSION_PERCENT,
            "percentEnabled": True,
        },
        "closingDate": closing_date,
    }
    if is_listing_side:
        price_body["listingCommission"] = {
            "commissionPercent": DEFAULT_COMMISSION_PERCENT,
            "percentEnabled": True,
        }
        price_body["listingDate"] = date.today().isoformat()
        price_body["listingExpirationDate"] = (date.today() + timedelta(days=365)).isoformat()

    r = requests.put(
        f"{ARRAKIS_BASE}/api/v1/transaction-builder/{builder_id}/price-date-info",
        headers=headers,
        json=price_body,
        timeout=15,
    )
    r.raise_for_status()

    return {
        "transactionId": builder_id,
        "boltUrl": f"{BOLT_BASE}/transactions/drafts/{builder_id}",
        "officeId": office_id,
        "agentId": agent_id,
        "salePrice": sale_price,
        "commissionPercent": DEFAULT_COMMISSION_PERCENT,
        "env": ENV,
    }


if __name__ == "__main__":
    parsed = json.loads(sys.stdin.read())
    print(json.dumps(create_draft(parsed), indent=2))
