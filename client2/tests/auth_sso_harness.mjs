// Company SSO on the screen (owner 10-07 「sso 붙이자」, lead 2095014ee; the implementer's spelling 10-07).
// ONE function asks 「is this our session's refusal」 (`isSessionRejection`: a 401/403 marked WWW-Authenticate: Session)
// and the login door, the admin door and the failure classifier all call it. The login door wraps `fetch` once; the
// SSO gate's 401 leaves for the login with the way back, once, never for an /auth/* request, and every response comes
// back as the same object with no body read. The socket's 4401 takes the same door. The admin door never asks for a
// token over SSO's refusals and says its 403 once. The account part draws nothing with SSO off, shows a new key once,
// and two of them on one page do not touch each other. Each layer has a defect that must go red at its named line.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import * as REAL_CFG from '../src/config.js';
import * as REAL_GATE from '../src/auth_gate.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const GATE = path.join(SRC, 'auth_gate.js');
const BADGE = path.join(SRC, 'account_badge.js');
const ADMIN = path.join(SRC, 'admin_token.js');
const CLASSIFY = path.join(SRC, 'config_resolve_view.js');
const WS = path.join(SRC, 'websocket.js');
// What the sign-in routes really answer, captured through the server's own suite (fixtures/capture_sso_spelling.py).
const FX = JSON.parse(readFileSync(path.join(HERE, 'fixtures', 'sso_spelling.json'), 'utf8'));

let ran = 0;
let failed = [];
const NAMES = [];
let quiet = false;
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { if (!quiet) console.log(`  ok   ${name}`); return; }
  failed.push(name);
  if (!quiet) console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// A response the way the browser hands it: a body that can be read once, a clone that can be read on its own.
const response = (status, body, headers = {}) => {
  const make = () => {
    const r = { status, ok: status >= 200 && status < 300, bodyUsed: false,
      headers: { get: (k) => headers[k] ?? headers[String(k).toLowerCase()] ?? null },
      async json() { if (r.bodyUsed) throw new TypeError('body used'); r.bodyUsed = true; return body === undefined ? null : JSON.parse(JSON.stringify(body)); },
      clone() { first.cloned += 1; return make(); } };
    return r;
  };
  const first = make();
  first.cloned = 0;
  return first;
};
const LOGIN_REQUIRED = FX.api_signed_out.body;
const ADMIN_REQUIRED = FX.admin_not_listed.body;
const TOKEN_GATE = [401, { detail: 'Admin token required' }, { 'WWW-Authenticate': 'X-Admin-Token' }];
const SESSION = { 'WWW-Authenticate': FX.api_signed_out.challenge };

/** A page: its location, its `fetch` answering from `answer(url, init)`, and every navigation it was asked for. */
const page = (answer, at = { pathname: '/admin.html', search: '?x=1', hash: '#ontology' }) => {
  const went = [];
  const win = { location: { ...at, href: `http://box${at.pathname}${at.search}${at.hash}`, assign: (u) => went.push(u) },
    fetch: async (url, init) => answer(String(url), init) };
  return { win, went };
};

