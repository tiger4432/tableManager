// Harness — the case-control console never prints a number without its denominator, keeps the
// three-way population three, and is GENERAL over finding kinds rather than a void screen with
// a parameter.
// Run: node client2/tests/case_control_harness.mjs
//
// WHAT IT DEFENDS. The product owner's acceptance criterion for this console is one sentence —
// "no number ships without its denominator, its evidence, and its speaker badge" — and every
// way of breaking it is invisible to an exit code and to a glance at the page:
//
//   Q1  🔴 NO RATE WITHOUT ITS DENOMINATOR, AND THE FRACTION IS ON SCREEN. "83%" over six
//       cases and "83%" over six hundred are different claims. `rateReading` cannot return a
//       percentage without a denominator — it returns a REFUSAL carrying the reason — and
//       `renderRate` is the only path from a count to a "%" in the view.
//
//   Q2  🔴 THE POPULATION IS THREE COUNTS AND NEVER-SCANNED IS OUT OF THE DENOMINATOR. The
//       fixture is built so the two rules disagree: found 6 + clean 244 = 250, unscanned 1120.
//       Folding unscanned into clean prints 6/1370 = 0.44% where the truth is 6/250 = 2.4% —
//       a coverage gap rendered as a quality improvement, one order of magnitude wrong, and
//       both numbers look perfectly plausible on screen.
//
//   Q3  🔴 VOID IS A DEFAULT VALUE, NEVER A BRANCH. The fixture's catalog declares
//       `default: "scratch"` and lists `crack` FIRST, with `void` third. So a `pickKind` that
//       reads the catalog answers `scratch`, and one that reaches for the fallback constant
//       answers `void` — the two rules are DISTINGUISHABLE on this input, which is the only
//       reason the check means anything. A fixture whose default happened to be void would
//       pass under both rules and decide nothing.
//
//   Q4  🔴 「분모 없음 — 대조 불가」 IS CONTENT, WITH ITS REASON. A kind whose signature
//       declares no `observed_by` has no inspection_run to contrast against. An EMPTY contrast
//       panel there reads as "no differences found" — the opposite of the truth — so the panel
//       must render the refusal and say which of the two reasons it is.
//
//   Q5  🔴 ONE FACT CHIP RENDERER, NOT THREE. `measured`, `observed` and `processed_with` are
//       one vocabulary by construction. Which field is the name and which is the value is a
//       TABLE in the core (`FACT_SPEC`); the view does not know what a `quantity` is. Section F
//       drives all three through the SAME function and demands the same structure out.
//
//   Q6  🔴 SPEAKER AND EVIDENCE RIDE ON EVERY CHIP, INCLUDING THE ONES THAT HAVE NEITHER. The
//       fixture's fourth fact carries no `source` at all: it must render 「출처 미상」 and
//       「근거 ref 없음」 rather than render clean, because a fact that quietly loses its
//       attribution is exactly the number the criterion forbids shipping.
//
//   Q7  🔴 EVERY CONSOLE CONTROL IS AN ANCHOR. Picking a kind, adding a slice and removing one
//       are links, so the page's form-control budget is untouched — `ledger.html` still carries
//       exactly one input (the lineage box) and zero buttons. Section G scores the rendered
//       console for `<select>`/`<input>`/`<button>` and finds none.
//
//   Q8  🔴 AN ABSENT COUNT IS NOT A MEASURED ZERO. `atoms` missing from a catalog row, a slice
//       row with no denominator, a population with no `clean` — each renders as a refusal or
//       as nothing, never as 0. Printing the second as the first states a fact nobody
//       established.
//
//   Q9  🔴 THE CLASS AXIS IS THE SAME TRAP ONE LEVEL DOWN. A defect's class (interfacial /
//       bulk / edge for a void) is a SECOND closed vocabulary, declared PER KIND in the
//       signature — so a list of void's classes written into the client is the generalisation
//       lost again, exactly as a `finding_kind === 'void'` branch would be. Section L uses two
//       kinds with DISJOINT class sets, so a hardcoded list passes for one and fails the other.
//       And 「클래스」 is deliberately the weakest available word: class is a classification,
//       never a verdict (§6-quater: 「합격인가」는 여전히 저장 금지).
//
// THE FIXTURE IS A DECLARED SHAPE, NOT A CAPTURE, AND IT SAYS SO. `GET /api/ledger/siblings`
// does not exist yet — the parallel server lane is building it. That makes this harness score
// the CLIENT'S READING of a shape the two lanes have to agree on, which is the most a client
// can be held to before the route answers. The moment it does, the fixture is replaced with a
// capture and any disagreement shows up here rather than on the owner's screen.

import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const CORE_PATH = join(SRC, 'case_control_core.js');
const VIEW_PATH = join(SRC, 'case_control_view.js');
const ENTRY_PATH = join(SRC, 'ledger_trace.js');
const PAGE_PATH = join(HERE, '..', 'ledger.html');
const LEDGER_CORE_URL = pathToFileURL(join(SRC, 'ledger_trace_core.js')).href;

const die = (msg) => { console.error(`HARNESS BROKEN: ${msg}`); process.exit(2); };

const CORE_PRISTINE = readFileSync(CORE_PATH, 'utf8');
const VIEW_PRISTINE = readFileSync(VIEW_PATH, 'utf8');
const ENTRY_SRC = readFileSync(ENTRY_PATH, 'utf8');
const PAGE_SRC = readFileSync(PAGE_PATH, 'utf8');
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures', 'case_control.json'), 'utf8'));

// ── the fixture is load-bearing; assert its SHAPE before scoring anything ────────────
// 🔴 A FIXTURE BOTH RULES AGREE ON DECIDES NOTHING. These guards are the difference between
// this file measuring something and this file passing vacuously.
{
  const cat = FIX.catalog;
  if (cat.default === 'void') die('catalog default is `void` — Q3 could not tell the catalog from the constant');
  if (cat.kinds[0].kind === 'void') die('catalog first row is `void` — the no-default path would be undecidable');
  if (!cat.kinds.some((k) => k.kind === 'void')) die('catalog carries no `void` row — the picker check would be vacuous');
  if (!cat.kinds.some((k) => Array.isArray(k.observed_by) && k.observed_by.length === 0)) {
    die('catalog carries no kind with an EMPTY observed_by — Q4 would be vacuous');
  }
  if (!cat.kinds.some((k) => k.atoms === undefined)) die('catalog carries no row with an ABSENT atoms — Q8 would be vacuous');

  const pop = FIX.siblings.populations;
  if (!pop.scanned || pop.scanned.count == null) die('fixture has no `scanned` count — the denominator would be re-derived unnoticed');
  if (pop.found.count + pop.clean_scanned.count !== pop.scanned.count) {
    die('fixture: found + clean_scanned != scanned — the identity the client relies on is broken');
  }
  if (!(pop.never_scanned.count > pop.scanned.count)) {
    die('fixture never_scanned is not large enough to move the rate visibly — Q2 would be weak');
  }

  const f = FIX.siblings.factors;
  if (!f.some((r) => r.clean_scanned === null)) die('no factor with a NULL clean side — the refusal path is unscored');
  if (!f.some((r) => r.clean_scanned && r.clean_scanned.n === 0)) die('no factor absent from the clean side — `absent_from_clean_population` is unscored');
  if (!f.some((r) => r.enrichment_state === 'flat')) die('no `flat` factor — the decoy drop in 차이점 would be unscored');
  if (!f.some((r) => r.enrichment_state === 'undeterminable')) die('no `undeterminable` factor — the KEEP rule would be unscored');
  if (!f.some((r) => r.about === 'inspection') || !f.some((r) => r.about === 'process')) {
    die('factors do not carry BOTH `about` values — a console that conflates a scanner artefact with a process cause would pass');
  }
  if (!f.some((r) => r.axis === 'class')) die('no class factor — the class axis would be unscored');

  const facts = FIX.siblings.facts;
  for (const pred of ['measured', 'observed', 'processed_with']) {
    if (!facts.some((x) => x.predicate === pred)) die(`fixture has no \`${pred}\` fact — Q5 would be vacuous`);
  }
  if (!facts.some((x) => !x.source)) die('every fact carries a source — Q6 would be vacuous');
  if (!facts.some((x) => x.basis && x.basis.kind === 'convention')) die('no convention-backed fact — the 가정 chip is unscored');
  if (!facts.some((x) => x.predicate === 'observed' && x.payload && x.payload.class)) {
    die('no observed fact carrying a `class` — §6-quater ① would be unscored');
  }

  // 🔴 THE CLASS AXIS HAS TO BE DECIDABLE THE SAME WAY THE KIND AXIS IS.
  const voidRow = cat.kinds.find((k) => k.kind === 'void');
  const crackRow = cat.kinds.find((k) => k.kind === 'crack');
  if (!voidRow.classes || !crackRow.classes) die('a kind carries no `classes` — section L would be vacuous');
  if (voidRow.classes.some((c) => crackRow.classes.includes(c))) {
    die('the two kinds share a class value — "switch the kind, switch the list" would be undecidable');
  }
  const reported = new Set(f.filter((r) => r.axis === 'class').map((r) => r.value));
  if (voidRow.classes.every((c) => reported.has(c))) {
    die('every declared class is reported — the 미보고 path (declared but absent) would be unscored');
  }

  // 🔴 THE TRANSFER WALK MUST VISIT DT MORE THAN ONCE, OR "DT happens once" PASSES.
  const hops = FIX.siblings.trace.hops;
  const dtStops = hops.filter((h) => h.to && h.to.kind === 'dt_slot').length;
  if (dtStops < 2) die(`the walk visits DT ${dtStops}x — a fixed-stage renderer would pass; it must be >= 2`);
  if (!hops.some((h) => h.quantity && h.quantity.of != null)) die('no hop carries a quantity PAIR — the selection would be invisible and unscored');
  if (!hops.some((h) => h.basis && h.basis.kind === 'convention')
      || !hops.some((h) => h.basis && h.basis.kind === 'measured')) {
    die('the walk does not carry BOTH basis kinds — the badge could be derived from the state and nobody would notice');
  }
  // A deliberate discontinuity, so the break is a rendered fact rather than a silent bridge.
  let broken = 0;
  for (let i = 1; i < hops.length; i += 1) {
    const prev = hops[i - 1].to; const cur = hops[i].from;
    const idOf = (n) => (n && n.keys ? Object.values(n.keys).join('|') : null);
    if (idOf(prev) !== idOf(cur)) broken += 1;
  }
  if (broken < 1) die('the walk is fully continuous — the break rendering would be unscored');
}

