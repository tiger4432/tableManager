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
      rows: Object.freeze([]), rulesKnown: Object.freeze([]),
    });
  }
  const listed = payload.listed || {};
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
    rulesKnown: Object.freeze(list(payload.rules_known).map(String)),
    rows: Object.freeze(list(payload.rows).map((row) => Object.freeze({
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
      rules: Object.freeze(ruleLines(row)),
      // 🔴 규칙이 빈 것이 「규칙이 없다」인지 «안 봤다»인지는 이 문장이 가른다. DELETE·제어
      //    행은 트리거가 아니라서 빈 것이고, 빈 칸으로 두면 「규칙이 없다」로 읽힌다.
      note: str(row.note),
    }))),
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
    mount.appendChild(this.root);
  }

  _line(cls, text) {
    const el = this.doc.createElement('div');
    el.className = cls;
    el.textContent = text;
    return el;
  }

  render(payload, opts = {}) {
    const view = outboxQueueView(payload, opts);
    this.root.textContent = '';

    const head = this.doc.createElement('div');
    head.className = 'queue-head';
    if (view.read) {
      // 설명 문구가 아니라 «값»이다 — 기준 시각과, 이 표가 담는 집합.
      head.appendChild(this._line('queue-at', view.generatedAt));
      if (view.population) head.appendChild(this._line('queue-population', view.population));
      if (view.capped) head.appendChild(this._line('queue-capped', '서버 상한'));
      if (view.hasMore) head.appendChild(this._line('queue-more', '다음 쪽 있음'));
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
      for (const rule of row.rules) {
        const el = this._line('queue-rule', rule.willFire ? rule.name : `${rule.name} · ${rule.whyNot}`);
        el.setAttribute('data-fires', rule.willFire ? 'true' : 'false');
        line.appendChild(el);
      }
      if (!row.rules.length && row.note) line.appendChild(this._line('queue-note', row.note));
      this.root.appendChild(line);
    }
    return view;
  }
}
