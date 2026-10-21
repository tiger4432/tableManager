// THE MAIN GRID'S GALLERY (owner 10-20 «불량 이미지 보기 좋게 · 메인 그리드 · 조건별 썸네일», lead 77ffe5cb6): the rows the
// grid holds - its filter, its sort, its count cap - as 160 px tiles of one image column, a line a value of the Rows by
// columns. A tile pressed: its picture large, its row's values, and «Show in grid». Its own div; the grid's rows, the page's
// one picture loader and the grid's row are handed in. Only the lines in view are drawn.
// With a Columns by column the lines are a board, rows x columns (owner 10-20 «갤러리는 매트릭스로», lead 3589216b9): a cell its
// rows' count, its share of the row and its first thumbnails; a cell pressed lays its tiles out under the board as the list does.
import { isBlank } from './absent.js';
import { Thumb } from './image_thumb.js';
import { countNumberText } from './match_count.js';

/** A tile's picture side (the server's /api/image px) - the token --gallery-tile says the same to the CSS. */
export const TILE_PX = 160;
/** The picture beside a tile pressed. */
export const LARGE_PX = 640;
/** A group's head line and the space between tiles, in px - gallery.css's .gallery-head and --space-2. */
export const HEAD_PX = 34;
export const GAP_PX = 6.8;
/** A tile's caption line under its picture. */
export const CAPTION_PX = 20;
/** Lines of tiles drawn above and below the ones in view. */
export const OVERSCAN = 2;
export const WORDS = Object.freeze({
  gallery: 'Gallery', grid: 'Grid', groupBy: 'Rows by', none: '(None)', image: 'Image', empty: '(Empty)', all: 'All rows',
  caption: 'Caption', order: 'Order', mostRows: 'Most rows', byValue: 'Value',
  columnsBy: 'Columns by', addColumn: '+ Column', show: 'Show', total: 'All', noRows: 'none', filterTo: 'Filter grid to this cell',
  perCell: (n) => `${n} per cell`,
  ofRows: (share) => `${share} of rows`,
  ofRow: (share) => `${share} of row`,
  loadMore: 'Load more', showInGrid: 'Show in grid', close: 'Close', noImageColumn: 'This table has no image column',
  rows: (n) => `${n.toLocaleString('en-US')} row${n === 1 ? '' : 's'}`,
  loaded: (n, total) => `${n.toLocaleString('en-US')} of ${total} loaded`,
  without: (n) => `${n.toLocaleString('en-US')} without image`,
  groupCount: (n) => n.toLocaleString('en-US'),
});

const textOf = (v) => (isBlank(v) ? '' : String(v));

/** The Order box: the groups with most rows first (the first said first among equals), or by their value. */
export const ORDERS = Object.freeze([['count', WORDS.mostRows], ['value', WORDS.byValue]]);
/** Thumbnails a board cell draws - the Show box. */
export const PER_CELL = Object.freeze([4, 9]);

/** A share as the board says it: «37%». */
const percent = (part, whole) => `${whole ? Math.round((part / whole) * 100) : 0}%`;

/**
 * The rows in groups: one a value of the `groupBy` columns (one column, or several - their values together are the key),
 * all in one when none is chosen; each group's rows, those with an image as tiles (the caption the `caption` column's
 * value) and how many have none. `order` - ORDERS; the tiles keep the grid's sort.
 * @param {Array<{id, data}>} rows  the grid's rows as it holds them, filtered and sorted
 * @param {{groupBy: string|string[]|null, image: string, caption?: string|null, order?: string, valueOf: (row, column) => any}} o
 */
