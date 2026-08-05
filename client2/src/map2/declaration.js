// ═══════════════════════════════════════════════════════════════════════════════
// LAYER (3) DECLARATION -- "what does this map SAY its coordinate frame is",
// as a VALUE, with a PROVENANCE TOKEN ON EVERY AXIS.
//
// (See docs/spec/MAP_ALIGNMENT_SPEC.md 0.2 layer 3 and 0.3 step 1.)
//
// WHY THIS FILE EXISTS. There is no `frame` value in the client today. There is a DOM panel,
// and the question "what frame are we on" is re-answered from that panel at 15 separate
// blocks in `map_editor.js` (measured: 14 blocks matching `parseInt(el.grid*.value, 10) || N`
// at :603 :839 :883 :1943 :3252 :5575 :5695 :6262 :6346 :6419 :7586 :8026 :8517 :8736, plus
// `currentGeomSignature:10486` which reads the same controls as RAW STRINGS). Six of those
// blocks are named functions and they read FOUR DIFFERENT FIELD SETS. Divergence between
// them is not a hypothetical: see the DIVERGENCE section below, each item measured.
//
// WHAT IS NEW HERE, AND IT IS ONLY ONE THING: **every axis carries where its value came
// from.** The defect this closes is `map_overlay._rotation_of:235-239` and its client twin
// `frameFromMeta:8459` -- `Number(meta.rotation) || 0` answers `0` whether the key was
// missing, unreadable, defaulted by a generator, or genuinely chosen by a person, and a
// consumer cannot refuse what it cannot observe.
//
// 🔴 THE REASON THAT MATTERS IS NOT THE ONE IT LOOKS LIKE. Measured on `wafer_map_metadata`
//    (668 rows, read-only, 2026-08-05): every row stores all 13 axes with the right type, so
//    `absent` = 0 rows and `unparsable` = 0 rows -- nothing is collapsing for the reason the
//    name `|| 0` suggests. What is real is the OTHER collapse: **516 of 668 rows carry
//    `rotation: 0`, and on 516 of them nobody chose it** -- 320 were written by the
//    registrar (`map_meta_registrar.synthesize_grid_meta:168-196` writes `rotation: 0`,
//    `side: "front"`, `grid_y_invert: False` unconditionally) and the other 196 carry a
//    generator's literal zero with no marker at all. Calling those `declared` asserts
//    something nobody checked.
//
//    That is what `indeterminate` is for, and it is why `raw`/`legacy` cannot replace it:
//    client-side, raw `'0'` and raw `''` are distinguishable because the DOM hands you
//    strings, but a stored numeric `0` and a defaulted numeric `0` are the same bytes. The
//    token is the only place that distinction can live.
//
// VOCABULARY IS BORROWED, NOT INVENTED. The tokens below are the ones the physical axis
// already settled on in `server/map_overlay.py` (`GEOMETRY_DECLARED` /
// `GEOMETRY_AUTO_REGISTERED` / `GEOMETRY_ABSENT` / `GEOMETRY_UNPARSABLE`, plus
// `ORIENTATION_INDETERMINATE` and `GEOMETRY_ASSUMED`), which in turn says out loud that it
// shares its vocabulary with the client's `physDeclaration:1509` `source`. A second spelling
// of "declared" would be the exact defect class this round is about, so there is not one
// here. The count is not the invariant -- the SOURCE is: every token here exists on the
// server first, and none is minted on this side.
//
// CONSTRAINTS, ALL LOAD-BEARING:
//   - NO DOM. No `document`, no `el`, no `window`. Input is a plain `grid_metadata`-shaped
//     object. The layer that reads input boxes is the ASSEMBLY layer, and it is not this one.
//   - NO TRANSPORT.
//   - NO IMPURE IMPORTS. In particular NOT `../config.js`: its line 1 reads
//     `window.location.port` and its line 4 reads `import.meta.env`, so importing it would
//     make this module un-importable from node -- which would defeat the whole point (see
//     the harness note below). Config values are PASSED IN, via `opts.defaults`.
//   - NO MODULE-LEVEL MUTABLE STATE. Every binding in this file is `const` and every exported
//     object is `Object.freeze`d. NOTE the honest version of this claim: the `MODULE_STATE`
//     ceiling in `check_harnesses.mjs` is scoped to `map_editor.js` and never looks at this
//     file, so nothing here is machine-enforced -- the discipline is the point, not the
//     counter. An `export const` holding a mutable object would satisfy any such counter while
//     keeping the disease, so it is avoided on purpose rather than because something checks.
//
// AND THE REASON IT IS A SEPARATE FILE AT ALL. `map_editor.js:1826-1828` records that
// extracting a function breaks the harnesses that slice it as text -- three died that way in
// one round and `loadExistingMap`'s catch reported the wreckage as "0 cells loaded". Nearly
// every client harness reads source with `readFileSync` and evaluates it in `node:vm`. This
// module is written so that a harness can simply `import` it. That is step 0 of the plan,
// folded into step 1 because it cannot be separated.
// (No count here on purpose: a census in a source comment goes stale the moment somebody adds
//  a file, and three files carrying three different numbers is how this one already went
//  wrong. Counts live in a dated report.)
//
// ═══════════════════════════════════════════════════════════════════════════════
// DIVERGENCE FOUND WHILE BUILDING THIS -- reported, not silently reconciled.
//
// D1. `seatingSnapshot:1937-1938` reads dimensions through `gridDimNum` (frame-window aware);
//     `readGridFrameControls:6262`, `getVisualGridDimensions:6419`, `currentCoordFrame:7586`
//     and `currentFrame:8517` read `parseInt(el.gridCols.value, 10) || 10` directly. Inside a
//     `withPhysFrame` window the first would answer with the SOURCE map's dimensions and the
//     other four with the SCREEN's. It is not live today only because `seatingSnapshot:1935`
//     bails out (`if (physFrameOverride) return null`).
//
// D2. `readGridFrameControls` carries NO rotation and NO side, although its own header
//     (:6257) calls itself "the single reading of the grid frame controls". Its caller
//     `buildPushGridMetadata:6269` takes `currentRotation`/`currentSide` as separate
//     arguments. So the single reading covers 5 of 7 grid axes.
//
// D3. THREE SPELLINGS OF ONE NULL GUARD on `grid_y_invert`:
//       `readGridFrameControls:6266`  `el.gridYInvert.checked`                  <- THROWS if absent
//       `currentCoordFrame:7590`      `el.gridYInvert ? ... : false`
//       `currentFrame:8521`           `!!(el.gridYInvert && el.gridYInvert.checked)`
//
// D4. START DEFAULT DISAGREES ACROSS THE SEAM. Client `frameFromMeta:8462` and every raw
//     re-read default an absent `grid_start_x/y` to **0**; server `map_overlay._grid_of:249`
//     defaults it to **1**. On a meta with no start declared, the two sides are one cell
//     apart. That is why `startX`/`startY` carry a source token here: `absent` is the state
//     a consumer must be able to refuse, and neither default is "right" in isolation.
//
// D5. `currentGeomSignature:10486` compares RAW STRINGS. It cannot under-trigger (distinct
//     frames cannot share a string tuple), but it over-triggers on `"10"` vs `"10.0"`, and it
//     omits the auto-registered marker and `validDieResolveSeq` -- both of which ARE in
//     `getWaferBoundingBox`'s cache key (:1832). Out of scope for stage A; recorded.
//
// D6. `getVisualGridDimensions:6418` reads the module global `currentRotation`, so the six
//     sites that derive visual dimensions from an EXPLICIT rotation argument (:1567 :1626
//     :1813 :6326 :6801 :8662 -- :6801 says so in a comment) physically cannot call it. They
//     are not "bypassing the primitive"; the primitive is not parametric. `visualDimensions`
//     below takes the frame as an argument for exactly that reason.
// ═══════════════════════════════════════════════════════════════════════════════

