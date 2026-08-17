import { isDraftRevisionEditable } from './ontology_explorer_store.js';

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

function replace(root, child) {
  root.replaceChildren(child);
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
      row.dataset.direct = 'true';
      row.setAttribute('aria-current', String(item.key === state.selection?.key));
      row.append(h('small', 'oe-change-label', item.change_status));
      addPopover(row, item);
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
  for (const [id, label] of [['definition', '정의'], ['usage', '사용처'], ['raw', '원본 JSON']]) {
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
  else panel.append(renderDefinition(state));
  article.append(tabs, panel);
  return article;
}

function renderIntegrity(state) {
  const aside = h('aside', 'oe-panel');
  const head = h('div', 'oe-panel-head');
  const title = h('div', 'oe-title-block');
  title.append(h('h1', '', 'Integrity'), h('p', '', state.viewContext?.context_token || 'compiled context 없음'));
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
