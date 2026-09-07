// S-7 ① — 「왜 느린가」가 화면에 닿나, 그리고 그것을 «한 독자»가 답하나.
//
// 🔴 서버가 문장을 «다 만들어» 보내는데(`value_suggest.py` 의 `slow_reason`) 읽는 자리가
//    «0» 이었습니다. 등급 2 — 화면이 거짓을 말하는 게 아니라, 문장이 화면 «앞»에 놓여 있습니다.
// 🔴 재는 것은 «가름»입니다. 그리고 세 상태를 «합치지 않는지**도 잽니다 —
//    키 없음(안 잼) · null(쟀고 안 느림) · 문장(느림). 오늘 앞의 둘은 둘 다 침묵이지만
//    «같은 뜻이 아니라서**, 합치면 서버가 그 둘을 가르는 날 화면이 영영 못 받습니다.
//
// Run: node client2/tests/slow_reason_harness.mjs
import { slowReasonNote } from '../src/slow_reason.js';
import { decodeReferenceView } from '../src/map2/decode.js';
import { adaptPayload } from '../src/map2/main.js';
import { buildViewModel } from '../src/map2/view_model.js';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';

let pass = 0, fail = 0;
const failed = [];
function ok(cond, name) {
  if (cond) { pass++; console.log(`  OK   ${name}`); }
  else { fail++; failed.push(name); console.log(`  BAD  ${name}`); }
}
const call = (fn) => { try { return fn(); } catch (e) { return `<<threw: ${e && e.message}>>`; } };

const SENTENCE = '응답이 1200ms 걸렸습니다 (예산 400ms) — 열을 좁혀 다시 물으십시오';

console.log('-- the four states, and none of them folded ---------------------------');
const st = (o) => call(() => slowReasonNote(o)).state;
ok(st({}) === 'unmeasured', 'A1 no key at all — this route does not say (안 잼)');
ok(st({ slow_reason: null }) === 'not_slow', 'A2 an explicit null — measured, and NOT slow');
ok(st({ slow_reason: SENTENCE }) === 'slow', 'A3 a sentence — measured, and slow');
// 🔴 THE ONE THAT MUST NOT COLLAPSE. Both draw nothing today; they are still different facts.
ok(st({}) !== st({ slow_reason: null }),
  'A4 「not measured」 and 「measured, not slow」 stay DIFFERENT, though both are silent today');
ok(slowReasonNote({}).text === '' && slowReasonNote({ slow_reason: null }).text === '',
  'A5 ...and both really are silent — the split is in the name, not in pixels');
// 실렸는데 문장이 아닌 것은 「안 느림」이 아닙니다 — 잰 것은 맞습니다.
ok(st({ slow_reason: 42 }) === 'unreadable',
  'A6 a present NON-STRING is neither measured-not-slow nor a sentence');
// 🔴 SPLIT FROM A6. Two different mutants (calling an unreadable value 「not slow」, and
//    drawing an empty string as a sentence) reddened the SAME single assertion, which
//    means one assertion was standing in for two properties.
ok(st({ slow_reason: '  ' }) === 'unreadable',
  'A6b ...and neither is a string with nothing in it');
ok(slowReasonNote({ slow_reason: 42 }).text === '',
  'A7 ...and it draws nothing rather than printing a number as a sentence');
ok(st(null) === 'unmeasured' && st('x') === 'unmeasured', 'A8 no body — nothing, and no throw');

console.log('\n-- the sentence is the SERVER\'S, verbatim ----------------------------');
ok(slowReasonNote({ slow_reason: SENTENCE }).text === SENTENCE,
  'B1 the sentence is passed through unchanged — not trimmed, prefixed or shortened');
const other = '다른 서버 문장';
ok(slowReasonNote({ slow_reason: other }).text === other,
  'B2 ...whatever it says — this client does not choose the words');

console.log('\n-- 🔴 and the client writes NO copy of that sentence ------------------');
// 게이트 ②. 문구 리터럴이 클라에 있으면 서버가 임계를 바꾸는 날 «두 문장»이 됩니다.
{
  const SRC = path.join(path.dirname(new URL(import.meta.url).pathname).replace(/^\//, ''), '..', 'src');
  const files = [];
  const walk = (d) => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      if (e.isDirectory()) walk(path.join(d, e.name));
      else if (e.name.endsWith('.js')) files.push(path.join(d, e.name));
    }
  };
  call(() => walk(SRC));
  ok(files.length > 50, `C0 CONTROL: the sweep saw the source tree (${files.length} files)`);
  // 🔴 COMMENTS ARE STRIPPED FIRST. A comment quoting the server's sentence cannot become a
  //    second author — only a RENDERED literal can — and the first version of this assertion
  //    reddened on my own explanatory comment, which is the check measuring the wrong thing.
  const LINE_COMMENT = new RegExp('(^|[^:])//[^' + String.fromCharCode(10) + ']*', 'g');
  const stripped = (src) => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(LINE_COMMENT, '$1');
  const guilty = files.filter((f) => {
    const s = stripped(readFileSync(f, 'utf8'));
    return s.includes('예산 ') && s.includes('걸렸습니다');
  });
  ok(guilty.length === 0,
    `C1 no client file writes the server's slow sentence itself (${guilty.map((g) => path.basename(g)).join(', ')})`);
}

