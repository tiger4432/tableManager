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
    // The map sets its indent through a custom property, so a stub with no `style` dies
    // there rather than failing an assertion.
    style: { setProperty() {} },
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
// `createDocumentFragment` joined the stub when block G started rendering the 원본 JSON
// tab: `keyValue` builds a fragment, and a fragment that only has to be appended into
// a parent is an element with no tag as far as these assertions can tell.
globalThis.document = { createElement: element, createDocumentFragment: () => element('#fragment') };
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
// 🔴 THE COLUMNS THE READ BRINGS IN ANYWAY, AS THE SERVER SENDS THEM. `locked` is a
// SUBSET of `candidates` and arrives on the row; the client draws it and never computes
// it, so this fixture is the only place the membership is stated. Two of the four, so the
// block below can tell a locked toggle from a free one -- one of each would let a probe
// that finds "some pressed chip" pass while looking at the wrong kind.
const LOCKED = ['dt_job', 'event_time'];
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
    { id: 'sources', label: '소스', sections: ['sources'], declared: 2,
      status: 'blocked', derived: 2, missing: 1, unanswered: 1, answered: 0 },
    // 🔴 WAS 「팩」 UNTIL 2026-08-21. `STEPS` lost that band when the `packs` section went,
    // so a fixture naming it would be scoring a payload the server can no longer send.
    // The block below only needs a step with nothing declared; `vocabulary` is a real one.
    { id: 'vocabulary', label: '낱말', sections: ['vocabulary'], declared: 0,
      status: 'empty', derived: 0, missing: 0, unanswered: 0, answered: 0 },
  ],
  fields: [
    // 🔴 THE FIRST OF THESE TWO USED TO BE `profile.packs`, WHICH THE SERVER CANNOT EMIT
    // ANY MORE: 2026-08-21 removed that declaration rather than deriving it. The pair the
    // E-block needs is one FORCED row and one DEFAULT row grounded on DIFFERENT
    // declarations, and both replacements are rules `authoring_plan` still produces --
    // `entity_binding_keys_from_entity` (measured `grammar_requires_it` on the operator's
    // own config) and `mapper_inputs_from_profile_bindings`.
    field({
      path: 'bundle.sources.dt_job.bind.mappings[0].bind.subject.keys',
      label: '식별키 이름',
      step: 'sources', state: 'derived', tier: 'structural', value: ['dt_job'],
      declared: ['dt_job'], has_declared: true,
      disposition: 'grammar_requires_it',
      ground: {
        rule: 'entity_binding_keys_from_entity', text: '채움: DTJob@1의 식별키',
        from_paths: ['bundle.entities.DTJob@1.keys'], from_keys: ['entity|DTJob@1'],
        from_value: ['dt_job'],
      },
    }),
    // 🔴 THE ROW CARRIES `candidates` AND `locked` SINCE 2026-08-22, and the fixture was
    // changed to the new contract rather than left describing the old one. The square is a
    // PICKER now (owner: 「차라리 컬럼 선택 하는거로 하고, 저 디폴트 컬럼들은 클릭 불가능한
    // 클릭되어 있는 버튼으로 둬」), so the row has to carry the set to pick from and the
    // subset that is not a choice. `value` is the server's default as `a13eeed4` computes
    // it: every candidate EXCEPT the locked ones, because a locked column is already coming
    // and `input_columns` means "on top of the read".
    field({
      path: 'bundle.sources.dt_job.map.input_columns', label: '매퍼 input_columns',
      step: 'sources', state: 'derived', tier: 'derivation',
      value: CANDIDATES.filter((column) => !LOCKED.includes(column)),
      candidates: CANDIDATES, locked: LOCKED,
      declared: ['lot'], has_declared: true, conflicts: true,
      comparison: 'superset', disposition: 'default_overridable',
      ground: {
        rule: 'mapper_inputs_from_profile_bindings',
        text: '채움: 소스 dt_job의 프로필이 바인딩한 컬럼 3개',
        from_paths: ['bundle.sources.dt_job.bind.mappings[0].bind.subject.keys.dt_job.column'],
        from_keys: ['source_plan|dt_job'],
        from_value: ['dt_index', 'dt_job', 'event_time'],
      },
    }),
    // 🔴 A MAP KEY, NOT AN INDEX, AND THE ROLE IS THE ONE THE PREDICATE FORCES.
    // `mappings` became a map keyed by sentence on 2026-08-21 and `packs` went the same
    // day, so `mappings[1].bind.count` named two shapes that no longer exist. The role a
    // value-object predicate opens is `value`; nothing declares it claim-side any more.
    // 🔴 THE MAP'S OWN ROW, WHICH THE SERVER EMITS FOR EVERY `bind`. Added 2026-08-22:
    // the fixture had none, so it could not tell "the plan NAMES this member" from "some
    // descendant row sits under this path" -- and that is exactly the distinction the map
    // now turns on, after a removed sentence kept being redrawn from the saved
    // declaration. A forced member set is a `shape` row whose value IS the names.
    field({
      path: 'bundle.sources.dt_job.bind.mappings.counted.bind', label: '결선할 역할',
      step: 'sources', state: 'derived', tier: 'derivation',
      value: ['occurred_at', 'subject', 'value'], disposition: 'shape',
      ground: {
        rule: 'bind_rows_from_predicate',
        text: '채움: 낱말 has_netdie@1이 요구하는 역할 3개',
        from_paths: ['bundle.vocabulary.has_netdie@1'],
        from_value: ['occurred_at', 'subject', 'value'],
      },
    }),
    field({
      path: 'bundle.sources.dt_job.bind.mappings.counted.bind.value', label: '역할 value',
      step: 'sources', state: 'missing', tier: 'constrained_input',
      candidates: ['column', 'constant'],
      refusals: [{ code: 'missing_required_role',
        path: 'bundle.sources.dt_job.bind.mappings.counted.bind.value',
        message: "predicate 'has_netdie@1' requires role 'value'" }],
    }),
    field({
      path: 'bundle.sources.dt_job.read.identity', label: 'identity', step: 'sources',
      state: 'unanswered', candidates: CANDIDATES, universe: 'PREPARED',
      universe_note: '물리 표 + 준비기 산출 컬럼',
    }),
    field({ path: 'bundle.entities.DTJob@1.keys', label: '식별키', step: 'entities',
      state: 'answered', value: ['dt_job'] }),
  ],
  counts: { derived: 2, missing: 1, unanswered: 1, answered: 1 },
  force_summary: { grammar_requires_it: 1, default_overridable: 1 },
  refusals: [],
  // 🔴 UNDER THE DECLARATION ON SCREEN, because that is what the map can answer for.
  // This is the shape the lead measured before deleting the 「필드에 붙지 않은 거절」 block:
  // a refusal with no plan row, whose path still lands on a map row. It was
  // `bundle.vocabulary` while a bucket printed refusals verbatim from anywhere.
  unattached_refusals: [
    { code: 'missing_field', path: 'bundle.sources.dt_job.read.occurred_at.timezone',
      message: 'field is required' },
  ],
};

