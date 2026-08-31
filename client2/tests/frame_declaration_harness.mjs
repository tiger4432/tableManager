/**
 * FRAME AS A VALUE -- scores `client2/src/map2/declaration.js` (MAP_ALIGNMENT_SPEC 0.3 step 1).
 *
 * 🔴 THIS HARNESS DOES NOT SLICE SOURCE. It `import`s the module under test. There is no
 *    `node:vm`, no `sliceFunction`, and no `readFileSync` of any `.js` on the baseline path.
 *    That is the point of the file, not an incidental style choice: nearly every other client
 *    harness reads source with `readFileSync` and evaluates it in `node:vm`, and most slice
 *    `map_editor.js` specifically. (No count here -- a census in a comment goes stale the
 *    moment somebody adds a file. It belongs in a dated report.) `map_editor.js:1826-1828`
 *    records what that costs -- one new module global killed three harnesses in a round, and
 *    `loadExistingMap`'s catch reported the wreckage to the operator as "0 cells loaded".
 *    Text-slicing gives the test technique a veto over the source layout. This harness is the
 *    first client harness that does not hand over that veto.
 *
 *    (`--mutate` DOES read the module's own text, to build in-memory variants imported as
 *    data: URIs. That is a deliberate, separate path -- it never edits a file on disk, and
 *    the baseline verdict above it is computed without touching the filesystem for source.)
 *
 * WHAT IS SCORED
 *
 *  A. PARITY WITH THE SHIPPED CODE. The six functions that answer "what frame are we on"
 *     today are transcribed below as pure functions -- transcribed, NOT imported and NOT
 *     derived from the module under test, the same discipline `offset_pitch_guard_harness`
 *     applies to the server's phys table. Every production frame shape is pushed through both
 *     and compared field by field. `frame.legacy` must equal the shipped answer on every
 *     field the shipped function actually computes.
 *
 *     Transcription fidelity is not asserted here -- it cannot be, by construction. It was
 *     proven once against the REAL sliced functions running in a vm with a DOM stub, on all
 *     668 rows / 3366 field comparisons, 0 divergences (S1A report, 2026-08-05).
 *
 *  B. PROVENANCE. Every axis reports one of the FIVE tokens -- the four shared with
 *     `map_overlay.py:314-317` plus `indeterminate` (`map_overlay.py:420`). This is the axis
 *     that did not exist: `_rotation_of` (map_overlay.py:235-239) and `frameFromMeta:8459`
 *     both answer 0 whether the key was missing, unreadable, defaulted by a generator, or
 *     chosen by a person. B2 scores the tainting rule and its anti-drift device.
 *
 *  C. PURITY AND FREEZE. No DOM globals are defined in this process; if the module reached
 *     for one it would throw. Every returned record is frozen.
 *
 * FIXTURES -- TWO SETS, NEVER MIXED. Confusing the two is a documented failure in this
 * project ("a fixture I authored is not evidence about production").
 *   PRODUCTION: `fixtures/prod_frame_metas.json` -- 66 distinct shapes covering all 668 rows
 *     of `wafer_map_metadata`, pulled read-only. Axis liveness, measured, in ROWS:
 *       chipX != chipY 36 | rot 90/270 52 | rot 180 100 | side back 55 | y_invert 2
 *       startX != 0 265 | startX != startY 52 | cols != rows 94 | offsetX != 0 14
 *       auto_registered 320
 *     Every axis is live, so an axis swap, a dropped rotation term, a dropped side term or a
 *     dropped marker cannot pass unnoticed. (Mutation section below measures that claim
 *     instead of asserting it.)
 *   SYNTHETIC: `SYNTHETIC` below. These exist because production CANNOT exercise them --
 *     measured: all 668 rows carry all 13 keys with correct types, so `absent` and
 *     `unparsable` have extension 0 in `wafer_map_metadata` today. Their extension is not
 *     zero in the code: `map_overlay._meta_of:227` returns None for an unregistered map or a
 *     failed query, and every `_*_of` helper below it then substitutes silently.
 *
 * Run:  node client2/tests/frame_declaration_harness.mjs [--mutate] [--verbose]
 * Read-only. Exit: 0 green | 1 a check failed | 2 harness failure.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

// NAMESPACE import, so `run(mod)` sees exactly the same surface for the live module and for
// an in-memory mutant. Hand-listing the surface here once caused a silent gap: a symbol added
// to the module but not to the list was exercised on mutants and undefined on the live run.
import * as LIVE from '../src/map2/declaration.js';
const { DECLARED, AUTO_REGISTERED, ABSENT, UNPARSABLE, INDETERMINATE } = LIVE;

const HERE = dirname(fileURLToPath(import.meta.url));
const MODULE_PATH = join(HERE, '..', 'src', 'map2', 'declaration.js');
const FIXTURE_PATH = join(HERE, 'fixtures', 'prod_frame_metas.json');

const die = (m) => {
  console.error(`HARNESS FAILURE: ${m}\n(Nothing was compared.)`);
  process.exit(2);
};

let PROD;
try {
  PROD = JSON.parse(readFileSync(FIXTURE_PATH, 'utf8').replace(/\r\n/g, '\n'));
} catch (e) {
  die(`cannot read the production fixture at ${FIXTURE_PATH}: ${e.message}`);
}
if (!PROD || !Array.isArray(PROD.shapes) || PROD.shapes.length === 0) {
  die('production fixture holds no shapes -- an empty fixture is not a passing run');
}

// ═══════════════════════════════════════════════════════════════════════════════
// THE ORACLES. Transcribed from map_editor.js at the line numbers given. They take a plain
// meta and a DOM-round-trip model instead of a DOM, because the shipped functions read
// controls that the loader has already filled from the meta.
//
// 🔴 THE DOM ROUND TRIP IS ITSELF LOSSY AND THAT IS MODELLED, NOT HIDDEN. A text input holds
//    a string and a checkbox holds a boolean, so `absent` and `unparsable` cannot survive the
//    trip: `String(undefined)` is `"undefined"`, which `parseInt` rejects, which `|| 10`
//    turns into 10. The oracles below reproduce that faithfully; the module reports the truth
//    the panel destroyed. Where the two differ on a SYNTHETIC row, that difference is the
//    finding, and it is asserted as such rather than smoothed over.
// ═══════════════════════════════════════════════════════════════════════════════

/** The DOM the loader would have produced from this meta (values are strings, as in HTML). */
function domFromMeta(meta) {
  const s = (v) => String(v);
  return {
    gridCols: s(meta.grid_cols), gridRows: s(meta.grid_rows),
    gridStartX: s(meta.grid_start_x), gridStartY: s(meta.grid_start_y),
    gridYInvert: !!meta.grid_y_invert,
    // module globals, not controls
    currentRotation: Number(meta.rotation) || 0,
    currentSide: meta.side === 'back' ? 'back' : 'front',
    physWaferDia: s(meta.phys_wafer_dia), physChipX: s(meta.phys_chip_x),
    physChipY: s(meta.phys_chip_y), physOffsetX: s(meta.phys_offset_x),
    physOffsetY: s(meta.phys_offset_y), physEdgeMargin: s(meta.phys_edge_margin),
    autoRegistered: meta.auto_registered === true,
  };
}

