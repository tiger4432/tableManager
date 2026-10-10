// ═══════════════════════════════════════════════════════════════════════════════
// TREND VIEW — the trend part (lead f984ab01d): its own div; a head (the column, the span, Load earlier / later), one
// picture - numbers on a value axis, words in lanes - and a legend. It draws the model trend.js makes; it reads nothing.
// ═══════════════════════════════════════════════════════════════════════════════
import { localMinute } from '../server_time.js';
import { unitText } from '../ui_words.js';
import { OTHERS } from './trend.js';
import { setDisabledReason } from '../disabled_reason.js';

const NS = 'http://www.w3.org/2000/svg';
const W = 900;
const PAD = { l: 136, r: 16, t: 14, b: 30 };
const NUMBER_H = 200;
const LANE_H = 26;
/** A line above the picture for each walked point off the axis on one side (lead 10-10). */
const EDGE_H = 18;

export const TREND_WORDS = Object.freeze({
  title: 'Trend',
  earlier: 'Load earlier',
  later: 'Load later',
  noEarlier: 'Nothing earlier',
  noLater: 'Nothing later',
  close: 'Close',
  none: 'No value with a time in this column',
  other: 'Other rows',
  walked: 'Dashed: the walked time',
  untimed: (n) => `${unitText(n, 'point')} without a time`,
  // The axis is in this screen's time; the server's windows are UTC (lead 10-10).
  local: 'local time',
  edge: (word, time, n) => `${word} walked ${time}${n > 1 ? ` (+${n - 1})` : ''}`,
});

export class TrendView {
  /** @param {HTMLElement} mount @param {{doc?: Document}} deps */
  constructor(mount, deps = {}) {
    this.doc = deps.doc || mount.ownerDocument;
    this.root = this._el('div', 'wk-trend');
    mount.appendChild(this.root);
  }

