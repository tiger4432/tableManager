/**
 * rnd_board — Save contrast (lead 3a262cc76). The part is driven against a fake of the tables'
 * own routes: contrast_run takes the PUT and answers the list, its rows stamped the way the chain
 * stamps a run it computed (lead 2dd93d4a9). Nothing else is read.
 *
 *   A  one save is ONE row: the marking's defects and controls, until = now, the walk arguments
 *      the candidate question carries and nothing else
 *   B  the saved run shows in the list, read with a sort the route accepts
 *   C  the run row says what the chain computed: Not computed yet / factors N · computed HH:MM (0 is 0)
 *   D  the run row's flags: unexamined, and incomplete from a STRING 'false'
 *   E  nothing to save from -> off, with the reason
 *   F  no controls -> the fact beside the button
 *   G  refusals are said
 *   H  two instances on one screen do not cross
 *   I  the board seats it on marking 1 with the candidate list's own question — ONE object
 *   J  what the real chain wrote, as the real route answers it (fixtures/rnd_board_contrast_chain.json,
 *      captured by the script beside it from the implementer's gate)
 *   L  the board's one question: the lists walk what Save saves; nothing marked is the default wafer
 *   M  the branch (lead 64c380aeb): Default asks what it asked before but its saved list, which reads the
 *      runs with no world (ccf374d48 answer 1); on a branch every request, the run row and the saved list
 *      carry it (fixtures/rnd_board_requests.before.json)
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

/** The tables' routes, as far as this part touches them. `compute` is what the chain writes on a run. */
function fakeTables({ refuseSave, refuseList, listStatus } = {}) {
  const server = { runs: [], puts: [], gets: [] };
  server.compute = (runId, cells) => {
    const row = server.runs.find((r) => r.data.run_id && r.data.run_id.value === runId);
    for (const [k, v] of Object.entries(cells)) row.data[k] = { value: v };
  };
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
      if (refuseList) return reply(listStatus || 422, { detail: refuseList });
      if (!['id', 'updated_at', 'row_id', 'run_id', 'until'].includes(u.searchParams.get('order_by'))) {
        return reply(422, { detail: `cannot sort by '${u.searchParams.get('order_by')}'` });
      }
      return reply(200, { data: server.runs.slice(0, Number(u.searchParams.get('limit'))), total: server.runs.length });
    }
    return reply(404, { detail: 'Not Found' });
  };
  return server;
}
const runRow = (id, cells) => ({ row_id: `x-${id}`, data: Object.fromEntries(
  Object.entries({ run_id: id, until: '2026-09-30T00:00:00Z', ...cells }).map(([k, v]) => [k, { value: v }])) });
