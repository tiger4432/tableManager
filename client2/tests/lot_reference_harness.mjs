// Harness — 랏 참조뷰(화면 ②). SCENARIO_CONSOLE_BRIEF §0-quinquies R2.
// Run: node client2/tests/lot_reference_harness.mjs
//
// WHAT IT DEFENDS. Six claims, and every one of them is invisible to an exit code and to a
// glance at the page:
//
//   P1  🔴 미판정 IS NOT 불통과. The gate column has THREE states, and the third is not a
//       weaker second. 「실재✓·상류✓·기전 미판정」 is the machine's OUTPUT (a DOE candidate);
//       「실재✓·상류✓·기전 불통과」 is a rejected explanation. An absent key, a null, and a
//       word this client has never heard of ALL resolve to 미판정 — never to 불통과 and never
//       to 통과. Section B, and B7 scores the direction of the default.
//
//   P2  🔴 ABSENT ≠ MEASURED-EMPTY, IN FOUR PLACES. `anomalies` absent ("아무도 안 봤다") vs
//       `[]` ("보고 못 찾았다"); `coverage` absent vs reported; `investigations` absent vs
//       reported; `factors` absent vs `[]`. Painting the first as the second manufactures a
//       clean bill of health — the defect the ledger screens were already burned by. Section C.
//
//   P3  🔴 `basis` IS CONSUMED, NOT DERIVED. Two `resolved` hops can rest on different things:
//       one on a measurement, one on a declared convention. The view reuses the hop renderer
//       that reads the FIELD (`4d9b912`), so C3-style pairs stay distinguishable here too.
//       Section D, and D3 is the pair that differs ONLY in `basis`.
//
//   P4  🔴 NO DENOMINATOR, NO NUMBER. Every rate on this screen goes through `rateReading`, and
//       `Number(null) === 0` is defeated at one door (`numOrNull`). Section E — E4 is the
//       literal trap that painted 「검사 0회」 as a measurement earlier today.
//
//   P5  🔴 THE FOUR SECTIONS ALWAYS STAND, AND 「발급된 질문 없음」 IS A SENTENCE ON SCREEN.
//       The investigation panel exists so nobody buys the same question twice; a panel that
//       hides when empty teaches the operator it does not exist. Section F.
//
//   P6  🔴 NO HARDCODED LISTS. Anomaly kinds, gate ids, and factor families all come off the
//       wire. `void` may appear only as a default position — and it does not appear here at
//       all. Section G reads the SOURCE TEXT, and G4/G5 are the mutation checks that make the
//       DOM assertions above non-vacuous: the legend must not be able to satisfy an assertion
//       about a row.

import * as core from '../src/lot_reference_core.js';
import * as view from '../src/lot_reference_view.js';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');

const die = (m) => { console.error(`\nFIXTURE BROKEN — ${m}`); process.exit(2); };

