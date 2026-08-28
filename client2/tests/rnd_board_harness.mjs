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
  // 🔴 스타일시트도 «채점 대상»입니다. 오늘 화면을 깬 것은 자바스크립트가 아니라 CSS 한 줄
  //    (flex-wrap)이었고, 소스에 안 읽어 두면 그 부류는 변이도 단언도 못 겁니다.
  read('board.css');
  const storeUrl = dataUrl(read('marking_store.js'));
  const apiUrl = dataUrl(read('api.js'));
  const panelUrl = dataUrl(read('panel.js')
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  const mapUrl = dataUrl(read('map_panel.js')
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`)
    .replaceAll("'./api.js'", `'${apiUrl}'`)
    .replaceAll("'../map2/painter.js'", `'${srcUrl('map2/painter.js')}'`)
    .replaceAll("'../map2/seating.js'", `'${srcUrl('map2/seating.js')}'`));
  const shellUrl = dataUrl(read('grid_shell.js'));
  const interUrl = dataUrl(read('marking_intersection.js')
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  // Round 2's parts are imported by `main.js` too, so they have to be rewired here or the
  // composition root cannot load at all -- which is how it failed the moment they landed.
  const tableUrl = dataUrl(read('table_part.js')
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  const partUrl = (file) => dataUrl(read(file)
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`)
    .replaceAll("'./table_part.js'", `'${tableUrl}'`)
    .replaceAll("'./api.js'", `'${apiUrl}'`));
  const headUrl = partUrl('head_summary_panel.js');
  const compUrl = partUrl('composition_panel.js');
  const candUrl = partUrl('candidate_list_panel.js');
  const rankUrl = partUrl('rank_list_panel.js');
  const ctlUrl = partUrl('control_bar_panel.js');
  const trendUrl = partUrl('main_trend_panel.js');
  const statusUrl = partUrl('marking_status_panel.js');
  const declUrl = partUrl('declaration_panel.js');
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
    .replaceAll("'./declaration_panel.js'", `'${declUrl}'`)
    .replaceAll("'./expanded_layer_panel.js'", `'${partUrl('expanded_layer_panel.js')}'`)
    // 🔴 A PART THIS LIST FORGETS TAKES THE WHOLE HARNESS DOWN, not one assertion: the
    //    composition root's import throws ERR_INVALID_URL before a single check runs.
    //    Every part `main.js` imports has to be here.
    .replaceAll("'./reach_panel.js'", `'${partUrl('reach_panel.js')}'`)
    .replaceAll("'./walk_box_panel.js'", `'${partUrl('walk_box_panel.js')}'`)
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
  const { MapPanel, seatedProjection } = mods.map;
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
        options: { axis: 'bond', space: 'die:base', load: () => Promise.resolve(FIX_07) } },
      { id: 'b', part: 'map', title: 'B', at: { column: 2, row: 1 },
        reads: 'marking:2', writes: 'marking:2',
        options: { axis: 'bond', space: 'die:base', load: () => Promise.resolve(FIX_03) } },
      { id: 'c', part: 'map', title: 'C', at: { column: 1, row: 2 },
        reads: 'marking:1', writes: null,
        options: { axis: 'bond', space: 'die:base', load: () => Promise.resolve(FIX_07) } },
      { id: 'd', part: 'map', title: 'D', at: { column: 2, row: 2 },
        reads: 'marking:2', writes: null,
        options: { axis: 'bond', space: 'die:base', load: () => Promise.resolve(FIX_07) } },
      // 🔴 THE THIRD NAME. Nothing in any module knows this string exists.
      { id: 'e', part: 'map', title: 'E', at: { column: 1, row: 3 },
        reads: 'marking:3', writes: 'marking:3',
        options: { axis: 'bond', space: 'die:base', load: () => Promise.resolve(FIX_07) } },
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

    // 🔴 ROTATION IS READ, NOT ASSUMED -- and this is the one defect a PICTURE CANNOT SHOW.
    //    The measured bond frame declares `rotation: 180` (dt and core declare 0). Drawing the
    //    stored coordinate puts this wafer on screen upside down and it still looks like a
    //    wafer; it only becomes an answer when one marking crosses two maps and the second one
    //    lights the wrong die. So the assertion is not 「그려진다」 -- it is that the seats MOVE,
    //    and that they move as a MIRROR rather than as any translation.
    {
      const bond = FIX_07.projections.find((pr) => pr.axis === 'bond');
      const grid = JSON.parse(bond.frame.grid);
      const cells = (bond.cells || []).slice(0, 40).map((c) => ({ ...c }));
      const seatsAt = (rotation) => seatedProjection(
        { grid: JSON.stringify({ ...grid, rotation }) }, cells,
      ).cells.map((c) => [c.x, c.y]);
      const at0 = seatsAt(0);
      const at180 = seatsAt(180);
      const moved = at0.filter((s, i) => s[0] !== at180[i][0] || s[1] !== at180[i][1]);
      ok('B16 a 180 frame does not seat its cells where a 0 frame would',
        cells.length > 0 && moved.length === cells.length,
        `${moved.length}/${cells.length} moved`);
      const sums = new Set();
      const shifts = new Set();
      at0.forEach((s, i) => {
        sums.add(`${s[0] + at180[i][0]},${s[1] + at180[i][1]}`);
        shifts.add(`${at180[i][0] - s[0]},${at180[i][1] - s[1]}`);
      });
      eq('B17 ... it is a MIRROR: every pair of seats sums to the one same point', sums.size, 1);
      ok('B18 ... which no translation of the whole map could do', shifts.size > 1,
        `${shifts.size} distinct shifts`);
    }
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
    // 🔴 목업은 맵 «머리»에 마킹 수를 답니다. 배지에만 있으면 「이 그림에서 몇 개를 골랐나」가
    //    수로 안 보입니다 -- 이 화면에서 제일 자주 묻는 수입니다.
    const headCounts = byClass(elOf('a'), 'rb-map__counts')[0];
    ok('C34 the map head carries the marking count beside the cell counts',
      Boolean(headCounts) && /^마킹 1 · /.test(headCounts.textContent),
      String(headCounts && headCounts.textContent).slice(0, 60));

    // A click at a coordinate resolves to the cell under it.
    // 🔴 SEATED, NOT STORED. The panel draws where the FRAME says the die sits (this fixture's
    //    bond frame declares `rotation: 180`), so the pixel for a cell must be computed from
    //    its seat. Taking `model.cells[5]` -- the stored coordinate -- asks about a die that is
    //    on screen somewhere else entirely.
    const cell = [...A._byXY.values()][5];
    const layoutOf = A._layout;
    const px = (layoutOf.originX + (cell.x - layoutOf.minX + 0.5) * layoutOf.cell) / A.dpr;
    const py = (layoutOf.originY + (cell.y - layoutOf.minY + 0.5) * layoutOf.cell) / A.dpr;
    // 🔴 THE MARKING GATE (Lead PM ruling, 2026-08-24). `lot_map` cells carry no node id, so
    //    the boundary STAMPS one to draw with -- and a stamped id is not a node. A marking is
    //    the subject of the next walk, so marking a stamped id would send that walk to a node
    //    that does not exist and it would answer 「없음」 for a die that is on screen. The gate
    //    is the flag the boundary already sets, and the refusal is SAID, not swallowed.
    ok('C16 a seat the server never named cannot be marked',
      cell.nodeIdResolved !== true && A.clickAt(px, py, false) === null,
      `resolved=${cell.nodeIdResolved}`);
    eq('C17 ... and nothing was written under that id',
      markings.signOf('marking:1', cell.nodeId), SIGN.ABSENT);
    ok('C18 ... and the panel says why',
      /노드가 없습니다/.test(String(byClass(elOf('a'), 'rb-map__note')[0]
        && byClass(elOf('a'), 'rb-map__note')[0].textContent)),
      String(byClass(elOf('a'), 'rb-map__note')[0]
        && byClass(elOf('a'), 'rb-map__note')[0].textContent));
    // 🔴 AND IT OPENS BY ITSELF. Nothing here changes the code path -- only the flag the route
    //    will set the day it ships an id. This is the assertion that keeps the gate from
    //    becoming a wall nobody notices.
    const named = A.model.cells[6];
    named.nodeId = 'ledger-entity:v1:a-real-node-the-server-named';
    named.nodeIdResolved = true;
    A.render();
    const seatedNamed = [...A._byXY.values()].find((c) => c.nodeId === named.nodeId);
    const nx = (A._layout.originX + (seatedNamed.x - A._layout.minX + 0.5) * A._layout.cell) / A.dpr;
    const ny = (A._layout.originY + (seatedNamed.y - A._layout.minY + 0.5) * A._layout.cell) / A.dpr;
    eq('C19 a seat the server DID name marks normally', A.clickAt(nx, ny, false), named.nodeId);
    eq('C19b ... with the case sign', markings.signOf('marking:1', named.nodeId), SIGN.CASE);
    eq('C19c a shift-click writes the control sign',
      A.clickAt(nx, ny, true) && markings.signOf('marking:1', named.nodeId), SIGN.CONTROL);
    ok('C19d a click outside every cell marks nothing', A.clickAt(-50, -50, false) === null);
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
    const cell = [...A._byXY.values()][9];
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
    // silence above means nothing.
    //
    // 🔴 IT IS A LITERAL, NOT A FILE, AND THAT IS THE POINT (Lead PM ruling 2026-08-25).
    //    It used to read `src/ledger_map_panel.js` -- the measured original, three module-level
    //    bindings that made that file impossible to place twice on one page. That file was
    //    deleted with admin's 원장 선언 tab (the tab left in 9cdf224c; the chain in the commit
    //    that carries this line -- `git log -- client2/src/ledger_map_panel.js` finds it).
    //    What F2 measures was never 「that file exists」; it is 「the scan sees this SHAPE」, and
    //    the shape is reproduced exactly here. Keeping it in a file also tied the control to
    //    someone else's lifetime: a refactor of those three lines would have emptied F2
    //    SILENTLY, and F1's green would have gone with it without a word.
    const MEASURED_ORIGINAL = [
      'let deps = null;',
      'let mountEl = null;',
      'let session = 0;',
    ].join(String.fromCharCode(10));
    const legacy = scan(MEASURED_ORIGINAL);
    ok('F2 the scan finds the measured defect in the shape it was written for',
      legacy.length >= 3, `found ${legacy.length}`);
    // And the behavioural half: two fresh instances share nothing.
    const doc2 = makeDoc('light');
    const h1 = doc2.createElement('div');
    const h2 = doc2.createElement('div');
    const store2 = new MarkingStore();
    const p1 = new MapPanel(h1, { space: 'die:base', doc: doc2, markings: store2, reads: 'x', writes: 'x',
      axis: 'bond', load: () => Promise.resolve(FIX_07) });
    const p2 = new MapPanel(h2, { space: 'die:base', doc: doc2, markings: store2, reads: 'y', writes: 'y',
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

    // 🔴 확대는 «모드»가 아니라 좌표계 선언의 다른 «값»입니다 (소유자 2026-08-24). 같은 부품,
    //    같은 답, 선언 하나만 다릅니다 -- 부품 안에 `if (zoom)` 이 생기면 조립식이 안쪽에서
    //    무너집니다. 오늘 라우트는 point 에 inchip 좌표를 «안 싣습니다», 그래서 이 인스턴스는
    //    「없음」을 그리는 것이 정상이고, 싣는 날 «선언도 코드도» 안 바뀌고 켜져야 합니다.
    const zoomHost = doc2.createElement('div');
    const zoom = new MapPanel(zoomHost, { doc: doc2, markings: store2, reads: 'z', writes: 'z',
      axis: 'bond', space: 'inchip', extent: { x: 20000, y: 20000 },
      load: () => Promise.resolve(FIX_07) });
    zoom.mount();
    await flush(); await flush();
    zoom.resize(240, 180);
    eq('F6 an inchip instance draws nothing while the route ships no inchip coordinate',
      zoom.lastPaint.cells, 0);
    eq('F7 ... and the die instance beside it is untouched by that declaration',
      p2.lastPaint.cells, 141);

    // 재료가 실리는 날. 같은 선언, 같은 코드, 이번엔 그림이 나옵니다.
    // ⚠️ 오늘 그 재료는 이 부품까지 «못 옵니다» -- `projectionModel` 이 셀을 여섯 필드로
    //    줄이면서 `points` 를 버립니다. 그 파일은 응용 레인 소관이라 여기서 안 고치고
    //    보고했습니다. 그래서 단언은 «이 부품이 보증하는 것»에 겁니다: 셀이 점을 물고 있으면
    //    inchip 선언이 그것을 그린다.
    // 🔴 자리는 «점이 말합니다» -- 총괄이 승인한 `placements` 모양 그대로입니다. 같은 점이
    //    die:base 와 inchip 에 «둘 다» 있고, 확대는 그 중 다른 자리를 읽는 일입니다.
    // ⚠️ inchip 인스턴스는 이제 답을 «그대로» 모델로 씁니다 (좌표계 선언). lot_map 바디를
    //    먹이는 조합은 제품에 없으므로, 모델 모양을 직접 놓고 «자리 규칙»만 잽니다.
    zoom.model = { cells: [{ points: null }] };
    zoom.model.cells[0].points = [
      { node_id: 'ledger-entity:v1:a-point', state: 'found',
        placements: [{ space: 'die:base', x: 13, y: 5 },
          { space: 'inchip', x: 14041.75, y: 9879.75, extent: { x: 9.8, y: 8.0 } }] },
      { node_id: 'ledger-entity:v1:another-point', state: 'found',
        placements: [{ space: 'inchip', x: 5000, y: 12000 }] },
      // 🔴 그 좌표계에 «자리가 없는» 점. 조용히 빠지면 「그런 게 없다」로 읽힙니다.
      { node_id: 'ledger-entity:v1:die-only', state: 'found',
        placements: [{ space: 'die:base', x: 4, y: 9 }] },
    ];
    zoom.render();
    eq('F8 the same declaration draws the points the day a cell carries them',
      zoom.lastPaint.cells, 2);
    eq('F8b a point with no place in THIS space is counted, not dropped',
      zoom.lastPaint.offSpace, 1);

    // 🔴 갈래는 «셋»입니다 (총괄 판정). 「어느 자리에도 없다」와 「자리를 아직 안 실어 준다」는
    //    다른 말이고, 앞의 것은 데이터의 상태, 뒤의 것은 «배관»의 상태입니다. 하나로 묶으면
    //    계약이 안 온 것이 「없는 것」으로 읽힙니다 -- 오늘 화면이 꺼진 사고의 뿌리가 그것입니다.
    zoom.model.cells[0].points = [
      { node_id: 'ledger-entity:v1:no-contract-yet', state: 'found' },
      { node_id: 'ledger-entity:v1:nowhere', state: 'found', placements: [] },
    ];
    zoom.render();
    // ⚠️ 이 하니스의 `eq` 는 «===» 입니다 -- 배열을 넣으면 절대 안 맞습니다. 문자열로 잽니다.
    eq('F8c a point whose placements never arrived is 「waiting」, not 「nowhere」',
      `${zoom.lastPaint.awaitingPlaces}/${zoom.lastPaint.offSpace}`, '1/1');
    // 🔴 새 경로: 재료가 «walk 의 노드»로 옵니다 (collect:'point'). 같은 좌표계 선언, 같은
    //    placements 규칙 -- 부품에는 갈래가 «하나»도 안 늘었습니다. lot_map 이 버려지는 날
    //    옛 갈래만 지우면 됩니다.
    zoom.model = { nodes: [
      { id: 'ledger-finding-point:v1:a', finding_kind: 'void',
        placements: [{ space: 'inchip', x: 100, y: 200 }] },
      { id: 'ledger-finding-point:v1:b', finding_kind: 'void',
        placements: [{ space: 'die:base', x: 3, y: 4 }] },
      { id: 'ledger-entity:v1:no-contract', finding_kind: 'void' },
    ] };
    zoom.render();
    eq('F16 the inchip space draws the walk own nodes, not only lot_map cells',
      zoom.lastPaint.cells, 1);
    eq('F16b ... and the other two are counted apart, nowhere vs not-yet',
      `${zoom.lastPaint.offSpace}/${zoom.lastPaint.awaitingPlaces}`, '1/1');
    zoom.destroy();

    // 🔴 한 칸이 «몇 개»를 물었나가 화면에 남아야 합니다. 실측: 다이당 최대 13, 4개 이상인
    //    다이가 1,906개. 전부 같은 빨강이면 1과 13이 «같아 보이고», 그건 수를 잃는 것입니다.
    const weighHost = doc2.createElement('div');
    const weigh = new MapPanel(weighHost, { space: 'die:base', doc: doc2, markings: store2, reads: 'w', writes: 'w',
      axis: 'bond', load: () => Promise.resolve(FIX_07) });
    weigh.mount();
    await flush(); await flush();
    weigh.resize(240, 240);
    const foundCells = weigh.model.cells.filter((c) => c.colorRole === 'found');
    foundCells[0].n = 1;
    foundCells[1].n = 13;
    weigh.render();
    const fills = new Set(canvasIn(weighHost).ops.filter((o) => o.op === 'fill')
      .map((o) => o.color));
    ok('F9 a die that carries 13 findings is not drawn like one that carries 1',
      fills.size >= 4, `${fills.size} distinct fills`);
    weigh.destroy();

    // 🔴 소스가 «설 수 있다고 선언한» 좌표계에만 인스턴스가 섭니다 (소유자 2026-08-24).
    //    MI 계측은 좌표 컬럼이 «아예 없습니다» -- 그건 결함이 아니라 그 계측의 성질이고,
    //    빈 맵을 띄우면 「데이터가 없다」로 읽힙니다. 「해당 없음」은 아무것도 없는 것입니다.
    let askedNo = 0;
    const noHost = doc2.createElement('div');
    const noMap = new MapPanel(noHost, { doc: doc2, markings: store2, reads: 'q', writes: 'q',
      axis: 'bond', space: 'die:base', sourceSpaces: [],
      load: () => { askedNo += 1; return Promise.resolve(FIX_07); } });
    noMap.mount();
    await flush(); await flush();
    eq('F10 a source with no coordinate space stands no map at all', noHost.children.length, 0);
    eq('F11 ... and it does not even ask', askedNo, 0);

    let askedYes = 0;
    const yesHost = doc2.createElement('div');
    const yesMap = new MapPanel(yesHost, { doc: doc2, markings: store2, reads: 'q2', writes: 'q2',
      axis: 'bond', space: 'die:base', sourceSpaces: ['die:base', 'inchip'],
      load: () => { askedYes += 1; return Promise.resolve(FIX_07); } });
    yesMap.mount();
    await flush(); await flush();
    yesMap.resize(200, 200);
    ok('F12 the same part stands when the source declares that space',
      askedYes === 1 && yesHost.children.length > 0 && yesMap.lastPaint.cells === 141,
      `asked ${askedYes} · children ${yesHost.children.length} · cells ${yesMap.lastPaint.cells}`);
    noMap.destroy(); yesMap.destroy();

    // 🔴 이 회귀의 «모양»입니다 (총괄 실측 2026-08-24: 8080 에서 칠해진 픽셀 0%). 부품의
    //    테두리는 전부 정상이고 -- 머리·수치·기반·페이저·배지 -- «그리는 자리»만 비어 있었고,
    //    요소를 세는 검사는 그것을 「정상」으로 읽습니다. 그래서 단언은 「요소가 있다」가 아니라
    //    「무엇이 «얼마나» 그려졌다」입니다.
    //    원인 후보 중 코드로 막을 수 있는 것: box 가 resize 콜백에서«만» 왔다는 것. 콜백이
    //    한 번도 안 오면 캔버스는 크기조차 못 받습니다. 이제 호스트에게 직접 묻습니다.
    const blindHost = doc2.createElement('div');
    blindHost.getBoundingClientRect = () => ({ width: 300, height: 240 });
    const blind = new MapPanel(blindHost, { space: 'die:base', doc: doc2, markings: store2, reads: 'b', writes: 'b',
      axis: 'bond', load: () => Promise.resolve(FIX_07) });
    blind.mount();
    await flush(); await flush();
    // resize() 는 «한 번도» 부르지 않습니다 -- 관찰자가 없는 자리를 흉내 냅니다.
    const blindCanvas = canvasIn(blindHost);
    const inkOps = blindCanvas ? blindCanvas.ops.filter((o) => o.op === 'fill') : [];
    const inked = inkOps.reduce((sum, o) => sum + Math.abs(o.w * o.h), 0);
    ok('F13 the first paint does not wait for a resize callback',
      Boolean(blindCanvas) && blindCanvas.width > 0 && blindCanvas.height > 0,
      blindCanvas ? `${blindCanvas.width}x${blindCanvas.height}` : 'no canvas');
    ok('F14 ... and it inks AREA, not just elements',
      inkOps.length >= 141 && inked > 0.2 * blindCanvas.width * blindCanvas.height,
      `${inkOps.length} fills · ${Math.round(inked)} of ${blindCanvas.width * blindCanvas.height}`);
    blind.destroy();

    // 🔴 선언한 이름이 «셋»이면 배지도 셋을 말합니다. 총괄이 marking:1 을 건드렸더니
    //    「읽기 marking:2」라 적힌 패널이 따라 움직였고, 배지만 보면 «거짓말»로 보였습니다 --
    //    실제로는 페이지가 세 번째 이름을 따라간 것입니다. 감추면 패널이 자기 선언을 어기는
    //    것처럼 읽힙니다.
    const followHost = doc2.createElement('div');
    const follower = new MapPanel(followHost, { space: 'die:base', doc: doc2, markings: store2,
      reads: 'marking:2', writes: 'marking:2', pageFollows: 'subject:wafer',
      axis: 'bond', load: () => Promise.resolve(FIX_07), loadByWafer: () => Promise.resolve(FIX_03) });
    follower.mount();
    await flush(); await flush();
    const badge = walk(followHost).find((n) => n.getAttribute && n.getAttribute('data-follows'));
    ok('F15 the badge names what the page follows, not only what it reads and writes',
      Boolean(badge) && /따라감 subject:wafer/.test(badge.textContent),
      String(badge && badge.textContent));
    follower.destroy();

    // 🔴 주어가 «아직 없는» 인스턴스는 묻지 않습니다. 물으면 라우트가 422 로 거절하고 화면엔
    //    「서버가 거절했습니다」가 떠서, 「아직 안 골랐다」가 «서버 잘못»으로 읽힙니다.
    let askedZoom = 0;
    const zoomHost2 = doc2.createElement('div');
    const zoom3 = new MapPanel(zoomHost2, { doc: doc2, markings: store2,
      reads: 'm:zoom', writes: 'm:zoom', start: { groupby: 'wafer', marking: 'm:zoom' },
      space: 'inchip', extent: { x: 20000, y: 20000 },
      load: () => { askedZoom += 1; return Promise.resolve({ nodes: [] }); } });
    zoom3.mount();
    await flush(); await flush();
    eq('F17 a map whose marking is empty does not ask', askedZoom, 0);
    ok('F17b ... and says it is waiting, not that the server refused',
      /비었습니다/.test(zoomHost2.textContent) && !/거절/.test(zoomHost2.textContent),
      zoomHost2.textContent.slice(0, 80));
    zoom3.destroy();
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
    // 🔴 «자리»가 아니라 «구성원»으로 잽니다. 셋째 맵(칩 확대)이 앞에 앉는 순간 maps[0]과
    //    maps[1] 이 같은 이름을 읽게 되는데, 그건 「한 부품이 여러 이름으로 선다」가 깨진 것이
    //    아닙니다 -- 자리로 세는 단언이 정당한 추가를 결함으로 찍는 그 부류입니다.
    // 🔴 기본값으로 떨어지면 placements 가 오는 «날» 모든 점이 아무 데도 안 맞습니다 --
    //    옛 경로가 그리는 동안은 «이상이 없어 보이는» 부류입니다 (총괄 판정 2026-08-24).
    const spaces = maps.map((pp) => (pp.options || {}).space);
    ok('H3b every seated map declares its coordinate space, none falls to a default',
      spaces.every(Boolean), spaces.join(' | '));
    ok('H3c and the bonding and core maps declare DIFFERENT grids',
      new Set(spaces.filter((x) => String(x).startsWith('die:'))).size >= 2, spaces.join(' | '));
    ok('H3 the instances of one part read more than one marking name',
      new Set(maps.map((p) => p.reads)).size >= 2,
      maps.map((p) => `${p.id}:${p.reads}`).join(' | '));
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
    // 🔴 은퇴 2026-08-28 (라운드 Z) — 「없어진 세상」을 재고 있었습니다. 지우지 않고 «행선지»를 답니다.
    //    무엇이 사라졌나: `options.question` 을 «선언하는 좌석이 0» 이 됐습니다. 그건 lot_map 의
    //                    질문(row·kind·by)이었고, 맵 좌석 둘이 마지막 소유자였습니다. 라우트가
    //                    사라진 자리를 { start, follow } 로 옮기면서 같이 갔습니다.
    //    왜 빨강인가:     `asked.length > 0` 은 «공허한 초록»을 막으려고 있던 가드입니다. 그 가드가
    //                    제 일을 했습니다 — 세던 것이 없어졌다고 말한 것이지 배선이 깨진 게 아닙니다.
    //                    남은 절반(「질문을 선언한 좌석은 로더를 받는다」)은 여전히 참이고,
    //                    선언하는 좌석이 «없어서» 재는 대상이 없습니다.
    //    어디로 가나:     맵 좌석이 걷기로 오는 지금, 같은 뜻의 단언은 H7c 입니다 — 「follow 를
    //                    선언한 좌석은 로더를 받는다」. 그게 오늘의 「질문 -> 로더」입니다.
    // RETIRED: ok('H7 binding turns a question into a loader',
    //   asked.length > 0 && asked.every((p) => typeof p.options.load === 'function'));
    ok('H7 a seat that declared a question still gets a loader (none declare one today)',
      asked.every((p) => typeof p.options.load === 'function'));
    const walkers = bound.panels.filter((p, i) => Array.isArray(BOARD.panels[i].follow));
    ok('H7c binding turns a declared walk into a loader',
      walkers.length > 0 && walkers.every((p) => typeof p.options.load === 'function'));
    ok('H7b a panel with no question is still handed the address',
      bound.panels.every((p) => p.options.apiBase === 'http://example'));
    ok('H8 binding does not mutate the declaration',
      BOARD.panels.every((p) => typeof (p.options || {}).load === 'undefined'));
    ok('H9 the device ratio reaches the parts',
      bound.panels.every((p) => p.options.dpr === 2));
  }

  shell.destroy();
  eq('I1 destroying the shell empties the host', host.children.length, 0);

  // ── S. 넓은 내용은 «자기 컨테이너»에서 스크롤합니다 ─────────────────────────────
  {
    const css = (mods.sources && mods.sources['board.css']) || '';
    const declaresRow = (cls) => {
      const at = css.indexOf(`.${cls} {`);
      if (at < 0) return false;
      const block = css.slice(at, css.indexOf('}', at));
      return /flex-wrap:\s*nowrap/.test(block) && /overflow-x:\s*auto/.test(block);
    };
    ok('S1 the head step chain stays on one line and scrolls itself',
      declaresRow('rb-head-steps'), 'rb-head-steps');
    ok('S2 ... and so does the expanded layer step chain',
      declaresRow('rb-layer-steps'), 'rb-layer-steps');
    // 🔴 부모만 잠그면 자식이 «0 쪽으로 찌그러집니다» -- 컨테이너 높이가 0 이 되어 넘침
    //    단언은 통과하는데 사람은 못 읽습니다 (총괄 실측: 칩 폭 18px · 글자가 세로로 쌓임).
    //    「없앴다」를 「고쳤다」로 세지 않으려면 자식 규칙이 «한 짝»으로 있어야 합니다.
    const childHolds = (cls) => {
      const at = css.indexOf(`.${cls} > * {`);
      if (at < 0) return false;
      const block = css.slice(at, css.indexOf('}', at));
      return /flex:\s*0 0 auto/.test(block) && /white-space:\s*nowrap/.test(block);
    };
    ok('S3 every chip in the head chain keeps its own width',
      childHolds('rb-head-steps'), 'rb-head-steps > *');
    ok('S4 ... and in the expanded layer chain',
      childHolds('rb-layer-steps'), 'rb-layer-steps > *');
  }

  return { ran, failures };
}

