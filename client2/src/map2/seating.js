// ═══════════════════════════════════════════════════════════════════════════════
// LAYER (4) SEATING -- declaration + evidence => every cell's seat in the common space.
// REGISTRATION ONLY. THIS FILE CANNOT DRAW.
//
// (MAP_ALIGNMENT_SPEC 0.2 layer 4 and 0.3 step 3.)
//
// 🔴 THE DEFECT THIS FILE EXISTS TO MAKE IMPOSSIBLE. In the legacy editor, `renderGridCanvas`
//    is the sole producer of the cell table, the seating record AND the overlay reseat, and it
//    happens to paint while doing it. Its off-canvas `continue` runs BEFORE the registration
//    line, so a declared cell pushed past the canvas edge disappears from the save payload and
//    from the plan's numbers alike -- "off screen" silently became "not in the data".
//
//    The split here is not a tidier arrangement of the same code. It is a different claim:
//    seating is computed and returned as DATA, with no viewport in scope. There is no canvas
//    size in this module, so there is no place to put a `continue`. The renderer receives the
//    result and only paints; nothing downstream ever reads the renderer's output as data.
//
// NO DOM. NO CANVAS. NO TRANSPORT. NO MODULE-LEVEL MUTABLE STATE.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Where does the cell at ORIGIN-RELATIVE index (c, r) sit, read under `frame`?
 *
 * Transcribed from the seam's own definition -- `server/utils/coordinate_transformer.py`
 * `cell_to_physical` -- rather than re-derived, so the two sides cannot drift by a
 * re-derivation. `side: back` is a LEFT/RIGHT mirror (about `visualCols - 1`) except under a
 * quarter turn, where the same physical flip lands on the row axis.
 *
 * @param {{rotation:number, side:string, cols:number, rows:number}} frame
 */
export function seatOf(frame, c, r) {
  const quarter = frame.rotation === 90 || frame.rotation === 270;
  const visualCols = quarter ? frame.rows : frame.cols;
  const visualRows = quarter ? frame.cols : frame.rows;

  let cm = c;
  let rm = r;
  if (frame.side === 'back') {
    if (quarter) rm = (visualRows - 1) - r;
    else cm = (visualCols - 1) - c;
  }

  switch (frame.rotation) {
    case 90:  return { x: rm, y: (visualCols - 1) - cm };
    case 180: return { x: (visualCols - 1) - cm, y: (visualRows - 1) - rm };
    case 270: return { x: (visualRows - 1) - rm, y: cm };
    default:  return { x: cm, y: rm };
  }
}

export function seatKey(x, y) {
  return `${x},${y}`;
}

// ── THE BOUNDING BOX ────────────────────────────────────────────────────────────
// 🔴 A STORED COORDINATE IS BOUNDING-BOX RELATIVE, NOT GRID RELATIVE. This is the term that
//    was missing, and its absence put EVERY cell of four contract fixtures on the wrong die
//    (3430 of 3430 across the group, measured by the contract lane) while the picture still
//    looked like a plausible wafer -- which is the worst possible failure mode, because the
//    operator confirms an alignment that is off and the confirmation is the thing we write.
//
// The convention is `xv = c - box.minC + start_x` (MAP_ALIGNMENT_SPEC 2.3), so the reverse a
// seating layer needs is `c = xv - start_x + box.minC`. The box is the extent of the dies that
// fall inside the wafer circle, computed in VISUAL space -- so it depends on the frame's
// rotation, which is why it is recomputed per frame rather than cached on the map.
//
// The geometry below is transcribed from the seam's own definition
// (`PhysicalWaferEngine.is_cell_inside_wafer` and `WaferMapCoordinateTransformer
// .get_wafer_bounding_box`), not re-derived: a cell is inside only when ALL FOUR of its
// corners are within the effective radius, and the effective radius is the wafer radius less
// the edge exclusion.
//
// ⚠️ THE BOX NEEDS PHYSICAL PARAMETERS AND THEY ARE NOT OPTIONAL. Without them there is no
//    circle, and a frame with no circle has no box. `boundingBoxOf` returns null in that case
//    and the caller must refuse rather than substitute a zero box: a zero box is a plausible
//    default impersonating a declaration, and it is exactly the shape this file was wrong in.

