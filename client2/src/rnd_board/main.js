// ═══════════════════════════════════════════════════════════════════════════════
// THE COMPOSITION ROOT of the R&D board. The ONLY file that knows a URL, a lot number, or
// where a panel sits.
//
// 🔴 THE SCREEN IS A LIST OF INSTANCE DECLARATIONS (below). Each entry names the part, its
//    seat, the marking it READS, the marking it WRITES, and its question. Adding a chart is
//    one entry; moving one when drag lands is a change to `at`. No part is edited either way.
//
// 🔴 THE DECLARATION IS DATA -- no functions in it -- so it can be serialised the day a
//    layout is saved or dragged. `bindLoaders` is what turns a question into a fetch, and it
//    lives HERE so no part ever holds a route.
//
// 🔴 TWO MAPS, TWO DIFFERENT MARKING NAMES. That is the round's acceptance standing on the
//    real screen: the same class, twice, reading and writing different names, not interfering.
//
// ⚠️ WHY BOTH ARE THE BOND AXIS AND NOT THE MOCKUP'S 본딩/코어 PAIR. Measured 2026-08-23:
//    `/api/ledger/lot_map?row=SYN-VOID-001&slot=07` returns `core` and `dt` as
//    `state:"no_frame", reason:"frame_ambiguous_across_slots"` -- a slot narrows rows in the
//    ROW axis's family only, so the core axis stays spread over 25 frames and there is no one
//    lattice to draw it on. Seating a core panel here would put a refusal sentence where the
//    mockup shows a wafer. Two bond maps of two different wafers are the same test of the
//    contract and they both DRAW.
// ═══════════════════════════════════════════════════════════════════════════════

// 🔴 THE STYLESHEET IS LINKED BY THE PAGE, AND `config.js` IS IMPORTED ONLY IN THE BROWSER
// BRANCH (at the bottom, dynamically). This module has to stay importable under bare node so
// the harness can drive the real composition root -- and `config.js` reads `window.location`
// and `import.meta.env` at module top level, so a static import of it would kill that.
// `API_BASE` still has exactly one definition; this file just does not ask for it until there
// is a document to ask on behalf of.
import { MarkingStore } from './marking_store.js';
import { intersectMarkings } from './marking_intersection.js';
import { GridShell } from './grid_shell.js';
import { MapPanel } from './map_panel.js';
import { HeadSummaryPanel } from './head_summary_panel.js';
import { CompositionPanel } from './composition_panel.js';
import { CandidateListPanel } from './candidate_list_panel.js';
import { RankListPanel } from './rank_list_panel.js';
import { ControlBarPanel } from './control_bar_panel.js';
import { MainTrendPanel } from './main_trend_panel.js';
import { fetchLotMap } from './api.js';

/** part name -> class. The shell resolves a declaration through this and nothing else. */
export const PARTS = { map: MapPanel, headSummary: HeadSummaryPanel, composition: CompositionPanel,
  candidateList: CandidateListPanel, rankList: RankListPanel, controlBar: ControlBarPanel,
  mainTrend: MainTrendPanel };

/**
 * THE SCREEN. Six seats: the mockup 2a arrangement -- full-width bands on top, then the
 * three-column strip (map / candidates / rank) under them.
 *
 * 🔴 SEATING FOUR PARTS EDITED NO PART FILE. Everything a part needs to answer its question
 *    is DECLARED here (`finalChipId`, `seedNodeId`, `collect`) and the shell spreads it into
 *    the constructor. That is the owner's assembly rule standing on a real screen.
 *
 * ⚠️ TWO SUBJECTS, NOT ONE, AND THE SCREEN SAYS SO IN THE TITLES. Measured 2026-08-23:
 *    `composition?final_chip_id=` resolves for `SYN-CX-CHIP-001` and for nothing in the void
 *    family (`SYN-VOID-001`, `SYN-CHIP-001`, `SYN-BW-001-07` all answer
 *    `final_subject_resolution.state: "absent"`), while the walk answers 25 ranked candidates
 *    on the very wafer map A draws (`SYN-BW-001-07`). Seating one subject would have meant
 *    putting a refusal where the mockup shows content. The mockup's 제어 band -- not built --
 *    is what will bind them, and until it is the titles carry the subject.
 */
