// Pins the two layered-graph pictures (chain graph · subgraph viewer) as the parts draw them, so the
// one-template round (lead 65754c39a) can show 「두 화면의 오늘 그림은 그대로」 byte for byte.
// Run: node client2/tests/fixtures/capture_graph_snapshots.mjs   - only on code whose pictures are the
// ones to keep; the harness compares every later drawing against this file.
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { snapshot, seatChain, seatSubgraph } from '../lib/graph_seats.mjs';
import { ChainGraphPanel } from '../../src/chain_graph.js';
import { SubgraphView } from '../../src/walk/subgraph_view.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const out = {
  _what: `The trees ChainGraphPanel and SubgraphView drew on the stub document, captured ${new Date().toISOString()}`
    + ' by capture_graph_snapshots.mjs. Never edit by hand.',
  chain: snapshot(seatChain(ChainGraphPanel)),
  subgraph_die: snapshot(await seatSubgraph(SubgraphView, 'die')),
  subgraph_continue: snapshot(await seatSubgraph(SubgraphView, 'continue')),
  subgraph_bundles: snapshot(await seatSubgraph(SubgraphView, 'bundles')),
};
writeFileSync(path.join(HERE, 'graph_snapshots.json'), JSON.stringify(out));
const count = (tree) => 1 + tree.children.reduce((n, c) => n + count(c), 0);
for (const key of Object.keys(out).filter((k) => !k.startsWith('_'))) console.log(key, count(out[key]), 'elements');