// ── the fixture ─────────────────────────────────────────────────────────────────────
//
// 🔴 IT IS BUILT SO THE TWO CANDIDATE READINGS DISAGREE. A row whose gates are all `true`
// decides nothing about the absent-vs-fail rule; a row that MIXES true / false / null /
// missing / unknown-word is the only shape that separates them. Same for the two `resolved`
// hops: they differ ONLY in `basis`.
const FIX = {
  state: 'ready',
  generated_at: '2026-08-14T09:30:00Z',
  lot: { id: 'CORE-A1', bucket: { id: 'special_eval', label: '특수평가', counts_toward_baseline: false } },
  summary: [
    { id: 'found', term: '보이드 발견', n: 6, of: 412 },
    { id: 'scanned', term: '스캔됨', n: 412, of: 500 },
    // 🔴 분모 없는 항목 — 숫자가 아니라 «분모 없음»으로 나가야 한다.
    { id: 'om', term: 'OM 임의 관측', n: 3, of: null, reason: '분모 없는 종류' },
  ],
  gates: [
    { id: 'real', label: '실재' },
    { id: 'upstream', label: '상류' },
    { id: 'mechanism', label: '기전' },
  ],
  coverage: {
    attributed: 380, of: 412,
    axes: [
      { axis: 'eqp', attributed: 380, of: 412 },
      { axis: 'recipe', attributed: 12, of: 412 },
    ],
  },
  lineage: {
    subject: 'CORE-A1 slot 5',
    anomalies: [
      { code: 'dt_visits', label: 'DT 2회', detail: 'D-77 · D-91', severity: 'high', value: 2 },
      { code: 'dwell', label: '대기 31h', detail: '본딩→DT', severity: 'info', value: 31, unit: 'h' },
    ],
    // 🔴 NODE IDENTITY IS `keys`, NOT `id` — `nodeId()` reads `node.keys.lot` and friends,
    // and a fixture spelling `{id: …}` makes every hop `unresolvable` while looking correct.
    // Caught by D2 on the first run of this harness; the shape is the walk's, not this file's.
    hops: [
      // 🔴 THE PAIR. Both `resolved`. One rests on a MEASUREMENT, one on a declared
      // CONVENTION — and the state word cannot tell them apart.
      {
        from: { keys: { lot: 'PKG-1' } }, to: { keys: { lot: 'BOND-9' } },
        label: '본딩', predicate: 'derived_from', occurred_at: '2026-08-01T00:00:00Z',
        basis: { kind: 'measured', name: 'pair_field' },
        quantity: { moved: 8, of: 12 },
      },
      {
        from: { keys: { lot: 'BOND-9' } }, to: { keys: { lot: 'DT-77' } },
        label: 'DT', predicate: 'derived_from', occurred_at: '2026-08-02T00:00:00Z',
        basis: { kind: 'convention', name: 'same_product_same_frame' },
        quantity: { moved: 8, of: 8 },
      },
      // 끊긴 홉 — 앞 홉의 도착지와 다르다. 다리를 놓지 말고 보여야 한다.
      {
        from: { keys: { lot: 'DT-91' } }, to: { keys: { lot: 'CORE-A1' } },
        label: 'DT 2회차', predicate: 'derived_from', occurred_at: '2026-08-03T00:00:00Z',
      },
    ],
    terminal_reason: '다이 단위 바인딩 미착지 — 랏 수준에서 멈춤',
  },
  factors: [
    {
      axis: 'eqp', value: 'B-3', label: 'B-3', about: 'process',
      family: { id: 'categorical', label: '범주', gap: false },
      found: { n: 5, of: 6 }, clean_scanned: { n: 40, of: 406 },
      enrichment: 8.4,
      // 통과 · 통과 · 미판정 — 이게 DOE 후보다.
      gates: { real: true, upstream: true, mechanism: null },
    },
    {
      axis: 'recipe', value: 'R-12@4', label: 'R-12 rev4', about: 'process',
      family: { id: 'categorical', label: '범주', gap: false },
      found: { n: 4, of: 6 }, clean_scanned: { n: 120, of: 406 },
      enrichment: 2.3,
      // 실재 판정했고 «불통과». 미판정과 같은 칸에 들어가면 안 된다.
      gates: { real: false, upstream: true, mechanism: 'reached' },
      reason: 'katz_lower_below_one',
    },
    {
      axis: 'mi', value: 'thickness', label: '두께 MI', about: 'inspection',
      // 🔴 결측 부류 — 답이 아니라 구멍.
      family: { id: 'missing', label: '결측', gap: true },
      found: { n: 6, of: 6 }, clean_scanned: null,
      gates: { real: 'unknowable_word' },   // 🔴 모르는 낱말 + 두 관문은 키 자체가 없음
    },
  ],
  investigations: [],
};

