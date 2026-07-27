/**
 * Legend map-key scope contract.
 *
 * THE ASSERTION NOBODY HAD: when a map is open, the legend on screen - and above all the
 * `replace_map` payload built from it - contains ONLY values that this map vouches for.
 *
 * Why this file exists. `map_split_registry` rows are keyed (ref_table, map_key, value).
 * The map editor seeds the legend with a TABLE-WIDE read (no map_key filter, deduped by
 * value across every map key in the table) so the user has the table's value vocabulary
 * as brushes before any map is chosen. That is a feature. The defect was that nothing
 * downstream could tell a vocabulary row from a row this map actually owns, so opening a
 * map and saving wrote another map's values into it - a `replace_map` write, so it also
 * became that map's whole plan. One value ("elle", defined in bonding_map|TEST_MAP_01)
 * had spread to four bonding_map keys in production by the time it was reported.
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
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const SRC_PLAN = join(ROOT, 'client2', 'src', 'transfer_plan.js');
const SRC_EDITOR = join(ROOT, 'client2', 'src', 'map_editor.js');
const JSON_OUT = process.argv.includes('--json');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

/** Slice `[async] function NAME(...) { ... }` out of source by brace matching. */
function extractFunction(source, name, file) {
  const decl = new RegExp(`(^|\\n)\\s*(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = decl.exec(source);
  if (!m) die(`could not extract function '${name}' from ${file} - it was renamed, removed, or reshaped. Update this harness deliberately; do not delete the check.`);
  const start = m.index + (m[1] ? m[1].length : 0);
  let i = source.indexOf('{', m.index + m[0].length - 1);
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

const NEEDED_EDITOR = [
  'parseJsonCol', 'normalizeKnobs', 'knobsToObject', 'serializeBands', 'serializeKnobs',
  'normalizeLegendItem', 'cloneLegend', 'normalizeBands',
  'parseLegendRegistryRows',        // GET response -> registry rows (dedupe flag = table-wide mode)
  'legendRowSignature',             // the one normal form the derived claim compares
  'reconcileVocabClaims',           // claim = painted OR differs from the borrowed seed
  'fetchRegistryRows',              // the two named scopes - the request itself is asserted
  'readRegistryScope',              // map scope wrapper (load + save both go through it)
  'loadLegendVocabulary',           // the table-wide seed - must mark everything it seeds
  'applyRegistryRowsToLegend',      // this map's rows -> on-screen legend
  'buildLegendRegistryUpdates',     // on-screen legend -> `replace_map` payload
  'saveLegendToServer',             // the real write path: scope + authority + fingerprint
  'buildSplitKey', 'canonRegistryRow', 'registryFingerprint',
];

// DEFAULT_LEGEND is a multi-line const; take it from source too - applyRegistryRowsToLegend
// falls back to it when a map claims nothing, and a re-typed copy would test a fiction.
function extractDefaultLegend(source) {
  const m = /(^|\n)\s*const\s+DEFAULT_LEGEND\s*=\s*\[/.exec(source);
  if (!m) die("could not extract const 'DEFAULT_LEGEND' from map_editor.js");
  let i = source.indexOf('[', m.index), depth = 0;
  for (; i < source.length; i++) {
    if (source[i] === '[') depth++;
    else if (source[i] === ']') { depth--; if (depth === 0) return `const DEFAULT_LEGEND = ${source.slice(source.indexOf('[', m.index), i + 1)};`; }
  }
  die("unbalanced brackets while extracting 'DEFAULT_LEGEND'");
}

const pieces = [
  extractConst(editorSrc, 'SPLIT_KEY_SEP', 'map_editor.js'),
  extractConst(editorSrc, 'FP_UNIT', 'map_editor.js'),
  extractConst(editorSrc, 'FP_ROW', 'map_editor.js'),
  extractConst(editorSrc, 'SPLIT_REGISTRY_TABLE', 'map_editor.js'),
  extractConst(editorSrc, 'REGISTRY_SCOPES', 'map_editor.js'),
  extractDefaultLegend(editorSrc),
  extractFunction(planSrc, 'bandToState', 'transfer_plan.js'),   // normalizeBands calls it
  ...NEEDED_EDITOR.map(n => extractFunction(editorSrc, n, 'map_editor.js')),
];

// Module state the extracted functions read/write. `legend` is the on-screen legend;
// `gridData` is the painted map ("x_y" -> value), which is how a map claims a value.
const sandbox = { legend: [], legendMeta: {}, activeBrush: '', gridData: {}, legendVocabularySeed: new Map(), console };
vm.createContext(sandbox);
try {
  // The real `fetchRegistryRows` runs: only the socket underneath it is stubbed. That way
  // the URL it builds - specifically whether it carries a `map_key` filter - is evidence,
  // not an assumption. `STUB.urls` is the request list this harness reports on.
  // `saveLegendToStorage` / `loadLegendFromStorage` are localStorage and are stubbed.
  vm.runInContext(
    'var API_BASE = "http://harness";\n'
    + 'var CURRENT_USER = "tester";\n'
    + 'var selectedTable = "bonding_map";\n'
    + 'var legendReplaceScope = null, legendConflict = null;\n'
    + 'var legendSaveState = { status: "idle", at: "", error: "" };\n'
    + 'var STUB = { urls: [], writes: [], body: { total: 0, data: [] }, httpOk: true, mapKey: null };\n'
    + 'async function fetch(url, init){ const m = ((init && init.method) || "GET").toUpperCase();\n'
    + '  if (m === "GET") { STUB.urls.push(String(url)); return { ok: STUB.httpOk, status: STUB.httpOk ? 200 : 500, json: async () => STUB.body }; }\n'
    + '  STUB.writes.push(JSON.parse(init.body)); return { ok: true, status: 200, json: async () => ({}) }; }\n'
    + 'function getCurrentMapKey(){ return STUB.mapKey; }\n'
    + 'function getLocalTimeString(){ return "2026-07-27 21:00:00"; }\n'
    + 'function renderLegendTable(){} function renderGridCanvas(){} function renderLegendMetaOnly(){}\n'
    + 'function saveLegendToStorage(){}\n'
    + 'function loadLegendFromStorage(){ legend = cloneLegend(DEFAULT_LEGEND); activeBrush = legend.length ? legend[0].value : ""; }\n'
    + pieces.join('\n'), sandbox);
} catch (e) {
  die(`extracted sources did not evaluate: ${e && e.message}`);
}
for (const fn of ['bandToState', ...NEEDED_EDITOR]) {
  if (typeof sandbox[fn] !== 'function') die(`'${fn}' did not evaluate to a function`);
}

// ---------------------------------------------------------------------------
// Fixture. Two map keys in ONE table with OVERLAPPING and DISJOINT values, and an
// updated_at ordering that makes MAPA win every collision - so the table-wide dedupe
// hands MAPA's desc/color/bands to a shared value and hands over MAPA's exclusive
// values wholesale. A fixture where the two maps share a value set, or where MAPB is
// the newest everywhere, cannot show this defect at all.
// ---------------------------------------------------------------------------
const cell = v => (v === undefined ? undefined : { value: v, is_overwrite: false, priority_source: 'user', updated_by: 'tester' });
const row = (mapKey, value, desc, color, bands, updatedAt) => ({
  data: {
    map_key: cell(mapKey), value: cell(value), split_desc: cell(desc), color: cell(color),
    knobs: cell('{}'), bands: cell(JSON.stringify(bands || [])),
    eventtime: cell(updatedAt), updated_at: cell(updatedAt),
  },
});

const MAPA_ROWS = [
  row('MAPA', '1', 'A: thickness down', '#10b981', [{ seq: 1, to: 3, materials: ['LOT_A1'] }], '2026-07-27 20:57:03'),
  row('MAPA', '2', 'A: POR',            '#ef4444', [{ seq: 1, to: 5, materials: ['LOT_A2'] }], '2026-07-27 20:57:03'),
  row('MAPA', 'A_ONLY',  'A exclusive split',  '#3b82f6', [{ seq: 1, to: 9, materials: ['LOT_A3'] }], '2026-07-27 20:57:03'),
  row('MAPA', 'A_ONLY2', 'A exclusive split 2', '#ec4899', [], '2026-07-27 20:57:03'),
];
const MAPB_ROWS = [
  row('MAPB', '1',      'B: thickness x2', '#f59e0b', [{ seq: 1, to: 7, materials: ['LOT_B1'] }], '2026-07-26 09:00:00'),
  row('MAPB', 'B_ONLY', 'B exclusive split', '#8b5cf6', [{ seq: 1, to: 2, materials: ['LOT_B2'] }], '2026-07-26 09:00:00'),
];
const TABLE_WIDE = { total: 6, data: [...MAPA_ROWS, ...MAPB_ROWS] };
const SCOPED_B   = { total: 2, data: MAPB_ROWS };

const REF_TABLE = 'bonding_map';
const failures = [];
let compared = 0;
const rec = (scenario, field, expected, actual) => {
  compared++;
  if (JSON.stringify(expected) !== JSON.stringify(actual)) failures.push({ scenario, field, expected, actual });
};
const values = arr => arr.map(l => String(l.value)).sort();
const payloadValues = ups => ups.map(u => String(u.updates.value)).sort();

// Seed the legend the way switchTable does: the deliberate table-wide vocabulary read.
// `vocab: true` is the provenance marker the fix introduces; on the defective version the
// field simply does not exist, which is exactly why nothing downstream could filter.
// Seed through the PRODUCT's loader, never by hand. Hand-marking rows here would fake the
// `vocab` flag and the seed snapshot together, and the derived-claim machinery below would
// be tested against a fixture instead of against the app.
async function seedVocabulary(painted) {
  sandbox.STUB.body = TABLE_WIDE;
  sandbox.STUB.httpOk = true;
  await sandbox.loadLegendVocabulary(REF_TABLE);
  // the map's painted cells - the other way a map claims a value
  sandbox.gridData = {};
  (painted || []).forEach((v, i) => { sandbox.gridData[`${i}_0`] = v; });
}

// --- 0. the dedupe itself: MAPA must win every collision (fixture is live) ------------
{
  const vocab = sandbox.parseLegendRegistryRows(TABLE_WIDE, true);
  rec('vocabulary-read', 'values', ['1', '2', 'A_ONLY', 'A_ONLY2', 'B_ONLY'], values(vocab));
  const one = vocab.find(r => r.value === '1');
  rec('vocabulary-read', 'shared value "1" resolves to the newest map key', 'MAPA', one && one.map_key);
  rec('vocabulary-read', 'shared value "1" carries the OTHER map\'s desc', 'A: thickness down', one && one.desc);
  if (values(vocab).length === values(sandbox.parseLegendRegistryRows(SCOPED_B, false)).length) {
    die('fixture is inert: the table-wide read and the map-scoped read produce the same number of values, so no scope defect could ever show.');
  }
}

// --- 0b. THE SEED ITSELF. The product's table-wide loader must (a) ask for the
//         'vocabulary' scope by name and (b) mark every row it puts on screen. If it
//         marks nothing, every filter downstream is a no-op and this whole file is
//         theatre - so this is asserted against the real function, not assumed.
const filterOf = url => JSON.parse(decodeURIComponent(String(url).split('filters=')[1] || '%7B%7D'));
const REQUESTS = [];   // the request list this harness reports as evidence
{
  sandbox.STUB.body = TABLE_WIDE;
  sandbox.STUB.urls = [];
  const src = await sandbox.loadLegendVocabulary(REF_TABLE);
  REQUESTS.push(['loadLegendVocabulary', filterOf(sandbox.STUB.urls[0])]);
  rec('vocabulary-seed', 'source', 'server', src);
  rec('vocabulary-seed', 'request carries NO map_key filter', ['ref_table'], Object.keys(filterOf(sandbox.STUB.urls[0])).sort());
  rec('vocabulary-seed', 'every seeded row is marked unclaimed', true, sandbox.legend.every(l => l.vocab === true));
  rec('vocabulary-seed', 'seeded values', ['1', '2', 'A_ONLY', 'A_ONLY2', 'B_ONLY'], values(sandbox.legend));
  rec('vocabulary-seed', 'nothing seeded is writable', [],
    payloadValues(sandbox.buildLegendRegistryUpdates(REF_TABLE, 'ANY', sandbox.legend, 'tester', 'now')));
  // the offline fallback is table-scoped too, so it must be marked as well
  // (the product warns to console on this path by design; muted so a green run is quiet)
  sandbox.STUB.httpOk = false;
  const realWarn = sandbox.console.warn; sandbox.console.warn = () => {};
  const src2 = await sandbox.loadLegendVocabulary(REF_TABLE);
  sandbox.console.warn = realWarn;
  rec('vocabulary-seed', 'offline fallback source', 'offline', src2);
  rec('vocabulary-seed', 'cache/DEFAULT fallback is marked too', true, sandbox.legend.every(l => l.vocab === true));
  sandbox.STUB.httpOk = true;
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
  // The map scope must NOT dedupe. Dedupe is the vocabulary mode's collapse across map
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

  // truncation stays a failure, not a smaller answer (a partial read backing replace_map deletes)
  sandbox.STUB.body = { total: 99, data: MAPB_ROWS };
  const trunc = await sandbox.readRegistryScope(REF_TABLE, 'MAPB');
  rec('map-scoped-read', 'truncated response is a failure', false, trunc.ok);
}

// --- 1. SCREEN. Open MAPB after a vocabulary seed -> only MAPB's values --------------
{
  await seedVocabulary();
  const before = values(sandbox.legend);
  sandbox.applyRegistryRowsToLegend(sandbox.parseLegendRegistryRows(SCOPED_B, false));
  rec('open-mapB/screen', 'legend values', ['1', 'B_ONLY'], values(sandbox.legend));
  const one = sandbox.legend.find(l => String(l.value) === '1');
  rec('open-mapB/screen', 'shared value desc comes from MAPB', 'B: thickness x2', one && one.desc);
  rec('open-mapB/screen', 'shared value bands come from MAPB', [{ seq: 1, to: 7, materials: ['LOT_B1'] }], one && one.bands);
  // The blast radius number: how many legend entries differ between the two readings.
  // If this is 0 the fixture proved nothing.
  const foreign = before.filter(v => !['1', 'B_ONLY'].includes(v));
  if (foreign.length === 0) die('fixture is inert: the vocabulary seed carried no foreign values.');
}

// --- 2. WRITE. The `replace_map` payload for MAPB must not carry MAPA's values --------
{
  await seedVocabulary();
  sandbox.applyRegistryRowsToLegend(sandbox.parseLegendRegistryRows(SCOPED_B, false));
  const ups = sandbox.buildLegendRegistryUpdates(REF_TABLE, 'MAPB', sandbox.legend, 'tester', '2026-07-27 21:00:00');
  rec('open-mapB/write', 'replace_map payload values', ['1', 'B_ONLY'], payloadValues(ups));
  rec('open-mapB/write', 'every row is scoped to MAPB', true, ups.every(u => u.updates.map_key === 'MAPB'));
  rec('open-mapB/write', 'split_key set', ['bonding_map|MAPB|1', 'bonding_map|MAPB|B_ONLY'],
    ups.map(u => u.business_key_val).sort());
}

// --- 3. WRITE, no map ever opened. A fresh key must not inherit the vocabulary --------
// This is the path that created bonding_map|A23, |b1, |aa123_a in production: pick a
// table, type a NEW map key, edit anything, and the debounced save fires with the
// vocabulary as its payload. `replace_map` on an empty scope deletes nothing, so the
// truncation/authority guards all pass - and a whole plan appears out of nowhere.
{
  await seedVocabulary();
  const ups = sandbox.buildLegendRegistryUpdates(REF_TABLE, 'NEWKEY', sandbox.legend, 'tester', '2026-07-27 21:00:00');
  rec('fresh-key/write', 'replace_map payload values', [], payloadValues(ups));
}

// --- 4. NO REGRESSION. Everything the map actually vouches for is still written -------
// (a) rows from this map's own registry; (b) a value the user explicitly edited;
// (c) a value the map's own cells carry (the caller clears `vocab` for painted values).
{
  // (c) MAPB's own cells carry '2' - a value MAPB's registry does not have. The map itself
  //     vouches for it, so it must survive the open AND be written.
  await seedVocabulary(['1', '2']);
  sandbox.applyRegistryRowsToLegend(sandbox.parseLegendRegistryRows(SCOPED_B, false));
  rec('vouched/screen', 'a painted-but-unregistered value stays on screen', true,
    sandbox.legend.some(l => String(l.value) === '2'));
  // (b) user adds a value in the panel - addLegendRowForPanel builds it without `vocab`
  sandbox.legend.push(sandbox.normalizeLegendItem({ value: 'D1', desc: 'typed by user', color: '#14b8a6' }));
  const ups = sandbox.buildLegendRegistryUpdates(REF_TABLE, 'MAPB', sandbox.legend, 'tester', '2026-07-27 21:00:00');
  rec('vouched/write', 'payload values', ['1', '2', 'B_ONLY', 'D1'], payloadValues(ups));
  const b = ups.find(u => u.updates.value === 'B_ONLY');
  rec('vouched/write', 'B_ONLY bands survive the round trip',
    JSON.stringify([{ seq: 1, to: 2, materials: ['LOT_B2'] }]), b && b.updates.bands);
  // the painted-but-unregistered value must NOT carry the other map's DOE
  const two = ups.find(u => u.updates.value === '2');
  rec('vouched/write', 'painted value does not inherit MAPA\'s bands', '[]', two && two.updates.bands);
}

// --- 5. A painted vocabulary value IS written (fresh key, nothing opened) -------------
// saveLegendToServer calls reconcileVocabClaims before building the payload.
{
  await seedVocabulary(['2']);                                // user painted cells with brush '2'
  sandbox.reconcileVocabClaims();
  const ups = sandbox.buildLegendRegistryUpdates(REF_TABLE, 'NEWKEY', sandbox.legend, 'tester', '2026-07-27 21:00:00');
  rec('fresh-key/painted', 'only the painted value is written', ['2'], payloadValues(ups));
}

// --- 5b. Opening a map that claims NOTHING leaves a paintable palette -----------------
// Eviction must not hand the user an empty brush list; the generic defaults come back,
// still unclaimed so still unwritten.
{
  await seedVocabulary();
  sandbox.applyRegistryRowsToLegend([]);                // empty map, empty registry scope
  rec('empty-map/screen', 'palette is not empty', true, sandbox.legend.length > 0);
  rec('empty-map/screen', 'no foreign value survived', [],
    sandbox.legend.map(l => String(l.value)).filter(v => ['A_ONLY', 'A_ONLY2', 'B_ONLY'].includes(v)));
  const ups = sandbox.buildLegendRegistryUpdates(REF_TABLE, 'EMPTYKEY', sandbox.legend, 'tester', '2026-07-27 21:00:00');
  rec('empty-map/write', 'nothing is written', [], payloadValues(ups));
}

// --- 5c. FRAME ROUND TRIP. Provenance must survive cloneLegend -----------------------
// snapshotEditorState stores `legend: cloneLegend(legend)` and restoreEditorState puts it
// back, so opening a material map in a sub-frame and coming back runs every legend row
// through the normal form. If the mark does not survive that, the parent map's borrowed
// brushes silently become writable again - contamination one round trip later.
{
  await seedVocabulary();
  const restored = sandbox.cloneLegend(sandbox.legend);
  rec('frame-round-trip', 'every row is still unclaimed after clone', true, restored.every(l => l.vocab === true));
  rec('frame-round-trip', 'nothing became writable', [],
    payloadValues(sandbox.buildLegendRegistryUpdates(REF_TABLE, 'ANY', restored, 'tester', 'now')));
  // and a claimed row must stay claimed across the same trip
  await seedVocabulary(['2']);
  sandbox.reconcileVocabClaims();
  rec('frame-round-trip', 'a claimed row survives the clone as claimed', ['2'],
    payloadValues(sandbox.buildLegendRegistryUpdates(REF_TABLE, 'ANY', sandbox.cloneLegend(sandbox.legend), 'tester', 'now')));
}

// --- 5d. THE BYPASSED GATE. This is the one that decides whether the fix survives the
//         DOE redesign. `vocab` is cleared explicitly by updateLegendRowForPanel, but the
//         redesign adds a second table of edit paths. If the mark were the ONLY mechanism,
//         any new path that forgot it would leave the user's typing on screen and drop it
//         from the save - visible, plausible, wrong. So the claim is also DERIVED: a row
//         that no longer matches the vocabulary row it was borrowed from is claimed,
//         whether or not anybody said so.
{
  await seedVocabulary();
  const before = sandbox.legend.filter(l => l.vocab).length;
  rec('bypassed-gate', 'everything starts unclaimed', 5, before);

  // an edit path that FORGOT the gate: mutate the row, never touch `vocab`
  const row = sandbox.legend.find(l => String(l.value) === 'A_ONLY');
  row.desc = 'user typed this and the gate did not fire';
  rec('bypassed-gate', 'mark is still (wrongly) set', true, row.vocab === true);

  sandbox.reconcileVocabClaims();
  rec('bypassed-gate', 'the edit is detected anyway', false, row.vocab);
  rec('bypassed-gate', 'and it reaches the payload', ['A_ONLY'],
    payloadValues(sandbox.buildLegendRegistryUpdates(REF_TABLE, 'K', sandbox.legend, 'tester', 'now')));

  // and the rows nobody touched are NOT swept up with it
  rec('bypassed-gate', 'untouched rows stay unclaimed', 4, sandbox.legend.filter(l => l.vocab).length);
}

// --- 5e. Every editable field counts as an edit, not just desc. A signature that ignored
//         bands would miss exactly the field this whole DOE panel exists to edit.
{
  for (const [field, mutate] of [
    ['desc', r => { r.desc = 'x'; }],
    ['color', r => { r.color = '#123456'; }],
    ['bands', r => { r.bands = [{ seq: 1, to: 4, materials: ['M9'] }]; }],
    ['knobs', r => { r.knobs = [{ k: 'temp', v: '200' }]; }],
    ['value', r => { r.value = 'RENAMED'; }],
  ]) {
    await seedVocabulary();
    const row = sandbox.legend.find(l => String(l.value) === 'A_ONLY2');
    mutate(row);
    sandbox.reconcileVocabClaims();
    rec('bypassed-gate/fields', `editing ${field} claims the row`, false, row.vocab);
  }
  // control: touching nothing must NOT claim
  await seedVocabulary();
  sandbox.reconcileVocabClaims();
  rec('bypassed-gate/fields', 'no edit -> nothing claimed', 5, sandbox.legend.filter(l => l.vocab).length);
}

// --- 5f. The seed must survive a frame round trip alongside the legend it describes.
//         If it did not, coming back from a material map would leave marked rows with no
//         seed - and a marked row with no seed reads as edited, claiming everything.
{
  await seedVocabulary();
  const framedLegend = sandbox.cloneLegend(sandbox.legend);
  const framedSeed = new Map(sandbox.legendVocabularySeed);   // what snapshotEditorState stores
  sandbox.legend = framedLegend;
  sandbox.legendVocabularySeed = framedSeed;                  // what restoreEditorState puts back
  sandbox.reconcileVocabClaims();
  rec('frame-round-trip', 'seed survives, so nothing is falsely claimed', 5, sandbox.legend.filter(l => l.vocab).length);
  // ...and detection still works on the far side
  sandbox.legend.find(l => String(l.value) === 'B_ONLY').desc = 'edited after the round trip';
  sandbox.reconcileVocabClaims();
  rec('frame-round-trip', 'edits are still detected after restore', 4, sandbox.legend.filter(l => l.vocab).length);
}

// --- 5g. THE REAL WRITE PATH, end to end. Everything above tests pieces; this runs
//         `saveLegendToServer` itself, so the placement of reconcileVocabClaims and the
//         fingerprint that becomes the next save's baseline are asserted rather than
//         mirrored. Mirroring is what let a fingerprint mutation pass unnoticed.
//
//         The observable consequence of getting the fingerprint wrong is not a wrong
//         number - it is that the NEXT save reports "다른 사람이 이 계획을 변경했습니다"
//         with nobody else there. So that is what this asserts.
{
  // one registry row per written value, in the shape a read-back would return
  const asReadBack = updates => ({
    total: updates.length,
    data: updates.map(u => ({ data: {
      map_key: cell(u.updates.map_key), value: cell(u.updates.value),
      split_desc: cell(u.updates.split_desc), color: cell(u.updates.color),
      knobs: cell(u.updates.knobs), bands: cell(u.updates.bands),
      eventtime: cell(u.updates.eventtime), updated_at: cell(u.updates.eventtime),
    } })),
  });

  await seedVocabulary();
  sandbox.STUB.mapKey = 'FRESHKEY';
  sandbox.STUB.body = { total: 0, data: [] };     // FRESHKEY has no rows yet
  sandbox.STUB.writes = [];
  sandbox.legendReplaceScope = null;
  sandbox.legendConflict = null;

  // an edit path that forgot the gate, again - but this time we let the PRODUCT save.
  sandbox.legend.find(l => String(l.value) === 'A_ONLY').desc = 'typed, gate not fired';

  const r1 = await sandbox.saveLegendToServer('FRESHKEY');
  rec('write-path', 'first save succeeds', true, r1.ok);
  rec('write-path', 'exactly one PUT', 1, sandbox.STUB.writes.length);
  const put = sandbox.STUB.writes[0] || { updates: [] };
  rec('write-path', 'replace_map is set', true, put.replace_map === true);
  rec('write-path', 'payload carries ONLY the edited row', ['A_ONLY'], payloadValues(put.updates));
  rec('write-path', 'reported count matches the payload', 1, r1.count);

  // Now the second save. The server holds exactly what we just sent.
  sandbox.STUB.body = asReadBack(put.updates);
  sandbox.STUB.writes = [];
  const r2 = await sandbox.saveLegendToServer('FRESHKEY');
  rec('write-path', 'second save is NOT a phantom conflict', undefined, r2.reason === 'conflict' ? 'conflict' : undefined);
  rec('write-path', 'second save succeeds', true, r2.ok);
  rec('write-path', 'and still writes only the claimed row', ['A_ONLY'],
    payloadValues((sandbox.STUB.writes[0] || { updates: [] }).updates));
  sandbox.STUB.mapKey = null;
}

// --- 6. FINGERPRINT. The post-save baseline must cover the SAME set that was written ---
// saveLegendToServer rebuilds a fingerprint from the legend after a successful write. If
// it fingerprints rows the payload filtered out, the next save sees a phantom conflict and
// refuses - "someone else changed this plan" with nobody else there.
{
  await seedVocabulary();
  sandbox.applyRegistryRowsToLegend(sandbox.parseLegendRegistryRows(SCOPED_B, false));
  const nowStr = '2026-07-27 21:00:00';
  const ups = sandbox.buildLegendRegistryUpdates(REF_TABLE, 'MAPB', sandbox.legend, 'tester', nowStr);
  // what the server now holds, read back through the same parser
  const readBack = ups.map(u => ({
    value: u.updates.value, desc: u.updates.split_desc, color: u.updates.color,
    knobs: sandbox.normalizeKnobs(JSON.parse(u.updates.knobs)),
    bands: sandbox.normalizeBands(JSON.parse(u.updates.bands)),
    eventtime: nowStr,
  }));
  // what saveLegendToServer must fingerprint: only the values it actually sent
  const sent = sandbox.legend
    .filter(item => ups.some(u => String(u.updates.value) === String(item.value)))
    .map(item => ({ value: item.value, desc: (item.desc || '').trim(), color: item.color,
                    knobs: item.knobs, bands: item.bands, eventtime: nowStr }));
  rec('fingerprint', 'baseline equals what the server holds',
    sandbox.registryFingerprint(readBack), sandbox.registryFingerprint(sent));
  // and it must NOT equal a fingerprint taken over the unfiltered legend
  const unfiltered = sandbox.legend.map(item => ({ value: item.value, desc: (item.desc || '').trim(),
    color: item.color, knobs: item.knobs, bands: item.bands, eventtime: nowStr }));
  if (sandbox.registryFingerprint(unfiltered) === sandbox.registryFingerprint(readBack)
      && sandbox.legend.length !== ups.length) {
    failures.push({ scenario: 'fingerprint', field: 'discrimination',
      expected: 'unfiltered fingerprint differs from server state', actual: 'identical' });
    compared++;
  }
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
