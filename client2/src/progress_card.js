// PROGRESS CARD — 「무언가가 도는 동안 그 진행을 보여 준다」의 «근원 템플릿».
//
// 🔴 왜 부품인가: 이 카드가 «둘째»로 필요해졌습니다 (파일 인제션 · 리플레이). 상설 —
//    「같은 종류가 «둘째»면 두 번째를 손으로 그리지 않는다. 첫째를 템플릿으로 올리고
//     둘 다 «선언»으로 만든다」. 그래서 이 파일에는 도메인 낱말이 «하나도» 없습니다:
//    표 이름도 파일 이름도 인자에 «없습니다» — 그것이 지금까지 묶여 있던 자리입니다.
//
// ═══ 이 파일이 지키는 셋 ═══════════════════════════════════════════════════════════
//
// ① «신원»은 부르는 쪽이 만듭니다 (`key`). 무엇으로 카드를 구별하는지는 그쪽 사정입니다.
//
// ② 이미 «끝난» 카드는 다시 안 그립니다. 늦게 도착한 진행 메시지가 완료를 되돌리면
//    사람은 「끝났는데 왜 다시 도나」를 봅니다.
//
// ③ 🔴 모르는 수를 «0 으로» 그리지 않습니다. 막대의 «폭»은 수가 아니면 0 이 맞지만
//    (길이를 못 그리니까), «글자로 나가는» 수는 `—` 입니다. 철자는 `absent.js` 하나뿐입니다.

import { localeCountText } from './absent.js';

const CONTAINER_ID = 'ingestion-progress-container';
const OVERFLOW_ID = 'progress-overflow';
const MAX_VISIBLE = 3;
const DONE_CLASSES = ['status-success', 'status-error', 'status-auto-dismiss'];

function cardsIn(container) {
  return Array.from(container.children).filter(el => el.id !== OVERFLOW_ID);
}

/** 넷째부터는 접고, 몇 건이 접혔는지 한 줄로. 집계 카드는 «자식으로 세지 않습니다». */
function collapseOverflow(container) {
  if (!container) return;
  const cards = cardsIn(container);
  cards.forEach((el, i) => {
    el.style.display = i < MAX_VISIBLE ? '' : 'none';
  });
  const hidden = cards.length - MAX_VISIBLE;
  let overflow = document.getElementById(OVERFLOW_ID);
  if (hidden <= 0) {
    if (overflow) overflow.remove();
    return;
  }
  if (!overflow) {
    overflow = document.createElement('div');
    overflow.id = OVERFLOW_ID;
    overflow.className = 'progress-card';
  }
  overflow.innerHTML =
    `<div class="progress-header"><span class="progress-title">📤 그 외 ${hidden}건 적재 중</span></div>`;
  container.appendChild(overflow);
  return overflow;
}

// 카드 제거는 두 경로(자동 완료 / finish 호출)에서 같은 일을 했다. 한 곳으로 모은 이유는
// 빈 컨테이너 판정 때문이다 — 집계 카드를 자식으로 세면 컨테이너가 영원히 안 지워진다.
function dismiss(card) {
  card.style.transition = 'opacity 0.35s ease, transform 0.35s ease';
  card.style.animation = 'none';
  card.style.opacity = '0';
  card.style.transform = 'translateY(20px) scale(0.9)';
  setTimeout(() => {
    const container = card.parentElement;
    card.remove();
    if (!container) return;
    if (cardsIn(container).length === 0) container.remove();
    else collapseOverflow(container);
  }, 400);
}

const isDone = (card) => DONE_CLASSES.some(c => card.classList.contains(c));

/**
 * 진행 카드를 그리거나 갱신합니다.
 *
 * @param {object} decl 부르는 쪽의 «선언» — 도메인 낱말은 전부 여기로 들어옵니다
 * @param {string} decl.key        이 카드의 신원. 부르는 쪽이 만듭니다
 * @param {string} decl.title      도는 동안의 제목
 * @param {string} [decl.subtitle] 제목 아래 한 줄 (무엇에 대한 것인가)
 * @param {*} [decl.progress]      백분율. 수가 아니면 막대는 0 폭입니다
 * @param {*} [decl.processed]     처리한 수. 모르면 «—»
 * @param {*} [decl.total]         전체 수. 모르면 «—»
 * @param {string} [decl.statsSuffix]  두 수 뒤에 붙는 말 (예: 「행 처리됨」)
 * @param {string} [decl.doneTitle]    완료로 판정됐을 때의 제목
 * @param {string} [decl.doneStats]    완료로 판정됐을 때의 아래 줄
 */
