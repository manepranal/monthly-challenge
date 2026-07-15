"""The pipeline steps — watch mode's otto-1/2/3 analogs.

Each step takes ONE email one state forward, does the minimum, and returns.
Never waits, never loops — the sweep in pipeline.py is the loop (Otto's
"checks once, never waits" rule). All three are safe to re-run: filing
re-copies the same files, and publish regenerates every artifact from the
ledger, so a retry after a mid-step crash converges instead of duplicating.

    NEW        --file-->     FILED       AI call #1 (classify.organize, one email)
    NEW        --file-->     NEEDS REVIEW  when any filing confidence < gate
    FILED      --schedule--> SCHEDULED   AI call #2 (dates.extract, one email)
    SCHEDULED  --publish-->  DONE        no AI — regenerate calendar/follow-ups/summary

The AI jobs are the same two forced-tool calls the one-shot mode uses
(classify.py / dates.py) — watch mode just feeds them a single-email inbox and
merges the results into the ledger instead of processing the whole pile at once.
"""

import datetime as dt
import os
import shutil
from pathlib import Path

import classify
import dates
import ledger as lg
import organize

# The human gate (Otto's `Requires UI QA` scope rule, applied honestly): a
# filing the model isn't confident about goes to a human instead of being
# auto-filed. Otto's own lesson — don't let the agent rubber-stamp the field
# that decides whether a human looks at it.
CONFIDENCE_GATE = float(os.environ.get("OTTO_CONFIDENCE_GATE", "0.6"))


def _single_email_inbox(deal: dict, email: dict) -> dict:
    return {"deal": deal, "emails": [email]}


# --------------------------------------------------------------------------
# NEW -> FILED (or NEEDS REVIEW)
# --------------------------------------------------------------------------

def step_file(deal_dir: Path, ledger: dict, entry: dict, email: dict) -> str:
    """AI job #1 on one email: route its attachments + surface action items.
    Low-confidence routings stop at the human gate instead of auto-filing."""
    plan = classify.organize(_single_email_inbox(ledger["deal"], email))
    entry["plan"] = plan

    low = [
        f for f in plan.get("filings", [])
        if float(f.get("confidence", 0)) < CONFIDENCE_GATE
    ]
    if low:
        names = ", ".join(f"{f['filename']} ({f.get('confidence', 0):.2f})" for f in low)
        lg.advance(ledger, entry, lg.STATE_NEEDS_REVIEW, f"low-confidence filing: {names}")
        lg.alert(
            deal_dir, ledger, entry,
            f"👀 `{entry['id']}` needs review — filing confidence below {CONFIDENCE_GATE}: "
            f"{names}. Approve with `python3 pipeline.py approve {entry['id']}` "
            f"(files the plan as-is) after checking BOARD.md / ledger.json.",
        )
        return lg.STATE_NEEDS_REVIEW

    apply_filings(deal_dir, ledger, entry, email)
    n_docs = len(entry["filed"])
    n_actions = len(plan.get("action_items", []))
    lg.advance(ledger, entry, lg.STATE_FILED, f"{n_docs} doc(s) filed, {n_actions} follow-up(s)")
    return lg.STATE_FILED


def apply_filings(deal_dir: Path, ledger: dict, entry: dict, email: dict) -> None:
    """Execute the stored filing plan (copy each attachment into its folder).
    Split out so `approve` can run it without a fresh AI call."""
    src_by_name = {a["filename"]: a["path"] for a in email.get("attachments", [])}
    entry["filed"] = []
    for f in (entry.get("plan") or {}).get("filings", []):
        src = src_by_name.get(f.get("filename"))
        dest_dir = Path(deal_dir) / f.get("destination", "Correspondence")
        dest_dir.mkdir(parents=True, exist_ok=True)
        if src and Path(src).exists():
            shutil.copy2(src, dest_dir / Path(src).name)
            entry["filed"].append({**f, "filed_to": str(dest_dir / Path(src).name)})
            lg.record(ledger, entry, f"filed {f['filename']} -> {f['destination']}/")
        else:
            lg.record(ledger, entry, f"missing source file for {f.get('filename')}")


# --------------------------------------------------------------------------
# FILED -> SCHEDULED
# --------------------------------------------------------------------------

def step_schedule(deal_dir: Path, ledger: dict, entry: dict, email: dict) -> str:
    """AI job #2 on one email: pull every dated milestone it (or its
    attachments) states. Emails with no dates legitimately produce zero."""
    result = dates.extract(_single_email_inbox(ledger["deal"], email))
    entry["milestones"] = result.get("milestones", [])
    n = len(entry["milestones"])
    lg.advance(ledger, entry, lg.STATE_SCHEDULED, f"{n} milestone(s)")
    return lg.STATE_SCHEDULED


# --------------------------------------------------------------------------
# SCHEDULED -> DONE
# --------------------------------------------------------------------------

def step_publish(deal_dir: Path, ledger: dict, entry: dict, email: dict) -> str:
    """No AI. Regenerate every deal artifact from the ledger — the whole ledger,
    not just this email — so artifacts are always a pure function of state and a
    re-run can never double-append. Then the email is DONE."""
    publish_artifacts(deal_dir, ledger)
    lg.advance(ledger, entry, lg.STATE_DONE, "artifacts published")
    return lg.STATE_DONE


def merged_milestones(ledger: dict) -> list:
    """Union of every email's milestones, deduped by (date, category) — the
    same deadline often arrives twice (contract, then a reminder email).
    Contract-sourced entries win ties, mirroring dates.py's 'contract wins'."""
    def is_contract(m):
        s = (m.get("source") or "").lower()
        return "agreement" in s or "contract" in s

    candidates = []
    for e in ledger["emails"].values():
        candidates.extend(e.get("milestones", []))
    candidates.sort(key=lambda m: (0 if is_contract(m) else 1))

    seen, out = set(), []
    for m in candidates:
        key = (m.get("date"), m.get("category"))
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return sorted(out, key=lambda m: m.get("date", ""))


def merged_actions(ledger: dict) -> list:
    out = []
    for e in sorted(ledger["emails"].values(), key=lambda x: x.get("date", "")):
        out.extend((e.get("plan") or {}).get("action_items", []))
    return out


def publish_artifacts(deal_dir: Path, ledger: dict) -> dict:
    """calendar.ics + FOLLOW_UPS.md + SUMMARY.md, regenerated from the ledger.
    Reuses the one-shot mode's builders so both modes emit identical formats."""
    deal_dir = Path(deal_dir)
    deal = ledger.get("deal", {})
    milestones = merged_milestones(ledger)
    actions = merged_actions(ledger)
    filed = [f for e in ledger["emails"].values() for f in e.get("filed", [])]

    ics = organize.build_ics(deal, milestones, dt.datetime.utcnow())
    (deal_dir / "calendar.ics").write_bytes(ics.encode("utf-8"))
    (deal_dir / "FOLLOW_UPS.md").write_text(organize._follow_ups_md(deal, actions))
    (deal_dir / "SUMMARY.md").write_text(
        organize._summary_md(deal, filed, milestones, actions, [])
    )
    return {"milestones": milestones, "actions": actions, "filed": filed}


# What runs for each state — pipeline.py dispatches off this table, the same
# way otto-run's `cfg` step resolves the skill from the ticket State.
STEP_FOR_STATE = {
    lg.STATE_NEW: ("file", step_file),
    lg.STATE_FILED: ("schedule", step_schedule),
    lg.STATE_SCHEDULED: ("publish", step_publish),
}
