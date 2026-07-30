// Helper to get local time string in YYYY-MM-DD HH:MM:SS format
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
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) sweepToasts();
  });
  window.addEventListener('focus', sweepToasts);
}

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
const MAX_VISIBLE_PROGRESS_CARDS = 3;
const PROGRESS_OVERFLOW_ID = 'progress-overflow';

function progressCards(container) {
  return Array.from(container.children).filter(el => el.id !== PROGRESS_OVERFLOW_ID);
}

function collapseProgressOverflow(container) {
  if (!container) return;
  const cards = progressCards(container);
  cards.forEach((el, i) => {
    el.style.display = i < MAX_VISIBLE_PROGRESS_CARDS ? '' : 'none';
  });

  const hidden = cards.length - MAX_VISIBLE_PROGRESS_CARDS;
  let overflow = document.getElementById(PROGRESS_OVERFLOW_ID);
  if (hidden <= 0) {
    if (overflow) overflow.remove();
    return;
  }
  if (!overflow) {
    overflow = document.createElement('div');
    overflow.id = PROGRESS_OVERFLOW_ID;
    overflow.className = 'progress-card';
  }
  overflow.innerHTML =
    `<div class="progress-header"><span class="progress-title">📤 그 외 ${hidden}건 적재 중</span></div>`;
  container.appendChild(overflow);   // 항상 맨 아래
}

// 카드 제거는 두 경로(자동 완료 / finish 호출)에서 같은 일을 했다. 한 곳으로 모은 이유는
// 빈 컨테이너 판정 때문이다 — 집계 카드를 자식으로 세면 컨테이너가 영원히 안 지워진다.
function dismissProgressCard(card) {
  card.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
  card.style.animation = 'none';
  card.style.opacity = '0';
  card.style.transform = 'translateY(20px) scale(0.9)';

  setTimeout(() => {
    const container = card.parentElement;
    card.remove();
    if (!container) return;
    if (progressCards(container).length === 0) {
      container.remove();
    } else {
      collapseProgressOverflow(container);
    }
  }, 400);
}

export function showIngestionProgress(tableName, filename, progress, processedRows, totalRows) {
  let container = document.getElementById('ingestion-progress-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'ingestion-progress-container';
    document.body.appendChild(container);
  }

  const cleanFilename = getCleanFilename(filename);
  const safeFilename = cleanFilename.replace(/[^a-zA-Z0-9]/g, '_');
  const cardId = `progress-${tableName}-${safeFilename}`;
  let card = document.getElementById(cardId);

  if (!card) {
    card = document.createElement('div');
    card.id = cardId;
    card.className = 'progress-card';
    container.appendChild(card);
    collapseProgressOverflow(container);
  }

  if (card.classList.contains('status-success') ||
    card.classList.contains('status-error') ||
    card.classList.contains('status-auto-dismiss')) {
    return;
  }

  const p = parseInt(progress, 10) || 0;
  const pr = parseInt(processedRows, 10) || 0;
  const tr = parseInt(totalRows, 10) || 0;

  card.innerHTML = `
    <div class="progress-header">
      <span class="progress-title">📤 파일 파싱 및 적재 중</span>
      <span class="progress-percent">${p}%</span>
    </div>
    <div class="progress-filename" title="${cleanFilename}">${cleanFilename}</div>
    <div class="progress-bar-container">
      <div class="progress-bar" style="width: ${p}%;"></div>
    </div>
    <div class="progress-stats">${pr.toLocaleString()} / ${tr.toLocaleString()} 행 처리됨</div>
  `;

  const isComplete = p >= 100 || (tr > 0 && pr >= tr);
  if (isComplete) {
    card.classList.add('status-auto-dismiss');
    card.classList.add('status-success');

    const title = card.querySelector('.progress-title');
    if (title) title.textContent = '✅ 파일 적재 완료';
    const percent = card.querySelector('.progress-percent');
    if (percent) percent.textContent = '100%';
    const bar = card.querySelector('.progress-bar');
    if (bar) bar.style.width = '100%';
    const stats = card.querySelector('.progress-stats');
    if (stats) stats.textContent = '적재 성공 및 정합성 검증 완료';

    setTimeout(() => dismissProgressCard(card), 2500);
  }
}

export function finishIngestionProgress(tableName, filename, status, errorMsg = null) {
  const cleanFilename = getCleanFilename(filename);
  const safeFilename = cleanFilename.replace(/[^a-zA-Z0-9]/g, '_');
  const cardId = `progress-${tableName}-${safeFilename}`;
  const card = document.getElementById(cardId);
  if (!card) return;

  if (card.classList.contains('status-success') ||
    card.classList.contains('status-error') ||
    card.classList.contains('status-auto-dismiss')) {
    return;
  }

  card.classList.add('status-auto-dismiss');

  if (status === 'SUCCESS') {
    card.classList.add('status-success');
    const title = card.querySelector('.progress-title');
    if (title) title.textContent = '✅ 파일 적재 완료';
    const percent = card.querySelector('.progress-percent');
    if (percent) percent.textContent = '100%';
    const bar = card.querySelector('.progress-bar');
    if (bar) bar.style.width = '100%';
    const stats = card.querySelector('.progress-stats');
    if (stats) stats.textContent = '적재 성공 및 정합성 검증 완료';
  } else {
    card.classList.add('status-error');
    const title = card.querySelector('.progress-title');
    if (title) title.textContent = '❌ 파일 적재 실패';
    const bar = card.querySelector('.progress-bar');
    if (bar) bar.style.width = '100%';
    const stats = card.querySelector('.progress-stats');
    if (stats) stats.textContent = errorMsg ? errorMsg.slice(0, 50) : '처리 중 예외 발생';
  }

  setTimeout(() => dismissProgressCard(card), 2500);
}

// Expose on window object dynamically for any non-ESM environment components if needed
window.showToast = showToast;
