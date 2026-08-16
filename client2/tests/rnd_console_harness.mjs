import assert from 'node:assert/strict';
import fs from 'node:fs';
import { canonicalMark, createMarkingStore, createSelectionStore, deterministicMarkKey, MARKING_SCHEMA_VERSION } from '../src/rnd_console/state.js';
import { createLedgerApi, markingSnapshotToSelection, normaliseSelectionResolution, normaliseTrendResponse, compositionToWorkspace } from '../src/rnd_console/api.js';
import { normaliseInvestigationPayload } from '../src/rnd_console/investigation_workspace.js';

let ran = 0;
const check = (condition, message) => { ran += 1; assert.ok(condition, message); };

const store = createSelectionStore();
let notice = null;
store.subscribe((ids, meta) => { notice = { ids, meta }; });
check(store.replace(['wafer:A', 'wafer:B'], 'chart:void'), 'selection changes');
check(store.get().length === 2, 'selection has no two-subject ceiling');
check(notice.meta.source === 'chart:void', 'selection source preserved');
store.replace(['wafer:A', 'wafer:B'], 'table');
check(store.get().length === 2, 'legacy facade remains compatible');

const marking = createMarkingStore();
const entityMark = canonicalMark({ kind: 'entity_set', groupId: 'A', subjectType: 'Wafer', selector: { ids: ['experiment-unit:v1:B', 'experiment-unit:v1:A'] }, origin: { viewId: 'trend', source: 'chart' } });
marking.apply(entityMark, { mode: 'add', source: 'chart' });
marking.setActiveGroup('B');
marking.apply({ kind: 'time_range', groupId: 'B', subjectType: 'Wafer', selector: { from: '2026-08-01T00:00:00Z', to: '2026-08-15T00:00:00Z', timezone: 'UTC', seriesId: 'void:edge' }, origin: { viewId: 'trend', source: 'brush' } }, { source: 'brush' });
marking.apply({ kind: 'map_cells', groupId: 'B', subjectType: 'Wafer', selector: { frame: { table: 'dt_map', mapId: 'DT:1', stage: 'DT', startX: 1, startY: 1, yInvert: false }, cells: [{ x: 1, y: 1, bondingLeg: 'HBM-B_LOW-P', materialId: 'MAT-7' }], layer: 'supply_material', ids: ['experiment-unit:v1:B'] }, origin: { viewId: 'maps', source: 'die' } }, { source: 'map' });
marking.apply({ kind: 'metric_region', groupId: 'B', subjectType: 'Wafer', selector: { seriesId: 'alpha:edge', metricId: 'found_chip_count', xFrom: '2026-08-01T00:00:00Z', xTo: '2026-08-15T00:00:00Z', yMin: 2, yMax: 8, findingKind: 'alpha', ids: ['wafer:B'] }, origin: { viewId: 'trend', source: 'bbox' } }, { source: 'bbox' });
const markingSnapshot = marking.snapshot();
check(markingSnapshot.schemaVersion === MARKING_SCHEMA_VERSION, 'snapshot carries schema version');
check(markingSnapshot.groups[0].marks[0].selector.ids.join(',') === 'experiment-unit:v1:A,experiment-unit:v1:B', 'opaque aggregate ids canonicalized without decoding');
check(deterministicMarkKey(entityMark) === deterministicMarkKey(canonicalMark(entityMark)), 'mark key is stable');
check(markingSnapshot.groups[1].marks.some((mark) => mark.kind === 'time_range') && markingSnapshot.groups[1].marks.some((mark) => mark.kind === 'map_cells') && markingSnapshot.groups[1].marks.some((mark) => mark.kind === 'metric_region'), 'typed marks coexist in one group');
check(markingSnapshot.groups[1].marks.find((mark) => mark.kind === 'map_cells').selector.cells[0].bondingLeg === 'HBM-B_LOW-P', 'spatial mark keeps the free-string Bonding Leg in its canonical cell key');
check(JSON.parse(JSON.stringify(markingSnapshot)).groups.length === 2, 'snapshot is serializable');
const resolverItems = markingSnapshotToSelection(markingSnapshot, new Map([['experiment-unit:v1:A', { type: 'Wafer', keys: { wafer: 'A' }, context: { role: 'planned_bonding_experiment_unit', bonding_leg: 'L1' }, mark_key: 'experiment-unit:v1:A' }]]));
check(resolverItems.some((item) => item.kind === 'wafer' && item.group === 'A'), 'entity mark adapts to resolver wafer selection');
const atomicPopulation = markingSnapshotToSelection({ schemaVersion: MARKING_SCHEMA_VERSION, groups: [{ id: 'A', role: 'analysis', marks: [{ id: 'population:A', kind: 'entity_set', groupId: 'A', subjectType: 'Wafer', selector: { ids: ['experiment-unit:v1:A', 'experiment-unit:v1:B'], findingKind: 'void' }, origin: { viewId: 'trend', source: 'table' } }] }] }, new Map());
check(atomicPopulation.length === 2 && new Set(atomicPopulation.map((item) => item.mark_id)).size === 2, 'one visual population expands to unique atomic resolver mark ids');
check(resolverItems.some((item) => item.kind === 'time_range' && item.operation === 'intersect'), 'time mark adapts to intersecting interval');
check(resolverItems.some((item) => item.kind === 'map_die' && item.map_id === 'DT:1'), 'map cells adapt to typed die selection');
check(!resolverItems.some((item) => item.kind === 'metric_region'), 'metric region provenance stays in snapshot without duplicating resolver subjects');
assert.throws(() => canonicalMark({ kind: 'metric_region', selector: { seriesId: 'alpha', xFrom: 'bad', xTo: '2026-08-15', yMin: 1, yMax: 2 } }), TypeError);
ran += 1;
const resolverMap = resolverItems.find((item) => item.kind === 'map_die');
check(resolverItems.every((item) => item.mark_id && item.origin?.viewId && item.schema_version === MARKING_SCHEMA_VERSION), 'resolver wire preserves mark provenance and schema');
check(resolverMap.x === 1 && resolverMap.y === 1 && resolverMap.material_id === 'MAT-7', '1-based non-inverted cell coordinates reach resolver unchanged');
check(resolverMap.frame.table === 'dt_map' && resolverMap.frame.map_id === 'DT:1', 'declared map frame reaches resolver');
check(resolverMap.frame.coordinate_system.start_x === 1 && resolverMap.frame.coordinate_system.start_y === 1 && resolverMap.frame.coordinate_system.y_invert === false, 'selector frame preserves declared coordinate system');
const overlayId = marking.ensureOverlayGroup('processed_with:BOND_PREP:505', 'BOND_PREP 505');
marking.apply({ kind: 'claim_filter', groupId: overlayId, subjectType: 'Wafer', selector: { predicate: 'processed_with', signature: { step: 'BOND_PREP', plasma_power_W: 505 }, ids: ['wafer:OVERLAY'], evidenceIds: ['facet:1'] }, origin: { viewId: 'investigation-workspace', source: 'facet:p' } });
const overlaySnapshot = marking.snapshot();
const overlayGroup = overlaySnapshot.groups.find((group) => group.id === overlayId);
check(overlayGroup.role === 'overlay' && /^#[0-9A-F]{6}$/i.test(overlayGroup.color), 'comparison click creates a deterministic accessible overlay group');
check(marking.ensureOverlayGroup('processed_with:BOND_PREP:505') === overlayId, 'overlay group identity is deterministic');
check(marking.waferMarkKeys().includes('wafer:OVERLAY'), 'claim filter ids participate in reverse Trend marking');
check(markingSnapshotToSelection(overlaySnapshot, new Map()).every((item) => item.group !== overlayId), 'overlay claims never enter the A/B resolver contrast');
check(canonicalMark(overlayGroup.marks[0]).selector.evidenceIds[0] === 'facet:1', 'claim filter keeps predicate signature ids and evidence');
check(canonicalMark({ kind: 'entity_set', selector: { ids: ['wafer:A'], findingKind: 'alpha' } }).selector.findingKind === 'alpha', 'analysis mark preserves its explicit finding kind');
check(canonicalMark({ kind: 'entity_set', selector: { ids: ['wafer:legacy'] } }).subjectType === 'Wafer', 'legacy Wafer mark remains legacy instead of expanding across legs');
assert.throws(() => canonicalMark({ kind: 'time_range', selector: { from: '2026-08-15', to: '2026-08-01' } }), TypeError);
ran += 1;
assert.throws(() => canonicalMark({ kind: 'map_cells', selector: { frame: { table: 't', mapId: 'm' }, cells: [{ x: 1.5, y: 2 }] } }), TypeError);
ran += 1;
assert.throws(() => canonicalMark({ kind: 'map_cells', selector: { frame: { mapId: 'm' }, cells: [{ x: 1, y: 2 }] } }), TypeError);
ran += 1;
assert.throws(() => marking.apply({ kind: 'entity_set', groupId: 'Z', selector: { ids: ['x'] } }), TypeError);
ran += 1;
assert.throws(() => marking.replaceKind('entity_set', [], 'Z'), TypeError);
ran += 1;
check(canonicalMark({ kind: 'map_cells', selector: { frame: { table: 't', mapId: 'm', y_invert: 'false' }, cells: [{ x: 1, y: 1 }] } }).selector.frame.yInvert === false, 'string false never flips map Y');

const trend = normaliseTrendResponse({
  state: 'ready',
  selectable_finding_kinds: [
    { id: 'alpha', label: 'Alpha', series: [{ id: 'alpha:edge', subtype: 'edge', label: 'Edge' }, { id: 'alpha:center', subtype: 'center', label: 'Center' }] },
    { id: 'beta', label: 'Beta', series: [{ id: 'beta:all', subtype: '', label: 'All' }] },
  ],
  applied_kinds: ['alpha'],
  trace_dimensions: [{ id: 'dt_trace', label: 'DT Trace', ontology_path: ['Wafer', 'FinalChip', 'Component', 'DT'], states: ['ready', 'partial', 'absent'] }, { id: 'core_trace', label: 'Core Trace', ontology_path: ['Wafer', 'FinalChip', 'Component', 'Core'], states: ['ready', 'partial', 'absent'] }],
  series: [{ id: 'alpha:edge', points: [{
    identity: { type: 'Wafer', mark_key: 'opaque:subject:7f31', keys: { wafer: 'BASE-A' }, context: { role: 'planned_bonding_experiment_unit', bonding_leg: 'LEG-03' } }, occurred_at: '2026-08-14T00:00:00Z',
    value: { event_count: 3, found_chip_count: 2 },
  }] }],
  table: { truncated: true, next_cursor: 'next', rows: [{
    identity: { type: 'Wafer', mark_key: 'opaque:subject:7f31', keys: { wafer: 'BASE-A' }, context: { role: 'planned_bonding_experiment_unit', bonding_leg: 'LEG-03' } }, occurred_at: '2026-08-14T00:00:00Z',
    traceability: { dt: { state: 'ready', count: 3 }, core: { state: 'partial', count: 2, reason: 'one_missing' } },
    metrics: [{ series_id: 'alpha:edge', event_count: 3, found_chip_count: 2 }, { series_id: 'beta:all', event_count: 99 }],
  }] },
});
check(trend.charts.length === 1, 'dynamic series becomes chart');
check(trend.charts[0].xLabel === '날짜 - BASE WAFER-ID', 'chart declares the required date and base wafer X axis');
check(trend.columns.some((column) => column.key === 'alpha:center'), 'selected declared empty subtype remains a table dimension');
check(!trend.columns.some((column) => column.key === 'beta:all') && trend.selectableFindingKinds.length === 2, 'columns follow applied config while selectable definitions remain available');
check(trend.rows[0].waferId === 'opaque:subject:7f31', 'opaque server mark_key remains the cross-view identity');
check(trend.rows[0].wafer === 'BASE-A' && trend.rows[0].bondingLeg === 'LEG-03', 'table preserves Wafer identity and experiment context separately');
check(trend.charts[0].points[0].subjectLabel === 'WF BASE-A · 실험단위 LEG-03' && trend.charts[0].points[0].xTickLabel.includes('LEG-03'), 'chart point and tick identify both Wafer and experiment unit');
check(trend.columns.some((column) => column.key === 'bondingLeg' && column.label === '본딩 실험단위'), 'Trend Table declares the experiment-unit column');
check(trend.rows[0]['alpha:edge'] === 2, 'table metric is projected');
check(trend.columns.find((column) => column.key === 'trace:dt_trace').format(trend.rows[0]['trace:dt_trace']) === '연결 · 3', 'declared DT trace dimension maps to its traceability key');
check(trend.rows[0]['trace:core_trace'].state === 'partial' && trend.rows[0].traceability.core.reason === 'one_missing', 'trace cell and raw traceability preserve partial state');
check(trend.columns.find((column) => column.key === 'trace:core_trace').ontologyPath.at(-1) === 'Core', 'trace column preserves its ontology path declaration');
check(trend.cursor === 'next' && trend.totalRows === 2, 'cursor continuation remains visible without invented total');

const noBridge = compositionToWorkspace([], { selection: ['wafer:A'], finalChipIds: [] });
check(noBridge.state === 'no_live_bridge', 'wafer-to-final-chip gap is explicit');
check(noBridge.components.length === 0, 'no live bridge never invents a component');

const workspace = compositionToWorkspace([{
  state: 'ready', final_chip: { keys: { final_chip_id: 'CHIP-1' } },
  components: [{ entity_id: 'component:C1', component_id: 'C1', resolution_state: 'candidate',
    core: { type: 'Logic', role: 'controller' }, bonding: { position: { layer: 8 } },
    transfer_events: [{ evidence_id: 'e:1', occurred_at: '2026-08-14T00:00:00Z',
      from: { type: 'core_slot', keys: { lot: 'C-1', slot: '02' } },
      to: { type: 'dt_slot', keys: { lot: 'D-1', slot: '11' } } }],
    upstream_process: { evidence_ids: [{ evidence_id: 'p:1', step: 'CMP' }] },
  }],
}], { selection: [], finalChipIds: ['CHIP-1'] });
check(workspace.state === 'ready', 'composition ready state preserved');
check(workspace.composition.components.length === 1, 'N-way component array preserved');
check(workspace.composition.components[0].lineage.length === 0, 'per-chip transfer detail stays out of the default workspace');
check(workspace.composition.components[0].mapping_state === 'candidate', 'candidate is not promoted to resolved');
check(workspace.composition.components[0].process_segments[0].same_count === 1, 'upstream process evidence retained');

const comparison = compositionToWorkspace([
  { state: 'ready', final_chip: { keys: { final_chip_id: 'D' } }, components: [{
    entity_id: 'd1', component_id: 'd1', resolution_state: 'resolved',
    core: { type: 'HBM', role: 'stack_layer_01', branch: 'B' }, bonding: { layer: 1 },
    dt_collections: [{}, {}], transfer_events: [], upstream_process: { events: [
      { step: 'REWORK_CLEAN', knobs: { actual: {} } },
      { step: 'BOND_PREP', knobs: { actual: { plasma_power_W: 505 } } },
    ] },
  }] },
  { state: 'ready', final_chip: { keys: { final_chip_id: 'R' } }, components: [{
    entity_id: 'r1', component_id: 'r1', resolution_state: 'resolved',
    core: { type: 'HBM', role: 'stack_layer_01', branch: 'A' }, bonding: { layer: 1 },
    dt_collections: [{}], transfer_events: [], upstream_process: { events: [
      { step: 'BOND_PREP', knobs: { actual: { plasma_power_W: 420 } } },
    ] },
  }] },
], { finalChipIds: ['D', 'R'], populationByChip: { D: 'defect', R: 'reference' } });
check(comparison.subjects[0].population === 'defect' && comparison.subjects[1].population === 'reference', 'population roles survive the adapter');
check(comparison.composition.components[0].process_segments[0].differences.some((item) => item.label === 'BOND_PREP plasma power'), 'process knob becomes an N-way difference');
check(comparison.candidates.some((item) => item.label.includes('HBM · B · 505 · 다중 DT')), 'cause candidate is derived from real type, branch, knob and DT path');
check(!JSON.stringify(comparison).includes('root_cause_signal') && !JSON.stringify(comparison).includes('cause_regroup'), 'answer-key tags are not consumed');

const html = fs.readFileSync(new URL('../rnd-console.html', import.meta.url), 'utf8');
check(html.includes('data-rnd-kind-options') && !html.includes('data-rnd-defect-chips') && !html.includes('data-rnd-sample'), 'Trend Config replaces every manual CHIP/sample control');
const shellCss = fs.readFileSync(new URL('../src/rnd_console/styles.css', import.meta.url), 'utf8');
check(/\.rnd-controls button\s*\{[^}]*align-items:\s*center[^}]*justify-content:\s*center/s.test(shellCss), 'control buttons stay horizontally and vertically centered');
check(shellCss.includes('.rnd-controls > * { min-width: 0; }') && shellCss.includes('text-overflow: ellipsis'), 'control children and long config labels stay bounded');
check(['--space-1: 4px', '--space-2: 8px', '--space-3: 12px', '--space-4: 16px'].every((token) => shellCss.includes(token)), 'shell exposes the 4/8/12/16 spacing scale');
const mainSource = fs.readFileSync(new URL('../src/rnd_console/main.js', import.meta.url), 'utf8');
const stateSource = fs.readFileSync(new URL('../src/rnd_console/state.js', import.meta.url), 'utf8');
check(mainSource.includes("slice(0, 2)") && mainSource.includes("searchParams.set('charts'"), 'two-chart selection is bounded and persisted');
check(mainSource.includes('onVisibleChartsChange: changeVisibleCharts')
  && mainSource.includes('renderKindOptions(); persistKinds(); showBanner();'),
  'Trend item selection changes the visible chart and synchronizes config plus URL');
