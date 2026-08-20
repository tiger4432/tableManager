// Ontology Config Explorer state contract.
// The reducer is deliberately DOM-free: one response may describe exactly one compiled
// context, and late responses can never overwrite a newer selection/search/draft request.

export const initialExplorerState = Object.freeze({
  activeSnapshot: null,
  viewContext: null,
  selection: null,
  invalid: {},
  configProblems: [],
  items: [],
  nodes: [],
  outbound: [],
  usedBy: [],
  usedByTotal: 0,
  outboundTotal: 0,
  referencesTruncated: false,
  currentPath: null,
  changes: [],
  edgeChanges: [],
  integrity: [],
  query: '',
  page: 1,
  total: 0,
  detailTab: 'definition',
  navigation: Object.freeze({ back: [], forward: [] }),
  draft: null,
  viewPreference: 'active',
  editorText: '',
  dirty: false,
  loading: false,
  error: null,
  removedSelection: null,
  requestGeneration: 0,
  // Authoring plan and the closed lists it offers. Deliberately OUTSIDE the compiled
  // context contract above: the plan reads the authoring file, not a snapshot, because
  // it has to answer while the bundle is half-written and `/view` cannot compile.
  authoring: null,
  authoringSchema: null,
  authoringError: null,
  // The declaration being NAMED, before the server has a draft for it. Local only, and
  // deliberately not merged into `items`: `items` mirrors what the server has, and a name
  // nobody has accepted yet is not that. Conflating them is how a create that was refused
  // goes on showing in the tree as if it existed.
  newDeclaration: null,
  // Rows the operator has opened by hand, by path.
  //
  // 🔴 IN STATE, NOT IN THE DOM. `<details open>` would be the obvious way and it is the
  // wrong one here: the commit step syncs attributes from the freshly built tree, so an
  // `open` the browser set would be removed on the next render and the row would fold
  // itself shut while being read. Keeping it here means a re-render cannot close it.
  expandedFields: [],
});

const CONTEXT_COLLECTIONS = [
  'items', 'nodes', 'outbound', 'used_by', 'integrity',
  'changes', 'edge_changes',
];

export function assertOneContext(payload) {
  const mismatch = (message) => {
    const error = new Error(message);
    error.code = 'context_mismatch';
    throw error;
  };
  const token = payload?.context_token;
  if (!token || payload?.view_context?.context_token !== token) {
    mismatch('응답의 snapshot context가 일치하지 않습니다.');
  }
  // 🔴 AN ABSENT SELECTION IS NOT A MISMATCHED ONE, and the difference is the whole first
  // screen of a fresh config. On an empty config `selection` is `null`, so
  // `payload?.selection?.context_token` is `undefined`, `undefined !== token` is true, and
  // this refused the response before anything could be rendered -- 「선택 항목이 다른
  // snapshot에서 왔습니다」 about a selection that does not exist.
  //
  // The rule is about objects that CARRY a token and disagree with it. Nothing that does
  // not exist can disagree. The server-side copy of this same rule had the same defect and
  // was fixed in ce81568; this is the second copy, and looking for it only after the
  // owner hit it is the lesson worth keeping.
  if (payload?.selection != null && payload.selection.context_token !== token) {
    mismatch('선택 항목이 다른 snapshot에서 왔습니다.');
  }
  for (const field of CONTEXT_COLLECTIONS) {
    for (const item of payload?.[field] || []) {
      if (item.context_token !== token) {
        mismatch(`${field}에 다른 snapshot 항목이 섞였습니다.`);
      }
    }
  }
  if (payload?.draft) {
    if (payload.draft.context_token !== token) mismatch('초안 메타데이터가 다른 context입니다.');
    for (const error of payload.draft.validation_errors || []) {
      if (error.context_token !== token) mismatch('초안 오류가 다른 context입니다.');
    }
  }
  return token;
}

function freezeNav(back, forward) {
  return Object.freeze({ back: Object.freeze(back), forward: Object.freeze(forward) });
}

