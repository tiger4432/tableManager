import { isDraftRevisionEditable } from './ontology_explorer_store.js';
import { commitTree } from './dom_patch.js';
import { splitBundlePath, getAtPath } from './ontology_path.js';
import { EMIT_SHAPE } from './ontology_shapes.js';

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
  //
  // 🔴 UNLESS THE SEARCH FOUND NOTHING, WHICH IS WHEN CREATING MATTERS MOST. With no
  // matches there are no groups, so every `+ New` disappeared -- and the operator's flow is
  // exactly: search the name, see it is free, create it. The screen answered 「일치하는
  // 정의가 없습니다」 and removed the way to act on that answer in the same breath (measured:
  // 0 groups, 0 buttons). Nothing is being buried here, because there is nothing to bury.
  const authorable = (state.authoringSchema?.authorable_kinds || []).map((row) => row.id);
  const ordered = state.query.trim() && groups.size
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
      // 🔴 READ IT vs FINISH IT, AND THE ROW SAYS WHICH.
      //
      // A declaration that resolved is INSPECTED -- selection, definition, 사용처, 참조
      // 검사, all of which show INTERPRETED facts. A declaration that did not resolve has
      // no interpreted facts, because it was not interpreted; the only two things true
      // about it are its text and why it could not be read, and that is exactly what the
      // draft editor shows. So its row opens the editor rather than selecting it.
      //
      // 🔴 AND THAT IS WHY IT IS NOT IN THE INDEX EITHER. Someone will notice the list has
      // a row that cannot be selected and "tidy" the mismatch by putting unread nodes into
      // the index. Do not: the list answers "what is in the file", selection answers "what
      // was interpreted". Different questions, no reason to give the same answer -- and
      // forcing them together means inventing interpreted facts that do not exist, which
      // is the failure this whole round exists to remove.
      const unread = state.invalid?.[item.key];
      const row = button(item.canonical_id, unread ? 'edit-unread' : 'select',
                         item.key, 'oe-tree-item');
      row.dataset.direct = 'true';
      row.setAttribute('aria-current', String(item.key === state.selection?.key));
      row.append(h('small', 'oe-change-label', item.change_status));
      addPopover(row, item);
      group.append(row);
      // 🔴 THE REASON SITS UNDER THE ROW, NOT IN A TOOLTIP. A declaration that could not be
      // read is one the operator has to go fix; a hover is not a place to read an
      // instruction from. ONE tag, and the sentence is what separates the two cases --
      // its own fault, or knocked out by something else that is not read yet. No second
      // badge and no second colour: 「빨강이 번지면 읽을 수가 없습니다」.
      if (unread) {
        for (const reason of unread.reasons || []) {
          const why = h('div', 'oe-tree-why');
          why.append(h('code', '', reason.path), h('span', '', reason.message));
          group.append(why);
        }
      }
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

