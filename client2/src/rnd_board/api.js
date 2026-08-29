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
  siblings: '/api/ledger/siblings',
  // 🔴 NOT UNDER `/api` -- measured 2026-08-28: `/api/tables/...` answers 404 and this answers
  //    200. It is the generic declared-relation reader, not a ledger route, which is the whole
  //    point: the grid is physics the operator declared, so it comes from the relation itself.
  mapGrid: '/tables/wafer_map_metadata/data',
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

// 🔴 THIS FILE MINTS THE PLACEHOLDER, SO THIS FILE GATES IT. `task/MARKING_CONTRACT.md` §4:
//    only a node id the SERVER gave may become a marking, because a stamped one sends the
//    walk off a node that does not exist and the empty answer that comes back cannot be told
//    apart from 「없다」. The prefix is not a domain word -- it is this module's own namespace,
//    kept beside the function that writes it so the two cannot drift.
const STAMPED_PREFIX = 'unresolved-die:';

/** True when `id` is one this client invented rather than one the server served. */
export function isStampedNodeId(id) {
  return typeof id === 'string' && id.startsWith(STAMPED_PREFIX);
}

/** See the header: a PLACEHOLDER for the node id the route does not yet serve. */
function stampedNodeId(axis, frame, cell) {
  return `${STAMPED_PREFIX}${axis}:${frameIdentity(frame)}:${cell.x},${cell.y}`;
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
      coordinateUnit: null, relations: [], ledgerBacked: false, unplaced: null,
      row: (body && body.row) || null,
      slot: (body && body.slot) || null,
      kind: (body && body.kind) || null,
    };
  }
  const frame = p.frame || null;
  const prov = (body && body.provenance) || {};
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
    // 🔴 WHAT THE COUNTS ARE COUNTS OF. Measured 2026-08-24: 「검사 29」 is scanned AND bonded --
    //    a die that was inspected but has no bonding row drops out of the join, and the screen
    //    said 29 where the source says 30. The number is the server's to fix; the LABEL is
    //    this screen's, and a label that cannot say what it counts is how that stayed invisible.
    //    So the relations ride through and the panel prints them; when the server changes what
    //    it joins, the words on screen change with it.
    // 🔴 WHAT THE MAP CANNOT PLACE, AS A NUMBER OR AS 「모른다」 -- never as a zero. Measured
    //    2026-08-24: 2,527 inspected seats have no process row and no bond/dt/cx coordinate, so
    //    no axis can draw them. On this row the server answers `state: "unknown"` because the
    //    row axis cannot attribute them at all, and it says so in its own sentence. A screen
    //    that printed 0 there would be claiming they do not exist.
    unplaced: (body && body.unplaced)
      ? {
        state: body.unplaced.state || 'unknown',
        scanned: typeof body.unplaced.scanned === 'number' ? body.unplaced.scanned : null,
        found: typeof body.unplaced.found === 'number' ? body.unplaced.found : null,
        reason: body.unplaced.reason || null,
        message: body.unplaced.message || null,
      }
      : null,
    relations: Array.isArray((prov || {}).relations) ? prov.relations.slice() : [],
    ledgerBacked: (prov || {}).ledger_backed === true,
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
 * `surprise_map_view.js` (지금은 없는 파일, 2026-08-25 삭제) established and `panel.js` restates.
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
      // 목업 ② 의 스텝 빵부스러기. MEASURED: `upstream_process.evidence_ids[]` carries `step`
      // and `occurred_at` for the core wafer -- INGOT_RELEASE › WAFER_SORT › … So the
      // breadcrumb is a fact the ledger already holds, not a path this client assembles.
      steps: (((c.upstream_process || {}).evidence_ids) || [])
        .map((e) => ({ step: e.step || null, at: e.occurred_at || null }))
        .filter((e) => e.step),
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
  const { apiBase, nodeId, fetchImpl, positive, negative,
          node_limit: nodeLimit, hops, follow, direction,
          continues_hops: continuesHops } = params || {};
  // 🔴 THE GATE (contract §4). Refused HERE rather than at the server, because the server
  //    would answer 200 with an empty walk and the screen would read that as 「없다」.
  //    A refusal is CONTENT: `subgraphModel` already renders `ok:false` with its reason.
  if (isStampedNodeId(nodeId)) {
    return { ok: false, status: null, body: null,
             detail: { detail: { reason: 'seed_is_not_a_server_node' } } };
  }
  const query = new URLSearchParams();
  query.set('id', nodeId);
  // 🔴 `collect` LEFT 2026-08-28 (round Z). It was TRUE and load-bearing when it was written:
  //    the walk collected one node KIND and this argument chose which, and naming it here was
  //    the fix for a screen that had been landing on the server default by accident. Revision 6
  //    ended the kinds -- every node is a declared entity now -- and the route dropped the
  //    parameter the same day, so the server had been IGNORING this line rather than refusing
  //    it: no error, no warning, and a screen that looked like it was still asking. What
  //    narrows a walk is `follow`, which is a predicate the declaration owns.
  // The signed sets the route already declares. Absent lists change nothing: a request that
  // names neither reaches the server exactly as it did before.
  for (const id of positive || []) query.append('positive', id);
  for (const id of negative || []) query.append('negative', id);
  // 🔴 THE BUDGET, CARRIED. Measured 2026-08-24: this boundary DROPPED both, so a part could
  //    read `truncated: ["nodes"]` and had no way to ask for more -- the screen could name the
  //    cut and never lift it. Omitted stays omitted, so the server's own default still applies
  //    and a request that names neither is byte-identical to before.
  if (nodeLimit !== undefined && nodeLimit !== null) query.set('node_limit', String(nodeLimit));
  if (hops !== undefined && hops !== null) query.set('hops', String(hops));
  // 🔴 «자재 예산»은 선언한 부품만 싣습니다 (라운드 ③, 2026-08-29). follow 와 «같은 모양»:
  //    없으면 안 싣고, 안 실으면 서버 기본 0 이라 오늘과 «완전히 같은» 답입니다.
  //    실측 2026-08-29: 돌고 있는 서버가 이 인자를 «진짜로 파싱»합니다 -- -1 · 99 · abc 가
  //    전부 422 이고 선언이 ge=0 le=40 입니다. 다만 라이브 선언에 `continues: true` 술어가
  //    «0» 이라 오늘은 어떤 값을 줘도 답이 같습니다. 그 플래그가 오는 날 이 줄이 값을 냅니다.
  if (continuesHops !== undefined && continuesHops !== null) {
    query.set('continues_hops', String(continuesHops));
  }
  // 🔴 THE DECLARED QUESTION, CARRIED. `follow` is NOT a speed knob -- it decides WHICH
  //    ANSWERS CAN EXIST. Measured by the Lead PM 2026-08-24: narrowing it to the observation
  //    predicates loses four `delam_formation` candidates outright, because those reach through
  //    `processed_with`/`transferred`. So the DECLARATION names it, never this function.
  //    Same shape as the signed sets and the budget above: absent stays absent, so a request
  //    that names neither is byte-identical to the one this boundary sent before.
  for (const p of follow || []) query.append('follow', p);
  if (direction) query.set('direction', direction);
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
export function measuredFromHops__untilServerServesIt(row, edges) {
  // 🔴 THE QUESTION HAS NEVER CHANGED: 「이 후보는 «가서 볼 수 있는 것»에 닿았나」. What keeps
  // changing is the name the walk gives that thing, and this is its third. The two earlier
  // names stay written down because deleting them would make this read like a rule that was
  // always wrong, and it was not -- each was true when it was written:
  //
  //    ~2026-08-25  `claim || value`, both node kinds. TRUE then.
  //     2026-08-25  a claim became an EDGE, so the `claim` arm could never fire again and only
  //                 `value` survived. Still a real rule, and dropping `claim` was the fix
  //                 rather than a loss: MEASURED on the old code, seed `SYN-CX-BW-001`, 21 of
  //                 21 candidates had a claim hop and 0 of 21 a value hop, so the arm that
  //                 died was the one that had been answering "yes" to everything.
  //     2026-08-28  revision 6 landed and every node the walk returns became a declared
  //                 ENTITY -- measured `{ entity: 507 }` on that same seed. `node_kind ===
  //                 'value'` stopped being a rule that can answer 「없다」 and became one that
  //                 cannot answer at all: permanently false, with no error and no log.
  //
  // 🔴 SO THE ANSWER MOVED FROM THE NODE TO THE EDGE, because that is where the ledger put it.
  // `measures@1` (wafer@1 -> quantity@1, 80,322 atoms) landed the same day and carries the
  // reading in its qualifiers. A trail that crosses one has touched something an engineer can
  // go and look at; a trail that only crosses `leads_to` is a name the declaration asserts.
  //
  // 🔴 NO NEW FIELD AND NO DECODER. The predicate is not on a hop and does not need to be: the
  // response already carries `edges[].{source,target,predicate}` (`ledger_subgraph.py:854`),
  // so a pair of consecutive hop ids IS the lookup key. The Lead PM cancelled the server-side
  // "put predicate on the hop" order once this was measured.
  //
  // ⚠️ UNDIRECTED ON PURPOSE. A hop pair is one step along the parent chain, and the chain
  // crosses the edge in whichever direction reached the node. Testing a single orientation
  // would answer 「없다」 for every trail that arrived from the quantity side.
  const crossings = new Set();
  for (const edge of edges || []) {
    if (!edge || edge.predicate !== 'measures') continue;
    crossings.add(`${edge.source} -> ${edge.target}`);
    crossings.add(`${edge.target} -> ${edge.source}`);
  }
  if (crossings.size === 0) return false;
  for (const ev of row.evidence || []) {
    const hops = ev.hops || [];
    for (let i = 1; i < hops.length; i += 1) {
      const from = hops[i - 1] && hops[i - 1].id;
      const to = hops[i] && hops[i].id;
      if (from && to && crossings.has(`${from} -> ${to}`)) return true;
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
// 🔴 THE SERVER SAYS WHICH BUDGET BOUND, AS FLAGS; THE PARTS WANT NAMES. This carries it
//    across and does not interpret: every flag the server set true becomes its own name and
//    nothing is merged, because 「깊이에서 잘림」 and 「노드 상한에서 잘림」 are different
//    answers -- one is 「홉을 늘리면 더 나온다」 and the other 「더 있는데 못 봤다」.
//
// 🔴 ABSENT IS NOT FALSE. A response with no `truncated` is a boundary that has not landed,
//    NOT a walk that ran to completion, so it returns `null` rather than `[]`. Turning an
//    absent field into a confident empty is exactly what blanked the maps this morning
//    (`placements`), and that mistake is not repeating in this file.
function truncationNames(raw) {
  if (!raw || typeof raw !== 'object') return null;
  return Object.keys(raw).filter((key) => raw[key] === true);
}

export function subgraphModel(result) {
  const failed = !result || result.ok === false;
  const body = (result && result.body) || null;
  if (failed || !body) {
    const status = (result && result.status) || null;
    const reason = (result && result.detail && result.detail.detail && result.detail.detail.reason) || null;
    return {
      ok: false, state: 'refused', status, reason,
      // The client-side gate and a server refusal are DIFFERENT answers and must not share
      // a sentence -- one says 「이 자리는 아직 노드가 아닙니다」, the other 「서버가 거절」.
      message: reason === 'seed_is_not_a_server_node'
        ? '이 자리는 아직 원장 노드가 아닙니다 — 그릴 수는 있어도 마킹은 안 됩니다'
        : (status ? `서버가 거절했습니다 (HTTP ${status})` : '응답이 없습니다'),
      contrast: null, complete: null, candidates: [], topSet: [],
      // Refused: nothing was walked, so whether it would have truncated is UNKNOWN.
      truncated: null,
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
      measured: measuredFromHops__untilServerServesIt(row, body.edges),
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
    // 🔴 THE SUBGRAPH ITSELF, CARRIED (round Z, 2026-08-28). The counts above stay exactly as
    //    they were and for the same reason. What is new is that a part which draws the
    //    subgraph -- the map, whose dice ARE these nodes -- has to see them, and until now the
    //    only way to get them was a second route. Counts answer 「연결이 있었나」; these answer
    //    「그 연결이 무엇이었나」, and collapsing the second into the first is what made the map
    //    need `lot_map` at all.
    nodes: Array.isArray(body.nodes) ? body.nodes : [],
    edges: Array.isArray(body.edges) ? body.edges : [],
    contrast: prop.contrast || null,
    // 🔴 «안 온 것»과 «끊겼다»는 다릅니다. `=== true` 로 접으면 필드가 아직 없는 응답이
    //    「예산에서 끊김」으로 읽히고, 데이터가 오기 «전에» 배너가 뜹니다 -- 오늘 하루의
    //    「없음을 고장으로 읽는」 부류입니다. 모르면 null 로 둡니다.
    complete: prop.complete === undefined || prop.complete === null
      ? null : prop.complete === true,
    truncated: truncationNames(body.truncated),
    truncationReason: (body.truncated && body.truncated.reason) || null,
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

/** `GET /api/ledger/trends`. `grain`, when declared, rides as URL-encoded JSON. */
export async function fetchTrends(params) {
  const { apiBase, kinds, window: win, grain, fetchImpl } = params || {};
  const query = new URLSearchParams();
  if (kinds) query.set('kinds', kinds);
  query.set('window', win || '180d');
  // 🔴 `grain` IS A JSON OBJECT, SENT AS A STRING. Passing a NAME (`grain=wafer`) is refused --
  //    `bad_trend_grain`, 「grain을 JSON으로 해석할 수 없다」 -- which is why this boundary sent
  //    none at all and took the server's default. The default aggregates one subject_type and
  //    reads the leg out of the wrong place, so every point came back 0.0: not an empty chart,
  //    a chart showing twelve findings as none. The screen DECLARES the grain it wants.
  if (grain) query.set('grain', JSON.stringify(grain));
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
        // 🔴 THE NUMERATOR TRAVELS SEPARATELY, and that is the point. The rate alone cannot say
        //    whether zero means nobody was found or nobody looked, which is exactly the reading
        //    that let a 50% map sit beside a 0% line (owner, 2026-08-24). `null` when the key is
        //    absent -- never 0, because 0 asserts a clean scan the server did not report.
        found: typeof value.found_chip_count === 'number' ? value.found_chip_count : null,
        state: value.state || null,
        markKey: identity.mark_key || null,
        // 🔴 2단계 (소유자 판정: 「키는 노드 아이디와 노드 타입」). 서버가 이미 둘을 싣고 있고
        //    (identity.node_id · identity.type), 읽는 쪽이 옮겨 갈 때까지 mark_key 도 함께
        //    남습니다 -- 읽는 쪽이 먼저 가면 화면이 조용히 빈다는 것이 오늘 아침의 교훈입니다.
        nodeId: identity.node_id || null,
        nodeType: identity.type || null,
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


/**
 * 목업 맵 하단의 기반 알약 숫자. MEASURED 2026-08-23: `composition.graph.nodes` is 38 nodes
 * typed `bond_layer` 10 · `dt_slot` 18 · `wafer_grid` 10 -- the mockup's three numbers exactly.
 * A node is a POSITION, so these are counts of positions, not of maps.
 */
export function basisCountsFromComposition(result) {
  const body = (result && result.body) || null;
  const nodes = (body && body.graph && body.graph.nodes) || [];
  const counts = Object.create(null);
  for (const n of nodes) {
    const t = n && n.type;
    if (!t) continue;
    counts[t] = (counts[t] || 0) + 1;
  }
  return counts;
}


/**
 * 목업의 맵 페이지 목록. MEASURED 2026-08-23: calling `lot_map` WITHOUT a slot answers with the
 * row's whole slot list on the bond frame -- `available_slots` ["01".."25"] -- while the same
 * call WITH a slot drops it. So the pages are a fact the route already serves; asking for them
 * is one slot-less call and no new endpoint.
 *
 * ⚠️ It reads the BOND frame on purpose. dt/core carry their own `available_slots` in a
 *    different vocabulary ("1".."25" unpadded, and a different lot), and feeding those back as
 *    `slot=` would be paging one axis with another axis's numbering.
 */
export function slotPagesFromLotMap(result) {
  // ⚠️ `fetchLotMap` RESOLVES WITH THE BODY ITSELF, while `fetchComposition` and `fetchSubgraph`
  //    resolve with `{ok, status, body}`. Two shapes at one boundary, and reading the wrong one
  //    here returned an empty page list SILENTLY -- no error, no refusal, just a pager that
  //    never appeared. Both are accepted rather than guessed at.
  const body = (result && result.body) || result || null;
  const projections = (body && body.projections) || [];
  const bond = projections.find((p) => p && p.axis === 'bond');
  const slots = bond && bond.frame && bond.frame.available_slots;
  return Array.isArray(slots) ? slots.slice() : [];
}


// ═══════════════════════════════════════════════════════════════════════════════
// SIBLINGS -- 「또래가 몇인가」. The control bar's Group by pills.
//
// 🔴 THE COUNT IS IN `scope.value_accounting`, NOT IN `case`. Handed over by the implementer
//    after they pulled it live: `case.subjects` counts the axis INSIDE the subject (leg,
//    recipe, equipment) and answers 0 or another number entirely. Measured shape:
//      value_accounting[0] = {value, state: "resolved", units: 384, subjects: 6}
//    `subjects` is the peer count (wafers); `units` is packages. Both come in one answer, so
//    the screen picks rather than derives.
// ═══════════════════════════════════════════════════════════════════════════════

/** `GET /api/ledger/siblings`. `scope` is `<axis>:<value>`. */
export async function fetchSiblings(params) {
  const { apiBase, scope, window: win, fetchImpl } = params || {};
  const query = new URLSearchParams();
  if (scope) query.set('scope', scope);
  query.set('window', win || '180d');
  const url = `${apiBase}${ROUTES.siblings}?${query.toString()}`;
  const res = await (fetchImpl || fetch)(url);
  if (!res.ok) return { ok: false, status: res.status, body: null };
  return { ok: true, status: res.status, body: await res.json() };
}

/**
 * @returns {{state, subjects, units}} -- `subjects`/`units` are null unless the server said
 *          `resolved`. An unresolved scope keeps 「—」 on the pill; it never becomes 0.
 */
export function peerCountFromSiblings(result) {
  const body = (result && result.body) || result || null;
  const rows = (body && body.scope && body.scope.value_accounting) || [];
  const row = rows[0] || null;
  const excluded = (body && body.scope && body.scope.excluded) || [];
  const straddle = excluded.find((e) => e && e.bucket === 'mixed') || null;
  const scope = (body && body.scope) || null;
  const base = {
    // 🔴 WHERE THE NUMBER CAME FROM, carried because the part has a place for it and the
    //    server already fills it. Measured in the live envelope: relation "bonding_log",
    //    column "base_id". Nothing here derives them -- a boundary that guessed a relation
    //    name would be inventing provenance, which is the one thing this screen refuses.
    // 🔴 ABSENT STAYS ABSENT. No scope means the response did not say, not that there is no
    //    relation, so these are null rather than empty strings.
    relation: (scope && scope.relation) || null,
    column: (scope && scope.column) || null,
    axis: (scope && scope.axis) || null,
    axisLabel: (scope && scope.axis_label) || null,
    // 🔴 TWO STATES, NOT ONE. The VALUE resolved (the axis exists, it has 6 subjects) while the
    //    COMPARISON came back empty (`empty_case_side`: none of those 6 is on the marked side).
    //    Printing the resolved number alone reads as 「6 으로 대조할 수 있다」, which is the exact
    //    opposite of what happened -- 「6 이 어느 쪽도 아니라 빠졌다」. So both travel.
    analysis: (body && body.state) || null,
    reason: (body && body.reason) || null,
    message: (body && body.message) || null,
    straddling: straddle && typeof straddle.subjects === 'number' ? straddle.subjects : null,
    straddleMessage: (straddle && straddle.message) || null,
  };
  if (!row || row.state !== 'resolved') {
    return { ...base, state: (row && row.state) || 'absent', subjects: null, units: null };
  }
  return {
    ...base,
    state: 'resolved',
    subjects: typeof row.subjects === 'number' ? row.subjects : null,
    units: typeof row.units === 'number' ? row.units : null,
  };
}


/**
 * 목업 ① 이 주는 정보를, 주어를 바꾸지 않고. The wafer this chip sits on and what was seen on
 * it, out of the SAME `lot_map` body the maps already use.
 *
 * ⚠️ `fetchLotMap` resolves with the body itself (see `slotPagesFromLotMap`), so both shapes
 *    are accepted here too.
 */
export function waferFactsFromLotMap(result, axis) {
  const body = (result && result.body) || result || null;
  const projections = (body && body.projections) || [];
  const p = projections.find((x) => x && x.axis === (axis || 'bond'));
  if (!p) return null;
  const frame = p.frame || {};
  return {
    wafer: frame.wafer || null,
    lot: (body && body.row) || null,
    cells: Array.isArray(p.cells) ? p.cells.length : null,
    found: typeof p.found === 'number' ? p.found : null,
    scanned: typeof p.scanned === 'number' ? p.scanned : null,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// 🔴 ONE CALL — 소유자가 그린 «클라 데이터 흐름» (2026-08-24).
//
//    The owner drew the board as SEVEN WALKS and no other route: every part declares
//    `{ start, collect }` and asks here. A part never names a route, a query parameter or a
//    model again -- which is why the map and the trend can be 「같은 collect, 시작점만 다름」
//    without either part knowing the other exists.
//
//      walk ①  start: each wafer          collect: trend_y        기본 트렌드
//      walk ③  start: marking 1           collect: candidate      후보
//      walk ④  start: marking 1           collect: wafer_process  자재 정보
//      walk ⑤  start: marking 1           collect: trend_y        맵  (같은 collect)
//      walk ⑦  start: marking 2           collect: candidate      후보 트렌드 · 후보 맵
//
// 🔴 THE COLLECT TABLE IS THE DECLARATION; THE ROUTES UNDER IT ARE TODAY'S MATERIAL.
//    The ledger carries coordinates as a subject on ONE family today (die transfer, 1,405
//    atoms), so `map` still reads `lot_map` -- the Lead PM's standing ruling is that the old
//    path stays alive until the walk itself can draw. When it can, ONE line here changes and
//    no part does.
//
// 🔴 THE SAME WALK IS NOT ASKED TWICE. Walk ⑦ feeds two parts; they mount together, so the
//    second one joins the first one's in-flight promise instead of opening a second request.
//    Only IN-FLIGHT calls are shared -- nothing is cached after it settles, because a cache
//    that outlives the request would answer a later question with an earlier answer.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * `start` is `{ groupby, value }`. 🔴 `groupby` is `'wafer'` today because the owner wrote
 * 「일단 wafer 로 고정」 -- it is a VALUE here, not a configuration axis, and it becomes two
 * the day something needs two.
 */
/**
 * 「닿는 곳」 -- 한 홉 walk 의 `edges[]` 를 «술어별»로 묶습니다.
 *
 * 🔴 새 라우트도 새 fetch 도 «없습니다». `fetchSubgraph` 를 그대로 쓰고 `hops` 만 1 로
 *    선언합니다 -- 화면이 하나 늘 때 함수가 하나 늘면 설계가 틀린 것이라는 소유자 상설
 *    그대로입니다. 다른 것은 «읽는 법»뿐입니다: `subgraphModel` 은 `graph:{nodes,edges}` 로
 *    «수»만 남기고 엣지를 버리는데, 이 질문의 답이 바로 그 버려진 엣지입니다.
 *
 * 🔴 `truncated.depth` 는 «잘림이 아닙니다». hops=1 로 물었으니 깊이에서 끊기는 것이 질문
 *    자체이고, 실제 손실은 nodes·edges·claims 쪽입니다. 둘을 같은 낱말로 부르면 「한 홉만
 *    물었다」가 「답이 모자라다」로 읽힙니다.
 */
export function reachModel(result) {
  const failed = !result || result.ok === false;
  const body = (result && result.body) || null;
  if (failed || !body) {
    const status = (result && result.status) || null;
    const reason = (result && result.detail && result.detail.detail && result.detail.detail.reason) || null;
    return {
      ok: false, state: 'refused', status, reason,
      message: reason === 'seed_is_not_a_server_node'
        ? '이 자리는 아직 원장 노드가 아닙니다 -- 걸어 나갈 수 없습니다'
        : (status ? `서버가 거절했습니다 (HTTP ${status})` : '응답이 없습니다'),
      seedId: null, seedLabel: null, rows: [], nodes: 0, edges: 0, cut: null,
    };
  }
  const seed = body.seed || null;
  const seedId = (seed && seed.id) || null;
  const nodes = Array.isArray(body.nodes) ? body.nodes : [];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges = Array.isArray(body.edges) ? body.edges : [];
  const groups = new Map();
  for (const e of edges) {
    const predicate = e && e.predicate;
    if (!predicate) continue;
    // 「어디로」 는 씨앗의 «반대편»입니다. 방향은 묻지 않았으므로 양쪽 다 나올 수 있습니다.
    const otherId = e.source === seedId ? e.target : e.source;
    if (!otherId || otherId === seedId) continue;
    let g = groups.get(predicate);
    // 🔴 A MAP, NOT A SET: the value is WHEN this destination was first reached. A Set keeps
    //    insertion order, which is the SERVER'S response order -- an order nobody chose and
    //    nothing guarantees. 「자리로 엮어두면 한 자리의 정체만 알아도 남은 자리가 모두
    //    확정된다」(소유자) only holds if the chain is in the order the facts happened.
    if (!g) { g = { predicate, when: new Map(), kinds: new Map(), edges: 0 }; groups.set(predicate, g); }
    // Several edges can land on one destination; the EARLIEST is when the walk first got there.
    const at = (e && e.occurred_at) || null;
    const seen = g.when.get(otherId);
    if (seen === undefined) g.when.set(otherId, at);
    else if (at && (!seen || at < seen)) g.when.set(otherId, at);
    g.edges += 1;
    // 🔴 종류도 «노드»로 셉니다. 엣지로 세면 「Value 10」 옆에 「닿는 수 4」 가 서고,
    //    한 줄 안에서 두 수가 서로를 반박합니다.
    const type = ((byId.get(otherId) || {}).type) || '?';
    let ofType = g.kinds.get(type);
    if (!ofType) { ofType = new Set(); g.kinds.set(type, ofType); }
    ofType.add(otherId);
  }
  const rows = [...groups.values()].map((g) => ({
    predicate: g.predicate,
    // 🔴 «닿는 노드»의 수이지 엣지 수가 아닙니다. 한 노드로 두 엣지가 가면 그것은 «한 곳»입니다.
    count: g.when.size,
    // 🔴 엣지 수도 «같이» 나릅니다. 실측 2026-08-25, 씨앗 SYN-BW-101-16: `binding` 은
    //    엣지 «10» 인데 닿는 곳은 «4» 입니다 -- 여섯 엣지가 이미 센 노드로 갑니다.
    //    총괄이 준 넷(39·29·10·9)은 엣지를 센 수이고, 클릭이 마킹하는 것은 «노드 집합»이라
    //    「10 이라 적어 놓고 4 를 마킹」이 됩니다. 두 수를 다 들고 화면이 고르게 합니다.
    edges: g.edges,
    kinds: [...g.kinds.entries()].map(([type, ids]) => ({ type, count: ids.size }))
      .sort((a, b) => b.count - a.count || String(a.type).localeCompare(String(b.type))),
    // 🔴 STABLE, AND NEVER SHAKEN BY NAME. Sorted by first-reached time; entries with no time,
    //    or with the SAME time, keep the order they arrived in. Measured 2026-08-26, seed
    //    SYN-BW-101-16: `bonded_from` reaches 29 destinations at ONE instant and `binding`
    //    carries no time at all -- if a name were the tiebreaker, those two rows would be
    //    ordered by a fact that is not in the data. 「시간이 없으면 없는 대로」 (총괄).
    nodeIds: [...g.when.entries()]
      .map(([id, at], i) => ({ id, at, i }))
      .sort((a, b) => {
        if (a.at && b.at && a.at !== b.at) return a.at < b.at ? -1 : 1;
        if (a.at && !b.at) return -1;
        if (!a.at && b.at) return 1;
        return a.i - b.i;
      })
      .map((x) => x.id),
    // 그 술어가 «언제부터 언제까지» 닿았나. 시각이 하나도 없으면 `null` -- 「없음」이지 0 이
    // 아니고, 화면이 그 칸을 «비웁니다».
    span: (() => {
      const times = [...g.when.values()].filter(Boolean).sort();
      return times.length ? { first: times[0], last: times[times.length - 1] } : null;
    })(),
  }));
  // 큰 것부터. 동수는 «이름»으로 갈라 응답 순서가 대표를 정하지 못하게 합니다.
  rows.sort((a, b) => b.count - a.count || String(a.predicate).localeCompare(String(b.predicate)));
  const t = body.truncated || {};
  return {
    ok: true, state: body.state || 'ready', status: null, reason: null, message: null,
    seedId, seedLabel: (seed && seed.label) || null,
    rows, nodes: nodes.length, edges: edges.length,
    // depth 는 «질문»이라 여기 없습니다. 이 셋이 참이면 답이 «실제로» 모자란 것입니다.
    cut: [t.nodes ? 'nodes' : null, t.edges ? 'edges' : null, t.claims ? 'claims' : null].filter(Boolean),
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// THE MAP, AS TWO MATERIALS (round Z, 2026-08-28). The Lead PM's ruling: 「점은 walk · 격자는 물리」.
//
// 🔴 WHY THE GRID IS A SECOND FETCH AND NOT A SECOND WALK. `unscanned` is an assertion of
//    ABSENCE, and absence needs a denominator. The subgraph can say which dice were inspected
//    and which carry findings; it cannot say which dice EXIST, because a die with no edge is
//    missing from it for three different reasons -- never inspected, cut by the budget, or
//    excluded by `follow`. The grid is where 「이 웨이퍼에 칸이 몇이나 있나」 lives, and it is
//    physics rather than ledger, so it comes from the declared relation.
//
// 🔴 AND WHEN THE WALK WAS TRUNCATED, THERE IS NO DENOMINATOR EITHER. A cut walk under-counts
//    `scanned`, so `grid - scanned` would report dice as unscanned that were merely unseen.
//    `mapModel` returns `unscanned: null` in that case and the part says how far the walk got.
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * `GET /tables/wafer_map_metadata/data`, filtered to ONE map. The denominator, and nothing else.
 *
 * 🔴 FILTERED AT THE SERVER. The relation holds 4,925 rows; pulling all of them to find one is
 * how a screen becomes slow for a value it uses once. Measured: the filter answers `total: 1`.
 */
export async function fetchMapGrid(params) {
  const { apiBase, mapId, fetchImpl } = params || {};
  if (!mapId) return { ok: false, grid: null, reason: 'no_map_id' };
  const filters = JSON.stringify({ map_id: { filterType: 'text', type: 'equals', filter: mapId } });
  const query = new URLSearchParams({ limit: '1', filters });
  const doFetch = fetchImpl || globalThis.fetch;
  const res = await doFetch(`${apiBase}${ROUTES.mapGrid}?${query.toString()}`);
  if (!res.ok) return { ok: false, grid: null, reason: `HTTP ${res.status}` };
  const body = await res.json();
  const row = (body && body.data && body.data[0]) || null;
  // 🔴 A MAP WITH NO ROW IS NOT AN ERROR. Measured 2026-08-28: `SYN-CX-BW-001` has exactly one
  //    row and `SYN-BW-101-02` has none. The screen must be able to draw the points it does
  //    have and say the grid is unknown, rather than refuse the whole seat.
  if (!row) return { ok: true, grid: null, reason: 'no_row_for_map' };
  const cell = row.data && row.data.grid_metadata;
  return { ok: true, grid: (cell && cell.value) || null, reason: null };
}

/**
 * A walk answer plus a grid, as the model the `die` coordinate space already reads.
 *
 * 🔴 EVERY NUMBER HERE IS COUNTED FROM AN EDGE, NEVER FROM A NAME. `scanned` is 「inspected 엣지가
 * 있다」 and `found` is 「observed 엣지가 몇 개인가」. No `if kind === 'void'` and no route.
 *
 * @param {object} answer  what `walk()` returned -- `subgraphModel`'s model, carrying nodes/edges
 * @param {?string} grid   `grid_metadata` as the relation serves it (a JSON string), or null
 */
export function mapModel(answer, grid, axis) {
  if (!answer || answer.ok === false) {
    return {
      axis, label: axis, sublabel: '', drawable: false,
      state: answer && answer.state === 'refused' ? 'refused' : 'absent',
      reason: (answer && answer.reason) || 'walk_absent',
      message: (answer && answer.message) || '걷지 못했습니다',
      cells: [], found: 0, scanned: 0, unscanned: null,
      frame: null, coordinateUnit: null,
    };
  }
  const nodes = answer.nodes || [];
  const edges = answer.edges || [];
  const dice = new Map();
  for (const node of nodes) {
    if (!node || node.type !== 'die') continue;
    const keys = node.keys || {};
    if (keys.x === undefined || keys.y === undefined) continue;
    dice.set(node.id, { x: keys.x, y: keys.y, n: 0, scanned: false, id: node.id });
  }
  for (const edge of edges) {
    if (!edge) continue;
    const die = dice.get(edge.target) || dice.get(edge.source);
    if (!die) continue;
    if (edge.predicate === 'inspected') die.scanned = true;
    if (edge.predicate === 'observed') { die.n += 1; die.scanned = true; }
  }
  const cells = [...dice.values()].map((die) => ({
    x: die.x, y: die.y, n: die.n,
    colorRole: die.n > 0 ? 'found' : (die.scanned ? 'scanned' : 'unscanned'),
    nodeId: die.id, nodeIdResolved: true,
  }));
  const scanned = cells.filter((cell) => cell.colorRole !== 'unscanned').length;
  const found = cells.reduce((sum, cell) => sum + cell.n, 0);
  // 🔴 THE THREE STATES OF `unscanned`, AND THEY ARE NOT INTERCHANGEABLE:
  //      a number  the grid declared its size and the walk ran whole
  //      null      the grid is unknown, OR the walk was cut -- the part says which
  const seats = declaredSeats(grid);
  const cut = answer.complete === false || (answer.truncated || []).length > 0;
  return {
    axis, label: axis, sublabel: '',
    // 🔴 NO SERVER VERDICT HERE. `lot_map` refused when its frames disagreed; a walk has no
    //    frame to disagree with, so what decides drawability is whether a grid was declared.
    drawable: Boolean(grid) && cells.length > 0,
    state: cells.length ? (grid ? 'ready' : 'no_grid') : 'empty',
    reason: grid ? null : 'grid_not_declared',
    message: grid ? null : '이 맵의 격자가 선언돼 있지 않습니다 — 점은 그대로입니다',
    cells, found, scanned,
    unscanned: seats === null || cut ? null : Math.max(0, seats - scanned),
    truncated: answer.truncated || null,
    complete: answer.complete === undefined ? null : answer.complete,
    frame: grid ? { grid } : null,
    coordinateUnit: 'cells_from_origin',
  };
}

/** `grid_cols x grid_rows` from the relation's own declaration, or null when it declares none. */
function declaredSeats(grid) {
  if (!grid) return null;
  let parsed = grid;
  if (typeof parsed === 'string') {
    try { parsed = JSON.parse(parsed); } catch { return null; }
  }
  const cols = Number(parsed && parsed.grid_cols);
  const rows = Number(parsed && parsed.grid_rows);
  if (!Number.isFinite(cols) || !Number.isFinite(rows) || cols <= 0 || rows <= 0) return null;
  return cols * rows;
}

/**
 * 「이 다이는 무엇으로 만들어졌나」, from the walk. The composition route's model, from edges.
 *
 * 🔴 NO NEW PREDICATE AND NO NEW ENTITY. The owner's question -- 「bondfrom collect 조합으로 구성
 * 파악되지 않아? 굳이 새 엣지가 왜 필요해?」 -- is answered by `bonded_from`, which already runs
 * base die -> core die. A package IS the base die, `(base, x, y)`, so there is nothing to declare.
 *
 * 🔴 WHAT THE WALK DOES NOT CARRY IS SAID, NOT ZEROED. `lot`, `slot` and `branch` were columns of
 * the composition route's own join; the ledger holds no atom for them at die granularity, so they
 * come back `null` and the panel prints 「—」. A zero there would be a number nobody measured.
 */
export function compositionFromWalk(answer) {
  const absent = (state, message) => ({
    ok: false, state, status: (answer && answer.status) || null, message,
    subject: null, wafer: null, resolution: null, window: null,
    cardinality: null, provenance: null,
    counts: { components: null, dtCollections: null },
    coreTypes: [], components: [],
  });
  if (!answer) return absent('absent', '아직 걷지 않았습니다');
  if (answer.ok === false) {
    return absent('refused', answer.message || '서버가 거절했습니다');
  }
  const nodes = answer.nodes || [];
  const edges = answer.edges || [];
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const seeds = new Set((answer.seeds || []).map((seed) => seed.id || seed));
  const components = [];
  for (const edge of edges) {
    if (!edge || edge.predicate !== 'bonded_from') continue;
    // 🔴 방향은 «엣지가 말합니다». source 가 base 이고 target 이 core 입니다 -- 여기서 방향을
    //    다시 정하면 그게 두 번째 진실이 됩니다.
    const core = byId.get(edge.target);
    if (!core) continue;
    const keys = core.keys || {};
    components.push({
      id: `${keys.mat_id}:${keys.x},${keys.y}`,
      entityId: core.id,
      core: { wafer: keys.mat_id || null, lot: null, slot: null, branch: null },
      lineage: null,
      resolutionState: seeds.has(edge.source) ? 'resolved' : 'reached',
      steps: [],
    });
  }
  const cut = answer.complete === false || (answer.truncated || []).length > 0;
  return {
    ok: true,
    state: components.length ? 'ready' : 'empty',
    status: answer.status || null,
    // 🔴 「구성 없음」 은 «문장»이지 빈 화면이 아닙니다. 측정: base die 18,545 / 원장의 서로 다른
    //    die 주어 400,690 = 4.63% 이므로 「없다」가 대다수이고 그게 오늘의 참입니다. 그리고 walk 이
    //    잘렸으면 「없다」가 아니라 「여기까지 봤다」입니다.
    message: components.length ? ''
      : (cut ? '이 걷기는 예산에서 끊겼습니다 — 구성이 없다는 뜻이 아닙니다'
             : '이 다이에는 기록된 구성이 없습니다'),
    subject: null, wafer: null, resolution: null, window: null,
    cardinality: { components: components.length },
    provenance: null,
    counts: { components: components.length, dtCollections: null },
    coreTypes: [...new Set(components.map((c) => c.core.wafer).filter(Boolean))],
    components,
    truncated: answer.truncated || null,
    complete: answer.complete === undefined ? null : answer.complete,
  };
}

/**
 * 「이 웨이퍼에 이 종류가 몇이나 있나」, counted in the window rather than joined on the server.
 *
 * 🔴 THE COUNT IS OF EDGES, NOT OF A NAME. A die is `found` when an `observed` edge lands on it
 * and the finding it reaches is `of_kind` the kind asked for; `scanned` is an `inspected` edge.
 * There is no `if kind === 'void'` here -- the kind arrives as an argument and is compared to
 * the kind NODE's own key, which is a word the declaration owns.
 *
 * ⚠️ A CUT WALK RETURNS `null` COUNTS, NOT ZEROS. Same rule the map's `unscanned` follows: a
 * truncated walk under-counts, and reporting that as a number says 「없다」 where 「못 봤다」 is true.
 */
export function waferFactsFromWalk(answer, kind) {
  if (!answer || answer.ok === false) return null;
  const nodes = answer.nodes || [];
  const edges = answer.edges || [];
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const wafer = nodes.find((node) => node.type === 'wafer');
  const cut = answer.complete === false || (answer.truncated || []).length > 0;
  // finding -> its kind, off the `of_kind` edges the walk already returned
  const kindOf = new Map();
  for (const edge of edges) {
    if (!edge || edge.predicate !== 'of_kind') continue;
    const target = byId.get(edge.target);
    kindOf.set(edge.source, (target && (target.keys || {}).defect_kind) || null);
  }
  const scanned = new Set();
  const found = new Set();
  for (const edge of edges) {
    if (!edge) continue;
    if (edge.predicate === 'inspected') scanned.add(edge.target);
    if (edge.predicate === 'observed' && (!kind || kindOf.get(edge.target) === kind)) {
      found.add(edge.source);
    }
  }
  return {
    wafer: wafer ? (wafer.keys || {}).wafer : null,
    lot: null,
    cells: cut ? null : scanned.size,
    found: cut ? null : found.size,
    scanned: cut ? null : scanned.size,
  };
}

/**
 * 「같은 설비를 지난 주어가 몇이나 되나」 — the one peer axis the ledger has a word for.
 *
 * 🔴 MEASURED BEFORE BUILDING (2026-08-28): `leg`, `bond_lot` and `scan_recipe` appear in ZERO
 * atoms, so those three axes are answered with a sentence rather than a count. `eqp_id` is real
 * -- 6,750 `measures` atoms carry it in their qualifiers -- and this counts THAT one.
 */
export function peerCountFromWalk(answer, eqpId) {
  if (!answer || answer.ok === false) return null;
  const subjects = new Set();
  let units = 0;
  for (const edge of (answer.edges || [])) {
    if (!edge || edge.predicate !== 'measures') continue;
    if (eqpId && (edge.qualifiers || {}).eqp_id !== eqpId) continue;
    units += 1;
    subjects.add(edge.source);
  }
  const cut = answer.complete === false || (answer.truncated || []).length > 0;
  return {
    subjects: cut ? null : subjects.size,
    units: cut ? null : units,
    // 🔴 어디서 왔는지 «지어내지 않습니다». lot_map 은 서버가 relation·column 을 실어 줬고,
    //    여기서는 그 자리에 «술어»가 옵니다 -- 그게 이 수의 출처이고 사실입니다.
    relation: 'measures', column: 'qualifiers.eqp_id',
    analysis: null, straddling: null, message: null,
  };
}

/**
 * 「마킹한 것들의 추세」, counted in the window. The owner ruled the population on 2026-08-28:
 * 「a지」 -- **the marking IS the population**. One marked wafer is one point, several are several.
 *
 * 🔴 THE TIME AXIS WAS ALREADY IN THE RESPONSE. Measured: all 626 edges of a board walk carry
 * `occurred_at`. So no server aggregation, no date-range route, and no new declaration -- the
 * window reads what the walk brought, which is the same rule the map's counts follow.
 *
 * 🔴 A CUT WALK PUBLISHES NO NUMBER. `state: 'truncated'` and the part says how far it got.
 * Dividing an under-counted numerator by an under-counted denominator produces a rate that
 * looks like a measurement and is not one.
 */
export function trendFromWalk(answer) {
  const empty = (state, message) => ({
    ok: state !== 'refused', state, points: [], kinds: [], provenance: null, message,
  });
  if (!answer) return empty('awaiting', '아직 안 골랐습니다');
  if (answer.ok === false) return empty('refused', answer.message || '서버가 거절했습니다');
  const nodes = answer.nodes || [];
  const edges = answer.edges || [];
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const kinds = [...new Set(nodes.filter((n) => n.type === 'defect_kind')
    .map((n) => (n.keys || {}).defect_kind).filter(Boolean))]
    .map((id) => ({ id, label: id, active: true }));
  if (answer.complete === false || (answer.truncated || []).length) {
    return { ...empty('truncated', '이 걷기는 예산에서 끊겼습니다 — 여기까지 봤습니다'), kinds };
  }
  // die -> the wafer it sits on, so a per-wafer point can be counted off die-level edges
  const waferOf = (id) => {
    const node = byId.get(id);
    const keys = (node && node.keys) || {};
    return keys.mat_id || keys.wafer || null;
  };
  const stat = new Map();
  const at = (wafer) => {
    if (!stat.has(wafer)) stat.set(wafer, { scanned: new Set(), found: new Set(), at: null });
    return stat.get(wafer);
  };
  for (const edge of edges) {
    if (!edge) continue;
    const wafer = waferOf(edge.target) || waferOf(edge.source);
    if (!wafer) continue;
    const row = at(wafer);
    if (edge.predicate === 'inspected') row.scanned.add(edge.target);
    if (edge.predicate === 'observed') row.found.add(edge.source);
    if (edge.occurred_at && (!row.at || edge.occurred_at > row.at)) row.at = edge.occurred_at;
  }
  const points = [...stat.entries()].map(([wafer, row]) => ({
    seriesId: 'marking', wafer, leg: null, at: row.at,
    denominator: row.scanned.size || null,
    found: row.found.size,
    rate: row.scanned.size ? row.found.size / row.scanned.size : null,
    state: 'measured', markKey: null,
    nodeId: (nodes.find((n) => n.type === 'wafer' && (n.keys || {}).wafer === wafer) || {}).id || null,
    nodeType: 'wafer',
  })).sort((a, b) => String(a.at || '').localeCompare(String(b.at || '')));
  return {
    ok: true,
    state: points.length ? 'ready' : 'empty',
    points, kinds,
    // 🔴 출처를 «지어내지 않습니다». lot_map 은 서버가 relation·column 을 실어 줬고, 여기서는
    //    그 자리에 «술어»가 옵니다 -- 이 수가 어느 엣지에서 나왔는지가 사실입니다.
    provenance: { source: 'walk', predicates: ['inspected', 'observed'] },
    message: points.length ? '' : '이 마킹에는 셀 것이 없습니다',
  };
}

/**
 * The walk a seat gets when it names no route: its `start` marking, carried whole, and whatever
 * else it declared (`follow`, `hops`, `direction`, the budgets) riding through untouched.
 *
 * 🔴 THE SIGNED SETS ARE THE MARKING. `positive`/`negative` pass straight through, so a seat
 * that marks a control group asks about it without this function learning a new word.
 */
const WALK = Object.freeze({
  params: (start) => (start.value
    ? { nodeId: start.value, positive: start.positive, negative: start.negative }
    : {}),
  run: (params) => fetchSubgraph(params).then(subgraphModel),
});

export const COLLECTS = Object.freeze({
  // 기본 트렌드 ① · 맵 ⑤ — 같은 collect. 트렌드는 창 전체를, 맵은 한 그룹을 그립니다.
  trend_y: {
    params: () => ({}),
    run: (params) => fetchTrends(params).then(trendsModel),
  },
  // ③⑦ 후보 — 마킹한 노드에서 걸어서 모읍니다.
  candidate: {
    // 🔴 `positive`/`negative` are the marking itself, carried through unchanged. A start with
    //    neither is the single-seed call this screen already makes; the contract's control
    //    side arrives the day a part passes them (`task/MARKING_CONTRACT.md` §1).
    // 🔴 `collect` USED TO BE NAMED HERE, and naming it was right while it existed: the walk
    //    collected one node kind, this row wanted `quantity`, and leaving it off meant landing
    //    on a server default by accident. Revision 6 ended the kinds and the route dropped the
    //    argument on 2026-08-28, so the line stopped being a choice and became a string the
    //    server discards. Removed in round Z with the parameter itself.
    params: (start) => (start.value
      ? { nodeId: start.value, positive: start.positive, negative: start.negative }
      : {}),
    run: (params) => fetchSubgraph(params).then(subgraphModel),
  },
  // ⑤ 맵의 점 — 마킹한 노드에서 걸어서 «관측»을 모읍니다. `candidate` 와 같은 걸음이고
  //    `collect` 하나만 다릅니다. 🔴 새 fetch 도 새 모델도 «없습니다» -- 화면이 하나 늘 때
  //    함수가 하나 늘면 그건 설계가 틀린 것이라는 소유자 상설이 이 자리의 통과 조건입니다.
  //
  // ⚠️ 지금 오는 값 (실측 2026-08-24, SYN-BW-103-11): point 208 · finding_kind 는
  //    { delam 9, defect 199 } 이고 `position` 은 «빈 객체»입니다. 배선은 맞고 값이 아직입니다 --
  //    서버가 `finding_kind`·`position` 을 제대로 실으면 «이 선언도 부품도 안 바뀌고» 값만
  //    나타나야 합니다. 그날 그게 이 항목이 맞았다는 증거입니다.
  // 🔴 `point` LEFT 2026-08-28 (round Z). It was already the walk -- the same fetch and the
  //    same model as `candidate`, differing only by a `collect` argument the server stopped
  //    accepting. The seat that used it (chip-zoom) already declared `follow` and `hops`, so
  //    what this row contributed was the NAME, and the name is the thing this round removes.
  //    The measured note above stays true and moves with the question: it now belongs to the
  //    seat's own declaration in `main.js`, which is where the question lives.
  // ④ 자재 정보 — 그 칩이 무엇으로 만들어졌나.
  wafer_process: {
    params: (start) => (start.value ? { finalChipId: start.value } : {}),
    run: (params) => fetchComposition(params).then(compositionModel),
  },
  // ⑤ 맵 — 오늘은 lot_map 이 재료입니다. 부품은 그것을 모릅니다.
  map: {
    params: (start) => (start.value ? { row: start.value, by: start.groupby } : {}),
    run: (params) => fetchLotMap(params),
  },
  // 기반 위치 수 — 같은 라우트, 다른 «선언». 갈래를 파지 않고 값을 하나 더 씁니다.
  basis: {
    params: (start) => (start.value ? { finalChipId: start.value } : {}),
    run: (params) => fetchComposition(params).then(basisCountsFromComposition),
  },
  // 또래 수 — 제어 막대의 알약 하나가 하나의 walk 입니다.
  peer: {
    params: (start) => (start.value ? { scope: start.value } : {}),
    run: (params) => fetchSiblings(params).then(peerCountFromSiblings),
  },
  // 「닿는 곳」 -- 마킹에서 «어느 술어로 무엇에» 닿는가. `candidate`·`point` 와 «같은 걸음»이고
  //    다른 것은 `hops` 와 «읽는 모델»뿐입니다. 부품이 hops 를 선언하지 않아도 1 입니다 --
  //    이 질문은 「한 홉에 무엇이 있나」이지 「멀리 무엇이 있나」가 아니어서, 홉 수가 부품의
  //    손잡이가 아니라 이 선언의 «뜻»입니다.
  reach: {
    params: (start) => (start.value
      ? { nodeId: start.value, hops: 1,
          positive: start.positive, negative: start.negative }
      : {}),
    run: (params) => fetchSubgraph(params).then(reachModel),
  },
});

/**
 * The one function a part calls. `createWalk` binds WHERE (apiBase) and HOW (fetchImpl) once,
 * at the composition root, so those two never appear in a part again.
 *
 * @returns {(spec: {start?, collect: string}) => Promise<any>}
 */
export function createWalk(deps) {
  const { apiBase, fetchImpl } = deps || {};
  const inflight = new Map();
  return function walk(spec) {
    const { start, collect, ...rest } = spec || {};
    // 🔴 NO NAME IS THE WALK ITSELF (round Z, 2026-08-28). A seat that declares `follow` has
    // stated its question in the LEDGER's words -- which predicates to walk from which marking
    // -- and needs no row in `COLLECTS`. What is left in that table is exactly the seats that
    // still name a ROUTE, so the table shrinking to nothing is the round's own measure.
    //
    // WHY THE TABLE WAS THE DEFECT AND THE DELETED ROUTES WERE NOT: a seat naming `map` or
    // `wafer_process` is naming a place on the server, so when that place went the seat went
    // 404 whole. A seat naming `[observed, inspected, bonded_from]` names things the
    // declaration owns, and a walk answers it.
    const declared = collect ? COLLECTS[collect] : WALK;
    // A collect nobody declared is a BUG IN THE SCREEN, not an empty answer: returning `null`
    // here would let a part draw 「없음」 for a question that was never asked.
    if (!declared) return Promise.reject(new Error(`walk: 선언되지 않은 collect — ${collect}`));
    const key = JSON.stringify([collect, start || null, rest]);
    const joined = inflight.get(key);
    if (joined) return joined;
    const running = Promise.resolve()
      // 🔴 START WINS. `rest` is the screen's declared question; `start` is the marking the
      //    user just moved. Spreading start LAST is what makes 「마킹을 바꾸면 따라온다」 true.
      .then(() => declared.run({ apiBase, fetchImpl, ...rest, ...declared.params(start || {}) }));
    inflight.set(key, running);
    const forget = () => { if (inflight.get(key) === running) inflight.delete(key); };
    running.then(forget, forget);
    return running;
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// DECLARATION -- 「무엇을 물을 수 있나」. 걷기 검색창의 드롭다운 넷이 여기서 나옵니다.
//
// 🔴 데이터가 아니라 «선언»입니다. `GET /api/ledger/declaration` 은 원장을 한 줄도 안 읽고
//    entities · vocabulary · 투영이 낼 수 있는 노드 종류를 그대로 답합니다. 그래서 목록을
//    여기 다시 적지 않습니다 -- 선언이 술어를 하나 더 가지면 드롭다운도 하나 늘어납니다
//    (총괄 실측 2026-08-27: 선언에 하나 넣으면 10 -> 11, 빼서 무효가 되면 503).
//
// 🔴 좁히기는 «서버의 subjects» 입니다. 이 파일은 좁히지 않습니다 -- 부품이 고른 타입으로
//    거르고, 비면 «문장»으로 말합니다. 여기서 미리 걸러 보내면 화면은 「왜 짧은가」를
//    물을 수 없게 됩니다.
// ═══════════════════════════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════════════════════════
// THE TYPE GRAPH — 「무엇을 볼지 고르면 follow 가 나온다」 (라운드 V, 소유자 2026-08-29)
//
// 🔴 THE LEDGER IS NOT READ. This graph is the DECLARATION's size, not the data's: 8 types and
//    12 predicate edges against 749,044 atoms. Measured: `/declaration` 49ms, building the
//    graph 0ms, every path for every pair about 1ms. So it costs the same whether the ledger
//    holds three quarters of a million rows or ten times that.
//
// 🔴 UNDIRECTED, BECAUSE THE WALK IS. `subgraph` is undirected for reachability and directed
//    only in the evidence it returns, and the paths people actually want run backwards along an
//    edge: `processed_with` is wafer -> recipe, so starting FROM a recipe needs that step
//    reversed. Searching only forwards answers zero for recipe -> quantity, which is wrong.
//
// 🔴 NO AUTOMATIC SHORTEST. Measured, wafer -> defect_kind has two: two hops through
//    `measures`/`leads_to` (a quantity that COULD cause that kind) and three through
//    `inspected`/`observed`/`of_kind` (a kind actually SEEN). Taking the short one silently
//    serves an inference as a fact. The reader picks, and picks by reading the chain.
// ═══════════════════════════════════════════════════════════════════════════════

/** `wafer@1` -> `wafer`. The declaration versions its names and the ledger does not. */
function bareType(value) {
  return String(value || '').split('@')[0];
}

/** `{types, edges}` from a declaration body. Edges carry the predicate that makes them. */
export function typeGraph(declaration) {
  const edges = [];
  for (const predicate of (declaration && declaration.predicates) || []) {
    const froms = (predicate.subjects || []).map(bareType);
    const tos = ((predicate.object || {}).types || []).map(bareType);
    for (const from of froms) {
      for (const to of tos) edges.push({ from, to, predicate: bareType(predicate.name) });
    }
  }
  const types = [...new Set(edges.flatMap((e) => [e.from, e.to]))].sort();
  return { types, edges };
}

/**
 * Every simple path from one declared type to another, as `{hops, follow, chain}`.
 *
 * 🔴 THE CAP IS STRUCTURAL, NOT A POLICY. A simple path cannot revisit a type, so it cannot be
 * longer than `types - 1`; that is the maximum that CAN exist, not a number chosen to keep the
 * list short. Lowering it is the same act as auto-picking the shortest -- measured, a cap of 4
 * makes `recipe -> quantity` look like one path when it is two.
 *
 * 🔴 WHAT KEEPS THIS SMALL IS THE CYCLE RANK, not the cap: `E - V + 1` is 1 today, which bounds
 * a pair at two paths. If the vocabulary grows cycles, the list grows with them and THAT is the
 * moment to look at the vocabulary -- not a moment to trim the answer.
 */
export function pathsBetween(declaration, from, to) {
  const { types, edges } = typeGraph(declaration);
  const limit = Math.max(1, types.length - 1);
  const out = [];
  // 🔴 자기 고리는 «경로의 한 칸»입니다 (소유자 정정 2026-08-29). X --술어--> X 를 빼면
  //    계보와 전달이 통째로 사라집니다 -- 실측: transfer 는 die -> die 이고 원자 «401,206» 로
  //    원장에서 제일 큰 술어이며, bonded_from 18,545 · slot_map 135 · leads_to 22 도 자기
  //    고리입니다. 「N대 위까지」가 뜻의 전부인 것들이라, 못 지나가면 그 질문 자체가 없습니다.
  //    한 술어는 «한 번»만 밟습니다: 반복 횟수는 follow 가 아니라 «사용자 축»이고, 선언이
  //    정할 수 있는 값이 아닙니다.
  const usedLoop = new Set();
  const walkOn = (at, seen, chain) => {
    if (chain.length && at === to) { out.push(chain.slice()); return; }
    if (chain.length >= limit) return;
    for (const edge of edges) {
      const loop = edge.from === edge.to && edge.from === at;
      let next = null;
      if (loop) next = at;
      else if (edge.from === at) next = edge.to;
      else if (edge.to === at) next = edge.from;
      else continue;
      if (loop) {
        if (usedLoop.has(edge.predicate)) continue;
        usedLoop.add(edge.predicate);
      } else if (seen.has(next)) continue;
      else seen.add(next);
      chain.push({ predicate: edge.predicate, next, loop });
      walkOn(next, seen, chain);
      chain.pop();
      if (loop) usedLoop.delete(edge.predicate);
      else seen.delete(next);
    }
  };
  if (from && to && types.includes(from) && types.includes(to)) {
    walkOn(from, new Set([from]), []);
  }
  // 🔴 «follow 집합»이 경로의 신원입니다. walk 이 받는 것은 {follow, hops} 이고, 같은 follow 에
  //    홉만 다른 둘은 «다른 길이 아니라» 「몇 번 반복하나」입니다 -- 소유자가 「반복 횟수는
  //    사용자 축」이라고 정한 바로 그 축이라, 경로 목록에 넣으면 사용자 축을 경로로 «위장»합니다.
  //    실측: 자기 고리를 넣자 die -> defect_kind 가 15 로 늘었는데, 그중 여럿이
  //    [measures, leads_to] 처럼 «같은 follow» 였습니다. 접고 나면 서로 다른 질문만 남습니다.
  //    ⚠️ 접을 때 «가장 짧은» 홉을 답니다 -- 그 경로가 최소 몇 홉을 요구하는지가 hops 의 뜻입니다.
  const byFollow = new Map();
  for (const steps of out) {
    const follow = [...new Set(steps.map((s) => s.predicate))];
    const key = follow.slice().sort().join('|');
    const route = {
      hops: steps.length,
      follow,
      chain: [from, ...steps.map((s) => s.next)],
    };
    const seen = byFollow.get(key);
    if (!seen || route.hops < seen.hops) byFollow.set(key, route);
  }
  return [...byFollow.values()].sort((a, b) => a.hops - b.hops
    || a.follow.length - b.follow.length);
}

/** `["wafer", {wafer: "SYN-…"}]` -> `ledger-entity:v1:<base64url>`. 서버 `decode_entity_id` 의 짝. */
export function entitySeedId(type, keys) {
  // 🔴 «타입은 벗겨서» 보냅니다. 선언은 `wafer@1` 로 버전을 달고 원장은 `wafer` 로 삽니다.
  //    `wafer@1` 을 그대로 실으면 주어가 하나도 안 맞아 walk 이 «씨앗 하나»를 답하는데,
  //    그건 거절이 아니라 「닿는 곳이 없다」로 보입니다 (총괄이 오늘 밤 한 번 당했습니다).
  const bare = String(type || '').split('@')[0];
  const json = JSON.stringify([bare, keys || {}]);
  const b64 = btoa(unescape(encodeURIComponent(json)));
  // 🔴 base64URL 은 «서버가 요구하는 것»이지 취향이 아닙니다. 클라 레인 실측 2026-08-27,
  //    키 `SYN-BW-101-16>` (base64 에 `+` 가 들어가는 첫 키):
  //      표준 base64  ->  HTTP «422»        base64url  ->  «200»
  //    오늘 쓰는 씨앗 셋은 `+`·`/` 를 안 만들어서 «두 방식이 같은 답»입니다 -- 그래서 이 줄은
  //    맞은 채로 검증되지 않고 있었고, 「단순화」로 되돌리면 그날부터 «특정 키만» 422 입니다.
  //    `rnd_board_walk_box_harness` 의 S 절이 그 판별 키로 못 박습니다.
  return 'ledger-entity:v1:' + b64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/** `GET /api/ledger/declaration`. 한 모양 -- 성공도 실패도 `{ok}` 를 답니다. */
export async function fetchDeclaration(params) {
  const { apiBase, fetchImpl } = params || {};
  const doFetch = fetchImpl || fetch;
  try {
    const res = await doFetch(`${apiBase || ''}/api/ledger/declaration`);
    const body = await res.json().catch(() => null);
    if (!res.ok || !body) {
      return { ok: false, message: (body && body.detail && body.detail.message)
        || `선언을 읽지 못했습니다 (${res.status})` };
    }
    return { ok: true, entities: body.entities || [], predicates: body.predicates || [],
             collect: body.collect || [] };
  } catch (err) {
    return { ok: false, message: `선언에 닿지 못했습니다 — ${err && err.message}` };
  }
}

/**
 * 걷기 검색창 전용 walk. 부품이 «고른 것»을 그대로 받습니다: `{type, keys, follow?, collect}`.
 *
 * 🔴 `createWalk` 을 못 씁니다 -- 그쪽 `collect` 는 «화면이 선언한 질문 이름»이고, 이쪽은
 *    «서버의 노드 종류»입니다. 같은 낱말이 두 뜻이라 섞으면 조용히 빈 답이 됩니다.
 * 🔴 결과는 «COLLECT 된 것»입니다 (소유자: 「결과는 COLLECT된 RETURN으로 보여줘」).
 *    walk 은 노드를 전부 실어 보내므로 «고른 종류»로 거르는 것이 그 문장의 뜻입니다.
 */
export function createWalkBoxWalk(deps) {
  const { apiBase, fetchImpl } = deps || {};
  const doFetch = fetchImpl || fetch;
  return async function walkBoxWalk(spec) {
    const { type, keys, follow } = spec || {};
    if (!type) return { ok: false, message: '노드 타입을 먼저 고르십시오' };
    const query = new URLSearchParams();
    query.set('id', entitySeedId(type, keys));
    // 🔴 «안 고르면 안 싣습니다». 빈 배열은 「아무것도 따르지 마라」이고 서버 기본값의 반대입니다.
    (follow || []).forEach((p) => query.append('follow', String(p).split('@')[0]));
    try {
      const res = await doFetch(`${apiBase || ''}/api/ledger/subgraph?${query}`);
      const body = await res.json().catch(() => null);
      if (!res.ok || !body) {
        const detail = body && body.detail;
        return { ok: false, message: (detail && detail.message)
          || `걷지 못했습니다 (${res.status})` };
      }
      // 🔴 여기서 «거르지 않습니다». 거르는 것은 walk 이 할 일이고, 부품이 받은 것을
      //    다시 좁히면 그 순간 화면이 「무엇을 못 봤는지」를 말할 수 없게 됩니다.
      const nodes = (body.nodes || [])
        .map((n) => ({ id: n.id, type: n.type, label: n.label }));
      return { ok: true, nodes, truncated: body.truncated || null };
    } catch (err) {
      return { ok: false, message: `걷기에 닿지 못했습니다 — ${err && err.message}` };
    }
  };
}
