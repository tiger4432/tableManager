// ═══════════════════════════════════════════════════════════════════════════════
// THE SAVE CONTRACT FOR A VALID-DIE MAP. PURE -- builds and gates a request; sends nothing.
// NO DOM. NO TRANSPORT. NO MODULE-LEVEL MUTABLE STATE.
//
// 🔴 WHY THIS IS NOT AN EDIT. A valid-die map is what OTHER maps take as their floor. When a
//    map declares `valid_die_ref`, the referenced map's cell set becomes the WHOLE answer to
//    "which dies exist" -- the wafer circle is demoted to a generator and does not participate
//    (server rule 2 in `map_overlay.py`). Writing one therefore changes what every consumer of
//    that reference means by a coordinate. It is closer in weight to a confirmation than to a
//    save, and the control is shaped accordingly: read is frictionless, the write is armed and
//    then committed, once.
//
// ── WHERE IT GOES, MEASURED (dev box, 2026-08-05 -- NOT production) ─────────────
// A valid-die map is ALWAYS read from the table `valid_die_ref`, whatever a declaration names
// (`map_overlay.parse_valid_die_ref`, the read pin). On this box the four floors that resolve
// all live there with a `(product, type)` composite key and a matching `wafer_map_metadata`
// row registered under `target_table = 'valid_die_ref'`. Every declaration that resolves has
// BOTH halves; every declaration that does not is missing one of them. So the contract below
// requires both, and requires the key to decompose into the declared key columns.
//
// ── THE VERSION QUESTION, AND THE ANSWER ────────────────────────────────────────
// `frame_confirmation` versions in place: a new row gets `version = max + 1` and the previous
// row gets `superseded_by`, and nothing is destroyed. The obvious move is to copy that here.
// IT IS THE WRONG MOVE, FOR A REACHABILITY REASON:
//
//   * A frame confirmation is reached through `confirmation_uid`. A consumer holds the uid, so
//     a superseding version is addressable and an old one stays addressable.
//   * A valid-die floor is reached through a NAME written into another map's metadata --
//     `{"table": ..., "map_id": ...}`. There is no uid in that declaration and no place to put
//     one without changing a stored schema. An in-place version would therefore be
//     UNADDRESSABLE: every existing declaration would silently follow the newest version, which
//     is precisely the silent reinterpretation this module exists to prevent.
//
// So the version is the KEY, and the contract splits by what changed:
//
//   CELL SET CHANGED  -> one `replace_map` write under the same key. Versionless on purpose:
//                        adding a version column here would be the FOURTH spelling of "which
//                        reading was in force" (MAP_ALIGNMENT_SPEC 0.3 item 4 names the three
//                        that already exist and forbids a fourth).
//   GEOMETRY CHANGED  -> REFUSED. Stored coordinates are bounding-box relative and the box is
//                        derived from the geometry, so changing rotation/side/pitch/offset/
//                        start under a fixed key moves EVERY consumer's coordinate without
//                        touching a single consumer row. A geometry change is a different
//                        floor and must take a different key; the old key stays readable for
//                        whatever already points at it.
//
// That split also removes the two-request hazard. The write is a metadata upsert followed by
// one `replace_map` cell write; because geometry changes are refused, the metadata half is
// idempotent, so a partial failure cannot leave a NEW spec sitting over OLD cells (which would
// resolve successfully and be wrong).
//
// 🔴 NO PERCENTAGE, NO SHARE, NO RATIO. Not in a field, not in the confirmation sentence.
// ═══════════════════════════════════════════════════════════════════════════════

import { decomposeMapKey, canonicalMapKey } from '../map_key.js';
import { tableCells, expressible } from './brush.js';
import { isDeclaredValue } from './legend.js';

/**
 * The pinned floor table. Not a preference: the server resolves EVERY `valid_die_ref`
 * declaration against this name regardless of what the declaration says, so a map authored
 * anywhere else has no consumer.
 */
export const FLOOR_TABLE = 'valid_die_ref';

/** The metadata table a floor must also be registered in, or its frame is unknowable. */
export const META_TABLE = 'wafer_map_metadata';

/**
 * The two routes this contract's request is meant for. Written once, here.
 * Both already exist and are the SAME endpoints the legacy map push uses -- no new REST
 * signature is invented, because a boundary contract is not this module's to declare.
 */
export const WRITE_ROUTES = Object.freeze({
  meta: `/tables/${META_TABLE}/data/updates`,
  cells: `/tables/${FLOOR_TABLE}/data/updates`,
});

