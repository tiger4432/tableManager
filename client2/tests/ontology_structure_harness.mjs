// Harness — the ontology STRUCTURE view is generated from declarations, never drawn.
// Run: node client2/tests/ontology_structure_harness.mjs
//
// WHAT IT DEFENDS. The product owner's brief (SCENARIO_CONSOLE_BRIEF §0-quater) states one
// failure condition outright — 「하드코딩된 노드/엣지 목록이 보이면 실패」 — and it is a
// failure an exit code and a glance at the page cannot detect: a hand-drawn picture of today's
// vocabulary looks EXACTLY like a generated one until the vocabulary changes.
//
//   S1  🔴 THE FIXTURE IS AN ORCHARD, ON PURPOSE. Not one word of the real vocabulary appears
//       in it — no Lot, no Wafer, no has_wafer. A screen carrying a node list cannot render an
//       orchard, so every node and edge the model produces here is proof of derivation. This
//       is the same discipline as the console's `default: "scratch"` fixture: an input the two
//       candidate rules DISAGREE on, rather than one they both happen to satisfy.
//
//   S2  🔴 AND THE SOURCE IS SCORED FOR THE REAL WORDS ANYWAY. S1 proves the fixture renders;
//       it does not prove nobody ALSO wrote the real vocabulary in beside it. Section B greps
//       the two modules (comments stripped) for every entity type and predicate in
//       `server/ledger/vocabulary.py` and demands zero.
//
//   S3  🔴 A 0-COUNT DECLARED EDGE IS NEVER HIDDEN. 「건수 0인 선언 엣지는 숨기지 말고 …
//       0으로 렌더」. The fixture declares `grafted_onto`, which no row mentions. Dropping it
//       is invisible on screen — the graph just looks tidier — and the owner would not learn
//       the axis exists. It must appear, as 선언됨 · 데이터 0.
//
//   S4  🔴 AN UNDECLARED OBSERVED EDGE IS A FINDING, NOT A RENDERING DETAIL. `smuggled_in` is
//       in the rows and in no signature. Dropping it hides ledger content; folding it in with
//       the declared ones hides a gate escape.
//
//   S5  🔴 AN ABSENT COUNT IS NOT A MEASURED ZERO. Same prohibition the console already
//       carries. `Crate.atoms` and one kind's `atoms` are absent in the fixture and must render
//       as 미보고.
//
//   S6  🔴 A GRADE THE CLIENT HAS NEVER HEARD OF STILL RENDERS. The fixture's `bore_fruit`
//       carries a fifth class, `hearsay`. A reader that iterates a four-name list drops it and
//       the bar silently under-counts by 10 with nothing on screen saying so.
//
//   S7  🔴 EVERY CONTROL IS AN ANCHOR. The page's form-control budget is one input, and this
//       view must not spend it. Zero `<select>`, `<input>`, `<button>` in the rendered tree.
//
//   S8  🔴 THE LAYOUT IS DETERMINISTIC AND NOTHING OVERLAPS. A force layout that settles
//       differently each load cannot be pointed at, and two boxes on top of each other are
//       the one failure the "readability is a function" rule forbids most directly.
//
//   S9  🔴 READABILITY IS SCORED, NOT ASSERTED. Section H reads the `os-` CSS out of
//       `ledger.html` and fails on any font-size below 13px.

import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const CORE_PATH = join(SRC, 'ontology_structure_core.js');
const VIEW_PATH = join(SRC, 'ontology_structure_view.js');
const ENTRY_PATH = join(SRC, 'ledger_trace.js');
const PAGE_PATH = join(HERE, '..', 'ledger.html');

const die = (msg) => { console.error(`HARNESS BROKEN: ${msg}`); process.exit(2); };

const CORE_SRC = readFileSync(CORE_PATH, 'utf8');
const VIEW_SRC = readFileSync(VIEW_PATH, 'utf8');
const ENTRY_SRC = readFileSync(ENTRY_PATH, 'utf8');
const PAGE_SRC = readFileSync(PAGE_PATH, 'utf8');
const FIX = JSON.parse(readFileSync(join(HERE, 'fixtures', 'ontology_structure.json'), 'utf8'));

// ── the stylesheet, from BOTH of its files ──────────────────────────────────────────
//
// 🔴 AN ASSERTION THAT LOSES ITS SOURCE DOES NOT GO RED — IT GOES VACUOUS, AND VACUOUS
// READS EXACTLY LIKE GREEN (lead PM, 2026-08-14). This project has shipped that failure
// before: a DOM assertion stayed green while every row was hidden, because the legend
// carried the same words the rows did. Red is a message; vacuous is silence wearing
// green. So each source below is checked for PRESENCE and for CONTENT, and a missing
// one KILLS THE RUN rather than quietly narrowing what section M can still see.
//
// The `os-` rules live in two FILES, and 2026-08-15 is why this is a LIST rather than a path.
// They used to sit inline in `ledger.html`; the structure view is now hosted by admin as well,
// so the rules moved to `src/ontology_structure.css` and the page's block went empty. THE GUARD
// BELOW FIRED, WHICH IS THE ENTIRE POINT — section M would otherwise have gone green while
// measuring nothing, and vacuous reads exactly like green.
//
// The assertion follows the rules: `ledger.html` is NOT a source here any more, and adding it
// back to make this pass would re-create the emptiness the guard exists to catch.
//
//   ontology_structure.css  the screen's own rules (moved out of the page — 144 selectors,
//                           including the `declared_unconsumed` badge and legend variants)
//   ledger_console.css      the console PAGE's overrides still keyed on `os-` (the wide
//                           declaration panel's scroll containment)
//
// Every named source is checked for presence AND content, and a missing or empty one KILLS THE
// RUN rather than quietly narrowing what section M can still see.
const CSS_SOURCES = [
  ['ontology_structure.css', join(SRC, 'ontology_structure.css')],
  ['ledger_console.css', join(SRC, 'ledger_console.css')],
];
const STRUCTURE_CSS = (() => {
  const parts = [];
  for (const [label, path] of CSS_SOURCES) {
    let text = '';
    try { text = readFileSync(path, 'utf8'); } catch (_) {
      die(`cannot read ${path} — section M would be blind to every rule that lives there`);
    }
    if (!/\.os-[a-z]/.test(text)) {
      die(`${label} carries no \`os-\` rule — the rules moved again, or this source is stale. `
        + 'Repoint this list at where they went; do NOT drop the source to make the run pass.');
    }
    parts.push(text);
  }
  return parts.join('\n');
})();

