# Skill: Build the deal calendar

The rule that governs how `dates.py` turns a contract into a calendar. In real
estate a missed contingency date can cost a client their deposit or the deal, so
the extraction is conservative: **never invent a date, and remind early.**

## Milestones to extract

Pull every dated milestone from the contract (primary) and emails:

| Category | Typical milestone |
|----------|-------------------|
| **Attorney Review** | Attorney-review period expiration |
| **Inspection** | Inspection contingency deadline |
| **Appraisal** | Appraisal contingency date |
| **Financing** | Mortgage / financing commitment date |
| **Walk-Through** | Final walk-through |
| **Closing** | Closing / settlement date |
| **Other** | Any other explicit deadline (effective date, deposit due, etc.) |

## Rules

1. **ISO dates only.** Every `date` is `YYYY-MM-DD`. Resolve prose like
   "shall expire at 5:00 PM on July 18, 2026" to `2026-07-18`.
2. **Never invent a date.** If a contingency is described but carries no date,
   skip it. A guessed deadline is worse than a missing one.
3. **The contract wins ties.** When the same milestone appears in both the
   contract and an email, use the contract's date and cite the contract as
   `source`.
4. **Reminder policy** (`reminder_days_before`):
   - Contingency deadlines (attorney review, inspection, appraisal, financing): **3 days**
   - Closing and final walk-through: **7 days**
   - Informational dates (effective date, etc.): **0** (no reminder)
5. Each milestone becomes an all-day event in `calendar.ics` with a `VALARM`
   reminder, importable into Google/Apple Calendar.
