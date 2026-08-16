import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  CLAIM_STATES,
  MAP_STAGE_ORDER,
  RESOLUTION_STATES,
  WORKSPACE_LAYER_ORDER,
  groupDuplicateComparisonRows,
  normaliseClaimState,
  normaliseInvestigationPayload,
  partitionComparisonRows,
  partitionMapsByStage,
  rankedActions,
  sortComponents,
} from '../../src/rnd_console/investigation_workspace.js';
import { normalizeCompositeLineage } from '../../src/rnd_console/composite_lineage_adapter.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(HERE, '..', '..', 'src', 'rnd_console', 'investigation_workspace.js'), 'utf8');
let ran = 0;
let failed = 0;

function check(condition, message) {
  ran += 1;
  if (condition) return;
  failed += 1;
  console.error(`FAIL: ${message}`);
}

check(WORKSPACE_LAYER_ORDER.join('>') === 'valid_die>process_area>used_area>supply_material>defect',
  'map layers must preserve valid die -> process -> used -> supply -> defect order');
check(new Set(CLAIM_STATES).size === 5, 'claim states must remain distinct');
check(normaliseClaimState('missing') === 'missing', 'missing must not become unknown');
check(normaliseClaimState('not_performed') === 'not_performed', 'not-performed must not become missing');
check(normaliseClaimState('nonsense') === 'unknown', 'unrecognised state must degrade to unknown');

const model = normaliseInvestigationPayload({
  subjects: [{ id: 'chip-a' }, { id: 'chip-b' }, { id: 'chip-c' }],
  groups: [{ id: 'A', label: 'Group A', count: 6 }, { id: 'B', label: 'Group B', count: 6 }],
  surprise: { score: 2.4, mechanism_model_id: 'void_formation', binding_state: 'pass' },
  comparisons: { process: [{ id: 'pressure', label: 'Pressure', predicate: 'processed_with',
    signature: { step: 'BOND_PREP', parameter: 'pressure_MPa', value: 0.55 },
    wafer_mark_keys: ['wafer:SYN-CX-BW-001'], evidence_ids: ['e:p1'], surprise: {
    score: 1.8, expected: 'low', observed: 'high', mechanism_model_id: 'void_formation', binding_state: 'pass',
  }, groups: [{ group_id: 'A', value: '505', state: 'recorded' }, { group_id: 'B', value: '420', state: 'recorded' }] },
  { id: 'cmp-time', label: 'CMP time', groups: [
    { group_id: 'A', count: 3, total: 6, state: 'recorded' },
    { group_id: 'B', count: 5, total: 10, state: 'recorded' },
  ] }], measurement: [
    { id: 'thickness', label: '두께', groups: [{ group_id: 'A', value: '71.2', state: 'recorded' }, { group_id: 'B', value: '68.4', state: 'recorded' }] },
    { id: 'missing-metrology', label: '계측 기록', groups: [{ group_id: 'A', state: 'missing' }, { group_id: 'B', state: 'missing' }] },
  ] },
  coverage: { attributed: 7, total: 9 },
  composition: {
    same_count: 18,
    components: [
      {
        id: 'bottom-memory', type: 'MEM', role: 'Memory', position: 'P02', qty: 2,
        mapping_state: 'candidate', same_count: 94,
        process_segments: [{ label: '본딩', same_count: 91, differences: [{
          label: '두께 측정', state: 'missing',
          values: [
            { subject_id: 'chip-a', state: 'missing' },
            { subject_id: 'chip-b', state: 'recorded', text: '71.2 µm' },
            { subject_id: 'chip-c', state: 'not_performed' },
          ],
        }] }],
        lineage: [{ state: 'contested', from: { lot: 'C-1', slot: '02' }, to: { lot: 'D-7', slot: '11' } }],
        map_ids: ['dt-7'],
      },
      { id: 'top-logic', type: 'LOGIC', role: 'Logic', position: 'P01', process_segments: [] },
    ],
  },
  maps: [{ map_id: 'dt-7', frame: { table: 'dt_map', map_id: 'dt-7',
    start_x: 1, start_y: 1, y_invert: false },
  meta: { grid_cols: 3, grid_rows: 2, valid_die_ref: { map_id: 'V1' } }, layers: {
    valid_die: [[1, 1], [2, 1]], process_area: [[1, 1]], used_area: [[1, 1]], defect: [[1, 1, 2]],
  } }],
  actions: [
    { id: 'low', information_gain: 0.2, rank: 1 },
    { id: 'high', information_gain: 2.7, rank: 9 },
  ],
});

