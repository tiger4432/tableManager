#!/usr/bin/env node
// Every screen, opened in real Chrome before a screen commit lands (lead 1343e5cca; owner 10-09 「이런 잘림 같은 ui
// 요소는 사전에 차단하면 안 됨?」). Each html entry in the built dist is opened at each size, driven through its states,
// and measured in the page:
//   clip      an element that clips (overflow hidden/clip) holds more than it shows - a letter's box crosses its
//             side - and neither it nor an element around it carries data-clip-ok (a cut made on purpose)
//   overflow  the page scrolls sideways, or a visible element outside every clipping box sits off the screen
//   panel     a panel a header button opens hangs right under it (its top, and its left or right edge, within TOL),
//             on screen, its first control takes a click, and none of its rows breaks into two lines (data-wrap-ok
//             on a panel that wraps on purpose)
//   text      visible text says [object ...], undefined or NaN
//   size      a button half again taller than the other items of its line, its letters no larger than theirs
//   columns   a table row whose long text cell runs past three lines while a short cell beside it leaves more than
//             half its width empty (owner 10-09: a narrow Source beside a wide Last)
//   words     a word broken between two of its letters (lead 10-09: a rule name in four pieces); data-wrap-ok on text
//             broken on purpose. A break after - or / is the browser's own, and letters outside a-z 0-9 _ are not read
//   answers   a GET the fixtures do not answer, or a screen that could not be driven
//   cells     what one screen asks of itself after one of its states (CELLS): the grid's header message - a press on
//             the button beside it reaches the button, and its title is its whole sentence (lead 10-09)
// One line per finding: entry · size · state · element path · what. Sizes: 1920x950, 1536x864, 1280x720.
// Chrome hands every request here (DevTools Fetch). Files come from dist, GETs from fixtures/screens_answers.json.gz
// (capture_screens.py), the two queues from fixtures/chain_states.json; no request reaches a server of ours. A GET with
// no answer is a red line - an unanswered screen draws empty and measures nothing. Other methods are refused and
// counted; a page that leaves (a link, Log out) is answered 204 and stays. Another origin's file (the fonts, the
// admin's editor) is fetched as the page asks: without the editor the admin page stops booting, without the fonts
// every width is measured in another face.
// --mutate: the five that leaked on 10-08/09, and the ledger table's hand widths (owner 10-09), are built back one at a
// time (vite, a temp folder) and each must be red.
//   node client2/tests/screen_layout_harness.mjs [--mutate] [--only <entry.html>] [--shots <dir>]
import { spawn } from 'node:child_process';
import { readFileSync, existsSync, mkdtempSync, rmSync, readdirSync, writeFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readSourceText } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CLIENT = path.resolve(HERE, '..');
const FIX = path.join(HERE, 'fixtures');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const ORIGIN = 'http://screens.test';
const SIZES = [[1920, 950], [1536, 864], [1280, 720]];
// Sizes one entry is seen at too: the walk page where the lead read its table (Edge 1568x775, lead 34d91c09d; Edge
// 1896x907 with the demo pair, lead 10-10 after 517eb6c2c).
// The test bed and the main grid at the four sizes their pickers are asked at (lead 72b2d7f8f) - 1280x720 is SIZES'.
const EDGE_SIZES = [[1920, 1080], [1440, 900], [1024, 768]];
// The main grid at all three too: its counts at 1024x768 were 0 wide under «‹ Prev» (lead 10-14).
// The sample page at 1024 and a phone's 390 too: the ledger declaration window's gate is five sizes (lead 4c7b42b0a).
const ENTRY_SIZES = { 'walk.html': [[1568, 775], [1896, 907], [1280, 720]], 'testbed.html': EDGE_SIZES, 'index.html': EDGE_SIZES,
  'sample.html': [[1024, 768], [390, 844]] };
// At 1024x768 the main grid is driven to its first state only: past it (a filter typed at the right end) the run loses
// Chrome and ends unsettled - not chased (lead 10-14 «그 밖의 1024 결함은 찾아 나서지 말 것»).
const FIRST_STATE_ONLY = { 'index.html': ['1024x768'] };
const sizesOf = (entry) => [...SIZES, ...(ENTRY_SIZES[entry] || [])];
const RULES = ['clip', 'overflow', 'panel', 'text', 'size', 'columns', 'words'];
const TOL = 12;
const argOf = (k) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : null);
const only = argOf('--only');
const shots = argOf('--shots');
const MUTATE = process.argv.includes('--mutate');
// A made-up admin token so the admin page reads one and asks the answers below; it never leaves this Chrome.
const TOKEN = 'screens-test';

