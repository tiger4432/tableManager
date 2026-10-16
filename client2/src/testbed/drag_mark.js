// A drag over a table's cells marks what it spans (owner 10-16 «크로스 테이블과 로우 테이블에서 드래그 마킹») - the one
// helper the table and the cross table both take. Pressed on one cell and let go on another: the rectangle between them
// (a table's lines: the lines between), shown under the brush while dragging; the click that ends a drag marks nothing
// again. A press let go on its own cell is a click, as before.

/** -> { add(el, row, col, data), ended() }. `done(spanned, event)` - the cells the drag spans, `{ el, row, col, data }` each. */
export function dragMarks(done) {
  const cells = [];
  let from = null;
  let to = null;
  let moved = false;
  let swallow = false;
  const span = () => {
    const [r0, r1] = [Math.min(from.row, to.row), Math.max(from.row, to.row)];
    const [c0, c1] = [Math.min(from.col, to.col), Math.max(from.col, to.col)];
    return cells.filter((c) => c.row >= r0 && c.row <= r1 && c.col >= c0 && c.col <= c1);
  };
  const paint = () => {
    const on = new Set(moved && from ? span() : []);
    for (const c of cells) c.el.classList.toggle('is-dragged', on.has(c));
  };
  return {
    add(el, row, col = 0, data = null) {
      const c = { el, row, col, data };
      cells.push(c);
      el.addEventListener('pointerdown', (event) => {
        if (event && event.button) return;
        from = c;
        to = c;
        moved = false;
      });
      el.addEventListener('pointerenter', () => {
        if (!from) return;
        to = c;
        if (c !== from) moved = true;
        paint();
      });
      el.addEventListener('pointerup', (event) => {
        if (!from) return;
        const got = moved ? span() : null;
        from = null;
        to = null;
        moved = false;
        paint();
        if (got) { swallow = true; done(got, event); }
      });
    },
    /** Did a drag just end here - the click it ends with is not a press. */
    ended() {
      const was = swallow;
      swallow = false;
      return was;
    },
  };
}
