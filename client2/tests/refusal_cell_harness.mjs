/**
 * 🚪 S-39 — 「이 소스의 행이 왜 안 들어갔나」가 그 소스의 행에서 읽히나. 대상을 IMPORT 합니다.
 *
 * 🔴 이 하니스가 지키는 것은 «세 픽셀»입니다: 안 잼 / 쟀는데 0 / 쟀고 N. 가운데를 0 으로
 *    그리면 「없음」과 「안 잼」이 같아지고, 그 둘은 조작자에게 정반대의 지시입니다.
 *
 * Run:  node client2/tests/refusal_cell_harness.mjs [--mutate]
 */
import { loadWithProbe } from './lib/probe.mjs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src', 'refusal_cell.js');

let pass = 0;
const failures = [];
const ok = (name, cond, detail = '') => {
  if (cond) { pass += 1; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);


async function score(mutate) {
  pass = 0; failures.length = 0;
  const { probe } = await loadWithProbe(SRC, {
    expose: ['refusalSummary', 'excludedNote', 'refusalSamples'],
    mutate, tag: 'refusalcell',
  });
  // ⚰️ C-54. `refusalCell` 과 그 열여섯 단언이 «같이» 은퇴했습니다 — 그것이 읽던 라우트가
  //    404 이고, 대상이 없는 단언은 초록이어도 아무 말도 안 합니다. 남은 셋은 시험 실행
  //    화면이 «오늘 쓰는» 함수들이고, 아래 B·C 블록이 그것을 잽니다.
  //    ⚠️ 세 픽셀 규율(안 잼 / 쟀는데 0 / 쟀고 N)은 사라지지 않았습니다 — 그 규율을 지금
  //    지는 자리는 소스 상태 패널의 `refusals` 셋이고, 그 하니스가 잽니다.
  const S = probe.refusalSummary;
  const X = probe.excludedNote;

  // ══ C-39: 시험 실행 머리도 «같은 철자»를 쓴다 ═══════════════════════════════════════
  // 🔴 두 봉투의 «모양»이 다릅니다 — 문지기는 `{사유: {count, samples}}`, 시험 실행은
  //    `{사유: count}`. 문장은 «하나»여야 하고, 그것이 이 단언들의 전부입니다.
  eq('B1 시험 실행 모양(사유: 수)도 같은 문장을 낸다',
     '거절 11 · undeclared_event_type 9 · no_time_column 2',
     S({ no_time_column: 2, undeclared_event_type: 9 }));
  // ⚰️ C-54. B2 는 「두 화면의 문장이 글자까지 같다」를 쟀습니다. 둘째 화면이 은퇴해서 그
  //    단언의 «주어 한쪽»이 없어졌습니다 — 남겨 두면 자기와 자기를 비교하는 공허한 초록입니다.
  //    「사전 0」은 M3·M7 이 계속 잽니다(낱말이 응답의 키인가 · 두 번째 철자가 생기나).
  // 🔴 C-54. 이 단언은 «되살린» 것입니다. 0 인 사유가 마디를 안 만든다는 성질을 재던 곳은
  //    은퇴한 A-블록(A8)이었고, 그것이 사라지자 그 필터를 지우는 변이(M6)가 «초록으로»
  //    빠져나갔습니다 — 코드는 살아 있는데 재는 눈만 죽은 자리입니다. 살아 있는 함수 위에
  //    다시 답니다. 「이 사유로는 안 걸렸다」는 그릴 것이 아닙니다.
  eq('B0 0 인 사유는 마디를 만들지 않는다', '거절 3 · undeclared_event_type 3',
     S({ no_time_column: 0, undeclared_event_type: 3 }));
  eq('B3 셀 것이 없으면 아무 말도 안 한다', '', S({}));
  eq('B4 0 뿐이어도 같다', '', S({ no_time_column: 0 }));
  eq('B5 봉투가 없으면 조용하다', '', S(undefined));

  // ══ 제외 — 「키 없음」과 「0」이 다르다 ═════════════════════════════════════════════
  eq('B6 표지를 선언한 소스의 제외 행 수', '제외 4', X({ rows: 4 }));
  // 🔴 키가 «없으면» 안 잰 것입니다 — 0 을 그리면 「재 봤는데 없다」가 됩니다.
  eq('B7 키가 없으면 «아무것도» 안 그린다', '', X(undefined));
  eq('B8 0 도 그리지 않는다 — 그릴 것이 없다', '', X({ rows: 0 }));
  eq('B9 수가 아니면 조용하다', '', X({ rows: null }));

  // ══ C-49 표본 — 「몇 건」 옆에 「어느 행이」 ═════════════════════════════════════════
  // 🔴 픽스처는 «서버가 실제로 짓는 모양»입니다, 설명이 아니라. 값은
  //    `config_explorer_service.py:723` 이 `MoleculeRefusal`(reason·detail·rows·addresses)
  //    에서 조립하고, 주소는 `source_preparation.py:991` 이 짓는
  //    `event_frame.rows[N].<column>` 입니다.
  // 🔴 그리고 이 봉투에는 «절단 플래그가 없습니다» — backfill 의 `refused_samples_capped` 는
  //    «다른» 봉투의 것입니다. 그래서 절단은 «세어서» 압니다.
  const P = probe.refusalSamples;
  const sample = (over = {}) => ({
    reason: 'missing_occurred_at',
    detail: "molecule ('DTJ-1',) declares 'event_time' and the row at "
      + 'event_frame.rows[3].event_time leaves it empty',
    rows: 2,
    addresses: [{ code: 'source_preparation_incomplete',
                  path: 'event_frame.rows[3].event_time' }],
    ...over,
  });
  const RUN = { count: 2, reasons: { missing_occurred_at: 2 },
                samples: [sample(), sample({ reason: 'no_identity', rows: 1,
                  addresses: [{ code: 'source_preparation_incomplete',
                                path: 'event_frame.rows[7].dt_job' }] })] };

  eq('C1 한 표본이 한 행', 2, P(RUN).rows.length);
  eq('C2 사유는 응답의 낱말 그대로', 'missing_occurred_at', P(RUN).rows[0].reason);
  eq('C3 주소는 «서버가 준» 것이지 조립한 것이 아니다',
    'event_frame.rows[3].event_time', P(RUN).rows[0].path);
  eq('C4 둘째 행은 자기 주소를 갖는다 — 첫 행이 복제되지 않는다',
    'event_frame.rows[7].dt_job', P(RUN).rows[1].path);
  eq('C5 「행 N」은 이 분자가 덮은 소스 행 수', '2', P(RUN).rows[0].rows);
  // 🔴 문장은 «그대로». 분자 키가 그 안에 살고, 자르면 「어느 이벤트」가 사라집니다.
  eq('C6 문지기의 문장은 한 글자도 안 바뀐다', sample().detail, P(RUN).rows[0].detail);

  // ── 절단: 「20 이 전부」와 「20 까지만 봤다」는 «다른 답» ──────────────────────────
  const CAPPED = { ...RUN, count: 40 };
  ok('C7 count 가 표본보다 많으면 «잘린» 것이다', P(CAPPED).capped === true);
  eq('C8 ...그리고 그것을 «값으로» 말한다', '2 건까지', P(CAPPED).note);
  // 🔴 THE DISCRIMINANT: 같은 표본 둘인데 `count` 만 다릅니다. 절단을 표본 «수»로만 재면
  //    두 경우가 같은 픽셀이 되고, 그것이 이 칸이 있는 이유입니다.
  ok('C9 안 잘렸으면 아무 말도 안 한다', P(RUN).capped === false && P(RUN).note === '');
  // ⚠️ `count` 가 «없으면» 「안 물어봤다」입니다 — 잘렸다고도 아니라고도 말하지 않습니다.
  ok('C10 count 가 없으면 절단을 «주장하지» 않는다',
    P({ samples: [sample()] }).capped === false && P({ samples: [sample()] }).note === '');

  // ── 없는 것을 지어내지 않는다 ────────────────────────────────────────────────────
  eq('C11 표본이 없으면 행도 없다', 0, P({ count: 3, reasons: {}, samples: [] }).rows.length);
  eq('C12 주소가 없는 표본은 «빈 주소» — 문장에서 캐내지 않는다', '',
    P({ samples: [sample({ addresses: [] })] }).rows[0].path);
  // 🔴 「행」이 수가 아니면 «빈 칸»입니다. 0 으로 그리면 「세 봤더니 0행」이 됩니다.
  eq('C13 행 수가 수가 아니면 빈 칸이지 0 이 아니다', '',
    P({ samples: [sample({ rows: null })] }).rows[0].rows);
  eq('C14 봉투가 없어도 던지지 않는다', 0, P(undefined).rows.length);
  eq('C15 ...모양이 틀려도 같다', 0, P({ samples: 'nope' }).rows.length);

  return { pass, failures: failures.slice() };
}

const base = await score(undefined);
console.log(`\n${base.failures.length === 0 ? '✓' : '✗'} baseline: ${base.pass} passed, `
  + `${base.failures.length} failed`);
console.log(`ASSERTIONS ${base.pass + base.failures.length} ${base.failures.length}`);

const MUTATIONS = [
  // 🔴 RE-ANCHORED TWICE WHEN THE CODE MOVED (C-39), AND THE SECOND TIME IT MOVED THE CODE.
  //    The guard used to live in `refusalCell` as `total === 0`; the counting went into
  //    `refusalSummary`, so the first re-anchor pointed at an empty-string check there --
  //    which turned out to be EQUIVALENT (falling through produced the same value), so the
  //    guard was deleted from the subject rather than scored with a vacuous assertion. What
  //    actually decides 「measured zero draws nothing」 is the line below, and it is the one
  //    a mutant has to be able to reach.
  ['M1 a measured zero is drawn as 「거절 0」, so 「none」 and 「not measured」 look alike',
   s => s.replace("  if (total === 0) return '';", '')],
  ['M3 the reason words stop being the response keys',
   s => s.replace('.map(r => `${r.reason} ${r.count}`)', '.map(r => `사유 ${r.count}`)')],
  ['M6 a zero-count reason still takes a segment',
   s => s.replace('    .filter(r => r.count > 0)', '')],
  // C-39. 🔴 THE ONE MUTANT THAT MATTERS FOR "one spelling": give the test-run head its own
  //    word and the two screens start saying the same fact differently, with no error.
  ['M7 the test-run head grows a second spelling of 거절',
   s => s.replace('  return [`${MARK} ${total}`, ...named.map(r => `${r.reason} ${r.count}`)].join(\' · \');',
                  '  return [`refused ${total}`, ...named.map(r => `${r.reason} ${r.count}`)].join(\' · \');')],
  ['M8 an unmeasured exclusion is drawn as zero',
   s => s.replace('  if (!Number.isFinite(rows) || rows <= 0) return \'\';',
                  '  if (!Number.isFinite(rows)) return `${EXCLUDED_MARK} 0`;')],
  // ── C-49 ──────────────────────────────────────────────────────────────────────
  ['M9 truncation is never claimed, so 「20 까지만 봤다」 reads as 「20 이 전부」',
   s => s.replace('  const capped = isCount(src.count) && Number(src.count) > items.length;',
                  '  const capped = false;')],
  ['M10 ...and the other way: it is claimed on the sample count alone, so an untruncated '
   + 'run also says 「까지」',
   s => s.replace('  const capped = isCount(src.count) && Number(src.count) > items.length;',
                  '  const capped = items.length > 0;')],
  ['M11 the gatekeeper\'s sentence is clipped, so the molecule key inside it is lost',
   s => s.replace('        detail: s.detail == null ? \'\' : String(s.detail),',
                  '        detail: s.detail == null ? \'\' : String(s.detail).slice(0, 20),')],
  ['M12 every row takes the FIRST sample\'s address, so two refusals point at one row',
   s => s.replace('      const first = (Array.isArray(s.addresses) ? s.addresses : [])\n'
                  + '        .find(a => a && typeof a === \'object\') || {};',
                  '      const first = (Array.isArray(refused.samples[0].addresses)\n'
                  + '        ? refused.samples[0].addresses : []).find(a => a) || {};')],
  ['M13 a missing row count is drawn as 0, so 「안 셌다」 becomes 「0 행」',
   s => s.replace('        rows: isCount(s.rows) ? String(Number(s.rows)) : \'\',',
                  '        rows: String(Number(s.rows) || 0),')],
  ['M14 the address is composed from the sentence instead of read from the server',
   s => s.replace('        path: first.path == null ? \'\' : String(first.path),',
                  '        path: String(s.detail || \'\').slice(0, 12),')],
];

if (process.argv.includes('--mutate')) {
  console.log('\n── MUTATIONS (each must turn the harness RED) ──');
  let caught = 0; const green = [];
  for (const [name, apply] of MUTATIONS) {
    let r;
    try { r = await score(apply); }
    catch (e) { console.log(`  ~ ${name} -> harness THREW (${e && e.message})`); caught++; continue; }
    if (r.failures.length === 0) { console.log(`  ✗ ${name} -> STILL GREEN`); green.push(name); continue; }
    caught++;
    console.log(`  ✓ ${name} -> ${r.failures.length} failure(s): ${r.failures.sort().join(' ')}`);
  }
  console.log(`\nmutations: ${caught}/${MUTATIONS.length} caught (${MUTATIONS.length} declared)`);
  if (green.length) { console.log(`  ✗ undetected: ${green.join(' | ')}`); process.exit(1); }
}

process.exit(base.failures.length === 0 ? 0 : 1);
