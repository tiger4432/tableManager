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
// ═══ SHAPE ═════════════════════════════════════════════════════════════════════════════
// The view model is pure and total (`queueView`), so a harness scores it by importing it.
// The class owns exactly one div, takes its mount in the constructor, and holds no
// module-level state — two of these can sit on one page without touching each other.

/** The status tokens `admin.html`'s `.health-dot` already understands. */
export const STATUS = Object.freeze({ OK: 'ok', NEUTRAL: 'loading', UNAVAILABLE: 'warn' });

/**
 * Seconds -> a duration a person reads at a glance. Total: a non-finite input is `null`,
 * never `NaN초`.
 *
 * The unit pair stops at two on purpose ("1시간 5분", not "1시간 5분 3초"): the third unit is
 * never the reason anyone looks at this card, and it makes the number wider than the label.
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

/**
 * `payload` -> what to draw. Pure and total.
 *
 * @param {object|null} payload  the route's body, or null
 * @param {{unavailable?: string}} [opts]  a reason the body could not be had (HTTP status,
 *        an older server process without this route, a network failure). When present, NO
 *        numbers are drawn: a stale or invented zero here is worse than an empty card.
 */
export function queueView(payload, opts = {}) {
  if (opts.unavailable || !payload || typeof payload !== 'object') {
    return Object.freeze({
      available: false,
      reason: opts.unavailable
        || '응답을 읽지 못했습니다 — 수를 그리지 않습니다 (빈 값이 0으로 읽히는 것을 막습니다).',
      cards: Object.freeze([]),
      notMeasured: Object.freeze([]),
    });
  }

  const secs = payload.oldest_waiting_seconds;
  // ── rule ①: three distinct states, three distinct readings ──
  //   null    nothing is waiting
  //   0       something is waiting and it arrived within this second
  //   n > 0   something has been waiting n
  let age;
  if (secs === null || secs === undefined) {
    age = { main: '대기 없음', sub: '기다리는 행이 «없습니다». 「0초」와 다릅니다 — 0초는 방금 '
                                + '들어온 것이 있다는 뜻입니다.', status: STATUS.OK };
  } else {
    const text = formatAge(secs);
    age = text === null
      ? { main: '—', sub: `나이를 읽지 못했습니다 (받은 값: ${JSON.stringify(secs)}).`,
          status: STATUS.UNAVAILABLE }
      : { main: text,
          // rule ③: say how to read it instead of colouring it.
          sub: payload.oldest_waiting_at
            ? `${payload.oldest_waiting_at} 부터 대기 · 한 번의 값으로는 판정되지 않습니다 — `
              + '새로 고칠 때마다 «자라는지» 보십시오'
            : '한 번의 값으로는 판정되지 않습니다 — 새로 고칠 때마다 «자라는지» 보십시오',
          status: STATUS.NEUTRAL };
  }

  const cards = [
    // The answer first. Depth is context, and the route's docstring is explicit that depth
    // alone cannot separate 「많다」 from 「밀린다」.
    { key: 'oldest', title: '제일 오래된 대기의 나이', ...age },
    { key: 'waiting', title: '대기 깊이', main: countOf(payload.waiting),
      sub: '바쁠 때 커졌다 줄어드는 것이 «정상»입니다. 이 수만으로는 「많다」와 「밀린다」를 '
         + '구별하지 못합니다.', status: STATUS.NEUTRAL },
    { key: 'retried', title: '대기 중 재시도', main: countOf(payload.retried_among_waiting),
      sub: '아직 «기다리는» 행 중 재시도된 수입니다. 이미 지나간 재시도는 세지 않습니다.',
      status: STATUS.NEUTRAL },
  ];

  // ── rule ②: the two the route refuses to compute, by name and with its reason ──
  const nm = payload.not_measured;
  const notMeasured = nm && typeof nm === 'object'
    ? Object.keys(nm).map(name => ({ name, why: String(nm[name]) }))
    : [];

  return Object.freeze({
    available: true,
    reason: '',
    cards: Object.freeze(cards.map(c => Object.freeze(c))),
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

  /** @param {object|null} payload  @param {{unavailable?: string}} [opts] */
  render(payload, opts = {}) {
    const view = queueView(payload, opts);
    const doc = this.doc;
    this.root.textContent = '';

    if (!view.available) {
      const box = doc.createElement('div');
      box.className = 'empty-state';
      const icon = doc.createElement('div');
      icon.className = 'empty-icon';
      icon.textContent = '⚪';
      const text = doc.createElement('div');
      text.className = 'empty-text';
      text.textContent = view.reason;
      box.appendChild(icon);
      box.appendChild(text);
      this.root.appendChild(box);
      return view;
    }

    const strip = doc.createElement('div');
    strip.className = 'health-strip';
    for (const c of view.cards) {
      // A `div`, not the `button` the dashboard cards use: these do not navigate anywhere,
      // and a button that does nothing when clicked is a promise the screen cannot keep.
      const card = doc.createElement('div');
      card.className = 'health-card';
      card.style.cursor = 'default';
      card.setAttribute('data-status', c.status);
      card.setAttribute('data-key', c.key);
      const top = doc.createElement('div');
      top.className = 'health-card-top';
      const dot = doc.createElement('span');
      dot.className = 'health-dot';
      const title = doc.createElement('span');
      title.className = 'health-card-title';
      title.textContent = c.title;
      top.appendChild(dot);
      top.appendChild(title);
      const main = doc.createElement('div');
      main.className = 'health-card-main';
      main.textContent = c.main;
      const sub = doc.createElement('div');
      sub.className = 'health-card-sub';
      sub.textContent = c.sub;
      card.appendChild(top);
      card.appendChild(main);
      card.appendChild(sub);
      strip.appendChild(card);
    }
    this.root.appendChild(strip);

    if (view.notMeasured.length > 0) {
      const box = doc.createElement('div');
      box.className = 'chain-queue-notmeasured';
      const head = doc.createElement('div');
      head.className = 'health-card-title';
      head.textContent = `여기서 «재지 않는» 수 ${view.notMeasured.length}개 — 없는 것이 아니라 안 잰 것입니다`;
      box.appendChild(head);
      for (const x of view.notMeasured) {
        const line = doc.createElement('div');
        line.className = 'health-card-sub';
        line.setAttribute('data-name', x.name);
        line.textContent = `${x.name} — ${x.why}`;
        box.appendChild(line);
      }
      this.root.appendChild(box);
    }
    return view;
  }
}
