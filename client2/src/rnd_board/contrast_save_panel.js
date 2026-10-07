// ═══════════════════════════════════════════════════════════════════════════════
// SAVE CONTRAST (lead 3a262cc76, owner 09-30 「일단 대조 저장 쪽만 만들어서 푸시해 확인해볼게」).
//
// The marked defect-versus-good question becomes ONE row of the contrast run table, and the chain
// computes the answer from that row. This part saves the QUESTION and lists what was saved — it
// walks nothing: the numbers in the list are the tables' own (see CONTRAST in api.js).
//   defect (positive) = the marking's cases · good (negative) = its controls, as `startFor` splits
//   them · the walk arguments = the question this seat carries · as_of = now
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel } from './panel.js';
import { CONTRAST, createContrastStore, newContrastRunId } from './api.js';
import { setDisabledReason } from '../disabled_reason.js';
import { localShort, localHourMinute } from '../server_time.js';

export const CONTRAST_WORDS = Object.freeze({
  save: 'Save contrast',
  refresh: 'Refresh',
  needDefects: 'Mark defect wafers first',
  saving: 'Saving',
  noControls: 'No controls — saved as unexamined',
  nothingMarked: 'Nothing marked — default',
  empty: 'No saved contrasts',
  // The box declares no run table (lead 10-08): said as a fact, not as a failure.
  notSetUp: `Not set up — table ${CONTRAST.runTable} is not declared`,
  notComputed: 'Not computed yet',
  unexamined: 'unexamined',
  incomplete: 'incomplete',
});

export class ContrastSavePanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    this.store = options.contrastStore
      || createContrastStore({ apiBase: options.apiBase, fetchImpl: options.fetchImpl, user: options.user,
        world: options.world });
    // The candidate question, whole, as the seat hands it. Only walk arguments reach the row.
    this.question = options.candidateQuestion || {};
    this.now = options.now || (() => Date.now());
    this.newId = options.newId || newContrastRunId;
    this.busy = false;
    this.refusal = '';
    this.runs = null;        // null = not read yet
    this.listRefusal = '';
    this.listNotSetUp = false;
  }

  mount() {
    super.mount();
    this.loadList();
  }

  /** The question's start, split as every walk start is: cases are defects, controls are good. */
  seeds() {
    return this.startFor(this.question.start || { marking: this.reads }) || null;
  }

  async loadList() {
    const got = await this.store.list(10);
    this.runs = got && got.ok ? got.runs : this.runs;
    this.listNotSetUp = Boolean(got && got.notSetUp);
    this.listRefusal = (got && got.ok) || this.listNotSetUp ? '' : ((got && got.message) || '');
    this.render();
  }

  async save() {
    const seeds = this.seeds();
    if (!seeds || this.busy) return;
    const nowMs = this.now();
    this.busy = true;
    this.refusal = '';
    this.render();
    const got = await this.store.save({
      runId: this.newId(nowMs),
      positive: seeds.positive,
      negative: seeds.negative || [],
      asOf: new Date(nowMs).toISOString(),
      question: this.question,
    });
    this.busy = false;
    this.refusal = got && got.ok ? '' : ((got && got.message) || '');
    this.render();
    if (got && got.ok) this.loadList();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    const el = (tag, cls, text) => {
      const n = doc.createElement(tag);
      if (cls) n.className = cls;
      if (text !== undefined) n.textContent = text;
      return n;
    };
    this.host.textContent = '';
    const root = el('div', 'rb-contrast');
    if (this.title) root.appendChild(el('div', 'rb-part-title', this.title));

    const seeds = this.seeds();
    const controls = el('div', 'rb-contrast-controls');
    const save = el('button', 'rb-contrast-save', CONTRAST_WORDS.save);
    save.setAttribute('type', 'button');
    setDisabledReason(save, this.busy ? CONTRAST_WORDS.saving : (seeds ? '' : CONTRAST_WORDS.needDefects));
    const refresh = el('button', 'rb-contrast-refresh', CONTRAST_WORDS.refresh);
    refresh.setAttribute('type', 'button');
    if (save.addEventListener) {
      save.addEventListener('click', () => this.save());
      refresh.addEventListener('click', () => this.loadList());
    }
    controls.append(save, refresh);
    root.appendChild(controls);
    if (seeds && seeds.fallback) {
      const said = (this.question.start.otherwise || {}).label || seeds.value;
      root.appendChild(el('div', 'rb-cand-line rb-cand-line--absent', `${CONTRAST_WORDS.nothingMarked} ${said}`));
    }
    // A save with no controls is still a save — the fact is said beside the button, before it is pressed.
    if (seeds && !(seeds.negative || []).length) {
      root.appendChild(el('div', 'rb-cand-line rb-cand-line--absent', CONTRAST_WORDS.noControls));
    }
    if (this.refusal) root.appendChild(el('div', 'rb-cand-line rb-cand-line--refused', this.refusal));

    const list = el('div', 'rb-contrast-list');
    if (this.listNotSetUp) list.appendChild(el('div', 'rb-cand-line rb-cand-line--absent', CONTRAST_WORDS.notSetUp));
    else if (this.listRefusal) list.appendChild(el('div', 'rb-cand-line rb-cand-line--refused', this.listRefusal));
    else if (Array.isArray(this.runs) && !this.runs.length) {
      list.appendChild(el('div', 'rb-cand-line rb-cand-line--absent', CONTRAST_WORDS.empty));
    }
    for (const run of this.runs || []) list.appendChild(this._row(run, el));
    root.appendChild(list);
    this.host.appendChild(root);
  }

  _row(run, el) {
    const row = el('div', 'rb-contrast-row');
    row.setAttribute('data-run', run.runId);
    const count = (n) => (n === null || n === undefined ? '—' : String(n));
    const computed = run.computedAt
      ? `factors ${count(run.factors)} · computed ${localHourMinute(run.computedAt)}` : CONTRAST_WORDS.notComputed;
    row.append(
      el('span', 'rb-contrast-when', run.asOf ? localShort(run.asOf) : '—'),
      el('span', 'rb-contrast-counts',
        `defects ${count(run.positive)} · controls ${count(run.negative)} · ${computed}`),
    );
    if (run.unexamined) row.appendChild(el('span', 'rb-cand-stat rb-cand-stat--absent', CONTRAST_WORDS.unexamined));
    if (run.incomplete) row.appendChild(el('span', 'rb-cand-stat rb-cand-stat--absent', CONTRAST_WORDS.incomplete));
    return row;
  }
}
