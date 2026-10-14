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

import { isBlank } from './absent.js';
import { numberOf } from './walk/reach_table.js';
import { parseServerInstant } from './server_time.js';

/** A refusal in words - what the expression box says. */
export class ExpressionError extends Error {}
/** A row-by-row use of a value the row holds several of - the slot says «several», as an unfolded slot does. */
export class SeveralValues extends Error {}
/** Several reads of one value, each with its time (ms or null) - what a walk gives a row. */
export class Reads {
  constructor(items) { this.items = items; }
}

const spelling = (v) => JSON.stringify(v);

// ── dates ─────────────────────────────────────────────────────────────────────────────────────────────────────────
/** The server's ingestion_settings "expression_time_zone" default (server/expression.py ZONE_DEFAULT). */
export const ZONE_DEFAULT = 'Asia/Seoul';
/** The server's setting as the page read it (GET /api/ledger/declaration's expression_time_zone) - one per page, as the
 *  server has one; a run's page.zone before it, ZONE_DEFAULT when neither (lead fe2ba4b1f ①). */
let pageZone = null;
export function useZone(name) { pageZone = typeof name === 'string' && name.trim() ? name.trim() : null; }
/** The one shape a time is read in - the server's TIME (expression.py) is the same pattern. */
const TIME = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?\s*(Z|[+-]\d{2}:?\d{2})?$/;
const PARTS = Object.freeze({
  year: 'Year', yy: 'Year', quarter: 'Quarter', qq: 'Quarter', month: 'Month', mm: 'Month',
  day: 'Day', 'day of month': 'Day', dayofmonth: 'Day', dd: 'Day', week: 'Week', wk: 'Week',
  'day of week': 'DayOfWeek', dayofweek: 'DayOfWeek', weekday: 'DayOfWeek', dw: 'DayOfWeek', hour: 'Hour', hh: 'Hour',
});
const OTHER_PARTS = new Set(['minute', 'mi', 'second', 'ss', 'millisecond', 'ms', 'day of year', 'dayofyear', 'dy',
  'year and week', 'yearandweek', 'yywk', 'isoyear', 'isoweek']);
