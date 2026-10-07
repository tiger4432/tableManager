// FOLD VIEWS - the pure half (leads 793017c62 · edcc0568c · 5ef260acf · 10-08): what a folded lump's table and
// points read, the one start-branch question, the window, and the one drawing. Fed the implementer's captures of
// the real walk (walk_fold_*.json, PostgreSQL), turned into the picture's nodes by the part's own `subgraphLayout`.
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
  const stepNodes = nodesOf(STEP);
  const processNodes = nodesOf(WAFER).filter((n) => n.type === 'process_event');
  say('R2 the y choices are the attributes some node holds a number in: the measurements\' value, none of the process events\' steps',
    JSON.stringify(m.valueAttributes(stepNodes)) === '["value"]' && processNodes.length > 0
      && JSON.stringify(m.valueAttributes(processNodes)) === '[]',
    JSON.stringify({ step: m.valueAttributes(stepNodes), process: m.valueAttributes(processNodes) }));
  const node = stepNodes[0];
  const two = { ...node, attributes: { value: '7' }, attributesByWorld: { value: [
    { world: 'what-if', value: '9', occurred_at: '2026-10-01T01:00:00+00:00' },
    { world: 'default', value: '7', occurred_at: '2026-10-01T02:00:00+00:00' }] } };
  say('R3 a value is said when the world that says it said it, not the first world listed',
    m.saidAt(two, 'value') === Date.parse('2026-10-01T02:00:00+00:00')
      && m.saidAt(node, 'value') === Date.parse(node.attributesByWorld.value[0].occurred_at),
    String(m.saidAt(two, 'value')));

  console.log('\n[S] the one start-branch question');
  const later = { results: [STEP] };
  const lit = m.startBranch([{ results: [WAFER] }, later]);
  const waferIds = WAFER.nodes.map((n) => n.id);
  const others = STEP.nodes.map((n) => n.id).filter((id) => !waferIds.includes(id));
  say('S1 the start branch is every node the first step reached, and nothing a later step brought',
    waferIds.length > 0 && waferIds.every((id) => lit.has(id)) && others.length > 0 && others.every((id) => !lit.has(id))
      && lit.size === new Set(waferIds).size, JSON.stringify({ lit: lit.size, wafer: waferIds.length, others: others.length }));

  console.log('\n[P] the points one attribute gives');
  const p = m.pointsOf(stepNodes, 'value', lit);
  const times = p.points.map((x) => x.t);
  say('P1 a point per node holding a number, at the time it was said, oldest first; the start branch\'s are lit',
    p.points.length === stepNodes.length && JSON.stringify(times) === JSON.stringify(times.slice().sort((a, b) => a - b))
      && p.points.filter((x) => x.lit).map((x) => x.id).sort().join() === stepNodes.filter((n) => lit.has(n.id)).map((n) => n.id).sort().join()
      && p.points.some((x) => x.lit) && p.points.some((x) => !x.lit),
    JSON.stringify({ points: p.points.length, lit: p.points.filter((x) => x.lit).length }));
  const odd = [{ ...node, id: 'a', attributes: { value: 'S1' } }, { ...node, id: 'b', attributesByWorld: {} },
    { ...node, id: 'c', attributes: {} }, node];
  const q = m.pointsOf(odd, 'value', new Set());
  say('P2 a value that is not a number and a value said at no time are left out and counted; a node without it is not counted',
    q.points.length === 1 && q.notNumber === 1 && q.noTime === 1, JSON.stringify({ points: q.points.length, notNumber: q.notNumber, noTime: q.noTime }));

  console.log('\n[W] the window of the one more step');
  const w = m.windowAround([Date.parse('2026-10-01T00:00:00Z'), Date.parse('2026-10-03T00:00:00Z'), NaN]);
  say('W1 the start branch\'s times, AROUND_DAYS each side; no time known, no window',
    m.AROUND_DAYS === 7 && w && w.since === Date.parse('2026-10-01T00:00:00Z') - 7 * DAY
      && w.until === Date.parse('2026-10-03T00:00:00Z') + 7 * DAY && m.windowAround([NaN]) === null && m.windowAround([]) === null,
    JSON.stringify(w));

  console.log('\n[D] the one drawing');
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
    M('Rm3', 'a value is said when the first world said something', 'R3',
      'const said = saids.find((s) => s && s.value === value) || saids[0];', 'const said = saids[0];'),
    M('Sm1', 'the start branch is everything any step reached', 'S1',
      'const first = (steps || [])[0];\n  return new Set(((first && first.results) || [])',
      'return new Set((steps || []).flatMap((s) => s.results || [])'),
    M('Pm1', 'the points are not lit from the start branch', 'P1', 'lit: Boolean(lit && lit.has(node.id))', 'lit: false'),
    M('Pm2', 'a value said at no time stands at time 0', 'P2', "if (t === null) { noTime += 1; continue; }", ''),
    M('Wm1', 'the window is a day each side', 'W1', 'export const AROUND_DAYS = 7;', 'export const AROUND_DAYS = 1;'),
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
