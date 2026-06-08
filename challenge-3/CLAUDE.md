# Open House Flyer Agent (June Challenge — "Agents for Agents")

> A real-estate agent gives a listing → Claude writes the marketing copy,
> screens it for Fair-Housing violations, and renders **both** a print-ready
> open-house flyer (PNG) and a vertical listing video (MP4), plus a social caption.

This is the June entry for the QA monthly challenge. The theme is **Agents for
Agents**: Claude-powered skills that quietly do real work on behalf of our real
estate agents. It implements the first listed example — *"create open house
flyers and videos"* — end-to-end, and, because it's built by QA, it won't publish
copy that exposes the agent to a Fair Housing complaint.

## What it does

```
$ ./run.sh examples/listing.json
$ ./run.sh examples/listing.json --photo ~/Desktop/front.jpg
$ ./run.sh 1b2d192e-4cae-4612-88c8-d8b8957de8eb --beds 4 --baths 3 --sqft 2680 --photo front.jpg
```

Output (in `./out`):
- `flyer.png` — the print-ready 8.5×11 flyer, rendered at 2× for crisp text
- `flyer.html` — the same flyer as editable HTML (tweak and re-screenshot)
- `listing.mp4` — an ~18s vertical (1080×1920) listing reel for Instagram/TikTok
- `caption.txt` — a ready-to-paste Instagram/Facebook caption with hashtags

The agent writes the copy in a senior-copywriter voice, runs it through a
**Fair-Housing compliance gate**, then composes a polished HTML flyer (screenshot
with headless Chrome) and a listing video (styled scene cards + ffmpeg motion).

## Why HTML → screenshot (and not an image/video model)

Claude's strength is **layout, typography, and copy** — not raster art. So the
flyer is composed as HTML/CSS and rendered to PNG with headless Chrome; the video
reuses the same approach — four styled scene cards rendered the same way, then
ffmpeg adds a slow Ken Burns push and crossfades them into a reel. The listing
photo is embedded as a base64 data-URI, so every page is fully self-contained (no
network, no broken images, no image/video model). The result looks **designed,
not generated**, and every frame is deterministic and offline.

## Architecture

| File | Role |
|------|------|
| `fetch.py` | Load the listing facts. Three auto-detected modes: a `listing.json` fact sheet, an **arrakis listing id** (`GET /transactions/{id}` for address/price/agent), or pure `--flags`. Flags override whatever the base source returned, so you can enrich a real arrakis listing with the MLS detail it doesn't store. |
| `copywriter.py` | Claude API `tool_use` (forced via `tool_choice`) → strict JSON copy blocks: headline, subheadline, stat line, description, feature bullets, open-house line, CTA, social caption. The model writes the voice but is forbidden from inventing facts. |
| `compliance.py` | **Fair-Housing gate.** An independent Claude call whose only job is to flag protected-class / steering language and return a sanitized rewrite. The renderer always uses the sanitized copy. |
| `flyer.py` | Fill the HTML/CSS flyer template, embed the photo as a data-URI, and screenshot it with headless Chrome (`--screenshot`). System fonts only, so it renders offline. Supports `print` (8.5×11) and `social` (1080×1350) sizes. Exposes `shoot()`, the shared Chrome screenshot helper. |
| `video.py` | Render four 1080×1920 scene cards (hero · stats · highlights · CTA) via `shoot()`, then assemble them with ffmpeg — a Ken Burns zoom per scene, crossfades, a silent audio track — into `listing.mp4`. |
| `main.py` | Orchestrator: fetch → copy → compliance → flyer + video → print summary. |
| `.claude/skills/validate-fair-housing.md` | The Fair-Housing rules the gate enforces. |
| `examples/listing.json` | A sample Rye, NY listing to run against (with `examples/hero.jpg`). |

## Pipeline

1. `fetch.load_listing(argv)` → a normalized `listing` dict (address, price,
   beds/baths/sqft, features, openHouse, photo, agent).
2. `copywriter.write_copy(listing)` → Claude returns the copy blocks via the
   `write_flyer_copy` tool. Facts come only from the listing; voice is the model's.
3. `compliance.review(copy)` → Claude returns `{compliant, violations, sanitized}`
   via the `report_compliance` tool. We always render the `sanitized` copy and
   print any violations so a human can confirm.
4. `flyer.render(listing, sanitized, fmt)` → writes `flyer.html`, screenshots it
   to `flyer.png`, writes `caption.txt`.
