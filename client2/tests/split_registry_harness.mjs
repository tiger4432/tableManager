// Split-registry harness — the legend value/desc contract, and the two write paths that
// remain in map_editor.js.
//
// 🔴 THIS FILE WAS DEAD FROM 2026-07-30 TO 2026-09-03, and "the symbols it slices were
//    renamed" was only half the reason. It sliced FOURTEEN names out of map_editor.js as
//    text. Nine of them moved or stayed; FIVE were DELETED FROM THE PRODUCT, so no amount of
//    re-pointing could have revived those assertions — there was nothing left to point at.
//    They are retired below, with an ABSENCE CHECK in their place rather than a comment: a
//    comment cannot notice the day one of them comes back.
//
// It no longer reads its subjects as text (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지).
// `split_registry_row.js` exports what it scores, so that half is a plain import. The three
// names still living inside `map_editor.js` are module-private, so they are reached through
// the probe, which appends to a byte-identical copy and cuts nothing (`lib/probe.mjs`).
//
// Run: node client2/tests/split_registry_harness.mjs
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe } from './lib/probe.mjs';
import {
  buildLegendRegistryUpdates, parseLegendRegistryRows,
  getMissingDescValues, formatLegendMetaText,
} from '../src/split_registry_row.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_DIR = join(HERE, '..', 'src');
const SRC_MAP = join(SRC_DIR, 'map_editor.js');

let pass = 0, fail = 0;
function check(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS ${name}`); }
  else { fail++; console.log(`  FAIL ${name} ${detail}`); }
}
function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

// ═══ T0. THE FIVE RETIRED SUBJECTS — asserted ABSENT, not commented away ═══
//
// These five were the reason this harness died, and each one's removal commit was found
// rather than guessed (verified by counting the declaration before and after):
//
//   DEFAULT_LEGEND            95bf072f  2026-07-28  feat(config): U6 — client hardcoding
//                                                   moved to declarations
//   loadLegendFromStorage     b35bc9fc  2026-07-28  feat(doe): land the zone model end to end
//   fetchLegendFromServer     269b39eb  2026-07-27  fix(map): stop one map's DOE from
//   loadLegend                269b39eb              appearing in every map
//   maybeOfferLegendMigration 4ba13ae3  2026-07-27  feat: isolated dev environment, …
//
// What they scored — the legend LOAD priority (server -> localStorage -> hardcoded default)
// and the one-time migration offer — is not a feature that moved. It was withdrawn:
// `map_editor.js:4605` records the migration prompt's removal (a confirm dialog on a READ
// path, asking about "split registry", an internal word), and the served `default_legend`
// replaced the hardcoded one. The load path now goes through the registry scope.
//
// 🔴 AN ABSENCE IS ASSERTED, NOT NARRATED. If any of these names is declared again, this
//    harness says so on the next run instead of leaving a comment nobody re-reads.
const RETIRED = ['DEFAULT_LEGEND', 'loadLegendFromStorage', 'fetchLegendFromServer',
                 'loadLegend', 'maybeOfferLegendMigration'];
{
  // Comments are stripped because one of the five is MENTIONED in one: `map_editor.js:4605`
  // is the note recording its own deletion, and a raw grep reads that as presence.
  // (The stripper also eats `//` inside string literals. That is harmless here — it can only
  // shorten a string, never manufacture one of the five identifiers.)
  const strip = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
  const files = [];
  (function walk(dir) {
    for (const e of readdirSync(dir)) {
      const p = join(dir, e);
      if (statSync(p).isDirectory()) walk(p);
      else if (e.endsWith('.js')) files.push(p);
    }
  })(SRC_DIR);
  if (files.length < 10) die(`only ${files.length} .js files found under src/ — the walk is `
    + 'broken, and a broken walk makes every absence check pass');
  console.log(`\n[T0] the five retired subjects are absent (${files.length} source files scanned)`);
  for (const name of RETIRED) {
    const re = new RegExp(`\\b${name}\\b`);
    const found = files.filter(f => re.test(strip(readFileSync(f, 'utf8'))));
    check(`${name} is gone from client2/src`, found.length === 0,
      found.map(f => f.slice(SRC_DIR.length + 1)).join(', '));
  }
  // The control. Without it, a stripper that emptied every file would make the five above
  // pass silently — the exact shape of "an instrument goes blind under its own fault".
  const live = files.filter(f => /\bbuildLegendRegistryUpdates\b/.test(strip(readFileSync(f, 'utf8'))));
  check('control: a name that DOES live is found by the same scan', live.length > 0,
    'if this fails the five results above mean nothing');
}

