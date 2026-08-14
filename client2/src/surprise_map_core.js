// ============================================================
// surprise_map_core.js — 마킹한 랏의 3축 맵을, 실제 프레임 위에.
//
// PURE. No DOM, no network, no `window`. Scored under bare node by
// `tests/surprise_harness.mjs`.
//
// 🔴 THE OWNER'S THIRD CONSTRAINT, AND IT IS THE ONLY ONE HE MARKED 🔴:
//   "3축 맵은 목업의 «원형 격자» 금지. 등록된 표준 frame 선언 + 실제 valid die
//    레퍼런스 위에 렌더하라. 좌표는 오리진 기준 칸수, 투영은 transferred 걷기.
//    목업의 동그란 격자는 그림이지 웨이퍼가 아니다 — 그걸 그대로 그리면 없는 것을
//    있는 척하는 것이다."
//
// So this file draws NOTHING it cannot source. Concretely:
//
//   THE FRAME       `wafer_map_metadata.grid_metadata` — the registered
//                   declaration — read through `map2/declaration.js`
//                   (`frameFromDeclaration` / `isFrameUsable`). Not invented,
//                   not defaulted into existence: an undeclared or unusable
//                   frame is a REFUSAL with the declaration's own reason tokens.
//   THE FLOOR       `valid_die_ref` rows. One row = one cell, and the PRESENCE
//                   of the row is the mask — there is no "is this die valid"
//                   column to misread. No reference -> refusal, never a circle.
//   THE SEATING     `map2/seating.js::computeSeating(cells, frame, null)` — the
//                   same arithmetic the map editor seats a map with, imported
//                   rather than re-derived. Coordinates are CELL COUNTS from the
//                   origin box; pitch never places a cell.
//   THE PROJECTION  the server's `transferred` walk. Each axis carries the
//                   defect chips ALREADY IN THAT AXIS'S OWN COORDINATES, because
//                   `server/map_overlay.py::resolve_map_transform` is declared the
//                   single coordinate-transform entry point and a second
//                   implementation in JS is exactly how the picture and the
//                   numbers come to disagree.
//
// 🔴 AND EVERY LEG THAT IS MISSING IS NAMED. A floor with no overlay renders the
// real wafer and says 「불량 좌표 미배포」. A missing frame renders nothing and
// says which axis of the declaration was absent. What never happens is a drawn
// grid standing in for a wafer nobody registered.
//
// ------------------------------------------------------------
// 🔴 THE LANDED CONTRACT — `server/ledger_lots.py::lot_map` (`56d8aae`).
//
//   GET /api/ledger/lot_map?row=<row>&slot=<slot>&kind=<kind>&by=<axis>&window=
//     -> { row, state, generated_at, kind, slot,
//          row_axis: {name, label, source},
//          window: {...},
//          projections: [
//            { axis: "bond"|"dt"|"core", label: "본딩축", sublabel: "스테이지 좌표",
//              state: "ready" | "no_frame" | "unreachable",
//              reason: "no_live_bridge" | "no_registered_frame"
//                    | "frame_ambiguous_across_slots" | null,
//              message: "<한국어 문장>" | null,
//              frame: { state: "ready", table, map_id, grid: <grid_metadata>,
//                       valid_die_ref: {relation, present} }
//                   | { state: "no_frame", reason: "frame_ambiguous_across_slots",
//                       available_slots: [...], available_lots: [...] }
//                   | { state, reason, message }  | null,
//              coordinate_unit: "cells_from_origin",
//              cells: [{x, y, n}], found: <int>, scanned: <int> } ],
//          provenance: {...} }
//
// DIFFS THIS CLIENT ABSORBED (server won every one):
//   `projections`   not `axes`
//   `frame.grid`    carries the grid_metadata; there is no inline `floor`
//   the SLOT LIST arrives as `frame.available_slots` under
//                   `reason: "frame_ambiguous_across_slots"` — so the strip is
//                   READ, not assembled a second time by this client
//   `found`/`scanned` per projection; cells carry `n`
//
// 🔴 AND ONE LEG IS STILL MISSING, NAMED RATHER THAN GUESSED. `valid_die_ref` is
// announced as `{relation, present}` — its presence, not WHICH map. The valid-die
// table is keyed on `(product, type)` while the frame's `map_id` is `{lot}_{slot}`
// on `wafer_map_metadata`; the two key spaces do not meet, so this client CANNOT
// derive which mask belongs to a projection. The panel therefore draws the defect
// chips on the REGISTERED GRID and says 「유효 다이 마스크 미적용」 — the grid is
// declared, the mask is absent, and neither is invented. Reported to the lead PM
// as a one-field request: `valid_die_ref.map_id` on the projection's frame.
// ------------------------------------------------------------

