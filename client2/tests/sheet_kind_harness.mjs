// The sheet kind (owner 10-13 3b97fcfb9 · 4554ee685 · «포맷팅 기능 필요»; lead 10-14 ㄱ): the visible area of a Sheet -
// an A1 grid that grows to the last cell written, a cell's value as its format says (numbers · times · a node's name or
// keys, a closed table, else «unknown format»), the key's node by its walk label, the input only while edited (in the
// cell or the formula bar), #MANY · #NAME? · #CYCLE with their reasons, one key a sheet, a format that writes the
// declaration and nothing else, and a declaration that comes back the same. It imports its subject; the page is the
// board's stub document.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { makeDoc, walk as walkAll } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { entitySeedId } from '../src/rnd_board/api.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const ascii = (t) => String(t).replace(/[^\x00-\x7f]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
const hasClass = (n, cls) => String(n.className || '').split(/\s+/).includes(cls);
const KEY = entitySeedId('lot_slot', { lot: 'L1', slot: '05' });
const ROW = (reads = {}) => ({ id: KEY, label: 'L1 · 05', reads });

function seen(M) {
  const S = M.sheet;
  const out = {};
  const textOf = (model, at) => model.grid.flat().find((c) => c.at === at);
  // ── the grid's size ──
  out.size = [S.sheetModel([], { declaration: {} }), S.sheetModel([], { declaration: { cells: { C12: { input: 'x' } } } }),
    S.sheetModel([], { declaration: { cells: { H2: { input: '1' } } } })].map((m) => [m.cols, m.rows]);
  // ── formats: a number, its negative, zero, nothing; a time; a node ──
  const f = (v, fmt, node) => S.formatValue(v, fmt, node).text;
  out.numbers = ['0', '0.00', '#,##0', '0.0%', '0.00E+00'].map((fmt) => [fmt, f(1234.5, fmt), f(-1234.5, fmt), f(0, fmt), f(null, fmt)]);
  out.small = [f(0.1234, '0.0%'), f(-0.00123, '0.00E+00'), f('2.5', '0'), f('29 mm', '0.00'), f(-0.4, '0'), f(-0.001, '0.00')];
  out.times = [f('2026-10-01 09:30:00', 'yyyy-mm-dd'), f('2026-10-01 09:30:00', 'yyyy-mm-dd hh:mm'), f('late', 'yyyy-mm-dd')];
  const node = { label: 'L1 · 05', keys: { lot: 'L1', slot: '05' } };
  out.nodes = [f(KEY, null, node), f(KEY, 'name', node), f(KEY, 'key', node), f(KEY, 'key:slot', node),
    S.formatValue(KEY, 'key:nope', node).why || null];
  out.unknown = [S.formatValue(7, 'abc').text, S.formatValue(7, 'abc').why || null, S.formatValue(7, '0').why || null];
  // ── a cell: the key's node, formula reads, literals ──
  const decl = { key: 'A1', cells: { A1: { input: '=lot_slot("L1", "05")' }, B1: { input: '=Avg([measures.value])', format: '0.00' },
    B2: { input: '=[measures.value]' }, B3: { input: '=nope' }, B4: { input: '=B5' }, B5: { input: '=B4' }, C1: { input: '12' },
    C2: { input: 'note' } } };
  const reads = { B1: { state: 'one', value: 3.14159 }, B2: { state: 'several', values: [1, 2, 3] },
    B3: { state: 'empty', why: 'No value named nope on lot_slot' }, B4: { state: 'cycle', ring: ['B4', 'B5', 'B4'] } };
  const model = S.sheetModel([ROW(reads)], { declaration: decl });
  out.cells = ['A1', 'B1', 'B2', 'B3', 'B4', 'C1', 'C2'].map((at) => { const c = textOf(model, at); return [at, c.text, c.why || null, c.num]; });
  out.keyNoRow = textOf(S.sheetModel([], { declaration: decl }), 'A1').text;
  // ── the slots the root reads: the formula cells, the key aside ──
  out.slots = S.slots({}, decl).map((s) => [s.key, s.slot.expr]);
  // ── one key a sheet ──
  out.keys = [S.keyPatch({ key: null }, 'B2'), S.keyPatch({ key: 'A1' }, 'A1'), S.keyPatch({ key: 'A1' }, 'B2')];
  // ── a cell left empty is out of the declaration ──
  out.withCell = [S.withCell({ A1: { input: 'x' } }, 'A1', { input: '' }), S.withCell({ A1: { input: 'x', format: '0' } }, 'A1', { input: '' }),
    S.withCell({}, 'B2', { format: null })];
  // ── the page: pick, edit, format, key ──
  const doc = makeDoc('light');
  const draw = (body, d, rows, declared) => {
    const ctx = { doc, declaration: d, declare: (patch) => { declared.push(patch); } };
    S.render(body, S.sheetModel(rows, ctx), ctx);
  };
  const cellTd = (body, at) => walkAll(body).find((n) => n.tagName === 'TD' && n.attrs && n.attrs['data-at'] === at);
  const bar = (body) => walkAll(body).find((n) => hasClass(n, 'sf-sheet__input'));
  const sayOf = (body) => (walkAll(body).find((n) => hasClass(n, 'sf-sheet__say')) || {})._text || '';
  {
    const body = doc.createElement('div');
    const declared = [];
    draw(body, decl, [ROW(reads)], declared);
    const keyShown = cellTd(body, 'A1')._text;
    cellTd(body, 'A1').dispatch('click', {});
    const keyInput = bar(body).value;
    cellTd(body, 'B1').dispatch('click', {});
    out.page = { keyShown, keyInput, b1Shown: cellTd(body, 'B1')._text, b1Bar: bar(body).value, b1Sel: hasClass(cellTd(body, 'B1'), 'is-sel') };
    // edited in place: Enter writes the input, Escape writes nothing
    cellTd(body, 'C1').dispatch('dblclick', {});
    const box = walkAll(cellTd(body, 'C1')).find((n) => hasClass(n, 'sf-sheet__edit'));
    out.page.editBox = box ? box.value : null;
    if (box) { box.value = '=C1*2'; box.dispatch('keydown', { key: 'Enter', preventDefault() {} }); }
    cellTd(body, 'C2').dispatch('dblclick', {});
    const box2 = walkAll(cellTd(body, 'C2')).find((n) => hasClass(n, 'sf-sheet__edit'));
    if (box2) { box2.value = 'changed'; box2.dispatch('keydown', { key: 'Escape' }); }
    out.page.edits = declared.map((p) => p.cells && p.cells.C1 && p.cells.C1.input);
    out.page.c2 = declared.some((p) => p.cells && p.cells.C2 && p.cells.C2.input === 'changed');
    // two cells, one format: one declaration, their inputs as they were
    declared.length = 0;
    cellTd(body, 'B2').dispatch('click', {});
    cellTd(body, 'C1').dispatch('click', { ctrlKey: true });
    const fmt = walkAll(body).find((n) => hasClass(n, 'sf-sheet__fmt'));
    fmt.value = '#,##0';
    fmt.dispatch('change', {});
    const p = declared[0] || { cells: {} };
    out.page.format = [declared.length, p.cells.B2 && p.cells.B2.format, p.cells.C1 && p.cells.C1.format,
      p.cells.B2 && p.cells.B2.input, p.cells.C1 && p.cells.C1.input, Object.keys(p).join(',')];
    // a format not in the table: said, nothing written
    declared.length = 0;
    const typed = walkAll(body).find((n) => hasClass(n, 'sf-sheet__fmtx'));
    typed.value = 'abc';
    typed.dispatch('keydown', { key: 'Enter', preventDefault() {} });
    out.page.unknown = [declared.length, sayOf(body)];
    // a second key: refused in a line, nothing written
    cellTd(body, 'B2').dispatch('click', {});
    walkAll(body).find((n) => hasClass(n, 'sf-sheet__key')).dispatch('click', {});
    out.page.secondKey = [declared.length, sayOf(body)];
    // an error cell says its reason when picked
    cellTd(body, 'B2').dispatch('click', {});
    out.page.reason = sayOf(body);
  }
  // ── two sheets on one page pick apart ──
  {
    const a = doc.createElement('div'); const b = doc.createElement('div');
    draw(a, decl, [ROW(reads)], []); draw(b, decl, [ROW(reads)], []);
    cellTd(a, 'C2').dispatch('click', {});
    out.two = [hasClass(cellTd(a, 'C2'), 'is-sel'), hasClass(cellTd(b, 'C2'), 'is-sel'), hasClass(cellTd(b, 'A1'), 'is-sel')];
  }
  // ── saved and opened: the same cells, the same picture ──
  const back = JSON.parse(JSON.stringify(decl));
  const again = S.sheetModel([ROW(reads)], { declaration: back });
  out.round = JSON.stringify(again.grid.flat().map((c) => [c.at, c.input, c.text])) === JSON.stringify(model.grid.flat().map((c) => [c.at, c.input, c.text]))
    && JSON.stringify(back.cells) === JSON.stringify(decl.cells);
  return out;
}

