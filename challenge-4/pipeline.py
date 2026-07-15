"""Watch mode — the Otto harness, local edition.

One-shot mode (main.py) organizes a pile. Watch mode organizes a *stream*:
emails land in a live inbox folder while the organizer runs, and each one walks
itself across the board — NEW -> FILED -> SCHEDULED -> DONE — exactly the way
Realtyka/otto walks a ticket from `To Do` to production:

  - The ledger is the single source of truth (Otto: YouTrack State).
  - Every tick runs AT MOST ONE step per email, then exits the step — the sweep
    is the loop, steps never wait (Otto: "checks once, never waits").
  - A lock file serializes runs per deal (Otto: the `otto-in-progress` tag).
  - A per-(email, state) dispatch counter caps retries; at the cap the email is
    PARKED with a durable alert and never touched again until a human resumes it
    (Otto: the run-budget gate + `otto-blocked`). Counting happens at dispatch
    time, BEFORE the step runs, so even a crashing step stays bounded.
  - Low-confidence filings stop at a human gate — NEEDS REVIEW — instead of
    being auto-filed (the honest version of Otto's `Requires UI QA` scoping).

Live inbox layout (drip.py feeds this from examples/ for the demo):

    live-inbox/
    ├── deal.json            # the deal facts (written once, first)
    ├── emails/<id>.json     # one file per landed email — the arrival event
    └── attachments/<name>   # the attachment files the emails reference

Usage:
    python3 pipeline.py watch  [live-inbox]     # sweep loop (Ctrl-C to stop)
    python3 pipeline.py tick   [live-inbox]     # exactly one tick
    python3 pipeline.py status [live-inbox]     # print the board
    python3 pipeline.py approve <email-id> [live-inbox]   # pass the review gate
    python3 pipeline.py resume  <email-id> [live-inbox]   # un-park, fresh budget

Tunables (env): OTTO_SWEEP_SEC=5  OTTO_MAX_RUNS_PER_STATE=3
                OTTO_CONFIDENCE_GATE=0.6  (see steps.py)
"""

import json
import os
import sys
import time
from pathlib import Path

import fetch
import ledger as lg
import organize
import steps

SWEEP_SEC = int(os.environ.get("OTTO_SWEEP_SEC", "5"))
MAX_RUNS_PER_STATE = int(os.environ.get("OTTO_MAX_RUNS_PER_STATE", "3"))
LOCK_NAME = ".otto-in-progress"
LOCK_STALE_SEC = 300

OUT_ROOT = Path("out")


def _p(s=""):
    print(s, flush=True)


# --------------------------------------------------------------------------
# Lock — Otto's `otto-in-progress` tag. One organizer per deal at a time.
# --------------------------------------------------------------------------

def acquire_lock(deal_dir: Path) -> bool:
    lock = Path(deal_dir) / LOCK_NAME
    if lock.exists():
        age = time.time() - lock.stat().st_mtime
        if age < LOCK_STALE_SEC:
            _p(f"  [lock] another run holds {LOCK_NAME} ({int(age)}s old) — skipping tick")
            return False
        # A crash can strand the lock; a stranded lock must never freeze the
        # deal forever (Otto retries its unlock 3x and fails LOUDLY for the
        # same reason). Break it with a visible warning.
        _p(f"  [lock] breaking stale lock ({int(age)}s old)")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({"pid": os.getpid(), "ts": time.time()}))
    return True