check(model.components.length === 2, 'one CHIP must retain multiple component branches');
check(model.groups.length === 2 && model.groups[0].id === 'A',
  'marking groups must survive normalisation without an A/B-only parser');
check(model.surprise.score === 2.4 && model.surprise.mechanismModelId === 'void_formation',
  'physics-backed overall surprise must preserve its cited model');
check(model.comparisons.process[0].surprise.score === 1.8,
  'facet surprise must remain attached to the compared process row');
check(model.comparisons.process[0].waferMarkKeys[0] === 'wafer:SYN-CX-BW-001'
  && model.comparisons.process[0].signature.parameter === 'pressure_MPa',
  'comparison rows must retain evidence-derived reverse-marking selectors');
const processBuckets = partitionComparisonRows(model.comparisons.process, model.groups);
check(processBuckets.different.map((row) => row.id).join(',') === 'pressure'
  && processBuckets.same.map((row) => row.id).join(',') === 'cmp-time',
  'candidate rows must list process differences while folding every equal recorded rate');
const measurementBuckets = partitionComparisonRows(model.comparisons.measurement, model.groups);
check(measurementBuckets.different.length === 2 && measurementBuckets.same.length === 0,
  'measurement differences stay visible and identical missing claims are never hidden as equal');
const duplicateBuckets = groupDuplicateComparisonRows([
  model.comparisons.process[0],
  { ...model.comparisons.process[0], id: 'pressure-second', evidenceIds: ['evidence:second'] },
  model.comparisons.process[1],
], model.groups);
check(duplicateBuckets.singles.map((row) => row.id).join(',') === 'cmp-time'
  && duplicateBuckets.duplicates.length === 1
  && duplicateBuckets.duplicates[0].count === 2,
  'visually identical candidate rows must fold while retaining every evidence row inside');
const mapStages = partitionMapsByStage([
  { id: 'core-a', stage: 'Core' }, { id: 'bond-a', frame: { stage: 'Bond' } },
  { id: 'dt-a', stage: 'DT' }, { id: 'bond-b', stage: 'BONDING' },
]);
check(MAP_STAGE_ORDER.join('>') === 'bond>dt>core'
  && mapStages.map((group) => `${group.stage}:${group.maps.length}`).join(',') === 'bond:2,dt:1,core:1',
  'maps must keep BONDING -> DT -> CORE vertical order and every same-stage WF peer');
check(model.components[0].role === 'Memory' && model.components[0].position === 'P02',
  'component role and position must survive normalisation');
check(model.components[0].segments[0].sameCount === 91,
  'compressed 100+ claim accounting must survive normalisation');
check(model.components[0].segments[0].differences[0].values[0].state === 'missing',
  'side-specific missing state must survive N-way normalisation');
check(model.components[0].segments[0].differences[0].values.length === 3,
  'N comparison subject values must survive without a two-column limit');
check(model.components[0].segments[0].differences[0].values[2].state === 'not_performed',
  'N-way values must preserve not-performed separately from missing');
check(model.components[0].transfers[0].state === 'contested',
  'component lineage must preserve contested state');
