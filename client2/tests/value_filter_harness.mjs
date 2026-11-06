// value_filter_harness — a grid column's one filter (src/value_filter.js, lead 11-06 ㄱ): Pick · Paste list · Condition.
// The gate the lead set: the Condition tab makes the SAME model AG Grid's text and number filters made - the tables below are
// AG Grid 35's own (SimpleFilter.getModelFromUi · TextFilter/NumberFilter values · SimpleFloatingFilter · the text and number
// filter handlers, node_modules/ag-grid-community main.esm.mjs), row by row. Then the set filter (A ea92380da), the paste
// list, the floating cell's typing, and two filters on one page not touching each other.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, byClass } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, '..', 'src', 'value_filter.js');
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const walk = (n) => [n, ...(n.children || []).flatMap(walk)];
const byTag = (n, tag) => walk(n).filter((c) => c.tagName === tag);

const T = (type, filter, filterTo) => ({ filterType: 'text', type, ...(filter !== undefined ? { filter } : {}), ...(filterTo !== undefined ? { filterTo } : {}) });
const N = (type, filter, filterTo) => ({ filterType: 'number', type, ...(filter !== undefined ? { filter } : {}), ...(filterTo !== undefined ? { filterTo } : {}) });

// C — the Condition tab's rows -> the model, as AG Grid built it from the same inputs
const CONDITIONS = [
  ['text contains', 'text', [{ type: 'contains', from: 'a' }], 'AND', T('contains', 'a')],
  ['text kept as typed, spaces too (trimInput off)', 'text', [{ type: 'equals', from: ' a ' }], 'AND', T('equals', ' a ')],
  ['text empty is no filter', 'text', [{ type: 'contains', from: '' }], 'AND', null],
  ['blank takes no value', 'text', [{ type: 'blank', from: 'ignored' }], 'AND', T('blank')],
  ['number parsed', 'number', [{ type: 'equals', from: '12.5' }], 'AND', N('equals', 12.5)],
  ['number «-» is none', 'number', [{ type: 'equals', from: '-' }], 'AND', null],
  ['number range', 'number', [{ type: 'inRange', from: '1', to: '5' }], 'AND', N('inRange', 1, 5)],
  ['number range half typed is none', 'number', [{ type: 'inRange', from: '1', to: '' }], 'AND', null],
  ['number not blank', 'number', [{ type: 'notBlank' }], 'AND', N('notBlank')],
  ['two joined AND', 'text', [{ type: 'contains', from: 'a' }, { type: 'endsWith', from: 'z' }], 'AND',
    { filterType: 'text', operator: 'AND', conditions: [T('contains', 'a'), T('endsWith', 'z')] }],
  ['two joined OR', 'number', [{ type: 'lessThan', from: '3' }, { type: 'greaterThan', from: '9' }], 'OR',
    { filterType: 'number', operator: 'OR', conditions: [N('lessThan', 3), N('greaterThan', 9)] }],
  ['the second empty: the first alone', 'text', [{ type: 'contains', from: 'a' }, { type: 'contains', from: '' }], 'OR', T('contains', 'a')],
];

// F — the floating cell: (model, column's first type) -> [the type it types into, can it type, what it shows]
const FLOATING = [
  ['none', null, 'contains', ['contains', true, '']],
  ['none, an equal-index column', null, 'equals', ['equals', true, '']],
  ['one condition', T('equals', 'x'), 'contains', ['equals', true, 'x']],
  ['a range', N('inRange', 1, 5), 'equals', ['inRange', false, '1-5']],
  ['blank', T('blank'), 'contains', ['blank', false, 'Blank']],
  ['two conditions', { filterType: 'text', operator: 'AND', conditions: [T('startsWith', 'a'), T('contains', 'b')] }, 'contains',
    ['startsWith', false, 'a AND b']],
  ['a set', { filterType: 'set', values: ['a', 'b', null] }, 'contains', ['contains', false, 'any of 3']],
];

