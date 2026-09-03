// Harness - V1 effort instrument wiring in map_editor.js.
// Run: node client2/tests/effort_instrument_harness.mjs   (no node_modules - vm sandbox)
//
// WHAT THIS PROVES. It executes the REAL function bodies (pushMapData / openMapFrame /
// popMapFrame) lifted verbatim from src, so every assertion below runs the branch it
// claims to test. It does not re-implement them.
//
// Every behavioural check is paired with a MUTATION: the same check is re-run against a
// deliberately defective variant of the same source, and the harness FAILS if the defect
// still passes. A check that cannot fail proves nothing (map-pm lesson: "결함 버전을
// 되돌려 넣어 검증이 실제로 실패하는지 확인").
//
// Extraction technique follows client2/tests/push_gate_harness.mjs.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';
import { loadWithProbe } from './lib/probe.mjs';
// The REAL key composer, not a re-typed one. Group K compares two spellings of the same
// business key and a second implementation here would compare this file against itself.
// `map_key.js` imports nothing, so this needs no node_modules.
import { getMapIdFromMeta as realGetMapIdFromMeta } from '../src/map_key.js';

const SRC_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'map_editor.js');
// Normalized to LF: the file on disk is CRLF, and the mutation patches below match on
// multi-line strings. Without this every multi-line mutation silently fails to apply and
// the mutation suite reports "ok" for defects it never actually injected.
const SRC = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

function extractFunction(src, name) {
  const re = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = re.exec(src);
  if (!m) throw new Error(`function ${name} not found`);
  const i = src.indexOf('{', m.index);
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    const ch = src[j];
    if (ch === '{') depth++;
    else if (ch === '}') { depth--; if (depth === 0) return src.slice(m.index, j + 1); }
  }
  throw new Error(`unbalanced braces for ${name}`);
}

