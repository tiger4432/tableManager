// Helper to get local time string in YYYY-MM-DD HH:MM:SS format
/**
 * HTML 특수문자 다섯을 «엔터티»로. 템플릿에 값을 끼워 넣기 «전»에 이것을 지납니다.
 *
 * 🔴 정본이 여기 «하나»인 이유. 2026-09-06 실측: 같은 함수가 세 벌 있었고 «하나도 export 되지
 *    않아» 각 파일이 자기 사본을 들고 있었습니다. 그리고 셋이 «같지 않았습니다» —
 *    `map2/excel_io.js` 것은 `& < >` «셋만» escape 하고 따옴표를 안 했습니다. 속성 자리에
 *    쓰였다면 값 하나가 속성을 «닫고» 나올 수 있었습니다. 사본이 갈라진다는 것이 이런 모양입니다.
 * 🔴 다섯 «전부» 합니다. 텍스트 자리에서 `&quot;` 는 그냥 따옴표로 보이므로 잃는 것이 없고,
 *    속성 자리에서는 그 둘이 «막는 것»입니다. 자리마다 다른 함수를 두면 고르는 사람이 틀립니다.
 * ⚠️ 이것은 «HTML 본문/속성»용입니다. URL 자리에는 `encodeURIComponent` 가 답이고,
 *    이 함수는 그것을 대신하지 않습니다.
 */
