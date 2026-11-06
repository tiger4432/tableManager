// The admin help (owner 10-29 «ㄴ»): the header's Help opens a side panel on any admin tab - a question in the
// operator's words, the server's ONE tool for it with its fields filled and that tool's own count, and the asks of this
// page until it reloads (no route reads the server's `admin_help_asks`). It runs nothing: Open form hands the tool's
// form the fields and the ask's `help_id`, and the operator runs it there.
//
// Cancel stops the waiting, not the ask - the server finishes it, writes its row and counts; the answer that comes
// after goes to Earlier marked «arrived after you stopped» (owner 10-29 «2 캔슬 넣어», lead).
//
// NO NETWORK, NO DOM GLOBALS: `send`, `doc` and the page's doors come in (admin.js hands adminFetch's; the harness fakes).
import { setDisabledReason } from './disabled_reason.js';
import { buildCountView } from './retroactive_view.js';
import { GuideReader, GUIDES_ROUTE } from './guide_reader.js';
import { localClock } from './server_time.js';

export const HELP_ROUTE = '/admin/help/ask';
// Ask's reasons for being off, and the lines that stand where an answer would
export const WRITE_FIRST = 'Write what you want to do';
export const ASKING = 'Asking - waiting for the model';
export const STOPPED_WAITING = 'Stopped waiting - the server still finishes this ask';
export const ARRIVED_LATE = 'arrived after you stopped';
export const UNTIL_RELOAD = 'until reload';
export const NOTHING_ASKED = 'Nothing asked since this page opened';
// the save's judgement passed - and nothing was saved (lead 10-29: said in the word)
export const CHECKED = 'Checked - would save';

/** The panel's width dragged on its left edge, kept per browser (owner 11-06) - none kept: the page's token. */
export const WIDTH_KEY = 'admin-help-width';
export const MIN_WIDTH = 360;
/** A dragged width as the panel takes it: whole pixels, at least MIN_WIDTH, at most the window. */
export const panelWidth = (px, viewport) => Math.round(Math.max(MIN_WIDTH, Math.min(px, viewport)));

/** The one request: the question as typed. */
export function helpRequest(question) {
  return { method: 'POST', path: HELP_ROUTE, body: { question } };
}

const shown = (v) => (Array.isArray(v) ? v.join(', ') : v === null || v === undefined ? '' : String(v));

/** The save's judgement of an example declaration (B 813eac94a): passed - not saved · refused · not checked. */
function checkOf(c) {
  if (!c || typeof c !== 'object') return null;
  if ('not_checked' in c) return { state: 'not', said: shown(c.not_checked) };
  if (c.ok === true) return { state: 'ok', said: shown(c.said) };
  if (c.ok === false) return { state: 'refused', said: shown(c.said) };
  return null;
}

/** The help's answer on how to write a declaration: the example as text, the guide sections it rests on, its check. */
function declarationOf(d) {
  if (!d || typeof d !== 'object') return null;
  const body = d.declaration;
  return {
    text: body === undefined || body === null ? '' : typeof body === 'string' ? body : JSON.stringify(body, null, 2),
    why: shown(d.why),
    sections: (Array.isArray(d.sections) ? d.sections : []).map(shown).filter(Boolean),
    dropped: Number(d.dropped_sections) > 0 ? Number(d.dropped_sections) : 0,
    check: checkOf(d.check),
    refused: shown(d.refused),
    retrieval: shown(d.retrieval),
  };
}

/** What an answer draws. `forms` - {op: label} of the tools whose form this page has (the Retroactive list).
 *  kind: `tool` (a tool and its fields) · `unsure` (none fitted; the tools near) · `refused` (the model was not asked). */
