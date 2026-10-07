// IMAGE PREVIEW - an image cell of the main grid previews on a dwell and opens from its mark, with little
// server load (lead 191912ce2, owner 10-01 「이미지 일단 메인그리드 해봐 서버 부하 크지 않게」).
//
// The order's gate table, by name:
//   D1 twenty cells passed over -> no picture asked for      D2 one dwell -> one <img>, its address the ref's
//   D3 moving on drops the last: its <img>, its late answer, its pending question
//   D4 a refusal says the server's sentence and what to do    D5 the mark opens the same address, no drag
//   D6 the box stays inside the window                         D7 two previews on one page keep apart
//   D8 a blank cell has no mark and asks nothing               D9 a cell that changes or goes takes its box
//   W1 only the word image takes the image cell                N1 a press on the cell itself: nothing asked, untouched
//   G1 grid: only the image column changes                     G2 grid: a join column of type image too
// 「같은 칸 다시 -> 새 요청 0」 is the browser's cache under the server's Cache-Control: measured in the
// browser, not here. Timers, fetch and the window are injected; nothing waits on a clock.
//
// Run: node client2/tests/image_preview_harness.mjs
import path from 'node:path';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { makeDoc } from './lib/board_dom.mjs';

if (typeof globalThis.document === 'undefined') {
  globalThis.document = {
    hidden: false, addEventListener() {}, removeEventListener() {},
    getElementById: () => null, querySelector: () => null,
  };
}

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PREVIEW = path.join(HERE, '..', 'src', 'image_preview.js');
const COLUMN = path.join(HERE, '..', 'src', 'grid_image_column.js');
const GRID = path.join(HERE, '..', 'src', 'grid.js');
const TOKENS = readFileSync(path.join(HERE, '..', 'src', 'tokens.css'), 'utf8');
const BASE = 'http://box:8080';
const REF = 'photos:lot 7/a&b#1.png';
const VIEW = { width: 1000, height: 700 };
const CAP = 320;
const EDGE = 6.8;

/** One preview on its own mount, with a clock, a fetch and a window that only record. */
function rig(P, doc = makeDoc(), answer = null) {
  const mount = doc.createElement('div');
  doc.body.appendChild(mount);
  const timers = [];
  const fetches = [];
  const opens = [];
  const preview = new P.ImagePreview(mount, {
    doc, base: BASE,
    setTimeout: (fn, ms) => { timers.push({ fn, ms, cancelled: false }); return timers.length - 1; },
    clearTimeout: (id) => { if (timers[id]) timers[id].cancelled = true; },
    fetch: (url, init) => {
      const call = { url, init };
      fetches.push(call);
      return new Promise((resolve, reject) => { call.resolve = resolve; call.reject = reject; if (answer) answer(call); });
    },
    open: (...args) => opens.push(args),
    viewport: () => VIEW, sizePx: () => CAP, edgePx: () => EDGE,
  });
  const due = () => { for (const t of timers) if (!t.cancelled && !t.fired) { t.fired = true; t.fn(); } };
  const imgs = () => mount.querySelectorAll('.image-preview-img');
  return { doc, mount, preview, timers, fetches, opens, due, imgs };
}
const cell = (doc, rect = { left: 100, top: 100, bottom: 128 }) => {
  const n = doc.createElement('div');
  n.getBoundingClientRect = () => rect;
  return n;
};
const flush = () => new Promise((r) => setTimeout(r, 0));
const lines = (box) => {
  const why = box ? box.querySelectorAll('.image-preview-why')[0] : null;
  return why ? [why._text, ...why.children.map((c) => c.textContent)].filter(Boolean) : [];
};
const response = (status, body, type = 'basic') => ({ status, ok: status >= 200 && status < 300, type,
  json: async () => body });

