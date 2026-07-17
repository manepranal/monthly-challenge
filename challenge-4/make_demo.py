"""Build a self-contained demo video for the Deal Organizer (challenge-4).

Same technique as the June entry: each scene is composed as HTML/CSS, screenshot
with headless Chrome (no image/video model), narrated with a synced macOS `say`
voice, and assembled with ffmpeg. Fully offline and deterministic.

    python3 make_demo.py            # -> out/_demo/deal-organizer-demo.mp4

Env:
    VOICE=Daniel  VOICE_RATE=188   # macOS TTS voice + words-per-minute
    DEMO_SILENT=1                  # skip narration (silent, uniform pacing)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "out" / "_demo"
W, H = 1920, 1080
VOICE = os.environ.get("VOICE", "Daniel")
RATE = os.environ.get("VOICE_RATE", "188")
SILENT = os.environ.get("DEMO_SILENT") == "1"

CHROME = os.environ.get("CHROME_BIN") or next(
    (c for c in [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ] if Path(c).exists()),
    None,
)

# --- shared styling --------------------------------------------------------
CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
html,body { width:1920px; height:1080px; overflow:hidden;
  font-family:-apple-system,'SF Pro Display','Helvetica Neue',Arial,sans-serif;
  background:#0d1117; color:#e6edf3; }
.stage { width:1920px; height:1080px; padding:96px 120px; position:relative;
  display:flex; flex-direction:column; }
.kicker { color:#2dd4bf; font-size:30px; font-weight:700; letter-spacing:3px;
  text-transform:uppercase; margin-bottom:22px; }
h1 { font-size:104px; font-weight:800; line-height:1.02; letter-spacing:-2px; }
h2 { font-size:66px; font-weight:800; letter-spacing:-1px; margin-bottom:14px; }
.sub { font-size:38px; color:#9fb0c0; font-weight:500; margin-top:24px; }
.accent { color:#2dd4bf; }
.footer { position:absolute; left:120px; bottom:64px; color:#5b6b7b;
  font-size:26px; letter-spacing:1px; }
.badge { display:inline-block; padding:6px 18px; border-radius:999px;
  font-size:24px; font-weight:700; }
.tag { display:inline-block; padding:4px 14px; border-radius:8px; font-size:24px;
  font-weight:600; background:#1b2430; color:#7fe3d4; margin-left:12px; }
.grid { display:flex; flex-direction:column; gap:18px; margin-top:20px; }
.card { background:#131c26; border:1px solid #23303d; border-radius:16px;
  padding:26px 32px; display:flex; align-items:center; gap:26px; }
.term { background:#0a0e14; border:1px solid #23303d; border-radius:16px;
  padding:34px 40px; font-family:'SF Mono','Menlo',monospace; font-size:29px;
  line-height:1.5; color:#c9d4e0; white-space:pre; margin-top:16px;
  box-shadow:0 30px 80px rgba(0,0,0,.5); }
.dots { position:absolute; top:22px; left:28px; }
.dots span { display:inline-block; width:15px; height:15px; border-radius:50%;
  margin-right:9px; }
.g { color:#3fb950; } .y { color:#d29922; } .c2 { color:#2dd4bf; }
.dim { color:#7d8ea0; }
.fname { font-family:'SF Mono','Menlo',monospace; font-size:27px; color:#e6edf3; }
.folder { font-size:30px; font-weight:700; }
.pill { font-size:22px; padding:3px 12px; border-radius:7px; font-weight:700; }
.hi { background:#3a1520; color:#ff7b93; } .md { background:#2a2410; color:#e3c04b; }
.date { font-family:'SF Mono','Menlo',monospace; font-weight:800; font-size:30px;
  color:#2dd4bf; min-width:150px; }
.rowlbl { font-size:31px; font-weight:600; }
.bell { color:#d29922; font-size:24px; margin-left:auto; white-space:nowrap; }
"""

FOLDER_ICON = "&#128193;"  # 📁
DOC_ICON = "&#128196;"     # 📄
BELL = "&#128276;"         # 🔔


