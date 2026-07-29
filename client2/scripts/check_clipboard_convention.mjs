#!/usr/bin/env node
// ── Convention guard: `navigator.clipboard` is BANNED in write paths ────────────────
//
// WHY THIS EXISTS. Production is a plain-HTTP LAN intranet, which is a NON-SECURE CONTEXT,
// so `navigator.clipboard` is not merely restricted - the whole object is `undefined`.
// Four separate files carry comments saying exactly this, and the code still drifted back:
// `map_editor.copyGridToExcel` called `navigator.clipboard.writeText` on that undefined
// object, and its `catch` called the SAME expression a second time, so the button ended in
// a Korean alert every single time a user pressed it. Comments did not hold the line, so
// this check does.
//
// THE SANCTIONED PATTERN for writing is the `copy` event's `e.clipboardData`
// (`clipboard.js` for the grid, `map_editor.writeClipboardRich` for the wafer map).
//
// EXIT CODES: 0 = clean, 1 = a new violation (or a listed exception that got fixed and
// should be removed from the list below).

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = join(fileURLToPath(new URL('../src/', import.meta.url)));

// The ONE sanctioned reader. `navigator.clipboard.read`/`readText` has no `e.clipboardData`
// equivalent outside a real paste event, so the grid's "paste from the OS" affordance is
// allowed to probe for it - it already degrades when the object is missing.
const ALLOW_READ = new Set(['main.js']);

// Known violations that predate this guard and belong to another owner. Listed, not
// silenced: the guard fails if any of them is REMOVED without updating this list, so the
// debt cannot rot invisibly, and it fails immediately for any NEW file.
const KNOWN = new Map([
  ['admin.js', { count: 2, owner: 'client-pm', note: 'JSON payload copy + transaction id copy - both write paths, both dead on plain HTTP' }],
]);

const SYMBOL = /navigator\s*\.\s*clipboard/g;

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (name.endsWith('.js') || name.endsWith('.mjs')) out.push(p);
  }
  return out;
}

// A hit inside a comment is documentation, not a call. Strip line and block comments and
// string literals before matching, otherwise every warning comment trips its own guard.
function stripNonCode(src) {
  let out = '';
  let i = 0;
  const n = src.length;
  while (i < n) {
    const c = src[i];
    const d = src[i + 1];
    if (c === '/' && d === '/') { while (i < n && src[i] !== '\n') i++; continue; }
    if (c === '/' && d === '*') { i += 2; while (i < n && !(src[i] === '*' && src[i + 1] === '/')) i++; i += 2; continue; }
    if (c === '"' || c === "'" || c === '`') {
      const q = c; i++;
      while (i < n && src[i] !== q) { if (src[i] === '\\') i++; i++; }
      i++; out += ' ';
      continue;
    }
    out += c; i++;
  }
  return out;
}

const found = new Map();
for (const file of walk(SRC)) {
  const rel = relative(SRC, file).split(sep).join('/');
  const code = stripNonCode(readFileSync(file, 'utf8'));
  const hits = code.match(SYMBOL);
  if (hits && hits.length) found.set(rel, hits.length);
}

const problems = [];
for (const [rel, count] of found) {
  if (ALLOW_READ.has(rel)) continue;
  const known = KNOWN.get(rel);
  if (!known) { problems.push(`NEW VIOLATION  ${rel}: ${count} use(s) of navigator.clipboard`); continue; }
  if (count !== known.count) {
    problems.push(`CHANGED        ${rel}: ${count} use(s), list says ${known.count} - update KNOWN in this script`);
  }
}
for (const [rel, known] of KNOWN) {
  if (!found.has(rel)) problems.push(`STALE ENTRY    ${rel}: no longer uses navigator.clipboard - remove it from KNOWN`);
}

if (problems.length === 0) {
  const debt = [...KNOWN].map(([f, k]) => `${f} (${k.count}, owner ${k.owner})`).join(', ');
  console.log(`[clipboard-convention] OK. Allowed reader: ${[...ALLOW_READ].join(', ')}. Known debt: ${debt || 'none'}`);
  process.exit(0);
}

console.error('[clipboard-convention] FAILED\n');
for (const p of problems) console.error('  ' + p);
console.error(`
  navigator.clipboard is undefined in production (plain-HTTP LAN = non-secure context).
  Write to the clipboard through the copy event instead:

      const onCopy = (e) => {
        e.clipboardData.setData('text/html', html);
        e.clipboardData.setData('text/plain', text);
        e.preventDefault();
      };

  See client2/src/map_editor.js  writeClipboardRich()   (button-triggered, synthetic event)
      client2/src/clipboard.js   document 'copy' handler (user-triggered Ctrl+C)
`);
process.exit(1);
