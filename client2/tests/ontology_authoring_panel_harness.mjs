// What actually reaches the screen in the ontology AUTHORING panels.
// Run: node client2/tests/ontology_authoring_panel_harness.mjs
//
// 🔴 THE ASSERTIONS ARE SCOPED TO CONTAINERS, NOT TO THE PAGE. A count of "how many
// times the word 파생 appears" is satisfied by the bucket HEADING alone, so deleting
// every row would stay green -- the legend making the assertion vacuous. Every count
// below is taken INSIDE the bucket element it is about, and the last block proves the
// counts bite by deleting the rows and requiring the numbers to move.
//
// The second thing measured here is the completion criterion "closed lists are
// server-supplied": the chips rendered for a candidate list are compared element-wise
// against the payload that produced them, so a literal introduced in the view would have
// to match the server's list exactly to pass, and would drift the moment it changed.

let ran = 0;
let failed = 0;
const check = (name, condition, detail = '') => {
  ran += 1;
  if (!condition) { failed += 1; console.error(`✗ ${name} ${detail}`); }
};
const eq = (name, actual, expected) =>
  check(name, actual === expected, `expected ${expected}, got ${actual}`);

// --- minimal DOM, enough for the `h()` helper the view uses -----------------------
function element(tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    children: [],
    attrs: Object.create(null),
    _text: '',
    _classes: [],
    dataset: Object.create(null),
    get className() { return this._classes.join(' '); },
    set className(value) {
      this._classes = String(value).split(/\s+/).filter(Boolean);
    },
    classList: {
      add(...names) { for (const n of names) if (!node._classes.includes(n)) node._classes.push(n); },
      contains(name) { return node._classes.includes(name); },
    },
    append(...items) {
      for (const item of items) if (item) this.children.push(item);
    },
    appendChild(child) { this.children.push(child); return child; },
    replaceChildren(...items) { this.children = items.filter(Boolean); },
    setAttribute(key, value) { this.attrs[String(key)] = String(value); },
    getAttribute(key) {
      return Object.prototype.hasOwnProperty.call(this.attrs, String(key))
        ? this.attrs[String(key)] : null;
    },
    querySelector() { return null; },
    addEventListener() {},
    set textContent(value) { this._text = String(value); this.children = []; },
    get textContent() {
      return this._text + this.children.map((child) => child.textContent).join('');
    },
  };
  return node;
}
globalThis.document = { createElement: element };
globalThis.requestAnimationFrame = (fn) => fn();

const { renderOntologyExplorer } = await import('../src/ontology_explorer_view.js');
const { initialExplorerState } = await import('../src/ontology_explorer_store.js');

const walk = (node, out = []) => {
  out.push(node);
  for (const child of node.children || []) walk(child, out);
  return out;
};
const byClass = (root, name) =>
  walk(root).filter((node) => node._classes?.includes(name));
// A harness that dies on the first missing node hides every assertion after it, which
// is how one defect comes to look like one failure. Index through this instead.
const at = (list, index) => list[index] || element('span');
const inside = (root, container, name) => {
  const box = byClass(root, container)[0];
  return box ? byClass(box, name) : [];
};

