// Harness — the MAP-KEY / METADATA-FIELD datalist surface of `map_editor.js` (2026-07-31).
// Run: node client2/tests/map_key_datalist_harness.mjs   (no node_modules — vm sandbox)
//
// WHY THIS IS A SEPARATE FILE FROM `value_suggest_keys_harness.mjs`.
// That harness owns the AG-GRID CELL EDITOR half of value suggestion: it loads
// `client2/src/value_suggest.js` + `client2/src/grid.js` into a model of AG-Grid's keyboard
// pipeline and scores the one-Enter acceptance criterion in KEYSTROKES. Nothing in it
// touches `map_editor.js`, and nothing here touches the cell editor — the two surfaces share
// only the server endpoint. Bolting these cases onto that file would put two unrelated
// sandboxes and two unrelated mutation corpora behind one exit code, and its sweep is keyed
// to `suggest`/`grid` sources by construction.
//
// WHAT THIS PROVES.
// The datalist code is sliced VERBATIM out of `map_editor.js` (the technique
// `valid_die_authoring_harness.mjs` / `geometry_origin_reseat_harness.mjs` established) and
// executed against a DOM model whose `getElementById` is a REAL TREE WALK. That last part is
// the load-bearing choice: the whole regeneration question ("can a datalist from the previous
// table still be reached?") is only answerable if detachment actually makes a node
// unreachable. A stub that resolves ids from a flat registry would answer "yes, still there"
// for both the correct and the defective implementation, i.e. it would score nothing.
//
// THE THREE AXES, AND WHAT MAKES EACH ONE FALSIFIABLE.
//   1. `unavailable_reason` IS NOT AN EMPTY LIST. Scored as a DISCRIMINATION, never as a
//      single observation: the same column is asked twice, once answering `values: []` with
//      `unavailable_reason: null` and once answering `values: []` with a reason, and the two
//      outcomes must DIFFER. An implementation that collapses them passes any check that only
//      looks at one of the two, which is exactly how the collapse survives review.
//   2. REGENERATION. Scored by unreachability after `innerHTML = ''` and by request counts
//      across a table switch, not by inspecting the source for a `delete`.
//   3. A DATALIST DOES NOT CONSTRAIN. Scored by running EVERY answer shape (complete,
//      truncated, unavailable, HTTP failure, refused) against an input holding a value that
//      appears in NO list, and asserting the value and the input's constraint attributes come
//      out untouched. Plus a structural read of `map_editor.html` itself, because the free
//      -typing path can also be broken in markup (`required`, `pattern`) where no JS runs.
//
// CONTROLS. The sweep runs NEGATIVE controls alongside the mutants: a consistent local rename
// and a comment-only edit. Both must ESCAPE. A detector that catches a comment edit is keying
// on source text rather than on behaviour, and its "caught" column is then worthless — it
// would be riding on the edit, not scoring its own axis.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'map_editor.js');
const HTML_PATH = join(HERE, '..', 'map_editor.html');

const SRC = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');
const HTML = readFileSync(HTML_PATH, 'utf8').replace(/\r\n/g, '\n');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

// ── Extraction ──────────────────────────────────────────────────────────────────
function sliceBalanced(src, startIdx, open, close) {
  const i = src.indexOf(open, startIdx);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    const ch = src[j];
    if (ch === open) depth++;
    else if (ch === close) { depth--; if (depth === 0) return src.slice(startIdx, j + 1); }
  }
  return null;
}

