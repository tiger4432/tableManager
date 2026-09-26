// C-14 tranche 2. The five admin list rows whose cells are SERVER-SUPPLIED NAMES.
//
// 🔴 WHY THESE FIVE, AND WHY IN A MODULE OF THEIR OWN.
//    The order was: take the templates carrying server strings first. These are they —
//    `filename`, `table_name`, `script_name`, `module_name`, `config_file`, workspace `name`.
//    Every one is a name the operator did not type and the client cannot vet.
//    They live here rather than inline in `admin.js` because the gate is BEHAVIOURAL — «a
//    hostile table name does not become an element» — and a behavioural gate needs the real
//    function, not a copy of it. `admin.js` cannot be imported (it imports `tokens.css` and
//    touches the DOM at module top), so the standing rule applies: move the logic being
//    measured into a module the harness can `import`. `admin_rows_harness.mjs` imports THESE
//    functions, so the assertion scores what the screen runs.
// 🔴 SO THE BADGES MOVED IN TOO. `statusBadge` interpolates `log.status`, `configBadge`
//    interpolates `ws.config_file` — both server strings. Leaving them at the call site would
//    put the escaping decision in two files, and the two would drift; that drift is exactly
//    what this C-14 sweep found last round (three `escapeHtml` copies, one of which left
//    quotes alone). One author per row.
//
// ⚠️ WHAT IS **NOT** ESCAPED HERE, AND WHY — recorded so the next reader does not re-derive it:
//    · locally built fragments (`statusBadge`, `laneBadge`, …) are markup BY CONSTRUCTION;
//      escaping them would print their tags as text
//    · locally computed numbers (`pct` from Math.max/min, `scriptCount`/`funcCount` from
//      `.length`) cannot carry a character that closes a tag
//    · the ternary style/label literals are written right here in this file
//    Everything reaching these functions from the server payload IS escaped, including inside
//    attributes — `data-table="${…}"` is the position where the quote-only drift was unsafe.
import { escapeHtml } from './utils.js';
import { localeCountText, isCount } from './absent.js';
import { statusBadgeClass, isDoneStatus } from './retry_verdict.js';
import { BACKFILL_WORDS } from './collector_backfill.js';

/** File Ingestion 로그 행. `withStatus` 는 Auto Update 탭 실패 목록과 공용이라 남습니다. */
export function fileLogRowHtml(log, { withStatus, timeStr }) {
  // Badge and button read the one seat (lead 65f2c808d) — a waiting file is not drawn as failed.
  const statusBadge = `<span class="${statusBadgeClass(log.status)}">${escapeHtml(log.status || 'FAILED')}</span>`;
  const retryBtnHtml = isDoneStatus(log.status)
    ? `<button class="admin-btn btn-primary" disabled>Retry</button>`
    : `<button class="admin-btn btn-primary btn-retry-file" data-id="${escapeHtml(log.id)}">Retry</button>`;
  // 감사 P2: 파일명은 상태와 무관한 중립색(모노) — 상태색은 배지에만
  const retryStyle = log.retry_count > 0
    ? 'color: var(--warning); font-weight: 600;'
    : 'color: var(--text-dim);';
  return `
    <td>${escapeHtml(log.id)}</td>
    <td style="font-weight: 500; color: var(--text); font-family: var(--font-mono); font-size: var(--fs-button); word-break: break-all;">${escapeHtml(log.filename)}</td>
    <td style="font-weight: bold; color: var(--color-primary);">${escapeHtml(log.table_name)}</td>
    ${withStatus ? `<td style="text-align: center;">${statusBadge}</td>` : ''}
    <td style="text-align: center; ${retryStyle}">${escapeHtml(log.retry_count)}</td>
    <td style="color: var(--text-muted); font-size: var(--fs-button); font-family: var(--font-mono);" title="${escapeHtml(log.created_at || '')}">${escapeHtml(timeStr)}</td>
    <td style="text-align: center;" onclick="event.stopPropagation()">
      ${retryBtnHtml}
    </td>
  `;
}

