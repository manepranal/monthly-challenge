"""Presenter cut of the WATCH-MODE demo — face bubble + your voice.

Same recipe as make_presenter.py (the one-shot cut), pointed at the 8
watch-mode scenes: your webcam as a circular bubble lower-right, your cleaned
voice as narration, each scene timed to the line you speak for it.

    python3 make_watch_presenter.py script            # print the 8 lines to record
    python3 make_watch_presenter.py [recording.mov]   # build the presenter cut

Prereqs: run `make_watch_demo.py` first (renders the 8 stills into
out/_watch_demo/). Needs ffmpeg; uses whisper-cli (if installed) to sync each
scene to the exact moment you start its line — falls back to pause detection,
then to a DURS env override (comma list of 8 durations, scaled to total).

Tuning env vars (same as make_presenter.py):
    CROP_EXPR      ffmpeg crop for the face square — per recording! Grab a frame
                   and eyeball it (July-demo-face-v2 was 500:500:425:220).
    WHISPER_MODEL  path to a ggml whisper model (default: the tiny.en used by
                   the playwright-learn-agent).
    DURS / NOISE_DB / MIN_SIL   see make_presenter.py
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import make_presenter as mp
import make_watch_demo as mwd

ROOT = Path(__file__).parent
OUT = ROOT / "out" / "_watch_demo"

# retarget the one-shot presenter machinery at the watch scenes
mp.D = OUT
mp.SCENES = [name for name, _fn, _line in mwd.SCENES]
mp.OUTNAME = "watch-mode-presenter.mp4"

LINES = [line for _name, _fn, line in mwd.SCENES]

WHISPER_MODEL = Path(os.environ.get(
    "WHISPER_MODEL",
    Path.home() / "playwright-learn-agent" / "models" / "ggml-tiny.en.bin"))

CANDIDATES = [
    ROOT / "recording-watch.mov",
    Path.home() / "Documents" / "July-watch-face.mov",
    Path.home() / "Desktop" / "July-watch-face.mov",
    Path.home() / "Downloads" / "July-watch-face.mov",
]


def find_recording() -> Path:
    if len(sys.argv) > 1:
        p = Path(sys.argv[1]).expanduser()
        if not p.exists():
            sys.exit(f"Recording not found: {p}")
        return p
    for c in CANDIDATES:
        if c.exists():
            return c
    sys.exit("No recording found. Pass a path or save to ~/Documents/July-watch-face.mov\n"
             "(print the lines to read with: python3 make_watch_presenter.py script)")


def _norm(w: str) -> str:
    return "".join(ch for ch in w.lower() if ch.isalnum())


def whisper_words(rec: Path):
    """Transcribe the recording's audio -> [(start_sec, word), ...] or None."""
    import shutil
    cli = shutil.which("whisper-cli")
    if not cli or not WHISPER_MODEL.exists():
        print("  (whisper-cli or model missing — skipping whisper sync)")
        return None
    wav = OUT / "whisper_in.wav"
    r = mp.sh(["ffmpeg", "-y", "-i", str(rec), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    if r.returncode != 0:
        return None
    of = OUT / "whisper"
    r = mp.sh([cli, "-m", str(WHISPER_MODEL), "-f", str(wav), "-oj", "-of", str(of), "-ml", "1"])
    jf = of.with_suffix(".json")
    if r.returncode != 0 or not jf.exists():
        print("  (whisper failed — skipping whisper sync)")
        return None
    segs = json.loads(jf.read_text()).get("transcription", [])
    words = []
    for s in segs:
        t0 = s["offsets"]["from"] / 1000.0
        for w in s["text"].split():
            if _norm(w):
                words.append((t0, _norm(w)))
    return words or None


def whisper_durs(rec: Path, total: float):
    """Scene durations from whisper word timings: cut where each line starts.

    Matches on a concatenated character stream (not word sequences) so
    whisper's tokenization ("Here 's", "organ izes") can't break alignment."""
    words = whisper_words(rec)
    if not words:
        return None
    stream, char_word = "", []
    for wi, (_t, w) in enumerate(words):
        stream += w
        char_word.extend([wi] * len(w))
    cuts, pos = [0.0], 0
    for i in range(1, len(LINES)):
        key_full = "".join(_norm(w) for w in LINES[i].split())
        hit = -1
        for length in (12, 8, 5):   # relax if whisper misheard a word
            hit = stream.find(key_full[:length], pos)
            if hit != -1:
                break
        if hit == -1:
            print(f"  (!) whisper couldn't locate the start of line {i + 1} "
                  f"({' '.join(LINES[i].split()[:4])}…) — falling back.")
            print(f"      transcript dump: {OUT / 'whisper.json'}")
            return None
        t = words[char_word[hit]][0]
        cuts.append(round(max(t - 0.12, cuts[-1] + 1.0), 3))  # lead-in, keep order
        pos = hit + 30   # skip well into this line before searching for the next
    cuts.append(total)
    durs = [round(cuts[k + 1] - cuts[k], 3) for k in range(len(LINES))]
    print(f"  whisper-synced scene durations: {durs}")
    return durs


def print_script():
    print("Record yourself reading these 8 lines, ~1s pause between lines.")
    print("Save to ~/Documents/July-watch-face.mov\n")
    for i, (name, line) in enumerate(zip(mp.SCENES, LINES), 1):
        print(f"{i}. [{name}]\n   {line}\n")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "script":
        print_script()
        return
    if not OUT.exists():
        sys.exit("out/_watch_demo not found — run `python3 make_watch_demo.py` first.")
    rec = find_recording()
    print(f"Recording: {rec}  ({mp.dur(rec):.1f}s)")
    voice = mp.clean_voice(rec)
    total = mp.dur(voice)
    print(f"Cleaned voice: {voice.name}  ({total:.1f}s)")
    durs = None
    if not os.environ.get("DURS"):
        durs = whisper_durs(rec, total)
    if durs is None:
        durs = mp.scene_durations(voice, total)   # DURS override or pause detection
    out = mp.build(rec, voice, durs)
    print(f"\n  Done -> {out}  ({mp.dur(out):.1f}s)")


if __name__ == "__main__":
    main()
