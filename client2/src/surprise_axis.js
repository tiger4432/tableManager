// ============================================================
// surprise_axis.js — 3축 맵의 «실물» 다리: 등록된 프레임 선언 + valid die 레퍼런스.
//
// This is the only file on this screen that talks to the network for map data,
// and it exists because the owner's third constraint is about PROVENANCE:
// the wafer under the defects has to be the registered one, not a drawn circle.
//
// 🔴 IT CONSUMES ROUTES THAT ARE ALREADY DEPLOYED. The frame declaration and the
// valid-die mask are read through the generic table routes the map editor has
// always used — no new server work is needed for the FLOOR to be real today:
//
//   GET /tables/{table}/schema                 -> {map_key_columns, columns[…]}
//   GET /tables/wafer_map_metadata/data?filters=…  -> rows[].data.grid_metadata.value
//                                                     (a JSON STRING)
//   GET /tables/valid_die_ref/data?filters=…       -> rows[].data.{x,y,val}.value
//                                                     ROW PRESENCE IS THE MASK
//
// 🔴 THE DEFECT OVERLAY IS THE PART THAT IS NOT SERVED YET. Its proposed shape is
// pinned in `surprise_map_core.js`'s header (`GET /api/ledger/lot_axis_map`).
// Until it lands the panels draw the real wafer and say 「불량 좌표 미배포」 —
// which is the honest picture, not a placeholder.
//
// 🔴 A PARTIAL MASK IS REFUSED, NOT DRAWN. A valid-die reference larger than the
// cap comes back as a refusal with the count, because a mask truncated at N rows
// draws a wafer with holes that are not in the wafer — a lie that looks like data.
// ============================================================

import { API_BASE } from './config.js';
import { decomposeMapKey } from './map_key.js';

//: The whole mask has to be present for the mask to mean anything (see header),
//: so this is a REFUSAL THRESHOLD rather than a page size. Sized well above a
//: 300 mm wafer at fine pitch; a reference beyond it is reported by count.
export const MASK_CAP = 60000;

const schemaCache = new Map();
const floorCache = new Map();

function textFilter(value) {
  return { filterType: 'text', type: 'equals', filter: String(value) };
}

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/** A table's declared map key columns — cached, one request per table per load. */
async function mapKeyColumns(table) {
  if (schemaCache.has(table)) return schemaCache.get(table);
  const p = getJson(`${API_BASE}/tables/${encodeURIComponent(table)}/schema`)
    .then((body) => ({
      keys: Array.isArray(body && body.map_key_columns) ? body.map_key_columns : [],
      types: (body && body.column_types) || {},
    }))
    .catch(() => ({ keys: [], types: {} }));
  schemaCache.set(table, p);
  return p;
}

/**
 * The REGISTERED frame declaration for one map.
 *
 * `grid_metadata` is stored as a JSON string, so a parse failure is a real
 * outcome and is reported as one — an unparsable declaration must not degrade
 * into the client's substituted defaults, which is precisely how a map ends up
 * drawn on a frame nobody declared.
 */
async function loadFrameMeta(table, mapId) {
  const filters = encodeURIComponent(JSON.stringify({
    target_table: textFilter(table),
    map_id: textFilter(mapId),
  }));
  const body = await getJson(`${API_BASE}/tables/wafer_map_metadata/data?limit=2&filters=${filters}`);
  const rows = Array.isArray(body && body.data) ? body.data : [];
  if (!rows.length) return { meta: null, reason: 'wafer_map_metadata에 등록 없음' };
  const cell = rows[0] && rows[0].data && rows[0].data.grid_metadata;
  const raw = cell && cell.value !== undefined ? cell.value : null;
  if (raw === null || raw === undefined || raw === '') {
    return { meta: null, reason: 'grid_metadata 비어 있음' };
  }
  if (typeof raw === 'object') return { meta: raw, reason: '' };
  try {
    return { meta: JSON.parse(String(raw)), reason: '' };
  } catch (err) {
    return { meta: null, reason: `grid_metadata 파싱 실패: ${String((err && err.message) || err)}` };
  }
}

/**
 * The valid-die mask for one reference — every row, or a refusal.
 *
 * The map key is decomposed against the table's OWN declared key columns rather
 * than split on a convention this file invents, so a reference table that keys on
 * something other than `(product, type)` still resolves.
 */
