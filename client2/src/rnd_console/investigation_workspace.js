// R&D investigation workspace — composition-aware comparison, lineage and maps.
//
// This module owns no route names.  The integrating entry point injects an adapter:
//   loadWorkspace({ selection, signal }) -> workspace payload
// Optional mutations are also injected:
//   executeAction(action, { selection }) -> Promise
//
// A CHIP is a composition root, not a single wafer journey.  Every component branch
// keeps its own role/position/type and LOT/SLOT/TRANSFER evidence.


export const WORKSPACE_LAYER_ORDER = Object.freeze([
  'valid_die',
  'process_area',
  'used_area',
  'supply_material',
  'defect',
]);

export const CLAIM_STATES = Object.freeze([
  'recorded',
  'missing',
  'not_performed',
  'unknown',
  'contradiction',
]);

export const RESOLUTION_STATES = Object.freeze([
  'resolved',
  'candidate',
  'contested',
  'unresolvable',
]);

export const MAP_STAGE_ORDER = Object.freeze(['bond', 'dt', 'core']);

const KOREAN_STATE = Object.freeze({
  recorded: '기록됨',
  missing: '기록 누락',
  not_performed: '미실시',
  unknown: '확인 필요',
  contradiction: '모순',
  resolved: '확정',
  candidate: '후보',
  contested: '경합',
  unresolvable: '해소 불가',
});

const SORTERS = Object.freeze({
  role: (a, b) => text(a.role).localeCompare(text(b.role), 'ko') || componentTie(a, b),
  position: (a, b) => text(a.position).localeCompare(text(b.position), 'ko', { numeric: true }) || componentTie(a, b),
  type: (a, b) => text(a.type).localeCompare(text(b.type), 'ko') || componentTie(a, b),
});

function text(value, fallback = '') {
  return value === null || value === undefined ? fallback : String(value);
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function finite(value, fallback = null) {
  if (value === null || value === undefined || value === '') return fallback;
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function bool(value) {
  return value === true;
}

function componentTie(a, b) {
  return text(a.label).localeCompare(text(b.label), 'ko') || text(a.id).localeCompare(text(b.id));
}

export function normaliseClaimState(value) {
  const state = text(value).toLowerCase();
  return CLAIM_STATES.includes(state) ? state : 'unknown';
}

export function normaliseResolutionState(value) {
  const state = text(value).toLowerCase();
  return RESOLUTION_STATES.includes(state) ? state : 'unresolvable';
}

function normaliseSide(raw) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const state = normaliseClaimState(source.state);
  return {
    state,
    text: text(source.text || source.display || source.value),
    source: text(source.source),
    occurredAt: text(source.occurred_at),
    reason: text(source.reason),
  };
}

function normaliseDifference(raw, index) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const fallbackValues = [source.left || source.A, source.right || source.B];
  const values = list(source.values).length ? list(source.values) : fallbackValues;
  return {
    id: text(source.id, `difference-${index}`),
    label: text(source.label || source.display, '이름 없는 항목'),
    kind: text(source.kind, 'category'),
    state: normaliseClaimState(source.state || 'recorded'),
    sentence: text(source.sentence),
    left: normaliseSide(source.left || source.A),
    right: normaliseSide(source.right || source.B),
    // N-way contract: values align to `subjects[]` by stable subject id when
    // provided, and by array position only as a backwards-compatible fallback.
    values: values.map((value, valueIndex) => ({
      subjectId: text(value && (value.subject_id || value.subjectId)),
      ...normaliseSide(value),
      index: valueIndex,
    })),
    gates: list(source.gates).map((gate) => ({
      label: text(gate && gate.label),
      verdict: text(gate && gate.verdict, 'unknown'),
    })),
    spatialRef: source.spatial_ref && typeof source.spatial_ref === 'object'
      ? { mapId: text(source.spatial_ref.map_id), componentId: text(source.spatial_ref.component_id) }
      : null,
  };
}

function normaliseSegment(raw, index) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const differences = list(source.differences).map(normaliseDifference);
  return {
    id: text(source.id, `segment-${index}`),
    label: text(source.label || source.display, `구간 ${index + 1}`),
    state: differences.length ? 'different' : text(source.state, 'same'),
    sameCount: finite(source.same_count, 0),
    totalCount: finite(source.total_count, differences.length),
    differences,
    missingCount: finite(source.missing_count, differences.filter((item) => item.state === 'missing').length),
    contradictionCount: finite(source.contradiction_count,
      differences.filter((item) => item.state === 'contradiction').length),
  };
}

function normaliseTransfer(raw, index) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const from = source.from && typeof source.from === 'object' ? source.from : {};
  const to = source.to && typeof source.to === 'object' ? source.to : {};
  return {
    id: text(source.id, `transfer-${index}`),
    state: normaliseResolutionState(source.state),
    occurredAt: text(source.occurred_at),
    quantity: finite(source.quantity ?? source.qty),
    from: {
      stage: text(from.stage || from.type),
      lot: text(from.lot),
      slot: text(from.slot),
      position: text(from.position),
    },
    to: {
      stage: text(to.stage || to.type),
      lot: text(to.lot),
      slot: text(to.slot),
      position: text(to.position),
    },
    alternatives: list(source.alternatives).map((item) => ({
      lot: text(item && item.lot),
      slot: text(item && item.slot),
      reason: text(item && item.reason),
    })),
    reason: text(source.reason),
  };
}

function point(raw) {
  if (Array.isArray(raw)) return {
    x: finite(raw[0], 0), y: finite(raw[1], 0), value: finite(raw[2], 1),
    materialId: text(raw[3] ?? (typeof raw[2] === 'string' ? raw[2] : '')),
  };
  const source = raw && typeof raw === 'object' ? raw : {};
  return {
    x: finite(source.x, 0), y: finite(source.y, 0), value: finite(source.value, 1),
    materialId: text(source.material_id ?? source.materialId ?? (typeof source.value === 'string' ? source.value : '')),
  };
}

function materialColor(materialId) {
  let hash = 0;
  for (const char of text(materialId)) hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0;
  return `hsl(${Math.abs(hash) % 360} 62% 48%)`;
}

function declaredBoolean(value, fallback = false) {
  if (typeof value === 'boolean') return value;
  if (value === 'true' || value === 1 || value === '1') return true;
  if (value === 'false' || value === 0 || value === '0') return false;
  return fallback;
}

