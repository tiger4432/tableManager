import './ontology_explorer.css';
import {
  initialExplorerState, reduceExplorerState, dirtyNavigationDecision,
  reduceFieldFold, reduceNewDeclaration, restoreDirtyEditorCheckpoint,
  declarationIdFor,
} from './ontology_explorer_store.js';
import { renderOntologyExplorer } from './ontology_explorer_view.js';
import {
  splitBundlePath, setAtPath, getAtPath, deleteAtPath,
} from './ontology_path.js';
import { declarationShape, emptyOf, shapeAt } from './ontology_skeleton.js';

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
                             draft = state.draft,
                             viewMode = state.viewPreference } = {}) =>
    load({ selection, draft, viewMode, allowContextSwitch: true });

  // Rewrite `keys` in the draft text the save button already sends.
  //
  // 🔴 IT EDITS `editorText`, NOT A SECOND SOURCE. The rows are another way to type into
  // the same buffer the textarea holds, so save, validation, dirty-tracking and the
  // revision guard all keep working untouched. A separate keys-state would be a second
  // author for one value, which is the merge question the mirror exists to avoid.
  const editEntityKeys = (mutate) => {
    let raw;
    try {
      raw = JSON.parse(state.editorText || '{}');
    } catch {
      return;                      // let the textarea own its own syntax error
    }
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return;
    const keys = Array.isArray(raw.keys) ? [...raw.keys] : [];
    const next = mutate(keys);
    dispatch({
      type: 'EDITOR_CHANGED',
      text: JSON.stringify({ ...raw, keys: next }, null, 2),
    });
  };

  // Put a picked reference into the draft text at the field's own path.
  //
  // 🔴 SAME ROUTE AS THE ENTITY KEYS ABOVE: parse the draft text, change one leaf, hand
  // the text back through `EDITOR_CHANGED`. No new save path and no new endpoint -- Save
  // still writes the same buffer, so there is exactly one thing that reaches the file.
  //
  // 🔴 THE SECTION AND THE ID ARE BOTH CHECKED BEFORE WRITING. The live config declares
  // `packs.dt-job@1` AND `profiles.dt-job@1`, so an id-only check would write a pack's
  // field into a profile's draft. If the prefix does not match the open draft, or the leaf
  // does not resolve, nothing is written -- the field belongs to something else.
  const editFieldAtPath = (path, value) => {
    const draft = state.draft;
    if (!draft || !state.editorText) return;
    const kinds = state.authoringSchema?.authorable_kinds || [];
    const section = kinds.find((row) => row.id === draft.target_kind)?.section;
    if (!section) return;
    const steps = splitBundlePath(path);
    if (steps[0] !== section || steps[1] !== draft.target_id) return;
    let raw;
    try {
      raw = JSON.parse(state.editorText);
    } catch {
      return;                      // let the textarea own its own syntax error
    }
    // 🔴 THE BRANCH IS BUILT, BECAUSE THE ROW WAS OFFERED. `setAtPath` refuses a missing
    // parent on purpose, and that was right while a plan row only ever named a leaf the
    // declaration already had a place for. It no longer is: a row is now offered for a
    // field nobody has filled in yet, so `driver.unit` gets a dropbox on a source that has
    // no `driver` at all -- and walked, choosing a unit wrote NOTHING. A control that
    // silently does nothing is the refusing control this screen keeps removing.
    // Plain objects only, never a guessed value, and never through a list index.
    const relative = steps.slice(2);
    for (let depth = 1; depth < relative.length; depth += 1) {
      const branch = relative.slice(0, depth);
      if (getAtPath(raw, branch) !== undefined) continue;
      if (typeof branch[branch.length - 1] === 'number') break;
      const built = setAtPath(raw, branch, {});
      if (built === null) break;
      raw = built;
    }
    const next = setAtPath(raw, relative, value);
    if (next === null) return;
    dispatch({ type: 'EDITOR_CHANGED', text: JSON.stringify(next, null, 2) });
  };

  // Read the leaf the writer would write, under the SAME guards -- section, id and
  // resolvability. Two different notions of "is this field mine" would eventually disagree.
  const draftValueAt = (path) => {
    const draft = state.draft;
    if (!draft || !state.editorText) return undefined;
    const kinds = state.authoringSchema?.authorable_kinds || [];
    const section = kinds.find((row) => row.id === draft.target_kind)?.section;
    if (!section) return undefined;
    const steps = splitBundlePath(path);
    if (steps[0] !== section || steps[1] !== draft.target_id) return undefined;
    try {
      return getAtPath(JSON.parse(state.editorText), steps.slice(2));
    } catch {
      return undefined;
    }
  };

  // One element of a list field. The whole list is rewritten through `editFieldAtPath`, so
  // there is still exactly one writer and one save path.
  const editFieldList = (path, mutate) => {
    const current = draftValueAt(path);
    if (!Array.isArray(current)) return;
    editFieldAtPath(path, mutate([...current]));
  };

  // Write a leaf named by a path RELATIVE to the declaration body (the claim form).
  // The absolute-path writer above is for authoring-plan rows; this one is for fields the
  // form knows about directly, and both end in the same `EDITOR_CHANGED`.
  const editShapeAtPath = (relative, value) => {
    if (!state.draft || !state.editorText) return;
    let raw;
    try {
      raw = JSON.parse(state.editorText);
    } catch {
      return;
    }
    const steps = splitBundlePath(relative);
    // 🔴 THE FORM'S OWN BRANCHES ARE BUILT, because the form is what promised them.
    // `setAtPath` refuses a missing parent on purpose -- an authoring-plan row names a leaf
    // the declaration already has a place for. But the claim form offers `emit.object.kind`
    // on a claim whose `emit` does not exist yet, and a field that silently does nothing is
    // the refusing control this screen keeps removing. The shape said those objects exist,
    // so writing through it creates them -- and only plain objects, never a guessed value.
    // 🔴 A LIST SLOT IS NEVER INVENTED, BUT WHAT LIVES INSIDE ONE STILL GETS BUILT. Refusing
    // the whole path as soon as it held a number was too wide: `mappings[0].bind` sits under
    // an element that EXISTS, and naming a binding there wrote nothing at all -- the button
    // was silent, which is the failure this screen keeps closing. So the refusal is narrowed
    // to what it always meant: a missing INDEX is a member nobody added, and inventing it
    // would put an empty slot in somebody's list.
    for (let depth = 1; depth < steps.length; depth += 1) {
      const branch = steps.slice(0, depth);
      if (getAtPath(raw, branch) !== undefined) continue;
      if (typeof branch[branch.length - 1] === 'number') break;
      const built = setAtPath(raw, branch, {});
      if (built === null) break;
      raw = built;
    }
    // 🔴 THE UI NEVER ASSERTS A TYPE. The plan carries none -- measured, a field record has
    // no type key and `implementation_version` is not a plan row at all -- so a table here
    // saying "this one is an integer" would be a second author for the validator's
    // contract, the exact thing removed from this screen all day.
    //
    // Instead: whatever type is already at that leaf is preserved, and a value typed into
    // an empty leaf goes in as typed. If that is wrong the validator says so, and since
    // today it says so ON the screen, showing beats blocking.
    const current = getAtPath(raw, steps);
    let written = value;
    if (typeof current === 'number' && typeof value === 'string') {
      const asNumber = Number(value.trim());
      if (value.trim() !== '' && Number.isFinite(asNumber)) written = asNumber;
    }
    const next = setAtPath(raw, steps, written);
    if (next === null) return;
    dispatch({ type: 'EDITOR_CHANGED', text: JSON.stringify(next, null, 2) });
  };

  // The skeleton node describing a path inside the open declaration, and the value the
  // draft currently holds there. Both walk the same path the writer would write.
  const shapeForPath = (relative) => {
    const skeleton = state.authoringSchema?.skeleton;
    const section = (state.authoringSchema?.authorable_kinds || [])
      .find((row) => row.id === state.draft?.target_kind)?.section;
    if (!skeleton || !section) return null;
    return shapeAt(declarationShape(skeleton, section), splitBundlePath(relative),
                   skeleton.defs);
  };

  const draftShapeAt = (relative) => {
    if (!state.editorText) return undefined;
    try {
      return getAtPath(JSON.parse(state.editorText), splitBundlePath(relative));
    } catch {
      return undefined;
    }
  };

  const removeShapeAtPath = (relative) => {
    if (!state.draft || !state.editorText) return;
    let raw;
    try {
      raw = JSON.parse(state.editorText);
    } catch {
      return;
    }
    const next = deleteAtPath(raw, splitBundlePath(relative));
    if (next === null) return;
    dispatch({ type: 'EDITOR_CHANGED', text: JSON.stringify(next, null, 2) });
  };

  // A list leaf named by a relative path (the draft-derived rows).
  const editShapeList = (relative, mutate) => {
    if (!state.draft || !state.editorText) return;
    let raw;
    try {
      raw = JSON.parse(state.editorText);
    } catch {
      return;
    }
    const current = getAtPath(raw, splitBundlePath(relative));
    if (!Array.isArray(current)) return;
    editShapeAtPath(relative, mutate([...current]));
  };

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
    // Same rule the naming box previewed, from the same function -- so what was shown as
    // 「→ lot@2」 is what gets created, rather than two guesses that agree today.
    const canonicalId = declarationIdFor(state, kind, state.newDeclaration?.id);
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
      const created = body.draft || body;
      dispatch({ type: 'DRAFT_OPENED', draft: created });
      // 🔴 CREATING IS 「와꾸 짜기」: THE EMPTY DECLARATION GOES INTO THE FILE NOW.
      //
      // Nothing describes a declaration that is not in the file -- measured: for an unsaved
      // create draft the plan has 0 rows for it, and even the draft preview reports
      // `validation_errors: 0` while calling itself invalid. So a fresh pack showed 「None
      // defined」 four times and never said what to make. Telling the operator "save first
      // and I will tell you" would be one more procedure to memorise, which is the thing
      // being removed.
      //
      // So it is written, and then the validator can name what it needs. Same shape as
      // 「저장 = 저장 + 반영」: two calls the server already has, joined behind one press.
      // NO NEW ENDPOINT. Possible only because saving stopped requiring the setup to
      // compile -- this morning an empty declaration would have been refused.
      const saved = await jsonRequest(`/drafts/${created.draft_id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        // 🔴 WHAT THE SERVER JUST SEEDED, NOT `{}`. This landed the declaration in the file
        // immediately -- and wrote an empty object over the containers `drafts/new` had put
        // there, so the seed was correct on the server and gone by the time anybody saw it.
        // Measured: the editor opened on `{}` while the draft record held
        // `{'subjects': [], 'object': {'qualifiers': …}}`.
        body: JSON.stringify({
          expected_revision: created.revision,
          raw: JSON.stringify(created.raw ?? {}),
        }),
      });
      const record = saved.draft || saved;
      await jsonRequest(`/drafts/${record.draft_id}/activate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ expected_revision: record.revision }),
      });
      dispatch({ type: 'DRAFT_CLOSED' });
      dispatch({ type: 'AUTHORING_INVALIDATED' });
      // 🔴 IN THE FILE IS NOT IN THE SNAPSHOT. An empty declaration does not resolve, so it
      // lands UNREAD -- and asking `/view` for it by name answers `unknown_selection`, which
      // is the trap the comment below has always warned about. Walked: the pack was in the
      // file and the screen showed nothing until a reload.
      //
      // So the mirror is read with no selection, and then the declaration is opened through
      // the same door its unread row uses. That path already seeds the editor from the file
      // and fetches the plan for the right subject.
      await readMirror({ selection: null, draft: null, viewMode: 'active' });
      const row = state.items.find((item) => item.key === created.target_key);
      if (row) await openUnread(row);
      return;
      // 🔴 NOT draft_preview. A brand-new draft's raw is `{}` and cannot compile BY
      // DEFINITION, so preview mode always falls back to the active snapshot and reports
      // the first validation error as the reason -- 「초안 대신 활성 snapshot 표시 ·
      // invalid_type」 on a declaration that was just created successfully. Preview is for
      // seeing what a draft would CHANGE; a fresh create has nothing to compare yet.
      // Re-read the mirror: the declaration is not in the snapshot until activation, but
      // the draft list and the tree's change markers are, and they are stale the moment
      // this returns.
      // 🔴 DO NOT ASK THE MIRROR FOR THE THING JUST CREATED. A create draft's target is by
      // definition NOT in the active snapshot -- that is what "create" means -- so
      // selecting it makes `/view` answer `unknown_selection` and the screen errors
      // immediately after a successful create. The mirror reflects what is DECLARED; the
      // new declaration lives in the draft layer, which `DRAFT_OPENED` above already holds.
      // 🔴 `viewMode` SPELLED OUT. The comment above promises the active view; with no
      // argument the read inherits whatever the last action left behind, and a brand-new
      // draft read in preview mode reports itself invalid the moment it is created.
      await readMirror({ selection: null, viewMode: 'active' });
    } catch (error) {
      dispatchNaming({ type: 'NEW_DECLARATION_FAILED', message: errorMessage(error) });
    }
  };

  // Remove one declaration. The preview SHOWS; it does not decide.
  //
  // 🔴 NO GATE, AND THAT IS THE RULING. Deleting something others reference used to make
  // the whole config unreadable, so it had to be judged in advance. It no longer does:
  // the referrers become `invalid`, which is listed, explained and openable -- the same
  // ordinary state as a declaration written before the thing it names.
  //
  // 🔴 AND NEVER A REFERENCE-COUNT GUARD. A source and its profile name each other, so
  // in-degree never reaches zero for either and such a guard refuses everything
  // (board `ec9f1c2`).
  const deleteDeclaration = async (targetKey) => {
    try {
      const plan = await jsonRequest(
        `/deletion-preview?targets=${encodeURIComponent(targetKey)}`);
      // `unread_after`, not `released`. The latter means "authored in another file and
      // merely stops being referenced" -- it never answered "what stops resolving", and
      // reading it for that printed 「영향 없음」 while a pack was about to go unread.
      // `unread_after` comes from the same resolver the load runs, so the confirm and the
      // outcome cannot disagree.
      const casualties = (plan.unread_after || []).map((row) => row.canonical_id || row.key);
      const id = targetKey.split('|')[1] || targetKey;
      // Terse, nouns and symbols -- the owner's rule for every string on this screen.
      const message = casualties.length
        ? `${id} 삭제
안 읽히게 됨 · ${casualties.length} : ${casualties.join(', ')}`
        : `${id} 삭제
영향 없음`;
      if (!window.confirm(message)) return;
      await jsonRequest(
        `/declarations/${encodeURIComponent(targetKey)}`
        + `?base_snapshot_hash=${encodeURIComponent(state.activeSnapshot?.snapshot_hash || '')}`,
        { method: 'DELETE' });
      dispatch({ type: 'DRAFT_CLOSED' });
      dispatch({ type: 'AUTHORING_INVALIDATED' });
      showToast(`${id} 삭제됨`, 'success');
      await readMirror({ draft: null, selection: null, viewMode: 'active' });
    } catch (error) { showToast(errorMessage(error), 'error'); }
  };

  // Put the editor back on the declaration just saved, so editing continues.
  //
  // Which door depends on what the save produced: a declaration that now resolves is in
  // the snapshot and takes the ordinary edit path; one that still cannot be read is not in
  // the snapshot at all, and takes the same door the tree row uses.
  const reopenForEditing = async (targetKey, kind, canonicalId) => {
    try {
      if (state.invalid?.[targetKey]) {
        const item = state.items.find((row) => row.key === targetKey);
        if (item) await openUnread(item);
        return;
      }
      const reopened = await jsonRequest('/drafts', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_key: targetKey,
          base_snapshot_hash: state.activeSnapshot?.snapshot_hash || '',
        }),
      });
      dispatch({ type: 'DRAFT_OPENED', draft: reopened.draft || reopened });
      await load({ selection: targetKey, draft: reopened.draft || reopened,
                   viewMode: 'active', allowContextSwitch: true });
    } catch (error) {
      // The save itself succeeded; failing to re-open is not a reason to say it did not.
      showToast(errorMessage(error), 'warning');
    }
  };

  // Open a declaration that is in the file but could not be read, on its own text.
  const openUnread = async (item) => {
    try {
      const res = await adminFetch(`${apiBase}/admin/ontology-explorer/drafts/new`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind: item.kind,
          canonical_id: item.canonical_id,
          base_snapshot_hash: state.activeSnapshot?.snapshot_hash || '',
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        showToast((body?.detail || body)?.message || errorMessage(
          new Error(`HTTP ${res.status}`)), 'error');
        return;
      }
      dispatch({ type: 'DRAFT_OPENED', draft: body.draft || body });
      // 🔴 SEEDED FROM THE FILE, NOT FROM `{}`. A fresh draft's raw is empty; this one is
      // being FINISHED, so it starts from what the operator already wrote. Saving sends
      // this buffer, so nothing they typed earlier is lost by opening it again.
      dispatch({
        type: 'EDITOR_CHANGED',
        text: JSON.stringify(item.raw ?? {}, null, 2),
      });
      // No re-read: opening a draft writes nothing, and a mirror read here would answer
      // with the draft's own empty `raw` and wipe the text just seeded from the file.
      //
      // 🔴 THE PLAN IS FETCHED HERE ANYWAY, AND IT IS NOT A RE-READ. `/view` is what would
      // clobber the seeded text; `loadAuthoring` hits a different endpoint and its reducer
      // touches `authoring`, `authoringSchema` and `authoringError` only -- never
      // `editorText`. Without this call an unread declaration opens with the raw textarea
      // and no rows, which is the state the operator was stuck in: suggestions missing
      // from the one declaration they came here to finish.
      void loadAuthoring(item.key);
    } catch (error) {
      showToast(errorMessage(error), 'error');
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
    // 🔴 A DRAFT MODE WITHOUT A DRAFT IS A 400, AND IT OUTLIVES ITS MOMENT.
    //
    // `viewMode` defaults to `state.viewPreference`, which a save leaves on
    // `draft_preview`. The draft is gone one action later, so the next read asks for a
    // draft view with no `draft_id` and is refused -- the screen then never re-reads,
    // keeps the pre-write snapshot hash, and the SECOND create dies on a stale
    // compare-and-swap. That is the 「두 번째 무반응」 the owner hit.
    //
    // Corrected HERE and not at the call sites: the mode and the draft travel together
    // through this one door, so every caller is covered and none has to remember.
    const mode = draft?.draft_id ? viewMode : 'active';
    dispatch({ type: 'REQUEST_STARTED', generation: requestId });
    const params = new URLSearchParams({
      q: state.query, page: String(state.page), limit: '100',
      view_mode: mode,
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
      //
      // 🔴 FALL BACK TO THE DRAFT'S TARGET. An UNREAD declaration is not in the index, so
      // there is no selection to key on -- and that is exactly the declaration someone is
      // sitting on, because unread is what 「일단 와꾸 짜놓고 나중에 살 채우는」 leaves
      // behind. Keyed on the selection alone the server got no prefix and widened the plan
      // to the whole config, so the one declaration being finished had no rows of its own.
      //
      // The plan itself never needed the index: `authoring()` reads the file 「DELIBERATELY
      // DOES NOT GO THROUGH active()」 and `authoring_prefix` is pure string mapping.
      // Measured on the live route with three unread declarations: 16, 4 and 9 fields came
      // back, 11 / 2 / 9 of them carrying candidates.
      // 🔴 THE DRAFT WINS OVER THE SELECTION, ALWAYS. `/view` PICKS a selection when the
      // caller names none, and a create draft names none -- so asking for the selection
      // first fetched the plan for whatever the server happened to pick (`source_plan|
      // dt_job` on the live config) and the editor filled with somebody else's fields
      // while its own heading said the new declaration. Reported as 「무엇을 새로 생성하든
      // 폼이 소스 dt_job으로 collapse 됨」.
      //
      // Same defect as this morning's `wafer@1` create showing `lot@1`, and the same cure:
      // ask for the subject the operator is editing, not the one the server chose. It only
      // became visible tonight because the rows moved INTO the editor -- as a list below,
      // a foreign declaration's fields read as background.
      //
      // For an edit draft the two are the same key, so preferring the draft is safe there.
      void loadAuthoring(
        payload.draft?.target_key || payload.selection?.key || selection || null);
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
    // 🔴 A CLEAN DRAFT DOES NOT FOLLOW YOU TO ANOTHER DECLARATION, and this is a defect
    // I introduced: since saving keeps the editor open, a draft is now ALWAYS open, so
    // carrying it here meant every other declaration rendered the read-only 「초안 대상은
    // X로 고정」 notice and `초안 편집` never appeared -- no way to move the editor at all,
    // with Discard removed by ruling.
    //
    // `keep` exists to protect UNSAVED typing. With nothing unsaved there is nothing to
    // protect, and holding the record only blocks the screen.
    const keptDraft = decision === 'keep' && state.dirty ? state.draft : null;
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
    // `/` jumps to the search, because the search box says it does. One listener.
    //
    // 🔴 NOT WHILE SOMEBODY IS TYPING. A field is where `/` is a character -- a JSON pointer,
    // a path, a regex -- so stealing it there would break writing to fix reading. The guard
    // asks what the event landed ON, not what the screen is doing.
    if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const el = event.target;
      const typing = el instanceof HTMLElement
        && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
      if (!typing) {
        const box = root.querySelector('.oe-search');
        if (box) {
          event.preventDefault();
          box.focus();
          box.select();
          return;
        }
      }
    }
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
    else if (action === 'start-field-text' || action === 'start-field-list'
             || action === 'start-field-object') {
      // The person picked the shape; the screen never guessed it. An empty value is
      // deliberately what lands -- the validator will now say what is missing INSIDE it,
      // and that becomes the next row. Starting a pack means `claims: {}`, and from there
      // the claim block takes over.
      editShapeAtPath(target.dataset.value,
                      action === 'start-field-list' ? []
                        : action === 'start-field-object' ? {} : '');
    }
    else if (action === 'form-name' || action === 'form-append'
             || action === 'form-remove' || action === 'form-clear') {
      // 🔴 CRUD IS READ OFF THE NODE, NOT OFF THE DECLARATION. 「폼은 모두 crud
      // 가능해야함」: every member a person can name, they can take back out. Before this
      // the screen could create a claim, a role or a qualifier and never remove one, so
      // three junk roles typed while testing could only be undone in the raw JSON editor
      // -- the editor this screen exists to stop being necessary.
      const path = target.dataset.value;
      // Taking a member out of a map and clearing an optional field are the same write:
      // the path stops being in the document. They are separate ACTIONS only because they
      // are separate sentences on screen -- `-` beside a named member means "not this
      // member", beside an optional field it means "no value here" -- and a reader of this
      // branch should not have to hold that they are two writes, because they are not.
      if (action === 'form-remove' || action === 'form-clear') {
        removeShapeAtPath(path);
      } else {
        const node = shapeForPath(path);
        if (!node || node.kind !== 'map') return;
        const empty = emptyOf(node.of, state.authoringSchema?.skeleton?.defs);
        if (action === 'form-append') {
          const held = draftShapeAt(path);
          editShapeAtPath(path, [...(Array.isArray(held) ? held : []), empty]);
        } else {
          const box = root.querySelector(`.oe-form-new-id[data-for="${path}"]`);
          const name = (box?.value || '').trim();
          if (!name) return;
          editShapeAtPath(`${path}.${name}`, empty);
          if (box) box.value = '';
        }
      }
    }
    else if (action === 'add-draft-item') {
      editShapeList(target.dataset.value, (items) => [...items, '']);
    }
    else if (action === 'remove-draft-item') {
      const at = Number(target.dataset.index);
      editShapeList(target.dataset.value, (items) => items.filter((_, i) => i !== at));
    }
    else if (action === 'add-field-item') {
      editFieldList(target.dataset.value, (items) => [...items, '']);
    }
    else if (action === 'remove-field-item') {
      const at = Number(target.dataset.index);
      editFieldList(target.dataset.value, (items) => items.filter((_, i) => i !== at));
    }
    else if (action === 'add-entity-key') {
      editEntityKeys((keys) => [...keys, '']);
    }
    else if (action === 'remove-entity-key') {
      const at = Number(target.dataset.value);
      editEntityKeys((keys) => keys.filter((_, i) => i !== at));
    }
    else if (action === 'toggle-field') {
      state = reduceFieldFold(state, { type: 'FIELD_TOGGLED', path: target.dataset.value });
      renderOntologyExplorer(root, state);
    }
    else if (action === 'delete-declaration') {
      await deleteDeclaration(target.dataset.value);
    }
    else if (action === 'edit-unread') {
      // 🔴 OPEN IT, ALWAYS. Pressing a row that then does nothing -- or answers "does not
      // exist in this snapshot" about a declaration sitting in the file -- is the 무반응
      // this screen has been fixing all day. An unread declaration is not in the index, so
      // there is nothing to select; `drafts/new` is the path that already opens an editor
      // without one, and the text comes from the row, which carries what is in the file.
      const item = state.items.find((row) => row.key === target.dataset.value);
      if (item) await openUnread(item);
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
      // 🔴 SAVE IS THE WRITE. 「저장이 곧 설정 파일 반영」 -- the owner's ruling, and the
      // reason there is no 활성화 button any more. Two calls the server already has, joined
      // behind one press: NO NEW ENDPOINT, and no confirm dialog on the one control the
      // operator uses most.
      //
      // The order is what makes a failure safe. The save lands first and its record is
      // dispatched, so if activation refuses -- a stale snapshot, a draft that no longer
      // compiles -- the config file is untouched (the activation rollback is already
      // there) and everything typed is still on screen to fix.
      const draftId = state.draft.draft_id;
      const targetKey = state.draft.target_key;
      const targetKind = state.draft.target_kind;
      const targetId = state.draft.target_id;
      try {
        const saved = await jsonRequest(`/drafts/${draftId}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            expected_revision: state.draft.revision, raw: state.editorText,
          }),
        });
        const record = saved.draft || saved;
        dispatch({ type: 'DRAFT_SAVED', draft: record });
        await jsonRequest(`/drafts/${draftId}/activate`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ expected_revision: record.revision }),
        });
        dispatch({ type: 'DRAFT_CLOSED' });
        dispatch({ type: 'AUTHORING_INVALIDATED' });
        showToast('저장했습니다.', 'success');
        await readMirror({ draft: null, selection: null, viewMode: 'active' });
        // 🔴 STAY ON WHAT YOU WERE EDITING. 「저장하고 계속 편집하던거 떠있게」 --
        // building a setup up is MANY saves, and losing your place at each one makes that
        // way of working impossible.
        //
        // 🔴 IT IS A NEW DRAFT, NOT THE OLD ONE KEPT OPEN. Saving consumes the record: it
        // is activated, its revision is spent. Holding it would make the SECOND save fail
        // on a stale revision -- and today's failures were all at the second and third
        // action, never the first.
        //
        // The re-read above happens FIRST so the new draft is based on the snapshot hash
        // the write just produced. A draft opened on the pre-write hash is refused by the
        // compare-and-swap, which is exactly this morning's 409.
        await reopenForEditing(targetKey, targetKind, targetId);
      } catch (error) { showToast(errorMessage(error), 'error'); }
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
    if (event.target.dataset.action === 'edit-draft-item') {
      const at = Number(event.target.dataset.index);
      const typed = event.target.value;
      editShapeList(event.target.dataset.value,
                    (items) => items.map((item, i) => (i === at ? typed : item)));
      return;
    }
    if (event.target.dataset.action === 'edit-shape') {
      // A relative path inside the declaration body -- `claims.<id>.roles.<name>.kind`.
      // `splitBundlePath` only strips a leading `bundle.`, so a relative path splits the
      // same way, brackets included. Same writer, same buffer, same save.
      // 🔴 A NUMBER LEAF WRITES A NUMBER. The skeleton says which leaves those are, the same
      // way it has always said which are booleans, so nothing here knows a field by name.
      // Without it `1` lands as `"1"`, the validator refuses it, and retyping cannot help --
      // measured on a preparer built from nothing.
      if (event.target.dataset.number === 'true') {
        const typed = event.target.value.trim();
        // Blank means "no value here", which is the key leaving -- not an empty string, and
        // not a 0 nobody asked for.
        if (typed === '') removeShapeAtPath(event.target.dataset.value);
        else if (Number.isFinite(Number(typed))) {
          editShapeAtPath(event.target.dataset.value, Number(typed));
        }
        return;
      }
      editShapeAtPath(event.target.dataset.value, event.target.value);
      return;
    }
    if (event.target.dataset.action === 'edit-shape-flag') {
      editShapeAtPath(event.target.dataset.value, event.target.checked);
      return;
    }
    if (event.target.dataset.action === 'edit-field-item') {
      const at = Number(event.target.dataset.index);
      const typed = event.target.value;
      editFieldList(event.target.dataset.value,
                    (items) => items.map((item, i) => (i === at ? typed : item)));
      return;
    }
    if (event.target.dataset.action === 'edit-field') {
      // Typing is never refused: whatever is in the box goes into the draft, list or no
      // list. The datalist offers the declared names; coining a new one stays possible,
      // which is the entire reason this is an input and not a `select`.
      editFieldAtPath(event.target.dataset.value, event.target.value);
      return;
    }
    if (event.target.dataset.action === 'edit-entity-key') {
      const at = Number(event.target.dataset.value);
      const typed = event.target.value;
      editEntityKeys((keys) => keys.map((k, i) => (i === at ? typed : k)));
      return;
    }
    if (event.target.dataset.action === 'new-declaration-id') {
      // Safe to re-render on every keystroke now: the reconciler keeps the focused control
      // and what is in it (`dom_patch.js`). Before it, this had to skip rendering to
      // protect the caret -- which is why the two handlers below still do.
      // 🔴 A NEW NAME NORMALISES TO LOWER CASE, AND VISIBLY (picker spec 0-b rule 3).
      // Visibly is the whole of it: normalising only in state would leave the input
      // showing what was typed while something else got saved -- the same defect as the
      // editor that silently discarded typing (`7086056`). The caret is put back because
      // the text is the same length; without that, typing into the middle of a name
      // jumps to the end on every keystroke.
      //
      // Only NEW names. Nothing here renames anything: `Lot@1` in the file stays `Lot@1`,
      // because entity and predicate spellings are atom identity (`DEDUPE_COLUMNS`).
      const typed = event.target.value;
      const normalised = typed.toLowerCase();
      if (normalised !== typed) {
        const from = event.target.selectionStart;
        const to = event.target.selectionEnd;
        event.target.value = normalised;
        if (from !== null) event.target.setSelectionRange(from, to);
      }
      dispatchNaming({ type: 'NEW_DECLARATION_TYPED', id: normalised });
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
        // Carries the editor like `select` and back/forward already do. The reducer
        // refuses to overwrite a dirty buffer regardless; this keeps every `load` caller
        // spelling the same contract, so the two do not drift apart.
        editorCheckpoint: state.dirty ? checkpoint() : null,
      }), 180);
    }
  });

  return {
    // The second caller that never carried the editor. A refresh is not a decision to
    // throw away what is being typed -- nobody asked for anything to be discarded.
    refresh: () => load({
      allowContextSwitch: true,
      editorCheckpoint: state.dirty ? checkpoint() : null,
    }),
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
