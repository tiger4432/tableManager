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
// 🔴 THE MISSING LEG LANDED (2026-08-14). `valid_die_ref` used to be announced as
// `{relation, present}` — presence, not WHICH map — so no key was resolvable and every
// panel said 「유효 다이 마스크 미적용」. The frame now carries `valid_die_ref.map_id`
// and the mask resolves through the key `surprise_axis.js::resolveFloors` deposits,
// `"<relation>|<map_id>"`, which is the same key `referenceKey` below builds.
//
// MEASURED against the restarted server, `SYN-VOID-001` slot 07:
//   frame.valid_die_ref  {"relation":"valid_die_ref","present":true,"map_id":"SYN-VD_G15X15"}
//   resolved floor       141 seats · defect chips 13 · off-floor 0
//   extent               the MASK's bounds (0..13), no longer the declared grid (0..14)
//
// ⚠️ AND `mask_absent` IS NOW UNREACHABLE ON LIVE DATA — SAY IT RATHER THAN IMPLY IT.
// Reaching it needs a frame that is USABLE and has NO resolvable reference, and measured
// on this box that combination does not occur: every `ready` frame carries a `map_id`
// (bond `SYN-VD_G15X15`, dt `SYN-VD_G15X10`, core `SYN-VD_G23X23`), and the 120
// `BS-2601-*` frames that carry no reference never get that far — `isFrameUsable` refuses
// them first, so their panel reads `frame_unusable`, NOT 「마스크 미적용」.
//
// It is kept because the population is one registration away from existing again, and
// because the harness fixture exercises exactly that shape. But nobody should go looking
// for 「마스크 미적용」 on screen today, and a note claiming the 120 show it would be
// wrong — an earlier draft of this block claimed precisely that.
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
  // 🔴 THE SENTENCE NO LONGER ASKS FOR A SLOT. The refusal is still the server's and
  // still FACTUAL — several frames matched and they cannot share one canvas — but the
  // remedy changed: the strip below renders each matched frame as its own map. Asking
  // the reader to pick was never sufficient anyway (MEASURED: `slot=01` resolves the
  // bonding axis and leaves DT and core ambiguous on the very same response).
  frame_ambiguous_across_slots: '이 행이 프레임 여러 개에 걸쳐 있습니다 — 아래에 한 장씩 폅니다',
  unreachable: '연결 없음 — 이 축을 이을 살아있는 다리가 없습니다',
  frame_unusable: '프레임 선언이 좌표를 세우기에 부족합니다',
  origin_box_unknown: '오리진 박스 미상 — 물리 규격(phys_*) 선언이 없습니다',
  no_cells: '이 행에 이 축의 불량 칩이 없습니다',
  seating_failed: '좌석 계산 실패',
  mask_absent: '유효 다이 마스크 미적용 — 등록 격자 위에 불량 칩만 그립니다',
  // 🔴 THE ONE CASE THE STRIP CANNOT HONESTLY OPEN, AND IT SAYS SO RATHER THAN
  // PICKING. When the matched frames span more than one lot, the wire hands over
  // `available_lots` and `available_slots` as two SEPARATE lists — which pairs of
  // them actually occur is not on the wire. Enumerating the cartesian product would
  // invent frames nobody registered; enumerating one lot's would drop the rest.
  frames_span_lots: '이 축의 프레임이 랏 여러 개에 걸쳐 있습니다 — 어느 조합이 실재하는지 응답에 없어 한 장씩 펴지 못합니다',
  // The row cannot be narrowed at all: no projection's frames are keyed on the axis
  // this row was read under, so no `slot` value addresses one of them.
  frames_not_addressable: '이 행은 슬롯으로 좁혀지지 않습니다 — 프레임 키가 이 행의 축에 속하지 않습니다',
};

