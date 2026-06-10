"""Open House Flyer Agent — orchestrator.

listing facts -> Claude copy -> Fair-Housing gate -> flyer.png + caption + listing.mp4

Usage:
  ./run.sh examples/listing.json
  ./run.sh <arrakis-listing-uuid> --beds 4 --baths 3 --sqft 2450 --photo hero.jpg
  ./run.sh --street "12 Oak Ln" --city Rye --state NY --zip 10580 --price 1250000 \\
           --beds 4 --baths 3 --photo hero.jpg --open-date "Sat, Jun 14" --open-time "1-4 PM"

  FLYER_ONLY=1 ./run.sh ...   # skip the video
"""

import os
import sys

from fetch import load_listing
from copywriter import write_copy
from compliance import review
from flyer import render
from video import render_video


def _money(n) -> str:
    try:
        return f"${float(n):,.0f}"
    except (TypeError, ValueError):
        return str(n)


def main() -> None:
    listing = load_listing(sys.argv[1:])
    a = listing["address"]

    print("\nListing")
    print(f"  Address:   {a['street']}, {a['city']}, {a['state']} {a['zip']}")
    print(f"  Price:     {_money(listing.get('price'))}")
    specs = [f"{listing[k]} {lbl}" for k, lbl in
             [("beds", "bd"), ("baths", "ba"), ("sqft", "sqft")] if listing.get(k)]
    if specs:
        print(f"  Specs:     {'  '.join(specs)}")
    if listing.get("_source"):
        print(f"  Source:    {listing['_source']}")

    print(f"\nWriting flyer copy with claude-sonnet-4-6...")
    copy = write_copy(listing)
    print(f"  Headline:  {copy['headline']}")
    print(f"  Stat line: {copy['statLine']}")

    print(f"\nFair-Housing review...")
    result = review(copy)
    if result["compliant"]:
        print("  ✓ compliant — no protected-class or steering language")
    else:
        print(f"  ⚠ {len(result['violations'])} issue(s) found and rewritten:")
        for v in result["violations"]:
            print(f"     - [{v.get('protectedClass') or v.get('issue')}] {v['field']}: {v['text']!r}")
    copy = result["sanitized"]

    fmt = os.environ.get("FLYER_FORMAT", "print")
    print(f"\nRendering {fmt} flyer with headless Chrome...")
    out = render(listing, copy, fmt)

    vid = None
    if os.environ.get("FLYER_ONLY") != "1":
        print(f"\nRendering listing video (4 scenes + Ken Burns) with ffmpeg...")
        try:
            vid = render_video(listing, copy)
        except SystemExit as e:
            print(f"  (skipping video: {e})", file=sys.stderr)

    print("\nDone")
    print(f"  Flyer:     {out['png']}  ({out['size']})")
    print(f"  HTML:      {out['html']}")
    if vid:
        voice = f", voice: {vid['voice']}" if vid.get("voice") else ", silent"
        print(f"  Video:     {vid['mp4']}  ({vid['size']}, {vid['duration']}{voice})")
        if not vid.get("voice"):
            print(f"  Script:    {vid['script']}  ← record this & save as out/voiceover.m4a for your voice")
    print(f"  Caption:   {out['caption']}")
    print(f"\nSocial caption:\n{copy['socialCaption']}\n")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
