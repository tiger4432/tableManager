// redo_banner_harness — THE BUTTONS ASSEMBLE, THEY DO NOT RUN.
//
// The re-translate moved out of the right-click menu and into the header, because selection
// happens in the grid and a menu that grows with it is what the owner objected to twice. The
// ruling that shaped this part is option A: the buttons assemble the groups and hand them over,
// and the dry-run counts and the run itself stay in admin, where the token is.
//
// 🔴 SO THE SHARPEST CHECK IN HERE IS ABOUT WHAT THE FILE DOES NOT CONTAIN. Nothing in it may
// reach `/admin/*` or hold a token; the moment it does, the boundary the ruling is made of is
// gone and no behavioural assertion would notice.
//
// The second is that the two buttons group in DIFFERENT PLACES. The ledger's groups come from
// the declaration this page already has, so they are assembled here. The chain's groups are one
// per rule and the rule list is behind the token, so this page hands over the keys and lets
// admin group them. A part that grouped both here would have to call a gated route.
//
// Every check is paired with a mutant; two controls must escape.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'redo_banner.js');
const SOURCE = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

let passed = 0;
let failed = 0;

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  console.log('ASSERTIONS 0 1');
  process.exit(2);
}

function ok(what, cond, saw) {
  if (cond) { passed++; console.log(`  ok   ${what}`); return; }
  failed++;
  console.log(`  FAIL ${what}${saw === undefined ? '' : `  -- saw ${JSON.stringify(saw)}`}`);
}

// ── a bare document, so nothing here can lean on a real DOM ─────────────────────────
function mkDoc() {
  const el = (tag) => {
    const node = {
      tagName: String(tag).toUpperCase(), children: [], className: '',
      dataset: {}, disabled: false, type: '', handlers: {},
      appendChild(child) { this.children.push(child); return child; },
      setAttribute(k, v) { this.dataset[k] = String(v); },
      addEventListener(name, fn) { this.handlers[name] = fn; },
      click() { if (this.handlers.click) this.handlers.click(); },
    };
    // 🔴 `textContent = ''` CLEARS CHILDREN in a real document, and this part relies on
    // that to redraw. A stub that only stores the string lets every render pile up, which showed
    // as four buttons where two were asserted -- an instrument fault that looks exactly like a
    // double-render defect. Modelled here so the stub cannot invent one or hide one.
    let text = '';
    Object.defineProperty(node, 'textContent', {
      get() { return text || node.children.map((k) => k.textContent).join(''); },
      set(v) { text = String(v); if (text === '') node.children.length = 0; },
      configurable: true,
    });
    return node;
  };
  return { createElement: el };
}

const walk = (node) => (node.children || [])
  .reduce((all, kid) => all.concat([kid], walk(kid)), []);
const byClass = (root, cls) => walk(root)
  .filter((n) => String(n.className || '').split(/\s+/).includes(cls));

function load(src) {
  const sandbox = { Array, String, Object, Number, Boolean, JSON };
  vm.createContext(sandbox);
  const body = src.replace(/^export /gm, '');
  vm.runInContext(`${body}\nglobalThis.__x = { RedoBanner, ledgerGroups, scopeValuesFor };`,
    sandbox);
  return sandbox.__x;
}

const X = load(SOURCE);
if (!X || !X.RedoBanner) die('redo_banner.js did not evaluate — its exports moved or renamed.');

const SOURCES = [{ relation: 'dt_log', source: 'dt_log_src',
                   scope_columns: ['lot_id', 'wafer_id'] }];
const envelope = (obj) => ({ data: Object.fromEntries(
  Object.entries(obj).map(([k, v]) => [k, { value: v }])) });
const readEnvelope = (row, col) => {
  const cell = row && row.data ? row.data[col] : undefined;
  if (cell && typeof cell === 'object' && 'value' in cell) return cell.value;
  return row ? row[col] : undefined;
};

function build(rows, opts = {}) {
  const doc = mkDoc();
  const host = doc.createElement('div');
  let handed = null;
  const part = new X.RedoBanner(host, {
    doc,
    sources: 'sources' in opts ? opts.sources : SOURCES,
    getSelection: () => rows,
    readValue: opts.readValue || readEnvelope,
    businessKey: 'businessKey' in opts ? opts.businessKey : 'lot_id',
    handOff: (p) => { handed = p; },
  });
  part.setRelation(opts.relation === undefined ? 'dt_log' : opts.relation);
  part.render();
  return { part, host, handed: () => handed };
}