// The entity identity keys, as repeatable free-text rows.
//
// 🔴 FREE TEXT IS CORRECT HERE, and it is the only field so far where that is true. An
// entity key is ONTOLOGY -- the operator invents it. `Lot@1 -> keys: ["lot"]` names what
// identifies the concept; the physical column that feeds it (`dt_job`) is declared
// separately on the source. `DTJob@1` spells its key and its column the same way, which is
// exactly what makes the two look like one thing.
//
// A picker here would look right on today's data and be wrong in principle: it would limit
// the concepts he may have to the columns that happen to exist, making the ontology
// subordinate to the physical tables.
//
// `x` per row is not decoration. A `+` with no way back makes a misclick permanent, which
// is the same dead end as a lock with no key. No reordering: atom identity serialises
// `subject_keys` sorted, so `["lot","wafer"]` and `["wafer","lot"]` are the same subject.
function renderEntityKeys(state) {
  let raw;
  try {
    raw = JSON.parse(state.editorText || '{}');
  } catch {
    return null;        // unparseable text is the textarea's problem, not this form's
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const keys = Array.isArray(raw.keys) ? raw.keys : [];

  const box = h('div', 'oe-keys');
  box.append(h('label', 'oe-label', 'Identity keys'));
  keys.forEach((value, index) => {
    const row = h('div', 'oe-key-row');
    row.dataset.key = `key:${index}`;
    const input = h('input', 'oe-key-input');
    input.type = 'text';
    input.value = value === null || value === undefined ? '' : String(value);
    input.dataset.action = 'edit-entity-key';
    input.dataset.value = String(index);
    input.setAttribute('aria-label', `Identity key ${index + 1}`);
    row.append(input, button('x', 'remove-entity-key', String(index), 'oe-key-remove'));
    box.append(row);
  });
  if (!keys.length) box.append(h('div', 'oe-key-none', 'None defined'));
  box.append(button('+ Add key', 'add-entity-key', '', 'oe-key-add'));
  return box;
}

// 🔴 THE RAW JSON EDITOR STAYS, AND THAT IS A RULING, NOT AN OVERSIGHT.
//
// The owner's instruction was to remove it, and the fork deliberately put that LAST --
// after the structured fields could do the same work. On 2026-08-19 it was measured and
// the day had not arrived. Do not delete this on the strength of the instruction alone;
// re-measure first.
//
// What has no other door today, counted on the live config:
//
//   * a NEW pack, mapper, profile or preparer gets **0 authoring rows**. The plan walks
//     what the document HOLDS, so a declaration whose body is `{}` yields nothing, and
//     without this textarea there is no way to type the first character.
//   * a NEW source gets 5 rows and 0 of them editable.
//   * `source_preparers.*.output_columns` (2 fields) -- no candidates, so no input.
//   * `sources.*.driver.occurred_at` (2 fields) -- dict-shaped, so chips only.
//
// Renaming is NOT on that list: this editor holds a declaration's BODY, not its name, so
// it never could rename anything. That dead end was closed from the other side, by letting
// an unread declaration be deleted (`28e2beb`).
//
// The removal becomes safe when a new declaration is offered its fields before it has any.
// The material for that already exists -- the validator emits `missing_field` with the
// exact path, and the plan already carries them in `unattached_refusals`.
function renderRaw(state) {
  // 🔴 A CREATE DRAFT HAS NO SELECTION TO MATCH. Its target is not in the snapshot --
  // that is what create means -- so it can never equal a selection, and this guard hid the
  // draft the operator had just made. He saw the declaration accepted and could not find it.
  //
  // 🔴 `creates_declaration`, NOT `!state.selection`. The second term was a PROXY for "this
  // is a create", true only while there was nothing to select -- correct on an empty config
  // and wrong from the first declaration onward. `/view` picks a selection when the caller
  // names none, so the SECOND create landed with `entity|lot@1` selected, the guard went
  // false, and the editor vanished: created, 200, and unreachable. First one fine, second
  // one dead -- which is exactly the walk the owner could not finish.
  //
  // The server already answers the real question; the record carries `creates_declaration`
  // and `public()` already ships it. This asks for the answer instead of the symptom.
  if (state.draft
      && (state.draft.creates_declaration
          || !state.selection
          || state.selection.key === state.draft.target_key)) {
    const editor = h('div', 'oe-editor');
    // The heading a create draft would otherwise never get: with the inspector skipped,
    // this is the only place the new declaration's own name appears on screen.
    if (state.draft.creates_declaration) {
      const title = h('div', 'oe-title-block');
      title.append(h('h1', '', state.draft.target_id), h('p', '', state.draft.target_kind));
      editor.append(title);
    }
    // 🔴 THE REASONS COME WITH YOU. Shown only in the list, they vanish at the moment the
    // operator opens the thing to fix it -- which is the one moment they are needed.
    const unreadHere = state.invalid?.[state.draft.target_key];
    if (unreadHere) {
      for (const reason of unreadHere.reasons || []) {
        const why = h('div', 'oe-tree-why');
        why.append(h('code', '', reason.path), h('span', '', reason.message));
        editor.append(why);
      }
    }
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
    // 🔴 ONE SAVE, AND THE LIFECYCLE BRANCH IS GONE -- IT WAS THE FLICKER.
    //
    //     초안 편집 버튼이 나오다 말다하고 저장검증은 뭐고 검토 요청은 뭔지 모르겠음
    //
    // `저장·검증` and `검토 요청` used to swap for `새 revision 편집` the moment a draft
    // became `review_requested`, so the save control vanished on its own. That is the
    // "appears and disappears" -- a state bug wearing a layout costume, and removing the
    // review step removes it rather than repairing it.
    //
    // Review is furniture: the sole operator cannot say what it is for. The server paths
    // stay; they are simply no longer reachable from here.
    // 🔴 FOUR BUTTONS ON THIS SCREEN, AND ONLY ONE OF THEM IS HERE.
    //
    //     버튼은 생성, 편집, 저장, 삭제 4가지만 · crud!  (owner, 2026-08-19)
    //
    // Create and Edit live outside the editor; Delete is its own round. What is left in
    // here is 저장 -- and 저장 now MEANS the config file changed, because the owner ruled
    // that saving is the write. `Activate` and `Discard` are gone: the first was a second
    // name for what Save already does, and the second was a control nobody asked for.
    const controls = h('div', 'oe-editor-controls');
    controls.append(button('Save', 'save-draft', '', 'oe-editor-action oe-editor-action-primary'));
    // 🔴 DELETE WHERE THE FILE HOLDS IT, WHICH IS NOT THE SAME AS "IN THE INDEX".
    // This used to require a selection, so an UNREAD declaration -- visible, in the file,
    // not in the snapshot -- had no delete button. That was a dead end with no other exit:
    // the editor changes a declaration's BODY, so a name typed wrong (`lot` for `lot@1`)
    // could not be repaired either. The owner hit exactly that tonight.
    //
    // The server no longer needs the index for the address; `state.invalid` is the screen's
    // own record of "in the file, did not resolve", the same map the unread rows render
    // from. A create draft still gets no button: nothing is written for it yet.
    if ((!state.draft.creates_declaration && state.selection)
        || state.invalid?.[state.draft.target_key]) {
      controls.append(button('Delete', 'delete-declaration', state.draft.target_key,
                             'oe-editor-action oe-editor-action-danger'));
    }
    editor.append(context);
    if (state.draft.target_kind === 'entity') {
      const keysForm = renderEntityKeys(state);
      if (keysForm) editor.append(keysForm);
    }
    // 🔴 THE FIELD ROWS LIVE IN THE EDITING AREA, NOT IN A LIST UNDER IT.
    //     「그거를 편집 영역으로 올려서 폼으로 만들면 되겠네」 (owner, 2026-08-19)
    // This is a MOVE, not a new surface: the same rows the plan already rendered below,
    // brought up to where the declaration is being edited, so filling them IS the editing.
    // No new area, no new mode, no modal -- the owner's standing rule.
    if (state.authoring) editor.append(renderAuthoring(state));
    editor.append(label, validation, controls);
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
    bar.append(h('div', 'oe-empty', state.authoringError || (state.loading ? 'Loading' : 'None')));
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
  // 🔴 A SETTLED DECISION IS NOT A PENDING ONE. A person-decided field that is already
  // filled and carries no problem is done -- keeping it open spends the operator's
  // attention re-reading answers nobody is asking for.
  //
  // This is what makes the page short. Measured: folding only the derived and the
  // single-candidate rows cut 23.5% and left 16 screens, because those rows were ALREADY
  // the short ones -- the tall ones are the filled choices, carrying their whole candidate
  // list. Folding by "is anything still owed here" instead of by tier is what turns a
  // complete config into a short page, which is the state it should read as.
  if (row.state === 'answered') return { open: false, reason: 'Set' };
  if (row.state === 'unanswered') return { open: false, reason: 'Optional' };
  return { open: true, reason: '' };
}

function renderAuthoringRow(row, expanded = [], editable = null) {
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
    // 🔴 A DATALIST ON THE INPUT, NEVER A `select`. The list SUGGESTS; it must not
    // constrain, because coining a name that nothing has yet is a thing this screen has
    // to keep allowing. (owner, 2026-08-19: 「미묘한 오타로 같은 말이 갈라지는거 방지」 --
    // the defence against a typo is being able to PICK, not being refused.)
    //
    // Only where there is somewhere to write: a string leaf, inside the declaration whose
    // draft is open. With no draft the row keeps its chips -- an input that cannot write
    // is a control that refuses, which this file already rules is worse than no control.
    if (editable) {
      const listId = `oe-dl-${row.path.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
      const list = h('datalist');
      list.id = listId;
      for (const item of row.candidates) {
        const option = h('option');
        option.value = typeof item === 'string' ? item : JSON.stringify(item);
        list.append(option);
      }
      const nameInput = (value, action, index) => {
        const input = h('input', 'oe-field-input');
        input.type = 'text';
        // 🔴 THE DRAFT'S VALUE, NOT THE PLAN'S. `row.value` is what the plan compiled from
        // the file, so it does not move while a draft is unsaved -- binding the input to
        // it made every keystroke snap back to the saved value on the next render, which
        // reads exactly like the screen throwing typing away (`7086056`). Caught by walking.
        input.value = value;
        input.dataset.action = action;
        input.dataset.value = row.path;
        if (index !== undefined) input.dataset.index = String(index);
        input.setAttribute('list', listId);
        input.setAttribute('aria-label', row.label);
        return input;
      };
      if (editable.kind === 'closed') {
        // 🔴 THE CURRENT VALUE IS ALWAYS AN OPTION, even when it is not in the list. A
        // dropdown that silently swaps an unrecognised value for its first option would
        // rewrite the operator's file by being rendered -- the same silent-change defect
        // this screen has been removing all day. A stray value stays visible and stays
        // wrong until a person changes it.
        const select = h('select', 'oe-field-select');
        select.dataset.action = 'edit-field';
        select.dataset.value = row.path;
        select.setAttribute('aria-label', row.label);
        const options = editable.options.includes(editable.value)
          ? editable.options : [editable.value, ...editable.options];
        for (const item of options) {
          const option = h('option', '', item);
          option.value = item;
          if (item === editable.value) option.selected = true;
          select.append(option);
        }
        box.append(select);
      } else if (editable.kind === 'list') {
        // The entity-keys shape, generalised: the rows edit the same draft buffer through
        // the same path tools, so save, dirty-tracking and the revision guard are untouched.
        editable.value.forEach((item, index) => {
          const line = h('div', 'oe-field-row');
          const drop = button('x', 'remove-field-item', row.path, 'oe-field-row-remove');
          drop.dataset.index = String(index);
          line.append(nameInput(item, 'edit-field-item', index), drop);
          box.append(line);
        });
        if (!editable.value.length) box.append(h('div', 'oe-key-none', 'None defined'));
        box.append(button('+ Add', 'add-field-item', row.path, 'oe-field-row-add'));
      } else {
        box.append(nameInput(editable.value, 'edit-field'));
      }
      box.append(list);
    } else {
      for (const item of row.candidates.slice(0, 24)) {
        box.append(h('i', 'oe-chip', typeof item === 'string' ? item : JSON.stringify(item)));
      }
      if (row.candidates.length > 24) {
        box.append(h('small', '', `외 ${row.candidates.length - 24}개 · 접힘`));
      }
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

// Which declaration is open for writing right now, as the `bundle.<section>.<id>.` prefix
// its fields carry -- or '' when nothing is open.
//
// 🔴 THE SECTION COMES FROM THE SERVER'S OWN MAP (`authorable_kinds`, sourced from
// `AUTHORABLE_SECTIONS`), never from a list written here. A kind-to-section table copied
// into this file would be a second rule to drift.
//
// 🔴 AND THE ID ALONE IS NOT ENOUGH. The live config declares BOTH `packs.dt-job@1` and
// `profiles.dt-job@1`; matching on the id would make a pack's field look writable while a
// profile's draft was open, and the write would land in the wrong declaration.
function writablePrefix(state) {
  const draft = state.draft;
  if (!draft || !state.editorText) return '';
  const kinds = state.authoringSchema?.authorable_kinds || [];
  const section = kinds.find((row) => row.id === draft.target_kind)?.section;
  if (!section || !draft.target_id) return '';
  return `bundle.${section}.${draft.target_id}.`;
}

// One claim as a block: the roles it needs, then the sentence it emits.
//
// 🔴 THE ROLES COME FROM THE DRAFT, NOT FROM THE PLAN. Measured: a pack's plan carries only
// `emit.*` rows -- `claims.<id>.roles` is never a field. But the roles are sitting in the
// draft document, and this screen already has a precedent for reading them straight from
// there rather than inventing a server field: `renderEntityKeys` renders the identity keys
// off `editorText`. Same move, so no new endpoint and no second schema.
//
// 🔴 AND `$subject` PICKS FROM THE ROLES THIS CLAIM JUST DEFINED -- the first field on this
// screen whose candidates come from a SIBLING rather than from the document. That is why it
// has to read the draft: the roles being offered may not be saved yet.
function renderClaimBlock(state, packId, claimId, claim, rows, renderRow, closedListFor,
                          fold, prefix, draftRaw) {
  const byPath = new Map(rows.map((row) => [row.path, row]));
  const box = h('section', `oe-claim${fold.open ? '' : ' is-folded'}`);
  box.dataset.key = `claim:${claimId}`;
  // 🔴 A COMPLETE CLAIM FOLDS; ONE THAT STILL OWES SOMETHING OPENS. Same predicate the
  // rows already use (`remaining`, plus conflicts and refusals) -- no new rule, and 「남은
  // 수」 keeps counting only what is actually owed. The owner's complaint was 「복잡해서
  // 구조를 못 외우겠다」, and half of that answer is showing less at once: a pack with five
  // claims opens the ones that need a hand, not all five.
  const toggle = button('', 'toggle-field', fold.key, 'oe-claim-toggle');
  toggle.setAttribute('aria-expanded', String(fold.open));
  toggle.append(h('h4', 'oe-claim-name', claimId));
  if (!fold.open) toggle.append(h('i', 'oe-folded-why', fold.reason));
  box.append(toggle);
  if (!fold.open) return box;
  const base = `claims.${claimId}`;
  const roles = claim && typeof claim.roles === 'object' && !Array.isArray(claim.roles)
    ? claim.roles : {};
  const roleNames = Object.keys(roles);

  const rolesBox = h('div', 'oe-claim-roles');
  rolesBox.append(h('label', 'oe-label', '역할'));
  const kindOptions = state.authoringSchema?.role_kind || [];
  for (const name of roleNames) {
    const role = roles[name] && typeof roles[name] === 'object' ? roles[name] : {};
    const line = h('div', 'oe-role-row');
    line.append(h('code', 'oe-role-name', name));
    // The kind is a closed list, so it is a dropbox -- and the value already in the file is
    // always an option, even an unrecognised one. Rendering must never rewrite the file.
    const select = h('select', 'oe-field-select');
    select.dataset.action = 'edit-shape';
    select.dataset.value = `${base}.roles.${name}.kind`;
    select.setAttribute('aria-label', `${name} 종류`);
    const current = typeof role.kind === 'string' ? role.kind : '';
    const options = kindOptions.includes(current) ? kindOptions : [current, ...kindOptions];
    for (const item of options) {
      const option = h('option', '', item);
      option.value = item;
      if (item === current) option.selected = true;
      select.append(option);
    }
    const required = h('input', 'oe-role-required');
    required.type = 'checkbox';
    required.checked = role.required === true;
    required.dataset.action = 'edit-shape-flag';
    required.dataset.value = `${base}.roles.${name}.required`;
    required.setAttribute('aria-label', `${name} 필수`);
    line.append(select, required, h('span', 'oe-role-required-label', '필수'));
    rolesBox.append(line);
  }
  if (!roleNames.length) rolesBox.append(h('div', 'oe-key-none', 'None defined'));
  // A role's NAME is coined by the person -- free text, like the claim's own name. Its kind
  // is a closed list and stays a dropbox once the row exists.
  const roleNaming = h('div', 'oe-claim-new');
  const roleInput = h('input', 'oe-role-new-id');
  roleInput.type = 'text';
  roleInput.placeholder = '역할 id · e.g. subject';
  roleInput.dataset.claim = claimId;
  roleInput.setAttribute('aria-label', `${claimId} 새 역할 id`);
  roleNaming.append(roleInput, button('+ 역할', 'add-role', claimId, 'oe-claim-new-go'));
  rolesBox.append(roleNaming);
  box.append(rolesBox);

  const emitBox = h('div', 'oe-claim-emit');
  emitBox.append(h('label', 'oe-label', 'emit'));
  // 🔴 THE EMIT FORM IS DRAWN EVEN WHEN `emit` IS ABSENT. The plan describes what the
  // document holds, so a claim named a moment ago has no emit rows at all -- and 「emit」 as
  // a bare label with nothing under it is the screen stopping one layer in. The shape says
  // which fields exist; the plan is still preferred wherever it HAS a row, because its row
  // carries the candidates and the refusals.
  const roleOptions = roleNames.map((name) => `$${name}`);
  const drawShape = (fields, base, container) => {
    for (const field of fields) {
      const path = `${base}.${field.key}`;
      const planned = byPath.get(`${prefix}.${path}`);
      if (planned) {
        container.append(renderRow(planned));
        continue;
      }
      if (field.kind === 'object') {
        const nested = h('div', 'oe-claim-emit-nested');
        nested.append(h('label', 'oe-label', field.label || field.key));
        drawShape(field.of, path, nested);
        container.append(nested);
        continue;
      }
      const line = h('div', 'oe-draft-field');
      line.append(h('code', 'oe-draft-field-name', field.label || field.key));
      const current = getAtPath(draftRaw, splitBundlePath(path));
      const value = typeof current === 'string' ? current : '';
      if (field.kind === 'choice') {
        const options = state.authoringSchema?.[field.list] || [];
        const select = h('select', 'oe-field-select');
        select.dataset.action = 'edit-shape';
        select.dataset.value = path;
        select.setAttribute('aria-label', field.label || field.key);
        // The value in the file is always an option, unrecognised or not -- rendering must
        // never rewrite it. An absent value shows as blank rather than as the first option.
        for (const item of (options.includes(value) ? options : [value, ...options])) {
          const option = h('option', '', item);
          option.value = item;
          if (item === value) option.selected = true;
          select.append(option);
        }
        line.append(select);
      } else {
        const input = h('input', 'oe-field-input');
        input.type = 'text';
        input.value = value;
        input.dataset.action = 'edit-shape';
        input.dataset.value = path;
        input.setAttribute('aria-label', field.label || field.key);
        if (field.kind === 'roles' && roleOptions.length) {
          const listId = `oe-dl-${path.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
          const list = h('datalist');
          list.id = listId;
          for (const item of roleOptions) {
            const option = h('option');
            option.value = item;
            list.append(option);
          }
          input.setAttribute('list', listId);
          line.append(input, list);
          container.append(line);
          continue;
        }
        line.append(input);
      }
      container.append(line);
    }
  };
  drawShape(EMIT_SHAPE, `${base}.emit`, emitBox);
  box.append(emitBox);
  return box;
}

