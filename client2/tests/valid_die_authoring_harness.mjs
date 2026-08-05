// M4 phase 2 - valid-die map AUTHORING. INV-1 .. INV-7.
// Run: node client2/tests/valid_die_authoring_harness.mjs [--json] [--mutate]
//
// Same technique as map_key_canonical_harness.mjs / push_gate_harness.mjs: map_editor.js
// imports ./config.js which touches window at module scope, so it cannot be imported in
// node. The functions under test stay module-private; their declarations are sliced out of
// the SOURCE TEXT and evaluated in a vm sandbox with stubs for the module state they read.
//
// FAILS LOUDLY (exit 2) when a function cannot be extracted. A harness that goes green
// because it stopped finding the code is worse than no harness - its green gets cited.
//
// --mutate re-evaluates the sandbox with the DEFECT PUT BACK and asserts this suite goes
// red. A suite that has never been shown to fail proves nothing.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_MAP = join(HERE, '..', 'src', 'map_editor.js');
const JSON_OUT = process.argv.includes('--json');
const MUTATE = process.argv.includes('--mutate');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

function sliceBalanced(src, startIdx, open, close) {
  let i = src.indexOf(open, startIdx);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    const ch = src[j];
    if (ch === open) depth++;
    else if (ch === close) { depth--; if (depth === 0) return src.slice(startIdx, j + 1); }
  }
  return null;
}

const SRC = readFileSync(SRC_MAP, 'utf8');
// The 7b canonicalisation (canonIntString / canonicalKeyValue / composeMapId /
// decomposeMapKey / canonicalMapKey + the two regexes) lives in its own module since the
// map-key extraction round. It is sliced from THERE now; the slices and everything scored
// with them are unchanged. `keyFn` dies just as loudly as `fn` if a name goes missing.
const SRC_KEY_PATH = join(HERE, '..', 'src', 'map_key.js');
const SRC_KEY = readFileSync(SRC_KEY_PATH, 'utf8');

