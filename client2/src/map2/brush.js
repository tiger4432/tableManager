// ═══════════════════════════════════════════════════════════════════════════════
// CELL BRUSH -- authoring on top of layer (4) SEATING. PURE.
// NO DOM. NO CANVAS. NO VIEWPORT. NO TRANSPORT. NO MODULE-LEVEL MUTABLE STATE.
//
// 🔴 THERE IS ONE COORDINATE IMPLEMENTATION AND THIS FILE DOES NOT CONTAIN IT.
//    A click has to travel seat -> cell index -> stored coordinate, which reads like an
//    invitation to write the inverse of `localIndex` and the inverse of `seatOf`. It is not.
//    Two spellings of one question ALWAYS diverge (MAP_ALIGNMENT_SPEC I6, measured three times
//    in one day), and here the divergence would be invisible: the picture stays a plausible
//    wafer while the authored dies land on other coordinates.
//
//    So this module runs the EXISTING transform FORWARDS over the authorable stored
//    coordinates and keeps the result as a lookup. `localIndex` and `seatOf` are imported and
//    called, never re-derived. A defect in either shows up in seating and in the brush at the
//    same time and in the same direction, which is the only property that makes the pair
//    trustworthy.
//
// 🔴 REGISTRATION BEFORE ANY VISIBILITY TEST -- structurally, not by ordering. There is no
//    viewport, no canvas size and no bounds argument anywhere in this file, so there is no
//    place to put the `continue` that removed 480 of 1600 declared cells from the legacy save
//    payload AND from the plan's numbers. Off-screen cannot become not-in-the-data here
//    because off-screen is not expressible.
//
// 🔴 NO GEOMETRY -> REFUSE, DO NOT GUESS. `boundingBoxOf` answering null means the frame
//    declares no physical geometry. This module then refuses: it does NOT build an identity
//    box. Stored coordinates are box relative, so an identity box silently reinterprets every
//    coordinate, and under `grid_y_invert` it mirrors about zero and sends every row negative
//    -- a new wrongness in a direction nobody has measured. Being wrong in the old, measured
//    way is recoverable; being wrong in a new way is not.
// ═══════════════════════════════════════════════════════════════════════════════

import { seatOf, seatKey, localIndex, boundingBoxOf, physOf, visualExtent,
         isCellInsideWafer } from './seating.js';

/** Named refusals. Nominal register; these are states, not sentences. */
export const BRUSH_REFUSAL = Object.freeze({
  NO_GEOMETRY: '기하 선언 없음',
  TOO_MANY_CELLS: '격자 상한 초과',
  NO_EXTENT: '격자 범위 없음',
});

/**
 * The enumeration ceiling. A 300mm wafer at a 2.5mm pitch is 14,400 dies, so a real grid
 * arrives comfortably under this.
 *
 * 🔴 EXCEEDING IT IS A REFUSAL, NEVER A TRUNCATION. A truncated authorable set is a wrong set
 *    that looks right: the operator paints inside it, the missing region is invisible, and the
 *    saved floor is short by exactly the part nobody could see. Truncation is demoted to
 *    failure here for the same reason the server demotes a truncated valid-die read.
 */
export const MAX_AUTHORABLE_CELLS = 20000;

/**
 * Every stored coordinate this frame can express, seated.
 *
 * THE ENUMERATION IS OVER STORED SPACE, NOT SEAT SPACE, and that is what keeps the transform
 * single. A stored coordinate is box relative with the frame's start offset applied
 * (MAP_ALIGNMENT_SPEC 2.3), so the expressible set is exactly
 *
 *     x in startX + [0 .. box.maxC - box.minC]
 *     y in startY + [0 .. box.maxR - box.minR]
 *
 * Each one is pushed through `localIndex` and then `seatOf` -- the same two calls, in the same
 * order, that `computeSeating` makes for a real cell. The seat-keyed map that falls out is
 * therefore a RECORD of the forward transform, not an inverse of it.
 *
 * The wafer circle is carried per seat as `insideCircle` and is NOT a filter. The circle is a
 * generator of a plausible starting shape, not a judge of validity: the maps this floor exists
 * for are taped parts whose valid-die shape a circle cannot express. Filtering here would
 * silently delete exactly the dies the operator opened the screen to declare.
 *
 * @param {{rotation:number, side:string, cols:number, rows:number, startX:number,
 *          startY:number, invertY:boolean}} frame
 * @returns frozen {boxKnown, box, refusal, seats:Map, coords:Array, count, bounds}
 */