function fn(src, name) {
  const m = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`).exec(src);
  if (!m) die(`function ${name} not found in ${SRC_PATH} — renamed or reshaped.`);
  const out = sliceBalanced(src, m.index, '{', '}');
  if (!out) die(`unbalanced braces for ${name}`);
  return out;
}

/**
 * A `const NAME = ...;` declaration, lifted verbatim. Handles the array form (multi-line)
 * and the trailing-comment form — a slicer that only matched `...;$` silently missed
 * `const columnValueComplete = new Map();  // comment`, and a missing binding here is a
 * ReferenceError, not a wrong answer, so it is loud either way.
 */
function konst(src, name) {
  const m = new RegExp(`^const ${name} = `, 'm').exec(src);
  if (!m) die(`const ${name} not found in ${SRC_PATH}`);
  const rest = m.index + m[0].length;
  if (src[rest] === '[') {
    const body = sliceBalanced(src, rest, '[', ']');
    if (!body) die(`unbalanced brackets for const ${name}`);
    return `${m[0]}${body};`;
  }
  const end = src.indexOf(';', rest);
  if (end < 0) die(`no terminator for const ${name}`);
  return src.slice(m.index, end + 1);
}

const FUNCS = [
  'markSuggestState', 'claimListFill', 'fillDatalist',
  'populateMapKeyDatalist', 'populateValidDieRefList', 'populateOverlayKeyList',
  // [1-a] The control-shape decision. Sliced verbatim so the <select>-vs-<input> choice is
  // scored as BEHAVIOUR, not read off the markup.
  'renderValidDieKeyControl',
  'colValueKey', 'dropColumnValueCache', 'canReuseComplete',
  'populateColumnValueDatalist', 'onMetaInputSuggest',
  'renderMetadataInputs',
];
const CONSTS = [
  'listFillSeq',
  'KEY_SUGGEST_DEBOUNCE_MS', 'COLUMN_VALUE_LIST_LIMIT', 'VALID_DIE_LIST_LIMIT',
  // The FIXED storage table of a valid-die map (2026-08-04). Extracted, never re-typed:
  // `populateValidDieRefList` no longer reads a control for its table, so this constant IS
  // the population it queries — a copy here that drifted would score the wrong table green.
  'VALID_DIE_TABLE',
  'mapKeyListCache', 'columnValueComplete', 'columnValueRefused', 'columnValueTruncated',
  'PUSH_SYSTEM_COLUMNS',
];

// ── DOM model — `getElementById` is a tree walk, on purpose (see the header) ─────
function makeNode(tag) {
  const node = {
    tagName: tag,
    id: '', value: '', title: '', className: '', type: '', placeholder: '', textContent: '',
    htmlFor: '',
    dataset: {},
    // [1-a] `style` and `options` exist because the valid-die key control now CHOOSES between
    // a <select> and the text input, and it expresses that choice with `style.display` while
    // reading its option set from the datalist's `.options`. Without both, the choice would be
    // unobservable here and every assertion about it would be vacuous — the model, not the
    // code, would be answering. `options` is the live child list on BOTH element kinds in the
    // browser, so it is modelled as the children rather than as a snapshot.
    style: {},
    children: [],
    parent: null,
    attrs: {},
    listeners: {},
    appendChild(c) { c.parent = node; node.children.push(c); return c; },
    setAttribute(k, v) { node.attrs[k] = String(v); },
    getAttribute(k) {
      return Object.prototype.hasOwnProperty.call(node.attrs, k) ? node.attrs[k] : null;
    },
    addEventListener(t, f) { (node.listeners[t] = node.listeners[t] || []).push(f); },
    listenerCount(t) { return (node.listeners[t] || []).length; },
    dispatch(t, ev) {
      (node.listeners[t] || []).slice()
        .forEach(f => f(Object.assign({ type: t, target: node }, ev || {})));
    },
  };
  Object.defineProperty(node, 'options', { get() { return node.children; } });
  Object.defineProperty(node, 'innerHTML', {
    get() { return ''; },
    // The real thing detaches every child. Modelled as detachment, not as "forget the list",
    // because reachability is what the regeneration axis is measured on.
    set(v) {
      if (v === '' || v === null || v === undefined) {
        node.children.forEach(c => { c.parent = null; });
        node.children.length = 0;
        return;
      }
      // `<option value="">(...)</option>` style seeding is not used by anything sliced here.
      node.children.forEach(c => { c.parent = null; });
      node.children.length = 0;
      node.seededHtml = String(v);
    },
  });
  return node;
}

function walk(root, visit) {
  visit(root);
  root.children.forEach(c => walk(c, visit));
}

function makeDocument(roots) {
  return {
    createElement: makeNode,
    getElementById(id) {
      let hit = null;
      roots.forEach(r => walk(r, n => { if (!hit && n.id === id) hit = n; }));
      return hit;
    },
    querySelectorAll(sel) {
      const m = /^\[id\^="(.*)"\]$/.exec(sel);
      const out = [];
      if (!m) return out;
      roots.forEach(r => walk(r, n => { if (n.id && n.id.startsWith(m[1])) out.push(n); }));
      return out;
    },
  };
}

// ── The sandbox ─────────────────────────────────────────────────────────────────
/**
 * `answers` is a list of matchers consulted in order for every request:
 *   { match: (url) => bool, status?, body?, throws?, once? }
 * The first match wins; `once: true` removes it after use, which is how a second focus is
 * given a different answer than the first (the "is the failure cached?" question).
 */
function build(src, { answers = [], table = 'bonding_map', schema = null } = {}) {
  const pieces = [];
  for (const name of CONSTS) pieces.push(konst(src, name));
  for (const name of FUNCS) pieces.push(fn(src, name));

  const container = makeNode('div');
  container.id = 'metadata-fields-container';
  const validDieList = makeNode('datalist'); validDieList.id = 'valid-die-ref-list';
  const validDieKey = makeNode('input'); validDieKey.id = 'valid-die-ref-key';
  validDieKey.title = '이 맵의 유효 다이를 정하는 맵의 키.';
  const validDieTable = makeNode('select'); validDieTable.id = 'valid-die-ref-table';
  validDieTable.value = '';
  // [1-a] The dropdown form of the key control. Starts hidden, exactly as the markup ships it.
  const validDieSelect = makeNode('select'); validDieSelect.id = 'valid-die-ref-select';
  validDieSelect.style.display = 'none';
  const overlayList = makeNode('datalist'); overlayList.id = 'overlay-src-key-list';
  const overlayKey = makeNode('input'); overlayKey.id = 'overlay-src-key';
  overlayKey.title = '겹칠 맵의 키';
  const overlayTable = makeNode('select'); overlayTable.id = 'overlay-src-table';
  overlayTable.value = '';

  // The two static datalists are PARENTED next to their inputs, exactly as the markup has
  // them (`.ov-body`, the valid-die block). Modelling them as detached roots would make one
  // whole failure mode unreachable: a `fillDatalist` that reached sideways and wrote into a
  // neighbouring input would have nothing to reach.
  const overlayPanel = makeNode('div');
  overlayPanel.appendChild(overlayTable);
  overlayPanel.appendChild(overlayKey);
  overlayPanel.appendChild(overlayList);
  const validDiePanel = makeNode('div');
  validDiePanel.appendChild(validDieTable);
  validDiePanel.appendChild(validDieSelect);
  validDiePanel.appendChild(validDieKey);
  validDiePanel.appendChild(validDieList);

  // A `body` exists because the realistic way to leave an ORPHAN datalist is to parent it
  // somewhere that outlives the container. Without a body in the model that defect has
  // nowhere to happen, and "we never saw it" would be a property of the model.
  const body = makeNode('body');
  body.id = 'document-body';
  const roots = [container, overlayPanel, validDiePanel, body];

  const requests = [];
  const el = {
    metadataContainer: container,
    validDieRefList: validDieList, validDieRefKey: validDieKey, validDieRefTable: validDieTable,
    validDieRefSelect: validDieSelect,
    overlaySrcKeyList: overlayList, overlaySrcKey: overlayKey, overlaySrcTable: overlayTable,
    colMapX: { value: 'x' }, colMapY: { value: 'y' }, colMapVal: { value: 'val' },
  };

  const sandbox = {
    el,
    document: makeDocument(roots),
    API_BASE: '/api',
    selectedTable: table,
    tableSchema: schema,
    console: { debug() {}, warn() {}, error() {}, log() {}, info() {} },
    Number, String, Array, Object, Math, JSON, Promise, Map, Set, WeakMap,
    encodeURIComponent,
    // `delay` is what makes an OUT-OF-ORDER landing expressible: without it every answer
    // arrives in request order and the stale-overwrite race has no fixture. `delay: n`
    // resolves `json()` after n extra microtask turns.
    async fetch(url) {
      requests.push(String(url));
      const a = answers.find(x => x.match(String(url)));
      if (!a) throw new Error(`no answer declared for ${url}`);
      if (a.once) answers.splice(answers.indexOf(a), 1);
      if (a.throws) throw new Error(a.throws);
      const status = a.status === undefined ? 200 : a.status;
      const turns = a.delay || 0;
      return {
        ok: status >= 200 && status < 300, status,
        json: async () => {
          for (let i = 0; i < turns; i++) await Promise.resolve();
          return a.body;
        },
      };
    },
  };
  vm.createContext(sandbox);
  try {
    vm.runInContext(pieces.join('\n\n'), sandbox);
  } catch (e) {
    die(`the sliced code does not evaluate: ${e && e.message}`);
  }
  return { sandbox, el, requests, container, roots };
}

// ── Scoring ─────────────────────────────────────────────────────────────────────
let pass = 0, fail = 0, quiet = false;
const failures = [];
function check(name, actual, expected) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; return true; }
  fail++; failures.push(name);
  if (!quiet) console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
  return false;
}

// `null` rather than a throw when the list is missing: a missing datalist is an ANSWER this
// suite has assertions about, and a crash would report it as a broken harness instead.
const optionValues = list => (list ? list.children.map(o => o.value) : null);

// ── Fixtures ────────────────────────────────────────────────────────────────────
// The fixture ACTIVATES every axis it claims to score:
//   · two tables with DISJOINT map-key sets, so a stale list is countable, not merely absent
//   · two tables with DIFFERENT key columns, so a stale field set is visible as a missing id
//   · a truncated answer whose `total` exceeds its row count, so the truncation term is live
//   · an `unavailable` answer whose `values` is [] — identical in shape to a genuine empty
//     answer, which is the only fixture that can score the collapse
const META_ROWS = {
  bonding_map: ['BASE-29_01', 'BASE-29_02', 'BASE-31_07'],
  core_defect_map: ['CORE-A_11', 'CORE-B_12'],
  // The FIXED valid-die population (2026-08-04). Deliberately DISJOINT from the two above:
  // the valid-die field is now scored on the canvas table `bonding_map` while expecting these
  // keys, so an implementation that fell back to the canvas table cannot pass by coincidence.
  valid_die_ref: ['CORE_1X', 'CORE_YINV', '5N_BASE'],
};
const metaBody = (table, total) => ({
  data: META_ROWS[table].map(id => ({ data: { map_id: { value: id } } })),
  total: total === undefined ? META_ROWS[table].length : total,
});
const metaAnswer = (table, total) => ({
  match: u => u.includes('/tables/wafer_map_metadata/data')
    && u.includes(encodeURIComponent(`"filter":"${table}"`)),
  body: metaBody(table, total),
});

const SCHEMA_A = {
  columns: ['lot_id', 'slot', 'x', 'y', 'val', 'created_at'],
  column_types: { lot_id: 'string', slot: 'number', x: 'number', y: 'number', val: 'string' },
  map_key_columns: ['lot_id', 'slot'],
};
const SCHEMA_B = {
  columns: ['base', 'x', 'y', 'val'],
  column_types: { base: 'string', x: 'number', y: 'number', val: 'string' },
  map_key_columns: ['base'],
};

const valuesAnswer = (table, column, body) => ({
  match: u => u.includes(`/tables/${table}/columns/${column}/values`),
  body,
});
const complete = values => ({ values, truncated: false, unavailable_reason: null });
const cut = values => ({ values, truncated: true, unavailable_reason: null });
const unavailable = reason => ({ values: [], truncated: false, unavailable_reason: reason });

const FREE = 'TYPED-BY-HAND-NOT-IN-ANY-LIST';
const CONSTRAINT_ATTRS = ['required', 'pattern', 'readonly', 'disabled', 'minlength'];
function constraintState(input) {
  return {
    attrs: CONSTRAINT_ATTRS.filter(a => input.getAttribute(a) !== null),
    readOnly: input.readOnly === true,
    disabled: input.disabled === true,
  };
}

