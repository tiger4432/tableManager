import { isDraftRevisionEditable } from './ontology_explorer_store.js';
import { commitTree } from './dom_patch.js';

const KIND_LABELS = Object.freeze({
  source_plan: 'Source plans', profile: 'Profiles', mapping: 'Mappings', binding: 'Bindings', pack: 'Packs',
  claim: 'Claims', predicate: 'Vocabulary', entity: 'Entities',
  preparer: 'Preparers', mapper: 'Mappers', verified_join: 'Verified joins', table: 'Tables',
});

const h = (tag, cls, text) => {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = String(text);
  return el;
};

const button = (text, action, value, cls = '') => {
  const el = h('button', cls, text);
  el.type = 'button';
  el.dataset.action = action;
  if (value !== undefined) el.dataset.value = value;
  return el;
};

// The one place the panel reaches the screen. It used to be `replaceChildren`, which
// threw away the operator's scroll, focus, expand state and half-typed text on every
// state change -- see `dom_patch.js` for the owner report that named it. Every render
// function above still builds a fresh detached tree; only the commit changed.
function replace(root, child) {
  commitTree(root, child);
}

function nodeMap(state) {
  return new Map([...state.items, ...state.nodes].map((node) => [node.key, node]));
}

function addPopover(target, node) {
  if (!node) return target;
  target.classList.add('oe-has-popover');
  const popover = h('span', 'oe-popover');
  popover.setAttribute('role', 'tooltip');
  popover.append(
    h('strong', '', `${node.kind} · ${node.canonical_id}`),
    h('span', '', node.description || `${node.kind} 선언`),
    h('code', '', node.config_path),
  );
  target.append(popover);
  return target;
}

// The naming row. Free text HERE is correct and is the one place it is: the operator is
// COINING a name that nothing else in the file has yet, so there is no set to pick from.
// Every LATER use of that name is a dropdown over what was coined.
function renderNewDeclaration(state, kind) {
  const box = h('div', 'oe-new-declaration');
  box.dataset.key = `new:${kind}`;
  const label = h('label', 'oe-new-label');
  label.append(h('span', 'oe-new-caption', `New ${KIND_LABELS[kind] || kind}`));
  const input = h('input', 'oe-new-id');
  input.type = 'text';
  input.dataset.action = 'new-declaration-id';
  input.value = state.newDeclaration?.id || '';
  input.placeholder = 'id · e.g. dt-job@1';
  input.setAttribute('aria-label', 'New declaration id');
  label.append(input);
  box.append(label);
  const actions = h('div', 'oe-new-actions');
  const make = button('Create', 'create-declaration', kind, 'oe-new-make');
  make.disabled = !(state.newDeclaration?.id || '').trim();
  actions.append(make, button('Cancel', 'cancel-declaration', kind, 'oe-new-cancel'));
  box.append(actions);
  if (state.newDeclaration?.error) {
    box.append(h('div', 'oe-error', state.newDeclaration.error));
  }
  return box;
}

