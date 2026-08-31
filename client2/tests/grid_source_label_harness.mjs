/**
 * grid_source_label — 「이 표가 원장 소스인가」를 세 문장으로 말하는가
 *
 * WHAT THIS SCORES:
 *   A  the three absences are THREE, produced separately: source / not a source / could not read
 *   B  the label reads the DECLARATION and invents nothing -- source name and emits come from it
 *   C  no subject is not an absence: with no table chosen the label makes no claim at all
 *   D  assembly-style: two instances on one page, different tables, no interference
 *
 * 🔴 THE THREE ARE MADE SEPARATELY, ON PURPOSE (brief G2). Scoring only one of them cannot see
 *    the collapse this part exists to prevent -- 「아님」 and 「못 읽음」 look identical to a test
 *    that never builds both. The refusal is made by making the loader fail, as the brief asks.
 *
 * 🔴 EVERY ASSERTION IS WOKEN BY A MUTANT, and a mutation whose anchor has rotted STOPS the run
 *    instead of reading as a pass.
 *
 * 🔴 THE FILE IS READ WITH ITS LINE ENDINGS NORMALISED. A worktree checked out CRLF makes every
 *    multi-line anchor unmatchable, and the harness then reports 「anchor gone」 for code that is
 *    byte-identical to main -- measured on this repo 2026-08-31.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const dataUrl = (src) => `data:text/javascript;base64,${Buffer.from(src, 'utf8').toString('base64')}`;

/** 라이브 `/api/ledger/declaration` 의 다듬은 사본 (2026-08-31, :8080 · sources 15행 중 둘). */
const DECLARATION = {
  ok: true,
  sources: [
    { source: 'bonded_from',
      relation: 'bonding_die_from_core',
      emits: ['bonded_from@1', 'in_container@1'],
      scope_columns: ['base_id', 'bx', 'by', 'core_wafer', 'cx', 'cy', 'event_time'] },
    { source: 'die_inspection',
      relation: 'inspection_run',
      emits: ['inspected@1'],
      scope_columns: ['base_wafer_id', 'base_x', 'base_y', 'observed_at', 'run_uid'] },
  ],
};

async function loadModule(mutate = null) {
  const file = path.join(SRC, 'grid_source_label.js');
  const text = readFileSync(file, 'utf8')
    .replace(new RegExp(String.fromCharCode(13, 10), 'g'), String.fromCharCode(10));
  const out = mutate ? mutate(text) : text;
  if (mutate && out === text) throw new Error('mutation anchor is GONE: grid_source_label.js');
  return import(dataUrl(out));
}

// ── the DOM stub (same shape the rnd_board harnesses drive) ─────────────────────
function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '', style: {}, children: [], attrs: Object.create(null), _text: '',
    appendChild(c) { this.children.push(c); return c; },
    append(...cs) { for (const c of cs) this.appendChild(c); },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  return node;
}
const makeDoc = () => { const doc = { createElement: (t) => makeNode(doc, t) }; return doc; };
const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const stateOf = (host) => {
  const hit = walk(host).find((n) => n.getAttribute && n.getAttribute('data-source-state'));
  return hit ? hit.getAttribute('data-source-state') : null;
};
// 🔴 SCOPED, BECAUSE THE WHOLE TEXT MAKES THE CLAIM VACUOUS. The emits line carries the source
//    name too (`bonded_from@1`), so 「the name is served」 measured on `host.textContent` stays
//    green even when the name element prints the relation instead -- measured, mutant M6.
const byClass = (host, cls) => walk(host)
  .filter((n) => String(n.className || '').split(/\s+/).includes(cls));
const flush = () => new Promise((r) => setTimeout(r, 0));