export const BOARD = Object.freeze({
  // 목업 2a: 전폭 단 둘이 위에, 그 아래 3열 띠 (맵 899 / 후보 508 / 순위 509).
  columns: 'minmax(0, 1.7fr) minmax(0, 1fr) minmax(0, 1fr)',
  // 목업 2a 의 세로 차례: 신원 · 제어 · 메인 트렌드 · 구성 · (맵 / 후보 / 순위).
  // 🔴 THE HEIGHTS ARE THE SCREEN'S, NOT A PART'S. The mockup is a page that SCROLLS -- fitting
  //    six bands into one viewport is what made every panel too short to read.
  // 🔴 `auto` COLLAPSED TO 2px HERE, MEASURED. Every panel carries `min-height: 0` (it must, or
  //    a part could push the grid open), so an auto row's minimum is ZERO -- and once the fixed
  //    rows below overflowed the viewport the identity band was squeezed to its borders while
  //    its content sat inside, invisible. A floor is what makes it survive the overflow.
  rows: 'minmax(92px, auto) minmax(44px, auto) 280px 220px 320px 320px',
  gap: '10px',
  // 🔴 DERIVED MARKINGS ARE DECLARED, NOT CODED. 「후보 map 의 마킹 활성 = 마킹 1 ∩ 마킹 2」
  //    (owner). A part reads `marking:3` by naming it in `reads`; nothing in a part, and
  //    nothing in this file, knows what 3 is made of except this line.
  //    ⚠️ NO PART READS `marking:3` YET -- the candidate map that wants it is not built. It is
  //    computed and standing so that seating that part is one string, and said out loud here
  //    rather than reported as finished wiring.
  intersections: [
    { sources: ['marking:1', 'marking:2'], target: 'marking:3' },
  ],
  panels: [
    {
      id: 'head-summary',
      part: 'headSummary',
      title: '머리 요약 · SYN-CX-CHIP-001',
      at: { column: 1, row: 1, columnSpan: 3 },
      reads: 'marking:1',
      writes: null,
      options: { finalChipId: 'SYN-CX-CHIP-001' },
    },
    {
      // 🔴 THE SCREEN'S GRAMMAR LIVES HERE (목업 ③). It writes the chosen axis into `axis:y`,
      //    which is a marking like any other -- see the part's header for why, and for what the
      //    Lead PM still has to rule on.
      id: 'control-bar',
      part: 'controlBar',
      title: '제어 · 축 선택',
      at: { column: 1, row: 2, columnSpan: 3 },
      reads: 'axis:y',
      writes: 'axis:y',
      options: {
        seedNodeId: 'ledger-entity:v1:WyJXYWZlciIseyJ3YWZlciI6IlNZTi1CVy0wMDEtMDcifV0',
        collect: 'quantity',
        window: '180d',
      },
    },
    {
      // 「점을 찍으면 그것이 씨앗이다」. The seed gets its OWN marking name -- the mockup calls it
      // 마킹 0 -- because a wafer picked in a trend and a die clicked on a map are different
      // kinds of thing and folding them into one name makes each panel's count a riddle.
      id: 'main-trend',
      part: 'mainTrend',
      title: '메인 트렌드',
      at: { column: 1, row: 3, columnSpan: 3 },
      reads: 'marking:0',
      writes: 'marking:0',
      options: { kinds: 'void', window: '180d' },
    },
    {
      id: 'composition',
      part: 'composition',
      title: '구성 · SYN-CX-CHIP-001',
      at: { column: 1, row: 4, columnSpan: 3 },
      reads: 'marking:1',
      writes: 'marking:1',
      options: { finalChipId: 'SYN-CX-CHIP-001' },
    },
    {
      id: 'map-bond-a',
      part: 'map',
      title: '본딩 맵 · 슬롯 07',
      at: { column: 1, row: 5 },
      reads: 'marking:1',
      writes: 'marking:1',
      options: {
        axis: 'bond',
        question: { row: 'SYN-VOID-001', slot: '07', kind: 'void' },
      },
    },
    {
      id: 'map-bond-b',
      part: 'map',
      title: '본딩 맵 · 슬롯 03',
      at: { column: 1, row: 6 },
      reads: 'marking:2',
      writes: 'marking:2',
      options: {
        axis: 'bond',
        question: { row: 'SYN-VOID-001', slot: '03', kind: 'void' },
      },
    },
    {
      // 🔴 후보 계열은 marking:2 -- 목업대로. 후보를 고르면 순위표의 같은 행이 같이 움직이고,
      //    그것이 「마킹은 부품 밖에 산다」가 화면에서 보이는 자리다.
      id: 'candidate-list',
      part: 'candidateList',
      title: '원인 후보 · SYN-BW-001-07',
      at: { column: 2, row: 5, rowSpan: 2 },
      reads: 'marking:2',
      writes: 'marking:2',
      options: {
        seedNodeId: 'ledger-entity:v1:WyJXYWZlciIseyJ3YWZlciI6IlNZTi1CVy0wMDEtMDcifV0',
        collect: 'quantity',
      },
    },
    {
      id: 'rank-list',
      part: 'rankList',
      title: '순위 · SYN-BW-001-07',
      at: { column: 3, row: 5, rowSpan: 2 },
      reads: 'marking:2',
      writes: 'marking:2',
      options: {
        seedNodeId: 'ledger-entity:v1:WyJXYWZlciIseyJ3YWZlciI6IlNZTi1CVy0wMDEtMDcifV0',
        collect: 'quantity',
      },
    },
  ],
});

