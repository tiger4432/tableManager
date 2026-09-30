/**
 * rnd_board — Save contrast (lead 3a262cc76). The part is driven against a fake of the tables'
 * own routes: contrast_run takes the PUT and answers the list, contrast_factor answers one
 * filtered read per run the way the chain would have filled it.
 *
 *   A  one save is ONE row: the marking's defects and controls, until = now, the walk arguments
 *      the candidate question carries and nothing else
 *   B  the saved run shows in the list, read with a sort the route accepts
 *   C  the chain's rows fill the count: factors N is what was read now (0 is 0); a failed read is unknown
 *   D  the factor rows' flags: unexamined, and incomplete from a STRING 'false'
 *   E  nothing to save from -> off, with the reason
 *   F  no controls -> the fact beside the button
 *   G  refusals are said
 *   H  two instances on one screen do not cross
 *   I  the board seats it on marking 1 with the candidate list's own question — ONE object
 *   J  what the real chain wrote, as the real route answers it (fixtures/rnd_board_contrast_chain.json,
 *      captured by the script beside it from the implementer's gate)
 *   L  the board's one question: the lists walk what Save saves; nothing marked is the default wafer
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe) except for the sentences it quotes.
 */
import { readFileSync } from 'node:fs';
import { loadBoardModules } from './lib/board_modules.mjs';
import { makeDoc, walk, byClass } from './lib/board_dom.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const LF = String.fromCharCode(10);
let ran = 0;
let failedList = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failedList.push(detail ? `${name} -- ${detail}` : name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};
const eq = (name, got, want) => ok(name, String(got) === String(want), `got ${got}, want ${want}`);
const settle = async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); };

// The real chain's rows through the real route — regenerate with the script beside it.
const CHAIN = JSON.parse(readFileSync(new URL('./fixtures/rnd_board_contrast_chain.json', import.meta.url), 'utf8'));
const NOW = Date.UTC(2026, 8, 30, 1, 2, 3);
const CASES = ['w:case-1', 'w:case-2'];
const CONTROL = 'w:good-1';
const QUESTION = { legacyRoute: 'candidate', direction: 'outgoing', node_limit: 1000 };

/** The tables' routes, as far as this part touches them. `factors` is what the chain wrote. */
function fakeTables({ refuseSave, refuseList } = {}) {
  const server = { runs: [], factors: {}, puts: [], gets: [] };
  server.fetch = async (url, init) => {
    const u = new URL(url, 'http://box');
    const reply = (status, body) => ({ ok: status < 400, status, json: async () => body });
    if (init && init.method === 'PUT') {
      const body = JSON.parse(init.body);
      server.puts.push({ path: u.pathname, body });
      if (refuseSave) return reply(400, { detail: refuseSave });
      for (const one of body.updates) {
        server.runs.unshift({ row_id: `r${server.runs.length}`, data: Object.fromEntries(
          Object.entries(one.updates).map(([k, v]) => [k, { value: v }])) });
      }
      return reply(200, { updated: body.updates.length });
    }
    server.gets.push(u);
    if (u.pathname === '/tables/contrast_run/data') {
      if (refuseList) return reply(422, { detail: refuseList });
      if (!['id', 'updated_at', 'row_id', 'run_id', 'until'].includes(u.searchParams.get('order_by'))) {
        return reply(422, { detail: `cannot sort by '${u.searchParams.get('order_by')}'` });
      }
      return reply(200, { data: server.runs.slice(0, Number(u.searchParams.get('limit'))), total: server.runs.length });
    }
    if (u.pathname === '/tables/contrast_factor/data') {
      const f = JSON.parse(u.searchParams.get('filters') || '{}').run_id || {};
      if (server.factors[f.filter] === 'refuse') return reply(500, { detail: 'boom' });
      const rows = f.type === 'equals' ? (server.factors[f.filter] || []) : [];
      return reply(200, { data: rows.slice(0, Number(u.searchParams.get('limit'))), total: rows.length });
    }
    return reply(404, { detail: 'Not Found' });
  };
  return server;
}
const factorRow = (runId, i, extra = {}) => ({ row_id: `f${i}`, data: {
  run_id: { value: runId }, node_id: { value: `n:${i}` }, contrast: { value: 'contrasted' },
  complete: { value: 'true' }, ...Object.fromEntries(Object.entries(extra).map(([k, v]) => [k, { value: v }])) } });

