// Harness — an overlay layer says, IN WORDS, which table and which key it came from.
// Run: node client2/tests/overlay_provenance_harness.mjs   (no node_modules — vm sandbox)
//
// WHY THIS EXISTS, AND WHY IT IS NOT PART OF `overlay_value_colour_harness.mjs`.
// That harness owns COLOUR: since `41b17ee` an overlay dot is filled with the colour its own
// value declares, which means colour now carries a second meaning and can no longer double as
// a layer's identity. This one owns the replacement — identity stated as text. They share the
// same renderer, so the split is by AXIS, not by file: mixing them would put a colour
// regression and a provenance regression behind one exit code and one mutation corpus.
//
// WHAT WAS ACTUALLY WRONG, AND WHY IT DID NOT LOOK LIKE A RENDERER BUG.
// `renderOverlayList` has emitted the source table and the source key since `8e34804`
// (2026-07-26). The operator still could not read them, and the reason was LAYOUT, not
// markup:
//   · `.ov-row` was `display: flex`;
//   · `.ov-name` was the ONLY item carrying `min-width: 0`, so it was the only box that
//     could actually give width back;
//   · `.ov-meta` declared `white-space: nowrap`, which makes its min-content width equal to
//     its whole text, so under `min-width: auto` it effectively refused to shrink;
//   · `.ov-name` had `overflow: hidden` and NO `text-overflow`, so what it lost, it lost
//     SILENTLY.
// Width budget from declared values (`map_editor.html` sidebar 330px, `.sidebar-content`
// padding 15px, `.overlay-box` border+padding 9px a side, `.ov-row` border+padding 6px a
// side => 254px of row interior; `.ov-dot` 11 + `.ov-btns` 3x24+2x2 = 76 + three 5px gaps):
// the name and the chips shared 152px, and ONE chip (`화면기준`, ~65px) drove the name under
// 40px. Two chips drove it to zero. So the identifier vanished exactly as the chip set grew —
// and `41b17ee` grew it.
//
// THEREFORE THIS HARNESS SCORES TWO DIFFERENT KINDS OF THING, DELIBERATELY.
//   A. BEHAVIOUR (JS): the renderer is EXECUTED and its output read. Provenance must be in
//      the row's TEXT. A `title=` attribute does not count and is asserted against on
//      purpose — a tooltip is not shown, it is hidden behind a hover, and the whole defect
//      being closed is "it is in the DOM and not on the screen".
//   B. STRUCTURE (CSS): the declarations that decide whether that text can be squeezed out.
//      A behavioural harness cannot see this — the renderer's output is byte-identical
//      whether the name gets 254px or 3px. Scoring it needs a layout engine (unavailable
//      here) or the declarations themselves, and the declarations are what a future edit
//      will actually change.
//
// MUTATION DISCIPLINE. Every `find` string below was verified to occur EXACTLY ONCE in its
// file before being written here. This directory has twice had a mutation land on its first
// match inside a COMMENT and silently score a different function; uniqueness is checked by
// the sweep itself (`applyOnce`), which FAILS on 0 or >1 matches rather than proceeding.
// The sweep also re-reads the mutated state and asserts the mutation is still present in the
// text it hands to the checks — a mutation a later line repairs would otherwise report green
// and mean "there was no mutation", not "the guard is unnecessary".
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe } from './lib/probe.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const JS_PATH = join(HERE, '..', 'src', 'map_editor.js');
const CSS_PATH = join(HERE, '..', 'src', 'transfer_plan.css');

const JS0 = readFileSync(JS_PATH, 'utf8').replace(/\r\n/g, '\n');
const CSS0 = readFileSync(CSS_PATH, 'utf8').replace(/\r\n/g, '\n');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

