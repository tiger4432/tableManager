// C-116 — 토스트가 화면을 덮는 «기제»를 잽니다.
// Run: node client2/tests/toast_stack_harness.mjs [--json]
//
// 소유자 물음: 「토스트 이중 이거 UI 가리는 경우 있는데」.
// 총괄이 브라우저에서 잰 것(2026-09-16): 실패 넷이 640×278px = 뷰포트 «높이의 31%» 를 15초 동안
// 덮습니다. 그 「이중」의 기제는 «우연이 아니라 설계»였습니다 — `utils.js` 가 실패를 동종 집계에서
// 빼 두었고(주석: 「개별 사유가 중요하므로」), 그래서 실패만 «접히지 않고» 상한 4 까지 쌓입니다.
//
// 🔴 이 하니스가 단언하는 것은 그 판단을 «지키면서» 쌓임을 줄였다는 것입니다:
//    사유는 «문장»이다 -> 문장이 «글자 그대로 같으면» 다른 사유가 아니다 -> 그때만 접는다.
//    그러므로 「다른 문장은 그대로 쌓인다」가 이 파일에서 제일 중요한 단언입니다. 그것이 빠지면
//    이 변경은 「사유를 지웠다」가 되고, 그건 고친 것이 아니라 «판정을 뒤집은» 것입니다.
//
// ⚠️ 여기서 «못 재는 것» — 상자의 «폭»과 «클릭을 먹는가»는 CSS 이고, 렌더돼야만 존재합니다.
//    그 둘은 브라우저에서 잽니다(보고서에 수치). 하니스로 갈음하지 «않습니다».
//
// 잘라쓰기 없음: `utils.js` 를 import 합니다(하니스 셋이 이미 그렇게 합니다).
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const UTILS = path.join(HERE, '..', 'src', 'utils.js');

// 🔴 `utils.js` 는 모듈 최상단에서 `document`/`window` 를 «가드와 함께» 읽습니다. 로드 «전»에
//    심어 두지 않으면 그 훅이 안 걸리고, 그러면 스윕의 한쪽 경로를 아무도 안 재게 됩니다.
globalThis.document = makeDoc('light');
globalThis.window = { addEventListener() {} };

let ran = 0;
let failed = 0;

function say(s, name, ok, got) {
  s.names.push(name);
  if (ok) return;
  s.failures.push(`${name} — ${JSON.stringify(got)}`);
}

// 한 장면이 끝나면 «둘 다» 비웁니다 — 모듈의 목록과 화면의 컨테이너.
// 하나만 비우면 다음 장면이 「접혔다」를 «앞 장면의 잔해»로 볼 수 있습니다.
function reset(probe) {
  probe.toastItems.splice(0);
  globalThis.document = makeDoc('light');
}

const toasts = () => {
  const c = globalThis.document.getElementById('toast-container');
  return c ? c.children.slice() : [];
};
const textsOf = () => toasts().map((n) => n.textContent);