// P — a held row's cell: AG Grid's text and number handlers for a condition, the server's rule for a set
const PASSES = [
  ['contains, either case', 'text', T('contains', 'Ab'), 'xaBy', true],
  ['equals, either case', 'text', T('equals', 'a'), 'A', true],
  ['contains on no value', 'text', T('contains', 'a'), null, false],
  ['notContains on no value', 'text', T('notContains', 'a'), null, true],
  ['blank on spaces', 'text', T('blank'), '   ', true],
  ['greater than, a number in text', 'number', N('greaterThan', 3), '4', true],
  ['range is exclusive (inRangeInclusive off)', 'number', N('inRange', 1, 5), 5, false],
  ['range inside', 'number', N('inRange', 1, 5), 3, true],
  ['equals on no value', 'number', N('equals', 3), null, false],
  ['OR passes on one', 'text', { filterType: 'text', operator: 'OR', conditions: [T('equals', 'x'), T('equals', 'y')] }, 'y', true],
  ['AND needs both', 'text', { filterType: 'text', operator: 'AND', conditions: [T('contains', 'x'), T('contains', 'y')] }, 'xz', false],
  ['set: a listed text', 'text', { filterType: 'set', values: ['a', null] }, 'a', true],
  ['set: null is the blank cells', 'text', { filterType: 'set', values: ['a', null] }, '', true],
  ['set: not listed', 'text', { filterType: 'set', values: ['a', null] }, 'b', false],
  ['set: a text set is exact', 'text', { filterType: 'set', values: ['a'] }, 'A', false],
  ['set: a number column by number', 'number', { filterType: 'set', values: [3] }, '3.0', true],
  ['set: none listed, no row', 'text', { filterType: 'set', values: [] }, 'a', false],
];

/** A ValueFilter in a fake page: its params recorded, its value reads answered by hand. */
function filterOn(m, doc, opts = {}) {
  const calls = { changed: [], hidden: 0, reads: [] };
  const pending = [];
  const f = new m.ValueFilter();
  f.init({
    kind: opts.kind || 'text', options: opts.options, defaultOption: opts.defaultOption, doc,
    column: { getColId: () => opts.col || 'lot' },
    getValue: (node) => node.cell,
    filterChangedCallback: (extra) => calls.changed.push(extra || null),
    readValues: (col, search) => new Promise((done) => { calls.reads.push([col, search]); pending.push(done); }),
  });
  return { f, calls, pending, open: () => f.afterGuiAttached({ hidePopup: () => { calls.hidden += 1; } }) };
}

const texts = (f) => byClass(f.listBox, 'value-filter__value').map((l) => l.textContent);
const boxes = (f) => byClass(f.listBox, 'value-filter__value').map((l) => byTag(l, 'INPUT')[0]);
const click = (el) => el.dispatch('click');
const setInput = (el, v) => { el.value = v; el.dispatch('input'); };

