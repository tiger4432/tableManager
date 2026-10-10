// 걷기 검색 — 「걷기 API 에 «폼 채워서 날려 보는» 자리」 (소유자 주문 그대로).
//
// 🔴 탐색기가 «아닙니다». 마킹 저장소도, 이력 나무도, 줍기(collect) 체인도 없습니다 —
//    총괄이 그것을 명시적으로 거뒀습니다. 여기 있는 것은 인자를 채우는 칸들과 Walk 버튼
//    하나, 그리고 «응답을 보여 주는 자리»뿐입니다.
//
// ⚠️ R&D 보드의 `WalkBoxPanel` 을 «안 씁니다». 처음에 그것을 앉혔다가 걷어냈습니다:
//    그 부품은 `direction` · `node_limit` 컨트롤이 «없고», `hops` 는 「고르는 값이 아니라
//    고른 경로가 데려오는 값」으로 지어져 있습니다(그 파일이 그렇게 적습니다). 이 주문은
//    셋을 «폼 칸»으로 요구하므로, 그 부품으로는 «고쳐야만» 됩니다 — 그리고 그 파일은
//    R&D 보드 것이라 못 고칩니다. 그래서 이 페이지가 자기 폼을 갖습니다.
//
// 🔴🔴 그런데 «요청을 짓는 것»은 이 페이지 일이 아닙니다 (소유자 2026-09-06, 깔끔 ④:
//    「같은 기능인데 «두 경로»가 있어서도 안 됨」). 걷기 요청을 짓는 함수가 둘이라 한쪽만
//    `hops` 를 안 실었고, 화면이 「3홉」이라 쓰는 동안 서버는 12홉을 걸었습니다.
//    => 그래서 이 페이지는 «폼»만 갖고, 요청은 `createWalkBoxWalk` «하나»가 짓습니다.
//
// 🔵 가져다 쓰는 것 둘. 다시 쓰지 않습니다:
//      `fetchDeclaration`    무엇을 고를 수 있나는 «선언»이 답합니다. 화면이 목록을 안 듭니다
//      `createWalkBoxWalk`   전선. 다섯 인자와 응답 키가 «한 자리»에 삽니다
//
// 🔴 배치 A (총괄 2b5819e1d · 소유자 10-02 「걷기는 A로」): 폼은 왼쪽 레일(.wk-rail), 결과는
//    오른쪽(.wk-main). 두 부품이 자기 div 를 갖고, 격자에 앉히는 것은 페이지(walk.html)입니다.
//    화면 글자는 영어(「영어로도 바꿔」), 서버가 보낸 문장은 그대로.
//
// ⛔ 걷기 API 는 «안 건드립니다» — 소유자 지시. 부르기만 합니다.

import { fetchDeclaration, createWalkBoxWalk, routeWith, fetchKeyValues, fetchTimePage }
  from '../rnd_board/api.js';
// 🔴 겉모양은 «부품과 같이» 다닙니다 (총괄 판정 2026-09-06).
import { ensureWalkStyles } from './styles.js';
import {
  followFromRoute, followChoices, walkableRoutes,
  cutBudgets, stepAlong,
} from './derive.js';
// 🔴 C-72. 표의 «결정»은 전부 여기 있고 이 파일에는 DOM 쓰기만 남습니다.
import { walkTableView, nextRoutes, ROUTE } from './table_view.js';
// «+ Column»'s choices, read off the walk (lead 5cf5c3401 answer 2).
import { routesFrom, valuesAt } from './reach_table.js';
// The trend of a column (lead f984ab01d): the model and the part that draws it.
import { walkPoints, pagePoints, mergePoints, trendModel, walkedTime, windowOf, PAGE_ROWS } from './trend.js';
import { TrendView } from './trend_view.js';
// 🔴 C-120. 「꺼짐 + 왜」의 좌석 하나 — 메인 그리드의 쓰기 버튼 셋이 쓰던 그 기제입니다.
import { setDisabledReason } from '../disabled_reason.js';
// The graph view of a start (lead c9bf53033) — a part with its own div; this page only places it.
import { SubgraphView, seedsOf } from './subgraph_view.js';
// The start baskets (lead bc63378e5) - the start marking's editor, a part with its own div in the right panel.
import { StartBaskets, BASKET_WORDS } from './start_baskets.js';
// PICK A NODE by first letters (lead bccbdd601) - a part with its own div.
import { NodeSearch, SEARCH_LIMIT } from './node_search.js';
// The markings live outside every part, in one store (lead f6fc6ba66 · the board's MarkingStore).
import { MarkingStore, SIGN } from '../rnd_board/marking_store.js';
// Copy id (lead 5cf5c3401): the one clipboard seat - the operating server is plain HTTP.
import { writeClipboardRich } from '../clipboard_write.js';
import { entitySeedId } from '../rnd_board/api.js';
import { markingIntent } from '../rnd_board/panel.js';
// The words other screens already draw for the same facts, spelled once.
import { CHOOSE, FAILED, LOADING, WALKING, unitText } from '../ui_words.js';
import { UNKNOWN, UNPICKED, isBlank } from '../absent.js';
// The worlds the walk reads (lead 99032248f): one seat, every request through it; the picker is a part.
import { withWorld, worldList, addressFor } from '../world.js';
import { BranchPicker } from '../branch_picker.js';

/** The graph's chain of markings: the start, then one per Continue. Its length is the chain's length. */
const GRAPH_CHAIN = Object.freeze(['walk-start', 'walk-2', 'walk-3', 'walk-4']);

/** 라벨«이자» 꺼진 사유. 한 상수라 둘이 갈라질 수 없습니다. */
const RUNNING = WALKING;

/** Why a table's Next is off: it walks on from the rows checked (lead 53050a4ec, owner 「행 선택은 해야지」). */
const CHECK_ROWS_FIRST = 'Check rows first';

/** 서버가 받는 값 그대로. 화면이 «자기 이름»을 만들지 않습니다. */
const DIRECTIONS = ['both', 'outgoing', 'incoming'];

// 🔴 손잡이의 기본값을 «여기 안 적습니다». 비워 두면 «안 실리고», 안 실리면 서버가 정합니다 —
//    무엇으로 정해졌는지는 응답의 `walk` 가 말합니다.
const SERVER_DEFAULT = 'default';
/** The one knob with a default here (lead 34d91c09d 9, owner 10-10 «다 넣어»): node_limit starts at the server's most
 *  (ledger_subgraph.MAX_NODE_LIMIT), not its 400 that cut the side by side walk. Cleared, the server's default again. */
export const NODE_LIMIT = 1000;
/** STEP's number knobs: the wire's name, the form's key, the server's bounds (null: none above) - drawn and sent from this
 *  one list (fanout_limit, lead 5d946a639). Blank, a knob is not sent and the server decides. */
const NUMBER_KNOBS = [['hops', 'hops', 1, 40], ['node_limit', 'nodeLimit', 10, NODE_LIMIT], ['fanout_limit', 'fanoutLimit', 1, null]];

/**
 * Where a side by side table's box scrolls so its node axis stands in its middle (lead 10-10 after 517eb6c2c: a wide +
 * side pushed the node, Δ and the − side past the box): the axis' centre on the box's, within what the box can scroll.
 */
export function axisScrollLeft({ boxLeft, boxWidth, axisLeft, axisRight, scrollLeft, scrollWidth }) {
  const want = scrollLeft + (axisLeft + axisRight) / 2 - (boxLeft + boxWidth / 2);
  return Math.max(0, Math.min(scrollWidth - boxWidth, Math.round(want)));
}

