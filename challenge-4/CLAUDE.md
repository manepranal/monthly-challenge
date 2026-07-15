# Deal Organizer (July Challenge — "Get your agents organized")

> A real-estate agent's deal inbox is a storm of emails, contracts, reports, and
> deadlines. Point Claude at it → every attachment is **filed into the right
> folder**, every contract deadline becomes a **calendar reminder**, and every
> "please do X" turns into a **follow-up** — with nothing sent and nothing moved
> without the agent's say-so.

This is the July entry for the QA monthly challenge. The theme is **"help agents
get organized."** It implements two of the brief's seed ideas at once —
*inbox → Drive filing* and *contract → calendar* — over one realistic deal, so
the whole story ("I got a folder full of chaos → now it's organized") is
demoable in a single run.

## What it does

Two modes over the same AI jobs:

```
# One-shot — organize a PILE (the original demo)
$ ./run.sh                       # the sample deal in examples/ (123 Maple Ave)
$ ./run.sh examples              # same, explicit
$ ./run.sh /path/to/deal-inbox   # any folder with inbox.json + attachments/

# Watch — organize a STREAM (Otto-style pipeline; see "Watch mode" below)
$ ./run.sh watch                 # terminal 1: the organizer, sweeping every 5s
$ ./run.sh drip                  # terminal 2: sample emails arrive one by one
```

Given a deal's inbox (6 emails, 5 attachments), it produces under `./out/<deal>/`:

- A **tidy deal folder** — each attachment copied into `Contracts & Agreements/`,
  `Inspections/`, `Financing & Appraisal/`, `Accounting & Commissions/`, or
  `Disclosures/`, chosen from the **document's content**.
- **`calendar.ics`** — every contract milestone (attorney review, inspection,
  appraisal, financing, walk-through, closing) as an all-day event with a
  reminder, importable straight into Google/Apple Calendar.
- **`FOLLOW_UPS.md`** — the "you still need to do this" items pulled from the
  messages (e.g. *reply to the buyer about the Saturday inspection*).
- **`SUMMARY.md`** — the one-page recap of what went where.

## Architecture

| File | Role |
|------|------|
| `fetch.py` | Load the inbox. Reads `inbox.json` + the real attachment files, extracting each PDF's text (pypdf, with a `.txt` fallback so extraction never breaks the demo). This is the offline stand-in for a live Gmail pull. |
| `classify.py` | **AI job #1 — file it.** One forced `tool_use` call (`organize_inbox`) reads the whole inbox and returns, per attachment, a `category` + a `destination` folder chosen from a fixed **enum**, plus `action_items` for anything a message asks the agent to do. Routing is by content, not filename. |
| `dates.py` | **AI job #2 — calendar it.** One forced `tool_use` call (`extract_milestones`) reads the executed contract and returns every deadline as `{name, ISO date, category, source, reminder_days_before}`. Conservative: never invents a date; the contract wins ties. |
| `organize.py` | The executor. Builds the folder tree, copies each attachment into its destination, writes a valid `calendar.ics` (with `VALARM` reminders), `FOLLOW_UPS.md`, and `SUMMARY.md`. Writes **only under `./out`** — nothing else is touched. |
| `main.py` | Orchestrator: fetch → classify → dates → organize → print the recap. |
| `.claude/skills/file-documents.md` | The filing taxonomy + rules the classifier follows. |
| `.claude/skills/build-deal-calendar.md` | The milestone taxonomy + reminder policy the date extractor follows. |
| `examples/` | A realistic buyer-side deal — `inbox.json` + 5 generated PDF attachments (`_make_fixtures.py` regenerates them). |

## Pipeline

1. `fetch.load_inbox(src)` → `{deal, emails:[{…, attachments:[{filename, path, text}]}]}`.
   PDF text is extracted so Claude can read each document.
2. `classify.organize(inbox)` → `{filings:[…], action_items:[…]}` via the
   `organize_inbox` tool. Each filing names a `destination` from the enum.
3. `dates.extract(inbox)` → `{milestones:[…]}` via the `extract_milestones` tool,
   read from the contract (+ corroborating emails).
4. `organize.build(...)` → copies documents into folders, writes `calendar.ics`,
   `FOLLOW_UPS.md`, `SUMMARY.md`, and returns the recap `main.py` prints.

## Concepts demonstrated

| Concept | Where it shows up |
|---------|--------------------|
| **Tools** | `classify.py` and `dates.py` — two forced `tool_use` schemas turn a messy inbox into typed plans (an `enum`-constrained filing plan + an ISO-date milestone list) the executor can trust. |
| **Skills** | Two `.claude/skills/*.md` files encode the *domain rules* — the filing taxonomy and the reminder policy — so the AI's choices are governed, deterministic, and auditable. |
| **Agents** | This project — `CLAUDE.md` defines a Claude Code agent you can `cd` into and run. It reads an inbox and *acts* (files, schedules, flags), but stops short of sending anything. |
| **Orchestration** | `main.py` chains two independent Claude calls (file, then schedule) plus a deterministic executor — the shape of a real assistant. |
| **Memory** | The agent's persona (a Real Brokerage buyer's agent) and the Google-account safety rules for the live demo come from user memory, not re-discovery. |

## Watch mode — the Otto-style pipeline