function sliceFn(src, path, name) {
  const m = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} not found in ${path}`);
  const out = sliceBalanced(src, m.index, '{', '}');
  if (!out) die(`unbalanced braces for ${name}`);
  return out;
}
function fn(name) { return sliceFn(SRC, SRC_MAP, name); }
function keyFn(name) { return sliceFn(SRC_KEY, SRC_KEY_PATH, name); }

// ── the fixture: every defect axis ACTIVE ───────────────────────────────────────
// chipX != chipY  (a pitch swap under rot 90/270 shows up)
// rot 90 + back   (rotation and mirror both engaged)
// edgeMargin 1    (NOT 0 - `physNum`'s `|| dflt` turns a declared 0 into 3.0; that is a
//                  PRE-EXISTING defect reported at M4 phase 1 §6-A and deliberately not
//                  exercised here, or this harness would be testing that bug instead)
// bbox minC != 0  (asserted below, so a dropped bbox term cannot hide)
const DIA = 20, EM = 1, CHIP_X = 2, CHIP_Y = 3;
const COLS = 11, ROWS = 9;                       // = applyPhysicalGeometry(DIA, EM, chip)

function inputStub(v) { return { value: String(v) }; }
function makeEl(over = {}) {
  return {
    physWaferDia: inputStub(DIA), physEdgeMargin: inputStub(EM),
    physChipX: inputStub(CHIP_X), physChipY: inputStub(CHIP_Y),
    physOffsetX: inputStub(0), physOffsetY: inputStub(0),
    gridCols: inputStub(COLS), gridRows: inputStub(ROWS),
    gridStartX: inputStub(1), gridStartY: inputStub(1),
    gridYInvert: { checked: false },
    // 2026-08-04: the table <select> is GONE — a valid-die map always lives in
    // `VALID_DIE_TABLE`. The designation now has exactly ONE control, the key box.
    validDieRefKey: inputStub(''),
    ...over,
  };
}

function buildSandbox(mutator) {
  const parts = [
    fn('physNum'), fn('gridDimNum'), fn('withPhysFrame'),
    fn('getScreenShift'), fn('getTransformedPhysicalConfig'),
    fn('getDieIndex'), fn('getCanvasCellFromDb'), fn('getDbCoords'),
    fn('isCellInsideWaferFast'), fn('getWaferBoundingBox'),
    keyFn('canonIntString'), keyFn('canonicalKeyValue'), keyFn('composeMapId'),
    keyFn('decomposeMapKey'), keyFn('canonicalMapKey'),
    fn('parseValidDieRef'), fn('validDieBasis'), fn('isValidDieAt'),
    // M4 phase 2
    fn('buildValidDieTemplate'), fn('validDieRefDisplay'), fn('validDieRefForPush'),
    fn('validDieRefFromControls'), fn('syncValidDieRefControls'), fn('validDieRefPayload'),
    fn('applyValidDieRef'), fn('validDieChainError'),
    // [rule 6] projectCellsToPhys is stated in terms of the mm projection -- both or neither.
    fn('projectCellsToWaferMm'), fn('projectCellsToPhys'), fn('currentFrame'), fn('resolveFrame'),
  ];
  let code = parts.join('\n\n');
  if (mutator) {
    const before = code;
    code = mutator(code);
    // A mutation that does not apply reports "caught" or "missed" about NOTHING. This is the
    // failure mode that makes a mutation suite decorative, so it is fatal.
    if (code === before) die('a mutation did not apply - its target text no longer exists');
  }
  const ctx = {
    console, physFrameOverride: null, currentRotation: 0, currentSide: 'front',
    validDie: null, boundingBoxCache: {}, el: makeEl(),
    CANON_INT_RE: /^[+-]?\d+$/, CANON_FLOAT_RE: /^[+-]?\d+\.0+$/,
    // [1-a] `syncValidDieRefControls` now also decides the key control's SHAPE (<select> when
    // the list is the whole population, text input otherwise). That decision is scored in
    // map_key_datalist_harness.mjs against a real DOM tree; stubbed here so this harness keeps
    // scoring the declaration round-trip and does not quietly become a second DOM model.
    renderValidDieKeyControl() {},
  };
  // The two regexes above are read from the source, not restated, so a change to either
  // reaches this harness instead of being shadowed by a stale copy.
  const reSrc = (name) => {
    const m = new RegExp(`const\\s+${name}\\s*=\\s*(\\/[^\\n]*\\/[a-z]*)\\s*;`).exec(SRC_KEY);
    if (!m) die(`const ${name} (regex) not found in ${SRC_KEY_PATH}`);
    return m[1];
  };
  // The FIXED valid-die storage table. Lifted from the source line, never re-typed: this
  // harness asserts the exact table name a new designation carries, and a copy that drifted
  // would score the WRONG table green — which is precisely the class of defect (the screen is
  // fine, the value points elsewhere) the designation path exists to prevent.
  const validDieTableSrc = (() => {
    const m = /const\s+VALID_DIE_TABLE\s*=\s*('[^']*'|"[^"]*")\s*;/.exec(SRC);
    if (!m) die('const VALID_DIE_TABLE not found in map_editor.js — the fixed storage table is gone or renamed.');
    return m[1];
  })();
  ctx.VALID_DIE_TABLE_EXPECTED = JSON.parse(validDieTableSrc.replace(/'/g, '"'));
  vm.createContext(ctx);
  try {
    vm.runInContext(
      `const CANON_INT_RE = ${reSrc('CANON_INT_RE')};\n`
      + `const CANON_FLOAT_RE = ${reSrc('CANON_FLOAT_RE')};\n`
      + `const VALID_DIE_TABLE = ${validDieTableSrc};\n`
      + code
      + `\nglobalThis.__h = { getDieIndex, getDbCoords, getCanvasCellFromDb,`
      + ` isCellInsideWaferFast, getTransformedPhysicalConfig, getWaferBoundingBox,`
      + ` parseValidDieRef, validDieBasis, isValidDieAt, buildValidDieTemplate,`
      + ` validDieRefDisplay, validDieRefForPush, applyValidDieRef, validDieChainError,`
      + ` syncValidDieRefControls, validDieRefPayload, projectCellsToPhys, canonicalMapKey };`, ctx);
  } catch (e) {
    die(`sandbox evaluation failed - ${e && e.message ? e.message : e}`);
  }
  return { ctx, H: ctx.__h };
}

// ── assertion plumbing ──────────────────────────────────────────────────────────
function newRun() {
  const st = { pass: 0, failures: [] };
  st.check = (inv, name, actual, expected) => {
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a === e) { st.pass++; if (!JSON_OUT && !st.quiet) console.log(`  ok   [${inv}] ${name}`); }
    else {
      st.failures.push({ inv, name, actual, expected });
      if (!JSON_OUT && !st.quiet) console.log(`  FAIL [${inv}] ${name}\n        actual   ${a}\n        expected ${e}`);
    }
  };
  return st;
}

// ════════════════════════════════════════════════════════════════════════════════
// The suite. Written as a function so --mutate can run it against a mutated sandbox
// and assert it goes RED.
// ════════════════════════════════════════════════════════════════════════════════
function runSuite(sb, st) {
  const { ctx, H } = sb;
  const chk = st.check;

  // helper: every (c, r) of the visual rect for the current on-screen rotation
  const visualRect = () => {
    const rot = ctx.currentRotation;
    const vc = (rot === 90 || rot === 270) ? ROWS : COLS;
    const vr = (rot === 90 || rot === 270) ? COLS : ROWS;
    const out = [];
    for (let r = 0; r < vr; r++) for (let c = 0; c < vc; c++) out.push([c, r]);
    return { vc, vr, cells: out };
  };
  const circleKeys = () => {
    const { vc, vr, cells } = visualRect();
    const pc = H.getTransformedPhysicalConfig(null, ctx.currentRotation, ctx.currentSide);
    const s = new Set();
    cells.forEach(([c, r]) => {
      if (H.isCellInsideWaferFast(c, r, vc, vr, pc, 700, 700)) {
        const p = H.getDieIndex(c, r, COLS, ROWS, ctx.currentRotation, ctx.currentSide);
        s.add(`${p.x}_${p.y}`);
      }
    });
    return s;
  };

  // ── fixture self-check: the defect axes really are live ───────────────────────
  ctx.currentRotation = 90; ctx.currentSide = 'back'; ctx.boundingBoxCache = {};
  const box = H.getWaferBoundingBox(90, 'back');
  chk('fixture', 'bbox minC != 0 (a dropped bbox term cannot hide)', box.minC > 0, true);
  chk('fixture', 'chipX != chipY (a pitch swap under rot90 cannot hide)', CHIP_X !== CHIP_Y, true);

  // ════════════════════════════════════════════════════════════════════════════
  // INV-1  A map with NO valid_die_ref behaves exactly as at HEAD.
  //        The new `template` branch must be invisible on the circle path.
  // ════════════════════════════════════════════════════════════════════════════
  const noDecl = { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined };
  chk('INV-1', 'basis with no declaration is circle', H.validDieBasis(noDecl), 'circle');
  chk('INV-1', 'basis of a null state is circle', H.validDieBasis(null), 'circle');
  // pass-through in BOTH directions, including a state carrying stale keys from a previous map
  const stale = { basis: 'circle', keys: new Set(['0_0', '1_1']), reason: '', ref: null, raw: undefined };
  let passThrough = true;
  for (let px = -2; px <= 12; px++) {
    for (const verdict of [true, false]) {
      if (H.isValidDieAt(px, 3, verdict, noDecl) !== verdict) passThrough = false;
      if (H.isValidDieAt(px, 3, verdict, stale) !== verdict) passThrough = false;
    }
  }
  chk('INV-1', 'no declaration -> isValidDieAt is the identity on the circle verdict (60 pairs)',
    passThrough, true);
  // the frame window still suspends every mask, template included
  ctx.physFrameOverride = { cols: COLS, rows: ROWS };
  const tplState = { basis: 'template', keys: new Set(['5_5']), reason: '', ref: null, raw: undefined };
  chk('INV-1', 'frame window suspends the template mask too (a source map is not cut by this map)',
    [H.isValidDieAt(5, 5, false, tplState), H.isValidDieAt(9, 9, true, tplState)], [false, true]);
  ctx.physFrameOverride = null;

  // The basis alphabet reachable FROM METADATA is unchanged: circle | ref | refused.
  // `template` is an authoring state, never a stored declaration - so the seam contract's
  // `valid_die_basis_cases` keep scoring the same three tokens.
  const resolveSrc = fn('resolveValidDie');
  chk('INV-1', "resolveValidDie never produces the `template` basis (metadata cannot reach it)",
    /['"]template['"]/.test(resolveSrc), false);
  chk('INV-1', 'the three metadata-derived tokens still answer as before',
    [H.validDieBasis({ basis: 'ref', keys: new Set(['1_1']) }),
     H.validDieBasis({ basis: 'ref', keys: new Set() }),
     H.validDieBasis({ basis: 'refused', keys: null }),
     H.validDieBasis({ basis: 'circle', keys: null })],
    ['ref', 'refused', 'refused', 'circle']);

  // ════════════════════════════════════════════════════════════════════════════
  // INV-2  A preset-generated template is a SAVABLE map.
  //        "Savable" = every generated cell is `inside`, so pushMapData's cell loop
  //        keeps it and the contrast guard sees dropped == 0.
  // ════════════════════════════════════════════════════════════════════════════
  ctx.currentRotation = 90; ctx.currentSide = 'back'; ctx.boundingBoxCache = {};
  const rect = H.buildValidDieTemplate('rect');
  const circ = H.buildValidDieTemplate('circle');
  const circleSet = circleKeys();

  chk('INV-2', 'rect canvas addresses every cell of the grid', rect.keys.size, COLS * ROWS);
  chk('INV-2', 'rect prefills every cell', rect.filled.length, COLS * ROWS);
  chk('INV-2', 'circle prefill == the circle verdict, key by key',
    [circ.filled.length, circ.filled.every(k => circleSet.has(k)), circleSet.size],
    [circleSet.size, true, circleSet.size]);
  // THE DEFECT AXIS. If this differential is 0 the fixture proves nothing: a template
  // generator that silently returns the circle would pass every other assertion here.
  // 72 is MEASURED, and measured twice: once here and once by an independent oracle
  // written from the spec formula (11x9 grid, R=9, pitch swapped to 3x2 by rot90,
  // all-four-corners rule -> 27 inside). Pinning the number, not just `> 0`, means a
  // fixture that quietly stops exercising the axis fails instead of going green.
  const outside = COLS * ROWS - circleSet.size;
  chk('INV-2', `rect reaches cells the circle refuses (differential = ${outside})`, outside, 72);
  chk('INV-2', 'the authoring canvas is the full grid for BOTH shapes '
    + '(so an existing template can be re-opened and edited, not only created)',
    [rect.keys.size, circ.keys.size], [COLS * ROWS, COLS * ROWS]);

  // A corner the circle refuses: valid under the template mask, invalid without it.
  // Checked in BOTH directions - a one-directional check passes an implementation that
  // ORs the mask with the circle.
  const cornerKey = [...rect.keys].find(k => !circleSet.has(k));
  const [cx, cy] = cornerKey.split('_').map(Number);
  const authoring = { basis: 'template', keys: rect.keys, reason: '', ref: null, raw: undefined };
  chk('INV-2', `corner ${cornerKey}: circle says no, template says yes`,
    [H.isValidDieAt(cx, cy, false, noDecl), H.isValidDieAt(cx, cy, false, authoring)],
    [false, true]);
  const inCircleKey = [...circleSet][0];
  const [ix, iy] = inCircleKey.split('_').map(Number);
  const carved = { basis: 'template', keys: new Set([...rect.keys].filter(k => k !== inCircleKey)),
                   reason: '', ref: null, raw: undefined };
  chk('INV-2', `carving ${inCircleKey} out makes it INVALID even though the circle allows it`,
    [H.isValidDieAt(ix, iy, true, noDecl), H.isValidDieAt(ix, iy, true, carved)],
    [true, false]);

  // ════════════════════════════════════════════════════════════════════════════
  // INV-3  The saved template, read back as a `valid_die_ref`, yields the SAME set.
  //        This is the round trip that matters: author at rot90/back, store the meta,
  //        then resolve it while the screen sits at rot0/front.
  // ════════════════════════════════════════════════════════════════════════════
  const storedMeta = {
    grid_cols: COLS, grid_rows: ROWS, grid_start_x: 1, grid_start_y: 1,
    grid_y_invert: false, rotation: 90, side: 'back',
    phys_wafer_dia: DIA, phys_chip_x: CHIP_X, phys_chip_y: CHIP_Y,
    phys_offset_x: 0, phys_offset_y: 0, phys_edge_margin: EM,
  };
  // What pushMapData would write: visual (x, y) per generated cell, at the AUTHORING frame.
  // Each row also carries the physical key it came FROM, so the comparison below is
  // key -> value per cell, not a set comparison. A set comparison would be satisfied by a
  // permutation - every cell landing on some other cell's coordinate - which is exactly the
  // "screen fine, values wrong" failure this domain produces.
  const authoredCells = [];
  const expectedPhys = new Map();          // "x,y" -> the phys key it was generated from
  {
    const { vc, vr, cells } = visualRect();
    if (vc * vr !== COLS * ROWS) die('visual rect size mismatch in fixture');
    cells.forEach(([c, r]) => {
      const v = H.getDbCoords(c, r, COLS, ROWS, 90, 'back', false, 1, 1);
      const p = H.getDieIndex(c, r, COLS, ROWS, 90, 'back');
      authoredCells.push({ x: v.x, y: v.y, val: `${p.x}_${p.y}` });
      expectedPhys.set(`${v.x},${v.y}`, `${p.x}_${p.y}`);
    });
    chk('INV-3', 'every authored cell has a DISTINCT stored coordinate (no collisions)',
      expectedPhys.size, COLS * ROWS);
  }
  // now the screen is somewhere else entirely
  ctx.currentRotation = 0; ctx.currentSide = 'front'; ctx.boundingBoxCache = {};
  {
    const refFrame = {
      cols: COLS, rows: ROWS, startX: 1, startY: 1, invertY: false,
      rotation: 90, side: 'back',
      waferDia: DIA, chipX: CHIP_X, chipY: CHIP_Y, offsetX: 0, offsetY: 0, edgeMargin: EM,
    };
    // projectCellsToPhys returns Map(physKey -> val); val carries the ORIGINATING phys key,
    // so `k === v` for every entry is the per-cell identity, checked value by value.
    const projected = ctx.projectCellsToPhys(authoredCells, refFrame);
    const wrongPlaced = [...projected.entries()].filter(([k, v]) => k !== v);
    chk('INV-3', 'saved template -> valid_die_ref projection puts every cell back on its own '
      + 'physical coordinate (99 cells, key by key, across a different on-screen frame)',
      [projected.size, wrongPlaced.length], [COLS * ROWS, 0]);
    chk('INV-3', 'and the recovered set is exactly the authored canvas',
      [...rect.keys].every(k => projected.has(k)) && projected.size === rect.keys.size, true);

    // ...and a DELIBERATELY WRONG frame must NOT reproduce it. If this differential were 0
    // the assertion above would be satisfied by any implementation at all. Counted per cell
    // (how many cells land on a coordinate that is not their own), not as a set difference:
    // the set difference is only 18 here because a full rectangle largely maps onto itself -
    // which is precisely why a set-level check is the weak one.
    const wrong = { ...refFrame, rotation: 0 };
    const wrongProj = ctx.projectCellsToPhys(authoredCells, wrong);
    const moved = [...wrongProj.entries()].filter(([k, v]) => k !== v).length;
    const setDiff = [...rect.keys].filter(k => !wrongProj.has(k)).length;
    chk('INV-3', `misreading the frame as rot0 misplaces ${moved} of ${COLS * ROWS} cells `
      + `(set-level difference would only show ${setDiff})`, [moved, setDiff], [98, 18]);
  }

  // ════════════════════════════════════════════════════════════════════════════
  // INV-4  Clearing the designation returns the map to circle geometry.
  //        `validDieRefForPush` is the single decision: what does Push write?
  //        `undefined` means the key is OMITTED from grid_metadata entirely.
  // ════════════════════════════════════════════════════════════════════════════
  // END TO END, not just the decision: the controls decide, `applyValidDieRef` writes, and
  // what comes back is what Push would actually put in `grid_metadata`. `undefined` means
  // the key is absent from the payload.
  const BASE_META = { grid_cols: 6, grid_rows: 6, phys_edge_margin: 0, grid_y_invert: false };
  // 🔴 The controls are built THE WAY THE APP BUILDS THEM: store the raw, then let
  // `syncValidDieRefControls` fill the box. Only after that is the USER's edit applied.
  // Assigning the control value directly would assert a state the app cannot produce - that
  // is exactly how F1 (a declared table silently downgraded to the home table on an untouched
  // Push) shipped 84/84 green.
  //   edit.key - the user typed in the key box (absent = untouched)
  // 2026-08-04: `edit.table` / `edit.tables` are GONE with the <select>. The storage table is
  // fixed, so the ONE thing a user can express is which key - and therefore the ONE thing that
  // separates "the user re-pointed this map" from "the user touched nothing" is that key.
  const forPush = (raw, edit = {}) => {
    ctx.validDie = { basis: 'circle', keys: null, reason: '', ref: null, raw };
    // pre-dirty the box: sync must overwrite it, not inherit it
    ctx.el.validDieRefKey.value = 'STALE_KEY';
    H.syncValidDieRefControls();
    if (edit.key !== undefined) ctx.el.validDieRefKey.value = edit.key;
    const d = H.validDieRefForPush();
    // 🔴 the decision->payload turn is CALLED, never restated. Re-typing those two lines here
    // would score a copy of the implementation, which passes even when the shipped code does
    // something the invariant forbids (the `transfer_log_is_declared_none` lesson).
    const out = H.validDieRefPayload(BASE_META, d, raw);
    // every other key must survive both branches, falsy declarations included
    if (out.grid_cols !== 6 || out.phys_edge_margin !== 0 || out.grid_y_invert !== false) {
      return 'OTHER-KEYS-DAMAGED';
    }
    return ('valid_die_ref' in out) ? out.valid_die_ref : undefined;
  };
  const VDT = ctx.VALID_DIE_TABLE_EXPECTED;      // read from the source, never re-typed
  const REF_CASES = [
    // [name, stored raw, user edits (see forPush), expected written value]
    ['INV-1 byte identity: nothing declared, nothing typed', undefined, {}, undefined],
    ['unchanged string is written back VERBATIM', 'TPL_1', {}, 'TPL_1'],
    ['CLEARED -> the key is omitted (back to circle)', 'TPL_1', { key: '' }, undefined],
    ['unchanged object is written back verbatim',
      { table: 't', map_id: 'K' }, {}, { table: 't', map_id: 'K' }],
    ['the alias spelling survives untouched (no rewriting of a shape we did not author)',
      { target_table: 't', map_key: 'K' }, {}, { target_table: 't', map_key: 'K' }],
    ['an UNREADABLE declaration is preserved, not silently repaired', 5, {}, 5],

    // ── 1-a: the storage table is FIXED, and a NEW designation always carries it ───
    // Every case below whose key the user actually typed must come out naming
    // VALID_DIE_TABLE explicitly. The string (table-inheriting) form is NOT emitted by
    // this UI any more: it would mean "a map in whatever table this map happens to live
    // in", which is the opposite of the ruling.
    ['[1-a] ...but editing an unreadable declaration replaces it, on the FIXED table',
      5, { key: '6' }, { table: VDT, map_id: '6' }],
    ['[1-a] a new designation names the fixed table (never the canvas table by inheritance)',
      undefined, { key: 'NEW' }, { table: VDT, map_id: 'NEW' }],
    ['whitespace-only clears (a blank is not a map key)', 'TPL_1', { key: '   ' }, undefined],

    // ── 1-a: A DECLARATION AUTHORED BEFORE THE RULING IS NOT SILENTLY REPOINTED ────
    // 🔴 THE DEFECT THIS GROUP EXISTS FOR. 8 rows in the live wafer_map_metadata declare a
    // valid-die map in `bonding_map` / `dt_map`. If "the table is fixed" were implemented as
    // "always write VALID_DIE_TABLE", then opening one of those maps and saving it - having
    // touched NOTHING - would repoint it at a different table. If that table carries a map of
    // the same name, a DIFFERENT map silently becomes the valid-die basis and every screen
    // still looks healthy. This is the same shape as F1 (which these cases replace, since the
    // <select> that caused F1 no longer exists) and it is INV-M4-1: an untouched declaration
    // comes out of a save exactly as it went in.
    ['[1-a] a legacy cross-table declaration survives an UNTOUCHED save',
      { table: 'bonding_map', map_id: '4E' }, {}, { table: 'bonding_map', map_id: '4E' }],
    ['[1-a] a legacy BARE-STRING declaration survives an UNTOUCHED save '
      + '(it means "a map in MY table" and re-reading it as a fixed-table key would move it)',
      '4MAIN_DT', {}, '4MAIN_DT'],
    ['[1-a] ...but re-keying a legacy declaration moves it to the fixed table '
      + '(a new choice is a valid_die_ref choice)',
      { table: 'bonding_map', map_id: '4E' }, { key: 'CORE_1X' }, { table: VDT, map_id: 'CORE_1X' }],
    ['[1-a] ...and clearing a legacy declaration still clears',
      { table: 'bonding_map', map_id: '4E' }, { key: '' }, undefined],
    ['[1-a] retyping the SAME key is not an edit (keep, so the stored shape is untouched)',
      { table: 'bonding_map', map_id: '4E' }, { key: '4E' }, { table: 'bonding_map', map_id: '4E' }],
    ['[1-a] a declaration ALREADY on the fixed table is likewise untouched by a no-op save '
      + '(the fixed table is not a licence to rewrite rows that already agree)',
      { table: VDT, map_id: 'CORE_1X' }, {}, { table: VDT, map_id: 'CORE_1X' }],
    ['[1-a] ...and re-keying it stays on the fixed table',
      { table: VDT, map_id: 'CORE_1X' }, { key: 'CORE_YINV' }, { table: VDT, map_id: 'CORE_YINV' }],

    // ── F2: declarations the reader calls a DECLARATION but the UI shows as blank ──
    // `""` is refused forever by the parser and this UI is the only way back. If it
    // reads as `keep`, the `""` is written straight back and the map stays refused.
    ['[F2] a stored "" is reachable by this UI and normalised OUT', '', {}, undefined],
    ['[F2] a stored null likewise', null, {}, undefined],
    ['[F2] an object with a blank key likewise',
      { table: 't', map_id: '' }, {}, undefined],
    ['[F2] ...and typing a key over a "" declares normally, on the fixed table',
      '', { key: 'TPL_9' }, { table: VDT, map_id: 'TPL_9' }],
  ];
  REF_CASES.forEach(([name, raw, edit, exp]) => chk('INV-4', name, forPush(raw, edit), exp));

  // ...and the decision->payload turn on its own, now that it is a function and not two lines
  // inside a DOM-bound one. Extracted at contract-keeper's request (`validDieRefPayload`).
  const PAYLOAD = [
    ['keep + a declaration -> the raw is written back verbatim', { keep: true }, 'TPL_1', 'TPL_1'],
    ['keep + no declaration -> the key stays absent', { keep: true }, undefined, undefined],
    ['keep + a declared "" is still the raw (only the DECISION may drop it)', { keep: true }, '', ''],
    ['changed -> the writer decides', { keep: false, ref: 'X' }, 'TPL_1', 'X'],
    ['cleared -> the key is omitted', { keep: false, ref: null }, 'TPL_1', undefined],
  ];
  PAYLOAD.forEach(([name, d, raw, exp]) => {
    const out = H.validDieRefPayload(BASE_META, d, raw);
    chk('INV-4', `validDieRefPayload: ${name}`,
      ('valid_die_ref' in out) ? out.valid_die_ref : undefined, exp);
  });
  // INV-1 byte identity is an OBJECT IDENTITY claim, not a key-by-key one: a map with no
  // declaration and no edit must hand pushMapData the very object it built, so the serialised
  // payload cannot differ by key order or by a key a rebuild forgot.
  chk('INV-4', 'validDieRefPayload: keep + no declaration returns the metadata object ITSELF',
    H.validDieRefPayload(BASE_META, { keep: true }, undefined) === BASE_META, true);

  // ...and the writer on its own, because the control path cannot reach every shape it must
  // survive: a blank arriving in the OBJECT form, a table-less object, a shape nobody
  // authored. Each of these written through verbatim produces a declaration the reader calls
  // an ERROR — i.e. a map permanently `refused` with no editor left to repair it.
  const wrote = (base, ref) => {
    const out = H.applyValidDieRef(base, ref);
    if (out === base) return 'MUTATED-ITS-ARGUMENT';
    return ('valid_die_ref' in out) ? out.valid_die_ref : undefined;
  };
  const B = { grid_cols: 6, grid_start_x: 0, grid_y_invert: false, phys_edge_margin: 0,
              auto_registered: false, some_future_key: '' };
  const WRITER = [
    ['null clears', null, undefined],
    ['a key string is written as a string', 'TPL_1', 'TPL_1'],
    ['a padded key is trimmed', '  TPL_1  ', 'TPL_1'],
    ['an EMPTY string is a clear, never a stored ""', '', undefined],
    ['a whitespace-only string is a clear', '   ', undefined],
    ['an object with a table is written as an object',
      { table: 'tpl_table', map_id: 'TPL_1' }, { table: 'tpl_table', map_id: 'TPL_1' }],
    ['the alias spelling is accepted on input',
      { target_table: 'tpl_table', map_key: 'TPL_1' }, { table: 'tpl_table', map_id: 'TPL_1' }],
    ['an object with a BLANK key is a clear (a table picked, no map chosen)',
      { table: 'tpl_table', map_id: '  ' }, undefined],
    ['a TABLELESS object is never emitted - it becomes the string form',
      { table: '', map_id: 'TPL_1' }, 'TPL_1'],
    ['...same when the table key is simply absent', { map_id: 'TPL_1' }, 'TPL_1'],
    ['a shape nobody authored is not stored', 5, undefined],
  ];
  WRITER.forEach(([name, ref, exp]) => chk('INV-4', `applyValidDieRef: ${name}`, wrote(B, ref), exp));
  // every other key survives, declared falsies first (a `v || dflt` rebuild turns
  // phys_edge_margin 0 into 3.0 and MOVES the wafer mask of a map that was only being cleared)
  const strip = (m) => { const o = { ...m }; delete o.valid_die_ref; return o; };
  chk('INV-4', 'applyValidDieRef preserves every other key including declared falsies',
    [strip(H.applyValidDieRef(B, 'TPL_1')), strip(H.applyValidDieRef({ ...B, valid_die_ref: 'X' }, null))],
    [B, B]);
  // and it does not mutate its argument (a mutating writer breaks the cancel path)
  const argCopy = { ...B, valid_die_ref: 'OLD' };
  H.applyValidDieRef(argCopy, 'NEW');
  H.applyValidDieRef(argCopy, null);
  chk('INV-4', 'applyValidDieRef does not mutate its argument', argCopy, { ...B, valid_die_ref: 'OLD' });
  // idempotent in the last operation - a clear that leaves debris only shows on the 2nd apply
  chk('INV-4', 'clear is idempotent',
    H.applyValidDieRef(H.applyValidDieRef({ ...B, valid_die_ref: 'X' }, null), null), B);

  // ════════════════════════════════════════════════════════════════════════════
  // INV-5  Unreadable -> refused with a reason. Never a silent circle fallback.
  // ════════════════════════════════════════════════════════════════════════════
  // [1-a 2026-08-04] THE LOAD PIN, updated deliberately and not to make a red go green.
  // Phase 1 read a bare string as "a map in MY table" and this row asserted `seam_map`. The
  // user ruled that loading is fixed — "불러오기는 무조건 valid_die_ref 를 이용하게" — so the
  // resolved table is now the FIXED one on every readable declaration, and the table the
  // declaration used to mean is carried alongside as `declaredTable` (the refusal message
  // needs it: "the key is wrong" and "the key is fine but not in this table" are different
  // repairs). The expectation is built from the constant EXTRACTED from the source, never
  // re-typed — a literal here that drifted would score the wrong table green.
  const PARSE = [
    [{}, 'seam_map', null],
    [{ valid_die_ref: null }, 'seam_map', null],
    [{ valid_die_ref: 'TPL_1' }, 'seam_map',
      { table: ctx.VALID_DIE_TABLE_EXPECTED, mapKey: 'TPL_1', declaredTable: 'seam_map' }],
    [{ valid_die_ref: '' }, 'seam_map', 'unreadable'],
    [{ valid_die_ref: 5 }, 'seam_map', 'unreadable'],
    [{ valid_die_ref: ['t', 'k'] }, 'seam_map', 'unreadable'],
  ];
  PARSE.forEach(([meta, home, exp]) => {
    const got = H.parseValidDieRef(meta, home);
    const norm = got === null ? null : (got.unreadable ? 'unreadable' : got);
    chk('INV-5', `parseValidDieRef(${JSON.stringify(meta)}) (unchanged from phase 1)`, norm, exp);
    if (exp === 'unreadable') {
      chk('INV-5', `  ...and carries a non-empty reason`, !!(got && got.reason && got.reason.length > 0), true);
    }
  });

  // ════════════════════════════════════════════════════════════════════════════
  // INV-6  The reference chain is ONE STEP. A valid-die map that itself declares a
  //        valid_die_ref is refused - self-reference and cycles included.
  // ════════════════════════════════════════════════════════════════════════════
  const HOME = { table: 'seam_map', mapKey: 'LOT_1' };
  const REF = { table: 'seam_map', mapKey: 'TPL_1' };
  const CHAIN = [
    // [name, ref, refMeta, expected]
    ['a plain one-hop reference is legal (without this, "refuse everything" passes)',
      REF, { grid_cols: 6, grid_rows: 6 }, null],
    ['an unknown ref meta is NOT a chain error (that failure is reported upstream)',
      REF, null, null],
    ['explicit null is absence at every level', REF, { valid_die_ref: null }, null],
    ['a two-level chain is refused', REF, { valid_die_ref: 'TPL_2' }, 'chain'],
    ['a two-cycle needs no cycle detector — B declared, so A refuses',
      REF, { valid_die_ref: 'LOT_1' }, 'chain'],
    ['a BROKEN second-level declaration is still a chain', REF, { valid_die_ref: '' }, 'chain'],
    ['a declared 0 is a declaration (a falsy test gets this wrong)',
      REF, { valid_die_ref: 0 }, 'chain'],
    ['a declared false is a declaration', REF, { valid_die_ref: false }, 'chain'],
    ['self-reference is refused', { table: 'seam_map', mapKey: 'LOT_1' },
      { grid_cols: 6, grid_rows: 6 }, 'self'],
    ['the same key in ANOTHER table is not self (identity is the pair)',
      { table: 'tpl_table', mapKey: 'LOT_1' }, { grid_cols: 6 }, null],
    ['another key in the SAME table is not self',
      { table: 'seam_map', mapKey: 'LOT_2' }, { grid_cols: 6 }, null],
  ];
  const chainReasons = { chain: new Set(), self: new Set() };
  CHAIN.forEach(([name, ref, refMeta, exp]) => {
    const r = H.validDieChainError(ref, refMeta, HOME);
    chk('INV-6', name, r === null || r === undefined ? null : 'refused', exp === null ? null : 'refused');
    if (exp !== null) {
      chk('INV-6', `  ...with a stated reason`, typeof r === 'string' && r.trim().length > 10, true);
      chainReasons[exp].add(r);
    }
  });
  // The two refusals are different problems with different fixes (re-point the reference vs
  // flatten the template). One shared string would make them indistinguishable to the user.
  chk('INV-6', 'the two refusal kinds do not share a reason',
    [...chainReasons.self].filter(r => chainReasons.chain.has(r)), []);
  // INV-7 reuse, BOTH polarities: same declared text, same home key, opposite answers, and
  // the only difference is the declared column type. A guard with its own normalisation
  // fails the second one.
  const KC = ['lot', 'slot'];
  const canonRef = (types) => ({
    table: 'seam_map', mapKey: H.canonicalMapKey(KC, 'LOT_01', types),
  });
  chk('INV-6', "'LOT_01' under slot:number IS the home identity -> self-reference",
    H.validDieChainError(canonRef({ lot: 'string', slot: 'number' }),
      { grid_cols: 6 }, HOME) !== null, true);
  chk('INV-6', "'LOT_01' under slot:string is NOT the home identity -> perfectly legal",
    H.validDieChainError(canonRef({ lot: 'string', slot: 'string' }),
      { grid_cols: 6 }, HOME), null);
  // and the check is reached BEFORE the cells are trusted
  chk('INV-6', 'resolveValidDie runs the chain check before projecting the cells',
    resolveSrc.indexOf('validDieChainError') > 0
    && resolveSrc.indexOf('validDieChainError') < resolveSrc.indexOf('projectCellsToPhys'), true);

  // ════════════════════════════════════════════════════════════════════════════
  // INV-7  ONE canonicaliser. The designation path must not grow a second one.
  // ════════════════════════════════════════════════════════════════════════════
  chk('INV-7', 'resolveValidDie still canonicalises the declared key through canonicalMapKey',
    /canonicalMapKey\s*\(/.test(resolveSrc), true);
  // The designation control trims and nothing else - canonicalisation happens exactly once,
  // at resolve time, through 7b. A second normaliser here would turn '01' into '1' and the
  // two spellings would stop being the same map at different moments.
  chk('INV-7', "the ref control trims but does NOT canonicalise ('01' stays '01')",
    forPush(undefined, { key: '  TPL_01  ' }),
    { table: ctx.VALID_DIE_TABLE_EXPECTED, map_id: 'TPL_01' });
  chk('INV-7', 'validDieRefForPush contains no canonicalisation of its own',
    /canonical/i.test(fn('validDieRefForPush')), false);

  // display is the exact inverse of the compose above - checked key -> value, because a
  // round trip through a defective pair passes on its own.
  const DISPLAY = [
    [undefined, { table: '', key: '' }],
    [null, { table: '', key: '' }],
    ['TPL_1', { table: '', key: 'TPL_1' }],
    [{ table: 't', map_id: 'K' }, { table: 't', key: 'K' }],
    [{ target_table: 't', map_key: 'K' }, { table: 't', key: 'K' }],
    [{ map_id: 'K' }, { table: '', key: 'K' }],
    [5, { table: '', key: '5' }],
    [['t', 'k'], { table: '', key: '["t","k"]' }],
  ];
  DISPLAY.forEach(([raw, exp]) =>
    chk('INV-7', `validDieRefDisplay(${JSON.stringify(raw)})`, H.validDieRefDisplay(raw), exp));
}

// ── run ─────────────────────────────────────────────────────────────────────────
const sb = buildSandbox(null);
// projectCellsToPhys / currentFrame / resolveFrame live in the sandbox scope; expose the
// context so the suite can call them with the module state it just set.
sb.ctx.projectCellsToPhys = vm.runInContext('projectCellsToPhys', sb.ctx);

if (!JSON_OUT) console.log('\n=== M4 phase 2 - valid-die authoring ===\n');
const main = newRun();
runSuite(sb, main);

// ── mutation check: put each defect BACK and require this suite to go red ────────
const MUTATIONS = [
  ['M1 template mask ignored in isValidDieAt (the branch that makes a rect savable)',
    s => s.replace("if (b !== 'ref' && b !== 'template') return circleInside;",
                   "if (b !== 'ref') return circleInside;")],
  ['M2 push always rewrites from the controls (an unreadable declaration is silently repaired)',
    s => s.replace('if (curTable === shown.table && curKey === shown.key) return { keep: true };',
                   '')],
  ['M3 push always keeps the stored raw (clearing the field stops working = INV-4 dies)',
    s => s.replace(/function validDieRefForPush\(\) \{/,
                   'function validDieRefForPush() { return { keep: true };')],
  ['M4 chain check folded into "allowed" (INV-6 gone)',
    s => s.replace(/function validDieChainError\(([^)]*)\) \{/,
                   'function validDieChainError($1) { return null;')],
  ['M7 the chain guard uses a FALSY test (declared 0 / false / "" fold into absence)',
    s => s.replace("if (inner === null || inner === undefined) return null;",
                   'if (!inner) return null;')],
  ['M8 the chain guard compares keys only (every cross-table reference reads as self)',
    s => s.replace('String(r.table) === String(h.table) && String(r.mapKey) === String(h.mapKey)',
                   'String(r.mapKey) === String(h.mapKey)')],
  ['M12 the chain guard compares tables only (every same-table reference reads as self)',
    s => s.replace('String(r.table) === String(h.table) && String(r.mapKey) === String(h.mapKey)',
                   'String(r.table) === String(h.table)')],
  ['M13 the chain guard normalises on its own (INV-7: a second canonicaliser)',
    s => s.replace('String(r.mapKey) === String(h.mapKey)',
                   'String(r.mapKey).replace(/0+(\\d)/g, "$1") === String(h.mapKey)')],
  ['M9 the writer pipes a blank key straight through (permanent `refused`, no way back)',
    s => s.replace("    return k === '' ? clear() : (out.valid_die_ref = k, out);",
                   '    out.valid_die_ref = k; return out;')],
  ['M10 the writer rebuilds instead of copying (declared falsies destroyed)',
    s => s.replace('const out = { ...(meta && typeof meta === \'object\' ? meta : {}) };',
                   'const out = {}; Object.entries(meta || {}).forEach(([k2, v2]) => { out[k2] = v2 || undefined; });')],
  ['M11 the writer emits a tableless object (the one recorded client/server divergence)',
    s => s.replace("out.valid_die_ref = (table === '') ? k : { table, map_id: k };",
                   'out.valid_die_ref = { table, map_id: k };')],
  ['M5 rect template silently returns the circle (the generator that proves nothing)',
    s => s.replace("const wanted = (shape === 'circle') ? circleInside : true;",
                   'const wanted = circleInside;')],
  // ── the three defects this round fixed, put back one at a time ─────────────────
  // M14/M15 retired 2026-08-04 with the <select> they described. Their invariant did not
  // retire — it moved onto the key comparison, and M20/M21 below are the same two failures
  // expressed against the control that survived.
  ['M20 [1-a] "the table is fixed" implemented as "always write the fixed table" '
    + '(an untouched legacy declaration is silently repointed at another table)',
    s => s.replace('const table = (key === shown.key) ? shown.table : VALID_DIE_TABLE;',
                   'const table = VALID_DIE_TABLE;')],
  ['M21 [1-a] a new designation inherits the canvas table again '
    + '(the string form comes back and the fixed table stops being fixed)',
    s => s.replace('const table = (key === shown.key) ? shown.table : VALID_DIE_TABLE;',
                   'const table = shown.table;')],
  ['M16 [F2] a declaration that displays as blank reads as `keep` '
    + '(a stored "" is written straight back = permanently refused, no way out)',
    s => s.replace(/if \(raw !== undefined && shown\.key === '' && curKey === ''\) return \{ keep: false, ref: null \};/,
                   '')],
  ['M17 the payload drops the declaration on a KEPT push '
    + '(saving a map once deletes its valid_die_ref)',
    s => s.replace("return (raw !== undefined) ? { ...gridMeta, valid_die_ref: raw } : gridMeta;",
                   'return gridMeta;')],
  ['M18 the payload ignores the decision and always keeps (clearing stops working)',
    s => s.replace('if (decision && decision.keep) {', 'if (decision) {')],
  ['M19 the payload rebuilds the metadata instead of handing back the object '
    + '(INV-1 byte identity becomes "we retyped the same keys")',
    s => s.replace('? { ...gridMeta, valid_die_ref: raw } : gridMeta;',
                   '? { ...gridMeta, valid_die_ref: raw } : { ...gridMeta };')],
  ['M6 the authoring basis leaks into the metadata alphabet',
    s => s.replace("if (v.basis === 'ref' || v.basis === 'template') {",
                   "if (v.basis === 'ref' || v.basis === 'template' || v.basis === 'circle') {")],
];

let mutCaught = 0, mutMissed = [];
if (MUTATE || true) {
  MUTATIONS.forEach(([name, mut]) => {
    let sbm;
    try { sbm = buildSandbox(mut); } catch (e) { mutCaught++; return; }
    sbm.ctx.projectCellsToPhys = vm.runInContext('projectCellsToPhys', sbm.ctx);
    const st = newRun();
    st.quiet = true;
    let threw = false;
    try { runSuite(sbm, st); } catch (e) { threw = true; }
    if (st.failures.length > 0 || threw) mutCaught++;
    else mutMissed.push(name);
  });
}

const result = {
  passed: main.pass, failed: main.failures.length, failures: main.failures,
  mutations: { total: MUTATIONS.length, caught: mutCaught, missed: mutMissed },
};
if (JSON_OUT) console.log(JSON.stringify(result, null, 2));
else {
  console.log(`\n--- ${main.pass} passed, ${main.failures.length} failed ---`);
  console.log(`--- mutation check: ${mutCaught}/${MUTATIONS.length} defects caught ---`);
  mutMissed.forEach(m => console.log(`    MISSED: ${m}`));
  // H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
  console.log(`ASSERTIONS ${main.pass + main.failures.length} ${main.failures.length}`);
}
process.exit((main.failures.length === 0 && mutMissed.length === 0) ? 0 : 1);