async function suite(P, C) {
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };

  console.log('\n[D] the preview');
  {
    const r = rig(P);
    for (let i = 0; i < 20; i++) {
      const c = cell(r.doc);
      r.preview.hover(c, `photos:a/${i}.png`);
      r.preview.leave(c);
    }
    r.due();
    say('D1 twenty cells passed over under the dwell: no picture asked for, every timer let go',
      r.imgs().length === 0 && r.fetches.length === 0 && r.timers.length === 20 && r.timers.every((t) => t.cancelled),
      JSON.stringify({ imgs: r.imgs().length, fetches: r.fetches.length, timers: r.timers.length }));
  }
  {
    const r = rig(P);
    const c = cell(r.doc);
    r.preview.hover(c, REF);
    const before = r.imgs().length;
    r.due();
    const src = r.imgs().map((i) => i.attrs.src);
    say('D2 one dwell: nothing before it, then one <img> whose address carries the ref as written',
      before === 0 && r.timers.length === 1 && r.timers[0].ms === P.DWELL_MS && P.DWELL_MS > 0
        && src.length === 1 && src[0] === `${BASE}/api/image?ref=${encodeURIComponent(REF)}`
        && decodeURIComponent(src[0].split('?ref=')[1]) === REF && r.fetches.length === 0,
      JSON.stringify({ before, src, timers: r.timers.map((t) => t.ms) }));
  }
  {
    // a fails and starts its question; b comes, fails too; a's late answers land; then c comes.
    const r = rig(P);
    const [a, b, c] = [cell(r.doc), cell(r.doc), cell(r.doc)];
    r.preview.hover(a, 'photos:a.png');
    r.due();
    const imgA = r.imgs()[0];
    const lateLoad = imgA.onload;
    imgA.onerror();
    const askA = r.fetches[0];
    r.preview.hover(b, 'photos:b.png');
    const droppedA = !('src' in imgA.attrs) && imgA.onload === null && imgA.onerror === null;
    const abortedA = Boolean(askA.init.signal && askA.init.signal.aborted);
    r.due();
    const imgB = r.imgs()[0];
    imgB.onerror();
    const askB = r.fetches[1];
    if (lateLoad) lateLoad();
    askA.resolve(response(404, { detail: 'late' }));
    await flush();
    const boxes = r.mount.querySelectorAll('.image-preview');
    const boxB = boxes[0];
    const srcB = (imgB && imgB.attrs.src) || '';
    const boxBQuiet = boxes.length === 1 && !boxB.classList.contains('is-refused') && lines(boxB).join('|') === P.LOADING;
    r.preview.hover(c, 'photos:c.png');
    const abortedB = Boolean(askB && askB.init.signal && askB.init.signal.aborted);
    say('D3 moving on lets the last go: its <img> emptied, its question aborted, its late answers neither draw nor keep the next one\'s question alive',
      droppedA && abortedA && boxBQuiet && srcB.endsWith(encodeURIComponent('photos:b.png')) && abortedB,
      JSON.stringify({ droppedA, abortedA, boxBQuiet, abortedB, lines: lines(boxB) }));
  }
  {
    const cases = [
      ['photos:gone.png', response(404, { detail: "no file 'gone.png' under source 'photos'" }),
        ["404 · no file 'gone.png' under source 'photos'", 'Next: correct the value in this cell']],
      ['db:7', response(502, { detail: "source 'db' could not be read: timeout" }),
        ["502 · source 'db' could not be read: timeout", 'Next: check this source in image_sources.json']],
      // (lead f087403fe) the server brokers every source: an outside host's failure is its 502 sentence too.
      ['https://img.example.com/a.png', response(502, { detail: "img.example.com answered 404 for '/a.png'" }),
        ["502 · img.example.com answered 404 for '/a.png'", 'Next: check this source in image_sources.json']],
      ['photos:a.png', 'throw', ['Server not reached', 'Next: check the connection, then hover again']],
      ['photos:a.txt', response(200, null), ['Not a picture the browser can draw', 'Next: open it to see what came back']],
    ];
    const got = [];
    for (const [ref, res, want] of cases) {
      const r = rig(P);
      r.preview.hover(cell(r.doc), ref);
      r.due();
      r.imgs()[0].onerror();
      const ask = r.fetches[0];
      if (res === 'throw') ask.reject(new TypeError('Failed to fetch')); else ask.resolve(res);
      await flush();
      await flush();
      const box = r.mount.querySelectorAll('.image-preview')[0];
      const seen = lines(box);
      got.push({ ref, ok: JSON.stringify(seen) === JSON.stringify(want) && box.classList.contains('is-refused')
        && r.fetches.length === 1 && ask.url === r.imgs()[0].attrs.src, seen });
    }
    say('D4 a picture that does not come: one question to the same address, then the server\'s sentence and the next step',
      got.every((g) => g.ok), JSON.stringify(got.filter((g) => !g.ok)));
  }
  {
    const r = rig(P);
    const renderer = new C.ImageCellRenderer();
    renderer.init({ value: REF, context: { imagePreview: r.preview }, eGridCell: { ownerDocument: r.doc } });
    const gui = renderer.getGui();
    const mark = gui.querySelectorAll('.cell-image-open')[0];
    // Measured in the browser (10-01): the grid starts its range drag from the pointer press and selects
    // from the focus a pressed button takes - stopping mousedown alone left the drag running.
    const stopped = [];
    const prevented = [];
    const ev = (type) => ({ stopPropagation: () => stopped.push(type), preventDefault: () => prevented.push(type) });
    for (const type of ['pointerdown', 'mousedown', 'click']) mark.dispatch(type, ev(type));
    say('D5 the mark opens the same address in a new window, and its press is not the cell\'s (no drag, no focus taken)',
      r.opens.length === 1 && r.opens[0][0] === `${BASE}/api/image?ref=${encodeURIComponent(REF)}`
        && r.opens[0][1] === '_blank' && ['pointerdown', 'mousedown', 'click'].every((t) => stopped.includes(t))
        && prevented.includes('mousedown') && mark.attrs.title === P.OPEN_IMAGE && r.imgs().length === 0,
      JSON.stringify({ opens: r.opens, stopped, prevented }));
  }
  {
    // Before its picture the box has no size of its own (the stub reports 0) and is placed by the cap;
    // once the picture comes it is placed again by the size it has.
    const placed = (rect, size) => {
      const r = rig(P);
      r.preview.hover(cell(r.doc, rect), 'photos:a.png');
      r.due();
      const box = r.mount.querySelectorAll('.image-preview')[0];
      if (size) {
        box.offsetWidth = size.w;
        box.offsetHeight = size.h;
        r.imgs()[0].onload();
      }
      return { left: parseFloat(box.style.left), top: parseFloat(box.style.top) };
    };
    const SIZE = { w: 189, h: 53 };
    const corner = placed({ left: 980, top: 680, bottom: 698 });
    const near = placed({ left: 100, top: 100, bottom: 128 });
    const cornerSized = placed({ left: 980, top: 680, bottom: 698 }, SIZE);
    const inside = (p, w, h) => p.left >= EDGE && p.top >= EDGE && p.left + w <= VIEW.width - EDGE + 1e-9
      && p.top + h <= VIEW.height - EDGE + 1e-9;
    const token = (TOKENS.match(/--image-preview-max:\s*[\d.]+px;/g) || []).length;
    say('D6 the box stays inside the window (a cell in the corner too), below a cell with room, right above one without once it has its size, and the cap is one token',
      inside(corner, CAP, CAP) && inside(near, CAP, CAP) && near.top === 128 + EDGE && near.left === 100
        && inside(cornerSized, SIZE.w, SIZE.h) && cornerSized.top === 680 - EDGE - SIZE.h && token === 1,
      JSON.stringify({ corner, near, cornerSized, token }));
  }
  {
    const doc = makeDoc();
    const one = rig(P, doc);
    const two = rig(P, doc);
    const a = cell(doc);
    const b = cell(doc);
    one.preview.hover(a, 'photos:a.png');
    one.due();
    const imgOne = one.imgs()[0];
    two.preview.hover(b, 'photos:b.png');
    two.due();
    two.preview.leave(b);
    two.preview.leave();
    say('D7 two previews on one page keep apart: each its own box, one leaving takes nothing of the other',
      one.imgs().length === 1 && one.imgs()[0] === imgOne && 'src' in imgOne.attrs
        && two.mount.querySelectorAll('.image-preview').length === 0
        && one.mount.querySelectorAll('.image-preview').length === 1,
      JSON.stringify({ one: one.imgs().length, two: two.imgs().length }));
  }
  {
    const r = rig(P);
    const renderer = new C.ImageCellRenderer();
    renderer.init({ value: '  ', context: { imagePreview: r.preview }, eGridCell: { ownerDocument: r.doc } });
    const gui = renderer.getGui();
    gui.dispatch('mouseenter', {});
    const mark = gui.querySelectorAll('.cell-image-open')[0];
    say('D8 a blank image cell: no mark, no text, and resting on it asks nothing',
      mark.style.display === 'none' && gui.querySelectorAll('.cell-image-ref')[0].textContent === ''
        && r.timers.length === 0, JSON.stringify({ display: mark.style.display, timers: r.timers.length }));
  }
  {
    const r = rig(P);
    const renderer = new C.ImageCellRenderer();
    renderer.init({ value: 'photos:a.png', context: { imagePreview: r.preview }, eGridCell: { ownerDocument: r.doc } });
    renderer.getGui().dispatch('mouseenter', {});
    r.due();
    const shown = r.imgs().length;
    renderer.refresh({ value: 'photos:b.png' });
    const afterRefresh = r.imgs().length;
    const text = renderer.getGui().querySelectorAll('.cell-image-ref')[0].textContent;
    renderer.getGui().dispatch('mouseenter', {});
    r.due();
    renderer.destroy();
    say('D9 a cell whose value changes, or that goes, takes its box with it',
      shown === 1 && afterRefresh === 0 && text === 'photos:b.png' && r.imgs().length === 0
        && r.mount.querySelectorAll('.image-preview').length === 0,
      JSON.stringify({ shown, afterRefresh, text, after: r.imgs().length }));
  }
  {
    const others = ['string', 'number', 'datetime', undefined].map((t) => Object.keys(C.imageColumnParts(t)).length);
    say('W1 only the column type word image takes the image cell',
      C.imageColumnParts('image').cellRenderer === C.ImageCellRenderer && others.every((n) => n === 0),
      JSON.stringify(others));
  }
  {
    // (lead, answer to the click question) the cell itself selects and edits as today; only the mark opens.
    const r = rig(P);
    const renderer = new C.ImageCellRenderer();
    renderer.init({ value: REF, context: { imagePreview: r.preview }, eGridCell: { ownerDocument: r.doc } });
    const text = renderer.getGui().querySelectorAll('.cell-image-ref')[0];
    const touched = [];
    const ev = (type) => ({ stopPropagation: () => touched.push(`stop ${type}`), preventDefault: () => touched.push(`prevent ${type}`) });
    for (const type of ['pointerdown', 'mousedown', 'click', 'dblclick']) text.dispatch(type, ev(type));
    say('N1 a press on the cell itself asks nothing and opens nothing, and reaches the grid untouched (select, edit as today)',
      r.opens.length === 0 && r.timers.length === 0 && r.fetches.length === 0 && touched.length === 0,
      JSON.stringify({ opens: r.opens.length, timers: r.timers.length, touched }));
  }
  return { ran: names.length, names, failures: fails };
}