def release_lock(deal_dir: Path) -> None:
    (Path(deal_dir) / LOCK_NAME).unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Intake — the arrival event (Otto's onChange dispatch)
# --------------------------------------------------------------------------

def load_email(live_dir: Path, path: Path) -> dict:
    """Read one landed email file and enrich its attachments with real paths +
    extracted text (same shape fetch.load_inbox produces for one-shot mode)."""
    email = json.loads(Path(path).read_text())
    attach_dir = Path(live_dir) / "attachments"
    enriched = []
    for name in email.get("attachments", []):
        p = attach_dir / name
        enriched.append({"filename": name, "path": str(p), "text": fetch._extract_text(p)})
    email["attachments"] = enriched
    return email


def intake(live_dir: Path, ledger: dict) -> list:
    """Register every email file not yet in the ledger. Returns new entries."""
    emails_dir = Path(live_dir) / "emails"
    if not emails_dir.exists():
        return []
    new = []
    for path in sorted(emails_dir.glob("*.json")):
        email_id = path.stem
        if email_id in ledger["emails"]:
            continue
        email = load_email(live_dir, path)
        email.setdefault("id", email_id)
        entry = lg.add_email(ledger, email, str(path))
        new.append(entry)
        _p(f"  [intake]   {entry['id']} • “{entry['subject'][:52]}” → NEW")
    return new


# --------------------------------------------------------------------------
# The tick — budget gate, then at most one step per email
# --------------------------------------------------------------------------

def run_budget_gate(deal_dir: Path, ledger: dict, entry: dict) -> bool:
    """Otto's gate job: count this dispatch BEFORE running (a crashing step must
    still burn budget), park at the cap with a durable alert. True = run."""
    state = entry["state"]
    n = entry["attempts"].get(state, 0)
    if n >= MAX_RUNS_PER_STATE:
        entry["parked"] = True
        lg.alert(
            deal_dir, ledger, entry,
            f"🚫 parked `{entry['id']}` — {MAX_RUNS_PER_STATE} attempt(s) in {state} "
            f"without progressing. It will not be retried automatically. "
            f"Resume with `python3 pipeline.py resume {entry['id']}` after investigating.",
        )
        return False
    entry["attempts"][state] = n + 1
    return True


def tick(live_dir: Path) -> bool:
    """One sweep pass: intake new arrivals, then walk every live item one step.
    Returns True if anything changed (for the watch loop's narration)."""
    live_dir = Path(live_dir)
    deal_file = live_dir / "deal.json"
    if not deal_file.exists():
        _p(f"  [tick] waiting — no deal.json in {live_dir}/ yet")
        return False

    deal = json.loads(deal_file.read_text())
    deal_dir = OUT_ROOT / organize.slugify(deal)

    if not acquire_lock(deal_dir):
        return False

    changed = False
    try:
        ledger = lg.load(deal_dir)
        ledger["deal"] = deal

        changed = bool(intake(live_dir, ledger))
        if changed:
            lg.save(deal_dir, ledger)   # arrivals survive even if a step crashes

        pending = [
            e for e in sorted(ledger["emails"].values(), key=lambda x: x.get("date", ""))
            if e["state"] in steps.STEP_FOR_STATE and not e.get("parked")
        ]
        for entry in pending:
            if not run_budget_gate(deal_dir, ledger, entry):
                changed = True
                lg.save(deal_dir, ledger)
                continue
            step_name, step_fn = steps.STEP_FOR_STATE[entry["state"]]
            lg.save(deal_dir, ledger)   # persist the counted dispatch first
            try:
                email = load_email(live_dir, entry["path"])
                new_state = step_fn(deal_dir, ledger, entry, email)
                _p(f"  [{step_name:<8}] {entry['id']} • “{entry['subject'][:44]}” → {new_state}")
            except Exception as exc:  # stay in state; the sweep retries, the budget bounds it
                lg.record(ledger, entry, f"{step_name} failed: {str(exc)[:120]}")
                _p(f"  [{step_name:<8}] {entry['id']} FAILED ({str(exc)[:80]}) — "
                   f"attempt {entry['attempts'][entry['state']]}/{MAX_RUNS_PER_STATE}, sweep retries")
            changed = True
            lg.save(deal_dir, ledger)

        if changed:
            lg.render_board(deal_dir, ledger)
            lg.save(deal_dir, ledger)
    finally:
        release_lock(deal_dir)   # Otto's always() unlock — never leave it stuck
    return changed


# --------------------------------------------------------------------------
# The sweep loop (Otto's 15-min onSchedule, compressed for a live demo)
# --------------------------------------------------------------------------

def watch(live_dir: Path) -> None:
    _p("=" * 68)
    _p("  DEAL ORGANIZER — watch mode (Otto-style pipeline)")
    _p(f"  live inbox: {live_dir}/   sweep: every {SWEEP_SEC}s   "
       f"budget: {MAX_RUNS_PER_STATE}/state")
    _p("=" * 68)
    quiet = 0
    while True:
        try:
            if tick(live_dir):
                quiet = 0
            else:
                quiet += 1
                if quiet % 12 == 1:   # throttled heartbeat, like the YT rule's
                    _p(f"  [sweep] idle — watching {live_dir}/ (Ctrl-C to stop)")
            time.sleep(SWEEP_SEC)
        except KeyboardInterrupt:
            _p("\n  [sweep] stopped. Board and artifacts are in out/<deal>/ — bye.")
            return


# --------------------------------------------------------------------------
# Human commands — the gates only a person clears
# --------------------------------------------------------------------------

def _deal_dir_for(live_dir: Path) -> Path:
    deal = json.loads((Path(live_dir) / "deal.json").read_text())
    return OUT_ROOT / organize.slugify(deal)


def approve(live_dir: Path, email_id: str) -> None:
    """Clear the NEEDS REVIEW gate: file the stored plan as-is (no new AI call)."""
    deal_dir = _deal_dir_for(live_dir)
    ledger = lg.load(deal_dir)
    entry = ledger["emails"].get(email_id)
    if not entry or entry["state"] != lg.STATE_NEEDS_REVIEW:
        _p(f"  nothing to approve: {email_id} is "
           f"{'missing' if not entry else 'in ' + entry['state']}")
        return
    email = load_email(live_dir, entry["path"])
    steps.apply_filings(deal_dir, ledger, entry, email)
    lg.advance(ledger, entry, lg.STATE_FILED, "approved by human — plan filed as-is")
    lg.render_board(deal_dir, ledger)
    lg.save(deal_dir, ledger)
    _p(f"  ✅ {email_id} approved → FILED ({len(entry['filed'])} doc(s)). "
       f"The sweep takes it from here.")


def resume(live_dir: Path, email_id: str) -> None:
    """Un-park (Otto: a human removing `otto-blocked`). Fresh budget, same state."""
    deal_dir = _deal_dir_for(live_dir)
    ledger = lg.load(deal_dir)
    entry = ledger["emails"].get(email_id)
    if not entry or not entry.get("parked"):
        _p(f"  nothing to resume: {email_id} is "
           f"{'missing' if not entry else 'not parked (' + entry['state'] + ')'}")
        return
    entry["parked"] = False
    entry["attempts"] = {}
    lg.record(ledger, entry, "un-parked by human — budget reset")
    lg.render_board(deal_dir, ledger)
    lg.save(deal_dir, ledger)
    _p(f"  ▶️  {email_id} resumed in {entry['state']} with a fresh budget.")


def status(live_dir: Path) -> None:
    deal_dir = _deal_dir_for(live_dir)
    lg.print_board(lg.load(deal_dir))
    _p(f"\n  board: {deal_dir}/BOARD.md   alerts: {deal_dir}/ALERTS.md")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "watch"
    if cmd in ("watch", "tick", "status"):
        live = Path(argv[2] if len(argv) > 2 else "live-inbox")
        {"watch": watch, "tick": tick, "status": status}[cmd](live)
    elif cmd in ("approve", "resume"):
        if len(argv) < 3:
            _p(f"usage: pipeline.py {cmd} <email-id> [live-inbox]")
            sys.exit(2)
        live = Path(argv[3] if len(argv) > 3 else "live-inbox")
        {"approve": approve, "resume": resume}[cmd](live, argv[2])
    else:
        _p(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main(sys.argv)
