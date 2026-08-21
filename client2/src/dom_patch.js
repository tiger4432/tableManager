// Commit a freshly built element tree onto a LIVE one by mutating what differs.
//
// 🔴 WHY THIS EXISTS, IN THE OWNER'S OWN WORDS (2026-08-19):
//
//     막 리스트 갱신한다고 새로고침 했더니 다시 페이지 맨위로 올라가있고 이럼 안됨
//
// The explorer panel rebuilt its whole DOM on every state change and committed it with
// `root.replaceChildren(...)`. That is correct output and destroyed everything the
// operator had accumulated. FOUR things die in a wholesale replace, and scroll -- the one
// that got reported -- is only the most visible:
//
//   * scroll position        the reported symptom
//   * focus                  the caret vanishes mid-entry; the next keystroke goes nowhere
//   * expand/collapse state  every section re-opens by hand after any change
//   * half-entered values    text typed and not yet committed is wiped
//
// 🔴 DO NOT "SAVE THE SCROLL OFFSET AND RESTORE IT AFTER RENDER". That is a patch on the
// wrong layer: it restores one of the four, races the layout, and still blows away focus
// and in-progress typing. The fix is to keep the DOM and mutate what changed.
//
// 🔴 AND IT IS A PREREQUISITE, NOT A POLISH. The collapse work and a wholesale re-render
// are actively hostile to each other -- ship collapsing on top of a panel that rebuilds
// itself and you have built a screen that folds itself shut whenever anything changes.
//
// The seam is deliberate: every `render*` function in the view keeps producing a fresh
// detached tree, exactly as before, and only the COMMIT step changes. Rewriting 562 lines
// of view code into targeted mutations would put the same requirement in every one of
// them, where it would be forgotten one function at a time.

/** Elements whose visible value lives in the DOM, not in the tree we just built. */
const FORM_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT']);

const isElement = (node) => node && node.nodeType === 1;
const isText = (node) => node && node.nodeType === 3;

/**
 * What kind of slot this child is, ignoring where it sits.
 *
 * Anything that must survive reordering says so with `data-key`; `data-action` is the next
 * best thing, because the controller already routes on it and it is unique per control.
 */
function signatureOf(node) {
  if (isText(node)) return '#text';
  if (!isElement(node)) return '#other';
  const data = node.dataset || {};
  if (data.key) return `k:${data.key}`;
  if (data.action) return `a:${data.action}:${data.value ?? ''}`;
  return `t:${node.tagName}.${node.className || ''}`;
}

/**
 * Keys for one child list: signature plus HOW MANY SIBLINGS OF THE SAME SIGNATURE come
 * before it.
 *
 * 🔴 NOT THE ABSOLUTE INDEX, AND THIS COST A REAL DEFECT. The first version keyed on
 * absolute position, which is fine until something is INSERTED ahead of a container. The
 * explorer prepends an error banner into `.oe-window` when a request fails, and that one
 * extra child renumbered every sibling after it -- so `.oe-main` at position 2 no longer
 * matched `.oe-main` at position 3, the whole tree was rebuilt, and the operator's scroll
 * was lost. That is precisely the symptom this module exists to remove, reappearing inside
 * its own repair, and only a real browser found it: the shim harness never rendered a
 * banner, so it never shifted anything.
 *
 * Counting occurrences of the same signature keeps both properties. `.oe-main` is still
 * the first `.oe-main` no matter what appears before it, while two unkeyed `<div
 * class="oe-row">` siblings stay distinguishable from each other and so still reconcile
 * positionally among themselves -- the honest answer when nothing distinguishes them.
 */
function keysFor(nodes) {
  const seen = new Map();
  return nodes.map((node) => {
    const signature = signatureOf(node);
    const nth = seen.get(signature) || 0;
    seen.set(signature, nth + 1);
    return `${signature}#${nth}`;
  });
}

function attributeNames(node) {
  if (typeof node.getAttributeNames === 'function') return node.getAttributeNames();
  return Object.keys(node.attrs || {});
}

function syncAttributes(live, next) {
  const wanted = attributeNames(next);
  for (const name of wanted) {
    const value = next.getAttribute(name);
    if (live.getAttribute(name) !== value) live.setAttribute(name, value);
  }
  const seen = new Set(wanted);
  for (const name of attributeNames(live)) {
    if (!seen.has(name)) live.removeAttribute(name);
  }
  if (live.className !== next.className) live.className = next.className;
  // `dataset` is how the controller routes every click, so a stale key silently rewires
  // a button to the previous action rather than breaking loudly.
  const nextData = next.dataset || {};
  const liveData = live.dataset || {};
  for (const name of Object.keys(nextData)) {
    if (liveData[name] !== nextData[name]) liveData[name] = nextData[name];
  }
  for (const name of Object.keys(liveData)) {
    if (!(name in nextData)) delete liveData[name];
  }
}

