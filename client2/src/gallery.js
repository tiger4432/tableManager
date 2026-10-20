// THE MAIN GRID'S GALLERY (owner 10-20 «불량 이미지 보기 좋게 · 메인 그리드 · 조건별 썸네일», lead 77ffe5cb6): the rows the
// grid holds - its filter, its sort, its count cap - as 160 px tiles of one image column, a line a value of the Group by
// column. A tile pressed: its picture large, its row's values, and «Show in grid». Its own div; the grid's rows, the page's
// one picture loader and the grid's row are handed in. Only the lines in view are drawn.
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
  gallery: 'Gallery', grid: 'Grid', groupBy: 'Group by', none: '(None)', image: 'Image', empty: '(Empty)', all: 'All rows',
  loadMore: 'Load more', showInGrid: 'Show in grid', close: 'Close', noImageColumn: 'This table has no image column',
  rows: (n) => `${n.toLocaleString('en-US')} row${n === 1 ? '' : 's'}`,
  loaded: (n, total) => `${n.toLocaleString('en-US')} of ${total} loaded`,
  without: (n) => `${n.toLocaleString('en-US')} without image`,
  groupCount: (n) => n.toLocaleString('en-US'),
});

const textOf = (v) => (isBlank(v) ? '' : String(v));

/**
 * The rows in groups: one a value of `groupBy` in the order the rows first say it (the grid's sort), all in one when none
 * is chosen; each group's rows with an image and how many have none.
 * @param {Array<{id, data}>} rows  the grid's rows as it holds them, filtered and sorted
 * @param {{groupBy: string|null, image: string, valueOf: (row, column) => any}} o
 */
export function galleryModel(rows, { groupBy, image, valueOf }) {
  const groups = new Map();
  for (const row of rows) {
    const key = groupBy ? textOf(valueOf(row, groupBy)) : '';
    if (!groups.has(key)) groups.set(key, { value: key, label: groupBy ? (key === '' ? WORDS.empty : key) : WORDS.all, count: 0, tiles: [], without: 0 });
    const g = groups.get(key);
    g.count += 1;
    const ref = valueOf(row, image);
    if (isBlank(ref)) g.without += 1; else g.tiles.push({ id: row.id, ref: String(ref), row });
  }
  return [...groups.values()];
}

/** Where each group's head and each line of tiles stands: `{kind: 'head'|'tiles', group, top, height, tiles?}`, the whole height. */
export function galleryLayout(groups, width) {
  const per = Math.max(1, Math.floor((width + GAP_PX) / (TILE_PX + GAP_PX)));
  const lineHeight = TILE_PX + CAPTION_PX + GAP_PX;
  const items = [];
  let top = 0;
  for (const group of groups) {
    items.push({ kind: 'head', group, top, height: HEAD_PX });
    top += HEAD_PX;
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
   *          valueOf: (row, column) => any, count: () => object|null, whole: () => boolean, loadMore: () => void,
   *          showRow: (id) => void, onClose?: () => void}} deps
   */
  constructor(mount, deps) {
    this.mount = mount;
    this.deps = deps;
    this.doc = deps.doc || mount.ownerDocument;
    this.picked = null;
    this.drawn = new Map();
    this.layout = { items: [], height: 0, per: 1 };
    this.asked = false;
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
    const groupBy = names.includes(kept.groupBy) ? kept.groupBy : null;
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
    bar.append(select(WORDS.groupBy, [['', WORDS.none], ...names.map((n) => [n, n])], groupBy || '', (v) => { this.keep({ groupBy: v || null }); this.render(); }));
    if (images.length > 1) bar.append(select(WORDS.image, images.map((n) => [n, n]), image, (v) => { this.keep({ image: v }); this.render(); }));
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
    root.append(body);
    this.mount.replaceChildren(root);
    this.groups = galleryModel(rows, { groupBy, image, valueOf: this.deps.valueOf });
    this.scroller = scroller;
    this.canvas = canvas;
    this.drawn = new Map();
    this.width = 0;
    scroller.addEventListener('scroll', () => this.soon());
    this.place();
    if (was) { scroller.scrollTop = was; this.place(); }
    if (this.picked) this.showSide(this.picked);
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
      this.layout = galleryLayout(this.groups, width);
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
      tile.append(at, this.el('span', 'gallery-tile__cap', t.ref));
      tile.title = t.ref;
      new Thumb(at, { doc: this.doc, loader: this.deps.loader }).show([t.ref], TILE_PX);
      tile.addEventListener('click', () => this.showSide(t));
      line.append(tile);
    }
    return line;
  }

  /** A tile pressed: its picture large, its row's values, and the way back to the grid's row. */
  showSide(t) {
    this.picked = t;
    for (const node of this.canvas ? this.canvas.querySelectorAll('.gallery-tile') : []) node.classList.toggle('is-picked', node.dataset.row === String(t.id));
    const side = this.side;
    side.hidden = false;
    const head = this.el('div', 'gallery-side__head');
    const show = this.el('button', 'glass-btn gallery-side__go', WORDS.showInGrid);
    show.type = 'button';
    show.addEventListener('click', () => this.deps.showRow(t.id));
    const close = this.el('button', 'glass-btn gallery-side__close', WORDS.close);
    close.type = 'button';
    close.addEventListener('click', () => { this.picked = null; side.hidden = true; this.render(); });
    head.append(show, close);
    const big = this.el('img', 'gallery-side__img');
    big.alt = t.ref;
    const url = this.deps.loader.url(t.ref, LARGE_PX);
    this.deps.loader.want(url, (ok) => { if (this.picked === t) big.src = ok ? url : ''; });
    const values = this.el('dl', 'gallery-side__values');
    for (const c of this.deps.columns() || []) {
      values.append(this.el('dt', '', c.name), this.el('dd', '', textOf(this.deps.valueOf(t.row, c.name))));
    }
    side.replaceChildren(head, big, values);
  }
}
