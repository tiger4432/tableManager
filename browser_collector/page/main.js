// The extension inside a tab: picking an element for a template, a preview, and a run's batches and next pages. Every
// product call goes through the service worker (background.js) - a page cannot call the product (CORS).
import { DomPage, readOpenedHere } from '../lib/page_dom.js';
import { readBatch } from '../lib/batch.js';
import { selectorFor, itemSelector, repeating } from '../lib/selectors.js';
import { visibleText } from '../lib/open_check.js';

/** A question to the service worker -> its answer (a refusal throws its sentence). */
const ask = (msg) => chrome.runtime.sendMessage(msg).then((a) => { if (!a || !a.ok) throw new Error(a ? a.error : 'no answer'); return a.value; });
/** A word to whoever listens (the panel) - nothing comes back. */
const say = (msg) => chrome.runtime.sendMessage(msg).catch(() => {});
const pages = new Map();             // run id -> its DomPage (a list keeps what was read across batches)

function pageFor(t, runId = null) {
  const make = () => new DomPage(t, {
    openTab: (address, fields, pairValue) => ask({ type: 'tab.read', t, address, fields, pairValue }).catch((e) => ({ opened: false, detail: e.message })),
  });
  if (!runId) return make();
  if (!pages.has(runId)) {
    const page = make();
    const open = page.open.bind(page);
    let item = 0;
    page.open = async (h, fields) => {          // the run screen draws the wait
      item += 1;
      say({ type: 'run.waiting', runId, seconds: t.waitSeconds, item });
      try { return await open(h, fields); } finally { say({ type: 'run.waited', runId }); }
    };
    pages.set(runId, page);
  }
  return pages.get(runId);
}
const existingFor = (t) => (cellsList) => ask({ type: 'keys.existing', t, cellsList }).then((a) => {
  if (a.error) throw new Error(a.error);
  return new Set(a.keys);
});

// ── picking ──────────────────────────────────────────────────────────────────────────────
let picking = null;

function overlay() {
  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647';
  const root = host.attachShadow({ mode: 'closed' });
  document.documentElement.appendChild(host);
  const boxes = [];
  const draw = (els, main) => {
    while (boxes.length) boxes.pop().remove();
    els.forEach((el) => {
      const r = el.getBoundingClientRect();
      const b = document.createElement('div');
      b.style.cssText = `pointer-events:none;position:fixed;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;box-sizing:border-box;`
        + `border:${el === main ? '2px solid' : '1px dashed'} #1a66d0;background:rgba(26,102,208,${el === main ? 0.12 : 0.06})`;
      root.appendChild(b);
      boxes.push(b);
    });
    if (main) {
      const r = main.getBoundingClientRect();
      const tag = document.createElement('div');
      tag.textContent = picking.label(main);
      tag.style.cssText = `pointer-events:none;position:fixed;left:${r.left}px;top:${Math.max(0, r.top - 20)}px;background:#1a66d0;color:#fff;font:12px/20px system-ui;padding:0 6px`;
      root.appendChild(tag);
      boxes.push(tag);
    }
  };
  return { draw, remove: () => host.remove() };
}

/** What a click on `el` gives for `kind` under the template `t` -> {selector, count, base} | {refused}. */
function pickOf(kind, el, t) {
  const area = (t.listArea && document.querySelector(t.listArea)) || null;
  const itemOf = (n) => (t.item ? [...(area || document).querySelectorAll(t.item)].find((i) => i.contains(n)) : null);
  const contentOf = (n) => (t.content ? [...document.querySelectorAll(t.content)].find((c) => c.contains(n)) : null);
  if (kind === 'item') { const within = area && area.contains(el) ? area : null; return itemSelector(repeating(el, within), within); }
  if (kind === 'clickTarget') {
    const item = itemOf(el);
    return item ? { selector: selectorFor(el, item), count: 1 } : { refused: 'pick inside a list item' };
  }
  if (kind === 'column' || kind === 'pair') {
    const item = itemOf(el);
    if (item) return { selector: selectorFor(el, item), base: 'item', count: 1 };
    const content = contentOf(el);
    if (content) return { selector: selectorFor(el, content), base: 'content', count: 1 };
    return { refused: 'pick inside a list item or the content area' };
  }
  return { selector: selectorFor(el, null), count: document.querySelectorAll(selectorFor(el, null)).length };
}

function startPick(kind, t) {
  stopPick();
  const ov = overlay();
  const stop = (e) => { e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation(); };
  const alikeOf = (el) => {
    if (kind !== 'item' || !el.parentElement) return [el];
    const area = (t.listArea && document.querySelector(t.listArea)) || null;
    try { return [...(area && area.contains(el) ? area : document).querySelectorAll(pickOf(kind, el, t).selector)]; } catch { return [el]; }
  };
  const on = {
    mousemove: (e) => { const el = e.target; if (el && el.nodeType === 1) ov.draw(alikeOf(el), kind === 'item' ? repeating(el) : el); },
    click: (e) => {
      stop(e);
      const el = e.target;
      const p = pickOf(kind, el, t);
      const attrs = [...el.attributes].map((a) => a.name);
      say({ type: 'pick.done', kind, ...p, sample: visibleText(el).slice(0, 80), attrs });
      stopPick();
    },
    mousedown: stop, mouseup: stop, pointerdown: stop, pointerup: stop,
    keydown: (e) => { if (e.key === 'Escape') { stop(e); say({ type: 'pick.done', kind, cancelled: true }); stopPick(); } },
  };
  for (const [name, fn] of Object.entries(on)) window.addEventListener(name, fn, true);
  picking = { label: (el) => `${el.tagName.toLowerCase()}${el.classList.length ? `.${[...el.classList].join('.')}` : ''}`, end: () => {
    for (const [name, fn] of Object.entries(on)) window.removeEventListener(name, fn, true);
    ov.remove();
  } };
}
function stopPick() { if (picking) { picking.end(); picking = null; } }

// ── the doors the panel and the service worker knock on ────────────────────────────────────
const DOORS = {
  ping: async () => true,
  'pick.start': async ({ kind, t }) => { startPick(kind, t); return true; },
  'pick.stop': async () => { stopPick(); return true; },
  preview: async ({ t, room }) => readBatch(t, pageFor(t), { room, existing: existingFor(t) }),
  batch: async ({ t, runId, room, first }) => readBatch(t, pageFor(t, runId), { room, existing: existingFor(t), firstIndex: first }),
  next: async ({ t, runId }) => pageFor(t, runId).next(),
  'read.here': async ({ t, fields, pairValue }) => readOpenedHere(t, fields, pairValue),
  'run.end': async ({ runId }) => { pages.delete(runId); return true; },
};

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  const door = DOORS[msg && msg.type];
  if (!door) return false;
  door(msg).then((v) => reply({ ok: true, value: v }), (e) => reply({ ok: false, error: String(e && e.message || e) }));
  return true;
});