// Fields the draft holds that the PLAN has no row for.
//
// 🔴 ONE GENERIC BLOCK, NOT A BRANCH PER KIND. Four per-kind branches would be four places
// to leak into each other, which is the standing regression risk in this round. This asks
// one question instead -- "is this top-level key missing from the plan?" -- so a mapper, a
// profile and a preparer are all handled without naming any of them.
//
// Measured on live declarations: exactly 6 such fields exist -- `implementation_id` and
// `implementation_version` on mappers and preparers, `accepts_verified_join_rules` and
// `input_columns` on preparers. Objects are skipped (the plan describes what is inside
// `claims` and `mappings`), and so are lists holding objects.
//
// 🔴 NO TYPE IS ASSERTED HERE. The shape rendered follows the value ALREADY in the draft,
// and the writer preserves that value's type. A field the draft does not hold yet gets no
// row from this block at all, because guessing its shape is what this screen refuses to do.
function renderUnplannedDraftFields(state, draftRaw, plannedTopLevel) {
  if (!draftRaw || typeof draftRaw !== 'object' || Array.isArray(draftRaw)) return null;
  const rows = [];
  for (const key of Object.keys(draftRaw)) {
    if (plannedTopLevel.has(key)) continue;
    const value = draftRaw[key];
    const line = h('div', 'oe-draft-field');
    line.append(h('code', 'oe-draft-field-name', key));
    if (typeof value === 'boolean') {
      const box = h('input', 'oe-role-required');
      box.type = 'checkbox';
      box.checked = value;
      box.dataset.action = 'edit-shape-flag';
      box.dataset.value = key;
      box.setAttribute('aria-label', key);
      line.append(box);
    } else if (typeof value === 'string' || typeof value === 'number') {
      const input = h('input', 'oe-field-input');
      input.type = 'text';
      input.value = String(value);
      input.dataset.action = 'edit-shape';
      input.dataset.value = key;
      input.setAttribute('aria-label', key);
      line.append(input);
    } else if (Array.isArray(value) && value.every((item) => typeof item === 'string')) {
      value.forEach((item, index) => {
        const row = h('div', 'oe-field-row');
        const input = h('input', 'oe-field-input');
        input.type = 'text';
        input.value = item;
        input.dataset.action = 'edit-draft-item';
        input.dataset.value = key;
        input.dataset.index = String(index);
        input.setAttribute('aria-label', `${key} ${index + 1}`);
        const drop = button('x', 'remove-draft-item', key, 'oe-field-row-remove');
        drop.dataset.index = String(index);
        row.append(input, drop);
        line.append(row);
      });
      if (!value.length) line.append(h('div', 'oe-key-none', 'None defined'));
      line.append(button('+ Add', 'add-draft-item', key, 'oe-field-row-add'));
    } else {
      continue;                 // an object, or a list of objects: the plan speaks for it
    }
    rows.push(line);
  }
  if (!rows.length) return null;
  const box = h('section', 'oe-bucket oe-bucket--draft');
  box.append(h('h3', '', `그 밖의 칸 · ${rows.length}`));
  for (const row of rows) box.append(row);
  return box;
}

