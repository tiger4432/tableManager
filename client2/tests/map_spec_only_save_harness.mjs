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
const SRC = readFileSync(SRC_PATH, 'utf8');
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
  'readGridFrameControls',
  'validDieRefDisplay', 'applyValidDieRef', 'validDieRefFromControls', 'validDieRefForPush',
  'validDieRefPayload',
  // The merge under test. Sliced, never re-typed: a copy here would let this harness score a
  // preservation rule the product does not implement.
  'mergeStoredGridMeta',
  // [D1] `buildPushGridMetadata` asks this before deciding whether the spec it writes is a
  // declaration or a synthesized stand-in.
  'geometryIsAutoRegistered', 'markGeometryAutoRegistered',
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
      const p = S.getDieIndex(c, r, frame.cols, frame.rows, ROT, SIDE);
      out.set(`${p.x}_${p.y}`, { c, r });
    }
  }
  return out;
}

// ── Sandbox ─────────────────────────────────────────────────────────────────────────────
function buildEnv(src, opts = {}) {
  const requests = [];
  const toasts = [];
  const confirms = [];
  const frame = opts.frame || WIDE;

  const sandbox = {
    console: { warn() {}, log() {}, error() {}, info() {}, debug() {} },
    JSON, Math, Number, Object, Array, String, Boolean, Set, Map, parseInt, parseFloat,
    isNaN, encodeURIComponent, Promise,
    el: makeEl(frame),
    API_BASE: '/api',
    CURRENT_USER: 'tester',
    selectedTable: opts.table || 'bonding_map',
    currentRotation: ROT,
    currentSide: SIDE,
    physFrameOverride: null,
    validDie: opts.validDie || { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    loadedIdentity: opts.loadedIdentity !== undefined
      ? opts.loadedIdentity : { table: 'bonding_map', mapKey: 'LOADED_MAP' },
    serverCellKeys: null,
    gridData: {},
    gridCells2D: {},
    // The identity SOURCE is under test, so this is a stub that deliberately answers something
    // DIFFERENT from `loadedIdentity.mapKey`: if the product read the loaded identity instead
    // of the live controls, the recorded request would carry the wrong key and say so.
    getCurrentMapKey: () => (opts.currentMapKey !== undefined ? opts.currentMapKey : 'CURRENT_MAP'),
    showToast: (msg, kind) => toasts.push({ msg: String(msg), kind }),
    syncValidDieRefControls() {},
    confirm: (text) => { confirms.push(String(text)); return opts.approve !== false; },
    fetch: async (url, init) => {
      const method = (init && init.method) ? init.method : 'GET';
      requests.push({ method, url: String(url), body: init && init.body ? init.body : null });
      const answer = opts.answer ? opts.answer(String(url), method, requests.length) : null;
      if (answer && answer.throwNetwork) throw new Error('network down');
      return {
        ok: answer ? answer.ok !== false : true,
        status: answer && answer.status ? answer.status : 200,
        json: async () => (answer && answer.body !== undefined) ? answer.body : { data: [] },
      };
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

  return { S: sandbox, requests, toasts, confirms };
}

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
    '  if (geometryIsAutoRegistered()) gridMeta.auto_registered = true;',
    '  // mark dropped'),
  // ...and the opposite: it is written unconditionally, which changes the payload of every
  // ordinary map in the database (INV-1).
  'auto-registration-is-written-for-everything': (s) => once(s,
    '  if (geometryIsAutoRegistered()) gridMeta.auto_registered = true;',
    '  gridMeta.auto_registered = true;'),
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
    if (verbose) console.log(`   mutant '${name}': ${newOnes.length} new failure(s)`
      + (newOnes.length ? ` — ${newOnes[0].slice(0, 120)}` : ''));
  }
  console.log(`--- mutation check: ${caught}/${total} defects caught ---`);
  process.exit(base.failures.length === 0 && caught === total ? 0 : 1);
})();
