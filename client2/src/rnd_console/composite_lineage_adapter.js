// composite_lineage_adapter.js — additive composite-CHIP lineage seam.
//
// The R&D screen must never flatten a final CHIP into one wafer path.  The
// backend may add `composite_lineage` to a response while existing ledger
// payloads remain valid; this adapter makes that addition optional and turns it
// into a stable read model for the investigation workspace.
//
// It deliberately does not fetch, choose a branch, or infer a missing identity.
// Those are ledger decisions.  A missing component id or transfer endpoint is a
// visible incomplete component, not a synthetic lot/slot identity.

const text = (value) => value == null ? '' : String(value);
const list = (value) => Array.isArray(value) ? value : [];

const RESOLUTION_STATES = new Set(['resolved', 'contested', 'candidate', 'unresolvable']);

function resolution(value) {
  const state = text(value).toLowerCase();
  return RESOLUTION_STATES.has(state) ? state : 'unresolvable';
}

function readPayload(raw) {
  if (!raw || typeof raw !== 'object') return null;
  // `composite_lineage` is the additive contract name reserved by the
  // integration shell.  `investigation.composite_lineage` supports a response
  // whose existing journey/trend body is left unchanged.
  if (raw.composite_lineage && typeof raw.composite_lineage === 'object') return raw.composite_lineage;
  if (raw.investigation && raw.investigation.composite_lineage
    && typeof raw.investigation.composite_lineage === 'object') return raw.investigation.composite_lineage;
  return null;
}

function position(value) {
  if (!value || typeof value !== 'object') return null;
  const container = text(value.container || value.lot || value.collection);
  const slot = text(value.slot);
  const coordinate = value.position == null ? '' : text(value.position);
  if (!container && !slot && !coordinate) return null;
  return { container, slot, position: coordinate };
}

function positions(value) {
  return list(value).map(position).filter(Boolean);
}

function lineageNode(raw, index) {
  const value = raw && typeof raw === 'object' ? raw : {};
  return {
    nodeId: text(value.node_id || value.id) || `unidentified-lineage-node-${index + 1}`,
    kind: text(value.kind) || 'event',
    label: text(value.label || value.display),
    state: resolution(value.state),
    address: position(value.address || value),
    occurredAt: text(value.occurred_at),
    sourceIds: list(value.source_ids).map(text).filter(Boolean),
    mapIds: list(value.map_ids).map(text).filter(Boolean),
  };
}

function transfer(event, index) {
  const raw = event && typeof event === 'object' ? event : {};
  return {
    eventId: text(raw.event_id || raw.id) || `unidentified-transfer-${index + 1}`,
    ordinal: Number.isFinite(Number(raw.ordinal)) ? Number(raw.ordinal) : index + 1,
    from: position(raw.from),
    to: position(raw.to),
    state: resolution(raw.state),
    reason: text(raw.reason),
    occurredAt: text(raw.occurred_at),
    sourceIds: list(raw.source_ids).map(text).filter(Boolean),
  };
}