export function galleryModel(rows, { groupBy, image, caption = null, order = 'count', valueOf }) {
  const by = [].concat(groupBy || []).filter(Boolean);
  const groups = new Map();
  for (const row of rows) {
    const parts = by.map((column) => textOf(valueOf(row, column)));
    const key = JSON.stringify(parts);
    if (!groups.has(key)) {
      groups.set(key, { key, parts, value: parts.join(' · '), count: 0, tiles: [], without: 0, rows: [],
        label: by.length ? parts.map((v) => (v === '' ? WORDS.empty : v)).join(' · ') : WORDS.all });
    }
    const g = groups.get(key);
    g.count += 1;
    g.rows.push(row);
    const ref = valueOf(row, image);
    if (isBlank(ref)) g.without += 1;
    else g.tiles.push({ id: row.id, ref: String(ref), caption: caption ? textOf(valueOf(row, caption)) : String(ref), row });
  }
  const out = [...groups.values()];
  if (order === 'value') return out.sort((a, b) => a.value.localeCompare(b.value, 'en', { numeric: true }));
  return out.map((g, i) => [g, i]).sort((a, b) => b[0].count - a[0].count || a[1] - b[1]).map(([g]) => g);
}

/**
 * The board: a line a group of `rowsBy`, a column a group of `columnBy`, both from galleryModel and in its order; a cell the
 * line's rows of that column's value grouped by the same function (null where the line has none), its share of the line.
 */
export function galleryBoard(rows, { rowsBy, columnBy, ...o }) {
  const columns = galleryModel(rows, { ...o, groupBy: [columnBy] }).map(({ key, label, parts }) => ({ key, label, value: parts[0] }));
  return {
    all: rows.length,
    columns,
    lines: galleryModel(rows, { ...o, groupBy: rowsBy }).map((line) => {
      const cells = new Map(galleryModel(line.rows, { ...o, groupBy: [columnBy] }).map((g) => [g.key, g]));
      return { ...line, share: percent(line.count, rows.length), cells: columns.map((c) => cells.get(c.key) || null) };
    }),
  };
}

/** Where each group's head and each line of tiles stands: `{kind: 'head'|'tiles', group, top, height, tiles?}`, the whole height.
 *  `heads` false - the tiles alone (a board cell opened: its head is the board's). */
export function galleryLayout(groups, width, { heads = true } = {}) {
  const per = Math.max(1, Math.floor((width + GAP_PX) / (TILE_PX + GAP_PX)));
  const lineHeight = TILE_PX + CAPTION_PX + GAP_PX;
  const items = [];
  let top = 0;
  for (const group of groups) {
    if (heads) {
      items.push({ kind: 'head', group, top, height: HEAD_PX });
      top += HEAD_PX;
    }
    for (let i = 0; i < group.tiles.length; i += per) {
      items.push({ kind: 'tiles', group, top, height: lineHeight, tiles: group.tiles.slice(i, i + per) });
      top += lineHeight;
    }
  }
  return { items, height: top, per };
}

/** The items a view of `height` px scrolled to `top` shows, and OVERSCAN lines either side. */
export function itemsInView(layout, top, height) {
  const margin = OVERSCAN * (TILE_PX + CAPTION_PX + GAP_PX);
  return layout.items.filter((it) => it.top + it.height >= top - margin && it.top <= top + height + margin);
}

export class GalleryPart {
  /**
   * @param {HTMLElement} mount  its own div
   * @param {{doc, base, loader, storage?, table: () => string, columns: () => Array<{name, type}>, rows: () => Array<{id, data}>,
   *          shown: () => string[], valueOf: (row, column) => any, count: () => object|null, whole: () => boolean,
   *          loadMore: () => void, showRow: (id) => void}} deps  `shown` - the columns the grid shows (its own answer)
   */
  constructor(mount, deps) {
    this.mount = mount;
    this.deps = deps;
    this.doc = deps.doc || mount.ownerDocument;
    this.picked = null;
    this.opened = null;
    this.drawn = new Map();
    this.layout = { items: [], height: 0, per: 1 };
    this.asked = false;
    // ← → the neighbour tile, Esc closes - only while this gallery's side panel is open, never while typing in a box
    this.onKey = (event) => {
      if (!this.picked) return;
      const t = event.target;
      const tag = t && t.tagName ? String(t.tagName).toLowerCase() : '';
      if (tag === 'input' || tag === 'select' || tag === 'textarea' || (t && t.isContentEditable)) return;
      if (event.key === 'Escape') { event.preventDefault(); this.close(); return; }
      const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
      if (!step) return;
      const tiles = (this.groups || []).flatMap((g) => g.tiles);
      const at = tiles.findIndex((x) => x.id === this.picked.id);
      const next = tiles[at + step];
      if (at < 0 || !next) return;
      event.preventDefault();
      this.showSide(next);
      this.reveal(next);
    };
  }