async function suite(m) {
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };

  eq('C1 the Condition tab makes AG Grid\'s model from the same inputs - each row of the table',
    CONDITIONS.map(([, kind, rows, op]) => m.conditionModel(kind, rows, op)), CONDITIONS.map((r) => r[4]));
  const models = CONDITIONS.map((r) => r[4]).filter(Boolean);
  eq('C2 a model reopened and applied unchanged is the same model (rowsOf ∘ conditionModel)',
    models.map((md) => { const { rows, operator } = m.rowsOf(md, 'contains'); return m.conditionModel(md.filterType, rows, operator); }), models);
  eq('C3 the option lists are AG Grid 35\'s, in its order', [m.TEXT_OPTIONS, m.NUMBER_OPTIONS],
    [['contains', 'notContains', 'equals', 'notEqual', 'startsWith', 'endsWith', 'blank', 'notBlank'],
      ['equals', 'notEqual', 'greaterThan', 'greaterThanOrEqual', 'lessThan', 'lessThanOrEqual', 'inRange', 'blank', 'notBlank']]);

  eq('F1 the floating cell: the type it types into, whether it types, what it shows - each row',
    FLOATING.map(([, md, def]) => { const last = m.lastTypeOf(md, def); return [last, m.floatingEditable(md, last), m.floatingText(md)]; }),
    FLOATING.map((r) => r[3]));
  eq('F2 a key in it is one condition of that type; emptied, no filter',
    [m.floatingModel('text', 'equals', 'x'), m.floatingModel('number', 'equals', '7'), m.floatingModel('text', 'contains', '')],
    [T('equals', 'x'), N('equals', 7), null]);

  eq('P1 a held row\'s cell passes as AG Grid (a condition) and the server (a set) judge it - each row',
    PASSES.map(([, kind, md, cell]) => m.passes(kind, md, cell)), PASSES.map((r) => r[4]));

  eq('L1 a pasted list: lines, commas and tabs; trimmed, empty dropped, each once; a number column\'s numbers as numbers',
    [m.pasteValues('text', 'a\nb, a\tc\r\n\n'), m.pasteValues('number', '1, 2.5, x')],
    [{ values: ['a', 'b', 'c'], duplicates: 1 }, { values: [1, 2.5, 'x'], duplicates: 0 }]);

  // V — the filter on a page
  const doc = makeDoc('light');
  const one = filterOn(m, doc);
  one.open();
  const reading = [one.f.searchLabel.textContent, one.calls.reads];
  one.pending.shift()({ values: ['A', 'B', null], more: false });
  await wait(0);
  eq('V01 opened: Pick reads the column\'s values once; drawn in the answer\'s order, the blank cells last as «(Blank)»',
    [reading, one.f.searchLabel.textContent, texts(one.f), one.f.applyButton.disabled],
    [['Reading…', [['lot', '']]], 'Search 3 values', ['A', 'B', '(Blank)'], true]);
  boxes(one.f)[0].checked = true; boxes(one.f)[0].dispatch('change');
  setInput(one.f.search, 'b');
  const shown = texts(one.f);
  const allBox = one.f.allBox;
  allBox.checked = true; allBox.dispatch('change');
  setInput(one.f.search, '');
  eq('V02 the search narrows here (a whole list); a pick stays through it; «Select all shown» takes what it shows',
    [shown, one.calls.reads.length, one.f.pickedWord.textContent, boxes(one.f).map((b) => b.checked)],
    [['B', '(Blank)'], 1, '3 selected', [true, true, true]]);
  click(one.f.applyButton);
  eq('V03 Apply: the set of the picks, the grid told once, the popup closed',
    [one.f.getModel(), one.f.isFilterActive(), one.calls.changed.length, one.calls.hidden],
    [{ filterType: 'set', values: ['A', 'B', null] }, true, 1, 1]);
  eq('V04 the grid\'s rows pass by the same rule', [{ cell: 'A' }, { cell: '' }, { cell: 'C' }].map((node) => one.f.doesFilterPass({ node })),
    [true, true, false]);

  one.open();
  const reopened = [one.f.tab, boxes(one.f).length];
  one.pending.shift()({ values: ['A', 'B', 'C', null], more: false });
  await wait(0);
  eq('V05 reopened on a set: Pick, its values ticked', [reopened, boxes(one.f).map((b) => b.checked)],
    [['pick', 0], [true, true, false, true]]);

  click(one.f.tabButtons[2]);
  const c = one.f.conds;
  c[0].type.value = 'contains'; c[0].type.dispatch('change');
  setInput(c[0].from, 'x');
  const secondShown = !c[1].box.hidden;
  one.f.joinBoxes[0].checked = false; one.f.joinBoxes[1].checked = true;   // a browser's radios: one of a group
  c[1].type.value = 'endsWith'; setInput(c[1].from, 'z');
  click(one.f.applyButton);
  eq('V06 the Condition tab applies AG Grid\'s two-condition model; its second comes once the first is whole',
    [secondShown, one.f.getModel()], [true, { filterType: 'text', operator: 'OR', conditions: [T('contains', 'x'), T('endsWith', 'z')] }]);
  one.open();
  eq('V07 reopened on a condition: the Condition tab, its rows and join as they were',
    [one.f.tab, c.map((r) => [r.type.value, r.from.value]), one.f.joinBoxes.map((r) => r.checked)],
    ['condition', [['contains', 'x'], ['endsWith', 'z']], [false, true]]);
  one.pending.shift()({ values: [], more: false });

  click(one.f.tabButtons[1]);
  setInput(one.f.pasteArea, 'a\nb\na');
  const pasteWords = [one.f.pasteCount.textContent, one.f.pasteDup.textContent];
  click(one.f.applyButton);
  eq('V08 Paste list: counted, duplicates said, applied as a set', [pasteWords, one.f.getModel()],
    [['2 values · equals any', '1 duplicate removed'], { filterType: 'set', values: ['a', 'b'] }]);
  click(one.f.clearButton);
  eq('V09 Clear: no filter, the grid told', [one.f.getModel(), one.f.isFilterActive(), one.calls.changed.length], [null, false, 4]);

  const two = filterOn(m, doc, { col: 'serial' });
  two.open();
  const first = two.pending.shift();
  setInput(two.f.search, '');
  two.f.readList('');
  two.pending.shift()({ values: ['NEW'], more: false });
  await wait(0);
  first({ values: ['OLD'], more: false });
  await wait(0);
  eq('V10 an answer a newer read passed is dropped', texts(two.f), ['NEW']);

  const big = filterOn(m, doc, { col: 'serial' });
  big.open();
  big.pending.shift()({ values: ['S1', 'S2'], more: true });
  await wait(0);
  const bigLabel = big.f.searchLabel.textContent;
  setInput(big.f.search, 'S9');
  const early = big.calls.reads.length;
  await wait(400);
  eq('V11 a list past the cap: said so; the search goes to the server after the keys stop, not here',
    [bigLabel, early, big.calls.reads], ['More than 10,000 values — type to search', 1, [['serial', ''], ['serial', 'S9']]]);

  const refused = filterOn(m, doc, { col: 'link' });
  refused.open();
  refused.pending.shift()({ refused: "is not a filter 'link' can read" });
  await wait(0);
  eq('V12 a refused read: the server\'s sentence where the list was, nothing to apply',
    [byClass(refused.f.listBox, 'refusal').map((n) => n.textContent), refused.f.applyButton.disabled],
    [["is not a filter 'link' can read"], true]);

  const a = filterOn(m, doc, { col: 'x' });
  const b = filterOn(m, doc, { col: 'y' });
  a.open(); b.open();
  a.pending.shift()({ values: ['1'], more: false }); b.pending.shift()({ values: ['1'], more: false });
  await wait(0);
  boxes(a.f)[0].checked = true; boxes(a.f)[0].dispatch('change');
  const formOf = (radio) => { for (let n = radio; n; n = n.parentNode) if (n.tagName === 'FORM') return n; return null; };
  eq('V13 two filters on one page: a pick in one is not in the other; their AND/OR are two forms',
    [a.f.picked.size, b.f.picked.size, formOf(a.f.joinBoxes[0]) !== formOf(b.f.joinBoxes[0]) && Boolean(formOf(a.f.joinBoxes[0]))],
    [1, 0, true]);

  a.f.onFloatingFilterChanged('equals', 'q');
  eq('V14 the floating cell\'s value: one condition of its type, the grid told it came from there',
    [a.f.getModel(), a.calls.changed.slice(-1)], [T('equals', 'q'), [{ afterFloatingFilter: true }]]);

  // the floating cell itself
  const sent = [];
  let parentModel = null;
  const ff = new m.ValueFloatingFilter();
  ff.init({ filterParams: { kind: 'number', doc }, column: { getColDef: () => ({ headerName: 'X' }), getColId: () => 'x' },
    currentParentModel: () => parentModel, showParentFilter: () => sent.push('open'),
    parentFilterInstance: (cb) => cb({ onFloatingFilterChanged: (type, value) => sent.push([type, value]) }) });
  const input = ff.input;
  const editable = [input.type, input.readOnly];
  setInput(input, '7');
  await wait(300);
  const before = sent.length;
  await wait(400);
  ff.onParentModelChanged({ filterType: 'set', values: [1, 2] });
  const asSet = [input.type, input.readOnly, input.value];
  click(input);
  ff.onParentModelChanged(N('equals', 9), { afterFloatingFilter: true });
  eq('V15 the floating cell: a number box; a key sent after AG Grid\'s 500 ms, once; a set read-only, a click opens the filter; its own echo ignored',
    [editable, before, sent, asSet, input.value], [['number', false], 0, [['equals', '7'], 'open'], ['text', true, 'any of 2'], 'any of 2']);
  ff.destroy();
  return { ran: ran.length, names: ran, failures };
}

