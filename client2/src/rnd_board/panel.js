// ═══════════════════════════════════════════════════════════════════════════════
// PANEL -- the component contract. A CLASS, so two of the same part can stand on one screen.
//
// 🔴 THE MEASURED FAILURE THIS EXISTS TO NOT REPEAT. `src/ledger_map_panel.js` holds `deps`,
//    `mountEl` and `session` at MODULE level, so a second `initLedgerMap` overwrites the
//    first: that file cannot be placed twice on one page, and nothing about it says so. Every
//    piece of per-instance state here is on `this`, set in the constructor.
//
// 🔴 A PANEL DOES NOT DECIDE ITS OWN SIZE. It is handed a box by the shell and re-lays-out
//    when the box changes (`resize`). This is the one condition that keeps the later
//    drag/resize work from being a rewrite: a part that bakes in 560px is a part that gets
//    re-written the day the user drags its corner. There is NO width or height constant in a
//    part, and the harness scores that a panel repaints at a size it never saw at mount.
//
// 🔴 A PANEL DRAWS IN ITS OWN `host` AND NOWHERE ELSE. It never reaches for a sibling, never
//    queries the document, never touches the shell. That is what makes the placement the
//    SHELL's data: a part carries no coordinates because it cannot see any.
//
// 🔴 `document` IS A DEPENDENCY, NOT A GLOBAL -- so a part is scorable under bare node.
//    (`surprise_map_view.js` established that discipline. 지금은 없는 파일 -- 근거는 이 줄이 마지막입니다.)
//
// MARKINGS: a part declares the name it READS and the name it WRITES, SEPARATELY. They may
// differ -- a rank table reads marking:2 and writes nothing; a map may write marking:1 while
// reading marking:2. The part never learns any other name exists.
// ═══════════════════════════════════════════════════════════════════════════════

import { SIGN } from './marking_store.js';
import { createWalk } from './api.js';

/**
 * The modifier keys, read ONCE, in the vocabulary the store speaks. Four parts read the same
 * three keys, and a screen where ctrl means 「더하기」 in one panel and something else in the
 * next is not one screen.
 *
 * Ctrl (or Cmd) ADDS; Shift picks the SIGN and COMPOSES with it, so ctrl+shift+click adds a
 * control. Nothing here decides what is marked -- only how.
 */
export function markingIntent(event) {
  const e = event || {};
  return {
    mode: (e.ctrlKey || e.metaKey) ? 'add' : 'replace',
    sign: e.shiftKey ? SIGN.CONTROL : SIGN.CASE,
  };
}

export class Panel {
  /**
   * @param {object} host  the element THIS panel owns. Made by the shell, never by the part.
   * @param {{doc: Document, markings: import('./marking_store.js').MarkingStore,
   *          reads?: string|null, writes?: string|null, title?: string}} deps
   */
  constructor(host, deps) {
    const options = deps || {};
    this.host = host;
    this.doc = options.doc;
    this.markings = options.markings;
    // The two names, declared at assembly time. `null` is a legitimate value: a part that
    // reads nothing simply never re-renders on a marking, and one that writes nothing is
    // read-only. Neither is a special case anywhere below.
    this.reads = options.reads || null;
    this.writes = options.writes || null;
    this.title = options.title || '';
    // The box, in CSS pixels. Zero until the shell measures -- a part must render something
    // sane before it has ever been sized (first paint happens before the first observation).
    this.box = { width: 0, height: 0 };
    this._unsubscribe = null;
  }

  /** Subscribe, then draw once. The shell calls this; a part does not mount itself. */
  mount() {
    if (this.reads && this.markings) {
      this._unsubscribe = this.markings.subscribe(this.reads, () => this.onMarkingChanged());
    }
    // A start marking this part does not READ is still its question: a change to it is a new one.
    const asked = this.start && this.start.marking;
    if (asked && asked !== this.reads && this.markings) {
      this._startOff = this.markings.subscribe(asked, () => this.onStartChanged());
    }
    this.render();
  }

  /** The shell hands over a box. The part fits it. */
  resize(width, height) {
    const w = Math.max(0, Math.floor(width));
    const h = Math.max(0, Math.floor(height));
    if (w === this.box.width && h === this.box.height) return;
    this.box = { width: w, height: h };
    this.onResize();
  }

  destroy() {
    if (this._unsubscribe) this._unsubscribe();
    this._unsubscribe = null;
    if (this._startOff) this._startOff();
    this._startOff = null;
    if (this.host) this.host.textContent = '';
  }

  // ── the marking contract, in two lines a part actually calls ──────────────────

  /**
   * How many marks stand under the name THIS part READS. Attenuation keys off it: while it is
   * zero nothing is dimmed, because 「아직 안 골랐다」 is not 「이건 아니다」.
   */
  /**
   * 🔴 START IS A MARKING (소유자 상설 2026-08-24: 「마킹한 노드의 하위 그래프를 데이터로」).
   *    A declaration may name one instead of carrying a literal id, and then the walk's subject
   *    is whatever the reader has marked -- signs included, because 「여기서 났다」 and 「봤는데
   *    안 났다」 are different sentences and the route takes them as `positive`/`negative`
   *    (`task/MARKING_CONTRACT.md` §1).
   *
   * @returns the start to walk with, or `null` when the marking is EMPTY -- which is not an
   *          error and not a zero: it is 「아직 안 골랐다」, and the caller says so instead of
   *          asking a question with no subject.
   */
  startFor(given) {
    const decl = given || this.start || null;
    if (!decl || !decl.marking || !this.markings) return decl;
    const entries = this.markings.entries(decl.marking);
    // 🔴 AN EMPTY MARKING MAY NAME WHAT IT MEANS (lead 09-30): a start that declares `otherwise`
    //    asks about that node — one defect, no controls — until something is marked. Controls
    //    alone are still no question.
    if (!entries.length && decl.otherwise) {
      const value = decl.otherwise.value;
      return { ...decl, value, positive: [value], negative: [], fallback: true };
    }
    const positive = entries.filter((e) => e[1] === SIGN.CASE).map((e) => e[0]);
    const negative = entries.filter((e) => e[1] === SIGN.CONTROL).map((e) => e[0]);
    if (!positive.length) return null;
    return { ...decl, value: decl.value || positive[0], positive, negative };
  }