// ── The checks ──────────────────────────────────────────────────────────────────
async function runChecks(src, { strict = true } = {}) {
  const r = {};

  // ── 0. FIXTURE ACTIVITY ───────────────────────────────────────────────────────
  //   Every staleness check below is stated as "how many of the OLD population survive",
  //   and that number can only be meaningful if the two populations are DISJOINT. If the
  //   two tables shared a map key or a key column, a completely stale list would still
  //   score 0 survivors and the suite would be self-congratulating. The equivalent question
  //   for the source-table axis: reading the overlay list off the canvas table instead of
  //   the source table changes 5 of 5 offered keys, not 0.
  {
    const keyOverlap = META_ROWS.bonding_map.filter(k => META_ROWS.core_defect_map.includes(k));
    const colOverlap = SCHEMA_A.map_key_columns.filter(c => SCHEMA_B.map_key_columns.includes(c));
    if (strict) {
      check('the two tables\' map keys are disjoint (or the staleness checks prove nothing)',
        keyOverlap, []);
      check('the two tables\' key columns are disjoint (same reason)', colOverlap, []);
      check('both populations are non-empty',
        [META_ROWS.bonding_map.length > 0, META_ROWS.core_defect_map.length > 0], [true, true]);
    }
  }

  // ── 1. OVERLAY: the population is "maps with a registered spec", and it is the
  //       SOURCE table's, not the canvas table's ────────────────────────────────
  {
    const env = build(src, {
      table: 'bonding_map',
      answers: [metaAnswer('core_defect_map'), metaAnswer('bonding_map')],
    });
    env.el.overlaySrcTable.value = 'core_defect_map';   // deliberately NOT `selectedTable`
    env.el.overlaySrcKey.value = FREE;
    await env.sandbox.populateOverlayKeyList();
    r.ovRequests = env.requests.length;
    r.ovHitsMetadata = env.requests.every(u => u.includes('/tables/wafer_map_metadata/data'));
    r.ovFilteredBySource = env.requests[0].includes(encodeURIComponent('"filter":"core_defect_map"'));
    r.ovOptions = optionValues(env.el.overlaySrcKeyList);
    r.ovValueUntouched = env.el.overlaySrcKey.value;
    r.ovConstraints = constraintState(env.el.overlaySrcKey);
    if (strict) {
      check('overlay focus costs exactly ONE request', r.ovRequests, 1);
      check('and it asks wafer_map_metadata, not the value-suggest endpoint',
        r.ovHitsMetadata, true);
      check('filtered by the OVERLAY SOURCE table, not by the canvas table',
        r.ovFilteredBySource, true);
      check('the datalist holds exactly the returned map_ids, in order',
        r.ovOptions, META_ROWS.core_defect_map);
      check('a hand-typed key present in no list is left untouched', r.ovValueUntouched, FREE);
      check('and no constraint attribute was added to the input',
        r.ovConstraints, { attrs: [], readOnly: false, disabled: false });
    }
  }

  // ── 1-bis. CHANGING THE SOURCE TABLE REPLACES THE POPULATION ──────────────────
  //   A stale list is worse than none because it is not visibly stale, so the check is
  //   stated as "how many of the OLD table's keys survive", which is 0 or it is a defect.
  {
    const env = build(src, {
      table: 'bonding_map',
      answers: [metaAnswer('core_defect_map'), metaAnswer('bonding_map')],
    });
    env.el.overlaySrcTable.value = 'core_defect_map';
    await env.sandbox.populateOverlayKeyList();
    env.el.overlaySrcTable.value = 'bonding_map';
    await env.sandbox.populateOverlayKeyList();
    const shown = optionValues(env.el.overlaySrcKeyList);
    r.ovAfterSwitch = shown;
    r.ovStaleSurvivors = shown.filter(v => META_ROWS.core_defect_map.includes(v)).length;
    if (strict) {
      check('after a source-table change the list is the NEW table\'s',
        r.ovAfterSwitch, META_ROWS.bonding_map);
      check('zero keys from the previous table survive', r.ovStaleSurvivors, 0);
    }
  }

  // ── 1-bis-2. A SLOW EARLIER ANSWER CANNOT OVERWRITE A NEWER LIST ─────────────
  //   Two source-table changes in quick succession, the FIRST answering slower than the
  //   second. Without a generation guard the first answer lands last and quietly restores
  //   the previous table's keys — a list that is wrong and looks completely normal, which
  //   is the same failure mode as a stale list, arriving by a different door.
  {
    const env = build(src, {
      table: 'bonding_map',
      answers: [
        { ...metaAnswer('core_defect_map'), delay: 8 },   // asked first, answers last
        metaAnswer('bonding_map'),
      ],
    });
    env.el.overlaySrcTable.value = 'core_defect_map';
    const slow = env.sandbox.populateOverlayKeyList();
    env.el.overlaySrcTable.value = 'bonding_map';
    const fast = env.sandbox.populateOverlayKeyList();
    await Promise.all([slow, fast]);
    await new Promise(r2 => setImmediate(r2));
    r.raceFinal = optionValues(env.el.overlaySrcKeyList);
    r.raceStaleSurvivors = (r.raceFinal || [])
      .filter(v => META_ROWS.core_defect_map.includes(v)).length;
    if (strict) {
      check('the LAST question wins even when its answer came back first',
        r.raceFinal, META_ROWS.bonding_map);
      check('no key from the superseded question survives', r.raceStaleSurvivors, 0);
    }
  }

  // ── 1-ter. THE VALID-DIE FIELD IS PINNED TO ONE TABLE ─────────────────────────
  //   Changed 2026-08-04 with the user ruling that a valid-die map always lives in
  //   `valid_die_ref`. The mechanism is unchanged (still `populateMapKeyDatalist`); what
  //   moved is the POPULATION, and this case is what holds it there. The canvas table is
  //   `bonding_map` and only the `valid_die_ref` answer is served, so an implementation that
  //   still asked for the canvas table would get NO answer and produce an empty list — the
  //   two outcomes cannot be confused.
  {
    const env = build(src, { table: 'bonding_map', answers: [metaAnswer('valid_die_ref')] });
    await env.sandbox.populateValidDieRefList();
    r.vdOptions = optionValues(env.el.validDieRefList);
    r.vdFilteredByFixedTable =
      env.requests[0].includes(encodeURIComponent('"filter":"valid_die_ref"'));
    r.vdAskedCanvasTable = env.requests[0].includes(encodeURIComponent('"filter":"bonding_map"'));
    // The second focus must not re-ask: a complete list is cached, and that is the whole
    // reason focus-time loading is affordable.
    await env.sandbox.populateValidDieRefList();
    r.vdRequests = env.requests.length;
    if (strict) {
      check('the valid-die list asks for the FIXED table, not the canvas table',
        r.vdFilteredByFixedTable, true);
      check('...and never asks for the canvas table', r.vdAskedCanvasTable, false);
      check('valid-die list holds valid_die_ref\'s map_ids', r.vdOptions, META_ROWS.valid_die_ref);
      check('a COMPLETE map-key list is cached: two focuses cost one request', r.vdRequests, 1);
    }
  }

  // ── 1-quater. A TRUNCATED MAP-KEY LIST IS NOT CACHED AND SAYS SO ──────────────
  {
    const env = build(src, {
      table: 'bonding_map',
      answers: [metaAnswer('valid_die_ref', 900)],     // total 900 >> 3 rows
    });
    const baseTitle = env.el.validDieRefKey.title;
    await env.sandbox.populateValidDieRefList();
    r.vdTruncMark = env.el.validDieRefKey.dataset.suggest;
    r.vdTruncTitleHasTotal = env.el.validDieRefKey.title.includes('900');
    // The status is appended to the field's OWN tooltip, never in place of it — a
    // convenience layer that eats the explanation of what the field is for is a net loss.
    r.vdTitleKeptBase = env.el.validDieRefKey.title.startsWith(baseTitle);
    await env.sandbox.populateValidDieRefList();
    r.vdTruncRequests = env.requests.length;
    if (strict) {
      check('a cut map-key list is marked truncated', r.vdTruncMark, 'truncated');
      check('and the title names the real population size', r.vdTruncTitleHasTotal, true);
      check('the field\'s original tooltip survives the status note', r.vdTitleKeptBase, true);
      check('a cut list is NOT cached — the next focus asks again', r.vdTruncRequests, 2);
    }
  }

  // ── 1-quinquies. THE KEY CONTROL'S SHAPE — <select> ONLY WHEN THE LIST IS THE WHOLE
  //   POPULATION (user request 2026-08-04: "valid die 리스트를 datalist 말고 preset과 같은
  //   형식으로 가능?").
  //
  //   The trade-off this scores: a datalist SUGGESTS (an unlisted key can still be typed and
  //   loaded), a <select> CONSTRAINS (it cannot). So the dropdown is allowed only where the
  //   list is provably the entire population; otherwise the text input stays and a reachable
  //   map stays reachable. Three fixtures, one per condition that forfeits the dropdown, and
  //   each one is scored as a DISCRIMINATION against the complete case — a single observation
  //   would pass against an implementation that never shows the select at all, which is the
  //   most natural way to get this wrong while looking safe.
  {
    const shape = env => ({
      select: env.el.validDieRefSelect.style.display === 'none' ? 'hidden' : 'shown',
      input: env.el.validDieRefKey.style.display === 'none' ? 'hidden' : 'shown',
    });

    // (a) COMPLETE, and the current key is empty → the dropdown, exactly like the preset one.
    const envOk = build(src, { table: 'bonding_map', answers: [metaAnswer('valid_die_ref')] });
    await envOk.sandbox.populateValidDieRefList();
    r.vdShapeComplete = shape(envOk);
    r.vdSelectOptions = envOk.el.validDieRefSelect.children.map(o => o.value);
    // 🔴 THE EQUIVALENCE THAT MAKES THIS SAFE: the placeholder option's value is the EMPTY
    //    STRING — byte-identical to what an untouched text input holds — so "고르지 않음"
    //    and "비워 둠" reach the save/apply path as the same value, which is 원 기하.
    //    If this option ever carried a sentinel like 'none', an empty selection would be
    //    written as a DECLARATION and the map would be refused instead of drawn as a circle.
    r.vdEmptyOptionValue = envOk.el.validDieRefSelect.children[0].value;
    r.vdEmptyOptionSaysCircle = /원 기하/.test(envOk.el.validDieRefSelect.children[0].textContent);

    // (b) TRUNCATED → the input stays, and a key that is in NO list survives untouched.
    const envCut = build(src, {
      table: 'bonding_map', answers: [metaAnswer('valid_die_ref', 900)],
    });
    envCut.el.validDieRefKey.value = FREE;
    await envCut.sandbox.populateValidDieRefList();
    r.vdShapeTruncated = shape(envCut);
    r.vdTruncatedKeptFreeKey = envCut.el.validDieRefKey.value;
    r.vdTruncatedUnconstrained = constraintState(envCut.el.validDieRefKey);

    // (c) UNAVAILABLE (HTTP failure) → the input stays, free key survives.
    const envDown = build(src, {
      table: 'bonding_map',
      answers: [{ match: u => u.includes('/tables/wafer_map_metadata/data'), status: 503, body: {} }],
    });
    envDown.el.validDieRefKey.value = FREE;
    await envDown.sandbox.populateValidDieRefList();
    r.vdShapeUnavailable = shape(envDown);
    r.vdUnavailableKeptFreeKey = envDown.el.validDieRefKey.value;

    // (d) COMPLETE, but the CURRENT key is not in the list — the pre-pin declarations are
    //     exactly this. A <select> could not display that key at all, so the control would
    //     read "-- 원 기하 --" for a map that HAS a declaration: a designation shown as no
    //     designation. This is the condition that makes the whole change safe, and without
    //     it the change is itself the defect it is meant to avoid.
    const envLegacy = build(src, { table: 'bonding_map', answers: [metaAnswer('valid_die_ref')] });
    envLegacy.el.validDieRefKey.value = FREE;
    await envLegacy.sandbox.populateValidDieRefList();
    r.vdShapeLegacyKey = shape(envLegacy);
    r.vdLegacyKeptFreeKey = envLegacy.el.validDieRefKey.value;

    // (e) TRUNCATED with an EMPTY key. Separated from (b) on purpose: in (b) the key is also
    //     unlisted, so ONE guard failing is enough to keep the input and the other guard is
    //     never exercised. Here only the truncation can forfeit the dropdown, so this is the
    //     fixture that can tell "we checked the population" from "we checked the key".
    const envCutEmpty = build(src, {
      table: 'bonding_map', answers: [metaAnswer('valid_die_ref', 900)],
    });
    await envCutEmpty.sandbox.populateValidDieRefList();
    r.vdShapeTruncatedEmptyKey = shape(envCutEmpty);

    if (strict) {
      check('COMPLETE + empty key -> the dropdown is the control',
        r.vdShapeComplete, { select: 'shown', input: 'hidden' });
      check('...and it offers the placeholder plus every listed key',
        r.vdSelectOptions, ['', ...META_ROWS.valid_die_ref]);
      check('the empty selection is the EMPTY STRING, identical to an empty input (= 원 기하)',
        r.vdEmptyOptionValue, '');
      check('...and it says so in words', r.vdEmptyOptionSaysCircle, true);
      check('TRUNCATED -> the text input stays, so an unlisted key is still reachable',
        r.vdShapeTruncated, { select: 'hidden', input: 'shown' });
      check('a truncated list does not eat a hand-typed key', r.vdTruncatedKeptFreeKey, FREE);
      check('...and does not constrain the input either',
        r.vdTruncatedUnconstrained, { attrs: [], readOnly: false, disabled: false });
      check('UNAVAILABLE -> the text input stays',
        r.vdShapeUnavailable, { select: 'hidden', input: 'shown' });
      check('an unavailable list does not eat a hand-typed key', r.vdUnavailableKeptFreeKey, FREE);
      check('TRUNCATED with an EMPTY key -> still the text input (the POPULATION is the reason)',
        r.vdShapeTruncatedEmptyKey, { select: 'hidden', input: 'shown' });
      check('a key that is NOT in a COMPLETE list still keeps the text input',
        r.vdShapeLegacyKey, { select: 'hidden', input: 'shown' });
      check('...and that key is not silently dropped', r.vdLegacyKeptFreeKey, FREE);
      // Fixture-inactivity guard. Names the wrong implementation that survives without it:
      // if the complete case ALSO hid the select, all four shape checks could be satisfied by
      // an implementation that never shows the dropdown, and the user request would be
      // unimplemented while the harness stayed green.
      check('the axis is ACTIVE: the complete case and the three fallbacks DISAGREE',
        [r.vdShapeComplete.select !== r.vdShapeTruncated.select,
          r.vdShapeComplete.select !== r.vdShapeUnavailable.select,
          r.vdShapeComplete.select !== r.vdShapeLegacyKey.select], [true, true, true]);
    }
  }

  // ── 1-sexies. A SUCCESSFUL BUT EMPTY LIST GETS ITS OWN WORDS ──────────────────
  //   Silence is what a broken dropdown looks like. "조회는 됐고 정말로 0건" and "목록을
  //   못 만들었다" must not arrive as the same empty control with the same empty tooltip.
  {
    const env = build(src, {
      table: 'bonding_map',
      answers: [{
        match: u => u.includes('/tables/wafer_map_metadata/data'),
        body: { data: [], total: 0 },
      }],
    });
    const baseTitle = env.el.validDieRefKey.title;
    await env.sandbox.populateValidDieRefList();
    r.vdEmptyMark = env.el.validDieRefKey.dataset.suggest;
    r.vdEmptyTitleSpeaks = env.el.validDieRefKey.title !== baseTitle;
    r.vdEmptyTitleKeptBase = env.el.validDieRefKey.title.startsWith(baseTitle);
    if (strict) {
      // Still COMPLETE — the query succeeded. The state must not be forged into a failure.
      check('an empty-but-successful list is still COMPLETE, not unavailable',
        r.vdEmptyMark, undefined);
      check('...but it SAYS it is genuinely empty rather than staying silent',
        r.vdEmptyTitleSpeaks, true);
      check('...without eating the field\'s own tooltip', r.vdEmptyTitleKeptBase, true);
    }
  }

  // ── 2. `unavailable_reason` IS NOT AN EMPTY LIST ──────────────────────────────
  //   Scored as a DISCRIMINATION between two answers that are byte-identical except for
  //   that one field. Either the two outcomes differ, or the field was collapsed.
  {
    const mkEnv = (body) => {
      const env = build(src, {
        table: 'bonding_map', schema: SCHEMA_A,
        answers: [valuesAnswer('bonding_map', 'lot_id', body)],
      });
      env.sandbox.renderMetadataInputs();
      return env;
    };
    const emptyEnv = mkEnv(complete([]));
    await emptyEnv.sandbox.populateColumnValueDatalist(
      'bonding_map', 'lot_id',
      emptyEnv.sandbox.document.getElementById('meta-list-lot_id'),
      emptyEnv.sandbox.document.getElementById('meta-input-lot_id'), '');
    const emptyInput = emptyEnv.sandbox.document.getElementById('meta-input-lot_id');

    const REASON = '접두 인덱스 idx_suggest_bonding_map_lot_id 가 없습니다.';
    const unavEnv = mkEnv(unavailable(REASON));
    const unavInput = unavEnv.sandbox.document.getElementById('meta-input-lot_id');
    unavInput.value = FREE;
    await unavEnv.sandbox.populateColumnValueDatalist(
      'bonding_map', 'lot_id',
      unavEnv.sandbox.document.getElementById('meta-list-lot_id'), unavInput, '');

    r.emptyMark = emptyInput.dataset.suggest === undefined ? null : emptyInput.dataset.suggest;
    r.unavMark = unavInput.dataset.suggest === undefined ? null : unavInput.dataset.suggest;
    r.unavTitleCarriesReason = unavInput.title.includes(REASON);
    r.unavOptions = optionValues(unavEnv.sandbox.document.getElementById('meta-list-lot_id')).length;
    r.emptyOptions = optionValues(emptyEnv.sandbox.document.getElementById('meta-list-lot_id')).length;
    r.unavValueUntouched = unavInput.value;
    r.unavConstraints = constraintState(unavInput);
    if (strict) {
      check('a GENUINELY empty answer carries no unavailability marker', r.emptyMark, null);
      check('an answer with a named reason is marked unavailable', r.unavMark, 'unavailable');
      check('THE TWO ARE DISTINGUISHABLE (this is the whole axis)',
        r.emptyMark === r.unavMark, false);
      check('both show zero options — so the LIST alone cannot tell them apart',
        [r.emptyOptions, r.unavOptions], [0, 0]);
      check('the server\'s own reason text reaches the operator', r.unavTitleCarriesReason, true);
      check('unavailability does not disturb a hand-typed value', r.unavValueUntouched, FREE);
      check('and adds no constraint', r.unavConstraints,
        { attrs: [], readOnly: false, disabled: false });
    }
  }

  // ── 2-bis. UNAVAILABILITY IS NOT CACHED; A REFUSAL (4xx) IS ───────────────────
  //   Different failures, different lifetimes. An index can be built later, so "could not
  //   look" must be re-asked; "not a suggestion target" is a DECLARATION and asking again
  //   is waste. Collapsing these two the other way is the same defect class.
  {
    const env = build(src, {
      table: 'bonding_map', schema: SCHEMA_A,
      answers: [valuesAnswer('bonding_map', 'lot_id', unavailable('타임아웃'))],
    });
    env.sandbox.renderMetadataInputs();
    const list = env.sandbox.document.getElementById('meta-list-lot_id');
    const input = env.sandbox.document.getElementById('meta-input-lot_id');
    await env.sandbox.populateColumnValueDatalist('bonding_map', 'lot_id', list, input, '');
    await env.sandbox.populateColumnValueDatalist('bonding_map', 'lot_id', list, input, '');
    r.unavRequests = env.requests.length;

    const env4 = build(src, {
      table: 'bonding_map', schema: SCHEMA_A,
      answers: [{ match: u => u.includes('/columns/slot/values'), status: 400, body: {} }],
    });
    env4.sandbox.renderMetadataInputs();
    const list4 = env4.sandbox.document.getElementById('meta-list-slot');
    const input4 = env4.sandbox.document.getElementById('meta-input-slot');
    input4.value = FREE;
    await env4.sandbox.populateColumnValueDatalist('bonding_map', 'slot', list4, input4, '');
    await env4.sandbox.populateColumnValueDatalist('bonding_map', 'slot', list4, input4, '');
    r.refusedRequests = env4.requests.length;
    r.refusedMark = input4.dataset.suggest === undefined ? null : input4.dataset.suggest;
    r.refusedValue = input4.value;
    r.refusedConstraints = constraintState(input4);
    if (strict) {
      check('"could not look" is re-asked on the next focus', r.unavRequests, 2);
      check('"not a suggestion target" is learned: the second focus asks nothing',
        r.refusedRequests, 1);
      check('a refused column carries NO marker — it is a declaration, not a failure',
        r.refusedMark, null);
      check('a refused column is a plain text input: value and constraints untouched',
        [r.refusedValue, r.refusedConstraints],
        [FREE, { attrs: [], readOnly: false, disabled: false }]);
    }
  }

  // ── 2-ter. AN HTTP FAILURE IS ALSO NOT AN EMPTY COLUMN ────────────────────────
  {
    const env = build(src, {
      table: 'bonding_map', schema: SCHEMA_A,
      answers: [{ match: u => u.includes('/columns/lot_id/values'), status: 500, body: {} }],
    });
    env.sandbox.renderMetadataInputs();
    const input = env.sandbox.document.getElementById('meta-input-lot_id');
    input.value = FREE;
    await env.sandbox.populateColumnValueDatalist(
      'bonding_map', 'lot_id',
      env.sandbox.document.getElementById('meta-list-lot_id'), input, '');
    r.http500Mark = input.dataset.suggest === undefined ? null : input.dataset.suggest;
    r.http500Value = input.value;

    const envThrow = build(src, {
      table: 'bonding_map',
      answers: [{ match: u => u.includes('/tables/wafer_map_metadata/data'),
                  throws: 'NetworkError' }],
    });
    await envThrow.sandbox.populateValidDieRefList();
    r.netMark = envThrow.el.validDieRefKey.dataset.suggest === undefined
      ? null : envThrow.el.validDieRefKey.dataset.suggest;
    if (strict) {
      check('an HTTP 5xx is marked unavailable, not read as an empty column',
        r.http500Mark, 'unavailable');
      check('and it leaves the typed value alone', r.http500Value, FREE);
      check('a thrown fetch on the map-key list is marked unavailable too', r.netMark, 'unavailable');
    }
  }

  // ── 3. THE GENERATED FIELDS ARE REGENERATED ──────────────────────────────────
  //   (a) every generated input has a datalist, and it lives INSIDE the container
  //   (b) after a regeneration for a different table, the previous table's datalists are
  //       UNREACHABLE — not merely empty
  //   (c) no per-node listener is ever attached, so regeneration cannot leak any
  {
    const env = build(src, { table: 'bonding_map', schema: SCHEMA_A });
    env.sandbox.renderMetadataInputs();
    const doc = env.sandbox.document;
    r.genPairs = SCHEMA_A.map_key_columns.map(c => {
      const input = doc.getElementById(`meta-input-${c}`);
      const list = doc.getElementById(`meta-list-${c}`);
      let inContainer = false;
      for (let p = list && list.parent; p; p = p.parent) if (p === env.container) inContainer = true;
      return {
        col: c,
        listAttr: input ? input.getAttribute('list') : null,
        listExists: !!list,
        listInsideContainer: inContainer,
        inputListeners: input ? Object.keys(input.listeners).length : -1,
      };
    });

    // The table changes: schema swapped, container rebuilt. `base` arrives, `lot_id`/`slot` go.
    env.sandbox.tableSchema = SCHEMA_B;
    env.sandbox.renderMetadataInputs();
    r.afterSwitch = {
      oldInput: doc.getElementById('meta-input-lot_id') === null,
      oldList: doc.getElementById('meta-list-lot_id') === null,
      oldList2: doc.getElementById('meta-list-slot') === null,
      newList: doc.getElementById('meta-list-base') !== null,
    };

    // Five more regenerations: the delegated listeners live on the container, so nothing
    // accumulates anywhere.
    for (let i = 0; i < 5; i++) env.sandbox.renderMetadataInputs();
    r.containerListenerLoad = Object.keys(env.container.listeners).length;
    r.perNodeListeners = doc.querySelectorAll('[id^="meta-input-"]')
      .reduce((n, i) => n + Object.keys(i.listeners).length, 0);
    r.fieldCount = doc.querySelectorAll('[id^="meta-input-"]').length;
    if (strict) {
      // Two separate assertions on purpose: the binding and the listener load are different
      // axes, and a composite check would let one of them ride on the other's failure.
      check('every generated field is bound to its own datalist, inside the container',
        r.genPairs.map(({ inputListeners, ...rest }) => rest),
        SCHEMA_A.map_key_columns.map(c => ({
          col: c, listAttr: `meta-list-${c}`, listExists: true, listInsideContainer: true,
        })));
      check('no generated input carries a listener of its own',
        r.genPairs.map(p => p.inputListeners), SCHEMA_A.map_key_columns.map(() => 0));
      check('after a table change the PREVIOUS table\'s datalists are unreachable, not stale',
        r.afterSwitch, { oldInput: true, oldList: true, oldList2: true, newList: true });
      check('renderMetadataInputs attaches no listener to any node it creates',
        r.perNodeListeners, 0);
      check('and it attaches none to the container either (the wiring is done once, in '
        + 'initDOMElements)', r.containerListenerLoad, 0);
      check('six regenerations leave exactly one field set', r.fieldCount,
        SCHEMA_B.map_key_columns.length);
    }
  }

  // ── 3-bis. A TABLE SWITCH DROPS THE COLUMN CACHE ─────────────────────────────
  //   Same column NAME on two tables is the case that makes a table-blind cache visible.
  //   `dropColumnValueCache` is what stops the new table's field from showing the old
  //   table's values, and the request count is what proves it ran.
  {
    const env = build(src, {
      table: 'bonding_map', schema: { ...SCHEMA_A, map_key_columns: ['lot_id'] },
      answers: [
        { match: u => u.includes('/tables/bonding_map/columns/lot_id/values'),
          body: complete(['K23A0011', 'K23A0012']) },
        { match: u => u.includes('/tables/core_defect_map/columns/lot_id/values'),
          body: complete(['CORE-9001']) },
      ],
    });
    env.sandbox.renderMetadataInputs();
    const doc = env.sandbox.document;
    await env.sandbox.populateColumnValueDatalist('bonding_map', 'lot_id',
      doc.getElementById('meta-list-lot_id'), doc.getElementById('meta-input-lot_id'), '');
    r.beforeSwitchValues = optionValues(doc.getElementById('meta-list-lot_id'));

    env.sandbox.dropColumnValueCache('bonding_map');
    env.sandbox.selectedTable = 'core_defect_map';
    env.sandbox.renderMetadataInputs();
    await env.sandbox.populateColumnValueDatalist('core_defect_map', 'lot_id',
      doc.getElementById('meta-list-lot_id'), doc.getElementById('meta-input-lot_id'), '');
    r.afterSwitchValues = optionValues(doc.getElementById('meta-list-lot_id'));
    r.crossTableSurvivors = r.afterSwitchValues.filter(v => r.beforeSwitchValues.includes(v)).length;
    r.switchRequests = env.requests.length;
    if (strict) {
      check('the new table\'s field shows the new table\'s values',
        r.afterSwitchValues, ['CORE-9001']);
      check('zero values from the previous table survive the switch', r.crossTableSurvivors, 0);
      check('and the new table really was asked (2 requests, not 1 cache hit)',
        r.switchRequests, 2);
    }
  }

  // ── 3-ter. SWITCHING AWAY AND BACK RE-ASKS THE SAME COLUMN ───────────────────
  //   The cache key already carries the table, so switching to a DIFFERENT table proves
  //   nothing about `dropColumnValueCache` — it would re-ask either way. The case that can
  //   only be answered by the drop is coming BACK to a table whose column is already cached:
  //   values may have been added while the operator was elsewhere, and a suggestion list
  //   that silently predates them is the stale-list defect wearing a different hat.
  {
    const env = build(src, {
      table: 'bonding_map', schema: { ...SCHEMA_A, map_key_columns: ['lot_id'] },
      answers: [{ match: u => u.includes('/tables/bonding_map/columns/lot_id/values'),
                  body: complete(['K23A0011']) }],
    });
    env.sandbox.renderMetadataInputs();
    const doc = env.sandbox.document;
    const ask = () => env.sandbox.populateColumnValueDatalist('bonding_map', 'lot_id',
      doc.getElementById('meta-list-lot_id'), doc.getElementById('meta-input-lot_id'), '');
    await ask();
    r.backAgainFirst = env.requests.length;
    await ask();                                     // still cached: no request
    r.backAgainCached = env.requests.length;
    env.sandbox.dropColumnValueCache('bonding_map'); // what switchTable does on re-entry
    env.sandbox.renderMetadataInputs();
    await env.sandbox.populateColumnValueDatalist('bonding_map', 'lot_id',
      doc.getElementById('meta-list-lot_id'), doc.getElementById('meta-input-lot_id'), '');
    r.backAgainAfterDrop = env.requests.length;
    if (strict) {
      check('a complete column answer is cached within one table visit',
        [r.backAgainFirst, r.backAgainCached], [1, 1]);
      check('re-entering the SAME table re-asks it (the cache was dropped)',
        r.backAgainAfterDrop, 2);
    }
  }

  // ── 4. A COMPLETE LIST IS NARROWED BY THE BROWSER; A CUT ONE IS RE-ASKED ──────
  //   This is the honesty rule for truncation, expressed as REQUEST COUNTS. Narrowing a
  //   list the server already cut would present a sample as a population.
  {
    const env = build(src, {
      table: 'bonding_map', schema: { ...SCHEMA_A, map_key_columns: ['lot_id'] },
      answers: [valuesAnswer('bonding_map', 'lot_id', complete(['K23A0011', 'K23A0012']))],
    });
    env.sandbox.renderMetadataInputs();
    const doc = env.sandbox.document;
    const input = doc.getElementById('meta-input-lot_id');
    input.value = '';
    input.dispatch('focusin');                       // not wired here — call directly instead
    await env.sandbox.onMetaInputSuggest({ type: 'focusin', target: input });
    await new Promise(r2 => setImmediate(r2));
    r.completeMark = input.dataset.suggest === undefined ? null : input.dataset.suggest;
    const afterFocus = env.requests.length;
    for (const ch of 'K23A') {
      input.value += ch;
      env.sandbox.onMetaInputSuggest({ type: 'input', target: input });
    }
    await new Promise(r2 => setImmediate(r2));
    r.completeExtraRequests = env.requests.length - afterFocus;
    // Free typing: filling the list must never write into the field.
    r.completeTypedValue = input.value;
    // Re-focusing after typing is the path the `input` early-return does NOT cover, so it is
    // where the complete-snapshot reuse is scored on its own.
    await env.sandbox.onMetaInputSuggest({ type: 'focusin', target: input });
    await new Promise(r2 => setImmediate(r2));
    r.refocusExtraRequests = env.requests.length - afterFocus;

    const envCut = build(src, {
      table: 'bonding_map', schema: { ...SCHEMA_A, map_key_columns: ['lot_id'] },
      answers: [valuesAnswer('bonding_map', 'lot_id', cut(['K23A0011', 'K23A0012']))],
    });
    envCut.sandbox.renderMetadataInputs();
    const doc2 = envCut.sandbox.document;
    const input2 = doc2.getElementById('meta-input-lot_id');
    input2.value = '';
    await envCut.sandbox.onMetaInputSuggest({ type: 'focusin', target: input2 });
    await new Promise(r2 => setImmediate(r2));
    r.cutMark = input2.dataset.suggest === undefined ? null : input2.dataset.suggest;
    const afterFocus2 = envCut.requests.length;
    input2.value = 'K2';
    await envCut.sandbox.onMetaInputSuggest({ type: 'input', target: input2 });
    await new Promise(r2 => setImmediate(r2));
    r.cutExtraRequests = envCut.requests.length - afterFocus2;
    r.cutPrefixOnWire = envCut.requests[envCut.requests.length - 1].includes('prefix=K2');
    if (strict) {
      check('a complete answer is not marked', r.completeMark, null);
      check('four more typed characters over a COMPLETE list cost zero requests',
        r.completeExtraRequests, 0);
      check('the field still holds exactly what was typed, not a suggested value',
        r.completeTypedValue, 'K23A');
      check('re-focusing a completely-answered column costs zero requests too',
        r.refocusExtraRequests, 0);
      check('a cut answer is marked truncated', r.cutMark, 'truncated');
      check('typing over a CUT list re-asks the server', r.cutExtraRequests, 1);
      check('and it re-asks with the typed prefix', r.cutPrefixOnWire, true);
    }
  }

  // ── 5. THE MARKUP DOES NOT CONSTRAIN EITHER ──────────────────────────────────
  //   The free-typing path can be broken where no JS runs. Read the file.
  {
    const ovTag = /<input[^>]*id="overlay-src-key"[^>]*>/.exec(HTML);
    const vdTag = /<input[^>]*id="valid-die-ref-key"[^>]*>/.exec(HTML);
    r.markup = {
      overlayHasList: !!(ovTag && /list="overlay-src-key-list"/.test(ovTag[0])),
      overlayDatalistExists: /<datalist id="overlay-src-key-list">/.test(HTML),
      overlayUnconstrained: !!(ovTag && !/\b(required|pattern=|readonly|disabled)\b/i.test(ovTag[0])),
      validDieStillHasList: !!(vdTag && /list="valid-die-ref-list"/.test(vdTag[0])),
      validDieUnconstrained: !!(vdTag && !/\b(required|pattern=|readonly|disabled)\b/i.test(vdTag[0])),
      generatedFieldsGetList: /input\.setAttribute\('list', `meta-list-\$\{col\}`\)/.test(src),
      generatedFieldsUnconstrained: !/input\.(required|pattern|readOnly)\s*=/.test(
        fn(src, 'renderMetadataInputs')),
    };
    if (strict) {
      check('the overlay key input suggests and does not constrain', r.markup, {
        overlayHasList: true, overlayDatalistExists: true, overlayUnconstrained: true,
        validDieStillHasList: true, validDieUnconstrained: true,
        generatedFieldsGetList: true, generatedFieldsUnconstrained: true,
      });
    }
  }

  return r;
}