async function suite(mods) {
  const { MarkingStore, SIGN } = mods.store;
  const { ContrastSavePanel, CONTRAST_WORDS } = mods.parts.contrast;

  const seat = (server, extra = {}) => {
    const doc = extra.doc || makeDoc();
    const host = doc.createElement('div');
    doc.body.appendChild(host);
    const markings = extra.markings || new MarkingStore();
    const panel = new ContrastSavePanel(host, {
      doc, markings, reads: extra.reads || 'marking:1', title: 'Contrast',
      apiBase: '', fetchImpl: server.fetch, user: 'tester',
      candidateQuestion: extra.question || QUESTION, now: () => NOW, newId: extra.newId || (() => 'run-fixed'),
    });
    panel.mount();
    return { doc, host, markings, panel };
  };
  const saveBtn = (host) => byClass(host, 'rb-contrast-save')[0];
  const refreshBtn = (host) => byClass(host, 'rb-contrast-refresh')[0];
  const rowsOf = (host) => byClass(host, 'rb-contrast-row');
  const countsOf = (host, runId) => {
    const row = rowsOf(host).find((r) => r.getAttribute('data-run') === runId);
    return row ? byClass(row, 'rb-contrast-counts')[0].textContent : '(no row)';
  };
  const tagsOf = (host, runId) => {
    const row = rowsOf(host).find((r) => r.getAttribute('data-run') === runId);
    return row ? byClass(row, 'rb-cand-stat').map((t) => t.textContent).join(',') : '(no row)';
  };
  const lines = (host, cls) => byClass(host, cls).map((n) => n.textContent);

  console.log(`${LF}-- A. one save is one row --`);
  const server = fakeTables();
  const a = seat(server);
  await settle();
  for (const id of CASES) a.markings.set('marking:1', id, SIGN.CASE);
  a.markings.set('marking:1', CONTROL, SIGN.CONTROL);
  saveBtn(a.host).dispatch('click');
  await settle();
  eq('A1 one PUT, one row in it', `${server.puts.length}|${(server.puts[0] || { body: { updates: [] } }).body.updates.length}`, '1|1');
  const put = (server.puts[0] || { path: '', body: { updates: [{}] } });
  const one = put.body.updates[0] || {};
  const row = one.updates || {};
  eq('A2 through the tables\' own write door', put.path, '/tables/contrast_run/data/updates');
  eq('A3 keyed by its run id', `${one.business_key_val}|${row.run_id}`, 'run-fixed|run-fixed');
  eq('A4 the defects are the marking\'s cases, as JSON text', row.positive, JSON.stringify(CASES));
  eq('A5 the controls are the marking\'s controls, as JSON text', row.negative, JSON.stringify([CONTROL]));
  eq('A6 as_of is until, and it is now', row.until, new Date(NOW).toISOString());
  eq('A7 the columns are exactly these: no legacyRoute, no invented argument',
    Object.keys(row).sort().join(','), 'direction,negative,node_limit,positive,run_id,until');
  eq('A8 the walk arguments are the candidate question\'s', `${row.direction}|${row.node_limit}`, 'outgoing|1000');
  eq('A9 who saved it rides the write door', `${one.source_name}|${one.updated_by}`, 'rnd_board|tester');
  {
    const wServer = fakeTables();
    const w = seat(wServer, { question: { direction: 'both', follow: ['bonded_from'], include_superseded: true, hops: 2 } });
    await settle();
    w.markings.set('marking:1', CASES[0], SIGN.CASE);
    saveBtn(w.host).dispatch('click');
    await settle();
    const wr = (wServer.puts[0] && wServer.puts[0].body.updates[0].updates) || {};
    eq('A10 a carried list and flag are text, a number stays a number',
      `${JSON.stringify(wr.follow)}|${JSON.stringify(wr.include_superseded)}|${JSON.stringify(wr.hops)}`,
      '"[\\"bonded_from\\"]"|"true"|2');
  }

  console.log(`${LF}-- B. the saved run shows in the list --`);
  const listReads = server.gets.filter((u) => u.pathname === '/tables/contrast_run/data');
  ok('B1 the list is read on mount and again after the save', listReads.length === 2, `reads ${listReads.length}`);
  eq('B2 read with a sort the route accepts, newest first',
    `${(listReads[1] || new URL('http://x')).searchParams.get('order_by')}|${(listReads[1] || new URL('http://x')).searchParams.get('order_desc')}`,
    'updated_at|true');
  eq('B3 the run is one row of the list', rowsOf(a.host).length, 1);
  eq('B4 its counts are the row\'s own; no factor row read yet is said as 0', countsOf(a.host, 'run-fixed'),
    'defects 2 · controls 1 · factors 0');

  console.log(`${LF}-- C. the chain's rows fill the candidate count --`);
  server.factors['run-fixed'] = [0, 1, 2].map((i) => factorRow('run-fixed', i));
  server.gets.length = 0;
  refreshBtn(a.host).dispatch('click');
  await settle();
  eq('C1 three factor rows -> factors 3', countsOf(a.host, 'run-fixed'), 'defects 2 · controls 1 · factors 3');
  const factorReads = server.gets.filter((u) => u.pathname === '/tables/contrast_factor/data');
  eq('C2 one factor read per listed run', factorReads.length, rowsOf(a.host).length);
  const filt = factorReads[0] ? JSON.parse(factorReads[0].searchParams.get('filters')) : {};
  eq('C3 the read asks for THIS run only', `${filt.run_id && filt.run_id.type}|${filt.run_id && filt.run_id.filter}`, 'equals|run-fixed');
  eq('C4 and carries one row, not the run\'s candidates', factorReads[0] && factorReads[0].searchParams.get('limit'), '1');
  eq('C5 a contrasted, complete run carries no tag', tagsOf(a.host, 'run-fixed'), '');
  server.factors['run-fixed'] = 'refuse';
  refreshBtn(a.host).dispatch('click');
  await settle();
  eq('C6 a failed factor read is unknown, not 0', countsOf(a.host, 'run-fixed'), 'defects 2 · controls 1 · factors —');
  server.factors['run-fixed'] = [0, 1, 2].map((i) => factorRow('run-fixed', i));

  console.log(`${LF}-- D. the factor rows' flags --`);
  server.runs.unshift({ row_id: 'x1', data: { run_id: { value: 'run-cut' }, positive: { value: '["a"]' },
    negative: { value: '[]' }, until: { value: '2026-09-30T00:00:00Z' } } });
  server.factors['run-cut'] = [factorRow('run-cut', 7, { contrast: 'unexamined', complete: 'false' })];
  refreshBtn(a.host).dispatch('click');
  await settle();
  eq('D1 unexamined and incomplete, from the chain\'s own words', tagsOf(a.host, 'run-cut'),
    `${CONTRAST_WORDS.unexamined},${CONTRAST_WORDS.incomplete}`);
  eq('D2 the other run keeps no tag', tagsOf(a.host, 'run-fixed'), '');

  console.log(`${LF}-- J. what the real chain wrote, as the real route answers it --`);
  {
    const chainFetch = async (url) => {
      const u = new URL(url, 'http://box');
      const reply = (b) => ({ ok: true, status: 200, json: async () => b });
      if (u.pathname === '/tables/contrast_run/data') return reply(CHAIN.run_list);
      const f = JSON.parse(u.searchParams.get('filters') || '{}').run_id || {};
      return reply(CHAIN.factor_reads[f.filter] || { data: [], total: 0 });
    };
    const j = seat({ fetch: chainFetch });
    await settle();
    const w = CHAIN.written;
    ok('J1 the chain wrote rows for each of the three runs (else the rest proves nothing)',
      ['R_SEEN', 'R_OPEN', 'R_CUT'].every((r) => w[r] > 0), JSON.stringify(w));
    const said = (r) => `${countsOf(j.host, r).split(' · ').pop()}|${tagsOf(j.host, r)}`;
    eq('J2 a run with controls: the rows the chain wrote, no tag', said('R_SEEN'), `factors ${w.R_SEEN}|`);
    eq('J3 a run without controls: its rows, unexamined', said('R_OPEN'), `factors ${w.R_OPEN}|${CONTRAST_WORDS.unexamined}`);
    eq('J4 a cut walk: its rows, incomplete', said('R_CUT'), `factors ${w.R_CUT}|${CONTRAST_WORDS.incomplete}`);
  }

  console.log(`${LF}-- E. nothing to save from -> off, with the reason --`);
  const eServer = fakeTables();
  const e = seat(eServer);
  await settle();
  const off = saveBtn(e.host);
  eq('E1 an empty marking: off, and says why', `${off.disabled}|${off.getAttribute('title')}`, `true|${CONTRAST_WORDS.needDefects}`);
  e.markings.set('marking:1', CONTROL, SIGN.CONTROL);
  eq('E2 controls alone are not a question: still off', saveBtn(e.host).disabled, true);
  e.panel.save();
  await settle();
  eq('E3 and nothing is written', eServer.puts.length, 0);
  e.markings.set('marking:1', CASES[0], SIGN.CASE);
  eq('E4 one defect turns it on', `${saveBtn(e.host).disabled}|${saveBtn(e.host).getAttribute('title')}`, 'false|null');

  console.log(`${LF}-- F. no controls -> the fact beside the button --`);
  const fServer = fakeTables();
  const f = seat(fServer);
  await settle();
  ok('F1 no marking, no fact line', !lines(f.host, 'rb-cand-line--absent').includes(CONTRAST_WORDS.noControls));
  f.markings.set('marking:1', CASES[0], SIGN.CASE);
  ok('F2 defects without controls: the fact is said', lines(f.host, 'rb-cand-line--absent').includes(CONTRAST_WORDS.noControls),
    lines(f.host, 'rb-cand-line--absent').join(' | '));
  saveBtn(f.host).dispatch('click');
  await settle();
  eq('F3 and the save still goes, with no controls', fServer.puts[0] && fServer.puts[0].body.updates[0].updates.negative, '[]');
  eq('F4 an empty stored list is 0 controls', countsOf(f.host, 'run-fixed'), 'defects 1 · controls 0 · factors 0');

  console.log(`${LF}-- G. refusals are said --`);
  const gServer = fakeTables({ refuseSave: "Table 'contrast_run' not found" });
  const g = seat(gServer);
  await settle();
  g.markings.set('marking:1', CASES[0], SIGN.CASE);
  saveBtn(g.host).dispatch('click');
  await settle();
  ok('G1 a refused save says the server\'s words', lines(g.host, 'rb-cand-line--refused')
    .includes("Save refused — Table 'contrast_run' not found"), lines(g.host, 'rb-cand-line--refused').join(' | '));
  eq('G2 and the button is back on', saveBtn(g.host).disabled, false);
  const hServer = fakeTables({ refuseList: 'no such table' });
  const h = seat(hServer);
  await settle();
  ok('G3 an unreadable list says so, not "No saved contrasts"',
    lines(h.host, 'rb-cand-line--refused').includes('Saved contrasts unreadable — no such table')
    && !lines(h.host, 'rb-cand-line--absent').includes(CONTRAST_WORDS.empty),
    lines(h.host, 'rb-cand-line').join(' | '));
  const emptyServer = fakeTables();
  const empty = seat(emptyServer);
  await settle();
  ok('G4 a readable empty list says it is empty', lines(empty.host, 'rb-cand-line--absent').includes(CONTRAST_WORDS.empty));

  console.log(`${LF}-- H. two instances on one screen --`);
  const doc = makeDoc();
  const shared = new MarkingStore();
  const s1 = fakeTables();
  const s2 = fakeTables();
  const one1 = seat(s1, { doc, markings: shared, reads: 'marking:1' });
  const two2 = seat(s2, { doc, markings: shared, reads: 'marking:3' });
  await settle();
  shared.set('marking:1', CASES[0], SIGN.CASE);
  eq('H1 a mark under one\'s name turns on that one only', `${saveBtn(one1.host).disabled}|${saveBtn(two2.host).disabled}`, 'false|true');
  saveBtn(one1.host).dispatch('click');
  await settle();
  eq('H2 its save goes through its own store only', `${s1.puts.length}|${s2.puts.length}`, '1|0');
  eq('H3 the other keeps its own list', `${rowsOf(one1.host).length}|${rowsOf(two2.host).length}`, '1|0');
  ok('H4 neither draws inside the other', !walk(one1.host).includes(two2.host) && !walk(two2.host).includes(one1.host));

  console.log(`${LF}-- I. the board seats it --`);
  const seatDecl = (mods.main.BOARD.panels || []).find((p) => p.part === 'contrastSave');
  const cand = (mods.main.BOARD.panels || []).find((p) => p.part === 'candidateList');
  eq('I1 one seat, reading marking 1', seatDecl ? `${seatDecl.reads}|${Boolean(mods.main.PARTS.contrastSave)}` : '(none)', 'marking:1|true');
  const q = (seatDecl && seatDecl.options && seatDecl.options.candidateQuestion) || {};
  eq('I2 its question is the candidate list\'s own', `${q.direction}|${q.node_limit}`, `${cand && cand.direction}|${cand && cand.node_limit}`);
  const bound = mods.main.bindLoaders({ panels: [seatDecl || {}] }, { apiBase: 'B', fetchImpl: () => null, user: 'who' }).panels[0];
  eq('I3 the page hands it the user who saves', bound.options && bound.options.user, 'who');
  const seatOf = (id) => (mods.main.BOARD.panels || []).find((p) => p.id === id) || {};
  const starts = [seatOf('candidate-list').start, seatOf('rank-list').start,
    (seatOf('contrast-save').options || {}).candidateQuestion
      && seatOf('contrast-save').options.candidateQuestion.start,
    (seatOf('head-summary').options || {}).question && seatOf('head-summary').options.question.start];
  ok('I4 the lists, Save and the head read ONE question object', Boolean(starts[0]) && starts.every((s) => s === starts[0]));

  console.log(`${LF}-- L. the board's one question: the lists walk what Save saves --`);
  {
    const walked = [];
    const boardPuts = [];
    const boardFetch = async (url, init) => {
      const u = new URL(url, 'http://box');
      const reply = (status, body) => ({ ok: status < 400, status, json: async () => body });
      if (init && init.method === 'PUT') { boardPuts.push(JSON.parse(init.body)); return reply(200, {}); }
      if (u.pathname.endsWith('/api/ledger/subgraph')) { walked.push(u); return reply(503, { detail: 'box' }); }
      return reply(200, { data: [], total: 0 });
    };
    const bdoc = makeDoc();
    const bhost = bdoc.createElement('div');
    bdoc.body.appendChild(bhost);
    const bmarks = new MarkingStore();
    const shell = mods.main.boot(bdoc, bhost, {
      markings: bmarks, fetchImpl: boardFetch, user: 'u', observeSize: () => () => {},
      layout: { ...mods.main.BOARD, panels: ['candidate-list', 'rank-list', 'contrast-save'].map(seatOf),
        intersections: [] },
    });
    await settle();
    const cand = shell.partOf('candidate-list');
    const rank = shell.partOf('rank-list');
    const save = shell.partOf('contrast-save');
    const otherwise = seatOf('candidate-list').start.otherwise;
    const q = (u) => (u ? [u.searchParams.getAll('positive').join('+'), u.searchParams.getAll('negative').join('+'),
      u.searchParams.get('direction'), u.searchParams.get('node_limit')].join('|') : '(no walk)');
    const ids = (v) => { try { return JSON.parse(v).join('+'); } catch (e) { return '(not JSON text)'; } };
    const rowQ = (row) => (row ? [ids(row.positive), ids(row.negative), row.direction, row.node_limit].join('|')
      : '(no row)');
    eq('L1 nothing marked: the lists walk the default wafer, one defect and no controls',
      q(walked[walked.length - 1]), `${otherwise.value}||outgoing|1000`);
    const saveOn = byClass(save.host, 'rb-contrast-save')[0];
    ok('L2 ...and Save is on, saying what it will save',
      saveOn && !saveOn.disabled && lines(save.host, 'rb-cand-line--absent').includes(`${CONTRAST_WORDS.nothingMarked} ${otherwise.label}`),
      `${saveOn && saveOn.disabled} ${lines(save.host, 'rb-cand-line--absent').join(' | ')}`);
    await save.save();
    await settle();
    const firstRow = boardPuts[0] && boardPuts[0].updates[0].updates;
    eq('L3 saved as seen: the default wafer, no controls', rowQ(firstRow), q(walked[walked.length - 1]));
    const counted = [];
    for (const part of [cand, rank]) {
      const inner = part.walk;
      part.walk = (spec) => { counted.push([part === cand ? 'cand' : 'rank', JSON.stringify(spec)]); return inner(spec); };
    }
    bmarks.replace('marking:1', [[CASES[0], SIGN.CASE], [CASES[1], SIGN.CASE], [CONTROL, SIGN.CONTROL]]);
    await settle();
    eq('L4 a new marking is a new question: each list walks once more',
      counted.map((c) => c[0]).sort().join(','), 'cand,rank');
    eq('L5 the rank list asks exactly what the candidate list asks',
      counted.length === 2 && counted[0][1] === counted[1][1], true);
    await save.save();
    await settle();
    const secondRow = boardPuts[1] && boardPuts[1].updates[0].updates;
    eq('L6 what Save saves is the walk the lists drew', rowQ(secondRow), q(walked[walked.length - 1]));
    eq('L7 ...and that walk is the marking', q(walked[walked.length - 1]),
      `${CASES.join('+')}|${CONTROL}|outgoing|1000`);
    const before = walked.length;
    bmarks.replace('marking:1', [[CONTROL, SIGN.CONTROL]]);
    await settle();
    const off = byClass(save.host, 'rb-contrast-save')[0];
    eq('L8 controls alone: no walk, the lists say so, Save is off with the reason',
      `${walked.length - before}|${cand.loadState}|${rank.loadState}|${off.disabled}|${off.getAttribute('title')}`,
      `0|no-seed|no-seed|true|${CONTRAST_WORDS.needDefects}`);
    shell.destroy();
  }

  return { ran, failed: failedList.slice() };
}

