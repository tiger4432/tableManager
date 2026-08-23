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
import { fetchSubgraph, subgraphModel } from './api.js';

export class RankListPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    this.apiBase = options.apiBase || '';
    this.seedNodeId = options.seedNodeId || null;
    this.collect = options.collect || 'quantity';
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
    const result = await fetchSubgraph({
      apiBase: this.apiBase,
      nodeId: this.seedNodeId,
      collect: this.collect,
      fetchImpl: this.fetchImpl,
    });
    this.model = subgraphModel(result);
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
    root.className = this.markCount() > 0 ? 'rb-rank is-attenuating' : 'rb-rank';

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
    if (m.state === 'empty') {
      const note = doc.createElement('div');
      note.className = 'rb-rank-note rb-rank-note--absent';
      // Same correction: state what the walk DID reach beside what it did not find.
      note.textContent = `노드 ${m.graph.nodes} · 엣지 ${m.graph.edges} — 원인 후보는 없습니다`;
      root.appendChild(note);
      place(root);
      return;
    }

    const table = doc.createElement('div');
    table.className = 'rb-rank-rows';
    table.appendChild(this._headRow());
    for (const c of m.candidates) table.appendChild(this._row(c, m));
    root.appendChild(table);
    place(root);
  }

  _headRow() {
    const el = this.doc.createElement('div');
    el.className = 'rb-rank-row rb-rank-row--head';
    for (const label of ['순위', '물리량 · 모델', '홉', '실측', '상태']) {
      const c = this.doc.createElement('span');
      c.textContent = label;
      el.appendChild(c);
    }
    return el;
  }

  _row(c, m) {
    const doc = this.doc;
    const wrap = doc.createElement('div');
    wrap.className = 'rb-rank-item';

    const el = doc.createElement('div');
    el.className = 'rb-rank-row';
    if (c.id) {
      el.setAttribute('data-node-id', c.id);
      const sign = this.signOf(c.id);
      if (sign === SIGN.CASE) el.classList.add('is-marked-case');
      el.addEventListener('click', (event) => {
        // Clicking a row opens its evidence AND marks it. The marking is what links this table
        // to whatever else happens to read the same name.
        if (this.opened.has(c.id)) this.opened.delete(c.id); else this.opened.add(c.id);
        const intent = markingIntent(event);
        this.mark(c.id, intent.sign, intent.mode);
        this.render();
      });
    }

    const rank = doc.createElement('span');
    rank.className = 'rb-rank-n';
    // The server's number, unchanged. Ties share it.
    rank.textContent = c.rank === null ? '-' : String(c.rank);

    const label = doc.createElement('span');
    label.className = 'rb-rank-label';
    const q = doc.createElement('span');
    q.className = 'rb-rank-quantity';
    q.textContent = c.quantity;
    const mdl = doc.createElement('span');
    mdl.className = 'rb-rank-model';
    mdl.textContent = c.model || '-';
    label.append(q, mdl);

    const hops = doc.createElement('span');
    hops.className = 'rb-rank-hops';
    hops.textContent = c.hopCount ? String(c.hopCount) : '-';

    const measured = doc.createElement('span');
    measured.className = c.measured ? 'rb-rank-measured' : 'rb-rank-measured is-absent';
    // 🔴 `-` IS THE POINT. It is how the 21 name-only candidates read in this table, and the
    // candidate list's folded card points here for exactly that.
    measured.textContent = c.measured ? '있음' : '-';

    const state = doc.createElement('span');
    state.className = 'rb-rank-state';
    state.textContent = this._stateWords(c, m).join(' · ') || '-';

    el.append(rank, label, hops, measured, state);
    wrap.appendChild(el);

    if (c.id && this.opened.has(c.id)) wrap.appendChild(this._evidence(c));
    return wrap;
  }

  /** Every word here is an absence or a position -- never a fault. */
  _stateWords(c, m) {
    const words = [];
    if (c.top) words.push('최상위');
    if (c.tied) words.push('동률');
    if (c.incomparable) words.push('종류 다름');
    // `complete:false` means the budget cut the walk short: what is below is UNEXAMINED, and
    // that is a different sentence from 「없다」.
    if (!m.complete) words.push('미검사');
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
