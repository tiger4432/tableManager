// MUTATION SCORER — the one place a mutant's verdict is decided.
//
// 🔴 A THROW IS A HOLE, NOT A CATCH. A mutation that stops the harness -- a rotted anchor, a
// module that no longer loads, a dereference of the control the defect just removed -- is not
// evidence that anything noticed. Counting it as `caught` turns a harness that DIED into a
// green line, which is the silent pass these corpora exist to prevent, wearing a different
// costume. A throw is reported INERT, by name, and counted as an escape.
//
// 🔴 AND A CATCH IS BY NAME. `caught` is not 「some assertion failed」 -- it is 「THIS assertion
// failed」, the one the mutant declares in `catches`. A mutant caught for an unrelated reason is
// a mutant nobody is measuring: the line it was written to protect can rot away underneath it
// while the corpus stays green. This is one notch stronger than counting failures, and it is
// the reason this loop was worth extracting rather than re-deciding per file.
//
// WHERE IT CAME FROM. `rnd_board_walk_harness.mjs` and `rnd_board_composition_harness.mjs` each
// carried this loop, near-identically -- two paths to one answer, which is criterion ④ (「둘이
// 갈라질 수 있나」, not 「둘이 있나」). C-66 lifted it here and both now call it.
//
// A mutant is `{ id, what, catches, mutate }`:
//   id       short handle for the run's output
//   what     what the mutation does, in the words of the behaviour it breaks
//   catches  the id PREFIX of the assertion that must fail. Required for a defect; a control
//            declares none, because a control must wake nothing at all.
//   mutate   whatever the caller's `run` needs -- this file never looks inside it.

/** A verdict word, so callers and readers use the same three. */
export const VERDICT = Object.freeze({ CAUGHT: 'CAUGHT', ESCAPED: 'ESCAPED', INERT: 'INERT' });

/**
 * Score one labelled set of mutants.
 *
 * @param {Array<{id?:string, what?:string, catches?:string, name?:string}>} mutants
 * @param {(m:any) => Promise<{failures:string[]}>|{failures:string[]}} run
 *        Runs the suite against the mutant and hands back the failures that are NEW for this
 *        run. Throwing is allowed and is scored -- see the note at the top.
 * @param {{mustCatch?:boolean, title?:string, log?:Function}} [opts]
 *        `mustCatch: false` scores a CONTROL set, which must wake nothing.
 * @returns {Promise<{wrong:number, caught:number, verdicts:Array}>}
 */
export async function scoreMutants(mutants, run, opts = {}) {
  const log = opts.log || console.log;
  const mustCatch = opts.mustCatch !== false;
  if (opts.title) log(opts.title);

  let wrong = 0;
  let caught = 0;
  const verdicts = [];

  for (const m of mutants) {
    const id = m.id || m.name || '(unnamed)';
    const what = m.what || m.name || '';
    let out = null;
    let threw = null;
    try { out = await run(m); } catch (err) { threw = err; }

    if (threw) {
      // Never right, for a defect OR a control: the harness stopped instead of judging.
      wrong += 1;
      verdicts.push({ id, verdict: VERDICT.INERT, why: String(threw && threw.message) });
      log(`  INERT   ${id} ${what}  -- ${String(threw && threw.message).slice(0, 90)}`);
      continue;
    }

    const failures = Array.isArray(out && out.failures) ? out.failures.map(String) : [];
    // A defect is caught only by the assertion it names. A control must wake nothing at all, so
    // for it ANY new failure is the wrong answer -- naming one would be asking which assertion
    // was allowed to be wrong.
    const hit = mustCatch
      ? (m.catches ? failures.some(f => f.startsWith(m.catches)) : false)
      : failures.length > 0;

    if (mustCatch && !m.catches) {
      // 🔴 LOUD, NOT LENIENT. A defect with no `catches` cannot be scored by name, and quietly
      //    accepting 「something failed」 for it would reintroduce exactly what this file exists
      //    to stop -- one mutant at a time, invisibly.
      wrong += 1;
      verdicts.push({ id, verdict: VERDICT.ESCAPED, why: 'no `catches` declared' });
      log(`  ESCAPED ${id} ${what}  -- no \`catches\`: nothing says WHICH assertion must fail`);
      continue;
    }

    if (hit === mustCatch) {
      if (mustCatch) caught += 1;
      verdicts.push({ id, verdict: mustCatch ? VERDICT.CAUGHT : VERDICT.ESCAPED });
      log(mustCatch
        ? `  caught  ${id} ${what}  (${m.catches})`
        : `  escaped ${id} ${what}`);
    } else {
      wrong += 1;
      verdicts.push({ id, verdict: mustCatch ? VERDICT.ESCAPED : VERDICT.CAUGHT,
        why: mustCatch ? `${m.catches} stayed green` : failures.slice(0, 2).join(' | ') });
      log(mustCatch
        ? `  ESCAPED ${id} ${what}  -- ${m.catches} stayed green`
        : `  CAUGHT  ${id} ${what}  <- a control woke: ${failures.slice(0, 2).join(' | ')}`);
    }
  }

  return { wrong, caught, verdicts };
}
