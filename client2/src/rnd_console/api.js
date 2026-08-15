const DEFAULT_BASE = globalThis.location?.port === '5173'
  ? 'http://127.0.0.1:8080/api/ledger'
  : '/api/ledger';

export class LedgerApiError extends Error {
  constructor(message, { status = 0, reason = 'unavailable', detail = null } = {}) {
    super(message);
    this.name = 'LedgerApiError';
    this.status = status;
    this.reason = reason;
    this.detail = detail;
  }
}

export class StaleResponseError extends Error {
  constructor() { super('낡은 응답은 폐기되었습니다.'); this.name = 'StaleResponseError'; }
}

function linkedController(externalSignal) {
  const controller = new AbortController();
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort(externalSignal.reason);
    else externalSignal.addEventListener('abort', () => controller.abort(externalSignal.reason), { once: true });
  }
  return controller;
}

async function responseJson(response) {
  let body = null;
  try { body = await response.json(); } catch { /* response without JSON */ }
  if (!response.ok) {
    const detail = body && (body.detail || body);
    throw new LedgerApiError(
      (detail && detail.message) || `원장 API 응답 실패 (${response.status})`,
      { status: response.status, reason: (detail && detail.reason) || 'unavailable', detail },
    );
  }
  return body || {};
}

function query(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value));
  });
  const rendered = search.toString();
  return rendered ? `?${rendered}` : '';
}

function requestLane(fetchImpl, base, route) {
  let sequence = 0;
  let active = null;
  return {
    async run(params, { signal } = {}) {
      sequence += 1;
      const mine = sequence;
      if (active) active.abort();
      active = linkedController(signal);
      const response = await fetchImpl(`${base}${route}${query(params)}`, {
        method: 'GET', headers: { Accept: 'application/json' }, signal: active.signal,
      });
      const body = await responseJson(response);
      if (mine !== sequence) throw new StaleResponseError();
      return body;
    },
    abort() { sequence += 1; if (active) active.abort(); active = null; },
  };
}

function jsonRequestLane(fetchImpl, base, route) {
  let sequence = 0;
  let active = null;
  return {
    async run(body, { signal } = {}) {
      sequence += 1;
      const mine = sequence;
      if (active) active.abort();
      active = linkedController(signal);
      const response = await fetchImpl(`${base}${route}`, {
        method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(body), signal: active.signal,
      });
      const payload = await responseJson(response);
      if (mine !== sequence) throw new StaleResponseError();
      return payload;
    },
    abort() { sequence += 1; if (active) active.abort(); active = null; },
  };
}

function multiRequestLane(fetchImpl, base, route) {
  let sequence = 0;
  let controllers = [];
  return {
    async run(values, common = {}, { signal } = {}) {
      sequence += 1;
      const mine = sequence;
      controllers.forEach((controller) => controller.abort());
      controllers = values.map(() => linkedController(signal));
      const bodies = await Promise.all(values.map((value, index) => fetchImpl(
        `${base}${route}${query({ ...common, final_chip_id: value })}`,
        { method: 'GET', headers: { Accept: 'application/json' }, signal: controllers[index].signal },
      ).then(responseJson)));
      if (mine !== sequence) throw new StaleResponseError();
      return bodies;
    },
    abort() { sequence += 1; controllers.forEach((controller) => controller.abort()); controllers = []; },
  };
}

export function createLedgerApi({ fetchImpl = globalThis.fetch, base = DEFAULT_BASE } = {}) {
  if (typeof fetchImpl !== 'function') throw new TypeError('fetch 구현이 필요합니다.');
  const trends = requestLane(fetchImpl, base, '/trends');
  const compositions = multiRequestLane(fetchImpl, base, '/composition');
  const resolver = jsonRequestLane(fetchImpl, base, '/selection/resolve');
  return Object.freeze({
    loadTrends(params = {}, options = {}) { return trends.run(params, options); },
    async resolveSelection(selection, { window = '365d', findingKind, signal } = {}) {
      if (!(selection || []).length) return normaliseSelectionResolution({ state: 'empty', selections: [], resolved_final_chip_ids: [] });
      const body = { selection, window };
      if (findingKind) body.finding_kind = findingKind;
      return normaliseSelectionResolution(await resolver.run(body, { signal }));
    },
    async resolveCompositionScope(markKeys, options = {}) {
      return this.resolveSelection((markKeys || []).map((mark_key) => ({
        kind: 'wafer', identity: { type: 'WaferLeg', keys: {}, mark_key }, operation: 'add', group: 'A',
      })), options);
    },
    loadCompositions(finalChipIds, params = {}, options = {}) {
      const ids = [...new Set((finalChipIds || []).map(String).filter(Boolean))];
      return ids.length ? compositions.run(ids, params, options) : Promise.resolve([]);
    },
    dispose() { trends.abort(); compositions.abort(); resolver.abort(); },
  });
}

