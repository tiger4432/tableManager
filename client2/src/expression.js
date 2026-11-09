// The expression calculator (lead 0b7d84462 · afcb79f14, plan a 10-13): Spotfire's expression language over rows. A
// text is read into a tree once (compile), then answered over the rows a point or a cell holds (run). One function
// table - the test bed's fold (testbed/aggregate.js) reads its folds. Scored by contracts/expression/vectors.json
// (tests/expression_vectors_harness.mjs), the file the server's calculator is scored by too.
//
// Rows: plain objects ({x: 1, $at: '2026-…'}) or {get(name), at} - a cell's value may be a list or a Reads (several
// reads, each with its own time); a fold counts their items, a row-by-row use needs one value.
// Dates (lead fe2ba4b1f): a time is cut into its date and parts on the wall clock of run's page.zone (an IANA name,
// ZONE_DEFAULT the server setting's default, owner «ㅇㅇ kst»). A time with an offset is moved there; one without is
// read as that wall clock. Date · DateTime answer a time text («2026-10-14T00:00:00+09:00», «Z» at offset 0).
// ParseDateTime(text, format) reads a text by a format in Spotfire's .NET spelling (owner 11-07 «2»: yyMMdd_HHmmss) - a
// closed token set (NET_TOKENS, the server's the same), refused when read outside it.
// The grammar of each function, the names refused and every refusal sentence are the server table's, written out in
// contracts/expression/catalogue.json (owner 11-09 «ㄴ») - imported here, not written here.

import CATALOGUE from '../../contracts/expression/catalogue.json' with { type: 'json' };
import { isBlank, SPACE } from './absent.js';
import { numberOf } from './walk/reach_table.js';
import { parseServerInstant, ZONE_DEFAULT, useZone, productZone, clockOf } from './server_time.js';

/** A refusal in words - what the expression box says. */
export class ExpressionError extends Error {}
/** The catalogue's sentence `key` with its blanks filled - the one way a refusal is worded. */
export const say = (key, fill = {}) => CATALOGUE.sentences[key].replace(/\{(\w+)\}/g, (_, k) => String(fill[k]));
/** The characters a backslash stands for inside quotes (lead 11-09 ①) - any other \x is itself. */
export const ESCAPED = '\\"\'';
/** A row-by-row use of a value the row holds several of - the slot says «several», as an unfolded slot does. */
export class SeveralValues extends Error {}
/** Several reads of one value, each with its time (ms or null) - what a walk gives a row. */
export class Reads {
  constructor(items) { this.items = items; }
}

const spelling = (v) => JSON.stringify(v);

// ── dates ─────────────────────────────────────────────────────────────────────────────────────────────────────────
// The zone (ZONE_DEFAULT · useZone) and its wall clock (clockOf) are the time writer's (server_time.js): the dates cut
// here and the times people read are one zone (owner 11-07). A run's page.zone comes before it.
export { ZONE_DEFAULT, useZone };
/** The one shape a time is read in - the server's TIME (expression.py) is the same pattern. */
const TIME = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?\s*(Z|[+-]\d{2}:?\d{2})?$/;
const PARTS = Object.freeze({
  year: 'Year', yy: 'Year', quarter: 'Quarter', qq: 'Quarter', month: 'Month', mm: 'Month',
  day: 'Day', 'day of month': 'Day', dayofmonth: 'Day', dd: 'Day', week: 'Week', wk: 'Week',
  'day of week': 'DayOfWeek', dayofweek: 'DayOfWeek', weekday: 'DayOfWeek', dw: 'DayOfWeek', hour: 'Hour', hh: 'Hour',
});
const OTHER_PARTS = new Set(['minute', 'mi', 'second', 'ss', 'millisecond', 'ms', 'day of year', 'dayofyear', 'dy',
  'year and week', 'yearandweek', 'yywk', 'isoyear', 'isoweek']);
/** A wall clock as UTC milliseconds - setUTCFullYear, so the years 1 to 99 are themselves (Date.UTC reads 0-99 as 19xx). */
const utcOf = (w) => { const at = new Date(0); at.setUTCFullYear(w.y, w.M - 1, w.d); at.setUTCHours(w.h || 0, w.mi || 0, w.s || 0, 0); return at.getTime(); };
/** The zone's offset (whole minutes - an old local mean time's seconds dropped, as the server) at an instant. */
const offsetAt = (ms, zone) => Math.floor((utcOf(clockOf(ms, zone)) - Math.floor(ms / 1000) * 1000) / 60000);
const sameWall = (a, b) => a.y === b.y && a.M === b.M && a.d === b.d && a.h === b.h && a.mi === b.mi && a.s === b.s;
/** A wall clock read in the zone: its offset there - the server's fold 0: a wall clock the zone repeats is the first,
 *  one it skips takes the offset before the change. */
const offsetOfWall = (w, zone) => {
  const guess = utcOf(w);
  const before = offsetAt(guess - 86400000, zone);
  const after = offsetAt(guess + 86400000, zone);
  const fits = [before, after].filter((o) => sameWall(clockOf(guess - o * 60000, zone), w));
  return fits.length ? Math.max(...fits) : before;    // the larger offset is the earlier instant
};
/** `v` on `zone`'s wall clock ({y, M, d, h, mi, s, ms, off}), or null - empty, or not a time (TIME, a real day). */
function wallOf(v, zone) {
  if (typeof v !== 'string' || isBlank(v)) return null;
  const m = TIME.exec(v.trim());
  if (!m) return null;
  const [y, M, d, h, mi, s] = [1, 2, 3, 4, 5, 6].map((i) => Number(m[i] || 0));
  const ms = Number((m[7] || '0').padEnd(6, '0').slice(0, 3));
  const at = new Date(utcOf({ y, M, d, h: 0, mi: 0, s: 0 }));
  if (y < 1 || at.getUTCFullYear() !== y || at.getUTCMonth() !== M - 1 || at.getUTCDate() !== d || h > 23 || mi > 59 || s > 59) return null;
  const wall = { y, M, d, h, mi, s };
  if (!m[8]) return { ...wall, ms, off: offsetOfWall(wall, zone) };
  const digits = m[8] === 'Z' ? '0000' : m[8].slice(1).replace(':', '');
  if (Number(digits.slice(0, 2)) > 23 || Number(digits.slice(2)) > 59) return null;           // ±24:00 is no offset
  const given = m[8] === 'Z' ? 0 : (m[8][0] === '-' ? -1 : 1) * (Number(digits.slice(0, 2)) * 60 + Number(digits.slice(2)));
  const instant = utcOf(wall) - given * 60000;
  const moved = clockOf(instant, zone);
  // moved outside the years 1 to 9999 - the server's datetime cannot hold it: not a time
  return moved.y < 1 || moved.y > 9999 ? null : { ...moved, ms, off: offsetAt(instant, zone) };
}
const pad2 = (n) => String(n).padStart(2, '0');
/** A time's day on the page zone's wall clock («YYYY-MM-DD») when it is that day's midnight there; else - not a time, a
 *  zone that is none - null. What the screen says a time of a slot of days as (testbed slot.js valueText, lead 10-15). */
export function dayText(v) {
  let w = null;
  try { w = wallOf(v, productZone()); } catch (e) { if (!(e instanceof RangeError)) throw e; }
  return w && !w.h && !w.mi && !w.s && !w.ms ? `${String(w.y).padStart(4, '0')}-${pad2(w.M)}-${pad2(w.d)}` : null;
}
/** A time as both calculators spell it: its wall clock and offset, «Z» at offset 0, milliseconds when not 0. */
const timeText = (w) => `${String(w.y).padStart(4, '0')}-${pad2(w.M)}-${pad2(w.d)}T${pad2(w.h)}:${pad2(w.mi)}:${pad2(w.s)}`
  + (w.ms ? `.${String(w.ms).padStart(3, '0')}` : '')
  + (w.off === 0 ? 'Z' : `${w.off < 0 ? '-' : '+'}${pad2(Math.floor(Math.abs(w.off) / 60))}:${pad2(Math.abs(w.off) % 60)}`);
const weekdayOf = (w) => new Date(utcOf({ y: w.y, M: w.M, d: w.d })).getUTCDay();
/** The week of the year, weeks starting on Sunday and the first holding January 1 - Spotfire's «first week of year is
 *  dependent on the regional settings», read for the owner's (Korean) ones; 1 to 54. */
