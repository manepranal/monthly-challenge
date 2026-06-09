"""Resolve a full listing fact sheet **from an MLS id** — the brief's entry point.

The challenge asks for "open house flyers and videos *from a new MLS id*." MLS
detail (beds/baths/sqft/photos/remarks) lives in the MLS, not in arrakis, so this
module is the bridge. It exposes one function — `lookup(mls_id) -> listing` — that
returns the same normalized dict `fetch._from_json_file` produces, so everything
downstream (copywriter → compliance → flyer → video) is unchanged.

Two providers, tried in order:

1. **RESO Web API (live)** — if `MLS_BASE_URL` + `MLS_API_TOKEN` are set, query the
   RESO `Property` resource by `ListingId` and map the RESO Data Dictionary fields
   onto our listing dict. This is the real shape used by MLS Grid, Bridge
   Interactive, Spark, and Trestle — any RESO-certified feed. Swap in your
   credentials and it talks to a real MLS.

2. **Local fixtures (offline demo default)** — RESO-shaped records keyed by MLS
   number under `mls_fixtures/`. They stand in for the credentialed feed so the
   `from a new MLS id` path is genuinely runnable without MLS access. Note: only
   the *transport* is mocked — the fixture is fed through the SAME `_map_reso`
   mapper the live feed uses, so the mapping logic is exercised for real.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE / "mls_fixtures"

MLS_BASE_URL = os.environ.get("MLS_BASE_URL")        # e.g. https://api.mlsgrid.com/v2
MLS_API_TOKEN = os.environ.get("MLS_API_TOKEN")

# An MLS id is short, alphanumeric (often with a leading area letter), and digit-
# heavy. This is deliberately loose — feeds vary — but tight enough not to grab a
# stray word or a file path.
_MLS_RE = re.compile(r"^[A-Za-z0-9-]{4,16}$")


class MlsNotFound(Exception):
    """Raised when an MLS id resolves through neither the live feed nor fixtures."""


def looks_like_mls_id(token: str) -> bool:
    """True if `token` is plausibly an MLS number (and not a .json path / UUID)."""
    if not token or token.lower().endswith(".json"):
        return False
    if not _MLS_RE.match(token):
        return False
    # Require some digits so plain words ("social", "print") don't qualify.
    return sum(c.isdigit() for c in token) >= 3


# --------------------------------------------------------------------------- #
# RESO Data Dictionary -> our listing dict
# --------------------------------------------------------------------------- #
def _join_features(record: dict) -> list:
    """Flatten RESO feature fields (arrays or comma-strings) into bullet points."""
    bullets = []
    for field in (
        "InteriorFeatures", "ExteriorFeatures", "Appliances",
        "Flooring", "ParkingFeatures", "PoolFeatures", "View",
    ):
        val = record.get(field)
        if not val:
            continue
        items = val if isinstance(val, list) else [s.strip() for s in str(val).split(",")]
        bullets.extend(i for i in items if i)
    # De-dupe preserving order, cap at 6 so the flyer stays clean.
    seen, out = set(), []
    for b in bullets:
        if b.lower() not in seen:
            seen.add(b.lower())
            out.append(b)
    return out[:6]


def _street(record: dict) -> str:
    parts = [
        record.get("StreetNumber"),
        record.get("StreetDirPrefix"),
        record.get("StreetName"),
        record.get("StreetSuffix"),
        record.get("StreetDirSuffix"),
    ]
    composed = " ".join(str(p).strip() for p in parts if p)
    if composed:
        return composed
    # Fall back to UnparsedAddress (take the segment before the first comma).
    unparsed = record.get("UnparsedAddress") or ""
    return unparsed.split(",")[0].strip()


def _hero_photo(record: dict) -> str | None:
    """First Media URL. Live feeds return https URLs we download; fixtures point at
    a local image path, which the flyer embeds directly."""
    media = record.get("Media") or []
    if not media:
        return None
    url = (media[0] or {}).get("MediaURL")
    if not url:
        return None
    if url.startswith(("http://", "https://")):
        try:
            out = HERE / "out"
            out.mkdir(exist_ok=True)
            dest = out / "mls_hero.jpg"
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return str(dest)
        except Exception:
            return None  # flyer falls back to its gradient placeholder
    # Local path (fixture) — resolve relative to the project.
    p = Path(url)
    return str(p if p.is_absolute() else (HERE / url))


def _map_reso(record: dict) -> dict:
    """Map one RESO `Property` record onto our normalized listing dict."""
    lot = None
    if record.get("LotSizeAcres"):
        lot = f"{record['LotSizeAcres']} ac"
    elif record.get("LotSizeSquareFeet"):
        lot = f"{int(record['LotSizeSquareFeet']):,} sqft lot"

    oh = record.get("OpenHouse") or {}

    return {
        "address": {
            "street": _street(record),
            "city": record.get("City") or "",
            "state": record.get("StateOrProvince") or "",
            "zip": record.get("PostalCode") or "",
        },
        "price": record.get("ListPrice"),
        "propertyType": record.get("PropertySubType") or record.get("PropertyType"),
        "beds": record.get("BedroomsTotal"),
        "baths": record.get("BathroomsTotalInteger") or record.get("BathroomsFull"),
        "sqft": record.get("LivingArea"),
        "lotSize": lot,
        "yearBuilt": record.get("YearBuilt"),
        "features": _join_features(record),
        "openHouse": {
            "date": oh.get("OpenHouseDate") or record.get("OpenHouseDate"),
            "time": oh.get("OpenHouseTime") or record.get("OpenHouseTime"),
        },
        "photo": _hero_photo(record),
        "mlsNumber": record.get("ListingId") or record.get("ListingKey"),
        "description": record.get("PublicRemarks"),
        "agent": {
            "name": record.get("ListAgentFullName"),
            "phone": record.get("ListAgentPreferredPhone") or record.get("ListAgentDirectPhone"),
            "email": record.get("ListAgentEmail"),
            "brokerage": record.get("ListOfficeName") or "Real Broker",
            "license": record.get("ListAgentStateLicense") or record.get("ListAgentMlsId"),
        },
        "_source": None,  # filled by the caller
    }


# --------------------------------------------------------------------------- #
# Providers
# --------------------------------------------------------------------------- #
def _from_reso_feed(mls_id: str) -> dict:
    """Query a live RESO Web API `Property` resource by ListingId."""
    url = f"{MLS_BASE_URL.rstrip('/')}/Property"
    params = {"$filter": f"ListingId eq '{mls_id}'", "$expand": "Media", "$top": 1}
    r = requests.get(
        url, params=params,
        headers={"Authorization": f"Bearer {MLS_API_TOKEN}", "Accept": "application/json"},
        timeout=20,
    )
    r.raise_for_status()
    rows = r.json().get("value") or []
    if not rows:
        raise MlsNotFound(f"MLS id {mls_id!r} not found in the RESO feed")
    listing = _map_reso(rows[0])
    listing["_source"] = f"RESO feed {MLS_BASE_URL} (ListingId {mls_id})"
    return listing


def _from_fixture(mls_id: str) -> dict:
    path = FIXTURE_DIR / f"{mls_id}.json"
    if not path.exists():
        raise MlsNotFound(
            f"MLS id {mls_id!r} not in {FIXTURE_DIR.name}/ and no live MLS feed "
            f"configured (set MLS_BASE_URL + MLS_API_TOKEN for a RESO feed)."
        )
    listing = _map_reso(json.loads(path.read_text()))
    listing["_source"] = f"MLS fixture {path.name} (stand-in for a RESO feed)"
    return listing


def lookup(mls_id: str) -> dict:
    """Resolve an MLS id to a normalized listing dict. Live feed if configured,
    else local fixtures. Raises MlsNotFound if neither resolves it."""
    if MLS_BASE_URL and MLS_API_TOKEN:
        return _from_reso_feed(mls_id)
    return _from_fixture(mls_id)


if __name__ == "__main__":
    import sys
    print(json.dumps(lookup(sys.argv[1]), indent=2))