  el(tag, cls, text) { const n = this.doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }

  /** The table's image columns and the choices kept for it (this browser). */
  images() { return (this.deps.columns() || []).filter((c) => c.type === 'image').map((c) => c.name); }

  kept() {
    const table = this.deps.table();
    try { return JSON.parse((this.deps.storage && this.deps.storage.getItem(`gallery:${table}`)) || '{}') || {}; } catch (e) { return {}; }
  }

  keep(next) {
    const table = this.deps.table();
    try { if (this.deps.storage) this.deps.storage.setItem(`gallery:${table}`, JSON.stringify({ ...this.kept(), ...next })); } catch (e) { /* not kept */ }
  }

  /** Draw it all again - the grid's rows changed (a filter, a sort, a page, a table). */
  render() {
    // the place it was scrolled to stays (the grid's rows change under it - a page added by Load more)
    const was = this.scroller ? this.scroller.scrollTop || 0 : 0;
    const images = this.images();
    const kept = this.kept();
    const image = images.includes(kept.image) ? kept.image : images[0];
    const names = (this.deps.columns() || []).map((c) => c.name);
    // Rows by: one column or several (a choice kept before the board was one name)
    const rowsBy = [...new Set([].concat(kept.groupBy || []))].filter((n) => names.includes(n));
    const groupBy = rowsBy.length ? rowsBy : null;
    const columnBy = names.includes(kept.columnBy) && !rowsBy.includes(kept.columnBy) ? kept.columnBy : null;
    const perCell = PER_CELL.includes(kept.perCell) ? kept.perCell : PER_CELL[0];
    const shown = (this.deps.shown ? this.deps.shown() : names) || [];
    const caption = names.includes(kept.caption) ? kept.caption : (shown.find((n) => n !== image) || null);
    const order = ORDERS.some(([v]) => v === kept.order) ? kept.order : ORDERS[0][0];
    const root = this.el('div', 'gallery');
    const bar = this.el('div', 'gallery-bar');
    root.append(bar);
    if (!image) {
      root.append(this.el('div', 'gallery-say', WORDS.noImageColumn));
      this.mount.replaceChildren(root);
      return;
    }
    const select = (label, options, value, onPick) => {
      const box = this.el('label', 'gallery-pick');
      box.append(this.el('span', 'gallery-pick__word', label));
      const s = this.el('select', 'gallery-select');
      for (const [v, words] of options) { const o = this.el('option', '', words); o.value = v; s.append(o); }
      s.value = value;
      s.addEventListener('change', () => onPick(s.value));
      box.append(s);
      return box;
    };
    // Rows by - its first box and one more per column added (+ Column); (None) in a box takes that column out
    const rowsKept = (next) => { this.keep({ groupBy: next.filter(Boolean) }); this.render(); };
    bar.append(select(WORDS.groupBy, [['', WORDS.none], ...names.map((n) => [n, n])], rowsBy[0] || '', (v) => rowsKept([v, ...rowsBy.slice(1)])));
    rowsBy.slice(1).forEach((name, i) => {
      const extra = this.el('select', 'gallery-select gallery-select--more');
      for (const [v, words] of [['', WORDS.none], ...names.map((n) => [n, n])]) { const o = this.el('option', '', words); o.value = v; extra.append(o); }
      extra.value = name;
      extra.addEventListener('change', () => rowsKept(rowsBy.map((n, j) => (j === i + 1 ? extra.value : n))));
      bar.append(extra);
    });
    const unused = names.filter((n) => !rowsBy.includes(n) && n !== columnBy && n !== image);
    if (rowsBy.length && unused.length) {
      const add = this.el('button', 'glass-page-btn gallery-add', WORDS.addColumn);
      add.type = 'button';
      add.addEventListener('click', () => rowsKept([...rowsBy, unused[0]]));
      bar.append(add);
    }
    bar.append(select(WORDS.columnsBy, [['', WORDS.none], ...names.filter((n) => !rowsBy.includes(n)).map((n) => [n, n])], columnBy || '',
      (v) => { this.opened = null; this.keep({ columnBy: v || null }); this.render(); }));
    if (columnBy) bar.append(select(WORDS.show, PER_CELL.map((n) => [String(n), WORDS.perCell(n)]), String(perCell), (v) => { this.keep({ perCell: Number(v) }); this.render(); }));
    if (images.length > 1) bar.append(select(WORDS.image, images.map((n) => [n, n]), image, (v) => { this.keep({ image: v }); this.render(); }));
    bar.append(select(WORDS.caption, names.map((n) => [n, n]), caption || '', (v) => { this.keep({ caption: v }); this.render(); }));
    if (groupBy || columnBy) bar.append(select(WORDS.order, ORDERS.slice(), order, (v) => { this.keep({ order: v }); this.render(); }));
    const rows = this.deps.rows() || [];
    // the grid holds part of the table: the counts are of the rows it holds, and it says so (lead 10-20)
    const count = this.deps.count ? this.deps.count() : null;
    const whole = this.deps.whole();
    const total = count && count.total !== null && count.total !== undefined ? countNumberText(count) : null;
    bar.append(this.el('span', 'gallery-count', whole || !total ? WORDS.rows(rows.length) : WORDS.loaded(rows.length, total)));
    if (!whole) {
      const more = this.el('button', 'glass-page-btn gallery-more', WORDS.loadMore);
      more.type = 'button';
      more.addEventListener('click', () => this.deps.loadMore());
      bar.append(more);
    }
    const body = this.el('div', 'gallery-body');
    const scroller = this.el('div', 'gallery-scroll');
    const canvas = this.el('div', 'gallery-canvas');
    scroller.append(canvas);
    body.append(scroller);
    this.side = this.el('aside', 'gallery-side');
    this.side.hidden = !this.picked;
    body.append(this.side);
    this.heads = !columnBy;
    if (columnBy) {
      const board = galleryBoard(rows, { rowsBy, columnBy, image, caption, order, valueOf: this.deps.valueOf });
      const open = this.openedIn(board);
      root.append(this.boardOf(board, { rowsBy, columnBy, perCell, open }));
      if (open) root.append(this.openHead(open, { rowsBy, columnBy }));
      this.groups = open ? [open.cell] : [];
    }
    root.append(body);
    this.mount.replaceChildren(root);
    if (!columnBy) this.groups = galleryModel(rows, { groupBy, image, caption, order, valueOf: this.deps.valueOf });
    this.scroller = scroller;
    this.canvas = canvas;
    this.drawn = new Map();
    this.width = 0;
    scroller.addEventListener('scroll', () => this.soon());
    this.place();
    if (was) { scroller.scrollTop = was; this.place(); }
    if (this.picked) this.showSide(this.picked);
  }