/** 진행 중 인제션 행. `elapsedText` 는 admin 의 포매터가 만든 것이라 받아서 «감쌉니다». */
export function activeIngestionRowHtml(item, { elapsedText }) {
  const laneBadge = item.lane === 'heavy'
    ? `<span class="badge badge-warning" style="font-weight: bold;">HEAVY</span>`
    : `<span class="badge badge-success">normal</span>`;
  const pct = Math.max(0, Math.min(item.progress || 0, 100));
  const statusNote = item.status === 'QUEUED' ? ' waiting' : '';
  // 🔴 `|| 0` USED TO BE HERE and it turned 「안 왔다」 into 「0개 처리했다」 — a
  //    number the server never sent. `localeCountText` keeps the two apart.
  const rowsText = (item.total_rows != null)
    ? `${localeCountText(item.processed_rows)} / ${localeCountText(item.total_rows)}`
    : (isCount(item.processed_rows) && Number(item.processed_rows) > 0
      ? localeCountText(item.processed_rows) : '-');
  return `
      <td style="font-family: var(--font-mono); font-size: var(--fs-button); color: var(--text); word-break: break-all;">${escapeHtml(item.filename)}</td>
      <td style="font-weight: bold; color: var(--color-primary);">${escapeHtml(item.table_name)}</td>
      <td style="text-align: center;">${laneBadge}</td>
      <td>
        <div style="display: flex; align-items: center; gap: 8px;">
          <div style="flex: 1; height: 6px; border-radius: 3px; background: var(--bg-inset); border: 1px solid var(--border); overflow: hidden;">
            <div style="width: ${pct}%; height: 100%; background: var(--accent); transition: width 0.4s;"></div>
          </div>
          <span style="font-family: var(--font-mono); font-size: var(--fs-label); color: var(--text-muted); min-width: 46px; text-align: right;">${pct}%${statusNote}</span>
        </div>
      </td>
      <td style="text-align: center; font-family: var(--font-mono); font-size: var(--fs-button); color: var(--text-muted);">${rowsText}</td>
      <td style="text-align: center; font-family: var(--font-mono); font-size: var(--fs-button); color: var(--text-muted);">${escapeHtml(elapsedText)}</td>
    `;
}

/** Workspace 행. `config_file` 이 배지 «안»에 있어 배지도 같이 들어왔습니다. */
export function workspaceRowHtml(ws) {
  const configBadge = ws.has_config
    ? `<span class="badge badge-success">${escapeHtml(ws.config_file)}</span>`
    : `<span class="badge badge-danger">None</span>`;
  const scriptCount = ws.custom_scripts.length;
  const scriptsBadge = scriptCount > 0
    ? `<span class="badge badge-success" style="font-family: var(--font-mono);">${scriptCount} script(s)</span>`
    : `<span class="badge badge-warning">None (Standard)</span>`;
  const rawFilesBadge = ws.raw_files_count > 0
    ? `<span class="badge badge-warning" style="font-family: var(--font-mono); font-weight: bold;">${ws.raw_files_count} file(s)</span>`
    : `<span class="badge badge-success" style="font-family: var(--font-mono);">0</span>`;
  return `
      <td style="font-weight: bold; color: var(--color-primary);">${escapeHtml(ws.name)}</td>
      <td style="font-family: var(--font-mono); font-size: var(--fs-button); font-weight: 500;">${escapeHtml(ws.table_name)}</td>
      <td style="text-align: center;">${configBadge}</td>
      <td style="text-align: center;">${scriptsBadge}</td>
      <td style="text-align: center;">${rawFilesBadge}</td>
    `;
}

/** Mapper 행. 파일명과 모듈명 둘 다 서버가 디스크에서 읽어 준 이름입니다. */
export function mapperRowHtml(mapper) {
  const funcCount = mapper.functions.length;
  return `
      <td style="font-weight: 500; color: var(--text); font-family: var(--font-mono); font-size: var(--fs-button); word-break: break-all;">${escapeHtml(mapper.filename)}</td>
      <td style="font-family: var(--font-mono); font-size: var(--fs-button); color: var(--text-muted);">${escapeHtml(mapper.module_name)}</td>
      <td style="text-align: center; font-weight: bold; color: var(--color-warning);">${funcCount}</td>
      <td style="text-align: center;" onclick="event.stopPropagation()">
        <button class="admin-btn btn-primary btn-edit-mapper">🛠️ Edit</button>
      </td>
    `;
}