export function markingSnapshotToSelection(snapshot, identities = new Map()) {
  const output = [];
  for (const group of snapshot?.groups || []) {
    if (group.role === 'overlay') continue;
    for (const mark of group.marks || []) {
      if (mark.kind === 'entity_set') {
        for (const id of mark.selector?.ids || []) output.push({
          kind: 'wafer', identity: identities.get(id) || { type: mark.subjectType || 'WaferLeg', keys: {}, mark_key: id },
          operation: 'add', group: group.id, group_id: group.id,
          finding_kind: mark.selector.findingKind || undefined,
          // One visual entity_set expands to many atomic resolver selections.  The
          // backend uses mark_id for idempotent selection provenance, so sharing
          // the container id would collapse the whole population to one subject.
          mark_id: `${mark.id}#entity:${encodeURIComponent(id)}`,
          origin: mark.origin, schema_version: snapshot.schemaVersion,
        });
      } else if (mark.kind === 'time_range') {
        output.push({ kind: 'time_range', interval: { from: mark.selector.from, to: mark.selector.to, timezone: mark.selector.timezone }, operation: 'intersect', group: group.id, group_id: group.id, finding_kind: mark.selector.findingKind || undefined, mark_id: mark.id, origin: mark.origin, schema_version: snapshot.schemaVersion });
      } else if (mark.kind === 'map_cells') {
        for (const cell of mark.selector?.cells || []) output.push({
          kind: 'map_die', map_id: mark.selector.frame.mapId, x: cell.x, y: cell.y,
          material_id: cell.materialId || undefined,
          table: mark.selector.frame.table, stage: mark.selector.frame.stage,
          frame: {
            table: mark.selector.frame.table, map_id: mark.selector.frame.mapId, stage: mark.selector.frame.stage,
            coordinate_system: {
              start_x: mark.selector.frame.startX, start_y: mark.selector.frame.startY,
              y_invert: mark.selector.frame.yInvert,
            },
          },
          operation: 'add', group: group.id,
          group_id: group.id, mark_id: mark.id, origin: mark.origin, schema_version: snapshot.schemaVersion,
          identity: (mark.selector.ids || []).map((id) => identities.get(id)).find(Boolean),
        });
      }
    }
  }
  return output;
}