// The smallest skeleton that is a real one: a section of name-keyed declarations, a
// name-keyed map of sentences inside it, and a name-keyed map of roles inside that. The
// last is what the binding template has to fill, and a map is the only shape that could
// not draw a member the document has not got.
const SKELETON = {
  defs: {
    binding: { kind: 'record', fields: [
      { key: 'kind', required: true, label: '결선 종류', node: { kind: 'leaf', hint: 'free' } },
    ] },
  },
  root: { kind: 'record', fields: [
    { key: 'sources', required: true, node: { kind: 'map', keyed_by: 'name', member: '소스',
      of: { kind: 'record', fields: [
        { key: 'read', required: true, label: '읽기', node: { kind: 'record', fields: [
          { key: 'occurred_at', required: true, label: '시각', node: { kind: 'record',
            fields: [
              { key: 'column', required: true, label: '컬럼',
                node: { kind: 'leaf', hint: 'free' } },
            ] } },
        ] } },
        // The mapper clause, exactly as `ledger_skeleton.json` declares it: an index-keyed
        // map of column names. It is here because the picker only exists on the TREE --
        // the buckets call `editableFor` without a node, and the node is what says this
        // absent value is a list. A fixture with no `map` could not reach the control at
        // all, which is how the two `input_columns` squares went unscored until now.
        { key: 'map', required: true, label: '매퍼', node: { kind: 'record', fields: [
          { key: 'input_columns', required: true, label: '매퍼 input_columns',
            node: { kind: 'map', keyed_by: 'index', member: '컬럼',
                    of: { kind: 'leaf', hint: 'free' } } },
        ] } },
        { key: 'bind', required: true, label: '결선', node: { kind: 'record', fields: [
          { key: 'mappings', required: true, node: { kind: 'map', keyed_by: 'name',
            member: '문장', of: { kind: 'record', fields: [
              { key: 'predicate', required: true, label: '낱말',
                node: { kind: 'leaf', hint: 'ref', section: 'vocabulary' } },
              { key: 'bind', required: true, label: '역할 바인딩',
                node: { kind: 'map', keyed_by: 'name', member: '역할',
                        of: { use: 'binding' } } },
            ] } } },
        ] } },
      ] } } },
  ] },
};

