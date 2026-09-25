/**
 * DECLARATION PROBLEM GROUPS — the declaration check's problem lines, the same reason folded into one
 * (lead b73255fc5 E · a48d1f2da: the function and the count first; the drawing waits for the mockup).
 *
 *   A  which lines are problems — the populations POPULATION_TONE colours warn or danger, nothing else
 *   B  folding — one group per (population, reason); the count is the lines folded; the sentence is the
 *      first line's, verbatim; a line with no reason token stands alone
 *
 * Every assertion is woken by a mutant below.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FILE = path.join(HERE, '..', 'src', 'config_resolve_view.js');
const REAL = await import('../src/config_resolve_view.js');

const entry = (subject, reason, detail) => ({ subject, reason, detail, fields: {} });
const REPORT = {
  vocabulary: { populations: ['effective', 'ineffective', 'rejected', 'someday'] },
  domains: [
    { domain: 'chain', title: 'Chain',
      effective: [entry('a', 'ok_reason', 'fine')],
      ineffective: [entry('t1', 'not_declared', 'first sentence'), entry('t2', 'not_declared', 'second sentence'),
                    entry('t3', null, 'says one thing'), entry('t4', null, 'says another')],
      rejected: [entry('r1', 'not_declared', 'rejected for the same word')],
      someday: [entry('s1', 'not_declared', 'a population the client has no colour for')] },
    { domain: 'ledger', title: 'Ledger',
      rejected: [entry('r2', 'mapping_unavailable', 'bad mapping'), entry('r3', 'mapping_unavailable', 'bad mapping again')] },
  ],
};

async function suite(mod) {
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };
  const groups = mod.problemGroups(mod.buildConfigResolveView(REPORT));
  const label = (g) => `${g.population.text}|${g.reason ? g.reason.text : '-'}|${g.count.text}`;

  eq('A1 an effective line is never a problem', groups.some((g) => g.population.text === 'effective'), false);
  eq('A2 a population with no colour is not counted as a problem', groups.some((g) => g.population.text === 'someday'), false);
  eq('A3 every problem line is in exactly one group',
    groups.reduce((s, g) => s + g.lines.length, 0), 4 + 1 + 2);
  eq('B1 the same reason in the same population is one group, counted',
    groups.filter((g) => g.population.text === 'ineffective' && g.reason && g.reason.text === 'not_declared').map(label),
    ['ineffective|not_declared|2']);
  eq('B2 the same reason in another population is its own group',
    groups.filter((g) => g.reason && g.reason.text === 'not_declared').map(label),
    ['ineffective|not_declared|2', 'rejected|not_declared|1']);
  eq('B3 folding crosses domains', groups.filter((g) => g.reason && g.reason.text === 'mapping_unavailable').map(label),
    ['rejected|mapping_unavailable|2']);
  eq('B4 a line with no reason stands alone — two such lines are two groups',
    groups.filter((g) => !g.reason).map((g) => g.detail.text), ['says one thing', 'says another']);
  eq('B5 the sentence is the first line\'s, verbatim, and says it is the server\'s',
    [groups[0].detail.text, groups[0].detail.src], ['first sentence', 'server']);
  eq('B6 the group keeps its lines, so opening it can show them', groups[0].lines.map((l) => l.entry.subject.text), ['t1', 't2']);
  return { ran, failures };
}

const result = await suite(REAL);
console.log('-- declaration problem groups --------------------------------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const MUTANTS = [
  { id: 'X1', what: 'every population is a problem', catches: ['A1', 'A2', 'A3'],
    mutate: (s) => s.replace("if (tone !== 'warn' && tone !== 'danger') continue;", '') },
  { id: 'X2', what: 'the key forgets the population, so two populations fold together', catches: ['B2'],
    mutate: (s) => s.replace('`${population.name}\\u0000${reason}`', 'reason') },
  { id: 'X3', what: 'lines with no reason fold into one', catches: ['B4'],
    mutate: (s) => s.replace('const key = reason === null ? null : ', 'const key = reason === null ? `${population.name}\\u0000-` : ') },
  { id: 'X4', what: 'the sentence is taken from the last line', catches: ['B5'],
    mutate: (s) => s.replace('group.lines.push({ domain: domain.name, entry });', 'group.lines.push({ domain: domain.name, entry }); group.detail = entry.detail;') },
  { id: 'X5', what: 'the count is the number of groups, not of lines', catches: ['B1', 'B3'],
    mutate: (s) => s.replace('count: count(group.lines.length)', 'count: count(1)') },
];
console.log('');
console.log('-- defect mutants (each must be CAUGHT by its named line) -----------');
const { wrong } = await scoreMutants(MUTANTS, async (m) => suite((await loadWithProbe(FILE, { mutate: m.mutate })).module));
const failed = result.failures.length + wrong;
console.log(`\n${result.ran.length - result.failures.length} passed, ${result.failures.length} failed; `
  + `${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${result.ran.length + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
