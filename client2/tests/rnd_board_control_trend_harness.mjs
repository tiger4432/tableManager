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
        evidence: [{ seed: 'seed', hops: [{ node_kind: 'value', kind: 'value', label: 'x', ref: 'recipe_book:R@1' }] }] },
      { id: 'q-name', type: 'Quantity', label: 'outgassing · void_formation', rank: 2,
        top: false, tied: false, incomparable: false,
        evidence: [{ seed: 'seed', hops: [{ node_kind: 'quantity', kind: 'quantity', label: 'y' }] }] },
    ],
    top_set: ['q-measured'],
  },
  graph: { nodes: [1, 2], edges: [1] },
};

/**
 * 🔴 선언 픽스처 -- 라이브 `/api/ledger/declaration` 의 다듬은 사본 (2026-08-29, :8080).
 *    수식어는 «술어 밑»에 삽니다. 여기서 재는 것은 「목록이 선언에서 오나」이고, 그래서
 *    이 픽스처에는 원장 데이터가 «한 줄도» 없습니다 -- 그게 「마킹과 무관」의 뜻입니다.
 */
const DECLARATION = {
  ok: true,
  entities: [],
  predicates: [
    { name: 'observed@1', subjects: ['die@1'],
      object: { kind: 'entity_ref', types: ['defect@1'],
        qualifiers: { required: [], optional: ['radius_x', 'unit', 'gate'] } } },
    { name: 'measures@1', subjects: ['wafer@1'],
      object: { kind: 'entity_ref', types: ['quantity@1'],
        qualifiers: { required: [], optional: ['value', 'role'] } } },
    { name: 'inspected@1', subjects: ['wafer@1'],
      object: { kind: 'entity_ref', types: ['die@1'],
        qualifiers: { required: [], optional: [] } } },
  ],
};

/**
 * 🔴 걷기 하나, 웨이퍼 하나, `radius_x` 셋 -- 그중 «하나가 문자»입니다.
 *    이것이 「하나라도 수치면 수치」의 «판별 입력»입니다: 전수를 요구하는 규칙과 하나로
 *    족한 규칙이 이 입력에서 «다른 답»을 냅니다 (전수면 축이 죽고, 하나면 3 이 나옵니다).
 *    두 규칙이 같은 답을 내는 표본으로는 어느 쪽이 도는지 알 수 없습니다.
 */