// ── the six tokens ──────────────────────────────────────────────────────────────
// The first four are byte-identical to `server/map_overlay.py` (`GEOMETRY_DECLARED` /
// `GEOMETRY_AUTO_REGISTERED` / `GEOMETRY_ABSENT` / `GEOMETRY_UNPARSABLE`) and are UNCHANGED
// by this file. The fifth is that module's `ORIENTATION_INDETERMINATE`.
//
// 🔴 THE SIXTH IS `assumed`, ADDED 2026-08-05 (MAP_ALIGNMENT_SPEC 9.1). The rule was never
//    "there are five"; it is BORROW, DO NOT INVENT. The server grew a token, so this side
//    copies it. Adding a seventh that the server does not have is still forbidden.
//
//    Why it must be here even though this file can never PRODUCE it: `assumed` marks a meta
//    whose wafer spec was borrowed from the reference floor for the computation, and that
//    borrowed copy lives only in server memory -- it is never stored, so no meta this client
//    reads can carry the marker. But the TOKEN arrives as a string, on
//    `sources.maps[].geometry` and `.geometry_basis`. A vocabulary missing it does not make
//    the client silent; it makes the client sort an assumed geometry into some other bucket
//    while every server test stays green. That is the divergence this seam exists to catch.
export const DECLARED = 'declared';
export const AUTO_REGISTERED = 'auto_registered';
export const ABSENT = 'absent';
export const UNPARSABLE = 'unparsable';
export const INDETERMINATE = 'indeterminate';
export const ASSUMED = 'assumed';

export const DECLARATION_TOKENS = Object.freeze([
  DECLARED, AUTO_REGISTERED, ABSENT, UNPARSABLE, INDETERMINATE, ASSUMED]);

// 🔴 `assumed` IS NOT `declared`, AND IT IS NOT A REFUSAL EITHER. The server splits the
//    question in two and this side has to keep them split:
//      · "is this the map's own declaration?"  -> no  (`geometry_refusal` still refuses it)
//      · "is there a basis to compute on?"     -> yes (`geometry_computable` accepts it)
//    Folding it into `declared` re-creates the impersonation this whole vocabulary exists to
//    stop; folding it into the refusals says a scored map could not be scored.
export const COMPUTABLE_TOKENS = Object.freeze([DECLARED, ASSUMED]);

