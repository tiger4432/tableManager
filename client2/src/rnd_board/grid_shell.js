// ═══════════════════════════════════════════════════════════════════════════════
// GRID SHELL -- placement lives HERE, outside every part.
//
// 🔴 THE LAYOUT IS DATA. A screen is a LIST OF INSTANCE DECLARATIONS:
//
//      { id, part: "map", at: {column, row, columnSpan, rowSpan},
//        reads: "marking:1", writes: "marking:1", title, options: {...} }
//
//    Adding a chart is one entry. Moving one -- which is what the later drag work does -- is
//    a change to `at`, in this list, and NOTHING inside the part changes. That is only true
//    because no part is ever told where it sits: the shell writes `grid-column`/`grid-row`
//    onto the panel element and the part sees a box, never a coordinate.
//
// ⛔ NO DRAG AND NO RESIZE HANDLES. Later work, deliberately not built. What IS built is the
//    one thing that would otherwise have to be retrofitted: every part is MEASURED and told
//    its box, so the day a corner becomes draggable the parts already follow.
//
// 🔴 ONE DIV PER PANEL, MADE HERE, HANDED OVER WHOLE. The part owns everything inside it and
//    nothing outside it. Two instances of the same part therefore cannot collide: they are
//    handed two different elements and hold their state on `this`.
//
// `document` and the size observer are DEPENDENCIES, so the shell is scorable under bare node.
// ═══════════════════════════════════════════════════════════════════════════════

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
  }

  /** Seat every declaration. Calling it again reseats from scratch. */
  render(layout) {
    this.destroy();
    this.layout = layout;
    const doc = this.doc;
    this.host.textContent = '';
    this.host.className = 'rb-board';
    this.host.style.display = 'grid';
    this.host.style.gridTemplateColumns = layout.columns;
    this.host.style.gridTemplateRows = layout.rows;
    if (layout.gap) this.host.style.gap = layout.gap;

    for (const decl of layout.panels || []) {
      const el = doc.createElement('div');
      el.className = 'rb-panel';
      el.setAttribute('data-panel', decl.id);
      // 🔴 THE ONLY PLACE COORDINATES ARE WRITTEN. Nothing downstream reads them back.
      const at = decl.at || {};
      el.style.gridColumn = `${at.column || 1} / span ${at.columnSpan || 1}`;
      el.style.gridRow = `${at.row || 1} / span ${at.rowSpan || 1}`;
      // A panel is a box with its own scroll, so one part's overflow cannot push a neighbour.
      el.style.minWidth = '0';
      el.style.minHeight = '0';
      this.host.appendChild(el);

      const PartClass = this.parts[decl.part];
      if (!PartClass) {
        el.setAttribute('data-panel-state', 'unknown-part');
        el.textContent = `미등록 부품: ${decl.part}`;
        this.panels.set(decl.id, { el, part: null, disconnect: () => {} });
        continue;
      }

      const part = new PartClass(el, {
        doc,
        markings: this.markings,
        reads: decl.reads || null,
        writes: decl.writes || null,
        title: decl.title || '',
        ...(decl.options || {}),
      });
      part.mount();
      const disconnect = this.observeSize(el, (w, h) => part.resize(w, h));
      this.panels.set(decl.id, { el, part, disconnect });
    }
    return this;
  }

  /** The seated part, by declaration id. For the host and for the harness. */
  partOf(id) {
    const seat = this.panels.get(id);
    return seat ? seat.part : null;
  }

  destroy() {
    for (const seat of this.panels.values()) {
      seat.disconnect();
      if (seat.part) seat.part.destroy();
    }
    this.panels.clear();
    if (this.host) this.host.textContent = '';
  }
}
