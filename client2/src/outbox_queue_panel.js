// 「대기열」 — 이 표의 변경으로 «앞으로 무엇이 돌 예정인가»를 행 하나씩 그린다.
//
// 🔴 이름에 「체인」이 없다. 이 표를 비우는 것은 «둘»이고(`owner`), 2026-09-04 에
//    「체인 대기열」이라는 이름이 읽는 사람을 체인으로 보냈다. 서버도 같은 이유로 경로에서
//    뺐다(`/outbox/queue/rows`). 그래서 화면 어디에도 「체인이다」라고 «단정»하지 않는다 —
//    주인은 «행마다» owner 칸이 말한다.
//
// 🔴 판단을 여기서 «다시 내리지» 않는다. 나이 표기는 chain_queue_panel 의 좌석을 부르고,
//    상태 낱말은 서버 어휘를 «그대로» 쓰고, 못 읽은 사유는 fetch 실패 좌석이 짓는다.
//
// 🔴 행은 «안 접는다» (판정 2026-09-22). 그리고 규칙도 이제 접을 것이 없다 — 소유자가
//    「거기에 triger되는 규칙들을 컬럼 추가해서 달면 될것 같아」 · 「표 양식 감사 로그랑
//    정확히 똑같이해」라 하셔서 «한 행이 한 줄»이고 규칙은 «칸»이다.
//    ⚠️ 폭이 모자란다 — 실측(2026-09-22, 493px 판): 규칙 칸에 쓸 수 있는 글자 폭 124px,
//       가장 «짧은» 사유 한 줄이 302px. 그래서 칸은 자르고 온 문장은 `title` 이 든다.
//
// 🔴 실패 행은 이 표에 «안 온다» — 서버가 모집단에서 뺐다(`2eb1d38d`). 그 사실을 화면에
//    적지 않는 것은 화면이 «지금 있는 것»만 말하기 때문이다. 모집단 문장이 경계를 말한다.
import { formatAge } from './chain_queue_panel.js';

const str = (v) => (v == null ? '' : String(v));
const list = (v) => (Array.isArray(v) ? v : []);

/** 한 행의 규칙 줄. `will_fire=false` 면 «서버의 사유»를 그대로 단다. */
function ruleLines(row) {
  return list(row.rules).map((rule) => ({
    name: str(rule && rule.name),
    // ⛔ 사유를 여기서 짓지 않는다 — 서버가 실은 문장이 정본이다.
    willFire: (rule && rule.will_fire) === true,
    whyNot: str(rule && rule.why_not),
  }));
}