let pass = 0, fail = 0;
function check(name, actual, expected) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; console.log(`  ok   ${name}`); }
  else { fail++; console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`); }
}

// ── Sandbox ─────────────────────────────────────────────────────────────────────
// `log` records what the instrument DID: every fetch body, and every effort call.
// Assertions read this log, so the evidence is a request list, not "it worked".
async function makeCtx(src, opts = {}) {
  const log = { requests: [], effort: [], nav: [], toasts: [], alerts: [], confirms: [] };
  let counters = opts.zeroEffort
    ? { session_id: 'sess-TEST', key: 0, mouse: 0, nav: 0 }
    : { session_id: 'sess-TEST', key: 11, mouse: 7, nav: 2 };

  // `dataset` is REAL, not a stub: the two provenance markers live in it and both writers
  // (`markGeometryAutoRegistered`, `markFrameChosen`) bail on `!input.dataset`, so a fixture
  // without it would turn the thing G23 scores into a silent no-op and read green.
  // ⚠️ It does NOT move any existing expectation: nothing on the push path writes a marker,
  //    so every dataset stays empty and G9's exact-object comparison is unchanged (INV-1).
  const inputEl = (v) => ({ value: String(v), checked: false, textContent: '', disabled: false,
    dataset: {} });
  const el = {
    btnPushMap: { textContent: '', disabled: false },
    colMapX: inputEl('x'), colMapY: inputEl('y'), colMapVal: inputEl('val'),
    gridCols: inputEl(3), gridRows: inputEl(3),
    gridStartX: inputEl(0), gridStartY: inputEl(0),
    gridYInvert: { checked: false },
    physWaferDia: inputEl(300), physChipX: inputEl(2.5), physChipY: inputEl(3.5),
    physOffsetX: inputEl(0.5), physOffsetY: inputEl(0.25), physEdgeMargin: inputEl(3),
    tableSelect: { value: '', options: [{ value: 'bonding_map' }, { value: 'dt_map' }], appendChild() {} },
    // [M4②] The designation controls Push now reads. EMPTY on purpose: "nothing declared,
    // nothing typed" is the state every assertion in this file assumes, and it is what makes
    // the pushed payload byte-identical to 2a9f6c4 (INV-1). `validDieRefForPush` is extracted
    // real, not stubbed, so this file actually executes that branch.
    validDieRefTable: inputEl(''), validDieRefKey: inputEl(''),
  };

  // [Push-path scoring] Optional control overrides. With `opts.controls` absent, `el` above
  // is untouched byte for byte -- every group-A/B expectation is still measured against
  // exactly the fixture it was written for. Group G supplies its own frame on purpose: the
  // A/B fixture has grid_cols === grid_rows and start_x === start_y === 0, which kills the
  // axis-swap and origin-drop defect axes by construction (map-pm: "픽스처가 결함 축을 죽인다").
  for (const [k, v] of Object.entries(opts.controls || {})) {
    if (!el[k]) continue;
    if (typeof v === 'boolean') el[k].checked = v; else el[k].value = String(v);
  }

  // 2 inside non-empty cells -> 2 updates, and nonEmptyOnGrid === 2 so the contrast
  // guard passes (it must not be the thing that short-circuits the push under test).
  const gridCells2D = opts.cells2D || {
    0: { 0: { inside: true, x: 1, y: 1, key: '1_1' }, 1: { inside: true, x: 2, y: 1, key: '2_1' } }
  };

  // 🔴 THE SYMBOLS ARE NO LONGER CUT OUT of map_editor.js and run in `vm`, and this file's
  // own comments record what that cost TWICE: a missing `pushBlockingCount` crashed the
  // sandbox build and left the only end-to-end scorer of the ⚡ Push path scoring NOTHING,
  // and a missing `mapKeyListCache` made every "successful" push throw inside the write path
  // while A1-A11 stayed green. Imported, a name cannot be missing from a list, because there
  // is no list.
  //
  // The globals go on `globalThis`: an imported module resolves them the way the browser
  // does, and setting them on the env would be a silent no-op. `debug` is kept because the
  // success epilogue calls it -- without it that epilogue threw a TypeError into
  // `pushMapData`'s own catch and alerted 「데이터 적재 실패」 on a push that had succeeded.
  const OUT = console;
  // 🔴 `log`, `info` and `error` FORWARD. The sandbox console silenced the module's chatter,
  //    and installing that silence GLOBALLY silences this harness's own output too -- the run
  //    printed one banner and exited 1 with nothing to read. What stays muted is the noise the
  //    module makes by design (`warn`, `debug`, `group`).
  globalThis.console = {
    log: (...a) => OUT.log(...a), info: (...a) => OUT.info(...a),
    error: (...a) => OUT.error(...a),
    warn() {}, debug() {}, group() {}, groupEnd() {},
  };
  globalThis.document = {
    querySelectorAll: () => (opts.metaInputs || [{ id: 'meta-input-map_id', value: 'MAP-1' }]),
    getElementById: () => ({ value: '' }),
    addEventListener() {}, removeEventListener() {}, querySelector: () => null,
  };
  globalThis.window = globalThis.window || {
    location: { port: '', origin: '', protocol: 'http:', host: '', search: '' },
    addEventListener() {},
  };
  // `opts.confirmSeq` answers the dialogs IN ORDER; anything past its end falls back to
  // `opts.confirmAnswer`. Answering by position, not by matching the message text, is
  // deliberate: a scorer that greps a Korean confirm string is pinning wording, and wording
  // is the thing a UI round is allowed to change.
  globalThis.confirm = (msg) => {
    log.confirms.push(msg);
    const i = log.confirms.length - 1;
    if (Array.isArray(opts.confirmSeq) && i < opts.confirmSeq.length) return opts.confirmSeq[i];
    return opts.confirmAnswer !== false;
  };
  globalThis.alert = (msg) => { log.alerts.push(msg); };
  // The write surface under test. Records every request body verbatim.
  //
  // `effort_recorded` is the server's answer to "did I actually write an effort row?". A
  // no-op save (the stored value already equals the submitted one) is a 200 that records
  // NOTHING, so the response carries false. opts.effortRecorded:
  //   undefined -> true (normal), false -> the no-op case, 'absent' -> an older server.
  globalThis.fetch = async (url, init) => {
    const body = init && init.body ? JSON.parse(init.body) : null;
    log.requests.push({ url, method: init && init.method, body });
    const ok = opts.failCellPush && String(url).includes('bonding_map') ? false : true;
    const okBody = { updated_count: 2 };
    if (opts.effortRecorded !== 'absent') okBody.effort_recorded = opts.effortRecorded !== false;
    return { ok, status: ok ? 200 : 500, json: async () => (ok ? okBody : { detail: 'boom' }) };
  };

  // Everything this harness STAGES on the module. `state` is `Object.keys` of it, so a name
  // the module does not declare is a loud failure rather than a property nobody reads.
  const stage = {
    gridCells2D,
    // reassigned below by the call recorder, so it needs a setter rather than a read
    gridData: opts.gridData || { '1_1': 'A', '2_1': 'B' },
    legend: [{ value: 'A', split_desc: 'd' }, { value: 'B', split_desc: 'd' }],
    tableSchema: opts.schema
      || { columns: ['x', 'y', 'val'], column_types: { x: 'number', y: 'number', val: 'string' }, map_key_columns: [] },
    // Read by `physNum` (the whole transform chain below goes through it). Never opened
    // here: the push path is the MAIN load, which is the "source meta == current controls"
    // special case of the frame window (SPEC §5.1).
    // ⑤'s coordinate evidence used to be staged here as `insideCalls`. THE PRODUCT HAS NO
    // SUCH NAME -- it is the harness's own list, and under `vm` a bare identifier is whatever
    // the sandbox says it is. It lives beside the recorder below and rides on the env.
    selectedTable: 'bonding_map',
    loadedIdentity: null, framePushed: false, frameTouched: false, legendDirty: false,
    // [F2b] provenance of the on-screen cells. null = "the server state is unknown", which
    // is what a never-loaded map looks like and what `serverCellKeySet` must answer with.
    serverCellKeys: null,
    legendReplaceScope: null, legendConflict: null, legendSaveState: null,
    // 🔴 The success epilogue invalidates this cache INSIDE the write path, and it was
    // absent from this sandbox -- so every "successful" push in this file threw a
    // ReferenceError right there, was swallowed by `pushMapData`'s catch, and alerted
    // 「데이터 적재 실패」. Nothing noticed: A1-A11 all read state written earlier. That is
    // byte for byte the `dde342c` incident the source comment at this call site records,
    // reproduced inside the harness meant to catch it. G18 now scores the epilogue.
    // 🔴 `mapKeyListCache` is a `const Map` in the product, so it is CLEARED below rather
    //    than replaced -- a const binding cannot be reassigned, and replacing it here would
    //    have left the module reading its own. Same shape as `el`.
    currentRotation: opts.rotation !== undefined ? opts.rotation : 90,
    currentSide: opts.side || 'back',
    editorFrames: [],
    overlayLayers: [],
    // [M4①] pushMapData now carries `valid_die_ref` forward from the loaded meta, so it
    // reads this state. `null` = the map declared nothing, which is what every assertion
    // in this file assumes: the pushed payload must stay byte-identical to 2a9f6c4.
    validDie: opts.validDie !== undefined ? opts.validDie : null,
    // 🔴 `validDieRefTableTouched` WAS STAGED HERE, and THE PRODUCT DELETED IT.
    //    map_editor.js:2461 still mentions the name -- inside a comment recording the
    //    removal and saying the invariant now rests on the key comparison in
    //    `validDieRefFromControls`. A plain grep reads that comment as "it exists".
    //    Under `vm` a bare identifier is whatever the sandbox says it is, so this file went
    //    on staging a flag nobody reads. The probe asks the module, and the module says no.



    // ── collaborators kept deliberately inert ──
    currentIdentityMismatch: () => null,
    setLoadedIdentity(t, k) { ctx.loadedIdentity = t && k ? { table: t, mapKey: k } : null; },
    // `notifyMapContext` is an IMPORT of the subject -- read-only from outside, so it goes
    // through the loader hook rather than being staged here.
    recordLastOpenMap() {}, saveLegendToStorage() {},
    saveLegendToServer: async () => ({ ok: true, count: 2 }),
    applyLegendSaveResult() {},
    snapshotEditorState: () => ({ tag: 'frame' }),
    restoreEditorState() {},
    recomputeActiveOverlays() {}, renderOverlayList() {}, renderBreadcrumb() {},
    renderGridCanvas() {}, renderLegendTable() {},
    switchTableQuiet: async () => {},
    loadExistingMap: async () => (opts.loadResult || { count: 5, mapKey: 'M1' }),
    findPresetByKind: () => null, applyPresetObject() {},
    getCurrentMapKey: () => 'MAP-1',
    frameTitle: () => 't',
  };
  const { probe: ctx } = await loadWithProbe(SRC_PATH, {
    expose: [
    'el', 'mapKeyListCache',
    'effortRoute', 'validDieRefDisplay', 'validDieRefFromControls', 'validDieRefForPush',
    'validDieRefPayload', 'applyValidDieRef', 'validDieBasis', 'eachSavableCell',
    'classifyUnsavableCells', 'serverCellKeySet', 'pushBlockingCount', 'physNum',
    'getTransformedPhysicalConfig', 'getScreenShift', 'isCellInsideWaferFast',
    'confirmLogShapedPushTarget', 'collectMetaFieldValues', 'controlIsSilent', 'gridFrameControlNum',
    'readGridFrameControls', 'geometryIsAutoRegistered', 'frameChosenFrom', 'markFrameChosen',
    'buildPushGridMetadata', 'confirmMissingSplitDescriptions', 'outsideCircleNoteForPush', 'pushMapData',
    'openMapFrame', 'unsavedWorkNotice', 'popMapFrame',
    ],
    // 🔴 `isCellInsideWafer` is here rather than in `expose` because the ⑤ recorder below
    //    REPLACES it. A read-only reference could not be wrapped, and the wrap is how every
    //    call it receives becomes evidence.
    state: [...Object.keys(stage), 'isCellInsideWafer'],
    // `el` is the module's own control registry -- a `const` object the readers look at. It
    // was a sandbox property before, so it is not among the names the old vm block extracted.
    // Filled below rather than replaced, because a `const` binding cannot be reassigned.
    // Eleven of the names this harness stages are IMPORTS of the subject, and no probe can
    // reach an import binding -- it is read-only to everyone but the module that declared it.
    stubs: {
      './config.js': { API_BASE: 'http://x', CURRENT_USER: 'tester' },
      './utils.js': { showToast: (m, t) => { log.toasts.push([m, t]); } },
      './effort_meter.js': {
        // Mirrors the real collector: with nothing accumulated it reports ABSENCE, never an
        // all-zero blob (the server would file that as a genuine measured score of 0).
        effortSnapshot: () => {
          log.effort.push('snapshot');
          if (!counters.key && !counters.mouse && !counters.nav) return undefined;
          return { ...counters };
        },
        effortCommitIfRecorded: (resBody) => {
          const flag = resBody && typeof resBody === 'object' ? resBody.effort_recorded : undefined;
          const known = typeof flag === 'boolean';
          log.effort.push(`commitIfRecorded:${known ? flag : 'absent'}`);
          if (known ? flag : true) { // absent -> legacy fallback (reset on success)
            log.effort.push('commit');
            counters = { ...counters, key: 0, mouse: 0, nav: 0 };
          }
        },
        countNav: (f, t) => { log.nav.push(`${f}>${t}`); },
        ROUTES: { MAP_EDITOR: 'map_editor', GRID: 'grid' },
      },
      './map_key.js': { getMapIdFromMeta: (m) => m.map_id || null },
      './split_registry_row.js': { getMissingDescValues: () => (opts.missingDesc || []) },
      './push_columns.js': {
        logShapedPushDecision: () => (opts.gate4 || { mode: 'clean', extras: [] }),
      },
      './transfer_plan.js': { notifyMapContext: () => {} },
    },
    // `src` is a MUTATE FUNCTION (or null): a mutant is a whole module, so one that fails to
    // parse fails loudly instead of counting as caught.
    mutate: typeof src === 'function' ? src : undefined,
    tag: 'effortinstr',
  });
  const probeInside = ctx.isCellInsideWafer;
  // The success epilogue invalidates this cache INSIDE the write path, and it was absent from
  // the old sandbox -- so every "successful" push threw a ReferenceError right there, was
  // swallowed by `pushMapData`'s catch, and alerted 「데이터 적재 실패」. Nothing noticed:
  // A1-A11 all read state written earlier. Emptied per env so each case starts cold.
  ctx.mapKeyListCache.clear();
  Object.assign(ctx.el, el);
  Object.assign(ctx, stage);
  // ⑤'s call recorder. The sandbox used to wrap `isCellInsideWafer` INSIDE the script; the
  // probe replaces the module's own binding from outside, which is the same thing done where
  // the module can see it. The wrapper adds no arithmetic: it forwards and reports what it was
  // asked and what it said.
  //
  // 🔴 `insideCalls` is the HARNESS's list, not module state -- the product has no such name,
  //    and the probe said so. It rides on the env for the ⑤ checks to read.
  const insideCalls = [];
  const realInside = probeInside;
  ctx.isCellInsideWafer = (c, r, vc, vr) => {
    const v = realInside(c, r, vc, vr);
    insideCalls.push([c, r, vc, vr, v]);
    return v;
  };
  ctx.insideCalls = insideCalls;
  const api = ctx;
  return { ctx, log, api };
}

// A second, much smaller sandbox holding only the TWO readers of the metadata panel that
// compose a map key. Kept separate from `makeCtx` on purpose: `getCurrentMapKey` is a
// function DECLARATION, so extracting it would overwrite the stub the A/B groups depend on.
async function makeKeyCtx(src, schema, metaInputs) {
  // A SECOND probe, and the separation is the same one the sandbox needed: `getCurrentMapKey`
  // is a function DECLARATION, and env ① stages a stub over it for the A/B groups. Two probes
  // are two module instances, so the real one runs here without touching that stub.
  globalThis.document = { querySelectorAll: () => metaInputs,
                          getElementById: () => null, addEventListener() {},
                          removeEventListener() {}, querySelector: () => null };
  globalThis.alert = () => {};
  const stage = { tableSchema: schema };
  const { probe } = await loadWithProbe(SRC_PATH, {
    expose: ['collectMetaFieldValues', 'getCurrentMapKey'],
    state: Object.keys(stage),
    stubs: { './map_key.js': { getMapIdFromMeta: realGetMapIdFromMeta } },
    mutate: typeof src === 'function' ? src : undefined,
    tag: 'effortkey',
  });
  Object.assign(probe, stage);
  return probe;
}

const cellReq = (log) => log.requests.filter(r => String(r.url).includes('/tables/bonding_map/'));
const metaReq = (log) => log.requests.filter(r => String(r.url).includes('wafer_map_metadata'));

// Key order is not the subject of any assertion here, and reordering an object literal is a
// legitimate edit. Compare the record as a mapping, not as a serialization.
const byKey = (o) => Object.fromEntries(Object.keys(o).sort().map(k => [k, o[k]]));
// The grid_metadata the push actually put on the wire, parsed back out of the request body.
const pushedGridMeta = (log) => JSON.parse(metaReq(log)[0].body.updates[0].updates.grid_metadata);
const typed = (v) => `${typeof v}:${JSON.stringify(v)}`;

// Deep, not top-level: double-billing is just as real if a future edit buries the field
// inside `updates[0].updates`. The check must reject effort ANYWHERE in that body.
function hasEffortAnywhere(node) {
  if (!node || typeof node !== 'object') return false;
  if (!Array.isArray(node) && Object.prototype.hasOwnProperty.call(node, 'effort')) return true;
  return Object.values(node).some(hasEffortAnywhere);
}

// ════════════════════════════════════════════════════════════════════════════════
// A. pushMapData — the single reporting point
// ════════════════════════════════════════════════════════════════════════════════
async function groupA(src, label) {
  const r = {};

  // A1/A2/A3 — successful push
  {
    const { log, api } = await makeCtx(src);
    await api.pushMapData();
    r.A1 = cellReq(log).length === 1 ? (cellReq(log)[0].body.effort || null) : 'NO-CELL-REQUEST';
    r.A2 = metaReq(log).map(q => hasEffortAnywhere(q.body) ? 'HAS-EFFORT' : 'none');
    r.A3 = log.effort.join(',');
    r.A4 = log.requests.length;   // exactly 2: metadata + cells (legend save is stubbed out)
  }

  // A5/A6 — failed push: counters must survive
  {
    const { log, api } = await makeCtx(src, { failCellPush: true });
    await api.pushMapData();
    r.A5 = log.effort.join(',');
    r.A6 = cellReq(log)[0].body.effort;
  }

  // A7 — a push refused BEFORE any request must not touch the counters at all
  {
    const { log, api } = await makeCtx(src, { confirmAnswer: false });
    const c = await makeCtx(src, { confirmAnswer: false });
    c.ctx.logShapedPushDecision = () => ({ mode: 'confirm', extras: ['dt_id'] });
    await c.api.pushMapData();
    r.A7 = `${c.log.requests.length}|${c.log.effort.join(',')}`;
    void log; void api;
  }

  // A8/A9 — a 200 that recorded NOTHING must not reset. This is the no-op save: the map
  // was re-pushed unchanged, so no correction happened and no effort row was written.
  // Committing here would delete the effort the push cost, and the operator's next attempt
  // — the one that finally changes something — would report only its own few clicks.
  {
    const { log, api } = await makeCtx(src, { effortRecorded: false });
    await api.pushMapData();
    r.A8 = log.effort.join(',');
    r.A9 = cellReq(log)[0].body.effort;   // the counts still rode with the request
  }

  // A10 — an older server that does not send the flag at all must still reset, or the
  // counter would grow without bound and bill a whole session to one later save.
  {
    const { log, api } = await makeCtx(src, { effortRecorded: 'absent' });
    await api.pushMapData();
    r.A10 = log.effort.join(',');
  }

  // A11 — nothing accumulated: the field must be ABSENT from the wire, not an all-zero
  // blob. The server accepts an explicit zero as a genuine measured score-0 correction,
  // so a phantom here halves the session baseline.
  {
    const { log, api } = await makeCtx(src, { zeroEffort: true });
    await api.pushMapData();
    r.A11 = hasEffortAnywhere(cellReq(log)[0].body) ? 'HAS-EFFORT' : 'none';
  }
  return r;
}

// ════════════════════════════════════════════════════════════════════════════════
// B. frame transitions
// ════════════════════════════════════════════════════════════════════════════════
async function groupB(src) {
  const r = {};

  // B1 — frame push from depth 0 emits exactly one transition
  {
    const { log, api } = await makeCtx(src);
    await api.openMapFrame({ table: 'dt_map', metaValues: { lot: 'L1' }, presetKind: 'tape' });
    r.B1 = log.nav.join(',');
  }
  // B2 — nested push reports the material surface as `from`
  {
    const { ctx, log, api } = await makeCtx(src);
    ctx.editorFrames = [{ tag: 'depth1' }];
    await api.openMapFrame({ table: 'dt_map', metaValues: { lot: 'L1' } });
    r.B2 = log.nav.join(',');
  }
  // B3 — a cancelled open moved no screen
  {
    const { log, api } = await makeCtx(src, { loadResult: { count: 0, cancelled: true } });
    await api.openMapFrame({ table: 'dt_map', metaValues: { lot: 'L1' } });
    r.B3 = log.nav.join(',') || '(none)';
  }
  // B4 — an empty (not-yet-built) material map IS a screen move
  {
    const { log, api } = await makeCtx(src, { loadResult: { count: 0, empty: true } });
    await api.openMapFrame({ table: 'dt_map', metaValues: { lot: 'L1' } });
    r.B4 = log.nav.join(',');
  }
  // B5 — depth guard: a refused push (stack too deep) is not a transition
  {
    const { ctx, log, api } = await makeCtx(src);
    ctx.editorFrames = [1, 2, 3, 4];
    await api.openMapFrame({ table: 'dt_map', metaValues: { lot: 'L1' } });
    r.B5 = log.nav.join(',') || '(none)';
  }
  // B6 — pop back to depth 0
  {
    const { ctx, log, api } = await makeCtx(src);
    ctx.editorFrames = [{ tag: 'parent' }];
    api.popMapFrame();
    r.B6 = log.nav.join(',');
  }
  // B7 — pop to a nested frame lands on the material surface
  {
    const { ctx, log, api } = await makeCtx(src);
    ctx.editorFrames = [{ tag: 'p0' }, { tag: 'p1' }];
    api.popMapFrame();
    r.B7 = log.nav.join(',');
  }
  // B8 — declining the unsaved-edit confirm keeps the user put: no transition
  {
    const { ctx, log, api } = await makeCtx(src, { confirmAnswer: false });
    ctx.editorFrames = [{ tag: 'parent' }];
    ctx.framePushed = false; ctx.frameTouched = true;
    api.popMapFrame();
    r.B8 = log.nav.join(',') || '(none)';
  }
  return r;
}

// ════════════════════════════════════════════════════════════════════════════════
// G. pushMapData's five named steps — the ORCHESTRATION, not the collaborators.
//
// WHY THIS GROUP EXISTS (round R6 §7). `push_gate_harness` scores what
// `logShapedPushDecision` DECIDES; `copy_header_count_harness` executes 50 of this
// function's lines. Nothing scored that `pushMapData` ACTS on those decisions. Nine
// defects were put back into the five steps and every oracle in the repository stayed
// green, including this file once revived. These assertions are those nine defects.
//
// The evidence is always a request list or a coordinate list. "It worked" is not evidence.
// ════════════════════════════════════════════════════════════════════════════════

// ⑤'s frame, chosen so every defect axis is ALIVE: cols 11 != rows 9 (dimension swap),
// chipX 2 != chipY 3 (pitch swap), rot 90 (the swap actually happens), side back (offset
// negation), startX 3 != startY -2 and neither is 0 (origin drop AND origin swap), a 20mm
// wafer with a 1mm edge margin so the circle actually cuts the 9x11 visual grid.
const FRAME = {
  gridCols: 11, gridRows: 9, gridStartX: 3, gridStartY: -2, gridYInvert: true,
  physWaferDia: 20, physChipX: 2, physChipY: 3,
  physOffsetX: 0.5, physOffsetY: 0.25, physEdgeMargin: 1,
};
// The same two cells the A/B groups use, plus the visual (c, r) the note walker reads.
const CELLS2 = {
  0: {
    0: { inside: true, x: 1, y: 1, key: '1_1', c: 0, r: 0 },
    1: { inside: true, x: 2, y: 1, key: '2_1', c: 1, r: 0 },
  }
};
// The full 9x11 visual canvas, every cell an authored valid die and every cell painted.
// That is the M4② template state the outside-circle note exists for, and it is the only
// state in which some `inside` cell can be outside the wafer circle.
const CELLS_FULL = (() => {
  const g = {};
  for (let r = 0; r < 11; r++) { g[r] = {}; for (let c = 0; c < 9; c++)
    g[r][c] = { inside: true, x: c, y: r, key: `${c}_${r}`, c, r }; }
  return g;
})();
const DATA_FULL = (() => {
  const d = {};
  for (let r = 0; r < 11; r++) for (let c = 0; c < 9; c++) d[`${c}_${r}`] = 'A';
  return d;
})();
const TEMPLATE_DIE = { basis: 'template', keys: new Set(['authored']) };
const REF_DIE = { basis: 'ref', keys: new Set(['1_1']), raw: { table: 'dt_map', map_id: 'TPL-9' } };
const NUM_SCHEMA = {
  columns: ['lot', 'slot', 'x', 'y', 'val'],
  column_types: { lot: 'string', slot: 'number', x: 'number', y: 'number', val: 'string' },
  map_key_columns: [],
};

async function groupG(src) {
  const r = {};

  // ── ① gate 4: a log-shaped target is REFUSED, before any dialog ──────────────
  // The near-miss the source records: dt_log opened as a map, ⚡ Push would have
  // replace_map'ed 256 real log rows into editor-fabricated (key, x, y, val) cells.
  {
    const { log, api } = await makeCtx(src, {
      gate4: { mode: 'block', extras: ['dt_id', 'eventtime', 'cx', 'cy', 'dt_eqp'] } });
    await api.pushMapData();
    r.G1 = log.requests.length;                     // nothing reached the server
    r.G2 = log.alerts.length;                       // the refusal did speak
    r.G3 = log.confirms.length;                     // gate 4 is FIRST: no question was asked
  }
  // ...and a declared exception (`map_push_ok`) that the operator ACCEPTS proceeds.
  // Without this the refusal above could be satisfied by a gate that never lets anything
  // through, which is not the contract.
  {
    const { log, api } = await makeCtx(src, { gate4: { mode: 'confirm', extras: ['dt_id'] } });
    await api.pushMapData();
    r.G4 = `${log.requests.length}|${log.confirms.length}|${log.alerts.length}`;
  }
  {
    // ...and DECLINING it stops the push. `confirmSeq` says no to the gate's question ONLY;
    // every later dialog answers yes. A7 looks like it covers this but does not: it declines
    // every confirm, so a gate that ignores its own answer is still stopped one dialog later
    // and the request list never moves. The sequence is what makes the gate's answer the
    // only variable.
    const { log, api } = await makeCtx(src, {
      gate4: { mode: 'confirm', extras: ['dt_id'] }, confirmSeq: [false] });
    await api.pushMapData();
    r.G19 = `${log.requests.length}|${log.confirms.length}`;
  }

  // ── ② the metadata panel ────────────────────────────────────────────────────
  {
    const { log, api } = await makeCtx(src, { metaInputs: [{ id: 'meta-input-lot', value: '' }] });
    await api.pushMapData();
    r.G5 = `${log.requests.length}|${log.alerts.length}`;   // declared but blank -> stop
  }
  {
    // ...and a table that declares NO metadata fields is NOT stopped. This is the second
    // term of the emptiness test; without it "always refuse" would satisfy G5.
    const { log, api } = await makeCtx(src, { metaInputs: [] });
    await api.pushMapData();
    r.G6 = log.requests.length;
  }
  {
    // The type coercion, scored key -> value ON THE WIRE. A `number`-declared column that
    // ships as a string is the "화면은 멀쩡한데 값이 틀린" class: the row is accepted and
    // the column silently holds text.
    const { log, api } = await makeCtx(src, {
      schema: NUM_SCHEMA,
      metaInputs: [{ id: 'meta-input-lot', value: 'L1' }, { id: 'meta-input-slot', value: '7' }] });
    await api.pushMapData();
    const row = cellReq(log)[0].body.updates[0].updates;
    r.G7 = typed(row.slot);      // number-declared
    r.G8 = typed(row.lot);       // string-declared: padding/text must survive untouched
  }

  // ── ③ the pushed wafer_map_metadata record ──────────────────────────────────
  // This is the record the NEXT load and EVERY overlay align through. 18,193 stored-
  // coordinate assertions elsewhere in the repo cannot see it: they compare the
  // coordinates a cell carries, not the frame those coordinates are later read through.
  {
    const { log, api } = await makeCtx(src, { controls: FRAME, cells2D: CELLS2 });
    await api.pushMapData();
    r.G9 = byKey(pushedGridMeta(log));
    r.G10 = 'valid_die_ref' in pushedGridMeta(log);   // nothing declared -> field ABSENT
  }
  {
    // A declaration the operator did not touch must be carried forward VERBATIM. Dropping
    // it re-locks the map to `refused` on the next read, and there is no UI that undoes it.
    const { log, api } = await makeCtx(src, {
      controls: { ...FRAME, validDieRefKey: 'TPL-9' }, cells2D: CELLS2, validDie: REF_DIE });
    await api.pushMapData();
    r.G11 = pushedGridMeta(log).valid_die_ref;
  }

  // ── ④ the split-description gate ────────────────────────────────────────────
  {
    // confirmSeq answers the split confirm NO. If the gate stops refusing, the Clean
    // Replace confirm (unanswered by the sequence, so YES) lets the push through and the
    // request list is what changes -- no wording is compared.
    const { log, api } = await makeCtx(src, { missingDesc: ['A', 'B'], confirmSeq: [false] });
    await api.pushMapData();
    r.G12 = `${log.requests.length}|${log.confirms.length}`;
  }
  {
    // ...and YES proceeds. The gate is a report, not a validity ruling (V1-V5).
    const { log, api } = await makeCtx(src, { missingDesc: ['A', 'B'], confirmSeq: [true] });
    await api.pushMapData();
    r.G13 = `${log.requests.length}|${log.confirms.length}`;
  }

  // ── ⑤ the outside-circle note ───────────────────────────────────────────────
  {
    const { ctx, log, api } = await makeCtx(src, {
      controls: FRAME, cells2D: CELLS_FULL, gridData: DATA_FULL, validDie: TEMPLATE_DIE });
    await api.pushMapData();
    const calls = ctx.insideCalls.slice();
    // The visual frame ⑤ resolved the physical one into. cols 11 / rows 9 under rot 90
    // means 9 visual columns and 11 visual rows; the swap is the defect.
    r.G14 = calls.length > 0 ? `${calls[0][2]}x${calls[0][3]}` : 'NO-CALLS';
    // The coordinate list itself, as an 11-row map: '.' inside the wafer, 'X' outside.
    // Reading a deliberately wrong frame moves cells in this picture; if it did not, the
    // fixture would be proving nothing.
    r.G15 = [];
    for (let row = 0; row < 11; row++) {
      let s = '';
      for (let col = 0; col < 9; col++) {
        const hit = calls.find(k => k[0] === col && k[1] === row);
        s += hit ? (hit[4] ? '.' : 'X') : '?';
      }
      r.G15.push(s);
    }
    // The note is compared against ⑤'s OWN return, never against a hardcoded Korean
    // string: reword it and both sides move together, drop it and only this fails.
    const note = api.outsideCircleNoteForPush(11, 9, 90, ctx.gridCells2D, ctx.gridData);
    const last = log.confirms[log.confirms.length - 1] || '';
    r.G16 = note !== '' && last.includes(note);
  }
  {
    // INV-1: a map whose valid-die basis IS the circle says nothing extra. The confirm
    // must be byte-identical to what it was before ⑤ existed.
    const { ctx, api } = await makeCtx(src, { controls: FRAME, cells2D: CELLS_FULL, gridData: DATA_FULL });
    r.G17 = api.outsideCircleNoteForPush(11, 9, 90, ctx.gridCells2D, ctx.gridData);
  }

  // ── ⑥ [2b] A BLANK FRAME BOX IS NOT A ZERO ──────────────────────────────────
  // `⚡ Push` is `replace_map`: it deletes every row of this map key and re-writes it under the
  // frame in this payload. A blank START box folded to 0 by `parseInt('') || 0` therefore does
  // not merely record a wrong origin — it re-addresses the whole map to it, irreversibly.
  // The predicate is shared with `saveMapSpecOnly` and with `resolveGridFrame`'s `current`
  // branch (`gridFrameControlNum`), so what is scored here is that THIS consumer asks it.
  {
    const { log, api } = await makeCtx(src, { controls: { gridStartX: '' } });
    await api.pushMapData();
    r.G20 = `${log.requests.length}|${log.confirms.length}`;   // nothing sent, nothing asked
    r.G21 = log.toasts.some(t => t[1] === 'error' && /START X/.test(t[0]) && /비어 있/.test(t[0]));
  }
  // 🔴 THE COUNTERFACTUAL IS NOT WRITTEN AGAIN HERE ON PURPOSE. The whole rest of group A and
  //    group G pushes with `gridStartX: 0` TYPED IN and expects requests to go out (A4 = 2,
  //    G18 = success), so "a typed zero still pushes" is already the ambient state of this
  //    file. Restating it would be a second assertion about the same fixture.

  // ── ⑦ [D4] THE FRAME'S OWN PROVENANCE REACHES THE RECORD ────────────────────
  // G9 already pins that an UNMARKED map's payload carries no such key (it compares the whole
  // object). This is the other half: a frame that came out of the coordinate-choice modal must
  // say so in the record the next load and every overlay align through.
  {
    const { ctx, log, api } = await makeCtx(src, { controls: FRAME, cells2D: CELLS2 });
    ctx.markFrameChosen('panel');
    await api.pushMapData();
    r.G22 = pushedGridMeta(log).frame_chosen_from;
  }

  // ── the epilogue, which nothing scored ──────────────────────────────────────
  // A push that succeeded must TOAST success and ALERT nothing. Every statement after the
  // cell PUT -- the serverCellKeys refresh, framePushed, the map-key cache invalidation,
  // the Split Registry save -- runs inside the try, so any one of them throwing turns a
  // completed write into 「데이터 적재 실패」 while the cells are already on the server.
  // That is exactly what `dde342c` did in production for a full round.
  {
    const { log, api } = await makeCtx(src);
    await api.pushMapData();
    r.G18 = `${log.alerts.length}|${log.toasts.map(t => t[1]).join(',')}`;
  }
  return r;
}

// ════════════════════════════════════════════════════════════════════════════════
// K. TWO SPELLINGS OF THE SAME MAP KEY — invariant ⑥ applied to the business key.
//
// 🔴 THESE ASSERTIONS RECORD A DEFECT, THEY DO NOT BLESS IT. `collectMetaFieldValues`
//    (the push path) type-coerces the panel per `column_types` before composing;
//    `getCurrentMapKey` composes from raw trimmed strings. `canonicalKeyValue` absorbs
//    the difference for every integer-shaped value, which is why nobody has noticed --
//    but not for a non-integral padded value or an unreadable one. K4/K5 below are the
//    two reachable divergences, pinned so they cannot drift further unseen.
//
//    `currentIdentityMismatch()` (the ⚡ Push guard) uses the UNTYPED spelling while
//    `loadedIdentity.mapKey` after a push is the TYPED one, so the guard can fire
//    "로드한 맵과 적재 대상이 다릅니다" on the map that was just pushed.
//
//    WHEN THE FIX LANDS, K4 AND K5 GO RED. That is the point: the fix round must come
//    back here and collapse each pair to one spelling, deliberately and on the record.
// ════════════════════════════════════════════════════════════════════════════════
async function groupK(src) {
  const numeric = {
    columns: ['lot', 'slot'],
    column_types: { lot: 'string', slot: 'number' },
    map_key_columns: ['lot', 'slot'],
  };
  const textual = { ...numeric, column_types: { lot: 'string', slot: 'string' } };
  const spell = async (slotVal, schema) => {
    const api = await makeKeyCtx(src, schema, [
      { id: 'meta-input-lot', value: 'L1' }, { id: 'meta-input-slot', value: slotVal }]);
    const push = realGetMapIdFromMeta(api.collectMetaFieldValues(schema).metaValues, schema)
      || 'default_map';
    const read = api.getCurrentMapKey();
    return `${push}|${read}`;
  };
  // Each `spell` builds an env, which is an import now, so the six are awaited IN ORDER.
  // Left as an object literal of promises they would all be pending when the comparison ran.
  return {
    K1: await spell('07', numeric),
    K2: await spell('7.0', numeric),
    K3: await spell('1e3', numeric),
    K4: await spell('007.5', numeric),   // 🔴 diverges
    K5: await spell('ABC', numeric),     // 🔴 diverges
    K6: await spell('07', textual),      // a string column keeps its padding on BOTH sides
  };
}

// ════════════════════════════════════════════════════════════════════════════════
const EXPECT_A = {
  A1: { session_id: 'sess-TEST', key: 11, mouse: 7, nav: 2 },
  A2: ['none'],
  A3: 'snapshot,commitIfRecorded:true,commit',
  A4: 2,
  A5: 'snapshot',
  A6: { session_id: 'sess-TEST', key: 11, mouse: 7, nav: 2 },
  A7: '0|',
  A8: 'snapshot,commitIfRecorded:false',                 // asked, told no, did NOT commit
  A9: { session_id: 'sess-TEST', key: 11, mouse: 7, nav: 2 },
  A10: 'snapshot,commitIfRecorded:absent,commit',        // legacy fallback
  A11: 'none'                                            // absence, not a measured zero
};
const EXPECT_B = {
  B1: 'map_editor>map_editor:material',
  B2: 'map_editor:material>map_editor:material',
  B3: '(none)',
  B4: 'map_editor>map_editor:material',
  B5: '(none)',
  B6: 'map_editor:material>map_editor',
  B7: 'map_editor:material>map_editor:material',
  B8: '(none)'
};
const EXPECT_G = {
  G1: 0,                    // ① a log-shaped BLOCK reaches the server with nothing
  G2: 1,                    // ① ...and says so once
  G3: 0,                    // ① ...having asked nothing first
  G4: '2|2|0',              // ① a declared exception, accepted, proceeds
  G5: '0|1',                // ② declared-but-blank metadata stops the push
  G6: 2,                    // ② a table with no metadata fields is not stopped
  G7: 'number:7',           // ② a number-declared column ships as a number
  G8: 'string:"L1"',        // ② a string-declared column ships untouched
  G9: {                     // ③ the frame the next load will align through
    grid_cols: 11, grid_rows: 9, grid_start_x: 3, grid_start_y: -2, grid_y_invert: true,
    phys_chip_x: 2, phys_chip_y: 3, phys_edge_margin: 1,
    phys_offset_x: 0.5, phys_offset_y: 0.25, phys_wafer_dia: 20,
    rotation: 90, side: 'back',
  },
  G10: false,               // ③ nothing declared -> no valid_die_ref key at all
  G11: { table: 'dt_map', map_id: 'TPL-9' },   // ③ an untouched declaration survives
  G12: '0|1',               // ④ declined -> refused after exactly one question
  G13: '2|2',               // ④ accepted -> proceeds
  G14: '9x11',              // ⑤ rot 90 on an 11x9 grid is a 9x11 visual frame
  // ⑤ the coordinate list, as the wafer silhouette the real transform draws over the 9x11
  // visual frame. '.' inside, 'X' outside; 30 of 99 painted cells are inside. This is a
  // CHARACTERIZATION list: it was recorded from the real `isCellInsideWafer` chain, not
  // re-derived. What makes it worth anything is that reading the frame the wrong way round
  // moves 18 of the 99 cells (measured -- see the I5b mutant), so it is not a picture that
  // any interpretation would have produced.
  //
  // 🔴 AND THE COUNT DOES NOT MOVE. The swapped frame leaves exactly 30 cells inside, so the
  //    note still reads 「원 밖 셀: 69건」 -- byte for byte the same sentence about a
  //    different 69 cells. An assertion on the number, or on the note text, would have seen
  //    NOTHING. Only the per-cell list can tell these two apart. (map-pm: 좌표 검증은
  //    키→값 단위로.)
  G15: ['XXXXXXXXX', 'XXXXXXXXX', 'XXX...XXX', 'XXX...XXX', 'XX.....XX', 'XX.....XX',
    'XX.....XX', 'XX.....XX', 'XXX...XXX', 'XXXX.XXXX', 'XXXXXXXXX'],
  G16: true,                // ⑤ the note is produced and is what the operator was shown
  G17: '',                  // ⑤ a circle-basis map says nothing extra (INV-1)
  G18: '0|success',         // the epilogue completed: no failure alert, one success toast
  G19: '0|1',               // ① a declared exception, DECLINED, refuses after one question
  G20: '0|0',               // ⑥ a blank START box: nothing sent, and nothing asked first
  G21: true,                // ⑥ ...and the operator is told WHICH box, and that it is empty
  G22: 'panel',             // ⑦ a chosen frame says so in the record it writes
};
const EXPECT_K = {
  K1: 'L1_7|L1_7',
  K2: 'L1_7|L1_7',
  K3: 'L1_1000|L1_1000',
  K4: 'L1_7.5|L1_007.5',    // 🔴 RECORDED DEFECT — two spellings of one business key
  K5: 'L1_NaN|L1_ABC',      // 🔴 RECORDED DEFECT — and the typed one invents 'NaN'
  K6: 'L1_07|L1_07',
};

console.log('\n=== A. pushMapData: effort rides the cell batch, resets only on success ===');
const a = await groupA(SRC);
for (const k of Object.keys(EXPECT_A)) check(k, a[k], EXPECT_A[k]);

console.log('\n=== B. screen transitions: one countNav per completed move ===');
const b = await groupB(SRC);
for (const k of Object.keys(EXPECT_B)) check(k, b[k], EXPECT_B[k]);

console.log('\n=== G. the five named steps of the write path: refusals, payload, frame ===');
const g = await groupG(SRC);
for (const k of Object.keys(EXPECT_G)) check(k, g[k], EXPECT_G[k]);

console.log('\n=== K. two spellings of one map key (invariant ⑥ — RECORDED, not blessed) ===');
const kk = await groupK(null);
for (const k of Object.keys(EXPECT_K)) check(k, kk[k], EXPECT_K[k]);

// ════════════════════════════════════════════════════════════════════════════════
// C. MUTATION — each defect must make the checks above FAIL.
//    A green harness against a broken source means the harness verified nothing.
// ════════════════════════════════════════════════════════════════════════════════
console.log('\n=== C. mutation: defect variants must break the checks ===');

const MUTANTS = [
  {
    name: 'M1 commit moved off the success branch (resets on every attempt)',
    apply: s => s
      .replace('      effortCommitIfRecorded(result);\n', '')
      .replace('  el.btnPushMap.textContent = \'⚡ Pushing...\';',
               '  effortCommitIfRecorded({ effort_recorded: true });\n  el.btnPushMap.textContent = \'⚡ Pushing...\';'),
    group: 'A', breaks: ['A3', 'A5']
  },
  {
    name: 'M8 commit ignores what the server said (resets on a no-op save, erasing the effort)',
    apply: s => s.replace('effortCommitIfRecorded(result);',
                          'effortCommitIfRecorded({ effort_recorded: true });'),
    group: 'A', breaks: ['A8']
  },
  {
    name: 'M2 effort field dropped from the cell payload',
    apply: s => s.replace('    effort: effortSnapshot()\n  };', '  };'),
    group: 'A', breaks: ['A1']
  },
  {
    name: 'M3 effort ALSO attached to the wafer_map_metadata push (double billing)',
    apply: s => s.replace(
      '        updated_by: CURRENT_USER\n      }]\n    };',
      '        updated_by: CURRENT_USER\n      }],\n      effort: effortSnapshot()\n    };'),
    group: 'A', breaks: ['A2']
  },
  {
    name: 'M3b same double billing, buried one level deeper (deep-scan check)',
    apply: s => s.replace(
      '          grid_metadata: gridMetaStr\n        },',
      '          grid_metadata: gridMetaStr\n        },\n        effort: effortSnapshot(),'),
    group: 'A', breaks: ['A2']
  },
  {
    name: 'M4 frame-push nav emitted before the load instead of after (counts cancels)',
    apply: s => s
      .replace('    countNav(navFrom, ROUTE_MATERIAL);\n', '')
      .replace('    await switchTableQuiet(spec.table);',
               '    await switchTableQuiet(spec.table);\n    countNav(navFrom, ROUTE_MATERIAL);'),
    // B5 (stack-too-deep) returns before this line either way, so it is NOT in `breaks`.
    group: 'B', breaks: ['B3']
  },
  {
    name: 'M5 `from` captured after the push (frame depth already incremented)',
    apply: s => s.replace(
      '  const navFrom = effortRoute();\n  const frame = snapshotEditorState();',
      '  const frame = snapshotEditorState();\n  let navFrom;'
    ).replace('    editorFrames.push(frame);', '    editorFrames.push(frame);\n    navFrom = effortRoute();'),
    group: 'B', breaks: ['B1']
  },
  {
    name: 'M6 pop nav emitted before the pop (reports the surface it left, not the one it landed on)',
    apply: s => s.replace(
      '  const frame = editorFrames.pop();\n  restoreEditorState(frame);\n  // [V1 effort instrument] After the pop',
      '  countNav(ROUTE_MATERIAL, effortRoute());\n  const frame = editorFrames.pop();\n  restoreEditorState(frame);\n  // [V1 effort instrument] After the pop'
    ).replace('  countNav(ROUTE_MATERIAL, effortRoute());\n  renderBreadcrumb();', '  renderBreadcrumb();'),
    group: 'B', breaks: ['B6']
  },
  {
    name: 'M7 pop nav emitted before the unsaved-edit confirm (counts a move the user declined)',
    // ⚠️ RE-ANCHORED 2026-08-04 ([fix E-3]). The old anchor was `  const dirty = !framePushed
    //    && frameTouched`, which no longer exists — the predicate moved into
    //    `unsavedWorkNotice()` so the map-replacing load could ask the same question. The
    //    anchor now carries popMapFrame's OWN first sentence, because `  const notice =
    //    unsavedWorkNotice();` alone is a substring of the load door's four-space copy, which
    //    sits ~3000 lines EARLIER — a first-match replace would have mutated that function
    //    instead and left this one untouched.
    // ⚠️ This mutant's silent disarming is also a note about the runner: `mutated === SRC` did
    //    not fire, because the SECOND `.replace` below still applied. A two-replace mutant
    //    whose first anchor drifts is only caught by its `breaks:` list going green.
    apply: s => s.replace(
      '  const notice = unsavedWorkNotice();\n  if (notice && !confirm(\n    `이 맵의 편집을 저장하지 않았습니다.',
      '  countNav(ROUTE_MATERIAL, ROUTE_MAIN);\n  const notice = unsavedWorkNotice();\n  if (notice && !confirm(\n    `이 맵의 편집을 저장하지 않았습니다.'
    ).replace('  countNav(ROUTE_MATERIAL, effortRoute());\n  renderBreadcrumb();', '  renderBreadcrumb();'),
    group: 'B', breaks: ['B8']
  },

  // ── the nine defects R6 §7a put back into the five named steps ──────────────
  // Every one of them was scored against nine suites, six contracts and this harness and
  // NOT ONE moved a number. They are the specification for group G.
  //
  // ⚠️ ALL of these anchor on SOURCE TEXT, like every other mutant in this file. What
  //    breaks them is a reword or a re-indent of the anchored lines, and the harness says
  //    so loudly (`mutation did not apply`) rather than passing. The anchors are listed in
  //    the round report so the next extraction round is not surprised.
  {
    name: 'I1 ① a log-shaped BLOCK never refuses (the dt_log destruction near-miss)',
    apply: s => s.replace('      );\n      return false;\n    }\n  }', '      );\n    }\n  }'),
    group: 'G', breaks: ['G1', 'G3']
  },
  {
    name: 'I1b ① a declined `map_push_ok` confirm proceeds anyway',
    apply: s => s.replace('      )) {\n        return false;\n      }', '      )) {\n        void 0;\n      }'),
    group: 'G', breaks: ['G19']
  },
  {
    name: 'I2 ② an empty metadata panel is accepted',
    apply: s => s.replace('return { ok: false, metaValues };', 'return { ok: true, metaValues };'),
    group: 'G', breaks: ['G5']
  },
  {
    name: 'I2b ② number-declared metadata columns written as strings',
    apply: s => s.replace(
      `metaValues[col] = colType === 'number' ? Number(val) : val;`,
      'metaValues[col] = val;'),
    group: 'G', breaks: ['G7']
  },
  {
    name: 'I3 ③ the pushed spec loses the frame origin (grid_start_x/y := 0)',
    apply: s => s.replace('    grid_start_x: startX,\n    grid_start_y: startY,',
                          '    grid_start_x: 0,\n    grid_start_y: 0,'),
    group: 'G', breaks: ['G9']
  },
  {
    name: 'I3b ③ the declaration is destroyed (valid_die_ref raw not carried)',
    apply: s => s.replace(
      '  const gridMetaOut = validDieRefPayload(gridMeta, validDieDecision,\n    validDie ? validDie.raw : undefined);',
      '  const gridMetaOut = validDieRefPayload(gridMeta, validDieDecision,\n    undefined);'),
    group: 'G', breaks: ['G11']
  },
  {
    // [2b] Today's expression, restored: silence folds to the default and `replace_map`
    // re-addresses the whole map to an origin nobody typed.
    name: 'I3c ⑥ a blank frame box resolves to the default again',
    apply: s => s.replace(
      '  const raw = input ? input.value : undefined;\n  if (controlIsSilent(raw)) return null;',
      '  const raw = input ? input.value : undefined;\n  if (controlIsSilent(raw)) return dflt;'),
    group: 'G', breaks: ['G20', 'G21']
  },
  {
    // ...and the shape this codebase actually reaches by accident: the question exists, and
    // one of its three consumers forgets to consult it.
    name: 'I3d ⑥ the PUSH writer stops asking about blanks (the other two still ask)',
    apply: s => s.replace(
      '  if (panel.silent.length > 0) {\n'
      + "    showToast(`${panel.silent.join(' · ')} 칸이 비어 있어 적재하지 않았습니다 — `",
      '  if (false) {\n'
      + "    showToast(`${panel.silent.join(' · ')} 칸이 비어 있어 적재하지 않았습니다 — `"),
    group: 'G', breaks: ['G20', 'G21']
  },
  {
    // [D4] The frame's provenance is dropped on the way out, so a frame that came from the
    // modal is written back as an ordinary declaration and can never be told apart again.
    name: 'I3e ⑦ the frame choice never reaches the record',
    apply: s => s.replace('  if (chosenFrom) gridMeta.frame_chosen_from = chosenFrom;',
                          '  // choice dropped'),
    group: 'G', breaks: ['G22']
  },
  {
    // ...and the mirror, which moves the payload of every ordinary map (INV-1). G9 is the
    // assertion that catches it, which is why G9 compares the WHOLE object.
    name: 'I3f ⑦ the frame choice is written for everything',
    apply: s => s.replace('  if (chosenFrom) gridMeta.frame_chosen_from = chosenFrom;',
                          "  gridMeta.frame_chosen_from = chosenFrom || 'panel';"),
    group: 'G', breaks: ['G9']
  },
  {
    name: 'I4 ④ the split-description gate never refuses',
    apply: s => s.replace('    if (!okMissing) return false;', '    if (!okMissing) void 0;'),
    group: 'G', breaks: ['G12']
  },
  {
    name: 'I5 ⑤ the outside-circle note is never produced',
    apply: s => s.replace('    if (n > 0) outsideNote = ', '    if (false) outsideNote = '),
    group: 'G', breaks: ['G16']
  },
  {
    name: 'I5b ⑤ the note counts with the axes swapped under rotation',
    apply: s => s.replace(
      '    const isRot = (currentRotation === 90 || currentRotation === 270);\n'
      + '    const visualCols = isRot ? rows : cols;\n    const visualRows = isRot ? cols : rows;',
      '    const isRot = (currentRotation === 90 || currentRotation === 270);\n'
      + '    const visualCols = isRot ? cols : rows;\n    const visualRows = isRot ? rows : cols;'),
    group: 'G', breaks: ['G14', 'G15']
  },
  {
    // Not a defect: the CANDIDATE FIX for the two spellings, injected to prove K4/K5 bite.
    // Making `getCurrentMapKey` coerce the way the push path does collapses both pairs.
    // If the fix round lands this (or its mirror image), K goes red and has to be updated
    // deliberately -- which is the whole reason K exists.
    name: 'K-fix `getCurrentMapKey` type-coerces like the push path (the pairs collapse)',
    apply: s => s.replace(
      `    if (val !== '') dict[col] = val;`,
      `    if (val !== '') dict[col] = (tableSchema.column_types[col] === 'number') ? Number(val) : val;`),
    group: 'K', breaks: ['K4', 'K5']
  },
];