// ── Baseline ────────────────────────────────────────────────────────────────────
console.log('=== BASELINE ===');
await runChecks(SRC, { strict: true });
console.log(`  ${pass} passed, ${fail} failed`);

// ── Mutants (must be CAUGHT) ────────────────────────────────────────────────────
const MUTATIONS = [
  {
    name: 'M1 [HIGH] `unavailable_reason` is collapsed into an empty result',
    find: `  if (body && body.unavailable_reason) {`,
    repl: `  if (false) {`,
    breaks: '"the server could not look" is distinguishable from "the column is empty"',
  },
  {
    name: 'M2 [HIGH] the unavailability is cached, so the column stays dead for the session',
    find: `    columnValueTruncated.delete(key);
    columnValueComplete.delete(key);
    fillDatalist(listEl, []);`,
    repl: `    columnValueTruncated.delete(key);
    columnValueComplete.set(key, { prefix: pfx, values: [] });
    fillDatalist(listEl, []);`,
    breaks: 'an index built later is picked up on the next focus',
  },
  {
    name: 'M3 [HIGH] a CUT list is cached and then narrowed locally (a sample as a population)',
    find: `  if (body && body.truncated) {
    columnValueTruncated.add(key);
    columnValueComplete.delete(key);`,
    repl: `  if (body && body.truncated) {
    columnValueTruncated.delete(key);
    columnValueComplete.set(key, { prefix: pfx, values });`,
    breaks: 'typing over a cut list re-asks the server',
  },
  {
    name: 'M4 [HIGH] the generated datalist is parented on the body (orphan survives the switch)',
    find: `    formGroup.appendChild(dataList);`,
    // The plausible defect, not an implausible one: a datalist appended somewhere global
    // still WORKS (`list=` resolves by id document-wide) and still fills — it simply keeps
    // the previous table's values after the fields are rebuilt, and looks completely normal.
    repl: `    document.getElementById('document-body').appendChild(dataList); /* MUTANT */`,
    breaks: 'a regenerated field set leaves no reachable stale datalist',
  },
  {
    name: 'M5 [HIGH] the map-key list is filtered by the CANVAS table, not the overlay source',
    find: `async function populateOverlayKeyList() {
  const table = el.overlaySrcTable ? el.overlaySrcTable.value : '';`,
    repl: `async function populateOverlayKeyList() {
  const table = selectedTable;`,
    breaks: 'the overlay list is the source table\'s population',
  },
  {
    name: 'M6 [MEDIUM] a truncated map-key list is cached as if it were complete',
    find: `  if (Number.isFinite(total) && total > rowCount) {`,
    repl: `  if (false) {`,
    breaks: 'a cut map-key list is re-asked and is marked',
  },
  {
    name: 'M7 [MEDIUM] an HTTP failure is served as an empty list',
    find: `    if (!res.ok) {
      if (!isCurrent()) return;   // 낡은 실패가 새 질문의 상태를 덮지 못한다
      markSuggestState(input, 'unavailable',`,
    repl: `    if (!res.ok) {
      fillDatalist(listEl, []); markSuggestState(input, '', ''); return; /* MUTANT */
      markSuggestState(input, 'unavailable',`,
    breaks: 'a 5xx is not read as an empty column',
  },
  {
    name: 'M8 [MEDIUM] a 4xx refusal is not learned, so every focus pays for it again',
    find: `      columnValueRefused.set(key, true);`,
    repl: `      /* MUTANT: never learned */`,
    breaks: 'a non-suggestible column is asked once, not on every focus',
  },
  {
    name: 'M9 [MEDIUM] the column cache is table-blind (the switch shows the old values)',
    find: `function colValueKey(table, column) { return \`\${table}::\${column}\`; }`,
    repl: `function colValueKey(table, column) { return \`\${column}\`; /* MUTANT */ }`,
    breaks: 'the same column name on two tables holds two populations',
  },
  {
    name: 'M10 [MEDIUM] the table switch keeps the column cache',
    find: `  Array.from(columnValueComplete.keys()).forEach(k => {
    if (k.startsWith(prefix)) columnValueComplete.delete(k);
  });`,
    repl: `  /* MUTANT: the previous table's values stay offered */`,
    breaks: 'a table switch really re-asks',
  },
  {
    name: 'M11 [MEDIUM] the datalist writes the first candidate into the input (a validator)',
    find: `function fillDatalist(listEl, values) {
  if (!listEl) return;`,
    repl: `function fillDatalist(listEl, values) {
  if (!listEl) return;
  if (values.length && listEl.parent && listEl.parent.children) {
    listEl.parent.children.forEach(c => { if (c.tagName === 'input') c.value = values[0]; });
  }`,
    breaks: 'a hand-typed value survives every answer shape',
  },
  {
    name: 'M12 [MEDIUM] `markSuggestState` destroys the input\'s own tooltip',
    find: `  const base = input.dataset.suggestTitleBase;`,
    repl: `  const base = ''; /* MUTANT: the original explanation is gone */`,
    breaks: 'the field keeps explaining what it is for',
    // Scored via the valid-die title, which starts non-empty in the fixture.
  },
  {
    // NOT a mutation of the `input` early-return in `onMetaInputSuggest`. That guard and this
    // one are REDUNDANT for request counting — removing either alone changes no observable
    // count, so a mutant on it would escape for a good reason rather than a bad one. The
    // reuse test is the guard that owns the FOCUS path, where nothing else covers it.
    name: 'M13 [MEDIUM] the complete snapshot is never reused (every focus pays again)',
    find: `  return prefix.length >= cachedPrefix.length
    && prefix.toLowerCase().startsWith(cachedPrefix.toLowerCase());`,
    repl: `  return false; /* MUTANT: the cache exists and is never consulted */`,
    breaks: 're-focusing a completely-answered column costs nothing',
  },
  {
    name: 'M16 [HIGH] a superseded answer is allowed to overwrite the newer list',
    find: `    if (!isCurrent()) return;   // 이 목록에 대한 더 새로운 질문이 이미 있다
    const rows = (result && Array.isArray(result.data)) ? result.data : [];`,
    repl: `    const rows = (result && Array.isArray(result.data)) ? result.data : [];`,
    breaks: 'the last question is the one whose answer is shown',
  },
  {
    name: 'M14 [MEDIUM] the generated input loses its `list` binding',
    find: `    input.setAttribute('list', \`meta-list-\${col}\`);`,
    repl: `    /* MUTANT: the datalist exists but nothing points at it */`,
    breaks: 'every generated field is bound to its datalist',
  },
  {
    name: 'M15 [MEDIUM] per-node listeners are attached on every regeneration',
    find: `    formGroup.appendChild(input);`,
    repl: `    input.addEventListener('focus', () => {}); /* MUTANT: leaks one per rebuild */
    formGroup.appendChild(input);`,
    breaks: 'regeneration attaches nothing to the nodes it creates',
  },
  // ── The key control's shape (1-a, 2026-08-04). Each anchor below is UNIQUE in the file;
  //    a repeated anchor lands on the first match and scores a different function.
  {
    name: 'M16 [HIGH] the dropdown is shown even when the list is NOT the whole population',
    find: `  const useSelect = listIsWholePopulation && curIsSelectable && keys.length > 0;`,
    repl: `  const useSelect = curIsSelectable && keys.length > 0;`,
    breaks: 'a truncated or failed list forfeits the <select>, so an unlisted map stays reachable',
  },
  {
    name: 'M17 [HIGH] the dropdown is shown even when the CURRENT key is not in it',
    find: `  const curIsSelectable = (cur === '' || keys.indexOf(cur) !== -1);   // ③의 부정`,
    repl: `  const curIsSelectable = true;   // MUTANT: a declared key it cannot display reads as 원 기하`,
    breaks: 'a map that HAS a declaration is never shown as having none',
  },
  {
    name: 'M18 [HIGH] the empty selection carries a sentinel instead of the empty string',
    find: `  none.value = '';
  // 🔴 빈 선택은 빈 입력칸과 **정확히 같은 뜻**이다`,
    repl: `  none.value = 'none';
  // MUTANT: 빈 선택이 선언으로 저장된다
  // 🔴 빈 선택은 빈 입력칸과 **정확히 같은 뜻**이다`,
    breaks: '"고르지 않음" reaches the save path as the same value as an empty input (= 원 기하)',
  },
  {
    name: 'M19 [MEDIUM] the dropdown is never shown at all (the request silently unimplemented)',
    find: `  sel.style.display = useSelect ? '' : 'none';`,
    repl: `  sel.style.display = 'none';`,
    breaks: 'a complete population IS offered as a dropdown',
  },
  {
    name: 'M20 [MEDIUM] a successful empty list goes back to silence',
    // NB the first draft of this mutation was `'' || \`...\`` — which still evaluates to the
    // message, so it changed the TEXT without changing the BEHAVIOUR and escaped for the
    // right reason. A mutation that does not mutate proves nothing; this one really silences
    // the branch and leaves the original call unreachable.
    find: `    markSuggestState(input, '',
      \`\${table}에 등록된 맵이 아직 없습니다`,
    repl: `    markSuggestState(input, '', '');
    if (false) markSuggestState(input, '',
      \`\${table}에 등록된 맵이 아직 없습니다`,
    breaks: '"genuinely zero" is distinguishable from a broken control',
  },
];

