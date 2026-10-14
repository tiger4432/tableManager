// ═══════════════════════════════════════════════════════════════════════════════
// GRID SHELL -- placement lives HERE, outside every part.
//
// 🔴 THE LAYOUT IS DATA. A screen is a LIST OF INSTANCE DECLARATIONS and the TREE they sit in:
//
//      { panels: [{ id, part: "map", reads: "marking:1", writes: "marking:1", title, options: {...} }, ...],
//        root: { split: 'row' | 'column', children: [{ id, size }, { split, size, children }, ...] },
//        gap, height?, locked? }
//
//    Spotfire's page (lead 10-13, observed on the owner's Spotfire): the visualization area is a SPLIT TREE - each split
//    lays its children side by side or stacked, each a share (`size`, a weight) - and the panels outside it (the left
//    bar, the start row, the properties and filters, the status bar) are DOCKED chrome: a panel with `dock`
//    ('top' | 'bottom' | 'left' | 'right') and its `size` (a CSS length across its side). Top and bottom run the page's
//    width, left and right stand between them. The tree's edits are pure (split_tree.js); this file draws the tree,
//    seats the parts, and turns a person's gestures into those edits. A part never learns where it sits.
//    `height` - the area's own height (Spotfire's custom visualization area size: the page scrolls past it).
//    `locked` - Spotfire's «Lock visualization area»: no line to drag, no title to move, no × or maximize.
//
// 🔴 A REDRAW MOVES THE PANELS, IT NEVER SEATS THEM AGAIN. Docking, resizing, maximizing and closing rebuild the
//    split boxes and put each panel's element into its new cell; the part keeps its state and is told its new box
//    by the size observer. Seating again would walk again.
//
// 🔴 ONE DIV PER PANEL, MADE HERE, HANDED OVER WHOLE. The part owns everything inside it and
//    nothing outside it. Two instances of the same part therefore cannot collide: they are
//    handed two different elements and hold their state on `this`.
//
// `document` and the size observer are DEPENDENCIES, so the shell is scorable under bare node.
// ═══════════════════════════════════════════════════════════════════════════════

import { leafIds, pathTo, nodeAt, removeLeaf, dockLeaf, swapLeaves, addLeaf, resizePair, withSizes, edgeAt, MIN_SIZE, DROP_EDGE } from './split_tree.js';

/**
 * The default observer: the platform's, when there is a platform. A shell running under bare
 * node gets a no-op and the harness injects its own so resizes can be driven deliberately.
 */
function platformObserveSize(el, onSize) {
  const RO = globalThis.ResizeObserver;
  if (!RO) return () => {};
  const ro = new RO((entries) => {
    for (const entry of entries) {
      const box = entry.contentRect || {};
      onSize(box.width || 0, box.height || 0);
    }
  });
  ro.observe(el);
  return () => ro.disconnect();
}

const SVG = 'http://www.w3.org/2000/svg';
// The title bar's buttons (14 x 21, Spotfire's size), drawn here: maximize - two arrows out to the corners; restore - in.
const ICONS = {
  maximize: ['M8 1h5v5h-1.6V3.7L8.7 6.4 7.6 5.3l2.7-2.7H8z', 'M6 13H1V8h1.6v2.3l2.7-2.7 1.1 1.1-2.7 2.7H6z'],
  restore: ['M13 2.1 10.3 4.8h2.3v1.6h-5v-5h1.6v2.3L11.9 1z', 'M1 11.9l2.7-2.7H1.4V7.6h5v5H4.8v-2.3L2.1 13z'],
  close: ['M2.1.9l11 11-1.2 1.2-11-11z', 'M11.9.9l1.2 1.2-11 11-1.2-1.2z'],
};
/** How near the area's border a drop docks on the page's edge, not on the part under it. */
const PAGE_EDGE = 16;
/** How far a press on a title moves before it is a drag (a click activates, a drag moves). */
const DRAG_START = 4;

