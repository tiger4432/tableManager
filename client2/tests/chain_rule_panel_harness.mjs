// CHAIN RULE — 저장이 «장전»까지라는 사실이 화면에 있는지, 그리고 그것이 «세 상태»인지.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). No DOM and no CSS
// at module scope, so it imports in node as it stands.
//
// 🔴 THE TWO THIS FILE EXISTS FOR:
//   ① A SAVED RULE MAY NOT BE RUNNING. The server writes a NEW rule with `enabled: false`
//      because the loader re-reads on reload and a saved rule would otherwise arm and fire
//      at once. If the screen does not show that value, the operator reads "saved" as
//      "running" and hunts for a fault that is not there.
//   ② THREE STATES, NOT TWO. `true`, `false`, and NO KEY - the list response carries no
//      `enabled` at all. Drawing the absent one as `false` turns 「안 물어봤다」 into
//      「꺼져 있다」, which is the class this repository has closed four times.
//
// Run: node client2/tests/chain_rule_panel_harness.mjs
import {
  chainRuleView, ChainRulePanel, CHAIN_RULE_REGISTRY,
  MAPPER_GROUPS, mapperChoices, mapperNotes, splitMapper, joinMapper,
} from '../src/chain_rule_panel.js';
import { TABLE_REGISTRY } from '../src/table_config_panel.js';
import { ABSENT } from '../src/absent.js';

let pass = 0;
const failures = [];
function eq(name, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}\n        got  ${g}\n        want ${w}`); }
}
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name} ${detail}`); }
}

function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '', style: {}, children: [], attrs: Object.create(null), _text: '', value: '',
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    addEventListener(type, fn) { (this._on ||= {})[type] = fn; },
    get textContent() { return this._text + this.children.map(c => c.textContent).join(''); },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
  };
  return node;
}
const makeDoc = () => { const doc = { createElement: t => makeNode(doc, t) }; return doc; };
const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const byClass = (host, cls) => walk(host)
  .filter(n => String(n.className || '').split(/\s+/).includes(cls));
const byTag = (host, tag) => walk(host).filter(n => n.tagName === tag);

const PAYLOAD = {
  config_path: '/data/config/chain_rules.json',
  base: 'sha256:abc',
  rules: ['lot_to_wafer', 'wafer_to_die'],
  error: null,
  editable_unit: 'rule',
  name: 'lot_to_wafer',
  declaration: { trigger_table: 'lot_event' },
  raw: '{\n  "trigger_table": "lot_event"\n}',
  enabled: true,
};
const draw = (payload, opts = {}) => {
  const doc = makeDoc();
  const host = doc.createElement('div');
  const panel = new ChainRulePanel(host, { doc, ...(opts.deps || {}) });
  panel.render(payload, opts.render || {});
  return host;
};

// ═══ ① 저장은 «장전»까지 — 그 값이 화면에 있다 ═════════════════════════════════════
console.log('\n[1] a saved rule may not be a running rule');
{
  const on = draw(PAYLOAD);
  const state = (host) => byClass(host, 'chain-rule-state').map(n => n.textContent);
  eq('a running rule says so, in the server\'s word', state(on), ['enabled true']);

  const off = draw({ ...PAYLOAD, enabled: false });
  eq('...and one that is not, likewise', state(off), ['enabled false']);
  eq('the value rides as data, so a style can mark it',
    byClass(off, 'chain-rule-state')[0].getAttribute('data-state'), 'false');
  ok('the two are not the same pixel',
    byClass(on, 'chain-rule-state')[0].getAttribute('data-state')
    !== byClass(off, 'chain-rule-state')[0].getAttribute('data-state'));

  // 🔴 THE THIRD STATE. The list response has no `enabled`; drawing `false` there would
  //    say "switched off" about a question nobody asked.
  const { enabled, ...noKey } = PAYLOAD;
  eq('no key draws nothing at all', state(draw(noKey)), []);
  // and a non-boolean is not coerced
  eq('a non-boolean is not read as false', state(draw({ ...PAYLOAD, enabled: 'yes' })), []);

  // 🔴 AFTER A SAVE the answer is the fresher fact - a NEW rule comes back off.
  const saved = draw(PAYLOAD, { render: { saved: { name: 'new_rule', rules: 3,
                                                   backup: '/b', enabled: false, created: true } } });
  eq('the save answer wins over the payload', state(saved), ['enabled false']);
  ok('...and the save line is still drawn', byClass(saved, 'chain-rule-saved').length === 1);
}