// ── Controls (must ESCAPE) ──────────────────────────────────────────────────────
// A detector that fires on either of these is reading source text, not behaviour, and its
// "caught" score belongs to the edit rather than to the axis it claims.
const CONTROLS = [
  {
    name: 'C1 control: a consistent local rename (behaviour identical)',
    find: `  const cached = mapKeyListCache.get(table);
  if (cached) { markSuggestState(input, '', ''); fillDatalist(listEl, cached); return; }`,
    repl: `  const memo = mapKeyListCache.get(table);
  if (memo) { markSuggestState(input, '', ''); fillDatalist(listEl, memo); return; }`,
  },
  {
    name: 'C2 control: a comment-only edit (no behaviour at all)',
    find: `function colValueKey(table, column) { return \`\${table}::\${column}\`; }`,
    repl: `// MUTANT-CONTROL: this comment changes nothing.
function colValueKey(table, column) { return \`\${table}::\${column}\`; }`,
  },
];

async function sweep(list, expectCaught, heading) {
  console.log(`\n=== ${heading} ===`);
  let applied = 0, caught = 0;
  const notApplied = [], wrong = [];
  for (const m of list) {
    if (!SRC.includes(m.find)) {
      notApplied.push(m.name);
      console.error(`  NOT APPLIED  ${m.name}\n    search string not found`);
      continue;
    }
    applied++;
    const mutated = SRC.replace(m.find, m.repl);
    const before = { pass, fail, failures: failures.length };
    let threw = null;
    quiet = true;
    try { await runChecks(mutated, { strict: true }); }
    catch (err) { threw = err; }
    quiet = false;
    const broke = fail > before.fail || threw !== null;
    const detectedBy = failures.slice(before.failures);
    pass = before.pass; fail = before.fail; failures.length = before.failures;

    if (broke) caught++;
    if (broke === expectCaught) {
      const why = threw ? `threw: ${String(threw.message).slice(0, 70)}`
        : (broke ? `${detectedBy.length} assertion(s), first: ${detectedBy[0]}` : 'no detector fired');
      console.log(`  ${expectCaught ? 'caught ' : 'escaped'} ${m.name}\n            by ${why}`);
    } else {
      wrong.push(m.name);
      console.error(`  ${expectCaught ? 'ESCAPED' : 'CAUGHT'} ${m.name}\n    ${
        expectCaught ? `expected to break: ${m.breaks}`
          : `a semantics-preserving edit fired: ${detectedBy.join(' | ')}`}`);
    }
  }
  return { applied, caught, notApplied, wrong, declared: list.length };
}

