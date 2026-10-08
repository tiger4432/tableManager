// OVERVIEW STATUS — mockup A's STATUS rows (owner 「A 로 해」, lead 3c3f2b1f2 · 5d157581e).
//
// 🔴 ONE JUDGE PER ROW. File · Chain · Auto Update · Enrichment were judged TWICE until
//    2026-09-25 — the Overview cards and the hidden health strip read the same responses and
//    asked different questions (the strip folded an unread total to 0 for Chain; only the strip
//    asked `errorText` / `absentPath` for Auto Update; a rule-less Enrichment was OK on one and
//    grey on the other). Each row is now ONE pure function from the server's responses to what
//    the row says; the board draws it and decides nothing.
//
// A row is { key, name, facts: [text], tone, word }. The words are a CLOSED FOUR paired with the
// dot's colour (lead 575a844f7); what is specific to a row is its FACTS, not a fifth word. Grey is
// every row that cannot be judged — not arrived yet (`undefined`, fact 「Loading…」), unread
// (`null`), or nothing to judge (no collectors, a small sample) — and the fact says which.
import { countText, isCount, localeCountText } from './absent.js';
import { errorText } from './body_error.js';
import { absentPath } from './absent_listing.js';
import { LOADING, unitText } from './ui_words.js';
import { failedSince } from './chain_queue_panel.js';
import { runtimeView } from './runtime_panel.js';
import { sourcesView } from './ledger_sources_panel.js';
import { isFailedStatus } from './retry_verdict.js';

export const TONE = Object.freeze({ OK: 'ok', WARN: 'warn', DANGER: 'danger', UNKNOWN: 'unknown' });
export const WORDS = Object.freeze({ ok: 'OK', warn: 'Warning', danger: 'Failing', unknown: 'Unknown' });

const row = (key, name, facts, tone) => Object.freeze({
  key, name, facts: Object.freeze(facts.filter(Boolean)), tone, word: WORDS[tone] });
const pending = (key, name) => row(key, name, [LOADING], TONE.UNKNOWN);
const count = (v) => (Number.isFinite(Number(v)) && v !== null && v !== '' ? Number(v) : null);

/** `/runtime` — the loops. Alive is the server's three states; only `false` is a fault. */
export function workersRow(runtime) {
  if (runtime === undefined) return pending('workers', 'Workers');
  const view = runtimeView(runtime);
  if (view.state !== 'ready') return row('workers', 'Workers', [], TONE.UNKNOWN);
  // 🔴 총괄 13aa739f3 — an idle on-demand process is resting, so it is not in M.
  const counted = view.rows.filter((r) => !r.idle);
  const alive = counted.filter((r) => r.cellTone && r.cellTone.alive === 'ok').length;
  const dead = counted.filter((r) => r.cellTone && r.cellTone.alive === 'danger').length;
  const tone = !counted.length ? TONE.UNKNOWN : dead ? TONE.DANGER
    : alive < counted.length ? TONE.WARN : TONE.OK;
  return row('workers', 'Workers', [`${alive} of ${counted.length} alive`], tone);
}

/** `/admin/file-ingestion/failed` + `/admin/file-ingestion/active`. */
export function fileRow({ failed, active } = {}) {
  if (failed === undefined) return pending('file', 'File Ingestion');
  const total = failed ? count(failed.total) : null;
  const ingesting = active && Array.isArray(active.data) ? active.data.length : null;
  const facts = [`failed ${countText(total)}`, `ingesting ${countText(ingesting)}`];
  const tone = total === null ? TONE.UNKNOWN : total > 0 ? TONE.DANGER
    : ingesting > 0 ? TONE.WARN : TONE.OK;
  return row('file', 'File Ingestion', facts, tone);
}

/** `/admin/outbox/failed` (through `failedSince`, the queue's Failed cell) + rules + mappers. */
export function chainRow({ outbox, rules, mappers } = {}) {
  if (outbox === undefined) return pending('chain', 'Chain');
  const failed = failedSince(outbox);
  const listed = (body) => (body && Array.isArray(body.data) ? body.data.length : null);
  const facts = [
    failed.read && failed.since ? `failed ${failed.total} since ${failed.since}` : `failed ${failed.text}`,
    `rules ${countText(listed(rules))}`,
    `mappers ${countText(listed(mappers))}`,
  ];
  const tone = !failed.read ? TONE.UNKNOWN : failed.total > 0 ? TONE.DANGER : TONE.OK;
  return row('chain', 'Chain', facts, tone);
}

/**
 * `/admin/auto-update/status` + the file-ingestion failures (the output link).
 * 🔴 An error body is «unread» and a missing status file is «absent» — neither is 「no
 *    collectors」. An unread failure list leaves the output link unchecked, which is not 0
 *    (health_card_absence_harness scores exactly these).
 */
