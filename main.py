"""Orchestrator: prompt -> parse -> validate -> create draft -> print summary."""

import sys

import requests

from create import ENV, create_draft
from parse import parse_prompt


def validate_splits(data: dict) -> None:
    co_total = sum(a["splitPercent"] for a in data["coAgents"])
    if abs(co_total - 100) > 0.01:
        raise SystemExit(
            f"Co-agent splits sum to {co_total}, expected 100. Adjust the prompt."
        )
    me_count = sum(1 for a in data["coAgents"] if a.get("isMe"))
    if me_count != 1:
        raise SystemExit(
            f"Expected exactly one coAgent with isMe=true, got {me_count}."
        )


def fmt_money(n: float) -> str:
    return f"${n:,.0f}"


def print_parsed(data: dict) -> None:
    print("Parsed:")
    print(f"  Gross commission: {fmt_money(data['grossCommission'])}")
    print(f"  Representation:   {data['representationType']}")
    a = data["address"]
    print(f"  Address:          {a['street']}, {a['city']}, {a['state']} {a['zip']}")
    print("  Co-agents:")
    for ag in data["coAgents"]:
        tag = " (me)" if ag.get("isMe") else ""
        print(f"    - {ag['name']}{tag} — {ag['splitPercent']}%")
    if data.get("referrals"):
        print("  Referrals:")
        for r in data["referrals"]:
            print(f"    - {r['name']} — {r['splitPercent']}%")


def main() -> None:
    prompt = " ".join(sys.argv[1:]).strip()
    if not prompt:
        print("Enter your transaction prompt (Ctrl+D to submit):")
        prompt = sys.stdin.read().strip()
    if not prompt:
        raise SystemExit("No prompt provided.")

    print(f"\nParsing with claude-sonnet-4-6...\n")
    data = parse_prompt(prompt)
    print_parsed(data)
    validate_splits(data)

    print(f"\nBuilding draft on {ENV}...")
    result = create_draft(data)

    print("\nDraft transaction ready")
    print(f"  ID:        {result['transactionId']}")
    print(f"  Bolt URL:  {result['boltUrl']}")
    print(
        f"  (sale price set to {fmt_money(result['salePrice'])} so "
        f"{result['commissionPercent']}% ≈ {fmt_money(data['grossCommission'])})"
    )


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