const weekOf = (w) => Math.floor(((utcOf({ y: w.y, M: w.M, d: w.d }) - utcOf({ y: w.y, M: 1, d: 1 })) / 86400000
  + weekdayOf({ y: w.y, M: 1, d: 1 })) / 7) + 1;
const PART_OF = Object.freeze({ Year: (w) => w.y, Quarter: (w) => Math.floor((w.M - 1) / 3) + 1, Month: (w) => w.M,
  Day: (w) => w.d, Hour: (w) => w.h, Week: weekOf, DayOfWeek: weekdayOf });
/** A function of one time: the time on the zone's wall clock, else empty - a value that is not a time is counted (the
 *  run's notTime), an empty one is not. */
const dated = (f) => ({ zoned: true,
  fn: (v, ctx) => {
    const w = wallOf(v, ctx.zone);
    if (!w) { if (!isBlank(v)) ctx.notTime.add(ctx.row); return null; }
    return f(w, ctx);
  } });
const datePart = (part, v, ctx) => {
  const name = typeof part === 'string' ? PARTS[part.trim().toLowerCase()] : undefined;
  if (!name) {
    const said = typeof part === 'string' ? part.trim().toLowerCase() : part;
    throw new ExpressionError(OTHER_PARTS.has(said) ? say('datepart_other', { part: said }) : say('datepart_name', { got: part }));
  }
  return dated(PART_OF[name]).fn(v, ctx);
};
// ── ParseDateTime (owner 11-07 «2»: Spotfire's .NET spelling) ──
/** The tokens it reads and their digits - the server's NET_TOKENS (contracts/expression/vectors.json binds the two). yy is
 *  .NET's window (TwoDigitYearMax 2029): 00-29 is 20xx, 30-99 is 19xx. */
const NET_TOKENS = Object.freeze({ yyyy: 4, yy: 2, MM: 2, dd: 2, HH: 2, mm: 2, ss: 2, fff: 3 });
/** .NET's format letters - a run of one is a token, refused unless in NET_TOKENS. */
const NET_LETTERS = 'yMdHhmsfFtzKg';
const NET_UNITS = Object.freeze({ y: 'year', M: 'month', d: 'day', H: 'hour', m: 'minute', s: 'second', f: 'fraction' });
const netFormats = new Map();
/** `fmt` in .NET's spelling -> {shape (its exact text), tokens (in order)}, or refused naming what it reads. */
function netFormat(fmt) {
  if (netFormats.has(fmt)) return netFormats.get(fmt);
  if (fmt.includes('%')) throw new ExpressionError(say('net_spelling', { fmt }));
  const shape = [];
  const tokens = [];
  const units = new Set();
  let i = 0;
  while (i < fmt.length) {
    const ch = fmt[i];
    let literal;
    if (ch === "'" || ch === '"') {
      const end = fmt.indexOf(ch, i + 1);
      if (end < 0) throw new ExpressionError(say('net_quote', { at: i + 1, fmt }));
      literal = fmt.slice(i + 1, end);
      i = end + 1;
    } else if (ch === '\\' && i + 1 < fmt.length) {
      literal = fmt[i + 1];
      i += 2;
    } else if (NET_LETTERS.includes(ch)) {
      let j = i;
      while (j < fmt.length && fmt[j] === ch) j += 1;
      const token = fmt.slice(i, j);
      i = j;
      if (!Object.hasOwn(NET_TOKENS, token)) throw new ExpressionError(say('net_reads', { token }));
      if (units.has(ch)) throw new ExpressionError(say('net_again', { token, unit: NET_UNITS[ch], fmt }));
      units.add(ch);
      tokens.push(token);
      shape.push(`([0-9]{${NET_TOKENS[token]}})`);
      continue;
    } else {
      literal = ch;
      i += 1;
    }
    shape.push(literal.replace(/[.*+?^${}()|[\]\\/-]/g, '\\$&'));
  }
  if (!['y', 'M', 'd'].every((u) => units.has(u))) throw new ExpressionError(say('net_needs', { fmt }));
  const out = { shape: new RegExp(`^(?:${shape.join('')})$`), tokens };
  netFormats.set(fmt, out);
  return out;
}
/** ParseDateTime's format is read with the expression: a text in quotes, in the closed set. */
const netFormatGiven = (args) => {
  if (args[1].t !== 'lit' || typeof args[1].v !== 'string') throw new ExpressionError(say('net_quoted'));
  netFormat(args[1].v);
};
/** `v` read by `fmt` on the zone's wall clock, as DateTime spells a time - else empty: a text that is not that shape or
 *  not a real time is counted (the run's notTime), an empty one is not. */
const parseDateTime = (v, fmt, ctx) => {
  if (isBlank(v)) return null;
  const { shape, tokens } = netFormat(fmt);
  const m = typeof v === 'string' ? shape.exec(v) : null;
  let w = null;
  if (m) {
    const got = Object.fromEntries(tokens.map((token, k) => [token, m[k + 1]]));
    const y = got.yyyy !== undefined ? Number(got.yyyy) : (Number(got.yy) < 30 ? 2000 : 1900) + Number(got.yy);
    w = wallOf(`${String(y).padStart(4, '0')}-${got.MM}-${got.dd}T${got.HH ?? '00'}:${got.mm ?? '00'}:${got.ss ?? '00'}`
      + (got.fff !== undefined ? `.${got.fff}` : ''), ctx.zone);
  }
  if (!w) { ctx.notTime.add(ctx.row); return null; }
  return timeText(w);
};
const finite = (v) => (typeof v === 'number' && !Number.isFinite(v) ? null : v === undefined ? null : v);

// ── the function table ──────────────────────────────────────────────────────────────────────────────────────────
// fold  over the rows: items {value, t}, blanks out. `params` constant arguments after the column, `pair` two columns,
//       `rowwise` several arguments fold within a row (Sum(1, null, 3)). Returns {value, skipped?, tied?, untimed?}.
// row   a value from values; any empty argument is an empty answer.
const nums = (items) => items.map((it) => numberOf(it.value)).filter((x) => x !== null);
const numeric = (f) => (items, params) => {
  const xs = nums(items);
  return { value: xs.length ? f(xs, params) : null, skipped: items.length - xs.length };
};
const sum = (xs) => xs.reduce((a, b) => a + b, 0);
const mean = (xs) => sum(xs) / xs.length;
const sorted = (xs) => [...xs].sort((a, b) => a - b);
const median = (xs) => { const s = sorted(xs); const n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };
const svar = (xs) => (xs.length < 2 ? null : sum(xs.map((v) => (v - mean(xs)) ** 2)) / (xs.length - 1));
const sd = (xs) => (xs.length < 2 ? null : Math.sqrt(svar(xs)));
// 7.0.1 «Percentiles and Quartiles»: f = (i - 1) / (n - 1), interpolated between the f-values around p.
const pct = (xs, p) => {
  const s = sorted(xs); const h = (s.length - 1) * p; const lo = Math.floor(h); const hi = Math.ceil(h);
  return s[lo] + (h - lo) * (s[hi] - s[lo]);
};
const q1 = (xs) => pct(xs, 0.25);
const q3 = (xs) => pct(xs, 0.75);
const iqr = (xs) => q3(xs) - q1(xs);
const uav = (xs) => Math.max(q3(xs), Math.max(...xs.filter((v) => v <= q3(xs) + 1.5 * iqr(xs))));
const lav = (xs) => Math.min(q1(xs), Math.min(...xs.filter((v) => v >= q1(xs) - 1.5 * iqr(xs))));
const outliers = (xs) => xs.filter((v) => v > uav(xs) || v < lav(xs)).length;
const T95 = 1.959964;
/** Text by character code, numbers by size - the one order `<` and UniqueConcatenate keep. */
const order = (a, b) => (typeof a === 'number' && typeof b === 'number' ? a - b : String(a) < String(b) ? -1 : String(a) > String(b) ? 1 : 0);
const distinctValues = (items) => [...new Map(items.map((it) => [spelling(it.value), it.value])).values()];

/** Latest (lead 10-13): with any timed item the newest of those (an untimed item is no candidate); with none timed the
 *  value when there is one or all agree. Two different values at the newest time: none - no rule orders them. */