// ═══ ② 거절은 서버의 낱말 ══════════════════════════════════════════════════════════
console.log('\n[2] the server\'s five refusals, none of them written here');
{
  for (const [code, path, message] of [
    ['rule_name_required', 'name', '저장할 규칙 이름이 없습니다'],
    ['stale_base', 'base', '이 파일이 열어 본 뒤에 바뀌었습니다. 다시 열어 확인한 뒤 저장하십시오'],
    ['chain_cycle', 'rules.lot_to_wafer', 'cycle detected'],
  ]) {
    const host = draw(PAYLOAD, { render: { refusal: { code, path, message } } });
    const box = byClass(host, 'chain-rule-refusal')[0];
    ok(`${code} keeps its code`, box && box.getAttribute('data-code') === code);
    ok(`${code} keeps its address`, box && box.textContent.includes(path));
    ok(`${code} keeps the server's sentence, verbatim`, box && box.textContent.includes(message));
  }
  const bare = draw(PAYLOAD, { render: { refusal: { message: 'x' } } });
  eq('a refusal with no code draws no code line', byClass(bare, 'chain-rule-refusal-code').length, 0);
  eq('no refusal, no box', byClass(draw(PAYLOAD), 'chain-rule-refusal').length, 0);
}

// ═══ ③ 고르기 · 지문 · 「못 읽음」 ═══════════════════════════════════════════════════
console.log('\n[3] the round trip, and unreadable is not empty');
{
  const doc = makeDoc();
  const host = doc.createElement('div');
  let sent = null, opened = null;
  const panel = new ChainRulePanel(host, { doc, onOpen: (n) => { opened = n; },
                                           onSave: (p) => { sent = p; } });
  panel.render(PAYLOAD);
  const root = byClass(host, 'chain-rule-panel')[0];
  eq('the fingerprint hangs where the save can read it', root.getAttribute('data-base'), 'sha256:abc');
  eq('...beside the rule it belongs to', root.getAttribute('data-name'), 'lot_to_wafer');
  byClass(host, 'chain-rule-save')[0]._on.click();
  eq('a save sends back the SAME fingerprint', sent && sent.base, 'sha256:abc');
  eq('...for the same rule, under the server\'s own key', sent && sent.name, 'lot_to_wafer');
  ok('...and the operator\'s text, not a re-serialisation', sent && sent.raw === PAYLOAD.raw);

  eq('every declared rule is offered', byTag(byClass(host, 'chain-rule-picker')[0], 'OPTION')
    .map(o => o.textContent), ['lot_to_wafer', 'wafer_to_die']);
  byClass(host, 'chain-rule-picker')[0]._on.change({ target: { value: 'wafer_to_die' } });
  eq('picking one asks for it by name', opened, 'wafer_to_die');
  eq('the count is the number offered', chainRuleView(PAYLOAD).count, '2');

  const broken = chainRuleView({ config_path: '/x', error: 'JSONDecodeError: line 3', rules: [] });
  eq('an unreadable file is not available', broken.available, false);
  eq('...and its count is a dash, not 0', broken.count, ABSENT);
  eq('a readable empty file IS available',
    chainRuleView({ config_path: '/x', error: null, rules: [] }).available, true);
  const dead = draw(null, { render: { unavailable: 'HTTP 401' } });
  ok('a failed fetch says so', /HTTP 401/.test(dead.textContent));
  eq('...and offers no picker', byClass(dead, 'chain-rule-picker').length, 0);
  eq('...and no save', byClass(dead, 'chain-rule-save').length, 0);
}