5. `video.render_video(listing, sanitized)` → renders four scene cards, then
   ffmpeg assembles `listing.mp4` (skip with `FLYER_ONLY=1`).

## Concepts demonstrated

| Concept | Where it shows up |
|---------|--------------------|
| **Tools** | `copywriter.py` and `compliance.py` — two forced `tool_use` schemas turn free-form generation into typed JSON the renderer can trust. |
| **Skills** | `.claude/skills/validate-fair-housing.md` gates publishing behind a domain compliance rule — the thing that makes a *QA-built* A4A skill trustworthy. |
| **Agents** | This project — `CLAUDE.md` defines a Claude Code agent you can `cd` into and run. |
| **Memory** | The arrakis env, token-fetch path, and default agent identity come from existing user memory, not re-discovery. |
| **Rendering** | Claude composes HTML/CSS; headless Chrome turns it into a shareable artifact — no image model needed. |

## Memory it relies on

- `feedback_token_via_pwadmin.md` — fresh admin token via `pwadmin` / `P@ssw0rd`
  on keymaker, never hardcoded (only used in arrakis-id mode).
- `project_transaction_lifecycle_agent.md` — default QA agent / `team2` context
  for resolving a real listing id.

## Setup

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # or rely on the `claude` CLI fallback
pip3 install -r requirements.txt
./run.sh examples/listing.json
```

- Needs **Google Chrome** (or Chromium/Brave/Edge) to render. Auto-detected;
  override with `CHROME_BIN=/path/to/chrome`.
- Needs **ffmpeg** for the video (`brew install ffmpeg`). If it's missing the
  flyer still renders and the video step is skipped with a notice.
- If the SDK key is missing or returns 401, every Claude step falls back to the
  `claude` CLI (OAuth), so the demo still runs end-to-end.
- `FLYER_FORMAT=social ./run.sh ...` renders the 1080×1350 Instagram flyer size.
- `FLYER_ONLY=1 ./run.sh ...` skips the video.
- arrakis-id mode defaults to `team2`; override with `DRAFT_TX_ENV=team1`.

## Demo limitations (called out so the demo is honest)

- **"From a new MLS id" is not wired up — this is the one real gap.** Beds/baths/
  sqft/photos/description are *not* in arrakis, so there is no MLS-id → listing
  lookup yet. Today the facts come from the `listing.json` sheet or `--flags`,
  and the arrakis-id mode only enriches address, list price, and the listing
  agent (read-only). Closing this needs an MLS/IDX feed (RESO Web API, MLS Grid,
  Bridge, Spark) or an internal listings service keyed by MLS number that returns
  photos — a credentialed data source we don't have in this repo.
- **The video is built from styled stills + ffmpeg motion, not an AI-video
  model.** Deterministic, offline, on-brand — but it's a Ken Burns reel over the
  listing photo and scene cards, not generated cinematography.
- **The photo** is the agent's own listing photo, passed via `--photo` (or
  `"photo"` in the JSON). With no photo, the hero falls back to a tasteful
  gradient placeholder so the flyer is still complete.
- **Fair-Housing review is assistive, not legal advice.** It catches the common,
  well-documented patterns (protected classes + coded steering language) and
  surfaces them; the agent's broker compliance team is still the final authority.
- **Render fidelity** depends on the local Chrome. System fonts are used so the
  output is deterministic and offline; swapping in a brand font would mean
  bundling the font file and embedding it as a data-URI too.

## Demo

Run it and open `out/flyer.png`. To see the compliance gate earn its keep, feed
it intentionally non-compliant copy:

```
$ echo '{"headline":"Perfect home for a growing family","subheadline":"safe, exclusive neighborhood near great schools","statLine":"","description":"","features":[],"openHouseLine":"","callToAction":"","socialCaption":""}' | python3 compliance.py
```

It flags the familial-status and steering language and returns a sanitized
rewrite.

## When to use this agent (Claude Code)

When an agent hands you a listing (a JSON fact sheet, an arrakis listing id, or
just the address + price + specs) and wants marketing material, use this project.
Run `./run.sh <listing>` and report:

1. The headline and stat line Claude wrote.
2. Whether the copy passed the Fair-Housing review (and what was rewritten).
3. The path to `out/flyer.png` and the social caption.

Never publish copy that failed the compliance gate without showing the user the
violations first.
