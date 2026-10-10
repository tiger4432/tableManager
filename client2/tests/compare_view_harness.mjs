// Compare (lead 10-09, demo ③): the start marking's signs side by side.
//
// Scores: the three picks come from the declaration; the walks one comparison asks (rows from every start, one per
// sign along the picked edge, the page's form kept); the table read from the answers (several edges folded with
// whose, «missing» where a sign reached no edge, the subject end when the type is only the edge's subject); the part
// on the walk page (its view, its asks, a world picked asks again, an answer from the old worlds not shown); and two
// parts on one screen that do not touch each other. It imports its subjects; the page is the board's stub document.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { makeDoc, flush, walk as walkAll } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { MarkingStore, SIGN } from '../src/rnd_board/marking_store.js';
import { entitySeedId, createWalkBoxWalk } from '../src/rnd_board/api.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const settle = async () => { for (let i = 0; i < 20; i += 1) await flush(); };
const DECL = { ...JSON.parse(readFileSync(join(HERE, 'fixtures', 'walk_start_declaration.json'), 'utf8')),
  worlds: ['default', 'w1'], operating: 'default' };

// Three wafers and three recipes. What each wafer's edges say: two processed_with from C, and from B one edge of
// another predicate carrying the same qualifier name, which must not count.
const W = (k) => entitySeedId('wafer', { wafer: k });
const R = (k) => `recipe-${k}`;
const SAID = {
  A: [['R1', 'processed_with', { step: 'CMP' }], ['R3', 'processed_with', {}]],
  B: [['R1', 'processed_with', { step: 'CMP' }], ['R2', 'register', { step: '99' }]],
  C: [['R1', 'processed_with', { step: 'ETCH' }], ['R2', 'processed_with', { step: '12' }]],
};
/** The server's answer to a walk URL: the starts' wafers and the recipes, as collected; the starts' edges. */
function answer(url) {
  const q = new URLSearchParams(String(url).split('?')[1] || '');
  const collect = q.getAll('collect');
  const ids = [...q.getAll('positive'), ...q.getAll('negative'), ...q.getAll('id')];
  const wafers = Object.keys(SAID).filter((k) => ids.includes(W(k)));
  const nodes = [
    ...(collect.includes('wafer') ? wafers.map((k) => ({ id: W(k), type: 'wafer', label: k })) : []),
    ...(collect.includes('recipe') ? ['R1', 'R2', 'R3'].map((k) => ({ id: R(k), type: 'recipe', label: k })) : []),
  ];
  const edges = wafers.flatMap((k) => SAID[k].map(([to, predicate, qualifiers], i) =>
    ({ id: `${k}-${i}`, source: W(k), target: R(to), predicate, qualifiers })));
  return { state: 'ok', seed: { id: ids[0] || 's' }, nodes, edges };
}
const respond = (urls) => async (url) => {
  urls.push(String(url));
  return { ok: true, status: 200, json: async () => (String(url).includes('/declaration') ? DECL : answer(url)) };
};
const query = (u) => {
  const q = new URLSearchParams(String(u).split('?')[1] || '');
  const out = {};
  for (const name of ['positive', 'negative', 'follow', 'collect', 'world']) if (q.getAll(name).length) out[name] = q.getAll(name);
  for (const name of ['direction', 'hops']) if (q.get(name)) out[name] = q.get(name);
  return out;
};
const sorted = (v) => (Array.isArray(v) ? v.map(sorted) : v && typeof v === 'object'
  ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sorted(v[k])])) : v);
