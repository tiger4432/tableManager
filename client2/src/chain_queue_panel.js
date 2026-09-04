// CHAIN QUEUE INSTRUMENT — turns 「체인 요청이 몇 개 씹히는 것 같다」 into numbers.
//
// Reads `GET /admin/chain/queue` and draws it. READ ONLY: there is no cancel, no retry, no
// reordering here, and there must not be. The queue's own worker owns the queue; a screen that
// could reorder it would be a second writer.
//
// ═══ THE THREE RULES THIS FILE EXISTS TO KEEP ═══════════════════════════════════════════
//
// ① `null` IS NOT `0`. An empty queue answers `oldest_waiting_seconds: null`; a queue that
//    just received something answers `0`. They are different facts and they get different
//    pixels. If they rendered the same, this instrument would reproduce the exact ambiguity
//    it was built to remove.
//
// ② A NUMBER THAT WAS NOT MEASURED IS NAMED, NOT OMITTED. The route deliberately does not
//    compute `retried_total` or `processed_recently` (no index; sequential scan) and says so
//    in `not_measured`. An absent number reads as zero, so those two are drawn WITH THEIR
//    REASON rather than left out.
//
// ③ NO INVENTED THRESHOLD. There is no operational basis in this repository for "60 seconds
//    is late", and a colour applied on a made-up number is a domain claim this file is not
//    entitled to make. The route's own docstring says what decides it: 「계속 자라면 실제로
//    안 나가는 것이고, 0 근처를 오가면 큐는 흐르고 있다」 — that is a comparison ACROSS
//    refreshes, not a property of one sample. So the age is stated, the way to read it is
//    stated, and no colour pretends to have judged it.
//
// ④ THE LIST IS CUT, AND THE CUT IS SAID. The route reads at most `listed.cap` rows, so
//    a short list can mean 「this is all of it」 or 「this is as far as I looked」. Those are
//    different facts, and a silently truncated list reads as the whole queue — the same
//    class of misreading as ② one layer out. When `listed.capped`, the screen says so.
//
// ═══ SHAPE ═════════════════════════════════════════════════════════════════════════════
// 🔴 A LIST, NOT A CARD STRIP (owner, 2026-09-04: 「chain 대기열 너무 가로로 길게
//    배치되어있음. 그냥 대기중인 트랜잭션 리스트로 보여줘 kpi 카드 형태 말고」).
//    Depth and retry count were cards; they are now COLUMNS of the thing they were
//    counting, which is what a person came here to see — WHICH transactions are waiting,
//    oldest first. The one number that cannot become a column stays as a single headline
//    line: the age of the oldest wait is a property of the QUEUE, not of any one row,
//    and rule ① lives in it.
//
// The view model is pure and total (`queueView`), so a harness scores it by importing it.
// The class owns exactly one div, takes its mount in the constructor, and holds no
// module-level state — two of these can sit on one page without touching each other.
// The table reuses `admin.html`'s existing `.table-container` / `.table-header` /
//    `.table-row` styles — a diagnostic panel is not a reason to grow a second table style.

/** The status tokens `admin.html`'s `.health-dot` already understands. */
import { countText } from './absent.js';

export const STATUS = Object.freeze({ OK: 'ok', NEUTRAL: 'loading', UNAVAILABLE: 'warn' });

/**
 * Seconds -> a duration a person reads at a glance. Total: a non-finite input is `null`,
 * never `NaN초`.
 *
 * The unit pair stops at two on purpose ("1시간 5분", not "1시간 5분 3초"): the third unit is
 * never the reason anyone looks at this panel, and it makes the number wider than the label.
 */