function latest(items) {
  if (!items.length) return { value: null };
  const timed = items.filter((it) => Number.isFinite(it.t));
  const untimed = items.length - timed.length;
  if (!timed.length) {
    const one = distinctValues(items);
    return one.length === 1 ? { value: one[0] } : { value: null, untimed };
  }
  const newest = Math.max(...timed.map((it) => it.t));
  const at = distinctValues(timed.filter((it) => it.t === newest));
  return at.length === 1 ? { value: at[0], untimed } : { value: null, tied: at.length, untimed };
}

function mostCommon(items) {
  const counts = new Map();
  for (const it of items) { const k = spelling(it.value); counts.set(k, { value: it.value, n: ((counts.get(k) || {}).n || 0) + 1 }); }
  let best = null;
  for (const c of counts.values()) if (!best || c.n > best.n) best = c;   // a tie keeps the one met first
  return { value: best ? best.value : null };
}

const pairNums = (pairs) => pairs.map((p) => [numberOf(p.x), numberOf(p.y)]).filter(([x, y]) => x !== null && y !== null);
const valueFor = (pick, last) => (pairs) => {
  const keyed = pairs.map((p) => [numberOf(p.x), p.y]).filter(([k]) => k !== null);
  if (!keyed.length) return { value: null };
  const target = pick(...keyed.map(([k]) => k));
  const hits = keyed.filter(([k]) => k === target);
  return { value: (last ? hits[hits.length - 1] : hits[0])[1] };
};

// ── text (owner 11-09 «ㄴ»: Spotfire's Text functions) - by code points, as the server's strings count ──
/** What a fold of texts writes between them - UniqueConcatenate and a one-column Concatenate (lead 11-09 ②). */
const JOINER = CATALOGUE.joiner;
/** A count's integer part (Text «Left»: 3.99 is 3), else null. */
const whole = (v) => { const x = numberOf(v); return x === null ? null : Math.trunc(x); };
/** A row function of texts: an empty argument is an empty answer. A text of spaces in quotes is a text - a row's empty
 *  value is null already (oneOf). */
const texts = (f) => (...vs) => (vs.some((v) => v === null || v === undefined) ? null : f(...vs));
const textRow = (f, more = {}) => ({ fn: texts(f), ...more });
const left = (s, n) => {
  const k = whole(n); const c = [...String(s)];
  if (k === null) return null;
  return (k >= 0 ? c.slice(0, k) : c.slice(0, Math.max(c.length + k, 0))).join('');   // a negative count takes that many off the right
};
const right = (s, n) => {
  const k = whole(n); const c = [...String(s)];
  if (k === null) return null;
  return (k >= 0 ? c.slice(Math.max(c.length - k, 0)) : c.slice(Math.min(-k, c.length))).join('');
};
const mid = (s, start, length) => {
  const st = whole(start); const ln = whole(length);
  if (st === null || ln === null || st < 1 || ln < 0) return null;   // Text «Mid»: a start below 1 or a negative length is an error
  return [...String(s)].slice(st - 1, st - 1 + ln).join('');
};
const indexIn = (hay, needle, from) => {
  for (let i = from; i + needle.length <= hay.length; i += 1) {
    let j = 0;
    while (j < needle.length && hay[i + j] === needle[j]) j += 1;
    if (j === needle.length) return i;
  }
  return -1;
};
const find = (needle, within, nth = 1) => {
  if (needle === null || within === null || nth === null) return null;
  const k = whole(nth); const a = [...String(needle)]; const b = [...String(within)];
  if (k === null) return null;
  if (!a.length || k < 1 || k > b.length) return 0;
  let at = -1;
  for (let n = 0; n < k; n += 1) {   // the k-th, each looked for one past the last
    at = indexIn(b, a, at + 1);
    if (at < 0) return 0;
  }
  return at + 1;
};
const repeat = (s, n) => { const k = whole(n); return k === null || k < 0 ? null : String(s).repeat(k); };
const split = (s, sep, n) => {
  const k = whole(n);
  if (k === null || k === 0 || String(sep) === '') return null;
  const parts = String(s).split(String(sep));
  if (Math.abs(k) > parts.length) return null;
  return k > 0 ? parts[k - 1] : parts[parts.length + k];   // a negative count from the end
};
const substitute = (s, old, nw) => {
  if (s === null || s === undefined) return null;
  const t = String(s);
  if (old === null || old === undefined || String(old) === '') return t;
  return t.split(String(old)).join(nw === null || nw === undefined ? '' : String(nw));
};
const trimmed = (s) => {
  const c = [...String(s)]; let a = 0; let b = c.length;
  while (a < b && SPACE.has(c[a].codePointAt(0))) a += 1;
  while (b > a && SPACE.has(c[b - 1].codePointAt(0))) b -= 1;
  return c.slice(a, b).join('');
};
const joined = (items) => ({ value: items.length ? items.map((it) => String(it.value)).join(JOINER) : null });
/** Concatenate's arguments in one row: empty ones left out (Text «Concatenate»: null + "Ape" is "Ape"). */
const concatenated = (values) => {
  const kept = values.filter((v) => v !== null && v !== undefined).map(String);
  return kept.length ? kept.join('') : null;
};

// ── patterns (RXExtract · RXReplace · ~=): only what JavaScript's RegExp, Python's re and .NET read alike ──
// A pattern is read once into the one text both calculators compile (the server's _translated, the same walk): classes
// spelled out (\d is [0-9]), «.» not a newline, «$» the end or before a last newline - anything else refused by name.
const WORDISH = '[A-Za-z0-9_]';
const OUTSIDE = Object.freeze({ d: '[0-9]', D: '[^0-9]', w: WORDISH, W: '[^A-Za-z0-9_]', s: '[\\t\\n\\v\\f\\r ]',
  S: '[^\\t\\n\\v\\f\\r ]', t: '\\t', n: '\\n', r: '\\r', f: '\\f', v: '\\v',
  b: `(?:(?<=${WORDISH})(?!${WORDISH})|(?<!${WORDISH})(?=${WORDISH}))`,
  B: `(?:(?<=${WORDISH})(?=${WORDISH})|(?<!${WORDISH})(?!${WORDISH}))` });
const INSIDE = Object.freeze({ d: '0-9', w: 'A-Za-z0-9_', s: '\\t\\n\\v\\f\\r ', t: '\\t', n: '\\n', r: '\\r', f: '\\f', v: '\\v' });
const COUNT = /^\{[0-9]+(,[0-9]*)?\}/;
const GROUP_HEADS = ['(?:', '(?=', '(?!'];
const alnum = (ch) => /^[A-Za-z0-9]$/.test(ch);
/** One character as itself in both engines' pattern grammar. */
const lit = (ch) => { const cp = ch.codePointAt(0); return alnum(ch) ? ch : cp < 0x10000 ? `\\u${cp.toString(16).toUpperCase().padStart(4, '0')}` : ch; };

