// PICKUP STATE — 「집는 이가 살아 있나」. 큐 화면의 «첫 줄»입니다.
//
// 🔴 왜 첫 줄인가: 서버가 재고 적어 뒀습니다 — 대기 시간이 «두 봉우리»입니다. 한 틱이거나,
//    끝이 없거나. 그래서 「줄이 얼마나 기냐」는 「곧 도나」와 「아무도 안 집냐」를 «못 가릅니다».
//    가르는 것은 «마지막 집기가 언제였나»입니다. 짧은 줄 + 오래된 집기가 빈 줄처럼 보이던
//    바로 그 상태입니다.
//
// ⛔ 예상 시각을 «한 수»로 내지 않습니다. 두 봉우리의 간격이 백 배라 「N초 뒤 시작」은
//    대부분 거짓입니다. ⛔ 진행률을 지어내지 않습니다.
// ⛔ 🔴 그리고 «임의 임계»로 「늦음」을 판정하지 않습니다. 나이와 주기를 «둘 다 단위와 함께»
//    내놓고, 읽는 것은 사람이 합니다. 여기서 「멈춤」이라고 쓰려면 그 경계가 필요한데,
//    그 경계는 이 파일이 «지어낼» 것이 아니라 서버가 «가진» 것입니다 (아직 안 옵니다).
//
// ⚠️ 그리고 「집은 적 없음」과 「안 물어봤음」은 다릅니다. 앞은 답이고 뒤는 답이 없는 것입니다.

/** 안 물어봤거나 못 받았습니다. */
export const PICKUP_UNREAD = '집기 · 모름';

const num = (value) => (Number.isFinite(value) ? value : null);
const int = (value) => (Number.isInteger(value) ? value : null);

/** 초를 사람이 읽는 «수 + 단위»로. 서술어 없음, 기호 하나. */
export function ageText(seconds) {
  const s = num(seconds);
  if (s === null) return '';
  if (s < 60) return `${Math.round(s)}초`;
  if (s < 3600) return `${Math.round(s / 60)}분`;
  return `${Math.round(s / 360) / 10}시간`;
}

/**
 * 큐 버킷 하나를 «네 사실»로. 전부 서버가 낸 값입니다.
 *
 * @param {object|null|undefined} queue `/admin/chain/queue` 안 scheduler 버킷의 `queue`
 * @param {{read?: boolean}} [opts]
 */
export function pickupState(queue, opts = {}) {
  if (opts.read === false || !queue || typeof queue !== 'object') {
    return { read: false, pickup: PICKUP_UNREAD, waiting: null, waitingText: '',
             orphaned: [], rows: [] };
  }
  const age = num(queue.last_pickup_age_seconds);
  const interval = num(queue.picker_interval_seconds);
  // 🔴 세 상태입니다: 집은 적 «없음» · 나이 «있음» · 나이를 «안 보냄».
  //    「집은 적 없음」을 0초로 그리면 방금 집은 것처럼 보입니다.
  let pickup;
  if (!queue.last_pickup_at) pickup = '집은 적 없음';
  else if (age === null) pickup = PICKUP_UNREAD;
  else pickup = `마지막 집기 · ${ageText(age)} 전`;
  // 주기는 «기준»이라 남깁니다 — 없으면 나이가 무엇에 견줄 수인지 알 수 없습니다.
  const basis = interval === null ? '' : `주기 ${ageText(interval)}`;

  // 🔴 앞에 몇 개는 «서버가 센 수»만 씁니다. 목록은 최신순이고 잘릴 수 있어서, 화면이 길이를
  //    세면 잘린 만큼 «적게» 말합니다 — 그리고 그 잘림은 화면에서 안 보입니다.
  const waiting = int(queue.waiting_count);
  const rows = Array.isArray(queue.waiting) ? queue.waiting : [];
  const truncated = waiting !== null && rows.length < waiting;

  // 🔴 「도는 중인데 주인이 없음」. 판정은 서버가 heartbeat 로 합니다 (`owned`/`orphaned`/
  //    `unknown`) — 여기서 pid 를 보지 않습니다. `unknown` 은 «고아가 아닙니다».
  const orphaned = (Array.isArray(queue.orphaned) ? queue.orphaned : [])
    .filter((row) => row && row.owner === 'orphaned')
    .map((row) => ({
      runId: typeof row.run_id === 'string' ? row.run_id : '',
      op: typeof row.op === 'string' ? row.op : '',
      age: ageText(row.started_seconds),
    }));

  return {
    read: true,
    pickup,
    basis,
    waiting,
    waitingText: waiting === null ? PICKUP_UNREAD
      : truncated ? `대기 ${waiting} · 목록 ${rows.length}` : `대기 ${waiting}`,
    truncated,
    orphaned,
    rows,
  };
}