// Gzipped (lead 348310aee): a capture again adds its few changed answers to the history, not 14 MB.
const ANSWERS = JSON.parse(gunzipSync(readFileSync(path.join(FIX, 'screens_answers.json.gz'))).toString('utf8')).answers;
const STATES = JSON.parse(readFileSync(path.join(FIX, 'chain_states.json'), 'utf8')).states;
// The two queues, one row per chain state - the server's shapes (66b330480, the slot's waiting_for_table); the first
// row's table has a long name.
const LONG_TABLE = 'wafer_process_inspection_result_by_lot_and_slot';
const tableOf = (i) => (i === 0 ? LONG_TABLE : 'dt_log');
const QUEUE = {
  '/outbox/queue/rows': {
    generated_at: '2026-10-08 20:00:00', clock: 'server', rules_known: ['dt_log_to_dt_map'],
    listed: { cap: 200, next_cursor: null }, population: 'processed_chain=false',
    rows: STATES.map((s, i) => ({ outbox_id: 300 + i, event_type: 'EDIT', table_name: tableOf(i), created_at: '2026-10-08 19:59:00',
      waiting_seconds: 60, owner: 'chain', chain_state: s.chain_state, broadcast_state: 'pending',
      rules: [{ name: 'dt_log_to_dt_map', will_fire: true }] })),
  },
  '/admin/chain/queue': {
    waiting: STATES.length, oldest_waiting_seconds: 60, waiting_by_owner: [], retried_among_waiting: 0,
    loop_seen_via: 'this_process', generated_at: '2026-10-08T20:00:00+09:00', now_running: [],
    waiting_transactions: STATES.map((s, i) => ({ transaction_id: `tx-${i}-0000-0000`, events: 1, rows: 1, tables: [tableOf(i)],
      waiting_seconds: 60, cancel: { key: `tx:${i}` }, chain_state: s.chain_state, slot_pid: 4242 })),
  },
};
// The main grid's Ledger column (lead 10-12): the recorded table is declared a source of the operating world and its rows
// carry ledger_rows - the first changed in another world, the second taken by no world read with one world not read - so
// a cell can measure what the column draws at its own width. The answers were recorded before either.
const LEDGER_TABLE = 'ledger_events';
const LEDGER_SOURCE = { source: 'fake_measure_events', relation: LEDGER_TABLE, emits: ['has_measurement', 'of_quantity'], world: 'default' };
const bodyOf = (a) => (typeof a.body === 'string' ? JSON.parse(a.body) : a.body);
for (const [key, a] of Object.entries(ANSWERS)) {
  if (!a || a.same_as || !a.body) continue;
  if (key.startsWith('/api/ledger/declaration')) {
    const b = bodyOf(a);
    if (Array.isArray(b.sources)) a.body = { ...b, sources: [...b.sources, LEDGER_SOURCE] };
  } else if (key.startsWith(`/tables/${LEDGER_TABLE}/data?`)) {
    const b = bodyOf(a);
    const took = (world, changed) => ({ source: LEDGER_SOURCE.source, world, changed });
    if (Array.isArray(b.data)) a.body = { ...b, data: b.data.map((row, i) => ({ ...row,
      ledger_rows: i === 0 ? [took('default', false), took('appdemo_ed', true)] : i === 1 ? [] : [took('default', false)],
      ledger_worlds_unread: i === 1 ? ['qa_unread'] : [] })) };
  }
}
// The test bed's board of dies (lead 10-14, the fourth 18766 look): its declaration saved the way the page's Save writes
// it, then the page opened again - a scatter of SYN-CX-BW-001's dies in panels by step, labels on the marked one (the
// die at x 12, the right edge), the tooltip's time and long id slots; a cross table by x. The dies' step, time and id
// are laid on the captured walk here (as the Ledger column above): the box's dies carry none.
const CX_WAFER = 'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0';
const CX_RIGHT_DIE = 'ledger-entity:v1:WyJkaWUiLHsibWF0X2lkIjoiU1lOLUNYLUJXLTAwMSIsIm1hdF90eXBlIjoiV2FmZXIiLCJ4IjoiMTIiLCJ5IjoiMyJ9XQ';
const BOARD_SAVED = (() => {
  const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
  const attr = (name) => ({ steps: [], value: { on: 'node', name }, words: [name] });
  const visual = { part: 'visual', row: 'die', start: { marking: 'marking:start' }, system: 'filter:1', filter: [], writes: 'marking:pick' };
  return {
    root: { split: 'row', children: [{ id: 'scatter-1', size: 1 }, { id: 'cross-1', size: 1 }] },
    visuals: [
      { ...visual, id: 'scatter-1', kind: 'scatter', labels: 'marked',
        encode: { x: key('x'), y: key('y'), panel: attr('step'), shape: attr('step'), label: attr('meas_id'), tip1: attr('eventtime'), tip2: attr('meas_id') } },
      { ...visual, id: 'cross-1', kind: 'crossTable', encode: { rows: key('x'), tip1: attr('eventtime') } },
    ],
    marks: { 'marking:start': [[CX_WAFER, 1]], 'marking:pick': [[CX_RIGHT_DIE, 1]] },
  };
})();
// Every kind in one board (lead 10-14, the part frame standard - task/design/BOARD_PART_FRAME_BOARD.dc.html): a map, a
// cross table with a description, one with no start yet (its empty line), a table, a scatter, a sheet - the canon's six.
const KINDS_SAVED = (() => {
  const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
  const visual = { part: 'visual', row: 'die', start: { marking: 'marking:start' }, system: 'filter:1', filter: [], writes: 'marking:pick' };
  const row = (ids) => ({ split: 'row', size: 1, children: ids.map((id) => ({ id, size: 1 })) });
  return {
    root: { split: 'column', children: [row(['map-1', 'cross-1', 'cross-2']), row(['table-1', 'scatter-1', 'sheet-1'])] },
    visuals: [
      { ...visual, id: 'map-1', kind: 'map', title: 'Die map', encode: { x: key('x'), y: key('y') } },
      // its row axis two columns - a hierarchy (lead 10-14)
      { ...visual, id: 'cross-1', kind: 'crossTable', title: 'Dies per row', description: 'Rows: type › y of the dies the start reached', encode: { rows: [key('mat_type'), key('y')] } },
      { ...visual, id: 'cross-2', kind: 'crossTable', title: 'Picked dies', start: { marking: 'marking:pick' }, writes: null, encode: { rows: key('x') } },
      { ...visual, id: 'table-1', kind: 'table', title: 'Dies', encode: { col1: { steps: [], value: { on: 'label', name: 'name' }, words: ['name'] }, col2: key('x'), col3: key('y') } },
      { ...visual, id: 'scatter-1', kind: 'scatter', encode: { x: key('x'), y: key('y'), color: [key('mat_type'), key('x')] } },
      { ...visual, id: 'sheet-1', kind: 'sheet', title: 'Wafer summary', row: null, key: 'A1', start: { node: 'wafer("SYN-CX-BW-001")' },
        cells: { A2: { input: 'Dies' }, B2: { input: '=Count([in_container~.x])' } }, encode: {} },
    ],
    marks: { 'marking:start': [[CX_WAFER, 1]] },
  };
})();
// The pictures (lead-board-14): a map filled by its Label by of images, a table's column of them, a scatter's Shape by and
// its tooltip - a die's two pictures turned in place.
const IMAGES_SAVED = (() => {
  const key = (name) => ({ steps: [], value: { on: 'key', name }, words: [name] });
  const photo = { steps: [], value: { on: 'node', name: 'photo' }, words: ['photo'] };
  const visual = { part: 'visual', row: 'die', start: { marking: 'marking:start' }, system: 'filter:1', filter: [], writes: 'marking:pick' };
  return {
    root: { split: 'row', children: [{ id: 'map-1', size: 1 }, { id: 'table-1', size: 1 }, { id: 'scatter-1', size: 1 }] },
    visuals: [
      { ...visual, id: 'map-1', kind: 'map', title: 'Die pictures', encode: { x: key('x'), y: key('y'), label: photo } },
      { ...visual, id: 'table-1', kind: 'table', title: 'Dies', encode: { col1: key('x'), col2: key('y'), col3: photo } },
      { ...visual, id: 'scatter-1', kind: 'scatter', encode: { x: key('x'), y: key('y'), shape: photo, tip1: photo } },
    ],
    marks: { 'marking:start': [[CX_WAFER, 1]] },
  };
})();
const BOARD_EVENT = '2026-11-23T18:49:00Z';
for (const [key, a] of Object.entries(ANSWERS)) {
  if (!a || a.same_as || !a.body || !key.startsWith('/api/ledger/subgraph?') || !key.includes(`positive=${encodeURIComponent(CX_WAFER)}`) || !key.includes('hops=')) continue;
  const b = bodyOf(a);
  if (!Array.isArray(b.nodes)) continue;
  a.body = { ...b, nodes: b.nodes.map((n) => (n.type !== 'die' ? n : { ...n, attributes: { ...(n.attributes || {}),
    step: Number(n.keys.x) % 2 ? 'STEP-A' : 'STEP-B', eventtime: { $datetime: BOARD_EVENT },
    meas_id: `fake-SYN-CX-BW-001-core_cmp_nonuniform-${n.keys.x}-${n.keys.y}` } })) };
}
// Pictures on the dies (lead-board-14) while the «images» state is on - a column the walk declares image, which the box's
// dies carry none of: an odd x two pictures, an even one; /api/image answers one 32 x 16 picture (its ratio not the cell's).
const PHOTOS = { on: false };
const PHOTO_PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAACAAAAAQCAIAAAD4YuoOAAAAIklEQVR4nGO4kOBAEnJouEASYhi1YNSCUQtGLRi1YChYAACOSwAumyb+zAAAAABJRU5ErkJggg==', 'base64');
const withPhotos = (a) => {
  const b = bodyOf(a);
  if (!Array.isArray(b.nodes)) return a;
  return { ...a, body: { ...b, nodes: b.nodes.map((n) => (n.type !== 'die' ? n : { ...n,
    attributes: { ...(n.attributes || {}), photo: Number(n.keys.x) % 2 ? [`d${n.keys.x}-${n.keys.y}-a`, `d${n.keys.x}-${n.keys.y}-b`] : `d${n.keys.x}-${n.keys.y}-a` },
    records: { ...(n.records || {}), photo: [{ column_type: 'image' }] } })) } };
};
const answerOf = (u) => {
  for (const [p, body] of Object.entries(QUEUE)) if (u.pathname === p) return { status: 200, type: 'application/json', body };
  const a = ANSWERS[u.pathname + u.search];
  const got = a && a.same_as ? ANSWERS[a.same_as] : a || null;
  return got && PHOTOS.on && u.pathname === '/api/ledger/subgraph' ? withPhotos(got) : got;
};
// Cells one screen asks of itself after one of its states, at every size; each answers null or why it is red.
const CELLS = [
  // The audit row's Kind word whole in its cell (lead 10-12: «OVERWRIT…» cut at 74 px) - every pill drawn, and the longest
  // word the row builder can draw (timeline.js kindOf: «OVERWRITE») set in a drawn cell and measured, as the answers may
  // hold none of it.
  { entry: 'index.html', after: 'loaded', rule: 'kind word whole', at: 'audit-kind', expr: `(() => {
  const pills = [...document.querySelectorAll('.audit-table .timeline-card .audit-kind .audit-pill')].filter((p) => p.getClientRects().length);
  if (!pills.length) return 'no kind drawn in the audit table';
  const fits = (p) => {
    const c = p.closest('.audit-kind'), cs = getComputedStyle(c), cr = c.getBoundingClientRect(), pr = p.getBoundingClientRect();
    const room = cr.right - parseFloat(cs.paddingRight) - parseFloat(cs.borderRightWidth);
    return pr.right > room + 0.5 ? 'div.audit-kind «' + p.textContent + '» ' + Math.ceil(pr.width) + ' px in ' + Math.floor(room - cr.left - parseFloat(cs.paddingLeft)) : null;
  };
  for (const p of pills) { const bad = fits(p); if (bad) return bad; }
  const was = pills[0].textContent;
  pills[0].textContent = 'OVERWRITE';
  const longest = fits(pills[0]);
  pills[0].textContent = was;
  return longest;
})()` },
  { entry: 'index.html', after: 'loaded', rule: 'beside the message', expr: `(() => {
  const log = document.getElementById('performance-log');
  if (!log || !log.getClientRects().length) return 'no header message on the page';
  const r = log.getBoundingClientRect();
  const mid = (r.top + r.bottom) / 2, centre = (r.left + r.right) / 2;
  const near = [...document.querySelectorAll('header button, header select, header input, header a[href]')]
    .filter((b) => b.getClientRects().length && getComputedStyle(b).visibility === 'visible')
    .map((b) => ({ b, box: b.getBoundingClientRect() })).filter((x) => x.box.width && x.box.top <= mid && x.box.bottom >= mid);
  const at = (x) => (x.box.left + x.box.right) / 2;
  const left = near.filter((x) => at(x) < centre).sort((p, q) => at(q) - at(p))[0];
  const right = near.filter((x) => at(x) > centre).sort((p, q) => at(p) - at(q))[0];
  if (!left && !right) return 'no control beside the header message';
  for (const x of [left, right].filter(Boolean)) {
    for (const px of [x.box.left + 2, at(x), x.box.right - 2]) {
      const hit = document.elementFromPoint(px, (x.box.top + x.box.bottom) / 2);
      if (!hit || !(hit === x.b || x.b.contains(hit))) {
        return \`a press on «\${(x.b.textContent || x.b.title || '').trim().slice(0, 24)}» at x \${Math.round(px)} reaches \${hit ? hit.tagName.toLowerCase() + (hit.id ? '#' + hit.id : '') : 'nothing'}\`;
      }
    }
  }
  return null;
})()` },
  // The status bar's counts take a press: the centre of each reaches it, not a page button laid over it (lead 10-14).
  { entry: 'index.html', after: 'loaded', rule: 'counts reachable', at: 'status-left', expr: `(() => {
  for (const id of ['exposed-rows', 'total-rows']) {
    const x = document.getElementById(id);
    if (!x || !x.getClientRects().length) return 'no #' + id + ' on the page';
    const r = x.getBoundingClientRect();
    if (r.width < 1) return 'the count #' + id + ' is ' + Math.round(r.width) + ' wide';
    const hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
    if (!hit || !(hit === x || x.contains(hit))) return 'a point on the count #' + id + ' reaches ' + (hit ? hit.tagName.toLowerCase() + (hit.id ? '#' + hit.id : '') : 'nothing');
  }
  return null;
})()` },
  { entry: 'index.html', after: 'loaded', rule: 'message title', expr: `(() => {
  const log = document.getElementById('performance-log');
  if (!log) return 'no header message on the page';
  const t = log.textContent;
  if (!t.trim()) return 'the header message is empty';
  if (getComputedStyle(log).pointerEvents === 'none') return 'the header message takes no pointer, so its title never shows';
  return log.title === t ? null : \`its title «\${log.title.slice(0, 30)}» is not its sentence «\${t.slice(0, 30)}»\`;
})()` },
];
// The open start picker takes a press: the centre of each of its controls reaches that control, not what lies under it
// (lead 10-13, 18997: the testbed's picker hung clipped under its panel - the point over its key box hit the scatter).
const PICKER_REACH = `(() => {
  const body = [...document.querySelectorAll('details.wk-barpop[open] > .wk-barpopbody')].find((b) => b.getClientRects().length);
  if (!body) return 'no open start picker';
  const parts = [...body.querySelectorAll('select, input, button')].filter((x) => x.getClientRects().length);
  if (!parts.length) return 'the open start picker shows no control';
  for (const x of parts) {
    const r = x.getBoundingClientRect();
    const hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
    if (!hit || !(hit === x || x.contains(hit))) {
      return 'a press on the picker ' + x.tagName.toLowerCase() + ' «' + (x.textContent || x.placeholder || x.value || '').trim().slice(0, 20)
        + '» reaches ' + (hit ? hit.tagName.toLowerCase() + (hit.className ? '.' + String(hit.className).split(' ')[0] : '') : 'nothing');
    }
  }
  return null;
})()`;
for (const entry of ['walk.html', 'testbed.html']) {
  CELLS.push({ entry, after: 'Add start opened', rule: 'picker reachable', at: 'wk-barpopbody', expr: PICKER_REACH });
}
// Every picker of the root part opens inside the screen and takes a press (lead 72b2d7f8f, owner 10-13 «x축 선언창
// 삐져나가서 안 보임»): each pill of the walked parts, then the start picker - its window's box inside the viewport, cut
// with a scroll of its own when it is cut, and the centre of each control it shows reaching that control.
const PICKERS_IN_VIEW = `(async () => {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
  const out = [];
  const check = (win, name) => {
    const r = win.getBoundingClientRect();
    if (r.left < -0.5 || r.top < -0.5 || r.right > vw + 0.5 || r.bottom > vh + 0.5) {
      return name + ' opens at ' + [r.left, r.top, r.right, r.bottom].map(Math.round).join(',') + ', past the ' + vw + 'x' + vh + ' screen';
    }
    if (win.scrollHeight > win.clientHeight + 1 && !/auto|scroll/.test(getComputedStyle(win).overflowY)) return name + ' is cut with no scroll of its own';
    for (const x of [...win.querySelectorAll('select, input, button')].filter((e) => e.getClientRects().length)) {
      const b = x.getBoundingClientRect();
      const cx = (b.left + b.right) / 2, cy = (b.top + b.bottom) / 2;
      if (cx < r.left || cx > r.right || cy < r.top || cy > r.bottom) continue;
      const hit = document.elementFromPoint(cx, cy);
      if (!hit || !(hit === x || x.contains(hit))) {
        return name + ': a press on ' + x.tagName.toLowerCase() + ' «' + (x.textContent || x.value || '').trim().slice(0, 20) + '» reaches '
          + (hit ? hit.tagName.toLowerCase() + (hit.className ? '.' + String(hit.className).split(' ')[0] : '') : 'nothing');
      }
    }
    return null;
  };
  const pills = [...document.querySelectorAll('.rb-panel .sf-pill')].filter((p) => p.getClientRects().length);
  if (!pills.length) return 'no pill drawn - the parts did not walk';
  const host = document.querySelector('.sf-pop-host');
  let opened = 0;
  for (const p of pills) {
    const name = 'the picker of «' + p.textContent.replace('▾', '').trim().slice(0, 24) + '»';
    p.click();
    await wait(300);
    if (!host || host.style.display === 'none' || !host.getClientRects().length) continue;
    opened += 1;
    const why = check(host, name);
    if (why) out.push(why);
    p.click();
    await wait(150);
  }
  if (!opened) out.push('no pill opened a picker');
  const pop = document.querySelector('details.wk-barpop');
  if (!pop) out.push('no start picker');
  else {
    pop.querySelector('summary').click();
    await wait(400);
    const body = pop.open ? pop.querySelector('.wk-barpopbody') : null;
    const why = body ? check(body, 'the start picker') : 'the start picker did not open';
    if (why) out.push(why);
    pop.open = false;
    await wait(150);
  }
  return out.length ? out.join(' | ') : null;
})()`;
// The right-most column's filter took its letter and the grid asked a read filtered by that column (lead 72b2d7f8f).
CELLS.push({ entry: 'index.html', after: 'right-most column filtered', rule: 'filter typed', at: 'ag-floating-filter', expr: `(() => {
  const t = window.__filterTyped;
  if (!t) return 'the right-most filter was never typed';
  if (t.why) return t.why;
  const box = [...document.querySelectorAll('.ag-floating-filter input')].find((i) => i.closest('[col-id]') && i.closest('[col-id]').getAttribute('col-id') === t.col);
  if (!box || box.value !== 'e') return 'the «' + t.col + '» filter box lost its letter';
  const asked = performance.getEntriesByType('resource').some((e) => e.startTime >= t.at && /\\/data\\?/.test(e.name)
    && decodeURIComponent(e.name).includes('"' + t.col + '"'));
  return asked ? null : 'the grid asked no read filtered by «' + t.col + '»';
})()` });
// The tooltip says a time as the grid does - no ISO «T … Z» (lead 10-14).
CELLS.push({ entry: 'testbed.html', after: 'tooltip over a cell', rule: 'time as shown', at: 'sf-tip', expr: `(() => {
  const tip = [...document.querySelectorAll('.sf-tip')].find((x) => x.getClientRects().length);
  if (!tip) return 'no tooltip over the cross table cell';
  const line = [...tip.children].map((x) => x.textContent).find((s) => s.startsWith('eventtime'));
  if (!line) return 'the tooltip says no eventtime: ' + tip.textContent.slice(0, 60);
  return /^eventtime: \\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}$/.test(line) ? null : 'the tooltip says «' + line + '»';
})()` });
// A picture inside its place with its ratio kept, a table's line one height, the map's cells filled (lead-board-14).
CELLS.push({ entry: 'testbed.html', after: 'images', rule: 'picture in its place', at: 'sf-thumb', expr: `(() => {
  const imgs = [...document.querySelectorAll('.sf-thumb__img')].filter((i) => i.getClientRects().length && i.naturalWidth > 0);
  if (!imgs.length) return 'no picture drawn in a table cell';
  for (const i of imgs) {
    const r = i.getBoundingClientRect();
    const box = i.closest('td').getBoundingClientRect();
    if (r.left < box.left - 1 || r.right > box.right + 1 || r.top < box.top - 1 || r.bottom > box.bottom + 1) return 'a picture out of its cell';
    if (Math.abs(r.width / r.height - i.naturalWidth / i.naturalHeight) > 0.1) return 'a picture ' + Math.round(r.width) + 'x' + Math.round(r.height) + ' of a ' + i.naturalWidth + 'x' + i.naturalHeight + ' one';
  }
  const lines = [...document.querySelectorAll('.sf-table--images tr')].filter((tr) => tr.querySelector('td'));
  if (lines.some((tr) => Math.abs(tr.getBoundingClientRect().height - 48) > 2)) return 'a line of the table of pictures not 48 px';
  // the map's cells: a picture in each of those big enough (16 px - image_thumb THUMB_MIN_PX), none asked under it
  const svg = document.querySelector('.tb-map__svg');
  if (!svg) return 'no map';
  const r = svg.getBoundingClientRect();
  const vb = svg.viewBox.baseVal;
  const cellPx = Math.min(r.width / vb.width, r.height / vb.height);
  const pics = svg.querySelectorAll('image').length;
  if (cellPx >= 17 && !pics) return 'cells of ' + Math.round(cellPx) + ' px with no picture';
  if (cellPx < 15 && pics) return 'cells of ' + Math.round(cellPx) + ' px drew pictures';
  return null;
})()` });
// Every picture fills its div after the window shrank and grew (lead 10-14: 40 x 44 left in a 280 x 179 panel).
CELLS.push({ entry: 'testbed.html', after: 'shrunk and grown', rule: 'picture fills its div', at: 'tb-plot', expr: `(() => {
  const plots = [...document.querySelectorAll('.tb-plot')].filter((x) => x.getClientRects().length);
  if (!plots.length) return 'no picture drawn';
  for (const plot of plots) {
    const canvas = plot.querySelector('canvas');
    const r = plot.getBoundingClientRect();
    if (!canvas) return 'a picture with no canvas';
    const c = canvas.getBoundingClientRect();
    if (Math.abs(c.width - r.width) > 2 || Math.abs(c.height - r.height) > 2) return 'a canvas ' + Math.round(c.width) + 'x' + Math.round(c.height) + ' in a ' + Math.round(r.width) + 'x' + Math.round(r.height) + ' picture';
  }
  return null;
})()` });
// A drop on a part's middle swaps the two (lead 10-14): Escape - nothing moves; the mark covers the whole part over its middle.
CELLS.push({ entry: 'testbed.html', after: 'parts swapped by a drop', rule: 'drop on a middle swaps', at: 'sf-drop', expr: `(() => {
  const s = window.__swapped;
  if (!s) return 'no drag made';
  if (s.afterEscape !== s.before) return 'Escape moved the parts: ' + s.before + ' -> ' + s.afterEscape;
  if (!s.escCovers || !s.covers) return 'the drop mark did not cover the part under the pointer';
  const want = s.before.split(',').map((id) => (id === 'scatter-1' ? 'table-1' : id === 'table-1' ? 'scatter-1' : id)).join(',');
  return s.after === want ? null : 'after the drop ' + s.after + ', not ' + want;
})()` });
// Each part's walks on the status line (owner 10-14 «행 걷기 + 값 걷기»): every part says its rows'
// walk (complete, or cached - the page's, lead-board-10c), and a part with a value walk says its slot's - none refused, none expired.
CELLS.push({ entry: 'testbed.html', after: 'walks on the status line', rule: 'walks said', at: 'sf-status', expr: `(() => {
  const all = window.__walkLine || [];
  if (!all.length) return 'no part activated';
  const rows = all.filter((p) => p.words.some((w) => /^Rows [0-9,]+ · (complete|cached)$/.test(w)));
  const values = all.filter((p) => p.words.some((w) => !w.startsWith('Rows ') && / · (complete|cached)$/.test(w)));
  const bad = all.flatMap((p) => p.words.filter((w) => /expired|refused/i.test(w)).map((w) => p.id + ': ' + w));
  if (bad.length) return bad.join('; ');
  if (rows.length < 2) return 'rows walk said by ' + rows.length + ' parts: ' + JSON.stringify(all);
  return values.length ? null : 'no value walk said: ' + JSON.stringify(all);
})()` });
// A column chip dragged onto another reorders the pill's columns - the hierarchy's levels follow (lead 10-14).
CELLS.push({ entry: 'testbed.html', after: 'columns reordered by a drag', rule: 'chips reorder columns', at: 'sf-pop__cols', expr: `(() => {
  const s = window.__chipOrder;
  if (!s) return 'no drag made';
  if (s.why) return s.why;
  return s.before === 'mat_type › y' && s.after === 'y › mat_type' && s.chips.join() === 'y,mat_type' ? null
    : 'before «' + s.before + '», after «' + s.after + '», chips ' + (s.chips || []).join(',');
})()` });
// The picker under its pill each time (lead 10-14): its left at the pill's, its top 4 under it - or flipped, its foot 4 above.
CELLS.push({ entry: 'testbed.html', after: 'pickers under their pills', rule: 'picker under its pill', at: 'sf-pop-host', expr: `(() => {
  const all = window.__pickPlaced || [];
  if (!all.length) return 'no pill picker opened';
  // its left at the pill's - or held 8 in from the right edge (fitUnder's shift); 4 under it - or flipped, 4 above
  const offs = all.filter((x) => x.why || (x.closed ? !x.slotGone : (!(Math.abs(x.dx) <= 1 || Math.abs(x.atRight - 8) <= 1) || !(Math.abs(x.below - 4) <= 1 || Math.abs(x.above - 4) <= 1))));
  return offs.length ? offs.slice(0, 6).map((off) => (off.why ? off.when + ': ' + off.why : off.closed ? off.kind + ' ' + off.when + ': closed though its pill stayed'
    : off.kind + ' ' + off.when + ': ' + off.dx + ' px from the pill\\'s left, ' + off.below + ' below it')).join(' | ') : null;
})()` });
// A table shows each cell's whole words - its columns as wide as their words, the table scrolling when wider than its
// area (lead 10-14: «SYN-CX-BW-0…» cut beside empty x · y).
CELLS.push({ entry: 'testbed.html', after: 'every kind', rule: 'table words whole', at: 'sf-table--rows', expr: `(() => {
  const cells = [...document.querySelectorAll('.sf-table--rows td, .sf-table--rows th')].filter((c) => c.getClientRects().length);
  if (!cells.length) return 'no table drawn';
  const cut = cells.find((c) => c.scrollWidth > c.clientWidth + 1);
  return cut ? '«' + cut.textContent.slice(0, 30) + '» ' + cut.scrollWidth + ' px of words in a ' + cut.clientWidth + ' px cell' : null;
})()` });
// A kind draws inside its area only (lead 10-14, the part frame standard): every shown element in a part's area inside
// the area's box - or inside a box between them that scrolls or cuts it.
CELLS.push({ entry: 'testbed.html', after: 'every kind', rule: 'kind inside its area', at: 'sf-frame__area', expr: `(() => {
  const areas = [...document.querySelectorAll('.sf-frame__area')].filter((a) => a.getClientRects().length);
  if (areas.length < 6) return 'only ' + areas.length + ' areas drawn';
  for (const area of areas) {
    const a = area.getBoundingClientRect();
    for (const e of area.querySelectorAll('*')) {
      if (!e.getClientRects().length) continue;
      let box = a;
      for (let up = e.parentElement; up && up !== area; up = up.parentElement) {
        if (/auto|scroll|hidden|clip/.test(getComputedStyle(up).overflow)) { box = up.getBoundingClientRect(); break; }
      }
      const r = e.getBoundingClientRect();
      const inside = (x) => r.left >= x.left - 1 && r.top >= x.top - 1 && r.right <= x.right + 1 && r.bottom <= x.bottom + 1;
      if (box !== a && !inside(box)) continue;
      if (!inside(a)) {
        const kind = (area.closest('.sf-part') || {}).getAttribute ? area.closest('.sf-part').getAttribute('data-kind') : '?';
        return kind + ': ' + e.tagName.toLowerCase() + (e.className && e.className.baseVal === undefined ? '.' + String(e.className).split(' ')[0] : '')
          + ' at ' + [r.left, r.top, r.right, r.bottom].map(Math.round) + ' outside its area ' + [a.left, a.top, a.right, a.bottom].map(Math.round);
      }
    }
  }
  return null;
})()` });
for (const after of ['walked at the edge', 'light theme']) {
  CELLS.push({ entry: 'testbed.html', after, rule: 'pickers in view', at: 'sf-pop-host', expr: PICKERS_IN_VIEW });
}
// The Ledger cell's first word whole at the column's own width (lead 10-12): the changed row starts «changed», the row no
// world read took starts «Not yet» though a world was not read - the word's letters inside the cell, not under the ellipsis.
CELLS.push({ entry: 'index.html', after: 'loaded', rule: 'ledger word first', at: 'ledger-cell', expr: `(async () => {
  const scrollers = [...document.querySelectorAll('.ag-body-horizontal-scroll-viewport, .ag-center-cols-viewport')];
  const was = scrollers.map((s) => s.scrollLeft);
  scrollers.forEach((s) => { s.scrollLeft = s.scrollWidth; s.dispatchEvent(new Event('scroll')); });
  await new Promise((r) => setTimeout(r, 400));
  try {
    const cells = [...document.querySelectorAll('.ag-cell[col-id="#ledger"]')].filter((c) => c.getClientRects().length);
    if (!cells.length) return 'no Ledger cell drawn';
    for (const [word, what] of [['changed', 'the changed row'], ['Not yet', 'the row no world read took']]) {
      const c = cells.find((x) => x.textContent.trim().startsWith(word));
      if (!c) return 'Ledger: ' + what + ' does not start with ' + word + ' (' + cells.slice(0, 3).map((x) => x.textContent.trim()).join(' | ') + ')';
      const walker = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node && !node.data.includes(word)) node = walker.nextNode();
      if (!node) return 'Ledger: no text holds ' + word;
      const range = document.createRange(), at = node.data.indexOf(word);
      range.setStart(node, at); range.setEnd(node, at + word.length);
      const cr = c.getBoundingClientRect(), end = cr.right - parseFloat(getComputedStyle(c).paddingRight);
      const r = range.getBoundingClientRect();
      if (r.right > end + 0.5) return 'Ledger: ' + word + ' cut in a ' + Math.round(cr.width) + ' px cell, its letters ' + Math.round(r.right - end) + ' px past the text';
    }
    return null;
  } finally { scrollers.forEach((s, i) => { s.scrollLeft = was[i]; s.dispatchEvent(new Event('scroll')); }); }
})()` });
// The Retroactive tab's contents (owner 10-11 R): a chip a card, and a press brings that card to the tab's top - the last
// ones as far as the tab scrolls; the header's own press (folding) not taken.
CELLS.push({ entry: 'admin.html', after: 'Retroactive', rule: 'contents', at: 'retroactive-sub', expr: `(() => {
  const chips = [...document.querySelectorAll('#retroactive-sub .retro-toc')];
  const cards = [...document.querySelectorAll('#retroactive-body article.retro-op')];
  if (!cards.length) return 'no card on the tab';
  if (chips.length !== cards.length) return chips.length + ' chips for ' + cards.length + ' cards';
  const wrap = document.getElementById('retroactive-tab-wrapper');
  for (const chip of chips) {
    chip.click();
    const card = cards.find((c) => c.dataset.op === chip.dataset.op);
    if (!card) return '«' + chip.textContent + '» has no card';
    const off = card.getBoundingClientRect().top - wrap.getBoundingClientRect().top;
    const atEnd = wrap.scrollTop >= wrap.scrollHeight - wrap.clientHeight - 1;
    if (Math.abs(off) > 2 && !(atEnd && off > 0)) return '«' + chip.textContent + '» leaves its card ' + Math.round(off) + ' px from the top';
  }
  wrap.scrollTop = 0;
  return null;
})()` });
// The walk table as the lead reviewed it (34d91c09d gate), asked in each theme after its two steps.
const SIDE_CELLS = [
  ['Δ in view', `(() => {
  // The first: Wide's later groups scroll (lead 10-11 W).
  const heads = [...document.querySelectorAll('.wk-sides thead th')].filter((th) => th.textContent.trim().startsWith('Δ')).slice(0, 1);
  if (!heads.length) return 'no Δ column drawn';
  for (const th of heads) {
    const t = th.closest('table').getBoundingClientRect(), r = th.getBoundingClientRect(), edge = Math.min(t.right, innerWidth);
    if (r.right > edge + 1) return \`«\${th.textContent.trim()}» ends \${Math.round(r.right - edge)} px past what its table shows\`;
  }
  return null;
})()`],
  ['node in view', `(() => {
  const cells = [...document.querySelectorAll('.wk-sides tbody tr:first-child td.wk-centre')];
  if (!cells.length) return 'no node cell drawn';
  for (const td of cells) {
    const t = td.closest('table').getBoundingClientRect(), r = td.getBoundingClientRect();
    if (r.left < Math.max(t.left, 0) - 1 || r.right > Math.min(t.right, innerWidth) + 1) {
      return \`the node cell «\${td.textContent.trim().slice(0, 24)}» stands at \${Math.round(r.left)}..\${Math.round(r.right)} px, its table shows \${Math.round(t.left)}..\${Math.round(Math.min(t.right, innerWidth))}\`;
    }
  }
  return null;
})()`],
  ['sign colours', `(() => {
  const cs = (sel) => { const e = document.querySelector(sel); return e ? getComputedStyle(e) : null; };
  const p = cs('.wk-sides th.wk-sidehead.wk-plus'), m = cs('.wk-sides th.wk-sidehead.wk-minus');
  const pc = cs('.wk-sides td.wk-plus'), mc = cs('.wk-sides td.wk-minus');
  if (!p || !m || !pc || !mc) return 'a sign band or a sign cell not drawn';
  if (p.color === m.color) return \`both bands say their sign in \${p.color}\`;
  if (p.backgroundColor === m.backgroundColor) return \`both bands on \${p.backgroundColor}\`;
  if (p.boxShadow === 'none' || m.boxShadow === 'none') return 'a band with no strip under it';
  if (pc.backgroundColor === mc.backgroundColor) return \`both sides' cells on \${pc.backgroundColor}\`;
  return null;
})()`],
  ['− side in view', `(() => {
  const firsts = [...document.querySelectorAll('.wk-sides thead tr:last-child th.wk-minus')].filter((th) => {
    const prev = th.previousElementSibling;
    return !prev || !prev.classList.contains('wk-minus');
  }).slice(0, 1);
  if (!firsts.length) return 'no − column drawn';
  for (const th of firsts) {
    const t = th.closest('table').getBoundingClientRect(), r = th.getBoundingClientRect(), edge = Math.min(t.right, innerWidth);
    if (r.left < Math.max(t.left, 0) - 1 || r.right > edge + 1) return \`the − side's first column «\${th.textContent.trim()}» stands at \${Math.round(r.left)}..\${Math.round(r.right)} px, its table shows \${Math.round(t.left)}..\${Math.round(edge)}\`;
  }
  return null;
})()`],
  // A side that did not reach a row says missing in each of its cells, none «—» (lead 10-11 W, the mockup B-ㄱ).
  ['missing each', `(() => {
  let seen = 0;
  for (const tr of document.querySelectorAll('.wk-sides tbody tr[data-row-id]')) {
    for (const side of ['wk-plus', 'wk-minus']) {
      const cells = [...tr.children].filter((c) => c.classList.contains(side));
      const missing = cells.filter((c) => c.classList.contains('wk-missing')).length;
      if (missing && missing < cells.length) return 'row «' + tr.getAttribute('data-row-id') + '» says missing in ' + missing + ' of its ' + cells.length + ' ' + side + ' cells';
      seen += missing;
    }
  }
  return seen ? null : 'no missing cell drawn';
})()`],
];
// The walk page's spacing, heights and type (lead 18da45b73, owner «간격 정리 넣어»): read by CSS Typed OM, where an auto
// margin stays «auto» (the resolved style says the free space in px). The graph's canvas, svg drawings and the account
// badge and the branch picker (shared parts, their own styles) are not the walk page's.
const WALK_PAGE = `const page = document.querySelector('.wk-page');
  const mine = (el) => el.getClientRects().length && !el.closest('svg, .sg-canvas, .acct-host, .branch-picker');
  const tally = (bad, key, el) => { const at = bad.get(key) || { n: 0, el }; at.n += 1; bad.set(key, at); };
  const said = (bad) => [...bad].map(([k, x]) => k + ' x' + x.n + ' (' + x.el.tagName.toLowerCase()
    + (typeof x.el.className === 'string' && x.el.className ? '.' + x.el.className.split(' ')[0] : '') + ')').join(' · ');`;