export function answerView(answer, forms = {}) {
  const a = answer || {};
  const base = { helpId: a.help_id || null, why: a.why ? String(a.why) : '' };
  if (!a.op) {
    // no ask reached the model (its refusal by name) - a «not sure» was asked and named none
    if (!a.tries) return { ...base, kind: 'refused', title: 'Not asked', refused: a.refused ? String(a.refused) : '' };
    const near = (Array.isArray(a.similar) ? a.similar : []).filter((s) => s && s.op)
      .map((s) => ({ op: s.op, label: s.label || forms[s.op] || s.op, form: s.op in forms }));
    // why the last try was refused, as the server says it (lead 10-29: «every answer is not sure» is read off this line)
    return { ...base, kind: 'unsure', title: 'Not sure', tries: a.tries, near, refused: a.refused ? String(a.refused) : '' };
  }
  const params = a.params && typeof a.params === 'object' ? a.params : {};
  const count = a.count ? buildCountView(a.count) : null;
  const declaration = declarationOf(a.declaration);
  return {
    // a declaration's own why takes the why's seat (lead 10-29: every card draws it in the same place)
    ...base, why: (declaration && declaration.why) || base.why, declaration, kind: 'tool', op: a.op, title: a.label || forms[a.op] || a.op, form: a.op in forms, params,
    fields: Object.keys(params).map((name) => ({ name, value: shown(params[name]) })),
    // the required fields the question left blank, the server's words - the form opens with them blank (B 7c326a296)
    unfilled: (Array.isArray(a.unfilled) ? a.unfilled : []).map(shown).filter(Boolean),
    // the form's own reading of a count (buildCountView): a number only with the server's word for it
    count: count && count.affectedLabel && count.affected ? { value: count.affected.text, label: count.affectedLabel.text } : null,
    rawCount: a.count || null,
    countRefused: a.count_refused ? String(a.count_refused) : '',
    doors: (Array.isArray(a.doors) ? a.doors : []).map((d) => ({
      name: shown(d.name), how: shown(d.how),
      open: d.open && d.open.href ? { label: shown(d.open.label) || shown(d.open.href), href: String(d.open.href) } : null })),
  };
}

const CLOCK = { set: (fn, ms) => setTimeout(fn, ms), clear: (h) => clearTimeout(h), now: () => Date.now() };

/**
 * One panel. `host` is where its own div lives; `deps`:
 *   doc       the document
 *   send      async (request) -> {ok: true, body} | {ok: false, error}  - the refusal already a sentence
 *   forms     () -> {op: label}  - the tools whose form the page has, read when an answer is drawn
 *   openForm  ({op, params, helpId, question, count}) - the page opens that tool's form filled
 *   clock     {set, clear, now}
 *   copy      (text) -> true when it reached the clipboard - an example declaration (the page's clipboard_write)
 *   tab       () -> the admin tab shown - the Guide's «For this tab»
 * Ask | Guide: Guide is the guides read without asking (guide_reader.js, owner 11-06), read through `send` too.
 */
export class HelpPanel {
  constructor(host, deps = {}) {
    this.host = host;
    this.doc = deps.doc;
    this.send = deps.send;
    this.forms = deps.forms || (() => ({}));
    this.openForm = deps.openForm || (() => {});
    this.clock = deps.clock || CLOCK;
    this.copy = deps.copy || (() => false);
    this.tab = deps.tab || (() => null);
    this.storage = deps.storage || null;   // where a dragged width is kept; none - not kept
    this.view = 'ask';
    this.asks = [];           // newest first: {question, at, view, waiting, stopped, late, runId}
    this.shown = null;        // the ask whose card is drawn
    this.tick = null;
    this.seconds = null;     // the waiting card's seconds, counted in place
    this.root = null;
  }

  get isOpen() { return Boolean(this.root && !this.root.hidden); }

  open() {
    if (!this.root) this.build();
    this.root.hidden = false;
    if (this.view === 'guide') this.reader.show(this.tab());
    else if (this.input.focus) this.input.focus();
  }

  /** Opens on the Guide - `tab`'s guides, `file` when given (a declaration window's «?»). */
  openGuide(tab, file = null) {
    if (!this.root) this.build();
    this.root.hidden = false;
    this.setView('guide');
    this.reader.show(tab, file);
  }

  setView(view) {
    this.view = view;
    this.askBody.hidden = view !== 'ask';
    this.guideBody.hidden = view !== 'guide';
    this.tag.hidden = view !== 'ask';
    this.viewBtns.forEach((b) => b.setAttribute('aria-pressed', b.dataset.view === view ? 'true' : 'false'));
  }

  close() { if (this.root) this.root.hidden = true; }

  /** Sets the panel's width token on its host - Ask and Guide alike. */
  setWidth(px) {
    const width = panelWidth(px, this.doc.defaultView ? this.doc.defaultView.innerWidth : px);
    this.host.style.setProperty('--help-panel-width', `${width}px`);
    return width;
  }

  /** The left edge dragged: the width follows the pointer, kept when it is let go. */
  drag(e, grip) {
    if (e.preventDefault) e.preventDefault();
    const view = this.doc.defaultView;
    let width = null;
    const move = (ev) => { width = this.setWidth(view.innerWidth - ev.clientX); };
    const up = () => {
      grip.className = 'help-panel__grip';
      view.removeEventListener('pointermove', move);
      view.removeEventListener('pointerup', up);
      try { if (width && this.storage) this.storage.setItem(WIDTH_KEY, String(width)); } catch (err) { /* not kept */ }
    };
    grip.className = 'help-panel__grip is-dragging';
    view.addEventListener('pointermove', move);
    view.addEventListener('pointerup', up);
  }

