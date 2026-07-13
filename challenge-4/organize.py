"""Execute the plan — the part that actually makes the agent organized.

Given the inbox, the filing plan (from classify.py) and the milestones (from
dates.py), this:

  1. builds a tidy deal folder tree and copies each attachment into the right
     sub-folder (the offline stand-in for a Google Drive deal folder);
  2. writes calendar.ics — a standard iCalendar file with a reminder on every
     deadline, importable straight into Google Calendar / Apple Calendar;
  3. writes FOLLOW_UPS.md (the surfaced action items) and SUMMARY.md.

Everything is written under ./out — nothing outside the project is touched. The
live Google Drive + Calendar variant (via MCP) is described in CLAUDE.md; it
consumes the exact same plan objects.
"""

import datetime as dt
import re
import shutil
from pathlib import Path


def slugify(deal: dict) -> str:
    base = deal.get("property") or deal.get("id") or "deal"
    base = base.split(",")[0]  # "123 Maple Avenue, Rye, NY" -> "123 Maple Avenue"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-")
    return slug or "deal"


def _ics_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 line folding at 75 octets (keep it simple/ASCII)."""
    if len(line) <= 73:
        return line
    out, rest = line[:73], line[73:]
    while rest:
        out += "\r\n " + rest[:72]
        rest = rest[72:]
    return out


def build_ics(deal: dict, milestones: list, now: dt.datetime) -> str:
    prop = deal.get("property", "")
    short = prop.split(",")[0]
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Deal Organizer//challenge-4//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for i, m in enumerate(milestones):
        try:
            d = dt.date.fromisoformat(m["date"])
        except (ValueError, KeyError):
            continue  # skip anything without a real ISO date
        dend = d + dt.timedelta(days=1)
        uid = f"{slugify(deal)}-{i}-{d.strftime('%Y%m%d')}@deal-organizer"
        summary = f"{m.get('name', 'Milestone')} — {short}"
        desc_bits = [m.get("note", ""), f"Source: {m.get('source', '')}", f"Deal: {prop}"]
        desc = "  ".join(b for b in desc_bits if b)
        rdays = int(m.get("reminder_days_before", 0) or 0)
        lines += [
            "BEGIN:VEVENT",
            _fold(f"UID:{uid}"),
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{dend.strftime('%Y%m%d')}",
            _fold(f"SUMMARY:{_ics_escape(summary)}"),
            _fold(f"DESCRIPTION:{_ics_escape(desc)}"),
            f"CATEGORIES:{_ics_escape(m.get('category', 'Other'))}",
            "TRANSP:TRANSPARENT",
        ]
        if rdays > 0:
            lines += [
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                _fold(f"DESCRIPTION:{_ics_escape(summary)}"),
                f"TRIGGER:-P{rdays}D",
                "END:VALARM",
            ]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def build(inbox: dict, plan: dict, milestones_result: dict, out_root: str = "out") -> dict:
    """Do the organizing. Returns a summary dict for the caller to print."""
    deal = inbox.get("deal", {})
    now = dt.datetime.utcnow()
    deal_dir = Path(out_root) / slugify(deal)
    if deal_dir.exists():
        shutil.rmtree(deal_dir)  # only ever our own ./out/<deal> — safe to rebuild
    deal_dir.mkdir(parents=True, exist_ok=True)

    # index attachments by filename -> source path
    src_by_name = {}
    for e in inbox.get("emails", []):
        for a in e.get("attachments", []):
            src_by_name[a["filename"]] = a["path"]

    # 1. file the documents
    filed, missing = [], []
    for f in plan.get("filings", []):
        name = f.get("filename")
        dest = f.get("destination", "Correspondence")
        src = src_by_name.get(name)
        dest_dir = deal_dir / dest
        dest_dir.mkdir(parents=True, exist_ok=True)
        if src and Path(src).exists():
            shutil.copy2(src, dest_dir / Path(src).name)
            filed.append({**f, "filed_to": str((dest_dir / Path(src).name))})
        else:
            missing.append(name)

    # 2. write the calendar
    milestones = milestones_result.get("milestones", [])
    ics = build_ics(deal, milestones, now)
    ics_path = deal_dir / "calendar.ics"
    # write bytes so the CRLF line endings RFC 5545 requires survive on every
    # platform (text mode on Windows would double the carriage returns).
    ics_path.write_bytes(ics.encode("utf-8"))

    # 3. follow-ups
    actions = plan.get("action_items", [])
    fu_path = deal_dir / "FOLLOW_UPS.md"
    fu_path.write_text(_follow_ups_md(deal, actions))

    # 4. summary
    summary_path = deal_dir / "SUMMARY.md"
    summary_path.write_text(_summary_md(deal, filed, milestones, actions, missing))

    return {
        "deal_dir": str(deal_dir),
        "filed": filed,
        "missing": missing,
        "milestones": milestones,
        "action_items": actions,
        "ics_path": str(ics_path),
        "summary_path": str(summary_path),
        "follow_ups_path": str(fu_path),
    }


def _follow_ups_md(deal: dict, actions: list) -> str:
    order = {"high": 0, "medium": 1, "low": 2}
    rows = ["# Follow-ups — " + deal.get("property", ""), ""]
    if not actions:
        rows.append("_No open follow-ups._")
        return "\n".join(rows) + "\n"
    for a in sorted(actions, key=lambda x: order.get(x.get("priority", "low"), 3)):
        due = f" _(by {a['due_hint']})_" if a.get("due_hint") else ""
        rows.append(f"- **[{a.get('priority', 'low').upper()}]** {a.get('task', '')}{due}")
    return "\n".join(rows) + "\n"


def _summary_md(deal, filed, milestones, actions, missing) -> str:
    lines = [f"# Deal Organizer — {deal.get('property', '')}", ""]
    lines.append(f"- **Deal:** {deal.get('id', '')}")
    lines.append(f"- **Buyers:** {deal.get('buyers', '')}")
    lines.append(f"- **Documents filed:** {len(filed)}")
    lines.append(f"- **Milestones:** {len(milestones)}")
    lines.append(f"- **Follow-ups:** {len(actions)}")
    lines.append("")
    lines.append("## Filed documents")
    by_dest = {}
    for f in filed:
        by_dest.setdefault(f.get("destination", ""), []).append(f)
    for dest, items in by_dest.items():
        lines.append(f"### {dest}")
        for f in items:
            lines.append(f"- {f['filename']}  _({f.get('category','')}, conf {f.get('confidence','')})_")
        lines.append("")
    if missing:
        lines.append("> Note: could not locate source file for: " + ", ".join(missing))
        lines.append("")
    lines.append("## Milestone calendar")
    for m in sorted(milestones, key=lambda x: x.get("date", "")):
        rem = f" · remind {m['reminder_days_before']}d before" if m.get("reminder_days_before") else ""
        lines.append(f"- **{m.get('date','')}** — {m.get('name','')}{rem}")
    lines.append("")
    lines.append("_Import `calendar.ics` into Google/Apple Calendar to load these with reminders._")
    return "\n".join(lines) + "\n"
