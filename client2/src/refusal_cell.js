// ═══════════════════════════════════════════════════════════════════════════════
// S-39 — 「이 소스의 행이 왜 안 들어갔나」, 그 소스의 «행»에서.
//
// 🔴 문지기는 거절을 «이름으로» 세고 있었습니다(닫힌 열둘) — 표본과 문장까지 들고서. 아무도
//    그 수를 읽지 않았습니다. 그래서 화면은 「몇 행이 안 들어갔나」는 보여 주고 「왜」는 영영
//    말하지 않았고, 그 틈에서 소유자는 시간 선언을 의심했습니다 — 열둘 중 시간에 관한 것은 «둘».
//
// ⛔ 이 파일은 사유를 «번역하지» 않습니다. 낱말은 응답의 «키 그대로»이고, 표본 문장은 문지기가
//    쓴 그대로입니다 — 그 문장이 이미 「어디에 무엇을 적으면 이 원자가 들어간다」를 말합니다.
//    여기서 사전을 만들면 열셋째가 생기는 날 화면이 그것을 «모르는 채 조용히» 빠뜨립니다.
//
// 🔴 세 상태이고, 셋이 «다른 픽셀»입니다:
//      안 잼      응답이 없다            -> 아무것도 없음 (`since` 도 없음)
//      쟀는데 0   응답은 있고 이 소스는 0 -> 「거절」은 «안 그림». `since` «만» 남음
//      쟀고 N     -> 「거절 N · <사유> k …」
//    가운데를 0 으로 그리면 「없음」과 「안 잼」이 같은 픽셀이 되고, 그 둘은 조작자에게
//    정반대의 지시입니다(하나는 「좋다」, 하나는 「이 프로세스는 아직 아무것도 안 했다」).
// ═══════════════════════════════════════════════════════════════════════════════

import { isCount } from './absent.js';

const MARK = '거절';
const SINCE_MARK = '이 프로세스가 뜬 뒤';
/** 준비기가 «자기 표지로» 뺀 행. 거절과 다른 사실이라 다른 낱말이다. */
const EXCLUDED_MARK = '제외';
/** 툴팁 한 칸에 얹히는 표본 수. 자르는 것은 «개수»이고 문장은 «그대로»입니다. */
const SAMPLES_SHOWN = 3;

/**
 * C-39. 「거절 N · <사유> k · <사유> k」 — «철자 한 곳».
 *
 * 🔴 왜 여기 있나. 시험 실행의 머리도 «같은 문장»을 씁니다. 그 화면이 자기 낱말을 적기
 *    시작하면 「거절」이 두 철자가 되고, 한쪽만 고쳐지는 날 두 화면이 «같은 사실»을 다르게
 *    말합니다 — 오류는 «안 납니다». 두 봉투의 «모양»은 다르지만(문지기는
 *    `{사유: {count, samples}}`, 시험 실행은 `{사유: count}`) 문장은 하나입니다.
 *
 * @param {object} counts `{<사유>: <수>}` — 사유 낱말은 «응답의 키 그대로»
 * @returns {string} 셀 수 있는 것이 없으면 «빈 문자열»
 */
export function refusalSummary(counts) {
  const src = counts && typeof counts === 'object' ? counts : {};
  const named = Object.keys(src)
    .map(k => ({ reason: k, count: Number(src[k]) || 0 }))
    .filter(r => r.count > 0)
    .sort((a, b) => b.count - a.count || (a.reason < b.reason ? -1 : 1));
  const total = named.reduce((n, r) => n + r.count, 0);
  if (total === 0) return '';
  return [`${MARK} ${total}`, ...named.map(r => `${r.reason} ${r.count}`)].join(' · ');
}

/**
 * C-39. 「제외 M」 — 준비기의 «자기 표지»가 뺀 행.
 *
 * 🔴 키가 «없는» 것과 «0» 이 다릅니다. 표지를 선언하지 않은 소스는 «안 재진» 것이고,
 *    거기에 0 을 그리면 「재 봤는데 없다」가 됩니다 — 서버가 그 둘을 키의 있음/없음으로
 *    가르고 있고(그 주석이 「이 픽셀 뒤로 행을 잃은 적이 있다」라고 적습니다), 화면도 그렇게 갈립니다.
 */
export function excludedNote(excluded) {
  if (!excluded || typeof excluded !== 'object') return '';
  const rows = Number(excluded.rows);
  if (!Number.isFinite(rows) || rows <= 0) return '';
  return `${EXCLUDED_MARK} ${rows}`;
}

/** 「N 건까지」 — «자른 것은 개수»라는 사실. 문장이 아니라 값 옆의 낱말입니다. */
const CAP_MARK = '건까지';

/**
 * C-49. 시험 실행의 «표본»을 표의 행으로. 「몇 건」 옆에 「어느 행이」.
 *
 * 🔴 낱말은 여기 «한 파일»에 삽니다 — 시험 실행 화면이 자기 철자를 쓰기 시작하면 「거절」이
 *    두 벌이 되고, 한쪽만 고쳐지는 날 두 화면이 같은 사실을 다르게 말합니다(오류는 «안 납니다»).
 *    ⚠️ 봉투의 «모양»은 다릅니다 — 문지기는 `{사유: {count, samples}}`, 시험 실행은
 *    `{count, reasons, samples[]}` 의 «평평한 목록»입니다. 같은 것은 낱말이지 모양이 아닙니다.
 *
 * 🔴 서버가 이 봉투에 «절단 플래그를 안 싣습니다»(backfill 의 `refused_samples_capped` 는
 *    «다른» 봉투의 것입니다). 그래서 «세어서» 압니다: `count` > 표본 수. 안 세면
 *    「거절이 20건이었다」와 「20건까지만 봤다」가 화면에서 «같아 보입니다».
 *
 * ⛔ 문장을 «다시 쓰지» 않습니다. `detail` 은 문지기가 쓴 그대로이고, 그 안에 «분자 키»가
 *    들어 있습니다 — 서버가 그것을 «자기 칸»으로 내놓기 전까지 화면이 문장을 파서 꺼내면
 *    그 문장의 두 번째 저자가 됩니다.
 *
 * @param {object} refused 시험 실행 응답의 `refused`, 그대로
 * @returns {{rows: {reason,rows,path,detail}[], capped: boolean, note: string}}
 */
