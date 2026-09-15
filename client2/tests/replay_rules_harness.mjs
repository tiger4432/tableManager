/**
 * 🏷️ C-109 — 「다시 돌리기」 목록은 «이 표를 트리거로 하는» 규칙만이고, 줄이 «어디서 어디로»를
 *    말한다. 대상을 **IMPORT** 해서 잽니다 (소유자 상설 2026-09-02: 잘라쓰기 금지).
 *
 * 🔴 소유자가 본 것(2026-09-15): 「그리드 상단 리플레이 버튼에 조인도 달아줘. 같은 체인문이면
 *    보여야지. 그리고 리플레이 버튼 누를 시 목록은 해당 테이블이 트리거인 체인 규칙만」.
 *    종전 목록은 «이름 문자열»이라 (ⓐ) 어느 표의 규칙인지 화면이 몰랐고 (ⓑ) 같은 이름의 조인과
 *    합성이 «같아 보였»고 (ⓒ) 표를 바꿔도 목록이 안 바뀌었습니다.
 *
 * 🔴 여기서 재는 것과 «재지 않는» 것:
 *    잽니다   — 목록을 긷는 함수(`replayable_rules.js`)와 줄을 그리는 부품(`redo_banner.js`)
 *    안 잽니다 — 「표가 바뀌면 다시 부른다」의 «배선»(main.js). 그 파일은 node 가 import 할 수
 *              없어(ag-grid + CSS + `init()`) 재려면 잘라쓰기뿐입니다. 그래서 그 자리는
 *              «실제 페이지»에서 봅니다 — 보고서에 그렇게 적습니다.
 * ⚠️ 「못 읽음 ≠ 빈 목록」의 두 문구는 `redo_banner_harness.mjs` §I 가 이미 잽니다. 같은 물음에
 *    두 집이 생기면 언젠가 둘이 다른 답을 합니다 — 여기서는 «새 주장»만 잽니다.
 *
 * Run: node client2/tests/replay_rules_harness.mjs
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const LOADER = path.join(HERE, '..', 'src', 'replayable_rules.js');
const BANNER = path.join(HERE, '..', 'src', 'redo_banner.js');

let ran = 0;
let failed = 0;

// ── 저장소와 fetch 는 «브라우저의 것»입니다. 스텁이 그 계약을 그대로 흉내 냅니다 ──────────
let token = 'tok-1';
globalThis.localStorage = {
  getItem: (k) => (k === 'assy.adminToken' ? (token || null) : null),
  setItem() {}, removeItem() {},
};
let asked = [];
let answer = null;
globalThis.fetch = async (url, init) => {
  asked.push({ url: String(url), init });
  if (typeof answer === 'function') return answer();
  return answer;
};
const okBody = (data) => ({ ok: true, json: async () => ({ status: 'success', data }) });

// ── 문서 스텁: 이 부품은 `doc` 을 «주입받습니다». 진짜 DOM 이 필요 없는 것이 그 값어치입니다 ──
function mkDoc() {
  const listeners = {};
  const el = (tag) => {
    const node = {
      tagName: String(tag).toUpperCase(), children: [], className: '',
      dataset: {}, disabled: false, type: '', style: {}, handlers: {}, parentNode: null,
      appendChild(child) { child.parentNode = this; this.children.push(child); return child; },
      setAttribute(k, v) { this.dataset[k] = String(v); },
      addEventListener(name, fn) { this.handlers[name] = fn; },
      click() { if (this.handlers.click) this.handlers.click(); },
    };
    // 🔴 `textContent = ''` 는 진짜 문서에서 «자식을 지웁니다». 안 지우는 스텁은 매 렌더가
    //    쌓이는 것을 못 보고, 그 결함은 「두 번 그렸다」와 똑같이 생겼습니다.
    let text = '';
    Object.defineProperty(node, 'textContent', {
      get() { return text + node.children.map((k) => k.textContent).join(''); },
      set(v) { text = String(v); node.children.length = 0; },
      configurable: true,
    });
    return node;
  };
  return {
    createElement: el,
    addEventListener(name, fn) { (listeners[name] = listeners[name] || []).push(fn); },
    removeEventListener(name, fn) {
      const list = listeners[name] || [];
      const at = list.indexOf(fn);
      if (at !== -1) list.splice(at, 1);
    },
  };
}
const walk = (node) => (node.children || [])
  .reduce((all, kid) => all.concat([kid], walk(kid)), []);
const byClass = (root, cls) => walk(root)
  .filter((n) => String(n.className || '').split(/\s+/).includes(cls));

// 🔴 C-112. 진짜 그리드 행은 `row_id` 를 «봉투 밖» 최상위에 들고 있습니다(`grid.js` 의
//    `getRowId` · 삭제 경로의 `node.data.row_id`). 픽스처가 그것을 안 달면 이 하니스는
//    «없는 표»를 재게 됩니다. `rowId: null` 은 «그 칸이 빈 행»을 일부러 만드는 자리입니다.
let rowSeq = 0;
const envelope = (obj, rowId) => ({
  row_id: rowId === undefined ? `r${(rowSeq += 1)}` : rowId,
  data: Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, { value: v }])) });
const readEnvelope = (row, col) => {
  const cell = row && row.data ? row.data[col] : undefined;
  if (cell && typeof cell === 'object' && 'value' in cell) return cell.value;
  return row ? row[col] : undefined;
};

const JOIN = { name: 'lot_slot_join', trigger_table: 'dt_lot', target_table: 'dt_wafer',
               kind: 'join' };
const MAP = { name: 'yield_mapper', trigger_table: 'dt_lot', target_table: 'dt_yield',
              kind: 'mapper' };

function suite(name) {
  const names = [];
  const failures = [];
  const say = (id, cond, detail) => {
    names.push(id);
    if (cond) { console.log(`  PASS ${id}`); return; }
    failures.push(detail === undefined ? id : `${id} — ${JSON.stringify(detail)}`);
    console.log(`  FAIL ${id}${detail === undefined ? '' : `  -- saw ${JSON.stringify(detail)}`}`);
  };
  return { names, failures, say, name };
}

// ═══ A. 목록을 긷는 함수 — 「이 표」를 묻고, 세 상태로 답한다 ═══════════════════════════
async function loaderSuite(mod) {
  const s = suite('loader');
  const call = async (table, reply, tok = 'tok-1') => {
    asked = []; answer = reply; token = tok;
    const got = await mod.loadReplayableRules(table);
    return { got, asked: asked.slice() };
  };

  // 🔴 표 이름은 «질의에 실려» 갑니다. 안 실으면 서버는 「전부」로 답하고, 화면은 남의 표의
  //    규칙을 이 표의 것처럼 내놓습니다 — 오류 없이.
  const one = await call('dt lot&x', okBody([JOIN]));
  s.say('A1 the request names THIS table, encoded',
    one.asked.length === 1
    && one.asked[0].url.includes('/admin/chain/rules/replayable?table=')
    && one.asked[0].url.endsWith(`table=${encodeURIComponent('dt lot&x')}`),
    one.asked.map((a) => a.url));
  // ⚠️ 토큰은 «헤더»입니다. 질의 문자열은 서버 접근 로그에 남습니다(`admin_token.js` 의 사유).
  s.say('A2 the token rides in the header, never in the query',
    one.asked[0].init && one.asked[0].init.headers
    && one.asked[0].init.headers['X-Admin-Token'] === 'tok-1'
    && !one.asked[0].url.includes('tok-1'),
    one.asked[0].init);
  s.say('A3 ... and the answer is the server\'s array, unchanged',
    Array.isArray(one.got) && one.got.length === 1 && one.got[0] === JOIN, one.got);

  const noTok = await call('dt_lot', okBody([JOIN]), '');
  s.say('A4 no token: no request is made at all, and the answer is 「unknown」',
    noTok.asked.length === 0 && noTok.got === null, noTok);
  const noTable = await call('', okBody([JOIN]));
  s.say('A5 no table: no subject, so no request and no claim',
    noTable.asked.length === 0 && noTable.got === null, noTable);

  // 🔴 이 셋이 같은 값이 되면 화면이 「403」과 「빈 목록」을 같은 픽셀로 그립니다.
  const empty = await call('dt_lot', okBody([]));
  s.say('A6 an empty list is a MEASUREMENT: `[]`, not null',
    Array.isArray(empty.got) && empty.got.length === 0, empty.got);
  const refused = await call('dt_lot', { ok: false, json: async () => ({}) });
  s.say('A7 a refusal is 「could not read」: null, not an empty list', refused.got === null,
    refused.got);
  const odd = await call('dt_lot', { ok: true, json: async () => ({ status: 'success' }) });
  s.say('A8 a body without a list is 「could not read」 too', odd.got === null, odd.got);
  const threw = await call('dt_lot', () => { throw new Error('offline'); });
  s.say('A9 a thrown fetch does not escape — the page must not die on a list',
    threw.got === null, threw.got);
  return { ran: s.names.length, names: s.names, failures: s.failures };
}

// ═══ B. 줄 — 「어떤 규칙이 어디서 어디로, 무슨 종류로」 ══════════════════════════════════
function bannerSuite(mod) {
  const s = suite('banner');
  const lines = (rules) => {
    const doc = mkDoc();
    const host = doc.createElement('div');
    const part = new mod.RedoBanner(host, {
      doc, sources: [],
      getSelection: () => [envelope({ lot_id: 'L1' }), envelope({ lot_id: 'L2' })],
      readValue: readEnvelope, businessKey: 'lot_id', handOff: () => {},
      hasToken: () => true, run: () => Promise.resolve({ ok: true }), rules,
    });
    part.setRelation('dt_lot');
    part.render();
    const chain = walk(host).find((n) => n.dataset && n.dataset.redo === 'chain');
    if (chain) chain.click();
    return { host, rows: byClass(host, 'redo-panel__group') };
  };

  const two = lines([JOIN, MAP]);
  // 🔴 줄이 «없을» 수 있습니다 — 신원을 못 읽으면 판은 문장 하나입니다. 그때 첨자로
  //    들어가면 하니스가 «던지고», 던진 하니스는 「잡았다」가 아니라 구멍입니다(변이 채점기의 규율).
  const rowText = (i) => (two.rows[i] ? two.rows[i].textContent : '(no line)');
  s.say('B1 one pressable line per rule the server sent',
    two.rows.length === 2 && two.rows.every((n) => n.tagName === 'BUTTON'),
    two.rows.map((n) => `${n.tagName}:${n.textContent}`));
  // 🔴 소유자의 물음이 이것입니다 — 「같은 체인문이면 보여야지」. 이름만으로는 조인과 합성이
  //    화면에서 구별되지 않습니다.
  s.say('B2 the line says where the rule runs FROM and TO',
    rowText(0).includes('dt_lot → dt_wafer') && rowText(1).includes('dt_lot → dt_yield'),
    two.rows.map((n) => n.textContent));
  const kindOf = (i) => (two.rows[i] ? byClass(two.rows[i], 'redo-panel__kind') : []);
  s.say('B3 the kind is its own cell, one word — not glued onto the sentence',
    kindOf(0).length === 1 && kindOf(0)[0].textContent === 'join'
    && kindOf(1).length === 1 && kindOf(1)[0].textContent === 'mapper',
    two.rows.map((n) => byClass(n, 'redo-panel__kind').map((k) => k.textContent)));
  // ⚠️ 확인 창이 없습니다 — 줄에 «크기»가 적혀 있고 그것을 누르는 것이 확인입니다.
  // ⚠️ C-112 에서 문구가 «좁아졌습니다»: 종전의 「N keys from M rows」는 업무 키와 행이
  //    갈라질 수 있을 때의 문구였고, row_id 는 중복이 없으므로 둘이 같습니다(판정 407 ②).
  s.say('B4 the size stays on the line, because pressing it IS the confirmation',
    two.rows.length === 2 && two.rows.every((n) => /2 rows/.test(n.textContent))
    && two.rows.every((n) => !/keys from/.test(n.textContent)),
    two.rows.map((n) => n.textContent));
  // 🔴 넘기는 것은 «이름»입니다. 서버는 `rule` 에 이름을 받지 객체를 받지 않습니다.
  const fired = [];
  // ⚠️ 행의 id 를 «글자로» 박으면 이 파일이 몇 번째로 만든 행인가에 달려 변이마다 움직입니다.
  //    재려는 것은 «그 행의 id 가 그대로 실렸나»이므로 행을 들고 비교합니다.
  const only = envelope({ lot_id: 'L1' });
  {
    const doc = mkDoc();
    const host = doc.createElement('div');
    const part = new mod.RedoBanner(host, {
      doc, sources: [],
      getSelection: () => [only],
      readValue: readEnvelope, businessKey: 'lot_id', handOff: () => {},
      hasToken: () => true,
      run: (op, params) => { fired.push({ op, params }); return Promise.resolve({ ok: true }); },
      rules: [JOIN],
    });
    part.setRelation('dt_lot');
    part.render();
    walk(host).find((n) => n.dataset && n.dataset.redo === 'chain').click();
    const row = byClass(host, 'redo-panel__group')[0];
    if (row && row.handlers.click) row.handlers.click();
  }
  // 🔴 C-112. 보내는 신원은 `row_ids` 입니다 — 그리드가 들고 있는 그것. 저장된 업무 키는
  //    composite 표에서 «조립된 문자열»이라 화면이 보내면 서버가 한 행도 못 찾습니다
  //    (박스 실측: `rows_scanned 0`, 오류 없이). 그리고 둘 다 보내면 서버가 거절합니다.
  s.say('B5 pressing it runs THAT rule by name, with the ROW IDS',
    fired.length === 1 && fired[0].params.rule === 'lot_slot_join'
    && fired[0].params.row_ids === only.row_id
    && !('business_keys' in fired[0].params), [fired, only.row_id]);

  // 🔴 서버가 안 말한 것은 화면이 «지어내지» 않습니다 — 세 상태의 셋째입니다.
  const bare = lines([{ name: 'only_a_name' }]);
  // ⚠️ 위와 같은 사유로 첫자를 막습니다 — 줄이 없는 것도 «답»이고, 그것을 받아 적어야
  //    신원을 잃은 변이가 «구멍»이 아니라 «잡힌 것»이 됩니다.
  const bareRow = bare.rows[0] || null;
  const bareText = bareRow ? bareRow.textContent : '(no line)';
  s.say('B6 a rule with no kind gets no badge',
    bareRow !== null && byClass(bareRow, 'redo-panel__kind').length === 0, bareText);
  s.say('B7 ... and with no tables, no arrow is invented',
    bareRow !== null && !bareText.includes('→') && !bareText.includes('undefined'),
    bareText);
  // 이름이 없으면 돌릴 수가 없습니다(`rule` 은 필수). 누르는 줄로 두면 400 을 부르는 줄입니다.
  const nameless = lines([{ trigger_table: 'dt_lot', target_table: 'dt_wafer', kind: 'join' }]);
  s.say('B8 a rule with no name is not a line you can press',
    nameless.rows.length === 1 && nameless.rows[0]
    && nameless.rows[0].tagName === 'DIV',
    nameless.rows.map((n) => `${n.tagName}:${n.textContent}`));
  // 🔴 C-112 — «한 물음에 두 답»을 보내지 않습니다. 서버는 둘 다 오면 거절하고
  //    (교집합이 아닙니다), 평키 표만 다른 길을 타면 그 표에서만 나는 고장이 생깁니다.
  const seen = JSON.stringify(two.rows.map((n) => n.textContent));
  // ⚠️ «보내는 것»은 둔러입니다: 줄을 누를 때의 `params` 와 「Open in admin」이 넘기는 짐.
  //    한쪽만 보면 다른 쪽에 업무 키가 남아도 이 줄이 초록입니다(실측: 변이 N12 가 탈출했습니다).
  let handed = null;
  {
    const doc = mkDoc();
    const host = doc.createElement('div');
    const part = new mod.RedoBanner(host, {
      doc, sources: [],
      getSelection: () => [envelope({ lot_id: 'L1' })],
      readValue: readEnvelope, handOff: (p) => { handed = p; },
      hasToken: () => true, run: () => Promise.resolve({ ok: true }), rules: [JOIN],
    });
    part.setRelation('dt_lot');
    part.render();
    walk(host).find((n) => n.dataset && n.dataset.redo === 'chain').click();
    const go = byClass(host, 'redo-panel__go')[0];
    if (go) go.click();
  }
  s.say('B9 no business key is anywhere on this screen or in EITHER thing it sends',
    !/business/i.test(seen)
    && !JSON.stringify(fired).includes('business')
    && handed !== null && !JSON.stringify(handed).includes('business')
    && handed.params && typeof handed.params.row_ids === 'string',
    [seen, fired, handed]);
  // 🔴 판정 407 ②. row_id 가 없는 행은 «이름을 달고» 섭니다 — 조용히 빠지면
  //    운영자는 고른 행이 전부 돌았다고 읽습니다.
  const withHole = (() => {
    const doc = mkDoc();
    const host = doc.createElement('div');
    const part = new mod.RedoBanner(host, {
      doc, sources: [],
      getSelection: () => [envelope({ lot_id: 'L1' }), envelope({ lot_id: 'L2' }, null)],
      readValue: readEnvelope, handOff: () => {},
      hasToken: () => true, run: () => Promise.resolve({ ok: true }), rules: [JOIN],
    });
    part.setRelation('dt_lot');
    part.render();
    walk(host).find((n) => n.dataset && n.dataset.redo === 'chain').click();
    return byClass(host, 'redo-panel__group');
  })();
  s.say('B10 a row with no row_id is NAMED and counted, not dropped',
    withHole.some((n) => /row_id 없는 행 1/.test(n.textContent)),
    withHole.map((n) => n.textContent));
  s.say('B11 ... and that line cannot be pressed, because those rows do not run',
    withHole.filter((n) => /row_id 없는 행/.test(n.textContent))
      .every((n) => n.tagName === 'DIV')
    && withHole.some((n) => n.tagName === 'BUTTON' && /— 1 row/.test(n.textContent)),
    withHole.map((n) => `${n.tagName}:${n.textContent}`));
  // ═══ W. C-113 ① — 선택이 크면 «한 줄»로 말하고, 막지는 않는다 ═════════════
  //
  // 🔴 운영 규격은 「한 트랜잭션에 수천 행」입니다(소유자 2026-09-08). 그보다 큰 선택은
  //    «틀린 것이 아니라» 큰 것이라, 화면은 수와 기준만 적고 누를지는 사람이 정합니다.
  // ⚠️ 기준은 «옵션»입니다(`warnAbove`) — 숫자를 박으면 그 숫자가 다른 설치에서도
  //    맞다고 말하는 것이 됩니다(「임시로 박스에 설정한 것으로 말하지 말 것」 상설).
  const warnLines = (rowCount, opts = {}) => {
    const doc = mkDoc();
    const host = doc.createElement('div');
    const rows = Array.from({ length: rowCount }, (_, i) => envelope({ lot_id: `L${i}` }));
    const part = new mod.RedoBanner(host, {
      doc, sources: [], getSelection: () => rows, readValue: readEnvelope, handOff: () => {},
      hasToken: () => true, run: () => Promise.resolve({ ok: true }), rules: [JOIN], ...opts,
    });
    part.setRelation('dt_lot');
    part.render();
    const chain = walk(host).find((n2) => n2.dataset && n2.dataset.redo === 'chain');
    if (chain) chain.click();
    return { warn: byClass(host, 'redo-panel__warn'), rows: byClass(host, 'redo-panel__group') };
  };
  const small = warnLines(3, { warnAbove: 5 });
  s.say('W1 a selection under the threshold says nothing about size',
    small.warn.length === 0, small.warn.map((n2) => n2.textContent));
  const big = warnLines(7, { warnAbove: 5 });
  s.say('W2 over it, ONE line with the count and the threshold',
    big.warn.length === 1 && /7/.test(big.warn[0].textContent)
    && /5/.test(big.warn[0].textContent), big.warn.map((n2) => n2.textContent));
  // 🔴 막지 않습니다 — 막으면 정당하게 큰 범위를 돌릴 길이 없어집니다.
  s.say('W3 ... and it does not block: the rule lines are still pressable',
    big.rows.length === 1 && big.rows[0].tagName === 'BUTTON',
    big.rows.map((n2) => `${n2.tagName}:${n2.textContent}`));
  const byDefault = warnLines(3);
  s.say('W4 the threshold is an option, not a number baked into the part',
    byDefault.warn.length === 0 && warnLines(1001).warn.length === 1,
    byDefault.warn.length);
  return { ran: s.names.length, names: s.names, failures: s.failures };
}

// ── 채점 ────────────────────────────────────────────────────────────────────────────────
const swap = (text, from, to) => {
  if (!text.includes(from)) {
    throw new Error(`mutation anchor is GONE: ${from.slice(0, 70)}`);
  }
  return text.split(from).join(to);
};

console.log('\n[A] the loader asks for THIS table, and answers in three states');
const loaderBase = await loadWithProbe(LOADER, {});
const baseA = await loaderSuite(loaderBase.module);
ran += baseA.ran;
failed += baseA.failures.length;

console.log('\n[B] the line names the rule, its path, and its kind');
const bannerBase = await loadWithProbe(BANNER, {});
const baseB = bannerSuite(bannerBase.module);
ran += baseB.ran;
failed += baseB.failures.length;

const LOADER_MUTANTS = [
  { id: 'N1', what: 'the table is dropped from the request, so the server answers for all of them',
    catches: 'A1 the request names THIS table',
    mutate: (t) => swap(t, "/admin/chain/rules/replayable?table=${encodeURIComponent(table)}`",
      "/admin/chain/rules/replayable`") },
  { id: 'N2', what: 'the request goes out without a token',
    catches: 'A4 no token: no request is made',
    mutate: (t) => swap(t, "  if (!token) return null;\n", '') },
  { id: 'N3', what: 'an empty list is folded into 「could not read」',
    catches: 'A6 an empty list is a MEASUREMENT',
    mutate: (t) => swap(t, '    return body.data;', '    return body.data.length ? body.data : null;') },
  { id: 'N4', what: 'a refusal is drawn as 「this table has no rule」',
    catches: 'A7 a refusal is 「could not read」',
    mutate: (t) => swap(t, '    if (!res.ok) return null;', '    if (!res.ok) return [];') },
];

const BANNER_MUTANTS = [
  { id: 'N5', what: 'the line loses where the rule runs from and to',
    catches: 'B2 the line says where the rule runs FROM and TO',
    mutate: (t) => swap(t, "          ? ` · ${rule.trigger_table} → ${rule.target_table}` : '';",
      "          ? '' : '';") },
  { id: 'N6', what: 'the kind is glued onto the sentence instead of standing in its own cell',
    catches: 'B3 the kind is its own cell',
    mutate: (t) => swap(t, "          kind: (rule && rule.kind) || '',",
      "          kind: '',") },
  { id: 'N7', what: 'the size leaves the line, so pressing it confirms nothing',
    catches: 'B4 the size stays on the line',
    mutate: (t) => swap(t, '          text: `${name}${path} — ${from}`,',
      '          text: `${name}${path}`,') },
  { id: 'N8', what: 'the whole rule object is handed to the server as `rule`',
    catches: 'B5 pressing it runs THAT rule by name',
    mutate: (t) => swap(t, '          params: name ? { rule: name, row_ids: keys } : null,',
      '          params: name ? { rule, business_keys: keys } : null,') },
  { id: 'N10', what: 'the screen sends what it can SEE instead of the row identity',
    catches: 'B1 one pressable line per rule',
    mutate: (t) => swap(t, "scopeValuesFor(rows, 'row_id', this.readValue)",
      "scopeValuesFor(rows, 'business_key_val', this.readValue)") },
  { id: 'N11', what: 'rows without a row_id are dropped in silence',
    catches: 'B10 a row with no row_id is NAMED',
    mutate: (t) => swap(t, '    const skipped = missing', '    const skipped = false') },
  { id: 'N12', what: 'both identities are sent, which the server refuses outright',
    catches: 'B9 no business key is anywhere',
    mutate: (t) => swap(t,
      "    const payload = { op: 'chain_replay', params: { row_ids: values.join(',') } };",
      "    const payload = { op: 'chain_replay', params: { row_ids: values.join(',') },\n"
      + "      businessKeys: values };") },
  { id: 'N13', what: 'every selection is called big, so the warning stops meaning anything',
    catches: 'W1 a selection under the threshold',
    mutate: (t) => swap(t, '    if (picked.length > this.warnAbove) {', '    if (picked.length >= 0) {') },
  { id: 'N14', what: 'the threshold is baked in rather than declared by the page',
    catches: 'W2 over it, ONE line',
    mutate: (t) => swap(t, '    if (picked.length > this.warnAbove) {',
      '    if (picked.length > 1000) {') },
  { id: 'N9', what: 'a rule that never said its tables is drawn with an arrow anyway',
    catches: 'B7 ... and with no tables, no arrow is invented',
    mutate: (t) => swap(t, '        const path = (rule && rule.trigger_table && rule.target_table)',
      '        const path = (rule)') },
];

// 🔴 대조군: 동작이 안 바뀌는 변경은 «아무것도 깨우면 안 됩니다». 안 그러면 이 채점기는
//    화면이 하는 일이 아니라 파일의 «모양»을 재고 있는 것입니다.
const LOADER_CONTROLS = [
  { id: 'C1', what: 'the empty-table guard is spelled out longhand',
    mutate: (t) => swap(t, '  if (!table) return null;',
      "  if (table === undefined || table === null || table === '') return null;") },
];
const BANNER_CONTROLS = [
  { id: 'C2', what: 'a local rename inside the row builder',
    mutate: (t) => swap(t, 'const path = (rule', 'const arrow = (rule')
      .split('${name}${path}').join('${name}${arrow}') },
];

const runLoader = async (m) => loaderSuite((await loadWithProbe(LOADER, { mutate: m.mutate })).module);
const runBanner = async (m) => bannerSuite((await loadWithProbe(BANNER, { mutate: m.mutate })).module);

const scoredA = await scoreMutants(LOADER_MUTANTS, runLoader,
  { baselineRan: baseA.ran, baselineNames: baseA.names,
    title: '\n  A mutants — each must be caught by the check it names.' });
const scoredB = await scoreMutants(BANNER_MUTANTS, runBanner,
  { baselineRan: baseB.ran, baselineNames: baseB.names,
    title: '\n  B mutants — each must be caught by the check it names.' });
const ctlA = await scoreMutants(LOADER_CONTROLS, runLoader,
  { mustCatch: false, baselineRan: baseA.ran, baselineNames: baseA.names,
    title: '\n  A controls — behaviour unchanged, so nothing may wake.' });
const ctlB = await scoreMutants(BANNER_CONTROLS, runBanner,
  { mustCatch: false, baselineRan: baseB.ran, baselineNames: baseB.names,
    title: '\n  B controls — behaviour unchanged, so nothing may wake.' });

ran += LOADER_MUTANTS.length + BANNER_MUTANTS.length
  + LOADER_CONTROLS.length + BANNER_CONTROLS.length;
failed += scoredA.wrong + scoredB.wrong + ctlA.wrong + ctlB.wrong;

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