const buttons = (host) => byClass(host, 'redo-banner__btn');
const groupsShown = (host) => byClass(host, 'redo-panel__group').map((n) => n.textContent);
const note = (host) => (byClass(host, 'redo-panel__note')[0] || {}).textContent;
const press = (host, which) => buttons(host).find((b) => b.dataset.redo === which).click();

console.log('\n── A. THE BOUNDARY ─────────────────────────────────────────────────');
{
  // 🔴 The ruling is a property of the FILE, and no rendered output can show it.
  const stripped = SOURCE.split('\n')
    .filter((l) => !l.trim().startsWith('//') && !l.trim().startsWith('*')
      && !l.trim().startsWith('/*'))
    .join('\n');
  ok('A1 the part never names an admin route', !stripped.includes('/admin/'), stripped.length);
  ok('A2 ... and never fetches at all', !/\bfetch\s*\(/.test(stripped));
  ok('A3 ... and holds no token', !/token/i.test(stripped));
}

console.log('\n── B. THE BUTTONS ──────────────────────────────────────────────────');
{
  const empty = build([]);
  ok('B1 with nothing selected both buttons are dead',
    buttons(empty.host).length === 2 && buttons(empty.host).every((b) => b.disabled === true),
    buttons(empty.host).map((b) => b.disabled));
  const chosen = build([envelope({ lot_id: 'L1', wafer_id: 'W1' })]);
  ok('B2 selecting a row brings both to life',
    buttons(chosen.host).every((b) => b.disabled === false),
    buttons(chosen.host).map((b) => b.disabled));
  // 🔴 THE DISCRIMINATING PAIR: on a table the declaration does not name, "nothing selected"
  //    and "not a ledger source" must not paint the same. The ledger button is ABSENT there.
  const notSource = build([envelope({ lot_id: 'L1' })], { relation: 'not_declared' });
  ok('B3 on a table that is not a ledger source the ledger button is absent, not merely dead',
    buttons(notSource.host).map((b) => b.dataset.redo).join(',') === 'chain',
    buttons(notSource.host).map((b) => b.dataset.redo));
}

console.log('\n── C. THE LEDGER GROUPS, ASSEMBLED HERE ────────────────────────────');
{
  const rows = [envelope({ lot_id: 'L1', wafer_id: 'W1' }),
                envelope({ lot_id: 'L1', wafer_id: 'W2' }),
                envelope({ lot_id: 'L2', wafer_id: 'W3' })];
  const b = build(rows);
  press(b.host, 'ledger');
  const lines = groupsShown(b.host);
  ok('C1 one line per declared scope column', lines.length === 2, lines);
  ok('C2 the group count is the DISTINCT values, not the row count',
    lines[0].includes('2 groups from 3 rows'), lines[0]);
  ok('C3 a second column groups by its own values',
    lines[1].includes('3 groups from 3 rows'), lines[1]);
  b.host.children.slice(1).forEach(() => {});
  byClass(b.host, 'redo-panel__go')[0].click();
  const handed = b.handed();
  ok('C4 handing over sends one group per column, with the declared parameter names',
    handed && handed.op === 'ledger_rescope' && handed.groups.length === 2
    && handed.groups[0].params.scope_column === 'lot_id'
    && handed.groups[0].params.source === 'dt_log_src', handed);
  ok('C5 ... and each group carries its own values, joined the way the route reads them',
    handed.groups[0].params.scope_values === 'L1,L2', handed.groups[0].params);

  // A column with no value in the selection cannot be a group -- it would hand over an empty
  // scope and admin would take the 400. It is named instead of vanishing.
  const holed = build([envelope({ lot_id: 'L1' })]);
  press(holed.host, 'ledger');
  const hl = groupsShown(holed.host);
  ok('C6 a column with nothing in it is not handed over',
    hl.filter((l) => l.startsWith('wafer_id')).every((l) => l.includes('no value')), hl);
  byClass(holed.host, 'redo-panel__go')[0].click();
  ok('C7 ... and the payload holds only the column that has values',
    holed.handed().groups.length === 1
    && holed.handed().groups[0].label === 'lot_id', holed.handed());

  // THE DISCRIMINATING SELECTION: every fixture above has a value in every row, so the size
  // of the selection and the number of rows the groups actually cover are THE SAME NUMBER and
  // no assertion on them can tell the two apart. Here they differ, and the line has to name
  // the second one -- otherwise it reads "1 group from 3 rows, 2 without a value", which counts
  // the same rows twice and is what the owner asked about.
  const partial = build([envelope({ lot_id: 'L1', wafer_id: 'W1' }),
                         envelope({ lot_id: 'L1' }),
                         envelope({ lot_id: 'L2' })]);
  press(partial.host, 'ledger');
  const pl = groupsShown(partial.host);
  ok('C8 the row count is the rows that CARRY the value, not the size of the selection',
    pl[1] === 'wafer_id \u2014 1 group from 1 row \u00b7 2 without a value', pl);
  ok('C9 ... and a column every row does carry still counts them all',
    pl[0] === 'lot_id \u2014 2 groups from 3 rows', pl);
}

console.log('\n── D. THE CHAIN KEYS, GROUPED ELSEWHERE ────────────────────────────');
{
  const rows = [envelope({ lot_id: 'L1' }), envelope({ lot_id: 'L1' }), envelope({ lot_id: 'L2' })];
  const b = build(rows);
  press(b.host, 'chain');
  byClass(b.host, 'redo-panel__go')[0].click();
  const handed = b.handed();
  ok('D1 the chain hand-off carries the KEYS, de-duplicated',
    handed.op === 'chain_replay' && handed.businessKeys.join(',') === 'L1,L2', handed);
  // 🔴 THE ONE THIS PART EXISTS TO GET RIGHT. Grouping by rule here would mean calling a gated
  //    route from the grid page, so the payload must NOT pretend to know the rules.
  ok('D2 ... and no rule grouping is invented here, because the rules are behind the token',
    handed.groups === undefined, handed);
  const noKey = build(rows, { businessKey: null });
  press(noKey.host, 'chain');
  ok('D3 a table with no business key says so rather than handing over nothing',
    (note(noKey.host) || '').includes('business key'), note(noKey.host));
}

console.log('\n── E. THE ENVELOPE ─────────────────────────────────────────────────');
{
  // Live measurement, 2026-08-31: this grid holds rows as `{data:{col:{value}}}`. Reading them
  // plainly returns "no values at all" and the screen then says a false thing.
  const rows = [envelope({ lot_id: 'L1' })];
  const plain = build(rows, { readValue: (row, col) => (row ? row[col] : undefined) });
  press(plain.host, 'ledger');
  ok('E1 without the injected reader the enveloped rows read as empty',
    (note(plain.host) || '').includes('no scope column has a value'), note(plain.host));
  const wired = build(rows);
  press(wired.host, 'ledger');
  ok('E2 with the reader the values are found where the grid keeps them',
    groupsShown(wired.host)[0].includes('1 group from 1 row'), groupsShown(wired.host));
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
const swap = (from, to) => (src) => {
  if (!src.includes(from)) die(`mutation anchor stopped matching: ${JSON.stringify(from)}. `
    + 'A harness that goes quiet because it lost the code is worse than no harness.');
  return src.replace(from, to);
};

const DEFECTS = [
  ['M1 the buttons are live with nothing selected',
    swap('btn.disabled = !enabled;', 'btn.disabled = false;')],
  ['M2 the ledger button is drawn on a table that is not a source',
    swap('if (row) bar.appendChild', 'bar.appendChild')],
  ['M3 the group count counts rows instead of distinct values',
    swap('      const n = g.values.length;', '      const n = g.rows;')],
  ['M4 a column with no values is handed over as an empty scope',
    swap('if (!values.length) { dropped.push(column); continue; }',
      'if (!values.length) { groups.push({ key: column, values, missing, '
      + 'rows: (rows || []).length }); continue; }')],
  ['M5 the chain hand-off invents a rule grouping the page cannot know',
    swap('        businessKeys: values,',
      '        businessKeys: values,\n        groups: values.map((v) => ({ label: v })),')],
  ['M6 the scope values are joined with something the route does not read',
    swap("scope_values: g.values.join(',')", "scope_values: g.values.join(' ')")],
  ['M7 a repeated value becomes its own group',
    swap('if (!seen.includes(value)) seen.push(value);', 'seen.push(value);')],
  ['M8 the line counts the whole selection instead of the rows that carry the value',
    swap('rows: (rows || []).length - missing', 'rows: (rows || []).length')],
];

const CONTROLS = [
  ['a local rename', (src) => src.replace(/\bseen\b/g, 'found')],
  ['comments stripped', (src) => src.split('\n')
    .filter((l) => !l.trim().startsWith('//') && !l.trim().startsWith('*')
      && !l.trim().startsWith('/*'))
    .join('\n')],
];

function score(list, mustCatch, heading) {
  console.log(`\n── ${heading} ─────────────────────────────`);
  let hit = 0;
  for (const [name, mutate] of list) {
    let bad = false;
    try {
      const M = load(mutate(SOURCE));
      const rows = [envelope({ lot_id: 'L1', wafer_id: 'W1' }),
                    envelope({ lot_id: 'L1', wafer_id: 'W2' }),
                    envelope({ lot_id: 'L2', wafer_id: 'W3' })];
      const doc = mkDoc();
      const host = doc.createElement('div');
      let handed = null;
      const part = new M.RedoBanner(host, {
        doc, sources: SOURCES, getSelection: () => rows, readValue: readEnvelope,
        businessKey: 'lot_id', handOff: (p) => { handed = p; },
      });
      part.setRelation('dt_log');
      part.render();
      // the checks that matter, read through guards so a crash cannot score as a catch
      const empty = new M.RedoBanner(mkDoc().createElement('div'), {
        doc: mkDoc(), sources: SOURCES, getSelection: () => [], readValue: readEnvelope });
      empty.host = mkDoc().createElement('div');
      empty.doc = doc;
      empty.setRelation('dt_log');
      empty.render();
      const notSource = new M.RedoBanner(doc.createElement('div'), {
        doc, sources: SOURCES, getSelection: () => rows, readValue: readEnvelope });
      notSource.setRelation('not_declared');
      notSource.render();
      const holed = new M.RedoBanner(doc.createElement('div'), {
        doc, sources: SOURCES, getSelection: () => [envelope({ lot_id: 'L1' })],
        readValue: readEnvelope, handOff: () => {} });
      holed.setRelation('dt_log');
      holed.render();
      holed.open = 'ledger';
      holed.render();
      // A selection where "how many rows I picked" and "how many rows this group covers" are
      // DIFFERENT numbers. Every other fixture here has both values in every row, which makes
      // the two indistinguishable and lets a count off the selection size score as correct.
      const partial = new M.RedoBanner(doc.createElement('div'), {
        doc, sources: SOURCES, readValue: readEnvelope, handOff: () => {},
        getSelection: () => [envelope({ lot_id: 'L1', wafer_id: 'W1' }),
                             envelope({ lot_id: 'L1' }), envelope({ lot_id: 'L2' })] });
      partial.setRelation('dt_log');
      partial.open = 'ledger';
      partial.render();
      part.open = 'ledger';
      part.render();
      const lines = groupsShown(host);
      const go = byClass(host, 'redo-panel__go')[0];
      if (go) go.click();
      const ledgerHanded = handed;
      part.open = 'chain';
      part.render();
      const go2 = byClass(host, 'redo-panel__go')[0];
      if (go2) go2.click();

      bad = buttons(empty.host).some((b) => b.disabled !== true)
        || buttons(notSource.host).map((b) => b.dataset.redo).join(',') !== 'chain'
        || !(lines[0] || '').includes('2 groups from 3 rows')
        || !ledgerHanded || ledgerHanded.groups.length !== 2
        || ledgerHanded.groups[0].params.scope_values !== 'L1,L2'
        || byClass(holed.host, 'redo-panel__group')
          .filter((n) => n.textContent.startsWith('wafer_id'))
          .some((n) => !n.textContent.includes('no value'))
        || !handed || handed.groups !== undefined
        || handed.businessKeys.join(',') !== 'L1,L2'
        || groupsShown(partial.host)[1]
           !== 'wafer_id \u2014 1 group from 1 row \u00b7 2 without a value';
    } catch (e) {
      bad = true;
    }
    if (bad === mustCatch) { hit++; console.log(`  ${mustCatch ? 'caught ' : 'escaped'} ${name}`); }
    else { failed++; console.log(`  ${mustCatch ? 'ESCAPED' : 'CAUGHT '} ${name}  <- wrong`); }
  }
  return hit;
}

const caught = score(DEFECTS, true, 'defect mutants (each must be CAUGHT)');
const escaped = score(CONTROLS, false, 'control mutants (each must ESCAPE)');

console.log(`\n${passed} passed, ${failed} failed; ${caught}/${DEFECTS.length} defects caught; `
  + `${escaped}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${passed} ${failed}`);
if (failed) process.exit(1);