def page(body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"


# --- scene bodies ----------------------------------------------------------
def s_title() -> str:
    return page("""
    <div class='stage' style='justify-content:center'>
      <div class='kicker'>July AI Challenge &middot; Get agents organized</div>
      <h1>Deal <span class='accent'>Organizer</span></h1>
      <div class='sub'>Point Claude at a deal's inbox &rarr; every document filed,<br>every deadline on the calendar, every follow-up surfaced.</div>
      <div class='footer'>The Real Brokerage &middot; QA monthly challenge &middot; challenge-4</div>
    </div>""")


def s_problem() -> str:
    rows = "".join(
        f"<div class='card'><span class='fname'>&#9993;&nbsp; {frm}</span>"
        f"<span class='dim' style='margin-left:auto'>{att}</span></div>"
        for frm, att in [
            ("Dana Cole — Fully executed contract", "Purchase_Agreement.pdf"),
            ("ProHome Inspections — Report ready", "Inspection_Report.pdf"),
            ("Meridian Home Loans — Appraisal", "Appraisal_Report.pdf"),
            ("Real Brokerage — Commission (CDA)", "Commission_Statement.pdf"),
            ("Robert Feldman, Esq. — Disclosures", "Sellers_Disclosure.pdf"),
            ("Priya Shah — Quick questions", "(no attachment)"),
        ]
    )
    return page(f"""
    <div class='stage'>
      <div class='kicker'>One deal &middot; 123 Maple Ave, Rye NY</div>
      <h2>The inbox is the chaos.</h2>
      <div class='sub' style='margin-top:6px'>6 emails &middot; 5 attachments &middot; 7 deadlines buried in a contract</div>
      <div class='grid'>{rows}</div>
    </div>""")


def s_terminal() -> str:
    t = (
        "<span class='dim'>$</span> ./run.sh\n"
        "<span class='c2'>====================================================</span>\n"
        "  DEAL ORGANIZER\n"
        "<span class='c2'>====================================================</span>\n\n"
        "Deal:   123 Maple Avenue, Rye, NY 10580\n"
        "Inbox:  6 emails, 5 attachments\n\n"
        "<span class='dim'>[1/3]</span> Filing documents with Claude ...\n"
        "        <span class='g'>5 documents routed, 5 follow-ups found</span>\n"
        "<span class='dim'>[2/3]</span> Extracting milestone dates with Claude ...\n"
        "        <span class='g'>7 milestones extracted</span>\n"
        "<span class='dim'>[3/3]</span> Building deal folder, calendar, follow-ups ...\n\n"
        "  <span class='g'>ORGANIZED &#10003;</span>"
    )
    return page(f"""
    <div class='stage' style='justify-content:center'>
      <div class='kicker'>Two Claude tool-calls do the thinking</div>
      <div class='term'><div class='dots'><span class='y' style='background:#ff5f56'></span><span style='background:#ffbd2e'></span><span style='background:#27c93f'></span></div>{t}</div>
    </div>""")


def s_filed() -> str:
    items = [
        ("Contracts &amp; Agreements", "Purchase_Agreement_123_Maple_Ave.pdf", "Contract"),
        ("Inspections", "Inspection_Report_123_Maple.pdf", "Inspection Report"),
        ("Financing &amp; Appraisal", "Appraisal_Report_123_Maple.pdf", "Appraisal"),
        ("Accounting &amp; Commissions", "Commission_Statement_123_Maple.pdf", "Commission Statement"),
        ("Disclosures", "Sellers_Disclosure_123_Maple.pdf", "Disclosure"),
    ]
    rows = "".join(
        f"<div class='card'><span class='folder accent'>{FOLDER_ICON} {folder}/</span>"
        f"<span class='fname'>{DOC_ICON} {doc}</span><span class='tag'>{cat}</span></div>"
        for folder, doc, cat in items
    )
    return page(f"""
    <div class='stage'>
      <div class='kicker'>Filed by content, not filename</div>
      <h2>Every document, in the right folder.</h2>
      <div class='grid'>{rows}</div>
    </div>""")


def s_calendar() -> str:
    ms = [
        ("Jul 08", "Contract Effective Date", ""),
        ("Jul 11", "Attorney Review Deadline", "remind 3d before"),
        ("Jul 18", "Home Inspection Contingency", "remind 3d before"),
        ("Jul 25", "Appraisal Contingency", "remind 3d before"),
        ("Aug 07", "Mortgage Commitment", "remind 3d before"),
        ("Sep 04", "Final Walk-Through", "remind 7d before"),
        ("Sep 05", "Closing Date", "remind 7d before"),
    ]
    rows = "".join(
        f"<div class='card' style='padding:18px 32px'><span class='date'>{d}</span>"
        f"<span class='rowlbl'>{name}</span>"
        + (f"<span class='bell'>{BELL} {r}</span>" if r else "<span class='bell dim'>info</span>")
        + "</div>"
        for d, name, r in ms
    )
    return page(f"""
    <div class='stage'>
      <div class='kicker'>Pulled from the executed contract</div>
      <h2>Every deadline, on the calendar.</h2>
      <div class='grid' style='gap:12px'>{rows}</div>
    </div>""")


def s_followups() -> str:
    items = [
        ("HIGH", "hi", "Share the inspection report with the buyers", "before 7/18"),
        ("HIGH", "hi", "Reply to Priya: confirm Saturday inspection + mover timing", "before Sat"),
        ("HIGH", "hi", "Get signed disclosures back to keep financing on track", "before 8/7"),
        ("HIGH", "hi", "Review the CDA split &amp; forward to title", "before 9/5"),
        ("MED", "md", "Have buyers acknowledge the seller disclosures", "ASAP"),
    ]
    rows = "".join(
        f"<div class='card'><span class='pill {cls}'>{lbl}</span>"
        f"<span class='rowlbl'>{task}</span>"
        f"<span class='dim' style='margin-left:auto'>{due}</span></div>"
        for lbl, cls, task, due in items
    )
    return page(f"""
    <div class='stage'>
      <div class='kicker'>Grounded in the messages — nothing invented</div>
      <h2>What's still on the agent.</h2>
      <div class='grid'>{rows}</div>
    </div>""")


def s_outro() -> str:
    return page("""
    <div class='stage' style='justify-content:center'>
      <div class='kicker'>challenge-4 &middot; deal organizer</div>
      <h1>Files itself.<br><span class='accent'>Never misses a date.</span></h1>
      <div class='sub'>Claude reads the inbox &rarr; files every document &rarr; builds the deadline calendar &rarr; surfaces the follow-ups.<br>One run. Nothing sent without the agent's say-so.</div>
      <div class='footer'>AI-powered &middot; demo-able &middot; solves a real organizational pain</div>
    </div>""")


def s_built() -> str:
    rows = [
        ("fetch.py", "load the inbox — emails + PDF attachments", ""),
        ("classify.py", "files each document by its content", "Claude"),
        ("dates.py", "extracts every contract deadline", "Claude"),
        ("organize.py", "builds folders + calendar + follow-ups", ""),
        (".claude/skills/", "the filing + reminder rules", "Skills"),
    ]
    cards = "".join(
        f"<div class='card'><span class='fname accent' style='min-width:300px'>{f}</span>"
        f"<span class='dim' style='font-size:29px'>{r}</span>"
        + (f"<span class='tag' style='margin-left:auto'>{t}</span>" if t else "")
        + "</div>"
        for f, r, t in rows
    )
    return page(f"""
    <div class='stage'>
      <div class='kicker'>A handful of small Python files</div>
      <h2>How it's built.</h2>
      <div class='grid'>{cards}</div>
    </div>""")


def s_toolcalls() -> str:
    t1 = ("<span class='c2'>organize_inbox</span>(inbox)  &rarr;  {\n"
          "    filings[]       <span class='dim'>file each attachment by content</span>\n"
          "    action_items[]  <span class='dim'>surface the follow-ups</span>\n"
          "}")
    t2 = ("<span class='c2'>extract_milestones</span>(contract)  &rarr;  {\n"
          "    milestones[]    <span class='dim'>every deadline as an ISO date + reminder</span>\n"
          "}")
    return page(f"""
    <div class='stage'>
      <div class='kicker'>Two forced tool-calls do the thinking</div>
      <h2>Claude returns typed plans.</h2>
      <div class='grid' style='gap:24px'>
        <div class='term' style='margin-top:6px'>{t1}</div>
        <div class='term' style='margin-top:0'>{t2}</div>
      </div>
    </div>""")


SCENES = [
    ("title", s_title, "This is the Deal Organizer — July's answer to helping real-estate agents get organized."),
    ("built", s_built, "Under the hood it's just a few small Python files — one loads the inbox, two call Claude, and one files everything and builds the calendar."),
    ("toolcalls", s_toolcalls, "The thinking is two Claude tool-calls: one files each document by its content, the other reads the contract and pulls out every deadline."),
    ("problem", s_problem, "A single deal buries an agent in email: the contract, the inspection report, the appraisal, the commission statement, disclosures — and seven deadlines hidden in the fine print."),
    ("terminal", s_terminal, "Point Claude at the inbox. In one run it reads every message and every attachment, then organizes the whole deal."),
    ("filed", s_filed, "Every document is filed by what's inside it — the contract, the inspection, the appraisal, the commission statement, and the disclosures each land in the right folder."),
    ("calendar", s_calendar, "Every deadline in the contract becomes a calendar reminder — attorney review, inspection, appraisal, financing, walk-through, and closing — so nothing slips."),
    ("followups", s_followups, "And whatever is still on the agent's plate is surfaced as a follow-up, highest priority first, grounded in the actual emails."),
    ("outro", s_outro, "Files itself. Never misses a date. That's the Deal Organizer."),
]


# --- rendering + assembly --------------------------------------------------
def shoot(html: str, png: Path) -> None:
    tmp = OUT / "_page.html"
    tmp.write_text(html)
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
         f"--screenshot={png}", f"--window-size={W},{H}",
         "--force-device-scale-factor=1", str(tmp)],
        check=True, capture_output=True,
    )
    if not png.exists():
        raise RuntimeError(f"Chrome returned 0 but wrote no screenshot for {png.name}")


