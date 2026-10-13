// The worlds a walk reads (lead 99032248f, owner 10-04 «세상은 독립, 겹침은 걸을 때 여럿 고르기»).
//
// Scores: the one seat (`world.js`) adds one `world=` per picked world in the order picked and nothing for
// none; the walk page's every request goes through it; its picker hands the page the whole new list on a
// press, the empty choice named after the operating world; and the graph's facts say which world an edge
// came from only when two or more are read. It imports its subjects; the page is the board's stub document.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { makeDoc, flush, walk as walkAll } from './lib/board_dom.mjs';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { SIGN } from '../src/rnd_board/marking_store.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const fx = (name) => JSON.parse(readFileSync(join(HERE, 'fixtures', name), 'utf8'));
const settle = async () => { for (let i = 0; i < 20; i += 1) await flush(); };

// The declaration answer as the server shapes it after 9e9a9015a: the worlds, the default first, and the
// operating one - here not the default.
const DECL = { entities: [{ type: 'wafer@1', keys: ['wafer'] }], predicates: [],
  worlds: ['default', 'w1'], operating: 'w1' };
const GRAPH_DECL = fx('walk_start_declaration.json');

async function seen(M) {
  const out = {};
  // ── the seat itself ──
  const sent = [];
  const rec = async (url) => { sent.push(String(url)); return {}; };
  for (const picked of [null, [], '  ', 'w1', ['w1', 'default'], ['w1', '', 'default']]) {
    await M.world.withWorld(rec, () => picked)('/api/ledger/subgraph?seed=x');
  }
  await M.world.withWorld(rec, () => ['w1'])('/api/ledger/declaration');
  out.seat = sent;
  out.address = [M.world.addressFor('http://box/walk.html?world=a&x=1', ['w1', 'default']),
    M.world.addressFor('http://box/walk.html?world=a&x=1', [])];
  // ── the walk page on a recording fetch ──
  const page = async (world) => {
    const urls = [];
    const picked = [];
    const doc = makeDoc('light');
    doc.head = doc.createElement('head');
    const host = doc.createElement('div');
    const mount = doc.createElement('div');
    const fetchImpl = async (url) => {
      urls.push(String(url));
      return { ok: true, status: 200, json: async () => (String(url).includes('/declaration') ? DECL
        : { state: 'ok', seed: { id: 's' }, nodes: [], edges: [] }) };
    };
    const wpage = M.page.boot(doc, host, { apiBase: '', fetchImpl, world, branchMount: mount,
      pickWorld: (names) => picked.push(names) });
    await settle();
    wpage.state.type = 'wafer@1';
    wpage.state.keys = { wafer: 'W1' };
    wpage.baskets.add(1);
    await wpage.fire();
    await settle();
    const chips = walkAll(mount).filter((n) => String(n.className || '').split(/\s+/).includes('branch-picker__chip'));
    // What the walk asked before any press: a press now walks again on the page (lead 10-09), counted in V9.
    const asked = urls.slice();
    for (const chip of chips) chip.dispatch('click', {});
    return { urls: asked, picked, chips: chips.map((c) => `${c._text}|${c.attrs['aria-pressed']}`) };
  };
  out.none = await page([]);
  out.two = await page(['w1', 'default']);
  // ── the graph's facts, on the page: a world chip only when two or more are read ──
  const facts = async (world) => {
    const body = JSON.parse(JSON.stringify(fx('walk_start_die.json')));
    // As the server answers (ec6874b28): an edge keeps its id and carries the worlds that say it, each with its
    // evidence - every other edge said by both.
    body.edges.forEach((edge, i) => {
      const said = (world) => ({ world, claim_id: `${edge.id}:${world}`, occurred_at: edge.occurred_at, source_who: edge.source_who });
      edge.by_world = i % 2 ? [said('w1'), said('default')] : [said('w1')];
      edge.worlds = edge.by_world.map((row) => row.world);
    });
    const doc = makeDoc('light');
    doc.head = doc.createElement('head');
    const host = doc.createElement('div');
    doc.body.appendChild(host);
    const fetchImpl = async (url) => ({ ok: true, status: 200,
      json: async () => (String(url).includes('/declaration') ? { ...DECL, entities: GRAPH_DECL.entities } : body) });
    const wpage = M.page.boot(doc, host, { apiBase: '', fetchImpl, world });
    await settle();
    wpage.state.view = 'graph';
    wpage.state.type = body._start.type;
    wpage.state.keys = { ...body._start.keys };
    wpage.render();
    wpage.baskets.add(1);
    await wpage.fire();
    await settle();
    const target = body.edges[0].target;
    // The picture is the graph part's Cytoscape (lead 5e1d9e372); a press on a node is a tap there.
    const node = wpage.graph && wpage.graph.cy ? wpage.graph.cy.getElementById(target) : null;
    if (node && node.nonempty()) node.emit('tap');
    const lines = walkAll(host).filter((n) => String(n.className || '') === 'sg-fact');
    const rows = walkAll(host).filter((n) => String(n.className || '') === 'sg-fact sg-fact--world');
    const chip = (n) => (n.children || []).find((c) => c.className === 'sg-world');
    return { lines: lines.length, tagged: rows.filter(chip).length,
      words: [...new Set(rows.filter(chip).map((n) => chip(n)._text))].sort(),
      evidence: rows.every((n) => (n.children || []).some((c) => c.className !== 'sg-world' && c._text)) };
  };
  out.many = await facts(['w1', 'default']);
  out.one = await facts(['w1']);
  // ── the graph's «Walk on from here», then Walk (lead 10-12 rehearsal: Walk sent the graph's own ask - fan-out 20, no
  //    hops, no node_limit): a node into the + basket and nothing else; Walk is the bar's ask, hops 1 as the bar has it ──
  {
    const urls = [];
    const body = JSON.parse(JSON.stringify(fx('walk_start_die.json')));
    const doc = makeDoc('light');
    doc.head = doc.createElement('head');
    const host = doc.createElement('div');
    doc.body.appendChild(host);
    const fetchImpl = async (url) => { urls.push(String(url)); return { ok: true, status: 200,
      json: async () => (String(url).includes('/declaration') ? { ...DECL, entities: GRAPH_DECL.entities } : body) }; };
    const wpage = M.page.boot(doc, host, { apiBase: '', fetchImpl });
    await settle();
    wpage.state.type = body._start.type;
    wpage.state.keys = { ...body._start.keys };
    wpage.state.hops = '1';
    wpage.state.direction = 'outgoing';
    wpage.render();
    wpage.baskets.add(1);
    await wpage.fire();
    await settle();
    const graphView = walkAll(host).find((n) => n.attrs && n.attrs['data-view'] === 'graph');
    if (graphView) graphView.dispatch('click', {});
    await settle();
    const far = body.nodes.find((n) => n.id === body.edges[0].target) || {};
    wpage.graph.walkOn({ id: far.id, label: far.label, type: far.type, keys: far.keys });
    const before = urls.length;
    await wpage.fire();
    await settle();
    const sent = urls.slice(before).filter((u) => u.includes('/subgraph')).map((u) => new URLSearchParams(u.split('?')[1] || ''));
    out.walkOn = { view: wpage.state.view, starts: wpage.graph.markings.entries('walk-start').length,
      sent: sent.map((q) => ({ hops: q.get('hops'), node_limit: q.get('node_limit'), fanout: q.has('fanout_limit'), positive: q.getAll('positive').length,
        direction: q.get('direction') })),
      limit: String(M.page.NODE_LIMIT) };
  }
  // ── Graph pressed before any Walk, and a Walk that fails on the Graph view (lead 10-12): the graph never walks its own
  //    ask - the press runs the bar's Walk and draws its answer; no start, or a failed walk, the table's line in its place ──
  const graphPage = async (answer) => {
    const urls = [];
    const body = JSON.parse(JSON.stringify(fx('walk_start_die.json')));
    const doc = makeDoc('light');
    doc.head = doc.createElement('head');
    const host = doc.createElement('div');
    doc.body.appendChild(host);
    const fetchImpl = async (url) => { urls.push(String(url)); return String(url).includes('/declaration')
      ? { ok: true, status: 200, json: async () => ({ ...DECL, entities: GRAPH_DECL.entities }) } : answer(body); };
    const wpage = M.page.boot(doc, host, { apiBase: '', fetchImpl });
    await settle();
    wpage.state.type = body._start.type;
    wpage.state.keys = { ...body._start.keys };
    wpage.state.hops = '1';
    wpage.render();
    const press = async (view) => {
      const b = walkAll(host).find((n) => n.attrs && n.attrs['data-view'] === view);
      if (b) b.dispatch('click', {});
      await settle();
    };
    const walks = () => urls.filter((u) => u.includes('/subgraph')).map((u) => new URLSearchParams(u.split('?')[1] || ''))
      .map((q) => ({ hops: q.get('hops'), node_limit: q.get('node_limit'), fanout: q.has('fanout_limit') }));
    // What the result pane says, the table's or the graph's - not the bar's.
    const said = (cls) => walkAll(host).filter((n) => String(n.className || '') === 'wk-result')
      .flatMap((box) => walkAll(box)).filter((n) => String(n.className || '') === cls).map((n) => n.textContent);
    return { wpage, press, walks, said, urls };
  };
  {
    const ok = await graphPage((body) => ({ ok: true, status: 200, json: async () => body }));
    await ok.press('graph');
    const none = { walks: ok.walks(), notes: ok.said('wk-note') };
    ok.wpage.baskets.add(1);
    await ok.press('table');
    await ok.press('graph');
    out.graphFirst = { none, walks: ok.walks(), drawn: ok.wpage.graph.state, limit: String(M.page.NODE_LIMIT) };
    // The picture's Continue from a node marked on it: its seeds as Continue seeds them, the bar's knobs beside (lead 10-12).
    const g = ok.wpage.graph;
    const marked = JSON.parse(JSON.stringify(fx('walk_start_die.json'))).edges[0].target;
    g.markings.set(g.writes(), marked, SIGN.CASE);
    const sentBefore = ok.urls.length;
    if (g.continueButton) g.continueButton.dispatch('click', {});
    await settle();
    const went = ok.urls.slice(sentBefore).filter((u) => u.includes('/subgraph')).map((u) => new URLSearchParams(u.split('?')[1] || ''));
    out.graphContinue = { walks: went.map((q) => ({ hops: q.get('hops'), node_limit: q.get('node_limit'), fanout: q.has('fanout_limit'),
      positive: q.getAll('positive') })), marked, limit: String(M.page.NODE_LIMIT) };
    const bad = await graphPage(() => ({ ok: false, status: 500, json: async () => ({ detail: 'the ledger said no' }) }));
    bad.wpage.baskets.add(1);
    await bad.press('graph');
    const onGraph = bad.said('wk-fail');
    const asked = bad.walks().length;
    await bad.press('table');
    const onTable = bad.said('wk-fail');
    await bad.press('graph');
    out.graphFailed = { onGraph, onTable, again: bad.said('wk-fail'), asked, after: bad.walks().length };
  }
  // ── a world picked on a walked page: walked again there, the same starts, no leaving (lead 10-09) ──
  {
    const urls = [];
    const picked = [];
    const doc = makeDoc('light');
    doc.head = doc.createElement('head');
    const host = doc.createElement('div');
    const mount = doc.createElement('div');
    const fetchImpl = async (url) => {
      urls.push(String(url));
      return { ok: true, status: 200, json: async () => (String(url).includes('/declaration') ? DECL
        : { state: 'ok', seed: { id: 's' }, nodes: [], edges: [] }) };
    };
    const wpage = M.page.boot(doc, host, { apiBase: '', fetchImpl, world: ['default'], branchMount: mount,
      pickWorld: (names) => picked.push(names) });
    await settle();
    wpage.state.type = 'wafer@1';
    wpage.state.keys = { wafer: 'W1' };
    wpage.baskets.add(1);
    await wpage.fire();
    await settle();
    const starts = JSON.stringify(wpage.graph.markings.entries('walk-start'));
    const before = urls.length;
    const chip = walkAll(mount).find((n) => String(n.className || '').split(/\s+/).includes('branch-picker__chip') && n._text === 'w1');
    if (chip) chip.dispatch('click', {});
    await settle();
    const after = urls.slice(before);
    const tail = (u) => (u.split('?')[1] || '').split('&').filter((p) => p.startsWith('world=')).join('&');
    out.switch = { picked, decl: after.filter((u) => u.includes('/declaration')).map(tail),
      walk: after.filter((u) => u.includes('/subgraph')).map(tail),
      same: JSON.stringify(wpage.graph.markings.entries('walk-start')) === starts && wpage.state.keys.wafer === 'W1' };
  }
  return out;
}

