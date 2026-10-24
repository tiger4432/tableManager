// ═══════════════════════════════════════════════════════════════════════════════
// FAILURE SUMMARY — the Chain tab's failure section folds to one line per (rules · failure sentence)
// (owner 10-24 「묶음이 100만개라고」 · 「똑같은 에러면 접든가」, lead ㄷ; the table · kind · day lines retired).
//
//   「lot_slot_join 19000 · 10-21 16:50–17:00」 and the sentence whole under it
//
// 🔴 THE LINE IS THE SERVER'S GROUP BY; THIS FILE COUNTS NOTHING. `by_cause` arrives with every
//    `/admin/outbox/failed` answer (unfiltered, A 06b1fd297), and the unfold asks the same route
//    for that line's rows by its cause and rules (A b7503191e) — the keys that line folded, so a
//    line cannot unfold to anything but what it counted.
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

/**
 * An error TEXT read back as that record, or null. A `rule_rows` run stores the chain's record as
 * JSON in its error (server 67b2e423b); one record is drawn one way (lead, 67b2e423b answer). A
 * text that does not parse — a sentence, or a record cut short — stays text.
 * @returns {object|null}
 */
export function failureRecordOf(errorText) {
  if (typeof errorText !== 'string') return null;
  let record = null;
  try { record = JSON.parse(errorText); } catch { return null; }
  return record && typeof record === 'object' && !Array.isArray(record)
    && Object.prototype.hasOwnProperty.call(record, 'reason') ? record : null;
}

/** The key of one line — its rules (comma-joined, as the route reads them) and its cause. */
export function lineKey(line) {
  const l = line || {};
  return [(Array.isArray(l.rules) ? l.rules : []).map(String).join(','), l.cause == null ? '' : String(l.cause)].join('\u0000');
}

/**
 * `/admin/outbox/failed` answer -> the lines. Pure.
 * @param {object|null} body
 */
export function failureSummaryView(body) {
  const lines = body && Array.isArray(body.by_cause) ? body.by_cause : null;
  if (!lines) return { read: false, lines: [], rows: 0 };
  const out = lines.map((l) => {
    const count = Number(l && l.count) || 0;
    const rules = Array.isArray(l && l.rules) ? l.rules.map(String) : [];
    // The failure sentence is the server's, whole (lead 903053c14) - as sent, '' when it sends none.
    const reason = typeof (l && l.cause) === 'string' ? l.cause.trim() : '';
    return { key: lineKey(l), text: [`${rules.length ? rules.join(', ') : `Rule ${NOT_RECORDED}`} ${count}`, localSpan(l.first_at, l.last_at)].join(' · '),
             reason, count, filter: { cause: l.cause == null ? '' : String(l.cause), rules: rules.join(',') } };
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
      if (line.reason) {
        const said = this.doc.createElement('div');
        said.className = 'refusal reason-lines fail-summary__reason';
        said.textContent = line.reason;
        said.setAttribute('title', line.reason);
        this.root.appendChild(said);
      }
      if (open && opts.rowsBody) this.root.appendChild(opts.rowsBody);
    }
  }
}
