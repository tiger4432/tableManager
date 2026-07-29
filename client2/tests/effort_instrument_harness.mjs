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
function makeCtx(src, opts = {}) {
  const log = { requests: [], effort: [], nav: [], toasts: [], alerts: [], confirms: [] };
  let counters = opts.zeroEffort
    ? { session_id: 'sess-TEST', key: 0, mouse: 0, nav: 0 }
    : { session_id: 'sess-TEST', key: 11, mouse: 7, nav: 2 };

  const inputEl = (v) => ({ value: String(v), checked: false, textContent: '', disabled: false });
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

  // 2 inside non-empty cells -> 2 updates, and nonEmptyOnGrid === 2 so the contrast
  // guard passes (it must not be the thing that short-circuits the push under test).
  const gridCells2D = {
    0: { 0: { inside: true, x: 1, y: 1, key: '1_1' }, 1: { inside: true, x: 2, y: 1, key: '2_1' } }
  };

  const ctx = {
    console: { log() {}, warn() {}, error() {}, group() {}, groupEnd() {} },
    JSON, Object, Array, Number, String, Set, Map, Boolean, Math, Promise,
    parseInt, parseFloat, isNaN, Error,
    API_BASE: 'http://x', CURRENT_USER: 'tester',
    el, gridCells2D,
    gridData: { '1_1': 'A', '2_1': 'B' },
    legend: [{ value: 'A', split_desc: 'd' }, { value: 'B', split_desc: 'd' }],
    tableSchema: { columns: ['x', 'y', 'val'], column_types: { x: 'number', y: 'number', val: 'string' }, map_key_columns: [] },
    selectedTable: 'bonding_map',
    loadedIdentity: null, framePushed: false, frameTouched: false, legendDirty: false,
    // [F2b] provenance of the on-screen cells. null = "the server state is unknown", which
    // is what a never-loaded map looks like and what `serverCellKeySet` must answer with.
    serverCellKeys: null,
    legendReplaceScope: null, legendConflict: null, legendSaveState: null,
    currentRotation: 90, currentSide: 'back',
    editorFrames: [],
    overlayLayers: [],
    // [M4①] pushMapData now carries `valid_die_ref` forward from the loaded meta, so it
    // reads this state. `null` = the map declared nothing, which is what every assertion
    // in this file assumes: the pushed payload must stay byte-identical to 2a9f6c4.
    validDie: null,
    // [M4② F1] the designation controls only mean "the user chose this" once the change
    // listener says so; false is the boot state and the state after every app-driven sync.
    validDieRefTableTouched: false,

    document: {
      querySelectorAll: () => [{ id: 'meta-input-map_id', value: 'MAP-1' }],
      getElementById: () => ({ value: '' }),
    },
    confirm: (msg) => { log.confirms.push(msg); return opts.confirmAnswer !== false; },
    alert: (msg) => { log.alerts.push(msg); },
    showToast: (m, t) => { log.toasts.push([m, t]); },

    // The write surface under test. Records every request body verbatim.
    //
    // `effort_recorded` is the server's answer to "did I actually write an effort row?".
    // A no-op save (the stored value already equals the submitted one) is a 200 that
    // records NOTHING, so the response carries false. opts.effortRecorded:
    //   undefined -> true (normal), false -> the no-op case, 'absent' -> an older server.
    fetch: async (url, init) => {
      const body = init && init.body ? JSON.parse(init.body) : null;
      log.requests.push({ url, method: init && init.method, body });
      const ok = opts.failCellPush && String(url).includes('bonding_map') ? false : true;
      const okBody = { updated_count: 2 };
      if (opts.effortRecorded !== 'absent') okBody.effort_recorded = opts.effortRecorded !== false;
      return { ok, status: ok ? 200 : 500, json: async () => (ok ? okBody : { detail: 'boom' }) };
    },

    // ── the collector, stubbed at the module boundary ──
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

    // ── collaborators kept deliberately inert ──
    logShapedPushDecision: () => ({ mode: 'clean', extras: [] }),
    currentIdentityMismatch: () => null,
    getMapIdFromMeta: (m) => m.map_id || null,
    getMissingDescValues: () => [],
    setLoadedIdentity(t, k) { ctx.loadedIdentity = t && k ? { table: t, mapKey: k } : null; },
    notifyMapContext() {}, recordLastOpenMap() {}, saveLegendToStorage() {},
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
  ctx.globalThis = ctx;
  vm.createContext(ctx);

  vm.runInContext([
    `const ROUTE_MAIN = ROUTES.MAP_EDITOR;`,
    `const ROUTE_MATERIAL = \`\${ROUTES.MAP_EDITOR}:material\`;`,
    extractFunction(src, 'effortRoute'),
    // [M4②] real, not stubbed - the push branch that decides whether `valid_die_ref`
    // appears in grid_metadata at all
    extractFunction(src, 'validDieRefDisplay'),
    extractFunction(src, 'validDieRefFromControls'),
    extractFunction(src, 'validDieRefForPush'),
    // the decision -> payload turn. Extracted out of pushMapData so it can be scored
    // instead of retyped; pushMapData now CALLS it, so it must be here or pushMapData
    // throws at the push point.
    extractFunction(src, 'validDieRefPayload'),
    extractFunction(src, 'applyValidDieRef'),
    extractFunction(src, 'validDieBasis'),
    // [F2] the ONE savable-cell predicate. `pushMapData` no longer restates the
    // `inside` + non-empty walk - it calls this, and so do the on-screen counters, so
    // "화면 수량 == 저장 수량" cannot drift. Same reason as validDieRefPayload above:
    // extracted so it can be scored, therefore it must be in this sandbox.
    extractFunction(src, 'eachSavableCell'),
    // [F2b] the complement of that predicate: which non-empty cells will NOT be saved, and
    // which of those the server demonstrably never sent. `pushMapData`'s data-protection
    // gate calls it, so it must be here too. Scored in copy_header_count_harness.mjs; here
    // it just has to be the REAL one, because the effort assertions below depend on the
    // push actually reaching the request.
    extractFunction(src, 'classifyUnsavableCells'),
    extractFunction(src, 'serverCellKeySet'),
    extractFunction(src, 'pushMapData'),
    extractFunction(src, 'openMapFrame'),
    extractFunction(src, 'popMapFrame'),
    `globalThis.__h = { pushMapData, openMapFrame, popMapFrame, effortRoute };`
  ].join('\n\n'), ctx);

  return { ctx, log, api: ctx.__h };
}

const cellReq = (log) => log.requests.filter(r => String(r.url).includes('/tables/bonding_map/'));
const metaReq = (log) => log.requests.filter(r => String(r.url).includes('wafer_map_metadata'));

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
    const { log, api } = makeCtx(src);
    await api.pushMapData();
    r.A1 = cellReq(log).length === 1 ? (cellReq(log)[0].body.effort || null) : 'NO-CELL-REQUEST';
    r.A2 = metaReq(log).map(q => hasEffortAnywhere(q.body) ? 'HAS-EFFORT' : 'none');
    r.A3 = log.effort.join(',');
    r.A4 = log.requests.length;   // exactly 2: metadata + cells (legend save is stubbed out)
  }

  // A5/A6 — failed push: counters must survive
  {
    const { log, api } = makeCtx(src, { failCellPush: true });
    await api.pushMapData();
    r.A5 = log.effort.join(',');
    r.A6 = cellReq(log)[0].body.effort;
  }

  // A7 — a push refused BEFORE any request must not touch the counters at all
  {
    const { log, api } = makeCtx(src, { confirmAnswer: false });
    const c = makeCtx(src, { confirmAnswer: false });
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
    const { log, api } = makeCtx(src, { effortRecorded: false });
    await api.pushMapData();
    r.A8 = log.effort.join(',');
    r.A9 = cellReq(log)[0].body.effort;   // the counts still rode with the request
  }

  // A10 — an older server that does not send the flag at all must still reset, or the
  // counter would grow without bound and bill a whole session to one later save.
  {
    const { log, api } = makeCtx(src, { effortRecorded: 'absent' });
    await api.pushMapData();
    r.A10 = log.effort.join(',');
  }

  // A11 — nothing accumulated: the field must be ABSENT from the wire, not an all-zero
  // blob. The server accepts an explicit zero as a genuine measured score-0 correction,
  // so a phantom here halves the session baseline.
  {
    const { log, api } = makeCtx(src, { zeroEffort: true });
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
    const { log, api } = makeCtx(src);
    await api.openMapFrame({ table: 'dt_map', metaValues: { lot: 'L1' }, presetKind: 'tape' });
    r.B1 = log.nav.join(',');
  }
  // B2 — nested push reports the material surface as `from`
  {
    const { ctx, log, api } = makeCtx(src);
    ctx.editorFrames = [{ tag: 'depth1' }];
    await api.openMapFrame({ table: 'dt_map', metaValues: { lot: 'L1' } });
    r.B2 = log.nav.join(',');
  }
  // B3 — a cancelled open moved no screen
  {
    const { log, api } = makeCtx(src, { loadResult: { count: 0, cancelled: true } });
    await api.openMapFrame({ table: 'dt_map', metaValues: { lot: 'L1' } });
    r.B3 = log.nav.join(',') || '(none)';
  }
  // B4 — an empty (not-yet-built) material map IS a screen move
  {
    const { log, api } = makeCtx(src, { loadResult: { count: 0, empty: true } });
    await api.openMapFrame({ table: 'dt_map', metaValues: { lot: 'L1' } });
    r.B4 = log.nav.join(',');
  }
  // B5 — depth guard: a refused push (stack too deep) is not a transition
  {
    const { ctx, log, api } = makeCtx(src);
    ctx.editorFrames = [1, 2, 3, 4];
    await api.openMapFrame({ table: 'dt_map', metaValues: { lot: 'L1' } });
    r.B5 = log.nav.join(',') || '(none)';
  }
  // B6 — pop back to depth 0
  {
    const { ctx, log, api } = makeCtx(src);
    ctx.editorFrames = [{ tag: 'parent' }];
    api.popMapFrame();
    r.B6 = log.nav.join(',');
  }
  // B7 — pop to a nested frame lands on the material surface
  {
    const { ctx, log, api } = makeCtx(src);
    ctx.editorFrames = [{ tag: 'p0' }, { tag: 'p1' }];
    api.popMapFrame();
    r.B7 = log.nav.join(',');
  }
  // B8 — declining the unsaved-edit confirm keeps the user put: no transition
  {
    const { ctx, log, api } = makeCtx(src, { confirmAnswer: false });
    ctx.editorFrames = [{ tag: 'parent' }];
    ctx.framePushed = false; ctx.frameTouched = true;
    api.popMapFrame();
    r.B8 = log.nav.join(',') || '(none)';
  }
  return r;
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

