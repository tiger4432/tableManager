// ═══════════════════════════════════════════════════════════════════════════════
// MAP PANEL -- the first real part on the skeleton. Canvas, resize, and BOTH ends of the
// marking contract (it reads one name and writes one, and they need not be the same).
//
// 🔴 NO NEW RENDERER. `map2/painter.js` is the canonical one (`layoutFor`, `paintSeating`,
//    `createCanvasSurface`) and it draws every die here. `surprise_map_view.js` already
//    reuses it and its header carries the reason; a second implementation of this arithmetic
//    is how the picture and the numbers come to disagree.
//
// 🔴 CANVAS, NOT SVG, AND THAT IS A MEASURED CHOICE (`map2/main.js` records it): a production
//    map runs to thousands of dies, so N copies of it as SVG is tens of thousands of nodes
//    per repaint -- and this board seats maps N at a time.
//
// 🔴 NOTHING IS DRAWN THAT WAS NOT SOURCED. A projection the server refused renders its OWN
//    sentence and NO canvas. There is no code path in this file that invents a wafer, a
//    circle, or a cell.
//
// 🔴 THE SERVER SEATED THESE CELLS. `coordinate_unit: "cells_from_origin"` -- the frame
//    transform already ran server-side, so this file applies NONE. Running `computeSeating`
//    over them would transform twice.
//
// 🔴 THE LATTICE COMES FROM THE FRAME'S DECLARATION (`grid_cols`/`grid_rows`/`grid_start_*`),
//    not from the cells' bounding box. Those two answer different questions and they part
//    company exactly at an empty edge -- see `declaredBounds` below for the measurement. The
//    cells' box is still the fallback for a projection whose frame declares no grid.
//
// 🔴 NO SIZE IS DECIDED HERE. There is no width or height constant in this file. The canvas
//    is the box the shell measured, minus whatever the head actually occupies -- measured,
//    not assumed -- so a dragged corner already works the day the shell grows handles.
//
// 🔴 THE PAINTER TAKES COLOURS, IT NEVER READS THEM (`painter.js` calls no `getComputedStyle`
//    by design). A canvas cannot inherit a CSS variable, so the palette below is transcribed
//    from `tokens.css` for the two themes, and it is keyed by the ROLE THAT ARRIVES WITH THE
//    CELL -- not by a kind this client enumerates. A role this table has never seen is drawn
//    in the neutral tone and COUNTED; it is never dropped, because a cell that vanishes
//    because the client did not recognise it is the same defect as a hardcoded kind list.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel, markingIntent } from './panel.js';
import { SIGN } from './marking_store.js';
import { projectionModel } from './api.js';
import { layoutFor, paintSeating, createCanvasSurface } from '../map2/painter.js';

//: Transcribed from `tokens.css`. Keyed by the role string the cell carries.
const ROLES = {
  light: {
    unscanned: '#d7dce4', scanned: '#b9c2cf', found: '#c22f2f',
    unknown: '#8792a5',
    case: '#1a66d0', control: '#8a5a00',
    // A seat the frame DECLARES and no cell arrived for. Quieter than any role, and an
    // outline rather than a fill, because it is an empty seat and not a measurement.
    vacant: '#c9cfda',
  },
  dark: {
    unscanned: '#36425f', scanned: '#55648a', found: '#f87e7e',
    unknown: '#6b7897',
    case: '#6ea8fe', control: '#f6bd35',
    vacant: '#3b465f',
  },
};

const CHROME = Object.freeze({
  LOADING: '읽는 중…',
  FAILED: '맵을 읽지 못했습니다',
  NO_BOX: '자리 없음',
});

