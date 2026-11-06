// The grid's «Tables» button (owner 11-06, lead L1): the grid's table and what narrows it, carried to the Tables page. The narrowing
// is the grid's own (narrowing.js), and a set filter's values can make it long, so it rides the browser's storage; the
// address names the table only. Read once on arrival and dropped, so a later visit opens as asked, not as handed.

export const HANDOFF_KEY = 'tables:handoff';
/** Not «tables.html»: the server keeps every path starting «tables» for its /tables API (main.py's page catch-all). */
export const TABLES_PAGE = 'source_tables.html';
/** How long a handed narrowing waits for its page - past it the page opens as its address says. */
export const HANDOFF_MS = 60000;

/** The Tables page's address for a table. */
export const tablesAddress = (table) => `${TABLES_PAGE}?table=${encodeURIComponent(table)}`;

/** Keep the hand-off: the table, its narrowing (narrowingParams' query text) and its world (null: the operating one). */
export function handoffWrite(storage, table, narrowing, world, now = Date.now()) {
  try {
    storage.setItem(HANDOFF_KEY, JSON.stringify({ table, narrowing: String(narrowing || ''), world: world || null, at: now }));
    return true;
  } catch {
    return false;
  }
}

/** What the page opens: the address's table, with the hand-off's narrowing and world when it was handed for that table
 *  and is fresh. The hand-off is taken - read once. */
export function handoffRead(storage, search, now = Date.now()) {
  const table = new URLSearchParams(search || '').get('table') || null;
  let handed = null;
  try {
    handed = JSON.parse(storage.getItem(HANDOFF_KEY) || 'null');
    storage.removeItem(HANDOFF_KEY);
  } catch {
    handed = null;
  }
  const fresh = handed && table && handed.table === table && now - Number(handed.at) <= HANDOFF_MS;
  return { table, narrowing: fresh ? String(handed.narrowing || '') : '', world: fresh ? handed.world || null : null, handed: Boolean(fresh) };
}

/** The grid's button: keep the hand-off, open the page beside the grid. */
export function openInTables(win, table, narrowing, world) {
  if (!table) return false;
  handoffWrite(win.localStorage, table, narrowing, world);
  win.open(tablesAddress(table), '_blank', 'noopener');
  return true;
}
