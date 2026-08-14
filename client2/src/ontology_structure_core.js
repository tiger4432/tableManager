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
// 🔴 PROPOSED SHAPE — NOT YET SERVED (server lane is building the aggregate).
// This client consumes ONE call. Every field is optional to this reader: a
// missing one renders as 미보고, never as 0 and never as a blank.
//
//   GET /api/ledger/structure
//     -> {
//          state: "absent" | "empty" | "ready",
//          generated_at: "<iso>",
//
//          entity_types: [                       // vocabulary.ENTITY_TYPES
//            { type: "Lot", label: "랏",
//              class: "issued" | "composed",
//              keys: ["lot"], semi_ref: "E90 substrate",
//              atoms: <int|null> }               // atoms whose SUBJECT is this type
//          ],
//
//          predicates: [                         // vocabulary.PREDICATES
//            { predicate: "has_wafer", label: "웨이퍼 보유", gloss: "<한 줄 뜻>",
//              layer: "canonical" | "ontology",
//              status: "active" | "reserved",
//              since: <int>, semi_ref: "E90",
//              subject: ["Lot"],
//              object: null | { kind: "value"|"entity_ref"|"event_ref",
//                               types: ["Wafer"], required: ["step", …] },
//              qualifiers: ["slot"],
//              atoms: <int|null> }
//          ],
//
//          edges: [                              // GROUP BY subject_type, predicate,
//            { subject_type: "Lot",              //          object_kind
//              predicate: "has_wafer",
//              object_kind: "entity_ref" | null, // null = ∅ (register)
//              object_types: ["Wafer"],          // observed targets, may be []
//              atoms: <int>,
//              first_at: "<iso>|null", last_at: "<iso>|null",
//              classes: { pin: n, confirmed: n, observation: n, inference: n } }
//          ],
//
//          declarations: [                       // 선언 지도 — which config says what
//            { source: "ledger_config",
//              file: "server/config/ledger_config.json",
//              title: "소스 → 원장 번역",
//              items: [ { term: "lot_event · split", detail: "…",
//                         edges: [ { subject_type, predicate, object_kind } ] } ] }
//          ]
//        }
//
// CHANGING WHAT THIS CONSUMES IS AN ESCALATION, NOT AN EDIT — and so is the
// server lane answering a different shape. A 404 leaves the model at state
// 'unknown' and the screen says so out loud instead of drawing an empty world.
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

  // ── vocabulary and types, as the server declared them ──
  const predRows = body && Array.isArray(body.predicates) ? body.predicates : [];
  const predicates = new Map();
  for (const row of predRows) {
    const sig = readPredicate(row);
    if (sig.predicate) predicates.set(sig.predicate, sig);
  }

  const typeRows = body && Array.isArray(body.entity_types) ? body.entity_types : [];
  const entityTypes = new Map();
  for (const row of typeRows) {
    const t = readEntityType(row);
    if (t.type) entityTypes.set(t.type, t);
  }

  // ── the declared skeleton ──
  const edges = new Map();
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
    const merged = {
      key,
      subjectType,
      predicate,
      objectKind,
      declaredTypes: prior ? prior.declaredTypes : [],
      observedTypes: listOf(row.object_types),
      atoms: numOrNull(row.atoms),
      firstAt: strOrEmpty(row.first_at),
      lastAt: strOrEmpty(row.last_at),
      classes: row.classes && typeof row.classes === 'object' ? row.classes : null,
      declared: !!prior,
      observed: true,
    };
    edges.set(key, merged);
    // Vocabulary the ledger holds and the declaration does not. It gets a node so
    // the edge has somewhere to land, and it is marked so it reads as the finding
    // it is rather than as a normal part of the world.
    if (!predicates.has(predicate)) predicates.set(predicate, ghostPredicate(predicate));
    if (!entityTypes.has(subjectType)) entityTypes.set(subjectType, ghostEntityType(subjectType));
  }

  // 🔴 AN EDGE HAS TWO POSSIBLE ORIGINS AND THE SCREEN MUST NOT CONFLATE THEM
  // (lead PM, 2026-08-14): one comes out of the LEDGER AGGREGATE and carries a
  // count, a period and a grade mix; the other comes out of the DECLARATION ALONE
  // and its count may be zero. The tracking UI's verdict gate is about to become
  // the FIRST consumer of the M4 mechanism graph, so "declared, zero consumers"
  // is a thing the owner comes to this screen looking for.
  //
  // 🔴 AND THAT MEANS A MEASURED ZERO MUST NOT RENDER AS 미보고. The two are
  // different facts and this file has already been warned once about the shape:
  // an absent FIELD is not a measurement, but a GROUP BY that ran and produced no
  // group for a declared axis IS one — the axis was looked for and found empty.
  // So the zero is claimable exactly when the aggregate actually ran over a
  // deployed table, and unclaimable otherwise.
  //
  //   state ready | empty  + an `edges` array  ->  a declared axis with no row is 0
  //   anything else                            ->  it is 미보고, and says so
  const aggregateRan = Array.isArray(body && body.edges)
    && (state === 'ready' || state === 'empty');

  // ── status per edge, and the layer filter ──
  const layerFilter = q.layer || '';
  const allEdges = [...edges.values()].map((e) => {
    // A declared axis the aggregate did not report is a zero ONLY if the
    // aggregate is in a position to have reported it.
    const atoms = (e.atoms === null && e.declared && !e.observed && aggregateRan) ? 0 : e.atoms;
    let status;
    if (!e.declared) status = 'undeclared';
    else if (atoms !== null && atoms > 0) status = 'flowing';
    else if (atoms === 0) status = 'declared_zero';
    else status = 'declared_unmeasured';
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
      layer: sig ? sig.layer : '',
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
        sub: known && known.keys.length ? `키 ${known.keys.join(' · ')}` : objectKindLabel(e.objectKind),
        declared: !!known,
      };
    } else {
      id = `obj:kind:${e.objectKind || 'none'}`;
      node = {
        id,
        kindOfNode: 'object',
        objectKind: e.objectKind,
        type: '',
        label: objectKindLabel(e.objectKind),
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
  const rawKinds = kindsBody && Array.isArray(kindsBody.kinds) ? kindsBody.kinds : [];
  const tableOf = new Map();
  for (const row of rawKinds) {
    if (row && row.kind != null) tableOf.set(String(row.kind), strOrEmpty(row.observation_table));
  }
  const kindRows = (kinds && Array.isArray(kinds.kinds) ? kinds.kinds : []).map((k) => ({
    ...k,
    observationTable: tableOf.get(k.kind) || '',
  }));

  // ── declaration map ──
  const declRows = body && Array.isArray(body.declarations) ? body.declarations : [];
  const declarations = declRows.map((d) => ({
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
      };
    }),
  }));

  const totals = {
    edges: allEdges.length,
    flowing: allEdges.filter((e) => e.status === 'flowing').length,
    declaredZero: allEdges.filter((e) => e.status === 'declared_zero').length,
    declaredUnmeasured: allEdges.filter((e) => e.status === 'declared_unmeasured').length,
    undeclared: allEdges.filter((e) => e.status === 'undeclared').length,
    atoms: allEdges.reduce((s, e) => s + (e.atoms || 0), 0),
    reported: allEdges.some((e) => e.atoms !== null),
    aggregateRan,
  };

  return {
    state,
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
      const RANK = { flowing: 0, undeclared: 1, declared_zero: 2, declared_unmeasured: 3 };
      const rank = (e) => (RANK[e.status] === undefined ? 4 : RANK[e.status]);
      if (rank(a) !== rank(b)) return rank(a) - rank(b);
      const aa = a.atoms === null ? -1 : a.atoms;
      const bb = b.atoms === null ? -1 : b.atoms;
      if (aa !== bb) return bb - aa;
      return a.key < b.key ? -1 : 1;
    }).map((e) => ({ ...e, selected: !!q.edge && q.edge === e.key })),
    vocabulary,
    kinds: {
      state: kinds && kinds.state ? kinds.state : 'unknown',
      rows: kindRows,
    },
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
