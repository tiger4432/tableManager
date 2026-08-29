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
import { createWalk } from './api.js';

/**
 * 🔴 이 점이 «어느 노드»인가 — 찍는 키는 한 곳에서 정합니다 (소유자 판정 2026-08-24:
 *    「키는 노드 아이디와 노드 타입」). 서버가 node_id 를 실으면 그것이고, 아직인 응답에서는
 *    옛 mark_key 입니다 -- 읽는 쪽이 «먼저» 가면 화면이 조용히 빕니다(오늘 아침 그 부류).
 *    여섯 자리가 각자 고르면 한 자리만 옮겨도 어긋나므로 «한 함수»가 답합니다.
 */
function markIdOf(point) {
  return (point && (point.nodeId || point.markKey)) || null;
}

/**
 * 🔴 이 점이 그리는 «값». 비율 축이면 비율이고 집계 축이면 집계값입니다 (라운드 ①-a).
 *    이름을 하나로 모으지 않고 `rate` 에 집계값을 넣으면 필드 이름이 거짓이 됩니다 --
 *    비율이 아닌 수를 「비율」이라 부르는 자리가 이 화면에 하나 더 생깁니다.
 *    아직 `value` 를 안 싣는 모델(`trendsModel`)이 있으므로 «없으면» 비율로 물러섭니다.
 */
function valueOf(point) {
  if (!point) return null;
  return point.value === undefined ? point.rate : point.value;
}

/** 비율은 %, 집계는 «그 수 그대로». 단위를 지어내지 않습니다. */
function formatValue(model, value) {
  if (model && model.valueKind === 'aggregate') {
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  }
  return `${(value * 100).toFixed(2)}%`;
}