// The fixture must actually contain the disagreements the sections rely on.
{
  const g = FIX.factors[0].gates;
  if (!(g.real === true && g.mechanism === null)) die('row0 lost its pass/unknown mix');
  if (FIX.factors[1].gates.real !== false) die('row1 lost its measured FAILURE');
  if ('upstream' in FIX.factors[2].gates) die('row2 must be MISSING a gate key, not carry null');
  const b = FIX.lineage.hops.map((h) => h.basis && h.basis.kind);
  if (b[0] !== 'measured' || b[1] !== 'convention') die('the basis pair collapsed');
  // 🔴 THE HOPS MUST ACTUALLY RESOLVE. A fixture whose nodes carry no `keys` makes every hop
  // `unresolvable`, and then D3's "two resolved hops differ only in basis" is scored on a
  // pair that is not resolved at all — a green that means nothing.
  if (!FIX.lineage.hops.every((h) => h.to && h.to.keys)) die('hop endpoints lost their keys');
  if (FIX.lineage.hops[1].to.keys.lot === FIX.lineage.hops[2].from.keys.lot) {
    die('the deliberate continuity BREAK closed up');
  }
  if (FIX.investigations.length !== 0) die('investigations must be measured-empty');
}

// ── the document stub ───────────────────────────────────────────────────────────────
// Same stub as `case_control_harness.mjs` — textContent concatenates descendants, and setting
// it clears children.
function makeDoc() {
  const make = (tag) => ({
    tagName: String(tag).toUpperCase(),
    className: '',
    children: [],
    attrs: Object.create(null),
    style: {},
    _text: '',
    parentNode: null,
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
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
    get firstChild() { return this.children.length ? this.children[0] : null; },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() {
      return this._text + this.children.map((c) => c.textContent).join('');
    },
  });
  return { createElement: (t) => make(t), createElementNS: (ns, t) => make(t) };
}

const walk = (node, out = []) => {
  out.push(node);
  for (const c of node.children) walk(c, out);
  return out;
};
const NOTHING = { tagName: '', className: '', children: [], textContent: '', getAttribute: () => null };
const first = (list) => (list && list.length ? list[0] : NOTHING);
const classesOf = (n) => String(n.className || '').split(/\s+/).filter(Boolean);
const byClass = (root, cls) => walk(root).filter((n) => classesOf(n).includes(cls));
const byAttr = (root, k, v) => walk(root).filter((n) => n.getAttribute(k) === v);
const hasAttr = (root, k) => walk(root).filter((n) => n.getAttribute(k) !== null);
const stripComments = (s) => s
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n').filter((l) => !/^\s*\/\/[:/]?/.test(l)).join('\n');

let pass = 0;
const failed = [];
const ok = (name, cond, detail) => {
  if (cond) pass += 1;
  else failed.push(detail ? `${name} — ${detail}` : name);
};

const render = (body, question) => {
  const doc = makeDoc();
  const mount = doc.createElement('div');
  const q = question || { view: 'lot', lot: 'CORE-A1', slot: '', finding: 'void' };
  view.renderLotReference(doc, mount, core.lotModel({ body, question: q, kind: q.finding }), null);
  return mount;
};

const question = { view: 'lot', lot: 'CORE-A1', slot: '', finding: 'void' };
const model = core.lotModel({ body: FIX, question, kind: 'void' });
const tree = render(FIX, question);

// 🔴 THE CONTAINER, NOT THE TREE. Every gate assertion below is scoped to the rank table's
// tbody, so the legend (which also names 통과/불통과/미판정) cannot satisfy one.
const rankBody = first(hasAttr(tree, 'data-rank-body'));