  toggle() { if (this.isOpen) this.close(); else this.open(); }

  el(tag, cls, text) {
    const e = this.doc.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  button(cls, text, onClick) {
    const b = this.el('button', `btn ${cls}`.trim(), text);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  build() {
    const root = this.el('aside', 'help-panel');
    root.setAttribute('aria-label', 'Help');
    const head = this.el('div', 'help-panel__head');
    head.appendChild(this.el('span', 'help-panel__title', 'Help'));
    const views = this.el('div', 'help-panel__views');
    views.setAttribute('role', 'group');
    views.setAttribute('aria-label', 'Help view');
    this.viewBtns = [['ask', 'Ask'], ['guide', 'Guide']].map(([view, text]) => {
      const b = this.button('help-panel__view', text, () => {
        this.setView(view);
        if (view === 'guide') this.reader.show(this.tab());
        else if (this.input.focus) this.input.focus();
      });
      b.dataset.view = view;
      views.appendChild(b);
      return b;
    });
    head.appendChild(views);
    this.tag = this.el('span', 'help-panel__tag', UNTIL_RELOAD);
    head.appendChild(this.tag);
    const close = this.button('btn-quiet ctl-small help-panel__close', '×', () => this.close());
    close.setAttribute('aria-label', 'Close help');
    head.appendChild(close);
    root.appendChild(head);
    const grip = this.el('div', 'help-panel__grip');
    grip.setAttribute('role', 'separator');
    grip.setAttribute('aria-orientation', 'vertical');
    grip.setAttribute('aria-label', 'Resize help');
    grip.addEventListener('pointerdown', (e) => this.drag(e, grip));
    root.appendChild(grip);
    let kept = null;
    try { kept = this.storage && Number(this.storage.getItem(WIDTH_KEY)); } catch (e) { kept = null; }
    if (kept > 0) this.setWidth(kept);

    const body = this.el('div', 'help-panel__body');
    const label = this.el('label', 'help-panel__label', 'Ask');
    this.input = this.el('textarea', 'help-panel__input');
    this.input.id = `help-q-${Math.random().toString(36).slice(2, 8)}`;
    label.setAttribute('for', this.input.id);
    this.input.addEventListener('input', () => this.drawAsk());
    this.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { if (e.preventDefault) e.preventDefault(); this.ask(); }
    });
    this.askBtn = this.button('btn-primary help-panel__ask', 'Ask', () => this.ask());
    body.appendChild(label);
    body.appendChild(this.input);
    const row = this.el('div', 'help-panel__row');
    row.appendChild(this.askBtn);
    body.appendChild(row);
    this.card = this.el('div', 'help-panel__card');
    body.appendChild(this.card);
    body.appendChild(this.el('div', 'help-panel__label', 'Earlier'));
    this.earlier = this.el('div', 'help-panel__earlier');
    body.appendChild(this.earlier);
    root.appendChild(body);
    this.askBody = body;
    this.guideBody = this.el('div', 'help-panel__body help-panel__guide');
    root.appendChild(this.guideBody);
    this.reader = new GuideReader(this.guideBody, { doc: this.doc, load: () => this.send({ method: 'GET', path: GUIDES_ROUTE }) });
    this.root = root;
    this.host.appendChild(root);
    this.setView(this.view);
    this.render();
  }

  get waiting() { return this.asks.find((r) => r.waiting) || null; }

  drawAsk() {
    const why = this.waiting ? ASKING : (this.input.value || '').trim() ? '' : WRITE_FIRST;
    setDisabledReason(this.askBtn, why);
  }

  async ask() {
    const question = (this.input.value || '').trim();
    if (!question || this.waiting) return;
    const rec = { question, at: this.clock.now(), view: null, waiting: true, stopped: false, late: false, runId: null };
    this.asks.unshift(rec);
    this.shown = rec;
    this.render();
    this.beat();
    const got = await this.send(helpRequest(question));
    rec.view = got && got.ok ? answerView(got.body, this.forms())
      : { kind: 'refused', title: 'Not asked', refused: (got && got.error) || '', helpId: null, why: '' };
    rec.late = rec.stopped;
    rec.waiting = false;
    if (this.tick) this.clock.clear(this.tick);
    this.tick = null;
    this.render();
  }