  /** The side panel shut and the keys let go. */
  close() {
    this.picked = null;
    if (this.side) this.side.hidden = true;
    if (this.doc.removeEventListener) this.doc.removeEventListener('keydown', this.onKey);
    this.render();
  }

  /** The tile's line scrolled into the view when it is out of it. */
  reveal(tile) {
    const item = this.layout.items.find((it) => it.kind === 'tiles' && it.tiles.some((x) => x.id === tile.id));
    if (!item || !this.scroller) return;
    const top = this.scroller.scrollTop || 0;
    const height = this.scroller.clientHeight || 0;
    if (item.top < top || item.top + item.height > top + height) {
      this.scroller.scrollTop = Math.max(0, item.top - HEAD_PX);
      this.place();
    }
  }

  soon() {
    if (this.asked) return;
    this.asked = true;
    const frame = (this.doc.defaultView && this.doc.defaultView.requestAnimationFrame) || ((fn) => setTimeout(fn, 16));
    frame(() => { this.asked = false; this.place(); });
  }

  /** The lines in view drawn, the rest taken away; the layout again when the width changed. */
  place() {
    if (!this.scroller) return;
    const width = this.scroller.clientWidth || TILE_PX;
    if (width !== this.width) {
      this.width = width;
      this.layout = galleryLayout(this.groups, width, { heads: this.heads !== false });
      this.canvas.style.height = `${this.layout.height}px`;
      for (const node of this.drawn.values()) node.remove();
      this.drawn = new Map();
    }
    const want = itemsInView(this.layout, this.scroller.scrollTop || 0, this.scroller.clientHeight || 2 * TILE_PX);
    const keys = new Set(want.map((it) => it.top));
    for (const [top, node] of this.drawn) if (!keys.has(top)) { node.remove(); this.drawn.delete(top); }
    for (const it of want) {
      if (this.drawn.has(it.top)) continue;
      const node = it.kind === 'head' ? this.head(it.group) : this.line(it.tiles);
      node.style.top = `${it.top}px`;
      node.style.height = `${it.height}px`;
      this.canvas.append(node);
      this.drawn.set(it.top, node);
    }
  }