export function reduceExplorerState(state = initialExplorerState, action) {
  switch (action.type) {
    case 'REQUEST_STARTED':
      return { ...state, loading: true, error: null, requestGeneration: action.generation };
    case 'REQUEST_FAILED':
      if (action.generation !== state.requestGeneration) return state;
      if (action.code === 'unknown_selection' || action.code === 'context_mismatch') {
        return {
          ...state, loading: false, error: action.message, selection: null,
          nodes: [], outbound: [], usedBy: [], integrity: [],
          currentPath: null,
          removedSelection: action.selection
            ? { key: action.selection, status: 'removed_or_unresolved' } : null,
        };
      }
      return { ...state, loading: false, error: action.message };
    case 'RESPONSE_RECEIVED': {
      if (action.generation !== state.requestGeneration) return state;
      assertOneContext(action.payload);
      const p = action.payload;
      if (action.expectedSelection && p.selection?.key !== action.expectedSelection) {
        const error = new Error('요청한 selection과 응답 selection이 일치하지 않습니다.');
        error.code = 'context_mismatch';
        throw error;
      }
      return {
        ...state,
        activeSnapshot: p.active_snapshot,
        viewContext: p.view_context,
        selection: p.selection,
        // What could not be read, keyed the way the tree keys nodes, and the problems no
        // declaration can be blamed for. Both come from the server; the screen holds no
        // opinion of its own about what resolves.
        invalid: p.invalid || {},
        configProblems: p.config_problems || [],
        items: p.items || [],
        nodes: p.nodes || [],
        outbound: p.outbound || [],
        usedBy: p.used_by || [],
        usedByTotal: p.used_by_total || 0,
        outboundTotal: p.outbound_total || 0,
        referencesTruncated: Boolean(p.references_truncated),
        // 🔴 THE ROOT PATH IS A PATH TO THE SELECTION, so with nothing selected there is
        // no path -- not an empty one. This ran on EVERY response, so on an empty config
        // it threw before a single node was rendered.
        currentPath: action.route || (p.selection ? {
          path_id: 'root', node_keys: [p.selection.key], edge_ids: [],
        } : null),
        changes: p.changes || [],
        edgeChanges: p.edge_changes || [],
        integrity: p.integrity || [],
        page: p.page || 1,
        total: p.total || 0,
        draft: p.draft || null,
        viewPreference: p.view_context?.mode === 'draft_preview' ? 'draft_preview' : 'active',
        // 🔴 A RESPONSE DOES NOT GET TO DELETE WHAT SOMEBODY IS TYPING.
        //
        // This rebuilt `editorText` from the draft record on EVERY response and cleared
        // `dirty` with it. An unsaved draft's `raw` is still `{}` on the server, so any
        // request that came back while the operator was mid-edit -- the search debounce,
        // a refresh -- silently replaced what they had typed with `{}`, and clearing
        // `dirty` meant not even a leave warning fired. Measured: key `wafer_id` typed,
        // `lot` typed into the search box, editor back to `{}` with no message.
        //
        // Corrected HERE rather than only at the call sites that forgot to carry the
        // editor: this is the one place the answer arrives, so a caller added later
        // cannot reintroduce the hole by not knowing about it.
        editorText: state.dirty ? state.editorText
          : (p.draft ? JSON.stringify(p.draft.raw, null, 2) : ''),
        dirty: state.dirty,
        loading: false,
        error: null,
        removedSelection: null,
      };
    }
    case 'NAVIGATE_TO': {
      const current = state.selection?.key;
      if (!current || current === action.key) return state;
      const checkpoint = action.current || {
        key: current, query: state.query, detailTab: state.detailTab,
        treeScroll: 0, workspaceScroll: 0, editorSelectionStart: 0,
        editorSelectionEnd: 0, viewPreference: state.viewPreference,
        route: state.currentPath, contextToken: state.viewContext?.context_token || null,
        viaEdge: action.viaEdge || null,
      };
      return {
        ...state,
        navigation: freezeNav([...state.navigation.back, checkpoint], []),
      };
    }
    case 'NAVIGATE_BACK': {
      if (!state.navigation.back.length) return state;
      const back = [...state.navigation.back];
      const checkpoint = back.pop();
      const current = action.current || {
        key: state.selection?.key, query: state.query, detailTab: state.detailTab,
        treeScroll: 0, workspaceScroll: 0, editorSelectionStart: 0,
        editorSelectionEnd: 0, viewPreference: state.viewPreference,
        route: state.currentPath, contextToken: state.viewContext?.context_token || null,
        viaEdge: null,
      };
      return {
        ...state,
        pendingNavigation: checkpoint,
        navigation: freezeNav(back, current.key
          ? [current, ...state.navigation.forward] : [...state.navigation.forward]),
      };
    }
    case 'NAVIGATE_FORWARD': {
      if (!state.navigation.forward.length) return state;
      const forward = [...state.navigation.forward];
      const checkpoint = forward.shift();
      const current = action.current || {
        key: state.selection?.key, query: state.query, detailTab: state.detailTab,
        treeScroll: 0, workspaceScroll: 0, editorSelectionStart: 0,
        editorSelectionEnd: 0, viewPreference: state.viewPreference,
        route: state.currentPath, contextToken: state.viewContext?.context_token || null,
        viaEdge: null,
      };
      return {
        ...state,
        pendingNavigation: checkpoint,
        navigation: freezeNav(current.key
          ? [...state.navigation.back, current] : [...state.navigation.back], forward),
      };
    }
    case 'NAVIGATION_CONSUMED':
      return { ...state, pendingNavigation: null };
    case 'QUERY_CHANGED':
      return { ...state, query: action.query, page: 1 };
    case 'TAB_CHANGED':
      return { ...state, detailTab: action.tab };
    case 'VIEW_MODE_CHANGED':
      return { ...state, viewPreference: action.mode };
    case 'DRAFT_OPENED':
      return {
        ...state,
        draft: action.draft,
        editorText: JSON.stringify(action.draft.raw, null, 2),
        dirty: false,
        detailTab: 'raw',
      };
    case 'EDITOR_CHANGED':
      if (!isDraftRevisionEditable(state.draft)) return state;
      return { ...state, editorText: action.text, dirty: true };
    case 'DRAFT_SAVED':
      return {
        ...state,
        draft: action.draft,
        editorText: JSON.stringify(action.draft.raw, null, 2),
        dirty: false,
      };
    case 'DRAFT_CLOSED':
      return { ...state, draft: null, editorText: '', dirty: false };
    case 'AUTHORING_RECEIVED':
      return {
        ...state,
        authoring: action.plan ?? state.authoring,
        authoringSchema: action.schema ?? state.authoringSchema,
        authoringError: null,
      };
    case 'AUTHORING_FAILED':
      // Keep the last good plan on screen and SAY it is stale. Blanking the panel would
      // read as "nothing left to author", which is the silent empty panel again.
      return { ...state, authoringError: action.message };
    case 'AUTHORING_INVALIDATED':
      return { ...state, authoring: null, authoringError: null };
    default:
      return state;
  }
}

