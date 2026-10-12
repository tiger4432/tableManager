#!/usr/bin/env node
// The walk's hubs as the screens read them (lead 10-12 · 10-13, task/WALK_HUB_ANSWER_SHAPE.md). The answers are the server
// hub branch's own: fixtures/walk_hub_answers.json.gz, written by its hub test's scenarios through its own helpers
// (fixtures/capture_walk_hubs.py says how to write it again) - the
// owner's example, the same walk opened, a contrast with two values, the walk with a typed cap, and four continued walks
// page by page with what the server's reference receiver (`_applied`) holds after them. The graph's hub cells are
// subgraph_view_harness's [HB] and [U].
//   node client2/tests/walk_hub_harness.mjs
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe, readSourceText } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const FIX = JSON.parse(gunzipSync(readFileSync(path.join(HERE, 'fixtures', 'walk_hub_answers.json.gz'))).toString('utf8'));
const { parseAst } = await import('rolldown/parseAst');

/** JSON with every object's keys sorted - the server's `json.dumps(sort_keys=True)`. */
const canon = (v) => JSON.stringify(v, (k, x) => (x && typeof x === 'object' && !Array.isArray(x)
  ? Object.fromEntries(Object.keys(x).sort().map((key) => [key, x[key]])) : x));
/** What a receiver holds, in the reference receiver's terms: nodes and edges by id, a node's page-local counts aside;
 *  each hub's rows by row id as column -> value. */
const PAGE_LOCAL = ['claim_count', 'predicates'];
function held(answer) {
  const nodes = Object.fromEntries((answer.nodes || []).map((n) => [n.id, Object.fromEntries(Object.entries(n).filter(([k]) => !PAGE_LOCAL.includes(k)))]));
  const edges = Object.fromEntries((answer.edges || []).map((e) => [e.id, e]));
  const tables = {};
  for (const [hub, t] of Object.entries(answer.tables || {})) {
    const at = t.columns.indexOf('id');
    const rows = Object.fromEntries(t.rows.map((r) => [r[at], Object.fromEntries(t.columns.map((c, i) => [c, r[i]]).filter(([, x]) => x !== null))]));
    if (Object.keys(rows).length) tables[hub] = rows;
  }
  return { nodes, edges, tables };
}
/** The reference's rows as this harness compares them (a cell the table did not hold is no cell). */
const reference = (applied) => ({ ...applied, tables: Object.fromEntries(Object.entries(applied.tables).map(([hub, rows]) =>
  [hub, Object.fromEntries(Object.entries(rows).map(([id, row]) => [id, Object.fromEntries(Object.entries(row).filter(([, x]) => x !== null))]))])) });

const { ids: ID, single: ONE_WALK } = FIX;
const OWNER = ONE_WALK.owner;
const name = (id) => (ONE_WALK.wafers_opened.nodes.find((n) => n.id === id) || {}).label;
const rowsOf = (answer, hub) => answer.tables[hub].rows.map((r) => Object.fromEntries(answer.tables[hub].columns.map((c, i) => [c, r[i]])));
// No capture holds a hub under a hub one row a row: the owner's defects cut to the first under each wafer.
const firstEach = (() => {
  const t = OWNER.tables[ID.defects];
  const at = t.columns.indexOf('parent_id');
  const seen = new Set();
  const rows = t.rows.filter((r) => !seen.has(r[at]) && seen.add(r[at]));
  return { ...OWNER, nodes: OWNER.nodes.map((n) => (n.id === ID.defects ? { ...n, count: rows.length, label: `defect ×${rows.length}` } : n)),
    tables: { ...OWNER.tables, [ID.defects]: { ...t, rows, count: rows.length } } };
})();
// ...and a next page that brings one more defect under the first wafer: one row two.
const oneMore = (() => {
  const t = OWNER.tables[ID.defects];
  const kept = new Set(firstEach.tables[ID.defects].rows.map((r) => r[t.columns.indexOf('id')]));
  const first = firstEach.tables[ID.defects].rows[0][t.columns.indexOf('parent_id')];
  const extra = t.rows.find((r) => !kept.has(r[t.columns.indexOf('id')]) && r[t.columns.indexOf('parent_id')] === first);
  const count = firstEach.tables[ID.defects].rows.length + 1;
  return { nodes: [{ ...OWNER.nodes.find((n) => n.id === ID.defects), count, label: `defect ×${count}` }],
    edges: [], tables: { [ID.defects]: { ...t, rows: [extra], count: 1 } } };
})();
// No capture holds a hub of one: the owner's wafers hub cut to its first member.
const ofOne = { ...OWNER, nodes: OWNER.nodes.filter((n) => n.depth <= 1).map((n) => (n.id === ID.wafers ? { ...n, count: 1 } : n)),
  edges: OWNER.edges.filter((e) => e.target === ID.wafers).map((e) => ({ ...e, count: 1 })),
  tables: { [ID.wafers]: { ...OWNER.tables[ID.wafers], rows: [OWNER.tables[ID.wafers].rows[0]], count: 1 } } };