// ── controls: mutations that must ESCAPE ────────────────────────────────────────
// An assertion caught by one of these is pinning TEXT, not behaviour. Text-pinning is how
// three harnesses died this month, so the escape is scored, not assumed.
const CONTROLS = [
  {
    name: 'C1 consistent rename of a pushMapData local (metaRead -> metaReadResult)',
    apply: s => s.replace(
      '  const metaRead = collectMetaFieldValues(tableSchema);\n'
      + '  if (!metaRead.ok) return;\n  const metaValues = metaRead.metaValues;',
      '  const metaReadResult = collectMetaFieldValues(tableSchema);\n'
      + '  if (!metaReadResult.ok) return;\n  const metaValues = metaReadResult.metaValues;'),
  },
  {
    name: 'C2 comment-only edit inside the write path',
    apply: s => s.replace('  // Always push dedicated wafer_map_metadata record',
      '  // Always push the dedicated wafer_map_metadata record (control mutation: comment only)'),
  },
];

// 🔴 The group functions take a MUTATE FUNCTION now (or null), not source text. `spec.mutate`
//    ignores a string, so passing the mutated text would load the UNMUTATED module and every
//    mutant would report「STILL PASSED against the defect」-- which is exactly what it did.
const RUN = { A: groupA, B: groupB, G: groupG, K: async s => groupK(s) };
const EXPECTED = { A: EXPECT_A, B: EXPECT_B, G: EXPECT_G, K: EXPECT_K };

