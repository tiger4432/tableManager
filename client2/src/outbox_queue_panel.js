// 「대기열」 — 이 표의 변경으로 «앞으로 무엇이 돌 예정인가»를 행 하나씩 그린다.
//
// 🔴 이름에 「체인」이 없다. 이 표를 비우는 것은 «둘»이고(`owner`), 2026-09-04 에
//    「체인 대기열」이라는 이름이 읽는 사람을 체인으로 보냈다. 서버도 같은 이유로 경로에서
//    뺐다(`/outbox/queue/rows`). 그래서 화면 어디에도 「체인이다」라고 «단정»하지 않는다 —
//    주인은 «행마다» owner 칸이 말한다.
//
// 🔴 판단을 여기서 «다시 내리지» 않는다. 나이 표기는 chain_queue_panel 의 좌석을 부르고,
//    상태 낱말은 서버 어휘를 «그대로» 쓰고, 못 읽은 사유는 fetch 실패 좌석이 짓는다.
//    같은 물음에 두 화면이 다른 답을 낼 자리가 없어야 한다.
//
// 🔴 행은 «안 접는다» (판정 2026-09-22). 접기 단위를 행으로 올리면 이 화면이
//    `/admin/chain/queue` 의 단위로 수렴하고, 두 화면을 가른 근거가 무너진다.
//    여기서 접는 것은 «규칙 줄»이다.
import { formatAge } from './chain_queue_panel.js';

const str = (v) => (v == null ? '' : String(v));
const list = (v) => (Array.isArray(v) ? v : []);

/** 한 행의 규칙 줄. `will_fire=false` 면 «서버의 사유»를 그대로 단다. */
function ruleLines(row) {
  return list(row.rules).map((rule) => ({
    name: str(rule && rule.name),
    willFire: (rule && rule.will_fire) === true,
    // ⛔ 사유를 여기서 짓지 않는다 — 서버가 실은 문장이 정본이다.
    whyNot: str(rule && rule.why_not),
  }));
}

/**
 * 접은 줄이 드는 «수». 총수가 아니라 «사유별»이다 —
 * 「규칙 5」로 접으면 이 화면의 존재 이유인 「왜 안 도나」가 클릭 뒤로 숨는다.
 * ⛔ 사유를 낱말로 «요약»하지 않는다. 묶는 키가 서버 문장이라 두 사유가 한 낱말로 합쳐질 수 없다.
 */
function ruleSummary(rules) {
  let firing = 0;
  const groups = [];
  const at = new Map();
  for (const rule of rules) {
    if (rule.willFire) { firing += 1; continue; }
    if (!at.has(rule.whyNot)) {
      at.set(rule.whyNot, groups.length);
      groups.push({ whyNot: rule.whyNot, count: 0 });
    }
    groups[at.get(rule.whyNot)].count += 1;
  }
  return Object.freeze({ firing, notFiring: Object.freeze(groups.map((g) => Object.freeze(g))) });
}

/**
 * 이 «쪽»의 행들이 한 값으로 모이는 칸이면 그 값, 섞이면 «빈 문자열».
 * 🔴 절대어는 계기를 같은 문장에 달고만 나간다. 그래서 「섞였다」는 말도 «안 한다» —
 *    말할 수 있을 때만 값을 내고, 아니면 그 칸에 대해 아무 말도 안 한다.
 */
function sharedValue(rows, pick) {
  if (!rows.length) return '';
  const first = pick(rows[0]);
  for (const row of rows) if (pick(row) !== first) return '';
  return first;
}

/**
 * 응답 하나를 «그릴 수 있는 모양»으로. 판단은 안 한다.
 * @param {object|null|undefined} payload `/outbox/queue/rows` 의 응답
 * @param {{unavailable?: string, failed?: string}} [opts] `failed` 는 못 받은 «사유»
 */
