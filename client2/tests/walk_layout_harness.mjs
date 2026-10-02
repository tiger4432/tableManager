/**
 * Walk page layout A (lead 2b5819e1d · owner 10-02 「걷기는 A로」 · 「영어로도 바꿔」).
 *
 *   node client2/tests/walk_layout_harness.mjs
 *
 * The page is stood up through `boot(doc, host, deps)` and driven through its own controls.
 * 🔴 THE WIRE IS THE GATE THE ORDER NAMES: the same choices made through the new controls send the
 *    same request the old page sent. `fixtures/walk_wire_before.json` was recorded from the page
 *    BEFORE the layout changed, through the old controls, with the same declaration as here.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'walk', 'main.js');
const STYLES = path.join(HERE, '..', 'src', 'walk', 'styles.js');
const { WALK_CSS: REAL_CSS } = await import('../src/walk/styles.js');
const BEFORE = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'walk_wire_before.json'), 'utf8'));
const LF = String.fromCharCode(10);
const HANGUL = /[가-힣]/;

function makeDoc() {
  const make = (tag) => option(tag, {
    tagName: tag, children: [], attrs: {}, listeners: {},
    className: '', value: '', checked: false, type: '', _text: '',
    append(...cs) { cs.forEach((c) => this.children.push(c)); },
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children = []; },
  });
  return { createElement: make, head: make('head') };
}
function option(tag, node) {
  if (tag !== 'option') return node;
  delete node.value;
  return Object.defineProperty(node, 'value', {
    get() { return this._value !== undefined ? this._value : this.textContent; },
    set(v) { this._value = String(v); },
  });
}
const walkAll = (el, out = []) => { out.push(el); el.children.forEach((c) => walkAll(c, out)); return out; };
const settle = async () => { for (let i = 0; i < 8; i += 1) await Promise.resolve(); };
const fire = (el, type) => { for (const fn of (el && el.listeners[type]) || []) fn(); };
const classes = (e) => String(e.className || '').split(/\s+/);

// The declaration the before-fixture was recorded with.
const DECL = { ok: true,
  entities: [{ type: 'die@1', keys: ['mat_id', 'x'] }, { type: 'wafer@1', keys: ['wafer'] }],
  predicates: [
    { name: 'in_container@1', subjects: ['die@1'], object: { types: ['wafer@1'] } },
    { name: 'transfer@1', subjects: ['die@1'], object: { types: ['die@1'] } },
    { name: 'observed@1', subjects: ['die@1'], object: { types: ['wafer@1'] } }] };
const RESULT = { nodes: [{ id: 'n:1', type: 'wafer@1', label: 'W-1', depth: 1, keys: { wafer: 'W-1' } }],
  edges: [] };

let ran = 0;
const NAMES = [];
let failures = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failures.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);

async function stand(mod) {
  const asked = [];
  const doc = makeDoc();
  const host = doc.createElement('div');
  const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
    const u = String(url);
    asked.push(u);
    if (u.includes('/key-values')) return { ok: true, status: 200, json: async () => ({ nodes: [], scanned: 0 }) };
    if (u.includes('/subgraph')) return { ok: true, status: 200, json: async () => RESULT };
    return { ok: true, status: 200, json: async () => DECL };
  } });
  await settle();
  const all = () => walkAll(host);
  const find = (test) => all().find(test);
  const cellInput = (name) => {
    const box = find((e) => e.tagName === 'label' && e.children.some((c) => c.textContent === name)
      && e.children.some((c) => c.tagName === 'input'));
    return box && box.children.find((c) => c.tagName === 'input');
  };
  const act = {
    type: async (t) => { const s = all().filter((e) => e.tagName === 'select')[0]; s.value = t; fire(s, 'change'); await settle(); },
    key: (k, v) => { const i = cellInput(k); i.value = v; fire(i, 'input'); },
    add: async (t) => { const s = find((e) => e.className === 'wk-add'); s.value = t; fire(s, 'change'); await settle(); },
    unchip: async (t) => { fire(find((e) => e.attrs && e.attrs['data-collect'] === t), 'click'); await settle(); },
    route: async () => { fire(find((e) => e.className === 'wk-path'), 'click'); await settle(); },
    loop: async () => { fire(find((e) => classes(e).includes('wk-loopchip')), 'click'); await settle(); },
    fold: async () => { fire(find((e) => e.className === 'wk-fold'), 'click'); await settle(); },
    tick: async (name) => {
      // A mutant can leave the list shut; the cell that follows then fails, the run must not throw.
      const row = find((e) => e.attrs && e.attrs['data-follow'] === name);
      if (row) fire(row.children.find((c) => c.tagName === 'input'), 'change');
      await settle();
    },
    direction: (d) => {
      const s = all().filter((e) => e.tagName === 'select').find((x) => x.children.some((o) => o.textContent === 'outgoing'));
      s.value = d; fire(s, 'change');
    },
    walk: async () => { fire(find((e) => e.className === 'wk-go'), 'click'); await settle(); },
  };
  return { host, handle, asked, all, find, act };
}

async function suite(mod, css = REAL_CSS) {
  console.log(`${LF}-- the parts: the form is the rail, the result its own --`);
  const page = await stand(mod);
  await page.act.type('die@1');
  page.act.key('mat_id', 'M-1');
  page.act.key('x', '12');
  await page.act.add('wafer@1');
  await page.act.route();
  await page.act.loop();
  const rail = page.find((e) => e.className === 'wk-rail');
  const main = page.find((e) => e.className === 'wk-main');
  const inside = (box) => new Set(box ? walkAll(box) : []);
  const inRail = inside(rail);
  const inMain = inside(main);
  const controls = page.all().filter((e) => ['select', 'input', 'button'].includes(e.tagName));
  const stray = controls.filter((e) => !(e.attrs && e.attrs['data-view'] !== undefined) && !inRail.has(e));
  ok('L1 every form control is in the rail', controls.length > 5 && stray.length === 0,
    `${controls.length} controls, ${stray.map((e) => e.className).join(',')} outside`);
  const views = controls.filter((e) => e.attrs && e.attrs['data-view'] !== undefined);
  ok('L2 Table | Graph and the result are in the main part', views.length === 2
    && views.every((e) => inMain.has(e)) && walkAll(main || { children: [] }).some((e) => e.className === 'wk-result'),
    `${views.length} views`);

  console.log(`${LF}-- Follow is one folded line until opened --`);
  const follows = () => page.all().filter((e) => e.attrs && e.attrs['data-follow'] !== undefined).length;
  const foldText = () => (page.find((e) => e.className === 'wk-fold') || { textContent: '' }).textContent;
  ok('L3 folded at first: no follow box drawn, the line says what the route picked',
    follows() === 0 && foldText().startsWith('Follow · in_container, transfer'), `${follows()} | ${foldText()}`);
  await page.act.fold();
  ok('L4 one press opens the list', follows() === 3, String(follows()));

  console.log(`${LF}-- the picked route is the one the fields hold --`);
  const picked = () => page.all().filter((e) => classes(e).includes('wk-route') && classes(e).includes('is-on')).length;
  eq('L5 the route the press filled is marked', picked(), 1);
  await page.act.tick('observed@1');
  eq('L6 a follow ticked by hand takes the mark off - the fields no longer hold that route', picked(), 0);

  console.log(`${LF}-- the wire: the same choices send what the old page sent --`);
  page.act.direction('outgoing');
  page.act.key('hops', '3');
  page.act.key('node_limit', '200');
  await page.act.walk();
  const sent = page.asked.filter((u) => u.includes('/subgraph'));
  eq('L7 the full set of choices: the same request as before the layout', sent[0], BEFORE.full);
  const bare = await stand(mod);
  await bare.act.type('die@1');
  bare.act.key('mat_id', 'M-1');
  await bare.act.walk();
  eq('L8 a type and a key, nothing else: the same request as before', bare.asked.filter((u) => u.includes('/subgraph'))[0],
    BEFORE.bare);

  console.log(`${LF}-- the result's title is what was asked, not what the form holds now --`);
  const title = () => (page.find((e) => e.className === 'wk-title') || { textContent: '' }).textContent;
  const asked = title();
  page.act.key('mat_id', 'M-2');
  await page.act.unchip('wafer@1');
  ok('L9 the title names the walk that was sent, and stays after the form changes',
    asked === 'die M-1 · 12 → wafer' && title() === asked, `${asked} | ${title()}`);
  ok('L10 × takes a collected type out and + Type offers it again',
    !page.find((e) => e.attrs && e.attrs['data-collect'] === 'wafer@1')
      && page.find((e) => e.className === 'wk-add').children.some((o) => o.value === 'wafer@1'));

  console.log(`${LF}-- the words are English --`);
  const korean = page.all().filter((e) => !e.children.length && HANGUL.test(e.textContent || ''))
    .map((e) => e.textContent);
  ok('L11 nothing drawn in the walk page is Korean', korean.length === 0, korean.join(' | '));

  // 🔴 「Walk stays at the rail's foot」 is the tree AND the stylesheet: this DOM has no layout, so the cell
  //    reads where Walk stands and that WALK_CSS (the rules the page carries) pins that box and scrolls the
  //    form. The lead's mutant renamed the foot's class and nothing went red (L1 only says 「in the rail」).
  console.log(`${LF}-- Walk stays at the rail's foot --`);
  const rules = [...css.replace(/\/\*[\s\S]*?\*\//g, ' ').matchAll(/([^{}]+)\{([^}]*)\}/g)]
    .map((m) => [m[1].split(',').map((s) => s.trim()), m[2]]);
  const ruled = (selector, prop) => rules.some(([sels, body]) => sels.includes(selector) && body.includes(prop));
  const kids = rail ? rail.children : [];
  const go = page.find((e) => e.className === 'wk-go');
  const holder = kids.find((k) => walkAll(k).includes(go));
  const footCls = holder ? classes(holder)[0] : '';
  const formCls = kids[0] ? classes(kids[0])[0] : '';
  ok('L12 Walk stands in the rail\'s last box, after the form, and the stylesheet pins that box while the form scrolls',
    Boolean(go) && holder === kids[kids.length - 1] && kids.length > 1
      && ruled(`.${footCls}`, 'flex: none') && ruled(`.wk-rail > .${formCls}`, 'overflow-y: auto'),
    JSON.stringify({ footCls, formCls, kids: kids.length, last: holder === kids[kids.length - 1] }));
}

const first = await loadWithProbe(SRC, {});
await suite(first.module);
console.log(`${LF}${failures.length === 0 ? 'PASS' : 'FAIL'} baseline: ${ran} assertions, ${failures.length} failure(s)`);
failures.forEach((f) => console.log(`   x ${f}`));
const base = { ran, names: NAMES.slice(), failures: failures.slice() };

const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const MUTANTS = [
  { id: 'W1', what: 'the step knobs are drawn in the result instead of the rail', catches: 'L1 every',
    mutate: (t) => swap(t, '      renderStep(body);', '      renderStep(main);') },
  { id: 'W2', what: 'Follow starts open', catches: 'L3 folded',
    mutate: (t) => swap(t, '    followOpen: false,', '    followOpen: true,') },
  { id: 'W3', what: 'the picked mark is always on', catches: 'L6 a follow',
    mutate: (t) => swap(t, "      const route = el(doc, 'div', 'wk-route' + (picked ? ' is-on' : ''));",
      "      const route = el(doc, 'div', 'wk-route is-on');") },
  { id: 'W4', what: 'node_limit is no longer sent', catches: 'L7 the full',
    mutate: (t) => swap(t, '    if (Number.isFinite(limit)) out.node_limit = limit;', '') },
  { id: 'W5', what: 'the title reads the live form', catches: 'L9 the title',
    mutate: (t) => swap(t, "      head.append(el(doc, 'span', 'wk-title', askedTitle(state.asked)));",
      "      head.append(el(doc, 'span', 'wk-title', askedTitle(spec())));") },
  { id: 'W6', what: 'the chip × does nothing', catches: 'L10 ',
    mutate: (t) => swap(t, "      chip.addEventListener('click', () => { state.collect.delete(t); render(); });", '') },
  { id: 'W7', what: 'a Korean word is drawn again', catches: 'L11 nothing',
    mutate: (t) => swap(t, "const SERVER_DEFAULT = 'default';", "const SERVER_DEFAULT = '서버 기본';") },
  // The lead's escaped mutant, now named.
  { id: 'W8', what: 'the foot box is renamed, so no rule pins it', catches: 'L12 Walk',
    mutate: (t) => swap(t, "    const foot = el(doc, 'div', 'wk-rail-foot');", "    const foot = el(doc, 'div', 'wk-foot');") },
  { id: 'W9', what: 'Walk is drawn inside the scrolling form', catches: 'L12 Walk',
    mutate: (t) => swap(t, '      renderGo(foot);', '      renderGo(body);') },
  { id: 'W10', what: 'the stylesheet stops pinning the foot', catches: 'L12 Walk', file: STYLES,
    mutate: (t) => swap(t, '.wk-rail-foot { flex: none;', '.wk-rail-foot { flex: 1 1 auto;') },
];
const run = async (m) => {
  ran = 0; NAMES.length = 0; failures = [];
  if (m.file === STYLES) {
    const styles = await loadWithProbe(STYLES, { mutate: m.mutate });
    await suite(first.module, styles.module.WALK_CSS);
  } else {
    const loaded = await loadWithProbe(SRC, { mutate: m.mutate });
    await suite(loaded.module);
  }
  return { ran, names: NAMES.slice(), failures: failures.slice() };
};
const scored = await scoreMutants(MUTANTS, run, { baselineRan: base.ran, baselineNames: base.names,
  title: `${LF}== layout mutants (each must be caught by the check it names) ==` });
console.log(`ASSERTIONS ${base.ran + MUTANTS.length} ${base.failures.length + scored.wrong}`);
process.exit(base.failures.length + scored.wrong === 0 ? 0 : 1);