function renderTree(state) {
  const nav = h('nav', 'oe-tree');
  nav.setAttribute('aria-label', '온톨로지 구성 트리');
  nav.append(h('div', 'oe-tree-title', `구성 요소 · ${state.total}개`));
  const groups = new Map();
  for (const item of state.items) {
    if (!groups.has(item.kind)) groups.set(item.kind, []);
    groups.get(item.kind).push(item);
  }
  // 🔴 EVERY AUTHORABLE KIND GETS A GROUP, EVEN AN EMPTY ONE. The tree used to render only
  // kinds that already had members, so an empty section had no node -- and therefore no
  // way to create its FIRST member. "Declare a pack" was impossible until a pack existed.
  // The list comes from the server (`authorable_kinds`, read off the same map that decides
  // what may be deleted), so the screen never offers to create what it could not remove.
  //
  // Only when nothing is being searched: during a search the tree answers the query, and
  // padding it with empty sections would bury the matches.
  const authorable = (state.authoringSchema?.authorable_kinds || []).map((row) => row.id);
  const ordered = state.query.trim()
    ? [...groups.keys()]
    : [...new Set([...authorable, ...groups.keys()])];
  for (const kind of ordered) {
    const items = groups.get(kind) || [];
    const group = h('section', 'oe-tree-group');
    group.dataset.key = `group:${kind}`;
    const heading = h('div', 'oe-tree-heading');
    heading.append(h('span', 'oe-tree-heading-text', KIND_LABELS[kind] || kind));
    if (authorable.includes(kind)) {
      const add = button('+ New', 'new-declaration', kind, 'oe-tree-add');
      add.setAttribute('aria-label', `New ${KIND_LABELS[kind] || kind}`);
      heading.append(add);
    }
    group.append(heading);
    if (state.newDeclaration?.kind === kind) {
      group.append(renderNewDeclaration(state, kind));
    }
    for (const item of items) {
      const row = button(item.canonical_id, 'select', item.key, 'oe-tree-item');
      row.dataset.direct = 'true';
      row.setAttribute('aria-current', String(item.key === state.selection?.key));
      row.append(h('small', 'oe-change-label', item.change_status));
      addPopover(row, item);
      group.append(row);
    }
    // An empty section SAYS SO rather than rendering as a bare heading, which reads as a
    // broken screen. Reaching a layer before its members exist is normal -- the layers are
    // declared in order -- so the sentence names the next move instead of an error.
    if (!items.length && state.newDeclaration?.kind !== kind) {
      group.append(h('div', 'oe-tree-none', 'None defined'));
    }
    nav.append(group);
  }
  if (state.query.trim() && !state.items.length) {
    nav.append(h('div', 'oe-empty', '일치하는 정의가 없습니다.'));
  }
  return nav;
}

function renderPaths(state) {
  const area = h('section', 'oe-flow-area');
  const heading = h('div', 'oe-section-heading');
  const mode = state.viewContext?.mode === 'draft_preview'
    ? `DRAFT PREVIEW · r${state.draft?.revision} · ${state.viewContext.preview_snapshot_hash?.slice(0, 8)}`
    : `ACTIVE · ${state.activeSnapshot?.snapshot_hash?.slice(0, 8)}`;
  heading.append(h('h2', '', 'Reference Flow'), h('span', '', mode));
  area.append(heading);
  const nodes = nodeMap(state);
  const current = state.currentPath || {
    path_id: 'root', node_keys: [state.selection.key], edge_ids: [],
  };
  const alternatives = state.paths.filter((path) => path.path_id !== current.path_id);
  const paths = [current, ...alternatives];
  const edgeMap = new Map([...state.outbound, ...state.usedBy].map((edge) => [edge.edge_id, edge]));
  paths.forEach((path, pathIndex) => {
    const lane = h('div', 'oe-flow');
    lane.dataset.pathId = path.path_id;
    lane.dataset.current = String(pathIndex === 0);
    lane.append(h('span', 'oe-flow-label', pathIndex === 0 ? '현재 경로' : `경로 후보 ${pathIndex}`));
    path.node_keys.forEach((key, index) => {
      const node = nodes.get(key);
      const card = button('', 'select', key, 'oe-flow-node');
      card.dataset.pathId = path.path_id;
      if (index > 0) card.dataset.edgeId = path.edge_ids[index - 1] || '';
      card.setAttribute('aria-pressed', String(key === state.selection?.key));
      card.append(h('div', 'oe-node-kind', node?.kind || 'unknown'));
      card.append(h('div', 'oe-node-name', node?.canonical_id || key));
      card.append(h('div', 'oe-node-state', `${node?.change_status || 'active'} · ${node?.compile_status || 'unresolved'}`));
      addPopover(card, node);
      lane.append(card);
      if (index < path.node_keys.length - 1) {
        const edge = edgeMap.get(path.edge_ids[index]);
        const arrow = h('div', 'oe-arrow', '→');
        arrow.append(h('small', '', `${edge?.status || 'resolved'} · ${edge?.change_status || 'active'}`));
        lane.append(arrow);
      }
    });
    area.append(lane);
  });
  return area;
}