// ── the grid: which columns change ────────────────────────────────────────────────────
const { state } = await import('../src/state.js');
function stage(photoType, joinType) {
  state.currentTable = 'shots';
  state.currentColumns = ['lot', 'photo', 'qty', 'created_at'];
  state.currentColumnTypes = { lot: 'string', photo: photoType, qty: 'number' };
  state.currentBusinessKey = 'lot';
  state.currentCompositeKeySources = [];
  state.currentVirtualColumns = [
    { name: 'right_shot', type: joinType, editable: false, right_table: 'dt_job', rule: 'r1', unresolved_label: '?' },
    { name: 'right_note', type: 'string', editable: false, right_table: 'dt_job', rule: 'r1', unresolved_label: '?' },
  ];
  state.currentJoinResolvedColumns = [];
  state.pendingTxEdits = {};
}
/** A definition as text: values as JSON, functions by their source - two runs compare by what they do. */
const shape = (def) => JSON.stringify(def, (k, v) => (typeof v === 'function' ? `fn:${v.name}:${v.toString()}` : v));

function gridSuite(G, C) {
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };
  console.log('\n[G] the grid');
  stage('image', 'image');
  const withImage = new Map(G.buildColumnDefs().map((d) => [d.field, d]));
  stage('string', 'string');
  const without = new Map(G.buildColumnDefs().map((d) => [d.field, d]));
  const others = ['lot', 'qty', 'created_at', 'right_note'];
  const same = others.filter((f) => withImage.has(f) && shape(withImage.get(f)) === shape(without.get(f)));
  const photo = withImage.get('photo');
  say('G1 an image column is drawn by the image cell; every other column\'s definition is what it was',
    same.length === others.length && photo && photo.cellRenderer === C.ImageCellRenderer
      && !(without.get('photo') || {}).cellRenderer && others.every((f) => !withImage.get(f).cellRenderer),
    JSON.stringify({ same, photo: photo && String(photo.cellRenderer && photo.cellRenderer.name) }));
  const join = withImage.get('right_shot');
  say('G2 a join column of type image is drawn by the same image cell; it stays read-only',
    join && join.cellRenderer === C.ImageCellRenderer && join.editable === false
      && !(without.get('right_shot') || {}).cellRenderer,
    JSON.stringify({ join: join && Object.keys(join) }));
  return { ran: names.length, names, failures: fails };
}