/** Named refusals. Nominal register -- these are states, not sentences. */
export const SAVE_REFUSAL = Object.freeze({
  NO_GEOMETRY: '기하 선언 없음',
  NOT_FROM_SERVER: '서버본 아님',
  TRUNCATED_READ: '조회 절단',
  WRONG_TABLE: '유효 다이 테이블 아님',
  KEY_SHAPE: '맵 키 형태 불일치',
  EMPTY: '셀 없음',
  GEOMETRY_CHANGED: '기하 변경 - 새 키 필요',
  SELF_REFERENCE: '자기 참조 선언',
  UNDECLARED_VALUE: '범례 밖 값',
  UNEXPRESSIBLE_CELL: '격자 밖 좌표',
  NO_AUTHOR: '작성자 없음',
});

/**
 * The geometry terms that participate in the bounding box, and therefore in what every stored
 * coordinate means. Listed once so "did the geometry change" has ONE definition.
 *
 * `grid_y_invert` is in here because it is a REFLECTION about `box.maxR`, not a translation --
 * it cannot be absorbed by a shift, so flipping it moves rows even when nothing else moved.
 */
export const GEOMETRY_KEYS = Object.freeze([
  'rotation', 'side', 'grid_cols', 'grid_rows', 'grid_y_invert',
  'phys_chip_x', 'phys_chip_y', 'phys_wafer_dia', 'phys_edge_margin',
  'phys_offset_x', 'phys_offset_y', 'start_x', 'start_y',
]);

/**
 * Which geometry terms differ between the stored spec and the one about to be written.
 * Compared as strings after a finite-number normalisation, so `13` and `13.0` are the same
 * declaration and `null` is never confused with `0`.
 *
 * @returns frozen array of key names. Empty means the geometry is unchanged.
 */
export function geometryDelta(storedMeta, nextMeta) {
  const a = storedMeta || {};
  const b = nextMeta || {};
  const changed = [];
  for (const k of GEOMETRY_KEYS) {
    if (spell(a[k]) !== spell(b[k])) changed.push(k);
  }
  return Object.freeze(changed);
}

/**
 * Does the map key decompose into exactly the declared key columns?
 *
 * USES THE EXISTING PRIMITIVE (`map_key.decomposeMapKey`), which already mirrors the server's
 * `build_key_filters` split including the last-column-absorbs-the-remainder rule. A second
 * splitter here would be the classic second spelling: it would agree on the easy keys and
 * disagree on exactly the ones with a separator in a component.
 *
 * @returns frozen {ok, parts, columns, reason}
 */
export function decomposeFloorKey(mapKey, keyColumns, columnTypes) {
  const cols = Array.isArray(keyColumns) ? keyColumns : [];
  const raw = String(mapKey === null || mapKey === undefined ? '' : mapKey).trim();
  if (cols.length === 0) {
    return frozen({ ok: false, parts: null, columns: cols, reason: '키 컬럼 선언 없음' });
  }
  if (raw === '') {
    return frozen({ ok: false, parts: null, columns: cols, reason: '맵 키 없음' });
  }
  const parts = decomposeMapKey(cols, raw, columnTypes);
  const filled = cols.filter(c => {
    const v = parts[c];
    return v !== null && v !== undefined && String(v) !== '';
  });
  if (filled.length !== cols.length) {
    return frozen({
      ok: false, parts, columns: cols,
      reason: `'${raw}'가 ${cols.join(' · ')} ${cols.length}칸으로 나뉘지 않음`,
    });
  }
  return frozen({ ok: true, parts: Object.freeze({ ...parts }), columns: cols, reason: null });
}

/**
 * THE GATE. Every precondition of a floor write, each as a named refusal.
 *
 * All of them are checked; the first failure does not stop the rest. An operator who is told
 * one reason, fixes it, and is then told a second reason has been made to pay twice for one
 * screen, and the second trip is where they stop reading.
 *
 * @param {object} input
 * @param {string} input.table         where the write is aimed
 * @param {string} input.mapKey
 * @param {Array}  input.keyColumns    the floor table's declared `map_key_columns`
 * @param {object} input.columnTypes   the floor table's declared `column_types`
 * @param {object} input.cellTable     from `brush.createCellTable` / `brushStroke`
 * @param {object} input.authorable    from `brush.authorableSeats`
 * @param {object} input.legend        from `legend.resolveLegend`
 * @param {object} input.storedMeta    the spec as the SERVER currently holds it, or null
 * @param {object} input.nextMeta      the spec about to be written
 * @param {string} input.origin        'server' when the screen derives from a server read
 * @param {boolean} input.truncated    true when the read that built the screen was cut short
 * @param {number} input.storedCellCount  the floor's current cell count, from the same read
 * @param {string} input.confirmedBy
 * @returns frozen {ok, refusals, cells, addedCount, removedCount, geometryChanged}
 */