function renderBreadcrumb(state) {
  const trail = h('div', 'oe-breadcrumb');
  trail.setAttribute('aria-label', '탐색 경로');
  const nodes = nodeMap(state);
  const path = state.currentPath?.node_keys || [state.selection.key];
  path.forEach((key, index) => {
    const node = nodes.get(key);
    const crumb = button(node?.canonical_id || key, 'select', key, 'oe-crumb-button');
    crumb.dataset.pathId = state.currentPath?.path_id || 'root';
    if (index > 0) crumb.dataset.edgeId = state.currentPath?.edge_ids[index - 1] || '';
    if (key === state.selection.key) crumb.setAttribute('aria-current', 'page');
    trail.append(crumb);
    if (index < path.length - 1) trail.append(h('span', 'oe-crumb-separator', '›'));
  });
  if (state.paths.length > 1) {
    trail.append(h('span', 'oe-path-count', `외 ${state.paths.length - 1}개 경로`));
  }
  return trail;
}

function keyValue(label, value) {
  const frag = document.createDocumentFragment();
  frag.append(h('div', 'oe-label', label));
  frag.append(h('div', 'oe-value', value ?? '—'));
  return frag;
}

function renderDefinition(state) {
  const grid = h('div', 'oe-signature');
  const selected = state.selection;
  grid.append(
    keyValue('종류', selected.kind),
    keyValue('정본 ID', selected.canonical_id),
    keyValue('Version', selected.version ?? 'None'),
    keyValue('설정 파일', selected.config_file),
    keyValue('정확한 위치', selected.json_pointer),
    keyValue('정의 해시', selected.definition_hash),
    keyValue('변경 상태', selected.change_status),
  );
  const code = h('pre', 'oe-code');
  code.append(h('code', '', JSON.stringify(selected.compiled, null, 2)));
  const wrap = h('div', 'oe-definition');
  wrap.append(grid, code);
  return wrap;
}

function renderUsage(state) {
  const wrap = h('div', 'oe-usage-list');
  const nodes = nodeMap(state);
  const rows = [...state.usedBy, ...state.outbound];
  for (const edge of rows) {
    const otherKey = edge.from_key === state.selection.key ? edge.to_key : edge.from_key;
    const node = nodes.get(otherKey);
    const row = button(node?.canonical_id || edge.target_id, 'select', otherKey, 'oe-usage');
    row.dataset.edgeId = edge.edge_id;
    row.disabled = !otherKey;
    row.append(h('small', '', `${edge.reference_kind} · ${edge.status} · ${edge.json_pointer}`));
    addPopover(row, node);
    wrap.append(row);
  }
  if (!rows.length) wrap.append(h('div', 'oe-empty', '직접 참조가 없습니다.'));
  return wrap;
}

function renderRaw(state) {
  if (state.draft && state.selection.key === state.draft.target_key) {
    const editor = h('div', 'oe-editor');
    const context = h('div', 'oe-editor-context');
    context.append(keyValue('초안 상태', state.draft.lifecycle_status));
    context.append(keyValue('Revision', state.draft.revision));
    context.append(keyValue('기준 snapshot', state.draft.base_snapshot_hash));
    const label = h('label', 'oe-label', 'Working draft JSON');
    const textarea = h('textarea', 'oe-editor-textarea');
    textarea.value = state.editorText;
    textarea.spellcheck = false;
    textarea.readOnly = !isDraftRevisionEditable(state.draft);
    if (!textarea.readOnly) textarea.dataset.action = 'edit-raw';
    label.append(textarea);
    const validation = h('div', 'oe-editor-validation');
    validation.dataset.valid = String(Boolean(state.draft.preview_valid));
    const errors = state.draft.validation_errors || [];
    validation.textContent = errors.length
      ? errors.map((e) => `[${e.reference_status || e.code}] ${e.json_pointer || e.path}: ${e.message}`).join('\n')
      : (state.draft.preview_valid ? '✓ 동일 compiler로 검증된 초안입니다.' : '저장하면 검증합니다.');
    const controls = h('div', 'oe-editor-controls');
    controls.append(button('초안 폐기', 'discard-draft', '', 'oe-editor-action'));
    if (state.draft.lifecycle_status === 'review_requested') {
      controls.append(button('새 revision 편집', 'revise-draft', '', 'oe-editor-action'));
    } else {
      controls.append(
        button('저장·검증', 'save-draft', '', 'oe-editor-action'),
        button('검토 요청', 'review-draft', '', 'oe-editor-action'),
      );
    }
    controls.append(button('활성화', 'activate-draft', '', 'oe-editor-action oe-editor-action-primary'));
    editor.append(context, label, validation, controls);
    return editor;
  }
  if (state.draft) {
    const notice = h('div', 'oe-warning', `초안 대상은 ${state.draft.target_id}로 고정되어 있습니다.`);
    const code = h('pre', 'oe-code');
    code.append(h('code', '', JSON.stringify(state.selection.raw, null, 2)));
    const wrap = h('div', 'oe-definition');
    wrap.append(notice, code);
    return wrap;
  }
  const code = h('pre', 'oe-code');
  code.append(h('code', '', JSON.stringify(state.selection.raw, null, 2)));
  return code;
}