check(mainSource.includes("startsWith('table')") && mainSource.includes("meta.mark?.kind === 'trace_dimension'"), 'table marking preserves scroll fast path and trace clicks avoid a finding guess');
check(!mainSource.includes("findingKind: 'void'") && !mainSource.includes('COMPLEX_SAMPLE'), 'integration has no hardcoded finding or sample scope');
check(mainSource.includes("role: 'planned_bonding_experiment_unit'") && mainSource.includes('ids: mark.markKey ? [mark.markKey] : []'), 'map selection sends Wafer identity plus its experiment context');
check(mainSource.includes('bondingLeg: mark.bondingLeg, materialId: mark.materialId')
  && stateSource.includes("cell.bondingLeg || cell.bonding_leg"),
  'map-cell marks preserve the declared experiment-unit value in their spatial selector');

const mapIdentity = normaliseInvestigationPayload({ maps: [{
  id: 'map:bond:1', identity: { type: 'Wafer', mark_key: 'opaque:subject:leg-3', keys: { wafer: 'BASE-A' }, context: { role: 'planned_bonding_experiment_unit', bonding_leg: 'LEG-03' } },
  frame: { table: 'bonding_log', mapId: 'BOND-1', stage: 'Bond' }, meta: { cols: 2, rows: 2 },
  layers: { valid_die: [{ x: 1, y: 1 }] },
}] });
check(mapIdentity.maps[0].markKey === 'opaque:subject:leg-3' && mapIdentity.maps[0].wafer === 'BASE-A' && mapIdentity.maps[0].bondingLeg === 'LEG-03', 'map payload preserves Wafer identity and experiment context');
const body = (html.match(/<body[\s\S]*<\/body>/i) || [''])[0]
  .replace(/<option(?![^>]*selected)[\s\S]*?<\/option>/gi, '')
  .replace(/<script[\s\S]*?<\/script>/gi, '')
  .replace(/<[^>]+>/g, ' ')
  .replace(/\s+/g, ' ');