/** `pattern` -> {text both compile, groups}, or refused naming the part. */
function translated(name, pattern, dotall) {
  const P = [...pattern];
  const part = (k) => { throw new ExpressionError(say('pattern_part', { name, part: k })); };
  const bad = () => { throw new ExpressionError(say('pattern_bad', { name, pattern })); };
  const startsAt = (i, s) => P.slice(i, i + s.length).join('') === s;
  const item = (i) => {   // one member of a [ ] -> [its text, one character?, the index after]
    const ch = P[i];
    if (ch !== '\\') return [lit(ch), true, i + 1];
    if (i + 1 >= P.length) bad();
    const e = P[i + 1];
    if (Object.hasOwn(INSIDE, e)) return [INSIDE[e], !'dws'.includes(e), i + 2];
    if (!alnum(e)) return [lit(e), true, i + 2];
    return part(`\\${e}`);
  };
  const out = []; const opened = [];
  let i = 0; let groups = 0; let repeat = false;
  while (i < P.length) {
    const ch = P[i];
    if (ch === '\\') {
      if (i + 1 >= P.length) bad();
      const e = P[i + 1];
      if (Object.hasOwn(OUTSIDE, e)) { out.push(OUTSIDE[e]); repeat = !'bB'.includes(e); }
      else if (!alnum(e)) { out.push(lit(e)); repeat = true; }
      else part(`\\${e}`);
      i += 2;
    } else if (ch === '[') {
      const body = ['['];
      i += 1;
      if (P[i] === '^') { body.push('^'); i += 1; }
      let first = true;
      for (;;) {
        if (i >= P.length) bad();
        if (P[i] === ']' && !first) break;
        if (startsAt(i, '-[')) part('-[');   // .NET's class subtraction
        first = false;
        let [text, single, next] = item(i);
        i = next;
        if (P[i] === '-' && i + 1 < P.length && P[i + 1] !== ']') {
          if (!single || P[i + 1] === '[') part(single ? P.slice(i, i + 2).join('') : '-');
          const [high, highSingle, after] = item(i + 1);
          i = after;
          if (!highSingle) part('-');
          text = `${text}-${high}`;
        }
        body.push(text);
      }
      out.push(`${body.join('')}]`);
      i += 1;
      repeat = true;
    } else if (ch === '(') {
      let head = GROUP_HEADS.find((h) => startsAt(i, h));
      if (!head && startsAt(i, '(?')) part(P.slice(i, i + 3).join(''));
      if (!head) { head = '('; groups += 1; }
      out.push(head); opened.push(head);
      i += head.length;
      repeat = false;
    } else if (ch === ')') {
      if (!opened.length) bad();
      repeat = ['(', '(?:'].includes(opened.pop());
      out.push(')');
      i += 1;
    } else if ('*+?'.includes(ch) || (ch === '{' && COUNT.test(P.slice(i).join('')))) {
      let q = ch === '{' ? COUNT.exec(P.slice(i).join(''))[0] : ch;
      if (!repeat) part(q);   // nothing before it to repeat
      i += q.length;
      if (P[i] === '+') part(`${q}+`);   // .NET has no possessive
      if (P[i] === '?') { q += '?'; i += 1; }
      out.push(q);
      repeat = false;
    } else {
      out.push({ '.': dotall ? '[\\s\\S]' : '[^\\n]', '^': '^', $: '(?=\\n?(?![\\s\\S]))', '|': '|' }[ch] || lit(ch));
      repeat = !'^$|'.includes(ch);
      i += 1;
    }
  }
  if (opened.length) bad();
  return { text: out.join(''), groups };
}
const patterns = new Map();
/** A pattern with its options (g all · i no case · s «.» takes a newline too) -> {compiled, groups}. */
function rx(name, pattern, options) {
  const key = JSON.stringify([pattern, options]);
  if (patterns.has(key)) return patterns.get(key);
  if ([...options].some((ch) => !'gis'.includes(ch))) throw new ExpressionError(say('options', { name, got: options }));
  const { text, groups } = translated(name, pattern, options.includes('s'));
  let compiled;
  try { compiled = new RegExp(text, `gu${options.includes('i') ? 'i' : ''}`); } catch (e) {
    if (!(e instanceof SyntaxError)) throw e;
    throw new ExpressionError(say('pattern_bad', { name, pattern }));
  }
  const out = { compiled, groups };
  patterns.set(key, out);
  return out;
}
/** `$1` `${1}` `$0` (the match) `$$` -> parts: texts and group numbers; a number past the groups is its own text; .NET's
 *  other $ forms are refused by name. */
function replacement(name, text, groups) {
  const parts = [];
  let i = 0;
  while (i < text.length) {
    const m = /^\$([0-9]+)|^\$\{([0-9]+)\}/.exec(text.slice(i));
    if (m) { const k = Number(m[1] ?? m[2]); parts.push(k <= groups ? k : m[0]); i += m[0].length; }
    else if (text.startsWith('$$', i)) { parts.push('$'); i += 2; }
    else if (text[i] === '$' && ['&', '`', "'", '+', '_', '{'].includes(text[i + 1])) throw new ExpressionError(say('replacement_part', { name, part: text.slice(i, i + 2) }));
    else { parts.push(text[i]); i += 1; }
  }
  return parts;
}
/** Each match left to right, an empty one stepped past by one character - the same walk as the server's. */
function* matches(compiled, s) {
  let at = 0;
  while (at <= s.length) {
    compiled.lastIndex = at;
    const m = compiled.exec(s);
    if (!m) return;
    yield m;
    const end = m.index + m[0].length;
    at = end > m.index ? end : end + (s.codePointAt(end) > 0xffff ? 2 : 1);
  }
}
const quoted = (name, args, at, what) => {
  const a = args[at];
  if (a.t !== 'lit' || typeof a.v !== 'string') throw new ExpressionError(say('quoted', { name, what }));
  return a.v;
};
/** The pattern (and a replacement · options) are read with the expression: texts in quotes, read once. */
const rxGiven = (name, withReplacement = false, withOptions = false) => (args) => {
  const pattern = quoted(name, args, 1, 'pattern');
  const said = withReplacement ? quoted(name, args, 2, 'replacement') : null;
  const flags = withOptions ? quoted(name, args, 3, 'options') : '';
  const { groups } = rx(name, pattern, flags);
  if (said !== null) replacement(name, said, groups);
};
const rxExtract = (s, pattern, nth) => {
  let k = whole(nth);
  if (k === null || k < 1) return null;
  for (const m of matches(rx('RXExtract', pattern, '').compiled, String(s))) {
    k -= 1;
    if (k === 0) return m[0];
  }
  return null;
};
const rxReplace = (s, pattern, said, options) => {
  const { compiled, groups } = rx('RXReplace', pattern, options);
  const parts = replacement('RXReplace', said, groups);
  const t = String(s);
  let out = ''; let last = 0;
  for (const m of matches(compiled, t)) {
    out += t.slice(last, m.index) + parts.map((p) => (typeof p === 'string' ? p : m[p] ?? '')).join('');
    last = m.index + m[0].length;
    if (!options.includes('g')) break;
  }
  return out + t.slice(last);
};

const fold = (fn, more = {}) => ({ fn, ...more });
const row = (fn) => ({ fn });
const num1 = (f) => row((a) => { const x = numberOf(a); return x === null ? null : f(x); });
const num2 = (f) => row((a, b) => { const x = numberOf(a); const y = numberOf(b); return x === null || y === null ? null : f(x, y); });

/** A fold over a datetime column (lead 10-13): instants compared, the row's value answered; a text that is not a time and
 *  an empty value left out; the same instant twice - the one met first. */
const times = (wins) => (items) => {
  let best = null;
  for (const it of items) {
    const at = parseServerInstant(it.value);
    if (at && (!best || wins(at.getTime(), best.t))) best = { t: at.getTime(), value: it.value };
  }
  return { value: best ? best.value : null };
};
/** A fold whose argument is a datetime column (run's `types`) answers by these instead. */
const BY_TIME = { Min: times((a, b) => a < b), Max: times((a, b) => a > b) };

