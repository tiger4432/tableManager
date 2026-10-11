// FOLD VIEWS - the pure half (leads 793017c62 · 5ef260acf · 10-08 · 10-11 E2b): what a value reads as, the one start-branch
// question, a lump's answer and the points its page step's Trend reads, and the one drawing. Fed the implementer's
// captures of the real walk (walk_fold_*.json, PostgreSQL; walk_next_18766.json, one step from bond_temp;
// walk_scheme_ed/ev_18766.json, bond_temp in the edge and the event scheme).
//
// Run: node client2/tests/fold_views_harness.mjs
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { subgraphLayout } from '../src/walk/subgraph_view.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SUBJECT = path.join(HERE, '..', 'src', 'walk', 'fold_views.js');
const fx = (name) => JSON.parse(readFileSync(path.join(HERE, 'fixtures', name), 'utf8'));
const WAFER = fx('walk_fold_wafer.json');
const STEP = fx('walk_fold_recipe_step.json');
const PROCESS = fx('walk_fold_process_lump.json');
const nodesOf = (...bodies) => subgraphLayout([{ results: bodies }], []).nodes;
const NEXT = fx('walk_next_18766.json');
const ED = fx('walk_scheme_ed_18766.json');
const EV = fx('walk_scheme_ev_18766.json');
const COLOURS = { lit: '#a00', ring: '#000', rest: '#999', text: '#111', font: 'sans-serif' };
const DAY = 24 * 60 * 60 * 1000;