// --- a plan shaped exactly like `authoring_plan()` output --------------------------
const CANDIDATES = ['dt_cell_key', 'dt_index', 'dt_job', 'event_time'];
const field = (over) => ({
  path: 'bundle.x', step: 'sources', label: '칸', state: 'answered',
  tier: 'constrained_input', value: null, declared: null, has_declared: false,
  conflicts: false, ground: null, candidates: null, universe: null,
  universe_note: '', comparison: 'equal', disposition: '', forbidden: [],
  note: '', refusals: [],
  ...over,
});
const PLAN = {
  physical_schema_file: 'table_config.json',
  config_source: { file: '/root/ledger_config.json', state: 'present' },
  steps: [
    { id: 'entities', label: '엔터티', sections: ['entities'], declared: 3,
      status: 'ready', derived: 0, missing: 0, unanswered: 0, answered: 3 },
    { id: 'profiles', label: '프로필', sections: ['profiles'], declared: 2,
      status: 'blocked', derived: 2, missing: 1, unanswered: 0, answered: 4 },
    { id: 'sources', label: '소스', sections: ['sources'], declared: 0,
      status: 'empty', derived: 0, missing: 0, unanswered: 0, answered: 0 },
  ],
  fields: [
    field({
      path: 'bundle.profiles.dt-job@1.packs', label: 'packs', step: 'profiles',
      state: 'derived', tier: 'structural', value: ['dt-job@1'],
      declared: ['dt-job@1'], has_declared: true,
      disposition: 'grammar_requires_it',
      ground: {
        rule: 'profile_packs_from_mapping_uses',
        text: '채움: mappings의 use 2건이 쓰는 팩',
        from_paths: ['bundle.profiles.dt-job@1.mappings[0].use',
          'bundle.profiles.dt-job@1.mappings[1].use'],
        from_keys: ['profile|dt-job@1'],
        from_value: ['dt-job@1'],
      },
    }),
    field({
      path: 'bundle.profiles.dt-job@1.mappings[0].bind.subject.keys', label: '식별키 이름',
      step: 'profiles', state: 'derived', tier: 'structural', value: ['dt_job'],
      declared: ['lot'], has_declared: true, conflicts: true,
      disposition: 'default_overridable',
      ground: {
        rule: 'entity_binding_keys_from_entity', text: '채움: DTJob@1의 식별키',
        from_paths: ['bundle.entities.DTJob@1.keys'], from_keys: ['entity|DTJob@1'],
        from_value: ['dt_job'],
      },
    }),
    field({
      path: 'bundle.profiles.dt-job@1.mappings[1].bind.count', label: '역할 count',
      step: 'profiles', state: 'missing', tier: 'constrained_input',
      candidates: ['column', 'constant'],
      refusals: [{ code: 'missing_required_role',
        path: 'bundle.profiles.dt-job@1.mappings[1].bind.count',
        message: "Claim requires role 'count'" }],
    }),
    field({
      path: 'bundle.sources.dt_job.driver.identity', label: 'identity', step: 'sources',
      state: 'unanswered', candidates: CANDIDATES, universe: 'PREPARED',
      universe_note: '물리 표 + 준비기 산출 컬럼',
    }),
    field({ path: 'bundle.entities.DTJob@1.keys', label: '식별키', step: 'entities',
      state: 'answered', value: ['dt_job'] }),
  ],
  counts: { derived: 2, missing: 1, unanswered: 1, answered: 1 },
  force_summary: { grammar_requires_it: 1, default_overridable: 1 },
  refusals: [],
  unattached_refusals: [
    { code: 'missing_field', path: 'bundle.vocabulary', message: 'field is required' },
  ],
};

const stateWith = (plan) => ({
  ...initialExplorerState,
  authoring: plan,
  detailTab: 'authoring',
  activeSnapshot: { snapshot_hash: 'abc12345', valid: true },
  viewContext: { mode: 'active', context_token: 'active:abc12345' },
  selection: {
    key: 'profile|dt-job@1', canonical_id: 'dt-job@1', kind: 'profile',
    config_path: 'bundle.profiles.dt-job@1', compile_status: 'valid',
    config_file: 'ledger_config.json',
  },
  navigation: { back: [], forward: [] },
});

const render = (plan) => {
  const root = element('div');
  renderOntologyExplorer(root, stateWith(plan));
  return root;
};

// ── A. the step bar: server steps, server labels ──────────────────────────────────
{
  const root = render(PLAN);
  const steps = byClass(root, 'oe-step');
  eq('A1 one chip per server step', steps.length, PLAN.steps.length);
  check('A2 labels come from the payload, not the view',
    PLAN.steps.every((step, i) => at(steps, i).textContent.includes(step.label)));
  check('A3 the step holding the selection is marked',
    at(steps, 1).classList.contains('is-here'),
    steps.map((s) => s.className).join(' | '));
  check('A4 a blocked step is marked blocked', at(steps, 1).classList.contains('is-blocked'));
  check('A5 an empty step says so', at(steps, 2).textContent.includes('비었음'));
  check('A6 the step bar renders with no selection at all', (() => {
    const blank = element('div');
    renderOntologyExplorer(blank, { ...stateWith(PLAN), selection: null });
    return byClass(blank, 'oe-step').length === PLAN.steps.length;
  })());
}

// ── B. every derived field renders its ground NEXT TO the value ───────────────────
{
  const root = render(PLAN);
  const derivedRows = inside(root, 'oe-bucket--derived', 'oe-field');
  const derivedGrounds = inside(root, 'oe-bucket--derived', 'oe-ground');
  eq('B1 the derived bucket holds every derived row', derivedRows.length, 2);
  eq('B2 every derived row carries a ground block',
    derivedGrounds.length, derivedRows.length);
  check('B3 the ground states its sentence',
    at(derivedGrounds, 0).textContent.includes('채움: mappings의 use 2건이 쓰는 팩'));
  check('B4 the ground names the declaration it came from',
    at(derivedGrounds, 0).textContent.includes('bundle.profiles.dt-job@1.mappings[0].use'));
  check('B5 the ground is inside the field card, not a separate tooltip layer',
    byClass(at(derivedRows, 0), 'oe-ground').length === 1);
  check('B6 the derived value itself is rendered',
    at(derivedRows, 0).textContent.includes('dt-job@1'));
  check('B7 a derived row that disagrees with the file says so',
    byClass(at(derivedRows, 1), 'oe-field-conflict').length === 1
      && at(byClass(at(derivedRows, 1), 'oe-field-conflict'), 0).textContent.includes('lot'));
  check('B8 derived rows offer no candidate picker (they are not questions)',
    byClass(at(derivedRows, 0), 'oe-candidates').length === 0);
}

