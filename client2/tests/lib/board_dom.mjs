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

const dataName = (key) => 'data-' + String(key).replace(/[A-Z]/g, (c) => '-' + c.toLowerCase());

function selectorMatches(node, sel) {
  const cls = /^\.([A-Za-z0-9_-]+)$/.exec(String(sel));
  if (cls) return String(node.className || '').split(/\s+/).includes(cls[1]);
  const attr = /^\[([A-Za-z0-9_-]+)="(.*)"\]$/.exec(String(sel));
  if (attr) return node.attrs && node.attrs[attr[1]] === attr[2];
  return false;
}

function querySelectorIn(root, sel) {
  for (const node of walk(root)) if (node !== root && selectorMatches(node, sel)) return node;
  return null;
}

export function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '',
    // CSS custom properties are set through `setProperty`, not by assignment -- a plain
    // object answers the first and throws on the second, which stops a render dead.
    style: { _props: Object.create(null),
             setProperty(k, v) { this._props[String(k)] = String(v); },
             getPropertyValue(k) { return this._props[String(k)] || ''; },
             removeProperty(k) { delete this._props[String(k)]; } },
    children: [],
    attrs: Object.create(null),
    listeners: Object.create(null),
    // The stub reports a zero-height head, so the canvas box equals the panel box here. The
    // browser reports the real one; either way the panel SUBTRACTS what it measured and
    // never assumes a number.
    offsetHeight: 0,
    _text: '',
    parentNode: null,
    // 🔴 `appendChild` MOVES. Measured 2026-09-13: without the detach, a row moved from one box
    //    to another sat in BOTH parents' child lists, and a walk of the tree counted one control
    //    twice -- 「a served list becomes a picker」 read 2 for a single picker. The browser's
    //    appendChild removes the node from its old parent first, and any part that REPARENTS
    //    (folding rows into 「고급」 is one) is measuring nothing until this stub does the same.
    appendChild(c) {
      if (c && c.parentNode && c.parentNode !== this
          && typeof c.parentNode.removeChild === 'function') c.parentNode.removeChild(c);
      this.children.push(c);
      c.parentNode = this;
      return c;
    },
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
    // 🔴 ADDED 2026-09-16 (C-116). `el.remove()` 는 자기를 부모에서 떼냅니다. 없으면
    //    `utils.js` 의 `removeToast` 가 400ms 뒤 «비동기로» 던집니다 — 단언 하나도
    //    안 빨개지고, 리모브를 재는 하니스는 «사라지지 않는 노드»를 정상으로 읽습니다.
    remove() { if (this.parentNode) this.parentNode.removeChild(this); },
    // 🔴 ADDED 2026-09-16 (C-121). `dom_patch.commitTree` 가 «첫 커밋»에 이것을 부릅니다 —
    //    자식이 하나가 아니면 patch 를 안 하고 통째로 갈아 끼웁니다. 이 철자가 없으면
    //    온톨로지 탐색기가 이 문서에 «한 번도» 못 앉고, 그러면 그 화면에 대한 단언은
    //    전부 「아무도 채점하지 않은 주장」이 됩니다 (같은 부류를 지난 라운드에 둘 잡았습니다:
    //    `id` 접근자 · `remove()`).
    replaceChildren(...cs) {
      for (const c of [...this.children]) this.removeChild(c);
      for (const c of cs) this.appendChild(c);
    },
    setAttribute(k, v) {
      this.attrs[String(k)] = String(v);
      if (String(k) === 'class') this.className = String(v);
    },
    // 🔴 ADDED 2026-09-16 (C-116). 브라우저에서 `el.id = 'x'` 는 `setAttribute('id','x')`
    //    와 «같은 것»이다. 이 스텁은 대입을 평범한 속성으로 받아 `attrs.id` 에 안 넣었고,
    //    그래서 `getElementById` 가 그 노드를 «영원히 못 찾았다». 그 차이는 오류를 안 낸다 —
    //    `utils.js` 의 `toastContainer()` 는 못 찾으면 «새로 만들므로», 하니스가 보는 토스트는
    //    매번 «새 컨테이너에 하나»였고 쌓임도 접힘도 «한 번도 안 재졌다».
    get id() { return this.getAttribute('id') || ''; },
    set id(v) { this.setAttribute('id', v); },
    getAttribute(k) {
      return Object.prototype.hasOwnProperty.call(this.attrs, String(k))
        ? this.attrs[String(k)] : null;
    },
    // 🔴 ADDED 2026-09-13 (C-100). A part that says 「열림」 with a class needs this, and it
    //    reads and writes THE SAME STRING as `className` -- two separate lists would let a
    //    class added through one be invisible to the other, so the harness would see 「닫힘」
    //    while the screen is open. No errors either way.
    classList: {
      _list() { return String(node.className || '').split(/\s+/).filter(Boolean); },
      _write(parts) { node.className = parts.join(' '); },
      add(...names) {
        const parts = this._list();
        for (const name of names) if (!parts.includes(name)) parts.push(name);
        this._write(parts);
      },
      remove(...names) {
        this._write(this._list().filter((p) => !names.includes(p)));
      },
      contains(name) { return this._list().includes(name); },
      toggle(name, force) {
        const has = this.contains(name);
        const want = force === undefined ? !has : !!force;
        if (want) this.add(name); else this.remove(name);
        return want;
      },
    },
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    // 🔴 ADDED 2026-09-13 (C-86). A stub that RECORDS listeners and cannot fire them scores
    //    what was wired, never what happens -- and 「the add control opens a name field」 is a
    //    claim about what happens. Bubbling is one level, which is all the delegation here
    //    needs (the form box listens for its children's `change`).
    dispatch(type, event = {}) {
      const ev = { type, target: this, ...event };
      for (const fn of this.listeners[type] || []) fn(ev);
      // Bubbles ALL the way, as a real `change` does. One level was the first spelling and
      // it made delegation look broken: a control nested four deep under the box that listens
      // is the ordinary case, not the exception.
      let up = this.parentNode;
      while (up) {
        for (const fn of up.listeners[type] || []) fn(ev);
        up = up.parentNode;
      }
      return ev;
    },
    // The two selector forms this repository's parts actually pass. Not a selector engine:
    // an engine that silently answers the wrong thing is worse than one that answers nothing,
    // so anything else returns null and the caller's assertion fails loudly.
    querySelector(sel) { return querySelectorIn(this, sel); },
    querySelectorAll(sel) { return walk(this).filter((n) => selectorMatches(n, sel)); },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  node.ownerDocument = doc;
  // `dataset.fooBar` IS `data-foo-bar`, and both spellings must reach one place -- the parts
  // write `el.dataset.action` and the harnesses read `attrs['data-action']`.
  node.dataset = new Proxy(Object.create(null), {
    get: (_t, key) => node.attrs[dataName(key)],
    set: (_t, key, value) => { node.attrs[dataName(key)] = String(value); return true; },
    has: (_t, key) => dataName(key) in node.attrs,
    deleteProperty: (_t, key) => { delete node.attrs[dataName(key)]; return true; },
    ownKeys: () => Object.keys(node.attrs).filter((k) => k.startsWith('data-'))
      .map((k) => k.slice(5).replace(/-([a-z])/g, (_m, c) => c.toUpperCase())),
    getOwnPropertyDescriptor: () => ({ enumerable: true, configurable: true }),
  });
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
    // 🔴 ADDED 2026-09-13 (C-95). `admin.js` reaches every panel with `byId(...)`, so a stub
    //    without this cannot run the SEATING code -- only the panel's own. The difference is
    //    「this panel draws that」 versus 「the page puts that panel there」, and the second is
    //    where the chain rule editor's user path actually broke.
    // ⚠️ A WALK, NOT A REGISTRY. An id set after the node is attached must still be found, and
    //    a registry filled at creation time would answer for detached nodes as well -- which
    //    is how a harness scores a screen nobody assembled.
    getElementById(id) {
      const want = String(id);
      for (const root of [doc.body, doc.documentElement]) {
        if (!root) continue;
        const hit = walk(root).find((el) => el.attrs && el.attrs.id === want);
        if (hit) return hit;
      }
      return null;
    },
    // The document's own two, delegated to the tree it owns. `admin.js` reaches a dozen
    // page parts this way before it ever seats a panel.
    querySelector(sel) { return doc.documentElement.querySelector(sel); },
    querySelectorAll(sel) { return doc.documentElement.querySelectorAll(sel); },
    addEventListener() {},
  };
  doc.documentElement = makeNode(doc, 'html');
  doc.documentElement.setAttribute('data-theme', theme || 'light');
  doc.body = makeNode(doc, 'body');
  doc.documentElement.appendChild(doc.body);
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