const HTML_ENTITY = Object.freeze({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
});
export function escapeHtml(value) {
  // `null`/`undefined` 는 «빈 문자열»입니다 — `String(null)` 이 내는 「null」이 화면에 찍히는
  // 것은 값이 아니라 «사고»이고, 세 사본 중 하나가 이미 그렇게 다루고 있었습니다.
  const text = value === null || value === undefined ? '' : String(value);
  return text.replace(/[&<>"']/g, (ch) => HTML_ENTITY[ch]);
}

export function getLocalTimeString(date = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  const yyyy = date.getFullYear();
  const MM = pad(date.getMonth() + 1);
  const dd = pad(date.getDate());
  const hh = date.getHours();
  const mm = pad(date.getMinutes());
  const ss = pad(date.getSeconds());
  return `${yyyy}-${MM}-${dd} ${hh}:${mm}:${ss}`;
}

// ============================================================
// 전역 토스트 시스템
//
// 설계 규율 (백그라운드 탭 누적 사고 대응):
//   ① **수명은 만료 시각(expireAt)이 정본이다.** 브라우저는 백그라운드 탭의 setTimeout을
//      수 초~분 단위로 throttle하므로, 타이머에 수명을 맡기면 탭을 벗어난 동안 토스트가
//      무한 누적된다(실제 사고: 복귀 시 15개 이상 적재). 타이머는 "스윕을 깨우는 힌트"일 뿐
//      만료 판정은 언제나 Date.now() 비교로 한다.
//   ② **동시 표시 상한**(MAX_VISIBLE). 초과분은 오래된 성공/정보부터 밀어낸다.
//   ③ **visibilitychange 훅** — 탭이 다시 보이는 순간 만료분을 즉시 일괄 정리한다.
//   ④ **동종 이벤트 집계** — 같은 dedupeKey는 새 토스트를 쌓지 않고 기존 토스트의
//      카운트·본문만 갱신한다(파일 처리 완료처럼 반복되는 알림).
//   ⑤ **실패는 집계·자동 해제에서 제외**하고 더 오래 남긴다. 성공 알림에 밀려 사라지면 안 된다.
//
// 이 변경은 **표시 계층만** 손댄다 — WS 이벤트 형태나 showToast 호출부 시그니처는 불변이다.
// ============================================================
const TOAST_MAX_VISIBLE = 4;
const TOAST_TTL = { info: 5000, success: 5000, warning: 9000, error: 15000 };
const toastItems = [];   // { el, type, expireAt, dedupeKey, count, baseMessage, sticky }
let toastSweepTimer = null;

function toastContainer() {
  let c = document.getElementById('toast-container');
  if (!c) {
    c = document.createElement('div');
    c.id = 'toast-container';
    document.body.appendChild(c);
  }
  return c;
}

function toastIcon(type) {
  if (type === 'success') return '✅';
  if (type === 'error') return '❌';
  if (type === 'warning') return '⚠️';
  return 'ℹ️';
}

// Retract toasts by dedupeKey. A toast that instructs the user to do something ("press
// Ctrl+V") must disappear the moment that instruction stops being true - otherwise it is
// telling them to repeat an action that has already run.
export function dismissToasts(dedupeKey) {
  if (!dedupeKey) return;
  for (let i = toastItems.length - 1; i >= 0; i--) {
    if (toastItems[i].dedupeKey === dedupeKey) removeToast(toastItems[i]);
  }
}

function removeToast(item) {
  const i = toastItems.indexOf(item);
  if (i >= 0) toastItems.splice(i, 1);
  const node = item.el;
  node.classList.add('hide');
  setTimeout(() => {
    node.remove();
    const c = document.getElementById('toast-container');
    if (c && c.children.length === 0) c.remove();
  }, 400);
}

// 만료 판정은 항상 경과 시간으로 한다 (throttle된 타이머를 신뢰하지 않는다)
//
// [M1 수정] `keep`은 **방금 삽입한 토스트**다. 종전에는 push 직후 sweep을 부르면서
// "가장 오래된 비-에러"를 찾았는데, 에러가 상한만큼 떠 있으면 **방금 넣은 성공 토스트가
// 유일한 비-에러**라 삽입 즉시 스스로 퇴거됐다(사용자는 알림을 아예 못 본다).
// 새로 넣은 것은 퇴거 대상에서 제외한다.
function sweepToasts(keep) {
  const now = Date.now();
  for (let i = toastItems.length - 1; i >= 0; i--) {
    const it = toastItems[i];
    if (it !== keep && !it.sticky && now >= it.expireAt) removeToast(it);
  }
  // 상한 초과분은 **오래된 비-에러부터** 밀어낸다 (에러는 마지막까지 남긴다)
  const evictable = () => toastItems.filter(it => it !== keep);
  let overflow = toastItems.length - TOAST_MAX_VISIBLE;
  if (overflow > 0) {
    for (const it of evictable()) {
      if (overflow <= 0) break;
      if (it.type !== 'error') { removeToast(it); overflow--; }
    }
    // 전부 에러라면 그때만 가장 오래된 것부터 정리한다 (새로 넣은 것은 여전히 보호)
    for (const it of evictable()) {
      if (toastItems.length <= TOAST_MAX_VISIBLE) break;
      removeToast(it);
    }
  }
  scheduleToastSweep();
}

function scheduleToastSweep() {
  clearTimeout(toastSweepTimer);
  if (toastItems.length === 0) return;
  const next = toastItems.reduce((m, it) => (it.sticky ? m : Math.min(m, it.expireAt)), Infinity);
  if (!Number.isFinite(next)) return;
  toastSweepTimer = setTimeout(sweepToasts, Math.max(250, next - Date.now()));
}

// 탭 복귀 즉시 정리 — 사용자가 과거 알림 더미를 마주하지 않게 한다
// The guard asked about `document` and then used `window`. In a browser both exist,
// so it was inert there; anywhere the DOM is stubbed only in PART - which is every
// harness that imports this module - it threw. Two globals, two questions.
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) sweepToasts();
  });
}
if (typeof window !== 'undefined') window.addEventListener('focus', sweepToasts);

function paintToast(item) {
  const label = item.count > 1 ? `${item.baseMessage} · ${item.count}건` : item.baseMessage;
  const icon = item.el.querySelector('.toast-icon');
  const body = item.el.querySelector('.toast-body');
  if (icon) icon.textContent = toastIcon(item.type);
  // ⚠️ textContent — 메시지에 파일명·서버 원문이 섞이므로 HTML로 해석시키지 않는다
  if (body) body.textContent = label;
}

