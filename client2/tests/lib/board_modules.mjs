// ═══════════════════════════════════════════════════════════════════════════════
// THE BOARD, LOADED — one loader, two harnesses.
//
// 🔴 IT MOVED HERE ON 2026-09-08 BECAUSE A SECOND HARNESS NEEDED IT. `rnd_board_harness`
//    owned this and the render-parity harness needs the SAME wiring; copying it would have
//    made the two drift the first time a part was added, and a forgotten part does not fail
//    one assertion — it throws ERR_INVALID_URL before any check runs. One loader, one place.
// ═══════════════════════════════════════════════════════════════════════════════
import { readSourceText } from './probe.mjs';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const SRC_DIR = path.join(HERE, '..', '..', 'src');
export const BOARD_DIR = path.join(SRC_DIR, 'rnd_board');
const srcUrl = (rel) => pathToFileURL(path.join(SRC_DIR, rel)).href;
const dataUrl = (src) => `data:text/javascript;base64,${Buffer.from(src, 'utf8').toString('base64')}`;
// 🔴 C-93. EVERY module URL goes through HERE, and `outward` is inside it. It used to be
//    applied at the call sites, and `api.js`'s site (plus `main.js`'s) simply did not have it --
//    so the day `api.js` gained its first outward import, EIGHT board harnesses stopped
//    measuring anything. The loader already knew the rule (see `OUTWARD_RE` below); what it
//    lacked was a place where forgetting is impossible.
const moduleUrl = (src) => dataUrl(outward(src));
// ── loading the modules under test, with an optional mutation per file ─────────────
//
// The relative imports are rewritten so a mutated copy still pulls the OTHER modules under
// test (mutated or not), and reaches the real `map2/painter.js` where it sits.

// 🔴 ANY PARENT-RELATIVE SPECIFIER, GENERICALLY. A hand-written list of rewrites has taken
//    harnesses down twice now (`../walk/derive.js` in C-70, `../server_time.js` in C-77), and
//    both times the failure was 「it used to assert and now measures nothing」 -- never one red
//    assertion. A part that imports one more sibling directory must not be able to do that
//    again, so `'../x/y.js'` resolves to the real file on disk rather than to a name somebody
//    remembered to add here.
// ⚠️ Same-directory `'./x.js'` is NOT swept up: those are the modules under test and they must
//    keep pointing at their data: URL twins, mutation and all.
const OUTWARD_RE = /'(\.\.\/[A-Za-z0-9_./-]+\.js)'/g;
const outward = (text) => text.replace(OUTWARD_RE, (whole, rel) => {
  const real = path.join(BOARD_DIR, rel);
  return existsSync(real) ? `'${pathToFileURL(real).href}'` : whole;
});

