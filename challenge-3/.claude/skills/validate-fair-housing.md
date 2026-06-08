---
name: validate-fair-housing
description: Review open-house flyer copy for Fair Housing Act violations before it is rendered or published.
---

# validate-fair-housing

Real-estate advertising is governed by the **Fair Housing Act** (42 U.S.C.
§ 3604(c)) and state equivalents. An ad may not state a preference, limitation,
or discrimination based on a **protected class**, and may not describe the
*likely occupant* instead of the *property*. A non-compliant flyer is real legal
exposure for the agent — so the copy is gated through this check before any
render.

Run this against the flyer copy object (`headline`, `subheadline`, `statLine`,
`description`, `features`, `openHouseLine`, `callToAction`, `socialCaption`)
**after** copywriting and **before** rendering. `compliance.py` enforces it with
an independent Claude call; these are the rules it applies.

## Protected classes — never reference

Race, color, religion, national origin, sex, disability/handicap, and
**familial status** (presence of children / families).

## Violations to flag and rewrite

- **Describing the occupant, not the property:** "perfect for a growing family",
  "ideal for newlyweds / retirees / bachelors", "great for empty nesters".
  → Rewrite to the property feature that prompted it ("spacious 4-bedroom
  layout").
- **Familial status:** "family room" is borderline-acceptable (a room name);
  "family-friendly", "kid-friendly", "no children" are violations.
- **Coded / steering language:** "safe neighborhood", "exclusive", "private
  community", "integrated", "traditional", "walking distance to
  church/temple/synagogue".
- **Ability / access:** "perfect for active adults", "able-bodied", "no
  wheelchair access".
- **Demographic or religious references** of any kind, including in the social
  caption and hashtags.

## Not violations (leave unchanged)

Neutral property features and amenities, prices, specs, room names, location
names, "spacious", "open floor plan", "primary suite", "move-in ready",
"chef's kitchen", "hardwood floors".

## On a violation

- Set `compliant = false` and list each violation with its `field`, the
  offending `text`, the `protectedClass` implicated, and the `issue`.
- Return a `sanitized` copy of **every** field with violations rewritten to
  neutral, property-focused language — preserving the marketing intent and all
  property facts. Do not delete a feature; reword it.
- The renderer always uses the `sanitized` copy. The original is never
  published.

## Honest limits

- This is an assistive check, not legal advice. It catches the common,
  well-documented patterns; an agent's broker compliance team is still the
  final authority. Surface the violations list to the user so a human can
  confirm.