  /** Stops waiting for the ask out; the server still finishes it. */
  stopWaiting() {
    const rec = this.waiting;
    if (!rec) return;
    rec.waiting = false;
    rec.stopped = true;
    if (this.tick) this.clock.clear(this.tick);
    this.tick = null;
    this.render();
  }

  beat() {
    if (this.tick) this.clock.clear(this.tick);
    this.tick = this.clock.set(() => {
      this.tick = null;
      const rec = this.waiting;
      if (!rec) return;
      // the seconds only - the card is not drawn again under a hand on its Cancel
      if (this.seconds && rec === this.shown) this.seconds.textContent = this.secondsOf(rec);
      this.beat();
    }, 1000);
  }

  secondsOf(rec) { return `${Math.floor((this.clock.now() - rec.at) / 1000)} s`; }

  /** The run the form queued from `helpId`'s answer, said on its ask. */
  noteRun(helpId, runId) {
    const rec = this.asks.find((r) => r.view && r.view.helpId && r.view.helpId === helpId);
    if (!rec) return;
    rec.runId = runId;
    this.render();
  }

  render() {
    if (!this.root) return;
    this.drawAsk();
    this.card.textContent = '';
    if (this.shown) this.card.appendChild(this.cardOf(this.shown));
    this.card.hidden = !this.shown;
    this.earlier.textContent = '';
    const rest = this.asks.filter((r) => r !== this.shown);
    if (!rest.length) this.earlier.appendChild(this.el('div', 'help-panel__empty', NOTHING_ASKED));
    rest.forEach((rec) => this.earlier.appendChild(this.rowOf(rec)));
  }

  cardOf(rec) {
    const box = this.el('div', 'help-card');
    const head = this.el('div', 'help-card__head');
    box.appendChild(head);
    if (rec.waiting) {
      head.appendChild(this.el('span', 'help-card__title', 'Asking the model'));
      this.seconds = this.el('span', 'help-card__meta', this.secondsOf(rec));
      head.appendChild(this.seconds);
      const acts = this.el('div', 'help-card__acts');
      acts.appendChild(this.button('help-card__cancel', 'Cancel', () => this.stopWaiting()));
      box.appendChild(acts);
      return box;
    }
    if (!rec.view) {
      box.dataset.tone = 'warn';
      head.appendChild(this.el('span', 'help-card__title', STOPPED_WAITING));
      return box;
    }
    const v = rec.view;
    head.appendChild(this.el('span', 'help-card__title', v.title));
    if (v.op) head.appendChild(this.el('span', 'help-card__op', v.op));
    if (v.kind === 'unsure') head.appendChild(this.el('span', 'help-card__meta', `asked ${v.tries} times`));
    if (rec.late) head.appendChild(this.el('span', 'help-card__late', ARRIVED_LATE));
    if (v.why) box.appendChild(this.el('div', 'help-card__why', v.why));
    if (v.kind === 'refused') {
      box.dataset.tone = 'danger';
      box.appendChild(this.el('div', 'help-card__refused', v.refused));
      return box;
    }
    if (v.kind === 'unsure') {
      if (v.refused) box.appendChild(this.el('div', 'help-card__refused', v.refused));
      const list = this.el('div', 'help-card__near');
      // a tool whose form the page has is the row's press - its form opens empty; the others are named only
      v.near.forEach((n) => {
        const line = n.form
          ? this.button('btn-quiet help-card__near-row help-card__open', '',
            () => this.openForm({ op: n.op, params: {}, helpId: v.helpId, question: rec.question, count: null }))
          : this.el('div', 'help-card__near-row');
        line.appendChild(this.el('span', 'help-card__op', n.op));
        line.appendChild(this.el('span', 'help-card__near-label', n.label));
        if (n.form) line.appendChild(this.el('span', 'help-card__near-go', 'Open form'));
        list.appendChild(line);
      });
      box.appendChild(list);
      return box;
    }
    box.dataset.tone = 'answer';
    if (v.fields.length) {
      const kv = this.el('div', 'help-card__fields');
      v.fields.forEach((f) => {
        kv.appendChild(this.el('span', 'help-card__k', f.name));
        kv.appendChild(this.el('span', 'help-card__v', f.value));
      });
      box.appendChild(kv);
    }
    // « · » between items: an item can hold commas itself («one of: tables, rules, transactions»)
    if (v.unfilled.length) box.appendChild(this.el('div', 'help-card__needs', `needs: ${v.unfilled.join(' · ')}`));
    if (v.declaration) box.appendChild(this.declarationBox(v.declaration));
    if (v.count) {
      const line = this.el('div', 'help-card__count');
      line.appendChild(this.el('span', 'help-card__count-value', v.count.value));
      line.appendChild(this.el('span', 'help-card__count-label', v.count.label));
      box.appendChild(line);
    }
    if (v.countRefused) box.appendChild(this.el('div', 'help-card__count-refused', v.countRefused));
    if (v.doors.length) {
      // one grid for every door, so the names stand in one column
      const doors = this.el('div', 'help-card__doors');
      v.doors.forEach((d) => {
        doors.appendChild(this.el('span', 'help-card__k', d.name));
        doors.appendChild(this.el('span', 'help-card__door', d.how));
      });
      box.appendChild(doors);
    }
    const acts = this.el('div', 'help-card__acts');
    if (v.form) {
      acts.appendChild(this.button('btn-primary help-card__open', 'Open form', () => this.openForm({
        op: v.op, params: v.params, helpId: v.helpId, question: rec.question, count: v.rawCount })));
    }
    v.doors.filter((d) => d.open).forEach((d) => {
      const a = this.el('a', 'btn btn-primary help-card__page', d.open.label);
      a.setAttribute('href', d.open.href);
      acts.appendChild(a);
    });
    if (acts.children.length) box.appendChild(acts);
    return box;
  }