const WALK_LOOK = [
  ['spacing tokens', `(() => { ${WALK_PAGE}
  if (!page) return 'no walk page';
  const TOKENS = [0, 3.4, 6.8, 10.2, 13.6, 20.4, 27.2];
  const bad = new Map();
  for (const el of [page, ...page.querySelectorAll('*')]) {
    if (!mine(el)) continue;
    const map = el.computedStyleMap();
    for (const prop of ['padding-top', 'padding-right', 'padding-bottom', 'padding-left', 'margin-top', 'margin-right', 'margin-bottom',
      'margin-left', 'row-gap', 'column-gap']) {
      const v = map.get(prop);
      if (!v || v.unit !== 'px' || TOKENS.some((t) => Math.abs(v.value - t) < 0.05)) continue;
      tally(bad, prop.replace(/-(top|right|bottom|left)$/, '') + ' ' + Number(v.value.toFixed(2)) + 'px', el);
    }
  }
  return bad.size ? 'off the --space-* grid: ' + said(bad) : null;
})()`],
  ['two heights', `(() => { ${WALK_PAGE}
  if (!page) return 'no walk page';
  const bad = new Map();
  for (const el of page.querySelectorAll('button, select, input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"])')) {
    if (!mine(el)) continue;
    const h = Math.round(el.getBoundingClientRect().height);
    if (h !== 44 && h !== 28) tally(bad, h + 'px', el);
  }
  return bad.size ? 'a control neither 44 nor 28 px high: ' + said(bad) : null;
})()`],
  // Parts stacked one over another touch nowhere (lead 348310aee: a section's NEXT, + Column and table 0 px apart):
  // two blocks side by side in a box, the lower one's top on the upper one's bottom, no line between - red.
  ['stacked gaps', `(() => { ${WALK_PAGE}
  if (!page) return 'no walk page';
  const bad = new Map();
  for (const box of [page, ...page.querySelectorAll('*')]) {
    if (!mine(box) || /^(TABLE|THEAD|TBODY|TR|TD|TH|SELECT|svg)$/i.test(box.tagName)) continue;
    const kids = [...box.children].filter((k) => mine(k) && !getComputedStyle(k).display.startsWith('inline')
      && getComputedStyle(k).position !== 'absolute');
    for (let i = 1; i < kids.length; i += 1) {
      const up = kids[i - 1].getBoundingClientRect(), down = kids[i].getBoundingClientRect();
      const across = Math.min(up.right, down.right) - Math.max(up.left, down.left) > 1;
      if (!across || down.top < up.bottom - 1 || down.top - up.bottom >= 0.5) continue;
      const lined = parseFloat(getComputedStyle(kids[i - 1]).borderBottomWidth) || parseFloat(getComputedStyle(kids[i]).borderTopWidth);
      if (!lined) tally(bad, kids[i - 1].tagName.toLowerCase() + '.' + String(kids[i - 1].className).split(' ')[0] + ' / '
        + kids[i].tagName.toLowerCase() + '.' + String(kids[i].className).split(' ')[0], kids[i]);
    }
  }
  return bad.size ? 'stacked parts with no gap: ' + said(bad) : null;
})()`],
  // W (lead 10-11 addendum 9, the canon ui-design-system §0 · §3): the walk screen's spaces and lines, measured.
  ['S2 section spaces', `(() => { ${WALK_PAGE}
  if (!page) return 'no walk page';
  const T = { s2: 6.8, s5: 20.4 };
  const secs = [...page.querySelectorAll('.wk-secs > .wk-sec')].filter(mine);
  for (let i = 1; i < secs.length; i += 1) {
    const gap = secs[i].getBoundingClientRect().top - secs[i - 1].getBoundingClientRect().bottom;
    if (Math.abs(gap - T.s5) > 0.6) return 'sections ' + Math.round(gap * 10) / 10 + ' px apart, not --space-5';
  }
  for (const sec of secs) {
    const bar = sec.querySelector(':scope > .wk-secbar');
    const next = bar && bar.nextElementSibling;
    if (!bar || !next) continue;
    const gap = next.getBoundingClientRect().top - bar.getBoundingClientRect().bottom;
    if (Math.abs(gap - T.s2) > 0.6) return 'a toolbar ' + Math.round(gap * 10) / 10 + ' px over what follows, not --space-2';
    const cg = parseFloat(getComputedStyle(bar).columnGap);
    if (Math.abs(cg - T.s2) > 0.05) return 'the parts of a toolbar ' + cg + ' px apart, not --space-2';
  }
  for (const el of page.querySelectorAll('.wk-sec, .wk-secs, .wk-secbar, .wk-result')) {
    const cs = getComputedStyle(el);
    if (parseFloat(cs.marginTop) || parseFloat(cs.marginBottom)) return el.className.split(' ')[0] + ' keeps a margin of its own';
  }
  return secs.length ? null : 'no section drawn';
})()`],
  ['S3 table cells', `(() => { ${WALK_PAGE}
  if (!page) return 'no walk page';
  const cells = [...page.querySelectorAll('.wk-table td, .wk-table th')].filter(mine).filter((c) => !c.classList.contains('wk-check'));
  if (!cells.length) return 'no table cell drawn';
  for (const c of cells) {
    const cs = getComputedStyle(c);
    if (Math.abs(parseFloat(cs.paddingTop) - 3.4) > 0.05 || Math.abs(parseFloat(cs.paddingLeft) - 6.8) > 0.05) {
      return 'a cell padded ' + cs.paddingTop + ' ' + cs.paddingLeft + ', not --space-1 --space-2';
    }
  }
  for (const td of page.querySelectorAll('.wk-table td.wk-num')) {
    const cs = getComputedStyle(td);
    if (cs.textAlign !== 'right' || !cs.fontVariantNumeric.includes('tabular-nums')) return 'a number cell not right and tabular';
  }
  for (const table of page.querySelectorAll('table.wk-wide')) {
    const first = table.querySelector('tbody tr[data-row-id]');
    if (!first) continue;
    const lefts = [...first.children].map((c) => Math.round(c.getBoundingClientRect().left));
    for (const th of table.querySelectorAll('th.wk-stephead')) {
      const left = Math.round(th.getBoundingClientRect().left);
      if (!lefts.some((x) => Math.abs(x - left) <= 1)) return 'the group «' + th.textContent.trim().slice(0, 30) + '» starts off the left edge of its cells';
    }
  }
  return null;
})()`],
  ['S4 one row height', `(() => { ${WALK_PAGE}
  if (!page) return 'no walk page';
  for (const table of page.querySelectorAll('table.wk-wide')) {
    const rows = [...table.querySelectorAll('tbody tr[data-row-id]')].filter(mine);
    const hs = [...new Set(rows.map((r) => Math.round(r.getBoundingClientRect().height)))];
    if (hs.length > 1) return 'rows ' + hs.join(' · ') + ' px high in one table';
    // Two lines high: a value line and its source line, each at most --space-5 (a «+N» tag or a copy button rides
    // inside its line), and the cell's padding.
    const s5 = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--space-5'));
    for (const r of rows) {
      const cs = getComputedStyle(r.querySelector('td:not(.wk-check)') || r.firstElementChild);
      const cap = 2 * s5 + parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom) + 1.5;
      const h = r.getBoundingClientRect().height;
      if (h > cap) return 'a row ' + h.toFixed(1) + ' px high, two lines are ' + cap.toFixed(1);
    }
  }
  return null;
})()`],
  ['S5 one left edge', `(() => { ${WALK_PAGE}
  if (!page) return 'no walk page';
  const head = page.querySelector('.wk-mainhead');
  const bar = page.querySelector('.wk-secbar');
  const table = page.querySelector('.wk-sec > .wk-tablebox > .wk-table');
  if (!head || !bar || !table) return 'no head, toolbar or table drawn';
  const xs = [head, bar, table].map((e) => Math.round(e.getBoundingClientRect().left));
  return Math.max(...xs) - Math.min(...xs) > 1 ? 'the head, a toolbar and its table start at ' + xs.join(' · ') + ' px' : null;
})()`],
  ['S6 no clipped letters', `(() => { ${WALK_PAGE}
  if (!page) return 'no walk page';
  const bad = new Map();
  for (const el of page.querySelectorAll('.wk-main *')) {
    if (!mine(el) || el.closest('[data-clip-ok]')) continue;
    const texts = [...el.childNodes].filter((n) => n.nodeType === 3 && n.textContent.trim());
    if (!texts.length) continue;
    const box = el.getBoundingClientRect();
    const r = document.createRange();
    r.selectNodeContents(el);
    const t = r.getBoundingClientRect();
    if (t.width && (t.right > box.right + 0.5 || t.left < box.left - 0.5)) tally(bad, '«' + el.textContent.trim().slice(0, 16) + '»', el);
  }
  return bad.size ? 'letters past their box: ' + said(bad) : null;
})()`],
  ['three type sizes', `(() => { ${WALK_PAGE}
  if (!page) return 'no walk page';
  const bad = new Map();
  for (const el of [page, ...page.querySelectorAll('*')]) {
    if (!el.getClientRects().length || el.closest('.sg-canvas, .acct-host, .branch-picker')) continue;
    // Letters: a text of its own, a select, a text input; a checkbox or an icon button has none.
    const own = el.tagName === 'SELECT' || (el.tagName === 'INPUT' && !/^(checkbox|radio|hidden)$/.test(el.type))
      || [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const f = parseFloat(getComputedStyle(el).fontSize);
    if (![13, 14, 16].some((t) => Math.abs(f - t) < 0.05)) tally(bad, Number(f.toFixed(2)) + 'px', el);
  }
  return bad.size ? 'letters neither 13, 14 nor 16 px: ' + said(bad) : null;
})()`],
];
for (const after of ['Graph', 'Side by side, light', 'Trend of a value cell', 'Long']) {
  // The S cells read the table: none is drawn on the graph.
  for (const [rule, expr] of WALK_LOOK) if (!(after === 'Graph' && /^S\d/.test(rule))) CELLS.push({ entry: 'walk.html', after, rule, at: 'wk-page', expr });
}
// The Route panel's walked ways (lead 10-12): each line whole in its row, and a wrapped line's lines and the rows apart.
CELLS.push({ entry: 'walk.html', after: 'Route walked', rule: 'route whole', at: 'wk-route', expr: `(() => {
  const lines = [...document.querySelectorAll('.wk-route .wk-pathchain')].filter((e) => e.getClientRects().length);
  if (!lines.length) return 'no walked route drawn';
  for (const l of lines) {
    const row = l.closest('.wk-path').getBoundingClientRect(), r = l.getBoundingClientRect();
    if (l.scrollWidth > l.clientWidth + 1 || l.scrollHeight > l.clientHeight + 1 || r.bottom > row.bottom + 0.5 || r.right > row.right + 0.5) {
      return 'wk-route «' + l.textContent.slice(0, 40) + '…» cut: ' + l.scrollWidth + ' of ' + l.clientWidth + ' px wide';
    }
  }
  return null;
})()` });
CELLS.push({ entry: 'walk.html', after: 'Route walked', rule: 'route lines apart', at: 'wk-route', expr: `(() => {
  const lines = [...document.querySelectorAll('.wk-route .wk-pathchain')].filter((e) => e.getClientRects().length);
  if (!lines.length) return 'no walked route drawn';
  for (const l of lines) {
    const cs = getComputedStyle(l), lh = parseFloat(cs.lineHeight) / parseFloat(cs.fontSize);
    if (!(lh >= 1.2)) return 'wk-route the lines of a way ' + lh.toFixed(2) + ' apart, not 1.2';
  }
  const rows = [...document.querySelectorAll('.wk-route')].filter((e) => e.getClientRects().length);
  for (let i = 1; i < rows.length; i += 1) {
    const gap = rows[i].getBoundingClientRect().top - rows[i - 1].getBoundingClientRect().bottom;
    if (gap < 3.4 - 0.5) return 'wk-route rows ' + gap.toFixed(1) + ' px apart';
  }
  return null;
})()` });
// The basket stays at the result's foot while the table scrolls, and never covers the last row (W addendum 3, S5).
CELLS.push({ entry: 'walk.html', after: 'A row ticked mid-table', rule: 'basket at the foot', at: 'wk-page', expr: `(() => {
  const main = document.querySelector('.wk-main'), basket = document.querySelector('.wk-main .wk-marked');
  if (!basket) return 'no basket';
  const chips = basket.querySelectorAll('[data-marked]').length, ticked = document.querySelectorAll('input[data-row]:checked').length;
  if (chips !== ticked) return chips + ' chips for ' + ticked + ' rows checked';
  const was = main.scrollTop;
  main.scrollTop = 0;
  const stuck = basket.getBoundingClientRect().bottom <= main.getBoundingClientRect().bottom + 1
    && basket.getBoundingClientRect().bottom >= main.getBoundingClientRect().bottom - main.clientHeight * 0.5;
  main.scrollTop = main.scrollHeight;
  const rows = [...document.querySelectorAll('.wk-main table.wk-table tbody tr')].filter((r) => r.getClientRects().length);
  const last = rows[rows.length - 1];
  const covered = last && last.getBoundingClientRect().bottom > basket.getBoundingClientRect().top + 0.5;
  main.scrollTop = was;
  if (!stuck) return 'the basket is not at the foot of the result box while it is scrolled to the top';
  if (covered) return 'the basket covers the last row';
  return null;
})()` });
CELLS.push({ entry: 'walk.html', after: 'A row ticked mid-table', rule: 'place kept', at: 'wk-page', expr: `(() => {
  const was = window.__place, main = document.querySelector('.wk-main'), table = document.querySelector('.wk-sec table.wk-wide');
  if (!was || !was.ticked || !was.top) return 'no row ticked mid-table (' + JSON.stringify(was) + ')';
  if (main.scrollTop !== was.top || table.scrollLeft !== was.left) return 'scrolled ' + was.top + ' · ' + was.left + ', after the tick ' + main.scrollTop + ' · ' + table.scrollLeft;
  return null;
})()` });
// A cell B reached wears its legend chip's colour, not its side's band (lead 10-11, the W 1 regression).
CELLS.push({ entry: 'walk.html', after: 'Control · B', rule: 'control colours', at: 'wk-page', expr: `(() => {
  const cells = [...document.querySelectorAll('table.wk-wide td.is-ctl-ab, table.wk-wide td.is-ctl-b')];
  if (!cells.length) return 'no cell B reached';
  for (const td of cells) {
    const kind = td.classList.contains('is-ctl-ab') ? 'ab' : 'b';
    const chip = document.querySelector('.wk-reachedn.is-ctl-' + kind);
    const want = chip ? getComputedStyle(chip).backgroundColor : '(no legend chip)';
    const got = getComputedStyle(td).backgroundColor;
    if (got !== want) return 'a ' + (kind === 'ab' ? 'A + B' : 'B only') + ' cell ' + got + ', its legend ' + want;
  }
  return null;
})()` });
// Node, Δ and the − side's first column in the first screen are asked at the sizes the lead named (34d91c09d (나);
// 10-10 after 517eb6c2c, the demo pair): at 1280 the table's box is narrower than node, Δ and a − column together.
const FIRST_SCREEN = ['1568x775', '1896x907', '1280x720'];
for (const after of ['Side by side, dark', 'Side by side, light']) {
  for (const [rule, expr] of SIDE_CELLS) {
    CELLS.push({ entry: 'walk.html', after, rule, at: 'wk-sides', expr, ...(/in view$/.test(rule) ? { sizes: FIRST_SCREEN } : {}) });
  }
}
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.json': 'application/json',
  '.png': 'image/png', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.txt': 'text/plain', '.ico': 'image/x-icon' };
