"""Render a vertical listing reel (MP4) from the listing facts + flyer copy.

Same philosophy as the flyer: Claude/CSS does the design, the machine does the
motion. We render 4 styled scene cards (1080x1920, the IG/TikTok Reels size) with
the same headless-Chrome path the flyer uses, then ffmpeg turns the stills into a
reel — a slow Ken Burns push on each scene, crossfaded together.

**Synced narration.** The agent writes one spoken line per scene from the
*sanitized* copy (so the words are Fair-Housing–gated, same as the on-screen
text), each worded to match what that scene shows. By default each line is
rendered with a macOS `say` voice (`VOICE`, default Daniel; `VOICE_RATE` wpm),
and the scene's length is set to its own line — so the voice always tracks the
visuals instead of drifting ahead. Offline and deterministic, but a stock TTS
voice, not a clone. Set `VOICE=off` to use your own recording instead
(`VOICEOVER=/path`, or `voiceover.<ext>` in the project dir or `out/`), in which
case the reel paces to your read; with neither, it falls back to a silent track.
(macOS Personal Voice — cloning your own voice — was evaluated but can't be
driven by a script here: the OS denies authorization to anything not signed with
an Apple Developer Team ID. See CLAUDE.md.)

No AI-video model: every frame is deterministic, offline, and on-brand.

Output: ./out/listing.mp4  (plus ./out/scene_*.png + ./out/narration_script.txt)
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from flyer import OUT, _photo_data_uri, shoot

HERE = Path(__file__).resolve().parent

W, H = 1080, 1920          # vertical reel
SCENE_SECS = 5.0           # default per-scene seconds (silent fallback)
XFADE = 0.6
FPS = 30

TAIL = 1.2                 # seconds of reel after the voice ends (fade-out room)
MIN_SCENE, MAX_SCENE = 3.5, 8.0                   # clamp per-scene pacing
# Your own narration recording. Set VOICEOVER=/path, or drop a file named
# voiceover.<ext> in the project dir or ./out. The agent never synthesizes a
# voice — this is your recording.
VOICEOVER_ENV = os.environ.get("VOICEOVER")
VOICE_EXTS = (".m4a", ".mp3", ".wav", ".aiff", ".aif", ".caf", ".m4b")

# Synced narration. By default the reel is narrated by a macOS `say` voice, with
# ONE spoken line per scene whose words match that scene's on-screen content, and
# each scene's length set to its own line — so the voice always tracks the
# visuals. Set VOICE="" (or off/none) to fall back to the record-your-own /
# silent path above. VOICE_RATE is words-per-minute.
VOICE = (os.environ.get("VOICE", "Daniel") or "").strip()
VOICE_RATE = int(os.environ.get("VOICE_RATE", "198"))
LEAD = 0.45                # silence before a scene's line starts (let it settle)
SEG_TAIL = 0.70            # breath after a scene's line before the next scene
MIN_TTS_SCENE = 3.0        # floor so a short line still holds on screen

NAVY_BG = ("background:radial-gradient(120% 80% at 50% 0%,#2c2c4a 0%,#1c1c28 70%);")


def _doc(bg_style: str, inner: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{W}px; height:{H}px; }}
  body {{ font-family:'Helvetica Neue',Helvetica,Arial,sans-serif; color:#fff; {bg_style} }}
  .scene {{ width:{W}px; height:{H}px; padding:120px 90px; display:flex;
            flex-direction:column; overflow:hidden; position:relative; }}
  .eyebrow {{ color:#d9b44a; letter-spacing:.32em; text-transform:uppercase;
              font-size:26px; font-weight:600; }}
  .serif {{ font-family:Georgia,'Times New Roman',serif; }}
  .badge {{ align-self:flex-start; background:#c9a24b; color:#1c1c28; font-weight:700;
            letter-spacing:.18em; font-size:28px; text-transform:uppercase;
            padding:16px 30px; border-radius:3px; }}
  .rule {{ width:90px; height:4px; background:#c9a24b; margin:30px 0; }}
</style></head><body><div class="scene">{inner}</div></body></html>"""


def _money(n) -> str:
    try:
        return f"${float(n):,.0f}"
    except (TypeError, ValueError):
        return ""