// ═══ T1. buildLegendRegistryUpdates — payload shape / bk assembly ═══
console.log('\n[T1] buildLegendRegistryUpdates');
{
  const legendArr = [
    { value: '1', desc: '  HTOL split A — 1.05V burn-in  ', color: '#10b981' },
    { value: '', desc: 'ghost', color: '#fff' },          // empty value excluded
    { value: 'E1', desc: '', color: '#8b5cf6' },          // empty desc allowed (push gate warns)
  ];
  const ups = buildLegendRegistryUpdates('bonding_map', 'BASE01', legendArr, 'tester', '2026-07-25 12:00:00');
  check('empty value filtered → 2', ups.length === 2, String(ups.length));
  const u0 = ups[0];
  // This is also where SPLIT_KEY_SEP and buildSplitKey are scored. Both are module-private,
  // and they are pinned through the value they produce rather than by reaching in: the
  // separator has to match `composite_key_separator` in server/config/table_config.json, and
  // what the server sees is this string.
  check('bk = ref|map|value (SPLIT_KEY_SEP through its output)',
    u0.business_key_val === 'bonding_map|BASE01|1', u0.business_key_val);
  check('split_key column = the same bk', u0.updates.split_key === u0.business_key_val);
  check('desc trimmed', u0.updates.split_desc === 'HTOL split A — 1.05V burn-in');
  check('composite source columns carried',
    u0.updates.ref_table === 'bonding_map' && u0.updates.map_key === 'BASE01' && u0.updates.value === '1');
  // 🔴 `ref_table` is the MAP's table, never the registry's own. Confusing the two writes
  //    every map's legend under one key — scored against the const itself in T5.
  check('source_name=user / updated_by passed through',
    u0.source_name === 'user' && u0.updated_by === 'tester');
  check('eventtime injected', u0.updates.eventtime === '2026-07-25 12:00:00');
  check('no mapKey → empty', buildLegendRegistryUpdates('bonding_map', null, legendArr, 'u', 'n').length === 0);
  check('no refTable → empty', buildLegendRegistryUpdates('', 'k', legendArr, 'u', 'n').length === 0);
}

// ═══ T2. parseLegendRegistryRows — cell contract / dedupe ═══
console.log('\n[T2] parseLegendRegistryRows');
{
  const mkRow = (value, desc, color, mapKey, by, at) => ({
    data: {
      value: { value, is_overwrite: true, updated_by: by, priority_source: 'user' },
      split_desc: { value: desc, is_overwrite: true, updated_by: by, priority_source: 'user' },
      color: { value: color, is_overwrite: false, updated_by: 'system' },
      map_key: { value: mapKey, is_overwrite: false, updated_by: 'system' },
      updated_at: { value: at, is_overwrite: false, updated_by: 'system' },
    },
  });
  const result = {
    data: [
      mkRow('1', 'old desc', '#111111', 'BASE01', 'alice', '2026-07-20 09:00:00'),
      mkRow('1', 'new desc', '#222222', 'BASE02', 'bob', '2026-07-24 18:30:00'),
      mkRow('0', 'FAIL bin', null, 'BASE01', 'alice', '2026-07-21 10:00:00'),
      mkRow('', 'no value skip', '#333333', 'BASE01', 'x', '2026-07-22 10:00:00'),
    ],
  };
  const noDedupe = parseLegendRegistryRows(result, false);
  check('empty-value row skipped → 3', noDedupe.length === 3, String(noDedupe.length));
  const deduped = parseLegendRegistryRows(result, true);
  check('dedupe → 2', deduped.length === 2, String(deduped.length));
  const v1 = deduped.find(r => r.value === '1');
  check('on a duplicate value the latest updated_at wins',
    v1.desc === 'new desc' && v1.updated_by === 'bob', JSON.stringify(v1));
  const v0 = deduped.find(r => r.value === '0');
  check('color null → fallback #6b7280', v0.color === '#6b7280', v0.color);
  check('updated_by comes from the split_desc cell', v0.updated_by === 'alice');
  check('empty / malformed response is safe',
    parseLegendRegistryRows(null, true).length === 0 && parseLegendRegistryRows({}, false).length === 0);
}

