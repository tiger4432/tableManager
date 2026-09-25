/**
 * DECLARATION PROBLEM GROUPS — the declaration check's problem lines, one line per
 * (domain, population, reason) (lead b73255fc5 E · b93cdf327: one level, count first).
 *
 *   A  which lines are problems — the populations POPULATION_TONE colours warn or danger, nothing else
 *   B  folding — one group per (domain, population, reason); the count is the lines folded; no
 *      sentence is carried (the first line's names one table); a line with no reason stands alone;
 *      the biggest group first
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
  vocabulary: { populations: ['effective', 'ineffective', 'rejected', 'someday'],
                reason_names: { not_declared: 'Not declared' } },
  domains: [
    { domain: 'chain', title: 'Chain',
      effective: [entry('a', 'ok_reason', 'fine')],
      ineffective: [entry('t1', 'not_declared', 'first sentence'), entry('t2', 'not_declared', 'second sentence'),
                    entry('t3', null, 'says one thing'), entry('t4', null, 'says another')],
      rejected: [entry('r1', 'not_declared', 'rejected for the same word')],
      someday: [entry('s1', 'not_declared', 'a population the client has no colour for')] },
    { domain: 'ledger', title: 'Ledger',
      rejected: [entry('r2', 'mapping_unavailable', 'bad mapping'), entry('r3', 'mapping_unavailable', 'bad mapping again'),
                 entry('r4', 'mapping_unavailable', 'and a third'), entry('r5', 'not_declared', 'the chain word, in another domain')] },
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
  const label = (g) => `${g.domain.text}|${g.population.text}|${g.reason ? g.reason.text : '-'}|${g.count.text}`;

  eq('A1 an effective line is never a problem', groups.some((g) => g.population.text === 'effective'), false);
  eq('A2 a population with no colour is not counted as a problem', groups.some((g) => g.population.text === 'someday'), false);
  eq('A3 every problem line is in exactly one group',
    groups.reduce((s, g) => s + g.lines.length, 0), 4 + 1 + 4);
  eq('B1 the same reason in the same population and domain is one group, counted',
    groups.filter((g) => g.population.text === 'ineffective' && g.reason && g.reason.text === 'not_declared').map(label),
    ['Chain|ineffective|not_declared|2']);
  eq('B2 the same reason in another population is its own group',
    groups.filter((g) => g.domain.text === 'Chain' && g.reason && g.reason.text === 'not_declared').map(label),
    ['Chain|ineffective|not_declared|2', 'Chain|rejected|not_declared|1']);
  eq('B3 the same reason in another DOMAIN is its own group (b93cdf327)',
    groups.filter((g) => g.population.text === 'rejected' && g.reason && g.reason.text === 'not_declared').map(label),
    ['Chain|rejected|not_declared|1', 'Ledger|rejected|not_declared|1']);
  eq('B4 a line with no reason stands alone — two such lines are two groups',
    groups.filter((g) => !g.reason).map((g) => g.lines[0].entry.detail.text), ['says one thing', 'says another']);
  eq('B5 a group carries no sentence of its own — the first line names one table', 'detail' in groups[0], false);
  eq('B6 the group keeps its lines, so opening it can show them',
    groups.find((g) => g.reason && g.reason.text === 'not_declared').lines.map((l) => l.entry.subject.text), ['t1', 't2']);
  eq('B8 a group draws the server\'s reason name, and a reason it was sent no name for draws none',
    [(groups.find((g) => g.reason && g.reason.text === 'not_declared').reasonName || {}).text,
     groups.find((g) => g.reason && g.reason.text === 'mapping_unavailable').reasonName], ['Not declared', null]);
  eq('B7 the biggest group first, and equal counts keep the report\'s order',
    groups.map((g) => g.count.text), ['3', '2', '1', '1', '1', '1']);
  return { ran, failures };
}

const result = await suite(REAL);
console.log('-- declaration problem groups --------------------------------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

const MUTANTS = [
  { id: 'X1', what: 'every population is a problem', catches: ['A1', 'A2', 'A3'],
    mutate: (s) => s.replace("if (tone !== 'warn' && tone !== 'danger') continue;", '') },
  { id: 'X2', what: 'the key forgets the domain, so two domains fold together', catches: ['B3'],
    mutate: (s) => s.replace('`${domain.name}\\u0000${population.name}\\u0000${reason}`', '`${population.name}\\u0000${reason}`') },
  { id: 'X3', what: 'the key forgets the population', catches: ['B2'],
    mutate: (s) => s.replace('`${domain.name}\\u0000${population.name}\\u0000${reason}`', '`${domain.name}\\u0000${reason}`') },
  { id: 'X4', what: 'lines with no reason fold into one', catches: ['B4'],
    mutate: (s) => s.replace('const key = reason === null ? null : ', 'const key = reason === null ? `${population.name}\\u0000-` : ') },
  { id: 'X5', what: 'the first line\'s sentence rides on the group again', catches: ['B5'],
    mutate: (s) => s.replace('reasonName: entry.reasonName, lines: [] };', 'reasonName: entry.reasonName, detail: entry.detail, lines: [] };') },
  { id: 'X6', what: 'the count is the number of groups, not of lines', catches: ['B1', 'B7'],
    mutate: (s) => s.replace('count: count(group.lines.length)', 'count: count(1)') },
  { id: 'X8', what: 'the reason name never reaches the group', catches: ['B8'],
    mutate: (s) => s.replace('reasonName: entry.reasonName, lines: [] };', 'reasonName: null, lines: [] };') },
  { id: 'X7', what: 'the groups stay in report order', catches: ['B7'],
    mutate: (s) => s.replace('.sort((x, y) => y.lines.length - x.lines.length)', '') },
];
console.log('');
console.log('-- defect mutants (each must be CAUGHT by its named line) -----------');
const { wrong } = await scoreMutants(MUTANTS, async (m) => suite((await loadWithProbe(FILE, { mutate: m.mutate })).module));
const failed = result.failures.length + wrong;
console.log(`\n${result.ran.length - result.failures.length} passed, ${result.failures.length} failed; `
  + `${MUTANTS.length - wrong}/${MUTANTS.length} defects caught, ${wrong} escaped.`);
console.log(`ASSERTIONS ${result.ran.length + MUTANTS.length} ${failed}`);
process.exit(failed ? 1 : 0);