// The fields the validator NAMES as missing but the plan has no row for.
//
// 🔴 NOTHING IS INVENTED HERE. Every row below comes from a `missing_field` refusal the
// server already sends -- the validator says 「빈 팩엔 `claims`가 없다」 with the exact path,
// and this only moves that from a refusal line into a place you can act on. No field is
// listed that the validator did not name.
//
// 🔴 AND THE SCREEN STILL DOES NOT ASSERT A TYPE. The refusal carries `code`, `path` and a
// prose `message` -- measured -- so the shape is not machine-readable, and a table here
// saying "`claims` is an object" would be the second author removed from this screen all
// day. So the PERSON picks the shape: a value, a list, or an object. The screen offers,
// the person decides, the validator judges. That is the same division as everywhere else.
//
// This is a starting point, not a form: it gets the first key into an empty declaration so
// the plan and the draft-derived rows have something to describe. A new pack begins with
// `claims`, and from there the claim block takes over.
function renderMissingStarters(state, plan, prefix, draftRaw, ownedElsewhere = new Set()) {
  if (!prefix || !draftRaw) return null;
  const named = new Map();
  for (const refusal of plan.unattached_refusals || []) {
    if (refusal.code !== 'missing_field') continue;
    if (!refusal.path?.startsWith(prefix)) continue;
    const relative = refusal.path.slice(prefix.length);
    if (!relative) continue;
    // 🔴 NESTED LEAVES TOO, BUT ONLY WHERE THERE IS SOMEWHERE TO PUT THEM. Once a claim
    // exists the validator names `claims.<id>.emit` and `claims.<id>.roles`, and those are
    // the rows that carry a pack the rest of the way. A leaf whose PARENT does not exist
    // yet is skipped: writing it would have to invent the branch above it, which is the one
    // thing the path writer refuses to do.
    const steps = splitBundlePath(relative);
    // The claims section asks for this one, and asks the better question (a name, not a
    // shape), so it must not also appear here as a shape picker.
    if (ownedElsewhere.has(relative)) continue;
    if (getAtPath(draftRaw, steps) !== undefined) continue;
    if (steps.length > 1 && getAtPath(draftRaw, steps.slice(0, -1)) === undefined) continue;
    named.set(relative, refusal);
  }
  if (!named.size) return null;
  const box = h('section', 'oe-bucket oe-bucket--start');
  box.append(h('h3', '', `아직 없는 칸 · ${named.size}`));
  for (const [key, refusal] of named) {
    const line = h('div', 'oe-starter');
    line.append(h('code', 'oe-starter-name', key));
    // The validator's own sentence, carried across unchanged -- it is the only thing that
    // knows what belongs here, and rewording it would put a second voice on the contract.
    const hint = (plan.unattached_refusals || []).find(
      (row) => row.path === refusal.path && row.code !== 'missing_field');
    if (hint) line.append(h('small', 'oe-starter-why', hint.message));
    line.append(button('값', 'start-field-text', key, 'oe-starter-go'),
                button('목록', 'start-field-list', key, 'oe-starter-go'),
                button('객체', 'start-field-object', key, 'oe-starter-go'));
    box.append(line);
  }
  return box;
}

