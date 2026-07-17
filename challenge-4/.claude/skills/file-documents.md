# Skill: File deal documents

The rule that governs how `classify.py` routes an attachment. It exists so filing
is **deterministic and auditable** — every document lands in exactly one known
folder, chosen from the document's content, not its filename.

## Destination folders (the only allowed targets)

| Folder | What belongs here |
|--------|-------------------|
| **Contracts & Agreements** | Purchase & sale agreements, listing agreements, amendments, addenda, riders, fully-executed contracts |
| **Inspections** | Home / pest / radon / sewer / structural inspection reports and re-inspections |
| **Financing & Appraisal** | Appraisal reports, mortgage commitments, pre-approvals, loan estimates, financing paperwork |
| **Accounting & Commissions** | Commission disbursement authorizations (CDAs), commission statements, invoices, payout / settlement statements |
| **Disclosures** | Seller property-condition disclosures, lead-based-paint disclosures, HOA docs, agency disclosures |
| **Correspondence** | A document that is really just a letter/message with no filing category above |

## Rules

1. **Read the content, not just the filename.** A file named `scan_0007.pdf` that
   contains a CDA is a *Commission Statement*, not correspondence.
2. **Exactly one destination per attachment.** No document is filed twice.
3. **Pick from the enum only.** Never invent a new folder name.
4. **Confidence.** Report a 0–1 confidence. Low confidence is a signal for a human
   to glance at it — it does not stop the filing.
5. **Do not move money or send anything.** Filing organizes copies; it never
   forwards a document to title, a client, or accounting on its own. Those are
   surfaced as *action items* for the agent to approve.

## Action items (follow-ups)

Separately from filing, scan every message for something the agent must *do*:
reply to a client, share a report before a deadline, forward a CDA to title.
Only include tasks grounded in an actual message — never invent work. Rank
`high` / `medium` / `low` and include a short timing hint when the message
implies one.