// How this calculator answers each function; the grammar (kind · args · counts) is the catalogue's - the server's
// table written out (owner 11-09 «ㄴ»): a name here the catalogue does not list is never read.
const IMPL = {
  Count: fold((items) => ({ value: items.length })),
  CountBig: fold((items) => ({ value: items.length })),
  UniqueCount: fold((items) => ({ value: distinctValues(items).length })),
  Sum: fold(numeric(sum)),
  Avg: fold(numeric(mean)),
  Min: fold(numeric((xs) => Math.min(...xs))),
  Max: fold(numeric((xs) => Math.max(...xs))),
  Median: fold(numeric(median)),
  Product: fold(numeric((xs) => xs.reduce((a, b) => a * b, 1))),
  MeanDeviation: fold(numeric((xs) => mean(xs.map((v) => Math.abs(v - mean(xs)))))),
  MedianAbsoluteDeviation: fold(numeric((xs) => median(xs.map((v) => Math.abs(v - median(xs)))))),
  First: fold((items) => ({ value: items.length ? items[0].value : null })),
  Last: fold((items) => ({ value: items.length ? items[items.length - 1].value : null })),
  Latest: fold(latest),
  MostCommon: fold(mostCommon),
  UniqueConcatenate: fold((items) => ({ value: items.length ? distinctValues(items).sort(order).join(JOINER) : null })),
  StdDev: fold(numeric(sd)),
  Var: fold(numeric(svar)),
  StdErr: fold(numeric((xs) => (xs.length < 2 ? null : sd(xs) / Math.sqrt(xs.length)))),
  Range: fold(numeric((xs) => Math.max(...xs) - Math.min(...xs))),
  Q1: fold(numeric(q1)),
  Q3: fold(numeric(q3)),
  IQR: fold(numeric(iqr)),
  P10: fold(numeric((xs) => pct(xs, 0.1))),
  P90: fold(numeric((xs) => pct(xs, 0.9))),
  Percentile: fold(numeric((xs, [p]) => (p === null ? null : pct(xs, p / 100)))),
  Percent: fold(numeric((xs, [p]) => (p === null ? null : Math.min(...xs) + (p / 100) * (Math.max(...xs) - Math.min(...xs))))),
  LIF: fold(numeric((xs) => q1(xs) - 1.5 * iqr(xs))),
  UIF: fold(numeric((xs) => q3(xs) + 1.5 * iqr(xs))),
  LOF: fold(numeric((xs) => q1(xs) - 3 * iqr(xs))),
  UOF: fold(numeric((xs) => q3(xs) + 3 * iqr(xs))),
  LAV: fold(numeric(lav)),
  UAV: fold(numeric(uav)),
  Outliers: fold(numeric(outliers)),
  PctOutliers: fold(numeric((xs) => (100 * outliers(xs)) / xs.length)),
  GeometricMean: fold(numeric((xs) => (xs.some((v) => v < 0) ? null : xs.some((v) => v === 0) ? 0 : Math.exp(mean(xs.map(Math.log)))))),
  TrimmedMean: fold(numeric((xs, [p]) => {
    if (p === null) return null;
    const k = Math.floor((xs.length * p) / 100 / 2);
    const kept = sorted(xs).slice(k, xs.length - k);
    return kept.length ? mean(kept) : null;
  })),
  NthLargest: fold(numeric((xs, [n]) => (n === null || n < 1 ? null : sorted(xs).reverse()[Math.min(Math.floor(n), xs.length) - 1]))),
  NthSmallest: fold(numeric((xs, [n]) => (n === null || n < 1 ? null : sorted(xs)[Math.min(Math.floor(n), xs.length) - 1]))),
  L95: fold(numeric((xs) => (xs.length < 2 ? null : mean(xs) - (T95 * sd(xs)) / Math.sqrt(xs.length)))),
  U95: fold(numeric((xs) => (xs.length < 2 ? null : mean(xs) + (T95 * sd(xs)) / Math.sqrt(xs.length)))),
  // two columns: a row with either side empty is left out (lead 10-13)
  WeightedAverage: fold((pairs) => {
    const ps = pairNums(pairs);
    const w = sum(ps.map(([x]) => x));
    return { value: ps.length && w !== 0 ? sum(ps.map(([x, y]) => x * y)) / w : null };
  }),
  Covariance: fold((pairs) => {
    const ps = pairNums(pairs);
    if (ps.length < 2) return { value: null };
    const mx = mean(ps.map(([x]) => x)); const my = mean(ps.map(([, y]) => y));
    return { value: sum(ps.map(([x, y]) => (x - mx) * (y - my))) / (ps.length - 1) };
  }),
  ValueForMax: fold(valueFor(Math.max, false)),
  ValueForMin: fold(valueFor(Math.min, false)),
  LastValueForMax: fold(valueFor(Math.max, true)),
  LastValueForMin: fold(valueFor(Math.min, true)),
  // values
  Abs: num1(Math.abs),
  Ceiling: num1(Math.ceil),
  Floor: num1(Math.floor),
  Round: num2((x, d) => {
    const digits = Math.trunc(d);   // only Arg2's integer part (Math «Round»)
    const away = (v) => Math.sign(v) * Math.round(Math.abs(v));   // 0.5 to the higher magnitude
    return digits >= 0 ? away(x * 10 ** digits) / 10 ** digits : away(x / 10 ** -digits) * 10 ** -digits;
  }),
  Sqrt: num1((x) => (x < 0 ? null : Math.sqrt(x))),
  Exp: num1(Math.exp),
  Ln: num1((x) => (x <= 0 ? null : Math.log(x))),
  Log10: num1((x) => (x <= 0 ? null : Math.log10(x))),
  Log: num2((x, b) => (x <= 0 || b <= 0 || b === 1 ? null : Math.log(x) / Math.log(b))),
  Mod: num2((a, b) => (b === 0 ? null : a - b * Math.floor(a / b))),
  Power: num2((a, b) => a ** b),
  PI: row(() => Math.PI),
  Sin: num1(Math.sin),
  Cos: num1(Math.cos),
  Tan: num1(Math.tan),
  ASin: num1((x) => (Math.abs(x) > 1 ? null : Math.asin(x))),
  ACos: num1((x) => (Math.abs(x) > 1 ? null : Math.acos(x))),
  ATan: num1(Math.atan),
  ATan2: num2((y, x) => Math.atan2(y, x)),
  // dates (lead fe2ba4b1f) - on the zone's wall clock
  Date: dated((w, ctx) => { const mid = { y: w.y, M: w.M, d: w.d, h: 0, mi: 0, s: 0 }; return timeText({ ...mid, ms: 0, off: offsetOfWall(mid, ctx.zone) }); }),
  DateTime: dated(timeText),
  ...Object.fromEntries(Object.entries(PART_OF).map(([name, f]) => [name, dated(f)])),
  DatePart: { zoned: true, fn: datePart },
  ParseDateTime: { zoned: true, fn: parseDateTime, check: netFormatGiven },
  // text (owner 11-09 «ㄴ») - a number or a boolean read as its text; counts by their integer part
  Concatenate: fold(joined, { within: concatenated }),
  Find: row(find),
  Left: textRow(left),
  Len: textRow((s) => [...String(s)].length),
  Lower: textRow((s) => String(s).toLowerCase()),
  Mid: textRow(mid),
  Repeat: textRow(repeat),
  Right: textRow(right),
  RXExtract: textRow(rxExtract, { check: rxGiven('RXExtract') }),
  RXReplace: textRow(rxReplace, { check: rxGiven('RXReplace', true, true) }),
  Split: textRow(split),
  Substitute: row(substitute),
  Substring: textRow(mid),
  Trim: textRow(trimmed),
  Upper: textRow((s) => String(s).toUpperCase()),
};
/** The table: each name the catalogue lists (and the screen's Marked) - its grammar with its answer here. */
export const FUNCTIONS = Object.freeze(Object.fromEntries([...Object.entries(CATALOGUE.functions), ...Object.entries(CATALOGUE.screen_only)]
  .map(([name, shape]) => [name, Object.freeze({ ...shape, ...IMPL[name] })])));
const BY_NAME = new Map(Object.keys(FUNCTIONS).map((name) => [name.toLowerCase(), name]));
/** Each function as the formula's signature line says it (lead 11-07) - the catalogue's words. Marked reads the page's
 *  markings, which a column's formula (the server's calculator) has none of. */
export const SIGNATURES = Object.freeze(Object.entries(CATALOGUE.functions).map(([name, fn]) => ({ name, args: fn.says })));
// Names not built, each refused with its sentence (the catalogue's not_yet).
const NOT_YET = CATALOGUE.not_yet;

