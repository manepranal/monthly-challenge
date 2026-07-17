"""Build the WATCH-MODE demo video (challenge-4's Otto-style pipeline).

Companion to make_demo.py (the one-shot cut) — same technique: HTML/CSS scenes
screenshot with headless Chrome, synced macOS `say` narration, ffmpeg assembly.
Reuses make_demo's shoot/narrate/build_clip helpers; only the scenes differ.
The terminal-replay and board scenes show REAL output from the verified
2026-07-15 live run (watch + drip concurrently), not mockups.

    python3 make_watch_demo.py      # -> out/_watch_demo/watch-mode-demo.mp4

Env: VOICE=Daniel VOICE_RATE=188 DEMO_SILENT=1 (same as make_demo.py)
"""

import shutil
import subprocess
import sys
from pathlib import Path

import make_demo as md

OUT = Path(__file__).parent / "out" / "_watch_demo"
md.OUT = OUT  # shoot()/narrate() write into the module-level OUT

MAIL = "&#128231;"   # 📧
NOENTRY = "&#128683;"  # 🚫
EYES = "&#128064;"   # 👀
CHECK = "&#10003;"   # ✓

EXTRA_CSS = """
.lane { display:flex; align-items:center; gap:18px; margin:26px 0 10px; }
.state { padding:12px 26px; border-radius:12px; font-weight:800; font-size:30px;
  background:#1b2430; color:#9fb0c0; border:1px solid #23303d; }
.state.on { background:#0e2b26; color:#2dd4bf; border-color:#2dd4bf; }
.arrow { color:#5b6b7b; font-size:34px; font-weight:700; }
.cols { display:flex; gap:28px; margin-top:10px; }
.term2 { background:#0a0e14; border:1px solid #23303d; border-radius:16px;
  padding:26px 30px; font-family:'SF Mono','Menlo',monospace; font-size:22.5px;
  line-height:1.52; color:#c9d4e0; white-space:pre; flex:1;
  box-shadow:0 30px 80px rgba(0,0,0,.5); }
.tlabel { font-size:24px; color:#5b6b7b; font-weight:700; letter-spacing:2px;
  text-transform:uppercase; margin-bottom:10px; }
.alertcard { background:#131c26; border:1px solid #23303d; border-left:6px solid;
  border-radius:16px; padding:26px 32px; font-size:29px; line-height:1.45; }
.stat { background:#131c26; border:1px solid #23303d; border-radius:16px;
  padding:30px 36px; flex:1; text-align:center; }
.stat .n { font-size:76px; font-weight:800; color:#2dd4bf; }
.stat .l { font-size:27px; color:#9fb0c0; margin-top:6px; }
"""


def page(body: str) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<style>{md.CSS}{EXTRA_CSS}</style></head><body>{body}</body></html>")


def lane(active: str = "") -> str:
    steps = ["NEW", "FILED", "SCHEDULED", "DONE"]
    bits = []
    for s in steps:
        cls = "state on" if s == active or active == "all" else "state"
        bits.append(f"<span class='{cls}'>{s}</span>")
    return "<div class='lane'>" + "<span class='arrow'>&rarr;</span>".join(bits) + "</div>"


# --- scenes -----------------------------------------------------------------

def s_title() -> str:
    return page(f"""
    <div class='stage' style='justify-content:center'>
      <div class='kicker'>July AI Challenge &middot; Deal Organizer &middot; part two</div>
      <h1>Watch <span class='accent'>mode</span></h1>
      <div class='sub'>The pile was easy. Now it organizes the <b>stream</b> —<br>
      emails walk themselves across a board while the agent works.</div>
      {lane('all')}
      <div class='footer'>The Real Brokerage &middot; QA monthly challenge &middot; challenge-4</div>
    </div>""")


def s_stream() -> str:
    return page(f"""
    <div class='stage'>
      <div class='kicker'>The real problem isn't a pile</div>
      <h2>Chaos is a stream.</h2>
      <div class='grid' style='margin-top:34px'>
        <div class='card'><span class='rowlbl'>One-shot mode</span>
          <span class='dim' style='margin-left:auto'>organize the inbox once &nbsp;{CHECK}</span></div>
        <div class='card' style='border-color:#2dd4bf'>
          <span class='rowlbl accent'>Watch mode</span>
          <span class='dim' style='margin-left:auto'>emails keep landing — the organizer never stops</span></div>
      </div>
      <div class='sub' style='margin-top:44px'>{MAIL} contract &nbsp;&rarr;&nbsp; {MAIL} inspection &nbsp;&rarr;&nbsp;
      {MAIL} appraisal &nbsp;&rarr;&nbsp; {MAIL} CDA &nbsp;&rarr;&nbsp; every one carries a document, a deadline, or a to-do.</div>
    </div>""")