async function suite({ gate, Badge, admin, wsDrive, classify }) {
  console.log('\n── X. the captured answers are the server\'s ──');
  ok('X1 the SSO gate marks its 401 and its 403 alike, and the socket closes with the code the screen listens for',
    FX.api_signed_out.status === 401 && FX.admin_not_listed.status === 403 && FX.api_signed_out.challenge === FX.admin_not_listed.challenge
    && gate.isSessionRejection(response(401, LOGIN_REQUIRED, SESSION)) && FX.ws_signed_out.closed === true
    && FX.ws_signed_out.code === gate.WS_LOGIN_REQUIRED, JSON.stringify([FX.api_signed_out.challenge, FX.ws_signed_out]));
  ok('X2 the key list carries every field the part reads', ['id', 'name', 'created_at', 'last_used_at']
    .every((k) => Object.prototype.hasOwnProperty.call(FX.keys_listed.body[0], k)), JSON.stringify(FX.keys_listed.body[0]));

  console.log('\n── W. the login door ──');
  {
    const seen = [];
    const { win, went } = page((url) => { const r = url.endsWith('/api/data') ? response(401, LOGIN_REQUIRED, SESSION) : response(200, {}); seen.push(r); return r; });
    gate.installLoginGate(win);
    const got = await win.fetch('/api/data');
    ok('W1 the SSO gate\'s 401 leaves for the login with the way back, and hands back the same response, no body read',
      same(went, ['/auth/login?next=' + encodeURIComponent('/admin.html?x=1#ontology')]) && got === seen[0] && !got.bodyUsed && got.cloned === 0,
      JSON.stringify([went, got === seen[0], got.bodyUsed, got.cloned]));
  }
  {
    const { win, went } = page(() => response(401, LOGIN_REQUIRED, SESSION));
    gate.installLoginGate(win);
    await Promise.all([win.fetch('/api/a'), win.fetch('/api/b'), win.fetch('/api/c')]);
    ok('W2 three refused at once: one departure', went.length === 1, String(went.length));
  }
  {
    const { win, went } = page(() => response(401, LOGIN_REQUIRED, SESSION));
    gate.installLoginGate(win);
    await win.fetch('/auth/me');
    await win.fetch('http://box/auth/keys');
    ok('W3 an /auth/* request is never sent back to the login', went.length === 0, JSON.stringify(went));
  }
  {
    // 🔴 THE CONTROL: what an SSO-off server answers today - the door must change none of it.
    const today = [response(200, { rows: [] }), response(...TOKEN_GATE), response(403, { detail: 'refused' }),
      response(503, { detail: 'no token configured' }), response(404, { detail: 'Not Found' }), response(401, undefined)];
    let i = 0;
    const { win, went } = page(() => today[i++]);
    gate.installLoginGate(win);
    const back = [];
    for (let k = 0; k < today.length; k += 1) back.push(await win.fetch(`/api/${k}`));
    ok('W4 SSO off: every answer of today comes back as itself, no body read, and nobody leaves',
      went.length === 0 && back.every((r, k) => r === today[k] && !r.bodyUsed && r.cloned === 0),
      JSON.stringify([went, back.map((r) => [r.bodyUsed, r.cloned])]));
  }
  {
    const { win } = page(() => response(200, {}));
    gate.installLoginGate(win);
    const once = win.fetch;
    gate.installLoginGate(win);
    ok('W5 a second install on the same page wraps nothing', win.fetch === once);
  }
  {
    const leaves = [];
    for (const [status, challenge] of [[401, 'Session'], [403, 'Session'], [401, 'X-Admin-Token'], [401, null]]) {
      const { win, went } = page(() => response(status, LOGIN_REQUIRED, challenge ? { 'WWW-Authenticate': challenge } : {}));
      gate.installLoginGate(win);
      await win.fetch('/api/x');
      leaves.push(went.length);
    }
    ok('W6 only 401 + Session leaves; 403 + Session, 401 + X-Admin-Token and an unmarked 401 stay', same(leaves, [1, 0, 0, 0]),
      JSON.stringify(leaves));
  }

  console.log('\n── A. the admin door over SSO\'s refusals ──');
  {
    const asked = [];
    const said = [];
    const deps = { askForToken: (m) => { asked.push(m); return 'tok'; }, onAdminRequired: (m) => said.push(m) };
    globalThis.localStorage = { getItem: () => '', setItem() {} };
    const answers = [response(403, ADMIN_REQUIRED, SESSION), response(403, ADMIN_REQUIRED, SESSION),
      response(401, LOGIN_REQUIRED, SESSION)];
    let i = 0;
    globalThis.fetch = async () => answers[i++] || response(200, {});
    const first = await admin.adminFetch('/admin/a', {}, deps);
    await admin.adminFetch('/admin/b', {}, deps);
    const third = await admin.adminFetch('/admin/c', {}, deps);
    ok('A1 admin_required: the server\'s sentence once, however many come back, and the response as it came',
      same(said, ['This needs an administrator.']) && first === answers[0] && !first.bodyUsed, JSON.stringify(said));
    ok('A2 SSO\'s refusals never ask for the admin token', asked.length === 0 && third === answers[2], JSON.stringify(asked));
    const control = [response(...TOKEN_GATE), response(200, {})];
    let j = 0;
    globalThis.fetch = async () => control[j++];
    const retried = await admin.adminFetch('/admin/d', {}, deps);
    ok('A3 SSO off: the token gate\'s rejection still asks once and retries', asked.length === 1 && retried === control[1],
      JSON.stringify(asked));
  }

  console.log('\n── B. the account part ──');
  const doc = { createElement: (tag) => element(tag) };
  // `logout` is how the server answers POST /auth/logout: 204 is the server as captured, before the Signed out page.
  const server = (me, logout = () => response(204)) => {
    const calls = [];
    let keys = [{ id: 'k1', name: 'nightly', created_at: '2026-10-07T09:00:00+09:00', last_used_at: null }];
    const fetch = async (url, init = {}) => {
      const method = (init.method || 'GET').toUpperCase();
      calls.push(`${method} ${url}`);
      if (url === '/auth/me') return response(200, me);
      if (url === '/auth/keys' && method === 'GET') return response(200, keys);
      if (url === '/auth/keys' && method === 'POST') {
        const { name } = JSON.parse(init.body);
        if (!name.trim()) return response(FX.key_name_required.status, FX.key_name_required.body);
        if (keys.some((k) => k.name === name)) return response(FX.key_name_taken.status, FX.key_name_taken.body);
        keys = [...keys, { id: 'k2', name, created_at: '2026-10-07T10:00:00+09:00', last_used_at: null }];
        return response(FX.key_made.status, { ...FX.key_made.body, id: 'k2', name, key: 'ak_secret_once' });
      }
      if (url.startsWith('/auth/keys/') && method === 'DELETE') { keys = keys.filter((k) => `/auth/keys/${k.id}` !== url); return response(204); }
      if (url === '/auth/logout') return logout();
      return response(404, {});
    };
    return { fetch, calls };
  };
  const make = (me, logout) => {
    const host = element('div');
    const srv = server(me, logout);
    const copied = [];
    const went = [];
    let reloads = 0;
    const part = new Badge(host, { doc, fetch: srv.fetch, reload: () => { reloads += 1; }, go: (url) => went.push(url),
      clipboard: { writeText: async (t) => copied.push(t) } });
    return { host, part, srv, copied, went, reloads: () => reloads };
  };
  {
    const off = make(FX.me_off.body);
    await off.part.mount();
    ok('B1 SSO off: the part draws nothing and asks only /auth/me', off.host.children.length === 0 && same(off.srv.calls, ['GET /auth/me']),
      JSON.stringify([off.host.children.length, off.srv.calls]));
  }
  const on = make(FX.me_signed_in.body);
  await on.part.mount();
  ok('B2 signed in: the name and Log out', same(texts(on.host, 'acct-name'), [FX.me_signed_in.body.user]) && texts(on.host, 'acct-logout').length === 1,
    JSON.stringify(texts(on.host, 'acct-name')));
  await click(on.host, 'acct-name');
  ok('B3 the name opens the keys: listed by name with their times', same(texts(on.host, 'acct-row-name'), ['nightly'])
    && find(on.host, 'acct-name')[0]?.getAttribute('aria-expanded') === 'true' && on.srv.calls.includes('GET /auth/keys'),
  JSON.stringify(texts(on.host, 'acct-row-name')));
  find(on.host, 'acct-key-name')[0].value = ' build ';
  await click(on.host, 'acct-create-key');
  const shown = texts(on.host, 'acct-fresh-key');
  await click(on.host, 'acct-copy');
  ok('B4 a new key is shown in the answer that made it, and Copy copies it', same(shown, ['ak_secret_once']) && same(on.copied, ['ak_secret_once'])
    && same(texts(on.host, 'acct-row-name'), ['nightly', 'build']), JSON.stringify([shown, on.copied]));
  await click(on.host, 'acct-name');
  await click(on.host, 'acct-name');
  ok('B5 shown once: closed and opened again, the key is gone', texts(on.host, 'acct-fresh-key').length === 0
    && !JSON.stringify(on.part).includes('ak_secret_once'), JSON.stringify(texts(on.host, 'acct-fresh-key')));
  find(on.host, 'acct-key-name')[0].value = 'nightly';
  await click(on.host, 'acct-create-key');
  ok('B6 a refused key says the server\'s sentence', same(texts(on.host, 'acct-error'), [FX.key_name_taken.body.detail.message]),
    JSON.stringify(texts(on.host, 'acct-error')));
  find(on.host, 'acct-key-name')[0].value = '  ';
  await click(on.host, 'acct-create-key');
  ok('B10 a nameless key says the server\'s sentence too', same(texts(on.host, 'acct-error'), [FX.key_name_required.body.detail.message]),
    JSON.stringify(texts(on.host, 'acct-error')));
  await click(find(on.host, 'acct-row').find((r) => texts(r, 'acct-row-name')[0] === 'nightly'), 'acct-revoke');
  ok('B7 Revoke deletes that key and reads the list again', on.srv.calls.includes('DELETE /auth/keys/k1')
    && same(texts(on.host, 'acct-row-name'), ['build']), JSON.stringify(on.srv.calls.slice(-3)));
  await click(on.host, 'acct-logout');
  ok('B8 a server from before the Signed out page (204): Log out ends the session, then reloads',
    on.srv.calls.at(-1) === 'POST /auth/logout' && on.reloads() === 1 && on.went.length === 0);
  {
    // The contract (lead 10-08): 200 {next} - the sign-in's end with our Signed out page to come back to.
    const END = 'https://adfs.example/adfs/oauth2/logout?post_logout_redirect_uri=https%3A%2F%2Fbox.example%2Fauth%2Fsigned-out';
    const to = make(FX.me_signed_in.body, () => response(200, { next: END }));
    await to.part.mount();
    await click(to.host, 'acct-logout');
    ok('L1 200 with next: Log out ends the session, then goes to that address as given, no reload',
      to.srv.calls.at(-1) === 'POST /auth/logout' && same(to.went, [END]) && to.reloads() === 0, JSON.stringify(to.went));
    const bare = make(FX.me_signed_in.body, () => response(200, {}));
    await bare.part.mount();
    await click(bare.host, 'acct-logout');
    ok('L2 200 without next: to our Signed out page', same(bare.went, ['/auth/signed-out']) && bare.reloads() === 0,
      JSON.stringify(bare.went));
    const refused = make(FX.me_signed_in.body, () => response(503, { detail: { message: 'Sign-out is unavailable' } }));
    await refused.part.mount();
    await click(refused.host, 'acct-logout');
    ok('L3 refused: the server\'s sentence beside Log out, as before; nowhere to go, no reload',
      same(texts(refused.host, 'acct-error'), ['Sign-out is unavailable']) && refused.went.length === 0 && refused.reloads() === 0,
      JSON.stringify([texts(refused.host, 'acct-error'), refused.went]));
  }
  {
    const one = make(FX.me_signed_in.body);
    const two = make(FX.me_signed_in.body);
    await one.part.mount(); await two.part.mount();
    await click(one.host, 'acct-name');
    ok('B9 two on one page: opening one leaves the other shut and unasked', find(one.host, 'acct-keys').length === 1
      && find(two.host, 'acct-keys').length === 0 && !two.srv.calls.includes('GET /auth/keys'));
  }

  console.log('\n── F. a failure line names whose refusal it is ──');
  {
    const { failureFactOf, fetchFailureText, CHROME } = classify;
    const line = (status, challenge) => fetchFailureText(failureFactOf(response(status, {},
      challenge ? { 'WWW-Authenticate': challenge } : {})), 'FALLBACK');
    const got = [[401, 'Session'], [403, 'Session'], [401, 'X-Admin-Token'], [403, 'X-Admin-Token'], [401, null], [403, null]]
      .map(([s, c]) => line(s, c));
    ok('F1 the SSO gate (Session): its 401 is a sign-in, its 403 the admin list',
      got[0] === CHROME.FETCH_SIGNED_OUT && got[1] === CHROME.FETCH_NOT_ADMIN, JSON.stringify(got.slice(0, 2)));
    ok('F2 SSO off (the control): the token gate and anything else say what they say today',
      same(got.slice(2), [CHROME.FETCH_UNAUTHORIZED, CHROME.FETCH_UNAUTHORIZED, CHROME.FETCH_INTERCEPTED, CHROME.FETCH_INTERCEPTED]),
      JSON.stringify(got.slice(2)));
    const asked = [[401, 'Session'], [403, 'Session'], [401, 'X-Admin-Token'], [403, 'X-Admin-Token'], [401, null], [403, null]]
      .map(([s, c]) => gate.isSessionRejection(response(s, {}, c ? { 'WWW-Authenticate': c } : {})));
    ok('F3 the one recognizer: Session on a 401 or a 403 is ours; X-Admin-Token or no marker is not; nor a word inside another challenge, nor a 200',
      same(asked, [true, true, false, false, false, false])
      && !gate.isSessionRejection(response(401, {}, { 'WWW-Authenticate': 'Basic realm="session-proxy"' }))
      && !gate.isSessionRejection(response(200, {}, SESSION)), JSON.stringify(asked));
  }

  console.log('\n── S. the socket takes the same door ──');
  const login = await wsDrive(FX.ws_signed_out.code, FX.ws_signed_out.reason);
  const drop = await wsDrive(1006, '');
  ok('S1 closed for want of a login: to the login, no reconnect', login.went === 1 && login.retry === false, JSON.stringify(login));
  ok('S2 any other close: reconnect as today, nobody leaves', drop.went === 0 && drop.retry === true, JSON.stringify(drop));
  return { ran, failed: failed.slice() };
}

