---
name: validate-doc-fields
description: Validate fields extracted from a contract or listing agreement before creating in reZen.
---

# validate-doc-fields

Before calling `create_from_contract` or `create_from_listing`, run these checks
against the parsed `fields` dict.

## Common (both docTypes)

- `address.state` MUST be enum form: all caps with underscores (e.g.
  `NEW_YORK`, not `New York` or `NY`). If the model returned a non-enum form,
  reject and re-extract.
- `address.zip` MUST be a 5-digit US zip (or `12345-6789`). Reject otherwise.
- `address.street`, `address.city` MUST be non-empty strings.

## Contract

- `salePrice` MUST be a positive number > 1,000.
- `contractDate` and `closingDate` MUST be ISO `YYYY-MM-DD` and parseable.
- `closingDate` MUST be on or after `contractDate`.
- `buyer.firstName`, `buyer.lastName`, `seller.firstName`, `seller.lastName`
  MUST be non-empty.
- If `commissionPercent` is set, it must be 0 < pct <= 10.

## Listing

- `listPrice` MUST be a positive number > 1,000.
- `listingDate` and `expirationDate` MUST be ISO and parseable.
- `expirationDate` MUST be after `listingDate`.
- `seller.firstName`, `seller.lastName` MUST be non-empty.
- If `commissionPercent` is set, it must be 0 < pct <= 10.

## On failure

- Print a single line per violation, prefixed `validate-doc-fields:`.
- Exit non-zero before any reZen API call.
- Do NOT silently coerce — if the document is bad, the user needs to know.