def s_otto() -> str:
    rails = [
        ("&#128274;", "One run per deal", "a lock file serializes the sweep — no double-work"),
        (NOENTRY, "Run budget", "3 tries per step, then parked with an alert — never a silent retry loop"),
        (EYES, "Human gate", "low-confidence filings stop and wait for approval — never auto-filed"),
    ]
    cards = "".join(
        f"<div class='card'><span style='font-size:40px'>{ic}</span>"
        f"<span class='rowlbl'>{t}</span><span class='dim' style='margin-left:auto;font-size:26px'>{d}</span></div>"
        for ic, t, d in rails
    )
    return page(f"""
    <div class='stage'>
      <div class='kicker'>Architecture borrowed from Otto — Real's ticket-to-production pipeline</div>
      <h2>Every email is a work item.</h2>
      {lane('all')}
      <div class='grid' style='margin-top:22px'>{cards}</div>
    </div>""")


def s_twoterm() -> str:
    left = (
        "<span class='dim'>$</span> ./run.sh drip\n\n"
        f"[drip] {MAIL} <span class='c2'>m1</span> landed &bull; “Fully executed contract”\n"
        f"[drip] {MAIL} <span class='c2'>m5</span> landed &bull; “Seller disclosures”\n"
        f"[drip] {MAIL} <span class='c2'>m6</span> landed &bull; “Quick questions before Saturday”\n"
        f"[drip] {MAIL} <span class='c2'>m2</span> landed &bull; “Inspection report ready”\n"
        f"[drip] {MAIL} <span class='c2'>m3</span> landed &bull; “Appraisal completed”\n"
        f"[drip] {MAIL} <span class='c2'>m4</span> landed &bull; “Commission CDA — ESC-88213”\n\n"
        "[drip] inbox fully delivered"
    )
    right = (
        "<span class='dim'>$</span> ./run.sh watch\n"
        "<span class='dim'>sweep: every 5s &middot; budget: 3/state</span>\n\n"
        "[<span class='y'>intake</span>  ] m1 &rarr; NEW\n"
        "[<span class='c2'>file</span>    ] m1 &rarr; FILED\n"
        "[<span class='y'>intake</span>  ] m5, m6 &rarr; NEW\n"
        "[<span class='c2'>schedule</span>] m1 &rarr; SCHEDULED <span class='dim'>(7 milestones)</span>\n"
        "[<span class='c2'>file</span>    ] m5 &rarr; FILED\n"
        "[<span class='g'>publish</span> ] m1 &rarr; DONE " + CHECK + "\n"
        "[<span class='c2'>file</span>    ] m2 &rarr; FILED\n"
        "<span class='dim'>&hellip; the sweep keeps walking the board &hellip;</span>\n"
        "[<span class='g'>publish</span> ] m4 &rarr; DONE " + CHECK
    )
    return page(f"""
    <div class='stage' style='justify-content:center'>
      <div class='kicker'>Real output &middot; two terminals, one live run</div>
      <div class='cols' style='margin-top:14px'>
        <div style='flex:1'><div class='tlabel'>emails arriving</div><div class='term2'>{left}</div></div>
        <div style='flex:1.15'><div class='tlabel'>the organizer</div><div class='term2'>{right}</div></div>
      </div>
    </div>""")


def s_board() -> str:
    rows = [
        ("m1", "Fully executed contract", "DONE", "g", "filed + calendared + published"),
        ("m5", "Seller disclosures", "SCHEDULED", "c2", "filed, dates extracted"),
        ("m6", "Quick questions (no attachment)", "SCHEDULED", "c2", "follow-ups only"),
        ("m2", "Inspection report", "FILED", "y", "awaiting schedule step"),
        ("m3", "Appraisal completed", "NEW", "dim", "just landed"),
        ("m4", "Commission CDA", "NEW", "dim", "just landed"),
    ]
    cards = "".join(
        f"<div class='card' style='padding:18px 32px'>"
        f"<span class='fname accent' style='min-width:70px'>{i}</span>"
        f"<span class='rowlbl'>{s}</span>"
        f"<span class='pill' style='margin-left:auto;background:#1b2430' ><span class='{cls}'>{st}</span></span>"
        f"<span class='dim' style='font-size:24px;min-width:330px;text-align:right'>{note}</span></div>"
        for i, s, st, cls, note in rows
    )
    return page(f"""
    <div class='stage'>
      <div class='kicker'>BOARD.md, mid-flight — four states live at once</div>
      <h2>The board tells the story.</h2>
      <div class='grid' style='gap:13px'>{cards}</div>
    </div>""")


