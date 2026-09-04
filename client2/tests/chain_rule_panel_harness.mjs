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
import { chainRuleView, ChainRulePanel, CHAIN_RULE_REGISTRY } from '../src/chain_rule_panel.js';
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
  ok('only this one carries a state of its own',
    typeof CHAIN_RULE_REGISTRY.extra === 'function' && !TABLE_REGISTRY.extra);
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

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
