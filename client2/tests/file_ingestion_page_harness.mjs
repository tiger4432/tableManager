// THE FILE INGESTION PAGE (owner 10-20 «ㅇㅇ 일케 해», lead; mockup FWp74vd6UqX1i7qXpyQg8K): its words and its parts.
//   M1 a read's Result: «400 rows · 12 new · 388 unchanged» (zeros after the rows left out); a failure - its reason; none counted - ABSENT
//   M2 Took «0.4 s»; none timed - ABSENT
//   M3 the query: blanks left out, status ALL by default, `to` a day included (until = the day after), the group word
//   M4 grouped by folder - each line in the server's group (its group_key), the server's label · count · failed, in the
//      rows' order; a folder group stands for the folder asked + its name («.» the folder asked itself);
//      by reason - a blank reason «(No reason)»; no group - one group without a head
//   M5 the table list: ok · failed from /tables, running from /active per table
//   M6 a status's word and tone: PENDING_RETRY «Pending retry» warn · FAILED danger · SUCCESS ok
//   M7 the folder a group stands for: the asked folder + the name in its separator, «.» the asked folder, none asked - the label
//   P1 the files part: a head per group with its count (a folder's head narrows the search to it), a line per file with its
//      folder (whole in the tooltip), «Retry N failed» on a folder with failures, the picked
//      one marked, a press hands the log; Show more only while more match
//   P2 the detail: a failure - «Why it failed» with the reason and the frame, «Retry this file»; a success - «Read again», no
//      reason box; Copy folder copies the folder; only the counts the server wrote
//   P3 the search line: All counts every status, the picked chip marked, a field's change hands its one key
//   P4 the table list: Find table narrows, the picked one marked, a press hands its name
//   P5 two of each part in one page do not touch each other's div
//   M8 · P7 · P8 the checklist's progress (owner 10-23): a row per table and source «K / N read · M left», nothing left
//      dimmed, the total's limit in the Files tooltip, «counted N s ago» · «counting» · «count failed»; none - its line
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
// a line is a file - its checklist row (A daafb2214); `id` is its newest record, null before its first read
const log = (id, over = {}) => ({ id, checklist_id: id + 1000, filename: 'bmap.txt', filepath: P('', '', 'fab', 'LOT', 'STEP_01', `W${id}`, 'bmap.txt'), folder: P('', '', 'fab', 'LOT', 'STEP_01', `W${id}`),
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
  ok('M1c a read the write refused part of: its counts, then the server\'s words for what it refused (총괄 10-21)',
    M.resultText(log(5, { rows_read: 1, rows_new: 0, rows_changed: 0, rows_unchanged: 0, rows_refused: 1,
      reason: '1 map refused: version_older' })) === '1 row · 1 refused · 1 map refused: version_older',
    M.resultText(log(5, { rows_read: 1, rows_new: 0, rows_changed: 0, rows_unchanged: 0, rows_refused: 1,
      reason: '1 map refused: version_older' })));
  ok('M2 Took in seconds; none timed - ABSENT', M.tookText(0.4) === '0.4 s' && M.tookText(null) === ABSENT && M.tookText(12.6) === '13 s', `${M.tookText(0.4)} ${M.tookText(12.6)}`);

  const q = M.queryOf({ table: 't', status: '', name: ' bmap ', folder: '', from: '2026-10-19', to: '2026-10-20', group: 'folder' }, { page: 2 });
  ok('M3 the query: blanks out, ALL by default, the To day included, the group word', q.get('table') === 't' && q.get('status') === 'ALL' && q.get('name') === 'bmap'
    && !q.has('folder') && q.get('since') === '2026-10-19' && q.get('until') === '2026-10-21' && q.get('group') === 'folder' && q.get('page') === '2', q.toString());

  const F1 = P('', '', 'fab', 'LOT', 'STEP_01');
  const F2 = P('', '', 'fab', 'LOT', 'STEP_02');
  const X = P('', '', 'fab', 'LOT');
  const rows = [log(11, { folder: F1, group_key: 'step_01' }), log(12, { folder: F1, group_key: 'step_01', status: 'FAILED', reason: 'bad' }),
    log(21, { folder: X, group_key: '.' })];
  const server = [{ key: 'step_01', label: 'STEP_01', count: 5, failed: 2 }, { key: '.', label: '.', count: 2, failed: 0 }];
  const byFolder = M.groupFiles(rows, 'folder', server, X);
  ok('M4a by folder: the server\'s groups as given, in the rows\' order',
    byFolder.length === 2 && byFolder[0].key === 'step_01' && byFolder[0].label === 'STEP_01' && byFolder[0].folder === F1 && byFolder[0].files.length === 2
      && byFolder[0].count === 5 && byFolder[0].failed === 2 && byFolder[1].folder === X && byFolder[1].count === 2,
    JSON.stringify(byFolder.map((g) => [g.key, g.label, g.folder, g.files.length, g.count, g.failed])));
  const byReason = M.groupFiles([log(31, { group_key: null }), log(32, { group_key: 'bad', status: 'FAILED' })], 'reason',
    [{ key: null, label: null, count: 2, failed: 0 }, { key: 'bad', label: 'bad', count: 1, failed: 1 }]);
  const none = M.groupFiles(rows, '', server);
  ok('M4b by reason - a blank reason «(No reason)»; no group - one group, no head',
    byReason[0].label === M.WORDS.noReason && byReason[0].count === 2 && byReason[1].label === 'bad' && none.length === 1 && none[0].head === false && none[0].files.length === 3,
    JSON.stringify(byReason.map((g) => [g.label, g.count])));
  ok('M7 the folder a group stands for', M.groupFolder(X, 'STEP_01') === F1 && M.groupFolder(X + BS, 'W1') === P(X, 'W1') && M.groupFolder('/srv/a/', 'b') === '/srv/a/b'
    && M.groupFolder(X, '.') === X && M.groupFolder('', F2) === F2, `${M.groupFolder(X, 'STEP_01')} ${M.groupFolder(X, '.')}`);

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
  const drills = [];
  const retries = [];
  const readAlls = [];
  const files = new Q.FilesPart(host, { doc, onPick: (l) => picks.push(l.id), onMore: () => { mores += 1; }, onDrill: (k) => drills.push(k),
    onRetryFolder: (g) => retries.push(g.folder), onReadAll: (f) => readAlls.push(f) });
  files.render({ groups: byFolder, shown: 'x', picked: 1012, more: true });
  const fileRows = walk(host).filter((n) => n.tagName === 'TR' && String(n.className).includes('fi-file'));
  const folderSpan = walk(fileRows[0]).find((n) => n.tagName === 'SPAN' && n.title);
  fileRows[1].dispatch('click');
  const more = byClass(host, 'fi-more')[0];
  if (more) more.dispatch('click');
  ok('P1a a head per group with its count, a line per file with its folder, the picked marked, a press hands the log',
    texts(host, 'fi-group__line').length === 2 && texts(host, 'fi-group__line')[0].includes(M.WORDS.groupSummary(5, 2)) && fileRows.length === 3
      && folderSpan && folderSpan.title === P('', '', 'fab', 'LOT', 'STEP_01', 'W11', '') && String(fileRows[1].className).includes('is-picked')
      && JSON.stringify(picks) === '[12]' && mores === 1, `${texts(host, 'fi-group__line')} rows ${fileRows.length} picks ${picks}`);
  const drill = byClass(host, 'fi-group__drill')[0];
  if (drill) drill.dispatch('click');
  ok('P1c a folder\'s head narrows the search to that folder', drill && drill.textContent === 'STEP_01' && JSON.stringify(drills) === JSON.stringify([F1]), JSON.stringify(drills));
  const retryButtons = byClass(host, 'fi-group__retry');
  if (retryButtons[0]) retryButtons[0].dispatch('click');
  ok('P1d «Retry N failed» on a folder with failures only, handing that folder', retryButtons.length === 1 && retryButtons[0].textContent === M.WORDS.retryFailed(2)
    && JSON.stringify(retries) === JSON.stringify([F1]), `${retryButtons.length} ${JSON.stringify(retries)}`);
  const readAllButtons = byClass(host, 'fi-readall');
  for (const b of readAllButtons) b.dispatch('click');
  ok('P1e «Read all again» on every folder head, handing that folder; no table named - none on the box head (총괄 10-21)',
    readAllButtons.length === 2 && readAllButtons.every((b) => b.textContent === M.WORDS.readAll) && readAlls.length === 2 && readAlls[0] === F1,
    `${readAllButtons.length} ${JSON.stringify(readAlls)}`);
  files.render({ groups: byFolder, shown: 'x', picked: null, more: false, table: 't1' });
  const tableReadAll = byClass(byClass(host, 'fi-box-head')[0], 'fi-readall');
  if (tableReadAll[0]) tableReadAll[0].dispatch('click');
  ok('P1f a table named: «Read all again» on the box head too, handing no folder - the whole table',
    tableReadAll.length === 1 && readAlls.length === 3 && readAlls[2] === null, JSON.stringify(readAlls));
  ok('P1g a folder head says what waits: «N waiting»', M.WORDS.groupSummary(5, 2, 3).endsWith(' · 3 waiting') && !M.WORDS.groupSummary(5, 2, 0).includes('waiting'));
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
  // a file not read yet - only its waiting read (A daafb2214): no record to retry, so the press is shut and says why
  detail.render({ ...log(15, { status: 'PENDING_RETRY', rows_read: null }), id: null });
  const shut = byClass(dHost, 'fi-btn--primary')[0];
  ok('P2d a file not read yet: its Retry is shut and says why', shut && shut.disabled === true
    && shut.title === M.WORDS.notReadYet, `${shut && shut.disabled} «${shut && shut.title}»`);
  // two such files are two lines - one picked is that one alone
  const pending = new Q.FilesPart(doc.createElement('div'), { doc, onPick() {}, onMore() {}, onDrill() {}, onRetryFolder() {} });
  pending.render({ groups: [{ key: null, head: false, files: [{ ...log(16), id: null }, { ...log(17), id: null }] }], shown: 'p', picked: 1017, more: false });
  const marked = walk(pending.mount).filter((n) => n.tagName === 'TR' && String(n.className).includes('is-picked'));
  ok('P1h two files not read yet are two lines - the picked one alone is marked', marked.length === 1 && marked[0].dataset.log === '1017',
    `${marked.length} ${marked.map((n) => n.dataset.log)}`);
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
  new Q.FilesPart(one, { doc, onPick() {}, onMore() {}, onDrill() {}, onRetryFolder() {} }).render({ groups: byFolder, shown: 'one', picked: null, more: false });
  new Q.FilesPart(two, { doc, onPick() {}, onMore() {}, onDrill() {}, onRetryFolder() {} }).render({ groups: none, shown: 'two', picked: null, more: false });
  ok('P5 two parts in one page keep to their own div', byClass(one, 'fi-group').length === 2 && byClass(two, 'fi-group').length === 0 && texts(one, 'fi-meta')[0] === 'one');

  // M8 · P7 - the checklist's progress (owner 10-23): a line per table and source, nothing left dimmed, when it was counted
  //   and an external source's last sweep, «Cancel waiting re-reads» where it has some waiting (A 11618814f)
  const NAS = P('', '', 'nas', 'void');
  const SWEEP = { state: 'rested', age_seconds: 40.2, seconds: 3, looked: 1200, already_read: 1197, dispatched: 3, why: { new: 2, changed: 1, retry: 0 } };
  const TABLES = [{ table_name: 'inspection_run', sources: [{ source: 'raws', total: 5, read: 3, left: 2, left_by_status: { PENDING_RETRY: 2 } },
    { source: NAS, total: 4, read: 4, left: 0, sweep: { ...SWEEP, dispatched: 0, why: {} } },
    { source: P('', '', 'nas', 'bond'), total: 9, read: 6, left: 3, left_by_status: { PENDING_RETRY: 2, FAILED: 1 }, sweep: SWEEP }] },
    { table_name: 'dt_log', sources: [] }];
  const srcLines = M.sourceLines(TABLES);
  const at = Date.parse('2026-10-23T05:00:00Z');
  ok('M8 a line per table and source, done when nothing is left; counted N s ago - counting before the first count, a failed count said',
    srcLines.length === 3 && srcLines[0].table === 'inspection_run' && !srcLines[0].done && srcLines[1].done
      && M.countedText({ counted_at: '2026-10-23T04:59:48Z' }, at) === 'counted 12 s ago' && M.countedText({ counting: true }, at) === 'counting'
      && M.countedText({ failed: 'timeout', counted_at: '2026-10-23T04:59:48Z' }, at) === 'count failed'
      && M.PROGRESS_COLUMNS.map((c) => c.cell(srcLines[0])).join(' | ') === `inspection_run | raws | 3 / 5 read · 2 left | ${ABSENT}`, JSON.stringify(srcLines));
  ok('M9 a sweep said: when, how long, looked, sent and why by word (none sent - no words); sweeping now; unavailable',
    M.sweepText(SWEEP) === 'last sweep 40 s ago, took 3.0 s · looked 1,200 · sent 3 (new 2 · changed 1)'
      && M.sweepText({ ...SWEEP, dispatched: 0, why: {} }) === 'last sweep 40 s ago, took 3.0 s · looked 1,200 · sent 0'
      && M.sweepText({ ...SWEEP, state: 'sweeping' }) === 'sweeping · looked 1,200 · sent 3 (new 2 · changed 1)'
      && M.sweepText({ state: 'unavailable' }) === 'unavailable', M.sweepText(SWEEP));
  ok('M10 Cancel waiting re-reads only on an external source with some waiting, its folder its root; the ask says the count, '
    + 'the states they go back to and that other tables are put back too',
    JSON.stringify(srcLines.map((l) => l.cancel)) === JSON.stringify([null, null, P('', '', 'nas', 'bond')])
      && M.cancelAsk({ message: '2 waiting file(s) under X to put back', by_state: { FAILED: 1, SUCCESS: 1 } })
        === '2 waiting file(s) under X to put back\nBack to: Failed 1 · Success 1\nOther tables reading this folder have their waiting files put back too',
    JSON.stringify(srcLines.map((l) => l.cancel)));
  const pHost = doc.createElement('div');
  doc.body.append(pHost);
  const cancels = [];
  new Q.ProgressPart(pHost, { doc, onCancel: (folder) => cancels.push(folder) }).render(srcLines, 'counted 12 s ago');
  const pRows = walk(pHost).filter((n) => n.tagName === 'TR' && n.dataset && n.dataset.table);
  const pCells = (tr) => walk(tr).filter((n) => n.tagName === 'TD').map((n) => n.textContent);
  const filesHead = walk(pHost).filter((n) => n.tagName === 'TH').find((n) => n.textContent === 'Files');
  ok('P7 a row per source «K / N read · M left», nothing left dimmed, the total\'s limit in the Files tooltip, when counted in the head',
    pRows.length === 3 && pCells(pRows[0])[2] === '3 / 5 read · 2 left' && pRows[1].className === 'fi-dim' && pRows[0].className !== 'fi-dim'
      && filesHead && filesHead.title === 'files a sweep has not reached yet are not in the total' && texts(pHost, 'fi-meta')[0] === 'counted 12 s ago',
    JSON.stringify(pRows.map(pCells)));
  const pButtons = walk(pHost).filter((n) => n.tagName === 'BUTTON');
  (pButtons[0] && pButtons[0].listeners.click || []).forEach((fn) => fn());
  ok('P9 one Cancel waiting re-reads, on its row, handing its folder', pButtons.length === 1 && walk(pRows[2]).includes(pButtons[0])
    && JSON.stringify(cancels) === JSON.stringify([P('', '', 'nas', 'bond')]), JSON.stringify(cancels));
  const pNone = doc.createElement('div');
  new Q.ProgressPart(pNone, { doc }).render([], 'counting');
  ok('P8 none counted yet - its line', texts(pNone, 'fi-say')[0] === M.WORDS.noSources);

  // P6 - Read now: who reads the path and why the watcher did not (the server's words), a button per owner
  const rHost = doc.createElement('div');
  doc.body.append(rHost);
  const asked = [];
  const reads = [];
  const answer = { path: 'X:\share\a\notes.txt', owners: [
    { table: 'ta', source: 'X:\share', why_not: ['name not matched'] }, { table: 'tb', source: 'raws', why_not: [] }] };
  let refuse = '';
  const rn = new Q.ReadNowPart(rHost, { doc, onCheck: async (p) => { asked.push(p); if (refuse) throw new Error(refuse); return answer; },
    onRead: (p, table) => reads.push([p, table]) });
  rn.render();
  const pathInput = walk(rHost).find((n) => n.tagName === 'INPUT');
  pathInput.value = '  X:\share\a\notes.txt ';
  walk(rHost).find((n) => n.tagName === 'FORM').dispatch('submit', { preventDefault() {} });
  await new Promise((r) => setTimeout(r, 0));
  const owners = byClass(rHost, 'fi-readnow__owner');
  const said = owners.map((o) => walk(o).filter((n) => n.dataset && n.dataset.tone).map((n) => `${n.dataset.tone}:${n.textContent}`)[0]);
  const buttons = byClass(rHost, 'fi-btn--primary');
  if (buttons[1]) buttons[1].dispatch('click');
  ok('P6a Check asks the trimmed path; a line per owner with the server\'s reason or «the watcher takes it»; Read now hands that owner',
    JSON.stringify(asked) === JSON.stringify(['X:\share\a\notes.txt']) && owners.length === 2
      && JSON.stringify(said) === JSON.stringify(['warn:name not matched', `ok:${M.WORDS.taken}`]) && buttons.length === 2
      && JSON.stringify(reads) === JSON.stringify([['X:\share\a\notes.txt', 'tb']]), `${asked} ${JSON.stringify(said)} ${JSON.stringify(reads)}`);
  refuse = 'No table reads X:\e.csv: it is under no raws folder and no external source root';
  await rn.check();
  ok('P6b a refusal: the server\'s sentence where the owners were, no button', byClass(rHost, 'fi-why')[0]?.textContent === M.WORDS.notRead + refuse
    && byClass(rHost, 'fi-readnow__owner').length === 0, byClass(rHost, 'fi-why')[0]?.textContent);
  return { ran, failed: failed.slice() };
}

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { name: 'zeros said too', catches: ['M1a'], file: 'model', mutate: swap('    if (numberOr(v)) parts.push', '    if (numberOr(v) !== null) parts.push') },
  { name: 'a read\'s refusal not said', catches: ['M1c'], file: 'model', mutate: swap('  if (!isBlank(log.reason)) parts.push(String(log.reason));', '') },
  { name: 'a failure said by its counts', catches: ['M1b'], file: 'model', mutate: swap("  if (isFailedStatus(log.status)) return reasonOf(log) || ABSENT;", '') },
  { name: 'Took without its unit', catches: ['M2'], file: 'model', mutate: swap("Math.round(s).toLocaleString('en-US')} s`", "Math.round(s).toLocaleString('en-US')}`") },
  { name: 'the To day left out (until = To)', catches: ['M3'], file: 'model', mutate: swap('      day.setDate(day.getDate() + 1);\n', '') },
  { name: 'the head count not the server\'s', catches: ['M4a'], file: 'model', mutate: swap('count: numberOr(c.count)', 'count: null') },
  { name: 'a line grouped by its own folder, not the server\'s key', catches: ['M4a'], file: 'model', mutate: swap('const key = keyOf(row.group_key);', 'const key = keyOf(row.folder);') },
  { name: 'the head says the key, not the label', catches: ['M4a'], file: 'model', mutate: swap('const label = isBlank(c.label) ? key : String(c.label);', 'const label = key;') },
  { name: '«.» drawn as a folder below', catches: ['M7'], file: 'model', mutate: swap("  if (!label || label === '.') return b;", '  if (!label) return b;') },
  { name: 'a folder head narrows to nothing', catches: ['P1c'], file: 'parts', mutate: swap('this.deps.onDrill(g.folder)', "this.deps.onDrill('')") },
  { name: 'Retry on every folder', catches: ['P1d'], file: 'parts', mutate: swap('if (g.failed > 0) {', 'if (true) {') },
  { name: 'Read all again on a folder hands the table', catches: ['P1e'], file: 'parts', mutate: swap('acts.append(this.readAll(g.folder));', 'acts.append(this.readAll(null));') },
  { name: 'no Read all again for the whole table', catches: ['P1f'], file: 'parts', mutate: swap('if (view.table) top.append(this.readAll(null));', '') },
  { name: 'what waits not said', catches: ['P1g'], file: 'model', mutate: swap("${waiting ? ` · ${count(waiting)} waiting` : ''}", '') },
  { name: 'a blank reason said blank', catches: ['M4b'], file: 'model', mutate: swap("label: label || (group === 'reason' ? WORDS.noReason : ABSENT)", 'label: label') },
  { name: 'running not counted per table', catches: ['M5'], file: 'model', mutate: swap('running: count(running.get(t.table_name))', 'running: count(0)') },
  { name: 'a waiting retry drawn as a failure', catches: ['M6'], file: 'model', mutate: swap("return tone === 'ok' ? 'ok' : tone === 'danger' ? 'danger' : 'warn';", "return tone === 'ok' ? 'ok' : 'danger';") },
  { name: 'the picked line not marked', catches: ['P1a'], file: 'parts', mutate: swap("`fi-file${view.picked === log.checklist_id ? ' is-picked' : ''}`", "'fi-file'") },
  { name: 'Show more always', catches: ['P1b'], file: 'parts', mutate: swap('    if (view.more) {', '    if (true) {') },
  { name: 'Read now hides why the watcher did not', catches: ['P6a'], file: 'parts', mutate: swap("owner.why_not.length ? owner.why_not.join(' · ') : WORDS.taken", 'WORDS.taken') },
  { name: 'Read now hands the first owner', catches: ['P6a'], file: 'parts', mutate: swap('this.deps.onRead(this.answer.path, owner.table)', 'this.deps.onRead(this.answer.path, this.answer.owners[0].table)') },
  { name: 'no reason box on a failure', catches: ['P2a'], file: 'parts', mutate: swap('    if (isFailedStatus(log.status) || (reason && !isDoneStatus(log.status))) {', '    if (false) {') },
  { name: 'Copy folder copies the path', catches: ['P2a'], file: 'parts', mutate: swap('copy(WORDS.copyFolder, folder.full)', 'copy(WORDS.copyFolder, log.filepath)') },
  { name: 'All counts nothing', catches: ['P3'], file: 'parts', mutate: swap("[{ key: 'ALL', count: total }", "[{ key: 'ALL', count: 0 }") },
  { name: 'the rows link without its tx', catches: ['P2c'], file: 'model', mutate: swap('tx: String(log.transaction_id)', "tx: ''") },
  { name: 'the address opens a table the list lacks', catches: ['G1'], file: 'narrowing', mutate: swap("(tables || []).includes(p.get('table')) ? p.get('table') : null", "p.get('table')") },
  { name: 'a source with nothing left not dimmed', catches: ['P7'], file: 'parts', mutate: swap("el('tr', line.done ? 'fi-dim' : '')", "el('tr', '')") },
  { name: 'the left count is the total', catches: ['M8'], file: 'model', mutate: swap('read · ${count(s.left)} left', 'read · ${count(s.total)} left') },
  { name: 'the total\'s limit not said', catches: ['P7'], file: 'parts', mutate: swap('      if (c.title) th.title = c.title;\n', '') },
  { name: 'a sweep sends without its words', catches: ['M9'], file: 'model', mutate: swap("${why.length ? ` (${why.join(' · ')})` : ''}", '') },
  { name: 'Cancel on every source', catches: ['M10'], file: 'model', mutate: swap('cancel: s.sweep && waiting > 0 ? s.source : null', 'cancel: s.source') },
  { name: 'the ask hides the other tables', catches: ['M10'], file: 'model', mutate: swap(", 'Other tables reading this folder have their waiting files put back too']", ']') },
  { name: 'Cancel hands nothing', catches: ['P9'], file: 'parts', mutate: swap('this.deps.onCancel(line.cancel)', 'this.deps.onCancel(null)') },
  { name: 'a file not read yet offers Retry - log_id null', catches: ['P2d'], file: 'parts', mutate: swap('if (log.id == null) { act.disabled = true;', 'if (false) { act.disabled = true;') },
  { name: 'a line is its record id again - two files not read yet are one', catches: ['P1h'], file: 'parts',
    mutate: swap('view.picked === log.checklist_id', 'view.picked === log.id') },
  { name: 'counted said without its age', catches: ['M8'], file: 'model', mutate: swap('return `counted ${', 'return `counted${') },
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