// ── Extraction ──────────────────────────────────────────────────────────────────
// 🔴 THE JS IS NO LONGER EXTRACTED. `renderOverlayList` used to be regex-sliced out of
// map_editor.js and evaluated in `vm`, which measures the SHAPE OF THE LETTERS: add one
// import to that function's file and the fragment throws on correct code. The module is now
// imported WHOLE (`lib/probe.mjs`), and the chips it calls are the REAL chips.
// The CSS below is still read as text, and that is not the same thing -- a stylesheet is not
// a module, there is nothing to import, and the declarations ARE the subject.
function sliceBalanced(src, startIdx, open, close) {
  const i = src.indexOf(open, startIdx);
  if (i < 0) return null;
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    const ch = src[j];
    if (ch === open) depth++;
    else if (ch === close) { depth--; if (depth === 0) return src.slice(startIdx, j + 1); }
  }
  return null;
}
// A CSS rule body, by selector. Returned WITHOUT comments so a mutation that only edits a
// comment cannot move any of the structural answers (that is control C2's job).
function cssRule(css, selector) {
  const i = css.indexOf(`\n${selector} {`);
  if (i < 0) die(`CSS rule \`${selector}\` not found in ${CSS_PATH} — renamed or reshaped.`);
  const body = sliceBalanced(css, i + 1, '{', '}');
  if (!body) die(`unbalanced braces for CSS rule ${selector}`);
  return body.replace(/\/\*[\s\S]*?\*\//g, '');
}
function decl(ruleBody, prop) {
  const m = new RegExp(`(?:^|[;{\\s])${prop}\\s*:\\s*([^;}]+)`).exec(ruleBody);
  return m ? m[1].trim().replace(/\s+/g, ' ') : null;
}

// ── Scoring ─────────────────────────────────────────────────────────────────────
let pass = 0, fail = 0, quiet = false;
const failures = [];
function check(name, actual, expected) {
  const a = JSON.stringify(actual), e = JSON.stringify(expected);
  if (a === e) { pass++; return true; }
  fail++; failures.push(name);
  if (!quiet) console.error(`  FAIL ${name}\n       expected ${e}\n       actual   ${a}`);
  return false;
}

// ── Fixtures ────────────────────────────────────────────────────────────────────
// The fixture ACTIVATES the axes it claims to score:
//   · two layers whose SOURCE TABLES differ and two whose SOURCE KEYS differ, so a renderer
//     that prints one layer's provenance for every row is countable rather than invisible;
//   · a FAILED layer, because that is the row whose identity the operator most needs and the
//     one whose markup takes a different branch;
//   · a table and a key carrying `<`, `"` and `&`, because provenance is now rendered as TEXT
//     and text is where an escaping regression turns into markup.
const LAYERS = [
  { id: 1, sourceTable: 'core_defect_map', sourceKey: 'LOT-D_05', color: '#e11d48',
    visible: true, failed: false, count: 1600, fanout: 1, cellCount: 1600 },
  { id: 2, sourceTable: 'core_defect_map', sourceKey: 'LOT-D_06', color: '#0ea5e9',
    visible: true, failed: false, count: 1580, fanout: 2, cellCount: 3160 },
  { id: 3, sourceTable: 'eds_fail_map', sourceKey: 'LOT-D_05', color: '#f59e0b',
    visible: false, failed: false, count: 900, fanout: 1, cellCount: 900 },
  { id: 4, sourceTable: 'dt_map', sourceKey: 'DT-EQP-01_20260511T0000_T01', color: '#a855f7',
    visible: true, failed: true, status: '규격 없음', reason: '소스 맵의 규격이 없습니다' },
  { id: 5, sourceTable: 'a&b<map>', sourceKey: 'K"1', color: '#22c55e',
    visible: true, failed: false, count: 4, fanout: 1, cellCount: 4 },
];

// 🔴 THE CHIP STUBS ARE GONE, AND THAT IS THE POINT OF THE CONVERSION. They existed because
// a sliced `renderOverlayList` could not see the chip functions that live beside it, so this
// file had to re-type them -- and a re-typed copy is free to drift from the real ones while
// this harness stays green. The imported module calls the REAL `overlayAlignChip`,
// `overlayFanChip` and `overlayLegendChip`. The chips still have their own owner
// (`overlay_value_colour_harness.mjs` A9/A10); this file just no longer keeps a second copy.

// The page objects the renderer writes into. `document` has to be a GLOBAL now rather than a
// vm sandbox property, because the imported module resolves `document` the way the browser
// does. `addEventListener` is present because map_editor.js wires the page at module scope.
function installPage() {
  const nodes = {};
  const mk = id => (nodes[id] = {
    id, textContent: '', innerHTML: '', style: {},
    querySelectorAll: () => [],   // the click wiring is not this harness's axis
  });
  mk('overlay-count'); mk('btn-clear-overlays'); mk('overlay-list');
  globalThis.document = {
    getElementById: id => nodes[id] || null,
    addEventListener() {},
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  globalThis.window = globalThis.window || {
    location: { port: '', origin: '', protocol: 'http:', host: '', search: '' },
    addEventListener() {},
  };
  return nodes;
}

// `jsMutate` is a function now, not mutated source text: the probe hands it the subject and
// imports whatever comes back, so a mutant is a WHOLE MODULE. A mutant that fails to parse
// therefore fails loudly instead of scoring as "caught", which is the failure mode that made
// the sliced version measure letter shapes.
async function buildRows(jsMutate, layers) {
  const nodes = installPage();
  const { probe } = await loadWithProbe(JS_PATH, {
    expose: ['renderOverlayList'],
    state: ['overlayLayers'],
    mutate: jsMutate || undefined,
    tag: 'ovprov',
  });
  probe.overlayLayers = layers;
  probe.renderOverlayList();
  return { html: nodes['overlay-list'].innerHTML, count: nodes['overlay-count'].textContent };
}

// One rendered row, split out of the emitted markup. Split on the row element rather than by
// index so a renderer that emits fewer rows fails loudly instead of shifting every answer.
function splitRows(html) {
  const parts = html.split(/(?=<div class="ov-row)/).filter(s => s.includes('ov-row'));
  return parts;
}

// The text an operator can actually READ. Attributes are stripped FIRST and on purpose: a
// `title=` is not shown, and provenance that survives only there is the defect, not the fix.
function visibleText(rowHtml) {
  return rowHtml
    .replace(/<[a-zA-Z][^>]*>/g, ' ')     // opening tags WITH their attributes
    .replace(/<\/[a-zA-Z]+>/g, ' ')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ').trim();
}

// The text inside the provenance region specifically. "Somewhere in the row" is not the
// contract — the brief is "put it where the layer already is", and a renderer that prints the
// table into the chip strip would satisfy a whole-row search while looking like a defect.
function nameText(rowHtml) {
  const m = /<span class="ov-name"[^>]*>([\s\S]*?)<\/span>\s*<span class="ov-meta"/.exec(rowHtml);
  return m ? visibleText(m[1] + '</span>') : null;
}

function countOf(s, needle) {
  let n = 0, i = -1;
  while ((i = s.indexOf(needle, i + 1)) >= 0) n++;
  return n;
}

// ── The checks ──────────────────────────────────────────────────────────────────
async function runChecks(jsMutate, cssSrc, { strict = true } = {}) {
  const r = {};

  // ── A. THE ROW SAYS WHICH TABLE AND WHICH KEY, IN READABLE TEXT ──────────────
  {
    const out = await buildRows(jsMutate, LAYERS);
    const rows = splitRows(out.html);
    r.rowCount = rows.length;
    r.names = rows.map(nameText);
    // Scored per layer as a PAIR, not as "the strings appear somewhere": a row that shows the
    // right table with the wrong key is the exact mistake this feature exists to prevent.
    r.saysBoth = rows.map((h, i) => {
      const t = r.names[i];
      return t !== null && t.includes(LAYERS[i].sourceTable) && t.includes(LAYERS[i].sourceKey);
    });
    // FIXTURE ACTIVITY. If every row rendered the same provenance, the check above would
    // still pass on layer 0 and the suite would be congratulating itself. Distinct layers
    // must produce distinct provenance text.
    r.distinctNames = new Set(r.names).size;
    // The tooltip is NOT the answer. Provenance must survive attribute stripping.
    r.survivesAttrStrip = rows.map((h, i) =>
      visibleText(h).includes(LAYERS[i].sourceTable) && visibleText(h).includes(LAYERS[i].sourceKey));
    // A failed layer is the row you most need to identify, and it takes a different branch.
    r.failedRowSaysBoth = r.saysBoth[3];
    // Escaping: the rendered markup must not contain the raw metacharacters as markup.
    r.escaped = !rows[4].includes('<map>') && !rows[4].includes('a&b<');
    r.escapedStillReads = r.names[4];
    r.countBadge = out.count;

    if (strict) {
      check('every layer renders exactly one row', r.rowCount, LAYERS.length);
      check('every row states its own source table AND its own source key',
        r.saysBoth, LAYERS.map(() => true));
      check('...including the FAILED layer', r.failedRowSaysBoth, true);
      check('distinct layers render distinct provenance (the fixture is not self-satisfying)',
        r.distinctNames, LAYERS.length);
      check('provenance survives attribute stripping — it is text, not a tooltip',
        r.survivesAttrStrip, LAYERS.map(() => true));
      check('a table/key carrying markup characters is escaped', r.escaped, true);
      check('...and still reads back as the original identifier',
        r.escapedStillReads, 'a&b<map> K"1');
      check('the count badge still reports the layer count', r.countBadge, String(LAYERS.length));
    }
  }

  // ── B. THE COMPLEXITY BUDGET, MEASURED ON RENDERED OUTPUT ────────────────────
  //   `overlay_value_colour_harness.mjs` A11 pins the same number by reading the renderer's
  //   SOURCE. This reads what the renderer PRODUCED, which is the half that catches a control
  //   added through a helper rather than through a literal in the function body.
  {
    const out = await buildRows(jsMutate, LAYERS);
    const rows = splitRows(out.html);
    r.buttonsOk = countOf(rows[0], '<button');
    r.buttonsFailed = countOf(rows[3], '<button');
    r.inputs = countOf(out.html, '<input') + countOf(out.html, '<select')
      + countOf(out.html, 'type="checkbox"');
    if (strict) {
      check('a successful overlay row renders exactly 3 buttons (import/toggle/delete)',
        r.buttonsOk, 3);
      check('a failed overlay row renders 2 (there is nothing to import)', r.buttonsFailed, 2);
      check('provenance added no input, select or checkbox anywhere in the list', r.inputs, 0);
    }
  }

  // ── C. THE IDENTIFIER CANNOT BE SQUEEZED OUT, AND CANNOT BE SHRUNK ───────────
  //   This is the half a behavioural harness is blind to: the emitted markup is identical
  //   whether the name box gets 254px or 3px. What decides that is these declarations.
  {
    const row = cssRule(cssSrc, '.ov-row');
    const name = cssRule(cssSrc, '.ov-name');
    const src = cssRule(cssSrc, '.ov-src');
    const key = cssRule(cssSrc, '.ov-key');
    const meta = cssRule(cssSrc, '.ov-meta');

    r.rowDisplay = decl(row, 'display');
    r.rowAreas = (decl(row, 'grid-template-areas') || '').replace(/["\s]+/g, ' ').trim();
    r.metaArea = decl(meta, 'grid-area');
    r.nameArea = decl(name, 'grid-area');
    // The chips must not share a track with the identifier. Stated as "meta owns a row of its
    // own", which is the property that makes the squeeze impossible rather than merely rare.
    r.metaHasOwnLine = /meta meta meta/.test(r.rowAreas) && r.metaArea === 'meta';
    // A hidden overflow with no way for the text to reflow is the SILENT clip. Either part of
    // the identifier must be allowed to wrap.
    r.srcWraps = decl(src, 'overflow-wrap');
    r.keyWraps = decl(key, 'overflow-wrap');
    r.nameHidesOverflow = decl(name, 'overflow') === 'hidden';
    r.srcClips = decl(src, 'text-overflow') !== null || decl(src, 'white-space') === 'nowrap';
    r.keyClips = decl(key, 'text-overflow') !== null || decl(key, 'white-space') === 'nowrap';
    // Readability is function: these four rules may only size themselves from the declared
    // tokens. A raw px/rem here is how a density problem gets "solved" by shrinking text.
    r.rawFontSizes = ['.ov-name', '.ov-src', '.ov-key', '.ov-meta']
      .map(sel => decl(cssRule(cssSrc, sel), 'font-size'))
      .filter(v => v !== null && !/^var\(--tp-fs-(body|label)\)$/.test(v));

    // ── THE OVERFLOW INVARIANT (user report 2026-08-04: "오버레이쪽 ui너무 좁아서 항목이
    //    밖으로 삐져나감"). A row OVERFLOWS its container exactly when its MIN-CONTENT width
    //    exceeds it, and min-content is decided by which items can give width back.
    //    In the pre-fix flex row NOTHING could: `.ov-dot` and `.ov-btns` were
    //    `flex-shrink: 0`, `.ov-meta` was `white-space: nowrap` under the default
    //    `min-width: auto` (so its min-content WAS its full text), and `.ov-name` — the only
    //    item that could shrink — bottoms out at 0 and then the row spills.
    //    A LOWER BOUND THAT NEEDS NO FONT METRICS: interior 254px, `.ov-dot` 11 +
    //    `.ov-btns` (3 x min-width 24 + 2 x 2) 76 + three 5px gaps = 102px before a single
    //    glyph. The live meta strip carries `1600칩` plus `정렬됨`/`화면기준`/`범례 밖 3종`;
    //    each `.ov-chip` adds 12px padding + 2px border + 3px margin = 17px of CHROME alone
    //    (51px for three), and a Hangul syllable at 12px is full-width, i.e. >= 12px of
    //    advance BY DEFINITION — 13 syllables in those three labels is >= 156px. So the row
    //    demanded >= 102 + 51 + 156 = 309px of a 254px box: >= 55px of spill with the
    //    identifier already crushed to zero. That is the reported symptom, and it is
    //    arithmetic on declared constants, not an estimate.
    //    The two declarations below are what make it impossible to come back.
    r.nameColumnCanGive = /minmax\(\s*0\s*,\s*1fr\s*\)/.test(decl(row, 'grid-template-columns') || '');
    r.metaRefusesToWrap = decl(meta, 'white-space') === 'nowrap';

    if (strict) {
      check('the overlay row lays out as a grid', r.rowDisplay, 'grid');
      check('the identifier column can always give width back (minmax(0,1fr))',
        r.nameColumnCanGive, true);
      check('the chip strip wraps on its own line instead of forcing the row wider',
        r.metaRefusesToWrap, false);
      check('the chips own a line of their own — they cannot take the identifier\'s width',
        r.metaHasOwnLine, true);
      check('the identifier owns the name area', r.nameArea, 'name');
      check('the source table may wrap rather than disappear', r.srcWraps, 'anywhere');
      check('the source key may wrap rather than disappear', r.keyWraps, 'anywhere');
      check('neither part is clipped to one line (an elided key is not a key)',
        [r.srcClips, r.keyClips], [false, false]);
      check('the name box does not hide overflow with nothing able to reflow',
        r.nameHidesOverflow, false);
      check('no overlay-row rule sizes its text with a raw value', r.rawFontSizes, []);
    }
  }

  return r;
}

// ── Baseline ────────────────────────────────────────────────────────────────────
console.log('=== BASELINE ===');
await runChecks(null, CSS0, { strict: true });
console.log(`  ${pass} passed, ${fail} failed`);
if (fail > 0) {
  console.error(`BASELINE RED — ${fail} failed: ${failures.join(' | ')}`);
  console.log(`ASSERTIONS ${pass + fail} ${fail}`);
  process.exit(1);
}

// ── Mutants (must be CAUGHT) / controls (must ESCAPE) ───────────────────────────
const MUTATIONS = [
  {
    name: 'N1 [HIGH] the row drops the source TABLE and shows only the key',
    file: 'js',
    find: `        <span class="ov-src">\${escapeHtmlAttr(o.sourceTable)}</span><span class="ov-key">\${escapeHtmlAttr(o.sourceKey)}</span>`,
    repl: `        <span class="ov-src"></span><span class="ov-key">\${escapeHtmlAttr(o.sourceKey)}</span>`,
    breaks: 'a layer names the table it came from',
  },
  {
    name: 'N2 [HIGH] provenance retreats into the tooltip (present in the DOM, not on screen)',
    file: 'js',
    find: `      <span class="ov-name" title="\${escapeHtmlAttr(o.sourceTable + ' · ' + o.sourceKey + (o.reason ? ' — ' + o.reason : ''))}">`,
    repl: `      <span class="ov-name" title="\${escapeHtmlAttr(o.sourceTable + ' · ' + o.sourceKey + (o.reason ? ' — ' + o.reason : ''))}" data-mutant="1"><!--`,
    // The comment swallows the two spans, so the strings survive ONLY in the title attribute
    // — which is exactly the shape the brief rejects ("a tooltip is not shown").
    breaks: 'provenance is readable without hovering',
  },
  {
    name: 'N3 [HIGH] the row goes back to flex — the chips can take the identifier\'s width',
    file: 'css',
    find: `.ov-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  grid-template-areas:
    "dot name btns"
    "meta meta meta";`,
    repl: `.ov-row {
  display: flex;`,
    breaks: 'the chips cannot compete with the identifier for width',
  },
  {
    name: 'N4 [HIGH] the key is clipped to one line with an ellipsis instead of wrapping',
    file: 'css',
    find: `  font-size: var(--tp-fs-label);
  overflow-wrap: anywhere;
}`,
    repl: `  font-size: var(--tp-fs-label);
  white-space: nowrap;
  text-overflow: ellipsis;
}`,
    breaks: 'a long map key is shown in full, not elided',
  },
  {
    name: 'N5 [HIGH] the identifier is hidden again behind an un-reflowable overflow',
    file: 'css',
    find: `.ov-name {
  grid-area: name;
  min-width: 0;`,
    repl: `.ov-name {
  grid-area: name;
  min-width: 0;
  overflow: hidden;`,
    breaks: 'nothing can be silently cut out of the name box',
  },
  {
    name: 'N9 [HIGH] the chip strip refuses to wrap again (the row spills out of the sidebar)',
    file: 'css',
    find: `  font-family: var(--font-mono);
  white-space: normal;
}`,
    repl: `  font-family: var(--font-mono);
  white-space: nowrap;
}`,
    breaks: 'the chips cannot force the row wider than its container',
  },
  {
    name: 'N10 [HIGH] the identifier column is content-sized, so it can no longer give width',
    file: 'css',
    find: `  grid-template-columns: auto minmax(0, 1fr) auto;`,
    repl: `  grid-template-columns: auto auto auto;`,
    breaks: 'the identifier column can always shrink',
  },
  {
    name: 'N6 [MEDIUM] the density problem is "solved" by shrinking the key',
    file: 'css',
    find: `  font-family: var(--font-mono);
  color: var(--text-dim);
  font-size: var(--tp-fs-label);`,
    repl: `  font-family: var(--font-mono);
  color: var(--text-dim);
  font-size: 9px;`,
    breaks: 'the identifier is sized from the declared readability tokens',
  },
  {
    name: 'N7 [MEDIUM] a fourth control lands on the row',
    file: 'js',
    find: `        <button type="button" class="ov-btn ov-del" data-act="del" title="제거">✕</button>`,
    repl: `        <button type="button" class="ov-btn" data-act="rename" title="이름">✎</button>
        <button type="button" class="ov-btn ov-del" data-act="del" title="제거">✕</button>`,
    breaks: 'the overlay row holds its 3-button budget',
  },
  {
    name: 'N8 [MEDIUM] the identifier stops being escaped now that it is rendered as text',
    file: 'js',
    find: `<span class="ov-src">\${escapeHtmlAttr(o.sourceTable)}</span>`,
    repl: `<span class="ov-src">\${o.sourceTable}</span>`,
    breaks: 'a table name carrying markup cannot break the row open',
  },
];

const CONTROLS = [
  {
    name: 'C1 control: a CSS comment-only edit (no declaration changes)',
    file: 'css',
    find: `/* 칩은 이제 자기 줄을 쓴다`,
    repl: `/* MUTANT-CONTROL: this comment changes nothing. 칩은 이제 자기 줄을 쓴다`,
  },
  {
    name: 'C2 control: a consistent local rename in the renderer (behaviour identical)',
    file: 'js',
    find: `  const box = document.getElementById('overlay-list');
  if (!box) return;`,
    repl: `  const listBox = document.getElementById('overlay-list');
  const box = listBox;
  if (!box) return;`,
  },
];

// A mutation that does not apply is a SILENT hole, and one that applies twice scores a
// function nobody meant to touch. Both are refused here rather than reported later.
function applyOnce(src, find, repl, label) {
  const n = countOf(src, find);
  if (n !== 1) return { ok: false, why: `search string occurs ${n} time(s), needs exactly 1`, src };
  const out = src.replace(find, repl);
  if (out === src) return { ok: false, why: 'replacement was a no-op', src };
  return { ok: true, src: out };
}

async function sweep(list, expectCaught, heading) {
  console.log(`\n=== ${heading} ===`);
  let applied = 0, caught = 0;
  const notApplied = [], wrong = [];
  for (const m of list) {
    const target = m.file === 'css' ? CSS0 : JS0;
    const a = applyOnce(target, m.find, m.repl, m.name);
    if (!a.ok) {
      notApplied.push(m.name);
      console.error(`  NOT APPLIED  ${m.name}\n    ${a.why}`);
      continue;
    }
    // CONFIRM THE MUTATED STATE, not merely the outcome. A mutation a later line repairs
    // would score green and mean "there was no mutation".
    if (!a.src.includes(m.repl)) {
      notApplied.push(m.name);
      console.error(`  NOT APPLIED  ${m.name}\n    the replacement is not present in the mutated text`);
      continue;
    }
    // "the original is gone" only applies when the replacement does not deliberately KEEP it
    // (N5/N7 wrap the anchor rather than delete it). Asserting it unconditionally is how a
    // perfectly good mutation gets reported as a silent hole -- which it did, first run.
    if (!m.repl.includes(m.find) && countOf(a.src, m.find) !== 0) {
      notApplied.push(m.name);
      console.error(`  NOT APPLIED  ${m.name}\n    the ORIGINAL text is still present after mutation`);
      continue;
    }
    applied++;

    const before = { pass, fail, n: failures.length };
    quiet = true;
    try {
      // A js mutant is applied to JS0 above -- for its uniqueness and no-op checks -- and then
      // handed to the probe as a function returning that same whole-file text. The CSS half is
      // unchanged: it is read, not run.
      await runChecks(m.file === 'css' ? null : () => a.src,
        m.file === 'css' ? a.src : CSS0, { strict: true });
    } catch (e) {
      // A mutant that makes the renderer throw is still detected — but say so, because a
      // crash and a wrong answer are different evidence.
      failures.push(`${m.name}: threw ${e && e.message}`);
      fail++;
    }
    quiet = false;
    const newFails = failures.slice(before.n);
    // The mutant's own score is rolled back: it must not pollute the baseline count.
    pass = before.pass; fail = before.fail; failures.length = before.n;

    const wasCaught = newFails.length > 0;
    if (wasCaught === expectCaught) {
      if (wasCaught) caught++;
      console.log(`  ${wasCaught ? 'caught ' : 'escaped'} ${m.name}\n            by ${
        wasCaught ? `${newFails.length} assertion(s), first: ${newFails[0]}` : 'no detector fired'}`);
    } else {
      wrong.push(m.name);
      console.error(`  ${expectCaught ? 'ESCAPED' : 'WRONGLY CAUGHT'} ${m.name}\n    ${
        m.breaks ? `nothing scored: ${m.breaks}` : newFails.join(' | ')}`);
    }
  }
  return { applied, caught, notApplied, wrong };
}

const mut = await sweep(MUTATIONS, true, 'MUTATION SWEEP (these must be CAUGHT)');
const ctl = await sweep(CONTROLS, false, 'CONTROL SWEEP (these must ESCAPE)');

console.log(`\n=== SUMMARY ===`);
console.log(`  baseline assertions : ${pass} passed, ${fail} failed`);
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
console.log(`  mutations declared  : ${MUTATIONS.length}`);
console.log(`  mutations APPLIED   : ${mut.applied}`);
console.log(`  mutations CAUGHT    : ${mut.caught}`);
console.log(`  controls APPLIED    : ${ctl.applied}`);
console.log(`  controls ESCAPED    : ${ctl.applied - ctl.wrong.length} of ${CONTROLS.length} (must be all)`);
if (mut.notApplied.length) console.error(`  NOT APPLIED: ${mut.notApplied.join(' | ')}`);
if (mut.wrong.length) console.error(`  ESCAPED (must not): ${mut.wrong.join(' | ')}`);
if (ctl.notApplied.length) console.error(`  CONTROLS NOT APPLIED: ${ctl.notApplied.join(' | ')}`);
if (ctl.wrong.length) console.error(`  CONTROLS WRONGLY CAUGHT: ${ctl.wrong.join(' | ')}`);

const bad = fail > 0
  || mut.applied !== MUTATIONS.length || mut.caught !== MUTATIONS.length
  || ctl.applied !== CONTROLS.length || ctl.wrong.length > 0;
if (bad) process.exit(1);
console.log('\nOK — an overlay layer says which table and which key, in text that cannot be squeezed out.');