const core = await import(new URL('../src/ontology_structure_core.js', import.meta.url).href);
const view = await import(new URL('../src/ontology_structure_view.js', import.meta.url).href);
const ccCore = await import(new URL('../src/case_control_core.js', import.meta.url).href);

// ── the fixture is load-bearing; assert its SHAPE before scoring anything ────────────
{
  const words = JSON.stringify(FIX);
  for (const real of ['"Lot"', '"Wafer"', 'has_wafer', 'derived_from', 'processed_with']) {
    if (words.includes(real)) die(`fixture leaked a real vocabulary word (${real}) — it would stop discriminating`);
  }
  if (!FIX.predicates.some((p) => p.predicate === 'grafted_onto')) die('fixture lost its 0-count declared predicate');
  if (FIX.edges.some((e) => e.predicate === 'grafted_onto')) die('fixture gave the 0-count predicate rows — S3 would pass vacuously');
  if (!FIX.edges.some((e) => e.predicate === 'smuggled_in')) die('fixture lost its undeclared observed edge');
  if (FIX.predicates.some((p) => p.predicate === 'smuggled_in')) die('fixture declared the undeclared edge — S4 would pass vacuously');
  if (!FIX.edges.some((e) => e.classes && e.classes.hearsay)) die('fixture lost its unknown grade class');
}

// ── the document stub ───────────────────────────────────────────────────────────────
// Same stub as `case_control_harness.mjs` (textContent concatenates descendants, and setting
// it clears children), plus `createElementNS` and `style`, which this view needs for SVG.
function makeDoc() {
  const make = (tag, ns) => ({
    tagName: String(tag).toUpperCase(),
    nodeNS: ns || '',
    className: '',
    children: [],
    attrs: Object.create(null),
    style: {},
    _text: '',
    parentNode: null,
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    removeChild(c) {
      const i = this.children.indexOf(c);
      if (i >= 0) this.children.splice(i, 1);
      c.parentNode = null;
      return c;
    },
    setAttribute(k, v) {
      this.attrs[String(k)] = String(v);
      if (String(k) === 'class') this.className = String(v);
    },
    getAttribute(k) {
      return Object.prototype.hasOwnProperty.call(this.attrs, String(k))
        ? this.attrs[String(k)] : null;
    },
    get firstChild() { return this.children.length ? this.children[0] : null; },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() {
      return this._text + this.children.map((c) => c.textContent).join('');
    },
  });
  return {
    createElement(tag) { return make(tag, ''); },
    createElementNS(ns, tag) { return make(tag, ns); },
  };
}