const real = await import('../src/value_filter.js');
const base = await suite(real);
console.log('-- value filter -----------------------------------------------------');
for (const name of base.names) console.log(`  ${base.failures.some((f) => f.startsWith(name + ':')) ? 'FAIL' : 'PASS'} ${name}`);
base.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { id: 'M1', what: 'two conditions kept as the first alone', catches: ['C1'],
    mutate: swap('return conditions.length === 1 ? conditions[0] : { filterType: kind, operator, conditions };', 'return conditions[0];') },
  { id: 'M2', what: 'a number condition sent as its text', catches: ['C1'], mutate: swap('  const value = Number.parseFloat(text);', '  const value = text;') },
  { id: 'M3', what: 'a range taken inclusive', catches: ['P1'], mutate: swap("case 'inRange': return v > c.filter && v < c.filterTo;", "case 'inRange': return v >= c.filter && v <= c.filterTo;") },
  { id: 'M4', what: 'text matched by case', catches: ['P1'], mutate: swap('String(cell).toLowerCase(), String(c.filter).toLowerCase()', 'String(cell), String(c.filter)') },
  { id: 'M5', what: 'a set\'s null not the blank cells', catches: ['P1'], mutate: swap('if (isBlankCell(cell)) return values.includes(null);', 'if (isBlankCell(cell)) return false;') },
  { id: 'M6', what: 'two conditions typeable in the floating cell', catches: ['F1'],
    mutate: swap("if (model.filterType === 'set' || model.operator) return false;", "if (model.filterType === 'set') return false;") },
  { id: 'M7', what: 'a pasted list not made unique', catches: ['L1'], mutate: swap('if (seen.has(word)) { duplicates += 1; continue; }', '') },
  { id: 'M8', what: 'a search drops the picks', catches: ['V02'], mutate: swap('  searched() {\n', '  searched() {\n    this.picked.clear();\n') },
  { id: 'M9', what: 'Apply with nothing picked', catches: ['V01'], mutate: swap("if (this.tab === 'pick') this.applyButton.disabled = !this.picked.size;", '') },
  { id: 'M10', what: 'a late answer drawn over a newer one', catches: ['V10'], mutate: swap('    if (read !== this.reads) return;\n', '') },
  { id: 'M11', what: 'a list past the cap searched here', catches: ['V11'], mutate: swap('if (!this.list || this.list.whole) { this.drawPick(); return; }', 'this.drawPick(); return;') },
  { id: 'M12', what: 'a refusal not said', catches: ['V12'], mutate: swap("if (list && list.refused) rows.push(this.el('div', 'refusal', list.refused));", '') },
  { id: 'M13', what: 'the floating cell sends every key at once', catches: ['V15'],
    mutate: swap('this.timer = setTimeout(() => this.typed(), FLOAT_DEBOUNCE_MS);', 'this.typed();') },
  { id: 'M14', what: 'the two filters\' AND/OR in one group', catches: ['V13'], mutate: swap("this.join = this.el('form', 'value-filter__join');", "this.join = this.el('div', 'value-filter__join');") },
  { id: 'M15', what: 'reopened on a condition, the Pick tab', catches: ['V07'], mutate: swap("this.show(m && m.filterType !== 'set' ? 'condition' : 'pick');", "this.show('pick');") },
];
console.log('');
const { wrong } = await scoreMutants(MUTANTS, async (mu) => suite((await loadWithProbe(SUBJECT, { mutate: mu.mutate })).module),
  { baselineRan: base.ran, baselineNames: base.names, title: '-- defect mutants (each must be CAUGHT by its named line) -----------' });
const failed = base.failures.length + wrong;
console.log(`\n${base.ran - base.failures.length} passed, ${base.failures.length} failed; ${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