const sleep = (ms) => new Promise((ok) => setTimeout(ok, ms));

// The temp folders go only after the verdict line, and one that will not go says so and changes nothing (lead 10-13:
// a killed Chrome's children still held its cache, and the EBUSY thrown in a timer between two mutants ended the run
// before its ASSERTIONS line). Every run's folders are its own (mkdtempSync).
const folders = [];
function removeFolder(dir, what) {
  try { rmSync(dir, { recursive: true, force: true }); } catch (err) { console.log(`${what} folder not removed: ${dir} ${err.code || err.message}`); }
}

async function openChrome() {
  if (!existsSync(CHROME)) throw new Error(`no Chrome at ${CHROME} - the screens cannot be opened`);
  const port = 9300 + Math.floor(Math.random() * 500);
  const profile = mkdtempSync(path.join(tmpdir(), 'screens-'));
  folders.push(profile);
  const proc = spawn(CHROME, ['--headless=new', '--hide-scrollbars', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
    '--window-size=1920,950', 'about:blank'], { stdio: 'ignore' });
  let target;
  for (let i = 0; i < 75 && !target; i += 1) {
    await sleep(200);
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page'); } catch { /* not up yet */ }
  }
  if (!target) { proc.kill(); throw new Error('Chrome did not answer on its DevTools port'); }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((ok) => ws.addEventListener('open', ok));
  let id = 0;
  const waiting = new Map();
  const handlers = [];
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(e.data);
    if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); return; }
    for (const h of handlers) h(m);
  });
  const send = (method, params = {}) => new Promise((ok) => { id += 1; waiting.set(id, ok); ws.send(JSON.stringify({ id, method, params })); })
    .then((m) => { if (m.error) throw new Error(`${method}: ${m.error.message}`); return m.result; });
  const close = () => { try { ws.close(); } catch { /* gone */ } proc.kill(); };
  return { send, on: (h) => handlers.push(h), close };
}

// One Chrome page that serves `dist` and the answers; `log` collects what was refused or unanswered.
async function servePage(chrome, dist) {
  const log = { missing: new Set(), refused: [], left: [], thrown: [], outside: new Set(), last: Date.now(), opening: false };
  chrome.on(async (m) => {
    if (m.method === 'Page.javascriptDialogOpening') { chrome.send('Page.handleJavaScriptDialog', { accept: false }).catch(() => {}); return; }
    if (m.method === 'Runtime.exceptionThrown') { log.thrown.push((m.params.exceptionDetails.exception || {}).description || m.params.exceptionDetails.text); return; }
    if (m.method !== 'Fetch.requestPaused') return;
    const { requestId, request, resourceType } = m.params;
    const u = new URL(request.url);
    log.last = Date.now();
    const reply = (status, type, body) => chrome.send('Fetch.fulfillRequest', { requestId, responseCode: status,
      responseHeaders: [{ name: 'Content-Type', value: type }], body: Buffer.from(body).toString('base64') }).catch(() => {});
    if (u.origin !== ORIGIN) {
      log.outside.add(u.origin);
      if (request.method === 'GET') chrome.send('Fetch.continueRequest', { requestId }).catch(() => {});
      else chrome.send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }).catch(() => {});
      return;
    }
    if (request.method !== 'GET' && request.method !== 'HEAD') { log.refused.push(`${request.method} ${u.pathname}`); chrome.send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }).catch(() => {}); return; }
    if (resourceType === 'Document') {
      if (!log.opening) { log.left.push(u.pathname + u.search); reply(204, 'text/plain', ''); return; }
      log.opening = false;
    }
    const file = path.join(dist, decodeURIComponent(u.pathname));
    if (path.extname(u.pathname) && existsSync(file)) { reply(200, MIME[path.extname(file)] || 'application/octet-stream', readFileSync(file)); return; }
    if (resourceType === 'Other' && u.pathname === '/favicon.ico') { reply(404, 'text/plain', ''); return; }
    if (u.pathname === '/api/image') { reply(200, 'image/png', PHOTO_PNG); return; }
    const a = answerOf(u);
    if (!a) { log.missing.add(u.pathname + u.search); reply(404, 'application/json', JSON.stringify({ detail: 'no answer in screens_answers.json.gz' })); return; }
    // An answer captured with no body (a 204) is an empty one - not a crash of the whole run.
    reply(a.status, a.type || 'application/json', typeof a.body === 'string' ? a.body : a.body === undefined ? '' : JSON.stringify(a.body));
  });
  await chrome.send('Page.enable');
  await chrome.send('Runtime.enable');
  await chrome.send('Fetch.enable', { patterns: [{ urlPattern: '*', requestStage: 'Request' }] });
  await chrome.send('Page.addScriptToEvaluateOnNewDocument', { source: `try { localStorage.setItem('assy.adminToken', '${TOKEN}'); } catch (e) {}` });
  return log;
}

const evaluate = async (chrome, expression) => {
  const r = await chrome.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(`in page: ${(r.exceptionDetails.exception || {}).description || r.exceptionDetails.text}`);
  return r.result.value;
};
// Quiet: no request for `quiet` ms (a poll may keep coming; `most` caps the wait), then the fonts.
async function settle(chrome, log, quiet = 700, most = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < most && Date.now() - log.last < quiet) await sleep(100);
  await evaluate(chrome, 'document.fonts.ready.then(() => true)');
}

