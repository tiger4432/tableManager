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
//      또래 축     🔴 NO ROUTE SERVES THESE COUNTS TODAY. The pills are drawn, the numbers are
//                  「—」, and the panel says so. Inventing 「같은 랏 11」 would be this screen
//                  telling its first lie.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel, markingIntent } from './panel.js';
import { SIGN } from './marking_store.js';
import { fetchTrends, trendsModel, fetchSubgraph, subgraphModel } from './api.js';

/** The peer axes the mockup names. Counts come from a route, never from here. */
const PEER_AXES = ['같은 레그', '같은 랏', '레시피', '설비', '7d'];

export class ControlBarPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    this.apiBase = options.apiBase || '';
    this.fetchImpl = options.fetchImpl || null;
    this.seedNodeId = options.seedNodeId || null;
    this.collect = options.collect || 'quantity';
    this.window = options.window || '180d';
    this.trends = null;
    this.walk = null;
    this.loadState = 'idle';
  }

  mount() {
    super.mount();
    this.load();
  }

  async load() {
    this.loadState = 'loading';
    this.render();
    const [trendResult, walkResult] = await Promise.all([
      fetchTrends({ apiBase: this.apiBase, window: this.window, fetchImpl: this.fetchImpl }),
      this.seedNodeId
        ? fetchSubgraph({
          apiBase: this.apiBase, nodeId: this.seedNodeId,
          collect: this.collect, fetchImpl: this.fetchImpl,
        })
        : Promise.resolve(null),
    ]);
    this.trends = trendsModel(trendResult);
    this.walk = walkResult ? subgraphModel(walkResult) : null;
    this.loadState = 'ready';
    // The first ratio axis is selected only if NOTHING is selected yet: a reload must not
    // silently move a choice the reader made.
    if (this.writes && this.markings && this.markings.count(this.writes) === 0) {
      const first = (this.trends.kinds || [])[0];
      if (first) this.mark(this._axisId('ratio', first.id), SIGN.CASE);
    }
    this.render();
  }

  _axisId(kind, id) { return `axis:${kind}:${id}`; }

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
    root.appendChild(this._group('②', 'Y value', '뿌릴 것', this._valuePills()));

    const grammar = doc.createElement('div');
    grammar.className = 'rb-control-grammar';
    grammar.textContent = 'Group by → Y value → 트렌드에서 씨앗 찍기 → 마킹 → 후보';
    root.appendChild(grammar);

    this.host.appendChild(root);
  }

  _group(ordinal, label, hint, pills) {
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
    return el;
  }

  /** 또래 축. Drawn, but with no counts -- because no route serves them yet. */
  _peerPills() {
    return PEER_AXES.map((axis) => this._pill({
      id: this._axisId('peer', axis),
      text: axis,
      // 🔴 「—」 is the honest count. Not 0, which would say 「또래가 없다」.
      count: null,
      unsourced: true,
    }));
  }

  _valuePills() {
    const pills = [];
    for (const kind of (this.trends && this.trends.kinds) || []) {
      pills.push(this._pill({
        id: this._axisId('ratio', kind.id),
        text: `${kind.label} 비율`,
        count: null,
      }));
    }
    const walk = this.walk;
    if (walk && walk.ok) {
      for (const c of walk.candidates || []) {
        if (!c.measured) continue;
        pills.push(this._pill({ id: this._axisId('quantity', c.id || c.quantity),
          text: c.quantity, count: null }));
      }
      if (walk.counts && walk.counts.nameOnly > 0) {
        // The folded rest, stated as what it is: declared names with nothing measured under them.
        pills.push(this._pill({
          id: null, text: '값 없음', count: walk.counts.nameOnly, unsourced: false, dim: true,
        }));
      }
    }
    if (!pills.length) {
      pills.push(this._pill({ id: null, text: '축 없음 — 아직 못 읽었습니다', count: null, dim: true }));
    }
    return pills;
  }

  _pill(spec) {
    const doc = this.doc;
    const el = doc.createElement('span');
    const chosen = spec.id ? this.signOf(spec.id) === SIGN.CASE : false;
    el.className = 'rb-pill'
      + (chosen ? ' is-chosen' : '')
      + (spec.dim ? ' rb-pill--dim' : '')
      + (spec.unsourced ? ' rb-pill--unsourced' : '');
    if (spec.id) el.setAttribute('data-axis-id', spec.id);
    const text = doc.createElement('span');
    text.className = 'rb-pill-text';
    text.textContent = spec.text;
    el.appendChild(text);
    const n = doc.createElement('span');
    n.className = spec.count === null ? 'rb-pill-count is-absent' : 'rb-pill-count';
    n.textContent = spec.count === null ? '—' : String(spec.count);
    el.appendChild(n);
    if (spec.id) {
      el.addEventListener('click', (event) => {
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
