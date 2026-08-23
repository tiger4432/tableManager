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
      dtCollectionCount: Array.isArray(c.dt_collections) ? c.dt_collections.length : null,
    })),
  };
}