// ═══ ④ 템플릿이 «하나»인지 ═════════════════════════════════════════════════════════
//
// 🔴 이것이 「둘째를 손으로 그리지 않았다」의 시험입니다. 두 등록부가 «같은 부품»을 쓰고
//    다른 것은 «선언»뿐이어야 합니다 — 선언이 겹치면 한쪽이 남의 자리를 그립니다.
console.log('\n[4] two registries, one part');
{
  ok('the two declarations differ in every word',
    CHAIN_RULE_REGISTRY.listKey !== TABLE_REGISTRY.listKey
    && CHAIN_RULE_REGISTRY.nameKey !== TABLE_REGISTRY.nameKey
    && CHAIN_RULE_REGISTRY.cls !== TABLE_REGISTRY.cls);
  // ⚠️ 전에는 「이쪽만 자기 상태를 든다」였습니다. 표 등록도 자기 것을 갖게 되면서
  //    그 문장이 «거짓»이 됐고, 지키려던 것은 「둘이 «같은 것»을 안 그린다」였습니다.
  //    그래서 재는 것을 «다른 함수인가»로 바꿉니다 — 같은 함수를 나눠 쓰면 한쪽이
  //    남의 상태를 그립니다.
  ok('each registry brings its own state, and not the same one',
    typeof CHAIN_RULE_REGISTRY.extra === 'function'
    && typeof TABLE_REGISTRY.extra === 'function'
    && CHAIN_RULE_REGISTRY.extra !== TABLE_REGISTRY.extra);
  // 조립식: 같은 화면에 둘을 놓아도 서로를 안 건드린다
  const doc = makeDoc();
  const h1 = doc.createElement('div'), h2 = doc.createElement('div');
  new ChainRulePanel(h1, { doc }).render(PAYLOAD);
  new ChainRulePanel(h2, { doc }).render({ ...PAYLOAD, name: 'wafer_to_die', base: 'sha256:zzz' });
  eq('the first keeps its own fingerprint',
    byClass(h1, 'chain-rule-panel')[0].getAttribute('data-base'), 'sha256:abc');
  eq('the second keeps its own',
    byClass(h2, 'chain-rule-panel')[0].getAttribute('data-base'), 'sha256:zzz');
  const p3 = new ChainRulePanel(h1.children[0] ? doc.createElement('div') : h1, { doc });
  p3.render(PAYLOAD); p3.render(PAYLOAD);
  ok('a re-render replaces rather than appends',
    byClass(p3.root, 'chain-rule-save').length === 1);
}