const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');

/** Import a (possibly mutated) pair of modules without writing into client2/src. */
async function load(coreSource, viewSource) {
  // The core imports the LINEAGE core by relative path; a data: URL has no directory, so it is
  // rewritten to the real file. That module is not under test here — it is scored, thoroughly,
  // by `ledger_trace_harness.mjs`.
  const coreRewritten = coreSource.replaceAll("'./ledger_trace_core.js'", `'${LEDGER_CORE_URL}'`);
  const coreUrl = `data:text/javascript;base64,${b64(coreRewritten)}`;
  const viewRewritten = viewSource.replaceAll("'./case_control_core.js'", `'${coreUrl}'`);
  const [core, view] = await Promise.all([
    import(coreUrl),
    import(`data:text/javascript;base64,${b64(viewRewritten)}`),
  ]);
  return { core, view };
}

// ── the document stub ───────────────────────────────────────────────────────────────
// Same stub as `ledger_trace_harness.mjs`, and for the same reason: `textContent` concatenates
// descendants (so an assertion is about the TREE, not one node) and setting it CLEARS children
// (so a re-render that forgot to clear is visible).
function makeDoc() {
  return {
    createElement(tag) {
      return {
        tagName: String(tag).toUpperCase(),
        className: '',
        children: [],
        attrs: Object.create(null),
        _text: '',
        parentNode: null,
        appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
        removeChild(c) {
          const i = this.children.indexOf(c);
          if (i >= 0) this.children.splice(i, 1);
          c.parentNode = null;
          return c;
        },
        setAttribute(k, v) { this.attrs[String(k)] = String(v); },
        getAttribute(k) {
          return Object.prototype.hasOwnProperty.call(this.attrs, String(k))
            ? this.attrs[String(k)] : null;
        },
        get firstChild() { return this.children.length ? this.children[0] : null; },
        set textContent(v) { this._text = String(v); this.children.length = 0; },
        get textContent() {
          return this._text + this.children.map((c) => c.textContent).join('');
        },
      };
    },
  };
}

const walk = (node, out = []) => {
  out.push(node);
  for (const c of node.children) walk(c, out);
  return out;
};
// Tolerant accessors: several mutants make an element DISAPPEAR, and a throw before the
// ASSERTIONS line reports to `check_harnesses.mjs` as DEAD rather than as red.
const NOTHING = { tagName: '', className: '', children: [], textContent: '', getAttribute: () => null };
const first = (list) => (list && list.length ? list[0] : NOTHING);
const classesOf = (n) => String(n.className || '').split(/\s+/).filter(Boolean);
const byClass = (root, cls) => walk(root).filter((n) => classesOf(n).includes(cls));
const byTag = (root, tag) => walk(root).filter((n) => n.tagName === String(tag).toUpperCase());
const byAttr = (root, k, v) => walk(root).filter((n) => n.getAttribute(k) === v);
const hasAttr = (root, k) => walk(root).filter((n) => n.getAttribute(k) !== null);
const stripComments = (s) => s
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n').filter((l) => !/^\s*\/\//.test(l)).join('\n');
const countOccurrences = (haystack, needle) => {
  if (!needle) return 0;
  let n = 0;
  let i = haystack.indexOf(needle);
  while (i !== -1) { n += 1; i = haystack.indexOf(needle, i + needle.length); }
  return n;
};

// ── the suite ───────────────────────────────────────────────────────────────────────