// ── C. missing and unanswered are named, with the server's own codes ──────────────
{
  const root = render(PLAN);
  const missing = inside(root, 'oe-bucket--missing', 'oe-field');
  eq('C1 the missing bucket holds the missing row', missing.length, 1);
  const refusal = byClass(at(missing, 0), 'oe-field-refusal');
  eq('C2 the refusal is shown verbatim', refusal.length, 1);
  check('C3 the stable code is on screen',
    at(refusal, 0).textContent.includes('missing_required_role'));
  const unanswered = inside(root, 'oe-bucket--unanswered', 'oe-field');
  eq('C4 the unanswered bucket holds the free question', unanswered.length, 1);
  const chips = byClass(at(byClass(at(unanswered, 0), 'oe-candidates'), 0), 'oe-chip');
  eq('C5 one chip per server candidate, no more', chips.length, CANDIDATES.length);
  check('C6 the chips ARE the server list, element for element',
    chips.every((chip, i) => chip.textContent === CANDIDATES[i]),
    chips.map((c) => c.textContent).join(','));
  check('C7 the column universe is named beside them',
    at(byClass(at(unanswered, 0), 'oe-candidates'), 0).textContent.includes('PREPARED'));
  check('C8 refusals with no field still reach the screen',
    root.textContent.includes('bundle.vocabulary'));
}

// ── D. the counts bite: delete the rows and the numbers must move ─────────────────
{
  const empty = render({ ...PLAN, fields: [], unattached_refusals: [] });
  eq('D1 no rows -> no derived cards', inside(empty, 'oe-bucket--derived', 'oe-field').length, 0);
  eq('D2 no rows -> no grounds', inside(empty, 'oe-bucket--derived', 'oe-ground').length, 0);
  eq('D3 no rows -> no missing cards', inside(empty, 'oe-bucket--missing', 'oe-field').length, 0);
  // The headings must survive: a vanished section reads as "nothing to do", which is the
  // false green this round was asked to remove.
  eq('D4 the derived heading survives an empty bucket',
    byClass(empty, 'oe-bucket--derived').length, 1);
  check('D5 an empty bucket says 없음 rather than showing nothing',
    at(byClass(empty, 'oe-bucket--derived'), 0).textContent.includes('없음'));
  const onlyGround = {
    ...PLAN,
    fields: [{ ...PLAN.fields[0], ground: null }],
  };
  let threw = false;
  let grounds = -1;
  try {
    grounds = inside(render(onlyGround), 'oe-bucket--derived', 'oe-ground').length;
  } catch (_) { threw = true; }
  check('D6 a derived row without a ground renders no ground block (B2 would go red)',
    !threw && grounds === 0, `grounds=${grounds}`);
}

// ── E. a filled value is never a greyed box ───────────────────────────────────────
// Owner rule 2026-08-19: a derived field renders its value AND its ground AND can be
// acted on. A field nobody can act on is force, and force must not wear the costume of
// a choice. Falsified, not observed: the panel is searched for any input control at all.
{
  const root = render(PLAN);
  const panel = byClass(root, 'oe-authoring')[0] || element('div');
  const controls = walk(panel).filter(
    (node) => ['INPUT', 'SELECT', 'TEXTAREA'].includes(node.tagName));
  eq('E1 the authoring panel renders no input control to grey out', controls.length, 0);
  const disabled = walk(panel).filter((node) => node.attrs?.disabled !== undefined);
  eq('E2 and nothing in it is disabled', disabled.length, 0);

  const derivedRows = inside(root, 'oe-bucket--derived', 'oe-field');
  const acts = derivedRows.map((row) => byClass(row, 'oe-field-act'));
  check('E3 every derived row says what may be done about it',
    acts.every((list) => list.length === 1),
    acts.map((l) => l.length).join(','));
  check('E4 a forced row says it cannot be changed here',
    at(acts[0], 0).textContent.includes('강제'));
  check('E5 a default row says it can be overwritten',
    at(acts[1], 0).textContent.includes('덮어쓸 수 있음'));

  const jumps = byClass(panel, 'oe-jump');
  check('E6 the ground is reachable, so the real lever is one click away',
    jumps.length >= 2);
  check('E7 the jump targets the declaration the value came from',
    jumps.some((node) => node.dataset.value === 'profile|dt-job@1')
      && jumps.some((node) => node.dataset.value === 'entity|DTJob@1'),
    jumps.map((n) => n.dataset.value).join(','));
  check('E8 the blocked structural tier is counted on screen, not absorbed',
    byClass(panel, 'oe-note').length === 1
      && at(byClass(panel, 'oe-note'), 0).textContent.includes('1개'));
}

console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