/**
 * Question -> `load`. The one seam between a declared screen and the network: replacing a
 * mocked answer with a real route is a change here, never in a part.
 */
export function bindLoaders(layout, deps) {
  const { apiBase, fetchImpl, dpr } = deps || {};
  return {
    ...layout,
    panels: (layout.panels || []).map((decl) => {
      const options = decl.options || {};
      // 🔴 THE ADDRESS IS INJECTED, NEVER DECLARED. `apiBase` is a fact about where this page
      //    is running, so it is known HERE and nowhere in the layout data -- which is what
      //    keeps that data serialisable the day a screen is saved or dragged.
      const bound = { ...options, apiBase, fetchImpl, dpr: dpr || 1 };
      if (!options.question) return { ...decl, options: bound };
      return {
        ...decl,
        options: {
          ...bound,
          load: () => fetchLotMap({ apiBase, fetchImpl, ...options.question }),
        },
      };
    }),
  };
}

/** Boot the board into `host`. Returns the shell, so a caller can reseat or tear down. */
export function boot(doc, host, deps) {
  const options = deps || {};
  const markings = options.markings || new MarkingStore();
  const shell = new GridShell(host, {
    doc,
    markings,
    parts: options.parts || PARTS,
    observeSize: options.observeSize,
  });
  const layout = options.layout || BOARD;
  shell.render(bindLoaders(layout, {
    apiBase: options.apiBase || '',
    fetchImpl: options.fetchImpl,
    dpr: options.dpr || 1,
  }));
  // Installed AFTER the seats, so a part that reads a derived name gets its first value from
  // the same first computation as everyone else.
  shell.intersections = (layout.intersections || []).map((spec) => intersectMarkings(markings, spec));
  return shell;
}

if (typeof document !== 'undefined') {
  const host = document.getElementById('rb-board');
  if (host) {
    import('../config.js').then(({ API_BASE }) => {
      boot(document, host, {
        apiBase: API_BASE,
        dpr: (typeof window !== 'undefined' && window.devicePixelRatio) || 1,
      });
    });
  }
}