async function suite(m) {
  const names = [];
  const fails = [];
  const say = (name, cond, detail) => {
    names.push(name);
    if (cond) { console.log(`  PASS ${name}`); return; }
    fails.push(name);
    console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
  };

  console.log('\n[R] what a value reads as');
  const read = ['10.1', ' 3 ', '0', 0, 'S1', '', '  ', null, undefined, NaN, '1e3'].map((v) => m.numberOf(v));
  say('R1 text that is a number reads as it; text that is not, blank or nothing reads as none; 0 is a value',
    JSON.stringify(read) === JSON.stringify([10.1, 3, 0, 0, null, null, null, null, null, null, 1000]), JSON.stringify(read));
  console.log('\n[S] the one start-branch question');
  const later = { results: [STEP] };
  const lit = m.startBranch([{ results: [WAFER] }, later]);
  const waferIds = WAFER.nodes.map((n) => n.id);
  const others = STEP.nodes.map((n) => n.id).filter((id) => !waferIds.includes(id));
  say('S1 the start branch is every node the first step reached, and nothing a later step brought',
    waferIds.length > 0 && waferIds.every((id) => lit.has(id)) && others.length > 0 && others.every((id) => !lit.has(id))
      && lit.size === new Set(waferIds).size, JSON.stringify({ lit: lit.size, wafer: waferIds.length, others: others.length }));

  console.log('\n[L] a lump\'s answer and its points (lead 10-11 E2b)');
  // bond_temp's measures from 64 wafers: the lump its owner, the wafers its members; one edge of another predicate, one
  // between two members, a node beyond and one more measures of bond_temp from a wafer not a member - none the lump's.
  const q = NEXT.seed.id;
  const wafers = NEXT.nodes.filter((n) => n.type === 'wafer').map((n) => n.id);
  const extra = { ...NEXT, nodes: [...NEXT.nodes, { id: q, type: 'quantity', label: 'bond_temp', keys: { quantity: 'bond_temp' } }, { id: 'x:far', type: 'wafer', label: 'X', keys: { wafer: 'X' } },
    { id: 'x:txt', type: 'wafer', label: 'T', keys: { wafer: 'T' } }],
  edges: [...NEXT.edges, { id: 'x:1', source: wafers[0], target: q, predicate: 'leads_to' }, { id: 'x:2', source: wafers[0], target: wafers[1], predicate: 'measures' },
    { id: 'x:3', source: 'x:far', target: wafers[2], predicate: 'measures' },
    { id: 'x:4', source: 'x:txt', target: q, predicate: 'measures', qualifiers: { value: 'n/a' }, occurred_at: NEXT.edges[0].occurred_at }] };
  const lump = { owner: q, members: wafers, predicate: 'measures', farType: 'wafer' };
  const answer = m.lumpAnswer([extra], lump);
  const ownEdges = NEXT.edges.filter((e) => e.predicate === 'measures' && (e.target === q || e.source === q)).map((e) => e.id);
  say('L1 a lump\'s answer: its owner and members, the edges between them along its predicate - another predicate, an edge between members, a node beyond left out',
    answer.nodes.map((n) => n.id).sort().join() === [q, ...wafers].sort().join()
      && answer.edges.map((e) => e.id).sort().join() === ownEdges.sort().join() && ownEdges.length === wafers.length,
    JSON.stringify({ nodes: answer.nodes.length, edges: answer.edges.length, own: ownEdges.length }));
  const litL = new Set(wafers.slice(0, 5));
  const pts = m.lumpPoints(answer, lump, NEXT._decl.entities, [], litL);
  // The page's own read of the whole walk, the same rows and the same column: the wafers' measures value toward q.
  const { walkTableView } = await import('../src/walk/table_view.js');
  const { rowsPoints } = await import('../src/walk/trend.js');
  const full = walkTableView(NEXT, NEXT._decl.entities, [], undefined, { positive: [q], negative: [] });
  const sec = full.sections.find((x) => x.type === 'wafer');
  const page = rowsPoints(full, wafers, sec.trendable[0].column).map((x) => [x.t, Number(x.value), litL.has(x.row)]);
  say('L2 a lump\'s points: those the page reads for the same rows and column - numbers, its start branch lit',
    pts.length === wafers.length && JSON.stringify(pts.map((x) => [x.t, x.v, x.lit])) === JSON.stringify(page)
      && pts.some((x) => x.lit) && pts.some((x) => !x.lit),
    JSON.stringify({ points: pts.length, page: page.length, lit: pts.filter((x) => x.lit).length }));
  // A lump opened as a step reads as a Next from its owner along its predicate (lead 10-11): the same Route, the same sources.
  const fromLump = walkTableView(answer, NEXT._decl.entities, [], undefined, { positive: [q], negative: [] });
  const routes = (view) => view.sections.find((x) => x.type === 'wafer').rows
    .map((r) => [r.id, r.byGroup[0][r.byGroup[0].length - 1].text, view.sources.source(view.groups[0], r.id)]).sort();
  say('L3 a lump\'s step: each member\'s Route and source as the Next from its owner along its predicate says them',
    JSON.stringify(routes(fromLump)) === JSON.stringify(routes(full)) && routes(full).length === wafers.length
      && routes(full).every(([, route]) => route === 'measures'),
    JSON.stringify(routes(fromLump).slice(0, 2)));
  // The same quantity in the two schemes on 18766 (lead 10-11 E2c): its lump's points, the edge's value and the node's own.
  const scheme = (F, predicate, farType) => {
    const owner = F._seed;
    const members = F.nodes.filter((n) => n.type === farType).map((n) => n.id);
    const one = { owner, members, predicate, farType };
    return m.lumpPoints(m.lumpAnswer([F], one), one, F._decl.entities, F._decl.predicates, new Set()).map((x) => JSON.stringify([x.t, x.v])).sort();
  };
  const ed = scheme(ED, 'measures', 'wafer');
  const ev = scheme(EV, 'of_quantity', 'measurement');
  say('L4 a lump\'s points in two schemes - its members\' measures value, its measurements\' own value: the same values and times (lead 10-11 E2c)',
    ed.length === 4 && ed.join() === ev.join(), JSON.stringify({ ed: ed.length, ev: ev.length }));

  console.log('\n[D] the one drawing');
  const p = { points: pts };
  const svg = m.pointsSvg(p.points, { width: 200, height: 80, pad: 6.8, r: 3.4, colours: COLOURS, axes: true });
  const circles = [...svg.matchAll(/<circle [^>]*>/g)].map((c) => c[0]);
  const litAt = circles.map((c) => c.includes(`fill="${COLOURS.lit}"`));
  say('D1 a dot per point; the rest first and faded, the start branch drawn over them',
    circles.length === p.points.length && litAt.indexOf(true) > 0 && litAt.slice(litAt.indexOf(true)).every(Boolean)
      && circles.filter((c) => !c.includes(COLOURS.lit)).every((c) => c.includes('opacity="0.4"')),
    JSON.stringify(litAt));
  const vs = p.points.map((x) => x.v);
  say('D2 no line, band or path; the axis says the highest and lowest value only',
    !/<(line|path|rect|polyline)/.test(svg) && svg.includes(`>${Math.max(...vs)}<`) && svg.includes(`>${Math.min(...vs)}<`)
      && [...svg.matchAll(/<text /g)].length === 2, svg.slice(0, 200));
  const addr = m.svgAddress(svg);
  say('D3 the same drawing as an image address reads back as the same markup',
    addr.startsWith('data:image/svg+xml') && decodeURIComponent(addr.split(',').slice(1).join(',')) === svg, addr.slice(0, 60));
  return { ran: names.length, failures: fails, names };
}

