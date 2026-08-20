// Contract harness for the Ontology Config Explorer state axes.
// Run: node client2/tests/ontology_explorer_harness.mjs
import {
  initialExplorerState, reduceExplorerState, assertOneContext, canLeaveSelection,
  dirtyNavigationDecision, isDraftRevisionEditable, mirrorLoaded, reduceNewDeclaration,
  restoreDirtyEditorCheckpoint, sectionMembers,
} from '../src/ontology_explorer_store.js';

let ran = 0;
let failed = 0;
const check = (name, condition) => {
  ran += 1;
  if (!condition) { failed += 1; console.error(`✗ ${name}`); }
};

const node = (key, token) => ({
  key, canonical_id: key, kind: 'entity', context_token: token,
  raw: {}, compiled: {}, compile_status: 'valid',
});
const payload = (token, selected = 'entity|A@1') => ({
  context_token: token,
  view_context: { mode: 'active', context_token: token },
  active_snapshot: { snapshot_hash: token.split(':')[1], valid: true },
  selection: node(selected, token),
  items: [node('entity|A@1', token), node('entity|B@1', token)],
  nodes: [node(selected, token)],
  outbound: [], used_by: [], integrity: [], page: 1, total: 2,
  changes: [], edge_changes: [],
});

{
  const good = payload('active:aaa');
  check('C1 one token accepted', assertOneContext(good) === 'active:aaa');
  const bad = payload('active:aaa');
  bad.items[1].context_token = 'active:bbb';
  let rejected = false;
  try { assertOneContext(bad); } catch (_) { rejected = true; }
  check('C2 mixed snapshot token rejected', rejected);
  const badIntegrity = payload('active:aaa');
  badIntegrity.integrity = [{ code: 'x', context_token: 'active:bbb' }];
  rejected = false;
  try { assertOneContext(badIntegrity); } catch (_) { rejected = true; }
  check('C3 mixed validation token rejected', rejected);
  rejected = false;
  try {
    reduceExplorerState(
      { ...initialExplorerState, requestGeneration: 1 },
      {
        type: 'RESPONSE_RECEIVED', generation: 1, payload: payload('active:aaa'),
        expectedSelection: 'entity|B@1',
      },
    );
  } catch (_) { rejected = true; }
  check('C4 mismatched requested selection rejected', rejected);
}

{
  let state = reduceExplorerState(initialExplorerState, { type: 'REQUEST_STARTED', generation: 2 });
  state = reduceExplorerState(state, {
    type: 'RESPONSE_RECEIVED', generation: 1, payload: payload('active:old'),
  });
  check('R1 stale response cannot install old snapshot', state.activeSnapshot === null);
  state = reduceExplorerState(state, {
    type: 'RESPONSE_RECEIVED', generation: 2, payload: payload('active:new'),
  });
  check('R2 current response installs snapshot', state.activeSnapshot.snapshot_hash === 'new');
  check('R3 selected kind is retained', state.selection.kind === 'entity');
  state = reduceExplorerState(state, { type: 'REQUEST_STARTED', generation: 3 });
  state = reduceExplorerState(state, {
    type: 'REQUEST_FAILED', generation: 3, code: 'unknown_selection', message: 'removed',
    selection: 'entity|A@1',
  });
  check('R4 removed selection cannot leave stale Inspector', state.selection === null && state.nodes.length === 0);
  check('R5 removed selection has explicit state', state.removedSelection.status === 'removed_or_unresolved');

  const changedEdge = {
    edge_id: 'edge-modified', from_key: 'entity|A@1', to_key: 'entity|B@1',
    status: 'resolved', change_status: 'modified', context_token: 'draft:d1:1:preview',
  };
  const changedPayload = payload('draft:d1:1:preview');
  changedPayload.view_context.mode = 'draft_preview';
  changedPayload.outbound = [changedEdge];
  changedPayload.edge_changes = [changedEdge];
  state = reduceExplorerState(
    { ...initialExplorerState, requestGeneration: 4 },
    { type: 'RESPONSE_RECEIVED', generation: 4, payload: changedPayload },
  );
  check('R6 modified edge survives API state for flow and change list',
    state.outbound[0].change_status === 'modified'
      && state.edgeChanges[0].change_status === 'modified');
}

