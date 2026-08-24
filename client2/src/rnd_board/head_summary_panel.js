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
import { createWalk } from './api.js';

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
    // 🔴 ONE CALL — 소유자가 그린 데이터 흐름(2026-08-24): 부품은 { start, collect } 만 선언하고
    //    라우트·질의·모델을 다시는 부르지 않습니다. 화면이 walk 하나를 «주입»하므로 같은 walk 을
    //    쓰는 두 부품이 요청 하나를 나눠 씁니다. 혼자 서는 부품은 자기 것을 만듭니다.
    this.walk = options.walk || createWalk({ apiBase: options.apiBase, fetchImpl: options.fetchImpl });
    // 시작점과 걷는 종류. 값이고 축이 아닙니다 — 소유자: 「일단 wafer 로 고정」.
    this.start = options.start || null;
    this.collect = options.collect || 'wafer_process';
    this.finalChipId = options.finalChipId || null;
    this.fetchImpl = options.fetchImpl || null;
    // 목업 ① 의 웨이퍼 줄. Per-kind, because the route answers one kind at a time.
    this.waferKinds = Array.isArray(options.waferKinds) ? options.waferKinds.slice() : [];
    this.loadWaferFacts = options.loadWaferFacts || null;
    // 🔴 목업이 머리에 다는 「마킹 1 · 34행」 · 「마킹 2 · 1행」. 이름은 «선언»입니다 -- 이 부품은
    //    1 과 2 가 무엇인지 모르고, 화면이 세 번째를 더해도 여기는 안 바뀝니다.
    this.markingRows = Array.isArray(options.markingRows) ? options.markingRows.slice() : [];
    this._rowOffs = [];
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
    for (const name of this.markingRows) {
      if (this.markings) this._rowOffs.push(this.markings.subscribe(name, () => this.render()));
    }
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
    this.model = await this.walk({
      start: this.start || { groupby: 'chip', value: this.finalChipId },
      collect: this.collect,
    });
    this.loadState = this.model.ok ? 'ready' : 'refused';
    this.render();
  }

  /**
   * 「이 칩이 앉은 웨이퍼와 그 수」 -- added beside the subject, not instead of it.
   *
   * 🔴 A KIND THAT HAS NOT ANSWERED IS NOT DRAWN. The second request lands later than the first
   *    and a 0 in its place would say 「delam 없음」 about a wafer nobody has asked about yet.
   */
  /**
   * 🔴 목업 머리의 «둘째 줄» — 「이 본딩 웨이퍼 자신의 스텝 4」와 그 알약들.
   *    자리를 «만들고» 비면 이유를 적습니다 (총괄 규칙 2026-08-24: 데이터가 없다고 멈추지 말 것).
   *    오늘 이 웨이퍼는 구성이 없으므로 스텝도 «안 옵니다» -- 그것이 참이고 정보입니다.
   */
  _stepLine() {
    const doc = this.doc;
    const steps = ((this.model && this.model.components) || [])
      .flatMap((c) => c.steps || []);
    const el = doc.createElement('div');
    el.className = 'rb-head-steps';
    const key = doc.createElement('span');
    key.className = 'rb-head-steps-key';
    key.textContent = steps.length ? `이 웨이퍼 자신의 스텝 ${steps.length}` : '이 웨이퍼 자신의 스텝';
    el.appendChild(key);
    if (!steps.length) {
      const none = doc.createElement('span');
      none.className = 'rb-head-steps-absent';
      none.textContent = '응답에 스텝이 없습니다 — 구성이 없는 웨이퍼입니다';
      el.appendChild(none);
      return el;
    }
    steps.forEach((s, i) => {
      if (i > 0) {
        const sep = doc.createElement('span');
        sep.className = 'rb-head-steps-sep';
        sep.textContent = '›';
        el.appendChild(sep);
      }
      const pill = doc.createElement('span');
      pill.className = 'rb-head-step';
      pill.textContent = s.step;
      if (s.at) pill.setAttribute('title', s.at);
      el.appendChild(pill);
    });
    return el;
  }

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
    if (first.wafer) put(`씨앗 웨이퍼 ${first.wafer}`, 'rb-head-wafer-subject');
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
    // 🔴 목업이 머리에 다는 마킹 행수. 이 수는 «맵의 수와 다른 것»입니다 -- 맵은 그 그림에
    //    그려진 칸을, 이건 «지금 찍혀 있는 행»을 셉니다. 그래서 같은 줄에 나란히 둡니다.
    for (const name of this.markingRows) {
      const n = this.markings ? this.markings.count(name) : 0;
      put(`${name} · ${n}행`, n > 0 ? 'rb-head-wafer-mark is-live' : 'rb-head-wafer-mark');
    }
    return el;
  }

  destroy() {
    if (this._subjectOff) this._subjectOff();
    this._subjectOff = null;
    for (const off of this._rowOffs) off();
    this._rowOffs = [];
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
      // 🔴 이 칩이 «앉은» 웨이퍼입니다 -- 아래 줄의 「씨앗 웨이퍼」와 «다른 대상»일 수 있고,
      //    실제로 지금 다릅니다(칩 계열과 목업 웨이퍼는 서로 다른 자재입니다). 둘 다 「웨이퍼」로
      //    적으면 두 대상의 수가 «한 대상»의 것으로 읽힙니다.
      line.appendChild(this._chip('칩이 앉은 웨이퍼', m.wafer.id, 'fact'));
    } else {
      line.appendChild(this._chip('칩이 앉은 웨이퍼', `해결 안 됨 · ${m.resolution.state}`, 'absent'));
    }

    line.appendChild(this._chip('상태', m.state, 'fact'));
    // 🔴 THE BASIS AND THE CANDIDATE COUNT MOVED TO 구성 (목업 2a). They belong beside the layers
    //    they explain, and having them in both bands is the same fact said twice on one screen.

    root.appendChild(line);
    const waferLine = this._waferLine();
    if (waferLine) root.appendChild(waferLine);
    // 목업의 둘째 줄. 비어도 «자리»는 섭니다 -- 없는 것은 없다고 말하는 자리입니다.
    root.appendChild(this._stepLine());

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
