---
name: validate-splits
description: Validate that the commission splits in a parsed real-estate transaction sum correctly. Co-agent splitPercent values must total 100; referral percents are independent.
---

# Validate Splits

When you have a parsed transaction object (from parse.py) before sending it to create.py, run this check.

## Rules

1. `data.coAgents[].splitPercent` must sum to 100 (within ±0.01).
2. There must be exactly one entry with `isMe: true`.
3. `data.referrals[].splitPercent` is independent — these come out of gross commission first and don't have to sum to anything specific.

## What to do on failure

If a rule fails, stop the workflow and ask the user to clarify the prompt — don't silently fix it. Showing the user the exact failed sum and which entries were parsed is more helpful than guessing at intent.
