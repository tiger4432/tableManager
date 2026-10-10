// The one simple-path search (walk/paths.js, lead 55f854fc5): the declaration's type routes (api.js pathsBetween) and the
// paths between two marked nodes of a walk.
//
// Scores simplePaths - every simple path either way, a route back to the start, a path ending at its destination, a
// self-loop not a step, the step cap, the count cap said only when a path was left - and pathKinds - kinds by the
// node types and predicates passed, an unchecked predicate's kind gone, direction ignored, a kind's paths capped,
// nothing found - and edgeCounts. It imports its subject. CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SUBJECT = join(HERE, '..', 'src', 'walk', 'paths.js');
const ascii = (t) => String(t).replace(/[^\x00-\x7f]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
const E = (from, to, predicate) => ({ from, to, predicate });
const via = (paths) => paths.map((p) => p.map((s) => `${s.predicate}>${s.next}`).join(' '));

// A walk's answer: a void, the wafer it is marked with, two model paths (each through a quantity), one through another
// predicate between the same types, and one bonding path whose edges point either way.
const NODES = [['v', 'void'], ['w', 'wafer'], ['q1', 'quantity'], ['q2', 'quantity'], ['q3', 'quantity'], ['d1', 'die'],
  ['d2', 'die']].map(([id, type]) => ({ id, type }));
let n = 0;
const edge = (source, target, predicate) => ({ id: `e${n += 1}`, source, target, predicate });
const EDGES = [edge('v', 'q1', 'leads_to'), edge('q1', 'w', 'measures'), edge('v', 'q2', 'leads_to'), edge('w', 'q2', 'measures'),
  edge('v', 'q3', 'predicts'), edge('q3', 'w', 'measures'), edge('d1', 'v', 'observed'), edge('d1', 'd2', 'bonded_from'),
  edge('w', 'd2', 'in_container')];
const ALL = new Set(['leads_to', 'measures', 'predicts', 'observed', 'bonded_from', 'in_container']);
const without = (name) => new Set([...ALL].filter((p) => p !== name));
const kindsOf = (got) => got.kinds.map((k) => [k.words.join(' '), k.count]);

function suite(P) {
  const names = [];
  const failures = [];
  const eq = (name, got, want) => {
    names.push(name);
    const g = ascii(JSON.stringify(got)), w = ascii(JSON.stringify(want));
    if (g === w) { console.log(`  PASS ${name}`); return; }
    failures.push(name);
    console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`);
  };
  const two = [E('a', 'b', 'p'), E('c', 'b', 'q'), E('a', 'c', 'r')];
  eq('P1 every simple path, either way along an edge, in the edges\' order',
    via(P.simplePaths(two, 'a', 'b', 5).paths), ['p>b', 'r>c q>b']);
  eq('P2 a route back: the start is the one vertex reached twice, on arriving',
    via(P.simplePaths([E('a', 'b', 'p'), E('b', 'a', 'q')], 'a', 'a', 5).paths), ['p>b p>a', 'p>b q>a', 'q>b p>a', 'q>b q>a']);
  eq('P3 a path ends at its destination: none walks on through it',
    via(P.simplePaths([E('a', 'b', 'p'), E('b', 'c', 'q'), E('c', 'b', 'r')], 'a', 'b', 5).paths), ['p>b']);
  eq('P4 a self-loop is not a step, not even a route back', via(P.simplePaths([E('a', 'a', 'loop')], 'a', 'a', 5).paths), []);
  eq('P5 no path past the step cap', via(P.simplePaths(two, 'a', 'b', 1).paths), ['p>b']);
  const capped = P.simplePaths(two, 'a', 'b', 5, 1);
  const exact = P.simplePaths(two, 'a', 'b', 5, 2);
  eq('P6 the count cap stops the search and says so - only when a path was left', [via(capped.paths), capped.cut, exact.cut],
    [['p>b'], true, false]);
  const walk = { nodes: NODES, edges: EDGES };
  const all = P.pathKinds(walk, 'v', 'w', ALL);
  eq('K1 kinds by the node types and the predicates passed, from the first node; the shortest first, then the most',
    kindsOf(all), [['void leads_to quantity measures wafer', 2], ['void predicts quantity measures wafer', 1],
      ['void observed die bonded_from die in_container wafer', 1]]);
  eq('K2 a predicate unchecked: its kind is gone', kindsOf(P.pathKinds(walk, 'v', 'w', without('bonded_from'))),
    [['void leads_to quantity measures wafer', 2], ['void predicts quantity measures wafer', 1]]);
  eq('K3 a kind\'s paths: its nodes and its edges, whichever way each edge points',
    (all.kinds[2] || { paths: [] }).paths.map((p) => [p.nodes, p.edges.map((e) => e.id)]), [[['v', 'd1', 'd2', 'w'], ['e7', 'e8', 'e9']]]);
  const many = { nodes: [...NODES, ...Array.from({ length: 25 }, (_, i) => ({ id: `m${i}`, type: 'quantity' }))],
    edges: [...EDGES, ...Array.from({ length: 25 }, (_, i) => [edge('v', `m${i}`, 'leads_to'), edge(`m${i}`, 'w', 'measures')]).flat()] };
  const big = P.pathKinds(many, 'v', 'w', ALL).kinds[0];
  eq('K4 a kind keeps its first 20 paths and says there are more', [big.count, big.paths.length, big.more], [27, 20, true]);
  eq('K5 nothing checked: no path, none found', [P.pathKinds(walk, 'v', 'w', new Set()).kinds, P.pathKinds(walk, 'v', 'w', new Set()).found],
    [[], 0]);
  eq('K6 a node the walk did not bring, or the same node twice: nothing', [P.pathKinds(walk, 'v', 'x', ALL).found,
    P.pathKinds(walk, 'v', 'v', ALL).found], [0, 0]);
  eq('K7 the edge list: each predicate the walk carries, its count, by name', P.edgeCounts(EDGES).map((c) => `${c.predicate} ${c.count}`),
    ['bonded_from 1', 'in_container 1', 'leads_to 2', 'measures 3', 'observed 1', 'predicts 1']);
  return { ran: names.length, names, failures };
}

console.log('\n[1] paths');
const base = suite(await import('../src/walk/paths.js'));
let ran = base.ran;
let failed = base.failures.length;
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  // Moved here with the search from api.js pathsBetween (its RC12 - RC14 mutants, lead 10-09).
  { id: 'PM1', what: 'a route never comes back', catches: 'P2',
    mutate: (t) => swap(t, '      if (seen.has(next) && next !== to) continue;', '      if (seen.has(next)) continue;') },
  { id: 'PM2', what: 'a path walks on past its destination', catches: 'P3',
    mutate: (t) => swap(t, '      else paths.push(chain.slice());\n      return;', '      else paths.push(chain.slice());\n      if (chain.length > 2) return;') },
  { id: 'PM3', what: 'a self-loop is a step', catches: 'P4',
    mutate: (t) => swap(t, '    if (edge.from === edge.to) continue;\n', '') },
  { id: 'PM4', what: 'no step cap', catches: 'P5', mutate: (t) => swap(t, '    if (chain.length >= limit) return;\n', '') },
  { id: 'PM5', what: 'the count cap said whenever it is reached', catches: 'P6',
    mutate: (t) => swap(t, '      if (paths.length >= most) cut = true;\n      else paths.push(chain.slice());',
      '      if (paths.length < most) paths.push(chain.slice());\n      if (paths.length >= most) cut = true;') },
  { id: 'PM6', what: 'an edge walked one way only', catches: 'K3',
    mutate: (t) => swap(t, 'for (const [at, next] of [[edge.from, edge.to], [edge.to, edge.from]]) {', 'for (const [at, next] of [[edge.from, edge.to]]) {') },
  { id: 'PM7', what: 'an unchecked predicate still walked', catches: 'K2',
    mutate: (t) => swap(t, '.filter((e) => checked.has(e.predicate) && typeOf.has(e.source)', '.filter((e) => typeOf.has(e.source)') },
  { id: 'PM8', what: 'a kind by its node types alone', catches: 'K1',
    mutate: (t) => swap(t, "const key = words.join('\\u0000');", "const key = nodes.map((id) => typeOf.get(id)).join('\\u0000');") },
  { id: 'PM9', what: 'a kind keeps every path', catches: 'K4',
    mutate: (t) => swap(t, 'if (kind.paths.length < perKind)', 'if (true)') },
];
const scored = await scoreMutants(MUTANTS, async (m) => suite((await loadWithProbe(SUBJECT, { mutate: m.mutate })).module),
  { baselineRan: base.ran, baselineNames: base.names, title: '\n  [1] mutants - each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;
console.log(`\n${ran - failed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
