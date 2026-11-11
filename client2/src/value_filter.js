// VALUE FILTER — a grid column's one filter (lead 11-06 ㄱ, mockup DrvGtAYZ5kLSUd7HvkygaN): Pick · Paste list · Condition.
// Its model is the grid's own - AG Grid's text and number filter models as they were, and a set {"filterType": "set",
// "values": [..., null]} (A ea92380da: null the blank cells, [] no row) - so the chips, the pivot carry and every read take
// it as they took them. The Condition tab is AG Grid's text and number filter again, two conditions and AND/OR (lead: today's
// capability does not shrink); its floating cell types as theirs did (lead: «floating typing stays as today»).
// Community AG Grid has no set filter and lends none of its filters to another, so this is the one filter of every column.

/** AG Grid 35's own option lists (DEFAULT_TEXT_FILTER_OPTIONS · DEFAULT_NUMBER_FILTER_OPTIONS, not exported). */
export const TEXT_OPTIONS = Object.freeze(['contains', 'notContains', 'equals', 'notEqual', 'startsWith', 'endsWith', 'blank', 'notBlank']);
export const NUMBER_OPTIONS = Object.freeze(['equals', 'notEqual', 'greaterThan', 'greaterThanOrEqual', 'lessThan', 'lessThanOrEqual',
  'inRange', 'blank', 'notBlank']);
/** Their words, as AG Grid's English locale says them. */
const OPTION_WORDS = Object.freeze({ contains: 'Contains', notContains: 'Does not contain', equals: 'Equals', notEqual: 'Does not equal',
  startsWith: 'Begins with', endsWith: 'Ends with', blank: 'Blank', notBlank: 'Not blank', greaterThan: 'Greater than',
  greaterThanOrEqual: 'Greater than or equal to', lessThan: 'Less than', lessThanOrEqual: 'Less than or equal to', inRange: 'Between' });
/** AG Grid's text and number floating filters wait this long after a key. */
export const FLOAT_DEBOUNCE_MS = 500;
/** A Pick list draws this many of its values; past it, typing narrows. */
export const PICK_SHOWN = 500;
/** The server's search waits this long after a key (a list past the server's cap is searched there). */
const SEARCH_DEBOUNCE_MS = 300;
export const BLANK_WORD = '(Blank)';

/** How many values a condition type takes: none for the blanks, two for a range. */
export const inputsOf = (type) => (type === 'blank' || type === 'notBlank' ? 0 : type === 'inRange' ? 2 : 1);

const isBlankCell = (v) => v == null || (typeof v === 'string' && v.trim().length === 0);

/** A value typed for a condition, as AG Grid reads it: text as typed ('' none), a number parsed ('' or '-' none). */
function typedValue(kind, raw) {
  if (raw == null) return null;
  if (kind !== 'number') return raw === '' ? null : String(raw);
  if (typeof raw === 'number') return Number.isNaN(raw) ? null : raw;
  const text = String(raw).trim();
  if (text === '' || text === '-') return null;
  const value = Number.parseFloat(text);
  return Number.isNaN(value) ? null : value;
}

/** One condition from its type and typed values, or null while a value it takes is missing (AG Grid's createCondition). */
export function conditionOf(kind, { type, from, to } = {}) {
  const n = inputsOf(type);
  const values = [typedValue(kind, from), typedValue(kind, to)].slice(0, n);
  if (!type || values.some((v) => v == null)) return null;
  const model = { filterType: kind, type };
  if (n > 0) model.filter = values[0];
  if (n > 1) model.filterTo = values[1];
  return model;
}

/** The Condition tab's model: its complete conditions - none, one, or two joined (AG Grid's getModelFromUi). */
export function conditionModel(kind, rows, operator = 'AND') {
  const conditions = rows.map((row) => conditionOf(kind, row)).filter(Boolean);
  if (!conditions.length) return null;
  return conditions.length === 1 ? conditions[0] : { filterType: kind, operator, conditions };
}