export function normaliseSelectionResolution(raw = {}) {
  const selections = Array.isArray(raw.selections) ? raw.selections : [];
  const chipIds = raw.resolved_final_chip_ids || selections.flatMap((item) => item.final_chip_ids || []);
  const waferMarks = selections.flatMap((item) => item.wafer_mark_keys || []);
  const comparison = raw.comparison || {};
  const facets = comparison.facets || {};
  const palette = { A: '#d04a52', B: '#3259d9' };
  const groups = (comparison.groups || []).map((group) => ({
    id: String(group.group_id || group.id),
    label: group.label || (group.group_id === 'A' ? 'Defect' : group.group_id === 'B' ? 'Reference' : String(group.group_id || group.id)),
    color: group.color || palette[group.group_id] || '#667085',
    // The investigation population is WaferLeg, not the many Core components
    // carried by each unit.  Keep component_count as evidence in the raw payload.
    count: Number(group.analysis_unit_count ?? group.count ?? group.component_count ?? 0),
  }));
  const facetLabel = (facet, category) => {
    const signature = facet.signature || {};
    if (category === 'measured_as' && facet.state === 'absent') return '계측 원장 미연결';
    if (category === 'processed_with') {
      const recipe = signature.recipe;
      const recipeName = recipe && typeof recipe === 'object'
        ? (recipe.name || recipe.id || recipe.recipe_id || '') : recipe;
      return [signature.step, recipeName ? `RCP ${recipeName}` : '']
        .filter(Boolean).join(' · ') || facet.label || facet.facet_id || '공정 항목';
    }
    if (category === 'measured_as') {
      return [signature.metric, signature.unit ? `[${signature.unit}]` : '', signature.method]
        .filter(Boolean).join(' · ') || facet.label || facet.facet_id || '계측 항목';
    }
    return [signature.step, signature.parameter, signature.field, signature.value]
      .filter((value) => value !== undefined && value !== null && value !== '').join(' · ')
      || facet.label || facet.facet_id || '비교 항목';
  };
  const adaptFacet = (facet, category) => {
    const waferMarkKeys = [...new Set((facet.wafer_mark_keys || facet.waferMarkKeys || facet.ids || []).map(String).filter(Boolean))];
    const evidenceIds = [...new Set((facet.evidence_ids || facet.evidenceIds || []).map(String).filter(Boolean))];
    return {
      id: String(facet.facet_id || facet.id || `${category}:status`), label: facetLabel(facet, category), state: facet.state || 'recorded',
      predicate: facet.predicate || category,
      signature: facet.signature || {},
      ids: waferMarkKeys, waferMarkKeys, wafer_mark_keys: waferMarkKeys,
      evidenceIds, evidence_ids: evidenceIds,
      delta: Number.isFinite(Number(facet.delta)) ? Number(facet.delta) : null,
      sentence: facet.sentence || facet.detail || (category === 'measured_as' && facet.state === 'absent'
        ? '계측 기록이 연결되지 않아 비교할 수 없습니다.' : ''),
      surprise: typeof facet.surprise === 'number' ? { score: facet.surprise } : (facet.surprise || {}),
      groups: (facet.groups || []).map((value) => {
        const baseValue = Number.isFinite(Number(value.frequency))
          ? `${(Number(value.frequency) * 100).toFixed(1)}%` : String(value.value ?? '');
        const stateCounts = value.state_counts || value.stateCounts || {};
        const stateLabels = { missing: '누락', not_performed: '미실시', unknown: '미상' };
        const absence = Object.entries(stateLabels)
          .filter(([state]) => Number(stateCounts[state] || 0) > 0)
          .map(([state, label]) => `${label} ${Number(stateCounts[state])}`);
        return {
          groupId: String(value.group_id || value.groupId),
          value: [baseValue, ...absence].filter(Boolean).join(' · '),
          count: Number(value.count ?? 0), total: Number(value.of_components ?? value.total ?? 0),
          state: value.state || 'recorded', stateCounts,
          waferMarkKeys: [...new Set((value.wafer_mark_keys || value.waferMarkKeys || []).map(String).filter(Boolean))],
          evidenceIds: [...new Set((value.evidence_ids || value.evidenceIds || []).map(String).filter(Boolean))],
        };
      }),
    };
  };
  const adaptMap = (source = {}) => {
    const frame = source.frame || {};
    const physicalMapId = frame.mapId || frame.map_id || source.map_id || source.mapId || source.id;
    const table = frame.table || source.table || source.source_table || '';
    const stage = frame.stage || source.stage || '';
    return {
      ...source,
      id: source.id || `map:${table}:${physicalMapId}`,
      map_id: source.map_id || physicalMapId,
      table,
      stage,
      frame: { ...frame, table, mapId: String(physicalMapId || ''), stage },
    };
  };
  const adaptAction = (source = {}, index) => {
    const parameters = source.parameters || {};
    const parameter = [parameters.step, parameters.parameter || parameters.predicate]
      .filter(Boolean).join(' ');
    const value = parameters.value === undefined || parameters.value === null ? '' : `=${parameters.value}`;
    const isDoe = source.kind === 'doe';
    const sentence = isDoe
      ? `${parameter}${value} · 가설 ${Number(source.hypotheses_split || 0)}개 분리`
      : `${parameter || 'processed_with'} · 결측 ${Number(source.missing_resolved || 0)}개 확보`;
    return {
      ...source,
      id: source.id || `resolver-action-${source.kind || 'unknown'}-${index + 1}`,
      rank: Number(source.rank || index + 1),
      label: source.label || (isDoe ? '물리 경로 분리 DOE' : source.kind === 'collect_missing' ? '결측 상태 확보' : '다음 확인'),
      sentence: source.sentence || sentence.slice(0, 40),
    };
  };
  const sequenceLabels = {
    order_change: '공정 순서 변경', repeat_change: '공정 반복 변경', insert: '공정 추가',
    delete: '공정 누락', substitution: '공정 대체', schema_branch: '공정 경로 분기',
    ambiguous_order: '순서 판단 어려움', record_absent: '공정 기록 없음',
  };
  const tokenText = (tokens) => (tokens || []).map((token) => token.step || token.step_family || '?').join(' → ');
  const sequence = comparison.sequence && typeof comparison.sequence === 'object' ? comparison.sequence : {};
  const sequenceRows = (sequence.differences || []).map((difference, index) => {
    const support = difference.support || {};
    const isMissing = difference.kind === 'record_absent' || difference.state === 'missing';
    const groupIds = [...new Set([
      ...groups.map((group) => group.id),
      ...Object.keys(isMissing ? support : support.left || {}),
      ...Object.keys(isMissing ? {} : support.right || {}),
    ])];
    return {
      id: `sequence:${difference.kind || 'unknown'}:${index + 1}`,
      label: sequenceLabels[difference.kind] || '공정 순서 차이',
      predicate: 'process_sequence',
      signature: { kind: difference.kind, left: difference.left || [], right: difference.right || [] },
      waferMarkKeys: [...new Set((difference.wafer_mark_keys || []).map(String).filter(Boolean))],
      evidenceIds: [...new Set((difference.evidence_ids || []).map(String).filter(Boolean))],
      state: isMissing ? 'missing' : difference.kind === 'ambiguous_order' ? 'unknown' : 'recorded',
      delta: null,
      sentence: isMissing ? '공정 기록이 없어 순서를 비교할 수 없습니다.'
        : [tokenText(difference.left), tokenText(difference.right)].filter(Boolean).join(' / '),
      surprise: {},
      groups: groupIds.map((groupId) => {
        const left = Number(support.left?.[groupId] || 0);
        const right = Number(support.right?.[groupId] || 0);
        const count = isMissing ? Number(support[groupId] || 0) : left + right;
        const total = groups.find((group) => group.id === groupId)?.count || 0;
        return {
          groupId, count, total, state: isMissing ? 'missing' : 'recorded',
          value: isMissing ? `${count}개 기록 없음` : `기준 ${left} · 차이 ${right}`,
        };
      }),
      evidence_ids: Array.isArray(difference.evidence_ids) ? difference.evidence_ids : [],
      sequence_kind: difference.kind,
    };
  });
  const populationByChip = {};
  selections.forEach((item) => (item.final_chip_ids || []).forEach((chipId) => {
    const group = item.input?.group;
    populationByChip[chipId] = group === 'A' ? 'defect' : group === 'B' ? 'reference' : 'unspecified';
  }));
  const adaptedProcess = Array.isArray(facets.process)
    ? facets.process.map((facet) => adaptFacet(facet, 'processed_with')) : [];
  const surpriseFacetId = comparison.surprise?.facet_id;
  if (surpriseFacetId) adaptedProcess.sort((left, right) =>
    Number(right.id === surpriseFacetId) - Number(left.id === surpriseFacetId));
  return {
    ...raw,
    state: raw.state || (chipIds.length ? 'ready' : 'no_live_bridge'),
    reason: raw.reason || selections.find((item) => item.reason)?.reason || '',
    final_chip_ids: [...new Set(chipIds.map(String).filter(Boolean))],
    wafer_mark_keys: [...new Set(waferMarks.map(String).filter(Boolean))],
    map_focus: selections.map((item) => item.map_focus).filter(Boolean),
    population_by_chip: populationByChip,
    maps: Array.isArray(raw.maps) ? raw.maps.map(adaptMap) : [],
    groups,
    comparisons: {
      process: [...adaptedProcess, ...sequenceRows],
      measurement: Array.isArray(facets.measurement) ? facets.measurement.map((facet) => adaptFacet(facet, 'measured_as')) : [],
      context: Array.isArray(facets.context) ? facets.context.map((facet) => adaptFacet(facet, 'context')) : [],
    },
    actions: Array.isArray(comparison.actions) ? comparison.actions.map(adaptAction) : [],
    surprise: typeof comparison.surprise === 'number' ? { score: comparison.surprise } : (comparison.surprise || {}),
    sequence,
  };
}

