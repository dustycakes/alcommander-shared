# sku-dial — canonical SKU dialer state

The pure digit/auto-dash logic behind a numeric SKU dialer. **The dash is
derived, never stored** — the operator never types or deletes one.

```
""  → ""        "5"    → "5"
"55" → "55-"    "5512" → "55-12"
```

Backspacing past the dash removes the digit *and* the dash together.

## Why this is here

Promoted from Kanban-Pulse (`lib/search/sku-dial.ts`) 2026-07-25. It is the
highest-rated search interaction in the portfolio — two Pulse users
independently called it one of the most useful tools built to date — and it is
the leading candidate for giving Relay floor traction, where operators are on
iPads and a numeric keypad beats a text field.

## API

| Function | Purpose |
|---|---|
| `appendDialDigit(digits, key)` | Append one keypad/keyboard key; ignores non-digits and overflow. |
| `deleteDialDigit(digits)` | Backspace — removes the last digit (the derived dash goes with it). |
| `formatDialTerm(digits)` | The display **and search** term, dash auto-inserted after the 2-digit prefix. |
| `SKU_DIAL_MAX_DIGITS` | `10` — 2-digit prefix + 8-digit canonical suffix. |

State is a raw digit string. `formatDialTerm` produces the term you hand to
`sku-search`'s `buildSkuSearchClause`; the trailing-dash form (`"55-"`) is
deliberately the search term too, since it ILIKE-scopes tighter than bare `55`.

## Design basis

Verified against Pulse prod 2026-07-08: **359/359 standard part numbers have a
2-digit prefix**, so the dash is inserted unconditionally the instant the 2nd
digit lands.

## Known limitation (accepted)

Dashless oddballs like `37341` can't be dialed — they format as `37-341`. Route
those to a free-text search mode, as Pulse does. Dustin signed off on this
trade-off 2026-07-25.

## Consumers

- **Kanban-Pulse** — `lib/search/sku-dial.ts`, live. The implementation this was
  promoted from.
- **Relay** — *not yet.* Parked pending the Relay re-assessment
  (`Relay/REASSESSMENT.md`); the port is a decision for that session.

## Tests

`sku-dial.test.ts` — 20 cases, vitest. This repo has no test runner of its own
yet, so run them from a consuming app or add one. See the root `README.md` for
the open sync-mechanism gap.
