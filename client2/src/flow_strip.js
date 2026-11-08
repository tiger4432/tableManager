// FLOW STRIP - where the open table's rows come from and where they go, under the page's top bar (owner 11-06, mockup
// 5X4wGr6QwEoa4bQ8D7BB47; lead 11-08 ㄱ). One walk of the system world from the table's node answers it: the rules
// that write it and what they read, the ingestions that fill it, the rules that read it and what they write, and which
// of its columns a rule writes - the grid's header reads that last part (`onAnswer`). The ledger sources that read it
// are the source label's answer (`setSources`, lead 11-08 ㄴ: one answer, the label's words). The walk runs only while
// the strip is open. Assembled part: its host and deps, no module state.
// NO DOM GLOBALS, NO NETWORK - a bare node document stub scores it.

/** The walk the strip asks: two steps from the table, along these predicates only. */
export const FLOW_FOLLOW = Object.freeze(['writes', 'reads_from', 'fills', 'has_column', 'writes_column',
  'joins_on', 'decides_by', 'triggered_by']);
export const FLOW_HOPS = 2;

const attr = (node, name) => {
  const value = node && node.attributes ? node.attributes[name] : undefined;
  return value === undefined || value === null || value === '' ? null : value;
};
const sorted = (items) => [...new Set(items)].sort();

/** The strip's model of one walk answer for `table` - null when the answer holds no node for it.
 *  {table: {name, keys, description}, comesFrom: [rule], fills: [{name, folder}], feeds: [rule],
 *   columns: {column: [rule]}} - a rule {name, kind, when, from, to, on}. */
export function flowOf(body, table) {
  const nodes = new Map((body && Array.isArray(body.nodes) ? body.nodes : []).map((node) => [node.id, node]));
  const edges = body && Array.isArray(body.edges) ? body.edges : [];
  const self = [...nodes.values()].find((node) => node.type === 'table' && node.keys && node.keys.table === table);
  if (!self) return null;
  const ends = (from, predicate) => edges.filter((edge) => edge.source === from && edge.predicate === predicate)
    .map((edge) => nodes.get(edge.target)).filter(Boolean);
  const into = (predicate) => edges.filter((edge) => edge.target === self.id && edge.predicate === predicate)
    .map((edge) => nodes.get(edge.source)).filter(Boolean);
  const rule = (node) => ({
    name: node.keys.rule, kind: attr(node, 'kind'), when: attr(node, 'when'),
    from: sorted(ends(node.id, 'reads_from').map((each) => each.keys.table)),
    to: sorted(ends(node.id, 'writes').map((each) => each.keys.table)),
    on: sorted(ends(node.id, 'joins_on').map((each) => each.keys.column)),
  });
  const writers = into('writes').map(rule).sort((a, b) => a.name.localeCompare(b.name));
  const written = new Set(writers.map((each) => each.name));
  const columns = {};
  for (const node of into('writes').concat(into('reads_from'))) {
    for (const column of ends(node.id, 'writes_column')) {
      if (column.keys.table !== table) continue;
      const list = columns[column.keys.column] || (columns[column.keys.column] = []);
      if (!list.some((each) => each.name === node.keys.rule)) list.push(rule(node));
    }
  }
  for (const list of Object.values(columns)) list.sort((a, b) => a.name.localeCompare(b.name));
  return {
    table: { name: table, keys: attr(self, 'key_columns'), description: attr(self, 'description') },
    comesFrom: writers,
    fills: into('fills').map((node) => ({ name: node.keys.ingestion, folder: attr(node, 'folder') }))
      .sort((a, b) => a.name.localeCompare(b.name)),
    // a rule that writes this table too sits under «Comes from» - a formula reads and writes its own table
    feeds: into('reads_from').filter((node) => !written.has(node.keys.rule)).map(rule)
      .sort((a, b) => a.name.localeCompare(b.name)),
    columns,
  };
}