const pInt = (raw, d) => (parseInt(raw, 10) || d);       // map_editor.js:6262 etc
const pFloat = (raw, d) => (parseFloat(raw) || d);       // map_editor.js:1435-1442 physNum

/** map_editor.js:1932 seatingSnapshot -- 13 axes (the `box` field is layer 2, not scored). */
function O_seatingSnapshot(dom) {
  return {
    cols: pInt(dom.gridCols, 10), rows: pInt(dom.gridRows, 10),
    rotation: dom.currentRotation, side: dom.currentSide,
    invertY: !!dom.gridYInvert,
    startX: pInt(dom.gridStartX, 0), startY: pInt(dom.gridStartY, 0),
    waferDia: pFloat(dom.physWaferDia, 300),
    chipX: pFloat(dom.physChipX, 2.5), chipY: pFloat(dom.physChipY, 2.5),
    offsetX: pFloat(dom.physOffsetX, 0.0), offsetY: pFloat(dom.physOffsetY, 0.0),
    edgeMargin: pFloat(dom.physEdgeMargin, 3.0),
  };
}

/**
 * map_editor.js `readGridFrameControls` -- 5 axes. NO rotation, NO side (finding D2).
 *
 * 🔴 THIS TRANSCRIPTION WAS NOT EDITED WHEN THE PRODUCT'S READER GREW A REFUSAL (2026-08-05),
 *    AND THAT IS THE POINT. `readGridFrameControls` now also reports `silent` -- the boxes that
 *    said nothing -- so that `parseInt('') || 0` stops promoting silence to a declared 0. The
 *    lenient fold transcribed below is UNCHANGED for every box that is not blank, which is what
 *    `declaration.js` deliberately preserves as `legacy` ("legacy DOES NOT GET STRICTER").
 *
 *    Editing this oracle to match a change in the thing it scores would be a repaired mutation:
 *    it would turn the parity check green by moving the check. So the honest question is whether
 *    the transcription still independently expresses what map2 believes over the inputs it is
 *    scored on -- and section F below MEASURES that instead of asserting it. The answer is that
 *    the refusal branch has extension ZERO here: a DOM round trip cannot produce a blank string
 *    (`String(undefined)` is `"undefined"`), so no shape this harness scores can reach it.
 */
function O_readGridFrameControls(dom) {
  return {
    cols: pInt(dom.gridCols, 10), rows: pInt(dom.gridRows, 10),
    startX: pInt(dom.gridStartX, 0), startY: pInt(dom.gridStartY, 0),
    invertY: dom.gridYInvert,
  };
}

/** map_editor.js:6418 getVisualGridDimensions -- reads the module global `currentRotation`. */
function O_getVisualGridDimensions(dom) {
  const cols = pInt(dom.gridCols, 10);
  const rows = pInt(dom.gridRows, 10);
  const q = (dom.currentRotation === 90 || dom.currentRotation === 270);
  return { visualCols: q ? rows : cols, visualRows: q ? cols : rows };
}

/** map_editor.js:7583 currentCoordFrame -- 7 axes + the visual pair. */
function O_currentCoordFrame(dom) {
  const v = O_getVisualGridDimensions(dom);
  return {
    cols: pInt(dom.gridCols, 10), rows: pInt(dom.gridRows, 10),
    rotation: dom.currentRotation, side: dom.currentSide,
    invertY: !!dom.gridYInvert,
    startX: pInt(dom.gridStartX, 0), startY: pInt(dom.gridStartY, 0),
    visualCols: v.visualCols, visualRows: v.visualRows,
  };
}

/** map_editor.js:8515 currentFrame -- 7 axes, no phys, no visual pair. */
function O_currentFrame(dom) {
  return {
    cols: pInt(dom.gridCols, 10), rows: pInt(dom.gridRows, 10),
    startX: pInt(dom.gridStartX, 0), startY: pInt(dom.gridStartY, 0),
    invertY: !!dom.gridYInvert,
    rotation: dom.currentRotation, side: dom.currentSide,
  };
}

/** map_editor.js:10486 currentGeomSignature -- RAW STRINGS joined by `|` (finding D5). */
function O_currentGeomSignature(dom) {
  return [
    dom.gridCols, dom.gridRows, dom.gridStartX, dom.gridStartY,
    dom.gridYInvert ? 1 : 0, dom.currentRotation, dom.currentSide,
    dom.physWaferDia, dom.physChipX, dom.physChipY,
    dom.physOffsetX, dom.physOffsetY, dom.physEdgeMargin,
  ].join('|');
}

// ═══════════════════════════════════════════════════════════════════════════════
// SYNTHETIC FIXTURES -- authored here, and NEVER counted as evidence about production.
// Each exists because production has extension 0 on the state it activates.
// ═══════════════════════════════════════════════════════════════════════════════
const FULL = {
  grid_cols: 45, grid_rows: 39, grid_start_x: 3, grid_start_y: 5,
  grid_y_invert: false, rotation: 90, side: 'back',
  phys_wafer_dia: 300, phys_chip_x: 11, phys_chip_y: 13,
  phys_offset_x: 5, phys_offset_y: 5, phys_edge_margin: 3,
};
const without = (...keys) => {
  const o = { ...FULL };
  for (const k of keys) delete o[k];
  return o;
};
const withKey = (k, v) => ({ ...FULL, [k]: v });

const marked = (o) => ({ ...o, auto_registered: true });

