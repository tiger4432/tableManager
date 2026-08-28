// ═══════════════════════════════════════════════════════════════════════════════
// 펼친 층 — 목업의 세 번째 구성 칸. 「층 표에서 «찍은» 층 하나」를 펼칩니다.
//
// 🔴 이 패널은 «질의를 하지 않습니다». 구성 walk 이 이미 걸어 온 답에서 «마킹된 층»을 골라
//    다시 그릴 뿐입니다 -- 확대가 새 질의가 아닌 것과 같은 이유입니다(총괄 판정 2026-08-24).
//    그래서 선언은 「어느 마킹을 읽나」와 「무엇을 걷나」 둘뿐입니다.
//
// 🔴 아직 안 골랐다 ≠ 없다. 마킹이 비면 「층을 찍으면 펼칩니다」라고 말합니다. 빈 상자가 아닙니다.
//
// 🔴 claims 표는 «표 부품»입니다 (선언 셋째). 구성 표·순위 표와 같은 코드이고 컬럼만 다릅니다.
//    ⚠️ 오늘 그 표는 «비어 있습니다» -- `compositionModel` 이 컴포넌트를 줄이면서
//       `upstream_process.events` 를 버려서 claims_present·parameters 가 이 부품까지 안 옵니다.
//       실측(2026-08-24)으로 원장에는 있습니다: 이벤트 27개, 각각 claims_present·payload·recipe.
//       `api.js` 는 응용 레인 파일이라 여기서 안 고치고 «빈 이유»를 화면이 말하게 했습니다.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel } from './panel.js';
import { SIGN } from './marking_store.js';
import { TablePart } from './table_part.js';