const walk = (node, out = []) => {
  out.push(node);
  for (const c of node.children) walk(c, out);
  return out;
};
const NOTHING = { tagName: '', className: '', children: [], textContent: '', getAttribute: () => null };
const first = (list) => (list && list.length ? list[0] : NOTHING);
const classesOf = (n) => String(n.className || '').split(/\s+/).filter(Boolean);
const byClass = (root, cls) => walk(root).filter((n) => classesOf(n).includes(cls));
const byTag = (root, tag) => walk(root).filter((n) => n.tagName === String(tag).toUpperCase());
const byAttr = (root, k, v) => walk(root).filter((n) => n.getAttribute(k) === v);
const stripComments = (s) => s
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .split('\n').filter((l) => !/^\s*\/\//.test(l)).join('\n');

let pass = 0;
const failed = [];
const ok = (name, cond, detail) => {
  if (cond) pass += 1;
  else failed.push(detail ? `${name} — ${detail}` : name);
};

// ── build the model and render it ───────────────────────────────────────────────────
const kindsBody = FIX.kinds_body;
const kinds = ccCore.kindCatalog(kindsBody);
const question = { view: 'structure', edge: '', layer: '' };
const model = core.structureModel({ body: FIX, kinds, kindsBody, question });

const doc = makeDoc();
const mount = doc.createElement('div');
view.renderStructure(doc, mount, model, null);
const tree = mount;

// ── A. the graph is DERIVED — an orchard renders ────────────────────────────────────
console.log('\n── A. derivation (the orchard) ───────────────────────────────────');
{
  const subjectLabels = model.graph.subjects.map((n) => n.label);
  ok('A1 subject nodes carry the fixture\'s own types',
    subjectLabels.includes('묘목') && subjectLabels.includes('과수원'),
    `got ${JSON.stringify(subjectLabels)}`);
  const predCodes = model.graph.predicates.map((n) => n.predicate).sort();
  ok('A2 every predicate the fixture declares OR the rows use gets a node',
    ['bore_fruit', 'enroll', 'grafted_onto', 'planted_in', 'smuggled_in'].every((p) => predCodes.includes(p)),
    `got ${JSON.stringify(predCodes)}`);
  ok('A3 the edge count is the declared cross product plus the undeclared rows',
    // planted_in×1 + bore_fruit×2 + grafted_onto×1 + enroll×2 + smuggled_in×2 = 8
    model.totals.edges === 8, `got ${model.totals.edges}`);
  ok('A4 an object node exists for the single declared target',
    model.graph.objects.some((n) => n.label === '과수원'),
    `got ${JSON.stringify(model.graph.objects.map((n) => n.label))}`);
  ok('A5 a multi-target declaration resolves to the object KIND, not to one arbitrary type',
    model.graph.objects.some((n) => n.label === '개체 참조' && n.sub === '3종'),
    `got ${JSON.stringify(model.graph.objects.map((n) => `${n.label}/${n.sub}`))}`);
  ok('A6 the ∅ object of an object-less predicate is a node of its own',
    model.graph.objects.some((n) => n.label.includes('목적어 없음')),
    `got ${JSON.stringify(model.graph.objects.map((n) => n.label))}`);
  ok('A7 the fixture\'s words reach the DOM', tree.textContent.includes('묘목') && tree.textContent.includes('planted_in'));
}

// ── B. no hand-drawn list anywhere in the source ────────────────────────────────────
console.log('\n── B. no hardcoded structure ─────────────────────────────────────');
{
  const REAL_TYPES = ['Lot', 'Wafer', 'Product', 'Equipment', 'Recipe', 'Die'];
  const REAL_PREDICATES = ['register', 'pin', 'same_as', 'derived_from', 'slot_map',
    'has_wafer', 'frame_confirmed', 'processed_with', 'has_param', 'transferred'];
  const coreCode = stripComments(CORE_SRC);
  const viewCode = stripComments(VIEW_SRC);
  // Quoted, so `pin` as a substring of `spin` or a css class does not raise a false alarm.
  const quoted = (w) => [`'${w}'`, `"${w}"`, `\`${w}\``];
  const hits = [];
  for (const w of [...REAL_TYPES, ...REAL_PREDICATES]) {
    for (const q of quoted(w)) {
      if (coreCode.includes(q)) hits.push(`core:${q}`);
      if (viewCode.includes(q)) hits.push(`view:${q}`);
    }
  }
  // 🔴 THE FOUR RESOLUTION CLASSES ARE THE ONE PERMITTED EXCEPTION and they are not
  // structure: `pin`/`confirmed`/`observation`/`inference` are the server's own enum
  // (`ledger_trace.CLASS_NAMES`) and this client only translates them. S6 is what keeps that
  // exception honest — an unknown member must survive.
  const allowed = hits.filter((h) => h.endsWith("'pin'"));
  const real = hits.filter((h) => !h.endsWith("'pin'"));
  ok('B1 no entity type or predicate name is written into the client', real.length === 0,
    `found ${JSON.stringify(real)}`);
  ok('B2 the one `pin` literal is the grade enum, beside the other three',
    allowed.length === 0 || (coreCode.includes("'confirmed'") && coreCode.includes("'inference'")),
    'a lone `pin` would be a vocabulary literal, not the class enum');
  //: The second clause moved off `PAGE_SRC` on 2026-08-15 for the same reason section M did:
  //: the `os-` rules left the page, so asking the PAGE whether a stylesheet injects node labels
  //: became a question about a file that has no stylesheet in it — true, and about nothing. It
  //: asks the stylesheet now, which is where such a rule could actually be written.
  ok('B3 neither the page nor the stylesheet carries node or edge content',
    !/data-node=/.test(PAGE_SRC) && !/os-node--subject[^{]*\{[^}]*content/.test(STRUCTURE_CSS));
}

// ── C. the two origins, and the zero that is a measurement ──────────────────────────
//
// 🔴 THE LEAD PM'S ADDITION (2026-08-14): an edge comes either from the LEDGER AGGREGATE or
// from the DECLARATION ALONE, and the tracking UI's verdict gate is about to be the first
// consumer of a declared-only axis. "선언됐지만 소비자 0" is a thing the owner comes here to
// FIND, so it may be neither hidden nor dimmed nor made to look like a defect — and a
// measured 0 may not print as 미보고, which is a different fact.
console.log('\n── C. declared-only axes, and a measured zero ────────────────────');
{
  // 🔴 THE STATE WORDS ARE THE SERVER'S, NOT THIS CLIENT'S (2026-08-14). The five
  // in `server/ledger_structure.py` are `flowing` · `declared_only` · `unmeasured`
  // · `undeclared` · `declared_unconsumed`. `declared_zero` and
  // `declared_unmeasured` were client-side spellings that never appeared on the
  // wire, and two names for one fact is the drift this whole screen reports on.
  const zero = model.edgeList.filter((e) => e.status === 'declared_only');
  ok('C1 the declared-and-never-used edge is in the list',
    zero.some((e) => e.predicate === 'grafted_onto'),
    `got ${JSON.stringify(model.edgeList.map((e) => `${e.predicate}:${e.status}`))}`);
  // 🔴 SCOPED TO THE EDGE LIST, NOT TO THE PAGE. The LEGEND also carries
  // `data-state="declared_only"` and prints the same words, so a tree-wide check passes
  // even when every declared-only edge has been dropped — MEASURED, on the mutant that
  // filters them out. A proxy that stays green under the defect it names is not evidence.
  const listBox = first(byClass(tree, 'os-edgelist'));
  const rows = byAttr(listBox, 'data-state', 'declared_only');
  ok('C2 and it reaches the DOM as a row of the axis list', rows.length > 0);
  ok('C3 with the words that say which layer it came from',
    listBox.textContent.includes('선언만 · 원장 0'));
  ok('C4 and it is drawn in the graph rather than only listed',
    model.graph.edges.some((e) => e.predicate === 'grafted_onto' && e.lead));
  const graftRow = first(rows.filter((r) => r.textContent.includes('grafted_onto')));
  ok('C5 an aggregate that ran and found nothing reports 0, not 미보고',
    first(byClass(graftRow, 'os-row__n')).textContent === '0건',
    first(byClass(graftRow, 'os-row__n')).textContent);
  ok('C5b and its empty period and grade read as 「원자 0」, not as a reporting gap',
    graftRow.textContent.includes('원자 0 — 기간 없음')
    && graftRow.textContent.includes('원자 0 — 등급 없음')
    && !graftRow.textContent.includes('미보고'),
    graftRow.textContent.slice(0, 160));
  ok('C6 and the model says so — a measured zero, not an absent field',
    zero.every((e) => e.atoms === 0));
  ok('C7 the origin of every edge is stated',
    model.edgeList.every((e) => ['both', 'declaration', 'ledger'].includes(e.origin)));
  ok('C8 a declared-only edge is NOT drawn thinner than a flowing one — it is dashed',
    /stroke-width': e.status === 'flowing' \? \(2 \+ \(e.weight \* 5\)\)/.test(VIEW_SRC)
    || /e\.status === 'flowing' \? \(2 \+ \(e\.weight \* 5\)\)\.toFixed\(2\) : 2\.4/.test(VIEW_SRC),
    'the width branch moved — re-read it before trusting this check');
  ok('C9 the legend names the two layers', tree.textContent.includes('엣지 출처 두 층'));

  // 🔴 AND THE ZERO IS ONLY CLAIMABLE WHEN THE AGGREGATE COULD HAVE COUNTED IT. Same body,
  // ledger absent: the very same axes must fall back to 미보고, or the screen states a
  // measurement nobody took. Two inputs the two candidate rules DISAGREE on.
  const noLedger = core.structureModel({
    body: { ...FIX, state: 'absent' }, kinds, kindsBody, question,
  });
  const unmeasured = noLedger.edgeList.filter((e) => e.status === 'unmeasured');
  ok('C10 with no ledger deployed the same axis is unmeasured, not zero',
    unmeasured.some((e) => e.predicate === 'grafted_onto')
    && unmeasured.every((e) => e.atoms === null),
    `got ${JSON.stringify(noLedger.edgeList.map((e) => `${e.predicate}:${e.status}`))}`);
  const d3 = makeDoc();
  const m3 = d3.createElement('div');
  view.renderStructure(d3, m3, noLedger, null);
  ok('C11 and it renders 미보고 rather than 0건',
    first(byAttr(first(byClass(m3, 'os-edgelist')), 'data-state', 'unmeasured'))
      .textContent.includes('미보고'));
  ok('C12 an aggregate that never answered leaves no measured zeros anywhere',
    noLedger.totals.declaredOnly === 0 && noLedger.totals.aggregateRan === false);
}

// ── D. the undeclared observed edge is a finding ────────────────────────────────────
console.log('\n── D. observed, undeclared ───────────────────────────────────────');
{
  const ghost = model.edgeList.find((e) => e.predicate === 'smuggled_in');
  ok('D1 the row that no signature declares is kept', !!ghost);
  ok('D2 and is marked undeclared', ghost && ghost.status === 'undeclared', ghost && ghost.status);
  ok('D3 its count is the measurement, not a refusal', ghost && ghost.atoms === 7);
  // Scoped, for the reason C2 records: the legend prints 「미선언 · 관측됨」 whether or not a
  // single undeclared edge survived into the list.
  ok('D4 the axis list says so in words, not just the legend',
    first(byClass(tree, 'os-edgelist')).textContent.includes('미선언'));
  ok('D5 its predicate gets a node, marked, so the edge has somewhere to land',
    model.graph.predicates.some((n) => n.predicate === 'smuggled_in' && n.declared === false));
  ok('D6 a subject type nobody declared gets one too — the drift one level deeper',
    model.graph.subjects.some((n) => n.type === 'Trellis' && n.declared === false),
    JSON.stringify(model.graph.subjects.map((n) => `${n.type}:${n.declared}`)));
  const noPeriod = model.edgeList.find((e) => e.subjectType === 'Trellis');
  ok('D7 an edge with no period says so rather than printing an empty range',
    noPeriod && noPeriod.period.ok === false && noPeriod.period.why === '기간 미보고');
  ok('D8 and an edge with no class breakdown does not draw an empty bar',
    noPeriod && noPeriod.grades.reported === false);
}

// ── E. an absent count is not a measured zero ───────────────────────────────────────
console.log('\n── E. absent ≠ zero ──────────────────────────────────────────────');
{
  ok('E1 an entity type with no atoms field reads null, never 0',
    model.graph.subjects.find((n) => n.type === 'Crate').atoms === null);
  const hollow = model.kinds.rows.find((k) => k.kind === 'hollow');
  ok('E2 a kind with no atoms field reads null', hollow && hollow.atoms === null);
  const kindsBox = first(byClass(tree, 'os-kinds'));
  ok('E3 and renders as 미보고 inside the registry panel', kindsBox.textContent.includes('미보고'));
  ok('E4 a kind with no observed_by renders 분모 없음 rather than a rate',
    kindsBox.textContent.includes('분모 없음'));
  ok('E5 the observation table absent on one kind renders 미보고, not an empty cell',
    hollow && hollow.observationTable === '');
}

// ── F. grades ───────────────────────────────────────────────────────────────────────
console.log('\n── F. resolution grades ──────────────────────────────────────────');
{
  const fruit = model.edgeList.find((e) => e.predicate === 'bore_fruit' && e.subjectType === 'Sapling');
  ok('F1 an unknown class survives under its raw spelling',
    fruit && fruit.grades.segments.some((s) => s.key === 'hearsay'),
    fruit && JSON.stringify(fruit.grades.segments.map((s) => s.key)));
  ok('F2 the segments add up to the count', fruit && fruit.grades.counted === 90);
  ok('F3 shares sum to 1', fruit
    && Math.abs(fruit.grades.segments.reduce((s, x) => s + x.share, 0) - 1) < 1e-9);
  const planted = model.edgeList.find((e) => e.predicate === 'planted_in');
  ok('F4 the four known grades keep their declared order',
    planted && planted.grades.segments.map((s) => s.key).join(',') === 'pin,confirmed,observation,inference',
    planted && planted.grades.segments.map((s) => s.key).join(','));
  ok('F5 the Korean labels reach the screen',
    ['핀', '확정', '관측', '추론'].every((w) => tree.textContent.includes(w)));
  const mism = core.classReading({ pin: 1, confirmed: 1 }, 50);
  ok('F6 a grade sum that disagrees with the count is announced, not rescaled', mism.mismatch === true);
  ok('F7 an edge with no classes says so rather than drawing an empty bar',
    core.classReading(null, 5).reported === false);
}

// ── G. every control is an anchor ───────────────────────────────────────────────────
console.log('\n── G. anchors only ───────────────────────────────────────────────');
{
  ok('G1 no <select>', byTag(tree, 'select').length === 0);
  ok('G2 no <input>', byTag(tree, 'input').length === 0);
  ok('G3 no <button>', byTag(tree, 'button').length === 0);
  const anchors = byTag(tree, 'A').filter((a) => a.getAttribute('href'));
  ok('G4 the edges and the layer filter are links', anchors.length > 0);
  ok('G5 and every href carries the view, so the answer is a URL',
    anchors.every((a) => a.getAttribute('href').includes('view=structure')),
    JSON.stringify(anchors.slice(0, 3).map((a) => a.getAttribute('href'))));
  const selected = core.structureModel({
    body: FIX, kinds, kindsBody, question: { view: 'structure', edge: model.edgeList[0].key, layer: '' },
  });
  ok('G6 a selected edge is selected in the model', selected.edgeList[0].selected === true);
  ok('G7 and clicking it again clears the selection',
    view.renderStructure(makeDoc(), makeDoc().createElement('div'), selected, null)
    && byTag(mount, 'A').length > 0);
}

// ── H. layout ───────────────────────────────────────────────────────────────────────
console.log('\n── H. layout ─────────────────────────────────────────────────────');
{
  const again = core.structureModel({ body: FIX, kinds, kindsBody, question });
  const geo = (m) => JSON.stringify([m.graph.subjects, m.graph.predicates, m.graph.objects]
    .map((c) => c.map((n) => [n.id, n.x, n.y])));
  ok('H1 the layout is deterministic', geo(model) === geo(again));
  const noOverlap = (col) => {
    const sorted = [...col].sort((a, b) => a.y - b.y);
    for (let i = 1; i < sorted.length; i += 1) {
      if (sorted[i - 1].y + sorted[i - 1].h > sorted[i].y) return false;
    }
    return true;
  };
  ok('H2 subject boxes do not overlap', noOverlap(model.graph.subjects));
  ok('H3 predicate boxes do not overlap', noOverlap(model.graph.predicates));
  ok('H4 object boxes do not overlap', noOverlap(model.graph.objects));
  const cols = model.graph.columns;
  ok('H5 the three columns do not overlap horizontally',
    cols[0].x + cols[0].w < cols[1].x && cols[1].x + cols[1].w < cols[2].x);
  const fan = model.graph.edges.filter((e) => e.predicate === 'enroll');
  ok('H6 a fan-in spreads its entry points instead of stacking them',
    fan.length === 2 && fan[0].lead.y2 !== fan[1].lead.y2);
  ok('H7 every drawn edge has both segments', model.graph.edges.every((e) => e.lead && e.tail));
}

// ── I. the layer filter, and the vocabulary panel ───────────────────────────────────
console.log('\n── I. filter and vocabulary ──────────────────────────────────────');
{
  const only = core.structureModel({
    body: FIX, kinds, kindsBody, question: { view: 'structure', edge: '', layer: 'canonical' },
  });
  ok('I1 filtering by layer narrows the graph',
    only.graph.edges.every((e) => e.layer === 'canonical') && only.graph.edges.length === 2,
    `got ${only.graph.edges.length}`);
  ok('I2 but the totals still count every axis', only.totals.edges === 8, `got ${only.totals.edges}`);
  ok('I3 the vocabulary panel lists every predicate, used or not',
    model.vocabulary.length === 5, `got ${model.vocabulary.length}`);
  ok('I4 it is sorted by how much has been said with each word',
    model.vocabulary[0].atoms >= model.vocabulary[1].atoms);
  const noGloss = model.vocabulary.find((v) => v.predicate === 'bore_fruit');
  ok('I5 a predicate with no prose gets a gloss DERIVED from its signature',
    noGloss && noGloss.gloss.includes('값') && noGloss.gloss.includes('season'),
    noGloss && noGloss.gloss);
  const objectless = model.vocabulary.find((v) => v.predicate === 'enroll');
  ok('I6 an object-less predicate\'s gloss says so', objectless && objectless.gloss.includes('목적어 없음'));
  ok('I7 a reserved predicate is badged', tree.textContent.includes('예약'));
}

// ── J. declaration map ──────────────────────────────────────────────────────────────
console.log('\n── J. declaration map ────────────────────────────────────────────');
{
  const decl = model.declarations[0];
  ok('J1 the config source is named with its file', decl && decl.file.includes('orchard_config.json'));
  ok('J2 an item that names an axis links to it', decl.items[0].edges.length === 1);
  ok('J3 an item that names none says so rather than rendering a dead link',
    decl.items[2].edges.length === 0 && tree.textContent.includes('연결된 축 없음'));
  const refs = byClass(tree, 'os-decl__ref');
  ok('J4 the links reach the DOM as anchors', refs.length === 2 && refs.every((r) => r.getAttribute('href')));
  ok('J5 and they point at an edge that exists',
    refs.every((r) => model.edgeList.some((e) => e.key === r.getAttribute('data-edge'))));
}

// ── K. state, notices, and the empty world ──────────────────────────────────────────
console.log('\n── K. which nothing is this ──────────────────────────────────────');
{
  const nothing = core.structureModel({ body: null, kinds, kindsBody, question });
  ok('K1 no body leaves the state unknown rather than claiming an empty world',
    nothing.state === 'unknown');
  const d2 = makeDoc();
  const m2 = d2.createElement('div');
  view.renderStructure(d2, m2, nothing, { tone: 'gap', title: '구조 집계 API 미배포 — 화면만 준비됨', detail: '404' });
  ok('K2 the frame still paints', byClass(m2, 'os-panel').length >= 3);
  ok('K3 the notice says the route is missing, not that the ledger is', m2.textContent.includes('미배포'));
  ok('K4 the kind registry still answers from its own route', m2.textContent.includes('마름병'));
  // 🔴 K5 — THE THREE EMPTIES MUST BE TELLABLE APART (lead PM, P0, 2026-08-14).
  //
  // The defect that cost the owner an evening was not that the screen was empty;
  // it was that an empty screen and a screen with legitimately nothing on it were
  // the SAME PIXELS. So it is not enough that each of these prints something —
  // asserting merely "not silent" would stay green on a screen that printed one
  // generic sentence over all three, which is exactly the state being repaired.
  //
  // Three worlds, three sentences, and the test fails if any two collapse:
  //   the answer could not be READ      · the census RAN and counted none
  //   the layer filter excluded them all
  const axisWordsOf = (m) => {
    const d = makeDoc();
    const mt = d.createElement('div');
    view.renderStructure(d, mt, m, null);
    return first(byClass(mt, 'os-edgelist')).textContent;
  };
  const unreadableWords = axisWordsOf(nothing);
  const measuredZeroWords = axisWordsOf(core.structureModel({
    body: { state: 'ready', edges: [] }, kinds, kindsBody, question,
  }));
  const filteredWords = axisWordsOf(core.structureModel({
    body: FIX, kinds, kindsBody, question: { view: 'structure', edge: '', layer: 'no-such-layer' },
  }));
  ok('K5a an unreadable answer says the axes could not be READ',
    unreadableWords.includes('읽지 못'), unreadableWords);
  ok('K5b a census that ran and found none says it MEASURED zero',
    measuredZeroWords.includes('0개') && measuredZeroWords.includes('측정된 0'),
    measuredZeroWords);
  ok('K5c a filter that excluded them all says so, and names the whole',
    filteredWords.includes('계층') && filteredWords.includes('8'), filteredWords);
  ok('K5d and no two of the three are the same sentence — a blank must say WHICH blank',
    new Set([unreadableWords, measuredZeroWords, filteredWords]).size === 3,
    `${unreadableWords} || ${measuredZeroWords} || ${filteredWords}`);

  const empty = core.structureModel({
    body: { state: 'empty', predicates: FIX.predicates, edges: [] }, kinds, kindsBody, question,
  });
  ok('K6 an empty ledger with a live aggregate reads as declared, measured 0',
    empty.totals.declaredOnly === empty.totals.edges && empty.totals.edges === 6,
    `${empty.totals.declaredOnly}/${empty.totals.edges}`);
  const noEdgesKey = core.structureModel({
    body: { state: 'ready', predicates: FIX.predicates }, kinds, kindsBody, question,
  });
  ok('K7 a response with no `edges` key at all claims no zeros',
    noEdgesKey.totals.declaredOnly === 0 && noEdgesKey.totals.unmeasured === 6,
    `${noEdgesKey.totals.declaredOnly}/${noEdgesKey.totals.unmeasured}`);
}

// ── L. wiring — it is on the page, at its own URL ───────────────────────────────────
console.log('\n── L. wiring ─────────────────────────────────────────────────────');
{
  ok('L1 the page carries the mount', /id="lt-structure"/.test(PAGE_SRC));
  ok('L2 the entry imports the renderer', /renderStructure/.test(ENTRY_SRC));
  ok('L3 and asks the aggregate route', /api\/ledger\/structure/.test(ENTRY_SRC));
  ok('L4 the view is a URL, not a mode', /view=structure/.test(PAGE_SRC));
  // 🔴 THE INTENT SURVIVED ITS PROBE. This asserted `if (isStructure) … return;`
  // until `ledger_trace.js` was rewritten and `isStructure` ceased to exist —
  // which made the test red for a reason that had nothing to do with the property
  // it defends. The PROPERTY is still real and still worth defending: a view
  // fetches only its own question, so opening the structure screen must not also
  // start the console's work. Re-expressed against what `render(params)` does
  // today — the structure branch RETURNS, and the console-only fetch is reachable
  // only after that return. Tangle the two again and this goes red.
  const renderBody = ENTRY_SRC.slice(ENTRY_SRC.indexOf('function render(params)'));
  const structAt = renderBody.indexOf('STRUCTURE_VIEW');
  const structReturn = renderBody.indexOf('return;', structAt);
  const coverageAt = renderBody.indexOf('loadCoverage(');
  ok('L5 the structure view returns before any of the console view\'s work',
    structAt > 0 && structReturn > structAt && coverageAt > structReturn,
    `structure@${structAt} return@${structReturn} loadCoverage@${coverageAt}`);
  ok('L6 it has its own session guard', /structureSession/.test(ENTRY_SRC));
  ok('L7 no new dependency was added',
    !/from '(?!\.\/)/.test(stripComments(VIEW_SRC).replace(/from 'node:[^']*'/g, '')));
}

// ── M. readability is scored ────────────────────────────────────────────────────────
console.log('\n── M. readability ────────────────────────────────────────────────');
{
  //: BOTH files. Assembled and validated at load — see `STRUCTURE_CSS`.
  const css = STRUCTURE_CSS;
  const sizes = [...css.matchAll(/font-size:\s*([\d.]+)px/g)].map((m) => Number(m[1]));
  ok('M1 the structure CSS declares font sizes at all', sizes.length > 10, `${sizes.length}`);
  const small = sizes.filter((s) => s < 13);
  ok('M2 nothing is below 13px', small.length === 0, `found ${JSON.stringify(small)}`);
  ok('M3 the graph scrolls horizontally rather than scaling type down',
    /\.os-graph__scroll\s*\{[^}]*overflow-x:\s*auto/.test(css));
  ok('M4 node labels are 17px', /\.os-node__label\s*\{[^}]*font-size:\s*17px/.test(css));
  ok('M5 the legend names both origins and both nothings',
    ['엣지 출처 두 층', '원장 집계', '선언만 · 원장 0', '선언만 · 집계 미보고', '미선언 · 관측됨']
      .every((w) => first(byClass(tree, 'os-legend')).textContent.includes(w)));
  // 🔴 「선언만」 IS NOT FADED. The lead PM's rule, scored: no opacity below 1 and no
  // dim-text colour on the declared-only edge or row. Fading it would say "less
  // important" about the very rows the owner may be here to find.
  //: Written against the POST-rename spelling. `declared_zero` was a client-side word
  //: that never existed on the wire; the stylesheet is being renamed to the server's
  //: `declared_only` in the same commit as the view's unwrap, and these two assertions
  //: are what prove the halves agree.
  ok('M6 the declared-only edge is dashed, not dimmed',
    /\.os-edge--declared_only \.os-edge__lead \{[^}]*stroke:\s*var\(--text-muted\)[^}]*stroke-dasharray/.test(css)
    && !/\.os-edge--declared_only[^{]*\{[^}]*opacity:\s*0\.[0-5]/.test(css));
  // 🔴 THIS WAS A BARE NEGATIVE AND SO IT PASSED VACUOUSLY. `!/…background/` is true
  // when the rule sets no background AND when the rule does not exist at all — so
  // deleting the row style entirely read as green. Require the rule to EXIST first,
  // then require it to carry no background: a missing rule is now red, not silent.
  const declaredOnlyRow = /\.os-row--declared_only\s*\{([^}]*)\}/.exec(css);
  ok('M7 the declared-only row exists and keeps a full-contrast background',
    !!declaredOnlyRow && !/background/.test(declaredOnlyRow[1]),
    declaredOnlyRow ? declaredOnlyRow[1].trim().replace(/\s+/g, ' ')
      : 'no `.os-row--declared_only` rule at all — the old assertion would have been vacuous here');
}