export function autoRow({ auto, failed } = {}) {
  if (auto === undefined) return pending('auto', 'Auto Update');
  if (!auto) return row('auto', 'Auto Update', [], TONE.UNKNOWN);
  const failure = errorText(auto);
  if (failure) return row('auto', 'Auto Update', [failure], TONE.UNKNOWN);
  const absent = absentPath(auto);
  if (absent) return row('auto', 'Auto Update', ['No status file', absent], TONE.WARN);
  const collectors = Array.isArray(auto.data) ? auto.data : [];
  if (!collectors.length) return row('auto', 'Auto Update', ['No collectors'], TONE.UNKNOWN);
  const failCount = collectors.filter((c) => isFailedStatus(c.last_status)).length;
  const activeCount = collectors.filter((c) => c.active !== false).length;
  const tables = new Set(collectors.map((c) => c.table_name));
  const logs = failed && Array.isArray(failed.data) ? failed.data : null;
  const linked = logs ? logs.filter((l) => tables.has(l.table_name)).length : null;
  const more = logs && count(failed.total) > logs.length ? '+' : '';
  const facts = [
    `active ${activeCount} of ${collectors.length}`,
    `failures ${failCount}`,
    linked === null ? 'output link unchecked' : `output failures ${linked}${more}`,
  ];
  const tone = failCount > 0 ? TONE.DANGER
    : (linked === null || linked > 0 || activeCount === 0) ? TONE.WARN : TONE.OK;
  return row('auto', 'Auto Update', facts, tone);
}

/** admin.js `fetchEnrichmentStatus()` — `{ rules, totalMissing }`, or null when unread. */
export function enrichmentRow(enrich) {
  if (enrich === undefined) return pending('enrichment', 'Enrichment');
  if (!enrich) return row('enrichment', 'Enrichment', [], TONE.UNKNOWN);
  const rules = Array.isArray(enrich.rules) ? enrich.rules.length : 0;
  if (!rules) return row('enrichment', 'Enrichment', ['No rules'], TONE.UNKNOWN);
  return row('enrichment', 'Enrichment', [unitText(rules, 'rule'), `missing ${countText(enrich.totalMissing)}`],
    enrich.totalMissing > 0 ? TONE.WARN : TONE.OK);
}

/** The loop in `/runtime` that is the ledger follow-up (server 0e7530cef): its `state`, and when stopped its `said`. */
export const LEDGER_FOLLOWUP_LOOP = 'ledger_followup';

/**
 * `/admin/ledger/sources` — sources by the server's own state words, and refused molecules; and the
 * follow-up's row of the `/runtime` answer the page already reads (lead 558a46ef1).
 * ⚠️ The server ships a MEANING per state, not a colour, so no state is coloured here. The one
 *    colour is a COUNT: refused molecules above 0 is Warning (the lane's choice — reported).
 * 🔴 A stopped follow-up fails the row with the server's sentence and what waits; each world it switched off is
 *    «live off: <world>» and the row warns at least. The closed four words stay; the rest is facts (lead 575a844f7).
 */
export function ledgerRow(sources, runtime) {
  const follow = runtime && Array.isArray(runtime.loops)
    ? runtime.loops.find((l) => l && l.loop === LEDGER_FOLLOWUP_LOOP) || null : null;
  const off = (follow && Array.isArray(follow.switched_off) ? follow.switched_off : [])
    .filter((w) => w && w.world).map((w) => `live off: ${w.world}`);
  if (follow && follow.state === 'stopped') {
    return row('ledger', 'Ledger', [follow.said, `waiting ${countText(follow.depth)}`, ...off], TONE.DANGER);
  }
  const base = ledgerSourcesRow(sources);
  if (!off.length) return base;
  return row('ledger', 'Ledger', [...base.facts, ...off], base.tone === TONE.DANGER ? TONE.DANGER : TONE.WARN);
}

function ledgerSourcesRow(sources) {
  if (sources === undefined) return pending('ledger', 'Ledger');
  if (!sources) return row('ledger', 'Ledger', [], TONE.UNKNOWN);
  const view = sourcesView(sources);
  if (!view.available) return row('ledger', 'Ledger', [view.reason], TONE.UNKNOWN);
  const raw = Array.isArray(sources.ingestion.sources) ? sources.ingestion.sources : [];
  const refused = raw.reduce((sum, s) => sum + (s && isCount(s.molecules_refused) ? Number(s.molecules_refused) : 0), 0);
  const facts = view.byState.map((b) => `${b.name || b.state} ${b.count}`);
  if (refused) facts.push(`refused ${localeCountText(refused)}`);
  return row('ledger', 'Ledger', facts, !view.rows.length ? TONE.UNKNOWN : refused ? TONE.WARN : TONE.OK);
}

/** `config_resolve_view.buildConfigResolveView(...)`, or null with the refusal line when unread. */
export function declarationsRow(view, reason = '') {
  if (view === undefined) return pending('declarations', 'Declarations');
  if (!view) return row('declarations', 'Declarations', [reason], TONE.UNKNOWN);
  const facts = view.totals.map((t) => `${t.label && t.label.text} ${t.count.text}`);
  const tone = view.empty ? TONE.UNKNOWN : view.tone === 'danger' ? TONE.DANGER
    : view.tone === 'warn' ? TONE.WARN : TONE.OK;
  return row('declarations', 'Declarations', facts, tone);
}

