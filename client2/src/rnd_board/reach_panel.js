// ═══════════════════════════════════════════════════════════════════════════════
// 닿는 곳 — 「이 마킹에서 «어느 것들로» 갈 수 있나」.
//
// 소유자: 「마킹 펼치는거 시각화 하는 차트 만들든가 «어느 것들로 닿을수 있는지 보여주는거»」.
// 예전의 「b 가 뭔지 모르니 b1·b2·b3 후보를 보여줘야지」를 «값»이 아니라 «엣지»에 적용한 것입니다.
//
// 🔴 이 부품은 «질의를 하나»만 합니다: 읽는 마킹을 씨앗으로 한 홉. `follow` 는 «없습니다» --
//    「무엇이 있나」를 묻는 자리에서 술어를 미리 좁히면, 좁힌 그 술어만 있는 것처럼 보입니다.
//
// 🔴 찍으면 «펼쳐집니다» — 그 술어로 닿는 «노드 집합»이 쓸 마킹에 들어갑니다. 소유자 도식의
//    「마킹1 → 찍기 → 마킹2」가 «엣지 쪽»에서도 도는 자리입니다. 표는 술어를 그리지만
//    마킹에 들어가는 것은 «노드»입니다 — 술어는 노드가 아니므로 표 자신은 아무것도 안 씁니다
//    (`writes: null` 로 넘깁니다).
//
// 🔴 부재는 «따로» 말합니다. 「아직 안 골랐다」와 「나가는 엣지가 없다」와 「서버가 거절」은
//    다른 문장입니다. 한 낱말로 합치면 셋 중 어느 것인지 화면에서 못 읽습니다.
//
// 조립식: 자기 host, 주입된 doc/markings, 모듈 수준 상태 0, 읽을 이름과 쓸 이름을 각각 선언.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel } from './panel.js';
import { SIGN } from './marking_store.js';
import { TablePart } from './table_part.js';

