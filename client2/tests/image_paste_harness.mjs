// IMAGE PASTE - a picture pasted or dropped on an image cell is kept by the server and its reference written to the cell
// as a pasted value is (owner 11-05 ㄱ, server c2b6b8e9b). Run: node client2/tests/image_paste_harness.mjs
//
//   P1 text and a picture (Excel copies a picture of every cell) -> the text, as today
//   P2 a picture alone, image cells -> that picture       P3 a picture alone, a cell that is not image -> refused
//   P4 two pictures -> refused                            P5 no picture -> the text path, as today
//   P6 an Excel empty cell ('\r\n', two cells '\t\r\n') and a picture -> the text, as today (owner 11-05 ㄴ)
//   I1 a drop's cell: the topmost grid cell under the point, only when its column is image
//   U1 the upload: its address and field; the ref; the server's sentence; no network
//   R1 the real paste listener: a picture into an image cell -> one upload, then the ref through the paste's own PUT
//   R2 the Excel shape (text + picture) into an image cell -> no upload, the text through the PUT
//   R3 a picture into a cell that is not image -> nothing sent, the refusal said
//   R4 a refused upload -> nothing written, the server's sentence said
//   R5 · R6 Excel empty cells (G1 one cell, G3 two) into image cells -> no upload, the same calls and line as the text alone
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const COLUMN = path.join(HERE, '..', 'src', 'grid_image_column.js');
const CLIPBOARD = path.join(HERE, '..', 'src', 'clipboard.js');

const doc = makeDoc('light');
const docListeners = new Map();
doc.addEventListener = (type, fn) => { (docListeners.get(type) || docListeners.set(type, []).get(type)).push(fn); };
doc.removeEventListener = () => {};
doc.activeElement = doc.body;
const log = doc.createElement('div');
log.setAttribute('id', 'performance-log');
doc.body.appendChild(log);
doc.getElementById = (id) => (id === 'performance-log' ? log : null);
globalThis.document = doc;
globalThis.window = {
  location: { port: '', origin: 'http://box', href: 'http://box/', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
};

const { state } = await import('../src/state.js');
const png = (name = 'image.png') => new File([new Uint8Array([137, 80, 78, 71, 1, 2, 3])], name, { type: 'image/png' });
const REF = 'shots_in:shots/2026-11-05/0123456789abcdef0123456789abcdef.png';

/** One grid row (lot, photo) behind the paste listener; the fetch records and answers. */
function stage(answers = {}) {
  const node = { data: { row_id: 'r1', data: { lot: { value: 'L1' }, photo: { value: '' } } } };
  state.currentTable = 'shots';
  state.currentColumns = ['lot', 'photo'];
  state.currentColumnTypes = { lot: 'string', photo: 'image' };
  state.currentVirtualColumns = [];
  state.selectedCellsMap = {};
  state.dragStartCell = null;
  state.dragEndCell = null;
  state.txModeActive = false;
  state.pendingTxEdits = {};
  state.pageCache = new Map();
  state.serverSort = { colId: 'row_id', desc: false };
  let focus = 'photo';
  state.gridApi = {
    getFocusedCell: () => ({ rowIndex: 0, column: { getId: () => focus, getColId: () => focus } }),
    getDisplayedRowAtIndex: () => node,
    getRowNode: () => node,
    getColumns: () => ['lot', 'photo'].map((c) => ({ getColId: () => c, getId: () => c })),
    getColumnState: () => [{ colId: 'lot' }, { colId: 'photo' }],
    refreshCells() {}, applyColumnState() {}, getColumnDefs: () => [], onSortChanged() {}, getEditingCells: () => [],
  };
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const call = { url: String(url), method: init.method || 'GET', body: init.body };
    calls.push(call);
    if (call.url.includes('/images?')) {
      const a = answers.upload || { status: 200, body: { ref: REF, bytes: 7, media_type: 'image/png' } };
      return { ok: a.status < 300, status: a.status, json: async () => a.body };
    }
    return { ok: true, status: 200, json: async () => ({ status: 'success', change_count: 1 }) };
  };
  log.textContent = '';
  return { calls, focusOn: (c) => { focus = c; } };
}
const paste = async (text, files) => {
  const dt = { types: [...(text ? ['text/plain'] : []), ...(files.length ? ['Files'] : [])], files,
    getData: (t) => (t === 'text/plain' ? text : '') };
  for (const fn of docListeners.get('paste') || []) await fn({ clipboardData: dt, target: doc.body, preventDefault() {} });
};
const putOf = (calls) => calls.filter((c) => c.method === 'PUT');
const putValue = (call) => { const b = JSON.parse(call.body); return b.updates[0].updates; };

