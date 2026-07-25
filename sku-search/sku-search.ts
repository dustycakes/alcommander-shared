/**
 * CANONICAL SKU search clause builder — shorthand-aware.
 *
 * Source of truth for every Alcom app that searches the Genius SKU keyspace
 * (Kanban-Pulse, Relay, and future apps). Until alcommander-shared is wired as
 * an importable TS package, each app keeps a copy — change this file and
 * propagate.
 *
 * ACTUAL SYNC STATE (audited 2026-07-25 — read before assuming parity):
 *   - Relay  `lib/data/sku-search.ts`   — in sync, and it is where
 *     `skuTermMatches` was written first (commit f7c4f2b). Backported here.
 *   - Pulse  `lib/data/parts-search.ts` — DIVERGENT BY DESIGN, not stale. It
 *     predates this file, exports `buildPartsSearchClause` returning
 *     `{clause}`, and hardcodes the `part_number` column. Its query logic is
 *     equivalent. It deliberately does NOT carry `skuTermMatches`: every Pulse
 *     search path round-trips to PostgREST, so a client-side matcher would be
 *     dead code there. Do not "fix" Pulse to match this file without a Pulse
 *     surface that filters an already-loaded list.
 *
 * There is no automated drift check yet. Nothing imports this directory, and
 * this repo has no package.json or tests — so "canonical" is currently a claim
 * enforced by hand. Treat that as the open gap.
 *
 * Genius SKUs are canonical "FAMILY-NNNNNNNN" (zero-padded 8-digit serial).
 * Users type the SHORTHAND with leading zeros dropped — "54-179" for
 * "54-00000179". Detect "<digits>-<digits>" and expand to a Postgres regex that
 * matches the exact suffix after any run of leading zeros, so "54-179" hits
 * 54-00000179 but NEVER 54-00001790. The ilike fallbacks on the sku column +
 * description stay as companions so partial prefixes ("55-") and mixed queries
 * ("54-179 washer") still match.
 *
 * Pure function — no DB client, trivially unit-testable, column-agnostic
 * (`skuColumn` defaults to "sku"; Pulse passes "part_number").
 */
const SHORTHAND = /^(\d+)-(\d+)$/;

function escapeForPostgrest(s: string): string {
  return s.replace(/[,()]/g, " ");
}

export function buildSkuSearchClause(
  rawTerm: string,
  skuColumn = "sku"
): string | null {
  const term = rawTerm.trim();
  if (!term) return null;

  const safe = escapeForPostgrest(term);
  const m = term.match(SHORTHAND);
  if (m) {
    const regex = `^${m[1]}-0*${m[2]}$`;
    return [
      `${skuColumn}.match.${regex}`,
      `${skuColumn}.ilike.%${safe}%`,
      `description.ilike.%${safe}%`,
    ].join(",");
  }

  return `${skuColumn}.ilike.%${safe}%,description.ilike.%${safe}%`;
}

/**
 * Client-side counterpart to buildSkuSearchClause — does one SKU/description row
 * match a search term? Mirrors the same shorthand rule (so "55-153" matches
 * "55-00000153" but never "55-00001530"), plus substring fallbacks on sku +
 * description.
 *
 * Use it wherever an app filters an ALREADY-LOADED list (Relay's zone order
 * sheet, `components/order/order-flow.tsx`) so the instant client-side filter
 * can't hide a row the server search would have returned. That mismatch was a
 * real bug in Relay before this existed: a shorthand query hid saved items that
 * were sitting right there.
 *
 * Apps whose every search path round-trips to the server (Pulse today) do not
 * need this.
 */
export function skuTermMatches(
  rawTerm: string,
  sku: string,
  description = ""
): boolean {
  const term = rawTerm.trim().toLowerCase();
  if (!term) return true;
  const s = sku.toLowerCase();
  const m = term.match(SHORTHAND);
  if (m && new RegExp(`^${m[1]}-0*${m[2]}$`).test(s)) return true;
  return s.includes(term) || description.toLowerCase().includes(term);
}
