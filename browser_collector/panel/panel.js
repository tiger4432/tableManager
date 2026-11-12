// The collector's side panel: templates, editing one by picking on the page, a preview, a run, its end, history, settings.
// The panel asks the service worker (background.js) for everything; the page tells it what was picked and how a run goes.
import { matches, patternOf } from '../lib/address.js';
import { ENDED } from '../lib/run.js';
import { missOf } from '../lib/declared.js';

const ask = (msg) => chrome.runtime.sendMessage(msg).then((a) => { if (!a || !a.ok) throw new Error(a ? a.error : 'no answer'); return a.value; });

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className = v;
    else if (k === 'value') el.value = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid.nodeType ? kid : String(kid));
  return el;
}
const stat = (v, k, tone = '') => h('div', { class: 'stat' }, h('span', { class: `v ${tone}` }, v), h('span', { class: 'k' }, k));
const blank = () => ({ name: '', address: '', frame: '', listArea: '', item: '', clickTarget: '', opens: 'in_place', content: '', waitSeconds: 10, close: '',
  next: { how: 'button', selector: '' }, endSeconds: 5, max: 0, pair: null, pairText: '', keys: [], table: '', fields: [] });
const copy = (t) => JSON.parse(JSON.stringify(t));
const REASONS = [['no_key', 'No key'], ['not_opened', 'Did not open'], ['refused', 'Refused']];
const missCount = (tally, r) => tally.misses.filter((m) => m.reason === r).length;

class Panel {
  constructor(mount) {
    this.mount = mount;
    this.view = 'list';
    this.templates = [];
    this.me = null;
    this.tab = null;
    this.draft = null;
    this.picking = null;
    this.preview = null;
    this.run = null;
    this.history = null;
    this.problem = null;
    this.filter = 'all';
    chrome.runtime.onMessage.addListener((m) => { this.heard(m); return false; });
    // picking keys pressed while the panel has the focus go to the page
    document.addEventListener('keydown', (e) => {
      if (!this.picking || !this.tab || !['ArrowUp', 'ArrowDown', 'Enter', 'Escape'].includes(e.key)) return;
      e.preventDefault();
      ask({ type: 'tab.pick.key', tabId: this.tab.id, key: e.key, shift: e.shiftKey }).catch(() => {});
    });
    chrome.tabs.onActivated.addListener(() => this.readTab());
    chrome.tabs.onUpdated.addListener((_id, info) => { if (info.url || info.status === 'complete') this.readTab(); });
    setInterval(() => { if (this.run && this.run.waiting && this.view === 'run') this.draw(); }, 1000);
    chrome.storage.onChanged.addListener(async () => { await this.signIn(); await this.load(); this.draw(); });
    this.start();
  }

  async start() {
    await this.readTab();
    this.settings = await ask({ type: 'settings.get' });
    if (!this.settings.server || !this.settings.hasKey) this.view = 'settings';
    else { await this.signIn(); await this.load(); }
    this.draw();
  }
  async readTab() { const [tab] = await chrome.tabs.query({ active: true, currentWindow: true }); this.tab = tab || null; this.draw(); }
  async signIn() { try { this.me = await ask({ type: 'whoami' }); } catch (e) { this.me = { ok: false, detail: e.message }; } }
  async load() {
    try {
      const r = await ask({ type: 'templates.list' });
      this.templates = r.ok ? r.templates : [];
      this.problem = r.ok ? null : r.detail;
    } catch (e) { this.problem = e.message; }
  }
  go(view) { this.view = view; this.draw(); }

  heard(m) {
    if (m.type === 'pick.done') this.picked(m);
    // a run started from another panel (or before this one opened) is shown here too
    if (m.type === 'run.progress' && !m.done && (!this.run || (this.run.done && this.run.id !== m.runId))) { this.run = { t: m.t, id: m.runId, tally: m.tally }; this.view = 'run'; }
    const mine = this.run && (m.runId === this.run.id || !this.run.id);
    if (m.type === 'run.progress' && mine) {
      this.run.id = m.runId;
      this.run.tally = m.tally;
      this.run.waiting = null;
      if (m.done) { this.run.done = true; this.view = 'done'; }
      this.draw();
    }
    if (m.type === 'run.waiting' && mine) { this.run.waiting = { since: Date.now(), seconds: m.seconds, item: m.item }; this.draw(); }
    if (m.type === 'run.waited' && mine) { this.run.waiting = null; this.draw(); }
  }