function renderInspector(state) {
  const article = h('article', 'oe-panel');
  article.setAttribute('aria-live', 'polite');
  const head = h('div', 'oe-panel-head');
  const title = h('div', 'oe-title-block');
  title.append(h('h1', '', state.selection.canonical_id), h('p', '', `${state.selection.kind} · ${state.selection.config_path}`));
  const actions = h('div', 'oe-head-actions');
  const mode = state.viewContext?.mode || 'active';
  actions.append(h('span', 'oe-status oe-status--active', `● ACTIVE · ${state.selection.compile_status}`));
  if (state.draft) {
    actions.append(h('span', `oe-status oe-status--${state.draft.lifecycle_status}`, `◇ DRAFT · ${state.draft.lifecycle_status}`));
    const activeButton = button('Active 보기', 'view-active', '', `oe-mode-action ${mode !== 'draft_preview' ? 'is-current' : ''}`);
    activeButton.setAttribute('aria-pressed', String(mode !== 'draft_preview'));
    const draftButton = button('Draft preview', 'view-draft', '', `oe-mode-action ${mode === 'draft_preview' ? 'is-current' : ''}`);
    draftButton.setAttribute('aria-pressed', String(mode === 'draft_preview'));
    draftButton.disabled = !state.draft.preview_valid;
    actions.append(activeButton, draftButton);
  }
  if (!state.draft && state.selection.config_file === 'ledger_config.json') {
    actions.append(button('초안 편집', 'create-draft', '', 'oe-edit-action'));
  }
  head.append(title, actions);
  article.append(head);

  const tabs = h('div', 'oe-tabs');
  tabs.setAttribute('role', 'tablist');
  for (const [id, label] of [
    ['definition', '정의'], ['authoring', '작성'], ['usage', '사용처'], ['raw', '원본 JSON'],
  ]) {
    const tab = button(label, 'tab', id, 'oe-tab');
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-selected', String(state.detailTab === id));
    tab.setAttribute('aria-controls', `oe-panel-${id}`);
    tabs.append(tab);
  }
  const panel = h('div', 'oe-tab-panel');
  panel.id = `oe-panel-${state.detailTab}`;
  panel.setAttribute('role', 'tabpanel');
  if (state.detailTab === 'usage') panel.append(renderUsage(state));
  else if (state.detailTab === 'raw') panel.append(renderRaw(state));
  else if (state.detailTab === 'authoring') panel.append(renderAuthoring(state));
  else panel.append(renderDefinition(state));
  article.append(tabs, panel);
  return article;
}

// ---------------------------------------------------------------- authoring panels
//
// 🔴 NO LIST LITERALS BELOW. Every step, tier, state name, candidate and closed list is
// read from the server payload. The one place this file may name a value is a CSS class
// derived from a server-supplied id. A copy here would go stale the day a declaration is
// added and would go stale SILENTLY, which is the failure the whole round is about.