  /** The cell opened - the one pressed while it still has rows, else the first cell that has. */
  openedIn(board) {
    const at = (lineKey, colKey) => {
      const li = board.lines.findIndex((l) => l.key === lineKey);
      const ci = board.columns.findIndex((c) => c.key === colKey);
      const cell = li >= 0 && ci >= 0 ? board.lines[li].cells[ci] : null;
      return cell ? { line: board.lines[li], column: board.columns[ci], cell, li } : null;
    };
    const kept = this.opened && at(this.opened.line, this.opened.column);
    if (kept) return kept;
    for (const line of board.lines) {
      const ci = line.cells.findIndex(Boolean);
      if (ci >= 0) return at(line.key, board.columns[ci].key);
    }
    return null;
  }

  /** The board: a corner, a head per column and «All»; a line its head (value · share of all rows), its cells and its total. */
  boardOf(board, { rowsBy, columnBy, perCell, open }) {
    const box = this.el('div', 'gallery-board');
    const grid = this.el('div', 'gallery-board__grid');
    grid.style.setProperty('--gallery-cols', String(board.columns.length));
    grid.append(this.el('span', 'gallery-board__corner', `${rowsBy.length ? rowsBy.join(' · ') : WORDS.all} \\ ${columnBy}`));
    for (const c of board.columns) grid.append(this.el('span', 'gallery-board__col', c.label));
    grid.append(this.el('span', 'gallery-board__col gallery-board__col--total', WORDS.total));
    board.lines.forEach((line, li) => {
      const head = this.el('div', 'gallery-board__row');
      head.style.setProperty('--gallery-cat', `var(--cat-${(li % 9) + 1})`);
      head.append(this.el('span', 'gallery-board__value', line.label), this.el('span', 'gallery-board__share', WORDS.ofRows(line.share)));
      grid.append(head);
      line.cells.forEach((cell, ci) => {
        const column = board.columns[ci];
        const on = open && open.line.key === line.key && open.column.key === column.key;
        const b = this.el('button', `gallery-cell${cell ? '' : ' is-empty'}${on ? ' is-open' : ''}`);
        b.type = 'button';
        b.dataset.line = line.key;
        b.dataset.column = column.key;
        b.setAttribute('aria-label', `${line.label} · ${column.label}, ${WORDS.rows(cell ? cell.count : 0)}`);
        const top = this.el('span', 'gallery-cell__top');
        top.append(this.el('span', 'gallery-cell__n', WORDS.groupCount(cell ? cell.count : 0)),
          this.el('span', 'gallery-cell__share', cell ? WORDS.ofRow(percent(cell.count, line.count)) : WORDS.noRows));
        b.append(top);
        if (cell && cell.tiles.length) {
          const thumbs = this.el('span', `gallery-cell__thumbs gallery-cell__thumbs--${perCell}`);
          for (const t of cell.tiles.slice(0, perCell)) {
            const at = this.el('span', 'gallery-cell__thumb');
            new Thumb(at, { doc: this.doc, loader: this.deps.loader }).show([t.ref], TILE_PX);
            thumbs.append(at);
          }
          b.append(thumbs);
        }
        if (cell) b.addEventListener('click', () => { this.opened = { line: line.key, column: column.key }; this.picked = null; this.render(); });
        else b.disabled = true;
        grid.append(b);
      });
      grid.append(this.el('div', 'gallery-board__total', WORDS.groupCount(line.count)));
    });
    box.append(grid);
    return box;
  }

