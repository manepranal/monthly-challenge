# Doc → reZen Agent (May Challenge)

> Real agent provides a contract (PDF or image) → create a transaction in reZen with the contract info and upload the contract to the checklist.
> Real agent provides a listing agreement (PDF or image) → create a listing in reZen with the listing info and upload the listing agreement to the checklist.

This is the May entry for the QA monthly challenge.

## What it does

```
$ ./run.sh examples/sample-contract.pdf
```

Output:
- Parsed fields from the document (sale price, parties, dates, address)
- A bolt URL pointing at the new **submitted** transaction (or listing)
- Confirmation that the source PDF/image was uploaded to the transaction's
  dropbox (the file storage backing the checklist tab in bolt)

The agent auto-detects whether the document is a **purchase contract** or a
**listing agreement** by reading the document itself, and routes to the
appropriate reZen flow.

## Architecture

| File | Role |
|------|------|
| `extract.py` | Claude API call. Sends the PDF (`document` block) or image (`image` block) plus two tool schemas — `extract_contract` and `extract_listing` — and lets the model pick which to call. `tool_choice: any` forces a structured answer. |
| `create.py`  | Pure REST client for arrakis. Walks the full builder lifecycle: location → owner → price-date → buyer/seller → commission-payer (multipart) → personal-deal → commission-splits → submit. Returns the real `transactionId`. |
| `upload.py`  | Calls `arrakis POST /api/v1/transactions/{txId}/dropbox` to ensure a dropbox exists, then `dropbox POST /api/v1/dropboxes/{id}/files` to attach the source document. |
| `main.py`    | Orchestrator: extract → route on docType → create+submit → upload → print summary. |
| `.claude/skills/validate-doc-fields.md` | Skill: enforce required fields per docType before hitting reZen. |
| `examples/`  | Where to drop sample contracts/listings to test against. |

## End-to-end pipeline (verified on team2)

For a buyer-rep contract:

1. `POST /transaction-builder` → builderId
2. `PUT  /transaction-builder/{id}/location-info`
3. `PUT  /transaction-builder/{id}/owner-info`     (owner agent role=`REAL`)
4. `PUT  /transaction-builder/{id}/price-date-info` (dealType=`SALE`, rep=`BUYER`)
5. `PUT  /transaction-builder/{id}/buyer-seller-info`
6. `PUT  /transaction-builder/{id}/commission-payer` (multipart, role=`SELLER`, `companyName` required)
7. `PUT  /transaction-builder/{id}/personal-deal-info` (`personalDeal=false`, `representedByAgent=false`)
8. `GET  /transaction-builder/{id}` → read `allParticipants`, find owner participantId
9. `PUT  /transaction-builder/{id}/commission-info` (100% to owner participantId)
10. `POST /transaction-builder/{id}/submit` → returns the new transactionId
11. `POST /transactions/{txId}/dropbox` → returns dropboxId
12. `POST {dropbox}/api/v1/dropboxes/{id}/files` (multipart, `uploadedBy` must be a UUID)

For a listing agreement: same flow except step 1 uses `?type=LISTING`, step 4
uses rep=`SELLER` plus listing dates, step 5 only sends `sellers`.

## Concepts demonstrated

| Concept | Where it shows up |
|---------|--------------------|
| **Tools (vision)** | `extract.py` — Claude API `tool_use` over a PDF / image input, with two tools and `tool_choice: any` for content-driven routing. |
| **Agents** | This very project — `CLAUDE.md` defines a Claude Code agent you can `cd` into and run `claude`. |
| **Skills** | `.claude/skills/validate-doc-fields.md` gates `create.py` behind required-field checks. |
| **Memory** | Default agent ID, env, and token-fetch path all come from existing user memory rather than being re-discovered each run. |

## Memory it relies on

- `project_transaction_lifecycle_agent.md` — default QA agent `767fbf84-afbf-4346-aad0-5e262259c657`, licensed in `NEW_YORK` and `NEW_JERSEY` on team2.
- `feedback_token_via_pwadmin.md` — fresh admin token via `pwadmin` / `P@ssw0rd` on keymaker, never hardcoded.

## Setup

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pip3 install -r requirements.txt
./run.sh path/to/contract.pdf
```

Defaults to `team2` because the default QA agent is licensed there. Override
with `DRAFT_TX_ENV=team1 ./run.sh ...`.

To skip submit (leave at draft), set `SUBMIT=0`. The dropbox upload only works
on submitted transactions, so the upload step will be skipped too.

## Demo limitations (called out so the demo is honest)

- **Contract buyer/seller** are extracted and added to the transaction via
  `buyer-seller-info`. They are **not** linked to existing yenta agents —
  that would need email-based agent lookups.
- **Commission payer** is set to the seller as a generic external participant
  (the seller pays the buyer's broker on most US deals). `companyName` is
  required by the API; we set it to the seller's full name.
- **Commission split** is hard-coded to 100% to the owning agent. Multi-agent
  splits would need an additional `/co-agent` PUT and per-participant splits.
- **`uploadedBy`** must be a yenta UUID. We use the default agent's UUID; in
  production you'd use the authenticated user's id.

## When to use this agent (Claude Code)

When the user hands you a contract or listing-agreement file (PDF or image),
use this project. Run `./run.sh <path>` and report:

1. Which docType was detected.
2. The parsed fields (so the user can spot OCR errors).
3. The bolt URL of the submitted transaction.
4. Whether the document was uploaded to the dropbox.
