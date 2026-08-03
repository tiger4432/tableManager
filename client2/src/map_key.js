// ── map_key.js — THE client-side half of map identity. ────────────────────────
//
// Moved out of map_editor.js unchanged (refactoring round 1, seam "map-key"). Every
// function below is byte-identical to the form it had there; the ONLY edits are the
// `export` keywords and `getMapIdFromMeta` taking the table schema as an argument
// instead of reading map_editor's module-level `tableSchema` (read-only there — it is
// passed in rather than re-exported as shared mutable state).
//
// WHY IT IS ITS OWN MODULE. These six functions call nothing outside themselves and
// nothing outside them writes what they read, so they are the one part of the editor
// that can be held to the server's answer on its own. `client2/tests/seam_7b_oracle.py`
// scores this spelling against the live `server/map_overlay.py` value-for-value, and
// `contracts/map_seam/vectors.json` pins the same names — both read THIS file now.
//
// ---------------------------------------------------------------------------
// [7b] Canonical key values — THE client-side half of map identity.
//
// Production defect (2026-07-28): a `number`-declared slot column stores 1, so the identity
// registered in wafer_map_metadata reads 'LOT_1' — while a parsed material token supplies
// '01' (and a Float column round-trips '1.0'). Composing with the raw value then misses
// silently: the cell data opens (crud casts data filters by declared column type) while the
// meta lookup returns nothing, so the map "has no spec" and alignment degrades to identity.
//
// The server half is live (`map_overlay.canonical_key_value`, `ab6ac02`). THIS IS THE MIRROR
// OF THAT FUNCTION and the two must agree value-for-value — the whole defect was the two
// sides disagreeing. Do not fork it, and do not add a second canonicalisation anywhere in
// the client: `composeMapId` / `decomposeMapKey` / `canonicalMapKey` are its only use forms.
//
// Known deliberate deviations from the Python (none of them key-shaped values):
//   · a JS boolean stringifies 'true', Python 'True'.
//   · Python accepts underscore digit separators ('1_0' -> '10'); '_' is the key separator
//     here, so a part can never legitimately contain one and we preserve the original.
//   · integers beyond Number.MAX_SAFE_INTEGER: the digit walk below is exact for any length,
//     but a value that arrived as a JS number was already lossy before we saw it.
// ---------------------------------------------------------------------------

const CANON_INT_RE = /^[+-]?[0-9]+$/;
// DECIMAL floats only. `Number('0x10')` is 16 while Python's `float('0x10')` raises, so
// using Number() as the readability test would canonicalise '0x10' to '16' — inventing a
// value the server never stores. Unreadable must stay unreadable (trimmed original).
const CANON_FLOAT_RE = /^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/;

// str(int(s)) without parseInt — exact for arbitrarily long digit strings.
function canonIntString(s) {
  const neg = s[0] === '-';
  let d = (s[0] === '+' || s[0] === '-') ? s.slice(1) : s;
  d = d.replace(/^0+/, '');
  if (d === '') d = '0';
  return (neg && d !== '0') ? `-${d}` : d;
}

// Value + DECLARED column type -> canonical key string.
//   · "number": integer-parse ('01' / ' 1 ' / '1.0' are the same key). A non-integral numeric
//     keeps its repr ('7.5'); an UNREADABLE value keeps its trimmed original — the lookup
//     misses honestly instead of inventing a key.
//   · anything else (string / undeclared): trimmed as-is. Padding may be meaningful.
//   · null/undefined stay null (composition sites decide their own placeholder).
export function canonicalKeyValue(value, colType) {
  if (value === null || value === undefined) return null;
  if (colType === 'number' && typeof value !== 'boolean') {
    if (typeof value === 'number') {
      if (Number.isFinite(value) && Number.isInteger(value)) return String(value);
      return String(value).trim();
    }
    const s = String(value).trim();
    if (CANON_INT_RE.test(s)) return canonIntString(s);
    if (CANON_FLOAT_RE.test(s)) {
      const f = Number(s);
      if (Number.isFinite(f) && Number.isInteger(f)) return String(f);
    }
    return s;
  }
  if (typeof value === 'number' && Number.isFinite(value) && Number.isInteger(value)) {
    // A float VALUE is numeric regardless of the declared type — '3.0' is a repr artifact,
    // not data (mirrors the server, which pinned this against crud.clean_str_value).
    return String(value);
  }
  return String(value).trim();
}

