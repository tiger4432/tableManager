// The product server as the extension's service worker calls it - a page's script cannot (CORS). The address and the
// personal key come from the settings; the key rides as a Bearer. A refusal is the server's own sentence (`detail`).

/** A row as /data answers it - {row_id, data: {column: {value, ...}}} - to {row_id, column: value}. */
export const flat = (row) => ({ row_id: row && row.row_id, ...Object.fromEntries(Object.entries((row && row.data) || {}).map(([c, cell]) =>
  [c, cell && typeof cell === 'object' && 'value' in cell ? cell.value : cell])) });

/** The longest read address in bytes (encoded): 8 KB is the common request-line cap (nginx's default
 *  large_client_header_buffers), the rest is room for the host and the headers. */
export const URL_BUDGET = 6000;

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

  /** The address `rows` reads - its filters ride in it, encoded. */
  rowsPath(table, filters = {}, { limit = 1000, cols = null, orderBy = null } = {}) {
    const f = Object.fromEntries(Object.entries(filters).map(([c, values]) => [c, { filterType: 'set', values }]));
    const q = new URLSearchParams({ limit: String(limit), defer_total: 'true', ...(Object.keys(f).length ? { filters: JSON.stringify(f) } : {}),
      ...(cols ? { cols: cols.join(',') } : {}), ...(orderBy ? { order_by: orderBy, order_desc: 'true' } : {}) });
    return `/tables/${encodeURIComponent(table)}/data?${q}`;
  }

  /** Rows of `table` whose columns are in `filters` ({column: [values]}) -> {ok, rows, detail}. */
  async rows(table, filters = {}, opts = {}) {
    const r = await this.call('GET', this.rowsPath(table, filters, opts));
    return { ok: r.ok, rows: r.ok ? ((r.body && r.body.data) || []).map(flat) : [], detail: r.detail, status: r.status };
  }

  /** Of the rows `cellsList`, the keys (`keys` columns joined by «|») `table` already has -> {have: Set of keys, tooLong: Set of
   *  first-key values whose read the server refused as too long}. The values go in reads of at most URL_BUDGET each (owner
   *  11-11 «uri too large»); one value past it is asked alone. Any other refused or unreached read throws its sentence. */
  async existing(table, keys, cellsList) {
    const have = new Set();
    const tooLong = new Set();
    const firsts = [...new Set(cellsList.map((c) => c[keys[0]]))];
    const opts = (values) => ({ limit: Math.max(values.length * 50, 1000), cols: keys });
    const fits = (values) => (this.server + this.rowsPath(table, { [keys[0]]: values }, opts(values))).length <= URL_BUDGET;
    const parts = [];
    for (const v of firsts) {
      const last = parts[parts.length - 1];
      if (last && fits([...last, v])) last.push(v); else parts.push([v]);
    }
    const joined = (row) => keys.map((k) => (row[k] === null || row[k] === undefined ? '' : String(row[k]))).join('|');
    for (const values of parts) {
      const r = await this.rows(table, { [keys[0]]: values }, opts(values));
      // one value past the budget, refused (414) or its connection cut (status 0, a proxy's way): that value only
      if (values.length === 1 && (r.status === 414 || (r.status === 0 && !fits(values)))) { tooLong.add(values[0]); continue; }
      if (!r.ok) throw Object.assign(new Error(r.detail), { status: r.status });
      for (const row of r.rows) have.add(joined(row));
    }
    return { have, tooLong };
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
