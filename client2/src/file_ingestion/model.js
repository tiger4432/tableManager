// THE FILE INGESTION PAGE's words and shapes (owner 10-20 «ㅇㅇ 일케 해», lead; mockup FWp74vd6UqX1i7qXpyQg8K): what a
// file log line says, how the lines group under a folder or a reason, the search's query - pure, so the harness imports
// what the page runs. The server's answers: /admin/file-ingestion/tables · /logs (A bbbea4323 · 0eba61a50 · 06c21a7b1).
import { ABSENT, isBlank } from '../absent.js';
import { folderOf } from '../admin_rows.js';
import { isFailedStatus, retryVerdict } from '../retry_verdict.js';
import { localShort } from '../server_time.js';

/** Lines a page of the list asks for; «Show more» asks the next page. */
export const PAGE_ROWS = 100;
/** The Group by box: the server's group word and what the box says. */
export const GROUPS = Object.freeze([['folder', 'Folder'], ['reason', 'Failure reason'], ['', 'None']]);
export const WORDS = Object.freeze({
  title: 'File Ingestion', day: 'YYYY-MM-DD', tables: 'Tables', findTable: 'Find table', table: 'Table', status: 'Status', all: 'All',
  name: 'File name contains', folder: 'Folder starts with', between: 'Read between', from: 'From', to: 'To',
  groupBy: 'Group by', files: 'Files read', file: 'File', path: 'Path', copyPath: 'Copy path', copyFolder: 'Copy folder',
  readBy: 'Read by', source: 'Source', readAt: 'Read at', result: 'Result', whyFailed: 'Why it failed',
  retryFile: 'Retry this file', readAgain: 'Read again', showRows: 'Show its rows in the grid',
  retryFailed: (n) => `Retry ${count(n)} failed`, retryAsk: (n, folder) => `Retry ${count(n)} failed file${n === 1 ? '' : 's'} under ${folder}?`, showMore: 'Show more', noReason: '(No reason)',
  noFiles: 'No file matches', pickFile: 'Pick a file', noTables: 'No file has been read yet',
  heads: ['File · folder', 'Status', 'Result', 'Read at', 'Took'],
  last: (at) => `last ${at}`, ok: (n) => `${n} ok`, failed: (n) => `${n} failed`, running: (n) => `${n} running`,
  groupSummary: (n, failed) => `${count(n)} file${n === 1 ? '' : 's'} · ${count(failed)} failed`,
  shown: (n, groups, match) => `${count(n)} file${n === 1 ? '' : 's'}${groups ? ` in ${count(groups)} group${groups === 1 ? '' : 's'}` : ''} shown · ${match} match`,
});

const count = (n) => Number(n || 0).toLocaleString('en-US');
const numberOr = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

/** A status as the page says it: «SUCCESS» -> «Success», «PENDING_RETRY» -> «Pending retry». */
export function statusWord(status) {
  const s = String(status || '').toLowerCase().replace(/_/g, ' ');
  return s ? s[0].toUpperCase() + s.slice(1) : ABSENT;
}

/** Its pill's tone - the one status judge (retry_verdict), ok · danger · warn. */
export function statusTone(status) {
  const tone = retryVerdict(status).tone;
  return tone === 'ok' ? 'ok' : tone === 'danger' ? 'danger' : 'warn';
}

/** The counts a read came to, the ones the server wrote (rows_* null: not counted - the line says nothing of them). */
export function resultCounts(log) {
  const rows = [['Rows read', log.rows_read], ['New', log.rows_new], ['Changed', log.rows_changed], ['Unchanged', log.rows_unchanged],
    ['Refused', log.rows_refused]];
  return rows.filter(([, v]) => numberOr(v) !== null).map(([label, v]) => ({ label, value: count(v) }));
}

/** A failure's one line: the server's reason, else the first line of its message. */
export function reasonOf(log) {
  if (!isBlank(log.reason)) return String(log.reason);
  const first = String(log.error_message || '').split('\n').find((l) => l.trim());
  return first ? first.trim() : '';
}

/** The Result cell: a failure's reason; else «400 rows · 12 new · 388 unchanged» (zeros after the rows left out). */
export function resultText(log) {
  if (isFailedStatus(log.status)) return reasonOf(log) || ABSENT;
  const read = numberOr(log.rows_read);
  if (read === null) return ABSENT;
  const parts = [`${count(read)} row${read === 1 ? '' : 's'}`];
  for (const [word, v] of [['new', log.rows_new], ['changed', log.rows_changed], ['unchanged', log.rows_unchanged], ['refused', log.rows_refused]]) {
    if (numberOr(v)) parts.push(`${count(v)} ${word}`);
  }
  return parts.join(' · ');
}