// ── A. the URL is the question ──────────────────────────────────────────────────────
console.log('\n── A. one question = one URL ─────────────────────────────────────');
{
  const params = new URLSearchParams('view=lot&lot=CORE-A1&slot=5&finding=scratch');
  const q = core.parseLotQuery(params);
  ok('A1 view/lot/slot/finding all read off the URL',
    q.view === 'lot' && q.lot === 'CORE-A1' && q.slot === '5' && q.finding === 'scratch',
    JSON.stringify(q));

  // 🔴 NO LITERAL DEFAULT IN THE CLIENT. An absent `finding` stays EMPTY so `pickKind`
  // resolves it against the server's catalog — a `void` spelled here would be the
  // generalisation quietly dying on the client side.
  const bare = core.parseLotQuery(new URLSearchParams('view=lot&lot=X'));
  ok('A2 absent finding stays empty, not "void"', bare.finding === '', bare.finding);

  ok('A3 the question round-trips through the address',
    core.lotQuery(q) === 'view=lot&lot=CORE-A1&slot=5&finding=scratch', core.lotQuery(q));
  ok('A4 the REQUEST is not the address bar (no view= to the server)',
    !core.lotFetchQuery(q).includes('view='), core.lotFetchQuery(q));
  ok('A5 an empty question is a bare view', core.lotQuery({ lot: '' }) === 'view=lot');
}

// ── B. the three gates ──────────────────────────────────────────────────────────────
console.log('\n── B. 세 관문 — 미판정은 불통과가 아니다 ─────────────────────────');
{
  ok('B1 true -> 통과', core.gateState(true) === 'pass');
  ok('B2 false -> 불통과 (a measured judgement)', core.gateState(false) === 'fail');
  ok('B3 null -> 미판정', core.gateState(null) === 'unknown');
  ok('B4 undefined (absent key) -> 미판정', core.gateState(undefined) === 'unknown');
  // 🔴 THE ONE THAT MATTERS. A word this client does not know may not paint itself
  // confident, and may not be folded into 불통과 either.
  ok('B5 an unknown word -> 미판정, not 통과 and not 불통과',
    core.gateState('unknowable_word') === 'unknown', core.gateState('unknowable_word'));
  ok('B6 0 and "" are not booleans on this path',
    core.gateState(0) === 'unknown' && core.gateState('') === 'unknown');
  // 🔴 THE DEFAULT'S DIRECTION, STATED AS ITS OWN CLAIM. If this ever flips, a lot whose
  // gates were never computed reads as fully refuted, and the DOE candidates vanish.
  ok('B7 the default is 미판정 — an ungraded row can never read 불통과',
    ['pass', 'fail'].every((s) => core.gateState({}) !== s), core.gateState({}));

  const row0 = model.rank.rows[0];
  ok('B8 pass/pass/unknown is counted as 2 passed of 3, 2 judged',
    row0.gates.passed === 2 && row0.gates.judged === 2 && row0.gates.of === 3,
    JSON.stringify({ p: row0.gates.passed, j: row0.gates.judged, o: row0.gates.of }));

  const row2 = model.rank.rows[2];
  ok('B9 a row with two MISSING gate keys reads three cells, all unjudged for the missing two',
    row2.gates.cells.length === 3
    && row2.gates.cells[1].state === 'unknown' && row2.gates.cells[2].state === 'unknown',
    JSON.stringify(row2.gates.cells.map((c) => c.state)));

  // ── on screen, inside the table body only ──
  const states = byAttr(rankBody, 'data-gate-state', 'unknown');
  ok('B10 미판정 cells render INSIDE the rank body', states.length >= 3, String(states.length));
  const fails = byAttr(rankBody, 'data-gate-state', 'fail');
  ok('B11 the one measured failure renders as 불통과 and there is exactly one',
    fails.length === 1, String(fails.length));
  ok('B12 불통과 and 미판정 do not share a word on screen',
    first(fails).textContent.includes('불통과')
    && !first(states).textContent.includes('불통과')
    && first(states).textContent.includes('미판정'),
    `${first(fails).textContent} | ${first(states).textContent}`);
  ok('B13 미판정 and 통과 do not share a glyph',
    !first(states).textContent.includes('✓'), first(states).textContent);
}