/** Every client source's member reads and property keys of one name, by the parser the bundler uses (not text). */
function readersOf(key, mutate) {
  const files = [];
  const walk = (dir) => {
    for (const f of readdirSync(dir)) {
      const p = path.join(dir, f);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.m?js$/.test(f)) files.push(p);
    }
  };
  walk(SRC);
  let members = 0;
  const hits = [];
  for (const file of files) {
    const own = readSourceText(file).text;
    const text = mutate ? mutate(path.relative(SRC, file).split(path.sep).join('/'), own) : own;
    const visit = (n) => {
      if (!n || typeof n !== 'object') return;
      if (Array.isArray(n)) { n.forEach(visit); return; }
      if (n.type === 'MemberExpression') {
        members += 1;
        const said = !n.computed && n.property && n.property.type === 'Identifier' ? n.property.name
          : n.property && n.property.type === 'Literal' ? n.property.value : null;
        if (said === key) hits.push(path.relative(SRC, file));
      }
      if (n.type === 'Property' && n.key && (n.key.name || n.key.value) === key) hits.push(path.relative(SRC, file));
      for (const k of Object.keys(n)) if (k !== 'type' && n[k] && typeof n[k] === 'object') visit(n[k]);
    };
    visit(parseAst(text, { lang: 'js' }));
  }
  return { files: files.length, members, hits };
}

