/**
 * Legend map-key scope contract.
 *
 * THE ASSERTION NOBODY HAD: when a map is open, the legend on screen - and above all the
 * `replace_map` payload built from it - contains ONLY values that this map vouches for.
 *
 * Why this file exists. `map_split_registry` rows are keyed (ref_table, map_key, value).
 * The map editor USED TO seed the legend with a TABLE-WIDE read (no map_key filter, deduped
 * by value across every map key in the table), so the user had the table's value vocabulary
 * as brushes before any map was chosen. Nothing downstream could tell such a row from a row
 * this map actually owns, so opening a map and saving wrote another map's values into it -
 * a `replace_map` write, so they became that map's whole plan. One value ("elle", defined in
 * bonding_map|TEST_MAP_01) had spread to four bonding_map keys in production.
 *
 * THE SEED IS GONE (2026-07-28, 사용자 지시). Opening the panel now has exactly two
 * branches: this map's registry rows if it has any, one empty DOE row (`VALUE 1`) if it
 * does not. A panel that opens with values nobody entered is indistinguishable from a
 * defect, and it was reported as one twice.
 *
 * THIS FILE DID NOT BECOME REDUNDANT. The placeholder row is still marked `vocab: true`
 * (an untouched placeholder must not create a registry row), the map-scoped read still has
 * to carry its `map_key` filter, and the DERIVED claim still has to catch an edit path that
 * forgot the gate - which now matters more, not less, because the zone redesign added four
 * persisted columns and a whole second table of edit paths.
 *
 * Read-only: it never writes to client2/. The functions under test are module-private,
 * and this harness must not change that, so it slices the named function declarations out
 * of the source text and evaluates them in a vm sandbox with stubs for the module state
 * they touch (`legend`, `legendMeta`, `activeBrush`).
 *
 * FAILS LOUDLY on extraction problems (exit 2). A harness that silently passes when it can
 * no longer find the functions is worse than no harness, because its green result gets
 * cited as evidence.
 *
 * Exit codes: 0 = client honours the scope | 1 = scope violation(s) | 2 = harness failure.
 *
 *   node contracts/legend_map_scope/client_harness.mjs
 *   node contracts/legend_map_scope/client_harness.mjs --json
 */
import { readFileSync } from 'node:fs';
import { loadWithProbe } from '../../client2/tests/lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const SRC_PLAN = join(ROOT, 'client2', 'src', 'transfer_plan.js');
const SRC_EDITOR = join(ROOT, 'client2', 'src', 'map_editor.js');
// The registry ROW normal form (payload/parse/fingerprint/signature) moved out of
// map_editor.js into its own module; the STATEFUL half (the read/save orchestration and the
// legend cluster it mutates) stayed. Both halves are sliced, from wherever they now live.
const SRC_ROW = join(ROOT, 'client2', 'src', 'split_registry_row.js');
const JSON_OUT = process.argv.includes('--json');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

/** Slice `[async] function NAME(...) { ... }` out of source by brace matching.
 *  A leading `export ` is accepted and EXCLUDED from the slice - the pieces are evaluated
 *  inside a vm script, where an export statement is a SyntaxError. The registry row normal
 *  form lives in an extracted module (client2/src/split_registry_row.js) and exports its
 *  symbols; map_editor.js keeps the stateful half module-private. This harness must be able
 *  to slice either spelling. */
function extractFunction(source, name, file) {
  const decl = new RegExp(`(^|\\n)\\s*(?:export\\s+)?((?:async\\s+)?function\\s+${name}\\s*\\()`);
  const m = decl.exec(source);
  if (!m) die(`could not extract function '${name}' from ${file} - it was renamed, removed, or reshaped. Update this harness deliberately; do not delete the check.`);
  const start = m.index + m[0].length - m[2].length;
  let i = source.indexOf('{', start + m[2].length - 1);
  if (i < 0) die(`found '${name}' in ${file} but no body`);
  let depth = 0;
  for (; i < source.length; i++) {
    const c = source[i];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return source.slice(start, i + 1); }
  }
  die(`unbalanced braces while extracting '${name}' from ${file}`);
}

/** Slice a single-line `const NAME = ...;` out of source. Taken from source, never
 *  re-typed here: the fingerprint separators are control characters, and a harness that
 *  guessed them would compare fingerprints the product never produces. */
function extractConst(source, name, file) {
  const m = new RegExp(`(^|\\n)\\s*const\\s+${name}\\s*=[^\\n]*`).exec(source);
  if (!m) die(`could not extract const '${name}' from ${file} - it was renamed or removed. Update this harness deliberately.`);
  return m[0].replace(/\/\/.*$/, '');
}

const planSrc = readFileSync(SRC_PLAN, 'utf8');
const editorSrc = readFileSync(SRC_EDITOR, 'utf8');
const rowSrc = readFileSync(SRC_ROW, 'utf8');

// split_registry_row.js — the ROW normal form. Pure functions of their arguments.
const NEEDED_ROW = [
  'parseJsonCol', 'normalizeKnobs', 'knobsToObject', 'serializeKnobs',
  'serializeStack', 'serializeMaterials',   // zone 저장 정규형 (`serializeBands`를 대체)
  'legendRowPayload',                       // 저장 컬럼의 단일 투영 — 아래 §5h가 이것을 건다
  'normalizeLegendItem', 'cloneLegend', 'normalizeBands',
  'parseLegendRegistryRows',        // GET response -> registry rows
  'legendRowSignature',             // the one normal form the derived claim compares
  'buildLegendRegistryUpdates',     // on-screen legend -> `replace_map` payload
  'buildSplitKey', 'canonRegistryRow', 'registryFingerprint',
];