  /** The opened cell's head: its colour, its words, its rows · without image, and the grid's filter set to it. */
  openHead(open, { rowsBy, columnBy }) {
    const head = this.el('div', 'gallery-open');
    head.style.setProperty('--gallery-cat', `var(--cat-${(open.li % 9) + 1})`);
    head.append(this.el('span', 'gallery-open__mark'), this.el('span', 'gallery-open__label', `${open.line.label} · ${open.column.label}`),
      this.el('span', 'gallery-open__n', [WORDS.rows(open.cell.count), open.cell.without ? WORDS.without(open.cell.without) : ''].filter(Boolean).join(' · ')));
    if (this.deps.filterTo) {
      const go = this.el('button', 'glass-page-btn ctl-small gallery-open__filter', WORDS.filterTo);
      go.type = 'button';
      const row = open.cell.rows[0];
      go.addEventListener('click', () => this.deps.filterTo([...rowsBy, columnBy].map((column) => ({ column, row }))));
      head.append(go);
    }
    return head;
  }

  head(group) {
    const h = this.el('div', 'gallery-head');
    h.append(this.el('span', 'gallery-head__value', group.label), this.el('span', 'gallery-head__n', WORDS.groupCount(group.count)));
    if (group.without) h.append(this.el('span', 'gallery-head__without', WORDS.without(group.without)));
    return h;
  }

  line(tiles) {
    const line = this.el('div', 'gallery-line');
    for (const t of tiles) {
      const tile = this.el('button', `gallery-tile${this.picked && this.picked.id === t.id ? ' is-picked' : ''}`);
      tile.type = 'button';
      tile.dataset.row = String(t.id);
      const at = this.el('span', 'gallery-tile__img');
      tile.append(at, this.el('span', 'gallery-tile__cap', t.caption));
      tile.title = t.caption === t.ref ? t.ref : `${t.caption} · ${t.ref}`;
      new Thumb(at, { doc: this.doc, loader: this.deps.loader }).show([t.ref], TILE_PX);
      tile.addEventListener('click', () => this.showSide(t));
      line.append(tile);
    }
    return line;
  }

  /** A tile pressed: its picture large, its row's values, and the way back to the grid's row. */
  showSide(t) {
    this.picked = t;
    if (this.doc.addEventListener) { this.doc.removeEventListener && this.doc.removeEventListener('keydown', this.onKey); this.doc.addEventListener('keydown', this.onKey); }
    for (const node of this.canvas ? this.canvas.querySelectorAll('.gallery-tile') : []) node.classList.toggle('is-picked', node.dataset.row === String(t.id));
    const side = this.side;
    side.hidden = false;
    const head = this.el('div', 'gallery-side__head');
    const show = this.el('button', 'glass-btn gallery-side__go', WORDS.showInGrid);
    show.type = 'button';
    show.addEventListener('click', () => this.deps.showRow(t.id));
    const close = this.el('button', 'glass-btn gallery-side__close', WORDS.close);
    close.type = 'button';
    close.addEventListener('click', () => this.close());
    head.append(show, close);
    const big = this.el('img', 'gallery-side__img');
    big.alt = t.ref;
    const url = this.deps.loader.url(t.ref, LARGE_PX);
    this.deps.loader.want(url, (ok) => { if (this.picked === t) big.src = ok ? url : ''; });
    const values = this.el('dl', 'gallery-side__values');
    for (const name of (this.deps.shown ? this.deps.shown() : (this.deps.columns() || []).map((c) => c.name)) || []) {
      values.append(this.el('dt', '', name), this.el('dd', '', textOf(this.deps.valueOf(t.row, name))));
    }
    side.replaceChildren(head, big, values);
  }
}