// Identity components joined with '_'. Each component is canonicalised by the DECLARED type
// of its column, because the meta row being looked up was registered from that column's
// stored value and must be composed the same way.
export function composeMapId(keyColumns, values, columnTypes) {
  const types = columnTypes || {};
  const vals = values || {};
  return (Array.isArray(keyColumns) ? keyColumns : []).map(k => {
    const v = canonicalKeyValue(vals[k], types[k]);
    return (v === null || v === undefined) ? '' : String(v);
  }).join('_');
}

// The inverse of composeMapId — mirrors the server's `build_key_filters` split exactly:
// the LAST column absorbs the remainder, so a lot name containing '_' survives.
export function decomposeMapKey(keyColumns, mapKey, columnTypes) {
  const cols = Array.isArray(keyColumns) ? keyColumns : (keyColumns ? [keyColumns] : []);
  const types = columnTypes || {};
  const out = {};
  if (cols.length === 0) return out;
  const key = String(mapKey === null || mapKey === undefined ? '' : mapKey);
  const parts = key.split('_');
  if (parts.length < cols.length) {
    // Undecomposable — match the whole key against the first column (server parity).
    out[cols[0]] = canonicalKeyValue(key, types[cols[0]]);
    return out;
  }
  const head = parts.slice(0, cols.length - 1);
  const tail = parts.slice(cols.length - 1).join('_');
  [...head, tail].forEach((v, i) => { out[cols[i]] = canonicalKeyValue(v, types[cols[i]]); });
  return out;
}

// A map key string in its canonical spelling. Decompose then recompose — the round-trip
// identity is exactly what makes this idempotent, so applying it twice cannot drift.
export function canonicalMapKey(keyColumns, mapKey, columnTypes) {
  const cols = Array.isArray(keyColumns) ? keyColumns : [];
  const raw = String(mapKey === null || mapKey === undefined ? '' : mapKey);
  if (cols.length === 0 || raw === '') return raw;
  const parts = decomposeMapKey(cols, raw, columnTypes);
  // Undecomposable: decomposeMapKey put the WHOLE key on the first column. Recomposing
  // would append empty tails and invent a different key, so return that single canonical
  // form instead — the honest answer for a key that does not fit the declared shape.
  if (Object.keys(parts).length < cols.length) {
    const only = parts[cols[0]];
    return (only === null || only === undefined) ? raw : String(only);
  }
  return composeMapId(cols, parts, columnTypes);
}

export function getMapIdFromMeta(metaDict, tableSchema) {
  if (!metaDict) return 'default_map';

  let mapKeyCols = tableSchema.map_key_columns;
  if (!mapKeyCols || !Array.isArray(mapKeyCols) || mapKeyCols.length === 0) {
    if (tableSchema.composite_key_source && Array.isArray(tableSchema.composite_key_source)) {
      mapKeyCols = tableSchema.composite_key_source.filter(col => !['x', 'y', 'val', 'die_id', 'code', 'grid_metadata'].includes(col.toLowerCase()));
    }
  }

  // [7b] The declared types come from the SAME table whose rows registered the meta row, so
  // composing here canonicalises identically to the registration side. Columns the user left
  // blank are dropped before composing (long-standing behaviour — a blank must not become an
  // empty component), so composeMapId is fed only the columns that are actually present.
  const colTypes = (tableSchema && tableSchema.column_types) || {};
  if (mapKeyCols && mapKeyCols.length > 0) {
    const present = mapKeyCols.filter(col => {
      const v = metaDict[col];
      return v !== undefined && v !== null && String(v).trim() !== '';
    });
    if (present.length > 0) return composeMapId(present, metaDict, colTypes);
  }

  const allCols = Object.keys(metaDict).filter(col => {
    const v = metaDict[col];
    return v !== undefined && v !== null && String(v).trim() !== '';
  });
  return allCols.length > 0 ? composeMapId(allCols, metaDict, colTypes) : 'default_map';
}