const SCHEMA = {
  skeleton: SKELETON,
  authorable_kinds: [{ id: 'source_plan', section: 'sources', versioned: false }],
};

// What the file holds for `dt_job`: the sentence names its predicate and has bound ONE of
// the roles that predicate forces. `value` is missing, which is the whole point.
const DOCUMENT = {
  read: { occurred_at: { column: 'event_time' } },
  bind: { mappings: { counted: {
    predicate: 'has_netdie@1',
    bind: { subject: { kind: 'entity' } },
  } } },
};

const stateWith = (plan) => ({
  ...initialExplorerState,
  authoring: plan,
  detailTab: 'authoring',
  activeSnapshot: { snapshot_hash: 'abc12345', valid: true },
  viewContext: { mode: 'active', context_token: 'active:abc12345' },
  // 🔴 A SOURCE PLAN, NOT ITS PROFILE, SINCE 2026-08-20. The profile became a clause of
  // the source and left `authorable_kinds`, so it has no section of its own to light up in
  // the step bar -- exactly as `preparer` and `mapper` already had none. The step bar
  // answers for the DECLARATION, and the declaration that holds these rows is the source.
  selection: {
    key: 'source_plan|dt_job', canonical_id: 'dt_job', kind: 'source_plan',
    config_path: 'bundle.sources.dt_job', compile_status: 'valid',
    config_file: 'ledger_config.json',
    raw: DOCUMENT,
  },
  authoringSchema: SCHEMA,
  navigation: { back: [], forward: [] },
});

// 🔴 THE ASSERTIONS BELOW SCORE AN EXPANDED ROW, so they must expand it.
//
// On 2026-08-19 the lead PM ruled the fold: a derived or single-candidate row renders as
// ONE LINE by default -- value, why it folded, and its ground -- and its disposition,
// candidate chips and lever-jump appear when it is opened. Everything from B and E below
// was written before that and describes the OPENED row, which is still exactly right; it
// just is not what the screen shows first.
//
// So `render` opens every row by hand, and `renderFolded` is the new helper that scores
// the default. Passing every path is deliberate: an assertion that quietly stopped finding
// its row would otherwise read as "the fold is working".
//
// `expandedFields` records the DECISION per path (`true` open, `false` shut, absent means
// the rule decides) rather than a set of paths that inverted the rule -- an inversion drifts
// into its own opposite the moment the rule's answer moves, which is what folded a subtree
// shut on save. "Opened by hand" is now spelled as the true it always meant.
const render = (plan) => {
  const root = element('div');
  renderOntologyExplorer(root, {
    ...stateWith(plan),
    expandedFields: Object.fromEntries(
      (plan.fields || []).map((row) => [row.path, true])),
  });
  return root;
};

const renderFolded = (plan) => {
  const root = element('div');
  renderOntologyExplorer(root, stateWith(plan));
  return root;
};