def narrate(text: str, stem: str) -> tuple[Path, float]:
    aiff = OUT / f"{stem}.aiff"
    subprocess.run(["say", "-v", VOICE, "-r", RATE, "-o", str(aiff), text], check=True)
    dur = float(subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(aiff)],
        check=True, capture_output=True, text=True).stdout.strip())
    return aiff, dur


def build_clip(png: Path, audio: Path, dur: float, out: Path) -> None:
    frames = max(1, int(dur * 30))
    outst = max(0.1, dur - 0.4)
    vf = (
        f"[0:v]scale={W}:{H},setsar=1,"
        f"zoompan=z='min(zoom+0.00035,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps=30,"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={outst}:d=0.4,format=yuv420p[v]"
    )
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(png)]
    if audio:
        cmd += ["-i", str(audio)]
        af = f"[1:a]apad=whole_dur={dur},afade=t=out:st={outst}:d=0.4[a]"
        cmd += ["-filter_complex", f"{vf};{af}", "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-filter_complex", vf, "-map", "[v]"]
    cmd += ["-t", f"{dur}", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "44100"]
    cmd += [str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def main() -> None:
    if not CHROME:
        sys.exit("No Chrome found — set CHROME_BIN.")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    clips = []
    for i, (name, fn, line) in enumerate(SCENES):
        print(f"  [{i+1}/{len(SCENES)}] {name} ...", flush=True)
        png = OUT / f"{name}.png"
        shoot(fn(), png)
        if SILENT:
            audio, dur = None, 4.0
        else:
            audio, adur = narrate(line, name)
            dur = max(3.6, adur + 1.0)
        clip = OUT / f"{name}.mp4"
        build_clip(png, audio, dur, clip)
        clips.append(clip)

    # concat — RE-ENCODE audio (a plain -c copy across separately-encoded AAC
    # parts leaves timestamp gaps that QuickTime mutes entirely).
    listf = OUT / "concat.txt"
    listf.write_text("".join(f"file '{c.name}'\n" for c in clips))
    final = OUT / "deal-organizer-demo.mp4"
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