/**
 * Physical parameters IN FRAME AXES -- transcribed from `server/map_overlay._frame_phys_params`.
 *
 * 🔴 THE MAP'S PHYSICAL SPEC IS NOT THE FRAME'S PHYSICAL SPEC, AND SUBSTITUTING ONE FOR THE
 *    OTHER MOVES THE WHOLE BOX. `is_cell_inside_wafer` turns a grid index into millimetres with
 *    `x_mm = (c - cc) * chip_x + off_x`, and `(c, r)` there is a FRAME index -- so `chip_x` has
 *    to be the pitch of the frame's x axis. Under a quarter turn that axis is the physical Y
 *    axis, so the PITCHES SWAP; and because `cell_to_physical` applies the side flip BEFORE the
 *    rotation, the x offset's SIGN flips on the back. Feed the raw meta values in and a rotated
 *    map's bounding box is displaced as a whole -- and since stored coordinates are box
 *    relative, every cell moves with it.
 *
 * The rule below is the server's own table, copied term for term rather than re-derived. Its
 * derivation is recorded in that function's docstring and was checked there across all eight
 * rotation x side combinations; re-deriving it here would be a second derivation of the
 * subtlest arithmetic in the system, and the two would eventually disagree.
 *
 *   | rotation | (chip_x, chip_y) | (off_x, off_y) |
 *   | 0        | (cx, cy)         | ( oox,  ooy)   |
 *   | 90       | (cy, cx)         | ( ooy, -oox)   |
 *   | 180      | (cx, cy)         | (-oox, -ooy)   |
 *   | 270      | (cy, cx)         | (-ooy,  oox)   |
 *
 * where `oox` is the meta's x offset with its sign flipped on the back side, and `ooy` is the
 * meta's y offset unchanged.
 *
 * Returns null when the frame declares no physical geometry -- there is no circle, so there is
 * no box, and a zero box would be a plausible default impersonating a declaration.
 */
export function physOf(frame) {
  const dia = num(frame.physWaferDia, frame.phys_wafer_dia);
  const cx = num(frame.physChipX, frame.phys_chip_x);
  const cy = num(frame.physChipY, frame.phys_chip_y);
  if (dia === null || cx === null || cy === null) return null;
  const margin = num(frame.physEdgeMargin, frame.phys_edge_margin);

  // The side flip is applied BEFORE the rotation, and it mirrors the physical x axis.
  const rawX = num(frame.physOffsetX, frame.phys_offset_x) || 0;
  const oox = frame.side === 'back' ? -rawX : rawX;
  const ooy = num(frame.physOffsetY, frame.phys_offset_y) || 0;

  let chipX = cx, chipY = cy, offsetX = oox, offsetY = ooy;
  if (frame.rotation === 90) {
    chipX = cy; chipY = cx; offsetX = ooy; offsetY = -oox;
  } else if (frame.rotation === 180) {
    offsetX = -oox; offsetY = -ooy;
  } else if (frame.rotation === 270) {
    chipX = cy; chipY = cx; offsetX = -ooy; offsetY = oox;
  }

  return Object.freeze({
    dia,
    chipX: Math.max(0.1, chipX),
    chipY: Math.max(0.1, chipY),
    offsetX,
    offsetY,
    radius: Math.max(0, dia / 2 - Math.max(0, margin === null ? 0 : margin)),
  });
}

/** Visual extents under this frame's rotation. A quarter turn swaps them. */
export function visualExtent(frame) {
  const quarter = frame.rotation === 90 || frame.rotation === 270;
  return {
    cols: quarter ? numOr(frame.rows, 0) : numOr(frame.cols, 0),
    rows: quarter ? numOr(frame.cols, 0) : numOr(frame.rows, 0),
  };
}