{
  let state = reduceExplorerState(initialExplorerState, { type: 'REQUEST_STARTED', generation: 1 });
  state = reduceExplorerState(state, {
    type: 'RESPONSE_RECEIVED', generation: 1, payload: payload('active:nav'),
  });
  state = reduceExplorerState(state, { type: 'NAVIGATE_TO', key: 'entity|B@1' });
  check('N1 navigation records previous selection', state.navigation.back[0].key === 'entity|A@1');
  state = { ...state, selection: node('entity|B@1', 'active:nav') };
  state = reduceExplorerState(state, { type: 'NAVIGATE_BACK' });
  check('N2 back restores exact node key', state.pendingNavigation.key === 'entity|A@1');
  check('N3 back preserves forward history', state.navigation.forward[0].key === 'entity|B@1');
  state = reduceExplorerState(state, { type: 'NAVIGATE_FORWARD' });
  check('N4 forward restores exact node key', state.pendingNavigation.key === 'entity|B@1');

  const custom = {
    key: 'entity|A@1', query: 'lot', detailTab: 'usage',
    treeScroll: 120, workspaceScroll: 340, editorSelectionStart: 7,
    editorSelectionEnd: 11, viewPreference: 'draft_preview',
    route: { path_id: 'edge:7', node_keys: ['entity|A@1', 'entity|B@1'], edge_ids: ['edge-7'] },
    contextToken: 'draft:d1:4:preview',
    viaEdge: 'edge-7',
  };
  state = reduceExplorerState({ ...state, navigation: { back: [custom], forward: [] } }, {
    type: 'NAVIGATE_BACK', current: { key: 'entity|B@1' },
  });
  check('N5 history preserves tab and scroll', state.pendingNavigation.detailTab === 'usage'
    && state.pendingNavigation.treeScroll === 120 && state.pendingNavigation.workspaceScroll === 340);
  check('N6 history preserves route edge evidence', state.pendingNavigation.viaEdge === 'edge-7');
  check('N7 history preserves active/draft mode and editor cursor',
    state.pendingNavigation.viewPreference === 'draft_preview'
      && state.pendingNavigation.editorSelectionStart === 7
      && state.pendingNavigation.editorSelectionEnd === 11);
  check('N8 history preserves exact compiled route', state.pendingNavigation.route.path_id === 'edge:7');
  check('N9 history preserves exact context token', state.pendingNavigation.contextToken === 'draft:d1:4:preview');
}

{
  const dirty = { ...initialExplorerState, dirty: true };
  check('D1 dirty draft can cancel movement', !canLeaveSelection(dirty, () => false));
  check('D2 dirty draft can explicitly discard and move', canLeaveSelection(dirty, () => true));
  check('D3 clean state moves without prompt result', canLeaveSelection(initialExplorerState, () => false));
  const opened = reduceExplorerState(initialExplorerState, {
    type: 'DRAFT_OPENED', draft: { raw: { status: 'active' }, revision: 0 },
  });
  check('D4 draft editor uses deterministic JSON', opened.editorText === '{\n  "status": "active"\n}');
  const edited = reduceExplorerState(opened, { type: 'EDITOR_CHANGED', text: '{}' });
  check('D5 editor change marks draft dirty', edited.dirty && edited.editorText === '{}');
  check('D6 dirty move can keep draft', dirtyNavigationDecision(edited, () => 'keep') === 'keep');
  check('D7 dirty move can discard draft', dirtyNavigationDecision(edited, () => 'discard') === 'discard');
  check('D8 dirty move can cancel', dirtyNavigationDecision(edited, () => 'cancel') === 'cancel');
  check('D9 unknown dirty decision fails closed', dirtyNavigationDecision(edited, () => 'other') === 'cancel');
  const reviewed = {
    ...opened,
    draft: { ...opened.draft, lifecycle_status: 'review_requested' },
  };
  check('D10 reviewed revision is not editable', !isDraftRevisionEditable(reviewed.draft));
  const attemptedEdit = reduceExplorerState(reviewed, { type: 'EDITOR_CHANGED', text: '{"changed":true}' });
  check('D11 reviewed revision ignores editor mutations', attemptedEdit.editorText === reviewed.editorText && !attemptedEdit.dirty);

  const activeDraftState = {
    ...edited,
    draft: {
      draft_id: 'draft-1', revision: 4, target_key: 'entity|A@1',
      raw: { status: 'active' }, lifecycle_status: 'saved',
    },
    viewContext: { mode: 'active', context_token: 'active:aaa' },
    viewPreference: 'active',
    editorText: '{"AUDIT_UNSAVED_KEEP_MARKER":true}',
    dirty: true,
  };
  const dirtyCheckpoint = {
    editorText: activeDraftState.editorText, dirty: true,
    editorSelectionStart: 8, editorSelectionEnd: 20,
    draftId: 'draft-1', draftRevision: 4, draftTargetKey: 'entity|A@1',
    viewPreference: 'active', contextToken: 'active:aaa',
  };
  const serverReloaded = {
    ...activeDraftState,
    editorText: '{"status":"last-server-save"}', dirty: false,
  };
  const restored = restoreDirtyEditorCheckpoint(serverReloaded, dirtyCheckpoint);
  check('D12 keep/back restores exact unsaved editor buffer',
    restored.dirty && restored.editorText === activeDraftState.editorText);
  check('D13 keep/back preserves pinned draft identity',
    restored.draft.draft_id === 'draft-1'
      && restored.draft.revision === 4
      && restored.draft.target_key === 'entity|A@1');
  const restoredAgain = restoreDirtyEditorCheckpoint(
    { ...restored, editorText: '{"status":"last-server-save"}', dirty: false },
    dirtyCheckpoint,
  );
  check('D14 repeated forward/back restores the same buffer',
    restoredAgain.dirty && restoredAgain.editorText === dirtyCheckpoint.editorText);
  check('D15 stale context cannot restore a dirty buffer',
    restoreDirtyEditorCheckpoint(serverReloaded, {
      ...dirtyCheckpoint, contextToken: 'draft:draft-1:4:stale',
    }).editorText === serverReloaded.editorText);
  check('D16 changed draft revision cannot restore a dirty buffer',
    restoreDirtyEditorCheckpoint(serverReloaded, {
      ...dirtyCheckpoint, draftRevision: 3,
    }).editorText === serverReloaded.editorText);
}

