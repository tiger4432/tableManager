/**
 * expression_vectors -- the screen calculator (src/expression.js) solves contracts/expression/vectors.json as it is.
 *
 * WHAT IT SCORES
 *   V  every scored vector: the expression over its rows gives `expect` (one answer) or `expect_rows` (one per row);
 *      numbers to 1e-9 relative, null = empty
 *   O  every `ours` row the same way (Latest, list values, numbers written as text)
 *   N  the one answer to «is this a number» (walk/reach_table numberOf): sign · digits · point · exponent (lead 10-13)
 *   C  the census: every scored row ran, none of `unsettled` did, and the file is not empty
 * The file is the server calculator's exam too (lead 0b7d84462): an answer here that differs from it is a defect here.
 *
 * IT IMPORTS ITS SUBJECTS. A mutant is a whole module copy (lib/probe.mjs loadWithProbe).
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const FILE = JSON.parse(readFileSync(join(HERE, '..', '..', 'contracts', 'expression', 'vectors.json'), 'utf8'));
const REAL = { expr: await import('../src/expression.js'), reach: await import('../src/walk/reach_table.js') };

const near = (got, want) => (typeof want === 'number'
  ? typeof got === 'number' && Math.abs(got - want) <= 1e-9 * Math.max(1, Math.abs(want))
  : JSON.stringify(got) === JSON.stringify(want));
const ascii = (v) => JSON.stringify(v).replace(/[^\x20-\x7e]/g, '?').slice(0, 90);

function suite(M, quiet = false) {
  let ran = 0;
  const failures = [];
  const names = [];
  const ok = (name, cond, detail = '') => {
    ran += 1; names.push(name);
    if (cond) { if (!quiet) console.log(`  PASS ${name}`); return; }
    failures.push(name);
    if (!quiet) console.log(`  FAIL ${name}${detail ? ` -- ${detail}` : ''}`);
  };
  const scored = new Set();
  const score = (tag, v) => {
    scored.add(v.id);
    const c = M.expr.compile(v.expr);
    const out = M.expr.run(c, v.rows);
    const rows = 'expect_rows' in v;
    const good = rows
      ? Array.isArray(out.values) && out.values.length === v.expect_rows.length && out.values.every((x, i) => near(x, v.expect_rows[i]))
      : 'value' in out && near(out.value, v.expect);
    ok(`${tag}[${v.id}]`, good, `got ${ascii(out)} want ${ascii(rows ? v.expect_rows : v.expect)}`);
  };
  for (const v of FILE.vectors) score('V', v);
  for (const v of FILE.ours) score('O', v);

  const N = M.reach.numberOf;
  const numerals = [['29.50', 29.5], [' 1 ', 1], ['+2', 2], ['1e1', 10], ['.5', 0.5], ['5.', 5], ['-3E-2', -0.03], [7, 7]];
  const texts = ['29,50', '29 mm', '0x10', '', '  ', 'Infinity', '1e', '.', '+', null, true];
  ok('N1 numerals are numbers', numerals.every(([s, n]) => N(s) === n), ascii(numerals.map(([s]) => N(s))));
  ok('N2 anything else is not a number', texts.every((s) => N(s) === null), ascii(texts.map((s) => N(s))));

  const rowsInFile = FILE.vectors.length + FILE.ours.length;
  ok('C1 every scored row of the file ran, and the file is not empty', scored.size === rowsInFile && rowsInFile > 0, `${scored.size} of ${rowsInFile}`);
  ok('C2 no unsettled row is scored', (FILE.unsettled || []).every((u) => !scored.has(u.id)), ascii((FILE.unsettled || []).map((u) => u.id)));
  return { ran, failures, names };
}

console.log('== baseline ==');
const base = suite(REAL);
if (base.failures.length) {
  console.log(`\n${base.ran - base.failures.length} passed, ${base.failures.length} failed`);
  console.log(`ASSERTIONS ${base.ran} ${base.failures.length}`);
  process.exit(1);
}

const swap = (text, from, to) => {
  if (!text.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`);
  return text.split(from).join(to);
};
const E = 'expression.js';
const R = 'walk/reach_table.js';
const MUTANTS = [
  { id: 'X1', what: 'a fold counts empty values', catches: 'V[count.col]', file: E,
    mutate: (t) => swap(t, '  return isBlank(v) ? [] : [{ value: v, t }];', '  return [{ value: v, t }];') },
  { id: 'X2', what: '% keeps the sign of Arg1 (JS %), not Mod\'s', catches: 'V[remainder.negative]', file: E,
    mutate: (t) => swap(t, "  if (o === '%') return y === 0 ? null : x - y * Math.floor(x / y);", "  if (o === '%') return y === 0 ? null : x % y;") },
  { id: 'X3', what: 'the percentile is not f = (i - 1) / (n - 1)', catches: 'V[q3.col.doc]', file: E,
    mutate: (t) => swap(t, '  const s = sorted(xs); const h = (s.length - 1) * p;', '  const s = sorted(xs); const h = Math.min(s.length - 1, s.length * p);') },
  { id: 'X4', what: 'and is not three-valued: null and false says null', catches: 'V[and.null.false]', file: E,
    mutate: (t) => swap(t, 'return a === false || b === false ? false : a && b ? true : null; }', 'return a && b ? true : a === null || b === null ? null : false; }') },
  { id: 'X5', what: 'an If branch folds every row, not the rows its condition sends it', catches: 'V[if.branch.subset]', file: E,
    mutate: (t) => swap(t, '  return value(cv ? a : b, { ...ctx, rows: ctx.rows.filter((_, i) => conds[i] === cv) });', '  return value(cv ? a : b, ctx);') },
  { id: 'X6', what: 'a case then folds every row', catches: 'V[case.then.subset.min]', file: E,
    mutate: (t) => swap(t, '  return value(branch, { ...ctx, rows: ctx.rows.filter((_, i) => firstTrue[i] === k) });', '  return value(branch, ctx);') },
  { id: 'X7', what: 'StdDev divides by n', catches: 'V[stddev.col]', file: E,
    mutate: (t) => swap(t, '/ (xs.length - 1));\nconst sd', '/ xs.length);\nconst sd') },
  { id: 'X8', what: '^ from the left', catches: 'V[precedence.caret.right]', file: E,
    mutate: (t) => swap(t, "  const power = () => { const a = primary(); if (op('^')) { p += 1; return { t: 'arith', op: '^', a, b: unary() }; } return a; };",
      "  const power = () => { let a = primary(); while (op('^')) { p += 1; a = { t: 'arith', op: '^', a, b: primary() }; } return a; };") },
  { id: 'X9', what: 'unary minus before ^', catches: 'V[precedence.caret.unary]', file: E,
    mutate: (t) => swap(t, "    if (op('-') || op('+')) { const o = ts[p].v; p += 1; const a = unary(); return o === '-' ? { t: 'neg', a } : a; }",
      "    if (op('-') || op('+')) { const o = ts[p].v; p += 1; const a = primary(); const s = o === '-' ? { t: 'neg', a } : a; if (op('^')) { p += 1; return { t: 'arith', op: '^', a: s, b: unary() }; } return s; }") },
  { id: 'X10', what: 'Latest with no timed row gives nothing', catches: 'O[latest.untimed.one]', file: E,
    mutate: (t) => swap(t, '    return one.length === 1 ? { value: one[0] } : { value: null, untimed };', '    return { value: null, untimed };') },
  { id: 'X11', what: 'a list value is one item', catches: 'O[list.count]', file: E,
    mutate: (t) => swap(t, '  if (Array.isArray(v)) return v.flatMap((x) => itemsOf(x, t));', '  if (Array.isArray(v)) return [{ value: v, t }];') },
  { id: 'X12', what: 'a when that is null is taken as true', catches: 'V[case.null.condition]', file: E,
    mutate: (t) => swap(t, ': bool(value(w, one))) === true;', ': bool(value(w, one))) !== false;') },
  { id: 'X13', what: 'text compares without case', catches: 'V[equal.text.case]', file: E,
    mutate: (t) => swap(t, ": String(a) < String(b) ? -1 : String(a) > String(b) ? 1 : 0);", ": String(a).toLowerCase() < String(b).toLowerCase() ? -1 : String(a).toLowerCase() > String(b).toLowerCase() ? 1 : 0);") },
  { id: 'X14', what: 'distinct is read and dropped', catches: 'V[avg.distinct]', file: E,
    mutate: (t) => swap(t, '  if (node.distinct) items =', '  if (false) items =') },
  { id: 'X15', what: 'Count() counts nothing', catches: 'V[count.rows]', file: E,
    mutate: (t) => swap(t, '  if (fn.none && !args.length) return ctx.rows.length;', '  if (fn.none && !args.length) return 0;') },
  { id: 'X16', what: 'Round goes half up, not away from zero', catches: 'V[round.half.negative]', file: E,
    mutate: (t) => swap(t, '    const away = (v) => Math.sign(v) * Math.round(Math.abs(v));', '    const away = (v) => Math.round(v);') },
  { id: 'X17', what: 'two different values at the newest time: one is picked', catches: 'O[latest.tie]', file: E,
    mutate: (t) => swap(t, '  return at.length === 1 ? { value: at[0], untimed } : { value: null, tied: at.length, untimed };', '  return { value: at[0], untimed };') },
  { id: 'X18', what: 'a MostCommon tie keeps the one met last', catches: 'V[mostcommon.col.tie]', file: E,
    mutate: (t) => swap(t, '  for (const c of counts.values()) if (!best || c.n > best.n) best = c;', '  for (const c of counts.values()) if (!best || c.n >= best.n) best = c;') },
  { id: 'X20', what: 'an even median the lower middle', catches: 'V[median.col.even]', file: E,
    mutate: (t) => swap(t, ': (s[n / 2 - 1] + s[n / 2]) / 2; };', ': s[n / 2 - 1]; };') },
  { id: 'X21', what: 'a numeric fold of nothing 0, not empty', catches: 'V[sum.col.all.null]', file: E,
    mutate: (t) => swap(t, '  return { value: xs.length ? f(xs, params) : null, skipped: items.length - xs.length };', '  return { value: xs.length ? f(xs, params) : 0, skipped: items.length - xs.length };') },
  { id: 'X19', what: 'a numeral is whatever Number() reads (0x10 is 16)', catches: 'N2', file: R,
    mutate: (t) => swap(t, "  if (typeof value !== 'string' || !NUMERAL.test(value.trim())) return null;", "  if (typeof value !== 'string' || !value.trim()) return null;") },
];
const CONTROLS = [
  { id: 'K1', what: 'a local renamed', file: E, mutate: (t) => swap(t, 'const T95 = 1.959964;', 'const T95x = 1.959964;\nconst T95 = T95x;') },
  { id: 'K2', what: 'comment lines stripped', file: E, mutate: (t) => t.split('\n').filter((l) => !/^\s*\/\//.test(l)).join('\n') },
];
const KEY = { [E]: 'expr', [R]: 'reach' };
const run = async (m) => {
  const copy = (await loadWithProbe(join(SRC, m.file), { mutate: m.mutate })).module;
  return suite({ ...REAL, [KEY[m.file]]: copy }, true);
};
const scored = await scoreMutants(MUTANTS, run, { baselineRan: base.ran, baselineNames: base.names, title: '\n== defect mutants (each caught by its named line) ==' });
const controls = await scoreMutants(CONTROLS, run, { mustCatch: false, title: '\n== controls (each must wake nothing) ==' });
const failed = scored.wrong + controls.wrong;
const ran = base.ran + MUTANTS.length + CONTROLS.length;
console.log(`\n${ran - failed} passed, ${failed} failed`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed ? 1 : 0);
