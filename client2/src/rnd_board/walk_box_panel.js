// ═══════════════════════════════════════════════════════════════════════════════
// 걷기 검색창 — walk 의 네 칸을 «사람이 그 자리에서» 고르는 손잡이판.
//
// 소유자: 「걷기 API 사용 위한 검색창. 검색창에는 NODE TYPE과 KEY, FOLLOW 리스트, COLLECT
//         대상으로 모든 요소는 현재 걸린 필터 수준에 따라 드롭다운 리스트를 제안할것」
//         「결과는 COLLECT된 RETURN으로 보여줘」
//
// 🔴 새 축이 아닙니다. 다른 부품이 «선언»으로 들고 태어나는 그 칸들(start·follow)을,
//    이 부품은 사람이 고르게 할 뿐입니다. 그래서 걷기 API 도 하나입니다 -- 늘어야 하는 것은
//    선언이지 갈래가 아닙니다(소유자 상설).
//
// 🔴 「필터 수준에 따라 제안」의 기전은 «서버의 `subjects`»입니다. 클라가 규칙을 만들지
//    않습니다: NODE TYPE 을 고르면 FOLLOW 는 그 타입을 `subjects` 에 가진 술어만 남는데,
//    그건 선언이 이미 답에 실어 보낸 사실입니다. 실측(총괄 2026-08-26):
//      die@1 -> transfer · observed · bonded_from      wafer@1 -> inspected · processed_with · register
//      lot@1 -> derived_from · register                recipe@1 -> «없음»
//    🔴 `recipe@1` 이 이 부품의 시금석입니다 -- 목적어로만 나오는 타입이라 나가는 술어가
//       없습니다. 그때 «문장»으로 말해야 합니다. 빈 드롭다운은 「고장」과 구별이 안 됩니다.
//
// 🔴 부재는 «셋»이고 문장도 셋입니다. 한 낱말로 합치면 화면에서 못 읽습니다:
//      ① 아직 안 골랐다              ② 서버가 아직 답을 못 준다      ③ 걸었는데 없다
//    ②에는 「라우트가 아직 없다」도 들어갑니다. 이 부품이 쓰이기 시작하는 날
//    `GET /api/ledger/declaration` 이 아직 없을 수 있고, 그때 화면은 «그렇게» 말해야 합니다.
//
// ── 주입되는 것 둘, 그리고 그 «모양» ────────────────────────────────────────────
//   loadDeclaration()  -> { ok, entities:[{type,keys[]}], predicates:[{name,subjects[]}],
//                           message? }
//   walk({ type, keys, follow })
//                      -> { ok, nodes:[{id,type,label}], message? }
// 🔴 «한 모양»입니다. 어떤 호출은 body 를 그냥 주고 어떤 호출은 {ok,body} 로 감싸면, 섞이는
//    자리에서 오류 없이 «빈 값»이 나옵니다. 라우트를 이 모양에 맞추는 것은 조립하는 쪽 일이고,
//    부품은 라우트를 모릅니다.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel } from './panel.js';
import { SIGN } from './marking_store.js';
import { TablePart } from './table_part.js';
import { typeGraph, pathsBetween } from './api.js';
import { UNPICKED } from '../absent.js';
// 🔴 C-70. 구획과 컬럼을 «걷기 페이지와 같은 함수»에서 받습니다. 이 파일이 컬럼 셋을 자기
//    소스에 적고 있던 동안 두 걷기 표는 «갈라질 수» 있었고, 갈라져도 오류가 안 납니다.
import { sectionsByType, sectionHeading, tableColumns, cellSource, pluralAttributes, COLUMNS }
  from '../walk/derive.js';

/** `wafer@1` -> `wafer`. 선언은 버전을 달고 타입 그래프는 안 답니다. */
function bareTypeName(value) {
  return String(value || '').split('@')[0];
}

