// Harness — 📐 규격만 저장 (`saveMapSpecOnly`), the metadata-only write path (2026-08-04).
// Run: node client2/tests/map_spec_only_save_harness.mjs   (no node_modules — vm sandbox)
//
// WHY A SEPARATE FILE. `effort_instrument_harness` owns ⚡ Push's request shape and
// `geometry_origin_reseat_harness` owns the wiring and the coordinate reactions. This is a
// THIRD write path with its own failure modes, and bolting it onto either would put two
// unrelated sandboxes and two unrelated mutation corpora behind one exit code.
//
// WHAT THIS PATH IS. The user asked for "메타만 저장하는 기능" — save the map's metadata block
// without re-pushing cells — targeted at "현재 설정된 테이블과 맵 아이디". It is the general
// form of the deleted 💾 SAVE (which wrote ONE field and earned nothing, because ⚡ Push
// already carried that field). No new server route: it reuses the same PUT.
//
// THE FOUR THINGS THAT CAN GO SILENTLY WRONG HERE, AND HOW EACH IS MADE FALSIFIABLE.
//
//   1. IT WRITES CELLS. The entire value of this feature is that it does not. Scored as a
//      REQUEST LIST, not as a claim: every fetch the sandbox sees is recorded with its method
//      and URL, and the assertion names the whole list. A harness that only checked "the
//      metadata request happened" would pass while a second request wiped the map.
//
//   2. IT CLOBBERS FIELDS THE EDITOR DOES NOT MODEL. This is a read-modify-write, and a
//      metadata row can carry keys this screen has never heard of. Scored by planting such
//      keys in the stored row and asserting they come back BYTE-IDENTICAL in the payload —
//      and, separately, that a CLEARED valid_die_ref does NOT resurrect from the stored copy.
//      Those two pull in opposite directions, which is exactly why one of them alone is not
//      a test: "preserve everything" passes #2a and fails #2b, "keep nothing" the reverse.
//
//   3. IT STRANDS CELLS WITHOUT SAYING SO. Shrink the grid, save meta only, and stored cells
//      that were inside the declared frame are now outside it — still in the database, no
//      longer addressable by the map that owns them. Nothing in the cell data changed; the
//      frame moved out from under it. Scored against an INDEPENDENT ORACLE: the fixture builds
//      the wide frame's key set and the narrow frame's key set with the product's own
//      `getDieIndex`, takes the set difference itself, and requires that number to appear in
//      the confirm text. A fixture that asserted only "some warning appeared" would pass on
//      any number, and the number is the whole content of the warning.
//
//   4. IT WRITES SOMEWHERE IT NEVER READ. `fetchGridMetaFor` distinguishes "no declaration"
//      (null) from "could not confirm" (throws). Proceeding on the second with `{}` destroys
//      the whole spec in one save — invariant ③. Scored by injecting the failure EXACTLY ONCE
//      and asserting that the request list contains the failed read and NOTHING ELSE.
//
// FIXTURE ACTIVITY. `cols !== rows`, `rotation 90`, `chip_x !== chip_y` and a non-zero offset
// are all simultaneously true, so the pitch-swap and bbox terms of `getDieIndex` are live. A
// square, unrotated, isotropic fixture cannot show a swap defect at all, and the stranded-cell
// count it produced would be an artefact of the symmetry rather than a measurement.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const SRC_PATH = join(ROOT, 'client2', 'src', 'map_editor.js');
const SRC = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');
// The response bound lives in config.js, so it is READ from there rather than typed here — a
// harness that hardcoded 15000 would keep passing after someone retuned the constant.
const CFG_PATH = join(ROOT, 'client2', 'src', 'config.js');
const CFG = readFileSync(CFG_PATH, 'utf8').replace(/\r\n/g, '\n');
const verbose = process.argv.includes('--verbose');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

// ── Extraction ──────────────────────────────────────────────────────────────────────────
function sliceFunction(src, name) {
  const m = new RegExp(`(?:^|\\n)(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} is gone from map_editor.js — renamed or reshaped.`);
  const start = m.index + (m[0].startsWith('\n') ? 1 : 0);
  const open = src.indexOf('{', start);
  let depth = 0;
  for (let j = open; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(start, j + 1); }
  }
  return die(`unbalanced braces for ${name}`);
}

// The write path, plus everything it calls that this harness must score rather than fake.
// A stub for any of these would let the harness grade an answer the product does not give.
const SYMBOLS = [
  'physNum', 'gridDimNum', 'getScreenShift', 'getTransformedPhysicalConfig', 'getDieIndex',
  // [2b] The reader, and the ONE predicate it asks about a blank box (shared with
  // `resolveGridFrame`'s `current` branch AND with `physDeclaration`). Sliced, never re-typed.
  'controlIsSilent', 'gridFrameControlNum', 'readGridFrameControls',
  'validDieRefDisplay', 'applyValidDieRef', 'validDieRefFromControls', 'validDieRefForPush',
  'validDieRefPayload',
  // The merge under test. Sliced, never re-typed: a copy here would let this harness score a
  // preservation rule the product does not implement.
  'mergeStoredGridMeta',
  // [D1] `buildPushGridMetadata` asks this before deciding whether the spec it writes is a
  // declaration or a synthesized stand-in.
  'geometryIsAutoRegistered', 'markGeometryAutoRegistered',
  // [D4] ...and the same pair for the FRAME half: a frame that came out of the coordinate-choice
  // modal must stay distinguishable from one the map declared, across this writer too.
  'frameChosenFrom', 'markFrameChosen',
  'buildPushGridMetadata',
  'serverCellKeySet', 'classifyUnsavableCells',
  // The READ. Real, so that "what did this feature ask the server" is a measurement.
  'fetchGridMetaFor',
  'saveMapSpecOnly',
];

// ── Fixture geometry — anisotropic, rotated, offset (see the header) ────────────────────
const WIDE = { cols: 25, rows: 21 };
const NARROW = { cols: 19, rows: 15 };
const PHYS = { dia: 300, chipX: 14.3, chipY: 9.7, offX: 1.7, offY: -2.4, margin: 3 };
const ROT = 90;
const SIDE = 'front';

function makeInput(v) { return { value: String(v), checked: false, style: {}, dataset: {} }; }

function makeEl(frame) {
  return {
    gridCols: makeInput(frame.cols), gridRows: makeInput(frame.rows),
    gridStartX: makeInput(1), gridStartY: makeInput(1),
    gridYInvert: { checked: false },
    physWaferDia: makeInput(PHYS.dia),
    physChipX: makeInput(PHYS.chipX), physChipY: makeInput(PHYS.chipY),
    physOffsetX: makeInput(PHYS.offX), physOffsetY: makeInput(PHYS.offY),
    physEdgeMargin: makeInput(PHYS.margin),
    validDieRefKey: makeInput(''),
    btnSaveMapSpec: { disabled: false, textContent: '📐 규격만 저장' },
  };
}

/**
 * Every physical key a declared frame covers, computed with the PRODUCT's `getDieIndex`.
 * This is the oracle for axis 3: the set difference between the wide and narrow frames IS
 * the population that a shrink strands, and it is derived rather than typed.
 */