function normaliseMap(raw, index) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const meta = source.meta && typeof source.meta === 'object' ? source.meta : {};
  const frame = source.frame && typeof source.frame === 'object' ? source.frame : {};
  const coordinateSystem = frame.coordinate_system && typeof frame.coordinate_system === 'object'
    ? frame.coordinate_system
    : (meta.coordinate_system && typeof meta.coordinate_system === 'object' ? meta.coordinate_system : {});
  const layers = source.layers && typeof source.layers === 'object' ? source.layers : {};
  const layerCells = (value) => list(Array.isArray(value) ? value : value && value.cells);
  const mapId = text(source.id || source.map_id || frame.map_id || frame.mapId, `map-${index}`);
  return {
    id: mapId,
    label: text(source.label || source.map_id, `맵 ${index + 1}`),
    stage: text(source.stage),
    frame: {
      table: text(frame.table || source.table || meta.table),
      mapId: text(frame.map_id || frame.mapId || source.map_id || mapId),
      stage: text(frame.stage || source.stage),
      startX: finite(frame.start_x ?? frame.startX ?? coordinateSystem.start_x ?? coordinateSystem.startX
        ?? meta.start_x ?? meta.grid_start_x, 1),
      startY: finite(frame.start_y ?? frame.startY ?? coordinateSystem.start_y ?? coordinateSystem.startY
        ?? meta.start_y ?? meta.grid_start_y, 1),
      yInvert: declaredBoolean(frame.y_invert ?? frame.yInvert ?? coordinateSystem.y_invert
        ?? coordinateSystem.yInvert ?? meta.y_invert ?? meta.grid_y_invert, false),
    },
    componentId: text(source.component_id),
    identity: source.identity && typeof source.identity === 'object'
      ? structuredClone(source.identity)
      : (source.subject_identity && typeof source.subject_identity === 'object' ? structuredClone(source.subject_identity) : null),
    markKey: text(source.wafer_mark_key || source.mark_key || source.identity?.mark_key || source.subject_identity?.mark_key),
    wafer: text(source.identity?.keys?.wafer || source.subject_identity?.keys?.wafer || source.subject_wafer),
    bondingLeg: text(source.identity?.context?.bonding_leg || source.subject_identity?.context?.bonding_leg
      || source.subject_leg || source.bonding_leg),
    resolutionState: normaliseResolutionState(source.resolution_state || 'resolved'),
    meta: {
      cols: Math.max(1, finite(meta.cols ?? meta.grid_cols, 1)),
      rows: Math.max(1, finite(meta.rows ?? meta.grid_rows, 1)),
      startX: finite(frame.start_x ?? frame.startX ?? coordinateSystem.start_x ?? coordinateSystem.startX
        ?? meta.start_x ?? meta.grid_start_x, 1),
      startY: finite(frame.start_y ?? frame.startY ?? coordinateSystem.start_y ?? coordinateSystem.startY
        ?? meta.start_y ?? meta.grid_start_y, 1),
      yInvert: declaredBoolean(frame.y_invert ?? frame.yInvert ?? coordinateSystem.y_invert
        ?? coordinateSystem.yInvert ?? meta.y_invert ?? meta.grid_y_invert, false),
      rotation: finite(meta.rotation, 0),
      side: text(meta.side, 'front'),
      validDieRef: text(meta.valid_die_ref && (meta.valid_die_ref.map_id || meta.valid_die_ref)),
      validDieState: text(meta.valid_die_state,
        layers.valid_die && layers.valid_die.state === 'ready' ? 'present' : (meta.valid_die_ref ? 'present' : 'missing')),
      orientationState: text(meta.orientation_state, 'declared'),
    },
    layers: {
      valid_die: layerCells(layers.valid_die).map(point),
      process_area: layerCells(layers.process_area).map(point),
      used_area: layerCells(layers.used_area).map(point),
      supply_material: layerCells(layers.supply_material || layers.material_id).map(point),
      defect: layerCells(layers.defect).map(point),
    },
    relatedComponents: list(source.related_components).map(text).filter(Boolean),
  };
}

function normaliseComponent(raw, index) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const lineageNodes = list(source.lineage_nodes).map((item, nodeIndex) => ({
    id: text(item && item.id, `${text(source.id, `component-${index}`)}-node-${nodeIndex}`),
    kind: text(item && item.kind, 'event'),
    label: text(item && (item.label || item.display), '이름 없는 단계'),
    state: normaliseResolutionState(item && item.state),
    occurredAt: text(item && item.occurred_at),
    lot: text(item && item.lot),
    slot: text(item && item.slot),
    position: text(item && item.position),
    quantity: finite(item && (item.quantity ?? item.qty)),
    mapIds: list(item && item.map_ids).map(text).filter(Boolean),
  }));
  return {
    id: text(source.id, `component-${index}`),
    label: text(source.label || source.core_id, `Core ${index + 1}`),
    type: text(source.type || source.core_type, '미상'),
    role: text(source.role, '미상'),
    position: text(source.position, '미상'),
    quantity: finite(source.quantity ?? source.qty, 1),
    mappingState: normaliseResolutionState(source.mapping_state || 'resolved'),
    compositionState: normaliseClaimState(source.composition_state || 'recorded'),
    sameCount: finite(source.same_count, 0),
    segments: list(source.segments || source.process_segments).map(normaliseSegment),
    transfers: list(source.transfers || source.lineage).map(normaliseTransfer),
    lineageNodes,
    mapIds: list(source.map_ids).map(text).filter(Boolean),
    alternatives: list(source.alternatives).map((item) => ({
      label: text(item && (item.label || item.core_id)),
      reason: text(item && item.reason),
    })),
  };
}

function normaliseCandidate(raw, index) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const surprise = source.surprise && typeof source.surprise === 'object' ? source.surprise : {};
  return {
    id: text(source.id, `candidate-${index}`),
    rank: finite(source.rank, index + 1),
    label: text(source.label || source.display, '이름 없는 후보'),
    sentence: text(source.sentence),
    componentId: text(source.component_id),
    gates: list(source.gates).map((gate) => ({ label: text(gate && gate.label), verdict: text(gate && gate.verdict) })),
    evidenceCount: finite(source.evidence_count, 0),
    surprise: {
      score: finite(surprise.score),
      mechanismModelId: text(surprise.mechanism_model_id),
      bindingState: text(surprise.binding_state, 'unknown'),
    },
  };
}

function normaliseAction(raw, index) {
  const source = raw && typeof raw === 'object' ? raw : {};
  return {
    id: text(source.id, `action-${index}`),
    rank: finite(source.rank, index + 1),
    kind: text(source.kind, 'collect'),
    label: text(source.label, '다음 확인'),
    sentence: text(source.sentence),
    informationGain: finite(source.information_gain, 0),
    hypothesesSplit: finite(source.hypotheses_split, 0),
    missingResolved: finite(source.missing_resolved, 0),
    targetCount: finite(source.target_count, 0),
    status: text(source.status, 'proposed'),
  };
}

function normaliseGroup(raw, index) {
  const source = raw && typeof raw === 'object' ? raw : {};
  return {
    id: text(source.id || source.key, `group-${index + 1}`),
    label: text(source.label || source.id || source.key, `Group ${index + 1}`),
    color: text(source.color),
    count: finite(source.count, 0),
  };
}

