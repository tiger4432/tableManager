// The walk table as a formula (walk/reach_table.js, lead 5cf5c3401): the same rows, values and missing cells on two
// schemes - a measurement as an edge (its value an edge attribute) and as an event node (its value the node's) - plus
// three groups, several values a cell, a two-step column, rows from a marking, the default columns of each scheme, Δ,
// the differs and missing flags, the ways cap and what says when (owner 10-10 e54560dc2). It imports its subject.
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
  eq('R10 the edge scheme\'s own columns: a group its far type, the attributes its edges carry (lead 10-11 W addendum 8 (다))',
    words(EDGE_SCHEME), ['measures ← wafer · step', 'measures ← wafer · value']);
  const perWafer = (t) => t === 'wafer';
  eq('R25 a far type that names (the declaration\'s static ones): a group a far node, the node named (lead 10-11 W addendum 8 (다))',
    F.defaultColumns(F.indexGraph(EDGE_SCHEME), ROWS, [], perWafer).map((c) => [c.words.join(' · '), c.end || null]),
    [['measures ← WN · step', 'wn'], ['measures ← WN · value', 'wn'], ['measures ← WP · step', 'wp'], ['measures ← WP · value', 'wp']]);
  // A far type's group reads its type's far ends only: x measures a (type A, 1) and b (type B, 2).
  const TWO_TYPES = { nodes: [node('x', 'X'), node('a', 'A'), node('b', 'B')], edges: [edge('x', 'p', 'a', { v: 1 }), edge('x', 'p', 'b', { v: 2 })] };
  eq('R26 a far type\'s group: the row\'s edges to that type, no other',
    F.defaultColumns(F.indexGraph(TWO_TYPES), ['x']).map((c) => [c.words.join(' · '), F.cellOf(F.indexGraph(TWO_TYPES), new Set(['x', 'a', 'b']), 'x', c).values]),
    [['p → A · v', [1]], ['p → B · v', [2]]]);
  // A column that ends at one node reads its edges to that node only; who gave a value - an edge's its subject, a node's
  // its own (lead 10-11 W 10, 11).
  const ix = F.indexGraph(EDGE_SCHEME);
  const toQ1 = { ...col([['measures', 'outgoing']], 'edge', 'value'), end: 'q1' };
  eq('R22 a column ending at a node: the row\'s edges to that node, no other (lead 10-11 W 10)',
    [F.cellOf(ix, new Set(['wp', 'q1', 'q2']), 'wp', toQ1).values, F.cellOf(ix, new Set(['wp', 'q1', 'q2']), 'wp', col([['measures', 'outgoing']], 'edge', 'value')).values],
    [[30.5], [30.5, 4.2]]);
  const ev0 = F.indexGraph(EVENT_SCHEME);
  eq('R23 who gave a value: an edge\'s its subject - the wafer, read from the wafer or from the quantity - a node\'s the node (lead 10-11 W 11)',
    [F.readsOf(ix, new Set(['wp', 'q1']), 'wp', toQ1).reads.map((r) => r.giver), F.readsOf(ix, new Set(['wp', 'q1']), 'q1', col([['measures', 'incoming']], 'edge', 'value')).reads.map((r) => r.giver),
      F.readsOf(ev0, new Set(['q1', 'e1']), 'q1', col([['of', 'incoming']], 'node', 'value')).reads.map((r) => r.giver)],
    [['wp'], ['wp'], ['e1']]);
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
  eq('R12 a step\'s arrow: out «→», in «←» - one predicate both ways, two columns told apart (lead 10-11 W: «(in)» retired)',
    F.defaultColumns(F.indexGraph(both), ['d1']).map((c) => c.words.join(' · ')), ['bonded_from → die · at', 'bonded_from ← die · at']);
  // ⚰️ R13 · R14 (how each group reached its nodes) retired 10-10 with viaDepth: the table's Route reads the paths the
  // server walked, an answer's evidence (lead df11f9e81) - walk_table_harness Z29 - Z32.
  const ev = F.indexGraph(EVENT_SCHEME);
  eq('R17 + Column\'s routes: what the rows take in this walk, either way, step by step',
    F.routesFrom(ev, ROWS, 2).map((r) => [r.words.join(' · '), r.to.join()]),
    [['of ← measurement', 'measurement'], ['of ← measurement · measured ← wafer', 'wafer'], ['of ← measurement · of → quantity', 'quantity']]);
  eq('R18 + Column\'s values at a route\'s end: the far node\'s attribute and its name - the event scheme\'s value',
    F.valuesAt(ev, ROWS, [{ predicate: 'of', direction: 'incoming' }]).map((v) => `${v.on} ${v.name}`), ['node value', 'label name']);
  eq('R19 a column judged once: a numeral in a string is a number, a time a string; a delta of numerals in strings their difference (lead 10-11: one answer to «is this a number»)',
    [[1, 2.5], ['a', ['x', 'y']], [true, false], [1, 'a'], ['', null, '  '], ['2026-10-10T00:00:00'], ['30.5']].map(F.valueKind)
      .concat([F.deltaOf([{ missing: false, values: ['30.5'] }, { missing: false, values: ['11'] }])]),
    ['number', 'string', 'boolean', 'mixed', 'empty', 'string', 'number', 19.5]);
  eq('R24 a value as a number: a numeral in text reads as it; text that is not, blank or nothing reads as none; 0 is a value',
    ['10.1', ' 3 ', '0', 0, 'S1', '', '  ', null, undefined, NaN, '1e3'].map(F.numberOf), [10.1, 3, 0, 0, null, null, null, null, null, null, 1000]);
  // The end's time (owner 10-10 e54560dc2, lead 10-11 E2c): a node that said 9 in one world and 7 in another, 7 its value;
  // a node that keeps no record; the edges into q timed apart from both.
  const SAID = { nodes: [node('q', 'quantity'), { ...node('e', 'measurement', { value: 7 }),
    attributes_by_world: { value: [{ world: 'b', value: 9, occurred_at: 'T1' }, { world: 'a', value: 7, occurred_at: 'T5' }] } },
  node('f', 'measurement', { value: 8 })],
  edges: [{ ...edge('e', 'of', 'q', { value: 3 }), occurred_at: 'T3' }, { ...edge('f', 'of', 'q'), occurred_at: 'T4' }] };
  const whenOf = (column) => F.readsOf(F.indexGraph(SAID), new Set(['q', 'e', 'f']), 'q', column).reads
    .map((r) => [r.value, r.when ? r.when.occurred_at : null]);
  eq('R20 what says when: an edge\'s value its edge; a node attribute the node\'s own record of that value, none when it keeps none (owner 10-10 e54560dc2, lead 10-11 E2c)',
    [whenOf(col([['of', 'incoming']], 'edge', 'value')), whenOf(col([['of', 'incoming']], 'node', 'value'))],
    [[[3, 'T3']], [[7, 'T5'], [8, null]]]);
  // A many attribute (lead 10-11 W 13): its value a list, its record the same list as another object; two groups saying
  // the same list.
  const MANY = { nodes: [node('q', 'quantity'), { ...node('e', 'measurement', { value: [10.4, 10.2, 10] }),
    attributes_by_world: { value: [{ world: 'a', value: [10.4, 10.2, 10], occurred_at: 'T5' }] } }],
  edges: [{ ...edge('e', 'of', 'q'), occurred_at: 'T3' }] };
  const manyCol = col([['of', 'incoming']], 'node', 'value');
  const manyIndex = F.indexGraph(MANY);
  const twoSaying = [{ name: '+', inside: new Set(['q', 'e']) }, { name: '-', inside: new Set(['q', 'e']) }];
  eq('R21 a many attribute: timed by the record saying the same list - its items, not one object; two groups saying it do not differ (lead 10-11 W 13)',
    [F.readsOf(manyIndex, new Set(['q', 'e']), 'q', manyCol).reads.map((r) => [r.value, r.when ? r.when.occurred_at : null]),
      F.tableOf(manyIndex, twoSaying, ['q'], [manyCol]).map((r) => r.differs)],
    [[[[10.4, 10.2, 10], 'T5']], [false]]);
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
    mutate: (t) => swap(t, '(inside && !inside.has(far))', 'false') },
  { id: 'FM21', what: 'a column ending at a node reads every far node', catches: 'R22',
    mutate: (t) => swap(t, '(lastId && far !== lastId) || ', '') },
  { id: 'FM24', what: 'a far type\'s group reads every far type', catches: 'R26',
    mutate: (t) => swap(t, " || (lastTypes && !lastTypes.includes((index.nodes.get(far) || {}).type || ''))", '') },
  { id: 'FM25', what: 'every far node its own group', catches: 'R10',
    mutate: (t) => swap(t, 'const end = perNode(type) ? id : null;', 'const end = id;') },
  { id: 'FM22', what: 'an edge\'s value given by its far end', catches: 'R23',
    mutate: (t) => swap(t, "giver: column.value.on === 'edge' && end.edge ? end.edge.source : end.node", 'giver: end.node') },
  { id: 'FM2', what: 'a row its group did not reach drawn empty, not missing', catches: 'R1 ',
    mutate: (t) => swap(t, "  if (!inside.has(x)) return { missing: true, reads: [], more: false };\n", '') },
  { id: 'FM3', what: 'every step taken outgoing', catches: 'R1 ',
    mutate: (t) => swap(t, "const edges = (step.direction === 'incoming' ? index.into : index.out).get(end.node) || [];",
      'const edges = index.out.get(end.node) || [];') },
  { id: 'FM4', what: 'a node attribute read off the last edge, as if every value rode on an edge', catches: 'R2 ',
    mutate: (t) => swap(t, '  const said = (node.attributes || {})[value.name];', '  const said = end.edge ? ((end.edge.qualifiers || {})[value.name]) : undefined;') },
  { id: 'FM5', what: 'delta from the first value of several', catches: 'R6',
    mutate: (t) => swap(t, 'cell.values.length === 1 ? numberOf', 'cell.values.length >= 1 ? numberOf') },
  { id: 'FM6', what: 'the last way\'s value overwrites the others', catches: 'R6',
    mutate: (t) => swap(t, "  const reads = ends.map((end) => ({", "  const reads = ends.slice(-1).map((end) => ({") },
  { id: 'FM7', what: 'every group reads the first group\'s reach', catches: 'R7',
    mutate: (t) => swap(t, 'Number((row.reach || [])[i]) > 0', 'Number((row.reach || [])[0]) > 0') },
  { id: 'FM8', what: 'an edge read without its attributes: a column for every step', catches: 'R11',
    mutate: (t) => swap(swap(t, '        if (!names.length) continue;\n', ''), '    for (const name of [...s.names].sort()) columns.push(',
      '    for (const name of [...s.names, \'\'].sort()) columns.push(') },
  { id: 'FM14', what: '+ Column\'s routes taken one way only', catches: 'R17',
    mutate: (t) => swap(t, "        for (const [direction, edges] of [['outgoing', index.out.get(at)], ['incoming', index.into.get(at)]]) {\n          for (const e of edges || []) {\n            const key",
      "        for (const [direction, edges] of [['outgoing', index.out.get(at)]]) {\n          for (const e of edges || []) {\n            const key") },
  { id: 'FM15', what: '+ Column offers no far node attribute', catches: 'R18',
    mutate: (t) => swap(t, '    for (const name of Object.keys(node.attributes || {})) names.node.add(name);\n', '') },
  { id: 'FM16', what: 'a numeral in a string judged a string', catches: 'R19',
    mutate: (t) => swap(t, ".map((v) => (numberOf(v) !== null ? 'number'", ".map((v) => (typeof v === 'number' ? 'number'") },
  { id: 'FM17', what: 'no delta of numerals in strings', catches: 'R19',
    mutate: (t) => swap(t, 'cell.values.length === 1 ? numberOf(cell.values[0]) : null)', "cell.values.length === 1 && typeof cell.values[0] === 'number' ? cell.values[0] : null)") },
  { id: 'FM23', what: 'a blank text reads as 0', catches: 'R24',
    // re-aimed (lead 10-13): numberOf reads a numeral by its rule now; a blank text past it is Number('') = 0
    mutate: (t) => swap(t, "if (typeof value !== 'string' || !NUMERAL.test(value.trim())) return null;", "if (typeof value !== 'string' || (value.trim() && !NUMERAL.test(value.trim()))) return null;") },
  { id: 'FM13', what: 'a row key read as an attribute', catches: 'R16',
    mutate: (t) => swap(t, "  if (value.on === 'key') return { value: (node.keys || {})[value.name], when: end.edge };\n", '') },
  { id: 'FM18', what: 'a node attribute timed by its first record, not the one saying its value', catches: 'R20',
    mutate: (t) => swap(t, '.find((s) => s && sameValue(s.value, said))', '.find((s) => s)') },
  { id: 'FM19', what: 'a node attribute timed by its way\'s last edge', catches: 'R20',
    mutate: (t) => swap(t, "  const when = ((node.attributes_by_world || {})[value.name] || []).find((s) => s && sameValue(s.value, said)) || null;",
      '  const when = end.edge;') },
  { id: 'FM20', what: 'a value the same as said only when it is the same object', catches: 'R21',
    mutate: (t) => swap(t, 'export const sameValue = (a, b) => JSON.stringify(a) === JSON.stringify(b);', 'export const sameValue = (a, b) => a === b;') },
  { id: 'FM9', what: 'a predicate taken both ways not told apart', catches: 'R12',
    mutate: (t) => swap(t, "${step.direction === 'incoming' ? '←' : '→'}", '→') },
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