function keysCovered(S, frame) {
  const isRot = (ROT === 90 || ROT === 270);
  const visC = isRot ? frame.rows : frame.cols;
  const visR = isRot ? frame.cols : frame.rows;
  const out = new Map();
  for (let r = 0; r < visR; r++) {
    for (let c = 0; c < visC; c++) {
      const p = S.getDieIndex(null, c, r, frame.cols, frame.rows, ROT, SIDE);
      out.set(`${p.x}_${p.y}`, { c, r });
    }
  }
  return out;
}

// ── Sandbox ─────────────────────────────────────────────────────────────────────────────
function cfgNumber(name) {
  const m = new RegExp(`export\\s+const\\s+${name}\\s*=\\s*([0-9.]+)\\s*;`).exec(CFG);
  if (!m) die(`\`export const ${name}\` is gone from config.js — renamed, moved, or not a literal.`);
  return Number(m[1]);
}

function buildEnv(src, opts = {}) {
  const requests = [];
  const toasts = [];
  const confirms = [];
  const frame = opts.frame || WIDE;
  // A CONTROLLABLE CLOCK. The response bound is a `setTimeout`, and a harness that let the real
  // one run would either wait 15 real seconds or measure nothing. Timers are recorded with the
  // delay they were ASKED for, so "the bound is the configured one" and "the timer was cleared"
  // are both readable — the second is the half that matters on the success path, where a
  // surviving timer would abort somebody else's request later.
  const timers = [];
  let timerSeq = 0;
  const aborts = [];

  const sandbox = {
    AbortController,
    setTimeout: (fn, ms) => { const id = ++timerSeq; timers.push({ id, ms, fn }); return id; },
    clearTimeout: (id) => {
      const i = timers.findIndex(t => t.id === id);
      if (i >= 0) timers.splice(i, 1);
    },
    MAP_SPEC_SAVE_TIMEOUT_MS: cfgNumber('MAP_SPEC_SAVE_TIMEOUT_MS'),
    console: { warn() {}, log() {}, error() {}, info() {}, debug() {} },
    JSON, Math, Number, Object, Array, String, Boolean, Set, Map, parseInt, parseFloat,
    isNaN, encodeURIComponent, Promise,
    el: makeEl(frame),
    API_BASE: '/api',
    CURRENT_USER: 'tester',
    selectedTable: opts.table || 'bonding_map',
    currentRotation: ROT,
    currentSide: SIDE,
    validDie: opts.validDie || { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    loadedIdentity: opts.loadedIdentity !== undefined
      ? opts.loadedIdentity : { table: 'bonding_map', mapKey: 'LOADED_MAP' },
    serverCellKeys: null,
    gridData: {},
    gridCells2D: {},
    // [fix E-2] The success path now also drops the back-guard's baseline, so `saveMapSpecOnly`
    // READS these two. Without them the function throws ReferenceError inside its own try and
    // reports a phantom failure — which is exactly how K5 caught their absence. They are
    // bindings, not an axis: what the guard should do with them is scored by
    // `valid_die_dirty_guard_harness.mjs`, which owns the edit predicate end to end.
    frameTouched: false,
    legendDirty: false,
    // The identity SOURCE is under test, so this is a stub that deliberately answers something
    // DIFFERENT from `loadedIdentity.mapKey`: if the product read the loaded identity instead
    // of the live controls, the recorded request would carry the wrong key and say so.
    getCurrentMapKey: () => (opts.currentMapKey !== undefined ? opts.currentMapKey : 'CURRENT_MAP'),
    showToast: (msg, kind) => toasts.push({ msg: String(msg), kind }),
    syncValidDieRefControls() {},
    confirm: (text) => { confirms.push(String(text)); return opts.approve !== false; },
    fetch: (url, init) => {
      const method = (init && init.method) ? init.method : 'GET';
      requests.push({
        method, url: String(url), body: init && init.body ? init.body : null,
        // Recorded so "the request carried an abort signal at all" is a measurement. A timeout
        // that arms a timer but never wires the signal through aborts nothing.
        hasSignal: !!(init && init.signal),
      });
      const answer = opts.answer ? opts.answer(String(url), method, requests.length) : null;
      if (answer && answer.throwNetwork) return Promise.reject(new Error('network down'));
      const respond = () => ({
        ok: answer ? answer.ok !== false : true,
        status: answer && answer.status ? answer.status : 200,
        json: async () => (answer && answer.body !== undefined) ? answer.body : { data: [] },
      });
      // THE PRODUCTION DEFECT, MODELLED EXACTLY: the request goes out and the promise NEVER
      // settles. The only thing that can ever end it is the caller's own abort, and a real
      // `fetch` rejects with an AbortError when that happens — so this one does too, because
      // the product branches on having caused the abort rather than on the error's shape.
      if (answer && answer.neverSettles) {
        return new Promise((_resolve, reject) => {
          const sig = init && init.signal;
          if (!sig) return;                       // no signal wired => genuinely forever
          sig.addEventListener('abort', () => {
            aborts.push({ at: requests.length });
            const err = new Error('The user aborted a request.');
            err.name = 'AbortError';
            reject(err);
          });
        });
      }
      // A slow-but-real response: settles only when the case says so, which is how "the answer
      // arrived INSIDE the bound" is expressed without a wall clock.
      if (answer && answer.deferred) {
        return new Promise((resolve, reject) => {
          answer.deferred.settle = () => resolve(respond());
          const sig = init && init.signal;
          if (sig) sig.addEventListener('abort', () => {
            aborts.push({ at: requests.length });
            const err = new Error('The user aborted a request.');
            err.name = 'AbortError';
            reject(err);
          });
        });
      }
      return Promise.resolve(respond());
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);

  const pieces = SYMBOLS.map(n => sliceFunction(src, n));
  // `VALID_DIE_TABLE` is a VALUE the confirm text quotes. Lifted from source, never re-typed.
  const vd = /^const VALID_DIE_TABLE = .*;$/m.exec(src);
  if (!vd) die('const VALID_DIE_TABLE is gone from map_editor.js');
  pieces.unshift(vd[0]);
  try { vm.runInContext(pieces.join('\n\n'), sandbox); }
  catch (e) { die(`extracted sources did not evaluate: ${e && e.message}`); }

  return {
    S: sandbox, requests, toasts, confirms, timers, aborts,
    // Fire every pending timer, which is how "the bound elapsed" is expressed.
    fireTimers: () => { [...timers].forEach(t => t.fn()); },
  };
}

/** One microtask drain, so a not-awaited call can be inspected mid-flight. */
const flush = () => new Promise(r => setImmediate(r));

// A stored metadata row as the server would hand it back, carrying TWO keys this editor has
// never modelled. They are the read-modify-write probe.
const UNMODELLED = { legacy_notch_hint: 'D-bottom', owner_note: '2024 pilot lot' };
function storedRow(extra = {}) {
  return {
    grid_cols: WIDE.cols, grid_rows: WIDE.rows, grid_start_x: 1, grid_start_y: 1,
    grid_y_invert: false, rotation: ROT, side: SIDE,
    phys_wafer_dia: PHYS.dia, phys_chip_x: PHYS.chipX, phys_chip_y: PHYS.chipY,
    phys_offset_x: PHYS.offX, phys_offset_y: PHYS.offY, phys_edge_margin: PHYS.margin,
    ...UNMODELLED, ...extra,
  };
}
const META_URL_READ = '/api/tables/wafer_map_metadata/data';
const META_URL_WRITE = '/api/tables/wafer_map_metadata/data/updates';

/** The canned answer function: the read returns `row` (or nothing), the write succeeds. */
function answerWith(row, opts = {}) {
  return (url, method) => {
    if (method === 'PUT') return opts.writeFails ? { ok: false, status: 500 } : { ok: true, body: {} };
    if (opts.readStatus) return { ok: false, status: opts.readStatus };
    if (opts.readThrows) return { throwNetwork: true };
    return { ok: true, body: { data: row ? [{ data: { grid_metadata: { value: JSON.stringify(row) } } }] : [] } };
  };
}

function metaPayload(requests) {
  const w = requests.filter(r => r.method === 'PUT');
  if (w.length !== 1) return null;
  const body = JSON.parse(w[0].body);
  return JSON.parse(body.updates[0].updates.grid_metadata);
}

// ── Cases ───────────────────────────────────────────────────────────────────────────────
async function run(src) {
  const failures = [];
  const evidence = [];
  let compared = 0;
  const eq = (name, expected, actual, note) => {
    compared++;
    const a = JSON.stringify(actual), e = JSON.stringify(expected);
    if (a !== e) failures.push(`${name}: expected ${e}, got ${a}${note ? ` — ${note}` : ''}`);
  };

  // ── A. THE EVERYDAY UPDATE. Request list, read-modify-write, and the identity source. ──
  {
    const env = buildEnv(src, { answer: answerWith(storedRow()) });
    await env.S.saveMapSpecOnly();

    // AXIS 1 — cells are untouched, stated as the WHOLE request list rather than as a claim.
    eq('A/only two requests, both to wafer_map_metadata',
      [`GET ${META_URL_READ}`, `PUT ${META_URL_WRITE}`],
      env.requests.map(r => `${r.method} ${r.url.split('?')[0]}`),
      'a request to the cell table here would mean this feature writes cells');

    const payload = metaPayload(env.requests);
    // AXIS 2a — keys the editor does not model survive byte-identical.
    eq('A/unmodelled stored fields survive the write',
      UNMODELLED,
      { legacy_notch_hint: payload.legacy_notch_hint, owner_note: payload.owner_note },
      'this is a read-modify-write; rebuilding the object from known fields deletes the rest');
    // ...and the editor's own fields are the ones the controls declare.
    eq('A/the editor\'s own fields come from the controls',
      { grid_cols: WIDE.cols, grid_rows: WIDE.rows, rotation: ROT, side: SIDE,
        phys_chip_x: PHYS.chipX, phys_chip_y: PHYS.chipY },
      { grid_cols: payload.grid_cols, grid_rows: payload.grid_rows, rotation: payload.rotation,
        side: payload.side, phys_chip_x: payload.phys_chip_x, phys_chip_y: payload.phys_chip_y });

    // AXIS — identity is the CURRENT controls, not what the map was loaded under.
    const w = JSON.parse(env.requests.find(r => r.method === 'PUT').body).updates[0];
    eq('A/the row written is the CURRENTLY SET table and map id',
      { business_key_val: 'bonding_map_CURRENT_MAP', map_id: 'CURRENT_MAP', target_table: 'bonding_map' },
      { business_key_val: w.business_key_val, map_id: w.updates.map_id,
        target_table: w.updates.target_table },
      'loadedIdentity.mapKey is LOADED_MAP — reading that instead is the defect this names');
    // ...and the READ asked about the same identity it then wrote. A read of one row and a
    // write of another is a read-modify-write of the wrong row, which looks perfect here.
    eq('A/...and the read asked about that same identity', true,
      env.requests[0].url.includes('CURRENT_MAP'));

    eq('A/exactly one confirm', 1, env.confirms.length,
      'UI discipline: reading is frictionless, writing gets exactly one confirmation');
    eq('A/the confirm names the table and the map id', true,
      (env.confirms[0] || '').includes('bonding_map') && (env.confirms[0] || '').includes('CURRENT_MAP'));
    eq('A/the confirm says this is an UPDATE, measured from the read', true,
      (env.confirms[0] || '').includes('갱신'));
    eq('A/...and does not claim to be a new registration', false,
      (env.confirms[0] || '').includes('새로 등록'));
    evidence.push(`A update: requests ${env.requests.map(r => r.method).join(',')}, `
      + `payload keys ${Object.keys(payload).length}, confirm 1`);
  }

  // ── B. THE CREATE. The row does not exist yet, and registering it is the useful case. ──
  {
    const env = buildEnv(src, { answer: answerWith(null) });
    await env.S.saveMapSpecOnly();
    eq('B/a missing row does not stop the save', 1,
      env.requests.filter(r => r.method === 'PUT').length,
      'refusing here would forbid exactly the operation the user asked for');
    eq('B/the confirm says NEW REGISTRATION, in those words', true,
      (env.confirms[0] || '').includes('새로 등록'));
    eq('B/...and not UPDATE', false, (env.confirms[0] || '').includes('갱신'));
    // The distinction is READ, not assumed: the same code path produced 갱신 in case A.
    const payload = metaPayload(env.requests);
    eq('B/nothing is invented for the fields it never read',
      undefined, payload.legacy_notch_hint,
      'a create has no stored row to preserve, and must not carry one from anywhere else');
    eq('B/still only the two metadata requests',
      [`GET ${META_URL_READ}`, `PUT ${META_URL_WRITE}`],
      env.requests.map(r => `${r.method} ${r.url.split('?')[0]}`));
    evidence.push(`B create: confirm says 새로 등록, payload keys ${Object.keys(payload).length}`);
  }

  // ── C. THE READ FAILED. Invariant ③: what was not read is not written. ─────────────────
  //   Injection is counted: the read is failed EXACTLY ONCE, and the assertion is that the
  //   request list ENDS there. Failing every request would also produce "no write" while
  //   proving nothing about the branch.
  {
    let reads = 0;
    const env = buildEnv(src, {
      answer: (url, method) => {
        if (method === 'PUT') return { ok: true, body: {} };
        reads++;
        return reads === 1 ? { ok: false, status: 500 } : { ok: true, body: { data: [] } };
      },
    });
    await env.S.saveMapSpecOnly();
    eq('C/exactly one read was failed', 1, reads,
      'if the fixture failed more than one, the recovery branch was never reached either');
    eq('C/no write followed a read that could not be confirmed', 0,
      env.requests.filter(r => r.method === 'PUT').length,
      'writing a rebuilt spec over a row we could not read destroys every field we do not model');
    eq('C/and no confirmation was even offered', 0, env.confirms.length,
      'asking the operator to approve a write that must not happen is its own defect');
    eq('C/the refusal says nothing was written', true,
      env.toasts.some(t => t.kind === 'error' && t.msg.includes('아무것도 기록되지 않았습니다')));
    evidence.push(`C read-failure: reads ${reads}, writes 0, confirms 0`);
  }

  // ── D. STRANDED CELLS. The number in the confirm must be the number actually stranded. ──
  {
    // Painted under the WIDE frame; the panel now declares the NARROW one. The oracle is the
    // set difference of the two frames' covered keys, taken here rather than read off the code.
    const probe = buildEnv(src, {});
    const wideKeys = keysCovered(probe.S, WIDE);
    const narrowKeys = keysCovered(probe.S, NARROW);
    const strandedOracle = [...wideKeys.keys()].filter(k => !narrowKeys.has(k));

    eq('D/fixture: the shrink genuinely strands cells', true, strandedOracle.length > 0,
      'a shrink that strands nothing cannot show whether the count is reported at all');
    eq('D/fixture: and it does not strand everything', true,
      narrowKeys.size > 0 && strandedOracle.length < wideKeys.size);

    const env = buildEnv(src, { frame: NARROW, answer: answerWith(storedRow()) });
    // Every wide-frame cell holds a value; the grid the panel declares covers only the narrow set.
    wideKeys.forEach((_v, k) => { env.S.gridData[k] = 'A'; });
    narrowKeys.forEach((v, k) => {
      if (!env.S.gridCells2D[v.r]) env.S.gridCells2D[v.r] = {};
      env.S.gridCells2D[v.r][v.c] = { key: k, c: v.c, r: v.r, inside: true };
    });
    env.S.loadedIdentity = { table: 'bonding_map', mapKey: 'CURRENT_MAP' };  // same identity
    await env.S.saveMapSpecOnly();

    eq('D/the confirm carries the EXACT stranded count', true,
      (env.confirms[0] || '').includes(`${strandedOracle.length}건`),
      `oracle says ${strandedOracle.length} stranded; confirm text: `
      + `${JSON.stringify(((env.confirms[0] || '') || '').slice(0, 200))}`);
    eq('D/...and says they are not deleted, only unreachable', true,
      (env.confirms[0] || '').includes('삭제되지 않지만'),
      'a warning that implies deletion sends the operator to the wrong recovery');
    eq('D/the save is a warning, not a refusal — the write still goes out', 1,
      env.requests.filter(r => r.method === 'PUT').length,
      'this write deletes nothing and is reversible by restoring the frame; refusing would '
      + 'also trap any map that already has off-grid cells');
    eq('D/still only the two metadata requests, even with cells on screen',
      [`GET ${META_URL_READ}`, `PUT ${META_URL_WRITE}`],
      env.requests.map(r => `${r.method} ${r.url.split('?')[0]}`),
      'the stranded cells are NOT rewritten anywhere — that is the whole point');

    // The zero case, so the count above is a measurement and not a constant.
    const envOk = buildEnv(src, { frame: WIDE, answer: answerWith(storedRow()) });
    wideKeys.forEach((v, k) => {
      envOk.S.gridData[k] = 'A';
      if (!envOk.S.gridCells2D[v.r]) envOk.S.gridCells2D[v.r] = {};
      envOk.S.gridCells2D[v.r][v.c] = { key: k, c: v.c, r: v.r, inside: true };
    });
    envOk.S.loadedIdentity = { table: 'bonding_map', mapKey: 'CURRENT_MAP' };
    await envOk.S.saveMapSpecOnly();
    eq('D/an unshrunk frame reports NO stranded cells', true,
      (envOk.confirms[0] || '').includes('격자 밖으로 밀려나는 셀: 없음') && !/\d+건/.test((envOk.confirms[0] || '')),
      'if both the shrunk and unshrunk cases said the same thing, the count would be decoration');
    evidence.push(`D stranded: oracle ${strandedOracle.length} of ${wideKeys.size} `
      + `(narrow covers ${narrowKeys.size}), confirm carried it; unshrunk case said 없음`);
  }

  // ── E. A DIFFERENT IDENTITY. A zero here would be a lie, so it must not be a zero. ─────
  {
    const env = buildEnv(src, { answer: answerWith(null), currentMapKey: 'BRAND_NEW' });
    env.S.gridData = { '1_1': 'A' };      // cells on screen, but they belong to LOADED_MAP
    env.S.gridCells2D = {};
    await env.S.saveMapSpecOnly();
    eq('E/it says the count is UNKNOWN, not zero', true,
      (env.confirms[0] || '').includes('셀 수 없습니다'),
      'the cells on screen came from a different map; reporting 0 stranded would be false');
    // Scoped to the stranded-cell LINE. A bare search for '없음' also matches the valid-die
    // line ('지정 없음'), which is unrelated and always present when nothing is designated —
    // an assertion that cannot distinguish the two would have gone red against correct code.
    eq('E/...and does not claim there are none', false,
      (env.confirms[0] || '').includes('격자 밖으로 밀려나는 셀: 없음'));
    evidence.push('E foreign identity: confirm says the stranded count cannot be counted');
  }

  // ── F. CLEARING THE DECLARATION MUST NOT RESURRECT IT FROM THE STORED ROW. ─────────────
  //   The mirror image of axis 2a, and the reason a plain spread is not the merge.
  {
    const env = buildEnv(src, {
      answer: answerWith(storedRow({ valid_die_ref: 'OLD_REF' })),
      validDie: { basis: 'ref', keys: new Set(), reason: '', ref: null, raw: 'OLD_REF' },
    });
    env.S.el.validDieRefKey.value = '';       // the operator cleared it
    await env.S.saveMapSpecOnly();
    const payload = metaPayload(env.requests);
    eq('F/a cleared valid_die_ref does NOT come back from the stored row',
      false, 'valid_die_ref' in payload,
      'a plain {...stored, ...built} spread restores it, because the key is ABSENT when cleared');
    eq('F/...while the unmodelled fields still survive that same merge',
      UNMODELLED,
      { legacy_notch_hint: payload.legacy_notch_hint, owner_note: payload.owner_note },
      'these two pull opposite ways — either one alone is satisfied by a wrong merge');
    eq('F/and the confirm says the designation is now none', true,
      (env.confirms[0] || '').includes('지정 없음'));
    evidence.push('F clear: valid_die_ref absent from payload, unmodelled fields intact');
  }

  // ── G. AN UNCHANGED DECLARATION IS WRITTEN BACK VERBATIM. ─────────────────────────────
  //   `validDieRefForPush`'s `keep` branch. A shape we did not author (an alias object) must
  //   not be silently normalised by a save the operator made for an unrelated reason.
  {
    const raw = { target_table: 'valid_die_ref', map_key: 'ALIAS_SHAPE' };
    const env = buildEnv(src, {
      answer: answerWith(storedRow({ valid_die_ref: raw })),
      validDie: { basis: 'ref', keys: new Set(), reason: '', ref: null, raw },
    });
    env.S.el.validDieRefKey.value = 'ALIAS_SHAPE';    // what the control displays for that raw
    await env.S.saveMapSpecOnly();
    eq('G/an untouched declaration is written back in its ORIGINAL shape', raw,
      metaPayload(env.requests).valid_die_ref,
      'rewriting a shape the user never touched hides their typo from them');
    evidence.push('G keep: alias-shaped declaration round-tripped unchanged');
  }

  // ── H. THE OPERATOR SAYS NO. ───────────────────────────────────────────────────────────
  {
    const env = buildEnv(src, { answer: answerWith(storedRow()), approve: false });
    await env.S.saveMapSpecOnly();
    eq('H/declining the confirm writes nothing', 0,
      env.requests.filter(r => r.method === 'PUT').length);
    evidence.push('H cancel: 0 writes');
  }

  // ── I. NO MAP KEY SET. Registering a spec under a placeholder identity is not a save. ──
  {
    const env = buildEnv(src, { answer: answerWith(null), currentMapKey: null });
    await env.S.saveMapSpecOnly();
    eq('I/no map key -> no requests at all', 0, env.requests.length,
      'the read is skipped too: there is no identity to read about');
    eq('I/...and it says so', true, env.toasts.some(t => t.kind === 'error'));
    evidence.push('I no key: 0 requests');
  }

  // ── J. [D1] AUTO-REGISTRATION SURVIVES THE ROUND TRIP. ────────────────────────────────
  //   A synthesized spec that loses its mark on the first save is silently promoted to a
  //   declaration, and it can never be demoted again: the ingestion registrar only fills in
  //   ABSENT rows, so it will never revisit one that now exists. Both writers share
  //   `buildPushGridMetadata`, so this is scored on the payload it produces.
  {
    const marked = buildEnv(src, { answer: answerWith(storedRow()) });
    marked.S.markGeometryAutoRegistered(true);
    await marked.S.saveMapSpecOnly();
    eq('J/a a marked spec writes the flag back', true,
      metaPayload(marked.requests).auto_registered,
      'losing it here promotes synthesized geometry to a declaration, permanently');

    // 🔴 THE OTHER HALF, and the one that protects INV-1: an UNMARKED map must not gain the
    //    key. A writer that always emits it would satisfy J/a and change the payload of every
    //    map in the database.
    const plain = buildEnv(src, { answer: answerWith(storedRow()) });
    await plain.S.saveMapSpecOnly();
    eq('J/b an unmarked spec does NOT gain the flag', false,
      'auto_registered' in metaPayload(plain.requests),
      'the payload of a normal map must be unchanged by this round');
    evidence.push('J round trip: marked payload carries auto_registered, unmarked does not');
  }

  // ── L. [D4] A CHOSEN FRAME STAYS DISTINGUISHABLE FROM A DECLARED ONE. ─────────────────
  //   The frame half's twin of J, and the reason this round exists. A map with no readable
  //   declaration is routed to the coordinate-choice modal; whatever the operator picks there
  //   was written back as a PLAIN declaration with no marker at all, so a frame nobody declared
  //   became byte-identical to one somebody did — permanently, because nothing ever revisits a
  //   row that already exists. Scored on the payload, because that is the only thing that
  //   survives the session.
  {
    for (const from of ['data', 'panel']) {
      const env = buildEnv(src, { answer: answerWith(storedRow()) });
      env.S.markFrameChosen(from);
      await env.S.saveMapSpecOnly();
      eq(`L/a a frame chosen from the ${from} says so in the payload`, from,
        metaPayload(env.requests).frame_chosen_from,
        'without this the choice is unrecoverable the moment the session ends');
    }
    // 🔴 WHICH choice, not merely THAT one happened. Folding both branches to `true` would pass
    //    a boolean assertion and delete the difference between a bbox-derived frame and the
    //    previous map's panel residue — the two are not the same claim about the same numbers.
    const a = buildEnv(src, { answer: answerWith(storedRow()) });
    a.S.markFrameChosen('data');
    await a.S.saveMapSpecOnly();
    const b = buildEnv(src, { answer: answerWith(storedRow()) });
    b.S.markFrameChosen('panel');
    await b.S.saveMapSpecOnly();
    eq('L/b the two choices are DISTINGUISHABLE from each other', true,
      metaPayload(a.requests).frame_chosen_from !== metaPayload(b.requests).frame_chosen_from);

    // INV-1, the same half J/b protects: an unchosen map must not gain the key. Every declared
    // map in the database is this case, and its payload must not move by one byte.
    const plain = buildEnv(src, { answer: answerWith(storedRow()) });
    await plain.S.saveMapSpecOnly();
    eq('L/c a declared frame does NOT gain the marker', false,
      'frame_chosen_from' in metaPayload(plain.requests),
      'the payload of a normal map must be unchanged by this round');
    // ...and the marker is a one-axis-read hazard: the product writes BOTH START boxes and reads
    // both, so a half-written marker must not be reported as a choice.
    const split = buildEnv(src, { answer: answerWith(storedRow()) });
    split.S.el.gridStartX.dataset.frameChosen = 'panel';
    await split.S.saveMapSpecOnly();
    eq('L/d a marker on only ONE axis is not a choice', false,
      'frame_chosen_from' in metaPayload(split.requests));
    // 🔴 INSIDE A FRAME WINDOW THE FRAME ANSWERS ALONE. This branch is the one nothing else in
    //    the repo executes, and an unexercised branch is an unread write that goes stale in
    //    silence. The defect it prevents is the phys marker's, one axis over: with a chosen map
    //    open, overlaying somebody else's map would report the SOURCE's frame as chosen because
    //    the screen still carries this session's marker. Provenance is a fact about a MAP.
    const win = buildEnv(src, { answer: answerWith(storedRow()) });
    win.S.markFrameChosen('panel');
    // The frame is an ARGUMENT now: `null` asks the screen, an object asks that map.
    const CHOSEN_FRAME = { frame_chosen_from: 'data' };
    const SILENT_FRAME = {};
    eq('L/e on screen the START boxes answer', 'panel', win.S.frameChosenFrom(null));
    eq('L/f a frame carrying the mark answers for its OWN map, not the screen', 'data',
      win.S.frameChosenFrom(CHOSEN_FRAME));
    eq('L/g ...and a frame that says nothing is not this session\'s choice', null,
      win.S.frameChosenFrom(SILENT_FRAME));
    evidence.push('L round trip: data/panel both reach the payload and differ; unmarked gains nothing');
  }

  // ── M. [2b] A BLANK BOX IS NOT A ZERO. ────────────────────────────────────────────────
  //   `parseInt('') || 0` used to promote silence to a declared 0 here exactly as it did on the
  //   load path — and this writer REGISTERS the grid, so a fabricated origin takes the address
  //   away from cells that are still sitting in the database. The predicate is shared with
  //   `resolveGridFrame`'s `current` branch (`gridFrameControlNum`), which is why there is one
  //   spelling to score rather than two that agree today.
  {
    const blank = buildEnv(src, { answer: answerWith(storedRow()) });
    blank.S.el.gridStartX.value = '';
    await blank.S.saveMapSpecOnly();
    eq('M/a a blank START box writes NOTHING', 0,
      blank.requests.filter(r => r.method === 'PUT').length,
      'a fabricated 0 registered here strands every cell the real origin addressed');
    eq('M/b ...and the operator is told WHICH box', true,
      blank.toasts.some(t => t.kind === 'error' && /START X/.test(t.msg)));
    eq('M/c ...and it is not asked as a question first', 0, blank.confirms.length,
      'a confirm on a value that cannot be saved is friction with no decision behind it');

    // THE COUNTERFACTUAL. A TYPED zero is a legitimate origin and must still save; otherwise
    // "refuses when blank" is satisfied by a writer that refuses, and the assertion is vacuous.
    const zero = buildEnv(src, { answer: answerWith(storedRow()) });
    zero.S.el.gridStartX.value = '0';
    await zero.S.saveMapSpecOnly();
    eq('M/d a TYPED zero still saves', 1, zero.requests.filter(r => r.method === 'PUT').length);
    eq('M/e ...and it reaches the payload as 0', 0, metaPayload(zero.requests).grid_start_x);
    evidence.push('M blank START: 0 writes, 0 confirms; typed 0: 1 write carrying grid_start_x 0');
  }

  // ── K. THE RESPONSE THAT NEVER COMES. ─────────────────────────────────────────────────
  //   Reported live 2026-08-04: 📐 규격만 저장 sticks on "Saving..." forever WHILE THE SAVE
  //   ACTUALLY SUCCEEDS. The button is restored in a `finally`, so a stuck button means the
  //   `finally` was never reached, which means `await fetch(...)` never settled.
  //
  //   🔴 NOTHING HERE MAY `await` THE CALL UNCONDITIONALLY. That is the whole failure mode: on
  //      the unbounded code the returned promise never settles, so an `await` would hang this
  //      harness rather than fail it — and it would hang inside the MUTATION SWEEP, where the
  //      unbounded version is deliberately reintroduced. Settlement is therefore OBSERVED (a
  //      `done` flag set from `.then`) instead of waited for.
  {
    // K1. The fixture, and the reproduction: the request goes out, nothing comes back.
    const env = buildEnv(src, {
      answer: (url, method) => (method === 'PUT'
        ? { neverSettles: true }
        : { ok: true, body: { data: [{ data: { grid_metadata: { value: JSON.stringify(storedRow()) } } } ] } }),
    });
    let done = false;
    env.S.saveMapSpecOnly().then(() => { done = true; }, () => { done = true; });
    await flush(); await flush();

    const put = env.requests.filter(r => r.method === 'PUT');
    eq('K1/the write really was sent (the fixture is alive)', 1, put.length);
    eq('K1/...and no response has arrived, so the button is mid-flight', true,
      env.S.el.btnSaveMapSpec.disabled === true
        && env.S.el.btnSaveMapSpec.textContent === '📐 Saving...',
      'this is the state the user was stranded in, and it is CORRECT until the bound elapses');
    eq('K1/the request carries an abort signal', true, put[0].hasSignal,
      'a bound that arms a timer but never wires the signal through aborts nothing');
    eq('K1/the armed bound is the one configured, not a number typed here',
      cfgNumber('MAP_SPEC_SAVE_TIMEOUT_MS'),
      env.timers.length === 1 ? env.timers[0].ms : null);

    // K2. The bound elapses. THIS is what did not exist.
    env.fireTimers();
    await flush(); await flush();
    eq('K2/the call settles instead of hanging forever', true, done,
      'without a bound this stays pending and the button never comes back');
    eq('K2/the button is released', [false, '📐 규격만 저장'],
      [env.S.el.btnSaveMapSpec.disabled, env.S.el.btnSaveMapSpec.textContent]);
    const timeoutToast = env.toasts.filter(t => t.kind === 'error').slice(-1)[0];
    eq('K2/...and the user is told', true, !!timeoutToast);

    // K3. THE MESSAGE MUST NOT CLAIM THE WRITE WAS DISCARDED. In the reported incident the
    //     write HAD landed. "Nothing was recorded" is wrong in the dangerous direction: it
    //     sends the operator to redo the edit from a stale screen.
    eq('K3/the timeout does NOT claim nothing was recorded', false,
      /아무것도 기록되지 않았습니다/.test(timeoutToast ? timeoutToast.msg : ''),
      'the write may well have landed — in the reported incident it had');
    eq('K3/...it says the outcome is unknown and must be checked', true,
      /확인이 필요합니다/.test(timeoutToast ? timeoutToast.msg : ''));
    eq('K3/...and says how long it waited, not "The user aborted a request"', true,
      /초 안에 응답이/.test(timeoutToast ? timeoutToast.msg : '')
        && !/aborted/i.test(timeoutToast ? timeoutToast.msg : ''),
      'echoing the AbortError text tells the user nothing about their save');

    // K4. A PLAIN NETWORK ERROR IS ALSO NOT A DISCARD. `TypeError: Failed to fetch` can happen
    //     before the request is sent OR after it was sent and the response was lost, and JS
    //     cannot tell those apart — so it must not assert the comfortable one.
    const netEnv = buildEnv(src, { answer: answerWith(storedRow(), { }) });
    netEnv.S.fetch = (url, init) => {
      const method = (init && init.method) ? init.method : 'GET';
      netEnv.requests.push({ method, url: String(url) });
      if (method === 'PUT') return Promise.reject(new Error('Failed to fetch'));
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ data: [{ data: { grid_metadata: { value: JSON.stringify(storedRow()) } } }] }),
      });
    };
    await netEnv.S.saveMapSpecOnly();
    const netToast = netEnv.toasts.filter(t => t.kind === 'error').slice(-1)[0];
    eq('K4/a network error does not claim nothing was recorded either', false,
      /아무것도 기록되지 않았습니다/.test(netToast ? netToast.msg : ''),
      'a lost response is indistinguishable from a rejected send, so it must not assert either');
    eq('K4/...and it too asks for a check', true,
      /확인이 필요합니다/.test(netToast ? netToast.msg : ''));
    eq('K4/...while still naming the cause', true,
      /Failed to fetch/.test(netToast ? netToast.msg : ''));
    eq('K4/the button is released on that path too', false,
      netEnv.S.el.btnSaveMapSpec.disabled);

    // K5. THE NEGATIVE, and the one that keeps the bound honest: a slow-but-REAL save that
    //     answers inside the bound must NOT be aborted. A bound that killed a working save
    //     would turn a successful write into a phantom failure.
    const deferred = {};
    const slow = buildEnv(src, {
      answer: (url, method) => (method === 'PUT'
        ? { deferred }
        : { ok: true, body: { data: [{ data: { grid_metadata: { value: JSON.stringify(storedRow()) } } }] } }),
    });
    let slowDone = false;
    slow.S.saveMapSpecOnly().then(() => { slowDone = true; }, () => { slowDone = true; });
    await flush(); await flush();
    eq('K5/the slow save is still in flight and NOT yet aborted', 0, slow.aborts.length);
    deferred.settle();                       // the response arrives, inside the bound
    await flush(); await flush();
    eq('K5/a slow-but-successful save completes', true, slowDone);
    eq('K5/...was never aborted', 0, slow.aborts.length);
    eq('K5/...reported success, not a phantom failure', true,
      slow.toasts.some(t => t.kind === 'success'));
    // The other half of "cleared": a timer that outlives its request aborts a later one.
    eq('K5/...and the bound timer was cleared, not left armed', 0, slow.timers.length);

    // K6. The ordinary fast path must not leave a timer behind either.
    const fast = buildEnv(src, { answer: answerWith(storedRow()) });
    await fast.S.saveMapSpecOnly();
    eq('K6/a fast save leaves no timer armed', 0, fast.timers.length);
    eq('K6/...and no abort happened', 0, fast.aborts.length);

    // K7. THE BOUND'S VALUE, SCORED AGAINST LITERALS RATHER THAN AGAINST ITSELF. Every other
    //     assertion here reads the constant from config.js, so all of them move WITH a retune
    //     and none would notice a bound of 100ms. These two numbers are typed here on purpose.
    //     There is no production measurement for this endpoint (`server/server.log` holds only
    //     TestClient traffic), so the band is wide and honest rather than narrow and invented.
    const bound = cfgNumber('MAP_SPEC_SAVE_TIMEOUT_MS');
    eq('K7/the bound is long enough not to kill a save that was going to work', true,
      bound >= 5000, `${bound}ms — below this a normal save on a loaded server is at risk`);
    eq('K7/...and short enough that a wedged server is not an indefinite stare', true,
      bound <= 30000, `${bound}ms — beyond this the operator has already given up`);

    evidence.push(`K hang: PUT sent, button held at 📐 Saving...; bound `
      + `${cfgNumber('MAP_SPEC_SAVE_TIMEOUT_MS')}ms released it and the toast asks for a check `
      + `instead of claiming a discard; a save answering inside the bound was untouched`);
  }

  return { failures, compared, evidence };
}

