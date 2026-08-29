// ═══════════════════════════════════════════════════════════════════════════════
// 부품 2 — 제어 막대 (축 선택자). 목업 2a ③.
//
// 🔴 THIS IS THE SCREEN'S GRAMMAR: Group by → Y value → 트렌드에서 씨앗 찍기 → 마킹 → 후보.
//    Everything else on the board answers a question this bar asked.
//
// 🔴 A SELECTION IS A MARKING. The chosen axis is written into a NAMED marking exactly like a
//    marked die: one id under `writes`, replaced on every plain click. So a part that wants to
//    follow the axis declares `reads: <that name>` and nothing new is invented -- no second
//    store, no second subscription mechanism, no second vocabulary.
//    ⚠️ Reported to the Lead PM rather than assumed: this widens 「마킹」 from 「내가 찍은 것」 to
//       「지금 고른 것」. If that reading is wrong the fix is a second store, not a change here.
//
// 🔴 EVERY COUNT ON A PILL IS SOURCED, AND A COUNT NOBODY SERVES IS 「—」, NOT A ZERO.
//    Measured 2026-08-23:
//      비율 N      `trends.selectable_finding_kinds`      (void · delam = 2)
//      물리량 N    walk candidates WITH a measurement      (`measured`)
//      값 없음 N   walk candidates that are a model NAME   (the folded rest)
// 🔴 Y축은 «집계 × 수식어» 한 쌍입니다 (라운드 ①-a, 2026-08-29). 그 전에는 «종류»(void 비율)
//    였고, 그 목록이 죽은 `/trends` 라우트의 `selectable_finding_kinds` 에서 왔습니다 -- 그래서
//    404 의 뿌리는 «차트»가 아니라 «알약»이었습니다. 셋이 서로 다른 곳에서 옵니다:
//      집계     고정 목록(`AGGREGATIONS`). 데이터가 필요 없어 «마킹이 비어도» 고를 수 있습니다
//      수식어   «선언»(`/declaration`). 마킹과 무관합니다
//      수치인가 «데이터». 마킹이 있을 때만 알 수 있고, 없으면 「재려면 마킹이 필요합니다」라고
//              말합니다 -- 「값 없음」이나 빈 목록으로 두면 「없어서」와 구별이 사라집니다
//
//      또래 축     🔴 NO ROUTE SERVES THESE COUNTS TODAY. The pills are drawn, the numbers are
//                  「—」, and the panel says so. Inventing 「같은 랏 11」 would be this screen
//                  telling its first lie.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel, markingIntent } from './panel.js';
import { SIGN } from './marking_store.js';
import { createWalk, AGGREGATIONS, qualifiersFromDeclaration, qualifierTypesFromWalk } from './api.js';

/**
 * The peer axes the mockup names, as a FALLBACK for a screen that declares none. Counts never
 * come from here -- a pill with no route behind it keeps 「—」.
 */
const PEER_AXES = ['같은 레그', '같은 랏', '레시피', '설비', '7d'];