export class ReachPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    this.walkFn = options.walk || null;
    // 🔴 `Panel` 은 `start` 를 안 들고 있습니다 -- 부품마다 자기가 받습니다(다른 부품들과
    //    같은 자리). 이걸 빼면 `startFor()` 가 «항상» null 이라 부품이 조용히 아무것도
    //    묻지 않고 「아직 안 골랐다」만 그립니다 -- 마킹이 «차 있어도». 하니스 C1 이 그것입니다.
    this.start = options.start || null;
    this.collect = options.collect || 'reach';
    this.model = null;
    this.loadState = 'idle';
    // 지금 펼친 술어. 인스턴스마다 자기 것이라 같은 화면의 둘이 서로 다른 줄을 펼칠 수 있습니다.
    this.opened = null;
  }

  mount() {
    super.mount();
    this.load();
  }

  /** 읽는 마킹이 움직이면 «질문이 바뀐 것»입니다 — 다시 그리는 게 아니라 다시 걷습니다. */
  onMarkingChanged() {
    this.opened = null;
    this.load();
  }

  async load() {
    const start = this.startFor();
    if (!this.walkFn || !start) {
      this.loadState = start ? 'idle' : 'no-marking';
      this.model = null;
      this.render();
      return;
    }
    this.loadState = 'loading';
    this.render();
    const model = await this.walkFn({ start, collect: this.collect });
    this.model = model;
    this.loadState = model && model.ok ? 'ready' : 'refused';
    this.render();
  }

  /**
   * 「펼치기」 — 그 술어로 닿는 노드 «전부»를 쓸 마킹에 넣습니다.
   *
   * 🔴 첫 노드만 `replace` 이고 나머지는 `add` 입니다. 전부 replace 면 마지막 하나만 남고,
   *    전부 add 면 이전에 펼친 것이 그대로 쌓입니다. 「클릭하면 초기화되고 새로」가
   *    소유자 판정이고, 집합을 넣는 것도 그 규칙 «하나»의 적용입니다.
   *    `add` 는 토글이라 같은 노드가 두 번 들어오면 지워집니다 — 그래서 모델이 집합으로 셉니다.
   */
  _expand(predicate) {
    const row = ((this.model && this.model.rows) || []).find((r) => r.predicate === predicate);
    if (!row) return;
    this.opened = predicate;
    row.nodeIds.forEach((id, i) => this.mark(id, SIGN.CASE, i === 0 ? 'replace' : 'add'));
    this.render();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    this.host.textContent = '';
    const root = doc.createElement('div');
    root.className = 'rb-reach';

    if (this.title) {
      const cap = doc.createElement('div');
      cap.className = 'rb-part-title';
      cap.textContent = this.title;
      root.appendChild(cap);
    }

    root.appendChild(this._head());

    const rows = (this.loadState === 'ready' && this.model && this.model.rows) || [];
    const tableHost = doc.createElement('div');
    tableHost.className = 'rb-reach-table';
    const table = new TablePart(tableHost, {
      doc,
      markings: this.markings,
      // 🔴 표는 «술어»를 그립니다. 술어는 노드가 아니므로 표 자신은 읽지도 쓰지도 않습니다 --
      //    마킹에 들어가는 것은 이 부품이 넣는 «노드 집합»입니다.
      reads: null,
      writes: null,
      rowKey: 'predicate',
      emptyText: this._emptyText(),
      columns: [
        { key: 'predicate', label: '술어', width: 'minmax(0, 1fr)', kind: 'mono' },
        { key: 'count', label: '닿는 수', width: '5rem', align: 'right', kind: 'number' },
        { key: 'kindText', label: '어디로', width: 'minmax(0, 1fr)' },
        // 🔴 순서가 «우연이 아니라는 것»이 화면에 있어야 합니다. 아래 목록은 시간 순으로
        //    마킹되는데, 그 근거가 안 보이면 읽는 사람에게는 여전히 임의의 순서입니다.
        { key: 'whenText', label: '언제', width: 'minmax(0, 1fr)', kind: 'mono' },
      ],
      rows: rows.map((r) => ({
        predicate: r.predicate,
        count: r.count,
        // 🔴 엣지 수는 «다를 때만» 붙습니다. 같을 때 붙이면 줄마다 같은 수가 두 번 서서
        //    읽는 사람이 「왜 두 번 적었나」를 먼저 묻게 됩니다. 다를 때는 그게 답입니다 --
        //    `binding` 은 엣지 10 이 노드 4 로 갑니다.
        kindText: r.kinds.map((k) => `${k.type} ${k.count}`).join(' · ')
          + (r.edges !== r.count ? ` · 엣지 ${r.edges}` : ''),
        // 🔴 시각이 «없는» 술어는 `null` 을 넘깁니다 -- 표가 「-」 로 그리고 is-absent 를 답니다.
        //    빈 문자열이나 0 을 쓰면 「시각이 없다」와 「시각이 0 이다」가 같은 픽셀이 됩니다.
        //    파생 엣지(`binding` 같은)가 그 자리입니다: 실측 10 엣지 전부 occurred_at 이 없습니다.
        whenText: this._span(r.span),
      })),
      onRowClick: (predicate) => this._expand(predicate),
    });
    table.mount();
    root.appendChild(tableHost);

    this.host.appendChild(root);
  }

  /**
   * 「언제」 칸 -- 그 술어가 «처음~마지막» 닿은 때. 하루 안이면 한 번만 적습니다.
   * 🔴 `null` 을 «그대로» 돌려줍니다. 없는 것을 문자열로 만들면 표가 그것을 값으로 그립니다.
   */
  _span(span) {
    if (!span || !span.first) return null;
    const day = (t) => String(t).slice(0, 10);
    const minute = (t) => String(t).slice(0, 16).replace('T', ' ');
    if (span.first === span.last) return minute(span.first);
    if (day(span.first) === day(span.last)) return `${minute(span.first)} ~ ${String(span.last).slice(11, 16)}`;
    return `${day(span.first)} ~ ${day(span.last)}`;
  }

  /** 머리 한 줄 — 무엇을 걸었고, 무엇이 왔고, 무엇이 펼쳐져 있나. */
  _head() {
    const doc = this.doc;
    const el = doc.createElement('div');
    el.className = 'rb-reach-head';
    const m = this.model;
    const parts = [];
    if (this.loadState === 'ready' && m) {
      parts.push(`${m.seedLabel || m.seedId || '씨앗'} · 한 홉`);
      parts.push(`노드 ${m.nodes} · 엣지 ${m.edges}`);
      // 🔴 depth 는 «질문»이라 여기 안 뜹니다. 이 셋만 「답이 실제로 모자라다」는 뜻입니다.
      if (m.cut && m.cut.length) parts.push(`잘림 ${m.cut.join('·')}`);
      if (this.opened) parts.push(`펼침 ${this.opened}`);
    } else if (this.loadState === 'no-marking') {
      parts.push(`${this.reads || '마킹'} 이 이 목록의 주어입니다`);
    }
    el.textContent = parts.join(' · ');
    return el;
  }

  /** 넷 중 어느 부재인지 «문장»으로 말합니다. 빈 표가 아닙니다. */
  _emptyText() {
    if (this.loadState === 'no-marking') return '아직 안 골랐습니다 — 찍으면 어디로 갈 수 있는지 보입니다';
    if (this.loadState === 'loading') return '읽는 중…';
    if (this.loadState === 'refused') return (this.model && this.model.message) || '걸어 보지 못했습니다';
    return '이 노드에서 나가는 엣지가 없습니다';
  }
}