// The naming step, kept out of the big reducer switch because it touches exactly one
// field and never the mirrored context. `error` is cleared on every keystroke: a refusal
// about the previous name is worse than silence once the operator starts changing it.
export function reduceNewDeclaration(state, action) {
  if (action.type === 'NEW_DECLARATION_OPENED') {
    return { ...state, newDeclaration: { kind: action.kind, id: '', error: null } };
  }
  if (action.type === 'NEW_DECLARATION_TYPED') {
    if (!state.newDeclaration) return state;
    return { ...state, newDeclaration: { ...state.newDeclaration, id: action.id, error: null } };
  }
  if (action.type === 'NEW_DECLARATION_FAILED') {
    if (!state.newDeclaration) return state;
    return { ...state, newDeclaration: { ...state.newDeclaration, error: action.message } };
  }
  if (action.type === 'NEW_DECLARATION_CLOSED') {
    return { ...state, newDeclaration: null };
  }
  return state;
}

// One row opened or closed by hand. A fold the operator cannot open is not a fold, it is
// a deletion -- so every folded row is reachable, and the choice survives re-renders.
export function reduceFieldFold(state, action) {
  if (action.type !== 'FIELD_TOGGLED') return state;
  const open = new Set(state.expandedFields);
  if (open.has(action.path)) open.delete(action.path);
  else open.add(action.path);
  return { ...state, expandedFields: [...open] };
}

