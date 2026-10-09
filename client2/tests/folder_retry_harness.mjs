// File Ingestion: retry the failed files under one folder (lead f0e668bb8).
// The part is driven in the page stub; the server's answers are the fixture's. The listed
// paths deliberately DISAGREE with the server's count (5 listed under the folder, the server
// says 3) — a screen that counted for itself would put 5 on the button.
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { makeDoc, makeNode, walk } from './lib/board_dom.mjs';

const SRC_PATH = fileURLToPath(new URL('../src/folder_retry.js', import.meta.url));
const doc = makeDoc('light');
globalThis.document = doc;

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else { fail++; failedNames.push(name); if (!quiet) console.log(`  BAD  ${name}`); }
}

const LOT = 'C:\\ws\\lot';
const EMPTY = 'C:\\ws\\empty';
const FAILED = [`${LOT}\\a\\1.csv`, `${LOT}\\a\\2.csv`, `${LOT}\\3.csv`, `${LOT}\\b\\4.csv`, `${LOT}\\b\\5.csv`];
// The page's rows: the failed ones, and one that loaded in a folder no failed file is under.
const OK_FOLDER = 'D:\\done\\in';
const ROWS = FAILED.map((filepath, i) => ({ id: i + 1, status: 'FAILED', filepath }))
  .concat([{ id: 9, status: 'SUCCESS', filepath: `${OK_FOLDER}\\ok.csv` }]);
const SERVER = {
  [LOT]: { status: 'preview', folder: LOT, count: 3, by_folder: { '.': 1, a: 2 }, message: `3 failed file(s) under ${LOT}` },
  [EMPTY]: { status: 'preview', folder: EMPTY, count: 0, by_folder: {}, message: `No failed file under ${EMPTY}` },
};
const RETRIED = 'Decoupled mode: Marked 3 logs as PENDING_RETRY. Standalone watcher will process them.';
// The same folder asked with the files that went in (server 04b40d64b's shape).
const SERVER_IN = { status: 'preview', folder: LOT, count: 14, by_state: { FAILED: 2, SKIPPED: 1, SUCCESS: 11 }, by_folder: { a: 14 },
  missing: 10, missing_files: ['m1.csv', 'm2.csv', 'm3.csv', 'm4.csv', 'm5.csv'], message: `14 file(s) under ${LOT}` };

function seat(M, answers = {}) {
  const calls = { preview: [], retry: [], include: [], retryInclude: [], refreshed: 0 };
  const mount = makeNode(doc, 'div');
  doc.body.appendChild(mount);
  const part = new M.FolderRetryPanel(mount, {
    doc,
    rows: () => ROWS,
    preview: async (folder, include) => {
      calls.preview.push(folder);
      calls.include.push(include);
      if (answers.previewFails) return { ok: false, text: 'Preview failed · 503' };
      if (include && folder === LOT) return { ok: true, body: SERVER_IN };
      return { ok: true, body: SERVER[folder] || { status: 'preview', folder, count: 0, by_folder: {}, message: `No failed file under ${folder}` } };
    },
    retry: async (folder, include) => {
      calls.retry.push(folder);
      calls.retryInclude.push(include);
      return { ok: true, body: { status: 'success', message: RETRIED } };
    },
    onRetried: () => { calls.refreshed += 1; },
  });
  const cls = (c) => walk(mount).find((n) => String(n.className || '').split(/\s+/).includes(c));
  const type = (text) => { part.input.value = text; part.input.dispatch('input', {}); };
  const press = async (c) => { cls(c).dispatch('click', {}); await new Promise((r) => setTimeout(r, 0)); };
  return { part, calls, cls, type, press, mount };
}

