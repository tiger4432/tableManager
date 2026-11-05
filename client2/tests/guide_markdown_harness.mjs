// The Help panel's Guide body (guide_markdown.js, owner 11-06): every guide the Help reads (server/admin/help_guides.json)
// is read with no line left as letters - a shape the reader does not know is drawn as its text, so the count is 0
// (lead 11-06). And the shapes the guides hold come out as blocks: tables, code blocks, quotes, lists.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readMarkdown, unknownOf, runsOf, hitsIn, inline } from '../src/guide_markdown.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
let ran = 0;
let failed = 0;
const check = (ok, what) => { ran += 1; if (!ok) { failed += 1; console.log(`  ✗ ${what}`); } };

const guides = Object.keys(JSON.parse(readFileSync(path.join(ROOT, 'server', 'admin', 'help_guides.json'), 'utf8')).guides);
check(guides.length >= 7, `canary: the guide list holds the Help's guides (${guides.length})`);
const kinds = {};
const count = (blocks) => blocks.forEach((b) => {
  kinds[b.t] = (kinds[b.t] || 0) + 1;
  if (b.t === 'quote') count(b.blocks);
  if (b.t === 'list') b.items.forEach(count);
});
for (const g of guides) {
  const blocks = readMarkdown(readFileSync(path.join(ROOT, g), 'utf8'));
  const unknown = unknownOf(blocks);
  check(unknown.length === 0, `${g}: no line left as letters - ${unknown.slice(0, 2).join(' / ')}`);
  count(blocks);
}
for (const t of ['table', 'pre', 'quote', 'list', 'p', 'h']) check((kinds[t] || 0) > 0, `the guides hold a ${t}`);

// a table row with no header row before it is a line the reader does not know
check(unknownOf(readMarkdown('text\n\n| a | b |\n')).length === 1, 'a headless table row is counted');
// a fence under a list item stays in the item; a quote holds a table
const nested = readMarkdown('- item\n\n  ```\n  code\n  ```\n> | h |\n> |---|\n> | v |');
check(nested[0].t === 'list' && nested[0].items[0].some((b) => b.t === 'pre' && b.text === 'code'), 'a fence in a list item');
check(nested[1].t === 'quote' && nested[1].blocks[0].t === 'table', 'a table in a quote');
// inline: code keeps its pipes, bold holds code
check(JSON.stringify(inline('a `x|y` **`k`**')) === JSON.stringify([{ t: 'text', s: 'a ' }, { t: 'code', s: 'x|y' },
  { t: 'text', s: ' ' }, { t: 'b', inl: [{ t: 'code', s: 'k' }] }]), 'inline runs');
// Find counts in the runs the body draws
const runs = runsOf(readMarkdown('Allow `allow_x` and ALLOW_x\n\n| allow_x |\n|---|\n| y |'));
check(runs.reduce((n, r) => n + hitsIn(r, 'allow_x').length, 0) === 3, 'Find counts every run, case folded');

console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed ? 1 : 0);