const TREND_WALK = {
  ok: true,
  complete: true,
  truncated: [],
  nodes: [
    { id: 'w1', type: 'wafer', keys: { wafer: 'W-1' } },
    { id: 'd1', type: 'die', keys: { mat_id: 'W-1' } },
    { id: 'd2', type: 'die', keys: { mat_id: 'W-1' } },
    { id: 'f1', type: 'defect', keys: {} },
    { id: 'f2', type: 'defect', keys: {} },
    { id: 'f3', type: 'defect', keys: {} },
  ],
  edges: [
    { source: 'w1', target: 'd1', predicate: 'inspected', occurred_at: '2026-07-11T08:00:00+09:00' },
    { source: 'w1', target: 'd2', predicate: 'inspected', occurred_at: '2026-07-11T08:00:00+09:00' },
    { source: 'd1', target: 'f1', predicate: 'observed', occurred_at: '2026-07-11T08:00:00+09:00',
      qualifiers: { radius_x: 2, unit: 'um' } },
    { source: 'd1', target: 'f2', predicate: 'observed', occurred_at: '2026-07-11T08:00:00+09:00',
      qualifiers: { radius_x: 4, unit: 'um' } },
    { source: 'd2', target: 'f3', predicate: 'observed', occurred_at: '2026-07-11T08:00:00+09:00',
      qualifiers: { radius_x: 'n/a', unit: 'um' } },
  ],
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
  // 집계 규칙은 «경계»에 삽니다 (`trendFromWalk`) -- 화면이 아니라 여기서 채점합니다.
  const api = await import(apiUrl);
  return { control, trend, store, api };
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
  const { control, trend, store, api } = mods;
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
      // 🔴 라운드 ①-a: 목록은 «선언»에서 오고, 「수치인가」는 이 마킹에서 옵니다.
      loadDeclaration: async () => DECLARATION,
      numericReads: 'marking:1',
    });
    bar.mount();
    await flush(); await flush(); await flush();

    const pills = byClass(host, 'rb-pill');
    const texts = pills.map((p) => p.textContent);
    // 🔴 A1 은 «다른 것을 잽니다» (라운드 ①-a, 2026-08-29). 옛 A1 은 「비율 축이 죽은
    //    라우트의 selectable_finding_kinds 에서 온다」였고, 그 라우트를 좌석이 더는 안 부릅니다.
    //    같은 자리에 남는 질문은 여전히 「목록을 부품이 «지어내나 받나»」이고, 이제 그 출처가
    //    선언입니다 -- 그래서 이름을 갈아끼우지 않고 «재는 대상»을 옮겨 적습니다.
    ok('A1 the Y pills are the DECLARATIONs qualifiers, not a list this part keeps',
      ['gate', 'radius_x', 'role', 'unit', 'value']
        .every((name) => texts.some((t) => t.startsWith(name))),
      texts.join(' | '));
    // 🔴 게이트 ② -- 「아직 안 골라서 못 잰다」는 «자기 문장»입니다. 「값 없음」이나 빈 목록으로
    //    두면 「없어서」와 구별이 사라지고, 그게 이 보드가 존재하는 이유입니다.
    const note = byClass(host, 'rb-control-note')[0];
    ok('A8 with an empty marking the qualifiers still stand and the reason is SAID',
      Boolean(note) && note.textContent.includes('재려면 마킹이 필요합니다')
      && texts.some((t) => t.startsWith('radius_x')), note && note.textContent);
    // 🔴 집계는 «데이터가 필요 없습니다». 마킹이 비어도 일곱이 전부 서 있어야 합니다.
    ok('A9 every aggregation is offered with no data at all',
      ['median', 'mean', 'sum', 'min', 'max', 'count', 'distinct']
        .every((agg) => texts.includes(agg)),
      texts.join(' | '));

    // 🔴 은퇴 2026-08-28 — 「없어진 세상」을 재고 있었습니다. 지우지 않고 «행선지»를 답니다.
    //    무엇이 사라졌나: 후보 «순위»가 `collect` 축과 함께 꺼졌습니다
    //                    (실측: /subgraph -> propagation.state="not_requested" · ranked=0).
    //                    후보가 0 이므로 `candidate.measured` 는 적용 대상이 없습니다.
    //    왜 초록이었나:   이 파일의 픽스처가 `node_kind: 'value'|'quantity'` 를 «손으로» 먹입니다.
    //                    서버 실측은 `{ entity: 400 }` 입니다 — 그 종류는 더 이상 안 옵니다.
    //                    픽스처를 «지금 값»으로 바꾸면 정확히 이 단언들이 같은 이름으로 깨집니다.
    //    어디로 가나:     「후보 패널을 walk 부품으로 다시 짓는 라운드」가 데려갑니다.
    //                    그때 `measured` 의 답은 «노드 종류»가 아니라 «술어»입니다 —
    //                    자취가 `observed` 엣지를 지났나. 그 엣지는 지금도 walk 응답에 옵니다.
    //    🟢 조립식 정의(「부품이 «자기가 선언한» 이름에 쓴다」)는 «여기서만» 재던 것이 아닙니다 —
    //       rnd_board_composition_harness A3 · rnd_board_harness D6 · walk_box D 절이 살아 있습니다.
    // RETIRED: ok('A2 a measured candidate becomes an axis', texts.some((t) => t.includes('bond_temp')));
    ok('A3 a name-only candidate does NOT become an axis on its own',
      !texts.some((t) => t.includes('outgassing')), texts.join(' | '));
    // RETIRED: ok('A4 the name-only rest is one folded pill carrying its count',
    // RETIRED: texts.some((t) => t.includes('값 없음') && t.includes('1')), texts.join(' | '));
    // 🔴 THE FOURTH ABSENCE: the axis resolved, the comparison did not. The resolved number on
    //    its own reads as 「이만큼으로 대조할 수 있다」, the opposite of what happened.
    const straddleBar = new control.ControlBarPanel(makeDoc().createElement('div'), {
      doc, markings: new MarkingStore(), reads: 'axis:y', writes: 'axis:y',
      apiBase: '', seedNodeId: 'seed', fetchImpl: routedFetch(TRENDS),
      peers: [{ label: '같은 레그', scope: 'leg:X' }],
      loadPeerCount: async () => ({ state: 'resolved', subjects: 6, units: 384,
        analysis: 'empty', reason: 'empty_case_side', message: '케이스 쪽 주어 0',
        straddling: 6, straddleMessage: '양쪽에 걸침',
        relation: 'bonding_log', column: 'leg' }),
    });
    straddleBar.mount();
    await flush(); await flush(); await flush();
    const straddlePill = byClass(straddleBar.host, 'rb-pill')
      .find((p) => p.textContent.includes('같은 레그'));
    // 🔴 수를 쓰면 «어디서 왔는지»도 씁니다. 맵은 이미 그러고 있었고 알약만 안 그랬습니다.
    ok('A7 a peer count names the relation it was counted from',
      Boolean(straddlePill) && /bonding_log\.leg 기준/.test(straddlePill.getAttribute('title') || ''),
      String(straddlePill && straddlePill.getAttribute('title')));
    ok('A6 a straddled peer says so instead of printing a comparable number',
      Boolean(straddlePill) && straddlePill.textContent.includes('대조 0')
      && straddlePill.textContent.includes('걸침 6'), straddlePill && straddlePill.textContent);

    // 🔴 A COUNT NOBODY SERVES IS 「—」. Zero would say 「또래가 없다」, which nobody measured.
    const peer = pills.find((p) => p.textContent.includes('같은 랏'));
    ok('A5 a peer axis nobody counted shows an em dash, not a zero',
      Boolean(peer) && peer.textContent.includes('—') && !/같은 랏0/.test(peer.textContent),
      peer && peer.textContent);

    // ── B. CHOOSING WRITES THE DECLARED NAME, AND THE AXIS IS A PAIR ───────────
    // 🔴 «자동 선택이 없습니다» (라운드 ①-a). 전에는 첫 비율 축을 대신 골라 줬는데, 집계 축에는
    //    대신 골라 줄 「첫째」가 없습니다 -- 대신 고르면 아무도 안 고른 축을 차트가 그립니다.
    eq('B1 nothing is chosen until somebody picks', markings.count('axis:y'), 0);
    const pick = (id) => {
      const el = pills.find((p) => p.getAttribute('data-axis-id') === id);
      if (el) el.click({});
      return Boolean(el);
    };
    // 집계만 고른 상태는 «아직 축이 아닙니다» -- 무엇을 잴지가 없으면 잴 수 없습니다.
    ok('B5 an aggregation alone is not yet an axis', pick('axis:aggregation:median')
      && markings.count('axis:y') === 0, `count ${markings.count('axis:y')}`);
    ok('B2 picking a qualifier completes the PAIR, and writes exactly one',
      pick('axis:qualifier:radius_x') && markings.count('axis:y') === 1,
      `count ${markings.count('axis:y')}`);
    eq('B3 ... and the pair is written as one id, aggregation and qualifier together',
      markings.signOf('axis:y', 'axis:agg:median:radius_x'), SIGN.CASE);
    ok('B6 changing the aggregation keeps the qualifier and still writes one',
      pick('axis:aggregation:max') && markings.count('axis:y') === 1
      && markings.signOf('axis:y', 'axis:agg:max:radius_x') === SIGN.CASE,
      String(markings.entries('axis:y')));
    eq('B4 nothing was written under any other name', markings.names(), ['axis:y']);
  }

  // ── C. A TREND POINT MARKS WITH THE LEDGER'S OWN ID ──────────────────────────
  {
    const doc = makeDoc();
    const markings = new MarkingStore();
    const host = doc.createElement('div');
    const t = new trend.MainTrendPanel(host, {
      doc, markings, reads: 'marking:0', writes: 'marking:0',
      // 🔴 `collect` 을 «적습니다» (총괄 검수 14:3x). 전에는 부품의 기본값이 이걸 대신
      //    골라 줘서 픽스처가 «무엇을 묻는지 안 말하고도» 돌았습니다 -- 그게 바로 그 기본값이
      //    화면에서 한 일입니다. 시험도 선언을 해야 «선언대로 도는지»를 잰다고 말할 수 있습니다.
      collect: 'trend_y',
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
    // 🔴 소유자 요청: 점 하나가 «몇 칩 중 몇 칩»인지 호버로. 비율만 있으면 「맵은 50%인데
    //    트렌드는 0%」 같은 어긋남을 못 봅니다 -- 오늘 실제로 못 봤습니다.
    const dot0 = byClass(host, 'rb-trend-dot')[0];
    ok('C8 a trend point annotates the counts its ratio was made of',
      Boolean(dot0) && /검사한 칩 \d+/.test(dot0.getAttribute('title') || '')
      && /보이드 난 칩/.test(dot0.getAttribute('title') || ''),
      String(dot0 && dot0.getAttribute('title')));
    // 🔴 128 과 64 는 «모순이 아니라 알갱이 둘»입니다. 화면이 그 낱말을 말해야 가릴 수 있습니다.
    ok('C9 a point says which grain its counts were taken at',
      /WaferLeg\(wafer\)/.test(dot0.getAttribute('title') || ''),
      String(dot0 && dot0.getAttribute('title')));
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
      collect: 'trend_y',
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
      collect: 'trend_y',
      apiBase: '', fetchImpl: refusingFetch(),
    });
    t.mount();
    await flush(); await flush();
    ok('E1 a refused trend renders the servers own sentence',
      byClass(host, 'rb-trend-note--refused').length === 1
      && host.textContent.includes('거절'), host.textContent.slice(0, 120));

    // 🔴 「선언이 없다」는 «거절이 아닙니다» -- 서버는 아무 말도 안 했습니다.
    //    기본값이 살아 있을 때는 이 부품이 «물어보지도 않고» 죽은 라우트를 불렀고,
    //    그 404 를 「서버가 거절했다」고 그렸습니다 (총괄 라이브 실측 14:3x).
    const bare = makeDoc();
    const bareHost = bare.createElement('div');
    let asked = 0;
    const t2 = new trend.MainTrendPanel(bareHost, {
      doc: bare, markings: new MarkingStore(), reads: null, writes: null,
      apiBase: '', fetchImpl: async () => { asked += 1; return { ok: true, status: 200, json: async () => TRENDS }; },
    });
    t2.mount();
    await flush(); await flush();
    eq('E2 a seat that declared no collect is not walked for one', asked, 0);
    ok('E3 ... and the panel SAYS that, rather than drawing a refusal',
      bareHost.textContent.includes('선언하지 않았습니다')
      && byClass(bareHost, 'rb-trend-note--refused').length === 0,
      bareHost.textContent.slice(0, 140));
  }

  // ── F. THE AXIS IS A PAIR, AND CHOOSING ONE CHANGES THE CHART ────────────
  // 🔴 게이트 ① (총괄 지시 ①-a): 「알약이 집계를 고르고, 고르면 «차트가 바뀐다»」. 안 바뀌면
  //    그것이 2026-08-24 에 소유자가 지적한 「알약이 차트를 안 바꾼다」의 재발입니다.
  {
    const median = api.trendFromWalk(TREND_WALK, { aggregation: 'median', qualifier: 'radius_x' });
    eq('F1 a numeric aggregation skips the non-numeric value rather than dying on it',
      [median.points.length, median.points[0].value, median.valueKind],
      [1, 3, 'aggregate']);
    // 🔴 못박음 ②: 건너뛴 수를 «셉니다». 안 세면 「없어서 0」과 「건너뛰어서 0」이 같은 수입니다.
    eq('F2 ... and says how many it skipped', median.skipped, 1);
    const counted = api.trendFromWalk(TREND_WALK, { aggregation: 'count', qualifier: 'radius_x' });
    eq('F3 count takes every value, numeric or not, and skips nothing',
      [counted.points[0].value, counted.skipped], [3, 0]);
    // 🔴 「하나라도 수치면 수치」는 «세는 쪽»이 두 수를 다 들고 있어야 말할 수 있습니다.
    eq('F4 the numeric verdict is two counts, not a boolean',
      api.qualifierTypesFromWalk(TREND_WALK).radius_x, { seen: 3, numeric: 2 });
    // 모르는 집계는 «거절»입니다. 빈 점으로 그리면 「아무도 안 쟀다」가 되는데 그건 거짓입니다.
    const bogus = api.trendFromWalk(TREND_WALK, { aggregation: 'nope', qualifier: 'radius_x' });
    eq('F5 an aggregation nobody declared is refused, not drawn as absence',
      [bogus.ok, bogus.state], [false, 'refused']);

    const doc = makeDoc();
    const markings = new MarkingStore();
    const host = doc.createElement('div');
    const t = new trend.MainTrendPanel(host, {
      doc, markings, reads: 'marking:1', writes: 'marking:1', axisReads: 'axis:y',
      load: async ({ axis }) => api.trendFromWalk(TREND_WALK, axis),
    });
    t.mount();
    await flush(); await flush();
    // 🔴 축은 한 번에 하나입니다 -- 화면의 `mark()` 도 지우고 씁니다. `set` 으로 쌓으면
    //    이름 아래에 둘이 남아 읽는 쪽이 «첫 것»을 보고, 그러면 바뀌지 않은 것을 바뀌었다고 재게 됩니다.
    const chooseAxis = (id) => markings.replace('axis:y', [[id, SIGN.CASE]]);
    chooseAxis('axis:agg:median:radius_x');
    await flush(); await flush();
    const titleOf = () => String((byClass(host, 'rb-trend-dot')[0] || { getAttribute: () => '' })
      .getAttribute('title') || '');
    ok('F6 choosing the pair draws the AGGREGATE, in the axis own words',
      titleOf().includes('median(radius_x) 3'), titleOf());
    // Guarded: a mutant that kills the axis must FAIL a named line, not crash the suite --
    // a crash reads as INERT, which is the honest word for 「아무것도 시험 안 했다」.
    const aggLegend = byClass(host, 'rb-trend-legend')[0];
    ok('F7 the legend says the skipped count where the reader can see it',
      Boolean(aggLegend) && aggLegend.textContent.includes('건너뜀 1'),
      aggLegend ? aggLegend.textContent : host.textContent.slice(0, 140));
    chooseAxis('axis:agg:max:radius_x');
    await flush(); await flush();
    // 🔴 이것이 게이트 ① 그 자체입니다 -- 알약이 바뀌면 «그린 수»가 바뀝니다.
    ok('F8 picking a different aggregation changes what the chart draws',
      titleOf().includes('max(radius_x) 4'), titleOf());

    // 🔴 두 가지 0 을 가릅니다 (라이브 실측 2026-08-29 에서 이 라운드가 만든 결함).
    //    `unit` 은 걷기가 «실었고» max 가 전부 건너뛴 것인데, 화면은 「안 실었습니다」라고
    //    말했습니다. 개수를 세고도 그 수를 «안 읽으면» 못박음 ② 가 공허해집니다.
    chooseAxis('axis:agg:max:unit');
    await flush(); await flush();
    const text = host.textContent;
    ok('F9 an aggregation that skipped EVERY value says so, not that nothing was carried',
      text.includes('전부 건너뛰었습니다') && !text.includes('안 실었습니다'),
      text.slice(0, 220));
    // 그리고 «진짜로 안 실린» 수식어는 여전히 그 문장이어야 합니다 -- 둘이 같아지면 구분이 없습니다.
    chooseAxis('axis:agg:max:gate');
    await flush(); await flush();
    ok('F10 ... and a qualifier the walk really did not carry keeps its own sentence',
      host.textContent.includes('안 실었습니다'), host.textContent.slice(0, 220));
  }

  return { ran, failures };
}

