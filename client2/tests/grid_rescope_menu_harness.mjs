/**
 * grid_rescope_menu + rescope_handoff — 「고르는 곳은 그리드, 실행하는 곳은 어드민」
 *
 * WHAT THIS SCORES:
 *   A  G1 — an undeclared table offers NO row at all (not a disabled one)
 *   B  G3 — the only columns on screen are the ones the declaration served
 *   C  the four ways the menu can be empty stay FOUR, each with its own words
 *   D  the handoff is written once and eaten once, and carries the declared param names
 *   E  the grid neither runs nor previews — no token, no /admin call, no write
 *
 * 🔴 THE HANDOFF IS EATEN, NOT READ. A payload left behind fills a scope on the NEXT visit that
 *    nobody picked this time, and the operator reads it as their own choice. That is the write
 *    side of the same defect this screen keeps catching on the read side.
 *
 * 🔴 THE FILES ARE READ WITH LINE ENDINGS NORMALISED — a CRLF worktree makes multi-line anchors
 *    unmatchable and the harness then blames code that is byte-identical to main.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const dataUrl = (src) => `data:text/javascript;base64,${Buffer.from(src, 'utf8').toString('base64')}`;
const read = (file) => readFileSync(path.join(SRC, file), 'utf8').replace(/\r\n/g, '\n')
  .replace(new RegExp(String.fromCharCode(13, 10), 'g'), String.fromCharCode(10));

/** 라이브 `/api/ledger/declaration` 의 `sources` 에서 둘 (2026-08-31, :8080). */
const SOURCES = [
  { source: 'die_inspection', relation: 'inspection_run', emits: ['inspected@1'],
    scope_columns: ['base_wafer_id', 'base_x', 'base_y', 'observed_at', 'run_uid'] },
  { source: 'bonded_from', relation: 'bonding_die_from_core',
    emits: ['bonded_from@1', 'in_container@1'],
    scope_columns: ['base_id', 'bx', 'by'] },
];

async function loadModules(mutate = {}) {
  const one = (file) => {
    const text = read(file);
    const fn = mutate[file];
    const out = fn ? fn(text) : text;
    if (fn && out === text) throw new Error(`mutation anchor is GONE: ${file}`);
    return out;
  };
  const menu = await import(dataUrl(one('grid_rescope_menu.js')));
  const handoff = await import(dataUrl(one('rescope_handoff.js')));
  return { menu, handoff };
}

function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '', style: {}, children: [], attrs: Object.create(null),
    listeners: Object.create(null), _text: '',
    appendChild(c) { this.children.push(c); return c; },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); },
    click() { for (const fn of this.listeners.click || []) fn({}); },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  return node;
}
const makeDoc = () => { const doc = { createElement: (t) => makeNode(doc, t) }; return doc; };
const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const items = (host) => walk(host).filter((n) => n.getAttribute && n.getAttribute('data-rescope-column'));
const live = (host) => items(host).filter((n) => !String(n.className).includes('is-empty'));
const makeStore = () => ({
  _v: Object.create(null),
  getItem(k) { return Object.prototype.hasOwnProperty.call(this._v, k) ? this._v[k] : null; },
  setItem(k, v) { this._v[k] = String(v); },
  removeItem(k) { delete this._v[k]; },
});