// 🔴 A DRAFT IS WHAT MAKES THE TREE EXIST, so the block that scores the tree opens one and
// the blocks that score the BUCKETS do not. `renderAuthoring` draws the form only when a
// draft is open, and every row it draws leaves the buckets -- which is exactly the
// difference the C block below is about, and exactly why E1 ("no greyed boxes") still
// renders without one.
const renderDraft = (plan) => {
  const root = element('div');
  renderOntologyExplorer(root, {
    ...stateWith(plan),
    draft: { target_kind: 'source_plan', target_id: 'dt_job' },
    editorText: JSON.stringify(DOCUMENT),
    expandedFields: Object.fromEntries(
      (plan.fields || []).map((row) => [row.path, true])),
  });
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
  check('A5 an empty step says so', at(steps, 2).textContent.includes('None defined'));
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
  eq('B1 the derived bucket holds every derived row', derivedRows.length, 3);  // was 2
  eq('B2 every derived row carries a ground block',
    derivedGrounds.length, derivedRows.length);
  check('B3 the ground states its sentence',
    at(derivedGrounds, 0).textContent.includes('채움: DTJob@1의 식별키'));
  check('B4 the ground names the declaration it came from',
    at(derivedGrounds, 0).textContent.includes('bundle.entities.DTJob@1.keys'));
  check('B5 the ground is inside the field card, not a separate tooltip layer',
    byClass(at(derivedRows, 0), 'oe-ground').length === 1);
  check('B6 the derived value itself is rendered',
    at(derivedRows, 0).textContent.includes('dt_job'));
  check('B7 a derived row that disagrees with the file says so',
    byClass(at(derivedRows, 1), 'oe-field-conflict').length === 1
      && at(byClass(at(derivedRows, 1), 'oe-field-conflict'), 0).textContent.includes('lot'));
  check('B8 derived rows offer no candidate picker (they are not questions)',
    byClass(at(derivedRows, 0), 'oe-candidates').length === 0);
}

// ── C. missing and unanswered are named, with the server's own codes ──────────────
//
// 🔴 THE CONTRACT CHANGED ON 2026-08-21 AND C1-C3 AND C8 MOVED WITH IT. Two
// `oe-bucket--missing` blocks used to sit below the tree -- 「빠짐 · N」 and 「필드에 붙지
// 않은 거절 · N」 -- and the owner asked for both to be deleted. The lead measured what
// covers them: `attentionPaths` marks every remaining/refused path `is-left` on the
// right-hand map, and all six unattached refusals in the live config had such a row. So
// the surfaces are the TREE ROW (which box) and the MAP (what is left), and these
// assertions score those instead of the bucket. They were not weakened -- C1 now refuses
// the bucket's RETURN, which nothing scored before.
{
  const root = renderDraft(PLAN);
  eq('C1 no missing bucket exists at all',
    byClass(root, 'oe-bucket--missing').length, 0);
  const refused = byClass(root, 'oe-node-row').filter(
    (row) => row._classes.includes('is-refused'));
  eq('C2 the refused role is a row in the tree, not a card below it', refused.length, 1);
  // 🔴 THE CODE MOVED OFF THE SENTENCE ON 2026-08-21, AND THIS MOVED WITH IT rather than
  // being deleted. Lead's ruling for the source form: a refusal beside a box gets human
  // wording and the raw identifier stays in the log -- `invalid_type` printed in bold is
  // the validator quoting itself at an operator who cannot act on it. So the refusal line
  // now carries the MESSAGE as its text and the code as `data-code`, and both halves are
  // scored: the code is still reachable (a bug report needs it) and the sentence a person
  // reads is the message. Dropping the code entirely would have been the weakening.
  eq('C3 the stable code is still carried, on the element',
    at(byClass(root, 'oe-field-refusal'), 0).dataset.code, 'missing_required_role');
  check('C3b and the sentence on screen is the message, not the code',
    !at(byClass(root, 'oe-field-refusal'), 0).textContent.includes('missing_required_role'));
  const unanswered = inside(render(PLAN), 'oe-bucket--unanswered', 'oe-field');
  eq('C4 the unanswered bucket holds the free question', unanswered.length, 1);
  const chips = byClass(at(byClass(at(unanswered, 0), 'oe-candidates'), 0), 'oe-chip');
  eq('C5 one chip per server candidate, no more', chips.length, CANDIDATES.length);
  check('C6 the chips ARE the server list, element for element',
    chips.every((chip, i) => chip.textContent === CANDIDATES[i]),
    chips.map((c) => c.textContent).join(','));
  check('C7 the column universe is named beside them',
    at(byClass(at(unanswered, 0), 'oe-candidates'), 0).textContent.includes('PREPARED'));
  const left = byClass(root, 'oe-map-row').filter(
    (row) => row._classes.includes('is-left'));
  check('C8 a refusal with no field still reaches the screen, on the map',
    left.some((row) => String(row.title || '').startsWith('read.occurred_at')),
    left.map((row) => row.title).join(','));
}