function renderStepBar(state) {
  const plan = state.authoring;
  const bar = h('nav', 'oe-steps');
  bar.setAttribute('aria-label', '셋업 걸음');
  if (!plan) {
    bar.append(h('div', 'oe-empty', state.authoringError || '작성 계획 불러오는 중…'));
    return bar;
  }
  const here = state.selection?.config_path || '';
  // 🔴 THE SPINE IS NUMBERED BECAUSE THE ORDER IS REAL, not because numbers look tidy: a
  // pack cannot name a predicate that does not exist yet, so 낱말 → 엔터티 → 팩 → 프로필 →
  // 매퍼 → 소스 is a dependency order and arriving at a layer early is normal. The server
  // sends the layers in that order and the screen does not re-sort them.
  plan.steps.forEach((step, index) => {
    const item = h('div', `oe-step is-${step.status}`);
    item.dataset.key = `step:${step.id}`;
    // The step the current selection belongs to, decided by the server's section list.
    if (step.sections.some((name) => here.includes(name))) item.classList.add('is-here');
    item.append(h('span', 'oe-step-ord', String(index + 1)));
    item.append(h('b', '', step.label));
    const tally = h('span', 'oe-step-tally');
    // The remaining count -- the one number an operator reads to find where work is left.
    // Computed by the SERVER (`is_remaining`), never re-derived here: the collapse rule
    // reads the same predicate, and a screen whose count and whose folding disagree is a
    // screen where neither is believed.
    if (step.remaining) {
      tally.append(h('i', 'oe-tally oe-tally--remaining', `${step.remaining} remaining`));
    } else if (step.declared) {
      tally.append(h('i', 'oe-tally oe-tally--done', 'Complete'));
    }
    for (const [key, mark] of [['unanswered', 'Optional'], ['derived', 'Derived']]) {
      if (!step[key]) continue;
      tally.append(h('i', `oe-tally oe-tally--${key}`, `${mark} ${step[key]}`));
    }
    if (!step.declared) tally.append(h('i', 'oe-tally', 'None defined'));
    item.append(tally);
    bar.append(item);
  });
  return bar;
}

function renderGround(row) {
  // The ground goes NEXT TO the value, never in a tooltip: a fill whose reason is one
  // hover away is a fill nobody reads, and an unread reason is a silent default.
  const ground = row.ground;
  if (!ground) return null;
  const box = h('div', 'oe-ground');
  box.append(h('span', 'oe-ground-text', ground.text));
  for (const path of ground.from_paths.slice(0, 2)) box.append(h('code', '', path));
  if (ground.from_paths.length > 2) {
    box.append(h('small', '', `외 ${ground.from_paths.length - 2}곳`));
  }
  return box;
}

function formatValue(value) {
  if (value === null || value === undefined) return '—';
  return typeof value === 'string' ? value : JSON.stringify(value);
}

function renderValue(row) {
  const value = row.value;
  if (value === null || value === undefined) return h('span', 'oe-value is-none', 'None');
  if (Array.isArray(value)) {
    const list = h('span', 'oe-value');
    if (!value.length) list.append(h('i', 'oe-chip is-none', '비움'));
    for (const item of value) {
      list.append(h('i', 'oe-chip', typeof item === 'string' ? item : JSON.stringify(item)));
    }
    return list;
  }
  if (typeof value === 'object') return h('code', 'oe-value', JSON.stringify(value));
  return h('span', 'oe-value', String(value));
}

// Does this row fold, and if so what does the folded line SAY?
//
// 🔴 FOLDING BY LENGTH WOULD HIDE THE DECISIONS. The whole point of the 164-field screen
// is the handful of real human judgements in it, and those are exactly the longest rows.
// So the fold is decided by DEGREES OF FREEDOM, and the precedence below is not
// negotiable -- it is what keeps the folding from contradicting the remaining count.
//
//     remaining -> open · problem -> open · derived/forced -> fold · single candidate ->
//     fold (reason shown) · otherwise -> open
//
// 🔴 `remaining` OUTRANKS EVERYTHING, INCLUDING A SINGLE CANDIDATE AND INCLUDING DERIVED.
// Without that, the layer header can say "3 remaining" while one of the three is folded out of
// sight, and an operator who catches that once stops believing both numbers. So a
// one-candidate field that is not yet FILLED stays open until it is.
//
// 🔴 AND A SINGLE CANDIDATE IS NOT THE SAME AS FORCED, which is the ruling this
// implements. Derived means the SCHEMA fixed it -- true tomorrow too. One candidate means
// TODAY'S DATA offers one, and declaring a second pack makes it two. Folding the second as
// if it were the first builds a fold that goes wrong on the day something connects: a
// genuine choice appears and stays hidden behind a fold nobody re-opened. That is why the
// count is read HERE, at render time, from the candidate list as it currently is -- never
// cached, never stamped on the field. When the list grows to two, the row opens by itself.
function foldDecision(row, expanded = []) {
  // The operator's own choice wins over every rule below it. A fold nobody can open is
  // not a fold, it is a deletion.
  if (expanded.includes(row.path)) return { open: true, reason: '', byHand: true };
  if (row.remaining) return { open: true, reason: '' };
  if (row.conflicts || row.refusals?.length) return { open: true, reason: '' };
  if (row.state === 'derived') {
    return { open: false, reason: row.disposition === 'grammar_requires_it' ? 'Forced' : 'Derived' };
  }
  // Read live. `candidates` is the list the server sent for THIS render.
  if (Array.isArray(row.candidates) && row.candidates.length === 1) {
    return { open: false, reason: 'Single candidate' };
  }
  return { open: true, reason: '' };
}

