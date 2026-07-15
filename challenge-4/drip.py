"""Drip the sample deal into the live inbox, one email at a time — the demo's
stand-in for "emails arriving while the organizer runs".

Run `python3 pipeline.py watch` in one terminal, this in another, and watch each
email walk itself across BOARD.md. Idempotent: already-dripped emails are
skipped, so it can be re-run (or resumed after Ctrl-C) safely.

Usage:
    python3 drip.py [live-inbox] [--interval SECONDS] [--source examples]
"""

import argparse
import json
import shutil
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("live_dir", nargs="?", default="live-inbox")
    ap.add_argument("--interval", type=int, default=20,
                    help="seconds between arrivals (default 20)")
    ap.add_argument("--source", default="examples",
                    help="fixtures folder with inbox.json + attachments/")
    args = ap.parse_args()

    src = Path(args.source)
    data = json.loads((src / "inbox.json").read_text())
    live = Path(args.live_dir)
    (live / "emails").mkdir(parents=True, exist_ok=True)
    (live / "attachments").mkdir(parents=True, exist_ok=True)

    # Deal facts land first — the organizer waits on deal.json before ticking.
    deal_file = live / "deal.json"
    if not deal_file.exists():
        deal_file.write_text(json.dumps(data["deal"], indent=2))
        print(f"[drip] deal.json → {deal_file}  ({data['deal'].get('property', '')})")

    emails = sorted(data.get("emails", []), key=lambda e: e.get("date", ""))
    for email in emails:
        target = live / "emails" / f"{email['id']}.json"
        if target.exists():
            print(f"[drip] {email['id']} already landed — skipping")
            continue

        # Attachments (plus their .txt extraction sidecars) must be readable
        # the instant the email file appears, so copy them first.
        for name in email.get("attachments", []):
            for candidate in (src / "attachments" / name,
                              (src / "attachments" / name).with_suffix(".txt")):
                if candidate.exists():
                    shutil.copy2(candidate, live / "attachments" / candidate.name)

        target.write_text(json.dumps(email, indent=2))
        n_att = len(email.get("attachments", []))
        print(f"[drip] 📧 {email['id']} landed • “{email['subject'][:52]}”"
              f"  ({n_att} attachment{'s' if n_att != 1 else ''})")

        if email is not emails[-1]:
            time.sleep(args.interval)

    print("[drip] inbox fully delivered — watch the board finish organizing.")


if __name__ == "__main__":
    main()