const number = (value) => Number.isFinite(Number(value)) ? Number(value) : null;
const identityFields = (identity = {}) => {
  const keys = identity.keys || {};
  const wafer = keys.wafer == null ? '' : String(keys.wafer);
  const bondingLeg = keys.bonding_leg == null ? '' : String(keys.bonding_leg);
  return {
    identity: structuredClone(identity), wafer, bondingLeg,
    subjectLabel: bondingLeg ? `WF ${wafer} · LEG ${bondingLeg}` : `WF ${wafer}`,
  };
};

export function normaliseTrendResponse(raw) {
  const selectableDefinitions = raw.selectable_finding_kinds || raw.finding_kinds || [];
  const appliedIds = new Set((raw.applied_kinds || []).map((item) => String(item?.id || item)));
  const activeDefinitions = appliedIds.size
    ? selectableDefinitions.filter((definition) => appliedIds.has(String(definition.id)))
    : (raw.finding_kinds || selectableDefinitions);
  const definitions = new Map();
  const traceDimensions = (raw.trace_dimensions || []).map((dimension, index) => ({
    id: String(dimension.id || dimension.key || dimension.dimension || `trace-${index + 1}`),
    sourceKey: String(dimension.source_key || dimension.key || dimension.id || '').replace(/_trace$/, ''),
    label: dimension.label || dimension.name || dimension.id || `Trace ${index + 1}`,
    ontologyPath: Array.isArray(dimension.ontology_path) ? dimension.ontology_path : [],
    states: Array.isArray(dimension.states) ? dimension.states : [],
  }));
  const traceCell = (row, dimension) => {
    const traceability = row.traceability || {};
    const source = Array.isArray(traceability)
      ? traceability.find((item) => [dimension.id, dimension.sourceKey].includes(String(item.dimension_id || item.id || item.key)))
      : traceability[dimension.id] || traceability[dimension.sourceKey];
    if (!source) return { state: 'absent', count: 0 };
    if (typeof source === 'string') return { state: source, count: 0 };
    return { ...source, state: source.state || 'absent', count: number(source.count) ?? 0 };
  };
  const traceDisplay = (value) => {
    const labels = { ready: '연결', partial: '일부', absent: '없음' };
    const label = labels[value?.state] || '미상';
    return value?.count ? `${label} · ${value.count}` : label;
  };
  for (const kind of activeDefinitions) {
    for (const series of kind.series || []) {
      definitions.set(series.id, {
        title: series.subtype ? `${kind.label} · ${series.label}` : `${kind.label} · 전체`,
        label: series.subtype ? `${kind.label} ${series.label}` : `${kind.label} 전체`,
      });
    }
  }
  const charts = (raw.series || []).map((series) => ({
    id: series.id,
    title: definitions.get(series.id)?.title || series.id,
    xLabel: '날짜 - BASE WAFER-ID',
    unit: '건',
    points: (series.points || []).map((point) => {
      const subject = identityFields(point.identity);
      return {
        waferId: point.identity?.mark_key,
        ...subject,
        x: point.occurred_at,
        xTickLabel: `${new Date(point.occurred_at).toLocaleDateString('ko-KR')} - ${subject.wafer}${subject.bondingLeg ? ` / ${subject.bondingLeg}` : ''}`,
        ariaLabel: `${subject.subjectLabel}, ${point.occurred_at}`,
        y: number(point.value?.found_chip_count) ?? number(point.value?.event_count) ?? 0,
      };
    }),
  }));
  const seriesIds = [...new Set([
    ...definitions.keys(),
    ...(raw.table?.rows || []).flatMap((row) => (row.metrics || []).map((metric) => metric.series_id)
      .filter((seriesId) => !definitions.size || definitions.has(seriesId))),
  ])];
  const rows = (raw.table?.rows || []).map((row) => {
    const subject = identityFields(row.identity);
    const result = {
      waferId: row.identity?.mark_key,
      ...subject,
      occurredAt: row.occurred_at,
      traceability: structuredClone(row.traceability || {}),
    };
    for (const dimension of traceDimensions) result[`trace:${dimension.id}`] = traceCell(row, dimension);
    for (const metric of row.metrics || []) result[metric.series_id] = number(metric.found_chip_count) ?? number(metric.event_count);
    return result;
  });
  return {
    state: raw.state || 'unavailable',
    charts,
    rows,
    columns: [
      { key: 'wafer', label: 'BASE WAFER-ID', width: 148 },
      { key: 'bondingLeg', label: 'BONDING LEG', width: 132 },
      { key: 'occurredAt', label: '관측 시각', width: 154, format: (value) => value ? new Date(value).toLocaleString('ko-KR') : '기록 없음' },
      ...traceDimensions.map((dimension) => ({ key: `trace:${dimension.id}`, label: dimension.label, width: 112, kind: 'trace', ontologyPath: dimension.ontologyPath, states: dimension.states, format: traceDisplay })),
      ...seriesIds.map((id) => ({ key: id, label: definitions.get(id)?.label || id, width: 112 })),
    ],
    cursor: raw.table?.next_cursor || null,
    truncated: Boolean(raw.table?.truncated),
    totalRows: rows.length + (raw.table?.truncated ? 1 : 0),
    selectableFindingKinds: selectableDefinitions,
    appliedKinds: appliedIds.size ? [...appliedIds] : activeDefinitions.map((definition) => String(definition.id)),
    raw,
  };
}