def s_rails() -> str:
    return page(f"""
    <div class='stage' style='justify-content:center'>
      <div class='kicker'>Safe by design — a stuck email is never silent</div>
      <h2>The rails, in action.</h2>
      <div class='grid' style='gap:26px;margin-top:26px'>
        <div class='alertcard' style='border-left-color:#ff7b93'>
          {NOENTRY} <b>parked m3</b> — 3 attempts in FILED without progressing.
          It will not be retried automatically.<br>
          <span class='dim'>Resume with</span> <span class='fname accent'>./run.sh resume m3</span>
          <span class='dim'>after investigating.</span></div>
        <div class='alertcard' style='border-left-color:#e3c04b'>
          {EYES} <b>m1 needs review</b> — filing confidence 0.42 is below the 0.6 gate.<br>
          <span class='dim'>Nothing was filed. Approve with</span>
          <span class='fname accent'>./run.sh approve m1</span>
          <span class='dim'>— the agent never rubber-stamps its own review.</span></div>
      </div>
    </div>""")


def s_done() -> str:
    stats = "".join(
        f"<div class='stat'><div class='n'>{n}</div><div class='l'>{l}</div></div>"
        for n, l in [("5", "documents filed by content"),
                     ("9", "deadlines on the calendar"),
                     ("7", "follow-ups, ranked")]
    )
    return page(f"""
    <div class='stage'>
      <div class='kicker'>The inbox went quiet &middot; the board is clear</div>
      <h2>Everything where it belongs.</h2>
      <div class='lane'><span class='state'>NEW (0)</span><span class='arrow'>&rarr;</span>
        <span class='state'>FILED (0)</span><span class='arrow'>&rarr;</span>
        <span class='state'>SCHEDULED (0)</span><span class='arrow'>&rarr;</span>
        <span class='state on'>DONE (6)</span></div>
      <div class='cols' style='margin-top:30px'>{stats}</div>
      <div class='sub' style='margin-top:36px'>Plus a full audit trail: every move, every attempt,
      every alert — in <span class='fname accent'>BOARD.md</span> and <span class='fname accent'>ledger.json</span>.</div>
    </div>""")


def s_outro() -> str:
    return page("""
    <div class='stage' style='justify-content:center'>
      <div class='kicker'>challenge-4 &middot; deal organizer &middot; watch mode</div>
      <h1>Organizes the stream.<br><span class='accent'>Parks what's stuck. Asks when unsure.</span></h1>
      <div class='sub'>An Otto-style pipeline in four small Python files —<br>
      the same two Claude tool-calls, now running on every email as it lands.</div>
      <div class='footer'>AI-powered &middot; demo-able &middot; solves a real organizational pain</div>
    </div>""")


SCENES = [
    ("title", s_title,
     "The Deal Organizer again — but this time it's watch mode. The pile was easy; now it organizes the stream."),
    ("stream", s_stream,
     "Real chaos isn't a pile you sort once. Emails keep landing, and every one carries a document, a deadline, or a to-do."),
    ("otto", s_otto,
     "The architecture is borrowed from Otto, Real's ticket-to-production pipeline. Every email is a work item with a state, each step moves it one column, and three rails keep it safe: a lock, a retry budget, and a human gate."),
    ("twoterm", s_twoterm,
     "Two terminals, one live run. On the left, emails drip in. On the right, the organizer sweeps every five seconds — intake, file, schedule, publish — one step per email per tick, never waiting."),
    ("board", s_board,
     "Here's the board mid-flight: the first email is already done while the last two are still landing. Four states live at once, every move logged."),
    ("rails", s_rails,
     "And when something goes wrong, it's loud. An email that keeps failing is parked with an alert and the exact resume command. A filing Claude isn't confident about stops and waits for approval — the agent never rubber-stamps its own review."),
    ("done", s_done,
     "When the inbox goes quiet, the board is clear: five documents filed, nine deadlines on the calendar, seven follow-ups ranked — with a full audit trail of how it got there."),
    ("outro", s_outro,
     "Organizes the stream. Parks what's stuck. Asks when it isn't sure. That's watch mode."),
]


def main() -> None:
    if not md.CHROME:
        sys.exit("No Chrome found — set CHROME_BIN.")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    clips = []
    for i, (name, fn, line) in enumerate(SCENES):
        print(f"  [{i+1}/{len(SCENES)}] {name} ...", flush=True)
        png = OUT / f"{name}.png"
        md.shoot(fn(), png)
        if md.SILENT:
            audio, dur = None, 4.0
        else:
            audio, adur = md.narrate(line, name)
            dur = max(3.6, adur + 1.0)
        clip = OUT / f"{name}.mp4"
        md.build_clip(png, audio, dur, clip)
        clips.append(clip)

    # Same concat rule as make_demo.py: RE-ENCODE audio (never -c copy).
    listf = OUT / "concat.txt"
    listf.write_text("".join(f"file '{c.name}'\n" for c in clips))
    final = OUT / "watch-mode-demo.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-b:a", "192k", "-ar", "44100", "-movflags", "+faststart", str(final)],
        check=True, capture_output=True, cwd=str(OUT))

    dur = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(final)], capture_output=True, text=True).stdout.strip()
    print(f"\n  Done -> {final}  ({float(dur):.1f}s)")


if __name__ == "__main__":
    main()
