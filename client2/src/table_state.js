// The open tables and what each one was left as (owner 11-05 ㄱ, mockup v3 «Open tables»): one store for every
// table's state - filters, sort, pivot, hidden columns, widths, scroll, selection, the pages read. Its settings live in
// the browser (they come back after a reload); its pages (the grid's own page cache) live in memory for the last KEEP
// tables only.
// A part: constructed with its storage, no module state - two stores on one page do not meet.

const KEEP = 5;
const TABS_KEY = 'grid-tabs';
const settingsKey = (table) => `grid-table:${table}`;

/** What a table is left as, split by where it lives: `settings` (browser storage) and `data` (memory). */
export function splitSnapshot(snap) {
  const { pages, currentSkip, hasMoreData, allDataLoaded, ...settings } = snap || {};
  return { settings, data: Array.isArray(pages) && pages.length ? { pages, currentSkip, hasMoreData, allDataLoaded } : null };
}

export class TableStateStore {
  /** `storage`: a Storage-like {getItem, setItem, removeItem} - localStorage, or null when the browser refuses it. */
  constructor({ storage = null, keep = KEEP } = {}) {
    this.storage = storage;
    this.keep = keep;
    this.data = new Map();   // table -> its rows, newest last; at most `keep`
    this.open = this._read(TABS_KEY, []).filter((t) => typeof t === 'string' && t);
  }

  _read(key, none) {
    try {
      const raw = this.storage ? this.storage.getItem(key) : null;
      return raw == null ? none : JSON.parse(raw);
    } catch {
      return none;
    }
  }

  _write(key, value) {
    try {
      if (this.storage) this.storage.setItem(key, JSON.stringify(value));
    } catch {
      // a browser that refuses storage keeps the tabs for this page only
    }
  }

  /** The open tables, in the order they were opened. */
  tables() {
    return [...this.open];
  }

  /** A table opened: a tab for it, at the end when it is new. */
  opened(table) {
    if (!table || this.open.includes(table)) return;
    this.open.push(table);
    this._write(TABS_KEY, this.open);
  }

  /** A table left: its settings kept in the browser, its rows in memory - the oldest rows let go past `keep`. */
  park(table, snap) {
    if (!table) return;
    const { settings, data } = splitSnapshot(snap);
    this._write(settingsKey(table), settings);
    this.data.delete(table);
    if (data) this.data.set(table, data);
    while (this.data.size > this.keep) this.data.delete(this.data.keys().next().value);
  }

  /** What a table was left as: its settings (or null, never seen) and its rows (or null, read them again). */
  take(table) {
    const settings = this._read(settingsKey(table), null);
    const data = this.data.get(table) || null;
    if (data) { this.data.delete(table); this.data.set(table, data); }   // the newest again
    return { settings, data };
  }

  /** A tab closed: the table leaves the row, its rows the memory; its settings stay for the next time it is opened. */
  close(table) {
    this.open = this.open.filter((t) => t !== table);
    this._write(TABS_KEY, this.open);
    this.data.delete(table);
  }
}
