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
    this.walkFn = options.walk || null;
    this.collect = options.collect || 'wafer_process';
    this.finalChipId = options.finalChipId || null;
    this.model = null;
    this.loadState = 'idle';
  }

  mount() {
    super.mount();
    this.load();
  }

  async load() {
    if (!this.walkFn) { this.loadState = 'idle'; this.render(); return; }
    this.loadState = 'loading';
    this.render();
    this.model = await this.walkFn({
      start: this.start || { groupby: 'chip', value: this.finalChipId },
      collect: this.collect,
    });
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
      note.textContent = this.loadState === 'loading' ? '읽는 중…'
        : (this.loadState === 'ready' ? '층을 찍으면 여기에 펼칩니다'
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