The one-shot run organizes a pile; real chaos is a *stream*. Watch mode borrows
its architecture from **Realtyka/otto** (Real's ticket-to-production pipeline):
every email is a work item that walks itself across a board, a sweep loop
retries anything stalled, and safety rails park anything stuck.

```
NEW ──file──▶ FILED ──schedule──▶ SCHEDULED ──publish──▶ DONE
 │                                                (regenerates calendar.ics,
 └──▶ NEEDS REVIEW (👀 human gate:                 FOLLOW_UPS.md, SUMMARY.md
      low-confidence filing — `approve`)           from the ledger)

 any state ──▶ 🚫 parked (run budget exhausted — `resume`)
```

| Otto (cloud) | Watch mode (local) |
|---|---|
| YouTrack ticket State = source of truth | `out/<deal>/ledger.json` per-email state |
| 🤖 Otto Board | `BOARD.md`, re-rendered every tick |
| onChange dispatch + 15-min onSchedule sweep | intake scan + sweep loop (`OTTO_SWEEP_SEC`, default 5s) |
| `otto-in-progress` tag | `.otto-in-progress` lock file per deal |
| run-budget gate → `otto-blocked` park + Slack alert | per-(email, state) dispatch counter, cap `OTTO_MAX_RUNS_PER_STATE` (3) → parked + `ALERTS.md` |
| Slack channel (`post.sh`) | `ALERTS.md` + console narration |
| `Requires UI QA = No` scope gate | confidence gate: filing < `OTTO_CONFIDENCE_GATE` (0.6) → `NEEDS REVIEW`, waits for a human `approve` |
| otto-1…4 skills, "checks once, never waits" | `file → schedule → publish` steps; one step per email per tick, the sweep is the loop |

Design rules carried over from Otto: steps are **idempotent** (publish
regenerates every artifact from the ledger, so a retry converges instead of
duplicating); the budget counts **at dispatch time**, so even a crashing step
stays bounded; state changes **reset** the budget; and a park is never silent —
it always lands in `ALERTS.md` with the exact resume command. One deliberate
improvement on Otto: the agent doesn't get to rubber-stamp its own human gate —
a filing below the confidence threshold stops and waits, it is never auto-filed.

```
$ ./run.sh watch                       # terminal 1 — the organizer
$ ./run.sh drip                        # terminal 2 — emails arrive every 20s
$ ./run.sh status                      # print the board
$ ./run.sh approve m3                  # clear a NEEDS REVIEW gate (files plan as-is)
$ ./run.sh resume m3                   # un-park with a fresh budget
```

Reset a demo with `rm -rf live-inbox out/<deal-slug>`. Watch-mode files:
`pipeline.py` (harness: intake, lock, budget gate, tick, sweep),
`steps.py` (the three steps), `ledger.py` (state store + board + alerts),
`drip.py` (demo feeder). `live-inbox/` is the simulated Gmail; in the live
variant the intake scan becomes a Gmail MCP search, and everything downstream
is unchanged.

## Live Google mode (Gmail + Drive + Calendar via MCP)

The offline run proves the logic end-to-end with zero external writes. To make it
**live**, the same two plan objects drive the real Google Workspace through the
Gmail / Drive / Calendar MCP tools:

- **Gmail** replaces `fetch.py`: search the agent's inbox for a deal, download the
  message bodies + attachments (instead of reading `examples/`).
- **Google Drive** replaces the local folder tree: create a `Deal Organizer — <address>`
  folder with the six sub-folders and upload each attachment into its destination.
- **Google Calendar** replaces `calendar.ics`: create each milestone as an event
  with its reminder.

**Safety rules for the live demo (from memory):** only ever *write* to a clearly
labeled demo Drive folder and a demo calendar; never delete or modify existing
files/events; read-only against the real inbox. The classification + date
extraction (the AI parts) are identical — only the I/O changes.

## Setup

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # or rely on the `claude` CLI fallback
pip3 install -r requirements.txt
./run.sh                                 # organizes the sample deal
```

- If the SDK key is missing or 401s, every Claude step falls back to the `claude`
  CLI (OAuth), so the demo still runs end-to-end.
- Override the model with `DEAL_MODEL=claude-opus-4-8 ./run.sh` (default
  `claude-sonnet-5`).
- Regenerate the sample PDFs with `pip3 install fpdf2 && python3 examples/_make_fixtures.py`.

## Demo limitations (called out so the demo is honest)

- **The offline run files copies, not the originals, and never sends anything.**
  Filing is deliberately a read-and-copy operation. Forwarding a CDA to title or
  replying to a client is surfaced as an *action item* for the agent to approve —
  the agent doesn't take irreversible or outward-facing actions on its own.
- **Date extraction is assistive, not legal advice.** It reads the deadlines the
  contract states; the agent and their attorney remain responsible for the dates.
  It will *skip* a contingency that has no explicit date rather than guess one.
- **PDF text is extracted, not OCR'd.** The sample contracts are text-based PDFs.
  A scanned/photographed document would need an OCR/vision step first (the same
  approach challenge-2 used).
- **The demo inbox is fixtures.** `examples/` is a crafted but realistic deal so
  the run is reproducible and touches no private mail. Point `./run.sh` at a real
  exported inbox folder, or wire the live Gmail MCP path above, to run it for real.

## When to use this agent (Claude Code)

When an agent hands you a pile of deal emails/attachments and wants it organized,
use this project. Run `./run.sh <inbox>` and report:

1. What was filed and where (the folder tree).
2. The milestone calendar (and confirm `calendar.ics` was written).
3. The open follow-ups, highest priority first.

Never forward a document or reply to a client on the agent's behalf without
showing them the action item and getting a go-ahead first.