check(model.maps[0].meta.validDieRef === 'V1', 'valid-die metadata reference must survive');
check(model.maps[0].layers.defect[0].value === 2, 'defect layer count must survive');
check(model.maps[0].meta.startX === 1 && model.maps[0].meta.startY === 1 && model.maps[0].meta.yInvert === false,
  'standard VOID frame must preserve 1-based origin and non-inverted Y');
check(model.actions[0].id === 'high', 'actions must rank by expected information gain');
check(rankedActions([{ id: 'a', information_gain: 1 }, { id: 'b', information_gain: 3 }])[0].id === 'b',
  'rankedActions must put highest information gain first');
check(sortComponents(model.components, 'position')[0].id === 'top-logic',
  'component sorting must support physical position');
check(sortComponents(model.components, 'type')[0].id === 'top-logic',
  'component sorting must support core type');
check(!SOURCE.includes('fetch('), 'workspace must not hardcode API fetches');
check(SOURCE.includes('adapter.loadWorkspace'), 'workspace must consume an injected adapter');
check(SOURCE.includes('AbortController'), 'selection refresh must cancel stale requests');
check(SOURCE.includes("kind: 'map_die'"), 'map cells must emit a typed spatial mark');
check(SOURCE.includes('options.onComparisonMark'),
  'comparison rows must expose the same marking seam as charts, tables, and maps');
check(SOURCE.includes("section(doc, 'Candidates'") && SOURCE.includes("appendCategory('Process'")
  && SOURCE.includes("appendCategory('Measurement'"),
  'Candidates must enumerate separate Process and Measurement lists');
check(SOURCE.includes('partitionMapsByStage(model.maps)') && !SOURCE.includes("'riw-map__open'"),
  'every map with data must render inside its vertical stage instead of a lazy placeholder');
check(SOURCE.includes('같은 기록 ${duplicateCount}개 · ${displayed.duplicates.length}묶음'),
  'duplicate candidate evidence must sit behind one closed parent summary');
check(SOURCE.includes('map.meta.yInvert ? height - 1 - localY : localY'),
  'map renderer must not invert Y when the declared physical frame says false');
check(RESOLUTION_STATES.join('|') === 'resolved|candidate|contested|unresolvable',
  'lineage resolution states must remain explicit');

const lineage = normalizeCompositeLineage({ composite_lineage: {
  state: 'ready', final_chip: { chip_id: 'CHIP-1', layer_count: 12 },
  comparison_subjects: [{ id: 'CHIP-1' }, { id: 'CHIP-2' }, { id: 'CHIP-3' }],
  components: [{
    component_id: 'DIE-1', core_type: 'LOGIC',
    dt_collections: [
      { container: 'DT-A', slot: '01', position: 'P3' },
      { container: 'DT-B', slot: '07', position: 'P9' },
    ],
    pick_events: [{ event_id: 'PICK-1', from: { container: 'DT-B', slot: '07', position: 'P9' } }],
    bonding_events: [{ event_id: 'BOND-1', layer: 11, position: { position: 'L11-C4' } }],
    lineage_nodes: [{ id: 'N1', kind: 'process' }, { id: 'N2', kind: 'transfer' }, { id: 'N3', kind: 'bonding' }],
  }],
  maps: [{ id: 'MAP-A' }, { id: 'MAP-B' }],
  spatial_attributions: [{ component_id: 'DIE-1', map_id: 'MAP-B' }],
} });
check(lineage.components[0].dtCollections.length === 2,
  'one component must retain every DT collection visited');
check(lineage.components[0].pickEvents.length === 1 && lineage.components[0].bondingEvents.length === 1,
  'pick and bonding events must remain arrays');
check(lineage.components[0].lineageNodes.length === 3,
  'generic N-node lineage must retain every upstream node');
check(lineage.comparisonSubjects.length === 3,
  'composite adapter must not impose a two-subject comparison limit');
check(lineage.maps.length === 2 && lineage.spatialAttributions.length === 1,
  'adapter must preserve N maps and spatial drill links');

console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
