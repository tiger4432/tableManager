// The chain graph seated on a stub document, and the tree it draws, serialised - shared by
// capture_graph_snapshots.mjs (which pinned the picture before the template, lead 65754c39a) and the
// harness that compares today's drawing with it. One seat for both, so the capture and the check cannot
// set the screen up differently. The subgraph viewer left the template for Cytoscape (lead 5e1d9e372); its
// seat stays for the two-parts-on-one-page check.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { makeDoc } from './board_dom.mjs';
import { createWalkBoxWalk, entitySeedId } from '../../src/rnd_board/api.js';
import { MarkingStore, SIGN } from '../../src/rnd_board/marking_store.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const fx = (name) => JSON.parse(readFileSync(path.join(HERE, '..', 'fixtures', name), 'utf8'));

/** A node as data: tag, its attributes sorted, its class and own text, its children - nothing else. */
export function snapshot(node) {
  const attrs = {};
  for (const key of Object.keys(node.attrs || {}).sort()) attrs[key] = node.attrs[key];
  return {
    tag: String(node.tagName || ''),
    cls: String(node.className || ''),
    attrs,
    text: String(node._text || ''),
    children: (node.children || []).map(snapshot),
  };
}

/** Every flag the chain picture draws differently: dim, opt-in, undeclared, ledger, synthesized, cycle,
 *  declared self-update, counts, a contested cell and a sentence-shaped cycle. */
export const CHAIN_PAYLOAD = Object.freeze({
  nodes: [
    { id: 'raw_log', label: 'raw_log', wakes: ['dt_log'] },
    { id: 'eqp_log', label: 'eqp_log', declared: false, wakes: ['dt_log'] },
    { id: 'dt_log', label: 'dt_log', wakes: ['dt_job_attribution', 'dt_inventory'] },
    { id: 'dt_job_attribution', label: 'dt_job_attribution', opt_in: true, wakes: [] },
    { id: 'dt_inventory', label: 'dt_inventory', enabled: false, wakes: [] },
    { id: 'loop_a', label: 'loop_a', wakes: ['loop_b'] },
    { id: 'loop_b', label: 'loop_b', wakes: ['loop_a'] },
    { id: 'ledger', label: 'ledger', kind: 'ledger', wakes: [] },
  ],
  edges: [
    { from: 'raw_log', to: 'dt_log', kind: 'mapper', rule: 'r1', origin: 'file' },
    { from: 'eqp_log', to: 'dt_log', kind: 'mapper', rule: 'enrichment_auto_confirm:x', origin: 'synthesized:x' },
    { from: 'dt_log', to: 'dt_job_attribution', kind: 'enrich' },
    { from: 'dt_log', to: 'dt_inventory', kind: 'vjoin', enabled: false },
    { from: 'loop_a', to: 'loop_b', kind: 'mapper' },
    { from: 'loop_b', to: 'loop_a', kind: 'mapper' },
    { from: 'dt_job_attribution', to: 'ledger', kind: 'ledger' },
    { from: 'dt_log', to: 'nowhere', kind: 'odd' },
    { from: 'raw_log', to: 'ledger', kind: 'odd' },
  ],
  cycles: [['loop_a', 'loop_b'], 'a cycle the validator named in a sentence'],
  declared_self_updates: [['dt_inventory'], 'dt_inventory updates itself by declaration'],
  counts: { tables: 8, rules: 7, contested: 1 },
  contested: [{ table: 'dt_log', column: 'wafer', writers: ['r1', 'r2'] }],
});

/** The chain graph as the admin page seats it, then one table picked. */
export function seatChain(ChainGraphPanel) {
  const doc = makeDoc('light');
  const host = doc.createElement('div');
  doc.body.appendChild(host);
  const panel = new ChainGraphPanel(host, { doc });
  panel.render(CHAIN_PAYLOAD);
  panel.select('dt_log');
  return host;
}

const wire = (bodies) => {
  let i = 0;
  return createWalkBoxWalk({
    apiBase: '',
    fetchImpl: async () => {
      const body = bodies[Math.min(i, bodies.length - 1)];
      i += 1;
      return { ok: true, status: 200, json: async () => body };
    },
  });
};

/** The subgraph viewer on the walk page's chain of names, the die walk drawn: its host and the part. */
export async function seatSubgraph(SubgraphView) {
  const DECL = fx('walk_start_declaration.json');
  const bodies = [fx('walk_start_die.json')];
  const doc = makeDoc('light');
  const host = doc.createElement('div');
  doc.body.appendChild(host);
  const markings = new MarkingStore();
  const chain = ['walk-start', 'walk-2', 'walk-3', 'walk-4'];
  const first = bodies[0];
  const start = first._start ? entitySeedId(first._start.type, first._start.keys) : first.seed.id;
  markings.replace(chain[0], [[start, SIGN.CASE]]);
  const view = new SubgraphView(host, { doc, walk: wire(bodies), entities: () => DECL.entities, markings, chain: (k) => chain[k] || '' });
  await view.show();
  return { host, view };
}