//: 🔴 HOW MANY FRAMES ARE ASKED FOR PER PAINT PASS. MEASURED on this box: a marked
//: lot matches 25 frames (107 of 108 lots; the 108th matches 20), so «fetch them all»
//: is 25 round trips per marked lot fired at once — six marked lots would be 150.
//: The loader repaints as each answer lands, and each repaint asks for the next
//: batch, so the strip fills itself progressively with NO control for the reader to
//: press. Scrolling is the only gesture, which is what the owner asked for.
//: 🔴 AND ABOVE THIS MANY MARKED LOTS THE MAPS ARE NOT THE ANSWER. MEASURED: a marked lot
//: matches 25 frames, so five marked lots is 125 maps — a page that ran to 12,283px, which
//: is the strip obeying its instruction and being wrong one level up. What the reader asked
//: by marking five lots is 「이것들이 서로 어떻게 다른가」, and that question is the contrast
//: panel's; the maps answer 「이 웨이퍼는 어떻게 생겼나」, which is a question about ONE.
//:
//: ⚠️ THIS IS ARRANGEMENT, NOT CONCEALMENT, AND THE DIFFERENCE IS A STATED COUNT.
//: `SCENARIO_CONSOLE_BRIEF` P0 item 6: 「접힌/잘린 내용은 「아래 N건」류 존재 표시 필수 —
//: 스크롤을 줄이는 건 배치이지 은닉이 아니다」. So the summary prints the REAL number of
//: frames it is not drawing. A strip that quietly drew the first few would be the fake
//: attenuation this project already has a ruling against.
export const FRAME_STRIP = Object.freeze({ batch: 8, maxLotsForMaps: 1 });

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

/**
 * 🔴 THE REGISTERED DECLARATION ARRIVES AS TEXT, AND REJECTING IT MEANT NO MAP EVER DREW.
 *
 * MEASURED on the live route: `wafer_map_metadata.grid_metadata` is `character varying`,
 * not `json`, so the frame's grid comes over the wire as a JSON STRING. This gate used to
 * read `typeof grid === 'object'`, which is false for every live response — so every
 * `ready` projection fell through to `no_registered_frame` and this screen has never
 * painted a wafer on real data. It was invisible because the harness fixture writes the
 * grid as an object literal, and a fixture that cannot express the wire's own type cannot
 * fail on it.
 *
 * Parsing is still a GATE, not a coercion: text that is not an object is refused exactly
 * as before. Nothing is defaulted into existence, and no shape is invented — the
 * declaration is read, or it is missing and says so.
 */
export function gridMetaOf(grid) {
  if (grid && typeof grid === 'object' && !Array.isArray(grid)) return grid;
  if (typeof grid !== 'string' || !grid.trim()) return null;
  let parsed;
  try { parsed = JSON.parse(grid); } catch (err) { return null; }
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null;
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
    // 🔴 A REFUSED PANEL STILL KNOWS WHOSE WAFER IT IS, and that is not a contradiction:
    // the refusal is about which FRAMES pair, not about who the wafer is. It matters in
    // the case where every panel of an entry refused — a registered frame key with no
    // registered grid — because then the refusals are the only place the name can come
    // from, and without this the entry falls back to the frame key while the wire was
    // carrying the wafer id all along.
    wafer: '',
    // 🔴 AND THE FRAME KEY SURVIVES A REFUSAL FOR THE SAME REASON. Found by the same
    // assertion that found the `wafer` gap, one layer along: a refused panel dropped
    // `mapId` too, so an entry whose every axis refused fell all the way back to a bare
    // slot number — 「01」 — when the server had declared `BS-2601-001_01` on the very
    // frame it was refusing. MEASURED: this is not a corner case. 120 of the 3,895
    // registered bonding frames are refused by `isFrameUsable`, and they are exactly the
    // 5 lots that carry no base identity — so on those lots EVERY entry took this path.
    //
    // ⚠️ AND THE REFUSAL IS ABOUT PROVENANCE, NOT GEOMETRY. An earlier version of this
    // note blamed `phys_chip_x: 1`, which is WRONG and would send the next reader to
    // check the die pitch — `isFrameUsable` never inspects the pitch at all. It requires
    // `cols`/`rows` to carry `source === DECLARED`, and on these frames the source is
    // `auto_registered`: the REGISTRAR wrote those dimensions, nobody declared them.
    // Measured reason tokens: `["cols:auto_registered", "rows:auto_registered"]`.
    mapId: '',
    availableSlots: [],
    availableLots: [],
    counts: { floor: 0, marked: 0, found: null, scanned: null, offFloor: 0, dropped: 0 },
  };
}