// ── THE TAINTING RULE ───────────────────────────────────────────────────────────
// One sentence:
//
//   🔴 A stored value equal to what the reader invents when the key is missing is not
//      evidence that anyone chose it.
//
// 🔴 AND ONE SENTENCE BOUNDING IT, WHICH IS THE HALF THAT IS EASY TO LOSE:
//
//      That inference is about ABSENT keys. It says nothing on an axis where no reader ever
//      had to invent anything, and it cannot say anything on an axis whose generator writes
//      a MEASUREMENT rather than a constant.
//
// So the value test runs on exactly the axes where `synthesize_grid_meta:168-196` writes a
// known constant -- `rotation` (0), `side` ("front"), `grid_y_invert` (False). Applied to a
// present, readable value on one of those three:
//
//   value != the invented value                  -> `declared`      (somebody moved it)
//   value == the invented value, marker present  -> `auto_registered`
//   value == the invented value, no marker       -> `indeterminate`
//
// On every OTHER axis the marker is the only witness:
//
//   marker present -> `auto_registered`      marker absent -> `declared`
//
// 🔴 WHY `grid_start_x/y` IS ON THE SECOND LIST AND NOT THE FIRST (lead PM ruling, 2026-08-05
//    -- this was an open question in the first cut of this file, and the ruling closes it):
//      (a) The registrar writes start as the OBSERVED MINIMUM (`map_meta_registrar.py:183`),
//          not a constant. A measurement can be any integer, so no value test can identify
//          one even in principle.
//      (b) The premise is empty regardless: measured on production, **0 of 668 rows lack
//          `grid_start_x/y`**. Every row states it, so nothing was ever invented, so "equals
//          what a reader would have invented" is answering a question nobody asked.
//    The earlier cut had start going `indeterminate` on a value match, and separately refused
//    to promote a marked `start_x: 37` to `declared`. The second instinct was right and this
//    is its general form; the first was the same mistake in the other direction.
//
// ⚠️ CONSEQUENCE, and it is a good one: the client/server disagreement about the start default
//    (client readers invent **0** -- `frameFromMeta:8462` and all 9 raw re-reads,
//    `parseInt(...) || 0`; `map_overlay._grid_of:249` invents **1**) NO LONGER TOUCHES
//    PROVENANCE. It used to invert the verdict on 660 of 668 rows. It still matters for
//    coordinate ARITHMETIC, which is why `opts.defaults` stays and why the disagreement is
//    boarded as its own item rather than closed.
//
// 🔴 THE INVENTED VALUE IS NOT WRITTEN DOWN TWICE. It is read back out of this module's own
//    defaults -- `noEvidenceValue()` below asks the reader what it produces for an absent
//    key. Hardcoding a second table of defaults here is precisely the two-spellings defect
//    this module exists to close, one layer down: the table and the readers would diverge
//    the first time somebody changed a default, and nothing would say so.
//    `frame.noEvidence` carries the table that was actually used, so a caller can check.

/** The axes whose stored VALUE can indicate provenance, because the registrar writes a known
 *  constant there. Everywhere else the registrar writes a measurement and only the marker
 *  speaks. This list IS the ruling above, in code. */
export const VALUE_CAN_INDICATE_PROVENANCE = Object.freeze(['rotation', 'side', 'invertY']);

/** The two axes the ruling names explicitly: measurements, so marker-only. */
export const START_AXES = Object.freeze(['startX', 'startY']);

/** The five axes the orientation vocabulary covers, in `map_overlay.py:424`'s order. */
export const ORIENTATION_AXES = Object.freeze([
  'rotation', 'side', 'invertY', 'startX', 'startY']);

/** The marker key. `server/map_overlay.py AUTO_REGISTERED_KEY`. */
export const AUTO_REGISTERED_KEY = 'auto_registered';

/**
 * The borrow marker. `server/map_overlay.py PHYS_ASSUMED_KEY` -- present only on the
 * in-memory copy the alignment scorer builds, and its value is `{table, map_id}`: WHERE the
 * wafer spec was borrowed from. Never stored, so no meta read here carries it; mirrored so
 * the port has no missing branch.
 */
export const PHYS_ASSUMED_KEY = 'phys_assumed_from';

/**
 * THE CHOICE MARKER, ADDED 2026-08-05. `map_editor.js buildPushGridMetadata` writes it when the
 * frame it is serialising came out of the coordinate-choice modal instead of out of the map:
 * `"data"` (📐 표준 — derived from this map's own cell bbox) or `"panel"` (⚙️ 현재 패널 — the
 * editor's left panel, which may be the previous map's residue).
 *
 * 🔴 IT IS A KEY, NOT A SEVENTH TOKEN, AND THE DISTINCTION IS THE WHOLE POINT. All six tokens
 *    answer one question -- "what kind of evidence is the VALUE ON THIS AXIS". "A human answered
 *    a modal" is not an answer to that question; it is a fact about the ROW. Checked one by one:
 *      · `declared`    -- a person really did choose, so in the strict sense this IS declared.
 *                         That is exactly why the token cannot carry the distinction: it is
 *                         already true of both the chosen frame and the map's own declaration.
 *      · `indeterminate` -- means "cannot be distinguished" (`map_overlay.py:511`), i.e. NO
 *                         evidence anybody chose. Here there is evidence. It would also make
 *                         `isFrameUsable` refuse cols/rows, which would shut the modal's own
 *                         purpose (`98b48e9`: let the map OPEN) back off.
 *      · `auto_registered` -- says the REGISTRAR wrote it. Stamping it on a panel frame would
 *                         also flip `geometryDeclaration` for a phys block a person measured,
 *                         and the server would refuse alignment quoting synthetic chip 1x1.
 *      · `absent` / `unparsable` -- the value is present and readable; both are false.
 *      · `assumed`     -- borrowed from the reference floor, server-memory only.
 *    So no token moves, `isFrameUsable` does not move, `geometryDeclaration` does not move. What
 *    the row gains is one observation: `frame.chosen`.
 *
 * 🔴 THE PRECEDENT IS `PHYS_ASSUMED_KEY`, not a token: present only when it happened, and its
 *    VALUE says where the numbers came from -- so that "if this assumption later turns out to be
 *    false, which decisions stood on it" stays answerable (`map_overlay.assume_phys_from:440`).
 *
 * ⚠️ NO SERVER TWIN YET, AND THAT IS STATED RATHER THAN HIDDEN. Every TOKEN here is copied from
 *    a server constant and none is minted on this side; that rule is about the vocabulary, and
 *    this file mints no token. The key is inert on the server -- `grid_metadata` is a JSON blob
 *    and no server reader consults unknown keys -- so it creates no divergence today. The
 *    server half (reading it, and refusing on it where that matters) is boarded, not done.
 */