import { frameFromDeclaration, isFrameUsable } from './map2/declaration.js';
import { computeSeating, unionBounds } from './map2/seating.js';

//: 🔴 THE SERVER CONVENTION, NOT THE CLIENT ONE. `dt_frame_transform.STANDARD_FRAME`
//: declares `grid_start_x/y = 1`; the shipped client substitutes 0 in one place
//: and that divergence is a known, boarded defect ([D4] in `map2/declaration.js`).
//: A read-only screen must not pick the losing side of an open question quietly,
//: so it takes the SERVER's and says so on screen.
export const FRAME_DEFAULTS = Object.freeze({ startX: 1, startY: 1 });

//: Axis labels for a CLOSED WIRE ENUM. An axis this file has never heard of keeps
//: its raw spelling rather than vanishing.
const AXIS_LABELS = { bond: '본딩축', dt: 'DT축', core: '코어축' };
const AXIS_HINTS = {
  bond: '본딩 스테이지 좌표 — 뭉치면 스테이지 기하',
  dt: '테이프 좌표 — 줄무늬면 테이프 행',
  core: '웨이퍼 좌표 — 링이면 웨이퍼 공정',
};

//: The refusal vocabulary. TOKENS with sentences beside them, so the screen can
//: print the sentence and the harness can score the token.
export const MAP_REFUSAL = {
  no_axes: '축 선언 없음 — 서버가 투영을 실어오지 않았습니다',
  // 🔴 MEASURED, NOT MISSING. `bonding_log.core_lot`/`cx`/`cy` are NULL across all
  // 357,796 rows, so there is no join to make — and making one is forbidden by
  // R-2026-08-14-D. This sentence stands in the core axis's own place; it is content.
  no_live_bridge: '연결 없음 — 좌표 컬럼이 이 행에서 전부 NULL입니다 (0이 아니라 부재)',
  no_registered_frame: '프레임 미등록 — 등록된 격자 없이는 그리지 않습니다',
  frame_ambiguous_across_slots: '이 행이 프레임 여러 개에 걸쳐 있습니다 — 슬롯을 고르십시오',
  unreachable: '연결 없음 — 이 축을 이을 살아있는 다리가 없습니다',
  frame_unusable: '프레임 선언이 좌표를 세우기에 부족합니다',
  origin_box_unknown: '오리진 박스 미상 — 물리 규격(phys_*) 선언이 없습니다',
  no_cells: '이 행에 이 축의 불량 칩이 없습니다',
  seating_failed: '좌석 계산 실패',
  mask_absent: '유효 다이 마스크 미적용 — 등록 격자 위에 불량 칩만 그립니다',
};

function strOrEmpty(v) {
  return v === null || v === undefined ? '' : String(v);
}

function listOf(v) {
  return Array.isArray(v) ? v : [];
}

function intOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

