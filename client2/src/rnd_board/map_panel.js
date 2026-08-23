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
import { computeSeating, visualExtent } from '../map2/seating.js';

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

/** The alpha an UNMARKED cell keeps while something is marked. Hex, because the painter is
 *  handed colour strings and a canvas cannot inherit a CSS variable. */
const DIM_ALPHA = '40';

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
 * `grid_metadata` -> the seat frame `map2/seating.js` consumes. A TRANSCRIPTION: every field is
 * copied, none is computed. `surprise_map_core.js::seatFrameOf` does the same from ITS frame
 * model; this one reads the ledger route's spelling (`grid_cols`, `grid_y_invert`, ...).
 * `null` when the declaration cannot seat anything -- then the cells stand exactly as they are.
 */
function seatFrameOfGrid(grid) {
  if (!grid) return null;
  const cols = Number(grid.grid_cols);
  const rows = Number(grid.grid_rows);
  if (!Number.isFinite(cols) || !Number.isFinite(rows) || cols <= 0 || rows <= 0) return null;
  return {
    rotation: Number(grid.rotation) || 0,
    side: grid.side || 'front',
    cols,
    rows,
    startX: Number.isFinite(Number(grid.grid_start_x)) ? Number(grid.grid_start_x) : 0,
    startY: Number.isFinite(Number(grid.grid_start_y)) ? Number(grid.grid_start_y) : 0,
    invertY: grid.grid_y_invert === true,
    physWaferDia: grid.phys_wafer_dia,
    physChipX: grid.phys_chip_x,
    physChipY: grid.phys_chip_y,
    physOffsetX: grid.phys_offset_x,
    physOffsetY: grid.phys_offset_y,
    physEdgeMargin: grid.phys_edge_margin,
  };
}

/**
 * 🔴 EVERY MAP STANDS AT 0°, AND THIS IS THE ONE PLACE THAT MAKES IT SO.
 *
 * MEASURED 2026-08-24 on `lot_map?row=SYN-VOID-001&slot=07`: the BOND frame declares
 * `rotation: 180` while dt and core declare `0`. Drawing the stored (x, y) straight into a
 * cell -- which every map on this board did -- puts the bonding wafer on screen upside down,
 * and there is NO WAY TO SEE IT: a rotated wafer is still a plausible wafer. It becomes an
 * answer the moment one marking crosses two maps, because bond (3,4) and core (3,4) are then
 * two different physical dies and the second map lights the wrong one.
 *
 * 🔴 NOT A FORMULA WRITTEN HERE. `map2/seating.js` already holds this seam, transcribed from
 *    `server/utils/coordinate_transformer.py`, with the bounding-box and y-invert terms that
 *    a hand-written rotation drops -- the project has measured what dropping them costs
 *    (3,430 cells on the wrong die, picture still plausible). This calls it.
 *
 * 🔴 NO AXIS NAMES. The input is the FRAME DECLARATION, so a fourth axis costs no code.
 *
 * @returns {{cells, bounds}} `bounds` is the seated lattice (0-based, quarter turns swapped),
 *          or `null` when the frame declares nothing -- then the caller's old lattice stands.
 */