export class WalkBoxPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    this.loadDeclaration = options.loadDeclaration || null;
    this.walkFn = options.walk || null;

    this.declaration = null;
    this.declState = 'idle';

    // 고른 것 -- 전부 per-instance 입니다. 같은 화면의 둘이 다른 타입을 들 수 있어야 합니다.
    this.nodeType = options.nodeType || null;
    this.keyValues = {};
    this.follow = new Set();
    // 🔴 C-51. 구간은 «둘 다 선택»이고 빈 칸이 「구간 없음」입니다 — 그래서 기본값이 빈
    //    문자열이지 `null` 도 오늘 날짜도 아닙니다. 채우면 그것이 질문이고, 비우면 «안 묻습니다».
    this.since = '';
    this.until = '';

    this.result = null;
    this.walkState = 'idle';

    // ═══════════════════════════════════════════════════════════════════════════
    // 탐색 이력 — 「마킹은 «값»이고 탐색은 그 값의 «나무»다」 (라운드 W, 소유자 설계)
    //
    // 🔴 나무이고 «자르지 않습니다». 뒤로 갔다 다른 데로 가도 먼저 갈래가 «남습니다» --
    //    소유자 손그림이 그렇고 파일 탐색기가 그렇습니다. 브라우저식으로 자르면 「돌아가서
    //    다른 길」이 «먼저 길을 지웁니다».
    //
    // 🔴 쓰는 곳은 `goto` «하나»입니다. 다른 어떤 경로도 저장소에 안 씁니다 -- 그래서
    //    「무엇이 마킹을 바꿨나」의 답이 언제나 한 줄입니다.
    //
    // 🔴 «무한 루프가 플래그로 막히지 않습니다». goto 직후에는 저장소 값 == nodes[current].value
    //    이므로 아래 구독의 「밖에서 바뀌었나」가 «값 비교»로 자동으로 거짓이 됩니다.
    //    `replace` 가 같은 값에 emit 을 «안 하는» 것이 이 성질의 전제입니다 (실측 2026-08-28).
    // ═══════════════════════════════════════════════════════════════════════════
    this.nodes = new Map();
    this.current = null;
    this._seq = 0;
    this._historyOff = null;
  }

  /** 이 인스턴스가 «쓰는» 이름. 선언에 없으면 이력은 서지 않습니다 (읽기 전용 인스턴스). */
  historyName() {
    return this.writes || null;
  }

  /** `[[nodeId, sign], ...]` 두 개가 같은 마킹인가. 순서는 뜻이 아니므로 정렬해서 봅니다. */
  static sameValue(a, b) {
    const norm = (v) => (v || []).map(([id, sign]) => `${id}${sign}`).sort().join('');
    return norm(a) === norm(b);
  }

  /** 이력의 한 칸으로 «이동». 저장소에 쓰는 곳은 여기뿐입니다. */
  goto(id) {
    const node = this.nodes.get(id);
    if (!node || !this.markings) return;
    this.current = id;
    this.markings.replace(this.historyName(), node.value);
    this.render();
  }

  /** 자식 한 칸을 «추가»하고 그리로 이동. 먼저 있던 형제는 그대로 남습니다. */
  push(value) {
    const name = this.historyName();
    if (!name) return null;
    this._seq += 1;
    const id = `h${this._seq}`;
    this.nodes.set(id, { value: (value || []).map(([n, s]) => [n, s]), parent: this.current });
    this.goto(id);
    return id;
  }

  /** 클릭 = «이동». 마킹이 그 노드 «하나»가 됩니다. */
  moveTo(nodeId) {
    this.push([[nodeId, SIGN.CASE]]);
  }

  /** 찍기 = «수집». 지금 값에 한 노드를 더하거나 뺍니다. */
  collect(nodeId, sign) {
    const now = (this.nodes.get(this.current) || {}).value || [];
    const next = now.filter(([id]) => id !== nodeId);
    if (sign !== SIGN.ABSENT) next.push([nodeId, sign]);
    this.push(next);
  }

  /** 이 칸의 형제들 -- 「다른 갈래」가 화면에 서려면 필요합니다. */
  siblingsOf(id) {
    const node = this.nodes.get(id);
    if (!node) return [];
    return [...this.nodes.entries()]
      .filter(([other, n]) => other !== id && n.parent === node.parent)
      .map(([other]) => other);
  }

  mount() {
    super.mount();
    this.loadDecl();
    const name = this.historyName();
    if (name && this.markings) {
      // 🔴 밖에서 바뀌면 «자식으로 붙습니다». 다른 부품이 찍은 것도 탐색의 한 걸음이고,
      //    그래야 「어디서 왔는지」가 이력에 남습니다. goto 가 부른 emit 은 값이 같아서
      //    여기에 «안 걸립니다» -- 그게 재진입 방지의 전부입니다.
      this._historyOff = this.markings.subscribe(name, () => {
        const outside = this.markings.entries(name);
        const here = (this.nodes.get(this.current) || {}).value || null;
        if (here && WalkBoxPanel.sameValue(here, outside)) return;
        if (!here && !outside.length) return;
        this.push(outside);
      });
    }
  }

  unmount() {
    if (this._historyOff) { this._historyOff(); this._historyOff = null; }
    if (super.unmount) super.unmount();
  }

  async loadDecl() {
    if (!this.loadDeclaration) { this.declState = 'idle'; this.render(); return; }
    this.declState = 'loading';
    this.render();
    const got = await this.loadDeclaration();
    this.declaration = got && got.ok ? got : null;
    this.declState = this.declaration ? 'ready' : 'refused';
    this.render();
  }

  /** 선언이 준 타입들. 선언이 없으면 «빈 배열»이지 지어낸 목록이 아닙니다. */
  types() {
    return ((this.declaration && this.declaration.entities) || []).map((e) => e.type);
  }

  /** 🔴 고른 타입의 keys «그대로». 칸을 네 개로 고정하면 타입을 바꿔도 안 따라옵니다. */
  keysOf(type) {
    const found = ((this.declaration && this.declaration.entities) || [])
      .find((e) => e.type === (type === undefined ? this.nodeType : type));
    return (found && found.keys) || [];
  }

  /**
   * 🔴 좁히는 것은 «서버의 subjects» 입니다. 타입을 안 골랐으면 좁힐 근거가 없으므로 전부입니다.
   *    빈 배열이 나오는 것은 «고장이 아니라 답»입니다 -- 목적어로만 나오는 타입이 있습니다.
   */
  followOptions() {
    const all = (this.declaration && this.declaration.predicates) || [];
    if (!this.nodeType) return all.map((p) => p.name);
    return all.filter((p) => (p.subjects || []).includes(this.nodeType)).map((p) => p.name);
  }

  /** 타입을 바꾸면 «그 타입에 없는» 키와 술어는 따라올 자격이 없습니다. */
  setType(type) {
    this.nodeType = type || null;
    const keys = this.keysOf();
    const kept = {};
    for (const k of keys) if (this.keyValues[k] !== undefined) kept[k] = this.keyValues[k];
    this.keyValues = kept;
    const allowed = new Set(this.followOptions());
    this.follow = new Set([...this.follow].filter((f) => allowed.has(f)));
    this.result = null;
    this.walkState = 'idle';
    this.render();
  }

  toggleFollow(name) {
    if (this.follow.has(name)) this.follow.delete(name);
    else this.follow.add(name);
    this.render();
  }

  async run() {
    if (!this.walkFn || !this.nodeType) return;
    this.walkState = 'loading';
    this.render();
    const keys = {};
    for (const [k, v] of Object.entries(this.keyValues)) if (v !== '' && v !== undefined) keys[k] = v;
    const spec = { type: this.nodeType, keys };
    // 🔴 «안 고르면 안 싣습니다». 빈 배열을 실으면 「아무 술어도 따르지 마라」로 읽히고,
    //    서버 기본값(전부)과 «정반대»입니다. 없는 것은 없는 채로 보냅니다.
    // 🔴 «버전을 벗겨서» 보냅니다 (round V, 2026-08-29). 선언은 `inspected@1` 로 부르고 라우트는
    //    `inspected` 만 받습니다 -- 실측: follow=inspected 200 · follow=inspected@1 «422».
    //    체크박스 라벨은 선언의 철자를 그대로 쓰고, 전선에만 벗깁니다. 같은 이음매를 씨앗 id
    //    쪽에서도 이미 그렇게 넘습니다(`entitySeedId` 의 그 줄).
    if (this.follow.size) spec.follow = [...this.follow].map(bareTypeName);
    // 🔴 hops 는 «고르는 값»이 아니라 «고른 경로가 요구하는 값»입니다 (소유자 정정
    //    2026-08-29). 실측: 씨앗 wafer · follow=inspected,observed,of_kind 에서
    //    hops=1 -> defect_kind 0 · hops=2 -> 0 · hops=3 -> «1». 2홉짜리 경로의 hops 로
    //    3홉 경로를 물으면 답이 «0» 인데, 그 0 은 「없다」가 아니라 「못 갔다」입니다 --
    //    화면에서는 «같은 0» 이라 구별이 안 됩니다. 그래서 경로가 hops 를 «데리고» 옵니다.
    if (this.hops) spec.hops = this.hops;
    // 🔴 C-51. 빈 칸은 «구간 없음»입니다 — 안 싣습니다. 그리고 여기서 «거르지 않습니다»:
    //    구간으로 자르는 것은 walk 의 일이고(상설), 부품이 받은 것을 다시 좁히면
    //    「무엇을 못 봤는지」를 화면이 말할 수 없게 됩니다.
    if (this.since) spec.since = this.since;
    if (this.until) spec.until = this.until;
    const got = await this.walkFn(spec);
    this.result = got || null;
    this.walkState = got && got.ok ? 'ready' : 'refused';
    this.render();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    this.host.textContent = '';
    const root = doc.createElement('div');
    root.className = 'rb-walkbox';

    if (this.title) {
      const cap = doc.createElement('div');
      cap.className = 'rb-part-title';
      cap.textContent = this.title;
      root.appendChild(cap);
    }

    if (this.declState !== 'ready') {
      root.appendChild(this._note(this.declState === 'loading'
        ? '선언을 읽는 중…'
        : (this.declState === 'refused'
          // ② -- 라우트 부재도 여기입니다.
          ? ((this.declaration && this.declaration.message)
            || '서버가 아직 선언을 못 줍니다 — 걷기 상자는 그 답 위에 섭니다')
          : '선언을 받지 못했습니다')));
      this.host.appendChild(root);
      return;
    }

    root.appendChild(this._typeRow());
    root.appendChild(this._keyRow());
    root.appendChild(this._destinationRow());
    root.appendChild(this._followRow());
    root.appendChild(this._intervalRow());
    root.appendChild(this._runRow());
    root.appendChild(this._resultBox());
    root.appendChild(this._historyBox());

    this.host.appendChild(root);
  }

  /**
   * 이력 나무. 아무 칸이나 누르면 «그리로 갑니다» -- 파일 탐색기처럼.
   *
   * 🔴 갈래는 «지워지지 않습니다». 뒤로 갔다 다른 데로 가면 «형제»가 되고 둘 다 남습니다.
   *    깊이만큼 들여쓰고, 지금 서 있는 칸을 표시합니다.
   * 🔴 안 그린 인스턴스도 있습니다: 쓸 이름을 선언하지 «않은» 상자는 이력이 «없습니다».
   *    빈 상자를 그리면 「탐색을 했는데 비었다」로 읽히므로 아예 안 그립니다.
   */
  _historyBox() {
    const doc = this.doc;
    const box = doc.createElement('div');
    box.className = 'rb-walkbox-history';
    if (!this.historyName() || !this.nodes.size) return box;
    const head = doc.createElement('div');
    head.className = 'rb-walkbox-history-head';
    head.textContent = `탐색 이력 ${this.nodes.size} · ${this.historyName()}`;
    box.appendChild(head);
    const depthOf = (id) => {
      let n = 0;
      let at = this.nodes.get(id);
      while (at && at.parent) { n += 1; at = this.nodes.get(at.parent); }
      return n;
    };
    for (const [id, node] of this.nodes) {
      const row = doc.createElement('button');
      row.className = 'rb-walkbox-step' + (id === this.current ? ' is-here' : '');
      row.setAttribute('data-step', id);
      row.setAttribute('type', 'button');
      // 값을 «세어서» 보여 줍니다 -- 노드 id 는 길고, 읽는 사람이 아는 것은 「몇 개를 들고 있나」입니다.
      const marks = node.value.length;
      row.textContent = `${'· '.repeat(depthOf(id))}${marks}개${id === this.current ? ' ←' : ''}`;
      row.addEventListener('click', () => this.goto(id));
      box.appendChild(row);
    }
    return box;
  }

  /**
   * 「무엇을 볼지」 고르는 줄. 술어가 아니라 «도착 노드 타입»을 고르고, 경로가 나옵니다.
   *
   * 🔴 자동으로 «안 고릅니다». 길이 여럿이면 경로 A · B · C 로 내놓고 사람이 사슬을 읽습니다 --
   *    실측: wafer -> defect_kind 의 2홉은 「일으킬 수 있는」(추정)이고 3홉은 「관측된」(사실)이라,
   *    짧다고 잡으면 추정을 사실로 내놓습니다.
   * 🔴 이름을 «지어내지 않습니다». 「관측 경로」 같은 라벨은 두 번째 어휘입니다 -- 사슬을 그대로
   *    보여 주고 라벨은 A · B · C 입니다. 이름이 필요하면 «선언»에서 와야 합니다.
   */
  _destinationRow() {
    const doc = this.doc;
    const box = this._field('무엇을 볼까 (도착 타입)');
    const from = bareTypeName(this.nodeType);
    if (!from) {
      box.appendChild(this._note('먼저 시작 타입을 고르십시오'));
      return box;
    }
    const select = doc.createElement('select');
    select.className = 'rb-walkbox-select';
    const none = doc.createElement('option');
    none.setAttribute('value', '');
    none.textContent = '— 술어를 직접 고릅니다 —';
    select.appendChild(none);
    for (const type of this.declaredTypes()) {
      if (type === from) continue;
      const opt = doc.createElement('option');
      opt.setAttribute('value', type);
      opt.textContent = type;
      if (type === this.destination) opt.setAttribute('selected', 'selected');
      select.appendChild(opt);
    }
    select.addEventListener('change', (ev) => {
      this.destination = (ev && ev.target && ev.target.value) || '';
      this.chosenPath = null;
      this.render();
    });
    box.appendChild(select);
    if (!this.destination) return box;
    const routes = this.routes();
    if (!routes.length) {
      // 🔴 「없다」와 「못 봤다」를 가릅니다 -- 이건 데이터가 아니라 «선언»의 사실입니다.
      box.appendChild(this._note(
        `${from} 과 ${this.destination} 은 «선언상» 안 이어집니다`, 'is-absent'));
      return box;
    }
    routes.forEach((route, index) => {
      const row = doc.createElement('button');
      row.setAttribute('type', 'button');
      row.setAttribute('data-route', String(index));
      row.className = 'rb-walkbox-route'
        + (this.chosenPath === index ? ' is-on' : '');
      // 🔴 자기 고리가 있는 경로는 «몇 번 반복하나»가 사용자 축입니다 (소유자 2026-08-29).
      //    지금은 «한 번»으로 걷고, 그것이 «기본값임을 말합니다» -- 말 안 하면 화면이
      //    「한 대 위까지만 봤다」를 「그게 전부다」로 내놓습니다. 오늘의 부재 규율 그대로입니다.
      const loops = route.chain.filter((t, i) => i && t === route.chain[i - 1]).length;
      row.textContent = `경로 ${String.fromCharCode(65 + index)} · ${route.hops}홉 · `
        + `${route.chain.join(' → ')}`
        + (loops ? ` · 같은 타입 되짚기 «1회»가 기본값입니다` : '');
      row.addEventListener('click', () => this.useRoute(index));
      box.appendChild(row);
    });
    return box;
  }

  /** 선언이 준 «타입 이름»들. 지어낸 목록이 아니라 선언의 것입니다. */
  declaredTypes() {
    return this.declaration ? typeGraph(this.declaration).types : [];
  }

  /** 지금 시작 타입에서 고른 도착지까지의 경로들. 선언 한 번으로 계산됩니다. */
  routes() {
    if (!this.declaration || !this.destination) return [];
    return pathsBetween(this.declaration, bareTypeName(this.nodeType), this.destination);
  }

  /** 경로 하나를 «쓴다» -- follow 와 hops 가 그 경로에서 나옵니다. */
  useRoute(index) {
    const route = this.routes()[index];
    if (!route) return;
    this.chosenPath = index;
    this.follow = new Set(route.follow);
    this.hops = route.hops;
    this.render();
  }

  _note(text, cls) {
    const el = this.doc.createElement('div');
    el.className = `rb-walkbox-note${cls ? ' ' + cls : ''}`;
    el.textContent = text;
    return el;
  }

  _field(label) {
    const box = this.doc.createElement('div');
    box.className = 'rb-walkbox-field';
    const lab = this.doc.createElement('div');
    lab.className = 'rb-walkbox-label';
    lab.textContent = label;
    box.appendChild(lab);
    return box;
  }

  _typeRow() {
    const doc = this.doc;
    const box = this._field('NODE TYPE');
    const sel = doc.createElement('select');
    sel.className = 'rb-walkbox-select';
    sel.setAttribute('data-field', 'type');
    for (const t of ['', ...this.types()]) {
      const opt = doc.createElement('option');
      opt.setAttribute('value', t);
      opt.textContent = t || '— 고르십시오 —';
      if (t === this.nodeType) opt.setAttribute('selected', 'selected');
      sel.appendChild(opt);
    }
    sel.addEventListener('change', (e) => this.setType((e && e.target && e.target.value) || ''));
    box.appendChild(sel);
    return box;
  }

  /**
   * C-51 — 「언제부터 언제까지」. 반열린 구간 [since, until), 둘 다 선택.
   *
   * ⛔ 부품이 «거르지 않습니다». 이 두 칸은 질문이고, 답을 자르는 것은 walk 입니다(상설).
   * ⛔ 설명 문구 없음 — 빈 칸이 「구간 없음」이라는 것은 «빈 칸이 말합니다»(상설 2026-09-04).
   */
  _intervalRow() {
    const doc = this.doc;
    const box = this._field('WHEN');
    for (const [name, label] of [['since', 'since'], ['until', 'until']]) {
      const wrap = doc.createElement('div');
      wrap.className = 'rb-walkbox-key';
      wrap.setAttribute('data-interval', name);
      const lab = doc.createElement('label');
      lab.textContent = label;
      const input = doc.createElement('input');
      input.setAttribute('type', 'date');
      input.setAttribute('data-interval-input', name);
      input.setAttribute('value', this[name] || '');
      input.addEventListener('input', (e) => { this[name] = (e && e.target && e.target.value) || ''; });
      wrap.append(lab, input);
      box.appendChild(wrap);
    }
    return box;
  }

  _keyRow() {
    const doc = this.doc;
    const box = this._field('KEY');
    const keys = this.keysOf();
    if (!this.nodeType) { box.appendChild(this._note('타입을 고르면 그 타입의 키가 나옵니다')); return box; }
    if (!keys.length) { box.appendChild(this._note('이 타입은 선언에 키가 없습니다')); return box; }
    for (const k of keys) {
      const wrap = doc.createElement('div');
      wrap.className = 'rb-walkbox-key';
      wrap.setAttribute('data-key', k);
      const lab = doc.createElement('label');
      lab.textContent = k;
      const input = doc.createElement('input');
      input.setAttribute('data-key-input', k);
      input.setAttribute('value', this.keyValues[k] === undefined ? '' : String(this.keyValues[k]));
      input.addEventListener('input', (e) => { this.keyValues[k] = (e && e.target && e.target.value) || ''; });
      wrap.append(lab, input);
      box.appendChild(wrap);
    }
    return box;
  }

  _followRow() {
    const doc = this.doc;
    const box = this._field('FOLLOW');
    const options = this.followOptions();
    if (!options.length) {
      // 🔴 시금석. 「없다」를 «문장»으로 -- 빈 목록은 고장과 구별이 안 됩니다.
      box.appendChild(this._note(this.nodeType
        ? `${this.nodeType} 에서 나가는 술어가 없습니다 — 이 타입은 목적어로만 나옵니다`
        : '선언에 술어가 없습니다', 'is-absent'));
      return box;
    }
    for (const name of options) {
      const wrap = doc.createElement('label');
      wrap.className = 'rb-walkbox-follow' + (this.follow.has(name) ? ' is-on' : '');
      wrap.setAttribute('data-follow', name);
      const cb = doc.createElement('input');
      cb.setAttribute('type', 'checkbox');
      if (this.follow.has(name)) cb.setAttribute('checked', 'checked');
      cb.addEventListener('change', () => this.toggleFollow(name));
      const text = doc.createElement('span');
      text.textContent = name;
      wrap.append(cb, text);
      box.appendChild(wrap);
    }
    box.appendChild(this._note('안 고르면 서버 기본값 — 전부 따릅니다'));
    return box;
  }

  _runRow() {
    const doc = this.doc;
    const box = doc.createElement('div');
    box.className = 'rb-walkbox-run';
    const btn = doc.createElement('button');
    btn.className = 'rb-walkbox-go';
    btn.setAttribute('data-action', 'walk');
    btn.textContent = '걷기';
    if (!this.nodeType) btn.setAttribute('disabled', 'disabled');
    btn.addEventListener('click', () => this.run());
    box.appendChild(btn);
    return box;
  }

  /** COLLECT 된 return. 표는 «선언»입니다 -- 두 번째 표를 손으로 그리지 않습니다. */
  _resultBox() {
    const doc = this.doc;
    const box = doc.createElement('div');
    box.className = 'rb-walkbox-result';
    const rows = (this.walkState === 'ready' && this.result && this.result.nodes) || [];
    // 🔴 끊긴 답을 «전부»로 읽게 두지 않습니다. 실측 2026-08-27, wafer@1 SYN-BW-101-16:
    //    `truncated` 가 nodes·edges·claims·actions «전부 true» 이고 depth 만 false 입니다 --
    //    예산에서 잘린 진짜 끊김입니다. 이 부품은 hops 를 선언하지 않으므로 depth 도 끊김이지
    //    질문이 아닙니다(그 구분은 「닿는 곳」쪽 이야기입니다). 서버가 부른 이름을 그대로 씁니다.
    // 🔴 판정을 «여기서 다시 하지 않습니다». 이 부품은 hops 를 선언하지 않으므로 depth 도
    //    끊김이고, 그 사실은 `createWalkBoxWalk` 가 «요청을 지을 때» 알고 있어 이미 접었습니다
    //    (`truncatedAxes`). 여기서 `reason` 을 다시 읽으면 그 판정의 «네 번째 사본»입니다.
    const axes = this.walkState === 'ready' && this.result && this.result.cut
      ? (this.result.truncatedAxes || []) : [];
    const cut = axes.length ? axes.join(', ') : null;
    // 🔴 문장은 표 «밖»에 답니다. `TablePart.render()` 가 첫 줄에서 자기 host 를 비우므로,
    //    같은 상자에 붙이면 표가 그려지는 순간 «조용히 지워집니다» -- 오류도 안 나고 픽셀만
    //    사라집니다. 하니스 T1 이 그것을 잡았습니다.
    if (cut) box.appendChild(this._note(`예산에서 끊겼습니다 — ${cut}. 이게 전부가 아닙니다`, 'is-cut'));
    // 🔴 C-51. 「구간 밖이라 안 가져온 수」 — «값 옆 한 줄». 판정은 `createWalkBoxWalk` 가
    //    이미 했습니다(`intervalExcluded`); 여기서 응답을 다시 읽으면 네 번째 사본입니다.
    // 🔴 키가 «없으면» 안 그립니다(구간을 안 물었다). `0` 은 «그립니다» — 「물었고 제외된 게
    //    없다」이고, 그 둘은 운영자에게 다른 답입니다. 그래서 참/거짓이 아니라 `null` 로 갈립니다.
    const excluded = this.walkState === 'ready' && this.result
      ? this.result.intervalExcluded : null;
    if (excluded !== null && excluded !== undefined) {
      box.appendChild(this._note(`구간 밖 ${excluded}`, 'is-interval'));
    }
    // 🔴 C-70. 걷기 결과는 «한 타입이 아닙니다» — 이 부품은 `collect` 를 안 싣고 서버 기본값은
    //    「닿은 것 전부」입니다. 타입마다 선언된 키가 다르므로 «구획»이 컬럼을 선언에서 가져올
    //    수 있게 하는 자리이고, 구획도 컬럼도 `walk/derive.js` 가 정합니다. 좁은 것은 그대로
    //    입니다 — 프리셋이 고르는 것은 «폭»이지 «정하는 쪽»이 아닙니다.
    const entities = (this.declaration && this.declaration.entities) || [];
    const sections = sectionsByType(rows);
    // C-89. 같은 독자, 같은 낱말 — 걷기 페이지의 표와 이 표가 같은 칸을 같은 모양으로 그립니다.
    const plural = pluralAttributes(this.result);
    // 부재는 여전히 «표 하나»가 말합니다. 구획이 없을 때 문장을 잃으면 「걷는 중」·「거절」·
    //    「걸었는데 없음」 셋이 같은 빈 화면이 됩니다.
    if (!sections.size) {
      const emptyHost = doc.createElement('div');
      box.appendChild(emptyHost);
      new TablePart(emptyHost, {
        doc,
        markings: this.markings,
        reads: this.reads,
        writes: this.writes,
        columns: tableColumns(entities, this.nodeType, [], COLUMNS.FOR_PICKING).map(partColumn),
        rows: [],
        emptyText: this._emptyText(),
      }).mount();
      return box;
    }
    for (const [type, nodes] of sections) {
      const host = doc.createElement('div');
      box.appendChild(host);
      const cols = tableColumns(entities, type, [], COLUMNS.FOR_PICKING);
      new TablePart(host, {
        doc,
        markings: this.markings,
        reads: this.reads,
        writes: this.writes,
        rowKey: 'id',
        title: sectionHeading(type, nodes.length),
        columns: cols.map(partColumn),
        rows: nodes.map((node) => partRow(cols, node, plural.get(type))),
        onRowClick: (id) => { this.mark(id, SIGN.CASE, 'replace'); this.render(); },
      }).mount();
    }
    return box;
  }

  /** 부재 셋, 문장 셋. */
  _emptyText() {
    if (this.walkState === 'loading') return '걷는 중…';
    // ② 서버가 못 준다 -- 거절과 라우트 부재가 같은 자리입니다.
    if (this.walkState === 'refused') {
      return (this.result && this.result.message) || '서버가 걷기에 답하지 않았습니다';
    }
    // ③ 걸었는데 없다.
    if (this.walkState === 'ready') return '걸었는데 닿은 것이 없습니다';
    // ① 아직 안 골랐다 / 안 걸었다.
    // C-99 ③. 두 문장이 한 값으로. 다음 행동은 «누를 수 있는 버튼»이 이미 말합니다.
    return UNPICKED;
  }
}