/**
 * 🔴 A NAMING SEAM BETWEEN TWO MODULES THAT HAVE NEVER MET.
 *
 * `map2/declaration.js::frameFromDeclaration` returns the physical spec as
 * `waferDia / chipX / chipY / offsetX / offsetY / edgeMargin`.
 * `map2/seating.js::physOf` reads `physWaferDia / phys_wafer_dia` (and the same
 * for the rest) and returns `null` for anything else — which makes
 * `boundingBoxOf` null and `boxKnown` false, i.e. a silent refusal.
 *
 * Nothing crossed this seam before: the alignment screen seats with `placeCells`
 * off the server's placement and never calls `computeSeating`, and `brush.js`
 * builds its own frame object. This screen is the FIRST consumer of
 * declaration → seating, so the transcription lives here, in one place, named.
 * It is a transcription and not a derivation — every field is copied, none is
 * computed — and it is reported to the lead PM as a seam worth unifying rather
 * than fixed by editing either module from this lane.
 */
export function seatFrameOf(frame) {
  return {
    rotation: frame.rotation,
    side: frame.side,
    cols: frame.cols,
    rows: frame.rows,
    startX: frame.startX,
    startY: frame.startY,
    invertY: frame.invertY,
    physWaferDia: frame.waferDia,
    physChipX: frame.chipX,
    physChipY: frame.chipY,
    physOffsetX: frame.offsetX,
    physOffsetY: frame.offsetY,
    physEdgeMargin: frame.edgeMargin,
  };
}

export const axisLabel = (axis, given) => {
  if (given) return String(given);
  const key = strOrEmpty(axis);
  return AXIS_LABELS[key] || key || '미상 축';
};

export const axisHint = (axis) => AXIS_HINTS[strOrEmpty(axis)] || '';

/** The key a resolved floor is filed under — `table|map_id`. */
export function referenceKey(ref) {
  if (!ref) return '';
  const table = strOrEmpty(ref.relation !== undefined ? ref.relation : ref.table);
  const mapId = strOrEmpty(ref.map_id !== undefined ? ref.map_id : ref.mapId);
  // 🔴 NO `map_id` MEANS NO RESOLVABLE MASK, AND THAT IS THE HONEST ANSWER. The
  // wire announces presence only; a key built from the relation alone would match
  // whichever mask happened to be cached and draw the wrong wafer.
  if (!table || !mapId) return '';
  return `${table}|${mapId}`;
}

/**
 * Cells as `{x, y, key}` — the shape `computeSeating` consumes.
 *
 * 🔴 A CELL WITH A NON-INTEGER COORDINATE IS DROPPED AND COUNTED, not coerced.
 * `Number('')` is 0, and a coordinate silently becoming (0,0) puts a defect at
 * the origin of a wafer it was never on.
 */
export function toCells(raw) {
  const cells = [];
  let dropped = 0;
  for (const c of listOf(raw)) {
    const x = intOrNull(c && c.x);
    const y = intOrNull(c && c.y);
    if (x === null || y === null) { dropped += 1; continue; }
    const n = intOrNull(c && c.n);
    cells.push({ x, y, n, key: `${x},${y}` });
  }
  return { cells, dropped };
}

function refuse(axis, code, detail) {
  return {
    axis: strOrEmpty(axis && axis.axis),
    label: axisLabel(axis && axis.axis, axis && axis.label),
    hint: axisHint(axis && axis.axis),
    table: strOrEmpty(axis && axis.table),
    basis: strOrEmpty(axis && axis.basis),
    ok: false,
    code,
    why: MAP_REFUSAL[code] || code,
    detail: detail || '',
    floor: null,
    marks: null,
    bounds: null,
    availableSlots: [],
    counts: { floor: 0, marked: 0, found: null, scanned: null, offFloor: 0, dropped: 0 },
  };
}

/**
 * One axis panel, resolved.
 *
 * The order of the gates is the order of the honesty: no frame -> nothing; no
 * reference -> nothing; both -> the REAL wafer, with the defect overlay if it
 * came and a stated gap if it did not.
 */