export function checkSaveGate(input) {
  const inp = input || {};
  const refusals = [];
  const add = (token, detail) => refusals.push(Object.freeze({ token, detail: detail || null }));

  // ① NO GEOMETRY, NO WRITE. Without a bounding box the stored coordinates have no origin, so
  //    what would be written is a set of numbers with no declared meaning. Degrading to an
  //    identity box would mirror `grid_y_invert` rows about zero and send every row negative.
  const authorable = inp.authorable;
  if (!authorable || authorable.boxKnown !== true) {
    add(SAVE_REFUSAL.NO_GEOMETRY, (authorable && authorable.refusal) || null);
  }

  // ② THE SCREEN MUST DERIVE FROM A SERVER READ. This is the invariant whose breach let ONE
  //    failed lookup, followed by an ordinary edit, delete an entire plan: the client did not
  //    know the server's state and wrote anyway. `replace_map` makes that fatal here too.
  if (inp.origin !== 'server') add(SAVE_REFUSAL.NOT_FROM_SERVER, String(inp.origin || '미상'));

  // ③ A TRUNCATED READ IS DEMOTED TO A FAILURE, NOT USED. Replacing from a partial set deletes
  //    the part that was never fetched, and the screen showed no sign it was missing.
  if (inp.truncated === true) add(SAVE_REFUSAL.TRUNCATED_READ);

  // ④ The pinned table. Anywhere else has no consumer, measured: every declaration is read
  //    from `valid_die_ref` regardless of what it names.
  if (inp.table !== FLOOR_TABLE) add(SAVE_REFUSAL.WRONG_TABLE, String(inp.table || '미지정'));

  // ⑤ The key must decompose into the declared columns, or the cells and the metadata row end
  //    up under different identities and the map resolves as "spec present, cells absent".
  const key = decomposeFloorKey(inp.mapKey, inp.keyColumns, inp.columnTypes);
  if (!key.ok) add(SAVE_REFUSAL.KEY_SHAPE, key.reason);

  const cells = tableCells(inp.cellTable);

  // ⑥ AN EMPTY FLOOR IS NOT AN ANSWER. The server reads a zero-cell reference as "not loaded
  //    yet", never as "no valid dies", because taking zero as the answer invalidates the whole
  //    consumer map. Writing zero therefore creates a state nobody can read as intended.
  if (cells.length === 0) add(SAVE_REFUSAL.EMPTY);

  // ⑦ GEOMETRY IS PART OF THE IDENTITY. See the header: an in-place geometry change is
  //    unaddressable, so it is refused and a new key is required.
  const delta = inp.storedMeta ? geometryDelta(inp.storedMeta, inp.nextMeta) : Object.freeze([]);
  if (delta.length > 0) add(SAVE_REFUSAL.GEOMETRY_CHANGED, delta.join(', '));

  // ⑧ A floor must not itself declare a floor. The server refuses a valid-die map that carries
  //    `valid_die_ref`; saying so here means the operator learns it before the round trip.
  const nextMeta = inp.nextMeta || {};
  if (nextMeta.valid_die_ref !== null && nextMeta.valid_die_ref !== undefined) {
    add(SAVE_REFUSAL.SELF_REFERENCE);
  }

  // ⑨ Every authored value must be in the declared vocabulary, and every authored coordinate
  //    must be one the frame can express. Both are counted over ALL cells, not sampled: a
  //    single unexpressible coordinate is a die written onto nothing.
  const undeclared = [];
  const unexpressible = [];
  for (const c of cells) {
    if (inp.legend && !isDeclaredValue(inp.legend, c.value)) undeclared.push(c);
    if (authorable && authorable.boxKnown === true && !expressible(authorable, c.x, c.y)) {
      unexpressible.push(c);
    }
  }
  if (undeclared.length > 0) add(SAVE_REFUSAL.UNDECLARED_VALUE, countDetail(undeclared.length));
  if (unexpressible.length > 0) {
    add(SAVE_REFUSAL.UNEXPRESSIBLE_CELL, countDetail(unexpressible.length));
  }

  // ⑩ A confirmation with no author is not a confirmation.
  if (!inp.confirmedBy || String(inp.confirmedBy).trim() === '') add(SAVE_REFUSAL.NO_AUTHOR);

  const storedCount = Number.isFinite(Number(inp.storedCellCount))
    ? Number(inp.storedCellCount) : null;

  return Object.freeze({
    ok: refusals.length === 0,
    refusals: Object.freeze(refusals),
    cells,
    cellCount: cells.length,
    storedCellCount: storedCount,
    geometryChanged: delta.length > 0,
    geometryDelta: delta,
    keyParts: key.ok ? key.parts : null,
  });
}

/**
 * Build the request. THROWS when the gate refuses -- a refused write must not be able to
 * produce a body that some other code path could still send.
 *
 * The result is two requests in a stated order, not one blob: the metadata upsert (idempotent,
 * because a geometry change was refused above) and then the single `replace_map` cell write.
 *
 * 🔴 `supersedes` NAMES WHAT THIS DESTROYS, and its count comes from the SAME gate result the
 *    screen rendered. It is not recounted here. The last time this system computed one number
 *    in two places the store used `ceil`, the screen used `round`, and the database held 34
 *    while the operator read 33.
 */
