// THE TEST BED DRAWS WHAT IS IN VIEW (owner 10-20 «일단 ㄱ», lead 9075f6605): measured on the dense walk board a table
// part drew 34,075 lines and the filters panel 34,616 boxes at once, and the browser's layout held the page 27-307 s.
//   W  the table draws the lines in view and a spacer line above and below: no layout to measure - the first 2 x OVERSCAN;
//      a box of 300 px over lines of 20 px - those 15 and OVERSCAN either side; scrolled - the window follows, starting on
//      an even line (a line keeps its stripe); a drag scrolled past lines not drawn marks every line between
//   F  a filter of more than FILTER_TOP values draws the most counted FILTER_TOP, a search box and «N more»; a value not
//      drawn keeps its check; the search narrows the values; the panel keeps what was typed when a check draws it again
// Imports only (the probe copies a module whole); each defect must go red at its line.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, walk } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'testbed');
const FILES = { table: path.join(SRC, 'kinds', 'table.js'), cond: path.join(SRC, 'condition_editor.js'), filters: path.join(SRC, 'filters_part.js') };
const STORE = await import('../src/testbed/keyed_store.js');

let ran = 0;
let failed = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1;
  NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failed.push(name);
  console.log(`  FAIL ${name}${detail === undefined ? '' : ` -- ${detail}`}`);
};

async function deps(m = null) {
  const out = {};
  for (const [key, file] of Object.entries(FILES)) {
    const mutate = m && m.file === key ? m.mutate : undefined;
    out[key] = (await loadWithProbe(file, mutate ? { mutate } : {})).module;
  }
  return out;
}

/** A table model of `n` lines, one number column. */
const modelOf = (n) => ({ keys: ['col1'], sort: null, numeric: [true], next: 'col2', pictured: false,
  lines: Array.from({ length: n }, (_, i) => ({ id: `L${i}`, ids: [`L${i}`], cells: [{ text: String(i), value: i }], marked: false, color: null })) });
const lineRows = (area) => walk(area).filter((n) => n.tagName === 'TR' && String(n.className) !== 'tb-table__pad' && n.children[0] && n.children[0].tagName === 'TD');
const padHeights = (area) => walk(area).filter((n) => String(n.className) === 'tb-table__pad').map((tr) => tr.children[0].style.height);