/** «0.4 s»; none timed (a skip, a tier-1 copy) - ABSENT. */
export function tookText(seconds) {
  const s = numberOr(seconds);
  return s === null ? ABSENT : `${s < 10 ? s.toFixed(1) : Math.round(s).toLocaleString('en-US')} s`;
}

/** When it was read: the log's last change, in the viewer's zone. */
export function readAtText(log) {
  const at = log.updated_at || log.created_at;
  return at ? localShort(at) : ABSENT;
}

/** The query of one page of the list. `to` is a day the operator includes - the server's `until` is «before», so the day after. */
export function queryOf(q, { page = 1, limit = PAGE_ROWS, group = q.group, status = q.status } = {}) {
  const p = new URLSearchParams();
  if (q.table) p.set('table', q.table);
  p.set('status', status || 'ALL');
  for (const [key, value] of [['name', q.name], ['folder', q.folder], ['since', q.from]]) if (!isBlank(value)) p.set(key, String(value).trim());
  if (!isBlank(q.to)) {
    const day = new Date(`${String(q.to).trim()}T00:00:00`);
    if (!Number.isNaN(day.getTime())) {
      day.setDate(day.getDate() + 1);
      const pad = (n) => String(n).padStart(2, '0');
      p.set('until', `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`);
    }
  }
  if (group) p.set('group', group);
  p.set('page', String(page));
  p.set('limit', String(limit));
  return p;
}

/** The folder a folder group stands for (B 1107c5a8e · 22edf8101): with a folder asked (`base`) the group is a name just
 *  below it - «.» the files right in it; with none, the group's label is the folder itself. */
export function groupFolder(base, label) {
  const b = String(base || '').trim();
  if (!b) return String(label || '');
  if (!label || label === '.') return b;
  const sep = b.includes('\\') ? '\\' : b.includes('/') ? '/' : '\\';
  return `${b.replace(/[\\/]+$/, '')}${sep}${label}`;
}

/** The lines in groups: each line in the group the server put it in (its `group_key`), the groups in the order the lines
 *  first say them, each with the server's label and count (`groups`); no group - one group, no head. A folder group
 *  carries the folder it stands for (`base` the folder asked) - its head drills in and retries its failures. */
export function groupFiles(rows, group, groups = [], base = '') {
  if (!group) return [{ key: null, head: false, files: rows.slice() }];
  const keyOf = (raw) => (raw === null || raw === undefined ? '' : String(raw));
  const counted = new Map((groups || []).map((g) => [keyOf(g.key), g]));
  const out = new Map();
  for (const row of rows) {
    const key = keyOf(row.group_key);
    if (!out.has(key)) {
      const c = counted.get(key) || {};
      const label = isBlank(c.label) ? key : String(c.label);
      out.set(key, { key, head: true, label: label || (group === 'reason' ? WORDS.noReason : ABSENT), files: [],
        count: numberOr(c.count), failed: numberOr(c.failed) || 0, folder: group === 'folder' && key !== '' ? groupFolder(base, label) : null });
    }
    out.get(key).files.push(row);
  }
  return [...out.values()];
}

/** The table list's lines: totals by status from /tables, running ones from /active (the watcher's, in memory). */
export function tableLines(tables, active = []) {
  const running = new Map();
  for (const a of active || []) running.set(a.table_name, (running.get(a.table_name) || 0) + 1);
  return (tables || []).map((t) => ({
    name: t.table_name, total: count(t.total), ok: count((t.by_status || {}).SUCCESS), failed: count((t.by_status || {}).FAILED),
    running: count(running.get(t.table_name)), last: t.last_at ? localShort(t.last_at) : ABSENT,
  }));
}

/** The grid opened on the rows a file wrote (the grid's address: its table, its read's transaction); none without a tx. */
export function rowsAddress(log) {
  if (isBlank(log.transaction_id) || isBlank(log.table_name)) return null;
  return `/?${new URLSearchParams({ table: String(log.table_name), tx: String(log.transaction_id) })}`;
}

/** A log line's folder as its row shows it (the admin lists' one folder function). */
export const folderLine = (log) => folderOf(log.filepath);
