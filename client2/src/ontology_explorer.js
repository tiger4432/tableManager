import './ontology_explorer.css';
import {
  initialExplorerState, reduceExplorerState, canLeaveSelection,
} from './ontology_explorer_store.js';
import { renderOntologyExplorer } from './ontology_explorer_view.js';

let controller = null;

function errorMessage(error) {
  return error?.detail?.message || error?.message || String(error);
}

export function createOntologyExplorerController({ root, apiBase, adminFetch, showToast }) {
  let state = { ...initialExplorerState, navigation: { back: [], forward: [] } };
  let generation = 0;
  let searchTimer = null;

  const dispatch = (action) => {
    state = reduceExplorerState(state, action);
    renderOntologyExplorer(root, state);
    return state;
  };

  const checkpoint = (viaEdge = null) => ({
    key: state.selection?.key,
    query: state.query,
    detailTab: state.detailTab,
    treeScroll: root.querySelector('.oe-tree')?.scrollTop || 0,
    workspaceScroll: root.querySelector('.oe-workspace')?.scrollTop || 0,
    viaEdge,
  });

  const restoreScroll = (saved) => requestAnimationFrame(() => {
    const tree = root.querySelector('.oe-tree');
    const workspace = root.querySelector('.oe-workspace');
    if (tree) tree.scrollTop = saved.treeScroll || 0;
    if (workspace) workspace.scrollTop = saved.workspaceScroll || 0;
  });

  const jsonRequest = async (path, init) => {
    const response = await adminFetch(`${apiBase}/admin/ontology-explorer${path}`, init);
    let payload = null;
    try { payload = await response.json(); } catch (_) { /* structured fallback below */ }
    if (!response.ok) {
      const detail = payload?.detail || payload || {};
      const error = new Error(detail.message || `요청 실패 (${response.status})`);
      error.detail = detail;
      throw error;
    }
    return payload;
  };

  const load = async ({
    selection = state.selection?.key,
    draft = state.draft,
    allowContextSwitch = false,
  } = {}) => {
    const requestId = ++generation;
    dispatch({ type: 'REQUEST_STARTED', generation: requestId });
    const params = new URLSearchParams({
      q: state.query, page: String(state.page), limit: '100',
    });
    if (selection) params.set('selection', selection);
    if (!allowContextSwitch && state.viewContext?.context_token) {
      params.set('context_token', state.viewContext.context_token);
    }
    if (draft?.draft_id) {
      params.set('draft_id', draft.draft_id);
      params.set('revision', String(draft.revision));
    }
    try {
      const payload = await jsonRequest(`/view?${params}`);
      dispatch({ type: 'RESPONSE_RECEIVED', generation: requestId, payload });
    } catch (error) {
      dispatch({
        type: 'REQUEST_FAILED', generation: requestId,
        code: error?.detail?.code || error?.code,
        message: errorMessage(error),
      });
    }
  };

  const discardDraft = async ({ ask = true } = {}) => {
    if (!state.draft) return true;
    if (ask && !window.confirm('현재 초안을 폐기할까요?')) return false;
    try {
      await jsonRequest(
        `/drafts/${state.draft.draft_id}?expected_revision=${state.draft.revision}`,
        { method: 'DELETE' },
      );
      dispatch({ type: 'DRAFT_CLOSED' });
      return true;
    } catch (error) {
      showToast(errorMessage(error), 'error');
      return false;
    }
  };

  const select = async (key, recordHistory = true, viaEdge = null) => {
    if (!key || key === state.selection?.key) return;
    if (!canLeaveSelection(state, () => window.confirm('저장하지 않은 초안을 폐기하고 이동할까요?'))) return;
    const leftDraftContext = Boolean(state.draft);
    if (state.draft && !(await discardDraft({ ask: !state.dirty }))) return;
    if (recordHistory) dispatch({
      type: 'NAVIGATE_TO', key, current: checkpoint(viaEdge), viaEdge,
    });
    await load({ selection: key, draft: null, allowContextSwitch: leftDraftContext });
  };

  const mutateDraft = async (path, init, action = 'DRAFT_SAVED') => {
    try {
      const draft = await jsonRequest(path, init);
      dispatch({ type: action, draft: draft.draft || draft });
      await load({
        selection: state.selection?.key, draft: draft.draft || draft,
        allowContextSwitch: true,
      });
      return draft;
    } catch (error) {
      showToast(errorMessage(error), 'error');
      return null;
    }
  };

  root.addEventListener('click', async (event) => {
    const target = event.target.closest('[data-action]');
    if (!target || target.disabled) return;
    const action = target.dataset.action;
    if (action === 'select') await select(target.dataset.value, true, target.dataset.edgeId || null);
    else if (action === 'tab') dispatch({ type: 'TAB_CHANGED', tab: target.dataset.value });
    else if (action === 'back' || action === 'forward') {
      dispatch({
        type: action === 'back' ? 'NAVIGATE_BACK' : 'NAVIGATE_FORWARD',
        current: checkpoint(),
      });
      const saved = state.pendingNavigation;
      dispatch({ type: 'NAVIGATION_CONSUMED' });
      if (saved?.key) {
        state = reduceExplorerState(state, { type: 'QUERY_CHANGED', query: saved.query || '' });
        state = reduceExplorerState(state, { type: 'TAB_CHANGED', tab: saved.detailTab || 'definition' });
        await select(saved.key, false);
        restoreScroll(saved);
      }
    } else if (action === 'create-draft') {
      try {
        const draft = await jsonRequest('/drafts', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_key: state.selection.key,
            base_snapshot_hash: state.activeSnapshot.snapshot_hash,
          }),
        });
        dispatch({ type: 'DRAFT_OPENED', draft });
        await load({ draft, allowContextSwitch: true });
      } catch (error) { showToast(errorMessage(error), 'error'); }
    } else if (action === 'save-draft') {
      await mutateDraft(`/drafts/${state.draft.draft_id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: state.draft.revision, raw: state.editorText }),
      });
    } else if (action === 'review-draft') {
      if (state.dirty) { showToast('먼저 초안을 저장해 주세요.', 'warning'); return; }
      await mutateDraft(`/drafts/${state.draft.draft_id}/review`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: state.draft.revision }),
      });
    } else if (action === 'activate-draft') {
      if (state.dirty) { showToast('먼저 초안을 저장해 주세요.', 'warning'); return; }
      if (!window.confirm('검토 요청한 정확한 revision을 활성 설정으로 교체할까요?')) return;
      try {
        await jsonRequest(`/drafts/${state.draft.draft_id}/activate`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ expected_revision: state.draft.revision }),
        });
        dispatch({ type: 'DRAFT_CLOSED' });
        showToast('검토한 초안을 활성화했습니다.', 'success');
        await load({ draft: null, allowContextSwitch: true });
      } catch (error) { showToast(errorMessage(error), 'error'); }
    } else if (action === 'discard-draft') {
      if (await discardDraft()) await load({ draft: null, allowContextSwitch: true });
    }
  });

  root.addEventListener('input', (event) => {
    if (event.target.dataset.action === 'edit-raw') {
      // Do not replace the textarea on every keystroke. The controller state changes,
      // while the focused DOM control remains the immediate rendered value.
      state = reduceExplorerState(state, { type: 'EDITOR_CHANGED', text: event.target.value });
    } else if (event.target.dataset.action === 'search') {
      const query = event.target.value;
      // Same focus rule for search: render once the debounced server result arrives.
      state = reduceExplorerState(state, { type: 'QUERY_CHANGED', query });
      clearTimeout(searchTimer);
      // Search narrows the catalog; it does not silently replace the inspector selection.
      // The operator explicitly clicks a result, which gives navigation history one truth.
      searchTimer = setTimeout(() => load({
        selection: state.selection?.key,
        draft: state.draft,
      }), 180);
    }
  });

  return {
    refresh: () => load({ allowContextSwitch: true }),
    destroy: () => clearTimeout(searchTimer),
    getState: () => state,
  };
}

export function initOntologyExplorer(options) {
  if (controller) controller.destroy();
  controller = createOntologyExplorerController(options);
  return controller;
}

export function refreshOntologyExplorer() {
  return controller?.refresh();
}