// 🔴 THE ONE PLACE ANYTHING ASKS "WHAT IS DECLARED IN THIS SECTION".
//
// Every picker built from step 5 onward reads this and holds no copy of its own. A picker
// that snapshots at mount is the defect the mirror exists to remove: declare a pack, go to
// the source whose profile needs it, and the list it captured a minute ago does not have it.
//
// 🔴 IT READS THE PLAN, NOT THE TREE, AND THAT IS THE WHOLE POINT. `state.items` is the
// obvious source and it is wrong twice over: `/view` is PAGED (100 at a time) and it is
// FILTERED BY THE SEARCH BOX, so a picker fed from it goes silently short -- and shortest
// exactly when the operator has typed a filter, which is when they are least likely to
// notice a name missing. `authoring.sections` is unpaged and unfiltered.
//
// 🔴 IT NEVER MERGES `newDeclaration`. The name being typed is not declared yet. Offering
// it would let a source's profile point at a pack the server has never accepted, and a create
// was REFUSED would go on showing as though it existed.
// 🔴 IT ANSWERS FOR THE AUTHORABLE SECTIONS AND NOTHING ELSE, and the picker round will
// hit that. Derived from the live config on 2026-08-19: every reference edge carries
// `expected_kind`, so `AUTHORABLE_SECTIONS[expected_kind]` gives the section a picker
// draws from -- entities, vocabulary, packs, sources. (`mappers`, `source_preparers` and
// `profiles` were on that list until 2026-08-20, when all three moved inside a source plan
// and joined the kinds below.)
// The rest of the expected kinds have no section of their own: `claim`, `mapping`,
// `binding`, `preparer`, `mapper` and `profile` (they live INSIDE an owner -- a mapper's `emits`
// picks claims from across all packs) and `table` (physical, read-only here, its own
// column universes). Those need a second source that does not exist yet. This is a gap in
// what is here, not a defect in it.
export function sectionMembers(state, section) {
  const all = state.authoring?.sections || {};
  if (section === undefined) return all;
  return all[section] || [];
}

// Is the mirror populated at all? Distinguishes "no declarations" from "not read yet",
// which render as the same empty list and mean opposite things to an operator.
export function mirrorLoaded(state) {
  return Boolean(state.authoring && state.authoring.sections);
}

export function canLeaveSelection(state, confirmDiscard) {
  return !state.dirty || Boolean(confirmDiscard());
}

export function dirtyNavigationDecision(state, choose) {
  if (!state.dirty) return 'keep';
  const choice = String(choose() || '').trim().toLowerCase();
  return ['keep', 'discard'].includes(choice) ? choice : 'cancel';
}

export function restoreDirtyEditorCheckpoint(state, checkpoint) {
  const draft = state.draft;
  const restorable = Boolean(
    checkpoint?.dirty
      && checkpoint.viewPreference === 'active'
      && state.viewContext?.mode === 'active'
      && checkpoint.contextToken === state.viewContext?.context_token
      && checkpoint.draftId === draft?.draft_id
      && checkpoint.draftRevision === draft?.revision
      && checkpoint.draftTargetKey === draft?.target_key
      && typeof checkpoint.editorText === 'string',
  );
  if (!restorable) return state;
  return {
    ...state,
    editorText: checkpoint.editorText,
    dirty: true,
    viewPreference: 'active',
  };
}

export function isDraftRevisionEditable(draft) {
  return Boolean(draft) && draft.lifecycle_status !== 'review_requested';
}

/** The id a new declaration will actually be created under.
 *
 *  Owner: 「new하면 @도 자동으로 안붙네」. Typing `lot` should make `lot@1`; if `lot@1` is
 *  taken it should offer `lot@2`; and `lot@3` typed by hand stays `lot@3` -- what a person
 *  wrote is not rewritten.
 *
 *  🔴 SIX OF THE SEVEN KINDS CARRY A VERSION AND SOURCES DO NOT (`dt_job`, no `@`), so
 *  "always append @1" would break sources. The screen does not hold that list: the server
 *  measures it off the validator and sends `versioned` on `authorable_kinds`. If the answer
 *  is missing, nothing is appended -- an absent flag must not invent a version.
 *
 *  The stored value is unchanged: `lot@1` is still exactly what lands in the file. This is
 *  typing, not format -- a format change would not match atoms already written.
 */
export function declarationIdFor(state, kind, typed) {
  const name = String(typed || '').trim();
  if (!name || name.includes('@')) return name;
  const row = (state.authoringSchema?.authorable_kinds || [])
    .find((item) => item.id === kind);
  if (!row?.versioned) return name;
  const taken = new Set((state.authoring?.sections || {})[row.section] || []);
  let version = 1;
  while (taken.has(`${name}@${version}`)) version += 1;
  return `${name}@${version}`;
}