export function authorableSeats(frame) {
  const box = boundingBoxOf(frame);
  if (!box) return refused(BRUSH_REFUSAL.NO_GEOMETRY);

  const spanX = box.maxC - box.minC + 1;
  const spanY = box.maxR - box.minR + 1;
  if (spanX <= 0 || spanY <= 0) return refused(BRUSH_REFUSAL.NO_EXTENT, box);
  if (spanX * spanY > MAX_AUTHORABLE_CELLS) return refused(BRUSH_REFUSAL.TOO_MANY_CELLS, box);

  const phys = physOf(frame);
  const extent = visualExtent(frame);
  const startX = finite(frame.startX, 0);
  const startY = finite(frame.startY, 0);

  const seats = new Map();
  const byCell = new Map();
  const coords = [];
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

  for (let j = 0; j < spanY; j++) {
    for (let i = 0; i < spanX; i++) {
      const x = startX + i;
      const y = startY + j;
      // THE SAME TWO CALLS `computeSeating` MAKES. Not a re-derivation of them.
      const { c, r } = localIndex(frame, box, x, y);
      const p = seatOf(frame, c, r);
      const key = seatKey(p.x, p.y);
      const entry = Object.freeze({
        x, y, c, r, seatX: p.x, seatY: p.y, key,
        insideCircle: isCellInsideWafer(c, r, extent.cols, extent.rows, phys),
      });
      // Registration is unconditional and happens here, before anything else can look at the
      // entry. There is no test between the loop head and this line, by construction.
      if (!seats.has(key)) seats.set(key, entry);
      byCell.set(cellKey(x, y), entry);
      coords.push(entry);
      if (p.x < minX) minX = p.x;
      if (p.x > maxX) maxX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.y > maxY) maxY = p.y;
    }
  }

  // ASSERTED, NOT DOCUMENTED. The enumeration is a bijection on a rectangle, so a seat
  // collision means the frame's transform is not injective over the box -- which would make
  // every count on this screen wrong. Better to stop than to answer short.
  if (seats.size !== coords.length) {
    throw new Error(
      `authorable seats collided: ${seats.size} seats for ${coords.length} stored coordinates. `
      + 'The frame transform is not injective over the bounding box.');
  }

  return Object.freeze({
    boxKnown: true,
    box,
    refusal: null,
    seats,
    byCell,
    coords: Object.freeze(coords),
    count: coords.length,
    bounds: Object.freeze({ minX, maxX, minY, maxY, empty: false }),
  });
}

function refused(reason, box) {
  return Object.freeze({
    boxKnown: false,
    box: box || null,
    refusal: reason,
    seats: new Map(),
    byCell: new Map(),
    coords: Object.freeze([]),
    count: 0,
    bounds: Object.freeze({ minX: 0, maxX: -1, minY: 0, maxY: -1, empty: true }),
  });
}

/**
 * A click, already converted to a seat by the renderer's own layout, back to the stored
 * coordinate it names. `null` means the click was outside the expressible set -- a fact worth
 * reporting, never a coordinate worth inventing.
 */
export function seatAt(authorable, seatX, seatY) {
  if (!authorable || !authorable.boxKnown) return null;
  return authorable.seats.get(seatKey(seatX, seatY)) || null;
}

// ── THE AUTHORED CELL TABLE ─────────────────────────────────────────────────────
// Immutable. Every operation returns a NEW frozen table, so an undo is a reference, not a
// replay, and no caller can hold a table that a later stroke mutated underneath it.

/** The key of a STORED coordinate. Distinct from `seatKey`, which keys a SEAT. */
export function cellKey(x, y) {
  return `${x},${y}`;
}

/**
 * @param {Array<{x,y,value}>} cells
 * @returns frozen {byKey:Map, count}
 *
 * LAST DECLARATION WINS on a duplicate coordinate, and the duplicates are REPORTED. A stored
 * map with two rows for one coordinate is a data defect; silently keeping one hides it.
 */
export function createCellTable(cells) {
  const byKey = new Map();
  const duplicates = [];
  for (const cell of Array.isArray(cells) ? cells : []) {
    if (!cell) continue;
    const x = finite(cell.x, null);
    const y = finite(cell.y, null);
    if (x === null || y === null) continue;
    const key = cellKey(x, y);
    if (byKey.has(key)) duplicates.push(key);
    byKey.set(key, Object.freeze({ x, y, value: cell.value === undefined ? null : cell.value }));
  }
  return Object.freeze({ byKey, count: byKey.size, duplicates: Object.freeze(duplicates) });
}

/** Stable, deterministic order: row major on the stored coordinate. The save payload's order. */
export function tableCells(table) {
  const out = [...((table && table.byKey) || new Map()).values()];
  out.sort((a, b) => (a.y - b.y) || (a.x - b.x));
  return Object.freeze(out);
}