/** A condition model back as the tab's rows - the inverse of conditionModel, for a model reopened. */
export function rowsOf(model, defaultOption) {
  const blankRow = { type: defaultOption, from: '', to: '' };
  const conditions = !model || model.filterType === 'set' ? [] : model.operator ? model.conditions || [] : [model];
  const rows = conditions.slice(0, 2).map((c) => ({ type: c.type, from: c.filter ?? '', to: c.filterTo ?? '' }));
  while (rows.length < 2) rows.push({ ...blankRow });
  return { rows, operator: model && model.operator === 'OR' ? 'OR' : 'AND' };
}

/** What a key in the floating cell sets: its one condition of the last type, or none when it is empty (AG Grid's
 *  onFloatingFilterChanged). */
export function floatingModel(kind, type, value) {
  return conditionOf(kind, { type, from: value });
}

/** The type the floating cell types into: the model's first condition's, else the column's first (AG Grid's lastType). */
export function lastTypeOf(model, defaultOption) {
  if (!model || model.filterType === 'set') return defaultOption;
  return (model.operator ? (model.conditions || [])[0] || {} : model).type || defaultOption;
}

/** The floating cell types only into one condition of one value. */
export function floatingEditable(model, lastType) {
  if (!model) return inputsOf(lastType) === 1;
  if (model.filterType === 'set' || model.operator) return false;
  return inputsOf(model.type) === 1;
}

/** «any of 3» - a set's words, the chip's and the floating cell's. */
export const setWords = (model) => `any of ${(model.values || []).length}`;

/** What the floating cell shows (AG Grid's getModelAsString): the value, «1-5», «Blank», «a AND b»; a set its words. */
export function floatingText(model) {
  if (!model) return '';
  if (model.filterType === 'set') return setWords(model);
  if (model.operator) return (model.conditions || []).map(floatingText).join(` ${model.operator} `);
  if (inputsOf(model.type) === 0) return OPTION_WORDS[model.type] || String(model.type);
  if (model.type === 'inRange') return `${model.filter}-${model.filterTo}`;
  return model.filter != null ? `${model.filter}` : `${model.type}`;
}

/** A pasted list: one value per line, comma or tab; trimmed, the empty dropped, each once. A number column's values go as
 *  numbers when they read as one - the server says which do not (422), the screen does not judge them. */
export function pasteValues(kind, text) {
  const seen = new Set();
  const values = [];
  let duplicates = 0;
  for (const part of String(text || '').split(/[\r\n\t,]+/)) {
    const word = part.trim();
    if (!word) continue;
    if (seen.has(word)) { duplicates += 1; continue; }
    seen.add(word);
    values.push(kind === 'number' && word !== '' && Number.isFinite(Number(word)) ? Number(word) : word);
  }
  return { values, duplicates };
}

/** A value's key in a pick: null is the blank cells; a number column's values are numbers. */
const pickKey = (v) => (v == null ? '\u0000blank' : `${typeof v}:${v}`);

const textMatch = (type, value, text) => {
  switch (type) {
    case 'contains': return value.includes(text);
    case 'notContains': return !value.includes(text);
    case 'equals': return value === text;
    case 'notEqual': return value !== text;
    case 'startsWith': return value.startsWith(text);
    case 'endsWith': return value.endsWith(text);
    default: return false;
  }
};

/** One condition on one held cell, as AG Grid's text and number filters judge it (TextFilterHandler · NumberFilterHandler). */
function conditionPasses(kind, c, cell) {
  if (c.type === 'blank') return isBlankCell(cell);
  if (c.type === 'notBlank') return !isBlankCell(cell);
  if (kind !== 'number') {
    if (cell == null) return c.type === 'notEqual' || c.type === 'notContains';
    return textMatch(c.type, String(cell).toLowerCase(), String(c.filter).toLowerCase());
  }
  if (cell == null) return false;
  const v = Number(cell);
  if (Number.isNaN(v)) return c.type === 'notEqual';
  switch (c.type) {
    case 'equals': return v === c.filter;
    case 'notEqual': return v !== c.filter;
    case 'greaterThan': return v > c.filter;
    case 'greaterThanOrEqual': return v >= c.filter;
    case 'lessThan': return v < c.filter;
    case 'lessThanOrEqual': return v <= c.filter;
    case 'inRange': return v > c.filter && v < c.filterTo;
    default: return true;
  }
}