const SYNTHETIC = [
  { id: 'rot_absent', meta: without('rotation'), axis: 'rotation', want: ABSENT, value: 0 },
  { id: 'rot_unparsable', meta: withKey('rotation', 'ninety'), axis: 'rotation', want: UNPARSABLE, value: 0 },
  // THE FIFTH TOKEN. A stored 0 equals what the reader invents, so it is not evidence that
  // anyone chose 0 -- and no marker says who put it there.
  { id: 'rot_stored_zero_unmarked', meta: withKey('rotation', 0), axis: 'rotation', want: INDETERMINATE, value: 0 },
  { id: 'rot_stored_ninety', meta: withKey('rotation', 90), axis: 'rotation', want: DECLARED, value: 90 },
  // The marker explains a registrar CONSTANT ...
  { id: 'rot_marked_zero', meta: marked(withKey('rotation', 0)), axis: 'rotation', want: AUTO_REGISTERED, value: 0 },
  // ... but cannot explain a value the registrar never writes: the editor inherited the
  // marker and turned the map (map_editor.js:6292). Answering auto_registered here is a lie.
  { id: 'rot_marked_ninety', meta: marked(withKey('rotation', 90)), axis: 'rotation', want: DECLARED, value: 90 },
  { id: 'side_absent', meta: without('side'), axis: 'side', want: ABSENT, value: 'front' },
  { id: 'side_unparsable', meta: withKey('side', 'BACK'), axis: 'side', want: UNPARSABLE, value: 'front' },
  { id: 'side_stored_front', meta: withKey('side', 'front'), axis: 'side', want: INDETERMINATE, value: 'front' },
  { id: 'side_stored_back', meta: withKey('side', 'back'), axis: 'side', want: DECLARED, value: 'back' },
  { id: 'side_marked_back', meta: marked(withKey('side', 'back')), axis: 'side', want: DECLARED, value: 'back' },
  { id: 'startx_absent', meta: without('grid_start_x'), axis: 'startX', want: ABSENT, value: 0 },
  // START IS MARKER-ONLY (lead PM ruling 2026-08-05): the registrar writes the observed
  // minimum, not a constant, so no value test can identify it -- and 0 of 668 production rows
  // lack the key, so the "what would a reader have invented" inference has no premise here.
  { id: 'startx_stored_zero', meta: withKey('grid_start_x', 0), axis: 'startX', want: DECLARED, value: 0 },
  { id: 'startx_stored_three', meta: withKey('grid_start_x', 3), axis: 'startX', want: DECLARED, value: 3 },
  // START IS THE EXCEPTION: the registrar writes the OBSERVED MINIMUM, so on a marked map any
  // integer is still the registrar's bbox scan, not a person's choice.
  { id: 'startx_marked_37', meta: marked(withKey('grid_start_x', 37)), axis: 'startX', want: AUTO_REGISTERED, value: 37 },
  { id: 'cols_absent', meta: without('grid_cols'), axis: 'cols', want: ABSENT, value: 10 },
  { id: 'cols_unparsable', meta: withKey('grid_cols', 'many'), axis: 'cols', want: UNPARSABLE, value: 10 },
  { id: 'cols_declared_zero', meta: withKey('grid_cols', 0), axis: 'cols', want: DECLARED, value: 0 },
  { id: 'invert_absent', meta: without('grid_y_invert'), axis: 'invertY', want: ABSENT, value: false },
  // A STRING IS NOT A BOOLEAN. Both spellings were `declared` until the parse-direction fix;
  // `'true'` in particular had the client applying the y mirror while the server did not.
  { id: 'invert_string_false', meta: withKey('grid_y_invert', 'false'), axis: 'invertY', want: UNPARSABLE, value: false },
  { id: 'invert_string_true', meta: withKey('grid_y_invert', 'true'), axis: 'invertY', want: UNPARSABLE, value: false },
  { id: 'invert_one', meta: withKey('grid_y_invert', 1), axis: 'invertY', want: DECLARED, value: true },
  // ── NORMALISE OR REFUSE: rotation ──
  { id: 'rot_negative_ninety', meta: withKey('rotation', -90), axis: 'rotation', want: DECLARED, value: 270 },
  { id: 'rot_three_sixty', meta: withKey('rotation', 360), axis: 'rotation', want: INDETERMINATE, value: 0 },
  { id: 'rot_forty_five', meta: withKey('rotation', 45), axis: 'rotation', want: UNPARSABLE, value: 0 },
  { id: 'rot_fractional', meta: withKey('rotation', 90.5), axis: 'rotation', want: DECLARED, value: 90 },
  // ── NORMALISE OR REFUSE: start ──
  { id: 'start_float_string', meta: withKey('grid_start_x', '3.7'), axis: 'startX', want: UNPARSABLE, value: 0 },
  { id: 'start_trailing_garbage', meta: withKey('grid_start_x', '3abc'), axis: 'startX', want: UNPARSABLE, value: 0 },
  // A NATIVE float truncates rather than refusing -- `int(3.7)` is 3. Left un-truncated it
  // makes `seatKey` emit "0.30000000000000004,5" and every membership lookup misses.
  { id: 'start_native_float', meta: withKey('grid_start_x', 3.7), axis: 'startX', want: DECLARED, value: 3 },
  { id: 'start_int_string', meta: withKey('grid_start_x', '3'), axis: 'startX', want: DECLARED, value: 3 },
  { id: 'chipx_garbage_suffix', meta: withKey('phys_chip_x', '11abc'), axis: 'chipX', want: UNPARSABLE, value: 2.5 },
  { id: 'invert_true', meta: withKey('grid_y_invert', true), axis: 'invertY', want: DECLARED, value: true },
  { id: 'chipx_absent', meta: without('phys_chip_x'), axis: 'chipX', want: ABSENT, value: 2.5 },
  { id: 'chipx_unparsable', meta: withKey('phys_chip_x', 'abc'), axis: 'chipX', want: UNPARSABLE, value: 2.5 },
  { id: 'chipx_marked', meta: marked(FULL), axis: 'chipX', want: AUTO_REGISTERED, value: 11 },
];