// ── reading the text ──────────────────────────────────────────────────────────────────────────────────────────────
const KEYWORDS = new Set(['and', 'or', 'xor', 'not', 'case', 'when', 'then', 'else', 'end', 'is', 'null', 'true', 'false', 'distinct']);
const OPS = ['<=>', '<=', '>=', '<>', '!=', '~=', '<', '>', '=', '+', '-', '*', '/', '%', '^', '&', '(', ')', ','];
const NUMBER = /^(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?/;
// A sheet's cell A1 and range B1:B9 (owner 10-13: the sheet's own grammar) - a name with digits before «(» is a call (P10).
const CELL_TOKEN = /^([A-Za-z]{1,3}[0-9]{1,7})(?::([A-Za-z]{1,3}[0-9]{1,7}))?(?![A-Za-z0-9_])(?!\s*\()/;

function tokens(text) {
  const out = [];
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (/\s/.test(ch)) { i += 1; continue; }
    const at = i;
    const n = NUMBER.exec(text.slice(i));
    if (n) { out.push({ k: 'num', v: Number(n[0]), at }); i += n[0].length; continue; }
    if (ch === '"' || ch === "'") {
      let j = i + 1; let said = '';
      while (j < text.length && text[j] !== ch) {
        if (text[j] === '\\' && j + 1 < text.length && ESCAPED.includes(text[j + 1])) j += 1;
        said += text[j];
        j += 1;
      }
      if (j >= text.length) throw new ExpressionError(say('text_open', { at: at + 1 }));
      out.push({ k: 'str', v: said, at });
      i = j + 1;
      continue;
    }
    if (ch === '[') {   // «]]» is a «]» inside a name (Spotfire's escape)
      let j = i + 1; let name = '';
      while (j < text.length && !(text[j] === ']' && text[j + 1] !== ']')) { name += text[j]; j += text[j] === ']' ? 2 : 1; }
      if (j >= text.length) throw new ExpressionError(say('name_open', { at: at + 1 }));
      out.push({ k: 'ref', v: name, at });
      i = j + 1;
      continue;
    }
    const cell = CELL_TOKEN.exec(text.slice(i));
    if (cell) {
      out.push(cell[2] ? { k: 'range', v: [cell[1].toUpperCase(), cell[2].toUpperCase()], at } : { k: 'cell', v: cell[1].toUpperCase(), at });
      i += cell[0].length;
      continue;
    }
    const word = /^[A-Za-z_][A-Za-z0-9_]*/.exec(text.slice(i));
    if (word) {
      const lw = word[0].toLowerCase();
      out.push(KEYWORDS.has(lw) ? { k: 'kw', v: lw, at } : { k: 'id', v: word[0], at });
      i += word[0].length;
      continue;
    }
    const op = OPS.find((o) => text.startsWith(o, i));
    if (op) { out.push({ k: 'op', v: op, at }); i += op.length; continue; }
    throw new ExpressionError(say('stray', { ch, at: at + 1 }));
  }
  out.push({ k: 'end', at: text.length });
  return out;
}

function parse(text, nodes = {}) {
  const ts = tokens(text);
  let p = 0;
  const op = (v) => ts[p].k === 'op' && ts[p].v === v;
  const kw = (v) => ts[p].k === 'kw' && ts[p].v === v;
  const where = () => (ts[p].k === 'end' ? say('at_end') : say('at', { at: ts[p].at + 1 }));
  const need = (test, what) => { if (!test()) throw new ExpressionError(say('expected', { what, where: where() })); p += 1; };
  const unexpected = () => new ExpressionError(say('unexpected', { snippet: text.slice(ts[p].at, ts[p].at + 12), where: where() }));
  // lowest first: or · xor · and · not · = <> <=> ~= · < > <= >= · Is Null · & · + - · * / % · unary - + · ^
  // (lead 10-13; & and ~= Ops · Prec, owner 11-09)
  const or = () => { let a = xor(); while (kw('or')) { p += 1; a = { t: 'or', a, b: xor() }; } return a; };
  const xor = () => { let a = and(); while (kw('xor')) { p += 1; a = { t: 'xor', a, b: and() }; } return a; };
  const and = () => { let a = not(); while (kw('and')) { p += 1; a = { t: 'and', a, b: not() }; } return a; };
  const not = () => { if (kw('not')) { p += 1; return { t: 'not', a: not() }; } return equality(); };
  const equality = () => {
    let a = relational();
    while (['=', '<>', '!=', '<=>', '~='].some(op)) {
      const o = ts[p].v; p += 1;
      if (o === '~=') {
        const pattern = relational();
        if (pattern.t !== 'lit' || typeof pattern.v !== 'string') throw new ExpressionError(say('quoted', { name: '«~=»', what: 'pattern' }));
        rx('«~=»', pattern.v, '');
        a = { t: 'match', a, pattern: pattern.v };
        continue;
      }
      a = { t: 'cmp', op: o === '!=' ? '<>' : o, a, b: relational() };
    }
    return a;
  };
  const relational = () => {
    let a = isNull();
    while (['<', '>', '<=', '>='].some(op)) { const o = ts[p].v; p += 1; a = { t: 'cmp', op: o, a, b: isNull() }; }
    return a;
  };
  const isNull = () => {
    const a = concat();
    if (!kw('is')) return a;
    p += 1;
    const negate = kw('not');
    if (negate) p += 1;
    need(() => kw('null'), say('want_null'));
    return { t: 'isnull', a, negate };
  };
  const concat = () => { let a = additive(); while (op('&')) { p += 1; a = { t: 'concat', a, b: additive() }; } return a; };
  const additive = () => { let a = multiplicative(); while (op('+') || op('-')) { const o = ts[p].v; p += 1; a = { t: 'arith', op: o, a, b: multiplicative() }; } return a; };
  const multiplicative = () => { let a = unary(); while (op('*') || op('/') || op('%')) { const o = ts[p].v; p += 1; a = { t: 'arith', op: o, a, b: unary() }; } return a; };
  const unary = () => {
    if (op('-') || op('+')) { const o = ts[p].v; p += 1; const a = unary(); return o === '-' ? { t: 'neg', a } : a; }
    return power();
  };
  // ^ before unary minus and from the right: -2 ^ 2 = -4, 2 ^ 3 ^ 2 = 512 (lead 10-13)
  const power = () => { const a = primary(); if (op('^')) { p += 1; return { t: 'arith', op: '^', a, b: unary() }; } return a; };
  const primary = () => {
    const tk = ts[p];
    if (tk.k === 'num' || tk.k === 'str') { p += 1; return { t: 'lit', v: tk.v }; }
    if (tk.k === 'ref') { p += 1; return { t: 'ref', name: tk.v }; }
    if (tk.k === 'cell') { p += 1; return { t: 'cell', at: tk.v }; }
    if (tk.k === 'range') { p += 1; return { t: 'range', from: tk.v[0], to: tk.v[1] }; }
    if (kw('null')) { p += 1; return { t: 'lit', v: null }; }
    if (kw('true') || kw('false')) { p += 1; return { t: 'lit', v: tk.v === 'true' }; }
    if (kw('case')) return caseOf();
    if (op('(')) { p += 1; const e = or(); need(() => op(')'), say('want_close')); return e; }
    if (tk.k === 'id') return call();
    throw tk.k === 'end' ? new ExpressionError(say('ends_soon')) : unexpected();
  };
  const call = () => {
    const tk = ts[p]; p += 1;
    const name = BY_NAME.get(tk.v.toLowerCase());
    if (!name && Object.prototype.hasOwnProperty.call(nodes, tk.v)) return nodeOf(tk.v);
    const lw = tk.v.toLowerCase();
    if (!name) throw new ExpressionError(say(Object.hasOwn(NOT_YET, lw) ? NOT_YET[lw] : 'no_function', { name: tk.v }));
    need(() => op('('), say('want_open_after', { name }));
    const distinct = kw('distinct');
    if (distinct) p += 1;
    const args = [];
    if (!op(')')) { args.push(or()); while (op(',')) { p += 1; args.push(or()); } }
    need(() => op(')'), say('want_close_of', { name }));
    const node = { t: 'call', name, fn: FUNCTIONS[name], args, distinct };
    arity(node);
    return node;
  };
  // type("key", …) - the node of that type with those keys, in the order its entity declares them (owner 3b97fcfb9)
  const nodeOf = (type) => {
    const { keys, id } = nodes[type];
    need(() => op('('), say('want_open_after', { name: type }));
    const args = [];
    if (!op(')')) { args.push(or()); while (op(',')) { p += 1; args.push(or()); } }
    need(() => op(')'), say('want_close_of', { name: type }));
    if (args.length !== keys.length) throw new ExpressionError(say('type_keys', { type, n: keys.length, s: keys.length === 1 ? '' : 's', keys: keys.join(', '), got: args.length }));
    return { t: 'node', type, keys, id, args };
  };
  const caseOf = () => {
    p += 1;
    const subject = kw('when') ? null : or();
    const whens = [];
    while (kw('when')) { p += 1; const when = or(); need(() => kw('then'), say('want_then')); whens.push({ when, then: or() }); }
    if (!whens.length) throw new ExpressionError(say('expected', { what: say('want_when'), where: where() }));
    let otherwise = null;
    if (kw('else')) { p += 1; otherwise = or(); }
    need(() => kw('end'), say('want_end'));
    return { t: 'case', subject, whens, otherwise };
  };
  const tree = or();
  if (ts[p].k !== 'end') throw unexpected();
  return tree;
}

function arity({ name, fn, args, distinct }) {
  const n = args.length;
  const fits = fn.kind === 'mark' ? n === 1 || n === 2 : fn.kind === 'if' ? n === 3
    : fn.kind === 'row' ? n >= (fn.least ?? fn.arity) && n <= fn.arity
      : fn.pair ? n === 2
        : fn.params ? n === 1 + fn.params
          : fn.rowwise ? n >= 1
            : fn.none ? n <= 1 : n === 1;
  const counts = (from, to) => Array.from({ length: to - from + 1 }, (_, k) => from + k).join(' or ');
  const want = fn.kind === 'mark' ? '1 or 2' : fn.kind === 'if' ? '3' : fn.kind === 'row' ? counts(fn.least ?? fn.arity, fn.arity) : fn.pair ? '2' : fn.params ? String(1 + fn.params)
    : fn.rowwise ? '1 or more' : fn.none ? '0 or 1' : '1';
  if (!fits) throw new ExpressionError(say('takes', { name, want, s: want === '1' ? '' : 's', n }));
  if (fn.check) fn.check(args);
  if (distinct && (fn.kind !== 'fold' || fn.pair || (fn.rowwise && n > 1))) throw new ExpressionError(say('distinct', { name }));
}

const children = (node) => [node.a, node.b, node.subject, node.otherwise, ...(node.args || []),
  ...(node.whens || []).flatMap((w) => [w.when, w.then])].filter(Boolean);
/** Does `node` read a row's value outside any fold - then the answer is one per row. */
const rowLevel = (node) => node.t === 'ref' || (node.t === 'call' && node.fn.kind === 'mark')
  || (!(node.t === 'call' && node.fn.kind === 'fold') && children(node).some(rowLevel))
  || (node.t === 'call' && node.fn.kind === 'fold' && !!node.fn.rowwise && node.args.length > 1 && node.args.some(rowLevel));   // several arguments fold within the row
// Marked's way is steps, not a value's name - not among the names a row must have.
const namesOf = (node, out = new Set()) => {
  if (node.t === 'ref') out.add(node.name);
  (node.t === 'call' && node.fn.kind === 'mark' ? node.args.slice(0, 1) : children(node)).forEach((c) => namesOf(c, out));
  return out;
};

// A sheet's cell addresses - the one seat: the calculator's references and the sheet kind's grid (kinds/sheet.js).
const column = (letters) => [...letters].reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0);
/** 1 -> A, 27 -> AA. */
export const letters = (n) => (n > 0 ? letters(Math.floor((n - 1) / 26)) + String.fromCharCode(65 + ((n - 1) % 26)) : '');
/** 'B3' -> {c: 2, r: 3}; not an address - null. */
export const place = (at) => { const m = /^([A-Z]{1,3})([1-9][0-9]{0,6})$/.exec(String(at || '')); return m ? { c: column(m[1]), r: Number(m[2]) } : null; };
export const address = (c, r) => `${letters(c)}${r}`;
/** A range's cells, a row at a time (B1:C2 -> B1 C1 B2 C2). */
export function rangeCells(from, to) {
  const a = place(from); const b = place(to);
  if (!a || !b) return [];
  const out = [];
  for (let r = Math.min(a.r, b.r); r <= Math.max(a.r, b.r); r += 1) {
    for (let c = Math.min(a.c, b.c); c <= Math.max(a.c, b.c); c += 1) out.push(`${letters(c)}${r}`);
  }
  return out;
}
const cellsOf = (node, out = new Set()) => {
  if (node.t === 'cell') out.add(node.at);
  if (node.t === 'range') rangeCells(node.from, node.to).forEach((c) => out.add(c));
  children(node).forEach((c) => cellsOf(c, out));
  return out;
};