async function suite(coreSource, viewSource) {
  const { core, view } = await load(coreSource, viewSource);
  let pass = 0;
  const failed = [];
  const ok = (name, cond, detail) => {
    if (cond) pass += 1;
    else failed.push(detail ? `${name} — ${detail}` : name);
  };

  const catalog = core.kindCatalog(FIX.catalog);
  const render = (body, question) => {
    const doc = makeDoc();
    const mount = doc.createElement('div');
    const model = core.consoleModel({ catalog, body, question });
    view.renderConsole(doc, mount, model, null);
    return { doc, mount, model };
  };

  // ── A. no rate without its denominator ────────────────────────────────────────────
  {
    const withD = core.rateReading(6, 250);
    ok('A1 a rate with a denominator resolves', withD.ok === true && Math.abs(withD.rate - 0.024) < 1e-9);
    const noD = core.rateReading(6, null);
    ok('A2 a rate WITHOUT a denominator refuses', noD.ok === false && noD.rate === null);
    ok('A3 and the refusal carries a reason', typeof noD.why === 'string' && noD.why.length > 0, noD.why);
    ok('A4 and it keeps the count it does have', noD.n === 6);
    ok('A5 a zero denominator is its own refusal',
      core.rateReading(0, 0).ok === false && core.rateReading(0, 0).d === 0);
    ok('A6 a missing numerator refuses too', core.rateReading(undefined, 250).ok === false);
    // 🔴 A defect rate is small by construction; rounding it to 0% prints "no defects".
    ok('A7 a small rate does not round to zero', core.percentText(0.004) !== '0%', core.percentText(0.004));
    ok('A8 a true zero still reads 0%', core.percentText(0) === '0%');
  }

  // ── B. the fraction reaches the SCREEN, beside the percentage ─────────────────────
  {
    const { mount, model } = render(FIX.siblings, { finding: 'void', slices: {} });
    const lead = first(byClass(mount, 'cc-rate--lead'));
    ok('B1 the headline rate renders', lead.getAttribute('data-rate-ok') === '1');
    ok('B2 and its fraction is on screen with it',
      lead.textContent.includes('6/250'), lead.textContent);
    ok('B3 and the percentage is the right one', lead.textContent.includes('2.4'), lead.textContent);
    // 🔴 THE DENOMINATOR IS ALWAYS RENDERED, and it names what defines it.
    const den = first(byAttr(mount, 'data-denominator', 'present'));
    ok('B4 the denominator block is on screen', den !== NOTHING);
    ok('B5 and it names inspection_run and the method',
      den.textContent.includes('inspection_run') && den.textContent.includes('xray'), den.textContent);
    ok('B6 the model divides by found+clean, not by everything',
      model.split.denominator === 250, String(model.split.denominator));
  }

  // ── C. 🔴 the population is THREE counts, and one of them is outside ──────────────
  {
    const { mount, model } = render(FIX.siblings, { finding: 'void', slices: {} });
    const cells = byAttr(mount, 'data-in-denominator', '1').concat(byAttr(mount, 'data-in-denominator', '0'));
    ok('C1 three population cells render', cells.length === 3, `found ${cells.length}`);
    const un = first(byAttr(mount, 'data-pop', 'unscanned'));
    ok('C2 never-scanned has its OWN cell', un !== NOTHING);
    ok('C3 and its count is on screen', un.textContent.includes('1,120'), un.textContent);
    // 🔴 THE ONE THAT MATTERS. Folding it in gives 1364; the panel must say 250.
    ok('C4 never-scanned is NOT in the denominator', un.getAttribute('data-in-denominator') === '0');
    ok('C5 the model excludes it', model.split.denominator === 250 && model.split.unscanned === 1120,
      `${model.split.denominator}/${model.split.unscanned}`);
    ok('C6 the total keeps it', model.split.total === 1370, String(model.split.total));
    // The arithmetic is printed so a reader can CHECK the exclusion rather than trust it.
    const sum = first(byClass(mount, 'cc-pop__sum'));
    ok('C7 the panel prints the arithmetic', sum.textContent.includes('250') && sum.textContent.includes('미스캔'),
      sum.textContent);
    ok('C8 found and clean are both in the denominator',
      first(byAttr(mount, 'data-pop', 'found')).getAttribute('data-in-denominator') === '1'
      && first(byAttr(mount, 'data-pop', 'clean')).getAttribute('data-in-denominator') === '1');
    // A population missing `clean` cannot produce a denominator by pretending it is 0.
    const partial = core.populationSplit({ population: { found: 7 } });
    ok('C9 a missing clean makes the denominator null, not smaller',
      partial.denominator === null && partial.clean === null);
  }

  // ── D. 🔴 void is a DEFAULT VALUE, never a branch ─────────────────────────────────
  {
    // The catalog says `scratch`; the constant says `void`. They disagree, so this decides.
    ok('D1 no kind asked -> the CATALOG default, not the constant',
      core.pickKind(catalog, '') === 'scratch', core.pickKind(catalog, ''));
    ok('D2 an asked kind wins over the catalog', core.pickKind(catalog, 'crack') === 'crack');
    const noDefault = core.kindCatalog(FIX.catalog_no_default);
    ok('D3 no declared default -> the catalog\'s FIRST row', core.pickKind(noDefault, '') === 'crack',
      core.pickKind(noDefault, ''));
    ok('D4 no catalog at all -> the fallback constant',
      core.pickKind(null, '') === core.DEFAULT_FINDING_KIND);
    // 🔴 THE SOURCE CENSUS. One appearance, and it is an assignment.
    const coreBody = stripComments(coreSource);
    ok('D5 the core mentions the word exactly once', countOccurrences(coreBody, "'void'") === 1,
      `found ${countOccurrences(coreBody, "'void'")}`);
    ok('D6 and that one is an assignment, not a comparison',
      /DEFAULT_FINDING_KIND\s*=\s*'void'/.test(coreBody) && !/===\s*'void'|'void'\s*===/.test(coreBody));
    ok('D7 the view never mentions it at all', !stripComments(viewSource).includes("'void'"));
    ok('D8 nor does the entry', !stripComments(ENTRY_SRC).includes("'void'"));
    // And the picker follows the catalog rather than a list in the view.
    const { mount } = render(FIX.siblings, { finding: '', slices: {} });
    const chips = hasAttr(mount, 'data-kind');
    ok('D9 the picker renders one link per catalog kind',
      chips.length === FIX.catalog.kinds.length, `found ${chips.length}`);
    ok('D10 and the default one is the ACTIVE one',
      first(byAttr(mount, 'aria-current', 'page')).getAttribute('data-kind') === 'scratch',
      first(byAttr(mount, 'aria-current', 'page')).getAttribute('data-kind'));
  }

  // ── E. 🔴 「분모 없음 — 대조 불가」 is content, with its reason ────────────────────
  {
    const { mount, model } = render(FIX.siblings_no_denominator, { finding: 'discoloration', slices: {} });
    ok('E1 the model refuses to contrast', model.contrastable === false);
    const box = first(byAttr(mount, 'data-contrast', 'no-denominator'));
    ok('E2 the contrast panel renders the refusal', box !== NOTHING);
    ok('E3 and the panel TITLE is the sentence',
      first(byClass(box, 'cc-nodenom__title')).textContent === '분모 없음 — 대조 불가',
      first(byClass(box, 'cc-nodenom__title')).textContent);
    // 🔴 WITH THE REASON. The sentence alone does not say WHICH of the two situations it is.
    ok('E4 and it says WHY — the server reason, verbatim',
      box.textContent.includes('observed_by'), box.textContent);
    // The panel is not empty and does not read as "no differences found".
    ok('E5 it is not an empty panel', box.textContent.length > 20);
    // And the rest of the console still works — the refusal is local to one panel.
    ok('E6 the kind picker still renders beside it', hasAttr(mount, 'data-kind').length > 0);
    const shared = first(byAttr(mount, 'data-panel', 'shared'));
    ok('E7 공통점 still renders — it needs no clean population', shared.textContent.includes('B-3'),
      shared.textContent);
    // The kind's own signature is what says so, and the picker says it too.
    const kindRow = catalog.kinds.find((k) => k.kind === 'discoloration');
    ok('E8 the catalog marks the kind as denominator-less', kindRow.hasDenominator === false);
    const { mount: m2 } = render(FIX.siblings, { finding: 'void', slices: {} });
    ok('E9 and the picker marks it before it is clicked',
      byAttr(m2, 'data-kind-nodenominator', '1').length === 1,
      String(byAttr(m2, 'data-kind-nodenominator', '1').length));
  }

  // ── F. 🔴 both denominators, on screen, in 차이점 ─────────────────────────────────
  {
    const { mount, model } = render(FIX.siblings, { finding: 'void', slices: {} });
    const panel = first(byAttr(mount, 'data-panel', 'contrast'));
    // 🔴 `flat` IS DROPPED AND `undeterminable` IS KEPT — the server's own rule, read off
    // each row's field. A missing judgement is not a judgement of "no difference".
    const shown = byClass(panel, 'cc-row');
    ok('F1 the flat decoy is dropped from 차이점',
      byAttr(panel, 'data-factor', 'P-880').length === 0);
    ok('F1b and the undeterminable row is KEPT',
      byAttr(panel, 'data-factor', 'W-9').length === 1);
    ok('F1c exactly the non-flat rows are shown',
      shown.length === FIX.siblings.factors.filter((r) => r.enrichment_state !== 'flat').length,
      `${shown.length} of ${FIX.siblings.factors.length}`);
    const b3 = first(byAttr(panel, 'data-factor', 'B-3'));
    ok('F2 the found side shows its fraction', b3.textContent.includes('5/6'), b3.textContent);
    // 🔴 THE SECOND DENOMINATOR, AND IT IS A DIFFERENT NUMBER FROM THE FIRST.
    ok('F3 the clean side shows ITS OWN fraction', b3.textContent.includes('115/244'), b3.textContent);
    ok('F4 both sides are labelled', b3.textContent.includes('난 쪽') && b3.textContent.includes('안 난 쪽'),
      b3.textContent);
    // A factor absent from the clean side is not "infinite times more likely" — the server
    // says so with a reason and a finite interval, and the screen renders that, not ∞.
    const c2 = first(byAttr(panel, 'data-factor', 'C-2'));
    ok('F5 a zero clean side prints no ratio', !c2.textContent.includes('Infinity'), c2.textContent);
    ok('F5b and it still prints both fractions',
      c2.textContent.includes('4/6') && c2.textContent.includes('0/244'), c2.textContent);
    ok('F5c and it says WHY there is no ratio',
      first(byAttr(c2, 'data-row-reason', 'absent_from_clean_population')) !== NOTHING, c2.textContent);
    // 🔴 THE RANK IS THE SERVER'S INTERVAL LOWER BOUND, CONSUMED. Ranking by the point
    // estimate puts the noisiest rows on top, which is the opposite of the question.
    const lows = model.contrast.map((r) => (r.ci ? r.ci[0] : null)).filter((v) => v !== null);
    ok('F6 차이점 is ranked by the interval lower bound, not the ratio',
      lows.every((v, i) => i === 0 || lows[i - 1] >= v), lows.join(','));
    ok('F6b and the row with no interval sinks to the bottom',
      model.contrast[model.contrast.length - 1].ci === null,
      model.contrast.map((r) => r.key).join(','));
    // The verdict word is the server's.
    ok('F7 each row carries the server verdict',
      first(byAttr(panel, 'data-verdict', 'enriched')) !== NOTHING);
    ok('F7b the undeterminable row says so, not "no difference"',
      first(byAttr(panel, 'data-factor', 'W-9')).textContent.includes('판정 불가'),
      first(byAttr(panel, 'data-factor', 'W-9')).textContent);
    // 🔴 `about` IS A BADGE THAT SEPARATES A SCANNER ARTEFACT FROM A PROCESS CAUSE.
    ok('F7c a process factor is badged as one',
      first(byAttr(b3, 'data-about', 'process')) !== NOTHING, b3.textContent);
    ok('F7d and an inspection factor is badged differently',
      first(byAttr(first(byAttr(mount, 'data-factor', 'interfacial')), 'data-about', 'inspection')) !== NOTHING);
    // 공통점 keeps EVERYTHING, including the decoy the second column exposes.
    const shared = first(byAttr(mount, 'data-panel', 'shared'));
    ok('F8 공통점 keeps the flat decoy', byAttr(shared, 'data-factor', 'P-880').length === 1);
    const sb3 = first(byAttr(shared, 'data-factor', 'B-3'));
    ok('F9 공통점 shows the shared fraction', sb3.textContent.includes('5/6'), sb3.textContent);
    ok('F10 🔴 and the clean-side fraction beside it',
      sb3.textContent.includes('115/244') && sb3.textContent.includes('안 난 쪽'), sb3.textContent);
    const decoy = first(byAttr(shared, 'data-factor', 'P-880'));
    ok('F10b the decoy is visibly a decoy — 6/6 against 238/244',
      decoy.textContent.includes('6/6') && decoy.textContent.includes('238/244'), decoy.textContent);
    // The 현황판 groups the SAME rows by axis, and its fraction is share-of-found.
    const status = first(byAttr(mount, 'data-panel', 'status'));
    const row = first(byAttr(status, 'data-slice-key', 'B-3'));
    ok('F11 the 현황판 groups the same rows by axis', row.textContent.includes('5/6'), row.textContent);
    // 🔴 THE PANEL SAYS ITS TWO NUMBERS ARE DIFFERENT KINDS OF NUMBER. The headline is a
    // defect rate; the rows are shares of the found population. Without the caption a reader
    // substitutes one for the other and 83%-of-my-defects becomes 83%-defective.
    ok('F11b the panel says the rows are shares, not rates',
      first(byAttr(status, 'data-slices-caption', 'share-of-found')) !== NOTHING);
    ok('F12 a factor with no clean side refuses rather than borrowing one',
      first(byAttr(status, 'data-slice-key', 'W-9')) !== NOTHING);
    // 🔴 AND THE REFUSAL IS ON SCREEN AS A REFUSAL. A fabricated `0/244` there would read as
    // "measured, and it is nothing" — the one sentence this console must never say by
    // accident. The row shows its found side and says the other side does not exist.
    const w9 = first(byAttr(panel, 'data-factor', 'W-9'));
    ok('F13 the missing clean side says so', w9.textContent.includes('대조군 없음'), w9.textContent);
    ok('F13b and prints no clean fraction at all',
      !/\/\s*244/.test(w9.textContent) && !w9.textContent.includes('0/'), w9.textContent);
    ok('F13c while its found side is intact', w9.textContent.includes('2/6'), w9.textContent);
  }

  // ── M. 🔴 the transfer walk — ANY length, joined by continuity ────────────────────
  //
  // 🔴 NOT FOUR FIXED STAGES. Every move of a chip is one `transferred` event and the walk
  // is joined by location continuity (hop N's `to` == hop N+1's `from`), so DT can appear
  // any number of times. The fixture visits DT TWICE precisely so a fixed-stage renderer
  // fails here instead of silently drawing a shorter chain.
  {
    const { mount, model } = render(FIX.siblings, { finding: 'void', slices: {} });
    const panel = first(byAttr(mount, 'data-panel', 'trace'));
    const hops = byClass(panel, 'cc-hop');
    ok('M1 every hop the walk carried is rendered',
      hops.length === FIX.siblings.trace.hops.length, `${hops.length} of ${FIX.siblings.trace.hops.length}`);
    ok('M2 the walk visits DT more than once and BOTH show',
      model.trace.hops.filter((h) => h.to && /DT-/.test(h.to.id)).length >= 2,
      model.trace.hops.map((h) => h.to && h.to.id).join(' → '));
    // 🔴 THE QUANTITY PAIR, WITH BOTH SIDES. 「8개」 alone is the forbidden shape.
    const q = first(byAttr(panel, 'data-qty', '8'));
    ok('M3 a selective transfer shows its pair', q.textContent.includes('8/12'), q.textContent);
    ok('M4 and the pair carries its denominator attribute', q.getAttribute('data-qty-of') === '12');
    ok('M5 the remainder is shown when both sides are real',
      first(byAttr(panel, 'data-remainder', '18')).textContent.includes('잔량'),
      first(byAttr(panel, 'data-remainder', '18')).textContent);
    // 🔴 BASIS PER HOP, READ OFF THE FIELD — two hops with the same state, opposite bases.
    ok('M6 a convention-backed hop is labelled 가정',
      byAttr(panel, 'data-basis-kind', 'convention').length >= 1);
    ok('M7 and a measured one is labelled 근거',
      byAttr(panel, 'data-basis-kind', 'measured').length >= 1);
    ok('M8 the two are different hops', panel.textContent.includes('가정') && panel.textContent.includes('근거'));
    // 🔴 A BREAK IS SHOWN, NOT BRIDGED.
    ok('M9 a discontinuity is rendered as one', byAttr(panel, 'data-hop-break', '1').length === 1,
      String(byAttr(panel, 'data-hop-break', '1').length));
    ok('M10 and the model counted it', model.trace.breaks === 1, String(model.trace.breaks));
    // Where it stopped, and that die-level binding is not there.
    ok('M11 the terminal reason is printed verbatim',
      first(byAttr(panel, 'data-trace-terminal', FIX.siblings.trace.terminal_reason)) !== NOTHING);
    ok('M12 the foot says the shape of the walk',
      first(byAttr(panel, 'data-trace-hops', '5')).textContent.includes('경유'),
      first(byAttr(panel, 'data-trace-hops', '5')).textContent);
    ok('M13 and says die-level binding is not landed',
      panel.textContent.includes('다이 단위 바인딩 미착지'));
    // 🔴 NO TRACE AT ALL IS NOT AN EMPTY CHAIN.
    const doc2 = makeDoc();
    const m2 = doc2.createElement('div');
    view.renderConsole(doc2, m2,
      core.consoleModel({ catalog, body: FIX.siblings_no_denominator, question: { finding: 'discoloration', slices: {} } }), null);
    ok('M14 a response with no trace says so rather than drawing an empty chain',
      first(byAttr(m2, 'data-trace', 'absent')) !== NOTHING);
    ok('M15 and renders no hops', byClass(m2, 'cc-hop').length === 0);
  }

  // ── G. 🔴 ONE fact chip renderer for three predicates ─────────────────────────────
  {
    const { mount } = render(FIX.siblings, { finding: 'void', slices: {} });
    const facts = byClass(mount, 'cc-fact');
    ok('G1 every fact renders a chip', facts.length === 4, String(facts.length));
    const m = first(byAttr(mount, 'data-fact', 'measured'));
    const o = first(byAttr(mount, 'data-fact', 'observed'));
    const p = first(byAttr(mount, 'data-fact', 'processed_with'));
    ok('G2 measured reads its quantity and value',
      m.textContent.includes('bondline_thickness') && m.textContent.includes('41.7') && m.textContent.includes('um'),
      m.textContent);
    ok('G3 observed reads its finding_kind and severity',
      o.textContent.includes('void') && o.textContent.includes('대형'), o.textContent);
    ok('G4 processed_with reads its step and recipe rev',
      p.textContent.includes('die_attach') && p.textContent.includes('R-12@4'), p.textContent);
    // 🔴 THE SAME STRUCTURE OUT OF ALL THREE — that is what "one renderer" means on screen.
    for (const [name, node] of [['measured', m], ['observed', o], ['processed_with', p]]) {
      ok(`G5 ${name} has the shared head`, byClass(node, 'cc-fact__head').length === 1);
      ok(`G6 ${name} has the shared foot`, byClass(node, 'cc-fact__foot').length === 1);
      ok(`G7 ${name} carries a speaker badge`, byClass(node, 'cc-speaker').length === 1);
    }
    // The reading table is DATA, so a predicate outside it still renders.
    const odd = core.factChip({ predicate: 'inspected_by', payload: { eqp: 'Z-9' }, source: { who: 'X' } });
    ok('G8 an unknown predicate still produces a chip', !!odd && odd.term === 'inspected_by', odd && odd.term);
    ok('G9 and keeps its qualifiers',
      !!odd && odd.meta.some((q) => q.key === 'eqp' && q.text === 'Z-9'));
  }

  // ── H. 🔴 speaker + evidence on every chip, including the ones with neither ───────
  {
    const { mount } = render(FIX.siblings, { finding: 'void', slices: {} });
    const m = first(byAttr(mount, 'data-fact', 'measured'));
    ok('H1 the speaker is named', m.textContent.includes('MI'), m.textContent);
    ok('H2 the evidence ref is on screen', m.textContent.includes('run_uid=MI-88213'), m.textContent);
    // The fixture's fourth fact has no source at all — it must SAY so.
    const bare = byClass(mount, 'cc-fact').find((n) => n.textContent.includes('reflow'));
    ok('H3 an unattributed fact says 출처 미상', bare && bare.textContent.includes('출처 미상'),
      bare && bare.textContent);
    ok('H4 and says its evidence ref is missing', bare && bare.textContent.includes('근거 ref 없음'),
      bare && bare.textContent);
    ok('H5 the unknown speaker is marked as such',
      first(byAttr(mount, 'data-speaker', 'unknown')) !== NOTHING);
    // 가정 vs 근거 — the SAME spelling the lineage screen uses, one page, one rule.
    const p = first(byAttr(mount, 'data-fact', 'processed_with'));
    ok('H6 a convention-backed fact is labelled 가정',
      p.textContent.includes('가정') && p.textContent.includes('lot_level_to_wafer'), p.textContent);
    ok('H7 and it is marked as convention for the CSS',
      first(byAttr(p, 'data-basis-kind', 'convention')) !== NOTHING);
    ok('H8 a measured fact is labelled 근거', m.textContent.includes('근거 ·'), m.textContent);
    // 🔴 The observer's own words, verbatim and unparsed.
    const o = first(byAttr(mount, 'data-fact', 'observed'));
    ok('H9 the note renders verbatim', o.textContent.includes('3시 방향 가장자리, 육안으로도 보임'), o.textContent);
  }

  // ── I. 🔴 every console control is an ANCHOR ──────────────────────────────────────
  {
    const { mount } = render(FIX.siblings, { finding: 'void', slices: { eqp: 'B-3' } });
    ok('I1 the console renders no <select>', byTag(mount, 'select').length === 0);
    ok('I2 no <input>', byTag(mount, 'input').length === 0);
    ok('I3 no <button>', byTag(mount, 'button').length === 0);
    ok('I4 the kind picker is anchors', byAttr(mount, 'data-kind', 'void')[0].tagName === 'A');
    const link = first(byAttr(mount, 'data-kind', 'crack')).getAttribute('href');
    ok('I5 and each anchor carries its question', link === '?finding=crack', link);
    // A slice row adds a slice; a slice chip removes one. Both are links.
    const row = first(byAttr(mount, 'data-slice-key', 'R-12@4'));
    ok('I6 a slice row is a link that adds the slice',
      row.tagName === 'A' && row.getAttribute('href').includes('recipe=R-12%404'), row.getAttribute('href'));
    const off = first(byAttr(mount, 'data-slice-off', 'eqp'));
    ok('I7 an active slice renders a chip that removes it',
      off.tagName === 'A' && !off.getAttribute('href').includes('eqp='), off.getAttribute('href'));
    ok('I8 and the chip keeps the kind', off.getAttribute('href').includes('finding=void'), off.getAttribute('href'));
    ok('I9 the row link keeps the kind too', row.getAttribute('href').includes('finding=void'));
  }

  // ── J. 🔴 an absent count is not a measured zero ──────────────────────────────────
  {
    const { mount } = render(FIX.siblings, { finding: 'void', slices: {} });
    // `tilt` has no `atoms` key at all.
    const tilt = first(byAttr(mount, 'data-kind', 'tilt'));
    ok('J1 a catalog row with no atoms count renders no number',
      tilt.getAttribute('data-kind-atoms') === null && !/\d/.test(tilt.textContent), tilt.textContent);
    const voidKind = first(byAttr(mount, 'data-kind', 'void'));
    ok('J2 a row that HAS one renders it', voidKind.textContent.includes('412'), voidKind.textContent);
    ok('J3 the core keeps an absent count null',
      catalog.kinds.find((k) => k.kind === 'tilt').atoms === null);
    // A catalog that could not be read does not present its fallback as a choice.
    const absent = core.kindCatalog(FIX.catalog_absent);
    const doc = makeDoc();
    const mnt = doc.createElement('div');
    view.renderConsole(doc, mnt, core.consoleModel({ catalog: absent, body: null, question: { finding: '', slices: {} } }), null);
    ok('J4 an unreadable catalog says so instead of offering one kind',
      first(byAttr(mnt, 'data-kinds-none', 'absent')) !== NOTHING);
    ok('J5 and the console still renders its panels', byAttr(mnt, 'data-panel', 'population').length === 1);
    ok('J6 with every count honest about being unreported',
      first(byAttr(mnt, 'data-pop', 'found')).textContent.includes('—'),
      first(byAttr(mnt, 'data-pop', 'found')).textContent);
    // 🔴 Grouping is done here, never by the locale — a count that groups per machine makes a
    // screenshot unquotable, the same defect the lineage screen fixed for instants.
    ok('J7 counts are grouped without the locale', view.countText(1120) === '1,120');
    ok('J8 and a null count is a dash, not a zero', view.countText(null) === '—');
    ok('J9 no locale formatting anywhere',
      !/toLocale(Date|Time|String)?/.test(stripComments(coreSource + viewSource)));
  }

  // ── L. 🔴 the CLASS axis — a second closed vocabulary, and not hardcoded either ───
  //
  // `MI_LEDGER_SCHEMA_PROPOSAL` §6-quater: a defect's class (interfacial / bulk / edge for a
  // void) arrives INSIDE the `observed` atom this console already receives, its value set is
  // CLOSED PER KIND and declared in the vocabulary signature, and it is both a 현황판 slice
  // axis and a case-control contrast axis — 「계면 보이드만 이 장비에 몰림」 is the finding.
  //
  // 🔴 THE FIXTURE MAKES "READS THE CATALOG" DECIDABLE AGAIN. `void` declares
  // interfacial/bulk/edge and `crack` declares die_edge/corner — DIFFERENT sets. A console
  // holding one list of classes passes for one kind and fails for the other, which is the
  // whole point: switching the kind must switch the list.
  {
    const { mount, model } = render(FIX.siblings, { finding: 'void', slices: {} });
    ok('L1 the kind\'s class set comes from the catalog',
      model.classes.join(',') === 'interfacial,bulk,edge', model.classes.join(','));
    const group = first(byAttr(mount, 'data-axis', 'class'));
    ok('L2 class renders as a slice axis', group !== NOTHING);
    ok('L3 and it is named 클래스 — a classification, not a verdict',
      group.textContent.includes('클래스') && !/등급|판정|합격|불합격/.test(group.textContent),
      group.textContent);
    ok('L4 the class axis leads the 현황판', model.slices[0] && model.slices[0].axis === 'class',
      model.slices[0] && model.slices[0].axis);
    // Each class row keeps its own denominator like any other slice row.
    const inter = first(byAttr(mount, 'data-slice-key', 'interfacial'));
    ok('L5 a class row carries its fraction', inter.textContent.includes('5/6'), inter.textContent);
    ok('L6 and it is a link that slices on class',
      inter.tagName === 'A' && inter.getAttribute('href').includes('class=interfacial'),
      inter.getAttribute('href'));
    // 🔴 A DECLARED CLASS THE ANSWER NEVER MENTIONED IS 미보고, NOT 0.
    const edge = first(byAttr(mount, 'data-slice-key', 'edge'));
    ok('L7 a declared-but-unreported class still appears', edge !== NOTHING);
    ok('L8 and it reads 미보고, never 0', edge.textContent.includes('미보고')
      && !/\b0\b/.test(edge.textContent), edge.textContent);
    ok('L9 and it is marked as declared rather than measured',
      edge.getAttribute('data-slice-declared') === '1');
    // The contrast axis.
    const panel = first(byAttr(mount, 'data-panel', 'contrast'));
    const row = first(byAttr(panel, 'data-factor', 'interfacial'));
    ok('L10 class is a contrast axis too', row !== NOTHING);
    ok('L11 with both denominators, like every other row',
      row.textContent.includes('5/6') && row.textContent.includes('3/244'), row.textContent);
    ok('L12 and it is labelled as the class axis', row.getAttribute('data-factor-axis') === 'class');
    // 🔴 SWITCH THE KIND, SWITCH THE LIST. This is the check a hardcoded set cannot pass.
    const crack = core.consoleModel({ catalog, body: FIX.siblings, question: { finding: 'crack', slices: {} } });
    ok('L13 another kind gets ITS OWN class set',
      crack.classes.join(',') === 'die_edge,corner', crack.classes.join(','));
    ok('L14 and a kind declaring none gets no class axis',
      core.consoleModel({ catalog, body: FIX.siblings_no_denominator, question: { finding: 'scratch', slices: {} } })
        .slices.every((g) => g.axis !== 'class'));
    // The class of a finding rides in the SAME utterance as the finding (§6-quater ①).
    const chip = first(byAttr(mount, 'data-fact', 'observed'));
    ok('L15 the observed chip carries its class',
      first(byAttr(chip, 'data-q', 'class')).textContent.includes('interfacial'),
      chip.textContent);
    ok('L16 under a neutral term', first(byAttr(chip, 'data-q', 'class')).textContent.includes('클래스'));
    // 🔴 NOT HARDCODED — the same census `void` gets, for the same reason.
    for (const value of ['interfacial', 'bulk', 'die_edge']) {
      ok(`L17 no class value «${value}» is written into the client`,
        !stripComments(coreSource).includes(`'${value}'`)
        && !stripComments(viewSource).includes(`'${value}'`)
        && !stripComments(ENTRY_SRC).includes(`'${value}'`));
    }
    // Today's scope is READING the class. Reclassification (`classified_as`) is reserved
    // vocabulary and must not grow a write path on this screen.
    ok('L18 no reclassification write path exists', !ENTRY_SRC.includes('classified_as')
      && !stripComments(viewSource).includes('classified_as'));
  }

  // ── K. re-render, and the notice that does not replace the console ────────────────
  {
    const doc = makeDoc();
    const mount = doc.createElement('div');
    const model = core.consoleModel({ catalog, body: FIX.siblings, question: { finding: 'void', slices: {} } });
    view.renderConsole(doc, mount, model, null);
    view.renderConsole(doc, mount, model, null);
    ok('K1 a re-render replaces rather than accumulates', mount.children.length === 1,
      String(mount.children.length));
    // 🔴 A REFUSAL SITS ABOVE THE PANELS, IT DOES NOT REPLACE THEM.
    const doc2 = makeDoc();
    const m2 = doc2.createElement('div');
    view.renderConsole(doc2, m2,
      core.consoleModel({ catalog, body: null, question: { finding: 'void', slices: {} } }),
      { tone: 'gap', title: '집계 API 미배포', detail: 'HTTP 404' });
    ok('K2 the notice renders', first(byAttr(m2, 'data-notice-tone', 'gap')).textContent.includes('집계 API 미배포'));
    ok('K3 and the server sentence goes out verbatim', m2.textContent.includes('HTTP 404'));
    ok('K4 and the panels are STILL there', byAttr(m2, 'data-panel', 'contrast').length === 1);
    ok('K5 and the picker is still usable', hasAttr(m2, 'data-kind').length === FIX.catalog.kinds.length);
    // A kind the catalog does not list is asked anyway, and the screen says so.
    const doc3 = makeDoc();
    const m3 = doc3.createElement('div');
    view.renderConsole(doc3, m3,
      core.consoleModel({ catalog, body: FIX.siblings, question: { finding: 'delam', slices: {} } }), null);
    ok('K6 an unlisted kind is still asked',
      first(byAttr(m3, 'data-answer-kind', 'console')).getAttribute('data-finding') === 'delam',
      first(byAttr(m3, 'data-answer-kind', 'console')).getAttribute('data-finding'));
    ok('K7 and the screen says it is unlisted',
      first(byAttr(m3, 'data-standing', 'unknown-kind')) !== NOTHING);
  }

  return { pass, fail: failed.length, failed };
}

