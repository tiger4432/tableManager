// Who is signed in, Log out, and that person's own API keys (company SSO, lead 2095014ee). One part, seated in every
// page's head bar; with SSO off (`/auth/me` says `sso: false`) it draws nothing. A new key is shown once, in the answer
// that made it - it is kept nowhere and is gone when the window closes or the list is read again.
import { localMinute } from './server_time.js';

const ME = '/auth/me';
const KEYS = '/auth/keys';
const LOGOUT = '/auth/logout';
const SIGNED_OUT = '/auth/signed-out';

const refusal = async (res) => {
  try { const m = (await res.json())?.detail?.message; if (typeof m === 'string' && m) return m; } catch (e) { /* not JSON */ }
  return `HTTP ${res.status}`;
};
// Where the browser goes once signed out: the server's `next` (the sign-in's own end, lead 10-08), else our page.
const nextOf = async (res) => {
  try { const n = (await res.json())?.next; if (typeof n === 'string' && n) return n; } catch (e) { /* not JSON */ }
  return SIGNED_OUT;
};

export class AccountBadge {
  /**
   * @param {HTMLElement} host  the element this part owns
   * @param {{doc: Document, fetch: Function, reload: Function, go: Function, clipboard?: {writeText: Function}}} deps
   */
  constructor(host, deps) {
    this.host = host;
    this.doc = deps.doc;
    this.fetch = deps.fetch;
    this.reload = deps.reload;
    this.go = deps.go;
    this.clipboard = deps.clipboard || null;
    this.me = null;
    this.open = false;
    this.keys = [];
    this.fresh = null;
    this.error = '';
  }

  async mount() {
    try {
      const res = await this.fetch(ME);
      this.me = res.ok ? await res.json() : null;
    } catch (e) { this.me = null; }
    this.render();
  }

  async _keys() {
    const res = await this.fetch(KEYS);
    if (!res.ok) { this.error = await refusal(res); return; }
    const list = await res.json();
    this.keys = Array.isArray(list) ? list : [];
  }

  async toggle() {
    this.open = !this.open;
    this.fresh = null;
    this.error = '';
    if (this.open) await this._keys();
    this.render();
  }

  async create(name) {
    this.fresh = null;
    this.error = '';
    const res = await this.fetch(KEYS, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }) });
    if (res.ok) this.fresh = (await res.json())?.key || null;
    else this.error = await refusal(res);
    await this._keys();
    this.render();
  }

  async revoke(id) {
    this.fresh = null;
    this.error = '';
    const res = await this.fetch(`${KEYS}/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!res.ok) this.error = await refusal(res);
    await this._keys();
    this.render();
  }

  async logout() {
    const res = await this.fetch(LOGOUT, { method: 'POST' });
    // 204 is a server from before the Signed out page: the reload it always had.
    if (res.status === 204) { this.reload(); return; }
    if (res.ok) { this.go(await nextOf(res)); return; }
    this.error = await refusal(res);
    this.render();
  }

  _el(tag, cls, text) {
    const el = this.doc.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = String(text);
    return el;
  }

  _button(text, cls, onClick) {
    const el = this._el('button', cls, text);
    el.type = 'button';
    el.addEventListener('click', onClick);
    return el;
  }

  render() {
    this.host.textContent = '';
    const me = this.me;
    if (!me || me.sso !== true || !me.user) return;
    const box = this._el('div', 'acct');
    const name = this._button(me.user, 'acct-name', () => void this.toggle());
    name.setAttribute('aria-expanded', String(this.open));
    box.append(name, this._button('Log out', 'acct-logout', () => void this.logout()));
    if (this.error && !this.open) box.append(this._el('span', 'acct-error', this.error));
    if (this.open) box.append(this._window());
    this.host.append(box);
  }

  _window() {
    const win = this._el('div', 'acct-keys');
    win.append(this._el('div', 'acct-title', 'API keys'));
    const form = this._el('div', 'acct-create');
    const input = this._el('input', 'acct-key-name');
    input.type = 'text';
    input.placeholder = 'Key name';
    form.append(input, this._button('Create key', 'acct-create-key', () => void this.create(input.value.trim())));
    win.append(form);
    if (this.fresh) {
      const fresh = this._el('div', 'acct-fresh');
      fresh.append(this._el('code', 'acct-fresh-key', this.fresh),
        this._button('Copy', 'acct-copy', () => { if (this.clipboard) void this.clipboard.writeText(this.fresh); }));
      win.append(fresh);
    }
    if (this.error) win.append(this._el('div', 'acct-error', this.error));
    const list = this._el('div', 'acct-list');
    if (!this.keys.length) list.append(this._el('div', 'acct-empty', 'No keys'));
    for (const key of this.keys) {
      const row = this._el('div', 'acct-row');
      row.append(this._el('span', 'acct-row-name', key.name),
        this._el('span', 'acct-row-time', `Created ${localMinute(key.created_at)}`),
        this._el('span', 'acct-row-time', `Last used ${localMinute(key.last_used_at)}`),
        this._button('Revoke', 'acct-revoke', () => void this.revoke(key.id)));
      list.append(row);
    }
    win.append(list);
    return win;
  }
}