export function seatedProjection(frame, cells) {
  const seatFrame = seatFrameOfGrid(parseGrid(frame && frame.grid));
  if (!seatFrame) return { cells: cells || [], bounds: null };
  const extent = visualExtent(seatFrame);
  const bounds = { minX: 0, maxX: extent.cols - 1, minY: 0, maxY: extent.rows - 1, empty: false };
  if (!cells || !cells.length) return { cells: cells || [], bounds };
  const seating = computeSeating(cells, seatFrame, null);
  // The seat carries its own cell, so every field the boundary stamped (state, role, node_id,
  // n) rides along untouched. Only the two coordinates are answered again.
  return { cells: seating.seats.map((s) => ({ ...s.cell, x: s.x, y: s.y })), bounds };
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
    // 🔴 THE BASIS IS THIS INSTANCE'S STATE, NOT THE SCREEN'S. Map A can stand on bond while
    //    map B stands on dt; the declaration gives the starting one and the pills move it.
    this.axis = options.axis;
    this.bases = Array.isArray(options.bases) ? options.bases.slice() : [];
    // 🔴 THE PAGE IS THIS INSTANCE'S STATE TOO. Map A on 3/25 and map B on 7/25 must not know
    //    about each other, and a marking survives paging because a marking is a set of node
    //    ids -- not a screen state (the harness scores that).
    this.slot = (options.question && options.question.slot) || null;
    this.pages = [];
    // 마킹이 거절된 자리의 «문장». null 이면 거절이 없었다는 뜻입니다.
    this.unmarkable = null;
    this.loadPages = options.loadPages || null;
    // 🔴 「점을 찍으면 그것이 씨앗」 REACHES THE MAP. The trend names the wafer it picked; a map
    //    that declares it follows that name re-targets onto it. Paging never clears a marking.
    this.pageFollows = options.pageFollows || null;
    this.loadByWafer = options.loadByWafer || null;
    this.wafer = null;
    this._followOff = null;
    this.loadBasisCounts = options.loadBasisCounts || null;
    this.basisCounts = null;
    this.body = null;
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
    if (this.pageFollows && this.markings) {
      this._followOff = this.markings.subscribe(this.pageFollows, () => this._onSubjectChanged());
      this._onSubjectChanged();
    }
    if (this.loadPages) {
      Promise.resolve().then(() => this.loadPages())
        .then((pages) => { this.pages = Array.isArray(pages) ? pages : []; this.render(); })
        .catch(() => { this.pages = []; });
    }
    if (this.loadBasisCounts) {
      Promise.resolve().then(() => this.loadBasisCounts())
        .then((counts) => { this.basisCounts = counts || null; this.render(); })
        // A count nobody could fetch stays null and draws as 「—」; it never becomes 0.
        .catch(() => { this.basisCounts = null; });
    }
  }

  destroy() {
    if (this._followOff) this._followOff();
    this._followOff = null;
    super.destroy();
  }

  /** The screen's subject moved; re-target onto that wafer. */
  _onSubjectChanged() {
    if (!this.loadByWafer) return;
    const entries = this.markings ? this.markings.entries(this.pageFollows) : [];
    const wafer = entries.length ? entries[0][0] : null;
    if (!wafer || wafer === this.wafer) return;
    this.wafer = wafer;
    // The slot no longer names this page: it was picked by wafer, not by position.
    this.slot = null;
    const mine = ++this._session;
    this.status = 'loading';
    this.render();
    Promise.resolve().then(() => this.loadByWafer(wafer))
      .then((body) => {
        if (mine !== this._session || !body) return;
        this.body = body;
        this.model = projectionModel(body, this.axis);
        this.status = 'ready';
        this.render();
      })
      .catch(() => { if (mine === this._session) { this.status = 'error'; this.render(); } });
  }

  /** Turn to another slot of the same row. Re-fetches; the marking is untouched. */
  setPage(slot) {
    if (!slot || slot === this.slot) return;
    this.slot = slot;
    this.reload();
  }

  /** Move this instance to another projection of the SAME response. */
  setBasis(axis) {
    if (!axis || axis === this.axis) return;
    this.axis = axis;
    if (this.body) this.model = projectionModel(this.body, axis);
    this.render();
  }

  /** Fetch, then paint. Stale answers are dropped by sequence, not painted over the current. */
  reload() {
    if (!this.load) return Promise.resolve();
    const mine = ++this._session;
    this.status = 'loading';
    this.render();
    return Promise.resolve()
      .then(() => (this.slot ? this.load({ slot: this.slot }) : this.load()))
      .then((body) => {
        if (mine !== this._session) return;
        // 🔴 ONE RESPONSE ALREADY CARRIES ALL THREE PROJECTIONS (measured: bond 141 · dt 11 ·
        //    core 110), so switching the basis is a re-read of what is in hand, not a refetch.
        this.body = body;
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
    // 목업의 상태 알약: 「이 패널이 «왜» 이렇게 그려졌나」. The mockup puts one on every map and
    // it is the difference between a panel you read and a panel you guess at.
    const basis = el(doc, 'span', 'rb-map__basis');
    const pager = el(doc, 'span', 'rb-map__pager');
    const badge = el(doc, 'span', 'rb-map__badge');
    head.appendChild(title);
    head.appendChild(sub);
    head.appendChild(counts);
    head.appendChild(basis);
    head.appendChild(pager);
    head.appendChild(badge);
    const stage = el(doc, 'div', 'rb-map__stage');
    const canvas = el(doc, 'canvas', 'rb-map__canvas');
    const outside = el(doc, 'div', 'rb-map__outside');
    const note = el(doc, 'div', 'rb-map__note');
    stage.appendChild(canvas);
    root.appendChild(head);
    root.appendChild(outside);
    root.appendChild(stage);
    root.appendChild(note);
    this.host.appendChild(root);
    if (canvas.addEventListener) {
      canvas.addEventListener('click', (event) => this._onCanvasClick(event));
    }
    this._nodes = { root, head, title, sub, counts, basis, pager, badge, stage, canvas,
      outside, note };
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
      // What came back is a fact whether or not it can be drawn; hiding it made a refused
      // projection look like an empty response.
      // 🔴 THE COUNTS NAME THEIR OWN SOURCE. 「검사 29」 turned out to mean 「검사되고 본딩된 29」
      //    -- an inspected die with no bonding row silently left the join and a real finding
      //    never reached the picture. The relations the server joined are printed beside the
      //    numbers, so the words change when the join does.
      const source = (m.relations || []).join(' ∩ ');
      n.counts.textContent = m.cells.length
        ? `${m.cells.length}칸 · 발견 ${m.found} · 검사 ${m.scanned}`
          + (source ? ` · ${source} 기준` : '')
        : '';
      if (m.cells.length && !m.ledgerBacked) {
        // A count read off source tables is not a ledger claim, and the difference is the whole
        // reason this board exists.
        n.counts.setAttribute('title', '원장이 아니라 소스 표에서 센 값입니다');
      }
    }
    // 🔴 THE TWO NAMES ARE ON SCREEN. Two panels reading different markings look identical
    // otherwise, and a reader has no way to tell which one his click moved.
    const read = this.reads || '—';
    const write = this.writes || '—';
    // 🔴 WHAT IS COUNTED IS WHAT IS DRAWN. This used to be `count(this.reads)`, the size of the
    // whole NAME -- so the moment another part wrote a node of its own kind under the same
    // name, this badge said 「표시 1」 over a wafer with nothing on it. The name's size is a
    // fact about the name; this badge is a sentence about THIS map.
    const ownCells = (m && m.cells) || [];
    let marked = 0;
    for (const cell of ownCells) if (this.signOf(cell.nodeId) !== SIGN.ABSENT) marked += 1;
    // 🔴 DERIVED FROM THE DECLARATION, not from a new option nobody sets. A panel whose
    //    declaration NAMES an axis was chosen deliberately; one that does not would be
    //    following whatever the control bar picked. Today every map here names its axis.
    this._writeBasisRow(n.basis);
    this._writePager(n.pager);
    n.badge.textContent = `읽기 ${read} · 쓰기 ${write} · 표시 ${marked}`;
    n.badge.setAttribute('data-reads', read);
    n.badge.setAttribute('data-writes', write);

    // A refusal is content: the server's own sentence, or the token when it sent none.
    // 🔴 WHAT THE MAP COULD NOT PLACE. This is the closest line on the screen to why the board
    //    exists: 2,525 inspected seats with a void recorded sat in the ledger and in no picture
    //    at all. It is said as a COUNT when the server counted it, and as 「귀속 불가」 -- with
    //    the server's own sentence -- when it could not. Never as a zero: 「모른다」 and 「없다」
    //    are the two things this whole board refuses to fold together.
    const un = m && m.unplaced;
    if (!un) {
      n.outside.textContent = '';
      n.outside.className = 'rb-map__outside';
    } else if (un.state === 'measured') {
      n.outside.className = 'rb-map__outside is-measured';
      n.outside.textContent = `맵 밖 · 검사 ${un.scanned === null ? '-' : un.scanned}`
        + ` · 발견 ${un.found === null ? '-' : un.found}`;
      if (un.message) n.outside.setAttribute('title', un.message);
    } else {
      n.outside.className = 'rb-map__outside is-unknown';
      n.outside.textContent = `맵 밖 · 귀속 불가${un.message ? ` — ${un.message}` : ''}`;
    }

    // A refusal we can still draw is a CAVEAT, not a blank panel: the sentence stays, the
    // picture appears, and the reader is told which one they are looking at.
    const refused = this.status === 'ready' && m && !m.drawable;
    const canDraw = Boolean(m && m.cells && m.cells.length && declaredBounds(m.frame));
    // 🔴 A REFUSED MARK IS SAID OUT LOUD. Swallowing it would look exactly like a click that
    //    missed, and the reader would try again on a seat that can never take a mark.
    n.note.textContent = refused ? (m.message || m.reason || m.state || '')
      : (this.unmarkable || '');
    n.note.className = refused && canDraw ? 'rb-map__note is-caveat'
      : (this.unmarkable ? 'rb-map__note is-caveat' : 'rb-map__note');
    n.root.setAttribute('data-map-state',
      this.status === 'ready' ? (m && m.drawable ? 'ready' : 'refused') : this.status);
  }

  /**
   * 목업의 페이지 자리 — 「‹ 3/25 ›」 와 «지금 어느 자재인지». Nothing is drawn when the route
   * served no page list: an absent pager is not a one-page row.
   */
  _writePager(host) {
    const doc = this.doc;
    host.textContent = '';
    if (!this.pages.length) return;
    const at = this.pages.indexOf(this.slot);
    const step = (delta) => {
      if (at < 0) return;
      const next = this.pages[at + delta];
      if (next) this.setPage(next);
    };
    const prev = doc.createElement('span');
    prev.className = at > 0 ? 'rb-map__page-step' : 'rb-map__page-step is-end';
    prev.textContent = '‹';
    prev.addEventListener('click', () => step(-1));
    const label = doc.createElement('span');
    label.className = 'rb-map__page-label';
    // The slot AND the wafer it turned out to be: a page number alone is not an identity.
    // 🔴 WHILE THE PAGE IS IN FLIGHT THE PAIR IS NOT TRUE YET. The slot changes the moment it is
    //    clicked and the wafer arrives with the answer, so for one frame the label read
    //    「08 · SYN-BW-001-07」 -- a page number bolted to the previous page's wafer. It says it
    //    is reading instead.
    const loading = this.status === 'loading';
    const wafer = this.model && this.model.frame && this.model.frame.wafer;
    // 🔴 A PAGE PICKED BY WAFER HAS NO SLOT NUMBER, and 「- / 25」 would imply it is page nothing
    //    of twenty-five. It names the wafer alone, which is how it was chosen.
    label.textContent = (this.slot ? `${this.slot} / ${this.pages.length}` : '씨앗')
      + (loading ? ' · 읽는 중…' : (wafer ? ` · ${wafer}` : ''));
    const next = doc.createElement('span');
    next.className = at >= 0 && at < this.pages.length - 1
      ? 'rb-map__page-step' : 'rb-map__page-step is-end';
    next.textContent = '›';
    next.addEventListener('click', () => step(1));
    host.appendChild(prev);
    host.appendChild(label);
    host.appendChild(next);
  }

  /**
   * 목업 맵 하단의 기반 줄. 「누르면 그 타입으로 추적해서 그 맵을 그린다」 -- so it is a
   * SELECTOR, and the chosen one is visible.
   */
  _writeBasisRow(host) {
    const doc = this.doc;
    host.textContent = '';
    if (!this.bases.length) return;
    const label = doc.createElement('span');
    label.className = 'rb-map__basis-label';
    label.textContent = '기반';
    host.appendChild(label);
    for (const b of this.bases) {
      const pill = doc.createElement('span');
      const chosen = b.axis === this.axis;
      pill.className = chosen ? 'rb-map__basis-pill is-chosen' : 'rb-map__basis-pill';
      pill.setAttribute('data-basis-axis', b.axis);
      const text = doc.createElement('span');
      text.textContent = b.label || b.axis;
      pill.appendChild(text);
      const n = doc.createElement('span');
      const count = this.basisCounts ? this.basisCounts[b.type || b.label] : undefined;
      n.className = typeof count === 'number' ? 'rb-map__basis-count' : 'rb-map__basis-count is-absent';
      // 「—」 while the count has not arrived; a zero here would claim the type is empty.
      n.textContent = typeof count === 'number' ? String(count) : '—';
      pill.appendChild(n);
      pill.addEventListener('click', () => this.setBasis(b.axis));
      host.appendChild(pill);
    }
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

    // 🔴 A CONSENSUS GRID IS STILL A GRID -- BUT ONLY THE GRID. `dt`/`core` come back
    //    `state: no_frame` while carrying their `grid` (dt 15x10 · core 23x23) and their cells.
    //    The order was 「테두리는 그릴 수 있습니다 — 「프레임 없음」으로 읽고 안 그리지 마십시오」,
    //    and the server's own sentence says why it can be no more than the borders: 「슬롯마다
    //    격자 치수가 다르므로 한 장에 겹쳐 그리면 좌표가 전부 어긋난다」. So the lattice is drawn
    //    and the cells are NOT -- a caption under a wrong picture is still a wrong picture.
    const superposed = Boolean(model && !model.drawable && model.cells.length
      && declaredBounds(model.frame));
    const drawable = this.status === 'ready' && model && model.cells.length
      && (model.drawable || superposed);
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

    // 🔴 SEATED FIRST, THEN EVERYTHING. The draw, the vacant lattice, the mark rings and the
    //    click index below all read `cells`, so seating once here is what keeps them agreeing.
    const seated = seatedProjection(model.frame, model.cells);
    const cells = seated.cells;
    const declared = seated.bounds || declaredBounds(model.frame);
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
      const present = superposed ? new Set() : new Set(cells.map((c) => `${c.x},${c.y}`));
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
    // 🔴 MARKING IS DRAWN BY ATTENUATION, not by decorating the hit. Measured in the owner's
    // Spotfire: clicking leaves the marked point at full strength and FADES EVERYTHING ELSE.
    // A ring has to be found; a faded field is read without looking. While nothing is marked
    // nothing fades -- 「아직 안 골랐다」 must not look like 「전부 아니다」.
    // 🔴 MY OWN CELLS, NOT THE NAME'S SIZE. Marking a LAYER in 구성 writes a component id
    //    under the same name, and keying off `markCount()` faded this whole wafer while
    //    nothing on it lit up -- the same defect the 「표시 N」 badge had, in the paint path.
    const attenuating = cells.some((c) => this.signOf(c.nodeId) !== SIGN.ABSENT);
    let painted = 0;
    // 🔴 SUPERPOSED MEANS THE LATTICE, NOT THE CELLS. The server's own sentence reads 「슬롯마다
    //    격자 치수가 다르므로 한 장에 겹쳐 그리면 좌표가 «전부 어긋난다»」, so painting these
    //    cells would draw positions the ledger says are wrong -- a caption under a wrong
    //    picture is still a wrong picture. The frame IS agreed (dt 15x10 · core 23x23), so the
    //    empty lattice is drawn and the sentence says what is missing: a slot.
    if (superposed) {
      this._layout = layout;
      this._byXY = null;
      this.lastPaint = { cells: 0, marks: 0, vacant };
      return;
    }
    for (const [role, group] of byRole) {
      const colour = palette[role] || palette.unknown;
      if (!attenuating) {
        painted += paintSeating(surface, { seats: group, seatCount: group.length },
          layout, colour).painted;
        continue;
      }
      // Same hue, less presence: the role still reads, it just stops competing.
      const lit = group.filter((c) => this.signOf(c.nodeId) !== SIGN.ABSENT);
      const dim = group.filter((c) => this.signOf(c.nodeId) === SIGN.ABSENT);
      if (dim.length) {
        painted += paintSeating(surface, { seats: dim, seatCount: dim.length },
          layout, `${colour}${DIM_ALPHA}`).painted;
      }
      if (lit.length) {
        painted += paintSeating(surface, { seats: lit, seatCount: lit.length },
          layout, colour).painted;
      }
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
    // 🔴 ONLY A NODE ID THE SERVER GAVE MAY BE MARKED (Lead PM ruling, 2026-08-24).
    //    `stampedNodeId` invents one so the picture can be drawn and two panels can agree on
    //    a die -- but a marking is the SUBJECT OF THE NEXT WALK, and an invented subject sends
    //    that walk to a node which does not exist. It would answer 「없음」 for a die that is
    //    right there on screen, and nothing would say why. `nodeIdResolved` already tells the
    //    two apart, so it is the gate. The day the route ships the id, this opens by itself
    //    and no line here changes.
    if (cell.nodeIdResolved !== true) {
      this.unmarkable = '이 자리는 아직 노드가 없습니다 — 서버가 id 를 실으면 마킹됩니다';
      this._writeHead();
      return null;
    }
    this.unmarkable = null;
    this.mark(cell.nodeId, control ? SIGN.CONTROL : SIGN.CASE, mode);
    this._writeHead();
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
