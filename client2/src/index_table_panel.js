// INDEXES — the indexes the models declare beside the database, and those on the same tables nothing declares
// (lead d71f931c7: the declaration is the index master; GET /admin/indexes = the server's `models.index_states`),
// and each table's declared storage beside what it holds (its `storage`, lead 11-09 ⓑ). The chain worker builds what
// is owed. The state is the server's token as it comes, a sentence is the server's, and nothing here judges — the one
// thing it adds is which tag tone a token wears. A storage row set by hand apart from its declaration offers «Apply
// declared» (admin; the server's refusal said under it).
import { ABSENT, countText, isCount } from './absent.js';
import { localHourMinute } from './server_time.js';

/** The tone of a state's tag, one the base layer draws (`.tag[data-tone]`); a token not here wears none. */
const STATE_TONE = Object.freeze({ present: 'ok', building: 'warn', missing: 'danger', invalid: 'danger',
  held: 'ok', owed: 'warn', follows: 'warn', differs: 'warn', refused: 'danger' });

/** Bytes as KB · MB · GB (1024 each), or a dash when the server sent none. */
export function sizeText(bytes) {
  if (!isCount(bytes)) return ABSENT;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = Number(bytes);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
  return `${unit && value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

const text = (v) => (v === null || v === undefined || v === '' ? ABSENT : String(v));

/** A row's size: the catalogue's estimate (`size_estimate`) wears «≈ », one not yet counted «≈ ?» - never «0 B» (B 11-06). */
const sizeOf = (r) => (r.size_estimate === true ? `≈ ${isCount(r.size_bytes) ? sizeText(r.size_bytes) : '?'}` : sizeText(r.size_bytes));

/** The answer -> what the table draws. `unread` when no answer came: an empty table would read as no index. */
export function indexTableView(body) {
  const declared = body && Array.isArray(body.declared) ? body.declared : null;
  if (!declared) return { state: 'unread', declared: [], outside: [], storage: [] };
  const common = (r) => ({ name: text(r.name), table: text(r.table), said: r.building ? String(r.building) : '',
    size: sizeOf(r), scans: countText(r.scans), unused: Number(r.scans) === 0 && isCount(r.scans) });
  return {
    state: 'ready',
    declared: declared.map((r) => ({ ...common(r || {}), columns: Array.isArray(r.columns) && r.columns.length
      ? r.columns.join(', ') : ABSENT, purpose: text(r.purpose), serves: text(r.serves), token: text(r.state),
      tone: STATE_TONE[r.state] || '' })),
    outside: (Array.isArray(body.outside) ? body.outside : []).map((r) => ({ ...common(r || {}),
      valid: r.valid === true ? 'yes' : r.valid === false ? 'no' : ABSENT })),
    // a refused row has no parameter and says why; a table a value is not yet on holds none (`held` null)
    storage: (Array.isArray(body.storage) ? body.storage : []).map((r) => ({ name: `${text(r.table)} ${text(r.parameter)}`,
      table: text(r.table), parameter: text(r.parameter), declared: text(r.declared), held: text(r.held),
      source: text(r.source), token: text(r.state), tone: STATE_TONE[r.state] || '', said: r.why ? String(r.why) : '',
      differs: r.state === 'differs' })),
  };
}

// The state beside the name, so a missing, invalid or building index is seen before the table scrolls (lead d71f931c7).
// Purpose and Serves carry the words and take the room; the rest are as wide as theirs (`cell-fit`, owner 10-09).
const DECLARED_COLUMNS = Object.freeze([['name', 'Name', 'cell-fit'], ['state', 'State', 'cell-fit'], ['table', 'Table', 'cell-fit'],
  ['columns', 'Columns', 'cell-fit'], ['purpose', 'Purpose'], ['serves', 'Serves'], ['size', 'Size', 'num cell-fit'],
  ['scans', 'Scans', 'num cell-fit']]);
const OUTSIDE_COLUMNS = Object.freeze([['name', 'Name'], ['valid', 'Valid', 'cell-fit'], ['table', 'Table'],
  ['size', 'Size', 'num cell-fit'], ['scans', 'Scans', 'num cell-fit']]);
const STORAGE_COLUMNS = Object.freeze([['table', 'Table', 'cell-fit'], ['parameter', 'Parameter', 'cell-fit'],
  ['state', 'State'], ['declared', 'Declared', 'num cell-fit'], ['held', 'Set', 'num cell-fit'], ['source', 'From', 'cell-fit']]);

export class IndexTablePanel {
  /** @param deps { doc, read: () => Promise<{body, refused}>, apply: (table) => Promise<{done, refused}>, now: () => Date }
   *  - `apply` is «Apply declared» on a storage row that differs (admin); with `read` the panel reads its own
   *  answer: open() and its Refresh, never two at once, and says when it last read (lead 11-06: the Overview's 30 s beat
   *  read GET /admin/indexes every time, a slow read overlapping the next - «32s P /admin/indexes»). */
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('IndexTablePanel needs a mount element');
    this.doc = deps.doc || mount.ownerDocument;
    this.read = deps.read || null;
    this.apply = deps.apply || null;
    this.now = deps.now || (() => new Date());
    this.reading = false;
    this.applying = false;
    if (this.read) {
      const head = mount.appendChild(this._el('div', 'index-table-head'));
      this.readAt = head.appendChild(this._el('span', 'meta index-read-at', ''));
      this.button = head.appendChild(this._el('button', 'admin-btn index-refresh', 'Refresh'));
      this.button.addEventListener('click', () => { this.open(); });
    }
    this.root = this.doc.createElement('div');
    this.root.className = 'index-table-panel';
    mount.appendChild(this.root);
  }

  /** Read the answer and draw it - a read still on its way is the one: nothing more is asked. */
  async open() {
    if (!this.read || this.reading) return false;
    this.reading = true;
    this.button.disabled = true;
    this.button.textContent = 'Reading…';
    try {
      const { body, refused } = await this.read();
      this.render(body, refused);
      this.readAt.textContent = `Read ${localHourMinute(this.now().toISOString())}`;
    } finally {
      this.reading = false;
      this.button.disabled = false;
      this.button.textContent = 'Refresh';
    }
    return true;
  }

  _el(tag, cls, words) {
    const el = this.doc.createElement(tag);
    if (cls) el.className = cls;
    if (words !== undefined) el.textContent = words;
    return el;
  }

  /** One table: a head row, then a row per index or storage value; a state cell is its tag; the server's sentence (a
   *  build's, a refusal's) stands under the `said` column; a storage value that differs offers «Apply declared». */
  _table(columns, rows, said) {
    const table = this._el('table', 'runtime-table index-table');
    const head = this._el('tr');
    for (const [, label, cls] of columns) head.appendChild(this._el('th', cls || '', label));
    table.appendChild(this._el('thead')).appendChild(head);
    const body = table.appendChild(this._el('tbody'));
    for (const row of rows) {
      const tr = this._el('tr');
      tr.setAttribute('data-index', row.name);
      for (const [key, , cls] of columns) {
        const td = this._el('td', cls || '');
        td.setAttribute('data-col', key);
        if (key === 'state') {
          const tag = td.appendChild(this._el('span', 'tag', row.token));
          if (row.tone) tag.setAttribute('data-tone', row.tone);
          if (row.differs && this.apply) {
            const button = td.appendChild(this._el('button', 'admin-btn index-apply', 'Apply declared'));
            button.addEventListener('click', () => { void this._applyDeclared(row.table, button, td); });
          }
        } else if (key === 'scans' && row.unused) {
          td.appendChild(this._el('span', 'meta', row.scans));
        } else {
          td.textContent = row[key];
        }
        if (key === said && row.said) td.appendChild(this._el('div', 'meta index-said', row.said));
        tr.appendChild(td);
      }
      body.appendChild(tr);
    }
    return table;
  }

  /** @param {object|null} body the GET /admin/indexes answer, null when it could not be read
   *  @param {string} [refused] the refusal's line when it could not be read */
  render(body, refused = '') {
    const view = indexTableView(body);
    this.root.textContent = '';
    if (view.state === 'unread') {
      this.root.appendChild(this._el('div', 'refusal', refused || ABSENT));
      return view;
    }
    this.root.appendChild(this._table(DECLARED_COLUMNS, view.declared, 'state'));
    this.root.appendChild(this._el('div', 'box-title index-outside-title', 'Not declared'));
    if (view.outside.length) this.root.appendChild(this._table(OUTSIDE_COLUMNS, view.outside, 'valid'));
    else this.root.appendChild(this._el('div', 'meta', 'None'));
    this.root.appendChild(this._el('div', 'box-title index-storage-title', 'Storage'));
    if (view.storage.length) this.root.appendChild(this._table(STORAGE_COLUMNS, view.storage, 'state'));
    else this.root.appendChild(this._el('div', 'meta', 'None'));
    return view;
  }

  /** «Apply declared» on one table: one at a time, «Applying…» while the server takes its lock (up to 30 s), then the
   *  table read again - or the server's refusal under the row. */
  async _applyDeclared(table, button, cell) {
    if (this.applying) return false;
    this.applying = true;
    button.disabled = true;
    button.textContent = 'Applying…';
    let said = '';
    try {
      said = (await this.apply(table)).refused || '';
    } finally {
      this.applying = false;
    }
    if (said) {
      button.disabled = false;
      button.textContent = 'Apply declared';
      cell.appendChild(this._el('div', 'refusal index-said', said));
      return false;
    }
    await this.open();
    return true;
  }
}
