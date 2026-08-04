// Harness — the back-guard's EDIT PREDICATE: which gestures mark a frame unsaved, and what
// the prompt names when it fires (2026-08-04).
// Run: node client2/tests/valid_die_dirty_guard_harness.mjs   (no node_modules — vm sandbox)
//
// THE LIVE REGRESSION THIS REPRODUCES. `popMapFrame` guarded unsaved work with
//   `!framePushed && frameTouched && gridData && Object.keys(gridData).length > 0`
// and `frameTouched` was set in exactly two places: `persistLegend` and `scheduleCellDraft`.
// Choosing a valid-die reference goes through NEITHER. So applying one changed the screen and
// changed what a later save would write, while the frame stayed marked CLEAN — and the next
// frame pop threw it away with no prompt at all. The 💾 SAVE button used to make the
// persistence step visible; it was removed and the guard was not moved with it.
//
// WHY THIS IS ITS OWN FILE, AND WHAT IT DOES NOT SCORE. `map_spec_only_save_harness` owns the
// 📐 규격만 저장 REQUEST SHAPE (read-modify-write, unmodelled fields, the response bound) and
// `valid_die_origin_alignment_harness` / `valid_die_head_parity_oracle` own what a declaration
// RESOLVES TO on the canvas. Neither has an opinion about frame dirtiness, and bolting this
// onto either would put two unrelated failure classes behind one exit code. `resolveValidDie`
// is therefore a RECORDER here, not a stub that fakes an answer this harness grades: what is
// under test is the marking, so the assertions read the recorder ("the apply was invoked with
// this declaration") and the flags, never a resolved mask.
//
// THE FOUR THINGS THAT CAN GO SILENTLY WRONG, AND HOW EACH IS MADE FALSIFIABLE.
//
//   1. A GESTURE IS LEFT UNMARKED. There are two applying gestures — the `<select>` `change`
//      and the key input's Enter — and one unmarked path reproduces the whole bug in a corner.
//      Scored by EXECUTING THE REAL LISTENER BODIES: the two wiring blocks are sliced out of
//      `initDOMElements` verbatim and run against recording controls, then the events are
//      fired. A harness that called `onValidDieRefChanged()` directly would pass even if the
//      `<select>` were wired to nothing.
//
//   2. MARKING SPREADS TO MERE VIEWING. That was the previous complaint ([fix E]) and it must
//      not come back. Scored in both shapes: a load followed straight by a pop, and a load of
//      a NON-EMPTY map followed by a pop — the second is the exact case [fix E] closed, and
//      the cell-count term this change removes is the thing that used to (accidentally) cover
//      it. Also scored for the IME Enter, which is not a gesture at all.
//
//   3. CLEARING BACK TO 원 기하 IS MISSED. Setting a declaration and removing one are the same
//      kind of edit, and the empty case is the one that looks like "nothing happened". Scored
//      as its own axis with `validDie.raw` non-empty going in.
//
//   4. THE PROMPT NAMES THE WRONG WRITER. Two writers exist; ⚡ Push is `replace_map`, a full
//      cell rewrite. For a declaration-only change 📐 규격만 저장 is the cheaper correct
//      answer, and a prompt that names only the expensive one is how people learn to push for
//      everything. Scored as the TEXT of the confirm, in both directions — cells dirty must
//      still name Push — and END TO END: apply, spec-save, pop, and the pop must be silent,
//      because a prompt that repeats after the user did what it said is a prompt that lied.
//
// FIXTURE ACTIVITY. The declaration used is an OBJECT ref (`{table, map_id}`) with a table
// that differs from the control's, and `validDieRefFromControls` is the real function — so
// the "did the user change it" comparison is live rather than trivially true. The spec-save
// leg is anisotropic and rotated (`chip_x !== chip_y`, rot 90, `cols !== rows`) for the same
// reason `map_spec_only_save_harness` is: a square isotropic fixture cannot show a swap
// defect at all, so a number it produced would be an artefact of the symmetry.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const SRC_PATH = join(ROOT, 'client2', 'src', 'map_editor.js');
const SRC = readFileSync(SRC_PATH, 'utf8');
const CFG = readFileSync(join(ROOT, 'client2', 'src', 'config.js'), 'utf8');
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

