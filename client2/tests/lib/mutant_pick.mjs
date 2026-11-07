// Which of the screen checker's mutants a run builds (lead 11-07): `--mutant <name>` (repeatable) names them - a landing
// runs the mutants of what it changed, not every one of a page's (43 of index.html, about 10 min each). `--only` and
// `--touched` narrow by page on top. A name no mutant has is said, so a typo is not a silent «nothing ran».

/** The names given as `--mutant <name>`, in order. */
export const namedMutants = (argv) => argv.flatMap((arg, i) => (arg === '--mutant' && argv[i + 1] ? [argv[i + 1]] : []));

/** -> {run: the mutants to build, unknown: names no mutant has}. `only` an entry or null; `picked` entries or null. */
export function pickMutants(mutants, { named = [], only = null, picked = null } = {}) {
  const unknown = named.filter((name) => !mutants.some((m) => m.name === name));
  const run = mutants.filter((m) => (!named.length || named.includes(m.name)) && (!only || m.entry === only)
    && (!picked || picked.includes(m.entry)));
  return { run, unknown };
}
