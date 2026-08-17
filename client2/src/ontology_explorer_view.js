const KIND_LABELS = Object.freeze({
  source: 'Sources', profile: 'Profiles', mapping: 'Mappings', pack: 'Packs',
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

function replace(root, child) {
  root.replaceChildren(child);
}

function nodeMap(state) {
  return new Map([...state.items, ...state.nodes].map((node) => [node.key, node]));
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
  for (const [kind, items] of groups) {
    const group = h('section', 'oe-tree-group');
    group.append(h('div', 'oe-tree-heading', KIND_LABELS[kind] || kind));
    for (const item of items) {
      const row = button(item.canonical_id, 'select', item.key, 'oe-tree-item');
      row.setAttribute('aria-current', String(item.key === state.selection?.key));
      row.title = `${item.kind} · ${item.config_path}`;
      group.append(row);
    }
    nav.append(group);
  }
  if (!state.items.length) nav.append(h('div', 'oe-empty', '일치하는 정의가 없습니다.'));
  return nav;
}

function renderPaths(state) {
  const area = h('section', 'oe-flow-area');
  const heading = h('div', 'oe-section-heading');
  heading.append(h('h2', '', 'Reference Flow'), h('span', '', '경로는 서로 합치지 않고 각각 표시'));
  area.append(heading);
  const nodes = nodeMap(state);
  for (const path of state.paths) {
    const lane = h('div', 'oe-flow');
    lane.dataset.pathId = path.path_id;
    path.node_keys.forEach((key, index) => {
      const node = nodes.get(key);
      const card = button('', 'select', key, 'oe-flow-node');
      if (index > 0) card.dataset.edgeId = path.edge_ids[index - 1] || '';
      card.setAttribute('aria-pressed', String(key === state.selection?.key));
      card.append(h('div', 'oe-node-kind', node?.kind || 'unknown'));
      card.append(h('div', 'oe-node-name', node?.canonical_id || key));
      lane.append(card);
      if (index < path.node_keys.length - 1) lane.append(h('div', 'oe-arrow', '→'));
    });
    area.append(lane);
  }
  return area;
}

function renderBreadcrumb(state) {
  const trail = h('div', 'oe-breadcrumb');
  trail.setAttribute('aria-label', '탐색 경로');
  const nodes = nodeMap(state);
  const path = state.paths[0]?.node_keys || [state.selection.key];
  path.forEach((key, index) => {
    const node = nodes.get(key);
    const crumb = button(node?.canonical_id || key, 'select', key, 'oe-crumb-button');
    if (index > 0) crumb.dataset.edgeId = state.paths[0]?.edge_ids[index - 1] || '';
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
    keyValue('버전', selected.version ?? '버전 없음'),
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
    wrap.append(row);
  }
  if (!rows.length) wrap.append(h('div', 'oe-empty', '직접 참조가 없습니다.'));
  return wrap;
}

function renderRaw(state) {
  if (state.draft) {
    const editor = h('div', 'oe-editor');
    const context = h('div', 'oe-editor-context');
    context.append(keyValue('초안 상태', state.draft.lifecycle_status));
    context.append(keyValue('Revision', state.draft.revision));
    context.append(keyValue('기준 snapshot', state.draft.base_snapshot_hash));
    const label = h('label', 'oe-label', 'Working draft JSON');
    const textarea = h('textarea', 'oe-editor-textarea');
    textarea.value = state.editorText;
    textarea.spellcheck = false;
    textarea.dataset.action = 'edit-raw';
    label.append(textarea);
    const validation = h('div', 'oe-editor-validation');
    validation.dataset.valid = String(Boolean(state.draft.preview_valid));
    const errors = state.draft.validation_errors || [];
    validation.textContent = errors.length
      ? errors.map((e) => `[${e.code}] ${e.path}: ${e.message}`).join('\n')
      : (state.draft.preview_valid ? '✓ 동일 compiler로 검증된 초안입니다.' : '저장하면 검증합니다.');
    const controls = h('div', 'oe-editor-controls');
    controls.append(
      button('초안 폐기', 'discard-draft', '', 'oe-editor-action'),
      button('저장·검증', 'save-draft', '', 'oe-editor-action'),
      button('검토 요청', 'review-draft', '', 'oe-editor-action'),
      button('활성화', 'activate-draft', '', 'oe-editor-action oe-editor-action-primary'),
    );
    editor.append(context, label, validation, controls);
    return editor;
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
  const badge = h('span', `oe-status oe-status--${mode}`, `${mode === 'draft_preview' ? '◇ DRAFT' : '● ACTIVE'} · ${state.selection.compile_status}`);
  actions.append(badge);
  if (!state.draft && state.selection.config_file === 'ledger_config.json') {
    actions.append(button('초안 편집', 'create-draft', '', 'oe-edit-action'));
  }
  head.append(title, actions);
  article.append(head);

  const tabs = h('div', 'oe-tabs');
  tabs.setAttribute('role', 'tablist');
  for (const [id, label] of [['definition', '정의'], ['usage', '사용처'], ['raw', '원본 JSON']]) {
    const tab = button(label, 'tab', id, 'oe-tab');
    tab.setAttribute('role', 'tab');
    tab.setAttribute('aria-selected', String(state.detailTab === id));
    tabs.append(tab);
  }
  const panel = h('div', 'oe-tab-panel');
  if (state.detailTab === 'usage') panel.append(renderUsage(state));
  else if (state.detailTab === 'raw') panel.append(renderRaw(state));
  else panel.append(renderDefinition(state));
  article.append(tabs, panel);
  return article;
}

function renderIntegrity(state) {
  const aside = h('aside', 'oe-panel');
  const head = h('div', 'oe-panel-head');
  const title = h('div', 'oe-title-block');
  title.append(h('h1', '', 'Integrity'), h('p', '', '같은 compiled snapshot 기준'));
  head.append(title);
  const body = h('div', 'oe-side-body');
  const checks = h('section', 'oe-side-section');
  checks.append(h('h3', '', '참조 검사'));
  const list = h('div', 'oe-check-list');
  for (const check of state.integrity) {
    const row = h('div', 'oe-check');
    row.append(h('i', '', check.status === 'valid' ? '✓' : '•'), h('span', '', check.message));
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
    row.append(h('small', '', `${edge.reference_kind} · ${edge.json_pointer}`));
    usageList.append(row);
  }
  if (!state.usedBy.length) usageList.append(h('div', 'oe-empty', '상위 참조가 없습니다.'));
  else if (state.referencesTruncated) usageList.append(
    h('div', 'oe-empty', `표시 상한 ${state.usedBy.length}개 · 전체 수는 상단에 표시`));
  uses.append(usageList);
  body.append(uses, checks);
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
  if (state.viewContext?.fallback_reason) {
    windowEl.append(h('div', 'oe-warning', `초안 대신 활성 snapshot 표시: ${state.viewContext.fallback_reason}`));
  }
  const main = h('div', 'oe-main');
  main.append(renderTree(state));
  const workspace = h('main', 'oe-workspace');
  if (state.selection) {
    workspace.append(renderBreadcrumb(state), renderPaths(state));
    const detail = h('section', 'oe-detail-grid');
    detail.append(renderInspector(state), renderIntegrity(state));
    workspace.append(detail);
  } else {
    workspace.append(h('div', 'oe-empty', state.loading ? '불러오는 중…' : '표시할 정의가 없습니다.'));
  }
  main.append(workspace);
  windowEl.append(main);
  replace(root, windowEl);
}