/**
 * Auto Update 수집기 행.
 * 🔴 `data-table` · `data-script` 가 이 라운드에서 «제일 중요한 두 칸»입니다 — 속성 «안»이라
 *    따옴표가 안 감싸지면 값이 속성을 닫고 나옵니다. 지난 회차에 사본 셋 중 하나가 정확히
 *    그 문자를 놔두고 있었고, 그래서 이름이 같은데 안전하지 않았습니다.
 */
/**
 * The Backfill cell (lead 09f0be40f). `backfill` = { view: collectorBackfillView(...), open,
 * value, busy, failure } — the page keeps open / typed / failure per collector, this draws it.
 * The button is drawn ON with its own title; the page turns it off through `setDisabledReason`.
 * The run line carries `data-backfill-key` so a poll can rewrite it without the input.
 */
/** The run line's class — the cell draws it and a poll rewrites it, one spelling for both. */
export const backfillLineClass = (line) => `au-backfill-line${line && line.tone ? ` is-${line.tone}` : ''}`;

export function backfillCellHtml(backfill) {
  const b = backfill || {};
  const v = b.view || {};
  if (!v.show) return '';
  const controls = b.open
    ? `<input class="au-backfill-start" placeholder="${BACKFILL_WORDS.placeholder}" value="${escapeHtml(b.value || '')}" aria-label="First day to backfill, KST">
       <button class="admin-btn btn-primary btn-backfill-start"${b.busy ? ' disabled' : ''}>${BACKFILL_WORDS.start}</button>
       <button class="admin-btn btn-backfill-cancel">${BACKFILL_WORDS.cancel}</button>`
    : `<button class="admin-btn btn-primary btn-backfill" title="${escapeHtml(v.title || '')}">${BACKFILL_WORDS.button}</button>`;
  const line = v.line || { text: '', tone: '' };
  return `<div class="au-backfill-controls">${controls}</div>
    <div class="${backfillLineClass(line)}" data-backfill-key="${escapeHtml(v.key || '')}">${escapeHtml(line.text)}</div>
    ${b.failure ? `<div class="au-backfill-line is-danger au-backfill-refusal">${escapeHtml(b.failure)}</div>` : ''}`;
}

export function autoUpdateRowHtml(col, { isActive, nextRunText, lastRunText, backfill }) {
  // The badge's class is the drawer's (retry_verdict, lead 457b34131) — no status ternary here.
  const statusBadge = `<span class="${statusBadgeClass(col.last_status)}">${escapeHtml(col.last_status || 'PENDING')}</span>`;
  const inactiveBadge = isActive ? '' :
    '<span class="badge badge-muted" style="margin-left: 8px; flex: none;">Inactive</span>';
  return `
      <td style="font-weight: bold; color: var(--color-primary);">${escapeHtml(col.table_name)}</td>
      <td style="font-weight: 500; color: var(--text); font-family: var(--font-mono); font-size: var(--fs-button); word-break: break-all;">${escapeHtml(col.script_name)}${inactiveBadge}</td>
      <td style="font-family: var(--font-mono); font-size: var(--fs-button); text-align: center;">${escapeHtml(col.cron_expression)}</td>
      <td style="color: var(--text-muted); font-size: var(--fs-button); font-family: var(--font-mono);" title="${escapeHtml(col.next_run || '')}">${escapeHtml(nextRunText)}</td>
      <td style="color: var(--text-muted); font-size: var(--fs-button); font-family: var(--font-mono);" title="${escapeHtml(col.last_run || '')}">${escapeHtml(lastRunText)}</td>
      <td style="text-align: center;">${statusBadge}</td>
      <td class="au-live" style="text-align: center;" onclick="event.stopPropagation()">
        <label class="au-switch" title="${isActive ? 'Click → deactivate the collector (schedule stops)' : 'Click → activate the collector (schedule resumes)'}">
          <input type="checkbox" class="au-active-toggle" ${isActive ? 'checked' : ''} aria-label="Collector schedule on/off">
          <span class="au-slider"></span>
        </label>
      </td>
      <td class="au-live" style="text-align: center;" onclick="event.stopPropagation()">
        <button class="admin-btn btn-primary btn-run-now" data-table="${escapeHtml(col.table_name)}" data-script="${escapeHtml(col.script_name)}"
         
          title="${isActive ? 'Collect once now' : 'An inactive collector can still be run by hand'}">Run Now</button>
      </td>
      <td class="au-backfill" onclick="event.stopPropagation()">${backfillCellHtml(backfill)}</td>
    `;
}
