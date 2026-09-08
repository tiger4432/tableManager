// ═══════════════════════════════════════════════════════════════════════════════
// THE DOCUMENT STUB — a page just large enough for the board, and no jsdom.
//
// 🔴 SHARED ON 2026-09-08 for the same reason the loader was: the render-parity harness
//    mounts the same panels and needs the same document. Two stubs would answer the same
//    question two ways, and the one that drifts is the one nobody is running that day.
// ⚠️ The canvas RECORDS rather than draws, so a map panel can be scored on what it asked
//    the context to do without a real one existing.
// ═══════════════════════════════════════════════════════════════════════════════
// ── the document stub ──────────────────────────────────────────────────────────────

export function recordingContext(canvas) {
  const ctx = {
    fillStyle: null,
    strokeStyle: null,
    lineWidth: 1,
    clearRect(x, y, w, h) { canvas.ops.push({ op: 'clear', x, y, w, h }); },
    fillRect(x, y, w, h) { canvas.ops.push({ op: 'fill', x, y, w, h, color: ctx.fillStyle }); },
    strokeRect(x, y, w, h) {
      canvas.ops.push({ op: 'stroke', x, y, w, h, color: ctx.strokeStyle });
    },
  };
  return ctx;
}

export function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '',
    style: {},
    children: [],
    attrs: Object.create(null),
    listeners: Object.create(null),
    // The stub reports a zero-height head, so the canvas box equals the panel box here. The
    // browser reports the real one; either way the panel SUBTRACTS what it measured and
    // never assumes a number.
    offsetHeight: 0,
    _text: '',
    parentNode: null,
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    // 🔴 ADDED 2026-09-08. The board harness only ever mounted MAP panels, which use
    //    `appendChild`; the other eleven parts use `append(...)`. A stub missing it does not
    //    fail one assertion — it throws before the panel renders, so the whole screen is blank
    //    and any comparison of it is a comparison of nothing.
    append(...cs) { for (const c of cs) this.appendChild(c); },
    removeChild(c) {
      const i = this.children.indexOf(c);
      if (i >= 0) this.children.splice(i, 1);
      c.parentNode = null;
      return c;
    },
    setAttribute(k, v) {
      this.attrs[String(k)] = String(v);
      if (String(k) === 'class') this.className = String(v);
    },
    getAttribute(k) {
      return Object.prototype.hasOwnProperty.call(this.attrs, String(k))
        ? this.attrs[String(k)] : null;
    },
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  if (node.tagName === 'CANVAS') {
    node.width = 0;
    node.height = 0;
    node.ops = [];
    node.paints = 0;
    // One `getContext` per paint, so `ops` is THIS paint's ops. `paints` keeps the history
    // that slicing would otherwise hide -- a double paint must still be visible.
    node.getContext = () => { node.ops = []; node.paints += 1; return recordingContext(node); };
  }
  return node;
}

export function makeDoc(theme) {
  const doc = {
    createElement(tag) { return makeNode(doc, tag); },
    createElementNS(ns, tag) { return makeNode(doc, tag); },
  };
  doc.documentElement = makeNode(doc, 'html');
  doc.documentElement.setAttribute('data-theme', theme || 'light');
  return doc;
}

/** The injected size observer, so a resize is something the harness DOES, not waits for. */
export function makeObserver() {
  const seats = [];
  const observe = (el, cb) => {
    const seat = { el, cb, live: true };
    seats.push(seat);
    return () => { seat.live = false; };
  };
  observe.seats = seats;
  observe.fireAll = (w, h) => { for (const s of seats) if (s.live) s.cb(w, h); };
  observe.fireFor = (el, w, h) => {
    for (const s of seats) if (s.live && s.el === el) s.cb(w, h);
  };
  return observe;
}

export const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

export const walk = (node, out = []) => {
  out.push(node);
  for (const c of node.children || []) walk(c, out);
  return out;
};
export const canvasIn = (root) => walk(root).find((n) => n.tagName === 'CANVAS') || null;
export const byClass = (root, cls) => walk(root).filter(
  (n) => String(n.className || '').split(/\s+/).includes(cls));