export function showProgressCard(decl) {
  const { key, title, subtitle = '', statsSuffix = '',
          doneTitle = title, doneStats = '' } = decl || {};
  if (!key) return null;
  let container = document.getElementById(CONTAINER_ID);
  if (!container) {
    container = document.createElement('div');
    container.id = CONTAINER_ID;
    document.body.appendChild(container);
  }
  const cardId = `progress-${key}`;
  let card = document.getElementById(cardId);
  if (!card) {
    card = document.createElement('div');
    card.id = cardId;
    card.className = 'progress-card';
    container.appendChild(card);
    collapseOverflow(container);
  }
  // ② 끝난 카드는 되돌리지 않습니다.
  if (isDone(card)) return card;

  // ③ 막대의 `p` 는 «폭»이라 수가 아니면 0 이 맞습니다. 글자로 나가는 둘은 `—` 입니다.
  const p = parseInt(decl.progress, 10) || 0;
  const pr = parseInt(decl.processed, 10);
  const tr = parseInt(decl.total, 10);

  card.innerHTML = `
    <div class="progress-header">
      <span class="progress-title">${title}</span>
      <span class="progress-percent">${p}%</span>
    </div>
    <div class="progress-filename" title="${subtitle}">${subtitle}</div>
    <div class="progress-bar-container">
      <div class="progress-bar" style="width: ${p}%;"></div>
    </div>
    <div class="progress-stats">${localeCountText(pr)} / ${localeCountText(tr)}${statsSuffix}</div>
  `;

  const complete = p >= 100
    || (Number.isFinite(tr) && tr > 0 && Number.isFinite(pr) && pr >= tr);
  if (complete) {
    card.classList.add('status-auto-dismiss');
    card.classList.add('status-success');
    const t = card.querySelector('.progress-title');
    if (t) t.textContent = doneTitle;
    const percent = card.querySelector('.progress-percent');
    if (percent) percent.textContent = '100%';
    const bar = card.querySelector('.progress-bar');
    if (bar) bar.style.width = '100%';
    const stats = card.querySelector('.progress-stats');
    if (stats) stats.textContent = doneStats;
    setTimeout(() => dismiss(card), 2500);
  }
  return card;
}

/**
 * 끝났다고 «말해진» 카드를 닫습니다.
 *
 * @param {object} decl
 * @param {string} decl.key
 * @param {boolean} decl.ok            성공인가
 * @param {string} [decl.okTitle]      성공 제목
 * @param {string} [decl.okStats]      성공 아래 줄
 * @param {string} [decl.failTitle]    실패 제목
 * @param {string} [decl.failStats]    실패 아래 줄 (서버가 준 사유가 있으면 그것)
 */
export function finishProgressCard(decl) {
  const { key, ok, okTitle = '', okStats = '', failTitle = '', failStats = '' } = decl || {};
  if (!key) return;
  const card = document.getElementById(`progress-${key}`);
  if (!card || isDone(card)) return;

  card.classList.add('status-auto-dismiss');
  const t = card.querySelector('.progress-title');
  const bar = card.querySelector('.progress-bar');
  const stats = card.querySelector('.progress-stats');
  if (ok) {
    card.classList.add('status-success');
    if (t) t.textContent = okTitle;
    const percent = card.querySelector('.progress-percent');
    if (percent) percent.textContent = '100%';
    if (bar) bar.style.width = '100%';
    if (stats) stats.textContent = okStats;
  } else {
    card.classList.add('status-error');
    if (t) t.textContent = failTitle;
    if (bar) bar.style.width = '100%';
    if (stats) stats.textContent = failStats;
  }
  setTimeout(() => dismiss(card), 2500);
}