export const FRAME_CHOSEN_KEY = 'frame_chosen_from';

/** The two things `frame_chosen_from` can say, in `resolveGridFrame`'s branch order. */
export const FRAME_CHOSEN_FROM = Object.freeze(['data', 'panel']);

/** The six physical keys, in the server's order (`map_overlay.py:265-266 PHYS_KEYS`). */
export const PHYS_KEYS = Object.freeze([
  'phys_wafer_dia', 'phys_chip_x', 'phys_chip_y',
  'phys_offset_x', 'phys_offset_y', 'phys_edge_margin',
]);

// ── the substituted values ──────────────────────────────────────────────────────
// These are NOT this module's opinion about geometry. They are a transcription of the
// numbers the shipped code already substitutes when nothing is declared, so that `legacy`
// (below) can reproduce today's behaviour byte for byte while `value` tells the truth.
//   cols/rows 10   -- `gridDimNum('cols', el.gridCols, 10)`      (map_editor.js:1937)
//   startX/Y  0    -- `parseInt(el.gridStartX.value, 10) || 0`   (map_editor.js:1943)
//                     NOTE: the server substitutes 1 here (D4). Callers that need the server's
//                     convention pass `{ startX: 1, startY: 1 }`; they do not edit this.
//   waferDia  300, chipX/Y 2.5, offsetX/Y 0.0, edgeMargin 3.0    (map_editor.js:1946-1951)
//   rotation  0, side 'front', invertY false                     (map_editor.js:8459-8461)
export const FRAME_DEFAULTS = Object.freeze({
  cols: 10, rows: 10,
  startX: 0, startY: 0,
  invertY: false,
  rotation: 0,
  side: 'front',
  waferDia: 300,
  chipX: 2.5, chipY: 2.5,
  offsetX: 0.0, offsetY: 0.0,
  edgeMargin: 3.0,
});

/** meta key -> frame axis name. The only place the two spellings are related. */
export const AXIS_META_KEY = Object.freeze({
  cols: 'grid_cols', rows: 'grid_rows',
  startX: 'grid_start_x', startY: 'grid_start_y',
  invertY: 'grid_y_invert',
  rotation: 'rotation', side: 'side',
  waferDia: 'phys_wafer_dia',
  chipX: 'phys_chip_x', chipY: 'phys_chip_y',
  offsetX: 'phys_offset_x', offsetY: 'phys_offset_y',
  edgeMargin: 'phys_edge_margin',
});

export const AXIS_NAMES = Object.freeze(Object.keys(AXIS_META_KEY));

/** Rotations the transform stack actually implements. 45 is a number, not a rotation. */
export const ROTATIONS = Object.freeze([0, 90, 180, 270]);
export const SIDES = Object.freeze(['front', 'back']);

// ── raw presence ────────────────────────────────────────────────────────────────
// One spelling of "did the meta say anything at all". Empty string counts as silence, which
// is what `physDeclaration:1511` and `map_overlay.geometry_declaration:346` both already do.
function isSilent(raw) {
  return raw === undefined || raw === null
    || (typeof raw === 'string' && raw.trim() === '');
}

/**
 * One axis, as a fact rather than a number.
 *
 *   value    -- what the meta actually declares, or the substituted default when it does not.
 *   source   -- one of the four tokens. THIS is the thing that did not exist before.
 *   raw      -- exactly what was in the meta (undefined when silent), for error text.
 *   legacy   -- what the SHIPPED code returns for this axis today.
 *
 * `legacy` is not decoration. `physNum`/`gridDimNum` end in `return v || dflt`, so a
 * DECLARED ZERO is folded into the default: `grid_cols: 0` is read as 10, and the resulting
 * mask lives in an index space the reference never declared. With both fields present, that
 * bug has a name a test can assert on -- `value !== legacy` -- instead of being invisible.
 */
function axis(name, raw, value, source, legacy) {
  return Object.freeze({ name, raw, value, source, legacy });
}