export function axisPanel(axis, floors) {
  if (!axis) return refuse(axis, 'no_axes');

  const state = strOrEmpty(axis.state);
  const reason = strOrEmpty(axis.reason);
  const cellSet = toCells(axis.cells);

  // 🔴 THE SERVER'S REFUSAL IS RENDERED AS THE SERVER WROTE IT, in its own place.
  // An axis it cannot reach keeps its heading and its row position — the core
  // axis reads 「연결 없음」 beside two drawn wafers instead of leaving a
  // two-axis row that quietly implies there were only ever two.
  if (state !== 'ready') {
    const panel = refuse(axis, MAP_REFUSAL[reason] ? reason : (state || 'unreachable'),
      strOrEmpty(axis.message));
    panel.unreachable = state === 'unreachable';
    // 🔴 THE SLOT LIST COMES OFF THE REFUSAL. `frame_ambiguous_across_slots`
    // answers WHICH slots exist, so the strip is read rather than assembled a
    // second time from a shape this client would have to guess.
    const fr = axis.frame || {};
    panel.availableSlots = listOf(fr.available_slots).map(strOrEmpty).filter(Boolean);
    // Cells can be served without a frame; they are counted, never drawn.
    panel.counts.marked = cellSet.cells.length;
    panel.counts.found = intOrNull(axis.found);
    panel.counts.scanned = intOrNull(axis.scanned);
    return panel;
  }

  // ── the frame: the REGISTERED declaration, read, never invented ──
  const fr = axis.frame || {};
  const meta = fr.grid && typeof fr.grid === 'object' ? fr.grid : null;
  if (!meta) return refuse(axis, 'no_registered_frame', strOrEmpty(fr.map_id));
  const declared = frameFromDeclaration(meta, { defaults: FRAME_DEFAULTS });
  const usable = isFrameUsable(declared);
  if (!usable.ok) return refuse(axis, 'frame_unusable', '사유 ' + usable.reasons.join(', '));
  const seatFrame = seatFrameOf(declared);

  // ── the floor: the valid-die mask, IF a resolver supplied one ──
  //
  // The wire announces `valid_die_ref: {relation, present}` — presence, not WHICH
  // map — so today this is null and the panel says so. See the header: the two key
  // spaces do not meet, and guessing one would draw a wafer nobody registered.
  const refKey = referenceKey(fr.valid_die_ref);
  const resolved = (floors && refKey && floors[refKey]) || null;
  const floorRaw = listOf(resolved && resolved.cells).length ? resolved.cells : null;
  let floorSeating = null;
  if (floorRaw) {
    const floorCells = toCells(floorRaw);
    try {
      floorSeating = computeSeating(floorCells.cells, seatFrame, null);
    } catch (err) {
      return refuse(axis, 'seating_failed', String((err && err.message) || err));
    }
    if (!floorSeating.boxKnown) return refuse(axis, 'origin_box_unknown', refKey);
  }

  // ── the overlay: defect chips in THIS axis's own coordinates ──
  let markSeating = null;
  if (cellSet.cells.length) {
    try {
      markSeating = computeSeating(cellSet.cells, seatFrame, null);
    } catch (err) {
      return refuse(axis, 'seating_failed', String((err && err.message) || err));
    }
  }

  // 🔴 WITH NO MASK THE EXTENT IS THE DECLARED GRID, NOT THE DEFECTS' OWN SPAN.
  // Fitting the picture to the defects would rescale it per row and make two rows
  // uncomparable — and would imply the wafer is exactly as big as its damage.
  const gridBounds = {
    minX: 0,
    minY: 0,
    maxX: Math.max(0, (declared.cols || 1) - 1),
    maxY: Math.max(0, (declared.rows || 1) - 1),
    empty: false,
  };
  let offFloor = 0;
  if (markSeating && floorSeating) {
    for (const seat of markSeating.seats) {
      if (!floorSeating.byKey.has(seat.x + ',' + seat.y)) offFloor += 1;
    }
  }

  return {
    axis: strOrEmpty(axis.axis),
    label: axisLabel(axis.axis, axis.label),
    hint: strOrEmpty(axis.sublabel) || axisHint(axis.axis),
    table: strOrEmpty(fr.table),
    basis: strOrEmpty(axis.coordinate_unit) || 'cells_from_origin',
    reference: refKey,
    mapId: strOrEmpty(fr.map_id),
    ok: true,
    // The mask gap is stated ON a panel that otherwise rendered.
    code: floorSeating ? (cellSet.cells.length ? null : 'no_cells') : 'mask_absent',
    why: floorSeating
      ? (cellSet.cells.length ? '' : MAP_REFUSAL.no_cells)
      : MAP_REFUSAL.mask_absent,
    detail: '',
    frame: declared,
    floor: floorSeating,
    marks: markSeating,
    bounds: floorSeating
      ? (markSeating ? unionBounds(floorSeating.bounds, markSeating.bounds) : floorSeating.bounds)
      : gridBounds,
    grid: { cols: declared.cols, rows: declared.rows },
    availableSlots: [],
    counts: {
      floor: floorSeating ? floorSeating.seatCount : 0,
      marked: markSeating ? markSeating.seatCount : 0,
      found: intOrNull(axis.found),
      scanned: intOrNull(axis.scanned),
      offFloor,
      dropped: cellSet.dropped,
    },
  };
}