let pass = 0;
const failures = [];
{
  const real = await import('../src/walk/fold_views.js');
  const base = await suite(real);
  pass += base.ran - base.failures.length;
  failures.push(...base.failures);
  const { loadWithProbe } = await import('./lib/probe.mjs');
  const { scoreMutants } = await import('./lib/mutation_scorer.mjs');
  const swap = (text, from, to) => {
    if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
    return text.split(from).join(to);
  };
  const M = (id, what, catches, from, to) => ({ id, what, catches, from, to });
  const MUTANTS = [
    M('Rm2', 'a blank text reads as 0', 'R1', "if (typeof value !== 'string' || !value.trim()) return null;", "if (typeof value !== 'string') return null;"),
    M('Sm1', 'the start branch is everything any step reached', 'S1',
      'const first = (steps || [])[0];\n  return new Set(((first && first.results) || [])',
      'return new Set((steps || []).flatMap((s) => s.results || [])'),
    M('Lm1', 'a lump\'s answer keeps every predicate between owner and member', 'L1',
      'if (e.predicate === lump.predicate && far !== null', 'if (far !== null'),
    M('Lm2', 'a lump\'s points not lit from the start branch', 'L2', 'lit: Boolean(lit && lit.has(p.row))', 'lit: false'),
    M('Lm3', 'a lump\'s answer carries no evidence', 'L3', 'propagation: { ranked: [...ranked.values()] } };', 'propagation: { ranked: [] } };'),
    M('Lm4', 'a lump\'s points read the steps\' columns only', 'L4', '  const at = section && section.trendable[0];',
      '  const at = section && section.columns.length ? { column: section.columns[0] } : null;'),
    M('Dm1', 'the start branch is drawn under the rest', 'D1', '[...labels, ...rest, ...lit]', '[...labels, ...lit, ...rest]'),
    M('Dm2', 'the rest is not faded', 'D1', ' opacity="0.4"/>', '/>'),
  ];
  const scored = await scoreMutants(MUTANTS, async (mu) => {
    const loaded = (await loadWithProbe(SUBJECT, { mutate: (t) => swap(t, mu.from, mu.to) })).module;
    const quiet = console.log;
    console.log = () => {};
    try { return await suite(loaded); } finally { console.log = quiet; }
  }, { baselineRan: base.ran, baselineNames: base.names, title: '\n  [mutants] - each must be caught by the check it names.' });
  pass += MUTANTS.length - scored.wrong;
  for (let i = 0; i < scored.wrong; i += 1) failures.push(`mutant verdict ${i + 1}`);
}
console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