async function measure(mutate = {}) {
  const { module: tv } = await loadWithProbe(path.join(SRC, 'walk', 'table_view.js'), { expose: ['applyPage'], mutate: mutate['table_view.js'] });
  const { module: dv } = await loadWithProbe(path.join(SRC, 'walk', 'derive.js'), { mutate: mutate['derive.js'] });
  const { module: api } = await loadWithProbe(path.join(SRC, 'rnd_board', 'api.js'), { mutate: mutate['api.js'] });
  const out = {};
  out.pages = FIX.paged.map((s) => {
    const got = s.pages.reduce((was, page) => tv.applyPage(was, page), { nodes: [], edges: [] });
    return [s.name, canon(held(got)) === canon(reference(s.applied))];
  });
  // The wire: every page of every continued walk, and the owner's answer with a bundles key beside its hubs.
  const wired = async (body) => api.createWalkBoxWalk({ apiBase: '', fetchImpl: async () => ({ ok: true, status: 200, json: async () => body }) })({ positive: [ID.lot] });
  const pass = (got, body) => ['tables', 'left', 'moved', 'edges_pending'].every((k) => canon(got[k] || null) === canon(body[k] || null))
    && canon(got.nodes.filter((n) => n.hub)) === canon((body.nodes || []).filter((n) => n.hub))
    && canon(got.edges.filter((e) => 'count' in e)) === canon((body.edges || []).filter((e) => 'count' in e));
  out.wire = [];
  for (const s of FIX.paged) for (const page of s.pages) out.wire.push(pass(await wired(page), page));
  const withBundles = await wired({ ...OWNER, bundles: [{ node: ID.lot, predicate: 'has_wafer', direction: 'outgoing', far_type: 'wafer', count: 3, drawn: 0 }] });
  out.noBundles = !('bundles' in withBundles) && pass(withBundles, OWNER);
  // The table: the owner's example and the contrast, a section each - its head, its sides, its heads, its rows.
  const sections = (answer, starts) => tv.walkTableView({ ok: true, ...answer }, [], [], undefined, starts).sections
    .map((s) => [s.heading, s.groups.map((g) => `${g.sign}${g.count}`).join(' '), s.centreHeads.join(' | '),
      s.rows.map((r) => r.centre.map((c) => c.text).join(' / ')).sort().join(' ; ')]);
  out.owner = sections(OWNER, { positive: [ID.lot], negative: [] });
  out.contrast = sections(ONE_WALK.contrast, { positive: [ID.P], negative: [ID.N] });
  // One defect under each wafer: the wafers' columns; a page that brings a second under one: a section of its own.
  out.oneEach = sections(firstEach, { positive: [ID.lot], negative: [] });
  out.oneMore = sections(tv.applyPage({ ...firstEach, edges: firstEach.edges }, oneMore), { positive: [ID.lot], negative: [] });
  // A hub of one: its member, a row of its type, the edge to it run to it.
  const asMember = dv.oneMemberHubs(ofOne);
  const member = rowsOf(ofOne, ID.wafers)[0].id;
  out.ofOne = { node: asMember.nodes.filter((n) => n.depth === 1).map((n) => [n.id === member, n.type, n.label, n.hubOf === ID.wafers]),
    edges: asMember.edges.map((e) => e.target === member), table: sections(ofOne, { positive: [ID.lot], negative: [] }) };
  // A lump of the picture opened as a table (lead 10-11 E2b) holding a hub: the wafers hub's branch, the defects hub.
  const { module: fv } = await loadWithProbe(path.join(SRC, 'walk', 'fold_views.js'), { mutate: mutate['fold_views.js'] });
  const lumped = fv.lumpAnswer([OWNER], { owner: ID.wafers, members: [ID.defects], predicate: 'observed' });
  out.lumpTable = sections(lumped, { positive: [ID.wafers], negative: [] }).map((s) => s[0]);
  // No client source reads an answer's `bundles`; the parser reads members, and the hubs' own key is read.
  const bundles = readersOf('bundles', mutate.census);
  const tables = readersOf('tables');
  out.census = { files: bundles.files > 100, members: bundles.members > 1000, bundles: bundles.hits, tablesRead: tables.hits.length > 0 };
  return out;
}