const placeholders = [...html.matchAll(/placeholder="([^"]*)"/g)].map((match) => match[1]).join(' ');
const visibleKoreanCharacters = ((body + placeholders).match(/[가-힣]/g) || []).length;
check(visibleKoreanCharacters <= 300, `default visible copy budget: ${visibleKoreanCharacters}/300 Korean characters`);

const requests = [];
const mockFetch = (url, options) => new Promise((resolve, reject) => {
  const request = { url, options, resolve, reject };
  requests.push(request);
  options.signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })), { once: true });
});
const api = createLedgerApi({ fetchImpl: mockFetch, base: '/x' });
const resolving = api.resolveSelection(resolverItems, { findingKind: 'alpha' });
check(requests[0].url === '/x/selection/resolve' && requests[0].options.method === 'POST', 'typed resolver uses the canonical POST route');
const resolverBody = JSON.parse(requests[0].options.body);
check(Array.isArray(resolverBody.selection) && resolverBody.window === '365d', 'resolver body preserves selection array and bounded window');
check(resolverBody.finding_kind === 'alpha', 'resolver body declares only an explicitly selected finding kind');
requests[0].resolve({ ok: true, status: 200, json: async () => ({
  state: 'ready', resolved_final_chip_ids: ['C-A'],
  selections: [{ input: { group: 'A' }, state: 'resolved', final_chip_ids: ['C-A'], wafer_mark_keys: ['wafer:A'], evidence_ids: ['e:1'] }],
  maps: [{ id: 'map:dt_map:DT:1', frame: { table: 'dt_map', map_id: 'DT:1', stage: 'DT', coordinate_system: { start_x: 1, start_y: 1, y_invert: false } }, layers: [] }],
  comparison: {
    groups: [{ group_id: 'A', component_count: 2 }],
    facets: { process: [{ facet_id: 'p', predicate: 'processed_with', signature: { step: 'BOND_PREP', recipe: { id: 'RCP-BOND-01' } }, wafer_mark_keys: ['wafer:A'], evidence_ids: ['facet:1'], groups: [{ group_id: 'A', count: 2, of_components: 2, frequency: 1, wafer_mark_keys: ['wafer:A'], evidence_ids: ['facet:1'] }], surprise: 0.9 }], measurement: [{ facet_id: 'm', predicate: 'measured', signature: { metric: 'bond_thickness', unit: 'nm', method: 'ellipsometry' }, wafer_mark_keys: ['wafer:A'], evidence_ids: ['measure:1'], groups: [{ group_id: 'A', value: 1125, count: 1, of_components: 2, state: 'recorded', state_counts: { recorded: 1, missing: 1 } }] }], context: [] },
    sequence: { state: 'ready', coverage: { resolved: 3, total: 4 }, differences: [
      { kind: 'order_change', left: [{ step: 'CMP' }], right: [{ step: 'BOND_PREP' }], support: { left: { A: 2 }, right: { B: 1 } }, evidence_ids: ['seq:1'] },
      { kind: 'record_absent', support: { B: 1 }, evidence_ids: [], state: 'missing' },
    ] },
    actions: [{ id: 'a1', label: '기록 확인' }], surprise: 0.9,
  },
}) });
const resolved = await resolving;
check(resolved.final_chip_ids[0] === 'C-A' && resolved.population_by_chip['C-A'] === 'defect', 'resolver union and A population survive normalization');
check(resolved.comparisons.process.length === 3, 'sequence differences append to process facets');
check(resolved.comparisons.process[0].label === 'BOND_PREP · RCP RCP-BOND-01',
  'Process candidate exposes only STEP and RCP name');