  draw() {
    if (!this.mount) return;
    const parts = this[`draw_${this.view}`]();
    this.mount.replaceChildren(...parts.filter(Boolean));
  }

  head(title, back = null, ...right) {
    const who = this.me && this.me.ok ? h('span', { class: 'chip ok' }, this.me.user ? `signed in · ${this.me.user}` : 'sign-in off')
      : h('span', { class: 'chip danger' }, 'not signed in');
    return h('div', { class: 'head' },
      back ? h('button', { class: 'small', 'aria-label': 'Back', onclick: back }, '‹') : null,
      h('span', { class: 'title' }, title), ...right, back ? null : who);
  }

  // ── templates ──────────────────────────────────────────────────────────────────────────
  draw_list() {
    const here = this.tab && this.tab.url ? this.templates.filter((t) => matches(t.address, this.tab.url)) : [];
    const other = this.templates.filter((t) => !here.includes(t));
    const card = (t, mine) => h('div', { class: `card ${mine ? 'here' : ''}` },
      h('span', { class: 'name' }, t.name),
      h('div', { class: 'kv' }, h('span', { class: 'k' }, 'Address'), h('span', { class: 'mono' }, t.address),
        h('span', { class: 'k' }, 'Into table'), h('span', { class: 'mono' }, t.table),
        h('span', { class: 'k' }, 'Key'), h('span', { class: 'mono' }, t.keys.join(' | ') || '-')),
      h('div', { class: 'row' },
        mine ? h('button', { class: 'primary', onclick: () => this.startRun(t) }, 'Run') : null,
        mine ? h('button', { onclick: () => this.startPreview(t) }, 'Preview') : null,
        h('button', { onclick: () => this.edit(t) }, 'Edit'),
        h('span', { class: 'grow' }),
        h('button', { class: 'stop', onclick: () => { this.deleting = { name: t.name }; this.draw(); } }, 'Delete')),
      this.deleting && this.deleting.name === t.name ? h('div', { class: 'alert' },
        h('span', { class: 'say' }, this.deleting.detail || `Delete template ${t.name} and its ${t.fields.length} columns? Rows already collected stay`),
        h('div', { class: 'row' },
          this.deleting.detail ? null : h('button', { class: 'stop', onclick: () => this.remove(t) }, 'Delete'),
          h('button', { onclick: () => { this.deleting = null; this.draw(); } }, this.deleting.detail ? 'Close' : 'Cancel'))) : null);
    return [
      this.head('Collector'),
      h('div', { class: 'body' },
        h('div', { class: 'section' }, h('span', { class: 'meta' }, 'This page'), h('span', { class: 'mono' }, this.tab ? this.tab.url : '-')),
        this.problem ? h('div', { class: 'alert' }, h('span', { class: 'say' }, this.problem), h('span', { class: 'meta' }, 'Next: check the server and key in Settings')) : null,
        h('div', { class: 'section' }, h('span', { class: 'label' }, 'Match this page', h('span', { class: 'n' }, here.length)),
          here.length ? here.map((t) => card(t, true)) : h('span', { class: 'empty-line' }, 'No template for this address')),
        h('div', { class: 'section' }, h('span', { class: 'label' }, 'Other templates', h('span', { class: 'n' }, other.length)),
          other.length ? other.map((t) => card(t, false)) : h('span', { class: 'empty-line' }, 'None'))),
      h('div', { class: 'foot' },
        h('button', { class: 'quiet', onclick: () => this.edit(null), disabled: !this.tab }, '+ New template on this page'),
        h('span', { class: 'grow' }),
        h('button', { onclick: () => this.openHistory() }, 'History'),
        h('button', { onclick: () => this.go('settings') }, 'Settings')),
    ];
  }

