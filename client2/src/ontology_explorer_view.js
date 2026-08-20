import { isDraftRevisionEditable } from './ontology_explorer_store.js';
import { commitTree } from './dom_patch.js';
import { splitBundlePath, getAtPath } from './ontology_path.js';
import {
  declarationShape, fieldApplies, memberPath, membersOf,
} from './ontology_skeleton.js';

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
  // 🔴 THE DEFAULT LIST IS TOP-LEVEL DECLARATIONS ONLY, AND THE TEST IS THE PATH'S LENGTH.
  // A `mapping` or a `binding` is not a declaration -- its id is synthesised from a pointer
  // (`<profile>#mapping:<id>#binding:<role>`), it lives INSIDE a profile, and
  // `authorable_bundle_path` refuses it: "cannot be created or removed on this screen".
  // Measured on the owner's config: 62 nodes = 20 declarations + 42 positions, and those 42
  // were taking three and four lines each in a 240px column.
  //
  // Not a list of kinds to exclude. `owning_section`'s own comment says why -- "THE
  // DISCRIMINATOR IS THE SECTION, NOT THE KIND ... length 2 is a top-level declaration,
  // longer is nested" -- and a blacklist leaks the day another nesting appears. Length
  // covers `claim` and `role` and whatever comes next without being told about them.
  //
  // The positions are not lost: the tree in the middle draws them inside their declaration,
  // which is where they live, and a SEARCH still lists them so they can be found by name.
  // 🔴 NOT `json_pointer.length === 2`, WHICH IS THE SAME RULE MEASURED IN THE WRONG UNIT.
  // That is true of `ledger_config.json`, where a declaration is `/<section>/<id>` -- but a
  // `table` comes from `table_config.json`, whose declarations sit at `/dt_log`, ONE segment.
  // The literal length test dropped both physical tables off the index. Measured before
  // shipping it: pointer depths across the owner's config are 1×2, 2×18, 4×14, 6×28.
  //
  // A position is exactly a node whose path EXTENDS another node's path, so that is the test.
  // It needs no length, no kind and no file: it stays true for `claim`, for `role`, and for
  // whatever file is added next.
  const owned = state.items.map((row) => row.config_path).filter(Boolean);
  const declarationOnly = (item) => {
    const path = item.config_path;
    if (!path) return true;
    return !owned.some((other) => other !== path && path.startsWith(`${other}/`));
  };
  const searching = Boolean(state.query.trim());
  const listed = searching ? state.items : state.items.filter(declarationOnly);
  // 🔴 THE COUNT COUNTS WHAT IS ON SCREEN. It used to say `state.total`, every node in the
  // index -- which was true of the index and false of the list, and would now read 62 above
  // 20 rows. A heading that disagrees with the list under it is the quiet kind of lie.
  nav.append(h('div', 'oe-tree-title',
                searching ? `검색 결과 · ${listed.length}개` : `선언 · ${listed.length}개`));
  const groups = new Map();
  for (const item of listed) {
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
  // 🔴 THE TOTAL IS SAID ONCE, AT THE TOP, and each layer says only its own share. The
  // owner's mockup (1b) leads with a single 「N REMAINING」, and that is Rule 7 applied to
  // the spine: a number the operator reads to decide WHETHER to look, before six numbers
  // telling him where.
  const totalRemaining = plan.steps.reduce((sum, step) => sum + (step.remaining || 0), 0);
  // 🔴 AND WHEN EVERY LAYER IS COMPLETE, THAT IS ONE FACT, NOT SIX. Counted on the owner's
  // live config: `Complete` appeared six times, each of them true and none of them adding
  // anything to the one before. The sentence belongs to the group.
  const allDone = plan.steps.length > 0
    && plan.steps.every((step) => step.declared && !step.remaining);
  const head = h('div', 'oe-spine-head');
  head.append(h('span', 'oe-spine-title', '셋업'));
  head.append(h('span', 'oe-spine-count',
                allDone ? `${plan.steps.length} layers · complete`
                        : `${totalRemaining} remaining`));
  bar.append(head);
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
    } else if (step.declared && !allDone) {
      // Said per layer only while the layers DISAGREE. When they all read the same, the
      // head above has already said it once and repeating it here is six copies of one fact.
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
    // 🔴 THE WORDS ARE NOT NEW. Each is already this screen's word for the same thing --
    // 「파생됨 · 묻지 않음」 on the bucket heading, 「강제 · …」 on the row's own action line,
    // 「비움」 on an empty list chip, 「후보」 across the client. Nothing here was translated
    // into existence; the state column had simply been left in the language the mockup did
    // not rule on, so 「선언됨」 stood beside four English words in one column.
    return { open: false, reason: row.disposition === 'grammar_requires_it' ? '강제' : '파생됨' };
  }
  // Read live. `candidates` is the list the server sent for THIS render.
  if (Array.isArray(row.candidates) && row.candidates.length === 1) {
    return { open: false, reason: '단일 후보' };
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
  if (row.state === 'answered') return { open: false, reason: '선언됨' };
  if (row.state === 'unanswered') return { open: false, reason: '비움' };
  return { open: true, reason: '' };
}

