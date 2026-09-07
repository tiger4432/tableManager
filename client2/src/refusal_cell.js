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

const MARK = '거절';
const SINCE_MARK = '이 프로세스가 뜬 뒤';
/** 툴팁 한 칸에 얹히는 표본 수. 자르는 것은 «개수»이고 문장은 «그대로»입니다. */
const SAMPLES_SHOWN = 3;

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
  // 🔴 응답의 «키 그대로». 정렬은 「많은 것부터」이고, 그건 뜻을 짓는 것이 아니라 순서입니다.
  const named = Object.keys(reasons)
    .map(k => ({ reason: k, count: Number(reasons[k] && reasons[k].count) || 0 }))
    .filter(r => r.count > 0)
    .sort((a, b) => b.count - a.count || (a.reason < b.reason ? -1 : 1));
  const total = named.reduce((n, r) => n + r.count, 0);
  if (total === 0) return Object.freeze({ text: '', title: '', since });

  const text = [`${MARK} ${total}`, ...named.map(r => `${r.reason} ${r.count}`)].join(' · ');
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
