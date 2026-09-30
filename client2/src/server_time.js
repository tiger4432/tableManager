// ═══════════════════════════════════════════════════════════════════════════════
// 서버 시각 — «UTC 순간»으로 읽고 «보는 쪽 zone»으로 그린다. 한 곳.
//
// 🔴 왜 생겼나 (C-77 / S-182 ⓐ, 판정 289). 서버가 시각을 «offset 단 ISO» 로 내기 시작했다.
//    실측(2026-09-11, `/tables/dt_job_attribution/data`): `'2026-08-01 15:28:47+00:00'`.
//    기계 로컬 렌더는 서버에서 사라졌고, 「어느 zone 으로 보이나」는 이제 «클라의 일»이다.
//
// 🔴 이 파일이 없던 동안 화면 셋이 그 문자열을 «잘라서» 그렸다. 자르면 offset 이 떨어지고,
//    UTC 숫자가 «로컬인 척» 찍힌다 — KST 운영자에게 아홉 시간 틀린 값이 오류 없이 나온다.
//    그 자리들의 주석은 「타임존 재해석 없음」이라 «적혀» 있었고, 서버가 naive 를 내던 때는
//    참이었다. 서버가 바뀐 날 그 문장이 거짓이 됐고 화면은 아무 말도 안 했다.
//
// ⚠️ 공백 구분자를 «T 로 바꿔서» 판다. `new Date('2026-08-01 15:28:47+00:00')` 는 V8 에서는
//    되지만 «표준이 보장하는 것은 T 형» 하나다(ES Date Time String Format). 브라우저가 바뀌면
//    조용히 Invalid Date 가 되는 부류이고, 그때 화면에 나가는 글자는 「Invalid Date」다.
// ═══════════════════════════════════════════════════════════════════════════════

/** 「그릴 것이 없다」 — 이 파일이 짓는 유일한 글자. 값이 아니다. */
export const NO_TIME = '-';

/**
 * 서버가 준 시각 문자열 -> «순간»(Date). 못 읽으면 `null`.
 *
 * 🔴 offset 을 «떼지 않는다». 떼는 순간 같은 글자가 보는 사람의 zone 에 따라 다른 순간이 되고,
 *    그게 이 함수가 존재하는 이유 전부다.
 * ⚠️ offset 이 «아예 없는» 문자열은 그대로 넘긴다 — 엔진이 naive 를 로컬로 읽는 것은 옛 서버의
 *    약속이었고, 여기서 `Z` 를 붙여 UTC 로 «지어내면» 그건 서버가 안 한 말이다.
 */
export function parseServerInstant(value) {
  if (value === null || value === undefined || value === '') return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  const text = String(value).trim();
  if (text === '') return null;
  // 공백 하나만 T 로. 나머지(offset·소수 초)는 손대지 않는다.
  const normalised = text.replace(/^(\d{4}-\d{2}-\d{2}) /, '$1T');
  const at = new Date(normalised);
  return Number.isNaN(at.getTime()) ? null : at;
}

const pad = (n) => String(n).padStart(2, '0');

/**
 * 보는 쪽 zone 의 벽시계. `Date` 의 `getHours()` 류가 이미 그 zone 이라 변환이 없다 —
 * 변환을 «여기서 또» 하면 두 번 옮겨진다.
 */
function parts(at) {
  return {
    y: at.getFullYear(), M: pad(at.getMonth() + 1), d: pad(at.getDate()),
    h: pad(at.getHours()), m: pad(at.getMinutes()), s: pad(at.getSeconds()),
  };
}

/** `YYYY-MM-DD HH:MM:SS` — 이력·상세의 기본. */
export function localStamp(value) {
  const at = parseServerInstant(value);
  if (!at) return NO_TIME;
  const p = parts(at);
  return `${p.y}-${p.M}-${p.d} ${p.h}:${p.m}:${p.s}`;
}

/** `YYYY-MM-DD HH:MM` — 분까지면 되는 표. */
export function localMinute(value) {
  const at = parseServerInstant(value);
  if (!at) return NO_TIME;
  const p = parts(at);
  return `${p.y}-${p.M}-${p.d} ${p.h}:${p.m}`;
}

/** `HH:MM` — when a run was computed (lead 2dd93d4a9: 「factors N · computed HH:MM」). */
export function localHourMinute(value) {
  const at = parseServerInstant(value);
  if (!at) return NO_TIME;
  const p = parts(at);
  return `${p.h}:${p.m}`;
}

/** `HH:MM:SS` — an instant of today on one line (lead 460f202d3: 「Loaded by chain worker HH:MM:SS」). */
export function localClock(value) {
  const at = parseServerInstant(value);
  if (!at) return NO_TIME;
  const p = parts(at);
  return `${p.h}:${p.m}:${p.s}`;
}

/**
 * `MM-DD HH:MM:SS` — 좁은 칸.
 *
 * ⚠️ 셋이 «다른 함수»인 것은 «폭»이지 «저자»가 아니다. 셋 다 `parseServerInstant` 하나를
 *    지나므로 「어느 순간인가」에 대한 답은 한 곳에서 나온다. 자르기로 폭을 맞추면 그 답이
 *    자리마다 갈라진다 — 그게 이 라운드가 고친 결함이다.
 */
export function localShort(value) {
  const at = parseServerInstant(value);
  if (!at) return NO_TIME;
  const p = parts(at);
  return `${p.M}-${p.d} ${p.h}:${p.m}:${p.s}`;
}

/**
 * 두 순간의 폭 — 같은 날이면 `MM-DD HH:MM–HH:MM`, 아니면 `MM-DD HH:MM – MM-DD HH:MM` (실패 요약 한 줄).
 * 한쪽을 못 읽으면 읽은 쪽만, 둘 다 못 읽으면 `NO_TIME`. 자르지 않습니다 — 칸마다 `parts` 에서 짓습니다.
 */
export function localSpan(first, last) {
  const a = parseServerInstant(first);
  const b = parseServerInstant(last);
  if (!a && !b) return NO_TIME;
  const short = (at) => { const p = parts(at); return `${p.M}-${p.d} ${p.h}:${p.m}`; };
  if (!a || !b) return short(a || b);
  const pa = parts(a); const pb = parts(b);
  if (pa.y === pb.y && pa.M === pb.M && pa.d === pb.d) return `${short(a)}–${pb.h}:${pb.m}`;
  return `${short(a)} – ${short(b)}`;
}

/**
 * 보는 쪽의 zone 이름(IANA) — 서버에 「날」을 물을 때 싣습니다(총괄 e573a6edf: 실패 요약의 날이 UTC 였음).
 * 못 얻으면 빈 문자열이고, 그때 서버는 UTC 로 답하며 그 사실을 `day_zone` 으로 돌려줍니다.
 */
export function viewerZone() {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return typeof zone === 'string' ? zone : '';
  } catch (err) {
    return '';
  }
}

/**
 * `localShort`, 다만 서버가 «보낸» 글자를 못 읽으면 그 글자 그대로 — `NO_TIME` 은 «안 보낸» 것에만.
 * 소스 현황의 두 시각(census `measured_at` · Last)이 이 한 함수를 지납니다(총괄 bed890af2).
 */
export function localShortOrAsSent(value) {
  const local = localShort(value);
  const sent = value !== null && value !== undefined && String(value).trim() !== '';
  return local === NO_TIME && sent ? String(value) : local;
}