/** A column's header tip lines from the rules that write it - «written by the chain» and each rule's facts. */
export function chainTipLines(rules) {
  if (!Array.isArray(rules) || !rules.length) return [];
  return ['written by the chain', ...rules.map((each) => [
    `${each.name}${each.kind ? ` (${each.kind})` : ''}`,
    each.from.length ? `from ${each.from.join(', ')}` : '',
    each.on.length ? `joined on ${each.on.join(', ')}` : '',
    each.when || '',
  ].filter(Boolean).join(' · '))];
}

export class FlowStrip {
  /**
   * @param {HTMLElement} host its own div
   * @param {{doc?: Document, walk: (table: string) => Promise<{ok: boolean, body?: object, message?: string}>,
   *          onAnswer?: (model: object|null) => void, onPickTable?: (table: string) => void,
   *          onEdit?: (table: string) => void, sourceWord?: (answer: object|null) => string|null}} deps
   *        sourceWord: the source label's words for an answer with no source line
   */
  constructor(host, deps = {}) {
    if (!host) throw new Error('FlowStrip needs a host element');
    this.host = host;
    this.doc = deps.doc || host.ownerDocument;
    this.walk = deps.walk || null;
    this.onAnswer = deps.onAnswer || (() => {});
    this.onPickTable = deps.onPickTable || (() => {});
    this.onEdit = deps.onEdit || (() => {});
    this.sourceWord = deps.sourceWord || (() => null);
    this.sources = null;
    this.open = false;
    this.table = null;
    this.state = 'closed';
    this.model = null;
    this.message = null;
    this.asked = 0;
    this.told = null;
  }

  /** The answer handed to the page - only when it changed, so a closed strip costs the grid nothing on a table switch. */
  _tell(model) {
    if (model === this.told) return;
    this.told = model;
    this.onAnswer(model);
  }

  /** The strip shown or not - shown, it walks the open table. */
  setOpen(open) {
    this.open = Boolean(open);
    return this.read();
  }

  /** The page's open table - walked again while the strip is open. */
  setTable(table) {
    if ((table || null) === this.table) return Promise.resolve();
    this.table = table || null;
    return this.read();
  }

  /** The source label's answer ({relation, state, rows, operating}) - drawn again, not walked. */
  setSources(answer) {
    this.sources = answer || null;
    this.render();
  }

  /** The Ledger side: a box per source line of the label's answer for this table, else the label's words for it. */
  _ledger() {
    const answer = this.sources && this.sources.relation === this.table ? this.sources : null;
    const rows = answer && Array.isArray(answer.rows) ? answer.rows : [];
    if (!rows.length) {
      const word = this.sourceWord(answer);
      return { boxes: [], word: answer && answer.state === 'not_source' ? null : word };
    }
    return { word: null, boxes: rows.map((row) => {
      const box = this._box('ledger', 'Ledger', [this._id('flow-strip__rule', row.source),
        ...(row.world && row.world !== answer.operating ? [this._el('span', 'flow-strip__meta', row.world)] : [])],
      row.planned === false ? (row.refusal && row.refusal.message) || 'refused' : '');
      if (row.planned === false) box.className += ' is-refused';
      return box;
    }) };
  }

  async read() {
    const mine = ++this.asked;
    this.model = null;
    this.message = null;
    if (!this.open || !this.table) {
      this.state = this.open ? 'idle' : 'closed';
      this._tell(null);
      this.render();
      return;
    }
    this.state = 'loading';
    this.render();
    let got = null;
    try {
      got = this.walk ? await this.walk(this.table) : { ok: false, message: 'no walk was injected' };
    } catch (err) {
      got = { ok: false, message: `walk unreachable - ${err && err.message}` };
    }
    if (mine !== this.asked) return;
    if (got && got.ok) {
      this.model = flowOf(got.body, this.table);
      this.state = this.model ? 'ready' : 'absent';
    } else {
      this.state = 'refused';
      this.message = (got && got.message) || 'walk refused';
    }
    this._tell(this.model);
    this.render();
  }