/**
 * The frames this refused projection matched, counted along BOTH keys separately.
 *
 * 🔴 SLOTS × LOTS IS NOT THE ANSWER AND MUST NOT BE MULTIPLIED. The wire says which
 * slots occur and which lots occur; it does not say which PAIRS occur. MEASURED on
 * this box: one row's core axis answers 25 slots and 2 lots, and the real number of
 * core frames per bonded wafer is 25–30 — never the product, 50. So the two counts
 * are reported side by side and the screen prints both rather than a total it would
 * be making up.
 */
export function frameSpanOf(panel) {
  const slots = listOf(panel && panel.availableSlots).length;
  const lots = listOf(panel && panel.availableLots).length;
  return { slots, lots, enumerable: lots === 1 && slots > 0 };
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
    // 🔴 AND THE LOT LIST WITH IT. The frame key is `{lot}_{slot}` — reading only the
    // slots and calling that «the frames» is the same flattening the server refused,
    // one layer up: MEASURED, a core axis answers 2 lots × 25 slots, and a strip built
    // from the slots alone would put two wafers' frames under one heading.
    panel.availableLots = listOf(fr.available_lots).map(strOrEmpty).filter(Boolean);
    // The server sets `wafer` on the REFUSED frame too, when the rows it refused over
    // still counted to exactly one bonded base wafer. Absent stays absent — the field is
    // omitted, never `null`, so an empty string here means «not served», not «unnamed».
    panel.wafer = strOrEmpty(fr.wafer);
    panel.mapId = strOrEmpty(fr.map_id);
    // The STORED cells ride along on the panel. The aggregate sheet overlays these raw
    // (see `overlayOf`) and must never reach for the seated copy.
    panel.cells = cellSet.cells;
    // Cells can be served without a frame; they are counted, never drawn.
    panel.counts.marked = cellSet.cells.length;
    panel.counts.found = intOrNull(axis.found);
    panel.counts.scanned = intOrNull(axis.scanned);
    return panel;
  }

  // ── the frame: the REGISTERED declaration, read, never invented ──
  const fr = axis.frame || {};
  // Every refusal from here down is about a frame the server NAMED, so each one carries
  // that name and its wafer out with it. Refusing to draw is not a reason to forget who
  // was refused — the entry still has to say which frame it is standing for.
  const named = (code, detail) => {
    const panel = refuse(axis, code, detail);
    panel.mapId = strOrEmpty(fr.map_id);
    panel.wafer = strOrEmpty(fr.wafer);
    return panel;
  };
  const meta = gridMetaOf(fr.grid);
  if (!meta) return named('no_registered_frame', strOrEmpty(fr.map_id));
  const declared = frameFromDeclaration(meta, { defaults: FRAME_DEFAULTS });
  const usable = isFrameUsable(declared);
  if (!usable.ok) return named('frame_unusable', '사유 ' + usable.reasons.join(', '));
  const seatFrame = seatFrameOf(declared);

  // ── the floor: the valid-die mask, IF a resolver supplied one ──
  //
  // The frame now names WHICH map (`valid_die_ref.map_id`), so this resolves wherever a
  // reference was registered and stays null where none was — see the header. Both
  // outcomes are live: SYN frames seat a 141-cell mask, the 120 `BS-2601-*` frames get
  // no key and keep the mask-absent sentence, and neither case is guessed.
  const refKey = referenceKey(fr.valid_die_ref);
  const resolved = (floors && refKey && floors[refKey]) || null;
  const floorRaw = listOf(resolved && resolved.cells).length ? resolved.cells : null;
  let floorSeating = null;
  if (floorRaw) {
    const floorCells = toCells(floorRaw);
    try {
      floorSeating = computeSeating(floorCells.cells, seatFrame, null);
    } catch (err) {
      return named('seating_failed', String((err && err.message) || err));
    }
    if (!floorSeating.boxKnown) return named('origin_box_unknown', refKey);
  }

  // ── the overlay: defect chips in THIS axis's own coordinates ──
  let markSeating = null;
  if (cellSet.cells.length) {
    try {
      markSeating = computeSeating(cellSet.cells, seatFrame, null);
    } catch (err) {
      return named('seating_failed', String((err && err.message) || err));
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
    // 🔴 THE CARRY-THROUGH. `waferLabelOf` reads `panel.wafer`, and panels are built HERE
    // from an explicit field list — so a field the wire carries but this list omits is
    // dropped one layer before any reader can see it. A consumer that reads a field is
    // not the same thing as a field that arrives.
    wafer: strOrEmpty(fr.wafer),
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
    cells: cellSet.cells,
    availableSlots: [],
    availableLots: [],
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
  const panels = axes.map((a) => axisPanel(a, floors));
  const base = {
    lot: strOrEmpty(entry && entry.lot),
    row: strOrEmpty(entry && entry.row),
    slot: strOrEmpty(entry && entry.slot),
  };
  if (!axes.length) {
    return { ...base, ok: false, why: MAP_REFUSAL.no_axes, panels: [] };
  }
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
 * 🔴 WHICH PROJECTION'S FRAMES THIS ROW CAN BE OPENED ONE BY ONE — DERIVED, NOT NAMED.
 *
 * The route narrows rows with `slot`, and the server applies it to the ROW AXIS's own
 * slot column and to nothing else (`_slot_column_for`). So the projection a `slot`
 * can resolve is the one whose frames are keyed on the very column the row was looked
 * up by — and the wire already says which one that is, without naming a column:
 * `available_lots` is the distinct set of that projection's lot key among rows the
 * WHERE clause matched, so it is EXACTLY `[row]` when the projection's lot column IS
 * the row axis's column, and something else otherwise.
 *
 * MEASURED, `row=SYN-VOID-001` under `by=bond_lot`:
 *   bond  available_lots ["SYN-VOID-001"]              <- equals the row: addressable
 *   dt    available_lots ["SYN-DT-001"]                <- a different lot space
 *   core  available_lots ["SYN-CL-001","SYN-CL-002"]   <- two, and unpairable
 * and under `by=dt_lot` the same test moves to the DT projection with no code change.
 *
 * That is the whole point: NO TABLE OR COLUMN NAME IS TYPED IN THIS FILE. A deployment
 * that declares different relations and different axes swaps its declarations and this
 * test follows them, because it compares two values the response itself carries.
 */
export function addressableProjection(entry) {
  const row = strOrEmpty(entry && entry.row);
  if (!row) return null;
  for (const p of listOf(entry && entry.projections)) {
    const fr = (p && p.frame) || {};
    const lots = listOf(fr.available_lots).map(strOrEmpty).filter(Boolean);
    const slots = listOf(fr.available_slots).map(strOrEmpty).filter(Boolean);
    if (lots.length === 1 && lots[0] === row && slots.length) {
      return { axis: strOrEmpty(p.axis), label: axisLabel(p.axis, p.label), slots, lot: lots[0] };
    }
  }
  return null;
}

/**
 * The strip for ONE marked row: which frames to open, or why they cannot be opened.
 *
 * 🔴 ONE FRAME IS ONE BONDED BASE WAFER, AND THAT IS MEASURED, NOT ASSUMED. On this
 * box `bonding_log.base_id` and the bonding frame key `(lot, slot)` are a BIJECTION —
 * 2,575 base wafers, 2,575 frames, 1:1 in both directions, no base wafer touching two
 * frames and no frame carrying two base wafers. So listing the addressable
 * projection's frames IS listing the lot's bonded base wafers; the wafer axis is not a
 * second mechanism bolted beside the multi-render, it is the same list read correctly.
 *
 * ⚠️ WHAT THAT BIJECTION DOES NOT BUY. It holds for the BONDING axis only. The same
 * measurement says one base wafer's dies arrive from 25 DT frames and from 25–30 core
 * frames, so 「웨이퍼 한 장 = 프레임 한 장」 is true of the wafer's OWN coordinate
 * system and false of the others. Those axes therefore stay refused INSIDE each
 * wafer's entry, with their frame counts printed — a fact about how the product is
 * built, not a gap in this screen.
 */
export function stripPlan(entry) {
  const row = strOrEmpty(entry && entry.row);
  const projections = listOf(entry && entry.projections);
  if (!projections.length) return { row, kind: 'no_axes', axis: '', slots: [], why: MAP_REFUSAL.no_axes };

  // 🔴 A ROW THAT ALREADY RESOLVES IS NOT AMBIGUOUS AND MUST NOT BE RE-FETCHED. When
  // the served answer already drew a frame, that answer IS the single entry — asking
  // for it again under a slot it never carried would be this file inventing a key.
  if (projections.some((p) => strOrEmpty(p.state) === 'ready')) {
    return { row, kind: 'single', axis: '', slots: [strOrEmpty(entry.slot)], why: '' };
  }

  const addr = addressableProjection(entry);
  if (addr) return { row, kind: 'strip', axis: addr.axis, label: addr.label, slots: addr.slots, why: '' };

  // Nothing addressable. Say WHICH of the two situations happened — 「랏이 여럿이라
  // 짝을 모른다」 and 「이 행에는 좁힐 슬롯 자체가 없다」 are different facts and a
  // reader deciding whether to re-ask under another axis needs to tell them apart.
  const spanning = projections.some((p) => listOf(p.frame && p.frame.available_lots).length > 1);
  return {
    row, kind: 'blocked', axis: '', slots: [],
    code: spanning ? 'frames_span_lots' : 'frames_not_addressable',
    why: spanning ? MAP_REFUSAL.frames_span_lots : MAP_REFUSAL.frames_not_addressable,
  };
}

/**
 * 🔴 WHAT THIS ENTRY IS CALLED — AND WHERE THE NAME CAME FROM, RECORDED.
 *
 * The owner asked for the strip to be labelled by base WF id. The route does not serve
 * one: `frame` carries `map_id` (`{lot}_{slot}`) and the response has no field naming
 * the bonded base wafer. Since the two are a measured bijection the ENTRY is right
 * either way, but the LABEL would be an invention, so this returns the frame key the
 * server did declare and marks the source. The day a `wafer` field lands on the frame
 * the label upgrades with no edit here, and until then nothing on screen claims to be
 * a wafer id that isn't one.
 */
export function waferLabelOf(panels, slot) {
  // 🔴 AGREEMENT, NOT THE FIRST ONE FOUND. Each projection derives its wafer over its OWN
  // surviving rows — the subsets differ, because a projection only keeps rows where its
  // coordinates are non-null. So «the first panel carrying a wafer» is a SAMPLE, and
  // sampling an identity is the exact move the server refuses one layer down when it
  // counts `wafers_seen` instead of taking `next(iter(...))` of an unchecked set.
  // On this corpus the panels always agree; a corpus where they did not would otherwise
  // label the entry with whichever axis happened to be listed first.
  const named = [];
  for (const p of listOf(panels)) {
    const w = strOrEmpty(p && p.wafer);
    if (w && !named.includes(w)) named.push(w);
  }
  if (named.length === 1) return { text: named[0], source: 'served' };
  // Disagreement is not a tiebreak — it means this entry is not one wafer, so it does
  // not get a wafer's name. Fall through to the key the frame actually declared.
  for (const p of listOf(panels)) {
    const m = strOrEmpty(p && p.mapId);
    if (m) return { text: m, source: named.length > 1 ? 'frame_key_disputed' : 'frame_key' };
  }
  return { text: strOrEmpty(slot), source: 'slot' };
}

/**
 * The map section for the whole marked set.
 *
 * `maps` is `{`${row}|${slot}`: <lot_map body>}`, filled in by the loader as answers
 * arrive. Returns the render model AND `wanted` — the next few `{row, slot}` the
 * loader should ask for. The budget is what keeps the strip from firing 25 requests
 * per marked lot in one burst; each answer repaints, and each repaint asks for the
 * next batch, so no control exists for the reader to press.
 */
/**
 * 🔴 THE FAN-IN OF ONE WAFER — NAMED, COUNTED, AND NOT MULTIPLIED.
 *
 * A focused wafer's dies did not all come from one place: MEASURED, one bonded base wafer
 * receives from 25 DT frames and 25–30 core frames. The temptation in a focus view is to
 * render 「이 웨이퍼의 소스」 as a grid of source frames, which means pairing the lot list
 * with the slot list — and the wire says which lots occur and which slots occur, never
 * which PAIRS. So each source axis reports its lots BY NAME and its slot count as a
 * separate number, and pairs are only claimed when there is exactly one lot to pair with.
 *
 * ⚠️ AND THE CELLS CANNOT BE SPLIT PER SOURCE FRAME. The refused projection serves this
 * wafer's chips in that axis's coordinates, but with no per-chip frame attribution — so
 * 「이 칩은 이 테이프에서 왔다」 is not answerable from this response and is not drawn.
 */
export function fanInOf(panel) {
  const span = frameSpanOf(panel);
  const lots = listOf(panel && panel.availableLots);
  return {
    axis: strOrEmpty(panel && panel.axis),
    label: strOrEmpty(panel && panel.label),
    lots,
    slots: span.slots,
    // Pairs are determined only when one lot owns every slot. With two, the real pairing
    // is not on the wire and the product would be frames nobody registered.
    pairable: span.enumerable,
    chips: (panel && panel.counts && panel.counts.marked) || 0,
    why: strOrEmpty(panel && panel.why),
    unreachable: !!(panel && panel.unreachable),
  };
}

/**
 * 🔴 WHICH STORED COORDINATE RUNS ALONG EACH DRAWN EDGE — DERIVED FROM THE SEATS, NEVER
 * ASSUMED FROM THE FRAME.
 *
 * The owner asked for X across the top and Y down the left, as CELL COUNTS FROM THE ORIGIN
 * (never millimetres — pitch does not place a cell, and multiplying by it manufactures a
 * precision the stored value does not have). The trap is that the drawn image is SEAT
 * space, not stored space: `computeSeating` puts each cell through the frame's rotation and
 * side, so under `rotation: 90` a drawn COLUMN holds a constant stored **y**, not x.
 * Labelling that column with a stored x would be a caption that is wrong while the picture
 * is right — this domain's signature defect.
 *
 * MEASURED, and it is not hypothetical: `SYN-VOID-001`'s 25 bonding frames span all eight
 * rotation x side combinations, so on that one lot both cases are on screen at once.
 *
 * So nothing is assumed. Each seat carries the `cell` it came from, and this reads them:
 * if every drawn column holds exactly one stored x, columns track x; if instead every
 * column holds exactly one stored y, they track y. If NEITHER holds, the mapping is not a
 * column-preserving one and this returns `null` so the caller draws the grid with NO
 * numbers rather than numbers it cannot stand behind.
 */
export function storedAxisTracks(panel) {
  const seatings = [panel && panel.floor, panel && panel.marks].filter(Boolean);
  const byCol = new Map();
  const byRow = new Map();
  let seen = 0;
  for (const seating of seatings) {
    for (const seat of listOf(seating.seats)) {
      const cell = seat && seat.cell;
      if (!cell) continue;
      const cx = intOrNull(cell.x);
      const cy = intOrNull(cell.y);
      if (cx === null || cy === null) continue;
      seen += 1;
      if (!byCol.has(seat.x)) byCol.set(seat.x, { xs: new Set(), ys: new Set() });
      if (!byRow.has(seat.y)) byRow.set(seat.y, { xs: new Set(), ys: new Set() });
      byCol.get(seat.x).xs.add(cx); byCol.get(seat.x).ys.add(cy);
      byRow.get(seat.y).xs.add(cx); byRow.get(seat.y).ys.add(cy);
    }
  }
  if (!seen) return null;
  const settle = (group) => {
    const constX = [...group.values()].every((v) => v.xs.size === 1);
    const constY = [...group.values()].every((v) => v.ys.size === 1);
    // Both constant means one line of cells — no axis is determined, so claim neither.
    if (constX === constY) return null;
    const which = constX ? 'x' : 'y';
    const at = new Map();
    for (const [seatPos, v] of group) at.set(seatPos, [...(constX ? v.xs : v.ys)][0]);
    return { axis: which, at };
  };
  const top = settle(byCol);
  const left = settle(byRow);
  if (!top || !left) return null;
  return { top, left };
}

//: 🔴 CAPS ARE COUNTED IN WAFERS, NEVER IN LOTS. The retired gate counted lots, which is the
//: unit substitution the owner ruled on: 「그냥 랏이란 단위를 잊으라 그래」. Aggregate sheets
//: are unbounded — overlaying more wafers makes the pattern SHARPER, so capping them would
//: throw away the only thing that shows it.
export const MAP_CAPS = Object.freeze({
  detailWafers: 10,
  //: 🔴 THE SMALL-N THRESHOLD. Four separate pictures are readable side by side and an
  //: overlay of four says almost nothing — the heat has four levels and no lattice can
  //: show through. Above it the individual sheets stop being readable and the overlay is
  //: the only thing that carries the pattern (VMR 2.17 raw; see `overlayOf`). The reader
  //: can always cross with the 낱장/집계 toggle, so this is a DEFAULT, not a gate.
  individualMax: 4,
});

//: The sheet modes, and the auto rule. `` (empty) means «follow the count».
export const SHEET_EACH = "each";
export const SHEET_AGG = "agg";
export function sheetModeFor(asked, wafers) {
  const want = strOrEmpty(asked);
  if (want === SHEET_EACH || want === SHEET_AGG) return want;
  return wafers <= MAP_CAPS.individualMax ? SHEET_EACH : SHEET_AGG;
}

/**
 * 🔴 THE OVERLAY IS IN STORED COORDINATES, AND THAT IS A MEASURED CHOICE, NOT A STYLE ONE.
 *
 * `computeSeating` is NOT used here, and using it would silently destroy the answer. The
 * per-wafer maps seat their cells through the frame's rotation/side because a picture of ONE
 * wafer should look like that wafer. The aggregate asks a different question — 「같은 스테이지
 * 자리에서 반복되는가」 — and `bond_x`/`bond_y` are already stage coordinates, so seating them
 * rotates each wafer into its own frame and scatters a stage-fixed pattern.
 *
 * MEASURED, variance-to-mean ratio over the mask (Poisson = 1.0, higher = clustered):
 *
 *                              SYN-VOID-101      SYN-VOID-001
 *   raw stored coordinates       VMR 2.17          VMR 1.89
 *   seated (rotation applied)    VMR 1.20          VMR 1.23
 *
 * Seating drags it to noise both times. The pattern is a stage lattice — hot cells at x=4
 * and x=9, every 5 rows — which is a multi-site head signature, and it exists only in
 * stored space. This is why the aggregate must not reuse the per-wafer seating path.
 */
export function overlayOf(panels) {
  const heat = new Map();
  let chips = 0;
  for (const p of listOf(panels)) {
    for (const c of listOf(p && p.cells)) {
      const x = intOrNull(c.x); const y = intOrNull(c.y);
      if (x === null || y === null) continue;
      chips += 1;
      const k = `${x},${y}`;
      heat.set(k, (heat.get(k) || 0) + 1);
    }
  }
  let max = 0;
  for (const v of heat.values()) if (v > max) max = v;
  return { heat, chips, max, cells: heat.size };
}

/**
 * The map section for the MARKED POPULATION — and the population is exactly what was marked.
 *
 * 🔴 NO UNIT SUBSTITUTION. Marking is a WAFER. One marked wafer means that wafer's own
 * bonding frame plus that wafer's chips projected onto the other axes — never its lot's
 * other 24 frames. The previous version expanded a marked row into every slot of its lot,
 * which is how 「마킹이 1장인데 25장 얘기가 왜 나와」 happened. MEASURED: `by=wafer` resolves
 * the bonding frame directly (`row_axis.source = bonding_log.base_id`, bond `ready`,
 * `map_id SYN-VOID-101_07`), so no expansion is needed to draw a wafer at all.
 *
 * 🔴 THE DEFAULT IS ONE AGGREGATE SHEET PER COORDINATE SYSTEM, not a list of wafers. The
 * mechanism signatures ask about fixed-position clustering, tape stripes and edge rings, and
 * those live ONLY in the overlay — see `overlayOf` for the measurement. N separate sheets do
 * not show the pattern less well, they remove it.
 */
export function mapSection(model, maps, floors, options) {
  const marked = listOf(model && model.marked);
  const focusWafer = strOrEmpty(model && model.question && model.question.wafer);
  const askedMode = strOrEmpty(model && model.question && model.question.sheets);
  const budget = intOrNull(options && options.batch);
  let left = budget === null ? FRAME_STRIP.batch : budget;
  const wanted = [];
  const at = (row) => (maps && (maps[`${row}|`] || maps[row])) || null;

  // ── the population: one request per marked wafer, no slot ───────────────────────────
  const members = [];
  for (const r of marked) {
    const row = strOrEmpty(r.row);
    if (!row) continue;
    const body = at(row);
    if (!body) {
      if (left > 0) { left -= 1; wanted.push({ row, slot: '' }); }
      members.push({ row, label: r.lot || row, pending: true, panels: [] });
      continue;
    }
    const panels = listOf(body.projections).map((p) => axisPanel(p, floors));
    members.push({ row, label: r.lot || row, pending: false, panels, body });
  }

  const settled = members.filter((m) => !m.pending);
  const axes = [];
  for (const m of settled) {
    for (const p of m.panels) if (!axes.includes(p.axis)) axes.push(p.axis);
  }

  // ── one sheet per (axis, grid) ─────────────────────────────────────────────────────
  const sheets = [];
  for (const axis of axes) {
    const groups = new Map();
    const gridless = [];
    let unsettled = 0;
    for (const m of settled) {
      const p = m.panels.find((q) => q.axis === axis);
      if (!p) continue;
      if (!p.ok) {
        // No declared grid on this panel. Its chips are real and counted, but there is no
        // registered lattice to lay them on and this file does not invent one.
        gridless.push({ wafer: m.row, panel: p });
        continue;
      }
      // 🔴 「방향 미확정」 IS AN EXCLUSION, NOT A GUESS. A frame whose declaration does not
      // settle its own grid is dropped from the overlay and COUNTED, the same way the axis
      // labeller prints no numbers rather than numbers it cannot stand behind.
      if (!p.frame || !Number.isInteger(p.frame.cols) || !Number.isInteger(p.frame.rows)) {
        unsettled += 1; continue;
      }
      const key = `${p.frame.cols}x${p.frame.rows}|${strOrEmpty(p.table)}`;
      if (!groups.has(key)) {
        groups.set(key, { key, cols: p.frame.cols, rows: p.frame.rows, panels: [], wafers: [], orient: new Set() });
      }
      const g = groups.get(key);
      g.panels.push(p); g.wafers.push(m.row);
      g.orient.add(`${p.frame.rotation}/${p.frame.side}`);
    }
    for (const g of groups.values()) {
      const ov = overlayOf(g.panels);
      sheets.push({
        axis,
        label: axisLabel(axis, (g.panels[0] || {}).label),
        gridKey: g.key,
        cols: g.cols,
        rows: g.rows,
        wafers: g.wafers,
        // 🔴 THE ORIENTATION MIX IS REPORTED, NOT SILENTLY MERGED. See `overlayOf`: mixing
        // them is what SHOWS the stage pattern, because these are stage coordinates — but
        // the reader is told the mix exists rather than having to assume it away.
        orientations: [...g.orient],
        heat: ov.heat, chips: ov.chips, max: ov.max, cellCount: ov.cells,
        unsettled,
        ok: true,
      });
    }
    if (!groups.size && gridless.length) {
      const ov = overlayOf(gridless.map((x) => x.panel));
      const first = gridless[0].panel;
      sheets.push({
        axis, label: axisLabel(axis, first.label), ok: false,
        code: first.code || 'no_registered_frame',
        why: first.why,
        wafers: gridless.map((x) => x.wafer),
        chips: ov.chips, cellCount: ov.cells, max: ov.max,
        spans: frameSpanOf(first),
        unsettled,
      });
    }
  }

  const focus = focusWafer ? settled.find((m) => m.row === focusWafer) : null;
  const mode = sheetModeFor(askedMode, members.length);
  return {
    mode,
    modeAuto: !strOrEmpty(askedMode),
    axes,
    marked: marked.length,
    wafers: members.length,
    members,
    sheets,
    wanted,
    pending: members.filter((m) => m.pending).length,
    focusWafer,
    focus: focus || null,
    detailCap: MAP_CAPS.detailWafers,
  };
}

/**
 * The `{row, slot}` pairs the loader should fetch next — the same computation the
 * render does, exported so the loader does not have to reimplement it.
 */
export function mapWants(model, maps, options) {
  return mapSection(model, maps, null, options).wanted;
}
