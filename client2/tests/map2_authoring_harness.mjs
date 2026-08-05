/**
 * MAP EDITOR 2 -- AUTHORING: CELL BRUSH, LEGEND, AND THE VALID-DIE SAVE CONTRACT.
 *
 * THIS HARNESS DOES NOT SLICE SOURCE. It `import`s every module it scores. There is no
 * `readFileSync` of a `.js`, no `node:vm`, and no `node_modules` dependency. That is possible
 * because the modules under test take arguments and return values.
 *
 * WHAT IS SCORED
 *   A. FIXTURE POTENCY -- the frames below actually ACTIVATE the defect axes. A fixture with
 *      `chip_x == chip_y`, `minC == 0` or `invertY` false cannot show a pitch swap, a box term
 *      or a mirror going wrong, and a green run on such a fixture measures nothing.
 *   B. ONE TRANSFORM -- the brush's stored-coordinate enumeration and `computeSeating` agree
 *      KEY BY VALUE over every authorable coordinate, and a deliberately wrong frame moves a
 *      counted number of them. If that number were zero the comparison would prove nothing.
 *   C. NOTHING DROPS A CELL -- enumeration, stroke and erase all account for every cell, at
 *      coordinates far outside any plausible viewport.
 *   D. NO GEOMETRY -> REFUSE -- a frame with no declared physical spec produces a refusal, not
 *      an identity box, and no coordinate is authorable through it.
 *   E. LEGEND -- value to colour and label; an undeclared value answers `null` and `null` is
 *      never turned into a colour.
 *   F. SAVE CONTRACT -- every precondition of a floor write, and a refused gate cannot produce
 *      a request body.
 *   G. DEFECT MODELS -- each defect below is injected into the data path and MUST turn this
 *      battery red. A model that cannot be applied stops the run; a model that survives fails
 *      the run. These are injected defects, not source rewrites: the harness never reads a
 *      `.js` file.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe): no emoji, no em-dash.
 */

import { computeSeating, seatOf, seatKey, boundingBoxOf, physOf,
         visualExtent } from '../src/map2/seating.js';
import * as BRUSH from '../src/map2/brush.js';
import * as LEGEND from '../src/map2/legend.js';
import * as AUTHORING from '../src/map2/authoring.js';

// ── FIXTURES ────────────────────────────────────────────────────────────────────
// Transcribed from `wafer_map_metadata` rows on the DEVELOPMENT box (2026-08-05, read only).
// THIS BOX IS NOT PRODUCTION and these are used as SHAPES, not as production facts.
//   valid_die_ref / CORE_1X    rot 270 front  45x39  chip 7x8  dia 300  off (5,5)
//   valid_die_ref / CORE_YINV  rot 0   front  45x39  chip 7x8  dia 300  off (5,5)  y-invert
// Both are anisotropic and decentred, which is exactly why they were chosen.

const F_QUARTER = Object.freeze({           // quarter turn: the pitches swap
  rotation: 270, side: 'front', cols: 45, rows: 39, startX: 1, startY: 1, invertY: false,
  phys_wafer_dia: 300, phys_chip_x: 7, phys_chip_y: 8, phys_edge_margin: 3,
  phys_offset_x: 5, phys_offset_y: 5,
});

const F_YINV = Object.freeze({              // the mirror branch, on a decentred box
  rotation: 0, side: 'front', cols: 45, rows: 39, startX: 1, startY: 1, invertY: true,
  phys_wafer_dia: 300, phys_chip_x: 7, phys_chip_y: 8, phys_edge_margin: 3,
  phys_offset_x: 5, phys_offset_y: 5,
});

const F_BACK_QUARTER = Object.freeze({      // side flip AND quarter turn together
  rotation: 90, side: 'back', cols: 45, rows: 39, startX: 2, startY: 3, invertY: false,
  phys_wafer_dia: 300, phys_chip_x: 7, phys_chip_y: 8, phys_edge_margin: 3,
  phys_offset_x: 5, phys_offset_y: 5,
});

const F_NO_GEOMETRY = Object.freeze({       // registered spec, no physical declaration
  rotation: 0, side: 'front', cols: 25, rows: 25, startX: 0, startY: 0, invertY: false,
});