function normaliseComparison(raw, index) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const surprise = source.surprise && typeof source.surprise === 'object' ? source.surprise : {};
  return {
    id: text(source.id, `comparison-${index + 1}`),
    label: text(source.label || source.name, `항목 ${index + 1}`),
    state: normaliseClaimState(source.state || 'recorded'),
    kind: text(source.kind),
    predicate: text(source.predicate),
    signature: source.signature && typeof source.signature === 'object' ? structuredClone(source.signature) : {},
    waferMarkKeys: list(source.wafer_mark_keys || source.waferMarkKeys).map(text).filter(Boolean),
    evidenceIds: list(source.evidence_ids || source.evidenceIds).map(text).filter(Boolean),
    sentence: text(source.sentence),
    delta: finite(source.delta),
    surprise: {
      score: finite(surprise.score),
      expected: text(surprise.expected),
      observed: text(surprise.observed),
      mechanismModelId: text(surprise.mechanism_model_id),
      bindingState: text(surprise.binding_state, 'unknown'),
    },
    groups: list(source.groups || source.values).map((value, valueIndex) => ({
      groupId: text(value && (value.group_id || value.groupId || value.id), `group-${valueIndex + 1}`),
      value: text(value && (value.value ?? value.display)),
      count: finite(value && value.count),
      total: finite(value && value.total),
      state: normaliseClaimState(value && value.state),
      waferMarkKeys: list(value && (value.wafer_mark_keys || value.waferMarkKeys)).map(text).filter(Boolean),
      evidenceIds: list(value && (value.evidence_ids || value.evidenceIds)).map(text).filter(Boolean),
    })),
  };
}

/** Pure payload boundary.  It deliberately preserves unknown/missing/not-performed separately. */
export function normaliseInvestigationPayload(raw) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const subjects = list(source.subjects).map((subject, index) => ({
    id: text(subject && (subject.id || subject.key), `subject-${index}`),
    label: text(subject && (subject.label || subject.id || subject.key), `대상 ${index + 1}`),
    population: text(subject && subject.population, 'unspecified'),
  }));
  const components = list(source.components || (source.composition && source.composition.components))
    .map(normaliseComponent);
  const maps = list(source.maps).map(normaliseMap);
  const candidates = list(source.candidates).map(normaliseCandidate)
    .sort((a, b) => a.rank - b.rank || b.evidenceCount - a.evidenceCount);
  const actions = list(source.actions).map(normaliseAction)
    .sort((a, b) => b.informationGain - a.informationGain || a.rank - b.rank);
  const comparisons = source.comparisons && typeof source.comparisons === 'object' ? source.comparisons : {};
  const surprise = source.surprise && typeof source.surprise === 'object' ? source.surprise : {};
  return {
    state: text(source.state, subjects.length ? 'ready' : 'idle'),
    headline: text(source.headline),
    coverage: {
      attributed: finite(source.coverage && source.coverage.attributed, 0),
      total: finite(source.coverage && source.coverage.total, 0),
    },
    subjects,
    groups: list(source.groups || source.selection_groups).map(normaliseGroup),
    surprise: {
      score: finite(surprise.score),
      label: text(surprise.label),
      mechanismModelId: text(surprise.mechanism_model_id),
      bindingState: text(surprise.binding_state, 'unknown'),
    },
    comparisons: {
      process: list(comparisons.process).map(normaliseComparison),
      measurement: list(comparisons.measurement).map(normaliseComparison),
      context: list(comparisons.context || comparisons.auxiliary).map(normaliseComparison),
    },
    compositionSummary: {
      sameCount: finite(source.composition && source.composition.same_count, 0),
      differentCount: finite(source.composition && source.composition.different_count,
        components.filter((item) => item.segments.some((segment) => segment.differences.length)).length),
      unresolvedCount: finite(source.composition && source.composition.unresolved_count,
        components.filter((item) => item.mappingState !== 'resolved').length),
    },
    compositionDifferences: list(source.composition && source.composition.differences)
      .map((item, index) => ({
        id: text(item && item.id, `composition-difference-${index}`),
        label: text(item && item.label, '구성 차이'),
        sentence: text(item && item.sentence),
        state: normaliseClaimState(item && item.state),
        componentIds: list(item && item.component_ids).map(text).filter(Boolean),
      })),
    components,
    maps,
    candidates,
    actions,
    notes: list(source.notes).map(text).filter(Boolean),
  };
}

export function sortComponents(components, by = 'role') {
  return [...list(components)].sort(SORTERS[by] || SORTERS.role);
}

export function rankedActions(actions) {
  return list(actions).map(normaliseAction)
    .sort((a, b) => b.informationGain - a.informationGain || a.rank - b.rank);
}

function comparableGroupValue(value) {
  if (!value || value.state !== 'recorded') return null;
  if (value.value !== '') return `value:${value.value}`;
  if (value.count === null || value.total === null || value.total <= 0) return null;
  return `ratio:${value.count / value.total}`;
}

/**
 * Split a complete comparison list without hiding missing/unknown claims.
 * Only fully recorded rows with the same value (or rate) in every selected
 * group are folded.  Everything else remains visible as an investigation lead.
 */
export function partitionComparisonRows(rows, groups) {
  const groupIds = list(groups).map((group) => text(group && group.id)).filter(Boolean);
  const result = { different: [], same: [] };
  for (const row of list(rows)) {
    const byGroup = new Map(list(row && row.groups).map((value) => [value.groupId, value]));
    const values = groupIds.map((groupId) => comparableGroupValue(byGroup.get(groupId)));
    const isSame = groupIds.length > 1
      && values.every((value) => value !== null)
      && values.every((value) => value === values[0]);
    result[isSame ? 'same' : 'different'].push(row);
  }
  return result;
}

function comparisonDisplayKey(row, groups) {
  const byGroup = new Map(list(row && row.groups).map((value) => [value.groupId, value]));
  const values = list(groups).map((group) => {
    const value = byGroup.get(text(group && group.id)) || {};
    return [text(value.state), text(value.value), value.count, value.total];
  });
  return JSON.stringify([
    text(row && row.label), text(row && row.state), text(row && row.sentence),
    row && row.delta, row && row.surprise && row.surprise.score, values,
  ]);
}

/** Keep every row, but fold evidence rows that would render identically. */
export function groupDuplicateComparisonRows(rows, groups) {
  const buckets = new Map();
  for (const row of list(rows)) {
    const key = comparisonDisplayKey(row, groups);
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key).push(row);
  }
  const singles = [];
  const duplicates = [];
  for (const groupedRows of buckets.values()) {
    if (groupedRows.length === 1) singles.push(groupedRows[0]);
    else duplicates.push({ rows: groupedRows, count: groupedRows.length });
  }
  return { singles, duplicates };
}

function canonicalMapStage(map) {
  const value = `${text(map && map.stage)} ${text(map && map.frame && map.frame.stage)}`.toLowerCase();
  if (value.includes('bond')) return 'bond';
  if (/(^|\W)dt(\W|$)/.test(value)) return 'dt';
  if (value.includes('core')) return 'core';
  return 'other';
}

/** Preserve every map while arranging hierarchy vertically and peer WF maps horizontally. */
export function partitionMapsByStage(maps) {
  const buckets = new Map([...MAP_STAGE_ORDER, 'other'].map((stage) => [stage, []]));
  for (const map of list(maps)) buckets.get(canonicalMapStage(map)).push(map);
  return [...buckets].filter(([, rows]) => rows.length).map(([stage, rows]) => ({ stage, maps: rows }));
}

