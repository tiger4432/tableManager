// The build's third-party notice (scripts/third_party_licenses.mjs, lead 10-06), measured on a node_modules made in a
// temp folder in the real tree's shapes: a pre-bundled copy whose map path is the carrier's own build tree, a nested
// dependency, a hoisted one - and what this box never meets: a copy that differs, a package with no license file.
// The plugin is called the way the bundler calls it. Each defect below must be caught by the line it names.
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const SUBJECT = fileURLToPath(new URL('../scripts/third_party_licenses.mjs', import.meta.url));

const tmp = mkdtempSync(path.join(os.tmpdir(), 'notice-'));
const put = (rel, text) => { const f = path.join(tmp, rel); mkdirSync(path.dirname(f), { recursive: true }); writeFileSync(f, text); return f; };
const pkg = (dir, o) => put(`${dir}/package.json`, JSON.stringify(o));
const DEP = 'export const x = 1;\n';
const MOVED = 'export const x = 2;\n';
pkg('node_modules/carrier', { name: 'carrier', version: '1.0.0', license: 'MIT', devDependencies: { dep: '^2.0.0' }, dependencies: { dep2: '3.0.0' } });
put('node_modules/carrier/LICENSE', 'carrier text');
pkg('node_modules/carrier/node_modules/dep2', { name: 'dep2', version: '3.0.0', license: 'ISC', dependencies: { dep3: '1.0.0' } });
put('node_modules/carrier/node_modules/dep2/LICENSE.md', 'dep2 text');
pkg('node_modules/dep3', { name: 'dep3', version: '1.0.0', license: 'MIT' });
put('node_modules/dep3/COPYING', 'dep3 text');
pkg('node_modules/dep', { name: 'dep', version: '2.0.0', license: 'MIT' });
put('node_modules/dep/LICENSE', 'dep text');
put('node_modules/dep/dist/d.js', DEP);
pkg('node_modules/bare', { name: 'bare', version: '0.1.0', license: 'MIT' });
const bare = put('node_modules/bare/index.js', '');
// The map's paths are the carrier's own build tree (its node_modules/dep), as cytoscape-dagre's are.
const carrier = (copy) => {
  const f = put('node_modules/carrier/dist/c.mjs', '');
  put('node_modules/carrier/dist/c.mjs.map', JSON.stringify({ sources: ['../src/own.mjs', '../node_modules/dep/dist/d.js'], sourcesContent: ['', copy] }));
  return f;
};

let ran = 0;
let failed = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1; NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failed.push(name);
  console.log(`  FAIL ${name}${detail ? ' -- ' + detail : ''}`);
};

