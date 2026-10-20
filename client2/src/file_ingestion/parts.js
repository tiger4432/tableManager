// THE FILE INGESTION PAGE's four parts (mockup FWp74vd6UqX1i7qXpyQg8K): the table list, the search line, the files read
// (grouped under a folder or a reason), one file's detail. Each owns its div and is handed its doc and what it calls; the
// page seats them and holds the query.
import { ABSENT } from '../absent.js';
import { isDoneStatus, isFailedStatus } from '../retry_verdict.js';
import { GROUPS, WORDS, folderLine, readAtText, reasonOf, resultCounts, resultText, rowsAddress, statusTone, statusWord, tookText } from './model.js';

function maker(doc) {
  return (tag, cls, text) => {
    const n = doc.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  };
}

const pill = (el, status) => { const p = el('span', 'fi-pill', statusWord(status)); p.dataset.tone = statusTone(status); return p; };
const boxHead = (el, words, side) => {
  const h = el('div', 'fi-box-head');
  h.append(el('span', 'fi-box-title', words));
  if (side !== undefined) h.append(el('span', 'fi-meta', side));
  return h;
};

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
  /** @param {{doc, onPick: (log) => void, onMore: () => void, onDrill: (folder) => void, onRetryFolder: (group) => void}} deps */
  constructor(mount, deps) {
    this.mount = mount;
    this.deps = deps;
    this.el = maker(deps.doc || mount.ownerDocument);
  }

  /** @param {{groups, shown: string, picked: number|null, more: boolean}} view */
  render(view) {
    const el = this.el;
    const root = el('section', 'fi-box fi-files');
    root.setAttribute('aria-label', 'Files');
    root.append(boxHead(el, WORDS.files, view.shown));
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
        if (g.count !== null) line.append(el('span', 'fi-meta fi-num', WORDS.groupSummary(g.count, g.failed)));
        if (g.folder && g.failed > 0) {
          const retry = el('button', 'fi-btn fi-btn--danger fi-group__retry', WORDS.retryFailed(g.failed));
          retry.type = 'button';
          retry.addEventListener('click', () => this.deps.onRetryFolder(g));
          line.append(retry);
        }
        td.append(line);
        tr.append(td);
        body.append(tr);
      }
      for (const log of g.files) {
        const tr = el('tr', `fi-file${view.picked === log.id ? ' is-picked' : ''}`);
        tr.dataset.log = String(log.id);
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
