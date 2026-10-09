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

import { fetchDeclaration, createWalkBoxWalk, routeWith, fetchKeyValues, PICK_TYPE_FIRST }
  from '../rnd_board/api.js';
// 🔴 겉모양은 «부품과 같이» 다닙니다 (총괄 판정 2026-09-06).
import { ensureWalkStyles } from './styles.js';
import {
  followFromRoute, followChoices, walkableRoutes,
  cutBudgets, stepAlong,
} from './derive.js';
// 🔴 C-72. 표의 «결정»은 전부 여기 있고 이 파일에는 DOM 쓰기만 남습니다.
import { walkTableView, nextRoutes } from './table_view.js';
// 🔴 C-120. 「꺼짐 + 왜」의 좌석 하나 — 메인 그리드의 쓰기 버튼 셋이 쓰던 그 기제입니다.
import { setDisabledReason } from '../disabled_reason.js';
// The graph view of a start (lead c9bf53033) — a part with its own div; this page only places it.
import { SubgraphView, seedsOf } from './subgraph_view.js';
// The markings live outside every part, in one store (lead f6fc6ba66 · the board's MarkingStore).
import { MarkingStore, SIGN } from '../rnd_board/marking_store.js';
import { entitySeedId } from '../rnd_board/api.js';
import { markingIntent } from '../rnd_board/panel.js';
// The words other screens already draw for the same facts, spelled once.
import { CHOOSE, FAILED, LOADING, WALKING, unitText } from '../ui_words.js';
import { UNKNOWN, UNPICKED } from '../absent.js';
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
    subjects: null, subjectsState: 'idle', subjectsReason: '',
    subjectsScanned: null, subjectsScanCut: false, subjectsListCut: false,
    direction: '', hops: '', nodeLimit: '',
    run: 'idle', result: null, reason: '',
    // What the shown result was asked with - the form can change after the walk.
    asked: null,
    view: 'table',
    // Which loop chips are on, per route row (`routeKey`). Off unless pressed (lead 5d5b8d750).
    loopsOn: new Map(),
    // The table's steps after the form's walk, each from the rows checked along one edge (lead 53050a4ec), and
    // which one is shown: 0 is the form's walk.
    steps: [],
    at: 0,
    // The start marking's names, as the form spelled each subject when its Walk put it there.
    startLabels: new Map(),
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
  /** The Walk press puts the form's subject in the chain's first marking the way the board marks (lead 10-09): a press
   *  replaces, Ctrl adds, Shift makes it a control. No subject, no mark (the part says so). */
  const markStart = (event) => {
    if (!Object.keys(state.keys || {}).length) { markings.replace(GRAPH_CHAIN[0], []); return; }
    const intent = markingIntent(event);
    const seed = entitySeedId(state.type, state.keys);
    state.startLabels.set(seed, Object.values(state.keys).join(' · '));
    if (intent.mode === 'add') markings.set(GRAPH_CHAIN[0], seed, intent.sign);
    else markings.replace(GRAPH_CHAIN[0], [[seed, intent.sign]]);
  };
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
    const hops = parseInt(state.hops, 10);
    if (Number.isFinite(hops)) out.hops = hops;
    const limit = parseInt(state.nodeLimit, 10);
    if (Number.isFinite(limit)) out.node_limit = limit;
    return out;
  }

  async function fire(event) {
    if (!state.type) return;
    markStart(event);
    await walkStarts();
  }

  /** The walk from the start marking as it stands - a Walk press, and a world picked (lead 10-09). */
  async function walkStarts() {
    // The graph walks its marking and nothing else - follow, collect and the knobs are the table's.
    if (state.view === 'graph') { showGraph(); return; }
    // The table walks the same signed starts: + as positive, - as negative (the wire takes the first + as the seed).
    // One + start alone is the form's subject, asked as before (walk_layout L7 · L8: the request does not change).
    const starts = seedsOf(markings.entries(GRAPH_CHAIN[0]));
    const signed = starts.positive.length > 0 && (starts.positive.length > 1 || starts.negative.length > 0);
    const asked = { ...spec(), ...(signed ? starts : {}) };
    state.run = 'running'; state.result = null; state.reason = '';
    state.asked = { ...asked, keys: { ...asked.keys } };
    // A new start clears the steps and what their checks wrote, as the graph's new start does (lead 53050a4ec).
    state.steps = []; state.at = 0;
    for (const name of GRAPH_CHAIN.slice(1)) markings.clear(name);
    render();
    const res = await walk(asked);
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
    ? { run: state.run, result: state.result, reason: state.reason }
    : state.steps[state.at - 1]);

  /** From the rows checked on step `at` (+ and -), one step along `route`; it stands after `at`, the steps beyond it go. */
  async function walkOn(at, seeds, route) {
    const asked = stepAlong({ positive: seeds.positive, negative: seeds.negative, predicate: route.predicate, farType: route.to });
    const step = { title: `${route.predicate} → ${route.to}`, asked, run: 'running', result: null, reason: '' };
    state.steps = [...state.steps.slice(0, at), step];
    state.at = at + 1;
    for (const name of GRAPH_CHAIN.slice(at + 2)) markings.clear(name);
    render();
    const res = await walk(asked);
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
      loadSubjects();
    });
    start.append(cell('Type', sel, 'wk-cell wk-cell-row'));

    // 🔴 고르는 것은 «키 하나의 값»이 아니라 «노드 하나»입니다. 한 번 고르면 아래 키 칸이
    //    «전부» 찹니다 — 칸마다 따로 고르게 하면 «그 조합은 없는» 씨앗을 만들 수 있습니다.
    // 🔵 직접 입력은 «남습니다» — 목록이 상한에 걸릴 수 있습니다.
    if (state.type) {
      const subjBox = field('Pick a node', 'wk-sub');
      if (state.subjectsState === 'loading') {
        subjBox.append(el(doc, 'div', 'wk-note', LOADING));
      } else if (state.subjectsState === 'failed') {
        subjBox.append(el(doc, 'div', 'wk-fail', `Node list · ${state.subjectsReason}`));
      } else if (state.subjectsState === 'ready') {
        const list = state.subjects || [];
        if (!list.length) {
          // 🔴 「봤는데 없다」와 「다 못 봤다」는 다릅니다. N 은 응답의 `scanned` — 읽은 «노드» 수입니다.
          subjBox.append(el(doc, 'div', 'wk-note', state.subjectsScanCut
            ? `Not every node read (up to ${state.subjectsScanned})`
            : 'No node of this type in the ledger'));
        } else {
          const ssel = el(doc, 'select', 'wk-select');
          ssel.append(el(doc, 'option', '', '— pick, or type the keys below —'));
          list.forEach((s, i) => {
            const vals = Object.values(s.keys || {}).map((v) => String(v)).join(' · ');
            const o = el(doc, 'option', '', s.count ? `${vals}  (${s.count})` : vals);
            o.value = String(i);
            ssel.append(o);
          });
          ssel.addEventListener('change', () => {
            const picked = list[Number(ssel.value)];
            if (!picked) return;
            // 통째로 갈아 끼웁니다 — 앞서 손으로 친 값이 «섞이면» 그것이 없는 조합입니다.
            state.keys = { ...picked.keys };
            render();
          });
          subjBox.append(ssel);
          if (state.subjectsListCut) {
            subjBox.append(el(doc, 'div', 'wk-note',
              `${unitText(list.length, 'node')} listed · not all · type the keys below if missing`));
          }
        }
      }
      start.append(subjBox);
    }

    const keys = keysOf(state.type);
    if (!state.type) start.append(el(doc, 'div', 'wk-note', 'Pick a type for its keys'));
    else if (!keys.length) start.append(el(doc, 'div', 'wk-note', 'This type has no keys'));
    const grid = el(doc, 'div', 'wk-keys');
    for (const k of keys) {
      const input = el(doc, 'input', 'wk-input');
      input.type = 'text';
      input.value = state.keys[k] === undefined ? '' : state.keys[k];
      input.addEventListener('input', () => { state.keys[k] = input.value; });
      grid.append(cell(k, input));
    }
    if (keys.length) start.append(grid);
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
      row.append(el(doc, 'span', 'wk-pathchain', r.chain.join(' → ')));
      row.append(el(doc, 'span', 'wk-pathmeta', `${unitText(asked.hops, 'hop')} · ${asked.follow.join(', ')}`));
      row.addEventListener('click', () => useRoute(r, loopsOf(r)));
      route.append(row);
      // The route's self-loops: pressing one adds it to this route and uses the route.
      if (r.loops.length) {
        const chips = el(doc, 'div', 'wk-loops');
        chips.append(el(doc, 'span', 'wk-note', 'self-loops'));
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
    for (const [name, key, min, max] of [['hops', 'hops', 1, 40],
                                         ['node_limit', 'nodeLimit', 10, 5000]]) {
      const input = el(doc, 'input', 'wk-input');
      input.type = 'number';
      input.min = String(min); input.max = String(max);
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
    // 🔴 C-120. 꺼진 이유가 «둘»입니다. 「걷는 중」은 라벨과 «같은 상수»이고, 타입이 없을 때의
    //    문장은 이 화면의 전선이 같은 사실에 이미 쓰는 말(`PICK_TYPE_FIRST`)입니다.
    setDisabledReason(go, state.run === 'running'
      ? RUNNING
      : (state.type ? '' : PICK_TYPE_FIRST));
    go.addEventListener('click', fire);
    root.append(go);
    // The signed starts the walk goes from: Ctrl+Walk adds the subject, Shift+Walk makes it a control (lead 10-09).
    const starts = markings.entries(GRAPH_CHAIN[0]);
    if (starts.length) {
      const line = el(doc, 'div', 'wk-starts');
      line.append(el(doc, 'span', 'wk-label', 'Starts'));
      for (const [id, sign] of starts) {
        const control = sign === SIGN.CONTROL;
        line.append(el(doc, 'span', control ? 'wk-start is-control' : 'wk-start',
          `${control ? '−' : '+'} ${state.startLabels.get(id) || id}`));
      }
      root.append(line);
    }
  }

  /**
   * 응답을 «표»로. 행은 «노드 하나»이고, 타입이 여럿이면 구획으로 나뉩니다.
   * 🔴 C-72. 이 함수는 «아무것도 정하지 않습니다» — 구획도 컬럼도 셀 글자도 못 그린 수도
   *    `walkTableView` 가 답하고, 여기서는 그 답을 DOM 으로 옮기기만 합니다.
   */
  function renderTable(box, r) {
    // C-98. 선언의 술어 목록이 «같이» 갑니다 — 확인 술어를 이름 대는 것은 선언입니다.
    const view = walkTableView(r, entities(), (state.decl && state.decl.predicates) || []);
    const at = state.at;
    const checks = checksOf(at);
    for (const section of view.sections) {
      const sec = el(doc, 'div', 'wk-sec');
      sec.append(el(doc, 'div', 'wk-sechead', section.heading));

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
        if (checks) {
          const td = el(doc, 'td', 'wk-check');
          const cb = el(doc, 'input');
          cb.type = 'checkbox';
          cb.setAttribute('data-row', row.id);
          const sign = markings.signOf(checks, row.id);
          cb.checked = sign !== SIGN.ABSENT;
          if (sign === SIGN.CONTROL) tr.className = 'is-control';
          // A click, for its Shift: a checked row is a control with it, as the board marks (lead 10-09).
          cb.addEventListener('click', (event) => { markings.toggle(checks, row.id, markingIntent(event).sign); render(); });
          td.append(cb);
          tr.append(td);
        }
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
      if (checks) sec.append(nextRow(at, section, checks));
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

  /** What the shown walk asked: the start's type and key values, and the types it collects. */
  function askedTitle(asked) {
    const values = Object.values(asked.keys || {}).map((v) => String(v)).filter((v) => v).join(' · ');
    const to = (asked.collect || []).join(', ');
    return `${asked.type || ''}${values ? ' ' + values : ''}${to ? ' → ' + to : ''}`;
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
      head.append(el(doc, 'span', 'wk-counts', asked
        ? `Nodes ${r.nodes.length} (collect: ${asked}) · Edges ${r.edges.length} (all)`
        : `Nodes ${r.nodes.length} · Edges ${r.edges.length}`));
    }
    // ── Table | Graph ───────────────────────────────────────────────────────
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
      // 🔴 「닿은 것이 없다」는 «실패가 아닙니다». 서버가 그 문장을 들고 오므로 그것을 씁니다.
      if (!r.nodes.length) {
        box.append(el(doc, 'div', 'wk-note', r.message || 'No node reached'));
      }
      renderTable(box, r);
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
    host.append(rail, main);
  }

  async function loadSubjects() {
    if (!state.type) { state.subjectsState = 'idle'; state.subjects = null; return; }
    const forType = state.type;
    state.subjectsState = 'loading'; state.subjects = null; render();
    const got = await fetchKeyValues({ apiBase, fetchImpl, type: forType });
    // 타입이 그새 바뀌었으면 «옛 답»을 앉히지 않습니다.
    if (state.type !== forType) return;
    if (got && got.ok) {
      state.subjectsState = 'ready';
      state.subjects = got.nodes;
      state.subjectsScanned = got.scanned;
      state.subjectsScanCut = got.scanTruncated;
      state.subjectsListCut = got.valuesTruncated;
    } else {
      state.subjectsState = 'failed';
      state.subjectsReason = (got && got.message) || UNKNOWN;
    }
    render();
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
    if (state.type && (state.run !== 'idle' || markings.count(GRAPH_CHAIN[0]))) await walkStarts();
  }

  const picker = options.branchMount
    ? new BranchPicker(options.branchMount, { doc, onPickSet: (names) => { void pickWorlds(names); } }) : null;
  if (picker) picker.show({ current: worlds });
  load();
  return { state, spec, fire, render, graph };
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