async function suite(mods) {
  const { GridRescopeMenu } = mods.menu;
  const { putRescopeHandoff, takeRescopeHandoff } = mods.handoff;
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };
  const ok = (name, cond, detail) => {
    ran.push(name);
    if (!cond) failures.push(detail ? `${name}: ${detail}` : name);
  };

  const build = (relation, rows, handOff, readValue) => {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const part = new GridRescopeMenu(host, {
      doc, sources: SOURCES, getSelection: () => rows || [], handOff, readValue,
    });
    part.setRelation(relation);
    return { part, host };
  };

  // 🔴 판별식이 되는 픽스처 (2026-08-31 라이브 실측). 이 그리드의 행은 «봉투»입니다.
  //    평범한 객체로만 재면 `row[col]` 과 주입된 읽기가 «같은 답»을 내서, 어느 쪽이 도는지
  //    알 수 없습니다 -- 그리고 실제 화면은 그때 여섯 컬럼 «전부»를 「값 없음」으로 그렸습니다.
  const envelope = (fields) => ({ row_id: 'r', data: Object.fromEntries(
    Object.entries(fields).map(([k, v]) => [k, { value: v, is_overwrite: false }])) });
  const readEnvelope = (row, column) => {
    const cell = row && row.data ? row.data[column] : undefined;
    if (cell && typeof cell === 'object' && 'value' in cell) return cell.value;
    return row ? row[column] : undefined;
  };

  // ── A. G1 — AN UNDECLARED TABLE OFFERS NOTHING ───────────────────────────────
  {
    const { host } = build('some_table_nobody_declared', [{ base_wafer_id: 'W-1' }]);
    eq('A1 an undeclared table offers no rescope row at all', items(host).length, 0);
    // 🔴 NOT a disabled row either: a row you can see but not use reads as 「it is broken」.
    ok('A2 ... and draws nothing at all, not a dead row', host.textContent === '',
      JSON.stringify(host.textContent));
  }

  // ── B. G3 — ONLY THE SERVED COLUMNS ARE ON SCREEN ────────────────────────────
  {
    const rows = [{ base_id: 'A', bx: 1, by: 2, secret_column: 'x' },
      { base_id: 'B', bx: 1, by: 3, secret_column: 'y' }];
    const { host } = build('bonding_die_from_core', rows);
    eq('B1 the columns offered are exactly the declared scope_columns',
      items(host).map((n) => n.getAttribute('data-rescope-column')), ['base_id', 'bx', 'by']);
    // 🔴 A column the server would refuse is not merely disabled -- it is absent.
    ok('B2 a column the declaration never served is nowhere on screen',
      !host.textContent.includes('secret_column'), host.textContent);
  }

  // ── C. THE EMPTY CASES STAY APART ────────────────────────────────────────────
  {
    const none = build('inspection_run', []);
    ok('C1 no selection says so, rather than offering columns',
      items(none.host).length === 0
        && none.host.textContent.includes('select rows to re-translate'),
      none.host.textContent);
    // 🔴 A column the rows carry no value for is DISABLED, not removed -- removing it would
    //    make it indistinguishable from a column the server refuses (B2).
    const rows = [{ base_id: 'A' }, { base_id: 'B' }];
    const some = build('bonding_die_from_core', rows);
    eq('C2 a column with no values in the selection stays visible but dead',
      items(some.host).length - live(some.host).length, 2);
    ok('C3 ... and says why, naming the column',
      some.host.textContent.includes('bx — no value in the selected rows'), some.host.textContent);
    // Rows that carry no value are COUNTED, not dropped in silence.
    const mixed = build('bonding_die_from_core', [{ base_id: 'A' }, { base_id: '' }, { base_id: 'B' }]);
    ok('C4 rows missing the value are counted, not dropped silently',
      live(mixed.host)[0].textContent.includes('1 without a value'), live(mixed.host)[0].textContent);
  }

  // ── C-bis. THE ROW SHAPE THIS GRID ACTUALLY USES ─────────────────────────────
  {
    const rows = [envelope({ base_id: 'A', bx: 1 }), envelope({ base_id: 'B', bx: 1 })];
    const plain = build('bonding_die_from_core', rows);
    // 주입 없이 읽으면 «전부 없음» — 라이브에서 실제로 그렇게 나왔습니다.
    eq('C5 without the injected reader the enveloped rows read as empty', live(plain.host).length, 0);
    const wired = build('bonding_die_from_core', rows, null, readEnvelope);
    eq('C6 with the reader the values are found where the grid keeps them',
      live(wired.host).map((n) => n.getAttribute('data-rescope-column')), ['base_id', 'bx']);
    ok('C7 ... and the counts are the values, not the rows',
      live(wired.host)[1].textContent.includes('bx (1)'), live(wired.host)[1].textContent);
  }

  // ── D. THE HANDOFF: DECLARED NAMES, WRITTEN ONCE, EATEN ONCE ─────────────────
  {
    let sent = null;
    const rows = [{ base_wafer_id: 'W-1' }, { base_wafer_id: 'W-2' }, { base_wafer_id: 'W-1' }];
    const { host } = build('inspection_run', rows, (p) => { sent = p; });
    live(host)[0].click();
    eq('D1 the handoff names the operation and the declared params',
      sent, { op: 'ledger_rescope',
        params: { source: 'die_inspection', scope_column: 'base_wafer_id', scope_values: 'W-1,W-2' } });

    const store = makeStore();
    ok('D2 the payload is written', putRescopeHandoff(sent, store) === true);
    const first = takeRescopeHandoff(store);
    eq('D3 ... and comes back whole',
      [first.op, first.params.scope_column, first.params.scope_values],
      ['ledger_rescope', 'base_wafer_id', 'W-1,W-2']);
    // 🔴 THE POINT: a second read is EMPTY. Otherwise the next visit prefills a scope nobody
    //    picked, and the operator reads it as their own.
    eq('D4 a second read is empty -- the handoff is eaten, not left behind',
      takeRescopeHandoff(store), null);
    // A store that refuses must not look like a success.
    const dead = { getItem() { throw new Error('blocked'); },
      setItem() { throw new Error('blocked'); }, removeItem() {} };
    eq('D5 a blocked store reports failure rather than pretending', putRescopeHandoff(sent, dead), false);
    eq('D6 ... and reading a blocked store is null, not a crash', takeRescopeHandoff(dead), null);
  }

  // ── E. THE GRID DOES NOT RUN ANYTHING ────────────────────────────────────────
  {
    ran.push('E1 the menu never names an admin route or a token');
    // 🔴 COMMENTS ARE STRIPPED FIRST. The file SAYS 「no admin route here」 in prose, and
    //    grepping the raw text makes that sentence fail its own assertion -- the claim has to
    //    be about what RUNS. (Measured 2026-08-31: this line went red on its own comment.)
    const NL = String.fromCharCode(10);
    const text = read('grid_rescope_menu.js')
      .split(NL)
      .filter((line) => !line.trim().startsWith('//') && !line.trim().startsWith('*')
        && !line.trim().startsWith('/*'))
      .join(NL);
    const offending = ['/admin/', 'adminFetch', 'X-Admin', 'localStorage', 'fetch('];
    const hits = offending.filter((word) => text.includes(word));
    if (hits.length) failures.push(`E1 the menu never names an admin route or a token: found ${hits.join(', ')}`);
  }

  return { ran, failures };
}