  _el(tag, cls, text) {
    const el = this.doc.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
  }

  _tableLink(name) {
    const button = this._el('button', 'flow-strip__table', name);
    button.type = 'button';
    button.addEventListener('click', () => this.onPickTable(name));
    return button;
  }

  /** A name the strip draws - a rule, a file, a source, a folder: one long id that goes down where it must
   *  (data-wrap-ok, lead 10-09). */
  _id(cls, text) {
    const span = this._el('span', cls, text);
    span.setAttribute('data-wrap-ok', '');
    return span;
  }

  _box(kind, kindWord, parts, tip) {
    const box = this._el('div', `flow-strip__item flow-strip__item--${kind}`);
    box.appendChild(this._el('span', 'flow-strip__kind', kindWord));
    for (const part of parts) box.appendChild(part);
    if (tip) box.title = tip;
    return box;
  }

  _rule(each, tables) {
    const parts = tables.map((name) => this._tableLink(name));
    parts.push(this._id('flow-strip__rule', each.name));
    if (each.on.length) parts.push(this._el('span', 'flow-strip__meta', `on ${each.on.join(', ')}`));
    return this._box('rule', each.kind || 'rule', parts, each.when || '');
  }

  _side(title, items, emptyWord) {
    const side = this._el('div', 'flow-strip__side');
    side.appendChild(this._el('span', 'flow-strip__title', title));
    if (!items.length) side.appendChild(this._el('span', 'flow-strip__none', emptyWord));
    for (const item of items) side.appendChild(item);
    return side;
  }

  render() {
    this.host.textContent = '';
    this.host.hidden = this.state === 'closed';
    if (this.state === 'closed') return;
    const root = this._el('section', `flow-strip is-${this.state}`);
    root.setAttribute('aria-label', `Flow of ${this.table || 'no table'}`);
    if (this.state !== 'ready') {
      const words = { idle: 'No table open', loading: 'Reading the flow…', absent: `${this.table} is not in the system world`,
        refused: this.message };
      root.appendChild(this._el('span', 'flow-strip__line', words[this.state]));
      this.host.appendChild(root);
      return;
    }
    const m = this.model;
    const comes = [
      ...m.fills.map((each) => this._box('file', 'File', [this._id('flow-strip__rule', each.name),
        ...(each.folder ? [this._id('flow-strip__meta flow-strip__path', each.folder)] : [])])),
      ...m.comesFrom.map((each) => this._rule(each, each.from.filter((name) => name !== m.table.name))),
    ];
    const ledger = this._ledger();
    const feeds = [
      ...m.feeds.map((each) => this._rule(each, each.to)),
      ...ledger.boxes,
      ...(ledger.word ? [this._el('span', 'flow-strip__none', ledger.word)] : []),
    ];
    root.appendChild(this._side('Comes from', comes, 'Nothing writes it'));
    root.appendChild(this._el('span', 'flow-strip__arrow', '→'));
    const centre = this._el('div', 'flow-strip__centre');
    const head = this._el('div', 'flow-strip__head');
    head.appendChild(this._el('span', 'flow-strip__name', m.table.name));
    if (m.table.keys) head.appendChild(this._el('span', 'flow-strip__meta', `key ${m.table.keys}`));
    centre.appendChild(head);
    centre.appendChild(this._el('span', m.table.description ? 'flow-strip__description' : 'flow-strip__none',
      m.table.description || 'No description'));
    const edit = this._el('button', 'flow-strip__edit', 'Edit');
    edit.type = 'button';
    edit.addEventListener('click', () => this.onEdit(m.table.name));
    centre.appendChild(edit);
    root.appendChild(centre);
    root.appendChild(this._el('span', 'flow-strip__arrow', '→'));
    root.appendChild(this._side('Feeds', feeds, 'Nothing reads it'));
    this.host.appendChild(root);
  }
}
