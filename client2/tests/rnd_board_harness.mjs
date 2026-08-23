/**
 * R&D BOARD SKELETON -- marking store, component contract, grid shell, and the map part.
 *
 * WHAT IS SCORED (the round's five acceptance items, in order):
 *   B  TWO MAPS ON ONE SCREEN, NO INTERFERENCE  -- the definition of "assembled"
 *   C  THE TWO READ DIFFERENT MARKING NAMES     -- and identical node ids do NOT cross
 *   D  A THIRD MARKING NAME CHANGES NO CODE     -- the definition of "extensible"
 *   E  RESIZING THE BOX MAKES THE MAP FOLLOW
 *   F  NO MODULE-LEVEL STATE IN A COMPONENT
 * plus A (the store itself) and G (the API boundary against a REAL response).
 *
 * 🔴 EVERY ASSERTION IS SHOWN TO BE AWAKE. Section M applies a mutation corpus to the REAL
 *    module sources -- loaded as data URLs, so the mutant is the shipped file plus one edit --
 *    and requires the NAMED assertion above to go red. A check that passes because two panels
 *    happen not to collide today is not the same as one that fails when they do, and the only
 *    way to tell them apart is to make them collide. Each mutant is modelled on a defect that
 *    has actually shipped in this repo (M1 is `ledger_map_panel.js`'s module-level session;
 *    M4 is the 560px canvas the order warns about).
 *
 * 🔴 THE FIXTURES ARE MEASURED, NOT INVENTED.
 *    `fixtures/rnd_board_lot_map_slot07.json` / `_slot03.json` are verbatim bodies of
 *    `GET /api/ledger/lot_map?row=SYN-VOID-001&slot=07|03&kind=void` off the live stack
 *    (127.0.0.1:8080, 2026-08-23): bond ready with 141 cells, dt/core refused with
 *    `frame_ambiguous_across_slots`. A hand-written body would have let the boundary parse a
 *    shape the server does not send.
 *
 * 🔴 THE DOCUMENT STUB HAS A 2D CONTEXT, ON PURPOSE. `surprise_harness.mjs` deliberately
 *    withholds `getContext` because that screen is judged on structure and sentences. This
 *    round is judged on whether two canvases stay out of each other's way and whether one
 *    follows its box -- both of which are invisible without the paint ops. So the stub's
 *    canvas records what the REAL `map2/painter.js` drew into it.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe): no emoji, no em-dash.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC_DIR = path.join(HERE, '..', 'src');
const BOARD_DIR = path.join(SRC_DIR, 'rnd_board');
const srcUrl = (rel) => pathToFileURL(path.join(SRC_DIR, rel)).href;
const dataUrl = (src) => `data:text/javascript;base64,${Buffer.from(src, 'utf8').toString('base64')}`;

const FIX_07 = JSON.parse(readFileSync(
  path.join(HERE, 'fixtures', 'rnd_board_lot_map_slot07.json'), 'utf8'));
const FIX_03 = JSON.parse(readFileSync(
  path.join(HERE, 'fixtures', 'rnd_board_lot_map_slot03.json'), 'utf8'));

// ── loading the modules under test, with an optional mutation per file ─────────────
//
// The relative imports are rewritten so a mutated copy still pulls the OTHER modules under
// test (mutated or not), and reaches the real `map2/painter.js` where it sits.

async function loadModules(mutate = {}) {
  // 🔴 THE TEXTS ARE CARRIED OUT WITH THE MODULES. Section F scans SOURCE, and scanning the
  // file on disk would make it blind to every mutant -- which is exactly what it did on the
  // first run: M5 (a module-level `let` prepended to `map_panel.js`) sailed through, because
  // the scan was reading the shipped file while the suite drove the mutated one.
  const sources = {};
  const read = (file) => {
    const text = readFileSync(path.join(BOARD_DIR, file), 'utf8')
      .replace(new RegExp(String.fromCharCode(13, 10), 'g'), String.fromCharCode(10));
    const fn = mutate[file];
    sources[file] = fn ? fn(text) : text;
    return sources[file];
  };
  const storeUrl = dataUrl(read('marking_store.js'));
  const apiUrl = dataUrl(read('api.js'));
  const panelUrl = dataUrl(read('panel.js')
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  const mapUrl = dataUrl(read('map_panel.js')
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`)
    .replaceAll("'./api.js'", `'${apiUrl}'`)
    .replaceAll("'../map2/painter.js'", `'${srcUrl('map2/painter.js')}'`));
  const shellUrl = dataUrl(read('grid_shell.js'));
  const interUrl = dataUrl(read('marking_intersection.js')
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  // Round 2's parts are imported by `main.js` too, so they have to be rewired here or the
  // composition root cannot load at all -- which is how it failed the moment they landed.
  const partUrl = (file) => dataUrl(read(file)
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`)
    .replaceAll("'./api.js'", `'${apiUrl}'`));
  const headUrl = partUrl('head_summary_panel.js');
  const compUrl = partUrl('composition_panel.js');
  const candUrl = partUrl('candidate_list_panel.js');
  const rankUrl = partUrl('rank_list_panel.js');
  const ctlUrl = partUrl('control_bar_panel.js');
  const trendUrl = partUrl('main_trend_panel.js');
  const statusUrl = partUrl('marking_status_panel.js');
  const mainUrl = dataUrl(read('main.js')
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`)
    .replaceAll("'./grid_shell.js'", `'${shellUrl}'`)
    .replaceAll("'./marking_intersection.js'", `'${interUrl}'`)
    .replaceAll("'./map_panel.js'", `'${mapUrl}'`)
    .replaceAll("'./head_summary_panel.js'", `'${headUrl}'`)
    .replaceAll("'./composition_panel.js'", `'${compUrl}'`)
    .replaceAll("'./candidate_list_panel.js'", `'${candUrl}'`)
    .replaceAll("'./rank_list_panel.js'", `'${rankUrl}'`)
    .replaceAll("'./control_bar_panel.js'", `'${ctlUrl}'`)
    .replaceAll("'./main_trend_panel.js'", `'${trendUrl}'`)
    .replaceAll("'./marking_status_panel.js'", `'${statusUrl}'`)
    .replaceAll("'./api.js'", `'${apiUrl}'`));
  const [store, api, panel, map, shell, main] = await Promise.all([
    import(storeUrl), import(apiUrl), import(panelUrl),
    import(mapUrl), import(shellUrl), import(mainUrl),
  ]);
  return { store, api, panel, map, shell, main, sources };
}

// ── the document stub ──────────────────────────────────────────────────────────────

function recordingContext(canvas) {
  const ctx = {
    fillStyle: null,
    strokeStyle: null,
    lineWidth: 1,
    clearRect(x, y, w, h) { canvas.ops.push({ op: 'clear', x, y, w, h }); },
    fillRect(x, y, w, h) { canvas.ops.push({ op: 'fill', x, y, w, h, color: ctx.fillStyle }); },
    strokeRect(x, y, w, h) {
      canvas.ops.push({ op: 'stroke', x, y, w, h, color: ctx.strokeStyle });
    },
  };
  return ctx;
}

function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '',
    style: {},
    children: [],
    attrs: Object.create(null),
    listeners: Object.create(null),
    // The stub reports a zero-height head, so the canvas box equals the panel box here. The
    // browser reports the real one; either way the panel SUBTRACTS what it measured and
    // never assumes a number.
    offsetHeight: 0,
    _text: '',
    parentNode: null,
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    removeChild(c) {
      const i = this.children.indexOf(c);
      if (i >= 0) this.children.splice(i, 1);
      c.parentNode = null;
      return c;
    },
    setAttribute(k, v) {
      this.attrs[String(k)] = String(v);
      if (String(k) === 'class') this.className = String(v);
    },
    getAttribute(k) {
      return Object.prototype.hasOwnProperty.call(this.attrs, String(k))
        ? this.attrs[String(k)] : null;
    },
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  if (node.tagName === 'CANVAS') {
    node.width = 0;
    node.height = 0;
    node.ops = [];
    node.paints = 0;
    // One `getContext` per paint, so `ops` is THIS paint's ops. `paints` keeps the history
    // that slicing would otherwise hide -- a double paint must still be visible.
    node.getContext = () => { node.ops = []; node.paints += 1; return recordingContext(node); };
  }
  return node;
}

function makeDoc(theme) {
  const doc = {
    createElement(tag) { return makeNode(doc, tag); },
    createElementNS(ns, tag) { return makeNode(doc, tag); },
  };
  doc.documentElement = makeNode(doc, 'html');
  doc.documentElement.setAttribute('data-theme', theme || 'light');
  return doc;
}

/** The injected size observer, so a resize is something the harness DOES, not waits for. */
function makeObserver() {
  const seats = [];
  const observe = (el, cb) => {
    const seat = { el, cb, live: true };
    seats.push(seat);
    return () => { seat.live = false; };
  };
  observe.seats = seats;
  observe.fireAll = (w, h) => { for (const s of seats) if (s.live) s.cb(w, h); };
  observe.fireFor = (el, w, h) => {
    for (const s of seats) if (s.live && s.el === el) s.cb(w, h);
  };
  return observe;
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

const walk = (node, out = []) => {
  out.push(node);
  for (const c of node.children || []) walk(c, out);
  return out;
};
const canvasIn = (root) => walk(root).find((n) => n.tagName === 'CANVAS') || null;
const byClass = (root, cls) => walk(root).filter(
  (n) => String(n.className || '').split(/\s+/).includes(cls));

// ── the suite ──────────────────────────────────────────────────────────────────────
//
// Returns `{ran, failures}`. Run once against the shipped modules (must be empty) and once
// per mutant (a NAMED assertion must be in `failures`).

async function suite(mods) {
  let ran = 0;
  const failures = [];
  const ok = (name, cond, detail) => {
    ran += 1;
    if (!cond) failures.push(detail ? `${name}: ${detail}` : name);
  };
  const eq = (name, got, want) => ok(name, got === want,
    `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);

  const { SIGN, MarkingStore } = mods.store;
  const { GridShell } = mods.shell;
  const { MapPanel } = mods.map;
  const { projectionModel } = mods.api;
  const { BOARD, bindLoaders, PARTS } = mods.main;
  const { markingIntent } = mods.panel;

  // ── A. THE MARKING STORE ─────────────────────────────────────────────────────
  {
    const s = new MarkingStore();
    // Names are DATA: a name this file has never seen works on first write.
    s.set('whatever:name', 'node-1', SIGN.CASE);
    eq('A1 unseen name accepts a mark', s.signOf('whatever:name', 'node-1'), SIGN.CASE);
    eq('A2 unwritten name is absent, not an error', s.signOf('never:written', 'node-1'),
      SIGN.ABSENT);
    // Three states, not two.
    s.set('m', 'n', SIGN.CONTROL);
    eq('A3 control is -1, distinct from absent', s.signOf('m', 'n'), SIGN.CONTROL);
    ok('A4 control is not absent', s.signOf('m', 'n') !== s.signOf('m', 'other'));
    // Names do not leak into each other.
    s.set('m:1', 'shared-id', SIGN.CASE);
    eq('A5 a mark under one name is absent under another',
      s.signOf('m:2', 'shared-id'), SIGN.ABSENT);
    // toggle
    s.toggle('m:1', 'shared-id', SIGN.CASE);
    eq('A6 toggling the same sign clears it', s.signOf('m:1', 'shared-id'), SIGN.ABSENT);
    s.set('m:1', 'x', SIGN.CASE);
    s.toggle('m:1', 'x', SIGN.CONTROL);
    eq('A7 toggling the other sign replaces it', s.signOf('m:1', 'x'), SIGN.CONTROL);
    // subscribe / unsubscribe, per name
    let heard1 = 0;
    let heard2 = 0;
    const off = s.subscribe('m:1', () => { heard1 += 1; });
    s.subscribe('m:2', () => { heard2 += 1; });
    s.set('m:1', 'y', SIGN.CASE);
    eq('A8 a listener hears its own name', heard1, 1);
    eq('A9 a listener does not hear another name', heard2, 0);
    off();
    s.set('m:1', 'z', SIGN.CASE);
    eq('A10 unsubscribe stops delivery', heard1, 1);
    // A no-op write must not wake anyone.
    const before = heard2;
    s.set('m:2', 'nope', SIGN.ABSENT);
    eq('A11 clearing an absent mark is not an event', heard2, before);
    // Names are derived from what carries marks.
    ok('A12 names() reports written names',
      s.names().includes('m:1') && s.names().includes('whatever:name'));
    eq('A13 count is per name', s.count('m:2'), 0);
  }

  // ── G. THE API BOUNDARY, AGAINST THE MEASURED BODY ───────────────────────────
  {
    const bond = projectionModel(FIX_07, 'bond');
    ok('G1 bond is drawable', bond.drawable === true);
    eq('G2 cell count is the served one', bond.cells.length, 141);
    eq('G3 found is the served one', bond.found, 13);
    eq('G4 coordinate unit is passed through', bond.coordinateUnit, 'cells_from_origin');
    ok('G5 every cell carries a node id', bond.cells.every((c) => Boolean(c.nodeId)));
    eq('G6 node ids are unique within a projection',
      new Set(bond.cells.map((c) => c.nodeId)).size, 141);
    ok('G7 the served body carries no node id, so it is stamped',
      bond.cells.every((c) => c.nodeIdResolved === false));
    // The role comes off the cell; the client does not name the roles it will accept.
    ok('G8 roles come from the data',
      new Set(bond.cells.map((c) => c.colorRole)).size >= 2);
    const dt = projectionModel(FIX_07, 'dt');
    ok('G9 a refused projection is not drawable', dt.drawable === false);
    eq('G10 the refusal reason is the servers', dt.reason, 'frame_ambiguous_across_slots');
    ok('G11 a refused projection keeps its cells but is still refused',
      dt.cells.length > 0 && dt.drawable === false);
    const missing = projectionModel(FIX_07, 'no-such-axis');
    ok('G12 an axis the body does not carry refuses rather than throws',
      missing.drawable === false && missing.reason === 'axis_not_served');
    // Two different wafers must not produce the same ids.
    const other = projectionModel(FIX_03, 'bond');
    const overlap = new Set(bond.cells.map((c) => c.nodeId));
    eq('G13 two wafers share no node id',
      other.cells.filter((c) => overlap.has(c.nodeId)).length, 0);
  }

  // ── THE SCREEN UNDER TEST: five panels, one shell, one store ─────────────────
  //
  // A and C are handed the SAME body on purpose, so their node ids are identical. That is
  // what makes C's cross-lighting and D's isolation say something: they cannot pass by the
  // ids happening to differ.
  const doc = makeDoc('light');
  const host = doc.createElement('div');
  const markings = new MarkingStore();
  const observe = makeObserver();
  const layout = {
    columns: 'minmax(0,1fr) minmax(0,1fr)',
    rows: 'minmax(0,1fr) minmax(0,1fr)',
    panels: [
      { id: 'a', part: 'map', title: 'A', at: { column: 1, row: 1 },
        reads: 'marking:1', writes: 'marking:1',
        options: { axis: 'bond', load: () => Promise.resolve(FIX_07) } },
      { id: 'b', part: 'map', title: 'B', at: { column: 2, row: 1 },
        reads: 'marking:2', writes: 'marking:2',
        options: { axis: 'bond', load: () => Promise.resolve(FIX_03) } },
      { id: 'c', part: 'map', title: 'C', at: { column: 1, row: 2 },
        reads: 'marking:1', writes: null,
        options: { axis: 'bond', load: () => Promise.resolve(FIX_07) } },
      { id: 'd', part: 'map', title: 'D', at: { column: 2, row: 2 },
        reads: 'marking:2', writes: null,
        options: { axis: 'bond', load: () => Promise.resolve(FIX_07) } },
      // 🔴 THE THIRD NAME. Nothing in any module knows this string exists.
      { id: 'e', part: 'map', title: 'E', at: { column: 1, row: 3 },
        reads: 'marking:3', writes: 'marking:3',
        options: { axis: 'bond', load: () => Promise.resolve(FIX_07) } },
    ],
  };
  const shell = new GridShell(host, {
    doc, markings, parts: { map: MapPanel }, observeSize: observe,
  });
  shell.render(layout);
  await flush();
  observe.fireAll(400, 300);

  const A = shell.partOf('a');
  const B = shell.partOf('b');
  const C = shell.partOf('c');
  const D = shell.partOf('d');
  const E = shell.partOf('e');
  const elOf = (id) => shell.panels.get(id).el;
  // Sections C/D/E read a panel's model. When B0 below is red they have nothing to read, so
  // they are SKIPPED rather than crashing the run -- a stack trace ends the suite, and a
  // mutant that ends the suite tells you less than one that reddens a named line.
  const ready = [A, B, C, D, E].every((p) => p && p.model);

  // ── B. TWO MAPS ON ONE SCREEN, NO INTERFERENCE ───────────────────────────────
  {
    // 🔴 THE GATE FOR EVERYTHING BELOW. A panel whose answer was cancelled by a SIBLING'S
    // request has no model, and the sections after this dereference one. Asserting it here
    // turns that failure into a named red instead of a stack trace three sections later.
    ok('B0 every seated panel got its own answer',
      [A, B, C, D, E].every((p) => p && p.model));
    eq('B1 the shell seated every declaration', shell.panels.size, 5);
    ok('B2 each panel got its own element',
      new Set(['a', 'b', 'c', 'd', 'e'].map(elOf)).size === 5);
    ok('B3 each part got its own canvas',
      new Set(['a', 'b', 'c', 'd', 'e'].map((id) => canvasIn(elOf(id)))).size === 5);
    // The two instances hold their OWN model. This is the assertion a module-level
    // `deps`/`mountEl`/`session` breaks (see `ledger_map_panel.js`).
    ok('B4 each instance holds its own model',
      A.model && B.model && A.model !== B.model);
    eq('B5 panel A drew its own wafers cells', A.lastPaint.cells, 141);
    eq('B6 panel B drew its own wafers cells', B.lastPaint.cells, 141);
    ok('B7 the two panels loaded different rows',
      Boolean(A.model && B.model && A.model.frame.wafer !== B.model.frame.wafer));
    // Paint went into each panel's own canvas, and nowhere else.
    const ca = canvasIn(elOf('a'));
    const cb = canvasIn(elOf('b'));
    eq('B8 canvas A received A cells', ca.ops.filter((o) => o.op === 'fill').length, 141);
    eq('B9 canvas B received B cells', cb.ops.filter((o) => o.op === 'fill').length, 141);
    ok('B10 the shell wrote placement, the part did not',
      elOf('a').style.gridColumn === '1 / span 1'
      && elOf('b').style.gridColumn === '2 / span 1');
    ok('B11 a panel element carries its declaration id',
      elOf('b').getAttribute('data-panel') === 'b');
    ok('B12 both panels report ready', elOf('a') && byClass(elOf('a'), 'rb-map')
      .every((n) => n.getAttribute('data-map-state') === 'ready'));

    // 🔴 THE LATTICE IS THE FRAME'S. The measured fixture declares `grid_cols/grid_rows` 15
    //    while its 141 cells span 0..13, so a map laid out on the CELLS draws this wafer
    //    14x14: the empty column and row do not shrink, they disappear, and nothing on screen
    //    says the shape changed. `grid` arrives as a JSON string, which is the other half of
    //    why this went unnoticed -- `frame.grid.grid_cols` is quietly `undefined`.
    eq('B13 the map lays out on the grid the frame declares', A._layout && A._layout.cols, 15);
    eq('B14 ... rows too, not the cells bounding box', A._layout && A._layout.rows, 15);
    // 「빈 자리」 and 「없는 자리」 are different sentences; before this round both were nothing.
    eq('B15 a declared seat with no cell holds its place', A.lastPaint.vacant, 15 * 15 - 141);
  }

  // ── C. TWO MARKING NAMES: same name lights, different name does not ──────────
  if (ready) {
    const target = A.model.cells[70];
    const paintsBefore = { b: canvasIn(elOf('b')).paints, d: canvasIn(elOf('d')).paints };
    // 🔴 THE RING CHANNEL CARRIES TWO MEANINGS NOW -- an empty declared seat is an outline
    //    too -- so "count the strokes" stopped being a question about marks the day the
    //    lattice started holding its empty seats. The GROUND's stroke colours are sampled
    //    here, before any mark exists, and a mark is a stroke in a colour that was not
    //    already on the canvas. Nothing about the tone is written down twice.
    const groundStroke = new Set(canvasIn(elOf('a')).ops
      .filter((o) => o.op === 'stroke').map((o) => o.color));
    const markStrokes = (id) => canvasIn(elOf(id)).ops
      .filter((o) => o.op === 'stroke' && !groundStroke.has(o.color));
    A.mark(target.nodeId, SIGN.CASE);

    eq('C1 the mark landed under the name A writes',
      markings.signOf('marking:1', target.nodeId), SIGN.CASE);
    eq('C2 it did not land under any other name',
      markings.signOf('marking:2', target.nodeId), SIGN.ABSENT);
    // Same name -> the other panel lit, WITHOUT the two knowing each other.
    eq('C3 the panel reading the same name repainted a mark', C.lastPaint.marks, 1);
    eq('C4 the writing panel shows its own mark', A.lastPaint.marks, 1);
    // Different name, IDENTICAL node ids -> nothing.
    eq('C6 a panel reading another name did not even repaint',
      canvasIn(elOf('d')).paints, paintsBefore.d);
    // 🔴 C5 FORCES THE REPAINT BEFORE ASKING, AND THE FIRST DRAFT DID NOT -- which made it
    // BLIND. `lastPaint` only moves when a panel repaints, and D is not subscribed to the
    // name that changed, so a component reading a HARDCODED name (mutant M2) sailed past a
    // check that was really only re-reading a stale number. Asking after a forced render is
    // what makes this a question about the READ path.
    D.render();
    eq('C5 the panel reading another name has no marks', D.lastPaint.marks, 0);
    eq('C7 the other wafers panel is untouched', B.lastPaint.marks, 0);
    ok('C8 the other wafers panel did not repaint',
      canvasIn(elOf('b')).paints === paintsBefore.b);
    // The mark is drawn as a ring ON TOP, not as a replacement cell.
    const strokes = markStrokes('a');
    eq('C9 exactly one ring was stroked', strokes.length, 1);
    ok('C10 the ring is drawn after the ground',
      canvasIn(elOf('a')).ops.indexOf(strokes[0])
      > canvasIn(elOf('a')).ops.findIndex((o) => o.op === 'fill'));

    // The control sign is REACHABLE and looks different from a case (brief 9, acceptance I).
    // 🔴 IT IS ADDED, NOT MARKED. A plain mark REPLACES now (the owner's selection model), so
    //    two signs standing together is what ctrl+click is FOR. Asserting it with a plain
    //    mark would be asserting the defect that was just removed.
    const other = A.model.cells[71];
    A.mark(other.nodeId, SIGN.CONTROL, 'add');
    eq('C11 a control mark is stored as -1',
      markings.signOf('marking:1', other.nodeId), SIGN.CONTROL);
    const rings = markStrokes('a');
    eq('C12 both marks are drawn', rings.length, 2);
    ok('C13 case and control are not the same colour',
      new Set(rings.map((r) => r.color)).size === 2);

    // Unmark, and the reader follows back down. Toggling lives in `add` and only there.
    A.mark(target.nodeId, SIGN.CASE, 'add');
    eq('C14 re-adding the same sign clears it',
      markings.signOf('marking:1', target.nodeId), SIGN.ABSENT);
    eq('C15 the reading panel followed the clear', C.lastPaint.marks, 1);

    // ── THE SELECTION MODEL ITSELF ────────────────────────────────────────────
    // 🔴 「클릭하면 초기화되고 새로」. A plain click empties the name first: without this, a
    //    reader who wants to look at ONE die has to undo every earlier click, which is the
    //    friction the owner reported.
    A.mark(A.model.cells[10].nodeId, SIGN.CASE, 'add');
    A.mark(A.model.cells[11].nodeId, SIGN.CASE, 'add');
    ok('C21 add accumulates', markings.count('marking:1') >= 2);
    A.mark(A.model.cells[12].nodeId, SIGN.CASE);
    eq('C22 a plain mark replaces everything under that name', markings.count('marking:1'), 1);
    eq('C23 ... and what is left is the one just marked',
      markings.signOf('marking:1', A.model.cells[12].nodeId), SIGN.CASE);
    A.mark(A.model.cells[12].nodeId, SIGN.CASE);
    eq('C24 a plain mark never toggles itself off',
      markings.signOf('marking:1', A.model.cells[12].nodeId), SIGN.CASE);
    // The modifier reading is ONE definition, shared by every part.
    const plain = markingIntent({});
    const ctrl = markingIntent({ ctrlKey: true });
    const shift = markingIntent({ shiftKey: true });
    const both = markingIntent({ ctrlKey: true, shiftKey: true });
    ok('C25 a plain click replaces with a case',
      plain.mode === 'replace' && plain.sign === SIGN.CASE);
    eq('C26 ctrl adds', ctrl.mode, 'add');
    eq('C27 shift picks the control sign', shift.sign, SIGN.CONTROL);
    ok('C28 ctrl+shift adds a control',
      both.mode === 'add' && both.sign === SIGN.CONTROL);

    // ── MARKING IS DRAWN BY ATTENUATION ───────────────────────────────────────
    // Measured in the owner's Spotfire: the marked point keeps its strength and everything
    // else fades. A hit that is only decorated has to be found; a faded field does not.
    const fillsOf = (id) => canvasIn(elOf(id)).ops.filter((o) => o.op === 'fill');
    // 🔴 AND NOTHING FADES WHILE NOTHING IS MARKED. B reads a name nobody has written, and
    //    drawing it faded would say 「전부 아니다」 where the truth is 「아직 안 골랐다」.
    ok('C29 nothing fades while nothing is marked',
      fillsOf('b').every((o) => String(o.color).length <= 7));
    ok('C30 a mark fades the rest of the wafer',
      fillsOf('a').some((o) => String(o.color).length === 9));
    ok('C31 the marked cell itself keeps full strength',
      fillsOf('a').some((o) => String(o.color).length === 7));

    // 🔴 THE BADGE COUNTS WHAT THIS MAP DREW, not the size of the name. A node of another
    //    kind written under the same name used to make it read 「표시 1」 over an untouched
    //    wafer -- the number was about the name, the sentence was about the map.
    markings.set('marking:2', 'ledger-quantity:v1:not-a-cell-of-any-map', SIGN.CASE);
    const badgeB = walk(elOf('b')).find((n) => n.getAttribute('data-reads') === 'marking:2');
    ok('C32 the badge counts this maps own cells',
      /표시 0$/.test(String(badgeB && badgeB.textContent)),
      String(badgeB && badgeB.textContent));
    markings.set('marking:2', 'ledger-quantity:v1:not-a-cell-of-any-map', SIGN.ABSENT);

    // Leave the name holding exactly one case, as the block below expects.
    A.mark(target.nodeId, SIGN.CASE);

    // A click at a coordinate resolves to the cell under it.
    const cell = A.model.cells[5];
    const layoutOf = A._layout;
    const px = (layoutOf.originX + (cell.x - layoutOf.minX + 0.5) * layoutOf.cell) / A.dpr;
    const py = (layoutOf.originY + (cell.y - layoutOf.minY + 0.5) * layoutOf.cell) / A.dpr;
    eq('C16 a click resolves to the cell under it', A.clickAt(px, py, false), cell.nodeId);
    eq('C17 that click marked it', markings.signOf('marking:1', cell.nodeId), SIGN.CASE);
    eq('C18 a shift-click writes the control sign',
      A.clickAt(px, py, true) && markings.signOf('marking:1', cell.nodeId), SIGN.CONTROL);
    ok('C19 a click outside every cell marks nothing', A.clickAt(-50, -50, false) === null);
    // A panel that declares no write name is inert.
    const readOnly = C.model.cells[3];
    C.mark(readOnly.nodeId, SIGN.CASE);
    eq('C20 a panel with no write name writes nothing',
      markings.signOf('marking:1', readOnly.nodeId), SIGN.ABSENT);
  }

  // ── D. A THIRD MARKING NAME, WITH NO CODE CHANGE ─────────────────────────────
  if (ready) {
    const target = E.model.cells[20];
    E.mark(target.nodeId, SIGN.CASE);
    eq('D1 a third name accepts a mark', markings.signOf('marking:3', target.nodeId),
      SIGN.CASE);
    eq('D2 the third-name panel painted it', E.lastPaint.marks, 1);
    // And it is genuinely a third context: the first two do not see it, even though A and E
    // are looking at the SAME wafer and therefore the same node ids.
    eq('D3 name one does not see it', markings.signOf('marking:1', target.nodeId),
      SIGN.ABSENT);
    eq('D4 name two does not see it', markings.signOf('marking:2', target.nodeId),
      SIGN.ABSENT);
    // Three names carrying marks AT THE SAME TIME. `names()` reports what is written, so
    // marking:2 has to actually be written for this to say anything.
    B.mark(B.model.cells[4].nodeId, SIGN.CASE);
    ok('D5 the store now reports three names at once',
      ['marking:1', 'marking:2', 'marking:3'].every((n) => markings.names().includes(n)),
      `names: ${markings.names().join(',')}`);
    eq('D6 the third name did not disturb the second', markings.count('marking:2'), 1);
  }

  // ── E. RESIZE: THE MAP FOLLOWS ITS BOX ───────────────────────────────────────
  if (ready) {
    const ca = canvasIn(elOf('a'));
    const widthBefore = ca.width;
    const cellBefore = A._layout.cell;
    eq('E1 the canvas took the box it was given', widthBefore, 400);
    observe.fireFor(elOf('a'), 800, 600);
    ok('E2 the canvas followed the new box', ca.width === 800 && ca.height === 600);
    ok('E3 the dies got bigger with the box', A._layout.cell > cellBefore);
    eq('E4 every cell is still drawn after a resize', A.lastPaint.cells, 141);
    // Only the panel that was resized moved.
    eq('E5 a resize of one panel does not resize another', canvasIn(elOf('b')).width, 400);
    // Down as well as up, and to a size no code has ever seen.
    observe.fireFor(elOf('a'), 137, 91);
    ok('E6 the canvas follows downward too',
      canvasIn(elOf('a')).width === 137 && canvasIn(elOf('a')).height === 91);
    eq('E7 no cell is lost at a small size', A.lastPaint.cells, 141);
    // Hit testing uses the CURRENT layout, not the one it was drawn with first.
    const cell = A.model.cells[9];
    const l = A._layout;
    const px = (l.originX + (cell.x - l.minX + 0.5) * l.cell) / A.dpr;
    const py = (l.originY + (cell.y - l.minY + 0.5) * l.cell) / A.dpr;
    eq('E8 clicks land on the right cell after a resize', A.hitCell(px, py), cell);
    observe.fireFor(elOf('a'), 400, 300);
  }

  // ── F. NO MODULE-LEVEL STATE IN A COMPONENT ──────────────────────────────────
  {
    // The scan: a mutable binding at column 0 is module state. That is the exact shape of the
    // measured defect (`let deps = null; let mountEl = null; let session = 0;`).
    const scan = (text) => text.split(/\r?\n/)
      .filter((line) => /^(let|var)\s/.test(line))
      .map((line) => line.trim());
    for (const file of ['panel.js', 'map_panel.js', 'grid_shell.js', 'marking_store.js']) {
      // The text the suite is actually DRIVING (see `loadModules`), not the file on disk.
      const found = scan(mods.sources[file]);
      eq(`F1 ${file} declares no module-level mutable state`, found.join(' | '), '');
    }
    // 🔴 THE POSITIVE CONTROL. If the scan cannot see the defect it was written for, its
    // silence above means nothing. `ledger_map_panel.js` is the measured original.
    const legacy = scan(readFileSync(path.join(SRC_DIR, 'ledger_map_panel.js'), 'utf8'));
    ok('F2 the scan finds the measured defect in ledger_map_panel.js', legacy.length >= 3,
      `found ${legacy.length}`);
    // And the behavioural half: two fresh instances share nothing.
    const doc2 = makeDoc('light');
    const h1 = doc2.createElement('div');
    const h2 = doc2.createElement('div');
    const store2 = new MarkingStore();
    const p1 = new MapPanel(h1, { doc: doc2, markings: store2, reads: 'x', writes: 'x',
      axis: 'bond', load: () => Promise.resolve(FIX_07) });
    const p2 = new MapPanel(h2, { doc: doc2, markings: store2, reads: 'y', writes: 'y',
      axis: 'bond', load: () => Promise.resolve(FIX_03) });
    p1.mount(); p2.mount();
    await flush();
    p1.resize(200, 200); p2.resize(300, 300);
    ok('F3 two bare instances keep separate boxes',
      p1.box.width === 200 && p2.box.width === 300);
    ok('F4 two bare instances keep separate models',
      Boolean(p1.model && p2.model && p1.model.frame.wafer !== p2.model.frame.wafer));
    p1.destroy();
    if (p2.model) store2.set('y', p2.model.cells[0].nodeId, SIGN.CASE);
    eq('F5 destroying one instance does not deafen the other', p2.lastPaint.marks, 1);
  }

  // ── H. THE COMPOSITION ROOT DECLARES THE SCREEN ──────────────────────────────
  {
    // 🔴 H1 WAS `panels.length === 2`, AND THAT IS THE DEFECT THIS ROUND FIXED: four parts were
    //    built, registered and NEVER SEATED, and no assertion here could tell. It now pins the
    //    MEMBERS -- every registered part stands on the screen -- so registering a part without
    //    seating it goes red at the moment it happens, which is when it is cheap.
    const seated = new Set(BOARD.panels.map((p) => p.part));
    ok('H1 every registered part is seated on the screen',
      Object.keys(PARTS).every((name) => seated.has(name)),
      `registered ${Object.keys(PARTS).join(',')} | seated ${[...seated].join(',')}`);
    const maps = BOARD.panels.filter((p) => p.part === 'map');
    ok('H2 one part stands twice on the same screen', maps.length >= 2);
    ok('H3 the two instances read different marking names',
      maps[0].reads !== maps[1].reads);
    ok('H4 every declared part is registered',
      BOARD.panels.every((p) => Boolean(PARTS[p.part])));
    ok('H5 placement is in the declaration, not in the part',
      BOARD.panels.every((p) => p.at && p.at.column && p.at.row));
    ok('H6 the declaration is data, with no functions in it',
      BOARD.panels.every((p) => Object.values(p.options || {})
        .every((v) => typeof v !== 'function')));
    const bound = bindLoaders(BOARD, { apiBase: 'http://example', dpr: 2 });
    // Only a panel that DECLARED a question gets a loader; the rest are handed the address and
    // ask their own route. Asserting `every` here would have been asserting that every part is
    // a map.
    const asked = bound.panels.filter((p, i) => (BOARD.panels[i].options || {}).question);
    ok('H7 binding turns a question into a loader',
      asked.length > 0 && asked.every((p) => typeof p.options.load === 'function'));
    ok('H7b a panel with no question is still handed the address',
      bound.panels.every((p) => p.options.apiBase === 'http://example'));
    ok('H8 binding does not mutate the declaration',
      BOARD.panels.every((p) => typeof (p.options || {}).load === 'undefined'));
    ok('H9 the device ratio reaches the parts',
      bound.panels.every((p) => p.options.dpr === 2));
  }

  shell.destroy();
  eq('I1 destroying the shell empties the host', host.children.length, 0);

  return { ran, failures };
}

// ── M. THE MUTATION CORPUS ─────────────────────────────────────────────────────────
//
// Each entry names the assertion that MUST go red. A mutant that is caught by nothing, or by
// the wrong thing, is reported as a hole in the suite.

const MUTANTS = [
  {
    id: 'M1',
    what: 'map_panel.js keeps its session counter at MODULE level (the ledger_map_panel defect)',
    catches: 'B5',
    mutate: {
      'map_panel.js': (s) => s
        .replace('const CHROME = Object.freeze({', 'let __session = 0;\nconst CHROME = Object.freeze({')
        .replace('    this._session = 0;', '')
        .replaceAll('this._session', '__session'),
    },
  },
  {
    id: 'M2',
    what: 'panel.js reads a HARDCODED marking name instead of the one it was declared with',
    catches: 'C5',
    mutate: {
      'panel.js': (s) => s.replace(
        'return this.markings.signOf(this.reads, nodeId);',
        "return this.markings.signOf('marking:1', nodeId);"),
    },
  },
  {
    id: 'M3',
    what: 'marking_store.js allows only two names (the hardcoded roster)',
    catches: 'D1',
    mutate: {
      'marking_store.js': (s) => s.replace(
        '    const next = normaliseSign(sign);',
        "    if (name !== 'marking:1' && name !== 'marking:2') return SIGN.ABSENT;\n"
        + '    const next = normaliseSign(sign);'),
    },
  },
  {
    id: 'M4',
    what: 'map_panel.js bakes in a fixed canvas size (the 560px the order warns about)',
    catches: 'E2',
    mutate: {
      'map_panel.js': (s) => s
        .replace('      width: Math.max(0, this.box.width),', '      width: 400,')
        .replace('      height: Math.max(0, this.box.height - headH - noteH),', '      height: 300,'),
    },
  },
  {
    id: 'M5',
    what: 'map_panel.js gains one module-level mutable binding',
    catches: 'F1 map_panel.js',
    mutate: { 'map_panel.js': (s) => `let leaked = null;\n${s}` },
  },
  {
    id: 'M6',
    what: 'grid_shell.js seats every panel in ONE shared element',
    catches: 'B2',
    mutate: {
      'grid_shell.js': (s) => s
        .replace('    this.panels = new Map();   // id -> {el, part, disconnect}',
          '    this.panels = new Map();\n    this._shared = null;')
        .replace('      const el = doc.createElement(\'div\');',
          '      const el = this._shared || (this._shared = doc.createElement(\'div\'));'),
    },
  },
  {
    id: 'M7',
    what: 'api.js drops the servers refusal and calls every projection drawable',
    catches: 'G9',
    mutate: {
      'api.js': (s) => s.replace("    drawable: p.state === 'ready',",
        '    drawable: true,'),
    },
  },
  {
    id: 'M8',
    what: 'map_panel.js paints marks with one colour, so control and case look identical',
    catches: 'C13',
    mutate: {
      'map_panel.js': (s) => s.replace(
        "        layout, palette.control, 'ring').painted;",
        "        layout, palette.case, 'ring').painted;"),
    },
  },
  {
    id: 'M14',
    what: 'map_panel.js stops attenuating, so a mark is decorated instead of the rest fading',
    catches: 'C30',
    mutate: {
      'map_panel.js': (s) => s.replace(
        '    const attenuating = cells.some((c) => this.signOf(c.nodeId) !== SIGN.ABSENT);',
        '    const attenuating = false;'),
    },
  },
  {
    id: 'M15',
    what: 'map_panel.js fades the wafer before anything is marked (unchosen drawn as rejected)',
    catches: 'C29',
    mutate: {
      'map_panel.js': (s) => s.replace(
        '    const attenuating = cells.some((c) => this.signOf(c.nodeId) !== SIGN.ABSENT);',
        '    const attenuating = true;'),
    },
  },
  {
    id: 'M16',
    what: 'the map badge counts the whole marking name again, not its own cells',
    catches: 'C32',
    mutate: {
      'map_panel.js': (s) => s.replace(
        '    for (const cell of ownCells) if (this.signOf(cell.nodeId) !== SIGN.ABSENT) marked += 1;',
        '    marked = this.markings && this.reads ? this.markings.count(this.reads) : 0;'),
    },
  },
  {
    id: 'M12',
    what: 'panel.js goes back to accumulating on every click (the reported friction)',
    catches: 'C22',
    mutate: {
      'panel.js': (s) => s.replace(
        "    if (mode === 'add') return this.markings.toggle(this.writes, nodeId, sign);",
        '    return this.markings.toggle(this.writes, nodeId, sign);'),
    },
  },
  {
    id: 'M13',
    what: 'panel.js reads ctrl as the SIGN key, so ctrl+click stops accumulating',
    catches: 'C26',
    mutate: {
      'panel.js': (s) => s.replace(
        "    mode: (e.ctrlKey || e.metaKey) ? 'add' : 'replace',",
        "    mode: e.altKey ? 'add' : 'replace',"),
    },
  },
  {
    id: 'M10',
    what: 'map_panel.js lays the wafer out on the cells bounding box, ignoring the declared frame',
    catches: 'B13',
    mutate: {
      'map_panel.js': (s) => s.replace(
        '    const bounds = declared ? unionBounds(declared, boundsOf(cells)) : boundsOf(cells);',
        '    const bounds = boundsOf(cells);'),
    },
  },
  {
    id: 'M11',
    what: 'map_panel.js reads frame.grid as an object, so the served JSON string parses to nothing',
    catches: 'B13',
    mutate: {
      'map_panel.js': (s) => s.replace(
        "  if (typeof grid !== 'string') return null;",
        "  if (typeof grid !== 'object') return null;"),
    },
  },
  {
    id: 'M9',
    what: 'map_panel.js drops cells whose role it does not recognise',
    catches: 'B5',
    mutate: {
      'map_panel.js': (s) => s.replace(
        "      const role = cell.colorRole || 'unknown';",
        "      const role = cell.colorRole || 'unknown';\n      if (role === 'unscanned') continue;"),
    },
  },
];

// ── run ────────────────────────────────────────────────────────────────────────────

let outerRan = 0;
const outerFailures = [];
const record = (name, cond, detail) => {
  outerRan += 1;
  if (!cond) outerFailures.push(detail ? `${name}: ${detail}` : name);
};

const baseline = await suite(await loadModules());
console.log(`baseline: ${baseline.ran} assertions, ${baseline.failures.length} failed`);
for (const f of baseline.failures) console.log(`  FAIL ${f}`);
record('BASELINE is green', baseline.failures.length === 0,
  baseline.failures.join(' / '));
record('BASELINE measured something', baseline.ran > 60, `ran ${baseline.ran}`);

for (const m of MUTANTS) {
  let red = null;
  let crashed = null;
  try {
    red = await suite(await loadModules(m.mutate));
  } catch (err) {
    crashed = String((err && err.message) || err);
  }
  if (crashed) {
    // A mutant that kills the suite outright is CAUGHT, but say so out loud: a crash is not
    // the same evidence as a named assertion going red.
    console.log(`${m.id} CRASHED the suite: ${crashed.slice(0, 120)}`);
    record(`${m.id} is caught`, true);
    continue;
  }
  const hit = red.failures.some((f) => f.startsWith(m.catches));
  console.log(`${m.id} ${hit ? 'caught by' : 'NOT CAUGHT, expected'} ${m.catches}`
    + ` (${red.failures.length} red) -- ${m.what}`);
  record(`${m.id} is caught by ${m.catches}`, hit,
    red.failures.length ? `red instead: ${red.failures.slice(0, 3).join(' / ')}` : 'nothing went red');
}

for (const f of outerFailures) console.log(`FAIL ${f}`);
console.log(`ASSERTIONS ${outerRan + baseline.ran} ${outerFailures.length}`);
process.exit(outerFailures.length ? 1 : 0);
