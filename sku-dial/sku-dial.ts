/**
 * CANONICAL SKU dial state — the pure digit/auto-dash logic behind a numeric
 * SKU dialer.
 *
 * Promoted here from Kanban-Pulse (`lib/search/sku-dial.ts`) on 2026-07-25.
 * Rationale: it is the highest-rated search interaction built so far — two
 * Pulse users independently called it one of the most useful tools to date —
 * and it is the strongest candidate for giving Relay traction on the floor,
 * where operators are on iPads and a numeric keypad beats a text field.
 *
 * Pulse remains the live implementation; this copy is the source of truth for
 * the next consumer. Relay does NOT yet consume it — Relay is parked pending a
 * top-to-bottom re-assessment (see `Relay/REASSESSMENT.md`), and porting it is
 * a decision for that session, not a drive-by.
 *
 * Pure functions, zero dependencies, no framework. Ships with its 20-case test
 * suite alongside (`sku-dial.test.ts`, vitest).
 *
 * State is a raw digit string; the dash is DERIVED, never stored. Verified
 * against prod 2026-07-08: 359/359 standard part numbers have a 2-digit
 * prefix, so the dash is inserted unconditionally the instant the 2nd digit
 * lands ("55" renders "55-"), and backspacing past it removes the digit AND
 * the dash together — the operator never types or deletes a dash.
 *
 * Known limitation (accepted, plan §3): dashless oddballs like "37341"
 * can't be dialed (they format as "37-341"); the ABC mode's free-text
 * input is their path.
 */

/** 2-digit prefix + up to 8-digit canonical suffix — pasting/dialing a full
 *  canonical SKU ("5500000012" → "55-00000012") lands an exact match. */
export const SKU_DIAL_MAX_DIGITS = 10;

/** Append one keypad/keyboard key; ignores non-digits and overflow. */
export function appendDialDigit(digits: string, key: string): string {
  if (!/^[0-9]$/.test(key)) return digits;
  if (digits.length >= SKU_DIAL_MAX_DIGITS) return digits;
  return digits + key;
}

/** Backspace — removes the last digit (the derived dash goes with it). */
export function deleteDialDigit(digits: string): string {
  return digits.slice(0, -1);
}

/**
 * The display/search term: dash auto-inserted after the 2-digit prefix.
 * "5" → "5" · "55" → "55-" · "5512" → "55-12". The trailing-dash form is
 * deliberately the SEARCH term too — "55-" ILIKE-scopes to 55- parts,
 * tighter than bare "55".
 */
export function formatDialTerm(digits: string): string {
  if (digits.length < 2) return digits;
  return `${digits.slice(0, 2)}-${digits.slice(2)}`;
}
