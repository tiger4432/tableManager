/**
 * CONFIG RESOLVE REPORT — the CLIENT half, scored against vectors.json.
 *
 * Read-only: it never writes to client2/.
 *
 *   node contracts/config_resolve_report/client_harness.mjs
 *   node contracts/config_resolve_report/client_harness.mjs --json
 *
 * Exit codes: 0 = client matches the contract | 1 = divergence(s) | 2 = harness failure.
 *
 * WHAT IT SCORES TODAY, AND WHY THAT IS THE PART WORTH SCORING
 *   The client renderer for this report has not been built yet (it lands after the current
 *   client round). But the invariant with the sharpest teeth does not need it to exist:
 *
 *     INV-F9-7 — the client must contain NONE of the reason words as source literals.
 *
 *   The server names the reason and composes the sentence; the client renders `detail`.
 *   A client that writes `not_declared` down has, at that moment, acquired its own opinion
 *   about what counts as ineffective — and the two sides can then disagree while every
 *   server test stays green. That is the hardcoded-copy class U6 deleted six instances of,
 *   and grep catches it from the first line of client code onward.
 *
 *   So this harness is USEFUL BEFORE the feature exists and stays useful after: it is a
 *   standing prohibition, not a mirror of an implementation.
 *
 * WHAT IT REPORTS AS PENDING
 *   The positive half — "the rendered text equals the server's `detail`" — needs the
 *   renderer. It is reported BY NAME as pending rather than passed, so the round's
 *   completion check can see what is still unscored (the Lead PM's pending rule).
 */
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, relative, sep } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..', '..');
const VECTORS_PATH = join(HERE, 'vectors.json');
const CLIENT_SRC = join(ROOT, 'client2', 'src');

const asJson = process.argv.includes('--json');

function die(msg) {
  console.error(`HARNESS FAILURE: ${msg}`);
  console.error('(This is not a passing result. Nothing was compared.)');
  process.exit(2);
}

if (!existsSync(VECTORS_PATH)) die(`vectors.json is missing at ${VECTORS_PATH}`);
const vectors = JSON.parse(readFileSync(VECTORS_PATH, 'utf8'));

const forbidden = vectors.forbidden_client_literals?.literals;
if (!Array.isArray(forbidden) || forbidden.length === 0) {
  die('vectors.json declares no forbidden_client_literals — the one check this harness '
    + 'can run today would silently pass over nothing.');
}
const allowPaths = new Set(vectors.forbidden_client_literals.allow_paths || []);

if (!existsSync(CLIENT_SRC)) die(`client source tree not found at ${CLIENT_SRC}`);

/** Every .js/.mjs/.html/.css under client2/src. */
function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, out);
    else if (/\.(js|mjs|html|css)$/.test(name)) out.push(full);
  }
  return out;
}

const files = walk(CLIENT_SRC);
if (files.length === 0) die(`no client source files under ${CLIENT_SRC}`);

const divergences = [];
const pending = [];

// --- INV-F9-7: the reason words are SERVER words ------------------------------------
for (const file of files) {
  const rel = relative(ROOT, file).split(sep).join('/');
  if (allowPaths.has(rel)) continue;
  const text = readFileSync(file, 'utf8');
  const lines = text.split('\n');
  for (const word of forbidden) {
    lines.forEach((line, i) => {
      if (!line.includes(word)) return;
      divergences.push({
        invariant: 'INV-F9-7',
        file: rel,
        line: i + 1,
        detail: `client source contains the server reason word '${word}'. The server names `
          + `the reason and composes the sentence; the client renders \`detail\`. Iterate `
          + `\`vocabulary.reasons\` from the response instead of writing the word down.`,
        excerpt: line.trim().slice(0, 160),
      });
    });
  }
}

// --- the positive half, pending until the renderer exists ---------------------------
const rendererHints = files.filter((f) => {
  const t = readFileSync(f, 'utf8');
  return t.includes('/admin/config/resolve') || t.includes('configResolve');
});
if (rendererHints.length === 0) {
  pending.push({
    invariant: 'INV-F9-4 (client side)',
    detail: 'no client code consumes GET /admin/config/resolve yet, so "the rendered text '
      + 'is the server\'s `detail`, verbatim" is UNSCORED. This blocks round completion, '
      + 'not the suite. When the renderer lands, extend this harness to assert it reads '
      + '`entry.detail` and never composes its own sentence per reason.',
  });
} else {
  const missing = rendererHints.filter(f => !readFileSync(f, 'utf8').includes('.detail'));
  for (const f of missing) {
    divergences.push({
      invariant: 'INV-F9-4 (client side)',
      file: relative(ROOT, f).split(sep).join('/'),
      line: 0,
      detail: 'this file consumes the resolve report but never reads `.detail`. The '
        + 'server composed a sentence for exactly this reason; ignoring it means the '
        + 'client is composing its own.',
    });
  }
}

const result = {
  contract: 'config_resolve_report',
  scanned_files: files.length,
  forbidden_literals: forbidden,
  divergences,
  pending,
  ok: divergences.length === 0,
};

if (asJson) {
  console.log(JSON.stringify(result, null, 2));
} else {
  console.log(`config_resolve_report — client half (${files.length} files scanned)`);
  for (const d of divergences) {
    console.log(`  DIVERGENCE ${d.invariant} ${d.file}:${d.line}`);
    console.log(`    ${d.detail}`);
    if (d.excerpt) console.log(`    > ${d.excerpt}`);
  }
  for (const p of pending) {
    console.log(`  PENDING ${p.invariant}`);
    console.log(`    ${p.detail}`);
  }
  console.log(divergences.length === 0
    ? `  OK — no client source writes a server reason word down.`
    : `  ${divergences.length} divergence(s).`);
}

process.exit(divergences.length === 0 ? 0 : 1);