async function suite(mod) {
  const { GridSourceLabel } = mod;
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

  const build = async (loader, relation) => {
    const doc = makeDoc();
    const host = doc.createElement('div');
    const part = new GridSourceLabel(host, { doc, loadDeclaration: loader });
    part.mount();
    await flush(); await flush();
    if (relation !== undefined) part.setRelation(relation);
    return { part, host };
  };

  // ── A. THE THREE ABSENCES, EACH MADE ON ITS OWN ──────────────────────────────
  {
    const served = async () => DECLARATION;
    const a = await build(served, 'inspection_run');
    eq('A1 a declared relation is named a source', stateOf(a.host), 'source');

    // 🔴 SECOND: read fine, simply not in the list. This is a FACT and gets its own sentence.
    const b = await build(served, 'some_table_nobody_declared');
    eq('A2 an undeclared relation says it does not enter the ledger', stateOf(b.host), 'not_source');

    // 🔴 THIRD: the route refused. Made by making the loader fail, as the brief asks.
    const c = await build(async () => ({ ok: false, message: '선언을 읽지 못했습니다 (503)' }),
      'inspection_run');
    eq('A3 a refused declaration is its OWN state, not 「not a source」', stateOf(c.host), 'unknown');

    // The three must not merely differ by a flag -- the reader has to see three sentences.
    const texts = [a.host.textContent, b.host.textContent, c.host.textContent];
    ok('A4 the three read as three different sentences',
      new Set(texts).size === 3, texts.join(' | '));
    // A thrown loader is the same absence as a refusing one, and must not read as 「not a source」.
    const d = await build(async () => { throw new Error('boom'); }, 'inspection_run');
    eq('A5 a loader that throws is also 「could not read」', stateOf(d.host), 'unknown');
  }

  // ── B. THE WORDS COME FROM THE DECLARATION ───────────────────────────────────
  {
    const { host } = await build(async () => DECLARATION, 'bonding_die_from_core');
    const nameEl = byClass(host, 'grid-source-label__name')[0];
    ok('B1 the source name is the declarations own, read where the name is drawn',
      Boolean(nameEl) && nameEl.textContent.includes('bonded_from')
      && !nameEl.textContent.includes('bonding_die_from_core'),
      String(nameEl && nameEl.textContent));
    // 🔴 `emits` GOES THROUGH WHOLE. Filtering here would make the screen say LESS than the
    //    declaration, and a predicate added tomorrow would vanish without anyone noticing.
    ok('B2 every emitted predicate is shown, unfiltered',
      host.textContent.includes('bonded_from@1') && host.textContent.includes('in_container@1'),
      host.textContent);
  }

  // ── C. NO SUBJECT IS NOT AN ABSENCE ──────────────────────────────────────────
  {
    const { host } = await build(async () => DECLARATION, undefined);
    eq('C1 with no table chosen the label claims nothing', stateOf(host), null);
    ok('C2 ... and draws no sentence either', host.textContent === '', JSON.stringify(host.textContent));
  }

  // ── D. TWO INSTANCES, ONE PAGE, NO INTERFERENCE (UI standing rule) ───────────
  {
    const one = await build(async () => DECLARATION, 'inspection_run');
    const two = await build(async () => DECLARATION, 'some_table_nobody_declared');
    eq('D1 two instances keep their own answers',
      [stateOf(one.host), stateOf(two.host)], ['source', 'not_source']);
    one.part.setRelation('bonding_die_from_core');
    // 🔴 THE SECOND MUST REDRAW, OR THIS PROVES NOTHING. Shared state only shows on the next
    //    render; comparing stale DOM lets a module-level variable through -- measured, mutant M5.
    two.part.render();
    eq('D2 ... and moving one does not move the other',
      [stateOf(one.host), stateOf(two.host)], ['source', 'not_source']);
    ok('D3 ... and the second still names its own relation, not the firsts',
      !two.host.textContent.includes('bonded_from'), two.host.textContent);
  }

  return { ran, failures };
}

const MUTANTS = [
  // 🔴 THE COLLAPSE THIS PART EXISTS TO PREVENT: a refusal drawn as 「not a source」.
  { id: 'M1', what: 'a refused declaration is drawn as 「not a source」',
    catches: 'A3',
    mutate: (s) => s.replace(
      "      this.sources = null;\n      this.loadState = 'refused';",
      "      this.sources = [];\n      this.loadState = 'ready';") },
  // A thrown loader taking the same road as a served one is the same collapse, one layer up.
  { id: 'M2', what: 'a loader that throws is treated as a served empty declaration',
    catches: 'A5',
    mutate: (s) => s.replace('      got = null;\n', '      got = { ok: true, sources: [] };\n') },
  // 🔴 「아직 안 골랐다」 folded into an absence -- the fourth state this file keeps out.
  { id: 'M3', what: 'no table chosen is drawn as 「not a source」',
    catches: 'C1',
    mutate: (s) => s.replace('    if (!this.relation) {', '    if (false) {') },
  // The screen saying LESS than the declaration.
  { id: 'M4', what: 'emits is filtered, so a predicate the declaration names disappears',
    catches: 'B2',
    mutate: (s) => s.replace(
      '    const emits = Array.isArray(row.emits) ? row.emits : [];',
      '    const emits = (Array.isArray(row.emits) ? row.emits : []).slice(0, 1);') },
  // Module-level state is the assembly-style failure: two instances stop being two.
  { id: 'M5', what: 'the chosen relation becomes shared, so two instances collide',
    catches: 'D2',
    mutate: (s) => s.replace(
      'export class GridSourceLabel {',
      'let SHARED_RELATION = null;\nexport class GridSourceLabel {')
      .replace('    this.relation = next;', '    SHARED_RELATION = next; this.relation = SHARED_RELATION;')
      .replace('    const row = rowFor(this.sources, this.relation);',
        '    const row = rowFor(this.sources, SHARED_RELATION);') },
  // A source whose name is invented rather than served.
  { id: 'M6', what: 'the label prints the relation instead of the declared source name',
    catches: 'B1',
    mutate: (s) => s.replace(
      '    name.textContent = `ledger source — ${row.source}`;',
      '    name.textContent = `ledger source — ${this.relation}`;') },
];

const result = await suite(await loadModule());
console.log('-- grid source label -----------------------------------------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

console.log('');
console.log('-- defect mutants (each must be CAUGHT by its named line) -----------');
let escaped = 0;
for (const m of MUTANTS) {
  let mutated;
  try {
    mutated = await loadModule(m.mutate);
  } catch (err) {
    console.log(`  INERT   ${m.id} ${m.what}  -- ${err.message}`);
    escaped += 1;
    continue;
  }
  let out;
  try {
    out = await suite(mutated);
  } catch (err) {
    console.log(`  INERT   ${m.id} ${m.what}  -- ${err.message}`);
    escaped += 1;
    continue;
  }
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