  // ── editing ────────────────────────────────────────────────────────────────────────────
  edit(t) {
    this.draft = t ? copy(t) : { ...blank(), address: this.tab && this.tab.url ? patternOf(this.tab.url) : '' };
    this.attrs = {};
    this.saved = null;
    this.go('edit');
  }
  pick(kind, extra = {}) {
    if (!this.tab) return;
    this.picking = { kind, ...extra };
    ask({ type: 'tab.pick', tabId: this.tab.id, kind, t: this.draft }).catch((e) => { this.saved = { ok: false, detail: e.message }; this.picking = null; this.draw(); });
    this.draw();
  }
  picked(m) {
    const p = this.picking;
    this.picking = null;
    if (this.tab) ask({ type: 'tab.unpick', tabId: this.tab.id }).catch(() => {});   // the other frames still pick
    if (!p || m.cancelled) { this.draw(); return; }
    if (m.refused) { this.saved = { ok: false, detail: m.refused }; this.draw(); return; }
    const d = this.draft;
    d.frame = m.frame ? patternOf(m.frame) : '';
    if (p.kind === 'column') {
      const at = p.index ?? d.fields.length;
      const f = d.fields[at] || { column: '', read: 'text', regex: '' };
      d.fields[at] = { ...f, base: m.base, selector: m.selector };
      this.attrs[at] = m.attrs;
      this.samples = { ...(this.samples || {}), [at]: m.sample };
    } else if (p.kind === 'next') d.next.selector = m.selector;
    else { d[p.kind] = m.add && d[p.kind] ? `${d[p.kind]}, ${m.selector}` : m.selector; if (p.kind === 'item') this.itemCount = m.count; }
    this.draw();
  }
  draw_edit() {
    const d = this.draft;
    const pickBtn = (kind, extra) => h('button', { class: `small ${this.picking && this.picking.kind === kind ? 'primary' : ''}`, onclick: () => this.pick(kind, extra) },
      this.picking && this.picking.kind === kind ? 'Picking' : 'Pick');
    const shown = (sel, empty, count = null) => h('span', { class: `picked ${sel ? '' : 'empty'}` }, sel || empty, count !== null && sel ? h('span', { class: 'count' }, count) : null);
    const input = (value, set, attrs = {}) => h('input', { value: value ?? '', oninput: (e) => set(e.target.value), ...attrs });
    const num = (value, set) => input(value || '', (v) => set(v === '' ? 0 : Number(v)), { style: 'width:60px;text-align:right', inputmode: 'numeric' });
    const radio = (name, value, now, set, label) => h('label', { class: 'row' }, h('input', { type: 'radio', name, checked: now === value, onchange: () => { set(value); this.draw(); } }), label);
    const item = d.fields.filter((f) => f.base === 'item').map((f) => f.column).filter(Boolean);
    const content = d.fields.filter((f) => f.base === 'content').map((f) => f.column).filter(Boolean);
    const [pairItem, pairContent] = (d.pairText || '').split('=');
    const pairSelect = (list, now, set) => h('select', { onchange: (e) => { set(e.target.value); } }, h('option', { value: '' }, '-'), list.map((c) => h('option', { value: c, selected: c === now }, c)));
    const fieldRow = (f, i) => h('tr', {},
      h('td', {}, h('span', { class: `chip ${f.base === 'content' ? 'after' : 'accent'}` }, f.base === 'content' ? 'after' : 'before')),
      h('td', {}, input(f.column, (v) => { f.column = v; })),
      h('td', { class: 'mono', title: (this.samples || {})[i] || '' }, f.selector || '(the item)'),
      h('td', {}, h('select', { onchange: (e) => { f.read = e.target.value; } },
        ['text', ...new Set([...(this.attrs[i] || []), ...(f.read !== 'text' ? [f.read.slice(1)] : [])])].map((a) => {
          const v = a === 'text' ? 'text' : `@${a}`;
          return h('option', { value: v, selected: f.read === v }, v);
        }))),
      h('td', {}, input(f.regex, (v) => { f.regex = v; }, { class: 'mono' })),
      h('td', {}, h('button', { class: 'small', 'aria-label': 'Remove column', onclick: () => { d.fields.splice(i, 1); this.draw(); } }, '×')));
    return [
      this.head(`Edit · ${d.name || 'new template'}`, () => this.go('list')),
      this.picking ? h('div', { class: 'banner' }, h('b', {}, `Picking · ${this.picking.kind}`), h('span', { class: 'grow' }),
        h('span', {}, `↑ ↓ widen${this.picking.kind === 'content' ? ' · Shift+click adds an area' : ''} · Esc stops`)) : null,
      h('div', { class: 'body' },
        h('div', { class: 'kv' },
          h('label', { class: 'k', for: 'f-name' }, 'Name'), input(d.name, (v) => { d.name = v; }, { id: 'f-name' }),
          h('label', { class: 'k', for: 'f-addr' }, 'Address'), input(d.address, (v) => { d.address = v; }, { id: 'f-addr', class: 'mono' }),
          h('label', { class: 'k', for: 'f-frame' }, 'Frame'), input(d.frame, (v) => { d.frame = v; }, { id: 'f-frame', class: 'mono', placeholder: 'empty = the page' })),
        h('div', { class: 'form' },
          h('span', { class: 'step' }, '1'), h('span', { class: 'k' }, 'List area'), shown(d.listArea, 'the whole page'), pickBtn('listArea'),
          h('span', { class: 'step' }, '2'), h('span', { class: 'k' }, 'List item'), shown(d.item, 'not picked', this.itemCount ?? null), pickBtn('item'),
          h('span', { class: 'step' }, '3'), h('span', { class: 'k' }, 'Click target'), shown(d.clickTarget, 'empty = the whole item'), pickBtn('clickTarget'),
          h('span', {}), h('span', { class: 'k' }, 'Opens'),
          h('span', { class: 'row' }, radio('opens', 'in_place', d.opens, (v) => { d.opens = v; }, 'in place'), radio('opens', 'new_tab', d.opens, (v) => { d.opens = v; }, 'link, new tab')), h('span', {}),
          h('span', { class: 'step' }, '4'), h('span', { class: 'k' }, 'Content area'), shown(d.content, 'not picked'), pickBtn('content'),
          h('span', {}), h('span', { class: 'k' }, 'Wait up to'), h('span', { class: 'row' }, num(d.waitSeconds, (v) => { d.waitSeconds = v; }), 's for it to change, then skip'), h('span', {}),
          h('span', {}), h('span', { class: 'k' }, 'Same as'),
          h('span', { class: 'row' }, pairSelect(item, pairItem, (v) => { d.pairText = v || pairContent ? `${v}=${pairContent || ''}` : ''; }), '=',
            pairSelect(content, pairContent, (v) => { d.pairText = pairItem || v ? `${pairItem || ''}=${v}` : ''; }), h('span', { class: 'meta' }, 'optional')), h('span', {})),
        h('div', { class: 'section' },
          h('span', { class: 'label' }, '5 Columns', h('span', { class: 'n' }, 'before = in the item · after = in the content area')),
          h('div', { class: 'box' }, h('table', {},
            h('thead', {}, h('tr', {}, ['', 'Column', 'Element', 'Read', 'Regex', ''].map((c) => h('th', {}, c)))),
            h('tbody', {}, d.fields.map(fieldRow)))),
          h('div', { class: 'row' }, h('button', { class: `small ${this.picking && this.picking.kind === 'column' ? 'primary' : ''}`, onclick: () => this.pick('column') }, '+ Column (pick)'))),
        h('div', { class: 'kv' },
          h('label', { class: 'k', for: 'f-key' }, 'Key'), input(d.keys.join('|'), (v) => { d.keys = v.split('|').map((s) => s.trim()).filter(Boolean); }, { id: 'f-key', class: 'mono', list: 'f-cols' }),
          h('label', { class: 'k', for: 'f-table' }, 'Into table'), input(d.table, (v) => { d.table = v; }, { id: 'f-table', class: 'mono' }),
          h('span', { class: 'k' }, 'Next page'), h('span', { class: 'row' },
            radio('next', 'button', d.next.how, (v) => { d.next.how = v; }, 'button'), radio('next', 'scroll', d.next.how, (v) => { d.next.how = v; }, 'scroll the list area')),
          h('span', {}), h('span', { class: 'row' }, shown(d.next.selector, d.next.how === 'scroll' ? 'not needed' : 'not picked'), d.next.how === 'button' ? pickBtn('next') : null),
          h('span', { class: 'k' }, 'End after'), h('span', { class: 'row' }, num(d.endSeconds, (v) => { d.endSeconds = v; }), 's with no new item'),
          h('span', { class: 'k' }, 'At most'), h('span', { class: 'row' }, num(d.max, (v) => { d.max = v; }), 'items · empty = no limit'),
          h('span', { class: 'k' }, 'Close'), h('span', { class: 'row' }, shown(d.close, 'optional - none'), pickBtn('close'))),
        h('datalist', { id: 'f-cols' }, d.fields.map((f) => h('option', { value: f.column }))),
        this.saved ? h('div', { class: this.saved.ok ? 'meta' : 'alert' }, this.saved.ok ? 'Saved' : h('span', { class: 'say' }, this.saved.detail)) : null),
      h('div', { class: 'foot' },
        h('button', { class: 'primary', onclick: () => this.save() }, 'Save'),
        h('button', { onclick: () => this.startPreview(this.draft) }, 'Preview this page'),
        h('span', { class: 'grow' }),
        h('button', { onclick: () => { if (this.tab) ask({ type: 'tab.unpick', tabId: this.tab.id }).catch(() => {}); this.picking = null; this.go('list'); } }, 'Cancel')),
    ];
  }
  async remove(t) {
    let a;
    try { a = await ask({ type: 'template.delete', t }); } catch (e) { a = { ok: false, detail: e.message }; }
    this.deleting = a.ok ? null : { name: t.name, detail: a.detail };
    if (a.ok) await this.load();
    this.draw();
  }
  async save() {
    try { this.saved = await ask({ type: 'template.save', t: this.draft }); } catch (e) { this.saved = { ok: false, detail: e.message }; }
    if (this.saved.ok) await this.load();
    this.draw();
  }

