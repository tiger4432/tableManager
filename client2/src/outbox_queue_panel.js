// 「대기열」 — 이 표의 변경으로 «앞으로 무엇이 돌 예정인가»를 행 하나씩 그린다.
//
// 🔴 이름에 「체인」이 없다. 이 표를 비우는 것은 «둘»이고(`owner`), 2026-09-04 에
//    「체인 대기열」이라는 이름이 읽는 사람을 체인으로 보냈다. 서버도 경로에서 뺐다.
// 🔴 판단을 여기서 «다시 내리지» 않는다 — 나이는 chain_queue_panel 의 좌석, 상태는 서버 어휘.
// 🔴 실패 행은 이 표에 «안 온다» — 서버가 모집단에서 뺐다(`2eb1d38d`). 경계는 모집단 문장이 말한다.
import { chainStateCell, formatAge, line } from './chain_queue_panel.js';

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
      // The server's `{state, why}` (248ae20cd); `state_detail` folded into its why.
      state: str(row.chain_state && row.chain_state.state),
      chainState: row.chain_state || null,
      slotPid: row.slot_pid ?? null,
      broadcast: str(row.broadcast_state),
      rules: Object.freeze(rules),
    });
  });
  return Object.freeze({
    read: true,
    reason: '',
    // 「지금」은 «서버의 것»이다. 화면이 자기 시계로 나이를 다시 재면 두 수가 갈린다.
    generatedAt: str(payload.generated_at),
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
  Object.freeze({ key: 'owner', label: 'Owner' }),
  Object.freeze({ key: 'table', label: 'Table' }),
  Object.freeze({ key: 'event', label: 'Event' }),
  Object.freeze({ key: 'age', label: 'Age' }),
  Object.freeze({ key: 'state', label: 'State' }),
  Object.freeze({ key: 'rules', label: 'Rules' }),
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
    // A hidden tab measures 0: the column is fitted again when the panel shows or changes width.
    const view = this.doc.defaultView;
    if (view && view.ResizeObserver) new view.ResizeObserver(() => this._fitState()).observe(this.root);
  }

  /** The State column as wide as its widest tag plus the cell's padding (owner 10-09: the tag was cut at 96px);
   *  the Rules column (1fr) gives the room. */
  _fitState() {
    const view = this.doc.defaultView;
    if (!view || !view.getComputedStyle) return;
    let need = 0;
    for (const tag of this.root.querySelectorAll('.queue-state .tag')) {
      const cell = tag.closest('.queue-cell');
      const cs = view.getComputedStyle(cell);
      need = Math.max(need, tag.offsetWidth + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight) + parseFloat(cs.borderRightWidth));
    }
    if (need) this.root.style.setProperty('--queue-state-w', `${Math.ceil(need)}px`);
  }

  _line(cls, text) { return line(this.doc, cls, text); }

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
    inner.setAttribute('data-clip-ok', '');
    el.appendChild(inner);
    return el;
  }

  /**
   * 규칙 «하나»에 줄 «하나». 이름을 대고, 안 돌면 서버 문장을 그대로 단다.
   *
   * 🔴 소유자 2026-09-23: 「어떤 rule 인지 구체적으로 적어 «접지말고»」 — 행이 왜 안 빠지는지를
   *    이 칸으로 찾고 계신다. 「3 <사유>」로 세면 «어느» 규칙인지가 사라진다.
   * ⛔ 사유를 짓지도 요약하지도 않는다. 사유 칸의 저자는 «서버»다 — 사유가 없을 때만
   *    「안 돈다」는 사실을 우리 낱말로 적고, 그건 사유가 아니다.
   */
  _rulesCell(rules) {
    const cell = this._line('audit-cell queue-cell queue-rules-cell', '');
    // 🔴 규칙이 «없는» 행은 아직 온다 — 제어 행이 그렇다(서버 `9c09e5c34`: 「그 행 자체가 일이고
    //    스케줄러가 돌린다」). 왜 없는지의 «문장»은 서버가 내던 것인데 그 칸이 같이 없어졌다.
    //    없는 사유를 화면이 지어내지 않는다. 사실만 적고, 문장은 서버가 다시 보낼 때 그 자리로 온다.
    if (!rules.length) {
      cell.appendChild(this._line('queue-rule-none', 'no rules'));
      return cell;
    }
    for (const rule of rules) {
      const one = this._line('queue-rule', '');
      one.setAttribute('data-firing', rule.willFire ? 'yes' : 'no');
      one.appendChild(this._line('queue-rule-name', rule.name || '—'));
      if (rule.willFire) one.appendChild(this._line('queue-rule-fires', 'firing'));
      else one.appendChild(this._line('queue-rule-why', rule.whyNot || 'not firing'));
      cell.appendChild(one);
    }
    return cell;
  }

  render(payload, opts = {}) {
    const view = outboxQueueView(payload, opts);
    this.root.textContent = '';

    const meta = this.doc.createElement('div');
    meta.className = 'queue-meta';
    if (view.read) {
      meta.appendChild(this._line('queue-at', view.generatedAt));
      if (view.population) meta.appendChild(this._line('queue-population', view.population));
      // 🔴 수와 「다음 쪽」이 «한 마디»다 (판정 조건). 떼어 놓으면 「50」이 «전부»로 읽힌다.
      if (!view.empty) {
        meta.appendChild(this._line('queue-page', [
          `${view.page.count} on this page`,
          ...view.page.shared,
          view.hasMore ? 'more pages' : '',
        ].filter(Boolean).join(' · ')));
      }
    } else if (view.reason) {
      meta.appendChild(this._line('queue-reason', view.reason));
    }
    this.root.appendChild(meta);
    if (!view.read) return view;

    if (view.empty) {
      this.root.appendChild(this._line('queue-empty', 'Nothing to run right now'));
      return view;
    }

    // Head and rows roll sideways together in one box when the panel is narrower than the six columns (lead 10-09).
    const scroll = this.doc.createElement('div');
    scroll.className = 'queue-scroll';
    this.root.appendChild(scroll);
    const head = this.doc.createElement('div');
    head.className = 'audit-head queue-head';
    // 🔴 머리 칸은 «행 칸의 이름»을 안 쓴다 — `.queue-rules` 가 머리줄 글꼴까지 덮는다.
    for (const col of COLUMNS) head.appendChild(this._cell(`queue-h-${col.key}`, col.label));
    scroll.appendChild(head);

    const body = this.doc.createElement('div');
    body.className = 'queue-rows';
    for (const row of view.rows) {
      const line = this.doc.createElement('div');
      line.className = 'queue-row';
      line.setAttribute('data-state', row.state || 'unknown');
      line.appendChild(this._cell('queue-owner', row.owner));
      line.appendChild(this._clipCell('queue-table', row.table));
      line.appendChild(this._cell('queue-event', row.eventType));
      line.appendChild(this._cell('queue-age', row.age, row.at));

      const state = this._cell('queue-state', '');
      state.appendChild(chainStateCell(this.doc, row.chainState, row.slotPid));
      line.appendChild(state);

      line.appendChild(this._rulesCell(row.rules));
      body.appendChild(line);
    }
    scroll.appendChild(body);
    this._fitState();
    return view;
  }
}
