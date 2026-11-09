// The Colours tab (owner 11-06 mockup v3, lead L2 ③): the table's colour rules - each its condition or writer, its role,
// its × - a new rule's form, and the picked cell's paint with its last change. One div, its mount and deps from the page
// (main.js), no module state. What a cell shows is grid_look.lookOf's; this writes sys_looks rows and draws.
// The form is built once: a read of the page draws the list and the paint again, never what a person is typing.

import { ROLES, SHAPES, WRITERS, roleName, isColour, ruleText, ruleUpdate, ruleMove, ruleOff, ruleOn, paintUpdate, paintKey, ruleRefusal } from './grid_look.js';
import { placeBetween, dropPlace } from './grid_order.js';
import { escapeHtml } from './utils.js';
import { FormulaInput } from './formula_input.js';
import { localShort } from './server_time.js';

const NO_CELL = 'Pick a cell of the table';
const NOT_PAINTABLE = 'A key or carried cell is no one row - pick a value cell';
const options = (pairs) => pairs.map(([word, name]) => `<option value="${word}">${name}</option>`).join('');
/** A role's tint on a chip or a swatch - a design role's class, or a picked colour's on the element's own style. */
const tone = (role) => (isColour(role) ? `look-colour" style="--look-colour:${escapeHtml(role)}` : `look-${escapeHtml(role)}`);
/** The colours a rule or a paint takes: the design roles, then any colour (owner 11-09 «색깔 선택») - `on` the one on. */
const colourPick = (data, on, colourData) => `${ROLES.map(([word, name]) => `<button type="button" class="look-swatch look-${word}${
  on === word ? ' is-on' : ''}" ${data}="${word}" aria-label="${name}" title="${name}"></button>`).join('')}<input type="color" class="look-swatch${
  isColour(on) ? ' is-on' : ''}" ${colourData} value="${isColour(on) ? on : '#2b7de9'}" aria-label="Colour" title="Colour">`;

/** The panel's line for what a swatch paints - the picked cell's name, or «N cells · M skipped (key or carried)». */
const paintLabel = ({ targets, skipped, single }) => (single ? single.label : targets.length || skipped
  ? `${targets.length} ${targets.length === 1 ? 'cell' : 'cells'}${skipped ? ` · ${skipped} skipped (key or carried)` : ''}` : '');

export class LookPanel {
  /**
   * @param {HTMLElement} mount
   * @param {{looks: () => object|null, table: () => string|null, columns: () => string[], picked: () => object|null,
   *          write: (update: object, stopped: string) => Promise<boolean>, history: (rowId: string) => Promise<object|null>,
   *          by: string, written: () => void, newId: () => string, say: (text: string) => void}} deps
   *   picked: the picked cell - {rowId, column, label} (paintable), {label} (not), or null
   *   range: a selection of more than one cell - {targets: [{rowId, column}], skipped} - or null
   *   say: a drop that cannot be placed, said with what to do
   */
  constructor(mount, deps) {
    this.deps = deps;
    this.histFor = null;
    this.dragging = null;
    this.root = document.createElement('div');
    this.root.className = 'look-panel';
    this.root.innerHTML = `
      <section class="box look-box">
        <div class="box-head"><h6 class="box-title">Colour rules</h6></div>
        <div class="box-body">
          <div class="look-list"></div>
          <form class="look-form">
            <span class="look-form__when"></span>
            <select name="written_by" class="ctl-small" aria-label="Written by"><option value="">Any writer</option>${options(WRITERS)}</select>
            <select name="shape" class="ctl-small" aria-label="Shape">${options(SHAPES)}</select>
            <input type="hidden" name="role" value="${ROLES[0][0]}">
            <div class="look-swatches look-form__colour" role="group" aria-label="Colour">${colourPick('data-role', ROLES[0][0], 'data-role-colour')}</div>
            <select name="columns" class="ctl-small look-form__cols" multiple aria-label="Columns" title="None picked: every column"></select>
            <button type="submit" class="btn-quiet ctl-small look-form__add">+ Rule</button>
          </form>
        </div>
      </section>
      <section class="box look-box">
        <div class="box-head"><h6 class="box-title">Paint</h6><span class="look-target"></span></div>
        <div class="box-body look-paint"></div>
      </section>`;
    mount.appendChild(this.root);
    this.form = this.root.querySelector('.look-form');
    // the condition is a formula over the cell's [value]: the one formula field, the calculator's words as one types
    this.when = new FormulaInput(this.root.querySelector('.look-form__when'), { doc: document, name: 'when', cls: 'ctl-small',
      placeholder: '[value] > 0.3', label: 'Condition', columns: () => ['value'], refusal: (when) => ruleRefusal({ when }) || '' });
    this.root.addEventListener('click', (e) => this.clicked(e));
    this.form.addEventListener('input', (e) => { if (e.target.matches('[data-role-colour]')) this.pickRole(e.target.value); });
    // a colour picked for the selection's paint - the native picker says it on change (its dialog closed)
    this.root.addEventListener('change', (e) => { if (e.target.matches('[data-paint-colour]')) this.paint(e.target.value); });
    this.form.addEventListener('submit', (e) => { e.preventDefault(); this.addRule(new FormData(this.form)); });
    // a rule dragged to another place in the list - a later rule wins, so its place is what it does
    this.root.addEventListener('dragstart', (e) => {
      const li = e.target.closest && e.target.closest('.look-rule');
      if (!li) return;
      this.dragging = li.dataset.rule;
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', li.dataset.rule);
    });
    this.root.addEventListener('dragover', (e) => { if (this.dragging && e.target.closest('.look-rule')) e.preventDefault(); });
    this.root.addEventListener('drop', (e) => {
      const li = e.target.closest('.look-rule');
      if (!this.dragging || !li) return;
      e.preventDefault();
      this.moveRule(this.dragging, li.dataset.rule);
      this.dragging = null;
    });
    this.root.addEventListener('dragend', () => { this.dragging = null; });
  }

