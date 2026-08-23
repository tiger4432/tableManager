// ═══════════════════════════════════════════════════════════════════════════════
// THE API BOUNDARY for the R&D board. Fetch on one side, a plain model on the other.
//
// 🔴 EVERY SHAPE BELOW WAS COPIED FROM A LIVE RESPONSE, NOT INVENTED. Measured
//    2026-08-23 against the running stack (`127.0.0.1:8080`):
//
//      GET /api/ledger/lot_map?row=SYN-VOID-001&slot=07&kind=void   200, 13,123 bytes
//        top-level  row · state · generated_at · kind · row_axis · slot · slot_column
//                   · window · projections · provenance
//        projection axis · label · sublabel · state · reason · message · frame
//                   · coordinate_unit · cells · found · scanned
//        bond       state "ready", 141 cells, found 13, scanned 29,
//                   frame {state, table:"bonding_log", map_id:"SYN-VOID-001_07",
//                          grid:<grid_metadata>, valid_die_ref:{relation,present,map_id},
//                          wafer:"SYN-BW-001-07"}
//        cell       {x, y, n, state}   state ∈ scanned(16) · unscanned(112) · found(13)
//                   x 0..13, y 0..13   coordinate_unit "cells_from_origin"
//        dt / core  state "no_frame", reason "frame_ambiguous_across_slots",
//                   frame {state, reason, available_slots[25], available_lots,
//                          frames_considered, frames_matched, superposed, wafer}
//
// 🔴 THE CLIENT DOES NOT ENUMERATE KINDS, AND THAT INCLUDES COLOUR. A cell's colour comes
//    from a ROLE that arrives with the cell (`color_role`, falling back to the cell's own
//    `state` string, which is what today's route serves). This module never tests a role
//    against a list of names it knows; the view resolves whatever string arrives through one
//    table and gives an unfamiliar role a neutral colour rather than dropping the cell. A
//    `kind -> colour` map in the client is the same defect as a `kind` list in the client.
//
// 🔴 ONE MEASURED GAP, NAMED RATHER THAN HIDDEN: `cells` CARRY NO NODE ID.
//    A marking is a set of node ids (`task/APPLICATION_MARKING_UNIT_BRIEF.md` §1), and the
//    served cells have none -- §4 of that same brief already records why (a map die is not a
//    resolvable node yet: 「die 노드를 마킹 대상으로 못 만든다」, blocked behind a frozen v1
//    entity list). So the id is stamped HERE, at the boundary, in the field the server will
//    serve (`node_id`), and every component upstream reads `cell.node_id` and cannot tell the
//    difference. The day `lot_map` serves it, `stampedNodeId` stops being called and NO
//    component changes.
//    ⚠️ The stamped string is NOT an ontology node id and must never be handed to a walk as a
//    seed. It is stable and collision-free ACROSS PANELS (it keys off the frame's own
//    identity), which is the only property the marking contract needs from it: two panels
//    showing the same die agree on the same string.
// ═══════════════════════════════════════════════════════════════════════════════

export const ROUTES = Object.freeze({
  lotMap: '/api/ledger/lot_map',
  composition: '/api/ledger/composition',
  subgraph: '/api/ledger/subgraph',
  trends: '/api/ledger/trends',
});

/**
 * `GET /api/ledger/lot_map`. `fetchImpl` is injected so the boundary is scorable without a
 * network; the page passes the platform's.
 */