async function suite(M) {
  ran = 0;
  failed = [];
  NAMES.length = 0;
  const marks = [];
  const ctxOf = (doc) => ({ doc, words: (k) => k, declare() {}, mark: (ids) => marks.push(ids), clear() {}, hover() {}, thumb: null });

  // W1 - no layout to measure (a stub, a box not shown yet): the first 2 x OVERSCAN lines
  const doc = makeDoc('dark');
  const area = doc.createElement('div');
  M.table.render(area, modelOf(500), ctxOf(doc));
  const first = lineRows(area);
  ok('W1 with nothing to measure, the first 2 x OVERSCAN lines and no more', first.length === 2 * M.table.OVERSCAN && first[0].children[0]._text === '0',
    `${first.length} lines`);

  // W2 - a box of 300 px over lines of 20 px: the lines in view and OVERSCAN below
  const laid = makeDoc('dark');
  const make = laid.createElement;
  laid.createElement = (tag) => { const n = make(tag); if (String(tag).toUpperCase() === 'TR') n.getBoundingClientRect = () => ({ top: 0, left: 0, width: 100, height: 20 }); return n; };
  const box = laid.createElement('div');
  const drawn = M.table.render(box, modelOf(500), ctxOf(laid));
  const wrap = box.children[0];
  wrap.clientHeight = 300;
  wrap.scrollTop = 0;
  drawn.resize();
  const atTop = lineRows(box);
  ok('W2 a 300 px box over 20 px lines: those 15 and OVERSCAN after, the rest a spacer as tall as its lines',
    atTop.length === 15 + M.table.OVERSCAN && JSON.stringify(padHeights(box)) === JSON.stringify(['0px', `${(500 - 35) * 20}px`]),
    `${atTop.length} lines, pads ${JSON.stringify(padHeights(box))}`);

  // W3 - scrolled to line 100: OVERSCAN before it, the 15 in view, OVERSCAN after
  wrap.scrollTop = 2000;
  drawn.resize();
  const mid = lineRows(box);
  ok('W3 scrolled, the window follows: line 80 first, 55 lines, the spacers as tall as the lines they stand for',
    mid[0].children[0]._text === '80' && mid.length === 55 && JSON.stringify(padHeights(box)) === JSON.stringify(['1600px', `${(500 - 135) * 20}px`]),
    `first ${mid[0] && mid[0].children[0]._text}, ${mid.length} lines, pads ${JSON.stringify(padHeights(box))}`);

  // W4 - a window that would start on an odd line starts one earlier: a line keeps its stripe (nth-child) as it scrolls
  wrap.scrollTop = 2020;
  drawn.resize();
  ok('W4 the window starts on an even line', lineRows(box)[0].children[0]._text === '80', lineRows(box)[0].children[0]._text);

  // W5 - a drag from line 80, scrolled down, let go on line 210: every line between is marked, drawn or not
  const from = lineRows(box)[0];
  from.dispatch('pointerdown', {});
  wrap.scrollTop = 4000;
  drawn.resize();
  const to = lineRows(box).find((tr) => tr.children[0]._text === '210');
  to.dispatch('pointerenter', {});
  to.dispatch('pointerup', {});
  const got = marks[marks.length - 1] || [];
  ok('W5 a drag scrolled past lines not drawn marks every line between', got.length === 131 && got[0] === 'L80' && got[130] === 'L210',
    `${got.length} marked`);

  // F - one slot's filter
  const fdoc = makeDoc('dark');
  const many = Array.from({ length: 100 }, (_, i) => [`v${i}`, i + 1]);
  const summary = (values) => ({ row: 'die', words: 'defect', slot: { steps: [], value: { on: 'label', name: 'name' } }, values, empty: 0 });
  const said = [];
  const searched = [];
  const control = M.cond.drawCondition(fdoc, summary(many), null, (next) => said.push(next), { search: '', onSearch: (t) => searched.push(t) });
  const valueLines = (root) => walk(root).filter((n) => String(n.className) === 'sf-filter__v' && walk(n).some((x) => String(x.className) === 'sf-filter__t'));
  const textOf = (line) => walk(line).find((x) => String(x.className) === 'sf-filter__t')._text;
  const more = (root) => (walk(root).find((n) => String(n.className) === 'sf-filter__more') || {})._text;
  const search = walk(control).find((n) => String(n.className) === 'sf-filter__search');
  const shown = valueLines(control);
  ok('F1 a slot of 100 values: the 20 most counted, a search box, «80 more»',
    shown.length === M.cond.FILTER_TOP && textOf(shown[0]) === 'v99' && Boolean(search) && more(control) === '80 more',
    `${shown.length} lines, first ${shown[0] && textOf(shown[0])}, more ${more(control)}`);
  const box99 = walk(shown[0]).find((n) => n.tagName === 'INPUT');
  box99.checked = false;
  box99.dispatch('change', {});
  const next = said[said.length - 1] || { values: [] };
  ok('F2 a drawn value unchecked: every value not drawn keeps its check', next.values.length === 99 && next.values.includes('v0') && !next.values.includes('v99'),
    `${next.values.length} kept`);
  search.value = 'v1';
  search.dispatch('input', {});
  const found = valueLines(control);
  ok('F3 the search narrows to the values it matches, the most counted first',
    found.length === 11 && textOf(found[0]) === 'v19' && !more(control) && searched[searched.length - 1] === 'v1',
    `${found.length} lines, first ${found[0] && textOf(found[0])}`);
  const few = M.cond.drawCondition(fdoc, summary([['b', 1], ['a', 9]]), null, () => {});
  ok('F4 a slot of few values draws them all in their order, no search box',
    valueLines(few).map(textOf).join(',') === 'b,a' && !walk(few).some((n) => String(n.className) === 'sf-filter__search'));

  // F5 - the panel: a check draws it again and the search box still holds what was typed
  const pdoc = makeDoc('dark');
  const filters = new STORE.KeyedStore({ 'filter:1': [] });
  const stats = new STORE.KeyedStore({ p1: { slots: [summary(many)] } });
  const active = new STORE.KeyedStore({ active: 'p1' });
  const host = pdoc.createElement('div');
  const panel = new M.filters.FiltersPart(host, { doc: pdoc, filters, stats, active });
  panel.mount();
  const panelSearch = () => walk(host).find((n) => String(n.className) === 'sf-filter__search');
  panelSearch().value = 'v2';
  panelSearch().dispatch('input', {});
  const line = valueLines(host)[0];
  const check = walk(line).find((n) => n.tagName === 'INPUT');
  check.checked = false;
  check.dispatch('change', {});
  ok('F5 a check draws the panel again and its search box keeps what was typed', panelSearch().value === 'v2' && textOf(valueLines(host)[0]) === 'v29',
    `search «${panelSearch().value}», first ${textOf(valueLines(host)[0])}`);
  return { ran, failed: failed.slice() };
}

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { name: 'every line drawn when there is nothing to measure', catches: ['W1'], file: 'table', mutate: swap('      : [0, Math.min(n, 2 * OVERSCAN)];', '      : [0, n];') },
  { name: 'the window does not follow the scroll', catches: ['W3'], file: 'table', mutate: swap('Math.floor(top / rowPx) - OVERSCAN', '0 - OVERSCAN') },
  { name: 'the window starts on an odd line', catches: ['W4'], file: 'table', mutate: swap('    a -= a % 2;\n', '') },
  { name: 'a drag marks only the lines drawn', catches: ['W5'], file: 'table',
    mutate: swap('    const between = model.lines.slice(Math.min(...at), Math.max(...at) + 1);', '    const between = spanned.map((c) => c.data);') },
  { name: 'every value drawn', catches: ['F1'], file: 'cond', mutate: swap('      const shown = many ? [...matched].sort((x, y) => y[1] - x[1]).slice(0, FILTER_TOP) : matched;', '      const shown = matched;') },
  { name: 'a check forgets the values not drawn', catches: ['F2'], file: 'cond',
    mutate: swap('        const next = summary.values.map(([x]) => x)', '        const next = summary.values.slice(-FILTER_TOP).map(([x]) => x)') },
  { name: 'the search narrows nothing', catches: ['F3'], file: 'cond',
    mutate: swap("      const matched = want ? summary.values.filter(([v]) => valueText(v, summary.time).toLowerCase().includes(want)) : summary.values;", '      const matched = summary.values;') },
  { name: 'the panel forgets what was typed', catches: ['F5'], file: 'filters', mutate: swap("{ search: this.searches.get(key) || '',", "{ search: '',") },
];

const base = await suite(await deps());
const BASE_NAMES = NAMES.slice();
if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
const { wrong } = await scoreMutants(MUTANTS, async (m) => {
  const d = await deps(m);
  const real = console.log;
  console.log = () => {};
  try { const r = await suite(d); return { failures: r.failed, ran: r.ran }; } finally { console.log = real; }
}, { baselineRan: base.ran, baselineNames: BASE_NAMES, title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
process.exit(wrong ? 1 : 0);