export function lotAxisMaps(entry, floors) {
  const axes = listOf(entry && entry.projections);
  // 🔴 THE SLOT STRIP IS DERIVED FROM WHAT THE LOT ACTUALLY HAS, never from a
  // range this file makes up. A lot with 25 slots and a lot with 3 are both real
  // and the screen must not imply the second is missing 22.
  const panelsFirst = axes.map((a) => axisPanel(a, floors));
  // 🔴 THE SLOT LIST IS THE SERVER'S ANSWER TO `frame_ambiguous_across_slots`,
  // not a range this file makes up. A row spanning 25 slots and one spanning 3
  // are both real, and the screen must not imply the second is missing 22.
  const slotSet = [];
  for (const pf of panelsFirst) {
    for (const sl of listOf(pf.availableSlots)) {
      if (!slotSet.includes(sl)) slotSet.push(sl);
    }
  }
  const slots = slotSet.map((sl) => ({ slot: sl, cols: null, rows: null }));
  const base = {
    lot: strOrEmpty(entry && entry.lot),
    row: strOrEmpty(entry && entry.row),
    slot: strOrEmpty(entry && entry.slot),
    slots,
  };
  if (!axes.length) {
    return { ...base, ok: false, why: MAP_REFUSAL.no_axes, panels: [] };
  }
  const panels = panelsFirst;
  return {
    ...base,
    ok: panels.some((p) => p.ok),
    // 🔴 A ROW WHERE EVERY AXIS REFUSED IS STILL A ROW WITH THREE HEADINGS. The
    // reader has to be able to see WHICH axis is missing, and that is only
    // legible when the axes that failed keep their places.
    why: '',
    panels,
  };
}

/**
 * The map section for the whole marked set.
 *
 * `maps` is `{lot: <axis payload>}`, filled in by the loader as answers arrive,
 * so a slow axis fetch shows as 「불러오는 중」 on that lot alone rather than
 * blanking the section.
 */
export function mapSection(model, maps, floors) {
  const marked = listOf(model && model.marked);
  return {
    marked: marked.length,
    // 🔴 KEYED ON `row`, NOT ON THE LOT NAME — `/api/ledger/lot_map` takes the
    // bonding row id, and one lot carries many of them.
    lots: marked.map((r) => {
      // The cache key carries the slot for the reason `loadAxisMap` records:
      // `row` alone would show one slot's wafer under another slot's heading.
      const slot = strOrEmpty(model && model.question && model.question.slot);
      const entry = (maps && (maps[`${r.row}|${slot}`] || maps[r.row])) || null;
      if (!entry) {
        return {
          lot: r.lot, row: r.row, ok: false, pending: true,
          why: '축 맵 불러오는 중…', panels: [], slots: [], slot: '',
        };
      }
      return {
        ...lotAxisMaps({ ...entry, lot: r.lot, row: r.row }, floors),
        pending: false,
      };
    }),
  };
}