/** A text read once. @returns {{ok: true, tree, perRow: boolean, names: string[]} | {ok: false, why: string}} */
export function compile(text, page = {}) {
  try {
    // nodes: the page's node types {type: {keys: [names in declared order], id(keys) -> node id}} - type("key") (screen only)
    const tree = parse(String(text || ''), page.nodes || {});
    return { ok: true, tree, perRow: rowLevel(tree), names: [...namesOf(tree)], cells: [...cellsOf(tree)] };
  } catch (e) {
    if (e instanceof ExpressionError) return { ok: false, why: e.message };
    throw e;
  }
}

// ── answering ─────────────────────────────────────────────────────────────────────────────────────────────────────
const cellOf = (r, name) => (r && typeof r.get === 'function' ? r.get(name) : r ? r[name] : undefined);
const timeOfRow = (r) => {
  const at = r && (typeof r.get === 'function' ? r.at : r.$at);
  const t = typeof at === 'number' ? at : typeof at === 'string' ? Date.parse(at) : NaN;
  return Number.isFinite(t) ? t : null;
};
/** A value's items for a fold, with the row's time unless a read carries its own; a list counts as its items. */
const itemsOf = (v, t) => {
  if (v instanceof Reads) return v.items.flatMap((it) => itemsOf(it.value, Number.isFinite(it.t) ? it.t : null));
  if (Array.isArray(v)) return v.flatMap((x) => itemsOf(x, t));
  return isBlank(v) ? [] : [{ value: v, t }];
};
/** A row's one value of a name - several distinct ones cannot be used row by row. */
const oneOf = (v, name) => {
  if (!(v instanceof Reads) && !Array.isArray(v)) return isBlank(v) ? null : v;
  const values = distinctValues(itemsOf(v, null));
  if (values.length > 1) throw new SeveralValues(name);
  return values.length ? values[0] : null;
};
const bool = (v) => (v === true || v === false ? v : null);
/** A value an operator cannot take as a number: not empty, and not a number-text. Spotfire refuses text × number as an
 *  expression (observed 10-13); our columns carry no type, so the row is empty and counted (lead 10-13 ①). */
const notNumber = (v) => !isBlank(v) && numberOf(v) === null;
const arith = (o, a, b) => {
  const x = numberOf(a); const y = numberOf(b);
  if (x === null || y === null) return null;
  if (o === '+') return x + y;
  if (o === '-') return x - y;
  if (o === '*') return x * y;
  if (o === '/') return y === 0 ? null : x / y;
  if (o === '%') return y === 0 ? null : x - y * Math.floor(x / y);   // as Mod (lead 10-13)
  return x ** y;
};
function compare(o, a, b) {
  const blankA = isBlank(a); const blankB = isBlank(b);
  if (o === '<=>') { if (blankA || blankB) return blankA && blankB; o = '='; }
  if (blankA || blankB) return null;
  let x = a; let y = b;
  if (typeof x !== typeof y) {
    x = numberOf(a); y = numberOf(b);
    if (x === null || y === null) return null;   // two kinds that are not both numbers
  }
  const c = order(x, y);
  return o === '=' ? c === 0 : o === '<>' ? c !== 0 : o === '<' ? c < 0 : o === '>' ? c > 0 : o === '<=' ? c <= 0 : c >= 0;
}

/** The same column of a node over the same rows, worked once (If's and Case's conditions run over the whole column). */
function columnOf(node, ctx, test) {
  if (!ctx.memo.has(node)) ctx.memo.set(node, new WeakMap());
  const byRows = ctx.memo.get(node);
  if (!byRows.has(ctx.rows)) byRows.set(ctx.rows, ctx.rows.map((r) => test({ ...ctx, row: r })));
  return byRows.get(ctx.rows);
}
const indexOfRow = (ctx) => {
  if (!ctx.memo.has(ctx.rows)) ctx.memo.set(ctx.rows, new Map(ctx.rows.map((r, i) => [r, i])));
  return ctx.memo.get(ctx.rows).get(ctx.row);
};