/**
 * `derive.js` 의 컬럼 서술자를 `TablePart` 의 컬럼 «표기»로 옮깁니다.
 *
 * 🔴 옮기는 것뿐입니다 — «무엇이 서는지»도 «어떤 순서인지»도 여기서 정하지 않습니다. 그 둘을
 *    여기서 만지면 이 파일이 다시 두 번째 저자가 됩니다.
 * ⚠️ `key` 는 서술자에서 «유도»합니다. 손으로 적으면 타입마다 다른 키 이름과 어긋납니다.
 */
function columnId(col) {
  return col.key ? `${col.kind}:${col.key}` : col.kind;
}

function partColumn(col) {
  return {
    key: columnId(col),
    label: col.name,
    width: col.kind === 'label' ? 'minmax(0, 1fr)' : 'minmax(0, 0.7fr)',
  };
}

/**
 * 🔴 값도 `derive.js` 가 읽습니다(`cellSource`). 수식어는 «안 묻습니다» — 좁은 프리셋에
 *    수식어 컬럼이 없으므로 물을 것이 없고, 여기서 지어내면 그것이 세 번째 저자입니다.
 * ⚠️ `id` 는 «컬럼이 아니지만» 행에 실립니다 — `TablePart` 의 `rowKey` 가 그것으로 마킹합니다.
 */
function partRow(cols, node, plural) {
  const row = { id: node.id };
  for (const col of cols) row[columnId(col)] = cellSource(col, node, {}, plural);
  return row;
}
