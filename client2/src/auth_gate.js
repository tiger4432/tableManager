// The screen's login door for company SSO (owner 10-07 「sso 붙이자」, lead 2095014ee).
// One seat per page: it wraps `fetch` once, and the SSO gate's 401 sends the page to the login with the way back. The
// socket's close code 4401 goes the same way (websocket.js). Everything else passes untouched - the same Response, its
// body unread - so with SSO off the page behaves as before.

export const LOGIN_PATH = '/auth/login';
/** The close code /ws answers a handshake without a login with. */
export const WS_LOGIN_REQUIRED = 4401;
const AUTH_PREFIX = '/auth/';
const SEAT = '__assyLoginGate';

/** Where the login is, carrying the page's own path back (same-origin relative only). */
export function loginTarget(loc) {
  return `${LOGIN_PATH}?next=${encodeURIComponent(`${loc.pathname}${loc.search}${loc.hash}`)}`;
}

/** THE ONE PLACE that asks 「is this our session's refusal」: the SSO gate marks its 401 (not signed in) and its 403
 *  (not an administrator) `WWW-Authenticate: Session`, as the admin token gate marks its own `X-Admin-Token`
 *  (lead 2095014ee). A `session` that is only a word inside another challenge is not it. The login door, the admin
 *  door and the failure classifier all call this. */
export function isSessionRejection(res) {
  if (!res || (res.status !== 401 && res.status !== 403)) return false;
  const challenge = res.headers && res.headers.get ? (res.headers.get('WWW-Authenticate') || '') : '';
  return /(^|[\s,])session($|[\s,])/i.test(challenge);
}

const seatOf = (win) => win[SEAT] || (win[SEAT] = { leaving: false, wrapped: false });

/** Leave for the login - once per page, however many requests were refused at the same time. */
export function goToLogin(win) {
  const seat = seatOf(win);
  if (seat.leaving) return;
  seat.leaving = true;
  win.location.assign(loginTarget(win.location));
}

const isAuthRequest = (input, win) => {
  const raw = typeof input === 'string' ? input : (input && input.url) || String(input);
  try { return new URL(raw, win.location.href).pathname.startsWith(AUTH_PREFIX); } catch (e) { return false; }
};

/** Wrap the page's `fetch` once. A second call on the same page wraps nothing. */
export function installLoginGate(win) {
  const seat = seatOf(win);
  if (seat.wrapped) return;
  seat.wrapped = true;
  const send = win.fetch.bind(win);
  win.fetch = async (input, init) => {
    const res = await send(input, init);
    if (res.status === 401 && isSessionRejection(res) && !isAuthRequest(input, win)) goToLogin(win);
    return res;
  };
}