/**
 * 규칙 칸이 드는 «수». 총수가 아니라 «사유별»이다 —
 * 「규칙 5」로 접으면 이 화면의 존재 이유인 「왜 안 도나」가 사라진다.
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

/** 「2 돎 · 3 <서버 사유>」. 사유가 없으면 «수만» — 없는 사유를 짓지 않는다. */
export function summaryText(summary) {
  const parts = [];
  if (summary.firing) parts.push(`${summary.firing} 돎`);
  for (const g of summary.notFiring) {
    parts.push(g.whyNot ? `${g.count} ${g.whyNot}` : `${g.count} 안 돎`);
  }
  return parts.join(' · ');
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
      generatedAt: '', population: '', hasMore: false, empty: false,
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
      //    낱말에 안 섞은 것이 어휘 규율이고, 그 대신 «이 칸»이 말한다 (판정 2026-09-22).
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
    hasMore: listed.next_cursor != null,
    // 🔴 「비었다」는 «읽고 나서만» 참이다. 못 읽은 것과 같은 픽셀이면 안 된다.
    empty: rows.length === 0,
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

/** 머리줄 낱말. 열 «순서»가 여기 한 곳에 산다 — 행과 머리가 갈릴 자리가 없다. */
const COLUMNS = Object.freeze([
  Object.freeze({ key: 'owner', label: '주인' }),
  Object.freeze({ key: 'table', label: '표' }),
  Object.freeze({ key: 'event', label: '사건' }),
  Object.freeze({ key: 'age', label: '나이' }),
  Object.freeze({ key: 'state', label: '상태' }),
  Object.freeze({ key: 'rules', label: '규칙' }),
]);

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

  /** 한 «칸». 칸 자체는 flex 라 그 위의 ellipsis 는 안 먹는다. */
  _cell(cls, text, title) {
    const el = this._line(`audit-cell queue-cell ${cls}`, text);
    if (title) el.setAttribute('title', title);
    return el;
  }

  /**
   * 넘치면 «자르는» 칸. 자르는 것은 «안쪽» 요소여야 한다 — `.audit-cell` 이 flex 라
   * 칸에 건 `text-overflow` 는 익명 텍스트에 안 걸린다. 감사 표가 `.audit-change .val-old`
   * 를 두는 이유가 이것이고, 온 문장은 `title` 이 든다.
   */
  _clipCell(cls, text) {
    const el = this._line(`audit-cell queue-cell ${cls}-cell`, '');
    const inner = this._line(cls, text);
    if (text) inner.setAttribute('title', text);
    el.appendChild(inner);
    return el;
  }

  render(payload, opts = {}) {
    const view = outboxQueueView(payload, opts);
    this.root.textContent = '';

    const meta = this.doc.createElement('div');
    meta.className = 'queue-meta';
    if (view.read) {
      // 설명 문구가 아니라 «값»이다 — 기준 시각과, 이 표가 담는 집합.
      meta.appendChild(this._line('queue-at', view.generatedAt));
      if (view.population) meta.appendChild(this._line('queue-population', view.population));
      // 🔴 수와 「다음 쪽」이 «한 마디»다 (판정 조건). 떼어 놓으면 「50」이 «전부»로 읽힌다.
      if (!view.empty) {
        meta.appendChild(this._line('queue-page', [
          `이 쪽 ${view.page.count} 행`,
          ...view.page.shared,
          view.hasMore ? '다음 쪽 있음' : '',
        ].filter(Boolean).join(' · ')));
      }
    } else if (view.reason) {
      meta.appendChild(this._line('queue-reason', view.reason));
    }
    this.root.appendChild(meta);
    if (!view.read) return view;

    // 🔴 0 행에 «빈 표»를 그리지 않는다 — 그건 「안 읽혔다」와 같은 픽셀이다.
    if (view.empty) {
      this.root.appendChild(this._line('queue-empty', '지금 돌 것이 없습니다'));
      return view;
    }

    const head = this.doc.createElement('div');
    head.className = 'audit-head queue-head';
    // 🔴 머리 칸은 «행 칸의 이름»을 안 쓴다 — `.queue-rules` 가 머리줄 글꼴까지 덮는다.
    for (const col of COLUMNS) head.appendChild(this._cell(`queue-h-${col.key}`, col.label));
    this.root.appendChild(head);

    const body = this.doc.createElement('div');
    body.className = 'queue-rows';
    for (const row of view.rows) {
      const line = this.doc.createElement('div');
      line.className = 'queue-row';
      line.setAttribute('data-state', row.state || 'unknown');
      // 주인이 먼저다.
      line.appendChild(this._cell('queue-owner', row.owner));
      line.appendChild(this._clipCell('queue-table', row.table));
      line.appendChild(this._cell('queue-event', row.eventType));
      line.appendChild(this._cell('queue-age', row.age, row.at));

      const state = this._cell('queue-state', '');
      state.appendChild(this._line('audit-pill', row.state));
      // 「기다리는 중」과 「재시도 중」을 가르는 것은 이 칸이다 — 상태 낱말은 둘 다 waiting 이다.
      // 좁아서 잘린다(실측: 배지 뒤 21px). 잘린 글자의 답은 이 화면에서 «하나»다 — title.
      if (row.stateDetail) {
        const detail = this._line('queue-state-detail', row.stateDetail);
        detail.setAttribute('title', row.stateDetail);
        state.appendChild(detail);
      }
      line.appendChild(state);

      // 규칙이 없는 행은 «왜 없는지»를 서버 문장이 말한다. 빈 칸으로 두면 「규칙이 없다」로 읽힌다.
      const text = row.rules.length ? summaryText(row.ruleSummary) : row.note;
      line.appendChild(this._clipCell(row.rules.length ? 'queue-rules' : 'queue-note', text));
      body.appendChild(line);
    }
    this.root.appendChild(body);
    return view;
  }
}
