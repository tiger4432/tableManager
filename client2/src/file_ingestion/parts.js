// THE FILE INGESTION PAGE's four parts (mockup FWp74vd6UqX1i7qXpyQg8K): the table list, the search line, the files read
// (grouped under a folder or a reason), one file's detail. Each owns its div and is handed its doc and what it calls; the
// page seats them and holds the query.
import { ABSENT } from '../absent.js';
import { setDisabledReason } from '../disabled_reason.js';
import { isDoneStatus, isFailedStatus } from '../retry_verdict.js';
import { localShort } from '../server_time.js';
import { GROUPS, PROGRESS_COLUMNS, WORDS, folderLine, leftText, pickBody, pickKey, pickMeta, pickPage, readAfter, readAtText, readBefore, readCount, reasonOf, resultCounts, resultText, rowsAddress, statusTone, statusWord, tookText } from './model.js';

function maker(doc) {
  return (tag, cls, text) => {
    const n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  };
}

const pill = (el, status, words) => { const p = el('span', 'fi-pill', words === undefined ? statusWord(status) : words); p.dataset.tone = statusTone(status); return p; };
const boxHead = (el, words, side) => {
  const h = el('div', 'fi-box-head');
  h.append(el('span', 'fi-box-title', words));
  if (side !== undefined) h.append(el('span', 'fi-meta', side));
  return h;
};

export class ProgressPart {
  /** The checklist's progress (owner 10-23): a row per table and source, its columns PROGRESS_COLUMNS; a source with
   *  nothing left dimmed; «Cancel waiting re-reads» on an external source with some waiting; «Pick files» on each, the
   *  picked one's panel (`pickMount`, the page's) in a row right under it (owner 10-26). The same rows on a beat are
   *  written in place, so the panel under one is never taken out and put back (its box would lose what is typed).
   *  @param {{doc, onCancel: (folder) => void, pickMount?: Element, onPick?: (line|null) => void}} deps */
  constructor(mount, deps) {
    this.mount = mount;
    this.deps = deps;
    this.el = maker(deps.doc || mount.ownerDocument);
    this.picked = null;
    this.drawn = null;
  }

  render(lines, counted) {
    // the rows' shape: the sources, each one's unread sentences (a row of their own) and the picked one
    const keysOf = () => `${lines.map((l) => `${pickKey(l)}\t${l.unread.join('\t')}`).join('\n')}\n${this.picked || ''}`;
    if (this.drawn && this.drawn.keys === keysOf()) { this.update(lines, counted); return; }
    if (this.picked && !lines.some((l) => pickKey(l) === this.picked)) {
      this.picked = null;
      if (this.deps.onPick) this.deps.onPick(null);
    }
    this.build(lines, counted, keysOf());
  }

  /** «Pick files» pressed: that source's panel opens under it, or closes when it was the open one. */
  pick(line) {
    const key = pickKey(line);
    this.picked = this.picked === key ? null : key;
    if (this.deps.onPick) this.deps.onPick(this.picked ? line : null);
    if (this.drawn) this.render(this.drawn.lines, this.drawn.counted);
  }

  update(lines, counted) {
    this.drawn.side.textContent = counted || '';
    this.drawn.lines = lines;
    this.drawn.counted = counted;
    lines.forEach((line, i) => {
      const row = this.drawn.rows[i];
      row.tr.className = line.done ? 'fi-dim' : '';
      PROGRESS_COLUMNS.forEach((c, j) => { row.cells[j].textContent = String(c.cell(line)); });
      // the buttons kept while what they do is the same - a beat must not take the focus off them
      if (row.cancel !== line.cancel) { row.act.replaceChildren(...this.actions(line)); row.cancel = line.cancel; }
    });
  }

  actions(line) {
    const el = this.el;
    const out = [];
    if (line.cancel) {
      const b = el('button', 'fi-btn', WORDS.cancelReread);
      b.type = 'button';
      b.addEventListener('click', () => this.deps.onCancel(line.cancel));
      out.push(b);
    }
    if (this.deps.pickMount) {
      const b = el('button', 'fi-btn', WORDS.pickFiles);
      b.type = 'button';
      b.setAttribute('aria-expanded', this.picked === pickKey(line) ? 'true' : 'false');
      b.addEventListener('click', () => this.pick(line));
      out.push(b);
    }
    return out;
  }

