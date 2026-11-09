// What a table's cells look like (owner 11-06, lead L2): colour rules and hand paint, rows of the shipped `sys_looks`
// beside the places (server/grid_look.py reads a page's). A rule gives a cell its role when its condition holds
// ([value] the cell's value, the expression language - src/expression.js) and the cell's writer is its written_by - each
// blank = any - on its columns (none = every column) - drawn as its shape: a fill behind the text, or a line (a left edge
// and the text in its role's colour, over a fill - owner 11-08 2ㄱ). A paint gives one cell its fill by hand. The rules
// every table has come with the read (server/grid_look.py fold, `every`). `lookOf` is the one seat that says which: a
// paint over every rule, a later rule over an earlier one (lead 11-07 ㄱ).

import { compile, run } from './expression.js';
import { LOOK_TABLE, cellOf, lookUpdate, placesOn } from './grid_order.js';

export const RULE = 'rule';
/** Said on the document when the looks or the picked cell changed - the Colours tab and the legend draw again. */
export const LOOKS_CHANGED = 'looks-changed';
export const saidLooksChanged = () => {
  if (typeof document !== 'undefined' && typeof document.dispatchEvent === 'function') document.dispatchEvent(new Event(LOOKS_CHANGED));
};
export const PAINT = 'paint';
/** The look_table of a rule every table has (server grid_look.EVERY). */
export const EVERY = '*';
/** A rule's shapes - its word, as it is stored (blank = fill), and its name on screen. */
export const LINE = 'line';
export const SHAPES = Object.freeze([['fill', 'Fill'], [LINE, 'Line']]);
/** The design roles a look takes - its word, as it is stored, and its name on screen. */
export const ROLES = Object.freeze([['ok', 'Ok'], ['warn', 'Warn'], ['danger', 'Danger'], ['accent', 'Accent']]);
/** Who wrote a cell (crud.writer_kind) - the words a rule's written_by picks. */
export const PERSON = 'person';
export const WRITERS = Object.freeze([[PERSON, 'Person'], ['chain', 'Chain'], ['ai', 'AI'], ['file', 'File'], ['merge', 'Merge']]);
/** A rule that is neither a condition nor a writer. */
export const RULE_EMPTY_NOTE = 'Write a condition or pick a writer';

const wordName = (pairs, word) => (pairs.find(([w]) => w === word) || [])[1] || word;
export const roleName = (role) => wordName(ROLES, role);

/** A paint's key - the row's id, then the column (a row id holds no «/»). */
export const paintKey = (rowId, column) => `${rowId}/${column}`;

const compiled = new Map();
function holds(text, value) {
  if (!compiled.has(text)) compiled.set(text, compile(text));
  const answer = run(compiled.get(text), [{ value }]);
  return Boolean(answer.values) && answer.values[0] === true;
}

/** The look of one cell: `rowId` its row, `column` its column, `cell` its {value, written_by} -> {role, hand} with
 *  `line` when a line rule holds, or null. `role` the fill (a paint's, else the last fill rule's), `line` the last line
 *  rule's. `looks` {rules: [in order], paints: {paintKey: {role}}} - null or absent: not said, nothing drawn. */
export function lookOf(looks, rowId, column, cell) {
  if (!looks) return null;
  const paint = (looks.paints || {})[paintKey(rowId, column)];
  let role = null;
  let line = null;
  for (const rule of looks.rules || []) {
    if (!rule.role || (rule.columns && !rule.columns.includes(column))) continue;
    if (rule.written_by && !(cell && cell.written_by === rule.written_by)) continue;
    if (!rule.when && !rule.written_by) continue;
    if (rule.when && !holds(rule.when, cell ? cell.value : null)) continue;
    if (rule.shape === LINE) line = rule.role;
    else role = rule.role;
  }
  const hand = Boolean(paint && paint.role);
  if (hand) role = paint.role;
  return role || line ? { role, hand, ...(line ? { line } : {}) } : null;
}

/** Why a rule cannot be saved - neither a condition nor a writer, or a condition the calculator refuses (its words) -
 *  or null. */
export function ruleRefusal({ when = '', written_by = '' }) {
  if (!String(when).trim() && !written_by) return RULE_EMPTY_NOTE;
  if (!String(when).trim()) return null;
  const read = compile(when);
  return read.ok ? null : read.why;
}

/** A rule as its list says it - its condition, its writer, a line's shape. */
export function ruleText(rule) {
  return [rule.when, rule.written_by ? `Written by: ${wordName(WRITERS, rule.written_by)}` : null,
    rule.shape === LINE ? wordName(SHAPES, LINE) : null].filter(Boolean).join(' · ');
}

/** A rule's write - its role, condition, writer, columns (`null` = every column) and shape at its place in the list. */
export function ruleUpdate(table, id, { role, when = '', written_by = '', columns = null, shape = '', position }, by) {
  return lookUpdate(table, RULE, id, { role, rule_when: when, written_by, rule_columns: columns ? JSON.stringify(columns) : '',
    shape, ...(position ? { position } : {}) }, by);
}