/** All four corners of the die inside the effective radius. Corners, not the centre. */
export function isCellInsideWafer(c, r, cols, rows, phys) {
  if (!phys || phys.radius <= 0) return false;
  const cx = (c - (cols - 1) / 2) * phys.chipX + phys.offsetX;
  const cy = ((rows - 1) / 2 - r) * phys.chipY + phys.offsetY;
  const hw = phys.chipX / 2;
  const hh = phys.chipY / 2;
  const rsq = phys.radius * phys.radius;
  const xs = [cx - hw, cx + hw];
  const ys = [cy - hh, cy + hh];
  for (const x of xs) for (const y of ys) if (x * x + y * y > rsq) return false;
  return true;
}

/**
 * @returns {{minC,maxC,minR,maxR}|null} null when the frame declares no physical geometry, or
 *          when no die falls inside the circle. Both are refusals, not zeros.
 */
export function boundingBoxOf(frame) {
  const phys = physOf(frame);
  if (!phys) return null;
  const { cols, rows } = visualExtent(frame);
  if (cols <= 0 || rows <= 0) return null;
  let minC = Infinity, maxC = -Infinity, minR = Infinity, maxR = -Infinity;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (!isCellInsideWafer(c, r, cols, rows, phys)) continue;
      if (c < minC) minC = c;
      if (c > maxC) maxC = c;
      if (r < minR) minR = r;
      if (r > maxR) maxR = r;
    }
  }
  if (minC === Infinity) return null;
  return Object.freeze({ minC, maxC, minR, maxR });
}

/**
 * Stored coordinate -> the frame's own cell index, carrying BOTH terms the seam requires.
 *
 *     c = xv - startX + box.minC
 *     r = invertY ? box.maxR - (yv - startY) : yv - startY + box.minR
 *
 * 🔴 THE Y BRANCH IS A REFLECTION, NOT A TRANSLATION, so it cannot be absorbed by the solved
 *    start shift the scorer applies -- which is why omitting it was not harmless the way an
 *    omitted constant would have been. Production carries rows with `grid_y_invert` true, and
 *    one of them sits on a decentred box, so the two terms interact.
 */
export function localIndex(frame, box, x, y) {
  const c = numOr(x, 0) - numOr(frame.startX, 0) + box.minC;
  const dy = numOr(y, 0) - numOr(frame.startY, 0);
  // 🔴 WITH NO BOX THE MIRROR IS NOT APPLIED EITHER, and that is deliberate. The mirror is
  //    ABOUT `box.maxR`; with an identity box it would reflect about zero and send every row
  //    negative -- a NEW wrongness on top of the old one, in a direction nobody has measured.
  //    So a frame with no physical geometry keeps exactly its previous behaviour and is
  //    flagged `boxKnown: false` instead. Being wrong in the old, measured way is recoverable;
  //    being wrong in a new way is not.
  const known = box !== IDENTITY_BOX;
  const r = (known && frame.invertY === true) ? box.maxR - dy : dy + box.minR;
  return { c, r };
}

/**
 * Seat EVERY cell. The returned record is the only thing anyone downstream may treat as data.
 *
 * @param {Array<{x:number,y:number,value?:*}>} cells  stored coordinates (origin-relative cell
 *        counts -- pitch is not involved; a coordinate is a cell count, never a millimetre).
 * @param {{rotation:number, side:string, cols:number, rows:number, startX:number, startY:number}} frame
 * @returns {{seats:Array, seatCount:number, bounds:object, byKey:Map, collisions:Array}}
 *
 * INVARIANT, ASSERTED HERE RATHER THAN DOCUMENTED: `seatCount === cells.length`. Nothing in
 * this function may drop a cell, so if the two ever differ it throws instead of returning a
 * quietly short answer. A silent short answer is the exact failure being closed.
 *
 * COLLISIONS ARE REPORTED, NOT RESOLVED. Two cells landing on one seat means the declaration
 * is wrong (or the map has duplicate coordinates); silently keeping the last one would hide
 * that. They are all seated; the duplicates are also listed.
 */