let pass = 0;
const failures = [];
{
  const P = await import('../src/image_preview.js');
  const C = await import('../src/grid_image_column.js');
  const G = await import('../src/grid.js');
  const base = await suite(P, C);
  const grid = gridSuite(G, C);
  pass += base.ran - base.failures.length + grid.ran - grid.failures.length;
  failures.push(...base.failures, ...grid.failures);

  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const swap = (text, from, to) => {
    if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
    return text.split(from).join(to);
  };
  const M = (id, what, catches, file, from, to) => ({ id, what, catches, file, from, to });
  const quietly = async (fn) => {
    const say = console.log;
    console.log = () => {};
    try { return await fn(); } finally { console.log = say; }
  };
  const MUTANTS = [
    M('M1', 'no dwell - the picture is asked for at once', 'D1', PREVIEW,
      '    this.timer = this.later(() => { this.timer = null; this._show(); }, DWELL_MS);', '    this._show();'),
    M('M2', 'the last picture is not let go', 'D3', PREVIEW, "      this.img.removeAttribute('src');\n", ''),
    M('M3', 'the ref goes unencoded', 'D2', PREVIEW, 'encodeURIComponent(String(ref))', 'String(ref)'),
    M('M4', 'the refusal sentence is not read', 'D4', PREVIEW,
      "detail: res.ok ? '' : await detailOf(res)", "detail: ''"),
    M('M5', 'the new window gets another address', 'D5', PREVIEW,
      "this.openWindow(imageRefUrl(this.base, ref), '_blank', 'noopener')", "this.openWindow(String(ref), '_blank', 'noopener')"),
    M('M6', 'the box is not kept inside the window', 'D6', PREVIEW,
      '  const left = Math.max(edge, Math.min(rect.left, view.width - width - edge));', '  const left = rect.left;'),
    M('M7', 'one at a time kept across every preview on the page, not per preview', 'D7', PREVIEW,
      '    this.drop();\n    if (isBlank(ref)) return;',
      '    if (globalThis.__lastPreview) globalThis.__lastPreview.drop();\n    globalThis.__lastPreview = this;\n'
        + '    this.drop();\n    if (isBlank(ref)) return;'),
    M('M10', 'the box is not placed again when its picture comes', 'D6', PREVIEW,
      "why.textContent = ''; this._place(box); }", "why.textContent = ''; }"),
    M('M8', 'a late answer for a cell left behind still draws', 'D3', PREVIEW,
      '    if (this.img !== img) return;\n    this.abort = null;', '    this.abort = null;'),
    M('M9', 'the question still in flight is not abandoned', 'D3', PREVIEW,
      '    if (this.abort) { this.abort.abort(); this.abort = null; }\n', ''),
    M('C1', 'a press on the mark starts a range drag', 'D5', COLUMN,
      "    this.mark.addEventListener('pointerdown', (e) => e.stopPropagation());\n", ''),
    M('C5', 'the pressed mark takes the focus, so the grid selects its cell', 'D5', COLUMN,
      "(e) => { e.preventDefault(); e.stopPropagation(); }", '(e) => { e.stopPropagation(); }'),
    M('C2', 'a blank cell still shows its mark', 'D8', COLUMN,
      "this.mark.style.display = blank ? 'none' : '';", "this.mark.style.display = '';"),
    M('C3', 'a cell that goes keeps its box', 'D9', COLUMN,
      '  destroy() {\n    if (this.preview) this.preview.leave(this.gui);\n  }', '  destroy() {}'),
    M('C4', 'every column is taken for an image', 'W1', COLUMN,
      'return type === IMAGE_TYPE ? { cellRenderer: ImageCellRenderer } : {};', 'return { cellRenderer: ImageCellRenderer };'),
    M('C6', 'a press anywhere on the cell opens the window', 'N1', COLUMN,
      "    this.mark.addEventListener('click', (e) => {", "    this.gui.addEventListener('click', (e) => {"),
    M('G1', 'the grid gives an image column no image cell', 'G1', GRID,
      '    Object.assign(colDef, imageColumnParts(colType));\n', ''),
    M('G2', 'a join column skips the image parts', 'G2', GRID, '      ...imageColumnParts(vc.type),\n', ''),
  ];
  const scored = await scoreMutants(MUTANTS, async (mu) => quietly(async () => {
    const mutate = (t) => swap(t, mu.from, mu.to);
    delete globalThis.__lastPreview;
    if (mu.file === GRID) {
      return gridSuite((await loadWithProbe(GRID, { mutate, tag: `ip${mu.id}` })).module, C);
    }
    const P2 = mu.file === PREVIEW ? (await loadWithProbe(PREVIEW, { mutate, tag: `ip${mu.id}` })).module : P;
    const C2 = mu.file === COLUMN ? (await loadWithProbe(COLUMN, { mutate, tag: `ip${mu.id}` })).module : C;
    if (mu.catches.startsWith('G')) return gridSuite(G, C2);
    return suite(P2, C2);
  }), { baselineNames: [...base.names, ...grid.names],
       title: '\n  [mutants] - each must be caught by the check it names.' });
  pass += MUTANTS.length - scored.wrong;
  for (let i = 0; i < scored.wrong; i += 1) failures.push(`mutant verdict ${i + 1}`);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