function suite(out) {
  const names = [];
  const failures = [];
  const eq = (name, got, want) => {
    names.push(name);
    const g = ascii(JSON.stringify(got)), w = ascii(JSON.stringify(want));
    if (g === w) { console.log(`  PASS ${name}`); return; }
    failures.push(name);
    console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`);
  };
  eq('S1 the grid: five by ten at least, else the last cell written and two columns, five rows past it', out.size, [[5, 10], [5, 17], [10, 10]]);
  eq('S2 number formats: a number, its negative, zero, nothing - rounded, grouped, percent, scientific', out.numbers, [
    ['0', '1235', '-1235', '0', ''], ['0.00', '1234.50', '-1234.50', '0.00', ''], ['#,##0', '1,235', '-1,235', '0', ''],
    ['0.0%', '123450.0%', '-123450.0%', '0.0%', ''], ['0.00E+00', '1.23E+03', '-1.23E+03', '0.00E+00', '']]);
  eq('S3 a fraction, a small negative, a number written as text; a text a number format cannot read stays as written; no -0', out.small, ['12.3%', '-1.23E-03', '3', '29 mm', '0', '0.00']);
  eq('S4 time formats: the day, the day and minute; not a time stays as written', out.times, ['2026-10-01', '2026-10-01 09:30', 'late']);
  eq('S5 a node: its name by default and by «name», its keys, one key by name; a key it has not is said', out.nodes,
    ['L1 · 05', 'L1 · 05', 'L1 · 05', '05', 'No key nope on this node']);
  eq('S6 a format not in the table: the value as it is and «unknown format»; one in the table says nothing', out.unknown, ['7', 'unknown format', null]);
  eq('S7 cells: the key its node\'s walk label, a formula its read formatted, several #MANY, no name #NAME?, a ring #CYCLE, a literal as written',
    out.cells, [['A1', 'L1 · 05', null, false], ['B1', '3.14', null, true], ['B2', '#MANY', '3 values — wrap in an aggregate', false],
      ['B3', '#NAME?', 'No value named nope on lot_slot', false], ['B4', '#CYCLE', 'A cycle: B4 → B5 → B4', false], ['C1', '12', null, true],
      ['C2', 'note', null, false]]);
  eq('S8 the key with no walk yet shows nothing - never its constructor text', out.keyNoRow, '');
  eq('S9 the slots the root reads: every formula cell but the key, the input after «=»', out.slots,
    [['B1', 'Avg([measures.value])'], ['B2', '[measures.value]'], ['B3', 'nope'], ['B4', 'B5'], ['B5', 'B4']]);
  eq('S10 one key a sheet: placed, taken back, a second refused', out.keys,
    [{ patch: { key: 'B2' } }, { patch: { key: null } }, { refused: 'one key per sheet' }]);
  eq('S11 a cell emptied with no format leaves the declaration; with a format it keeps the format', out.withCell, [{}, { A1: { format: '0' } }, {}]);
  eq('S12 the page: a cell shows its value, the formula bar its input - the key its name in the cell, its constructor in the bar',
    out.page && [out.page.keyShown, out.page.keyInput, out.page.b1Shown, out.page.b1Bar, out.page.b1Sel],
    ['L1 · 05', '=lot_slot("L1", "05")', '3.14', '=Avg([measures.value])', true]);
  eq('S13 edited in place: the box holds the input, Enter writes it, Escape writes nothing', out.page && [out.page.editBox, out.page.edits, out.page.c2],
    ['12', ['=C1*2'], false]);
  eq('S14 a format on two cells: one declaration of cells, their formats set and their inputs as they were', out.page && out.page.format,
    [1, '#,##0', '#,##0', '=[measures.value]', '12', 'cells']);
  eq('S15 a typed format not in the table: «unknown format», nothing written', out.page && out.page.unknown, [0, 'unknown format']);
  eq('S16 a second key: «one key per sheet», nothing written', out.page && out.page.secondKey, [0, 'one key per sheet']);
  eq('S17 an error cell picked says its reason', out.page && out.page.reason, '3 values — wrap in an aggregate');
  eq('S18 two sheets on one page: a pick in one is not the other\'s', out.two, [true, false, true]);
  eq('S19 saved and opened: the same cells and the same picture', out.round, true);
  return { ran: names.length, names, failures };
}

const REAL = { sheet: await import('../src/testbed/kinds/sheet.js') };
console.log('\n[1] the sheet kind');
const base = suite(seen(REAL));
let ran = base.ran;
let failed = base.failures.length;
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const F = 'testbed/kinds/sheet.js';
const MUTANTS = [
  { id: 'SM1', what: 'a small negative drawn -0', catches: 'S3', mutate: (t) => swap(t, '  return /^-[0.]+$/.test(text) ? text.slice(1) : text;', '  return text;') },
  { id: 'SM2', what: 'thousands not grouped', catches: 'S2', mutate: (t) => swap(t, "  if (f === '#,##0') return { text: grouped(fixed(x, 0)) };", "  if (f === '#,##0') return { text: fixed(x, 0) };") },
  { id: 'SM3', what: 'the exponent unpadded (1.23E+3)', catches: 'S2', mutate: (t) => swap(t, '${pad(Math.abs(Number(e)))}', '${Math.abs(Number(e))}') },
  { id: 'SM4', what: 'any format passes as known', catches: 'S6', mutate: (t) => swap(t, 'export const knownFormat = (f) => !f || FORMATS.includes(f) || KEY_FORMAT.test(f);', 'export const knownFormat = () => true;') },
  { id: 'SM5', what: 'the key cell shows its constructor text', catches: 'S12', mutate: (t) => swap(t, "    if (row) { value = row.id; node = nodeOf(row.id, row.label) || { label: row.label || row.id, keys: {} }; }",
    "    value = input;") },
  { id: 'SM6', what: 'a second key replaces the first', catches: 'S10', mutate: (t) => swap(t, '  if (decl.key) return { refused: SHEET_WORDS.oneKey };\n', '') },
  { id: 'SM7', what: 'several values drawn as the first', catches: 'S7', mutate: (t) => swap(t, "    else if (read && read.state === 'several') {", "    else if (read && read.state === 'several' && false) {") },
  { id: 'SM8', what: 'the key read as a formula slot', catches: 'S9', mutate: (t) => swap(t, '  .filter(([at, spec]) => at !== (declaration && declaration.key) && spec', '  .filter(([at, spec]) => spec') },
  { id: 'SM9', what: 'a format change writes inputs too (the formula bar\'s text into every picked cell)', catches: 'S14',
    mutate: (t) => swap(t, '    for (const at of own.sel) cells = withCell(cells, at, { format: format || null });', '    for (const at of own.sel) cells = withCell(cells, at, { format: format || null, input: input.value });') },
  { id: 'SM10', what: 'Escape keeps the edit', catches: 'S13', mutate: (t) => swap(t, "          if (e.key === 'Escape') finish(false);", "          if (e.key === 'Escape') finish(true);") },
  { id: 'SM11', what: 'the pick lives on the module, not the part', catches: 'S18',
    mutate: (t) => swap(t, '  const own = body.sheetPick || (body.sheetPick = { sel: [\'A1\'], anchor: \'A1\', say: \'\' });',
      '  const own = SHARED;').replace('export function render(', "const SHARED = { sel: ['A1'], anchor: 'A1', say: '' };\nexport function render(") },
  { id: 'SM12', what: 'the grid does not grow past the cells written', catches: 'S1 the grid', mutate: (t) => swap(t, 'const MARGIN = { c: 2, r: 5 };', 'const MARGIN = { c: 0, r: 0 };') },
];
const scored = await scoreMutants(MUTANTS.map((m) => ({ ...m, file: F })), async (m) => {
  const copy = (await loadWithProbe(join(SRC, F), { mutate: m.mutate })).module;
  return suite(seen({ sheet: copy }));
}, { baselineRan: base.ran, baselineNames: base.names, title: '\n  [1] mutants - each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;
console.log(`\n${ran - failed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
