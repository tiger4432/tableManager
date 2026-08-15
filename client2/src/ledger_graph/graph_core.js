const list = (value) => Array.isArray(value) ? value : [];

export function readGraph(body) {
  const source = body && typeof body === 'object' ? body : {};
  const nodes = list(source.nodes).filter((n) => n && n.id).map((n) => ({
    ...n,
    id: String(n.id), type: String(n.type || 'Unknown'),
    label: String(n.label || n.id), keys: n.keys && typeof n.keys === 'object' ? n.keys : {},
    depth: Number.isFinite(Number(n.depth)) ? Number(n.depth) : null,
    claim_count: Number(n.claim_count || 0), predicates: list(n.predicates),
  }));
  const ids = new Set(nodes.map((n) => n.id));
  const edges = list(source.edges).filter((e) => e && e.id && ids.has(String(e.source)) && ids.has(String(e.target))).map((e) => ({
    ...e, id: String(e.id), source: String(e.source), target: String(e.target),
    predicate: String(e.predicate || 'related'), witnesses: Number(e.witnesses || 0),
    rank: Number.isFinite(Number(e.rank)) ? Number(e.rank) : null,
  }));
  return {
    state: String(source.state || 'unknown'), nodes, edges,
    seedId: source.seed && source.seed.id ? String(source.seed.id) : (nodes[0]?.id || ''),
    walk: source.walk || {}, truncated: source.truncated || {},
    message: String(source.message || ''), generatedAt: String(source.generated_at || ''),
  };
}

const claimTargetId = (edge) => `claim-shape:${edge.subject_type || edge.source}:${edge.predicate}:${edge.object_kind || 'none'}`;

export function readStructure(body) {
  const source = body && typeof body === 'object' ? body : {};
  const graph = source.graph && typeof source.graph === 'object' ? source.graph : {};
  const rawEdges = list(graph.edges).filter((edge) => edge && edge.id && edge.source);
  const predicateCounts = new Map();
  for (const edge of rawEdges) {
    if (!predicateCounts.has(String(edge.source))) predicateCounts.set(String(edge.source), []);
    predicateCounts.get(String(edge.source)).push({
      predicate: String(edge.predicate || 'related'),
      count: Number(edge.atoms || 0),
      label: String(edge.predicate_label || edge.predicate || 'related'),
    });
  }
  const nodes = list(graph.nodes).filter((node) => node && node.id).map((node) => ({
    ...node,
    id: String(node.id),
    type: String(node.type || 'Unknown'),
    label: String(node.label || node.id),
    keys: { identity_keys: list(node.keys).join(', ') || '없음' },
    depth: null,
    claim_count: Number(node.atoms_as_subject || 0),
    predicates: predicateCounts.get(String(node.id)) || [],
    schema_kind: 'entity_type',
  }));
  const ids = new Set(nodes.map((node) => node.id));
  for (const edge of rawEdges) {
    if (edge.target && ids.has(String(edge.target))) continue;
    const id = claimTargetId(edge);
    if (ids.has(id)) continue;
    const kind = String(edge.object_kind || 'none');
    nodes.push({
      id,
      type: kind === 'value' ? 'Value' : kind === 'event_ref' ? 'Event' : 'Empty',
      label: `${edge.predicate_label || edge.predicate} ${kind === 'value' ? '값' : kind === 'event_ref' ? '사건' : '목적어 없음'}`,
      keys: { fields: list(edge.object_fields).join(', ') || '없음' },
      depth: null,
      claim_count: Number(edge.atoms || 0),
      predicates: [],
      schema_kind: 'claim_shape',
      object_kind: edge.object_kind ?? null,
      object_fields: list(edge.object_fields),
    });
    ids.add(id);
  }
  const edges = rawEdges.map((edge) => ({
    ...edge,
    id: String(edge.id),
    source: String(edge.source),
    target: edge.target && ids.has(String(edge.target)) ? String(edge.target) : claimTargetId(edge),
    predicate: String(edge.predicate || 'related'),
    predicateLabel: String(edge.predicate_label || edge.predicate || 'related'),
    witnesses: Number(edge.atoms || 0),
    rank: null,
    sourceRows: list(edge.sources),
  })).filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  const seed = nodes.filter((node) => node.schema_kind === 'entity_type')
    .sort((a, b) => b.claim_count - a.claim_count || a.id.localeCompare(b.id))[0];
  return {
    state: String(source.state || 'unknown'),
    nodes,
    edges,
    seedId: seed?.id || nodes[0]?.id || '',
    walk: {},
    truncated: {},
    message: '',
    generatedAt: String(source.generated_at || ''),
    mode: 'ontology',
    cost: source.cost || {},
    drift: source.drift || {},
    window: source.window || {},
  };
}