  build(lines, counted, keys) {
    const el = this.el;
    const root = el('section', 'fi-box fi-progress');
    const head0 = boxHead(el, WORDS.progress, counted || '');
    root.append(head0);
    this.drawn = { keys, lines, counted, side: head0.children[head0.children.length - 1], rows: [] };
    if (!lines.length) {
      root.append(el('div', 'fi-say fi-pad', WORDS.noSources));
      this.mount.replaceChildren(root);
      return;
    }
    const doc = this.deps.doc || this.mount.ownerDocument;
    // the panel moves with its row when the rows change - a box being typed in keeps its focus
    let typing = null;
    for (let n = doc && doc.activeElement; n && this.deps.pickMount; n = n.parentNode) if (n === this.deps.pickMount) { typing = doc.activeElement; break; }
    const table = el('table', 'fi-list');
    const head = el('tr');
    for (const c of PROGRESS_COLUMNS) {
      const th = el('th', c.cls, c.head);
      if (c.title) th.title = c.title;
      head.append(th);
    }
    head.append(el('th', 'cell-fit'));
    const body = el('tbody');
    for (const line of lines) {
      const tr = el('tr', line.done ? 'fi-dim' : '');
      tr.dataset.table = line.table;
      const cells = PROGRESS_COLUMNS.map((c) => {
        const td = el('td', c.cls, c.cell(line));
        if (c.wrap) td.dataset.wrapOk = '';
        tr.append(td);
        return td;
      });
      // the buttons in a box of their own - a flex cell would leave the table's layout and lie over its neighbour
      const cell = el('td', 'cell-fit');
      const act = el('div', 'fi-progress__acts');
      act.append(...this.actions(line));
      cell.append(act);
      tr.append(cell);
      body.append(tr);
      this.drawn.rows.push({ tr, cells, act, cancel: line.cancel });
      if (line.unread.length) {
        const said = el('tr', 'fi-progress__unread');
        const td = el('td');
        td.colSpan = PROGRESS_COLUMNS.length + 1;
        td.dataset.wrapOk = '';
        for (const sentence of line.unread) {
          const one = el('div', 'fi-progress__said', sentence);
          one.dataset.tone = 'warn';
          td.append(one);
        }
        said.append(td);
        body.append(said);
      }
      if (this.picked === pickKey(line)) {
        const under = el('tr', 'fi-progress__pick');
        const td = el('td');
        td.colSpan = PROGRESS_COLUMNS.length + 1;
        td.append(this.deps.pickMount);
        under.append(td);
        body.append(under);
      }
    }
    const thead = el('thead');
    thead.append(head);
    table.append(thead, body);
    // a panel open: the list scrolls in its own box, so this one is not capped under it
    const scroll = el('div', `fi-scroll fi-progress__scroll${this.picked ? ' is-picking' : ''}`);
    scroll.append(table);
    root.append(scroll);
    this.mount.replaceChildren(root);
    if (typing && typing.focus) typing.focus();
  }
}

export class PickFilesPart {
  /** Pick files by pattern under one source (owner 10-26): a pattern, the files it matches read or not (a page at a time,
   *  each ticked or not; the head's tick = every listed one), Read these, and the handed files' states on the page's beat.
   *  The pattern box is drawn once per source - a beat redraws the list under it only while files are being read, never the box.
   *  @param {{doc, onList: (line, pattern) => Promise<answer>, onRead: (line, pattern, body, n) => Promise<{job}|null>,
   *           onLeft: (job, paths) => Promise<{handed, left, read, failed, matched, handing, not_handed, files}>}} deps */
  constructor(mount, deps) {
    this.mount = mount;
    this.deps = deps;
    this.el = maker(deps.doc || mount.ownerDocument);
    this.line = null;
  }