export class GridShell {
  /**
   * @param {object} host  the element the board fills.
   * @param {{doc: Document, markings: object, parts: Record<string, Function>,
   *          observeSize?: Function}} deps  `parts` maps a declaration's `part` name to its
   *          class. A part this registry has never heard of is REFUSED VISIBLY (see below),
   *          not skipped -- a panel that silently does not appear is a bug that reads as a
   *          layout choice.
   */
  constructor(host, deps) {
    const options = deps || {};
    this.host = host;
    this.doc = options.doc;
    this.markings = options.markings;
    this.parts = options.parts || {};
    this.observeSize = options.observeSize || platformObserveSize;
    this.panels = new Map();   // id -> {el, part, disconnect}
    this.layout = null;
    this.root = null;
    this.maximized = null;
  }

  /** Seat every declaration. Calling it again reseats from scratch. */
  render(layout) {
    this.destroy();
    this.layout = layout;
    this.root = layout.root || null;
    this.maximized = null;
    const doc = this.doc;
    this.host.textContent = '';
    this.host.className = 'rb-board';
    this.host.style.display = 'grid';
    this.host.style.gridTemplateAreas = '"top top top" "left area right" "bottom bottom bottom"';
    this.host.style.gridTemplateColumns = 'auto minmax(0, 1fr) auto';
    this.host.style.gridTemplateRows = `auto ${layout.height ? 'auto' : 'minmax(0, 1fr)'} auto`;
    this.gap = layout.gap || '0px';
    this.docks = {};
    this.area = doc.createElement('div');
    this.area.className = 'rb-area';
    this.area.style.gridArea = 'area';
    this.area.style.position = 'relative';
    this.area.style.display = 'flex';
    this.area.style.minWidth = '0';
    this.area.style.minHeight = '0';
    // The frames carry half the gap each, so the area reaches half a gap past its box: the outer panels sit on it.
    this.area.style.margin = `calc(${this.gap} / -2)`;
    if (layout.height) this.area.style.height = layout.height;
    this.host.appendChild(this.area);
    // Panels the drawn tree does not show (another one maximized) wait here, seated.
    this.parked = doc.createElement('div');
    this.parked.style.display = 'none';
    this.host.appendChild(this.parked);
    for (const decl of layout.panels || []) this.seat(decl);
    this.listen();
    this.drawArea();
    return this;
  }

  /** One panel's element and part - in its dock, or parked until the tree is drawn. */
  seat(decl) {
    const doc = this.doc;
    const el = doc.createElement('div');
    el.className = 'rb-panel';
    el.setAttribute('data-panel', decl.id);
    // A panel is a box with its own scroll, so one part's overflow cannot push a neighbour.
    el.style.minWidth = '0';
    el.style.minHeight = '0';
    if (decl.dock) {
      this.dockOf(decl.dock).appendChild(el);
      // 🔴 THE ONLY PLACE A DOCKED PANEL'S SIZE IS WRITTEN: across its side; along it, the side's share.
      el.style[decl.dock === 'left' || decl.dock === 'right' ? 'width' : 'height'] = decl.size || 'auto';
      el.style.flex = '1 1 0px';
    } else {
      this.parked.appendChild(el);
    }

    const PartClass = this.parts[decl.part];
    if (!PartClass) {
      el.setAttribute('data-panel-state', 'unknown-part');
      el.textContent = `Unregistered part: ${decl.part}`;
      this.panels.set(decl.id, { el, part: null, decl, box: null, disconnect: () => {} });
      return el;
    }

    const part = new PartClass(el, {
      doc,
      markings: this.markings,
      reads: decl.reads || null,
      writes: decl.writes || null,
      // 🔴 소유자 데이터 흐름 정본: 부품이 선언하는 것은 «읽을 마킹»과 «무엇을 걷나»입니다.
      //    reads/writes 와 «같은 자리»에 서는 이유가 그것입니다 -- start 가 곧 마킹이니까요.
      start: decl.start || null,
      legacyRoute: decl.legacyRoute || null,
      title: decl.title || '',
      // The whole entry too: a part whose declaration is more than these (the testbed's visual - kind, row, encode,
      // filter) reads it here, and hands it back for Save.
      declaration: decl,
      ...(decl.options || {}),
    });
    part.mount();
    const seat = { el, part, decl, box: null, disconnect: () => {} };
    seat.disconnect = this.observeSize(el, (w, h) => { seat.box = { width: w, height: h }; part.resize(w, h); });
    this.panels.set(decl.id, seat);
    return el;
  }

