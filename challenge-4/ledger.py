"""The ledger — watch mode's single source of truth (Otto's "YouTrack State").

Watch mode borrows its architecture from Realtyka/otto, the ticket-to-production
pipeline: every work item carries a State, each pipeline step advances it, and a
sweep re-evaluates anything that stalled. Here the work item is an *email*, and
the ledger (`out/<deal>/ledger.json`) plays the role YouTrack plays for Otto:

    NEW -> FILED -> SCHEDULED -> DONE          (the forward walk)
           NEEDS REVIEW                        (human gate: low-confidence filing)
           parked: true                        (run budget exhausted — Otto's
                                                `otto-blocked` tag; human resumes)

Alongside the state, each entry stores what its steps produced (the filing plan,
the filed copies, the milestones) so the publish step can regenerate every deal
artifact from the ledger alone — idempotent, exactly like Otto's re-entrant
steps. `BOARD.md` is the human-readable render (Otto's agile board) and
`ALERTS.md` is the durable alert channel (Otto's Slack posts).
"""

import datetime as dt
import json
from pathlib import Path

# The forward walk. NEEDS_REVIEW sits between NEW and FILED when the
# confidence gate trips; `parked` is a flag on top of any state, not a state.
STATE_NEW = "NEW"
STATE_NEEDS_REVIEW = "NEEDS REVIEW"
STATE_FILED = "FILED"
STATE_SCHEDULED = "SCHEDULED"
STATE_DONE = "DONE"

FORWARD_ORDER = [STATE_NEW, STATE_NEEDS_REVIEW, STATE_FILED, STATE_SCHEDULED, STATE_DONE]

LEDGER_NAME = "ledger.json"
BOARD_NAME = "BOARD.md"
ALERTS_NAME = "ALERTS.md"


def _now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load(deal_dir: Path) -> dict:
    path = Path(deal_dir) / LEDGER_NAME
    if path.exists():
        return json.loads(path.read_text())
    return {"deal": {}, "emails": {}, "history": []}


def save(deal_dir: Path, ledger: dict) -> None:
    deal_dir = Path(deal_dir)
    deal_dir.mkdir(parents=True, exist_ok=True)
    path = deal_dir / LEDGER_NAME
    # Write-then-rename so a mid-write crash can't leave a torn ledger — the
    # ledger is the source of truth, a half-written one would strand the deal.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, indent=2))
    tmp.replace(path)


def add_email(ledger: dict, email: dict, email_path: str) -> dict:
    """Register a newly-landed email as a NEW work item (the intake event)."""
    entry = {
        "id": email.get("id"),
        "subject": email.get("subject", ""),
        "from": email.get("from", ""),
        "date": email.get("date", ""),
        "path": email_path,          # source of truth for re-reads; ledger stays lean
        "state": STATE_NEW,
        "parked": False,
        "attempts": {},              # per-state dispatch counter (the run budget)
        "plan": None,                # filing plan from the file step
        "filed": [],                 # what actually got copied where
        "milestones": [],            # from the schedule step
        "history": [],
    }
    ledger["emails"][entry["id"]] = entry
    record(ledger, entry, "landed in inbox -> NEW")
    return entry


def record(ledger: dict, entry: dict, event: str) -> None:
    """Append to the entry's activity log (Otto's YouTrack activity stream)."""
    line = {"ts": _now(), "event": event}
    entry["history"].append(line)
    ledger["history"].append({"ts": line["ts"], "email": entry["id"], "event": event})


def advance(ledger: dict, entry: dict, new_state: str, note: str = "") -> None:
    """Move an entry forward and reset its run budget — Otto resets the retry
    counter on every State change, so a step never inherits a stale count."""
    old = entry["state"]
    entry["state"] = new_state
    entry["attempts"] = {}
    entry["parked"] = False
    record(ledger, entry, f"{old} -> {new_state}" + (f" ({note})" if note else ""))


def alert(deal_dir: Path, ledger: dict, entry: dict, message: str) -> None:
    """Durable alert (Otto's Slack channel): append to ALERTS.md + console bell.
    Parks and review-gates must never be invisible."""
    deal_dir = Path(deal_dir)
    deal_dir.mkdir(parents=True, exist_ok=True)
    path = deal_dir / ALERTS_NAME
    stamp = _now()
    header = "" if path.exists() else "# Alerts — Deal Organizer watch mode\n\n"
    with path.open("a") as f:
        f.write(f"{header}- **{stamp}** — {message}\n")
    record(ledger, entry, f"ALERT: {message}")
    print(f"  🔔 {message}", flush=True)


def render_board(deal_dir: Path, ledger: dict) -> None:
    """Render BOARD.md — the kanban view of the ledger (Otto's agile board)."""
    deal = ledger.get("deal", {})
    entries = sorted(ledger["emails"].values(), key=lambda e: e.get("date", ""))

    counts = {s: 0 for s in FORWARD_ORDER}
    parked = 0
    for e in entries:
        counts[e["state"]] = counts.get(e["state"], 0) + 1
        if e.get("parked"):
            parked += 1

    lane = "  →  ".join(
        f"{s} ({counts.get(s, 0)})"
        for s in [STATE_NEW, STATE_FILED, STATE_SCHEDULED, STATE_DONE]
    )
    lines = [
        f"# 🤖 Deal Board — {deal.get('property', '(deal pending)')}",
        "",
        f"`{lane}`" + (f"  ·  👀 needs review: {counts.get(STATE_NEEDS_REVIEW, 0)}" if counts.get(STATE_NEEDS_REVIEW) else "")
        + (f"  ·  🚫 parked: {parked}" if parked else ""),
        "",
        "| Email | Subject | State | Attempts | Last activity |",
        "|---|---|---|---|---|",
    ]
    for e in entries:
        flags = ""
        if e.get("parked"):
            flags = " 🚫"
        elif e["state"] == STATE_NEEDS_REVIEW:
            flags = " 👀"
        att = sum(e.get("attempts", {}).values())
        last = e["history"][-1] if e["history"] else {"ts": "", "event": ""}
        lines.append(
            f"| `{e['id']}` | {e['subject'][:48]} | **{e['state']}**{flags} "
            f"| {att} | {last['ts']} — {last['event'][:60]} |"
        )

    lines += ["", "## Activity", ""]
    for h in ledger["history"][-25:]:
        lines.append(f"- `{h['ts']}` **{h['email']}** — {h['event']}")
    lines.append("")

    (Path(deal_dir) / BOARD_NAME).write_text("\n".join(lines))


def print_board(ledger: dict) -> None:
    """Console version of the board for `status` / end-of-tick narration."""
    entries = sorted(ledger["emails"].values(), key=lambda e: e.get("date", ""))
    if not entries:
        print("  (no emails yet)")
        return
    for e in entries:
        flag = " 🚫 PARKED" if e.get("parked") else (" 👀" if e["state"] == STATE_NEEDS_REVIEW else "")
        print(f"  [{e['state']:>12}]{flag}  {e['id']:<4} {e['subject'][:56]}")
