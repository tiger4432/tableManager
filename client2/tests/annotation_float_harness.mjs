// The declaration screen's hover annotation takes no room (owner 10-07 「호버링하면 어노테이션 때문에 UI 진동」, lead
// dee90e340). It was `absolute` inside a scroll box: below the last row it grew the list's scroll height, a scrollbar
// came under the pointer, the row narrowed out from under it, the annotation went, the scrollbar went - again.
// Now it is `fixed` and placed beside its row (`placePopover`, by the image preview's `placeBeside`) when the pointer
// or the focus reaches the row (the screen's root). The browser measurement of the list boxes is the report's; this
// measures the rule, the placement and the wiring, each with a defect that must go red at its named line.
import { readFileSync } from 'node:fs';
import { register } from 'node:module';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
register(pathToFileURL(path.join(HERE, 'lib', 'css_loader.mjs')).href);
const CSS = path.join(HERE, '..', 'src', 'ontology_explorer.css');
const VIEW = path.join(HERE, '..', 'src', 'ontology_explorer_view.js');
const SCREEN = path.join(HERE, '..', 'src', 'ontology_explorer.js');

// The smallest page the screen's controller stands on (as explorer_open_path_harness does).
function element(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], attrs: Object.create(null), _classes: [], dataset: Object.create(null),
    _on: Object.create(null), style: { setProperty() {} }, _text: '',
    get className() { return this._classes.join(' '); }, set className(v) { this._classes = String(v).split(/\s+/).filter(Boolean); },
    classList: { add(...n) { for (const x of n) if (!node._classes.includes(x)) node._classes.push(x); },
      remove(...n) { node._classes = node._classes.filter((c) => !n.includes(c)); }, contains(n) { return node._classes.includes(n); },
      toggle(n, on) { if (on) node.classList.add(n); else node.classList.remove(n); } },
    append(...items) { for (const i of items) if (i) this.children.push(i); }, appendChild(c) { this.children.push(c); return c; },
    replaceChildren(...items) { this.children = items.filter(Boolean); }, removeChild(c) { this.children = this.children.filter((x) => x !== c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); }, removeAttribute(k) { delete this.attrs[k]; },
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }, querySelector() { return null; }, querySelectorAll() { return []; },
    addEventListener(type, fn) { (this._on[type] ||= []).push(fn); }, removeEventListener() {}, focus() {}, scrollIntoView() {},
    closest() { return null; }, contains() { return false; },
    set textContent(v) { this._text = String(v); this.children = []; }, get textContent() { return this._text; },
  };
  return node;
}
globalThis.document = { createElement: element, createDocumentFragment: () => element('#fragment'),
  createTextNode: (t) => { const n = element('#text'); n.textContent = t; return n; },
  addEventListener() {}, removeEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; } };
globalThis.requestAnimationFrame = (fn) => fn();
globalThis.window = { addEventListener() {}, removeEventListener() {}, location: { hash: '' } };

const EDGE = 6.8;
const WINDOW = { innerWidth: 1440, innerHeight: 900,
  getComputedStyle: () => ({ getPropertyValue: (name) => (name === '--space-2' ? ` ${EDGE}px` : '') }) };
/** A row with its annotation, at `rect`; the annotation 250 x 104 as the browser measured it. */
const row = (rect) => {
  const pop = { offsetWidth: 250, offsetHeight: 104, style: {} };
  return { pop, querySelector: (sel) => (sel === ':scope > .oe-popover' ? pop : null),
    ownerDocument: { defaultView: WINDOW, documentElement: {} }, getBoundingClientRect: () => rect };
};

let ran = 0;
let failed = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failed.push(name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};