def _clean_for_speech(s: str) -> str:
    """Make a copy fragment read cleanly aloud: drop bullets, hashtags, emoji."""
    if not s:
        return ""
    s = s.replace("–", "-").replace("—", "-")  # en/em dash -> hyphen (keep ranges)
    s = re.sub(r"#\w+", "", s)                 # hashtags
    s = re.sub(r"[•·|*_#]+", ", ", s)          # bullet/markup chars -> pause
    s = re.sub(r"[^\w\s.,!?;:'\"()$%&/-]", "", s)  # strip emoji/symbols
    s = re.sub(r"\s+", " ", s).replace(" ,", ",").strip()
    return s


def narration_script(listing: dict, copy: dict) -> str:
    """The script to read aloud — built from the sanitized copy (Fair-Housing safe)."""
    parts = []
    for field, suffix in [("headline", "."), ("description", ""),
                          ("openHouseLine", "."), ("callToAction", "")]:
        frag = _clean_for_speech(copy.get(field, ""))
        if frag:
            parts.append(frag if frag.endswith((".", "!", "?")) else frag + suffix)
    return " ".join(p for p in parts if p).strip()


def _audio_duration(path: Path):
    """Seconds of an audio file via ffprobe, or None."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=20).stdout.strip()
        return float(out) if out else None
    except Exception:
        return None


def _find_voiceover():
    """Locate the user's narration recording: $VOICEOVER, else voiceover.<ext>
    in the project dir or ./out. Returns a Path or None."""
    if VOICEOVER_ENV:
        p = Path(VOICEOVER_ENV).expanduser()
        return p if p.exists() else None
    for base in (HERE, OUT):
        for ext in VOICE_EXTS:
            p = base / f"voiceover{ext}"
            if p.exists():
                return p
    return None


def _trim_silence(src: Path):
    """Clean a raw recording: trim leading/trailing silence AND collapse long
    internal gaps (a mid-read pause) down to a natural ~0.35s beat, so a fixed-
    length take with hesitations doesn't leave dead air in the reel. Short,
    natural pauses are kept. Returns a Path (cleaned, or the original on failure)."""
    dst = OUT / "voiceover_trimmed.wav"
    flt = ("silenceremove=start_periods=1:start_threshold=-35dB:start_silence=0.1:"
           "stop_periods=-1:stop_threshold=-35dB:stop_duration=0.4:stop_silence=0.35")
    try:
        p = subprocess.run(["ffmpeg", "-y", "-i", str(src), "-af", flt, str(dst)],
                           capture_output=True, text=True, timeout=60)
        if p.returncode == 0 and dst.exists() and dst.stat().st_size > 0 and _audio_duration(dst):
            return dst
    except Exception:
        pass
    return src


def _join_sentences(parts: list) -> str:
    """Join fragments into clean sentences — one period between, no doubles."""
    out = []
    for p in parts:
        p = _clean_for_speech(p or "").strip().rstrip(".!?").strip()
        if p:
            out.append(p)
    return (". ".join(out) + ".") if out else ""


def narration_segments(listing: dict, copy: dict) -> list:
    """One spoken line per scene, worded to match that scene's on-screen content
    (hero · headline+stats · highlights · open-house+contact). Built from the
    *sanitized* copy, so the voice is Fair-Housing–gated like the visuals — and
    kept tight + non-repetitive (each fact said once) so the reel stays a reel.
    Lines up 1:1 with SCENES."""
    a = listing.get("address", {})
    city, street = a.get("city") or "", a.get("street") or ""
    price = _money(listing.get("price"))

    # Scene 1 — hero: "Just Listed", the address, the price.
    lead = f"Just listed in {city}" if city else "Just listed"
    locprice = ", ".join(x for x in [street, f"offered at {price}" if price else ""] if x)
    seg1 = _join_sentences([lead, locprice])

    # Scene 2 — headline + the stat pills. (The subheadline is left to the
    # highlights scene, so scenes 2 and 3 don't say the same thing.)
    specs = []
    if listing.get("beds"):
        specs.append(f"{listing['beds']} bedrooms")
    if listing.get("baths"):
        specs.append(f"{listing['baths']} baths")
    if listing.get("sqft"):
        try:
            specs.append(f"{int(listing['sqft']):,} square feet")
        except (TypeError, ValueError):
            pass
    seg2 = _join_sentences([copy.get("headline", ""), ", ".join(specs)])

    # Scene 3 — the highlights checklist (same items the card shows).
    feats = [_clean_for_speech(f) for f in copy.get("features", [])[:5]]
    feats = [f for f in feats if f]
    seg3 = _join_sentences(["Highlights include " + ", ".join(feats)]) if feats else ""

    # Scene 4 — open-house line + a single, non-redundant contact ask (the CTA's
    # phone/date are not repeated here).
    agent = listing.get("agent", {})
    contact = ""
    if agent.get("name"):
        contact = f"Call {agent['name']}"
        if agent.get("phone"):
            contact += f" at {agent['phone']} to schedule a showing"
    seg4 = _join_sentences([copy.get("openHouseLine", ""), contact])

    return [seg1, seg2, seg3, seg4]


def _say_tts(text: str, voice: str, rate: int, out_aiff: Path) -> Path:
    """Render one narration line to audio with macOS `say` (offline, no clone)."""
    txt = OUT / (out_aiff.stem + ".txt")
    txt.write_text(text + "\n", encoding="utf-8")
    subprocess.run(["say", "-v", voice, "-r", str(rate), "-f", str(txt),
                    "-o", str(out_aiff)], capture_output=True, text=True, timeout=90)
    return out_aiff


def _assemble_track(seg_audio: list, lead: float, gaps: list, out_wav: Path) -> Path:
    """Lay the per-scene lines onto one track at the right offsets: a `lead` of
    silence, then each line, then `gaps[i]` of silence before the next — so line i
    plays while scene i is on screen. Built with one ffmpeg concat."""
    seq = [("s", lead)]
    for i, a in enumerate(seg_audio):
        seq.append(("f", a))
        if i < len(gaps):
            seq.append(("s", gaps[i]))
    cmd = ["ffmpeg", "-y"]
    for kind, val in seq:
        if kind == "s":
            cmd += ["-f", "lavfi", "-t", f"{max(val, 0.01):.3f}",
                    "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        else:
            cmd += ["-i", str(val)]
    k = len(seq)
    fc = "".join(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}];"
                 for i in range(k))
    fc += "".join(f"[a{i}]" for i in range(k)) + f"concat=n={k}:v=0:a=1[out]"
    cmd += ["-filter_complex", fc, "-map", "[out]", str(out_wav)]
    subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return out_wav


def _synth_synced_narration(listing: dict, copy: dict, voice: str, rate: int):
    """Per-scene TTS + a positioned audio track. Returns (durs, track, label):
    `durs` are per-scene seconds (each scene as long as its own spoken line),
    `track` is the assembled voiceover. None if `say` is unavailable."""
    if not shutil.which("say"):
        return None
    segs = narration_segments(listing, copy)
    seg_audio, seg_secs = [], []
    for i, line in enumerate(segs, 1):
        aiff = OUT / f"_voice_seg_{i}.aiff"
        if line:
            _say_tts(line, voice, rate, aiff)
        d = (_audio_duration(aiff) or 0.0) if line and aiff.exists() else 0.0
        seg_audio.append(aiff if d else None)
        seg_secs.append(d)

    durs = [max(MIN_TTS_SCENE, LEAD + d + SEG_TAIL) for d in seg_secs]
    # silence after line i so line i+1 starts exactly when scene i+1 appears
    gaps = [(durs[i] - XFADE) - seg_secs[i] for i in range(len(durs) - 1)]
    track = OUT / "voiceover_synced.wav"
    # a silent placeholder stands in for any empty scene line, keeping offsets right
    placeholders = []
    for i, a in enumerate(seg_audio):
        if a is None:
            sil = OUT / f"_voice_seg_{i+1}.aiff"
            subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-t", "0.05",
                            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                            str(sil)], capture_output=True, text=True, timeout=30)
            a = sil
        placeholders.append(a)
    _assemble_track(placeholders, LEAD, gaps, track)
    return durs, track, f"{voice} (synced TTS)"


def _scene_hero(listing: dict, copy: dict) -> str:
    photo = _photo_data_uri(listing.get("photo"))
    a = listing.get("address", {})
    addr = ", ".join(x for x in [a.get("street"), a.get("city"),
                                 f"{a.get('state','')} {a.get('zip','')}".strip()] if x)
    if photo:
        bg = (f"background-image:linear-gradient(180deg,rgba(0,0,0,.15) 30%,"
              f"rgba(0,0,0,.82) 100%),url('{photo}');background-size:cover;"
              "background-position:center;")
    else:
        bg = NAVY_BG
    inner = f"""
      <div class="badge">Just Listed</div>
      <div style="margin-top:auto">
        <div class="serif" style="font-size:120px;font-weight:700;line-height:1;
             text-shadow:0 4px 24px rgba(0,0,0,.6)">{_money(listing.get('price'))}</div>
        <div style="font-size:34px;letter-spacing:.04em;margin-top:18px;color:#f2f2f6">
             {html.escape(addr)}</div>
      </div>"""
    return _doc(bg, inner)


def _scene_headline(listing: dict, copy: dict) -> str:
    pills = []
    for key, lbl in [("beds", "Beds"), ("baths", "Baths"), ("sqft", "Sq Ft"),
                     ("lotSize", "Lot"), ("yearBuilt", "Built")]:
        v = listing.get(key)
        if v:
            v = f"{int(v):,}" if key == "sqft" else str(v)
            pills.append(f'<div style="text-align:center"><div class="serif" '
                         f'style="font-size:64px">{html.escape(v)}</div>'
                         f'<div style="font-size:24px;letter-spacing:.12em;'
                         f'text-transform:uppercase;color:#a8a8c4">{lbl}</div></div>')
    stats = (f'<div style="display:flex;gap:54px;flex-wrap:wrap;margin-top:50px">'
             f'{"".join(pills)}</div>') if pills else ""
    inner = f"""
      <div class="eyebrow">For Sale</div>
      <div class="rule"></div>
      <div class="serif" style="font-size:84px;line-height:1.08;margin-bottom:24px">
           {html.escape(copy.get('headline',''))}</div>
      <div style="font-size:36px;color:#c9c9dd;line-height:1.4">
           {html.escape(copy.get('subheadline',''))}</div>
      {stats}"""
    return _doc(NAVY_BG, inner)


def _scene_features(listing: dict, copy: dict) -> str:
    feats = copy.get("features", [])[:6]
    items = "".join(
        f'<div style="display:flex;gap:24px;align-items:flex-start;margin:22px 0;'
        f'font-size:40px;line-height:1.3">'
        f'<span style="color:#c9a24b;font-weight:700">&#10003;</span>'
        f'<span>{html.escape(f)}</span></div>'
        for f in feats
    )
    inner = f"""
      <div class="eyebrow">Highlights</div>
      <div class="rule"></div>
      <div style="margin-top:10px">{items}</div>"""
    return _doc(NAVY_BG, inner)


def _scene_cta(listing: dict, copy: dict) -> str:
    agent = listing.get("agent", {})
    open_line = copy.get("openHouseLine") or ""
    contact = "  ·  ".join(x for x in [agent.get("phone"), agent.get("email")] if x)
    open_block = (f'<div class="serif" style="font-size:60px;color:#e7c873;'
                  f'line-height:1.2;margin-bottom:18px">{html.escape(open_line)}</div>'
                  ) if open_line else ""
    cta = copy.get("callToAction") or "Schedule your private tour today."
    inner = f"""
      <div style="margin:auto 0">
        {open_block}
        <div style="font-size:44px;color:#f2f2f6;margin-bottom:60px">{html.escape(cta)}</div>
        <div class="rule"></div>
        <div class="serif" style="font-size:56px">{html.escape(agent.get('name') or 'Your Real Agent')}</div>
        <div style="font-size:32px;color:#c9c9dd;margin-top:12px">{html.escape(contact)}</div>
        <div style="font-size:34px;font-weight:600;letter-spacing:.05em;margin-top:28px">
             {html.escape(agent.get('brokerage') or 'Real Broker')}</div>
        <div style="font-size:20px;color:#8f8fae;margin-top:40px">&#8962; Equal Housing Opportunity.
             Information deemed reliable but not guaranteed.</div>
      </div>"""
    return _doc(NAVY_BG, inner)


SCENES = [_scene_hero, _scene_headline, _scene_features, _scene_cta]


def _render_scenes(listing: dict, copy: dict) -> list:
    paths = []
    for i, scene in enumerate(SCENES, 1):
        html_path = OUT / f"scene_{i}.html"
        png_path = OUT / f"scene_{i}.png"
        html_path.write_text(scene(listing, copy), encoding="utf-8")
        shoot(html_path, png_path, W, H)
        paths.append(png_path)
    return paths


def _build_ffmpeg_cmd(scene_pngs: list, out_mp4: Path, durs: list,
                      voiceover: str | None = None) -> list:
    n = len(scene_pngs)
    total = sum(durs) - (n - 1) * XFADE

    cmd = ["ffmpeg", "-y"]
    for p, d in zip(scene_pngs, durs):
        cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(p)]
    if voiceover:
        cmd += ["-i", voiceover]                       # your narration recording
    else:
        cmd += ["-f", "lavfi", "-t", f"{total:.2f}",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    parts = []
    for i, d in enumerate(durs):
        # Source PNGs are 2160x3840 (2x); zoompan crops/zooms into them and
        # outputs 1080x1920, so the push stays crisp. Alternate in/out for life.
        if i % 2 == 0:
            z = "min(zoom+0.0006,1.12)"
        else:
            z = "if(eq(on,0),1.12,max(zoom-0.0006,1.0))"
        parts.append(
            f"[{i}:v]scale=2160:3840,setsar=1,"
            f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={int(d * FPS)}:s={W}x{H}:fps={FPS}[v{i}]"
        )

    label = "v0"
    length = durs[0]
    for i in range(1, n):
        off = length - XFADE
        new = f"x{i}"
        parts.append(
            f"[{label}][v{i}]xfade=transition=fade:duration={XFADE}:"
            f"offset={off:.2f}[{new}]"
        )
        length += durs[i] - XFADE
        label = new

    parts.append(
        f"[{label}]fade=t=in:st=0:d=0.5,"
        f"fade=t=out:st={length - 0.6:.2f}:d=0.6[vout]"
    )

    if voiceover:
        # Pad your audio (with trailing silence) to exactly the reel length, then
        # hard-cap the output with -t. Avoids the apad+-shortest hang where the
        # infinite-padded stream never lets ffmpeg terminate.
        parts.append(f"[{n}:a]apad=whole_dur={total:.2f}[aout]")
        audio_map = "[aout]"
    else:
        audio_map = f"{n}:a"

    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "[vout]", "-map", audio_map,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k",
        "-t", f"{total:.2f}", "-movflags", "+faststart",
        str(out_mp4),
    ]
    return cmd


def render_video(listing: dict, copy: dict) -> dict:
    if not shutil.which("ffmpeg"):
        raise SystemExit(
            "ffmpeg not found — needed to assemble the video. Install it "
            "(brew install ffmpeg) or skip video with FLYER_ONLY=1."
        )
    OUT.mkdir(exist_ok=True)
    scene_pngs = _render_scenes(listing, copy)

    # Always write the full read-aloud script (for the record-your-own path).
    (OUT / "narration_script.txt").write_text(
        narration_script(listing, copy) + "\n", encoding="utf-8")

    n = len(SCENES)
    use_tts = VOICE.lower() not in ("", "off", "none", "silent")
    synced = _synth_synced_narration(listing, copy, VOICE, VOICE_RATE) if use_tts else None

    if synced:
        durs, track, voice_label = synced
        voiceover = str(track)
        print(f"  Voice: {voice_label} — one line per scene, scenes paced to each line",
              file=sys.stderr)
    else:
        # Record-your-own / silent fallback: one uniform pace over all scenes.
        if use_tts:
            print("  (`say` unavailable — falling back to recording/silent)", file=sys.stderr)
        raw_voiceover = _find_voiceover()
        voiceover = _trim_silence(raw_voiceover) if raw_voiceover else None
        voice_label = raw_voiceover.name if raw_voiceover else None
        dur = _audio_duration(voiceover) if voiceover else None
        if voiceover and dur:
            scene_secs = max(MIN_SCENE, min(MAX_SCENE,
                                            (dur + TAIL + (n - 1) * XFADE) / n))
            print(f"  Voiceover: {voice_label} ({dur:.0f}s after silence-trim) — pacing reel to your read",
                  file=sys.stderr)
        else:
            if voiceover:
                print(f"  (couldn't read audio duration of {voice_label}; reel will be silent)",
                      file=sys.stderr)
            else:
                print("  (no voiceover recording found — reel is silent. Record "
                      "out/narration_script.txt and save as out/voiceover.m4a)", file=sys.stderr)
            voiceover, voice_label = None, None
            scene_secs = SCENE_SECS
        durs = [scene_secs] * n
        voiceover = str(voiceover) if voiceover else None

    out_mp4 = OUT / "listing.mp4"
    cmd = _build_ffmpeg_cmd(scene_pngs, out_mp4, durs, voiceover)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not out_mp4.exists() or out_mp4.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr[-800:]}")
    secs = sum(durs) - (n - 1) * XFADE
    return {"mp4": str(out_mp4), "scenes": len(scene_pngs), "size": f"{W}x{H}",
            "duration": f"{secs:.0f}s", "voice": voice_label,
            "script": str(OUT / "narration_script.txt")}


if __name__ == "__main__":
    import json
    payload = json.load(sys.stdin)
    print(json.dumps(render_video(payload["listing"], payload["copy"]), indent=2))