// ── G. the binding template: choosing a predicate lays the slots out ──────────────
//
// 🔴 THE HALF OF `packs` REMOVAL THAT IS NOT A DELETION (owner, 2026-08-21: 「packs 제거 후
// 소스에는 문장id - vocab - vocab 정의 따른 하위 항목별 binding 템플릿 이런 형태가 되어야
// 함」). A record always drew its declared fields, so an unfilled one was a visible empty
// box; a name-keyed MAP drew only what the document held, so a Role the grammar requires
// and the file has not got was simply not on the screen. Dropping `claims` without this
// would have MOVED the burden onto a person -- they would have to know the word `value`
// from outside the form -- which is worse than what was there before.
{
  const root = renderDraft(PLAN);
  const roleRows = byClass(root, 'oe-node').filter(
    (node) => String(node.dataset.path || '')
      .startsWith('bind.mappings.counted.bind.'));
  const paths = roleRows.map((node) => node.dataset.path);
  check('G1 the bound role is drawn',
    paths.includes('bind.mappings.counted.bind.subject'), paths.join(','));
  check('G2 the role the predicate forces is drawn though the document lacks it',
    paths.includes('bind.mappings.counted.bind.value'), paths.join(','));
  const slots = paths.filter((path) => path.split('.').length === 5);
  check('G3 no slot is invented: only what the document holds or the plan names',
    slots.length === 3, slots.join(','));  // was 2: the predicate opens three roles
}