function value(node, ctx) {
  switch (node.t) {
    case 'lit': return node.v;
    case 'ref':
      if (!ctx.row) throw new ExpressionError(say('row_value', { name: node.name }));
      return oneOf(cellOf(ctx.row, node.name), node.name);
    case 'neg': { const a = value(node.a, ctx); if (notNumber(a)) ctx.notNumber.add(ctx.row); const x = numberOf(a); return x === null ? null : -x; }
    case 'arith': {
      const a = value(node.a, ctx); const b = value(node.b, ctx);
      if (notNumber(a) || notNumber(b)) ctx.notNumber.add(ctx.row);
      return finite(arith(node.op, a, b));
    }
    case 'cmp': return compare(node.op, value(node.a, ctx), value(node.b, ctx));
    case 'concat': { const a = value(node.a, ctx); const b = value(node.b, ctx); return a === null || b === null ? null : String(a) + String(b); }
    case 'match': { const a = value(node.a, ctx); return a === null ? null : !matches(rx('«~=»', node.pattern, '').compiled, String(a)).next().done; }
    case 'not': { const a = bool(value(node.a, ctx)); return a === null ? null : !a; }
    case 'and': { const a = bool(value(node.a, ctx)); const b = bool(value(node.b, ctx)); return a === false || b === false ? false : a && b ? true : null; }
    case 'or': { const a = bool(value(node.a, ctx)); const b = bool(value(node.b, ctx)); return a === true || b === true ? true : a === false && b === false ? false : null; }
    case 'xor': { const a = bool(value(node.a, ctx)); const b = bool(value(node.b, ctx)); return a === null || b === null ? null : a !== b; }
    case 'isnull': {
      let v;
      try { v = value(node.a, ctx); } catch (e) { if (e instanceof SeveralValues) return node.negate; throw e; }
      return node.negate ? !isBlank(v) : isBlank(v);
    }
    case 'case': return caseValue(node, ctx);
    case 'cell': return sheetCell(ctx, node.at);
    case 'range': return rangeCells(node.from, node.to).map((at) => sheetCell(ctx, at));
    case 'node': {
      const keys = node.args.map((a) => value(a, ctx));
      return keys.some(isBlank) ? null : node.id(Object.fromEntries(node.keys.map((k, i) => [k, keys[i]])));
    }
    case 'call':
      if (node.fn.kind === 'if') return ifValue(node, ctx);
      if (node.fn.kind === 'mark') return markedValue(node, ctx);
      if (node.fn.kind === 'row') return finite(node.fn.fn(...node.args.map((a) => value(a, ctx)), ...(node.fn.zoned ? [ctx] : [])));
      return finite(foldValue(node, ctx));
    default: throw new ExpressionError(say('cannot_answer', { t: node.t }));
  }
}

/** Marked("name") - is this row in the page's marking `name`; Marked("name", [way]) - is one of the way's end nodes in it
 *  (lead 10-13). A way that reaches nothing from this row: unknown (null), not false. The page answers who is in a
 *  marking (ctx.marked, a hub by its members); without it the name is refused - the server's calculator has no markings. */
function markedValue(node, ctx) {
  if (typeof ctx.marked !== 'function') throw new ExpressionError(say('screen_marks', { name: 'Marked' }));
  if (!ctx.row) throw new ExpressionError(say('marked_row'));
  const [nameArg, way] = node.args;
  const name = String(value(nameArg, { ...ctx, row: null }));
  // The page answers each node: true · false · unknown (null) - its marking layer (lead 10-13, owner): nothing computed here.
  const said = (id) => { const v = ctx.marked(name, id); return v === true || v === false ? v : null; };
  if (!way) return said(ctx.row.id);
  if (way.t !== 'ref') throw new ExpressionError(say('marked_way'));
  const ends = typeof ctx.row.endsOf === 'function' ? ctx.row.endsOf(way.name) : null;
  if (!ends || !ends.length) return null;
  const each = ends.map(said);
  return each.some((v) => v === true) ? true : each.every((v) => v === false) ? false : null;
}

/** A1 - the sheet answers its cells' values (ctx.cell); without it the name is refused - the sheet's grammar alone. */
function sheetCell(ctx, at) {
  if (typeof ctx.cell !== 'function') throw new ExpressionError(say('cell_sheet', { at }));
  const v = ctx.cell(at);
  return v === undefined ? null : v;
}

function foldValue(node, ctx) {
  const { fn, args } = node;
  if (fn.none && !args.length) return ctx.rows.length;   // Count(): the rows
  if (fn.rowwise && args.length > 1 && fn.within) return fn.within(args.map((a) => value(a, ctx)));
  if (fn.rowwise && args.length > 1) return fn.fn(args.flatMap((a) => itemsOf(value(a, ctx), null))).value;
  const across = (arg, r) => (arg.t === 'ref' ? cellOf(r, arg.name) : value(arg, { ...ctx, row: r }));
  if (fn.pair) {
    const pairs = [];
    for (const r of ctx.rows) {
      const x = oneOf(across(args[0], r), '');
      const y = oneOf(across(args[1], r), '');
      if (!isBlank(x) && !isBlank(y)) pairs.push({ x, y });
    }
    return fn.fn(pairs).value;
  }
  // An argument that reads a sheet's cells and no row's value (Sum(B1:B9)) folds its own items once, not once a row.
  const once = !rowLevel(args[0]) && cellsOf(args[0]).size > 0;
  let items = once ? itemsOf(value(args[0], { ...ctx, row: null }), null)
    : ctx.rows.flatMap((r) => itemsOf(across(args[0], r), timeOfRow(r)));
  if (node.distinct) items = [...new Map(items.map((it) => [spelling(it.value), it])).values()];
  const params = args.slice(1).map((a) => numberOf(value(a, { ...ctx, row: null })));
  if (BY_TIME[node.name] && args[0].t === 'ref' && ctx.types[args[0].name] === 'datetime') return BY_TIME[node.name](items).value;
  return fn.fn(items, params).value;
}

// An If's branches fold only the rows their condition sends them (Logic «More about using if»).
function ifValue(node, ctx) {
  const [c, a, b] = node.args;
  if (!ctx.row) { const cv = bool(value(c, ctx)); return cv === true ? value(a, ctx) : cv === false ? value(b, ctx) : null; }
  const conds = columnOf(c, ctx, (one) => bool(value(c, one)));
  const cv = conds[indexOfRow(ctx)];
  if (cv === null) return null;
  return value(cv ? a : b, { ...ctx, rows: ctx.rows.filter((_, i) => conds[i] === cv) });
}

// A when is judged on the whole column; its then folds the rows it and no earlier when takes (Logic «More about using
// case»); a when that is not true goes on, and no else is empty (lead 10-13).
function caseValue(node, ctx) {
  const test = (w, one) => (node.subject ? compare('=', value(node.subject, one), value(w, one)) : bool(value(w, one))) === true;
  if (!ctx.row) {
    const hit = node.whens.find((w) => test(w.when, ctx));
    return hit ? value(hit.then, ctx) : node.otherwise ? value(node.otherwise, ctx) : null;
  }
  const cols = node.whens.map((w) => columnOf(w.when, ctx, (one) => test(w.when, one)));
  const firstTrue = ctx.rows.map((_, i) => cols.findIndex((col) => col[i]));
  const k = firstTrue[indexOfRow(ctx)];
  const branch = k >= 0 ? node.whens[k].then : node.otherwise;
  if (!branch) return null;
  return value(branch, { ...ctx, rows: ctx.rows.filter((_, i) => firstTrue[i] === k) });
}

/**
 * Answer a compiled expression over rows: one answer, or one per row when it reads a row's value outside a fold.
 * @returns {{value: *} | {values: Array} | {several: string} | {why: string}}
 */
export function run(compiled, rows, page = {}) {
  if (!compiled.ok) return { why: compiled.why };
  // notNumber: the rows an operator met a text that is not a number on - their answer is empty; marked: the page's
  // markings (screen only), for Marked(); types: {column: "datetime"} (table_config's column_types words); cell: a
  // sheet's cell values by address (A1), for cell references
  // zone: the IANA name dates are cut in (ZONE_DEFAULT when the page gives none); notTime: the rows a date function met
  // a value that is not a time on
  const zone = page.zone || productZone();
  try { clockOf(0, zone); } catch (e) { if (e instanceof RangeError) return { why: say('not_zone', { zone }) }; throw e; }
  const ctx = { rows: rows || [], row: null, memo: new Map(), notNumber: new Set(), notTime: new Set(), marked: page.marked,
    types: page.types || {}, cell: page.cell, zone };
  try {
    if (!compiled.perRow) { const v = finite(value(compiled.tree, ctx)); return { value: v, notNumber: ctx.notNumber.size, notTime: ctx.notTime.size }; }
    const values = ctx.rows.map((r) => finite(value(compiled.tree, { ...ctx, row: r })));
    return { values, notNumber: ctx.notNumber.size, notTime: ctx.notTime.size };
  } catch (e) {
    if (e instanceof SeveralValues) return { several: e.message };
    if (e instanceof ExpressionError) return { why: e.message };
    throw e;
  }
}

/** One fold by its name over items {value, t} - the test bed's reduce chips (testbed/aggregate.js); `n` the items it
 *  folded (lists as their items, blanks out). */
export function foldItems(name, items) {
  const fn = FUNCTIONS[name];
  if (!fn || fn.kind !== 'fold' || fn.pair || fn.params) throw new Error(`Unknown reduce: ${name}`);
  const flat = items.flatMap((it) => itemsOf(it.value, Number.isFinite(it.t) ? it.t : null));
  return { ...fn.fn(flat), n: flat.length };
}
