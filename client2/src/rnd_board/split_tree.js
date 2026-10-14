// THE PAGE'S SPLIT TREE (lead 10-13, owner «화면은 계속 확장가능한 그리드야»): Spotfire's page is a tree of splits - each
// split lays its children side by side ('row') or stacked ('column'), each child a share (`size`, a weight); a leaf is
// one panel by id. Docking on an edge splits the target; closing one gives its share back to its siblings. Pure - no
// DOM - so every edit is scored on data; the shell (grid_shell.js) draws the tree and calls these.
//
// node   { id }  a leaf  |  { split: 'row' | 'column', children: [node & { size }] }
// edge   'left' | 'right' | 'top' | 'bottom' | 'center' (a drop on a part's middle - the two swap places)

const DIR = { left: 'row', right: 'row', top: 'column', bottom: 'column' };
/** A panel keeps its title row and a little of its body (a Spotfire title row is 43 with its padding). */
export const MIN_SIZE = 60;
/** A drop this near a part's side (a share of the side across it) lands on that edge; farther in, on its middle. */
export const DROP_EDGE = 0.25;

/** Every leaf's id, left to right, top to bottom. */
export function leafIds(node) {
  if (!node) return [];
  return node.split ? node.children.flatMap(leafIds) : [node.id];
}

/** The child indices from the root to a leaf (a node the tree holds), or null. */
export function pathTo(node, id, at = []) {
  if (!node) return null;
  if (!node.split) return node.id === id ? at : null;
  for (let i = 0; i < node.children.length; i += 1) {
    const got = pathTo(node.children[i], id, [...at, i]);
    if (got) return got;
  }
  return null;
}

/** The node at a path. */
export function nodeAt(node, path) {
  return path.reduce((n, i) => (n && n.split ? n.children[i] : null), node);
}

/** A split of one child is that child (in its parent's share); a split of none is gone. */
function tidy(node) {
  if (!node || !node.split) return node;
  const children = node.children.map(tidy).filter(Boolean);
  if (!children.length) return null;
  if (children.length === 1) return { ...children[0], size: node.size };
  return { ...node, children };
}

/** The tree without a leaf: its share goes back to its siblings (Spotfire: the one beside it fills the room). */
export function removeLeaf(node, id) {
  const strip = (n) => {
    if (!n) return null;
    if (!n.split) return n.id === id ? null : n;
    return { ...n, children: n.children.map(strip).filter(Boolean) };
  };
  const out = tidy(strip(node));
  if (!out) return null;
  const { size: _share, ...root } = out;
  return root;
}

/** The node at `path` replaced by `make(node)`. */
function replaceAt(node, path, make) {
  if (!path.length) return make(node);
  const [i, ...rest] = path;
  return { ...node, children: node.children.map((c, k) => (k === i ? replaceAt(c, rest, make) : c)) };
}

/**
 * A leaf docked on an edge of another leaf (or of the page, `targetId` null): taken from where it was, and the target
 * split in two halves along that edge - the moved one on that side. A leaf the tree does not hold yet is put in the
 * same way (an added visual).
 */
export function dockLeaf(node, movingId, targetId, edge) {
  const dir = DIR[edge];
  if (!dir || movingId === targetId) return node;
  const first = edge === 'left' || edge === 'top';
  const moving = { id: movingId, size: 1 };
  const without = removeLeaf(node, movingId);
  if (!without) return { id: movingId };
  const pair = (target) => {
    const { size, ...kept } = target;
    const split = { split: dir, children: first ? [moving, { ...kept, size: 1 }] : [{ ...kept, size: 1 }, moving] };
    return size === undefined ? split : { ...split, size };
  };
  if (targetId === null || targetId === undefined) return pair(without);
  const path = pathTo(without, targetId);
  return path ? replaceAt(without, path, pair) : node;
}

/**
 * Two leaves' places swapped - each takes the other's place and share, the tree's shape kept (Spotfire: a visual's title
 * dropped on the middle of another, the two change places).
 */
export function swapLeaves(node, a, b) {
  const ids = leafIds(node);
  if (a === b || !ids.includes(a) || !ids.includes(b)) return node;
  const swap = (n) => (n.split ? { ...n, children: n.children.map(swap) } : { ...n, id: n.id === a ? b : n.id === b ? a : n.id });
  return swap(node);
}

/**
 * Where Spotfire puts an added visual: it splits the largest one (by area; the first of equals) in two halves - side by
 * side, the new one on the right, when it is wider than high; stacked, the new one on top, otherwise (observed 10-13).
 * @param {Record<string, {width: number, height: number}>} boxes  each leaf's box
 */
export function addLeaf(node, id, boxes) {
  const ids = leafIds(node);
  if (!ids.length) return { id };
  const area = (k) => { const b = (boxes || {})[k] || {}; return (b.width || 0) * (b.height || 0); };
  const largest = ids.reduce((best, k) => (area(k) > area(best) ? k : best), ids[0]);
  const box = (boxes || {})[largest] || {};
  return dockLeaf(node, id, largest, (box.width || 0) > (box.height || 0) ? 'right' : 'top');
}

/**
 * The shares of children `i` and `i + 1` after their line is dragged `delta` pixels: the two keep their sum, neither
 * goes under `min` pixels. Measured in pixels, kept as weights - the other children do not move.
 * @param {number[]} sizes  the split's weights   @param {number} pxA  @param {number} pxB  the two children's pixels now
 * @returns {number[]} the split's weights, the two replaced (unchanged when the two cannot both keep `min`)
 */
export function resizePair(sizes, i, pxA, pxB, delta, min = MIN_SIZE) {
  const total = pxA + pxB;
  if (!(total >= 2 * min) || !(total > 0)) return sizes;
  const a = Math.min(Math.max(pxA + delta, min), total - min);
  const weight = sizes[i] + sizes[i + 1];
  const out = [...sizes];
  out[i] = (weight * a) / total;
  out[i + 1] = weight - out[i];
  return out;
}

/** The split at `path` with its children's weights replaced. */
export function withSizes(node, path, sizes) {
  return replaceAt(node, path, (split) => ({ ...split, children: split.children.map((c, k) => ({ ...c, size: sizes[k] })) }));
}

/**
 * The edge of a box a point is nearest to (normalised by the box's sides, so a wide box's top and bottom are not
 * favoured) - where a dragged part lands when dropped there; `middle` given, a point at least that far in from every
 * side is the box's middle ('center').
 */
export function edgeAt(box, x, y, middle = 0) {
  const fx = box.width ? (x - box.left) / box.width : 0.5;
  const fy = box.height ? (y - box.top) / box.height : 0.5;
  const near = [['left', fx], ['right', 1 - fx], ['top', fy], ['bottom', 1 - fy]];
  const best = near.reduce((b, e) => (e[1] < b[1] ? e : b));
  return middle > 0 && best[1] >= middle ? 'center' : best[0];
}
