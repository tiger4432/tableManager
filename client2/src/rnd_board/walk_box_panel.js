// ═══════════════════════════════════════════════════════════════════════════════
// 걷기 검색창 — walk 의 네 칸을 «사람이 그 자리에서» 고르는 손잡이판.
//
// 소유자: 「걷기 API 사용 위한 검색창. 검색창에는 NODE TYPE과 KEY, FOLLOW 리스트, COLLECT
//         대상으로 모든 요소는 현재 걸린 필터 수준에 따라 드롭다운 리스트를 제안할것」
//         「결과는 COLLECT된 RETURN으로 보여줘」
//
// 🔴 새 축이 아닙니다. 다른 부품이 «선언»으로 들고 태어나는 그 네 칸(start·collect·follow)을,
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
//                           collect:[string], message? }
//   walk({ type, keys, follow, collect })
//                      -> { ok, nodes:[{id,type,label}], message? }
// 🔴 «한 모양»입니다. 어떤 호출은 body 를 그냥 주고 어떤 호출은 {ok,body} 로 감싸면, 섞이는
//    자리에서 오류 없이 «빈 값»이 나옵니다. 라우트를 이 모양에 맞추는 것은 조립하는 쪽 일이고,
//    부품은 라우트를 모릅니다.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel } from './panel.js';
import { SIGN } from './marking_store.js';
import { TablePart } from './table_part.js';

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
    this.collect = options.collect || null;

    this.result = null;
    this.walkState = 'idle';
  }

  mount() {
    super.mount();
    this.loadDecl();
  }

  async loadDecl() {
    if (!this.loadDeclaration) { this.declState = 'idle'; this.render(); return; }
    this.declState = 'loading';
    this.render();
    const got = await this.loadDeclaration();
    this.declaration = got && got.ok ? got : null;
    this.declState = this.declaration ? 'ready' : 'refused';
    if (this.declaration && !this.collect) this.collect = (this.declaration.collect || [])[0] || null;
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

  collects() {
    return (this.declaration && this.declaration.collect) || [];
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
    const spec = { type: this.nodeType, keys, collect: this.collect };
    // 🔴 «안 고르면 안 싣습니다». 빈 배열을 실으면 「아무 술어도 따르지 마라」로 읽히고,
    //    서버 기본값(전부)과 «정반대»입니다. 없는 것은 없는 채로 보냅니다.
    if (this.follow.size) spec.follow = [...this.follow];
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
    root.appendChild(this._followRow());
    root.appendChild(this._collectRow());
    root.appendChild(this._runRow());
    root.appendChild(this._resultBox());

    this.host.appendChild(root);
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

  _collectRow() {
    const doc = this.doc;
    const box = this._field('COLLECT');
    const sel = doc.createElement('select');
    sel.className = 'rb-walkbox-select';
    sel.setAttribute('data-field', 'collect');
    for (const c of this.collects()) {
      const opt = doc.createElement('option');
      opt.setAttribute('value', c);
      opt.textContent = c;
      if (c === this.collect) opt.setAttribute('selected', 'selected');
      sel.appendChild(opt);
    }
    sel.addEventListener('change', (e) => { this.collect = (e && e.target && e.target.value) || null; this.render(); });
    box.appendChild(sel);
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
    const cut = this.walkState === 'ready' && this.result && this.result.truncated
      && this.result.truncated.reason ? String(this.result.truncated.reason) : null;
    // 🔴 문장은 표 «밖»에 답니다. `TablePart.render()` 가 첫 줄에서 자기 host 를 비우므로,
    //    같은 상자에 붙이면 표가 그려지는 순간 «조용히 지워집니다» -- 오류도 안 나고 픽셀만
    //    사라집니다. 하니스 T1 이 그것을 잡았습니다.
    if (cut) box.appendChild(this._note(`예산에서 끊겼습니다 — ${cut}. 이게 전부가 아닙니다`, 'is-cut'));
    const tableHost = doc.createElement('div');
    box.appendChild(tableHost);
    const table = new TablePart(tableHost, {
      doc,
      markings: this.markings,
      reads: this.reads,
      writes: this.writes,
      rowKey: 'id',
      emptyText: this._emptyText(),
      columns: [
        { key: 'label', label: 'label', width: 'minmax(0, 1fr)' },
        { key: 'type', label: 'type', width: '8rem', kind: 'mono' },
        { key: 'id', label: 'id', width: 'minmax(0, 1.4fr)', kind: 'mono' },
      ],
      rows: rows.map((n) => ({ id: n.id, type: n.type, label: n.label })),
      onRowClick: (id) => { this.mark(id, SIGN.CASE, 'replace'); this.render(); },
    });
    table.mount();
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
    return this.nodeType ? '「걷기」를 누르면 결과가 여기 나옵니다' : '타입을 고르고 걸으십시오';
  }
}
