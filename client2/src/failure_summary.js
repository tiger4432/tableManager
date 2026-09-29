// ═══════════════════════════════════════════════════════════════════════════════
// FAILURE SUMMARY — the Chain tab's failure section folds to one line per (table · kind · day)
// (owner 「ㄴ 요약 한 줄」, lead 36dff3b6a · e573a6edf · e6e5a08ee).
//
//   「dt_inventory EDIT 33 · 09-23 00:14–00:39 · attempts 1」
//
// 🔴 THE LINE IS THE SERVER'S GROUP BY; THIS FILE COUNTS NOTHING. `summary` arrives with every
//    `/admin/outbox/failed` answer (unfiltered), and the unfold asks the same route for that
//    line's rows by (table · event_type · day) — the filter goes through the same failure clause
//    and day expression the summary grouped by (lead 2f2a2f570), so a line cannot unfold to
//    anything but what it counted.
// 🔴 THE ROWS ARE THE PAGE'S. Opening a line moves the page's own row table (per-row Retry,
//    diagnostics, pager) under it — the way the Overview board takes page-owned bodies. This
//    part owns the lines only; two instances on one page do not share anything.
// ═══════════════════════════════════════════════════════════════════════════════
import { localSpan } from './server_time.js';

export const NOT_RECORDED = 'not recorded';
export const ROW_NOT_GIVEN = 'not given by the error';

/**
 * One quarantined group's record (`payload.error_log`) as its five cells — READ, never guessed
 * (order 45f5da3f5, owner 「차라리 에러를 잘남기는게 나음」). The screen used to name the first rule
 * whose table matched; the record now names the rules that woke. A record written before a cell
 * existed says 「not recorded」 for it; a row the error did not name says so (null, an empty list,
 * or the worker's own sentence).
 * @returns {Array<[string, string]>}
 */
export function failureRecordCells(errorLog) {
  const log = errorLog && typeof errorLog === 'object' ? errorLog : {};
  const has = (key) => Object.prototype.hasOwnProperty.call(log, key);
  const names = (key) => (!has(key) ? NOT_RECORDED
    : Array.isArray(log[key]) && log[key].length ? log[key].map(String).join(', ') : 'none');
  const row = !has('row') ? NOT_RECORDED
    : log.row === null || (Array.isArray(log.row) && !log.row.length) ? ROW_NOT_GIVEN
      : Array.isArray(log.row) ? log.row.map(String).join(', ') : String(log.row);
  return [
    ['Rule', names('rules')],
    ['Table', names('tables')],
    ['Rows', has('rows') ? String(log.rows) : NOT_RECORDED],
    ['Row', row],
    ['Reason', log.reason ? String(log.reason) : NOT_RECORDED],
  ];
}

/** The key of one line — what the unfold asks the route for. */
export function lineKey(line) {
  const l = line || {};
  return [l.table_name, l.event_type, l.day].map((v) => String(v == null ? '' : v)).join('\u0000');
}

/**
 * `/admin/outbox/failed` answer -> the lines. Pure.
 * @param {object|null} body
 * @param {string} [sentZone] the zone the request sent (`viewerZone()`); the answer's `day_zone`
 *   differs only when the server could not read it, and then the line says whose day it is.
 */
export function failureSummaryView(body, sentZone = '') {
  const lines = body && Array.isArray(body.summary) ? body.summary : null;
  if (!lines) return { read: false, lines: [], rows: 0 };
  const zone = body && typeof body.day_zone === 'string' ? body.day_zone : '';
  const foreignDay = Boolean(zone) && zone !== sentZone;
  const out = lines.map((l) => {
    const count = Number(l && l.count) || 0;
    const parts = [`${l.table_name} ${l.event_type} ${count}`, localSpan(l.first_at, l.last_at)];
    if (foreignDay) parts.push(`${l.day} (${zone} day)`);
    parts.push(`attempts ${Number(l && l.retry_max) || 0}`);
    return { key: lineKey(l), text: parts.join(' · '), count,
             filter: { table: String(l.table_name), event_type: String(l.event_type), day: String(l.day) } };
  });
  return { read: true, lines: out, rows: out.reduce((n, l) => n + l.count, 0) };
}

export class FailureSummary {
  /**
   * @param {HTMLElement} mount
   * @param {{doc?: Document, onToggle?: (line: object|null) => void}} [deps]
   */
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('FailureSummary needs a mount element');
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    if (!this.doc) throw new Error('FailureSummary needs a document (deps.doc or mount.ownerDocument)');
    this.onToggle = deps.onToggle || (() => {});
    this.root = this.doc.createElement('div');
    this.root.className = 'fail-summary';
    this.mount.appendChild(this.root);
  }

  /**
   * @param {object} view `failureSummaryView(...)`
   * @param {{openKey?: string|null, rowsBody?: HTMLElement}} [opts] the open line, and the page's
   *   row table to seat under it
   */
  render(view, opts = {}) {
    this.root.textContent = '';
    const openKey = opts.openKey || null;
    for (const line of (view && view.lines) || []) {
      const open = line.key === openKey;
      const head = this.doc.createElement('button');
      head.className = 'fail-summary__line' + (open ? ' is-open' : '');
      head.setAttribute('data-key', line.key);
      head.setAttribute('aria-expanded', open ? 'true' : 'false');
      head.textContent = line.text;
      head.addEventListener('click', () => this.onToggle(open ? null : line));
      this.root.appendChild(head);
      if (open && opts.rowsBody) this.root.appendChild(opts.rowsBody);
    }
  }
}