  /** Open under a source's line (none: closed). */
  open(line) {
    Object.assign(this, { line, pattern: '', answer: null, listedAt: 0, refused: '', page: 1, ticked: new Set(), reading: null, busy: false });
    if (!line) { this.mount.replaceChildren(); return; }
    const el = this.el;
    const form = el('form', 'fi-pick__form');
    const label = el('label', 'fi-field fi-grow2');
    label.append(el('span', 'fi-label', WORDS.pattern));
    const input = el('input', 'fi-input fi-mono');
    input.spellcheck = false;
    label.append(input);
    const go = el('button', 'fi-btn', WORDS.list);
    go.type = 'submit';
    this.age = el('span', 'fi-meta');
    form.append(label, go, this.age);
    form.addEventListener('submit', (e) => { e.preventDefault(); this.pattern = input.value.trim(); if (this.pattern) this.list(); });
    this.input = input;
    this.body = el('div', 'fi-pick__body');
    const root = el('div', 'fi-pick');
    root.append(form, this.body);
    this.mount.replaceChildren(root);
    this.drawBody();
  }

  async list() {
    this.busy = true;
    this.drawBody();
    try {
      this.answer = await this.deps.onList(this.line, this.pattern);
      // a read that came to its end is the last list's; one with files left stays said until they are read
      Object.assign(this, { refused: '', listedAt: Date.now(), page: 1, ticked: new Set(), reading: this.going() ? this.reading : null });
    } catch (e) {
      Object.assign(this, { answer: null, refused: e.message });
    }
    this.busy = false;
    this.drawBody();
  }

  async read() {
    const body = pickBody(this.answer, this.ticked);
    const n = readCount(this.answer, this.ticked);
    // answered at once with its job; the server hands the files after (B b5ee3f42a) and the beat asks how far it came
    const job = await this.deps.onRead(this.line, this.answer.pattern || this.pattern, body, n);
    if (!job) return;
    const paths = body ? body.paths : this.answer.files.map((f) => f.path);
    this.reading = { job: job.job, n, handed: new Set(paths), now: new Map(), counts: { handed: 0, left: 0, read: 0, failed: 0, matched: null },
      handing: true, lost: '' };
    this.drawBody();
    await this.tick();
  }

  /** A Read these still moving: handing, or handed files left to read - and the server still knows its job. */
  going() {
    const r = this.reading;
    return Boolean(r) && !r.lost && (r.handing || r.counts.left > 0);
  }

  /** The handed files on the page shown - the only ones whose states the beat asks (After), at most a page. */
  shownHanded() {
    return pickPage(this.answer.files || [], this.page).rows.map((f) => f.path).filter((p) => this.reading.handed.has(p));
  }

  /** The page's beat: the job asked while it moves, or once for a page whose handed files were not asked yet; the
   *  list's age said again. */
  async tick() {
    if (!this.line) return;
    const r = this.reading;
    const shown = r && this.answer ? this.shownHanded() : [];
    if (r && !r.lost && (this.going() || shown.some((p) => !r.now.has(p)))) {
      // one ask at a time - Read these, the progress beat and its re-read after a hand-off each call this, and an older
      // answer landing after a newer one would draw the job backwards
      if (this.asking) return;
      this.asking = true;
      try {
        const got = await this.deps.onLeft(r.job, shown);
        r.counts = got;
        r.handing = Boolean(got.handing);
        for (const p of shown) if (!r.now.has(p)) r.now.set(p, null);
        for (const f of got.files || []) r.now.set(f.path, f);
      } catch (e) {
        // the server knows no such job (restarted, or past the newest it keeps) - its sentence said, not asked again;
        // else the next beat asks
        if (e.status === 404) r.lost = e.message;
      } finally {
        this.asking = false;
      }
      this.drawBody();
      return;
    }
    // nothing being read: only the age moves - a redraw would scroll the list back to its top under the reader
    this.sayAge();
  }

  sayAge() {
    this.age.textContent = this.busy ? WORDS.listing : this.listedAt ? WORDS.listedAgo((Date.now() - this.listedAt) / 1000) : '';
  }