async function suite(M) {
  const before = { pass, fail };

  // ── A: nothing runs before a preview ────────────────────────────────────────────
  {
    const s = seat(M);
    const run = s.cls('folder-retry-run');
    ok(s.cls('folder-retry-preview').disabled === true, 'A1 Preview is off while the field is empty');
    s.type(LOT);
    ok(run.disabled === true && run.attrs.title === M.FOLDER_RETRY_WORDS.previewFirst,
      `A2 Retry is off until this folder is previewed, and says so [${run.attrs.title}]`);
    await s.press('folder-retry-run');
    ok(s.calls.retry.length === 0, `A3 pressing it anyway sends nothing [${s.calls.retry.length}]`);
  }

  // ── B: the number is the server's, the button carries it, the press runs that folder ─────
  {
    const s = seat(M);
    s.type(LOT);
    await s.press('folder-retry-preview');
    const run = s.cls('folder-retry-run');
    ok(s.calls.preview.length === 1 && s.calls.preview[0] === LOT, 'B1 Preview asks the server about the folder typed');
    ok(s.cls('folder-retry-said').textContent === SERVER[LOT].message,
      `B2 the sentence is the server's, as it came [${s.cls('folder-retry-said').textContent}]`);
    ok(run.textContent === 'Retry 3' && run.disabled === false,
      `B3 Retry carries the server's count, not the 5 listed paths [${run.textContent}]`);
    const rows = walk(s.cls('folder-retry-by')).filter((n) => n.tagName === 'DIV' && n !== s.cls('folder-retry-by'))
      .map((n) => n.textContent);
    ok(JSON.stringify(rows) === JSON.stringify(['. · 1', 'a · 2']),
      `B4 under it, each folder just below with its count, as the server grouped them [${rows}]`);
    await s.press('folder-retry-run');
    ok(s.calls.retry.length === 1 && s.calls.retry[0] === LOT, `B5 the press runs the previewed folder once [${s.calls.retry}]`);
    ok(s.cls('folder-retry-said').textContent === RETRIED, 'B6 the result is the server\'s sentence');
    ok(run.disabled === true && run.textContent === 'Retry' && s.calls.refreshed === 1,
      `B7 the count is spent: Retry is off until the next preview, and the list is read again [${run.textContent}]`);
  }

  // ── C: a changed folder is a new question ───────────────────────────────────────
  {
    const s = seat(M);
    s.type(LOT);
    await s.press('folder-retry-preview');
    s.type(`${LOT}\\a`);
    const run = s.cls('folder-retry-run');
    ok(run.disabled === true && run.textContent === 'Retry' && run.attrs.title === M.FOLDER_RETRY_WORDS.previewFirst,
      `C1 changing the folder turns Retry off and drops the old number [${run.textContent}]`);
    await s.press('folder-retry-run');
    ok(s.calls.retry.length === 0, 'C2 ... and a press then sends nothing');
    s.type(LOT);
    ok(run.disabled === false && run.textContent === 'Retry 3', 'C3 back to the previewed folder, its preview stands');
  }

  // ── D: nothing to retry, and a refused preview ───────────────────────────────────
  {
    const s = seat(M);
    s.type(EMPTY);
    await s.press('folder-retry-preview');
    const run = s.cls('folder-retry-run');
    ok(run.disabled === true && run.attrs.title === SERVER[EMPTY].message,
      `D1 0 failed: Retry is off, and its reason is the server's sentence [${run.attrs.title}]`);
    const r = seat(M, { previewFails: true });
    r.type(LOT);
    await r.press('folder-retry-preview');
    ok(r.cls('refusal') && r.cls('refusal').textContent === 'Preview failed · 503'
      && r.cls('folder-retry-run').disabled === true, 'D2 a refused preview says the page\'s line and leaves Retry off');
  }

  // ── E: the suggestions are the list's own folders ─────────────────────────────────
  {
    const got = M.folderCandidates(['C:\\ws\\lot\\a\\1.csv', '/data/in/x.csv']);
    ok(JSON.stringify(got) === JSON.stringify(['/data', '/data/in', 'C:\\ws', 'C:\\ws\\lot', 'C:\\ws\\lot\\a']),
      `E1 every folder above a listed file, no bare drive and no empty one [${got}]`);
    const s = seat(M);
    s.part.input.dispatch('focus', {});
    const options = walk(s.part.list).filter((n) => n.tagName === 'OPTION').map((n) => n.value);
    ok(options.includes(LOT) && options.includes(`${LOT}\\a`), `E2 the field offers them when it is focused [${options.length}]`);
    ok(!options.some((o) => o.startsWith('D:')), `E3 ... from the FAILED rows only — a loaded file's folders are not offered [${options}]`);
  }

  // ── F: the files that went in (lead a4d135a06): the toggle rides on the ask, and its preview is its own ────
  {
    const s = seat(M);
    s.type(LOT);
    await s.press('folder-retry-preview');
    ok(s.calls.include[0] === false, `F1 off, the preview asks for the failed files only [${s.calls.include}]`);
    const box = s.cls('folder-retry-include-box');
    box.checked = true;
    box.dispatch('change', {});
    const run = s.cls('folder-retry-run');
    ok(run.disabled === true && run.textContent === 'Retry' && run.attrs.title === M.FOLDER_RETRY_WORDS.previewFirst,
      `F2 turning it on drops the old preview: Retry is off until this is previewed [${run.textContent}]`);
    await s.press('folder-retry-preview');
    ok(s.calls.include[1] === true && run.textContent === 'Retry 14',
      `F3 on, the preview asks for the files that went in too, and Retry carries that count [${s.calls.include} · ${run.textContent}]`);
    const rows = walk(s.cls('folder-retry-by')).filter((n) => n.tagName === 'DIV' && n !== s.cls('folder-retry-by'))
      .map((n) => n.textContent);
    const want = ['FAILED 2 · SKIPPED 1 · SUCCESS 11', 'a · 14', `${M.FOLDER_RETRY_WORDS.missing} 10: m1.csv, m2.csv, m3.csv, m4.csv, m5.csv, …`];
    ok(JSON.stringify(rows) === JSON.stringify(want),
      `F4 the answer as it came: by state, each folder, the files not where their record says [${rows}]`);
    await s.press('folder-retry-run');
    ok(s.calls.retryInclude[0] === true && s.calls.retry[0] === LOT, `F5 Retry sends the toggle its preview had [${s.calls.retryInclude}]`);
  }

  return { pass: pass - before.pass, fail: fail - before.fail };
}