  // ── preview ────────────────────────────────────────────────────────────────────────────
  async startPreview(t) {
    this.preview = { t, busy: true };
    this.go('preview');
    try { this.preview.batch = await ask({ type: 'tab.preview', tabId: this.tab.id, t, room: 5 }); } catch (e) { this.preview.problem = e.message; }
    this.preview.busy = false;
    this.draw();
  }
  draw_preview() {
    const p = this.preview;
    const cols = p.t.fields.map((f) => f.column);
    const b = p.batch;
    return [
      this.head(`Preview · ${p.t.name || 'new template'}`, () => this.go(this.draft ? 'edit' : 'list')),
      h('div', { class: 'body' },
        p.busy ? h('span', { class: 'empty-line' }, 'Reading the first 5 items…') : null,
        p.problem ? h('div', { class: 'alert' }, h('span', { class: 'say' }, p.problem)) : null,
        b ? h('div', { class: 'stats' }, stat(b.read, 'items read'), stat(b.rows.length, 'rows'), stat(b.unchecked ? '-' : b.skipped, 'key in table'), stat(b.misses.length, 'kept', b.misses.length ? 'warn' : '')) : null,
        b && b.unchecked ? h('span', { class: 'meta' }, `${p.t.table ? 'Key' : 'Table'} not set - keys not checked`) : null,
        b ? h('div', { class: 'box' }, h('table', {},
          h('thead', {}, h('tr', {}, cols.map((c) => h('th', {}, c)))),
          h('tbody', {}, b.rows.map((r) => h('tr', {}, cols.map((c) => (r.cells[c] === null ? h('td', { class: 'empty' }, 'empty') : h('td', {}, r.cells[c])))))))) : null,
        b && b.misses.length ? h('div', { class: 'box' }, b.misses.map((m) => this.missLine(m))) : null),
      h('div', { class: 'foot' },
        h('button', { class: 'primary', onclick: () => this.startRun(p.t), disabled: !p.t.name }, 'Run all pages'),
        h('span', { class: 'grow' }),
        h('button', { onclick: () => this.edit(p.t) }, 'Edit')),
    ];
  }