  drawBody() {
    if (!this.line) return;
    const el = this.el;
    this.input.setAttribute('aria-invalid', this.refused ? 'true' : 'false');
    this.sayAge();
    // a redraw keeps the list where it was scrolled and the control that held the focus
    const was = this.body.querySelector('.fi-pick__list');
    const top = was ? was.scrollTop : 0;
    const doc = this.mount.ownerDocument;
    const held = doc && [...this.body.querySelectorAll('[data-pick]')].includes(doc.activeElement) ? doc.activeElement.dataset.pick : null;
    const parts = [];
    if (this.refused) {
      const why = el('div', 'fi-why');
      why.setAttribute('role', 'alert');
      why.append(el('span', 'fi-why__title', WORDS.notRead), el('span', '', this.refused));
      parts.push(why);
    }
    if (this.answer) parts.push(...this.drawList());
    this.body.replaceChildren(...parts);
    const now = this.body.querySelector('.fi-pick__list');
    if (now) now.scrollTop = top;
    const back = held && [...this.body.querySelectorAll('[data-pick]')].find((n) => n.dataset.pick === held);
    if (back) back.focus();
  }

  drawList() {
    const el = this.el;
    const files = this.answer.files || [];
    const { page, pages, rows } = pickPage(files, this.page);
    const meta = el('div', 'fi-pick__meta');
    const said = el('span', 'fi-meta fi-num', pickMeta(this.answer, this.ticked.size));
    const pager = el('div', 'fi-pick__pager');
    const step = (words, to, off) => {
      const b = el('button', 'fi-btn', words);
      b.type = 'button';
      b.disabled = off;
      b.dataset.pick = words;
      b.addEventListener('click', () => { this.page = to; this.drawBody(); });
      return b;
    };
    pager.append(step(WORDS.prev, page - 1, page <= 1), el('span', 'fi-meta fi-num', WORDS.pageOf(page, pages)), step(WORDS.next, page + 1, page >= pages));
    meta.append(said, pager);
    const table = el('table', 'fi-list');
    const head = el('tr');
    const all = el('input');
    all.type = 'checkbox';
    all.setAttribute('aria-label', WORDS.tickAll);
    all.dataset.pick = 'all';
    all.checked = files.length > 0 && this.ticked.size === files.length;
    all.addEventListener('change', () => { this.ticked = all.checked ? new Set(files.map((f) => f.path)) : new Set(); this.drawBody(); });
    const corner = el('th', 'cell-fit');
    corner.append(all);
    head.append(corner, ...WORDS.pickHeads.map((h) => el('th', h === 'Path' || h === 'After' ? '' : 'cell-fit', h)));
    const tbody = el('tbody');
    for (const f of rows) {
      const tr = el('tr', 'fi-file');
      const box = el('input');
      box.type = 'checkbox';
      box.setAttribute('aria-label', WORDS.tickOne(f.rel || f.path));
      box.dataset.pick = `tick:${f.path}`;
      box.checked = this.ticked.has(f.path);
      box.addEventListener('change', () => { if (box.checked) this.ticked.add(f.path); else this.ticked.delete(f.path); this.drawBody(); });
      const tick = el('td', 'cell-fit');
      tick.append(box);
      const path = el('td', 'fi-mono fi-path', f.rel || f.path);
      path.title = f.path;
      path.dataset.wrapOk = '';
      const before = readBefore(f);
      const was = el('td', 'cell-fit');
      was.append(pill(el, before.status, before.words));
      const after = this.reading ? readAfter(f, this.reading.handed, this.reading.now) : null;
      const now = el('td', after ? 'fi-pick__after' : 'fi-meta cell-fit', after ? undefined : ABSENT);
      if (after) {
        now.append(pill(el, after.status, after.words));
        if (after.why) { const why = el('div', 'fi-result', after.why); why.dataset.wrapOk = ''; now.append(why); }
      }
      tr.append(tick, path, el('td', 'fi-meta fi-num cell-fit', f.modified_at ? localShort(f.modified_at) : ABSENT), was, now);
      tbody.append(tr);
    }
    const thead = el('thead');
    thead.append(head);
    table.append(thead, tbody);
    const scroll = el('div', 'fi-scroll fi-pick__list');
    scroll.append(table);
    const acts = el('div', 'fi-pick__acts');
    const n = readCount(this.answer, this.ticked);
    const go = el('button', 'fi-btn fi-btn--primary', WORDS.readThese(n));
    go.type = 'button';
    go.dataset.pick = 'read';
    const r = this.reading;
    const going = this.going();
    const wait = !going ? '' : r.handing ? WORDS.handing(r.counts.matched ?? r.n) : WORDS.readingWait(r.counts.left);
    if (!files.length) go.disabled = true;
    else if (wait) setDisabledReason(go, wait);
    go.addEventListener('click', () => this.read());
    acts.append(go, el('span', 'fi-meta', wait || (this.ticked.size ? '' : WORDS.noneTicked(n))));
    const out = [meta, scroll, acts];
    if (r) {
      const line = el('div', 'fi-pick__reading');
      const word = r.lost ? WORDS.lostWord : r.handing ? WORDS.handingWord : r.counts.left > 0 ? WORDS.reading : WORDS.readDone;
      line.append(el('span', 'fi-pick__reading-word', word), el('span', 'fi-num', r.lost || leftText(r.counts)));
      out.push(line);
    }
    return out;
  }
}