function node(doc, tag, className, content) {
  const element = doc.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined && content !== null) element.textContent = String(content);
  return element;
}

function clear(element) {
  while (element.firstChild) element.removeChild(element.firstChild);
}

function stateBadge(doc, state) {
  const badge = node(doc, 'span', `riw-state riw-state--${state}`, KOREAN_STATE[state] || '확인 필요');
  badge.dataset.state = state;
  return badge;
}

function section(doc, title, className = '') {
  const box = node(doc, 'section', `riw-panel ${className}`.trim());
  box.appendChild(node(doc, 'h2', 'riw-panel__title', title));
  return box;
}

function renderCoverage(doc, model) {
  const total = model.coverage.total;
  const attributed = model.coverage.attributed;
  const wrap = node(doc, 'div', 'riw-coverage');
  wrap.appendChild(node(doc, 'span', 'riw-coverage__label', '귀속 범위'));
  wrap.appendChild(node(doc, 'strong', 'riw-coverage__value', total ? `${attributed}/${total}` : '확인 필요'));
  const meter = node(doc, 'span', 'riw-coverage__meter');
  const fill = node(doc, 'i', 'riw-coverage__fill');
  fill.style.width = `${total ? Math.max(0, Math.min(100, attributed / total * 100)) : 0}%`;
  meter.appendChild(fill);
  wrap.appendChild(meter);
  return wrap;
}

function renderComparisonRow(doc, row, groups, category) {
  const item = node(doc, 'button', `riw-compare-row riw-compare-row--${row.state}`);
  item.type = 'button';
  item.dataset.comparisonId = row.id;
  item.dataset.comparisonCategory = category;
  item.title = '이 조건과 연결된 WF 마킹';
  item.style.setProperty('--riw-group-count', Math.max(1, groups.length));
  const label = node(doc, 'div', 'riw-compare-row__label');
  label.appendChild(node(doc, 'b', '', row.label));
  if (row.surprise.score !== null) {
    label.appendChild(node(doc, 'em', 'riw-surprise-score', `놀라움 ${row.surprise.score.toFixed(2)}`));
  }
  if (row.sentence) label.appendChild(node(doc, 'span', '', row.sentence));
  item.appendChild(label);
  const byGroup = new Map(row.groups.map((value) => [value.groupId, value]));
  for (const group of groups) {
    const value = byGroup.get(group.id) || { state: 'unknown', value: '', count: null, total: null };
    const cell = node(doc, 'div', `riw-compare-value riw-compare-value--${value.state}`);
    cell.appendChild(node(doc, 'small', '', group.label));
    const display = value.value || (value.count !== null
      ? `${value.count}${value.total !== null ? `/${value.total}` : ''}`
      : KOREAN_STATE[value.state]);
    cell.appendChild(node(doc, 'b', '', display));
    item.appendChild(cell);
  }
  return item;
}

function renderComparisonCategory(doc, title, rows, groups, category) {
  const panel = section(doc, title, 'riw-compare-category');
  for (const row of rows.slice(0, 1)) panel.appendChild(renderComparisonRow(doc, row, groups, category));
  if (rows.length > 1) {
    const more = node(doc, 'details', 'riw-more');
    more.appendChild(node(doc, 'summary', 'riw-more__summary', `${rows.length - 1}개 더 보기`));
    const body = node(doc, 'div', 'riw-more__body');
    for (const row of rows.slice(1)) body.appendChild(renderComparisonRow(doc, row, groups, category));
    more.appendChild(body);
    panel.appendChild(more);
  }
  if (!rows.length) panel.appendChild(node(doc, 'p', 'riw-empty', '비교 가능한 기록이 없습니다.'));
  return panel;
}

function renderGroupComparison(doc, model) {
  const box = node(doc, 'section', 'riw-group-comparison');
  const head = node(doc, 'header', 'riw-group-comparison__head');
  head.appendChild(node(doc, 'h2', '', 'Group Comparison'));
  const chips = node(doc, 'div', 'riw-group-chips');
  for (const group of model.groups) {
    const chip = node(doc, 'span', 'riw-group-chip', `${group.label} · ${group.count}`);
    if (group.color) chip.style.setProperty('--riw-group-color', group.color);
    chips.appendChild(chip);
  }
  head.appendChild(chips);
  if (model.surprise.score !== null) {
    const surprise = node(doc, 'strong', 'riw-surprise-total', `Surprise ${model.surprise.score.toFixed(2)}`);
    surprise.title = model.surprise.mechanismModelId || '물리 모델 근거 확인 필요';
    head.appendChild(surprise);
  }
  box.appendChild(head);
  const grid = node(doc, 'div', 'riw-compare-grid');
  grid.appendChild(renderComparisonCategory(doc, 'Process', model.comparisons.process, model.groups, 'process'));
  grid.appendChild(renderComparisonCategory(doc, 'Measurement', model.comparisons.measurement, model.groups, 'measurement'));
  grid.appendChild(renderComparisonCategory(doc, 'Context', model.comparisons.context, model.groups, 'context'));
  box.appendChild(grid);
  return box;
}

function renderComponentList(doc, model, state) {
  const panel = section(doc, 'Chip Composition', 'riw-composition');
  const summary = node(doc, 'div', 'riw-summary');
  summary.appendChild(node(doc, 'span', '', `동일 ${model.compositionSummary.sameCount}`));
  summary.appendChild(node(doc, 'span', 'riw-summary__hot', `차이 ${model.compositionSummary.differentCount}`));
  summary.appendChild(node(doc, 'span', 'riw-summary__warn', `미해소 ${model.compositionSummary.unresolvedCount}`));
  panel.appendChild(summary);

  const controls = node(doc, 'div', 'riw-sort');
  controls.appendChild(node(doc, 'span', 'riw-sort__label', '묶기'));
  for (const [id, label] of [['role', '역할'], ['position', '위치'], ['type', '종류']]) {
    const button = node(doc, 'button', `riw-chip${state.sortBy === id ? ' is-active' : ''}`, label);
    button.type = 'button';
    button.dataset.sort = id;
    controls.appendChild(button);
  }
  panel.appendChild(controls);

  if (model.compositionDifferences.length) {
    const differences = node(doc, 'div', 'riw-composition-differences');
    for (const difference of model.compositionDifferences) {
      const row = node(doc, 'div', `riw-composition-difference riw-composition-difference--${difference.state}`);
      row.appendChild(node(doc, 'b', '', difference.label));
      row.appendChild(node(doc, 'span', '', difference.sentence || KOREAN_STATE[difference.state] || '확인 필요'));
      differences.appendChild(row);
    }
    panel.appendChild(differences);
  }

  const listNode = node(doc, 'div', 'riw-component-list');
  for (const component of sortComponents(model.components, state.sortBy)) {
    const row = node(doc, 'button', `riw-component${state.componentId === component.id ? ' is-active' : ''}`);
    row.type = 'button';
    row.dataset.componentId = component.id;
    const head = node(doc, 'span', 'riw-component__head');
    head.appendChild(node(doc, 'b', '', component.label));
    head.appendChild(stateBadge(doc, component.mappingState));
    row.appendChild(head);
    row.appendChild(node(doc, 'span', 'riw-component__meta',
      `${component.type} · ${component.role} · ${component.position} · ${component.quantity}개`));
    const diffCount = component.segments.reduce((sum, segment) => sum + segment.differences.length, 0);
    row.appendChild(node(doc, 'span', 'riw-component__counts',
      `같음 ${component.sameCount} · 차이 ${diffCount}`));
    listNode.appendChild(row);
  }
  if (!model.components.length) listNode.appendChild(node(doc, 'p', 'riw-empty', '구성 정보가 없습니다.'));
  panel.appendChild(listNode);
  return panel;
}