export function outboxQueueView(payload, opts = {}) {
  const failed = str(opts.failed);
  if (!payload || failed) {
    return Object.freeze({
      read: false,
      // 사유 없는 「모름」은 고칠 자리가 없다. 사유는 부르는 쪽이 준다.
      reason: failed || str(opts.unavailable),
      generatedAt: '', population: '', capped: false, hasMore: false,
      page: Object.freeze({ count: 0, shared: Object.freeze([]) }),
      rows: Object.freeze([]), rulesKnown: Object.freeze([]),
    });
  }
  const listed = payload.listed || {};
  const rows = list(payload.rows).map((row) => {
    const rules = ruleLines(row);
    return Object.freeze({
      id: str(row.outbox_id),
      // 🔴 주인이 «첫 칸»이다 (소유자 판정). 서버가 안 말한 행은 「chain」이 아니라 «—».
      owner: str(row.owner) || '—',
      // 서버가 자리표시자를 «None» 으로 접어 보낸다. 없는 표 이름을 표처럼 그리지 않는다.
      table: str(row.table_name) || '—',
      eventType: str(row.event_type),
      // 읽을 수 없는 나이는 «—», 절대 「0초」가 아니다 — 그 좌석의 규칙 그대로.
      age: formatAge(row.waiting_seconds) ?? '—',
      at: str(row.created_at),
      state: str(row.chain_state),
      // 🔴 「아직 안 돌았다」와 「돌다 실패해 재시도 중」은 둘 다 waiting 이다. 사유를 상태
      //    낱말에 안 섞은 것이 어휘 규율이고, 그 대신 «이 칸»이 말한다. 안 그리면 규율만
      //    지키고 정보는 잃는다 (판정 2026-09-22).
      stateDetail: str(row.state_detail),
      broadcast: str(row.broadcast_state),
      rules: Object.freeze(rules),
      ruleSummary: ruleSummary(rules),
      // 🔴 규칙이 빈 것이 「규칙이 없다」인지 «안 봤다»인지는 이 문장이 가른다. DELETE·제어
      //    행은 트리거가 아니라서 빈 것이고, 빈 칸으로 두면 「규칙이 없다」로 읽힌다.
      note: str(row.note),
    });
  });
  return Object.freeze({
    read: true,
    reason: '',
    // 「지금」은 «서버의 것»이다. 화면이 자기 시계로 나이를 다시 재면 두 수가 갈린다.
    generatedAt: str(payload.generated_at),
    // 🔵 이 표가 «무엇을 담는가»를 서버 문장 그대로. 화면이 자기 경계를 스스로 말한다.
    population: str(payload.population),
    // 🔴 「잘렸다」는 «서버 상한에 닿았다»이다. 「더 있다」는 next_cursor 가 말한다 —
    //    그 둘을 섞으면 5행짜리 큐도 매 쪽 「잘렸다」고 말한다.
    capped: listed.capped === true,
    hasMore: listed.next_cursor != null,
    // 🔴 서버는 행 «수»를 일부러 안 싣는다 — 이 표를 비우는 것이 둘이라 합친 수가
    //    「체인이 밀렸다」로 읽힌다(게이트 ⑪). 그래서 이 수는 «이 쪽»의 수이고,
    //    그 사실은 `hasMore` 와 «한 마디»로 나간다 (render 참조).
    page: Object.freeze({
      count: rows.length,
      shared: Object.freeze([
        sharedValue(rows, (r) => r.table),
        sharedValue(rows, (r) => r.eventType),
        sharedValue(rows, (r) => r.state),
      ].filter(Boolean)),
    }),
    rulesKnown: Object.freeze(list(payload.rules_known).map(String)),
    rows: Object.freeze(rows),
  });
}

