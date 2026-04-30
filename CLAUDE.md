# Draft Transaction Agent

Take an English description of a real-estate deal, parse it into structured fields with the Claude API, and build a **draft** transaction in bolt via the arrakis REST API.

This project is a demo for the QA monthly challenge: showing how Claude's API + tool use can drive an internal workflow.

## What it does

```
$ ./run.sh "Create a transaction with $20,000 gross commission for me and my partner Tamir. I am 60%, he's 40%. We also have a referral for 30% named Jason, and the address is 123 Main Street, New York, New York 10025."
```

Output:
- The parsed JSON of the deal (commission, address, splits, referral)
- A bolt URL pointing at the new draft transaction

The result sits in bolt's drafts list — un-submitted — ready for the user to finalize.

## Architecture

| File | Role |
|------|------|
| `parse.py`  | Claude API call. Uses tool_use with a strict JSON schema to coerce free text into typed fields. Forced via `tool_choice` so the model can't reply in plain text. |
| `create.py` | Pure REST client for arrakis. Walks the builder endpoints (location → owner → price/commission). The submit step is **deliberately skipped** — that is what keeps it a draft. |
| `main.py`   | Orchestrator: parse → validate splits → create → print summary. |
| `.claude/skills/validate-splits.md` | Skill: enforce that splits sum to 100 with exactly one `isMe` entry. |
| `examples/prompt.txt` | The challenge example prompt. |

## Concepts demonstrated

| Concept | Where it shows up |
|---------|--------------------|
| **Tools**  | `parse.py` — Claude API `tool_use` schema for structured extraction. |
| **Agents** | This very project — `CLAUDE.md` defines a Claude Code agent you can `cd` into and run `claude`. |
| **Skills** | `.claude/skills/validate-splits.md` — gates `create.py` behind a domain rule. |
| **Memory** | The default agent ID, env, and token-fetch path all come from existing user memory rather than being re-discovered each run. |

## Memory it relies on

- `project_transaction_lifecycle_agent.md` — default QA agent `767fbf84-afbf-4346-aad0-5e262259c657`, licensed in NEW_YORK and NEW_JERSEY on team2.
- `feedback_token_via_pwadmin.md` — fresh admin token via `pwadmin` / `P@ssw0rd` on keymaker, never hardcoded.

## Setup

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pip3 install -r requirements.txt
./run.sh                                  # interactive
./run.sh "$(cat examples/prompt.txt)"    # one-shot
```

Defaults to `team2` because the default QA agent is licensed there. Override with `DRAFT_TX_ENV=team1 ./run.sh`.

## Demo limitations (called out so the demo is honest)

- **Tamir, Jason** are name-only in the prompt. The parser extracts them and `validate-splits` checks the sums, but they aren't added to the draft as participants — that would need real Rezen agent IDs. Only the user (`me`) is added as the `REAL` owner agent.
- `buyer-seller-info`, `commission-payer`, and `personal-deal-info` are skipped. They're only required at *submit* time, not for a draft.
- Bolt URL uses `/transactions/drafts/{id}` — verify the exact path on your bolt build; if drafts open from a different route, edit `BOLT_BASE` in `create.py`.

## When to use this agent (Claude Code)

When the user gives an English description of a real-estate deal and wants a draft created, use this project. Run `./run.sh "<prompt>"` and report the bolt URL back. Don't submit the draft — keeping it in draft mode is the whole point.