function renderAuthoringRow(row, expanded = []) {
  const fold = foldDecision(row, expanded);
  const card = h('div', `oe-field is-${row.state}${fold.open ? '' : ' is-folded'}`);
  card.dataset.key = `field:${row.path}`;
  const head = h('div', 'oe-field-head');
  head.append(h('b', '', row.label));
  head.append(h('i', `oe-tier oe-tier--${row.tier}`, row.tier));
  card.append(head);
  if (!fold.open) {
    // The folded line is one row: value, and WHY it folded. A fold whose reason is
    // invisible reads as the screen deciding for the operator, which is the exact thing
    // the acceptance bar forbids -- so the reason is rendered, not implied.
    const line = button('', 'toggle-field', row.path, 'oe-field-folded');
    line.setAttribute('aria-expanded', 'false');
    line.append(h('code', 'oe-folded-value', formatValue(row.value)));
    line.append(h('i', 'oe-folded-why', fold.reason));
    const why = row.ground?.text;
    if (why) line.append(h('small', 'oe-folded-ground', why));
    card.append(line);
    return card;
  }
  if (fold.byHand) {
    const shut = button('Fold', 'toggle-field', row.path, 'oe-field-refold');
    shut.setAttribute('aria-expanded', 'true');
    head.append(shut);
  }
  card.append(h('code', 'oe-field-path', row.path));
  if (row.state !== 'missing') card.append(renderValue(row));
  const ground = renderGround(row);
  if (ground) card.append(ground);
  if (row.conflicts) {
    const clash = h('div', 'oe-field-conflict');
    clash.append(h('b', '', '선언과 불일치'));
    clash.append(h('code', '', JSON.stringify(row.declared)));
    card.append(clash);
  }
  // 🔴 NO GREYED BOXES. A filled value a person cannot act on is force wearing the
  // costume of a choice. Each disposition gets a real action instead: for a value fixed
  // by another declaration the lever is ON that declaration, so the row sends you there.
  if (row.state === 'derived' && row.disposition) {
    const act = h('div', 'oe-field-act');
    if (row.disposition === 'grammar_requires_it') {
      act.append(h('span', '', '강제 · 이 자리에서 못 바꿈'));
    } else if (row.disposition === 'remove_from_file') {
      act.append(h('span', '', '강제 · 파일에서 뺄 수 있음'));
    } else if (row.disposition === 'default_overridable') {
      act.append(h('span', '', '기본값 · 덮어쓸 수 있음'));
    } else if (row.disposition === 'unmeasured') {
      act.append(h('span', '', '거절이 남아 있어 제거 가능 여부 미측정'));
    }
    for (const key of row.ground?.from_keys || []) {
      const jump = button(`근거 · ${key.split('|')[1] || key}`, 'select', key, 'oe-jump');
      jump.dataset.direct = 'true';
      act.append(jump);
    }
    card.append(act);
  }
  if (row.candidates && row.state !== 'derived') {
    const box = h('div', 'oe-candidates');
    const label = row.universe ? `${row.universe} · ${row.universe_note}` : '고를 수 있는 값';
    box.append(h('small', '', `${label} · ${row.candidates.length}`));
    for (const item of row.candidates.slice(0, 24)) {
      box.append(h('i', 'oe-chip', typeof item === 'string' ? item : JSON.stringify(item)));
    }
    if (row.candidates.length > 24) {
      box.append(h('small', '', `외 ${row.candidates.length - 24}개 · 접힘`));
    }
    card.append(box);
  }
  if (row.forbidden?.length) {
    const box = h('div', 'oe-candidates is-forbidden');
    box.append(h('small', '', `쓸 수 없는 이름 · ${row.forbidden.length}`));
    for (const item of row.forbidden.slice(0, 12)) box.append(h('i', 'oe-chip', item));
    if (row.forbidden.length > 12) {
      box.append(h('small', '', `외 ${row.forbidden.length - 12}개 · 접힘`));
    }
    card.append(box);
  }
  for (const refusal of row.refusals) {
    const line = h('div', 'oe-field-refusal');
    line.append(h('b', '', refusal.code), h('span', '', refusal.message));
    card.append(line);
  }
  if (row.note) card.append(h('small', 'oe-field-note', row.note));
  return card;
}