const clocks = new Map();
/** `zone`'s wall clock of an instant (ms): {y, M, d, h, mi, s}. */
const clockOf = (ms, zone) => {
  if (!clocks.has(zone)) {
    clocks.set(zone, new Intl.DateTimeFormat('en-US', { timeZone: zone, hourCycle: 'h23', year: 'numeric', month: '2-digit',
      day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', era: 'short' }));
  }
  const p = Object.fromEntries(clocks.get(zone).formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  const year = Number(p.year);
  // an era'd year: 1 BC is the year 0 (outside 1 to 9999 - not a time, as the server)
  return { y: p.era === 'BC' ? 1 - year : year, M: Number(p.month), d: Number(p.day), h: Number(p.hour), mi: Number(p.minute),
    s: Number(p.second) };
};
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
  try { w = wallOf(v, pageZone || ZONE_DEFAULT); } catch (e) { if (!(e instanceof RangeError)) throw e; }
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
const dated = (f) => ({ kind: 'row', arity: 1, zoned: true,
  fn: (v, ctx) => {
    const w = wallOf(v, ctx.zone);
    if (!w) { if (!isBlank(v)) ctx.notTime.add(ctx.row); return null; }
    return f(w, ctx);
  } });
const datePart = (part, v, ctx) => {
  const name = typeof part === 'string' ? PARTS[part.trim().toLowerCase()] : undefined;
  if (!name) {
    const said = typeof part === 'string' ? part.trim().toLowerCase() : part;
    throw new ExpressionError(OTHER_PARTS.has(said) ? `DatePart «${said}» is not in this edition`
      : `DatePart takes a part name (year · quarter · month · day · week · day of week · hour) - got ${part}`);
  }
  return dated(PART_OF[name]).fn(v, ctx);
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

const fold = (fn, more = {}) => ({ kind: 'fold', fn, ...more });
const row = (arity, fn) => ({ kind: 'row', arity, fn });
const num1 = (f) => row(1, (a) => { const x = numberOf(a); return x === null ? null : f(x); });
const num2 = (f) => row(2, (a, b) => { const x = numberOf(a); const y = numberOf(b); return x === null || y === null ? null : f(x, y); });

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

export const FUNCTIONS = Object.freeze({
  Count: fold((items) => ({ value: items.length }), { none: true }),
  CountBig: fold((items) => ({ value: items.length }), { none: true }),
  UniqueCount: fold((items) => ({ value: distinctValues(items).length })),
  Sum: fold(numeric(sum), { rowwise: true }),
  Avg: fold(numeric(mean), { rowwise: true }),
  Min: fold(numeric((xs) => Math.min(...xs)), { rowwise: true }),
  Max: fold(numeric((xs) => Math.max(...xs)), { rowwise: true }),
  Median: fold(numeric(median), { rowwise: true }),
  Product: fold(numeric((xs) => xs.reduce((a, b) => a * b, 1)), { rowwise: true }),
  MeanDeviation: fold(numeric((xs) => mean(xs.map((v) => Math.abs(v - mean(xs))))), { rowwise: true }),
  MedianAbsoluteDeviation: fold(numeric((xs) => median(xs.map((v) => Math.abs(v - median(xs))))), { rowwise: true }),
  First: fold((items) => ({ value: items.length ? items[0].value : null })),
  Last: fold((items) => ({ value: items.length ? items[items.length - 1].value : null })),
  Latest: fold(latest),
  MostCommon: fold(mostCommon),
  UniqueConcatenate: fold((items) => ({ value: items.length ? distinctValues(items).sort(order).join(', ') : null })),
  StdDev: fold(numeric(sd)),
  Var: fold(numeric(svar)),
  StdErr: fold(numeric((xs) => (xs.length < 2 ? null : sd(xs) / Math.sqrt(xs.length)))),
  Range: fold(numeric((xs) => Math.max(...xs) - Math.min(...xs))),
  Q1: fold(numeric(q1)),
  Q3: fold(numeric(q3)),
  IQR: fold(numeric(iqr)),
  P10: fold(numeric((xs) => pct(xs, 0.1))),
  P90: fold(numeric((xs) => pct(xs, 0.9))),
  Percentile: fold(numeric((xs, [p]) => (p === null ? null : pct(xs, p / 100))), { params: 1 }),
  Percent: fold(numeric((xs, [p]) => (p === null ? null : Math.min(...xs) + (p / 100) * (Math.max(...xs) - Math.min(...xs)))), { params: 1 }),
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
  }), { params: 1 }),
  NthLargest: fold(numeric((xs, [n]) => (n === null || n < 1 ? null : sorted(xs).reverse()[Math.min(Math.floor(n), xs.length) - 1])), { params: 1 }),
  NthSmallest: fold(numeric((xs, [n]) => (n === null || n < 1 ? null : sorted(xs)[Math.min(Math.floor(n), xs.length) - 1])), { params: 1 }),
  L95: fold(numeric((xs) => (xs.length < 2 ? null : mean(xs) - (T95 * sd(xs)) / Math.sqrt(xs.length)))),
  U95: fold(numeric((xs) => (xs.length < 2 ? null : mean(xs) + (T95 * sd(xs)) / Math.sqrt(xs.length)))),
  // two columns: a row with either side empty is left out (lead 10-13)
  WeightedAverage: fold((pairs) => {
    const ps = pairNums(pairs);
    const w = sum(ps.map(([x]) => x));
    return { value: ps.length && w !== 0 ? sum(ps.map(([x, y]) => x * y)) / w : null };
  }, { pair: true }),
  Covariance: fold((pairs) => {
    const ps = pairNums(pairs);
    if (ps.length < 2) return { value: null };
    const mx = mean(ps.map(([x]) => x)); const my = mean(ps.map(([, y]) => y));
    return { value: sum(ps.map(([x, y]) => (x - mx) * (y - my))) / (ps.length - 1) };
  }, { pair: true }),
  ValueForMax: fold(valueFor(Math.max, false), { pair: true }),
  ValueForMin: fold(valueFor(Math.min, false), { pair: true }),
  LastValueForMax: fold(valueFor(Math.max, true), { pair: true }),
  LastValueForMin: fold(valueFor(Math.min, true), { pair: true }),
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
  PI: row(0, () => Math.PI),
  Sin: num1(Math.sin),
  Cos: num1(Math.cos),
  Tan: num1(Math.tan),
  ASin: num1((x) => (Math.abs(x) > 1 ? null : Math.asin(x))),
  ACos: num1((x) => (Math.abs(x) > 1 ? null : Math.acos(x))),
  ATan: num1(Math.atan),
  ATan2: num2((y, x) => Math.atan2(y, x)),
  If: { kind: 'if' },
  // dates (lead fe2ba4b1f) - on the zone's wall clock
  Date: dated((w, ctx) => { const mid = { y: w.y, M: w.M, d: w.d, h: 0, mi: 0, s: 0 }; return timeText({ ...mid, ms: 0, off: offsetOfWall(mid, ctx.zone) }); }),
  DateTime: dated(timeText),
  ...Object.fromEntries(Object.entries(PART_OF).map(([name, f]) => [name, dated(f)])),
  DatePart: { kind: 'row', arity: 2, zoned: true, fn: datePart },
  // Spotfire's Marked() (lead 10-13): the page's marking - screen only, the markings come in ctx.
  Marked: { kind: 'mark' },
});
const BY_NAME = new Map(Object.keys(FUNCTIONS).map((name) => [name.toLowerCase(), name]));
// task/SPOTFIRE_FUNCTIONS.md names this edition does not build (the vectors' out_of_edition) - refused by name.
const NOT_YET = new Set(['normdist', 'norminv', 'tdist', 'tinv', 'chidist', 'chiinv', 'fdist', 'finv', 'lag', 'lead',
  'rand', 'randbetween', 'concatenate', 'reach']);

// ── reading the text ──────────────────────────────────────────────────────────────────────────────────────────────
const KEYWORDS = new Set(['and', 'or', 'xor', 'not', 'case', 'when', 'then', 'else', 'end', 'is', 'null', 'true', 'false', 'distinct']);
const OPS = ['<=>', '<=', '>=', '<>', '!=', '<', '>', '=', '+', '-', '*', '/', '%', '^', '(', ')', ','];
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
      const close = text.indexOf(ch, i + 1);
      if (close < 0) throw new ExpressionError(`A text opened at ${at + 1} does not close`);
      out.push({ k: 'str', v: text.slice(i + 1, close), at });
      i = close + 1;
      continue;
    }
    if (ch === '[') {   // «]]» is a «]» inside a name (Spotfire's escape)
      let j = i + 1; let name = '';
      while (j < text.length && !(text[j] === ']' && text[j + 1] !== ']')) { name += text[j]; j += text[j] === ']' ? 2 : 1; }
      if (j >= text.length) throw new ExpressionError(`A name opened at ${at + 1} does not close`);
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
    throw new ExpressionError(ch === '&' ? '«&» is not in this edition' : `«${ch}» at ${at + 1} is not part of an expression`);
  }
  out.push({ k: 'end', at: text.length });
  return out;
}

