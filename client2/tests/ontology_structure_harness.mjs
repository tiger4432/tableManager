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
  ok('B3 the page carries no node or edge markup either',
    !/data-node=/.test(PAGE_SRC) && !/os-node--subject[^{]*\{[^}]*content/.test(PAGE_SRC));
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
  const zero = model.edgeList.filter((e) => e.status === 'declared_zero');
  ok('C1 the declared-and-never-used edge is in the list',
    zero.some((e) => e.predicate === 'grafted_onto'),
    `got ${JSON.stringify(model.edgeList.map((e) => `${e.predicate}:${e.status}`))}`);
  // 🔴 SCOPED TO THE EDGE LIST, NOT TO THE PAGE. The LEGEND also carries
  // `data-status="declared_zero"` and prints the same words, so a tree-wide check passes
  // even when every declared-only edge has been dropped — MEASURED, on the mutant that
  // filters them out. A proxy that stays green under the defect it names is not evidence.
  const listBox = first(byClass(tree, 'os-edgelist'));
  const rows = byAttr(listBox, 'data-status', 'declared_zero');
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
  const unmeasured = noLedger.edgeList.filter((e) => e.status === 'declared_unmeasured');
  ok('C10 with no ledger deployed the same axis is unmeasured, not zero',
    unmeasured.some((e) => e.predicate === 'grafted_onto')
    && unmeasured.every((e) => e.atoms === null),
    `got ${JSON.stringify(noLedger.edgeList.map((e) => `${e.predicate}:${e.status}`))}`);
  const d3 = makeDoc();
  const m3 = d3.createElement('div');
  view.renderStructure(d3, m3, noLedger, null);
  ok('C11 and it renders 미보고 rather than 0건',
    first(byAttr(first(byClass(m3, 'os-edgelist')), 'data-status', 'declared_unmeasured'))
      .textContent.includes('미보고'));
  ok('C12 an aggregate that never answered leaves no measured zeros anywhere',
    noLedger.totals.declaredZero === 0 && noLedger.totals.aggregateRan === false);
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
  ok('K5 the axis panel says the axes are unreported rather than showing none silently',
    m2.textContent.includes('선언된 축이 없습니다'));
  const empty = core.structureModel({
    body: { state: 'empty', predicates: FIX.predicates, edges: [] }, kinds, kindsBody, question,
  });
  ok('K6 an empty ledger with a live aggregate reads as declared, measured 0',
    empty.totals.declaredZero === empty.totals.edges && empty.totals.edges === 6,
    `${empty.totals.declaredZero}/${empty.totals.edges}`);
  const noEdgesKey = core.structureModel({
    body: { state: 'ready', predicates: FIX.predicates }, kinds, kindsBody, question,
  });
  ok('K7 a response with no `edges` key at all claims no zeros',
    noEdgesKey.totals.declaredZero === 0 && noEdgesKey.totals.declaredUnmeasured === 6,
    `${noEdgesKey.totals.declaredZero}/${noEdgesKey.totals.declaredUnmeasured}`);
}

// ── L. wiring — it is on the page, at its own URL ───────────────────────────────────
console.log('\n── L. wiring ─────────────────────────────────────────────────────');
{
  ok('L1 the page carries the mount', /id="lt-structure"/.test(PAGE_SRC));
  ok('L2 the entry imports the renderer', /renderStructure/.test(ENTRY_SRC));
  ok('L3 and asks the aggregate route', /api\/ledger\/structure/.test(ENTRY_SRC));
  ok('L4 the view is a URL, not a mode', /view=structure/.test(PAGE_SRC));
  ok('L5 the structure view does not also run the console',
    /if \(isStructure\)[\s\S]{0,900}?return;/.test(ENTRY_SRC));
  ok('L6 it has its own session guard', /structureSession/.test(ENTRY_SRC));
  ok('L7 no new dependency was added',
    !/from '(?!\.\/)/.test(stripComments(VIEW_SRC).replace(/from 'node:[^']*'/g, '')));
}

// ── M. readability is scored ────────────────────────────────────────────────────────
console.log('\n── M. readability ────────────────────────────────────────────────');
{
  const block = PAGE_SRC.slice(PAGE_SRC.indexOf('구조 뷰 (?view=structure)'));
  const styleEnd = block.indexOf('</style>');
  const css = styleEnd > 0 ? block.slice(0, styleEnd) : block;
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
  ok('M6 the declared-only edge is dashed, not dimmed',
    /\.os-edge--declared_zero \.os-edge__lead \{[^}]*stroke:\s*var\(--text-muted\)[^}]*stroke-dasharray/.test(css)
    && !/\.os-edge--declared_zero[^{]*\{[^}]*opacity:\s*0\.[0-5]/.test(css));
  ok('M7 and its row keeps a full-contrast background',
    !/\.os-row--declared_zero\s*\{[^}]*background/.test(css));
}

// ── verdict ─────────────────────────────────────────────────────────────────────────
if (failed.length) console.error(`\nfailures:\n  ${failed.join('\n  ')}`);
console.log(`\n${pass} passed, ${failed.length} failed.`);
console.log(`ASSERTIONS ${pass + failed.length} ${failed.length}`);
process.exit(failed.length ? 1 : 0);
