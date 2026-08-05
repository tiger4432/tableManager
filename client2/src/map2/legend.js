// ═══════════════════════════════════════════════════════════════════════════════
// LEGEND -- value to colour and label. PURE. NO DOM, NO CANVAS, NO TRANSPORT,
// NO MODULE-LEVEL MUTABLE STATE.
//
// WHAT THE CONTRACT IS (learned from the legacy editor's behaviour, NOT transcribed from its
// implementation -- transcribing would carry its module globals across with it):
//
//   1. THE LEGEND IS THE ONLY COLOUR SOURCE. There is no second colour dictionary, and this
//      module never invents a colour. The legacy editor keeps a `pickUnusedColor()` that
//      invents one, and deliberately does not call it from the value lookup; the same rule is
//      enforced structurally here by not having such a function at all.
//
//   2. THERE ARE EXACTLY TWO DECLARATION SOURCES, IN ORDER: the map's own rows first, then the
//      served default. Both are supplied by the caller. Neither answering is a THIRD outcome,
//      not a fallback -- see 3.
//
//   3. 🔴 `null` IS A FACT, NOT A MISSING RETURN VALUE. `colorOf` returning null means NOBODY
//      DECLARED A COLOUR FOR THIS VALUE. A renderer must draw that absence (an unfilled mark);
//      substituting a plausible colour dresses an undeclared value in a confident one, the
//      screen looks fine, and the meaning is wrong. That is the exact failure class this
//      domain exists to stop, so the distinction is carried in the return type.
//
//   4. VALUES ARE COMPARED AS STRINGS. A legend row declaring `1` and a cell holding `'1'` are
//      the same value; a cell holding `1.0` is NOT, because the declaration is a vocabulary
//      entry and not a number. `''`, `null` and `undefined` are not values at all.
//
//   5. NO RATIO, NO PERCENTAGE, ANYWHERE. Not as a field, not in a label, not in a tooltip.
//      There is no count-of-cells function in this module either: a legend describes the
//      vocabulary, and mixing tallies into it is how a share ends up rendered next to a swatch.
// ═══════════════════════════════════════════════════════════════════════════════

/** Nobody declared a colour for this value. The screen says this, not a guessed swatch. */
export const NO_COLOUR_DECLARED = '색 선언 없음';

/** A legend row with no description. Nominal, not a sentence. */
export const NO_LABEL_DECLARED = '설명 없음';

/**
 * Is `v` a value at all? Empty string, null and undefined are absences, and an absence must
 * never match a declared row -- a legend row declaring the empty string would otherwise colour
 * every cell whose value failed to load.
 */
export function isValue(v) {
  if (v === null || v === undefined) return false;
  if (typeof v === 'boolean') return false;
  return String(v) !== '';
}

/** The one spelling of "what key does this value have in the legend". */
export function valueKey(v) {
  return isValue(v) ? String(v) : null;
}

/**
 * Rows -> frozen, de-duplicated, declaration-ordered rows.
 *
 * FIRST DECLARATION WINS on a duplicate value. The alternative (last wins) makes an appended
 * row silently retint an existing one, and appending is what the auto-add path does.
 *
 * A row whose `color` is absent is KEPT, with `color: null`. Dropping it would lose the
 * label, and "this value is in the vocabulary but has no colour" is a state the screen has
 * to be able to show.
 */
export function normalizeLegend(rows) {
  const out = [];
  const seen = new Set();
  for (const raw of Array.isArray(rows) ? rows : []) {
    if (!raw || typeof raw !== 'object') continue;
    const key = valueKey(raw.value);
    if (key === null || seen.has(key)) continue;
    seen.add(key);
    const colour = typeof raw.color === 'string' && raw.color !== '' ? raw.color : null;
    const label = typeof raw.desc === 'string' && raw.desc !== '' ? raw.desc : null;
    out.push(Object.freeze({ value: key, label, color: colour }));
  }
  return Object.freeze(out);
}

/**
 * The two declaration sources, resolved into one lookup. Own rows shadow the served default
 * per value, not wholesale: a map that declares a colour for `1` but not for `E1` keeps the
 * served `E1`.
 *
 * @param {Array} own      the open map's own legend rows
 * @param {Array} fallback the served default legend
 * @returns frozen {rows, byValue:Map, ownCount, fallbackCount}
 */
export function resolveLegend(own, fallback) {
  const ownRows = normalizeLegend(own);
  const fallbackRows = normalizeLegend(fallback);
  const byValue = new Map();
  for (const r of ownRows) byValue.set(r.value, Object.freeze({ ...r, source: 'own' }));
  for (const r of fallbackRows) {
    if (!byValue.has(r.value)) byValue.set(r.value, Object.freeze({ ...r, source: 'default' }));
  }
  return Object.freeze({
    rows: Object.freeze([...byValue.values()]),
    byValue,
    ownCount: ownRows.length,
    fallbackCount: fallbackRows.length,
  });
}

/** The declared row for this value, or null. Null means nobody declared it. */
export function rowOf(legend, value) {
  const key = valueKey(value);
  if (key === null || !legend || !legend.byValue) return null;
  return legend.byValue.get(key) || null;
}

/**
 * 🔴 THE COLOUR, OR `null` MEANING NOBODY DECLARED ONE. Never a default, never invented.
 * A row that exists with no colour also answers `null` -- the value is in the vocabulary but
 * its colour is not declared, and both absences are the same instruction to the renderer.
 */
export function colorOf(legend, value) {
  const row = rowOf(legend, value);
  return row && row.color ? row.color : null;
}

/** The declared label, or null. `null` is the same kind of fact as in `colorOf`. */
export function labelOf(legend, value) {
  const row = rowOf(legend, value);
  return row && row.label ? row.label : null;
}

/**
 * The legend strip, as data. One entry per declared value.
 *
 * `colorKnown` and `labelKnown` are STATED rather than left for the renderer to infer from a
 * null, so a strip that renders `NO_COLOUR_DECLARED` as text cannot be mistaken for one that
 * renders a swatch of an invented colour.
 *
 * No tallies here. A legend entry carries no count, and therefore no share.
 */
export function legendEntries(legend) {
  const rows = (legend && legend.rows) || [];
  return Object.freeze(rows.map(r => Object.freeze({
    value: r.value,
    label: r.label === null ? NO_LABEL_DECLARED : r.label,
    labelKnown: r.label !== null,
    color: r.color,
    colorKnown: r.color !== null,
    colorNote: r.color === null ? NO_COLOUR_DECLARED : null,
    source: r.source,
  })));
}

/**
 * Values a brush may write, in declaration order. A brush must not be able to write a value
 * outside the legend: an undeclared value paints a cell nobody can read back, and the map is
 * the floor other maps are read against.
 */
export function brushableValues(legend) {
  return Object.freeze(((legend && legend.rows) || []).map(r => r.value));
}

/** Is this value in the declared vocabulary? The brush gate asks this, not `colorOf`. */
export function isDeclaredValue(legend, value) {
  return rowOf(legend, value) !== null;
}
