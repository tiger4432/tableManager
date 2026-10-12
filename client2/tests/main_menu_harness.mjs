#!/usr/bin/env node
// The main grid's «🧭 Menu» (client2/index.html #nav-dropdown): every page it names is a page the build makes, and
// «Board» opens the test bed the way its neighbours open theirs (owner 10-13 via the lead: «board 라는 이름으로 메인
// 그리드에 메뉴 달아서»). The markup is the subject - read as text, a drift oracle, not code sliced to run.
//   node client2/tests/main_menu_harness.mjs
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readSourceText } from './lib/probe.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..');
const INDEX = readSourceText(path.join(ROOT, 'index.html')).text;
// The build's own config, through the loader the build uses (it bundles the file, so its __dirname resolves).
const { loadConfigFromFile } = await import('vite');
const { config: CONFIG } = await loadConfigFromFile({ command: 'build', mode: 'production' }, path.join(ROOT, 'vite.config.js'), ROOT, 'silent');

/** The menu's items: each <a> inside #nav-dropdown, its attributes and its words, comments aside. */
function menuOf(html) {
  const from = html.indexOf('id="nav-dropdown"');
  if (from < 0) return [];
  const block = html.slice(from, html.indexOf('</div>', from)).replace(/<!--[\s\S]*?-->/g, '');
  return [...block.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a\s*>/g)].map(([, attrs, words]) => ({
    attrs: Object.fromEntries([...attrs.matchAll(/([\w-]+)(?:="([^"]*)")?/g)].map(([, k, v]) => [k, v === undefined ? true : v])),
    words: words.replace(/\s+/g, ' ').trim(),
  }));
}

function measure(html, config) {
  const items = menuOf(html);
  const pages = Object.values(((config.build || {}).rollupOptions || {}).input || {}).map((p) => `/${path.basename(p)}`);
  const board = items.find((i) => /(^| )Board$/.test(i.words));
  const walk = items.find((i) => i.attrs.href === '/walk.html');
  const form = (i) => (i ? { class: i.attrs.class, target: i.attrs.target || null, download: Boolean(i.attrs.download) } : null);
  return {
    items: items.length,
    board: board ? { href: board.attrs.href, form: form(board) } : null,
    walkForm: form(walk),
    // Every page the menu names (not the API's download) is one the build writes.
    unbuilt: items.map((i) => i.attrs.href).filter((h) => h && h.endsWith('.html') && !pages.includes(h)),
  };
}

const cells = (o) => [
  ['M1 the menu has «Board», to /testbed.html, opened as Walk opens - the same classes, no new tab, no download',
    [o.items > 3, o.board && o.board.href, o.board && JSON.stringify(o.board.form) === JSON.stringify(o.walkForm)],
    [true, '/testbed.html', true]],
  ['M2 every page the menu names is a page the build writes', o.unbuilt, []],
];

const DEFECTS = [
  ['D1 Board goes to the R&D board -> M1', 'M1', (h) => h.replace('href="/testbed.html"', 'href="/rnd-board.html"'), null],
  ['D2 Board opens a new tab -> M1', 'M1', (h) => h.replace('<a href="/testbed.html"', '<a target="_blank" href="/testbed.html"'), null],
  ['D3 Board named otherwise -> M1', 'M1', (h) => h.replace('📊 Board<', '📊 Test bed<'), null],
  ['D4 the build does not write testbed.html -> M2', 'M2', null, (c) => {
    const input = { ...c.build.rollupOptions.input };
    delete input.testbed;
    return { ...c, build: { ...c.build, rollupOptions: { ...c.build.rollupOptions, input } } };
  }],
];

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
let pass = 0;
let fail = 0;
console.log('-- the main grid menu ---------------------------------------------');
for (const [label, got, want] of cells(measure(INDEX, CONFIG))) {
  const ok = same(got, want);
  console.log(`  ${ok ? 'PASS' : 'FAIL'} ${label}${ok ? '' : `\n        got  ${JSON.stringify(got)}\n        want ${JSON.stringify(want)}`}`);
  if (ok) pass += 1; else fail += 1;
}
console.log('-- defect mutants (each must be caught by the check it names) ------');
for (const [label, name, html, config] of DEFECTS) {
  const text = html ? html(INDEX) : INDEX;
  if (html && text === INDEX) throw new Error(`mutant «${label}» changed nothing - its anchor is gone`);
  const caught = cells(measure(text, config ? config(CONFIG) : CONFIG)).some(([n, g, w]) => n.startsWith(name) && !same(g, w));
  console.log(`  ${caught ? 'caught ' : 'ESCAPED'} ${label}`);
  if (caught) pass += 1; else fail += 1;
}
console.log(`ASSERTIONS ${pass + fail} ${fail}`);
if (fail) process.exitCode = 1;