// ── READING A VALUE: NORMALISE OR REFUSE. NEVER PASS THROUGH. ───────────────────
//
// 🔴 THE DIRECTION IS THE DEFECT, NOT THE CASES. The first cut of this file read values with
//    `parseInt` / `parseFloat` / `Number` and reported whatever came back as `declared`. Those
//    three are LENIENT: `parseInt('3abc')` is 3, `parseFloat('1.2.3')` is 1.2, `Number('')`
//    is 0. So the client accepted input the server refuses and stamped it `declared` -- "a
//    person chose this" -- on nine distinct malformed shapes (contract lane, 2026-08-05,
//    `contracts/map2_seam/` `orientation_divergence`). Every one of them shipped a value the
//    server would have rejected, and a per-case patch would have left the tenth.
//
//    So the readers below are strict, and they are strict in the SAME WAY the server is: the
//    server's readers are literally `int(raw)` and `float(raw)` (`map_overlay.py:426-460`),
//    and Python's `int`/`float` REFUSE what JavaScript's parsers happily truncate. The two
//    coercions here reproduce that refusal. This is not the client copying the server's
//    table -- it is both sides implementing "a value we cannot read is not a declaration".
//
// ⚠️ `legacy` DOES NOT GET STRICTER, and that is deliberate. `legacy` models what the SHIPPED
//    editor does (`parseInt(el.gridCols.value, 10) || 10`), which is lenient, and it is the
//    only thing seam parity is scored against. Making it strict here would rewrite history
//    and turn the parity oracle green by moving the oracle. So each reader computes the two
//    answers independently: `value`/`source` strictly, `legacy` exactly as before.

/** Python `int(x)`: truncates numbers toward zero, and REFUSES a string that is not a plain
 *  integer -- `int('3.7')` and `int('3abc')` both raise, where `parseInt` returns 3. */
function toPyInt(raw) {
  if (typeof raw === 'boolean') return raw ? 1 : 0;         // Python: int(True) == 1
  if (typeof raw === 'number') return Number.isFinite(raw) ? Math.trunc(raw) : null;
  if (typeof raw === 'string') {
    const t = raw.trim();
    return /^[+-]?\d+$/.test(t) ? Number(t) : null;
  }
  return null;
}