// ---- in the page: window.__screens = { measure, openNext, close }. Lines are {rule, path, what}.
function screensLib(TOL) {
  const css = (el) => getComputedStyle(el);
  const shown = (el) => {
    if (!el || !el.isConnected) return false;
    const s = css(el);
    if (s.display === 'none' || s.visibility !== 'visible' || Number(s.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const pathOf = (el) => {
    const parts = [];
    for (let e = el; e && e !== document.body && parts.length < 4; e = e.parentElement) {
      let p = e.tagName.toLowerCase();
      if (e.id) { parts.unshift(`${p}#${e.id}`); break; }
      const cls = [...e.classList].slice(0, 2).join('.');
      if (cls) p += `.${cls}`;
      parts.unshift(p);
    }
    return parts.join(' > ');
  };
  const clips = (s) => /hidden|clip/.test(s.overflowX) || /hidden|clip/.test(s.overflowY);
  const scrolls = (s) => /auto|scroll/.test(s.overflowX) || /auto|scroll/.test(s.overflowY);
  const ownText = (el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
  const hasText = (el) => ownText(el) || [...el.querySelectorAll('*')].some(ownText);
  const label = (el) => (el.textContent || el.getAttribute('aria-label') || el.title || '').trim().replace(/\s+/g, ' ').slice(0, 30);
  const wait = (ms) => new Promise((ok) => setTimeout(ok, ms));
  const textBeyond = (el) => {
    const b = el.getBoundingClientRect();
    const k = el.offsetWidth ? b.width / el.offsetWidth : 1;
    const left = b.left + el.clientLeft * k, top = b.top + el.clientTop * k;
    const right = left + el.clientWidth * k, bottom = top + el.clientHeight * k;
    let dx = 0, dy = 0;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.textContent.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(n);
      for (const r of range.getClientRects()) {
        if (!r.width) continue;
        dx = Math.max(dx, r.right - right, left - r.left);
        dy = Math.max(dy, r.bottom - bottom, top - r.top);
      }
    }
    return [dx, dy];
  };
  const readerOnly = (el, s) => el.clientWidth <= 1 || el.clientHeight <= 1 || (s.clip && s.clip !== 'auto');

  function measure(scopeSel) {
    const lines = [];
    const W = innerWidth, H = innerHeight;
    const scope = scopeSel ? document.querySelector(scopeSel) : document.body;
    if (!scope) return lines;
    const all = [scope, ...scope.querySelectorAll('*')].filter(shown);
    for (const el of all) {
      const s = css(el);
      if (s.display === 'inline' || s.display === 'contents' || !clips(s) || scrolls(s) || el.closest('[data-clip-ok]') || !hasText(el)) continue;
      if (readerOnly(el, s)) continue;
      if (el.scrollWidth - el.clientWidth <= 1 && el.scrollHeight - el.clientHeight <= 1) continue;
      // Held more than it shows; cut is where a glyph's box crosses the box it is drawn in (screen px, any zoom).
      const [dx, dy] = textBeyond(el);
      if (dx > 1 || dy > 1) {
        lines.push({ rule: 'clip', path: pathOf(el), what: [dx > 1 && `${Math.round(dx)} px of text past its side`, dy > 1 && `${Math.round(dy)} px past its top or bottom`]
          .filter(Boolean).join(', ') + `: «${el.textContent.trim().replace(/\s+/g, ' ').slice(0, 40)}»` });
      }
    }
    if (!scopeSel) {
      const sw = document.scrollingElement.scrollWidth - W;
      if (sw > 1) lines.push({ rule: 'overflow', path: 'page', what: `scrolls sideways by ${sw} px` });
    }
    const inBox = (el) => {
      for (let e = el.parentElement; e && e !== document.body && e !== document.documentElement; e = e.parentElement) {
        const s = css(e);
        if (clips(s) || scrolls(s)) return true;
      }
      return false;
    };
    const off = [];
    for (const el of all) {
      if (off.some((o) => o.contains(el)) || inBox(el) || readerOnly(el, css(el))) continue;
      const r = el.getBoundingClientRect();
      const placed = /fixed|absolute/.test(css(el).position);
      const by = Math.max(-r.left, r.right - W, placed ? r.bottom - H : 0, placed ? -r.top : 0);
      if (by > 1) { off.push(el); lines.push({ rule: 'overflow', path: pathOf(el), what: `${Math.round(by)} px off the screen` }); }
    }
    const bad = /\[object [A-Za-z]+\]|\bundefined\b|\bNaN\b/;
    const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const m = n.textContent.match(bad);
      if (m && shown(n.parentElement)) lines.push({ rule: 'text', path: pathOf(n.parentElement), what: `says «${m[0]}»` });
    }
    for (const el of scope.querySelectorAll('input, textarea')) {
      const m = String(el.value || '').match(bad);
      if (m && shown(el)) lines.push({ rule: 'text', path: pathOf(el), what: `holds «${m[0]}»` });
    }
    // size: a button against the other items of its line - the line is the button's bar (its widest ancestor still
    // one line high): its other controls by their box, or, when it stands alone among words, the words by their letters
    // (a flex row stretches a text box to the button beside it). Odd: half again taller, its letters no larger.
    // A button with no words is an icon, the size of its icon.
    const isButton = (e) => e.matches('button, [role="button"]');
    const isControl = (e) => e.matches('button, [role="button"], input, select, textarea') || (e.matches('a[href]') && css(e).display !== 'inline');
    const median = (xs) => xs.sort((x, y) => x - y)[Math.floor(xs.length / 2)];
    const textBox = (el) => {
      let top = Infinity, bottom = -Infinity;
      for (const n of el.childNodes) {
        if (n.nodeType !== 3 || !n.textContent.trim()) continue;
        const range = document.createRange();
        range.selectNodeContents(n);
        const r = range.getBoundingClientRect();
        if (r.height) { top = Math.min(top, r.top); bottom = Math.max(bottom, r.bottom); }
      }
      return bottom > top ? { top, bottom, height: bottom - top } : null;
    };
    for (const b of all.filter((e) => isButton(e) && e.textContent.trim())) {
      // a vertical pill (a left tray's axis) runs along its words - its height is its length, not its size
      if (/^vertical/.test(css(b).writingMode)) continue;
      const r = b.getBoundingClientRect();
      let bar = b.parentElement;
      while (bar && bar.parentElement && bar.parentElement !== document.body && bar.parentElement.getBoundingClientRect().height < r.height * 3) bar = bar.parentElement;
      if (!bar) continue;
      const mid = (x) => (x.top + x.bottom) / 2;
      const items = [];
      for (const e of bar.querySelectorAll('*')) {
        if (e === b || b.contains(e) || e.contains(b) || !shown(e)) continue;
        if (isControl(e)) {
          if (!e.parentElement.closest('button, [role="button"]')) items.push({ box: e.getBoundingClientRect(), font: parseFloat(css(e).fontSize), control: true });
          continue;
        }
        if (e.closest('button, [role="button"]')) continue;
        const t = textBox(e);
        if (t) items.push({ box: t, font: parseFloat(css(e).fontSize) });
      }
      const near = items.filter((x) => mid(x.box) >= r.top && mid(x.box) <= r.bottom);
      // The other controls of the line when it has any; its text when the button stands alone among words.
      const line = near.some((x) => x.control) ? near.filter((x) => x.control) : near;
      if (!line.length) continue;
      const h = median(line.map((x) => x.box.height));
      const f = median(line.map((x) => x.font));
      const font = parseFloat(css(b).fontSize);
      if (r.height > h * 1.5 && font <= f) {
        lines.push({ rule: 'size', path: pathOf(b), what: `«${label(b)}» ${Math.round(r.height)} px high at ${font} px letters, its line ${Math.round(h)} px at ${f} px` });
      }
    }
    // columns: one line per table - a row where a cell runs past three lines while a neighbouring column is more than
    // half empty all the way down (its widest cell decides; a column as wide as its longest word is not slack)
    const tables = new Map();
    for (const tr of scope.querySelectorAll('tr, [role="row"]')) {
      if (!shown(tr)) continue;
      const table = tr.closest('table, [role="table"], [role="grid"], [role="treegrid"]') || tr.parentElement;
      const cells = [...tr.children].filter(shown).map((c) => {
        const b = c.getBoundingClientRect();
        const s = css(c);
        const left = b.left + parseFloat(s.paddingLeft);
        const width = b.width - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight);
        const tops = new Set();
        let right = left;
        const walker = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
          if (!n.textContent.trim()) continue;
          const range = document.createRange();
          range.selectNodeContents(n);
          for (const r of range.getClientRects()) if (r.width) { tops.add(Math.round(r.top)); right = Math.max(right, r.right); }
        }
        return { c, lines: tops.size, width, empty: width - (right - left) };
      });
      if (!tables.has(table)) tables.set(table, []);
      tables.get(table).push(cells);
    }
    for (const [table, rows] of tables) {
      const empty = (i) => Math.min(...rows.filter((r) => r[i] && r[i].lines > 0).map((r) => r[i].empty));
      for (const cells of rows) {
        const t = cells.findIndex((x) => x.lines > 3);
        if (t < 0) continue;
        const l = cells.findIndex((x, i) => i !== t && x.lines > 0 && empty(i) > x.width / 2);
        if (l < 0) continue;
        lines.push({ rule: 'columns', path: pathOf(table), what: `«${label(cells[t].c)}» runs to ${cells[t].lines} lines while the column of «${label(cells[l].c)}» leaves ${Math.round(empty(l))} of ${Math.round(cells[l].width)} px empty` });
        break;
      }
    }
    // words: in a text that runs over lines, two letters of one word on two lines
    const letter = /\w/;
    const texts = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
    for (let n = texts.nextNode(); n; n = texts.nextNode()) {
      const t = n.textContent;
      if (t.trim().length < 2 || !shown(n.parentElement) || n.parentElement.closest('[data-wrap-ok]')) continue;
      const whole = document.createRange();
      whole.selectNodeContents(n);
      if (new Set([...whole.getClientRects()].filter((r) => r.width).map((r) => Math.round(r.top))).size < 2) continue;
      let prev = null;
      for (let i = 0; i < t.length; i += 1) {
        const one = document.createRange();
        one.setStart(n, i);
        one.setEnd(n, i + 1);
        const box = [...one.getClientRects()].find((r) => r.width);
        if (!box) continue;
        if (prev && prev.i === i - 1 && box.top > prev.box.top + prev.box.height / 2 && letter.test(t[i - 1]) && letter.test(t[i])) {
          const from = t.lastIndexOf(' ', i) + 1;
          const to = t.indexOf(' ', i) < 0 ? t.length : t.indexOf(' ', i);
          lines.push({ rule: 'words', path: pathOf(n.parentElement), what: `«${t.slice(from, to).slice(0, 40)}» breaks between «${t[i - 1]}» and «${t[i]}»` });
          break;
        }
        prev = { box, i };
      }
    }
    return lines;
  }

  // Every button in a <header>, and every [aria-haspopup], pressed in turn: what appears positioned is its panel.
  const keyOf = (b) => `${pathOf(b)}|${label(b)}`;
  // the worlds' chips (a shared part, the branch picker) toggle a world - they open nothing; a pick walks again and redraws
  const openers = () => [...document.querySelectorAll('header button, header [role="button"], [aria-haspopup]')].filter((b) => shown(b) && !b.disabled && !b.closest('.branch-picker'));
  const floating = () => [...document.querySelectorAll('body *')].filter((e) => /absolute|fixed/.test(css(e).position) && shown(e));
  const pressed = new Set();
  let open = null;
  async function openNext() {
    const b = openers().find((x) => !pressed.has(keyOf(x)));
    if (!b) return null;
    const key = keyOf(b);
    pressed.add(key);
    const before = new Set(floating());
    b.click();
    await wait(450);
    const now = openers().find((x) => keyOf(x) === key) || b;
    const boxed = (el) => { for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) { if (scrolls(css(e))) return true; } return false; };
    const fresh = floating().filter((e) => !before.has(e) && !boxed(e) && !e.closest('[aria-live]'));
    const panel = fresh.find((e) => !fresh.some((o) => o !== e && o.contains(e))
      && e.getBoundingClientRect().width > 40 && e.getBoundingClientRect().height > 20);
    if (!panel) return { opener: key, panel: null, lines: [] };
    const a = now.getBoundingClientRect(), p = panel.getBoundingClientRect();
    const lines = [];
    const below = p.top - a.bottom;
    const edge = Math.min(Math.abs(p.left - a.left), Math.abs(p.right - a.right));
    const atMargin = p.left <= TOL || p.right >= innerWidth - TOL;
    if (below < -1 || below > TOL) lines.push({ rule: 'panel', path: pathOf(panel), what: `top ${Math.round(below)} px under «${label(now)}»` });
    if (edge > TOL && !atMargin) lines.push({ rule: 'panel', path: pathOf(panel), what: `no edge meets «${label(now)}» (nearest ${Math.round(edge)} px)` });
    if (p.left < 0 || p.right > innerWidth || p.bottom > innerHeight) lines.push({ rule: 'panel', path: pathOf(panel), what: `off the screen, opened by «${label(now)}»` });
    if (p.top < 0) lines.push({ rule: 'panel', path: pathOf(panel), what: `above the screen, opened by «${label(now)}»` });
    // Cut to the screen, it scrolls in its own box (lead 72b2d7f8f: one placement cuts a panel taller than the room).
    if (panel.scrollHeight > panel.clientHeight + 1 && !/auto|scroll/.test(css(panel).overflowY)) {
      lines.push({ rule: 'panel', path: pathOf(panel), what: `cut with no scroll of its own, opened by «${label(now)}»` });
    }
    const first = panel.querySelector('button:not([disabled]), a[href], input, select, label, [role="menuitem"]');
    if (first && shown(first)) {
      const f = first.getBoundingClientRect();
      const hit = document.elementFromPoint(f.left + f.width / 2, f.top + f.height / 2);
      if (!(hit === first || first.contains(hit))) lines.push({ rule: 'panel', path: pathOf(first), what: `first control covered by ${hit ? pathOf(hit) : 'nothing'}` });
    }
    // A row of the panel is one line (owner 10-09: the header's panels came out narrower and their rows broke in two);
    // a panel that wraps on purpose says so with data-wrap-ok.
    if (!panel.closest('[data-wrap-ok]')) {
      for (const el of panel.querySelectorAll('*')) {
        if (!shown(el)) continue;
        const tops = new Set();
        for (const n of el.childNodes) {
          if (n.nodeType !== 3 || !n.textContent.trim()) continue;
          const range = document.createRange();
          range.selectNodeContents(n);
          for (const r of range.getClientRects()) if (r.width) tops.add(Math.round(r.top));
        }
        if (tops.size > 1) lines.push({ rule: 'panel', path: pathOf(el), what: `«${label(el)}» breaks into ${tops.size} lines in the panel «${label(now)}» opened` });
      }
    }
    panel.setAttribute('data-screens-open', '');
    open = { key, panel };
    return { opener: key, panel: pathOf(panel), lines };
  }
  async function close() {
    if (!open) return true;
    const { key, panel } = open;
    open = null;
    panel.removeAttribute('data-screens-open');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await wait(150);
    if (shown(panel)) { document.body.click(); await wait(150); }
    const again = openers().find((x) => keyOf(x) === key);
    if (shown(panel) && again) { again.click(); await wait(200); }
    return !shown(panel);
  }
  window.__screens = { measure, openNext, close };
  return true;
}

// ---- the states each entry is driven through, in order; every entry ends with its header's panels opened.
// A wait that runs out leaves its state unreached: the drive loop says it under «answers», with the step, so a green
// line is never a state the gate did not get to (lead 10-10 - the walk page passed once with every wait run out).
const waitsRunOut = [];
const until = async (chrome, test, most = 10000) => {
  const held = await evaluate(chrome, `new Promise((ok) => { const t0 = Date.now();
  const tick = () => { let v = false; try { v = (${test}); } catch (e) {} if (v || Date.now() - t0 > ${most}) ok(Boolean(v)); else setTimeout(tick, 150); }; tick(); })`);
  if (!held) waitsRunOut.push(`waited ${most} ms and it never held: ${test}`);
  return held;
};
const GRID_LOADED = `/^Loaded/.test((document.querySelector('#performance-log') || {}).textContent || '')`;
const press = (c, words) => evaluate(c, `(() => { const b = [...document.querySelectorAll('button')].find((x) => x.textContent.trim() === ${JSON.stringify(words)} && !x.disabled);
  if (b) b.click(); return Boolean(b); })()`);
