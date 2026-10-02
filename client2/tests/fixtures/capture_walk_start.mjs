// Captures the fixtures `subgraph_view_harness` reads: the declaration and two start-only walks, as the
// server sends them, through the page's own wire (`createWalkBoxWalk` with nothing but a start).
// Run against a box API: node client2/tests/fixtures/capture_walk_start.mjs [apiBase]
// Never edit the JSON by hand - re-run this.
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createWalkBoxWalk, fetchKeyValues } from '../../src/rnd_board/api.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const apiBase = process.argv[2] || 'http://localhost:8080';
const stamp = new Date().toISOString();

const declRes = await fetch(`${apiBase}/api/ledger/declaration`);
const decl = await declRes.json();
writeFileSync(path.join(HERE, 'walk_start_declaration.json'), JSON.stringify({
  _what: `REAL server output. GET /api/ledger/declaration on a box API, captured ${stamp} by capture_walk_start.mjs.`,
  ...decl,
}));

// The first subject the key list offers for each type; the walk carries the start and nothing else.
for (const [type, file] of [['wafer', 'walk_start_wafer.json'], ['die', 'walk_start_die.json']]) {
  const kv = await fetchKeyValues({ apiBase, type, limit: 1 });
  const keys = kv.ok && kv.nodes.length ? kv.nodes[0].keys : null;
  if (!keys) throw new Error(`no ${type} subject to start from`);
  let url = '';
  let body = null;
  const fetchImpl = async (u, init) => {
    url = String(u);
    const res = await fetch(u, init);
    body = await res.clone().json();
    return res;
  };
  const got = await createWalkBoxWalk({ apiBase, fetchImpl })({ type, keys });
  if (!got.ok) throw new Error(`${type} walk refused: ${got.message}`);
  writeFileSync(path.join(HERE, file), JSON.stringify({
    _what: `REAL server output. ${url.replace(apiBase, '')} (start ${type} ${JSON.stringify(keys)}, nothing else), `
      + `captured ${stamp} by capture_walk_start.mjs.`,
    _start: { type, keys },
    ...body,
  }));
  console.log(type, JSON.stringify(keys), 'nodes', got.nodes.length, 'edges', got.edges.length);
  if (type !== 'die') continue;
  // The second step: a marking of one node the die walk reached (its first defect two steps out), walked as the
  // viewer's Continue walks it - the marking's signed ids - with node_limit 30 so the fixture stays small
  // (the viewer itself sends no budget; this file pins the merge, not the budget).
  // Two or more steps out, so a second step that does not carry on from it would be drawn elsewhere.
  const marked = got.nodes.find((n) => String(n.type).split('@')[0] === 'defect' && n.depth >= 2);
  if (!marked) throw new Error('the die walk reached no defect to mark');
  let stepUrl = '';
  let stepBody = null;
  const stepFetch = async (u, init) => {
    stepUrl = String(u);
    const res = await fetch(u, init);
    stepBody = await res.clone().json();
    return res;
  };
  const step = await createWalkBoxWalk({ apiBase, fetchImpl: stepFetch })({ positive: [marked.id], negative: [], node_limit: 30 });
  if (!step.ok) throw new Error(`step walk refused: ${step.message}`);
  writeFileSync(path.join(HERE, 'walk_start_die_step2.json'), JSON.stringify({
    _what: `REAL server output. ${stepUrl.replace(apiBase, '')} (a marking of ${marked.id} from walk_start_die.json), `
      + `captured ${stamp} by capture_walk_start.mjs.`,
    _marked: marked.id,
    ...stepBody,
  }));
  console.log('step 2 from', marked.label, 'nodes', step.nodes.length, 'edges', step.edges.length);
}