// ═══ T3. getMissingDescValues — the push warning gate ═══
console.log('\n[T3] getMissingDescValues');
{
  const legendArr = [
    { value: '1', desc: 'GOOD split' },
    { value: '0', desc: '   ' },                 // whitespace only → missing
    { value: 2, desc: 'numeric legend value' },  // type mismatch defended (String compare)
  ];
  const missing = getMissingDescValues(['1', '0', '2', '9'], legendArr);
  check('whitespace desc + value absent from the legend are both reported',
    JSON.stringify(missing) === JSON.stringify(['0', '9']), JSON.stringify(missing));
  check('empty input is safe', getMissingDescValues(null, null).length === 0);
}

// ═══ T4. formatLegendMetaText ═══
console.log('\n[T4] formatLegendMetaText');
{
  check('unsaved', formatLegendMetaText(undefined) === '서버 미저장');
  check('meta rendered',
    formatLegendMetaText({ updated_by: 'bob', updated_at: '2026-07-24 18:30:00' })
      === 'bob · 2026-07-24 18:30:00');
}

// ═══ T5. the three that still live inside map_editor.js ═══
//
// Reached through the probe. `saveLegendToServer`'s FULL write path — zone gate, scope
// authority, fingerprint, replace_map payload — is scored end to end by
// `contracts/legend_map_scope/client_harness.mjs` §5g/§5h, which stages the server state
// those guards read. This file deliberately does NOT restate that: a second spelling of the
// same question diverges, and the contract's version is the one with the server beside it.
//
// What is scored here is the part that needs no server state at all, and that the contract
// does not cover: the refusal that happens BEFORE any of those guards run.
console.log('\n[T5] map_editor.js — SPLIT_REGISTRY_TABLE / saveLegendToStorage / saveLegendToServer');
{
  const store = new Map();
  globalThis.localStorage = {
    getItem: k => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: k => store.delete(k),
  };
  globalThis.window = globalThis.window || {
    location: { port: '', origin: '', protocol: 'http:', host: '', search: '' },
    addEventListener() {}, matchMedia: () => ({ matches: false, addEventListener() {} }),
  };
  globalThis.document = globalThis.document || {
    getElementById: () => null, querySelector: () => null, querySelectorAll: () => [],
    addEventListener() {}, removeEventListener() {},
    documentElement: { style: { setProperty() {} } },
    body: { appendChild() {}, classList: { add() {}, remove() {} } },
    createElement: () => ({ style: {}, appendChild() {}, remove() {},
                            classList: { add() {}, remove() {} } }),
  };
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url: String(url), method: (init && init.method) || 'GET' });
    return { ok: true, status: 200, json: async () => ({ data: [], total: 0 }) };
  };

  const { probe } = await loadWithProbe(SRC_MAP, {
    expose: ['SPLIT_REGISTRY_TABLE', 'saveLegendToStorage', 'saveLegendToServer'],
    state: ['selectedTable', 'saveDoeDraft'],
    stubs: {
      './config.js': { API_BASE: 'http://harness', CURRENT_USER: 'tester',
                       MAP_SPEC_SAVE_TIMEOUT_MS: 1000 },
      './utils.js': { showToast: () => {}, getLocalTimeString: () => '2026-09-03 00:00:00' },
    },
    tag: 'splitregistry',
  });

  // ── SPLIT_REGISTRY_TABLE: the REGISTRY's own table, never a map's ──
  check('SPLIT_REGISTRY_TABLE is a single table name, not a per-map one',
    typeof probe.SPLIT_REGISTRY_TABLE === 'string' && probe.SPLIT_REGISTRY_TABLE.length > 0,
    String(probe.SPLIT_REGISTRY_TABLE));
  // 🔴 The defect this guards: writing `ref_table = SPLIT_REGISTRY_TABLE` would file every
  //    map's legend under one key, and the screen would look right until a second map saved.
  const ups = buildLegendRegistryUpdates('bonding_map', 'BASE01',
    [{ value: '1', desc: 'd', color: '#000' }], 'u', 'n');
  check('and a payload names the MAP\'s table in ref_table, not the registry\'s',
    ups[0].updates.ref_table !== probe.SPLIT_REGISTRY_TABLE, ups[0].updates.ref_table);

  // ── saveLegendToStorage: the legacy per-table cache is DROPPED, and the draft is written ──
  // It used to write the legend into `map_legend_<table>`. It now removes that key: the
  // registry is the store and the draft is the only local copy. A version that still wrote
  // the cache would resurrect one map's legend on every other map — the defect 269b39eb fixed.
  {
    let draftCalls = 0;
    probe.saveDoeDraft = () => { draftCalls++; };
    probe.selectedTable = 'bonding_map';
    store.set('map_legend_bonding_map', '[{"value":"STALE"}]');
    probe.saveLegendToStorage();
    check('the legacy per-table legend cache is removed',
      store.has('map_legend_bonding_map') === false);
    check('and the DOE draft is written instead (the local copy that survives a failed save)',
      draftCalls === 1, String(draftCalls));
  }

  // ── saveLegendToServer: refuses before it touches the network ──
  {
    probe.selectedTable = 'bonding_map';
    requests.length = 0;
    const noKey = await probe.saveLegendToServer(null);
    check('no map key → refused', noKey && noKey.ok === false, JSON.stringify(noKey));
    check('and the refusal is NAMED, not a bare false', noKey && noKey.reason === 'no-map-key',
      JSON.stringify(noKey));
    // 🔴 The ordering claim. A refusal that fired AFTER the zone probe would still return
    //    ok:false, so the reason alone cannot tell the two apart — the request count can.
    check('and nothing went to the server: the refusal is reached BEFORE the zone probe',
      requests.length === 0, JSON.stringify(requests));

    // NEGATIVE CONTROL. Same call with a map key gets past that guard and DOES reach the
    // network, so the zero above is a refusal rather than a path nobody walks.
    requests.length = 0;
    // The product warns to console on this path by design (the zone columns are not in this
    // stub's schema); muted so a green run is quiet. The REAL console object is replaced --
    // an imported module resolves `console` as a global, so muting it anywhere else is a
    // silent no-op and the warning prints anyway.
    const realWarn = console.warn; console.warn = () => {};
    const withKey = await probe.saveLegendToServer('BASE01');
    console.warn = realWarn;
    check('negative control: with a map key it goes past the guard and reaches the server',
      requests.length > 0, JSON.stringify(requests.slice(0, 2)));
    check('negative control: and its refusal, if any, is NOT no-map-key',
      !withKey || withKey.reason !== 'no-map-key', JSON.stringify(withKey));
  }
}

console.log(`\n════ RESULT: ${pass} passed, ${fail} failed ════`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail === 0 ? 0 : 1);