const MUTANTS = [
  { name: 'the-whole-question-is-saved', catches: ['A7'], file: 'api.js',
    from: '  for (const key of CONTRAST.args) {',
    to: '  for (const key of Object.keys(r.question || {})) {' },
  { name: 'a-list-is-sent-raw', catches: ['A4', 'A5'], file: 'api.js',
    from: 'const cellText = (value) => (Array.isArray(value) ? JSON.stringify(value)',
    to: 'const cellText = (value) => (Array.isArray(value) ? value' },
  { name: 'a-flag-is-sent-raw', catches: ['A10'], file: 'api.js',
    from: "  : typeof value === 'boolean' ? String(value) : value);",
    to: '  : value);' },
  { name: 'until-is-dropped', catches: ['A6'], file: 'api.js',
    from: '    [CONTRAST.asOf]: r.asOf,\n',
    to: '' },
  { name: 'a-string-false-reads-as-complete', catches: ['D1'], file: 'api.js',
    from: "const saysFalse = (value) => value === false || String(value).trim().toLowerCase() === 'false';",
    to: 'const saysFalse = (value) => value === false;' },
  { name: 'the-count-is-the-rows-on-the-page', catches: ['J2', 'J3', 'J4'], file: 'api.js',
    from: '  const total = body && Number.isFinite(Number(body.total)) ? Number(body.total) : null;',
    to: '  const total = body && Array.isArray(body.data) ? body.data.length : null;' },
  { name: 'a-read-0-is-drawn-as-unknown', catches: ['B4', 'F4'], file: 'api.js',
    from: '    factors: total,',
    to: '    factors: total ? total : null,' },
  { name: 'the-list-sorts-by-a-name-the-table-lacks', catches: ['B2', 'B3'], file: 'api.js',
    from: '&order_by=updated_at&order_desc=true',
    to: '&order_by=as_of&order_desc=true' },
  { name: 'the-controls-are-ignored', catches: ['A5'],
    from: '      negative: seeds.negative || [],',
    to: '      negative: [],' },
  { name: 'the-button-is-on-without-defects', catches: ['E1', 'E2'],
    from: "(seeds ? '' : CONTRAST_WORDS.needDefects)",
    to: "''" },
  { name: 'unknown-is-drawn-as-0', catches: ['C6'],
    from: "    const count = (n) => (n === null || n === undefined ? '—' : String(n));",
    to: '    const count = (n) => String(n ?? 0);' },
  { name: 'an-empty-marking-means-nothing', catches: ['L1', 'L2'], file: 'panel.js',
    from: '    if (!entries.length && decl.otherwise) {',
    to: '    if (false) {' },
  { name: 'the-lists-do-not-follow-their-start', catches: ['L4'], file: 'panel.js',
    from: '    if (asked && asked !== this.reads && this.markings) {',
    to: '    if (false) {' },
  { name: 'the-save-asks-its-own-question', catches: ['I4', 'L2'], file: 'main.js',
    from: '      options: { candidateQuestion: LIST_QUESTION },',
    to: '      options: { candidateQuestion: CANDIDATE_QUESTION },' },
  { name: 'the-rank-list-keeps-a-fixed-seed', catches: ['I4', 'L5'], file: 'main.js',
    from: "      ...LIST_QUESTION,\n      title: 'Rank',",
    to: "      ...CANDIDATE_QUESTION, start: { groupby: 'wafer', value: 'w:fixed' },\n      title: 'Rank'," },
  { name: 'the-list-walk-drops-the-controls', catches: ['L6', 'L7'], file: 'api.js',
    from: '      ? { nodeId: start.value, positive: start.positive, negative: start.negative }',
    to: '      ? { nodeId: start.value, positive: start.positive }' },
  { name: 'no-controls-is-not-said', catches: ['F2'],
    from: '    if (seeds && !(seeds.negative || []).length) {',
    to: '    if (false) {' },
];