/** Python `float(x)`: refuses trailing garbage, where `parseFloat` truncates to it. */
function toPyFloat(raw) {
  if (typeof raw === 'boolean') return raw ? 1 : 0;
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : null;
  if (typeof raw === 'string') {
    const t = raw.trim();
    if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(t)) return null;
    const n = Number(t);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/** What the shipped editor's lenient DOM read produces. Unchanged on purpose (see above). */
function legacyInt(raw, dflt) {
  const n = typeof raw === 'number' ? raw : parseInt(String(raw), 10);
  return Number.isFinite(n) ? (n || dflt) : dflt;
}
function legacyFloat(raw, dflt) {
  const n = typeof raw === 'number' ? raw : parseFloat(String(raw));
  return Number.isFinite(n) ? (n || dflt) : dflt;
}

function intAxis(name, raw, dflt) {
  const legacy = legacyInt(raw, dflt);
  if (isSilent(raw)) return axis(name, undefined, dflt, ABSENT, legacy);
  const n = toPyInt(raw);
  if (n === null) return axis(name, raw, dflt, UNPARSABLE, legacy);
  return axis(name, raw, n, DECLARED, legacy);
}

function floatAxis(name, raw, dflt) {
  const legacy = legacyFloat(raw, dflt);
  if (isSilent(raw)) return axis(name, undefined, dflt, ABSENT, legacy);
  const n = toPyFloat(raw);
  if (n === null) return axis(name, raw, dflt, UNPARSABLE, legacy);
  return axis(name, raw, n, DECLARED, legacy);
}

/**
 * Rotation. THE headline axis. `_rotation_of:235-239` and `frameFromMeta:8459` both answer 0
 * for a missing key, an unreadable key and a stored zero alike. Measured on production, the
 * first two never happen and the third is 516 of 668 rows -- and on all 516 nobody chose it
 * (320 registrar-written, 196 a generator's literal zero). The tainting rule above is what
 * separates those from a person who actually set rotation to 0; the NUMBER this function
 * returns is unchanged either way.
 */
function rotationAxis(raw, dflt) {
  const legacy = Number.isFinite(Number(raw)) ? (Number(raw) || dflt) : dflt;
  if (isSilent(raw)) return axis('rotation', undefined, dflt, ABSENT, legacy);
  const i = toPyInt(raw);
  if (i === null) return axis('rotation', raw, dflt, UNPARSABLE, legacy);
  // NORMALISE. Python's `%` never returns a negative, so `-90 % 360` is 270 there and -90
  // here unless this is written out. That difference is not cosmetic: `visualDimensions`
  // tests `rot === 90 || rot === 270`, so an un-normalised -90 lays the grid out UNROTATED
  // while the server transforms a quarter turn -- a 45x39 map drawn 45 wide and read 39 wide.
  const n = ((i % 360) + 360) % 360;
  // THEN REFUSE. `ROTATIONS` is exported two screens up and says 45 is a number, not a
  // rotation. Not consulting it here was a second spelling of the domain INSIDE ONE MODULE:
  // the file stated the domain and its parser ignored it, so 45 went downstream `declared`
  // and `visualDimensions` silently treated it as 0.
  if (!ROTATIONS.includes(n)) return axis('rotation', raw, dflt, UNPARSABLE, legacy);
  return axis('rotation', raw, n, DECLARED, legacy);
}

/**
 * Side. `meta.side === 'back' ? 'back' : 'front'` (map_editor.js:8461) answers 'front' for
 * absent, for 'BACK', and for 'rear' alike -- the same collapse as rotation, one axis over.
 * A value outside the two-word vocabulary is `unparsable`, not a silent 'front'.
 */
function sideAxis(raw, dflt) {
  if (isSilent(raw)) return axis('side', undefined, dflt, ABSENT, dflt);
  const s = String(raw);
  const legacy = s === 'back' ? 'back' : 'front';
  if (!SIDES.includes(s)) return axis('side', raw, dflt, UNPARSABLE, legacy);
  return axis('side', raw, s, DECLARED, legacy);
}

/**
 * grid_y_invert. `!!meta.grid_y_invert` (map_editor.js:8463) is truthiness, and truthiness
 * reads the STRING `"false"` as true. Only real booleans and the two obvious string
 * spellings are `declared` here; anything else is `unparsable` and carries the legacy
 * truthiness result so the divergence stays visible instead of being resolved by this file.
 */
function boolAxis(name, raw, dflt) {
  const legacy = !!raw;                          // `!!meta.grid_y_invert` (map_editor.js:8463)
  if (isSilent(raw)) return axis(name, undefined, dflt, ABSENT, legacy);
  // ONLY a real truth value counts. The first cut also accepted the STRINGS 'true'/'false',
  // and that was the whole defect in miniature: `'true'` became `{true, declared}` here and
  // `{false, unparsable}` on the server, so the y mirror was applied by one side and not the
  // other -- EVERY row of the map reflected between the two answers. A string is not a
  // boolean; a writer that stores one has not declared anything readable.
  if (typeof raw === 'boolean') return axis(name, raw, raw, DECLARED, legacy);
  if (typeof raw === 'number' && (raw === 0 || raw === 1)) {
    return axis(name, raw, raw === 1, DECLARED, legacy);
  }
  return axis(name, raw, dflt, UNPARSABLE, legacy);
}

/**
 * The whole-meta physical verdict -- a straight port of
 * `server/map_overlay.geometry_declaration:337-355`, token for token and, critically, in the
 * same ORDER: the marker is read BEFORE the values, because the marker means "the values
 * below are not evidence" and reading the values first would make it inert.
 *
 * This is deliberately NOT merged with the per-axis sources. The server keeps the two apart
 * for a stated reason (`_phys_signature:270`: "this function does not ask about provenance"),
 * and merging them would delete the synthetic geometry's INTENDED answer.
 */
export function geometryDeclaration(meta) {
  const m = (meta && typeof meta === 'object') ? meta : {};
  // 🔴 The borrow marker is read FIRST, before the auto-registration marker, because a
  //    borrowed copy has already overwritten the six values underneath -- they are no longer
  //    the registrar's. This client cannot construct such a meta (the copy lives in server
  //    memory and is never stored), and the branch is here anyway: this function's contract
  //    is that it is a PORT, in the same order, and a port with a missing branch is a port
  //    that answers differently the first time the other side hands it one.
  if (m[PHYS_ASSUMED_KEY]) return ASSUMED;
  if (m[AUTO_REGISTERED_KEY] === true) return AUTO_REGISTERED;
  for (const k of PHYS_KEYS) {
    const v = m[k];
    if (isSilent(v)) return ABSENT;
    const n = typeof v === 'number' ? v : parseFloat(String(v));
    if (!Number.isFinite(n)) return UNPARSABLE;
  }
  return DECLARED;
}

/**
 * Visual (on-canvas) dimensions. **Derived from the frame passed in**, never from a global.
 *
 * The rule is one line and it is copied verbatim from the eleven places that already spell
 * it (`map_editor.js:886-887` and siblings): a quarter turn swaps the axes. What is new is
 * only that the rotation arrives as an argument, which is what lets the six frame-parametric
 * call sites (:1567 :1626 :1813 :6326 :6801 :8662) share it -- they could not call
 * `getVisualGridDimensions:6418` because that one reads `currentRotation` off the module.
 *
 * Accepts either a Frame from `frameFromDeclaration` or a bare `{cols, rows, rotation}`.
 */
export function visualDimensions(frame) {
  const f = frame || {};
  const cols = f.cols;
  const rows = f.rows;
  const rot = Number(f.rotation) || 0;
  const quarter = (rot === 90 || rot === 270);
  return Object.freeze({
    visualCols: quarter ? rows : cols,
    visualRows: quarter ? cols : rows,
  });
}

/**
 * `getVisualGridDimensions` derives from the LEGACY numbers, because that is the pair the
 * canvas loop actually walks today. Kept separate rather than switching `visualDimensions`
 * on a flag: a caller must say which of the two it means.
 */
export function visualDimensionsLegacy(frame) {
  const f = frame || {};
  return visualDimensions({
    cols: f.axes ? f.axes.cols.legacy : f.cols,
    rows: f.axes ? f.axes.rows.legacy : f.rows,
    rotation: f.axes ? f.axes.rotation.legacy : f.rotation,
  });
}

/**
 * THE ENTRY POINT. `grid_metadata`-shaped plain object in, frozen Frame out.
 *
 * @param {object|null} meta   a `grid_metadata` blob. Not mutated, not retained.
 * @param {object}      [opts]
 * @param {object}      [opts.defaults] overrides for `FRAME_DEFAULTS`. This is how config
 *                                      reaches this module -- it does NOT import config.js.
 *
 * Returns a frozen record with, for every axis, BOTH a plain value AND `axes[name]` carrying
 * the source token.
 *
 * 🔴 `frame.<axis>` IS NOT A DROP-IN FOR WHAT THE SIX EXISTING FUNCTIONS RETURN. An earlier
 *    version of this comment said it was, and that was wrong in the one way that matters:
 *    `frame.<axis>` is `axes[<axis>].value`, the DECLARED value, while the six shipped
 *    functions return the value after the `|| dflt` fold. The drop-in is `frame.legacy.*`,
 *    and it is the only thing parity is scored against.
 *
 *    The difference is the entire reason this module exists -- on a meta declaring
 *    `grid_cols: 0`, `frame.cols` is 0 and `frame.legacy.cols` is 10 -- so sourcing the flat
 *    fields from `legacy` would delete the module's purpose while leaving every parity
 *    assertion green. The harness pins `frame.<axis> === frame.axes.<axis>.value` on every
 *    axis of every production shape, and pins the two apart on a declared zero, precisely to
 *    make that swap fail.
 *
 * Never returns null: a meta with no dimensions is a frame whose `cols.source` is
 * `absent`, which is strictly more information than `frameFromMeta:8455`'s `return null`.
 * `isFrameUsable()` below is the refusal, and it is a separate decision on purpose --
 * layer 3 declares, it does not judge (MAP_ALIGNMENT_SPEC 0.2).
 */
export function frameFromDeclaration(meta, opts) {
  const m = (meta && typeof meta === 'object') ? meta : null;
  const d = Object.assign({}, FRAME_DEFAULTS, (opts && opts.defaults) || {});
  const get = (key) => (m ? m[key] : undefined);

  const autoRegistered = !!(m && m[AUTO_REGISTERED_KEY] === true);

  const axes = {
    cols: intAxis('cols', get('grid_cols'), d.cols),
    rows: intAxis('rows', get('grid_rows'), d.rows),
    startX: intAxis('startX', get('grid_start_x'), d.startX),
    startY: intAxis('startY', get('grid_start_y'), d.startY),
    invertY: boolAxis('invertY', get('grid_y_invert'), d.invertY),
    rotation: rotationAxis(get('rotation'), d.rotation),
    side: sideAxis(get('side'), d.side),
    waferDia: floatAxis('waferDia', get('phys_wafer_dia'), d.waferDia),
    chipX: floatAxis('chipX', get('phys_chip_x'), d.chipX),
    chipY: floatAxis('chipY', get('phys_chip_y'), d.chipY),
    offsetX: floatAxis('offsetX', get('phys_offset_x'), d.offsetX),
    offsetY: floatAxis('offsetY', get('phys_offset_y'), d.offsetY),
    edgeMargin: floatAxis('edgeMargin', get('phys_edge_margin'), d.edgeMargin),
  };

  // ── APPLY THE TAINTING RULE (see THE TAINTING RULE, above) ────────────────────
  //
  // The invented value is asked of the reader, not restated: `noEvidence[name]` is exactly
  // what this function produces for a missing key, because that is what `d` is.
  //
  // 🔴 THE VALUE TEST ONLY RUNS ON AXES WHERE THE REGISTRAR WRITES A KNOWN CONSTANT.
  //    `synthesize_grid_meta:168-196` writes rotation / side / y_invert as unconditional
  //    constants, so for those three a stored value CAN be compared against what a reader
  //    would have invented and the comparison means something. Everywhere else the registrar
  //    writes a MEASUREMENT -- `grid_start_x/y` is the observed minimum
  //    (`map_meta_registrar.py:183`), dimensions and diameter come off the same bbox -- and a
  //    measurement can be any integer, so no value test can identify it even in principle.
  //    On those axes the marker is the ONLY evidence: marked -> `auto_registered`, unmarked ->
  //    `declared`, whatever the value.
  //
  // ⚠️ AND THE INFERENCE HAS A PREMISE THAT IS EMPTY FOR START ANYWAY. "This equals what a
  //    reader would have invented" only carries information when a reader might have had to
  //    invent something. Measured on production: 0 of 668 rows lack `grid_start_x/y` -- every
  //    row states it explicitly, so nothing was ever invented and the comparison is answering
  //    a question nobody asked. (Lead PM ruling, 2026-08-05.)
  //
  //    Consequence worth stating out loud: the client/server disagreement about the start
  //    default (0 vs 1) no longer touches provenance at all. It still matters for coordinate
  //    ARITHMETIC, which is why `opts.defaults` stays, and it is boarded separately.
  //
  //    A marked map carrying `rotation: 90` is still `declared`, not `auto_registered` -- the
  //    editor inherited the marker and turned the map (`map_editor.js:6292`), and the
  //    registrar demonstrably never writes 90.
  //
  // `indeterminate` therefore lands on rotation / side / invertY only. Widening it to the
  // pitch axes would change what `geometryDeclaration` means, and that token block is shared
  // with the server.
  const noEvidence = {};
  for (const name of AXIS_NAMES) noEvidence[name] = d[name];

  for (const name of AXIS_NAMES) {
    const a = axes[name];
    if (a.source !== DECLARED) continue;              // absent / unparsable are already final
    let source = DECLARED;
    if (!VALUE_CAN_INDICATE_PROVENANCE.includes(name)) {
      // Measurement axes (start, dimensions, pitch, diameter): the marker is the only witness.
      if (autoRegistered) source = AUTO_REGISTERED;
    } else {
      const evidenceFree = Object.is(a.value, noEvidence[name]);
      if (autoRegistered) source = evidenceFree ? AUTO_REGISTERED : DECLARED;
      else if (evidenceFree) source = INDETERMINATE;
    }
    if (source !== DECLARED) axes[name] = axis(name, a.raw, a.value, source, a.legacy);
  }

  const frozenAxes = Object.freeze(axes);
  const flat = {};
  for (const name of AXIS_NAMES) flat[name] = frozenAxes[name].value;

  const legacy = {};
  for (const name of AXIS_NAMES) legacy[name] = frozenAxes[name].legacy;
  const legacyVis = visualDimensions(legacy);
  Object.assign(legacy, legacyVis);

  const vis = visualDimensions(flat);

  return Object.freeze(Object.assign(flat, {
    axes: frozenAxes,
    legacy: Object.freeze(legacy),
    visualCols: vis.visualCols,
    visualRows: vis.visualRows,
    autoRegistered,
    // 🔴 WHETHER THE CHOICE HAPPENED -- the frame half's provenance, and the reason it is a
    //    field next to `autoRegistered` rather than a token inside `axes` (see FRAME_CHOSEN_KEY).
    //    `null` on every meta that does not carry the marker, which is every meta written before
    //    2026-08-05 and every genuinely declared one, so no verdict anywhere moves.
    //    The raw string is exposed, not a boolean: WHICH choice was made is the half that lets a
    //    later reader tell a bbox-derived frame from a panel frame, and folding it to `true`
    //    would delete exactly that.
    chosen: (m && !isSilent(m[FRAME_CHOSEN_KEY])) ? String(m[FRAME_CHOSEN_KEY]) : null,
    geometry: geometryDeclaration(m),
    present: !!m,
    // The invented values this frame was scored against. Exposed so a caller can see WHICH
    // convention produced an `indeterminate` -- the seam disagrees about start (see THE
    // TAINTING RULE), and a verdict whose basis is invisible is the thing this module is for.
    noEvidence: Object.freeze(noEvidence),
  }));
}

/**
 * What the reader invents for `axis` when the key is missing -- asked of the reader itself.
 * This is the anti-drift device: if a default moves, this moves with it, because it is the
 * same code path a real absent key takes.
 */
export function noEvidenceValue(axisName, opts) {
  return frameFromDeclaration({}, opts).axes[axisName].value;
}

/** Every axis whose source is one of `tokens`. Used by refusal text and by the harness. */
export function axesWithSource(frame, tokens) {
  const want = new Set([].concat(tokens));
  if (!frame || !frame.axes) return Object.freeze([]);
  return Object.freeze(AXIS_NAMES.filter(n => want.has(frame.axes[n].source)));
}

/**
 * Dimension domain. Transcribed from `map_editor.js:8499 frameDimBounds` and from
 * `map_editor.html`'s `#grid-cols`/`#grid-rows` `min="1" max="100"`. Integers only and NOT
 * clamped -- clamping builds the mask in an index space the reference never declared, which
 * is the "screen looks fine, values are wrong" state this domain exists for.
 */
export function frameDimBounds() { return Object.freeze({ min: 1, max: 100 }); }

/**
 * Is this frame usable as a coordinate basis? Returns `{ ok, reasons }` -- reasons are
 * TOKENS, not sentences. Human wording is applied once, at the place a human reads it
 * (the same discipline as `_GEOMETRY_REFUSAL_TEXT` in `map_overlay.py:319`); a second
 * judgement dressed as a message is how two verdicts start disagreeing.
 */
export function isFrameUsable(frame) {
  const reasons = [];
  if (!frame || !frame.axes) return Object.freeze({ ok: false, reasons: Object.freeze(['no_frame']) });
  const b = frameDimBounds();
  for (const k of ['cols', 'rows']) {
    const a = frame.axes[k];
    if (a.source !== DECLARED) reasons.push(`${k}:${a.source}`);
    else if (!Number.isInteger(a.value) || a.value < b.min || a.value > b.max) {
      reasons.push(`${k}:out_of_domain`);
    }
  }
  if (frame.axes.rotation.source === DECLARED && !ROTATIONS.includes(frame.axes.rotation.value)) {
    reasons.push('rotation:out_of_domain');
  }
  if (frame.axes.side.source === UNPARSABLE) reasons.push('side:unparsable');
  return Object.freeze({ ok: reasons.length === 0, reasons: Object.freeze(reasons) });
}

/**
 * Axes where the shipped fold changed the number -- i.e. where a DECLARED value is not the
 * value the running client uses. Today that is exactly the `|| dflt` on a declared zero.
 * Empty on a healthy meta; anything in it is a live "screen is fine, value is wrong".
 */
export function foldedAxes(frame) {
  if (!frame || !frame.axes) return Object.freeze([]);
  return Object.freeze(AXIS_NAMES.filter(n => {
    const a = frame.axes[n];
    return a.source === DECLARED && a.value !== a.legacy;
  }));
}
