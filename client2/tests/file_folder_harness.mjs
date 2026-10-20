// A FILE'S FOLDER ON ITS LOG LINE (owner 10-20 «파일 인제션 로그에 경로 좀 띄워 — 다 voids.json 이면 뭐가 뭔지 모름», lead):
//   P1 a short folder shown whole, the name left out
//   P2 a long one cut at the front on a folder line - the last folders stay, «…» says it was cut; the whole in the tooltip
//      and on the Copy
//   P3 a path with forward slashes the same
//   P4 no folder (a bare name, nothing, null) - no folder line
//   P5 a path cannot break out of the tooltip or the Copy's attribute
//   P6 both lists the row draws (the File tab's with a status, Auto Update's failures without) carry it
//   P7 the in-progress row the same folder line (lead, after A 6470b773f put `filepath` on /admin/file-ingestion/active)
// Imports only (the probe copies a module whole); each defect must go red at its line.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { scoreMutants } from './lib/mutation_scorer.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FILE = path.join(HERE, '..', 'src', 'admin_rows.js');

let ran = 0;
let failed = [];
const NAMES = [];
const ok = (name, cond, detail) => {
  ran += 1;
  NAMES.push(name);
  if (cond) { console.log(`  ok   ${name}`); return; }
  failed.push(name);
  console.log(`  FAIL ${name}${detail === undefined ? '' : ` -- ${detail}`}`);
};

const SHORT = 'C:\\data\\W12\\voids.json';
const LONG = 'D:\\operations\\inspection\\results\\2026\\10\\LOT-AB1234\\W12\\voids.json';
const row = (M, filepath, withStatus = true) => M.fileLogRowHtml({ id: 1, filename: 'voids.json', filepath, table_name: 't', status: 'SUCCESS', retry_count: 0 },
  { withStatus, timeStr: '10-20 09:00' });
const attr = (html, name) => { const m = html.match(new RegExp(`${name}="([^"]*)"`)); return m ? m[1] : null; };

async function suite(M) {
  ran = 0;
  failed = [];
  NAMES.length = 0;

  const s = M.folderOf(SHORT);
  ok('P1 a short folder shown whole, the name left out', s && s.full === 'C:\\data\\W12\\' && s.shown === s.full, JSON.stringify(s));

  const l = M.folderOf(LONG);
  const longRow = row(M, LONG);
  ok('P2a a long folder cut at the front on a folder line, the last folders kept',
    l && l.full === 'D:\\operations\\inspection\\results\\2026\\10\\LOT-AB1234\\W12\\' && l.shown.startsWith('…\\') && l.shown.endsWith('\\LOT-AB1234\\W12\\')
      && l.shown.length <= M.FOLDER_TAIL + 1 && l.full.endsWith(l.shown.slice(1)),
    JSON.stringify(l));
  ok('P2b the whole folder in the tooltip and on the Copy, the cut one on the line',
    attr(longRow, 'title') === l.full && attr(longRow, 'data-path') === l.full && longRow.includes(`>${l.shown}</span>`), longRow.slice(0, 400));

  const f = M.folderOf('/srv/lots/W07/voids.json');
  ok('P3 forward slashes the same', f && f.full === '/srv/lots/W07/' && f.shown === f.full, JSON.stringify(f));

  ok('P4 no folder - a bare name, nothing, null - no folder line',
    M.folderOf('voids.json') === null && M.folderOf('') === null && M.folderOf(null) === null && !row(M, 'voids.json').includes('file-folder') && !row(M, null).includes('file-folder'));

  const hostile = row(M, 'C:\\x" onmouseover="alert(1)\\<b>y</b>\\voids.json');
  ok('P5 a path cannot break out of the tooltip or the Copy, nor open an element', !/" onmouseover=/.test(hostile) && !hostile.includes('<b>'), hostile.slice(0, 400));

  ok('P6 both lists carry it - with a status and without', row(M, SHORT, true).includes('file-folder-copy') && row(M, SHORT, false).includes('file-folder-copy'));
  const active = (filepath) => M.activeIngestionRowHtml({ filename: 'voids.json', filepath, table_name: 't', lane: 'normal', progress: 40, status: 'PROCESSING', processed_rows: 1, total_rows: 2 }, { elapsedText: '3s' });
  const live = active(LONG);
  ok('P7 the in-progress row: the same folder line, the whole in its tooltip and Copy; none without a path',
    attr(live, 'title') === l.full && attr(live, 'data-path') === l.full && live.includes(`>${l.shown}</span>`) && !active(undefined).includes('file-folder'), live.slice(0, 400));
  return { ran, failed: failed.slice() };
}

const swap = (from, to) => (t) => { if (!t.includes(from)) throw new Error(`mutation anchor is GONE: ${from.slice(0, 60)}`); return t.split(from).join(to); };
const MUTANTS = [
  { name: 'the name kept on the folder', catches: ['P1'], mutate: swap('  const full = path.slice(0, cut + 1);', '  const full = path;') },
  { name: 'cut at the back, not the front', catches: ['P2a'], mutate: swap('  const tail = full.slice(full.length - FOLDER_TAIL);', '  const tail = full.slice(0, FOLDER_TAIL);') },
  { name: 'cut mid-folder', catches: ['P2a'], mutate: swap('  const at = tail.search(', '  const at = 0 * tail.search(') },
  { name: 'the tooltip holds the cut folder', catches: ['P2b'], mutate: swap('  const full = escapeHtml(folder.full);', '  const full = escapeHtml(folder.shown);') },
  { name: 'backslashes only', catches: ['P3'], mutate: swap(", path.lastIndexOf('/'));", ', -1);') },
  { name: 'a bare name drawn as a folder', catches: ['P4'], mutate: swap('  if (cut < 0) return null;', "  if (cut < 0) return { full: path, shown: path };") },
  { name: 'the path not escaped', catches: ['P5'], mutate: swap('  const full = escapeHtml(folder.full);', '  const full = folder.full;') },
  { name: 'the folder only on the status list', catches: ['P6'], mutate: swap('${escapeHtml(log.filename)}${folderLineHtml(log.filepath)}</td>', "${escapeHtml(log.filename)}${withStatus ? folderLineHtml(log.filepath) : ''}</td>") },
  { name: 'the in-progress row without its folder', catches: ['P7'], mutate: swap('${escapeHtml(item.filename)}${folderLineHtml(item.filepath)}</td>', '${escapeHtml(item.filename)}</td>') },
];

const load = async (m) => (await loadWithProbe(FILE, m ? { mutate: m.mutate } : {})).module;
const base = await suite(await load());
const BASE_NAMES = NAMES.slice();
if (base.failed.length) { console.log(`ASSERTIONS ${base.ran} ${base.failed.length}`); process.exit(1); }
const { wrong } = await scoreMutants(MUTANTS, async (m) => {
  const M = await load(m);
  const real = console.log;
  console.log = () => {};
  try { const r = await suite(M); return { failures: r.failed, ran: r.ran }; } finally { console.log = real; }
}, { baselineRan: base.ran, baselineNames: BASE_NAMES, title: '\n== defect mutants (each must be CAUGHT by its named line) ==' });
console.log(`\nASSERTIONS ${base.ran} ${base.failed.length}`);
process.exit(wrong ? 1 : 0);