export class ReadNowPart {
  /** «Read now» (총괄 aaf19d0ca): a path, who reads it and why the watcher did not - the server's words - and a button
   * per owner. @param {{doc, onCheck: (path) => Promise<answer>, onRead: (path, table) => Promise<void>}} deps */
  constructor(mount, deps) {
    this.mount = mount;
    this.deps = deps;
    this.el = maker(deps.doc || mount.ownerDocument);
    this.path = '';
    this.answer = null;
    this.refused = '';
  }

  render() {
    const el = this.el;
    const root = el('section', 'fi-box fi-readnow');
    root.append(boxHead(el, WORDS.readNowTitle));
    const form = el('form', 'fi-readnow__form fi-pad');
    const label = el('label', 'fi-field fi-grow2');
    label.append(el('span', 'fi-label', WORDS.readNowPath));
    const input = el('input', 'fi-input fi-mono');
    input.value = this.path;
    input.spellcheck = false;
    label.append(input);
    const check = el('button', 'fi-btn', WORDS.check);
    check.type = 'submit';
    form.append(label, check);
    form.addEventListener('submit', (e) => { e.preventDefault(); this.path = input.value.trim(); if (this.path) this.check(); });
    root.append(form);
    if (this.refused) {
      const why = el('div', 'fi-why fi-readnow__said');
      why.append(el('span', 'fi-why__title', WORDS.notRead), el('span', '', this.refused));
      root.append(why);
    }
    for (const owner of (this.answer && this.answer.owners) || []) {
      const line = el('div', 'fi-readnow__owner');
      const words = owner.why_not.length ? owner.why_not.join(' · ') : WORDS.taken;
      const said = el('span', '', words);
      said.dataset.tone = owner.why_not.length ? 'warn' : 'ok';
      const read = el('button', 'fi-btn fi-btn--primary', WORDS.readNow);
      read.type = 'button';
      read.dataset.table = owner.table;
      read.addEventListener('click', () => this.deps.onRead(this.answer.path, owner.table));
      line.append(el('span', 'fi-mono', owner.table), el('span', 'fi-meta fi-path', owner.source), said, read);
      root.append(line);
    }
    this.mount.replaceChildren(root);
  }

  async check() {
    try {
      this.answer = await this.deps.onCheck(this.path);
      this.refused = '';
    } catch (e) {
      this.answer = null;
      this.refused = e.message;
    }
    this.render();
  }
}

export class TableListPart {
  /** @param {{doc, onPick: (name) => void}} deps */
  constructor(mount, deps) {
    this.mount = mount;
    this.deps = deps;
    this.el = maker(deps.doc || mount.ownerDocument);
    this.find = '';
  }

  render(lines, picked) {
    const el = this.el;
    const root = el('nav', 'fi-box fi-tables');
    root.setAttribute('aria-label', WORDS.tables);
    root.append(boxHead(el, WORDS.tables));
    const label = el('label', 'fi-field fi-pad');
    label.append(el('span', 'fi-label', WORDS.findTable));
    const input = el('input', 'fi-input');
    input.type = 'search';
    input.value = this.find;
    input.addEventListener('input', () => { this.find = input.value; this.list(list, lines, picked); });
    label.append(input);
    const list = el('div', 'fi-table-list');
    root.append(label, list);
    this.list(list, lines, picked);
    this.mount.replaceChildren(root);
  }

