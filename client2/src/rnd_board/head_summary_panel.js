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
    // 목업 ① 의 웨이퍼 줄. Per-kind, because the route answers one kind at a time.
    this.waferKinds = Array.isArray(options.waferKinds) ? options.waferKinds.slice() : [];
    this.loadWaferFacts = options.loadWaferFacts || null;
    this.waferFacts = Object.create(null);
    // 🔴 THE WAFER LINE FOLLOWS THE MARKING. 「마킹 -> 머리요약」 (owner): picking a point in the
    //    trend moves the maps, and this band has to move with them or it describes a wafer
    //    nobody is looking at any more.
    this.subjectReads = options.subjectReads || null;
    this.subjectWafer = null;
    this._subjectOff = null;
    this.model = null;
    this.loadState = this.finalChipId ? 'idle' : 'no-subject';
  }

  mount() {
    super.mount();
    if (this.finalChipId) this.load();
    if (this.subjectReads && this.markings) {
      this._subjectOff = this.markings.subscribe(this.subjectReads, () => this._onSubject());
      this._onSubject();
    }
    if (this.loadWaferFacts) {
      for (const kind of this.waferKinds) {
        Promise.resolve().then(() => this.loadWaferFacts(kind, this.subjectWafer))
          .then((facts) => { if (facts) { this.waferFacts[kind] = facts; this.render(); } })
          // A kind that failed stays absent, which draws as nothing rather than as zero.
          .catch(() => {});
      }
    }
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

  /**
   * 「이 칩이 앉은 웨이퍼와 그 수」 -- added beside the subject, not instead of it.
   *
   * 🔴 A KIND THAT HAS NOT ANSWERED IS NOT DRAWN. The second request lands later than the first
   *    and a 0 in its place would say 「delam 없음」 about a wafer nobody has asked about yet.
   */
  _waferLine() {
    const kinds = this.waferKinds.filter((k) => this.waferFacts[k]);
    if (!kinds.length) return null;
    const doc = this.doc;
    const first = this.waferFacts[kinds[0]];
    const el = doc.createElement('div');
    el.className = 'rb-head-wafer';
    const put = (text, cls) => {
      const n = doc.createElement('span');
      n.className = cls || 'rb-head-wafer-fact';
      n.textContent = text;
      el.appendChild(n);
    };
    if (first.wafer) put(`웨이퍼 ${first.wafer}`, 'rb-head-wafer-subject');
    if (first.lot) put(`랏 ${first.lot}`);
    if (typeof first.cells === 'number') put(`${first.cells}칸`);
    for (const kind of kinds) {
      const f = this.waferFacts[kind];
      if (typeof f.found !== 'number') continue;
      put(`${kind} ${f.found}`, 'rb-head-wafer-kind');
    }
    if (typeof first.scanned === 'number') put(`검사 ${first.scanned}`);
    // The kinds still in flight are named, so a missing one reads as 「아직」 rather than 「없음」.
    const pending = this.waferKinds.filter((k) => !this.waferFacts[k]);
    if (pending.length) put(`${pending.join(' · ')} 읽는 중…`, 'rb-head-wafer-pending');
    return el;
  }

  destroy() {
    if (this._subjectOff) this._subjectOff();
    this._subjectOff = null;
    super.destroy();
  }

  /** The screen moved to another wafer; re-read this band's facts for it. */
  _onSubject() {
    const entries = this.markings ? this.markings.entries(this.subjectReads) : [];
    const wafer = entries.length ? entries[0][0] : null;
    if (!wafer || wafer === this.subjectWafer) return;
    this.subjectWafer = wafer;
    // Cleared, not left stale: the old wafer's numbers under a new wafer's name would be a lie.
    this.waferFacts = Object.create(null);
    this.render();
    if (!this.loadWaferFacts) return;
    for (const kind of this.waferKinds) {
      Promise.resolve().then(() => this.loadWaferFacts(kind, wafer))
        .then((facts) => { if (facts) { this.waferFacts[kind] = facts; this.render(); } })
        .catch(() => {});
    }
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    this.host.textContent = '';
    const root = doc.createElement('div');
    root.className = 'rb-head';
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
    // 🔴 THE BASIS AND THE CANDIDATE COUNT MOVED TO 구성 (목업 2a). They belong beside the layers
    //    they explain, and having them in both bands is the same fact said twice on one screen.

    root.appendChild(line);
    const waferLine = this._waferLine();
    if (waferLine) root.appendChild(waferLine);

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
