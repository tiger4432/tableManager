/** How wide a column must be to hold the widest `sel` under `root` whole (lead 10-09: a word is never broken, its column
 *  is as wide as its longest word): the element plus its cell's (closest `cell`) padding and right line. 0 when none is
 *  drawn - a hidden box measures 0, so a caller keeps what it had. */
export function widestCell(root, sel, cell) {
  const view = root.ownerDocument && root.ownerDocument.defaultView;
  if (!view || !view.getComputedStyle) return 0;
  let need = 0;
  for (const el of root.querySelectorAll(sel)) {
    const cs = view.getComputedStyle(el.closest(cell));
    need = Math.max(need, el.offsetWidth + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) + parseFloat(cs.borderRightWidth));
  }
  return Math.ceil(need);
}
