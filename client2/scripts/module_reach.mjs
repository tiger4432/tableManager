// What a change reaches - the screen checker's --touched (owner 10-24) and the harness runner (lead 10-27 «ㄴ») narrow by
// these two answers, so the two can not part: the files changed since this tree left origin/main, and each vite entry's
// modules (its chunk and every chunk it imports). CSS pulled in by an @import inside CSS is inlined, not a module - it
// is reached only through the file that names it.
import { execFileSync } from 'node:child_process';
import { readdirSync, readFileSync, statSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

export const norm = (id) => id.split('?')[0].replace(/\\/g, '/').toLowerCase();

/** A vite plugin that fills `graph` with entry id -> the ids of every module the entry reaches, all through `norm`. */
export function reachPlugin(graph) {
  return { name: 'module-reach', generateBundle(o, bundle) {
    const reach = (file, into) => {
      const c = bundle[file];
      if (!c || c.type !== 'chunk' || into.has(file)) return;
      into.add(file);
      for (const f of [...c.imports, ...c.dynamicImports]) reach(f, into);
    };
    for (const [file, c] of Object.entries(bundle)) {
      if (c.type !== 'chunk' || !c.isEntry || !c.facadeModuleId) continue;
      const files = new Set();
      reach(file, files);
      graph.set(norm(c.facadeModuleId), new Set([c.facadeModuleId, ...[...files].flatMap((f) => bundle[f].moduleIds)].map(norm)));
    }
  } };
}

/** Changed files as `norm`ed absolute paths: one commit's (`commit`), or since the merge base with origin/main -
 *  committed, staged, unstaged and new. */
export function changedFiles(cwd, commit = null) {
  const git = (...a) => execFileSync('git', a, { cwd, encoding: 'utf8' }).split('\n').filter(Boolean);
  const top = git('rev-parse', '--show-toplevel')[0];
  const rel = commit ? git('-C', top, 'diff', '--name-only', `${commit}^`, commit)
    : [...git('-C', top, 'diff', '--name-only', git('merge-base', 'HEAD', 'origin/main')[0]),
      ...git('-C', top, 'ls-files', '--others', '--exclude-standard')];
  return [...new Set(rel)].map((f) => norm(`${top}/${f}`));
}

/** The lines `file` gained or lost, by the same span as changedFiles. */
function changedLines(cwd, file, commit) {
  const span = commit ? [`${commit}^`, commit]
    : [execFileSync('git', ['merge-base', 'HEAD', 'origin/main'], { cwd, encoding: 'utf8' }).trim()];
  return execFileSync('git', ['diff', '-U0', ...span, '--', file], { cwd, encoding: 'utf8' })
    .split('\n').filter((l) => /^[-+](?![-+]{2} )/.test(l)).join('\n');
}

/** Whether a SCANS cell (harness_floors.mjs) covers a path. A scope is a repo path ending in '/**' (the folder and all
 *  under it) or '/*' (the folder's own entries). `kind`: 'file' a changed file, 'dir' a folder listed, 'tree' a folder
 *  listed with { recursive: true }. */
export function scanCovers(scopes, top, p, kind) {
  return scopes.some((s) => {
    const deep = s.endsWith('/**');
    const base = `${norm(top)}/${norm(s.replace(/\/\*\*?$/, ''))}`;
    if (kind === 'file') return deep ? p.startsWith(`${base}/`) : path.posix.dirname(p) === base;
    return deep ? p === base || p.startsWith(`${base}/`) : kind === 'dir' && p === base;
  });
}

/** Every folder that holds a source file - tracked, or new and not ignored. A folder outside it (a temp dir, the probe's
 *  gitignored copies) holds nothing a change can reach. */
export function sourceDirs(top) {
  const dirs = new Set();
  for (const f of execFileSync('git', ['-C', top, 'ls-files', '--cached', '--others', '--exclude-standard'], { encoding: 'utf8' }).split('\n')) {
    if (!f) continue;
    for (let d = path.posix.dirname(norm(`${top}/${f}`)); !dirs.has(d) && d.length > 3; d = path.posix.dirname(d)) dirs.add(d);
  }
  return dirs;
}

// A harness that lists a folder reads what nobody named; without a SCANS cell it runs on every change.
const LISTS = /\breaddirSync\b|\breaddir\(|\bglobSync\b|\bglob\(|ls-files/;
// Any dotted word: only one a tracked file is called counts (`ledger_config.json.sample` too).
const NAMES = /[A-Za-z0-9_-][A-Za-z0-9_.-]*\.[A-Za-z0-9]+\b/g;
const uncomment = (t) => t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|\s)\/\/.*$/gm, '$1');

/** Which harnesses a change reaches. A harness reaches its own file, the tests/lib helpers it imports, every tracked file
 *  its text names (a basename two tracked files share counts only with its folder named beside it), and every module a
 *  named client file reaches in one vite build, and every file its SCANS cell covers. Returns { run, notRun, why, reach }
 *  - `why` set when every harness runs. */
export async function harnessesToRun({ client, tests, harnesses, changed, commit = null, scans = new Map() }) {
  const all = (why) => ({ run: harnesses, notRun: [], why, reach: new Map() });
  const own = ['scripts/check_harnesses.mjs', 'scripts/read_harness.mjs', 'scripts/module_reach.mjs', 'package.json',
    'package-lock.json', 'vite.config.js'].map((f) => norm(path.join(client, f)));
  const whole = changed.find((f) => own.includes(f));
  if (whole) return all(`${path.posix.relative(norm(client), whole)} changed`);
  // The runner's tables are data: a floor moved runs the harness it names, so the new floor is measured.
  const tables = norm(path.join(client, 'scripts', 'harness_floors.mjs'));
  const tabled = changed.includes(tables) ? changedLines(client, tables, commit) : '';
  const top = execFileSync('git', ['rev-parse', '--show-toplevel'], { cwd: client, encoding: 'utf8' }).trim();
  const tracked = execFileSync('git', ['-C', top, 'ls-files'], { encoding: 'utf8' }).split('\n').filter(Boolean).map((f) => norm(`${top}/${f}`));
  const byBase = new Map();
  for (const f of tracked) {
    const b = path.posix.basename(f);
    if (!byBase.has(b)) byBase.set(b, []);
    byBase.get(b).push(f);
  }
  let graph;
  try {
    const { build } = await import(pathToFileURL(path.join(client, 'node_modules', 'vite', 'dist', 'node', 'index.js')).href);
    const walk = (d) => readdirSync(d).flatMap((n) => { const p = path.join(d, n); return statSync(p).isDirectory() ? walk(p) : [p]; });
    const inputs = walk(path.join(client, 'src')).filter((p) => /\.m?js$/.test(p));
    const out = mkdtempSync(path.join(tmpdir(), 'module-reach-'));
    graph = new Map();
    try {
      await build({ root: client, configFile: path.join(client, 'vite.config.js'), logLevel: 'silent', plugins: [reachPlugin(graph)],
        build: { outDir: out, emptyOutDir: true, write: false, minify: false,
          rollupOptions: { input: Object.fromEntries(inputs.map((p, i) => [`reach_${i}`, p])) } } });
    } finally {
      rmSync(out, { recursive: true, force: true });
    }
  } catch (err) {
    return all(`the module graph could not be built (${String(err.message || err).split('\n')[0]})`);
  }
  const textOf = (file, seen) => {
    if (seen.has(file)) return '';
    seen.add(file);
    let t = '';
    try { t = uncomment(readFileSync(file, 'utf8')); } catch { return ''; }
    const libs = [...t.matchAll(/['"](\.{1,2}\/[^'"]+\.mjs)['"]/g)].map((m) => path.resolve(path.dirname(file), m[1]))
      .filter((l) => l.startsWith(tests + path.sep));
    return [t, ...libs.map((l) => textOf(l, seen))].join('\n');
  };
  const run = [];
  const notRun = [];
  const reaches = new Map();
  for (const name of harnesses) {
    if (tabled.includes(name)) { run.push(name); continue; }
    const scopes = scans.get(name);
    // The harness's own text: tests/lib/probe.mjs lists its temp folder to sweep it, which reads nothing.
    if (!scopes && LISTS.test(uncomment(readFileSync(path.join(tests, name), 'utf8')))) { run.push(name); continue; }
    const seen = new Set();
    const text = textOf(path.join(tests, name), seen);
    const reach = new Set([...seen].map(norm));
    for (const b of new Set(text.match(NAMES) || [])) {
      const fs = byBase.get(b.toLowerCase()) || [];
      for (const f of fs) {
        const dir = path.posix.basename(path.posix.dirname(f));
        if (fs.length === 1 || text.includes(`${dir}/`) || text.includes(`'${dir}'`)) reach.add(f);
      }
    }
    if (reach.size === seen.size && !scopes) { run.push(name); continue; }   // names no file - nothing to narrow by
    // Listing a folder names every file in it - an html page listed reaches its modules like a page named.
    if (scopes) for (const f of tracked) if (scanCovers(scopes, top, f, 'file')) reach.add(f);
    for (const f of [...reach]) for (const m of graph.get(f) || []) reach.add(m);
    reaches.set(name, reach);
    (changed.some((f) => reach.has(f) || (scopes && scanCovers(scopes, top, f, 'file'))) ? run : notRun).push(name);
  }
  return { run, notRun, why: null, reach: reaches };
}