// ═══════════════════════════════════════════════════════════════════════════════
// SCORING
// ═══════════════════════════════════════════════════════════════════════════════
function run(mod) {
  const {
    frameFromDeclaration: mkFrame, visualDimensions: vDims,
    visualDimensionsLegacy: vDimsLegacy, geometryDeclaration: geoDecl,
    axesWithSource: axesWith, foldedAxes: folded, isFrameUsable: usable,
    AXIS_NAMES: NAMES, DECLARATION_TOKENS: TOKENS,
  } = mod;

  let compared = 0;
  const failures = [];
  const evidence = [];
  const eq = (what, got, want) => {
    compared++;
    if (!Object.is(got, want)) failures.push(`${what}: got ${JSON.stringify(got)} want ${JSON.stringify(want)}`);
  };
  const ok = (what, cond) => { compared++; if (!cond) failures.push(what); };

  // ── A. PARITY on production shapes ───────────────────────────────────────────
  let prodRows = 0;
  let identicalRows = 0;
  const divergent = new Map();
  for (const shape of PROD.shapes) {
    const meta = shape.meta;
    const n = shape.n;
    prodRows += n;
    const dom = domFromMeta(meta);
    const F = mkFrame(meta);
    const L = F.legacy;
    const before = failures.length;

    const ss = O_seatingSnapshot(dom);
    for (const k of Object.keys(ss)) eq(`prod[${shape.table}] seatingSnapshot.${k}`, L[k], ss[k]);

    const rg = O_readGridFrameControls(dom);
    for (const k of Object.keys(rg)) eq(`prod[${shape.table}] readGridFrameControls.${k}`, L[k], rg[k]);

    const gv = O_getVisualGridDimensions(dom);
    const mv = vDimsLegacy(F);
    eq(`prod[${shape.table}] getVisualGridDimensions.visualCols`, mv.visualCols, gv.visualCols);
    eq(`prod[${shape.table}] getVisualGridDimensions.visualRows`, mv.visualRows, gv.visualRows);

    const cc = O_currentCoordFrame(dom);
    for (const k of Object.keys(cc)) {
      const mine = (k === 'visualCols' || k === 'visualRows') ? mv[k] : L[k];
      eq(`prod[${shape.table}] currentCoordFrame.${k}`, mine, cc[k]);
    }

    const cf = O_currentFrame(dom);
    for (const k of Object.keys(cf)) eq(`prod[${shape.table}] currentFrame.${k}`, L[k], cf[k]);

    const sig = O_currentGeomSignature(dom);
    const mineSig = [
      String(meta.grid_cols), String(meta.grid_rows),
      String(meta.grid_start_x), String(meta.grid_start_y),
      L.invertY ? 1 : 0, L.rotation, L.side,
      String(meta.phys_wafer_dia), String(meta.phys_chip_x), String(meta.phys_chip_y),
      String(meta.phys_offset_x), String(meta.phys_offset_y), String(meta.phys_edge_margin),
    ].join('|');
    eq(`prod[${shape.table}] currentGeomSignature`, mineSig, sig);

    if (failures.length === before) identicalRows += n;
    else divergent.set(shape.table, (divergent.get(shape.table) || 0) + n);
  }
  evidence.push(`A. parity: ${PROD.shapes.length} shapes / ${prodRows} production rows; `
    + `identical on every field: ${identicalRows}; divergent: ${prodRows - identicalRows}`);
  ok('A. every production row must be identical to the shipped answer', identicalRows === prodRows);

  // ── B. PROVENANCE ────────────────────────────────────────────────────────────
  for (const c of SYNTHETIC) {
    const F = mkFrame(c.meta);
    eq(`B. synthetic[${c.id}] ${c.axis}.source`, F.axes[c.axis].source, c.want);
    eq(`B. synthetic[${c.id}] ${c.axis}.value`, F.axes[c.axis].value, c.value);
  }
  // The four states `_rotation_of` collapses must be four tokens here.
  const rotIds = ['rot_absent', 'rot_unparsable', 'rot_stored_zero_unmarked', 'rot_marked_zero'];
  const rotTokens = new Set(rotIds
    .map(id => mkFrame(SYNTHETIC.find(s => s.id === id).meta).axes.rotation.source));
  eq('B. absent / unparsable / stored-zero / registrar-written are four distinct tokens',
    rotTokens.size, 4);
  // ...and all four still produce the number 0, so nothing downstream moves yet.
  for (const id of rotIds) {
    eq(`B. ${id} still answers 0`, mkFrame(SYNTHETIC.find(s => s.id === id).meta).legacy.rotation, 0);
  }

  // ── B2. THE TAINTING RULE, and its anti-drift device ─────────────────────────
  // "A stored value equal to what the reader invents when the key is missing is not evidence
  // that anyone chose it." The invented value must be READ BACK OUT of the reader, never
  // restated -- otherwise the table and the defaults diverge silently the first time a
  // default moves. This pair of assertions is what makes that true rather than intended.
  for (const a of NAMES) {
    eq(`B2. noEvidenceValue(${a}) is what an absent key produces`,
      mod.noEvidenceValue(a), mkFrame({}).axes[a].value);
    eq(`B2. frame.noEvidence[${a}] is the table actually used`,
      mkFrame(FULL).noEvidence[a], mod.noEvidenceValue(a));
  }
  // Move a default and the verdict must move with it -- this is the drift the device stops.
  // Scored on `rotation`, which IS a value-testable axis: FULL stores 90, so it is declared;
  // make 90 the invented value and the same stored 90 stops being evidence of a choice.
  eq('B2. a moved default moves the verdict (rotation 90 declared by default)',
    mkFrame(FULL).axes.rotation.source, DECLARED);
  eq('B2. ...and becomes indeterminate once 90 is what the reader invents',
    mkFrame(FULL, { defaults: { rotation: 90 } }).axes.rotation.source, INDETERMINATE);

  // ── B3. THE VALUE TEST IS BOUNDED (lead PM ruling 2026-08-05) ────────────────
  // The inference is about ABSENT keys and about generators that write CONSTANTS. It runs on
  // rotation / side / invertY and nowhere else. On every other axis the marker is the only
  // witness: marked -> auto_registered, unmarked -> declared, whatever the value.
  eq('B3. exactly three axes are value-testable', mod.VALUE_CAN_INDICATE_PROVENANCE.length, 3);
  eq('B3. and they are the three the registrar writes as constants',
    mod.VALUE_CAN_INDICATE_PROVENANCE.join(','), 'rotation,side,invertY');
  for (const a of NAMES) {
    if (mod.VALUE_CAN_INDICATE_PROVENANCE.includes(a)) continue;
    // Stored value == what the reader invents, unmarked. A value test would say indeterminate.
    const f = mkFrame({ ...FULL, [mod.AXIS_META_KEY[a]]: mod.noEvidenceValue(a) });
    eq(`B3. ${a} is a measurement axis: an invented-looking value is still declared`,
      f.axes[a].source, DECLARED);
    // ...and the marker alone flips it, without consulting the value.
    const g = mkFrame(marked({ ...FULL, [mod.AXIS_META_KEY[a]]: mod.noEvidenceValue(a) }));
    eq(`B3. ${a}: the marker is the only witness`, g.axes[a].source, AUTO_REGISTERED);
  }
  // 🔴 THE PAYOFF: the start default no longer touches provenance. The client invents 0 and
  //    the server invents 1; under the old value test that inverted the verdict on 660 of 668
  //    production rows. Now both conventions agree on every start, marked and unmarked.
  for (const stored of [0, 1, 37]) {
    for (const m of [withKey('grid_start_x', stored), marked(withKey('grid_start_x', stored))]) {
      eq(`B3. start ${stored}${m.auto_registered ? ' marked' : ''}: default 0 and default 1 agree`,
        mkFrame(m).axes.startX.source, mkFrame(m, { defaults: { startX: 1 } }).axes.startX.source);
    }
  }
  eq('B3. START_AXES names the two the ruling is about', mod.START_AXES.join(','), 'startX,startY');
  for (const a of mod.START_AXES) {
    ok(`B3. ${a} is never value-tested`, !mod.VALUE_CAN_INDICATE_PROVENANCE.includes(a));
  }
  // `indeterminate` therefore lands on three axes, not the five the orientation vocabulary
  // covers -- the two lists are different on purpose and the difference is exactly START_AXES.
  eq('B3. orientation vocabulary still covers five axes', mod.ORIENTATION_AXES.length, 5);
  eq('B3. value-testable is orientation minus start',
    mod.ORIENTATION_AXES.filter(a => !mod.START_AXES.includes(a)).join(','),
    mod.VALUE_CAN_INDICATE_PROVENANCE.join(','));
  // The declared zero that the shipped `|| dflt` eats.
  const zeroCols = mkFrame(withKey('grid_cols', 0));
  eq('B. declared grid_cols=0 keeps its value', zeroCols.axes.cols.value, 0);
  eq('B. declared grid_cols=0 legacy is the shipped fold to 10', zeroCols.axes.cols.legacy, 10);
  eq('B. foldedAxes names it', folded(zeroCols).join(','), 'cols');
  eq('B. and it is refused as a basis', usable(zeroCols).ok, false);
  // Production, measured -- not a claim, a count.
  let prodFolded = 0;
  let prodNonDeclared = 0;
  for (const shape of PROD.shapes) {
    const F = mkFrame(shape.meta);
    if (folded(F).length > 0) prodFolded += shape.n;
    if (axesWith(F, [ABSENT, UNPARSABLE]).length > 0) prodNonDeclared += shape.n;
  }
  evidence.push(`B. production rows with a folded declared value: ${prodFolded} of ${prodRows}`);
  evidence.push(`B. production rows with any absent/unparsable axis: ${prodNonDeclared} of ${prodRows}`);
  eq('B. no production row has an absent or unparsable axis (all 13 keys present)', prodNonDeclared, 0);
  eq('B. no production row folds a declared value', prodFolded, 0);
  // The marker, which production DOES exercise -- 320 rows.
  let markedRows = 0;
  for (const shape of PROD.shapes) {
    const F = mkFrame(shape.meta);
    const isMarked = F.axes.chipX.source === AUTO_REGISTERED;
    ok(`B. marker agrees with geometryDeclaration on ${shape.table}`,
      isMarked === (F.geometry === AUTO_REGISTERED));
    if (isMarked) markedRows += shape.n;
  }
  eq('B. auto_registered production rows', markedRows, 320);
  evidence.push(`B. auto_registered rows: ${markedRows} of ${prodRows}`);
  // Vocabulary. Pinned as SEPARATE facts so that a change to the shared four is a different
  // failure from a change to either of the two that came later.
  //
  // 🔴 THE COUNT WAS THE WRONG INVARIANT AND THIS IS THE CORRECTION (2026-08-05). The rule was
  //    never "there are five" -- it is that every token is COPIED from a server constant and
  //    none is minted here. Pinning the length made a legitimate server-side addition
  //    (`GEOMETRY_ASSUMED`, MAP_ALIGNMENT_SPEC 9.1) read as a client defect, which is the
  //    failure pointing the wrong way: the client was correct and the assertion was stale.
  //    Each token is pinned by NAME and POSITION instead, so an invented one still fails.
  eq('B. the four shared with map_overlay.py GEOMETRY_*, in that order',
    TOKENS.slice(0, 4).join(','), 'declared,auto_registered,absent,unparsable');
  eq('B. the fifth is map_overlay.py ORIENTATION_INDETERMINATE', TOKENS[4], 'indeterminate');
  eq('B. the sixth is map_overlay.py GEOMETRY_ASSUMED', TOKENS[5], 'assumed');
  eq('B. the seventh is map_overlay.py GEOMETRY_CONFIRMED', TOKENS[6], 'confirmed');
  //
  // 🔴 THE LENGTH PIN IS GONE, AND IT WAS RE-ADDED TWO LINES BELOW ITS OWN OBITUARY.
  //    The comment above says the count was the wrong invariant and that each token is pinned
  //    by NAME AND POSITION instead -- and then the next line pinned `TOKENS.length === 6`
  //    anyway. It fired on 2026-08-06 when the server grew `confirmed`, for the third time,
  //    with the client correct and the assertion stale. Knowing the rule clearly is evidently
  //    not the same as following it, which is why the fix is a DELETION and not a bumped number.
  //
  //    The rule this repository keeps relearning: PIN THE MEMBERS, NOT THE COUNT.
  //
  // ⚠️ AND THE HONEST HALF, MEASURED RATHER THAN ASSERTED. A first draft of this comment
  //    claimed the positional pins above already catch an invented token. THEY DO NOT, and the
  //    mutant said so: appending `'provisional'` at index 7 left this harness at 4079/0. The
  //    length pin really was covering that, badly -- it caught the invented token and the
  //    legitimate one with the same useless message ("got 7 want 6").
  //
  //    That boundary is NOT re-owned here, because owning it means writing the whole
  //    vocabulary down a fourth time and this round is about a word being enumerated in too
  //    many places. It is owned by `contracts/map2_seam/client_harness.mjs`, which compares
  //    the token SET against the shared contract and, on the same mutant, fails naming the
  //    extra word. A set pin still needs an edit when the server legitimately grows -- but it
  //    edits with the new word in the failure text, which is a maintenance step rather than a
  //    riddle. This file pins the members it can see and points at the owner for the rest.
  //
  //    What IS kept here is the invariant a length pin cannot express at all: the vocabulary
  //    is a SET. A token repeated past the last positional pin is caught by nothing above and
  //    by nothing in the contract's set comparison either, and unlike a length it stays true
  //    however many tokens the server adds.
  eq('B. the vocabulary is a set -- no token appears twice',
    new Set(TOKENS).size, TOKENS.length);

  // The 516: it is real, and it is what the module's header now claims. Rotation is stored as
  // 0 on 516 of 668 rows and on none of them did a person choose it -- 320 written by the
  // registrar, 196 a generator's literal zero with no marker.
  const rotSrc = {};
  for (const shape of PROD.shapes) {
    const s = mkFrame(shape.meta).axes.rotation.source;
    rotSrc[s] = (rotSrc[s] || 0) + shape.n;
  }
  evidence.push(`B. rotation provenance over ${prodRows} rows: `
    + Object.keys(rotSrc).sort().map(k => `${k}=${rotSrc[k]}`).join(' '));
  eq('B. rotation auto_registered rows', rotSrc[AUTO_REGISTERED] || 0, 320);
  eq('B. rotation indeterminate rows', rotSrc[INDETERMINATE] || 0, 196);
  eq('B. rotation evidence-free rows total 516',
    (rotSrc[AUTO_REGISTERED] || 0) + (rotSrc[INDETERMINATE] || 0), 516);
  eq('B. rotation genuinely declared rows', rotSrc[DECLARED] || 0, 152);
  for (const shape of PROD.shapes) {
    const F = mkFrame(shape.meta);
    for (const a of NAMES) ok(`B. ${a} source in vocabulary`, TOKENS.includes(F.axes[a].source));
  }
  // geometryDeclaration is the server's port, including MARKER-BEFORE-VALUES order.
  eq('C. marker wins over complete values', geoDecl({ ...FULL, auto_registered: true }), AUTO_REGISTERED);
  eq('C. complete values are declared', geoDecl(FULL), DECLARED);
  eq('C. one missing phys key is absent', geoDecl(without('phys_edge_margin')), ABSENT);
  eq('C. a non-numeric phys key is unparsable', geoDecl(withKey('phys_offset_y', 'x')), UNPARSABLE);
  eq('C. null meta is absent', geoDecl(null), ABSENT);

  // ── E. THE VALUE SURFACE IS THE DECLARED VALUE, NOT THE FOLDED ONE ───────────
  //
  // 🔴 THIS IS THE SECTION THAT HAD TO EXIST. Sourcing the flat fields from `legacy` instead
  //    of `value` -- one word in `frameFromDeclaration` -- deletes the entire reason this
  //    module exists and scored 3438/0 without it, because stage B's plan is to read
  //    `frame.<axis>` and every parity assertion above is deliberately scored against
  //    `frame.legacy.*`.
  //
  // 🔴 AND IT CANNOT BE PINNED ON PRODUCTION. Measured: 0 of 668 production rows fold a
  //    declared value, so `value === legacy` on every axis of every production row and
  //    asserting their identity there is 858 assertions that cannot fail. The divergence only
  //    exists where a stored zero meets a non-zero substitute, so that is what is built here.
  //    An axis whose substitute is 0 (startX, startY, offsetX, offsetY, rotation) cannot
  //    diverge at all and is deliberately not in this list.
  const FOLDABLE = { cols: 10, rows: 10, waferDia: 300, chipX: 2.5, chipY: 2.5, edgeMargin: 3.0 };
  for (const [a, substitute] of Object.entries(FOLDABLE)) {
    const f = mkFrame({ ...FULL, [mod.AXIS_META_KEY[a]]: 0 });
    eq(`E. ${a}: the flat surface carries the DECLARED zero`, f[a], 0);
    eq(`E. ${a}: axes.value carries the declared zero`, f.axes[a].value, 0);
    eq(`E. ${a}: legacy carries the shipped substitute`, f.legacy[a], substitute);
    ok(`E. ${a}: the two surfaces are NOT the same`, f[a] !== f.legacy[a]);
    eq(`E. ${a}: foldedAxes names it`, folded(f).includes(a), true);
  }
  // Every axis of every synthetic frame: the flat field IS `axes[name].value`.
  for (const c of SYNTHETIC) {
    const f = mkFrame(c.meta);
    for (const a of NAMES) eq(`E. synthetic[${c.id}].${a} flat === axes.value`, f[a], f.axes[a].value);
  }
  // ...and the visual pair is derived from the value surface, not the legacy one. A frame
  // declaring 0 columns has 0 visual columns; `visualDimensionsLegacy` is what answers 10.
  const zc = mkFrame({ ...FULL, grid_cols: 0 });   // FULL is rot 90, so cols/rows swap
  eq('E. visualRows comes from the value surface', zc.visualRows, 0);
  eq('E. visualDimensionsLegacy comes from the legacy surface', vDimsLegacy(zc).visualRows, 10);

  // ── F. THE ORACLE COUPLING, MEASURED RATHER THAN ASSERTED ────────────────────
  //
  // `O_readGridFrameControls` above transcribes a function that changed this round: the product
  // now refuses a blank box instead of folding it to 0. A transcription edited to match its own
  // subject proves nothing, so the claim that this one did NOT have to move is a measurement:
  // over every shape scored here, how many DOM round trips produce a box the product would call
  // silent? The DOM round trip is lossy in a documented direction -- a text input holds a STRING,
  // and `String(undefined)` is `"undefined"`, not `""` -- so the answer should be zero, and if it
  // ever stops being zero the transcription really has become a second implementation.
  const domBlank = (dom) => ['gridCols', 'gridRows', 'gridStartX', 'gridStartY']
    .filter(k => dom[k] === undefined || dom[k] === null || String(dom[k]).trim() === '');
  let blankProdRows = 0;
  let blankSynthetic = 0;
  for (const shape of PROD.shapes) {
    if (domBlank(domFromMeta(shape.meta)).length > 0) blankProdRows += shape.n;
  }
  for (const c of SYNTHETIC) {
    if (domBlank(domFromMeta(c.meta)).length > 0) blankSynthetic++;
  }
  evidence.push(`F. oracle coupling: DOM round trips producing a blank frame box -- `
    + `production ${blankProdRows} of ${prodRows} rows, synthetic ${blankSynthetic} of `
    + `${SYNTHETIC.length} shapes. The product's refusal branch is unreachable from here, so `
    + `the transcription still expresses the lenient fold and was not moved to match it.`);
  eq('F. no production shape can reach the product\'s blank-box refusal', blankProdRows, 0);
  eq('F. no synthetic shape can either (a missing key round-trips as "undefined")',
    blankSynthetic, 0);
  // ...and the counterfactual, so the measurement is not vacuous: a genuinely blank box IS
  // detected by the same expression. Without this, `domBlank` returning [] always would pass.
  eq('F. the blank detector is live', domBlank({ gridCols: '10', gridRows: '', gridStartX: '3',
    gridStartY: '5' }).join(','), 'gridRows');

  // ── G. THE CHOICE MARKER -- provenance for the FRAME half ────────────────────
  //
  // The frame half had no provenance channel at all: `auto_registered` is read here for the
  // measurement axes, but a map whose frame came from ⚙️ 현재 패널 carried no marker of any
  // kind, so it was byte-identical to a map that declared its own frame. What closes it is NOT
  // a seventh token (see FRAME_CHOSEN_KEY for why each of the six fails) but a record that the
  // choice HAPPENED, exposed as one field.
  const chosenMeta = (from) => ({ ...FULL, [mod.FRAME_CHOSEN_KEY]: from });
  eq('G. the key is the one map_editor.js writes', mod.FRAME_CHOSEN_KEY, 'frame_chosen_from');
  eq('G. a declared frame reports no choice', mkFrame(FULL).chosen, null);
  eq('G. ...and so does a meta with no keys at all', mkFrame({}).chosen, null);
  eq('G. ...and a null meta', mkFrame(null).chosen, null);
  for (const from of mod.FRAME_CHOSEN_FROM) {
    eq(`G. a frame chosen from the ${from} says so`, mkFrame(chosenMeta(from)).chosen, from);
  }
  // WHICH choice, not merely THAT one happened: a boolean would delete the difference between a
  // bbox-derived frame and the previous map's panel residue.
  ok('G. the two choices are distinguishable from each other',
    mkFrame(chosenMeta('data')).chosen !== mkFrame(chosenMeta('panel')).chosen);
  eq('G. FRAME_CHOSEN_FROM is the writer\'s branch order',
    mod.FRAME_CHOSEN_FROM.join(','), 'data,panel');
  // An empty string is silence, exactly as it is on every other key this module reads.
  eq('G. an empty marker is not a choice', mkFrame(chosenMeta('')).chosen, null);
  //
  // 🔴 AND THE HALF THAT KEEPS IT HONEST: recording the choice must move NOTHING ELSE. No axis
  //    token changes, `geometryDeclaration` does not change, and the frame stays usable -- the
  //    modal exists so that the map OPENS (98b48e9), and a marker that made it un-alignable
  //    would shut that back off. Scored by comparing the whole record minus `chosen`.
  const strip = (f) => JSON.stringify(Object.assign({}, f, { chosen: null }));
  for (const from of mod.FRAME_CHOSEN_FROM) {
    eq(`G. the ${from} marker changes nothing but \`chosen\``,
      strip(mkFrame(chosenMeta(from))), strip(mkFrame(FULL)));
    eq(`G. ...including the geometry verdict`, geoDecl(chosenMeta(from)), geoDecl(FULL));
    eq(`G. ...and the frame stays usable`, usable(mkFrame(chosenMeta(from))).ok, true);
  }
  // No token was minted FOR THIS. The claim is about `frame_chosen_from`, and the assertion
  // that carries it is the membership one on the next line -- `data`/`panel` must not appear
  // in the vocabulary. The length pin that used to stand here could not express that: it went
  // red on 2026-08-06 for `confirmed`, a token the SERVER minted and this side copied, which
  // is the opposite of what it was written to catch. Deleted rather than bumped, same reason
  // as at the vocabulary block above -- PIN THE MEMBERS, NOT THE COUNT.
  for (const from of mod.FRAME_CHOSEN_FROM) {
    ok(`G. \`${from}\` is not a token`, !TOKENS.includes(from));
    for (const a of NAMES) {
      ok(`G. ${a} keeps its token under a ${from} marker`,
        mkFrame(chosenMeta(from)).axes[a].source === mkFrame(FULL).axes[a].source);
    }
  }

  // ── C. VISUAL DIMENSIONS, parametric ─────────────────────────────────────────
  // The reason the existing primitive could not be shared: it reads a module global.
  for (const rot of [0, 90, 180, 270]) {
    const v = vDims({ cols: 45, rows: 39, rotation: rot });
    const q = (rot === 90 || rot === 270);
    eq(`C. visualDimensions(${rot}).visualCols`, v.visualCols, q ? 39 : 45);
    eq(`C. visualDimensions(${rot}).visualRows`, v.visualRows, q ? 45 : 39);
  }
  eq('C. visualDimensions ignores ambient state (frame argument only)',
    vDims({ cols: 3, rows: 7, rotation: 270 }).visualCols, 7);

  // ── D. PURITY AND FREEZE ─────────────────────────────────────────────────────
  ok('D. no `document` in this process', typeof document === 'undefined');
  ok('D. no `window` in this process', typeof window === 'undefined');
  const f0 = mkFrame(FULL);
  ok('D. frame is frozen', Object.isFrozen(f0));
  ok('D. axes bag is frozen', Object.isFrozen(f0.axes));
  ok('D. each axis is frozen', NAMES.every(n => Object.isFrozen(f0.axes[n])));
  ok('D. legacy bag is frozen', Object.isFrozen(f0.legacy));
  // A frame built from the same meta twice must be equal -- no hidden state between calls.
  eq('D. two calls agree (no module state)',
    JSON.stringify(mkFrame(FULL)), JSON.stringify(mkFrame(FULL)));
  // Mutating the input after the fact must not move the frame.
  const mutable = { ...FULL };
  const snap = mkFrame(mutable);
  mutable.rotation = 270;
  eq('D. frame does not alias its input', snap.rotation, 90);
  // Defaults are injectable -- this is how config reaches a module that cannot import it.
  eq('D. injected startX default (the server convention, finding D4)',
    mkFrame(without('grid_start_x'), { defaults: { startX: 1 } }).startX, 1);
  eq('D. default default is the client convention',
    mkFrame(without('grid_start_x')).startX, 0);
  eq('D. FRAME_DEFAULTS is frozen', Object.isFrozen(mod.FRAME_DEFAULTS), true);
  const bounds = mod.frameDimBounds();
  eq('D. dim bounds min', bounds.min, 1);
  eq('D. dim bounds max', bounds.max, 100);

  return { compared, failures, evidence };
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════════
const verbose = process.argv.includes('--verbose');
const mutate = process.argv.includes('--mutate');

const base = run(LIVE);
if (verbose || !mutate) base.evidence.forEach(e => console.log('  ' + e));
console.log(`${base.failures.length === 0 ? 'PASS' : 'FAIL'} baseline: ${base.compared} assertions, `
  + `${base.failures.length} failure(s)`);
console.log(`ASSERTIONS ${base.compared} ${base.failures.length}`);
base.failures.slice(0, 25).forEach(f => console.log(`   x ${f}`));
if (base.failures.length > 25) console.log(`   ... and ${base.failures.length - 25} more`);

if (mutate) {
  // In-memory variants only. The file on disk is never written, so there is no CRLF hazard
  // and no stale artefact to forget to revert.
  const SRC = readFileSync(MODULE_PATH, 'utf8').replace(/\r\n/g, '\n');
  const swap = (name, from, to) => ({
    name,
    apply: (s) => {
      if (!s.includes(from)) throw new Error(`anchor not found: ${from}`);
      const n = s.split(from).length - 1;
      if (n !== 1) throw new Error(`anchor is not unique (${n} matches): ${from}`);
      return s.split(from).join(to);
    },
  });

  const MUTANTS = [
    swap('M1 visual dims never swap on a quarter turn',
      'const quarter = (rot === 90 || rot === 270);',
      'const quarter = false;'),
    swap('M2 side falls back to back',
      "side: 'front',", "side: 'back',"),
    swap('M3 declared zero is not folded (drops `|| dflt` from the legacy int read)',
      'parseInt(String(raw), 10);\n  return Number.isFinite(n) ? (n || dflt) : dflt;',
      'parseInt(String(raw), 10);\n  return Number.isFinite(n) ? n : dflt;'),
    swap('M4 rotation legacy ignores the declared value',
      "const legacy = Number.isFinite(Number(raw)) ? (Number(raw) || dflt) : dflt;",
      "const legacy = 0;"),
    swap('M5 chipX and chipY swapped',
      "chipX: floatAxis('chipX', get('phys_chip_x'), d.chipX),",
      "chipX: floatAxis('chipX', get('phys_chip_y'), d.chipX),"),
    swap('M6 the auto_registered marker is ignored on measurement axes',
      'if (autoRegistered) source = AUTO_REGISTERED;',
      'if (false) source = AUTO_REGISTERED;'),
    swap('M7 absent and unparsable collapse to one token',
      'const n = toPyInt(raw);\n  if (n === null) return axis(name, raw, dflt, UNPARSABLE, legacy);',
      'const n = toPyInt(raw);\n  if (n === null) return axis(name, raw, dflt, ABSENT, legacy);'),
    swap('M8 startX default silently becomes the server convention',
      'startX: 0, startY: 0,', 'startX: 1, startY: 1,'),
    swap('M9 the frame is not frozen',
      'return Object.freeze(Object.assign(flat, {', 'return (Object.assign(flat, {'),
    // 🔴 THE ONE THAT SCORED 3438/0 BEFORE SECTION E EXISTED. One word, and the module still
    //    passed every parity assertion, because parity is scored against `legacy` on purpose
    //    and production never folds a value. Stage B reads `frame.<axis>`.
    swap('M10 the flat surface is sourced from legacy instead of value',
      'for (const name of AXIS_NAMES) flat[name] = frozenAxes[name].value;',
      'for (const name of AXIS_NAMES) flat[name] = frozenAxes[name].legacy;'),
    // The fifth token, and the two halves of the tainting rule.
    swap('M11 indeterminate collapses back into declared',
      'else if (evidenceFree) source = INDETERMINATE;',
      'else if (false) source = INDETERMINATE;'),
    swap('M12 the marker explains any value, including a rotation the registrar never writes',
      'if (autoRegistered) source = evidenceFree ? AUTO_REGISTERED : DECLARED;',
      'if (autoRegistered) source = AUTO_REGISTERED;'),
    // THE RULING REGRESSION MUTANT: put start back under the value test. That is the shape
    // the module had before the 2026-08-05 ruling, and it is what re-introduces the 660-row
    // client/server inversion.
    swap('M13 start is value-tested again (the pre-ruling shape)',
      "export const VALUE_CAN_INDICATE_PROVENANCE = Object.freeze(['rotation', 'side', 'invertY']);",
      "export const VALUE_CAN_INDICATE_PROVENANCE = Object.freeze(['rotation', 'side', 'invertY', 'startX', 'startY']);"),
    // The anti-drift device: restate the invented values instead of asking the reader.
    swap('M14 the no-evidence table is restated instead of read back from the reader',
      'for (const name of AXIS_NAMES) noEvidence[name] = d[name];',
      "for (const name of AXIS_NAMES) noEvidence[name] = FRAME_DEFAULTS[name];"),
    // ── THE PARSE DIRECTION. Each of these restores a LENIENT read, which is the shape the
    //    module had before 2026-08-05 and the shape that produced nine seam divergences.
    swap('M15 integers read leniently again (parseInt accepts trailing garbage)',
      // Anchored on the tail of the strict test rather than on the pattern itself -- a regex
      // literal inside a mutant string needs double escaping and silently stops matching if
      // one level is lost. Ask the anchor guard: it caught exactly that while this was written.
      '.test(t) ? Number(t) : null;',
      '.test(t) || true ? (Number.isFinite(parseInt(t, 10)) ? parseInt(t, 10) : null) : null;'),
    swap('M16 rotation is not normalised mod 360',
      'const n = ((i % 360) + 360) % 360;', 'const n = i;'),
    swap('M17 rotation is not gated on the exported ROTATIONS domain',
      "if (!ROTATIONS.includes(n)) return axis('rotation', raw, dflt, UNPARSABLE, legacy);",
      "if (false) return axis('rotation', raw, dflt, UNPARSABLE, legacy);"),
    swap('M18 grid_y_invert accepts strings again',
      "  if (typeof raw === 'number' && (raw === 0 || raw === 1)) {",
      "  if (typeof raw === 'string') return axis(name, raw, raw.trim().toLowerCase() === 'true', DECLARED, legacy);"
      + "  if (typeof raw === 'number' && (raw === 0 || raw === 1)) {"),
    swap('M19 floats read leniently again (parseFloat truncates to garbage)',
      '.test(t)) return null;\n    const n = Number(t);',
      '.test(t)) { /* lenient */ }\n    const n = parseFloat(t);'),
    // ── THE CHOICE MARKER. Each of these is a way of "recording the choice" that loses the
    //    thing the record was for.
    swap('M20 the choice marker is never read (a chosen frame is a declared frame again)',
      "chosen: (m && !isSilent(m[FRAME_CHOSEN_KEY])) ? String(m[FRAME_CHOSEN_KEY]) : null,",
      'chosen: null,'),
    swap('M21 the marker is folded to a boolean (WHICH choice is lost)',
      "chosen: (m && !isSilent(m[FRAME_CHOSEN_KEY])) ? String(m[FRAME_CHOSEN_KEY]) : null,",
      'chosen: !!(m && m[FRAME_CHOSEN_KEY]),'),
    swap('M22 the marker is minted as a seventh token instead of a record',
      "  DECLARED, AUTO_REGISTERED, ABSENT, UNPARSABLE, INDETERMINATE, ASSUMED]);",
      "  DECLARED, AUTO_REGISTERED, ABSENT, UNPARSABLE, INDETERMINATE, ASSUMED, 'chosen']);"),
    // ⚠️ THIS ANCHOR WAS STALE AND THE WHOLE SWEEP DIED ON IT (found 2026-08-05). It still said
    //    "the five tokens" after `assumed` made the header say six, so `--mutate` exited 2 with
    //    nothing scored — and the gate never noticed because the gate runs this harness BARE.
    //    A mutation corpus whose control cannot be applied is a corpus nobody is running.
    swap('CONTROL a comment change must NOT be caught',
      '// ── the six tokens ', '// ── the 6 tokens '),
  ];

  console.log('\n  MUTATION CONTROLS -- a surviving mutant means the check above it is inert.\n');
  let scored = 0;
  for (const m of MUTANTS) {
    const isControl = m.name.startsWith('CONTROL');
    let killed;
    let detail = '';
    // 🔴 AN ANCHOR THAT DOES NOT MATCH IS A HARNESS DEFECT, NOT A CAUGHT MUTANT. This bit me
    //    while writing this file: M7's anchor was stale, `apply` threw, the throw was scored
    //    as a kill, and the run reported 10/10 while one mutant had never been APPLIED. A
    //    mutant that was never introduced proves exactly nothing, so it now stops the run.
    let src;
    try {
      src = m.apply(SRC);
    } catch (e) {
      die(`mutant "${m.name}" could not be applied: ${e.message}. `
        + `An unapplied mutant is not a caught mutant.`);
    }
    try {
      const url = 'data:text/javascript;base64,' + Buffer.from(src, 'utf8').toString('base64');
      const mod = await import(url);
      const out = run(mod);
      killed = out.failures.length > 0;
      detail = killed ? `${out.failures.length} failure(s), first: ${out.failures[0]}` : '';
      // A mutant that ran fewer assertions than the baseline did not get scored; it crashed
      // its way to a verdict. That is a harness defect, not a caught mutant.
      if (out.compared < base.compared) {
        detail += ` [WARNING: ran ${out.compared} of ${base.compared} assertions]`;
      }
    } catch (e) {
      killed = true;
      detail = `threw: ${String(e && e.message).slice(0, 110)}`;
    }
    if (killed !== isControl) scored++;
    console.log(`  ${killed ? 'CAUGHT  ' : 'SURVIVED'}  ${m.name}`);
    if (detail) console.log(`            ${detail}`);
  }
  console.log(`\n  ${scored}/${MUTANTS.length} scored as intended.`);
  if (scored !== MUTANTS.length) process.exit(1);
}

process.exit(base.failures.length === 0 ? 0 : 1);
