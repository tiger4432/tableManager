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
import { entitySeedId } from '../src/rnd_board/api.js';

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = join(HERE, '..', 'src');
const FILE = JSON.parse(readFileSync(join(HERE, '..', '..', 'contracts', 'expression', 'vectors.json'), 'utf8'));
const REAL = { expr: await import('../src/expression.js'), reach: await import('../src/walk/reach_table.js'), slot: await import('../src/testbed/slot.js'),
  api: await import('../src/rnd_board/api.js') };
// The declaration answer a page reads, its zone another than Seoul's (E10).
const TOLD = await REAL.api.fetchDeclaration({ fetchImpl: async () => ({ ok: true, json: async () => ({ expression_time_zone: 'America/New_York' }) }) });

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
  // A mutated calculator is a copy with its own Reads class: the test bed's row hands it its reads in the copy's.
  const asCopy = (row) => (M.expr === REAL.expr ? row : { ...row, get: (n) => { const r = row.get(n); return r instanceof REAL.expr.Reads ? new M.expr.Reads(r.items) : r; } });
  const score = (tag, v) => {
    scored.add(v.id);
    // Screen only (a sheet): `nodes` the page's node types for type("key"), the id as the start row builds it.
    const nodes = v.nodes ? Object.fromEntries(Object.entries(v.nodes).map(([type, keys]) => [type, { keys, id: (k) => entitySeedId(type, k) }])) : null;
    const c = M.expr.compile(v.expr, nodes ? { nodes } : {});
    // A vector with a graph names its rows by node id; the screen reads them as the test bed does (testbed/slot.js calcRow).
    const index = v.graph ? M.reach.indexGraph(v.graph) : null;
    // Screen only (Marked): the vector fakes the page's marking layer. `types`: the columns' type words, as the server's run takes them.
    const page = v.markings ? { marked: (name, id) => { const m = v.markings[name] || {}; return (m.in || []).includes(id) ? true : (m.unknown || []).includes(id) ? null : false; } } : {};
    if (v.types) page.types = v.types;
    if (v.zone) page.zone = v.zone;
    if (v.cells) page.cell = (at) => v.cells[at];
    // Screen only (Reach): the vector fakes the walk's judgment of each row against its node - another node unknown
    if (v.reach) {
      const to = entitySeedId(v.reach.to.type, v.reach.to.keys);
      page.reach = (node, id) => (node !== to ? null : (v.reach.found || []).includes(id) ? true : (v.reach.unknown || []).includes(id) ? null : false);
    }
    const out = M.expr.run(c, index ? v.rows.map((id) => asCopy(M.slot.calcRow(index, new Set(index.nodes.keys()), id))) : v.rows, page);
    const rows = 'expect_rows' in v;
    const good = rows
      ? Array.isArray(out.values) && out.values.length === v.expect_rows.length && out.values.every((x, i) => near(x, v.expect_rows[i]))
      : 'value' in out && near(out.value, v.expect);
    ok(`${tag}[${v.id}]`, good && (!('expect_not_time' in v) || out.notTime === v.expect_not_time),
      `got ${ascii(out)} want ${ascii(rows ? v.expect_rows : v.expect)}`);
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
  // An operator that meets a text that is not a number (lead 10-13 ①): the row empty and counted once however many
  // operators met it; an empty value is empty and not counted.
  // A way's two answers refused; a way to several ends several values (lead 10-13).
  const g = M.reach.indexGraph({ nodes: [{ id: 'w', type: 'wafer', attributes: {} }, { id: 'd', type: 'die', attributes: { gate: 1 } },
    { id: 'e', type: 'die', attributes: {} }],
  edges: [{ source: 'w', target: 'd', predicate: 'inspected', qualifiers: { gate: 7 } }, { source: 'w', target: 'e', predicate: 'has', qualifiers: { n: 1 } },
    { source: 'w', target: 'd', predicate: 'has', qualifiers: { n: 2 } }] });
  const wRow = () => [asCopy(M.slot.calcRow(g, new Set(g.nodes.keys()), 'w'))];
  // A mutated calculator's copy has its own refusal class, so the row's refusal comes out thrown there - the sentence is the claim.
  let both;
  try { both = M.expr.run(M.expr.compile('[inspected.gate]'), wRow()); } catch (e) { both = { why: e && e.message }; }
  const many = M.expr.run(M.expr.compile('[has.n]'), wRow());
  ok('E2 a way whose end node and last edge both say the name is refused - two answers', /both a value of the node it reaches and of its edge/.test(String(both.why)), ascii(both));
  ok('E3 a way to two ends is several values row by row; folded, both', Boolean(many.several)
    && M.expr.run(M.expr.compile('Sum([has.n])'), wRow()).value === 3, ascii(many));
  // Marked without the page's markings is refused by name - the server's calculator has none.
  const blind = M.expr.run(M.expr.compile('Marked("B")'), [{ x: 1 }]);
  ok('E4 Marked with no page markings refused by name', /Marked is the screen's/.test(String(blind.why)), ascii(blind));
  // A cell reference with no sheet is refused by name (owner: the sheet's grammar); a type with no page's node types is no
  // function; a constructor given the wrong number of keys says how many and which.
  const noSheet = M.expr.run(M.expr.compile('Sum(B1:B3)'), []);
  ok('E5 a cell reference with no sheet refused by name', /Cell references are the sheet's/.test(String(noSheet.why)), ascii(noSheet));
  const wafer = { wafer: { keys: ['wafer'], id: (k) => k.wafer } };
  const noTypes = M.expr.compile('wafer("W01")');
  const twoKeys = M.expr.compile('wafer("W01", 2)', { nodes: wafer });
  ok('E6 a type the page did not give is no function; the wrong number of keys says the keys',
    /No function named wafer/.test(String(noTypes.why)) && /wafer takes 1 key \(wafer\) - got 2/.test(String(twoKeys.why)), ascii([noTypes, twoKeys]));
  // Dates (lead fe2ba4b1f): a part name this edition does not answer, one Spotfire has not, a zone that is none - by name.
  const part = M.expr.run(M.expr.compile('DatePart("minute", "2026-10-14")'), []);
  const noPart = M.expr.run(M.expr.compile('DatePart("fortnight", "2026-10-14")'), []);
  const noZone = M.expr.run(M.expr.compile('Date("2026-10-14")'), [], { zone: 'Nowhere/Zone' });
  ok('E8 a date refusal said by name - a part not in this edition, no part, no zone',
    /DatePart «minute» is not in this edition/.test(String(part.why)) && /DatePart takes a part name/.test(String(noPart.why))
    && /«Nowhere\/Zone» is not a time zone/.test(String(noZone.why)), ascii([part, noPart, noZone]));
  ok('E9 with no zone the server setting\'s default (Asia/Seoul)',
    M.expr.run(M.expr.compile('Date("2026-10-13T23:00:00Z")'), []).value === '2026-10-14T00:00:00+09:00');
  // Lead fe2ba4b1f ①: the page reads the server's zone from the declaration answer (fetchDeclaration -> useZone), and
  // its runs cut dates there - the server's half: test_the_declaration_answer_carries_the_setting_the_screen_cuts_by.
  const told = TOLD;
  M.expr.useZone(told.zone);
  const elsewhere = M.expr.run(M.expr.compile('Date("2026-10-14T02:00:00Z")'), []).value;
  M.expr.useZone(null);
  ok('E10 the declaration\'s zone is the page\'s - the same day as the server cuts', told.zone === 'America/New_York'
    && elsewhere === '2026-10-13T00:00:00-04:00' && M.expr.run(M.expr.compile('Date("2026-10-14T02:00:00Z")'), []).value
    === '2026-10-14T00:00:00+09:00', ascii([told.zone, elsewhere]));
  // P10 before «(» is a call, not the cell P10.
  ok('E7 a name with digits before «(» is a call', M.expr.run(M.expr.compile('P10([x])'), [{ x: 1 }, { x: 3 }]).value === 1.2);
  const met = M.expr.run(M.expr.compile('[x] * 2 + [x]'), [{ x: '29 mm' }, { x: '29.50' }, { x: null }, { x: 'a' }, { x: 3 }]);
  ok('E1 the rows an operator met a text that is not a number on: counted once each, an empty value not', met.notNumber === 2
    && JSON.stringify(met.values) === JSON.stringify([null, 88.5, null, null, 9]), ascii(met));
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
const S = 'testbed/slot.js';
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
  { id: 'X22', what: 'an operator meeting a text says nothing', catches: 'E1', file: E,
    mutate: (t) => swap(t, '      if (notNumber(a) || notNumber(b)) ctx.notNumber.add(ctx.row);\n', '') },
  { id: 'X23', what: 'an empty value is counted as not a number', catches: 'E1', file: E,
    mutate: (t) => swap(t, 'const notNumber = (v) => !isBlank(v) && numberOf(v) === null;', 'const notNumber = (v) => numberOf(v) === null;') },
  { id: 'X27', what: 'Marked takes unknown for out', catches: 'O[marked.row]', file: E,
    mutate: (t) => swap(t, 'return v === true || v === false ? v : null; };', 'return v === true; };') },
  { id: 'X28', what: 'a way that reaches nothing is out, not unknown', catches: 'O[marked.way]', file: E,
    mutate: (t) => swap(t, '  if (!ends || !ends.length) return null;', '  if (!ends || !ends.length) return false;') },
  { id: 'X29', what: 'Marked folded once over the rows, not row by row', catches: 'O[marked.row]', file: E,
    mutate: (t) => swap(t, "const rowLevel = (node) => node.t === 'ref' || (node.t === 'call' && (node.fn.kind === 'mark' || node.fn.kind === 'reach'))", "const rowLevel = (node) => node.t === 'ref' || (node.t === 'call' && node.fn.kind === 'reach')") },
  { id: 'X50', what: 'Reach folded once over the rows, not row by row', catches: 'O[reach.row]', file: E,
    mutate: (t) => swap(t, "const rowLevel = (node) => node.t === 'ref' || (node.t === 'call' && (node.fn.kind === 'mark' || node.fn.kind === 'reach'))", "const rowLevel = (node) => node.t === 'ref' || (node.t === 'call' && node.fn.kind === 'mark')") },
  { id: 'X51', what: 'a row the walk could not judge read as not reaching', catches: 'O[reach.row]', file: E,
    mutate: (t) => swap(t, 'const v = ctx.reach(to, ctx.row.id);', 'const v = ctx.reach(to, ctx.row.id) || false;') },
  { id: 'X30', what: 'a datetime column folded as numbers - its types not read', catches: 'V[time.min]', file: E,
    mutate: (t) => swap(t, "  if (BY_TIME[node.name] && args[0].t === 'ref' && ctx.types[args[0].name] === 'datetime') return BY_TIME[node.name](items).value;\n", '') },
  { id: 'X31', what: 'the same instant twice: the one met last', catches: 'V[time.min.offset.same.instant]', file: E,
    mutate: (t) => swap(t, 'const BY_TIME = { Min: times((a, b) => a < b),', 'const BY_TIME = { Min: times((a, b) => a <= b),') },
  { id: 'X32', what: 'a range read a column at a time', catches: 'O[sheet.range.order]', file: E,
    mutate: (t) => swap(t, '  for (let r = Math.min(a.r, b.r); r <= Math.max(a.r, b.r); r += 1) {\n    for (let c = Math.min(a.c, b.c); c <= Math.max(a.c, b.c); c += 1) out.push(`${letters(c)}${r}`);',
      '  for (let c = Math.min(a.c, b.c); c <= Math.max(a.c, b.c); c += 1) {\n    for (let r = Math.min(a.r, b.r); r <= Math.max(a.r, b.r); r += 1) out.push(`${letters(c)}${r}`);') },
  { id: 'X33', what: 'a fold over cells folds them once a row', catches: 'O[sheet.range.once]', file: E,
    mutate: (t) => swap(t, '  const once = !rowLevel(args[0]) && cellsOf(args[0]).size > 0;', '  const once = false;') },
  { id: 'X34', what: 'a constructor\'s keys taken in the id\'s order, not the declared one', catches: 'O[node.keys.declared.order]', file: E,
    mutate: (t) => swap(t, 'node.id(Object.fromEntries(node.keys.map((k, i) => [k, keys[i]])))', 'node.id(Object.fromEntries([...node.keys].sort().reverse().map((k, i) => [k, keys[i]])))') },
  { id: 'X35', what: 'a cell reference with no sheet reads empty', catches: 'E5', file: E,
    mutate: (t) => swap(t, "  if (typeof ctx.cell !== 'function') throw new ExpressionError(", "  if (typeof ctx.cell !== 'function') return null; if (false) throw new ExpressionError(") },
  { id: 'X36', what: 'P10( read as the cell P10', catches: 'E7', file: E,
    mutate: (t) => swap(t, '(?![A-Za-z0-9_])(?!\\s*\\()/;', '(?![A-Za-z0-9_])/;') },
  { id: 'X24', what: '«~» read as forwards', catches: 'O[way.backward.fold]', file: S,
    mutate: (t) => swap(t, "{ predicate: p.slice(0, -1), direction: 'incoming' }", "{ predicate: p.slice(0, -1), direction: 'outgoing' }") },
  { id: 'X25', what: 'a way\'s two answers taken as the edge\'s', catches: 'E2', file: S,
    mutate: (t) => swap(t, '  if (onEdge && own) throw new ExpressionError(', '  if (false) throw new ExpressionError(') },
  { id: 'X26', what: 'a way read as one name - the code before (the row\'s own value named «in_container.size»)', catches: 'O[way.forward]', file: S,
    mutate: (t) => swap(t, '  const way = wayOf(name);\n  if (!way)', '  const way = null;\n  if (!way)') },
  { id: 'X19', what: 'a numeral is whatever Number() reads (0x10 is 16)', catches: 'N2', file: R,
    mutate: (t) => swap(t, "  if (typeof value !== 'string' || !NUMERAL.test(value.trim())) return null;", "  if (typeof value !== 'string' || !value.trim()) return null;") },
];
const CONTROLS = [
  { id: 'K1', what: 'a local renamed', file: E, mutate: (t) => swap(t, 'const T95 = 1.959964;', 'const T95x = 1.959964;\nconst T95 = T95x;') },
  { id: 'K2', what: 'comment lines stripped', file: E, mutate: (t) => t.split('\n').filter((l) => !/^\s*\/\//.test(l)).join('\n') },
];
const KEY = { [E]: 'expr', [R]: 'reach', [S]: 'slot' };
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