// ── the wiring census — text only, so it is scored ONCE ──────────────────────────────
function census() {
  let pass = 0;
  const failed = [];
  const ok = (name, cond, detail) => {
    if (cond) pass += 1;
    else failed.push(detail ? `${name} — ${detail}` : name);
  };
  // "Landed is not wired": a renderer nobody calls is a file, not a screen.
  ok('W1 the entry imports the console core', ENTRY_SRC.includes("from './case_control_core.js'"));
  ok('W2 the entry imports the console view', ENTRY_SRC.includes("from './case_control_view.js'"));
  ok('W3 the entry renders the console', ENTRY_SRC.includes('renderConsole('));
  ok('W4 the entry asks the kind catalog', ENTRY_SRC.includes('/api/ledger/kinds'));
  ok('W5 the entry asks the siblings route', ENTRY_SRC.includes('/api/ledger/siblings?'));
  ok('W6 and asks for the contrast framing on the SAME call', ENTRY_SRC.includes('mode=contrast'));
  // 🔴 ONE CALL, NOT TWO. A second endpoint would let the two panels disagree.
  ok('W7 there is no second analysis endpoint', !ENTRY_SRC.includes('/api/ledger/contrast'));
  ok('W8 the console runs on every load', /runConsole\(consoleAsked\)/.test(ENTRY_SRC));
  ok('W9 the page declares the console mount', PAGE_SRC.includes('id="lt-console"'));
  ok('W10 and still declares the lineage hooks',
    PAGE_SRC.includes('id="lt-query"') && PAGE_SRC.includes('id="lt-result"'));
  // 🔴 THE COMPLEXITY BUDGET IS UNTOUCHED, and that is the claim rather than an accident: the
  // console added five kinds of navigation and zero form controls, because every one of them
  // is a link.
  const controls = (PAGE_SRC.match(/<(input|select|textarea)\b/gi) || []).length;
  ok('W11 the page still carries exactly one input', controls === 1, `found ${controls}`);
  const buttons = (PAGE_SRC.match(/<button\b/gi) || []).length;
  ok('W12 and still no buttons', buttons === 0, `found ${buttons}`);
  // Still read-only. The write axis (`POST /api/ledger/actions`) is not in this round.
  ok('W13 the console adds no write',
    !/method\s*:\s*['"](POST|PUT|PATCH|DELETE)/i.test(ENTRY_SRC));
  // The session guard, on the SECOND question too. A shared counter would make one question
  // cancel the other.
  ok('W14 the console has its own session guard',
    countOccurrences(ENTRY_SRC, 'mine !== consoleSession') >= 5,
    `found ${countOccurrences(ENTRY_SRC, 'mine !== consoleSession')}`);
  ok('W15 and the lineage guard is untouched',
    countOccurrences(ENTRY_SRC, 'mine !== session') >= 8,
    `found ${countOccurrences(ENTRY_SRC, 'mine !== session')}`);
  // The lineage answer keeps the console's question in the address bar.
  ok('W16 the lineage URL keeps the finding kind', ENTRY_SRC.includes('consoleQuery(consoleAsked)'));
  // No markup path, ever — an operator's note out of the ledger must not become markup.
  ok('W17 the view builds nodes, never markup',
    !/innerHTML|outerHTML|insertAdjacentHTML/.test(stripComments(VIEW_PRISTINE)));
  return { pass, fail: failed.length, failed };
}

// ── mutants ─────────────────────────────────────────────────────────────────────────
const CORE = 'core';
const VIEW = 'view';

const DEFECTS = [
  // 🔴 THE HEADLINE DEFECT: a percentage with nothing under it.
  [CORE, 'rate-without-a-denominator',
    (s) => s.replace("      why: reason || '분모 없음', text: `${n}건 · 분모 없음` };",
      '      why: null, ok: true, rate: n, text: `${n}` };')],
  [CORE, 'zero-denominator-divides-anyway',
    (s) => s.replace('  if (d <= 0) {', '  if (false) {')],
  [VIEW, 'the-fraction-is-dropped',
    (s) => s.replace("    const frac = el(doc, 'span', 'cc-rate__frac', `${countText(reading.n)}/${countText(reading.d)}`);",
      "    const frac = el(doc, 'span', 'cc-rate__frac', '');")],
  [VIEW, 'a-refusal-renders-blank',
    (s) => s.replace("  const why = el(doc, 'span', 'cc-rate__why', (reading && reading.why) || '분모 없음');",
      "  const why = el(doc, 'span', 'cc-rate__why', '');")],
  [CORE, 'small-rates-round-to-zero',
    (s) => s.replace("  if (pct < 0.01) return '<0.01%';\n  if (pct < 10) return `${pct.toFixed(2)}%`;",
      '  if (pct < 10) return `${Math.round(pct)}%`;')],

  // 🔴 THE THREE-WAY SPLIT, COLLAPSED. This is the defect the brief names explicitly.
  [CORE, 'unscanned-folded-into-the-denominator',
    (s) => s.replace('  const denominator = scanned !== null ? scanned',
      '  const denominator = scanned !== null ? scanned + (unscanned || 0)')],
  [CORE, 'unscanned-marked-as-in-the-denominator',
    (s) => s.replace("    { key: 'unscanned', term: '미스캔', n: s.unscanned, inDenominator: false,",
      "    { key: 'unscanned', term: '미스캔', n: s.unscanned, inDenominator: true,")],
  [CORE, 'unscanned-row-dropped',
    (s) => s.replace("    { key: 'unscanned', term: '미스캔', n: s.unscanned, inDenominator: false,\n      note: '검사 안 함 — 분모 제외' },", '')],
  [VIEW, 'the-arithmetic-is-not-printed',
    (s) => s.replace('  panel.appendChild(sum);', '')],
  // 🔴 THE DEFECT THIS HARNESS ACTUALLY FOUND, KEPT AS A MUTANT. `Number(null) === 0`, so the
  // idiom `Number.isFinite(Number(v))` reads an explicitly-null field — the way a server says
  // "I did not count this" — as a MEASURED ZERO. Shipped in the first draft of the core: a
  // slice with a null denominator rendered 「검사 0회」 and a response with no `denominator`
  // object rendered 「분모 0」. Both look exactly like a real measurement on screen.
  [CORE, 'an-absent-field-reads-as-a-measured-zero',
    (s) => s.replace("  if (v === null || v === undefined || v === '') return null;", '')],
  [CORE, 'a-missing-count-fakes-a-zero',
    (s) => s.replace('  const clean = count(pop.clean_scanned);',
      '  const clean = count(pop.clean_scanned) === null ? 0 : count(pop.clean_scanned);')],

  // 🔴 THE GENERALISATION, LOST. Each of these is "void became a special case".
  [CORE, 'the-constant-outranks-the-catalog',
    (s) => s.replace("  const want = asked == null ? '' : String(asked).trim();\n  if (want !== '') return want;",
      "  const want = asked == null ? '' : String(asked).trim();\n  if (want !== '') return want;\n  return DEFAULT_FINDING_KIND;")],
  [CORE, 'the-catalog-default-is-ignored',
    (s) => s.replace('  if (cat && cat.defaultKind) return cat.defaultKind;', '')],
  [VIEW, 'the-picker-drops-its-coverage',
    (s) => s.replace('    if (row.atoms !== null) {', '    if (false) {')],
  [CORE, 'an-absent-atom-count-reads-as-zero',
    (s) => s.replace('      atoms: numOrNull(row.atoms),',
      '      atoms: numOrNull(row.atoms) === null ? 0 : numOrNull(row.atoms),')],

  // 🔴 THE HONEST DEGRADATION, TURNED BACK INTO AN EMPTY PANEL.
  [CORE, 'a-kind-with-no-method-contrasts-anyway',
    (s) => s.replace("    contrastable: denominator.standing === 'present' && split.clean !== null,",
      '    contrastable: true,')],
  [CORE, 'the-refusal-loses-its-reason',
    (s) => s.replace("? '검사 모집단이 정의되지 않음' : String(den.message),", "? '' : '',")],
  [CORE, 'a-kind-with-no-methods-claims-a-denominator',
    (s) => s.replace('      hasDenominator: methods.length > 0,', '      hasDenominator: true,')],
  [VIEW, 'the-refusal-panel-renders-empty',
    (s) => s.replace("    box.appendChild(el(doc, 'span', 'cc-nodenom__title', '분모 없음 — 대조 불가'));", '')],

  // 🔴 BOTH DENOMINATORS, AND THE BASE RATE.
  [VIEW, 'the-clean-side-is-dropped',
    (s) => s.replace("    side.appendChild(renderSide(doc, '안 난 쪽', row.inClean, 'clean'));", '')],
  // 🔴 THE DECOY SURVIVES INTO 차이점. A factor carried by the found and clean sides alike
  // is `flat` and belongs in 공통점 (where the second column exposes it) and NOT in the
  // differences panel, where it reads as a cause.
  [CORE, 'the-flat-decoy-survives-into-contrast',
    (s) => s.replace("const rows = factorRows(body).filter((r) => r.state !== 'flat');",
      'const rows = factorRows(body);')],
  // 🔴 AND THE OPPOSITE OVERREACH: dropping `undeterminable` too. A missing judgement is not
  // a judgement of "no difference", and hiding it makes an unmeasurable factor look like a
  // measured non-finding.
  [CORE, 'undeterminable-dropped-from-contrast',
    (s) => s.replace("const rows = factorRows(body).filter((r) => r.state !== 'flat');",
      "const rows = factorRows(body).filter((r) => r.state === 'enriched' || r.state === 'depleted');")],
  // Ranking by the point estimate puts the noisiest rows on top — the opposite of the question.
  [CORE, 'contrast-ranked-by-the-point-estimate',
    (s) => s.replace('    const al = a.ci ? a.ci[0] : null;\n    const bl = b.ci ? b.ci[0] : null;',
      '    const al = a.enrichment;\n    const bl = b.enrichment;')],
  // A factor whose clean side the server could not establish must refuse, not borrow.
  [CORE, 'a-missing-clean-side-borrows-a-denominator',
    (s) => s.replace("    inClean: clean ? rateReading(clean.n, clean.of, '안 난 쪽 분모 없음')\n      : rateReading(null, null, '대조군 없음'),",
      '    inClean: clean ? rateReading(clean.n, clean.of) : rateReading(0, 244),')],

  // 🔴 ONE CHIP RENDERER, AND ITS ATTRIBUTION.
  [CORE, 'observed-loses-its-kind-name',
    (s) => s.replace("  observed: { term: '관측', name: 'finding_kind', value: 'severity_word' },",
      "  observed: { term: '관측', name: null, value: 'severity_word' },")],
  [CORE, 'processed_with-loses-its-recipe-rev',
    (s) => s.replace('      return `${raw.recipe_id}${rev}`;', '      return `${raw.recipe_id}`;')],
  [CORE, 'an-unattributed-fact-renders-clean',
    (s) => s.replace("  if (!who) return { kind: 'unknown', text: '출처 미상' };",
      "  if (!who) return { kind: 'source', text: '' };")],
  [CORE, 'the-evidence-ref-is-dropped',
    (s) => s.replace('  if (!raw && !event) return null;', '  return null;\n  if (!raw && !event) return null;')],
  [VIEW, 'a-missing-evidence-ref-renders-nothing',
    (s) => s.replace("    const ev = el(doc, 'span', 'cc-evidence cc-evidence--none', '근거 ref 없음');",
      "    const ev = el(doc, 'span', 'cc-evidence cc-evidence--none', '');")],
  [CORE, 'an-unknown-predicate-is-dropped',
    (s) => s.replace('  if (!fact || typeof fact !== \'object\') return null;',
      "  if (!fact || typeof fact !== 'object') return null;\n  if (!FACT_SPEC[fact.predicate]) return null;")],
  [CORE, 'the-observers-note-is-dropped',
    (s) => s.replace('    note: firstText(payload.note),', '    note: null,')],

  // 🔴 THE ANCHORS. A control here would be a new mode on a page that must not grow one.
  [VIEW, 'the-kind-picker-is-not-a-link',
    (s) => s.replace("    const a = el(doc, 'a', `cc-kind${active ? ' cc-kind--active' : ''}`);",
      "    const a = el(doc, 'span', `cc-kind${active ? ' cc-kind--active' : ''}`);")],
  [VIEW, 'a-slice-chip-does-not-remove-its-slice',
    (s) => s.replace("    const a = queryLink(doc, 'cc-slicechip',\n      `${axisTerm(key)} ${bag[key]} ×`, model.question, key);",
      "    const a = queryLink(doc, 'cc-slicechip',\n      `${axisTerm(key)} ${bag[key]} ×`, model.question, null);")],
  [CORE, 'the-slice-link-drops-the-kind',
    (s) => s.replace("  if (kind !== '') parts.push(`finding=${encodeURIComponent(kind)}`);", '')],
  [VIEW, 'console-re-render-accumulates',
    (s) => s.replace('export function renderConsole(doc, mount, model, notice) {\n  clear(mount);',
      'export function renderConsole(doc, mount, model, notice) {')],
  [VIEW, 'a-refusal-replaces-the-panels',
    (s) => s.replace('  wrap.appendChild(renderStatus(doc, model));', '  if (!notice) wrap.appendChild(renderStatus(doc, model));')
      .replace('  wrap.appendChild(renderContrast(doc, model));', '  if (!notice) wrap.appendChild(renderContrast(doc, model));')],
  // 🔴 THE CLASS AXIS — the same generalisation trap, one level down.
  [CORE, 'the-class-axis-is-dropped',
    (s) => s.replace("  { axis: 'class', term: '클래스' },\n", '')],
  [CORE, 'the-class-set-is-not-read-from-the-catalog',
    (s) => s.replace('    const classes = Array.isArray(row.classes)', '    const classes = Array.isArray(null)')],
  [CORE, 'a-declared-class-with-no-rows-vanishes',
    (s) => s.replace('    const missing = declared.filter((c) => !present.has(c));',
      '    const missing = [];')],
  [CORE, 'a-declared-class-with-no-rows-reads-as-zero',
    (s) => s.replace("          rate: rateReading(null, null, '미보고 — 이 조회에 없음'),",
      '          rate: rateReading(0, 250),')],
  [CORE, 'class-reads-like-a-verdict',
    (s) => s.replace("  class: '클래스',", "  class: '판정',")
      .replace("  { axis: 'class', term: '클래스' },", "  { axis: 'class', term: '판정' },")],
  [CORE, 'the-class-slice-param-is-not-carried',
    (s) => s.replace("export const SLICE_PARAMS = ['class', 'eqp'", "export const SLICE_PARAMS = ['eqp'")],
  [VIEW, 'counts-go-through-the-locale',
    (s) => s.replace('export function countText(n) {',
      'export function countText(n) {\n  if (Number.isFinite(Number(n))) return Number(n).toLocaleString();')],
];

// Must ESCAPE. If one is caught, a check is reading source text instead of behaviour.
const CONTROLS = [
  [CORE, 'control:private-rename', (s) => s.replaceAll('firstText', 'firstNonEmpty')],
  [VIEW, 'control:comments-stripped',
    (s) => s.split('\n').filter((l) => !/^\s*\/\//.test(l)).join('\n')],
];

// ── run ─────────────────────────────────────────────────────────────────────────────
console.log('── case-control console ──────────────────────────────────────────');
const base = await suite(CORE_PRISTINE, VIEW_PRISTINE);
const wiring = census();
for (const f of base.failed) console.log(`  ✗ ${f}`);
for (const f of wiring.failed) console.log(`  ✗ ${f}`);
console.log(`  ${base.pass + wiring.pass} passed, ${base.fail + wiring.fail} failed`);

async function runMutant(target, mutate) {
  const core = target === CORE ? mutate(CORE_PRISTINE) : CORE_PRISTINE;
  const view = target === VIEW ? mutate(VIEW_PRISTINE) : VIEW_PRISTINE;
  if (target === CORE && core === CORE_PRISTINE) return { unchanged: true };
  if (target === VIEW && view === VIEW_PRISTINE) return { unchanged: true };
  try { return await suite(core, view); }
  catch (e) { return { pass: 0, fail: 1, failed: [`threw: ${e && e.message}`] }; }
}

let caught = 0;
const escapedNames = [];
console.log('\n── defect mutants (each must be CAUGHT) ──────────────────────────');
for (const [target, name, mutate] of DEFECTS) {
  const r = await runMutant(target, mutate);
  // 🔴 A mutation that did not apply scores a PRISTINE module and reports "caught: no". A
  // rename upstream must turn this file red, not quietly retire its corpus.
  if (r.unchanged) die(`mutant \`${name}\` did not change the ${target} source — its anchor moved`);
  if (r.fail > 0) { caught += 1; console.log(`  caught  ${name}  (${r.failed[0]})`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}

let controlsCaught = 0;
const controlsCaughtNames = [];
console.log('\n── control mutants (each must ESCAPE) ────────────────────────────');
for (const [target, name, mutate] of CONTROLS) {
  const r = await runMutant(target, mutate);
  if (r.unchanged) die(`control \`${name}\` did not change the ${target} source — its anchor moved`);
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else {
    controlsCaught += 1;
    controlsCaughtNames.push(`${name} (${r.failed[0]})`);
    console.log(`  CAUGHT  ${name}  (${r.failed[0]})`);
  }
}

if (escapedNames.length) console.error(`\ndefects that escaped:\n  ${escapedNames.join('\n  ')}`);
if (controlsCaughtNames.length) {
  console.error('\ncontrols that were caught (a check is reading source text):\n  '
    + controlsCaughtNames.join('\n  '));
}

const bad = base.fail + wiring.fail + escapedNames.length + controlsCaught;
console.log(`\n${base.pass + wiring.pass} passed, ${base.fail + wiring.fail} failed; `
  + `${caught}/${DEFECTS.length} defects caught, ${escapedNames.length} escaped; `
  + `${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
const ran = base.pass + base.fail + wiring.pass + wiring.fail + DEFECTS.length + CONTROLS.length;
const failedTotal = base.fail + wiring.fail + escapedNames.length + controlsCaught;
console.log(`ASSERTIONS ${ran} ${failedTotal}`);
process.exit(bad ? 1 : 0);
