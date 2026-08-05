// THE PUSH-COLUMN CONTRACT (data-protection gate 4), extracted from `map_editor.js`.
//
// WHY IT IS ITS OWN MODULE, AND WHY THIS ONE FIRST. Every harness in `client2/tests/` that
// scores `map_editor.js` slices its functions out of the source TEXT and re-declares the
// module's globals around them. That is forced, not stylistic: a function that reads a module
// global cannot be called twice with different state, so a harness has no way to run it except
// to extract it and rebuild the world. The cost is that the FILE's structure acquires a veto
// over refactoring it (see the `getDieIndex` and `getWaferBoundingBox` notes in
// `map_editor.js`, both of which forbid an extraction because four harnesses would die).
//
// These three symbols were measured to be the only group in that file with NO module-mutable
// dependency, direct or transitive, and no read of `el`: they take everything as arguments and
// return everything they decide. So they can simply be imported, and the three harnesses that
// scored them by slicing (`push_gate`, `virtual_column_render`, `map_key_datalist`) now hold
// the real module object instead of a re-parsed copy of its text.
//
// KEEP IT A LEAF. It imports nothing, on purpose: `push_gate_harness` and
// `virtual_column_render_harness` build their mutants by importing this module's text as a
// `data:` URL, and a relative import cannot resolve inside one. An import added here silently
// turns every mutant into a throw, and a throw scores as a kill -- a perfect mutation report
// in which nothing was ever executed.
//
// THE PRIMITIVE: docs/architecture/PRIMITIVES.md records this gate (`deed6d2`). Its "어디"
// row names `map_editor.js`; that is now this file.

// [Gate 4 - log-shaped push target] Columns the push payload can NEVER carry or
// that the server manages itself. Union of the two existing classifications:
// the schema endpoint's appended system tail + row identity (main.py:get_table_schema)
// and the write path's skip list (crud.py apply_row_update_internal system_cols,
// which also skips id/updated_by). grid_metadata is included because pushMapData
// serializes it explicitly whenever the column exists.
export const PUSH_SYSTEM_COLUMNS = [
  'created_at', 'updated_at', 'row_id', 'id', 'updated_by', 'business_key_val',
  'is_graph_synced', 'needs_graph_rollback', 'graph_synced_at',
  'grid_metadata'
];

// [Gate 4] Which of the target table's declared columns would a map push DESTROY?
// A ⚡ Push is `replace_map`: every row in the map-key scope is deleted, then rewritten
// from rows that carry only (map keys, x, y, val). Any other data column on the target
// (a log table's business key, timestamps-as-data, second coordinate pairs, equipment
// columns ...) comes back NULL on every row - viewing such a table as a map is fine,
// pushing into it is destruction.
//
// A column is COVERED (survives the push) iff it is:
//   - a map_key_column (written as the constant map scope),
//   - the currently bound x / y / val column,
//   - a system column the server manages (PUSH_SYSTEM_COLUMNS),
//   - the business_key WHEN it is composite-derived from covered columns only -
//     crud.apply_row_update_internal recomputes it from composite_key_source on
//     write, so e.g. bonding_map's pkg_id (base_x_y) survives even though the
//     payload never carries it. dt_log's dt_id has no composite source: not covered.
// Everything else in schema.columns is an unprotected data column -> refuse.
export function getUnprotectedPushColumns(schema, xCol, yCol, valCol) {
  const cols = Array.isArray(schema && schema.columns) ? schema.columns : [];
  const covered = new Set([
    ...(Array.isArray(schema && schema.map_key_columns) ? schema.map_key_columns : []),
    xCol, yCol, valCol,
    ...PUSH_SYSTEM_COLUMNS
  ]);
  const bk = schema && schema.business_key;
  const src = Array.isArray(schema && schema.composite_key_source) ? schema.composite_key_source : [];
  if (bk && src.length > 0 && src.every(c => covered.has(c))) covered.add(bk);
  return cols.filter(c => !covered.has(c));
}

// [Gate 4] Full gate decision for one push target. One function so the harness
// executes the same branch pushMapData acts on:
//   'clean'   - no data columns outside the map contract: no gate friction at all.
//   'confirm' - extras exist BUT the site declared `map_push_ok: true` on the table
//               (table_config -> /schema): one loss-acknowledging confirm, then proceed.
//   'block'   - extras exist and no declaration: hard refusal.
export function logShapedPushDecision(schema, xCol, yCol, valCol) {
  const extras = getUnprotectedPushColumns(schema, xCol, yCol, valCol);
  if (extras.length === 0) return { mode: 'clean', extras };
  return { mode: (schema && schema.map_push_ok === true) ? 'confirm' : 'block', extras };
}