/** Does a held row's cell pass the model - the server's set rule (null the blank cells, a number column's by number), AG
 *  Grid's for a condition. The server narrows the read; this keeps a row the socket brings in to the same rule. */
export function passes(kind, model, cell) {
  if (!model) return true;
  if (model.filterType === 'set') {
    const values = model.values || [];
    if (isBlankCell(cell)) return values.includes(null);
    if (kind === 'number') return values.some((v) => v != null && Number(v) === Number(cell));
    return values.some((v) => v != null && String(v) === String(cell));
  }
  if (model.operator) {
    const each = (model.conditions || []).map((c) => conditionPasses(kind, c, cell));
    return model.operator === 'OR' ? each.some(Boolean) : each.every(Boolean);
  }
  return conditionPasses(kind, model, cell);
}

const TABS = Object.freeze([['pick', 'Pick'], ['paste', 'Paste list'], ['condition', 'Condition']]);

/** A column's filter, AG Grid's custom filter component. filterParams: { kind 'text'|'number', options, defaultOption,
 *  readValues(column, search) -> Promise<{values, more} | {refused}>, doc }. */
export class ValueFilter {
  init(params) {
    this.params = params;
    this.kind = params.kind === 'number' ? 'number' : 'text';
    this.options = params.options || (this.kind === 'number' ? NUMBER_OPTIONS : TEXT_OPTIONS);
    this.defaultOption = params.defaultOption || this.options[0];
    this.doc = params.doc || document;
    this.model = null;
    this.tab = 'pick';
    this.picked = new Map();
    this.list = null;
    this.reads = 0;
    this.searchTimer = null;
    this.hidePopup = null;
    this.build();
  }