// ── H. input_columns is a picker; the columns the read already brings are inert ────
//
// Owner, 2026-08-21: 「차라리 컬럼 선택 하는거로 하고, 저 디폴트 컬럼들은 클릭 불가능한
// 「클릭되어 있는」 버튼으로 둬」 -- and minutes later, 「그러면 그냥 디폴트 전체 입력해도
// 되지?」. The two halves are ONE landing: an everything-default makes a source sensitive to
// columns it does not use, and the only thing that makes that safe is being able to SEE
// which of the pressed ones you may turn off. So the assertions below score the difference
// between the two kinds of pressed, not the pressing.
//
// 🔴 EVERY COUNT IS TAKEN INSIDE THE ROW'S OWN `oe-node`. The legend, the other rows and
// the map reuse `oe-chip` and `oe-pick`, and a panel-wide count has already passed here
// while the rows it was about were empty.
{
  const root = renderDraft(PLAN);
  const rows = byClass(root, 'oe-node').filter(
    (node) => node.dataset.path === 'map.input_columns');
  eq('H1 the mapper input_columns square is drawn exactly once', rows.length, 1);
  const picks = byClass(at(rows, 0), 'oe-picks');
  const chips = picks.length ? byClass(at(picks, 0), 'oe-pick') : [];
  eq('H2 one toggle per server candidate, inside that row', chips.length, CANDIDATES.length);
  check('H3 the toggles ARE the server list, element for element',
    chips.every((chip, i) => chip.textContent === CANDIDATES[i]),
    chips.map((c) => c.textContent).join(','));
  const held = chips.filter((chip) => chip.dataset.locked === 'true');
  check('H4 the locked toggles are the server list, element for element',
    held.map((chip) => chip.textContent).join(',') === LOCKED.join(','),
    held.map((c) => c.textContent).join(','));
  check('H5 a locked toggle is pressed',
    held.length === LOCKED.length
      && held.every((chip) => chip.getAttribute('aria-pressed') === 'true'));
  // 🔴 THE ONE THAT IS ACTUALLY MINE. With everything pressed by default, "the toggles are
  // pressed" is true even of code that does nothing, so the probe has to bite on the
  // difference: a locked one carries NOTHING for the click delegate or the Enter/Space
  // handler to find (`[data-action]` / `button[data-action]`), while a free one carries the
  // action and the payload.
  check('H6 a locked toggle cannot be pressed by mouse, by key, or by a dispatched click',
    held.every((chip) => chip.dataset.action === undefined && chip.tagName !== 'BUTTON'),
    held.map((c) => `${c.tagName}:${c.dataset.action}`).join(','));
  const free = chips.filter((chip) => chip.dataset.locked === undefined);
  check('H7 every other candidate IS a toggle that presses',
    free.length === CANDIDATES.length - LOCKED.length
      && free.every((chip) => chip.tagName === 'BUTTON'
        && chip.dataset.action === 'pick-candidate'),
    free.map((c) => `${c.tagName}:${c.dataset.action}`).join(','));
  check('H8 and every other candidate starts pressed (the server default is everything)',
    free.every((chip) => chip.getAttribute('aria-pressed') === 'true'),
    free.map((c) => c.getAttribute('aria-pressed')).join(','));
  // 🔴 THE PAYLOAD, NOT THE PAINT. The chip carries the WHOLE next value and the document
  // gets what it says, so a chip that looks right and writes a locked name is still the
  // defect. Red the moment a locked candidate stops being recognised as one: it would join
  // `free`, and its payload is its own name appended.
  const payloads = free.map((chip) => JSON.parse(chip.dataset.pick));
  check('H9 no toggle ever puts a locked column into the document',
    payloads.every((list) => LOCKED.every((column) => !list.includes(column))),
    JSON.stringify(payloads));
  check('H10 pressing a pressed toggle takes exactly that column back out',
    payloads.every((list, index) => {
      const want = free.filter((_, other) => other !== index)
        .map((chip) => chip.textContent);
      return JSON.stringify(list) === JSON.stringify(want);
    }), JSON.stringify(payloads));
  // 🔴 A PICKER THE PERSON CANNOT SEE IS A PICKER THAT IS NOT THERE. `renderDraft` opens
  // every row by hand, so everything above would pass on a row that folds shut by default
  // -- and `foldDecision` folds `answered`, `unanswered` and single-candidate rows before
  // any control is built. This renders the SAME plan with no hand-expansion at all.
  const plain = element('div');
  renderOntologyExplorer(plain, {
    ...stateWith(PLAN),
    draft: { target_kind: 'source_plan', target_id: 'dt_job' },
    editorText: JSON.stringify(DOCUMENT),
  });
  const shut = byClass(plain, 'oe-node').filter(
    (node) => node.dataset.path === 'map.input_columns');
  const shutChips = byClass(at(shut, 0), 'oe-pick');
  eq('H11 the square shows its toggles with nothing expanded by hand',
    shutChips.length, CANDIDATES.length);

  // 🔴 A LOCKED COLUMN THE FILE ALREADY DECLARES IS CARRIED, NOT STRIPPED, and the reason
  // is the validator rather than a preference: `setup_bundle` refuses `invalid_mapper` --
  // "Profile column 'x' at … is missing" -- for every column a binding names that
  // `map.input_columns` does not declare, and the binding columns include the identity.
  // Measured on the live file 2026-08-22: `dt_job.map` declares `dt_job`,
  // `lot_event.map` declares `event_time` and `event_group_key`, all locked. A screen that
  // took them back out on the next press would refuse the owner's own config as the side
  // effect of an unrelated click.
  const declaring = element('div');
  renderOntologyExplorer(declaring, {
    ...stateWith(PLAN),
    draft: { target_kind: 'source_plan', target_id: 'dt_job' },
    editorText: JSON.stringify({ ...DOCUMENT, map: { input_columns: ['dt_index', 'dt_job'] } }),
    expandedFields: Object.fromEntries(
      (PLAN.fields || []).map((row) => [row.path, true])),
  });
  const held2 = byClass(declaring, 'oe-node').filter(
    (node) => node.dataset.path === 'map.input_columns');
  const chips2 = byClass(at(held2, 0), 'oe-pick');
  const free2 = chips2.filter((chip) => chip.dataset.locked === undefined);
  check('H12 a locked column the document declares survives a press on another toggle',
    free2.length === CANDIDATES.length - LOCKED.length
      && free2.every((chip) => JSON.parse(chip.dataset.pick).includes('dt_job')),
    free2.map((chip) => chip.dataset.pick).join(' | '));
  check('H13 and it is still drawn as locked, not as a toggle the person may switch off',
    chips2.filter((chip) => chip.dataset.locked === 'true')
      .map((chip) => chip.textContent).join(',') === LOCKED.join(','),
    chips2.map((chip) => `${chip.textContent}:${chip.dataset.locked}`).join(','));

  // 🔴 NOTHING LOCKED IS NOT NOTHING TO DRAW. A source whose `read` says nothing yet locks
  // no column at all, and the server sends `[]` rather than omitting the key. That has to
  // be the picker it always was -- a row that answers an empty list with "no control" is
  // the defect this panel paid a round for once already, an absence nobody can tell from
  // an emptiness.
  const none = element('div');
  renderOntologyExplorer(none, {
    ...stateWith({
      ...PLAN,
      fields: PLAN.fields.map((row) => (
        row.path === 'bundle.sources.dt_job.map.input_columns'
          ? { ...row, locked: [] } : row)),
    }),
    draft: { target_kind: 'source_plan', target_id: 'dt_job' },
    editorText: JSON.stringify(DOCUMENT),
    expandedFields: Object.fromEntries(
      (PLAN.fields || []).map((row) => [row.path, true])),
  });
  const open = byClass(none, 'oe-node').filter(
    (node) => node.dataset.path === 'map.input_columns');
  const chips3 = byClass(at(open, 0), 'oe-pick');
  check('H14 an empty locked list still draws the whole picker, every chip pressable',
    chips3.length === CANDIDATES.length
      && chips3.every((chip) => chip.tagName === 'BUTTON'
        && chip.dataset.action === 'pick-candidate'
        && chip.dataset.locked === undefined),
    `${chips3.length} chips: ${chips3.map((c) => `${c.tagName}:${c.dataset.locked}`).join(',')}`);
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
  // Owner ruled the UI register on 2026-08-19: formal English nouns, never Korean verb
  // forms. The label moved from 없음 to `None defined`; the property it scores did not.
  check('D5 an empty bucket says None defined rather than showing nothing',
    at(byClass(empty, 'oe-bucket--derived'), 0).textContent.includes('None defined'));
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
    jumps.some((node) => node.dataset.value === 'source_plan|dt_job')
      && jumps.some((node) => node.dataset.value === 'entity|DTJob@1'),
    jumps.map((n) => n.dataset.value).join(','));
  check('E8 the blocked structural tier is counted on screen, not absorbed',
    byClass(panel, 'oe-note').length === 1
      && at(byClass(panel, 'oe-note'), 0).textContent.includes('1개'));
}