// ── C. absent is not measured-empty ─────────────────────────────────────────────────
console.log('\n── C. 「안 봤다」와 「보고 못 찾았다」는 다른 문장 ────────────────');
{
  const noAnom = JSON.parse(JSON.stringify(FIX));
  delete noAnom.lineage.anomalies;
  const t1 = render(noAnom, question);
  ok('C1 absent anomalies renders a GAP, never 「특이점 없음」',
    byAttr(t1, 'data-gap', 'anomalies').length === 1
    && byAttr(t1, 'data-anomaly-none', '1').length === 0);

  const emptyAnom = JSON.parse(JSON.stringify(FIX));
  emptyAnom.lineage.anomalies = [];
  const t2 = render(emptyAnom, question);
  ok('C2 measured-empty anomalies renders the CLAIM, not a gap',
    byAttr(t2, 'data-anomaly-none', '1').length === 1
    && byAttr(t2, 'data-gap', 'anomalies').length === 0);
  ok('C3 the two nothings do not share a sentence',
    first(byAttr(t1, 'data-gap', 'anomalies')).textContent
      !== first(byAttr(t2, 'data-anomaly-none', '1')).textContent);

  const noCov = JSON.parse(JSON.stringify(FIX));
  delete noCov.coverage;
  const t3 = render(noCov, question);
  ok('C4 absent coverage says so — it never assumes full attribution',
    byAttr(t3, 'data-gap', 'coverage').length === 1
    && byAttr(t3, 'data-coverage', '0').length === 1);

  const noFactors = JSON.parse(JSON.stringify(FIX));
  delete noFactors.factors;
  const t4 = render(noFactors, question);
  ok('C5 absent factors is 「미착지」, empty factors is 「차이 0건」',
    byAttr(t4, 'data-gap', 'rank').length === 1 && byAttr(t4, 'data-rank-none', '1').length === 0);
  const zeroFactors = JSON.parse(JSON.stringify(FIX));
  zeroFactors.factors = [];
  ok('C6 …and the second renders the measured zero',
    byAttr(render(zeroFactors, question), 'data-rank-none', '1').length === 1);

  const noBucket = JSON.parse(JSON.stringify(FIX));
  delete noBucket.lot.bucket;
  ok('C7 absent bucket renders 「버킷 미보고」, never a silent 양산',
    first(byAttr(render(noBucket, question), 'data-bucket', '')).textContent.includes('미보고'));
  ok('C8 special_eval is SHOWN AND MARKED, with its baseline exclusion visible',
    byAttr(tree, 'data-bucket', 'special_eval').length === 1
    && byAttr(tree, 'data-baseline', '0').length === 1);
}

// ── D. basis is consumed, not derived ───────────────────────────────────────────────
console.log('\n── D. basis — 두 resolved 홉이 같은 낱말을 단다 ─────────────────');
{
  const hops = model.lineage.hops;
  ok('D1 the walk is ANY length — three hops, not a fixed stage index', hops.length === 3);
  ok('D2 both of the first two hops read `resolved`',
    hops[0].state === 'resolved' && hops[1].state === 'resolved');
  // 🔴 THE PAIR THE RULE IS DECIDED ON: same state word, different basis.
  ok('D3 …and they are still told apart, because basis is a FIELD',
    hops[0].basis.kind === 'measured' && hops[1].basis.kind === 'convention',
    JSON.stringify([hops[0].basis, hops[1].basis]));
  ok('D4 the convention hop says 가정 on screen',
    first(byAttr(tree, 'data-basis-kind', 'convention')).textContent.includes('가정'),
    first(byAttr(tree, 'data-basis-kind', 'convention')).textContent);
  ok('D5 the measured hop says 근거',
    first(byAttr(tree, 'data-basis-kind', 'measured')).textContent.includes('근거'));
  ok('D6 a continuity break is SHOWN, not bridged',
    hops[2].continuous === false && byAttr(tree, 'data-hop-break', '1').length === 1);
  ok('D7 the terminal reason is the server\'s sentence, verbatim',
    byAttr(tree, 'data-lineage-terminal', FIX.lineage.terminal_reason).length === 1);
  ok('D8 the declared anomalies render as badges with the server\'s own words',
    byAttr(tree, 'data-anomaly', 'dt_visits').length === 1
    && byAttr(tree, 'data-anomaly', 'dwell').length === 1
    && first(byAttr(tree, 'data-anomaly', 'dt_visits')).textContent.includes('DT 2회'));
}