/**
 * Slice a balanced `{...}` statement block starting at a HEAD line, e.g. `if (el.foo) {`.
 * This is how the event wiring is scored: those listeners live inside `initDOMElements`,
 * a function that touches the whole page, and re-typing them here would let this harness
 * grade a wiring the product does not have.
 * The head must be UNIQUE — a first-match slice has twice landed on a different construct in
 * this file, once inside a comment.
 */
function sliceBlock(src, head) {
  const i = src.indexOf(head);
  if (i < 0) die(`wiring block head is gone from map_editor.js: ${head}`);
  if (src.indexOf(head, i + 1) >= 0) die(`wiring block head is not unique: ${head}`);
  const open = src.indexOf('{', i);
  let depth = 0;
  for (let j = open; j < src.length; j++) {
    if (src[j] === '{') depth++;
    else if (src[j] === '}') { depth--; if (depth === 0) return src.slice(i, j + 1); }
  }
  return die(`unbalanced braces for wiring block ${head}`);
}

const KEY_WIRING_HEAD = '  if (el.validDieRefKey) {';
const SELECT_WIRING_HEAD = '  if (el.validDieRefSelect) {';

const SYMBOLS = [
  // ── the guard and the gateways that feed it ──
  'persistLegend', 'scheduleCellDraft', 'setLoadedIdentity', 'clearGrid', 'popMapFrame',
  // ── the declaration path ──
  'validDieRefDisplay', 'validDieRefFromControls', 'onValidDieRefChanged',
  // ── the cheaper writer the reworded prompt names, sliced so the end-to-end leg is real ──
  'physNum', 'gridDimNum', 'getScreenShift', 'getTransformedPhysicalConfig', 'getDieIndex',
  'readGridFrameControls', 'applyValidDieRef', 'validDieRefForPush', 'validDieRefPayload',
  'mergeStoredGridMeta', 'geometryIsAutoRegistered', 'markGeometryAutoRegistered',
  'buildPushGridMetadata', 'serverCellKeySet', 'classifyUnsavableCells', 'fetchGridMetaFor',
  'saveMapSpecOnly',
];

// ── Fixture ─────────────────────────────────────────────────────────────────────────────
const FRAME = { cols: 25, rows: 21 };
const PHYS = { dia: 300, chipX: 14.3, chipY: 9.7, offX: 1.7, offY: -2.4, margin: 3 };
const ROT = 90;
const SIDE = 'front';
// A declaration whose TABLE is not the control's default, so `validDieRefFromControls`'s
// "did the user touch the key" comparison is exercised rather than trivially satisfied.
const STORED_REF = { table: 'valid_die_ref', map_id: 'VD_MASK_A' };

function makeInput(v) { return { value: String(v), checked: false, style: {}, dataset: {} }; }

/** A control that records its listeners, so the real handler bodies can be fired. */
function makeControl(v) {
  const listeners = {};
  return {
    value: String(v), style: {}, dataset: {},
    addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
    __fire(type, ev) { (listeners[type] || []).forEach(fn => fn(ev)); },
    __listenerTypes() { return Object.keys(listeners).sort(); },
  };
}

function cfgNumber(name) {
  const m = new RegExp(`export\\s+const\\s+${name}\\s*=\\s*([0-9.]+)\\s*;`).exec(CFG);
  if (!m) die(`\`export const ${name}\` is gone from config.js`);
  return Number(m[1]);
}