function component(raw, index) {
  const value = raw && typeof raw === 'object' ? raw : {};
  const componentId = text(value.component_id || value.die_id || value.core_die_id);
  const transfers = list(value.transfers || value.transfer_chain).map(transfer);
  const dtCollections = positions(value.dt_collections || value.dt_visits);
  const fallbackDt = position(value.dt_collection || value.dt);
  if (!dtCollections.length && fallbackDt) dtCollections.push(fallbackDt);
  const pickEvents = list(value.pick_events).map((item, pickIndex) => ({
    eventId: text(item && (item.event_id || item.id)) || `unidentified-pick-${pickIndex + 1}`,
    from: position(item && (item.from || item.position || item)),
    state: resolution(item && item.state),
    occurredAt: text(item && item.occurred_at),
  }));
  const fallbackPick = position(value.pick || value.pick_position);
  if (!pickEvents.length && fallbackPick) {
    pickEvents.push({ eventId: text(value.pick_event_id), from: fallbackPick,
      state: resolution(value.pick_state || value.state), occurredAt: text(value.pick_occurred_at) });
  }
  const bondingEvents = list(value.bonding_events).map((item, bondingIndex) => ({
    eventId: text(item && (item.event_id || item.id)) || `unidentified-bonding-${bondingIndex + 1}`,
    layer: item && item.layer == null ? null : item.layer,
    role: text(item && (item.role || item.bonding_role)),
    position: position(item && (item.position || item.bonding_position)),
    state: resolution(item && item.state),
    occurredAt: text(item && item.occurred_at),
  }));
  if (!bondingEvents.length && (value.bonding_layer != null || value.bonding_position)) {
    bondingEvents.push({ eventId: text(value.bonding_event_id), layer: value.bonding_layer ?? null,
      role: text(value.bonding_role || value.role), position: position(value.bonding_position),
      state: resolution(value.bonding_state || value.state), occurredAt: text(value.bonding_occurred_at) });
  }
  return {
    // An empty value is intentional: consumers must render it as an identity
    // gap, never replace it with the source lot/slot (which can change).
    componentId,
    componentKey: componentId || `unidentified-component-${index + 1}`,
    identityState: componentId ? 'resolved' : 'unresolvable',
    core: {
      type: text(value.core_type),
      product: text(value.core_product),
      role: text(value.role),
      source: position(value.source_core || value.core_source),
    },
    // Arrays are the contract. Singular aliases are read-only bridges only.
    dtCollections,
    pickEvents,
    bondingEvents,
    lineageNodes: list(value.lineage_nodes).map(lineageNode),
    bonding: bondingEvents[0] || null,
    dt: dtCollections[0] || null,
    transfers,
    transferState: resolution(value.transfer_state || value.state),
    processClaims: list(value.process_claims),
    spatialEvidence: value.spatial_evidence && typeof value.spatial_evidence === 'object'
      ? value.spatial_evidence : null,
  };
}

/**
 * Normalise the additive composite lineage response without changing existing
 * journey/trend content.  Composition and process differences remain separate
 * collections so no caller can accidentally compare a missing component as a
 * missing process claim.
 */
export function normalizeCompositeLineage(raw) {
  const payload = readPayload(raw);
  if (!payload) {
    return {
      state: 'absent',
      reason: 'composite_lineage_not_provided',
      finalChip: null,
      components: [],
      comparisonSubjects: [],
      maps: [],
      compositionDifferences: [],
      processDifferences: [],
      spatialAttributions: [],
    };
  }

  const final = payload.final_chip && typeof payload.final_chip === 'object' ? payload.final_chip : {};
  const components = list(payload.components).map(component);
  return {
    state: text(payload.state) || 'ready',
    reason: text(payload.reason),
    finalChip: {
      chipId: text(final.chip_id || final.id),
      product: text(final.product),
      compositionState: resolution(final.composition_state || payload.composition_state || payload.state),
      layerCount: Number.isFinite(Number(final.layer_count)) ? Number(final.layer_count) : null,
    },
    components,
    comparisonSubjects: list(payload.comparison_subjects || payload.subjects).map((item, index) => ({
      subjectId: text(item && (item.subject_id || item.id)) || `unidentified-subject-${index + 1}`,
      label: text(item && (item.label || item.display || item.subject_id || item.id)),
    })),
    maps: list(payload.maps),
    // These lists are purposefully passed through as different planes.  The
    // workspace may fold equal process claims only after matching components by
    // role/type/position; it must not fold or align composition here.
    compositionDifferences: list(payload.composition_differences),
    processDifferences: list(payload.process_differences),
    spatialAttributions: list(payload.spatial_attributions).length
      ? list(payload.spatial_attributions)
      : (payload.spatial_attribution && typeof payload.spatial_attribution === 'object'
        ? [payload.spatial_attribution] : []),
  };
}

/**
 * Small stateful seam for the integration shell.  The owner of the workspace
 * can subscribe once; payload updates preserve the last normalised answer and
 * never mutate the server response.
 */
export function createCompositeLineageAdapter(onChange = null) {
  let current = normalizeCompositeLineage(null);
  return Object.freeze({
    update(raw) {
      current = normalizeCompositeLineage(raw);
      if (typeof onChange === 'function') onChange(current);
      return current;
    },
    current() { return current; },
  });
}
