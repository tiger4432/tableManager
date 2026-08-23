// ═══════════════════════════════════════════════════════════════════════════════
// 부품 3 — 메인 트렌드. 목업 2a ④.
//
// 🔴 THIS IS WHERE 「점을 찍으면 그것이 씨앗이다」 BECOMES TRUE. Every point carries the ledger's
//    own `identity.mark_key`, so clicking one writes THAT id into the marking this instance was
//    declared to write. The part invents no subject and no id.
//
// 🔴 THE LEGEND STATES THE DENOMINATOR. `provenance` says the numerator is `observed` and the
//    denominator is `inspection_run` with `absence_is_zero: false`, and the mockup prints
//    exactly that. A rate whose denominator is unstated is a number nobody can check, and this
//    screen's whole argument is that a number you cannot check is not evidence.
//
// 🔴 A POINT WITH NO RATE IS NOT A POINT AT ZERO. `absence_is_zero` is false upstream; drawing
//    an unmeasured wafer on the floor of the chart would make it true on screen.
//
// 🔴 PLAIN DOM, NO CANVAS AND NO NEW RENDERER. This is tens of points, not thousands of dies:
//    each point is its own element so it is its own click target, and the part stays scorable
//    under the bare-node document stub the harnesses drive.
//
// 🔴 NO SIZE CONSTANT. Positions are percentages of the box the shell handed over.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel, markingIntent } from './panel.js';
import { SIGN } from './marking_store.js';
import { fetchTrends, trendsModel } from './api.js';

