// 🔴 브라우저에서는 `loc` 이 «window.location 그 자체»입니다 -- 아래 세 줄의 뜻은 한 글자도
//    바뀌지 않았습니다. 바뀐 것은 «window 가 없는 곳»에서의 거동뿐입니다.
//    왜: 이 파일은 client2 의 17개 모듈이 import 합니다. 최상단에서 `window` 를 읽으면
//    node 가 이 파일을 «import 하는 순간 던지고», 그러면 그 17개를 재는 하니스가 전부 파일을
//    «텍스트로 잘라» 재는 수밖에 없습니다 (소유자 2026-09-02: 「잘라쓰기 하니스 절대금지」).
//    ⚠️ 여기에 맨 `window.` 를 다시 쓰면 그 하니스들이 «한 줄로» 잘라쓰기로 되돌아갑니다.
const loc = typeof window !== 'undefined' && window.location
  ? window.location
  : { port: '', origin: '', protocol: '', host: '' };
const isDevServer = loc.port === '5173';
export const API_BASE = isDevServer ? 'http://127.0.0.1:8080' : loc.origin;
export const WS_URL = isDevServer ? 'ws://127.0.0.1:8080/ws' : `${loc.protocol === 'https:' ? 'wss:' : 'ws:'}//${loc.host}/ws`;
// 🔴 `import.meta.env.VITE_USER` 라는 «글자 그대로»가 계약입니다. vite.config.js 의
//    `define` 이 이 표현식을 빌드 때 문자열 리터럴로 «치환»하므로, 한 글자라도 다르게 적으면
//    (`env.VITE_USER` 같은 축약) 치환이 «조용히» 안 일어나고 모든 사용자가 `web_client` 가
//    됩니다 -- 오류 없이, 화면도 멀쩡하게. 그래서 접근을 try 로 감싸기만 했습니다.
//    node 에는 `import.meta.env` 자체가 없어 «읽는 순간» TypeError 가 나고, 그 한 줄이
//    이 파일을 import 하는 17개 모듈을 전부 「텍스트로 잘라 재는」 하니스로 몰아넣었습니다.
let viteUser;
try { viteUser = import.meta.env.VITE_USER; } catch (e) { viteUser = undefined; }
export const CURRENT_USER = viteUser || 'web_client';
export const pageLimit = 1000; // Chunk size

// ── WebSocket reconnect tuning ────────────────────────────────────────────────
// These live HERE, next to `pageLimit`, because they are the same kind of thing: a knob an
// operator may want to move without reading the reconnect logic. They are read only by
// `websocket.js`.
//
// WHY THE CEILING IS 5s AND NOT THE 30s IT WAS. 30s is an internet-scale number and this is a
// localhost stack; it was costing a stall two orders of magnitude longer than the thing being
// waited for. Measured on the live stack 2026-08-04:
//   · server lifespan startup, n=324 real process starts in server.log:
//     median 12ms, p90 22ms, p99 195ms, max 3094ms;
//   · WebSocket handshake once the server is accepting: median 2.54ms, max 4.15ms;
//   · a retry against a down server costs one ECONNREFUSED: median 0.49ms, max 2.71ms.
// So the client was waiting up to 30s for something that is ready in well under a second, and
// the log shows it: of 164 restarts where a browser reconnected, 20.7% stalled >= 5s and 10.4%
// stalled >= 25s. 5s clears even the 3094ms outlier on the first retry, and the price of
// probing that often is ~12 refused connects a minute — about 6ms of work per minute per tab.
//
// WHY A CEILING AT ALL, RATHER THAN A FLAT 1s. A permanently-down server must not be hammered
// forever, and the worse case is a server that ACCEPTS and immediately drops: each cycle costs
// a full handshake plus `checkServerHealth()` plus `fetchData(true)`, not a 0.49ms refusal.
// The backoff is what makes that self-limiting.
export const WS_RECONNECT_BASE_MS = 1000;
export const WS_RECONNECT_CEILING_MS = 5000;
// Jitter is DOWNWARD ONLY (delay x [0.75, 1.0]), which is not the usual symmetric band, and the
// asymmetry is the point: it de-synchronises many open tabs so they cannot retry in lockstep,
// while leaving `WS_RECONNECT_CEILING_MS` a TRUE upper bound on the wake-up gap. A symmetric
// +-25% band would make the real worst case 6.25s while the constant still read 5000.
export const WS_RECONNECT_JITTER = 0.25;
// A connection that opened and died faster than this did not prove the server is healthy, so
// it must not be allowed to reset the ladder. See the flap guard in `websocket.js`.
export const WS_HEALTHY_SESSION_MS = 1000;
// Floor between two signal-triggered immediate retries, so rapid alt-tabbing cannot turn the
// wake signal into an unthrottled retry loop.
export const WS_WAKE_MIN_GAP_MS = 500;

