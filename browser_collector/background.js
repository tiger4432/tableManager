// The extension's service worker: every product call (a page's script cannot make one - CORS), putting the page script
// into a tab, and driving a run - batch, write, next page - across the pages it moves through.
import { Product } from './lib/product.js';
import { TABLES, templateOf, rowsOf, runRow, missRows } from './lib/declared.js';
import { runTemplate, ENDED } from './lib/run.js';
import { matches } from './lib/address.js';

chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

const product = async () => new Product(await chrome.storage.local.get(['server', 'key']));
const tell = (msg) => chrome.runtime.sendMessage(msg).catch(() => {});

/** Until the tab has loaded (a link or a next page that moved it). */
function loaded(tabId, ms = 30000) {
  return new Promise((resolve) => {
    const done = () => { chrome.tabs.onUpdated.removeListener(on); clearTimeout(timer); resolve(); };
    const on = (id, info) => { if (id === tabId && info.status === 'complete') done(); };
    const timer = setTimeout(done, ms);
    chrome.tabs.onUpdated.addListener(on);
    chrome.tabs.get(tabId).then((tab) => { if (tab.status === 'complete') done(); }, done);
  });
}

/** The frames of `tabId` a frame pattern names: '' the top, null every frame, else the first whose address matches. */
async function framesOf(tabId, frame) {
  if (frame === '') return [0];
  const all = await chrome.scripting.executeScript({ target: { tabId, allFrames: true }, func: () => location.href });
  if (frame === null) return all.map((r) => r.frameId);
  const hit = all.find((r) => matches(frame, r.result));
  if (!hit) throw new Error(`no frame on this page matches ${frame}`);
  return [hit.frameId];
}

/** A message to the page script in `tabId` - in the frames `frame` names (framesOf) - put there first when it is not. */
async function toTab(tabId, msg, frame = '') {
  const frameIds = await framesOf(tabId, frame);
  await chrome.scripting.executeScript({ target: { tabId, frameIds }, files: ['page/loader.js'] });
  const a = await chrome.tabs.sendMessage(tabId, msg, frameIds.length === 1 ? { frameId: frameIds[0] } : {});
  if (!a || !a.ok) throw new Error(a ? a.error : 'the page did not answer');
  return a.value;
}

/** A link opened in a tab of its own, read there, the tab closed. */
async function readInTab({ t, address, fields, pairValue }) {
  const tab = await chrome.tabs.create({ url: address, active: false });
  try {
    await loaded(tab.id);
    return await toTab(tab.id, { type: 'read.here', t, fields, pairValue });
  } catch (e) {
    return { opened: false, detail: String(e.message || e) };
  } finally {
    chrome.tabs.remove(tab.id).catch(() => {});
  }
}

const runs = new Map();     // run id -> { stop }

async function run(tabId, t) {
  const runId = crypto.randomUUID();
  const state = { stop: false, pause: false };
  runs.set(runId, state);
  const p = await product();
  const started = new Date().toISOString();
  const empty = { written: 0, skipped: 0, misses: [] };
  let tally = { ...empty, pages: 0, read: 0, ended: null, detail: null };
  tell({ type: 'run.progress', runId, t, tally });
  const opened = await p.write(TABLES.runs, [runRow(runId, t, started, empty)], t.name);
  if (!opened.ok) {
    tally = { ...tally, ended: ENDED.REFUSED, detail: opened.detail };
  } else {
    const tab = {
      batch: (room, first) => toTab(tabId, { type: 'batch', t, runId, room: room === Infinity ? 1e9 : room, first }, t.frame),
      // a next page that moves the tab ends the page script before it answers - the new page is read when loaded
      next: async () => { try { return await toTab(tabId, { type: 'next', t, runId }, t.frame); } catch { await loaded(tabId); return 'more'; } },
    };
    const write = { write: (rows) => p.write(t.table, rows.map((r) => r.cells), t.name) };
    try {
      tally = await runTemplate(t, tab, write, { progress: (x) => tell({ type: 'run.progress', runId, t, tally: x }), stopped: () => state.stop, paused: () => state.pause });
    } catch (e) {
      tally = { ...tally, ended: ENDED.REFUSED, detail: String(e.message || e) };
    }
    await p.write(TABLES.runs, [runRow(runId, t, started, tally)], t.name);
    if (tally.misses.length) await p.write(TABLES.misses, missRows(runId, t, tally.misses), t.name);
  }
  toTab(tabId, { type: 'run.end', runId }, t.frame).catch(() => {});
  runs.delete(runId);
  tell({ type: 'run.progress', runId, t, tally, done: true });
}

