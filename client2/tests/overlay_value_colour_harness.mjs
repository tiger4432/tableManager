/**
 * [N2] Overlay markers are coloured BY THE OVERLAY CELL'S OWN VALUE -- harness.
 *
 * Scores ONE claim, on the shipped branch, by executing it:
 *
 *     An overlay dot's fill is the colour THE LEGEND declares for that dot's value, and
 *     there is no second colour source. A value the legend does not declare gets NO fill
 *     (it is not given an invented colour), and a dot that answers for more than one source
 *     cell gets no fill either (choosing one would be the representative the user rejected).
 *
 * WHY A DEDICATED SCORER. Before this round the overlay layer painted one flat colour per
 * LAYER, so the canvas showed how many overlapping chips there were and where -- but not
 * what any of them said. The obvious wrong fix is a private palette: `pickUnusedColor()` is
 * sitting right there and would make every dot look confidently coloured while meaning
 * nothing. That failure is invisible to the eye (the screen looks better, not worse), which
 * is precisely the class this domain exists to catch.
 *
 * THE ORACLE IS THE DECLARATION, NOT THE FUNCTION. Every expected colour below is a literal
 * written into the fixture's legend rows / served `default_legend` rows. Nothing is compared
 * against another call of the implementation, so a shared defect would have to be a defect of
 * the declaration itself.
 *
 * FIXTURE AXES, all live on purpose:
 *   - a value declared ONLY by the open map's legend        (per-map registry row wins)
 *   - a value declared ONLY by the served default_legend    (the site-wide declaration)
 *   - a value declared by BOTH, with DIFFERENT colours      (precedence is observable;
 *                                                            equal colours would hide it)
 *   - a value declared by NEITHER                           (the honest-absence path)
 *   - a cell holding two items with DIFFERENT values        (no representative)
 *   - a cell holding two items with the SAME value          (still no fill -- a solid dot
 *                                                            means exactly one source chip)
 *
 * Run:  node client2/tests/overlay_value_colour_harness.mjs
 * Read-only against client2/. Mutation sweep is unconditional -- there is no flag to forget.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_PATH = join(HERE, '..', 'src', 'map_editor.js');
// Line endings normalised -- every mutation below matches a `\n` string, and on a CRLF
// checkout those matches silently MISS while the baseline stays green.
const SRC0 = readFileSync(SRC_PATH, 'utf8').replace(/\r\n/g, '\n');

const die = (m) => { console.error(`HARNESS FAILURE: ${m}\n(Nothing was compared.)`); process.exit(2); };

function sliceFunction(source, name) {
  const decl = new RegExp(`(^|\\n)\\s*(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = decl.exec(source);
  if (!m) die(`symbol not found: ${name} (renamed? this harness must be updated, never skipped)`);
  const start = m.index + (m[1] ? m[1].length : 0);
  let i = m.index + m[0].length - 1;
  let paren = 0;
  for (; i < source.length; i++) {
    if (source[i] === '(') paren++;
    else if (source[i] === ')') { paren--; if (paren === 0) { i++; break; } }
  }
  i = source.indexOf('{', i);
  if (i < 0) die(`no body for ${name}`);
  let depth = 0;
  for (; i < source.length; i++) {
    if (source[i] === '{') depth++;
    else if (source[i] === '}') { depth--; if (depth === 0) return source.slice(start, i + 1); }
  }
  die(`unbalanced braces extracting '${name}'`);
}

// Comments stripped -- a sibling harness carried a permanent false red because an ordering
// assertion matched a symbol that only appeared inside a comment.
const stripComments = (s) => s.split('\n').map(ln => ln.replace(/\/\/.*$/, '')).join('\n');
const countOf = (hay, needle) => hay.split(needle).length - 1;

const SYMBOLS = [
  'declaredLegendRow',
  'legendColorForValue', 'overlayMarkerFill', 'paintOverlayDot',
  // A12 (2026-08-04). The REGISTRATION half of this feature: without it the colouring code
  // above is correct and does nothing, because no overlay value is ever in the legend to be
  // declared. Sliced, never re-typed — a local copy would score a seeding the product does
  // not perform.
  'overlayLayerValues', 'ensureLegendValues', 'autoAddLegendValue', 'legendOverlaySources',
  'overlayUnlistedValues', 'overlayLegendChip', 'escapeHtmlAttr',
];

// ── Fixture: the two declaration layers, with DIFFERENT colours where they overlap ────────
// `1` is declared twice on purpose. If the two colours agreed, precedence would be
// unobservable and A3 would pass no matter which source won.
const MAP_LEGEND = [
  { value: '1', color: '#10b981', desc: 'good' },
  { value: 'F', color: '#ef4444', desc: 'fail' },
];
const SERVED_DEFAULT = [
  { value: '1', color: '#000000', desc: 'site good' },   // must LOSE to the map legend row
  { value: 'R', color: '#8b5cf6', desc: 'rework' },      // declared only here
];
const UNLISTED = ['ZZ9', 'QQ'];                          // declared by neither

// Every `saveLegendToStorage()` the seeding path makes. A count, not a boolean: "the local
// draft was written" and "it was written once per value" are different claims.
const ctxSaves = [];

function makeSandbox(src) {
  ctxSaves.length = 0;
  const body = SYMBOLS.map(n => sliceFunction(src, n)).join('\n\n');
  const ctx = {
    console, Math, Number, String, Array, Object, Map, Set, JSON,
    legend: MAP_LEGEND.map(r => ({ ...r })),
    overlayContract: { valueColumnCandidates: [], defaultLegend: SERVED_DEFAULT.map(r => ({ ...r })) },
    // ── A12 support. STUBBED deliberately, and only the parts that are somebody else's
    //    contract: `normalizeLegendItem`/`legendRowSignature` live in
    //    `client2/src/split_registry_row.js` and are scored by `split_registry_harness.mjs`;
    //    `saveLegendToStorage` is the local-draft writer and its own axis is the draft
    //    lifecycle. What is NOT stubbed is everything this axis actually claims —
    //    `overlayLayerValues`, `ensureLegendValues`, `autoAddLegendValue` and
    //    `legendColorForValue` are the real thing.
    //    🔴 The stub signature is NOT identity: it must preserve `vocab`, because the whole
    //    "nothing reaches the server" argument rides on that field surviving the round trip.
    normalizeLegendItem: (o) => ({ desc: '', ...o }),
    legendRowSignature: (o) => JSON.stringify([o.value, o.desc, o.color]),
    legendVocabularySeed: new Map(),
    // A13 reads the LIVE layer set, so it has to be settable from a check.
    overlayLayers: [],
    pickUnusedColor: () => '#123456',
    saveLegendToStorage: () => { ctxSaves.push('save'); },
  };
  vm.createContext(ctx);
  try { vm.runInContext(body, ctx); } catch (e) { die(`sandbox did not evaluate: ${e.message}`); }
  return ctx;
}

// A canvas 2D context that records instead of drawing. `fillStyle` is recorded on assignment
// so "assigned but never used" is distinguishable from "actually filled".
function recordingCtx() {
  const rec = { fills: [], strokes: [], arcs: [], ellipses: [], assignedFill: [] };
  let fillStyle = null, strokeStyle = null, lineWidth = 0;
  return {
    rec,
    get fillStyle() { return fillStyle; },
    set fillStyle(v) { fillStyle = v; rec.assignedFill.push(v); },
    get strokeStyle() { return strokeStyle; },
    set strokeStyle(v) { strokeStyle = v; },
    get lineWidth() { return lineWidth; },
    set lineWidth(v) { lineWidth = v; },
    beginPath() { },
    arc(x, y, r) { rec.arcs.push({ x, y, r }); },
    // 2026-08-04: the painter draws an ELLIPSE when the two radii differ, and falls back to
    // `arc` when the context has no `ellipse`. A recorder without `ellipse` would silently
    // score the fallback and report a circle where the product draws an ellipse -- the same
    // "measured the wrong branch" trap this file already carries scars from. The dots this
    // harness paints are all square, so the count below is unchanged; the method exists so
    // that stops being true by accident rather than in silence.
    ellipse(x, y, rx, ry) { rec.ellipses.push({ x, y, rx, ry }); },
    fill() { rec.fills.push(fillStyle); },
    stroke() { rec.strokes.push({ color: strokeStyle, width: lineWidth }); },
  };
}

const item = (val) => ({ val, rx: 1, ry: 2, mmX: 0, mmY: 0, srcX: 0, srcY: 0 });

// ── Assertions ───────────────────────────────────────────────────────────────────────────
function runAll(src) {
  const fails = [];
  let ran = 0;
  const ok = (cond, name, detail) => { ran++; if (!cond) fails.push(`${name}${detail ? ` -- ${detail}` : ''}`); };
  const eq = (got, want, name) => ok(got === want, name, `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
  // Structural compare for the array-shaped answers A12 needs. `eq` stays reference-strict on
  // purpose for every scalar assertion above it -- widening it would quietly turn `0 === '0'`
  // style mistakes into passes across 60 existing checks.
  const eqDeep = (got, want, name) =>
    ok(JSON.stringify(got) === JSON.stringify(want), name,
       `got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
  const ctx = makeSandbox(src);

  // ── A1: PATH ONE -- the value is in THE OPEN MAP'S legend (its registry rows). ──
  eq(ctx.legendColorForValue('1'), '#10b981', 'A1 map legend colour');
  eq(ctx.legendColorForValue('F'), '#ef4444', 'A1b map legend colour (second row)');
  // A stored value arrives as whatever the column type made it; the lookup must not care.
  eq(ctx.legendColorForValue(1), '#10b981', 'A1c a numeric value finds its string row');

  // ── A2: PATH TWO -- declared only by the served `default_legend`. ──
  eq(ctx.legendColorForValue('R'), '#8b5cf6', 'A2 served default_legend colour');

  // ── A3: PRECEDENCE. The open map's own row wins over the site-wide declaration. ──
  //        Both declare `1`; if the served row won, the dot would contradict the legend
  //        table the user is looking at while both sources are "the legend".
  ok(ctx.legendColorForValue('1') !== '#000000', 'A3 the map legend row wins over default_legend',
    'the served colour won -- the canvas would disagree with the visible legend table');

  // ── A4: PATH THREE -- declared by NEITHER. This is the honest-absence path. ──
  for (const v of UNLISTED) {
    eq(ctx.legendColorForValue(v), null, `A4 unlisted value '${v}' has no colour`);
  }
  // And it must not be quietly turned into a palette entry. Both palettes are read out of
  // the source so a new palette colour cannot slip past this list.
  const paletteHits = [];
  for (const arrName of ['LEGEND_PALETTE', 'OVERLAY_COLORS']) {
    const m = new RegExp(`const ${arrName} = \\[([^\\]]*)\\]`, 's').exec(src);
    if (!m) { ok(false, `A4b ${arrName} not found in source`, 'the palette moved; this check is blind'); continue; }
    const colours = m[1].match(/#[0-9a-fA-F]{6}/g) || [];
    ok(colours.length > 3, `A4b ${arrName} parsed`, `only ${colours.length} colours found`);
    for (const v of UNLISTED) if (colours.includes(ctx.legendColorForValue(v))) paletteHits.push(`${v}->${arrName}`);
  }
  ok(paletteHits.length === 0, 'A4c an unlisted value is never given a palette colour', paletteHits.join(', '));

  // ── A5: the empty/absent value is not a colour question at all. ──
  eq(ctx.legendColorForValue(''), null, 'A5 empty value');
  eq(ctx.legendColorForValue(null), null, 'A5b null value');
  eq(ctx.legendColorForValue(undefined), null, 'A5c undefined value');

  // ── A6: THE FILL RULE. A solid dot means EXACTLY ONE source chip with a declared value. ──
  eq(ctx.overlayMarkerFill([item('1')]), '#10b981', 'A6 one listed item is filled');
  eq(ctx.overlayMarkerFill([item('R')]), '#8b5cf6', 'A6b one item declared by default_legend is filled');
  eq(ctx.overlayMarkerFill([item('ZZ9')]), null, 'A6c one UNLISTED item is not filled');
  eq(ctx.overlayMarkerFill([item('1'), item('F')]), null,
    'A6d two DIFFERENT values pick no representative');
  // 🔴 Even when the several items agree. The fallback dot is drawn only because the cell is
  //    too small to show them apart; a solid dot there would read as "one source chip", and
  //    the whole point of the rule is that a solid dot has exactly one meaning.
  eq(ctx.overlayMarkerFill([item('1'), item('1')]), null,
    'A6e two items are unfilled even when they agree');
  eq(ctx.overlayMarkerFill([]), null, 'A6f an empty list is not filled');
  eq(ctx.overlayMarkerFill(null), null, 'A6g a missing list is not filled');

  // ── A7: THE PAINTER. Execute it and read what reached the canvas. ──
  {
    const c = recordingCtx();
    ctx.paintOverlayDot(c, 10, 20, 3, '#10b981', '#3b82f6');
    eq(c.rec.fills.length, 1, 'A7 a filled dot fills once');
    eq(c.rec.fills[0], '#10b981', 'A7b it fills with the VALUE colour');
    ok(c.rec.strokes.some(s => s.color === '#3b82f6'), 'A7c the ring is the LAYER colour',
      `strokes: ${JSON.stringify(c.rec.strokes)} -- layer identity is lost when 2+ overlays are on`);
    ok(c.rec.strokes.some(s => s.color === '#ffffff'), 'A7d a white halo separates it from the cell',
      'a value-coloured dot on a same-coloured cell would be invisible');
    eq(c.rec.arcs.length, 1, 'A7e one arc per dot');
  }
  {
    // The unlisted dot. NOTHING may be filled -- not the ring colour, not a default.
    const c = recordingCtx();
    ctx.paintOverlayDot(c, 10, 20, 3, null, '#3b82f6');
    eq(c.rec.fills.length, 0, 'A7f an unlisted dot is not filled at all');
    eq(c.rec.assignedFill.length, 0, 'A7g and no fill style is even assigned',
      'assigning it means one edit away from filling it');
    ok(c.rec.strokes.some(s => s.color === '#3b82f6'), 'A7h the hollow dot still shows its layer');
    eq(c.rec.arcs.length, 1, 'A7i the hollow dot is still drawn');
  }

  // ── A8: WHICH VALUES ARE UNLISTED -- recomputed from the live legend, never cached. ──
  {
    const layer = {
      items: new Map([
        ['0_0', [item('1')]],
        ['1_0', [item('ZZ9'), item('QQ')]],
        ['2_0', [item('R')]],
        ['3_0', [item('')]],            // blank is not a value that wants a colour
        ['4_0', [item('ZZ9')]],         // repeat -- the answer is a SET of values
      ]),
    };
    const miss = ctx.overlayUnlistedValues(layer);
    eq(miss.length, 2, `A8 unlisted count (got ${JSON.stringify(miss)})`);
    ok(miss.includes('ZZ9') && miss.includes('QQ'), 'A8b the unlisted values are named', JSON.stringify(miss));
    ok(!miss.includes('1') && !miss.includes('R'), 'A8c declared values are not listed', JSON.stringify(miss));
    ok(!miss.includes(''), 'A8d the blank value is not listed as missing');

    // FRESHNESS. Add one of them to the legend; the answer must shrink on the next call.
    // A count captured when the layer was added would still say 2 here.
    ctx.legend.push({ value: 'ZZ9', color: '#84cc16', desc: 'typed by the user just now' });
    const after = ctx.overlayUnlistedValues(layer);
    eq(after.length, 1, `A8e adding a legend row shrinks the answer (got ${JSON.stringify(after)})`);
    eq(ctx.legendColorForValue('ZZ9'), '#84cc16', 'A8f and that value is now coloured');
    ctx.legend.pop();
    eq(ctx.overlayUnlistedValues(layer).length, 2, 'A8g removing it again restores the answer');

    // A failed row has no items to judge.
    eq(ctx.overlayUnlistedValues({ failed: true, items: layer.items }).length, 0, 'A8h a failed layer answers empty');
    eq(ctx.overlayUnlistedValues({}).length, 0, 'A8i a layer with no items answers empty');

    // ── A9: THE CHIP. It exists only when there is something to say, and it says WHAT. ──
    const chip = ctx.overlayLegendChip(layer);
    ok(chip.includes('범례 밖 2종'), 'A9 the chip states how many values have no colour', chip);
    ok(chip.includes('ZZ9') && chip.includes('QQ'), 'A9b the chip names them', chip);
    ok(chip.includes('ov-chip'), 'A9c the chip reuses the existing chip class (no new UI region)', chip);
    eq(ctx.overlayLegendChip({ items: new Map([['0_0', [item('1')]]]) }), '',
      'A9d nothing is said when every value is declared');
    eq(ctx.overlayLegendChip({ failed: true }), '', 'A9e a failed row says nothing');
  }

  // ── A10: WIRING. The functions above are worth nothing if the renderer does not call them.
  //         (`drawOverlayMarkers` needs a live canvas + module state, so this reads its source.)
  {
    const draw = stripComments(sliceFunction(src, 'drawOverlayMarkers'));
    const nFill = countOf(draw, 'overlayMarkerFill(');
    const nPaint = countOf(draw, 'paintOverlayDot(');
    ok(nPaint >= 2, 'A10 both marker branches go through the painter', `${nPaint} call(s)`);
    ok(nFill === nPaint, 'A10b every painted dot asks the legend for its fill',
      `${nFill} fill lookup(s) for ${nPaint} dot(s) -- a branch is painting a colour of its own`);
    ok(!/fillStyle\s*=/.test(draw), 'A10c the marker code sets no fill of its own',
      'a second colour source has appeared inside the renderer');
    // 🔴 The remainder is the in-chip position, and the long-term plan puts defects there.
    //    Colouring must not have consumed it.
    ok(/it\.rx/.test(draw) && /it\.ry/.test(draw), 'A10d the in-chip remainder is still used',
      'the mm remainder was dropped while this path was being edited');

    const lookup = stripComments(sliceFunction(src, 'legendColorForValue'));
    ok(/legend\.find/.test(lookup), 'A10e the lookup reads the open map legend');
    ok(/declaredLegendRow\s*\(/.test(lookup), 'A10f the lookup falls back to the served default_legend');
    ok(!/pickUnusedColor|LEGEND_PALETTE|OVERLAY_COLORS/.test(lookup),
      'A10g the lookup never reaches for a palette', 'that is the invented colour');

    const list = stripComments(sliceFunction(src, 'renderOverlayList'));
    ok(/overlayLegendChip\s*\(/.test(list), 'A10h the overlay row shows the unlisted chip');

    // The chip counts against the LIVE legend, so a legend edit has to re-render the row.
    const legendTable = stripComments(sliceFunction(src, 'renderLegendTable'));
    // 🔴 The GUARD is asserted, not merely the call. `if (false) renderOverlayList();` still
    //    contains the call, and that is exactly how a refresh gets disabled without anyone
    //    noticing -- the chip then keeps the count it had before the user added the value.
    ok(/overlayLayers\.length[^\n]*renderOverlayList\s*\(/.test(legendTable),
      'A10i a legend edit refreshes the overlay rows whenever overlays exist',
      `renderLegendTable does not condition the refresh on overlayLayers: ${legendTable.slice(0, 400)}`);
  }

  // ── A11: COMPLEXITY BUDGET. No control was added for this feature. ──
  //         The overlay row's buttons are the whole interactive surface of this block.
  {
    const list = stripComments(sliceFunction(src, 'renderOverlayList'));
    const buttons = countOf(list, '<button');
    eq(buttons, 3, `A11 the overlay row still has exactly 3 buttons (import / toggle / delete)`);
    ok(!/<input|<select|type="checkbox"/.test(list), 'A11b and no input was added to it');
  }

  // ── A12: LOADING AN OVERLAY PUTS ITS VALUES IN THE LEGEND — the headline, end to end. ──
  //   USER REPORT 2026-08-04: "오버레이 값별 색은 아직 안된듯?" and "오버레이 로딩하면 doe
  //   쪽도 목록 추가되어야하는데". One defect from both ends. Everything A1-A11 scores was
  //   correct AND produced nothing, because `ensureLegendValues` had exactly two callers and
  //   neither was the display path: an overlay layer's values were never in the legend, so
  //   `legendColorForValue` truthfully answered "nobody declared this" for every one of them.
  //
  //   SCORED AS A TRANSITION, NOT A STATE. "the values are in the legend" passes on a
  //   fixture that seeded them by accident. The claim is that the SAME dot goes from
  //   unfilled to filled because the layer was loaded — so both ends are measured on one
  //   layer, in one sandbox, with the registration in between.
  {
    const c = ctx;                                  // the A1-A11 sandbox, legend as fixtured
    const item = (v) => ({ val: v, rx: 0.5, ry: 0.5 });
    // A layer carrying values NOBODY declares (`UNLISTED`), plus one the map already knows.
    const layer = {
      failed: false,
      items: new Map([
        ['0_0', [item(UNLISTED[0])]],
        ['1_0', [item(UNLISTED[1])]],
        ['2_0', [item('1')]],                       // already declared — must not be touched
        ['3_0', [item('')]],                        // blank was never a value wanting a colour
        ['4_0', [item(UNLISTED[0])]],               // repeat — a value is seeded ONCE
      ]),
    };

    const before = UNLISTED.map(v => c.legendColorForValue(v));
    const beforeFill = c.overlayMarkerFill(layer.items.get('0_0'));
    const legendSizeBefore = c.legend.length;
    const declaredColorOfOne = c.legendColorForValue('1');

    const seeded = c.ensureLegendValues(c.overlayLayerValues(layer), { vocab: true });

    const after = UNLISTED.map(v => c.legendColorForValue(v));
    const afterFill = c.overlayMarkerFill(layer.items.get('0_0'));
    const rows = seeded.map(v => c.legend.find(l => String(l.value) === v));

    // ① THE HEADLINE. Unfilled -> filled, on the same dot.
    eqDeep(before, [null, null], 'A12 before loading, the overlay values have no declared colour');
    eq(beforeFill, null, 'A12b so the dot is drawn unfilled — the state the user reported');
    ok(after.every(x => typeof x === 'string' && x.length > 0),
      'A12c after loading, every overlay value has a colour', JSON.stringify(after));
    ok(typeof afterFill === 'string' && afterFill.length > 0,
      'A12d ...and the SAME dot now fills', String(afterFill));
    // FIXTURE ACTIVITY: if the values had already been declared, A12c would pass on a
    // registration that never ran.
    ok(before.every(x => x === null) && after.every(x => x !== null),
      'A12e the transition is real (the fixture did not start already-declared)');

    // ② WHAT IS SEEDED, EXACTLY. Blanks are not values; repeats are not two rows; a value
    //    the map already declares is left alone (re-adding it would overwrite the user's
    //    colour with a palette pick).
    eqDeep(seeded.slice().sort(), UNLISTED.slice().sort(),
      'A12f exactly the undeclared, non-blank, deduped values are seeded');
    eq(c.legend.length, legendSizeBefore + UNLISTED.length,
      'A12g one legend row per seeded value, and none for the ones already there');
    eq(c.legendColorForValue('1'), declaredColorOfOne,
      'A12h an already-declared value keeps the colour the map gave it');

    // ③ NOTHING REACHES THE SERVER. The mark is what `buildLegendRegistryUpdates` drops on
    //    and what `applyRegistryRowsToLegend` takes back down at the next load, so it IS the
    //    "local only" guarantee. Asserted together with its seed: `reconcileVocabClaims`
    //    reads a marked row with NO seed as a rename and promotes it to a saved claim, so a
    //    mark without a seed would write to the server by a different door.
    eqDeep(rows.map(r => r && r.vocab === true), seeded.map(() => true),
      'A12i every seeded row is marked as vocabulary — this map does not claim it');
    eqDeep(rows.map(r => r && c.legendVocabularySeed.has(String(r.value))), seeded.map(() => true),
      'A12j ...and each carries its seed signature, so a later edit promotes it deliberately');
    ok(ctxSaves.length === 1,
      'A12k the LOCAL draft is written once, and nothing else is written',
      `${ctxSaves.length} save(s)`);

    // ④ THE IMPORT PATH IS NOT MARKED. Same primitive, opposite meaning: imported cells ARE
    //    painted onto this map, so their values are this map's own. If both callers marked,
    //    a real DOE plan would silently drop out of every save.
    const imported = c.ensureLegendValues(new Set(['IMPORTED-9']));
    const importedRow = c.legend.find(l => String(l.value) === 'IMPORTED-9');
    eqDeep(imported, ['IMPORTED-9'], 'A12l the import caller seeds too');
    ok(!importedRow.vocab, 'A12m ...but unmarked — a painted value is this map\'s own',
      `vocab=${importedRow && importedRow.vocab}`);

    // ⑤ WIRING. As with A10, the functions above are worth nothing if the display path does
    //    not call them — and this is precisely the call that was missing.
    const add = stripComments(sliceFunction(src, 'addOverlayLayer'));
    ok(/ensureLegendValues\s*\(\s*overlayLayerValues\s*\(\s*layer\s*\)\s*,\s*\{\s*vocab:\s*true\s*\}\s*\)/.test(add),
      'A12n adding a display layer registers that layer\'s values as vocabulary');
    // The GUARD, not merely the call: `if (false) ensureLegendValues(...)` still contains it.
    ok(!/if\s*\(\s*false\s*\)[^\n]*ensureLegendValues/.test(add),
      'A12o ...and the call is not disabled in place');
    ok(/seeded\.length\s*>\s*0[\s\S]{0,400}?recomputeLockedCells\s*\(/.test(add)
      && /seeded\.length\s*>\s*0[\s\S]{0,400}?renderLegendTable\s*\(/.test(add),
      'A12p ...and the same follow-up the import path does (locks + legend table) runs');
  }

  // ── A13: AN OVERLAY-SOURCED LEGEND ROW SAYS SO, AND NAMES ITS SOURCE ─────────────
  //   USER RULING 2026-08-04: overlay-sourced values are marked; they do not blend in as if
  //   they were the map's own. The legend describes THIS map's split registry, so a value the
  //   map does not contain, listed indistinguishably from ones it does, is a quiet false
  //   statement about the map.
  //
  //   DERIVED, NOT STORED, and that is what makes the edge cases fall out instead of needing
  //   their own code: the mark is a function of (this row's claim state, the layers loaded
  //   right now). Every case below is therefore scored as a key->value answer from that one
  //   function rather than as a rendering detail.
  {
    const c = ctx;
    const item = (v) => ({ val: v, rx: 0.5, ry: 0.5 });
    const L1 = { failed: false, sourceTable: 'eds_fail_map', sourceKey: 'LOT-C_06',
                 items: new Map([['0_0', [item('ZZ9')]], ['1_0', [item('F')]]]) };
    const L2 = { failed: false, sourceTable: 'core_defect_map', sourceKey: 'LOT-D_05',
                 items: new Map([['0_0', [item('ZZ9')]]]) };
    const LF = { failed: true, sourceTable: 'dt_map', sourceKey: 'GONE',
                 items: new Map([['0_0', [item('QQ')]]]) };
    c.overlayLayers = [L1, L2, LF];

    const rowOf = v => c.legend.find(l => String(l.value) === v);
    const zz9 = rowOf('ZZ9');                 // seeded by A12 as vocabulary, supplied by BOTH
    const own = rowOf('F');                   // the map's OWN registry row, also in L1
    const imported = rowOf('IMPORTED-9');     // seeded unmarked by the import caller
    const qq = rowOf('QQ');                   // vocabulary, but its only layer FAILED

    eq(c.legendOverlaySources(zz9).length, 2,
      'A13 a value carried by two overlays is ONE row that names both sources');
    ok(c.legendOverlaySources(zz9).join('|').includes('eds_fail_map · LOT-C_06')
      && c.legendOverlaySources(zz9).join('|').includes('core_defect_map · LOT-D_05'),
      'A13b ...and names each by TABLE and KEY, the same fact the layer row states',
      JSON.stringify(c.legendOverlaySources(zz9)));
    eqDeep(c.legendOverlaySources(own), [],
      'A13c a value the MAP declares is the map\'s own even when an overlay also carries it');
    eqDeep(c.legendOverlaySources(imported), [],
      'A13d an IMPORTED value is the map\'s own — importing paints it onto this map');
    eqDeep(c.legendOverlaySources(qq), [],
      'A13e a FAILED layer carries nothing, so it sources nothing');

    // FIXTURE ACTIVITY. If `F` were absent from L1, A13c would pass on a function that simply
    // never looks at the layers — the check has to be able to fail.
    ok(c.overlayLayerValues(L1).has('F'),
      'A13f the fixture really does put a map-owned value inside an overlay');

    // THE SHARP EDGE the ruling names: the user gives an overlay-sourced value a colour, then
    // removes the overlay. Assigning breaks the row's seed signature, `reconcileVocabClaims`
    // clears `vocab`, and from that instant the row is the map's own — so removing the layer
    // cannot take the colour away. Modelled by doing exactly that: change the row, clear the
    // mark the way the reconciler would, then drop the layers.
    zz9.color = '#abcdef';
    zz9.vocab = false;                        // what reconcileVocabClaims derives from the edit
    eqDeep(c.legendOverlaySources(zz9), [],
      'A13g once the user declares a colour, the row stops being overlay-sourced');
    c.overlayLayers = [];
    eq(c.legendColorForValue('ZZ9'), '#abcdef',
      'A13h ...and removing every overlay does not take that colour away');

    // The mark is TEXT in the value cell, not a control, and not sized below the token.
    const render = stripComments(sliceFunction(src, 'renderLegendTable'));
    ok(/legendOverlaySources\s*\(\s*item\s*\)/.test(render),
      'A13i the legend renderer asks for the mark');
    ok(/createElement\('span'\)/.test(render.slice(render.indexOf('legendOverlaySources'))),
      'A13j ...and renders it as a span — no button, no toggle, no new control');
    const marked = render.slice(render.indexOf('legendOverlaySources'),
                                render.indexOf('legendOverlaySources') + 900);
    ok(!/createElement\('(button|select|input)'\)/.test(marked),
      'A13k ...and adds no control of any kind alongside it');
    ok(!/fontSize\s*=\s*'0\.[0-7]/.test(marked),
      'A13l ...and does not shrink the type to make room');
  }

  return { fails, ran };
}

// ── Baseline ─────────────────────────────────────────────────────────────────────────────
const base = runAll(SRC0);
console.log('― N2 overlay markers coloured by the overlay value ―');
console.log(`legend authority: map row #10b981 for '1' (beats served #000000) · served #8b5cf6 for 'R' · ${UNLISTED.join('/')} undeclared -> no fill`);
console.log(`ASSERTIONS ${base.ran} ${base.fails.length}`);
if (base.fails.length) {
  console.error(`BASELINE RED -- ${base.fails.length} failed:`);
  base.fails.forEach(f => console.error(`  x ${f}`));
  process.exit(1);
}
console.log('baseline: all assertions passed');

// ── Mutation sweep ───────────────────────────────────────────────────────────────────────
// 🔴 Put the defect back and confirm the harness actually goes red. A green suite that cannot
//    fail has measured nothing. APPLIED and CAUGHT are reported separately because a mutation
//    whose pattern no longer matches is a SILENT hole, not a pass.
const MUTATIONS = [
  // ① The obvious wrong fix: when the legend has no answer, make one up. The canvas looks
  //    BETTER after this mutation, which is why it needs a machine to catch it.
  ['an undeclared value is given an invented colour',
    "return (declared && declared.color) ? String(declared.color) : null;",
    "return (declared && declared.color) ? String(declared.color) : '#6b7280';"],
  ['the served default_legend is never consulted',
    'const declared = declaredLegendRow(v);',
    'const declared = null;'],
  ['the open map legend is ignored (the site-wide row wins)',
    'const own = legend.find(item => String(item.value) === v);',
    'const own = null;'],
  // ② The rejected design: a multi-source cell answers with one value's colour.
  ['a representative value is chosen for a multi-source dot',
    'if (!Array.isArray(list) || list.length !== 1) return null;',
    'if (!Array.isArray(list) || list.length === 0) return null;'],
  // ③ The painter forgets that "no colour" is a state.
  ['the painter fills an undeclared dot anyway',
    'if (fill) { ctx.fillStyle = fill; ctx.fill(); }',
    'ctx.fillStyle = fill || ringColor; ctx.fill();'],
  ['the layer ring is dropped (which overlay a dot belongs to is lost)',
    "  ctx.strokeStyle = ringColor;\n  ctx.lineWidth = 0.8;",
    "  ctx.strokeStyle = '#ffffff';\n  ctx.lineWidth = 0.8;"],
  ['the white halo is dropped (a dot vanishes on a same-coloured cell)',
    "  ctx.strokeStyle = '#ffffff';\n  ctx.lineWidth = 1.6;",
    "  ctx.strokeStyle = ringColor;\n  ctx.lineWidth = 1.6;"],
  // ④ The renderer stops asking -- the regression back to one flat colour per layer.
  // Re-pointed 2026-08-04: the marker radius became per-axis (`r` -> `rx`/`ry`, `rr` -> `rrx`/
  // `rry`), so both anchors stopped matching. The sweep's own applied-count check is what said
  // so; a `find` that no longer matches is a silent hole, not a pass.
  ['the 1:1 branch reverts to the flat layer colour',
    'paintOverlayDot(ctx, cx, cy, rx, overlayMarkerFill(list), layer.color, ry);',
    'paintOverlayDot(ctx, cx, cy, rx, layer.color, layer.color, ry);'],
  ['the N:1 branch reverts to the flat layer colour',
    'paintOverlayDot(ctx, cx, cy, rrx, overlayMarkerFill([it]), layer.color, rry);',
    'paintOverlayDot(ctx, cx, cy, rrx, layer.color, layer.color, rry);'],
  // ⑤ The in-chip remainder is consumed while this path is edited.
  ['the in-chip remainder is discarded in the marker path',
    'const fx = it.rx / layer.seatChip.x - 0.5;\n        const fy = it.ry / layer.seatChip.y - 0.5;',
    'const fx = 0;\n        const fy = 0;'],
  // ⑥ The honest-absence report goes stale or goes wrong.
  // Re-pointed 2026-08-04: `overlayUnlistedValues` no longer walks the items itself (the walk
  // moved to `overlayLayerValues`, which the registration path also needs). The mutation had
  // to move with it -- a `find` string that no longer matches is a SILENT hole, and the sweep
  // reported exactly that on the first run after the refactor.
  ['every value is reported as unlisted',
    'return [...overlayLayerValues(o)].filter(v => !legendColorForValue(v));',
    'return [...overlayLayerValues(o)];'],
  // (7) The registration half (A12). Without these the colouring above is correct and inert.
  ['loading an overlay layer no longer registers its values (the reported defect, put back)',
    'const seeded = ensureLegendValues(overlayLayerValues(layer), { vocab: true });',
    'const seeded = []; /* MUTANT: the display path registers nothing */'],
  ['overlay values are registered as this map OWN plan (they would be pushed to the server)',
    "      if (asVocab) {\n        const row = legend.find(l => String(l.value) === sv);",
    "      if (false) {\n        const row = legend.find(l => String(l.value) === sv);"],
  ['the vocabulary mark is written without its seed (a later edit promotes it silently)',
    'if (row) { row.vocab = true; legendVocabularySeed.set(sv, legendRowSignature(row)); }',
    'if (row) { row.vocab = true; }'],
  ['a blank overlay cell is registered as a value',
    "    if (v === '') return;                       // \ube48 \uac12\uc740 \uc0c9\uc744 \uc6d0\ud55c \uc801\uc774 \uc5c6\ub2e4",
    '    /* MUTANT: blanks become legend rows */'],
  ['re-adding an already-declared value overwrites the colour the map gave it',
    'if (legend.some(item => String(item.value) === v)) return false;',
    'legend = legend.filter(item => String(item.value) !== v);'],
  // (8) The provenance mark (A13).
  ['an overlay-sourced legend row blends in as if it were the map own value',
    "  if (!item || item.vocab !== true) return [];",
    '  return []; /* MUTANT: nothing is ever marked */'],
  ['a value the MAP declares is demoted to overlay-sourced',
    "  if (!item || item.vocab !== true) return [];\n  const v = String(item.value);",
    '  const v = String(item.value);'],
  ['the mark says overlay but not WHICH overlay',
    "    .map(o => `${o.sourceTable} \u00b7 ${o.sourceKey}`);",
    "    .map(o => '\uc624\ubc84\ub808\uc774');"],
  // Re-pointed after it SURVIVED: `legendOverlaySources` used to re-check `!o.failed`, and
  // deleting that check changed no answer because `overlayLayerValues` already returns an
  // empty set for a failed layer. A guard a mutation cannot kill is a guard that is not doing
  // anything -- so the duplicate came out of the product and the mutation now aims at the one
  // implementation of "a failed layer carries nothing".
  ['a failed layer is treated as a source of values',
    '  if (!o || o.failed || !o.items) return out;',
    '  if (!o || !o.items) return out;'],
  ['the legend renderer never asks for the mark',
    '    const srcs = legendOverlaySources(item);',
    '    const srcs = []; /* MUTANT: derived and then discarded */'],
  ['a legend edit no longer refreshes the unlisted chip (it goes stale)',
    'if (overlayLayers.length > 0) renderOverlayList();',
    'if (false) renderOverlayList();'],
  ['the unlisted chip is dropped from the overlay row',
    '${overlayAlignChip(o)}${overlayFanChip(o)}${overlayLegendChip(o)}',
    '${overlayAlignChip(o)}${overlayFanChip(o)}'],
];

let applied = 0, caught = 0;
for (const [name, from, to] of MUTATIONS) {
  if (!SRC0.includes(from)) { console.log(`  ! NOT APPLIED (pattern gone): ${name}`); continue; }
  applied++;
  const mutated = SRC0.replace(from, to);
  let red = false, why = '';
  try {
    const r = runAll(mutated);
    red = r.fails.length > 0;
    why = r.fails[0] || '';
  } catch (e) { red = true; why = `threw: ${e.message}`; }
  if (red) { caught++; console.log(`  v CAUGHT: ${name}  (${why})`); }
  else console.log(`  x SURVIVED: ${name}`);
}
console.log(`mutations: ${caught}/${applied} caught (${MUTATIONS.length} declared)`);
if (applied !== MUTATIONS.length) { console.error('a declared mutation no longer applies -- the harness has a silent hole'); process.exit(1); }
if (caught !== applied) process.exit(1);
