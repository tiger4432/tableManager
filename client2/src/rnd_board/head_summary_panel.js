// ═══════════════════════════════════════════════════════════════════════════════
// 부품 A — 머리 요약. 「지금 무엇을 보고 있나」 한 줄.
//
// 명세: task/design/rnd_board_component_spec.md §3.
//
// 🔴 THIS PART'S WHOLE JOB IS TELLING ABSENCES APART. Everything it draws is either a fact the
//    ledger stated or a NAMED absence, and the two must not look alike. This repository has
//    been burned by the other habit -- reading 「없음」 as 「고장」 -- so the rule here is
//    concrete: an absence never gets `--danger`, and it never gets an icon that means error.
//
// 🔴 IT DRAWS NO CONCLUSION. It says what was resolved and on what basis. It does not say
//    「원인은 X」, and it does not turn `cardinality: 'variable'` into a number: the ledger
//    refuses to claim a constant there, and a part that prints `10` has invented the claim.
//
// 🔴 NO SIZE CONSTANT. The box comes from the shell; `onResize` just redraws. A part that
//    bakes in a width is a part that gets rewritten the day its corner is dragged.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel } from './panel.js';
import { fetchComposition, compositionModel } from './api.js';

export class HeadSummaryPanel extends Panel {
  /**
   * @param {object} host  the element the shell made for this instance.
   * @param {object} deps  Panel's deps plus `{apiBase, finalChipId, fetchImpl}`.
   */
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    // Per-instance, on `this` -- never module scope. Two of these can stand side by side on
    // one screen looking at two different chips, which is the acceptance condition.
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
    this.host.textContent = '';
    const root = doc.createElement('div');
    root.className = 'rb-head';

    if (this.loadState === 'no-subject') {
      // NOT an error: nobody has picked a chip yet. Says what to do, in one clause.
      root.appendChild(this._note('대상 없음', '칩을 고르면 여기에 나옵니다', 'idle'));
      this.host.appendChild(root);
      return;
    }
    if (this.loadState === 'loading') {
      root.appendChild(this._note('불러오는 중', this.finalChipId, 'idle'));
      this.host.appendChild(root);
      return;
    }
    if (!this.model || !this.model.ok) {
      // A REFUSAL, said as a refusal. This is the one state that may look like a problem,
      // because it is one -- the server answered and said no.
      root.appendChild(this._note('서버 거절', (this.model && this.model.message) || '', 'refused'));
      this.host.appendChild(root);
      return;
    }

    const m = this.model;
    const line = doc.createElement('div');
    line.className = 'rb-head-line';

    const subject = doc.createElement('span');
    subject.className = 'rb-head-subject';
    subject.textContent = m.subject.finalChipId || '(이름 없음)';
    line.appendChild(subject);

    // The wafer, or the fact that there isn't one. `resolution.state` names WHICH absence.
    if (m.wafer && m.wafer.id) {
      line.appendChild(this._chip('웨이퍼', m.wafer.id, 'fact'));
    } else {
      line.appendChild(this._chip('웨이퍼', `해결 안 됨 · ${m.resolution.state}`, 'absent'));
    }

    line.appendChild(this._chip('상태', m.state, 'fact'));

    // 🔴 The basis is shown, not summarised. 「resolved」 alone hides WHAT it was resolved on,
    // and that is the first thing an engineer disputes.
    if (m.resolution.basis) {
      line.appendChild(this._chip('근거', m.resolution.basis, 'fact'));
    }
    if (typeof m.resolution.candidateCount === 'number') {
      line.appendChild(this._chip('후보', String(m.resolution.candidateCount), 'fact'));
    }

    root.appendChild(line);

    // ── the absences, in their own row so they cannot be mistaken for measurements ──
    const absences = doc.createElement('div');
    absences.className = 'rb-head-absences';

    if (m.window.defaulted) {
      // 「기간을 안 골랐다」 ≠ 「기간이 없다」. The server applied its own; say whose it is.
      absences.appendChild(this._chip(
        '기간', `기본값 적용 · ${m.window.spec || '?'} — 고른 적 없음`, 'absent'));
    } else if (m.window.spec) {
      absences.appendChild(this._chip('기간', m.window.spec, 'fact'));
    }

    // `variable` stays the word the ledger chose.
    if (m.cardinality.components) {
      absences.appendChild(this._chip(
        '개수', `${m.cardinality.components} — 상수가 아님`, 'absent'));
    }

    if (!m.provenance.ledgerBacked) {
      absences.appendChild(this._chip('출처', '원장 근거 없음', 'absent'));
    }

    if (absences.children.length) root.appendChild(absences);
    this.host.appendChild(root);
  }

  // ── drawing helpers. `kind` decides the TOKEN class, and 'absent' is never the danger one ──

  _chip(label, value, kind) {
    const el = this.doc.createElement('span');
    el.className = `rb-chip rb-chip--${kind}`;
    const k = this.doc.createElement('span');
    k.className = 'rb-chip-key';
    k.textContent = label;
    const v = this.doc.createElement('span');
    v.className = 'rb-chip-val';
    v.textContent = value;
    el.append(k, v);
    return el;
  }

  _note(title, detail, kind) {
    const el = this.doc.createElement('div');
    el.className = `rb-head-note rb-head-note--${kind}`;
    const t = this.doc.createElement('span');
    t.className = 'rb-head-note-title';
    t.textContent = title;
    el.appendChild(t);
    if (detail) {
      const d = this.doc.createElement('span');
      d.className = 'rb-head-note-detail';
      d.textContent = detail;
      el.appendChild(d);
    }
    return el;
  }
}