// ── Mutations ───────────────────────────────────────────────────────────────────────────
function once(src, find, repl) {
  const CR = String.fromCharCode(13);
  const toCrlf = (s) => s.split('\n').join(CR + '\n');
  if (src.indexOf(find) < 0 && src.indexOf(toCrlf(find)) >= 0) {
    find = toCrlf(find); repl = toCrlf(repl);
  }
  const i = src.indexOf(find);
  if (i < 0) die(`mutation anchor not found: ${find.slice(0, 70)}`);
  if (src.indexOf(find, i + 1) >= 0) die(`mutation anchor is not unique: ${find.slice(0, 70)}`);
  return src.slice(0, i) + repl + src.slice(i + find.length);
}

const MUTANTS = {
  // The merge becomes a plain spread. Axis 2b only — 2a still passes, which is the point.
  'cleared-declaration-resurrects': (s) => once(s,
    "  if (!('valid_die_ref' in src)) delete out.valid_die_ref;",
    '  // no clear'),
  // The merge stops merging. Axis 2a only — 2b still passes.
  'stored-fields-are-not-preserved': (s) => once(s,
    '  const out = { ...base, ...src };',
    '  const out = { ...src };'),
  // Invariant ③ broken: a read that could not be confirmed is treated as an empty row.
  'writes-over-a-read-it-could-not-confirm': (s) => once(s,
    ['  } catch (e) {',
     '    showToast(`맵 규격을 확인하지 못해 저장을 중단했습니다 — ${(e && e.message) ? e.message : e}. `',
     '      + `잠시 후 다시 시도하십시오(아무것도 기록되지 않았습니다).`, \'error\');',
     '    return;',
     '  }'].join('\n'),
    ['  } catch (e) {',
     '    stored = {};',
     '  }'].join('\n')),
  // The identity reverts to what the map was loaded under — the user asked for the opposite.
  // ⚠️ THE ANCHOR CARRIES ITS NEXT TWO LINES ON PURPOSE. `const mapKey = getCurrentMapKey();`
  //    alone occurs THREE times in map_editor.js (`saveDoeDraft`, `getPlanSaveState`, and this
  //    function) and a first-match replace would have mutated `saveDoeDraft` — a different
  //    function entirely, which this harness does not score, so the mutant would have come back
  //    NOT CAUGHT and been read as a hole in the assertions. `once` refuses non-unique anchors
  //    for exactly this reason, and it refused this one before the lines below were added.
  'identity-comes-from-the-loaded-map': (s) => once(s,
    ['  const mapKey = getCurrentMapKey();',
     '  if (!mapKey) {',
     "    showToast('맵 키 칸을 채워야 규격을 저장할 수 있습니다 — 어느 맵의 규격으로 등록할지 '"].join('\n'),
    ['  const mapKey = (loadedIdentity && loadedIdentity.mapKey) ? loadedIdentity.mapKey : getCurrentMapKey();',
     '  if (!mapKey) {',
     "    showToast('맵 키 칸을 채워야 규격을 저장할 수 있습니다 — 어느 맵의 규격으로 등록할지 '"].join('\n')),
  // The stranded count is never taken. The confirm still appears and still looks complete.
  'stranded-cells-are-not-counted': (s) => once(s,
    '  const offGrid = sameIdentity ? classifyUnsavableCells().offGrid.length : null;',
    '  const offGrid = sameIdentity ? 0 : null;'),
  // A foreign identity is reported as "밀려나는 셀: 없음" instead of "셀 수 없습니다" — a zero
  // about cells that belong to a different map. The most comfortable-looking wrong answer.
  // ⚠️ AN EARLIER VERSION OF THIS MUTANT WAS INERT and came back NOT CAUGHT: it changed how
  //    `offGrid` is COMPUTED, but the branch below tests `!sameIdentity` first, so the computed
  //    value was never read on that path. A mutant the code routes around proves nothing about
  //    the assertions; the defect had to be moved onto the branch that actually decides.
  'foreign-identity-reports-a-misleading-zero': (s) => once(s,
    ['  if (!sameIdentity) {',
     '    orphanLine = `· 이 식별자로 불러온 셀이 화면에 없어, 격자 밖으로 밀려나는 셀 수는 `',
     '      + `셀 수 없습니다.\\n`;',
     '  } else if (offGrid > 0) {'].join('\n'),
    ['  if (false) {',
     "    orphanLine = '';",
     '  } else if (offGrid > 0) {'].join('\n')),
  // create/update is asserted rather than measured.
  'new-versus-update-is-assumed': (s) => once(s,
    '  const isNew = (stored === null);',
    '  const isNew = false;'),
  // The confirm disappears. UI discipline says writes get exactly one.
  'the-write-asks-nobody': (s) => once(s,
    '  if (!confirm(\n    `맵 규격만 기록합니다 — 셀은 하나도 쓰지 않습니다.\\n\\n`',
    '  if (false && confirm(\n    `맵 규격만 기록합니다 — 셀은 하나도 쓰지 않습니다.\\n\\n`'),
  // [D1] The mark is dropped on the way out, so the first save of an auto-registered map
  // promotes its synthesized geometry to a declaration — irreversibly, because the registrar
  // only ever fills ABSENT rows.
  'auto-registration-is-lost-on-save': (s) => once(s,
    '  if (geometryIsAutoRegistered(null)) gridMeta.auto_registered = true;',
    '  // mark dropped'),
  // ...and the opposite: it is written unconditionally, which changes the payload of every
  // ordinary map in the database (INV-1).
  'auto-registration-is-written-for-everything': (s) => once(s,
    '  if (geometryIsAutoRegistered(null)) gridMeta.auto_registered = true;',
    '  gridMeta.auto_registered = true;'),
  // ── [D4] THE FRAME HALF. The same three failure shapes, one axis over. ─────────────────
  // The marker is dropped on the way out: a frame that came from the modal is written back as
  // an ordinary declaration and can never be told apart from one again.
  'frame-choice-is-lost-on-save': (s) => once(s,
    '  if (chosenFrom) gridMeta.frame_chosen_from = chosenFrom;',
    '  // choice dropped'),
  // It is written for everything, which moves the payload of every declared map (INV-1).
  'frame-choice-is-written-for-everything': (s) => once(s,
    '  if (chosenFrom) gridMeta.frame_chosen_from = chosenFrom;',
    "  gridMeta.frame_chosen_from = chosenFrom || 'panel';"),
  // 🔴 THE ONE THAT LOOKS HARMLESS. The fact that a choice HAPPENED is recorded, but WHICH
  //    choice is folded away — so a bbox-derived frame and the previous map's panel residue
  //    become the same record, which is most of what the marker was for.
  'frame-choice-forgets-which-choice': (s) => once(s,
    '  if (chosenFrom) gridMeta.frame_chosen_from = chosenFrom;',
    '  if (chosenFrom) gridMeta.frame_chosen_from = true;'),
  // Only one START box is consulted, so a half-written marker reads as a whole one and the
  // other axis's write rots with nothing to say so.
  'frame-choice-reads-one-axis-only': (s) => once(s,
    '  return dx.frameChosen === dy.frameChosen ? dx.frameChosen : null;',
    '  return dx.frameChosen;'),
  // The screen's marker leaks into a frame window, so an overlaid map's provenance is reported
  // as this session's. Provenance is a fact about a MAP, not about who has the editor open.
  'frame-choice-leaks-across-a-frame-window': (s) => once(s,
    "  if (frame) return frame.frame_chosen_from || null;\n  if (!el) return null;",
    '  if (!el) return null;'),
  // ── [2b] THE BLANK BOX. Today's expression, restored: silence becomes a declared 0. ────
  'a-blank-box-resolves-to-zero': (s) => once(s,
    '  const raw = input ? input.value : undefined;\n  if (controlIsSilent(raw)) return null;',
    '  const raw = input ? input.value : undefined;\n  if (controlIsSilent(raw)) return dflt;'),
  // ...and the softer version: the predicate still answers `null`, but the writer stops asking.
  // This is the shape the codebase actually reaches by accident — the question exists and one
  // of its two consumers forgets to consult it.
  'the-writer-stops-asking-about-blanks': (s) => once(s,
    '  if (panel.silent.length > 0) {\n' +
    '    showToast(`${panel.silent.join(\' · \')} 칸이 비어 있어 규격을 저장하지 않았습니다 — `',
    '  if (false) {\n' +
    '    showToast(`${panel.silent.join(\' · \')} 칸이 비어 있어 규격을 저장하지 않았습니다 — `'),
  // ── K: THE RESPONSE BOUND ──────────────────────────────────────────────────────────────
  // TODAY'S CODE, RESTORED EXACTLY. The request goes out with no signal and no timer, so the
  // promise never settles and the button never comes back. This mutant IS the reported defect,
  // and the assertions it trips are the reproduction.
  // ⚠️ ANCHORED ON THE `signal` SPREAD PLUS ITS CLOSING LINES. `body: JSON.stringify(payload),`
  //    alone is NOT unique in map_editor.js — the ⚡ Push writer spells it identically — and a
  //    first-match replace would have mutated a function this harness does not score, coming
  //    back NOT CAUGHT and reading as a hole in the assertions.
  'the-write-has-no-response-bound': (s) => once(s,
    ['  const abort = (typeof AbortController === \'function\') ? new AbortController() : null;',
     '  let timedOut = false;',
     '  const timeoutTimer = abort',
     '    ? setTimeout(() => { timedOut = true; abort.abort(); }, MAP_SPEC_SAVE_TIMEOUT_MS)',
     '    : null;'].join('\n'),
    ['  const abort = null;',
     '  let timedOut = false;',
     '  const timeoutTimer = null;'].join('\n')),
  // The timer is armed but the signal is never handed to `fetch`, so the abort has nothing to
  // abort. Arming a timer is not a timeout.
  'the-abort-signal-is-never-wired-through': (s) => once(s,
    '      ...(abort ? { signal: abort.signal } : {}),',
    '      // signal not wired'),
  // The bound fires but the message reverts to the claim that is wrong in the dangerous
  // direction — the reported incident had the write LANDING while the user was told otherwise.
  'the-timeout-claims-nothing-was-recorded': (s) => once(s,
    ['      showToast(`맵 규격 저장 — ${Math.round(MAP_SPEC_SAVE_TIMEOUT_MS / 1000)}초 안에 응답이 `',
     '        + `오지 않았습니다. 저장됐는지 확인이 필요합니다 — 화면을 새로 고쳐 규격을 확인한 뒤 `',
     '        + `다시 시도하십시오.`, \'error\');'].join('\n'),
    '      showToast(`맵 규격 저장 실패 — 아무것도 기록되지 않았습니다.`, \'error\');'),
  // ...and the same claim on the network-error branch, which is the case JS genuinely cannot
  // resolve: a lost response and a rejected send look identical from here.
  'the-network-error-claims-nothing-was-recorded': (s) => once(s,
    ['      showToast(`맵 규격 저장 — 응답을 받지 못했습니다 (${(e && e.message) ? e.message : e}). `',
     '        + `저장됐는지 확인이 필요합니다 — 화면을 새로 고쳐 규격을 확인하십시오.`, \'error\');'].join('\n'),
    '      showToast(`맵 규격 저장 실패 — 아무것도 기록되지 않았습니다.`, \'error\');'),
  // The timer outlives the request. Harmless for this controller, which is already spent — but
  // it is the shape that aborts the NEXT request once a controller is reused.
  'the-bound-timer-is-never-cleared': (s) => once(s,
    '    if (timeoutTimer !== null) clearTimeout(timeoutTimer);',
    '    /* timer left armed */;'),
  // 🔴 NO MUTANT FOR THE BOUND'S VALUE, AND THAT IS DELIBERATE. This harness drives a virtual
  //    clock, so retuning `MAP_SPEC_SAVE_TIMEOUT_MS` changes no behaviour it can observe — and
  //    every assertion that quotes the bound reads it from config.js, so they would all move
  //    with the mutation and stay green. Declaring a mutation nothing can catch is how a
  //    harness ends up with a permanent hole it reports as coverage. The value is defended
  //    instead by K7, which scores it against literals typed here.
  // ── NEGATIVE CONTROL. A comment-only edit must ESCAPE. A corpus that "catches" this is
  //    keying on source text rather than behaviour, and its caught column means nothing.
  '__control_comment_only': (s) => once(s,
    '// UI 규율: 읽기는 무마찰, **쓰기는 1회 확인**. 확인창은 정확히 하나이고, 격자 밖으로',
    '// UI 규율(reworded control mutant): 읽기는 무마찰, 쓰기는 1회 확인. 격자 밖으로'),
};