// ── a minimal element ─────────────────────────────────────────────────────────────
function element(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], attrs: Object.create(null), _classes: [], _on: Object.create(null), _text: '', value: '',
    get className() { return this._classes.join(' '); }, set className(v) { this._classes = String(v).split(/\s+/).filter(Boolean); },
    append(...items) { for (const i of items) if (i) this.children.push(i); },
    setAttribute(k, v) { this.attrs[k] = String(v); }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    addEventListener(type, fn) { (this._on[type] ||= []).push(fn); },
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
    toJSON() { return { tag: this.tagName, cls: this.className, text: this._text, children: this.children }; },
  };
  return node;
}
const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const find = (root, cls) => walk(root).filter((n) => n._classes.includes(cls));
const texts = (root, cls) => find(root, cls).map((n) => n.textContent);
const settle = () => new Promise((r) => setImmediate(r));
const click = async (root, cls) => {
  const [el] = find(root, cls);
  for (const fn of el?._on.click || []) fn({});
  for (let k = 0; k < 6; k += 1) await settle();
};

// ── the socket, driven the way ws_connect_watchdog_harness drives it ─────────────────
const makeWsDrive = (mutate) => async (code, reason) => {
  let went = 0;
  const state = { ws: null, wsReconnectDelay: REAL_CFG.WS_RECONNECT_BASE_MS, wsRetryTimer: null, wsOpenedAt: 0,
    wsPrevReconnectDelay: REAL_CFG.WS_RECONNECT_BASE_MS, wsLastWakeAt: 0, wsWakeSignalsInstalled: true,
    wsConnectWatchdog: null, wsConnectingSince: 0, wsWatchdogTrips: 0, currentTable: 't', pageCache: new Map() };
  const badge = { textContent: '', className: '' };
  const { probe } = await loadWithProbe(WS, {
    mutate, expose: ['initWebSocket'], tag: 'sso-ws',
    stubs: {
      './config.js': Object.fromEntries(['WS_URL', 'WS_RECONNECT_BASE_MS', 'WS_RECONNECT_CEILING_MS', 'WS_RECONNECT_JITTER',
        'WS_HEALTHY_SESSION_MS', 'WS_WAKE_MIN_GAP_MS', 'WS_CONNECT_TIMEOUT_MS', 'WS_CONNECT_STALE_MS'].map((k) => [k, REAL_CFG[k]])),
      './state.js': { state },
      './dom.js': { elements: { get wsStatus() { return badge; }, tableSelect: { value: 't' } } },
      './api.js': { checkServerHealth: async () => {}, loadTables: async () => {}, fetchData: () => {} },
      './auth_gate.js': { WS_LOGIN_REQUIRED: REAL_GATE.WS_LOGIN_REQUIRED, goToLogin: () => { went += 1; } },
    },
  });
  const saved = { WebSocket: globalThis.WebSocket, document: globalThis.document, window: globalThis.window,
    setTimeout: globalThis.setTimeout, clearTimeout: globalThis.clearTimeout, console: globalThis.console };
  let sock = null;
  globalThis.WebSocket = class { constructor(url) { this.url = url; sock = this; } close() {} };
  globalThis.document = { querySelector: () => ({ classList: { add() {}, remove() {} } }), addEventListener() {} };
  globalThis.window = { addEventListener() {} };
  globalThis.setTimeout = () => 1;
  globalThis.clearTimeout = () => {};
  globalThis.console = { log() {}, error() {}, warn() {}, info() {}, debug() {} };
  try {
    probe.initWebSocket();
    sock.onclose({ code, reason });
    return { went, retry: state.wsRetryTimer !== null };
  } finally { Object.assign(globalThis, saved); }
};

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const load = async (file, mutate) => (await loadWithProbe(file, mutate ? { mutate } : {})).module;
// The admin door and the classifier import `isSessionRejection` from the gate module; they are handed the copy under
// test, so a defect in the one recognizer shows wherever it is asked.
const withGate = async (file, mutate, gate) => (await loadWithProbe(file, {
  ...(mutate ? { mutate } : {}), stubs: { './auth_gate.js': { isSessionRejection: gate.isSessionRejection } } })).module;
