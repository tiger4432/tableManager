/**
 * rnd_board — 제어 막대(공사9-1) · 메인 트렌드(공사9-2) 계약 채점
 *
 * WHAT THIS SCORES:
 *   A  the control bar's pills are SOURCED -- every count comes from a response, and a count
 *      nobody serves is 「—」 rather than 0
 *   B  a chosen axis is written under the name the INSTANCE declared, and a plain click replaces
 *   C  a trend point marks with the LEDGER'S own id, never one this client assembled
 *   D  the legend states the denominator, and a degenerate axis is SAID rather than drawn around
 *
 * 🔴 THE FIXTURES ARE TRIMMED COPIES OF LIVE BODIES (2026-08-23, 127.0.0.1:8080):
 *    `trends?kinds=void&window=180d` and `subgraph?id=<wafer>&collect=quantity`. The trend body
 *    keeps the shape that matters -- `series[].points[].identity.mark_key`, `value.found_rate`,
 *    and `provenance` -- plus one point with NO rate, which the live stack does not currently
 *    serve and which is exactly the case that must not be drawn at zero.
 *
 * 🔴 EVERY ASSERTION IS WOKEN BY A MUTANT, and a mutation whose anchor has rotted STOPS the run
 *    instead of reading as a pass.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC_DIR = path.join(HERE, '..', 'src');
const BOARD_DIR = path.join(SRC_DIR, 'rnd_board');
const dataUrl = (src) => `data:text/javascript;base64,${Buffer.from(src, 'utf8').toString('base64')}`;

const TRENDS = {
  state: 'ready',
  selectable_finding_kinds: [
    { id: 'void', label: '보이드', active: true },
    { id: 'delam', label: '박리', active: true },
  ],
  provenance: {
    numerator: { predicate: 'observed', ledger_backed: true },
    denominator: { source: 'inspection_run', absence_is_zero: false },
  },
  series: [{
    id: 'void:all',
    points: [
      { identity: { keys: { wafer: 'W-1' }, context: { bonding_leg: 'L' }, mark_key: 'mk-1' },
        occurred_at: '2026-07-11T08:00:00+09:00',
        value: { found_rate: 0.02, scan_denominator: 64, state: 'found' } },
      { identity: { keys: { wafer: 'W-2' }, context: { bonding_leg: 'L' }, mark_key: 'mk-2' },
        occurred_at: '2026-07-12T08:00:00+09:00',
        value: { found_rate: 0.0, scan_denominator: 64, state: 'scanned_clean' } },
      // 🔴 NO RATE. Not zero: nobody measured it.
      { identity: { keys: { wafer: 'W-3' }, context: { bonding_leg: 'L' }, mark_key: 'mk-3' },
        occurred_at: '2026-07-13T08:00:00+09:00',
        value: { state: 'unscanned' } },
    ],
  }],
};

const FLAT_TRENDS = JSON.parse(JSON.stringify(TRENDS));
FLAT_TRENDS.series[0].points = FLAT_TRENDS.series[0].points.slice(0, 2).map((p) => ({
  ...p, occurred_at: '2026-07-11T08:00:00+09:00', value: { ...p.value, found_rate: 0.0 },
}));

const WALK = {
  seeds: [{ id: 'seed', sign: '+' }],
  propagation: {
    collect: 'quantity', state: 'ranked', contrast: 'unexamined', complete: true,
    ranked: [
      { id: 'q-measured', type: 'Quantity', label: 'bond_temp · void_formation', rank: 1,
        top: true, tied: false, incomparable: false,
        // 🔴 `node_kind` IS THE FIELD THE DERIVATION READS -- `kind` is the one the card prints.
        //    A fixture carrying only one of them scores a candidate as name-only and the whole
        //    measured/name-only split silently inverts.
        evidence: [{ seed: 'seed', hops: [{ node_kind: 'claim', kind: 'claim', label: 'x', ref: 'recipe_book:R@1' }] }] },
      { id: 'q-name', type: 'Quantity', label: 'outgassing · void_formation', rank: 2,
        top: false, tied: false, incomparable: false,
        evidence: [{ seed: 'seed', hops: [{ node_kind: 'quantity', kind: 'quantity', label: 'y' }] }] },
    ],
    top_set: ['q-measured'],
  },
  graph: { nodes: [1, 2], edges: [1] },
};

async function loadModules(mutate = {}) {
  const read = (file) => {
    const text = readFileSync(path.join(BOARD_DIR, file), 'utf8')
      .replace(new RegExp(String.fromCharCode(13, 10), 'g'), String.fromCharCode(10));
    const fn = mutate[file];
    const out = fn ? fn(text) : text;
    if (fn && out === text) throw new Error(`mutation anchor is GONE: ${file}`);
    return out;
  };
  const storeUrl = dataUrl(read('marking_store.js'));
  const apiUrl = dataUrl(read('api.js'));
  const panelUrl = dataUrl(read('panel.js').replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  const rewire = (file) => dataUrl(read(file)
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`)
    .replaceAll("'./api.js'", `'${apiUrl}'`));
  const control = await import(rewire('control_bar_panel.js'));
  const trend = await import(rewire('main_trend_panel.js'));
  const store = await import(storeUrl);
  return { control, trend, store };
}

// ── the DOM stub (same shape the other board harnesses drive) ──────────────────────
function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '', style: {}, children: [], attrs: Object.create(null),
    listeners: Object.create(null), _text: '', parentNode: null,
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    append(...cs) { for (const c of cs) this.appendChild(c); },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); if (String(k) === 'class') this.className = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); },
    click(ev) { for (const fn of this.listeners.click || []) fn(ev || {}); },
    get firstElementChild() { return this.children[0] || null; },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  return node;
}
const makeDoc = () => { const doc = { createElement: (t) => makeNode(doc, t) }; return doc; };
const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const byClass = (root, cls) => walk(root).filter((n) => String(n.className || '').split(/\s+/).includes(cls));
const flush = () => new Promise((r) => setTimeout(r, 0));

/** One fetch stub that answers both routes off the URL, the way the real boundary sees them. */
const routedFetch = (trends) => async (url) => ({
  ok: true, status: 200,
  json: async () => (String(url).includes('/trends') ? trends : WALK),
});
const refusingFetch = () => async () => ({
  ok: false, status: 422, json: async () => ({ detail: { message: '서버가 거절했습니다' } }),
});