function suite(out) {
  const names = [];
  const failures = [];
  const eq = (name, got, want) => {
    names.push(name);
    const g = JSON.stringify(got), w = JSON.stringify(want);
    if (g === w) { console.log(`  PASS ${name}`); return; }
    failures.push(name);
    console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`);
  };
  const q = '/api/ledger/subgraph?seed=x';
  eq('V1 the seat: none (null, [], blank) sends no world; one name one; several one each in the order picked, blanks dropped',
    out.seat, [q, q, q, `${q}&world=w1`, `${q}&world=w1&world=default`, `${q}&world=w1&world=default`,
      '/api/ledger/declaration?world=w1']);
  eq('V2 the address names the picked worlds instead, in order, and keeps the rest; none names none',
    out.address, ['http://box/walk.html?x=1&world=w1&world=default', 'http://box/walk.html?x=1']);
  const carry = (urls, tail) => urls.length > 1 && urls.every((u) => (u.split('?')[1] || '').split('&')
    .filter((p) => p.startsWith('world=')).join('&') === tail);
  eq('V3 the walk page with no world: its requests (declaration, walk) carry none', [out.none.urls.length > 1,
    out.none.urls.filter((u) => u.includes('world=')).length, out.none.urls.some((u) => u.includes('/subgraph'))],
  [true, 0, true]);
  eq('V4 with two picked: every request carries both, in the order picked', [carry(out.two.urls, 'world=w1&world=default'),
    out.two.urls.some((u) => u.includes('/subgraph'))], [true, true]);
  eq('V5 the picker: the empty choice named after the operating world and pressed while none is; then the worlds',
    out.none.chips, ['Operating · w1|true', 'default|false', 'w1|false']);
  eq('V6 ...picked ones read their order; a press hands the page the whole new list',
    [out.two.chips, out.two.picked], [['Operating · w1|false', '2 · default|true', '1 · w1|true'],
      [[], ['w1'], ['default']]]);
  eq('V7 two or more read: under each edge line of the facts, a row per world that says it - its chip and its evidence',
    [out.many.lines > 0, out.many.tagged > 0, out.many.words, out.many.evidence], [true, true, ['default', 'w1'], true]);
  eq('V8 one world read: no world chip', [out.one.lines > 0, out.one.tagged], [true, 0]);
  eq('V9 a world picked on a walked page: the address is told the new list, the declaration and the walk are asked again on it, in order',
    [out.switch.picked, out.switch.decl.length > 0 && out.switch.decl.every((t) => t === 'world=default&world=w1'),
      out.switch.walk.length > 0 && out.switch.walk.every((t) => t === 'world=default&world=w1')],
    [[['default', 'w1']], true, true]);
  eq('X1 ...with the same form and the same signed starts', out.switch.same, true);
  eq('G2 Graph pressed before any Walk: no start, nothing asked and the table\'s «No walk yet»; a start, one walk - the bar\'s ask (hops 1, node_limit, no fan-out) - and its answer drawn (lead 10-12)',
    out.graphFirst, { none: { walks: [], notes: ['No walk yet'] },
      walks: [{ hops: '1', node_limit: out.graphFirst.limit, fanout: false }], drawn: 'done', limit: out.graphFirst.limit });
  eq('G4 the picture\'s Continue from a node marked on it: one walk from that node, the bar\'s knobs beside - hops 1, node_limit, no fan-out the bar has not (lead 10-12)',
    out.graphContinue, { walks: [{ hops: '1', node_limit: out.graphContinue.limit, fanout: false, positive: [out.graphContinue.marked] }],
      marked: out.graphContinue.marked, limit: out.graphContinue.limit });
  eq('G3 a Walk that fails on the Graph view: the graph pane says the table\'s fail line; Graph pressed again walks nothing (lead 10-12)',
    [out.graphFailed.onGraph.length === 1, out.graphFailed.onGraph, out.graphFailed.again, out.graphFailed.asked, out.graphFailed.after],
    [true, out.graphFailed.onTable, out.graphFailed.onTable, 1, 1]);
  eq('G1 the graph\'s «Walk on from here» then Walk: two + starts, one walk, the bar\'s ask - its direction, hops 1, node_limit, no fan-out the bar has not (lead 10-12)',
    out.walkOn, { view: 'graph', starts: 2, sent: [{ hops: '1', node_limit: out.walkOn.limit, fanout: false, positive: 2, direction: 'outgoing' }], limit: out.walkOn.limit });
  return { ran: names.length, names, failures };
}

const REAL = {
  world: await import('../src/world.js'),
  page: await import('../src/walk/main.js'),
};
console.log('\n[1] the worlds a walk reads');
const base = suite(await seen(REAL));
let ran = base.ran;
let failed = base.failures.length;
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  { id: 'W1', what: 'several worlds go in reverse order', catches: 'V1', file: 'world.js', key: 'world',
    mutate: (t) => swap(t, "const tail = worlds.map(", "const tail = worlds.slice().reverse().map(") },
  { id: 'W2', what: 'none sends an empty world', catches: 'V1', file: 'world.js', key: 'world',
    mutate: (t) => swap(t, '    if (!worlds.length) return fetchImpl(url, init);\n', '') },
  { id: 'W3', what: 'the walk goes round the seat', catches: 'V4', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, '  const walk = createWalkBoxWalk({ apiBase, fetchImpl, resumable: true });',
      '  const walk = createWalkBoxWalk({ apiBase, fetchImpl: options.fetchImpl, resumable: true });') },
  { id: 'W4', what: 'the declaration goes round the seat', catches: 'V4', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, '    const got = await fetchDeclaration({ apiBase, fetchImpl });',
      '    const got = await fetchDeclaration({ apiBase, fetchImpl: options.fetchImpl });') },
  { id: 'W5', what: 'one world read draws the chips', catches: 'V8', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, 'worldChips: worlds.length > 1', 'worldChips: true') },
  { id: 'W6', what: 'the page never tells the graph it reads several', catches: 'V7', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, 'worldChips: worlds.length > 1', 'worldChips: false') },
  { id: 'W7', what: 'a world picked does not walk again', catches: 'V9', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, "    if (state.run !== 'idle' || markings.count(START)) await walkStarts();\n", '') },
  { id: 'W8', what: 'a world picked leaves the seat on the old worlds', catches: 'V9', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, '    worlds = worldList(names);\n', '') },
  { id: 'W10', what: 'Graph pressed before any Walk walks nothing', catches: 'G2', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, "void (state.run === 'idle' ? walkStarts() : showBranch());", 'void showBranch();') },
  { id: 'W11', what: 'with no answer the graph walks its own ask again', catches: 'G3', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, '    if (!state.result) return;\n', '') },
  { id: 'W12', what: 'a failed Walk on the Graph view says nothing there', catches: 'G3', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, "const status = state.view === 'graph' && walkStatus(state);", 'const status = false;') },
  { id: 'W13', what: 'the picture\'s Continue walks with its own fan-out, not the bar\'s knobs', catches: 'G4', file: 'walk/main.js', key: 'page',
    mutate: (t) => swap(t, 'new SubgraphView(graphMount, { doc, walk, ask: askFrom, entities,', 'new SubgraphView(graphMount, { doc, walk, entities,') },
  // ⚰️ W9 «Walk on the Graph view sends the graph's own ask» retired 10-12: the graph walks with the bar's ask (askFrom,
  //    owner 10-12 «one ask for every next walk»), so «its own» is the same request and G1 cannot tell them apart.
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
