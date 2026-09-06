// 걷기 검색 — 「걷기 API 에 «폼 채워서 날려 보는» 자리」 (소유자 주문 그대로).
//
// 🔴 탐색기가 «아닙니다». 마킹 저장소도, 이력 나무도, 줍기(collect) 체인도 없습니다 —
//    총괄이 그것을 명시적으로 거뒀습니다. 여기 있는 것은 인자를 채우는 칸들과 「날리기」
//    하나, 그리고 «응답을 보여 주는 자리»뿐입니다.
//
// ⚠️ R&D 보드의 `WalkBoxPanel` 을 «안 씁니다». 처음에 그것을 앉혔다가 걷어냈습니다:
//    그 부품은 `direction` · `node_limit` 컨트롤이 «없고», `hops` 는 「고르는 값이 아니라
//    고른 경로가 데려오는 값」으로 지어져 있습니다(그 파일이 그렇게 적습니다). 이 주문은
//    셋을 «폼 칸»으로 요구하므로, 그 부품으로는 «고쳐야만» 됩니다 — 그리고 그 파일은
//    R&D 보드 것이라 못 고칩니다. 그래서 이 페이지가 자기 폼을 갖습니다.
//
// 🔴🔴 그런데 «요청을 짓는 것»은 이 페이지 일이 아닙니다 (소유자 2026-09-06, 깔끔 ④:
//    「같은 기능인데 «두 경로»가 있어서도 안 됨」). 오늘 이 저장소가 그 부류로 결함을
//    하나 냈습니다 — 걷기 요청을 짓는 함수가 둘이라 한쪽만 `hops` 를 안 실었고, 화면이
//    「3홉」이라 쓰는 동안 서버는 12홉을 걸었습니다. 오류도 경고도 «0» 이었습니다.
//    => 그래서 이 페이지는 «폼»만 갖고, 요청은 `createWalkBoxWalk` «하나»가 짓습니다.
//       세 번째 저자를 만들지 않습니다.
//
// 🔵 가져다 쓰는 것 둘. 다시 쓰지 않습니다:
//      `fetchDeclaration`    무엇을 고를 수 있나는 «선언»이 답합니다. 화면이 목록을 안 듭니다
//      `createWalkBoxWalk`   전선. 다섯 인자와 응답 키가 «한 자리»에 삽니다
//                            (씨앗 접기도 그 안입니다 — 여기서 base64 를 다시 적지 않습니다)
//
// ⛔ 걷기 API 는 «안 건드립니다» — 소유자 지시. 부르기만 합니다.

import { fetchDeclaration, createWalkBoxWalk, pathsBetween } from '../rnd_board/api.js';
// 🔴 겉모양은 «부품과 같이» 다닙니다 (총괄 판정 2026-09-06). 호스트가 스타일시트를
//    챙기게 하면 호스트가 하나 늘 때마다 챙기기를 «기억»해야 하고, 안 챙기면 맨몸으로
//    뜹니다 — 오류 없이. 그게 기준 ④ 위반입니다.
import { ensureWalkStyles } from './styles.js';
import { bareName, followFromRoute, followChoices, keepWalkableRoutes } from './derive.js';

/** 서버가 받는 값 그대로. 화면이 «자기 이름»을 만들지 않습니다. */
const DIRECTIONS = ['both', 'outgoing', 'incoming'];

// 🔴 손잡이의 기본값을 «여기 안 적습니다». 적으면 서버가 기본을 바꾸는 날 이 화면만
//    옛 수를 보여 주고, 그게 오늘 고친 그 병(값의 저자가 둘)입니다. 비워 두면 «안 실리고»,
//    안 실리면 서버가 정합니다 — 그리고 무엇으로 정해졌는지는 응답의 `walk` 가 말합니다.
const SERVER_DEFAULT = '서버 기본';

const el = (doc, tag, cls, text) => {
  const n = doc.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = String(text);
  return n;
};

/**
 * @param {Document} doc
 * @param {HTMLElement} host
 * @param {{apiBase?: string, fetchImpl?: Function}} [deps]
 */