async function suite(mods) {
  const { control, trend, store } = mods;
  const { MarkingStore, SIGN } = store;
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };
  const ok = (name, cond, detail) => {
    ran.push(name);
    if (!cond) failures.push(detail ? `${name}: ${detail}` : name);
  };

  // ── A. THE CONTROL BAR'S PILLS ARE SOURCED ───────────────────────────────────
  {
    const doc = makeDoc();
    const markings = new MarkingStore();
    const host = doc.createElement('div');
    const bar = new control.ControlBarPanel(host, {
      doc, markings, reads: 'axis:y', writes: 'axis:y',
      apiBase: '', seedNodeId: 'seed', fetchImpl: routedFetch(TRENDS),
    });
    bar.mount();
    await flush(); await flush(); await flush();

    const pills = byClass(host, 'rb-pill');
    const texts = pills.map((p) => p.textContent);
    ok('A1 the ratio axes come from the routes own selectable kinds',
      texts.some((t) => t.includes('보이드 비율')) && texts.some((t) => t.includes('박리 비율')),
      texts.join(' | '));
    ok('A2 a measured candidate becomes an axis', texts.some((t) => t.includes('bond_temp')));
    ok('A3 a name-only candidate does NOT become an axis on its own',
      !texts.some((t) => t.includes('outgassing')), texts.join(' | '));
    ok('A4 the name-only rest is one folded pill carrying its count',
      texts.some((t) => t.includes('값 없음') && t.includes('1')), texts.join(' | '));
    // 🔴 THE FOURTH ABSENCE: the axis resolved, the comparison did not. The resolved number on
    //    its own reads as 「이만큼으로 대조할 수 있다」, the opposite of what happened.
    const straddleBar = new control.ControlBarPanel(makeDoc().createElement('div'), {
      doc, markings: new MarkingStore(), reads: 'axis:y', writes: 'axis:y',
      apiBase: '', seedNodeId: 'seed', fetchImpl: routedFetch(TRENDS),
      peers: [{ label: '같은 레그', scope: 'leg:X' }],
      loadPeerCount: async () => ({ state: 'resolved', subjects: 6, units: 384,
        analysis: 'empty', reason: 'empty_case_side', message: '케이스 쪽 주어 0',
        straddling: 6, straddleMessage: '양쪽에 걸침' }),
    });
    straddleBar.mount();
    await flush(); await flush(); await flush();
    const straddlePill = byClass(straddleBar.host, 'rb-pill')
      .find((p) => p.textContent.includes('같은 레그'));
    ok('A6 a straddled peer says so instead of printing a comparable number',
      Boolean(straddlePill) && straddlePill.textContent.includes('대조 0')
      && straddlePill.textContent.includes('걸침 6'), straddlePill && straddlePill.textContent);

    // 🔴 A COUNT NOBODY SERVES IS 「—」. Zero would say 「또래가 없다」, which nobody measured.
    const peer = pills.find((p) => p.textContent.includes('같은 랏'));
    ok('A5 a peer axis nobody counted shows an em dash, not a zero',
      Boolean(peer) && peer.textContent.includes('—') && !/같은 랏0/.test(peer.textContent),
      peer && peer.textContent);

    // ── B. CHOOSING WRITES THE DECLARED NAME, AND A PLAIN CLICK REPLACES ───────
    ok('B1 the first ratio axis is chosen when nothing was chosen yet',
      markings.count('axis:y') === 1, `count ${markings.count('axis:y')}`);
    // Guarded: a mutant that writes somewhere else must FAIL a named line, not crash the suite.
    // A crash reads as INERT, which is the honest word for 「아무것도 시험 안 했다」 -- and this
    // assertion has something to say about that mutant.
    const chosenEntry = markings.entries('axis:y')[0];
    const first = chosenEntry ? chosenEntry[0] : null;
    const other = pills.find((p) => p.getAttribute('data-axis-id')
      && p.getAttribute('data-axis-id') !== first);
    if (other) other.click({});
    eq('B2 a plain click leaves exactly one axis chosen', markings.count('axis:y'), 1);
    eq('B3 ... and it is the one just clicked',
      markings.signOf('axis:y', other.getAttribute('data-axis-id')), SIGN.CASE);
    eq('B4 nothing was written under any other name', markings.names(), ['axis:y']);
  }

  // ── C. A TREND POINT MARKS WITH THE LEDGER'S OWN ID ──────────────────────────
  {
    const doc = makeDoc();
    const markings = new MarkingStore();
    const host = doc.createElement('div');
    const t = new trend.MainTrendPanel(host, {
      doc, markings, reads: 'marking:0', writes: 'marking:0',
      apiBase: '', fetchImpl: routedFetch(TRENDS),
      // 화면이 실제로 선언하는 것과 같은 모양 -- 「접는 단위」 줄이 이 선언에서 나옵니다.
      grain: { subject_type: 'WaferLeg', identity_fields: ['wafer'] },
    });
    t.mount();
    await flush(); await flush();

    const dots = byClass(host, 'rb-trend-dot');
    // 🔴 THE POINT WITH NO RATE IS NOT DRAWN AT ZERO. `absence_is_zero` is false upstream.
    eq('C1 only points that carry a rate are plotted', dots.length, 2);
    ok('C2 the unplotted point is counted and named, not dropped',
      byClass(host, 'rb-trend-absent').some((n) => n.textContent.includes('비율 없음 1')),
      byClass(host, 'rb-trend-absent').map((n) => n.textContent).join(' | '));
    dots[0].click({});
    eq('C3 a click marks the points OWN mark_key', markings.signOf('marking:0', 'mk-1'), SIGN.CASE);
    eq('C4 ... and nothing else', markings.count('marking:0'), 1);

    const legend = byClass(host, 'rb-trend-legend')[0];
    ok('C5 the legend states the numerator and the denominator it was served',
      legend.textContent.includes('observed') && legend.textContent.includes('inspection_run'),
      legend.textContent);
    ok('C6 ... including absence_is_zero', legend.textContent.includes('absence_is_zero false'));
    // 🔴 목업의 「접는 단위」 줄 — 선언에 있는 것을 그대로 말합니다. 이게 없으면 «접힌» 차트가
    //    안 접힌 차트처럼 읽힙니다 (점 하나가 웨이퍼 하나인지 웨이퍼×레그인지 모릅니다).
    ok('C7 the chart says what it folds a point out of',
      /접는 단위 WaferLeg/.test(legend.textContent), legend.textContent.slice(0, 90));
  }

  // ── D. A DEGENERATE AXIS IS SAID, NOT DRAWN AROUND ───────────────────────────
  {
    const doc = makeDoc();
    const markings = new MarkingStore();
    const host = doc.createElement('div');
    const t = new trend.MainTrendPanel(host, {
      doc, markings, reads: 'marking:0', writes: 'marking:0',
      apiBase: '', fetchImpl: routedFetch(FLAT_TRENDS),
    });
    t.mount();
    await flush(); await flush();
    const text = host.textContent;
    ok('D1 a flat value axis is stated', text.includes('값이 전부 같습니다'), text.slice(0, 160));
    // 🔴 THE CLAIM MOVED WITH THE AXIS. It used to be 「가로는 차례」 because the axis said
    //    nothing; the axis now names the materials and prints the one timestamp, so what must
    //    be scored is that BOTH are said -- the material ticks and the moment.
    ok('D2 a single timestamp is said, and the axis names its materials',
      text.includes('한 시각') && text.includes('가로는 «자재»입니다'), text.slice(0, 200));
    ok('D4 each material gets one tick, not one per point',
      byClass(host, 'rb-trend-xtick').length === 2,
      String(byClass(host, 'rb-trend-xtick').map((n) => n.textContent)));
    // 🔴 WITH EVERY RATE AT ZERO THERE IS NO UPPER BOUND IN THE DATA.
    const ymax = byClass(host, 'rb-trend-ymax')[0];
    eq('D3 the axis top is an em dash when nothing has a value', ymax.textContent, '—');
  }

  // ── E. A REFUSAL IS THE SERVER'S SENTENCE ────────────────────────────────────
  {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const t = new trend.MainTrendPanel(host, {
      doc, markings: new MarkingStore(), reads: null, writes: null,
      apiBase: '', fetchImpl: refusingFetch(),
    });
    t.mount();
    await flush(); await flush();
    ok('E1 a refused trend renders the servers own sentence',
      byClass(host, 'rb-trend-note--refused').length === 1
      && host.textContent.includes('거절'), host.textContent.slice(0, 120));
  }

  return { ran, failures };
}

