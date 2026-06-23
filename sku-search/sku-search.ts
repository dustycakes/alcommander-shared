/**
 * CANONICAL SKU search clause builder — shorthand-aware.
 *
 * Source of truth for every Alcom app that searches the Genius SKU keyspace
 * (Kanban-Pulse, Relay, and future apps). Until alcommander-shared is wired as
 * an importable TS package, each app keeps a synced copy (Pulse:
 * lib/data/parts-search.ts; Relay: lib/data/sku-search.ts) — change this file
 * and propagate.
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
