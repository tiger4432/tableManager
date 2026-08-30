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
import { ExpandedLayerPanel } from './expanded_layer_panel.js';
import { ReachPanel } from './reach_panel.js';
import { WalkBoxPanel } from './walk_box_panel.js';
import { fetchTrends, trendsModel, fetchSubgraph, subgraphModel,
  createWalk,
  fetchLotMap, fetchComposition, basisCountsFromComposition,
  slotPagesFromLotMap, fetchSiblings, peerCountFromSiblings,
  waferFactsFromLotMap,
  fetchDeclaration, createWalkBoxWalk, fetchMapGrid, entitySeedId, compositionFromWalk, waferFactsFromWalk, peerCountFromWalk, trendFromWalk } from './api.js';

/**
 * part name -> class. The shell resolves a declaration through this and nothing else.
 *
 * 🔴 ADDING A PART HERE? ADD IT TO `tests/rnd_board_harness.mjs`'s REWRITE LIST TOO.
 *    That harness carries this file as a `data:` URL and rewrites every relative import; a part
 *    it does not know throws `Failed to resolve module specifier` and takes the WHOLE harness
 *    down -- not one assertion. The warning used to live only beside that list, which is read
 *    by people who already know. This is the line a person adding a part actually walks past.
 *
 * 🔴 AND JUDGE THE BUILD BY THE `dist` HASH, NEVER BY THE EXIT CODE. When that happens,
 *    `npm run build` still reports exit 0 -- prebuild fails, vite never runs, and dist keeps
 *    its previous hash. Measured twice on 2026-08-26/27, once by the Lead PM and once by a run
 *    that executed in the wrong directory.
 */