console.log('\n=== A. pushMapData: effort rides the cell batch, resets only on success ===');
const a = await groupA(SRC);
for (const k of Object.keys(EXPECT_A)) check(k, a[k], EXPECT_A[k]);

console.log('\n=== B. screen transitions: one countNav per completed move ===');
const b = await groupB(SRC);
for (const k of Object.keys(EXPECT_B)) check(k, b[k], EXPECT_B[k]);

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
    apply: s => s.replace(
      '  const dirty = !framePushed && frameTouched',
      '  countNav(ROUTE_MATERIAL, ROUTE_MAIN);\n  const dirty = !framePushed && frameTouched'
    ).replace('  countNav(ROUTE_MATERIAL, effortRoute());\n  renderBreadcrumb();', '  renderBreadcrumb();'),
    group: 'B', breaks: ['B8']
  },
];

for (const m of MUTANTS) {
  const mutated = m.apply(SRC);
  if (mutated === SRC) { fail++; console.error(`  FAIL ${m.name}: mutation did not apply (source drifted)`); continue; }
  let got;
  try {
    got = m.group === 'A' ? await groupA(mutated) : await groupB(mutated);
  } catch (e) {
    console.log(`  ok   ${m.name} -> threw (${e.message.slice(0, 48)})`);
    pass++; continue;
  }
  const expected = m.group === 'A' ? EXPECT_A : EXPECT_B;
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

console.log(`\n${fail === 0 ? 'PASS' : 'FAIL'} — ${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