async function suite(C, CB) {
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };
  console.log('\n[P] which paste is a picture');
  say('P1 text beside a picture is the text - Excel copies a picture of every cell',
    C.pastedImage('photos:lot7/a.png\r\n', [png()], ['image']) === null);
  const one = C.pastedImage('', [png()], ['image', 'image']);
  say('P2 a picture alone into image cells is that picture', one && one.file && one.file.type === 'image/png', JSON.stringify(one));
  const mixed = C.pastedImage('', [png()], ['image', 'string']);
  say('P3 a picture alone with a cell that is not image is refused by name',
    mixed && mixed.refused === C.IMAGES_ONLY, JSON.stringify(mixed));
  const two = C.pastedImage('', [png('a.png'), png('b.png')], ['image']);
  say('P4 two pictures are refused', two && two.refused === C.ONE_IMAGE, JSON.stringify(two));
  say('P5 no picture is the text path', C.pastedImage('', [new File(['x'], 'a.txt', { type: 'text/plain' })], ['image']) === null
    && C.pastedImage('', [], ['image']) === null);
  say('P6 an Excel empty cell and its picture is the text - only no text at all is a picture',
    C.pastedImage('\r\n', [png()], ['image']) === null && C.pastedImage('\t\r\n', [png()], ['image', 'image']) === null
      && C.pastedImage(' ', [png()], ['image']) === null);

  console.log('\n[I] a drop\'s cell');
  const el = (cls, attrs = {}, closest = null) => ({ classList: { contains: (c) => cls.split(' ').includes(c) },
    getAttribute: (k) => attrs[k], closest: () => closest });
  const row = (i) => el('ag-row', { 'row-index': String(i) });
  const types = { lot: 'string', photo: 'image' };
  const under = [el('drop-overlay'), el('ag-cell', { 'col-id': 'photo' }, row(3)), el('ag-row'), el('ag-body')];
  const got = C.imageCellIn(under, types);
  const onText = C.imageCellIn([el('ag-cell', { 'col-id': 'lot' }, row(0)), el('ag-cell', { 'col-id': 'photo' }, row(0))], types);
  say('I1 the topmost grid cell under the point, only when its column is image',
    got && got.colId === 'photo' && got.rowIndex === 3 && onText === null && C.imageCellIn([el('drop-overlay')], types) === null,
    JSON.stringify({ got: got && { colId: got.colId, rowIndex: got.rowIndex }, onText }));

  console.log('\n[U] the upload');
  const sent = [];
  const ok = await C.uploadImage('http://box', 'my table', 'photo col', png(), async (url, init) => {
    sent.push({ url, init });
    return { ok: true, status: 200, json: async () => ({ ref: REF }) };
  });
  const big = await C.uploadImage('http://box', 't', 'c', png(), async () => ({ ok: false, status: 413,
    json: async () => ({ detail: 'the picture is 99.9 MB; at most 10 MB' }) }));
  const down = await C.uploadImage('http://box', 't', 'c', png(), async () => { throw new TypeError('Failed to fetch'); });
  const blank = await C.uploadImage('http://box', 't', 'c', png(), async () => ({ ok: false, status: 500, json: async () => { throw new Error('html'); } }));
  say('U1 one POST to /tables/<t>/images?column=<c> with the field file; the ref; the server\'s sentence; no network said',
    sent.length === 1 && sent[0].url === 'http://box/tables/my%20table/images?column=photo%20col' && sent[0].init.method === 'POST'
      && sent[0].init.body.get('file') instanceof File && ok.ref === REF
      && big.refused === 'the picture is 99.9 MB; at most 10 MB' && down.refused === C.NOT_SENT
      && blank.refused === 'Image not saved (HTTP 500)',
    JSON.stringify({ url: sent[0] && sent[0].url, ok, big, down, blank }));

  console.log('\n[R] the paste listener');
  docListeners.clear();
  CB.setupClipboardHandlers();
  {
    const s = stage();
    await paste('', [png()]);
    const order = s.calls.map((c) => `${c.method} ${c.url.replace(/^.*\/tables\//, '').split('?')[0]}`);
    const put = putOf(s.calls)[0];
    say('R1 a picture into an image cell: one upload, then the ref through the paste\'s own PUT',
      order.join(',') === 'POST shots/images,PUT shots/data/updates' && put && putValue(put).photo === REF
        && log.textContent === 'Pasted · 1 cell updated',
      JSON.stringify({ order, put: put && putValue(put), log: log.textContent }));
  }
  {
    const s = stage();
    await paste('photos:lot7/a.png', [png()]);
    const put = putOf(s.calls)[0];
    say('R2 the Excel shape (text + picture) into an image cell: no upload, the text through the PUT',
      s.calls.filter((c) => c.method === 'POST').length === 0 && put && putValue(put).photo === 'photos:lot7/a.png',
      JSON.stringify(s.calls.map((c) => c.method)));
  }
  {
    const s = stage();
    s.focusOn('lot');
    await paste('', [png()]);
    say('R3 a picture into a cell that is not image: nothing sent, the refusal said',
      s.calls.length === 0 && log.textContent === C.IMAGES_ONLY, JSON.stringify({ calls: s.calls.length, log: log.textContent }));
  }
  {
    const s = stage({ upload: { status: 415, body: { detail: 'that file is not a png, jpeg, gif, bmp, webp or tiff picture' } } });
    await paste('', [png()]);
    say('R4 a refused upload: nothing written, the server\'s sentence said',
      putOf(s.calls).length === 0 && log.textContent === 'that file is not a png, jpeg, gif, bmp, webp or tiff picture',
      JSON.stringify({ calls: s.calls.map((c) => c.method), log: log.textContent }));
  }
  for (const [cell, id, text] of [['R5', 'G1', '\r\n'], ['R6', 'G3', '\t\r\n']]) {
    const seen = async (files) => {
      const s = stage();
      await paste(text, files);
      return { calls: s.calls.map((c) => `${c.method} ${c.url} ${c.body instanceof FormData ? 'form' : c.body || ''}`), log: log.textContent };
    };
    const withPicture = await seen([png()]);
    const textAlone = await seen([]);
    say(`${cell} ${id} Excel empty cell${id === 'G3' ? 's' : ''} into image cells: no upload, the same as the text alone`,
      !withPicture.calls.some((c) => c.startsWith('POST')) && JSON.stringify(withPicture) === JSON.stringify(textAlone),
      JSON.stringify({ withPicture, textAlone }));
  }
  docListeners.clear();
  return { ran: names.length, names, failures: fails };
}

