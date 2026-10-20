// THE FILE INGESTION PAGE (owner 10-20 «ㅇㅇ 일케 해», lead; mockup FWp74vd6UqX1i7qXpyQg8K): its words and its parts.
//   M1 a read's Result: «400 rows · 12 new · 388 unchanged» (zeros after the rows left out); a failure - its reason; none counted - ABSENT
//   M2 Took «0.4 s»; none timed - ABSENT
//   M3 the query: blanks left out, status ALL by default, `to` a day included (until = the day after), the group word
//   M4 grouped by folder - under the folder ABOVE a file's own, the server's per-folder counts summed into it, in the rows' order;
//      by reason - a blank reason «(No reason)»; no group - one group without a head
//   M5 the table list: ok · failed from /tables, running from /active per table
//   M6 a status's word and tone: PENDING_RETRY «Pending retry» warn · FAILED danger · SUCCESS ok
//   P1 the files part: a head per group with its count, a line per file with its folder (whole in the tooltip), the picked
//      one marked, a press hands the log; Show more only while more match
//   P2 the detail: a failure - «Why it failed» with the reason and the frame, «Retry this file»; a success - «Read again», no
//      reason box; Copy folder copies the folder; only the counts the server wrote
//   P3 the search line: All counts every status, the picked chip marked, a field's change hands its one key
//   P4 the table list: Find table narrows, the picked one marked, a press hands its name
//   P5 two of each part in one page do not touch each other's div
// Imports only (the probe copies a module whole); each defect must go red at its line.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';
import { makeDoc, walk, byClass } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src', 'file_ingestion');
const FILES = { model: path.join(SRC, 'model.js'), parts: path.join(SRC, 'parts.js'), narrowing: path.join(HERE, '..', 'src', 'narrowing.js') };
const { ABSENT } = await import('../src/absent.js');

let ran = 0;
let failed = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1;
  NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failed.push(name);
  console.log(`  FAIL ${name}${detail === undefined ? '' : ` -- ${detail}`}`);
};

async function load(m) {
  const model = (await loadWithProbe(FILES.model, m && m.file === 'model' ? { mutate: m.mutate } : {})).module;
  // the parts import the model by path; a model mutant reaches them through the probe's copy only when the parts are its
  const parts = (await loadWithProbe(FILES.parts, m && m.file === 'parts' ? { mutate: m.mutate } : {})).module;
  const narrowing = (await loadWithProbe(FILES.narrowing, m && m.file === 'narrowing' ? { mutate: m.mutate } : {})).module;
  return { model, parts, narrowing };
}

const BS = '\\';
const P = (...segs) => segs.join(BS);
const log = (id, over = {}) => ({ id, filename: 'bmap.txt', filepath: P('', '', 'fab', 'LOT', 'STEP_01', `W${id}`, 'bmap.txt'), folder: P('', '', 'fab', 'LOT', 'STEP_01', `W${id}`),
  table_name: 'inspection_run', status: 'SUCCESS', rows_read: 400, rows_new: 12, rows_changed: 0, rows_unchanged: 388, rows_refused: 0,
  reader: 'standard', source: 'raws', reason: null, failed_at: null, took_seconds: 0.4, created_at: '2026-10-20T10:00:00+00:00', updated_at: '2026-10-20T10:00:00+00:00', ...over });
const texts = (root, cls) => byClass(root, cls).map((n) => n.textContent);