function renderAuthoring(state) {
  const wrap = h('div', 'oe-authoring');
  const plan = state.authoring;
  if (!plan) {
    wrap.append(h('div', 'oe-empty', state.authoringError || '작성 계획 불러오는 중…'));
    return wrap;
  }
  if (state.authoringError) wrap.append(h('div', 'oe-warning', state.authoringError));
  // The blocked strongest tier, stated rather than absorbed: fields whose value is fully
  // determined AND that the grammar still demands as a key. Each is a question the screen
  // can answer but cannot remove, and that is a config-grammar item, not a UI one.
  const blocked = plan.force_summary?.grammar_requires_it || 0;
  if (blocked) {
    wrap.append(h('div', 'oe-note',
      `자유도 0인데 문법이 요구하는 칸 ${blocked}개 · 화면이 채우고 근거로 보낸다`));
  }
  if (plan.config_source?.state !== 'present') {
    wrap.append(h('div', 'oe-warning',
      `${plan.config_source?.file || plan.physical_schema_file} not found · blank`));
  }
  // Bucket order is the reading order: what must be done, what is still asked, what was
  // filled for you. Groups are always rendered, empty or not -- a vanished heading is
  // indistinguishable from "nothing to do".
  const buckets = [
    ['missing', '빠짐'], ['unanswered', '미답'],
    ['derived', '파생됨 · 묻지 않음'], ['answered', '답함'],
  ];
  for (const [stateId, label] of buckets) {
    const rows = plan.fields.filter((row) => row.state === stateId);
    const section = h('section', `oe-bucket oe-bucket--${stateId}`);
    section.append(h('h3', '', `${label} · ${rows.length}`));
    if (!rows.length) section.append(h('div', 'oe-empty', 'None defined'));
    for (const row of rows) section.append(renderAuthoringRow(row, state.expandedFields));
    wrap.append(section);
  }
  if (plan.unattached_refusals?.length) {
    const section = h('section', 'oe-bucket oe-bucket--missing');
    section.append(h('h3', '', `필드에 붙지 않은 거절 · ${plan.unattached_refusals.length}`));
    for (const refusal of plan.unattached_refusals) {
      const line = h('div', 'oe-field-refusal');
      line.append(h('b', '', refusal.code), h('code', '', refusal.path),
        h('span', '', refusal.message));
      section.append(line);
    }
    wrap.append(section);
  }
  return wrap;
}