/**
 * @param {string} message
 * @param {'info'|'success'|'error'|'warning'} type
 * @param {{dedupeKey?: string, sticky?: boolean, ttl?: number}} [opts]
 *        dedupeKey — 같은 키의 알림은 쌓지 않고 기존 토스트에 집계된다.
 */
export function showToast(message, type = 'info', opts = {}) {
  sweepToasts(); // 새 토스트를 올리기 전에 먼저 만료분을 걷어낸다
  const now = Date.now();
  const ttl = Number(opts.ttl) || TOAST_TTL[type] || 5000;
  const text = String(message);

  // ④ 동종 집계 — 실패는 집계하지 않는다(개별 사유가 중요하므로)
  if (opts.dedupeKey && type !== 'error') {
    const hit = toastItems.find(it => it.dedupeKey === opts.dedupeKey && it.type === type);
    if (hit) {
      hit.count += 1;
      hit.baseMessage = text;          // 최신 메시지로 갱신 (예: 최근 파일명)
      hit.expireAt = now + ttl;        // 수명 연장
      paintToast(hit);
      scheduleToastSweep();
      return;
    }
  }

  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  const iconEl = document.createElement('span');
  iconEl.className = 'toast-icon';
  iconEl.style.fontSize = '1.1rem';
  const bodyEl = document.createElement('span');
  bodyEl.className = 'toast-body';
  el.appendChild(iconEl);
  el.appendChild(bodyEl);
  el.addEventListener('click', () => { const it = toastItems.find(x => x.el === el); if (it) removeToast(it); });

  const item = {
    el, type, expireAt: now + ttl,
    dedupeKey: opts.dedupeKey || null,
    count: 1, baseMessage: text,
    sticky: !!opts.sticky,
  };
  paintToast(item);
  toastContainer().appendChild(el);
  toastItems.push(item);
  sweepToasts(item);   // [M1] 방금 넣은 것은 퇴거 대상에서 제외
}

// Helper to strip user prefix and unique UUID suffixes from filename in client
export function getCleanFilename(filename) {
  if (!filename) return '';
  let clean = filename.replace(/^user\([^)]+\)_/, '');
  const lastDotIdx = clean.lastIndexOf('.');
  if (lastDotIdx !== -1) {
    let name = clean.slice(0, lastDotIdx);
    const ext = clean.slice(lastDotIdx);
    name = name.replace(/_[0-9a-fA-F]{8}$/, '');
    clean = name + ext;
  } else {
    clean = clean.replace(/_[0-9a-fA-F]{8}$/, '');
  }
  return clean;
}

// Floating Ingestion Progress Widget Helper
// 좌측 진행 카드는 (테이블, 파일)마다 하나씩 생기고 상한이 없었다 — 파일 여러 개를
// 한 번에 넣으면 화면 왼쪽이 카드로 덮인다. 우측 토스트에서 같은 문제를 `dedupeKey`
// 집계(④)로 풀었으므로 여기도 같은 취지로 **상한 + 나머지 한 줄 집계**를 쓴다.
// 진행률은 개별 파일마다 의미가 있으므로 합치지 않고 **가리기만** 한다 — 가려진 카드도
// 갱신은 계속 받고, 완료되면 스스로 사라지며 뒤 카드가 올라온다(대기열처럼 보인다).
// 파일 인제션의 «선언». 모양은 `progress_card.js` 가 들고 있고, 여기 남은 것은
// 「이 진행이 무엇에 대한 것인가」뿐입니다 — 표 이름과 파일 이름은 «신원»을 만드는 데만
// 쓰이고, 부품은 그 낱말을 모릅니다 (상설: 근원 템플릿 -> 데이터 갈아끼우기).
function ingestionKey(tableName, filename) {
  return `${tableName}-${getCleanFilename(filename).replace(/[^a-zA-Z0-9]/g, '_')}`;
}

