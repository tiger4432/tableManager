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
    root.className = 'rb-comp';

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

    // ── the layers ─────────────────────────────────────────────────────────────
    const table = doc.createElement('div');
    table.className = 'rb-comp-rows';
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
    place(root);
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

    const id = doc.createElement('span');
    id.className = 'rb-comp-row-id';
    id.textContent = c.id || '(id 없음)';

    const core = doc.createElement('span');
    core.className = 'rb-comp-row-core';
    core.textContent = c.core
      ? [c.core.wafer, c.core.slot, c.core.type].filter(Boolean).join(' · ')
      : '-';

    const state = doc.createElement('span');
    state.className = `rb-comp-row-state is-${c.resolutionState}`;
    state.textContent = c.resolutionState;

    const events = doc.createElement('span');
    events.className = 'rb-comp-row-events';
    events.textContent = typeof c.transferEventCount === 'number' ? String(c.transferEventCount) : '-';

    el.append(id, core, state, events);
    return el;
  }
}