function parse(text, nodes = {}) {
  const ts = tokens(text);
  let p = 0;
  const op = (v) => ts[p].k === 'op' && ts[p].v === v;
  const kw = (v) => ts[p].k === 'kw' && ts[p].v === v;
  const where = () => (ts[p].k === 'end' ? 'at the end' : `at ${ts[p].at + 1}`);
  const need = (test, what) => { if (!test()) throw new ExpressionError(`${what} expected ${where()}`); p += 1; };
  // lowest first: or · xor · and · not · = <> <=> · < > <= >= · Is Null · + - · * / % · unary - + · ^ (lead 10-13)
  const or = () => { let a = xor(); while (kw('or')) { p += 1; a = { t: 'or', a, b: xor() }; } return a; };
  const xor = () => { let a = and(); while (kw('xor')) { p += 1; a = { t: 'xor', a, b: and() }; } return a; };
  const and = () => { let a = not(); while (kw('and')) { p += 1; a = { t: 'and', a, b: not() }; } return a; };
  const not = () => { if (kw('not')) { p += 1; return { t: 'not', a: not() }; } return equality(); };
  const equality = () => {
    let a = relational();
    while (['=', '<>', '!=', '<=>'].some(op)) { const o = ts[p].v; p += 1; a = { t: 'cmp', op: o === '!=' ? '<>' : o, a, b: relational() }; }
    return a;
  };
  const relational = () => {
    let a = isNull();
    while (['<', '>', '<=', '>='].some(op)) { const o = ts[p].v; p += 1; a = { t: 'cmp', op: o, a, b: isNull() }; }
    return a;
  };
  const isNull = () => {
    const a = additive();
    if (!kw('is')) return a;
    p += 1;
    const negate = kw('not');
    if (negate) p += 1;
    need(() => kw('null'), '«null»');
    return { t: 'isnull', a, negate };
  };
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
    if (op('(')) { p += 1; const e = or(); need(() => op(')'), '«)»'); return e; }
    if (tk.k === 'id') return call();
    throw new ExpressionError(tk.k === 'end' ? 'The expression ends too soon' : `«${text.slice(tk.at, tk.at + 12)}» ${where()} is not expected`);
  };
  const call = () => {
    const tk = ts[p]; p += 1;
    const name = BY_NAME.get(tk.v.toLowerCase());
    if (!name && Object.prototype.hasOwnProperty.call(nodes, tk.v)) return nodeOf(tk.v);
    if (!name) throw new ExpressionError(NOT_YET.has(tk.v.toLowerCase()) ? `${tk.v} is not in this edition` : `No function named ${tk.v}`);
    need(() => op('('), `«(» after ${name}`);
    const distinct = kw('distinct');
    if (distinct) p += 1;
    const args = [];
    if (!op(')')) { args.push(or()); while (op(',')) { p += 1; args.push(or()); } }
    need(() => op(')'), `«)» closing ${name}`);
    const node = { t: 'call', name, fn: FUNCTIONS[name], args, distinct };
    arity(node);
    return node;
  };
  // type("key", …) - the node of that type with those keys, in the order its entity declares them (owner 3b97fcfb9)
  const nodeOf = (type) => {
    const { keys, id } = nodes[type];
    need(() => op('('), `«(» after ${type}`);
    const args = [];
    if (!op(')')) { args.push(or()); while (op(',')) { p += 1; args.push(or()); } }
    need(() => op(')'), `«)» closing ${type}`);
    if (args.length !== keys.length) throw new ExpressionError(`${type} takes ${keys.length} key${keys.length === 1 ? '' : 's'} (${keys.join(', ')}) - got ${args.length}`);
    return { t: 'node', type, keys, id, args };
  };
  const caseOf = () => {
    p += 1;
    const subject = kw('when') ? null : or();
    const whens = [];
    while (kw('when')) { p += 1; const when = or(); need(() => kw('then'), '«then»'); whens.push({ when, then: or() }); }
    if (!whens.length) throw new ExpressionError(`«when» expected ${where()}`);
    let otherwise = null;
    if (kw('else')) { p += 1; otherwise = or(); }
    need(() => kw('end'), '«end»');
    return { t: 'case', subject, whens, otherwise };
  };
  const tree = or();
  if (ts[p].k !== 'end') throw new ExpressionError(`«${text.slice(ts[p].at, ts[p].at + 12)}» ${where()} is not expected`);
  return tree;
}