  _el(tag, cls, text) {
    const n = this.doc.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  _svg(tag, attrs, text) {
    const n = this.doc.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
    if (text !== undefined) n.textContent = text;
    return n;
  }

  _button(word, act, off = '') {
    const b = this._el('button', 'wk-add', word);
    b.type = 'button';
    setDisabledReason(b, off);
    if (b.addEventListener) b.addEventListener('click', act);
    return b;
  }

  /**
   * @param {{title: string, model: object, groups: string[], t0: number|null, onEarlier?: Function, onLater?: Function,
   *          hasEarlier?: boolean, hasLater?: boolean, onClose?: Function}} spec
   */
  show(spec) {
    const { model } = spec;
    this.root.textContent = '';
    const head = this._el('div', 'wk-trend-head');
    head.append(this._el('span', 'wk-label', TREND_WORDS.title), this._el('span', 'wk-trend-title', spec.title));
    const points = model.numbers.length + model.words.length;
    const said = model.t ? `${unitText(points, 'point')} · ${localMinute(new Date(model.t[0]).toISOString())} → ${localMinute(new Date(model.t[1]).toISOString())} ${TREND_WORDS.local}` : '';
    head.append(this._el('span', 'wk-note', [said, model.untimed ? TREND_WORDS.untimed(model.untimed) : ''].filter(Boolean).join(' · ')));
    const acts = this._el('span', 'wk-trend-acts');
    if (spec.onEarlier) acts.append(this._button(TREND_WORDS.earlier, spec.onEarlier, spec.hasEarlier === false ? TREND_WORDS.noEarlier : ''));
    if (spec.onLater) acts.append(this._button(TREND_WORDS.later, spec.onLater, spec.hasLater === false ? TREND_WORDS.noLater : ''));
    if (spec.onClose) acts.append(this._button(TREND_WORDS.close, spec.onClose));
    head.append(acts);
    this.root.append(head);
    if (!model.t) {
      this.root.append(this._el('div', 'wk-note', TREND_WORDS.none));
      return;
    }
    const numberH = model.numbers.length ? NUMBER_H : 0;
    const outside = model.outside || [];
    const edges = Math.max(outside.filter((o) => o.before).length, outside.filter((o) => !o.before).length);
    const top = PAD.t + edges * EDGE_H;
    const H = top + numberH + model.lanes.length * LANE_H + PAD.b;
    const svg = this._svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'wk-trend-svg', role: 'img', 'aria-label': `${TREND_WORDS.title} · ${spec.title}` });
    const [t0, t1] = model.t[0] === model.t[1] ? [model.t[0] - 3600000, model.t[1] + 3600000] : model.t;
    const x = (t) => PAD.l + ((t - t0) / (t1 - t0)) * (W - PAD.l - PAD.r);
    if (numberH) {
      const [v0, v1] = model.v[0] === model.v[1] ? [model.v[0] - 1, model.v[1] + 1] : model.v;
      const y = (v) => top + (1 - (v - v0) / (v1 - v0)) * (numberH - 10);
      for (const v of [v0, (v0 + v1) / 2, v1]) {
        svg.append(this._svg('line', { x1: PAD.l, x2: W - PAD.r, y1: y(v), y2: y(v), class: 'wk-trend-grid' }));
        svg.append(this._svg('text', { x: PAD.l - 8, y: y(v) + 4, 'text-anchor': 'end', class: 'wk-trend-word' }, String(Number(v.toPrecision(6)))));
      }
      for (const p of model.numbers) svg.append(this._dot(x(p.t), y(p.value), p));
    }
    model.lanes.forEach((lane, i) => {
      const ly = top + numberH + i * LANE_H + LANE_H / 2;
      svg.append(this._svg('line', { x1: PAD.l, x2: W - PAD.r, y1: ly, y2: ly, class: 'wk-trend-grid' }));
      svg.append(this._svg('text', { x: PAD.l - 8, y: ly + 4, 'text-anchor': 'end', class: `wk-trend-word${lane === OTHERS ? ' is-others' : ''}` }, lane));
      for (const p of model.words.filter((w) => w.lane === lane)) svg.append(this._dot(x(p.t), ly + jitter(p.key), p));
    });
    for (let k = 0; k <= 4; k += 1) {
      const t = t0 + ((t1 - t0) * k) / 4;
      svg.append(this._svg('text', { x: x(t), y: H - 10, 'text-anchor': k === 0 ? 'start' : k === 4 ? 'end' : 'middle', class: 'wk-trend-word' },
        localMinute(new Date(t).toISOString()).slice(5)));
    }
    if (spec.t0 !== null && spec.t0 >= t0 && spec.t0 <= t1) {
      svg.append(this._svg('line', { x1: x(spec.t0), x2: x(spec.t0), y1: top, y2: H - PAD.b, class: 'wk-trend-t0' }));
    }
    // A walked point off the axis says itself at that edge, in its group's colour; it does not stretch the axis.
    for (const before of [true, false]) {
      outside.filter((o) => o.before === before).forEach((o, i) => {
        const word = TREND_WORDS.edge(o.group === null ? TREND_WORDS.other : spec.groups[o.group], localMinute(new Date(o.t).toISOString()).slice(5), o.n);
        svg.append(this._svg('text', { x: before ? PAD.l : W - PAD.r, y: PAD.t + i * EDGE_H + 12, 'text-anchor': before ? 'start' : 'end',
          class: `wk-trend-edge ${o.group === null ? 'is-other' : `is-g${o.group}`}` }, before ? `◀ ${word}` : `${word} ▶`));
      });
    }
    this.root.append(svg);
    const legend = this._el('div', 'wk-trend-legend');
    spec.groups.forEach((name, i) => legend.append(this._key(`is-g${i}`, name)));
    legend.append(this._key('is-other', TREND_WORDS.other), this._el('span', 'wk-note', TREND_WORDS.walked));
    this.root.append(legend);
  }

  _dot(cx, cy, p) {
    const group = p.group === null || p.group === undefined ? 'is-other' : `is-g${p.group}`;
    const dot = this._svg('circle', { cx: cx.toFixed(1), cy: cy.toFixed(1), r: p.walked ? 5 : group === 'is-other' ? 1.8 : 3,
      class: `wk-tp ${group}${p.walked ? ' is-walked' : ''}`, 'data-key': p.key });
    // Who gave the point, as its cell says (lead 99ed68cb7 C).
    if (p.source) { const said = this._svg('title', {}); said.textContent = p.source; dot.append(said); }
    return dot;
  }

  _key(cls, word) {
    const k = this._el('span', 'wk-trend-key');
    const dot = this._svg('svg', { width: 10, height: 10, viewBox: '0 0 10 10' });
    dot.append(this._svg('circle', { cx: 5, cy: 5, r: 4, class: `wk-tp ${cls}` }));
    k.append(dot, this._el('span', '', word));
    return k;
  }
}

/** A point's place inside its lane, the same for the same key: the lane's dots do not sit on one line. */
function jitter(key) {
  let h = 0;
  for (const ch of String(key)) h = (h * 31 + ch.charCodeAt(0)) % 1000;
  return ((h / 1000) - 0.5) * (LANE_H - 10);
}