/** 조립식 부품: 자기 div 하나, mount·deps 를 생성자로, 모듈 상태 «없음». */
export class OutboxQueuePanel {
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('OutboxQueuePanel needs a mount element');
    this.doc = deps.doc || mount.ownerDocument;
    if (!this.doc) throw new Error('OutboxQueuePanel needs a document (deps.doc or mount.ownerDocument)');
    this.root = this.doc.createElement('div');
    this.root.className = 'queue-panel';
    // 펼친 행. «인스턴스»가 든다 — 같은 화면에 둘을 앉혀도 서로를 안 건드린다.
    this.expanded = new Set();
    this._last = null;
    mount.appendChild(this.root);
  }

  _line(cls, text) {
    const el = this.doc.createElement('div');
    el.className = cls;
    el.textContent = text;
    return el;
  }

  _ruleLine(rule) {
    const el = this._line('queue-rule', rule.willFire ? rule.name : `${rule.name} · ${rule.whyNot}`);
    el.setAttribute('data-fires', rule.willFire ? 'true' : 'false');
    return el;
  }

  /** 「2 돎 · 3 <서버 사유>」. 사유가 없으면 «수만» 말한다 — 없는 사유를 짓지 않는다. */
  _summaryText(summary) {
    const parts = [];
    if (summary.firing) parts.push(`${summary.firing} 돎`);
    for (const g of summary.notFiring) {
      parts.push(g.whyNot ? `${g.count} ${g.whyNot}` : `${g.count} 안 돎`);
    }
    return parts.join(' · ');
  }

  render(payload, opts = {}) {
    this._last = { payload, opts };
    const view = outboxQueueView(payload, opts);
    this.root.textContent = '';

    const head = this.doc.createElement('div');
    head.className = 'queue-head';
    if (view.read) {
      // 설명 문구가 아니라 «값»이다 — 기준 시각과, 이 표가 담는 집합.
      head.appendChild(this._line('queue-at', view.generatedAt));
      if (view.population) head.appendChild(this._line('queue-population', view.population));
      if (view.capped) head.appendChild(this._line('queue-capped', '서버 상한'));
      // 🔴 수와 「다음 쪽」이 «한 마디»다 (판정 조건). 떼어 놓으면 「50」이 «전부»로 읽힌다.
      head.appendChild(this._line('queue-page', [
        `이 쪽 ${view.page.count} 행`,
        ...view.page.shared,
        view.hasMore ? '다음 쪽 있음' : '',
      ].filter(Boolean).join(' · ')));
    } else if (view.reason) {
      head.appendChild(this._line('queue-reason', view.reason));
    }
    this.root.appendChild(head);
    if (!view.read) return view;

    for (const row of view.rows) {
      const line = this.doc.createElement('div');
      line.className = 'queue-row';
      line.setAttribute('data-state', row.state || 'unknown');
      // 주인이 먼저다.
      line.appendChild(this._line('queue-owner', row.owner));
      line.appendChild(this._line('queue-table', row.table));
      line.appendChild(this._line('queue-event', row.eventType));
      line.appendChild(this._line('queue-age', row.age));
      line.appendChild(this._line('queue-state', row.state));
      if (row.stateDetail) line.appendChild(this._line('queue-state-detail', row.stateDetail));
      if (row.rules.length) {
        const open = this.expanded.has(row.id);
        const toggle = this.doc.createElement('button');
        toggle.className = 'queue-rules-toggle';
        toggle.setAttribute('type', 'button');
        toggle.setAttribute('data-expanded', open ? 'true' : 'false');
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        toggle.textContent = `${open ? '▾' : '▸'} ${this._summaryText(row.ruleSummary)}`;
        toggle.addEventListener('click', () => {
          if (this.expanded.has(row.id)) this.expanded.delete(row.id);
          else this.expanded.add(row.id);
          if (this._last) this.render(this._last.payload, this._last.opts);
        });
        line.appendChild(toggle);
        // 펼치면 «이름»을 보러 간다 — 수와 사유는 접힌 줄이 이미 말했다.
        if (open) for (const rule of row.rules) line.appendChild(this._ruleLine(rule));
      }
      if (!row.rules.length && row.note) line.appendChild(this._line('queue-note', row.note));
      this.root.appendChild(line);
    }
    return view;
  }
}