function renderAuthoring(state) {
  const wrap = h('div', 'oe-authoring');
  const plan = state.authoring;
  if (!plan) {
    wrap.append(h('div', 'oe-empty', state.authoringError || (state.loading ? 'Loading' : 'None')));
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
  // 🔴 ABSENT AND UNREADABLE ARE NOT THE SAME CASE. Absent gets an OFFER; a file that
  // exists but will not parse gets its error and nothing else, because it is almost
  // certainly somebody's work with a bad comma in it. Writing a skeleton over that would
  // destroy hours and look like a feature. The server refuses on `exists()` rather than on
  // "does it parse", so this is a rendering of that rule, not a second copy of it.
  if (plan.config_source?.state === 'absent') {
    const offer = h('div', 'oe-bootstrap');
    offer.append(h('b', '', 'No configuration file'));
    offer.append(h('code', '', plan.config_source.file || ''));
    // The screen OFFERS. Writing a file is a side effect and this screen does not take
    // those on its own, so nothing happens until a person presses it.
    offer.append(h('small', '',
      `Create a starting file: setup_version + ${(plan.steps || []).length} empty sections`));
    offer.append(button('Create starting file', 'bootstrap-config', '', 'oe-bootstrap-go'));
    if (plan.bootstrapError) offer.append(h('div', 'oe-error', plan.bootstrapError));
    wrap.append(offer);
  } else if (plan.config_source?.state !== 'present') {
    wrap.append(h('div', 'oe-warning',
      `${plan.config_source?.file || plan.physical_schema_file} not readable`));
  }
  // Bucket order is the reading order: what must be done, what is still asked, what was
  // filled for you. Groups are always rendered, empty or not -- a vanished heading is
  // indistinguishable from "nothing to do".
  const prefix = writablePrefix(state);
  // Parsed once for the whole panel, not per row: the draft text is one document.
  let draftRaw = null;
  if (prefix) {
    try { draftRaw = JSON.parse(state.editorText); } catch { draftRaw = null; }
  }
  // A row is editable only when its leaf actually resolves inside the open draft AND is a
  // string. A leaf that does not resolve belongs to another declaration, and a list or an
  // object is not one input's shape -- both keep the chips they had.
  // 🔴 A CLOSED LIST GETS A DROPBOX; A NAME GETS A DATALIST. The difference is the whole
  // point of this round: a predicate or an entity is a name the operator may still be
  // COINING, so the list must suggest and never constrain -- while a role kind or an object
  // kind is one of a handful of words the code knows, and there is nothing to coin.
  //
  // Which is which is decided by DATA, not by a table written here: if a field's candidate
  // set is exactly a list the server publishes in `closed_lists()`, it is closed.
  // `closed_lists()` says it itself -- "The screen renders what this returns and owns no
  // copy" -- so a hardcoded map of "these paths are dropdowns" would be the second author
  // it warns about. Measured on the live config: 9 fields match (object_kind 5,
  // mapper_unit 2, source_unit 2).
  const closedLists = Object.entries(state.authoringSchema || {}).filter(
    ([, value]) => Array.isArray(value) && value.length
      && value.every((item) => typeof item === 'string'));
  const closedListFor = (candidates) => {
    if (!Array.isArray(candidates) || !candidates.length) return null;
    if (!candidates.every((item) => typeof item === 'string')) return null;
    const want = new Set(candidates);
    const found = closedLists.find(([, values]) => values.length === want.size
      && values.every((item) => want.has(item)));
    return found ? found[1] : null;
  };

  const editableFor = (row) => {
    if (!prefix || !draftRaw || !row.path.startsWith(prefix)) return null;
    const current = getAtPath(draftRaw, splitBundlePath(row.path).slice(2));
    const closed = closedListFor(row.candidates);
    if (typeof current === 'string') {
      return closed ? { kind: 'closed', value: current, options: closed }
                    : { kind: 'string', value: current };
    }
    // A list of names is the entity-keys shape: one input per element, each offering the
    // same candidates. Only when every element is a string -- a list holding objects is
    // not a row of name boxes, and pretending otherwise would flatten what it holds.
    if (Array.isArray(current) && current.every((item) => typeof item === 'string')) {
      return { kind: 'list', value: current };
    }
    return null;
  };
  // Claim grouping: the path already says which claim a row belongs to, so this is the
  // structure the DATA states, not a layout invented here.
  // 🔴 A PACK ALWAYS GETS ITS CLAIMS SECTION, even before `claims` exists. The validator
  // already says 「must be a non-empty object」, so asking the operator to pick a SHAPE for
  // it is asking a settled question -- the same rule as "a closed list is a dropbox, not a
  // free field", seen from the other side. What is unsettled is the NAME of each claim, and
  // that is what this section asks for.
  const draftClaims = state.draft?.target_kind === 'pack' && draftRaw
    ? (draftRaw.claims && typeof draftRaw.claims === 'object' && !Array.isArray(draftRaw.claims)
        ? draftRaw.claims : {})
    : null;
  const claimOf = (path) => {
    const found = /\.claims\.([^.]+)\./.exec(path);
    return found ? found[1] : null;
  };
  // 🔴 `$subject` OFFERS THE ROLES THIS CLAIM DEFINED, from the draft, so they are offered
  // BEFORE the claim is saved. The plan cannot answer this: its candidates for these fields
  // come from the document, and a role typed a moment ago is not in the document yet.
  const ROLE_REFERENCING = new Set(['subject', 'occurred_at', 'value']);
  const withSiblingRoles = (row) => {
    const claimId = draftClaims ? claimOf(row.path) : null;
    if (!claimId) return row;
    const leaf = row.path.split('.').pop();
    if (!ROLE_REFERENCING.has(leaf)) return row;
    const claim = draftClaims[claimId];
    const roles = claim && typeof claim.roles === 'object' && !Array.isArray(claim.roles)
      ? claim.roles : {};
    const names = Object.keys(roles).map((name) => `$${name}`);
    return names.length ? { ...row, candidates: names } : row;
  };
  const buckets = [
    ['missing', '빠짐'], ['unanswered', '미답'],
    ['derived', '파생됨 · 묻지 않음'], ['answered', '답함'],
  ];
  // Top-level keys the plan already speaks for, so the block below does not repeat them.
  const plannedTopLevel = new Set(
    plan.fields
      .filter((row) => prefix && row.path.startsWith(prefix))
      .map((row) => row.path.slice(prefix.length).split('.')[0])
      .filter(Boolean));
  const unplanned = renderUnplannedDraftFields(state, draftRaw, plannedTopLevel);
  if (unplanned) wrap.append(unplanned);
  const starters = renderMissingStarters(
    state, plan, prefix, draftRaw,
    new Set(state.draft?.target_kind === 'pack' ? ['claims'] : []));
  if (starters) wrap.append(starters);

  // A claim is one block, so its rows leave the state buckets and travel with it.
  const claimed = new Set();
  if (draftClaims) {
    const section = h('section', 'oe-bucket oe-bucket--claims');
    section.append(h('h3', '', `주장 · ${Object.keys(draftClaims).length}`));
    for (const claimId of Object.keys(draftClaims)) {
      const rows = plan.fields.filter((row) => claimOf(row.path) === claimId);
      rows.forEach((row) => claimed.add(row.path));
      const renderRow = (row) => {
        const shown = withSiblingRoles(row);
        return renderAuthoringRow(shown, state.expandedFields, editableFor(shown));
      };
      const key = `claim:${state.draft.target_id}:${claimId}`;
      // 🔴 AN EMPTY CLAIM OWES EVERYTHING, and the plan cannot say so: a claim with no
      // body has no rows, so "does any row still owe something" read as "nothing owed" and
      // folded the claim shut the instant it was named. The operator typed `hello` and got
      // 「hello · 채워짐」 -- the opposite of true. Emptiness is asked of the DRAFT, which is
      // the only thing that knows about a claim that was named a second ago.
      const body = draftClaims[claimId];
      const empty = !body || typeof body !== 'object' || Array.isArray(body)
        || !Object.keys(body).length;
      // 🔴 AND A CLAIM THE PLAN HAS NEVER SEEN STAYS OPEN. The plan describes the FILE, so
      // for a claim named a moment ago it has no rows at all -- and "no row still owes
      // anything" is then vacuously true, which folded the claim shut the instant it gained
      // its first role. `rows.length === 0` is the honest reading: nothing is known about
      // this claim yet, so it cannot be reported as finished.
      const owes = empty || !rows.length || rows.some(
        (row) => row.remaining || row.conflicts || row.refusals?.length);
      const fold = {
        key,
        open: owes || state.expandedFields.includes(key),
        reason: owes ? '' : '채워짐',
      };
      section.append(renderClaimBlock(
        state, state.draft.target_id, claimId, draftClaims[claimId], rows, renderRow,
        closedListFor, fold, prefix.replace(/\.$/, ''), draftRaw));
    }
    if (!Object.keys(draftClaims).length) {
      section.append(h('div', 'oe-empty', 'None defined'));
    }
    // 🔴 A CLAIM HAS TO BE NAMEABLE, or `claims: {}` is a dead end -- measured: an empty
    // claims map makes the validator name NOTHING, so the screen falls silent exactly
    // where it just told you to start. Free text is right here for the same reason it is
    // right on the naming row: the operator is coining a name nothing else holds yet.
    const naming = h('div', 'oe-claim-new');
    const input = h('input', 'oe-claim-new-id');
    input.type = 'text';
    input.placeholder = '주장 id · e.g. register';
    input.setAttribute('aria-label', '새 주장 id');
    naming.append(input, button('+ 주장', 'add-claim', '', 'oe-claim-new-go'));
    section.append(naming);
    wrap.append(section);
  }
  for (const [stateId, label] of buckets) {
    const rows = plan.fields.filter(
      (row) => row.state === stateId && !claimed.has(row.path));
    const section = h('section', `oe-bucket oe-bucket--${stateId}`);
    section.append(h('h3', '', `${label} · ${rows.length}`));
    if (!rows.length) section.append(h('div', 'oe-empty', 'None defined'));
    for (const row of rows) {
      section.append(renderAuthoringRow(row, state.expandedFields, editableFor(row)));
    }
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
  // 🔴 ABSENCE IS NOT PROGRESS. This read `불러오는 중` whenever there was no hash, so an
  // empty config announced a load that would never finish and the operator waited for it.
  // In-flight and absent are different states and only one of them ends -- `state.loading`
  // already tells them apart, so the fallback asks it instead of assuming.
  const snap = state.activeSnapshot?.snapshot_hash?.slice(0, 8)
    || (state.loading ? 'Loading' : 'None');
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
  // 🔴 ABOVE THE TREE, NOT INSIDE IT. One of these can stop EVERYTHING from loading, and
  // burying it among per-declaration tags sends a person to fix declarations while the
  // cause sits in a different layer entirely.
  for (const problem of state.configProblems || []) {
    const banner = h('div', 'oe-error');
    banner.append(h('code', '', problem.path), h('span', '', problem.message));
    windowEl.append(banner);
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
  // 🔴 A CREATE DRAFT IS THE SUBJECT, AND NOTHING AROUND IT BELONGS TO IT YET.
  //
  //     lot 생성 후 wafer 생성시 여전히 lot으로 떠있는상태로 key 입력만 초기화됨
  //
  // The owner created `wafer@1` and the screen kept every panel pointed at `lot@1` --
  // title, breadcrumb, paths, integrity, 사용처 -- with only the key box belonging to the
  // new draft. Counted in the panel's DOM at that moment: `lot@1` 16 times, `wafer@1`
  // ZERO. An empty key list under a heading that says `lot@1` does not read as "a new
  // declaration"; it reads as "lot's keys were wiped", which is what was reported.
  //
  // The cause is upstream and is not a bug: a create target is NOT in the snapshot, so the
  // re-read asks for no selection and the server picks one -- and any declaration it picks
  // is the wrong subject, because the right one does not exist yet.
  //
  // 🔴 SO THE PANELS ARE NOT DRAWN, NOT FILLED WITH A PLACEHOLDER. Integrity, 사용처
  // and the reference paths have nothing to say about a declaration that is not declared;
  // an empty box with invented copy would be a second thing to read wrong. Absence is
  // rendered as absence.
  if (state.draft?.creates_declaration) {
    workspace.append(renderRaw(state));
    // The rows are inside `renderRaw`'s editor now, so nothing is appended here.
  } else if (state.selection) {
    workspace.append(renderBreadcrumb(state), renderPaths(state));
    const detail = h('section', 'oe-detail-grid');
    detail.append(renderInspector(state), renderIntegrity(state));
    workspace.append(detail);
  } else if (state.draft) {
    // An open draft is the thing being worked on; show it even though nothing is selected.
    workspace.append(renderRaw(state));
    // The rows are inside `renderRaw`'s editor now, so nothing is appended here.
  } else if (state.authoring) {
    workspace.append(renderAuthoring(state));
  } else {
    workspace.append(h('div', 'oe-empty', state.loading ? '불러오는 중…' : '표시할 정의가 없습니다.'));
  }
  main.append(workspace);
  windowEl.append(main);
  replace(root, windowEl);
}