  async moveRule(id, onto) {
    const table = this.deps.table();
    const rules = (this.deps.looks() || { rules: [] }).rules;
    const from = rules.findIndex((rule) => rule.id === id);
    const to = rules.findIndex((rule) => rule.id === onto);
    if (!table || from < 0 || to < 0) return;
    const drop = dropPlace(rules.map((rule) => rule.position), from, to);
    if (!drop) return;
    if (drop.refused) { this.deps.say(`Rule not moved: ${drop.refused}`); return; }
    if (await this.deps.write([ruleMove(table, id, drop.place, this.deps.by)], 'Rule not moved')) this.deps.written();
  }

  /** The cells a swatch paints: the selection's, or the picked one - {targets, skipped, single}; single the picked cell. */
  paintable() {
    const range = this.deps.range();
    if (range) return { targets: range.targets, skipped: range.skipped, single: null };
    const picked = this.deps.picked();
    return { targets: picked && picked.rowId ? [{ rowId: picked.rowId, column: picked.column }] : [], skipped: 0, single: picked };
  }

  draw() {
    const looks = this.deps.looks() || { rules: [], paints: {} };
    // a rule every table has: «Every table», not dragged; its × turns it off here, «On here» back on (server fold)
    const rules = looks.rules.filter((rule) => rule.role || rule.every).map((rule) => `<li class="look-rule${rule.every ? ' is-every' : ''}${
      rule.role ? '' : ' is-off'}" draggable="${rule.every ? 'false' : 'true'}" data-rule="${escapeHtml(rule.id)}">
      <span class="look-rule__text">${escapeHtml(ruleText(rule))}${rule.columns ? `<span class="look-rule__cols"> · ${escapeHtml(rule.columns.join(', '))}</span>` : ''}${
        rule.every ? '<span class="look-rule__every"> · Every table</span>' : ''}</span>
      ${rule.role ? `<span class="chip look-role ${tone(rule.role)}">${escapeHtml(roleName(rule.role))}</span>
      <button type="button" class="chip-remove" data-remove="${escapeHtml(rule.id)}" aria-label="${rule.every ? 'Off on this table' : 'Remove rule'}">×</button>`
        : `<span></span><button type="button" class="btn-quiet ctl-small" data-on="${escapeHtml(rule.id)}">On here</button>`}</li>`).join('');
    this.root.querySelector('.look-list').innerHTML = rules ? `<ul class="look-rules">${rules}</ul>` : '<p class="look-empty">No rules</p>';

    // the table's columns - the ones picked stay picked while the table is the same
    const cols = this.form.querySelector('.look-form__cols');
    const names = this.deps.columns();
    if ([...cols.options].map((o) => o.value).join('\n') !== names.join('\n')) {
      cols.innerHTML = names.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join('');
    }

    const aim = this.paintable();
    const { targets, single } = aim;
    const label = paintLabel(aim);
    const paintOf = (rowId, column) => (looks.paints || {})[paintKey(rowId, column)];
    const roles = targets.map((t) => (paintOf(t.rowId, t.column) || {}).role || '');
    const on = roles.length && roles.every((role) => role === roles[0]) ? roles[0] : null;   // the role they all have
    this.root.querySelector('.look-target').textContent = label;
    const swatches = `${colourPick('data-paint', on, 'data-paint-colour')}<button type="button" class="look-swatch${on === '' ? ' is-on' : ''}"
      data-paint="" aria-label="None" title="None">∅</button>`;
    this.root.querySelector('.look-paint').innerHTML = !label ? `<p class="look-empty">${NO_CELL}</p>`
      : !targets.length ? `<p class="look-empty">${NOT_PAINTABLE}</p>`
        : `<div class="look-swatches">${swatches}</div><p class="look-hist"></p>`;
    this.fillHistory(single && single.rowId ? paintOf(single.rowId, single.column) : null);
  }

