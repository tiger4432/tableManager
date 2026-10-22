#!/usr/bin/env node
// Every screen, opened in real Chrome before a screen commit lands (lead 1343e5cca; owner 10-09 「이런 잘림 같은 ui
// 요소는 사전에 차단하면 안 됨?」). Each html entry of the source, built now into a folder of this run's (lead 10-22 ㄴ - the committed dist can be a
// build behind), is opened at each size, driven through its states,
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
// Chrome hands every request here (DevTools Fetch). Files come from that build, GETs from fixtures/screens_answers.json.gz
// (capture_screens.py), the two queues from fixtures/chain_states.json; no request reaches a server of ours. A GET with
// no answer is a red line - an unanswered screen draws empty and measures nothing. Other methods are refused and
// counted; a page that leaves (a link, Log out) is answered 204 and stays. Another origin's file (the fonts, the
// admin's editor) is fetched as the page asks: without the editor the admin page stops booting, without the fonts
// every width is measured in another face.
// --mutate: the five that leaked on 10-08/09, and the ledger table's hand widths (owner 10-09), are built back one at a
// time (vite, a temp folder) and each must be red.
//   node client2/tests/screen_layout_harness.mjs [--mutate] [--only <entry.html>] [--shots <dir>]
import { spawn, execFileSync } from 'node:child_process';
import { readFileSync, existsSync, mkdtempSync, rmSync, readdirSync, writeFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readSourceText } from './lib/probe.mjs';
import { QUEUE_POLL_MS } from '../src/queue_poll.js';

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
const RULES = ['clip', 'overflow', 'panel', 'text', 'size', 'centre', 'heights', 'columns', 'words', 'built now'];
// This run's mark on every bundle it builds (lead 10-22 ㄴ): a page without it was built by someone else - the committed
// dist a build behind its source (prebuild runs before vite) or another run's.
const STAMP = `${process.pid}-${Date.now()}`;
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
// The worker's statement-limit sentence (_said_timeout), on a retrying line of both queues and on the failed list's line
// and record (lead 903053c14, owner 10-21 «빨간 글씨 600 s 나오고 끝»).
const TIMEOUT = '[rules=lot_slot_join target=dt_wafer] statement timeout · 600 s · stage write:dt_wafer - one statement '
  + 'of this group ran past chain_statement_timeout_seconds (ingestion_settings.json); the database stopped it';
const TIMED_OUT = { state: 'retrying', why: { attempt: 1, cap: 2, stage: 'write:dt_wafer', last_failure: TIMEOUT } };
// Each line's rules (3de34d292): a running line's rule its rows in and seconds, the timed-out line's its last run's rows.
const RULES_OF = (state) => [state === TIMED_OUT ? { rule: 'lot_slot_join', rows_in: 19000, rows_out: 20000, running_seconds: null }
  : state.state === 'running' ? { rule: 'dt_log_to_dt_map', rows_in: 500, rows_out: null, running_seconds: 72 }
  : { rule: 'dt_log_to_dt_map', rows_in: null, rows_out: null, running_seconds: null }];