// map_editor.js — the STATEFUL half. These read and write the legend cluster, which is why
// they did not move with the row normal form.
const NEEDED_EDITOR = [
  'probeZoneColumns',               // 물리 zone 컬럼 게이트 (저장 파괴 방지)
  'reconcileVocabClaims',           // claim = painted OR differs from what was seeded
  'fetchRegistryRows',              // the named scope - the request itself is asserted
  'readRegistryScope',              // map scope wrapper (load + save both go through it)
  'seedEmptyDoe',                   // the ONLY answer to "this map has no registry rows"
  'applyRegistryRowsToLegend',      // this map's rows -> on-screen legend
  'saveLegendToServer',             // the real write path: scope + authority + fingerprint
];

// [U6] The empty-map seed is served now (paint-rules `default_legend`); the client keeps
// only the "nothing declared" arm as EMPTY_DOE_SEED, resolved through defaultLegendRows().
// Both are taken from source - a re-typed copy would test a fiction. This harness runs
// with `overlayContract = null` (see preamble), i.e. the no-served-declaration arm, which
// is the branch the two-branch seeding contract here is about.
function extractEmptyDoeSeed(source) {
  const m = /(^|\n)\s*const\s+EMPTY_DOE_SEED\s*=\s*\[/.exec(source);
  if (!m) die("could not extract const 'EMPTY_DOE_SEED' from map_editor.js");
  let i = source.indexOf('[', m.index), depth = 0;
  for (; i < source.length; i++) {
    if (source[i] === '[') depth++;
    else if (source[i] === ']') { depth--; if (depth === 0) return `const EMPTY_DOE_SEED = ${source.slice(source.indexOf('[', m.index), i + 1)};`; }
  }
  die("unbalanced brackets while extracting 'EMPTY_DOE_SEED'");
}

const zoneSrc = readFileSync(join(ROOT, 'client2', 'src', 'doe_bands.js'), 'utf8');

// 🔴 NOTHING IS CUT OUT ANY MORE. The four subjects -- map_editor.js, split_registry_row.js,
// transfer_plan.js and doe_bands.js -- are imported WHOLE, one probe each. Slicing scores the
// SHAPE OF THE LETTERS: the day one of these functions calls a helper that is not on the list,
// this contract reddens on correct code and names the missing symbol, not the change.
//
// The consts it had to cut in beside them -- SPLIT_KEY_SEP, FP_UNIT, FP_ROW,
// LEGEND_PAYLOAD_COLUMNS, SPLIT_REGISTRY_TABLE, REGISTRY_SCOPES, ZONE_COLUMNS, EMPTY_DOE_SEED
// -- are simply in scope. `extractEmptyDoeSeed` is gone with them: a bracket-balancing reader
// for one array literal existed only because a script-level `const` is lexical, so the sandbox
// could not see it.
//
// `API_BASE`, `CURRENT_USER` and `getLocalTimeString` are IMPORTS of map_editor.js. No probe
// can reach an import binding, so they come through the loader hook.
//
// The real `fetchRegistryRows` still runs: only the socket underneath it is stubbed, so the
// URL it builds -- specifically whether it carries a `map_key` filter -- is evidence rather
// than an assumption. `probeZoneColumns` is still NOT stubbed: it is a guard on the
// destructive write path, and a harness that mocked it would be asserting the guard exists
// rather than that it works.
const STUB = { urls: [], writes: [], body: { total: 0, data: [] }, httpOk: true,
               mapKey: null, zoneBody: null };

globalThis.document = {
  getElementById: () => null, addEventListener() {}, removeEventListener() {},
  querySelector: () => null, querySelectorAll: () => [],
};
globalThis.window = globalThis.window || {
  location: { port: '', origin: '', protocol: 'http:', host: '', search: '' },
  addEventListener() {},
};
globalThis.fetch = async (url, init) => {
  const m = ((init && init.method) || 'GET').toUpperCase();
  if (m === 'GET') {
    STUB.urls.push(String(url));
    const isProbe = String(url).indexOf('limit=1') >= 0 && String(url).indexOf('filters=') < 0;
    const body = (isProbe && STUB.zoneBody) ? STUB.zoneBody : STUB.body;
    return { ok: STUB.httpOk, status: STUB.httpOk ? 200 : 500, json: async () => body };
  }
  STUB.writes.push(JSON.parse(init.body));
  return { ok: true, status: 200, json: async () => ({}) };
};

// Module state the imported functions read and write. `legend` is the on-screen legend;
// `gridData` is the painted map ("x_y" -> value), which is how a map claims a value.
const EDITOR_STAGE = {
  legend: [], legendMeta: {}, activeBrush: '', gridData: {},
  legendVocabularySeed: new Map(),
  selectedTable: 'bonding_map',
  legendReplaceScope: null, legendConflict: null,
  // [U6] no served default_legend -> the EMPTY_DOE_SEED arm
  overlayContract: null,
  legendSaveState: { status: 'idle', at: '', error: '' },
  zoneColumnsPresent: null, draftBase: null,
  getCurrentMapKey: () => STUB.mapKey,
  renderLegendTable: () => {}, renderGridCanvas: () => {}, renderLegendMetaOnly: () => {},
  saveLegendToStorage: () => {}, saveDoeDraft: () => {}, clearDoeDraft: () => {},
  cellsDigest: () => '0:0',
};

const editor = (await loadWithProbe(SRC_EDITOR, {
  expose: [...NEEDED_EDITOR, 'defaultLegendRows', 'SPLIT_REGISTRY_TABLE', 'REGISTRY_SCOPES',
           'ZONE_COLUMNS', 'EMPTY_DOE_SEED'],
  state: Object.keys(EDITOR_STAGE),
  stubs: {
    './config.js': { API_BASE: 'http://harness', CURRENT_USER: 'tester' },
    './utils.js': { getLocalTimeString: () => '2026-07-27 21:00:00' },
  },
  tag: 'legendscope_editor',
})).probe;

const rowMod = (await loadWithProbe(SRC_ROW, {
  expose: [...NEEDED_ROW, 'SPLIT_KEY_SEP', 'FP_UNIT', 'FP_ROW', 'LEGEND_PAYLOAD_COLUMNS'],
  tag: 'legendscope_row',
})).probe;

const plan = (await loadWithProbe(SRC_PLAN, {
  expose: ['bandToState', 'prevTo'],
  tag: 'legendscope_plan',
})).probe;

const zones = (await loadWithProbe(join(ROOT, 'client2', 'src', 'doe_bands.js'), {
  expose: ['boundState', 'parseMaterialList', 'bandsToZones'],
  tag: 'legendscope_zones',
})).probe;

// One lookup, the same shape the scorer already used. The map_editor probe is the base so its
// ACCESSORS survive: `sandbox.legend = …` has to reach the module, and a flat copy would turn
// a live binding into a dead value.
const sandbox = editor;
for (const p of [rowMod, plan, zones]) {
  for (const [k, v] of Object.entries(p)) if (!(k in sandbox)) sandbox[k] = v;
}
Object.assign(sandbox, EDITOR_STAGE);
sandbox.STUB = STUB;

for (const fn of ['bandToState', ...NEEDED_ROW, ...NEEDED_EDITOR]) {
  if (typeof sandbox[fn] !== 'function') die(`'${fn}' did not evaluate to a function`);
}

// ---------------------------------------------------------------------------
// Fixture. Two map keys in ONE table with OVERLAPPING and DISJOINT values. The rows carry
// ZONE columns (`stack`/`mat_1h`/`mat_mid`/`mat_top`) - the retired `bands` column is read
// only by the migration and is exercised in contracts/doe_band_rules.
//
// ⚠️ WHAT CHANGED ON 2026-07-28, and why several scenarios below are GONE rather than
//    rewritten. The table-wide 'vocabulary' read is deleted: the panel no longer borrows
//    the table's value vocabulary as a brush palette, because a screen that opens with
//    values nobody entered is indistinguishable from a defect (reported twice). The rule
//    is two branches with no third - this map's registry rows if it has any, one empty DOE
//    row if it does not.
//
//    DELETED, with reasons:
//      §0  the table-wide dedupe (`parseLegendRegistryRows(_, true)`) - no caller can ask
//          for it any more; `fetchRegistryRows` passes `false` unconditionally and §0c
//          asserts the map scope never collapses duplicates, which is the property that
//          actually protects a broken `map_key` filter from looking plausible.
//      §0b the vocabulary seed request - the request does not exist.
//      §3  "a fresh key must not inherit the vocabulary" - there is no vocabulary to
//          inherit. Its successor is §3z: a fresh key inherits the EMPTY DOE and writes
//          nothing, which is the same guarantee against the one seed that remains.
//
//    KEPT AND STILL LOAD-BEARING: everything about the map-scoped read, the `vocab`
//    payload filter, and the DERIVED claim. The placeholder row `seedEmptyDoe` puts on
//    screen is marked `vocab: true`, so an untouched placeholder still must not create a
//    registry row, and a forgotten edit gate still must be caught by signature.
// ---------------------------------------------------------------------------
const cell = v => (v === undefined ? undefined : { value: v, is_overwrite: false, priority_source: 'user', updated_by: 'tester' });
const row = (mapKey, value, desc, color, zone, updatedAt) => ({
  data: {
    map_key: cell(mapKey), value: cell(value), split_desc: cell(desc), color: cell(color),
    knobs: cell('{}'),
    stack: cell(zone ? String(zone.stack) : ''),
    mat_1h: cell(JSON.stringify((zone && zone.mat_1h) || [])),
    mat_mid: cell(JSON.stringify((zone && zone.mat_mid) || [])),
    mat_top: cell(JSON.stringify((zone && zone.mat_top) || [])),
    eventtime: cell(updatedAt), updated_at: cell(updatedAt),
  },
});

const MAPA_ROWS = [
  row('MAPA', '1', 'A: thickness down', '#10b981', { stack: 3, mat_mid: ['LOT_A1'] }, '2026-07-27 20:57:03'),
  row('MAPA', '2', 'A: POR',            '#ef4444', { stack: 5, mat_mid: ['LOT_A2'] }, '2026-07-27 20:57:03'),
  row('MAPA', 'A_ONLY',  'A exclusive split',  '#3b82f6', { stack: 9, mat_mid: ['LOT_A3'] }, '2026-07-27 20:57:03'),
  row('MAPA', 'A_ONLY2', 'A exclusive split 2', '#ec4899', null, '2026-07-27 20:57:03'),
];
const MAPB_ROWS = [
  row('MAPB', '1',      'B: thickness x2', '#f59e0b', { stack: 7, mat_mid: ['LOT_B1'] }, '2026-07-26 09:00:00'),
  row('MAPB', 'B_ONLY', 'B exclusive split', '#8b5cf6', { stack: 2, mat_1h: ['LOT_B2'], mat_top: ['LOT_B3'] }, '2026-07-26 09:00:00'),
];
const TABLE_WIDE = { total: 6, data: [...MAPA_ROWS, ...MAPB_ROWS] };
const SCOPED_B   = { total: 2, data: MAPB_ROWS };

// The one-row probe response that says the zone columns physically exist.
const ZONE_PROBE_OK = { total: 1, data: [{ data: {
  value: cell('x'), split_desc: cell(''), color: cell('#000'), knobs: cell('{}'),
  stack: cell(''), mat_1h: cell('[]'), mat_mid: cell('[]'), mat_top: cell('[]'), eventtime: cell(''),
} }] };
// ...and one that says they do not (the pre-migration server).
const ZONE_PROBE_MISSING = { total: 1, data: [{ data: {
  value: cell('x'), split_desc: cell(''), color: cell('#000'), knobs: cell('{}'),
  bands: cell('[]'), eventtime: cell(''),
} }] };

const REF_TABLE = 'bonding_map';
const failures = [];
let compared = 0;
const rec = (scenario, field, expected, actual) => {
  compared++;
  if (JSON.stringify(expected) !== JSON.stringify(actual)) failures.push({ scenario, field, expected, actual });
};
const values = arr => arr.map(l => String(l.value)).sort();
const payloadValues = ups => ups.map(u => String(u.updates.value)).sort();

// Seed the legend the way switchTable does now: ONE empty DOE row, marked and snapshotted.
// Seeded through the PRODUCT's function, never by hand - hand-marking would fake the
// `vocab` flag and the seed snapshot together, and the derived-claim machinery below would
// then be tested against a fixture instead of against the app.
function seedEmpty(painted) {
  sandbox.seedEmptyDoe();
  sandbox.gridData = {};
  (painted || []).forEach((v, i) => { sandbox.gridData[`${i}_0`] = v; });
}

const REQUESTS = [];   // the request list this harness reports as evidence
const filterOf = url => JSON.parse(decodeURIComponent(String(url).split('filters=')[1] || '%7B%7D'));

// --- 0. THE EMPTY DOE. Two branches, no third. -----------------------------------------
{
  seedEmpty();
  rec('empty-doe', 'exactly one row', 1, sandbox.legend.length);
  rec('empty-doe', 'the row is VALUE 1', '1', String(sandbox.legend[0].value));
  rec('empty-doe', 'nothing is prefilled', ['', '', [], [], []],
    [String(sandbox.legend[0].stack), sandbox.legend[0].desc,
     sandbox.legend[0].mat_1h, sandbox.legend[0].mat_mid, sandbox.legend[0].mat_top]);
  rec('empty-doe', 'the placeholder is marked unclaimed', true, sandbox.legend[0].vocab === true);
  rec('empty-doe', 'an untouched placeholder writes NOTHING', [],
    payloadValues(sandbox.buildLegendRegistryUpdates(REF_TABLE, 'ANY', sandbox.legend, 'tester', 'now')));
  rec('empty-doe', 'the brush is usable immediately', '1', sandbox.activeBrush);
}

// --- 0c. THE MAP-SCOPED READ. It must actually filter by map_key, and the scope name
//         must be spelled - `null` may never quietly become "the whole table".
{
  sandbox.STUB.body = SCOPED_B;
  sandbox.STUB.urls = [];
  const r = await sandbox.readRegistryScope(REF_TABLE, 'MAPB');
  REQUESTS.push(['readRegistryScope(MAPB)', filterOf(sandbox.STUB.urls[0])]);
  rec('map-scoped-read', 'ok', true, r.ok);
  rec('map-scoped-read', 'request carries a map_key filter', ['map_key', 'ref_table'], Object.keys(filterOf(sandbox.STUB.urls[0])).sort());
  rec('map-scoped-read', 'filtered on the right key', 'MAPB', filterOf(sandbox.STUB.urls[0]).map_key.filter);
  rec('map-scoped-read', 'rows', ['1', 'B_ONLY'], values(r.rows));
  rec('map-scoped-read', 'zone columns survive the read', [7, ['LOT_B1']],
    [Number(r.rows.find(x => x.value === '1').stack), r.rows.find(x => x.value === '1').mat_mid]);

  // The map scope must NOT dedupe. Dedupe was the vocabulary mode's collapse across map
  // keys; doing it here would MASK a broken map_key filter - a widened read would come
  // back as a plausible one-row-per-value legend instead of an obviously wrong pile.
  sandbox.STUB.body = TABLE_WIDE;
  const wide = await sandbox.readRegistryScope(REF_TABLE, 'MAPB');
  rec('map-scoped-read', 'map scope never collapses duplicate values', 6, wide.rows.length);
  sandbox.STUB.body = SCOPED_B;

  // a missing map key must be refused, not silently widened to the whole table
  sandbox.STUB.urls = [];
  const bad = await sandbox.readRegistryScope(REF_TABLE, null);
  rec('map-scoped-read', 'null map key is refused', false, bad.ok);
  rec('map-scoped-read', 'and no request was issued', 0, sandbox.STUB.urls.length);
  let threw = '';
  try { await sandbox.fetchRegistryRows('whatever', REF_TABLE, 'MAPB'); } catch (e) { threw = e.message; }
  rec('map-scoped-read', 'an unnamed scope is refused', "unknown registry scope 'whatever'", threw);
  // ...including the one that used to exist. A retired scope must not still answer.
  let threwVocab = '';
  try { await sandbox.fetchRegistryRows('vocabulary', REF_TABLE, null); } catch (e) { threwVocab = e.message; }
  rec('map-scoped-read', "the retired 'vocabulary' scope is refused", "unknown registry scope 'vocabulary'", threwVocab);

  // truncation stays a failure, not a smaller answer (a partial read backing replace_map deletes)
  sandbox.STUB.body = { total: 99, data: MAPB_ROWS };
  const trunc = await sandbox.readRegistryScope(REF_TABLE, 'MAPB');
  rec('map-scoped-read', 'truncated response is a failure', false, trunc.ok);
}

// --- 1. SCREEN. Open MAPB -> only MAPB's values, and the placeholder is evicted ---------
{
  seedEmpty();
  sandbox.applyRegistryRowsToLegend(sandbox.parseLegendRegistryRows(SCOPED_B, false));
  rec('open-mapB/screen', 'legend values', ['1', 'B_ONLY'], values(sandbox.legend));
  const one = sandbox.legend.find(l => String(l.value) === '1');
  rec('open-mapB/screen', 'shared value desc comes from MAPB', 'B: thickness x2', one && one.desc);
  rec('open-mapB/screen', "shared value's zones come from MAPB", [7, ['LOT_B1'], [], []],
    one && [Number(one.stack), one.mat_mid, one.mat_1h, one.mat_top]);
  // 🔴 THE PLACEHOLDER IS VALUE '1' AND SO IS ONE OF MAPB'S ROWS. That collision is
  //    deliberate: it is the only shape in which an unclaimed placeholder could survive
  //    into a payload by being mistaken for a real row.
  rec('open-mapB/screen', 'the placeholder is claimed by the registry row', false, one && one.vocab);
}

// --- 2. WRITE. The `replace_map` payload for MAPB must not carry MAPA's values ----------
{
  seedEmpty();
  sandbox.applyRegistryRowsToLegend(sandbox.parseLegendRegistryRows(SCOPED_B, false));
  const ups = sandbox.buildLegendRegistryUpdates(REF_TABLE, 'MAPB', sandbox.legend, 'tester', '2026-07-27 21:00:00');
  rec('open-mapB/write', 'replace_map payload values', ['1', 'B_ONLY'], payloadValues(ups));
  rec('open-mapB/write', 'every row is scoped to MAPB', true, ups.every(u => u.updates.map_key === 'MAPB'));
  rec('open-mapB/write', 'split_key set', ['bonding_map|MAPB|1', 'bonding_map|MAPB|B_ONLY'],
    ups.map(u => u.business_key_val).sort());
  // 🔴 THE RETIRED COLUMN IS NOT WRITTEN. `bands` is read-only now; a second writer would
  //    put the plan in two places and `replace_map` would let them erase each other.
  rec('open-mapB/write', 'no payload carries `bands`', [], ups.filter(u => 'bands' in u.updates).map(u => u.updates.value));
  // 🔴 THE LITERAL MUST BE COMPLETE. `buildLegendRegistryUpdates` spells its column names
  //    out so `server/tests/test_install_product_tables.py` can read them statically and
  //    prove each one is declared. That leaves exactly one gap - adding a column to
  //    `legendRowPayload` and forgetting it in the literal - and this closes it. A column
  //    that is signed and fingerprinted but never actually written would make an edit look
  //    saved on screen and be absent from the server.
  {
    const cols = sandbox.LEGEND_PAYLOAD_COLUMNS;
    const written = Object.keys((ups[0] || { updates: {} }).updates);
    rec('open-mapB/write', 'every LEGEND_PAYLOAD_COLUMNS entry is actually written', [],
      cols.filter(c => written.indexOf(c) < 0));
  }
  const b = ups.find(u => u.updates.value === 'B_ONLY');
  rec('open-mapB/write', 'zone columns are what goes out',
    ['2', '["LOT_B2"]', '[]', '["LOT_B3"]'],
    b && [b.updates.stack, b.updates.mat_1h, b.updates.mat_mid, b.updates.mat_top]);
}

// --- 3z. A fresh key inherits the EMPTY DOE and writes nothing --------------------------
// The successor to the deleted "must not inherit the vocabulary". The hazard is the same
// and it is the one that created bonding_map|A23, |b1, |aa123_a in production: pick a
// table, type a NEW map key, and the debounced save fires. `replace_map` on an empty scope
// deletes nothing, so every other guard passes - and a plan appears out of nowhere.
{
  seedEmpty();
  const ups = sandbox.buildLegendRegistryUpdates(REF_TABLE, 'NEWKEY', sandbox.legend, 'tester', '2026-07-27 21:00:00');
  rec('fresh-key/write', 'replace_map payload values', [], payloadValues(ups));
}

// --- 4. NO REGRESSION. Everything the map actually vouches for is still written ---------
// (a) rows from this map's own registry; (b) a value the user explicitly added.
//
// The old third case - "a value the map's cells carry but its registry does not" - was
// about a VOCABULARY row that painting rescued. With no vocabulary seed the only unclaimed
// row that can exist is the placeholder, and §5 asserts that painting claims it directly.
// A value the loader adds from the map's own cells arrives WITHOUT the mark, so it is
// written by construction rather than by rescue; asserting it here would test
// `normalizeLegendItem`'s default, not the scope rule this file is about.
{
  seedEmpty();
  sandbox.applyRegistryRowsToLegend(sandbox.parseLegendRegistryRows(SCOPED_B, false));
  sandbox.legend.push(sandbox.normalizeLegendItem({ value: 'D1', desc: 'typed by user', color: '#14b8a6' }));
  const ups = sandbox.buildLegendRegistryUpdates(REF_TABLE, 'MAPB', sandbox.legend, 'tester', '2026-07-27 21:00:00');
  rec('vouched/write', 'payload values', ['1', 'B_ONLY', 'D1'], payloadValues(ups));
  const b = ups.find(u => u.updates.value === 'B_ONLY');
  rec('vouched/write', "B_ONLY's zones survive the round trip", ['2', '["LOT_B2"]', '[]', '["LOT_B3"]'],
    b && [b.updates.stack, b.updates.mat_1h, b.updates.mat_mid, b.updates.mat_top]);
  // a value the user just added carries NO borrowed layer structure
  const d1 = ups.find(u => u.updates.value === 'D1');
  rec('vouched/write', 'a new value has no borrowed layer structure', ['', '[]', '[]', '[]'],
    d1 && [d1.updates.stack, d1.updates.mat_1h, d1.updates.mat_mid, d1.updates.mat_top]);
}

// --- 5. A painted placeholder IS written -----------------------------------------------
{
  seedEmpty(['1']);                                // user painted cells with the placeholder
  sandbox.reconcileVocabClaims();
  rec('fresh-key/painted', 'the painted placeholder is written', ['1'],
    payloadValues(sandbox.buildLegendRegistryUpdates(REF_TABLE, 'NEWKEY', sandbox.legend, 'tester', 'now')));
}

// --- 5b. Opening a map that claims NOTHING leaves a paintable palette -------------------
{
  seedEmpty();
  sandbox.applyRegistryRowsToLegend([]);                // empty map, empty registry scope
  rec('empty-map/screen', 'palette is not empty', true, sandbox.legend.length > 0);
  rec('empty-map/screen', 'and it is exactly the one empty row', 1, sandbox.legend.length);
  const ups = sandbox.buildLegendRegistryUpdates(REF_TABLE, 'EMPTYKEY', sandbox.legend, 'tester', 'now');
  rec('empty-map/write', 'nothing is written', [], payloadValues(ups));
}

// --- 5c. FRAME ROUND TRIP. Provenance must survive cloneLegend --------------------------
{
  seedEmpty();
  const restored = sandbox.cloneLegend(sandbox.legend);
  rec('frame-round-trip', 'still unclaimed after clone', true, restored.every(l => l.vocab === true));
  rec('frame-round-trip', 'nothing became writable', [],
    payloadValues(sandbox.buildLegendRegistryUpdates(REF_TABLE, 'ANY', restored, 'tester', 'now')));
  seedEmpty(['1']);
  sandbox.reconcileVocabClaims();
  rec('frame-round-trip', 'a claimed row survives the clone as claimed', ['1'],
    payloadValues(sandbox.buildLegendRegistryUpdates(REF_TABLE, 'ANY', sandbox.cloneLegend(sandbox.legend), 'tester', 'now')));
  // and the zones survive a deep copy rather than being shared with the snapshot
  seedEmpty();
  sandbox.legend[0].mat_mid = ['M_01'];
  const clone = sandbox.cloneLegend(sandbox.legend);
  clone[0].mat_mid.push('M_02');
  rec('frame-round-trip', 'clone does not share the zone arrays', ['M_01'], sandbox.legend[0].mat_mid);
}

// --- 5d. THE BYPASSED GATE. The redesign added a whole second table of edit paths.
//         `vocab` is cleared explicitly by updateLegendRowForPanel, but if the mark were
//         the ONLY mechanism, any new path that forgot it would leave the user's typing on
//         screen and drop it from the save - visible, plausible, wrong. So the claim is
//         also DERIVED: a row that no longer matches what it was seeded as is claimed,
//         whether or not anybody said so.
{
  seedEmpty();
  rec('bypassed-gate', 'starts unclaimed', 1, sandbox.legend.filter(l => l.vocab).length);
  const r = sandbox.legend[0];
  r.desc = 'user typed this and the gate did not fire';
  rec('bypassed-gate', 'mark is still (wrongly) set', true, r.vocab === true);
  sandbox.reconcileVocabClaims();
  rec('bypassed-gate', 'the edit is detected anyway', false, r.vocab);
  rec('bypassed-gate', 'and it reaches the payload', ['1'],
    payloadValues(sandbox.buildLegendRegistryUpdates(REF_TABLE, 'K', sandbox.legend, 'tester', 'now')));
}

// --- 5e. EVERY PERSISTED FIELD COUNTS AS AN EDIT. 🔴 This is the group the zone rewrite
//         made critical: the new model added four columns (`stack`, `mat_1h`, `mat_mid`,
//         `mat_top`), and a signature that covered only the old ones would make an edit to
//         a LAYER STRUCTURE invisible to the derived claim - which is the single field
//         this whole panel exists to edit.
//
//         The field list is taken from the PRODUCT's `LEGEND_PAYLOAD_COLUMNS`, not typed
//         here, so adding a column without a mutation for it fails this file rather than
//         passing it silently.
{
  const MUTATE = {
    value: r => { r.value = 'RENAMED'; },
    split_desc: r => { r.desc = 'x'; },
    color: r => { r.color = '#123456'; },
    knobs: r => { r.knobs = [{ k: 'temp', v: '200' }]; },
    stack: r => { r.stack = 16; },
    mat_1h: r => { r.mat_1h = ['H_01']; },
    mat_mid: r => { r.mat_mid = ['M_01']; },
    mat_top: r => { r.mat_top = ['T_01']; },
  };
  const cols = sandbox.LEGEND_PAYLOAD_COLUMNS;
  const uncovered = cols.filter(c => !MUTATE[c]);
  if (uncovered.length > 0) {
    die(`LEGEND_PAYLOAD_COLUMNS gained ${uncovered.join(', ')} with no mutation here. A persisted column that this file cannot mutate is a column whose edit the derived claim may not detect - and an undetected edit is shown on screen and dropped from the save.`);
  }
  for (const c of cols) {
    seedEmpty();
    const r = sandbox.legend[0];
    MUTATE[c](r);
    sandbox.reconcileVocabClaims();
    rec('bypassed-gate/fields', `editing ${c} claims the row`, false, r.vocab);
  }
  seedEmpty();
  sandbox.reconcileVocabClaims();
  rec('bypassed-gate/fields', 'no edit -> nothing claimed', 1, sandbox.legend.filter(l => l.vocab).length);
}

// --- 5f. The seed snapshot must survive a frame round trip alongside the legend ----------
{
  seedEmpty();
  const framedLegend = sandbox.cloneLegend(sandbox.legend);
  const framedSeed = new Map(sandbox.legendVocabularySeed);
  sandbox.legend = framedLegend;
  sandbox.legendVocabularySeed = framedSeed;
  sandbox.reconcileVocabClaims();
  rec('frame-round-trip', 'seed survives, so nothing is falsely claimed', 1, sandbox.legend.filter(l => l.vocab).length);
  sandbox.legend[0].mat_mid = ['edited after the round trip'];
  sandbox.reconcileVocabClaims();
  rec('frame-round-trip', 'edits are still detected after restore', 0, sandbox.legend.filter(l => l.vocab).length);
}

// --- 5g. THE ZONE COLUMN GATE. 🔴 The most destructive path in this file.
//
//   `stack`/`mat_*` are DECLARED in product_tables.py but the physical ALTER is a separate
//   step. If they are not there yet, crud.py drops them from the payload - and this write
//   is `replace_map`, so the scope is replaced by rows carrying desc/color/knobs and NO
//   LAYER STRUCTURE. The screen still looks right until the next load. That is the whole
//   plan, deleted, under a green "자동 저장" chip.
{
  seedEmpty();
  sandbox.zoneColumnsPresent = null;
  sandbox.STUB.zoneBody = ZONE_PROBE_MISSING;
  sandbox.STUB.mapKey = 'FRESHKEY';
  sandbox.STUB.body = { total: 0, data: [] };
  sandbox.STUB.writes = [];
  sandbox.legendReplaceScope = null;
  sandbox.legendConflict = null;
  sandbox.legend[0].desc = 'typed';

  // the product warns to console on this path by design; muted so a green run is quiet.
  // 🔴 The REAL console: an imported module resolves `console` as a global, so muting it on
  //    the env would be a silent no-op and the warning would print on a green run.
  const realWarn = console.warn; console.warn = () => {};
  const blocked = await sandbox.saveLegendToServer('FRESHKEY');
  console.warn = realWarn;
  rec('zone-gate', 'the save is refused', false, blocked.ok);
  rec('zone-gate', 'and says which guard fired', 'zone-columns-missing', blocked.reason);
  rec('zone-gate', '🔴 NOTHING was written', 0, sandbox.STUB.writes.length);

  // The guard must not be permanent: the moment the column appears, saving resumes on its
  // own. A guard that never releases is an outage.
  sandbox.zoneColumnsPresent = null;
  sandbox.STUB.zoneBody = ZONE_PROBE_OK;
  const ok = await sandbox.saveLegendToServer('FRESHKEY');
  rec('zone-gate', 'it releases once the columns exist', true, ok.ok);
  rec('zone-gate', 'and then exactly one PUT goes out', 1, sandbox.STUB.writes.length);
}

// --- 5h. THE REAL WRITE PATH, end to end. Everything above tests pieces; this runs
//         `saveLegendToServer` itself, so the placement of reconcileVocabClaims and the
//         fingerprint that becomes the next save's baseline are asserted rather than
//         mirrored. Mirroring is what let a fingerprint mutation pass unnoticed.
//
//         The observable consequence of getting the fingerprint wrong is not a wrong
//         number - it is that the NEXT save reports "다른 사람이 이 계획을 변경했습니다"
//         with nobody else there. So that is what this asserts.
{
  const asReadBack = updates => ({
    total: updates.length,
    data: updates.map(u => ({ data: {
      map_key: cell(u.updates.map_key), value: cell(u.updates.value),
      split_desc: cell(u.updates.split_desc), color: cell(u.updates.color),
      knobs: cell(u.updates.knobs), stack: cell(u.updates.stack),
      mat_1h: cell(u.updates.mat_1h), mat_mid: cell(u.updates.mat_mid), mat_top: cell(u.updates.mat_top),
      eventtime: cell(u.updates.eventtime), updated_at: cell(u.updates.eventtime),
    } })),
  });

  seedEmpty();
  sandbox.zoneColumnsPresent = true;
  sandbox.STUB.zoneBody = ZONE_PROBE_OK;
  sandbox.STUB.mapKey = 'FRESHKEY';
  sandbox.STUB.body = { total: 0, data: [] };
  sandbox.STUB.writes = [];
  sandbox.legendReplaceScope = null;
  sandbox.legendConflict = null;

  // 🔴 an edit path that forgot the gate, and it edits a ZONE - the field the redesign
  //    added. Under a signature that still only covered desc/color/bands this row would be
  //    shown as edited and silently left out of the save.
  sandbox.legend[0].mat_mid = ['M_01'];

  const r1 = await sandbox.saveLegendToServer('FRESHKEY');
  rec('write-path', 'first save succeeds', true, r1.ok);
  rec('write-path', 'exactly one PUT', 1, sandbox.STUB.writes.length);
  const put = sandbox.STUB.writes[0] || { updates: [] };
  rec('write-path', 'replace_map is set', true, put.replace_map === true);
  rec('write-path', 'payload carries the zone-edited row', ['1'], payloadValues(put.updates));
  rec('write-path', 'and the zone edit itself is in it', '["M_01"]',
    (put.updates[0] || { updates: {} }).updates.mat_mid);
  rec('write-path', 'reported count matches the payload', 1, r1.count);

  // Now the second save. The server holds exactly what we just sent.
  sandbox.STUB.body = asReadBack(put.updates);
  sandbox.STUB.writes = [];
  const r2 = await sandbox.saveLegendToServer('FRESHKEY');
  rec('write-path', 'second save is NOT a phantom conflict', undefined, r2.reason === 'conflict' ? 'conflict' : undefined);
  rec('write-path', 'second save succeeds', true, r2.ok);
  rec('write-path', 'and still writes only the claimed row', ['1'],
    payloadValues((sandbox.STUB.writes[0] || { updates: [] }).updates));
  sandbox.STUB.mapKey = null;
}

// --- 6. FINGERPRINT. The post-save baseline must cover the SAME set that was written -----
{
  seedEmpty();
  sandbox.applyRegistryRowsToLegend(sandbox.parseLegendRegistryRows(SCOPED_B, false));
  const nowStr = '2026-07-27 21:00:00';
  const ups = sandbox.buildLegendRegistryUpdates(REF_TABLE, 'MAPB', sandbox.legend, 'tester', nowStr);
  // what the server now holds, read back through the same parser
  const readBack = ups.map(u => ({
    value: u.updates.value, desc: u.updates.split_desc, color: u.updates.color,
    knobs: sandbox.normalizeKnobs(JSON.parse(u.updates.knobs)),
    stack: u.updates.stack,
    mat_1h: JSON.parse(u.updates.mat_1h), mat_mid: JSON.parse(u.updates.mat_mid), mat_top: JSON.parse(u.updates.mat_top),
    eventtime: nowStr,
  }));
  const sent = sandbox.legend
    .filter(item => ups.some(u => String(u.updates.value) === String(item.value)))
    .map(item => ({ ...item, eventtime: nowStr }));
  rec('fingerprint', 'baseline equals what the server holds',
    sandbox.registryFingerprint(readBack), sandbox.registryFingerprint(sent));
  // 🔴 AND IT MUST DISCRIMINATE ON A ZONE. A fingerprint blind to the layer structure would
  //    make two different plans look identical and let a concurrent overwrite through.
  const moved = readBack.map(r => ({ ...r, mat_mid: r.mat_mid.concat(['EXTRA']) }));
  rec('fingerprint', 'a changed MID changes the fingerprint', true,
    sandbox.registryFingerprint(moved) !== sandbox.registryFingerprint(readBack));
  const restacked = readBack.map(r => ({ ...r, stack: String(Number(r.stack || 0) + 1) }));
  rec('fingerprint', 'a changed STACK changes the fingerprint', true,
    sandbox.registryFingerprint(restacked) !== sandbox.registryFingerprint(readBack));
}

// ---------------------------------------------------------------------------
if (JSON_OUT) {
  console.log(JSON.stringify({ compared, failed: failures.length, failures }, null, 2));
} else if (failures.length === 0) {
  console.log(`legend map-key scope: OK (${compared} assertions)`);
  console.log('registry requests issued (evidence):');
  for (const [who, f] of REQUESTS) console.log(`  ${who.padEnd(24)} ${JSON.stringify(f)}`);
} else {
  console.log(`legend map-key scope: ${failures.length} VIOLATION(S) of ${compared} assertions\n`);
  for (const f of failures) {
    console.log(`  [${f.scenario}] ${f.field}`);
    console.log(`      expected: ${JSON.stringify(f.expected)}`);
    console.log(`      actual  : ${JSON.stringify(f.actual)}`);
  }
  console.log('\nA legend row whose value belongs to another map key must never reach a');
  console.log('`replace_map` payload: that write IS the opened map\'s whole plan.');
}
process.exit(failures.length === 0 ? 0 : 1);