async function loadMaskCells(table, mapId) {
  const { keys, types } = await mapKeyColumns(table);
  const parts = keys.length ? decomposeMapKey(keys, mapId, types) : {};
  const filters = {};
  for (const k of Object.keys(parts)) filters[k] = textFilter(parts[k]);
  const q = Object.keys(filters).length
    ? `&filters=${encodeURIComponent(JSON.stringify(filters))}`
    : '';
  const body = await getJson(`${API_BASE}/tables/${encodeURIComponent(table)}/data?limit=${MASK_CAP + 1}${q}`);
  const rows = Array.isArray(body && body.data) ? body.data : [];
  const total = Number.isFinite(Number(body && body.total)) ? Number(body.total) : rows.length;
  if (total > MASK_CAP || rows.length > MASK_CAP) {
    return { cells: null, reason: `레퍼런스 ${total}칸 — 상한 ${MASK_CAP} 초과, 부분 마스크는 그리지 않습니다` };
  }
  const cells = [];
  for (const row of rows) {
    const d = (row && row.data) || {};
    const x = d.x && d.x.value !== undefined ? d.x.value : null;
    const y = d.y && d.y.value !== undefined ? d.y.value : null;
    if (x === null || y === null) continue;
    cells.push({ x, y });
  }
  return { cells, reason: cells.length ? '' : '레퍼런스 행 0' };
}

/**
 * One reference (`table|map_id`) resolved to `{frame, cells}` — cached forever
 * per page load, because a mask does not change while somebody reads a table.
 */
export function loadFloor(table, mapId) {
  const key = `${table}|${mapId}`;
  if (floorCache.has(key)) return floorCache.get(key);
  const p = Promise.all([loadFrameMeta(table, mapId), loadMaskCells(table, mapId)])
    .then(([frame, mask]) => ({
      frame: frame.meta,
      cells: mask.cells,
      reason: [frame.reason, mask.reason].filter(Boolean).join(' · '),
    }))
    .catch((err) => ({ frame: null, cells: null, reason: String((err && err.message) || err) }));
  floorCache.set(key, p);
  return p;
}

/**
 * Every reference an axis payload names, resolved into the `floors` map
 * `surprise_map_core.js` reads.
 *
 * An axis that carried its own `frame` and `floor` inline is skipped — the server
 * having answered fully is the fast path, and asking anyway would spend two
 * requests to re-learn what is already on the page.
 */
export async function resolveFloors(axes, into) {
  const floors = into || {};
  const wanted = [];
  for (const axis of Array.isArray(axes) ? axes : []) {
    // 🔴 THE LANDED SHAPE PUTS IT UNDER THE FRAME: `frame.valid_die_ref` is
    // `{relation, present, map_id}`, and THE MASK RESOLVES. Measured live
    // 2026-08-14 after the server restart: `SYN-VOID-001` slot 07 carries
    // `{relation: "valid_die_ref", present: true, map_id: "SYN-VD_G15X15"}`, all
    // three axes resolve, floor seats 141 / off-floor 0, and the panel's mask code
    // is null where it used to read 「유효 다이 마스크 미적용」.
    //
    // (This comment said the opposite until tonight — that `map_id` was absent and
    // this loop found nothing. It described a real past state, which is exactly
    // why it was dangerous: a stale comment reads as current, and this one would
    // have told the next reader the mask was dead while it was working.)
    //
    // 🔴 THE KEY IS `table|map_id` AND BOTH HALVES MUST AGREE. `relation` names
    // WHICH TABLE the id is an id in, so two references with the same `map_id` in
    // different relations are different masks — dropping either half would serve
    // one wafer's mask under another's frame.
    //
    // A reference with no `map_id` still falls through to `mask_absent` below.
    // That branch is NOT the normal case on live data — it is currently
    // unreachable there, because every usable frame carries a reference and every
    // reference-less frame (the real `BS-2601-*`) is refused earlier as
    // `frame_unusable` (its `cols`/`rows` are `auto_registered`, not declared).
    // It survives on a harness fixture and is kept because a future frame could
    // land in that state — not because anything reaches it today.
    const fr = (axis && axis.frame) || {};
    const ref = fr.valid_die_ref || axis.reference || null;
    if (!ref) continue;
    const table = String(ref.relation || ref.table || '');
    const mapId = ref.map_id !== undefined ? ref.map_id : ref.mapId;
    if (!table || mapId === undefined || mapId === null || mapId === '') continue;
    const key = `${table}|${mapId}`;
    if (floors[key]) continue;
    wanted.push([key, table, String(mapId)]);
  }
  await Promise.all(wanted.map(async ([key, table, mapId]) => {
    floors[key] = await loadFloor(table, mapId);
  }));
  return floors;
}