const LINES = [...STATES.map((s) => s.chain_state), TIMED_OUT];
const QUEUE = {
  '/outbox/queue/rows': {
    generated_at: '2026-10-08 20:00:00', clock: 'server', rules_known: ['dt_log_to_dt_map'],
    listed: { cap: 200, next_cursor: null }, population: 'processed_chain=false',
    rows: LINES.map((state, i) => ({ outbox_id: 300 + i, event_type: 'EDIT', table_name: tableOf(i), created_at: '2026-10-08 19:59:00',
      waiting_seconds: 60, owner: 'chain', chain_state: state, broadcast_state: 'pending',
      rules: [{ name: 'dt_log_to_dt_map', will_fire: true }] })),
  },
  '/admin/chain/queue': {
    waiting: LINES.length, oldest_waiting_seconds: 60, waiting_by_owner: [], retried_among_waiting: 0,
    loop_seen_via: 'this_process', generated_at: '2026-10-08T20:00:00+09:00', now_running: [],
    waiting_transactions: LINES.map((state, i) => ({ transaction_id: `tx-${i}-0000-0000`, events: 1, rows: 1, tables: [tableOf(i)],
      waiting_seconds: 60, cancel: { key: `tx:${i}` }, chain_state: state, slot_pid: 4242, rules: RULES_OF(state) })),
    recent_failures: [
      { transaction_id: 'tx-timeout-0000-0000', rules: ['lot_slot_join'], tables: ['dt_wafer'], stage: 'write:dt_wafer', rows_in: 19000,
        rows_out: 20000, rows: 19000, failure: TIMEOUT, failed_at: '2026-10-21 17:00:00' },
      { transaction_id: 'single_e-2', rules: null, tables: null, stage: null, rows_in: null, rows_out: null, rows: null,
        failure: 'ValueError: no wafer', failed_at: '2026-10-21 16:40:00' }],
    recent_failures_listed: { cap: 20, capped: false },
  },
  '/admin/outbox/failed': (() => {
    const at = '2026-10-21T17:00:00+09:00';
    const record = { failed_at: at, reason: TIMEOUT, rules: ['lot_slot_join'], tables: ['dt_wafer'], rows: 19000, row: null };
    return { status: 'success', total: 1, page: 1, limit: 10, oldest_failed_at: at, day_zone: 'Asia/Seoul',
      summary: [
        { table_name: 'dt_wafer', event_type: 'EDIT', day: '2026-10-21', count: 19000, first_at: '2026-10-21T16:50:00+09:00',
          last_at: at, retry_max: 1, last_failure: TIMEOUT },
        { table_name: 'dt_log', event_type: 'CREATE', day: '2026-10-20', count: 2, first_at: at, last_at: at, retry_max: 0 }],
      data: [{ transaction_id: 'tx-timeout-0000-0000', table_names: ['dt_wafer'], event_types: ['EDIT'], retry_count: 1,
        attempts_this_round: 1, failed_at: at, events: [{ id: 1, event_uuid: 'e-1', event_type: 'EDIT', table_name: 'dt_wafer',
          payload: { transaction_id: 'tx-timeout-0000-0000', error_log: record }, status: 'FAILED', retry_count: 1,
          attempts_this_round: 1, created_at: at, processed_at: at }] }] };
  })(),
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
// The main grid's gallery (lead 3589216b9): while its states run, dt_log is read with an image column «photo» - a picture on
// every row but every seventh - and its rows and count narrowed by the grid's filters the way the server narrows them.
const GALLERY = { on: false };
// The declaration read refused the way the server refuses it (lead 06d7ca89e): 503, its sentence in detail.message.
const DECL_REFUSED = { on: false };
// The main grid pivoted (owner 10-22): while its states run, dt_log declares a pivot (item column b_wy, value dt_index)
// and a pivot read answers 40 key groups of eight items - two long names, three more held back, some cells blank.
const PIVOT = { on: false };
const PIVOT_DECL = { column: 'b_wy', value: 'dt_index' };
const PIVOT_ITEMS = ['THK_CENTER', 'THK_EDGE', 'BOW', 'WARP', 'TTV', 'SORI', 'THICKNESS_VARIATION_EDGE_EXCL_3MM', 'FLATNESS_SFQR_MAX_26X8'];
const pivotValue = (i, k) => Number((10 + ((i * 7 + k * 3) % 50) / 7).toFixed(2));
// Apply's read again in pivot view (lead 10-23 ㄱ): each long row asked by id («pv-<group>-<item>») at its value, moved by
// one since the edit, or gone - as PIVOT_LONG.mode says. A group id finds nothing.
const PIVOT_LONG = { mode: 'same' };
const pivotLongRows = (filters) => ((filters.row_id || {}).conditions || [])
  .map((c) => /^pv-(\d+)-(\d+)$/.exec(String(c.filter))).filter((m) => m && PIVOT_LONG.mode !== 'gone')
  .map(([id, i, k]) => ({ row_id: id, data: { dt_job: { value: `JOB-${String(Math.floor(i / 8) + 1).padStart(3, '0')}` }, b_wx: { value: i % 8 },
    b_wy: { value: PIVOT_ITEMS[k] }, dt_index: { value: pivotValue(Number(i), Number(k)) + (PIVOT_LONG.mode === 'moved' ? 1 : 0) } } }));
const pivotAnswer = (u) => {
  if (u.pathname === '/tables/dt_log/schema') {
    const a = ANSWERS['/tables/dt_log/schema'];
    return { ...a, body: { ...bodyOf(a), pivot: PIVOT_DECL } };
  }
  if (u.pathname === '/tables/dt_log/data' && u.searchParams.get('pivot') !== 'true') {
    const filters = JSON.parse(u.searchParams.get('filters') || '{}');
    if (filters.row_id) return { status: 200, type: 'application/json', body: { table_name: 'dt_log', total: null, data: pivotLongRows(filters) } };
  }
  if (u.searchParams.get('pivot') !== 'true') return null;
  if (u.pathname === '/tables/dt_log/data/count') return { status: 200, type: 'application/json', body: { table_name: 'dt_log', total: 40 } };
  if (u.pathname !== '/tables/dt_log/data') return null;
  const skip = Number(u.searchParams.get('skip') || 0);
  const limit = Number(u.searchParams.get('limit') || 1000);
  const groups = Array.from({ length: 40 }, (_, i) => ({ dt_job: `JOB-${String(Math.floor(i / 8) + 1).padStart(3, '0')}`, b_wx: i % 8,
    cells: Object.fromEntries(PIVOT_ITEMS.map((item, k) => [item, { value: pivotValue(i, k), row_id: `pv-${i}-${k}` }])
      .filter((_, k) => (i + k) % 9 !== 0)) }));
  return { status: 200, type: 'application/json', body: { table_name: 'dt_log', total: null, skip, limit,
    pivot: { ...PIVOT_DECL, keys: ['dt_job', 'b_wx'], items: PIVOT_ITEMS, items_more: 3 }, data: groups.slice(skip, skip + limit) } };
};
const DECL_SENTENCE = 'The declaration could not be read: no ledger configuration at C:/assy/config/ledger_config.json - fix the declaration and reload';
const DT_LOG_ROWS = '/tables/dt_log/data?skip=0&limit=1000&order_by=updated_at&order_desc=true&defer_total=true';
const galleryAnswer = (u) => {
  if (u.pathname === '/tables/dt_log/schema') {
    const a = ANSWERS['/tables/dt_log/schema'];
    const b = bodyOf(a);
    return { ...a, body: { ...b, columns: [...b.columns.slice(0, -3), 'photo', ...b.columns.slice(-3)], column_types: { ...b.column_types, photo: 'image' } } };
  }
  if (u.pathname !== '/tables/dt_log/data' && u.pathname !== '/tables/dt_log/data/count') return null;
  const a = ANSWERS[DT_LOG_ROWS];
  const b = bodyOf(a);
  const filters = JSON.parse(u.searchParams.get('filters') || '{}');
  const valueOf = (row, col) => { const c = row.data && row.data[col]; return c && typeof c === 'object' ? c.value : c; };
  const rows = b.data.map((row, i) => ({ ...row, data: { ...row.data, photo: { ...(row.data.c_bn || {}), value: i % 7 === 3 ? null : `photo/${i}.png` } } }))
    .filter((row) => Object.entries(filters).every(([col, f]) => {
      const v = valueOf(row, col);
      if (f.type === 'blank') return v === null || v === undefined || String(v).trim() === '';
      return f.type === 'equals' ? String(v) === String(f.filter) : true;
    }));
  if (u.pathname.endsWith('/count')) return { status: 200, type: 'application/json', body: { table_name: 'dt_log', total: Object.keys(filters).length ? rows.length : bodyOf(ANSWERS['/tables/dt_log/data/count']).total } };
  return { ...a, body: { ...b, data: rows } };
};
const answerOf = (u) => {
  if (GALLERY.on) { const g = galleryAnswer(u); if (g) return g; }
  if (PIVOT.on) { const v = pivotAnswer(u); if (v) return v; }
  if (DECL_REFUSED.on && u.pathname === '/api/ledger/declaration') {
    return { status: 503, type: 'application/json', body: { detail: { reason: 'declaration_unreadable', message: DECL_SENTENCE } } };
  }
  for (const [p, body] of Object.entries(QUEUE)) if (u.pathname === p) return { status: 200, type: 'application/json', body };
  const a = ANSWERS[u.pathname + u.search];
  const got = a && a.same_as ? ANSWERS[a.same_as] : a || null;
  return got && PHOTOS.on && u.pathname === '/api/ledger/subgraph' ? withPhotos(got) : got;
};
// One pivot item cell edited with Tx on and applied (lead 10-23 ㄱ), Apply's read again answered as `mode` says; a staged
// edit left by the state before is discarded first. Ends when Apply has said how it ended.
async function pivotEditApplied(c, mode) {
  await evaluate(c, `(() => { const d = [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Discard' && !b.disabled);
    if (d) d.click(); return true; })()`);
  await sleep(900);
  PIVOT_LONG.mode = mode;
  await evaluate(c, `(() => {
    const cell = document.querySelector('.ag-center-cols-container .ag-row[row-index="1"] .ag-cell[col-id^="item:"]');
    if (!cell) return false;
    const r = cell.getBoundingClientRect();
    const o = { bubbles: true, cancelable: true, clientX: r.x + 5, clientY: r.y + 5, view: window };
    for (const type of ['mousedown', 'mouseup', 'click']) cell.dispatchEvent(new MouseEvent(type, o));
    cell.dispatchEvent(new MouseEvent('dblclick', { ...o, detail: 2 }));
    return true; })()`);
  await until(c, "!!document.querySelector('.ag-cell-inline-editing input')");
  await evaluate(c, `(() => {
    const input = document.querySelector('.ag-cell-inline-editing input');
    input.value = '12.5'; input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
    return true; })()`);
  await until(c, "/pending/.test((document.querySelector('#performance-log') || {}).textContent || '')");
  await evaluate(c, `(() => { const b = [...document.querySelectorAll('button')].find((x) => x.textContent.trim() === 'Apply' && !x.disabled);
    if (b) b.click(); return Boolean(b); })()`);
  await until(c, "!/Checking|pending/.test((document.querySelector('#performance-log') || {}).textContent || '')"
    + " || getComputedStyle(document.getElementById('tx-conflict-line')).display !== 'none'");
  await sleep(900);
}
// Cells one screen asks of itself after one of its states, at every size; each answers null or why it is red.
const CELLS = [
  // The declaration form is one grid (lead 10-21, form D): on the sample page a 40-letter name three levels down is
  // whole in its cell, and every row's value stands at one x. At the stacked width the rows have no columns.
  { entry: 'sample.html', after: 'Ledger declaration, list open, light', sizes: ['1024x768'], rule: 'names whole, columns in line',
    at: 'sample-decl-form', expr: `(() => {
  const rows = [...document.querySelectorAll('#sample-decl-form .oe-node-row')].filter((r) => r.getClientRects().length);
  if (rows.length < 6) return 'the sample form drew ' + rows.length + ' rows';
  const cut = [...document.querySelectorAll('#sample-decl-form .oe-node-name')].find((e) => e.scrollWidth > e.clientWidth + 1);
  if (cut) return '«' + cut.textContent + '» ' + cut.clientWidth + ' of ' + cut.scrollWidth + ' px';
  const xs = new Set(rows.map((r) => [...r.children].find((c) => c.classList.contains('oe-node-value'))).filter(Boolean)
    .map((c) => Math.round(c.getBoundingClientRect().left)));
  if (xs.size !== 1) return 'oe-node-value at ' + [...xs].join(' · ') + ' px';
  return null;
})()` },
  // The form's rows (lead 10-21, skill §0-bis): every row a whole number of row steps (a box and a step) high and the
  // chip lines it holds that many, no gap between rows, every first box one box high at one x with its text at one x,
  // a one-line row's name and box (and the box's text) on the row's middle within 1 px, and a row's word beside its
  // box, never over it (order da59efbb7, owner «require 뱃지랑 input ui 겹치는거»).
  { entry: 'sample.html', after: 'Ledger declaration, list open, light', sizes: ['1024x768'], rule: 'rows one height, boxes at one x',
    at: 'sample-decl-form', expr: `(() => {
  const rows = [...document.querySelectorAll('#sample-decl-form .oe-node-row')].filter((r) => r.getClientRects().length);
  const css = getComputedStyle(document.documentElement);
  const box = parseFloat(css.getPropertyValue('--control-h-small')), unit = box + parseFloat(css.getPropertyValue('--space-2'));
  const R = (e) => e.getBoundingClientRect(), mid = (b) => (b.top + b.bottom) / 2, say = (e) => '«' + e.textContent.trim().slice(0, 24) + '»';
  const probe = document.createElement('div');
  probe.style.width = 'var(--oe-box-w)';
  document.querySelector('#sample-decl-form .oe-skeleton-form').append(probe);
  const boxW = R(probe).width;
  probe.remove();
  if (!(boxW > 0)) return 'the box width token reads ' + boxW;
  const textOf = (e) => { const w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT); for (let t = w.nextNode(); t; t = w.nextNode()) if (t.textContent.trim()) { const g = document.createRange(); g.selectNodeContents(t); return g.getBoundingClientRect(); } return null; };
  const seen = { chips: 0, folded: 0, deep: 0, word: 0, table: 0 }, lefts = new Set(), texts = new Set();
  const tables = [...document.querySelectorAll('#sample-decl-form .oe-node-table')].filter((t) => t.getClientRects().length);
  for (const t of tables) {
    const n = Math.round(R(t).height / unit);
    if (n < 1 || Math.abs(R(t).height - n * unit) > 0.5) return 'table ' + say(t) + ' ' + R(t).height.toFixed(1) + ' px, not a whole number of ' + unit.toFixed(1);
  }
  // A row that opens a top-level block stands below its divider: the block's margin, its line and its padding (lead 10-21).
  const divider = (r) => { const n = r.parentElement; if (!n || n.firstElementChild !== r) return 0; const s = getComputedStyle(n);
    const line = parseFloat(s.borderTopWidth) || 0; return line ? parseFloat(s.marginTop) + line + parseFloat(s.paddingTop) : 0; };
  let prev = null;
  for (const r of rows) {
    const rb = R(r), k = Math.round(rb.height / unit);
    if (k < 1 || Math.abs(rb.height - k * unit) > 0.5) return 'row ' + say(r) + ' ' + rb.height.toFixed(1) + ' px, not a whole number of ' + unit.toFixed(1);
    const under = prev && tables.find((t) => Math.abs(R(t).top - R(prev).bottom) <= 0.5 && Math.abs(R(t).bottom - rb.top) <= 0.5);
    seen.table += under ? 1 : 0;
    if (prev && !under && Math.abs(rb.top - R(prev).bottom - divider(r)) > 0.5) return 'row ' + say(r) + ' ' + (rb.top - R(prev).bottom).toFixed(1) + ' px below the row above';
    prev = r;
    const cell = r.querySelector(':scope > .oe-node-value'), b = cell && cell.firstElementChild;
    const chips = b && b.classList.contains('oe-chips') ? b : null;
    const lines = chips ? new Set([...chips.children].map((c) => Math.round(R(c).top))).size : 1;
    if (k !== lines) return 'row ' + say(r) + ' ' + k + ' steps high for ' + lines + ' line(s)';
    seen.chips += chips && lines > 1 ? 1 : 0; seen.folded += r.classList.contains('is-folded') ? 1 : 0; seen.deep += Number(r.dataset.depth) >= 3 ? 1 : 0;
    if (!b) continue;
    const first = chips ? chips.firstElementChild : b, fb = R(first), fs = getComputedStyle(first);
    if (Math.abs(fb.height - box) > 0.5) return 'box ' + say(first) + ' ' + fb.height.toFixed(1) + ' px high, not ' + box;
    if (first.classList.contains('oe-box') && Math.abs(fb.width - Math.min(boxW, R(cell).width)) > 0.5) return 'box ' + say(first) + ' ' + fb.width.toFixed(1) + ' px wide, not ' + boxW.toFixed(1);
    lefts.add(Math.round(fb.left));
    texts.add(Math.round(fb.left + parseFloat(fs.borderLeftWidth) + parseFloat(fs.paddingLeft)));
    const word = cell.querySelector(':scope > .oe-tier');
    if (word) {
      seen.word += 1;
      const wb = R(word);
      if (wb.left < fb.right - 0.5 && wb.right > fb.left + 0.5) return 'the word ' + say(word) + ' over its box ' + say(first) + ' by ' + (fb.right - wb.left).toFixed(1) + ' px';
    }
    const glyphs = textOf(first);
    if (glyphs && Math.abs(mid(glyphs) - mid(fb)) > 1) return 'the text of ' + say(first) + ' ' + (mid(glyphs) - mid(fb)).toFixed(1) + ' px off its box middle';
    if (k > 1) continue;
    for (const c of [r.querySelector(':scope > .oe-node-label .oe-node-name'), first].filter(Boolean)) {
      if (Math.abs(mid(R(c)) - mid(rb)) > 1) return say(c) + ' ' + (mid(R(c)) - mid(rb)).toFixed(1) + ' px off its row middle';
    }
  }
  if (lefts.size !== 1) return 'boxes start at ' + [...lefts].join(' · ') + ' px';
  if (texts.size !== 1) return 'box text starts at ' + [...texts].join(' · ') + ' px';
  if (!seen.chips || !seen.folded || !seen.deep || !seen.word || !seen.table) return 'the sample form lacks ' + Object.keys(seen).filter((n) => !seen[n]).join(', ') + ' (else this proves nothing)';
  return null;
})()` },
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
// The side panel's lit tab is the pane it shows (owner 10-21 「탭은 글로벌인데 가끔 대기열 따로 있네」): after the row pick
// under Queue, a queue beat, a row picked on the open queue and a table switched from it.
for (const after of ['row picked, Queue tab', 'Queue tab, a beat later', 'a row picked under the Queue tab', 'table switched from the Queue tab',
  'the first table again']) {
  CELLS.push({ entry: 'index.html', after, rule: 'lit tab shows its pane', at: 'history-sidebar', expr: `(() => {
  const paneOf = { 'tab-global': 'timeline-container', 'tab-row': 'timeline-container', 'tab-reference': 'reference-view', 'tab-queue': 'queue-view' };
  const lit = [...document.querySelectorAll('.history-sidebar .history-tabs > .tab-btn.active')].map((b) => b.id);
  const shown = ['timeline-container', 'reference-view', 'queue-view']
    .filter((id) => { const p = document.getElementById(id); return p && getComputedStyle(p).display !== 'none'; });
  if (lit.length !== 1) return 'tabs lit: ' + (lit.join(' ') || 'none');
  if (shown.length !== 1 || shown[0] !== paneOf[lit[0]]) return 'tab «' + lit[0] + '» lit, pane shown: ' + (shown.join(' ') || 'none');
  return '';
})()` });
}
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
  const lines = [...document.querySelectorAll('.sf-table--images tr')].filter((tr) => tr.querySelector('td') && !tr.classList.contains('tb-table__pad'));
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
// The chain form (lead after a2b7f6e14 · owner 10-21 「선언에 체인 칼럼 타겟 없는데」): target_columns stands on the first
// screen, not under Advanced, in either grammar; a take record's fn picks from the four the rule answer carries.
const TARGET_COLUMNS_FIRST = `(() => {
  const box = document.querySelector('.chain-rule-form [data-path="target_columns"]');
  if (!box) return 'target_columns is not drawn';
  if (box.closest('.chain-rule-advanced')) return 'target_columns is under Advanced';
  return box.getClientRects().length ? null : 'target_columns is drawn hidden';
})()`;
for (const after of ['Chain, a join whose take holds a record', 'Chain, a flat rule']) {
  CELLS.push({ entry: 'admin.html', after, rule: 'contents', at: 'target_columns', expr: TARGET_COLUMNS_FIRST });
}
CELLS.push({ entry: 'admin.html', after: 'Chain, + then record on the take', rule: 'contents', at: 'derive.join.take', expr: `(() => {
  const words = (at) => { const s = document.querySelector('select[data-value="' + at + '"]');
    return s ? [...s.options].map((o) => o.value).filter(Boolean).join(',') : 'no picker'; };
  const want = 'count,min,max,unique_concat';
  for (const at of ['derive.join.take[1].fn', 'derive.join.take[2].fn']) if (words(at) !== want) return at + ' offers ' + words(at);
  const held = document.querySelector('select[data-value="derive.join.take[1].fn"]').value;
  return held === 'unique_concat' ? null : 'take[1].fn holds ' + held;
})()` });
// The gallery's board (lead 3589216b9): a line's cells add up to its total and the totals to the rows held; a cell opened
// lays out as many tiles as its rows with a picture; Filter grid to this cell puts the line's and the column's columns on
// the grid's filter.
// The row checkboxes and the header's select-all at the grid's left edge with the first data column hidden (owner 10-22).
CELLS.push({ entry: 'index.html', after: 'first column hidden', rule: 'select all at the left', at: 'ag-header', expr: `(() => {
  const gone = window.__hiddenFirst;
  if (!gone || gone === '#' || /^\\d+$/.test(gone)) return 'the column hidden is not a data column (' + gone + ')';
  if (document.querySelector('.ag-header-cell[col-id="' + gone + '"]')) return 'the first column was not hidden (' + gone + ')';
  const shown = (el) => el && el.getClientRects().length && !el.closest('.ag-hidden');
  const all = document.querySelector('.ag-header .ag-header-select-all');
  if (!shown(all)) return 'no select-all checkbox in the header';
  const rows = [...document.querySelectorAll('.ag-row .ag-selection-checkbox')].filter(shown);
  if (!rows.length) return 'no row checkbox';
  const left = document.querySelector('.ag-root').getBoundingClientRect().left;
  const at = all.closest('.ag-header-cell').getBoundingClientRect().left;
  return at - left > 2 ? 'the select-all checkbox stands ' + Math.round(at - left) + ' px from the left edge of the grid' : null;
})()` });
// The row a click picks is selected, as it was (owner 10-22: the selection moved to its own column, its click kept).
CELLS.push({ entry: 'index.html', after: 'a row picked under the Queue tab', rule: 'a click selects its row', at: 'ag-row', expr: `(() => {
  const row = document.querySelector('.ag-center-cols-container .ag-row[row-index="1"]');
  if (!row) return 'no row 1';
  return row.classList.contains('ag-row-selected') ? null : 'row 1 was clicked and is not selected';
})()` });
// The grid pivoted (owner 10-22): an item's column headed by the item alone, the footer counting groups, the items held
// back said, «Pivot» pressed - and all of it undone when it is pressed again; no «Pivot» on a table that declares none.
CELLS.push({ entry: 'index.html', after: 'Pivot on', rule: 'pivot drawn', at: 'pivot', expr: `(() => {
  const heads = [...document.querySelectorAll('.ag-header-row-column .ag-header-cell[col-id^="item:"]')];
  // the grid draws the columns in view only - the item columns drawn, each one of the answer's items
  const items = ${JSON.stringify(PIVOT_ITEMS)};
  if (!heads.length) return 'no item column';
  const stray = heads.find((h) => !items.includes(h.getAttribute('col-id').slice(5)));
  if (stray) return 'an item column not in the answer: ' + stray.getAttribute('col-id');
  const named = heads.find((h) => (h.querySelector('.ag-header-cell-text') || h).textContent.trim() !== h.getAttribute('col-id').slice(5));
  if (named) return 'an item header says «' + named.textContent.trim() + '»';
  const total = (document.getElementById('total-rows') || {}).textContent || '';
  if (!total.includes(' group')) return 'the footer says «' + total + '»';
  const more = document.getElementById('pivot-more-line');
  if (!more || more.hidden || more.textContent.trim() !== '3 more items not shown') return 'the held-back line: «' + (more ? more.textContent : 'none') + '»';
  const b = document.getElementById('pivot-toggle-btn');
  return b && b.getAttribute('aria-pressed') === 'true' ? null : 'Pivot is not pressed';
})()` });
// Part ② (lead 10-22): in pivot view cells are written many at a time and the transaction is open; rows are not.
CELLS.push({ entry: 'index.html', after: 'Pivot on', rule: 'pivot writes', at: 'pivot', expr: `(() => {
  const add = document.getElementById('add-row-btn');
  if (!add || !add.disabled || add.getAttribute('title') !== 'Rows are added and deleted with Pivot off') return 'Add Row: ' + (add ? add.disabled + ' «' + add.getAttribute('title') + '»' : 'none');
  const tx = document.getElementById('tx-mode-toggle');
  return tx && !tx.disabled ? null : 'the transaction toggle is shut in pivot view';
})()` });
// lead 10-23 ㄱ: Apply in pivot view with Tx on writes the long row; a long row changed since asks; one gone drops the edit.
CELLS.push({ entry: 'index.html', after: 'Pivot, an edit applied', rule: 'pivot apply writes', at: 'pivot', expr: `(() => {
  const said = (document.getElementById('performance-log') || {}).textContent || '';
  return /^Applied batch updates .*\\(1 cells updated\\)/.test(said) ? null : 'Apply ended «' + said + '»';
})()` });
CELLS.push({ entry: 'index.html', after: 'Pivot, an edit over a changed row', rule: 'pivot apply asks', at: 'pivot', expr: `(() => {
  const line = document.getElementById('tx-conflict-line');
  const text = (document.getElementById('tx-conflict-text') || {}).textContent || '';
  return line && getComputedStyle(line).display !== 'none' && text === '1 cell changed on the server since you edited' ? null
    : 'no question - «' + text + '» · ' + ((document.getElementById('performance-log') || {}).textContent || '');
})()` });
CELLS.push({ entry: 'index.html', after: 'Pivot, an edit of a gone row', rule: 'pivot apply drops', at: 'pivot', expr: `(() => {
  const said = (document.getElementById('performance-log') || {}).textContent || '';
  return said === 'Nothing applied · 1 staged edit dropped (row deleted)' ? null : 'Apply ended «' + said + '»';
})()` });
CELLS.push({ entry: 'index.html', after: 'Pivot off', rule: 'pivot undone', at: 'pivot', expr: `(() => {
  const add = document.getElementById('add-row-btn');
  if (add && add.getAttribute('title') === 'Rows are added and deleted with Pivot off') return 'Add Row still says the pivot';
  if (document.querySelector('.ag-header-cell[col-id^="item:"]')) return 'an item column is left';
  const total = (document.getElementById('total-rows') || {}).textContent || '';
  if (total.includes(' group')) return 'the footer still says «' + total + '»';
  const more = document.getElementById('pivot-more-line');
  if (more && !more.hidden) return 'the held-back line is left';
  const b = document.getElementById('pivot-toggle-btn');
  return b && !b.hidden && b.getAttribute('aria-pressed') === 'false' ? null : 'Pivot is not drawn unpressed';
})()` });
CELLS.push({ entry: 'index.html', after: 'loaded', rule: 'pivot only where declared', at: 'pivot', expr: `(() => {
  const b = document.getElementById('pivot-toggle-btn');
  return b && b.hidden ? null : 'Pivot is drawn on a table that declares none';
})()` });
// A refused declaration read: the header's label says the server's sentence, not «server refused (503)» (lead 06d7ca89e).
CELLS.push({ entry: 'index.html', after: 'declaration refused, page opened again', rule: 'server sentence said', at: 'grid-source-label', expr: `(() => {
  const l = document.querySelector('#grid-source-label-host .grid-source-label');
  if (!l) return 'no header label';
  const said = l.textContent.trim();
  return said.includes(${JSON.stringify(DECL_SENTENCE)}) ? null : 'the label says «' + said + '»';
})()` });
CELLS.push({ entry: 'index.html', after: 'Gallery, rows by columns', rule: 'board adds up', at: 'gallery-board', expr: `(() => {
  const grid = document.querySelector('#gallery-host .gallery-board__grid');
  if (!grid) return 'no board drawn';
  const lines = new Map();
  for (const c of grid.querySelectorAll('.gallery-cell')) lines.set(c.dataset.line, (lines.get(c.dataset.line) || 0) + Number(c.querySelector('.gallery-cell__n').textContent.replace(/,/g, '')));
  const totals = [...grid.querySelectorAll('.gallery-board__total')].map((n) => Number(n.textContent.replace(/,/g, '')));
  const sums = [...lines.values()];
  const held = Number(((document.querySelector('#gallery-host .gallery-count') || {}).textContent || '').replace(/,/g, '').match(/^\\d+/));
  const cols = new Set([...grid.querySelectorAll('.gallery-cell')].map((c) => c.dataset.column)).size;
  if (lines.size < 2 || cols < 4) return lines.size + ' lines, ' + cols + ' columns drawn';
  if (sums.join() !== totals.join()) return 'cells add up to ' + sums.join(' · ') + ', totals ' + totals.join(' · ');
  if (totals.reduce((a, b) => a + b, 0) !== held) return 'totals ' + totals.reduce((a, b) => a + b, 0) + ' of ' + held + ' rows held';
  if (grid.querySelectorAll('.gallery-board__col').length !== cols + 1) return grid.querySelectorAll('.gallery-board__col').length + ' column heads for ' + cols + ' columns';
  return null;
})()` });
// A cell's thumbnail fills its share of the cell, its ratio kept (lead 10-22): the picture is read at 160 px and a share
// at the column's cap is wider - a picture held at its own size stood small in its box.
CELLS.push({ entry: 'index.html', after: 'Gallery, rows by columns', rule: 'thumbs fill', at: 'gallery-cell__thumb', expr: `(() => {
  const imgs = [...document.querySelectorAll('#gallery-host .gallery-cell__thumb img')].filter((i) => i.complete && i.naturalWidth > 0);
  if (!imgs.length) return 'no thumbnail loaded';
  for (const i of imgs) {
    const box = i.closest('.gallery-cell__thumb').getBoundingClientRect();
    const r = i.getBoundingClientRect();
    if (Math.abs(r.width - box.width) > 1 && Math.abs(r.height - box.height) > 1) return 'a ' + i.naturalWidth + ' x ' + i.naturalHeight + ' picture drawn ' + Math.round(r.width) + ' x ' + Math.round(r.height) + ' in a ' + Math.round(box.width) + ' x ' + Math.round(box.height) + ' box';
  }
  return null;
})()` });
CELLS.push({ entry: 'index.html', after: 'Gallery, a cell opened and a tile pressed', rule: 'opened cell tiles', at: 'gallery-open', expr: `(() => {
  const words = ((document.querySelector('#gallery-host .gallery-open__n') || {}).textContent || '').replace(/,/g, '');
  const m = words.match(/^(\\d+) rows?(?: · (\\d+) without image)?$/);
  if (!m) return 'the opened head says «' + words + '»';
  const want = Number(m[1]) - Number(m[2] || 0);
  const scroll = document.querySelector('#gallery-host .gallery-scroll');
  if (scroll) { scroll.scrollTop = scroll.scrollHeight; scroll.dispatchEvent(new Event('scroll')); }
  const tiles = document.querySelectorAll('#gallery-host .gallery-tile').length;
  const side = document.querySelector('#gallery-host .gallery-side');
  if (tiles !== want && tiles < 12) return tiles + ' tiles for ' + want + ' rows with a picture';
  if (!side || side.hidden) return 'no side panel after a tile pressed';
  return null;
})()` });
CELLS.push({ entry: 'index.html', after: 'Gallery, filtered to a cell', rule: 'filter set', at: 'filter-chip', expr: `(() => {
  const chips = [...document.querySelectorAll('.filter-chip-label')].map((n) => n.textContent.toLowerCase());
  for (const col of ['c_bn', 'core_lot']) if (!chips.some((t) => t.includes(col))) return 'no «' + col + '» filter on the grid: ' + JSON.stringify(chips);
  const cells = document.querySelectorAll('#gallery-host .gallery-cell:not(.is-empty)').length;
  if (cells !== 1) return cells + ' cells with rows after the grid was filtered to one';
  return null;
})()` });
// A failure sentence is the server's, whole (lead 903053c14): the failed list's line, the queue's timeout line and the
// newest failed groups say it as sent, and it reads to its end or to three lines with the whole of it in its title -
// never one line cut; a line's rules say their rows (3de34d292).
CELLS.push({ entry: 'admin.html', after: 'Chain', rule: 'reason whole', at: 'fail-summary__reason', expr: `(() => {
  const want = ${JSON.stringify(TIMEOUT)};
  const line = [...document.querySelectorAll('#chain-fail-summary-mount .fail-summary__reason')];
  const why = [...document.querySelectorAll('#chain-queue-mount .queue-line-state-why')].filter((e) => e.textContent.includes('timeout'));
  const recent = [...document.querySelectorAll('#chain-queue-mount .chain-queue-failure')].filter((e) => e.textContent.includes('timeout'));
  if (line.length !== 1 || why.length !== 1 || recent.length !== 1) return line.length + ' failed-list sentences, ' + why.length + ' queue timeout whys, ' + recent.length + ' recent failures';
  const rules = [...document.querySelectorAll('#chain-queue-mount .chain-queue-rule')].map((e) => e.textContent);
  for (const said of ['lot_slot_join · in 19,000 · out 20,000', 'dt_log_to_dt_map · in 500 · running 1m 12s']) if (!rules.includes(said)) return 'no rule line «' + said + '»: ' + JSON.stringify(rules.slice(0, 3));
  for (const [el, whole] of [[line[0], want], [why[0], 'attempt 1/2 · write:dt_wafer · ' + want], [recent[0], want]]) {
    if (el.textContent.trim() !== whole || el.getAttribute('title') !== whole) return '«' + el.textContent.trim().slice(0, 48) + '» drawn, title «' + (el.getAttribute('title') || '').slice(0, 24) + '»';
    const s = getComputedStyle(el);
    const lines = Math.round(el.clientHeight / (parseFloat(s.lineHeight) || parseFloat(s.fontSize) * 1.2));
    if (el.scrollWidth > el.clientWidth + 1) return '«' + whole.slice(0, 24) + '» cut at its side, ' + lines + ' line(s)';
    if (el.scrollHeight > el.clientHeight + 1 && lines < 3) return '«' + whole.slice(0, 24) + '» cut at ' + lines + ' line(s)';
  }
  return null;
})()` });
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
  // the base layer's two (lead f3639d4a2: walk's own 44 / 28 moved onto them)
  const token = (n) => parseFloat(getComputedStyle(document.documentElement).getPropertyValue(n));
  const big = token('--control-h'), small = token('--control-h-small');
  const bad = new Map();
  for (const el of page.querySelectorAll('button, select, input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"])')) {
    if (!mine(el)) continue;
    const h = el.getBoundingClientRect().height;
    if (Math.abs(h - big) > 1 && Math.abs(h - small) > 1) tally(bad, Math.round(h) + 'px', el);
  }
  return bad.size ? 'a control neither --control-h (' + big + ') nor --control-h-small (' + small + ') high: ' + said(bad) : null;
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

// What listens on a port, by process name - for the sentence a Chrome that did not answer leaves (lead 10-22).
const holderOf = (port) => {
  try {
    return execFileSync('powershell', ['-NoProfile', '-Command', `$c = Get-NetTCPConnection -State Listen -LocalPort ${port} -ErrorAction SilentlyContinue | `
      + `Select-Object -First 1; if ($c) { (Get-Process -Id $c.OwningProcess).ProcessName + ' pid ' + $c.OwningProcess } else { 'nothing' }`], { encoding: 'utf8' }).trim();
  } catch (err) { return `not read (${err.message.split('\n')[0]})`; }
};

// The OS picks the DevTools port (port 0) and Chrome writes it into its profile's DevToolsActivePort (lead 10-22): with a
// random port of 9300-9799 two runs on one box could meet - a port held by anything else left «did not answer», one held
// by another run's Chrome handed this run THAT Chrome's page. The page asked for carries this run's own mark.
async function openChrome() {
  if (!existsSync(CHROME)) throw new Error(`no Chrome at ${CHROME} - the screens cannot be opened`);
  const profile = mkdtempSync(path.join(tmpdir(), 'screens-'));
  folders.push(profile);
  const start = `data:text/html,screens-${process.pid}-${path.basename(profile)}`;
  const proc = spawn(CHROME, ['--headless=new', '--hide-scrollbars', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    '--window-size=1920,950', start], { stdio: 'ignore' });
  const written = path.join(profile, 'DevToolsActivePort');
  let port = null;
  let target;
  for (let i = 0; i < 75 && !target; i += 1) {
    await sleep(200);
    if (!port && existsSync(written)) port = Number(readFileSync(written, 'utf8').split(/\r?\n/)[0]) || null;
    if (!port) continue;
    try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === 'page'); } catch { /* not up yet */ }
  }
  if (!target) {
    proc.kill();
    throw new Error(`Chrome did not answer on its DevTools port - ${port ? `port ${port}, held by ${holderOf(port)}` : 'no port written in 15 s'}`);
  }
  if (target.url !== start) { proc.kill(); throw new Error(`the DevTools page on port ${port} is not this run's: ${target.url.slice(0, 80)}`); }
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
    if (PIVOT.on && request.method === 'PUT' && u.pathname === '/tables/dt_log/data/updates') {
      // Apply's save in pivot view (lead 10-23 ㄱ): answered with how many of its updates name a long row - a group id is none.
      const sent = JSON.parse(request.postData || '{}').updates || [];
      reply(200, 'application/json', JSON.stringify({ change_count: sent.filter((x) => /^pv-/.test(String(x.row_id || ''))).length }));
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
      // A sentence held to three lines or more with the whole of it in its title is cut at its bottom on purpose (lead
      // 10-21, 903053c14: a reason or a why, the rest in the tooltip) - never at its side.
      const clamped = parseInt(s.webkitLineClamp, 10) >= 3 && (el.getAttribute('title') || '').trim() === el.textContent.trim();
      if (dx > 1 || (dy > 1 && !clamped)) {
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
    // A base chip (base.css .chip) stands in a line as a control does - one of the two heights (lead f3639d4a2).
    const isControl = (e) => e.matches('button, [role="button"], input, select, textarea, .chip') || (e.matches('a[href]') && css(e).display !== 'inline');
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
    const mid = (x) => (x.top + x.bottom) / 2;
    // The line a control stands on: its bar (its widest ancestor still one line high), and the bar's other controls - and
    // words, by their letters - whose middle is within the control's height. One grouping for size and heights.
    const lineOf = (b, r) => {
      let bar = b.parentElement;
      while (bar && bar.parentElement && bar.parentElement !== document.body && bar.parentElement.getBoundingClientRect().height < r.height * 3) bar = bar.parentElement;
      if (!bar) return null;
      const items = [];
      for (const e of bar.querySelectorAll('*')) {
        if (e === b || b.contains(e) || e.contains(b) || !shown(e)) continue;
        if (isControl(e)) {
          if (!e.parentElement.closest('button, [role="button"]')) items.push({ el: e, box: e.getBoundingClientRect(), font: parseFloat(css(e).fontSize), control: true });
          continue;
        }
        if (e.closest('button, [role="button"]')) continue;
        const t = textBox(e);
        if (t) items.push({ box: t, font: parseFloat(css(e).fontSize) });
      }
      return { bar, near: items.filter((x) => mid(x.box) >= r.top && mid(x.box) <= r.bottom) };
    };
    // A control boxed by a height: not a tick box, a slider, a text area, nor a control inside a control, nor a vertical pill.
    // Only a control that draws its box (a line or a fill) shows a height; a word-like link button shows none. AG-Grid's
    // parts are its theme's (the base layer stops at them, base.css).
    const clear = (c) => !c || c === 'transparent' || /rgba\([^)]*,\s*0\)$/.test(c);
    const drawsBox = (e) => {
      const s = css(e);
      return !clear(s.backgroundColor) || ['Top', 'Right', 'Bottom', 'Left'].some((k) => parseFloat(s[`border${k}Width`]) > 0
        && s[`border${k}Style`] !== 'none' && !clear(s[`border${k}Color`]));
    };
    const boxed = (e) => isControl(e) && !e.matches('textarea, input[type="checkbox"], input[type="radio"], input[type="range"], input[type="file"], input[type="color"], input[type="hidden"]')
      && !e.parentElement.closest('button, [role="button"]') && !e.closest('[class^="ag-"], [class*=" ag-"]')
      && !/^vertical/.test(css(e).writingMode) && drawsBox(e);
    // A control that holds a picture (a gallery tile, a board cell) is a card: its height is its picture's and its words
    // stand at its top or under it - neither the size of a word control nor its middle.
    const card = (e) => !!e.querySelector('img, canvas');
    for (const b of all.filter((e) => isButton(e) && e.textContent.trim() && !card(e))) {
      // a vertical pill (a left tray's axis) runs along its words - its height is its length, not its size
      if (/^vertical/.test(css(b).writingMode)) continue;
      const r = b.getBoundingClientRect();
      const at = lineOf(b, r);
      if (!at) continue;
      const near = at.near;
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
    // centre: a control's words in its middle (owner 10-20 «버튼 안에 글씨 정렬 안 맞고») - the middle of its own letters'
    // box within 1 px of its box's. A field's text is placed by the browser between its paddings: those two, within 2 px.
    const ownWords = (c) => {
      let top = Infinity, bottom = -Infinity;
      const walker = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if (!n.textContent.trim() || n.parentElement.closest('button, [role="button"], a[href], select') !== c || !shown(n.parentElement)) continue;
        const range = document.createRange();
        range.selectNodeContents(n);
        for (const q of range.getClientRects()) if (q.height) { top = Math.min(top, q.top); bottom = Math.max(bottom, q.bottom); }
      }
      return bottom > top ? { top, bottom } : null;
    };
    for (const c of all.filter((e) => boxed(e) && !card(e))) {
      const r = c.getBoundingClientRect();
      if (r.height < 4) continue;
      let off;
      if (c.matches('input, select')) {
        const s = css(c);
        off = ((parseFloat(s.paddingTop) + parseFloat(s.borderTopWidth)) - (parseFloat(s.paddingBottom) + parseFloat(s.borderBottomWidth))) / 2;
      } else {
        const t = ownWords(c);
        if (!t) continue;
        off = mid(t) - mid(r);
      }
      if (Math.abs(off) > 1) lines.push({ rule: 'centre', path: pathOf(c), what: `«${label(c)}» its words ${Math.abs(off).toFixed(1)} px ${off > 0 ? 'below' : 'above'} its middle` });
    }
    // heights: the controls of one line stand one height (owner 10-20, lead f3639d4a2 - two heights, --control-h and the
    // small one; never a chip of its own height beside a field). Said once per line.
    // The height a person sees: a segmented group's (a box of controls only, the control filling it) - its border is the
    // group's. Compared only within one layer: a list hung over a header is not of the header's line.
    const face = (e) => {
      const own = e.getBoundingClientRect().height;
      // up through the wrappers that draw nothing and are the control's own size, to the box that holds them
      let p = e.parentElement;
      while (p && p !== document.body && !drawsBox(p) && p.getBoundingClientRect().height - own <= 2.5) p = p.parentElement;
      if (!p || p === document.body || !drawsBox(p) || [...p.children].some((k) => shown(k) && !isControl(k) && !k.querySelector('button, [role="button"], select, input'))) return own;
      const ph = p.getBoundingClientRect().height;
      return ph - own <= 2.5 ? ph : own;
    };
    const layer = (e) => { for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) if (/fixed|absolute/.test(css(a).position)) return a; return null; };
    const told = new Set();
    for (const c of all.filter((e) => boxed(e) && !card(e))) {
      const r = c.getBoundingClientRect();
      if (r.height < 4) continue;
      const at = lineOf(c, r);
      if (!at || told.has(at.bar)) continue;
      const mine = face(c);
      const other = at.near.find((x) => x.control && boxed(x.el) && !card(x.el) && x.box.height >= 4 && layer(x.el) === layer(c) && Math.abs(face(x.el) - mine) > 1);
      if (!other) continue;
      told.add(at.bar);
      lines.push({ rule: 'heights', path: pathOf(c), what: `«${label(c)}» ${Math.round(mine)} px high beside «${label(other.el)}» ${Math.round(face(other.el))} px on one line` });
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
// A box of the gallery's bar by its word, set to a value.
const GALLERY_PICK = (word, value) => `(() => { const l = [...document.querySelectorAll('#gallery-host .gallery-pick')]
  .find((p) => (p.querySelector('.gallery-pick__word') || {}).textContent === ${JSON.stringify(word)}); const s = l && l.querySelector('select');
  if (!s) return false; s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`;
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
    // The page opened again with its declaration read refused: the header's label reads it once, at the start - first, and
    // the page opened again with it read, so the states after it (the Ledger column, the edits Replay chain shows) have it.
    ['declaration refused, page opened again', async (c, log) => {
      DECL_REFUSED.on = true;
      log.opening = true;
      await c.send('Page.navigate', { url: `${ORIGIN}/index.html` });
      await sleep(1500);
      await settle(c, log);
      await evaluate(c, `(${screensLib})(${TOL})`);
      await until(c, GRID_LOADED, 15000);
      await until(c, "Boolean(document.querySelector('#grid-source-label-host .grid-source-label.is-unknown'))");
      DECL_REFUSED.on = false;
    }],
    ['declaration read, page opened again', async (c, log) => {
      log.opening = true;
      await c.send('Page.navigate', { url: `${ORIGIN}/index.html` });
      await sleep(1500);
      await settle(c, log);
      await evaluate(c, `(${screensLib})(${TOL})`);
      await until(c, GRID_LOADED, 15000);
      await until(c, "Boolean(document.querySelector('#grid-source-label-host .grid-source-label')) && !document.querySelector('#grid-source-label-host .is-unknown, #grid-source-label-host .is-pending')");
    }],
    // The gallery's board (lead 3589216b9) on dt_log with its picture column: Rows by c_bn, Columns by core_lot (12 values).
    ['Gallery, rows by columns', async (c, log) => {
      GALLERY.on = true;
      // each size starts from no choice kept (+ Column below would add a box per size)
      await evaluate(c, "window.__galleryFrom = (document.getElementById('table-select') || {}).value; try { localStorage.removeItem('gallery:dt_log'); } catch (e) {} true");
      for (const name of ['ledger_events', 'dt_log']) {
        await evaluate(c, `(() => { const sel = document.getElementById('table-select'); if (!sel || sel.value === ${JSON.stringify(name)}) return false;
          sel.value = ${JSON.stringify(name)}; sel.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
        await sleep(900);
        await settle(c, log);
        await until(c, GRID_LOADED);
      }
      await until(c, "!(document.getElementById('gallery-toggle-btn') || {}).hidden");
      await evaluate(c, "document.getElementById('gallery-toggle-btn').click(); true");
      await sleep(400);
      await evaluate(c, GALLERY_PICK('Rows by', 'c_bn'));
      await evaluate(c, GALLERY_PICK('Columns by', 'core_lot'));
      await sleep(800);
    }],
    ['Gallery, nine a cell', (c) => evaluate(c, GALLERY_PICK('Show', '9')).then(() => sleep(800))],
    ['Gallery, a cell opened and a tile pressed', async (c) => {
      await evaluate(c, "(() => { const cell = document.querySelectorAll('#gallery-host .gallery-cell:not(.is-empty)')[1]; if (cell) cell.click(); return Boolean(cell); })()");
      await sleep(500);
      await evaluate(c, "(() => { const t = document.querySelector('#gallery-host .gallery-tile'); if (t) t.click(); return Boolean(t); })()");
      await sleep(600);
    }],
    ['Gallery, + Column', (c) => evaluate(c, "(() => { const b = document.querySelector('#gallery-host .gallery-add'); if (b) b.click(); return Boolean(b); })()").then(() => sleep(800))],
    ['Gallery, filtered to a cell', async (c, log) => {
      await evaluate(c, "(() => { const b = document.querySelector('#gallery-host .gallery-open__filter'); if (b) b.click(); return Boolean(b); })()");
      await sleep(900);
      await settle(c, log);
      await until(c, GRID_LOADED);
      await sleep(600);
    }],
    ['Gallery left, the first table again', async (c, log) => {
      await evaluate(c, `(() => { const sel = document.getElementById('table-select'); if (!sel || !window.__galleryFrom) return false;
        sel.value = window.__galleryFrom === 'dt_log' ? 'ledger_events' : window.__galleryFrom; sel.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
      await sleep(900);
      await settle(c, log);
      await until(c, GRID_LOADED);
      GALLERY.on = false;
      await evaluate(c, `(() => { const sel = document.getElementById('table-select'); if (!sel || sel.value === window.__galleryFrom) return true;
        sel.value = window.__galleryFrom; sel.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
      await sleep(900);
      await settle(c, log);
      await until(c, GRID_LOADED);
    }],
    // The grid pivoted (owner 10-22): dt_log with its pivot declared (PIVOT), «Pivot» pressed, then pressed again.
    ['Pivot on', async (c, log) => {
      PIVOT.on = true;
      await evaluate(c, "window.__pivotFrom = (document.getElementById('table-select') || {}).value; try { localStorage.removeItem('grid-pivot:dt_log'); } catch (e) {} true");
      for (const name of ['ledger_events', 'dt_log']) {
        await evaluate(c, `(() => { const sel = document.getElementById('table-select'); if (!sel || sel.value === ${JSON.stringify(name)}) return false;
          sel.value = ${JSON.stringify(name)}; sel.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
        await sleep(900);
        await settle(c, log);
        await until(c, GRID_LOADED);
      }
      await until(c, "!(document.getElementById('pivot-toggle-btn') || {}).hidden");
      await evaluate(c, "document.getElementById('pivot-toggle-btn').click(); true");
      await sleep(900);
      await settle(c, log);
      await until(c, GRID_LOADED);
      await until(c, "document.querySelectorAll('.ag-header-cell[col-id^=\"item:\"]').length > 0");
    }],
    // Apply in pivot view with Tx on - the default path (lead 10-23 ㄱ): an item cell edited and applied, its long row read
    // again first; then the same over a long row changed since the edit, and over one gone.
    ['Pivot, an edit applied', (c) => pivotEditApplied(c, 'same')],
    ['Pivot, an edit over a changed row', (c) => pivotEditApplied(c, 'moved')],
    ['Pivot, an edit of a gone row', (c) => pivotEditApplied(c, 'gone')],
    ['Pivot off', async (c, log) => {
      await evaluate(c, "document.getElementById('pivot-toggle-btn').click(); true");
      await sleep(900);
      await settle(c, log);
      await until(c, GRID_LOADED);
    }],
    ['Pivot left, the first table again', async (c, log) => {
      PIVOT.on = false;
      PIVOT_LONG.mode = 'same';
      for (const to of ['ledger_events', '__pivotFrom']) {
        await evaluate(c, `(() => { const sel = document.getElementById('table-select'); const to = ${JSON.stringify(to)} === '__pivotFrom' ? window.__pivotFrom : ${JSON.stringify(to)};
          if (!sel || !to || sel.value === to) return true; sel.value = to; sel.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
        await sleep(900);
        await settle(c, log);
        await until(c, GRID_LOADED);
      }
    }],
    // The Queue tab open for one beat of its poll and a little more.
    ['Queue tab, a beat later', (c) => evaluate(c, "(() => { const tab = document.getElementById('tab-queue'); if (tab) tab.click(); return true; })()")
      .then(() => sleep(QUEUE_POLL_MS + 1500))],
    ['a row picked under the Queue tab', (c) => evaluate(c, `(() => {
      const cell = document.querySelector('.ag-center-cols-container .ag-row[row-index="1"] .ag-cell');
      if (cell) for (const t of ['mousedown', 'mouseup', 'click']) cell.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window }));
      return true; })()`).then(() => sleep(600))],
    // Another table from the dropdown, the Queue tab still open (the switch that left the Queue pane under Global).
    ['table switched from the Queue tab', async (c, log) => {
      await evaluate(c, `(() => { const sel = document.getElementById('table-select'); if (!sel) return false;
        window.__firstTable = sel.value;
        sel.value = sel.value === 'dt_log' ? 'ledger_events' : 'dt_log';
        sel.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
      await sleep(900);
      await settle(c, log);
      await until(c, GRID_LOADED);
    }],
    // Back to the table the page opened on: the filters, the row pick and the header panels after it are that table's.
    ['the first table again', async (c, log) => {
      await evaluate(c, `(() => { const sel = document.getElementById('table-select'); if (!sel || !window.__firstTable) return false;
        sel.value = window.__firstTable; sel.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
      await sleep(900);
      await settle(c, log);
      await until(c, GRID_LOADED);
    }],
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
    // The first data column hidden from the column selector (owner 10-22): the checkboxes rode on it.
    ['first column hidden', async (c) => {
      await evaluate(c, "(() => { const b = document.getElementById('column-selector-btn'); if (b) b.click(); return Boolean(b); })()");
      await sleep(400);
      await evaluate(c, `(() => { const box = document.querySelector('#column-list-container .col-selector-checkbox'); if (!box) return false;
        window.__hiddenFirst = box.id.replace(/^col-toggle-/, ''); box.checked = false; box.dispatchEvent(new Event('change', { bubbles: true }));
        document.body.dispatchEvent(new MouseEvent('click', { bubbles: true })); return true; })()`);
      await sleep(600);
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
    // The chain form opened on a rule (lead after a2b7f6e14 · owner 10-21): a join whose take holds a record - its rows,
    // the fn picker, then + and record on a third item - and a flat rule; both with target_columns on the first screen.
    // The rules are the captured take_record_probe and dt_log_to_dt_map.
    ['Chain, a flat rule', async (c) => {
      await evaluate(c, "location.hash = '#chain'; true");
      await until(c, "!!document.querySelector('select.chain-rule-picker')");
      await choose(c, 'select.chain-rule-picker', [0, "x.value === 'dt_log_to_dt_map'"]);
      await until(c, "!!document.querySelector('[data-path=\"target_table\"]')");
      await evaluate(c, `(() => { const at = document.querySelector('[data-path="target_columns"]');
        if (at) at.scrollIntoView({ block: 'center' }); return true; })()`);
    }],
    ['Chain, a join whose take holds a record', async (c) => {
      await evaluate(c, "location.hash = '#chain'; true");
      await until(c, "!!document.querySelector('select.chain-rule-picker')");
      await choose(c, 'select.chain-rule-picker', [0, "x.value === 'take_record_probe'"]);
      await until(c, "!!document.querySelector('[data-path=\"derive.join.take\"]')");
      // a folded toggle is oe-field-folded on a field and oe-node-folded on a row
      const unfold = (at) => evaluate(c, `(() => {
        const fold = document.querySelector('button[data-action="toggle-field"][data-value="${at}"]');
        if (fold && /folded/.test(fold.className)) fold.click(); return Boolean(fold); })()`);
      await unfold('derive.join.take');
      await until(c, "!!document.querySelector('[data-path=\"derive.join.take[1]\"]')");
      await unfold('derive.join.take[1]');
      await until(c, "!!document.querySelector('[data-value=\"derive.join.take[1].fn\"]')");
      await evaluate(c, `(() => { const at = document.querySelector('[data-path="derive.join.take"]');
        if (at) at.scrollIntoView({ block: 'center' }); return true; })()`);
    }],
    ['Chain, + then record on the take', async (c) => {
      await evaluate(c, `(() => { const add = document.querySelector('button[data-action="form-append"][data-value="derive.join.take"]');
        if (add) add.click(); return Boolean(add); })()`);
      await until(c, "!!document.querySelector('select[data-action=\"edit-shape-branch\"][data-value=\"derive.join.take[2]\"]')");
      await choose(c, 'select[data-action="edit-shape-branch"][data-value="derive.join.take[2]"]', [0, "x.value === 'record'"]);
      await until(c, "!!document.querySelector('[data-value=\"derive.join.take[2].fn\"]')");
      await evaluate(c, `(() => { const at = document.querySelector('[data-path="derive.join.take"]');
        if (at) at.scrollIntoView({ block: 'center' }); return true; })()`);
    }],
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
        const built = await evaluate(chrome, 'document.documentElement.dataset.screensBuild || null');
        if (built !== STAMP) add('loaded', [{ rule: 'built now', path: entry, what: `the page is not this run's build (${built || 'no mark'})` }]);
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
const source = await buildBundle('screens-source-');
const { entries, found } = await runScreens(source, 'source');
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
  // «Pivot» on every table, the footer counting rows in pivot view (owner 10-22).
  { name: 'Pivot drawn on every table', entry: 'index.html', rule: 'pivot only where declared', at: 'pivot',
    file: 'src/api.js', edits: [['    button.hidden = !state.currentPivot;', '    button.hidden = false;']] },
  { name: 'Pivot refused while Tx is merely on (it is on by default)', entry: 'index.html', rule: 'pivot drawn', at: 'pivot',
    file: 'src/api.js', edits: [['  if (Object.keys(state.pendingTxEdits).length) { elements.performanceLog', '  if (state.txModeActive) { elements.performanceLog']] },
  { name: 'Apply reads a pivot group id again', entry: 'index.html', rule: 'pivot apply writes', at: 'pivot',
    file: 'src/grid_pivot.js', edits: [['  if (!view) return [...new Set(edits.map((edit) => edit.rowId))];\n', '  return [...new Set(edits.map((edit) => edit.rowId))];\n']] },
  { name: 'rows are not refused in pivot view', entry: 'index.html', rule: 'pivot writes', at: 'pivot',
    file: 'src/write_guard.js', edits: [["const ROW_CONTROLS = ['addRowBtn', 'deleteRowBtn', 'smartPasteBtn'];", 'const ROW_CONTROLS = [];']] },
  { name: 'the footer counts rows in pivot view', entry: 'index.html', rule: 'pivot drawn', at: 'pivot',
    file: 'src/api.js', edits: [['elements.totalRowsCount.dataset.unit = rowUnit();', "elements.totalRowsCount.dataset.unit = 'row';"]] },
  // The checkboxes back on the schema's first column (owner 10-22): hidden from the column selector, they go with it.
  { name: 'the checkboxes back on the first data column', entry: 'index.html', rule: 'select all at the left', at: 'ag-header',
    file: 'src/grid.js', edits: [["    rowSelection: { mode: 'multiRow', checkboxes: true, headerCheckbox: true, enableClickSelection: true },\n", "    rowSelection: 'multiple',\n"], ['      resizable: true,\n      // C-85.', '      resizable: true,\n      checkboxSelection: index === 0,\n      headerCheckboxSelection: index === 0,\n      // C-85.']] },
  // A click no longer selects its row (the selection options keep it only when asked).
  { name: 'a click no longer selects its row', entry: 'index.html', rule: 'a click selects its row', at: 'ag-row',
    file: 'src/grid.js', edits: [['enableClickSelection: true', 'enableClickSelection: false']] },
  // The refused declaration read drawn as its status alone again (lead 06d7ca89e).
  { name: 'a refused declaration said as its status alone', entry: 'index.html', rule: 'server sentence said', at: 'grid-source-label',
    file: 'src/main.js', edits: [["    if (!res.ok) return { ok: false, message: await refusalText(res, 'server refused') };\n",
      "    if (!res.ok) return { ok: false, message: `server refused (${res.status})` };\n"]] },
  // A panel left inside the header is placed in the header's zoomed px (10-08).
  // A table switch lights Global and leaves the Queue pane shown (owner 10-21) - the tab marked, its pane not asked.
  { name: 'a table switch lights Global over the Queue pane', entry: 'index.html', rule: 'lit tab shows its pane', at: 'history-sidebar',
    says: /pane shown: queue-view/, file: 'src/api.js', edits: [["  pickHistoryTab('global');\n",
      "  state.activeHistoryTab = 'global';\n  for (const b of elements.tabGlobalBtn.parentNode.children) b.classList.toggle('active', b === elements.tabGlobalBtn);\n"]] },
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
  // The gallery's board (lead 3589216b9): it rolls inside its own box; a shut gallery is not laid out; the chip strip
  // folded again when the header gives it another width while the gallery holds the grid's place.
  { name: 'the board sets the page width', entry: 'index.html', rule: 'overflow', at: 'page',
    file: 'src/gallery.css', edits: [['max-height: 60%; overflow: auto; contain: inline-size;', 'max-height: 60%; overflow: auto;']] },
  { name: 'a shut gallery laid out under the grid', entry: 'index.html', rule: 'clip', at: '', says: /px past its top or bottom: «AssyManager/,
    file: 'src/gallery.css', edits: [['.gallery-host[hidden] { display: none; }', '']] },
  { name: 'a thumbnail held at its own size', entry: 'index.html', rule: 'thumbs fill', at: 'gallery-cell__thumb',
    file: 'src/gallery.css', edits: [['.sf-thumb__img { display: block; width: 100%; height: 100%; object-fit: contain; }',
      '.sf-thumb__img { display: block; max-width: 100%; max-height: 100%; object-fit: contain; }']] },
  { name: 'the chip strip not folded again when the header gives it another width', entry: 'index.html', rule: 'clip', at: 'filter-chips',
    file: 'src/grid.js', edits: [['    chipBarWatch.observe(bar);', '']] },
  { name: 'the why beside its tag, cut at the cell', entry: 'index.html', rule: 'clip', at: 'queue-line-state-why',
    file: 'src/base.css', edits: [
      [':where(.queue-line-state) { display: flex; flex-direction: column; align-items: flex-start;', ':where(.queue-line-state) { display: flex; align-items: center;'],
      [':where(.reason-lines) { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; line-clamp: 3;',
        ':where(.reason-lines) { display: block;'],
      ['  overflow: hidden; white-space: normal; overflow-wrap: anywhere; min-width: 0; }',
        '  overflow: hidden; white-space: nowrap; text-overflow: ellipsis; min-width: 0; }']] },
  { name: 'the admin queue why held to one line again', entry: 'admin.html', rule: 'reason whole', at: 'fail-summary__reason',
    file: 'admin.html', edits: [['    .chain-queue-table .chain-queue-failure { overflow-wrap: break-word; }',
      '    .chain-queue-table .chain-queue-failure { overflow-wrap: break-word; }\n    .chain-queue-table .queue-line-state-why { -webkit-line-clamp: 1; line-clamp: 1; }']] },
  { name: 'a recent failure breaks its words anywhere', entry: 'admin.html', rule: 'words', at: 'td > div.refusal.reason-lines',
    file: 'admin.html', edits: [['    .chain-queue-table .chain-queue-failure { overflow-wrap: break-word; }', '    .chain-queue-table .chain-queue-failure { }']] },
  { name: 'the failed line says the seconds of its sentence alone', entry: 'admin.html', rule: 'reason whole', at: 'fail-summary__reason',
    file: 'src/failure_summary.js', edits: [["l.last_failure.trim() : '';", "(l.last_failure.match(/\\d+ s/) || [''])[0] : '';"]] },
  { name: 'a recent failure says the seconds of its sentence alone', entry: 'admin.html', rule: 'reason whole', at: 'fail-summary__reason',
    file: 'src/chain_queue_panel.js', edits: [["const said = this._line('refusal reason-lines chain-queue-failure', f.failure);",
      "const said = this._line('refusal reason-lines chain-queue-failure', (f.failure.match(/\\d+ s/) || [''])[0]);"]] },
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
    at: 'mapper-list-body', file: 'admin.html', edits: [['    #mapper-list-body .admin-btn,\n    #autoupdate-linked-body .admin-btn,\n    .file-folder-copy,\n    #retry-all-outbox-btn {\n',
      '    .file-folder-copy,\n    #retry-all-outbox-btn {\n']] },
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
    file: 'src/testbed/picker.js', edits: [["      fitUnder(this.host, pill, { align: 'left', gap: 4 });",
      "      { const s = pill.getBoundingClientRect(); this.host.style.left = `${Math.max(8, Math.min(s.left, document.documentElement.clientWidth - 760))}px`; this.host.style.top = `${s.bottom + 4}px`; }"]] },
  // The base layer's controls (lead f3639d4a2, owner 10-20 «버튼 안에 글씨 정렬 안 맞고»): built back, on the sample page.
  { name: 'a padding-top on the base button, its words off its middle', entry: 'sample.html', rule: 'centre', at: 'sample-actions',
    file: 'src/base.css', edits: [['  height: var(--control-h);\n  padding: 0 var(--space-3);\n  font-family: var(--font-head);',
      '  height: var(--control-h);\n  padding: 6px var(--space-3) 0;\n  font-family: var(--font-head);']] },
  { name: 'the name column back at its base width, a long name cut', entry: 'sample.html', rule: 'names whole, columns in line',
    at: 'sample-decl-form', says: /a_forty_letter_name_of_a_declared_column/, file: 'src/ontology_explorer.css',
    edits: [['  grid-template-columns: max-content minmax(0, 1fr);', '  grid-template-columns: calc(var(--space-6) * 5) minmax(0, 1fr);']] },
  { name: 'a row padded again, its height off the row step', entry: 'sample.html', rule: 'rows one height, boxes at one x',
    at: 'sample-decl-form', says: /not a whole number/, file: 'src/ontology_explorer.css',
    edits: [['  margin: 0; padding: 0;\n', '  margin: 0; padding: 3px 0;\n']] },
  { name: 'the row\'s word drawn over its box again', entry: 'sample.html', rule: 'rows one height, boxes at one x',
    at: 'sample-decl-form', says: /over its box/, file: 'src/ontology_explorer.css',
    edits: [['.oe-node-value > .oe-tier { flex: none; }', '.oe-node-value > .oe-tier { flex: none; margin-left: calc(var(--space-6) * -2); }']] },
  { name: 'a table under its row padded off the row step', entry: 'sample.html', rule: 'rows one height, boxes at one x',
    at: 'sample-decl-form', says: /table .* not a whole number/, file: 'src/ontology_explorer.css',
    edits: [['  padding: 0 0 0 calc(var(--oe-indent) * max(var(--oe-depth, 0) - 1, 0) + var(--space-5));',
      '  padding: var(--space-1) 0 0 calc(var(--oe-indent) * max(var(--oe-depth, 0) - 1, 0) + var(--space-5));']] },
  { name: 'a value box stretched to its cell again', entry: 'sample.html', rule: 'rows one height, boxes at one x',
    at: 'sample-decl-form', says: /px wide, not/, file: 'src/ontology_explorer.css',
    edits: [['width: 100%; max-width: var(--oe-box-w);', 'width: 100%; max-width: none;']] },
  { name: 'chip lines closer than the row step', entry: 'sample.html', rule: 'rows one height, boxes at one x',
    at: 'sample-decl-form', says: /not a whole number|steps high/, file: 'src/ontology_explorer.css',
    edits: [['  padding-block: var(--space-1);', '']] },
  { name: 'the row sets its boxes at its top', entry: 'sample.html', rule: 'rows one height, boxes at one x',
    at: 'sample-decl-form', says: /off its row middle/, file: 'src/ontology_explorer.css',
    edits: [['  align-items: center; min-width: 0;', '  align-items: start; min-width: 0;']] },
  { name: 'a summary text a step left of the values', entry: 'sample.html', rule: 'rows one height, boxes at one x',
    at: 'sample-decl-form', says: /box text starts at/, file: 'src/ontology_explorer.css',
    edits: [['  padding: 0 var(--space-3); border: 1px solid transparent;', '  padding: 0; border: 1px solid transparent;']] },
  { name: 'a chip of its own height beside the small field', entry: 'sample.html', rule: 'heights', at: 'sample-actions',
    file: 'src/base.css', edits: [['  box-sizing: border-box;\n  height: var(--control-h-small);\n  padding: 0 var(--space-3);',
      '  box-sizing: border-box;\n  height: 22px;\n  padding: 0 var(--space-3);']] },
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
// The one build door: the source as it is now, into a folder of this run's, every html stamped with STAMP - the base
// pass with no other plugin, a mutant with its edit (lead 10-22 ㄴ).
async function buildBundle(prefix, plugins = []) {
  const { build } = await import('vite');
  const out = mkdtempSync(path.join(tmpdir(), prefix));
  await build({ root: CLIENT, configFile: path.join(CLIENT, 'vite.config.js'), logLevel: 'silent', build: { outDir: out, emptyOutDir: true },
    plugins: [...plugins, { name: 'screens-stamp', transformIndexHtml: (html) => html.replace(/<html\b/, `<html data-screens-build="${STAMP}"`) }] });
  return out;
}
async function buildMutant(m) {
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
  const out = await buildBundle('screens-mutant-', [{ name: 'screens-mutant', enforce: 'pre', transform: (code, id) => (mine(id) ? swap() : null),
    transformIndexHtml: { order: 'pre', handler: (html, ctx) => (mine(ctx.filename) ? swap() : html) } }]);
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
removeFolder(source, 'build');
process.exit(failed ? 1 : 0);
