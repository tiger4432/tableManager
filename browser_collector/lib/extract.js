// A template column's value from the page: an element under its base (the item, or the opened content), read as its
// visible text or as one attribute («@name»), then the column's regex - its first group when it has one. A value of
// length 0 is no value (null), whichever step made it so.
import { visibleText } from './open_check.js';

/** `raw` through `regex` -> the value, or null. */
export function pick(raw, regex) {
  if (raw === null || raw === undefined) return null;
  let text = String(raw).trim();
  if (regex) {
    const m = new RegExp(regex).exec(text);
    text = m ? String(m.length > 1 ? (m[1] ?? '') : m[0]).trim() : '';
  }
  return text === '' ? null : text;
}

/** The element a column names under `base` - an empty selector is the base itself. */
export const elementOf = (base, selector) => (!base ? null : (selector ? base.querySelector(selector) : base));

/** One column's value under `base`. */
export function readColumn(base, { selector, read, regex }) {
  const el = elementOf(base, selector);
  if (!el) return null;
  return pick(read && read.startsWith('@') ? el.getAttribute(read.slice(1)) : visibleText(el), regex);
}

/** Every column of `fields` under `base` -> {column: value}. */
export const readColumns = (base, fields) => Object.fromEntries(fields.map((f) => [f.column, readColumn(base, f)]));
