// THE ADMIN PAGE'S ADDRESS — `#<tab>` or `#<key>=<value>` (its hash router; an old `?tab=` link too). admin.js reads it;
// a page that opens the admin at a place builds it here - the main grid's Flow box opens the chain editor at a rule
// (owner 11-10 «플로우 ㄱ»). One spelling both ways. No DOM.

export const ADMIN_PAGE = '/admin.html';

/** {key, value} of an admin address: the hash, else an old `?tab=` link; the value decoded as it was encoded. */
export function adminRouteOf(hash, search = '') {
  let raw = String(hash || '').replace(/^#/, '');
  if (!raw) raw = new URLSearchParams(search || '').get('tab') || '';
  const eq = raw.indexOf('=');
  const key = (eq >= 0 ? raw.slice(0, eq) : raw).toLowerCase();
  let value = null;
  if (eq >= 0) {
    try { value = decodeURIComponent(raw.slice(eq + 1)); } catch (e) { value = raw.slice(eq + 1); }
  }
  return { key, value };
}

/** The address that opens the admin at `key` (a tab, `editor`, `chain`), at `value` when given. */
export function adminHref(key, value = null) {
  return `${ADMIN_PAGE}#${key}${value === null || value === undefined || value === '' ? '' : `=${encodeURIComponent(value)}`}`;
}

/** The chain editor with rule `name` open. */
export const chainRuleHref = (name) => adminHref('chain', name);

/** A rule an address names that the rules file lacks. */
export const ruleNotFound = (name) => `Rule ${name} not found`;

/** One rule's read (GET /admin/chain/rules/raw?name=) for `name`: as it came when the file has that rule; else the list
 *  with nothing open and why - the editor does not draw an empty form under a name the file lacks. `held` is the «not
 *  found» said before: a list read (the 30 s refresh) says it again, until a person opens a rule or a new one (`byPerson`)
 *  - a refresh does not take away why the address opened nothing (lead 11-10). -> {body, refusal, held} */
export function ruleAddressed(body, name, held = null, byPerson = false) {
  if (!name) return { body, refusal: byPerson ? null : held, held: byPerson ? null : held };
  if (!body || !Array.isArray(body.rules) || body.rules.includes(name)) return { body, refusal: null, held: null };
  const { name: _asked, declaration: _none, raw: _empty, ...list } = body;
  const refusal = { code: '', path: '', message: ruleNotFound(name) };
  return { body: list, refusal, held: refusal };
}
