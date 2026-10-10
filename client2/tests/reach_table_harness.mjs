// The walk table as a formula (walk/reach_table.js, lead 5cf5c3401): the same rows, values and missing cells on two
// schemes - a measurement as an edge (its value an edge attribute) and as an event node (its value the node's) - plus
// three groups, several values a cell, a two-step column, rows from a marking, the default columns of each scheme, Δ,
// the differs and missing flags and the ways cap. It imports its subject.
//
// CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SUBJECT = join(HERE, '..', 'src', 'walk', 'reach_table.js');
const ascii = (t) => String(t).replace(/[^\x00-\x7f]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);

const node = (id, type, attributes = {}) => ({ id, type, label: id.toUpperCase(), attributes });
const edge = (source, predicate, target, qualifiers) => ({ id: `${source}>${target}`, source, target, predicate, ...(qualifiers ? { qualifiers } : {}) });
const ranked = (rows) => ({ ranked: Object.entries(rows).map(([id, reach]) => ({ id, reach })) });
const STARTS = [{ name: '+', starts: ['wp'] }, { name: '−', starts: ['wn'] }];
const W = ['wp', 'wn'].map((id) => node(id, 'wafer'));
const Q = ['q1', 'q2', 'q3'].map((id) => node(id, 'quantity'));
// Scheme A: the measurement is an edge, its value the edge's.
const EDGE_SCHEME = {
  nodes: [...W, ...Q],
  edges: [edge('wp', 'measures', 'q1', { value: 30.5, step: 'FAKE' }), edge('wn', 'measures', 'q1', { value: 11, step: 'FAKE' }),
    edge('wp', 'measures', 'q2', { value: 4.2, step: 'FAKE' }), edge('wn', 'measures', 'q3', { value: 0.8, step: 'FAKE' })],
  propagation: ranked({ q1: [1, 1], q2: [1, 0], q3: [0, 1] }),
};
// Scheme B: the measurement is an event node between them, its value the node's.
const EVENT_SCHEME = {
  nodes: [...W, ...Q, node('e1', 'measurement', { value: 30.5 }), node('e2', 'measurement', { value: 11 }),
    node('e3', 'measurement', { value: 4.2 }), node('e4', 'measurement', { value: 0.8 })],
  edges: [edge('wp', 'measured', 'e1'), edge('e1', 'of', 'q1'), edge('wn', 'measured', 'e2'), edge('e2', 'of', 'q1'),
    edge('wp', 'measured', 'e3'), edge('e3', 'of', 'q2'), edge('wn', 'measured', 'e4'), edge('e4', 'of', 'q3')],
  propagation: ranked({ e1: [1, 0], e3: [1, 0], e2: [0, 1], e4: [0, 1], q1: [1, 1], q2: [1, 0], q3: [0, 1] }),
};
const ROWS = ['q1', 'q2', 'q3'];
const col = (steps, on, name) => ({ steps: steps.map(([predicate, direction]) => ({ predicate, direction })), value: { on, name } });
const said = (cell) => (cell.missing ? 'missing' : cell.values.join(',') || '-');