  /** A side's dock, made the first time a panel docks there. */
  dockOf(side) {
    if (this.docks[side]) return this.docks[side];
    const dock = this.doc.createElement('div');
    dock.className = 'rb-dock';
    dock.setAttribute('data-dock', side);
    dock.style.gridArea = side;
    dock.style.display = 'flex';
    dock.style.flexDirection = side === 'left' || side === 'right' ? 'column' : 'row';
    dock.style.minWidth = '0';
    dock.style.minHeight = '0';
    dock.style.gap = this.gap;
    // The gap between a dock and the area is the dock's, so a side nobody docks on takes no room.
    const toward = { top: 'marginBottom', bottom: 'marginTop', left: 'marginRight', right: 'marginLeft' }[side];
    dock.style[toward] = this.gap;
    this.host.appendChild(dock);
    this.docks[side] = dock;
    return dock;
  }

  /** Draw the area's tree again from `this.root`, moving each seated panel into its cell. */
  drawArea() {
    const doc = this.doc;
    for (const id of leafIds(this.root)) {
      const seat = this.panels.get(id);
      if (seat) this.parked.appendChild(seat.el);
    }
    const shown = this.maximized && this.panels.has(this.maximized) ? { id: this.maximized } : this.root;
    const build = (node, path) => {
      if (!node.split) return this.cell(node.id);
      const box = doc.createElement('div');
      box.className = 'rb-split';
      box.setAttribute('data-split', node.split);
      box.style.display = 'flex';
      box.style.flexDirection = node.split;
      box.style.minWidth = '0';
      box.style.minHeight = '0';
      node.children.forEach((child, i) => {
        if (i && !this.layout.locked) box.appendChild(this.splitter(node.split, path, i - 1));
        const kid = build(child, [...path, i]);
        kid.style.flex = `${child.size === undefined ? 1 : child.size} 1 0px`;
        box.appendChild(kid);
      });
      return box;
    };
    const drawn = shown ? build(shown, []) : doc.createElement('div');
    drawn.style.flex = '1 1 0px';
    if (!shown) {
      drawn.className = 'sf-say rb-area__empty';
      drawn.textContent = 'Add a visualization';
    }
    this.area.replaceChildren(drawn);
    this.drop = null;
  }

  /** A leaf's cell: its share and nothing else; inside it the frame - half the gap around it (a margin, so the share is
   *  the weight's whatever sits beside it), the panel, and - unlocked - its title bar's buttons. */
  cell(id) {
    const doc = this.doc;
    const cell = doc.createElement('div');
    cell.className = 'rb-cell';
    cell.setAttribute('data-cell', id);
    cell.style.display = 'grid';
    cell.style.minWidth = '0';
    cell.style.minHeight = '0';
    const frame = doc.createElement('div');
    frame.className = 'rb-frame';
    frame.style.margin = `calc(${this.gap} / 2)`;
    frame.style.position = 'relative';
    frame.style.display = 'grid';
    frame.style.minWidth = '0';
    frame.style.minHeight = '0';
    cell.appendChild(frame);
    const seat = this.panels.get(id);
    if (!seat) {
      frame.textContent = `Unplaced panel: ${id}`;
      return cell;
    }
    frame.appendChild(seat.el);
    if (!this.layout.locked) frame.appendChild(this.tools(id));
    return cell;
  }

  /** The title bar's buttons over a panel's top right: maximize (restore while maximized) and close. Shown on hover. */
  tools(id) {
    const doc = this.doc;
    const tools = doc.createElement('div');
    tools.className = 'sf-tools';
    const button = (icon, title, act) => {
      const b = doc.createElement('button');
      b.type = 'button';
      b.className = 'sf-tool';
      b.title = title;
      b.setAttribute('aria-label', title);
      const svg = doc.createElementNS(SVG, 'svg');
      svg.setAttribute('viewBox', '0 0 14 14');
      for (const d of ICONS[icon]) {
        const path = doc.createElementNS(SVG, 'path');
        path.setAttribute('d', d);
        svg.appendChild(path);
      }
      b.appendChild(svg);
      b.addEventListener('click', act);
      tools.appendChild(b);
      return b;
    };
    if (this.maximized === id) button('restore', 'Restore visualization layout', () => this.maximize(null));
    else button('maximize', 'Maximize visualization', () => this.maximize(id));
    button('close', 'Close', () => this.remove(id));
    return tools;
  }

