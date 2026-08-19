import './ontology_explorer.css';
import {
  initialExplorerState, reduceExplorerState, dirtyNavigationDecision,
  reduceFieldFold, reduceNewDeclaration, restoreDirtyEditorCheckpoint,
} from './ontology_explorer_store.js';
import { renderOntologyExplorer } from './ontology_explorer_view.js';

let controller = null;

function chooseDirtyNavigation(root) {
  return new Promise((resolve) => {
    root.querySelector('.oe-dirty-dialog-backdrop')?.remove();
    const backdrop = document.createElement('div');
    backdrop.className = 'oe-dirty-dialog-backdrop';
    const dialog = document.createElement('section');
    dialog.className = 'oe-dirty-dialog';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'oe-dirty-dialog-title');
    const title = document.createElement('h2');
    title.id = 'oe-dirty-dialog-title';
    title.textContent = '저장하지 않은 초안이 있습니다';
    const message = document.createElement('p');
    message.textContent = '초안을 유지해 다른 선언을 보거나, 폐기하거나, 이동을 취소하세요.';
    const actions = document.createElement('div');
    actions.className = 'oe-dirty-dialog-actions';
    const finish = (choice) => {
      backdrop.remove();
      resolve(choice);
    };
    for (const [choice, label] of [
      ['keep', '초안 유지'], ['discard', '초안 폐기'], ['cancel', '이동 취소'],
    ]) {
      const action = document.createElement('button');
      action.type = 'button';
      action.dataset.dirtyChoice = choice;
      action.textContent = label;
      action.addEventListener('click', () => finish(choice), { once: true });
      actions.append(action);
    }
    dialog.append(title, message, actions);
    backdrop.append(dialog);
    backdrop.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') finish('cancel');
    });
    backdrop.addEventListener('click', (event) => {
      if (event.target === backdrop) finish('cancel');
    });
    root.append(backdrop);
    requestAnimationFrame(() => actions.querySelector('button')?.focus());
  });
}

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

  // The naming step has its own reducer: it touches one local field and never the mirrored
  // server context, and routing it through the big switch would put a not-yet-accepted
  // name next to the collections that mirror what the server actually has.
  const dispatchNaming = (action) => {
    state = reduceNewDeclaration(state, action);
    renderOntologyExplorer(root, state);
    return state;
  };

  // 🔴 THE ONE WAY THIS SCREEN LEARNS WHAT THE SERVER HAS.
  //
  // Every successful write ends here and nothing else refreshes anything. The rule that
  // matters is what it does NOT take: no argument saying who called it, no flag for
  // "local save" versus anything else. A path only a local save can call is a path a
  // message could never reuse, and rebuilding it later is the expensive version of this.
  //
  // 🔴 ONLY ON SUCCESS. A failed save must leave the draft exactly as typed -- the
  // operator's next move is to fix one field, not to retype the declaration -- so no
  // failure branch calls this.
  const readMirror = async ({ selection = state.selection?.key || null,
                             draft = state.draft } = {}) =>
    load({ selection, draft, allowContextSwitch: true });

  // Write the smallest config that validates, so a setup can begin from nothing.
  //
  // 🔴 THE SCREEN OFFERS; THE PERSON DECIDES. This is the only write here that is not a
  // draft, so it happens on a press and never because the screen noticed the file was
  // missing. The server refuses if anything is at the path -- including a file that will
  // not parse, which is somebody's work with a bad comma in it rather than an absence.
  const bootstrapConfig = async () => {
    try {
      const res = await adminFetch(`${apiBase}/admin/ontology-explorer/bootstrap`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = body?.detail || body;
        // Kept on the offer, not floated as a toast: the next move is to read it and act.
        state = { ...state, authoring: { ...(state.authoring || {}),
          bootstrapError: detail?.message || `HTTP ${res.status}` } };
        renderOntologyExplorer(root, state);
        return;
      }
      showToast?.(`${body.created} created`);
      // A config coming into existence while the screen is open is not a special case; it
      // is the ordinary "the server changed, re-read". If this ever needs its own bespoke
      // refresh again, the mirror has stopped being the single path.
      await readMirror({ selection: null });
    } catch (error) {
      state = { ...state, authoring: { ...(state.authoring || {}),
        bootstrapError: errorMessage(error) } };
      renderOntologyExplorer(root, state);
    }
  };

  // Author a declaration that does not exist yet, then open its draft.
  //
  // 🔴 THE REFUSAL STAYS ON THE NAMING ROW rather than becoming a toast. The operator's
  // next move is to change the name they just typed, and a message that floats away leaves
  // them retyping against a rule they can no longer read.
  const createDeclaration = async (kind) => {
    const canonicalId = (state.newDeclaration?.id || '').trim();
    if (!canonicalId) return;
    try {
      const res = await adminFetch(`${apiBase}/admin/ontology-explorer/drafts/new`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind,
          canonical_id: canonicalId,
          base_snapshot_hash: state.activeSnapshot?.snapshot_hash || '',
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = body?.detail || body;
        dispatchNaming({
          type: 'NEW_DECLARATION_FAILED',
          message: detail?.message || errorMessage(new Error(`HTTP ${res.status}`)),
        });
        return;
      }
      dispatchNaming({ type: 'NEW_DECLARATION_CLOSED' });
      dispatch({ type: 'DRAFT_OPENED', draft: body.draft || body });
      dispatch({ type: 'VIEW_MODE_CHANGED', mode: 'draft_preview' });
      // Re-read the mirror: the declaration is not in the snapshot until activation, but
      // the draft list and the tree's change markers are, and they are stale the moment
      // this returns.
      await readMirror({ selection: (body.draft || body).target_key });
    } catch (error) {
      dispatchNaming({ type: 'NEW_DECLARATION_FAILED', message: errorMessage(error) });
    }
  };

  const checkpoint = (viaEdge = null) => {
    const dirtyContextToken = state.dirty && state.activeSnapshot?.snapshot_hash
      ? `active:${state.activeSnapshot.snapshot_hash}` : null;
    return {
      key: state.selection?.key,
      query: state.query,
      detailTab: state.detailTab,
      treeScroll: root.querySelector('.oe-tree')?.scrollTop || 0,
      workspaceScroll: root.querySelector('.oe-workspace')?.scrollTop || 0,
      editorSelectionStart: root.querySelector('.oe-editor-textarea')?.selectionStart || 0,
      editorSelectionEnd: root.querySelector('.oe-editor-textarea')?.selectionEnd || 0,
      viewPreference: state.dirty ? 'active' : state.viewPreference,
      route: state.currentPath,
      contextToken: dirtyContextToken || state.viewContext?.context_token || null,
      editorText: state.dirty ? state.editorText : null,
      dirty: state.dirty,
      draftId: state.draft?.draft_id || null,
      draftRevision: state.draft?.revision ?? null,
      draftTargetKey: state.draft?.target_key || null,
      viaEdge,
    };
  };

  const restoreScroll = (saved) => requestAnimationFrame(() => {
    const tree = root.querySelector('.oe-tree');
    const workspace = root.querySelector('.oe-workspace');
    if (tree) tree.scrollTop = saved.treeScroll || 0;
    if (workspace) workspace.scrollTop = saved.workspaceScroll || 0;
    const editor = root.querySelector('.oe-editor-textarea');
    if (editor) editor.setSelectionRange(
      saved.editorSelectionStart || 0, saved.editorSelectionEnd || 0,
    );
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
    viewMode = state.viewPreference,
    route = null,
    editorCheckpoint = null,
    allowContextSwitch = false,
    expectedContextToken = null,
  } = {}) => {
    const requestId = ++generation;
    dispatch({ type: 'REQUEST_STARTED', generation: requestId });
    const params = new URLSearchParams({
      q: state.query, page: String(state.page), limit: '100',
      view_mode: viewMode,
    });
    if (selection) params.set('selection', selection);
    const expectedToken = expectedContextToken
      || (!allowContextSwitch ? state.viewContext?.context_token : null);
    if (expectedToken) {
      params.set('context_token', expectedToken);
    }
    if (draft?.draft_id) {
      params.set('draft_id', draft.draft_id);
      params.set('revision', String(draft.revision));
    }
    try {
      const payload = await jsonRequest(`/view?${params}`);
      dispatch({
        type: 'RESPONSE_RECEIVED', generation: requestId, payload, route,
        expectedSelection: selection,
      });
      if (requestId !== state.requestGeneration) return;
      // Not awaited: the authoring plan annotates the view, it does not gate it.
      void loadAuthoring(payload.selection?.key || selection || null);
      if (editorCheckpoint) {
        state = restoreDirtyEditorCheckpoint(state, editorCheckpoint);
        renderOntologyExplorer(root, state);
      }
    } catch (error) {
      dispatch({
        type: 'REQUEST_FAILED', generation: requestId,
        code: error?.detail?.code || error?.code,
        message: errorMessage(error),
        selection,
      });
      // A blank or broken root is precisely when `/view` cannot answer and the authoring
      // plan can. Loading it here is what gives a from-scratch operator a way in.
      void loadAuthoring(null);
    }
  };

  // The authoring plan is fetched per selection (the server filters it) and the closed
  // lists exactly once -- they change only when the validator's constants change, which
  // is a deploy, not a click. Failure never blanks the panel; it annotates it.
  const loadAuthoring = async (selection) => {
    try {
      const params = new URLSearchParams();
      if (selection) params.set('selection', selection);
      const [plan, schema] = await Promise.all([
        jsonRequest(`/authoring/plan?${params}`),
        state.authoringSchema
          ? Promise.resolve(state.authoringSchema)
          : jsonRequest('/authoring/schema'),
      ]);
      dispatch({ type: 'AUTHORING_RECEIVED', plan, schema });
    } catch (error) {
      console.warn('[ontology] authoring plan unavailable', error);
      dispatch({ type: 'AUTHORING_FAILED', message: errorMessage(error) });
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

  const routeFor = (key, viaEdge, direct, pathId) => {
    if (direct) return { path_id: 'root', node_keys: [key], edge_ids: [] };
    const candidate = [state.currentPath, ...state.paths]
      .find((path) => path?.path_id === pathId);
    const position = candidate?.node_keys?.lastIndexOf(key) ?? -1;
    if (position >= 0) {
      return {
        path_id: candidate.path_id,
        node_keys: candidate.node_keys.slice(0, position + 1),
        edge_ids: candidate.edge_ids.slice(0, position),
      };
    }
    if (!viaEdge) return { path_id: 'root', node_keys: [key], edge_ids: [] };
    const edge = [...state.outbound, ...state.usedBy].find((item) => item.edge_id === viaEdge);
    if (!edge?.to_key || ![edge.from_key, edge.to_key].includes(key)) {
      return { path_id: 'root', node_keys: [key], edge_ids: [] };
    }
    return {
      path_id: `edge:${edge.edge_id}`,
      node_keys: [state.selection.key, key],
      edge_ids: [edge.edge_id],
    };
  };

  const select = async (
    key, recordHistory = true, viaEdge = null, direct = false, pathId = null,
  ) => {
    if (!key || key === state.selection?.key) return;
    const choice = state.dirty ? await chooseDirtyNavigation(root) : 'keep';
    const decision = dirtyNavigationDecision(state, () => choice);
    if (decision === 'cancel') return;
    const preserveEditor = decision === 'keep' && state.dirty;
    const leavingCheckpoint = checkpoint(viaEdge);
    const keptDraft = decision === 'keep' ? state.draft : null;
    const leftDraftContext = Boolean(state.draft);
    if (decision === 'discard' && state.draft && !(await discardDraft({ ask: false }))) return;
    const route = routeFor(key, viaEdge, direct, pathId);
    if (recordHistory) dispatch({
      type: 'NAVIGATE_TO', key, current: leavingCheckpoint, viaEdge,
    });
    await load({
      selection: key, draft: keptDraft,
      viewMode: preserveEditor ? 'active' : state.viewPreference,
      route, editorCheckpoint: preserveEditor ? leavingCheckpoint : null,
      allowContextSwitch: leftDraftContext,
      expectedContextToken: preserveEditor ? leavingCheckpoint.contextToken : null,
    });
  };

  const mutateDraft = async (
    path, init, action = 'DRAFT_SAVED', nextViewMode = state.viewPreference,
  ) => {
    try {
      const draft = await jsonRequest(path, init);
      dispatch({ type: action, draft: draft.draft || draft });
      dispatch({ type: 'VIEW_MODE_CHANGED', mode: nextViewMode });
      await load({
        selection: state.selection?.key, draft: draft.draft || draft,
        viewMode: nextViewMode,
        allowContextSwitch: true,
      });
      return draft;
    } catch (error) {
      showToast(errorMessage(error), 'error');
      return null;
    }
  };

  root.addEventListener('keydown', (event) => {
    const target = event.target.closest('button[data-action]');
    if (!target || target.disabled || !['Enter', ' '].includes(event.key)) return;
    event.preventDefault();
    target.click();
  });

  root.addEventListener('click', async (event) => {
    const target = event.target.closest('[data-action]');
    if (!target || target.disabled) return;
    const action = target.dataset.action;
    if (action === 'select') await select(
      target.dataset.value, true, target.dataset.edgeId || null,
      target.dataset.direct === 'true',
      target.dataset.pathId || null,
    );
    else if (action === 'tab') dispatch({ type: 'TAB_CHANGED', tab: target.dataset.value });
    else if (action === 'bootstrap-config') {
      await bootstrapConfig();
    }
    else if (action === 'toggle-field') {
      state = reduceFieldFold(state, { type: 'FIELD_TOGGLED', path: target.dataset.value });
      renderOntologyExplorer(root, state);
    }
    else if (action === 'new-declaration') {
      dispatchNaming({ type: 'NEW_DECLARATION_OPENED', kind: target.dataset.value });
    } else if (action === 'cancel-declaration') {
      dispatchNaming({ type: 'NEW_DECLARATION_CLOSED' });
    } else if (action === 'create-declaration') {
      await createDeclaration(target.dataset.value);
    }
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
        state = reduceExplorerState(state, {
          type: 'VIEW_MODE_CHANGED', mode: saved.viewPreference || 'active',
        });
        await load({
          selection: saved.key, draft: state.draft,
          viewMode: saved.viewPreference || 'active', route: saved.route,
          editorCheckpoint: saved.dirty ? saved : null,
          allowContextSwitch: true, expectedContextToken: saved.contextToken,
        });
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
        dispatch({ type: 'VIEW_MODE_CHANGED', mode: 'active' });
        await load({ draft, viewMode: 'active', allowContextSwitch: true });
      } catch (error) { showToast(errorMessage(error), 'error'); }
    } else if (action === 'save-draft') {
      await mutateDraft(`/drafts/${state.draft.draft_id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: state.draft.revision, raw: state.editorText }),
      }, 'DRAFT_SAVED', 'draft_preview');
    } else if (action === 'review-draft') {
      if (state.dirty) { showToast('먼저 초안을 저장해 주세요.', 'warning'); return; }
      await mutateDraft(`/drafts/${state.draft.draft_id}/review`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: state.draft.revision }),
      });
    } else if (action === 'revise-draft') {
      await mutateDraft(`/drafts/${state.draft.draft_id}/revise`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: state.draft.revision }),
      }, 'DRAFT_SAVED', 'active');
    } else if (action === 'view-active' || action === 'view-draft') {
      const mode = action === 'view-draft' ? 'draft_preview' : 'active';
      dispatch({ type: 'VIEW_MODE_CHANGED', mode });
      await load({ draft: state.draft, viewMode: mode, allowContextSwitch: true });
    } else if (action === 'activate-draft') {
      if (state.dirty) { showToast('먼저 초안을 저장해 주세요.', 'warning'); return; }
      if (!window.confirm('검토 요청한 정확한 revision을 활성 설정으로 교체할까요?')) return;
      try {
        await jsonRequest(`/drafts/${state.draft.draft_id}/activate`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ expected_revision: state.draft.revision }),
        });
        dispatch({ type: 'DRAFT_CLOSED' });
        dispatch({ type: 'AUTHORING_INVALIDATED' });
        showToast('검토한 초안을 활성화했습니다.', 'success');
        // Activation is the write that changes what is DECLARED, so it re-reads through
        // the same door as every other write rather than refreshing in its own way.
        await readMirror({ draft: null });
      } catch (error) { showToast(errorMessage(error), 'error'); }
    } else if (action === 'discard-draft') {
      if (await discardDraft()) await readMirror({ draft: null });
    }
  });

  root.addEventListener('input', (event) => {
    if (event.target.dataset.action === 'new-declaration-id') {
      // Safe to re-render on every keystroke now: the reconciler keeps the focused control
      // and what is in it (`dom_patch.js`). Before it, this had to skip rendering to
      // protect the caret -- which is why the two handlers below still do.
      dispatchNaming({ type: 'NEW_DECLARATION_TYPED', id: event.target.value });
      return;
    }
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
