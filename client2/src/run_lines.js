// ═══════════════════════════════════════════════════════════════════════════════
// RUN LINES — one run is one line: title | progress | elapsed | state | ×, and what it
// did on a full-width line under it (lead a274c90f0).
//
// 🔴 THE GRID DECLARES FIVE CELLS AND THE LINE ALWAYS HAS FIVE. The list it replaces was a
//    three-column grid whose finished rows had four children, so the result sentence fell into
//    the 32px elapsed cell and broke after every word (a 203px-tall row on a 2619px window).
//    Which cell a thing sits in is this file's; a line never grows a sixth.
// 🔴 A FINISHED RUN SAYS SO IN A WORD, NOT A FADE. Opacity 0.35 made it unreadable — readability
//    is a feature. The word is the server's (`state_names`); the colour is the muted text token.
// 🔴 ONE PART, TWO PLACES (lead 78ebdcfc0): the Overview's recent runs now, the top queue's
//    RUNNING next. Each is an instance on its own mount; the page decides where they sit.
// ═══════════════════════════════════════════════════════════════════════════════

const textOf = (node) => (node && typeof node.text === 'string' ? node.text : '');

/** A `buildRunsView` row -> what one line draws. Pure. */
export function runLineView(row) {
  const r = row || {};
  const progress = r.progress || {};
  const bar = progress.mode === 'bar';
  return {
    id: String(r.id || ''),
    title: [textOf(r.what), textOf(r.detail)].filter(Boolean).join(' · '),
    who: textOf(r.who),
    bar: bar ? 'known' : 'unknown',
    percent: bar ? Number(progress.percent) || 0 : null,
    number: bar ? `${Number(progress.percent) || 0}%` : String(progress.text || ''),
    elapsed: String(progress.elapsed || ''),
    state: textOf(r.stateName),
    finished: Boolean(r.finished),
    waiting: !r.finished && !r.moving,
    stopping: Boolean(r.stopping),
    // × only where a cancel can reach, and never twice: a stopping run has already been asked.
    cancel: Boolean(r.cancel) && !r.stopping,
    summary: textOf(r.summary),
    reason: textOf(r.reason),
    extras: Array.isArray(r.extras) ? r.extras : [],
  };
}

export class RunLines {
  /**
   * @param {HTMLElement} mount
   * @param {{doc?: Document, onCancel?: (id: string) => void,
   *          resultBoxes?: (extras: Array) => HTMLElement[]}} [deps]
   */
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('RunLines needs a mount element');
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    if (!this.doc) throw new Error('RunLines needs a document (deps.doc or mount.ownerDocument)');
    this.onCancel = deps.onCancel || (() => {});
    this.resultBoxes = deps.resultBoxes || (() => []);
    this.root = this.doc.createElement('div');
    this.root.className = 'run-lines';
    this.mount.appendChild(this.root);
  }

  _el(tag, cls, text) {
    const el = this.doc.createElement(tag);
    el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  _line(row) {
    const v = runLineView(row);
    const line = this._el('div', 'run-line'
      + (v.finished ? ' is-finished' : v.stopping ? ' is-stopping' : v.waiting ? ' is-waiting' : ''));
    line.setAttribute('data-run-id', v.id);

    const what = this._el('span', 'run-line__what', v.title);
    what.title = v.title;
    if (v.who) what.appendChild(this._el('span', 'run-line__who', v.who));
    line.appendChild(what);

    const progress = this._el('span', 'run-line__progress');
    const bar = this._el('span', 'running-bar' + (v.bar === 'unknown' ? ' is-unknown' : '')
      + (v.waiting || v.finished || v.stopping ? ' is-waiting' : ''));
    const fill = this._el('span', 'running-bar__fill');
    if (v.percent !== null) fill.style.width = `${v.percent}%`;
    bar.appendChild(fill);
    progress.appendChild(bar);
    progress.appendChild(this._el('span', 'run-line__number', v.number));
    line.appendChild(progress);

    line.appendChild(this._el('span', 'run-line__elapsed', v.elapsed));
    line.appendChild(this._el('span', 'run-line__state', v.state));

    const act = this._el('span', 'run-line__act');
    if (v.cancel) {
      const x = this._el('button', 'admin-btn running-x', '×');
      x.title = 'stop this one — the server keeps running';
      x.addEventListener('click', () => this.onCancel(v.id));
      act.appendChild(x);
    }
    line.appendChild(act);

    // What it did — the server's words, on its own full-width line. A failure reason sits here too.
    const boxes = this.resultBoxes(v.extras) || [];
    if (boxes.length || v.summary || v.reason) {
      const result = this._el('div', 'run-line__result');
      boxes.forEach((box) => result.appendChild(box));
      if (v.summary) result.appendChild(this._el('span', 'run-line__summary', v.summary));
      if (v.reason) result.appendChild(this._el('span', 'run-line__reason', v.reason));
      line.appendChild(result);
    }
    return line;
  }

  /** @param {Array} rows `buildRunsView(...).rows` */
  render(rows) {
    this.root.textContent = '';
    for (const row of Array.isArray(rows) ? rows : []) this.root.appendChild(this._line(row));
  }
}
