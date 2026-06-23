# sku-search — shorthand-aware SKU search (shared canonical)

The Alcom Genius SKU keyspace is canonical **`FAMILY-NNNNNNNN`** (a zero-padded
8-digit serial, e.g. `54-00000179`). On the floor, people type the **shorthand**
with the leading zeros dropped — `54-179`. Every app that searches SKUs should
resolve that shorthand to the exact item.

`sku-search.ts` is the **canonical implementation**: it builds a PostgREST
`or()` clause that expands `<digits>-<digits>` to a Postgres regex
`^family-0*serial$` (exact suffix after any run of leading zeros — so `54-179`
matches `54-00000179` but never `54-00001790`), with `ilike` fallbacks on the
SKU column + description so partial prefixes (`55-`) and mixed queries
(`54-179 washer`) still match. Pure, column-agnostic (`skuColumn` defaults to
`sku`; Pulse passes `part_number`), trivially unit-testable.

## Status / how it's consumed
`alcommander-shared` is **not yet an importable TS package**, so each app keeps a
**synced copy**:
- **Kanban-Pulse** — `lib/data/parts-search.ts` (the original).
- **Relay** — `lib/data/sku-search.ts`.

**Change this file and propagate to both.** When `alcommander-shared` gains a TS
surface, both apps should import from here and the copies retire (cross-project
consolidation flag — see Alcommander CLAUDE.md).
