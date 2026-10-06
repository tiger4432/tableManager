// Pins the chain graph's picture as the part draws it, so the one-template round (lead 65754c39a) can show
// 「오늘 그림은 그대로」 byte for byte. The subgraph viewer left the template for Cytoscape (lead 5e1d9e372).
// Run: node client2/tests/fixtures/capture_graph_snapshots.mjs   - only on code whose pictures are the
// ones to keep; the harness compares every later drawing against this file.
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { snapshot, seatChain } from '../lib/graph_seats.mjs';
import { ChainGraphPanel } from '../../src/chain_graph.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const out = {
  _what: `The tree ChainGraphPanel drew on the stub document, captured ${new Date().toISOString()}`
    + ' by capture_graph_snapshots.mjs. Never edit by hand.',
  chain: snapshot(seatChain(ChainGraphPanel)),
};
writeFileSync(path.join(HERE, 'graph_snapshots.json'), JSON.stringify(out));
const count = (tree) => 1 + tree.children.reduce((n, c) => n + count(c), 0);
for (const key of Object.keys(out).filter((k) => !k.startsWith('_'))) console.log(key, count(out[key]), 'elements');