const deps = async (m = {}) => {
  const gate = await load(GATE, m.file === 'gate' && m.mutate);
  return {
    gate,
    Badge: (await load(BADGE, m.file === 'badge' && m.mutate)).AccountBadge,
    admin: await withGate(ADMIN, m.file === 'admin' && m.mutate, gate),
    classify: await withGate(CLASSIFY, m.file === 'classify' && m.mutate, gate),
    wsDrive: makeWsDrive(m.file === 'ws' ? m.mutate : undefined),
  };
};

const MUTANTS = [
  { name: 'the door leaves on any 401', catches: ['W6'], file: 'gate',
    mutate: swap('    if (res.status === 401 && isSessionRejection(res) && !isAuthRequest(input, win)) goToLogin(win);',
      '    if (res.status === 401 && !isAuthRequest(input, win)) goToLogin(win);') },
  { name: 'the door leaves on the 403 too', catches: ['W6'], file: 'gate',
    mutate: swap('    if (res.status === 401 && isSessionRejection(res) && !isAuthRequest(input, win)) goToLogin(win);',
      '    if (isSessionRejection(res) && !isAuthRequest(input, win)) goToLogin(win);') },
  { name: 'the way back loses its #tab', catches: ['W1'], file: 'gate', mutate: swap('${loc.search}${loc.hash}', '${loc.search}') },
  { name: 'every refused request leaves again', catches: ['W2'], file: 'gate', mutate: swap('  if (seat.leaving) return;\n', '') },
  { name: '/auth/* is sent back to the login', catches: ['W3'], file: 'gate',
    mutate: swap(' && !isAuthRequest(input, win)) goToLogin(win);', ') goToLogin(win);') },
  { name: 'a second install wraps again', catches: ['W5'], file: 'gate', mutate: swap('  if (seat.wrapped) return;\n', '') },
  { name: 'admin_required is said every time', catches: ['A1'], file: 'admin',
    mutate: swap('  if (res.status === 403 && isSessionRejection(res) && !adminRequiredSaid && deps.onAdminRequired) {',
      '  if (res.status === 403 && isSessionRejection(res) && deps.onAdminRequired) {') },
  { name: 'SSO off draws the part anyway', catches: ['B1'], file: 'badge', mutate: swap("    if (!me || me.sso !== true || !me.user) return;\n", '    if (!me) return;\n') },
  { name: 'the new key outlives its answer', catches: ['B5'], file: 'badge',
    mutate: swap('    this.open = !this.open;\n    this.fresh = null;\n', '    this.open = !this.open;\n') },
  { name: 'Copy copies nothing', catches: ['B4'], file: 'badge',
    mutate: swap('if (this.clipboard) void this.clipboard.writeText(this.fresh);', 'if (this.clipboard) void this.clipboard.writeText(\'\');') },
  { name: 'a refused key says nothing', catches: ['B6'], file: 'badge', mutate: swap('    else this.error = await refusal(res);\n', '') },
  { name: 'Revoke deletes nothing', catches: ['B7'], file: 'badge',
    mutate: swap("{ method: 'DELETE' }", "{ method: 'GET' }") },
  { name: 'Log out only reloads', catches: ['B8'], file: 'badge', mutate: swap("    const res = await this.fetch(LOGOUT, { method: 'POST' });\n", '    const res = { ok: true };\n') },
  { name: 'a 200 reloads like the old server', catches: ['L1'], file: 'badge',
    mutate: swap('    if (res.status === 204) { this.reload(); return; }\n', '    if (res.ok) { this.reload(); return; }\n') },
  { name: 'a 204 goes to the Signed out page', catches: ['B8'], file: 'badge',
    mutate: swap('    if (res.status === 204) { this.reload(); return; }\n', '') },
  { name: 'next is not followed', catches: ['L1'], file: 'badge', mutate: swap('this.go(await nextOf(res));', 'this.go(SIGNED_OUT);') },
  { name: 'no next goes nowhere', catches: ['L2'], file: 'badge', mutate: swap('  return SIGNED_OUT;\n', "  return '';\n") },
  { name: 'a refused sign-out says nothing', catches: ['L3'], file: 'badge',
    mutate: swap('    if (res.ok) { this.go(await nextOf(res)); return; }\n    this.error = await refusal(res);\n', '    if (res.ok) { this.go(await nextOf(res)); return; }\n') },
  { name: 'the failure line never reads the Session marker', catches: ['F1'], file: 'classify',
    mutate: swap('    session: isSessionRejection(res),' + '\n', '    session: false,' + '\n') },
  { name: 'a Session refusal reads as the token gate\'s', catches: ['F1'], file: 'classify',
    mutate: swap('    if (failure.session) return failure.status === 401 ? CHROME.FETCH_SIGNED_OUT : CHROME.FETCH_NOT_ADMIN;' + '\n', '') },
  { name: 'any challenge that mentions session counts', catches: ['F3'], file: 'gate',
    mutate: swap('  return /(^|[\\s,])session($|[\\s,])/i.test(challenge);', '  return /session/i.test(challenge);') },
  // 🔴 ONE BREAK, TWO CALLERS: the same defect in the one recognizer must redden the classifier AND the login door.
  { name: 'the recognizer calls every 401/403 ours - seen by the classifier', catches: ['F2'], file: 'gate',
    mutate: swap('  return /(^|[\\s,])session($|[\\s,])/i.test(challenge);', '  return true;') },
  { name: 'the recognizer calls every 401/403 ours - seen by the login door', catches: ['W6'], file: 'gate',
    mutate: swap('  return /(^|[\\s,])session($|[\\s,])/i.test(challenge);', '  return true;') },
  { name: 'the socket reconnects after a login refusal', catches: ['S1'], file: 'ws',
    mutate: swap('    if (event && event.code === WS_LOGIN_REQUIRED) { goToLogin(window); return; }\n', '') },
];

console.log('== baseline ==');
const base = await suite(await deps());
const BASE_NAMES = NAMES.slice();
if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
const { wrong } = await scoreMutants(MUTANTS, async (m) => {
  const d = await deps(m);
  const real = console.log;
  console.log = () => {};
  quiet = true;
  ran = 0; failed = [];
  try { await suite(d); } finally { quiet = false; console.log = real; }
  return { failures: failed, ran };
}, { baselineRan: base.ran, baselineNames: BASE_NAMES, title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
process.exit(wrong ? 1 : 0);