export function filterGraph(model, filters = {}) {
  const text = String(filters.text || '').trim().toLowerCase();
  const types = filters.types instanceof Set ? filters.types : new Set();
  const predicates = filters.predicates instanceof Set ? filters.predicates : new Set();
  const visibleNodes = model.nodes.filter((node) => {
    if (types.size && !types.has(node.type)) return false;
    if (!text) return true;
    const haystack = `${node.type} ${node.label} ${JSON.stringify(node.keys)}`.toLowerCase();
    return haystack.includes(text);
  });
  const nodeIds = new Set(visibleNodes.map((n) => n.id));
  let edges = model.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));
  if (predicates.size) edges = edges.filter((edge) => predicates.has(edge.predicate));
  if (text) {
    const touching = new Set();
    for (const edge of model.edges) {
      if (edge.predicate.toLowerCase().includes(text)) {
        touching.add(edge.source); touching.add(edge.target);
      }
    }
    for (const node of model.nodes) {
      if (touching.has(node.id) && (!types.size || types.has(node.type)) && !nodeIds.has(node.id)) {
        visibleNodes.push(node); nodeIds.add(node.id);
      }
    }
    edges = model.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)
      && (!predicates.size || predicates.has(edge.predicate)));
  }
  const seedId = visibleNodes.some((node) => node.id === model.seedId)
    ? model.seedId : (visibleNodes[0]?.id || '');
  return { ...model, nodes: visibleNodes, edges, seedId };
}

export function subgraphFrom(model, startId, hops = 20) {
  const start = String(startId || '');
  if (!start || !model.nodes.some((node) => node.id === start)) return model;
  const cap = Math.max(0, Math.min(20, Number(hops) || 0));
  const adjacency = new Map();
  const link = (a, b) => {
    if (!adjacency.has(a)) adjacency.set(a, new Set());
    adjacency.get(a).add(b);
  };
  for (const edge of model.edges) { link(edge.source, edge.target); link(edge.target, edge.source); }
  const depth = new Map([[start, 0]]);
  const queue = [start];
  while (queue.length) {
    const current = queue.shift();
    if (depth.get(current) >= cap) continue;
    for (const next of adjacency.get(current) || []) if (!depth.has(next)) {
      depth.set(next, depth.get(current) + 1); queue.push(next);
    }
  }
  const nodes = model.nodes.filter((node) => depth.has(node.id));
  const ids = new Set(nodes.map((node) => node.id));
  const edges = model.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  return { ...model, nodes, edges, seedId: start, focusDepth: depth };
}

export function radialLayout(model) {
  const adjacency = new Map();
  const add = (a, b) => {
    if (!adjacency.has(a)) adjacency.set(a, new Set());
    adjacency.get(a).add(b);
  };
  for (const edge of model.edges) { add(edge.source, edge.target); add(edge.target, edge.source); }
  const depth = new Map([[model.seedId, 0]]);
  const queue = model.seedId ? [model.seedId] : [];
  while (queue.length) {
    const id = queue.shift();
    const neighbors = [...(adjacency.get(id) || [])].sort();
    for (const next of neighbors) if (!depth.has(next)) {
      depth.set(next, depth.get(id) + 1); queue.push(next);
    }
  }
  const maxDepth = Math.max(0, ...depth.values());
  const detachedDepth = maxDepth + 1;
  const rings = [];
  for (const node of model.nodes) {
    const d = depth.has(node.id) ? depth.get(node.id) : detachedDepth;
    if (!rings[d]) rings[d] = [];
    rings[d].push(node);
  }
  const positions = new Map();
  if (model.seedId) positions.set(model.seedId, { x: 0, y: 0, depth: 0 });
  let previousRadius = 0;
  for (let d = 1; d < rings.length; d += 1) {
    const ring = (rings[d] || []).sort((a, b) => `${a.type}|${a.label}|${a.id}`.localeCompare(`${b.type}|${b.label}|${b.id}`));
    if (!ring.length) continue;
    const radius = Math.max(previousRadius + 155, (ring.length * 92) / (2 * Math.PI));
    previousRadius = radius;
    const step = (Math.PI * 2) / ring.length;
    ring.forEach((node, index) => {
      const angle = (-Math.PI / 2) + (index * step) + (d % 2 ? 0 : step / 2);
      positions.set(node.id, { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius, depth: d });
    });
  }
  return positions;
}

export function edgeCurves(edges) {
  const groups = new Map();
  for (const edge of edges) {
    const key = edge.source < edge.target ? `${edge.source}|${edge.target}` : `${edge.target}|${edge.source}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(edge);
  }
  const result = new Map();
  for (const group of groups.values()) {
    group.sort((a, b) => a.id.localeCompare(b.id)).forEach((edge, index) => {
      if (index === 0) result.set(edge.id, 0);
      else result.set(edge.id, Math.ceil(index / 2) * 28 * (index % 2 ? 1 : -1));
    });
  }
  return result;
}