  /** The line between child `index` and the next of the split at `path` - dragged, their shares change. */
  splitter(dir, path, index) {
    const line = this.doc.createElement('div');
    line.className = 'sf-splitter';
    line.setAttribute('data-dir', dir);
    line.style.flex = '0 0 0px';
    line.addEventListener('pointerdown', (event) => this.beginResize(event, line, path, index));
    return line;
  }

  // ── the edits: each a tree change and a redraw ──

  /** A panel added where Spotfire adds one: the largest one split in two (split_tree.addLeaf). */
  add(decl) {
    this.maximized = null;
    this.seat(decl);
    const boxes = Object.fromEntries([...this.panels].filter(([, s]) => s.box).map(([k, s]) => [k, s.box]));
    this.root = addLeaf(this.root, decl.id, boxes);
    this.drawArea();
  }

  /** A panel closed: its part let go, its share given back to the ones beside it. */
  remove(id) {
    const seat = this.panels.get(id);
    if (!seat || seat.decl.dock) return;
    seat.disconnect();
    if (seat.part) seat.part.destroy();
    seat.el.remove();
    this.panels.delete(id);
    this.root = removeLeaf(this.root, id);
    if (this.maximized === id) this.maximized = null;
    this.drawArea();
  }

  /** A panel moved onto an edge of another (`targetId`) or of the page (null); onto another's middle - the two swap. */
  dock(id, targetId, edge) {
    this.root = edge === 'center' ? swapLeaves(this.root, id, targetId) : dockLeaf(this.root, id, targetId, edge);
    this.drawArea();
  }

  /** The line after child `index` of the split at `path` dragged `delta` pixels, the two children `pxA` and `pxB` now. */
  resizeAt(path, index, pxA, pxB, delta) {
    const split = nodeAt(this.root, path);
    if (!split || !split.split) return;
    const sizes = split.children.map((c) => (c.size === undefined ? 1 : c.size));
    this.root = withSizes(this.root, path, resizePair(sizes, index, pxA, pxB, delta, MIN_SIZE));
    this.drawArea();
  }

  /** One panel over the whole area (null: the tree again). A view, not the layout - Save keeps the tree. */
  maximize(id) {
    this.maximized = id && this.panels.has(id) ? id : null;
    this.drawArea();
  }

  /** The layout as it stands: the tree, and each panel's declaration as its part holds it now. */
  layoutNow() {
    return { ...this.layout, root: this.root, panels: [...this.panels.values()].map((s) => {
      const held = s.part && typeof s.part.declaration === 'function' ? s.part.declaration() : s.decl;
      const { options: _pageDeps, ...own } = held;
      return { ...own, ...(s.decl.dock ? { dock: s.decl.dock, size: s.decl.size } : {}) };
    }) };
  }

  // ── the gestures (a browser's; the edits above are what they call) ──

  /** Presses on a title start a move; the document hears the rest. Once per render. */
  listen() {
    if (this.layout.locked || typeof this.area.addEventListener !== 'function') return;
    this.area.addEventListener('pointerdown', (event) => this.beginMove(event));
  }

  /** Follow the pointer on the document until it is let go; `onUp` gets the last event, Escape cancels. */
  follow(onMove, onUp) {
    const doc = this.doc;
    const move = (e) => onMove(e);
    const done = (e, cancelled) => {
      doc.removeEventListener('pointermove', move);
      doc.removeEventListener('pointerup', up);
      doc.removeEventListener('keydown', key);
      onUp(e, cancelled);
    };
    const up = (e) => done(e, false);
    const key = (e) => { if (e.key === 'Escape') done(e, true); };
    doc.addEventListener('pointermove', move);
    doc.addEventListener('pointerup', up);
    doc.addEventListener('keydown', key);
  }

