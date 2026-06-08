"""Render a vertical listing reel (MP4) from the listing facts + flyer copy.

Same philosophy as the flyer: Claude/CSS does the design, the machine does the
motion. We render 4 styled scene cards (1080x1920, the IG/TikTok Reels size) with
the same headless-Chrome path the flyer uses, then ffmpeg turns the stills into a
reel — a slow Ken Burns push on each scene, crossfaded together, with a silent
audio track so the file uploads cleanly everywhere.

No AI-video model: every frame is deterministic, offline, and on-brand.

Output: ./out/listing.mp4  (plus ./out/scene_*.png intermediates)
"""

from __future__ import annotations

import html
import shutil
import subprocess
import sys
from pathlib import Path

from flyer import OUT, _photo_data_uri, shoot

W, H = 1080, 1920          # vertical reel
SCENE_SECS = 5.0
XFADE = 0.6
FPS = 30

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


def _build_ffmpeg_cmd(scene_pngs: list, out_mp4: Path) -> list:
    n = len(scene_pngs)
    frames = int(SCENE_SECS * FPS)
    total = n * SCENE_SECS - (n - 1) * XFADE

    cmd = ["ffmpeg", "-y"]
    for p in scene_pngs:
        cmd += ["-loop", "1", "-t", str(SCENE_SECS), "-i", str(p)]
    cmd += ["-f", "lavfi", "-t", f"{total:.2f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    parts = []
    for i in range(n):
        # Source PNGs are 2160x3840 (2x); zoompan crops/zooms into them and
        # outputs 1080x1920, so the push stays crisp. Alternate in/out for life.
        if i % 2 == 0:
            z = "min(zoom+0.0006,1.12)"
        else:
            z = "if(eq(on,0),1.12,max(zoom-0.0006,1.0))"
        parts.append(
            f"[{i}:v]scale=2160:3840,setsar=1,"
            f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={W}x{H}:fps={FPS}[v{i}]"
        )

    label = "v0"
    length = SCENE_SECS
    for i in range(1, n):
        off = length - XFADE
        new = f"x{i}"
        parts.append(
            f"[{label}][v{i}]xfade=transition=fade:duration={XFADE}:"
            f"offset={off:.2f}[{new}]"
        )
        length += SCENE_SECS - XFADE
        label = new

    parts.append(
        f"[{label}]fade=t=in:st=0:d=0.5,"
        f"fade=t=out:st={length - 0.6:.2f}:d=0.6[vout]"
    )

    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", "[vout]", "-map", f"{n}:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-shortest", "-movflags", "+faststart",
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
    out_mp4 = OUT / "listing.mp4"
    cmd = _build_ffmpeg_cmd(scene_pngs, out_mp4)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not out_mp4.exists() or out_mp4.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr[-800:]}")
    secs = len(SCENES) * SCENE_SECS - (len(SCENES) - 1) * XFADE
    return {"mp4": str(out_mp4), "scenes": len(scene_pngs),
            "size": f"{W}x{H}", "duration": f"{secs:.0f}s"}


if __name__ == "__main__":
    import json
    payload = json.load(sys.stdin)
    print(json.dumps(render_video(payload["listing"], payload["copy"]), indent=2))
