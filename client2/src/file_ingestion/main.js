// THE FILE INGESTION PAGE (owner 10-20 «ㅇㅇ 일케 해», lead; mockup FWp74vd6UqX1i7qXpyQg8K): the page holds the query and
// seats the four parts. Every /admin call goes through admin_token.adminFetch (the token the admin page keeps).
import '../tokens.css';
import '../base.css';
import './file_ingestion.css';
import { API_BASE } from '../config.js';
import { adminFetch } from '../admin_token.js';
import { showToast } from '../utils.js';
import { writeClipboardRich } from '../clipboard_write.js';
import { fileRetryAsk, fileRetryToast } from '../retry_verdict.js';
import { INCLUDE_STATUSES } from '../folder_retry.js';
import { countNumberText } from '../match_count.js';
import { initTheme } from '../theme.js';
import { WORDS, groupFiles, queryOf, tableLines } from './model.js';
import { DetailPart, FilesPart, SearchPart, TableListPart } from './parts.js';

const NO_TOKEN = 'Admin token needed - open Admin once on this browser';

async function read(path) {
  const res = await adminFetch(`${API_BASE}${path}`);
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).detail || ''; } catch (e) { /* not JSON */ }
    throw new Error(res.status === 401 ? NO_TOKEN : `${path.split('?')[0]} ${res.status}${detail ? ` · ${typeof detail === 'string' ? detail : JSON.stringify(detail)}` : ''}`);
  }
  return res.json();
}

async function act(path) {
  const res = await adminFetch(`${API_BASE}${path}`, { method: 'POST' });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(res.status === 401 ? NO_TOKEN : `${res.status}${body.detail ? ` · ${typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)}` : ''}`);
  return body;
}

export function seatFileIngestionPage(doc = document) {
  const byId = (id) => doc.getElementById(id);
  const query = { table: new URLSearchParams(doc.defaultView.location.search).get('table') || '', status: 'ALL', name: '', folder: '', from: '', to: '', group: 'folder' };
  const view = { lines: [], rows: [], groups: [], chips: [], total: null, page: 1, picked: null };
  const say = (text) => { byId('fi-said').textContent = text || ''; };
  const tables = new TableListPart(byId('fi-tables'), { doc, onPick: (name) => { query.table = name; search(); } });
  const searchPart = new SearchPart(byId('fi-search'), { doc, onChange: (patch) => { Object.assign(query, patch); search(); } });
  const files = new FilesPart(byId('fi-files'), {
    doc, onPick: (log) => { view.picked = log; draw(); },
    onMore: () => { view.page += 1; list(true); },
    onDrill: (folder) => { query.folder = folder; search(); },
    onRetryFolder: (g) => handAgain(g.folder, false),
    onReadAll: (folder) => handAgain(folder || query.folder, true),
  });
  // «Retry N failed» and «Read all again»: the files this table read (read_by, B 1107c5a8e) under the folder - none: the
  // whole table - through the one Retry door, every state with `all` (총괄 10-21); the preview's number asked first
  async function handAgain(folder, all) {
    const p = new URLSearchParams({ read_by: query.table || '' });
    if (folder) p.set('folder', folder);
    if (all) p.set('statuses', INCLUDE_STATUSES);
    const q = queryOf(query);
    for (const key of ['since', 'until']) if (q.has(key)) p.set(key, q.get(key));
    try {
      const seen = await act(`/admin/file-ingestion/retry-failed?${p}&preview=true`);
      if (!seen.count) { showToast(seen.message || 'Nothing to read', 'info'); return; }
      const where = folder || query.table;
      if (!doc.defaultView.confirm(all ? WORDS.readAllAsk(seen.count, where) : WORDS.retryAsk(seen.count, where))) return;
      const done = await act(`/admin/file-ingestion/retry-failed?${p}`);
      showToast(done.message || `${seen.count} handed again`, 'success');
      await list(false);
    } catch (e) { showToast(`❌ ${e.message}`, 'error'); }
  }

  const detail = new DetailPart(byId('fi-detail'), {
    doc,
    onCopy: (text, words) => {
      if (writeClipboardRich('', text)) showToast(`📋 ${words.replace(/^Copy /, '')} copied`, 'info');
      else showToast('❌ Copy failed', 'error');
    },
    onAct: async (log) => {
      const ask = fileRetryAsk(log, INCLUDE_STATUSES);
      if (!doc.defaultView.confirm(ask.confirm)) return;
      try {
        const res = await adminFetch(`${API_BASE}/admin/file-ingestion/retry-failed?${ask.query}`, { method: 'POST' });
        if (!res.ok) throw new Error(`retry ${res.status}`);
        const result = await res.json().catch(() => ({}));
        await list(false);
        const now = view.rows.find((r) => r.id === log.id);
        const said = fileRetryToast(result, now ? now.status : null, log);
        showToast(said.text, said.tone);
      } catch (e) {
        showToast(`❌ ${e.message}`, 'error');
      }
    },
  });

  function draw() {
    const picked = view.picked && view.rows.find((r) => r.id === view.picked.id);
    view.picked = picked || null;
    tables.render(view.lines, query.table);
    searchPart.render(query, view.chips);
    const groups = groupFiles(view.rows, query.group, view.groups, query.folder);
    const match = view.total ? countNumberText(view.total) : '0';
    files.render({ groups, picked: view.picked ? view.picked.id : null, more: !!view.total && view.rows.length < view.total.total,
      table: query.table,
      shown: WORDS.shown(view.rows.length, groups.filter((g) => g.head).length, match) });
    detail.render(view.picked);
  }

  async function list(append) {
    try {
      const page = append ? view.page : 1;
      const answer = await read(`/admin/file-ingestion/logs?${queryOf(query, { page })}`);
      view.page = page;
      view.rows = append ? view.rows.concat(answer.data || []) : (answer.data || []);
      view.groups = answer.groups || [];
      view.total = { total: answer.total, capped: answer.capped };
      say('');
    } catch (e) { say(e.message); }
    draw();
  }

  async function search() {
    view.picked = null;
    try {
      const chips = await read(`/admin/file-ingestion/logs?${queryOf(query, { page: 1, limit: 1, group: 'status', status: 'ALL' })}`);
      view.chips = (chips.groups || []).map((g) => ({ key: g.key, count: g.count }));
    } catch (e) { say(e.message); }
    await list(false);
  }

  async function start() {
    try {
      const [t, a] = await Promise.all([read('/admin/file-ingestion/tables'), read('/admin/file-ingestion/active')]);
      view.lines = tableLines(t.data, a.data);
      if (!query.table && view.lines.length) query.table = view.lines[0].name;
      byId('fi-as-of').textContent = `as of ${new Date().toLocaleTimeString('en-GB')}`;
    } catch (e) { say(e.message); }
    await search();
  }

  draw();
  start();
  return { query, view, search };
}

if (typeof document !== 'undefined' && document.getElementById('fi-page')) {
  try { initTheme(); } catch (e) { /* the page draws in its stored theme either way */ }
  seatFileIngestionPage(document);
}