function place(raw = {}) {
  const keys = raw.keys || {};
  return {
    stage: raw.type || '',
    lot: keys.lot || keys.core_lot || keys.dt_lot || keys.bond_lot || '',
    slot: keys.slot || keys.core_slot || keys.dt_slot || keys.bond_slot || '',
    position: raw.position == null ? '' : (typeof raw.position === 'object' ? JSON.stringify(raw.position) : String(raw.position)),
  };
}

function chipOf(payload, fallback) {
  return payload?.final_chip?.keys?.final_chip_id || fallback;
}

function processSteps(component) {
  return new Set(processEvents(component).map((evidence) => evidence?.step).filter(Boolean));
}

function processEvents(component) {
  const upstream = component?.upstream_process || {};
  return upstream.events?.length ? upstream.events : (upstream.evidence_ids || []);
}

function processParameter(component, step, key) {
  const event = processEvents(component).find((candidate) => candidate?.step === step);
  const actual = event?.knobs?.actual;
  return actual && Object.prototype.hasOwnProperty.call(actual, key) ? actual[key] : null;
}

function worstResolution(components) {
  const order = ['resolved', 'candidate', 'contested', 'unresolvable'];
  return components.reduce((worst, component) => {
    const state = component?.resolution_state || 'unresolvable';
    return order.indexOf(state) > order.indexOf(worst) ? state : worst;
  }, 'resolved');
}

