// INDEXES — the indexes the models declare beside the database, and those on the same tables nothing declares
// (lead d71f931c7: the declaration is the index master; GET /admin/indexes = the server's `models.index_states`).
// Read only: the chain worker builds what is owed. The state is the server's token as it comes, a build's
// sentence is the server's, and nothing here judges — the one thing it adds is which tag tone a token wears.
import { ABSENT, countText, isCount } from './absent.js';

/** The tone of a state's tag, one the base layer draws (`.tag[data-tone]`); a token not here wears none. */
const STATE_TONE = Object.freeze({ present: 'ok', building: 'warn', missing: 'danger', invalid: 'danger' });

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

/** The answer -> what the table draws. `unread` when no answer came: an empty table would read as no index. */
export function indexTableView(body) {
  const declared = body && Array.isArray(body.declared) ? body.declared : null;
  if (!declared) return { state: 'unread', declared: [], outside: [] };
  const common = (r) => ({ name: text(r.name), table: text(r.table), building: r.building ? String(r.building) : '',
    size: sizeText(r.size_bytes), scans: countText(r.scans), unused: Number(r.scans) === 0 && isCount(r.scans) });
  return {
    state: 'ready',
    declared: declared.map((r) => ({ ...common(r || {}), columns: Array.isArray(r.columns) && r.columns.length
      ? r.columns.join(', ') : ABSENT, purpose: text(r.purpose), serves: text(r.serves), token: text(r.state),
      tone: STATE_TONE[r.state] || '' })),
    outside: (Array.isArray(body.outside) ? body.outside : []).map((r) => ({ ...common(r || {}),
      valid: r.valid === true ? 'yes' : r.valid === false ? 'no' : ABSENT })),
  };
}

// The state beside the name, so a missing, invalid or building index is seen before the table scrolls (lead d71f931c7).
const DECLARED_COLUMNS = Object.freeze([['name', 'Name'], ['state', 'State'], ['table', 'Table'], ['columns', 'Columns'],
  ['purpose', 'Purpose'], ['serves', 'Serves'], ['size', 'Size', 'num'], ['scans', 'Scans', 'num']]);
const OUTSIDE_COLUMNS = Object.freeze([['name', 'Name'], ['valid', 'Valid'], ['table', 'Table'],
  ['size', 'Size', 'num'], ['scans', 'Scans', 'num']]);

export class IndexTablePanel {
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('IndexTablePanel needs a mount element');
    this.doc = deps.doc || mount.ownerDocument;
    this.root = this.doc.createElement('div');
    this.root.className = 'index-table-panel';
    mount.appendChild(this.root);
  }

  _el(tag, cls, words) {
    const el = this.doc.createElement(tag);
    if (cls) el.className = cls;
    if (words !== undefined) el.textContent = words;
    return el;
  }

  /** One table: a head row, then a row per index; a state cell is its tag; while building, the server's sentence
   *  stands under the `said` column. */
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
        } else if (key === 'scans' && row.unused) {
          td.appendChild(this._el('span', 'meta', row.scans));
        } else {
          td.textContent = row[key];
        }
        if (key === said && row.building) td.appendChild(this._el('div', 'meta index-building', row.building));
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
    return view;
  }
}