function suite(F) {
  const names = [];
  const failures = [];
  const eq = (name, got, want) => {
    names.push(name);
    const g = ascii(JSON.stringify(got)), w = ascii(JSON.stringify(want));
    if (g === w) { console.log(`  PASS ${name}`); return; }
    failures.push(name);
    console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`);
  };
  const run = (scheme, columns, rows = ROWS, starts = STARTS) => {
    const index = F.indexGraph(scheme);
    const groups = F.groupsOf(scheme, starts);
    return { index, groups, table: F.tableOf(index, groups, rows, columns) };
  };
  const cellsOf = (got) => got.table.map((r) => [r.id, r.cells.map((byGroup) => byGroup.map(said))]);
  const a = run(EDGE_SCHEME, [col([['measures', 'incoming']], 'edge', 'value'), col([['measures', 'incoming']], 'label')]);
  const b = run(EVENT_SCHEME, [col([['of', 'incoming']], 'node', 'value'), col([['of', 'incoming'], ['measured', 'incoming']], 'label')]);
  const want = [['q1', [['30.5', '11'], ['WP', 'WN']]], ['q2', [['4.2', 'missing'], ['WP', 'missing']]],
    ['q3', [['missing', '0.8'], ['missing', 'WN']]]];
  eq('R1 the edge scheme: a row a node, each group its own value, missing where it did not reach', cellsOf(a), want);
  eq('R2 the event scheme, its value one node further and its wafer two steps: the same rows, values and missing',
    cellsOf(b), want);
  eq('R3 delta: two groups, one number each - the first less the second', a.table.map((r) => r.deltas[0]), [19.5, null, null]);
  eq('R4 the flags: missing where a group did not reach, differs where the groups say other things',
    a.table.map((r) => [r.missing, r.differs]), [[false, true], [true, true], [true, true]]);
  const same = run({ ...EDGE_SCHEME, edges: [...EDGE_SCHEME.edges.slice(0, 1), edge('wn', 'measures', 'q1', { value: 30.5 })] },
    [col([['measures', 'incoming']], 'edge', 'value')], ['q1']);
  eq('R5 two groups saying the same: not differs', same.table.map((r) => [r.missing, r.differs]), [[false, false]]);
  const twice = run({ ...EDGE_SCHEME, edges: [...EDGE_SCHEME.edges, { ...edge('wp', 'measures', 'q1', { value: 31 }), id: 'again' }] },
    [col([['measures', 'incoming']], 'edge', 'value')], ['q1']);
  eq('R6 several ways, several values: every one kept, and no delta', [twice.table[0].cells[0].map(said), twice.table[0].deltas[0]],
    [['30.5,31', '11'], null]);
  const third = { ...EDGE_SCHEME, nodes: [...EDGE_SCHEME.nodes, node('wz', 'wafer')],
    edges: [...EDGE_SCHEME.edges, edge('wz', 'measures', 'q3', { value: 7 })],
    propagation: ranked({ q1: [1, 1, 0], q2: [1, 0, 0], q3: [0, 1, 1] }) };
  const three = run(third, [col([['measures', 'incoming']], 'edge', 'value')], ROWS, [...STARTS, { name: '3', starts: ['wz'] }]);
  eq('R7 three groups: a cell each, no delta', three.table.map((r) => [r.cells[0].map(said), r.deltas[0]]),
    [[['30.5', '11', 'missing'], null], [['4.2', 'missing', 'missing'], null], [['missing', '0.8', '7'], null]]);
  const marked = run(EVENT_SCHEME, [col([['of', 'incoming']], 'node', 'value')], ['q3', 'q1']);
  eq('R8 rows from a marking: its nodes, in its order, keyed by id', marked.table.map((r) => [r.id, r.cells[0].map(said)]),
    [['q3', ['missing', '0.8']], ['q1', ['30.5', '11']]]);
  const capped = F.cellOf(twice.index, new Set(['q1', 'wp', 'wn']), 'q1', col([['measures', 'incoming']], 'edge', 'value'), 2);
  eq('R9 a cell follows its first ways and says it has more', [capped.values, capped.more], [[30.5, 11], true]);
  const bare = run(EDGE_SCHEME, [], ['q1', 'q2']);
  eq('R15 a row with no column: differs and missing from where the groups reached it', bare.table.map((r) => [r.missing, r.differs]),
    [[false, false], [true, true]]);
  const words = (scheme) => F.defaultColumns(F.indexGraph(scheme), ROWS).map((c) => c.words.join(' · '));
  eq('R10 the edge scheme\'s own columns: the attributes its edges carry, nothing of the far node', words(EDGE_SCHEME),
    ['measures (in) · step', 'measures (in) · value']);
  eq('R11 the event scheme\'s own columns: none - its edges carry nothing; its value is a column of the far node (R2)',
    words(EVENT_SCHEME), []);
  const keyed = F.defaultColumns(F.indexGraph({ nodes: [{ ...node('w1', 'wafer', { grade: 'A' }), keys: { wafer: 'W-1' } }], edges: [] }),
    ['w1'], ['wafer']);
  eq('R16 the row\'s own keys and the attributes it carries first, with no step: the node\'s own, read off the row',
    [keyed.map((c) => [c.words.join(' · '), c.steps.length, c.value.on]),
      F.cellOf(F.indexGraph({ nodes: [{ ...node('w1', 'wafer', { grade: 'A' }), keys: { wafer: 'W-1' } }], edges: [] }),
        new Set(['w1']), 'w1', keyed[0]).values],
    [[['wafer', 0, 'key'], ['grade', 0, 'node']], ['W-1']]);
  const both = { nodes: [node('d1', 'die'), node('d2', 'die'), node('d3', 'die')],
    edges: [edge('d1', 'bonded_from', 'd2', { at: 1 }), edge('d3', 'bonded_from', 'd1', { at: 2 })] };
  eq('R12 a step taken in says «(in)»: one predicate both ways, two columns told apart',
    F.defaultColumns(F.indexGraph(both), ['d1']).map((c) => c.words.join(' · ')), ['bonded_from · at', 'bonded_from (in) · at']);
  // ⚰️ R13 · R14 (how each group reached its nodes) retired 10-10 with viaDepth: the table's Route reads the paths the
  // server walked, an answer's evidence (lead df11f9e81) - walk_table_harness Z29 - Z32.
  const ev = F.indexGraph(EVENT_SCHEME);
  eq('R17 + Column\'s routes: what the rows take in this walk, either way, step by step',
    F.routesFrom(ev, ROWS, 2).map((r) => [r.words.join(' · '), r.to.join()]),
    [['of (in)', 'measurement'], ['of (in) · measured (in)', 'wafer'], ['of (in) · of', 'quantity']]);
  eq('R18 + Column\'s values at a route\'s end: the far node\'s attribute and its name - the event scheme\'s value',
    F.valuesAt(ev, ROWS, [{ predicate: 'of', direction: 'incoming' }]).map((v) => `${v.on} ${v.name}`), ['node value', 'label name']);
  eq('R19 a column judged once by its values\' JSON type: a numeral in a string and a time are strings; a delta needs numbers',
    [[1, 2.5], ['a', ['x', 'y']], [true, false], [1, 'a'], ['', null, '  '], ['2026-10-10T00:00:00'], ['30.5']].map(F.valueKind)
      .concat([F.deltaOf([{ missing: false, values: ['30.5'] }, { missing: false, values: ['11'] }])]),
    ['number', 'string', 'boolean', 'mixed', 'empty', 'string', 'string', null]);
  return { ran: names.length, names, failures };
}

console.log('\n[1] reach table');
const base = suite(await import('../src/walk/reach_table.js'));
let ran = base.ran;
let failed = base.failures.length;
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  { id: 'FM1', what: 'a cell follows edges outside its group', catches: 'R1 ',
    mutate: (t) => swap(t, '(inside && !inside.has(farOf(e, step.direction)))', 'false') },
  { id: 'FM2', what: 'a row its group did not reach drawn empty, not missing', catches: 'R1 ',
    mutate: (t) => swap(t, "  if (!inside.has(x)) return { missing: true, reads: [], more: false };\n", '') },
  { id: 'FM3', what: 'every step taken outgoing', catches: 'R1 ',
    mutate: (t) => swap(t, "const edges = (step.direction === 'incoming' ? index.into : index.out).get(end.node) || [];",
      'const edges = index.out.get(end.node) || [];') },
  { id: 'FM4', what: 'a node attribute read off the last edge, as if every value rode on an edge', catches: 'R2',
    mutate: (t) => swap(t, '  return (node.attributes || {})[value.name];', '  return end.edge ? ((end.edge.qualifiers || {})[value.name]) : undefined;') },
  { id: 'FM5', what: 'delta from the first value of several', catches: 'R6',
    mutate: (t) => swap(t, 'cell.values.length === 1 &&', 'cell.values.length >= 1 &&') },
  { id: 'FM6', what: 'the last way\'s value overwrites the others', catches: 'R6',
    mutate: (t) => swap(t, "  const reads = ends.map((end) => ({", "  const reads = ends.slice(-1).map((end) => ({") },
  { id: 'FM7', what: 'every group reads the first group\'s reach', catches: 'R7',
    mutate: (t) => swap(t, 'Number((row.reach || [])[i]) > 0', 'Number((row.reach || [])[0]) > 0') },
  { id: 'FM8', what: 'an edge read without its attributes: a column for every step', catches: 'R11',
    mutate: (t) => swap(t, '    for (const name of [...s.names].sort()) columns.push(', '    for (const name of [...s.names, \'\'].sort()) columns.push(') },
  { id: 'FM14', what: '+ Column\'s routes taken one way only', catches: 'R17',
    mutate: (t) => swap(t, "        for (const [direction, edges] of [['outgoing', index.out.get(at)], ['incoming', index.into.get(at)]]) {\n          for (const e of edges || []) {\n            const key",
      "        for (const [direction, edges] of [['outgoing', index.out.get(at)]]) {\n          for (const e of edges || []) {\n            const key") },
  { id: 'FM15', what: '+ Column offers no far node attribute', catches: 'R18',
    mutate: (t) => swap(t, '    for (const name of Object.keys(node.attributes || {})) names.node.add(name);\n', '') },
  { id: 'FM16', what: 'a numeral in a string judged a number', catches: 'R19',
    mutate: (t) => swap(t, ".map((v) => (typeof v === 'number' ? 'number'", ".map((v) => (Number.isFinite(Number(v)) && typeof v !== 'boolean' ? 'number'") },
  { id: 'FM17', what: 'a delta of numerals in strings', catches: 'R19',
    mutate: (t) => swap(t, "cell.values.length === 1 && typeof cell.values[0] === 'number'\n  && Number.isFinite(cell.values[0]) ? cell.values[0] : null);",
      "cell.values.length === 1\n  && Number.isFinite(Number(cell.values[0])) ? Number(cell.values[0]) : null);") },
  { id: 'FM13', what: 'a row key read as an attribute', catches: 'R16',
    mutate: (t) => swap(t, "  if (value.on === 'key') return (node.keys || {})[value.name];\n", '') },
  { id: 'FM9', what: 'a predicate taken both ways not told apart', catches: 'R12',
    mutate: (t) => swap(t, "(step.direction === 'incoming' ? `${step.predicate} (in)` : step.predicate)", '(step.predicate)') },
  { id: 'FM11', what: 'differs read off the values only', catches: 'R15',
    mutate: (t) => swap(t, 'differs: reached.some((r) => r !== reached[0]) || ', 'differs: ') },
  { id: 'FM12', what: 'the ways cap never said', catches: 'R9', mutate: (t) => swap(t, '{ more = true; break; }', '{ break; }') },
];
const scored = await scoreMutants(MUTANTS, async (m) => suite((await loadWithProbe(SUBJECT, { mutate: m.mutate })).module),
  { baselineRan: base.ran, baselineNames: base.names, title: '\n  [1] mutants - each must be caught by the check it names.' });
ran += MUTANTS.length;
failed += scored.wrong;
console.log(`\n${ran - failed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