const main = async () => {
  console.log('== baseline ==');
  const base = await suite(await loadBoardModules());
  const BASE_NAMES = NAMES.slice();
  console.log(`${LF}${base.ran - base.failed.length} passed, ${base.failed.length} failed.`);
  if (base.failed.length) {
    console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`);
    process.exit(1);
  }
  const { wrong: escaped } = await scoreMutants(MUTANTS, async (m) => {
    let mods;
    try {
      mods = await loadBoardModules({
        [m.file || 'contrast_save_panel.js']:
          (src) => (src.includes(m.from) ? src.split(m.from).join(m.to) : src),
      });
    } catch (err) {
      console.error(`HARNESS FAILURE: ${err.message} (${m.name})`);
      console.error('(This is not a passing result. Nothing was compared.)');
      process.exit(2);
    }
    const real = console.log;
    console.log = () => {};
    ran = 0; failedList = [];
    try { await suite(mods); } finally { console.log = real; }
    return { failures: failedList, ran };
  }, { baselineRan: base.ran, baselineNames: BASE_NAMES,
       title: `${LF}== defect mutants (each must be CAUGHT by its named line) ==` });

  console.log(`${LF}ASSERTIONS ${base.ran} ${base.failed.length}`);
  process.exit(escaped ? 1 : 0);
};

main();
