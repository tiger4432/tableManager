// ═══════════════════════════════════════════════════════════════════════════════
// 부품 G — 순위 리스트. 명세 §9.
//
// 🔴 순위는 «판정이 아닙니다». The mockup writes that on the panel itself and so does this part.
//    No score and no probability leaves the server -- it was taken out on purpose -- so a screen
//    that ranked harder than the data would be making the claim for it. `tied` rows keep the
//    SAME number; renumbering them would invent an order nobody computed.
//
// 🔴 물리량 and 모델 are TWO LINES. The same quantity appears under two models, and joining them
//    states a third claim nobody made.
//
// 🔴 EVIDENCE IS FOLDED BY DEFAULT. Hops run 3-6 and there are 25 rows; opening them all is a
//    wall, and a wall is read as noise.
//
// 🔴 THE STATE COLUMN IS THIS PART'S VOCABULARY, and every word in it is an ABSENCE, not a
//    fault: 동률 · 종류 다름 · 미검사. None of them borrows the danger tokens.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel, markingIntent } from './panel.js';
import { SIGN } from './marking_store.js';
import { createWalk } from './api.js';
import { TablePart } from './table_part.js';

export class RankListPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    // 🔴 ONE CALL — 소유자가 그린 데이터 흐름(2026-08-24): 부품은 { start, collect } 만 선언하고
    //    라우트·질의·모델을 다시는 부르지 않습니다. 화면이 walk 하나를 «주입»하므로 같은 walk 을
    //    쓰는 두 부품이 요청 하나를 나눠 씁니다. 혼자 서는 부품은 자기 것을 만듭니다.
    this.walk = options.walk || createWalk({ apiBase: options.apiBase, fetchImpl: options.fetchImpl });
    // 시작점과 걷는 종류. 값이고 축이 아닙니다 — 소유자: 「일단 wafer 로 고정」.
    this.start = options.start || null;
    // 이 걷기의 «예산». 화면이 선언하고 부품은 나르기만 합니다 -- 기본값에 기대면 끊긴 걷기가
    // 「후보 없음」으로 보입니다 (오늘 두 번 그렇게 읽혔습니다).
    this.nodeLimit = options.nodeLimit || null;
    this.seedNodeId = options.seedNodeId || null;
    this.collect = options.collect || 'candidate';
    this.fetchImpl = options.fetchImpl || null;
    this.model = null;
    this.loadState = this.seedNodeId ? 'idle' : 'no-seed';
    // Per-instance, so two rank tables can stand side by side with different rows open.
    this.opened = new Set();
  }

  mount() {
    super.mount();
    if (this.seedNodeId) this.load();
  }

  async load() {
    this.loadState = 'loading';
    this.render();
    this.model = await this.walk({
      start: this.start || { groupby: 'wafer', value: this.seedNodeId },
      collect: this.collect,
      ...(this.nodeLimit ? { node_limit: this.nodeLimit } : {}),
    });
    this.loadState = this.model.ok ? 'ready' : 'refused';
    this.render();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    // 🔴 THE CURSOR MUST NOT MOVE. A re-render rebuilds this panel's box, and a rebuilt box
    //    starts at scrollTop 0 -- so the row under the pointer jumps away on the very click
    //    that opened it. The owner named this: 「접힌거 펴지면서 좌표 바껴서 마우스 위치 옮겨야」.
    //    The position is carried across; the fold stays inside this panel's own cell.
    const kept = this.host.firstElementChild;
    const scrollTop = kept ? kept.scrollTop || 0 : 0;
    const place = (node) => { this.host.appendChild(node); node.scrollTop = scrollTop; };
    this.host.textContent = '';
    const root = doc.createElement('div');
    // 🔴 ATTENUATION, not decoration (the owner's Spotfire, measured): while something is
    //    marked the rest FADES. Nothing fades while nothing is marked -- 「아직 안 골랐다」
    //    and 「이건 아니다」 are different sentences. The dimming itself is CSS, so it is one
    //    rule per part rather than a colour computed here.
    // 🔴 ATTENUATE ONLY WHEN SOMETHING OF MINE IS MARKED. A name is shared, so another
    //    panel writing an id of its own kind would otherwise fade every row here while
    //    none of them lit up.
    const mineMarked = (this.model && this.model.candidates || []).map((c) => c.id)
      .some((id) => id && this.signOf(id) !== SIGN.ABSENT);
    root.className = mineMarked ? 'rb-rank is-attenuating' : 'rb-rank';
    // 🔴 THE PANEL SAYS WHAT IT IS. The declaration carries a title and the shell hands it
    //    over; only the map drew it, so four panels stood unnamed on the screen and a
    //    reader had to infer the subject from the content. It is STICKY: a title that
    //    scrolls away is a title you cannot check while reading row 20.
    if (this.title) {
      const cap = doc.createElement('div');
      cap.className = 'rb-part-title';
      cap.textContent = this.title;
      root.appendChild(cap);
    }

    const caption = doc.createElement('div');
    caption.className = 'rb-rank-caption';
    // Said on the panel, not only in a comment. The screen must not read as a verdict.
    caption.textContent = '순위는 판정이 아닙니다 · 점수·확률 없음';
    root.appendChild(caption);


    if (this.loadState !== 'ready' || !this.model || !this.model.ok) {
      const note = doc.createElement('div');
      note.className = this.loadState === 'refused'
        ? 'rb-rank-note rb-rank-note--refused' : 'rb-rank-note rb-rank-note--absent';
      note.textContent = this.loadState === 'no-seed' ? '씨앗 없음'
        : this.loadState === 'loading' ? '걷는 중'
        : (this.model && this.model.message) || '서버가 거절했습니다';
      root.appendChild(note);
      place(root);
      return;
    }

    const m = this.model;
    // 🔴 잘린 것을 «말합니다». 순위표에서 이것이 빠지면 「1위가 진짜 1위」인지 알 수 없습니다 --
    //    걸어오다 끊긴 walk 의 1위는 「지금까지 본 것 중 1위」입니다 (총괄 판정 2026-08-24).
    if (Array.isArray(m.truncated) && m.truncated.length) {
      const cut = doc.createElement('div');
      cut.className = 'rb-rank-note rb-rank-note--absent';
      cut.textContent = `${m.truncated.join(' · ')} 에서 잘림 — 더 있을 수 있습니다`;
      root.appendChild(cut);
    }
    if (m.state === 'empty') {
      const note = doc.createElement('div');
      note.className = 'rb-rank-note rb-rank-note--absent';
      // Same correction: state what the walk DID reach beside what it did not find.
      note.textContent = `노드 ${m.graph.nodes} · 엣지 ${m.graph.edges} — 원인 후보는 없습니다`;
      root.appendChild(note);
      place(root);
      return;
    }

    // 🔴 표 부품, 두 번째 «선언». 코드는 구성 표와 «한 벌»이고 다른 것은 이 컬럼 목록뿐입니다
    //    (소유자 상설 ①). 전에는 이 표만 머리·행높이·두 줄·구분선·상태 표기가 달랐습니다.
    const table = doc.createElement('div');
    table.className = 'rb-rank-rows';
    const rows = new TablePart(table, {
      doc,
      markings: this.markings,
      reads: this.reads,
      writes: this.writes,
      rowKey: 'nodeId',
      emptyText: '응답에 후보가 없습니다',
      columns: [
        { key: 'rank', label: '순위', width: '2.5rem', kind: 'rank' },
        { key: 'quantity', label: '물리량 · 모델', kind: 'two_line', subKey: 'model' },
        { key: 'hops', label: '홉', width: '2rem', kind: 'number' },
        { key: 'measured', label: '실측', width: '3rem' },
        { key: 'state', label: '상태', width: '8rem', kind: 'badge' },
      ],
      rows: m.candidates.map((c) => this._rankRow(c, m)),
      // 펼침의 «내용»은 이 패널의 것입니다. 표는 자리만 내줍니다.
      detailFor: (row) => (row.nodeId && this.opened.has(row.nodeId)
        ? this._evidence(row.candidate) : null),
      onRowClick: (id) => {
        if (this.opened.has(id)) this.opened.delete(id); else this.opened.add(id);
        this.render();
      },
    });
    rows.mount();
    root.appendChild(table);
    place(root);
  }

  /**
   * 한 후보의 «행 데이터». 그리는 것은 표 부품입니다 -- 구성 표와 같은 코드입니다.
   * 🔴 `-` IS THE POINT for 실측: it is how the name-only candidates read here, and the
   *    candidate list's folded card points at exactly that column.
   */
  _rankRow(c, m) {
    return {
      nodeId: c.id || null,
      candidate: c,
      rank: c.rank === null ? null : String(c.rank),
      quantity: c.quantity,
      model: c.model || null,
      hops: c.hopCount ? String(c.hopCount) : null,
      measured: c.measured ? '있음' : null,
      state: this._stateWords(c, m).join(' · ') || null,
    };
  }
  /** Every word here is an absence or a position -- never a fault. */
  _stateWords(c, m) {
    const words = [];
    if (c.top) words.push('최상위');
    if (c.tied) words.push('동률');
    if (c.incomparable) words.push('종류 다름');
    // `complete:false` means the budget cut the walk short: what is below is UNEXAMINED, and
    // that is a different sentence from 「없다」.
    if (m.complete === false) words.push('미검사');
    return words;
  }

  _evidence(c) {
    const doc = this.doc;
    const box = doc.createElement('div');
    box.className = 'rb-rank-evidence';
    for (const ev of c.evidence || []) {
      for (const hop of ev.hops || []) {
        const line = doc.createElement('div');
        line.className = hop.declaredOnly ? 'rb-rank-hop is-declared' : 'rb-rank-hop';
        const kind = doc.createElement('span');
        kind.className = 'rb-rank-hop-kind';
        kind.textContent = hop.kind || '-';
        const label = doc.createElement('span');
        label.className = 'rb-rank-hop-label';
        label.textContent = hop.label || '';
        line.append(kind, label);
        if (hop.ref) {
          const ref = doc.createElement('span');
          ref.className = 'rb-rank-hop-ref';
          // The ref is what makes a hop checkable, so it is shown verbatim.
          ref.textContent = hop.ref;
          line.appendChild(ref);
        }
        box.appendChild(line);
      }
    }
    return box;
  }
}
