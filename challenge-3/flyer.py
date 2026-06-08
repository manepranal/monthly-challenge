"""Render the flyer copy + listing facts into a PNG.

Approach: Claude's strength is layout + copy, not raster art — so we compose a
polished HTML/CSS flyer and screenshot it with headless Chrome. The listing
photo is embedded as a base64 data-URI so the `file://` page is fully
self-contained (no network, no broken images). No image-gen API needed.

Output (in ./out): flyer.html (editable), flyer.png (the artifact),
caption.txt (the social caption).
"""

from __future__ import annotations

import base64
import html
import os
import shutil
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"

# 8.5x11 portrait at 96dpi; rendered at 2x device scale for crisp text.
SIZES = {
    "print": (816, 1056),
    "social": (1080, 1350),  # Instagram portrait
}

CHROME_CANDIDATES = [
    os.environ.get("CHROME_BIN"),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    shutil.which("google-chrome"),
    shutil.which("chromium"),
    shutil.which("chromium-browser"),
]

MEDIA_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif",
}


def _find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if c and Path(c).exists():
            return c
    raise SystemExit(
        "No Chrome/Chromium found to render the flyer. Install Google Chrome, "
        "or set CHROME_BIN=/path/to/chrome."
    )


def _photo_data_uri(photo: str | None) -> str | None:
    if not photo:
        return None
    p = Path(photo).expanduser()
    if not p.exists():
        print(f"  (photo {photo!r} not found — using a placeholder)", file=sys.stderr)
        return None
    media = MEDIA_BY_EXT.get(p.suffix.lower())
    if not media:
        print(f"  (unsupported photo type {p.suffix!r} — using a placeholder)", file=sys.stderr)
        return None
    data = base64.standard_b64encode(p.read_bytes()).decode("ascii")
    return f"data:{media};base64,{data}"


def _money(n) -> str:
    try:
        return f"${float(n):,.0f}"
    except (TypeError, ValueError):
        return ""


def _stat_pills(listing: dict) -> str:
    pills = []
    if listing.get("beds"):
        pills.append((str(listing["beds"]), "Beds"))
    if listing.get("baths"):
        pills.append((str(listing["baths"]), "Baths"))
    if listing.get("sqft"):
        pills.append((f"{int(listing['sqft']):,}", "Sq Ft"))
    if listing.get("lotSize"):
        pills.append((str(listing["lotSize"]), "Lot"))
    if listing.get("yearBuilt"):
        pills.append((str(listing["yearBuilt"]), "Built"))
    cells = "".join(
        f'<div class="stat"><div class="stat-num">{html.escape(v)}</div>'
        f'<div class="stat-lbl">{html.escape(l)}</div></div>'
        for v, l in pills
    )
    return f'<div class="stats">{cells}</div>' if cells else ""


def _features_html(features: list) -> str:
    if not features:
        return ""
    items = "".join(
        f'<li><span class="tick">&#10003;</span>{html.escape(f)}</li>' for f in features
    )
    return f'<ul class="features">{items}</ul>'


def _hero_style(photo_uri: str | None) -> str:
    if photo_uri:
        return (
            f"background-image:linear-gradient(180deg,rgba(0,0,0,.05) 40%,"
            f"rgba(0,0,0,.72) 100%),url('{photo_uri}');"
            "background-size:cover;background-position:center;"
        )
    return (
        "background-image:linear-gradient(135deg,#23233b 0%,#3a3a5c 60%,#c9a24b 160%);"
    )