export function formatAge(seconds) {
  // 🔴 `Number(null) === 0`, and so is `Number('')`. Without this line an ABSENCE formats
  //    as 「0초」 — the same collapse rule ① exists to prevent, one layer down. `queueView`
  //    happens to check for null before calling here, but this function is exported and the
  //    next caller will not know to.
  if (seconds === null || seconds === undefined || seconds === '') return null;
  const n = Number(seconds);
  if (!Number.isFinite(n) || n < 0) return null;
  const s = Math.floor(n);
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60);
  if (m < 60) return s % 60 ? `${m}분 ${s % 60}초` : `${m}분`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h}시간 ${m % 60}분` : `${h}시간`;
  const d = Math.floor(h / 24);
  return h % 24 ? `${d}일 ${h % 24}시간` : `${d}일`;
}

// 🔴 `countOf` LIVED HERE UNTIL 2026-09-04 and it had this bug: `Number('') === 0` and
//    `''` is neither null nor undefined, so an empty string rendered as 「0」. The same
//    collapse `formatAge` guards against, in the function beside it. It moved to `absent.js`
//    with that hole closed, because this round needed the SAME spelling in five more files
//    and six private copies drift silently.
const countOf = countText;

/**
 * `blocked_by` → what to draw, or null. EVERY FIELD IS THE SERVER'S OWN VALUE.
 *
 * 🔴 NOTHING IS TRANSLATED HERE. `moving` is `progressing`/`stalled`/`unreported` and
 *    `cancel_reaches` is `at_next_batch`/`unknown`/`never`; those are the server's words for
 *    states it distinguishes deliberately (`unreported` is NOT `stalled` — four of six
 *    operations report progress and two never do, so "no progress since the start" is all
 *    that is known). Rewriting them into 「멈춤」/「안 닿음」 would fold that apart-ness
 *    back together and would be this screen asserting something the server did not say.
 *    The recovery sentence is the server's too, and is carried verbatim.
 */
/** 「<요청자> 가 <큐 시각> 에 <연산> 을 <인자> 에 걸었습니다」 — 한 줄, 값만. */
function whyLine(b) {
  const who = b.requested_by ? String(b.requested_by) : '모름';
  const when = b.queued_at ? String(b.queued_at) : '모름';
  const op = b.op == null ? '' : String(b.op);
  const params = (b.params && typeof b.params === 'object' && !Array.isArray(b.params))
    ? b.params : null;
  // ⛔ 값은 «안 나갑니다». 키는 «선언 순서» 그대로이고, 배열이면 개수를 셉니다.
  const args = params
    ? (Object.keys(params).length
      ? Object.keys(params).map(k => {
        const v = params[k];
        return Array.isArray(v) ? `${k}: ${v.length}개` : k;
      }).join(' · ')
      : '없음')
    : '없음';
  return `${who} 가 ${when} 에 ${op} 을 ${args} 에 걸었습니다`;
}

function blockedView(b) {
  if (!b || typeof b !== 'object') return null;
  return Object.freeze({
    runId: String(b.run_id == null ? '' : b.run_id),
    op: String(b.op == null ? '' : b.op),
    state: String(b.state == null ? '' : b.state),
    moving: String(b.moving == null ? '' : b.moving),
    cancelReaches: String(b.cancel_reaches == null ? '' : b.cancel_reaches),
    // rule ① again: `null` here means the run never reported, which is not 「0초」.
    noProgress: formatAge(b.no_progress_seconds) ?? '—',
    stallAfter: formatAge(b.stall_after_seconds) ?? '—',
    processed: countOf(b.processed_rows),
    total: countOf(b.total_rows),
    recovery: b.recovery ? String(b.recovery) : '',
    // 🔴 「왜 도는지」. 서버가 셋을 «날것»으로 냅니다 — 요청자 · 큐 시각 · 인자.
    //    문장은 화면 몫이고(서버가 안 짓습니다), 「한 줄」입니다.
    //    ⚠️ 요청자가 없으면 «모름»입니다. 서버가 `null` 을 보내고, 이름을 지어내지
    //       않는 것이 이 도구의 규율입니다 — 「없음」도 답입니다.
    //    🔴 인자는 «키와 개수»만입니다. 값이 운영 데이터를 담을 수 있어서,
    //       무엇이 걸렸는지는 알 수 있고 «내용은 안 나갑니다». 보안 조건입니다.
    why: whyLine(b),
  });
}

/** head8… — the same abbreviation the failed-transaction table beside this one uses. */
function shortTx(id) {
  const t = String(id ?? '');
  return t.length > 9 ? `${t.slice(0, 8)}…` : t;
}

/**
 * `payload` -> what to draw. Pure and total.
 *
 * @param {object|null} payload  the route's body, or null
 * @param {{unavailable?: string}} [opts]  a reason the body could not be had (HTTP status,
 *        an older server process without this route, a network failure). When present, NO
 *        numbers are drawn: a stale or invented zero here is worse than an empty panel.
 */
export function queueView(payload, opts = {}) {
  if (opts.unavailable || !payload || typeof payload !== 'object') {
    return Object.freeze({
      available: false,
      reason: opts.unavailable
        || '응답을 읽지 못했습니다 — 수를 그리지 않습니다 (빈 값이 0으로 읽히는 것을 막습니다).',
      headline: null,
      failed: null,
      depth: '—',
      byOwner: Object.freeze([]),
      splitByOwner: false,
      rows: Object.freeze([]),
      truncated: '',
      notMeasured: Object.freeze([]),
    });
  }

  const secs = payload.oldest_waiting_seconds;
  // ── rule ①: three distinct states, three distinct readings ──
  //   null    nothing is waiting
  //   0       something is waiting and it arrived within this second
  //   n > 0   something has been waiting n
  // 🔴 「대기 0」은 「밀린 것 없음」이 «아닐 수» 있습니다 — 실패한 행은
  //    `processed_chain=true` 라 «큐에서 빠집니다». 그래서 그 수가 «옆에» 서야 합니다.
  //    ⛔ 문장을 늘리지 않습니다. 값 하나이고, 없으면 «안 그립니다» (0 으로도 안 그립니다).
  const failed = Number.isFinite(Number(opts.failedTotal)) && opts.failedTotal !== null
    && opts.failedTotal !== '' ? `실패 ${Number(opts.failedTotal)}` : null;
  let headline;
  if (secs === null || secs === undefined) {
    headline = { main: '대기 없음', sub: '기다리는 행이 «없습니다». 「0초」와 다릅니다 — 0초는 '
                                      + '방금 들어온 것이 있다는 뜻입니다.', status: STATUS.OK };
  } else {
    const text = formatAge(secs);
    headline = text === null
      ? { main: '—', sub: `나이를 읽지 못했습니다 (받은 값: ${JSON.stringify(secs)}).`,
          status: STATUS.UNAVAILABLE }
      : { main: `제일 오래된 대기 ${text}`,
          // rule ③: say how to read it instead of colouring it.
          sub: payload.oldest_waiting_at
            ? `${payload.oldest_waiting_at} 부터 대기 · 한 번의 값으로는 판정되지 않습니다 — `
              + '새로 고칠 때마다 «자라는지» 보십시오'
            : '한 번의 값으로는 판정되지 않습니다 — 새로 고칠 때마다 «자라는지» 보십시오',
          status: STATUS.NEUTRAL };
  }

  // ── the list. Server order is `id` ascending = longest waiting first; that order IS the
  //    answer, so it is not re-sorted here. ──
  // ── 「누가 이 행을 비우나」 (2026-09-04) ────────────────────────────────
  // 🔴 `unknown` IS NOT `chain`. The server keeps the two apart on purpose, and folding
  //    them here would rebuild the exact misreading that sent someone to inspect a healthy
  //    worker: one undifferentiated number called 「체인 대기열」 while a scheduler run sat
  //    still. The buckets are carried through 1:1, in the server's order, with no arithmetic.
  const buckets = Array.isArray(payload.waiting_by_owner) ? payload.waiting_by_owner : [];
  const byOwner = buckets.map(b => Object.freeze({
    owner: String((b && b.owner) == null ? '' : b.owner),
    waiting: countOf(b && b.waiting),
    age: formatAge(b && b.oldest_waiting_seconds) ?? '—',
    eventTypes: Object.freeze(Array.isArray(b && b.event_types) ? b.event_types.map(String) : []),
    blocked: blockedView(b && b.blocked_by),
  }));
  // 🔴 ONE OWNER IS NOT A SPLIT. Drawing a per-owner breakdown of a single owner adds a
  //    row that says the same thing as the headline, and the reader has to compare two numbers
  //    to learn they are the same number.
  const splitByOwner = byOwner.length > 1;

  const src = Array.isArray(payload.waiting_transactions) ? payload.waiting_transactions : [];
  const rows = src.map(t => Object.freeze({
    txId: String(t.transaction_id ?? ''),
    txShort: shortTx(t.transaction_id),
    rows: countOf(t.rows),
    tables: Array.isArray(t.tables) && t.tables.length ? t.tables.join(', ') : '—',
    eventTypes: Object.freeze(Array.isArray(t.event_types) ? t.event_types.map(String) : []),
    // rule ①, per row: an unreadable age is a dash, never 「0초」.
    age: formatAge(t.waiting_seconds) ?? '—',
    // 🔴 WHO EMPTIES THIS ROW. The server decides it once, from `event_type`; if the screen
    //    re-decided it from the same field there would be TWO copies of that judgement and they
    //    would drift. A row whose owners the server did not name draws a dash, not 「chain」.
    owners: Array.isArray(t.owners) && t.owners.length ? t.owners.join(', ') : '—',
    at: t.waiting_at || '',
    // An empty string means zero retries. The column exists to surface the NON-zero ones,
    // and a column of 「0」 down every row is noise that hides the one row that is not 0.
    maxRetry: Number(t.max_retry) > 0 ? countOf(t.max_retry) : '',
  }));

  // ── rule ④: a cut list says it was cut ──
  const listed = payload.listed && typeof payload.listed === 'object' ? payload.listed : null;
  const truncated = listed && listed.capped
    ? `앞에서 ${countOf(listed.rows_scanned)}행까지만 읽었습니다 (상한 ${countOf(listed.cap)}). `
      + '아래 목록은 대기열의 «전부가 아닙니다».'
    : '';

  // ── rule ②: the two the route refuses to compute, by name and with its reason ──
  const nm = payload.not_measured;
  const notMeasured = nm && typeof nm === 'object'
    ? Object.keys(nm).map(name => ({ name, why: String(nm[name]) }))
    : [];

  // 🔴 The card strip carried `waiting` and `retried_among_waiting`. Dropping the strip must
  //    not drop the numbers — a measured number that stops being drawn is rule ② with the
  //    sign flipped. They become ONE line beside the age, not two cards.
  headline.aggregate = `대기 ${countOf(payload.waiting)}개 · 그중 재시도 `
                     + `${countOf(payload.retried_among_waiting)}개`;

  return Object.freeze({
    available: true,
    reason: '',
    headline: Object.freeze(headline),
    failed,
    depth: countOf(payload.waiting),
    byOwner: Object.freeze(byOwner),
    splitByOwner,
    rows: Object.freeze(rows),
    truncated,
    notMeasured: Object.freeze(notMeasured.map(x => Object.freeze(x))),
  });
}

/**
 * The panel. One mount, one div, no module state — two of these can sit on one page.
 *
 * Same constructor shape as `GridSourceLabel(host, deps)`: the mount is positional and the
 * document is INJECTED, so a harness drives it with a plain object instead of a browser.
 *
 * @param {HTMLElement} mount
 * @param {{doc?: Document}} [deps]
 */
export class ChainQueuePanel {
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('ChainQueuePanel needs a mount element');
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    if (!this.doc) throw new Error('ChainQueuePanel needs a document (deps.doc or mount.ownerDocument)');
    this.root = this.doc.createElement('div');
    this.root.className = 'chain-queue-panel';
    this.mount.appendChild(this.root);
  }

  /** @param {string} cls @param {string} text */
  _line(cls, text) {
    const el = this.doc.createElement('div');
    el.className = cls;
    el.textContent = text;
    return el;
  }

  /** @param {string} text @param {string} [align] */
  _td(text, align) {
    const td = this.doc.createElement('td');
    td.textContent = text;
    if (align) td.style.textAlign = align;
    return td;
  }

  /** @param {string} icon @param {string} text */
  _empty(icon, text) {
    const box = this.doc.createElement('div');
    box.className = 'empty-state';
    const ic = this.doc.createElement('div');
    ic.className = 'empty-icon';
    ic.textContent = icon;
    box.appendChild(ic);
    box.appendChild(this._line('empty-text', text));
    return box;
  }

  /** @param {object|null} payload  @param {{unavailable?: string}} [opts] */
  render(payload, opts = {}) {
    const view = queueView(payload, opts);
    const doc = this.doc;
    this.root.textContent = '';

    if (!view.available) {
      this.root.appendChild(this._empty('⚪', view.reason));
      return view;
    }

    // ── headline: ONE line, not a card. Rule ① lives here. ──
    const head = doc.createElement('div');
    head.className = 'chain-queue-headline';
    head.setAttribute('data-status', view.headline.status);
    const dot = doc.createElement('span');
    dot.className = 'health-dot';
    head.appendChild(dot);
    head.appendChild(this._line('chain-queue-headline-main', view.headline.main));
    // 🔴 실패 수는 «대기 옆»에 섭니다. 탭을 옮기지 않고 둘이 같이 읽혀야, 「대기 0」이
    //    「잘 돌고 있다」로 «안» 읽힙니다. 값을 모르면 아무것도 안 그립니다.
    if (view.failed) head.appendChild(this._line('chain-queue-headline-fail', view.failed));
    head.appendChild(this._line('chain-queue-headline-agg', view.headline.aggregate));
    head.appendChild(this._line('chain-queue-headline-sub', view.headline.sub));
    this.root.appendChild(head);

    // ── 누가 비우나 ── 소유자가 «하나»면 그리지 않는다 (위 `splitByOwner` 참조).
    if (view.splitByOwner) {
      const strip = doc.createElement('div');
      strip.className = 'chain-queue-owner-strip';
      for (const b of view.byOwner) {
        const line = this._line('chain-queue-owner',
          `${b.owner} · 대기 ${b.waiting}개 · 제일 오래 ${b.age}`);
        line.setAttribute('data-owner', b.owner);
        strip.appendChild(line);
      }
      this.root.appendChild(strip);
    }

    // ── 그 소유자가 «왜» 기다리는가 ──
    // 🔴 `blocked_by` 가 null 이면 «아무것도» 그리지 않는다. 서버가 적어 둔 대로
    //    null 은 「막힌 것이 없다」가 아니라 「이유를 모른다」이고, 「없음」으로 그리면
    //    이 파일이 없애려는 바로 그 0 이 하나 더 생긴다.
    // 🔴 값은 «서버의 낟말로» 적는다. `moving` 과 `cancel_reaches` 를 번역하면
    //    서버가 일부러 갈라 둔 `stalled` 와 `unreported` 가 한 말로 접힌다.
    for (const b of view.byOwner) {
      if (!b.blocked) continue;
      const box = doc.createElement('div');
      box.className = 'chain-queue-blocked';
      box.setAttribute('data-owner', b.owner);
      box.appendChild(this._line('chain-queue-blocked-head',
        `${b.owner} · blocked_by — ${b.blocked.op} ${b.blocked.runId}`));
      box.appendChild(this._line('chain-queue-blocked-fact',
        `state ${b.blocked.state} · moving ${b.blocked.moving} · cancel_reaches ${b.blocked.cancelReaches}`));
      box.appendChild(this._line('chain-queue-blocked-fact',
        `processed_rows ${b.blocked.processed} / total_rows ${b.blocked.total}`
        + ` · no_progress ${b.blocked.noProgress} · stall_after ${b.blocked.stallAfter}`));
      // 🔴 「왜 도는지」가 «사실» 줄들 다음, 복구 문장 앞에 섭니다.
      if (b.blocked.why) box.appendChild(this._line('chain-queue-blocked-why', b.blocked.why));
      if (b.blocked.recovery) {
        box.appendChild(this._line('chain-queue-blocked-recovery', b.blocked.recovery));
      }
      this.root.appendChild(box);
    }

    if (view.truncated) this.root.appendChild(this._line('chain-queue-truncated', view.truncated));

    if (view.rows.length === 0) {
      this.root.appendChild(this._empty('🎉', '대기 중인 트랜잭션이 없습니다.'));
      return view;
    }

    const table = doc.createElement('table');
    table.className = 'table-container';
    const thead = doc.createElement('thead');
    thead.className = 'table-header';
    const hr = doc.createElement('tr');
    // Width is set on the header cells so the body columns follow — the same shape the
    // failed-transaction table beside this one uses.
    for (const [label, width, align] of [
      ['Transaction ID', '130px', ''], ['대기', '100px', ''], ['Tables', '', ''],
      ['Event', '110px', ''], ['행', '60px', 'center'], ['재시도', '70px', 'center'],
    ]) {
      const th = doc.createElement('th');
      th.textContent = label;
      if (width) th.style.width = width;
      if (align) th.style.textAlign = align;
      hr.appendChild(th);
    }
    thead.appendChild(hr);
    table.appendChild(thead);

    const tbody = doc.createElement('tbody');
    for (const r of view.rows) {
      const tr = doc.createElement('tr');
      tr.className = 'table-row';
      tr.setAttribute('data-txid', r.txId);

      const tdId = doc.createElement('td');
      const chip = doc.createElement('span');
      chip.className = 'tx-id-chip';
      chip.title = r.txId;
      chip.textContent = r.txShort;
      tdId.appendChild(chip);
      tr.appendChild(tdId);

      const tdAge = this._td(r.age);
      tdAge.className = 'chain-queue-age';
      if (r.at) tdAge.title = `${r.at} 부터 대기`;
      tr.appendChild(tdAge);

      tr.appendChild(this._td(r.tables));

      const tdEv = doc.createElement('td');
      if (r.eventTypes.length) {
        for (const t of r.eventTypes) {
          const b = doc.createElement('span');
          b.className = `badge ${t === 'CREATE' ? 'badge-warning' : 'badge-danger'}`;
          b.style.marginRight = '4px';
          b.textContent = t;
          tdEv.appendChild(b);
        }
      } else {
        tdEv.textContent = '—';
      }
      // 🔴 소유자를 «칸을 늘리지 않고» 보입니다. 일곱째 컬럼을 더하면 좀은 패널에서
      //    표가 다시 넘칩니다 — 바로 앞 라운드에서 0 으로 만든 수입니다.
      //    event_type 이 그 판정의 재료이므로 같은 칸이 자연스러운 자리입니다.
      const ow = this._line('chain-queue-row-owners', r.owners);
      ow.setAttribute('data-owners', r.owners);
      tdEv.appendChild(ow);
      tr.appendChild(tdEv);

      tr.appendChild(this._td(r.rows, 'center'));
      // rule ③ applies here too: the retry count is stated, never coloured into a verdict.
      tr.appendChild(this._td(r.maxRetry, 'center'));

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    this.root.appendChild(table);

    if (view.notMeasured.length > 0) {
      const box = doc.createElement('div');
      box.className = 'chain-queue-notmeasured';
      box.appendChild(this._line('health-card-title',
        `여기서 «재지 않는» 수 ${view.notMeasured.length}개 — 없는 것이 아니라 안 잰 것입니다`));
      for (const x of view.notMeasured) {
        const line = this._line('health-card-sub', `${x.name} — ${x.why}`);
        line.setAttribute('data-name', x.name);
        box.appendChild(line);
      }
      this.root.appendChild(box);
    }
    return view;
  }
}