/** `retroactive_view.buildRunsView(...)` with `failedSources`. 「0 running」 too — an empty fact cell
 *  could not be told from an unread one (lead 909ea2052 ③, reversing 575a844f7). A source that could
 *  not be read makes the row grey, not idle. */
export function retroactiveRow(runs) {
  if (runs === undefined) return pending('retroactive', 'Retroactive');
  if (!runs) return row('retroactive', 'Retroactive', [], TONE.UNKNOWN);
  const unreachable = Array.isArray(runs.failedSources) ? runs.failedSources : [];
  // 🔴 「가장 오래」는 «최댓값»이고 끝난 줄은 뺍니다 — 접힌 줄만 보고 끊을지 정하는 자리라 그 한 수가
  //    판단입니다(renderRunning 에서 옮김). 08:52 에 끝난 것을 09:13 에 「oldest 21m」 로 적지 않습니다.
  const minutes = (Array.isArray(runs.rows) ? runs.rows : []).filter((r) => r && !r.finished)
    .map((r) => (r.progress && typeof r.progress.elapsedMinutes === 'number' ? r.progress.elapsedMinutes : null))
    .filter((m) => m !== null);
  const facts = [`${countText(runs.liveCount)} running`,
    runs.liveCount > 0 && minutes.length ? `oldest ${Math.max(...minutes)}m` : ''];
  if (unreachable.length) facts.push(`${unreachable.join(', ')} unreachable`);
  return row('retroactive', 'Retroactive', facts, unreachable.length ? TONE.UNKNOWN : TONE.OK);
}

/** `/dashboard/summary` `.recorrection` — the rate of cells a person fixed twice or more. */
export function recorrectionRow(stat) {
  if (stat === undefined) return pending('recorrection', 'Re-correction');
  if (!stat) return row('recorrection', 'Re-correction', ['No report'], TONE.UNKNOWN);
  const win = stat.window_days == null ? '' : `last ${stat.window_days} days`;
  if (stat.rate_pct == null) {
    const why = stat.unavailable_reason ? `Aggregation failed · ${stat.unavailable_reason}`
      : stat.measured_cells == null ? 'Not aggregated' : 'No corrected cells';
    return row('recorrection', 'Re-correction', [why, win], TONE.UNKNOWN);
  }
  const cells = count(stat.measured_cells);
  const small = cells === null || cells < 100;
  const facts = [`${Number(stat.rate_pct).toFixed(1)}%`,
    `${localeCountText(stat.recorrected_cells)} of ${localeCountText(stat.measured_cells)} cells`, win,
    small ? 'small sample' : ''];
  const tone = small ? TONE.UNKNOWN : stat.rate_pct >= 10 ? TONE.DANGER
    : stat.rate_pct >= 5 ? TONE.WARN : TONE.OK;
  return row('recorrection', 'Re-correction', facts, tone);
}

/**
 * `/dashboard/summary` `.effort` — interaction score per correction, and its coverage.
 * 🔴 Coverage stays beside the score: 0 measured while people corrected is the collector dying,
 *    and without it 「no sample」 and 「the instrument is dead」 are the same dash.
 */
export function effortRow(stat) {
  if (stat === undefined) return pending('effort', 'Correction effort');
  const days = stat && stat.window_days != null ? `last ${stat.window_days} days` : '';
  const ratio = stat ? stat.measured_ratio : null;
  const coverage = ratio == null ? 'coverage unknown' : `coverage ${(ratio * 100).toFixed(0)}%`;
  if (!stat) return row('effort', 'Correction effort', ['No report'], TONE.UNKNOWN);
  if (stat.avg_score == null) {
    if (stat.unavailable_reason) {
      return row('effort', 'Correction effort', [`Aggregation failed · ${stat.unavailable_reason}`], TONE.DANGER);
    }
    if (ratio === 0) {
      return row('effort', 'Correction effort', ['0 measured', 'human corrections exist', days], TONE.DANGER);
    }
    return row('effort', 'Correction effort', ['No corrections', days], TONE.UNKNOWN);
  }
  const low = ratio == null || ratio < 0.5;
  return row('effort', 'Correction effort', [
    `${Number(stat.avg_score).toFixed(1)} pts`,
    `${localeCountText(stat.session_count)} sessions`,
    `${localeCountText(stat.tx_count)} measured`, coverage, days,
  ], low ? TONE.WARN : TONE.OK);
}

/** The board's order (mockup A). */
export const ROW_ORDER = Object.freeze(['workers', 'file', 'chain', 'auto', 'enrichment', 'ledger',
  'declarations', 'retroactive', 'recorrection', 'effort']);

