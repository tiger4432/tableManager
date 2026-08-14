// ============================================================
// ontology_structure_core.js — the TYPE-LEVEL structure of the ledger, as a model.
//
// PURE. No DOM, no network, no `window`. It runs under bare node, which is why
// `tests/ontology_structure_harness.mjs` can drive it directly — same contract as
// `ledger_trace_core.js` and `case_control_core.js`.
//
// 🔴 WHAT THIS SCREEN ANSWERS (product owner, 2026-08-14, SCENARIO_CONSOLE_BRIEF
// §0-quater): "지금 너무 구조가 숨겨져 있어서 UI 어떻게 설계해야 할지 모르겠어."
// Not a history graph — a TYPE graph. Which subject types are joined to which
// object kinds by which predicate, HOW MUCH data is on each of those joins, over
// WHAT period, and at WHICH resolution grade. The axis that carries data and the
// axis that is only declared have to be distinguishable at a glance, because that
// difference is the thing the owner cannot currently see.
//
// 🔴 NOTHING IN THIS FILE IS A DRAWING. There is no node list and no edge list
// here, and adding one would be the failure condition the brief states outright
// ("하드코딩된 노드/엣지 목록이 보이면 실패"). Every node and every edge is
// DERIVED, twice over:
//
//   the DECLARED skeleton   from the vocabulary's own signatures — for each
//                           predicate, the cross product of its declared subject
//                           types with its declared object kind. A predicate
//                           registered tomorrow draws itself.
//   the OBSERVED weight     from the ledger's `GROUP BY subject_type, predicate,
//                           object_kind` — count, period, grade distribution.
//
// The union is the graph. An edge in the skeleton with no rows renders as
// 「선언됨 · 데이터 0」 and is NEVER dropped (brief: "건수 0인 선언 엣지는 숨기지
// 말고"), because a hidden axis is one the owner cannot know exists. An edge in
// the rows with no declaration renders as 「미선언」, which is a finding about the
// gate rather than a rendering detail.
//
// The only literals here are LABEL MAPS FOR CLOSED WIRE ENUMS (the four
// resolution classes of `server/ledger_trace.py::CLASS_NAMES`, the three object
// kinds of `vocabulary.OBJECT_KINDS`, the two layers). They translate a word the
// server already sent; they never decide which words exist. An enum member this
// file has never heard of renders under its raw wire spelling rather than
// vanishing — that is the test of the difference.
//
// ------------------------------------------------------------
// 🔴 TWO SHAPES, AND THE READER SAYS WHICH ONE IT GOT (P0, 2026-08-14).
//
// The screen shipped against a PROPOSED flat shape that was never served. What
// `server/ledger_structure.py` actually answers nests the same facts one level
// down, and reading the flat keys against it yielded four empty arrays, no throw,
// and a frame that announced 「원장 가동 — 아래 숫자는 실측입니다」 over nothing.
// THAT is the defect this header now exists to prevent: a shape mismatch that
// renders as silence is indistinguishable from a world with nothing in it.
//
// So `shapeReading` names the containers it located, and a body it cannot read at
// all is a REPORTED condition carrying the top-level keys that did arrive.
//
//   SERVED (`server/ledger_structure.py`, measured 2026-08-14) — the primary read:
//     { state: "absent"|"empty"|"ready", generated_at, relation,
//       window: { declared, spec, from, to, forced, forced_reason },
//       cost:   { census_ms, atoms_counted, groups, exact, … },
//       graph: {
//         nodes: [ { id, type, label, entity_class, keys, semi_ref, declared,
//                    atoms_as_subject, atoms_as_object, registered, node_state } ],
//         edges: [ { id: "Lot|has_wafer|entity:Wafer",   // ← THE IDENTITY. see below
//                    source, target, subject_type, predicate, predicate_label,
//                    object_kind, object_kind_label, object_type, object_fields,
//                    qualifiers, status, layer, since, semi_ref, declared,
//                    atoms, first_at, last_at, classes: {…}, sources: [ … ],
//                    edge_state } ],
//         layers: [ { id: "ledger"|"mechanism", label, state, nodes, edges, atoms } ],
//         mechanism: { state, declared, config, spec_ref, models, nodes, edges,
//                      directions, ledger_link, … } },
//       vocabulary: { predicates: [ { predicate, label, layer, status, since,
//                                     subject_types, object_kind, object_types,
//                                     object_fields, qualifiers, semi_ref, atoms,
//                                     classes, edge_ids } ],
//                     entity_types: [ { type, label, class, keys, semi_ref } ],
//                     object_kinds, classes, projection_only_words },
//       kinds: { state, default, kinds: [ … ], readable },
//       declarations: [ { id, group, config, origin, path, declares, name, label,
//                         readable, detail: {…}, edge_ids, node_ids, atoms, cursor } ],
//       cursors: [ … ], drift: { undeclared_edge_ids, undeclared_node_ids,
//                                undeclared_sources } }
//
//   LEGACY (the proposed flat shape) — still read, because the harness fixture is
//     written in it and it is what proves the DERIVATION discipline: flat
//     `predicates` / `entity_types` / `edges` / `declarations`, where no edge list
//     is served and the skeleton is the cross product of the signatures.
//
// 🔴 ON THE SERVED SHAPE THE EDGE IDENTITY IS THE SERVER'S `id`, NOT THIS FILE'S
// `edgeKey`. Measured: `same_as` alone yields 36 edges whose
// `subject|predicate|object_kind` triple collapses to 6 — six distinct target
// types per subject share one triple. Re-deriving the key here would silently
// merge thirty edges into six and the screen would be wrong while looking right,
// which is the exact failure mode this repository has already paid for twice.
// One authority per shape: the server unions declaration and ledger, and this
// file draws what it is told.
//
// 🔴 AND THE FIVE EDGE STATES ARE THE SERVER'S WORDS (`ledger_structure.py`):
// `flowing` · `declared_only` · `unmeasured` · `undeclared` ·
// `declared_unconsumed`. This file does not re-derive them when the wire carries
// one, and a sixth state it has never heard of survives under its raw spelling.
// ============================================================

export const STRUCTURE_VIEW = 'structure';

//: Label maps for CLOSED WIRE ENUMS. See the header: these translate words the
//: server sends; an unknown member survives under its raw spelling.
const CLASS_ORDER = ['pin', 'confirmed', 'observation', 'inference'];
const CLASS_LABELS = {
  pin: '핀', confirmed: '확정', observation: '관측', inference: '추론',
};
const OBJECT_KIND_LABELS = {
  value: '값', entity_ref: '개체 참조', event_ref: '사건 참조',
};
const LAYER_LABELS = { canonical: '정본 문법', ontology: '세계 어휘' };
const STATUS_LABELS = { active: '가동', reserved: '예약' };

const STRUCTURE_STATES = new Set(['absent', 'empty', 'ready']);

export function structureState(body) {
  const s = body && body.state != null ? String(body.state) : '';
  return STRUCTURE_STATES.has(s) ? s : 'unknown';
}