/**
 * Carry over control state without stepping on the person using it.
 *
 * 🔴 THE FOCUSED CONTROL IS THE AUTHORITY ON ITS OWN VALUE. The tree we are committing was
 * built from state that is, by one keystroke, older than what the operator has typed.
 * Writing it back would delete the character they just entered and move the caret to the
 * end -- which is the "half-entered values" failure, arriving through the repair for it.
 *
 * 🔴 A `select` IS NOT BEING TYPED INTO, AND IT KEEPS FOCUS AFTER A CHOICE. There is no
 * half-entered state in a dropdown: the choice is whole the instant it is made, and the
 * state we are committing already contains it. But the element STAYS focused afterwards,
 * so the typing guard applied to it forever after -- its value was never resynced again
 * while its `<option>` children were rebuilt underneath it. Text boxes keep the guard;
 * that protection is the reason it exists and it is untouched.
 */
function syncFormState(live, next, activeElement) {
  if (!FORM_TAGS.has(live.tagName)) return;
  if (live === activeElement && live.tagName !== 'SELECT') return;
  if (next.value !== undefined && live.value !== next.value) live.value = next.value;
  if (next.checked !== undefined && live.checked !== next.checked) live.checked = next.checked;
  if (next.disabled !== undefined && live.disabled !== next.disabled) {
    live.disabled = next.disabled;
  }
}

function childrenOf(node) {
  if (node.childNodes) return Array.from(node.childNodes);
  return Array.from(node.children || []);
}

/**
 * Reconcile one pair. Returns the node that should occupy this slot -- `live` when it was
 * patched in place, `next` when the two were too different to reconcile.
 */
function patchNode(live, next, activeElement) {
  if (isText(live) && isText(next)) {
    if (live.nodeValue !== next.nodeValue) live.nodeValue = next.nodeValue;
    return live;
  }
  if (!isElement(live) || !isElement(next) || live.tagName !== next.tagName) return next;
  syncAttributes(live, next);
  patchChildren(live, next, activeElement);
  // 🔴 THE VALUE IS WRITTEN AFTER THE CHILDREN, AND THIS IS THE OTHER HALF OF THE DEFECT.
  //
  // A `select`'s value is only meaningful against the `<option>` list it currently holds,
  // and this panel CHANGES that list on the very render that follows a choice: the current
  // value is always offered as an option, so an empty field renders `['', ...list]` and
  // stops prepending the blank the moment something is chosen. Reconciling those children
  // positionally then shifts every option up by one -- the live element keeps its
  // `selectedIndex`, so the row silently reads as the NEXT value down.
  //
  // Measured on the live screen with nothing focused, so it is not the guard above and not
  // an instrument artefact: options `['', 'group', 'row']`, chose `group`, the draft
  // recorded `group`, and the box showed `row`. Syncing before the children could not see
  // it -- the old and new values were both `group` and it correctly did nothing.
  //
  // Last is also the safe order for the other two tags: an `input` has no element children
  // and a `textarea`'s text child is its DEFAULT value, so writing the live value after
  // that child settles can only be more correct, never less.
  syncFormState(live, next, activeElement);
  return live;
}

function patchChildren(live, next, activeElement) {
  const liveNodes = childrenOf(live);
  const nextNodes = childrenOf(next);

  const liveKeys = keysFor(liveNodes);
  const nextKeys = keysFor(nextNodes);

  const pool = new Map();
  liveNodes.forEach((node, index) => {
    const key = liveKeys[index];
    if (!pool.has(key)) pool.set(key, []);
    pool.get(key).push(node);
  });

  const settled = nextNodes.map((nextNode, index) => {
    const bucket = pool.get(nextKeys[index]);
    const match = bucket && bucket.length ? bucket.shift() : null;
    return match ? patchNode(match, nextNode, activeElement) : nextNode;
  });

  const keep = new Set(settled);
  for (const node of liveNodes) {
    if (!keep.has(node)) live.removeChild(node);
  }
  // 🔴 MOVE ONLY WHAT IS OUT OF PLACE. Re-inserting a node that is already in position is
  // not a no-op in a real browser: moving the focused element blurs it, which would bring
  // back the exact defect this module exists to remove.
  settled.forEach((node, index) => {
    const current = childrenOf(live)[index];
    if (current !== node) live.insertBefore(node, current || null);
  });
}

/**
 * Commit `nextTree` into `root`, keeping every live node that can be reused.
 *
 * Drop-in for `root.replaceChildren(nextTree)`; the first commit into an empty root is
 * exactly that, and every later one mutates.
 */
export function commitTree(root, nextTree, activeElement) {
  const active = activeElement !== undefined
    ? activeElement
    : (typeof document !== 'undefined' ? document.activeElement : null);
  const existing = childrenOf(root);
  if (existing.length !== 1) {
    root.replaceChildren(nextTree);
    return nextTree;
  }
  const settled = patchNode(existing[0], nextTree, active);
  if (settled !== existing[0]) root.replaceChildren(settled);
  return settled;
}