  // ── a run ──────────────────────────────────────────────────────────────────────────────
  async startRun(t) {
    this.run = { t, id: null, tally: { pages: 0, read: 0, written: 0, skipped: 0, misses: [], ended: null }, started: new Date() };
    this.filter = 'all';
    this.go('run');
    try { await ask({ type: 'run.start', tabId: this.tab.id, t }); } catch (e) { this.run.tally.ended = ENDED.REFUSED; this.run.tally.detail = e.message; this.go('done'); }
  }
  /** The kept items run again - only those, found by the values read before opening; on the tab now showing their list. */
  retry(t, misses) {
    const { only, max, ...plain } = t;
    this.startRun({ ...plain, only: misses.map((m) => m.cells || {}), max: misses.length });
  }

  draw_run() {
    const { t, tally, waiting } = this.run;
    const w = waiting ? Math.min(waiting.seconds, Math.round((Date.now() - waiting.since) / 1000)) : 0;
    return [
      this.head(`Running · ${t.name}`),
      h('div', { class: 'body' },
        tally.paused ? h('div', { class: 'row' }, h('span', { class: 'chip warn' }, 'Paused'), h('span', { class: 'meta' }, `after item ${tally.read}`)) : null,
        waiting ? h('div', { class: 'section' }, h('div', { class: 'row' }, h('span', {}, `Item ${waiting.item}`), h('span', { class: 'chip after' }, 'Waiting for content to change'), h('span', {}, `${w} s of ${waiting.seconds}`)),
          h('div', { class: 'bar' }, h('div', { style: `width:${Math.round((100 * w) / waiting.seconds)}%` }))) : null,
        h('div', { class: 'stats' },
          stat(tally.pages || 1, 'page'),
          stat(t.max ? `${tally.read} of max ${t.max}` : tally.read, 'items read'),
          stat(tally.written, 'rows written', 'ok'),
          stat(tally.skipped, 'key in table, skipped'),
          ...REASONS.map(([r, k]) => stat(missCount(tally, r), k.toLowerCase(), r === 'refused' ? 'danger' : 'warn'))),
        h('span', { class: 'meta' }, 'Keep this tab open')),
      h('div', { class: 'foot' },
        h('button', { class: 'quiet', onclick: () => { this.run.pausing = !this.run.pausing; ask({ type: 'run.pause', runId: this.run.id, on: this.run.pausing }); this.draw(); } },
          this.run.pausing ? 'Resume' : 'Pause'),
        h('button', { class: 'stop', onclick: () => ask({ type: 'run.stop', runId: this.run.id }) }, 'Stop')),
    ];
  }
  missLine(m) {
    const cells = Object.entries(m.cells || {}).filter(([, v]) => v !== null).map(([k, v]) => `${k} ${v}`).join(' · ');
    return h('div', { class: `miss ${m.reason}` },
      h('div', { class: 'row' }, h('span', { class: `chip ${m.reason === 'refused' ? 'danger' : 'warn'}` }, m.reason.replace('_', ' ')), h('span', { class: 'meta' }, `#${m.index + 1}`)),
      h('span', { class: 'mono meta' }, m.at), h('span', { class: 'why' }, m.detail), cells ? h('span', {}, cells) : null);
  }
  draw_done() {
    const { t, tally } = this.run;
    const ended = { [ENDED.LAST]: ['Ended at the last page', 'ok'], [ENDED.LIMIT]: [`Stopped at limit · ${tally.read} of max ${t.max}`, 'warn'],
      [ENDED.STOPPED]: ['Stopped', 'warn'], [ENDED.REFUSED]: ['Stopped - the product refused the run', 'danger'] }[tally.ended] || ['Ended', 'ok'];
    if (t.only) ended[0] = `Retry · found ${tally.read} of ${t.only.length}`;
    const shown = tally.misses.filter((m) => this.filter === 'all' || m.reason === this.filter);
    return [
      this.head(`Done · ${t.name}`),
      h('div', { class: 'body' },
        h('div', { class: 'row' }, h('span', { class: `chip ${ended[1]}` }, ended[0]), h('span', { class: 'meta' }, `${tally.pages || 1} page(s)${tally.written ? ` · written as layer «${t.name}»` : ''}`)),
        tally.detail ? h('div', { class: 'alert' }, h('span', { class: 'say' }, tally.detail),
          h('span', { class: 'meta' }, 'Next: ask the table\'s owner for edit, or pick another table in the template')) : null,
        h('div', { class: 'stats' }, stat(tally.written, 'written', 'ok'), stat(tally.skipped, 'key in table, skipped'), stat(tally.misses.length, 'kept, not written', tally.misses.length ? 'warn' : '')),
        tally.misses.length ? h('div', { class: 'section' },
          h('span', { class: 'label' }, 'Kept', h('span', { class: 'n' }, 'in the run log · History')),
          h('div', { class: 'row' }, [['all', `All ${tally.misses.length}`], ...REASONS.map(([r, k]) => [r, `${k} ${missCount(tally, r)}`])].map(([r, label]) =>
            h('button', { class: `small ${this.filter === r ? 'on' : ''}`, onclick: () => { this.filter = r; this.draw(); } }, label))),
          h('div', { class: 'box' }, shown.map((m) => this.missLine(m)))) : null),
      h('div', { class: 'foot' },
        shown.length ? h('button', { class: 'primary', onclick: () => this.retry(t, shown) }, `Retry these ${shown.length}`) : null,
        h('span', { class: 'grow' }), h('button', { onclick: () => { this.run = null; this.go('list'); } }, 'Templates')),
    ];
  }