function sideCell(doc, side, label) {
  const cell = node(doc, 'span', `riw-side riw-side--${side.state}`);
  cell.appendChild(node(doc, 'small', '', label));
  cell.appendChild(node(doc, 'b', '', side.text || KOREAN_STATE[side.state] || '확인 필요'));
  if (side.reason) cell.title = side.reason;
  return cell;
}

function renderDifference(doc, difference, subjects) {
  const row = node(doc, 'article', `riw-difference riw-difference--${difference.state}`);
  const head = node(doc, 'div', 'riw-difference__head');
  head.appendChild(node(doc, 'b', '', difference.label));
  if (difference.state !== 'recorded') head.appendChild(stateBadge(doc, difference.state));
  row.appendChild(head);
  if (difference.sentence) row.appendChild(node(doc, 'p', 'riw-difference__sentence', difference.sentence));
  const sides = node(doc, 'div', 'riw-difference__sides');
  const valuesBySubject = new Map(difference.values.filter((value) => value.subjectId)
    .map((value) => [value.subjectId, value]));
  const displaySubjects = subjects.length ? subjects : [{ id: 'A', label: '대상 A' }, { id: 'B', label: '대상 B' }];
  for (let index = 0; index < displaySubjects.length; index += 1) {
    const subject = displaySubjects[index];
    const value = valuesBySubject.get(subject.id) || difference.values[index]
      || (index === 0 ? difference.left : (index === 1 ? difference.right : normaliseSide(null)));
    sides.appendChild(sideCell(doc, value, subject.label));
  }
  row.appendChild(sides);
  if (difference.gates.length) {
    const gates = node(doc, 'div', 'riw-gates');
    for (const gate of difference.gates) {
      const chip = node(doc, 'span', `riw-gate riw-gate--${gate.verdict}`, gate.label || '판정');
      chip.dataset.verdict = gate.verdict;
      gates.appendChild(chip);
    }
    row.appendChild(gates);
  }
  if (difference.spatialRef && difference.spatialRef.mapId) {
    const drill = node(doc, 'button', 'riw-inline-action', '관련 위치 보기');
    drill.type = 'button';
    drill.dataset.mapId = difference.spatialRef.mapId;
    if (difference.spatialRef.componentId) drill.dataset.componentId = difference.spatialRef.componentId;
    row.appendChild(drill);
  }
  return row;
}

function renderProcess(doc, model, state) {
  const panel = section(doc, 'Process Difference', 'riw-process');
  const component = model.components.find((item) => item.id === state.componentId) || model.components[0];
  if (!component) {
    panel.appendChild(node(doc, 'p', 'riw-empty', '비교할 구성 Core가 없습니다.'));
    return panel;
  }
  const context = node(doc, 'div', 'riw-context');
  context.appendChild(node(doc, 'b', '', component.label));
  context.appendChild(node(doc, 'span', '', `${component.role} · ${component.position}`));
  panel.appendChild(context);

  const track = node(doc, 'div', 'riw-segments');
  for (const segment of component.segments) {
    const block = node(doc, 'details', `riw-segment${segment.differences.length ? ' is-different' : ''}`);
    // The first screen carries conclusions and actions. 100+ claim details stay folded
    // until the investigator asks for them.
    block.open = false;
    const summary = node(doc, 'summary', 'riw-segment__summary');
    summary.appendChild(node(doc, 'b', '', segment.label));
    const account = [];
    if (segment.sameCount) account.push(`같음 ${segment.sameCount}`);
    if (segment.differences.length) account.push(`차이 ${segment.differences.length}`);
    if (segment.missingCount) account.push(`누락 ${segment.missingCount}`);
    if (segment.contradictionCount) account.push(`모순 ${segment.contradictionCount}`);
    summary.appendChild(node(doc, 'span', '', account.join(' · ') || '차이 없음'));
    block.appendChild(summary);
    const body = node(doc, 'div', 'riw-segment__body');
    for (const difference of segment.differences) body.appendChild(renderDifference(doc, difference, model.subjects));
    if (!segment.differences.length) body.appendChild(node(doc, 'p', 'riw-folded', `동일 항목 ${segment.sameCount || segment.totalCount}개`));
    block.appendChild(body);
    track.appendChild(block);
  }
  if (!component.segments.length) track.appendChild(node(doc, 'p', 'riw-empty', '공정 기록이 없습니다.'));
  panel.appendChild(track);
  return panel;
}

function addressText(address) {
  const parts = [];
  if (address.stage) parts.push(address.stage);
  if (address.lot) parts.push(`LOT ${address.lot}`);
  if (address.slot) parts.push(`SLOT ${address.slot}`);
  if (address.position) parts.push(address.position);
  return parts.join(' · ') || '주소 확인 필요';
}