export class ExpandedLayerPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    // 🔴 좌석의 `start` 를 «여기서» 받습니다 (round Z-3, 2026-08-28). `Panel` 밑절은 `startFor()`
    //    에서 `this.start` 를 «읽기만» 하고 대입하지 않습니다 -- 구성·머리 두 부품은 각자 이 줄을
    //    들고 있었고 «이 부품만 없었습니다». 그래서 좌석이 마킹을 선언해도 주어가 늘 박힌 칩으로
    //    떨어져 `id=SYN-CX-CHIP-001` 이 나갔고 422 였습니다.
    //    ⚠️ 그 요청은 walk 의 합침 때문에 화면 전체에서 «한 번»만 보입니다 -- 그래서 어제는
    //    「이 좌석은 요청을 안 낸다」로 읽었습니다. 세 좌석이 같은 하나를 나눠 쓰고 있었습니다.
    this.start = options.start || null;
    this.walkFn = options.walk || null;
    this.collect = options.collect || 'wafer_process';
    // 🔴 좌석이 라우트 이름을 안 대면 «합성 루트가 묶어 준 걷기»를 씁니다 (round Z-3).
    //    이 기본값이 살아 있으면 좌석이 이름을 지웠는데도 죽은 라우트를 계속 부릅니다.
    this.boundWalk = options.load || null;
    this.finalChipId = options.finalChipId || null;
    this.model = null;
    this.loadState = 'idle';
  }

  /**
   * 이 부품의 «주어». 좌석이 마킹을 선언했으면 마킹이고, 아니면 좌석이 박아 준 것입니다.
   *
   * 🔴 두 길이 다 삽니다 (round Z-3, 2026-08-28). 화면의 좌석 셋은 «마킹»을 선언하고, 그때
   *    빈 마킹은 `null` -- 「아직 안 골랐다」이지 부재가 아닙니다. 마킹을 «선언하지 않은»
   *    호출자(픽스처가 그렇습니다)는 종전처럼 박힌 주어로 섭니다. 갈래를 «선언»이 정하지
   *    부품이 값을 보고 추측하지 않습니다.
   */
  subjectStart() {
    if (this.start && this.start.marking) return this.startFor();
    return this.start || (this.finalChipId ? { groupby: 'chip', value: this.finalChipId } : null);
  }

  mount() {
    super.mount();
    // 🔴 마킹이 비면 «묻지 않습니다» (round Z-3). 빈 주어로 물으면 답이 거절이고, 화면엔
    //    「서버가 거절했습니다」가 뜹니다 -- 그건 「아직 안 골랐다」를 «고장»으로 그리는 것이고
    //    다른 두 좌석은 이미 그렇게 하고 있었습니다. 이 좌석만 무조건 물어서 404 를 그렸습니다.
    if (this.subjectStart()) this.load();
  }

  async load() {
    if (!this.walkFn && !this.boundWalk) { this.loadState = 'idle'; this.render(); return; }
    // 🔴 주어가 없으면 «묻지 않습니다» — mount 뿐 아니라 «여기»에서도. 마킹 구독이 다시
    //    부르는 길이 있어서 mount 의 관문만으로는 새어 나갔고, 빈 주어로 물으면 422 입니다
    //    (실측 2026-08-28: 「서버가 거절했습니다 (HTTP 422)」가 화면에 떴습니다).
    if (!this.subjectStart()) { this.loadState = 'idle'; this.render(); return; }
    this.loadState = 'loading';
    this.render();
    this.model = await (this.boundWalk
      ? this.boundWalk({ start: this.subjectStart() })
      : this.walkFn({
      // 🔴 마킹이 «주어»입니다 (round Z-3). 칩 id 로 물으면 원장에 0건이라 좌석이 404 였고,
      //    `startFor()` 는 마킹이 비면 «null» 을 줍니다 -- 그게 「아직 안 골랐다」이고 부재가
      //    아닙니다. 박힌 씨앗으로 되돌아가지 «않습니다»: 그 값은 원장이 모르는 이름입니다.
      start: this.subjectStart(),
      collect: this.collect,
      }));
    this.loadState = this.model && this.model.ok ? 'ready' : 'refused';
    this.render();
  }

  /** 지금 «찍힌» 층. 마킹은 노드 집합이므로 컴포넌트의 노드 id 로 맞춥니다. */
  _marked() {
    const list = (this.model && this.model.components) || [];
    return list.find((c) => this.signOf(c.entityId || c.id) !== SIGN.ABSENT) || null;
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    this.host.textContent = '';
    const root = doc.createElement('div');
    root.className = 'rb-layer';

    if (this.title) {
      const cap = doc.createElement('div');
      cap.className = 'rb-part-title';
      cap.textContent = this.title;
      root.appendChild(cap);
    }

    const marked = this.loadState === 'ready' ? this._marked() : null;
    if (!marked) {
      const note = doc.createElement('div');
      note.className = 'rb-layer-note';
      // 넷 중 첫째 부재입니다 -- 「없다」가 아니라 「아직 안 골랐다」.
      // 🔴 idle 은 «아직 안 물었다» 입니다 (round Z-3). 마킹이 비면 mount 가 묻지 않으므로
      //    여기에 머무는데, 종전 문장은 「구성을 못 읽었습니다」였습니다 -- 이 파일 머리가
      //    「아직 안 골랐다 ≠ 없다」라고 적어 두고 정작 그 자리에서 «고장»으로 그렸습니다.
      note.textContent = this.loadState === 'idle' ? '층을 찍으면 여기에 펼칩니다'
        : this.loadState === 'loading' ? '읽는 중…'
        : (this.loadState === 'ready'
          ? (((this.model && this.model.components) || []).length
            ? '층을 찍으면 여기에 펼칩니다'
            : '이 웨이퍼는 구성 기록이 없습니다 — 펼칠 층이 없습니다')
          : (this.model && this.model.message) || '구성을 못 읽었습니다');
      root.appendChild(note);
      this.host.appendChild(root);
      return;
    }

    const head = doc.createElement('div');
    head.className = 'rb-layer-head';
    head.textContent = `${this._layerLabel(marked.id)} · ${(marked.core && marked.core.wafer) || '코어 웨이퍼 없음'}`;
    root.appendChild(head);

    root.appendChild(this._steps(marked));

    // claims 표 — 표 부품의 «셋째 선언». 컬럼만 다르고 코드는 구성·순위 표와 한 벌입니다.
    const tableHost = doc.createElement('div');
    tableHost.className = 'rb-layer-claims';
    const claims = new TablePart(tableHost, {
      doc,
      markings: this.markings,
      reads: this.reads,
      writes: null,
      emptyText: '이 응답에 claim 이 없습니다 — 원장에는 있고 경계가 아직 안 싣습니다',
      columns: [
        { key: 'claim', label: 'claims_present', width: 'minmax(0, 1fr)', kind: 'mono' },
        { key: 'actual', label: 'actual', width: '5rem', align: 'right' },
        { key: 'setpoint', label: 'setpoint', width: '5rem', align: 'right' },
      ],
      rows: this._claimRows(marked),
    });
    claims.mount();
    root.appendChild(tableHost);

    this.host.appendChild(root);
  }

  /** 스텝 사슬. 목업의 알약 줄입니다 -- 순서는 원장이 준 순서 그대로입니다. */
  _steps(component) {
    const doc = this.doc;
    const box = doc.createElement('div');
    box.className = 'rb-layer-steps';
    const steps = component.steps || [];
    if (!steps.length) {
      const none = doc.createElement('span');
      none.className = 'rb-layer-step is-absent';
      none.textContent = '스텝이 응답에 없습니다';
      box.appendChild(none);
      return box;
    }
    steps.forEach((s, i) => {
      if (i > 0) {
        const sep = doc.createElement('span');
        sep.className = 'rb-layer-sep';
        sep.textContent = '›';
        box.appendChild(sep);
      }
      const el = doc.createElement('span');
      el.className = 'rb-layer-step';
      el.textContent = s.step;
      if (s.at) el.setAttribute('title', s.at);
      box.appendChild(el);
    });
    return box;
  }

  /**
   * claims 행. ⚠️ 오늘은 «항상 빈 배열»입니다 -- 경계가 `events` 를 안 실어서입니다.
   * 실리는 날 이 함수만 값을 보게 되고 표도 선언도 안 바뀝니다.
   */
  _claimRows(component) {
    const events = component.events || [];
    const rows = [];
    for (const e of events) {
      for (const name of e.claims_present || []) {
        const param = (e.parameters || []).find((p) => p && p.name === name) || null;
        rows.push({
          claim: name,
          actual: param ? param.actual : null,
          setpoint: param ? param.setpoint : null,
        });
      }
    }
    return rows;
  }

  /** 「SYN-CX-CHIP-001:L04」 -> 「L04」. 칩 id 는 제목에 이미 있습니다. */
  _layerLabel(id) {
    if (!id) return '층 없음';
    const at = String(id).lastIndexOf(':');
    return at >= 0 ? String(id).slice(at + 1) : String(id);
  }
}