async function suite({ model: M, parts: Q, narrowing: N }) {
  ran = 0;
  failed = [];
  NAMES.length = 0;

  ok('M1a a read said by its counts, zeros after the rows left out', M.resultText(log(1)) === '400 rows · 12 new · 388 unchanged', M.resultText(log(1)));
  ok('M1b a failure said by its reason; none counted - ABSENT',
    M.resultText(log(2, { status: 'FAILED', reason: 'line 3: 3 values for 2 x values' })) === 'line 3: 3 values for 2 x values'
      && M.resultText(log(3, { status: 'FAILED', reason: null, error_message: '\nTraceback first\nmore' })) === 'Traceback first'
      && M.resultText(log(4, { rows_read: null })) === ABSENT);
  ok('M2 Took in seconds; none timed - ABSENT', M.tookText(0.4) === '0.4 s' && M.tookText(null) === ABSENT && M.tookText(12.6) === '13 s', `${M.tookText(0.4)} ${M.tookText(12.6)}`);

  const q = M.queryOf({ table: 't', status: '', name: ' bmap ', folder: '', from: '2026-10-19', to: '2026-10-20', group: 'folder' }, { page: 2 });
  ok('M3 the query: blanks out, ALL by default, the To day included, the group word', q.get('table') === 't' && q.get('status') === 'ALL' && q.get('name') === 'bmap'
    && !q.has('folder') && q.get('since') === '2026-10-19' && q.get('until') === '2026-10-21' && q.get('group') === 'folder' && q.get('page') === '2', q.toString());

  const rows = [log(11), log(12, { status: 'FAILED', reason: 'bad' }), log(21, { folder: P('', '', 'fab', 'LOT', 'STEP_02', 'W21') })];
  const server = [{ key: P('', '', 'fab', 'LOT', 'STEP_01', 'W11'), count: 1, failed: 0 }, { key: P('', '', 'fab', 'LOT', 'STEP_01', 'W12'), count: 1, failed: 1 },
    { key: P('', '', 'fab', 'LOT', 'STEP_01', 'W13'), count: 3, failed: 1 }, { key: P('', '', 'fab', 'LOT', 'STEP_02', 'W21'), count: 2, failed: 0 }];
  const byFolder = M.groupFiles(rows, 'folder', server);
  ok('M4a by folder: under the folder above, the counts summed, in the rows\' order',
    byFolder.length === 2 && byFolder[0].key === P('', '', 'fab', 'LOT', 'STEP_01', '') && byFolder[0].files.length === 2 && byFolder[0].count === 5 && byFolder[0].failed === 2
      && byFolder[1].count === 2, JSON.stringify(byFolder.map((g) => [g.key, g.files.length, g.count, g.failed])));
  const byReason = M.groupFiles(rows, 'reason', [{ key: null, count: 2, failed: 0 }, { key: 'bad', count: 1, failed: 1 }]);
  const none = M.groupFiles(rows, '', server);
  ok('M4b by reason - a blank reason «(No reason)»; no group - one group, no head',
    byReason[0].label === M.WORDS.noReason && byReason[0].count === 2 && byReason[1].label === 'bad' && none.length === 1 && none[0].head === false && none[0].files.length === 3,
    JSON.stringify(byReason.map((g) => [g.label, g.count])));

  const lines = M.tableLines([{ table_name: 'a', total: 1203, by_status: { SUCCESS: 1190, FAILED: 11 }, last_at: null }, { table_name: 'b', total: 2, by_status: { SUCCESS: 2 } }],
    [{ table_name: 'a' }, { table_name: 'a' }, { table_name: 'c' }]);
  ok('M5 the table list: ok · failed by status, running from /active per table', lines[0].ok === '1,190' && lines[0].failed === '11' && lines[0].running === '2' && lines[1].running === '0'
    && lines[0].total === '1,203', JSON.stringify(lines));
  ok('M6 a status\'s word and tone', M.statusWord('PENDING_RETRY') === 'Pending retry' && M.statusTone('PENDING_RETRY') === 'warn' && M.statusTone('FAILED') === 'danger'
    && M.statusTone('SUCCESS') === 'ok', `${M.statusWord('PENDING_RETRY')} ${M.statusTone('PENDING_RETRY')}`);

  // P1 - the files part
  const doc = makeDoc('light');
  const host = doc.createElement('div');
  doc.body.append(host);
  const picks = [];
  let mores = 0;
  const files = new Q.FilesPart(host, { doc, onPick: (l) => picks.push(l.id), onMore: () => { mores += 1; } });
  files.render({ groups: byFolder, shown: 'x', picked: 12, more: true });
  const fileRows = walk(host).filter((n) => n.tagName === 'TR' && String(n.className).includes('fi-file'));
  const folderSpan = walk(fileRows[0]).find((n) => n.tagName === 'SPAN' && n.title);
  fileRows[1].dispatch('click');
  const more = byClass(host, 'fi-more')[0];
  if (more) more.dispatch('click');
  ok('P1a a head per group with its count, a line per file with its folder, the picked marked, a press hands the log',
    texts(host, 'fi-group__line').length === 2 && texts(host, 'fi-group__line')[0].includes(M.WORDS.groupSummary(5, 2)) && fileRows.length === 3
      && folderSpan && folderSpan.title === P('', '', 'fab', 'LOT', 'STEP_01', 'W11', '') && String(fileRows[1].className).includes('is-picked')
      && JSON.stringify(picks) === '[12]' && mores === 1, `${texts(host, 'fi-group__line')} rows ${fileRows.length} picks ${picks}`);
  files.render({ groups: byFolder, shown: 'x', picked: null, more: false });
  ok('P1b no Show more when nothing more matches', byClass(host, 'fi-more').length === 0);

  // P2 - the detail
  const dHost = doc.createElement('div');
  doc.body.append(dHost);
  const copies = [];
  const acts = [];
  const detail = new Q.DetailPart(dHost, { doc, onCopy: (t) => copies.push(t), onAct: (l) => acts.push(l.id) });
  detail.render(log(12, { status: 'FAILED', reason: 'line 3: bad', failed_at: 'p.py:7 in parse', rows_read: 0, rows_new: null, rows_changed: null, rows_unchanged: null, rows_refused: null }));
  const why = byClass(dHost, 'fi-why')[0];
  const main = byClass(dHost, 'fi-btn--primary')[0];
  const copyFolder = byClass(dHost, 'fi-btn').find((b) => b.textContent === M.WORDS.copyFolder);
  if (copyFolder) copyFolder.dispatch('click');
  main.dispatch('click');
  const countLabels = walk(byClass(dHost, 'fi-counts')[0] || dHost).filter((n) => n.tagName === 'TD' && String(n.className) === 'fi-dim').map((n) => n.textContent);
  ok('P2a a failure: its reason and frame, «Retry this file», Copy folder copies the folder, only the counts written',
    why && why.textContent.includes('line 3: bad') && why.textContent.includes('p.py:7 in parse') && main.textContent === M.WORDS.retryFile && JSON.stringify(acts) === '[12]'
      && copies[0] === P('', '', 'fab', 'LOT', 'STEP_01', 'W12', '') && JSON.stringify(countLabels) === '["Rows read"]', `${why && why.textContent} ${main.textContent} ${copies} ${countLabels}`);
  detail.render(log(13));
  ok('P2b a success: «Read again», no reason box; no tx - no «Show its rows»', byClass(dHost, 'fi-why').length === 0 && byClass(dHost, 'fi-btn--primary')[0].textContent === M.WORDS.readAgain
    && byClass(dHost, 'fi-btn--link').length === 0);
  detail.render(log(14, { transaction_id: 'tx-9' }));
  const rowsLink = byClass(dHost, 'fi-btn--link')[0];
  const back = rowsLink ? N.gridAddress(rowsLink.getAttribute('href').slice(1), ['inspection_run']) : null;
  ok('P2c a read with its tx: «Show its rows in the grid» opens the grid on that table and tx', back && back.table === 'inspection_run' && back.tx === 'tx-9'
    && M.rowsAddress(log(14, { transaction_id: 'tx-9' })) === rowsLink.getAttribute('href') && M.rowsAddress(log(15)) === null, rowsLink && rowsLink.getAttribute('href'));
  const g1 = N.gridAddress('?table=b&tx=t1', ['a', 'b']);
  const g2 = N.gridAddress('?table=zz&tx=t1', ['a', 'b']);
  const g3 = N.gridAddress('?tx=t1', ['a', 'b']);
  ok('G1 the grid\'s address: a listed table and its tx; a table not listed or none - neither', g1.table === 'b' && g1.tx === 't1' && g2.table === null && g2.tx === null && g3.tx === null,
    JSON.stringify([g1, g2, g3]));

  // P3 - the search line
  const sHost = doc.createElement('div');
  doc.body.append(sHost);
  const patches = [];
  const search = new Q.SearchPart(sHost, { doc, onChange: (p) => patches.push(p) });
  search.render({ table: 't', status: 'FAILED', name: '', folder: '', from: '', to: '', group: 'folder' }, [{ key: 'SUCCESS', count: 69 }, { key: 'FAILED', count: 6 }]);
  const chips = byClass(sHost, 'fi-chip');
  const name = walk(sHost).find((n) => n.tagName === 'INPUT' && n.dataset.key === 'name');
  name.value = 'bmap';
  name.dispatch('change');
  chips[0].dispatch('click');
  ok('P3 All counts every status, the picked chip marked, a change hands its one key',
    chips.length === 3 && chips[0].textContent === 'All75' && String(chips[2].className).includes('is-picked') && !String(chips[0].className).includes('is-picked')
      && JSON.stringify(patches) === '[{"name":"bmap"},{"status":"ALL"}]', `${chips.map((c) => c.textContent)} ${JSON.stringify(patches)}`);

  // P4 - the table list
  const tHost = doc.createElement('div');
  doc.body.append(tHost);
  const picked = [];
  const list = new Q.TableListPart(tHost, { doc, onPick: (n) => picked.push(n) });
  list.render(lines, 'b');
  const find = walk(tHost).find((n) => n.tagName === 'INPUT');
  const before = byClass(tHost, 'fi-table').length;
  const markedB = String(byClass(tHost, 'fi-table')[1].className).includes('is-picked');
  find.value = 'a';
  find.dispatch('input');
  const after = byClass(tHost, 'fi-table');
  after[0].dispatch('click');
  ok('P4 Find table narrows, the picked marked, a press hands its name', before === 2 && after.length === 1 && after[0].dataset.table === 'a' && JSON.stringify(picked) === '["a"]' && markedB, `${before} -> ${after.length}`);

  // P5 - two of each, one page
  const one = doc.createElement('div');
  const two = doc.createElement('div');
  doc.body.append(one, two);
  new Q.FilesPart(one, { doc, onPick() {}, onMore() {} }).render({ groups: byFolder, shown: 'one', picked: null, more: false });
  new Q.FilesPart(two, { doc, onPick() {}, onMore() {} }).render({ groups: none, shown: 'two', picked: null, more: false });
  ok('P5 two parts in one page keep to their own div', byClass(one, 'fi-group').length === 2 && byClass(two, 'fi-group').length === 0 && texts(one, 'fi-meta')[0] === 'one');
  return { ran, failed: failed.slice() };
}

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { name: 'zeros said too', catches: ['M1a'], file: 'model', mutate: swap('    if (numberOr(v)) parts.push', '    if (numberOr(v) !== null) parts.push') },
  { name: 'a failure said by its counts', catches: ['M1b'], file: 'model', mutate: swap("  if (String(log.status) === 'FAILED') return reasonOf(log) || ABSENT;", '') },
  { name: 'Took without its unit', catches: ['M2'], file: 'model', mutate: swap("Math.round(s).toLocaleString('en-US')} s`", "Math.round(s).toLocaleString('en-US')}`") },
  { name: 'the To day left out (until = To)', catches: ['M3'], file: 'model', mutate: swap('      day.setDate(day.getDate() + 1);\n', '') },
  { name: 'grouped by a file\'s own folder', catches: ['M4a'], file: 'model', mutate: swap("return group === 'folder' && key ? folderGroupOf(key) : key;", 'return key;') },
  { name: 'the head counts the last child folder only', catches: ['M4a'], file: 'model', mutate: swap('    c.count += numberOr(g.count) || 0;', '    c.count = numberOr(g.count) || 0;') },
  { name: 'a blank reason said blank', catches: ['M4b'], file: 'model', mutate: swap("label: key || (group === 'reason' ? WORDS.noReason : ABSENT)", 'label: key') },
  { name: 'running not counted per table', catches: ['M5'], file: 'model', mutate: swap('running: count(running.get(t.table_name))', 'running: count(0)') },
  { name: 'a waiting retry drawn as a failure', catches: ['M6'], file: 'model', mutate: swap("return tone === 'ok' ? 'ok' : tone === 'danger' ? 'danger' : 'warn';", "return tone === 'ok' ? 'ok' : 'danger';") },
  { name: 'the picked line not marked', catches: ['P1a'], file: 'parts', mutate: swap("`fi-file${view.picked === log.id ? ' is-picked' : ''}`", "'fi-file'") },
  { name: 'Show more always', catches: ['P1b'], file: 'parts', mutate: swap('    if (view.more) {', '    if (true) {') },
  { name: 'no reason box on a failure', catches: ['P2a'], file: 'parts', mutate: swap("    if (String(log.status) === 'FAILED' || reason && String(log.status) !== 'SUCCESS') {", '    if (false) {') },
  { name: 'Copy folder copies the path', catches: ['P2a'], file: 'parts', mutate: swap('copy(WORDS.copyFolder, folder.full)', 'copy(WORDS.copyFolder, log.filepath)') },
  { name: 'All counts nothing', catches: ['P3'], file: 'parts', mutate: swap("[{ key: 'ALL', count: total }", "[{ key: 'ALL', count: 0 }") },
  { name: 'the rows link without its tx', catches: ['P2c'], file: 'model', mutate: swap('tx: String(log.transaction_id)', "tx: ''") },
  { name: 'the address opens a table the list lacks', catches: ['G1'], file: 'narrowing', mutate: swap("(tables || []).includes(p.get('table')) ? p.get('table') : null", "p.get('table')") },
  { name: 'Find table narrows nothing', catches: ['P4'], file: 'parts', mutate: swap('.filter((t) => !want || String(t.name).toLowerCase().includes(want))', '') },
];

const base = await suite(await load());
const BASE_NAMES = NAMES.slice();
if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
const { wrong } = await scoreMutants(MUTANTS, async (m) => {
  const d = await load(m);
  const real = console.log;
  console.log = () => {};
  try { const r = await suite(d); return { failures: r.failed, ran: r.ran }; } finally { console.log = real; }
}, { baselineRan: base.ran, baselineNames: BASE_NAMES, title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
process.exit(wrong ? 1 : 0);