function el(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

/** min/max over served coordinates. See the header: this is not a seating. */
function boundsOf(cells) {
  if (!cells.length) return { minX: 0, maxX: -1, minY: 0, maxY: -1, empty: true };
  let minX = Infinity; let maxX = -Infinity; let minY = Infinity; let maxY = -Infinity;
  for (const c of cells) {
    if (c.x < minX) minX = c.x;
    if (c.x > maxX) maxX = c.x;
    if (c.y < minY) minY = c.y;
    if (c.y > maxY) maxY = c.y;
  }
  return { minX, maxX, minY, maxY, empty: false };
}

/**
 * The frame's `grid`, as an object. MEASURED 2026-08-23: the live route serves it as a JSON
 * **string** (`frame.grid = '{"grid_cols": 15, ...}'`), so reading `frame.grid.grid_cols`
 * silently returns undefined. Parsed here, and anything that is not an object is refused
 * quietly -- a frame that declares nothing is a frame the cells have to speak for.
 */
function parseGrid(grid) {
  if (!grid) return null;
  if (typeof grid === 'object') return grid;
  if (typeof grid !== 'string') return null;
  try {
    const parsed = JSON.parse(grid);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (e) {
    return null;
  }
}

/**
 * 🔴 THE LATTICE IS THE FRAME'S, NOT THE CELLS'. `boundsOf` answers 「어디까지 값이 왔나」,
 * which is a different question from 「이 웨이퍼는 몇 칸인가」, and the two differ exactly when
 * the edge is empty: measured, a frame declaring 15x15 arrives with cells spanning 0..13, and
 * taking the cells' box drew it 14x14 -- the empty column and row did not shrink, they
 * DISAPPEARED, and a wafer whose edge dies never ran became a different shape without saying so.
 * `null` when the frame declares no grid; then the cells' box stands, as before.
 */
function declaredBounds(frame) {
  const grid = parseGrid(frame && frame.grid);
  if (!grid) return null;
  const cols = Number(grid.grid_cols);
  const rows = Number(grid.grid_rows);
  if (!Number.isFinite(cols) || !Number.isFinite(rows) || cols <= 0 || rows <= 0) return null;
  // ⛔ CELL COUNTS FROM THE ORIGIN. No pitch, no mm: `coordinate_unit` is
  // `cells_from_origin` and multiplying by `phys_chip_x` would invent a second transform.
  const minX = Number.isFinite(Number(grid.grid_start_x)) ? Number(grid.grid_start_x) : 0;
  const minY = Number.isFinite(Number(grid.grid_start_y)) ? Number(grid.grid_start_y) : 0;
  return { minX, maxX: minX + cols - 1, minY, maxY: minY + rows - 1, empty: false };
}

/**
 * The declaration, widened by anything that arrived outside it. `paintSeating` does not clip
 * -- its own error text says the scaling is fitted so that no seat can fall outside the
 * window -- so switching the lattice from the cells to the declaration would let a cell the
 * frame did not expect be painted off-canvas and vanish silently. It is drawn, and the
 * declaration is still what the empty edge is measured against.
 */
function unionBounds(a, b) {
  if (!a || a.empty) return b;
  if (!b || b.empty) return a;
  return {
    minX: Math.min(a.minX, b.minX), maxX: Math.max(a.maxX, b.maxX),
    minY: Math.min(a.minY, b.minY), maxY: Math.max(a.maxY, b.maxY),
    empty: false,
  };
}

export class MapPanel extends Panel {
  /**
   * @param {object} host  this panel's own element, from the shell.
   * @param {{axis: string, load: Function, dpr?: number, ...PanelDeps}} deps
   *        `load` is `() => Promise<lot_map body>` -- injected by the composition root, so
   *        this part never knows a URL and the day the route moves, one line in `main.js`
   *        changes.
   */
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    this.axis = options.axis;
    this.load = options.load;
    this.dpr = options.dpr || 1;
    this.model = null;
    this.status = 'loading';
    this.failure = null;
    // 🔴 PER-INSTANCE session guard. `ledger_map_panel.js` keeps this at module level, which
    // is exactly why two of it cannot stand on one page: the second instance's answers cancel
    // the first's.
    this._session = 0;
    this._nodes = null;
    this._layout = null;
    this._byXY = null;
    //: What the last paint actually did. Render statistics for the harness and the head line
    //: -- nothing downstream reads this as data.
    this.lastPaint = { cells: 0, marks: 0, vacant: 0 };
  }

  mount() {
    super.mount();
    this.reload();
  }

  /** Fetch, then paint. Stale answers are dropped by sequence, not painted over the current. */
  reload() {
    if (!this.load) return Promise.resolve();
    const mine = ++this._session;
    this.status = 'loading';
    this.render();
    return Promise.resolve()
      .then(() => this.load())
      .then((body) => {
        if (mine !== this._session) return;
        this.model = projectionModel(body, this.axis);
        this.status = 'ready';
        this.render();
      })
      .catch((err) => {
        if (mine !== this._session) return;
        this.model = null;
        this.status = 'error';
        this.failure = String((err && err.message) || err).slice(0, 200);
        this.render();
      });
  }

  // ── DOM ──────────────────────────────────────────────────────────────────────

  render() {
    this._ensureChrome();
    this._writeHead();
    this._paint();
  }

  /** Built ONCE. A marking change must not recreate the canvas or drop the click handler. */
  _ensureChrome() {
    if (this._nodes) return;
    const doc = this.doc;
    const root = el(doc, 'div', 'rb-map');
    const head = el(doc, 'div', 'rb-map__head');
    const title = el(doc, 'span', 'rb-map__title', this.title);
    const sub = el(doc, 'span', 'rb-map__sub');
    const counts = el(doc, 'span', 'rb-map__counts');
    const badge = el(doc, 'span', 'rb-map__badge');
    head.appendChild(title);
    head.appendChild(sub);
    head.appendChild(counts);
    head.appendChild(badge);
    const stage = el(doc, 'div', 'rb-map__stage');
    const canvas = el(doc, 'canvas', 'rb-map__canvas');
    const note = el(doc, 'div', 'rb-map__note');
    stage.appendChild(canvas);
    root.appendChild(head);
    root.appendChild(stage);
    root.appendChild(note);
    this.host.appendChild(root);
    if (canvas.addEventListener) {
      canvas.addEventListener('click', (event) => this._onCanvasClick(event));
    }
    this._nodes = { root, head, title, sub, counts, badge, stage, canvas, note };
  }

  _writeHead() {
    const n = this._nodes;
    n.title.textContent = this.title;
    const m = this.model;
    if (this.status === 'loading') {
      n.sub.textContent = CHROME.LOADING;
      n.counts.textContent = '';
    } else if (this.status === 'error') {
      n.sub.textContent = CHROME.FAILED;
      n.counts.textContent = this.failure || '';
    } else if (m) {
      n.sub.textContent = m.sublabel ? `${m.label} · ${m.sublabel}` : m.label;
      n.counts.textContent = m.drawable
        ? `${m.cells.length}칸 · 발견 ${m.found} · 검사 ${m.scanned}`
        : '';
    }
    // 🔴 THE TWO NAMES ARE ON SCREEN. Two panels reading different markings look identical
    // otherwise, and a reader has no way to tell which one his click moved.
    const read = this.reads || '—';
    const write = this.writes || '—';
    const marked = this.reads && this.markings ? this.markings.count(this.reads) : 0;
    n.badge.textContent = `읽기 ${read} · 쓰기 ${write} · 표시 ${marked}`;
    n.badge.setAttribute('data-reads', read);
    n.badge.setAttribute('data-writes', write);

    // A refusal is content: the server's own sentence, or the token when it sent none.
    const refused = this.status === 'ready' && m && !m.drawable;
    n.note.textContent = refused ? (m.message || m.reason || m.state || '') : '';
    n.root.setAttribute('data-map-state',
      this.status === 'ready' ? (m && m.drawable ? 'ready' : 'refused') : this.status);
  }

  // ── PAINT ────────────────────────────────────────────────────────────────────

  _palette() {
    const root = this.doc && this.doc.documentElement;
    const theme = root && root.getAttribute ? root.getAttribute('data-theme') : null;
    return theme === 'dark' ? ROLES.dark : ROLES.light;
  }

  /** The canvas box: the shell's box minus what the head MEASURES at. No constants. */
  _canvasBox() {
    const n = this._nodes;
    const headH = (n.head && n.head.offsetHeight) || 0;
    const noteH = (n.note && n.note.offsetHeight) || 0;
    return {
      width: Math.max(0, this.box.width),
      height: Math.max(0, this.box.height - headH - noteH),
    };
  }

  _paint() {
    const n = this._nodes;
    const canvas = n.canvas;
    const model = this.model;
    const box = this._canvasBox();
    this._layout = null;
    this._byXY = null;
    this.lastPaint = { cells: 0, marks: 0, vacant: 0 };

    const drawable = this.status === 'ready' && model && model.drawable && model.cells.length;
    if (canvas.style) canvas.style.display = drawable ? 'block' : 'none';
    if (!drawable || !box.width || !box.height) return;

    // Device pixels for the backing store, CSS pixels for the element. The layout is computed
    // in DEVICE pixels, so `_hitCell` divides back out.
    const dpr = this.dpr || 1;
    canvas.width = Math.floor(box.width * dpr);
    canvas.height = Math.floor(box.height * dpr);
    if (canvas.style) {
      canvas.style.width = `${box.width}px`;
      canvas.style.height = `${box.height}px`;
    }
    if (!canvas.getContext) return;   // a document stub with no 2D context: chrome only
    const surface = createCanvasSurface(canvas.getContext('2d'));

    const cells = model.cells;
    const declared = declaredBounds(model.frame);
    const bounds = declared ? unionBounds(declared, boundsOf(cells)) : boundsOf(cells);
    const layout = layoutFor(bounds, { width: canvas.width, height: canvas.height, padding: 0 });
    surface.clear(canvas.width, canvas.height);
    if (layout.empty) return;

    const palette = this._palette();

    // 🔴 「빈 자리」 AND 「없는 자리」 MUST NOT LOOK ALIKE, and until now both were nothing at
    // all. A seat the frame declares and no cell filled is drawn as an OUTLINE: it holds its
    // place, and it is visibly not a measurement. Outside the declared lattice nothing is
    // drawn, which is the other sentence -- there is no seat there to be empty.
    let vacant = 0;
    if (declared) {
      const present = new Set(cells.map((c) => `${c.x},${c.y}`));
      const seats = [];
      for (let y = bounds.minY; y <= bounds.maxY; y += 1) {
        for (let x = bounds.minX; x <= bounds.maxX; x += 1) {
          if (!present.has(`${x},${y}`)) seats.push({ x, y });
        }
      }
      if (seats.length) {
        vacant = paintSeating(surface, { seats, seatCount: seats.length },
          layout, palette.vacant, 'ring').painted;
      }
    }

    // Ground: one group per ROLE THAT ARRIVED. Roles are discovered from the data, never
    // listed here -- a role nobody has seen before gets a group of its own and the neutral
    // tone, and the accounting below proves no cell was dropped on the way.
    const byRole = new Map();
    for (const cell of cells) {
      const role = cell.colorRole || 'unknown';
      let group = byRole.get(role);
      if (!group) { group = []; byRole.set(role, group); }
      group.push(cell);
    }
    let painted = 0;
    for (const [role, group] of byRole) {
      const colour = palette[role] || palette.unknown;
      painted += paintSeating(surface, { seats: group, seatCount: group.length },
        layout, colour).painted;
    }

    // Figure, drawn LAST: the marks. Grouped by SIGN, because「봤는데 안 났다」(control) and
    // 「한 번도 안 봤다」(absent) are different facts and must not look the same.
    const cased = [];
    const control = [];
    for (const cell of cells) {
      const sign = this.signOf(cell.nodeId);
      if (sign === SIGN.CASE) cased.push(cell);
      else if (sign === SIGN.CONTROL) control.push(cell);
    }
    let marks = 0;
    if (control.length) {
      marks += paintSeating(surface, { seats: control, seatCount: control.length },
        layout, palette.control, 'ring').painted;
    }
    if (cased.length) {
      marks += paintSeating(surface, { seats: cased, seatCount: cased.length },
        layout, palette.case, 'ring').painted;
    }

    this._layout = layout;
    this._byXY = new Map(cells.map((c) => [`${c.x},${c.y}`, c]));
    this.lastPaint = { cells: painted, marks, vacant };
  }

  // ── CLICK -> MARK ────────────────────────────────────────────────────────────

  /**
   * The cell under a point in CSS pixels of the canvas, or `null`. DOM-free on purpose, so
   * the hit arithmetic is scorable under bare node.
   */
  hitCell(cssX, cssY) {
    const layout = this._layout;
    if (!layout || layout.empty || !layout.cell || !this._byXY) return null;
    const dpr = this.dpr || 1;
    const x = layout.minX + Math.floor((cssX * dpr - layout.originX) / layout.cell);
    const y = layout.minY + Math.floor((cssY * dpr - layout.originY) / layout.cell);
    return this._byXY.get(`${x},${y}`) || null;
  }

  /**
   * Mark what is under the point. Plain = CASE, with `control` = CONTROL. `mode` is the
   * selection model (`Panel.mark`): a plain click REPLACES, ctrl/cmd ADDS.
   */
  clickAt(cssX, cssY, control, mode) {
    const cell = this.hitCell(cssX, cssY);
    if (!cell) return null;
    this.mark(cell.nodeId, control ? SIGN.CONTROL : SIGN.CASE, mode);
    return cell.nodeId;
  }

  _onCanvasClick(event) {
    const canvas = this._nodes && this._nodes.canvas;
    if (!canvas || !canvas.getBoundingClientRect) return;
    const rect = canvas.getBoundingClientRect();
    const intent = markingIntent(event);
    this.clickAt(event.clientX - rect.left, event.clientY - rect.top,
      intent.sign === SIGN.CONTROL, intent.mode);
  }
}