export function compositionToWorkspace(payloads, {
  selection = [], finalChipIds = [], populationByChip = {},
} = {}) {
  if (!finalChipIds.length) {
    return {
      state: selection.length ? 'no_live_bridge' : 'idle',
      headline: selection.length
        ? 'Trend에서 고른 비교 모집단은 유지됐지만, 웨이퍼를 최종 CHIP 구성으로 잇는 라이브 근거가 없습니다.'
        : 'Trend 마킹은 비교 모집단을 고릅니다. 구성 추적은 위에서 최종 CHIP ID를 직접 지정합니다.',
      subjects: selection.map((id) => ({ id, label: id })), components: [], maps: [], candidates: [], actions: [],
      coverage: { attributed: 0, total: selection.length },
      notes: selection.length ? ['no_live_bridge'] : [],
    };
  }
  const subjects = [];
  let totalEvents = 0;
  const chipRecords = [];
  payloads.forEach((payload, payloadIndex) => {
    const chipId = chipOf(payload, finalChipIds[payloadIndex]);
    const population = populationByChip[chipId] || 'unspecified';
    subjects.push({ id: `final_chip:${chipId}`, label: `${chipId} · ${population === 'defect' ? '불량' : population === 'reference' ? '정상 비교' : '집단 역할 미지정'}`, population });
    chipRecords.push({ chipId, population, payload });
  });

  // Compare like roles/layers across every CHIP. A role group stays one component in the
  // workspace, while every subject value and every transfer event remains individually named.
  const roleGroups = new Map();
  for (const record of chipRecords) {
    for (const component of record.payload.components || []) {
      const role = component.core?.role || `bond_layer_${component.bonding?.layer ?? 'unknown'}`;
      if (!roleGroups.has(role)) roleGroups.set(role, new Map());
      roleGroups.get(role).set(record.chipId, component);
      totalEvents += (component.transfer_events || []).length;
    }
  }

  const components = [];
  const compositionDifferences = [];
  let unknownClaims = 0;
  for (const [role, byChip] of [...roleGroups].sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))) {
    const present = [...byChip.values()];
    const id = `role:${role}`;
    const allSteps = new Set(present.flatMap((component) => [...processSteps(component)]));
    const commonSteps = [...allSteps].filter((step) => finalChipIds.every((chipId) => processSteps(byChip.get(chipId)).has(step)));
    const differences = [];
    const addDimension = (key, label, getter) => {
      const values = finalChipIds.map((chipId) => {
        const component = byChip.get(chipId);
        const value = component ? getter(component) : null;
        return { subject_id: `final_chip:${chipId}`, state: value == null ? 'unknown' : 'recorded', text: value == null ? '계약상 확인 불가' : String(value), reason: value == null ? 'claim_absent_or_component_missing' : '' };
      });
      if (new Set(values.map((value) => `${value.state}:${value.text}`)).size > 1) {
        differences.push({ id: `${id}|${key}`, label, state: values.some((value) => value.state === 'unknown') ? 'unknown' : 'recorded', values,
          gates: [{ label: 'Statistical · 집단별 빈도 대조', verdict: 'unknown' }, { label: 'Upstream · 원장 구성 근거', verdict: 'pass' }, { label: 'Mechanism · 기전 연결 계약 부재', verdict: 'unknown' }] });
      }
    };
    addDimension('core-type', 'Core 종류', (component) => component.core?.type);
    addDimension('core-branch', 'Core 공정 분기', (component) => component.core?.branch);
    addDimension('bond-prep-power', 'BOND_PREP plasma power', (component) => processParameter(component, 'BOND_PREP', 'plasma_power_W'));
    addDimension('dt-count', '거쳐 간 DT 수', (component) => component.dt_collections?.length);
    addDimension('transfer-count', 'TRANSFER 횟수', (component) => component.transfer_events?.length);
    for (const step of [...allSteps].sort()) {
      const values = finalChipIds.map((chipId) => {
        const recorded = processSteps(byChip.get(chipId)).has(step);
        if (!recorded) unknownClaims += 1;
        return { subject_id: `final_chip:${chipId}`, state: recorded ? 'recorded' : 'unknown', text: recorded ? '기록 있음' : '기록 없음 · 누락/미실시/미상 미분류', reason: recorded ? '' : 'absence_semantics_not_in_composition_contract' };
      });
      if (values.some((value) => value.state !== 'recorded')) differences.push({
        id: `${id}|step:${step}`, label: step, state: 'unknown',
        sentence: '기록 부재만으로 미실시라고 단정하지 않습니다.', values,
        gates: [{ label: 'Statistical · 집단별 발생 빈도', verdict: 'pass' }, { label: 'Upstream · Core 공정 기록', verdict: 'pass' }, { label: 'Mechanism · 공정 파라미터 계약 부재', verdict: 'unknown' }],
      });
    }
    const representative = present[0] || {};
    components.push({
      id, label: role, core_type: new Set(present.map((component) => component.core?.type).filter(Boolean)).size === 1 ? representative.core?.type : '여러 종류',
      role, position: role, mapping_state: worstResolution(present),
      composition_state: byChip.size === finalChipIds.length ? 'recorded' : 'unknown',
      process_segments: [{ id: `${id}|process`, label: 'Core Process Comparison', same_count: commonSteps.length, total_count: allSteps.size, missing_count: differences.filter((item) => item.state === 'unknown').length, differences }],
      lineage: [], map_ids: [],
    });
    if (byChip.size !== finalChipIds.length) compositionDifferences.push({
      id: `${id}|presence`, label: `${role} 구성`, state: 'unknown', component_ids: [id],
      sentence: `${finalChipIds.length - byChip.size}개 CHIP에서 해당 역할의 구성 근거가 없습니다.`,
    });
  }

  // Population-level process frequencies turn the expanded role rows into a short cause list.
  const frequency = new Map();
  const combinations = new Map();
  for (const record of chipRecords) {
    for (const component of record.payload.components || []) {
      for (const step of processSteps(component)) {
        const row = frequency.get(step) || { defect: 0, reference: 0, unspecified: 0 };
        row[record.population] += 1;
        frequency.set(step, row);
      }
      const signal = [component.core?.type || '미상', component.core?.branch || '미상',
        processParameter(component, 'BOND_PREP', 'plasma_power_W') ?? '파라미터 없음',
        (component.dt_collections || []).length > 1 ? '다중 DT' : '단일 DT'].join(' · ');
      const combo = combinations.get(signal) || { defect: 0, reference: 0, unspecified: 0 };
      combo[record.population] += 1;
      combinations.set(signal, combo);
    }
  }
  const combinationCandidates = [...combinations.entries()].map(([signal, counts]) => ({
    signal, ...counts, delta: counts.defect - counts.reference,
  })).filter((row) => row.defect !== row.reference).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 3).map((row, index) => ({
    id: `population-combination:${row.signal}`, rank: index + 1,
    label: row.signal,
    sentence: row.reference === 0
      ? `불량 ${row.defect}개에서 공통이고 정상 비교에는 없습니다. 조합 연관 후보이며 인과 확정이 아닙니다.`
      : `불량 ${row.defect}개 · 정상 비교 ${row.reference}개 구성 Core에서 확인됐습니다. 조합 연관 후보이며 인과 확정이 아닙니다.`,
    evidence_count: row.defect + row.reference,
    gates: [{ label: 'Statistical · 조합 빈도 차이', verdict: 'pass' }, { label: 'Upstream · Core 공정·DT 근거 존재', verdict: 'pass' }, { label: 'Mechanism · 기전 모델 미연결', verdict: 'unknown' }],
  }));
  const stepCandidates = [...frequency.entries()].map(([step, counts]) => ({
    step, ...counts, delta: counts.defect - counts.reference,
  })).filter((row) => row.defect !== row.reference).sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, 2).map((row, index) => ({
    id: `population-step:${row.step}`, rank: combinationCandidates.length + index + 1, label: `${row.step} 공정 분포 차이`,
    sentence: `불량 CHIP 구성 Core ${row.defect}개, 정상 비교 Core ${row.reference}개에서 기록됐습니다. 이는 연관 후보이며 인과 확정이 아닙니다.`,
    evidence_count: row.defect + row.reference,
    gates: [{ label: 'Statistical · 기술 빈도 차이', verdict: 'pass' }, { label: 'Upstream · Core 공정 근거 존재', verdict: 'pass' }, { label: 'Mechanism · 파라미터·기전 계약 부재', verdict: 'unknown' }],
  }));
  const candidates = [...combinationCandidates, ...stepCandidates];

  const unresolved = components.filter((component) => component.mapping_state !== 'resolved').length;
  const actions = [];
  if (unknownClaims) actions.push({ id: 'classify-process-absence', rank: 1, kind: 'verify', label: '공정 기록 부재의 의미 확인', sentence: `누락·미실시·아직 모름이 섞인 ${unknownClaims}개 값을 분류하면 집단 차이가 크게 줄어듭니다.`, information_gain: 0.95, hypotheses_split: 3, missing_resolved: unknownClaims, target_count: unknownClaims });
  if (unresolved) actions.push({ id: 'resolve-transfer-address', rank: 2, kind: 'verify', label: 'TRANSFER 주소 후보 확인', sentence: `${unresolved}개 역할 가지의 LOT/SLOT 후보를 확인해 DT 경로를 확정합니다.`, information_gain: 0.82, hypotheses_split: 2, missing_resolved: unresolved, target_count: unresolved });
  const readyCount = payloads.filter((payload) => payload.state === 'ready').length;
  return {
    state: readyCount ? 'ready' : (payloads.some((payload) => payload.state === 'absent') ? 'unavailable' : 'empty'),
    headline: `${finalChipIds.length.toLocaleString('ko-KR')}개 CHIP 비교`,
    subjects,
    coverage: { attributed: readyCount, total: finalChipIds.length },
    composition: {
      same_count: 0,
      different_count: components.length,
      unresolved_count: components.filter((component) => component.mapping_state !== 'resolved').length,
      differences: compositionDifferences, components,
    },
    maps: [], candidates, actions,
    notes: [...(totalEvents ? [] : ['TRANSFER 근거 없음']), 'map_evidence_not_distributed'],
  };
}