export function buildSaveRequest(gate, input) {
  if (!gate || gate.ok !== true) {
    throw new Error(
      'buildSaveRequest called on a refused gate. A refused write must not have a body: '
      + ((gate && gate.refusals) || []).map(r => r.token).join(' / '));
  }
  const inp = input || {};
  const mapId = canonicalMapKey(inp.keyColumns, inp.mapKey, inp.columnTypes);
  const parts = gate.keyParts || {};

  const metaUpdate = {
    row_id: `${FLOOR_TABLE}_${mapId}`,
    data: {
      map_pk: `${FLOOR_TABLE}_${mapId}`,
      target_table: FLOOR_TABLE,
      map_id: mapId,
      grid_metadata: JSON.stringify(inp.nextMeta || {}),
    },
    source_name: 'user',
    updated_by: inp.confirmedBy,
  };

  // The cell rows carry the key columns as COLUMNS, not as a joined string. The joined form is
  // the metadata row's identity; the cell rows are filtered by the columns themselves.
  const cellUpdates = gate.cells.map(c => ({
    data: Object.assign({}, parts, { x: c.x, y: c.y, val: c.value }),
    source_name: 'user',
    updated_by: inp.confirmedBy,
  }));

  return Object.freeze({
    meta: Object.freeze({
      route: WRITE_ROUTES.meta,
      method: 'PUT',
      body: Object.freeze({ updates: Object.freeze([metaUpdate]), silent: false }),
    }),
    cells: Object.freeze({
      route: WRITE_ROUTES.cells,
      method: 'PUT',
      // 🔴 `replace_map: true` IS THE DESTRUCTIVE TERM. It is legal here only because the gate
      //    proved the screen came from a complete server read; on a truncated or unknown read
      //    it deletes whatever it did not see.
      body: Object.freeze({
        updates: Object.freeze(cellUpdates), silent: false, replace_map: true,
      }),
    }),
    supersedes: Object.freeze({
      table: FLOOR_TABLE,
      map_id: mapId,
      cell_count: gate.storedCellCount,
    }),
    writes: Object.freeze({ meta: 1, cells: 1 }),
  });
}

/**
 * The confirm control's state -- arm, then commit. Mirrors the alignment screen's existing
 * pattern rather than introducing a second one: state lives in the caller's session, arming is
 * not a write, the same control arms and commits, and any change to what is being confirmed
 * disarms.
 *
 * FULL SENTENCES APPEAR HERE AND NOWHERE ELSE. This is the write confirmation; everything else
 * on the screen is nominal.
 */
export function writeIntent(gate, opts) {
  const o = opts || {};
  const enabled = !!(gate && gate.ok);
  const armed = enabled && o.armed === true;
  const mapKey = String(o.mapKey || '');
  const replacing = gate && Number.isFinite(gate.storedCellCount) && gate.storedCellCount > 0;

  let sentence;
  if (!enabled) {
    sentence = null;
  } else if (replacing) {
    sentence = `유효 다이 맵 '${mapKey}'의 셀 ${gate.storedCellCount}개를 `
      + `${gate.cellCount}개로 교체합니다. 이 맵을 기준으로 삼는 모든 맵의 유효 다이가 바뀝니다.`;
  } else {
    sentence = `유효 다이 맵 '${mapKey}'을 셀 ${gate.cellCount}개로 새로 등록합니다.`;
  }

  return Object.freeze({
    enabled,
    armed,
    label: armed ? '다시 눌러 확정' : '확정',
    sentence,
    // Nominal, and it names the first blocking state rather than listing all of them in the
    // control. The full list belongs next to the picture, where there is room to read it.
    inertHint: enabled ? null : firstRefusal(gate),
    refusalCount: gate && gate.refusals ? gate.refusals.length : 0,
  });
}

function firstRefusal(gate) {
  const list = (gate && gate.refusals) || [];
  return list.length === 0 ? '준비 안 됨' : list[0].token;
}

/** `N건`. A count, never a share -- there is no denominator anywhere in this module. */
function countDetail(n) {
  return `${n}건`;
}

/**
 * One spelling of a declared value, for comparison only.
 * `null`/`undefined`/`''` all spell as the SAME absence token, which is deliberately NOT `'0'`
 * -- an absent offset and a declared zero offset must not compare equal.
 */
function spell(v) {
  if (v === null || v === undefined || v === '') return ' absent';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  const n = Number(v);
  if (Number.isFinite(n) && String(v).trim() !== '') return String(n);
  return String(v);
}

function frozen(o) {
  return Object.freeze(o);
}
