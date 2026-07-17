"""Deal Organizer — orchestrator.

    fetch inbox  ->  Claude files the documents  ->  Claude extracts the dates
                 ->  build the deal folder + calendar + follow-ups

Usage:
    python3 main.py                 # runs on examples/ (the sample deal)
    python3 main.py examples        # same, explicit
    python3 main.py /path/to/inbox  # any folder with inbox.json + attachments/
"""

import sys

import classify
import dates
import fetch
import organize

BAR = "=" * 68


def _p(s=""):
    print(s, flush=True)


def main(argv):
    source = argv[1] if len(argv) > 1 else "examples"

    _p(BAR)
    _p("  DEAL ORGANIZER  ·  July challenge — 'get your agents organized'")
    _p(BAR)

    # 1. Load the inbox
    inbox = fetch.load_inbox(source)
    deal = inbox["deal"]
    n_att = fetch.attachment_count(inbox)
    _p(f"\nDeal:     {deal.get('property','')}")
    _p(f"Inbox:    {len(inbox['emails'])} emails, {n_att} attachments")

    # 2. Claude files the documents + surfaces follow-ups
    _p("\n[1/3] Filing documents with Claude ...")
    plan = classify.organize(inbox)
    _p(f"      {len(plan.get('filings', []))} documents routed, "
       f"{len(plan.get('action_items', []))} follow-ups found")

    # 3. Claude extracts the deadline calendar
    _p("\n[2/3] Extracting milestone dates with Claude ...")
    milestones = dates.extract(inbox)
    _p(f"      {len(milestones.get('milestones', []))} milestones extracted")

    # 4. Organize: folders + calendar + follow-ups
    _p("\n[3/3] Building the deal folder, calendar, and follow-ups ...")
    result = organize.build(inbox, plan, milestones)

    # ---- report -------------------------------------------------------
    _p("\n" + BAR)
    _p("  ORGANIZED")
    _p(BAR)

    _p(f"\n  Deal folder:  {result['deal_dir']}/")
    by_dest = {}
    for f in result["filed"]:
        by_dest.setdefault(f["destination"], []).append(f)
    for dest, items in by_dest.items():
        _p(f"    {dest}/")
        for f in items:
            _p(f"       - {f['filename']}   ({f['category']})")
    if result["missing"]:
        _p("    (!) missing source files: " + ", ".join(result["missing"]))

    _p("\n  Calendar (calendar.ics):")
    for m in sorted(result["milestones"], key=lambda x: x.get("date", "")):
        rem = f"  · remind {m['reminder_days_before']}d before" if m.get("reminder_days_before") else ""
        _p(f"    {m.get('date','')}   {m.get('name','')}{rem}")

    if result["action_items"]:
        _p("\n  Follow-ups:")
        order = {"high": 0, "medium": 1, "low": 2}
        for a in sorted(result["action_items"], key=lambda x: order.get(x.get("priority",""), 3)):
            due = f"  (by {a['due_hint']})" if a.get("due_hint") else ""
            _p(f"    [{a.get('priority','').upper():6}] {a.get('task','')}{due}")

    _p("\n  Artifacts:")
    _p(f"    - {result['summary_path']}")
    _p(f"    - {result['ics_path']}")
    _p(f"    - {result['follow_ups_path']}")
    _p("\n  Import calendar.ics into Google/Apple Calendar to load every")
    _p("  deadline with its reminder. Done.\n")


if __name__ == "__main__":
    main(sys.argv)