/**
 * 성공 카드의 아래 줄 — 🔴 「검증 완료」는 «서버가 아무 말도 안 했을 때만» 참입니다.
 *
 * 적재는 성공하고도 행을 «버릴 수» 있습니다. 인제션이 그 사실을 세어서 문장으로 만들고
 * (`_compose_detail`: 「키 결측으로 N행 스킵」 · 「파싱 결과 0행 ― 저장된 셀 없음」),
 * 그 문장은 성공 통지의 사유 슬롯에 실려 «화면까지» 옵니다. 그런데 이 카드는 상태가
 * SUCCESS 라는 것만 보고 「적재 성공 및 정합성 검증 완료」를 «무조건» 말했습니다 —
 * 즉 버려진 행이 있는 적재가 «완전한 것»으로 보였고, 다음 공정이 그것을 그대로 받았습니다.
 *
 * ⛔ 그리고 «자막»을 달지 않습니다. 「검증 완료 (일부 행 제외됨)」처럼 뒤에 붙이면 앞 절이
 *    여전히 «거짓»입니다. 서버가 할 말이 있으면 그 말이 «답»이고, 없을 때만 위 문장입니다.
 *
 * ⚠️ 상한은 «오늘의 조립기»에 맞춰져 있습니다 — 위 세 조각이 " / " 로 이어진 길이가
 *    들어갑니다. 조립기가 조각을 더 붙이는 날 이 수를 «다시 재야» 합니다. 잘라서 뒤를 버리면
 *    버리는 것이 대개 «수»입니다 (「키 결측으로 N행」이 뒤에 옵니다).
 */
export const INGESTION_DONE_STATS = '적재 성공 및 정합성 검증 완료';
export const MAX_INGESTION_DONE_STATS = 120;

export function ingestionDoneStats(detail) {
  const said = detail == null ? '' : String(detail).trim();
  if (!said) return INGESTION_DONE_STATS;
  return said.length > MAX_INGESTION_DONE_STATS
    ? said.slice(0, MAX_INGESTION_DONE_STATS) : said;
}

export function showIngestionProgress(tableName, filename, progress, processedRows, totalRows) {
  showProgressCard({
    key: ingestionKey(tableName, filename),
    title: '\ud83d\udce4 파일 파싱 및 적재 중',
    subtitle: getCleanFilename(filename),
    progress,
    processed: processedRows,
    total: totalRows,
    statsSuffix: ' 행 처리됨',
    doneTitle: '\u2705 파일 적재 완료',
    // 진행이 시작될 때는 서버가 아직 아무 말도 안 했습니다 — 여기서는 기본 문장이 맞고,
    // 끝날 때 `finishIngestionProgress` 가 할 말이 있으면 «갈아 끼웁니다».
    doneStats: INGESTION_DONE_STATS,
  });
}

export function finishIngestionProgress(tableName, filename, status, errorMsg = null) {
  finishProgressCard({
    key: ingestionKey(tableName, filename),
    ok: status === 'SUCCESS',
    okTitle: '\u2705 파일 적재 완료',
    okStats: ingestionDoneStats(errorMsg),
    failTitle: '\u274c 파일 적재 실패',
    failStats: errorMsg ? errorMsg.slice(0, 50) : '처리 중 예외 발생',
  });
}

// Expose on window object dynamically for any non-ESM environment components if needed.
// 🔴 `typeof` 가드는 «브라우저에서 아무것도 바꾸지 않습니다» -- window 가 있으면 전과 같이
//    붙습니다. window 가 «없는» 곳(node)에서 이 한 줄이 파일 전체를 import 불가로 만들고,
import { showProgressCard, finishProgressCard } from './progress_card.js';
//    그래서 utils.js 를 재던 하니스가 텍스트 잘라쓰기를 쓸 수밖에 없었습니다.
if (typeof window !== 'undefined') window.showToast = showToast;