for (const m of MUTANTS) {
  const mutated = m.apply(SRC);
  if (mutated === SRC) { fail++; console.error(`  FAIL ${m.name}: mutation did not apply (source drifted)`); continue; }
  let got;
  try {
    got = await RUN[m.group](() => mutated);
  } catch (e) {
    console.log(`  ok   ${m.name} -> threw (${e.message.slice(0, 48)})`);
    pass++; continue;
  }
  const expected = EXPECTED[m.group];
  const actuallyBroke = m.breaks.filter(k => JSON.stringify(got[k]) !== JSON.stringify(expected[k]));
  if (actuallyBroke.length === m.breaks.length) {
    pass++;
    console.log(`  ok   ${m.name} -> ${actuallyBroke.map(k => `${k} became ${JSON.stringify(got[k])}`).join('; ')}`);
  } else {
    fail++;
    const survived = m.breaks.filter(k => !actuallyBroke.includes(k));
    console.error(`  FAIL ${m.name} -> checks ${survived.join(',')} STILL PASSED against the defect`);
  }
}

console.log('\n=== D. control mutations: these must ESCAPE every assertion above ===');
for (const c of CONTROLS) {
  const mutated = c.apply(SRC);
  if (mutated === SRC) {
    fail++;
    console.error(`  FAIL ${c.name}: control did not apply (source drifted) — it proves nothing`);
    continue;
  }
  for (const grp of ['A', 'B', 'G', 'K']) {
    let got;
    try { got = await RUN[grp](() => mutated); }
    catch (e) { got = { __threw: e.message }; }
    // Compared as a MAPPING: the order in which a group happens to fill its result object
    // is not behaviour, and a control that "failed" on key order would be pinning the
    // harness's own bookkeeping instead of the product.
    check(`${c.name} :: group ${grp} escapes`, byKey(got), byKey(EXPECTED[grp]));
  }
}

console.log(`\n${fail === 0 ? 'PASS' : 'FAIL'} — ${pass} passed, ${fail} failed`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail === 0 ? 0 : 1);