const LEGEND_ROWS = Object.freeze([
  { value: '1', desc: 'GOOD', color: '#10b981' },
  { value: '0', desc: 'FAIL', color: '#ef4444' },
  { value: 'E1', desc: 'Edge 1' },            // in the vocabulary, no colour declared
]);
const DEFAULT_LEGEND_ROWS = Object.freeze([
  { value: '1', desc: 'DEFAULT GOOD', color: '#000000' },
  { value: 'E2', desc: 'Edge 2', color: '#ec4899' },
]);

const FLOOR_KEY_COLUMNS = Object.freeze(['product', 'type']);
const FLOOR_COLUMN_TYPES = Object.freeze({ product: 'string', type: 'string' });

// ── THE BATTERY ─────────────────────────────────────────────────────────────────
// A function of the module bundle so a defect model can be substituted for one export.

function run(M) {
  let compared = 0;
  const failures = [];
  const ok = (cond, what) => { compared++; if (!cond) failures.push(what); };
  const eq = (a, b, what) => {
    compared++;
    if (a !== b) failures.push(`${what}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
  };
  const throws = (fn, what) => {
    compared++;
    try { fn(); failures.push(`${what}: expected a throw, none happened`); } catch (e) { /* ok */ }
  };

  const { brush, legend, authoring } = M;

  // ── A. FIXTURE POTENCY ────────────────────────────────────────────────────────
  // If any of these fail, every green below is worthless: the fixture cannot express the
  // defect. This is asserted, not assumed, because a fixture that dies quietly is how a
  // harness reports coverage it does not have.
  {
    const phys = physOf(F_QUARTER);
    ok(phys !== null, 'A1 the quarter-turn fixture declares physical geometry');
    ok(phys.chipX !== phys.chipY,
       `A2 the fixture is anisotropic (chipX ${phys.chipX} vs chipY ${phys.chipY}) -- an `
       + 'isotropic chip cannot show a pitch swap');
    const box = boundingBoxOf(F_QUARTER);
    ok(box !== null, 'A3 the quarter-turn fixture has a bounding box');
    ok(box.minC !== 0,
       `A4 the box is decentred on x (minC ${box.minC}) -- minC 0 hides a dropped box term`);
    ok(box.minR !== 0,
       `A5 the box is decentred on y (minR ${box.minR}) -- minR 0 hides a dropped box term`);
    ok(F_YINV.invertY === true, 'A6 a fixture exercises the grid_y_invert mirror');
    ok(F_BACK_QUARTER.side === 'back', 'A7 a fixture exercises the side flip');
    const ext = visualExtent(F_QUARTER);
    eq(ext.cols, 39, 'A8 a quarter turn swaps the visual extents (cols)');
    eq(ext.rows, 45, 'A9 a quarter turn swaps the visual extents (rows)');
    ok(boundingBoxOf(F_NO_GEOMETRY) === null,
       'A10 the geometry-less fixture really has no box');
  }

  // ── B. ONE TRANSFORM ──────────────────────────────────────────────────────────
  for (const [name, frame] of [['quarter', F_QUARTER], ['yinv', F_YINV],
                               ['back-quarter', F_BACK_QUARTER]]) {
    const authorable = brush.authorableSeats(frame);
    ok(authorable.boxKnown === true, `B1 ${name}: the frame is authorable`);
    ok(authorable.count > 0, `B2 ${name}: the authorable set is non-empty`);

    // KEY BY VALUE, not a count and not a round trip through the same function. Every stored
    // coordinate the brush enumerates is fed to `computeSeating` -- the production path -- and
    // the two must name the SAME seat. A round-trip identity would pass with a defective `f`
    // and its own inverse; this cannot.
    const cells = authorable.coords.map(c => ({ x: c.x, y: c.y, value: '1' }));
    const seating = computeSeating(cells, frame);
    eq(seating.seatCount, cells.length, `B3 ${name}: seating registers every enumerated cell`);
    let mismatched = 0;
    for (let i = 0; i < cells.length; i++) {
      const want = authorable.coords[i];
      const got = seating.seats[i];
      if (got.x !== want.seatX || got.y !== want.seatY) mismatched++;
    }
    eq(mismatched, 0, `B4 ${name}: brush and computeSeating agree seat by seat`);

    // COUNTERFACTUAL. Read the same coordinates under a deliberately wrong frame and count how
    // many seats move. Zero would mean the fixture cannot tell the frames apart, so the
    // agreement above would be evidence of nothing.
    const wrong = Object.freeze({ ...frame, rotation: (frame.rotation + 90) % 360 });
    const wrongSeating = computeSeating(cells, wrong);
    let moved = 0;
    for (let i = 0; i < cells.length; i++) {
      if (wrongSeating.seats[i].x !== seating.seats[i].x
          || wrongSeating.seats[i].y !== seating.seats[i].y) moved++;
    }
    ok(moved > 0,
       `B5 ${name}: a wrong frame moves ${moved} of ${cells.length} seats -- 0 would mean the `
       + 'fixture cannot distinguish frames');

    // The seat map is what a click reads. It must answer for a seat the enumeration produced
    // and refuse for one it did not.
    const first = authorable.coords[0];
    const hit = brush.seatAt(authorable, first.seatX, first.seatY);
    ok(hit !== null && hit.x === first.x && hit.y === first.y,
       `B6 ${name}: a click on an enumerated seat names its stored coordinate`);
    eq(brush.seatAt(authorable, 100000, 100000), null,
       `B7 ${name}: a click outside the enumerated set names no coordinate`);
  }

  // ── C. NOTHING DROPS A CELL ───────────────────────────────────────────────────
  {
    const authorable = brush.authorableSeats(F_QUARTER);
    eq(authorable.seats.size, authorable.count,
       'C1 every enumerated coordinate has its own seat (the transform is injective)');

    // Coordinates chosen to sit far outside any plausible viewport, in BOTH directions. The
    // legacy defect skipped these before registering them.
    const far = authorable.coords.filter(c => c.seatX < 3 || c.seatY < 3
                                         || c.seatX > 35 || c.seatY > 40);
    ok(far.length > 0, 'C2 the fixture contains seats at the extremes');

    let table = brush.createCellTable([]);
    const stroke = brush.brushStroke(table, authorable, far.map(c => ({ x: c.x, y: c.y })), '1');
    eq(stroke.added.length, far.length, 'C3 every extreme coordinate is registered');
    eq(stroke.rejected.length, 0, 'C4 no extreme coordinate is rejected');
    eq(stroke.table.count, far.length, 'C5 the table holds every registered cell');
    table = stroke.table;

    // A repaint must not add, and must not lose.
    const repaint = brush.brushStroke(table, authorable, far.map(c => ({ x: c.x, y: c.y })), '0');
    eq(repaint.added.length, 0, 'C6 repainting an existing cell adds nothing');
    eq(repaint.repainted.length, far.length, 'C7 repainting is reported as a repaint');
    eq(repaint.table.count, far.length, 'C8 repainting does not change the count');
    eq(brush.tableCells(repaint.table).every(c => c.value === '0'), true,
       'C9 repainting actually changed the values');

    // Painting the same value twice is neither an add nor a repaint.
    const again = brush.brushStroke(repaint.table, authorable,
                                    far.map(c => ({ x: c.x, y: c.y })), '0');
    eq(again.unchanged.length, far.length, 'C10 an idempotent stroke is reported as unchanged');
    eq(again.table.count, far.length, 'C11 an idempotent stroke does not change the count');

    // Erase removes rows; it does NOT write an empty value. Existence is the declaration.
    const gone = brush.eraseStroke(repaint.table, far.slice(0, 5).map(c => ({ x: c.x, y: c.y })));
    eq(gone.removed.length, 5, 'C12 erase removes exactly the named cells');
    eq(gone.table.count, far.length - 5, 'C13 erase leaves the rest');
    eq(brush.tableCells(gone.table).some(c => c.value === '' || c.value === null), false,
       'C14 erase does not leave an empty-valued row behind');
    const absent = brush.eraseStroke(gone.table, far.slice(0, 5).map(c => ({ x: c.x, y: c.y })));
    eq(absent.absent.length, 5, 'C15 erasing an absent cell is reported, not silent');
    eq(absent.table.count, far.length - 5, 'C16 erasing an absent cell changes nothing');

    // A coordinate the frame cannot express is REJECTED and reported, never invented.
    const bad = brush.brushStroke(table, authorable, [{ x: 99999, y: 99999 }], '1');
    eq(bad.rejected.length, 1, 'C17 an unexpressible coordinate is rejected');
    eq(bad.added.length, 0, 'C18 an unexpressible coordinate is not registered');

    // The table is immutable: the original is untouched by every operation above.
    eq(table.count, far.length, 'C19 the source table is never mutated in place');

    // Duplicate stored coordinates are reported, not silently collapsed.
    const dup = brush.createCellTable([{ x: 1, y: 1, value: '1' }, { x: 1, y: 1, value: '0' }]);
    eq(dup.count, 1, 'C20 a duplicate coordinate yields one row');
    eq(dup.duplicates.length, 1, 'C21 the duplicate is reported');
  }

  // ── D. NO GEOMETRY -> REFUSE ──────────────────────────────────────────────────
  {
    const a = brush.authorableSeats(F_NO_GEOMETRY);
    eq(a.boxKnown, false, 'D1 a frame with no physical declaration is not authorable');
    eq(a.refusal, brush.BRUSH_REFUSAL.NO_GEOMETRY, 'D2 the refusal is named');
    eq(a.count, 0, 'D3 no coordinate is authorable through it');
    eq(a.box, null, 'D4 no box is substituted');
    eq(brush.seatAt(a, 0, 0), null, 'D5 no click resolves through it');
    eq(brush.expressible(a, 0, 0), false, 'D6 the origin is not quietly expressible');
    const stroke = brush.brushStroke(brush.createCellTable([]), a, [{ x: 0, y: 0 }], '1');
    eq(stroke.added.length, 0, 'D7 a stroke through a geometry-less frame registers nothing');
    eq(stroke.rejected.length, 1, 'D8 and says so');
  }

  // ── E. LEGEND ─────────────────────────────────────────────────────────────────
  {
    const L = legend.resolveLegend(LEGEND_ROWS, DEFAULT_LEGEND_ROWS);
    eq(legend.colorOf(L, '1'), '#10b981', "E1 the map's own row shadows the served default");
    eq(legend.labelOf(L, '1'), 'GOOD', 'E2 the label comes from the same row as the colour');
    eq(legend.colorOf(L, 'E2'), '#ec4899',
       'E3 a value the map does not declare still reads from the served default');
    eq(legend.colorOf(L, 'E1'), null,
       'E4 a declared value with no declared colour answers null, not a colour');
    eq(legend.labelOf(L, 'E1'), 'Edge 1', 'E5 and keeps its label');
    eq(legend.colorOf(L, 'ZZZ'), null, 'E6 an undeclared value answers null');
    eq(legend.isDeclaredValue(L, 'ZZZ'), false, 'E7 and is not in the vocabulary');
    eq(legend.isDeclaredValue(L, 'E1'), true, 'E8 a colourless row is still in the vocabulary');
    eq(legend.colorOf(L, ''), null, 'E9 the empty string is not a value');
    eq(legend.colorOf(L, null), null, 'E10 null is not a value');
    eq(legend.colorOf(L, undefined), null, 'E11 undefined is not a value');
    eq(legend.colorOf(L, true), null, 'E12 a boolean is not a value');
    eq(legend.colorOf(L, 1), '#10b981', 'E13 values compare as strings');

    const entries = legend.legendEntries(L);
    eq(entries.length, 4, 'E14 the strip carries every declared value once');
    const e1 = entries.find(e => e.value === 'E1');
    eq(e1.colorKnown, false, 'E15 a missing colour is STATED, not left to be inferred');
    eq(e1.colorNote, legend.NO_COLOUR_DECLARED, 'E16 and is named in words');
    eq(entries.find(e => e.value === '1').source, 'own', 'E17 the strip records the source');
    eq(entries.find(e => e.value === 'E2').source, 'default', 'E18 for both sources');
    ok(entries.every(e => !/\d\s*%/.test(String(e.label))), 'E19 no percentage in a label');
    ok(entries.every(e => !('count' in e) && !('share' in e)),
       'E20 a legend entry carries no tally, so it can carry no share');

    // First declaration wins, so appending a row cannot retint an existing one.
    const dupL = legend.resolveLegend([{ value: '1', color: '#aaa' },
                                       { value: '1', color: '#bbb' }], []);
    eq(legend.colorOf(dupL, '1'), '#aaa', 'E21 the first declaration of a value wins');
    eq(legend.brushableValues(L).length, 4, 'E22 the brush palette is the declared vocabulary');
  }

  // ── F. SAVE CONTRACT ──────────────────────────────────────────────────────────
  {
    const L = legend.resolveLegend(LEGEND_ROWS, DEFAULT_LEGEND_ROWS);
    const authorable = brush.authorableSeats(F_QUARTER);
    const picked = authorable.coords.slice(0, 200).map(c => ({ x: c.x, y: c.y }));
    const painted = brush.brushStroke(brush.createCellTable([]), authorable, picked, '1').table;
    const META = Object.freeze({
      rotation: 270, side: 'front', grid_cols: 45, grid_rows: 39, grid_y_invert: false,
      phys_chip_x: 7, phys_chip_y: 8, phys_wafer_dia: 300, phys_edge_margin: 3,
      phys_offset_x: 5, phys_offset_y: 5, start_x: 1, start_y: 1,
    });
    const base = {
      table: authoring.FLOOR_TABLE, mapKey: 'CORE_1X',
      keyColumns: FLOOR_KEY_COLUMNS, columnTypes: FLOOR_COLUMN_TYPES,
      cellTable: painted, authorable, legend: L,
      storedMeta: META, nextMeta: META, origin: 'server', truncated: false,
      storedCellCount: 854, confirmedBy: 'tester',
    };
    const tokens = g => g.refusals.map(r => r.token);

    const good = authoring.checkSaveGate(base);
    eq(good.ok, true, `F1 a complete floor write passes the gate (${tokens(good).join(',')})`);
    eq(good.cellCount, 200, 'F2 the gate counts the cells once, from the table it was given');

    const cases = [
      ['F3 a geometry-less frame refuses',
       { authorable: brush.authorableSeats(F_NO_GEOMETRY) }, authoring.SAVE_REFUSAL.NO_GEOMETRY],
      ['F4 a screen that did not come from a server read refuses',
       { origin: 'local' }, authoring.SAVE_REFUSAL.NOT_FROM_SERVER],
      ['F5 a truncated read refuses',
       { truncated: true }, authoring.SAVE_REFUSAL.TRUNCATED_READ],
      ['F6 a write aimed anywhere but the pinned floor table refuses',
       { table: 'bonding_map' }, authoring.SAVE_REFUSAL.WRONG_TABLE],
      ['F7 a key that does not split into the declared columns refuses',
       { mapKey: 'DT' }, authoring.SAVE_REFUSAL.KEY_SHAPE],
      ['F8 an empty cell set refuses',
       { cellTable: brush.createCellTable([]) }, authoring.SAVE_REFUSAL.EMPTY],
      ['F9 a geometry change under an existing key refuses',
       { nextMeta: { ...META, rotation: 0 } }, authoring.SAVE_REFUSAL.GEOMETRY_CHANGED],
      ['F10 a y-invert flip is a geometry change',
       { nextMeta: { ...META, grid_y_invert: true } }, authoring.SAVE_REFUSAL.GEOMETRY_CHANGED],
      ['F11 a start shift is a geometry change',
       { nextMeta: { ...META, start_x: 2 } }, authoring.SAVE_REFUSAL.GEOMETRY_CHANGED],
      ['F12 a floor that declares its own floor refuses',
       { nextMeta: { ...META, valid_die_ref: 'OTHER' } }, authoring.SAVE_REFUSAL.SELF_REFERENCE],
      ['F13 a value outside the legend refuses',
       { cellTable: brush.brushStroke(brush.createCellTable([]), authorable,
                                      picked, 'NOPE').table },
       authoring.SAVE_REFUSAL.UNDECLARED_VALUE],
      ['F14 a coordinate the frame cannot express refuses',
       { cellTable: brush.createCellTable([{ x: 99999, y: 99999, value: '1' }]) },
       authoring.SAVE_REFUSAL.UNEXPRESSIBLE_CELL],
      ['F15 a confirmation with no author refuses',
       { confirmedBy: '' }, authoring.SAVE_REFUSAL.NO_AUTHOR],
    ];
    for (const [what, patch, token] of cases) {
      const g = authoring.checkSaveGate({ ...base, ...patch });
      eq(g.ok, false, `${what} (ok flag)`);
      ok(tokens(g).indexOf(token) >= 0, `${what} (token ${token}; got ${tokens(g).join(',')})`);
    }

    // Every refusal is reported, not just the first: an operator told one reason at a time
    // pays for the same screen twice.
    const many = authoring.checkSaveGate({ ...base, origin: 'local', truncated: true,
                                           confirmedBy: '' });
    ok(many.refusals.length >= 3, 'F16 all refusals are reported together, not one at a time');

    // A geometry change is only a refusal against a STORED spec. A brand new floor has none.
    const fresh = authoring.checkSaveGate({ ...base, storedMeta: null, storedCellCount: 0,
                                            nextMeta: { ...META, rotation: 0 } });
    eq(fresh.ok, true, 'F17 a floor with no stored spec is not a geometry change');

    // A refused gate must not be able to produce a body.
    throws(() => authoring.buildSaveRequest(
      authoring.checkSaveGate({ ...base, truncated: true }), base),
      'F18 a refused gate cannot produce a request body');

    const req = authoring.buildSaveRequest(good, base);
    eq(req.cells.body.replace_map, true, 'F19 the cell write is a replace');
    eq(req.cells.body.updates.length, 200, 'F20 every authored cell is in the body');
    eq(req.meta.body.updates.length, 1, 'F21 the spec is written once');
    eq(req.meta.body.updates[0].data.target_table, authoring.FLOOR_TABLE,
       'F22 the spec row is registered against the pinned floor table');
    eq(req.meta.body.updates[0].data.map_id, 'CORE_1X', 'F23 under the canonical key');
    eq(req.cells.body.updates[0].data.product, 'CORE',
       'F24 cell rows carry the key COLUMNS, not the joined string');
    eq(req.cells.body.updates[0].data.type, '1X', 'F25 both of them');
    eq(req.supersedes.cell_count, 854,
       'F26 the request names what it destroys, using the count the screen already had');
    eq(req.writes.meta + req.writes.cells, 2, 'F27 the write is two requests, stated');
    ok(!/\d\s*%/.test(JSON.stringify(req)), 'F28 no percentage anywhere in the request');

    // Arm then commit. Arming is not a write and the sentence names the consequence.
    const idle = authoring.writeIntent(good, { armed: false, mapKey: 'CORE_1X' });
    eq(idle.enabled, true, 'F29 a passing gate enables the control');
    eq(idle.armed, false, 'F30 it does not start armed');
    ok(idle.sentence.indexOf('854') >= 0 && idle.sentence.indexOf('200') >= 0,
       'F31 the confirmation sentence names both counts');
    ok(idle.sentence.indexOf('기준으로 삼는 모든 맵') >= 0,
       'F32 and names who else is affected');
    const armed = authoring.writeIntent(good, { armed: true, mapKey: 'CORE_1X' });
    eq(armed.armed, true, 'F33 arming is a state, not a write');
    eq(armed.label, '다시 눌러 확정', 'F34 the armed label asks for the second press');
    const blocked = authoring.writeIntent(
      authoring.checkSaveGate({ ...base, truncated: true }), { armed: true, mapKey: 'X' });
    eq(blocked.enabled, false, 'F35 a refused gate cannot be armed');
    eq(blocked.armed, false, 'F36 and reports itself unarmed');
    ok(blocked.inertHint !== null, 'F37 and names the first blocking state');
    ok(!/\d\s*%/.test(String(idle.sentence)), 'F38 no percentage in the confirmation sentence');

    // The key shape, measured against the four floors that exist and the seven names that do
    // not resolve (dev box, 2026-08-05).
    for (const k of ['5N_BASE', 'CORE_1X', 'CORE_YINV', 'TEST_TEST']) {
      eq(authoring.decomposeFloorKey(k, FLOOR_KEY_COLUMNS, FLOOR_COLUMN_TYPES).ok, true,
         `F39 a registered floor key decomposes: ${k}`);
    }
    for (const k of ['DT', '4E', 'V1']) {
      eq(authoring.decomposeFloorKey(k, FLOOR_KEY_COLUMNS, FLOOR_COLUMN_TYPES).ok, false,
         `F40 a single-token key cannot be a floor key: ${k}`);
    }
  }

  return { compared, failures };
}

// ── RUN THE BASELINE ────────────────────────────────────────────────────────────
const REAL = Object.freeze({ brush: BRUSH, legend: LEGEND, authoring: AUTHORING });
const base = run(REAL);

console.log(`ASSERTIONS ${base.compared} ${base.failures.length}`);
if (base.failures.length > 0) {
  console.log('\nFAILURES');
  for (const f of base.failures) console.log(`  - ${f}`);
  process.exit(1);
}

// ── G. DEFECT MODELS ────────────────────────────────────────────────────────────
// Each model injects a specific defect into the data path and re-runs the SAME battery. A
// model that cannot be applied STOPS THE RUN: a defect that was never introduced proves
// nothing, and scoring an unapplied model as a kill is how a harness reports coverage it does
// not have. A model that survives fails the run.

function replacing(bundleKey, exportName, make) {
  return (M) => {
    const mod = M[bundleKey];
    if (!mod || typeof mod[exportName] !== 'function') {
      throw new Error(`cannot apply: ${bundleKey}.${exportName} is not an exported function`);
    }
    const patched = Object.assign(Object.create(null), mod);
    patched[exportName] = make(mod[exportName], mod);
    return Object.assign({}, M, { [bundleKey]: patched });
  };
}

const MODELS = [
  ['G1 the box origin term is dropped from the stored coordinate',
   replacing('brush', 'authorableSeats', (real) => (frame) => {
     const a = real(frame);
     if (!a.boxKnown) return a;
     const coords = a.coords.map(c => Object.freeze({ ...c, x: c.x - a.box.minC }));
     const byCell = new Map();
     for (const c of coords) byCell.set(`${c.x},${c.y}`, c);
     return Object.freeze({ ...a, coords: Object.freeze(coords), byCell });
   })],

  ['G2 an off-viewport skip is reintroduced before registration',
   replacing('brush', 'authorableSeats', (real) => (frame) => {
     const a = real(frame);
     if (!a.boxKnown) return a;
     // The legacy I5 defect: "off screen" quietly becomes "not in the data".
     const coords = a.coords.filter(c => c.seatX >= 3 && c.seatY >= 3
                                      && c.seatX <= 35 && c.seatY <= 40);
     const seats = new Map();
     const byCell = new Map();
     for (const c of coords) { seats.set(c.key, c); byCell.set(`${c.x},${c.y}`, c); }
     return Object.freeze({ ...a, coords: Object.freeze(coords), seats, byCell,
                            count: coords.length });
   })],

  ['G3 an identity box is substituted when the frame declares no geometry',
   replacing('brush', 'authorableSeats', (real) => (frame) => {
     const a = real(frame);
     if (a.boxKnown) return a;
     return Object.freeze({ ...a, boxKnown: true, refusal: null,
                            box: Object.freeze({ minC: 0, maxC: 0, minR: 0, maxR: 0 }) });
   })],

  ['G4 the y mirror is skipped, so an invert frame reads as a plain frame',
   replacing('brush', 'authorableSeats', (real) => (frame) => {
     const a = real(Object.freeze({ ...frame, invertY: false }));
     return a;
   })],

  ['G5 the legend invents a colour for an undeclared value',
   replacing('legend', 'colorOf', (real) => (L, v) => real(L, v) || '#888888')],

  ['G6 the legend admits an undeclared value into the vocabulary',
   replacing('legend', 'isDeclaredValue', () => () => true)],

  ['G7 a stroke reports a repaint but does not apply it',
   replacing('brush', 'brushStroke', (real) => (t, a, coords, value) => {
     const out = real(t, a, coords, value);
     if (out.repainted.length === 0) return out;
     return Object.freeze({ ...out, table: t });
   })],

  ['G8 erase writes an empty value instead of removing the row',
   replacing('brush', 'eraseStroke', (real, mod) => (t, coords) => {
     const out = real(t, coords);
     const next = new Map(t.byKey);
     for (const c of out.removed) next.set(mod.cellKey(c.x, c.y), Object.freeze({ ...c, value: '' }));
     return Object.freeze({ ...out, table: Object.freeze({ byKey: next, count: next.size,
                                                           duplicates: t.duplicates }) });
   })],

  ['G9 the gate accepts a truncated read',
   replacing('authoring', 'checkSaveGate', (real, mod) => (input) => {
     const g = real(input);
     const kept = g.refusals.filter(r => r.token !== mod.SAVE_REFUSAL.TRUNCATED_READ);
     return Object.freeze({ ...g, refusals: Object.freeze(kept), ok: kept.length === 0 });
   })],

  ['G10 the gate accepts a geometry change under an existing key',
   replacing('authoring', 'checkSaveGate', (real, mod) => (input) => {
     const g = real(input);
     const kept = g.refusals.filter(r => r.token !== mod.SAVE_REFUSAL.GEOMETRY_CHANGED);
     return Object.freeze({ ...g, refusals: Object.freeze(kept), ok: kept.length === 0 });
   })],

  ['G11 the gate accepts a write that did not come from a server read',
   replacing('authoring', 'checkSaveGate', (real, mod) => (input) => {
     const g = real(input);
     const kept = g.refusals.filter(r => r.token !== mod.SAVE_REFUSAL.NOT_FROM_SERVER);
     return Object.freeze({ ...g, refusals: Object.freeze(kept), ok: kept.length === 0 });
   })],

  ['G12 a refused gate still produces a request body',
   replacing('authoring', 'buildSaveRequest', (real) => (gate, input) => {
     try { return real(gate, input); }
     catch (e) { return real(Object.freeze({ ...gate, ok: true }), input); }
   })],

  ['G13 the request drops the destructive replace flag, so a replace becomes an upsert',
   replacing('authoring', 'buildSaveRequest', (real) => (gate, input) => {
     const r = real(gate, input);
     return Object.freeze({ ...r, cells: Object.freeze({ ...r.cells,
       body: Object.freeze({ ...r.cells.body, replace_map: false }) }) });
   })],

  ['G14 the confirmation sentence loses the count it is replacing',
   replacing('authoring', 'writeIntent', (real) => (gate, opts) => {
     const w = real(gate, opts);
     return Object.freeze({ ...w, sentence: w.sentence === null ? null : '확정하시겠습니까?' });
   })],

  ['CONTROL a wrapper that changes nothing must NOT be caught',
   replacing('brush', 'authorableSeats', (real) => (frame) => real(frame))],
];

console.log('\n  DEFECT MODELS -- a surviving model means the checks above it are inert.\n');
let scored = 0;
for (const [name, apply] of MODELS) {
  const isControl = name.startsWith('CONTROL');
  let mutated;
  try {
    mutated = apply(REAL);
  } catch (e) {
    console.log(`  UNAPPLIED  ${name}`);
    console.log(`            ${e.message}`);
    console.log('\n  An unapplied model is not a caught model. Stopping.');
    process.exit(1);
  }
  let killed;
  let detail = '';
  let out = null;
  try {
    out = run(mutated);
    killed = out.failures.length > 0;
    detail = killed ? `${out.failures.length} failure(s), first: ${out.failures[0]}` : '';
  } catch (e) {
    killed = true;
    detail = `threw: ${String(e && e.message).slice(0, 110)}`;
  }
  // A model that ran fewer assertions than the baseline crashed its way to a verdict rather
  // than being scored. Report it: that is a harness defect, not a caught defect.
  if (out && out.compared < base.compared) {
    detail += ` [WARNING: ran ${out.compared} of ${base.compared} assertions]`;
  }
  if (killed !== isControl) scored++;
  console.log(`  ${killed ? 'CAUGHT  ' : 'SURVIVED'}  ${name}`);
  if (detail) console.log(`            ${detail}`);
}
console.log(`\n  ${scored}/${MODELS.length} scored as intended.`);
process.exit(scored === MODELS.length ? 0 : 1);