  list(list, lines, picked) {
    const el = this.el;
    const want = this.find.trim().toLowerCase();
    const shown = (lines || []).filter((t) => !want || String(t.name).toLowerCase().includes(want));
    if (!shown.length) { list.replaceChildren(el('div', 'fi-say fi-pad', WORDS.noTables)); return; }
    list.replaceChildren(...shown.map((t) => {
      const b = el('button', `fi-table${t.name === picked ? ' is-picked' : ''}`);
      b.type = 'button';
      b.dataset.table = t.name;
      const top = el('span', 'fi-table__top');
      top.append(el('span', 'fi-mono', t.name), el('span', 'fi-meta fi-num', t.total));
      const counts = el('span', 'fi-table__counts');
      const ok = el('span', 'fi-num', WORDS.ok(t.ok)); ok.dataset.tone = 'ok';
      const failed = el('span', 'fi-num', WORDS.failed(t.failed)); failed.dataset.tone = 'danger';
      counts.append(ok, failed, el('span', 'fi-meta fi-num', WORDS.running(t.running)));
      if (t.waiting) counts.append(el('span', 'fi-meta fi-num', WORDS.waiting(t.waiting)));
      b.append(top, counts, el('span', 'fi-meta', WORDS.last(t.last)));
      b.addEventListener('click', () => this.deps.onPick(t.name));
      return b;
    }));
  }
}

export class SearchPart {
  /** @param {{doc, onChange: (patch) => void}} deps - a patch of the query: {status} · {name} · {folder} · {from} · {to} · {group} */
  constructor(mount, deps) {
    this.mount = mount;
    this.deps = deps;
    this.el = maker(deps.doc || mount.ownerDocument);
  }

  /** @param {{table, status, name, folder, from, to, group}} query  @param {Array<{key, count}>} chips the statuses and their counts */
  render(query, chips) {
    const el = this.el;
    const root = el('section', 'fi-box fi-search');
    root.setAttribute('aria-label', 'Search');
    const field = (words, control, cls = '') => { const f = el('label', `fi-field ${cls}`); f.append(el('span', 'fi-label', words), control); return f; };
    const table = el('span', 'fi-table-shown fi-mono', query.table || ABSENT);
    const tableBox = el('div', 'fi-field');
    tableBox.append(el('span', 'fi-label', WORDS.table), table);
    const status = el('fieldset', 'fi-field fi-status');
    status.append(el('legend', 'fi-label', WORDS.status));
    const row = el('div', 'fi-chips');
    const total = (chips || []).reduce((n, c) => n + (c.count || 0), 0);
    for (const c of [{ key: 'ALL', count: total }, ...(chips || [])]) {
      const b = el('button', `fi-chip${(query.status || 'ALL') === c.key ? ' is-picked' : ''}`);
      b.type = 'button';
      b.dataset.status = c.key;
      b.append(el('span', '', c.key === 'ALL' ? WORDS.all : statusWord(c.key)), el('span', 'fi-chip__n fi-num', Number(c.count || 0).toLocaleString('en-US')));
      b.addEventListener('click', () => this.deps.onChange({ status: c.key }));
      row.append(b);
    }
    status.append(row);
    const text = (key, cls) => {
      const i = el('input', `fi-input ${cls || ''}`);
      i.type = 'search';
      i.value = query[key] || '';
      i.dataset.key = key;
      i.addEventListener('change', () => this.deps.onChange({ [key]: i.value }));
      return i;
    };
    const day = (key, words) => {
      const i = el('input', 'fi-input fi-day fi-num');
      i.type = 'text';
      i.placeholder = WORDS.day;
      i.value = query[key] || '';
      i.dataset.key = key;
      i.setAttribute('aria-label', words);
      i.addEventListener('change', () => this.deps.onChange({ [key]: i.value }));
      return i;
    };
    const between = el('span', 'fi-between');
    between.append(day('from', WORDS.from), day('to', WORDS.to));
    const group = el('select', 'fi-input');
    group.dataset.key = 'group';
    for (const [value, words] of GROUPS) { const o = el('option', '', words); o.value = value; group.append(o); }
    group.value = query.group || '';
    group.addEventListener('change', () => this.deps.onChange({ group: group.value }));
    root.append(tableBox, status, field(WORDS.name, text('name'), 'fi-grow'), field(WORDS.folder, text('folder', 'fi-mono'), 'fi-grow2'),
      field(WORDS.between, between), field(WORDS.groupBy, group));
    this.mount.replaceChildren(root);
  }
}

