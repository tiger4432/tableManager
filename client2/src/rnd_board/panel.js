// ═══════════════════════════════════════════════════════════════════════════════
// PANEL -- the component contract. A CLASS, so two of the same part can stand on one screen.
//
// 🔴 THE MEASURED FAILURE THIS EXISTS TO NOT REPEAT. `src/ledger_map_panel.js` holds `deps`,
//    `mountEl` and `session` at MODULE level, so a second `initLedgerMap` overwrites the
//    first: that file cannot be placed twice on one page, and nothing about it says so. Every
//    piece of per-instance state here is on `this`, set in the constructor.
//
// 🔴 A PANEL DOES NOT DECIDE ITS OWN SIZE. It is handed a box by the shell and re-lays-out
//    when the box changes (`resize`). This is the one condition that keeps the later
//    drag/resize work from being a rewrite: a part that bakes in 560px is a part that gets
//    re-written the day the user drags its corner. There is NO width or height constant in a
//    part, and the harness scores that a panel repaints at a size it never saw at mount.
//
// 🔴 A PANEL DRAWS IN ITS OWN `host` AND NOWHERE ELSE. It never reaches for a sibling, never
//    queries the document, never touches the shell. That is what makes the placement the
//    SHELL's data: a part carries no coordinates because it cannot see any.
//
// 🔴 `document` IS A DEPENDENCY, NOT A GLOBAL -- so a part is scorable under bare node.
//    (`surprise_map_view.js` established that discipline; its header carries the reason.)
//
// MARKINGS: a part declares the name it READS and the name it WRITES, SEPARATELY. They may
// differ -- a rank table reads marking:2 and writes nothing; a map may write marking:1 while
// reading marking:2. The part never learns any other name exists.
// ═══════════════════════════════════════════════════════════════════════════════

import { SIGN } from './marking_store.js';

export class Panel {
  /**
   * @param {object} host  the element THIS panel owns. Made by the shell, never by the part.
   * @param {{doc: Document, markings: import('./marking_store.js').MarkingStore,
   *          reads?: string|null, writes?: string|null, title?: string}} deps
   */
  constructor(host, deps) {
    const options = deps || {};
    this.host = host;
    this.doc = options.doc;
    this.markings = options.markings;
    // The two names, declared at assembly time. `null` is a legitimate value: a part that
    // reads nothing simply never re-renders on a marking, and one that writes nothing is
    // read-only. Neither is a special case anywhere below.
    this.reads = options.reads || null;
    this.writes = options.writes || null;
    this.title = options.title || '';
    // The box, in CSS pixels. Zero until the shell measures -- a part must render something
    // sane before it has ever been sized (first paint happens before the first observation).
    this.box = { width: 0, height: 0 };
    this._unsubscribe = null;
  }

  /** Subscribe, then draw once. The shell calls this; a part does not mount itself. */
  mount() {
    if (this.reads && this.markings) {
      this._unsubscribe = this.markings.subscribe(this.reads, () => this.onMarkingChanged());
    }
    this.render();
  }

  /** The shell hands over a box. The part fits it. */
  resize(width, height) {
    const w = Math.max(0, Math.floor(width));
    const h = Math.max(0, Math.floor(height));
    if (w === this.box.width && h === this.box.height) return;
    this.box = { width: w, height: h };
    this.onResize();
  }

  destroy() {
    if (this._unsubscribe) this._unsubscribe();
    this._unsubscribe = null;
    if (this.host) this.host.textContent = '';
  }

  // ── the marking contract, in two lines a part actually calls ──────────────────

  /** `+1` | `-1` | `0` for a node, under the name THIS part declared it reads. */
  signOf(nodeId) {
    if (!this.reads || !this.markings) return SIGN.ABSENT;
    return this.markings.signOf(this.reads, nodeId);
  }

  /** Write under the name THIS part declared it writes. A part with no write name is inert. */
  mark(nodeId, sign) {
    if (!this.writes || !this.markings) return SIGN.ABSENT;
    return this.markings.toggle(this.writes, nodeId, sign);
  }

  // ── hooks a part overrides ────────────────────────────────────────────────────

  /** Build/redraw the whole panel into `this.host`. */
  render() {}

  /** The marking this part reads changed. Default: redraw. */
  onMarkingChanged() { this.render(); }

  /** The box changed. Default: redraw. */
  onResize() { this.render(); }
}