// ── N. served shape: the edge identity is the server's id ───────────────────────────
console.log('\n── N. edge identity (36, not 6) ──────────────────────────────────');
{
  // 🔴 THE ONE GUARD THAT CATCHES A WRONG SCREEN THAT LOOKS RIGHT (P0, 2026-08-14).
  // On the SERVED shape `subject|predicate|object_kind` is NOT unique: a predicate
  // that accepts many target types emits one edge PER TARGET, all sharing that
  // triple. Measured against the live route, `same_as` alone yields 36 edges
  // behind 6 triples. Re-deriving the key here — the obvious "simplification",
  // and what this file's own `edgeKey` invites — silently merges thirty edges into
  // six, and the graph still draws, still balances, and still reads as correct.
  // Nothing on screen says otherwise. Only a count can tell, so the count is
  // pinned.
  //
  // The fixture is an orchard for the reason S1 records, and it is a DISCRIMINANT
  // by construction: the two candidate rules disagree on it 36 to 6. A fixture
  // they agreed on would decide nothing.
  const GROVE = ['Sapling', 'Orchard', 'Crate', 'Trellis', 'Grove', 'Nursery'];
  const servedEdges = [];
  for (const s of GROVE) {
    for (const t of GROVE) {
      servedEdges.push({
        id: `${s}|same_grove_as|entity:${t}`,
        subject_type: s,
        predicate: 'same_grove_as',
        object_kind: 'entity_ref',
        object_kind_label: '개체 참조',
        object_type: t,
        declared: true,
        atoms: 0,
        edge_state: 'declared_only',
        layer: 'canonical',
        status: 'active',
        since: 1,
      });
    }
  }
  const SERVED_FIX = {
    state: 'ready',
    generated_at: '2026-08-14T16:19:25+09:00',
    graph: {
      nodes: GROVE.map((t) => ({
        id: t, type: t, label: t, entity_class: 'issued', keys: ['id'],
        declared: true, atoms_as_subject: 0, node_state: 'declared_only',
      })),
      edges: servedEdges,
      layers: [],
      mechanism: null,
    },
    vocabulary: {
      predicates: [{
        predicate: 'same_grove_as', label: '같은 숲', layer: 'canonical', status: 'active',
        since: 1, subject_types: GROVE, object_kind: 'entity_ref', object_types: GROVE,
        object_fields: [], qualifiers: [], atoms: 0,
      }],
      entity_types: GROVE.map((t) => ({ type: t, label: t, class: 'issued', keys: ['id'] })),
    },
    declarations: [],
  };
  //: The fixture is load-bearing — assert the two rules actually disagree on it.
  const triples = new Set(servedEdges.map((e) => `${e.subject_type}|${e.predicate}|${e.object_kind}`));
  if (servedEdges.length !== 36 || triples.size !== 6) {
    die(`served fixture stopped discriminating: ${servedEdges.length} edges over ${triples.size} triples`);
  }

  const sm = core.structureModel({ body: SERVED_FIX, kinds, kindsBody, question });
  ok('N1 the served shape is recognised as served', sm.reading.shape === 'served', sm.reading.shape);
  ok('N2 every served edge keeps its own identity — 36, not 6',
    sm.edgeList.length === 36, `got ${sm.edgeList.length}`);
  ok('N3 and the 36 keys are distinct',
    new Set(sm.edgeList.map((e) => e.key)).size === 36);
  ok('N4 the key is the server\'s id, not the re-derived triple',
    sm.edgeList.every((e) => e.key.includes('entity:')),
    sm.edgeList[0] && sm.edgeList[0].key);
  ok('N5 all 36 reach the drawn graph, not just the list',
    sm.graph.edges.length === 36, `got ${sm.graph.edges.length}`);
  const dN = makeDoc();
  const mN = dN.createElement('div');
  view.renderStructure(dN, mN, sm, null);
  const nRows = byAttr(first(byClass(mN, 'os-edgelist')), 'data-state', 'declared_only');
  ok('N6 and all 36 reach the DOM as rows of the axis list',
    nRows.length === 36, `got ${nRows.length}`);
  ok('N7 the server\'s state word is used rather than re-derived',
    sm.edgeList.every((e) => e.status === 'declared_only'));
  // 🔴 AND A STATE THIS CLIENT HAS NEVER HEARD OF STILL RENDERS — the same
  // discipline S6 applies to grades. A legend that iterates a fixed list of five
  // would drop it, and the edges under it would leave the screen silently.
  const alien = JSON.parse(JSON.stringify(SERVED_FIX));
  alien.graph.edges[0].edge_state = 'quantum_superposed';
  const am = core.structureModel({ body: alien, kinds, kindsBody, question });
  const dA = makeDoc();
  const mA = dA.createElement('div');
  view.renderStructure(dA, mA, am, null);
  ok('N8 an unknown edge state survives under its raw spelling',
    am.edgeList.some((e) => e.status === 'quantum_superposed')
    && am.totals.byState.some((s) => s.key === 'quantum_superposed' && s.n === 1),
    JSON.stringify(am.totals.byState));
  ok('N9 and it does not take its edge off the screen',
    am.edgeList.length === 36 && mA.textContent.includes('quantum_superposed'));
}