export class ControlBarPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    // 🔴 ONE CALL — 소유자가 그린 데이터 흐름(2026-08-24): 부품은 { start, collect } 만 선언하고
    //    라우트·질의·모델을 다시는 부르지 않습니다. 화면이 walk 하나를 «주입»하므로 같은 walk 을
    //    쓰는 두 부품이 요청 하나를 나눠 씁니다. 혼자 서는 부품은 자기 것을 만듭니다.
    this.walk = options.walk || createWalk({ apiBase: options.apiBase, fetchImpl: options.fetchImpl });
    // 시작점과 걷는 종류. 값이고 축이 아닙니다 — 소유자: 「일단 wafer 로 고정」.
    this.start = options.start || null;
    // 🔴 수식어 목록은 «선언»에서 옵니다 (라운드 ①-a). 화면이 주입하고 부품은 라우트를 모릅니다.
    //    이 자리에 있던 `collect: 'trend_y'` 가 이 화면에 남은 마지막 `/trends` 호출이었습니다.
    this.loadDeclaration = options.loadDeclaration || null;
    // 🔴 「수치인가」는 «데이터»가 정하므로 «주어»가 필요합니다. 이 이름의 마킹이 비면 재지
    //    않고, 수식어는 «그대로 보이면서» 왜 못 쟀는지를 문장으로 말합니다.
    this.numericReads = options.numericReads || null;
    this.qualifiers = [];
    this.qualifierTypes = null;
    this.declarationState = 'idle';
    this.declarationMessage = null;
    // 아직 아무 쌍도 안 골랐을 때의 «집계». 고정 목록에서 오므로 데이터가 없어도 값이 있습니다.
    this.aggregation = options.aggregation || 'count';
    this._numericOff = null;
    this._sampledKey = null;
    // 🔴 후보 «질문 전체»를 받습니다. 전에는 `candidateCollect` 한 칸만 받아서 맨몸으로
    //    걸었고, 그래서 같은 질문이 화면에서 세 갈래로 나갔습니다 (총괄 실측 2026-08-25).
    //    통째로 받아 통째로 펼치면 walk 의 합침 열쇠가 다른 두 자리와 «글자 그대로» 같습니다.
    this.candidateQuestion = options.candidateQuestion || { collect: 'candidate' };
    this.fetchImpl = options.fetchImpl || null;
    this.seedNodeId = options.seedNodeId || null;
    this.window = options.window || '180d';
    // 🔴 THE SCOPES ARE DECLARED, THE COUNTS ARE FETCHED. `[{label, scope}]` -- the screen picks
    //    which lot and which equipment axis it means (the route answers several), and a peer
    //    with no scope declared stays 「—」 rather than becoming a zero.
    this.peers = Array.isArray(options.peers) ? options.peers.slice() : [];
    this.loadPeerCount = options.loadPeerCount || null;
    this.peerCounts = Object.create(null);
    this.candidateWalk = null;
    this.loadState = 'idle';
  }

  mount() {
    super.mount();
    if (this.numericReads && this.markings) {
      this._numericOff = this.markings.subscribe(this.numericReads, () => this._sampleNumeric());
    }
    this.load();
  }

  destroy() {
    if (this._numericOff) this._numericOff();
    this._numericOff = null;
    super.destroy();
  }

  async load() {
    this.loadState = 'loading';
    this.render();
    const [declaration, candidates] = await Promise.all([
      this.loadDeclaration ? this.loadDeclaration() : Promise.resolve(null),
      this.seedNodeId
        ? this.walk({
          start: { groupby: 'wafer', value: this.seedNodeId },
          ...this.candidateQuestion,
        })
        : Promise.resolve(null),
    ]);
    // 선언은 원장을 안 읽습니다 -- 마킹이 비어 있어도 이 목록은 «전부» 서 있습니다.
    this.qualifiers = declaration && declaration.ok ? qualifiersFromDeclaration(declaration) : [];
    this.declarationState = declaration ? (declaration.ok ? 'ready' : 'refused') : 'absent';
    this.declarationMessage = declaration && !declaration.ok ? declaration.message : null;
    // Each declared scope is one call; a refusal leaves that pill at 「—」 and the others stand.
    if (this.loadPeerCount) {
      for (const peer of this.peers) {
        if (!peer.scope) continue;
        Promise.resolve().then(() => this.loadPeerCount(peer.scope))
          .then((got) => { this.peerCounts[peer.scope] = got; this.render(); })
          .catch(() => {});
      }
    }
    this.candidateWalk = candidates || null;
    this.loadState = 'ready';
    // 🔴 «자동 선택 없음» (라운드 ①-a). 전에는 첫 비율 축을 대신 골라 줬는데, 집계 축에는
    //    대신 골라 줄 「첫째」가 없습니다 -- `count × ?` 를 대신 고르면 아무도 안 고른 축을
    //    차트가 그리게 됩니다. 아무것도 안 골랐으면 차트는 «자기 기본»(비율)을 그립니다.
    this.render();
    this._sampleNumeric();
  }

  _axisId(kind, id) { return `axis:${kind}:${id}`; }

  /**
   * 「수치인가」는 «데이터»입니다 -- 마킹이 비면 걷지 않고, 그 사실을 문장으로 말합니다.
   * 🔴 여기서 «거르지» 않습니다. 걷기가 실은 값을 그대로 세고, 판정은 알약이 합니다.
   */
  _sampleNumeric() {
    const start = this.numericReads
      ? this.startFor({ marking: this.numericReads, groupby: 'wafer' })
      : null;
    if (!start) {
      this._sampledKey = null;
      if (this.qualifierTypes === null) return;
      this.qualifierTypes = null;
      this.render();
      return;
    }
    const key = JSON.stringify(start);
    if (key === this._sampledKey) return;
    this._sampledKey = key;
    Promise.resolve()
      .then(() => this.walk({ start }))
      .then((answer) => {
        this.qualifierTypes = answer && answer.ok ? qualifierTypesFromWalk(answer) : {};
        this.render();
      })
      .catch(() => {});
  }

  /**
   * 「지금 무엇이 골라져 있나」 -- «마킹»에서 읽습니다. 부품이 따로 들고 있으면 밖에서
   * 바뀐 축(선언 패널의 Y 드롭다운도 같은 이름에 씁니다)과 둘이 어긋납니다.
   */
  _chosenPair() {
    const entries = this.markings && this.reads ? this.markings.entries(this.reads) : [];
    const id = entries.length ? entries[0][0] : null;
    const parts = String(id || '').split(':');
    if (parts[1] !== 'agg') return { aggregation: this.aggregation, qualifier: null };
    const rest = parts.slice(2).join(':');
    const cut = rest.indexOf(':');
    if (cut < 0) return { aggregation: rest || this.aggregation, qualifier: null };
    return { aggregation: rest.slice(0, cut), qualifier: rest.slice(cut + 1) };
  }

  /** 쌍이 «완성됐을 때만» 축이 됩니다. 집계만 고른 상태는 아직 축이 아니라 «고르는 중»입니다. */
  _writePair(aggregation, qualifier) {
    this.aggregation = aggregation;
    if (qualifier) this.mark(`axis:agg:${aggregation}:${qualifier}`, SIGN.CASE);
    this.render();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    this.host.textContent = '';
    const root = doc.createElement('div');
    root.className = 'rb-control';

    if (this.title) {
      const cap = doc.createElement('div');
      cap.className = 'rb-part-title';
      cap.textContent = this.title;
      root.appendChild(cap);
    }

    root.appendChild(this._group('①', 'Group by', '또래', this._peerPills()));
    root.appendChild(this._group('②', 'Y value', '수식어', this._valuePills(), this._numericNote()));
    root.appendChild(this._group('③', '집계', '어떻게 재나', this._aggregationPills()));

    const grammar = doc.createElement('div');
    grammar.className = 'rb-control-grammar';
    grammar.textContent = 'Group by → Y value → 트렌드에서 씨앗 찍기 → 마킹 → 후보';
    root.appendChild(grammar);

    this.host.appendChild(root);
  }

  _group(ordinal, label, hint, pills, note) {
    const doc = this.doc;
    const el = doc.createElement('div');
    el.className = 'rb-control-group';
    const n = doc.createElement('span');
    n.className = 'rb-control-ordinal';
    n.textContent = ordinal;
    const name = doc.createElement('span');
    name.className = 'rb-control-label';
    name.textContent = label;
    const h = doc.createElement('span');
    h.className = 'rb-control-hint';
    h.textContent = hint;
    el.append(n, name, h);
    for (const pill of pills) el.appendChild(pill);
    if (note) el.appendChild(note);
    return el;
  }

  /**
   * 🔴 세 문장이 «서로 다릅니다» (총괄 지시 ①-a). 「아직 안 골라서 못 잰다」를 「값 없음」이나
   *    빈 목록으로 그리면 「없어서」와 구별이 사라집니다 -- 이 보드가 존재하는 이유입니다.
   */
  _numericNote() {
    const doc = this.doc;
    const note = doc.createElement('div');
    note.className = 'rb-control-note';
    if (this.declarationState === 'refused') {
      note.textContent = `선언을 못 읽었습니다 — ${this.declarationMessage || ''}`;
    } else if (this.declarationState === 'absent') {
      note.textContent = '선언을 받지 못했습니다 — 수식어 목록은 선언에서 옵니다';
    } else if (!this.numericReads) {
      note.textContent = '수식어는 선언에서 옵니다 · 수치인지는 이 부품이 재지 않습니다';
    } else if (this.qualifierTypes === null) {
      // 🔴 이 문장이 게이트 ② 입니다. 목록은 «그대로 서 있고», 못 잰 이유만 말합니다.
      note.textContent = `재려면 마킹이 필요합니다 — ${this.numericReads} 이 비어 있습니다`
        + ' (수식어는 선언에서 오므로 그대로 있습니다)';
    } else {
      const carried = this.qualifiers
        .filter((q) => (this.qualifierTypes[q.name] || {}).seen).length;
      note.textContent = `${this.numericReads} 에서 쟀습니다`
        + ` · 값이 실려 온 수식어 ${carried}/${this.qualifiers.length}`;
    }
    return note;
  }

  /**
   * 고정 목록입니다 -- 데이터가 «필요 없어» 마킹이 비어도 고를 수 있습니다.
   * 🔴 수치 전용 집계는 «재 본 뒤에만» 끕니다. 안 재 봤는데 끄면 「아직 안 골라서」가
   *    「이 수식어로는 못 한다」로 읽힙니다.
   */
  _aggregationPills() {
    const chosen = this._chosenPair();
    const seen = chosen.qualifier && this.qualifierTypes
      ? (this.qualifierTypes[chosen.qualifier] || { seen: 0, numeric: 0 })
      : null;
    const nonNumeric = Boolean(seen && seen.seen > 0 && seen.numeric === 0);
    return AGGREGATIONS.map((agg) => this._pill({
      id: this._axisId('aggregation', agg.id),
      text: agg.label,
      count: undefined,
      chosen: chosen.aggregation === agg.id,
      dim: agg.numericOnly && nonNumeric,
      title: agg.numericOnly
        ? (nonNumeric
          ? `${chosen.qualifier} 는 이 마킹에서 수치가 아니었습니다`
          : '수치인 값만 셉니다 — 건너뛴 수는 차트가 말합니다')
        : '값의 종류를 가리지 않습니다',
      onPick: () => this._writePair(agg.id, this._chosenPair().qualifier),
    }));
  }

  /** 또래 축. Counts come from `siblings`; a scope the screen did not declare stays 「—」. */
  _peerPills() {
    const declared = this.peers.length
      ? this.peers
      : PEER_AXES.map((label) => ({ label, scope: null }));
    return declared.map((peer) => {
      const got = peer.scope ? this.peerCounts[peer.scope] : null;
      const has = got && typeof got.subjects === 'number';
      // 🔴 THE FOURTH ABSENCE, IN ITS OWN WORDS. The other three are 「아직 안 골랐다」·
      //    「그 종류가 없다」·「대조를 안 했다」. This one is 「걸쳐 있어 어느 쪽도 아니다」: the
      //    axis resolved and its subjects exist, but none of them is on the marked side, so
      //    there is nothing to compare with. Writing the resolved number alone would say the
      //    opposite of what happened -- which is the misreading this whole screen exists to end.
      const straddled = has && got.analysis === 'empty';
      if (straddled) {
        return this._pill({
          id: this._axisId('peer', peer.label),
          text: `${peer.label} · 대조 0 · 걸침 ${got.straddling === null ? got.subjects : got.straddling}`,
          count: undefined,
          unsourced: true,
          title: [got.message || got.straddleMessage, this._peerTitle(got)]
            .filter(Boolean).join(' · ') || null,
        });
      }
      return this._pill({
        id: this._axisId('peer', peer.label),
        // 🔴 「—」 is the honest count. Not 0, which would say 「또래가 없다」.
        // 🔴 AND WHEN THE AXIS ITSELF IS ABSENT, 「—」 IS NOT ENOUGH (round Z-3, 2026-08-28).
        //    Measured: `leg`, `bond_lot` and `scan_recipe` appear in ZERO atoms, so the window
        //    has nothing to count -- but a dash here reads exactly like 「세어 봤더니 0」 and
        //    like 「아직 안 왔다」. The sentence rides in the pill's own text so the reader sees
        //    WHY, and so the missing axis stays visible as something the declaration could gain.
        text: got && got.message ? `${peer.label} · ${got.message}` : peer.label,
        count: has ? got.subjects : null,
        unsourced: !has,
        // 🔴 수를 쓰면 «어디서 왔는지»도 씁니다 -- 맵은 「bonding_log ∩ inspection_run 기준」이라
        //    적는데 이 알약만 안 적고 있었습니다. 경로가 한쪽만 죽는 날 두 회계가 «같은 수»처럼
        //    읽힙니다. 서버가 이미 싣는 것이고 (scope.relation · scope.column), 지어내지 않습니다.
        title: this._peerTitle(got),
      });
    });
  }

  _valuePills() {
    const pills = [];
    const chosen = this._chosenPair();
    // 🔴 목록은 «선언»입니다 -- 마킹과 무관하게 전부 서 있습니다. 곁수(수치 n/m)만 데이터에서
    //    오고, 안 재 봤으면 그 곁수가 «없을» 뿐 알약은 사라지지 않습니다.
    for (const q of this.qualifiers) {
      const got = this.qualifierTypes ? (this.qualifierTypes[q.name] || { seen: 0, numeric: 0 }) : null;
      const words = got
        ? (got.seen ? `수치 ${got.numeric}/${got.seen}` : '이 마킹에는 값이 없습니다')
        : null;
      pills.push(this._pill({
        id: this._axisId('qualifier', q.name),
        text: words ? `${q.name} · ${words}` : q.name,
        count: undefined,
        chosen: chosen.qualifier === q.name,
        // 어느 술어가 이 수식어를 «싣는지»는 선언이 이미 압니다. 지어내지 않습니다.
        title: `${q.predicates.join(' · ')} 이 싣습니다`,
        onPick: () => this._writePair(this._chosenPair().aggregation, q.name),
      }));
    }
    const walk = this.candidateWalk;
    if (walk && walk.ok) {
      for (const c of walk.candidates || []) {
        if (!c.measured) continue;
        pills.push(this._pill({ id: this._axisId('quantity', c.id || c.quantity),
          text: c.quantity, count: undefined }));
      }
      if (walk.counts && walk.counts.nameOnly > 0) {
        // The folded rest, stated as what it is: declared names with nothing measured under them.
        pills.push(this._pill({
          id: null, text: '값 없음', count: walk.counts.nameOnly, unsourced: false, dim: true,
        }));
      }
    }
    if (!pills.length) {
      pills.push(this._pill({
        id: null,
        text: this.loadState === 'loading' ? '선언을 읽는 중…' : '축 없음 — 아직 못 읽었습니다',
        count: null, dim: true,
      }));
    }
    return pills;
  }

  /** 알약 하나의 «출처와 곁수». 안 온 것은 안 적습니다 -- 빈 문자열도 지어낸 값입니다. */
  _peerTitle(got) {
    if (!got) return null;
    const parts = [];
    if (typeof got.units === 'number') parts.push(`유닛 ${got.units}`);
    if (got.relation) parts.push(`${got.relation}${got.column ? `.${got.column}` : ''} 기준`);
    return parts.length ? parts.join(' · ') : null;
  }

  _pill(spec) {
    const doc = this.doc;
    const el = doc.createElement('span');
    // 🔴 «쌍»을 쓰는 알약은 자기 id 로 마킹되지 않습니다 (라운드 ①-a) -- 마킹에 들어가는 것은
    //    `axis:agg:<집계>:<수식어>` 하나이고, 이 알약은 그 쌍의 «반쪽»입니다. 그래서 골라진
    //    상태를 부르는 쪽이 말해 주고, 그것을 안 주는 알약은 예전대로 마킹에서 읽습니다.
    const chosen = spec.chosen !== undefined
      ? Boolean(spec.chosen)
      : (spec.id ? this.signOf(spec.id) === SIGN.CASE : false);
    el.className = 'rb-pill'
      + (chosen ? ' is-chosen' : '')
      + (spec.dim ? ' rb-pill--dim' : '')
      + (spec.unsourced ? ' rb-pill--unsourced' : '');
    if (spec.id) el.setAttribute('data-axis-id', spec.id);
    const text = doc.createElement('span');
    text.className = 'rb-pill-text';
    text.textContent = spec.text;
    el.appendChild(text);
    // `null` means 「the route served no number」 and draws 「—」. `undefined` means this pill
    // already SAYS its numbers in words, so a dash after them would be a second, emptier claim.
    if (spec.count !== undefined) {
      const n = doc.createElement('span');
      n.className = spec.count === null ? 'rb-pill-count is-absent' : 'rb-pill-count';
      n.textContent = spec.count === null ? '—' : String(spec.count);
      el.appendChild(n);
    }
    if (spec.title) el.setAttribute('title', spec.title);
    if (spec.id) {
      el.addEventListener('click', (event) => {
        if (spec.onPick) { spec.onPick(event); return; }
        // A plain click REPLACES, which is what single-select means. Ctrl still adds, and on an
        // axis that is a legitimate question -- two Y values is a comparison, not an error.
        const intent = markingIntent(event);
        this.mark(spec.id, intent.sign, intent.mode);
        this.render();
      });
    }
    return el;
  }
}