console.log('\n-- the map2 path: carried, adapted, drawn -----------------------------');
const walkOf = (stats) => call(() => decodeReferenceView({ sources: { cells: [], maps: [] }, stats }).counts);
ok(walkOf({ elapsed_ms: 12, slow_reason: SENTENCE }).slowReason.state === 'slow',
  'D1 decode carries the judgement, not the raw field');
ok(walkOf({ elapsed_ms: 12 }).slowReason.state === 'unmeasured',
  'D2 ...and today, with no such key, it carries 「not measured」');
// 🔴 BEHAVIOURAL, NOT BY NAME: a copy of the reader would pass a name check and still drift.
for (const stats of [{ slow_reason: SENTENCE }, { slow_reason: null }, {}, { slow_reason: 7 }]) {
  const mine = slowReasonNote(stats);
  const theirs = walkOf({ elapsed_ms: 1, ...stats }).slowReason;
  ok(theirs.state === mine.state && theirs.text === mine.text,
    `D3 decode agrees with the one reader on ${JSON.stringify(stats)}`);
}

const adapted = (stats) => call(() => adaptPayload({
  reference: { cells: [] }, sources: { cells: [[0, 0]], maps: [] }, stats,
}));
// 🔴 TOTAL. A dropped field made this THROW and killed every assertion after it, so the
//    mutant that dropped it looked identical to one that changed nothing.
const adaptedState = (st) => { const r = adapted(st); return (r && r.slow_reason && r.slow_reason.state) || '<<none>>'; };
ok(adaptedState({ elapsed_ms: 9, slow_reason: SENTENCE }) === 'slow',
  'E1 the adapter carries it onto the row the screen reads');
ok(adaptedState({ elapsed_ms: 9 }) === 'unmeasured',
  'E2 ...and carries 「not measured」 when the key is absent');

console.log('\n-- the drawn line ----------------------------------------------------');
const meta = (stats) => {
  const vm = call(() => buildViewModel({ session: { payload: adapted(stats) } }));
  return (vm && vm.meta) || '';
};
ok(meta({ elapsed_ms: 9, slow_reason: SENTENCE }).includes(SENTENCE),
  'F1 a slow answer puts the SERVER\'S sentence on the meta line');
ok(!meta({ elapsed_ms: 9, slow_reason: null }).includes('예산'),
  'F2 a measured-but-not-slow answer says nothing about being slow');
// 🔴 무회귀: 오늘의 응답(키 없음)은 «글자 그대로» 같아야 합니다.
ok(meta({ elapsed_ms: 9 }) === meta({ elapsed_ms: 9, slow_reason: null }),
  'F3 today\'s payload and a not-slow one render IDENTICALLY — this round only ADDS');
ok(meta({ elapsed_ms: 9 }).includes('9ms'),
  'F4 CONTROL: the elapsed time is still drawn, so F2/F3 are not passing on an empty line');
ok(meta({ elapsed_ms: 9, slow_reason: SENTENCE }) !== meta({ elapsed_ms: 9 }),
  'F5 slow and not-slow are DIFFERENT pixels, which is the round');
// 🔴 F6 EXISTS BECAUSE F2/F3 DID NOT DO WHAT THEY CLAIMED. Drawing on EVERY state pushes
//    the empty text, which adds a trailing separator rather than a word — F3 still saw two
//    identical strings and F2 still saw no 예산. An empty segment is a visible defect.
for (const st of [{ elapsed_ms: 9 }, { elapsed_ms: 9, slow_reason: null }, { elapsed_ms: 9, slow_reason: 42 }]) {
  const line = meta(st);
  ok(!line.endsWith(' · ') && !line.endsWith(' ·') && !line.includes('· ·'),
    `F6 a silent state adds NOTHING, not an empty segment: ${JSON.stringify(line)}`);
}

console.log(`\n${pass} passed, ${fail} failed.`);
if (fail) console.error(`failed:\n  ${failed.join('\n  ')}`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
process.exit(fail ? 1 : 0);