const MUTANTS = [
  // 🔴 THE MUTANT MUST FAIL A NAMED LINE, NOT CRASH. Removing the early return throws on
  //    `row.scope_columns`, and a crash reads as INERT -- which is the honest word for
  //    「nothing was measured」. So the defect is injected where it actually happens: the
  //    lookup falls back to SOME source instead of answering 「this table is not one」.
  { id: 'M1', what: 'an undeclared table falls back to some other source and gets the menu',
    catches: 'A1',
    mutate: { 'grid_rescope_menu.js': (s) => s.replace(
      "    return this.sources.find((row) => row && row.relation === this.relation) || null;",
      "    return this.sources.find((row) => row && row.relation === this.relation) || this.sources[0] || null;") } },
  { id: 'M2', what: 'columns come from the selected row instead of the declaration',
    catches: 'B1',
    mutate: { 'grid_rescope_menu.js': (s) => s.replace(
      '    const columns = Array.isArray(row.scope_columns) ? row.scope_columns : [];',
      '    const columns = Object.keys(rows[0] || {});') } },
  { id: 'M3', what: 'a column with no values is removed, so it looks like one the server refuses',
    catches: 'C2',
    mutate: { 'grid_rescope_menu.js': (s) => s.replace(
      "        item.className = 'rescope-menu__item is-empty';",
      '        continue;') } },
  { id: 'M4', what: 'rows missing the value are dropped without saying how many',
    catches: 'C4',
    mutate: { 'grid_rescope_menu.js': (s) => s.replace(
      "      const skipped = missing ? ` · ${missing} without a value` : '';",
      "      const skipped = '';") } },
  { id: 'M5', what: 'the handoff invents a param name the operation never declared',
    catches: 'D1',
    mutate: { 'grid_rescope_menu.js': (s) => s.replace(
      '            scope_column: column,', '            column: column,') } },
  // 🔴 THE ONE THIS SEAM EXISTS FOR.
  { id: 'M6', what: 'the handoff is read but not eaten, so the next visit prefills a stale scope',
    catches: 'D4',
    mutate: { 'rescope_handoff.js': (s) => s.replace(
      '    target.removeItem(KEY);', '    // left behind') } },
  { id: 'M7', what: 'a blocked store reports success, so the scope vanishes silently',
    catches: 'D5',
    mutate: { 'rescope_handoff.js': (s) => s.replace(
      '  } catch (err) {\n    return false;\n  }', '  } catch (err) {\n    return true;\n  }') } },
];

const result = await suite(await loadModules());
console.log('-- grid rescope menu + handoff -------------------------------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

console.log('');
console.log('-- defect mutants (each must be CAUGHT by its named line) -----------');
let escaped = 0;
for (const m of MUTANTS) {
  let mutated;
  try { mutated = await loadModules(m.mutate); }
  catch (err) { console.log(`  INERT   ${m.id} ${m.what}  -- ${err.message}`); escaped += 1; continue; }
  let out;
  try { out = await suite(mutated); }
  catch (err) { console.log(`  INERT   ${m.id} ${m.what}  -- ${err.message}`); escaped += 1; continue; }
  const hit = out.failures.find((f) => f.startsWith(m.catches));
  if (hit) console.log(`  caught  ${m.id} ${m.what}  (${m.catches})`);
  else { console.log(`  ESCAPED ${m.id} ${m.what}  -- ${m.catches} stayed green`); escaped += 1; }
}

const total = result.ran.length + MUTANTS.length;
const bad = result.failures.length + escaped;
console.log('');
console.log(`${result.ran.length - result.failures.length} passed, ${result.failures.length} failed; `
  + `${MUTANTS.length - escaped}/${MUTANTS.length} defects caught, ${escaped} escaped.`);
console.log(`ASSERTIONS ${total} ${bad}`);
