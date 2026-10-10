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
  entities: [{ type: 'die', keys: ['mat_id', 'x'] }, { type: 'wafer', keys: ['wafer'] }],
  predicates: [
    { name: 'in_container', subjects: ['die'], object: { types: ['wafer'] } },
    { name: 'transfer', subjects: ['die'], object: { types: ['die'] } },
    { name: 'observed', subjects: ['die'], object: { types: ['wafer'] } }] };
const RESULT = { nodes: [{ id: 'n:1', type: 'wafer', label: 'W-1', depth: 1, keys: { wafer: 'W-1' } }],
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

async function stand(mod, decl = DECL) {
  const asked = [];
  const doc = makeDoc();
  const host = doc.createElement('div');
  const handle = mod.boot(doc, host, { apiBase: '', fetchImpl: async (url) => {
    const u = String(url);
    asked.push(u);
    if (u.includes('/key-values')) return { ok: true, status: 200, json: async () => ({ nodes: [], scanned: 0 }) };
    if (u.includes('/subgraph')) return { ok: true, status: 200, json: async () => RESULT };
    return { ok: true, status: 200, json: async () => decl };
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
    // A Control · B box (lead 99ed68cb7 D), as tick does for Follow.
    control: async (name) => {
      const row = find((e) => e.attrs && e.attrs['data-control'] === name);
      if (row) fire(row.children.find((c) => c.tagName === 'input'), 'change');
      await settle();
    },
    tick: async (name) => {
      // A mutant can leave a row undrawn; the cell that follows then fails, the run must not throw.
      const row = find((e) => e.attrs && e.attrs['data-follow'] === name);
      if (row) fire(row.children.find((c) => c.tagName === 'input'), 'change');
      await settle();
    },
    direction: (d) => {
      const s = all().filter((e) => e.tagName === 'select').find((x) => x.children.some((o) => o.textContent === 'outgoing'));
      s.value = d; fire(s, 'change');
    },
    walk: async () => { fire(find((e) => e.className === 'wk-go'), 'click'); await settle(); },
    // The picked node into the Positive basket (lead bc63378e5: Walk walks the baskets).
    plus: async () => { fire(find((e) => e.className === 'wk-basketadd'), 'click'); await settle(); },
  };
  const ticked = () => all().filter((e) => e.attrs && e.attrs['data-follow'] !== undefined
    && e.children.some((c) => c.tagName === 'input' && c.checked)).map((e) => e.attrs['data-follow']).join(',');
  return { host, handle, asked, all, find, act, ticked };
}

async function suite(mod, css = REAL_CSS) {
  console.log(`${LF}-- the parts: the form is the rail, the result its own --`);
  const page = await stand(mod);
  await page.act.type('die');
  page.act.key('mat_id', 'M-1');
  page.act.key('x', '12');
  await page.act.add('wafer');
  await page.act.route();
  await page.act.loop();
  const rail = page.find((e) => e.className === 'wk-rail');
  const main = page.find((e) => e.className === 'wk-main');
  const inside = (box) => new Set(box ? walkAll(box) : []);
  const side = page.find((e) => e.className === 'wk-side');
  const inRail = inside(rail);
  const inMain = inside(main);
  const inSide = inside(side);
  const controls = page.all().filter((e) => ['select', 'input', 'button'].includes(e.tagName));
  const stray = controls.filter((e) => !(e.attrs && e.attrs['data-view'] !== undefined) && !inRail.has(e) && !inSide.has(e));
  ok('L1 every form control is in the rail', controls.length > 5 && stray.length === 0,
    `${controls.length} controls, ${stray.map((e) => e.className).join(',')} outside`);
  const views = controls.filter((e) => e.attrs && e.attrs['data-view'] !== undefined);
  ok('L2 Table | Graph and the result are in the main part', views.length === 2
    && views.every((e) => inMain.has(e)) && walkAll(main || { children: [] }).some((e) => e.className === 'wk-result'),
    `${views.length} views`);
  const adds = controls.filter((e) => e.className === 'wk-basketadd');
  ok('L16 the start baskets are a part of their own, after the result: both + in it, nothing of the form',
    Boolean(side) && adds.length === 2 && adds.every((e) => inSide.has(e)) && !controls.some((e) => inSide.has(e) && inRail.has(e))
      && page.host.children[page.host.children.length - 1] === side, `${Boolean(side)} ${adds.length}`);

  // 🔴 THE CHECK LIST IS THE MAIN PICK, THE ROUTES THE AID (owner 10-06, lead bf3653401).
  console.log(`${LF}-- Follow: every declared predicate, open, before the routes --`);
  const follows = () => page.all().filter((e) => e.attrs && e.attrs['data-follow'] !== undefined).length;
  ok('L3 open at first: one box per declared predicate, and the route press ticked its predicates',
    follows() === DECL.predicates.length && page.ticked() === 'in_container,transfer',
    `${follows()} of ${DECL.predicates.length} | ${page.ticked()}`);
  const form = rail ? rail.children[0] : { children: [] };
  const holds = (test) => form.children.findIndex((c) => walkAll(c).some(test));
  const followAt = holds((e) => e.attrs && e.attrs['data-follow'] !== undefined);
  const routesAt = holds((e) => e.className === 'wk-path');
  ok('L4 the follow list stands before the route list in the form', followAt >= 0 && routesAt > followAt,
    `follow ${followAt} | routes ${routesAt}`);

  console.log(`${LF}-- the picked route is the one the fields hold --`);
  const picked = () => page.all().filter((e) => classes(e).includes('wk-route') && classes(e).includes('is-on')).length;
  eq('L5 the route the press filled is marked', picked(), 1);
  await page.act.tick('observed');
  eq('L6 a follow ticked by hand takes the mark off - the fields no longer hold that route', picked(), 0);

  console.log(`${LF}-- the wire: the same choices send what the old page sent --`);
  page.act.direction('outgoing');
  page.act.key('hops', '3');
  page.act.key('node_limit', '200');
  await page.act.plus();
  await page.act.walk();
  const sent = page.asked.filter((u) => u.includes('/subgraph'));
  eq('L7 the full set of choices: the same request as before the layout', sent[0], BEFORE.full);
  const bare = await stand(mod);
  await bare.act.type('die');
  bare.act.key('mat_id', 'M-1');
  await bare.act.plus();
  await bare.act.walk();
  eq('L8 a type and a key, nothing else: the same request as before, and node_limit at the server\'s most (lead 34d91c09d 9)',
    bare.asked.filter((u) => u.includes('/subgraph'))[0], `${BEFORE.bare}&node_limit=${mod.NODE_LIMIT}`);
  // fanout_limit (lead 5d946a639): typed, it goes with the walk; blank (the bare walk above), it does not.
  page.act.key('fanout_limit', '50');
  await page.act.walk();
  const queryOf = (p, i) => new URLSearchParams((p.asked.filter((u) => u.includes('/subgraph')).slice(i)[0] || '').split('?')[1] || '');
  ok('L18 fanout_limit typed goes with the walk; blank it does not (lead 5d946a639)',
    queryOf(page, -1).get('fanout_limit') === '50' && !queryOf(bare, 0).has('fanout_limit'),
    `${queryOf(page, -1).get('fanout_limit')} | ${queryOf(bare, 0).has('fanout_limit')}`);
  const limit = bare.find((e) => e.tagName === 'label' && e.children.some((c) => c.textContent === 'node_limit')
    && e.children.some((c) => c.tagName === 'input'));
  const limitInput = limit && limit.children.find((c) => c.tagName === 'input');
  const counts = (bare.find((e) => e.className === 'wk-counts') || { textContent: '' }).textContent;
  ok('L17 node_limit starts at the server\'s most and goes no higher; the counts line says how long the walk took (lead 34d91c09d 9)',
    Boolean(limitInput) && limitInput.value === '1000' && limitInput.max === '1000' && / · \d+\.\d s$/.test(counts),
    `${limitInput && limitInput.value} ${limitInput && limitInput.max} | ${counts}`);
  const sentFollow = (p) => {
    const url = p.asked.filter((u) => u.includes('/subgraph')).pop() || '';
    return new URLSearchParams(url.split('?')[1] || '').getAll('follow').join(',');
  };
  const one = await stand(mod);
  await one.act.type('die');
  one.act.key('mat_id', 'M-1');
  await one.act.tick('transfer');
  await one.act.plus();
  await one.act.walk();
  eq('L13 one box of three ticked: only that one goes as follow', sentFollow(one), 'transfer');
  // D (lead 99ed68cb7): B empty, the one walk it always was; B ticked, the same walk once more with follow = B.
  const params = (u) => [...new URLSearchParams((u || '').split('?')[1] || '').entries()].filter(([k]) => k !== 'follow').map((kv) => kv.join('=')).sort().join('&');
  const followOf = (u) => new URLSearchParams((u || '').split('?')[1] || '').getAll('follow').join(',');
  const subOf = (p) => p.asked.filter((u) => u.includes('/subgraph'));
  ok('LD1 Control · B empty: one walk, the request it always was',
    subOf(one).length === 1 && one.all().some((e) => e.attrs && e.attrs['data-control'] === 'observed'), JSON.stringify(subOf(one)));
  const twice = await stand(mod);
  await twice.act.type('die');
  twice.act.key('mat_id', 'M-1');
  await twice.act.tick('transfer');
  await twice.act.control('observed');
  await twice.act.plus();
  await twice.act.walk();
  const [first, second] = subOf(twice);
  ok('LD2 Control · B ticked: two walks - the first as before, the second the same with follow = B',
    subOf(twice).length === 2 && first === subOf(one)[0] && followOf(second) === 'observed' && params(second) === params(first),
    JSON.stringify(subOf(twice)));
  const kept = await stand(mod);
  await kept.act.type('die');
  await kept.act.add('wafer');
  await kept.act.tick('observed');
  await kept.act.route();
  eq('L14 a route press adds its predicates and keeps a box ticked by hand', kept.ticked(), 'in_container,observed');

  console.log(`${LF}-- the result's title is what was asked, not what the form holds now --`);
  const title = () => (page.find((e) => e.className === 'wk-title') || { textContent: '' }).textContent;
  const asked = title();
  page.act.key('mat_id', 'M-2');
  await page.act.unchip('wafer');
  ok('L9 the title names the walk that was sent - its baskets and what it collects (lead 34d91c09d 6) - and stays after the form changes',
    asked === '+ 1 → wafer' && title() === asked, `${asked} | ${title()}`);
  ok('L10 × takes a collected type out and + Type offers it again',
    !page.find((e) => e.attrs && e.attrs['data-collect'] === 'wafer')
      && page.find((e) => e.className === 'wk-add').children.some((o) => o.value === 'wafer'));

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

  // A route back to the start type (lead 10-09: demo step 2 by a click, no follow or hops typed by hand). A third type:
  // the route list's cap is the types less one, so with two types a route back (two steps) does not fit.
  console.log(`${LF}-- a route back to the start type --`);
  const back = await stand(mod, { ...DECL, entities: [...DECL.entities, { type: 'lot', keys: ['lot'] }],
    predicates: [...DECL.predicates, { name: 'holds', subjects: ['lot'], object: { types: ['wafer'] } }] });
  await back.act.type('wafer');
  await back.act.add('wafer');
  const rowOf = () => back.find((e) => e.className === 'wk-path'
    && e.children.some((c) => c.textContent === 'wafer \u2192 die \u2192 wafer')
    && e.children.some((c) => String(c.textContent).endsWith(' in_container')));
  const filled = () => `${[...back.handle.state.follow].sort().join(',')}|${back.handle.state.hops}`;
  const row = rowOf();
  if (row) { fire(row, 'click'); await settle(); }
  const pressed = filled();
  const box = back.find((e) => classes(e).includes('wk-route') && walkAll(e).includes(rowOf()));
  const chip = box && walkAll(box).find((e) => classes(e).includes('wk-loopchip'));
  if (chip) { fire(chip, 'click'); await settle(); }
  ok('L15 wafer collected from wafer: the route back wafer -> die -> wafer by in_container; pressed, it fills follow and hops; its loop chip adds one',
    Boolean(row) && pressed === 'in_container|2' && filled() === 'in_container,transfer|3',
    `${Boolean(row)} | ${pressed} | ${filled()}`);
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
  { id: 'LDm1', what: 'B walked though empty', catches: 'LD1',
    mutate: (t) => swap(t, 'state.control.size ? await walk(', 'true ? await walk(') },
  { id: 'LDm2', what: 'B walks with A\'s follow', catches: 'LD2',
    mutate: (t) => swap(t, 'follow: [...state.control]', 'follow: [...state.follow]') },
  { id: 'W1', what: 'the step knobs are drawn in the result instead of the rail', catches: 'L1 every',
    mutate: (t) => swap(t, '      renderStep(body);', '      renderStep(main);') },
  { id: 'W2', what: 'Follow is drawn after the routes again', catches: 'L4 the follow',
    mutate: (t) => swap(swap(t, '      renderFollow(body);', ''),
      '      renderStep(body);', '      renderStep(body); renderFollow(body);') },
  { id: 'W3', what: 'the picked mark is always on', catches: 'L6 a follow',
    mutate: (t) => swap(t, "      const route = el(doc, 'div', 'wk-route' + (picked ? ' is-on' : ''));",
      "      const route = el(doc, 'div', 'wk-route is-on');") },
  { id: 'W4', what: 'node_limit is no longer sent', catches: 'L7 the full',
    mutate: (t) => swap(t, '      if (Number.isFinite(n)) out[wire] = n;', "      if (Number.isFinite(n) && wire !== 'node_limit') out[wire] = n;") },
  { id: 'W16', what: 'fanout_limit drawn but not sent', catches: 'L18 ',
    mutate: (t) => swap(t, '      if (Number.isFinite(n)) out[wire] = n;', "      if (Number.isFinite(n) && wire !== 'fanout_limit') out[wire] = n;") },
  { id: 'W5', what: 'the title reads the live form', catches: 'L9 the title',
    mutate: (t) => swap(t, "      head.append(el(doc, 'span', 'wk-title', state.at === 0 ? askedTitle(askedOf) : shown.title));",
      "      head.append(el(doc, 'span', 'wk-title', state.at === 0 ? askedTitle(spec()) : shown.title));") },
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
  { id: 'W11', what: 'every drawn box is sent, ticked or not', catches: 'L13 ',
    mutate: (t) => swap(t, '    if (state.follow.size) out.follow = [...state.follow];',
      '    out.follow = followOptions();') },
  { id: 'W12', what: 'a route press replaces the ticks, as before 10-06', catches: 'L14 ',
    mutate: (t) => swap(t, '      state.follow = new Set([...state.follow, ...followFromRoute(allPredicates(), asked.follow)]);',
      '      state.follow = new Set(followFromRoute(allPredicates(), asked.follow));') },
  { id: 'W13', what: 'a route press no longer ticks anything', catches: 'L3 open',
    mutate: (t) => swap(t, '      state.follow = new Set([...state.follow, ...followFromRoute(allPredicates(), asked.follow)]);',
      '') },
  { id: 'W14', what: 'node_limit left to the server again', catches: 'L8 a type',
    mutate: (t) => swap(t, 'nodeLimit: String(NODE_LIMIT),', "nodeLimit: '',") },
  { id: 'W15', what: 'the counts line says no time', catches: 'L17 ',
    mutate: (t) => swap(t, ': `Nodes ${r.nodes.length} · Edges ${r.edges.length}`) + took));', ': `Nodes ${r.nodes.length} · Edges ${r.edges.length}`)));') },
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