def build_html(listing: dict, copy: dict, fmt: str = "print") -> str:
    w, h = SIZES.get(fmt, SIZES["print"])
    photo_uri = _photo_data_uri(listing.get("photo"))
    a = listing.get("address", {})
    address_line = ", ".join(
        x for x in [a.get("street"), a.get("city"),
                    f"{a.get('state','')} {a.get('zip','')}".strip()] if x
    )
    agent = listing.get("agent", {})
    agent_contact = "  •  ".join(
        x for x in [agent.get("phone"), agent.get("email")] if x
    )
    ptype = listing.get("propertyType") or ""
    open_line = copy.get("openHouseLine") or ""
    placeholder_glyph = "" if photo_uri else '<div class="glyph">&#127968;</div>'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  /* System fonts only — no network @import, so the page renders fully offline. */
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{w}px; height:{h}px; }}
  body {{ font-family:'Helvetica Neue',Helvetica,Arial,sans-serif; color:#1c1c28; background:#fff; }}
  .flyer {{ width:{w}px; height:{h}px; display:flex; flex-direction:column; overflow:hidden; }}

  .hero {{ position:relative; height:{int(h*0.50)}px; {_hero_style(photo_uri)}
           display:flex; flex-direction:column; justify-content:space-between; padding:30px; }}
  .glyph {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
            font-size:150px; opacity:.25; }}
  .badge {{ align-self:flex-start; background:#c9a24b; color:#1c1c28; font-weight:600;
            letter-spacing:.16em; font-size:13px; text-transform:uppercase;
            padding:8px 16px; border-radius:2px; position:relative; }}
  .price {{ position:relative; color:#fff; font-family:Georgia,'Times New Roman',serif;
            font-size:52px; font-weight:700; text-shadow:0 2px 12px rgba(0,0,0,.5); }}

  .body {{ flex:1; padding:34px 40px 0; display:flex; flex-direction:column; }}
  .addr {{ font-size:13px; letter-spacing:.14em; text-transform:uppercase;
           color:#8a7a3c; font-weight:600; }}
  .headline {{ font-family:Georgia,'Times New Roman',serif; font-size:34px; line-height:1.12;
               margin:8px 0 4px; color:#1c1c28; }}
  .sub {{ font-size:16px; color:#5a5a6e; margin-bottom:18px; }}

  .stats {{ display:flex; gap:0; border-top:1px solid #e6e2d6; border-bottom:1px solid #e6e2d6;
            margin-bottom:20px; }}
  .stat {{ flex:1; text-align:center; padding:14px 4px;
           border-right:1px solid #e6e2d6; }}
  .stat:last-child {{ border-right:0; }}
  .stat-num {{ font-family:Georgia,'Times New Roman',serif; font-size:24px; color:#1c1c28; }}
  .stat-lbl {{ font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:#9a9aae; }}

  .desc {{ font-size:14.5px; line-height:1.6; color:#3a3a48; margin-bottom:16px; }}
  .features {{ list-style:none; columns:2; column-gap:26px; margin-bottom:4px; }}
  .features li {{ font-size:13.5px; color:#3a3a48; padding:5px 0; break-inside:avoid;
                  display:flex; align-items:flex-start; gap:8px; }}
  .tick {{ color:#c9a24b; font-weight:700; }}

  .open {{ margin-top:auto; background:#1c1c28; color:#fff; text-align:center;
           padding:14px; font-size:15px; font-weight:600; letter-spacing:.03em; }}
  .open b {{ color:#e7c873; }}

  .footer {{ background:#23233b; color:#fff; padding:20px 40px;
             display:flex; justify-content:space-between; align-items:center; }}
  .agent-name {{ font-family:Georgia,'Times New Roman',serif; font-size:20px; }}
  .agent-meta {{ font-size:12.5px; color:#b9b9cf; margin-top:3px; }}
  .brand {{ text-align:right; }}
  .brand .bk {{ font-size:15px; font-weight:600; letter-spacing:.04em; }}
  .eho {{ font-size:9.5px; color:#8f8fae; margin-top:5px; max-width:230px; line-height:1.35; }}
</style></head>
<body>
  <div class="flyer">
    <div class="hero">
      {placeholder_glyph}
      <div class="badge">Just Listed</div>
      <div class="price">{_money(listing.get('price'))}</div>
    </div>
    <div class="body">
      <div class="addr">{html.escape(address_line)}{(' &nbsp;|&nbsp; ' + html.escape(ptype)) if ptype else ''}</div>
      <div class="headline">{html.escape(copy.get('headline',''))}</div>
      <div class="sub">{html.escape(copy.get('subheadline',''))}</div>
      {_stat_pills(listing)}
      <div class="desc">{html.escape(copy.get('description',''))}</div>
      {_features_html(copy.get('features', []))}
      {f'<div class="open">{html.escape(open_line)}</div>' if open_line else '<div style="margin-top:auto"></div>'}
    </div>
    <div class="footer">
      <div>
        <div class="agent-name">{html.escape(agent.get('name') or 'Your Real Agent')}</div>
        <div class="agent-meta">{html.escape(agent_contact)}</div>
      </div>
      <div class="brand">
        <div class="bk">{html.escape(agent.get('brokerage') or 'Real Broker')}</div>
        <div class="eho">&#8962; Equal Housing Opportunity. Information deemed reliable but not guaranteed.</div>
      </div>
    </div>
  </div>
</body></html>"""


def shoot(html_path: Path, png_path: Path, w: int, h: int) -> None:
    """Screenshot a local HTML file to PNG with headless Chrome at 2x scale.

    Shared by the flyer and the video scene renderer. The page is expected to be
    fully offline (system fonts + data-URI images), so the shot is immediate.
    """
    chrome = _find_chrome()
    profile = OUT / ".chrome-profile"  # isolated; never touches the user's Chrome
    if png_path.exists():
        png_path.unlink()  # so a stale file can't masquerade as success

    def _flags(headless: str) -> list:
        return [
            chrome,
            headless,
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-sync",
            f"--user-data-dir={profile}",
            "--force-device-scale-factor=2",
            f"--window-size={w},{h}",
            "--default-background-color=FFFFFFFF",
            f"--screenshot={png_path}",
            html_path.as_uri(),
        ]

    stderr = ""
    for headless in ("--headless=new", "--headless"):  # modern, then legacy
        try:
            proc = subprocess.run(_flags(headless), capture_output=True,
                                  text=True, timeout=45)
            stderr = proc.stderr
        except subprocess.TimeoutExpired:
            stderr = f"timed out with {headless}"
        if png_path.exists():
            break
    if not png_path.exists():
        raise RuntimeError(f"Chrome did not produce a screenshot.\n{stderr[:600]}")


def render(listing: dict, copy: dict, fmt: str = "print") -> dict:
    OUT.mkdir(exist_ok=True)
    w, h = SIZES.get(fmt, SIZES["print"])
    html_path = OUT / "flyer.html"
    png_path = OUT / "flyer.png"
    caption_path = OUT / "caption.txt"

    html_path.write_text(build_html(listing, copy, fmt), encoding="utf-8")
    caption_path.write_text(copy.get("socialCaption", ""), encoding="utf-8")
    shoot(html_path, png_path, w, h)

    return {
        "html": str(html_path),
        "png": str(png_path),
        "caption": str(caption_path),
        "format": fmt,
        "size": f"{w}x{h} @2x",
    }


if __name__ == "__main__":
    import json
    payload = json.load(sys.stdin)
    print(json.dumps(render(payload["listing"], payload["copy"],
                            os.environ.get("FLYER_FORMAT", "print")), indent=2))