// --- E. Naming a declaration that does not exist yet ------------------------------
//
// The screen could EDIT a declaration and could not MAKE one, so a new source had to be
// typed into `ledger_config.json` by hand. These score the LOCAL half -- the name being
// chosen, before any server has accepted it.
//
// 🔴 THE NAME BEING TYPED IS NOT PART OF THE MIRROR. `items` reflects what the server has;
// a name nobody has accepted is not that, and merging them is how a REFUSED create goes on
// showing in the tree as though it existed. E1 and E6 pin the separation.
//
// The rendered half -- an entry point on every authorable section including empty ones,
// and the caret surviving a keystroke re-render -- is verified in a real browser rather
// than here: a shim models `activeElement` and `selectionStart` as plain properties, so it
// would report them preserved whatever the code did.
{
  const base = { ...initialExplorerState, items: [{ key: 'pack|only@1', kind: 'pack' }] };

  const opened = reduceNewDeclaration(base, { type: 'NEW_DECLARATION_OPENED', kind: 'entity' });
  check('E1 opening names a kind and touches nothing the server mirrors',
    opened.newDeclaration.kind === 'entity' && opened.newDeclaration.id === ''
    && opened.items === base.items);

  const typed = reduceNewDeclaration(opened, { type: 'NEW_DECLARATION_TYPED', id: 'DTJob@1' });
  check('E2 typing keeps the kind and records the id',
    typed.newDeclaration.kind === 'entity' && typed.newDeclaration.id === 'DTJob@1');

  const refused = reduceNewDeclaration(typed, {
    type: 'NEW_DECLARATION_FAILED', message: '이미 선언됨' });
  check('E3 a refusal stays ON the row, with the name still there to edit',
    refused.newDeclaration.error === '이미 선언됨'
    && refused.newDeclaration.id === 'DTJob@1');

  // The operator's next move after a refusal is to change the name. A message about the
  // PREVIOUS name, still on screen while they retype, is worse than none.
  const retyped = reduceNewDeclaration(refused, { type: 'NEW_DECLARATION_TYPED', id: 'DTJob@2' });
  check('E4 editing the name clears the refusal it was about',
    retyped.newDeclaration.error === null && retyped.newDeclaration.id === 'DTJob@2');

  check('E5 closing drops the whole naming state',
    reduceNewDeclaration(retyped, { type: 'NEW_DECLARATION_CLOSED' }).newDeclaration === null);

  // 🔴 The counter-test: without this the reducer could simply return `state` for
  // everything and E1-E5 would still need it to do something. Typing with nothing open
  // must NOT invent a naming state out of a stray event.
  check('E6 typing with nothing open invents no declaration',
    reduceNewDeclaration(base, { type: 'NEW_DECLARATION_TYPED', id: 'ghost@1' })
      .newDeclaration === null);
  check('E7 a failure with nothing open invents no declaration',
    reduceNewDeclaration(base, { type: 'NEW_DECLARATION_FAILED', message: 'x' })
      .newDeclaration === null);
  check('E8 an unrelated action leaves the naming state exactly as it was',
    reduceNewDeclaration(typed, { type: 'TAB_CHANGED', tab: 'raw' }) === typed);
}