const W = (ids) => ids.map(name);
const cells = (o) => [
  ['H1 a continued walk\'s pages laid over each other by id hold what the server\'s reference receiver holds - moved, left, a head of count 0 gone with its table, each hub\'s rows (four walks)',
    o.pages, FIX.paged.map((s) => [s.name, true])],
  ['H2 the wire carries every page as the server sent it - the hubs, their counts, their tables, what left, what moved, the edges read first - and no bundles, a bundles key beside them or not',
    [o.wire.every(Boolean) && o.wire.length === FIX.paged.reduce((n, s) => n + s.pages.length, 0), o.noBundles], [true, true]],
  ['H3 the table: the types\' sections, then a section a hub - its mark and head, its sides its value, a row a member by name; the defects under the wafers their own section with the wafer each hangs from',
    [o.owner, o.contrast.slice(-3)], [[
      ['lot · 1', '+1', 'lot', 'L'],
      ['kind · 2', '+2', 'kind', 'K0 ; K1'],
      ['▤ wafer ×3 · L has_wafer →', '+3', 'wafer', W(rowsOf(OWNER, ID.wafers).map((r) => r.id)).sort().join(' ; ')],
      ['▤ defect ×6 · wafer ×3 observed →', '+6', 'defect | wafer',
        rowsOf(OWNER, ID.defects).map((r) => `${name(r.id)} / ${name(r.parent_id)}`).sort().join(' ; ')]],
    ONE_WALK.contrast.nodes.filter((n) => n.hub).map((h) => [`▤ ${h.label} · ${ONE_WALK.contrast.nodes.find((n) => n.id === h.hub.near).label} has_wafer →`,
      `+${h.value[0] ? 2 : 0} −${h.value[1] ? 2 : 0}`, 'wafer', rowsOf(ONE_WALK.contrast, h.id).map((r) => nameOfAny(r.id)).sort().join(' ; ')])]],
  ['H4 a hub under a hub one row a row is that hub\'s columns, no section of its own; a page that brings a second under one row makes it a section again (lead 10-13 Q2)',
    [o.oneEach.map((s) => s[0]), o.oneEach.find((s) => s[0].startsWith('▤ wafer')).slice(2), o.oneMore.map((s) => s[0])],
    [['lot · 1', 'kind · 2', '▤ wafer ×3 · L has_wafer →'], ['wafer | observed → defect',
      rowsOf(firstEach, ID.defects).map((r) => `${name(r.parent_id)} / ${name(r.id)}`).sort().join(' ; ')],
      ['lot · 1', 'kind · 2', '▤ wafer ×3 · L has_wafer →', '▤ defect ×4 · wafer ×3 observed →']]],
  ['H5 a hub of one is its member: the node its row\'s, by name, the hub id held; the edge to it run to it; in the table a row of its type, no hub section',
    o.ofOne, { node: [[true, 'wafer', name(rowsOf(ofOne, ID.wafers)[0].id), true]], edges: [true],
      table: [['lot · 1', '+1', 'lot', 'L'], ['wafer · 1', '+1', 'wafer', name(rowsOf(ofOne, ID.wafers)[0].id)]] }],
  ['H7 a lump of the picture holding a hub, opened as a table: its owner and its member, hubs both, keep their tables - a section each',
    o.lumpTable, ['▤ wafer ×3 · L has_wafer →', '▤ defect ×6 · wafer ×3 observed →']],
  ['H6 no client source reads an answer\'s bundles - its member nor a key of that name - while the parser reads every file and the hubs\' tables are read',
    o.census, { files: true, members: true, bundles: [], tablesRead: true }],
];
// A member no answer sends as a node, by its keys - read off its id here by Node's own base64url, not the client's reader.
function nameOfAny(id) {
  const [, keys] = JSON.parse(Buffer.from(String(id).split(':').pop(), 'base64url').toString('utf8'));
  return Object.values(keys).join(' / ');
}

