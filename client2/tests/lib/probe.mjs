// PROBE — import a module WHOLE and reach into it. Nothing is ever cut out.
//
// This file exists because of the owner's standing rule (2026-09-02): a harness must not read
// its subject as text and run regex-sliced fragments in `vm`. Slicing measures the SHAPE OF
// THE LETTERS, not the behaviour — add one `import` and the fragment throws, add one `const`
// and the fragment cannot see it, and both failures are red on correct code. The reverse is
// worse: a slice can be green while the real module is broken.
//
// But `export` alone does not replace slicing here. Measured on `map_editor.js`: 24 of the 30
// harnesses that slice it SET module-level state (`gridData`, `legend`, `validDie`, …) to
// stage the case they score. ESM cannot do that from outside — a namespace object is sealed,
// and an `export let` binding is read-only to importers. So a harness could call the function
// and never stage what the function reads.
//
// SO: the subject is copied BYTE FOR BYTE and a probe object is APPENDED after the last line.
// The copy is written beside the original so its own relative imports resolve, imported, and
// deleted. Every reason the slicing ban exists is gone, because nothing is removed:
//
//     a new `import` in the subject   -> still there, still runs
//     a new `const`                   -> still in scope, the probe sees it
//     a helper call                   -> the helper is in the same file
//     bytes cut                       -> ZERO, and `assertAppendOnly` proves it every load
//
// 🔴 THIS IS A BRIDGE, NOT A DESTINATION. The destination is the rule CLAUDE.md already
// states: lift the logic being measured into a module that can simply be imported
// (`truncation.js`, `match_count.js`, `dropdown.js` are that shape). Appending buys the
// harnesses correctness tonight; it does not make a 10,000-line entry module acceptable.
import { readFileSync, writeFileSync, rmSync, readdirSync } from 'node:fs';
import { register } from 'node:module';
import { dirname, join, basename } from 'node:path';
import { pathToFileURL } from 'node:url';

// The one name the appended object is bound to. Asserted ABSENT from the subject on every
// load, so this can never shadow something the subject already had.
export const MARK = '__harness_probe__';

const COPY_INFIX = '.__probe__.';
const STUB_INFIX = '.__probe_stub__.';
// Where a generated stub finds the functions the harness supplied. The stub only DELEGATES --
// it never carries behaviour of its own, because a stub whose behaviour is written as source
// text is the second face of the thing this file replaces.
const SINKS = '__harness_probe_sinks__';
let seq = 0;
let registered = false;

// 🔴 THE REAL CONSOLE, CAPTURED AT LOAD. Harnesses install a RECORDING console on
// `globalThis` so they can assert on what the subject reported -- and one of them swallowed
// this file's own failure message, leaving `exit 2` with no output at all. An instrument that
// goes blind under its own fault is worse than no instrument.
const OUT = console;