// ── E. no denominator, no number ────────────────────────────────────────────────────
console.log('\n── E. 분모 없는 숫자는 이 화면을 못 떠난다 ──────────────────────');
{
  ok('E1 numOrNull(null) is null, not 0', core.numOrNull(null) === null);
  ok('E2 numOrNull("") is null, not 0', core.numOrNull('') === null);
  ok('E3 a real 0 survives as 0', core.numOrNull(0) === 0);
  // 🔴 THE TRAP THAT ALREADY FIRED ONCE TODAY: `Number(null) === 0` painting 「검사 0회」
  // as a measurement. A missing denominator must refuse, not divide by a manufactured zero.
  const r = core.rateReading(3, null, '분모 없는 종류');
  ok('E4 a missing denominator REFUSES — it does not become 「검사 0회」',
    r.ok === false && r.d === null && r.text.includes('분모 없음'), JSON.stringify(r));
  ok('E5 a real zero denominator is a DIFFERENT refusal',
    core.rateReading(3, 0).why.includes('검사 0회'));

  const rates = byClass(tree, 'cc-rate');
  ok('E6 every rendered rate declares whether it has a denominator',
    rates.length > 0 && rates.every((n) => n.getAttribute('data-rate-ok') !== null),
    String(rates.length));
  const okRates = rates.filter((n) => n.getAttribute('data-rate-ok') === '1');
  ok('E7 every ok rate carries BOTH numerator and denominator on screen',
    okRates.length > 0 && okRates.every((n) => walk(n).some((c) => c.getAttribute('data-numerator') !== null)
      && walk(n).some((c) => c.getAttribute('data-denominator') !== null)),
    String(okRates.length));
  // 🔴 THE REASON IS THE SERVER'S, AND IT REPLACES THE NUMBER — not decorates it. A bare
  // 「3」 with no denominator beside it is the one thing this screen may not print.
  const om = first(byAttr(tree, 'data-stat', 'om'));
  ok('E8 the denominator-less summary row prints its reason, and no percentage',
    om.textContent.includes('분모 없는 종류') && !om.textContent.includes('%'), om.textContent);
  ok('E9 「안 난 쪽」 with no control population refuses with a reason',
    model.rank.rows[2].inClean.ok === false && model.rank.rows[2].inClean.why === '대조군 없음');
  ok('E10 attribution coverage renders as N of M, per axis',
    byAttr(tree, 'data-coverage-axis', 'eqp').length === 1
    && first(byAttr(tree, 'data-coverage-axis', 'eqp')).textContent.includes('380'),
    first(byAttr(tree, 'data-coverage-axis', 'eqp')).textContent);
}