  el(tag, cls, text) {
    const node = this.doc.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  button(cls, text, onClick) {
    const b = this.el('button', cls, text);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  build() {
    this.root = this.el('div', 'value-filter base-in-grid');
    this.tabs = this.el('div', 'value-filter__tabs');
    this.tabButtons = TABS.map(([id, word]) => {
      const b = this.button('value-filter__tab', word, () => this.show(id));
      b.dataset.tab = id;
      return b;
    });
    this.tabs.append(...this.tabButtons);
    this.body = this.el('div', 'value-filter__body');
    const foot = this.el('div', 'value-filter__foot');
    this.clearButton = this.button('ctl-small', 'Clear', () => this.apply(null));
    this.applyButton = this.button('ctl-small btn-primary', 'Apply', () => this.applyTab());
    foot.append(this.clearButton, this.applyButton);
    this.root.append(this.tabs, this.body, foot);
    this.buildPick();
    this.buildPaste();
    this.buildCondition();
  }

  buildPick() {
    this.pick = this.el('div', 'value-filter__pane');
    this.searchLabel = this.el('label', 'form-label');
    this.search = this.el('input', 'ctl-small value-filter__search');
    this.search.type = 'text';
    this.search.addEventListener('input', () => this.searched());
    const line = this.el('div', 'value-filter__line');
    const all = this.el('label', 'value-filter__all');
    this.allBox = this.el('input');
    this.allBox.type = 'checkbox';
    this.allBox.addEventListener('change', () => this.pickAllShown(this.allBox.checked));
    this.allWord = this.el('span');
    all.append(this.allBox, this.allWord);
    this.pickedWord = this.el('span', 'value-filter__picked');
    line.append(all, this.pickedWord);
    this.listBox = this.el('div', 'value-filter__list');
    this.pick.append(this.searchLabel, this.search, line, this.listBox);
  }

  buildPaste() {
    this.paste = this.el('div', 'value-filter__pane');
    const label = this.el('label', 'form-label', 'One value per line, comma or tab');
    this.pasteArea = this.el('textarea', 'value-filter__paste');
    this.pasteArea.rows = 9;
    this.pasteArea.addEventListener('input', () => this.drawPasteCount());
    const line = this.el('div', 'value-filter__line');
    this.pasteCount = this.el('span', 'value-filter__count');
    this.pasteDup = this.el('span', 'meta');
    line.append(this.pasteCount, this.pasteDup);
    this.paste.append(label, this.pasteArea, line);
  }

  buildCondition() {
    this.condition = this.el('div', 'value-filter__pane');
    const row = () => {
      const type = this.el('select', 'ctl-small value-filter__type');
      for (const option of this.options) {
        const o = this.el('option', '', OPTION_WORDS[option] || option);
        o.value = option;
        type.appendChild(o);
      }
      const from = this.el('input', 'ctl-small value-filter__from');
      const to = this.el('input', 'ctl-small value-filter__to');
      for (const input of [from, to]) {
        input.type = this.kind === 'number' ? 'number' : 'text';
        input.addEventListener('input', () => this.drawCondition());
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') this.applyTab(); });
      }
      type.addEventListener('change', () => this.drawCondition());
      const box = this.el('div', 'value-filter__cond');
      box.append(type, from, to);
      return { box, type, from, to };
    };
    this.conds = [row(), row()];
    // a form of its own: radios group by name within their form, so two filters' joins never share one
    this.join = this.el('form', 'value-filter__join');
    this.join.addEventListener('submit', (e) => e.preventDefault());
    this.joinBoxes = ['AND', 'OR'].map((op) => {
      const label = this.el('label', 'value-filter__all');
      const radio = this.el('input');
      radio.type = 'radio';
      radio.value = op;
      radio.name = 'join';
      label.append(radio, this.el('span', '', op));
      this.join.appendChild(label);
      return radio;
    });
    this.condition.append(this.conds[0].box, this.join, this.conds[1].box);
  }

  getGui() { return this.root; }
  isFilterActive() { return this.model != null; }
  getModel() { return this.model; }
  setModel(model) { this.model = model || null; }
  // a pivot's carried column (owner 11-11 ㄴ): the server kept the group if any of its long rows passes - a group row
  // holds one value or only how many, so every row it sent passes here
  doesFilterPass(params) { return this.params.server || passes(this.kind, this.model, this.params.getValue(params.node)); }

  /** The floating cell typed (AG Grid's onFloatingFilterChanged): one condition of `type`, or none. */
  onFloatingFilterChanged(type, value) {
    this.model = floatingModel(this.kind, type || this.defaultOption, value);
    this.params.filterChangedCallback({ afterFloatingFilter: true });
  }

  afterGuiAttached(params) {
    this.hidePopup = params && params.hidePopup ? params.hidePopup : null;
    const m = this.model;
    this.picked = new Map(m && m.filterType === 'set' ? (m.values || []).map((v) => [pickKey(v), v]) : []);
    this.search.value = '';
    this.pasteArea.value = '';
    const { rows, operator } = rowsOf(m, this.defaultOption);
    rows.forEach((r, i) => { this.conds[i].type.value = r.type; this.conds[i].from.value = r.from; this.conds[i].to.value = r.to; });
    this.joinBoxes.forEach((radio) => { radio.checked = radio.value === operator; });
    this.show(m && m.filterType !== 'set' ? 'condition' : 'pick');
    this.readList('');
  }

  show(tab) {
    this.tab = tab;
    this.tabButtons.forEach((b) => b.classList.toggle('is-on', b.dataset.tab === tab));
    this.body.replaceChildren({ pick: this.pick, paste: this.paste, condition: this.condition }[tab]);
    if (tab === 'pick') this.drawPick();
    if (tab === 'paste') this.drawPasteCount();
    if (tab === 'condition') this.drawCondition();
  }

  /** The column's values for Pick - the grid's narrowing less this column's own filter; an answer a newer read passed is
   *  dropped. `search` goes to the server only when the list is past its cap. */
  async readList(search) {
    const read = ++this.reads;
    if (!search) { this.list = null; this.drawPick(); }
    const answer = await this.params.readValues(this.params.column.getColId(), search);
    if (read !== this.reads) return;
    this.list = answer && !answer.refused ? { values: answer.values || [], more: Boolean(answer.more), whole: !search && !answer.more }
      : { refused: (answer && answer.refused) || 'Values read failed', values: [] };
    this.drawPick();
  }

  searched() {
    if (!this.list || this.list.whole) { this.drawPick(); return; }
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.readList(this.search.value.trim()), SEARCH_DEBOUNCE_MS);
  }

  /** The values the search shows: a whole list searched here, a list past the cap as the server answered the search. */
  shownValues() {
    if (!this.list || this.list.refused) return [];
    const word = this.search.value.trim().toLowerCase();
    if (!this.list.whole || !word) return this.list.values;
    return this.list.values.filter((v) => (v == null ? BLANK_WORD : String(v)).toLowerCase().includes(word));
  }

  drawPick() {
    if (this.tab !== 'pick') return;
    const list = this.list;
    this.searchLabel.textContent = !list ? 'Reading…' : list.refused ? 'Search'
      : !list.whole ? 'More than 10,000 values — type to search'
      : `Search ${list.values.length.toLocaleString('en-US')} values`;
    const shown = this.shownValues();
    const rows = shown.slice(0, PICK_SHOWN).map((v) => {
      const label = this.el('label', `value-filter__value${v == null ? ' is-blank' : ''}`);
      const box = this.el('input');
      box.type = 'checkbox';
      box.checked = this.picked.has(pickKey(v));
      box.addEventListener('change', () => { this.toggle(v, box.checked); });
      label.append(box, this.el('span', '', v == null ? BLANK_WORD : String(v)));
      return label;
    });
    if (shown.length > PICK_SHOWN) {
      rows.push(this.el('div', 'meta value-filter__more', `${PICK_SHOWN} of ${shown.length.toLocaleString('en-US')} shown — type to narrow`));
    }
    if (list && list.refused) rows.push(this.el('div', 'refusal', list.refused));
    this.listBox.replaceChildren(...rows);
    this.allWord.textContent = `Select all shown (${shown.length.toLocaleString('en-US')})`;
    this.allBox.checked = shown.length > 0 && shown.every((v) => this.picked.has(pickKey(v)));
    this.allBox.disabled = !shown.length;
    this.drawPicked();
  }

  drawPicked() {
    this.pickedWord.textContent = `${this.picked.size.toLocaleString('en-US')} selected`;
    if (this.tab === 'pick') this.applyButton.disabled = !this.picked.size;
  }

  toggle(v, on) {
    if (on) this.picked.set(pickKey(v), v);
    else this.picked.delete(pickKey(v));
    const shown = this.shownValues();
    this.allBox.checked = shown.length > 0 && shown.every((s) => this.picked.has(pickKey(s)));
    this.drawPicked();
  }

  pickAllShown(on) {
    for (const v of this.shownValues()) {
      if (on) this.picked.set(pickKey(v), v);
      else this.picked.delete(pickKey(v));
    }
    this.drawPick();
  }

  drawPasteCount() {
    const { values, duplicates } = pasteValues(this.kind, this.pasteArea.value);
    this.pasteCount.textContent = `${values.length.toLocaleString('en-US')} values · equals any`;
    this.pasteDup.textContent = duplicates ? `${duplicates} duplicate${duplicates === 1 ? '' : 's'} removed` : '';
    if (this.tab === 'paste') this.applyButton.disabled = !values.length;
  }

  conditionRows() {
    return this.conds.map((c) => ({ type: c.type.value, from: c.from.value, to: c.to.value }));
  }

  /** The second condition and its join come once the first is complete (AG Grid's); a range shows its second box. */
  drawCondition() {
    const rows = this.conditionRows();
    this.conds.forEach((c, i) => {
      const n = inputsOf(rows[i].type);
      c.from.hidden = n < 1;
      c.to.hidden = n < 2;
    });
    const second = conditionOf(this.kind, rows[0]) != null;
    this.join.hidden = !second;
    this.conds[1].box.hidden = !second;
    if (this.tab === 'condition') this.applyButton.disabled = false;
  }

  applyTab() {
    if (this.tab === 'pick') return this.apply({ filterType: 'set', values: [...this.picked.values()] });
    if (this.tab === 'paste') return this.apply({ filterType: 'set', values: pasteValues(this.kind, this.pasteArea.value).values });
    const rows = this.conditionRows();
    const first = conditionOf(this.kind, rows[0]);
    const operator = (this.joinBoxes.find((r) => r.checked) || {}).value || 'AND';
    return this.apply(conditionModel(this.kind, first ? rows : [rows[0]], operator));
  }

  apply(model) {
    this.model = model;
    this.params.filterChangedCallback();
    if (this.hidePopup) this.hidePopup();
  }

  destroy() { clearTimeout(this.searchTimer); this.reads += 1; }
}

/** Its floating cell: typing is one condition of the last type, as AG Grid's was; a set, a range, a blank or two conditions
 *  read here and open the filter on a click. */
export class ValueFloatingFilter {
  init(params) {
    this.params = params;
    const fp = params.filterParams || {};
    this.kind = fp.kind === 'number' ? 'number' : 'text';
    this.defaultOption = fp.defaultOption || (fp.options || (this.kind === 'number' ? NUMBER_OPTIONS : TEXT_OPTIONS))[0];
    const doc = fp.doc || document;
    // AG Grid's own floating input's classes, so its theme draws this one as it drew that one
    const div = (cls) => { const d = doc.createElement('div'); d.className = cls; return d; };
    this.root = div('value-floating ag-floating-filter-input');
    const field = div('ag-input-field ag-text-field');
    const wrap = div('ag-wrapper ag-input-wrapper ag-text-field-input-wrapper');
    this.input = doc.createElement('input');
    // base-in-grid: drawn as the base layer's input (owner 11-09 - the theme drew no line style, the browser's inset showed)
    this.input.className = 'value-floating__input ag-input-field-input ag-text-field-input base-in-grid';
    this.input.setAttribute('aria-label', `${params.column.getColDef().headerName || params.column.getColId()} Filter Input`);
    wrap.appendChild(this.input);
    field.appendChild(wrap);
    this.root.appendChild(field);
    this.timer = null;
    this.input.addEventListener('input', () => {
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.typed(), FLOAT_DEBOUNCE_MS);
    });
    this.input.addEventListener('click', () => { if (this.input.readOnly && params.showParentFilter) params.showParentFilter(); });
    this.lastType = this.defaultOption;
    this.onParentModelChanged(params.currentParentModel ? params.currentParentModel() : null);
  }

  getGui() { return this.root; }

  typed() {
    const value = this.input.value;
    this.params.parentFilterInstance((filter) => { if (filter) filter.onFloatingFilterChanged(this.lastType, value); });
  }

  onParentModelChanged(model, event) {
    if (event && event.afterFloatingFilter) return;
    this.lastType = lastTypeOf(model, this.defaultOption);
    const editable = floatingEditable(model, this.lastType);
    this.input.type = editable && this.kind === 'number' ? 'number' : 'text';
    this.input.readOnly = !editable;
    this.input.classList.toggle('is-read', !editable);
    this.input.value = floatingText(model);
  }

  destroy() { clearTimeout(this.timer); }
}