// ═══ ⑤ 맵퍼 후보 — 두 묶음, 그리고 두 철자 사이의 번역 (C-101 ③) ═══════════════════
// 🔴 소유자 2026-09-13: 「테이블이랑 맵퍼 설정은 리스트 좀 나오게해」 + 「내 파일이 왜 안 보이지」.
//    실측이 그 원인이었다: 드롭다운이 `registered`(데코레이터가 등록한 이름)«만» 읽고, 같은
//    응답의 `data`(파일별 def 목록)는 «안 읽었다». 소유자의 맵퍼는 `BaseMapper` 상속이라
//    등록부에 없다 — 그래서 화면이 「선택지 없음」이라고 «참이 아닌 것»을 말했다.
console.log('\n[5] the mapper candidates, and the translation between the two spellings');
{
  const BODY = {
    registered: ['build_dt_map'],
    data: [{ filename: 'lot.py', module_name: 'mappers.lot',
             functions: [{ name: 'build_rows' }, { name: 'helper' }] }],
  };
  const got = mapperChoices(BODY);
  // ⚠️ C-106 ⑦ 이 이 단언을 «뒤집었습니다». 종전에는 파일 함수가 「파일 함수」 한 묶음이었고,
  //    소유자가 「파일별 묶음, 항목은 함수 이름만」을 골랐습니다 — 목록이 길어지면 항목마다
  //    같은 모듈 접두가 반복되고 그 반복이 「내 파일이 어디 있나」를 다시 가립니다.
  eq('a registered name and a file function are different groups',
    got.map((c) => [c.value, c.group]),
    [['build_dt_map', MAPPER_GROUPS.registered],
     ['mappers.lot:build_rows', 'mappers.lot'],
     ['mappers.lot:helper', 'mappers.lot']]);
  ok('a file function is shown by its FUNCTION name, and the file is the group',
    got[1].label === 'build_rows');
  eq('an unread answer is 「모름」, not 「없음」', mapperChoices(null), null);
  eq('an answer with neither cell is 「없음」', mapperChoices({}), []);
  // 🔴 S-223 이 오면 `candidates` 가 «이깁니다» — 그때 위 다리는 지워지고, 그 전에도 두 읽기가
  //    «같은 모양»을 냅니다(한 push 를 지나므로).
  const AFTER = { registered: ['ignored'], data: [{ module_name: 'm', functions: [{ name: 'x' }] }],
                  candidates: [{ module: 'mappers.a', name: 'run', kind: 'registered' },
                               { module: 'mappers.a', name: 'inner', kind: 'function' }] };
  eq('when the server names candidates, that is the list',
    mapperChoices(AFTER).map((c) => c.value), ['run', 'mappers.a:inner']);
  // ── C-106 ⑤: 선언된 파라미터가 «고르면 따라옵니다» ──────────────────────────────
  // 🔴 세 상태입니다. `params` 가 목록이면 그 행들을 채우고, `null` 이면 «안 물어본» 것이라
  //    아무것도 안 채우며(오늘 그대로), 빈 목록이면 「읽었고 없다」라 역시 채울 것이 없습니다.
  const DECLARED = { candidates: [
    { module: 'm', name: 'withParams', kind: 'registered', params: ['retry', 'batch'] },
    { module: 'm', name: 'unknownParams', kind: 'registered', params: null },
    { module: 'm', name: 'noParams', kind: 'registered', params: [] }] };
  const picked = mapperChoices(DECLARED);
  eq('a candidate that declares parameters carries the cells to write',
    picked[0].fill, { 'params.retry': '', 'params.batch': '' });
  eq('one that declares NOTHING KNOWN carries none -- 「not asked」 is not 「none」',
    picked[1].fill, undefined);
  eq('...and one that was read and has none carries none either', picked[2].fill, undefined);
  // ── 고른 것이 어느 칸들에 적히나 ───────────────────────────────────────────────
  eq('a registered name writes its own cell only', splitMapper('build_dt_map'), null);
  eq('a file function writes the two cells and CLEARS the one',
    splitMapper('mappers.lot:build_rows'),
    { mapper: null, mapper_module: 'mappers.lot', mapper_function: 'build_rows' });
  eq('a token with nothing after the mark is not one', splitMapper('mappers.lot:'), null);
  eq('...nor one with nothing before it', splitMapper(':build_rows'), null);
  eq('nothing chosen writes nothing special', splitMapper(''), null);
  // ── 문서가 든 것을 고르개의 값으로 ─────────────────────────────────────────────
  eq('the one cell is read as itself', joinMapper({ mapper: 'build_dt_map' }), 'build_dt_map');
  eq('the two cells are read back as the token',
    joinMapper({ mapper_module: 'mappers.lot', mapper_function: 'build_rows' }),
    'mappers.lot:build_rows');
  eq('half of the two-cell spelling is not a mapper',
    joinMapper({ mapper_module: 'mappers.lot' }), '');
  eq('a rule that names none reads as none', joinMapper({}), '');
  ok('the one cell wins when a rule carries both',
    joinMapper({ mapper: 'one', mapper_module: 'm', mapper_function: 'f' }) === 'one');
  // ── 목록 «밖»의 줄들 ───────────────────────────────────────────────────────────
  eq('no such cells means no lines -- 「못 읽음」 is not 「없음」', mapperNotes({}), []);
  eq('a module that is here but not for chains gets one line, in the server\'s words',
    mapperNotes({ other: [{ module: 'mappers.rf', kind: 'ledger_roleframe', why: 'not a chain mapper' }] }),
    [{ kind: 'other', text: 'mappers.rf · not a chain mapper' }]);
  eq('...and one that would not import says why',
    mapperNotes({ refused: [{ module: 'mappers.x', why: 'ImportError: no pandas' }] }),
    [{ kind: 'refused', text: 'mappers.x · ImportError: no pandas' }]);
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