const MUTANTS = [
  { id: 'M13', what: 'a point states counts without the grain they were taken at',
    catches: 'C9',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      "        + (grainWord ? ` · ${grainWord} 기준` : '')", "        + ''") } },
  // 🔴 앵커가 «옮겨졌습니다» (라운드 ①-a): 제목이 축마다 다른 문장을 쓰게 되면서 이 줄이
  //    삼항의 «비율 쪽 가지»가 됐습니다. 재는 것은 그대로입니다 -- 점이 만들어진 두 수.
  { id: 'M12', what: 'a trend point shows only its ratio, hiding the two counts it was made of',
    catches: 'C8',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      "        : ` · 검사한 칩 ${seen} · 보이드 난 칩 ${hit}`", "        : ''") } },
  { id: 'M11', what: 'a peer count is shown without saying which relation it came from',
    catches: 'A7',
    mutate: { 'control_bar_panel.js': (s) => s.replace(
      "    if (got.relation) parts.push(`${got.relation}${got.column ? `.${got.column}` : ''} 기준`);",
      '    if (false) parts.push();') } },
  { id: 'M10', what: 'the chart hides what it folds a point out of',
    catches: 'C7',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      '    if (this.grain && this.grain.subject_type) {', '    if (false) {') } },
  // 🔴 같은 결함, 새 자리 (라운드 ①-a): 목록을 부품이 «지어내는» 것. 출처가 죽은 라우트에서
  //    선언으로 옮겨졌으므로 앵커도 같이 옮깁니다 -- 이름을 갈아끼운 것이 아닙니다.
  { id: 'M1', what: 'the control bar keeps its own list of Y qualifiers instead of the declared one',
    catches: 'A1',
    mutate: { 'control_bar_panel.js': (s) => s.replace(
      'for (const q of this.qualifiers) {',
      "for (const q of [{ name: '고정', predicates: [] }]) {") } },
  // 🔴 게이트 ② 의 변이: 「아직 안 골라서」를 「없어서」로 접는 것. 오류가 안 나고 화면이
  //    «조용히 다른 사실»을 말하는 부류라, 문장이 있어야만 잡힙니다.
  { id: 'M14', what: 'an empty marking is reported as an absence, folding two absences into one',
    catches: 'A8',
    mutate: { 'control_bar_panel.js': (s) => s.replace(
      "      note.textContent = `재려면 마킹이 필요합니다 — ${this.numericReads} 이 비어 있습니다`",
      "      note.textContent = '값 없음'") } },
  // 🔴 집계는 «데이터가 필요 없습니다». 데이터를 기다리게 하면 빈 마킹에서 축이 통째로 사라집니다.
  { id: 'M15', what: 'the aggregations wait for data, so an empty marking has no axis at all',
    catches: 'A9',
    mutate: { 'control_bar_panel.js': (s) => s.replace(
      '    return AGGREGATIONS.map((agg) => this._pill({',
      '    return (this.qualifierTypes ? AGGREGATIONS : []).map((agg) => this._pill({') } },
  // 🔴 「하나라도 수치면 수치」의 반대: 전수를 요구하는 규칙. 문자 하나가 축을 죽입니다.
  { id: 'M16', what: 'one non-numeric value kills the whole axis (all-or-nothing instead of any)',
    catches: 'F1',
    mutate: { 'api.js': (s) => s.replace(
      '      const used = numericOnly ? nums : row.values;',
      '      const used = numericOnly && nums.length === row.values.length ? nums : [];') } },
  // 🔴 건너뛴 수를 «안 세면» 값은 맞고 화면만 덜 말합니다 -- 그게 이 변이의 요점입니다.
  { id: 'M17', what: 'the skipped values are dropped silently, so absent and skipped look alike',
    catches: 'F2',
    mutate: { 'api.js': (s) => s.replace(
      '      if (numericOnly) skipped += row.values.length - nums.length;',
      '      if (false) skipped += 0;') } },
  // 🔴 게이트 ① 의 변이: 알약이 «차트를 안 바꾸는» 것. 2026-08-24 에 소유자가 지적한 그 결함.
  { id: 'M18', what: 'the chosen aggregation never reaches the walk, so the pill does not move the chart',
    catches: 'F8',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      '      ? this.boundWalk({ start, axis: this.axis })',
      '      ? this.boundWalk({ start })') } },
  // 🔴 라이브에서 실제로 난 결함입니다 (2026-08-29). 건너뛰기를 «안 실렸다»로 읽는 것.
  { id: 'M19', what: 'a fully skipped aggregation is reported as a qualifier the walk never carried',
    catches: 'F9',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      '        ? (m.skipped > 0', '        ? (false') } },
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
  // 🔴 찍는 것은 «노드»입니다. 웨이퍼 «이름»을 찍으면 그 문자열은 어느 노드도 아니고,
  //    다음 walk 이 그것을 씨앗으로 못 씁니다 (오늘 아침 「지어낸 id」와 같은 부류).
  { id: 'M5', what: 'the trend marks the wafer NAME it assembled instead of the node the ledger gave',
    catches: 'C3',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      '          this.mark(markIdOf(p), intent.sign, intent.mode);',
      '          this.mark(p.wafer, intent.sign, intent.mode);') } },
  // 앵커 둘이 «옮겨졌습니다» (라운드 ①-a): 그리는 값이 `rate` 에서 `valueOf(p)` 로,
  // 축 꼭대기의 서식이 `formatValue` 로. 재는 결함은 하나도 안 바뀌었습니다.
  { id: 'M6', what: 'a point with no rate is plotted at zero (absence read as a measurement)',
    catches: 'C1',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      '    const drawn = m.points.filter((p) => valueOf(p) !== null && valueOf(p) !== undefined && p.at);',
      '    const drawn = m.points.map((p) => (valueOf(p) === null ? { ...p, rate: 0, value: 0 } : p));') } },
  { id: 'M7', what: 'the axis top is printed as 100% when no rate has a value',
    catches: 'D3',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      "    yTop.textContent = maxRate > 0 ? formatValue(m, top) : '—';",
      '    yTop.textContent = formatValue(m, top);') } },
  // 🔴 총괄이 라이브에서 잡은 결함입니다 (14:3x): 좌석이 이름을 똄 뒤에도 «부품의 기본값»이
  //    죽은 라우트를 되살립니다. 선언에서 사라졌는지를 재는 게이트는 그때 «초록»입니다.
  { id: 'M20', what: 'the trend invents a collect nobody declared, reviving the dead route',
    catches: 'E2',
    mutate: { 'main_trend_panel.js': (s) => s.replace(
      '    this.collect = options.collect || null;',
      "    this.collect = options.collect || 'trend_y';") } },
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