// ── the five edge states, as the server spells them ──────────
//
// `server/ledger_structure.py` owns the rule that assigns these; this file only
// reads the word. Kept as constants so the one place that DERIVES a state (the
// legacy flat shape, which carries no `edge_state`) uses the same five words the
// wire does, instead of a second spelling that has to be translated back.
export const EDGE_FLOWING = 'flowing';
export const EDGE_DECLARED_ONLY = 'declared_only';
export const EDGE_UNMEASURED = 'unmeasured';
export const EDGE_UNDECLARED = 'undeclared';
export const EDGE_DECLARED_UNCONSUMED = 'declared_unconsumed';
export const EDGE_STATES = [
  EDGE_FLOWING, EDGE_DECLARED_ONLY, EDGE_UNMEASURED, EDGE_UNDECLARED,
  EDGE_DECLARED_UNCONSUMED,
];

// ── WHERE THE ANSWER KEEPS ITS PARTS ─────────────────────────
//
// 🔴 ONE PLACE THAT READS THE ENVELOPE AND NAMES WHAT IT EXPECTED (lead PM, P0,
// 2026-08-14). The seam between this screen and `/api/ledger/structure` drifted
// once — the client asked for four top-level keys, three of them had moved a
// level down, and the result was four empty arrays, NO THROW, and a frame that
// claimed the numbers on it were measurements. An empty screen and a screen with
// legitimately nothing on it looked identical.
//
// So the containers are located ONCE, here, and the outcome is a value the view
// is obliged to render: which containers were found, which were expected and
// missing, and — when nothing at all was recognisable — the top-level keys that
// DID arrive, so the reader can see the drift rather than infer it from silence.

export const SHAPE_SERVED = 'served';
export const SHAPE_LEGACY = 'legacy';
export const SHAPE_NONE = 'none';
export const SHAPE_UNREADABLE = 'unreadable';

//: What the served shape must contain for this screen to have anything to draw.
//: `graph.edges` is the load-bearing one: without it there is no graph at all.
const SERVED_CONTAINERS = [
  ['graph.edges', (b) => b.graph && Array.isArray(b.graph.edges)],
  ['graph.nodes', (b) => b.graph && Array.isArray(b.graph.nodes)],
  ['vocabulary.predicates', (b) => b.vocabulary && Array.isArray(b.vocabulary.predicates)],
  ['vocabulary.entity_types', (b) => b.vocabulary && Array.isArray(b.vocabulary.entity_types)],
];

const LEGACY_CONTAINERS = [
  ['edges', (b) => Array.isArray(b.edges)],
  ['predicates', (b) => Array.isArray(b.predicates)],
  ['entity_types', (b) => Array.isArray(b.entity_types)],
];

function probe(body, table) {
  const found = [];
  const missing = [];
  for (const [name, test] of table) {
    let hit = false;
    try { hit = !!test(body); } catch (_) { hit = false; }
    (hit ? found : missing).push(name);
  }
  return { found, missing };
}

/**
 * Which shape the answer is in — and, when it is in none of them, what arrived.
 *
 * @returns { shape, keys, found, missing, ok, why }
 *   `ok` is false for `none` and `unreadable`. `why` is a sentence the view
 *   prints verbatim; it names the keys rather than describing them, because a
 *   description cannot be compared against the server by the person reading it.
 */
export function shapeReading(body) {
  if (body === null || body === undefined) {
    return {
      shape: SHAPE_NONE, keys: [], found: [], missing: [], ok: false,
      why: '응답 없음',
    };
  }
  if (typeof body !== 'object' || Array.isArray(body)) {
    return {
      shape: SHAPE_UNREADABLE, keys: [], found: [], missing: [], ok: false,
      why: `응답이 객체가 아닙니다 (${Array.isArray(body) ? 'array' : typeof body})`,
    };
  }
  const keys = Object.keys(body).sort();
  const served = probe(body, SERVED_CONTAINERS);
  if (served.found.length) {
    return {
      shape: SHAPE_SERVED, keys, found: served.found, missing: served.missing, ok: true,
      why: served.missing.length
        ? `응답에 ${served.missing.join(' · ')} 없음 — 그 부분은 비어 보입니다`
        : '',
    };
  }
  const legacy = probe(body, LEGACY_CONTAINERS);
  if (legacy.found.length) {
    return {
      shape: SHAPE_LEGACY, keys, found: legacy.found, missing: legacy.missing, ok: true,
      why: '',
    };
  }
  // 🔴 THE BLANK THAT MUST NEVER BE SILENT. Neither layout was recognised, so
  // every panel below is about to be empty for a reason that has nothing to do
  // with the ledger. Name the expectation AND the arrival — the pair is the
  // diagnosis, either one alone is a guess.
  return {
    shape: SHAPE_UNREADABLE, keys, found: [], missing: SERVED_CONTAINERS.map((c) => c[0]),
    ok: false,
    why: `응답에서 그래프를 찾지 못했습니다 — 기대 ${SERVED_CONTAINERS.map((c) => c[0]).join(' · ')} / 도착 ${keys.length ? keys.join(' · ') : '(키 없음)'}`,
  };
}

export const classLabel = (key) => CLASS_LABELS[key] || String(key);
export const objectKindLabel = (kind) => (
  kind == null || kind === '' ? '∅ 목적어 없음' : (OBJECT_KIND_LABELS[kind] || String(kind))
);
export const layerLabel = (layer) => LAYER_LABELS[layer] || String(layer || '');
export const statusLabel = (status) => STATUS_LABELS[status] || String(status || '');

