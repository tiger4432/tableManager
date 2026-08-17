// Contract harness for the Ontology Config Explorer state axes.
// Run: node client2/tests/ontology_explorer_harness.mjs
import {
  initialExplorerState, reduceExplorerState, assertOneContext, canLeaveSelection,
  dirtyNavigationDecision, isDraftRevisionEditable,
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
  outbound: [], used_by: [], path_candidates: [], integrity: [], page: 1, total: 2,
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
}

console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
