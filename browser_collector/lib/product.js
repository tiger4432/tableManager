// The product server as the extension's service worker calls it - a page's script cannot (CORS). The address and the
// personal key come from the settings; the key rides as a Bearer. A refusal is the server's own sentence (`detail`).

/** A row as /data answers it - {row_id, data: {column: {value, ...}}} - to {row_id, column: value}. */
export const flat = (row) => ({ row_id: row && row.row_id, ...Object.fromEntries(Object.entries((row && row.data) || {}).map(([c, cell]) =>
  [c, cell && typeof cell === 'object' && 'value' in cell ? cell.value : cell])) });

const said = (body) => (body && body.detail !== undefined ? (typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)) : null);

export class Product {
  constructor({ server, key }, fetchFn = (...a) => fetch(...a)) {
    this.server = String(server || '').replace(/\/+$/, '');
    this.key = key || '';
    this.fetch = fetchFn;
  }

  /** -> {ok, status, body, detail} - a server not reached is status 0 with the browser's sentence. */
  async call(method, path, body) {
    let res;
    try {
      res = await this.fetch(`${this.server}${path}`, {
        method,
        headers: { Authorization: `Bearer ${this.key}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (err) {
      return { ok: false, status: 0, body: null, detail: `server not reached - ${err.message}` };
    }
    let parsed = null;
    try { parsed = await res.json(); } catch { /* an empty or non-JSON answer */ }
    return { ok: res.ok, status: res.status, body: parsed, detail: res.ok ? null : (said(parsed) || `${res.status} ${res.statusText}`) };
  }

  /** Rows of `table` whose columns are in `filters` ({column: [values]}) -> {ok, rows, detail}. */
  async rows(table, filters = {}, { limit = 1000, cols = null, orderBy = null } = {}) {
    const f = Object.fromEntries(Object.entries(filters).map(([c, values]) => [c, { filterType: 'set', values }]));
    const q = new URLSearchParams({ limit: String(limit), defer_total: 'true', ...(Object.keys(f).length ? { filters: JSON.stringify(f) } : {}),
      ...(cols ? { cols: cols.join(',') } : {}), ...(orderBy ? { order_by: orderBy, order_desc: 'true' } : {}) });
    const r = await this.call('GET', `/tables/${encodeURIComponent(table)}/data?${q}`);
    return { ok: r.ok, rows: r.ok ? ((r.body && r.body.data) || []).map(flat) : [], detail: r.detail, status: r.status };
  }

  /** Of the rows `cellsList`, the keys (`keys` columns joined by «|») `table` already has -> Set (a refused read throws its sentence). */
  async existing(table, keys, cellsList) {
    if (!cellsList.length) return new Set();
    const firsts = [...new Set(cellsList.map((c) => c[keys[0]]))];
    const r = await this.rows(table, { [keys[0]]: firsts }, { limit: Math.max(firsts.length * 50, 1000), cols: keys });
    if (!r.ok) throw Object.assign(new Error(r.detail), { status: r.status });
    const joined = (row) => keys.map((k) => (row[k] === null || row[k] === undefined ? '' : String(row[k]))).join('|');
    return new Set(r.rows.map(joined));
  }

  /** Rows of `table` by their row ids, removed -> {ok} | {ok: false, status, detail}. */
  async remove(table, rowIds) {
    const r = await this.call('POST', `/tables/${encodeURIComponent(table)}/rows/batch_delete`, { row_ids: rowIds });
    return r.ok ? { ok: true } : { ok: false, status: r.status, detail: r.detail };
  }

  /** Who the key signs in as -> {ok, user, detail}. */
  async whoAmI() {
    const r = await this.call('GET', '/auth/me');
    return { ok: r.ok, user: r.ok && r.body ? r.body.user : null, detail: r.detail };
  }

  /** Rows into `table` as the layer `source` -> {ok} | {ok: false, status, detail}. */
  async write(table, rows, source) {
    const r = await this.call('PUT', `/tables/${encodeURIComponent(table)}/data/updates`,
      { updates: rows.map((cells) => ({ updates: cells, source_name: source })) });
    return r.ok ? { ok: true } : { ok: false, status: r.status, detail: r.detail };
  }
}