// --- F. the mirror: one source for what is declared ------------------------------
//
// Every picker from step 5 onward reads `sectionMembers` and holds no copy. These pin the
// two properties that make that safe, and both are things a plausible implementation gets
// wrong in a way no test would notice without them.
{
  const plan = {
    sections: { packs: ['a@1', 'b@1'], entities: ['E@1'], vocabulary: [],
                mappers: [], profiles: [], sources: [], source_preparers: [] },
    fields: [], steps: [],
  };
  // `items` is what the TREE renders: paged at 100 and narrowed by the search box.
  const state = {
    ...initialExplorerState, authoring: plan,
    items: [{ key: 'pack|a@1', kind: 'pack', canonical_id: 'a@1' }],
    newDeclaration: { kind: 'pack', id: 'typing@1', error: null },
  };

  check('F1 members come from the plan, unpaged and unfiltered',
    sectionMembers(state, 'packs').join(',') === 'a@1,b@1');

  // 🔴 THE DEFECT THIS PREVENTS IS SILENT. A picker fed from `state.items` would have
  // WORKED in every test where nothing was filtered, then offered a subset the moment
  // somebody typed in the search box -- not an error, not empty, just fewer options than
  // exist, with nothing on screen to tell the operator.
  check('F2 members are NOT the filtered tree page',
    sectionMembers(state, 'packs').length > state.items.length);

  // 🔴 The name being typed is not declared. Merging it would let a profile point at a
  // pack the server never accepted, and a REFUSED create would keep showing as real.
  check('F3 the declaration being typed is never offered as existing',
    !sectionMembers(state, 'packs').includes('typing@1'));

  check('F4 an unknown section is empty rather than undefined',
    Array.isArray(sectionMembers(state, 'nope')) && sectionMembers(state, 'nope').length === 0);
  check('F5 called without a section it returns the whole map',
    Object.keys(sectionMembers(state)).length === 7);

  // "Nothing declared" and "not read yet" render as the same empty list and mean opposite
  // things -- one is a prerequisite to state, the other is a spinner.
  check('F6 an unread mirror is distinguishable from an empty one',
    mirrorLoaded(state) === true && mirrorLoaded(initialExplorerState) === false);
  check('F7 a mirror with all-empty sections still counts as read',
    mirrorLoaded({ ...initialExplorerState,
      authoring: { sections: { packs: [] } } }) === true);
}

// --- G. the empty config must survive the whole client path -----------------------
//
// 🔴 THE SAME MISTAKE IN FOUR PLACES, and each one was found by the owner rather than by a
// test. "There is no selection" was read as "the selection is wrong" by the context check,
// and as "read `.key` off it" by the reducer. Both were correct for as long as a config
// always had declarations; both broke the day bootstrap made empty the STARTING state.
//
// Scored on the payload the server actually sends for an empty config, not on a
// hand-trimmed one, so a field appearing there later is covered too.
{
  const token = 'active:abc12345';
  const emptyPayload = {
    context_token: token,
    view_context: { mode: 'active', context_token: token },
    active_snapshot: { snapshot_hash: 'abc12345', compiled_at: 'now', valid: true },
    selection: null,
    items: [], nodes: [], outbound: [], used_by: [],
    outbound_total: 0, used_by_total: 0, reference_limit: 200,
    references_truncated: false, integrity: [],
    changes: [], edge_changes: [], page: 1, limit: 100, total: 0,
  };

  let accepted = true;
  try { assertOneContext(emptyPayload); } catch { accepted = false; }
  check('G1 an absent selection is not a mismatched one', accepted);

  let next = null, threw = null;
  try {
    next = reduceExplorerState(initialExplorerState,
      { type: 'RESPONSE_RECEIVED', generation: 0, payload: emptyPayload });
  } catch (error) { threw = error; }
  check('G2 the reducer survives a response with nothing selected',
    threw === null, threw && threw.message);
  check('G3 and it keeps the snapshot, which is what the create button needs',
    next?.activeSnapshot?.snapshot_hash === 'abc12345');
  check('G4 no selection means no root path, rather than a path to nothing',
    next?.currentPath === null);
  check('G5 the empty view is empty, not unread',
    Array.isArray(next?.items) && next.items.length === 0 && next.total === 0);

  // 🔴 The counter-half: a selection that IS present and DOES disagree must still be
  // refused, or the fix traded one silent failure for another.
  let refused = false;
  try {
    assertOneContext({ ...emptyPayload,
      selection: { key: 'entity|E@1', context_token: 'active:other' } });
  } catch { refused = true; }
  check('G6 a selection carrying the wrong token is still refused', refused);
}

console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