export async function fetchLotMap(params) {
  const { apiBase, row, slot, kind, by, window: win, fetchImpl } = params;
  const query = new URLSearchParams();
  query.set('row', row);
  if (slot) query.set('slot', slot);
  if (kind) query.set('kind', kind);
  if (by) query.set('by', by);
  if (win) query.set('window', win);
  const doFetch = fetchImpl || globalThis.fetch;
  const res = await doFetch(`${apiBase}${ROUTES.lotMap}?${query.toString()}`);
  if (!res.ok) {
    const err = new Error(`HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

/** The frame's own identity, for the stamped id. Whichever of these the frame carries. */
function frameIdentity(frame) {
  if (!frame) return 'no-frame';
  return frame.wafer || frame.map_id || frame.table || 'no-frame';
}

/** See the header: a PLACEHOLDER for the node id the route does not yet serve. */
function stampedNodeId(axis, frame, cell) {
  return `unresolved-die:${axis}:${frameIdentity(frame)}:${cell.x},${cell.y}`;
}

/**
 * One projection of a `lot_map` body, as a plain model.
 *
 * Refusals are CONTENT, not an absence: a projection the server could not draw comes back
 * with `drawable: false` and the server's OWN sentence, and the view prints that instead of
 * inventing a wafer. Nothing here manufactures a grid, a circle, or a cell.
 *
 * @returns {{axis, label, sublabel, drawable, state, reason, message, cells, found, scanned,
 *            frame, coordinateUnit, row, slot, kind}}
 */
export function projectionModel(body, axis) {
  const projections = (body && body.projections) || [];
  const p = projections.find((x) => x && x.axis === axis) || null;
  if (!p) {
    return {
      axis,
      label: axis,
      sublabel: '',
      drawable: false,
      state: 'absent',
      reason: 'axis_not_served',
      message: `${axis} 축이 응답에 없습니다`,
      cells: [], found: 0, scanned: 0, frame: null,
      coordinateUnit: null,
      row: (body && body.row) || null,
      slot: (body && body.slot) || null,
      kind: (body && body.kind) || null,
    };
  }
  const frame = p.frame || null;
  const cells = (p.cells || []).map((cell) => ({
    x: cell.x,
    y: cell.y,
    n: cell.n,
    // The role the view colours by. Served field first; today's route serves `state`.
    colorRole: cell.color_role || cell.state || null,
    nodeId: cell.node_id || stampedNodeId(axis, frame, cell),
    nodeIdResolved: Boolean(cell.node_id),
  }));
  return {
    axis: p.axis,
    label: p.label || p.axis,
    sublabel: p.sublabel || '',
    // 🔴 DRAWABLE IS THE SERVER'S VERDICT, READ -- not re-derived from the cell count. A
    // refused projection can still carry cells (measured: dt refuses and carries 11), and
    // drawing them would be putting coordinates from several frames onto one lattice.
    drawable: p.state === 'ready',
    state: p.state || null,
    reason: p.reason || null,
    message: p.message || null,
    cells,
    found: p.found || 0,
    scanned: p.scanned || 0,
    frame,
    coordinateUnit: p.coordinate_unit || null,
    row: (body && body.row) || null,
    slot: (body && body.slot) || null,
    kind: (body && body.kind) || null,
  };
}


// ═══════════════════════════════════════════════════════════════════════════════
// COMPOSITION -- 「이 최종 칩은 무엇으로 만들어졌나」. ONE route feeds TWO parts (A 머리 요약,
// D 구성), which is why they were ordered together.
//
// 🔴 THE QUERY KEY IS `final_chip_id`, NOT `id`. Measured: `?id=` answers 422 with
//    `{"loc":["query","final_chip_id"],"msg":"Field required"}`. Written down because a
//    guessed key returns a REFUSAL, and a refusal rendered as an empty panel reads as
//    「이 칩은 구성이 없다」 -- which is the absence-vs-fault confusion this board exists to end.
// ═══════════════════════════════════════════════════════════════════════════════

/** `GET /api/ledger/composition`. `fetchImpl` injected so the boundary scores without a network. */
export async function fetchComposition(params) {
  const { apiBase, finalChipId, fetchImpl } = params || {};
  const query = new URLSearchParams();
  query.set('final_chip_id', finalChipId);
  const url = `${apiBase}${ROUTES.composition}?${query.toString()}`;
  const res = await (fetchImpl || fetch)(url);
  if (!res.ok) {
    // The refusal is CARRIED, not swallowed. A part renders "the server refused, here is why",
    // never a blank box.
    let detail = null;
    try { detail = await res.json(); } catch (e) { detail = null; }
    return { ok: false, status: res.status, detail, body: null };
  }
  return { ok: true, status: res.status, detail: null, body: await res.json() };
}

/**
 * The view model both parts read. NO DOM -- so it is scorable under bare node, the discipline
 * `surprise_map_view.js` established and `panel.js` restates.
 *
 * 🔴 EVERY FIELD IS SOURCED. Nothing is defaulted into a number that looks measured: a missing
 *    count is `null` and the parts print 「-」 for it. `cardinality` arrives as the WORD the
 *    server chose ('variable'), not as a number, and it stays a word -- turning it into `10`
 *    would state a constant the ledger explicitly refuses to claim.
 *
 * 🔴 `windowDefaulted` IS AN ABSENCE, NOT A FAULT. It means nobody chose a period, so the
 *    server applied its own. A part must say that in different words from a refusal.
 */
export function compositionModel(result) {
  const failed = !result || result.ok === false;
  const body = (result && result.body) || null;
  if (failed || !body) {
    const status = (result && result.status) || null;
    return {
      ok: false,
      state: 'refused',
      status,
      message: status ? `서버가 거절했습니다 (HTTP ${status})` : '응답이 없습니다',
      subject: null, wafer: null, resolution: null, window: null,
      cardinality: null, provenance: null,
      counts: { components: null, dtCollections: null },
      coreTypes: [], components: [],
    };
  }
  const fsr = body.final_subject_resolution || {};
  const win = body.window || {};
  const applied = win.applied || {};
  const summary = body.summary || {};
  const card = body.cardinality || {};
  const prov = body.provenance || {};
  const num = (v) => (typeof v === 'number' ? v : null);
  return {
    ok: true,
    state: body.state || 'unknown',
    status: (result && result.status) || null,
    message: '',
    subject: {
      finalChipId: (body.final_chip && body.final_chip.keys && body.final_chip.keys.final_chip_id) || null,
      entityId: (body.final_chip && body.final_chip.entity_id) || null,
    },
    // The wafer the chip was resolved onto. `null` when the ledger could not resolve one --
    // which is a STATE, and `resolution.state` carries which one.
    wafer: fsr.wafer ? { id: fsr.wafer.wafer || null, entityId: fsr.wafer.entity_id || null } : null,
    resolution: {
      state: fsr.state || 'unknown',
      basis: fsr.basis || null,
      candidateCount: Array.isArray(fsr.candidates) ? fsr.candidates.length : null,
    },
    window: {
      spec: applied.spec || null,
      from: applied.from || null,
      to: applied.to || null,
      declared: applied.declared === true,
      defaulted: win.defaulted === true,
      requested: win.requested || null,
    },
    cardinality: {
      components: card.components || null,
      transferEvents: card.transfer_events || null,
      dtCollections: card.dt_collections || null,
    },
    provenance: {
      source: prov.source || null,
      predicate: prov.predicate || null,
      ledgerBacked: prov.ledger_backed === true,
    },
    counts: {
      components: num(summary.component_count),
      dtCollections: num(summary.dt_collection_count),
    },
    coreTypes: Array.isArray(summary.core_types) ? summary.core_types.slice() : [],
    components: (Array.isArray(body.components) ? body.components : []).map((c) => ({
      id: c.component_id || null,
      entityId: c.entity_id || null,
      core: c.core || null,
      bonding: c.bonding || null,
      resolutionState: c.resolution_state || 'unknown',
      transferEventCount: Array.isArray(c.transfer_events) ? c.transfer_events.length : null,
      // 목업의 「이력 4 ›」. The derived_from chain the ledger already walked for this core --
      // a COUNT of events, and `null` when the response carried no lineage at all.
      lineage: c.core && c.core.lineage
        ? {
          state: c.core.lineage.state || null,
          events: Array.isArray(c.core.lineage.events) ? c.core.lineage.events.length : null,
        }
        : null,
      dtCollectionCount: Array.isArray(c.dt_collections) ? c.dt_collections.length : null,
    })),
  };
}


// ═══════════════════════════════════════════════════════════════════════════════
// SUBGRAPH -- 「이 웨이퍼 왜 이런가」. ONE route feeds TWO parts (F 후보 리스트, G 순위 리스트).
//
// 🔴 THREE THINGS WERE MEASURED, NOT ASSUMED, AND EACH WOULD HAVE PUT A FALSE SENTENCE ON THE
//    SCREEN:
//
//    1. `id` IS A NODE ID, not a wafer name. `?id=SYN-BW-103-11` answers 422
//       `subgraph_request_invalid`; `?id=ledger-entity:v1:<b64>` answers 200.
//    2. `ranked` AND `top_set` LIVE INSIDE `propagation`, not at the top level. Reading
//       `body.ranked` returns undefined, which renders as 「걷기가 아무것도 못 찾았다」 -- a claim
//       about the wafer. It found 25.
//    3. THE ROWS CARRY NO `kind`, `sublabel`, `detail` OR `color_role`. The order named that
//       shape; this route does not serve it today. So the one distinction the screen exists to
//       draw is DERIVED from the evidence hops, per the Lead PM's own rule, and `measured` below
//       is that derivation and nothing else.
//
// 🔴 `measured` IS THE WHOLE POINT OF THIS SCREEN. A candidate whose hops are all `quantity`
//    pointing at `mechanism_models.json` is a NAME the model declares; one with a `value` or
//    `claim` hop has something an engineer can go and look at. Measured on the live seed:
//    4 of 25. If those two look alike, the engineer walks to the 21 and finds nothing there.
// ═══════════════════════════════════════════════════════════════════════════════

/** `GET /api/ledger/subgraph`. `fetchImpl` injected so the boundary scores without a network. */
export async function fetchSubgraph(params) {
  const { apiBase, nodeId, collect, fetchImpl } = params || {};
  const query = new URLSearchParams();
  query.set('id', nodeId);
  query.set('collect', collect || 'quantity');
  const url = `${apiBase}${ROUTES.subgraph}?${query.toString()}`;
  const res = await (fetchImpl || fetch)(url);
  if (!res.ok) {
    let detail = null;
    try { detail = await res.json(); } catch (e) { detail = null; }
    return { ok: false, status: res.status, detail, body: null };
  }
  return { ok: true, status: res.status, detail: null, body: await res.json() };
}

// ═══════════════════════════════════════════════════════════════════════════════
// ⚠️ TEMPORARY BOUNDARY ADAPTER -- DELETE THIS FUNCTION WHEN THE SERVER SERVES THE FIELD.
//
// Lead PM ruling 2026-08-23: the derivation is ADOPTED because 「가서 볼 수 있는 것」 and
// 「모델이 붙인 이름」 must be told apart or the rank table means nothing -- but a client
// INTERPRETING ontology meaning is temporary, and the same ruling already applies to the map
// cell's `node_id` placeholder. It is collected here, in ONE function, so the day
// `/api/ledger/subgraph` serves the distinction itself, this function disappears and NO PART
// IS TOUCHED.
//
// What it decides: a hop of kind `value` or `claim` reaches something an engineer can go and
// look at. Hops that are all `quantity` are a name `mechanism_models.json` declares.
//
// ⚠️ It counts WALKS, not declarations. The order said 3 of 25; this says 4 of 25, and the
//    Lead PM ruled the 4 correct -- their 3 counted rows with a model binding, which is a
//    different question. `post_bond_queue_h · void_observation_bias` is the extra: it reaches
//    a claim atom (`mes_queue:SYN-BW-103-11`) and a value hop.
// ═══════════════════════════════════════════════════════════════════════════════
export function measuredFromHops__untilServerServesIt(row) {


  for (const ev of row.evidence || []) {
    for (const hop of ev.hops || []) {
      if (hop && (hop.node_kind === 'value' || hop.node_kind === 'claim')) return true;
    }
  }
  return false;
}

/**
 * The view model both parts read. NO DOM.
 *
 * 🔴 THE FIVE ABSENCES ARE CARRIED SEPARATELY AND NONE OF THEM IS AN ERROR:
 *      contrast 'unexamined'  나는 또래를 «안 쟀다»   != 「깨끗했다」
 *      complete false          예산에서 끊겼다        != 「없다」
 *      state 'empty'           물리량에 «안 닿았다»   != 「원인 없음」
 *      tied                    동률                  != 순서가 있는 척
 *      incomparable            종류가 다름            != 더 낮음
 *    A part that collapses any two of these has told the operator something the ledger did not.
 */
export function subgraphModel(result) {
  const failed = !result || result.ok === false;
  const body = (result && result.body) || null;
  if (failed || !body) {
    const status = (result && result.status) || null;
    const reason = (result && result.detail && result.detail.detail && result.detail.detail.reason) || null;
    return {
      ok: false, state: 'refused', status, reason,
      message: status ? `서버가 거절했습니다 (HTTP ${status})` : '응답이 없습니다',
      contrast: null, complete: null, candidates: [], topSet: [],
      graph: { nodes: 0, edges: 0 },
      counts: { total: 0, measured: 0, nameOnly: 0, tied: 0, incomparable: 0 },
    };
  }
  const prop = body.propagation || {};
  const rows = Array.isArray(prop.ranked) ? prop.ranked : [];
  const candidates = rows.map((row) => {
    // The label is 「물리량 · 모델」 joined by U+00B7 -- measured, one separator, nothing else.
    // 🔴 SPLIT, NEVER MERGE. The same quantity appears under two models, and joining them
    //    states a third claim nobody made.
    const parts = String(row.label || '').split('·');
    return {
      id: row.id || null,
      quantity: (parts[0] || '').trim() || String(row.label || ''),
      model: (parts[1] || '').trim() || null,
      rank: typeof row.rank === 'number' ? row.rank : null,
      top: row.top === true,
      tied: row.tied === true,
      incomparable: row.incomparable === true,
      measured: measuredFromHops__untilServerServesIt(row),
      hopCount: (row.evidence || []).reduce((n, ev) => Math.max(n, (ev.hops || []).length), 0),
      evidence: (row.evidence || []).map((ev) => ({
        seed: ev.seed || null,
        sign: ev.sign || null,
        hops: (ev.hops || []).map((h) => ({
          id: h.id || null, kind: h.node_kind || null, label: h.label || '',
          ref: h.ref || null,
          // A hop that points at the model file is a DECLARATION; one that points elsewhere is
          // a thing in the world. The parts show that difference rather than the raw string.
          declaredOnly: h.node_kind === 'quantity',
        })),
      })),
    };
  });
  const measured = candidates.filter((c) => c.measured).length;
  return {
    ok: true,
    state: prop.state || 'unknown',
    status: (result && result.status) || null,
    reason: null,
    message: prop.message || '',
    // 'unexamined' is the value today, and it means NOBODY LOOKED -- not that nothing was found.
    // 🔴 WHAT THE WALK DID REACH, carried even when `state` is 'empty'. Lead PM correction
    // 2026-08-23: `collect=quantity` answering `ranked: []` on a die seed does NOT mean there
    // are no edges -- the same seed under `collect=entity` returns 2. There were 4 nodes and 3
    // edges the whole time. A part that says 「연결 없음」 has denied a transfer that happened.
    graph: {
      nodes: Array.isArray(body.nodes) ? body.nodes.length : 0,
      edges: Array.isArray(body.edges) ? body.edges.length : 0,
    },
    contrast: prop.contrast || null,
    complete: prop.complete === true,
    candidates,
    topSet: Array.isArray(prop.top_set) ? prop.top_set.slice() : [],
    counts: {
      total: candidates.length,
      measured,
      nameOnly: candidates.length - measured,
      tied: candidates.filter((c) => c.tied).length,
      incomparable: candidates.filter((c) => c.incomparable).length,
    },
  };
}


// ═══════════════════════════════════════════════════════════════════════════════
// TRENDS -- 「이 불량이 어떻게 움직였나」, and the route that makes 「점을 찍으면 그것이 씨앗」
// possible at all.
//
// 🔴 MEASURED 2026-08-23, `?kinds=void&window=180d`:
//    1. `grain` IS OPTIONAL AND THE SERVER DEFAULTS IT. Passing `grain=wafer` is a REFUSAL --
//       `bad_trend_grain`, 「grain을 JSON으로 해석할 수 없다」 -- because the parameter is a JSON
//       object, not a name. Omitted, the answer carries the grain it chose, which is what this
//       screen shows rather than a word this client made up.
//    2. EVERY POINT CARRIES `identity.mark_key`. That is the id a click marks: the trend does
//       not invent a subject, it hands over the one the ledger already named.
//    3. `value.found_rate` has its numerator and denominator DECLARED in `provenance`
//       (observed / inspection_run, `absence_is_zero: false`). The legend prints that, because
//       a rate whose denominator is unstated is a number nobody can check.
//    4. `selectable_finding_kinds` is the list of ratio axes -- 2 today (void, delam). The
//       control bar's pills are that list, not a list this client keeps.
// ═══════════════════════════════════════════════════════════════════════════════

/** `GET /api/ledger/trends`. `grain` is deliberately NOT sent -- see the header. */
export async function fetchTrends(params) {
  const { apiBase, kinds, window: win, fetchImpl } = params || {};
  const query = new URLSearchParams();
  if (kinds) query.set('kinds', kinds);
  query.set('window', win || '180d');
  const url = `${apiBase}${ROUTES.trends}?${query.toString()}`;
  const res = await (fetchImpl || fetch)(url);
  if (!res.ok) {
    let detail = null;
    try { detail = await res.json(); } catch (e) { detail = null; }
    return { ok: false, status: res.status, detail, body: null };
  }
  return { ok: true, status: res.status, detail: null, body: await res.json() };
}

/**
 * @returns {{ok, state, points: Array, kinds: Array, provenance, message}}
 *          A point is `{wafer, leg, at, rate, state, markKey, denominator}`. Nothing is
 *          defaulted: a point whose `found_rate` is missing keeps `rate: null` and the view
 *          draws it as unmeasured rather than as zero -- `absence_is_zero` is FALSE here and
 *          this is the one place that could quietly make it true.
 */
export function trendsModel(result) {
  if (!result || !result.ok) {
    const detail = (result && result.detail) || {};
    const inner = detail.detail || detail;
    return {
      ok: false, state: 'refused', points: [], kinds: [], provenance: null,
      message: inner.message || inner.reason || `HTTP ${(result && result.status) || '?'}`,
    };
  }
  const body = result.body || {};
  const series = body.series || [];
  const points = [];
  for (const s of series) {
    for (const p of s.points || []) {
      const identity = p.identity || {};
      const value = p.value || {};
      points.push({
        seriesId: s.id || null,
        wafer: (identity.keys || {}).wafer || null,
        leg: (identity.context || {}).bonding_leg || null,
        at: p.occurred_at || null,
        rate: typeof value.found_rate === 'number' ? value.found_rate : null,
        denominator: typeof value.scan_denominator === 'number' ? value.scan_denominator : null,
        state: value.state || null,
        markKey: identity.mark_key || null,
      });
    }
  }
  const prov = body.provenance || {};
  return {
    ok: true,
    state: body.state || null,
    points,
    kinds: (body.selectable_finding_kinds || []).map((k) => ({
      id: k.id, label: k.label || k.id, active: Boolean(k.active),
    })),
    provenance: {
      numerator: (prov.numerator || {}).predicate || null,
      denominator: (prov.denominator || {}).source || null,
      absenceIsZero: Boolean((prov.denominator || {}).absence_is_zero),
    },
    message: null,
  };
}