// ── F. the fold (lead PM ruling, 2026-08-19) ─────────────────────────────────────
//
// Folding by LENGTH would hide the handful of real human judgements, which are the longest
// rows -- so the fold is decided by DEGREES OF FREEDOM, and the precedence is what keeps
// it from contradicting the 「n 남음」 count:
//
//     remaining -> open · problem -> open · derived/forced -> fold · 1 option -> fold
{
  const folded = renderFolded(PLAN);
  const cards = byClass(folded, 'oe-field');
  const foldedCards = cards.filter((c) => c._classes.includes('is-folded'));

  check('F1 something folds and something does not -- otherwise this measures nothing',
    foldedCards.length > 0 && foldedCards.length < cards.length,
    `${foldedCards.length} folded of ${cards.length}`);

  // Every folded row states WHY. A fold whose reason is invisible reads as the screen
  // deciding for the operator, which is the thing the acceptance bar forbids.
  const whys = byClass(folded, 'oe-folded-why').map((n) => n.textContent).filter(Boolean);
  check('F2 every folded row says why it folded',
    whys.length === foldedCards.length, `${whys.length} reasons for ${foldedCards.length} folds`);
  check('F3 the reasons come from the ruled vocabulary',
    // `Set` became 「선언됨」 by the owner's 6b ruling (answered 접힘 → 「선언됨」 한 마디).
    // The set stays CLOSED -- that is what this checks; only a member was renamed, and it
    // is renamed here in the same commit as the code, not left to fail later as a mystery.
    whys.every((w) => ['파생됨', '강제', '단일 후보', '선언됨', '비움'].includes(w)), whys.join(','));

  // 🔴 `remaining` OUTRANKS THE FOLD. Otherwise the layer header says "3 남음" while one of
  // the three is folded out of sight, and an operator who notices believes neither number.
  const owed = (PLAN.fields || []).filter((row) => row.remaining);
  const foldedPaths = new Set(foldedCards.map(
    (c) => c.dataset?.key ? String(c.dataset.key).slice('field:'.length) : ''));
  check('F4 nothing counted as 남음 is ever folded away',
    owed.every((row) => !foldedPaths.has(row.path)),
    owed.filter((row) => foldedPaths.has(row.path)).map((row) => row.path).join(','));

  // A fold nobody can open is not a fold, it is a deletion.
  check('F5 every folded row is a control that opens it',
    foldedCards.every((card) =>
      byClass(card, 'oe-field-folded').some((n) => n.dataset?.action === 'toggle-field')));
}

  // --- G. R1: the server says a red run does not block, and says what would ----------