export async function loadBoardModules(mutate = {}) {
  // 🔴 THE TEXTS ARE CARRIED OUT WITH THE MODULES. Section F scans SOURCE, and scanning the
  // file on disk would make it blind to every mutant -- which is exactly what it did on the
  // first run: M5 (a module-level `let` prepended to `map_panel.js`) sailed through, because
  // the scan was reading the shipped file while the suite drove the mutated one.
  const sources = {};
  const read = (file) => {
    const text = readSourceText(path.join(BOARD_DIR, file)).text
      .replace(new RegExp(String.fromCharCode(13, 10), 'g'), String.fromCharCode(10));
    const fn = mutate[file];
    const out = fn ? fn(text) : text;
    // 🔴 C-93. THE GONE-ANCHOR GUARD MOVED IN WITH THE SIX. Every private loader carried it and
    //    this one did not, so folding them here without it would have quietly traded 「the
    //    mutant did nothing」 for 「caught」 -- the one failure a green sweep cannot show you.
    if (fn && out === text) throw new Error(`mutation anchor is GONE: ${file}`);
    sources[file] = out;
    return sources[file];
  };
  // 🔴 스타일시트도 «채점 대상»입니다. 오늘 화면을 깬 것은 자바스크립트가 아니라 CSS 한 줄
  //    (flex-wrap)이었고, 소스에 안 읽어 두면 그 부류는 변이도 단언도 못 겁니다.
  read('board.css');
  const storeUrl = moduleUrl(read('marking_store.js'));
  const apiUrl = moduleUrl(read('api.js'));
  const panelUrl = moduleUrl(read('panel.js')
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  const mapUrl = moduleUrl(read('map_panel.js')
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`)
    .replaceAll("'./api.js'", `'${apiUrl}'`)
    .replaceAll("'../map2/painter.js'", `'${srcUrl('map2/painter.js')}'`)
    .replaceAll("'../map2/seating.js'", `'${srcUrl('map2/seating.js')}'`));
  const shellUrl = moduleUrl(read('grid_shell.js'));
  const interUrl = moduleUrl(read('marking_intersection.js')
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  // Round 2's parts are imported by `main.js` too, so they have to be rewired here or the
  // composition root cannot load at all -- which is how it failed the moment they landed.
  const tableUrl = moduleUrl(read('table_part.js')
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  const partUrl = (file) => moduleUrl(read(file)
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`)
    .replaceAll("'./table_part.js'", `'${tableUrl}'`)
    .replaceAll("'./api.js'", `'${apiUrl}'`)
    // 🔴 C-70. `walk_box_panel.js` now takes its columns and its sectioning from the WALK
    //    PAGE's `derive.js`, so that specifier has to be rewired too. It is not under mutation
    //    here, so it points at the real file. Forgetting it is not one red assertion: the
    //    import throws before any check runs, and the runner reports 「it used to assert and
    //    now measures nothing」 — which is exactly how this landed on two harnesses at once.
    .replaceAll("'../walk/derive.js'", `'${srcUrl('walk/derive.js')}'`));
  const headUrl = partUrl('head_summary_panel.js');
  const compUrl = partUrl('composition_panel.js');
  const candUrl = partUrl('candidate_list_panel.js');
  const rankUrl = partUrl('rank_list_panel.js');
  const ctlUrl = partUrl('control_bar_panel.js');
  const trendUrl = partUrl('main_trend_panel.js');
  const statusUrl = partUrl('marking_status_panel.js');
  const declUrl = partUrl('declaration_panel.js');
  const mainUrl = moduleUrl(read('main.js')
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`)
    .replaceAll("'./grid_shell.js'", `'${shellUrl}'`)
    .replaceAll("'./marking_intersection.js'", `'${interUrl}'`)
    .replaceAll("'./map_panel.js'", `'${mapUrl}'`)
    .replaceAll("'./head_summary_panel.js'", `'${headUrl}'`)
    .replaceAll("'./composition_panel.js'", `'${compUrl}'`)
    .replaceAll("'./candidate_list_panel.js'", `'${candUrl}'`)
    .replaceAll("'./rank_list_panel.js'", `'${rankUrl}'`)
    .replaceAll("'./control_bar_panel.js'", `'${ctlUrl}'`)
    .replaceAll("'./main_trend_panel.js'", `'${trendUrl}'`)
    .replaceAll("'./marking_status_panel.js'", `'${statusUrl}'`)
    .replaceAll("'./declaration_panel.js'", `'${declUrl}'`)
    .replaceAll("'./expanded_layer_panel.js'", `'${partUrl('expanded_layer_panel.js')}'`)
    // 🔴 A PART THIS LIST FORGETS TAKES THE WHOLE HARNESS DOWN, not one assertion: the
    //    composition root's import throws ERR_INVALID_URL before a single check runs.
    //    Every part `main.js` imports has to be here.
    .replaceAll("'./reach_panel.js'", `'${partUrl('reach_panel.js')}'`)
    .replaceAll("'./walk_box_panel.js'", `'${partUrl('walk_box_panel.js')}'`)
    .replaceAll("'./api.js'", `'${apiUrl}'`));
  // 🔴 C-93 (판정 345). THE PARTS COME BACK BY NAME, because six harnesses used to build this
  //    same graph each in their own copy of three lines -- and the day `api.js` gained an import,
  //    the omission was in all seven at once. One loader, one place to forget nothing.
  // ⚠️ Every harness now pays for the whole board's load. That is the price of one loader, and
  //    it is small: `main.js` imports every part anyway, so nothing new is being evaluated.
  const [store, api, panel, map, shell, main, table, inter, derive,
    head, comp, cand, rank, control, trend, status, decl, layer, reach, box] =
    await Promise.all([
      import(storeUrl), import(apiUrl), import(panelUrl),
      import(mapUrl), import(shellUrl), import(mainUrl),
      import(tableUrl), import(interUrl), import(srcUrl('walk/derive.js')),
      import(headUrl), import(compUrl), import(candUrl), import(rankUrl),
      import(ctlUrl), import(trendUrl), import(statusUrl), import(declUrl),
      import(partUrl('expanded_layer_panel.js')),
      import(partUrl('reach_panel.js')), import(partUrl('walk_box_panel.js')),
    ]);
  return { store, api, panel, map, shell, main, sources,
    parts: { table, inter, derive, head, comp, cand, rank,
      control, trend, status, decl, layer, reach, box } };
}