check(resolved.comparisons.measurement[0].label === 'bond_thickness · [nm] · ellipsometry'
  && resolved.comparisons.measurement[0].id === 'm',
  'Measurement candidate names the measured quantity, unit, and method');
check(resolved.comparisons.measurement[0].groups[0].value === '1125 · 누락 1'
  && resolved.comparisons.measurement[0].groups[0].stateCounts.missing === 1,
  'Measurement candidate exposes explicit missing-state counts beside the raw value');
check(resolved.groups[0].id === 'A' && resolved.groups[0].count === 2, 'resolver group shape adapts to workspace');
check(resolved.comparisons.process[0].groups[0].value === '100.0%' && resolved.comparisons.process[0].surprise.score === 0.9, 'facet frequency and surprise survive adaptation');
check(resolved.comparisons.process[0].ids[0] === 'wafer:A' && resolved.comparisons.process[0].evidenceIds[0] === 'facet:1' && resolved.comparisons.process[0].signature.recipe.id === 'RCP-BOND-01', 'facet reverse-mark ids, evidence and STEP/RCP signature survive adaptation');
check(resolved.comparisons.process[0].waferMarkKeys[0] === 'wafer:A' && resolved.comparisons.process[0].groups[0].waferMarkKeys[0] === 'wafer:A', 'facet and group reverse-mark keys remain view-readable');
check(resolved.actions[0].id === 'a1' && resolved.surprise.score === 0.9, 'resolver actions and top surprise survive adaptation');
check(resolved.maps[0].frame.mapId === 'DT:1' && resolved.maps[0].frame.table === 'dt_map', 'physical map frame survives normalization');
check(resolved.maps[0].frame.coordinate_system.start_x === 1 && resolved.maps[0].frame.coordinate_system.start_y === 1 && resolved.maps[0].frame.coordinate_system.y_invert === false, 'declared 1-based non-inverted coordinate metadata survives normalization');
check(resolved.comparisons.process[1].label === '공정 순서 변경' && resolved.comparisons.process[1].groups.find((group) => group.groupId === 'A').count === 2, 'sequence order support adapts by group');
check(resolved.comparisons.process[2].state === 'missing' && resolved.comparisons.process[2].groups.find((group) => group.groupId === 'B').state === 'missing', 'sequence record absence remains missing');
check(resolved.sequence.coverage.total === 4 && resolved.sequence.differences[0].evidence_ids[0] === 'seq:1', 'raw sequence evidence remains available');
const oldRequest = api.loadTrends({ window: '30d' }).catch((error) => error.name);
const newRequest = api.loadTrends({ window: '90d' });
check(requests[1].options.signal.aborted, 'new trend request aborts the previous request');
requests[2].resolve({ ok: true, status: 200, json: async () => ({ state: 'empty' }) });
check((await newRequest).state === 'empty', 'latest trend response wins');
check(await oldRequest === 'AbortError', 'aborted response cannot contaminate state');
api.dispose();

console.log(`ASSERTIONS ${ran} 0`);