export class MainTrendPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    this.apiBase = options.apiBase || '';
    this.kinds = options.kinds || null;
    this.window = options.window || '180d';
    // Declared by the screen, never assembled here: this part does not know what a grain means.
    this.grain = options.grain || null;
    // 🔴 THE AXIS THE CONTROL BAR CHOSE. A panel READS one marking through the base class, and
    //    this part needs two: the seed it writes, and the axis somebody else picked. The second
    //    name is declared here and subscribed by hand.
    //    CONTRACT WITH `control_bar_panel.js`: the id is `axis:<kind>:<id>` -- `ratio` for a
    //    finding kind this route can plot, `quantity` for a walk candidate it cannot.
    this.axisReads = options.axisReads || null;
    // 🔴 THE SUBJECT, BY NAME, SO OTHER PARTS CAN FOLLOW IT. The mark id is the ledger's
    //    `identity.mark_key`, which no other part can decode into a wafer without parsing a
    //    server id. The wafer NAME is in the same point, so it is written under its own
    //    declared name and a map can page to it by declaring that it follows.
    this.writesSubject = options.writesSubject || null;
    // 🔴 「내가 보고 있는 점」 -- the wafer the rest of the screen is on. Declared, subscribed by
    //    hand like the axis, and drawn as a ring so it is visible without being marked.
    this.subjectReads = options.subjectReads || null;
    this._subjectOff = null;
    this.axisChosen = null;
    this._axisOff = null;
    this.fetchImpl = options.fetchImpl || null;
    this.seedWafer = options.seedWafer || null;
    this.model = null;
    this.loadState = 'idle';
  }

  mount() {
    super.mount();
    if (this.subjectReads && this.markings) {
      this._subjectOff = this.markings.subscribe(this.subjectReads, () => this.render());
    }
    if (this.axisReads && this.markings) {
      this._axisOff = this.markings.subscribe(this.axisReads, () => this._onAxisChanged());
      this._onAxisChanged();
    }
    this.load();
  }

  destroy() {
    if (this._axisOff) this._axisOff();
    this._axisOff = null;
    if (this._subjectOff) this._subjectOff();
    this._subjectOff = null;
    super.destroy();
  }

  /** The chosen axis, read off the marking the control bar writes. */
  _onAxisChanged() {
    const entries = this.markings ? this.markings.entries(this.axisReads) : [];
    const chosen = entries.length ? entries[0][0] : null;
    if (chosen === this.axisChosen) return;
    this.axisChosen = chosen;
    const parts = String(chosen || '').split(':');
    const kind = parts[1] || null;
    const id = parts.slice(2).join(':') || null;
    if (kind === 'ratio' && id && id !== this.kinds) {
      this.kinds = id;
      this.load();
      return;
    }
    // 🔴 A QUANTITY AXIS IS NOT A RATIO. This route serves finding kinds; a walk candidate like
    //    `bond_temp` has no series here. The panel draws nothing and SAYS which axis it is and
    //    why -- an empty chart with no sentence would read as 「그 축은 값이 0」.
    this.render();
  }

  async load() {
    this.loadState = 'loading';
    this.render();
    const result = await fetchTrends({
      apiBase: this.apiBase, kinds: this.kinds, window: this.window,
      grain: this.grain, fetchImpl: this.fetchImpl,
    });
    this.model = trendsModel(result);
    this.loadState = this.model.ok ? 'ready' : 'refused';
    this.render();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    this.host.textContent = '';
    const root = doc.createElement('div');
    // 🔴 MY OWN POINTS, NOT THE NAME'S SIZE -- the same rule the map and the lists follow.
    const mineMarked = ((this.model && this.model.points) || [])
      .some((p) => p.markKey && this.signOf(p.markKey) !== SIGN.ABSENT);
    root.className = mineMarked ? 'rb-trend is-attenuating' : 'rb-trend';

    if (this.title) {
      const cap = doc.createElement('div');
      cap.className = 'rb-part-title';
      cap.textContent = this.title;
      root.appendChild(cap);
    }

    // The subtitle is the instruction, on the panel: this is how a seed is chosen.
    const sub = doc.createElement('div');
    sub.className = 'rb-trend-sub';
    sub.textContent = '점을 찍으면 그것이 씨앗입니다 · 씨앗도 마킹 하나';
    root.appendChild(sub);

    if (this.loadState !== 'ready' || !this.model || !this.model.ok) {
      const note = doc.createElement('div');
      note.className = this.loadState === 'refused'
        ? 'rb-trend-note rb-trend-note--refused' : 'rb-trend-note rb-trend-note--absent';
      note.textContent = this.loadState === 'loading' ? '읽는 중…'
        : (this.model && this.model.message) || '서버가 거절했습니다';
      root.appendChild(note);
      this.host.appendChild(root);
      return;
    }

    const chosenKind = String(this.axisChosen || '').split(':')[1] || null;
    if (chosenKind && chosenKind !== 'ratio') {
      const note = doc.createElement('div');
      note.className = 'rb-trend-note rb-trend-note--absent';
      // The id stays checkable in the title; the sentence says the KIND, because a raw node id
      // in a sentence is a string nobody reads.
      note.setAttribute('title', String(this.axisChosen));
      note.textContent = '고른 축은 «물리량»입니다 — 이 차트는 «비율»만 그립니다'
        + ' (걷기에서 고른 축은 후보·순위가 씁니다)';
      root.appendChild(note);
      this.host.appendChild(root);
      return;
    }

    const m = this.model;
    const drawn = m.points.filter((p) => p.rate !== null && p.at);
    if (!drawn.length) {
      // Two facts, separately: what came back, and what could not be plotted.
      const note = doc.createElement('div');
      note.className = 'rb-trend-note rb-trend-note--absent';
      note.textContent = m.points.length
        ? `점 ${m.points.length}개 · 비율이 붙은 것은 없습니다 — 아직 안 쟀습니다`
        : '이 창에 점이 없습니다';
      root.appendChild(note);
      this.host.appendChild(root);
      return;
    }

    root.appendChild(this._plot(drawn, m));
    root.appendChild(this._legend(drawn, m));
    this.host.appendChild(root);
  }

  _plot(points, m) {
    const doc = this.doc;
    const plot = doc.createElement('div');
    plot.className = 'rb-trend-plot';

    const rates = points.map((p) => p.rate);
    const times = points.map((p) => Date.parse(p.at)).filter((t) => !Number.isNaN(t));
    const maxRate = Math.max(...rates, 0);
    const minRate = Math.min(...rates);
    const minTime = Math.min(...times);
    const maxTime = Math.max(...times);
    const spanTime = maxTime - minTime;
    // 🔴 MEASURED 2026-08-23: this stack answers 12 points that are ALL 0.0% at ONE timestamp.
    //    A chart drawn as if those axes had spread puts twelve wafers on top of each other at
    //    the origin and reads as 「데이터 없음」, which is false -- they were scanned and they
    //    were clean. So a degenerate axis is SAID (see `_flatNote`) and the points are laid out
    //    by index, which is honest about being an order rather than a time.
    this.flatRate = maxRate === minRate;
    this.flatTime = !(spanTime > 0);
    // The top of the axis is the data's own maximum, never a rounded number this file invented.
    const top = maxRate > 0 ? maxRate : 1;

    const seed = this._seedPoint(points);
    if (seed) {
      // 🔴 THE SEED'S OWN VALUE, AS A LINE. Everything above it is worse than the seed, and that
      //    comparison is the reason this chart is on the screen.
      const line = doc.createElement('div');
      line.className = 'rb-trend-seedline';
      line.style.bottom = `${(seed.rate / top) * 100}%`;
      plot.appendChild(line);
    }

    for (const p of points) {
      const dot = doc.createElement('div');
      const marked = p.markKey ? this.signOf(p.markKey) : SIGN.ABSENT;
      const isSubject = Boolean(this.subjectReads && p.wafer && this.markings
        && this.markings.signOf(this.subjectReads, p.wafer) !== SIGN.ABSENT);
      dot.className = 'rb-trend-dot'
        + (marked === SIGN.CASE ? ' is-marked-case' : '')
        + (marked === SIGN.CONTROL ? ' is-marked-control' : '')
        + (isSubject ? ' is-subject' : '')
        + (seed && p === seed ? ' is-seed' : '');
      const t = Date.parse(p.at);
      const i = points.indexOf(p);
      dot.style.left = this.flatTime
        ? `${points.length > 1 ? (i / (points.length - 1)) * 100 : 50}%`
        : `${(((Number.isNaN(t) ? minTime : t) - minTime) / spanTime) * 100}%`;
      // A flat rate axis is drawn as a flat line, at the floor, not spread to fill the box.
      dot.style.bottom = this.flatRate && maxRate === 0 ? '0%' : `${(p.rate / top) * 100}%`;
      dot.setAttribute('data-wafer', p.wafer || '');
      if (p.markKey) dot.setAttribute('data-node-id', p.markKey);
      // The title is the whole point, in the vocabulary the ledger used.
      dot.setAttribute('title',
        `${p.wafer || '(웨이퍼 없음)'} · ${(p.rate * 100).toFixed(2)}%`
        + (p.denominator === null ? '' : ` · 분모 ${p.denominator}`)
        + (p.state ? ` · ${p.state}` : ''));
      if (p.markKey) {
        dot.addEventListener('click', (event) => {
          const intent = markingIntent(event);
          this.mark(p.markKey, intent.sign, intent.mode);
          if (this.writesSubject && this.markings && p.wafer) {
            // Replace, always: the subject of the screen is one thing at a time.
            this.markings.clear(this.writesSubject);
            this.markings.set(this.writesSubject, p.wafer, SIGN.CASE);
          }
        });
      }
      plot.appendChild(dot);
    }

    // Axis ends only: the maximum and the floor, both from the data.
    const yTop = doc.createElement('div');
    yTop.className = maxRate > 0 ? 'rb-trend-ymax' : 'rb-trend-ymax is-absent';
    // 🔴 AN AXIS TOP NOBODY MEASURED IS NOT A NUMBER. With every rate at zero there is no upper
    //    bound in the data, and printing 「100.0%」 would be this panel inventing the scale it
    //    is drawing on.
    yTop.textContent = maxRate > 0 ? `${(top * 100).toFixed(1)}%` : '—';
    const yBottom = doc.createElement('div');
    yBottom.className = 'rb-trend-ymin';
    yBottom.textContent = '0.0%';
    // 🔴 THE X AXIS NAMES ITS TIME. It was saying 「차례」 and nothing else, so the reader could
    //    not see WHEN any of this happened. Measured: every point in this window shares one
    //    timestamp, so the axis says that timestamp -- an order with no clock on it is not an
    //    answer to 「언제」.
    const stamp = (v) => String(v || '').replace('T', ' ').slice(0, 16);
    const xLeft = doc.createElement('div');
    xLeft.className = 'rb-trend-xlabel is-left';
    xLeft.textContent = this.flatTime
      ? `${stamp(points[0].at)} · 한 시각`
      : stamp(points[0].at);
    plot.appendChild(xLeft);
    if (!this.flatTime) {
      const xRight = doc.createElement('div');
      xRight.className = 'rb-trend-xlabel is-right';
      xRight.textContent = stamp(points[points.length - 1].at);
      plot.appendChild(xRight);
    }
    plot.append(yTop, yBottom);
    return plot;
  }

  /** The marked point, if one is marked; otherwise none. The seed is a MARKING, not a field. */
  _seedPoint(points) {
    for (const p of points) {
      if (p.markKey && this.signOf(p.markKey) === SIGN.CASE) return p;
    }
    return null;
  }

  _legend(points, m) {
    const doc = this.doc;
    const el = doc.createElement('div');
    el.className = 'rb-trend-legend';
    const one = doc.createElement('span');
    one.textContent = `점 하나 = 웨이퍼 하나 · ${points.length}개`;
    el.appendChild(one);
    if (m.provenance) {
      const prov = doc.createElement('span');
      prov.className = 'rb-trend-prov';
      // 🔴 THE DENOMINATOR, ON SCREEN. Printed from `provenance`, never from a memory of it.
      prov.textContent = `y = 비율 (분자 ${m.provenance.numerator || '?'}`
        + ` · 분모 ${m.provenance.denominator || '?'}`
        + ` · absence_is_zero ${m.provenance.absenceIsZero ? 'true' : 'false'})`;
      el.appendChild(prov);
    }
    // 🔴 SAID, NOT DRAWN AROUND. 「퍼질 축이 없다」 is a fact about today's data and it is a
    //    different sentence from 「점이 없다」 -- the wafers were scanned and they were clean.
    if (this.flatRate || this.flatTime) {
      const flat = doc.createElement('span');
      flat.className = 'rb-trend-absent';
      const parts = [];
      if (this.flatRate) parts.push('값이 전부 같습니다');
      if (this.flatTime) parts.push('시각이 전부 같습니다 — 가로는 시간이 아니라 «차례»입니다');
      flat.textContent = parts.join(' · ');
      el.appendChild(flat);
    }
    const unplotted = m.points.length - points.length;
    if (unplotted > 0) {
      const gap = doc.createElement('span');
      gap.className = 'rb-trend-absent';
      // Not dropped silently: a point without a rate is a wafer nobody measured.
      gap.textContent = `비율 없음 ${unplotted} — 안 쟀습니다`;
      el.appendChild(gap);
    }
    return el;
  }
}