// ── F. the four sections always stand ───────────────────────────────────────────────
console.log('\n── F. 네 구역 — 빈 칸도 문장으로 서 있다 ────────────────────────');
{
  for (const key of ['header', 'lineage', 'rank', 'investigations']) {
    ok(`F1.${key} the section renders`, byAttr(tree, 'data-panel', key).length === 1);
  }
  // 🔴 THE SENTENCE THE BRIEF ASKS FOR, ON SCREEN, TODAY.
  const none = first(byAttr(tree, 'data-investigations', '0'));
  ok('F2 「발급된 질문 없음」 is a sentence on screen, not a hidden panel',
    none.textContent === '발급된 질문 없음', none.textContent);
  ok('F3 …and the panel says WHY, differently for measured-empty vs not-deployed',
    first(byAttr(tree, 'data-panel', 'investigations')).textContent.includes('발급된 수집 요청이 없습니다'));

  const noLog = JSON.parse(JSON.stringify(FIX));
  delete noLog.investigations;
  const t = render(noLog, question);
  ok('F4 with the axis undeployed the SAME sentence stands, with a different reason',
    first(byAttr(t, 'data-investigations', '0')).textContent === '발급된 질문 없음'
    && first(byAttr(t, 'data-panel', 'investigations')).textContent.includes('R6'));

  // 답 있는/없는 항목이 같은 문장을 쓰지 않는다.
  const withLog = JSON.parse(JSON.stringify(FIX));
  withLog.investigations = [
    { id: 'REQ-1', kind: 'collect_request', kind_label: '수집 요청', question: 'B-3 위 두께 재기', state: 'open', opened_at: '2026-08-10T00:00:00Z' },
    { id: 'REQ-2', kind: 'collect_request', question: '이전 질문', state: 'closed', answer: '두께 정상', reissue_of: 'REQ-0' },
  ];
  const t2 = render(withLog, question);
  ok('F5 an unanswered request says 「답 미도착」, not 「답 없음」',
    first(byAttr(t2, 'data-answer', '0')).textContent === '답 미도착');
  ok('F6 an answered one renders its answer', byAttr(t2, 'data-answer', '1').length === 1);
  ok('F7 a reissue carries the question it re-asked', byAttr(t2, 'data-reissue-of', 'REQ-0').length === 1);

  // 랏 없는 참조뷰는 오류가 아니라 안내다.
  const bare = render(null, { view: 'lot', lot: '', slot: '', finding: '' });
  ok('F8 no lot in the URL is CONTENT, not an error or a blank',
    byAttr(bare, 'data-gap', 'no-lot').length === 1 && byAttr(bare, 'data-panel', 'rank').length === 0);

  // 🔴 착지 안 한 쓰기 축을 «버튼»으로 위장하지 않는다.
  ok('F9 the action bar is absent AND said out loud — no dead button',
    byAttr(tree, 'data-gap', 'actions').length === 1
    && walk(tree).filter((n) => n.tagName === 'BUTTON').length === 0);

  // 🔴 THE GRAPH LINK. The old graph branch is retired (판정 R-2026-08-14-H) — every
  // `/graph/*` route now refuses — so this must NOT point at `graph.html`.
  const g = first(byAttr(tree, 'data-structure-link', '1'));
  ok('F10 the graph link points at the ledger\'s own generated structure view',
    g.getAttribute('href') === '?view=structure', g.getAttribute('href'));
  ok('F11 nothing on this screen links to the retired graph screen',
    !walk(tree).some((n) => String(n.getAttribute('href') || '').includes('graph.html')));
  ok('F12 the view\'s own address is on screen — this is a link you can paste',
    first(byAttr(tree, 'data-self-link', '1')).getAttribute('href').startsWith('?view=lot&lot='));
}