function die(msg) {
  OUT.error(`HARNESS FAILURE (probe): ${msg}`);
  OUT.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

const IDENT = /^[A-Za-z_$][A-Za-z0-9_$]*$/;

// A crashed run can leave a copy behind, and a stray copy in `src/` is the one way this
// mechanism could reach production. Sweep before the first load rather than trusting a
// `finally` that a `process.exit` skips.
function sweep(dir) {
  let names;
  try { names = readdirSync(dir); } catch { return; }
  for (const n of names) {
    if (n.includes(COPY_INFIX) || n.includes(STUB_INFIX)) {
      try { rmSync(join(dir, n)); } catch { /* someone else's */ }
    }
  }
}

// ── condition ②: the copy must START WITH the subject's bytes ─────────────────────────────
// This is the load-bearing check. Appending decays into slicing the moment somebody trims the
// prefix "just a little", and the only thing that can notice is a machine comparing bytes.
function assertAppendOnly(prefixBytes, copyBytes, suffix) {
  const head = copyBytes.subarray(0, prefixBytes.length);
  if (!head.equals(prefixBytes)) {
    die('the copy does not begin with the subject\'s bytes. Something was CUT or REWRITTEN, '
      + 'which is the slicing this file exists to replace.');
  }
  const expected = prefixBytes.length + Buffer.byteLength(suffix, 'utf8');
  if (copyBytes.length !== expected) {
    die(`the copy is ${copyBytes.length} bytes but the subject plus the appended probe is `
      + `${expected}. Something was inserted in the middle.`);
  }
}

function buildSuffix(expose, state) {
  const lines = [];
  for (const n of expose) lines.push(`  ${n},`);
  // A getter/setter pair, so the harness reads and writes the LIVE binding rather than a
  // snapshot taken when this object was built.
  for (const n of state) {
    lines.push(`  get ${n}() { return ${n}; }, set ${n}(v) { ${n} = v; },`);
  }
  return '\n\n'
    + '// ─────────────────────────────────────────────────────────────────────────────\n'
    + '// APPENDED BY client2/tests/lib/probe.mjs. Not part of the file above; every byte\n'
    + '// before this comment is the subject, unmodified. This copy is deleted after import.\n'
    + '// ─────────────────────────────────────────────────────────────────────────────\n'
    + `export const ${MARK} = {\n${lines.join('\n')}\n};\n`;
}

// Which names the subject actually imports from a given specifier. A stub for a name the
// subject never imported would sit there doing nothing while the harness believed it had
// intercepted the call -- silent, and green.
function importedNames(subjectText, specifier) {
  const out = new Set();
  const q = specifier.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(`import\\s*\\{([^}]*)\\}\\s*from\\s*['"]${q}['"]`, 'g');
  let m;
  while ((m = re.exec(subjectText))) {
    for (const part of m[1].split(',')) {
      const name = part.trim().split(/\s+as\s+/).pop().trim();
      if (name) out.add(name);
    }
  }
  return out;
}

// The stub re-exports the real module and overrides only the stubbed names. An explicit
// export wins over `export *`, which is what makes the override work without naming
// everything else. Its own `./x.js` is NOT redirected: the hook keys on the importer being a
// probe copy, and this file is not one.
function stubSource(specifier, names, tag, values) {
  // A function is DELEGATED, so the harness can swap behaviour between loads and see calls as
  // they happen. A plain value cannot be delegated -- there is nothing to call -- so it is
  // re-exported once, at load. The distinction is the sink's own shape, not a flag: a stub
  // that guessed would turn `API_BASE` into a function and the subject would call a string.
  const lines = names.map(n => (typeof values[n] === 'function'
    ? `export function ${n}(...args) { return SINK[${JSON.stringify(n)}](...args); }`
    : `export const ${n} = SINK[${JSON.stringify(n)}];`));
  return `// GENERATED by client2/tests/lib/probe.mjs for one harness run. Deleted after import.\n`
    + `// It delegates; it decides nothing.\n`
    + `export * from ${JSON.stringify(specifier)};\n`
    + `const SINK = globalThis[${JSON.stringify(SINKS)}][${JSON.stringify(tag)}]`
    + `[${JSON.stringify(specifier)}];\n`
    + `${lines.join('\n')}\n`;
}

/**
 * Import `srcPath` whole, with a probe appended.
 *
 * spec.expose  names read once — functions and consts the harness CALLS
 * spec.state   names the harness must READ AND WRITE (module-level `let`/`var`)
 * spec.mutate  optional (text) => text, applied to the subject BEFORE appending. This is how
 *              a mutation sweep works now: the mutant is a whole module, not a fragment, so a
 *              mutant that fails to parse fails loudly instead of scoring as "caught".
 *
 * Returns { probe, module }. A name that does not exist in the subject throws on evaluation,
 * which is the intended loud failure — a probe that quietly returns undefined would let a
 * renamed function score green.
 */
export async function loadWithProbe(srcPath, spec = {}) {
  const expose = spec.expose || [];
  const state = spec.state || [];
  for (const n of [...expose, ...state]) {
    if (!IDENT.test(n)) die(`\`${n}\` is not an identifier. The probe builds source text, so a `
      + 'name has to be a name.');
  }
  const both = expose.filter(n => state.includes(n));
  if (both.length) die(`${both.join(', ')} asked for as both expose and state — pick one, `
    + 'or the appended object has a duplicate key and the later one silently wins.');

  const dir = dirname(srcPath);
  if (seq === 0) sweep(dir);

  const originalBytes = readFileSync(srcPath);
  const originalText = originalBytes.toString('utf8');

  // ── condition ③: the mark must not already be in the subject ────────────────────────────
  if (originalText.includes(MARK)) {
    die(`${basename(srcPath)} already contains \`${MARK}\`. The probe would shadow it, and the `
      + 'harness would measure the probe instead of the module.');
  }

  const prefixText = spec.mutate ? spec.mutate(originalText) : originalText;
  if (typeof prefixText !== 'string') die('spec.mutate must return the mutated source text.');
  if (spec.mutate && prefixText === originalText) {
    die('spec.mutate returned the source unchanged. A mutant that did not mutate scores as '
      + '"caught" for the wrong reason — it proves nothing.');
  }

  const suffix = buildSuffix(expose, state);
  const prefixBytes = Buffer.from(prefixText, 'utf8');
  const copyBytes = Buffer.concat([prefixBytes, Buffer.from(suffix, 'utf8')]);
  if (!spec.mutate && !prefixBytes.equals(originalBytes)) {
    die('reading and re-encoding the subject did not round-trip. Refusing to import a copy '
      + 'that is not byte-identical to the file on disk.');
  }
  assertAppendOnly(prefixBytes, copyBytes, suffix);

  const tag = `${spec.tag || 'probe'}${seq++}`.replace(/[^A-Za-z0-9_]/g, '');
  const copyPath = join(dir, `${basename(srcPath, '.js')}${COPY_INFIX}${tag}.js`);

  // ── dependencies the harness wants to intercept ─────────────────────────────────────
  const stubPaths = [];
  const stubs = spec.stubs || {};
  const specifiers = Object.keys(stubs);
  if (specifiers.length) {
    if (!registered) { register('./probe_hooks.mjs', import.meta.url); registered = true; }
    globalThis[SINKS] = globalThis[SINKS] || {};
    globalThis[SINKS][tag] = stubs;
    for (const specifier of specifiers) {
      const sib = /^\.\/([A-Za-z0-9_.-]+)\.js$/.exec(specifier);
      if (!sib) die(`stub specifier ${JSON.stringify(specifier)} is not a sibling module. `
        + 'Only `./name.js` can be redirected — a package or a deep path is out of scope.');
      const names = Object.keys(stubs[specifier]);
      const declared = importedNames(originalText, specifier);
      const missing = names.filter(n => !declared.has(n));
      if (missing.length) {
        die(`${basename(srcPath)} does not import ${missing.join(', ')} from ${specifier}. `
          + 'A stub for a name the subject never imported intercepts nothing, and the harness '
          + 'would go green believing it had.');
      }
      const stubPath = join(dir, `${sib[1]}${STUB_INFIX}${tag}.js`);
      writeFileSync(stubPath, stubSource(specifier, names, tag, stubs[specifier]));
      stubPaths.push(stubPath);
    }
  }

  writeFileSync(copyPath, copyBytes);
  try {
    const module = await import(pathToFileURL(copyPath).href);
    const probe = module[MARK];
    if (!probe) die('the appended probe is missing from the imported module — the subject may '
      + 'end inside an unterminated block comment or template literal.');
    return { probe, module };
  } finally {
    try { rmSync(copyPath); } catch { /* the sweep above catches leftovers next run */ }
    for (const p of stubPaths) { try { rmSync(p); } catch { /* same */ } }
  }
}