// ── The connect watchdog ────────────────────────────────────────────────────────
// EVERYTHING ABOVE IS DRIVEN BY `onclose`, AND A HANG DELIVERS NO `onclose`. Measured in
// production 2026-08-04: reaching the app as `localhost` resolves to the IPv6 loopback first
// while the server binds IPv4 only, and the socket then enters CONNECTING and never leaves —
// no `onopen`, no `onclose`, no `onerror`. The same server by its external IP connects fine.
// The server-side cause is being fixed separately; this constant is about the client surviving
// it, because any blackholed route reproduces it: a proxy that neither completes nor rejects an
// Upgrade, a firewall that drops, a half-open NAT.
//
// The consequence of no `onclose` is total: `scheduleReconnect` is only ever called from
// `onclose`, so the ladder never advances and no retry is ever queued; and `wakeNow` refuses to
// act on a CONNECTING socket, so focus and `online` become no-ops too. The 5s ceiling, the wake
// signals and the flap guard are all bypassed by a socket that simply never resolves.
//
// WHY 8000 AND NOT LESS. Killing a connection that was about to succeed converts a working page
// into a permanent reconnect loop — a worse failure than the hang — so this is chosen from the
// TOP of the measured range, not the middle. Against the measurements in hand:
//   · a completed handshake against the live :8080 is 2.54ms median, 4.15ms max. 8000ms is
//     ~1900x the slowest real handshake ever recorded on this stack.
//   · the largest real latency anywhere here is server lifespan startup: 12ms median, 3094ms
//     max over n=324 process starts. That normally shows up as a REFUSED connect (0.49ms) and
//     never reaches this timer at all — but even under the pessimistic reading, where the
//     listener accepts and the app stalls the Upgrade for the whole 3094ms, 8000ms still leaves
//     2.6x headroom.
// WHY NOT MORE. The bound is dead time the user stares at before the ladder is even allowed to
// start; worst-case recovery is 8000ms + one rung (<= WS_RECONNECT_CEILING_MS), about 13s.
// Raising it buys headroom nothing has measured a need for and pays in visible dead time.
//
// IT IS A CONSTANT HERE, NOT A LITERAL IN `websocket.js`, so a site whose real connects are
// genuinely slower than anything measured can raise it without a code change.
export const WS_CONNECT_TIMEOUT_MS = 8000;
// How long a socket must have been CONNECTING before a WAKE SIGNAL is allowed to abandon it.
// `wakeNow` refuses to act on a CONNECTING socket because the point is to shorten a wait, never
// to open a second socket beside one still negotiating — but "CONNECTING" and "negotiating"
// stopped being the same thing once a blackholed route could hold a socket there forever, and
// the measurements say the difference is not subtle: a real handshake is 4.15ms at worst, so
// 1000ms is ~240x anything a live negotiation has ever taken. Below this the old refusal stands
// unchanged. See the long note in `wakeNow` for why the signal gets to break a stale one at all
// when the watchdog above would eventually do it anyway.
export const WS_CONNECT_STALE_MS = 1000;

// ── The spec-only save's response bound ─────────────────────────────────────────
// SAME FAILURE CLASS AS THE WATCHDOG ABOVE, ON THE OTHER PROTOCOL. Reported live 2026-08-04:
// 📐 규격만 저장 sticks on "Saving..." forever WHILE THE SAVE ACTUALLY SUCCEEDS. The button is
// restored in a `finally`, so the only way it stays stuck is that the `finally` is never
// reached — the `await fetch(...)` never settles. A hung HTTP response is the same blackholed
// route that holds a WebSocket in CONNECTING.
//
// 🔴 NO PRODUCTION MEASUREMENT EXISTS FOR THIS ENDPOINT, AND ONE IS NOT INVENTED HERE.
//    `server/server.log` carries 486 `data/updates` lines and every one of them is
//    `http://testserver` — FastAPI's TestClient, not browser traffic. There is no request
//    duration instrumentation on this route at all. Quoting a test-suite number as if it
//    described production is how this repo has previously argued for defects that did not
//    exist, so the bound below is argued from the SHAPE of the work and the COST of being
//    wrong instead, and it is labelled as such.
//
// WHY 15000. The work is a SINGLE-ROW upsert through the same batch route ⚡ Push uses for
// thousands of cells. A server taking longer than 15s for one row is not slow, it is wedged,
// and the operator needs to be told that rather than keep staring at a disabled button. For
// scale, 15s is ~5x the largest real latency ever measured anywhere on this stack (3094ms
// lifespan startup, n=324) — an unrelated and much heavier operation, and the only
// order-of-magnitude anchor actually in hand.
//
// WHY BEING WRONG IS CHEAPER HERE THAN IN THE SOCKET CASE. Two reasons, and they are why this
// bound can be tighter relative to its evidence than WS_CONNECT_TIMEOUT_MS is:
//   · the write is IDEMPOTENT — the endpoint upserts on `business_key_val` and the payload
//     carries the whole spec, so a repeat save produces the same row rather than a second one;
//   · the abort message does not claim the write was discarded. It says the outcome is unknown
//     and asks the operator to verify, so a premature abort costs one re-save and can never
//     cause a wrong belief about what is stored.
// A too-LONG bound, by contrast, is the stranded UI this exists to end.
export const MAP_SPEC_SAVE_TIMEOUT_MS = 15000;
