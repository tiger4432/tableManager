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

/** File Ingestion 로그 행. `withStatus` 는 Auto Update 탭 실패 목록과 공용이라 남습니다. */
export function fileLogRowHtml(log, { withStatus, timeStr }) {
  const statusBadge = `<span class="badge ${log.status === 'SUCCESS' ? 'badge-success' : 'badge-danger'}">${escapeHtml(log.status || 'FAILED')}</span>`;
  const retryBtnHtml = log.status === 'SUCCESS'
    ? `<button class="admin-btn btn-primary" style="padding: 4px 10px; font-size: 0.75rem; opacity: 0.5; cursor: not-allowed;" disabled>Retry</button>`
    : `<button class="admin-btn btn-primary btn-retry-file" data-id="${escapeHtml(log.id)}" style="padding: 4px 10px; font-size: 0.75rem;">Retry</button>`;
  // 감사 P2: 파일명은 상태와 무관한 중립색(모노) — 상태색은 배지에만
  const retryStyle = log.retry_count > 0
    ? 'color: var(--warning); font-weight: 600;'
    : 'color: var(--text-dim);';
  return `
    <td>${escapeHtml(log.id)}</td>
    <td style="font-weight: 500; color: var(--text); font-family: var(--font-mono); font-size: 0.85rem; word-break: break-all;">${escapeHtml(log.filename)}</td>
    <td style="font-weight: bold; color: var(--color-primary);">${escapeHtml(log.table_name)}</td>
    ${withStatus ? `<td style="text-align: center;">${statusBadge}</td>` : ''}
    <td style="text-align: center; ${retryStyle}">${escapeHtml(log.retry_count)}</td>
    <td style="color: var(--text-muted); font-size: 0.85rem; font-family: var(--font-mono);" title="${escapeHtml(log.created_at || '')}">${escapeHtml(timeStr)}</td>
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
  const statusNote = item.status === 'QUEUED' ? ' 대기' : '';
  // 🔴 `|| 0` USED TO BE HERE and it turned 「안 왔다」 into 「0개 처리했다」 — a
  //    number the server never sent. `localeCountText` keeps the two apart.
  const rowsText = (item.total_rows != null)
    ? `${localeCountText(item.processed_rows)} / ${localeCountText(item.total_rows)}`
    : (isCount(item.processed_rows) && Number(item.processed_rows) > 0
      ? localeCountText(item.processed_rows) : '-');
  return `
      <td style="font-family: var(--font-mono); font-size: 0.85rem; color: var(--text); word-break: break-all;">${escapeHtml(item.filename)}</td>
      <td style="font-weight: bold; color: var(--color-primary);">${escapeHtml(item.table_name)}</td>
      <td style="text-align: center;">${laneBadge}</td>
      <td>
        <div style="display: flex; align-items: center; gap: 8px;">
          <div style="flex: 1; height: 6px; border-radius: 3px; background: var(--bg-inset); border: 1px solid var(--border); overflow: hidden;">
            <div style="width: ${pct}%; height: 100%; background: var(--accent); transition: width 0.4s;"></div>
          </div>
          <span style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--text-muted); min-width: 46px; text-align: right;">${pct}%${statusNote}</span>
        </div>
      </td>
      <td style="text-align: center; font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted);">${rowsText}</td>
      <td style="text-align: center; font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-muted);">${escapeHtml(elapsedText)}</td>
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
      <td style="font-family: var(--font-mono); font-size: 0.85rem; font-weight: 500;">${escapeHtml(ws.table_name)}</td>
      <td style="text-align: center;">${configBadge}</td>
      <td style="text-align: center;">${scriptsBadge}</td>
      <td style="text-align: center;">${rawFilesBadge}</td>
    `;
}

/** Mapper 행. 파일명과 모듈명 둘 다 서버가 디스크에서 읽어 준 이름입니다. */
export function mapperRowHtml(mapper) {
  const funcCount = mapper.functions.length;
  return `
      <td style="font-weight: 500; color: var(--text); font-family: var(--font-mono); font-size: 0.85rem; word-break: break-all;">${escapeHtml(mapper.filename)}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; color: var(--text-muted);">${escapeHtml(mapper.module_name)}</td>
      <td style="text-align: center; font-weight: bold; color: var(--color-warning);">${funcCount}</td>
      <td style="text-align: center;" onclick="event.stopPropagation()">
        <button class="admin-btn btn-primary btn-edit-mapper" style="padding: 4px 10px; font-size: 0.75rem;">🛠️ Edit</button>
      </td>
    `;
}

/**
 * Auto Update 수집기 행.
 * 🔴 `data-table` · `data-script` 가 이 라운드에서 «제일 중요한 두 칸»입니다 — 속성 «안»이라
 *    따옴표가 안 감싸지면 값이 속성을 닫고 나옵니다. 지난 회차에 사본 셋 중 하나가 정확히
 *    그 문자를 놔두고 있었고, 그래서 이름이 같은데 안전하지 않았습니다.
 */
export function autoUpdateRowHtml(col, { isActive, nextRunText, lastRunText }) {
  const statusBadge = `<span class="badge ${
    col.last_status === 'SUCCESS' ? 'badge-success' :
    col.last_status === 'FAIL' ? 'badge-danger' :
    col.last_status === 'RUNNING' ? 'badge-warning' : 'badge-warning'
  }">${escapeHtml(col.last_status || 'PENDING')}</span>`;
  const inactiveBadge = isActive ? '' :
    '<span class="badge badge-muted" style="margin-left: 8px; flex: none;">비활성</span>';
  return `
      <td style="font-weight: bold; color: var(--color-primary);">${escapeHtml(col.table_name)}</td>
      <td style="font-weight: 500; color: var(--text); font-family: var(--font-mono); font-size: 0.85rem; word-break: break-all;">${escapeHtml(col.script_name)}${inactiveBadge}</td>
      <td style="font-family: var(--font-mono); font-size: 0.85rem; text-align: center;">${escapeHtml(col.cron_expression)}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem; font-family: var(--font-mono);" title="${escapeHtml(col.next_run || '')}">${escapeHtml(nextRunText)}</td>
      <td style="color: var(--text-muted); font-size: 0.85rem; font-family: var(--font-mono);" title="${escapeHtml(col.last_run || '')}">${escapeHtml(lastRunText)}</td>
      <td style="text-align: center;">${statusBadge}</td>
      <td class="au-live" style="text-align: center;" onclick="event.stopPropagation()">
        <label class="au-switch" title="${isActive ? '클릭 → 수집기 비활성화 (스케줄 중단)' : '클릭 → 수집기 활성화 (스케줄 재개)'}">
          <input type="checkbox" class="au-active-toggle" ${isActive ? 'checked' : ''} aria-label="수집기 스케줄 활성 토글">
          <span class="au-slider"></span>
        </label>
      </td>
      <td class="au-live" style="text-align: center;" onclick="event.stopPropagation()">
        <button class="admin-btn btn-primary btn-run-now" data-table="${escapeHtml(col.table_name)}" data-script="${escapeHtml(col.script_name)}"
          style="padding: 4px 10px; font-size: 0.75rem;"
          title="${isActive ? '즉시 1회 수집 실행' : '비활성 수집기도 수동 실행은 가능합니다'}">Run Now</button>
      </td>
    `;
}