// ── O. a blank is never silent ──────────────────────────────────────────────────────
console.log('\n── O. no silent blank ────────────────────────────────────────────');
{
  // 🔴 THE DEFECT OF 2026-08-14, PINNED. Three of the four containers this screen
  // read had moved one level down the response. Nothing threw; every array came
  // back empty and the frame painted itself over a void under the words 「원장 가동
  // — 아래 숫자는 실측입니다」. The repair is not "read the new keys" — that fixes
  // today's drift and nothing about tomorrow's. The repair is that a reader which
  // cannot find the graph SAYS SO.
  const drifted = {
    state: 'ready', generated_at: '2026-08-14T16:19:25+09:00',
    relation: 'ledger_events', window: {}, cost: {}, cursors: [], drift: {},
  };
  const dm = core.structureModel({ body: drifted, kinds, kindsBody, question });
  ok('O1 an unrecognisable body is reported, not treated as an empty world',
    dm.reading.ok === false && dm.reading.shape === 'unreadable', dm.reading.shape);
  ok('O2 and the reading names BOTH what was expected and what arrived',
    dm.reading.why.includes('graph.edges') && dm.reading.why.includes('cursors'),
    dm.reading.why);
  const dO = makeDoc();
  const mO = dO.createElement('div');
  view.renderStructure(dO, mO, dm, null);
  ok('O3 the screen is not blank', mO.children.length > 0);
  ok('O4 it says the emptiness is the READER\'s, not the ledger\'s',
    mO.textContent.includes('원장이 비어서가 아닙니다'), mO.textContent.slice(0, 200));
  ok('O5 and it refuses to claim the ledger state it was handed',
    !mO.textContent.includes('아래 숫자는 실측입니다'));

  // 🔴 A THROW MUST REACH THE SCREEN. The renderer used to clear the mount and
  // THEN build, so anything that threw left a literally empty element — the same
  // pixels as an empty world, with no way to tell them apart.
  const poisoned = core.structureModel({ body: FIX, kinds, kindsBody, question });
  Object.defineProperty(poisoned, 'edgeList', {
    get() { throw new Error('INJECTED render fault'); },
  });
  const dP = makeDoc();
  const mP = dP.createElement('div');
  let escaped = false;
  try { view.renderStructure(dP, mP, poisoned, null); } catch (_) { escaped = true; }
  ok('O6 a render fault does not escape to the caller', escaped === false);
  ok('O7 the mount is not left empty by it', mP.children.length > 0);
  ok('O8 and the fault itself is on screen',
    mP.textContent.includes('그리지 못했습니다') && mP.textContent.includes('INJECTED render fault'),
    mP.textContent.slice(0, 160));
}

