// ═══════════════════════════════════════════════════════════════════════════════
// 부품 D — 구성. 「이 최종 칩은 무엇으로 만들어졌나」.
//
// 명세: task/design/rnd_board_component_spec.md §6. Same route as 부품 A
// (`/api/ledger/composition`), which is why the two were ordered together.
//
// 🔴 THE ROWS ARE MARKABLE, AND THAT IS THIS PART'S ONLY LINK TO ANYTHING ELSE. A row marks a
//    component's ontology node id. No sibling is named, no shell is touched: another part
//    lights up because it happens to read the SAME name, not because this one told it to.
//    That is what lets this part be dropped into a different screen unchanged.
//
// 🔴 IT PRINTS `-`, NOT `0`. A count the server did not send is absent, and absence is not
//    zero. `0` is a measurement; `-` is the honest shape of "not stated".
//
// 🔴 NO SIZE CONSTANT. `onResize` redraws into whatever box the shell hands over.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel, markingIntent } from './panel.js';
import { SIGN } from './marking_store.js';
import { fetchComposition, compositionModel } from './api.js';

export class CompositionPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    this.apiBase = options.apiBase || '';
    this.finalChipId = options.finalChipId || null;
    this.fetchImpl = options.fetchImpl || null;
    this.model = null;
    this.loadState = this.finalChipId ? 'idle' : 'no-subject';
  }

  mount() {
    super.mount();
    if (this.finalChipId) this.load();
  }

  async load() {
    this.loadState = 'loading';
    this.render();
    const result = await fetchComposition({
      apiBase: this.apiBase,
      finalChipId: this.finalChipId,
      fetchImpl: this.fetchImpl,
    });
    this.model = compositionModel(result);
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
    const mineMarked = (this.model && this.model.components || []).map((c) => c.entityId || c.id)
      .some((id) => id && this.signOf(id) !== SIGN.ABSENT);
    root.className = mineMarked ? 'rb-comp is-attenuating' : 'rb-comp';
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

    if (this.loadState === 'no-subject' || this.loadState === 'loading' || !this.model || !this.model.ok) {
      const state = this.loadState === 'no-subject' ? '대상 없음'
        : this.loadState === 'loading' ? '불러오는 중'
        : '서버 거절';
      const detail = this.loadState === 'refused' && this.model ? this.model.message : (this.finalChipId || '');
      const note = doc.createElement('div');
      note.className = this.loadState === 'refused'
        ? 'rb-comp-note rb-comp-note--refused'
        : 'rb-comp-note rb-comp-note--idle';
      note.textContent = detail ? `${state} — ${detail}` : state;
      root.appendChild(note);
      place(root);
      return;
    }

    const m = this.model;

    // ── counts. `-` where the server said nothing ──────────────────────────────
    const counts = doc.createElement('div');
    counts.className = 'rb-comp-counts';
    counts.appendChild(this._count('components', m.counts.components));
    counts.appendChild(this._count('dt_collections', m.counts.dtCollections));
    if (m.coreTypes.length) {
      counts.appendChild(this._count('core types', m.coreTypes.length, m.coreTypes.join(' · ')));
    }
    root.appendChild(counts);

    // The ledger's own word about whether these counts are a constant. Kept as a word.
    if (m.cardinality.components) {
      const card = doc.createElement('div');
      card.className = 'rb-comp-cardinality';
      card.textContent = `cardinality 는 ${m.cardinality.components} — 이 칩의 실측이고 상수가 아닙니다`;
      root.appendChild(card);
    }

    // ── 「어떻게 정해졌나」 — 목업 2a 의 구성 패널이 층 위에 다는 상자 ──────────────
    // 🔴 THE RESOLUTION IS SHOWN, NOT SUMMARISED. 「resolved」 alone hides WHAT it was resolved
    //    on, and the basis is the first thing an engineer disputes. It sits beside the layers
    //    it explains rather than in the identity band.
    if (m.resolution) {
      const box = doc.createElement('div');
      box.className = 'rb-comp-resolution';
      const head = doc.createElement('div');
      head.className = 'rb-comp-resolution-head';
      head.textContent = '어떻게 정해졌나';
      box.appendChild(head);
      const put = (k, v, absent) => {
        const row = doc.createElement('div');
        row.className = absent ? 'rb-comp-resolution-row is-absent' : 'rb-comp-resolution-row';
        const key = doc.createElement('span');
        key.className = 'rb-comp-resolution-key';
        key.textContent = k;
        const val = doc.createElement('span');
        val.className = 'rb-comp-resolution-val';
        val.textContent = v;
        row.append(key, val);
        box.appendChild(row);
      };
      put('state', m.resolution.state || '-', !m.resolution.state);
      // `basis` is a path into the ledger; it is printed verbatim so it can be checked.
      put('basis', m.resolution.basis || '응답에 근거가 없습니다', !m.resolution.basis);
      put('candidates',
        typeof m.resolution.candidateCount === 'number' ? String(m.resolution.candidateCount) : '-',
        typeof m.resolution.candidateCount !== 'number');
      root.appendChild(box);
    }

    // ── the layers ─────────────────────────────────────────────────────────────
    const table = doc.createElement('div');
    table.className = 'rb-comp-rows';
    // A column head, because seven columns without one is a grid of unlabelled strings.
    const head = doc.createElement('div');
    // 🔴 NOT `rb-comp-row`. A header that wears the row's class makes every 「행이 몇 개냐」 and
    //    「행을 클릭하면」 assertion count and click the wrong thing -- it broke two of them the
    //    moment it was added. The columns are shared through a variable instead.
    head.className = 'rb-comp-head';
    for (const label of ['층', '코어 웨이퍼', '랏', '슬롯', '브랜치', '이력', '상태']) {
      const h = doc.createElement('span');
      h.textContent = label;
      head.appendChild(h);
    }
    table.appendChild(head);
    for (const c of m.components) {
      table.appendChild(this._row(c));
    }
    if (!m.components.length) {
      const empty = doc.createElement('div');
      empty.className = 'rb-comp-note rb-comp-note--idle';
      // NOT 「구성이 없습니다」 -- that would state a fact about the chip. The response carried
      // no rows; those are different sentences.
      empty.textContent = '응답에 구성 행이 없습니다';
      table.appendChild(empty);
    }
    root.appendChild(table);

    // ── 목업 ② 의 스텝 빵부스러기 — 마킹된 층의 «자기 스텝» ────────────────────
    // 🔴 THE CHAIN THE MOCKUP DECLARES: 층 마킹 → 그 층의 공정. It is driven by the marking
    //    this panel already writes, so clicking a layer is what opens it -- no second control.
    const markedLayer = m.components.find(
      (c) => this.signOf(c.entityId || c.id) !== SIGN.ABSENT);
    if (markedLayer) root.appendChild(this._steps(markedLayer));

    place(root);
  }

  /** The marked layer's own process steps, in order, as the ledger recorded them. */
  _steps(c) {
    const doc = this.doc;
    const box = doc.createElement('div');
    box.className = 'rb-comp-steps';
    const head = doc.createElement('span');
    head.className = 'rb-comp-steps-head';
    const wafer = (c.core && c.core.wafer) || c.id;
    const steps = c.steps || [];
    head.textContent = `${wafer} 의 스텝 ${steps.length}`;
    box.appendChild(head);
    if (!steps.length) {
      const none = doc.createElement('span');
      none.className = 'rb-comp-steps-absent';
      // Not 「공정이 없다」: the response carried no upstream process for this layer.
      none.textContent = '응답에 공정 이력이 없습니다';
      box.appendChild(none);
      return box;
    }
    steps.forEach((s, i) => {
      if (i > 0) {
        const sep = doc.createElement('span');
        sep.className = 'rb-comp-steps-sep';
        sep.textContent = '›';
        box.appendChild(sep);
      }
      const el = doc.createElement('span');
      el.className = 'rb-comp-step';
      el.textContent = s.step;
      if (s.at) el.setAttribute('title', s.at);
      box.appendChild(el);
    });
    return box;
  }

  _count(label, value, title) {
    const el = this.doc.createElement('div');
    el.className = 'rb-comp-count';
    const v = this.doc.createElement('span');
    v.className = 'rb-comp-count-value';
    v.textContent = typeof value === 'number' ? String(value) : '-';
    const k = this.doc.createElement('span');
    k.className = 'rb-comp-count-label';
    k.textContent = label;
    if (title) el.setAttribute('title', title);
    el.append(v, k);
    return el;
  }

  _row(c) {
    const doc = this.doc;
    const el = doc.createElement('div');
    el.className = 'rb-comp-row';
    // The node this row stands for. Marking is BY NODE -- that is the whole coupling.
    const nodeId = c.entityId || c.id;
    if (nodeId) {
      el.setAttribute('data-node-id', nodeId);
      const sign = this.signOf(nodeId);
      if (sign === SIGN.CASE) el.classList.add('is-marked-case');
      else if (sign === SIGN.CONTROL) el.classList.add('is-marked-control');
      // A part with no write name is inert here: `mark` returns without touching the store.
      el.addEventListener('click', (event) => {
        const intent = markingIntent(event);
        this.mark(nodeId, intent.sign, intent.mode);
      });
    }

    // 🔴 THE MOCKUP'S SEVEN COLUMNS, AND EVERY ONE OF THEM IS SERVED (measured 2026-08-23):
    //    층 `component_id` · 코어웨이퍼 `core.wafer` · 랏 `core.lot` · 슬롯 `core.slot` ·
    //    브랜치 `core.branch` · 이력 `core.lineage.events` · 상태 `resolution_state`.
    //    Three of them were already in the response and this panel was throwing them away, so
    //    one row said far less than the ledger knew about it.
    const core = c.core || {};
    const cell = (cls, text, absentTitle) => {
      const n = doc.createElement('span');
      n.className = text === null || text === undefined || text === ''
        ? `${cls} is-absent` : cls;
      // `-` is 「이 응답이 그 칸을 안 줬다」, never 「없다」. The title says which.
      n.textContent = text === null || text === undefined || text === '' ? '-' : String(text);
      if ((text === null || text === undefined || text === '') && absentTitle) {
        n.setAttribute('title', absentTitle);
      }
      return n;
    };

    el.append(
      cell('rb-comp-row-id', this._layerLabel(c.id)),
      cell('rb-comp-row-core', core.wafer, '응답에 코어 웨이퍼가 없습니다'),
      cell('rb-comp-row-lot', core.lot, '응답에 랏이 없습니다'),
      cell('rb-comp-row-slot', core.slot, '응답에 슬롯이 없습니다'),
      cell('rb-comp-row-branch', core.branch, '응답에 브랜치가 없습니다'),
      cell('rb-comp-row-lineage', c.lineage ? c.lineage.events : null, '계보를 안 실어 줬습니다'),
    );
    const state = doc.createElement('span');
    state.className = `rb-comp-row-state is-${c.resolutionState}`;
    state.textContent = c.resolutionState;
    el.appendChild(state);
    return el;
  }

  /** 「SYN-CX-CHIP-001:L04」 -> 「L04」. The chip id is on the panel title already. */
  _layerLabel(id) {
    if (!id) return null;
    const at = String(id).lastIndexOf(':');
    return at >= 0 ? String(id).slice(at + 1) : String(id);
  }
}