function renderAuthoringRow(row, expanded = [], editable = null, bare = false) {
  const fold = foldDecision(row, expanded);
  const card = h('div', `oe-field is-${row.state}${fold.open ? '' : ' is-folded'}`
                        + (bare ? ' is-bare' : ''));
  card.dataset.key = `field:${row.path}`;
  const head = h('div', 'oe-field-head');
  // In the tree the name lives in the row's own label column, at its own indent. Repeating
  // it inside the card would put the same word twice on one line and, worse, at a second
  // x-position -- the thing the mockup's fixed columns exist to stop.
  if (!bare) head.append(h('b', '', row.label));
  head.append(h('i', `oe-tier oe-tier--${row.tier}`, row.tier));
  card.append(head);
  if (!fold.open) {
    // The folded line is one row: value, and WHY it folded. A fold whose reason is
    // invisible reads as the screen deciding for the operator, which is the exact thing
    // the acceptance bar forbids -- so the reason is rendered, not implied.
    const line = button('', 'toggle-field', row.path, 'oe-field-folded');
    line.setAttribute('aria-expanded', 'false');
    line.append(h('code', 'oe-folded-value', formatValue(row.value)));
    // 🔴 THE REASON BELONGS TO WHICHEVER COLUMN OWNS IT. In the tree the row's state column
    // already says 「선언됨」, so repeating it here put the same word at two x-positions and
    // rendered as one run of text -- `dt_log선언됨`. Outside the tree there IS no state
    // column, so the reason stays. `bare` already carries that distinction; it does not need
    // a second flag. The GROUND line is untouched -- it says why the value is what it is,
    // which the state column never says.
    if (!bare) line.append(h('i', 'oe-folded-why', fold.reason));
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
// The form, generated from the skeleton. One function for every declaration kind.
//
// 🔴 IT ASKS WHAT THE NODE IS, NEVER WHAT THE DECLARATION IS. There is no branch here for
// packs, none for sources, none "just for emit" -- the owner's finish line for this round
// is 「다른 스키마 운영 환경에서 코드 0줄, 선언 교체만으로 발화」, and a renderer that asks
// which kind it is looking at needs code again for the next schema. Add a field to
// `ledger_skeleton.json` and it appears here; take it out and it stops. That is the test.
//
// This replaced three hand-written builders -- a claim block, a starter list, and a
// leftover-fields block -- which between them knew `claims`, `roles`, `emit`, `mappings`
// and `pack` by name and still could not express `emit.object.entity`, so the owner's own
// `lot-lineage@1` was unbuildable through the form.
//
// 🔴 THE PLAN STILL WINS WHEREVER IT HAS A ROW. The skeleton describes what EXISTS; the
// authoring plan describes what the FILE holds, and only its rows carry candidates,
// refusals and grounds. So a leaf the plan speaks for is rendered by the plan, and the
// skeleton fills what the plan cannot see -- which is everything absent.
//
// CRUD is read off the node kind, per the owner's 「폼은 모두 crud 가능해야함」:
//   map     name a member / list them / edit inside / REMOVE that member
//   record  its fields are fixed, so there is nothing to add or remove -- only edit
//   leaf    edit; and clear it, when the skeleton says the field is optional
// The tree. One renderer walks the skeleton, and every declaration in the setup is drawn
// by it -- owner, mockup 6b: the tree is what makes the screen answer to ANY layer.
//
// 🔴 IT ASKS WHAT THE NODE IS, NEVER WHICH DECLARATION IT IS IN. A source's `driver` four
// deep and a profile's `mappings[0].bind.subject` five deep come out of these same
// functions. That is what makes 6b fit where 1b did not: 1b's "claims in pack" column
// existed for only two of the seven kinds (measured -- pack->claims, profile->mappings; the
// other five have no such layer), so it needed a branch per kind. A tree needs none.
//
// 🔴 A ROW IS THREE COLUMNS: label | value | state. The indent moves the LABEL column only
// (-16px per depth) while the state column keeps a fixed width, so value and state stand on
// the same vertical line at every depth. Indenting the whole row would step the columns
// sideways instead, which is what the owner's 「잘 정돈되게」 rules out.

/** The plan paths that still owe something -- the server's predicate, not a second one. */
function attentionPaths(plan) {
  const hot = [];
  for (const row of plan.fields || []) {
    if (row.remaining || row.conflicts || row.refusals?.length) hot.push(row.path);
  }
  return hot;
}

/** Does anything at or under this absolute path still owe something? */
function needsAttention(hot, absolute) {
  return hot.some((item) => item === absolute
    || item.startsWith(absolute + '.') || item.startsWith(absolute + '['));
}

function treeRow(depth, label, extras, valueEl, stateEl, cls) {
  const row = h('div', 'oe-node-row' + (cls ? ' ' + cls : ''));
  // Depth is DATA; the formula turning it into a width lives in the stylesheet.
  row.style.setProperty('--oe-depth', String(depth));
  const name = h('div', 'oe-node-label');
  name.append(h('span', 'oe-node-name', label));
  for (const extra of extras || []) name.append(extra);
  row.append(name);
  const value = h('div', 'oe-node-value');
  if (valueEl) value.append(valueEl);
  row.append(value);
  const state = h('div', 'oe-node-state');
  if (stateEl) state.append(stateEl);
  row.append(state);
  return row;
}

/** One node: its own row, and -- when it is a branch that is open -- its children below. */
function renderSkeletonForm(context, node, path, value, depth = 0, label = null) {
  const shape = context.deref(node);
  if (!shape) return null;
  if (shape.kind === 'leaf') return renderTreeLeaf(context, shape, path, value, depth, label);
  const open = !path || needsAttention(context.hot, context.absolute(path))
    || context.expanded.includes(path);
  const box = h('div', 'oe-node');
  const kind = h('i', 'oe-node-badge', shape.kind === 'map' ? 'MAP' : 'RECORD');
  const children = shape.kind === 'map'
    ? renderSkeletonMap(context, shape, path, value, depth)
    : renderSkeletonRecord(context, shape, path, value, depth);
  {
    // 🔴 A FOLD SHOWS ITS COUNT. Folding without saying how many were folded is deleting
    // with extra steps -- the mockup's rule is 「접힌 것은 개수를 보인다」, and it is the
    // same fault this round has been removing everywhere else: an absence nobody can tell
    // apart from an emptiness.
    const hidden = children.childElementCount;
    const toggle = path
      ? button(open ? '−' : '접힘 · ' + hidden, 'toggle-field', path,
               open ? 'oe-node-fold' : 'oe-node-folded')
      : null;
    if (toggle) toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    box.append(treeRow(depth, label || path, [kind], null, toggle,
                       (path ? 'is-branch' : 'is-branch is-root')
                       + (open ? '' : ' is-folded')));
  }
  if (open) box.append(children);
  return box;
}

function renderSkeletonRecord(context, node, path, value, depth) {
  const box = h('div', 'oe-node-children');
  const held = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  for (const field of node.fields || []) {
    const at = path ? path + '.' + field.key : field.key;
    const current = held[field.key];
    if (!fieldApplies(field, held, current)) continue;
    // Always one level in: the node drawing these children has its own row now, including
    // the root. While the root drew no row, its fields had to stay at its depth or the whole
    // declaration would have been indented under nothing.
    const drawn = renderSkeletonForm(context, field.node, at, current, depth + 1,
                                     field.label || field.key);
    if (!drawn) continue;
    // An optional field the document holds can be taken back out. The tree row owns the
    // chrome now, so the control rides in the label column beside the name.
    if (field.required === false && current !== undefined) {
      const slot = drawn.querySelector('.oe-node-label');
      if (slot) slot.append(button('−', 'form-clear', at, 'oe-form-remove'));
    }
    box.append(drawn);
  }
  return box;
}

function renderSkeletonMap(context, node, path, value, depth) {
  const box = h('div', 'oe-node-children');
  // A plan row ABOUT the map itself says what the grammar expects OF it -- which qualifier
  // slots a predicate opens, for instance. It stays at the top of the block.
  const own = context.planRow(path);
  if (own) {
    // 🔴 THREE ARGUMENTS, NOT TWO. `renderRow` is `(row, node, bare)`, so the bare `true`
    // that used to sit here landed in `node` and left `bare` false -- these four rows drew
    // their own card head while every sibling was a flat line, and said their state twice.
    // The other call site got the third argument in the same commit; this one did not.
    // Passing `bare` also means the row must supply the state element itself, exactly as
    // `renderTreeLeaf` does -- otherwise the only place that stated it disappears.
    const fold = foldDecision(own, context.expanded);
    const state = h('i', 'oe-tier oe-tier--' + own.tier,
                    fold.open ? own.tier : fold.reason);
    box.append(treeRow(depth + 1, '이 자리', [],
                       context.renderRow(own, null, true), state));
  }
  const members = membersOf(node, value);
  for (const key of members) {
    const at = memberPath(path, key, node.keyed_by);
    const drawn = renderSkeletonForm(
      context, node.of, at,
      node.keyed_by === 'index' ? (value || [])[key] : (value || {})[key],
      depth + 1, String(key));
    if (!drawn) continue;
    const slot = drawn.querySelector('.oe-node-label');
    if (slot) slot.append(button('−', 'form-remove', at, 'oe-form-remove'));
    box.append(drawn);
  }
  const naming = h('div', 'oe-form-new');
  if (node.keyed_by === 'index') {
    naming.append(button('+ ' + (node.member || '항목'), 'form-append', path, 'oe-form-add'));
  } else {
    const input = h('input', 'oe-form-new-id');
    input.type = 'text';
    input.placeholder = node.member || '이름';
    input.dataset.for = path;
    input.setAttribute('aria-label', (node.member || path) + ' 새 이름');
    naming.append(input, button('+ ' + (node.member || '항목'), 'form-name', path,
                                'oe-form-add'));
  }
  box.append(treeRow(depth + 1, '', [], naming, null, 'is-new'));
  return box;
}

/** A leaf row. The control itself is unchanged -- only the chrome around it is new. */
function renderTreeLeaf(context, node, path, value, depth, label) {
  const planned = context.planRow(path);
  const control = planned
    ? context.renderRow(context.suggest(planned, node, path), node, true)
    : renderSkeletonLeaf(context, node, path, value);
  const box = h('div', 'oe-node');
  let state = null;
  let cls = '';
  if (planned) {
    const fold = foldDecision(planned, context.expanded);
    state = h('i', 'oe-tier oe-tier--' + planned.tier,
              fold.open ? planned.tier : fold.reason);
    cls = planned.remaining ? 'is-remaining'
      : planned.refusals && planned.refusals.length ? 'is-refused' : '';
  }
  box.append(treeRow(depth, label || path, [], control, state, cls));
  return box;
}

// The control for an UNPLANNED leaf. A leaf the plan speaks for is drawn by the plan row
// instead (see `renderTreeLeaf`) -- that row is the only thing carrying candidates,
// refusals and grounds, so the skeleton fills exactly what the plan cannot see.
function renderSkeletonLeaf(context, node, path, value) {
  if (node.hint === 'flag') {
    const box = h('input', 'oe-role-required');
    box.type = 'checkbox';
    box.checked = value === true;
    box.dataset.action = 'edit-shape-flag';
    box.dataset.value = path;
    box.setAttribute('aria-label', path);
    return box;
  }
  const text = typeof value === 'string' || typeof value === 'number' ? String(value) : '';
  if (node.hint === 'choice') {
    const options = context.schema[node.list] || [];
    const select = h('select', 'oe-field-select');
    select.dataset.action = 'edit-shape';
    select.dataset.value = path;
    select.setAttribute('aria-label', path);
    // The value in the document is always an option, recognised or not -- rendering must
    // never rewrite the file. An absent value shows blank, not as the first choice.
    for (const item of (options.includes(text) ? options : [text, ...options])) {
      const option = h('option', '', item);
      option.value = item;
      if (item === text) option.selected = true;
      select.append(option);
    }
    return select;
  }
  const input = h('input', 'oe-field-input');
  // 🔴 A NUMBER FIELD SAYS SO, BECAUSE OTHERWISE IT CANNOT BE FILLED AT ALL. Typing 1 into a
  // text box stores "1", the validator refuses it (`invalid_version -- must be a positive
  // integer`), and typing it again produces the same string: a new mapper or preparer could
  // only be completed in the raw JSON editor. Packs hid this -- they hold no integer.
  //
  // The declaration is what carries the type, not this file: `hint: number` sits in
  // `ledger_skeleton.json` beside `hint: flag`, which has always meant boolean. So this adds
  // no second author and no branch that knows a field by name -- the same three lines would
  // type a field this screen has never heard of.
  input.type = node.hint === 'number' ? 'number' : 'text';
  if (node.hint === 'number') input.dataset.number = 'true';
  input.value = text;
  input.dataset.action = 'edit-shape';
  input.dataset.value = path;
  input.setAttribute('aria-label', path);
  const suggestions = node.hint === 'ref' ? context.declared(node.section)
    : node.hint === 'role' ? context.rolesNear(path, node.from) : [];
  if (suggestions.length) {
    const listId = `oe-dl-${path.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
    const list = h('datalist');
    list.id = listId;
    for (const item of suggestions) {
      const option = h('option');
      option.value = item;
      list.append(option);
    }
    input.setAttribute('list', listId);
    const wrap = h('span', 'oe-form-suggested');
    wrap.append(input, list);
    return wrap;
  }
  return input;
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

  const editableFor = (row, node) => {
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
    // 🔴 A FIELD NOBODY HAS FILLED IN YET IS STILL A FIELD. Everything above asks what the
    // draft HOLDS, so an absent value produced no control at all -- and the skeleton hands
    // this row over precisely because the plan knows the path, which left the empty case
    // owned by the one renderer that cannot draw it. Measured on a source built from
    // nothing: `relation`, `profile_id` and `driver.unit` had no input anywhere, so a new
    // source could not be given the two names that identify it. Packs hid this too; they
    // have no plan-owned leaf.
    //
    // Kept on the plan's row rather than falling back to the skeleton's own control,
    // because the row is what carries the candidates and the refusal -- `relation` offers
    // the tables, `profile_id` the profiles. Losing those would trade one silence for another.
    //
    // Only where the person is the one who owes the value: `derived` is the system's to
    // write, and an input there would invite a fight with whatever computes it.
    // 🔴 ONLY FOR A LEAF, AND THE SKELETON IS WHAT SAYS SO. Without the node this offered a
    // text box for every absent field, including the list ones -- typing into `subjects` wrote
    // `"Lot@1"` where `["Lot@1"]` belongs, a wrong type in the owner's file put there by the
    // screen. Which is the same fault this round has been closing, introduced by the fix for
    // it. A map or a list already has its own control (a member namer, an append), so this
    // fallback has nothing to add there anyway.
    if (node && node.kind === 'leaf' && current === undefined
        && (row.state === 'missing' || row.state === 'unanswered')) {
      return closed ? { kind: 'closed', value: '', options: closed }
                    : { kind: 'string', value: '' };
    }
    return null;
  };
  const buckets = [
    ['missing', '빠짐'], ['unanswered', '미답'],
    ['derived', '파생됨 · 묻지 않음'], ['answered', '답함'],
  ];

  // ---- the form, generated ------------------------------------------------------
  //
  // 🔴 WHICH DECLARATION THIS IS NEVER ASKED. The section name comes off the payload
  // (`authorable_kinds`), the shape comes off the skeleton, and everything below walks
  // those two. That is the owner's finish line for the round -- 「다른 스키마 운영
  // 환경에서 코드 0줄」 -- and it is why the pack-shaped code that used to live here
  // (claims, roles, emit, `ROLE_REFERENCING`) is gone rather than extended.
  const drawn = new Set();
  const skeleton = state.authoringSchema?.skeleton || null;
  const section = (state.authoringSchema?.authorable_kinds || [])
    .find((row) => row.id === state.draft?.target_kind)?.section || null;
  const bodyNode = skeleton && section ? declarationShape(skeleton, section) : null;
  const base = prefix.replace(/\.$/, '');
  const planRow = (path) => {
    const row = plan.fields.find((item) => item.path === `${base}.${path}`);
    if (row) drawn.add(row.path);
    return row;
  };
  // A `$role` is spelled by the ROLE, not by the endpoint: `$r` when it is required and
  // `$r?` when it is not, which is the server's `_role_reference` and the only spelling
  // the validator accepts. The skeleton says where to look (`from`), so this knows the
  // word "roles" only because the document used it.
  const rolesNear = (path, from) => {
    const steps = splitBundlePath(path);
    for (let depth = steps.length - 1; depth >= 0; depth -= 1) {
      const holder = getAtPath(draftRaw, steps.slice(0, depth));
      const roles = holder && typeof holder === 'object' && !Array.isArray(holder)
        ? holder[from] : null;
      if (roles && typeof roles === 'object' && !Array.isArray(roles)) {
        return Object.keys(roles).map(
          (name) => (roles[name]?.required === true ? `$${name}` : `$${name}?`));
      }
    }
    return [];
  };
  const context = {
    schema: state.authoringSchema || {},
    planRow,
    deref: (node) => (node && node.use ? (skeleton.defs || {})[node.use] : node),
    declared: (name) => (state.authoring?.sections || {})[name] || [],
    rolesNear,
    // 🔴 THE ROLES A CLAIM DEFINED A MOMENT AGO ARE OFFERED BEFORE IT IS SAVED. The plan
    // row's own candidates come from the DOCUMENT, so a role typed just now is not among
    // them -- and this screen exists so that nothing has to be saved to be seen.
    renderRow: (row, node, bare = false) => renderAuthoringRow(
      row, state.expandedFields, editableFor(row, node), bare),
    // The tree reads folding off the SAME rows the layer counts are computed from, so a
    // branch can never sit folded over a field the spine is still counting as remaining.
    hot: attentionPaths(plan),
    expanded: state.expandedFields || [],
    absolute: (path) => (base ? base + '.' + path : path),
    suggest: (row, node, path) => {
      if (!node || node.hint !== 'role') return row;
      const names = rolesNear(path, node.from);
      return names.length ? { ...row, candidates: names } : row;
    },
  };
  if (bodyNode && draftRaw) {
    const body = h('section', 'oe-bucket oe-bucket--form');
    const form = renderSkeletonForm(context, bodyNode, '', draftRaw, 0,
                                   state.draft.target_id);
    if (form) body.append(form);
    wrap.append(body);
  }

  // 🔴 AN EMPTY BUCKET SAYS NOTHING FOUR TIMES. All four are empty on a declaration that
  // was just created, so the screen answered 「None defined」 four times over and buried the
  // one thing that mattered -- the form beside them. The old rule ("always render, a
  // vanished heading is indistinguishable from nothing to do") is kept where it is TRUE:
  // if the whole panel would be silent, one line still says so. It is only the repetition
  // that goes.
  const shown = buckets.map(([stateId, label]) => {
    const rows = plan.fields.filter(
      (row) => row.state === stateId && !drawn.has(row.path));
    return { stateId, label, rows };
  });
  const anythingToShow = shown.some((bucket) => bucket.rows.length) || Boolean(bodyNode);
  for (const { stateId, label, rows } of shown) {
    if (!rows.length && anythingToShow) continue;
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
  top.append(h('div', 'oe-brand', 'Ontology Config Explorer'));
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
  // 🔴 THE PLACEHOLDER ADVERTISES A KEY, SO THE KEY IS BOUND. The mockup writes
  // 「이름으로 이동  /」 and a screen that says `/` without listening for it is telling the
  // operator about something that is not there -- the exact fault this round keeps removing.
  // The listener lives in the controller; this line is only the promise.
  search.placeholder = '이름으로 이동  /';
  search.value = state.query;
  search.dataset.action = 'search';
  searchLabel.append(search);
  // Mockup order: title · draft id · search, and everything after is pushed right. The
  // history arrows are that "everything after" here, so they carry the auto margin now.
  top.append(searchLabel, history);
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
  // 🔴 THE LAYERS ARE THE FIRST COLUMN, not a strip above the work. Owner's ruling on the
  // mockup: 「1b의 구조만 가져와」 — 1b makes the six layers the primary axis, so the screen
  // reads 층 → 선언 → 폼 left to right instead of asking the operator to look up at a bar
  // and back down. The bar's data is unchanged; only where it sits is.
  main.append(renderTree(state));
  const workspace = h('main', 'oe-workspace');
  // Always first, always one line: "지금 어느 걸음인가" is the one element the owner
  // asked to keep and strengthen, and it must survive the no-selection case too --
  // that is the from-scratch entry, where it is the only thing on screen.
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
    workspace.append(renderBreadcrumb(state));
    const detail = h('section', 'oe-detail-grid');
    // Integrity is the body's third column now, not a card inside the workspace.
    // Leaving both put the same panel on screen twice, side by side, saying the same
    // sentence -- seen in the browser, not in the diff.
    detail.append(renderInspector(state));
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
  // 6b's third column. The mockup puts the reference flow here, not across the top of the
  // work -- owner: 「위에 플로우도 목업에는 오른쪽 패널에 있는데 좀 작게하고」. At 330px the
  // boxes cannot stand side by side, so "smaller" is a vertical stack at the mockup's own
  // 11px, which is what its right panel does.
  //
  // What the flow SAYS is unchanged, and so is clicking a node -- only where it sits.
  const side = h('div', 'oe-side');
  if (state.selection) side.append(renderPaths(state));
  side.append(renderIntegrity(state));
  main.append(side);
  // 🔴 THE SPINE IS A BAND ABOVE THE BODY, NOT A COLUMN INSIDE IT. It was appended into
  // `.oe-main` for 1b, where the layers were the left column; 6b makes them a horizontal
  // band and the CSS was moved to match, but this line was not -- so the band was laid out
  // as `repeat(6, 1fr)` inside a 240px grid slot, 40px per layer, and every layer label
  // broke one character per line. Two arrangements from two mockups, meeting in one file.
  windowEl.append(renderStepBar(state));
  windowEl.append(main);
  replace(root, windowEl);
}