export class MainTrendPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    // 🔴 ONE CALL — 소유자가 그린 데이터 흐름(2026-08-24): 부품은 { start, collect } 만 선언하고
    //    라우트·질의·모델을 다시는 부르지 않습니다. 화면이 walk 하나를 «주입»하므로 같은 walk 을
    //    쓰는 두 부품이 요청 하나를 나눠 씁니다. 혼자 서는 부품은 자기 것을 만듭니다.
    this.walk = options.walk || createWalk({ apiBase: options.apiBase, fetchImpl: options.fetchImpl });
    // 시작점과 걷는 종류. 값이고 축이 아닙니다 — 소유자: 「일단 wafer 로 고정」.
    this.start = options.start || null;
    // 🔴 좌석이 라우트 이름을 안 대면 «합성 루트가 묶어 준 걷기»를 씁니다 (round Z-3).
    //    this.collect 의 기본값이 살아나면 좌석이 이름을 뗐는데도 죽은 trends 라우트를
    //    계속 부릅니다 -- 오늘 같은 모양을 세 부품에서 이미 만났습니다.
    this.boundWalk = options.load || null;
    // 🔴 기본값이 «떠났습니다» (총괄 검수 14:3x, 2026-08-29). 세 줄 위의 경고가 맞았고 줄이 남아
    //    있었습니다 -- 좌석이 `collect` 를 뗀 뒤에도 이 `|| 'trend_y'` 가 죽은 라우트를 되살립니다.
    //    🔴 배울 것: «기본값은 아무도 안 쓴 선언»입니다. 선언에서 지워도 부품이 들고 있으면
    //       그대로 돌고, 「좌석 선언에서 사라졌나」로 재는 게이트는 그때 초록입니다.
    //       그래서 이제 «없으면 안 걷고 말합니다» -- 지어내는 것보다 조용한 답이 낫습니다.
    this.collect = options.collect || null;
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
    // 🔴 «집계 × 수식어» 축 (라운드 ①-a). `null` 이면 이 차트는 자기 기본(비율)을 그립니다 --
    //    아무도 안 고른 축을 대신 골라 그리지 않습니다.
    this.axis = null;
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
    this._watchStart();
    this.load();
  }

  destroy() {
    if (this._axisOff) this._axisOff();
    this._axisOff = null;
    if (this._subjectOff) this._subjectOff();
    this._subjectOff = null;
    if (this._offStart) this._offStart();
    this._offStart = null;
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
    // 축을 «떠나는» 것도 한 걸음입니다 -- 안 되돌리면 비율을 골라도 집계가 그려집니다.
    const wasAggregate = Boolean(this.axis);
    this.axis = null;
    // 🔴 `axis:agg:<집계>:<수식어>`. 쌍이 완성됐을 때만 축입니다 (control_bar_panel.js 와 같은 철자).
    if (kind === 'agg' && id) {
      const cut = id.indexOf(':');
      if (cut > 0) {
        this.axis = { aggregation: id.slice(0, cut), qualifier: id.slice(cut + 1) };
        this.load();
        return;
      }
    }
    if (kind === 'ratio' && id && id !== this.kinds) {
      this.kinds = id;
      this.load();
      return;
    }
    if (wasAggregate) { this.load(); return; }
    // 🔴 A QUANTITY AXIS IS NOT A RATIO. This route serves finding kinds; a walk candidate like
    //    `bond_temp` has no series here. The panel draws nothing and SAYS which axis it is and
    //    why -- an empty chart with no sentence would read as 「그 축은 값이 0」.
    this.render();
  }

  /** 🔴 THE SUBJECT MOVED, SO THE QUESTION IS ASKED AGAIN. Declared name, not a hardcoded one. */
  _watchStart() {
    if (!this.start || !this.start.marking || !this.markings) return;
    this._offStart = this.markings.subscribe(this.start.marking, () => this.load());
  }

  async load() {
    // 🔴 A QUESTION WITH NO SUBJECT IS NOT ASKED. When this instance's start names a marking
    //    and nobody has marked anything yet, walking would answer for EVERYBODY and the chart
    //    would look like an answer about the candidate nobody picked. It waits, and says so.
    // 🔴 무엇을 모을지 «아무도 안 말했으면» 묻지 않습니다. 기본값을 지어내면 그 순간 화면이
    //    선언에 없는 질문을 하게 되고, 그 답이 404 여도 화면은 「서버가 거절」이라 말합니다.
    if (!this.boundWalk && !this.collect) {
      this.model = null;
      this.loadState = 'undeclared';
      this.render();
      return;
    }
    const start = this.startFor();
    if (!start && this.start && this.start.marking) {
      this.model = null;
      this.loadState = 'awaiting';
      this.render();
      return;
    }
    this.loadState = 'loading';
    this.render();
    this.model = await (this.boundWalk
      ? this.boundWalk({ start, axis: this.axis })
      : this.walk({
        start, collect: this.collect,
        kinds: this.kinds, window: this.window, grain: this.grain,
      }));
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
      .some((p) => markIdOf(p) && this.signOf(markIdOf(p)) !== SIGN.ABSENT);
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
    sub.textContent = this.start && this.start.marking
      ? `${this.start.marking} 이 이 차트의 주어입니다`
      : '점을 찍으면 그것이 씨앗입니다 · 씨앗도 마킹 하나';
    root.appendChild(sub);

    if (this.loadState !== 'ready' || !this.model || !this.model.ok) {
      const note = doc.createElement('div');
      // 「선언이 없다」는 «거절이 아닙니다» -- 서버는 아무 말도 안 했습니다.
      note.className = this.loadState === 'refused'
        ? 'rb-trend-note rb-trend-note--refused' : 'rb-trend-note rb-trend-note--absent';
      // 🔴 「아직 안 골랐다」 IS ITS OWN SENTENCE. Folding it into 「없다」 or a refusal would
      //    make an untouched screen look broken -- the first of the four absences this board
      //    is built to keep apart.
      note.textContent = this.loadState === 'awaiting'
        ? `${(this.start && this.start.marking) || '마킹'} 이 비었습니다 — 후보를 고르면 그립니다`
        : (this.loadState === 'undeclared'
          ? '이 좌석이 «무엇을 모을지» 선언하지 않았습니다 — 그래서 걷지 않았습니다'
          : (this.loadState === 'loading' ? '읽는 중…'
            : (this.model && this.model.message) || '서버가 거절했습니다'));
      root.appendChild(note);
      this.host.appendChild(root);
      return;
    }

    const chosenKind = String(this.axisChosen || '').split(':')[1] || null;
    if (chosenKind && chosenKind !== 'ratio' && chosenKind !== 'agg') {
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
    const drawn = m.points.filter((p) => valueOf(p) !== null && valueOf(p) !== undefined && p.at);
    if (!drawn.length) {
      // Two facts, separately: what came back, and what could not be plotted.
      const note = doc.createElement('div');
      note.className = 'rb-trend-note rb-trend-note--absent';
      // 🔴 잘린 걷기는 「점이 없다」가 «아닙니다» (round Z-3, 2026-08-28). 실측: 마킹한 다이에서
      //    걸으면 complete:false · truncated ["nodes","claims"] 로 오고, 그때 「이 창에 점이
      //    없습니다」는 «예산에서 못 본 것»을 «없는 것»으로 바꿔 말합니다. 모델이 이미 그 문장을
      //    싣고 있었고 화면이 안 쓰고 있었습니다 -- 오늘 unscanned 에서 세운 규칙 그대로입니다.
      // 🔴 여기에 «두 가지 0» 이 있습니다 (실측 2026-08-29, 라이브에서 제 라운드가 만든 결함).
      //    `unit` 은 걷기가 «4개나 실었는데» max 가 전부 건너뛴 것이고, 그때 화면이
      //    「안 실었습니다」라고 말했습니다 -- 총괄 못박음 ②(「건너뛴 개수를 말할 것」)가
      //    막으려던 바로 그 오독입니다. 재료는 이미 모델에 있었고 이 자리가 안 읽고 있었습니다.
      const carried = m.points.reduce((n, p) => n + (p.denominator || 0), 0);
      const axisWord = m.valueKind === 'aggregate' && m.axis
        ? (m.skipped > 0
          ? `${m.axis.aggregation}(${m.axis.qualifier}) 는 값 ${carried}개를 «전부 건너뛰었습니다»`
            + ' — 수치가 아니었습니다 (count · distinct 는 잽니다)'
          : `${m.axis.aggregation}(${m.axis.qualifier}) 로 잰 것은 없습니다 — 이 걷기가 그 수식어를 안 실었습니다`)
        : '비율이 붙은 것은 없습니다 — 아직 안 쟀습니다';
      note.textContent = m.points.length
        ? `점 ${m.points.length}개 · ${axisWord}`
        : (m.state === 'truncated' && m.message ? m.message : '이 창에 점이 없습니다');
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

    const rates = points.map((p) => valueOf(p));
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
      line.style.bottom = `${(valueOf(seed) / top) * 100}%`;
      plot.appendChild(line);
    }

    for (const p of points) {
      const dot = doc.createElement('div');
      const marked = markIdOf(p) ? this.signOf(markIdOf(p)) : SIGN.ABSENT;
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
      dot.style.bottom = this.flatRate && maxRate === 0 ? '0%' : `${(valueOf(p) / top) * 100}%`;
      dot.setAttribute('data-wafer', p.wafer || '');
      if (markIdOf(p)) dot.setAttribute('data-node-id', markIdOf(p));
      // The title is the whole point, in the vocabulary the ledger used.
      // 🔴 소유자 요청 (2026-08-24): 「몇 칩 있고 몇 칩 보이드인지 호버하면 어노테이션」.
      //    비율은 «그 둘로 만든 것»이라는 게 보여야 합니다 -- 오늘 「맵은 50%인데 트렌드는 0%」를
      //    못 알아본 자리가 여기입니다. 수는 «응답에 있는 그대로» 띄우고 계산하지 않습니다.
      //    ⚠️ 분자(`found_chip_count`)는 경계 모델이 아직 안 싣습니다 (api.js = 응용 레인).
      //       그래서 그 칸은 «지어내지 않고» 없다고 말합니다 -- 0 이라고 쓰면 「보이드 없음」이
      //       되는데 그건 다른 사실입니다.
      // 🔴 «알갱이»도 같이 말합니다 (총괄 판정 2026-08-24). 맵이 128 을 세고 이 점이 64 를
      //    세는 것은 «어긋남이 아니라» 세는 단위가 다른 것입니다 (128 = 레그 64 + 레그 64).
      //    맵은 「bonding_log ∩ inspection_run 기준」이라 출처를 답는데 이 점은 안 답았고,
      //    그래서 운영자가 두 수를 «모순»으로 읽습니다. 낱말은 «선언된 그대로» 씁니다.
      const grainWord = this.grain && this.grain.subject_type
        ? `${this.grain.subject_type}(${[...(this.grain.identity_fields || []),
          ...(this.grain.context_fields || [])].join(' · ')})`
        : null;
      const seen = p.denominator === null ? '—' : p.denominator;
      const hit = typeof p.found === 'number' ? p.found : '— (경계가 아직 안 싣습니다)';
      // 🔴 집계 축은 «칩»을 세지 않습니다 -- 「검사한 칩」이라 적으면 값의 개수를 칩 수로
      //    읽게 됩니다. 무엇으로 만든 수인지는 축마다 다른 문장이어야 합니다.
      const body = m.valueKind === 'aggregate' && m.axis
        ? ` · ${m.axis.aggregation}(${m.axis.qualifier}) ${formatValue(m, valueOf(p))}`
          + ` · 값 ${seen}개 · 쓴 값 ${hit}개`
        : ` · 검사한 칩 ${seen} · 보이드 난 칩 ${hit}`
          + ` · 비율 ${formatValue(m, valueOf(p))}`;
      dot.setAttribute('title',
        `${p.wafer || '(웨이퍼 없음)'}`
        + body
        + (grainWord ? ` · ${grainWord} 기준` : '')
        + (p.state ? ` · ${p.state}` : ''));
      if (markIdOf(p)) {
        dot.addEventListener('click', (event) => {
          const intent = markingIntent(event);
          // 🔴 이제 «노드»를 찍습니다. 서버가 node_id 를 실으면 그것을, 아직이면 옛 mark_key 를
          //    씁니다 -- 둘 다 없는 점은 애초에 리스너가 안 붙습니다. 「읽는 쪽이 먼저 가지
          //    않는다」는 2단계의 규칙 그대로입니다.
          this.mark(markIdOf(p), intent.sign, intent.mode);
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
    yTop.textContent = maxRate > 0 ? formatValue(m, top) : '—';
    const yBottom = doc.createElement('div');
    yBottom.className = 'rb-trend-ymin';
    yBottom.textContent = m.valueKind === 'aggregate' ? '0' : '0.0%';
    // 🔴 THE X AXIS NAMES ITS TIME. It was saying 「차례」 and nothing else, so the reader could
    //    not see WHEN any of this happened. Measured: every point in this window shares one
    //    timestamp, so the axis says that timestamp -- an order with no clock on it is not an
    //    answer to 「언제」.
    const stamp = (v) => String(v || '').replace('T', ' ').slice(0, 16);

    // 🔴 THE AXIS NAMES THE MATERIAL, NOT JUST THE MOMENT. 「x축에 시간에 추가로 자재 id도」
    //    (owner). Points that belong to one material sit together, so the tick goes under the
    //    middle of that material's points -- one label per material, not one per point.
    const groups = new Map();
    points.forEach((p, i) => {
      const key = p.wafer || '(이름 없음)';
      const at = this.flatTime
        ? (points.length > 1 ? (i / (points.length - 1)) * 100 : 50)
        : ((Date.parse(p.at) - minTime) / spanTime) * 100;
      const g = groups.get(key) || { key, sum: 0, n: 0 };
      g.sum += at; g.n += 1;
      groups.set(key, g);
    });
    for (const g of groups.values()) {
      const tick = doc.createElement('div');
      const marked = this.subjectReads && this.markings
        && this.markings.signOf(this.subjectReads, g.key) !== SIGN.ABSENT;
      tick.className = marked ? 'rb-trend-xtick is-subject' : 'rb-trend-xtick';
      tick.style.left = `${g.sum / g.n}%`;
      tick.textContent = g.key;
      tick.setAttribute('title', `${g.key} · ${g.n}점`);
      plot.appendChild(tick);
    }

    // The moment stays, beside the materials: 「언제」 and 「무엇」 are two questions.
    const xLeft = doc.createElement('div');
    xLeft.className = 'rb-trend-xlabel is-left';
    xLeft.textContent = this.flatTime
      ? `${stamp(points[0].at)} · 한 시각`
      : `${stamp(points[0].at)} → ${stamp(points[points.length - 1].at)}`;
    plot.appendChild(xLeft);
    plot.append(yTop, yBottom);
    return plot;
  }

  /** The marked point, if one is marked; otherwise none. The seed is a MARKING, not a field. */
  _seedPoint(points) {
    for (const p of points) {
      if (markIdOf(p) && this.signOf(markIdOf(p)) === SIGN.CASE) return p;
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
    // 🔴 목업의 「접는 단위」 줄 (A4). 이 차트가 «무엇을 한 점으로 접는지»는 선언에 있습니다 --
    //    grain 의 subject_type 이 그것이고, 지어낼 필요가 없습니다. 단위별 «행수»는 이 라우트가
    //    안 실으므로 그 사실을 적습니다. 자리를 비워 두면 「접지 않는다」로 읽힙니다.
    if (this.grain && this.grain.subject_type) {
      const fold = doc.createElement('span');
      fold.className = 'rb-trend-fold';
      const keys = (this.grain.identity_fields || []).join(' · ');
      fold.textContent = `접는 단위 ${this.grain.subject_type}`
        + (keys ? ` (${keys})` : '')
        + ' · 단위별 행수는 이 응답에 없습니다';
      el.appendChild(fold);
    }
    // 🔴 집계 축은 «자기 문장»을 씁니다 (라운드 ①-a). 비율의 분자·분모 문장을 그대로 쓰면
    //    median(radius_x) 를 「비율」이라 부르게 됩니다.
    if (m.valueKind === 'aggregate' && m.axis) {
      const ax = doc.createElement('span');
      ax.className = 'rb-trend-prov';
      const carried = points.reduce((n, p) => n + (p.denominator || 0), 0);
      ax.textContent = `y = ${m.axis.aggregation}(${m.axis.qualifier})`
        + ` · 값 ${carried}개`
        + (m.provenance && m.provenance.predicates
          ? ` · ${m.provenance.predicates.join(' · ')} 에서` : '');
      el.appendChild(ax);
      // 🔴 건너뛴 수를 «말합니다» (총괄 못박음 ②). 말 안 하면 「없어서」와 「건너뛰어서」가
      //    같은 수가 됩니다 -- 「하나라도 수치면 수치」의 값은 이 문장이 치릅니다.
      if (m.skipped > 0) {
        const skipped = doc.createElement('span');
        skipped.className = 'rb-trend-absent';
        skipped.textContent = `건너뜀 ${m.skipped} — 수치가 아니었습니다`;
        el.appendChild(skipped);
      }
    }
    if (m.provenance && m.valueKind !== 'aggregate') {
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
      // The axis now names the materials and the moment, so the old wording («차례») would
      // contradict what the reader can see on it.
      if (this.flatTime) parts.push('가로는 «자재»입니다 · 시각은 하나뿐입니다');
      flat.textContent = parts.join(' · ');
      el.appendChild(flat);
    }
    const unplotted = m.points.length - points.length;
    if (unplotted > 0) {
      const gap = doc.createElement('span');
      gap.className = 'rb-trend-absent';
      // Not dropped silently: a point without a value is a wafer nobody measured.
      gap.textContent = m.valueKind === 'aggregate' && m.axis
        ? `값 없음 ${unplotted} — 이 자재에는 ${m.axis.qualifier} 가 안 실렸습니다`
        : `비율 없음 ${unplotted} — 안 쟀습니다`;
      el.appendChild(gap);
    }
    return el;
  }
}
