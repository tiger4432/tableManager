// Harness — committing a new tree must not cost the operator their place.
// Run: node client2/tests/dom_patch_harness.mjs
//
// WHAT IT DEFENDS. The owner reported one symptom and it contained two defects:
//
//     막 리스트 갱신한다고 새로고침 했더니 다시 페이지 맨위로 올라가있고 이럼 안됨
//
// The visible half is the scroll jump. The bigger half is that a reload was needed at
// all. This harness scores the first: a re-render must keep the DOM and mutate what
// changed, so that FOUR things survive -- scroll, focus, expand/collapse, half-typed
// text. All four reduce to one measurable property, and it is the property every
// "restore the scroll offset afterwards" patch fails:
//
//   🔴 THE LIVE NODE MUST BE THE SAME OBJECT BEFORE AND AFTER. Identity is what carries
//      scrollTop, the caret, `<details open>`, and an uncommitted input value. Nothing
//      here asserts on scrollTop directly, because a mini-DOM would let me fake it --
//      node identity is the thing that cannot be faked, and it is strictly stronger.
//
// 🔴 AND THE COUNTER-TEST IS THE POINT. A reconciler that returns the live tree untouched
// would pass every identity assertion and ship a screen that never updates. So each
// section that asserts "this survived" is paired with one asserting "this changed", and
// the last block runs the OLD implementation (`replaceChildren`) against the same cases
// to prove the assertions bite -- if they pass under a wholesale replace, they are
// measuring nothing.