/** A rule moved to `position` (grid_order.dropPlace over the rules' positions) - its other cells not touched. */
export const ruleMove = (table, id, position, by) => lookUpdate(table, RULE, id, { position }, by);

/** A rule taken off - its role wiped; its condition, writer and columns stay (its history says what it was). On a rule
 *  every table has, the table's row of its key: off on this table only (server grid_look.fold). */
export const ruleOff = (table, id, by) => lookUpdate(table, RULE, id, { role: '' }, by);

/** A rule every table has, on again on this table - its table row's role the one it turned off (`under`). */
export const ruleOn = (table, rule, by) => lookUpdate(table, RULE, rule.id, { role: rule.under }, by);

/** The paints a selection asks: `cells` {rowIndex, colId}, `targetOf(cell)` the stored cell it is (grid.lookTarget) or
 *  null -> {targets: [{rowId, column}] once each, skipped: the cells that are no one row's (a pivot's key or carried)}. */
export function paintTargets(cells, targetOf) {
  const seen = new Map();
  let skipped = 0;
  for (const cell of cells) {
    const at = targetOf(cell);
    if (!at || !at.rowId) { skipped += 1; continue; }
    seen.set(paintKey(at.rowId, at.column), { rowId: at.rowId, column: at.column });
  }
  return { targets: [...seen.values()], skipped };
}

/** A paint's write - `role` '' wipes it. */
export const paintUpdate = (table, rowId, column, role, by) => lookUpdate(table, PAINT, paintKey(rowId, column), { role }, by);

const columnsOf = (text) => { try { const v = JSON.parse(text); return Array.isArray(v) && v.length ? v.map(String) : null; } catch { return null; } };

/** `looks` with a sys_looks broadcast's rows on `table` taken in -> the new looks, or null when it names none of them. */
export function looksOn(msg, table, looks) {
  const items = (msg && Array.isArray(msg.items) ? msg.items : []).filter((item) => cellOf(item, 'look_table') === table
    && [RULE, PAINT].includes(cellOf(item, 'look_axis')));
  if (!items.length) return null;
  const rules = new Map(((looks && looks.rules) || []).map((rule) => [rule.id, rule]));
  const paints = { ...((looks && looks.paints) || {}) };
  for (const item of items) {
    const key = cellOf(item, 'look_key');
    const role = cellOf(item, 'role') || null;
    if (cellOf(item, 'look_axis') === PAINT) {
      if (role) paints[key] = { role, row_id: item.row_id };
      else delete paints[key];
    } else if (!role) {
      rules.delete(key);
    } else {
      rules.set(key, { id: key, row_id: item.row_id, position: cellOf(item, 'position') || key, role,
        when: cellOf(item, 'rule_when') || null, columns: columnsOf(cellOf(item, 'rule_columns')),
        written_by: cellOf(item, 'written_by') || null, shape: cellOf(item, 'shape') || 'fill' });
    }
  }
  const order = (a, b) => (a.position < b.position ? -1 : a.position > b.position ? 1 : a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  return { rules: [...rules.values()].sort(order), paints };
}

/** What a sys_looks broadcast does to the screen showing `table` (`entered`: read in entered order, `written`: the
 *  places it wrote) -> {reread: true} - a rule (a writer rule's cells say their writer only on a read; a rule every
 *  table has is this one's too), a place moved, or a message with no rows (past the server's BROADCAST_ITEM_LIMIT, or a
 *  delete) - unless its `edits_of` (the tables written, server access.edits_of) leaves this one and EVERY out - or
 *  {looks} drawn from the message, or {} when it is not this table's. */
export function lookBroadcast(msg, table, looks, { entered = false, written = new Set() } = {}) {
  const items = msg && Array.isArray(msg.items) ? msg.items : [];
  if (!items.length) {
    return Array.isArray(msg && msg.edits_of) && !msg.edits_of.includes(table) && !msg.edits_of.includes(EVERY) ? {} : { reread: true };
  }
  if (items.some((item) => cellOf(item, 'look_table') === EVERY && cellOf(item, 'look_axis') === RULE)) return { reread: true };
  const taken = looksOn(msg, table, looks);
  if ((taken && items.some((item) => cellOf(item, 'look_axis') === RULE)) || (entered && placesOn(msg, table, written))) {
    return { reread: true };
  }
  return taken ? { looks: taken } : {};
}

/** A page's looks taken in: `append` keeps the paints of the pages already shown (rules are the table's, whole). */
export function pageLooks(looks, answer, append = false) {
  if (!answer) return append ? looks : null;
  return { rules: answer.rules || [], paints: { ...(append && looks ? looks.paints : {}), ...(answer.paints || {}) } };
}

export { LOOK_TABLE };