async function suite(css, view, makeController) {
  console.log('\n── A. the annotation takes no room ──');
  const body = (css.replace(/\/\*[\s\S]*?\*\//g, ' ').match(/#ontology-explorer-root \.oe-popover \{([^}]*)\}/) || [])[1] || '';
  ok('A1 the annotation is fixed, placed by the script - no absolute box in its list, no top or left of its own',
    /position:\s*fixed/.test(body) && !/position:\s*absolute/.test(body) && !/(^|[;\s])(top|left)\s*:/.test(body), body.trim());

  console.log('\n── B. beside its row, inside the window ──');
  const under = row({ left: 1079, top: 506, bottom: 542, right: 1381 });
  view.placePopover(under);
  ok('B1 under its row, from the row\'s left', under.pop.style.left === '1079px' && under.pop.style.top === `${542 + EDGE}px`,
    JSON.stringify(under.pop.style));
  const low = row({ left: 1079, top: 840, bottom: 876, right: 1381 });
  view.placePopover(low);
  ok('B2 no room below: above its row', low.pop.style.top === `${840 - EDGE - 104}px`, JSON.stringify(low.pop.style));
  const right = row({ left: 1300, top: 100, bottom: 136, right: 1420 });
  view.placePopover(right);
  ok('B3 at the window\'s right side: kept inside it', right.pop.style.left === `${1440 - 250 - EDGE}px`, JSON.stringify(right.pop.style));
  let threw = null;
  try { view.placePopover({ querySelector: () => null, ownerDocument: { defaultView: WINDOW } }); } catch (e) { threw = e.message; }
  ok('B4 a row with no annotation is left alone', threw === null, threw);

  console.log('\n── C. the screen places it when the pointer or the focus reaches a row ──');
  const root = element('div');
  makeController({ root, apiBase: '', adminFetch: async () => ({ ok: true, status: 200, json: async () => ({}) }), showToast: () => {} });
  const fire = (type, target) => { for (const fn of root._on[type] || []) fn({ target }); };
  const hit = row({ left: 200, top: 300, bottom: 336, right: 424 });
  fire('mouseover', { closest: (sel) => (sel === '.oe-has-popover' ? hit : null) });
  ok('C1 the pointer reaching a row places its annotation', hit.pop.style.top === `${336 + EDGE}px`, JSON.stringify(hit.pop.style));
  const focused = row({ left: 200, top: 400, bottom: 436, right: 424 });
  fire('focusin', { closest: (sel) => (sel === '.oe-has-popover' ? focused : null) });
  ok('C2 the focus reaching a row places its annotation', focused.pop.style.top === `${436 + EDGE}px`, JSON.stringify(focused.pop.style));
  // Keyboard focus stays on its row while the list scrolls (measured: the row 120 px up, the annotation left behind).
  const kept = row({ left: 200, top: 280, bottom: 316, right: 424 });
  root.querySelector = (sel) => (/focus-visible/.test(sel) ? kept : null);
  fire('scroll', { closest: () => null });
  ok('C3 a list scrolling under a shown annotation places it again', kept.pop.style.top === `${316 + EDGE}px`, JSON.stringify(kept.pop.style));
  return { ran, failed: failed.slice() };
}

const CSS_TEXT = readFileSync(CSS, 'utf8');
const loadView = async (mutate) => (await loadWithProbe(VIEW, mutate ? { mutate } : {})).module;
const loadScreen = async (mutate) => (await loadWithProbe(SCREEN, mutate ? { mutate } : {})).module.createOntologyExplorerController;
const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };

const MUTANTS = [
  { name: 'the annotation is an absolute box again', catches: ['A1'], file: 'css',
    mutate: swap('display: none; position: fixed; z-index: 30;', 'display: none; position: absolute; z-index: 30; left: 6.8px; top: calc(100% - 2px);') },
  { name: 'the annotation is not placed', catches: ['B1'], file: 'view', mutate: swap('  popover.style.top = `${at.top}px`;\n', '') },
  { name: 'the placement is the row\'s own corner, not beside it', catches: ['B1'], file: 'view',
    mutate: swap('  const at = placeBeside(', '  const at = ((r) => ({ left: r.left, top: r.top }))(row.getBoundingClientRect()) || placeBeside(') },
  { name: 'the pointer reaching a row places nothing', catches: ['C1'], file: 'screen',
    mutate: swap("  root.addEventListener('mouseover', placeAnnotation);\n", '') },
  { name: 'the focus reaching a row places nothing', catches: ['C2'], file: 'screen',
    mutate: swap("  root.addEventListener('focusin', placeAnnotation);\n", '') },
  { name: 'a scrolling list leaves a shown annotation behind', catches: ['C3'], file: 'screen',
    mutate: swap("  root.addEventListener('scroll', () => {\n", "  root.addEventListener('scroll-unheard', () => {\n") },
];

console.log('== baseline ==');
const base = await suite(CSS_TEXT, await loadView(), await loadScreen());
const BASE_NAMES = NAMES.slice();
if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
const { wrong } = await scoreMutants(MUTANTS, async (m) => {
  const css = m.file === 'css' ? m.mutate(CSS_TEXT) : CSS_TEXT;
  const view = m.file === 'view' ? await loadView(m.mutate) : await loadView();
  const screen = m.file === 'screen' ? await loadScreen(m.mutate) : await loadScreen();
  const real = console.log;
  console.log = () => {};
  ran = 0; failed = [];
  try { await suite(css, view, screen); } finally { console.log = real; }
  return { failures: failed, ran };
}, { baselineRan: base.ran, baselineNames: BASE_NAMES, title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
process.exit(wrong ? 1 : 0);