const C = await import('../src/grid_image_column.js');
const CB = await import('../src/clipboard.js');
const base = await suite(C, CB);
let pass = base.ran - base.failures.length;
const failures = [...base.failures];

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
  M('X1', 'the picture wins over the text', 'P1', COLUMN, '  if (text) return null;\n', ''),
  M('X2', 'one image cell among the targets is enough', 'P3', COLUMN,
    '!types.every((t) => t === IMAGE_TYPE)', '!types.some((t) => t === IMAGE_TYPE)'),
  M('X3', 'two pictures pass', 'P4', COLUMN, 'if (images.length > 1 || list.length > 1)', 'if (false)'),
  M('X4', 'a drop takes any image cell under the point, not the topmost cell', 'I1', COLUMN,
    ".find((el) => el && el.classList && el.classList.contains('ag-cell'));",
    ".find((el) => el && el.classList && el.classList.contains('ag-cell') && (types || {})[el.getAttribute('col-id')] === IMAGE_TYPE);"),
  M('X5', 'the server\'s sentence is not read', 'U1', COLUMN,
    "typeof answer.detail === 'string' && answer.detail ? answer.detail : ", ''),
  M('X6', 'the paste writes its text even when it uploaded the picture', 'R1', CLIPBOARD,
    '  const value = image ? await uploadedRef(image.file, targetCells[0].colId) : text;',
    '  if (image) await uploadedRef(image.file, targetCells[0].colId);\n  const value = text;'),
  M('X7', 'a refused upload writes the refusal into the cell', 'R4', CLIPBOARD,
    "  if (got.refused) { sayStopped(got.refused); return ''; }", '  if (got.refused) { return got.refused; }'),
  M('X8', 'text of only whitespace counts as none, as isBlank reads it', 'P6', COLUMN,
    '  if (text) return null;\n', '  if (!isBlank(text)) return null;\n'),
  M('X9', 'the listener drops an Excel empty cell\'s text before asking (its picture uploads)', 'R5', CLIPBOARD,
    'pastedImage(text, files,', 'pastedImage(text.trim(), files,'),
];
const scored = await scoreMutants(MUTANTS, async (mu) => quietly(async () => {
  const mutate = (t) => swap(t, mu.from, mu.to);
  const C2 = mu.file === COLUMN ? (await loadWithProbe(COLUMN, { mutate, tag: `ipx${mu.id}` })).module : C;
  const CB2 = mu.file === CLIPBOARD ? (await loadWithProbe(CLIPBOARD, { mutate, tag: `ipx${mu.id}` })).module : CB;
  return suite(C2, CB2);
}), { baselineNames: base.names, title: '\n  [mutants] - each must be caught by the check it names.' });
pass += MUTANTS.length - scored.wrong;
for (let i = 0; i < scored.wrong; i += 1) failures.push(`mutant verdict ${i + 1}`);

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