// The viewer's wall clock of an instant, worked out here rather than by the formatter under test.
const hm = (iso) => { const d = new Date(iso); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
const AT = '2026-09-30T01:05:00Z';

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
  eq('B4 a saved run the chain has not computed says so', countsOf(a.host, 'run-fixed'),
    `defects 2 · controls 1 · ${CONTRAST_WORDS.notComputed}`);

  console.log(`${LF}-- C. the run row says what the chain computed --`);
  server.compute('run-fixed', { computed_at: AT, candidates: 3, contrast: 'contrasted', complete: 'true' });
  server.runs.unshift(runRow('run-zero', { positive: '["a"]', negative: '["b"]', computed_at: AT, candidates: 0,
    contrast: 'contrasted', complete: 'true' }));
  server.runs.unshift(runRow('run-blank', { positive: '["a"]', negative: '[]', computed_at: AT, candidates: '' }));
  server.runs.unshift(runRow('run-new', { positive: '["a"]', negative: '["b"]' }));
  server.runs.unshift(runRow('run-gap', { positive: '["a"," "]', negative: '["b",""]' }));
  server.runs.unshift(runRow('run-empty', { positive: '{}', negative: '[""]' }));
  server.runs.unshift(runRow('run-text', { positive: 'abc', negative: '["b"]' }));
  server.gets.length = 0;
  refreshBtn(a.host).dispatch('click');
  await settle();
  eq('C1 computed with three: factors 3 · computed HH:MM', countsOf(a.host, 'run-fixed'),
    `defects 2 · controls 1 · factors 3 · computed ${hm(AT)}`);
  eq('C2 the list is ONE read of the run table — no factor read', server.gets.map((u) => u.pathname).join(','),
    '/tables/contrast_run/data');
  eq('C3 a contrasted, complete run carries no tag', tagsOf(a.host, 'run-fixed'), '');
  eq('C4 computed with none: factors 0, an answer', countsOf(a.host, 'run-zero'),
    `defects 1 · controls 1 · factors 0 · computed ${hm(AT)}`);
  eq('C5 a computed run whose count is blank is unknown, not 0', countsOf(a.host, 'run-blank'),
    `defects 1 · controls 0 · factors — · computed ${hm(AT)}`);
  eq('C7 a blank id is not counted, as the chain\'s walk drops it (lead d4a949a8c ㉲)', countsOf(a.host, 'run-gap'),
    `defects 1 · controls 1 · ${CONTRAST_WORDS.notComputed}`);
  eq('C8 an object or a list of blanks holds no id (0); text that is not a list is unknown (lead dcd159739)',
    `${countsOf(a.host, 'run-empty')} | ${countsOf(a.host, 'run-text')}`,
    `defects 0 · controls 0 · ${CONTRAST_WORDS.notComputed} | defects — · controls 1 · ${CONTRAST_WORDS.notComputed}`);
  const lastOf = (r) => countsOf(a.host, r).split(' · ').slice(2).join(' · ');
  eq('C6 not computed, computed 0 and computed N are three different lines',
    new Set(['run-new', 'run-zero', 'run-fixed'].map(lastOf)).size, 3);

  console.log(`${LF}-- D. the run row's flags --`);
  server.runs.unshift(runRow('run-cut', { positive: '["a"]', negative: '[]', computed_at: AT, candidates: 5,
    contrast: 'unexamined', complete: 'false' }));
  refreshBtn(a.host).dispatch('click');
  await settle();
  eq('D1 unexamined and incomplete, from the chain\'s own words', tagsOf(a.host, 'run-cut'),
    `${CONTRAST_WORDS.unexamined},${CONTRAST_WORDS.incomplete}`);
  eq('D2 the other run keeps no tag', tagsOf(a.host, 'run-fixed'), '');
  eq('D3 a run not computed yet carries no tag', tagsOf(a.host, 'run-new'), '');

  console.log(`${LF}-- J. what the real chain wrote on its runs, as the real route answers it --`);
  {
    const gets = [];
    const chainFetch = async (url) => {
      const u = new URL(url, 'http://box');
      gets.push(u.pathname);
      return { ok: true, status: 200, json: async () => CHAIN.run_list };
    };
    const j = seat({ fetch: chainFetch });
    await settle();
    const w = CHAIN.written;
    const at = (r) => {
      const row = (CHAIN.run_list.data || []).find((x) => x.data.run_id.value === r);
      return row && row.data.computed_at ? row.data.computed_at.value : null;
    };
    ok('J1 the chain wrote factor rows for the three walked runs and none for the empty one (else the rest proves nothing)',
      w.R_SEEN > 0 && w.R_OPEN > 0 && w.R_CUT > 0 && w.R_EMPTY === 0 && Boolean(at('R_EMPTY')) && !at('R_WAITING'),
      JSON.stringify(w));
    const said = (r) => `${countsOf(j.host, r).split(' · ').slice(2).join(' · ')}|${tagsOf(j.host, r)}`;
    eq('J2 a run with controls: the rows the chain wrote, no tag', said('R_SEEN'), `factors ${w.R_SEEN} · computed ${hm(at('R_SEEN'))}|`);
    eq('J3 a run without controls: its rows, unexamined', said('R_OPEN'),
      `factors ${w.R_OPEN} · computed ${hm(at('R_OPEN'))}|${CONTRAST_WORDS.unexamined}`);
    eq('J4 a cut walk: its rows, incomplete', said('R_CUT'),
      `factors ${w.R_CUT} · computed ${hm(at('R_CUT'))}|${CONTRAST_WORDS.incomplete}`);
    eq('J5 a walk that reached nothing: factors 0, computed', said('R_EMPTY').split('|')[0],
      `factors 0 · computed ${hm(at('R_EMPTY'))}`);
    eq('J6 a run the chain has not walked yet', said('R_WAITING'), `${CONTRAST_WORDS.notComputed}|`);
    eq('J7 one read of the run table', gets.join(','), '/tables/contrast_run/data');
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
  eq('F4 an empty stored list is 0 controls', countsOf(f.host, 'run-fixed'),
    `defects 1 · controls 0 · ${CONTRAST_WORDS.notComputed}`);

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
  // The box's answer when the run table is not declared (measured 10-08: 404 "Table 'contrast_run' not found").
  const undeclared = seat(fakeTables({ refuseList: "Table 'contrast_run' not found", listStatus: 404 }));
  await settle();
  ok('G7 a run table the box does not declare is said as not set up - a fact, not a refusal, not empty (lead 10-08)',
    JSON.stringify(lines(undeclared.host, 'rb-cand-line--absent')) === JSON.stringify([CONTRAST_WORDS.notSetUp])
      && CONTRAST_WORDS.notSetUp === 'Not set up — table contrast_run is not declared'
      && lines(undeclared.host, 'rb-cand-line--refused').length === 0,
    lines(undeclared.host, 'rb-cand-line').join(' | '));
  const broken = seat(fakeTables({ refuseList: 'boom', listStatus: 500 }));
  await settle();
  ok('G8 any other failure of the list is still a refusal',
    JSON.stringify(lines(broken.host, 'rb-cand-line--refused')) === JSON.stringify(['Saved contrasts unreadable — boom'])
      && !lines(broken.host, 'rb-cand-line--absent').includes(CONTRAST_WORDS.notSetUp),
    lines(broken.host, 'rb-cand-line').join(' | '));
  // The server's other refusal shapes (lead d4a949a8c ㉮, C-52): a named reason and a list.
  const refusedWith = async (detail) => {
    const s = seat(fakeTables({ refuseSave: detail }));
    await settle();
    s.markings.set('marking:1', CASES[0], SIGN.CASE);
    saveBtn(s.host).dispatch('click');
    await settle();
    return lines(s.host, 'rb-cand-line--refused');
  };
  const named = await refusedWith({ reason: 'run_id_taken', argument: 'run_id', value: 'R1' });
  ok('G5 a named refusal keeps its reason and where', named.includes('Save refused — run_id_taken · run_id=R1'), named.join(' | '));
  const listed = await refusedWith([{ loc: ['body', 'updates'], msg: 'Field required' }]);
  ok('G6 a list refusal keeps each field and message', listed.includes('Save refused — updates · Field required'), listed.join(' | '));

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

  console.log(`${LF}-- M. the branch the board reads (lead 64c380aeb): one seat, every request --`);
  {
    // 🔴 EVERY REQUEST, NOT THIS ONE. The whole BOARD booted on a recording fetch AND a recording global
    //    fetch, then one Save. On the default the list is the one captured before the round; on a branch
    //    every one of them carries it - a request round the seat reads the default beside a branch's
    //    picture and nothing errors.
    const BEFORE = JSON.parse(readFileSync(new URL('./fixtures/rnd_board_requests.before.json', import.meta.url), 'utf8'));
    const drain = async () => { for (let i = 0; i < 40; i += 1) await new Promise((r) => setTimeout(r, 0)); };
    const boardOn = async (world) => {
      const urls = [];
      const picked = [];
      let row = null;
      const reply = (status, body) => ({ ok: status < 400, status, json: async () => body });
      const record = (via) => async (url, init) => {
        urls.push(`${via} ${(init && init.method) || 'GET'} ${String(url)}`);
        if (init && init.method === 'PUT') row = JSON.parse(init.body).updates[0].updates;
        const u = new URL(String(url), 'http://box');
        if (u.pathname.endsWith('/api/ledger/declaration')) {
          return reply(200, { sources: [], worlds: ['default', 'w1'], operating: 'w1' });
        }
        return reply(200, { data: [], total: 0 });
      };
      const keep = globalThis.fetch;
      globalThis.fetch = record('global');
      try {
        const bdoc = makeDoc();
        const bhost = bdoc.createElement('div');
        const mount = bdoc.createElement('span');
        bdoc.body.appendChild(bhost);
        bdoc.body.appendChild(mount);
        const shell = mods.main.boot(bdoc, bhost, { markings: new MarkingStore(), fetchImpl: record('injected'),
          user: 'u', observeSize: () => () => {}, world, branchMount: mount, pickWorld: (name) => picked.push(name) });
        await drain();
        await shell.partOf('contrast-save').save();
        await drain();
        // The worlds the board reads, pressed as chips (lead 99032248f): each press hands the page a list.
        const chips = byClass(mount, 'branch-picker__chip');
        const listed = chips.map((c) => `${c._text}${c.attrs['aria-pressed'] === 'true' ? '*' : ''}`);
        for (const label of ['w1', 'default', 'Operating · w1']) {
          const chip = chips.find((c) => c._text === label);
          if (chip) chip.dispatch('click');
        }
        shell.destroy();
        return { urls: urls.sort(), row, listed, picked };
      } finally {
        globalThis.fetch = keep;
      }
    };
    const onDefault = await boardOn(null);
    const onBranch = await boardOn('w1');
    const onBlank = await boardOn('  ');
    const byName = await boardOn('default');
    const both = await boardOn(['w1', 'default']);
    const rowKeys = (r) => (r ? Object.keys(r).sort().join(',') : '(no save)');
    // 🔴 ONE NAMED EXCEPTION (lead ccf374d48 answer 1): Default's saved list reads the runs with no world,
    //    so that one request adds the table filter's blank condition. Every other request is the day before's.
    const BLANK = JSON.stringify({ world: { filterType: 'text', type: 'blank' } });
    const isList = (u) => u.includes(' GET ') && u.includes('/tables/contrast_run/data?');
    const DEFAULT_NOW = BEFORE.urls.map((u) => (isList(u) ? `${u}&filters=${encodeURIComponent(BLANK)}` : u)).sort();
    eq('M1 no world: the whole board asks what it asked before the round, byte for byte - but the saved list',
      BEFORE.urls.some(isList) && JSON.stringify(onDefault.urls) === JSON.stringify(DEFAULT_NOW)
        && rowKeys(onDefault.row) === BEFORE.saveRowKeys.join(','), true);
    eq('M2 the empty choice is named after the operating world, pressed while none is; then the declaration\'s worlds',
      onDefault.listed.join(','), 'Operating · w1*,default,w1');
    const lacking = onBranch.urls.filter((u) => !u.includes('world=w1'));
    eq('M3 on a branch every request of the board carries it',
      `${onBranch.urls.length}|${lacking.length}`, `${BEFORE.urls.length}|0`);
    eq('M4 ...and none goes round the page\'s fetch', onBranch.urls.filter((u) => u.startsWith('global')).length, 0);
    eq('M5 the saved run says its branch; with no world the row is the day before\'s',
      `${onBranch.row && onBranch.row.world}|${rowKeys(onDefault.row)}`, `w1|${BEFORE.saveRowKeys.join(',')}`);
    const listUrl = onBranch.urls.find((u) => u.includes(' GET ') && u.includes('/tables/contrast_run/data?')) || '';
    const filters = new URL(listUrl.split(' ').pop() || 'http://box', 'http://box').searchParams.get('filters');
    eq('M6 the saved list reads that branch\'s runs', filters, JSON.stringify({ world: { filterType: 'text', type: 'equals', filter: 'w1' } }));
    eq('M7 a press hands the page the worlds, the default by its name too; the empty choice hands it none',
      JSON.stringify(onDefault.picked), JSON.stringify([['w1'], ['default'], []]));
    eq('M8 a blank branch in the address is no world', JSON.stringify(onBlank.urls) === JSON.stringify(DEFAULT_NOW), true);
    const defaultList = onDefault.urls.find(isList) || '';
    eq('M10 the default by its name: every request of the board carries world=default',
      `${byName.urls.length}|${byName.urls.filter((u) => !u.includes('world=default')).length}`, `${BEFORE.urls.length}|0`);
    const order = (u) => (u.split('?')[1] || '').split('&').filter((p) => p.startsWith('world=')).join('&');
    const bothList = both.urls.find(isList) || '';
    eq('M11 two worlds: every request carries both in the order picked; the run and its list name them comma-joined',
      `${both.urls.length}|${both.urls.filter((u) => order(u) !== 'world=w1&world=default').length}|${both.row && both.row.world}|`
        + new URL(bothList.split(' ').pop() || 'http://box', 'http://box').searchParams.get('filters'),
      `${BEFORE.urls.length}|0|w1,default|${JSON.stringify({ world: { filterType: 'text', type: 'equals', filter: 'w1,default' } })}`);
    eq('M9 with no world the saved list reads the runs with no world',
      new URL(defaultList.split(' ').pop() || 'http://box', 'http://box').searchParams.get('filters'), BLANK);
  }

  return { ran, failed: failedList.slice() };
}

const MUTANTS = [
  { name: 'an-undeclared-table-reads-as-a-refusal', catches: ['G7'], file: 'api.js',
    from: '        if (res.status === 404) return { ok: false, notSetUp: true };\n', to: '' },
  { name: 'every-failure-reads-as-not-set-up', catches: ['G8'], file: 'api.js',
    from: '        if (res.status === 404) return { ok: false, notSetUp: true };\n',
    to: '        if (!res.ok) return { ok: false, notSetUp: true };\n' },
  { name: 'not-set-up-says-nothing', catches: ['G7'],
    from: "    if (this.listNotSetUp) list.appendChild(el('div', 'rb-cand-line rb-cand-line--absent', CONTRAST_WORDS.notSetUp));\n    else if",
    to: '    if' },
  { name: 'the-save-reads-only-a-message', catches: ['G5', 'G6'], file: 'api.js',
    from: "    const said = refusalSentence(await res.json().catch(() => null), res.status, '');\n",
    to: "    const body = await res.json().catch(() => null);\n    const detail = body && body.detail;\n"
      + "    const said = typeof detail === 'string' ? detail : (detail && detail.message) || '';\n" },
  { name: 'a-blank-id-is-counted', catches: ['C7'], file: 'api.js',
    from: '  return Array.isArray(ids) ? ids.filter((id) => !isBlank(id)).length : null;',
    to: '  return Array.isArray(ids) ? ids.length : null;' },
  { name: 'an-object-reads-as-unknown', catches: ['C8'], file: 'api.js',
    from: '  if (isBlank(ids)) return 0;', to: '  if (Array.isArray(ids) && !ids.length) return 0;' },
  { name: 'unreadable-text-reads-as-zero', catches: ['C8'], file: 'api.js',
    from: '    try { ids = JSON.parse(ids); } catch (e) { return null; }', to: '    try { ids = JSON.parse(ids); } catch (e) { return 0; }' },
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
  { name: 'the-count-is-not-the-runs-own', catches: ['C1', 'J2', 'J3', 'J4'], file: 'api.js',
    from: '        && Number.isFinite(Number(found)) ? Number(found) : null,',
    to: '        && Number.isFinite(Number(found)) ? 1 : null,' },
  { name: 'zero-candidates-read-as-unknown', catches: ['C4', 'J5'], file: 'api.js',
    from: '        && Number.isFinite(Number(found)) ? Number(found) : null,',
    to: '        && Number(found) ? Number(found) : null,' },
  { name: 'a-run-is-always-computed', catches: ['B4', 'C6', 'J6'], file: 'api.js',
    from: '    const computedAt = isBlank(at) ? null : at;',
    to: "    const computedAt = at || 'soon';" },
  { name: 'the-list-sorts-by-a-name-the-table-lacks', catches: ['B2', 'B3'], file: 'api.js',
    from: '&order_by=updated_at&order_desc=true',
    to: '&order_by=as_of&order_desc=true' },
  { name: 'the-controls-are-ignored', catches: ['A5'],
    from: '      negative: seeds.negative || [],',
    to: '      negative: [],' },
  { name: 'the-button-is-on-without-defects', catches: ['E1', 'E2'],
    from: "(seeds ? '' : CONTRAST_WORDS.needDefects)",
    to: "''" },
  { name: 'unknown-is-drawn-as-0', catches: ['C5'],
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
  { name: 'the-board-sends-round-its-branch', catches: ['M3'], file: 'main.js',
    from: '  const fetchImpl = withWorld(options.fetchImpl || ((url, init) => globalThis.fetch(url, init)), () => worlds);',
    to: '  const fetchImpl = options.fetchImpl || ((url, init) => globalThis.fetch(url, init));' },
  { name: 'the-saved-run-forgets-its-branch', catches: ['M5'], file: 'api.js',
    from: '      const row = { ...contrastRunRow(run), ...(world ? { world } : {}) };',
    to: '      const row = { ...contrastRunRow(run) };' },
  { name: 'the-saved-list-reads-every-branch', catches: ['M6'], file: 'api.js',
    from: "const onWorld = world ? { filterType: 'text', type: 'equals', filter: world } :",
    to: "const onWorld = false ? { filterType: 'text', type: 'equals', filter: world } :" },
  { name: 'the-default-list-reads-every-branch', catches: ['M9'], file: 'api.js',
    from: ": { filterType: 'text', type: 'blank' };", to: ': {};' },
  { name: 'the-save-part-is-not-told-the-branch', catches: ['M5', 'M6'],
    from: ',\n        world: options.world });', to: ' });' },
  { name: 'the-picker-lists-no-branch', catches: ['M2'], file: 'api.js',
    from: 'worlds: body.worlds || [],', to: 'worlds: [],' },
  { name: 'the-picker-is-not-told-the-operating-world', catches: ['M2'], file: 'main.js',
    from: ',\n      operating: got && got.operating }));', to: ' }));' },
  { name: 'a-blank-branch-is-sent', catches: ['M8'], file: 'main.js',
    from: '  const worlds = worldList(options.world);', to: '  const worlds = [].concat(options.world || []);' },
  { name: 'the-board-reads-only-its-first-world', catches: ['M11'], file: 'main.js',
    from: 'globalThis.fetch(url, init)), () => worlds);', to: 'globalThis.fetch(url, init)), () => worlds.slice(0, 1));' },
  { name: 'a-pick-goes-nowhere', catches: ['M7'], file: 'main.js',
    from: '{ doc, onPickSet: options.pickWorld }', to: '{ doc, onPickSet: () => {} }' },
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
