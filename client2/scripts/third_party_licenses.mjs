// The build writes dist/THIRD_PARTY_LICENSES.txt (lead 10-06: the build makes it, no hand copy): for every package
// whose code ships in a chunk, its name, version, license and license file, read from node_modules at build time.
// A package is in when a chunk carries one of its files, when that file's own source map lists another package's
// file (cytoscape-dagre ships @dagrejs/dagre pre-bundled), or when a package that is in depends on it.
// The build stops, by name, on a package it cannot read and on a carried file that is not the installed package's -
// a pre-bundled copy has no version to read, so the installed devDependency stands in for it and must be that file.
// A build that succeeds therefore wrote a whole notice; nothing reads dist afterwards (lead 10-06).
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

export const NOTICE_FILE = 'THIRD_PARTY_LICENSES.txt';
const NM = '/node_modules/';

// '<...>/node_modules/@a/b/dist/c.js' -> { name: '@a/b', dir: '<...>/node_modules/@a/b', rel: 'dist/c.js' }
function packageAt(file) {
  const f = file.replace(/\\/g, '/').split('?')[0];
  const i = f.lastIndexOf(NM) + NM.length;
  if (i < NM.length) return null;
  const parts = f.slice(i).split('/');
  const name = parts[0].startsWith('@') ? `${parts[0]}/${parts[1]}` : parts[0];
  return { name, dir: f.slice(0, i) + name, rel: f.slice(i + name.length + 1) };
}

// Where node finds `name` from `dir`: its own node_modules, then each one above.
function locate(name, dir) {
  for (let d = dir; ; d = path.dirname(d)) {
    if (path.basename(d) !== 'node_modules' && existsSync(path.join(d, 'node_modules', name, 'package.json'))) {
      return path.join(d, 'node_modules', name);
    }
    if (path.dirname(d) === d) return null;
  }
}

// The other packages a package file's own source map lists - its own sources (cytoscape-dagre's src/) are not a copy.
function carried(file, own) {
  const map = `${file.replace(/\\/g, '/').split('?')[0]}.map`;
  if (!existsSync(map)) return [];
  const { sources = [], sourceRoot = '', sourcesContent = [] } = JSON.parse(readFileSync(map, 'utf8'));
  return sources.map((s, i) => ({ ...packageAt(path.resolve(path.dirname(map), sourceRoot, s)), content: sourcesContent[i] }))
    .filter((c) => c.name && c.name !== own);
}

function read(dir) {
  if (!dir || !existsSync(path.join(dir, 'package.json'))) return null;
  const file = readdirSync(dir).find((f) => /^(licen[cs]e|copying)(\.|$)/i.test(f));
  if (!file) return null;
  return { dir, pkg: JSON.parse(readFileSync(path.join(dir, 'package.json'), 'utf8')),
    text: readFileSync(path.join(dir, file), 'utf8').trim() };
}

export function noticeOf(files) {
  const queue = [];
  const seen = new Set();
  const copies = [];
  const add = (name, dir) => { if (!seen.has(name)) { seen.add(name); queue.push({ name, dir }); } };
  for (const file of files) {
    const p = packageAt(file);
    if (!p) continue;
    add(p.name, p.dir);
    for (const c of carried(file, p.name)) { add(c.name, locate(c.name, p.dir)); copies.push({ by: p.name, ...c }); }
  }
  const found = new Map();
  const missing = [];
  while (queue.length) {
    const p = queue.shift();
    const r = read(p.dir);
    if (!r) { missing.push(p.name); continue; }
    found.set(p.name, r);
    Object.keys(r.pkg.dependencies || {}).forEach((d) => add(d, locate(d, r.dir)));
  }
  const drift = [];
  let compared = 0;
  for (const c of copies) {
    const own = found.get(c.name);
    const by = found.get(c.by);
    if (!own || !by || c.content === undefined) continue;
    compared += 1;
    const installed = path.join(own.dir, c.rel);
    if (existsSync(installed) && readFileSync(installed, 'utf8') === c.content) continue;
    const range = { ...by.pkg.dependencies, ...by.pkg.devDependencies }[c.name] || 'an unstated version';
    drift.push(`${c.by} ${by.pkg.version} carries ${c.name} (built against ${range}) whose ${c.rel} is not the installed `
      + `${c.name} ${own.pkg.version}'s - raise them together`);
  }
  const names = [...found.keys()].sort((a, b) => a.localeCompare(b));
  const text = names.map((n) => { const r = found.get(n); return `== ${n} ${r.pkg.version} (${r.pkg.license})\n\n${r.text}\n`; })
    .join('\n');
  return { names, missing, drift, compared, text };
}

export function thirdPartyLicenses() {
  return {
    name: 'third-party-licenses',
    generateBundle(_, bundle) {
      const ids = Object.values(bundle).filter((c) => c.type === 'chunk').flatMap((c) => c.moduleIds);
      const { missing, drift, text } = noticeOf(ids);
      const wrong = [...missing.map((n) => `${n} ships in this build but has no installed package.json with a license file`),
        ...drift];
      if (wrong.length) this.error(`${NOTICE_FILE}: ${wrong.join('; ')}`);
      this.emitFile({ type: 'asset', fileName: NOTICE_FILE, source: text });
    },
  };
}