function arity({ name, fn, args, distinct }) {
  const n = args.length;
  const fits = fn.kind === 'mark' ? n === 1 || n === 2 : fn.kind === 'if' ? n === 3
    : fn.kind === 'row' ? n === fn.arity
      : fn.pair ? n === 2
        : fn.params ? n === 1 + fn.params
          : fn.rowwise ? n >= 1
            : fn.none ? n <= 1 : n === 1;
  const want = fn.kind === 'mark' ? '1 or 2' : fn.kind === 'if' ? '3' : fn.kind === 'row' ? String(fn.arity) : fn.pair ? '2' : fn.params ? String(1 + fn.params)
    : fn.rowwise ? '1 or more' : fn.none ? '0 or 1' : '1';
  if (!fits) throw new ExpressionError(`${name} takes ${want} argument${want === '1' ? '' : 's'} - got ${n}`);
  if (distinct && (fn.kind !== 'fold' || fn.pair || (fn.rowwise && n > 1))) throw new ExpressionError(`distinct goes in a one-column aggregation, not ${name}`);
}

const children = (node) => [node.a, node.b, node.subject, node.otherwise, ...(node.args || []),
  ...(node.whens || []).flatMap((w) => [w.when, w.then])].filter(Boolean);
/** Does `node` read a row's value outside any fold - then the answer is one per row. */
const rowLevel = (node) => node.t === 'ref' || (node.t === 'call' && node.fn.kind === 'mark')
  || (!(node.t === 'call' && node.fn.kind === 'fold') && children(node).some(rowLevel));
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
      if (!ctx.row) throw new ExpressionError(`[${node.name}] is a row's value - fold it (Avg([${node.name}])) or use it row by row`);
      return oneOf(cellOf(ctx.row, node.name), node.name);
    case 'neg': { const a = value(node.a, ctx); if (notNumber(a)) ctx.notNumber.add(ctx.row); const x = numberOf(a); return x === null ? null : -x; }
    case 'arith': {
      const a = value(node.a, ctx); const b = value(node.b, ctx);
      if (notNumber(a) || notNumber(b)) ctx.notNumber.add(ctx.row);
      return finite(arith(node.op, a, b));
    }
    case 'cmp': return compare(node.op, value(node.a, ctx), value(node.b, ctx));
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
    default: throw new ExpressionError(`Cannot answer ${node.t}`);
  }
}

