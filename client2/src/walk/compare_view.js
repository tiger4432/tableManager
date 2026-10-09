// ═══════════════════════════════════════════════════════════════════════════════
// COMPARE — the start marking's signs side by side (lead 10-09, demo ③).
//
// Rows: the nodes of a picked type the walk reaches from every start (+ and −). Columns: the signs. A cell: the picked
// value of the picked edge into that row, from what that sign's starts reached; several edges say every value and
// whose (table_view's fold), none is a red «missing», an edge without the value the absent mark. The three picks
// come from the declaration; no domain word is written here. The walks are the page's own (its form, its world
// seat): this part asks and reads the answer by its picks, it does not filter beyond the type it collected.
// ═══════════════════════════════════════════════════════════════════════════════
import { predicatesTouching } from './derive.js';
import { qualifiersByNode, valueText, isNumericText } from './table_view.js';
import { seedsOf } from './subgraph_view.js';
import { setDisabledReason } from '../disabled_reason.js';
import { CHOOSE, FAILED, WALKING } from '../ui_words.js';
import { ABSENT } from '../absent.js';

export const COMPARE_WORDS = Object.freeze({
  type: 'Rows',
  edge: 'Edge',
  value: 'Value',
  go: 'Compare',
  missing: 'missing',
  noStarts: 'Walk with a start first',
  pickAll: 'Pick a type, an edge and a value',
  noValue: 'carries no value: pick another edge',
  idle: 'Nothing compared yet',
  noRows: 'No row: the walk reached no node of this type',
});

const declared = (declaration, name) => ((declaration || {}).predicates || []).find((p) => p.name === name) || null;

/** The three picks' choices, from the declaration alone: its types, the edges touching the type, the edge's values. */
export function compareChoices(declaration, picks = {}) {
  const decl = declaration || {};
  const types = (decl.entities || []).map((e) => e.type);
  const edges = picks.type ? predicatesTouching(decl.predicates, picks.type, decl.entities) : [];
  const q = ((declared(decl, picks.edge) || {}).object || {}).qualifiers || {};
  return { types, edges, values: [...(q.required || []), ...(q.optional || [])] };
}

/**
 * The walks one comparison asks - the page's form (its follow and knobs) from the start marking's ids:
 *   rows   every start (+ and −) as positive, collecting the row type
 *   signs  per sign that has a start, its starts as positive, the picked edge added to a chosen follow, collecting the
 *          row type and the edge's other ends (so whose value it is has its name)
 */
export function compareRequests(spec, starts, picks, declaration) {
  const { type, keys, collect, ...form } = spec || {};
  const edge = declared(declaration, picks.edge) || {};
  const ends = [...new Set([...(edge.subjects || []), ...((edge.object || {}).types || [])])]
    .filter((t) => t !== picks.type);
  const rows = { ...form, positive: [...starts.positive, ...starts.negative], collect: [picks.type] };
  const signs = [['+', starts.positive], ['−', starts.negative]]
    .filter(([, ids]) => ids.length)
    .map(([sign, ids]) => ({ sign, ids, spec: { ...form,
      ...(form.follow ? { follow: [...new Set([...form.follow, picks.edge])] } : {}),
      positive: [...ids], collect: [picks.type, ...ends] } }));
  return { rows, signs };
}

/**
 * The table from the answers. `columns[i]` is one sign's `{ sign, labels, answer }`; `followed` the form's follow.
 * A row's end of the edge is its object end, or its subject end when the type is only the edge's subject.
 */
export function compareView(rowsAnswer, columns, picks, declaration, followed = []) {
  const edge = declared(declaration, picks.edge) || {};
  const flip = !((edge.object || {}).types || []).includes(picks.type) && (edge.subjects || []).includes(picks.type);
  const rows = ((rowsAnswer && rowsAnswer.nodes) || []).filter((n) => n.type === picks.type);
  const read = columns.map(({ sign, labels, answer }) => {
    const edges = ((answer && answer.edges) || []).filter((e) => e.predicate === picks.edge)
      .map((e) => (flip ? { ...e, source: e.target, target: e.source } : e));
    return { sign, labels, reached: new Set(edges.map((e) => e.target)),
      byNode: qualifiersByNode(edges, (answer && answer.nodes) || []) };
  });
  return {
    heading: `${COMPARE_WORDS.type}: ${picks.type} reached by ${followed.length ? followed.join(' · ') : 'every predicate'}`
      + (followed.includes(picks.edge) ? ` · rows include ${picks.edge}` : ''),
    columns: read.map((c) => `${c.sign} ${c.labels.join(' · ')}`),
    // Said under a sign only when one of its cells is missing.
    missing: read.filter((c) => rows.some((n) => !c.reached.has(n.id)))
      .map((c) => `${c.sign} ${COMPARE_WORDS.missing}: no ${picks.edge} edge from what ${c.sign} reached`),
    rows: rows.map((n) => ({
      id: n.id,
      label: n.label || n.id,
      cells: read.map((c) => {
        if (!c.reached.has(n.id)) return { text: COMPARE_WORDS.missing, missing: true };
        // The edge is there and does not say the value: absent, not missing.
        const text = valueText((c.byNode.get(n.id) || {})[picks.value]) || ABSENT;
        return { text, missing: false, numeric: isNumericText(text) };
      }),
    })),
  };
}