function renderLineage(doc, model, state) {
  const panel = section(doc, 'Transfer Lineage', 'riw-lineage');
  const component = model.components.find((item) => item.id === state.componentId) || model.components[0];
  if (!component || (!component.lineageNodes.length && !component.transfers.length)) {
    panel.appendChild(node(doc, 'p', 'riw-empty', '이 구성의 이동 기록이 없습니다.'));
    return panel;
  }
  if (component.lineageNodes.length) {
    const chain = node(doc, 'ol', 'riw-lineage-chain');
    for (const lineageNode of component.lineageNodes) {
      const item = node(doc, 'li', `riw-lineage-node riw-lineage-node--${lineageNode.state}`);
      const head = node(doc, 'div', 'riw-lineage-node__head');
      head.appendChild(node(doc, 'b', '', lineageNode.label));
      head.appendChild(stateBadge(doc, lineageNode.state));
      item.appendChild(head);
      const address = [lineageNode.lot && `LOT ${lineageNode.lot}`,
        lineageNode.slot && `SLOT ${lineageNode.slot}`, lineageNode.position].filter(Boolean).join(' · ');
      if (address) item.appendChild(node(doc, 'span', 'riw-lineage-node__address', address));
      if (lineageNode.occurredAt) item.appendChild(node(doc, 'time', '', lineageNode.occurredAt));
      if (lineageNode.mapIds.length) {
        const maps = node(doc, 'div', 'riw-lineage-node__maps');
        for (const mapId of lineageNode.mapIds) {
          const button = node(doc, 'button', 'riw-inline-action', '관련 맵 보기');
          button.type = 'button';
          button.dataset.mapId = mapId;
          maps.appendChild(button);
        }
        item.appendChild(maps);
      }
      chain.appendChild(item);
    }
    panel.appendChild(chain);
  }
  for (const transfer of component.transfers) {
    const event = node(doc, 'article', `riw-transfer riw-transfer--${transfer.state}`);
    const head = node(doc, 'div', 'riw-transfer__head');
    head.appendChild(node(doc, 'b', '', '이동'));
    head.appendChild(stateBadge(doc, transfer.state));
    if (transfer.occurredAt) head.appendChild(node(doc, 'time', '', transfer.occurredAt));
    event.appendChild(head);
    event.appendChild(node(doc, 'div', 'riw-transfer__address', addressText(transfer.from)));
    event.appendChild(node(doc, 'div', 'riw-transfer__arrow', '↓'));
    event.appendChild(node(doc, 'div', 'riw-transfer__address', addressText(transfer.to)));
    if (transfer.quantity !== null) event.appendChild(node(doc, 'span', 'riw-transfer__qty', `${transfer.quantity}개`));
    if (transfer.reason) event.appendChild(node(doc, 'p', 'riw-transfer__reason', transfer.reason));
    if (transfer.alternatives.length) {
      const choices = node(doc, 'div', 'riw-transfer__choices');
      for (const alt of transfer.alternatives) {
        choices.appendChild(node(doc, 'span', '', `${alt.lot || 'LOT 미상'} / ${alt.slot || 'SLOT 미상'}`));
      }
      event.appendChild(choices);
    }
    panel.appendChild(event);
  }
  return panel;
}

