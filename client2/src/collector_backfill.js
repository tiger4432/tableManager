// ═══════════════════════════════════════════════════════════════════════════════
// AUTO UPDATE — a collector row's Backfill cell (lead 09f0be40f, 소유자 「ㄱ ㅇㅇ」).
//
// The button runs the existing `collector_backfill` operation (no new route, no new op) and
// the line under it is that operation's latest run for THIS collector. Whether the run is
// still going, done or failed is `buildRunsView`'s answer (one seat) — this file compares no
// run state itself.
// ⚠️ Three states for the window, as the status record sends it: a string (declared - on),
//    null (not declared - off, with the reason) and NO KEY (an older record that cannot say -
//    no button at all, so a declared collector is never told to declare one).
// ═══════════════════════════════════════════════════════════════════════════════
import { buildRunsView } from './retroactive_view.js';

export const BACKFILL_OP = 'collector_backfill';
export const BACKFILL_WORDS = Object.freeze({
  button: 'Backfill',
  start: 'Start',
  cancel: 'Cancel',
  placeholder: 'YYYY-MM-DD',
  offTitle: 'Declare # window: to backfill',
});

/** The collector as the backfill operation names it (`<table>/<script.py>`). */
export const collectorKey = (col) => `${(col || {}).table_name}/${(col || {}).script_name}`;

/**
 * @param col       one `/admin/auto-update/status` collector entry
 * @param runsBody  the `/admin/retroactive/runs` body (`{runs, state_names}`), or null unread
 * @returns {{show: boolean, title: string, offReason: string, key: string,
 *            line: null | {text: string, tone: 'live'|'done'|'danger'}}}
 *   `offReason` goes through `setDisabledReason` (the one seat that turns a control off with
 *   its reason); '' means on, and `title` is the button's own words then.
 */
export function collectorBackfillView(col, runsBody) {
  const c = col || {};
  const key = collectorKey(c);
  if (!('window' in c)) return { show: false, title: '', offReason: '', key, line: null };
  const declared = typeof c.window === 'string' ? c.window.trim() : '';
  const title = declared ? `Backfill day by day (# window: ${declared})` : '';
  const offReason = declared ? '' : BACKFILL_WORDS.offTitle;
  const runs = runsBody && Array.isArray(runsBody.runs) ? runsBody.runs : [];
  // The list is newest first (server `queued_at` desc) - the first of this collector's is its latest.
  const latest = runs.find((r) => r && r.op === BACKFILL_OP && r.params && r.params.collector === key);
  if (!latest) return { show: true, title, offReason, key, line: null };
  const row = buildRunsView({ runs: [latest], state_names: runsBody.state_names || {} }, Date.now(), {}, {}).rows[0];
  const word = row.stateName && row.stateName.text ? row.stateName.text : '';
  const total = Number(latest.total_rows);
  const done = Number(latest.processed_rows);
  const days = Number.isFinite(total) && total > 0 ? `${Number.isFinite(done) ? done : 0}/${total} days` : '';
  const reason = row.reason && row.reason.text ? row.reason.text : '';
  const summary = row.summary && row.summary.text ? row.summary.text : '';
  const said = row.finished ? (reason || summary) : '';
  return {
    show: true, title, offReason, key,
    line: {
      text: [word, days, said].filter(Boolean).join(' · '),
      tone: reason ? 'danger' : row.finished ? 'done' : 'live',
    },
  };
}