async function templates() {
  const p = await product();
  const [ts, fs] = await Promise.all([p.rows(TABLES.templates), p.rows(TABLES.fields, {}, { limit: 5000 })]);
  if (!ts.ok) return { ok: false, detail: ts.detail };
  return { ok: true, templates: ts.rows.map((row) => templateOf(row, fs.rows)) };
}

/** A template's rows of sys_template_fields, one per column. */
const fieldRowsOf = (p, name) => p.rows(TABLES.fields, { template: [name] }, { limit: 5000 });

async function save(t) {
  const p = await product();
  const rows = rowsOf(t);
  const a = await p.write(TABLES.templates, [rows.template], 'user');
  if (!a.ok) return a;
  const b = rows.fields.length ? await p.write(TABLES.fields, rows.fields, 'user') : a;
  if (!b.ok) return b;
  // a column taken out of the template leaves its row - removed, or it comes back on the next read
  const had = await fieldRowsOf(p, t.name);
  const keep = new Set(rows.fields.map((f) => f.column));
  const gone = had.rows.filter((r) => !keep.has(r.column)).map((r) => r.row_id);
  return gone.length ? p.remove(TABLES.fields, gone) : b;
}

/** A template removed - its columns' rows first (left, they come back with a template of its name), then its own row.
 *  The rows it collected and its runs' log stay. */
async function remove(t) {
  const p = await product();
  for (const [table, rows] of [[TABLES.fields, () => fieldRowsOf(p, t.name)], [TABLES.templates, () => p.rows(TABLES.templates, { template: [t.name] })]]) {
    const had = await rows();
    if (!had.ok) return had;
    const a = had.rows.length ? await p.remove(table, had.rows.map((r) => r.row_id)) : had;
    if (!a.ok) return a;
  }
  return { ok: true };
}

const DOORS = {
  'settings.get': async () => { const s = await chrome.storage.local.get(['server', 'key']); return { server: s.server || '', hasKey: Boolean(s.key) }; },
  'settings.save': async ({ server, key }) => {
    await chrome.storage.local.set(key ? { server, key } : { server });
    return (await product()).whoAmI();
  },
  whoami: async () => (await product()).whoAmI(),
  'templates.list': templates,
  'template.save': async ({ t }) => save(t),
  'template.delete': async ({ t }) => remove(t),
  'keys.existing': async ({ t, cellsList }) => {
    try { return { keys: [...await (await product()).existing(t.table, t.keys, cellsList)] }; } catch (e) { return { error: e.message }; }
  },
  'tab.read': readInTab,
  'tab.pick': async ({ tabId, kind, t }) => toTab(tabId, { type: 'pick.start', kind, t }, null),
  'tab.unpick': async ({ tabId }) => toTab(tabId, { type: 'pick.stop' }, null),
  'tab.pick.key': async ({ tabId, key, shift }) => toTab(tabId, { type: 'pick.key', key, shift }, null),
  'tab.preview': async ({ tabId, t, room }) => toTab(tabId, { type: 'preview', t, room }, t.frame),
  'run.start': async ({ tabId, t }) => { run(tabId, t); return true; },
  'run.stop': async ({ runId }) => { const s = runs.get(runId); if (s) s.stop = true; return true; },
  'run.pause': async ({ runId, on }) => { const s = runs.get(runId); if (s) s.pause = Boolean(on); return true; },
  history: async () => (await product()).rows(TABLES.runs, {}, { limit: 100, orderBy: 'started_at' }),
  misses: async ({ runId }) => (await product()).rows(TABLES.misses, { run_id: [runId] }, { limit: 5000 }),
};

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  const door = DOORS[msg && msg.type];
  if (!door) return false;
  door(msg).then((v) => reply({ ok: true, value: v }), (e) => reply({ ok: false, error: String(e && e.message || e) }));
  return true;
});
