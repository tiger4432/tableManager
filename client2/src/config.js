const isDevServer = window.location.port === '5173';
export const API_BASE = isDevServer ? 'http://127.0.0.1:8080' : window.location.origin;
export const WS_URL = isDevServer ? 'ws://127.0.0.1:8080/ws' : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;
export const CURRENT_USER = import.meta.env.VITE_USER || 'web_client';
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