export function computeSeating(cells, frame) {
  const list = Array.isArray(cells) ? cells : [];
  const seats = new Array(list.length);
  const byKey = new Map();
  const collisions = [];
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

  // The box is resolved ONCE per seating, not per cell. `null` means the frame declared no
  // physical geometry: the identity box is used and the result says so, so a caller can refuse
  // rather than be handed coordinates that silently assume a centred wafer.
  const box = boundingBoxOf(frame) || IDENTITY_BOX;
  const boxKnown = box !== IDENTITY_BOX;

  for (let i = 0; i < list.length; i++) {
    const cell = list[i];
    const { c, r } = localIndex(frame, box, cell.x, cell.y);
    const p = seatOf(frame, c, r);
    const key = seatKey(p.x, p.y);
    const seat = Object.freeze({ index: i, x: p.x, y: p.y, key, cell });
    seats[i] = seat;
    if (byKey.has(key)) collisions.push(seat);
    else byKey.set(key, seat);
    if (p.x < minX) minX = p.x;
    if (p.x > maxX) maxX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.y > maxY) maxY = p.y;
  }

  if (seats.length !== list.length) {
    throw new Error(
      `seating dropped a cell: ${seats.length} seats for ${list.length} cells. `
      + 'Seating registers; it never filters.');
  }

  const bounds = list.length === 0
    ? Object.freeze({ minX: 0, maxX: -1, minY: 0, maxY: -1, empty: true })
    : Object.freeze({ minX, maxX, minY, maxY, empty: false });

  return Object.freeze({
    seats: Object.freeze(seats),
    seatCount: seats.length,
    bounds,
    byKey,
    collisions: Object.freeze(collisions),
    frame: Object.freeze({ ...frame }),
    box,
    // Stated, not assumed. A consumer that cares whether these coordinates rest on a real
    // wafer geometry can ask, instead of discovering it from a picture that looks plausible.
    boxKnown,
  });
}

/** Union of two seatings' bounds, so a floor and a source share one coordinate window. */
export function unionBounds(a, b) {
  if (!a || a.empty) return b || Object.freeze({ minX: 0, maxX: -1, minY: 0, maxY: -1, empty: true });
  if (!b || b.empty) return a;
  return Object.freeze({
    minX: Math.min(a.minX, b.minX),
    maxX: Math.max(a.maxX, b.maxX),
    minY: Math.min(a.minY, b.minY),
    maxY: Math.max(a.maxY, b.maxY),
    empty: false,
  });
}

/**
 * Per-seat comparison of a source against the floor, in the common space.
 * Returns COUNTS ONLY -- never a ratio. A ratio computed here would eventually be rendered,
 * and a coverage ratio provably inverts the ranking (a correctly-oriented but offset candidate
 * outranked by three wrongly-oriented ones), so the ratio is not produced at any point.
 */
export function compareSeatings(floorSeating, sourceSeating) {
  const agree = [];
  const sourceOnly = [];
  const floorOnly = [];
  for (const seat of sourceSeating.seats) {
    if (floorSeating.byKey.has(seat.key)) agree.push(seat);
    else sourceOnly.push(seat);
  }
  for (const seat of floorSeating.seats) {
    if (!sourceSeating.byKey.has(seat.key)) floorOnly.push(seat);
  }
  return Object.freeze({
    agree: Object.freeze(agree),
    sourceOnly: Object.freeze(sourceOnly),
    floorOnly: Object.freeze(floorOnly),
    agreeCount: agree.length,
    sourceOnlyCount: sourceOnly.length,
    floorOnlyCount: floorOnly.length,
  });
}

/**
 * The box used when a frame declares no physical geometry. It is the IDENTITY, and seatings
 * built on it are flagged `boxKnown: false` -- it is a stated absence, never a claim that the
 * box happens to be at the origin.
 */
const IDENTITY_BOX = Object.freeze({ minC: 0, maxC: 0, minR: 0, maxR: 0 });

function numOr(v, dflt) {
  const n = Number(v);
  return Number.isFinite(n) ? n : dflt;
}

/** First finite value among the spellings, or null. `Number(null)` is 0, so `null` is tested. */
function num(...vals) {
  for (const v of vals) {
    if (v === null || v === undefined || v === '' || typeof v === 'boolean') continue;
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return null;
}