export class FilesPart {
  /** «Read all again»: every file read there - failed, read and archived alike - through the Retry door (총괄 10-21). */
  readAll(folder) {
    const b = this.el('button', 'fi-btn fi-readall', WORDS.readAll);
    b.type = 'button';
    b.addEventListener('click', () => this.deps.onReadAll(folder));
    return b;
  }

  /** @param {{doc, onPick: (log) => void, onMore: () => void, onDrill: (folder) => void, onRetryFolder: (group) => void,
   *            onReadAll: (folder) => void}} deps - onReadAll(null): the table the search names, whole */
  constructor(mount, deps) {
    this.mount = mount;
    this.deps = deps;
    this.el = maker(deps.doc || mount.ownerDocument);
  }

  /** @param {{groups, shown: string, picked: number|null, more: boolean, table: string}} view */
  render(view) {
    const el = this.el;
    const root = el('section', 'fi-box fi-files');
    root.setAttribute('aria-label', 'Files');
    const top = boxHead(el, WORDS.files, view.shown);
    if (view.table) top.append(this.readAll(null));
    root.append(top);
    const files = (view.groups || []).reduce((n, g) => n + g.files.length, 0);
    if (!files) {
      root.append(el('div', 'fi-say fi-pad', WORDS.noFiles));
      this.mount.replaceChildren(root);
      return;
    }
    const scroll = el('div', 'fi-scroll');
    const table = el('table', 'fi-list');
    const head = el('tr');
    WORDS.heads.forEach((words, i) => head.append(el('th', i >= 3 ? 'fi-num' : '', words)));
    const thead = el('thead');
    thead.append(head);
    table.append(thead);
    for (const g of view.groups) {
      const body = el('tbody');
      if (g.head) {
        const tr = el('tr', 'fi-group');
        const td = el('td');
        td.colSpan = WORDS.heads.length;
        const line = el('span', 'fi-group__line');
        if (g.folder) {
          // a folder's head narrows the search to it (lead 10-20: the server groups below the folder asked)
          const drill = el('button', 'fi-group__drill fi-mono', g.label);
          drill.type = 'button';
          drill.title = g.label;
          drill.addEventListener('click', () => this.deps.onDrill(g.folder));
          line.append(drill);
        } else line.append(el('span', 'fi-mono', g.label));
        if (g.count !== null) line.append(el('span', 'fi-meta fi-num', WORDS.groupSummary(g.count, g.failed, g.waiting)));
        if (g.folder) {
          const acts = el('span', 'fi-group__acts');
          if (g.failed > 0) {
            const retry = el('button', 'fi-btn fi-btn--danger fi-group__retry', WORDS.retryFailed(g.failed));
            retry.type = 'button';
            retry.addEventListener('click', () => this.deps.onRetryFolder(g));
            acts.append(retry);
          }
          acts.append(this.readAll(g.folder));
          line.append(acts);
        }
        td.append(line);
        tr.append(td);
        body.append(tr);
      }
      for (const log of g.files) {
        const tr = el('tr', `fi-file${view.picked === log.checklist_id ? ' is-picked' : ''}`);
        tr.dataset.log = String(log.checklist_id);
        const name = el('td');
        name.append(el('span', 'fi-mono fi-block', log.filename));
        const folder = folderLine(log);
        if (folder) { const f = el('span', 'fi-mono fi-meta fi-block', folder.shown); f.title = folder.full; name.append(f); }
        const statusCell = el('td');
        statusCell.append(pill(el, log.status));
        tr.append(name, statusCell, el('td', 'fi-result', resultText(log)), el('td', 'fi-num fi-meta', readAtText(log)), el('td', 'fi-num fi-meta', tookText(log.took_seconds)));
        tr.addEventListener('click', () => this.deps.onPick(log));
        body.append(tr);
      }
      table.append(body);
    }
    scroll.append(table);
    root.append(scroll);
    if (view.more) {
      const more = el('button', 'fi-more', WORDS.showMore);
      more.type = 'button';
      more.addEventListener('click', () => this.deps.onMore());
      root.append(more);
    }
    this.mount.replaceChildren(root);
  }
}