/** A column by what it reads - its steps and its value - not its place in the table. */
const columnKey = (column) => JSON.stringify([column.steps, column.value]);

const el = (doc, tag, cls, text) => {
  const n = doc.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = String(text);
  return n;
};

/**
 * @param {Document} doc
 * @param {HTMLElement} host
 * @param {{apiBase?: string, fetchImpl?: Function, world?: string|string[], branchMount?: HTMLElement,
 *          pickWorld?: Function}} [deps]
 *   `world` - the worlds the walk reads, in the order picked (none: the operating one); `pickWorld(names)` - the
 *   page's address follows a pick (the walk itself walks again on the new worlds, no reload: lead 10-09).
 */
export function boot(doc, host, deps) {
  const options = deps || {};
  const apiBase = options.apiBase || '';
  // 자기 규칙을 «자기가» 들고 앉습니다. 호스트는 아무것도 안 챙깁니다.
  ensureWalkStyles(doc);
  // THE WALK'S ONE WORLD SEAT (lead 99032248f), as the board's: every request goes through this fetch.
  let worlds = worldList(options.world);
  const fetchImpl = withWorld(options.fetchImpl || ((url, init) => globalThis.fetch(url, init)), () => worlds);
  const walk = createWalkBoxWalk({ apiBase, fetchImpl });

  const state = {
    decl: null, declState: 'loading', declReason: '',
    type: '', keys: {}, follow: new Set(), collect: new Set(),
    direction: '', hops: '', nodeLimit: String(NODE_LIMIT), fanoutLimit: '',
    // How long the shown walk took, ms (lead 34d91c09d 9: a slower walk says so in the counts line).
    run: 'idle', result: null, reason: '', took: null,
    // What the shown result was asked with - the form can change after the walk.
    asked: null,
    view: 'table',
    // Which rows the side by side table shows (lead 5cf5c3401): all, those the groups differ on, those one missed.
    rowFilter: 'all',
    // «+ Column»: the columns added a type, for this page; the type whose picker is open and the route it holds.
    added: new Map(), picking: '', pickedRoute: -1,
    // The types whose empty columns are shown, the cells whose several values are unfolded (lead 34d91c09d 7, 1).
    emptyOpen: new Set(), openCells: new Set(),
    // The trend open (lead f984ab01d): its section's type, row and column; the time pages asked and where they end.
    trend: null,
    // Which loop chips are on, per route row (`routeKey`). Off unless pressed (lead 5d5b8d750).
    loopsOn: new Map(),
    // The table's steps after the form's walk, each from the rows checked along one edge (lead 53050a4ec), and
    // which one is shown: 0 is the form's walk.
    steps: [],
    at: 0,
  };
  const routeKey = (r) => `${r.to}|${r.follow.slice().sort().join('+')}`;
  const loopsOf = (r) => state.loopsOn.get(routeKey(r)) || new Set();

  const entities = () => (state.decl && state.decl.entities) || [];
  const keysOf = (type) => {
    const found = entities().find((e) => e.type === type);
    return (found && found.keys) || [];
  };
  // The two parts this page seats: the form rail and the result. Made once and kept across renders.
  const rail = el(doc, 'div', 'wk-rail');
  const main = el(doc, 'div', 'wk-main');
  // Made once and kept across renders (`render` empties the host); it walks through the same wire.
  const markings = new MarkingStore();
  const graphMount = el(doc, 'div', 'wk-graph');
  const graph = new SubgraphView(graphMount, { doc, walk, entities, markings, chain: GRAPH_CHAIN,
    worldChips: worlds.length > 1, declaration: () => state.decl });
  // The box is the key it searches by: what is typed is that key, a node picked fills every key.
  const searchMount = el(doc, 'div', '');
  const search = new NodeSearch(searchMount, { doc,
    ask: (prefix) => fetchKeyValues({ apiBase, fetchImpl, type: state.type, startsWith: prefix, limit: SEARCH_LIMIT }),
    onType: (text) => { if (search.axis) state.keys[search.axis] = text; baskets.render(); },
    onPick: (node) => { state.keys = { ...node.keys }; render(); },
    onAnswer: () => baskets.render() });
  /** The form's subject as the baskets' + takes it - picked from the list or typed; none until a type and a key. A key
   *  typed that the ledger names no node by says so (lead b5cdcbc75). */
  const pickedNode = () => {
    const keys = Object.fromEntries(Object.entries(state.keys || {}).filter(([, v]) => !isBlank(v)));
    return state.type && Object.keys(keys).length
      ? { id: entitySeedId(state.type, keys), label: Object.values(keys).join(' · '), type: state.type, keys,
        unheld: search.holdsNone(keys[search.axis]) }
      : null;
  };
  const sideMount = el(doc, 'div', 'wk-side');
  const baskets = new StartBaskets(sideMount, { doc, markings, name: GRAPH_CHAIN[0], picked: pickedNode });
  // The trend part, made once and seated under the tables when a column's trend is open.
  const trendMount = el(doc, 'div', '');
  const trendView = new TrendView(trendMount, { doc });
  // 🔴 C-120. 꺼진 이유가 «둘»입니다: 「걷는 중」(라벨과 같은 상수), 그리고 Positive 바구니가 빔.
  const goReason = () => (state.run === 'running'
    ? RUNNING
    : (seedsOf(markings.entries(GRAPH_CHAIN[0])).positive.length ? '' : BASKET_WORDS.noStart));
  // Walk follows the baskets as they change, not only when the page redraws.
  let goButton = null;
  markings.subscribe(GRAPH_CHAIN[0], () => { if (goButton) setDisabledReason(goButton, goReason()); });
  /** The graph walks the start marking as it stands. */
  const showGraph = (opts) => { graph.show(opts); };
  // 🔴 체크칸은 선언된 술어 «전부» (소유자 10-06 「엣지 리스트 다 주고 체크하는걸 메인으로」).
  //    거르는 것은 걷기의 일입니다. R&D 걷기 상자는 동결이라 닿는 것만 그립니다.
  const declaredPredicates = () => (state.decl && state.decl.predicates) || [];
  const allPredicates = () => declaredPredicates().map((p) => p.name);
  const followOptions = () => followChoices(allPredicates(), allPredicates(), state.follow);

  /**
   * 시작 타입에서 «고른 도착지»까지 선언이 아는 길. 지어내지 않고 `pathsBetween` 을 씁니다.
   * 🔴 도착지마다 «따로» 냅니다. 합치면 누른 사람이 «무엇을 향한 길»을 골랐는지 알 수 없습니다.
   */
  function routes() {
    if (!state.decl || !state.type || !state.collect.size) return [];
    const out = [];
    // 🔴 걷기가 «거절할» 길은 내놓지 않습니다. 규칙과 사유는 `derive.js` 의 `walkableRoutes` 에 있습니다.
    for (const to of state.collect) {
      for (const r of walkableRoutes(state.decl, state.type, to)) out.push({ ...r, to });
    }
    return out.sort((a, b) => a.hops - b.hops || a.follow.length - b.follow.length);
  }

  /** 폼의 칸 -> 전선의 인자. «빈 칸은 안 싣습니다» — 그것이 「안 골랐다」의 정직한 모양입니다. */
  function spec() {
    const out = { type: state.type, keys: state.keys };
    if (state.follow.size) out.follow = [...state.follow];
    // 🔴 `follow` 와 «같은 규율». 안 고르면 안 싣고, 안 실으면 서버가 전부 줍니다.
    if (state.collect.size) out.collect = [...state.collect];
    if (state.direction) out.direction = state.direction;
    for (const [wire, key] of NUMBER_KNOBS) {
      const n = parseInt(state[key], 10);
      if (Number.isFinite(n)) out[wire] = n;
    }
    return out;
  }

  /** Walk: the baskets as they are (lead bc63378e5). Ctrl and Shift on it retired - the baskets add and sign. */
  async function fire() {
    await walkStarts();
  }

  /** The walk from the start marking as it stands - a Walk press, and a world picked (lead 10-09). */
  async function walkStarts() {
    if (!markings.count(GRAPH_CHAIN[0])) return;
    // The graph walks its marking and nothing else - follow, collect and the knobs are the table's.
    if (state.view === 'graph') { showGraph(); return; }
    // The table walks the same signed starts: + as positive, - as negative (the wire takes the first + as the seed).
    // One + start alone is asked by its type and keys, as the form asked it (walk_layout L7 · L8: the request does not change).
    const starts = seedsOf(markings.entries(GRAPH_CHAIN[0]));
    const signed = starts.positive.length > 0 && (starts.positive.length > 1 || starts.negative.length > 0);
    const one = signed ? null : baskets.describe(starts.positive[0]);
    const asked = { ...spec(), ...(one ? { type: one.type, keys: { ...one.keys } } : {}), ...(signed ? starts : {}) };
    state.run = 'running'; state.result = null; state.reason = '';
    state.asked = { ...asked, keys: { ...asked.keys } };
    // A new start clears the steps and what their checks wrote, as the graph's new start does (lead 53050a4ec).
    state.steps = []; state.at = 0;
    for (const name of GRAPH_CHAIN.slice(1)) markings.clear(name);
    render();
    const began = Date.now();
    const res = await walk(asked);
    state.took = Date.now() - began;
    if (res && res.ok) { state.run = 'done'; state.result = res; }
    else {
      // ⚠️ 실패도 «보여야» 합니다. 빈 화면은 「안 눌렸나」와 구별이 안 됩니다.
      state.run = 'failed';
      state.reason = (res && res.message) || UNKNOWN;
    }
    render();
  }

  // ── the table's steps (lead 53050a4ec): a step's checked rows are the page's marking the graph reads too ──
  /** The marking a step's checks write, the graph's chain after its start; none once the chain is used up. */
  const checksOf = (at) => GRAPH_CHAIN[at + 1] || '';
  /** The step shown: the form's walk, or one walked on from it. */
  const shownStep = () => (state.at === 0
    ? { run: state.run, result: state.result, reason: state.reason, took: state.took }
    : state.steps[state.at - 1]);

  /** From the rows checked on step `at` (+ and -), one step along `route`; it stands after `at`, the steps beyond it go. */
  async function walkOn(at, seeds, route) {
    const asked = stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to });
    const step = { title: `${route.predicate} → ${route.to}`, asked, run: 'running', result: null, reason: '' };
    state.steps = [...state.steps.slice(0, at), step];
    state.at = at + 1;
    for (const name of GRAPH_CHAIN.slice(at + 2)) markings.clear(name);
    render();
    const began = Date.now();
    const res = await walk(asked);
    step.took = Date.now() - began;
    if (state.steps[at] !== step) return;   // walked over meanwhile
    if (res && res.ok) { step.run = 'done'; step.result = res; }
    else { step.run = 'failed'; step.reason = (res && res.message) || UNKNOWN; }
    render();
  }

  function field(label, cls = 'wk-field') {
    const box = el(doc, 'div', cls);
    box.append(el(doc, 'div', 'wk-label', label));
    return box;
  }

  /** A name above its control - the key, step and type cells all take this shape. */
  function cell(name, control, cls = 'wk-cell') {
    const box = el(doc, 'label', cls);
    box.append(el(doc, 'span', 'wk-keyname', name), control);
    return box;
  }

  function renderStart(root) {
    const start = field('Start');
    const sel = el(doc, 'select', 'wk-select');
    // 🔴 The placeholder is NO type. An option without a value of its own is worth its text, and
    //    picking it again made that text the type (lead b417e2ad8).
    const none = el(doc, 'option', '', CHOOSE);
    none.value = '';
    sel.append(none);
    for (const e of entities()) {
      const o = el(doc, 'option', '', e.type);
      o.value = e.type;
      if (e.type === state.type) o.selected = true;
      sel.append(o);
    }
    sel.addEventListener('change', () => {
      state.type = sel.value;
      // 타입을 바꾸면 그 타입에 «없는» 키는 따라올 자격이 없습니다. 체크는 남습니다 — 목록에 전부
      // 보이니 숨은 체크가 없습니다 (총괄 10-06, 10-02 판정을 뒤집음).
      const allowedKeys = new Set(keysOf(state.type));
      state.keys = Object.fromEntries(
        Object.entries(state.keys).filter(([k]) => allowedKeys.has(k)));
      state.result = null; state.run = 'idle';
      render();
      void openSearch();
    });
    start.append(cell('Type', sel, 'wk-cell wk-cell-row'));

    // 🔴 고르는 것은 «키 하나의 값»이 아니라 «노드 하나»입니다. 한 번 고르면 키 칸이
    //    «전부» 찹니다 — 칸마다 따로 고르게 하면 «그 조합은 없는» 씨앗을 만들 수 있습니다.
    // 🔵 친 키는 «남습니다» — 고르지 않으면 그 키 그대로가 노드입니다.
    if (state.type) {
      const subjBox = field('Pick a node', 'wk-sub');
      search.setText(search.axis ? state.keys[search.axis] : '');
      subjBox.append(searchMount);
      start.append(subjBox);
    }

    const keys = keysOf(state.type);
    if (!state.type) start.append(el(doc, 'div', 'wk-note', 'Pick a type for its keys'));
    else if (!keys.length) start.append(el(doc, 'div', 'wk-note', 'This type has no keys'));
    const grid = el(doc, 'div', 'wk-keys');
    // The key the box stands for has no second cell.
    const cells = keys.filter((k) => k !== search.axis);
    for (const k of cells) {
      const input = el(doc, 'input', 'wk-input');
      input.type = 'text';
      input.value = state.keys[k] === undefined ? '' : state.keys[k];
      // A typed key is the subject too: the baskets' + follows it (only the baskets redraw, the caret stays).
      input.addEventListener('input', () => { state.keys[k] = input.value; baskets.render(); });
      grid.append(cell(k, input));
    }
    if (cells.length) start.append(grid);
    root.append(start);
  }

  // ── collect: «무엇을 가져오나». 고른 타입은 칩(× 로 뺌), 더하기는 남은 타입의 드롭다운 하나 ──
  // 🔵 드롭다운인 이유: 이 화면이 «타입 하나를 고르는» 데 이미 쓰는 컨트롤이 그것입니다.
  function renderCollect(root) {
    const box = field('Collect');
    const types = entities().map((e) => e.type);
    if (!types.length) {
      box.append(el(doc, 'div', 'wk-note', 'No entity declared'));
      root.append(box);
      return;
    }
    const chips = el(doc, 'div', 'wk-chips');
    for (const t of types.filter((t) => state.collect.has(t))) {
      const chip = el(doc, 'button', 'wk-chip', `${t} ×`);
      chip.type = 'button';
      chip.setAttribute('data-collect', t);
      chip.setAttribute('aria-label', `Remove ${t}`);
      chip.addEventListener('click', () => { state.collect.delete(t); render(); });
      chips.append(chip);
    }
    const rest = types.filter((t) => !state.collect.has(t));
    if (rest.length) {
      const add = el(doc, 'select', 'wk-add');
      add.setAttribute('aria-label', 'Add a type to collect');
      const first = el(doc, 'option', '', '+ Type');
      first.value = '';
      add.append(first);
      for (const t of rest) {
        const o = el(doc, 'option', '', t);
        o.value = t;
        add.append(o);
      }
      add.addEventListener('change', () => {
        if (!add.value) return;
        state.collect.add(add.value);
        render();
      });
      chips.append(add);
    }
    box.append(chips);
    if (!state.collect.size) box.append(el(doc, 'div', 'wk-note', `${UNPICKED} · ${SERVER_DEFAULT} · all`));
    root.append(box);
  }

  // ── 경로: 시작과 도착지가 정해지면 선언이 «길을 알려 줍니다» ──────────────────
  // 🔴 채워 주는 것이지 «뺏는 게 아닙니다». 누르면 그 길의 술어가 체크에 «더해지고» hops 가 채워집니다.
  //    이미 있는 체크는 지우지 않습니다 (소유자 10-06 「경로는 보조용」).
  //    지금 고른 줄은 «지금 칸의 값»과 같은 줄입니다 — 손으로 고치면 표시가 정직하게 빠집니다.
  function renderRoutes(root) {
    if (!state.type || !state.collect.size) return;
    const found = routes();
    const box = el(doc, 'div', 'wk-field');
    const head = el(doc, 'div', 'wk-routes-head');
    head.append(el(doc, 'span', 'wk-label', `Route to ${[...state.collect].join(', ')}`),
      el(doc, 'span', 'wk-note', unitText(found.length, 'route')));
    box.append(head);
    if (!found.length) {
      // 「길이 없다」는 답입니다. 빈 칸으로 두면 「아직 안 셌다」와 같아 보입니다.
      box.append(el(doc, 'div', 'wk-note',
        `No route from ${state.type} to ${[...state.collect].join(' · ')}`));
    }
    // A route with the loop chips that are on fills follow and hops.
    const useRoute = (r, on) => {
      const asked = routeWith(r, on);
      // 채우는 두 줄. 규칙은 `derive.js` 에 있고, 지우면 그쪽 하니스가 빨개집니다.
      state.follow = new Set([...state.follow, ...followFromRoute(allPredicates(), asked.follow)]);
      state.hops = String(asked.hops);
      render();
    };
    const sameSet = (a, b) => a.size === b.size && [...a].every((x) => b.has(x));
    for (const r of found) {
      const asked = routeWith(r, loopsOf(r));
      const picked = state.hops === String(asked.hops)
        && sameSet(state.follow, new Set(followFromRoute(allPredicates(), asked.follow)));
      const route = el(doc, 'div', 'wk-route' + (picked ? ' is-on' : ''));
      const row = el(doc, 'button', 'wk-path');
      row.type = 'button';
      row.setAttribute('aria-pressed', picked ? 'true' : 'false');
      row.append(el(doc, 'span', 'wk-pathto', `→ ${r.to}`));
      // A line each, cut at the row's end on purpose (lead 18da45b73): the whole in its title, and in the form once pressed.
      for (const [cls, text] of [['wk-pathchain', r.chain.join(' → ')], ['wk-pathmeta', `${unitText(asked.hops, 'hop')} · ${asked.follow.join(', ')}`]]) {
        const line = el(doc, 'span', cls, text);
        line.title = text;
        line.setAttribute('data-clip-ok', '');
        row.append(line);
      }
      row.addEventListener('click', () => useRoute(r, loopsOf(r)));
      route.append(row);
      // The route's self-loops: pressing one adds it to this route and uses the route.
      if (r.loops.length) {
        // Its word on its own line: beside it the 44 px chips stood boxed taller than their line (lead 34d91c09d 8).
        route.append(el(doc, 'div', 'wk-note', 'self-loops'));
        const chips = el(doc, 'div', 'wk-loops');
        for (const loop of r.loops) {
          const on = loopsOf(r).has(loop.predicate);
          const chip = el(doc, 'button', 'wk-loopchip' + (on ? ' is-on' : ''), `↻ ${loop.predicate}`);
          chip.type = 'button';
          chip.setAttribute('aria-pressed', on ? 'true' : 'false');
          chip.title = `${loop.at} → ${loop.at}`;
          chip.addEventListener('click', () => {
            const next = new Set(loopsOf(r));
            if (on) next.delete(loop.predicate); else next.add(loop.predicate);
            state.loopsOn.set(routeKey(r), next);
            useRoute(r, next);
          });
          chips.append(chip);
        }
        route.append(chips);
      }
      box.append(route);
    }
    root.append(box);
  }

  // ── 손잡이 셋. 비면 «안 갑니다» — 그 상태를 칸이 «말합니다» ────────────────────
  function renderStep(root) {
    const box = field('Step');
    const grid = el(doc, 'div', 'wk-steps');
    const dir = el(doc, 'select', 'wk-select');
    dir.append(el(doc, 'option', '', SERVER_DEFAULT));
    for (const d of DIRECTIONS) {
      const o = el(doc, 'option', '', d);
      o.value = d;
      if (d === state.direction) o.selected = true;
      dir.append(o);
    }
    dir.addEventListener('change', () => { state.direction = dir.value; });
    grid.append(cell('direction', dir));
    for (const [name, key, min, max] of NUMBER_KNOBS) {
      const input = el(doc, 'input', 'wk-input');
      input.type = 'number';
      input.min = String(min);
      if (max !== null) input.max = String(max);
      input.placeholder = SERVER_DEFAULT;
      input.value = state[key];
      input.addEventListener('input', () => { state[key] = input.value; });
      grid.append(cell(name, input));
    }
    box.append(grid);
    root.append(box);
  }

  // ── follow: 선언된 술어 전부를 체크로. 이것이 «주»이고 경로 목록이 «보조»입니다 ─────────
  function renderFollow(root) {
    const opts = followOptions();
    const box = field('Follow');
    if (!opts.length) {
      box.append(el(doc, 'div', 'wk-note', 'No predicate declared'));
      root.append(box);
      return;
    }
    const list = el(doc, 'div', 'wk-checks');
    for (const name of opts) {
      const row = el(doc, 'label', 'wk-check' + (state.follow.has(name) ? ' is-on' : ''));
      row.setAttribute('data-follow', name);
      const cb = el(doc, 'input');
      cb.type = 'checkbox';
      cb.checked = state.follow.has(name);
      cb.addEventListener('change', () => {
        if (state.follow.has(name)) state.follow.delete(name); else state.follow.add(name);
        render();
      });
      row.append(cb, el(doc, 'span', '', name));
      list.append(row);
    }
    box.append(list);
    if (!state.follow.size) box.append(el(doc, 'div', 'wk-note', `${UNPICKED} · ${SERVER_DEFAULT}`));
    root.append(box);
  }

  function renderGo(root) {
    const go = el(doc, 'button', 'wk-go', state.run === 'running' ? RUNNING : 'Walk');
    go.type = 'button';
    goButton = go;
    setDisabledReason(go, goReason());
    go.addEventListener('click', () => { void fire(); });
    root.append(go);
  }

  /**
   * 응답을 «표»로. 행은 «노드 하나»이고, 타입이 여럿이면 구획으로 나뉩니다.
   * 🔴 C-72. 이 함수는 «아무것도 정하지 않습니다» — 구획도 컬럼도 셀 글자도 못 그린 수도
   *    `walkTableView` 가 답하고, 여기서는 그 답을 DOM 으로 옮기기만 합니다.
   */
  function renderTable(box, r, starts) {
    // C-98. 선언의 술어 목록이 «같이» 갑니다 — 확인 술어를 이름 대는 것은 선언입니다.
    const view = walkTableView(r, entities(), (state.decl && state.decl.predicates) || [], undefined, starts, state.added,
      state.emptyOpen);
    if (view.unsplit) box.append(el(doc, 'div', 'wk-note', 'One table for both signs: the answer does not say which start reached a node'));
    if (view.groups) box.append(rowFilterBar());
    renderSections(box, view);
    if (view.groups && state.trend) renderTrend(box, view, r);
  }

  /** All rows · Differs · Missing (lead 5cf5c3401): which rows of the side by side table are drawn. */
  function rowFilterBar() {
    const bar = el(doc, 'div', 'wk-rowfilter');
    bar.setAttribute('role', 'group');
    for (const [value, word] of [['all', 'All rows'], ['differs', 'Differs'], ['missing', 'Missing']]) {
      const b = el(doc, 'button', 'wk-view' + (state.rowFilter === value ? ' is-on' : ''), word);
      b.type = 'button';
      b.setAttribute('data-rows', value);
      b.setAttribute('aria-pressed', String(state.rowFilter === value));
      b.addEventListener('click', () => { state.rowFilter = value; render(); });
      bar.append(b);
    }
    return bar;
  }

  /** A row's check, as the board marks (Shift: a control). */
  function checkCell(tr, checks, id) {
    const td = el(doc, 'td', 'wk-check');
    const cb = el(doc, 'input');
    cb.type = 'checkbox';
    cb.setAttribute('data-row', id);
    const sign = markings.signOf(checks, id);
    cb.checked = sign !== SIGN.ABSENT;
    if (sign === SIGN.CONTROL) tr.className = 'is-control';
    // A click, for its Shift: a checked row is a control with it, as the board marks (lead 10-09).
    cb.addEventListener('click', (event) => { markings.toggle(checks, id, markingIntent(event).sign); render(); });
    td.append(cb);
    tr.append(td);
  }

  /**
   * The formula's section (lead 5cf5c3401): with two groups the + columns reversed on the left, the node in the centre,
   * Δ beside it, the − columns on the right (lead 34d91c09d (나): Δ in the first screen with the node; the − side scrolls
   * in the table's box); with any other count the node first, then each group's columns. Three head rows: the group,
   * the step (once over the columns that share it), the value's name.
   */
  function formulaTable(section, checks) {
    const pair = section.groups.length === 2;
    const n = section.heads.length;
    const table = el(doc, 'table', 'wk-table wk-sides');
    const thead = el(doc, 'thead');
    const band = el(doc, 'tr');
    const steps = el(doc, 'tr');
    const head = el(doc, 'tr');
    if (checks) for (const row of [band, steps, head]) row.append(el(doc, 'th', 'wk-check'));
    const word = (sign) => (sign === '−' ? BASKET_WORDS.negative : sign === '+' ? BASKET_WORDS.positive : sign);
    const side = (g, i) => {
      const cls = g.sign === '−' ? 'wk-minus' : 'wk-plus';
      const th = el(doc, 'th', `wk-sidehead ${cls}${pair && i === 0 ? ' is-left' : ''}`, `${word(g.sign)} · ${unitText(g.starts, 'start')} · ${unitText(g.count, 'row')}`);
      th.colSpan = n;
      th.setAttribute('data-sign', g.sign);
      band.append(th);
      const parts = pair && i === 0 ? [...section.parts].reverse() : section.parts;
      // A step said once over the run of columns that share it.
      parts.forEach((p, k) => {
        if (k > 0 && parts[k - 1].step === p.step) { steps.children[steps.children.length - 1].colSpan += 1; return; }
        const s = el(doc, 'th', `wk-stephead ${cls}`, p.step);
        s.colSpan = 1;
        steps.append(s);
      });
      for (const p of parts) head.append(el(doc, 'th', cls, p.leaf));
    };
    // The node's own columns in the centre (keys, attributes); a type with none says its name there.
    const own = section.centreHeads.length ? section.centreHeads : [section.type];
    const over = (cls, span) => {
      for (const row of [band, steps]) {
        const th = el(doc, 'th', cls);
        th.colSpan = span;
        row.append(th);
      }
    };
    const centre = () => {
      over('wk-ownhead wk-centre', own.length);
      for (const h of own) head.append(el(doc, 'th', 'wk-centre', h));
    };
    const delta = () => {
      if (!section.deltaHeads.length) return;
      over('wk-ownhead wk-delta', section.deltaHeads.length);
      for (const h of section.deltaHeads) head.append(el(doc, 'th', 'wk-num wk-delta', h));
    };
    if (pair) { side(section.groups[0], 0); centre(); delta(); side(section.groups[1], 1); } else { centre(); section.groups.forEach(side); }
    thead.append(band, ...(section.parts.some((p) => p.step) ? [steps] : []), head);
    table.append(thead);
    const tbody = el(doc, 'tbody');
    const td = (cell, cls, at) => {
      const c = el(doc, 'td', cell.missing ? `wk-missing ${cls}` : `${cell.numeric ? 'wk-num ' : ''}${cls}`);
      if (cell.span) c.colSpan = cell.span;
      // A value and, under it, who gave it (lead 99ed68cb7 C): its node's keys and how this side reached that node.
      const sources = cell.sources || [];
      const said = (value, k) => {
        c.append(el(doc, 'div', 'wk-val', value));
        if (sources[k]) c.append(el(doc, 'div', 'wk-src', sources[k]));
      };
      const open = Boolean(cell.rest) && state.openCells.has(at);
      // Several values: the first and «+N»; a press on «+N» unfolds them all in the cell, another folds (lead 34d91c09d 1).
      if (open) cell.values.forEach(said);
      else said(cell.text, 0);
      if (cell.rest) {
        if (open) c.className += ' is-open';
        const more = el(doc, 'button', 'wk-more', open ? 'Less' : cell.rest);
        more.type = 'button';
        more.setAttribute('aria-expanded', String(open));
        more.addEventListener('click', (event) => {
          event.stopPropagation();
          if (open) state.openCells.delete(at); else state.openCells.add(at);
          render();
        });
        c.append(more);
      }
      return c;
    };
    const rows = section.rows.filter((row) => state.rowFilter === 'all' || (state.rowFilter === 'differs' ? row.differs : row.missing));
    for (const row of rows) {
      const tr = el(doc, 'tr');
      tr.setAttribute('data-row-id', row.id);
      if (checks) checkCell(tr, checks, row.id);
      const cells = (i) => (pair && i === 0 ? [...row.byGroup[i]].reverse() : row.byGroup[i]);
      const node = () => {
        const cells = row.centre.length ? row.centre : [{ text: row.label }];
        cells.forEach((cell, i) => {
          const c = el(doc, 'td', 'wk-centre');
          c.append(el(doc, 'span', 'wk-centrelabel', cell.text));
          // The id is picked, not read (lead 5cf5c3401): an icon on the first centre cell, shown with its row (34d91c09d 5).
          if (i === 0) c.append(copyIdButton(row.id));
          tr.append(c);
        });
      };
      const group = (i) => {
        for (const cell of cells(i)) {
          const c = td(cell, section.groups[i].sign === '−' ? 'wk-minus' : 'wk-plus',
            cell.rest ? `${section.type}\u0000${row.id}\u0000${i}\u0000${cell.col === undefined ? ROUTE : columnKey(section.columns[cell.col])}` : '');
          // A value cell opens its column's trend for this row (lead f984ab01d).
          if (cell.col !== undefined && !cell.missing) {
            c.className += ' wk-pick';
            c.setAttribute('data-col', String(cell.col));
            c.addEventListener('click', () => openTrend(section.type, row.id, columnKey(section.columns[cell.col]), i));
          }
          tr.append(c);
        }
      };
      const deltas = () => { for (const d of row.deltas) tr.append(td(d, 'wk-delta')); };
      if (pair) { group(0); node(); deltas(); group(1); } else { node(); section.groups.forEach((_, i) => group(i)); }
      tbody.append(tr);
    }
    table.append(tbody);
    return table;
  }

  /** The id behind an icon on its row (lead 5cf5c3401, 34d91c09d 5); clipboard_write puts it on the clipboard. */
  function copyIdButton(id) {
    const copy = el(doc, 'button', 'wk-copyid');
    copy.type = 'button';
    copy.setAttribute('data-id', id);
    copy.setAttribute('aria-label', 'Copy id');
    copy.title = 'Copy id';
    copy.append(el(doc, 'span', 'wk-copyicon'));
    copy.addEventListener('click', () => {
      if (!writeClipboardRich('', id)) return;
      copy.className = 'wk-copyid is-done';
      copy.title = 'Copied';
      copy.setAttribute('aria-label', 'Copied');
    });
    return copy;
  }

  /** A column's trend for one row (lead f984ab01d): the walk's points now, the server's time page after. The column is
   *  held by what it reads, not its place - a fold or a number column added moves places (lead 34d91c09d 2, 7). */
  function openTrend(type, row, col, group) {
    state.trend = { type, row, col, group, t0: null, pages: [], earlier: null, later: null, hasEarlier: null, hasLater: null };
    render();
    void loadTrend('around');
  }

  /** The column a trend reads, when its section is still drawn. */
  function trendColumn(view) {
    const t = state.trend;
    const section = t && view.sections.find((s) => s.type === t.type && s.groups);
    const col = section ? section.columns.findIndex((c) => columnKey(c) === t.col) : -1;
    return col >= 0 ? { section, column: section.columns[col], col } : null;
  }

  /** One more time page - around the walked time, or past either end (the implementer's contract, edge values only). */
  async function loadTrend(mode) {
    const t = state.trend;
    const view = t && t.view;
    const at = view && trendColumn(view);
    if (!at || at.column.steps.length !== 1 || at.column.value.on !== 'edge') return;
    const step = at.column.steps[0];
    const ask = mode === 'around' ? { around: t.t0 === null ? null : new Date(t.t0).toISOString() }
      : mode === 'earlier' ? { earlier: t.earlier } : { later: t.later };
    if (!Object.values(ask)[0]) return;
    const got = await fetchTimePage({ apiBase, fetchImpl, id: t.row, predicate: step.predicate, direction: step.direction,
      page: PAGE_ROWS, ...ask });
    if (state.trend !== t || !got.ok) return;
    t.pages.push(got.answer);
    if (mode !== 'later') { t.earlier = got.page.earlier; t.hasEarlier = got.page.has_earlier; }
    if (mode !== 'earlier') { t.later = got.page.later; t.hasLater = got.page.has_later; }
    render();
  }

  /** The open trend under the tables. */
  function renderTrend(box, view, r) {
    const t = state.trend;
    const at = trendColumn(view);
    if (!at) return;
    const own = walkPoints(view.index, view.groups, t.row, at.column);
    const walked = new Set(own.map((p) => p.key));
    // A point says who gave it, as its cell does (lead 99ed68cb7 C): the same read, the same seat.
    const points = t.pages.reduce((all, answer) => mergePoints(all, pagePoints(answer, view.groups, t.row, at.column, walked)), own)
      .map((p) => ({ ...p, source: view.sources.source(p.group === null || p.group === undefined ? null : view.groups[p.group], p.node) }));
    if (t.t0 === null) t.t0 = walkedTime(own, r.generated_at, t.group);
    // The view the next page is read against: the trend's own, not a second computing of the table.
    t.view = view;
    const row = at.section.rows.find((x) => x.id === t.row);
    const word = (sign) => (sign === '−' ? BASKET_WORDS.negative : sign === '+' ? BASKET_WORDS.positive : sign);
    // The axis: the pages' windows and the pressed side's walked points; another side's far off stands at the edge.
    const model = trendModel(points, undefined, { windows: t.pages.map(windowOf).filter(Boolean), group: t.group });
    trendView.show({ title: `${row ? row.label : t.row} · ${at.section.columnHeads[at.col]}`, model,
      groups: at.section.groups.map((g) => word(g.sign)), t0: t.t0,
      ...(t.pages.length ? { onEarlier: () => { void loadTrend('earlier'); }, onLater: () => { void loadTrend('later'); },
        hasEarlier: Boolean(t.hasEarlier), hasLater: Boolean(t.hasLater) } : {}),
      onClose: () => { state.trend = null; render(); } });
    box.append(trendMount);
  }

  /** «+ Column» (lead 5cf5c3401 answer 2): a route the rows take in this walk, then what its end holds; × takes one out. */
  function columnPicker(section, index) {
    const box = el(doc, 'div', 'wk-addcol');
    // Columns no row has a value in, folded until pressed (lead 34d91c09d 7).
    if (section.empty.count) {
      const fold = el(doc, 'button', 'wk-add wk-emptycols' + (section.empty.open ? ' is-on' : ''),
        unitText(section.empty.count, 'empty column'));
      fold.type = 'button';
      fold.setAttribute('aria-pressed', String(section.empty.open));
      fold.addEventListener('click', () => {
        if (state.emptyOpen.has(section.type)) state.emptyOpen.delete(section.type); else state.emptyOpen.add(section.type);
        render();
      });
      box.append(fold);
    }
    const added = state.added.get(section.type) || [];
    added.forEach((column, i) => {
      const chip = el(doc, 'button', 'wk-chip', `${column.words.join(' · ')} ×`);
      chip.type = 'button';
      chip.setAttribute('aria-label', `Remove ${column.words.join(' · ')}`);
      chip.addEventListener('click', () => { added.splice(i, 1); render(); });
      box.append(chip);
    });
    if (state.picking !== section.type) {
      const open = el(doc, 'button', 'wk-add', '+ Column');
      open.type = 'button';
      open.addEventListener('click', () => { state.picking = section.type; state.pickedRoute = -1; render(); });
      box.append(open);
      return box;
    }
    const ids = section.rows.map((row) => row.id);
    const routes = routesFrom(index, ids);
    const route = routes[state.pickedRoute] || null;
    const ways = el(doc, 'select', 'wk-select');
    ways.append(el(doc, 'option', '', routes.length ? 'Route' : 'No route from these rows'));
    routes.forEach((r, i) => {
      const o = el(doc, 'option', '', `${r.words.join(' · ')} → ${r.to.join(' · ')}`);
      o.value = String(i);
      if (i === state.pickedRoute) o.selected = true;
      ways.append(o);
    });
    ways.addEventListener('change', () => { state.pickedRoute = ways.value === '' ? -1 : Number(ways.value); render(); });
    box.append(ways);
    if (route) {
      const what = el(doc, 'select', 'wk-select');
      what.append(el(doc, 'option', '', 'Value'));
      valuesAt(index, ids, route.steps).forEach((v, i) => {
        const o = el(doc, 'option', '', v.on === 'edge' ? `edge · ${v.name}` : v.on === 'key' ? `key · ${v.name}` : v.name);
        o.value = String(i);
        what.append(o);
      });
      what.addEventListener('change', () => {
        const v = valuesAt(index, ids, route.steps)[Number(what.value)];
        if (!v) return;
        if (!state.added.has(section.type)) state.added.set(section.type, []);
        state.added.get(section.type).push({ steps: route.steps, value: { on: v.on, name: v.name },
          words: [`${route.words.join(' · ')} → ${route.to.join(' · ')}`, v.name] });
        state.picking = '';
        render();
      });
      box.append(what);
    }
    const cancel = el(doc, 'button', 'wk-add', 'Cancel');
    cancel.type = 'button';
    cancel.addEventListener('click', () => { state.picking = ''; render(); });
    box.append(cancel);
    return box;
  }

  /** The table's sections and what it did not draw. */
  function renderSections(box, view) {
    const at = state.at;
    const checks = checksOf(at);
    for (const section of view.sections) {
      const sec = el(doc, 'div', 'wk-sec');
      sec.append(el(doc, 'div', 'wk-sechead', section.heading));
      // Next above its table, once (lead 3375edd9b).
      if (checks) sec.append(nextRow(at, section, checks));
      if (section.groups) {
        sec.append(columnPicker(section, view.index), formulaTable(section, checks));
        box.append(sec);
        continue;
      }

      const table = el(doc, 'table', 'wk-table');
      const thead = el(doc, 'thead');
      const hr = el(doc, 'tr');
      if (checks) hr.append(el(doc, 'th', 'wk-check'));
      for (const column of section.columns) hr.append(el(doc, 'th', '', column.name));
      thead.append(hr);
      table.append(thead);

      const tbody = el(doc, 'tbody');
      for (const row of section.rows) {
        const tr = el(doc, 'tr');
        if (checks) checkCell(tr, checks, row.id);
        for (const cell of row.cells) {
          const td = el(doc, 'td', cell.numeric ? 'wk-num' : '', cell.text);
          // The id is picked, not read (styles.js .wk-id): cut on purpose.
          if (cell.kind === 'id') { td.className = 'wk-id'; td.setAttribute('data-clip-ok', ''); }
          tr.append(td);
        }
        tbody.append(tr);
      }
      table.append(tbody);
      sec.append(table);
      box.append(sec);
    }

    if (view.hidden) {
      box.append(el(doc, 'div', 'wk-note', `${view.hidden} more not drawn`));
    }
  }

  /** Under a section: the declared edges one step from its type; each walks on from the rows checked of it. */
  function nextRow(at, section, checks) {
    const line = el(doc, 'div', 'wk-next');
    line.append(el(doc, 'span', 'wk-label', 'Next'));
    const seeds = seedsOf(section.rows.map((row) => [row.id, markings.signOf(checks, row.id)]));
    for (const route of nextRoutes(state.decl, section.type)) {
      const go = el(doc, 'button', 'wk-next-edge', `${route.predicate} → ${route.to}`);
      go.type = 'button';
      setDisabledReason(go, seeds.positive.length ? '' : CHECK_ROWS_FIRST);
      go.addEventListener('click', () => { if (seeds.positive.length) void walkOn(at, seeds, route); });
      line.append(go);
    }
    return line;
  }

  /** The steps walked: the form's walk, then each step on from it; a press shows that step's table again. */
  function renderSteps(root) {
    if (!state.steps.length) return;
    const line = el(doc, 'div', 'wk-steps');
    const titles = [askedTitle(state.asked || {}), ...state.steps.map((s) => s.title)];
    titles.forEach((title, i) => {
      const b = el(doc, 'button', 'wk-step' + (state.at === i ? ' is-on' : ''), `Step ${i + 1} · ${title}`);
      b.type = 'button';
      b.addEventListener('click', () => { state.at = i; render(); });
      line.append(b);
    });
    root.append(line);
  }

  /** What the shown walk asked (lead 34d91c09d 6): the baskets' counts and the types it collects - not the box's last
   *  key, which named one start of several. One + start alone is asked by its keys, so it is one. */
  function askedTitle(asked) {
    const plus = asked.positive ? asked.positive.length : 1;
    const minus = (asked.negative || []).length;
    const to = (asked.collect || []).join(', ');
    return `+ ${plus}${minus ? ` · − ${minus}` : ''}${to ? ' → ' + to : ''}`;
  }

  function renderHead(root) {
    const head = el(doc, 'div', 'wk-mainhead');
    const shown = shownStep();
    const r = shown.result;
    const askedOf = state.at === 0 ? state.asked : shown.asked;
    if (state.view === 'table' && shown.run === 'done' && r && askedOf) {
      head.append(el(doc, 'span', 'wk-title', state.at === 0 ? askedTitle(askedOf) : shown.title));
      // 🔴 두 수가 «다른 모집단»입니다. collect 는 노드를 거르고 엣지는 «안 거릅니다», 그래서
      //    collect 가 걸렸을 때만 «주어»를 답니다.
      const asked = (askedOf.collect || []).join(', ');
      const took = shown.took === null || shown.took === undefined ? '' : ` · ${(shown.took / 1000).toFixed(1)} s`;
      head.append(el(doc, 'span', 'wk-counts', (asked
        ? `Nodes ${r.nodes.length} (collect: ${asked}) · Edges ${r.edges.length} (all)`
        : `Nodes ${r.nodes.length} · Edges ${r.edges.length}`) + took));
      // The server's own sentence and its state (lead b5cdcbc75: «Nodes 1 · Edges 0» alone read as a wafer with no data).
      if (r.message) head.append(el(doc, 'span', 'wk-note wk-said', [r.state, r.message].filter(Boolean).join(' · ')));
    }
    // ── Table | Graph ───────────────────────────────────────────────────────
    // ⚰️ Compare retired 10-10 (lead 3375edd9b, owner «Compare 접어»): the walk table side by side is the one screen that
    //    sets the signs against each other - its group per sign, its missing cells, its «predicate · name» heads.
    const views = el(doc, 'div', 'wk-views');
    for (const [name, word] of [['table', 'Table'], ['graph', 'Graph']]) {
      const button = el(doc, 'button', 'wk-view' + (state.view === name ? ' is-on' : ''), word);
      button.type = 'button';
      button.setAttribute('data-view', name);
      button.addEventListener('click', () => {
        state.view = name;
        if (name === 'graph' && state.type) showGraph({ reuse: true });
        render();
      });
      views.append(button);
    }
    head.append(views);
    root.append(head);
  }

  function renderResult(root) {
    const box = el(doc, 'div', 'wk-result');
    const shown = shownStep();
    if (shown.run === 'idle') {
      box.append(el(doc, 'div', 'wk-note', 'No walk yet'));
    } else if (shown.run === 'running') {
      box.append(el(doc, 'div', 'wk-note', RUNNING));
    } else if (shown.run === 'failed') {
      // 🔴 사유를 «서버의 말»로. 여기서 다시 쓰면 같은 거절이 두 화면에서 달라집니다.
      const line = el(doc, 'div', 'wk-fail');
      line.append(el(doc, 'b', '', FAILED), el(doc, 'span', '', ' · ' + shown.reason));
      box.append(line);
    } else if (shown.result) {
      const r = shown.result;
      // 🔴 몇 홉을 «실제로» 걸었나. 요청한 수와 다르면 그 자체가 답입니다.
      if (r.walk) {
        box.append(el(doc, 'div', 'wk-walk',
          `Asked ${unitText(r.walk.hops_requested, 'hop')} · reached ${unitText(r.walk.hops_reached, 'hop')}`
          + ` · ${r.walk.direction}`));
      }
      // 🔴 S-13: «기준 시각». 위의 수들이 「지금」이 아니라 «그때»의 것입니다.
      if (r.generatedAt) {
        box.append(el(doc, 'div', 'wk-note', `As of ${String(r.generatedAt)}`));
      }
      // ⚠️ 절단은 «말합니다». 🔴 «자른 축»을 씁니다 — `reason` 을 그대로 쓰면 다 걸은 답에도 depth 가 실립니다.
      if (r.cut) {
        box.append(el(doc, 'div', 'wk-trunc',
          `Cut · ${cutBudgets(r.truncatedAxes, r.limits).join(' · ')}`));
      }
      // 🔴 타입 분포 — 「collect 가 «먹었나»」가 «눈에» 보이는 자리입니다. ⚠️ 거르지 않고 세기만.
      if (r.nodes.length) {
        const byType = new Map();
        for (const n of r.nodes) {
          const t = n.type || '—';
          byType.set(t, (byType.get(t) || 0) + 1);
        }
        const dist = el(doc, 'div', 'wk-dist');
        dist.append(el(doc, 'span', 'wk-distlabel', 'Types'));
        // The types the shown walk collected: the form's, or the step's far type.
        const collected = state.at === 0 ? state.collect : new Set(shown.asked.collect);
        for (const [t, n] of [...byType.entries()].sort((a, b) => b[1] - a[1])) {
          const chip = el(doc, 'span', 'wk-distchip' + (collected.has(t) ? ' is-asked' : ''));
          chip.append(el(doc, 'b', '', t), el(doc, 'span', '', ` ${n}`));
          dist.append(chip);
        }
        box.append(dist);
      }
      // 🔴 「닿은 것이 없다」는 «실패가 아닙니다». 서버가 문장을 들고 오면 머리가 그것을 씁니다.
      if (!r.nodes.length && !r.message) box.append(el(doc, 'div', 'wk-note', 'No node reached'));
      const askedOf = state.at === 0 ? state.asked : shown.asked;
      renderTable(box, r, { positive: (askedOf && askedOf.positive) || [], negative: (askedOf && askedOf.negative) || [] });
    }
    root.append(box);
  }

  function render() {
    host.textContent = '';
    rail.textContent = '';
    main.textContent = '';
    // The rail scrolls inside itself; Walk sits in its foot, always in reach (lead 2b5819e1d).
    const body = el(doc, 'div', 'wk-form');
    const foot = el(doc, 'div', 'wk-rail-foot');
    if (state.declState === 'loading') {
      body.append(el(doc, 'div', 'wk-note', `Declaration · ${LOADING}`));
    } else if (state.declState === 'failed') {
      // 「못 읽음」과 「없음」은 다릅니다 — 앞은 다시 눌러 볼 수 있습니다.
      const line = el(doc, 'div', 'wk-fail');
      line.append(el(doc, 'b', '', 'Declaration not read'), el(doc, 'span', '', ' · ' + state.declReason));
      const again = el(doc, 'button', 'wk-go', 'Retry');
      again.type = 'button';
      again.addEventListener('click', load);
      body.append(line);
      foot.append(again);
    } else {
      renderStart(body);
      renderCollect(body);
      renderFollow(body);
      renderRoutes(body);
      renderStep(body);
      renderGo(foot);
      renderHead(main);
      if (state.view === 'graph') main.append(graphMount);
      else { renderSteps(main); renderResult(main); }
    }
    rail.append(body, foot);
    // The baskets read the form's picked node for their «+»: drawn with the page.
    baskets.render();
    host.append(rail, main, sideMount);
    // Each side by side table opens with its node axis in the middle of its box - on every draw, a walk again too.
    if (host.querySelectorAll) for (const table of host.querySelectorAll('table.wk-sides')) centreAxis(table);
  }

  /** A drawn table's box scrolled to its axis: the node's columns in the leaf head row. */
  function centreAxis(table) {
    const axis = [...table.querySelectorAll('thead tr:last-child th.wk-centre')];
    if (!axis.length) return;
    const box = table.getBoundingClientRect();
    table.scrollLeft = axisScrollLeft({ boxLeft: box.left, boxWidth: table.clientWidth, axisLeft: axis[0].getBoundingClientRect().left,
      axisRight: axis[axis.length - 1].getBoundingClientRect().right, scrollLeft: table.scrollLeft, scrollWidth: table.scrollWidth });
  }

  /** A type picked: the box asks its first nodes, and its answer names the key the box stands for. */
  async function openSearch() {
    if (!state.type) return;
    // 타입이 그새 바뀌었으면 «옛 답»을 앉히지 않습니다 (the box drops an answer asked before the newer one).
    if (await search.open()) render();
  }

  async function load() {
    state.declState = 'loading'; render();
    const got = await fetchDeclaration({ apiBase, fetchImpl });
    if (got && got.ok) { state.decl = got; state.declState = 'ready'; }
    else { state.declState = 'failed'; state.declReason = (got && got.message) || UNKNOWN; }
    if (picker) picker.show({ worlds: (got && got.worlds) || [], current: worlds, operating: got && got.operating });
    render();
  }

  /** Picking worlds walks again on them and the page stays (lead 10-09): the declaration is read on the new worlds,
   *  then the same form and the same signed starts walk again; the address follows through `pickWorld`. */
  async function pickWorlds(names) {
    worlds = worldList(names);
    graph.worldChips = worlds.length > 1;
    if (options.pickWorld) options.pickWorld(worlds);
    await load();
    if (state.run !== 'idle' || markings.count(GRAPH_CHAIN[0])) await walkStarts();
  }

  const picker = options.branchMount
    ? new BranchPicker(options.branchMount, { doc, onPickSet: (names) => { void pickWorlds(names); } }) : null;
  if (picker) picker.show({ current: worlds });
  load();
  return { state, spec, fire, render, graph, baskets };
}

// 🔴 부팅은 «이 파일 끝»에서만. bare node 로 이 모듈을 읽어도 DOM 을 안 건드려야
//    하니스가 붙을 수 있습니다 — R&D 보드 main.js 가 같은 규율을 씁니다.
if (typeof document !== 'undefined') {
  const host = document.getElementById('wk-host');
  if (host) {
    import('../config.js').then(({ API_BASE }) => {
      // A pick walks again on the page; the address follows, so a reload opens the same worlds.
      boot(document, host, { apiBase: API_BASE, world: new URL(location.href).searchParams.getAll('world'),
        branchMount: document.getElementById('wk-branch'),
        pickWorld: (names) => { history.replaceState(history.state, '', addressFor(location.href, names)); } });
    });
  }
}