/** Marked("name") - is this row in the page's marking `name`; Marked("name", [way]) - is one of the way's end nodes in it
 *  (lead 10-13). A way that reaches nothing from this row: unknown (null), not false. The page answers who is in a
 *  marking (ctx.marked, a hub by its members); without it the name is refused - the server's calculator has no markings. */
function markedValue(node, ctx) {
  if (typeof ctx.marked !== 'function') throw new ExpressionError("Marked is the screen's - it reads the page's markings");
  if (!ctx.row) throw new ExpressionError('Marked is a row\'s - use it row by row');
  const [nameArg, way] = node.args;
  const name = String(value(nameArg, { ...ctx, row: null }));
  // The page answers each node: true · false · unknown (null) - its marking layer (lead 10-13, owner): nothing computed here.
  const said = (id) => { const v = ctx.marked(name, id); return v === true || v === false ? v : null; };
  if (!way) return said(ctx.row.id);
  if (way.t !== 'ref') throw new ExpressionError('Marked takes a way in brackets second - Marked("B", [in_container])');
  const ends = typeof ctx.row.endsOf === 'function' ? ctx.row.endsOf(way.name) : null;
  if (!ends || !ends.length) return null;
  const each = ends.map(said);
  return each.some((v) => v === true) ? true : each.every((v) => v === false) ? false : null;
}

/** A1 - the sheet answers its cells' values (ctx.cell); without it the name is refused - the sheet's grammar alone. */
function sheetCell(ctx, at) {
  if (typeof ctx.cell !== 'function') throw new ExpressionError(`Cell references are the sheet's - ${at} reads a sheet's cell`);
  const v = ctx.cell(at);
  return v === undefined ? null : v;
}

function foldValue(node, ctx) {
  const { fn, args } = node;
  if (fn.none && !args.length) return ctx.rows.length;   // Count(): the rows
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
  const zone = page.zone || pageZone || ZONE_DEFAULT;
  try { clockOf(0, zone); } catch (e) { if (e instanceof RangeError) return { why: `«${zone}» is not a time zone` }; throw e; }
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
