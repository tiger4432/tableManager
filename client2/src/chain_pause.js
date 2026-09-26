// CHAIN PAUSE — the emergency stop's control (leads 3840af307 · 668fa004c). One part, two
// instances: the Overview's Queue section and the top of the Chain tab, drawn from one read.
//
// 🔴 TWO ANSWERS, TWO OWNERS. `GET /admin/chain/pause` is the REQUESTED state (the control
//    file); `/health`'s chain worker status says whether the worker has TAKEN it (its beat).
//    When they differ the line says both — a pause the worker has not taken is not a stopped chain.

export const PAUSE_ROUTE = '/admin/chain/pause';
export const RESUME_ROUTE = '/admin/chain/resume';

export const PAUSE_WORDS = Object.freeze({
  pause: 'Pause chain', resume: 'Resume chain', confirm: 'Pause now', cancel: 'Cancel',
  reason: 'Reason (optional)',
  confirmLine: 'Pause the chain? It takes no new work until Resume. Nothing queued is lost.',
  pausing: 'Pausing…', resuming: 'Resuming…',
});

/**
 * @param {{read: true, paused: {by?, at?, reason?}|null}|{read: false, reason?: string}|null} requested
 * @param {{status?: string, detail?: string}|null} worker  `/health` checks.workers.chain, or null unread
 * @returns {{state: 'running'|'paused'|'unknown', tone: string, action: 'pause'|'resume',
 *            line: string, worker: {text: string, title: string}|null}}
 */
export function chainPauseView(requested, worker) {
  const req = requested || { read: false };
  const word = worker && worker.status ? String(worker.status) : null;
  const title = worker && typeof worker.detail === 'string' ? worker.detail : '';
  const said = (text) => ({ text, title });
  if (!req.read) {
    // Pausing is safe whatever the state is, so an unreadable state still offers it.
    return { state: 'unknown', tone: '', action: 'pause',
      line: `Pause state unreadable${req.reason ? ` — ${req.reason}` : ''}`,
      worker: word ? said(`Worker: ${word}`) : null };
  }
  const p = req.paused;
  if (p && typeof p === 'object') {
    // `at` is the server's local time with no zone — shown as given, and said to be the server's.
    const at = p.at ? ` at ${String(p.at).replace('T', ' ')} (server time)` : '';
    return { state: 'paused', tone: 'warn', action: 'resume',
      line: `Paused by ${p.by || 'unknown'}${at}${p.reason ? ` · ${p.reason}` : ''}`,
      worker: word && word !== 'paused' ? said(`Worker: ${word} · not paused yet`) : null };
  }
  return { state: 'running', tone: 'ok', action: 'pause', line: 'Running',
    worker: word === 'paused' ? said('Worker: paused · takes the queue on its next tick') : null };
}

/** The request a button sends — the route is chosen here, beside the view that chose the action. */
export function pauseRequest(action, reason) {
  return action === 'resume'
    ? { path: RESUME_ROUTE, body: {} }
    : { path: PAUSE_ROUTE, body: { reason: String(reason || '').trim() } };
}

export class ChainPauseControl {
  /** @param {HTMLElement} mount  @param {{doc?: Document, send: (req) => Promise<{ok: boolean, error?: string}>}} deps */
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('ChainPauseControl needs a mount element');
    this.doc = deps.doc || mount.ownerDocument;
    this.send = deps.send || (async () => ({ ok: false, error: 'No route wired' }));
    this.root = this.doc.createElement('div');
    this.root.className = 'chain-pause';
    this.status = this._el('div', 'chain-pause-line');
    this.workerLine = this._el('div', 'chain-pause-worker');
    this.controls = this._el('div', 'chain-pause-controls');
    this.said = this._el('div', 'chain-pause-said');
    mount.appendChild(this.root);
    // What this instance is in the middle of — kept across the page's re-reads.
    this.confirming = false;
    this.busy = '';
    this.reason = '';
    this.drawn = null;
    this.view = null;
  }

  _el(tag, cls) {
    const el = this.doc.createElement(tag);
    el.className = cls;
    this.root.appendChild(el);
    return el;
  }

  _button(cls, text, onClick) {
    const b = this.doc.createElement('button');
    b.type = 'button';
    b.className = `admin-btn ${cls}`;
    b.textContent = text;
    if (this.busy) b.disabled = true;
    b.addEventListener('click', onClick);
    this.controls.appendChild(b);
    return b;
  }

  render(view) {
    // Someone else paused or resumed: a question asked of the old state is not asked of the new one.
    if (this.view && this.view.action !== view.action) this.confirming = false;
    this.view = view;
    this.root.setAttribute('data-tone', view.tone || '');
    this.status.textContent = view.line;
    this.workerLine.textContent = view.worker ? view.worker.text : '';
    this.workerLine.setAttribute('title', view.worker ? view.worker.title : '');
    // A re-read that changes nothing here leaves the controls — and a reason being typed — alone.
    const key = `${view.action}|${this.confirming}|${this.busy}`;
    if (key !== this.drawn) this._drawControls(key);
    return view;
  }

  _drawControls(key) {
    this.drawn = key;
    this.controls.textContent = '';
    const action = this.view.action;
    if (this.busy) {
      this._button('btn-primary', this.busy === 'resume' ? PAUSE_WORDS.resuming : PAUSE_WORDS.pausing, () => {});
      return;
    }
    if (action === 'resume') {
      this._button('btn-primary chain-pause-resume', PAUSE_WORDS.resume, () => this._fire('resume'));
      return;
    }
    const input = this.doc.createElement('input');
    input.className = 'glass-input chain-pause-reason';
    input.placeholder = PAUSE_WORDS.reason;
    input.setAttribute('aria-label', PAUSE_WORDS.reason);
    input.value = this.reason;
    input.addEventListener('input', () => { this.reason = input.value; });
    this.controls.appendChild(input);
    if (!this.confirming) {
      this._button('btn-danger chain-pause-go', PAUSE_WORDS.pause, () => this._confirm(true));
      return;
    }
    const ask = this.doc.createElement('span');
    ask.className = 'chain-pause-ask';
    ask.textContent = PAUSE_WORDS.confirmLine;
    this.controls.appendChild(ask);
    this._button('btn-danger chain-pause-confirm', PAUSE_WORDS.confirm, () => this._fire('pause'));
    this._button('chain-pause-cancel', PAUSE_WORDS.cancel, () => this._confirm(false));
  }

  _confirm(on) {
    this.confirming = on;
    this.said.textContent = '';
    this.render(this.view);
  }

  async _fire(action) {
    if (this.busy) return;
    this.busy = action;
    this.said.textContent = '';
    this.render(this.view);
    let answer;
    try {
      answer = await this.send(pauseRequest(action, this.reason));
    } catch (e) {
      answer = { ok: false, error: (e && e.message) || 'Request failed' };
    }
    this.busy = '';
    if (answer && answer.ok) {
      this.confirming = false;
      this.reason = '';
    } else {
      // The refusal stays on this instance's line; a toast would be gone before it is read.
      this.said.textContent = (answer && answer.error) || 'Request failed';
    }
    this.render(this.view);
  }
}