console.log('-- the real module -------------------------------------------------');
await suite(await import('../src/folder_retry.js'));
const base = { pass, fail };
const baseFailed = [...failedNames];

const DEFECTS = [
  ['Retry runs without a preview',
    (s) => s.replace(": !seen ? FOLDER_RETRY_WORDS.previewFirst", ": !seen ? ''")
      .replace('    const seen = this.current();\n    if (!seen', '    const seen = this.current() || { folder: this.folder(), count: 1 };\n    if (!seen')],
  ['the screen counts the files itself',
    (s) => s.replace('count: body.count,', 'count: this.rows().filter((r) => String(r.filepath).startsWith(folder)).length,')],
  ['the suggestions take every row, not the failed ones',
    (s) => s.replace('.filter((r) => r && isFailedStatus(r.status))', '.filter((r) => r)')],
  ['a changed folder keeps the old preview',
    (s) => s.replace('return this.seen && this.seen.folder === this.folder() && this.seen.include === this.include() ? this.seen : null;',
      'return this.seen && this.seen.include === this.include() ? this.seen : null;')],
  ['a turned toggle keeps the old preview',
    (s) => s.replace('return this.seen && this.seen.folder === this.folder() && this.seen.include === this.include() ? this.seen : null;',
      'return this.seen && this.seen.folder === this.folder() ? this.seen : null;')],
  ['the toggle is not sent',
    (s) => s.replace('const got = await this.preview(folder, include);', 'const got = await this.preview(folder, false);')],
  ['the files not where their record says are not drawn',
    (s) => s.replace("          ...(missing ? [`${FOLDER_RETRY_WORDS.missing} ${missing}: ${names.join(', ')}${missing > names.length ? ', …' : ''}`] : []),\n", '')],
  ['0 failed leaves Retry on',
    (s) => s.replace(": seen.count > 0 ? '' : seen.message", ": ''")],
];
const CONTROLS = [
  ['comments stripped', (s) => s.split('\n').filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join('\n')],
];

async function scoreMutant(mutate) {
  try {
    return await suite((await loadWithProbe(SRC_PATH, { mutate, tag: 'folderretry' })).module);
  } catch (e) {
    if (/did not mutate|unchanged/.test(String(e && e.message))) {
      quiet = false;
      console.error(`\nan anchor no longer matches: ${e.message}`);
      process.exit(2);
    }
    return { pass: 0, fail: 1 };
  }
}

quiet = true;
let caught = 0; const escapedNames = [];
console.log('\n-- defect mutants (each must be CAUGHT) ----------------------------');
for (const [name, mutate] of DEFECTS) {
  const r = await scoreMutant(mutate);
  if (r.fail > 0) { caught++; console.log(`  caught  ${name}`); }
  else { escapedNames.push(name); console.log(`  ESCAPED ${name}`); }
}
let controlsCaught = 0;
console.log('\n-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, mutate] of CONTROLS) {
  const r = await scoreMutant(mutate);
  if (r.fail === 0) console.log(`  escaped ${name}`);
  else { controlsCaught++; console.log(`  CAUGHT  ${name}  <- a check is reading source text`); }
}
quiet = false;

if (base.fail) console.error(`\nfailed:\n  ${baseFailed.join('\n  ')}`);
const bad = base.fail + escapedNames.length + controlsCaught;
console.log(`\n${base.pass} passed, ${base.fail} failed; ${caught}/${DEFECTS.length} defects caught, `
  + `${escapedNames.length} escaped; ${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
process.exit(bad ? 1 : 0);