//
// 🔴 THE DEFECT THIS SCORES IS A MONTH LONG AND HAD NO ERROR. `activate` refuses on
//    exactly one thing and a red test run is not it -- but the screen could only show the
//    red, so declarations that were writable the whole time were never written.
//
// 🔴 EVERY CASE IS SCORED IN THREE, not two. The third is "the server did not say":
//    an older build sends neither key, and 「안 물어봤다」 must not draw as 「안 막는다」.
//    A two-state test passes against a view that treats absent as false.
{
  const RUN = { status: 'ok', rows_read: 12, molecules: 3, atoms: 9, sentences: [],
                refusal: null, relation: 'dt_job' };
  const draw = (run, blockers) => {
    const root = element('div');
    // `target_key` is what puts the EDITOR on screen (the view asks whether the
    // selection and the draft are the same declaration), and the controls live in it.
    const draft = { target_kind: 'source_plan', target_id: 'dt_job',
                    target_key: 'source_plan|dt_job' };
    if (blockers !== undefined) draft.activation_blockers = blockers;
    renderOntologyExplorer(root, {
      // the editor -- and so the Save control -- lives on the 원본 JSON tab
      ...stateWith(PLAN), detailTab: 'raw', draft, editorText: JSON.stringify(DOCUMENT),
      ...(run === undefined ? {} : { testRun: run }),
    });
    return root;
  };
  const noteText = (root) => byClass(root, 'oe-testrun-note').map((n) => n.textContent).join('|');

  // ① the test run's own line
  check('G1 a run that does not block says so',
    noteText(draw({ ...RUN, blocks_activation: false })).includes('저장 차단 아님'));
  check('G2 a run that DOES block says the opposite',
    noteText(draw({ ...RUN, blocks_activation: true })).includes('저장 차단')
    && !noteText(draw({ ...RUN, blocks_activation: true })).includes('아님'));
  // 🔴 THE THIRD STATE. Without this one, a view that read `!run.blocks_activation`
  //    would pass G1 and G2 and still lie to every operator on an older server.
  check('G3 a server that did not say draws NEITHER word',
    !noteText(draw(RUN)).includes('차단'), noteText(draw(RUN)));
  // and the red result itself is still on screen -- this round does not turn red green
  check('G4 the refusal is not hidden by any of that',
    byClass(draw({ ...RUN, status: 'refused', blocks_activation: false,
                   refusal: { message: 'x', code: 'y' } }), 'oe-testrun-refusal').length === 1);

  // ② what would refuse the save, beside Save
  const blockerText = (root) =>
    byClass(root, 'oe-editor-blockers').map((n) => n.textContent).join('|');
  check('G5 an empty list says nothing blocks',
    blockerText(draw(undefined, [])) === '막는 것 없음');
  check('G6 a blocker is named as the server named it',
    blockerText(draw(undefined, ['stale_draft'])) === 'stale_draft');
  check('G7 several are joined, still unranslated',
    blockerText(draw(undefined, ['stale_draft', 'conflict_draft']))
      === 'stale_draft · conflict_draft');
  // 🔴 THE THIRD STATE AGAIN, and the one that matters most here: an absent key is
  //    NOT an empty list. Drawing 「막는 것 없음」 for a server that never answered would
  //    be this screen asserting something it was not told.
  check('G8 an absent key draws nothing at all',
    byClass(draw(undefined, undefined), 'oe-editor-blockers').length === 0);
  // the control it sits beside still exists, and there is still only one of it
  check('G9 Save is still the one primary control',
    byClass(draw(undefined, []), 'oe-editor-action-primary').length === 1);
}

console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