const choose = (c, sel, pick) => evaluate(c, `(() => { const s = document.querySelectorAll(${JSON.stringify(sel)})[${pick[0]}]; if (!s) return false;
  const o = [...s.options].find((x, i) => ${pick[1]}); if (!o) return false; s.value = o.value; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
// PICK A NODE's box (lead bccbdd601): the key typed, then its row pressed - the review's two wafers (34d91c09d), not
// the list's first two.
const pickKey = async (c, key) => {
  // The box shows once the type's first answer names its key (hidden while it loads, and a hidden box takes no focus).
  await until(c, "document.querySelector('.wk-search .wk-cell') && !document.querySelector('.wk-search .wk-cell').hidden");
  await evaluate(c, `(() => { const b = document.querySelector('.wk-search input'); if (!b) return false; b.focus(); b.click();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(b, ${JSON.stringify(key)});
    b.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  const row = `[...document.querySelectorAll('.wk-searchitem')].find((r) => (r.querySelector('.wk-searchkey') || {}).textContent === ${JSON.stringify(key)})`;
  await until(c, row);
  return evaluate(c, `(() => { const r = ${row}; if (!r) return false;
    r.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window })); return true; })()`);
};
// A basket's +: the picked node into Positive (+) or Negative (−) (lead bc63378e5).
const basket = (c, sign) => evaluate(c, `(() => { const b = document.querySelector('.wk-basketadd[data-sign="${sign}"]');
  if (b && !b.disabled) b.click(); return Boolean(b); })()`);
// «+ Add start»: the start baskets' picker opened (walk/start_baskets.js - a details whose body hangs under the bar).
const openStartPicker = (c) => evaluate(c, `(() => { const pop = document.querySelector('details.wk-barpop');
  if (pop && !pop.open) pop.querySelector('summary').click(); return Boolean(pop); })()`).then(() => sleep(300));
// The page opened again (what it saved read anew): one navigation let through, the measuring put back.
const openAgain = async (c, log) => {
  log.opening = true;
  await c.send('Page.navigate', { url: `${ORIGIN}/testbed.html` });
  await sleep(1500);
  await settle(c, log);
  await evaluate(c, `(${screensLib})(${TOL})`);
};
const DRIVE = {
  'walk.html': [
    ['a wafer walked, Table', async (c) => {
      await choose(c, '.wk-select', [0, "x.textContent.trim() === 'wafer'"]);
      await pickKey(c, 'SYN-BW-103-11');
      await sleep(300);
      await basket(c, '+');
      await press(c, 'Walk');
      await until(c, "document.querySelector('.wk-main table, .wk-main svg, .wk-main canvas')");
    }],
    ['Graph', (c) => press(c, 'Graph').then(() => sleep(1500))],
    // The table side by side (lead 3375edd9b) with the demo pair (34d91c09d; 10-10 after 517eb6c2c): a second wafer in
    // Negative, wafer and quantity collected, then Walk - a band per sign, a missing side, a wide + side, a Δ.
    ['Table, + and - side by side', async (c) => {
      await press(c, 'Table');
      await pickKey(c, 'SYN-BW-SPL-400-19');
      await sleep(300);
      await basket(c, '−');
      await choose(c, 'select.wk-add', [0, "x.value === 'wafer'"]);
      await choose(c, 'select.wk-add', [0, "x.value === 'quantity'"]);
      await press(c, 'Walk');
      await until(c, "document.querySelectorAll('.wk-sidehead').length > 1");
    }],
    // The same table in each theme; SIDE_CELLS ask the four after each.
    ['Side by side, dark', (c) => evaluate(c, "document.documentElement.setAttribute('data-theme', 'dark'); true").then(() => sleep(300))],
    ['Side by side, light', (c) => evaluate(c, "document.documentElement.setAttribute('data-theme', 'light'); true").then(() => sleep(300))],
    // A value cell pressed opens its column's trend under the tables (lead f984ab01d).
    ['Trend of a value cell', async (c) => {
      await evaluate(c, `(() => { const td = document.querySelector('.wk-sides td.wk-pick'); if (td) td.click(); return Boolean(td); })()`);
      await until(c, "document.querySelector('.wk-trend svg, .wk-trend .wk-note')");
    }],
    // Long (lead 10-11 W): the first section a value record a line.
    ['Long', async (c) => {
      await evaluate(c, `(() => { const b = document.querySelector('.wk-sec [data-shape="long"]'); if (b) b.click(); return Boolean(b); })()`);
      await until(c, "document.querySelector('table.wk-long')");
    }],
    // Control · B (lead 99ed68cb7 D): leads_to walked once more from the same baskets (10-11, the W 1 regression).
    ['Control · B', async (c) => {
      // The wafer section back in Wide: B reaches the two start wafers, A + B on each side.
      await evaluate(c, `(() => { const b = document.querySelector('.wk-sec [data-shape="wide"]'); if (b) b.click(); return Boolean(b); })()`);
      await evaluate(c, `(() => { const box = document.querySelector('[data-control="leads_to"] input'); if (box && !box.checked) box.click(); return Boolean(box); })()`);
      await press(c, 'Walk');
      await until(c, "document.querySelector('.wk-reachedn')");
    }],
    // A row ticked deep in a long table keeps the reader's place (owner 10-11 «체크할 때마다 상단으로 스크롤 초기화하지 마»).
    ['A row ticked mid-table', (c) => evaluate(c, `(() => {
      const main = document.querySelector('.wk-main'), table = document.querySelector('.wk-sec table.wk-wide');
      main.scrollTop = Math.floor((main.scrollHeight - main.clientHeight) / 2); table.scrollLeft = 40;
      const rows = [...main.querySelectorAll('input[data-row]')].filter((b) => b.getBoundingClientRect().top > 0);
      window.__place = { top: main.scrollTop, left: table.scrollLeft, ticked: Boolean(rows[0]) };
      if (rows[0]) rows[0].click();
      return true; })()`).then(() => sleep(300))],
    // through ▾ opened after the walk: its Route says the ways walked (owner 10-12 «실제 걸은 경로로»), a long way wrapping.
    ['Route walked', async (c) => {
      await evaluate(c, `(() => { const chip = document.querySelector('.wk-through > :first-child'); if (chip) chip.click(); return Boolean(chip); })()`);
      await until(c, "[...document.querySelectorAll('.wk-routes-head')].some((h) => h.getClientRects().length && /Walked to/.test(h.textContent))");
    }],
    ['Add start opened', openStartPicker],
  ],
  // The testbed's start row (lead 10-13, 18997: its picker hung clipped under a 44 px panel - no start could be picked).
  'testbed.html': [
    // a board saved by a state before (the dies below, or Save pressed while panels were opened) - the page's own layout
    ['Add start opened', async (c, log) => {
      PHOTOS.on = false;
      const had = await evaluate(c, "(() => { const had = localStorage.getItem('testbed:visuals') !== null; localStorage.removeItem('testbed:visuals'); return had; })()");
      if (had) await openAgain(c, log);
      await openStartPicker(c);
    }],
    // The root part at the right edge and the foot of the grid, the start row at the foot (lead 72b2d7f8f): the page's
    // own gestures (lead 10-13) - the Marked table closed by its ×, the scatter's title dragged onto the area's right edge -
    // the right dock and the status bar hidden, the start row's dock written to the foot; then a wafer walked from there.
    ['walked at the edge', async (c) => {
      // The board seats its parts once the declaration is in: the gesture waits for the title it presses. A page that opens
      // already laid at the edge - the measuring pressed the head's Save on the size before, and the page opens what was
      // saved (lead 10-14: the five red sizes after the first) - is laid.
      await until(c, "Boolean(document.querySelector('[data-cell=\"scatter-1\"] [data-part-title]'))", 15000);
      const laid = await evaluate(c, `(() => {
        const press = (type, target, x, y) => target.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y,
          button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true }));
        for (const sel of ['[data-dock="right"]', '[data-panel="status"]']) { const e = document.querySelector(sel); if (e) e.style.display = 'none'; }
        const top = document.querySelector('[data-dock="top"]');
        if (top) top.style.gridArea = 'bottom';
        const cellsNow = () => [...document.querySelectorAll('[data-cell]')].map((x) => x.getAttribute('data-cell')).join(',');
        if (cellsNow() === 'cross-1,scatter-1') return true;
        const close = document.querySelector('[data-cell="marked"] .sf-tool[title="Close"]');
        if (close) close.click();
        const title = document.querySelector('[data-cell="scatter-1"] [data-part-title]');
        if (!title || !top || !close) return 'title ' + Boolean(title) + ' start row ' + Boolean(top) + ' close ' + Boolean(close) + ' cells ' + cellsNow();
        const t = title.getBoundingClientRect();
        const area = document.querySelector('.rb-area').getBoundingClientRect();
        const y = (area.top + area.bottom) / 2;
        press('pointerdown', title, t.left + 20, t.top + 10);
        press('pointermove', document, area.right - 40, y);
        press('pointermove', document, area.right - 4, y);
        press('pointerup', document, area.right - 4, y);
        const cells = cellsNow();
        return cells === 'cross-1,scatter-1' ? true : 'cells ' + cells + ' area ' + [area.left, area.right, y].map(Math.round) + ' title ' + [t.left, t.top].map(Math.round); })()`);
      if (laid !== true) throw new Error(`the scatter did not land on the area's right edge: ${laid}`);
      await openStartPicker(c);
      await choose(c, '.tb-start__type', [0, "x.value === 'wafer'"]);
      await pickKey(c, 'SYN-BW-103-11');
      await sleep(300);
      await basket(c, '+');
      await evaluate(c, "(() => { const pop = document.querySelector('details.wk-barpop'); if (pop) pop.open = false; return true; })()");
      await until(c, "document.querySelectorAll('[data-panel=\"scatter-1\"] .sf-pill').length > 0", 15000);
    }],
    // The Spotfire standard's tokens in the other theme (lead b72a0ea4f: the sample and the test bed, dark and light).
    ['light theme', (c) => evaluate(c, "document.documentElement.setAttribute('data-theme', 'light'); true").then(() => sleep(300))],
    // The board of dies (BOARD_SAVED): opened as saved - panels by step, the marked die's label at the right edge, the
    // filters panel with the long ids and the times (lead 10-14).
    ['dies in panels', async (c, log) => {
      await evaluate(c, `localStorage.setItem('testbed:visuals', ${JSON.stringify(JSON.stringify(BOARD_SAVED))}); true`);
      await openAgain(c, log);
      await until(c, "document.querySelectorAll('.sf-trellis__panel canvas').length >= 2 && document.querySelectorAll('[data-panel=\"cross-1\"] td').length > 0", 15000);
    }],
    // The tooltip of a cross table cell - its time as the grid says it (lead 10-14: «2026-11-23T18:49:00.000Z»).
    ['tooltip over a cell', async (c) => {
      await evaluate(c, `(() => { const td = document.querySelector('[data-panel="cross-1"] td'); if (!td) return false;
        const r = td.getBoundingClientRect();
        td.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: r.left + 4, clientY: r.top + 4 })); return true; })()`);
      await sleep(200);
    }],
    // The window shrunk and grown again (lead 10-14: a panel kept its 40 x 44 canvas after growing).
    ['shrunk and grown', async (c) => {
      const [w, h] = await evaluate(c, '[window.innerWidth, window.innerHeight]');
      await c.send('Emulation.setDeviceMetricsOverride', { width: 800, height: 450, deviceScaleFactor: 1, mobile: false });
      await sleep(800);
      await c.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: false });
      await sleep(800);
    }],
    // The pictures (IMAGES_SAVED, lead-board-14): the photos on, the board opened; the table's pictures in
    ['images', async (c, log) => {
      PHOTOS.on = true;
      await evaluate(c, `localStorage.setItem('testbed:visuals', ${JSON.stringify(JSON.stringify(IMAGES_SAVED))}); true`);
      await openAgain(c, log);
      await until(c, "document.querySelectorAll('.sf-part').length >= 3 && [...document.querySelectorAll('.sf-thumb__img')].some((i) => i.complete && i.naturalWidth > 0)", 15000);
      await sleep(600);
    }],
    // Every kind in one board (KINDS_SAVED): the part frame the same round each kind's area (lead 10-14)
    ['every kind', async (c, log) => {
      PHOTOS.on = false;
      await evaluate(c, `localStorage.setItem('testbed:visuals', ${JSON.stringify(JSON.stringify(KINDS_SAVED))}); true`);
      await openAgain(c, log);
      await until(c, "document.querySelectorAll('.sf-part').length >= 6 && document.querySelectorAll('[data-panel=\"table-1\"] td').length > 0", 15000);
    }],
    // Each part made active in turn - its status line read (the walks it says)
    ['walks on the status line', async (c) => {
      await evaluate(c, `(async () => {
        const wait = (ms) => new Promise((r) => setTimeout(r, ms));
        const out = [];
        for (const el of document.querySelectorAll('[data-panel]')) {
          const inner = el.querySelector('.sf-frame');
          if (!inner) continue;
          inner.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
          await wait(150);
          out.push({ id: el.getAttribute('data-panel'), words: [...document.querySelectorAll('.sf-status span')].map((s) => s.textContent) });
        }
        window.__walkLine = out;
        return true;
      })()`);
    }],
    // A pill of two columns: its second column's chip dragged onto the first in the picker - the hierarchy's levels change
    // places (lead 10-14).
    ['columns reordered by a drag', async (c) => {
      const got = await evaluate(c, `(async () => {
        const wait = (ms) => new Promise((r) => setTimeout(r, ms));
        const corner = () => (document.querySelector('[data-panel="cross-1"] .sf-table__corner') || {}).textContent || null;
        const before = corner();
        const pill = document.querySelector('[data-panel="cross-1"] .sf-frame__left .sf-pill');
        if (!pill) return { why: 'no row axis pill' };
        pill.click();
        await wait(300);
        const chip = (k) => document.querySelector('.sf-pop-host [data-column="' + k + '"]');
        if (!chip(0) || !chip(1)) return { why: 'no column chips', before };
        const data = new DataTransfer();
        chip(1).dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: data }));
        chip(0).dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, dataTransfer: data }));
        chip(0).dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: data }));
        await wait(600);
        const chips = [...document.querySelectorAll('.sf-pop-host [data-column]')].map((x) => x.textContent.replace('×', '').trim());
        document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
        await wait(200);
        return { before, after: corner(), chips };
      })()`);
      await evaluate(c, `window.__chipOrder = ${JSON.stringify(got)}; true`);
    }],
    // A pill's picker stays under its pill (owner 10-14 «알약 선언창 자꾸 화면 좌상단으로 날아가는데»): opened, after a
    // value picked (the part drawn again), after the window resized - each kind's tray pills; where it stood each time.
    ['pickers under their pills', async (c) => {
      const placed = async (when) => evaluate(c, `(() => {
        const host = document.querySelector('.sf-pop-host');
        const pill = window.__pickPill && window.__pickPill();
        if (!pill) return { when: ${JSON.stringify(when)}, why: 'no pill' };
        // closed - right only when its pill's slot is gone from there (a table's + Column became a column)
        if (!host || host.style.display === 'none') return { when: ${JSON.stringify(when)}, kind: window.__pickKind, closed: true, slotGone: pill.getAttribute('data-slot') !== window.__pickSlot };
        const h = host.getBoundingClientRect(), r = pill.getBoundingClientRect();
        return { when: ${JSON.stringify(when)}, kind: window.__pickKind, dx: Math.round(h.left - r.left), atRight: Math.round(document.documentElement.clientWidth - h.right), below: Math.round(h.top - r.bottom), above: Math.round(r.top - h.bottom) };
      })()`);
      const out = [];
      // each tray pill, then the properties panel's first three (that panel is drawn again on every pick)
      const trays = await evaluate(c, `[...document.querySelectorAll('.sf-frame__tray .sf-pill')].filter((p) => p.getClientRects().length)
        .map((p) => [p.closest('[data-panel]').getAttribute('data-panel') + ' ' + [...p.closest('.sf-frame__tray').classList].pop(),
          "document.querySelector('[data-panel=\\"" + p.closest('[data-panel]').getAttribute('data-panel') + "\\"] ." + [...p.closest('.sf-frame__tray').classList].pop()
          + " .sf-frame__pills').children[" + [...p.parentNode.children].indexOf(p) + "]"])`);
      const props = [0, 1, 2].map((i) => [`properties pill ${i}`, `[...document.querySelectorAll('[data-panel="properties"] .sf-pill')][${i}]`]);
      for (const [label, findExpr] of [...trays, ...props]) {
        const opened = await evaluate(c, `(() => {
          const find = () => ${findExpr};
          window.__pickPill = find; window.__pickKind = ${JSON.stringify(label)}; window.__pickSlot = find() && find().getAttribute('data-slot');
          if (!find()) return false; find().click(); return true; })()`);
        if (!opened) continue;
        await sleep(300);
        out.push(await placed('opened'));
        // a value picked: the part drawn again
        await evaluate(c, `(() => { const it = [...document.querySelectorAll('.sf-pop-host .sf-pop__col')][1];
          const b = it && [...it.querySelectorAll('button.sf-pop__it')].find((x) => !x.classList.contains('is-on'));
          if (b) b.click(); return Boolean(b); })()`);
        await sleep(600);
        out.push(await placed('after a pick'));
        // a second pick in the same picker - the part was drawn again after the first
        await evaluate(c, `(() => { const b = [...document.querySelectorAll('.sf-pop-host .sf-pop__red')].find((x) => !x.classList.contains('is-on') && !x.disabled);
          if (b) b.click(); return Boolean(b); })()`);
        await sleep(600);
        out.push(await placed('after a second pick'));
        const [w, h] = await evaluate(c, '[window.innerWidth, window.innerHeight]');
        await c.send('Emulation.setDeviceMetricsOverride', { width: w - 120, height: h, deviceScaleFactor: 1, mobile: false });
        await sleep(400);
        out.push(await placed('window narrowed'));
        await c.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: false });
        await sleep(400);
        await evaluate(c, "(() => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true })); return true; })()");
        await sleep(200);
      }
      await evaluate(c, `window.__pickPlaced = ${JSON.stringify(out)}; true`);
    }],
    // A part's title dropped on another's middle - the two swap (owner 10-14, Spotfire's); dragged there and Escape - nothing
    // moves; while over the middle the drop mark covers the whole part.
    ['parts swapped by a drop', async (c) => {
      const got = await evaluate(c, `(async () => {
        const wait = (ms) => new Promise((r) => setTimeout(r, ms));
        const fire = (type, target, x, y) => target.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y,
          button: 0, pointerId: 1, pointerType: 'mouse', isPrimary: true }));
        const cells = () => [...document.querySelectorAll('[data-cell]')].map((x) => x.getAttribute('data-cell')).join(',');
        const drag = async (from, to, end) => {
          const title = document.querySelector('[data-cell="' + from + '"] [data-part-title]');
          const box = document.querySelector('[data-cell="' + to + '"]').getBoundingClientRect();
          const t0 = title.getBoundingClientRect();
          const [x, y] = [(box.left + box.right) / 2, (box.top + box.bottom) / 2];
          fire('pointerdown', title, t0.left + 30, t0.top + 10);
          fire('pointermove', document, t0.left + 60, t0.top + 30);
          fire('pointermove', document, x, y);
          await wait(100);
          const mark = document.querySelector('.sf-drop');
          const m = mark ? mark.getBoundingClientRect() : null;
          const covers = Boolean(m) && Math.abs(m.width - box.width) <= 2 && Math.abs(m.height - box.height) <= 2;
          if (end === 'escape') document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
          else fire('pointerup', document, x, y);
          await wait(300);
          return covers;
        };
        const before = cells();
        const escCovers = await drag('scatter-1', 'table-1', 'escape');
        const afterEscape = cells();
        const covers = await drag('scatter-1', 'table-1', 'drop');
        return { before, afterEscape, escCovers, covers, after: cells() };
      })()`);
      await evaluate(c, `window.__swapped = ${JSON.stringify(got)}; true`);
    }],
    // the next size opens the page's own layout
    ['saved cleared', (c) => evaluate(c, "localStorage.removeItem('testbed:visuals'); true")],
  ],
  // The sample's Spotfire standard section (src/spotfire.css), in each theme.
  'sample.html': [
    ['Spotfire standard, light', (c) => evaluate(c, `(() => { document.documentElement.setAttribute('data-theme', 'light');
      const s = document.querySelector('.sample-sf'); if (s) s.scrollIntoView({ block: 'start' }); return Boolean(s); })()`).then(() => sleep(300))],
    ['Spotfire standard, dark', (c) => evaluate(c, "document.documentElement.setAttribute('data-theme', 'dark'); true").then(() => sleep(300))],
    // The ledger declaration window (owner 10-14), one chip's list open as the mockup draws it, in each theme.
    // The Spotfire section is set aside: its floating tools are its own scenes' to measure, and off the screen here.
    ['Ledger declaration, list open, dark', (c) => evaluate(c, `(() => { const s = document.getElementById('sample-decl-bar');
      const sf = document.querySelector('.sample-sf'); const box = sf && sf.closest('section'); if (box) box.hidden = true;
      const chip = s && s.querySelector('[data-path="sentences.0.subject.keys.wafer"]'); if (chip) chip.click();
      const open = document.getElementById('sample-decl-bar');
      if (open) open.scrollIntoView({ block: 'start' }); return Boolean(open && open.querySelector('.ldb-pop')); })()`).then(() => sleep(300))],
    ['Ledger declaration, list open, light', (c) => evaluate(c, "document.documentElement.setAttribute('data-theme', 'light'); true").then(() => sleep(300))],
  ],
  'index.html': [
    ['loaded', (c) => until(c, GRID_LOADED, 15000)],
    // One filter at a time, each one's load waited out: typed together, which half-set the grid's debounce sent
    // depended on the clock and the answers held only some (application QA 4bd46df68: red in one run of four).
    ['three filters', async (c, log) => {
      for (const [col, v] of [['subject_type', 'die'], ['predicate', 'in_container'], ['object_kind', 'entity_ref']]) {
        await evaluate(c, `(() => {
          const input = [...document.querySelectorAll('.ag-floating-filter input')].find((i) => i.closest('[col-id]') && i.closest('[col-id]').getAttribute('col-id') === ${JSON.stringify(col)});
          if (!input) return false;
          Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, ${JSON.stringify(v)});
          input.dispatchEvent(new Event('input', { bubbles: true }));
          return true; })()`);
        await sleep(900);
        await settle(c, log);
        await until(c, GRID_LOADED);
      }
    }],
    ['row picked, Queue tab', (c) => evaluate(c, `(() => {
      const cell = document.querySelector('.ag-center-cols-container .ag-row[row-index="0"] .ag-cell');
      if (cell) for (const t of ['mousedown', 'mouseup', 'click']) cell.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window }));
      const tab = document.getElementById('tab-queue'); if (tab) tab.click();
      return true; })()`)],
    // Dragged to 500 px: wider than the six columns' least widths or not, every cell whole (the box rolls).
    ['side panel dragged to 500 px', (c) => evaluate(c, `(() => {
      const bar = document.getElementById('main-split-resizer'); const box = document.querySelector('.main-layout'); if (!bar || !box) return false;
      const x = box.getBoundingClientRect().right - 500;
      const at = (t) => (t === 'mousedown' ? bar : document).dispatchEvent(new MouseEvent(t, { bubbles: true, clientX: x, clientY: 300 }));
      at('mousedown'); at('mousemove'); at('mouseup');
      return true; })()`).then(() => sleep(600))],
    // At the panel's floor the queue rolls sideways inside its own box, its columns whole (lead 10-09).
    ['side panel at its narrowest', (c) => evaluate(c, `(() => {
      const bar = document.getElementById('main-split-resizer'); if (!bar) return false;
      const at = (t) => (t === 'mousedown' ? bar : document).dispatchEvent(new MouseEvent(t, { bubbles: true, clientX: innerWidth, clientY: 300 }));
      at('mousedown'); at('mousemove'); at('mouseup');
      return true; })()`).then(() => sleep(600))],
    // The right-most column's own filter box takes a letter at every size and the grid reads by it (lead 72b2d7f8f:
    // the owner's most used screen) - scrolled to the grid's right end, the box's centre reaching the box.
    ['right-most column filtered', async (c, log) => {
      await evaluate(c, `(async () => {
        const v = document.querySelector('.ag-body-horizontal-scroll-viewport');
        if (v) { v.scrollLeft = v.scrollWidth; v.dispatchEvent(new Event('scroll')); }
        await new Promise((r) => setTimeout(r, 500));
        const boxes = [...document.querySelectorAll('.ag-floating-filter input')].filter((i) => i.getClientRects().length && !i.disabled);
        const box = boxes.sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right)[0];
        const col = box && box.closest('[col-id]') ? box.closest('[col-id]').getAttribute('col-id') : null;
        if (!box || !col) { window.__filterTyped = { why: 'no filter box at the right end' }; return false; }
        const r = box.getBoundingClientRect();
        const hit = document.elementFromPoint((r.left + r.right) / 2, (r.top + r.bottom) / 2);
        if (!(hit === box || box.contains(hit))) {
          window.__filterTyped = { why: 'a press on the «' + col + '» filter box reaches ' + (hit ? hit.tagName.toLowerCase() + '.' + String(hit.className).split(' ')[0] : 'nothing') };
          return false;
        }
        box.focus();
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(box, 'e');
        box.dispatchEvent(new Event('input', { bubbles: true }));
        window.__filterTyped = { col, at: performance.now() };
        return true; })()`);
      await sleep(900);
      await settle(c, log);
      await until(c, GRID_LOADED);
    }],
    // ... and its letter taken back, so the header panels opened next are the ones the grid had (no extra «✕»).
    ['right-most filter cleared', async (c, log) => {
      await evaluate(c, `(() => { const t = window.__filterTyped; if (!t || !t.col) return false;
        const box = [...document.querySelectorAll('.ag-floating-filter input')].find((i) => i.closest('[col-id]') && i.closest('[col-id]').getAttribute('col-id') === t.col);
        if (!box) return false; Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(box, '');
        box.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
      await sleep(900);
      await settle(c, log);
      await until(c, GRID_LOADED);
    }],
  ],
  'admin.html': [
    ['Overview', async () => true],
    ['Overview, every row unfolded', (c) => evaluate(c, `(() => {
      for (const row of document.querySelectorAll('.ov-row[aria-expanded="false"]')) row.click();
      return true; })()`).then(() => sleep(800))],
    // The Retry row with «Include files that went in» turned on (lead a4d135a06).
    ['File Ingestion, files that went in included', (c) => evaluate(c, `(() => {
      location.hash = '#file';
      return true; })()`).then(() => sleep(1500)).then(() => evaluate(c, `(() => {
      const box = document.querySelector('.folder-retry-include-box'); if (!box) return false;
      box.checked = true; box.dispatchEvent(new Event('change', { bubbles: true }));
      return true; })()`))],
    // The other tabs, each by its address (lead 10-09: the File tab showed two defects the first time it was opened).
    ...[['Tables', 'tables'], ['Chain', 'chain'], ['Auto Update', 'autoupdate'], ['Retroactive', 'retroactive']]
      .map(([name, hash]) => [name, (c) => evaluate(c, `location.hash = '#${hash}'; true`).then(() => sleep(1500))]),
    ['Ontology Explorer', (c) => evaluate(c, "location.hash = '#ontology'; true").then(() => sleep(1500))],
  ],
};

async function runScreens(dist, label, one = only) {
  const entries = readdirSync(dist).filter((n) => n.endsWith('.html')).sort().filter((n) => !one || n === one);
  const found = [];
  const chrome = await openChrome();
  try {
    const log = await servePage(chrome, dist);
    // Each size once, however many entries name it.
    for (const [w, h] of new Map([...SIZES, ...Object.values(ENTRY_SIZES).flat()].map((s) => [s.join('x'), s])).values()) {
      await chrome.send('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: false });
      for (const entry of entries.filter((e) => sizesOf(e).some(([a, b]) => a === w && b === h))) {
        const size = `${w}x${h}`;
        log.missing.clear(); log.refused.length = 0; log.left.length = 0; log.thrown.length = 0; log.outside.clear();
        log.opening = true;
        await chrome.send('Page.navigate', { url: `${ORIGIN}/${entry}` });
        await sleep(300);
        await settle(chrome, log);
        await evaluate(chrome, `(${screensLib})(${TOL})`);
        const add = (state, lines) => { for (const l of lines) found.push({ entry, size, state, ...l }); };
        const panels = [];
        try {
        const all = DRIVE[entry] || [['loaded', async () => true]];
        const states = (FIRST_STATE_ONLY[entry] || []).includes(size) ? all.slice(0, 1) : all;
        let state = 'loaded';
        waitsRunOut.length = 0;
        for (const [name, step] of states) {
          state = name;
          await step(chrome, log);
          add(state, waitsRunOut.splice(0).map((what) => ({ rule: 'answers', path: entry, what })));
          await settle(chrome, log);
          add(state, await evaluate(chrome, 'window.__screens.measure()'));
          for (const cell of CELLS.filter((c) => c.entry === entry && c.after === state && (!c.sizes || c.sizes.includes(size)))) {
            const why = await evaluate(chrome, cell.expr);
            if (why) add(state, [{ rule: cell.rule, path: cell.at || '#performance-log', what: why }]);
          }
          if (shots) writeFileSync(path.join(shots, `${entry}_${size}_${state.replace(/[^a-z0-9]+/gi, '-')}.png`),
            Buffer.from((await chrome.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
        }
        for (let i = 0; i < 60; i += 1) {
          const opened = await evaluate(chrome, 'window.__screens.openNext()');
          if (!opened) break;
          if (!opened.panel) continue;
          panels.push(opened.opener.split('|')[1]);
          await settle(chrome, log, 400, 3000);
          add(`${state}, «${opened.opener.split('|')[1]}» open`, [...opened.lines, ...await evaluate(chrome, "window.__screens.measure('[data-screens-open]')")]);
          if (shots) writeFileSync(path.join(shots, `${entry}_${size}_panel-${opened.opener.split('|')[1].replace(/[^a-z0-9]+/gi, '-')}.png`),
            Buffer.from((await chrome.send('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
          await evaluate(chrome, 'window.__screens.close()');
        }
        } catch (err) {
          found.push({ entry, size, state: 'driving', rule: 'answers', path: entry, what: `could not be driven: ${err.message}` });
        }
        console.log(`  ${label} ${entry} ${size}: ${panels.length} panels opened${panels.length ? ` - ${panels.map((p) => `«${p}»`).join(' ')}` : ''}`);
        for (const u of log.missing) found.push({ entry, size, state: 'answers', rule: 'answers', path: u, what: 'no answer in screens_answers.json.gz' });
        if (log.refused.length) console.log(`  ${label} ${entry} ${size}: ${log.refused.length} non-GET refused (${[...new Set(log.refused)].join(', ')})`);
        for (const t of new Set(log.thrown)) console.log(`  ${label} ${entry} ${size}: threw ${String(t).split('\n').slice(0, 2).join(' | ')}`);
        if (log.outside.size) console.log(`  ${label} ${entry} ${size}: fetched from ${[...log.outside].join(', ')}`);
        if (log.left.length) console.log(`  ${label} ${entry} ${size}: stayed on the page when it asked to leave for ${[...new Set(log.left)].join(', ')}`);
      }
    }
  } finally {
    chrome.close();
  }
  return { entries, found };
}

let ran = 0;
let failed = 0;
const t0 = Date.now();
const { entries, found } = await runScreens(path.join(CLIENT, 'dist'), 'dist');
for (const entry of entries) {
  for (const [w, h] of sizesOf(entry)) {
    const cells = CELLS.filter((c) => c.entry === entry && (!c.sizes || c.sizes.includes(`${w}x${h}`)));
    for (const rule of new Set([...RULES, 'answers', ...cells.map((c) => c.rule)])) {
      ran += 1;
      const mine = found.filter((f) => f.entry === entry && f.size === `${w}x${h}` && f.rule === rule);
      if (mine.length) failed += 1;
      console.log(`${mine.length ? '✗' : '✓'} ${entry} ${w}x${h} ${rule}${mine.length ? ` - ${mine.length}` : ''}`);
      const times = new Map();
      for (const f of mine) { const k = `${f.entry} · ${f.size} · ${f.state} · ${f.path} · ${f.what}`; times.set(k, (times.get(k) || 0) + 1); }
      for (const [k, n] of times) console.log(`    ${k}${n > 1 ? ` (x${n})` : ''}`);
    }
  }
}
console.log(`screens: ${entries.length} entries x ${SIZES.length} sizes in ${Math.round((Date.now() - t0) / 1000)} s`);

// The five that leaked on 10-08/09, each built back into a temp folder (the source is not touched) and opened on its
// screen: its line must turn red. A find that is no longer in the file is an error, not an escape.
const MUTANTS = [
  // A panel left inside the header is placed in the header's zoomed px (10-08).
  { name: 'Replay chain panel placed inside the zoomed header', entry: 'index.html', rule: 'panel', at: 'redo-panel', says: /under/,
    file: 'src/dropdown.js', edits: [['    doc.body.appendChild(panel);\n', '']] },
  // Options and Menu hung from their buttons by CSS inside the header: narrowed by its zoom, their rows in two (10-09).
  { name: 'Options and Menu drawn inside the zoomed header, their rows in two', entry: 'index.html', rule: 'panel', at: '',
    says: /breaks into/, file: 'src/main.js', edits: [
      ['      if (!isVisible) placeUnder(elements.settingsDropdown, elements.settingsMenuBtn);\n', ''],
      ['      if (!isVisible) placeUnder(elements.navDropdown, elements.navMenuBtn);\n', '']] },
  // A rule name in a 48px column, broken letter by letter (lead 10-09; owner 09-23 「접지말고」).
  { name: 'the Rules column back at 48px, its names broken anywhere', entry: 'index.html', rule: 'words', at: 'queue-rule-name',
    file: 'src/style.css', edits: [
      ['minmax(var(--queue-rules-w, 48px), 1fr)', 'minmax(48px, 1fr)'],
      ['                   flex: none; white-space: nowrap; }', '                   flex: 0 1 auto; min-width: 0; overflow-wrap: anywhere; }']] },
  // The header message laid over the button beside it, and its title no longer following its text (lead 10-09).
  { name: 'the header message laid over the button beside it', entry: 'index.html', rule: 'beside the message', at: 'performance-log',
    file: 'src/style.css', edits: [['.app-header #performance-log { flex: 0 1 auto; min-width: 0; pointer-events: auto; }',
      '.app-header #performance-log { flex: 0 1 auto; min-width: 0; pointer-events: auto; position: absolute; inset: 0 0 auto 0; z-index: 5; }']] },
  { name: 'the status bar on one line again - its counts 0 wide at 1024', entry: 'index.html', rule: 'counts reachable', at: 'status-left',
    file: 'src/style.css', edits: [['  flex-wrap: wrap;\n  align-items: center;\n  justify-content: space-between;', '  align-items: center;\n  justify-content: space-between;'],
      ['  min-width: 30ch;\n', '  min-width: 0;\n']] },
  { name: 'the header message title not following its text', entry: 'index.html', rule: 'message title', at: 'performance-log',
    file: 'src/main.js', edits: [['      followTitle(elements.performanceLog);\n', '']] },
  // The Ledger cell's source said first again (lead 10-12): its state word goes under the ellipsis at the column's width.
  { name: 'the Ledger cell says its source before changed', entry: 'index.html', rule: 'ledger word first', at: 'ledger-cell',
    file: 'src/grid_ledger_column.js', edits: [['return [CHANGED, which, ...unknownTail]', 'return [changed[0].source, CHANGED, which, ...unknownTail]']] },
  { name: 'the audit Kind column back at 74px', entry: 'index.html', rule: 'kind word whole', at: 'audit-kind',
    file: 'src/style.css', edits: [['70px 62px 96px 96px 110px minmax(72px, 1fr)', '70px 62px 74px 96px 110px minmax(72px, 1fr)']] },
  { name: 'State column back at a fixed 96px', entry: 'index.html', rule: 'clip', at: 'queue-cell',
    file: 'src/style.css', edits: [['max(96px, var(--queue-state-w, 96px))', '96px']] },
  { name: 'the why beside its tag, cut at the cell', entry: 'index.html', rule: 'clip', at: 'queue-line-state-why',
    file: 'src/base.css', edits: [
      [':where(.queue-line-state) { display: flex; flex-direction: column; align-items: flex-start;', ':where(.queue-line-state) { display: flex; align-items: center;'],
      [':where(.queue-line-state-why) { white-space: normal; overflow-wrap: anywhere; min-width: 0; }',
        ':where(.queue-line-state-why) { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }']] },
  { name: 'the chain state object drawn as text', entry: 'index.html', rule: 'text', at: 'queue',
    file: 'src/chain_queue_panel.js', edits: [["const token = chainState && chainState.state ? String(chainState.state) : '';", "const token = chainState ? String(chainState) : '';"]] },
  { name: 'the Overview queue Refresh boxed at the base button height', entry: 'admin.html', rule: 'size', at: 'chain-queue-refresh',
    file: 'admin.html', edits: [['    .ov-show-all,\n    .chain-queue-panel .chain-queue-refresh,\n    #file-list-body .admin-btn,\n',
      '    .ov-show-all,\n    #file-list-body .admin-btn,\n']] },
  // A file row's Retry boxed at the base button height again, 36 px in its 14 px line (lead a4d135a06's round).
  { name: 'a file row Retry boxed at the base button height', entry: 'admin.html', rule: 'size', at: 'file-list-body',
    file: 'admin.html', edits: [['    #file-list-body .admin-btn,\n    #mapper-list-body .admin-btn,\n',
      '    #mapper-list-body .admin-btn,\n']] },
  // The admin tabs round (lead 10-09): what the gate found when it first opened Tables, Chain, Auto Update, Retroactive.
  { name: 'the Chain and Auto Update row buttons boxed at the base button height', entry: 'admin.html', rule: 'size',
    at: 'mapper-list-body', file: 'admin.html', edits: [['    #mapper-list-body .admin-btn,\n    #autoupdate-linked-body .admin-btn,\n    #retry-all-outbox-btn {\n',
      '    #retry-all-outbox-btn {\n']] },
  { name: 'the Backfill column back at 220px beside the collector names', entry: 'admin.html', rule: 'columns', at: 'sec-collectors',
    file: 'admin.html', edits: [['<th title="Run the collector once per day from a start day (KST)">Backfill</th>',
      '<th style="width: 220px;" title="Run the collector once per day from a start day (KST)">Backfill</th>']] },
  { name: 'the path face breaking the server sentences between any two letters', entry: 'admin.html', rule: 'words', at: 'cfg-path',
    file: 'admin.html', edits: [['      color: var(--text-dim);\n      overflow-wrap: anywhere;\n    }\n',
      '      color: var(--text-dim);\n      word-break: break-all;\n    }\n']] },
  // ⚰️ «the Retroactive list line cut without saying so» retired 10-11 (owner R): the line is chips that wrap, and the clip
  //    rule watches them now - no data-clip-ok.
  { name: 'a contents chip bringing up the card after its own', entry: 'admin.html', rule: 'contents', at: 'retroactive-sub',
    file: 'src/admin.js', edits: [['      const card = byId(\'retroactive-body\').querySelector(`article.retro-op[data-op="${CSS.escape(op.op)}"]`);',
      '      const all = [...byId(\'retroactive-body\').querySelectorAll(\'article.retro-op\')]; const card = all[(all.findIndex((c) => c.dataset.op === op.op) + 1) % all.length];']] },
  { name: 'the ledger sources table back on its hand widths (Source 150px, the timestamp the rest)', entry: 'admin.html',
    rule: 'columns', at: 'ledger-sources', file: 'src/ledger_sources_panel.js', edits: [
      ["      if (fit) th.className = 'cell-fit';", "      th.style.width = { Source: '150px', State: '130px', Refused: '70px' }[label] || '';"],
      ["    if (fit) td.className = 'cell-fit';", '']] },
  // The walk table's nine (lead 34d91c09d): what the lead saw on Edge, built back.
  { name: 'the sign bands without their colours', entry: 'walk.html', rule: 'sign colours', at: 'wk-sides',
    file: 'src/walk/styles.js', edits: [['.wk-sides th.wk-sidehead.wk-plus {', '.wk-sides th.wk-sidehead.wk-plus-gone {'],
      ['.wk-sides th.wk-sidehead.wk-minus {', '.wk-sides th.wk-sidehead.wk-minus-gone {']] },
  { name: 'a side that did not reach saying missing in its first cell only', entry: 'walk.html', rule: 'missing each', at: 'wk-sides',
    file: 'src/walk/table_view.js', edits: [['          : { text: MISSING, missing: true, col: c })),', '          : (c === 0 ? { text: MISSING, missing: true, col: c } : { text: EMPTY, col: c }))),']] },
  { name: 'sections spaced by their own margins again', entry: 'walk.html', rule: 'S2 section spaces', at: 'wk-page',
    file: 'src/walk/styles.js', edits: [['.wk-sec { display: flex; flex-direction: column; gap: var(--space-2); }', '.wk-sec { display: flex; flex-direction: column; gap: var(--space-2); margin: var(--space-3) 0 var(--space-4); }']] },
  { name: 'table cells padded --space-2 --space-3 again', entry: 'walk.html', rule: 'S3 table cells', at: 'wk-page',
    file: 'src/walk/styles.js', edits: [['  padding: var(--space-1) var(--space-2); text-align: left; vertical-align: top; }', '  padding: var(--space-2) var(--space-3); text-align: left; vertical-align: top; }']] },
  { name: 'the basket left at the end of the flow, not stuck', entry: 'walk.html', rule: 'basket at the foot', at: 'wk-page',
    file: 'src/walk/styles.js', edits: [['.wk-marked { position: sticky; bottom: 0;', '.wk-marked { position: static; bottom: 0;']] },
  { name: 'a tick throws the reader back to the top', entry: 'walk.html', rule: 'place kept', at: 'wk-page',
    file: 'src/walk/main.js', edits: [['    main.scrollTop = place.top;\n', '']] },
  { name: 'the side bands over the control colours again', entry: 'walk.html', rule: 'control colours', at: 'wk-page',
    file: 'src/walk/styles.js', edits: [['.wk-table td.is-ctl-b { box-shadow: inset 3px 0 0 var(--danger); background: var(--danger-weak); }',
      '.wk-table td.is-ctl-b { box-shadow: inset 3px 0 0 var(--danger); background: var(--danger-weak); }\n'
        + '.wk-sides td.wk-plus { background: color-mix(in srgb, var(--wk-plus) 7%, var(--bg-surface)); }\n'
        + '.wk-sides td.wk-minus { background: color-mix(in srgb, var(--wk-minus) 7%, var(--bg-surface)); }']] },
  { name: 'a «+N» tag growing its row', entry: 'walk.html', rule: 'S4 one row height', at: 'wk-page',
    file: 'src/walk/styles.js', edits: [['gap: var(--space-1); max-height: var(--space-5); }', 'gap: var(--space-1); }']] },
  { name: 'the result boxed again, off the head\'s left edge', entry: 'walk.html', rule: 'S5 one left edge', at: 'wk-page',
    file: 'src/walk/styles.js', edits: [['.wk-result { display: flex; flex-direction: column; gap: var(--space-2); }', '.wk-result { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-2) var(--space-3); border: 1px solid var(--border); }']] },
  // ⚰️ «a group head cut short» retired 10-12: the walk table is fixed-width and data-clip-ok (owner 10-12 「폭이 꿀렁꿀렁」),
  //    a head two lines each cut whole in its title (owner 10-12 «m..») - S6 skips it by design; its anchor had gone too.
  // The walk page's spacing, heights and type (lead 18da45b73), built back.
  { name: 'the parts of a section stacked with no gap', entry: 'walk.html', rule: 'stacked gaps', at: 'wk-page',
    file: 'src/walk/styles.js', edits: [['.wk-sec { display: flex; flex-direction: column; gap: var(--space-2);', '.wk-sec { display: flex; flex-direction: column; gap: 0;']] },
  // «a route row's two lines with no gap», re-aimed 10-12 (lead): the Route walked step opens through ▾, a way wraps in two.
  { name: 'a route row\'s two lines with no gap', entry: 'walk.html', rule: 'route lines apart', at: 'wk-route',
    file: 'src/walk/styles.js', edits: [['.wk-pathchain { min-width: 0; line-height: 1.25;', '.wk-pathchain { min-width: 0; line-height: 0.9;']] },
  { name: 'a walked way cut at its row\'s end again', entry: 'walk.html', rule: 'route whole', at: 'wk-route',
    file: 'src/walk/styles.js', edits: [['line-height: 1.25; overflow-wrap: anywhere;', 'line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;']] },
  { name: 'the table cells back on 5 x 8 px', entry: 'walk.html', rule: 'spacing tokens', at: 'wk-page',
    file: 'src/walk/styles.js', edits: [['  padding: var(--space-1) var(--space-2); text-align: left; vertical-align: top; }', '  padding: 5px 8px; text-align: left; vertical-align: top; }']] },
  // The testbed's start picker clipped by its panel again (lead 10-13, 18997) - its window not placed by the one
  // placement, so it hangs absolute in a panel that clips its own box (re-aimed 72b2d7f8f: tb-pops retired).
  { name: 'the start picker hung under a panel that clips it', entry: 'testbed.html', rule: 'picker reachable', at: 'wk-barpopbody',
    file: 'src/walk/start_baskets.js', edits: [["    this.place = () => { if (this.pop.open) fitUnder(body, chip, { align: 'left', gap: 3.4 }); };", '    this.place = () => {};']] },
  // The owner's (72b2d7f8f): a pill's picker dropped under its pill whatever the room - the X axis at the foot of the page.
  { name: 'the slot picker drops under its pill again, off the foot of the screen', entry: 'testbed.html', rule: 'pickers in view', at: 'sf-pop-host',
    file: 'src/testbed/picker.js', edits: [["      if (anchor && anchor.getBoundingClientRect) fitUnder(this.host, anchor, { align: 'left', gap: 4 });",
      "      if (anchor && anchor.getBoundingClientRect) { const s = anchor.getBoundingClientRect(); this.host.style.left = `${Math.max(8, Math.min(s.left, document.documentElement.clientWidth - 760))}px`; this.host.style.top = `${s.bottom + 4}px`; }"]] },
  { name: 'Copy id back at 20 px high', entry: 'walk.html', rule: 'two heights', at: 'wk-page',
    file: 'src/walk/styles.js', edits: [['.wk-copyid { height: var(--wk-h-small);', '.wk-copyid { height: 20px;']] },
  { name: 'a 12 px line again', entry: 'walk.html', rule: 'three type sizes', at: 'wk-page',
    file: 'src/walk/styles.js', edits: [['.wk-note { font-size: var(--wk-fs-line);', '.wk-note { font-size: 12px;']] },
  // ⚰️ «the table drawn without its axis in the middle» retired 10-11 with the mirrored sides (lead W): the node is first,
  //    the first column's + · Δ · − beside it - its − cell in view is still asked (− side in view).
  { name: 'the first column\'s − cell pushed past the table\'s view', entry: 'walk.html', rule: '− side in view', at: 'wk-sides',
    // The table is fixed-width (owner 10-12): a head's min-width moves nothing - the columns' own widths push it.
    file: 'src/walk/styles.js', edits: [['.wk-wide th.wk-sidehead, .wk-wide th.wk-leafhead { text-align: center; }', '.wk-wide th.wk-sidehead, .wk-wide th.wk-leafhead { text-align: center; }\n.wk-sides col.wk-col-value { width: 1600px !important; }']] },
];
async function buildMutant(m) {
  const { build } = await import('vite');
  const out = mkdtempSync(path.join(tmpdir(), 'screens-mutant-'));
  const target = path.join(CLIENT, m.file).replace(/\\/g, '/');
  const hits = new Map(m.edits.map(([a]) => [a, 0]));
  const swap = () => {
    // The anchors are written with \n; a checkout with core.autocrlf holds \r\n (10-12: every mutant past the first unrun) -
    // the file's text through the one reader (probe_mechanism P1), not a private normaliser.
    let code = readSourceText(target).text;
    for (const [a, b] of m.edits) if (code.includes(a)) { hits.set(a, hits.get(a) + 1); code = code.split(a).join(b); }
    return code;
  };
  const mine = (id) => id.split('?')[0].replace(/\\/g, '/') === target;
  await build({ root: CLIENT, configFile: path.join(CLIENT, 'vite.config.js'), logLevel: 'silent', build: { outDir: out, emptyOutDir: true },
    plugins: [{ name: 'screens-mutant', enforce: 'pre', transform: (code, id) => (mine(id) ? swap() : null),
      transformIndexHtml: { order: 'pre', handler: (html, ctx) => (mine(ctx.filename) ? swap() : html) } }] });
  for (const [a, n] of hits) if (!n) throw new Error(`mutant «${m.name}»: «${a.slice(0, 60)}» is not in ${m.file}`);
  return out;
}
if (MUTATE) {
  for (const m of MUTANTS) {
    if (only && m.entry !== only) continue;   // --only names the mutants' entry too
    ran += 1;
    const out = await buildMutant(m);
    try {
      const got = (await runScreens(out, 'mutant', m.entry)).found
        .filter((f) => f.rule === m.rule && f.path.includes(m.at) && (!m.says || m.says.test(f.what)));
      if (!got.length) failed += 1;
      console.log(`${got.length ? '✓' : '✗'} mutant «${m.name}» ${got.length ? `red: ${got[0].path} · ${got[0].what}` : `ESCAPED - no ${m.rule} line at ${m.at}`}`);
    } finally {
      removeFolder(out, 'mutant build');
    }
  }
}
console.log(`ASSERTIONS ${ran} ${failed}`);
await sleep(1500);   // the last Chrome's children let go of its profile
for (const dir of folders) removeFolder(dir, 'profile');
process.exit(failed ? 1 : 0);
