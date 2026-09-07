// ═══════════════════════════════════════════════════════════════════════════════
// S-36 — 대기열의 «소급 행»이 자기가 무엇인지 말한다.
//
// 🔴 왜 있나. 소급 실행은 자기 payload 에 «누가 · 무슨 op · 어느 인자»를 이미 들고 오는데,
//    대기열 라우트가 `transaction_id` 하나만 읽고 나머지를 버렸습니다. 그래서 화면의 그 행은
//    「표 없음(—) · 이벤트 하나」였고, 운영자는 그것이 «무엇인지» 알 길이 없었습니다 —
//    답이 그 행 «안»에 있는데도. 서버가 이제 싣고, 이 파일이 그 한 줄을 만듭니다.
//
// 🔴 세 상태입니다. 키가 «없으면» 이 묶음에 소급 행이 «없다»(해당 없음)이고, 있는데 칸이
//    `null` 이면 「물었는데 아무도 안 적었다」입니다. 앞은 아무것도 안 그리고, 뒤는 «없음»을
//    그립니다 — 서버 주석이 그 둘을 다른 사실로 적어 두었고, 화면도 그렇게 갈라야 합니다.
//
// ⚠️ 그리고 «배열»입니다. 지시서에는 객체 하나로 적혀 있었는데 서버는
//    `g.setdefault("retroactive", []).append(...)` 로 «모읍니다» — 한 트랜잭션 묶음에 소급 행이
//    여럿 섞일 수 있습니다. 객체로 읽었으면 둘째부터 «조용히» 사라졌을 것입니다.
//
// ⛔ 뜻을 «짓지» 않습니다. `op` 도 `params` 도 서버 값 그대로이고, 이 파일이 하는 유일한 가공은
//    «길이 자르기»입니다. 「이 op 는 이런 뜻」을 여기서 번역하기 시작하면 그 사전이 서버의
//    어휘와 갈라지는 날 화면이 조용히 틀린 이름을 부릅니다.
// ═══════════════════════════════════════════════════════════════════════════════

/** 이 행이 소급이라는 표시. 낱말 하나. */
const MARK = '소급';
/** 「물었는데 아무도 안 적었다」. 「해당 없음」과 다릅니다 — 그쪽은 아무것도 안 그립니다. */
const UNSAID = '없음';
/** 인자는 한 줄에 얹히는 만큼만. 자르는 것은 «길이»이고 뜻이 아닙니다. */
const PARAMS_CAP = 60;

/** 서버가 준 인자를 «그대로», 다만 한 줄에 얹힐 만큼만. */
export function paramsSummary(params) {
  if (params === null || params === undefined) return '';
  let text;
  try { text = typeof params === 'string' ? params : JSON.stringify(params); }
  catch (e) { return ''; }
  if (!text || text === '{}' || text === '[]') return '';
  return text.length > PARAMS_CAP ? `${text.slice(0, PARAMS_CAP)}…` : text;
}

/**
 * 대기열 한 행의 소급 설명. 소급이 아니면 «빈 문자열» — 부르는 쪽이 오늘 그리던 것을 그립니다.
 * @param {Array|undefined} list 서버의 `waiting_transactions[].retroactive`
 */
export function retroactiveNote(list) {
  if (!Array.isArray(list) || list.length === 0) return '';
  const one = (e) => {
    const r = e && typeof e === 'object' ? e : {};
    const op = r.op != null && String(r.op) !== '' ? String(r.op) : UNSAID;
    const who = r.requested_by != null && String(r.requested_by) !== ''
      ? String(r.requested_by) : UNSAID;
    return [op, who, paramsSummary(r.params)].filter(Boolean).join(' · ');
  };
  return `${MARK} · ${list.map(one).join(' | ')}`;
}