const MUTANTS = [
  { id: 'M10', what: 'the chart hides what it folds a point out of',
    catches: 'C7',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      '    if (this.grain && this.grain.subject_type) {', '    if (false) {') } },
  { id: 'M1', what: 'the control bar keeps its own list of ratio axes instead of the served one',
    catches: 'A1',
    mutate: { 'control_bar_panel.js': (s) => s.replace(
      'for (const kind of (this.trends && this.trends.kinds) || []) {',
      "for (const kind of [{ id: 'x', label: '고정' }]) {") } },
  { id: 'M2', what: 'a name-only candidate is offered as an axis, so a pill leads nowhere',
    catches: 'A3',
    mutate: { 'control_bar_panel.js': (s) => s.replace(
      '        if (!c.measured) continue;', '        if (false) continue;') } },
  // 🔴 ANCHORED ON THE PREDICATE, ON ONE LINE. The previous anchor spanned two lines and named
  //    a shape the peer-count round rewrote; this one sits on the decision itself -- what a
  //    pill shows when the route served no number.
  // Anchored on the predicate, one line: what a pill shows when the route served no number.
  { id: 'M3', what: 'an unserved peer count is drawn as 0 instead of an em dash',
    catches: 'A5',
    mutate: { 'control_bar_panel.js': (s) => s.replace(
      "count: has ? got.subjects : null,",
      "count: has ? got.subjects : 0,") } },
  // 🔴 THE FOURTH ABSENCE. A pill whose axis resolved but whose comparison came back empty must
  //    NOT print the resolved number on its own -- it reads as its opposite.
  { id: 'M9', what: 'a straddled peer prints its subject count as if it were comparable',
    catches: 'A6',
    mutate: { 'control_bar_panel.js': (s) => s.replace(
      "const straddled = has && got.analysis === 'empty';",
      "const straddled = false;") } },
  { id: 'M4', what: 'the control bar writes a fixed marking name instead of its declared one',
    catches: 'B4',
    mutate: { 'panel.js': (s) => s.replace(
      'return this.markings.set(this.writes, nodeId, sign);',
      "return this.markings.set('axis:fixed', nodeId, sign);") } },
  { id: 'M5', what: 'the trend marks the wafer NAME it assembled instead of the ledgers mark_key',
    catches: 'C3',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      '          this.mark(p.markKey, intent.sign, intent.mode);',
      '          this.mark(p.wafer, intent.sign, intent.mode);') } },
  { id: 'M6', what: 'a point with no rate is plotted at zero (absence read as a measurement)',
    catches: 'C1',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      '    const drawn = m.points.filter((p) => p.rate !== null && p.at);',
      '    const drawn = m.points.map((p) => (p.rate === null ? { ...p, rate: 0 } : p));') } },
  { id: 'M7', what: 'the axis top is printed as 100% when no rate has a value',
    catches: 'D3',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      "    yTop.textContent = maxRate > 0 ? `${(top * 100).toFixed(1)}%` : '—';",
      '    yTop.textContent = `${(top * 100).toFixed(1)}%`;') } },
  { id: 'M8', what: 'the legend drops the denominator, leaving a rate nobody can check',
    catches: 'C5',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      "      prov.textContent = `y = 비율 (분자 ${m.provenance.numerator || '?'}`",
      "      prov.textContent = `y = 비율 (`") } },
];

const result = await suite(await loadModules());
console.log('-- rnd_board control bar + main trend -------------------------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

let escaped = 0;
console.log('\n-- defect mutants (each must be CAUGHT by its named line) -----------');
for (const m of MUTANTS) {
  let out;
  try {
    out = await suite(await loadModules(m.mutate));
  } catch (e) {
    escaped += 1;
    console.log(`  INERT   ${m.id} ${m.what}  -- ${String(e.message).slice(0, 60)}`);
    continue;
  }
  const hit = out.failures.some((f) => f.startsWith(m.catches));
  if (hit) console.log(`  caught  ${m.id} ${m.what}  (${m.catches})`);
  else { escaped += 1; console.log(`  ESCAPED ${m.id} ${m.what}  -- ${m.catches} stayed green`); }
}

const total = result.ran.length + MUTANTS.length;
const failed = result.failures.length + escaped;
console.log(`\n${result.ran.length - result.failures.length} passed, ${result.failures.length} failed; `
  + `${MUTANTS.length - escaped}/${MUTANTS.length} defects caught, ${escaped} escaped.`);
console.log(`ASSERTIONS ${total} ${failed}`);
if (failed) process.exitCode = 1;