  /** The paint's last change - «Danger · lee · 11-06 14:02 — before: none». */
  async fillHistory(paint) {
    const line = this.root.querySelector('.look-hist');
    this.histFor = paint && paint.row_id;
    if (!line || !this.histFor) return;
    const rowId = this.histFor;
    const page = await this.deps.history(rowId).catch(() => null);
    const last = page && page.logs && page.logs[0];
    if (!last || this.histFor !== rowId || !line.isConnected) return;
    const was = (v) => (v === null || v === undefined || v === '' ? 'none' : roleName(String(v)));
    line.textContent = `${was(last.new_value)} · ${last.updated_by || ''} · ${localShort(last.timestamp)} — before: ${was(last.old_value)}`;
  }

  /** The new rule's colour - a design role's word or a picked colour - marked on its swatch. */
  pickRole(role) {
    this.form.elements.role.value = role;
    for (const el of this.form.querySelectorAll('[data-role], [data-role-colour]')) {
      el.classList.toggle('is-on', el.matches('[data-role-colour]') ? isColour(role) : el.dataset.role === role);
    }
  }

  /** The selection's cells painted `role` ('' wipes them). */
  async paint(role) {
    const table = this.deps.table();
    const { targets } = this.paintable();
    if (!table || !targets.length) return;
    if (await this.deps.write(targets.map((t) => paintUpdate(table, t.rowId, t.column, role, this.deps.by)), 'Paint not saved')) this.deps.written();
  }

  async clicked(e) {
    const role = e.target.closest('[data-role]');
    if (role) { this.pickRole(role.dataset.role); return; }
    const table = this.deps.table();
    const remove = e.target.closest('[data-remove]');
    const swatch = e.target.closest('[data-paint]');
    const on = e.target.closest('[data-on]');
    if (!table || (!remove && !swatch && !on)) return;
    let done = false;
    if (remove) {
      done = await this.deps.write([ruleOff(table, remove.dataset.remove, this.deps.by)], 'Rule not removed');
    } else if (on) {
      const rule = ((this.deps.looks() || { rules: [] }).rules).find((r) => r.id === on.dataset.on);
      if (!rule || !rule.under) return;
      done = await this.deps.write([ruleOn(table, rule, this.deps.by)], 'Rule not turned on');
    } else {
      await this.paint(swatch.dataset.paint);
      return;
    }
    if (done) this.deps.written();
  }

  async addRule(form) {
    const table = this.deps.table();
    const when = String(form.get('when') || '').trim();
    const writtenBy = String(form.get('written_by') || '');
    if (!table) return;
    const refused = ruleRefusal({ when, written_by: writtenBy });
    this.when.refuse(refused || '');
    if (refused) return;
    const rules = (this.deps.looks() || { rules: [] }).rules;
    const last = rules.length ? rules[rules.length - 1].position : null;
    const columns = form.getAll('columns').map(String);
    const done = await this.deps.write([ruleUpdate(table, this.deps.newId(), { role: String(form.get('role')), when, written_by: writtenBy,
      columns: columns.length ? columns : null, shape: String(form.get('shape') || ''), position: placeBetween(last, null) }, this.deps.by)],
    'Rule not saved');
    if (!done) return;
    this.form.reset();
    this.when.value = '';
    this.pickRole(ROLES[0][0]);
    this.deps.written();
  }
}