// ── Sandbox ─────────────────────────────────────────────────────────────────────────────
function buildEnv(src, opts = {}) {
  const confirms = [];
  const toasts = [];
  const applies = [];     // every `resolveValidDie` invocation, with the declaration it carried
  const requests = [];
  const el = {
    gridCols: makeInput(FRAME.cols), gridRows: makeInput(FRAME.rows),
    gridStartX: makeInput(1), gridStartY: makeInput(1),
    gridYInvert: { checked: false },
    physWaferDia: makeInput(PHYS.dia),
    physChipX: makeInput(PHYS.chipX), physChipY: makeInput(PHYS.chipY),
    physOffsetX: makeInput(PHYS.offX), physOffsetY: makeInput(PHYS.offY),
    physEdgeMargin: makeInput(PHYS.margin),
    validDieRefKey: makeControl(opts.controlKey !== undefined ? opts.controlKey : ''),
    validDieRefSelect: makeControl(''),
    validDieRefList: { innerHTML: '' },
    mapWorkspace: { scrollLeft: 0, scrollTop: 0 },
    btnSaveMapSpec: { disabled: false, textContent: '📐 규격만 저장' },
  };

  const sandbox = {
    AbortController,
    setTimeout: (fn) => { void fn; return 0; },   // the cell draft's debounce is not under test
    clearTimeout: () => {},
    setImmediate,
    MAP_SPEC_SAVE_TIMEOUT_MS: cfgNumber('MAP_SPEC_SAVE_TIMEOUT_MS'),
    console: { warn() {}, log() {}, error() {}, info() {}, debug() {} },
    JSON, Math, Number, Object, Array, String, Boolean, Set, Map, parseInt, parseFloat,
    isNaN, encodeURIComponent, Promise,
    el,
    API_BASE: '/api',
    CURRENT_USER: 'tester',
    selectedTable: 'bonding_map',
    currentRotation: ROT,
    currentSide: SIDE,
    physFrameOverride: null,
    // ── the state under test ──
    frameTouched: false,
    framePushed: false,
    legendDirty: false,
    gridData: opts.gridData ? { ...opts.gridData } : {},
    gridCells2D: {},
    editorFrames: [{ marker: 'PARENT_FRAME' }],
    loadedIdentity: { table: 'bonding_map', mapKey: 'MAP_UNDER_EDIT' },
    legendReplaceScope: null,
    serverCellKeys: null,
    loadedFCells: new Set(),
    cellDraftTimer: null,
    validDie: opts.validDie
      ? { ...opts.validDie }
      : { basis: 'circle', keys: null, reason: '', ref: null, raw: undefined },
    ROUTE_MATERIAL: 'map_editor:material',
    getCurrentMapKey: () => 'MAP_UNDER_EDIT',
    effortRoute: () => 'map_editor',
    countNav() {},
    renderBreadcrumb() {},
    notifyMapContext() {},
    restoreEditorState() {},
    renderGridCanvas() {},
    updateLegendCounts() {},
    notifyLegendChanged() {},
    saveLegendToStorage() {},
    saveDoeDraft() {},
    populateValidDieRefList() {},
    renderValidDieKeyControl() {},
    syncValidDieRefControls() {},
    showToast: (msg, kind) => toasts.push({ msg: String(msg), kind }),
    confirm: (text) => { confirms.push(String(text)); return opts.approve !== false; },
    // THE RECORDER. It writes back `validDie.raw` exactly as `resolveValidDie`'s own `set`
    // does (`raw` is the declaration original), because the NEXT gesture's "did the user
    // change it" comparison reads that field — a recorder that dropped it would make the
    // clearing case unreachable. It resolves no mask: masks are scored elsewhere.
    resolveValidDie: async (meta, table, homeKey) => {
      applies.push({
        ref: (meta && 'valid_die_ref' in meta) ? meta.valid_die_ref : null,
        table, homeKey,
      });
      sandbox.validDie = {
        ...sandbox.validDie,
        raw: (meta && 'valid_die_ref' in meta) ? meta.valid_die_ref : undefined,
      };
    },
    fetch: (url, init) => {
      const method = (init && init.method) ? init.method : 'GET';
      requests.push({ method, url: String(url), body: init && init.body ? init.body : null });
      if (method === 'PUT') return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
      return Promise.resolve({
        ok: true, status: 200,
        json: async () => ({ data: [{ data: { grid_metadata: { value: JSON.stringify({
          grid_cols: FRAME.cols, grid_rows: FRAME.rows, grid_start_x: 1, grid_start_y: 1,
          rotation: ROT, side: SIDE,
        }) } } }] }),
      });
    },
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);

  const pieces = SYMBOLS.map(n => sliceFunction(src, n));
  const vd = /^const VALID_DIE_TABLE = .*;$/m.exec(src);
  if (!vd) die('const VALID_DIE_TABLE is gone from map_editor.js');
  pieces.unshift(vd[0]);
  // The wiring, verbatim. Wrapped in a function only so it can be invoked on demand.
  pieces.push(`function __wireValidDieControls() {\n`
    + sliceBlock(src, KEY_WIRING_HEAD) + '\n'
    + sliceBlock(src, SELECT_WIRING_HEAD) + '\n}');
  try { vm.runInContext(pieces.join('\n\n'), sandbox); }
  catch (e) { die(`extracted sources did not evaluate: ${e && e.message}`); }
  sandbox.__wireValidDieControls();

  return { S: sandbox, el, confirms, toasts, applies, requests };
}