// ── M. THE MUTATION CORPUS ─────────────────────────────────────────────────────────
//
// Each entry names the assertion that MUST go red. A mutant that is caught by nothing, or by
// the wrong thing, is reported as a hole in the suite.

const MUTANTS = [
  { id: 'M15', what: 'a map falls back to a bare die space, erasing which grid it is on',
    catches: 'H3b',
    mutate: { 'main.js': (s) => s.replace("        space: 'die:base',", '') } },
  // 🔴 그림으로는 «안 보이는» 자리입니다: 스텝이 몇 개든 상자 안에 있어야 하는데, wrap 하나가
  //    머리 패널을 517px 넘치게 해 아래 패널 둘을 덮었습니다 (총괄 실측 2026-08-24).
  { id: 'M13', what: 'the step chain wraps again, so a chip with many steps overflows its panel',
    catches: 'S1',
    mutate: { 'board.css': (s) => s.replace(
      '.rb-head-steps { display: flex; flex-wrap: nowrap;',
      '.rb-head-steps { display: flex; flex-wrap: wrap;') } },
  { id: 'M14', what: 'the chips are allowed to shrink, so the row collapses to zero height and reads vertically',
    catches: 'S3',
    mutate: { 'board.css': (s) => s.replace(
      '.rb-head-steps > * { flex: 0 0 auto; white-space: nowrap; }',
      '.rb-head-steps > * { white-space: nowrap; }') } },
  { id: 'M12', what: 'a map with an empty marking asks anyway, so 「not chosen yet」 reads as a refusal',
    catches: 'F17',
    mutate: { 'map_panel.js': (s) => s.replace(
      '    if (this.start && this.start.marking && !this.startFor()) {', '    if (false) {') } },
  { id: 'M09', what: 'the map ignores a walk model and only ever reads lot_map cells',
    catches: 'F16',
    mutate: { 'map_panel.js': (s) => s.replace(
      '      if (Array.isArray(model.nodes)) {', '      if (false) {') } },
  { id: 'M08', what: 'the map head drops the marking count, leaving it only in the badge',
    catches: 'C34',
    mutate: { 'map_panel.js': (s) => s.replace(
      '        ? `마킹 ${markedHere} · ${cellsHere.length}칸',
      '        ? `${cellsHere.length}칸') } },
  // 🔴 배지가 «선언한 이름 전부»를 말해야 합니다. 둘만 말하면, 세 번째 이름을 따라 움직인
  //    패널이 「선언과 다르게 도는 것」으로 읽힙니다 -- 총괄이 실제로 그렇게 읽었습니다.
  { id: 'M07', what: 'the badge hides the name the page follows, so the panel looks like it lies',
    catches: 'F15',
    mutate: { 'map_panel.js': (s) => s.replace(
      "      + (this.pageFollows ? ` · 따라감 ${this.pageFollows}` : '');", "      + '';") } },
  // 🔴 「아직 안 왔다」를 「없다」로 접는 변이. 화면은 조용히 「그런 건 없습니다」라고 말합니다.
  { id: 'M06', what: 'a placement that has not arrived is folded into "this point is nowhere"',
    catches: 'F8c',
    mutate: { 'map_panel.js': (s) => s.replace(
      "  if (!item || !Array.isArray(item.placements)) return 'awaiting';",
      "  if (!item || !Array.isArray(item.placements)) return 'nowhere';") } },
  // 🔴 그린 것이 «없는데» 테두리는 멀쩡한 모양 -- 요소를 세는 검사가 「정상」이라 읽는 그 회귀.
  { id: 'M05', what: 'the first paint waits for a resize callback that may never come',
    catches: 'F13',
    mutate: { 'map_panel.js': (s) => s.replace(
      '      if (rect && rect.width > 0 && rect.height > 0) this.resize(rect.width, rect.height);',
      '      if (false) this.resize(rect.width, rect.height);') } },
  // 🔴 「이 좌표계에 자리가 없다」와 「그런 점이 없다」를 같은 그림으로 만드는 변이입니다.
  { id: 'M04', what: 'a point with no place in this space is dropped silently instead of counted',
    catches: 'F8b',
    mutate: { 'map_panel.js': (s) => s.replace(
      "        if (state === 'nowhere') { panel._offSpace += 1; return null; }",
      "        if (state === 'nowhere') { return null; }") } },
  // 🔴 「좌표가 없다」와 「좌표가 있어야 하는데 빈다」를 같은 그림으로 만드는 변이입니다.
  { id: 'M03', what: 'a map stands even for a source that declares no such coordinate space',
    catches: 'F10',
    mutate: { 'map_panel.js': (s) => s.replace(
      '    return !this.sourceSpaces || this.sourceSpaces.includes(this.space);',
      '    return true;') } },
  // 🔴 수를 색에서 지우면 1과 13이 같아 보입니다. 그림은 여전히 「그려집니다」.
  { id: 'M02', what: 'the count a die carries is dropped from the drawing',
    catches: 'F9',
    mutate: { 'map_panel.js': (s) => s.replace(
      '        const shade = weightShade(cell.n);', '        const shade = 1;') } },
  // 🔴 좌표계가 선언이 아니라 부품 안의 고정값이 되면, 확대는 「부품을 고쳐야 서는 것」이 됩니다.
  { id: 'M01', what: 'the coordinate space is hardcoded to die instead of read from the declaration',
    catches: 'F8',
    mutate: { 'map_panel.js': (s) => s.replace(
      "    return SPACES[String(this.space).split(':')[0]] || SPACES.die;",
      '    return SPACES.die;') } },
  // 🔴 A STAMPED ID IS NOT A NODE. Dropping the gate still "works" on screen -- the die lights
  //    up -- and the walk it starts is the thing that fails, three panels away.
  { id: 'M00', what: 'a stamped (server-less) node id is allowed into the marking',
    catches: 'C16',
    mutate: { 'map_panel.js': (s) => s.replace(
      '    if (cell.nodeIdResolved !== true) {', '    if (false) {') } },
  // 🔴 THE DEFECT THAT LOOKS RIGHT. Ignoring `rotation` still draws a plausible wafer, which is
  //    why nothing on this board noticed for a week. It dies on the seats moving, not on a count.
  { id: 'M0', what: 'the frame rotation is ignored and stored coordinates are drawn as seats',
    catches: 'B16',
    mutate: { 'map_panel.js': (s) => s.replace(
      '  const seating = computeSeating(cells, seatFrame, null);',
      '  const seating = { seats: cells.map((c) => ({ x: c.x, y: c.y, cell: c })) };') } },
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