// ── main ────────────────────────────────────────────────────────────────────────────────
(async () => {
  const base = await run(SRC);
  if (verbose) base.evidence.forEach(e => console.log('  ' + e));
  console.log(`${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.compared} assertions, `
    + `${base.failures.length} failure(s)`);
  console.log(`ASSERTIONS ${base.compared} ${base.failures.length}`);
  base.failures.forEach(f => console.log(`   ✗ ${f}`));

  let caught = 0, total = 0;
  for (const [name, fn] of Object.entries(MUTANTS)) {
    const isControl = name.startsWith('__control');
    let f = [];
    try { f = (await run(fn(SRC))).failures; }
    catch (e) { f = [`threw: ${String(e && e.message).slice(0, 80)}`]; }
    const newOnes = f.filter(x => !base.failures.includes(x));
    if (isControl) {
      if (newOnes.length > 0) {
        console.log(`   ✗ CONTROL '${name}' was CAUGHT — the assertions are keying on source `
          + 'text, not on behaviour, and the caught count below is decoration');
        base.failures.push(`control mutant '${name}' was caught`);
      } else if (verbose) console.log(`   control '${name}': escaped, as required`);
      continue;
    }
    total++;
    if (newOnes.length > 0) caught++;
    else console.log(`   ✗ mutant '${name}' was NOT caught — the assertions above do not score `
      + 'what they claim to score');
    // EVERY new failure, not just the first. Which assertions a mutant trips is the evidence
    // that they score what they claim to; one truncated line cannot show that, and for the
    // mutant that restores the unbounded write the full list IS the bug report.
    if (verbose) {
      console.log(`   mutant '${name}': ${newOnes.length} new failure(s)`);
      newOnes.forEach(f => console.log(`       · ${f}`));
    }
  }
  console.log(`--- mutation check: ${caught}/${total} defects caught ---`);
  process.exit(base.failures.length === 0 && caught === total ? 0 : 1);
})();
