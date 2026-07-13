"""Presenter cut of the Deal Organizer demo — same recipe as the June entry.

Takes a webcam recording of you narrating the 7 scene lines and rebuilds the
demo so it looks like you're presenting it: your face as a circular bubble in
the lower-right, YOUR cleaned voice as the narration, and each scene timed to
the line you speak for it (detected from the ~1s pauses between lines).

    python3 make_presenter.py [recording.mov]

Prereqs: run `make_demo.py` first (it renders the 7 scene stills into
out/_demo/). Needs ffmpeg. Auto-detects the recording if no path is given.

Tuning env vars:
    CROP_EXPR  ffmpeg crop for the face square (default: centered ~0.7*height square)
    NOISE_DB   silence threshold for pause detection (default -35dB)
    MIN_SIL    min pause length in seconds to count as a scene break (default 0.45)
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
D = ROOT / "out" / "_demo"
SCENES = ["title", "built", "toolcalls", "problem", "terminal", "filed", "calendar", "followups", "outro"]

# lower-right bubble: 360px circle with a 56px margin on a 1920x1080 frame
OVERLAY_XY = "1504:664"
BUBBLE = (
    "scale=360:360,format=rgba,geq="
    "r='if(lte(hypot(X-180\\,Y-180)\\,172)\\, r(X\\,Y)\\, 255)':"
    "g='if(lte(hypot(X-180\\,Y-180)\\,172)\\, g(X\\,Y)\\, 255)':"
    "b='if(lte(hypot(X-180\\,Y-180)\\,172)\\, b(X\\,Y)\\, 255)':"
    "a='if(lte(hypot(X-180\\,Y-180)\\,180)\\,255\\,0)'"
)
# grab a centered, slightly-high square from the source (face is usually upper-middle)
CROP_EXPR = os.environ.get("CROP_EXPR", "ih*0.7:ih*0.7:(iw-ih*0.7)/2:ih*0.04")
NOISE_DB = os.environ.get("NOISE_DB", "-35")
MIN_SIL = float(os.environ.get("MIN_SIL", "0.45"))

CANDIDATES = [
    ROOT / "recording.mov",
    Path.home() / "Documents" / "July-demo-face.mov",
    Path.home() / "Desktop" / "July-demo-face.mov",
    Path.home() / "Downloads" / "July-demo-face.mov",
]


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def dur(path) -> float:
    r = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(r.stdout.strip())


def find_recording() -> Path:
    if len(sys.argv) > 1:
        p = Path(sys.argv[1]).expanduser()
        if not p.exists():
            sys.exit(f"Recording not found: {p}")
        return p
    for c in CANDIDATES:
        if c.exists():
            return c
    sys.exit("No recording found. Pass a path or save to ~/Documents/July-demo-face.mov")


def clean_voice(rec: Path) -> Path:
    """Extract + studio-clean the narration to ~-14 LUFS (mirrors clean_voice.sh)."""
    out = D / "voice_clean.m4a"
    # highpass to cut rumble, gentle de-ess/compand, loudnorm to broadcast level
    af = ("highpass=f=80,afftdn=nf=-25,"
          "acompressor=threshold=-18dB:ratio=3:attack=5:release=120,"
          "loudnorm=I=-14:TP=-1.5:LRA=11")
    r = sh(["ffmpeg", "-y", "-i", str(rec), "-vn", "-af", af,
            "-ar", "48000", "-c:a", "aac", "-b:a", "192k", str(out)])
    if r.returncode != 0:
        sys.exit("voice clean failed:\n" + r.stderr[-800:])
    return out


def scene_durations(voice: Path, total: float) -> list:
    """Split the narration into 7 scene windows using the pauses between lines.
    Cut points fall in the MIDDLE of each pause so scenes never cut mid-word."""
    # Explicit override (scene start-times mapped from a whisper transcript of
    # the narration) — the reliable path when the room has too many word-gaps for
    # silencedetect to isolate the 7 lines. Values are scaled to the real total.
    if os.environ.get("DURS"):
        vals = [float(x) for x in os.environ["DURS"].split(",")]
        if len(vals) != len(SCENES):
            sys.exit(f"DURS needs {len(SCENES)} comma-separated values")
        scale = total / sum(vals)
        durs = [round(v * scale, 3) for v in vals]
        print(f"  using DURS override -> {durs}")
        return durs

    r = sh(["ffmpeg", "-i", str(voice), "-af",
            f"silencedetect=noise={NOISE_DB}dB:d={MIN_SIL}", "-f", "null", "-"])
    log = r.stderr
    sil = []
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", log)]
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else total
        sil.append((s, e))

    # speech spans = complement of silence
    spans, cur = [], 0.0
    for s, e in sil:
        if s > cur + 0.05:
            spans.append((cur, s))
        cur = max(cur, e)
    if cur < total - 0.05:
        spans.append((cur, total))

    if len(spans) == len(SCENES):
        cuts = [0.0]
        for i in range(1, len(spans)):
            cuts.append((spans[i - 1][1] + spans[i][0]) / 2.0)
        cuts.append(total)
        durs = [round(cuts[i + 1] - cuts[i], 3) for i in range(len(SCENES))]
        print(f"  synced: {len(spans)} spoken lines -> scene durations {durs}")
        return durs

    print(f"  (!) found {len(spans)} spoken chunks, expected {len(SCENES)} — "
          f"falling back to equal split. Adjust NOISE_DB / MIN_SIL or re-record "
          f"with clearer pauses.")
    each = round(total / len(SCENES), 3)
    return [each] * len(SCENES)


def build(rec: Path, voice: Path, durs: list) -> Path:
    for name in SCENES:
        if not (D / f"{name}.png").exists():
            sys.exit(f"Missing scene still {name}.png — run make_demo.py first.")
    total = sum(durs)
    out = ROOT / "out" / "_demo" / "deal-organizer-presenter.mp4"

    cmd = ["ffmpeg", "-y"]
    for name, d in zip(SCENES, durs):
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{d}", "-i", str(D / f"{name}.png")]
    cmd += ["-i", str(rec)]        # index = len(SCENES)  -> bubble video
    cmd += ["-i", str(voice)]      # index = len(SCENES)+1 -> narration

    n = len(SCENES)
    parts = []
    for i in range(n):
        parts.append(f"[{i}:v]scale=1920:1080,setsar=1,fps=30[v{i}]")
    concat_in = "".join(f"[v{i}]" for i in range(n))
    parts.append(f"{concat_in}concat=n={n}:v=1:a=0[bg]")
    parts.append(f"[{n}:v]crop={CROP_EXPR},{BUBBLE}[bub]")
    parts.append(f"[bg][bub]overlay={OVERLAY_XY}:format=auto:shortest=0[vid]")
    fc = ";".join(parts)

    cmd += ["-filter_complex", fc, "-map", "[vid]", "-map", f"{n+1}:a",
            "-t", f"{total}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(out)]
    r = sh(cmd)
    if r.returncode != 0:
        sys.exit("composite failed:\n" + r.stderr[-1500:])
    return out


def main():
    if not D.exists():
        sys.exit("out/_demo not found — run `python3 make_demo.py` first.")
    rec = find_recording()
    print(f"Recording: {rec}  ({dur(rec):.1f}s)")
    voice = clean_voice(rec)
    total = dur(voice)
    print(f"Cleaned voice: {voice.name}  ({total:.1f}s)")
    durs = scene_durations(voice, total)
    out = build(rec, voice, durs)
    print(f"\n  Done -> {out}  ({dur(out):.1f}s)")


if __name__ == "__main__":
    main()