const mut = await sweep(MUTATIONS, true, 'MUTATION SWEEP');
const ctl = await sweep(CONTROLS, false, 'CONTROL SWEEP (these must ESCAPE)');

console.log('\n=== SUMMARY ===');
console.log(`  baseline assertions : ${pass} passed, ${fail} failed`);
// H1 protocol: the runner reads this line to tell "red with N assertions" from a crash.
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
console.log(`  mutations declared  : ${mut.declared}`);
console.log(`  mutations APPLIED   : ${mut.applied}`);
console.log(`  mutations CAUGHT    : ${mut.caught}`);
console.log(`  controls APPLIED    : ${ctl.applied}`);
console.log(`  controls ESCAPED    : ${ctl.applied - ctl.caught} of ${ctl.applied} (must be all)`);
if (mut.notApplied.length) console.error(`  NOT APPLIED: ${mut.notApplied.join(' | ')}`);
if (mut.wrong.length) console.error(`  ESCAPED: ${mut.wrong.join(' | ')}`);
if (ctl.notApplied.length) console.error(`  CONTROLS NOT APPLIED: ${ctl.notApplied.join(' | ')}`);
if (ctl.wrong.length) console.error(`  CONTROLS WRONGLY CAUGHT: ${ctl.wrong.join(' | ')}`);
if (failures.length) console.error(`  baseline failures: ${failures.join(' | ')}`);

const ok = fail === 0
  && mut.notApplied.length === 0 && mut.wrong.length === 0 && mut.applied === mut.declared
  && ctl.notApplied.length === 0 && ctl.wrong.length === 0 && ctl.applied === ctl.declared;
console.log(ok
  ? '\nOK — suggestion without constraint, and every declared defect is detected.\n'
  : '\nFAILED\n');
process.exit(ok ? 0 : 1);