export function refusalSamples(refused) {
  const src = refused && typeof refused === 'object' ? refused : {};
  const items = (Array.isArray(src.samples) ? src.samples : [])
    .filter(s => s && typeof s === 'object')
    .map(s => {
      // 주소는 «첫 번째»입니다 — 거절 하나가 여럿을 들 수 있고, 읽는 쪽의 모양은 하나이며
      // `gate.MoleculeRefused` 도 같은 자리에서 `code`·`path` 를 고릅니다.
      const first = (Array.isArray(s.addresses) ? s.addresses : [])
        .find(a => a && typeof a === 'object') || {};
      return Object.freeze({
        reason: s.reason == null ? '' : String(s.reason),
        // 「행 N」은 이 분자가 «덮은 소스 행 수»입니다. 수가 아니면 «빈 칸» — 0 이 아닙니다.
        // ⚠️ `Number(null)` 은 «0 이고 유한합니다». 「수인가」의 철자는 `absent.js` 하나뿐이고,
        //    그것을 안 쓰면 「안 셌다」가 「0 행」으로 그려집니다 — 이 하니스가 그 자리를 잡았습니다.
        rows: isCount(s.rows) ? String(Number(s.rows)) : '',
        path: first.path == null ? '' : String(first.path),
        detail: s.detail == null ? '' : String(s.detail),
      });
    });
  const capped = isCount(src.count) && Number(src.count) > items.length;
  return Object.freeze({
    rows: Object.freeze(items),
    capped,
    note: capped ? `${items.length} ${CAP_MARK}` : '',
  });
}

/**
 * @param {object} report `GET /admin/ontology-explorer/refusals` 응답, 그대로
 * @param {string} sourceId 그 행의 소스 id (문지기가 세는 키와 «같은 이름»)
 * @returns {{text: string, title: string, since: string}}
 */
export function refusalCell(report, sourceId) {
  const none = { text: '', title: '', since: '' };
  if (!report || typeof report !== 'object') return Object.freeze({ ...none });
  const since = report.since != null && String(report.since) !== ''
    ? `${SINCE_MARK} ${String(report.since)}` : '';
  const sources = report.sources && typeof report.sources === 'object' ? report.sources : {};
  const entry = sourceId != null ? sources[String(sourceId)] : null;
  if (!entry || typeof entry !== 'object') return Object.freeze({ text: '', title: '', since });

  const reasons = entry.reasons && typeof entry.reasons === 'object' ? entry.reasons : {};
  // 🔴 이 봉투를 «저 봉투의 모양»으로 옮기고 문장은 `refusalSummary` 가 짓습니다 — 시험 실행
  //    머리와 «같은 철자»여야 하고, 다른 것은 모양뿐입니다(여기 `{사유: {count}}`, 저기 `{사유: count}`).
  // ⚠️ 거르기도 세기도 «여기서 다시 하지 않습니다». 한 번 더 하면 그 갈래가 «죽은 채»로 남고,
  //    실제로 그랬습니다 — 그 두 줄을 지우는 변이가 답을 «하나도» 안 바꿔 빠져나갔습니다.
  const counts = {};
  for (const k of Object.keys(reasons)) {
    counts[k] = Number(reasons[k] && reasons[k].count) || 0;
  }
  // ⚠️ 여기 「빈 문장이면 일찍 돌아간다」가 «있었고 지웠습니다» — 그대로 떨어져도 `named` 가
  //    비어 표본이 없고 «같은 값»이 나옵니다. 그 갈래를 지우는 변이가 답을 하나도 안 바꿔
  //    빠져나갔고, 등가 변이는 공허한 단언으로 쫓을 것이 아니라 «없앨 코드»입니다.
  //    「쟀는데 0 이면 안 그린다」를 실제로 정하는 자리는 `refusalSummary` 의 `total === 0` 입니다.
  const text = refusalSummary(counts);
  // 표본은 「많은 사유부터」 — 뜻을 짓는 것이 아니라 순서입니다.
  const named = Object.keys(counts)
    .filter(k => counts[k] > 0)
    .sort((a, b) => counts[b] - counts[a] || (a < b ? -1 : 1))
    .map(k => ({ reason: k }));
  // 🔴 표본 문장은 «그대로». 문지기가 조작자의 다음 행동을 이미 그 안에 적어 두었고,
  //    다시 쓰거나 자르면 수는 남고 «수리 방법»이 사라집니다.
  const details = [];
  for (const r of named) {
    const samples = Array.isArray(reasons[r.reason].samples) ? reasons[r.reason].samples : [];
    for (const s of samples) {
      if (s && s.detail != null && String(s.detail) !== '') details.push(String(s.detail));
      if (details.length >= SAMPLES_SHOWN) break;
    }
    if (details.length >= SAMPLES_SHOWN) break;
  }
  return Object.freeze({ text, title: details.join('\n'), since });
}