const ascii = (t) => String(t).replace(/[^\x00-\x7f]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
const hasClass = (n, cls) => String(n.className || '').split(/\s+/).includes(cls);
const tableOf = (root) => walkAll(root).filter((n) => n.tagName === 'TR')
  .map((tr) => tr.children.map((c) => (hasClass(c, 'cmp-missing') ? `[${c._text}]` : c._text)));
const textOf = (root) => walkAll(root).map((n) => n._text || '').filter((t) => t).join('|');

async function seen(M) {
  const C = M.compare;
  const out = {};
  const PICKS = { type: 'recipe', edge: 'processed_with', value: 'step' };
  // ── the declaration's choices ──
  out.choices = [C.compareChoices(DECL, {}), C.compareChoices(DECL, { type: 'recipe' }),
    C.compareChoices(DECL, { type: 'quantity', edge: 'measures' })];
  // ── the walks one comparison asks ──
  const starts = { positive: ['a', 'c'], negative: ['b'] };
  out.requests = C.compareRequests({ type: 'wafer', keys: { wafer: 'A' }, follow: ['register'], collect: ['lot'],
    direction: 'out', hops: 3 }, starts, PICKS, DECL);
  out.unfollowed = C.compareRequests({ type: 'wafer', keys: { wafer: 'A' } }, { positive: ['a'], negative: [] }, PICKS, DECL);
  // ── the table from the answers ──
  const urlOf = (ids, collect) => `/x?${[...ids.map((id) => `positive=${encodeURIComponent(id)}`),
    ...collect.map((t) => `collect=${t}`)].join('&')}`;
  const rowsAnswer = answer(urlOf([W('A'), W('C'), W('B')], ['recipe']));
  const signs = [{ sign: '+', labels: ['A', 'C'], answer: answer(urlOf([W('A'), W('C')], ['recipe', 'wafer'])) },
    { sign: '−', labels: ['B'], answer: answer(urlOf([W('B')], ['recipe', 'wafer'])) }];
  out.view = C.compareView(rowsAnswer, signs, PICKS, DECL, ['register']);
  out.including = C.compareView(rowsAnswer, signs, PICKS, DECL, ['register', 'processed_with']).heading;
  out.everything = C.compareView(rowsAnswer, signs, PICKS, DECL, []).heading;
  // The type only the edge's subject: the value sits at the subject end, whose is the object.
  const waferRows = answer(urlOf([W('A'), W('C')], ['wafer']));
  out.flipped = C.compareView(waferRows, [{ sign: '+', labels: ['A', 'C'], answer: signs[0].answer }],
    { type: 'wafer', edge: 'processed_with', value: 'step' }, DECL, []).rows.map((r) => [r.label, r.cells.map((c) => c.text)]);

  // ── two parts on one screen ──
  {
    const doc = makeDoc('light');
    const urls = [];
    const walk = createWalkBoxWalk({ apiBase: '', fetchImpl: respond(urls) });
    const markings = new MarkingStore();
    markings.replace('walk-start', [[W('A'), SIGN.CASE], [W('B'), SIGN.CONTROL]]);
    const mounts = [doc.createElement('div'), doc.createElement('div')];
    for (const m of mounts) doc.body.appendChild(m);
    const deps = { doc, walk, markings, startsName: 'walk-start', spec: () => ({}), declaration: () => DECL,
      labelOf: (id) => ({ [W('A')]: 'A', [W('B')]: 'B' }[id] || id) };
    const parts = mounts.map((m) => new C.CompareView(m, deps));
    const pick = (i, key, value) => {
      const s = walkAll(mounts[i]).find((n) => n.attrs && n.attrs['data-pick'] === key);
      s.value = value;
      s.dispatch('change', {});
    };
    const secondBefore = [textOf(mounts[1]), JSON.stringify(parts[1].picks)];
    pick(0, 'type', 'recipe'); pick(0, 'edge', 'processed_with'); pick(0, 'value', 'step');
    walkAll(mounts[0]).find((n) => hasClass(n, 'cmp-go')).dispatch('click', {});
    await settle();
    out.two = { first: tableOf(mounts[0]), asked: urls.length,
      second: [textOf(mounts[1]), JSON.stringify(parts[1].picks)], secondBefore,
      own: mounts.map((m) => m.children.length) };
    const firstAfter = textOf(mounts[0]);
    pick(1, 'type', 'wafer');
    out.two.firstKept = textOf(mounts[0]) === firstAfter;
  }

  // ── an answer that comes after the comparison was forgotten is not drawn ──
  {
    const doc = makeDoc('light');
    const pending = [];
    const walk = (spec) => new Promise((resolve) => pending.push(() => resolve({ ok: true, ...answer(urlOf(spec.positive, spec.collect)) })));
    const markings = new MarkingStore();
    markings.replace('walk-start', [[W('A'), SIGN.CASE]]);
    const mount = doc.createElement('div');
    const part = new C.CompareView(mount, { doc, walk, markings, startsName: 'walk-start', spec: () => ({}), declaration: () => DECL });
    part.picks = { ...PICKS };
    const asking = part.ask();
    part.forget();
    for (const go of pending) go();
    await asking;
    await settle();
    out.stale = { state: part.state, rows: tableOf(mount).length };
  }

  // ── the part on the walk page ──
  {
    const urls = [];
    const doc = makeDoc('light');
    doc.head = doc.createElement('head');
    const host = doc.createElement('div');
    const branch = doc.createElement('div');
    const wpage = M.page.boot(doc, host, { apiBase: '', fetchImpl: respond(urls), world: ['default'], branchMount: branch,
      pickWorld: () => {} });
    await settle();
    out.views = walkAll(host).filter((n) => n.attrs && n.attrs['data-view']).map((n) => n._text);
    // Each start goes in its basket, then Walk (lead bc63378e5: Walk walks the baskets).
    const walkAs = async (k, sign = 1) => { wpage.state.type = 'wafer'; wpage.state.keys = { wafer: k }; wpage.baskets.add(sign); await wpage.fire(); await settle(); };
    const view = async (name) => { walkAll(host).find((n) => n.attrs && n.attrs['data-view'] === name).dispatch('click', {}); await settle(); };
    const goOf = () => walkAll(host).find((n) => hasClass(n, 'cmp-go'));
    const pick = (key, value) => {
      const s = walkAll(host).find((n) => n.attrs && n.attrs['data-pick'] === key);
      s.value = value;
      s.dispatch('change', {});
    };
    await view('compare');
    out.typeOptions = walkAll(walkAll(host).find((n) => n.attrs && n.attrs['data-pick'] === 'type'))
      .filter((n) => n.tagName === 'OPTION').length;
    out.reasons = [goOf().attrs.title];
    pick('type', 'recipe'); pick('edge', 'processed_with'); pick('value', 'step');
    out.reasons.push(goOf().attrs.title);
    await walkAs('A');
    await walkAs('B', -1);
    await walkAs('C', 1);
    out.reasons.push(goOf().disabled);
    let before = urls.length;
    goOf().dispatch('click', {});
    await settle();
    out.page = { asked: urls.slice(before).map(query), table: tableOf(host) };
    // A world picked in the compare view asks the comparison again on the new worlds.
    before = urls.length;
    const chip = walkAll(branch).find((n) => hasClass(n, 'branch-picker__chip') && n._text === 'w1');
    chip.dispatch('click', {});
    await settle();
    out.world = { asked: urls.slice(before).filter((u) => u.includes('/subgraph')).map(query), table: tableOf(host) };
    // A world picked in another view: the comparison's answer from the old worlds is not drawn when it comes back.
    await view('table');
    before = urls.length;
    walkAll(branch).find((n) => hasClass(n, 'branch-picker__chip') && /^\d+ · w1$/.test(n._text)).dispatch('click', {});
    await settle();
    const elsewhere = urls.slice(before).filter((u) => u.includes('/subgraph')).map(query);
    await view('compare');
    out.away = { compareAsked: elsewhere.filter((q) => (q.collect || []).includes('recipe')).length,
      table: tableOf(host).length, note: textOf(host).includes('Nothing compared yet') };
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
  eq('P1 the picks come from the declaration: its types; the edges touching the type; the edge\'s values',
    [out.choices[0].types, out.choices[0].edges, out.choices[1].edges, out.choices[2].values],
    [DECL.entities.map((e) => e.type), [], ['processed_with'], ['value', 'value_text', 'role', 'step', 'eqp_id']]);
  eq('P2 the rows walk: the form kept, every start (+ and -) as positive, the row type collected',
    sorted(out.requests.rows), sorted({ follow: ['register'], direction: 'out', hops: 3, positive: ['a', 'c', 'b'], collect: ['recipe'] }));
  eq('P3 one walk per sign: its starts, the picked edge added to the chosen follow, the type and the edge\'s other end collected',
    sorted(out.requests.signs), sorted([
      { sign: '+', ids: ['a', 'c'], spec: { follow: ['register', 'processed_with'], direction: 'out', hops: 3, positive: ['a', 'c'], collect: ['recipe', 'wafer'] } },
      { sign: '−', ids: ['b'], spec: { follow: ['register', 'processed_with'], direction: 'out', hops: 3, positive: ['b'], collect: ['recipe', 'wafer'] } }]));
  eq('P4 no follow chosen: no follow asked (every predicate); a sign with no start asks nothing',
    sorted([out.unfollowed.rows, out.unfollowed.signs]),
    sorted([{ positive: ['a'], collect: ['recipe'] }, [{ sign: '+', ids: ['a'], spec: { positive: ['a'], collect: ['recipe', 'wafer'] } }]]));
  eq('P5 the cells: one edge its value, several folded with whose, an edge of another predicate not read, an edge without the value absent, none "missing"',
    [out.view.columns, out.view.rows.map((r) => [r.label, r.cells.map((c) => (c.missing ? `[${c.text}]` : c.text))]),
      out.view.rows[1].cells[0].numeric],
    [['+ A · C', '− B'], [['R1', ['2 edges · CMP (A) · ETCH (C)', 'CMP']], ['R2', ['12', '[missing]']],
      ['R3', ['—', '[missing]']]], true]);
  eq('P6 the heading: the rows\' type and the follow that reached them; "rows include" the edge when the follow has it',
    [out.view.heading, out.including, out.everything],
    ['Rows: recipe reached by register', 'Rows: recipe reached by register · processed_with · rows include processed_with',
      'Rows: recipe reached by every predicate']);
  eq('P7 what "missing" says, under a sign with a missing cell only', out.view.missing,
    ['− missing: no processed_with edge from what − reached']);
  eq('P8 the type only the edge\'s subject: the value at the subject end, whose the object', out.flipped,
    [['A', ['CMP']], ['C', ['2 edges · ETCH (R1) · 12 (R2)']]]);
  eq('I1 two parts on one screen: one compares in its own div, the other\'s picks and drawing do not move',
    [out.two.first.length > 1, out.two.asked, out.two.second, out.two.own, out.two.firstKept],
    [true, 3, out.two.secondBefore, [1, 1], true]);
  eq('S1 an answer that comes after the comparison was forgotten is not drawn', out.stale, { state: 'idle', rows: 0 });
  eq('G1 the walk page\'s views: Table, Graph, Compare; the comparison\'s types are the declaration\'s, read after it came',
    [out.views, out.typeOptions], [['Table', 'Graph', 'Compare'], DECL.entities.length + 1]);
  eq('G2 the Compare button says what stops it: the picks, then a start; with both it is pressable',
    out.reasons, ['Pick a type, an edge and a value', 'Add a start to a basket first', false]);
  const A = W('A'), B = W('B'), Cw = W('C');
  const TABLE = [['recipe', '+ A · C', '− B'], ['R1', '2 edges · CMP (A) · ETCH (C)', 'CMP'], ['R2', '12', '[missing]'],
    ['R3', '—', '[missing]']];
  eq('G3 on the page: pressed, the rows walk and one walk per sign from the page\'s signed starts; the table drawn',
    [sorted(out.page.asked), out.page.table],
    [sorted([{ positive: [A, Cw, B], collect: ['recipe'], world: ['default'] },
      { positive: [A, Cw], collect: ['recipe', 'wafer'], world: ['default'] },
      { positive: [B], collect: ['recipe', 'wafer'], world: ['default'] }]), TABLE]);
  eq('G4 a world picked in the compare view asks the comparison again on the new worlds and draws it',
    [sorted(out.world.asked.filter((q) => (q.collect || [])[0] === 'recipe')), out.world.table],
    [sorted([{ positive: [A, Cw, B], collect: ['recipe'], world: ['default', 'w1'] },
      { positive: [A, Cw], collect: ['recipe', 'wafer'], world: ['default', 'w1'] },
      { positive: [B], collect: ['recipe', 'wafer'], world: ['default', 'w1'] }]), TABLE]);
  eq('G5 a world picked in another view: the old comparison is not drawn, nothing compared until asked',
    out.away, { compareAsked: 0, table: 0, note: true });
  return { ran: names.length, names, failures };
}

const REAL = {
  compare: await import('../src/walk/compare_view.js'),
  page: await import('../src/walk/main.js'),
};
console.log('\n[1] compare');
const base = suite(await seen(REAL));
let ran = base.ran;
let failed = base.failures.length;
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  { id: 'K1', what: 'the rows walk from the + starts only', catches: 'P2', file: 'walk/compare_view.js', key: 'compare',
    mutate: (t) => swap(t, 'positive: [...starts.positive, ...starts.negative], collect: [picks.type]', 'positive: [...starts.positive], collect: [picks.type]') },
  { id: 'K2', what: 'a sign walks the chosen follow without the edge', catches: 'P3', file: 'walk/compare_view.js', key: 'compare',
    mutate: (t) => swap(t, 'follow: [...new Set([...form.follow, picks.edge])]', 'follow: [...form.follow]') },
  { id: 'K3', what: 'a row the sign reached no edge into reads empty', catches: 'P5', file: 'walk/compare_view.js', key: 'compare',
    mutate: (t) => swap(t, '        if (!c.reached.has(n.id)) return { text: COMPARE_WORDS.missing, missing: true };\n', '') },
  { id: 'K4', what: 'an edge of any predicate read', catches: 'P5', file: 'walk/compare_view.js', key: 'compare',
    mutate: (t) => swap(t, '.filter((e) => e.predicate === picks.edge)', '') },
  { id: 'K5', what: 'the heading never says the rows include the edge', catches: 'P6', file: 'walk/compare_view.js', key: 'compare',
    mutate: (t) => swap(t, '(followed.includes(picks.edge) ?', '(false ?') },
  { id: 'K6', what: 'the subject end never read', catches: 'P8', file: 'walk/compare_view.js', key: 'compare',
    mutate: (t) => swap(t, 'const flip = !(', 'const flip = false && !(') },
  { id: 'K7', what: 'the picks shared by every part', catches: 'I1', file: 'walk/compare_view.js', key: 'compare',
    mutate: (t) => swap(t, "this.picks = { type: '', edge: '', value: '' };",
      "this.picks = (globalThis.__cmpPicks = globalThis.__cmpPicks || { type: '', edge: '', value: '' });") },
  { id: 'K8', what: 'a forgotten answer drawn', catches: 'S1', file: 'walk/compare_view.js', key: 'compare',
    mutate: (t) => swap(t, '    if (asked !== this.asks) return;\n', '') },
  { id: 'K9', what: 'a world picked in the compare view does not ask again', catches: 'G4', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, "    if (state.view === 'compare') { await compare.ask(); return; }\n", '') },
  { id: 'K10', what: 'a world picked elsewhere leaves the old comparison drawn', catches: 'G5', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, '    compare.forget();\n', '') },
  { id: 'K11', what: 'the page seats the comparison without drawing it on the declaration it read', catches: 'G1', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, '{ compare.render(); main.append(compareMount); }', 'main.append(compareMount);') },
  { id: 'K14', what: 'what missing says drawn under every sign', catches: 'P7', file: 'walk/compare_view.js', key: 'compare',
    mutate: (t) => swap(t, 'read.filter((c) => rows.some((n) => !c.reached.has(n.id)))', 'read') },
  { id: 'K12', what: 'an edge without the value drawn empty', catches: 'P5', file: 'walk/compare_view.js', key: 'compare',
    mutate: (t) => swap(t, '[picks.value]) || ABSENT;', '[picks.value]);') },
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
