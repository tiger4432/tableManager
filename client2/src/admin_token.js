// ═══════════════════════════════════════════════════════════════════════════════
// ADMIN TOKEN — 「어디에 있나」를 아는 «한 곳»
//
// 🔴 이 파일은 «읽기»와 «이름»만 압니다. 묻지(프롬프트) 않고, 쓰지 않습니다 —
//    쓰는 곳은 `admin.js` 하나이고, 그 쪽이 이 상수를 씁니다.
//
// 🔴 왜 따로 생겼나: 그리드 페이지가 「토큰이 있나」를 묻게 되면서(소유자 요구, 2026-09-01
//    — 고른 줄을 «그 자리»에서 돌린다) 같은 키 문자열이 두 파일에 생길 참이었습니다.
//    키가 두 벌이면 한쪽만 바뀌는 날 「토큰이 있는데 없다고 하는 화면」이 되고,
//    그건 오류를 내지 않습니다 — 조용히 틀립니다.
// ═══════════════════════════════════════════════════════════════════════════════

export const ADMIN_TOKEN_KEY = 'assy.adminToken';

// 헤더로만 보냅니다. 질의 문자열은 서버 접근 로그에 남고 헤더는 남지 않습니다.
export const ADMIN_TOKEN_HEADER = 'X-Admin-Token';

/** 저장된 토큰, 없으면 빈 문자열. 저장소가 막혀 있어도 «던지지 않습니다». */
export function readAdminToken() {
  try { return localStorage.getItem(ADMIN_TOKEN_KEY) || ''; } catch (e) { return ''; }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 🔴 C-122. 그리고 «어떻게 붙여 보내나»도 여기입니다.
//
// ⚠️ 위 머리글이 「이 파일은 «읽기»와 «이름»만 압니다」라고 적어 두었고, 이 절이 그것을
//    넓힙니다. 그 문장이 막으려던 것은 «프롬프트»와 «저장»이었고 그 둘은 여전히 밖입니다 —
//    묻는 것은 주입받고, 쓰는 것은 `admin.js` 하나뿐입니다. 넓어진 것은 「보내기」이고,
//    그 이유는 이 절이 없어서 «두 번째 전송»이 생겼기 때문입니다.
//
// 🔴 실측(2026-09-16): `/admin/**` 을 «맨 fetch»로 부르는 자리가 저장소 전체에 «하나»
//    있었습니다 — `main.js` 의 소급 실행. 그 자리는 아래 넷을 «전부» 안 받고 있었습니다:
//      ① 토큰 헤더 부착              ② 503 일 때 서버 본문을 띄우기
//      ③ 날아가는 중에 토큰이 바뀌면 «조용히» 재시도   ④ 게이트 거절이면 «한 번만» 다시 묻기
//    그래서 같은 실패가 두 화면에서 «다른 답»을 냈습니다. 판별식 ④ 그대로입니다.
//
// ⛔ 새 구현을 짓지 않았습니다 — `admin.js` 의 몸통을 «그대로» 옮겼습니다. 페이지마다
//    다른 것은 «묻는 방법»과 «문장이 앉을 자리»뿐이라, 그 둘만 주입받습니다.
// ═══════════════════════════════════════════════════════════════════════════════

/** True only for rejections the admin GATE issued.
 *
 * Status alone is not enough: `_resolve_admin_script_path` answers 403 when an
 * isolated server refuses a write into the live mappers/ tree, which has nothing
 * to do with the token. Treating that as an auth failure made the page demand a
 * token and then OVERWRITE the correct stored one with whatever was retyped.
 * The server marks its own rejections with `WWW-Authenticate: X-Admin-Token`.
 */
export function isGateRejection(res) {
  if (res.status !== 401 && res.status !== 403) return false;
  const challenge = res.headers && res.headers.get
    ? (res.headers.get('WWW-Authenticate') || '') : '';
  return challenge.toLowerCase().includes(ADMIN_TOKEN_HEADER.toLowerCase());
}

/** 헤더«로만» 보냅니다. 질의 문자열은 서버 접근 로그에 남고 헤더는 남지 않습니다. */
export function withAdminToken(init) {
  const token = readAdminToken();
  if (!token) return init;
  const next = Object.assign({}, init || {});
  next.headers = Object.assign({}, (init && init.headers) || {},
    { [ADMIN_TOKEN_HEADER]: token });
  return next;
}

// 토큰이 바뀔 때마다 오릅니다. 바뀌기 «전»에 날아간 응답은 낡은 증거입니다 — 새 토큰에
// 대해 아무 말도 안 하므로 두 번째 프롬프트를 띄우면 안 됩니다. 이것이 없으면
// 「일곱 요청에 프롬프트 하나」가 «타이밍 운»이 됩니다.
let generation = 0;
/** 지금 세대. 토큰이 바뀌었는지를 «비교»하는 쪽이 씁니다. */
export function tokenGeneration() { return generation; }
/** 토큰을 새로 저장한 쪽이 «한 번» 부릅니다. */
export function bumpTokenGeneration() { generation += 1; }

/**
 * `/admin/**` 로 가는 «유일한» 전송.
 *
 * @param {string} url
 * @param {object} [init]
 * @param {{onServiceUnavailable?: (detail: string) => void,
 *          askForToken?: (message: string) => Promise<string>|string}} [deps]
 *
 * 🔴 `deps` 가 둘뿐인 이유: 페이지마다 다른 것이 그 둘뿐입니다.
 *    · `onServiceUnavailable` — 503 본문을 «어디에» 세우나. 어드민은 토스트, 그리드는
 *      그 줄 자체가 답을 들고 있어 «안 넘깁니다»(안 그러면 같은 문장이 두 번 뜹니다 — 실측).
 *    · `askForToken` — 그리드 페이지에는 모달이 없습니다. 안 넘기면 «안 묻습니다».
 */
export async function adminFetch(url, init, deps = {}) {
  const generationAtSend = generation;
  let res = await fetch(url, withAdminToken(init));

  // 503 = the server has no token configured and this route refuses to run
  // without one. The body names the variable and says to restart; surfacing it
  // here is the whole point of the 503 split, and the call sites would otherwise
  // show a generic "저장 중 오류 발생".
  if (res.status === 503) {
    if (deps.onServiceUnavailable) {
      try {
        const body = await res.clone().json();
        if (body && body.detail) deps.onServiceUnavailable(body.detail);
      } catch (e) { /* not a JSON body - let the caller report it */ }
    }
    return res;
  }

  if (!isGateRejection(res)) return res;

  // Someone else already replaced the token while this was in flight. Retry
  // silently with the new one instead of accusing it of being wrong.
  if (generation !== generationAtSend) {
    return fetch(url, withAdminToken(init));
  }

  if (!deps.askForToken) return res;

  const message = readAdminToken()
    ? '관리자 토큰이 거부되었습니다. 다시 입력해 주세요.'
    : '관리자 토큰을 입력하세요.';
  const token = await deps.askForToken(message);
  // Retry once only. A second rejection returns to the caller so the page shows
  // its own error instead of looping the operator on a modal.
  if (token) res = await fetch(url, withAdminToken(init));
  return res;
}