  markCount() {
    if (!this.reads || !this.markings) return 0;
    return this.markings.count(this.reads);
  }

  /** `+1` | `-1` | `0` for a node, under the name THIS part declared it reads. */
  signOf(nodeId) {
    if (!this.reads || !this.markings) return SIGN.ABSENT;
    return this.markings.signOf(this.reads, nodeId);
  }

  /**
   * Write under the name THIS part declared it writes. A part with no write name is inert.
   *
   * 🔴 A PLAIN CLICK REPLACES, AND THAT IS THE DEFAULT. The owner named the defect: 「클릭하면
   *    «초기화되고 새로» 되어야하는데 ctrl+클릭이 마킹 «누적»」. Accumulating on every click
   *    makes 「이것만 다시 보고 싶다」 impossible -- you have to undo the last N clicks first --
   *    and that is what read as unnatural. `'add'` (ctrl/cmd) accumulates, and re-adding the
   *    same node with the same sign clears it: toggling belongs THERE and nowhere else.
   *
   *    The default is `replace` on purpose. A part that forgets to pass a mode then behaves
   *    like every other part instead of quietly reintroducing the defect.
   */
  mark(nodeId, sign, mode = 'replace') {
    if (!this.writes || !this.markings) return SIGN.ABSENT;
    if (mode === 'add') return this.markings.toggle(this.writes, nodeId, sign);
    this.markings.clear(this.writes);
    return this.markings.set(this.writes, nodeId, sign);
  }

  // ── hooks a part overrides ────────────────────────────────────────────────────

  /** Build/redraw the whole panel into `this.host`. */
  render() {}

  /** The marking this part reads changed. Default: redraw. */
  onMarkingChanged() { this.render(); }

  /** Its start marking changed, when that is not the one it reads. Default: nothing. */
  onStartChanged() {}

  /** The box changed. Default: redraw. */
  onResize() { this.render(); }
}

/**
 * The walked lists' prelude (candidate list · rank list, lead d4a949a8c ㉱): the walk they share,
 * the seat's question or a fixed seed, a walk on mount and whenever the question moves.
 * ⚠️ Not in `Panel` itself: its `onStartChanged` is a no-op other subscribed panels inherit.
 */
export class WalkedListPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    // 🔴 ONE CALL — 소유자가 그린 데이터 흐름(2026-08-24): 부품은 { start, collect } 만 선언하고
    //    라우트·질의·모델을 다시는 부르지 않습니다. 화면이 walk 하나를 «주입»하므로 같은 walk 을
    //    쓰는 두 부품이 요청 하나를 나눠 씁니다. 혼자 서는 부품은 자기 것을 만듭니다.
    this.walk = options.walk || createWalk({ apiBase: options.apiBase, fetchImpl: options.fetchImpl });
    // 시작점과 걷는 종류. 값이고 축이 아닙니다 — 소유자: 「일단 wafer 로 고정」.
    this.start = options.start || null;
    // 이 걷기의 «예산». 기본값에 기대면 끊긴 걷기가 「후보 없음」으로 보입니다
    // (오늘 두 번 그렇게 읽혔습니다).
    // 🔴 이 화면에서는 «여기로 안 들어옵니다» -- `CANDIDATE_QUESTION` 이 선언에 실려
    //    `bindLoaders` 의 질문으로 들어오고, 그게 세 자리를 한 요청으로 합치는 조건입니다.
    //    남겨 둔 이유는 이 부품이 «혼자 설» 때입니다: 그때는 질문을 얹어 줄 선언이 없습니다.
    this.nodeLimit = options.nodeLimit || null;
    this.seedNodeId = options.seedNodeId || null;
    this.legacyRoute = options.legacyRoute || 'candidate';
    this.fetchImpl = options.fetchImpl || null;
    this.model = null;
    this.loadState = this.seed() ? 'idle' : 'no-seed';
  }

  /** The walk's start: the seat's question (its marking, or what it names while that is empty),
   *  or a fixed seed when the part stands alone. */
  seed() {
    if (this.start && this.start.marking) return this.startFor();
    return this.start || (this.seedNodeId ? { groupby: 'wafer', value: this.seedNodeId } : null);
  }

  mount() {
    super.mount();
    if (this.seed()) this.load();
  }

  /** The question moved: walk again. */
  onStartChanged() { this.load(); }

  async load() {
    const start = this.seed();
    if (!start) {
      this.model = null;
      this.loadState = 'no-seed';
      this.render();
      return;
    }
    this.loadState = 'loading';
    this.render();
    this.model = await this.walk({
      start,
      legacyRoute: this.legacyRoute,
      ...(this.nodeLimit ? { node_limit: this.nodeLimit } : {}),
    });
    this.loadState = this.model.ok ? 'ready' : 'refused';
    this.render();
  }
}