  // ── history ────────────────────────────────────────────────────────────────────────────
  async openHistory() {
    this.history = { runs: null, open: null, misses: null };
    this.go('history');
    try { const r = await ask({ type: 'history' }); this.history.runs = r.ok ? r.rows : []; this.history.problem = r.ok ? null : r.detail; } catch (e) { this.history.problem = e.message; }
    this.draw();
  }
  async openRun(id) {
    this.history.open = this.history.open === id ? null : id;
    this.history.misses = null;
    this.draw();
    if (!this.history.open) return;
    const r = await ask({ type: 'misses', runId: id });
    this.history.misses = r.ok ? r.rows.map(missOf) : [];
    this.draw();
  }
  draw_history() {
    const hs = this.history;
    const runLine = (r) => [h('tr', { onclick: () => this.openRun(r.run_id), style: 'cursor:pointer' },
      h('td', {}, String(r.started_at || '').replace('T', ' ').slice(0, 19)), h('td', {}, r.template),
      ...['written', 'skipped', 'no_key', 'not_opened', 'refused'].map((k) => h('td', { style: 'text-align:right' }, r[k] ?? 0))),
    hs.open === r.run_id ? h('tr', {}, h('td', { colspan: 7 }, hs.misses === null ? 'Reading…' : hs.misses.length ? [
      ...hs.misses.map((m) => this.missLine(m)),
      this.templates.some((x) => x.name === r.template) ? h('button', { class: 'quiet', onclick: () => this.retry(this.templates.find((x) => x.name === r.template), hs.misses) }, `Retry these ${hs.misses.length}`) : null,
    ] : h('span', { class: 'empty-line' }, 'Nothing kept'))) : null];
    return [
      this.head('History', () => this.go('list')),
      h('div', { class: 'body' },
        hs.problem ? h('div', { class: 'alert' }, h('span', { class: 'say' }, hs.problem)) : null,
        hs.runs === null ? h('span', { class: 'empty-line' }, 'Reading…') : h('div', { class: 'box' }, h('table', {},
          h('thead', {}, h('tr', {}, ['Started', 'Template', 'Written', 'Skipped', 'No key', 'Not opened', 'Refused'].map((c) => h('th', {}, c)))),
          h('tbody', {}, hs.runs.flatMap(runLine))))),
    ];
  }

