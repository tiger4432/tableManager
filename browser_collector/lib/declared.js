// 🔴 THE ONE PLACE the extension spells the product's names (lead 11-07): the four tables and their columns, as the
// server's declaration has them (server/declarations/table_config.json - that file is the canon; a rename there is a
// rename here). Everything else in the extension reads a template as the object below.
//
//   template  { name, address, frame, listArea, item, clickTarget, opens, content, waitSeconds, close, next: {how, selector},
//               endSeconds, max, pair: {item, content} | null, keys: [column], table, fields: [field] }
//   field     { column, base: 'item' | 'content', selector, read: 'text' | '@attr', regex }

export const TABLES = Object.freeze({ templates: 'sys_templates', fields: 'sys_template_fields', runs: 'sys_collect_runs', misses: 'sys_collect_misses' });
const SPLIT = '|';
const num = (v, none) => (v === null || v === undefined || v === '' || Number.isNaN(Number(v)) ? none : Number(v));
const text = (v) => (v === null || v === undefined ? '' : String(v));

/** A template from its sys_templates row and its sys_template_fields rows. */
export function templateOf(row, fieldRows) {
  const fields = fieldRows.filter((f) => f.template === row.template).map((f) => ({
    column: text(f.column), base: f.base === 'content' ? 'content' : 'item', selector: text(f.element),
    read: !f.take || f.take === 'text' ? 'text' : `@${f.take}`, regex: text(f.regex),
  }));
  const [itemCol, contentCol] = text(row.ready_match).split('=').map((s) => s.trim());
  const byName = (c, base) => fields.find((f) => f.column === c && f.base === base) || null;
  const pair = itemCol && contentCol && byName(itemCol, 'item') && byName(contentCol, 'content')
    ? { item: byName(itemCol, 'item'), content: byName(contentCol, 'content') } : null;
  return {
    name: text(row.template), address: text(row.url_pattern), frame: text(row.frame_pattern), listArea: text(row.list_area), item: text(row.list_item),
    clickTarget: text(row.click_target), opens: row.open_method === 'new_tab' ? 'new_tab' : 'in_place',
    content: text(row.content_area), waitSeconds: num(row.timeout_seconds, 10), close: text(row.close_element),
    next: { how: row.next_method === 'scroll' ? 'scroll' : 'button', selector: text(row.next_element) },
    endSeconds: num(row.scroll_end_seconds, 5), max: num(row.max_items, 0),
    pair, pairText: text(row.ready_match),
    keys: text(row.key_columns).split(SPLIT).map((s) => s.trim()).filter(Boolean),
    table: text(row.target_table), fields,
  };
}

/** A template as the rows it is saved as -> {template: row, fields: [row]}. Every row names the target table (edit_by). */
export function rowsOf(t) {
  return {
    template: {
      template: t.name, url_pattern: t.address, frame_pattern: t.frame || null, list_area: t.listArea, list_item: t.item, click_target: t.clickTarget,
      open_method: t.opens, content_area: t.content, timeout_seconds: t.waitSeconds, close_element: t.close,
      next_method: t.next.how, next_element: t.next.selector, scroll_end_seconds: t.endSeconds, max_items: t.max || null,
      ready_match: t.pairText || null, key_columns: t.keys.join(SPLIT), target_table: t.table,
    },
    fields: t.fields.map((f) => ({
      template: t.name, column: f.column, base: f.base, element: f.selector,
      take: f.read === 'text' ? 'text' : f.read.slice(1), regex: f.regex || null, target_table: t.table,
    })),
  };
}

/** The run's row - written at its start and again with its counts at its end. */
export const runRow = (runId, t, startedAt, tally) => ({
  run_id: runId, template: t.name, target_table: t.table, started_at: startedAt,
  written: tally.written, skipped: tally.skipped,
  no_key: tally.misses.filter((m) => m.reason === 'no_key').length,
  not_opened: tally.misses.filter((m) => m.reason === 'not_opened').length,
  refused: tally.misses.filter((m) => m.reason === 'refused').length,
});

/** The items a run kept, one row each - the reason's sentence in `detail`, the values read in `cells`. */
export const missRows = (runId, t, misses) => misses.map((m, i) => ({
  run_id: runId, seq: String(i + 1), target_table: t.table, page_url: m.at, reason: m.reason, detail: m.detail,
  cells: JSON.stringify(m.cells),
}));

/** A kept item as the panel shows it, from its sys_collect_misses row. */
export function missOf(row) {
  let cells = {};
  try { cells = JSON.parse(row.cells || '{}'); } catch { /* a cell that is not JSON */ }
  return { reason: row.reason, at: row.page_url, detail: row.detail, index: Number(row.seq) - 1, cells };
}