function renderMapSvg(doc, map, visibleLayers) {
  const width = map.meta.cols;
  const height = map.meta.rows;
  const svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.classList.add('riw-map-svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `${map.label} 좌표 맵`);
  for (const layerId of WORKSPACE_LAYER_ORDER) {
    if (!visibleLayers.has(layerId)) continue;
    const group = doc.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.classList.add('riw-map-layer', `riw-map-layer--${layerId}`);
    group.dataset.layer = layerId;
    for (const cell of map.layers[layerId]) {
      const rect = doc.createElementNS('http://www.w3.org/2000/svg', 'rect');
      const localX = cell.x - map.meta.startX;
      const localY = cell.y - map.meta.startY;
      rect.setAttribute('x', String(localX));
      rect.setAttribute('y', String(map.meta.yInvert ? height - 1 - localY : localY));
      rect.setAttribute('width', '0.92');
      rect.setAttribute('height', '0.92');
      rect.setAttribute('data-map-cell', 'true');
      rect.setAttribute('data-map-id', map.id);
      rect.setAttribute('data-frame-map-id', map.frame.mapId);
      rect.setAttribute('data-frame-table', map.frame.table);
      rect.setAttribute('data-frame-stage', map.frame.stage);
      rect.setAttribute('data-identity-mark-key', map.markKey);
      rect.setAttribute('data-identity-wafer', map.wafer);
      rect.setAttribute('data-identity-bonding-leg', map.bondingLeg);
      rect.setAttribute('data-frame-start-x', String(map.frame.startX));
      rect.setAttribute('data-frame-start-y', String(map.frame.startY));
      rect.setAttribute('data-frame-y-invert', String(map.frame.yInvert));
      rect.setAttribute('data-layer', layerId);
      rect.setAttribute('data-x', String(cell.x));
      rect.setAttribute('data-y', String(cell.y));
      if (layerId === 'defect') rect.setAttribute('data-count', String(cell.value));
      if (layerId === 'supply_material' && cell.materialId) {
        rect.setAttribute('data-material-id', cell.materialId);
        rect.style.setProperty('--riw-material-color', materialColor(cell.materialId));
      }
      group.appendChild(rect);
    }
    svg.appendChild(group);
  }
  return svg;
}

function renderMaps(doc, model, state) {
  const panel = section(doc, 'Source / Supply Maps', 'riw-maps');
  const toolbar = node(doc, 'div', 'riw-map-toolbar');
  const labels = {
    valid_die: '유효 다이',
    process_area: '공정 영역',
    used_area: '사용 영역',
    supply_material: 'Supply 자재',
    defect: '불량',
  };
  for (const layer of WORKSPACE_LAYER_ORDER) {
    const label = node(doc, 'label', 'riw-layer-toggle');
    const input = node(doc, 'input');
    input.type = 'checkbox';
    input.checked = state.layers.has(layer);
    input.dataset.layer = layer;
    label.appendChild(input);
    label.appendChild(node(doc, 'span', '', labels[layer]));
    toolbar.appendChild(label);
  }
  panel.appendChild(toolbar);

  const appendMap = (strip, map) => {
    const card = node(doc, 'article', `riw-map${state.mapId === map.id ? ' is-active' : ''}`);
    card.dataset.mapId = map.id;
    card.dataset.stage = canonicalMapStage(map);
    const head = node(doc, 'div', 'riw-map__head');
    head.appendChild(node(doc, 'b', '', `${map.stage ? `${map.stage.toUpperCase()} · ` : ''}${map.label}`));
    head.appendChild(stateBadge(doc, map.resolutionState));
    card.appendChild(head);
    if (map.meta.validDieState !== 'present') {
      card.appendChild(node(doc, 'p', 'riw-map__warning', '유효 다이 기준 확인 필요'));
    } else {
      card.appendChild(renderMapSvg(doc, map, state.layers));
    }
    const meta = node(doc, 'div', 'riw-map__meta');
    meta.appendChild(node(doc, 'span', '', `${map.meta.cols}×${map.meta.rows}`));
    meta.appendChild(node(doc, 'span', '', `시작 ${map.meta.startX}, ${map.meta.startY}`));
    meta.appendChild(node(doc, 'span', '', `${map.meta.rotation}° · ${map.meta.side === 'back' ? '후면' : '전면'}`));
    card.appendChild(meta);
    const materials = [...new Set(map.layers.supply_material.map((cell) => cell.materialId).filter(Boolean))];
    if (materials.length) {
      const legend = node(doc, 'div', 'riw-material-legend');
      for (const materialId of materials.slice(0, 6)) {
        const item = node(doc, 'span', 'riw-material-legend__item', materialId);
        item.style.setProperty('--riw-material-color', materialColor(materialId));
        legend.appendChild(item);
      }
      if (materials.length > 6) legend.appendChild(node(doc, 'span', '', `+${materials.length - 6}`));
      card.appendChild(legend);
    }
    if (map.meta.orientationState !== 'declared') {
      card.appendChild(node(doc, 'p', 'riw-map__warning', '방향 정확성 확인 중'));
    }
    strip.appendChild(card);
  };
  const stack = node(doc, 'div', 'riw-map-stage-stack');
  const stageLabels = { bond: 'BONDING', dt: 'DT', core: 'CORE', other: 'OTHER' };
  for (const group of partitionMapsByStage(model.maps)) {
    const stage = node(doc, 'section', 'riw-map-stage');
    stage.dataset.mapStage = group.stage;
    const head = node(doc, 'header', 'riw-map-stage__head');
    head.appendChild(node(doc, 'h3', '', stageLabels[group.stage]));
    head.appendChild(node(doc, 'span', '', `${group.maps.length}개 맵`));
    stage.appendChild(head);
    const strip = node(doc, 'div', 'riw-map-strip');
    const maps = state.mapId && group.maps.some((map) => map.id === state.mapId)
      ? [...group.maps].sort((left, right) => Number(right.id === state.mapId) - Number(left.id === state.mapId))
      : group.maps;
    for (const map of maps) appendMap(strip, map);
    stage.appendChild(strip);
    stack.appendChild(stage);
  }
  if (!model.maps.length) stack.appendChild(node(doc, 'p', 'riw-empty', '연결된 맵이 없습니다.'));
  panel.appendChild(stack);
  return panel;
}

function renderCandidates(doc, model, state) {
  const panel = section(doc, 'Candidates', 'riw-candidates');
  const categories = node(doc, 'div', 'riw-candidate-categories');
  const appendCategory = (title, rows, category) => {
    const bucket = partitionComparisonRows(rows, model.groups);
    const displayed = groupDuplicateComparisonRows(bucket.different, model.groups);
    const duplicateCount = displayed.duplicates.reduce((total, group) => total + group.count, 0);
    const box = node(doc, 'section', 'riw-candidate-category');
    box.dataset.candidateCategory = category;
    const head = node(doc, 'header', 'riw-candidate-category__head');
    head.appendChild(node(doc, 'h3', '', title));
    head.appendChild(node(doc, 'span', '',
      `차이 ${bucket.different.length} · 같은 기록 ${duplicateCount}개 접힘 · 동일 ${bucket.same.length}`));
    box.appendChild(head);
    for (const row of displayed.singles) {
      box.appendChild(renderComparisonRow(doc, row, model.groups, category));
    }
    if (displayed.duplicates.length) {
      const repeated = node(doc, 'details', 'riw-more riw-duplicate-candidates');
      repeated.dataset.duplicateCount = String(duplicateCount);
      repeated.appendChild(node(doc, 'summary', 'riw-more__summary',
        `같은 기록 ${duplicateCount}개 · ${displayed.duplicates.length}묶음`));
      const repeatedBody = node(doc, 'div', 'riw-more__body');
      for (const duplicate of displayed.duplicates) {
        const folded = node(doc, 'details', 'riw-more riw-duplicate-candidate-group');
        folded.dataset.duplicateCount = String(duplicate.count);
        folded.appendChild(node(doc, 'summary', 'riw-more__summary',
          `${duplicate.rows[0].label} · ${duplicate.count}건`));
        const body = node(doc, 'div', 'riw-more__body');
        for (const row of duplicate.rows) body.appendChild(renderComparisonRow(doc, row, model.groups, category));
        folded.appendChild(body);
        repeatedBody.appendChild(folded);
      }
      repeated.appendChild(repeatedBody);
      box.appendChild(repeated);
    }
    if (bucket.same.length) {
      const same = node(doc, 'details', 'riw-more riw-same-candidates');
      same.dataset.sameCount = String(bucket.same.length);
      same.appendChild(node(doc, 'summary', 'riw-more__summary', `동일 ${bucket.same.length}개`));
      const body = node(doc, 'div', 'riw-more__body');
      for (const row of bucket.same) body.appendChild(renderComparisonRow(doc, row, model.groups, category));
      same.appendChild(body);
      box.appendChild(same);
    }
    if (!rows.length) box.appendChild(node(doc, 'p', 'riw-empty', '비교 가능한 기록이 없습니다.'));
    categories.appendChild(box);
  };
  appendCategory('Process', model.comparisons.process, 'process');
  appendCategory('Measurement', model.comparisons.measurement, 'measurement');
  panel.appendChild(categories);
  return panel;
}

function renderActions(doc, model) {
  const panel = section(doc, 'Next Best Action', 'riw-actions');
  const appendAction = (target, action) => {
    const row = node(doc, 'article', 'riw-action');
    row.appendChild(node(doc, 'span', 'riw-action__score', action.informationGain.toFixed(1)));
    const body = node(doc, 'div', 'riw-action__body');
    const actionTitle = node(doc, 'div', 'riw-action__title');
    actionTitle.appendChild(node(doc, 'b', '', action.label));
    actionTitle.appendChild(node(doc, 'span', 'riw-action__kind', action.kind === 'doe' ? 'DOE' : '결측 확보'));
    body.appendChild(actionTitle);
    if (action.sentence) body.appendChild(node(doc, 'p', '', action.sentence));
    body.appendChild(node(doc, 'small', '',
      `가설 ${action.hypothesesSplit}개 분리 · 결측 ${action.missingResolved}개 해소 · 대상 ${action.targetCount}개`));
    row.appendChild(body);
    const button = node(doc, 'button', 'riw-action__button', '검토');
    button.type = 'button';
    button.dataset.actionId = action.id;
    row.appendChild(button);
    target.appendChild(row);
  };
  if (model.actions.length) appendAction(panel, model.actions[0]);
  if (model.actions.length > 1) {
    const more = node(doc, 'details', 'riw-more');
    more.appendChild(node(doc, 'summary', 'riw-more__summary', `액션 ${model.actions.length - 1}개 더 보기`));
    const body = node(doc, 'div', 'riw-more__body');
    for (const action of model.actions.slice(1)) appendAction(body, action);
    more.appendChild(body);
    panel.appendChild(more);
  }
  if (!model.actions.length) panel.appendChild(node(doc, 'p', 'riw-empty', '지금 제안할 다음 확인이 없습니다.'));
  return panel;
}

function renderWorkspace(doc, root, model, state, notice) {
  clear(root);
  root.classList.add('riw');
  root.dataset.state = notice ? notice.tone : model.state;
  const head = node(doc, 'header', 'riw-head');
  const title = node(doc, 'div');
  title.appendChild(node(doc, 'h1', 'riw-title', 'R&D Investigation'));
  title.appendChild(node(doc, 'p', 'riw-headline', model.headline || '마킹한 대상의 실제 차이와 다음 확인을 봅니다.'));
  head.appendChild(title);
  head.appendChild(renderCoverage(doc, model));
  root.appendChild(head);
  if (notice) root.appendChild(node(doc, `div`, `riw-notice riw-notice--${notice.tone}`, notice.message));
  if (notice && (notice.tone === 'loading' || notice.tone === 'error')) return;

  root.appendChild(renderMaps(doc, model, state));
  if (model.groups.length) root.appendChild(renderGroupComparison(doc, model));

  const lower = node(doc, 'div', 'riw-lower');
  lower.appendChild(renderCandidates(doc, model, state));
  lower.appendChild(renderActions(doc, model));
  root.appendChild(lower);
  const upper = node(doc, 'div', 'riw-upper');
  upper.appendChild(renderComponentList(doc, model, state));
  upper.appendChild(renderProcess(doc, model, state));
  const evidence = node(doc, 'details', 'riw-evidence');
  evidence.appendChild(node(doc, 'summary', 'riw-evidence__summary',
    `Evidence Details · 구성 ${model.components.length} · 차이 ${model.compositionSummary.differentCount}`));
  const evidenceBody = node(doc, 'div', 'riw-evidence__body');
  evidenceBody.appendChild(upper);
  evidence.appendChild(evidenceBody);
  root.appendChild(evidence);
}

function emptyModel() {
  return normaliseInvestigationPayload({ state: 'idle', coverage: {}, components: [], maps: [], candidates: [], actions: [] });
}

/**
 * Initialise a reusable workspace.
 *
 * @returns {{ updateSelection(selection): Promise<void>, destroy(): void,
 *             getState(): object, render(payload): void }}
 */
export function initInvestigationWorkspace(options = {}) {
  const root = options.root || options.mount;
  if (!root || !root.ownerDocument) throw new TypeError('R&D 조사 화면을 붙일 DOM root가 필요합니다.');
  const adapter = options.adapter || {};
  if (typeof adapter.loadWorkspace !== 'function') throw new TypeError('adapter.loadWorkspace가 필요합니다.');
  const doc = root.ownerDocument;
  const state = {
    destroyed: false,
    requestId: 0,
    controller: null,
    selection: options.initialSelection || null,
    sortBy: 'role',
    componentId: '',
    mapId: '',
    layers: new Set(WORKSPACE_LAYER_ORDER),
    model: emptyModel(),
  };

  const redraw = (notice = null) => {
    if (!state.destroyed) renderWorkspace(doc, root, state.model, state, notice);
  };

  const onClick = async (event) => {
    const target = event.target && typeof event.target.closest === 'function' ? event.target : null;
    if (!target) return;
    const comparisonTarget = target.closest('[data-comparison-id]');
    if (comparisonTarget && root.contains(comparisonTarget)) {
      const category = comparisonTarget.dataset.comparisonCategory;
      const comparison = state.model.comparisons[category]?.find(
        (item) => item.id === comparisonTarget.dataset.comparisonId);
      if (comparison && typeof options.onComparisonMark === 'function') {
        options.onComparisonMark({ ...comparison, category });
      }
      return;
    }
    const mapCell = target.closest('[data-map-cell]');
    if (mapCell && root.contains(mapCell)) {
      state.mapId = mapCell.dataset.mapId || state.mapId;
      const mark = {
        kind: 'map_die',
        mapId: text(mapCell.dataset.frameMapId || state.mapId),
        table: text(mapCell.dataset.frameTable),
        stage: text(mapCell.dataset.frameStage),
        startX: Number(mapCell.dataset.frameStartX),
        startY: Number(mapCell.dataset.frameStartY),
        yInvert: mapCell.dataset.frameYInvert === 'true',
        componentId: state.componentId,
        layer: mapCell.dataset.layer,
        x: Number(mapCell.dataset.x),
        y: Number(mapCell.dataset.y),
        materialId: text(mapCell.dataset.materialId),
        markKey: text(mapCell.dataset.identityMarkKey),
        wafer: text(mapCell.dataset.identityWafer),
        bondingLeg: text(mapCell.dataset.identityBondingLeg),
      };
      if (typeof options.onSpatialMark === 'function') options.onSpatialMark(mark);
      redraw();
      return;
    }
    const sort = target.closest('[data-sort]');
    if (sort && root.contains(sort)) {
      state.sortBy = sort.dataset.sort;
      redraw();
      return;
    }
    const component = target.closest('[data-component-id]');
    if (component && root.contains(component)) {
      state.componentId = component.dataset.componentId;
      state.mapId = '';
      redraw();
      if (typeof options.onComponentChange === 'function') options.onComponentChange(state.componentId);
      return;
    }
    const mapTarget = target.closest('[data-map-id]');
    if (mapTarget && root.contains(mapTarget)) {
      const requestedComponent = mapTarget.dataset.componentId;
      if (requestedComponent) state.componentId = requestedComponent;
      state.mapId = mapTarget.dataset.mapId;
      redraw();
      if (typeof options.onMapDrilldown === 'function') options.onMapDrilldown(state.mapId, state.componentId);
      return;
    }
    const actionTarget = target.closest('[data-action-id]');
    if (actionTarget && root.contains(actionTarget)) {
      const action = state.model.actions.find((item) => item.id === actionTarget.dataset.actionId);
      if (!action) return;
      if (typeof options.onAction === 'function') options.onAction(action, state.selection);
      else if (typeof adapter.executeAction === 'function') await adapter.executeAction(action, { selection: state.selection });
    }
  };

  const onChange = (event) => {
    const input = event.target;
    if (!input || !input.dataset || !input.dataset.layer) return;
    if (input.checked) state.layers.add(input.dataset.layer);
    else state.layers.delete(input.dataset.layer);
    redraw();
  };

  root.addEventListener('click', onClick);
  root.addEventListener('change', onChange);

  const api = {
    async updateSelection(selection) {
      if (state.destroyed) return;
      state.selection = selection;
      state.requestId += 1;
      const requestId = state.requestId;
      if (state.controller) state.controller.abort();
      state.controller = new AbortController();
      redraw({ tone: 'loading', message: '조사 내용을 불러오는 중입니다.' });
      try {
        const payload = await adapter.loadWorkspace({ selection, signal: state.controller.signal });
        if (state.destroyed || requestId !== state.requestId) return;
        state.model = normaliseInvestigationPayload(payload);
        if (!state.model.components.some((item) => item.id === state.componentId)) {
          state.componentId = state.model.components[0] ? state.model.components[0].id : '';
        }
        if (!state.model.maps.some((item) => item.id === state.mapId)) state.mapId = '';
        redraw();
      } catch (error) {
        if (state.destroyed || requestId !== state.requestId || (error && error.name === 'AbortError')) return;
        redraw({ tone: 'error', message: text(error && error.message, '조사 내용을 불러오지 못했습니다.') });
      }
    },
    render(payload) {
      state.model = normaliseInvestigationPayload(payload);
      if (!state.model.components.some((item) => item.id === state.componentId)) {
        state.componentId = state.model.components[0] ? state.model.components[0].id : '';
      }
      redraw();
    },
    getState() {
      return {
        selection: state.selection,
        sortBy: state.sortBy,
        componentId: state.componentId,
        mapId: state.mapId,
        layers: [...state.layers],
      };
    },
    destroy() {
      state.destroyed = true;
      state.requestId += 1;
      if (state.controller) state.controller.abort();
      root.removeEventListener('click', onClick);
      root.removeEventListener('change', onChange);
      clear(root);
      root.classList.remove('riw');
      delete root.dataset.state;
    },
  };

  redraw();
  if (options.initialSelection !== undefined) void api.updateSelection(options.initialSelection);
  return api;
}