export const PARTS = { map: MapPanel, headSummary: HeadSummaryPanel, composition: CompositionPanel,
  candidateList: CandidateListPanel, rankList: RankListPanel, controlBar: ControlBarPanel,
  mainTrend: MainTrendPanel, markingStatus: MarkingStatusPanel,
  declaration: DeclarationPanel, expandedLayer: ExpandedLayerPanel, reach: ReachPanel,
  walkBox: WalkBoxPanel };

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
// 🔴 이 파일의 씨앗 여섯 줄은 «픽스처 기본값»이지 계약이 아닙니다 (총괄 판정 2026-08-24).
//    웨이퍼 SYN-CX-BW-001 과 칩 SYN-CX-CHIP-001 은 «같은 물리 대상»입니다 -- 그 칩이 그
//    웨이퍼에 앉아 있고, 그래서 한 화면에 주어가 하나입니다. 라우트가 서로 다른 id 를 받을 뿐입니다.
//    ⚠️ 다음 항목이 `start { marking: 'marking:1' }` 이고, 마킹이 시작점을 몰고 오는 날
//       이 줄들은 «사라집니다». 계약으로 읽지 마십시오.
// ═══════════════════════════════════════════════════════════════════════════════
// 후보 질문 «하나». 세 자리가 이것을 씁니다 -- 컨트롤 바 · Y축 목록 · 후보/순위 표.
//
// 🔴 세 자리가 같은 질문을 «각자» 적고 있었습니다: 씨앗도 collect 도 셋 다 같은데
//    (["wafer",{"wafer":"SYN-CX-BW-001"}] · quantity) direction 과 node_limit 만 달라서
//    한 화면이 같은 답을 «세 번» 길었습니다. 총괄 판정 2026-08-25: 선언 하나를 나눠 쓴다.
//
// 🔴 «통째로» 씁니다 -- 칸을 골라 베끼지 않습니다. walk 의 합침 열쇠가
//    `JSON.stringify([collect, start, rest])` 라 «키 순서»에 민감해서, 같은 두 칸을 다른
//    순서로 적으면 같은 질문이 다른 열쇠가 되고 합쳐지지 않습니다. 한 객체를 펼치면
//    순서가 «정의상» 같습니다.
//
// direction  계보를 나가는 쪽으로만 (총괄 실측 2026-08-24): 형제 웨이퍼 74장이 빠지고
//            답은 그대로 (wafer 104 → 30 · 3,490 → 241 노드 · 1,757 → 210ms).
//            follow 는 «없습니다» -- 좁히면 processed_with/transferred 로만 닿는 delam
//            후보 넷을 영영 못 봅니다. 여기서 follow 는 속도가 아니라 «답의 존재 범위».
// node_limit 이 걷기의 «예산» (총괄 실측 2026-08-24): 기본 400 이면 nodes·claims 가 끊겨
//            ranked 가 0 이고, 1000 이면 후보 21 이 나옵니다. 구성이 스텝 267개를 물고
//            옵니다. 컨트롤이 아니라 «선언»입니다 -- 버튼도 자동 재시도도 없습니다.
// ═══════════════════════════════════════════════════════════════════════════════
const CANDIDATE_QUESTION = { collect: 'candidate', direction: 'outgoing', node_limit: 1000 };

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
  // 7행은 「닿는 곳」의 자리입니다. 앞 여섯 행은 목업의 띠이고 이건 그 «아래»에 붙습니다 --
  // 목업에 없는 부품이라 목업의 배치를 밀어내지 않는 것이 맞습니다.
  rows: 'minmax(118px, auto) minmax(44px, auto) 190px 190px 360px 340px 240px',
  gap: '10px',
  // 🔴 마킹은 «둘»입니다 (소유자 도식 · MARKING_CONTRACT §3). 트렌드에서 찍은 것이 마킹 1 이고
  //    그것이 후보·자재정보·맵 «셋»의 시작점입니다. 후보에서 찍은 것이 마킹 2 입니다.
  //    `marking:0` 과 `marking:3` 은 «은퇴»했습니다 -- 0 은 1 과 같은 것을 다른 이름으로
  //    부르고 있었고(그래서 트렌드와 맵이 «안 이어져» 있었습니다), 3 은 읽는 부품이 0개인
  //    파생이었습니다. 교집합이 필요해지면 읽는 자리에서 계산합니다.
  intersections: [],
  panels: [
    {
      id: 'head-summary',
      part: 'headSummary',
      // 🔴 제목에 씨앗을 박지 않습니다. 이 패널은 marking:1 을 «따라가는데» 제목만 선언된
      //    문자열이라, 총괄이 클릭 뒤에 「머리가 안 따라온다」로 읽었습니다 -- 몸통은
      //    「씨앗 웨이퍼 …」로 바뀌고 있었고 «제목만» 옛 이름이었습니다.
      title: '머리 요약',
      at: { column: 1, row: 1, columnSpan: 3 },
      reads: 'marking:1',
      writes: null,
      // walk ④ — 「이 주어가 무엇으로 만들어졌나」. groupby 는 값이지 축이 아닙니다.
      // 🔴 씨앗이 «칩»에서 «마킹»으로 (round Z-3, 2026-08-28). 그 칩 id 는 원장에 «0건»이라
      //    좌석이 통째로 404 였습니다. 구성은 `bonded_from` 이 이미 답합니다 -- base die 에서
      //    core die 로 가는 그 엣지이고, 소유자 말대로 pkg 는 (base, x, y) 그 자체입니다.
      //    ⚠️ 다이를 여기 «박지 않습니다»: 손으로 만든 die 씨앗은 JSON 이 1.0 을 못 써서
      //    조용히 «덜» 답합니다 (실측 4a540a50). 마킹의 id 는 walk 이 «만든» 것이라 그 문제가 없습니다.
      start: { groupby: 'die', marking: 'marking:1' },
      follow: ['bonded_from'],
      // 자재를 «두 대 위»까지 따라갑니다 -- 이 좌석의 질문이 「이 다이가 무엇으로
      //    만들어졌나」이고, 코어가 또 다른 코어 위에 앉는 적층을 한 겹 보기 위해서입니다.
      //    관측 예산과 «따로» 쓰이므로 결함 쪽을 굶기지 않습니다.
      backbone_hops: 2,
      // 🔴 방향을 «선언»합니다 (라운드 ⓪, 2026-08-29). 서버 기본 `both` 는 이 씨앗에서
      //    «남의 웨이퍼»로 새고 그 예산으로 절단이 납니다 -- 실측은 보고서의 표에.
      //    일괄로 바꾼 것이 «아닙니다»: 부품마다 두 방향을 각각 걸어 네 수를 비교했습니다.
      direction: 'outgoing',
      options: {
        finalChipId: 'SYN-CX-CHIP-001',
        // 🔴 판정 (총괄 06:3x): 주어는 «칩»이고 웨이퍼는 «옆에» 붙습니다. 목업 ① 이 주는 정보를
        //    가져오되 주어를 바꾸지 않습니다 -- 구성·후보·순위가 그 칩의 층에서 나오기 때문에
        //    주어를 웨이퍼로 옮기면 인과 패널 절반이 설 자리를 잃습니다.
        waferQuestion: { row: 'SYN-CX-BW-001', by: 'wafer' },
        waferKinds: ['void', 'delam'],
        // 목업이 머리에 다는 「마킹 1 · N행」 · 「마킹 2 · N행」. 이름은 여기서만 압니다.
        markingRows: ['marking:1', 'marking:2'],
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
          { name: 'marking:1', label: '씨앗 · 마킹 1' },
          { name: 'marking:2', label: '후보 · 마킹 2' },
        ],
      },
    },
    {
      // 🔴 THE SCREEN'S GRAMMAR LIVES HERE (목업 ③). It writes the chosen axis into `axis:y`,
      //    which is a marking like any other -- see the part's header for why, and for what the
      //    Lead PM still has to rule on.
      id: 'control-bar',
      // 🔴 방향을 «선언»합니다 (라운드 ⓪ 보완, 2026-08-29). 이 좌석의 걷기는 선언 목록이
      //    아니라 «부품 배선» 안(`optionsFor('y')`)에 있어서 1차에서 안 잡혔습니다 --
      //    실측 표를 좌석 «선언»으로만 만들었고, 화면 요청으로 대조하지 않은 제 잘못입니다.
      //    실측: both 400노드·절단 nodes,claims  ->  outgoing 251노드·절단 «없음».
      //    Y축 «종류 목록»을 만드는 자리라, 잘린 표본에서 고르면 「그런 종류가 없다」로
      //    보입니다. 오늘은 종류가 하나뿐이라 목록이 같지만, 둘째가 오는 날 갈립니다.
      direction: 'outgoing',
      part: 'controlBar',
      title: '제어 · 축 선택',
      at: { column: 1, row: 2, columnSpan: 4 },
      reads: 'axis:y',
      writes: 'axis:y',
      // 🔴 `collect: 'trend_y'` 가 «떠났습니다» (라운드 ①-a, 2026-08-29). 이 한 줄이 화면에
      //    남은 마지막 `/trends` 호출이었고, 그것이 Y축 «종류» 목록의 출처였습니다. 축이
      //    「집계 × 수식어」가 되면서 목록은 «선언»에서 오고, 그래서 이 좌석은 이제 라우트를
      //    한 개도 이름 대지 않습니다.
      options: {
        seedNodeId: 'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0',
        // 🔴 「수치인가」의 «주어». 목록(선언)과 달리 이것은 데이터라 마킹이 필요하고,
        //    비면 재지 않고 그 사실을 문장으로 말합니다 -- 「값 없음」이 아닙니다.
        numericReads: 'marking:1',
        window: '180d',
        // 🔴 이 부품은 후보를 «자기가» 걷습니다. 그러니 질문도 자기가 받아야 합니다 --
        //    안 주면 맨몸으로 걸어 나가 같은 답을 «네 번째»로 긷습니다 (총괄 실측).
        candidateQuestion: CANDIDATE_QUESTION,
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
      // 🔴 트렌드에서 찍은 점이 «마킹 1» 입니다. 이 한 줄이 없어서 맵이 트렌드를 «안 따라왔습니다».
      reads: 'marking:1',
      writes: 'marking:1',
      // walk ① — 씨앗은 «마킹»입니다. 「창 안의 모든 웨이퍼」였던 자리이고, 소유자가
      //    ⓐ 로 판정하면서 «마킹이 모집단»이 됐습니다. 하나 찍으면 하나, 여럿이면 여럿.
      start: { groupby: 'wafer', marking: 'marking:1' },
      // 🔴 모집단은 «마킹»입니다 (소유자 판정 2026-08-28 「a지」). 좌석이 씨앗 없는 날짜
      //    창을 묻지 않습니다 -- 그건 walk 의 모양이 아니라 라우트를 다시 파는 것입니다.
      //    시간축은 이미 응답 안에 있습니다: 실측으로 626 엣지 «전부» occurred_at 을 답니다.
      follow: ['inspected', 'observed', 'of_kind'],
      // 🔴 방향을 «선언»합니다 (라운드 ⓪, 2026-08-29). 서버 기본 `both` 는 이 씨앗에서
      //    «남의 웨이퍼»로 새고 그 예산으로 절단이 납니다 -- 실측은 보고서의 표에.
      //    일괄로 바꾼 것이 «아닙니다»: 부품마다 두 방향을 각각 걸어 네 수를 비교했습니다.
      direction: 'outgoing',
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
      // 🔴 방향을 «선언»합니다 (라운드 ⓪ 보완, 2026-08-29). 이 좌석은 그리는 것이 «선언»이라
      //    walk 을 안 하는 줄 알았는데, `fields` 가 있어서 `optionsFor('y')` 가 «여기» 묶입니다 --
      //    Y축 종류 목록을 만드는 걷기입니다. 좌석에 선언이 하나도 없어 `walkHere` 가 맨 `walk`
      //    이었고, 그래서 서버 기본 both 로 나갔습니다.
      //    실측: both 400노드·절단 nodes,claims  ->  outgoing 251노드·절단 «없음».
      //    ⚠️ 1차에서 못 잡은 이유: 표를 «좌석 선언»으로만 만들고 화면 요청과 대조하지
      //    않았습니다. 이 자리는 선언에 follow 도 direction 도 없어서 목록에 안 떴습니다.
      direction: 'outgoing',
      part: 'declaration',
      title: '축',
      at: { column: 4, row: 3 },
      reads: null,
      writes: null,
      options: {
        fields: [
          { label: 'Data table', text: 'trends' },
          { label: 'Y value', writes: 'axis:y', options: 'y' },
          // 목업의 X value. 지금 트렌드의 x 는 «계측 시각»이고 가로 눈금이 자재입니다 --
          // 고를 수 있는 목록이 아직 없어서 «지금 무엇인지»를 말합니다. 지어내지 않습니다.
          { label: 'X value', text: '계측 시각 · 가로 눈금은 자재' },
          { label: 'Group by', writes: 'axis:group', options: 'group' },
          { label: 'Color by', text: '(None)' },
          { label: 'Shape by', text: '(None)' },
          { label: 'Marking', reads: 'marking:1' },
          { label: 'Data limiting', text: '(None)' },
        ],
      },
    },
    {
      // 🔴 목업 ① — 「마킹한 후보 트렌드 (마킹 2)」. 부품은 «메인 트렌드와 같은 것»이고 바뀌는
      //    것은 선언뿐입니다: 시작점이 마킹 2 이고, 읽는 마킹도 2 입니다. 새 부품을 만들면
      //    조립식이라는 말이 거짓이 됩니다.
      id: 'candidate-trend',
      part: 'mainTrend',
      title: '마킹한 후보 트렌드 · 마킹 2',
      at: { column: 1, row: 4, columnSpan: 3 },
      reads: 'marking:2',
      writes: 'marking:2',
      // walk ⑦ — 후보에서 찍은 것이 이 차트의 «주어»입니다. 비어 있으면 묻지 않습니다.
      start: { groupby: 'wafer', marking: 'marking:2' },
      // 🔴 모집단은 «마킹»입니다 (소유자 판정 2026-08-28 「a지」). 좌석이 씨앗 없는 날짜
      //    창을 묻지 않습니다 -- 그건 walk 의 모양이 아니라 라우트를 다시 파는 것입니다.
      //    시간축은 이미 응답 안에 있습니다: 실측으로 626 엣지 «전부» occurred_at 을 답니다.
      follow: ['inspected', 'observed', 'of_kind'],
      // 🔴 방향을 «선언»합니다 (라운드 ⓪, 2026-08-29). 서버 기본 `both` 는 이 씨앗에서
      //    «남의 웨이퍼»로 새고 그 예산으로 절단이 납니다 -- 실측은 보고서의 표에.
      //    일괄로 바꾼 것이 «아닙니다»: 부품마다 두 방향을 각각 걸어 네 수를 비교했습니다.
      direction: 'outgoing',
      options: {
        kinds: 'void',
        window: '180d',
        axisReads: 'axis:y',
        subjectReads: 'subject:wafer',
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
      id: 'composition',
      part: 'composition',
      // 🔴 씨앗이 «칩»에서 «마킹»으로 (round Z-3, 2026-08-28). 그 칩 id 는 원장에 «0건»이라
      //    좌석이 통째로 404 였습니다. 구성은 `bonded_from` 이 이미 답합니다 -- base die 에서
      //    core die 로 가는 그 엣지이고, 소유자 말대로 pkg 는 (base, x, y) 그 자체입니다.
      //    ⚠️ 다이를 여기 «박지 않습니다»: 손으로 만든 die 씨앗은 JSON 이 1.0 을 못 써서
      //    조용히 «덜» 답합니다 (실측 4a540a50). 마킹의 id 는 walk 이 «만든» 것이라 그 문제가 없습니다.
      start: { groupby: 'die', marking: 'marking:1' },
      follow: ['bonded_from'],
      // 자재를 «두 대 위»까지 따라갑니다 -- 이 좌석의 질문이 「이 다이가 무엇으로
      //    만들어졌나」이고, 코어가 또 다른 코어 위에 앉는 적층을 한 겹 보기 위해서입니다.
      //    관측 예산과 «따로» 쓰이므로 결함 쪽을 굶기지 않습니다.
      backbone_hops: 2,
      // 🔴 방향을 «선언»합니다 (라운드 ⓪, 2026-08-29). 서버 기본 `both` 는 이 씨앗에서
      //    «남의 웨이퍼»로 새고 그 예산으로 절단이 납니다 -- 실측은 보고서의 표에.
      //    일괄로 바꾼 것이 «아닙니다»: 부품마다 두 방향을 각각 걸어 네 수를 비교했습니다.
      direction: 'outgoing',
      title: '구성 · SYN-CX-CHIP-001',
      at: { column: 1, row: 5, columnSpan: 2 },
      reads: 'marking:1',
      writes: 'marking:1',
      options: { finalChipId: 'SYN-CX-CHIP-001' },
    },
    {
      id: 'map-bond-a',
      part: 'map',
      // 🔴 `collect: 'map'` LEFT 2026-08-28 (round Z). It named `lot_map`, and when that route
      //    went the seat went 404 whole. The points are the walk's own dice and the grid is
      //    physics, so what this seat declares now is the two things the ledger and the
      //    relation already own.
      // 🔴 AND `kind: 'void'` LEFT WITH IT. The walk has no kind axis, and filtering by kind in
      //    the client is the part doing the walk's job. Measured before dropping it: `of_kind`
      //    carries `void` on 103,841 of 103,841 atoms -- it is the ONLY kind in the ledger --
      //    so on today's data this changes nothing on screen. The day a second kind lands, the
      //    answer is a declared predicate to follow, not an argument re-added here.
      start: { groupby: 'wafer', value: 'SYN-CX-BW-001' },
      follow: ['inspected', 'observed', 'of_kind'],
      // 🔴 방향을 «선언»합니다 (라운드 ⓪, 2026-08-29). 서버 기본 `both` 는 이 씨앗에서
      //    «남의 웨이퍼»로 새고 그 예산으로 절단이 납니다 -- 실측은 보고서의 표에.
      //    일괄로 바꾼 것이 «아닙니다»: 부품마다 두 방향을 각각 걸어 네 수를 비교했습니다.
      direction: 'outgoing',
      title: '본딩 맵',
      at: { column: 1, row: 6 },
      reads: 'marking:1',
      writes: 'marking:1',
      options: {
        axis: 'bond',
        // 🔴 계약의 이름 그대로. 본딩 맵은 «본딩 웨이퍼의 격자»입니다.
        space: 'die:base',
        // 목업 맵 하단의 기반 선택자. `type` is the node type the count comes from.
        // 🔴 기준 알약 «삭제» (round Z-3, 2026-08-28, 총괄 판정). 셋이 대던 이름
        //    bond_layer · dt_slot · wafer_grid 는 «선언에 없습니다» — 선언된 엔티티 타입은
        //    defect · defect_kind · die · dtjob · lot · lot_slot · quantity · recipe · wafer
        //    아홉입니다. 선언에 없는 낱말을 사용자에게 축으로 내놓는 것이 2026-08-27 에
        //    소유자가 「사용자가 claim, point, collection 이런 걸 어케 암」으로 지적한 그
        //    모양이고, 옛 이름을 새 타입에 «매핑»하면 방금 지운 가운데 표를 다시 만드는 것입니다.
        //    ⚠️ 이 축이 제품에 필요하면 «엔티티 선언»으로 올라옵니다 — 알약이 우기는 게 아닙니다.
        //    같이 빠지는 것: basisChipId — 그 수를 부르던 composition 호출입니다.
        // 트렌드에서 찍은 웨이퍼로 이 맵이 «옮겨 갑니다».
        pageFollows: 'subject:wafer',
        // 🔴 목업이 그린 그 웨이퍼입니다 -- 총괄 실측으로 원장의 «났다» 원자가 199 로
        //    목업 머리의 숫자와 «정확히» 같습니다. 기본값이 void 13 짜리 웨이퍼였던 동안은
        //    목업과 «그림의 밀도»가 달라서 나란히 놓아도 대조가 안 됐습니다.
        // 🔴 격자의 «분모». 걷기는 「검사됐다」와 「났다」를 말하고, 「칸이 몇이나 있나」는
        //    말하지 못합니다 -- 엣지가 없는 이유가 셋이라서(안 함 · 예산 · follow). 그래서
        //    unscanned 는 여기서 오고, 이 행이 없으면 화면이 «수 대신 「격자 미선언」»을 말합니다.
        mapId: 'SYN-CX-BW-001',
      },
    },
    {
      // 🔴 목업의 «칩 확대». 새 부품이 아니라 «좌표계 선언이 다른 두 번째 인스턴스»입니다 --
      //    space 하나와 collect 하나. 부품에는 `if (zoom)` 이 없습니다 (총괄 합격 판정 F).
      //    ⚠️ 오늘은 «없음»이 나오는 게 정상입니다: Finding Point 의 position 이 아직 빈
      //       객체라 inchip 자리를 가진 점이 0개입니다. 그 상태가 F 의 재료입니다.
      id: 'chip-zoom',
      part: 'map',
      title: '칩 확대 · 마킹 1',
      at: { column: 4, row: 4 },
      reads: 'marking:1',
      writes: 'marking:1',
      start: { groupby: 'wafer', marking: 'marking:1' },
      // 🔴 `collect: 'point'` LEFT 2026-08-28 (round Z). This seat named a QUESTION NAME that
      //    `api.js` translated into a route, and that middle table is what the round removes:
      //    a seat that names a route dies when the route does, while `follow` below names
      //    predicates the DECLARATION owns. Nothing else here changed -- the walk, the hops and
      //    the model are the ones this seat already used; only the name is gone.
      // 🔴 이 부품의 «질문»입니다. 좁혀도 되는 것은 «점 부품뿐»입니다 -- 후보·순위는 좁히면
      //    delam 계열 넷을 잃습니다 (총괄 실측 2026-08-24).
      //
      // 🔴 `bonded_from` 이 «왜» 이 목록에 있나 -- 구현자 실측 2026-08-25, 씨앗 SYN-CX-BW-001:
      //      follow 없음                          point «130» · 노드 354
      //      observed,inspected                   point «121» · 노드 250   <- 9개가 «사라집니다»
      //      observed,inspected,bonded_from       point «130» · 노드 266   <- 그대로 · 노드 −25%
      //    사라진 9는 (4..6, 8..10) 의 void 로 «맵 위의 연속된 3×3 덩어리»입니다. 그런데 그 9의
      //    엣지도 «observed» 입니다 -- 필터가 자른 것은 관측이 아니라 «그 관측의 주어로 가는 길»
      //    (SYN-CX-BW-001 --bonded_from--> SYN-CX-CW-HBM-B-02) 이었습니다. 코어 웨이퍼에서 난
      //    void 가 통째로 안 보이는 것이고, 화면에서는 「없다」와 구별이 안 됩니다.
      //    ⚠️ 그래서 관측 술어만으로는 «닿을 수 없습니다». 구조 술어 하나가 같이 있어야 합니다.
      follow: ['observed', 'inspected', 'bonded_from'],
      // 자재를 «한 대 위»까지. 이 좌석은 관측을 보는 자리이고 bonded_from 은 「그 관측의
      //    주어로 가는 길」로만 씁니다 -- 실측 근거가 이 선언 위 주석에 이미 있습니다.
      backbone_hops: 1,
      // 🔴 방향을 «선언»합니다 (라운드 ⓪, 2026-08-29). 서버 기본 `both` 는 이 씨앗에서
      //    «남의 웨이퍼»로 새고 그 예산으로 절단이 납니다 -- 실측은 보고서의 표에.
      //    일괄로 바꾼 것이 «아닙니다»: 부품마다 두 방향을 각각 걸어 네 수를 비교했습니다.
      direction: 'outgoing',
      // hops 8 은 «공짜»입니다 -- 12 와 point 130 으로 «동일»하고 trunc 도 []. (같은 실측)
      hops: 8,
      options: {
        space: 'inchip',
        // 칩 한 변의 물리 크기. 실측(총괄): 칩 20,000um 안에 반경 8um -- 1/2,500 이라
        // 웨이퍼 맵 위에서는 0.008px 이고 «확대에서만» 뜻이 있습니다.
        extent: { x: 20000, y: 20000 },
      },
    },
    {
      // 🔴 목업은 구성에도 «축 열»을 답니다 -- 같은 선언 부품, 다른 필드. 부품을 새로 만들지
      //    않는다는 것이 이 화면의 전제이고, 여기가 그 두 번째 증거입니다.
      id: 'composition-declaration',
      // 🔴 방향을 «선언»합니다 (라운드 ⓪ 보완, 2026-08-29). 이 좌석은 그리는 것이 «선언»이라
      //    walk 을 안 하는 줄 알았는데, `fields` 가 있어서 `optionsFor('y')` 가 «여기» 묶입니다 --
      //    Y축 종류 목록을 만드는 걷기입니다. 좌석에 선언이 하나도 없어 `walkHere` 가 맨 `walk`
      //    이었고, 그래서 서버 기본 both 로 나갔습니다.
      //    실측: both 400노드·절단 nodes,claims  ->  outgoing 251노드·절단 «없음».
      //    ⚠️ 1차에서 못 잡은 이유: 표를 «좌석 선언»으로만 만들고 화면 요청과 대조하지
      //    않았습니다. 이 자리는 선언에 follow 도 direction 도 없어서 목록에 안 떴습니다.
      direction: 'outgoing',
      part: 'declaration',
      title: '축 · 구성',
      at: { column: 4, row: 5 },
      reads: null,
      writes: null,
      options: {
        fields: [
          { label: 'Data table', text: 'composition' },
          { label: 'Marker by', text: 'component_id' },
          { label: 'Color by', text: 'role' },
          { label: 'Data limiting', reads: 'marking:1' },
        ],
      },
    },
    {
      // 🔴 목업 구성의 «셋째 칸». 질의를 새로 하지 않습니다 -- 구성 walk 이 이미 걸어 온 답에서
      //    «찍은 층»을 펼칩니다. 그래서 marking:1 을 읽고 그 외에는 선언이 없습니다.
      id: 'expanded-layer',
      part: 'expandedLayer',
      title: '펼친 층',
      at: { column: 3, row: 5 },
      reads: 'marking:1',
      writes: null,
      // 🔴 씨앗이 «칩»에서 «마킹»으로 (round Z-3, 2026-08-28). 그 칩 id 는 원장에 «0건»이라
      //    좌석이 통째로 404 였습니다. 구성은 `bonded_from` 이 이미 답합니다 -- base die 에서
      //    core die 로 가는 그 엣지이고, 소유자 말대로 pkg 는 (base, x, y) 그 자체입니다.
      //    ⚠️ 다이를 여기 «박지 않습니다»: 손으로 만든 die 씨앗은 JSON 이 1.0 을 못 써서
      //    조용히 «덜» 답합니다 (실측 4a540a50). 마킹의 id 는 walk 이 «만든» 것이라 그 문제가 없습니다.
      start: { groupby: 'die', marking: 'marking:1' },
      follow: ['bonded_from'],
      // 자재를 «두 대 위»까지 따라갑니다 -- 이 좌석의 질문이 「이 다이가 무엇으로
      //    만들어졌나」이고, 코어가 또 다른 코어 위에 앉는 적층을 한 겹 보기 위해서입니다.
      //    관측 예산과 «따로» 쓰이므로 결함 쪽을 굶기지 않습니다.
      backbone_hops: 2,
      // 🔴 방향을 «선언»합니다 (라운드 ⓪, 2026-08-29). 서버 기본 `both` 는 이 씨앗에서
      //    «남의 웨이퍼»로 새고 그 예산으로 절단이 납니다 -- 실측은 보고서의 표에.
      //    일괄로 바꾼 것이 «아닙니다»: 부품마다 두 방향을 각각 걸어 네 수를 비교했습니다.
      direction: 'outgoing',
      options: { finalChipId: 'SYN-CX-CHIP-001' },
    },
    {
      // 🔴 목업의 둘째 맵은 «코어 맵»입니다 (마킹 2 · 후보가 걸린 점). 우리는 본딩 맵을 한 장
      //    더 놓고 있었습니다. 부품은 그대로이고 «기반»과 «읽는 마킹»만 다릅니다 -- 조립식
      //    규칙이 성립한다는 증거이기도 합니다.
      id: 'map-core',
      part: 'map',
      // 🔴 좌석 8 과 «같은 이유, 같은 변경». 부품도 좌표계도 그대로이고 읽는 마킹만 다릅니다 --
      //    조립식 규칙이 두 번째 인스턴스에서도 성립한다는 것이 이 자리의 증거였고, 라우트가
      //    빠진 뒤에도 그대로입니다.
      start: { groupby: 'wafer', value: 'SYN-CX-BW-001' },
      follow: ['inspected', 'observed', 'of_kind'],
      // 🔴 방향을 «선언»합니다 (라운드 ⓪, 2026-08-29). 서버 기본 `both` 는 이 씨앗에서
      //    «남의 웨이퍼»로 새고 그 예산으로 절단이 납니다 -- 실측은 보고서의 표에.
      //    일괄로 바꾼 것이 «아닙니다»: 부품마다 두 방향을 각각 걸어 네 수를 비교했습니다.
      direction: 'outgoing',
      title: '코어 맵 · 마킹 2',
      at: { column: 2, row: 6 },
      reads: 'marking:2',
      writes: 'marking:2',
      options: {
        axis: 'core',
        // 🔴 코어 맵은 «코어 웨이퍼의 격자»입니다 -- dt 는 별도 단계이지 이 맵이 아닙니다.
        space: 'die:core',
        // 🔴 기준 알약 «삭제» (round Z-3, 2026-08-28, 총괄 판정). 셋이 대던 이름
        //    bond_layer · dt_slot · wafer_grid 는 «선언에 없습니다» — 선언된 엔티티 타입은
        //    defect · defect_kind · die · dtjob · lot · lot_slot · quantity · recipe · wafer
        //    아홉입니다. 선언에 없는 낱말을 사용자에게 축으로 내놓는 것이 2026-08-27 에
        //    소유자가 「사용자가 claim, point, collection 이런 걸 어케 암」으로 지적한 그
        //    모양이고, 옛 이름을 새 타입에 «매핑»하면 방금 지운 가운데 표를 다시 만드는 것입니다.
        //    ⚠️ 이 축이 제품에 필요하면 «엔티티 선언»으로 올라옵니다 — 알약이 우기는 게 아닙니다.
        //    같이 빠지는 것: basisChipId — 그 수를 부르던 composition 호출입니다.
        // 트렌드에서 찍은 웨이퍼로 이 맵이 «옮겨 갑니다».
        pageFollows: 'subject:wafer',
        // 🔴 목업이 그린 그 웨이퍼입니다 -- 총괄 실측으로 원장의 «났다» 원자가 199 로
        //    목업 머리의 숫자와 «정확히» 같습니다. 기본값이 void 13 짜리 웨이퍼였던 동안은
        //    목업과 «그림의 밀도»가 달라서 나란히 놓아도 대조가 안 됐습니다.
        mapId: 'SYN-CX-BW-001',
      },
    },
    {
      // 🔴 후보 계열은 marking:2 -- 목업대로. 후보를 고르면 순위표의 같은 행이 같이 움직이고,
      //    그것이 「마킹은 부품 밖에 산다」가 화면에서 보이는 자리다.
      id: 'candidate-list',
      part: 'candidateList',
      start: { groupby: 'wafer', value: 'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0' },
      // 후보 질문 «통째로». 위 CANDIDATE_QUESTION 이 이 셋의 «유일한» 출처입니다.
      ...CANDIDATE_QUESTION,
      title: '원인 후보 · SYN-CX-BW-001',
      at: { column: 3, row: 6 },
      reads: 'marking:2',
      writes: 'marking:2',
      options: {
        seedNodeId: 'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0',
      },
    },
    {
      id: 'rank-list',
      part: 'rankList',
      start: { groupby: 'wafer', value: 'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0' },
      // 후보 질문 «통째로». 위 CANDIDATE_QUESTION 이 이 셋의 «유일한» 출처입니다.
      ...CANDIDATE_QUESTION,
      title: '순위 · SYN-CX-BW-001',
      at: { column: 4, row: 6 },
      reads: 'marking:2',
      writes: 'marking:2',
      options: {
        seedNodeId: 'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0',
      },
    },
    {
      // 🔴 「어느 것들로 닿을 수 있는지」 (소유자 2026-08-25). 마킹 1 을 주어로 «한 홉» 걷고,
      //    술어마다 「무엇에 몇 개」를 보여 줍니다. 한 줄을 찍으면 그 술어로 닿는 노드 집합이
      //    마킹 2 에 들어갑니다 -- 그래서 후보 트렌드·후보 맵이 «따라 움직입니다».
      //
      // 🔴 start 가 «리터럴이 아니라 마킹»입니다. 이 부품에서 씨앗을 박으면 「마킹에서 어디로」가
      //    「그 웨이퍼에서 어디로」가 되어 질문 자체가 바뀝니다. 마킹이 비면 「아직 안 골랐다」
      //    라고 말하고 기다립니다 -- 빈 표가 아니라 문장입니다.
      id: 'reach',
      part: 'reach',
      start: { marking: 'marking:1', groupby: 'wafer' },
      collect: 'reach',
      title: '닿는 곳 · 마킹 1 에서 한 홉',
      at: { column: 1, row: 7, columnSpan: 2 },
      reads: 'marking:1',
      writes: 'marking:2',
    },
    {
      // 🔴 「걷기 API 사용 위한 검색창」 (소유자 2026-08-26). 다른 부품이 «선언»으로 들고
      //    태어나는 네 칸(타입·키·follow·collect)을 사람이 그 자리에서 고릅니다. 그래서
      //    걷기 API 는 여전히 «하나»이고, 늘어난 것은 갈래가 아니라 선언입니다.
      //
      // 🔴 이 부품은 마킹을 «읽지 않습니다». 키를 손으로 넣는 것이 이 부품의 존재 이유라,
      //    마킹을 주어로 삼으면 그 순간 「닿는 곳」과 같은 부품이 됩니다. 대신 결과 행을
      //    찍으면 마킹 2 에 «쓰므로», 손으로 시작한 걸음도 체인에 들어옵니다.
      id: 'walkBox',
      part: 'walkBox',
      title: '걷기 -- 타입 · 키 · 따라갈 술어 · 모을 것',
      at: { column: 1, row: 8, columnSpan: 2 },
      reads: null,
      writes: 'marking:2',
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
  // 🔴 선언은 «한 번만» 풉니다 (E-1, 2026-08-30). 걷기 검색창과 제어 막대가 각자 주입받아
  //    각자 부르는 바람에 화면 로드마다 `/declaration` 이 «둘»이었습니다. 부품이 서로를
  //    모르는 것은 맞고, 합칠 자리는 «주입하는 여기»입니다 -- 부품 안은 한 글자도 안 바뀝니다.
  let declarationOnce = null;
  const loadDeclarationOnce = () => {
    if (!declarationOnce) {
      declarationOnce = fetchDeclaration({ apiBase, fetchImpl })
        // 🔴 «거절은 가두지 않습니다». 선언 자체는 안 바뀌지만 「못 읽었다」는 다음 번에
        //    읽힐 수 있고, 실패한 약속을 캐시하면 그 화면은 영원히 「선언을 못 읽었습니다」가
        //    됩니다 -- 오늘 밤 내내 가른 「없어서」와 「아직」의 그 구분입니다.
        .then((got) => { if (!got || !got.ok) declarationOnce = null; return got; });
    }
    return declarationOnce;
  };
  return {
    ...layout,
    panels: (layout.panels || []).map((decl) => {
      const options = decl.options || {};
      // 🔴 부품이 «자기 질문»을 선언합니다. `collect` 와 같은 자리에 서는 세 칸이고, 적힌 것만
      //    실립니다 -- 빈 선언이면 `walkHere` 가 `walk` «그 자체»라 요청이 한 글자도 안 바뀝니다.
      //    부품은 이것을 모릅니다: 질문은 «선언»에 있고 부품은 자기 마킹과 collect 만 들고 걷습니다.
      const question = {};
      if (decl.follow) question.follow = decl.follow;
      if (decl.direction) question.direction = decl.direction;
      if (decl.hops !== undefined && decl.hops !== null) question.hops = decl.hops;
      // 예산도 «선언»입니다. 이걸 안 실으면 후보 질문의 세 칸 중 하나가 부품 options 로
      // 새고, 그 순간 세 자리가 다시 «다른 열쇠»가 됩니다 (그게 2aaf194b 가 15 로 늘어난
      // 이유입니다 -- direction 만 맞추고 node_limit 은 다른 길로 들어왔습니다).
      if (decl.node_limit !== undefined && decl.node_limit !== null) question.node_limit = decl.node_limit;
      // 자재 예산도 «선언»입니다 (라운드 ③). 안 적은 부품은 안 싣고, 그러면 서버 기본 0 입니다.
      if (decl.backbone_hops !== undefined && decl.backbone_hops !== null) {
        question.backbone_hops = decl.backbone_hops;
      }
      const walkHere = Object.keys(question).length
        ? (spec) => walk({ ...question, ...(spec || {}) })
        : walk;
      // 🔴 THE ADDRESS IS INJECTED, NEVER DECLARED. `apiBase` is a fact about where this page
      //    is running, so it is known HERE and nowhere in the layout data -- which is what
      //    keeps that data serialisable the day a screen is saved or dragged.
      const bound = { ...options, walk: walkHere, apiBase, fetchImpl, dpr: dpr || 1 };
      // 🔴 걷기 검색창은 «다른 모양의 walk» 을 받습니다. 이 부품의 `collect` 는 화면이 선언한
      //    질문 이름이 아니라 «서버의 노드 종류»이고, 씨앗도 마킹이 아니라 사람이 넣은 키에서
      //    만들어집니다. 같은 이름이 두 뜻이라 섞으면 오류 없이 «빈 답»이 나옵니다.
      // 🔴 `decl.part` 이지 `options.part` 이 «아닙니다» -- `options` 는 `decl.options` 이고
      //    좌석이 아닙니다. 틀리면 조건이 «영원히 거짓»이라 주입이 조용히 안 되고, 화면은
      //    「선언을 받지 못했습니다」를 그립니다 -- 라우트가 200 을 주는 동안에도.
      if (decl.part === 'walkBox') {
        bound.loadDeclaration = loadDeclarationOnce;
        bound.walk = createWalkBoxWalk({ apiBase, fetchImpl });
      }
      // 🔴 Y축의 «수식어 목록»도 선언에서 옵니다 (라운드 ①-a). 걷기 검색창과 «같은 함수»이고
      //    같은 이름으로 주입합니다 -- 부품 둘이 각자 라우트를 알게 되는 것을 막는 자리입니다.
      if (decl.part === 'controlBar') {
        bound.loadDeclaration = loadDeclarationOnce;
      }
      // The basis counts come from ANOTHER route, so the seam is here and the part stays
      // route-free: it is handed a function that answers 「타입별 몇 개인가」 and nothing else.
      if (options.fields) {
        // 🔴 THE LISTS ARE FETCHED HERE, NOT IN THE PART. `y` is the ratio axes this route can
        //    plot plus the walk's measured quantities; `group` is the peer scopes the screen
        //    declared. The part receives `[{id, label}]` and knows nothing else.
        bound.optionsFor = (key) => {
          if (key === 'y') {
            return Promise.all([
              // 🔴 종류 목록도 «같은 걷기»에서 나옵니다 (round Z-3, 2026-08-28). 죽은
              //    trend_y 라우트를 부르던 자리인데, 종류는 응답의 defect_kind 노드가 이미
              //    말합니다 -- 목록을 위해 «두 번째 질문»을 만들 이유가 없습니다.
              walkHere({
                start: { groupby: 'wafer',
                  value: 'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0' },
                follow: ['inspected', 'observed', 'of_kind'],
              }).then(trendFromWalk),
              walkHere({
                start: { groupby: 'wafer',
                  value: 'ledger-entity:v1:WyJ3YWZlciIseyJ3YWZlciI6IlNZTi1DWC1CVy0wMDEifV0' },
                // 같은 후보 질문입니다 -- 목록도 표도 같은 답을 보아야 합니다.
                ...CANDIDATE_QUESTION,
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
        // 🔴 라우트가 아니라 «걷기 + 세기» (round Z-3 B, 2026-08-28). lot_map 이 서버에서
        //    조인해 주던 수를 창이 셉니다 -- 총괄 판정 그대로이고, 재료는 이미 응답 안에
        //    있습니다(of_kind 엣지가 종류 노드로, inspected/observed 가 다이로).
        bound.loadWaferFacts = (kind, wafer) => walkHere({
          start: { value: entitySeedId('wafer', { wafer: wafer || options.waferQuestion.row }) },
          follow: ['inspected', 'observed', 'of_kind'],
          // 🔴 이 곁가지는 «관측만» 봅니다 -- 좌석이 선언한 «자재» 예산을 물려받으면 안 됩니다
          //    (지시: 관측만 보는 자리엔 안 붙인다). 실측으로 좌석 질문이 그대로 새고 있어서
          //    여기서 «명시적으로» 끕니다. null 이면 경계가 안 싣습니다.
          backbone_hops: null,
        }).then((answer) => waferFactsFromWalk(answer, kind));
      }
      if (options.peers) {
        // 🔴 넷 중 «하나»만 셀 수 있습니다. 실측 2026-08-28: leg · bond_lot · scan_recipe 는
        //    원장에 원자 «0» 이고 값도 «0» 입니다 -- 창은 원장에 낱말이 없는 것을 못 셉니다.
        //    총괄 판정: 컨트롤을 «남기고» 그 사실을 말한다. 「0」 이나 「데이터 없음」은
        //    «세어 봤더니 0» 과 구별이 안 되므로 쓰지 않습니다.
        bound.loadPeerCount = (scope) => {
          const eqp = String(scope || '').startsWith('bond_eqp:')
            ? String(scope).slice('bond_eqp:'.length) : null;
          if (!eqp) {
            return Promise.resolve({
              subjects: null, units: null, relation: null, column: null,
              analysis: null, straddling: null, message: '이 축은 원장에 없습니다',
            });
          }
          return walkHere({
            start: { value: entitySeedId('wafer', { wafer: options.waferQuestion.row }) },
            follow: ['measures'],
          }).then((answer) => {
            const got = peerCountFromWalk(answer, eqp);
            // 🔴 네 번째 부재입니다 (총괄 판정 2026-08-28). 앞의 셋은 「축이 원장에 없다」·
            //    「walk 이 잘렸다」·「아직 안 불렀다」이고, 이건 «축은 있는데 이 씨앗에 값이
            //    없다» 입니다. 실측: 보드 씨앗으로 follow=measures 가 200 에 엣지 «0» —
            //    참인데 화면에서는 앞의 셋과 «같은 대시»였습니다.
            if (got && got.units === 0) {
              return { ...got, message: '이 씨앗에는 측정이 없습니다' };
            }
            return got;
          });
        };
      }
      if (options.basisChipId) {
        bound.loadBasisCounts = () => walkHere({
          start: { groupby: 'chip', value: options.basisChipId }, collect: 'basis',
        });
      }
      // 🔴 질문이 «박히지 않은» 맵은 walk 에서 옵니다. 라우트 이름은 여기서도 안 나옵니다 --
      //    선언의 collect 하나가 어디로 갈지 정합니다.
      if (!options.question) {
        if (decl.part === 'map' && decl.collect) {
          bound.load = (override) => walkHere({ collect: decl.collect, ...(override || {}) });
        }
        // 🔴 라우트 이름을 «안 가진» 맵 좌석 (round Z). 걷기는 좌석의 선언 그대로 나가고,
        //    격자는 «두 번째 재료»로 여기서 묶입니다 -- 부품은 apiBase 도 fetchImpl 도 모르는
        //    채로 남습니다. 이미 있는 loadPages · loadByWafer · loadBasisCounts 와 같은 모양입니다.
        if (decl.part === 'map' && !decl.collect && decl.follow) {
          // 🔴 씨앗은 «원장 노드 id» 입니다. lot_map 은 웨이퍼를 «이름»으로 받았고 walk 은 안
          //    받습니다 -- 이름을 그대로 보내면 422 이고, 화면엔 「서버가 거절」이 뜹니다
          //    (실측 2026-08-28: `id=SYN-CX-BW-001` -> 422). 마킹에서 오는 좌석은 이미 id 를
          //    들고 있고, 씨앗이 «박힌» 이 좌석만 여기서 만들어 줍니다. 같은 함수, 같은 철자.
          // 🔴 «마지막»에 정규화합니다. 부품이 reload 마다 `{start: this.startFor()}` 를 덮어쓰기로
          //    넘기는데, 그 값은 선언에 적힌 이름 그대로입니다 -- 먼저 바꿔 두면 그 덮어쓰기가
          //    다시 이름으로 되돌려 놓습니다 (실측: 그래서 422 가 두 번째까지 살아남았습니다).
          //    이미 노드 id 인 것(마킹에서 온 것)은 «건드리지 않습니다».
          const seedOf = (start) => {
            if (!start || !start.value) return start;
            const text = String(start.value);
            if (text.startsWith('ledger-entity:v1:')) return start;
            const type = start.groupby || 'wafer';
            return { ...start, value: entitySeedId(type, { [type]: text }) };
          };
          bound.load = (override) => {
            const spec = { start: decl.start, follow: decl.follow, ...(override || {}) };
            spec.start = seedOf(spec.start);
            return walkHere(spec);
          };
          bound.loadGrid = (mapId) => fetchMapGrid({
            apiBase, fetchImpl, mapId: mapId || options.mapId,
          });
          // 트렌드에서 찍은 웨이퍼로 «옮겨 갈» 때: 같은 걸음, 시작점만 그 웨이퍼.
          bound.loadByWafer = (wafer) => walkHere({
            start: { value: entitySeedId('wafer', { wafer }) }, follow: decl.follow,
          });
        }
        // 🔴 구성 세 좌석 (round Z-3). 맵과 «같은 걸음»이고 읽는 모델만 다릅니다 -- 라우트를
        //    되살리지 않고, 새 술어도 안 만들고, `bonded_from` 이 이미 답하는 것을 읽습니다.
        //    부품은 «자기가 무엇을 읽는지»만 알고 어디서 오는지는 모릅니다.
        if (decl.part !== 'map' && !decl.collect && decl.follow) {
          // 🔴 같은 걷기, «읽는 모델»만 다릅니다. 갈래는 부품 이름 하나이고, 그 이름은 이미
          //    선언에 있습니다 -- 여기에 라우트 표를 다시 만들지 않으려면 이 한 줄이어야 합니다.
          const read = decl.part === 'mainTrend' ? trendFromWalk : compositionFromWalk;
          // 🔴 `axis` 는 «읽는 쪽»의 인자이지 걷기의 인자가 아닙니다 (라운드 ①-a). 전선에
          //    실리면 같은 질문이 축마다 «다른 열쇠»가 되어 합침이 깨지고, 서버는 모르는
          //    칸을 조용히 버립니다 -- 200 이 증거가 아니라는 그 자리입니다. 그래서 여기서
          //    떼어 내고, 나가는 요청은 축과 무관하게 «글자 그대로» 같습니다.
          bound.load = (override) => {
            const { axis, ...rest } = override || {};
            return walkHere({ start: decl.start, follow: decl.follow, ...rest })
              .then((answer) => read(answer, axis));
          };
        }
        return { ...decl, options: bound };
      }
      return {
        ...decl,
        options: {
          ...bound,
          // The override is how a part turns a page without learning a route: it hands back
          // the one field it is changing and the question stays the composition root's.
          load: (override) => walkHere({
            collect: 'map', ...options.question, ...(override || {}),
          }),
          // 씨앗으로 찍힌 웨이퍼를 그리는 길. 같은 라우트, 축만 웨이퍼.
          loadByWafer: (wafer) => walkHere({
            start: { groupby: 'wafer', value: wafer },
            collect: 'map', ...options.question, slot: undefined,
          }),
          // 목업의 페이지 목록. Measured: a slot-less call carries the row's whole slot list.
          loadPages: () => walkHere({
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