/** One comparison: its own div, its own picks and answers; the walk, the markings and the form are the page's. */
export class CompareView {
  /**
   * @param {HTMLElement} mount
   * @param {{doc?: Document, walk: Function, markings: object, startsName: string, spec: Function,
   *          declaration: Function, labelOf?: Function}} deps
   */
  constructor(mount, deps = {}) {
    this.doc = deps.doc || (mount && mount.ownerDocument);
    this.walk = deps.walk;
    this.markings = deps.markings;
    this.startsName = deps.startsName;
    this.spec = deps.spec || (() => ({}));
    this.declaration = deps.declaration || (() => null);
    this.labelOf = deps.labelOf || ((id) => id);
    this.picks = { type: '', edge: '', value: '' };
    this.state = 'idle';
    this.view = null;
    this.reason = '';
    this.asks = 0;
    this.root = this.doc.createElement('div');
    this.root.className = 'cmp-view';
    mount.appendChild(this.root);
    this.render();
  }

  _el(tag, cls, text) {
    const n = this.doc.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  /** What stops a comparison now, or '' - the button says it. */
  _blocked() {
    if (this.picks.edge && !compareChoices(this.declaration(), this.picks).values.length) {
      return `${this.picks.edge} ${COMPARE_WORDS.noValue}`;
    }
    if (!this.picks.type || !this.picks.edge || !this.picks.value) return COMPARE_WORDS.pickAll;
    const starts = seedsOf(this.markings.entries(this.startsName));
    return starts.positive.length + starts.negative.length ? '' : COMPARE_WORDS.noStarts;
  }

  /** The answers no longer stand (a world picked elsewhere): drawn as not compared until asked again. */
  forget() {
    this.asks += 1;
    this.state = 'idle';
    this.view = null;
    this.render();
  }

  async ask() {
    if (this._blocked()) { this.render(); return; }
    const asked = ++this.asks;
    const spec = this.spec();
    const decl = this.declaration();
    const starts = seedsOf(this.markings.entries(this.startsName));
    const req = compareRequests(spec, starts, this.picks, decl);
    this.state = 'running';
    this.render();
    const [rows, ...signs] = await Promise.all([this.walk(req.rows), ...req.signs.map((s) => this.walk(s.spec))]);
    if (asked !== this.asks) return;
    const refused = [rows, ...signs].find((r) => !r || !r.ok);
    if (refused) {
      this.state = 'failed';
      this.reason = (refused && refused.message) || FAILED;
    } else {
      this.state = 'done';
      this.view = compareView(rows,
        req.signs.map((s, i) => ({ sign: s.sign, labels: s.ids.map((id) => this.labelOf(id)), answer: signs[i] })),
        this.picks, decl, (spec && spec.follow) || []);
    }
    this.render();
  }

  _pick(label, key, options) {
    const box = this._el('label', 'cmp-pick');
    box.appendChild(this._el('span', 'wk-label', label));
    const select = this._el('select', 'wk-select cmp-select');
    select.setAttribute('data-pick', key);
    for (const value of ['', ...options]) {
      const o = this._el('option', '', value || CHOOSE);
      o.value = value;
      select.appendChild(o);
    }
    select.value = this.picks[key];
    select.addEventListener('change', () => {
      this.picks[key] = select.value;
      // A pick drops what depends on it: the type the edge, the edge the value.
      if (key === 'type') { this.picks.edge = ''; this.picks.value = ''; }
      if (key === 'edge') this.picks.value = '';
      this.view = null;
      this.state = 'idle';
      this.render();
    });
    box.appendChild(select);
    return box;
  }

  render() {
    this.root.textContent = '';
    const choices = compareChoices(this.declaration(), this.picks);
    const bar = this._el('div', 'cmp-picks');
    bar.appendChild(this._pick(COMPARE_WORDS.type, 'type', choices.types));
    bar.appendChild(this._pick(COMPARE_WORDS.edge, 'edge', choices.edges));
    bar.appendChild(this._pick(COMPARE_WORDS.value, 'value', choices.values));
    const go = this._el('button', 'wk-go cmp-go', this.state === 'running' ? WALKING : COMPARE_WORDS.go);
    go.type = 'button';
    setDisabledReason(go, this.state === 'running' ? WALKING : this._blocked());
    go.addEventListener('click', () => { void this.ask(); });
    bar.appendChild(go);
    this.root.appendChild(bar);

    if (this.state === 'failed') {
      const line = this._el('div', 'wk-fail');
      line.append(this._el('b', '', FAILED), this._el('span', '', ` · ${this.reason}`));
      this.root.appendChild(line);
      return;
    }
    if (this.state !== 'done' || !this.view) {
      this.root.appendChild(this._el('div', 'wk-note', this.state === 'running' ? WALKING : COMPARE_WORDS.idle));
      return;
    }
    const v = this.view;
    this.root.appendChild(this._el('div', 'cmp-heading', v.heading));
    if (!v.rows.length) {
      this.root.appendChild(this._el('div', 'wk-note', COMPARE_WORDS.noRows));
      return;
    }
    const table = this._el('table', 'wk-table cmp-table');
    const head = this._el('tr');
    head.appendChild(this._el('th', '', this.picks.type));
    for (const column of v.columns) head.appendChild(this._el('th', '', column));
    const thead = this._el('thead');
    thead.appendChild(head);
    table.appendChild(thead);
    const body = this._el('tbody');
    for (const row of v.rows) {
      const tr = this._el('tr');
      tr.setAttribute('data-row', row.id);
      tr.appendChild(this._el('td', 'cmp-label', row.label));
      for (const cell of row.cells) {
        tr.appendChild(this._el('td', cell.missing ? 'cmp-missing' : (cell.numeric ? 'wk-num' : 'cmp-many'), cell.text));
      }
      body.appendChild(tr);
    }
    table.appendChild(body);
    this.root.appendChild(table);
    for (const line of v.missing) this.root.appendChild(this._el('div', 'wk-note cmp-missing-says', line));
  }
}