export function boot(doc, host, deps) {
  const options = deps || {};
  const apiBase = options.apiBase || '';
  // 자기 규칙을 «자기가» 들고 앉습니다. 호스트는 아무것도 안 챙깁니다.
  ensureWalkStyles(doc);
  const walk = createWalkBoxWalk({ apiBase, fetchImpl: options.fetchImpl });

  const state = {
    decl: null, declState: 'loading', declReason: '',
    type: '', keys: {}, follow: new Set(), collect: new Set(),
    direction: '', hops: '', nodeLimit: '',
    run: 'idle', result: null, reason: '',
  };

  // 🔴 `@1` 을 뗍니다. 선언은 타입을 `wafer@1` 로 쓰고 전선과 `pathsBetween` 의 타입 그래프는
  //    `wafer` 로 씁니다 -- 둘을 섞으면 경로가 «0 개»로 나오고, 그 0 은 「길이 없다」와
  //    구별이 안 됩니다. 술어에서도 «같은 함정»이라, 그 규칙은 `derive.js` 한 곳에 삽니다.
  const bare = bareName;

  const entities = () => (state.decl && state.decl.entities) || [];
  const keysOf = (type) => {
    const found = entities().find((e) => e.type === type);
    return (found && found.keys) || [];
  };
  // 🔴 술어도 «선언»에서, 그리고 «고른 타입을 주어로 갖는 것»만. 이것이 사람이 배관 낱말을
  //    몰라도 되는 이유입니다 — 고를 수 있는 것만 보입니다.
  const allPredicates = () => ((state.decl && state.decl.predicates) || []).map((p) => p.name);
  const followOptions = () => {
    const all = (state.decl && state.decl.predicates) || [];
    if (!state.type) return all.map((p) => p.name);
    const fromHere = all.filter((p) => (p.subjects || []).includes(state.type)).map((p) => p.name);
    // 규칙과 그 사유는 `derive.js` 에 있습니다 — 하니스가 «그 함수»를 재기 때문입니다.
    return followChoices(fromHere, allPredicates(), state.follow);
  };

  /**
   * 시작 타입에서 «고른 도착지»까지 선언이 아는 길. 지어내지 않고 `pathsBetween` 을 씁니다 --
   * 그 함수가 `{hops, follow, chain}` 을 이미 돌려주고, 같은 follow 를 가진 것은 «가장 짧은
   * 홉»으로 접어 줍니다.
   * 🔴 도착지마다 «따로» 냅니다. 합치면 「defect 로 가는 길」과 「die 로 가는 길」이 한 줄에
   *    섞여, 누른 사람이 «무엇을 향한 길»을 골랐는지 알 수 없게 됩니다.
   */
  function routes() {
    if (!state.decl || !state.type || !state.collect.size) return [];
    const out = [];
    for (const to of state.collect) {
      for (const r of pathsBetween(state.decl, bare(state.type), bare(to))) {
        out.push({ ...r, to: bare(to) });
      }
    }
    // 🔴 걷기가 «거절할» 길은 내놓지 않습니다. 규칙과 사유는 `derive.js` 에 있습니다.
    const walkable = keepWalkableRoutes(entities(), out);
    return walkable.sort((a, b) => a.hops - b.hops || a.follow.length - b.follow.length);
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

  async function fire() {
    if (!state.type) return;
    state.run = 'running'; state.result = null; state.reason = ''; render();
    const res = await walk(spec());
    if (res && res.ok) { state.run = 'done'; state.result = res; }
    else {
      // ⚠️ 실패도 «보여야» 합니다. 빈 화면은 「안 눌렸나」와 구별이 안 됩니다.
      state.run = 'failed';
      state.reason = (res && res.message) || '알 수 없음';
    }
    render();
  }

  function field(label) {
    const box = el(doc, 'div', 'wk-field');
    box.append(el(doc, 'div', 'wk-label', label));
    return box;
  }

  function renderForm(root) {
    // ── 씨앗: 타입 ──────────────────────────────────────────────────────────────
    const typeBox = field('노드 타입');
    const sel = el(doc, 'select', 'wk-select');
    sel.append(el(doc, 'option', '', '— 고르십시오 —'));
    for (const e of entities()) {
      const o = el(doc, 'option', '', e.type);
      o.value = e.type;
      if (e.type === state.type) o.selected = true;
      sel.append(o);
    }
    sel.addEventListener('change', () => {
      state.type = sel.value;
      // 타입을 바꾸면 그 타입에 «없는» 키와 술어는 따라올 자격이 없습니다.
      const allowedKeys = new Set(keysOf(state.type));
      state.keys = Object.fromEntries(
        Object.entries(state.keys).filter(([k]) => allowedKeys.has(k)));
      const allowed = new Set(followOptions());
      state.follow = new Set([...state.follow].filter((f) => allowed.has(f)));
      state.result = null; state.run = 'idle';
      render();
    });
    typeBox.append(sel);
    root.append(typeBox);

    // ── 씨앗: 키 ────────────────────────────────────────────────────────────────
    const keyBox = field('키');
    const keys = keysOf(state.type);
    if (!state.type) keyBox.append(el(doc, 'div', 'wk-note', '타입을 고르면 키가 나옵니다'));
    else if (!keys.length) keyBox.append(el(doc, 'div', 'wk-note', '이 타입은 키가 없습니다'));
    for (const k of keys) {
      const row = el(doc, 'label', 'wk-keyrow');
      row.append(el(doc, 'span', 'wk-keyname', k));
      const input = el(doc, 'input', 'wk-input');
      input.type = 'text';
      input.value = state.keys[k] === undefined ? '' : state.keys[k];
      input.addEventListener('input', () => { state.keys[k] = input.value; });
      row.append(input);
      keyBox.append(row);
    }
    root.append(keyBox);

    // ── collect: «무엇을 가져오나» ────────────────────────────────────────────
    //
    // 🔴 목록이 시작 타입 드롭다운과 «같은 선언»에서 나옵니다. 사람이 배관 낱말(point ·
    //    collection · claim …)을 몰라도 되는 이유가 그것입니다 -- 고를 수 있는 것만 보입니다.
    // 🔵 체크박스입니다. 이 화면의 «여럿 고르기»는 이미 follow 가 체크박스라, 여기만 다중 선택
    //    드롭다운을 쓰면 같은 일을 하는 컨트롤이 «두 모양»이 됩니다. 그리고 ctrl+클릭 다중
    //    선택은 「하나 누르면 나머지가 풀리는」 사고가 나는 자리입니다.
    const collectBox = field('collect · 무엇을 가져오나');
    const types = entities().map((e) => e.type);
    if (!types.length) collectBox.append(el(doc, 'div', 'wk-note', '선언에 엔터티 없음'));
    for (const t of types) {
      const row = el(doc, 'label', 'wk-check' + (state.collect.has(t) ? ' is-on' : ''));
      row.setAttribute('data-collect', t);
      const cb = el(doc, 'input');
      cb.type = 'checkbox';
      cb.checked = state.collect.has(t);
      cb.addEventListener('change', () => {
        if (state.collect.has(t)) state.collect.delete(t); else state.collect.add(t);
        render();
      });
      row.append(cb, el(doc, 'span', '', t));
      collectBox.append(row);
    }
    if (types.length) collectBox.append(el(doc, 'div', 'wk-note', `안 고르면 ${SERVER_DEFAULT} · 전부`));
    root.append(collectBox);

    // ── 경로: 시작과 도착지가 정해지면 선언이 «길을 알려 줍니다» ──────────────────
    //
    // 🔴 채워 주는 것이지 «뺏는 게 아닙니다». 누르면 아래 follow 체크와 hops 가 채워지고,
    //    그다음 손으로 고쳐도 됩니다 -- 도출은 출발점이지 잠금이 아닙니다.
    if (state.type && state.collect.size) {
      const pathBox = field('경로 · 선언이 아는 길');
      const found = routes();
      if (!found.length) {
        // 「길이 없다」는 답입니다. 빈 칸으로 두면 「아직 안 셌다」와 같아 보입니다.
        pathBox.append(el(doc, 'div', 'wk-note',
          `${bare(state.type)} 에서 ${[...state.collect].map(bare).join(' · ')} 로 가는 길 없음`));
      }
      for (const r of found) {
        const row = el(doc, 'button', 'wk-path');
        row.type = 'button';
        row.append(el(doc, 'span', 'wk-pathto', `→ ${r.to}`));
        row.append(el(doc, 'span', 'wk-pathchain', r.chain.join(' → ')));
        row.append(el(doc, 'span', 'wk-pathmeta', `${r.hops}홉 · ${r.follow.join(', ')}`));
        row.addEventListener('click', () => {
          // 채우는 두 줄. 규칙은 `derive.js` 에 있고, 지우면 그쪽 하니스가 빨개집니다.
          state.follow = new Set(followFromRoute(allPredicates(), r.follow));
          state.hops = String(r.hops);
          render();
        });
        pathBox.append(row);
      }
      root.append(pathBox);
    }

    // ── follow ────────────────────────────────────────────────────────────────
    const followBox = field('follow · 어느 길로');
    const opts = followOptions();
    if (!opts.length) {
      followBox.append(el(doc, 'div', 'wk-note', state.type
        ? `${state.type} 에서 나가는 술어 없음`
        : '선언에 술어 없음'));
    }
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
      followBox.append(row);
    }
    if (opts.length) followBox.append(el(doc, 'div', 'wk-note', `안 고르면 ${SERVER_DEFAULT}`));
    root.append(followBox);

    // ── 손잡이 셋. 비면 «안 갑니다» — 그 상태를 칸이 «말합니다» ────────────────────
    const knobs = field('걸음');
    const dirRow = el(doc, 'label', 'wk-keyrow');
    dirRow.append(el(doc, 'span', 'wk-keyname', 'direction'));
    const dir = el(doc, 'select', 'wk-select');
    dir.append(el(doc, 'option', '', SERVER_DEFAULT));
    for (const d of DIRECTIONS) {
      const o = el(doc, 'option', '', d);
      o.value = d;
      if (d === state.direction) o.selected = true;
      dir.append(o);
    }
    dir.addEventListener('change', () => { state.direction = dir.value; });
    dirRow.append(dir);
    knobs.append(dirRow);
    for (const [name, key, min, max] of [['hops', 'hops', 1, 40],
                                         ['node_limit', 'nodeLimit', 10, 5000]]) {
      const row = el(doc, 'label', 'wk-keyrow');
      row.append(el(doc, 'span', 'wk-keyname', name));
      const input = el(doc, 'input', 'wk-input');
      input.type = 'number';
      input.min = String(min); input.max = String(max);
      input.placeholder = SERVER_DEFAULT;
      input.value = state[key];
      input.addEventListener('input', () => { state[key] = input.value; });
      row.append(input);
      knobs.append(row);
    }
    root.append(knobs);

    // ── 날리기 ────────────────────────────────────────────────────────────────
    const go = el(doc, 'button', 'wk-go', state.run === 'running' ? '걷는 중' : '날리기');
    go.type = 'button';
    go.disabled = !state.type || state.run === 'running';
    go.addEventListener('click', fire);
    root.append(go);
  }

  function renderResult(root) {
    if (state.run === 'idle') return;
    const box = el(doc, 'div', 'wk-result');
    if (state.run === 'running') { box.append(el(doc, 'div', 'wk-note', '걷는 중')); }
    else if (state.run === 'failed') {
      // 🔴 사유를 «서버의 말»로. 여기서 다시 쓰면 같은 거절이 두 화면에서 달라집니다.
      const line = el(doc, 'div', 'wk-fail');
      line.append(el(doc, 'b', '', '실패'), el(doc, 'span', '', ' · ' + state.reason));
      box.append(line);
    } else if (state.result) {
      const r = state.result;
      box.append(el(doc, 'div', 'wk-counts',
        `노드 ${r.nodes.length} · 엣지 ${r.edges.length}`));
      // 🔴 몇 홉을 «실제로» 걸었나. 요청한 수와 다르면 그 자체가 답입니다 —
      //    예산에서 끊겼거나, 그 방향으로 더 갈 것이 없었거나.
      if (r.walk) {
        box.append(el(doc, 'div', 'wk-walk',
          `요청 ${r.walk.hops_requested}홉 · 도달 ${r.walk.hops_reached}홉`
          + ` · ${r.walk.direction}`));
      }
      // ⚠️ 절단은 «말합니다». 안 말하면 잘린 목록이 「전부」로 읽힙니다.
      if (r.cut) {
        box.append(el(doc, 'div', 'wk-trunc', `절단됨 · ${r.truncated.reason}`));
      }
      // 🔴 타입 분포 — 「collect 가 «먹었나»」가 «눈에» 보이는 자리입니다. 수만 보면
      //    collect 를 건 것과 안 건 것이 같아 보입니다: 둘 다 「노드 N」이니까요.
      //    ⚠️ 여기서 «거르지 않습니다». 세기만 합니다 -- 거르는 것은 walk 의 일이고,
      //       화면이 거르면 「서버가 무엇을 줬나」를 영영 못 봅니다.
      if (r.nodes.length) {
        const byType = new Map();
        for (const n of r.nodes) {
          const t = n.type || '—';
          byType.set(t, (byType.get(t) || 0) + 1);
        }
        const dist = el(doc, 'div', 'wk-dist');
        dist.append(el(doc, 'span', 'wk-distlabel', '타입'));
        for (const [t, n] of [...byType.entries()].sort((a, b) => b[1] - a[1])) {
          const chip = el(doc, 'span', 'wk-distchip' + (state.collect.has(t) || state.collect.has(`${t}@1`) ? ' is-asked' : ''));
          chip.append(el(doc, 'b', '', t), el(doc, 'span', '', ` ${n}`));
          dist.append(chip);
        }
        box.append(dist);
      }
      // 🔴 「닿은 것이 없다」는 «실패가 아닙니다». 서버가 그 문장을 들고 오므로 그것을 씁니다.
      if (!r.nodes.length) {
        box.append(el(doc, 'div', 'wk-note', r.message || '닿은 노드 없음'));
      }
      for (const n of r.nodes.slice(0, 200)) {
        const row = el(doc, 'div', 'wk-row');
        row.append(el(doc, 'span', 'wk-rowtype', n.type || '—'));
        row.append(el(doc, 'span', 'wk-rowlabel', n.label || n.id || ''));
        box.append(row);
      }
      if (r.nodes.length > 200) {
        box.append(el(doc, 'div', 'wk-note', `이 아래 ${r.nodes.length - 200} 개 안 그림`));
      }
    }
    root.append(box);
  }

  function render() {
    host.textContent = '';
    const root = el(doc, 'div', 'wk-form');
    if (state.declState === 'loading') {
      root.append(el(doc, 'div', 'wk-note', '선언 · 읽는 중'));
    } else if (state.declState === 'failed') {
      // 「못 읽음」과 「없음」은 다릅니다 — 앞은 다시 눌러 볼 수 있습니다.
      const line = el(doc, 'div', 'wk-fail');
      line.append(el(doc, 'b', '', '선언 못 읽음'), el(doc, 'span', '', ' · ' + state.declReason));
      const again = el(doc, 'button', 'wk-go', '다시');
      again.type = 'button';
      again.addEventListener('click', load);
      root.append(line, again);
    } else {
      renderForm(root);
      renderResult(root);
    }
    host.append(root);
  }

  async function load() {
    state.declState = 'loading'; render();
    const got = await fetchDeclaration({ apiBase, fetchImpl: options.fetchImpl });
    if (got && got.ok) { state.decl = got; state.declState = 'ready'; }
    else { state.declState = 'failed'; state.declReason = (got && got.message) || '알 수 없음'; }
    render();
  }

  load();
  return { state, spec, fire, render };
}

// 🔴 부팅은 «이 파일 끝»에서만. bare node 로 이 모듈을 읽어도 DOM 을 안 건드려야
//    하니스가 붙을 수 있습니다 — R&D 보드 main.js 가 같은 규율을 씁니다.
if (typeof document !== 'undefined') {
  const host = document.getElementById('wk-host');
  if (host) {
    import('../config.js').then(({ API_BASE }) => {
      boot(document, host, { apiBase: API_BASE });
    });
  }
}
