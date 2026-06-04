# Narration script — `may-challenge-demo-2min.mp4`

First-person, for you to read **live over the slide** or **record and send back to mux in**.
The video is **2:14** and auto-advances on its own — these lines are sized so a natural
speaking pace (~150 wpm) lands on each section. If you run a little long or short, that's
fine; the video keeps playing regardless.

| Time | On screen | Say this |
|------|-----------|----------|
| **0:00–0:10** | Title — *Doc → reZen Agent* | "Hi team. For the May challenge, I built an agent that takes a real-estate document — a contract or a listing — and files the whole deal in reZen, automatically." |
| **0:10–0:26** | *The manual way* | "Here's the problem. Today, when an agent sends us a signed contract or listing, someone has to read it, create the transaction in reZen by hand, re-type every field, then upload the document to the checklist. It's slow, and easy to get wrong." |
| **0:26–0:46** | *How the agent does it* | "My agent collapses all of that into one step. It sends the PDF straight to Claude's vision API, which reads the document and pulls out the fields as structured data. Then it calls the reZen API to build and submit the transaction — and finally attaches the original PDF to the right checklist item." |
| **0:46–1:14** | Contract run (terminal) | "Let's watch it on a real purchase contract. It reads the PDF — and there are the fields it pulled out: the address, the eight-hundred-seventy-five-thousand-dollar sale price, the contract and closing dates, the buyer, the seller, and the commission. Then it submits the transaction on team two and hands back a live Bolt URL. And there at the bottom — the contract PDF is uploaded straight onto a checklist item. Seconds, no typing." |
| **1:14–1:40** | Listing run (terminal) | "It works the same way for a listing agreement — and notice, I never told it which type of document this is. The agent figures that out by reading the document itself and routes to the listing flow automatically. It pulls the list price, the listing and expiration dates, the seller, and the M-L-S number, submits the listing, and attaches the agreement to the checklist." |
| **1:40–1:56** | *Live on team2* (URLs) | "And these are real. Both transactions are live on team two right now. Open either one, click the Checklist tab, and the source document is right there — attached automatically. Two documents in, two finished deals out, with zero manual data entry." |
| **1:56–2:14** | *Tools · Agents · Skills · Memory* | "Under the hood, this one demo touches everything the challenge is about: Claude's vision and tool-use API for the extraction, an agent that drives the whole reZen flow, a skill that validates the fields, and memory for the environment and credentials. That's my May challenge — thanks!" |

## To bake the voice in (optional)
Record yourself reading the whole script in one ~2-minute take (your phone's voice memo is
fine), then hand me the audio file — I'll line it up to the timecodes and mux it into the MP4.
Or just talk over the slide live; the video runs on its own.