function numOrNull(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function strOrEmpty(v) {
  return v === null || v === undefined ? '' : String(v);
}

function listOf(v) {
  return Array.isArray(v) ? v.filter((x) => x != null && String(x) !== '').map(String) : [];
}

// ── the question, as a URL ───────────────────────────────────
//
// Same discipline as the console: every control on this screen is an anchor, so
// the question lives in the address bar and a structure the owner is looking at
// can be pasted into a message.

/** Read the structure question out of a `URLSearchParams`-like. */
export function parseStructureQuery(params) {
  const get = (k) => {
    const v = params && typeof params.get === 'function' ? params.get(k) : null;
    return v == null ? '' : String(v).trim();
  };
  return {
    view: get('view'),
    edge: get('edge'),
    layer: get('layer'),
  };
}

/** Write it back. Only non-empty parts, so the default question is a bare `?view=structure`. */
export function structureQuery(question, omit) {
  const q = question || {};
  const parts = [`view=${encodeURIComponent(STRUCTURE_VIEW)}`];
  if (q.layer && omit !== 'layer') parts.push(`layer=${encodeURIComponent(q.layer)}`);
  if (q.edge && omit !== 'edge') parts.push(`edge=${encodeURIComponent(q.edge)}`);
  return parts.join('&');
}

/**
 * The identity of one edge — and it is the GROUP BY, spelled once.
 *
 * `subject_type | predicate | object_kind` is exactly the aggregation the brief
 * names, so the declared skeleton and the observed rows collide on the same key
 * by construction rather than by a matching rule that can drift.
 */
export function edgeKey(subjectType, predicate, objectKind) {
  return `${strOrEmpty(subjectType)}|${strOrEmpty(predicate)}|${objectKind == null || objectKind === '' ? 'none' : String(objectKind)}`;
}

// ── the resolution-grade distribution ────────────────────────

/**
 * An edge's grade mix, as segments that always sum to the total.
 *
 * 🔴 A CLASS THIS FILE HAS NEVER HEARD OF STILL RENDERS. The four names are the
 * server's enum today; an unrecognised key becomes a segment under its own raw
 * spelling instead of being silently dropped, because a segment that disappears
 * makes the other four add up to less than the count beside them and nothing on
 * screen says why.
 */
export function classReading(classes, atoms) {
  const src = classes && typeof classes === 'object' ? classes : null;
  const seen = [];
  if (src) {
    for (const key of CLASS_ORDER) {
      if (Object.prototype.hasOwnProperty.call(src, key)) seen.push(key);
    }
    for (const key of Object.keys(src)) {
      if (!seen.includes(key)) seen.push(key);
    }
  }
  const segments = [];
  let counted = 0;
  for (const key of seen) {
    const n = numOrNull(src[key]);
    if (n === null) continue;
    counted += n;
    segments.push({ key, label: classLabel(key), n, share: 0 });
  }
  const total = numOrNull(atoms);
  // The bar's denominator is what the segments actually add up to. Using `atoms`
  // instead would make a short-reporting server draw a bar with a silent gap that
  // reads as a fifth, unnamed grade.
  const base = counted > 0 ? counted : 0;
  for (const seg of segments) seg.share = base > 0 ? seg.n / base : 0;
  return {
    segments,
    counted,
    total,
    // 🔴 THE DISAGREEMENT IS CONTENT. If the grades do not add up to the count,
    // say so — do not quietly rescale one to the other.
    mismatch: total !== null && counted > 0 && counted !== total,
    reported: segments.length > 0,
  };
}

/** `first_at`/`last_at` as one reading, or the reason there is not one. */
export function periodReading(firstAt, lastAt) {
  const from = strOrEmpty(firstAt);
  const to = strOrEmpty(lastAt);
  if (!from && !to) return { ok: false, why: '기간 미보고', from: '', to: '' };
  return { ok: true, why: '', from, to };
}

/** A wire instant, trimmed to minutes. Never `toLocaleString` — see case_control_view. */
export function instantText(raw) {
  const s = strOrEmpty(raw);
  if (!s) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(s);
  if (!m) return s;
  return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}`;
}

// ── the derivation ───────────────────────────────────────────

/**
 * Expand ONE predicate signature into the edges it declares.
 *
 * This is where the skeleton comes from and it is the reason no list of edges
 * exists anywhere: the signature already says which subjects it accepts and
 * which object kind it takes, so the cross product IS the declaration.
 */
function declaredEdgesOf(sig) {
  const predicate = strOrEmpty(sig.predicate);
  const subjects = listOf(sig.subject);
  const object = sig.object && typeof sig.object === 'object' ? sig.object : null;
  const kind = object ? strOrEmpty(object.kind) : '';
  const types = object ? listOf(object.types) : [];
  return subjects.map((subjectType) => ({
    key: edgeKey(subjectType, predicate, kind),
    subjectType,
    predicate,
    objectKind: kind,
    declaredTypes: types,
  }));
}

function readPredicate(row) {
  const predicate = strOrEmpty(row && row.predicate);
  const object = row && row.object && typeof row.object === 'object' ? row.object : null;
  return {
    predicate,
    label: strOrEmpty(row && row.label) || predicate,
    gloss: strOrEmpty(row && row.gloss),
    layer: strOrEmpty(row && row.layer),
    status: strOrEmpty(row && row.status),
    since: numOrNull(row && row.since),
    semiRef: strOrEmpty(row && row.semi_ref),
    subject: listOf(row && row.subject),
    object: object ? {
      kind: strOrEmpty(object.kind),
      types: listOf(object.types),
      required: listOf(object.required),
    } : null,
    qualifiers: listOf(row && row.qualifiers),
    atoms: numOrNull(row && row.atoms),
    declared: true,
  };
}

function readEntityType(row) {
  const type = strOrEmpty(row && row.type);
  return {
    type,
    label: strOrEmpty(row && row.label) || type,
    cls: strOrEmpty(row && row.class),
    keys: listOf(row && row.keys),
    semiRef: strOrEmpty(row && row.semi_ref),
    atoms: numOrNull(row && row.atoms),
    declared: true,
  };
}

/**
 * A predicate that only the ROWS know about — undeclared vocabulary in the
 * ledger. It gets a node like any other, marked, because the alternative is an
 * edge pointing at nothing or an edge quietly dropped.
 */
function ghostPredicate(name) {
  return {
    predicate: name,
    label: name,
    gloss: '',
    layer: '',
    status: '',
    since: null,
    semiRef: '',
    subject: [],
    object: null,
    qualifiers: [],
    atoms: null,
    declared: false,
  };
}

function ghostEntityType(type) {
  return {
    type, label: type, cls: '', keys: [], semiRef: '', atoms: null, declared: false,
  };
}

// ── reading the SERVED shape ─────────────────────────────────
//
// The server has already unioned the declaration with the ledger, so on this path
// there is no skeleton to derive: `graph.edges` IS the union and `graph.nodes` IS
// the type list, ghosts included. What is left to do here is translate field
// names and refuse to invent anything the wire did not say.

function servedPredicate(row) {
  const predicate = strOrEmpty(row && row.predicate);
  //: `object_kind: null` is a DECLARATION (the ∅ object), not an absent field, so
  //: it must not collapse into "this predicate has no object clause" — the ∅
  //: column node hangs off it.
  const kind = row && row.object_kind != null ? String(row.object_kind) : '';
  const types = listOf(row && row.object_types);
  const fields = listOf(row && row.object_fields);
  const hasObject = kind !== '' || types.length > 0 || fields.length > 0;
  return {
    predicate,
    label: strOrEmpty(row && row.label) || predicate,
    gloss: strOrEmpty(row && row.gloss),
    layer: strOrEmpty(row && row.layer),
    status: strOrEmpty(row && row.status),
    since: numOrNull(row && row.since),
    semiRef: strOrEmpty(row && row.semi_ref),
    subject: listOf(row && row.subject_types),
    object: hasObject ? { kind, types, required: fields } : null,
    qualifiers: listOf(row && row.qualifiers),
    atoms: numOrNull(row && row.atoms),
    declared: true,
  };
}

function servedEntityType(row) {
  const type = strOrEmpty(row && (row.type != null ? row.type : row.id));
  //: `atoms_as_subject` is the count this column means — how much has been SAID
  //: about instances of this type. `atoms` is accepted as the older spelling.
  const asSubject = row && row.atoms_as_subject !== undefined
    ? numOrNull(row.atoms_as_subject) : numOrNull(row && row.atoms);
  return {
    type,
    label: strOrEmpty(row && row.label) || type,
    cls: strOrEmpty(row && (row.class != null ? row.class : row.entity_class)),
    keys: listOf(row && row.keys),
    semiRef: strOrEmpty(row && row.semi_ref),
    atoms: asSubject,
    atomsAsObject: numOrNull(row && row.atoms_as_object),
    registered: numOrNull(row && row.registered),
    nodeState: strOrEmpty(row && row.node_state),
    declared: !(row && row.declared === false),
  };
}

function readSources(raw) {
  return (Array.isArray(raw) ? raw : []).map((s) => ({
    who: strOrEmpty(s && s.source_who),
    derivation: strOrEmpty(s && s.derivation),
    atoms: numOrNull(s && s.atoms),
  })).filter((s) => s.who || s.derivation);
}

/**
 * One served edge, normalised.
 *
 * 🔴 THE KEY IS `row.id`. See the file header: the `subject|predicate|kind`
 * triple is NOT unique on this shape — measured, `same_as` puts six edges (one
 * per target type) behind each triple. Falling back to the derived key when the
 * server sends no id keeps the legacy contract, but the id wins whenever it
 * exists.
 */
function servedEdge(row) {
  const subjectType = strOrEmpty(row.subject_type);
  const predicate = strOrEmpty(row.predicate);
  const objectKind = row.object_kind == null ? '' : String(row.object_kind);
  const target = strOrEmpty(row.object_type);
  const atoms = numOrNull(row.atoms);
  return {
    key: strOrEmpty(row.id) || edgeKey(subjectType, predicate, objectKind),
    subjectType,
    predicate,
    objectKind,
    objectKindLabel: strOrEmpty(row.object_kind_label),
    declaredTypes: target ? [target] : [],
    observedTypes: [],
    atoms,
    firstAt: strOrEmpty(row.first_at),
    lastAt: strOrEmpty(row.last_at),
    classes: row.classes && typeof row.classes === 'object' ? row.classes : null,
    declared: !(row.declared === false),
    observed: atoms !== null,
    //: The server's verdict. `edgeStatusOf` prefers it over any derivation.
    wireState: strOrEmpty(row.edge_state),
    wireLayer: strOrEmpty(row.layer),
    since: numOrNull(row.since),
    predicateStatus: strOrEmpty(row.status),
    semiRef: strOrEmpty(row.semi_ref),
    qualifiers: listOf(row.qualifiers),
    objectFields: listOf(row.object_fields),
    sources: readSources(row.sources),
  };
}

/** A `detail` object, as one bounded line. Six entries, then it stops. */
function compactDetail(detail) {
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return '';
  const parts = [];
  for (const k of Object.keys(detail)) {
    if (parts.length >= 6) { parts.push('…'); break; }
    const v = detail[k];
    if (v === null || v === undefined || v === '') continue;
    if (Array.isArray(v)) { if (v.length) parts.push(`${k} ${v.length}`); }
    else if (typeof v === 'object') {
      const n = Object.keys(v).length;
      if (n) parts.push(`${k} {${n}}`);
    } else parts.push(`${k} ${String(v)}`);
  }
  return parts.join(' · ');
}

/**
 * The served declaration list, grouped by its own `group` field.
 *
 * The legacy shape nested items inside a source; the served one is flat and says
 * which group each row belongs to. Grouping here rather than asking the server to
 * re-nest keeps the wire one row per declaration, which is also what carries
 * `readable: false` — a config the server could not open, which is exactly the
 * kind of gap this panel exists to show.
 */
function servedDeclarations(rows, edgeKeys) {
  const groups = new Map();
  for (const d of (Array.isArray(rows) ? rows : [])) {
    if (!d || typeof d !== 'object') continue;
    const groupKey = strOrEmpty(d.group) || 'etc';
    if (!groups.has(groupKey)) {
      groups.set(groupKey, {
        source: groupKey, file: '', title: '', items: [], files: [],
      });
    }
    const g = groups.get(groupKey);
    if (!g.title) g.title = strOrEmpty(d.declares) || groupKey;
    const file = strOrEmpty(d.config);
    if (file && !g.files.includes(file)) g.files.push(file);
    const detail = compactDetail(d.detail);
    const unreadable = d.readable === false;
    groups.get(groupKey).items.push({
      term: strOrEmpty(d.label) || strOrEmpty(d.name) || strOrEmpty(d.id),
      detail: unreadable ? `읽지 못함${detail ? ` · ${detail}` : ''}` : detail,
      //: Only ids that resolve to an edge on screen become links. A ref to an
      //: edge that is not here would be a dead link that looks live.
      edges: listOf(d.edge_ids).filter((k) => edgeKeys.has(k)),
      atoms: numOrNull(d.atoms),
      readable: !unreadable,
    });
  }
  const out = [...groups.values()];
  for (const g of out) {
    g.file = g.files.slice(0, 3).join(' · ') + (g.files.length > 3 ? ' …' : '');
    delete g.files;
  }
  return out;
}

/** The `graph.layers` summary — which layer of the world is in what condition. */
function servedLayers(rows) {
  return (Array.isArray(rows) ? rows : []).map((l) => ({
    id: strOrEmpty(l && l.id),
    label: strOrEmpty(l && l.label) || strOrEmpty(l && l.id),
    state: strOrEmpty(l && l.state),
    nodes: numOrNull(l && l.nodes),
    edges: numOrNull(l && l.edges),
    atoms: numOrNull(l && l.atoms),
    reason: strOrEmpty(l && l.reason),
    message: strOrEmpty(l && l.message),
    specRef: strOrEmpty(l && l.spec_ref),
  })).filter((l) => l.id);
}

/**
 * The M4 mechanism graph.
 *
 * 🔴 IT IS NOT DRAWN INTO THE THREE COLUMNS. Its nodes are causal variables
 * (`bond_pressure → interface_unfill`), not subject/predicate/object triples, and
 * forcing them into that layout would assert a join that does not exist. It gets
 * its own panel — which is also the only place the fifth edge state,
 * `declared_unconsumed`, can currently be seen.
 */
function servedMechanism(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const edges = (Array.isArray(raw.edges) ? raw.edges : []).map((e) => ({
    id: strOrEmpty(e && e.id),
    model: strOrEmpty(e && e.model),
    source: strOrEmpty(e && e.source),
    target: strOrEmpty(e && e.target),
    dir: strOrEmpty(e && e.dir),
    dirLabel: strOrEmpty(e && e.dir_label),
    hasForm: !!(e && e.has_form),
    atoms: numOrNull(e && e.atoms),
    status: strOrEmpty(e && e.edge_state),
  }));
  const nodes = (Array.isArray(raw.nodes) ? raw.nodes : []).map((n) => ({
    id: strOrEmpty(n && n.id),
    label: strOrEmpty(n && n.label) || strOrEmpty(n && n.id),
    model: strOrEmpty(n && n.model),
    atoms: numOrNull(n && n.atoms),
    status: strOrEmpty(n && n.node_state),
  }));
  const link = raw.ledger_link && typeof raw.ledger_link === 'object' ? {
    entityType: strOrEmpty(raw.ledger_link.entity_type),
    reason: strOrEmpty(raw.ledger_link.reason),
    message: strOrEmpty(raw.ledger_link.message),
  } : null;
  return {
    state: strOrEmpty(raw.state) || 'unknown',
    declared: !!raw.declared,
    config: strOrEmpty(raw.config),
    origin: strOrEmpty(raw.origin),
    specRef: strOrEmpty(raw.spec_ref),
    reason: strOrEmpty(raw.reason),
    message: strOrEmpty(raw.message),
    models: (Array.isArray(raw.models) ? raw.models : []).map((m) => ({
      model: strOrEmpty(m && m.model),
      version: strOrEmpty(m && m.version),
      nodes: listOf(m && m.nodes),
      edgeIds: listOf(m && m.edge_ids),
      validity: strOrEmpty(m && m.validity),
    })),
    nodes,
    edges,
    link,
  };
}

/** The kind registry, when the structure answer carries one of its own. */
function servedKinds(raw) {
  if (!raw || typeof raw !== 'object' || !Array.isArray(raw.kinds)) return null;
  const rows = [];
  for (const k of raw.kinds) {
    if (!k || typeof k !== 'object') continue;
    const kind = strOrEmpty(k.kind);
    if (!kind) continue;
    const methods = listOf(k.observed_by);
    rows.push({
      kind,
      label: strOrEmpty(k.label) || kind,
      atoms: numOrNull(k.atoms),
      runs: numOrNull(k.runs),
      methods,
      classes: listOf(k.classes),
      //: The server's own field, never a re-derivation from the method count —
      //: same rule `case_control_core.kindCatalog` records at length.
      hasDenominator: typeof k.has_denominator === 'boolean'
        ? k.has_denominator : methods.length > 0,
      observationTable: strOrEmpty(k.observation_table),
      ledgerState: strOrEmpty(k.ledger_state),
      ledgerAtoms: numOrNull(k.ledger_atoms),
      ledgerEdges: listOf(k.ledger_edge_ids),
    });
  }
  return { state: strOrEmpty(raw.state) || 'unknown', rows };
}

/** How the census was taken — the reader's right to know what the numbers cost. */
function servedCensus(body) {
  const cost = body.cost && typeof body.cost === 'object' ? body.cost : {};
  const win = body.window && typeof body.window === 'object' ? body.window : {};
  return {
    relation: strOrEmpty(body.relation),
    ms: numOrNull(cost.census_ms),
    atoms: numOrNull(cost.atoms_counted),
    groups: numOrNull(cost.groups),
    exact: typeof cost.exact === 'boolean' ? cost.exact : null,
    windowSpec: strOrEmpty(win.spec),
    windowFrom: strOrEmpty(win.from),
    windowTo: strOrEmpty(win.to),
    forced: !!win.forced,
    forcedReason: strOrEmpty(win.forced_reason),
  };
}

function servedDrift(raw) {
  const d = raw && typeof raw === 'object' ? raw : {};
  return {
    edges: listOf(d.undeclared_edge_ids),
    nodes: listOf(d.undeclared_node_ids),
    sources: listOf(d.undeclared_sources),
  };
}

/**
 * An edge's state.
 *
 * 🔴 THE WIRE'S WORD WINS AND AN UNKNOWN ONE SURVIVES. `server/ledger_structure.py`
 * owns the rule; re-deriving over the top would be a second implementation of it,
 * which is how this repository produced two disagreeing coordinate transforms. The
 * derivation below runs ONLY when no state was sent — the legacy flat shape.
 */
function edgeStatusOf(e) {
  if (e.wireState) return e.wireState;
  if (!e.declared) return EDGE_UNDECLARED;
  if (e.atoms !== null && e.atoms > 0) return EDGE_FLOWING;
  if (e.atoms === 0) return EDGE_DECLARED_ONLY;
  return EDGE_UNMEASURED;
}

// ── layout (pure geometry, so the harness can score it) ──────
//
// 🔴 DETERMINISTIC, NOT FORCE-DIRECTED. `graph_viewer.js` carries a force layout
// for the INSTANCE graph, where the node set is unknown and large. This graph is
// the vocabulary: a dozen predicates and a handful of types, and it must look the
// same on every load so the owner can point at a spot and be understood. A
// simulation that settles differently each time is worse than useless for that.
//
// 🔴 SIZES ARE FIXED AND THE SVG IS NEVER SHRUNK BELOW THEM. Readability is a
// function of this screen, so a narrow viewport scrolls the graph horizontally —
// it does not scale the type down (`ledger.html` sets `min-width` to match).
export const LAYOUT = {
  padX: 28,
  headerH: 46,
  padY: 18,
  subjW: 220,
  predW: 330,
  objW: 230,
  gap: 118,
  sideH: 64,
  predH: 88,
  pitchSide: 86,
  pitchPred: 112,
};

function columnX() {
  const subjX = LAYOUT.padX;
  const predX = subjX + LAYOUT.subjW + LAYOUT.gap;
  const objX = predX + LAYOUT.predW + LAYOUT.gap;
  return { subjX, predX, objX, width: objX + LAYOUT.objW + LAYOUT.padX };
}

function place(items, x, w, h, pitch, contentH, top) {
  const n = items.length;
  const span = n * pitch;
  const start = top + Math.max(0, (contentH - span) / 2);
  return items.map((item, i) => ({
    ...item,
    x, w, h,
    y: Math.round(start + (i * pitch) + ((pitch - h) / 2)),
  }));
}

/**
 * The whole screen, as one value.
 *
 * @param body   the `GET /api/ledger/structure` body, or null
 * @param kinds  the normalised `GET /api/ledger/kinds` catalog (case_control_core), or null
 * @param kindsBody the RAW kinds body — for `observation_table`, the one field the
 *                  shared catalog reader does not carry
 * @param question `parseStructureQuery` output
 */
export function structureModel({ body, kinds, kindsBody, question } = {}) {
  const q = question || {};
  const state = structureState(body);
  // 🔴 THE ENVELOPE IS READ ONCE, AND THE OUTCOME IS PART OF THE MODEL. Every
  // panel below can legitimately be empty; only this value can say whether the
  // emptiness is the ledger's or the reader's.
  const reading = shapeReading(body);
  const served = reading.shape === SHAPE_SERVED;

  const graph = served && body.graph && typeof body.graph === 'object' ? body.graph : null;
  const vocab = served && body.vocabulary && typeof body.vocabulary === 'object'
    ? body.vocabulary : null;

  // ── vocabulary and types, as the server declared them ──
  const predicates = new Map();
  const predRows = served
    ? (vocab && Array.isArray(vocab.predicates) ? vocab.predicates : [])
    : (body && Array.isArray(body.predicates) ? body.predicates : []);
  for (const row of predRows) {
    const sig = served ? servedPredicate(row) : readPredicate(row);
    if (sig.predicate) predicates.set(sig.predicate, sig);
  }

  const entityTypes = new Map();
  const typeRows = served
    ? (vocab && Array.isArray(vocab.entity_types) ? vocab.entity_types : [])
    : (body && Array.isArray(body.entity_types) ? body.entity_types : []);
  for (const row of typeRows) {
    const t = served ? servedEntityType(row) : readEntityType(row);
    if (t.type) entityTypes.set(t.type, t);
  }
  // On the served shape the counted nodes come separately, in census order.
  // Declaration order stays authoritative for POSITION; the node row supplies the
  // numbers and any type the ledger knows and the vocabulary does not.
  if (graph && Array.isArray(graph.nodes)) {
    for (const row of graph.nodes) {
      const t = servedEntityType(row);
      if (!t.type) continue;
      const prior = entityTypes.get(t.type);
      entityTypes.set(t.type, prior ? { ...prior, ...t, label: t.label || prior.label } : t);
    }
  }

  // ── the edges ──
  //
  // SERVED: the server already unioned declaration and ledger; this is a read.
  // LEGACY: no edge list is served, so the skeleton is the cross product of the
  //         signatures and the rows are merged onto it. The two paths never mix,
  //         because a key built two ways is the drift this screen reports on.
  const edges = new Map();
  let aggregateRan;
  if (served) {
    for (const row of (graph && Array.isArray(graph.edges) ? graph.edges : [])) {
      if (!row || typeof row !== 'object') continue;
      const e = servedEdge(row);
      if (!e.key || !e.subjectType || !e.predicate) continue;
      edges.set(e.key, e);
      if (!predicates.has(e.predicate)) predicates.set(e.predicate, ghostPredicate(e.predicate));
      if (!entityTypes.has(e.subjectType)) {
        entityTypes.set(e.subjectType, ghostEntityType(e.subjectType));
      }
    }
    // The server states every edge's condition itself, including `unmeasured`, so
    // there is nothing left here to claim on its behalf.
    aggregateRan = !!(graph && Array.isArray(graph.edges))
      && (state === 'ready' || state === 'empty');
  } else {
    // ── the declared skeleton ──
    for (const sig of predicates.values()) {
      for (const e of declaredEdgesOf(sig)) {
        edges.set(e.key, {
          ...e,
          observedTypes: [],
          atoms: null,
          firstAt: '',
          lastAt: '',
          classes: null,
          declared: true,
          observed: false,
          wireState: '',
          wireLayer: '',
          sources: [],
        });
      }
    }
    // ── the observed weight, merged onto the same key ──
    const edgeRows = body && Array.isArray(body.edges) ? body.edges : [];
    for (const row of edgeRows) {
      if (!row || typeof row !== 'object') continue;
      const subjectType = strOrEmpty(row.subject_type);
      const predicate = strOrEmpty(row.predicate);
      if (!subjectType || !predicate) continue;
      const objectKind = row.object_kind == null ? '' : String(row.object_kind);
      const key = edgeKey(subjectType, predicate, objectKind);
      const prior = edges.get(key);
      edges.set(key, {
        key,
        subjectType,
        predicate,
        objectKind,
        objectKindLabel: '',
        declaredTypes: prior ? prior.declaredTypes : [],
        observedTypes: listOf(row.object_types),
        atoms: numOrNull(row.atoms),
        firstAt: strOrEmpty(row.first_at),
        lastAt: strOrEmpty(row.last_at),
        classes: row.classes && typeof row.classes === 'object' ? row.classes : null,
        declared: !!prior,
        observed: true,
        wireState: strOrEmpty(row.edge_state),
        wireLayer: strOrEmpty(row.layer),
        sources: readSources(row.sources),
      });
      // Vocabulary the ledger holds and the declaration does not. It gets a node
      // so the edge has somewhere to land, and it is marked so it reads as the
      // finding it is rather than as a normal part of the world.
      if (!predicates.has(predicate)) predicates.set(predicate, ghostPredicate(predicate));
      if (!entityTypes.has(subjectType)) entityTypes.set(subjectType, ghostEntityType(subjectType));
    }
    // 🔴 AN EDGE HAS TWO POSSIBLE ORIGINS AND THE SCREEN MUST NOT CONFLATE THEM
    // (lead PM, 2026-08-14): one comes out of the LEDGER AGGREGATE and carries a
    // count, a period and a grade mix; the other comes out of the DECLARATION
    // ALONE and its count may be zero.
    //
    // 🔴 AND THAT MEANS A MEASURED ZERO MUST NOT RENDER AS 미보고. An absent FIELD
    // is not a measurement, but a GROUP BY that ran and produced no group for a
    // declared axis IS one — the axis was looked for and found empty. So the zero
    // is claimable exactly when the aggregate actually ran, and unclaimable
    // otherwise.
    //
    //   state ready | empty + an `edges` array -> a declared axis with no row is 0
    //   anything else                          -> it is 미보고, and says so
    aggregateRan = Array.isArray(body && body.edges)
      && (state === 'ready' || state === 'empty');
  }

  // ── status per edge, and the layer filter ──
  const layerFilter = q.layer || '';
  const allEdges = [...edges.values()].map((e) => {
    // A declared axis the aggregate did not report is a zero ONLY if the
    // aggregate is in a position to have reported it. (Legacy path only — on the
    // served shape the server has already decided, and `wireState` says so.)
    const atoms = (!e.wireState && e.atoms === null && e.declared && !e.observed && aggregateRan)
      ? 0 : e.atoms;
    const status = edgeStatusOf({ ...e, atoms });
    const sig = predicates.get(e.predicate);
    // Object targets: what the declaration says, plus anything the rows actually
    // carried. Both, because a target observed and not declared is exactly the
    // kind of drift this screen exists to expose.
    const targets = [];
    for (const t of e.declaredTypes) if (!targets.includes(t)) targets.push(t);
    for (const t of e.observedTypes) if (!targets.includes(t)) targets.push(t);
    return {
      ...e,
      atoms,
      status,
      targets,
      // Which of the two layers this edge came out of — the thing the owner is
      // here to tell apart. `both` is the healthy case: declared AND flowing.
      origin: e.declared && (atoms !== null && atoms > 0) ? 'both'
        : (e.declared ? 'declaration' : 'ledger'),
      layer: e.wireLayer || (sig ? sig.layer : ''),
      grades: classReading(e.classes, atoms),
      period: periodReading(e.firstAt, e.lastAt),
    };
  });

  const layers = [];
  for (const e of allEdges) {
    const key = e.layer || '';
    if (!key) continue;
    let row = layers.find((l) => l.key === key);
    if (!row) { row = { key, label: layerLabel(key), count: 0 }; layers.push(row); }
    row.count += 1;
  }
  layers.sort((a, b) => (a.key < b.key ? -1 : 1));

  const shown = layerFilter
    ? allEdges.filter((e) => e.layer === layerFilter)
    : allEdges;

  // ── the three columns, derived from what the shown edges touch ──
  //
  // Declared order first (the server sends the vocabulary in its declaration
  // order and that order is meaningful), ghosts last so drift sinks to the
  // bottom rather than hiding in the middle.
  const usedSubjects = new Set(shown.map((e) => e.subjectType));
  const usedPredicates = new Set(shown.map((e) => e.predicate));

  const subjectNodes = [...entityTypes.values()]
    .filter((t) => usedSubjects.has(t.type))
    .sort((a, b) => (a.declared === b.declared ? 0 : (a.declared ? -1 : 1)))
    .map((t) => ({
      id: `subj:${t.type}`,
      kindOfNode: 'subject',
      type: t.type,
      label: t.label,
      sub: t.keys.length ? `키 ${t.keys.join(' · ')}` : '',
      cls: t.cls,
      atoms: t.atoms,
      declared: t.declared,
    }));

  const predicateNodes = [...predicates.values()]
    .filter((p) => usedPredicates.has(p.predicate))
    .sort((a, b) => {
      if (a.declared !== b.declared) return a.declared ? -1 : 1;
      const la = a.layer || 'zz';
      const lb = b.layer || 'zz';
      if (la !== lb) return la < lb ? -1 : 1;
      const sa = a.since === null ? 0 : a.since;
      const sb = b.since === null ? 0 : b.since;
      if (sa !== sb) return sa - sb;
      return a.predicate < b.predicate ? -1 : 1;
    })
    .map((p) => ({
      id: `pred:${p.predicate}`,
      kindOfNode: 'predicate',
      predicate: p.predicate,
      label: p.label,
      gloss: p.gloss || glossOf(p),
      layer: p.layer,
      status: p.status,
      since: p.since,
      semiRef: p.semiRef,
      qualifiers: p.qualifiers,
      atoms: p.atoms,
      declared: p.declared,
    }));

  // Object nodes: one per DISTINCT target of a shown edge. A single declared
  // target resolves to that entity type; several (or none) resolve to the object
  // KIND itself, which is the third axis of the brief's GROUP BY. Both cases come
  // out of the declaration — neither is a choice made here about which predicate
  // is special.
  const objectNodes = [];
  const objectIdOf = new Map();
  for (const e of shown) {
    let id;
    let node;
    if (e.targets.length === 1) {
      const t = e.targets[0];
      const known = entityTypes.get(t);
      id = `obj:type:${t}`;
      node = {
        id,
        kindOfNode: 'object',
        objectKind: e.objectKind,
        type: t,
        label: known ? known.label : t,
        //: The server's own label for the kind when it sent one — it is the same
        //: enum this file translates, and its spelling is the authority.
        sub: known && known.keys.length
          ? `키 ${known.keys.join(' · ')}`
          : (e.objectKindLabel || objectKindLabel(e.objectKind)),
        declared: !!known,
      };
    } else {
      id = `obj:kind:${e.objectKind || 'none'}`;
      node = {
        id,
        kindOfNode: 'object',
        objectKind: e.objectKind,
        type: '',
        label: e.objectKindLabel || objectKindLabel(e.objectKind),
        sub: e.targets.length > 1 ? `${e.targets.length}종` : '',
        declared: true,
      };
    }
    objectIdOf.set(e.key, id);
    if (!objectNodes.some((n) => n.id === id)) objectNodes.push(node);
  }

  // ── geometry ──
  const cols = columnX();
  const contentH = Math.max(
    predicateNodes.length * LAYOUT.pitchPred,
    subjectNodes.length * LAYOUT.pitchSide,
    objectNodes.length * LAYOUT.pitchSide,
    LAYOUT.pitchPred,
  );
  const top = LAYOUT.headerH + LAYOUT.padY;
  const subjects = place(subjectNodes, cols.subjX, LAYOUT.subjW, LAYOUT.sideH, LAYOUT.pitchSide, contentH, top);
  const preds = place(predicateNodes, cols.predX, LAYOUT.predW, LAYOUT.predH, LAYOUT.pitchPred, contentH, top);
  const objects = place(objectNodes, cols.objX, LAYOUT.objW, LAYOUT.sideH, LAYOUT.pitchSide, contentH, top);

  const at = new Map();
  for (const n of subjects) at.set(n.id, n);
  for (const n of preds) at.set(n.id, n);
  for (const n of objects) at.set(n.id, n);

  // ── the edge geometry, and the fan-in spread ──
  //
  // Several subjects land on one predicate (register takes five), so the entry
  // points are spread down the pill's left edge. Without that the five lines
  // arrive at one pixel and the fan reads as one line.
  const bySubjectSide = new Map();
  const byObjectSide = new Map();
  for (const e of shown) {
    const pid = `pred:${e.predicate}`;
    if (!bySubjectSide.has(pid)) bySubjectSide.set(pid, []);
    bySubjectSide.get(pid).push(e.key);
    const oid = objectIdOf.get(e.key);
    if (!byObjectSide.has(oid)) byObjectSide.set(oid, []);
    byObjectSide.get(oid).push(e.key);
  }

  const maxAtoms = shown.reduce((m, e) => Math.max(m, e.atoms || 0), 0);

  const laidEdges = shown.map((e) => {
    const s = at.get(`subj:${e.subjectType}`);
    const p = at.get(`pred:${e.predicate}`);
    const o = at.get(objectIdOf.get(e.key));
    const fan = bySubjectSide.get(`pred:${e.predicate}`) || [];
    const slot = fan.indexOf(e.key);
    const inY = p ? p.y + (LAYOUT.predH * ((slot + 1) / (fan.length + 1))) : 0;
    return {
      ...e,
      objectId: objectIdOf.get(e.key),
      // subject → predicate: the segment that CARRIES THE MEASUREMENT.
      lead: s && p ? {
        x1: s.x + s.w, y1: s.y + (s.h / 2),
        x2: p.x, y2: Math.round(inY),
      } : null,
      // predicate → object: structural, and fixed by the signature (a predicate
      // declares exactly one object kind), so it carries no number of its own.
      tail: p && o ? {
        x1: p.x + p.w, y1: p.y + (LAYOUT.predH / 2),
        x2: o.x, y2: o.y + (o.h / 2),
      } : null,
      weight: maxAtoms > 0 && e.atoms ? Math.min(1, Math.log10(1 + e.atoms) / Math.log10(1 + maxAtoms)) : 0,
      selected: !!q.edge && q.edge === e.key,
    };
  });

  // ── vocabulary panel: every declared predicate, used or not ──
  const atomsByPredicate = new Map();
  for (const e of allEdges) {
    if (e.atoms === null) continue;
    atomsByPredicate.set(e.predicate, (atomsByPredicate.get(e.predicate) || 0) + e.atoms);
  }
  const vocabulary = [...predicates.values()].map((p) => ({
    predicate: p.predicate,
    label: p.label,
    gloss: p.gloss || glossOf(p),
    layer: p.layer,
    layerLabel: layerLabel(p.layer),
    status: p.status,
    statusLabel: statusLabel(p.status),
    since: p.since,
    semiRef: p.semiRef,
    qualifiers: p.qualifiers,
    subject: p.subject,
    object: p.object,
    declared: p.declared,
    // The predicate's own count if the server sent one; otherwise the sum over
    // its edges. Never a 0 invented out of an absent field.
    atoms: p.atoms !== null ? p.atoms
      : (atomsByPredicate.has(p.predicate) ? atomsByPredicate.get(p.predicate) : null),
  })).sort((a, b) => {
    const aa = a.atoms === null ? -1 : a.atoms;
    const bb = b.atoms === null ? -1 : b.atoms;
    if (aa !== bb) return bb - aa;
    return a.predicate < b.predicate ? -1 : 1;
  });

  // ── kind registry panel ──
  //
  // The served answer carries its own registry, richer than the shared catalog
  // (it knows which ledger edges each kind reaches). Prefer it; fall back to the
  // separately-fetched `/api/ledger/kinds` so the panel still answers when the
  // structure route does not.
  const inlineKinds = served ? servedKinds(body.kinds) : null;
  let kindState;
  let kindRows;
  if (inlineKinds) {
    kindState = inlineKinds.state;
    kindRows = inlineKinds.rows;
  } else {
    const rawKinds = kindsBody && Array.isArray(kindsBody.kinds) ? kindsBody.kinds : [];
    const tableOf = new Map();
    for (const row of rawKinds) {
      if (row && row.kind != null) tableOf.set(String(row.kind), strOrEmpty(row.observation_table));
    }
    kindState = kinds && kinds.state ? kinds.state : 'unknown';
    kindRows = (kinds && Array.isArray(kinds.kinds) ? kinds.kinds : []).map((k) => ({
      ...k,
      observationTable: tableOf.get(k.kind) || '',
    }));
  }

  // ── declaration map ──
  const declRows = body && Array.isArray(body.declarations) ? body.declarations : [];
  const declarations = served
    ? servedDeclarations(declRows, new Set(edges.keys()))
    : declRows.map((d) => ({
      source: strOrEmpty(d && d.source),
      file: strOrEmpty(d && d.file),
      title: strOrEmpty(d && d.title) || strOrEmpty(d && d.source),
      items: (d && Array.isArray(d.items) ? d.items : []).map((item) => {
        const refs = (item && Array.isArray(item.edges) ? item.edges : [])
          .map((r) => edgeKey(r && r.subject_type, r && r.predicate, r && r.object_kind))
          .filter((k) => edges.has(k));
        return {
          term: strOrEmpty(item && item.term),
          detail: strOrEmpty(item && item.detail),
          edges: refs,
          atoms: null,
          readable: true,
        };
      }),
    }));

  // ── the two layers of the world, and the mechanism graph ──
  const graphLayers = served && graph ? servedLayers(graph.layers) : [];
  const mechanism = served && graph ? servedMechanism(graph.mechanism) : null;
  const census = served ? servedCensus(body) : null;
  const drift = served ? servedDrift(body.drift) : null;

  // 🔴 EVERY STATE THAT OCCURRED IS COUNTED, INCLUDING ONE THIS FILE HAS NEVER
  // HEARD OF. Same discipline as `classReading`: a sixth state introduced by the
  // server must show up under its raw spelling rather than vanish from a legend
  // that iterates a fixed list of five.
  const stateCounts = new Map();
  const bump = (k) => { if (k) stateCounts.set(k, (stateCounts.get(k) || 0) + 1); };
  for (const e of allEdges) bump(e.status);
  for (const e of (mechanism ? mechanism.edges : [])) bump(e.status);
  const statusRows = EDGE_STATES.map((k) => ({ key: k, n: stateCounts.get(k) || 0 }));
  for (const k of stateCounts.keys()) {
    if (!EDGE_STATES.includes(k)) statusRows.push({ key: k, n: stateCounts.get(k) });
  }

  const countOf = (k) => allEdges.filter((e) => e.status === k).length;
  const totals = {
    edges: allEdges.length,
    flowing: countOf(EDGE_FLOWING),
    declaredOnly: countOf(EDGE_DECLARED_ONLY),
    unmeasured: countOf(EDGE_UNMEASURED),
    undeclared: countOf(EDGE_UNDECLARED),
    //: The fifth state lives on the mechanism layer, which is not part of the
    //: three-column graph — so it is counted from there, not invented here.
    declaredUnconsumed: (mechanism ? mechanism.edges : [])
      .filter((e) => e.status === EDGE_DECLARED_UNCONSUMED).length,
    byState: statusRows,
    atoms: allEdges.reduce((s, e) => s + (e.atoms || 0), 0),
    reported: allEdges.some((e) => e.atoms !== null),
    aggregateRan,
  };

  return {
    state,
    //: WHICH NOTHING THIS IS. The view is obliged to render this when it is not
    //: `ok` — a blank whose cause is the reader must not look like a blank whose
    //: cause is the ledger.
    reading,
    graphLayers,
    mechanism,
    census,
    drift,
    generatedAt: strOrEmpty(body && body.generated_at),
    question: { view: STRUCTURE_VIEW, edge: q.edge || '', layer: layerFilter },
    layers,
    graph: {
      width: cols.width,
      height: top + contentH + LAYOUT.padY,
      columns: [
        { x: cols.subjX, w: LAYOUT.subjW, label: '주어 유형' },
        { x: cols.predX, w: LAYOUT.predW, label: '술어' },
        { x: cols.objX, w: LAYOUT.objW, label: '목적어 종류' },
      ],
      subjects, predicates: preds, objects,
      edges: laidEdges,
    },
    // The detail list under the graph — the same edges, sorted so the axes that
    // carry data come first and the declared-empty ones sit together where they
    // can be counted at a glance.
    edgeList: [...shown].sort((a, b) => {
      // 🔴 THE DECLARED-ONLY AXES SIT TOGETHER AND ARE NOT BURIED. They are what
      // the owner may specifically be here for ("declared but zero consumers"), so
      // they are one contiguous block rather than scattered among the busy ones.
      const RANK = {
        [EDGE_FLOWING]: 0,
        [EDGE_UNDECLARED]: 1,
        [EDGE_DECLARED_ONLY]: 2,
        [EDGE_UNMEASURED]: 3,
        [EDGE_DECLARED_UNCONSUMED]: 4,
      };
      const rank = (e) => (RANK[e.status] === undefined ? 5 : RANK[e.status]);
      if (rank(a) !== rank(b)) return rank(a) - rank(b);
      const aa = a.atoms === null ? -1 : a.atoms;
      const bb = b.atoms === null ? -1 : b.atoms;
      if (aa !== bb) return bb - aa;
      return a.key < b.key ? -1 : 1;
    }).map((e) => ({ ...e, selected: !!q.edge && q.edge === e.key })),
    vocabulary,
    kinds: { state: kindState, rows: kindRows },
    declarations,
    totals,
  };
}

/**
 * A predicate's one-line reading, DERIVED from its signature when the server did
 * not send prose for it.
 *
 * The brief asks the vocabulary panel for "한 줄 뜻". A gloss the server writes is
 * better, and this is what the screen says when there is not one — a sentence
 * built out of the declaration rather than a blank, so the panel is useful the
 * day it ships instead of the day someone writes ten sentences.
 */
export function glossOf(sig) {
  if (!sig) return '';
  const subject = listOf(sig.subject);
  const subjText = subject.length ? subject.join(' · ') : '주어 미선언';
  if (!sig.object) return `${subjText} 를 등록 — 목적어 없음`;
  const kind = strOrEmpty(sig.object.kind);
  const types = listOf(sig.object.types);
  const quals = listOf(sig.qualifiers);
  const tail = quals.length ? ` · 한정자 ${quals.join(' · ')}` : '';
  if (kind === 'entity_ref') {
    return `${subjText} → ${types.length ? types.join(' · ') : '개체'}${tail}`;
  }
  const required = listOf(sig.object.required);
  const body = required.length ? `${objectKindLabel(kind)} {${required.join(', ')}}` : objectKindLabel(kind);
  return `${subjText} → ${body}${tail}`;
}