  // ── settings ───────────────────────────────────────────────────────────────────────────
  draw_settings() {
    const s = this.settings || {};
    let server = s.server || '';
    let key = '';
    const check = async () => {
      this.me = await ask({ type: 'settings.save', server, key }).catch((e) => ({ ok: false, detail: e.message }));
      this.settings = await ask({ type: 'settings.get' });
      if (this.me.ok) await this.load();
      this.draw();
    };
    return [
      this.head('Settings', this.settings && this.settings.server ? () => this.go('list') : null),
      h('div', { class: 'body' },
        h('div', { class: 'section' }, h('label', { class: 'meta', for: 's-server' }, 'Product server'),
          h('input', { id: 's-server', class: 'mono', value: server, placeholder: 'http://server:port', oninput: (e) => { server = e.target.value; } })),
        h('div', { class: 'section' }, h('label', { class: 'meta', for: 's-key' }, 'Personal key'),
          h('input', { id: 's-key', type: 'password', placeholder: s.hasKey ? 'saved - type to replace' : 'from your account page', oninput: (e) => { key = e.target.value; } })),
        h('div', { class: 'row' }, h('button', { class: 'primary', onclick: check }, 'Save and check'),
          this.me ? (this.me.ok ? h('span', { class: 'chip ok' }, `reached · signed in as ${this.me.user || '- (sign-in off)'}`) : null) : null),
        this.me && !this.me.ok ? h('div', { class: 'alert' }, h('span', { class: 'say' }, this.me.detail),
          h('span', { class: 'meta' }, this.me.detail && this.me.detail.startsWith('server not reached') ? 'Next: open the server address in a tab of this browser' : 'Next: make a new key on your account page and paste it here')) : null),
    ];
  }
}

new Panel(document.getElementById('app'));
