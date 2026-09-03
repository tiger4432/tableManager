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

/** A count that is genuinely absent renders as `—`, never as `0`. See rule ②. */
function countOf(v) {
  return Number.isFinite(Number(v)) && v !== null && v !== undefined ? String(Number(v)) : '—';
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
      depth: '—',
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
  const src = Array.isArray(payload.waiting_transactions) ? payload.waiting_transactions : [];
  const rows = src.map(t => Object.freeze({
    txId: String(t.transaction_id ?? ''),
    txShort: shortTx(t.transaction_id),
    rows: countOf(t.rows),
    tables: Array.isArray(t.tables) && t.tables.length ? t.tables.join(', ') : '—',
    eventTypes: Object.freeze(Array.isArray(t.event_types) ? t.event_types.map(String) : []),
    // rule ①, per row: an unreadable age is a dash, never 「0초」.
    age: formatAge(t.waiting_seconds) ?? '—',
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
    depth: countOf(payload.waiting),
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
    head.appendChild(this._line('chain-queue-headline-agg', view.headline.aggregate));
    head.appendChild(this._line('chain-queue-headline-sub', view.headline.sub));
    this.root.appendChild(head);

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