/**
 * Paint `value` onto every coordinate in `coords` that the frame can express.
 *
 * @param {object} table       from `createCellTable`
 * @param {object} authorable  from `authorableSeats`
 * @param {Array<{x,y}>} coords
 * @param {*} value
 * @returns frozen {table, added, repainted, unchanged, rejected}
 *
 * `rejected` holds coordinates outside the expressible set. They are RETURNED, not dropped in
 * silence -- a brush that quietly ignores part of a stroke teaches the operator that the
 * stroke landed.
 *
 * INVARIANT ASSERTED HERE: the new table's count equals the old count plus `added.length`.
 * Nothing in this function may lose a cell that was already in the table.
 */
export function brushStroke(table, authorable, coords, value) {
  const before = (table && table.byKey) || new Map();
  const next = new Map(before);
  const added = [];
  const repainted = [];
  const unchanged = [];
  const rejected = [];

  for (const c of Array.isArray(coords) ? coords : []) {
    const x = finite(c && c.x, null);
    const y = finite(c && c.y, null);
    if (x === null || y === null) { rejected.push(c); continue; }
    if (!expressible(authorable, x, y)) { rejected.push(Object.freeze({ x, y })); continue; }
    const key = cellKey(x, y);
    const prev = next.get(key);
    const cell = Object.freeze({ x, y, value });
    if (!prev) added.push(cell);
    else if (prev.value !== value) repainted.push(cell);
    else { unchanged.push(prev); continue; }
    next.set(key, cell);
  }

  const out = Object.freeze({
    byKey: next, count: next.size, duplicates: (table && table.duplicates) || Object.freeze([]),
  });
  if (out.count !== before.size + added.length) {
    throw new Error(
      `brushStroke lost a cell: ${before.size} + ${added.length} added should be ${out.count}. `
      + 'A stroke registers and repaints; it never removes.');
  }
  return Object.freeze({
    table: out,
    added: Object.freeze(added),
    repainted: Object.freeze(repainted),
    unchanged: Object.freeze(unchanged),
    rejected: Object.freeze(rejected),
  });
}

/**
 * Remove coordinates from the table.
 *
 * 🔴 ERASING IS A SEPARATE VERB FROM PAINTING, and it is not "paint with an empty value".
 *    On this table a row's EXISTENCE is what declares a die valid (the server reads existence,
 *    not value), so an erase that wrote an empty value would leave the die declared while the
 *    screen showed it gone.
 */
export function eraseStroke(table, coords) {
  const before = (table && table.byKey) || new Map();
  const next = new Map(before);
  const removed = [];
  const absent = [];
  for (const c of Array.isArray(coords) ? coords : []) {
    const x = finite(c && c.x, null);
    const y = finite(c && c.y, null);
    if (x === null || y === null) { absent.push(c); continue; }
    const key = cellKey(x, y);
    const prev = next.get(key);
    if (!prev) { absent.push(Object.freeze({ x, y })); continue; }
    next.delete(key);
    removed.push(prev);
  }
  const out = Object.freeze({
    byKey: next, count: next.size, duplicates: (table && table.duplicates) || Object.freeze([]),
  });
  if (out.count !== before.size - removed.length) {
    throw new Error(
      `eraseStroke removed the wrong number: ${before.size} - ${removed.length} should be `
      + `${out.count}.`);
  }
  return Object.freeze({
    table: out, removed: Object.freeze(removed), absent: Object.freeze(absent),
  });
}

/**
 * Does the frame have a stored spelling for this coordinate?
 *
 * ASKED OF THE ENUMERATION, NOT RECOMPUTED FROM THE BOX. Recomputing the rectangle here would
 * be a second definition of the expressible set, and the day it disagreed with the enumeration
 * the brush would accept a coordinate that has no seat -- painting a die onto nothing.
 */
export function expressible(authorable, x, y) {
  if (!authorable || !authorable.boxKnown) return false;
  return authorable.byCell.has(cellKey(x, y));
}

/**
 * A finite number or the stated default.
 *
 * 🔴 `Number(null)` IS `0`, AND A ZERO THAT CAME FROM AN ABSENCE IS INDISTINGUISHABLE FROM A
 *    DECLARED ZERO once it is in the arithmetic. `null` and `''` are therefore tested before
 *    the coercion, and a boolean is refused outright -- `Number(true)` is 1, which is a
 *    perfectly plausible coordinate.
 */
function finite(v, dflt) {
  if (v === null || v === undefined || v === '' || typeof v === 'boolean') return dflt;
  const n = Number(v);
  return Number.isFinite(n) ? n : dflt;
}