function suite({ NOTICE_FILE, noticeOf, thirdPartyLicenses }) {
  console.log('\n── F. what the notice holds ──');
  const same = noticeOf([carrier(DEP)]);
  ok('F1 the carrier, what its map carries (hoisted), its dependency (nested) and that one\'s (hoisted) are named',
    same.names.join() === 'carrier,dep,dep2,dep3', same.names.join());
  ok('F2 a carried copy equal to the installed file passes, and the carrier\'s own sources are not a copy',
    same.drift.length === 0 && same.compared === 1, `${same.drift} / ${same.compared}`);
  ok('F3 each section holds its package\'s license file', ['carrier text', 'dep text', 'dep2 text', 'dep3 text'].every((t) => same.text.includes(t))
    && same.text.includes('== dep2 3.0.0 (ISC)'), same.text);
  const heads = [...same.text.matchAll(/^== (\S+) \S+ \(.*\)$/gm)].map((m) => m[1]);
  ok('F4 one head line per package, in name order', heads.join() === same.names.join(), heads.join());

  const moved = noticeOf([carrier(MOVED)]);
  const want = "carrier 1.0.0 carries dep (built against ^2.0.0) whose dist/d.js is not the installed dep 2.0.0's - raise them together";
  ok('F5 a carried copy that differs is one sentence naming both versions', moved.drift.length === 1 && moved.drift[0] === want, moved.drift.join('; '));

  const lost = noticeOf([bare]);
  ok('F6 a package with no license file is missing, by name', lost.missing.join() === 'bare' && !lost.names.includes('bare'), lost.missing.join());

  console.log('\n── P. the plugin, called as the bundler calls it ──');
  const emitted = [];
  const ctx = { emitFile: (f) => emitted.push(f), error: (m) => { throw new Error(m); } };
  const chunk = (ids) => ({ a: { type: 'chunk', moduleIds: ids }, b: { type: 'asset' } });
  const stop = (ids) => { try { thirdPartyLicenses().generateBundle.call(ctx, {}, chunk(ids)); return null; } catch (e) { return e.message; } };
  const good = stop([carrier(DEP), '\0vite/preload-helper.js']);
  ok('P1 a good build emits the notice at the dist root', good === null && emitted.length === 1
    && emitted[0].fileName === NOTICE_FILE && emitted[0].source === same.text, good || JSON.stringify(emitted.map((e) => e.fileName)));
  const drifted = stop([carrier(MOVED)]);
  ok('P2 a differing copy stops the build with that sentence', drifted !== null && drifted.includes(want), drifted);
  const unread = stop([bare]);
  ok('P3 an unreadable package stops the build by name', unread !== null && unread.includes('bare ships in this build'), unread);
  ok('P4 a stopped build emits nothing', emitted.length === 1, emitted.length);
  return { ran, failed: failed.slice() };
}

const MUTANTS = [
  { name: 'own-sources-count-as-copies', catches: ['F2'],
    from: '.filter((c) => c.name && c.name !== own);', to: '.filter((c) => c.name);' },
  { name: 'no-carried-discovery', catches: ['F1'], from: 'for (const c of carried(file, p.name))', to: 'for (const c of [])' },
  { name: 'no-dependency-following', catches: ['F1'], from: 'Object.keys(r.pkg.dependencies || {}).forEach', to: '[].forEach' },
  { name: 'lookup-stops-at-its-own-node_modules', catches: ['F1'],
    from: '    if (path.dirname(d) === d) return null;', to: '    return null;' },
  { name: 'no-content-comparison', catches: ['F5'], from: "readFileSync(installed, 'utf8') === c.content) continue;", to: 'true) continue;' },
  { name: 'unreadable-package-dropped-silently', catches: ['F6'],
    from: 'if (!r) { missing.push(p.name); continue; }', to: 'if (!r) { continue; }' },
  { name: 'plugin-ignores-drift', catches: ['P2'], from: '...drift];', to: '];' },
  { name: 'plugin-emits-beside-the-root', catches: ['P1'], from: 'fileName: NOTICE_FILE', to: 'fileName: `assets/${NOTICE_FILE}`' },
  { name: 'license-text-left-out', catches: ['F3'], from: '\\n\\n${r.text}\\n`', to: '\\n`' },
];

const load = async (mutate) => (await loadWithProbe(SUBJECT, mutate ? { mutate } : {})).module;

const main = async () => {
  let wrong = 0;
  try {
    console.log('== baseline ==');
    const base = suite(await load());
    const BASE_NAMES = NAMES.slice();
    if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
    ({ wrong } = await scoreMutants(MUTANTS, async (m) => {
      const swap = (t) => { if (!t.includes(m.from)) throw new Error(`mutation anchor is GONE: ${m.name}`); return t.split(m.from).join(m.to); };
      const mod = await load(swap);
      const real = console.log;
      console.log = () => {};
      ran = 0; failed = [];
      try { suite(mod); } finally { console.log = real; }
      return { failures: failed, ran };
    }, { baselineRan: base.ran, baselineNames: BASE_NAMES,
         title: '\n== defect mutants (each must be CAUGHT by its named line) ==' }));
    console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
  process.exit(wrong ? 1 : 0);
};

main();