const DEFECTS = [
  ['D1 moved rows left where they were -> H1', 'H1', { 'table_view.js': (t) => t.replace('    if (cells) rowsOf(rows, to).set(row, cells);\n', '') }],
  ['D2 a row that left its hub kept in its table -> H1', 'H1', { 'table_view.js': (t) => t.replace(
    '  for (const [hub, row] of page.left || []) if (rows.has(hub)) rows.get(hub).delete(row);\n', '') }],
  ['D3 a head of count 0 drawn as a node -> H1', 'H1', { 'table_view.js': (t) => t.replace(
    '    if (gone(node)) { nodes.delete(node.id); rows.delete(node.id); } else nodes.set(node.id, node);', '    nodes.set(node.id, node);') }],
  // ⚠️ No mutant for the order itself: in the server's answers no page brings a row both in its tables and in its own
  //    moved or left, so the order changes nothing on them - a vector the server does not send would only test this file.
  ['D4 the wire drops the hubs\' tables -> H2', 'H2', { 'api.js': (t) => t.replace('        tables: body.tables || null,\n', '        tables: null,\n') }],
  ['D5 the wire carries the bundles on -> H2', 'H2', { 'api.js': (t) => t.replace('        tables: body.tables || null,\n',
    '        tables: body.tables || null,\n        bundles: body.bundles,\n') }],
  ['D6 a hub\'s head a row of its type -> H3', 'H3', { 'table_view.js': (t) => t.replace(
    'const members = nodes.filter((n) => !n.hub && groups.some(', 'const members = nodes.filter((n) => groups.some(') }],
  ['D7 a hub\'s sides every row, not its value -> H3', 'H3', { 'table_view.js': (t) => t.replace(
    'count: groups.length > 1 && head.value ? (head.value[i] ? rows.length : 0) : rows.length', 'count: rows.length') }],
  ['D8 a hub under a hub without the row it hangs from -> H3', 'H3', { 'table_view.js': (t) => t.replace(
    '...(above ? [{ text: nodeWords(r.parent_id) }] : [])', '...[]') }],
  ['D9 a hub one row a row never the columns -> H4', 'H4', { 'table_view.js': (t) => t.replace(
    'const asColumns = new Set(heads.filter(oneEach).map((n) => n.id));', 'const asColumns = new Set();') }],
  ['D10 the columns kept when a row holds two -> H4', 'H4', { 'table_view.js': (t) => t.replace(
    'return under.length === above.size && new Set(under).size === under.length && under.every((p) => above.has(p));',
    'return under.every((p) => above.has(p));') }],
  ['D11 the edge to a hub of one left on the hub -> H5', 'H5', { 'derive.js': (t) => t.replace(
    '.map((e) => ({ ...e, source: end(e.source), target: end(e.target) }))', '') }],
  ['D12 the table reads a hub of one as a hub -> H5', 'H5', { 'table_view.js': (t) => t.replace(
    '  const result = oneMemberHubs(given);\n', '  const result = given;\n') }],
  ['D14 a lump\'s answer drops its hubs\' tables -> H7', 'H7', { 'fold_views.js': (t) => t.replace(
    '    ...(Object.keys(tables).length ? { tables } : {}) };', '  };') }],
  ['D13 a source reads an answer\'s bundles -> H6', 'H6', { census: (file, t) => (file === 'walk/main.js' ? `${t}\nexport const held = (answer) => answer.bundles;\n` : t) }],
];

const eqText = (a, b) => JSON.stringify(a) === JSON.stringify(b);
let pass = 0;
let fail = 0;
const failed = [];
console.log('-- walk hubs ---------------------------------------------------------');
const base = await measure();
for (const [label, got, want] of cells(base)) {
  const ok = eqText(got, want);
  console.log(`  ${ok ? 'PASS' : 'FAIL'} ${label}${ok ? '' : `\n        got  ${JSON.stringify(got)}\n        want ${JSON.stringify(want)}`}`);
  if (ok) pass += 1; else { fail += 1; failed.push(label); }
}
console.log('');
console.log('-- defect mutants (each must be caught by the check it names) ------');
let escaped = 0;
for (const [label, names, edits] of DEFECTS) {
  const guarded = Object.fromEntries(Object.entries(edits).map(([file, edit]) => [file, file === 'census' ? edit : (text) => {
    const out = edit(text);
    if (out === text) throw new Error(`mutant «${label}» changed nothing in ${file} - its anchor is gone`);
    return out;
  }]));
  let caught;
  try {
    const got = await measure(guarded);
    caught = cells(got).some(([n, g, w]) => n.startsWith(names) && !eqText(g, w));
  } catch (err) {
    if (/its anchor is gone/.test(String(err && err.message))) throw err;
    caught = false;
    console.log(`        threw: ${err && err.message}`);
  }
  if (!caught) escaped += 1;
  console.log(`  ${caught ? 'caught ' : 'ESCAPED'} ${label}`);
}
console.log('');
console.log(`${pass} passed, ${fail} failed; ${DEFECTS.length - escaped}/${DEFECTS.length} defects caught.`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
if (fail) console.log(`FAILED: ${failed.join(' | ')}`);
if (fail || escaped) process.exitCode = 1;