// ── P. the class the view emits has a rule that styles it ───────────────────────────
console.log('\n── P. view ↔ stylesheet agree ────────────────────────────────────');
{
  // 🔴 THE SEAM NOTHING WAS WATCHING (lead PM, 2026-08-14). The view builds its class
  // names out of the state word, the stylesheet keys its rules on that same word, and
  // NOTHING compared the two — so when the state vocabulary was corrected to the
  // server's spelling, every dashed edge silently became a solid one. No test moved.
  // The screen still drew, still balanced, still read as correct, and the one thing it
  // exists to show — an axis that carries data vs an axis that is only declared —
  // stopped being visible.
  //
  // Both directions matter and they catch different halves of a rename:
  //   emitted-but-unstyled  ->  the view moved first, the CSS did not      (P2)
  //   styled-but-unemitted  ->  the CSS kept a rule nothing can reach      (P3)
  const NOT_A_STATE = new Set(['on', 'off']);
  const modifiersIn = (text) => {
    const out = new Set();
    for (const m of text.matchAll(/\.os-(?:edge|row|badge|legend__item)--([a-z_]+)/g)) {
      if (!NOT_A_STATE.has(m[1])) out.add(m[1]);
    }
    return out;
  };

  // A world holding all five states at once, so the harvest is of what the view
  // ACTUALLY put on the elements rather than of what this test assumes it puts there.
  const mk = (t, st, atoms, declared) => ({
    id: `Bed|planted_row|entity:${t}`, subject_type: 'Bed', predicate: 'planted_row',
    object_kind: 'entity_ref', object_type: t, declared, atoms,
    edge_state: st, layer: 'canonical', status: 'active', since: 1,
  });
  const PFIX = {
    state: 'ready',
    generated_at: '2026-08-14T16:19:25+09:00',
    graph: {
      nodes: [{
        id: 'Bed', type: 'Bed', label: 'Bed', entity_class: 'issued', keys: ['id'],
        declared: true, atoms_as_subject: 5, node_state: 'flowing',
      }],
      edges: [
        mk('Rose', 'flowing', 5, true),
        mk('Tulip', 'declared_only', 0, true),
        mk('Iris', 'unmeasured', null, true),
        mk('Weed', 'undeclared', 3, false),
      ],
      layers: [],
      mechanism: {
        state: 'declared', declared: true, config: 'm.json',
        models: [{ model: 'bloom', version: 'v0', nodes: ['sun', 'petal'], edge_ids: ['bloom|sun->petal'] }],
        nodes: [],
        edges: [{
          id: 'bloom|sun->petal', model: 'bloom', source: 'sun', target: 'petal',
          dir: '+', dir_label: '증가', edge_state: 'declared_unconsumed',
        }],
      },
    },
    vocabulary: {
      predicates: [{
        predicate: 'planted_row', label: '심음', layer: 'canonical', status: 'active',
        since: 1, subject_types: ['Bed'], object_kind: 'entity_ref',
        object_types: ['Rose', 'Tulip', 'Iris'], object_fields: [], qualifiers: [], atoms: 5,
      }],
      entity_types: [{ type: 'Bed', label: 'Bed', class: 'issued', keys: ['id'] }],
    },
    declarations: [],
  };
  const pm = core.structureModel({ body: PFIX, kinds, kindsBody, question });
  const dP2 = makeDoc();
  const mP2 = dP2.createElement('div');
  view.renderStructure(dP2, mP2, pm, null);

  const emitted = new Set();
  for (const n of walk(mP2)) {
    for (const c of classesOf(n)) {
      const m = /^os-(?:edge|row|badge|legend__item)--([a-z_]+)$/.exec(c);
      if (m && !NOT_A_STATE.has(m[1])) emitted.add(m[1]);
    }
  }
  const STATES = ['flowing', 'declared_only', 'unmeasured', 'undeclared', 'declared_unconsumed'];
  //: The fixture is load-bearing: if it stopped exercising all five, P2 would pass by
  //: simply never emitting the state whose rule went missing.
  ok('P1 the fixture drives all five states onto the screen',
    STATES.every((s) => emitted.has(s)), `emitted ${[...emitted].sort().join(',')}`);

  const styled = modifiersIn(STRUCTURE_CSS);
  const unstyled = [...emitted].filter((s) => !styled.has(s));
  ok('P2 every state the view emits has a rule in the stylesheet',
    unstyled.length === 0, `unstyled: ${unstyled.sort().join(',')}`);
  const orphan = [...styled].filter((s) => !emitted.has(s));
  ok('P3 and no rule is left keyed on a state the view can no longer emit',
    orphan.length === 0, `orphan: ${orphan.sort().join(',')}`);
}

// ── verdict ─────────────────────────────────────────────────────────────────────────
if (failed.length) console.error(`\nfailures:\n  ${failed.join('\n  ')}`);
console.log(`\n${pass} passed, ${failed.length} failed.`);
console.log(`ASSERTIONS ${pass + failed.length} ${failed.length}`);
process.exit(failed.length ? 1 : 0);