let ran = 0;
let failed = 0;
const check = (name, condition, detail = '') => {
  ran += 1;
  if (!condition) { failed += 1; console.error(`✗ ${name} ${detail}`); }
};
const eq = (name, actual, expected) =>
  check(name, actual === expected, `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

// --- a DOM shim with the pieces the reconciler actually uses ----------------------
// childNodes / insertBefore / removeChild / getAttributeNames all appear in `dom_patch`,
// so a shim without them would silently skip the code under test.
let active = null;

function text(value) {
  return { nodeType: 3, nodeValue: String(value), parentNode: null };
}

function element(tag) {
  const node = {
    nodeType: 1,
    tagName: String(tag).toUpperCase(),
    childNodes: [],
    attrs: Object.create(null),
    dataset: Object.create(null),
    className: '',
    parentNode: null,
    value: undefined,
    // Not read by the reconciler -- carried so a test can prove it survived.
    scrollTop: 0,
    open: false,
    append(...items) {
      for (const item of items) {
        if (!item) continue;
        const child = typeof item === 'string' ? text(item) : item;
        child.parentNode = node;
        node.childNodes.push(child);
      }
    },
    replaceChildren(...items) {
      node.childNodes = items.filter(Boolean);
      for (const child of node.childNodes) child.parentNode = node;
    },
    removeChild(child) {
      const at = node.childNodes.indexOf(child);
      if (at >= 0) node.childNodes.splice(at, 1);
      child.parentNode = null;
      return child;
    },
    insertBefore(child, before) {
      const from = node.childNodes.indexOf(child);
      if (from >= 0) node.childNodes.splice(from, 1);
      const at = before ? node.childNodes.indexOf(before) : -1;
      if (at >= 0) node.childNodes.splice(at, 0, child);
      else node.childNodes.push(child);
      child.parentNode = node;
      return child;
    },
    setAttribute(key, value) { node.attrs[String(key)] = String(value); },
    getAttribute(key) {
      const name = String(key);
      return Object.prototype.hasOwnProperty.call(node.attrs, name) ? node.attrs[name] : null;
    },
    removeAttribute(key) { delete node.attrs[String(key)]; },
    getAttributeNames() { return Object.keys(node.attrs); },
    get textContent() {
      return node.childNodes.map((c) => (c.nodeType === 3 ? c.nodeValue : c.textContent)).join('');
    },
  };
  return node;
}

globalThis.document = { createElement: element, get activeElement() { return active; } };

const { commitTree } = await import('../src/dom_patch.js');

const el = (tag, cls, kids = [], props = {}) => {
  const node = element(tag);
  node.className = cls || '';
  Object.assign(node, props);
  node.append(...kids);
  return node;
};
const kids = (node) => node.childNodes;

// ---------------------------------------------------------------------------------
// A. The live node survives a commit that changes its content.
// Both halves matter: same object, different text.
// ---------------------------------------------------------------------------------
{
  const root = element('div');
  const panelA = el('section', 'oe-window', [el('p', 'row', [text('before')])]);
  commitTree(root, panelA, null);

  const livePanel = kids(root)[0];
  const liveRow = kids(livePanel)[0];
  livePanel.scrollTop = 420;

  const panelB = el('section', 'oe-window', [el('p', 'row', [text('after')])]);
  commitTree(root, panelB, null);

  check('A1 panel is the same object after a commit', kids(root)[0] === livePanel);
  check('A2 row is the same object after a commit', kids(kids(root)[0])[0] === liveRow);
  eq('A3 scroll position survived', kids(root)[0].scrollTop, 420);
  eq('A4 but the content actually updated', kids(root)[0].textContent, 'after');
}

// ---------------------------------------------------------------------------------
// B. The focused control owns its own value.
// The tree being committed is one keystroke behind by construction; writing it back is
// how the repair for a scroll jump deletes the character just typed.
// ---------------------------------------------------------------------------------
{
  const root = element('div');
  const build = (query) => el('section', 'oe-window', [
    el('input', 'oe-search', [], { value: query, dataset: { action: 'search' } }),
    el('input', 'oe-other', [], { value: 'untouched', dataset: { action: 'other' } }),
  ]);
  commitTree(root, build(''), null);

  const search = kids(kids(root)[0])[0];
  const other = kids(kids(root)[0])[1];
  search.value = 'dt_lo';          // the operator has typed; state has not caught up
  active = search;

  commitTree(root, build(''), search);

  eq('B1 focused control keeps what was typed', search.value, 'dt_lo');
  check('B2 focused control was not replaced', kids(kids(root)[0])[0] === search);

  // The counter-half: an UNFOCUSED control must still follow state, or the reconciler is
  // just refusing to update inputs.
  const next = build('');
  next.childNodes[1].value = 'from-state';
  commitTree(root, next, search);
  eq('B3 unfocused control does follow state', other.value, 'from-state');
  active = null;
}

// ---------------------------------------------------------------------------------
// C. Expand/collapse state lives in the DOM and must outlive a commit.
// This is the one that makes the collapse feature and a wholesale re-render hostile to
// each other: ship collapsing on a panel that rebuilds and it folds itself shut.
// ---------------------------------------------------------------------------------
{
  const root = element('div');
  const build = (label) => el('section', 'oe-window', [
    el('details', 'oe-layer', [el('summary', '', [text(label)])], { dataset: { key: 'profiles' } }),
  ]);
  commitTree(root, build('프로필 · 2'), null);

  const details = kids(kids(root)[0])[0];
  details.open = true;                       // the operator opened it

  commitTree(root, build('프로필 · 3'), null);

  check('C1 open section stayed open', kids(kids(root)[0])[0].open === true);
  eq('C2 and its heading still updated', kids(root)[0].textContent, '프로필 · 3');
}

// ---------------------------------------------------------------------------------
// D. Removal and reordering.
// A reconciler that never removes anything would pass A-C and grow the page forever.
// ---------------------------------------------------------------------------------
{
  const root = element('div');
  const rows = (ids) => el('section', 'oe-window',
    ids.map((id) => el('div', 'oe-row', [text(id)], { dataset: { key: id } })));

  commitTree(root, rows(['a', 'b', 'c']), null);
  const first = kids(kids(root)[0])[0];
  const third = kids(kids(root)[0])[2];

  commitTree(root, rows(['a', 'c']), null);
  eq('D1 removed row is gone', kids(kids(root)[0]).length, 2);
  check('D2 surviving keyed row kept its identity', kids(kids(root)[0])[0] === first);
  check('D3 keyed row survived losing a sibling before it', kids(kids(root)[0])[1] === third);

  commitTree(root, rows(['c', 'a']), null);
  eq('D4 reorder produced the new order',
    kids(kids(root)[0]).map((n) => n.textContent).join(','), 'c,a');
  check('D5 reorder MOVED nodes rather than rebuilding them',
    kids(kids(root)[0])[0] === third && kids(kids(root)[0])[1] === first);
}

// ---------------------------------------------------------------------------------
// E. dataset must not go stale. Every click in this panel routes on `data-action`, so a
// carried-over stale key silently rewires a button to the previous action.
// ---------------------------------------------------------------------------------
{
  const root = element('div');
  const build = (action, value) => el('section', 'oe-window', [
    el('button', 'oe-act', [text('go')], { dataset: { key: 'act', action, value } }),
  ]);
  commitTree(root, build('open-draft', '7'), null);
  const btn = kids(kids(root)[0])[0];

  commitTree(root, build('discard-draft', '9'), null);
  eq('E1 action followed the new tree', btn.dataset.action, 'discard-draft');
  eq('E2 value followed the new tree', btn.dataset.value, '9');

  const bare = el('section', 'oe-window', [
    el('button', 'oe-act', [text('go')], { dataset: { key: 'act' } }),
  ]);
  commitTree(root, bare, null);
  eq('E3 dropped dataset key is removed, not left behind',
    kids(kids(root)[0])[0].dataset.action, undefined);
}

// ---------------------------------------------------------------------------------
// G. 🔴 AN INSERTION AHEAD OF A CONTAINER MUST NOT RENUMBER IT.
//
// This case is here because THIS HARNESS STAYED GREEN THROUGH THE REAL DEFECT. The first
// implementation keyed children on absolute position; the explorer prepends an error
// banner into `.oe-window` when a request fails, that one extra child shifted every
// sibling after it, `.oe-main` stopped matching itself, the whole tree was rebuilt, and
// the scroll was lost -- the exact symptom the module exists to remove, arriving inside
// its own repair. Found by driving the real view in a real browser, not here.
//
// Nothing above shifted a sibling, so nothing above could see it. That is the lesson
// worth more than the fix: sections A-F all rendered the SAME SHAPE twice.
// ---------------------------------------------------------------------------------
{
  const root = element('div');
  const build = (withBanner) => el('section', 'oe-window', [
    ...(withBanner ? [el('div', 'oe-error', [text('재적용 실패')])] : []),
    el('div', 'oe-main', [el('nav', 'oe-tree', [text('packs')])]),
  ]);

  commitTree(root, build(false), null);
  const main = kids(kids(root)[0])[0];
  const tree = kids(main)[0];
  main.scrollTop = 90;

  commitTree(root, build(true), null);

  const win = kids(root)[0];
  check('G1 the banner really was inserted', win.textContent.includes('재적용 실패'));
  eq('G2 window now has two children', kids(win).length, 2);
  check('G3 the shifted container kept its identity', kids(win)[1] === main);
  check('G4 and so did its subtree', kids(kids(win)[1])[0] === tree);
  eq('G5 scroll survived the insertion above it', kids(win)[1].scrollTop, 90);

  // And removing the banner must shift it back without rebuilding either.
  commitTree(root, build(false), null);
  check('G6 identity survived the banner going away too', kids(kids(root)[0])[0] === main);
  eq('G7 scroll still survived', main.scrollTop, 90);
}

// ---------------------------------------------------------------------------------
// F. 🔴 THE ASSERTIONS BITE. Run the OLD commit (`replaceChildren`) against the same
// cases. Every survival claim above must FAIL under it -- otherwise this harness would
// have stayed green through the defect the owner reported, which is the only outcome
// that would make it worthless.
// ---------------------------------------------------------------------------------
{
  const replaceCommit = (root, tree) => root.replaceChildren(tree);

  const root = element('div');
  replaceCommit(root, el('section', 'oe-window', [el('p', 'row', [text('before')])]));
  const livePanel = kids(root)[0];
  livePanel.scrollTop = 420;
  replaceCommit(root, el('section', 'oe-window', [el('p', 'row', [text('after')])]));

  check('F1 under the old commit the panel is a DIFFERENT object',
    kids(root)[0] !== livePanel);
  check('F2 under the old commit scroll is lost', kids(root)[0].scrollTop === 0);

  const droot = element('div');
  const build = (label) => el('section', 'oe-window', [
    el('details', 'oe-layer', [el('summary', '', [text(label)])], { dataset: { key: 'p' } }),
  ]);
  replaceCommit(droot, build('a'));
  kids(kids(droot)[0])[0].open = true;
  replaceCommit(droot, build('b'));
  check('F3 under the old commit an open section folds shut',
    kids(kids(droot)[0])[0].open === false);
}

// The runner's contract: one machine line from this harness's OWN counters. Taken from
// `check_harnesses.mjs`, not from memory -- a prose summary exits 0 having proved nothing,
// which the gate reads as death rather than as a pass.
console.log(`ASSERTIONS ${ran} ${failed}`);
if (failed) process.exit(1);