function suite(mod, probe) {
  const s = { names: [], failures: [] };
  const { showToast, dismissToasts } = mod;

  // ══ T1 «같은 문장»은 접힌다 — 그것이 소유자가 본 「이중」이다 ═══════════════════════
  reset(probe);
  const SAME = '체인 규칙 inventory_confirmed 거절: right_table 이 카탈로그에 없습니다.';
  showToast(SAME, 'error');
  showToast(SAME, 'error');
  say(s, 'T1 the same failure sentence twice is ONE toast', toasts().length === 1, textsOf());
  say(s, 'T1b ... and it says how many', /·\s*2건/.test(textsOf()[0] || ''), textsOf());

  // ══ T2 «다른 문장»은 접히지 않는다 — 판정 「개별 사유가 중요하다」를 지키는 자리 ════
  reset(probe);
  showToast('row_id 가 없습니다.', 'error');
  showToast('토큰이 만료되었습니다.', 'error');
  say(s, 'T2 two DIFFERENT failure sentences stay two toasts', toasts().length === 2, textsOf());
  say(s, 'T2b ... and neither is drawn as a count',
    textsOf().every((t) => !/건/.test(t)), textsOf());

  // ══ T3 호출자의 dedupeKey 로는 실패를 묶지 않는다 ═════════════════════════════════
  // 🔴 그 키는 서로 «다른 문장»을 한 덩이로 묶을 수 있습니다. 묶이면 운영자는 둘째 사유를
  //    «영영 못 봅니다» — 화면에 오류도 안 납니다. 그래서 여기가 이 변경의 안전판입니다.
  reset(probe);
  showToast('첫째 사유', 'error', { dedupeKey: 'chain' });
  showToast('둘째 사유', 'error', { dedupeKey: 'chain' });
  say(s, 'T3 one dedupeKey does NOT merge two different failure sentences',
    toasts().length === 2, textsOf());

  // ══ T4 실패가 아닌 것은 오늘 그대로 — dedupeKey 로 접힌다 ═════════════════════════
  reset(probe);
  showToast('파일 3 처리 완료', 'success', { dedupeKey: 'done' });
  showToast('파일 4 처리 완료', 'success', { dedupeKey: 'done' });
  say(s, 'T4 a non-failure still folds on its dedupeKey', toasts().length === 1, textsOf());
  say(s, 'T4b ... and shows the latest message with the count',
    /파일 4 처리 완료 ·\s*2건/.test(textsOf()[0] || ''), textsOf());

  // ══ T5 `dismissToasts(key)` 가 실패에도 여전히 닿는다 ════════════════════════════
  // 🔴 접기 키를 «저장된 dedupeKey 위에» 덮어썼다면 이 줄이 빨개집니다. 그 둘은 다른 일을
  //    합니다 — 하나는 「접을 것인가」, 하나는 「거둘 것인가」.
  reset(probe);
  showToast('붙여넣기를 누르십시오', 'error', { dedupeKey: 'paste-hint' });
  const before = probe.toastItems.length;
  dismissToasts('paste-hint');
  // ⚠️ 목록에서는 «즉시» 빠지고 화면에서는 400ms 뒤에 빠집니다(페이드 아웃).
  //    그래서 «거두어졌나»는 목록으로 재고, DOM 으로 재면 언제나 1 이 나옵니다.
  say(s, 'T5 dismissToasts still retracts a failure that carried that key',
    before === 1 && probe.toastItems.length === 0, [before, probe.toastItems.length]);

  // ══ T7 닫는 일은 «닫기 단추»가 한다 — 본체가 클릭을 «가져가지» 않는다 ════════════
  // 🔴 전에는 토스트 «전체»가 click 으로 닫혔습니다. 그러면 그 밑 버튼을 겨냥한 클릭을
  //    토스트가 삼킵니다(실측: 어드민의 「탭 열기 →」). 본체의 `pointer-events: none` 은
  //    CSS 라 여기서 못 재지만, 「본체에 click 핸들러가 «없다»」와 「× 가 닫는다」는 잽니다.
  reset(probe);
  showToast('닫아 보십시오', 'error');
  const only = toasts()[0];
  const closer = only.children.find((n) => n.className === 'toast-close');
  say(s, 'T7 a toast carries a close control', Boolean(closer),
    only.children.map((n) => n.className).join(','));
  say(s, 'T7b ... and the BODY no longer listens for a click of its own',
    !(only.listeners && only.listeners.click), Object.keys(only.listeners || {}));
  if (closer && closer.listeners.click) closer.listeners.click.forEach((fn) => fn());
  say(s, 'T7c ... and pressing it retracts that toast', probe.toastItems.length === 0,
    probe.toastItems.length);

  // ══ T6 접기는 상한을 바꾸지 않는다 — 다른 사유 넷은 여전히 넷이다 ════════════════
  reset(probe);
  ['가', '나', '다', '라'].forEach((m) => showToast(`사유 ${m}`, 'error'));
  say(s, 'T6 four different reasons are still four toasts (folding changed no cap)',
    toasts().length === 4, textsOf().length);

  return { ran: s.names.length, names: s.names, failures: s.failures };
}

