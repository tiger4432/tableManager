// Start baskets (owner 10-10, lead bc63378e5): the walk's start marking edited as Positive and Negative.
//
// Scores: + puts the picked node in its basket with that sign, × takes it out, + on the other basket moves it (one sign
// a node), nothing picked leaves + off with its reason, the baskets say the marking whoever writes it, two parts on one
// screen do not touch each other; on the walk page Walk asks the baskets as they are, an empty Positive keeps Walk off
// with its reason and asks nothing, and Ctrl or Shift on Walk writes no mark. It imports its subjects; the page is the
// board's stub document.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { makeDoc, flush, walk as walkAll } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { MarkingStore, SIGN } from '../src/rnd_board/marking_store.js';
import { entitySeedId } from '../src/rnd_board/api.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const settle = async () => { for (let i = 0; i < 20; i += 1) await flush(); };
const ascii = (t) => String(t).replace(/[^\x00-\x7f]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
const hasClass = (n, cls) => String(n.className || '').split(/\s+/).includes(cls);
const DECL = { ...JSON.parse(readFileSync(join(HERE, 'fixtures', 'walk_start_declaration.json'), 'utf8')) };
const W = (k) => entitySeedId('wafer', { wafer: k });
const node = (k) => ({ id: W(k), label: k, type: 'wafer', keys: { wafer: k } });

/** What a basket part shows: per sign, its count and its rows' labels. */
const shownOf = (root) => ['+', '−'].map((sign) => {
  const box = walkAll(root).find((n) => n.attrs && n.attrs['data-sign'] === sign && hasClass(n, 'wk-basket'));
  if (!box) return null;
  return [walkAll(box).filter((n) => hasClass(n, 'wk-basketcount')).map((n) => n._text).join(),
    walkAll(box).filter((n) => hasClass(n, 'wk-basketlabel')).map((n) => n._text)];
});
const addOf = (root, sign) => walkAll(walkAll(root).find((n) => n.attrs && n.attrs['data-sign'] === sign && hasClass(n, 'wk-basket')) || { children: [] })
  .find((n) => hasClass(n, 'wk-basketadd'));
const removeOf = (root, label) => {
  const row = walkAll(root).find((n) => hasClass(n, 'wk-basketrow') && walkAll(n).some((c) => hasClass(c, 'wk-basketlabel') && c._text === label));
  return row && walkAll(row).find((n) => hasClass(n, 'wk-basketremove'));
};
// A control a mutant left undrawn is not pressed; the cell that reads after it says what is missing.
// As a browser does: a disabled button takes no click.
const press = (n, event = {}) => { if (n && !n.disabled) n.dispatch('click', event); };

async function seen(M) {
  const out = {};
  // ── the part ──
  {
    const doc = makeDoc('light');
    const markings = new MarkingStore();
    let picked = null;
    const mount = doc.createElement('div');
    doc.body.appendChild(mount);
    const part = new M.baskets.StartBaskets(mount, { doc, markings, name: 'start', picked: () => picked });
    // The page redraws the part when the pick changes; so does this.
    const pick = (key) => { picked = node(key); part.render(); };
    out.empty = { shown: shownOf(mount), add: addOf(mount, '+') && [addOf(mount, '+').disabled, addOf(mount, '+').attrs.title] };
    pick('A');
    press(addOf(mount, '+'));
    pick('B');
    press(addOf(mount, '+'));
    out.added = { shown: shownOf(mount), marks: markings.entries('start') };
    pick('A');
    press(addOf(mount, '−'));
    out.moved = { shown: shownOf(mount), marks: markings.entries('start') };
    press(removeOf(mount, 'B'));
    out.removed = { shown: shownOf(mount), marks: markings.entries('start') };
    markings.set('start', W('C'), SIGN.CASE);
    out.other = shownOf(mount);
  }
  // ── two parts on one screen ──
  {
    const doc = makeDoc('light');
    const markings = new MarkingStore();
    const mounts = [doc.createElement('div'), doc.createElement('div')];
    for (const m of mounts) doc.body.appendChild(m);
    new M.baskets.StartBaskets(mounts[0], { doc, markings, name: 'one', picked: () => node('A') });
    new M.baskets.StartBaskets(mounts[1], { doc, markings, name: 'two', picked: () => node('B') });
    const before = JSON.stringify(shownOf(mounts[1]));
    press(addOf(mounts[0], '+'));
    out.two = { first: shownOf(mounts[0]), second: JSON.stringify(shownOf(mounts[1])), before, marks: markings.entries('two'),
      own: mounts.map((m) => m.children.length) };
  }
  // ── the walk page ──
  {
    const urls = [];
    const doc = makeDoc('light');
    doc.head = doc.createElement('head');
    const host = doc.createElement('div');
    const page = M.page.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
      urls.push(String(url));
      return { ok: true, status: 200, json: async () => (String(url).includes('/declaration') ? DECL
        : { state: 'ok', seed: { id: 's' }, nodes: [], edges: [] }) };
    } });
    await settle();
    const go = () => walkAll(host).find((n) => hasClass(n, 'wk-go'));
    const walks = () => urls.filter((u) => u.includes('/subgraph'));
    const q = (u) => new URLSearchParams(String(u || '').split('?')[1] || '');
    page.state.type = 'wafer';
    page.state.keys = { wafer: 'A' };
    page.render();
    out.off = [go().disabled, go().attrs.title];
    go().dispatch('click', {});
    await settle();
    out.offAsked = walks().length;
    // A + and C -, and the form left on B: Walk asks the baskets, not the form.
    press(addOf(host, '+'));
    page.state.keys = { wafer: 'C' };
    page.render();
    press(addOf(host, '−'));
    page.state.keys = { wafer: 'B' };
    page.render();
    const before = walks().length;
    go().dispatch('click', {});
    await settle();
    const signed = q(walks()[before]);
    out.signed = [walks().length - before, signed.getAll('positive'), signed.getAll('negative')];
    // C out: one + alone, asked by its type and keys as the form asked it - A, not the form's B.
    press(removeOf(host, 'C'));
    const at = walks().length;
    go().dispatch('click', {});
    await settle();
    const one = q(walks()[at]);
    out.one = [walks().length - at, one.get('id'), one.getAll('positive').length];
    // Ctrl and Shift on Walk: no mark written, the baskets as they were.
    const marks = JSON.stringify(page.graph.markings.entries('walk-start'));
    go().dispatch('click', { ctrlKey: true, shiftKey: true });
    await settle();
    out.keys = JSON.stringify(page.graph.markings.entries('walk-start')) === marks;
  }
  // ── a key typed, not picked from the list (lead 10-10: + stayed off) ──
  {
    const urls = [];
    const doc = makeDoc('light');
    doc.head = doc.createElement('head');
    const host = doc.createElement('div');
    const page = M.page.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
      urls.push(String(url));
      return { ok: true, status: 200, json: async () => (String(url).includes('/declaration') ? DECL
        : { state: 'ok', seed: { id: 's' }, nodes: [], edges: [] }) };
    } });
    await settle();
    page.state.type = 'wafer';
    page.render();
    const keyInput = walkAll(host).find((n) => n.tagName === 'INPUT' && hasClass(n, 'wk-input')
      && n.parentNode && walkAll(n.parentNode).some((c) => hasClass(c, 'wk-keyname') && c._text === 'wafer'));
    const offBefore = addOf(host, '+') ? addOf(host, '+').disabled : null;
    if (keyInput) { keyInput.value = 'TYPED-1'; keyInput.dispatch('input', {}); }
    const onAfter = addOf(host, '+') ? addOf(host, '+').disabled : null;
    const go = () => walkAll(host).find((n) => hasClass(n, 'wk-go'));
    const goOffBefore = go().disabled;
    press(addOf(host, '+'));
    const goOffAfter = go().disabled;
    const at = urls.filter((u) => u.includes('/subgraph')).length;
    press(go());
    await settle();
    const asked = urls.filter((u) => u.includes('/subgraph')).slice(at);
    out.typed = [Boolean(keyInput), offBefore, onAfter, shownOf(host)[0], goOffBefore, goOffAfter,
      asked.length, new URLSearchParams(String(asked[0] || '').split('?')[1] || '').get('id')];
    // x on the only + start, no page redraw after the one that drew Walk on: Walk goes off with its reason.
    page.render();
    const goOnDrawn = !go().disabled;
    press(removeOf(host, 'TYPED-1'));
    out.goOffAgain = [goOnDrawn, shownOf(host)[0], go().disabled, go().attrs.title];
  }
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
  eq('B1 nothing picked: both baskets empty, + off with its reason', [out.empty.shown, out.empty.add],
    [[['0', []], ['0', []]], [true, 'Pick a node first']]);
  eq('B2 + puts the picked node in its basket as its sign, named as it was picked', [out.added.shown, out.added.marks],
    [[['2', ['A', 'B']], ['0', []]], [[W('A'), SIGN.CASE], [W('B'), SIGN.CASE]]]);
  eq('B3 + on the other basket moves the node: one sign a node', [out.moved.shown, out.moved.marks],
    [[['1', ['B']], ['1', ['A']]], [[W('A'), SIGN.CONTROL], [W('B'), SIGN.CASE]]]);
  eq('B4 x takes a node out of its basket and the marking', [out.removed.shown, out.removed.marks],
    [[['0', []], ['1', ['A']]], [[W('A'), SIGN.CONTROL]]]);
  eq('B5 the baskets say the marking whoever writes it', out.other, [['1', [W('C')]], ['1', ['A']]]);
  eq('B6 two parts on one screen: one takes a node, the other and its marking do not move',
    [out.two.first, out.two.second === out.two.before, out.two.marks, out.two.own], [[['1', ['A']], ['0', []]], true, [], [1, 1]]);
  eq('B7 the page: an empty Positive keeps Walk off with its reason, and a press asks nothing',
    [out.off, out.offAsked], [[true, 'Add a start to Positive first'], 0]);
  eq('B8 Walk asks the baskets as they are - + as positive, - as negative - not the node the form holds',
    out.signed, [1, [W('A')], [W('C')]]);
  eq('B9 one + start alone is asked by its type and keys, as before: the basket\'s node, not the form\'s',
    out.one, [1, W('A'), 0]);
  eq('B10 Ctrl and Shift on Walk write no mark', out.keys, true);
  eq('B11 a key typed, not picked from the list: + comes on, puts it in, and Walk asks that key',
    out.typed, [true, true, false, ['1', ['TYPED-1']], true, false, 1, W('TYPED-1')]);
  eq('B12 x on the only + start, no page redraw: Walk goes off with its reason',
    out.goOffAgain, [true, ['0', []], true, 'Add a start to Positive first']);
  return { ran: names.length, names, failures };
}

