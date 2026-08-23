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
import { MarkingStatusPanel } from './marking_status_panel.js';
import { DeclarationPanel } from './declaration_panel.js';
import { fetchTrends, trendsModel, fetchSubgraph, subgraphModel,
  createWalk,
  fetchLotMap, fetchComposition, basisCountsFromComposition,
  slotPagesFromLotMap, fetchSiblings, peerCountFromSiblings,
  waferFactsFromLotMap } from './api.js';

/** part name -> class. The shell resolves a declaration through this and nothing else. */
export const PARTS = { map: MapPanel, headSummary: HeadSummaryPanel, composition: CompositionPanel,
  candidateList: CandidateListPanel, rankList: RankListPanel, controlBar: ControlBarPanel,
  mainTrend: MainTrendPanel, markingStatus: MarkingStatusPanel,
  declaration: DeclarationPanel };

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
  // 🔴 목업의 아래 띠는 «가로»입니다 — 본딩 맵 | 코어 맵 | 후보 | 순위 가 나란히. 우리가 맵을
  //    세로로 쌓아 두어서 「한눈에 보이는 차이」가 났습니다 (소유자 지적).
  columns: 'minmax(0, 1.15fr) minmax(0, 1.15fr) minmax(0, 1fr) minmax(0, 1fr)',
  // 목업 2a 의 세로 차례: 신원 · 제어 · 메인 트렌드 · 구성 · (맵 / 후보 / 순위).
  // 🔴 THE HEIGHTS ARE THE SCREEN'S, NOT A PART'S. The mockup is a page that SCROLLS -- fitting
  //    six bands into one viewport is what made every panel too short to read.
  // 🔴 `auto` COLLAPSED TO 2px HERE, MEASURED. Every panel carries `min-height: 0` (it must, or
  //    a part could push the grid open), so an auto row's minimum is ZERO -- and once the fixed
  //    rows below overflowed the viewport the identity band was squeezed to its borders while
  //    its content sat inside, invisible. A floor is what makes it survive the overflow.
  // ⚠️ THE TREND'S BAND IS SMALLER THAN THE MOCKUP'S ON PURPOSE, TODAY. Its data has no
  //    spread (every rate 0.0 at one timestamp), so a 280px band was 240px of empty air at
  //    the top of the screen -- the least mockup-like thing on it. The height goes to the
  //    layer table, which has ten rows to show. When the trend gets a spread this is one
  //    number here, and no part changes.
  //    ⚠️ 92px WAS THE FLOOR UNTIL THE WAFER LINE LANDED: measured content 112px in a 92px
  //       row, so the new line was clipped. An `auto` row cannot grow here -- the fixed rows
  //       below already overflow the viewport, so auto sinks to its own minimum.
  rows: 'minmax(118px, auto) minmax(44px, auto) 190px 360px 340px',
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
      // walk ④ — 「이 주어가 무엇으로 만들어졌나」. groupby 는 값이지 축이 아닙니다.
      start: { groupby: 'chip', value: 'SYN-CX-CHIP-001' },
      collect: 'wafer_process',
      options: {
        finalChipId: 'SYN-CX-CHIP-001',
        // 🔴 판정 (총괄 06:3x): 주어는 «칩»이고 웨이퍼는 «옆에» 붙습니다. 목업 ① 이 주는 정보를
        //    가져오되 주어를 바꾸지 않습니다 -- 구성·후보·순위가 그 칩의 층에서 나오기 때문에
        //    주어를 웨이퍼로 옮기면 인과 패널 절반이 설 자리를 잃습니다.
        waferQuestion: { row: 'SYN-VOID-001', slot: '07' },
        waferKinds: ['void', 'delam'],
        subjectReads: 'subject:wafer',
      },
    },
    {
      // 스팟파이어의 상태바. 「N marked」 가 «항상» 보여야 한다는 게 계약입니다 -- 마킹이 비어
      // 있다는 사실이 곧 마킹으로 거르는 패널이 빈 이유이기 때문입니다.
      id: 'marking-status',
      part: 'markingStatus',
      title: '마킹',
      at: { column: 4, row: 1 },
      reads: null,
      writes: null,
      options: {
        names: [
          { name: 'marking:0', label: '씨앗 · 마킹 0' },
          { name: 'marking:1', label: '맵 · 마킹 1' },
          { name: 'marking:2', label: '후보 · 마킹 2' },
          { name: 'marking:3', label: '교집합 · 마킹 3' },
        ],
      },
    },
    {
      // 🔴 THE SCREEN'S GRAMMAR LIVES HERE (목업 ③). It writes the chosen axis into `axis:y`,
      //    which is a marking like any other -- see the part's header for why, and for what the
      //    Lead PM still has to rule on.
      id: 'control-bar',
      part: 'controlBar',
      title: '제어 · 축 선택',
      at: { column: 1, row: 2, columnSpan: 4 },
      reads: 'axis:y',
      writes: 'axis:y',
      collect: 'trend_y',
      options: {
        seedNodeId: 'ledger-entity:v1:WyJXYWZlciIseyJ3YWZlciI6IlNZTi1CVy0wMDEtMDcifV0',
        window: '180d',
        // 🔴 THE SCREEN PICKS WHICH LOT AND WHICH EQUIPMENT IT MEANS. The route answers several
        //    axes; choosing is a declaration, not a derivation. `7d` has no scope -- it is a
        //    window, not a peer axis -- so it stays 「—」 until it is given one.
        peers: [
          { label: '같은 레그', scope: 'leg:HBM-B_LOW-P' },
          { label: '같은 랏', scope: 'bond_lot:SYN-K1-201' },
          { label: '레시피', scope: 'scan_recipe:SYN_VOID_R1' },
          { label: '설비', scope: 'bond_eqp:SYN-BD-02' },
          { label: '7d', scope: null },
        ],
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
      // walk ① — start 없음: 「each groupby」, 즉 창 안의 모든 웨이퍼입니다.
      collect: 'trend_y',
      options: {
        kinds: 'void',
        window: '180d',
        // 🔴 THE CONTROL BAR'S CHOICE REACHES THIS CHART. It was a dead control until now: the
        //    pill turned blue and nothing moved. The name is declared, so a second trend can
        //    follow a different chooser without either part changing.
        axisReads: 'axis:y',
        // 찍은 점의 웨이퍼를 «이름»으로 남깁니다 -- 맵이 그것을 따라갑니다.
        writesSubject: 'subject:wafer',
        // 지금 화면이 보고 있는 웨이퍼의 점을 «표시»합니다 (마킹과는 별개).
        subjectReads: 'subject:wafer',
        // 🔴 THE GRAIN IS DECLARED, AND IT IS WHY THE POINTS HAVE VALUES. Handed over measured:
        //    the server's default aggregates `Wafer` and reads the leg out of `object_payload`,
        //    which returns 24 points all at 0.0 -- twelve findings drawn as none. Two fields
        //    differ from the default: `subject_type` and `axes[1].numerator.from`.
        grain: {
          subject_type: 'WaferLeg',
          identity_fields: ['wafer'],
          aggregation_unit: 'void_by_experiment_unit',
          context_fields: ['bonding_leg'],
          context_role: 'planned_bonding_experiment_unit',
          marking: 'identity.mark_key',
          axes: [
            { name: 'wafer',
              denominator: { relation: 'inspection_run', column: 'base_wafer_id' },
              numerator: { from: 'subject_keys', key: 'wafer' } },
            { name: 'bonding_leg',
              denominator: { relation: 'bonding_map', column: 'leg' },
              numerator: { from: 'subject_keys', key: 'bonding_leg' } },
          ],
        },
      },
    },
    {
      // 스팟파이어가 차트마다 오른쪽에 다는 선언 블록. 필드는 «선언»이고, 고르는 것은 마킹에
      // 씁니다 -- 트렌드는 이 패널이 있는지도 모릅니다.
      id: 'trend-declaration',
      part: 'declaration',
      title: '축',
      at: { column: 4, row: 3 },
      reads: null,
      writes: null,
      options: {
        fields: [
          { label: 'Data table', text: 'trends' },
          { label: 'Y value', writes: 'axis:y', options: 'y' },
          { label: 'Group by', writes: 'axis:group', options: 'group' },
          { label: 'Color by', text: '(None)' },
          { label: 'Shape by', text: '(None)' },
          { label: 'Marking', reads: 'marking:0' },
          { label: 'Data limiting', text: '(None)' },
        ],
      },
    },
    {
      id: 'composition',
      part: 'composition',
      start: { groupby: 'chip', value: 'SYN-CX-CHIP-001' },
      collect: 'wafer_process',
      title: '구성 · SYN-CX-CHIP-001',
      at: { column: 1, row: 4, columnSpan: 4 },
      reads: 'marking:1',
      writes: 'marking:1',
      options: { finalChipId: 'SYN-CX-CHIP-001' },
    },
    {
      id: 'map-bond-a',
      part: 'map',
      collect: 'map',
      title: '본딩 맵 · 슬롯 07',
      at: { column: 1, row: 5 },
      reads: 'marking:1',
      writes: 'marking:1',
      options: {
        axis: 'bond',
        // 목업 맵 하단의 기반 선택자. `type` is the node type the count comes from.
        bases: [
          { axis: 'bond', label: 'bond_layer', type: 'bond_layer' },
          { axis: 'dt', label: 'dt_slot', type: 'dt_slot' },
          { axis: 'core', label: 'wafer_grid', type: 'wafer_grid' },
        ],
        basisChipId: 'SYN-CX-CHIP-001',
        // 트렌드에서 찍은 웨이퍼로 이 맵이 «옮겨 갑니다».
        pageFollows: 'subject:wafer',
        question: { row: 'SYN-VOID-001', slot: '07', kind: 'void' },
      },
    },
    {
      // 🔴 목업의 둘째 맵은 «코어 맵»입니다 (마킹 2 · 후보가 걸린 점). 우리는 본딩 맵을 한 장
      //    더 놓고 있었습니다. 부품은 그대로이고 «기반»과 «읽는 마킹»만 다릅니다 -- 조립식
      //    규칙이 성립한다는 증거이기도 합니다.
      id: 'map-core',
      part: 'map',
      collect: 'map',
      title: '코어 맵 · 마킹 2',
      at: { column: 2, row: 5 },
      reads: 'marking:2',
      writes: 'marking:2',
      options: {
        axis: 'core',
        bases: [
          { axis: 'bond', label: 'bond_layer', type: 'bond_layer' },
          { axis: 'dt', label: 'dt_slot', type: 'dt_slot' },
          { axis: 'core', label: 'wafer_grid', type: 'wafer_grid' },
        ],
        basisChipId: 'SYN-CX-CHIP-001',
        // 트렌드에서 찍은 웨이퍼로 이 맵이 «옮겨 갑니다».
        pageFollows: 'subject:wafer',
        question: { row: 'SYN-VOID-001', slot: '07', kind: 'void' },
      },
    },
    {
      // 🔴 후보 계열은 marking:2 -- 목업대로. 후보를 고르면 순위표의 같은 행이 같이 움직이고,
      //    그것이 「마킹은 부품 밖에 산다」가 화면에서 보이는 자리다.
      id: 'candidate-list',
      part: 'candidateList',
      start: { groupby: 'wafer', value: 'ledger-entity:v1:WyJXYWZlciIseyJ3YWZlciI6IlNZTi1CVy0wMDEtMDcifV0' },
      collect: 'candidate',
      title: '원인 후보 · SYN-BW-001-07',
      at: { column: 3, row: 5 },
      reads: 'marking:2',
      writes: 'marking:2',
      options: {
        seedNodeId: 'ledger-entity:v1:WyJXYWZlciIseyJ3YWZlciI6IlNZTi1CVy0wMDEtMDcifV0',
      },
    },
    {
      id: 'rank-list',
      part: 'rankList',
      start: { groupby: 'wafer', value: 'ledger-entity:v1:WyJXYWZlciIseyJ3YWZlciI6IlNZTi1CVy0wMDEtMDcifV0' },
      collect: 'candidate',
      title: '순위 · SYN-BW-001-07',
      at: { column: 4, row: 5 },
      reads: 'marking:2',
      writes: 'marking:2',
      options: {
        seedNodeId: 'ledger-entity:v1:WyJXYWZlciIseyJ3YWZlciI6IlNZTi1CVy0wMDEtMDcifV0',
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
  // 🔴 ONE WALK FOR THE WHOLE SCREEN, and that is not a performance note: 후보 트렌드와 후보
  //    맵은 «같은 walk»(⑦)을 먹습니다. 인스턴스가 하나여야 둘째 부품이 첫째의 진행 중인 요청에
  //    «합류»합니다 -- 인스턴스를 부품마다 만들면 같은 질문을 두 번 보내게 됩니다.
  const walk = createWalk({ apiBase, fetchImpl });
  return {
    ...layout,
    panels: (layout.panels || []).map((decl) => {
      const options = decl.options || {};
      // 🔴 THE ADDRESS IS INJECTED, NEVER DECLARED. `apiBase` is a fact about where this page
      //    is running, so it is known HERE and nowhere in the layout data -- which is what
      //    keeps that data serialisable the day a screen is saved or dragged.
      const bound = { ...options, walk, apiBase, fetchImpl, dpr: dpr || 1 };
      // The basis counts come from ANOTHER route, so the seam is here and the part stays
      // route-free: it is handed a function that answers 「타입별 몇 개인가」 and nothing else.
      if (options.fields) {
        // 🔴 THE LISTS ARE FETCHED HERE, NOT IN THE PART. `y` is the ratio axes this route can
        //    plot plus the walk's measured quantities; `group` is the peer scopes the screen
        //    declared. The part receives `[{id, label}]` and knows nothing else.
        bound.optionsFor = (key) => {
          if (key === 'y') {
            return Promise.all([
              walk({ collect: 'trend_y', window: '180d' }),
              walk({
                start: { groupby: 'wafer',
                  value: 'ledger-entity:v1:WyJXYWZlciIseyJ3YWZlciI6IlNZTi1CVy0wMDEtMDcifV0' },
                collect: 'candidate',
              }),
            ]).then(([trends, candidates]) => {
              const out = (trends.kinds || []).map((k) => ({
                id: `axis:ratio:${k.id}`, label: `${k.label} 비율`,
              }));
              for (const c of (candidates.ok ? candidates.candidates : []) || []) {
                if (!c.measured) continue;
                out.push({ id: `axis:quantity:${c.id || c.quantity}`,
                  label: `${c.quantity}${c.model ? ` · ${c.model}` : ''}` });
              }
              return out;
            });
          }
          if (key === 'group') {
            return Promise.resolve([
              { id: 'peer:leg', label: '같은 레그' },
              { id: 'peer:lot', label: '같은 랏' },
              { id: 'peer:recipe', label: '레시피' },
              { id: 'peer:eqp', label: '설비' },
            ]);
          }
          return Promise.resolve([]);
        };
      }
      if (options.waferQuestion) {
        // One call per kind, because the route answers one kind at a time. A kind that has not
        // answered yet stays BLANK on screen -- never 0.
        // A wafer given means the screen moved: same route, wafer axis (the one that answers
        // for a wafer picked out of a trend rather than a slot of a lot).
        bound.loadWaferFacts = (kind, wafer) => walk(wafer
          ? { start: { groupby: 'wafer', value: wafer }, collect: 'map', kind }
          : { collect: 'map', ...options.waferQuestion, kind })
          .then((body) => waferFactsFromLotMap(body, 'bond'));
      }
      if (options.peers) {
        bound.loadPeerCount = (scope) => walk({
          start: { groupby: 'scope', value: scope }, collect: 'peer', window: options.window,
        });
      }
      if (options.basisChipId) {
        bound.loadBasisCounts = () => walk({
          start: { groupby: 'chip', value: options.basisChipId }, collect: 'basis',
        });
      }
      if (!options.question) return { ...decl, options: bound };
      return {
        ...decl,
        options: {
          ...bound,
          // The override is how a part turns a page without learning a route: it hands back
          // the one field it is changing and the question stays the composition root's.
          load: (override) => walk({
            collect: 'map', ...options.question, ...(override || {}),
          }),
          // 씨앗으로 찍힌 웨이퍼를 그리는 길. 같은 라우트, 축만 웨이퍼.
          loadByWafer: (wafer) => walk({
            start: { groupby: 'wafer', value: wafer },
            collect: 'map', ...options.question, slot: undefined,
          }),
          // 목업의 페이지 목록. Measured: a slot-less call carries the row's whole slot list.
          loadPages: () => walk({
            collect: 'map', ...options.question, slot: undefined,
          }).then(slotPagesFromLotMap),
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
