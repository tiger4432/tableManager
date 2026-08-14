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
// 🔴 PROPOSED SHAPE — NOT YET SERVED.
//
//   GET /api/ledger/lot_map?row=<row>&slot=<slot>&kind=<kind>&by=<axis>
//     -> { row, lot, slot, kind, generated_at,
//          slots: [ {slot, cols, rows} ],     // 🔴 이 랏이 «실제로» 가진 슬롯들
//          axes: [
//            { axis: "bond" | "dt" | "core",
//              label: "본딩축",
//              table: "bonding_log",          // whose coordinates these are
//              basis: "transferred",          // how the projection was obtained
//              reference: { table: "valid_die_ref", map_id: "PRD-A_BASE" },
//              frame: { <grid_metadata object> } | null,
//              floor: [ {x, y} ] | null,      // null -> resolve via `reference`
//              cells: [ {x, y, n} ] | null,   // null -> 좌표 미배포, NOT zero defects
//              state: "ready" | "absent" | "unreachable",
//              reason: "no_live_bridge" | "<token>" } ] }
//
// 🔴 ONE LOT IS NOT ONE MAP. Measured by the server lane (2026-08-14): the
// bonding map is keyed on `(bond_lot, bond_slot)` — 25 slots per lot, each with
// its OWN grid (11×11, 12×12, 12×13, 13×13…). `slot` is therefore part of the
// question, not a detail: overlaying 25 slots into one picture would draw a
// wafer that does not exist anywhere. The frames are real — 2,500 of them
// registered in `wafer_map_metadata` — which is exactly why there is no excuse
// for a drawn circle.
//
// 🔴 AND THE CORE AXIS IS UNREACHABLE TODAY, MEASURED, NOT ASSUMED:
// `bonding_log.core_lot/core_slot/cx/cy` are NULL across all 357,796 rows and
// `dt_map.core_lot` across all 5,619 — zero matches. Reviving it needs a new side
// join, which ruling R-2026-08-14-D forbids. The server answers
// `{"axis":"core","state":"unreachable","reason":"no_live_bridge"}` and THIS
// SCREEN SAYS SO IN THE CORE AXIS'S OWN PLACE. It is not hidden and the slot is
// not collapsed to two — an absence the reader cannot see is an absence they
// will assume away, which is the structure view's 「선언만 있는 축」 rule.
//
// `floor`/`frame` may be omitted, in which case the loader resolves them from
// the two routes that ARE deployed today (`/tables/wafer_map_metadata/data` and
// `/tables/valid_die_ref/data`) and hands them in through `floors`.
//
// CHANGING WHAT THIS CONSUMES IS AN ESCALATION, NOT AN EDIT.
// ============================================================

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
  no_axes: '축 선언 없음 — 서버가 축을 실어오지 않았습니다',
  // 🔴 MEASURED, NOT MISSING. The bridge columns are NULL across every row, so
  // there is no join to make — and making one is forbidden by R-2026-08-14-D.
  // This sentence stands in the core axis's own place; it is content.
  unreachable: '연결 없음 — 이 축을 이을 살아있는 다리가 없습니다',
  no_live_bridge: '연결 없음 — 브릿지 컬럼이 전 행 NULL입니다 (0이 아니라 부재)',
  no_slot: '이 슬롯의 맵이 없습니다',
  frame_undeclared: '프레임 미등록 — wafer_map_metadata에 이 축의 선언이 없습니다',
  frame_unusable: '프레임 선언이 좌표를 세우기에 부족합니다',
  reference_absent: 'valid die 레퍼런스 없음 — 그릴 웨이퍼가 없습니다',
  reference_empty: 'valid die 레퍼런스에 칸이 0개입니다',
  origin_box_unknown: '오리진 박스 미상 — 물리 규격(phys_*) 선언이 없습니다',
  cells_unreported: '불량 좌표 미배포 — 바닥만 실물입니다',
  seating_failed: '좌석 계산 실패',
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
  const table = strOrEmpty(ref.table);
  const mapId = strOrEmpty(ref.map_id !== undefined ? ref.map_id : ref.mapId);
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
    counts: { floor: 0, marked: 0, offFloor: 0, dropped: 0 },
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

  // 🔴 THE FIRST GATE, AND IT IS A STATEMENT RATHER THAN AN ERROR. An axis the
  // server declares `unreachable` keeps its heading, its place in the row and its
  // reason — the core axis reads 「연결 없음」 beside two drawn wafers instead of
  // leaving a two-axis row that quietly implies there were only ever two.
  const state = strOrEmpty(axis.state);
  if (state === 'unreachable') {
    const reason = strOrEmpty(axis.reason);
    const panel = refuse(axis, MAP_REFUSAL[reason] ? reason : 'unreachable',
      reason && !MAP_REFUSAL[reason] ? `사유 ${reason}` : '');
    panel.unreachable = true;
    return panel;
  }

  const ref = axis.reference || null;
  const key = referenceKey(ref);
  const resolved = (floors && key && floors[key]) || null;

  // ── the frame: registered declaration only ──
  const meta = (axis.frame && typeof axis.frame === 'object')
    ? axis.frame
    : (resolved && resolved.frame) || null;
  if (!meta) {
    return refuse(axis, 'frame_undeclared',
      key ? `참조: ${key}` : '참조 선언도 없습니다');
  }
  const frame = frameFromDeclaration(meta, { defaults: FRAME_DEFAULTS });
  const usable = isFrameUsable(frame);
  if (!usable.ok) {
    return refuse(axis, 'frame_unusable', `사유 ${usable.reasons.join(', ')}`);
  }
  const seatFrame = seatFrameOf(frame);

  // ── the floor: valid_die_ref rows, presence IS the mask ──
  const floorRaw = listOf(axis.floor).length
    ? axis.floor
    : ((resolved && resolved.cells) || null);
  if (floorRaw === null) return refuse(axis, 'reference_absent', key ? `참조: ${key}` : '');
  const floorCells = toCells(floorRaw);
  if (!floorCells.cells.length) return refuse(axis, 'reference_empty', key ? `참조: ${key}` : '');

  let floorSeating;
  try {
    floorSeating = computeSeating(floorCells.cells, seatFrame, null);
  } catch (err) {
    return refuse(axis, 'seating_failed', String((err && err.message) || err));
  }
  // 🔴 `boxKnown === false` MEANS THE ORIGIN BOX WAS NOT DERIVABLE — the physical
  // spec is absent, so `boundingBoxOf` returned null and the seater fell back to
  // an identity box. That is a designed refusal, and drawing on top of it would
  // put every cell at the wrong offset. Not a warning: a stop.
  if (!floorSeating.boxKnown) return refuse(axis, 'origin_box_unknown', key ? `참조: ${key}` : '');

  // ── the overlay: defect chips in THIS axis's coordinates ──
  const hasCells = listOf(axis.cells).length > 0 || Array.isArray(axis.cells);
  const markCells = hasCells ? toCells(axis.cells) : { cells: [], dropped: 0 };
  let markSeating = null;
  if (hasCells && markCells.cells.length) {
    try {
      markSeating = computeSeating(markCells.cells, seatFrame, null);
    } catch (err) {
      return refuse(axis, 'seating_failed', String((err && err.message) || err));
    }
  }

  // A defect seated where the reference has no die is a FINDING about the data,
  // not a pixel to hide: it means the two maps disagree about which dies exist.
  let offFloor = 0;
  if (markSeating) {
    for (const seat of markSeating.seats) {
      if (!floorSeating.byKey.has(`${seat.x},${seat.y}`)) offFloor += 1;
    }
  }

  return {
    axis: strOrEmpty(axis.axis),
    label: axisLabel(axis.axis, axis.label),
    hint: axisHint(axis.axis),
    table: strOrEmpty(axis.table),
    basis: strOrEmpty(axis.basis),
    reference: key,
    ok: true,
    // 🔴 THE FLOOR IS REAL AND THE OVERLAY MAY NOT BE. Said in the panel rather
    // than left for the reader to infer from an empty wafer.
    code: hasCells ? null : 'cells_unreported',
    why: hasCells ? '' : MAP_REFUSAL.cells_unreported,
    detail: '',
    frame,
    floor: floorSeating,
    marks: markSeating,
    bounds: markSeating
      ? unionBounds(floorSeating.bounds, markSeating.bounds)
      : floorSeating.bounds,
    counts: {
      floor: floorSeating.seatCount,
      marked: markSeating ? markSeating.seatCount : 0,
      offFloor,
      dropped: floorCells.dropped + markCells.dropped,
    },
  };
}

/**
 * The three axes for one marked lot.
 *
 * A lot with no axis payload at all comes back as ONE refusal rather than three
 * identical ones — the reader learns nothing from the same sentence written
 * three times.
 */
export function lotAxisMaps(entry, floors) {
  const axes = listOf(entry && entry.axes);
  // 🔴 THE SLOT STRIP IS DERIVED FROM WHAT THE LOT ACTUALLY HAS, never from a
  // range this file makes up. A lot with 25 slots and a lot with 3 are both real
  // and the screen must not imply the second is missing 22.
  const slots = listOf(entry && entry.slots).map((s) => ({
    slot: strOrEmpty(s && s.slot !== undefined ? s.slot : s),
    cols: intOrNull(s && s.cols),
    rows: intOrNull(s && s.rows),
  })).filter((s) => s.slot !== '');
  const base = {
    lot: strOrEmpty(entry && entry.lot),
    row: strOrEmpty(entry && entry.row),
    slot: strOrEmpty(entry && entry.slot),
    slots,
  };
  if (!axes.length) {
    return { ...base, ok: false, why: MAP_REFUSAL.no_axes, panels: [] };
  }
  const panels = axes.map((a) => axisPanel(a, floors));
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