  /** The example to paste (its Copy beside it), the guide sections it rests on, and what the save would say of it. */
  declarationBox(d) {
    const box = this.el('div', 'help-card__decl');
    if (d.refused) box.appendChild(this.el('div', 'help-card__refused', d.refused));
    if (d.text) {
      const text = this.el('pre', 'help-card__decl-text', d.text);
      text.setAttribute('data-clip-ok', '');
      box.appendChild(text);
      const copy = this.button('btn-quiet help-card__copy', 'Copy', () => {
        Promise.resolve().then(() => this.copy(d.text))
          .then((ok) => { copy.textContent = ok === false ? 'Copy failed' : 'Copied'; }, () => { copy.textContent = 'Copy failed'; });
      });
      const acts = this.el('div', 'help-card__acts');
      acts.appendChild(copy);
      box.appendChild(acts);
    }
    if (d.sections.length) {
      const list = this.el('div', 'help-card__sections');
      d.sections.forEach((s) => list.appendChild(this.el('div', 'help-card__section', s)));
      box.appendChild(list);
    }
    // how the sections were picked - the server's word; a failed embedding's sentence rides in it
    if (d.retrieval) box.appendChild(this.el('div', 'help-card__meta help-card__retrieval', `via ${d.retrieval}`));
    if (d.dropped) {
      box.appendChild(this.el('div', 'help-card__dropped',
        `${d.dropped} section name${d.dropped === 1 ? '' : 's'} the model made up ${d.dropped === 1 ? 'was' : 'were'} dropped`));
    }
    // a refused second call carries the same sentence as its not_checked - said once, as the refusal
    const c = d.refused ? null : d.check;
    if (c && c.state === 'ok') {
      box.appendChild(this.el('div', 'help-card__check-ok', CHECKED));
      if (c.said) box.appendChild(this.el('div', 'help-card__check-note', c.said));
    }
    if (c && c.state === 'refused') box.appendChild(this.el('div', 'help-card__refused', c.said));
    if (c && c.state === 'not') box.appendChild(this.el('div', 'help-card__check-not', `Not checked: ${c.said}`));
    return box;
  }

  rowOf(rec) {
    const row = this.button('btn-quiet help-row', '', () => { this.shown = rec; this.render(); });
    // two lines, each a long word that gives way and a short one at the right edge; a third, the refusal's first line
    const line = () => row.appendChild(this.el('span', 'help-row__line'));
    const top = line();
    top.appendChild(this.el('span', 'help-row__q', rec.question));
    top.appendChild(this.el('span', 'help-row__at', localClock(new Date(rec.at).toISOString())));
    const under = line();
    const what = rec.waiting ? 'Asking' : !rec.view ? 'waiting' : rec.view.title;
    under.appendChild(this.el('span', 'help-row__what', what));
    const tail = rec.late ? ARRIVED_LATE : rec.runId ? `run ${rec.runId}` : '';
    under.appendChild(this.el('span', 'help-row__tail', tail));
    const said = rec.view && rec.view.refused ? rec.view.refused.split('\n')[0] : '';
    if (said) line().appendChild(this.el('span', 'help-row__refused', said));
    return row;
  }
}