const flush = () => new Promise(r => setImmediate(r));

/** Fire the `<select>` gesture: the browser sets the value, then dispatches `change`. */
async function pickFromSelect(env, value) {
  env.el.validDieRefSelect.value = String(value);
  env.el.validDieRefSelect.__fire('change', {});
  await flush(); await flush();
}

/** Fire the fallback input's gesture: type, then Enter. */
async function typeAndEnter(env, value, ev = {}) {
  env.el.validDieRefKey.value = String(value);
  env.el.validDieRefKey.__fire('keydown', { key: 'Enter', ...ev });
  await flush(); await flush();
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

  // ── A. THE REPORTED REGRESSION, BOTH GESTURES. ────────────────────────────────────────
  // The map has NO painted cells, which is the shape the removed cell-count term silenced by
  // construction: a template map, or a map being declared before it is filled.
  for (const [label, gesture] of [
    ['select', (env) => pickFromSelect(env, 'VD_MASK_A')],
    ['enter', (env) => typeAndEnter(env, 'VD_MASK_A')],
  ]) {
    const env = buildEnv(src);
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');   // a clean baseline, as a load gives
    eq(`A[${label}]/baseline is clean after the load`,
      { touched: false, pushed: false }, { touched: env.S.frameTouched, pushed: env.S.framePushed });

    await gesture(env);

    // The apply really happened — otherwise a "marked" flag would be measuring nothing.
    eq(`A[${label}]/the declaration was applied`, [STORED_REF], env.applies.map(a => a.ref),
      'the gesture must reach resolveValidDie; a flag set without an apply is not this feature');
    eq(`A[${label}]/the frame is marked unsaved`, true, env.S.frameTouched);

    const popped = env.S.popMapFrame();
    eq(`A[${label}]/the pop prompted exactly once`, 1, env.confirms.length,
      'THIS IS THE REGRESSION: 0 here means the selection is discarded in silence');
    eq(`A[${label}]/approved pop still returns`, true, popped);
    evidence.push(`A[${label}] confirm text: ${JSON.stringify(env.confirms[0] || null)}`);
  }

  // ── B. DECLINING KEEPS THE USER PUT — the frame must NOT be popped. ───────────────────
  {
    const env = buildEnv(src, { approve: false });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    const popped = env.S.popMapFrame();
    eq('B/declining returns false', false, popped);
    eq('B/declining leaves the frame stack intact', 1, env.S.editorFrames.length);
  }

  // ── C. CLEARING BACK TO 원 기하 IS AN EDIT TOO. ───────────────────────────────────────
  // Going in, the map ALREADY carries a declaration, and the control shows it — so the empty
  // selection is a real change rather than a no-op.
  {
    const env = buildEnv(src, {
      validDie: { basis: 'ref', keys: null, reason: '', ref: null, raw: STORED_REF },
      controlKey: STORED_REF.map_id,
    });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, '');
    eq('C/the clear was applied as 해제 (no declaration)', [null], env.applies.map(a => a.ref),
      'an empty selection must mean 원 기하 exactly as an empty input does');
    eq('C/the clear marks the frame unsaved', true, env.S.frameTouched);
    env.S.popMapFrame();
    eq('C/the pop prompted', 1, env.confirms.length,
      'clearing is the case most likely to be missed — it looks like nothing happened');
    eq('C/the 해제 toast still fires', true,
      env.toasts.some(t => t.msg.indexOf('유효 다이 지정을 해제했습니다') >= 0));
  }

  // ── D. A MERELY-VIEWED MAP GOES BACK IN SILENCE. [fix E] must not regress. ────────────
  // Two shapes, because the cell-count term this change removes used to be what (accidentally)
  // covered the second one.
  {
    const env = buildEnv(src, { gridData: {} });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.S.popMapFrame();
    eq('D1/viewing an empty map is silent', 0, env.confirms.length);
  }
  {
    const env = buildEnv(src, {
      gridData: { '3_4': 'A1', '5_6': 'B2', '7_8': 'A1' },
      validDie: { basis: 'ref', keys: null, reason: '', ref: null, raw: STORED_REF },
      controlKey: STORED_REF.map_id,
    });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    // Nothing is touched: the map is opened, its valid-die designation is looked at, and the
    // user leaves. This is the exact complaint [fix E] closed.
    env.S.popMapFrame();
    eq('D2/viewing a NON-EMPTY map with a declaration is silent', 0, env.confirms.length,
      'this is the [fix E] complaint; removing the cell-count term must not bring it back');
    eq('D2/...and no apply was invoked by merely looking', 0, env.applies.length);
  }
  {
    // The IME Enter is not a gesture: confirming a Korean composition must not apply anything,
    // and therefore must not dirty the frame either.
    const env = buildEnv(src);
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await typeAndEnter(env, 'VD_MASK_A', { isComposing: true });
    eq('D3/an IME-composition Enter applies nothing', 0, env.applies.length);
    eq('D3/...and leaves the frame clean', false, env.S.frameTouched);
    env.S.popMapFrame();
    eq('D3/...so the pop is silent', 0, env.confirms.length);
  }
  {
    // A non-Enter keystroke in the input is typing, not a commit.
    const env = buildEnv(src);
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.el.validDieRefKey.value = 'VD_MA';
    env.el.validDieRefKey.__fire('keydown', { key: 'A' });
    await flush();
    eq('D4/typing without Enter applies nothing', 0, env.applies.length);
    eq('D4/...and leaves the frame clean', false, env.S.frameTouched);
  }

  // ── E. THE CELL-COUNT TERM. `clearGrid` empties gridData and IS an edit. ──────────────
  {
    const env = buildEnv(src, { gridData: { '3_4': 'A1', '5_6': 'B2' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.S.clearGrid();                       // approve:true -> the clear goes through
    eq('E/clearGrid emptied the grid', 0, Object.keys(env.S.gridData).length);
    eq('E/clearGrid marked the frame', true, env.S.frameTouched);
    const confirmsBefore = env.confirms.length;
    env.S.popMapFrame();
    eq('E/clearing every value still prompts on the way back', confirmsBefore + 1, env.confirms.length,
      'the old `gridData` non-empty term made "delete everything" the one edit that vanished silently');
  }

  // ── F. WHICH WRITER THE PROMPT NAMES. ────────────────────────────────────────────────
  {
    const env = buildEnv(src);
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    env.S.popMapFrame();
    const text = env.confirms[0] || '';
    eq('F1/a declaration-only edit names 📐 규격만 저장', true, text.indexOf('📐 규격만 저장') >= 0,
      'Push rewrites every cell for a change that touched none');
    eq('F1/...and does NOT name ⚡ Push', false, text.indexOf('⚡ Push') >= 0,
      'naming the expensive option only is how people learn to push for everything');
    eq('F1/...and the declaration did not light the cell/legend draft flag', false, env.S.legendDirty,
      'legendDirty is what the plan head shows as unsaved plan work; a declaration is not that');
  }
  {
    const env = buildEnv(src, { gridData: { '3_4': 'A1' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.S.scheduleCellDraft();               // a real cell write went through the draft gateway
    env.S.popMapFrame();
    const text = env.confirms[0] || '';
    eq('F2/a cell edit still names ⚡ Push', true, text.indexOf('⚡ Push') >= 0);
    eq('F2/...and does not offer the spec-only writer for it', false, text.indexOf('📐 규격만 저장') >= 0,
      '📐 규격만 저장 writes no cells, so offering it for a cell edit would lose the cells');
  }
  {
    // Both kinds of edit at once: the cell edit dominates, because the spec writer cannot
    // carry cells.
    const env = buildEnv(src, { gridData: { '3_4': 'A1' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    env.S.persistLegend();
    env.S.popMapFrame();
    eq('F3/declaration + legend edit names ⚡ Push', true,
      (env.confirms[0] || '').indexOf('⚡ Push') >= 0);
  }

  // ── G. A PUSHED FRAME IS CLEAN; AN EDIT AFTER THE PUSH IS NOT. ───────────────────────
  {
    const env = buildEnv(src, { gridData: { '3_4': 'A1' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.S.scheduleCellDraft();
    env.S.framePushed = true;                // what pushMapData sets on a recorded success
    env.S.popMapFrame();
    eq('G1/a pushed frame goes back in silence', 0, env.confirms.length);
  }
  {
    const env = buildEnv(src, { gridData: { '3_4': 'A1' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    env.S.framePushed = true;
    await pickFromSelect(env, 'VD_MASK_A');  // ...and THEN the declaration changes
    eq('G2/an apply after a push re-arms the guard', false, env.S.framePushed,
      'the screen again holds something the server does not have');
    env.S.popMapFrame();
    eq('G2/...so the pop prompts', 1, env.confirms.length);
  }

  // ── H. END TO END: the prompt must not repeat after the user does what it says. ──────
  {
    const env = buildEnv(src);
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    eq('H/the frame is unsaved before the save', true, env.S.frameTouched);

    await env.S.saveMapSpecOnly();           // the writer the prompt names (confirm approved)
    const writes = env.requests.filter(r => r.method === 'PUT');
    eq('H/the spec save issued exactly one write', 1, writes.length);
    eq('H/...and it carried the declaration', STORED_REF,
      JSON.parse(JSON.parse(writes[0].body).updates[0].updates.grid_metadata).valid_die_ref,
      'if the save did not persist the ref, clearing the guard below would be a lie');
    eq('H/the guard is cleared by the cheaper writer', false, env.S.frameTouched);

    const before = env.confirms.length;
    env.S.popMapFrame();
    eq('H/the pop after the spec save is silent', before, env.confirms.length,
      'a prompt that asks again after the user did exactly what it said is a prompt that lied');
  }
  {
    // ...but the spec save must NOT clear a frame that also holds cell work — it writes no
    // cells, so those are still unsaved.
    const env = buildEnv(src, { gridData: { '3_4': 'A1' } });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    env.S.scheduleCellDraft();
    await env.S.saveMapSpecOnly();
    eq('H2/a frame with cell work stays unsaved after a spec-only save', true, env.S.frameTouched);
    const before = env.confirms.length;
    env.S.popMapFrame();
    eq('H2/...and still prompts', before + 1, env.confirms.length);
    eq('H2/...naming ⚡ Push, because the cells are what is left', true,
      (env.confirms[env.confirms.length - 1] || '').indexOf('⚡ Push') >= 0);
  }

  // ── I. THE WIRING ITSELF. Both gestures must be bound, and blur must NOT be. ─────────
  {
    const env = buildEnv(src);
    eq('I/the key input binds focus + input + keydown, and NOT change',
      ['focus', 'input', 'keydown'], env.el.validDieRefKey.__listenerTypes(),
      'a `change` here fires on blur — leaving the box would re-seat the whole map (3-a)');
    eq('I/the select binds change', ['change'], env.el.validDieRefSelect.__listenerTypes());
  }
  {
    // The `<select>` must copy its value into the key input BEFORE applying — the key input is
    // the single source of truth and `onValidDieRefChanged` reads it, so a reversed order
    // applies the PREVIOUS value.
    const env = buildEnv(src, { controlKey: 'OLD_KEY' });
    env.S.setLoadedIdentity('bonding_map', 'MAP_UNDER_EDIT');
    await pickFromSelect(env, 'VD_MASK_A');
    eq('I/the select writes the key input before applying', 'VD_MASK_A', env.el.validDieRefKey.value);
    eq('I/...so the applied declaration is the NEW one', [STORED_REF], env.applies.map(a => a.ref));
  }

  return { failures, compared, evidence };
}

// ── Mutants ─────────────────────────────────────────────────────────────────────────────
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

// ⚠️ EVERY ANCHOR BELOW IS MULTI-LINE OR CARRIES ITS OWN COMMENT TAIL. `  frameTouched = true;`
//    ALONE IS NOT UNIQUE in map_editor.js — `persistLegend` and `scheduleCellDraft` each spell
//    it — and a first-match replace would mutate a function this harness scores differently,
//    coming back as a hole that reads like coverage.
const MUTANTS = {
  // ── THE REPORTED REGRESSION, RESTORED EXACTLY. This mutant IS today's shipped code. ──
  'the-declaration-path-marks-nothing': (s) => once(s,
    ['  frameTouched = true;',
     '  framePushed = false;',
     '  if (key === \'\') {'].join('\n'),
    '  if (key === \'\') {'),
  // Half of it: marked, but the guard stays disarmed after a Push.
  'the-declaration-path-leaves-framePushed-set': (s) => once(s,
    ['  frameTouched = true;',
     '  framePushed = false;',
     '  if (key === \'\') {'].join('\n'),
    ['  frameTouched = true;',
     '  if (key === \'\') {'].join('\n')),
  // Marked in the wrong place: `resolveValidDie` is on the LOAD path too, so this is the
  // [fix E] complaint coming back — viewing a map would prompt.
  'the-mark-migrates-into-the-clearing-branch-only': (s) => once(s,
    ['  frameTouched = true;',
     '  framePushed = false;',
     '  if (key === \'\') {'].join('\n'),
    ['  if (key === \'\') {',
     '    frameTouched = true;',
     '    framePushed = false;'].join('\n')),
  // ── THE GUARD PREDICATE ──
  // The cell-count term, restored. Catches the empty-map declaration and `clearGrid`.
  'the-guard-requires-cells': (s) => once(s,
    '  const dirty = !framePushed && frameTouched;',
    '  const dirty = !framePushed && frameTouched && gridData && Object.keys(gridData).length > 0;'),
  // The edit predicate is dropped, which is what made mere VIEWING prompt before [fix E].
  'the-guard-drops-the-edit-predicate': (s) => once(s,
    '  const dirty = !framePushed && frameTouched;',
    '  const dirty = !framePushed && gridData && Object.keys(gridData).length > 0;'),
  // The guard never fires at all.
  'the-guard-is-disarmed': (s) => once(s,
    '  const dirty = !framePushed && frameTouched;',
    '  const dirty = false;'),
  // Declining no longer keeps the user put.
  'declining-the-prompt-pops-anyway': (s) => once(s,
    '    `\\n[확인] 저장하지 않고 돌아가기\\n[취소] 이 화면에 남기`\n  )) return false;',
    '    `\\n[확인] 저장하지 않고 돌아가기\\n[취소] 이 화면에 남기`\n  )) { /* popped anyway */ }'),
  // ── THE PROMPT'S CONTENT ──
  // Today's wording, restored: it names only the expensive writer.
  'the-prompt-names-only-push': (s) => once(s,
    ['    `이 맵의 편집을 저장하지 않았습니다.\\n\\n` +',
     '    (legendDirty',
     '      ? `· 셀 값이 바뀌었습니다 — [⚡ Push]로 저장하십시오.\\n`',
     '      : `· 셀은 하나도 바뀌지 않았습니다 — [📐 규격만 저장]이면 충분합니다.\\n`) +'].join('\n'),
    '    `이 맵을 [⚡ Push]로 저장하지 않았습니다.\\n\\n` +'),
  // ...and the reverse: the cheap writer is offered for a CELL edit, which would lose cells.
  'the-prompt-offers-spec-only-for-cell-edits': (s) => once(s,
    ['    (legendDirty',
     '      ? `· 셀 값이 바뀌었습니다 — [⚡ Push]로 저장하십시오.\\n`',
     '      : `· 셀은 하나도 바뀌지 않았습니다 — [📐 규격만 저장]이면 충분합니다.\\n`) +'].join('\n'),
    '    `· 셀은 하나도 바뀌지 않았습니다 — [📐 규격만 저장]이면 충분합니다.\\n` +'),
  // ── THE END-TO-END LEG ──
  // The cheaper writer does not clear the guard, so the prompt repeats after the user obeys it.
  'the-spec-save-does-not-clear-the-guard': (s) => once(s,
    '    if (!legendDirty) frameTouched = false;\n    syncValidDieRefControls();',
    '    syncValidDieRefControls();'),
  // ...and the opposite: it clears unconditionally, throwing away the fact that CELLS are
  // still unsaved — this write does not carry a single cell.
  'the-spec-save-clears-the-guard-unconditionally': (s) => once(s,
    '    if (!legendDirty) frameTouched = false;\n    syncValidDieRefControls();',
    '    frameTouched = false;\n    syncValidDieRefControls();'),
  // ── THE WIRING ──
  // The select copies its value AFTER applying, so the PREVIOUS declaration is what lands.
  'the-select-applies-before-it-writes-the-key': (s) => once(s,
    ['      if (el.validDieRefKey) el.validDieRefKey.value = el.validDieRefSelect.value;',
     '      onValidDieRefChanged();'].join('\n'),
    ['      onValidDieRefChanged();',
     '      if (el.validDieRefKey) el.validDieRefKey.value = el.validDieRefSelect.value;'].join('\n')),
  // The IME guard is dropped: confirming a Korean composition becomes an apply.
  'the-ime-composition-enter-applies': (s) => once(s,
    '      if (e.isComposing || e.keyCode === 229) return;',
    '      /* IME guard dropped */'),
  // A `change` listener on the input, which fires on BLUR — leaving the box would re-seat the
  // map and dirty the frame. That is the behaviour 3-a removed.
  'the-key-input-regains-a-change-listener': (s) => once(s,
    '    el.validDieRefKey.addEventListener(\'input\', renderValidDieKeyControl);',
    ['    el.validDieRefKey.addEventListener(\'input\', renderValidDieKeyControl);',
     '    el.validDieRefKey.addEventListener(\'change\', onValidDieRefChanged);'].join('\n')),
  // ── NEGATIVE CONTROL. A comment-only edit must ESCAPE. A corpus that "catches" this is
  //    keying on source text rather than behaviour, and its caught column means nothing.
  '__control_comment_only': (s) => once(s,
    '  // [fix E] Prompt only when this frame was actually edited since it opened AND the',
    '  // [fix E] (reworded control mutant) prompt only on a real edit that was not pushed,'),
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
    if (verbose) {
      console.log(`   mutant '${name}': ${newOnes.length} new failure(s)`);
      newOnes.forEach(x => console.log(`       · ${x}`));
    }
  }
  console.log(`--- mutation check: ${caught}/${total} defects caught ---`);
  process.exit(base.failures.length === 0 && caught === total ? 0 : 1);
})();
