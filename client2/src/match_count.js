// ═══════════════════════════════════════════════════════════════════════════════
// MATCH COUNT — 「몇 건인가」를 «세 상태»로 답하는 한 곳
//
// 🔴 개수는 «늦게 옵니다» (소유자 승인 2026-09-02). 행을 먼저 그리고, 개수는 두 번째 요청이
//    오면 채웁니다. 그래서 화면은 이제 «세 가지»를 구별해야 합니다:
//       숫자   `12`     센 결과
//       null   `…`      «아직 모릅니다» -- 세는 중
//       0      `0`      «진짜 없습니다»
//    「Matches:」 낱말은 index.html 의 제 칸에 있습니다 — 좁으면 낱말이 먼저 비킵니다(C-99 ②, 총괄 10-09).
//    null 을 0 으로 그리면 「일치 없음」이라는 «거짓»이고, 빈칸으로 두면 고장으로 읽힙니다.
//
// 🔴 이 파일이 생긴 이유: 「Matches:」를 쓰는 자리가 «다섯»이었습니다 --
//       api.js:256(캐시) · api.js:313 · timeline.js:1051(캐시) · timeline.js:1112 · main.js:1119
//    하나만 고치면 나머지 넷이 «그 경로에서만» 「Matches: null」을 찍습니다. 그건 0 도 빈칸도
//    아니면서 「세는 중」도 아닌 세 번째 거짓말입니다. 그래서 «부류»로 옮깁니다.
//
// 🔴 수는 «언제의 무엇»입니다 (소유자 ㄱ · 총괄 67e5e9ccd ㄱ-1, 서버 table_total): 표 전체는 일꾼이 마지막으로
//    센 수와 그 시각, 좁힌 읽기는 10,000 까지만 세고 넘으면 capped. 바닥줄 · 쪽 넘기기 끝 · 보강 결손이 이 파일을 지납니다.
//
// NO DOM GLOBALS beyond the element handed in. 맨 node 로 채점됩니다.
// ═══════════════════════════════════════════════════════════════════════════════
import { ageText } from './pickup_state.js';
import { localStamp, parseServerInstant } from './server_time.js';
import { unitText } from './ui_words.js';

/** 「아직 모른다」의 표기. 0 과도 빈칸과도 달라야 합니다. */
export const COUNTING = '…';
export const COUNTING_ROWS = `Counting rows${COUNTING}`;
/** A count the server could not make (총괄 0fd18ae19 6: `failed: {reason, at}` · a refused /data/count) - not «counting». */
export const COUNT_FAILED = 'Count failed';
/** 바닥줄의 나이를 다시 그리는 간격 (총괄 10-13 ①: 그대로 둔 «10s ago» 가 몇 분 뒤에도 10s 면 거짓). 요청 없음. */
export const AGE_EVERY_MS = 10000;

/** 센 수인가. `null`·`undefined`·NaN 은 «아닙니다». */
export function isCounted(total) {
  return typeof total === 'number' && Number.isFinite(total);
}

/** 서버의 수 한 묶음 -> { total, capped, countedAt, seconds, counting, failed }. 받는 것: `/data` 의 답(`count` 가 있으면
 *  그것) · `/data/count` 의 답 · 수 하나(옛 서버 · Load All 이 받은 행 수). total null = 아직 모름 — 수가 없는 «답»은
 *  세는 중(counting), null(거절된 읽기 · 표 바꿈)은 세러 간 적이 없습니다. */
export function countOf(x) {
  const c = x !== null && typeof x === 'object' ? (x.count !== null && typeof x.count === 'object' ? x.count : x) : { total: x };
  const total = isCounted(c.total) ? c.total : null;
  const known = (v) => (total === null ? null : v);
  const failed = total === null && c.failed !== null && typeof c.failed === 'object' ? c.failed : null;
  return { total, capped: total !== null && c.capped === true, countedAt: known(c.counted_at || c.countedAt || null),
    seconds: known(isCounted(c.count_seconds) ? c.count_seconds : isCounted(c.seconds) ? c.seconds : null),
    counting: total === null && !failed && (typeof c.counting === 'boolean' ? c.counting : x !== null && typeof x === 'object'),
    failed };
}

/** 수만 — «4,012,334» · «10,000+» · «…». 낱말이 앞에 서는 자리(보강 결손)가 씁니다. */
export function countNumberText(x) {
  const c = countOf(x);
  return c.total === null ? COUNTING : `${c.total.toLocaleString('en-US')}${c.capped ? '+' : ''}`;
}

