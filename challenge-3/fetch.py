"""Load the listing facts that feed the flyer.

Three input modes, auto-detected from the single positional argument:

1) **Listing JSON file** (preferred for the demo) — a path ending in `.json`
   with the full fact sheet (address, price, beds/baths/sqft, features,
   open-house, photo, agent). MLS-style detail lives here because it is NOT
   in arrakis. See `examples/listing.json`.

2) **arrakis listing id** — a UUID. We `GET /transactions/{id}` and pull the
   real address, list price, and listing agent. Beds/baths/sqft/photo are not
   stored in arrakis, so they come from `--beds/--baths/...` flags (or are
   left blank and the copywriter omits them).

3) **nothing / flags only** — build the listing entirely from CLI flags.

In every mode, CLI flags override whatever the base source provided, so you can
enrich a real arrakis listing with the MLS detail it doesn't store.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import requests

ENV = os.environ.get("DRAFT_TX_ENV", "team2")
ARRAKIS_BASE = f"https://arrakis.{ENV}realbrokerage.com"
KEYMAKER_BASE = f"https://keymaker.{ENV}realbrokerage.com"

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)

# Flags that map straight onto the listing dict (string values).
_STR_FLAGS = {
    "--street", "--city", "--state", "--zip", "--type", "--lot", "--photo",
    "--mls", "--open-date", "--open-time", "--agent", "--phone", "--email",
    "--brokerage", "--license",
}
_NUM_FLAGS = {"--price", "--beds", "--baths", "--sqft", "--year"}


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


def _empty_listing() -> dict:
    return {
        "address": {"street": "", "city": "", "state": "", "zip": ""},
        "price": None,
        "propertyType": None,
        "beds": None,
        "baths": None,
        "sqft": None,
        "lotSize": None,
        "yearBuilt": None,
        "features": [],
        "openHouse": {"date": None, "time": None},
        "photo": None,
        "mlsNumber": None,
        "agent": {
            "name": None,
            "phone": None,
            "email": None,
            "brokerage": "Real Broker",
            "license": None,
        },
    }


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into `base`, ignoring None/empty overrides."""
    for k, v in override.items():
        if v in (None, "", [], {}):
            continue
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _from_json_file(path: Path) -> dict:
    data = json.loads(path.read_text())
    return _deep_merge(_empty_listing(), data)


def _from_arrakis(listing_id: str) -> dict:
    """Pull address / list price / listing agent from a real arrakis listing.

    arrakis transaction shapes vary by env, so we probe a few candidate field
    paths defensively rather than assume one schema.
    """
    token = get_token()
    r = requests.get(
        f"{ARRAKIS_BASE}/api/v1/transactions/{listing_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    tx = r.json()

    listing = _empty_listing()

    addr = tx.get("address") or tx.get("propertyAddress") or {}
    listing["address"] = {
        "street": addr.get("street") or addr.get("oneLine") or "",
        "city": addr.get("city") or "",
        "state": (addr.get("state") or addr.get("stateOrProvince") or "").replace("_", " ").title(),
        "zip": addr.get("zip") or addr.get("zipCode") or addr.get("postalCode") or "",
    }

    price = (
        (tx.get("price") or {}).get("amount")
        if isinstance(tx.get("price"), dict)
        else tx.get("price")
    ) or (
        (tx.get("salePrice") or {}).get("amount")
        if isinstance(tx.get("salePrice"), dict)
        else tx.get("salePrice")
    ) or (
        (tx.get("listPrice") or {}).get("amount")
        if isinstance(tx.get("listPrice"), dict)
        else tx.get("listPrice")
    )
    listing["price"] = price

    listing["mlsNumber"] = tx.get("mlsNumber") or (tx.get("location") or {}).get("mlsNumber")

    # Listing agent: first owner / REAL participant we can name.
    parts = tx.get("agentsInfo", {}).get("ownerAgent") or tx.get("allParticipants") or []
    if isinstance(parts, dict):
        parts = [parts]
    for p in parts:
        first = p.get("firstName") or ""
        last = p.get("lastName") or ""
        name = (f"{first} {last}").strip() or p.get("name")
        if name:
            listing["agent"]["name"] = name
            listing["agent"]["phone"] = p.get("phoneNumber") or p.get("phone")
            listing["agent"]["email"] = p.get("emailAddress") or p.get("email")
            break

    listing["_source"] = f"arrakis listing {listing_id} on {ENV}"
    return listing


def _apply_flags(listing: dict, argv: list) -> dict:
    """Apply --flag value overrides. Repeatable --feature builds the list."""
    override = _empty_listing()
    override["features"] = []
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag == "--feature":
            override["features"].append(argv[i + 1])
            i += 2
        elif flag in _STR_FLAGS:
            val = argv[i + 1]
            _set_flag(override, flag, val)
            i += 2
        elif flag in _NUM_FLAGS:
            val = argv[i + 1]
            num = float(val) if "." in val else int(val)
            _set_flag(override, flag, num)
            i += 2
        else:
            i += 1
    return _deep_merge(listing, override)


def _set_flag(d: dict, flag: str, val) -> None:
    mapping = {
        "--street": ("address", "street"),
        "--city": ("address", "city"),
        "--state": ("address", "state"),
        "--zip": ("address", "zip"),
        "--price": ("price",),
        "--type": ("propertyType",),
        "--beds": ("beds",),
        "--baths": ("baths",),
        "--sqft": ("sqft",),
        "--lot": ("lotSize",),
        "--year": ("yearBuilt",),
        "--mls": ("mlsNumber",),
        "--photo": ("photo",),
        "--open-date": ("openHouse", "date"),
        "--open-time": ("openHouse", "time"),
        "--agent": ("agent", "name"),
        "--phone": ("agent", "phone"),
        "--email": ("agent", "email"),
        "--brokerage": ("agent", "brokerage"),
        "--license": ("agent", "license"),
    }
    path = mapping[flag]
    node = d
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = val


def load_listing(argv: list) -> dict:
    """argv is everything after the script name. First non-flag token is the
    source (JSON path or arrakis id); the rest are --flag overrides."""
    source: Optional[str] = None
    flags = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--"):
            # --feature and value-flags consume the next token too
            flags.append(tok)
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                flags.append(argv[i + 1])
                i += 2
            else:
                i += 1
        elif source is None:
            source = tok
            i += 1
        else:
            i += 1

    if source and source.lower().endswith(".json"):
        listing = _from_json_file(Path(source).expanduser().resolve())
    elif source and UUID_RE.match(source):
        listing = _from_arrakis(source)
    else:
        listing = _empty_listing()
        if source:
            print(
                f"  (source {source!r} is neither a .json path nor a listing UUID — "
                f"building from flags only)",
                file=sys.stderr,
            )

    listing = _apply_flags(listing, flags)

    if not listing["address"]["street"]:
        raise SystemExit(
            "No street address. Provide a listing JSON, an arrakis id, or "
            "at least --street/--city/--state/--zip."
        )
    if not listing.get("price"):
        raise SystemExit("No price. Provide it in the JSON or via --price.")
    return listing


if __name__ == "__main__":
    print(json.dumps(load_listing(sys.argv[1:]), indent=2))
