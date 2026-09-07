// C-1 «화면 절반» — 「이 규칙이 «꺼져서» 안 돌았다」와 「돌았는데 바꿀 게 없었다」가 갈리나.
//
// 🔴 대상을 «import 합니다». 판정이 `admin.js` 안에 있으면 `tokens.css` 때문에 node 가 못 읽고,
//    그러면 이 판정을 재려고 화면을 통째로 세워야 합니다 — 그것이 이 모듈이 따로 있는 사유입니다.
// 🔴 재는 것은 «문구»가 아니라 «가름»입니다. 그리고 «배지 이름»도 잽니다 — 스타일시트에 없는
//    이름을 고르면 「그렸다」고 적어 두고 화면엔 아무 강조도 안 붙습니다.
//
// Run: node client2/tests/rule_outcome_harness.mjs
import { ruleOutcomeView } from '../src/rule_outcome.js';

let pass = 0, fail = 0;
const failed = [];
function ok(cond, name) {
  if (cond) { pass++; console.log(`  OK   ${name}`); }
  else { fail++; failed.push(name); console.log(`  BAD  ${name}`); }
}
// 🔴 던짐을 «값»으로 기록합니다 — 던지면 뒤 단언이 한 번도 안 돌고, 그러면 서로 다른 결함이
//    같은 답으로 보입니다. 오늘 세 번 겪은 부류입니다.
function view(entry) {
  try { return ruleOutcomeView(entry); }
  catch (e) { return { read: `<<threw: ${e && e.message}>>`, outcome: '', badge: '', reason: '', age: null }; }
}

// `server/event_constants.py` 의 닫힌 여섯. 여기 다시 적는 것이 아니라 «인용»입니다 —
// 서버가 값을 하나 더하면 이 목록과 어긋나고, 그 어긋남을 B5 가 잡습니다.
const SIX = ['skipped:disabled', 'skipped:not_triggered', 'ran:unchanged',
             'ran:changed', 'failed', 'never_evaluated'];
// `client2/admin.html` 이 «실제로 정의하는» 배지 넷 (실측).
const STYLED = new Set(['badge-danger', 'badge-warning', 'badge-success', 'badge-muted']);
const at = (outcome, extra = {}) => view({ last_outcome: outcome, ...extra });

console.log('-- the round\'s sentence ----------------------------------------------');
// 🔴 ㉠ THE GATE'S OWN SAMPLE: 「꺼져서 안 돌았다」와 「돌았는데 0」.
const disabled = at('skipped:disabled');
const unchanged = at('ran:unchanged');
ok(disabled.outcome !== unchanged.outcome, 'A1 disabled and ran:unchanged carry different words');
ok(disabled.badge !== unchanged.badge, 'A2 ...and different emphasis, so they differ at a glance');
ok(disabled.read === true && unchanged.read === true,
  'A3 CONTROL: both were READ — A1/A2 are a decision, not a parse failure');
// 🔴 운영자가 «고칠 수 있는» 것은 하나뿐이고, 그것이 보여야 합니다.
ok(disabled.badge === 'badge-warning',
  'A4 the one outcome in the operator\'s hands is the one marked as actionable');
ok(at('failed').badge === 'badge-danger', 'A5 ...and the only error is the only danger');
ok(at('ran:changed').badge !== at('ran:unchanged').badge,
  'A6 ran:changed and ran:unchanged are different shapes (the order\'s words)');

console.log('\n-- the vocabulary is the server\'s, and nothing is invented ------------');
ok(SIX.every(o => at(o).outcome === o),
  'B1 every one of the six is printed VERBATIM — no Korean synonym, no second spelling');
// ⛔ `ran:changed` 의 사실은 「행을 냈다」이지 「바꿨다」가 아닙니다.
ok(!at('ran:changed').outcome.includes('바꿈') && !at('ran:changed').outcome.includes('변경'),
  'B2 ran:changed is NOT called 「바꿈」 — the server only knows the mapper produced rows');
ok(SIX.every(o => STYLED.has(at(o).badge)),
  'B3 every badge name is one the stylesheet actually defines (an unstyled class draws nothing)');
ok(at('failed', { last_reason: 'mapper raised ValueError' }).reason === 'mapper raised ValueError',
  'B4 the server\'s reason is carried verbatim');
// 🔴 A SEVENTH VALUE IS DRAWN, BUT NOT GRADED. Swallowing it would hide a real outcome;
//    inventing a severity for it would be a claim the client cannot make.
const seventh = at('ran:partially_something');
ok(seventh.read === true && seventh.outcome === 'ran:partially_something',
  'B5 an unknown seventh value is still SHOWN — the token itself cannot be false');
ok(seventh.badge === 'badge-muted',
  'B6 ...but carries no severity, because grading it would be the invented part');

console.log('\n-- absence means exactly one thing ------------------------------------');
// 🔴 게이트 ⑤: `never_evaluated`(값)와 «키 없음»(옛 서버)이 다르게.
ok(at('never_evaluated').read === true && at('never_evaluated').outcome === 'never_evaluated',
  'C1 never_evaluated is a VALUE — this process has not seen the rule yet');
ok(view(undefined).read === false, 'C2 ...and a missing entry draws nothing (older server)');
ok(at('never_evaluated').read !== view(undefined).read,
  'C3 the two are therefore distinguishable, which is gate ⑤');
ok(view(null).read === false && view({}).read === false,
  'C4 null and an empty object draw nothing rather than a blank badge');
ok(view({ last_outcome: '   ' }).read === false,
  'C5 whitespace is not an outcome');
ok(view({ last_outcome: 42 }).read === false,
  'C6 a non-string outcome draws nothing rather than being stringified into a fake token');

console.log('\n-- numbers are the server\'s, or absent --------------------------------');
ok(at('ran:changed', { last_age_seconds: 90 }).age === 90, 'D1 the age is carried as given');
ok(at('ran:changed').age === null, 'D2 a missing age is null — never 0, which means 「방금」');
ok(at('ran:changed', { last_age_seconds: null }).age === null, 'D3 ...and an explicit null too');
ok(at('ran:changed', { last_age_seconds: '5' }).age === null,
  'D4 a string is not a number — it is not coerced into one');
ok(at('ran:changed').reason === '', 'D5 a missing reason is empty, not the word 「없음」');
// 🔴 이 칸은 «성공에도» 옵니다 — 그래서 「있나」가 아니라 «값»을 단언합니다 (게이트 ④).
ok(at('ran:unchanged').read === true && at('ran:unchanged').outcome === 'ran:unchanged',
  'D6 a SUCCESSFUL run still carries the field, so the assertion is on the value');

console.log(`\n${pass} passed, ${fail} failed.`);
if (fail) console.error(`failed:\n  ${failed.join('\n  ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail ? 1 : 0);