function renderIntegrity(state) {
  const aside = h('aside', 'oe-panel');
  const head = h('div', 'oe-panel-head');
  const title = h('div', 'oe-title-block');
  title.append(h('h1', '', 'Integrity'), h('p', '', state.viewContext?.context_token || 'No compiled context'));
  head.append(title);
  const body = h('div', 'oe-side-body');
  const checks = h('section', 'oe-side-section');
  checks.append(h('h3', '', '참조 검사'));
  const list = h('div', 'oe-check-list');
  for (const check of state.integrity) {
    const row = h('div', 'oe-check');
    row.append(h('i', '', check.status === 'valid' ? '✓' : '•'), h('span', '', `${check.status} · ${check.message}`));
    list.append(row);
  }
  checks.append(list);
  const uses = h('section', 'oe-side-section');
  uses.append(h('h3', '', `이 정의를 사용하는 곳 · ${state.usedByTotal}`));
  const usageList = h('div', 'oe-usage-list');
  const nodes = nodeMap(state);
  for (const edge of state.usedBy) {
    const node = nodes.get(edge.from_key);
    const row = button(node?.canonical_id || edge.from_key, 'select', edge.from_key, 'oe-usage');
    row.dataset.edgeId = edge.edge_id;
    row.append(h('small', '', `${edge.reference_kind} · ${edge.status} · ${edge.json_pointer}`));
    addPopover(row, node);
    usageList.append(row);
  }
  if (!state.usedBy.length) usageList.append(h('div', 'oe-empty', '상위 참조가 없습니다.'));
  else if (state.referencesTruncated) usageList.append(
    h('div', 'oe-empty', `표시 상한 ${state.usedBy.length}개 · 전체 수는 상단에 표시`));
  uses.append(usageList);
  const changeSection = h('section', 'oe-side-section');
  if (state.viewContext?.mode === 'draft_preview') {
    changeSection.append(h('h3', '', 'Draft changes'));
    const changeList = h('div', 'oe-change-list');
    for (const change of state.changes) {
      const node = nodes.get(change.key);
      const row = node
        ? button(change.canonical_id, 'select', change.key, 'oe-usage')
        : h('div', 'oe-change-row', change.canonical_id || change.key);
      row.append(h('small', '', `${change.change_status} · ${change.kind} · ${change.json_pointer}`));
      changeList.append(row);
    }
    for (const edge of state.edgeChanges) {
      const row = h('div', 'oe-change-row', edge.reference_kind || edge.edge_id);
      row.append(h('small', '', `${edge.change_status} · ${edge.status} · ${edge.json_pointer}`));
      changeList.append(row);
    }
    if (!state.changes.length && !state.edgeChanges.length) {
      changeList.append(h('div', 'oe-empty', 'active 대비 변경이 없습니다.'));
    }
    changeSection.append(changeList);
  }
  body.append(uses, checks);
  if (state.viewContext?.mode === 'draft_preview') body.append(changeSection);
  aside.append(head, body);
  return aside;
}

export function renderOntologyExplorer(root, state) {
  const windowEl = h('section', 'oe-window');
  windowEl.setAttribute('aria-label', 'Ontology Config Explorer');
  const top = h('header', 'oe-topbar');
  const history = h('div', 'oe-history-actions');
  const back = button('←', 'back', '', 'oe-icon-action');
  back.disabled = !state.navigation.back.length;
  back.setAttribute('aria-label', '이전 선택');
  const forward = button('→', 'forward', '', 'oe-icon-action');
  forward.disabled = !state.navigation.forward.length;
  forward.setAttribute('aria-label', '다음 선택');
  history.append(back, forward);
  top.append(history, h('div', 'oe-brand', 'Ontology Config Explorer'));
  const snap = state.activeSnapshot?.snapshot_hash?.slice(0, 8) || '불러오는 중';
  top.append(h('span', 'oe-snapshot', `● snapshot · ${snap}`));
  const searchLabel = h('label', 'oe-search-wrap');
  searchLabel.append(h('span', 'sr-only', '정의 검색'));
  const search = h('input', 'oe-search');
  search.type = 'search';
  search.placeholder = 'ID 또는 종류 검색';
  search.value = state.query;
  search.dataset.action = 'search';
  searchLabel.append(search);
  top.append(searchLabel);
  windowEl.append(top);
  if (state.error) windowEl.append(h('div', 'oe-error', state.error));
  if (state.removedSelection) {
    windowEl.append(h('div', 'oe-error', `${state.removedSelection.key} · removed/unresolved`));
  }
  if (state.viewContext?.fallback_reason) {
    windowEl.append(h('div', 'oe-warning', `초안 대신 활성 snapshot 표시: ${state.viewContext.fallback_reason}`));
  }
  const main = h('div', 'oe-main');
  main.append(renderTree(state));
  const workspace = h('main', 'oe-workspace');
  // Always first, always one line: "지금 어느 걸음인가" is the one element the owner
  // asked to keep and strengthen, and it must survive the no-selection case too --
  // that is the from-scratch entry, where it is the only thing on screen.
  workspace.append(renderStepBar(state));
  if (state.selection) {
    workspace.append(renderBreadcrumb(state), renderPaths(state));
    const detail = h('section', 'oe-detail-grid');
    detail.append(renderInspector(state), renderIntegrity(state));
    workspace.append(detail);
  } else if (state.authoring) {
    workspace.append(renderAuthoring(state));
  } else {
    workspace.append(h('div', 'oe-empty', state.loading ? '불러오는 중…' : '표시할 정의가 없습니다.'));
  }
  main.append(workspace);
  windowEl.append(main);
  replace(root, windowEl);
}