const REAL = {
  baskets: await import('../src/walk/start_baskets.js'),
  page: await import('../src/walk/main.js'),
};
console.log('\n[1] start baskets');
const base = suite(await seen(REAL));
let ran = base.ran;
let failed = base.failures.length;
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  { id: 'BM1', what: '+ on any basket puts the node as +', catches: 'B3', file: 'walk/start_baskets.js', key: 'baskets',
    mutate: (t) => swap(t, '    this.markings.set(this.name, node.id, sign);', '    this.markings.set(this.name, node.id, SIGN.CASE);') },
  { id: 'BM2', what: 'x takes nothing out', catches: 'B4', file: 'walk/start_baskets.js', key: 'baskets',
    mutate: (t) => swap(t, '  remove(id) { this.markings.set(this.name, id, SIGN.ABSENT); }', '  remove(id) { return id; }') },
  { id: 'BM3', what: '+ on with nothing picked', catches: 'B1 ', file: 'walk/start_baskets.js', key: 'baskets',
    mutate: (t) => swap(t, "setDisabledReason(add, node ? '' : BASKET_WORDS.noPick);", "setDisabledReason(add, '');") },
  { id: 'BM4', what: 'the baskets do not hear the marking', catches: 'B5', file: 'walk/start_baskets.js', key: 'baskets',
    mutate: (t) => swap(t, '    this.unsubscribe = this.markings.subscribe(this.name, () => this.render());\n', '') },
  { id: 'BM5', what: 'every part writes one marking', catches: 'B6', file: 'walk/start_baskets.js', key: 'baskets',
    mutate: (t) => swap(t, '    this.name = deps.name;', "    this.name = 'start';") },
  { id: 'BM6', what: 'Walk on with an empty Positive', catches: 'B7', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, "(seedsOf(markings.entries(GRAPH_CHAIN[0])).positive.length ? '' : BASKET_WORDS.noStart)", "''") },
  { id: 'BM7', what: 'Walk asks the form\'s node, not the baskets', catches: 'B9', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, '    const one = signed ? null : baskets.describe(starts.positive[0]);', '    const one = null;') },
  { id: 'BM8', what: 'Shift on Walk marks the form\'s node a control again', catches: 'B10', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, "    go.addEventListener('click', () => { void fire(); });",
      "    go.addEventListener('click', (event) => { if (event && event.shiftKey) markings.set(GRAPH_CHAIN[0], entitySeedId(state.type, state.keys), SIGN.CONTROL); void fire(); });") },
  { id: 'BM9', what: 'a typed key leaves the baskets as they were drawn', catches: 'B11', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, "input.addEventListener('input', () => { state.keys[k] = input.value; baskets.render(); });",
      "input.addEventListener('input', () => { state.keys[k] = input.value; });") },
  { id: 'BM10', what: 'Walk is drawn once and does not follow the baskets', catches: 'B12', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, "markings.subscribe(GRAPH_CHAIN[0], () => { if (goButton) setDisabledReason(goButton, goReason()); });", '') },
];
const scored = await scoreMutants(MUTANTS, async (m) => {
  const copy = (await loadWithProbe(join(SRC, m.file), { mutate: m.mutate })).module;
  return suite(await seen({ ...REAL, [m.key]: copy }));
}, { baselineRan: base.ran, baselineNames: base.names, title: '\n  [1] mutants - each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;
console.log(`\n${ran - failed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