// ── 채점 ────────────────────────────────────────────────────────────────────────────────
const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 70)}`);
  return text.split(from).join(to);
};

const load = async (mutate) => loadWithProbe(UTILS, {
  expose: ['toastItems'], mutate, tag: 'toast',
});

console.log('\n[T] failures fold only when the sentence is the same one');
const base = await load(undefined);
const baseline = suite(base.module, base.probe);
ran += baseline.ran;
failed += baseline.failures.length;
for (const f of baseline.failures) console.log(`  ✗ ${f}`);
if (!baseline.failures.length) console.log(`  ✓ ${baseline.ran} assertions`);

const MUTANTS = [
  { id: 'M1', what: 'failures are put back outside folding, so a run of the same one stacks again',
    catches: 'T1 the same failure sentence twice is ONE toast',
    mutate: (t) => swap(t, "const foldKey = type === 'error' ? `msg:${text}`",
      "const foldKey = type === 'error' ? null") },
  { id: 'M2', what: 'failures fold on the CALLER’s key, so two different reasons become one',
    catches: 'T3 one dedupeKey does NOT merge two different failure sentences',
    mutate: (t) => swap(t, "const foldKey = type === 'error' ? `msg:${text}` : (opts.dedupeKey || null);",
      'const foldKey = opts.dedupeKey || null;') },
  { id: 'M3', what: 'the fold happens but the count never rises, so two look like one',
    catches: 'T1b ... and it says how many',
    mutate: (t) => swap(t, '      hit.count += 1;', '      hit.count += 0;') },
  { id: 'M4', what: 'everything folds by its text, so two different successes collapse',
    catches: 'T4 a non-failure still folds on its dedupeKey',
    mutate: (t) => swap(t, "const foldKey = type === 'error' ? `msg:${text}` : (opts.dedupeKey || null);",
      'const foldKey = `msg:${text}`;') },
  { id: 'M5', what: 'the key is computed but never stored, so nothing ever folds',
    catches: 'T1 the same failure sentence twice is ONE toast',
    mutate: (t) => swap(t, '    foldKey,\n', '    foldKey: null,\n') },
  { id: 'M6', what: 'the fold key overwrites the dedupe key, so retraction stops finding it',
    catches: 'T5 dismissToasts still retracts a failure that carried that key',
    mutate: (t) => swap(t, '    dedupeKey: opts.dedupeKey || null,\n    foldKey,',
      '    dedupeKey: foldKey,\n    foldKey,') },
  { id: 'M7', what: 'the close button is never attached, so nobody can dismiss a toast by hand',
    catches: 'T7 a toast carries a close control',
    mutate: (t) => swap(t, '  el.appendChild(closeEl);', '  void closeEl;') },
  { id: 'M8', what: 'the whole toast listens for clicks again, so it eats what is aimed below it',
    catches: 'T7b ... and the BODY no longer listens for a click of its own',
    mutate: (t) => swap(t, '  el.appendChild(closeEl);',
      "  el.appendChild(closeEl);\n  el.addEventListener('click', () => {"
      + ' const it = toastItems.find(x => x.el === el); if (it) removeToast(it); });') },
  { id: 'M9', what: 'the close button is drawn but wired to nothing',
    catches: 'T7c ... and pressing it retracts that toast',
    mutate: (t) => swap(t, "  closeEl.addEventListener('click', () => {\n"
      + '    const it = toastItems.find(x => x.el === el);\n    if (it) removeToast(it);\n  });',
      "  closeEl.addEventListener('click', () => {});") },
];

const CONTROLS = [
  { id: 'C1', what: 'a local rename — the same rule under another name',
    mutate: (t) => swap(t, 'const foldKey =', 'const groupKey =')
      .split('if (foldKey) {').join('if (groupKey) {')
      .split('it.foldKey === foldKey').join('it.foldKey === groupKey')
      .split('    foldKey,').join('    foldKey: groupKey,') },
  { id: 'C2', what: 'a warning lives a little longer — nothing here reads that number',
    mutate: (t) => swap(t, 'warning: 9000', 'warning: 9500') },
];

const run = async (m) => {
  const { module, probe } = await load(m.mutate);
  return suite(module, probe);
};

const scored = await scoreMutants(MUTANTS, run,
  { baselineRan: baseline.ran, baselineNames: baseline.names,
    title: '\n  mutants — each must be caught by the check it names.' });
const ctl = await scoreMutants(CONTROLS, run,
  { mustCatch: false, baselineRan: baseline.ran, baselineNames: baseline.names,
    title: '\n  controls — behaviour unchanged, so nothing may wake.' });

ran += MUTANTS.length + CONTROLS.length;
failed += scored.wrong + ctl.wrong;

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
