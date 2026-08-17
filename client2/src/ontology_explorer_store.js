// Ontology Config Explorer state contract.
// The reducer is deliberately DOM-free: one response may describe exactly one compiled
// context, and late responses can never overwrite a newer selection/search/draft request.

export const initialExplorerState = Object.freeze({
  activeSnapshot: null,
  viewContext: null,
  selection: null,
  items: [],
  nodes: [],
  outbound: [],
  usedBy: [],
  usedByTotal: 0,
  outboundTotal: 0,
  referencesTruncated: false,
  paths: [],
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
});

const CONTEXT_COLLECTIONS = [
  'items', 'nodes', 'outbound', 'used_by', 'path_candidates', 'integrity',
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
  if (payload?.selection?.context_token !== token) {
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
          nodes: [], outbound: [], usedBy: [], paths: [], integrity: [],
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
        items: p.items || [],
        nodes: p.nodes || [],
        outbound: p.outbound || [],
        usedBy: p.used_by || [],
        usedByTotal: p.used_by_total || 0,
        outboundTotal: p.outbound_total || 0,
        referencesTruncated: Boolean(p.references_truncated),
        paths: p.path_candidates || [],
        currentPath: action.route || {
          path_id: 'root', node_keys: [p.selection.key], edge_ids: [],
        },
        changes: p.changes || [],
        edgeChanges: p.edge_changes || [],
        integrity: p.integrity || [],
        page: p.page || 1,
        total: p.total || 0,
        draft: p.draft || null,
        viewPreference: p.view_context?.mode === 'draft_preview' ? 'draft_preview' : 'active',
        editorText: p.draft ? JSON.stringify(p.draft.raw, null, 2) : '',
        dirty: false,
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
    default:
      return state;
  }
}

export function canLeaveSelection(state, confirmDiscard) {
  return !state.dirty || Boolean(confirmDiscard());
}

export function dirtyNavigationDecision(state, choose) {
  if (!state.dirty) return 'keep';
  const choice = String(choose() || '').trim().toLowerCase();
  return ['keep', 'discard'].includes(choice) ? choice : 'cancel';
}

export function isDraftRevisionEditable(draft) {
  return Boolean(draft) && draft.lifecycle_status !== 'review_requested';
}
