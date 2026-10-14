// TOOLTIP AND LABELS - the root part's (base set 10 and 9, docs/architecture/ROOT_PART_BASE_SET.md). A mark's tooltip is
// its name and each slot's value - the kind's slots, Color by, Marker by and the Tooltip slots the declaration adds
// (tip1 …, «+» for one more, Spotfire's Tooltip page) - read the way its mark was read (a hub its rows folded); a mark of
// rows a kind groups itself (a cross table cell, a map coordinate) says how many and each slot's value when they share
// one. A label is the Label by slot's value (else the mark's name), shown on none, the marked marks or all (`labels`).
// The kind asks neither: it hands the root what is under the pointer and draws the label the root gives.

import { slotWords, valueText, isTimeRead } from './slot.js';

const TIP = /^tip(\d+)$/;
const tipOrder = (key) => Number(TIP.exec(key)[1]);
/** The Tooltip keys the declaration holds, in order. */
export const tipsOf = (encode) => Object.keys(encode || {}).filter((k) => TIP.test(k)).sort((a, b) => tipOrder(a) - tipOrder(b));
const nextTip = (encode) => { const keys = tipsOf(encode); return `tip${keys.length ? tipOrder(keys[keys.length - 1]) + 1 : 1}`; };
/** The Tooltip slots: each held and the next one. */
export const tipSlots = (encode) => [...tipsOf(encode), nextTip(encode)].map((key) => ({ key, label: 'Tooltip' }));

/** The Label by slot every kind holds; what labels show (Spotfire's «Show labels for»). */
export const LABEL_SLOT = Object.freeze({ key: 'label', label: 'Label by' });
export const LABEL_SHOWS = Object.freeze([['none', 'None'], ['marked', 'Marked rows'], ['all', 'All']]);

/** A read in words: one value, several (how many), nothing - null. */
const readWords = (read, key = null, ctx = {}) => {
  if (!read) return null;
  if (read.state === 'one') return ctx.text ? ctx.text(key, read.value, isTimeRead(read)) : valueText(read.value, isTimeRead(read));
  if (read.state === 'several') return `${(read.values || []).length || 'several'} values`;
  return null;
};

/** Rows read as one for a tooltip: each slot's value when they all say the same one, else how many values. */
function sharedReads(rows, keys) {
  return Object.fromEntries(keys.map((key) => {
    const said = [...new Map(rows.map((r) => r.reads[key]).filter((r) => r && r.state === 'one').map((r) => [JSON.stringify(r.value), r.value])).values()];
    // a time the rows read stays a time (the screen gate's cross table cell, lead 10-14)
    const time = rows.some((r) => isTimeRead(r.reads[key])) ? { time: true } : {};
    return [key, said.length === 1 ? { state: 'one', value: said[0], ...time } : said.length ? { state: 'several', values: said } : { state: 'empty' }];
  }));
}

/**
 * A mark's tooltip lines: its name, then «slot: value» for each slot with something to say.
 * @param {{label?: string, reads?: object, ids: string[]}} mark  a unit the root made, or the rows a kind grouped (`ids`)
 * @param {{rowsById: Map, slots: Array<{key}>, encode: object}} ctx
 */
export function tipLines(mark, ctx) {
  const rows = (mark.ids || []).map((id) => ctx.rowsById.get(id)).filter(Boolean);
  const keys = ctx.slots.map((s) => s.key).filter((k) => ctx.encode[k]);
  const reads = mark.reads || (rows.length === 1 ? rows[0].reads : sharedReads(rows, keys));
  const name = mark.label || (rows.length === 1 ? rows[0].label : `${rows.length} rows`);
  // a slot's words once - the same column on Y, Top/Bottom by and Panel by is one line (lead 10-14)
  const lines = new Map();
  for (const k of keys) {
    const words = slotWords(ctx.encode[k]);
    // a slot of images (the root's `images`): its words and what to draw - {words, spec}
    const refs = ctx.images ? ctx.images(k, reads[k]) : null;
    if (refs) { if (refs.length && !lines.has(words)) lines.set(words, { words, spec: { id: mark.id || (mark.ids || []).join(','), key: k, refs } }); continue; }
    const said = readWords(reads[k], k, ctx);
    if (said !== null && !lines.has(words)) lines.set(words, `${words}: ${said}`);
  }
  return [name, ...lines.values()];
}

/** A mark's label: none, or for the marked marks only, or all - the Label by value, else the mark's name. */
export function labelOf(mark, ctx) {
  const shows = ctx.shows || (ctx.decl && ctx.decl.labels) || 'none';
  if (shows === 'none' || (shows === 'marked' && !ctx.marked(mark.ids || []))) return null;
  const rows = (mark.ids || []).map((id) => ctx.rowsById.get(id)).filter(Boolean);
  const read = mark.reads ? mark.reads.label : rows.length === 1 ? rows[0].reads.label : sharedReads(rows, ['label']).label;
  // a Label by of images: what to draw - {id, key, refs} (the root's picture at the mark's turn)
  const refs = ctx.images ? ctx.images('label', read) : null;
  if (refs) return refs.length ? { id: mark.id || (mark.ids || []).join(','), key: 'label', refs } : null;
  return readWords(read) || mark.label || (rows.length === 1 ? rows[0].label : null);
}