export class DetailPart {
  /** @param {{doc, onCopy: (text, words) => void, onAct: (log) => void}} deps */
  constructor(mount, deps) {
    this.mount = mount;
    this.deps = deps;
    this.el = maker(deps.doc || mount.ownerDocument);
  }

  render(log) {
    const el = this.el;
    const root = el('aside', 'fi-box fi-detail');
    root.setAttribute('aria-label', 'File detail');
    root.append(boxHead(el, WORDS.file));
    const body = el('div', 'fi-detail__body');
    root.append(body);
    if (!log) { body.append(el('div', 'fi-say', WORDS.pickFile)); this.mount.replaceChildren(root); return; }
    const folder = folderLine(log);
    const path = el('div', 'fi-field');
    path.append(el('span', 'fi-label', WORDS.path), el('span', 'fi-mono fi-path', log.filepath || log.filename));
    const copies = el('span', 'fi-actions');
    const copy = (words, text) => { const b = el('button', 'fi-btn', words); b.type = 'button'; b.addEventListener('click', () => this.deps.onCopy(text, words)); return b; };
    copies.append(copy(WORDS.copyPath, log.filepath || log.filename));
    if (folder) copies.append(copy(WORDS.copyFolder, folder.full));
    path.append(copies);
    const facts = el('dl', 'fi-facts');
    const fact = (words, value) => { const dd = el('dd'); if (typeof value === 'string') dd.textContent = value; else dd.append(value); facts.append(el('dt', '', words), dd); };
    fact(WORDS.table, log.table_name || ABSENT);
    fact(WORDS.readBy, log.reader || ABSENT);
    fact(WORDS.source, log.source || ABSENT);
    fact(WORDS.status, pill(el, log.status));
    fact(WORDS.readAt, `${readAtText(log)} · ${tookText(log.took_seconds)}`);
    body.append(path, facts);
    const counts = resultCounts(log);
    if (counts.length) {
      const result = el('div', 'fi-field');
      const t = el('table', 'fi-counts');
      for (const c of counts) { const tr = el('tr'); tr.append(el('td', 'fi-dim', c.label), el('td', 'fi-num', c.value)); t.append(tr); }
      result.append(el('span', 'fi-label', WORDS.result), t);
      body.append(result);
    }
    const reason = reasonOf(log);
    if (isFailedStatus(log.status) || (reason && !isDoneStatus(log.status))) {
      const why = el('div', 'fi-why');
      why.append(el('span', 'fi-why__title', WORDS.whyFailed), el('span', '', reason || ABSENT));
      if (log.failed_at) why.append(el('span', 'fi-mono fi-meta', log.failed_at));
      body.append(why);
    }
    const acts = el('div', 'fi-actions');
    const act = el('button', 'fi-btn fi-btn--primary', isFailedStatus(log.status) ? WORDS.retryFile : WORDS.readAgain);
    act.type = 'button';
    // no record yet (A daafb2214: a file whose only line is its waiting read) - nothing for the Retry door to name
    if (log.id == null) setDisabledReason(act, WORDS.notReadYet);
    act.addEventListener('click', () => this.deps.onAct(log));
    acts.append(act);
    const rows = rowsAddress(log);
    if (rows) {
      const a = el('a', 'fi-btn fi-btn--link', WORDS.showRows);
      a.setAttribute('href', rows);
      a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener');
      acts.append(a);
    }
    body.append(acts);
    this.mount.replaceChildren(root);
  }
}