// ── G. no hardcoded lists, and the DOM assertions are not vacuous ───────────────────
console.log('\n── G. 하드코딩 금지 · 단언이 공허하지 않은가 ────────────────────');
{
  const coreSrc = stripComments(readFileSync(join(SRC, 'lot_reference_core.js'), 'utf8'));
  const viewSrc = stripComments(readFileSync(join(SRC, 'lot_reference_view.js'), 'utf8'));

  ok('G1 no `void` literal anywhere — the kind comes from the server catalog',
    !/['"]void['"]/.test(coreSrc) && !/['"]void['"]/.test(viewSrc));
  ok('G2 no anomaly kind is spelled in the source',
    !/dt_visits|dwell|DT 2회|대기 31h/.test(coreSrc + viewSrc));
  ok('G3 no family id is matched by string — `gap` is the server\'s flag',
    !/===\s*['"]missing['"]/.test(coreSrc) && !/===\s*['"]missing['"]/.test(viewSrc));

  // 🔴 THE MUTATION CHECKS. Without these, B10–B13 could be satisfied by the legend alone.
  const noRows = JSON.parse(JSON.stringify(FIX));
  noRows.factors = [];
  const mutated = render(noRows, question);
  ok('G4 MUTATION — delete every row and the gate assertions go RED',
    byAttr(mutated, 'data-gate-state', 'unknown').length === 0
    && byAttr(mutated, 'data-gate-state', 'fail').length === 0,
    `unknown=${byAttr(mutated, 'data-gate-state', 'unknown').length} fail=${byAttr(mutated, 'data-gate-state', 'fail').length}`);
  // …while the legend is still there, still naming all three words. That is exactly why the
  // legend may not carry `data-gate-state`.
  const legendStill = byAttr(mutated, 'data-legend', '1').length === 1
    && first(byAttr(mutated, 'data-legend', '1')).textContent.includes('미판정');
  ok('G5 …and the legend SURVIVES that deletion, still saying 미판정 — so a tree-wide sweep '
    + 'would have stayed green. The scoping is load-bearing.', legendStill);

  const cellAttrs = byAttr(rankBody, 'data-gate-state', 'unknown').length;
  ok('G6 MUTATION — flip the default to `fail` and B7 would break (documented direction)',
    cellAttrs > 0 && core.gateState(undefined) !== 'fail');

  // 서버가 넷째 관문을 선언하면 넷째 열이 코드 0줄로 생긴다.
  const fourth = JSON.parse(JSON.stringify(FIX));
  fourth.gates.push({ id: 'dose', label: '용량' });
  const t = render(fourth, question);
  ok('G7 a FOURTH declared gate becomes a fourth column with no line changing here',
    byAttr(t, 'data-gate-col', 'dose').length === 1
    && byAttr(t, 'data-gate', 'dose').length === FIX.factors.length,
    String(byAttr(t, 'data-gate', 'dose').length));
  ok('G8 …and every cell in it is 미판정, because nobody judged it',
    byAttr(t, 'data-gate', 'dose').every((n) => n.getAttribute('data-gate-state') === 'unknown'));

  // 서버가 관문 축을 안 실으면 기본 세 관문 — 그리고 그렇다고 «말한다».
  const noGates = JSON.parse(JSON.stringify(FIX));
  delete noGates.gates;
  const t2 = render(noGates, question);
  ok('G9 an undeclared gate axis falls back to the default THREE and says so',
    byAttr(t2, 'data-gate-col', 'real').length === 1
    && first(byAttr(t2, 'data-legend', '1')).textContent.includes('관문 축 미선언'));

  ok('G10 the client does NOT re-sort — rows keep the server\'s order',
    model.rank.rows.map((r) => r.key).join(',') === FIX.factors.map((f) => f.value).join(','),
    model.rank.rows.map((r) => r.key).join(','));
  ok('G11 the source contains no sort of the ranking rows',
    !/rows\.sort|factors\.sort/.test(coreSrc));

  ok('G12 the 결측 부류 row is painted as a HOLE, not as a finding',
    byAttr(tree, 'data-family-gap', '1').length === 1
    && classesOf(first(byAttr(tree, 'data-rank-row', 'thickness'))).includes('lr-row--gap'));

  ok('G13 neither file touches `window` or `document` (bare-node scorable)',
    !/\bwindow\.|\bdocument\./.test(coreSrc) && !/\bwindow\.|\bdocument\./.test(viewSrc));
}

// ── report ─────────────────────────────────────────────────────────────────────────
//
// 🔴 THE MACHINE LINE IS NOT OPTIONAL. `check_harnesses.mjs` reads `ASSERTIONS <ran>
// <failed>` and treats an exit-0 with no line — or with ran=0 — as DEAD rather than green,
// because a harness that crashes before asserting anything exits the same way one that
// passed does. It is printed from THIS file's own counters; the runner never re-scores prose.
console.log(`\n${'─'.repeat(66)}`);
const ran = pass + failed.length;
if (failed.length === 0) {
  console.log(`✅ ALL GREEN — ${pass} claims scored`);
} else {
  console.log(`❌ ${failed.length} FAILED (of ${ran})`);
  for (const f of failed) console.log(`   · ${f}`);
}
console.log(`ASSERTIONS ${ran} ${failed.length}`);
process.exit(failed.length === 0 ? 0 : 1);