/** 바닥줄 한 줄 — «4,012,334 rows · 10s ago» · «10,000+ rows» · «Counting rows…» · «Count failed (<reason>)». 나이는 `now` 에서 센 시각까지. */
export function matchCountText(x, now = Date.now()) {
  const c = countOf(x);
  if (c.failed) return c.failed.reason ? `${COUNT_FAILED} (${c.failed.reason})` : COUNT_FAILED;
  if (c.total === null) return c.counting ? COUNTING_ROWS : COUNTING;
  const rows = unitText(countNumberText(c), 'row');
  const at = c.capped ? null : parseServerInstant(c.countedAt);
  return at ? `${rows} · ${ageText(Math.max(0, (now - at.getTime()) / 1000))} ago` : rows;
}

/** 마우스를 올리면 — 센 시각(보는 쪽 zone)과 센 데 걸린 초. 못 센 수는 그 줄 전부와 그 시각(좁은 바닥줄은 사유를 자릅니다). */
export function matchCountTitle(x) {
  const c = countOf(x);
  if (c.failed) return c.failed.at ? `${matchCountText(c)} · ${localStamp(c.failed.at)}` : matchCountText(c);
  if (!c.countedAt || c.capped) return '';
  return `Counted ${localStamp(c.countedAt)}${c.seconds === null ? '' : ` · took ${c.seconds} s`}`;
}

const CLOCK = { now: () => Date.now(), every: (fn, ms) => setInterval(fn, ms), stop: (h) => clearInterval(h) };

/** 바닥줄을 부르는 «한 함수». 표기 · 표지 · 마우스 글을 같이 답니다. 나이가 있는 수면 그 줄 하나에 타이머 하나 —
 *  `AGE_EVERY_MS` 마다 같은 수로 글자만 다시 그립니다(총괄 10-13 ①). 타이머는 그 요소가 듭니다. */
export function setMatchCount(el, x, clock = CLOCK) {
  if (!el) return;
  const c = countOf(x);
  const draw = () => { el.textContent = matchCountText(c, clock.now()); };
  draw();
  // A narrow bar (the screen gate at 1280 with the side panel at 500): the tail («rows · 10s ago») gives way, the
  // number never - its glyphs and one for the «…» are the element's floor (the bar is monospace: a ch a glyph).
  const floor = c.total !== null ? countNumberText(c) : c.failed ? COUNT_FAILED : c.counting ? 'Counting' : COUNTING;
  if (el.style) el.style.minWidth = `${floor.length + (floor === el.textContent ? 0 : 1)}ch`;
  // 글자만으로도 구별되지만 표지도 답니다 -- 세는 중인 수는 «아직 쓸 수 없는» 수입니다.
  if (el.classList) el.classList.toggle('is-counting', c.total === null);
  const title = matchCountTitle(c);
  if (title && el.setAttribute) el.setAttribute('title', title);
  else if (el.removeAttribute) el.removeAttribute('title');
  if (el.matchAgeTimer) clock.stop(el.matchAgeTimer);
  el.matchAgeTimer = c.countedAt && !c.capped ? clock.every(draw, AGE_EVERY_MS) : null;
}

/** 실시간 행 하나가 들어오고 나갈 때 쪽 캐시의 수(ui.js) — 정확한 수만 움직입니다. 10,000+ 는 그대로, 모름은 모름. */
export function shiftCount(x, by) {
  const c = countOf(x);
  return c.total === null || c.capped ? c : { ...c, total: Math.max(0, c.total + by) };
}

/** 페이지 컨트롤이 무엇을 보여야 하는가. DOM 을 모르므로 «수»로만 답합니다.
 *
 * 🔴 `Math.ceil(null / limit) || 1` 은 «1» 입니다. 그러면 아직 안 센 표가 「1쪽뿐」이 되고
 *    `currentPage >= totalPages` 가 참이 되어 «다음이 꺼집니다» -- 세는 중에는 다음 쪽으로
 *    갈 수 없게 됩니다. 「모른다」와 「1쪽뿐」은 «다른 상태»입니다.
 */
export function pagingView(x, currentSkip, pageLimit, shown) {
  const { total, capped } = countOf(x);
  const currentPage = Math.floor(currentSkip / pageLimit) + 1;
  const counted = total !== null && !capped;
  const totalPages = counted ? (Math.ceil(total / pageLimit) || 1) : null;
  return {
    currentPage,
    totalPages,
    totalPagesText: counted ? String(totalPages) : capped ? `${Math.ceil(total / pageLimit)}+` : COUNTING,
    prevDisabled: currentPage === 1,
    // 모르거나 10,000+ 이면 끝은 «limit 보다 짧은 쪽» (구현자 A 67e5e9ccd ㄱ-1) — `shown` 은 지금 쪽의 행 수.
    // 센 수도 늙으니(총괄 0fd18ae19 5) 꽉 찬 쪽은 센 쪽 수의 끝이어도 끝이 아닙니다.
    nextDisabled: counted ? currentPage >= totalPages && !(isCounted(shown) && shown >= pageLimit) : isCounted(shown) && shown < pageLimit,
  };
}