  beginResize(event, line, path, index) {
    if (event.button !== 0) return;
    event.preventDefault();
    const box = line.parentNode;
    const kids = [...box.children].filter((k) => k.className !== 'sf-splitter');
    const [a, b] = [kids[index], kids[index + 1]];
    const row = line.getAttribute('data-dir') === 'row';
    const px = (el) => { const r = el.getBoundingClientRect(); return row ? r.width : r.height; };
    const pxA = px(a);
    const pxB = px(b);
    const at = row ? event.clientX : event.clientY;
    const split = nodeAt(this.root, path);
    const sizes = split.children.map((c) => (c.size === undefined ? 1 : c.size));
    line.classList.add('is-dragging');
    // While dragged only the two boxes change; the tree takes the result when the line is let go.
    this.follow((e) => {
      const next = resizePair(sizes, index, pxA, pxB, (row ? e.clientX : e.clientY) - at, MIN_SIZE);
      a.style.flex = `${next[index]} 1 0px`;
      b.style.flex = `${next[index + 1]} 1 0px`;
    }, (e, cancelled) => {
      line.classList.remove('is-dragging');
      if (cancelled) { this.drawArea(); return; }
      this.resizeAt(path, index, pxA, pxB, (row ? e.clientX : e.clientY) - at);
    });
  }

  beginMove(event) {
    if (event.button !== 0 || !event.target || typeof event.target.closest !== 'function') return;
    const handle = event.target.closest('[data-part-title]');
    if (!handle || event.target.closest('button, select, input')) return;
    const cell = handle.closest('[data-cell]');
    if (!cell || !this.area.contains(cell)) return;
    const id = cell.getAttribute('data-cell');
    const [x0, y0] = [event.clientX, event.clientY];
    let moving = false;
    let landing = null;
    this.follow((e) => {
      if (!moving && Math.hypot(e.clientX - x0, e.clientY - y0) < DRAG_START) return;
      moving = true;
      landing = this.landingAt(id, e.clientX, e.clientY);
      this.showDrop(landing);
    }, (e, cancelled) => {
      this.showDrop(null);
      if (!moving || cancelled || !landing) return;
      this.dock(id, landing.target, landing.edge);
    });
  }

  /** Where a part dropped at (x, y) lands: near the area's border, that edge of the page; else the edge of the part under
   *  the pointer it is nearest. Over itself or outside the area: nowhere. */
  landingAt(id, x, y) {
    const area = this.area.getBoundingClientRect();
    if (x < area.left || x > area.right || y < area.top || y > area.bottom) return null;
    const page = [['left', x - area.left], ['right', area.right - x], ['top', y - area.top], ['bottom', area.bottom - y]]
      .filter(([, d]) => d < PAGE_EDGE).sort((p, q) => p[1] - q[1])[0];
    if (page) return { target: null, edge: page[0], box: area };
    const under = this.doc.elementFromPoint(x, y);
    const cell = under && under.closest ? under.closest('[data-cell]') : null;
    if (!cell || cell.getAttribute('data-cell') === id) return null;
    const box = cell.getBoundingClientRect();
    return { target: cell.getAttribute('data-cell'), edge: edgeAt(box, x, y, DROP_EDGE), box };
  }

  /** The drop's mark: the half of the target the part would take - all of it, its middle (the two swap). */
  showDrop(landing) {
    if (!landing) { if (this.drop) this.drop.remove(); this.drop = null; return; }
    if (!this.drop) {
      this.drop = this.doc.createElement('div');
      this.drop.className = 'sf-drop';
    }
    const area = this.area.getBoundingClientRect();
    const b = landing.box;
    const half = { left: [0, 0, 0.5, 1], right: [0.5, 0, 0.5, 1], top: [0, 0, 1, 0.5], bottom: [0, 0.5, 1, 0.5], center: [0, 0, 1, 1] }[landing.edge];
    Object.assign(this.drop.style, { left: `${b.left - area.left + b.width * half[0]}px`, top: `${b.top - area.top + b.height * half[1]}px`,
      width: `${b.width * half[2]}px`, height: `${b.height * half[3]}px` });
    this.area.appendChild(this.drop);
  }

  /** The seated part, by declaration id. For the host and for the harness. */
  partOf(id) {
    const seat = this.panels.get(id);
    return seat ? seat.part : null;
  }

  /** Where a panel sits in the tree (its child indices), or null - docked or not seated. */
  pathOf(id) { return pathTo(this.root, id); }

  destroy() {
    for (const seat of this.panels.values()) {
      seat.disconnect();
      if (seat.part) seat.part.destroy();
    }
    this.panels.clear();
    if (this.host) this.host.textContent = '';
  }
}
