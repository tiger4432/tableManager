// ═══════════════════════════════════════════════════════════════════════════════
// MARKING STORE -- N markings, keyed by NAME, living OUTSIDE every component.
//
// 🔴 WHAT THIS STORE KNOWS, EXHAUSTIVELY:
//
//       name (string)  ->  { node id (string) -> sign (+1 | -1) }
//
//    It does not know what a node is, what kind it is, what shape draws it, or which
//    component is looking. `task/APPLICATION_MARKING_UNIT_BRIEF.md` §8 acceptance H:
//    「저장소가 아는 것 = 이름 -> (id -> 부호). 타입·모양은 여전히 모른다」. The moment this
//    file learns a type, every component has to agree with it and the contract leaks.
//
// 🔴 THERE ARE NO `marking1` / `marking2` FIELDS, AND THAT IS THE WHOLE POINT.
//    Names are DATA. A third marking is a third string a screen declares when it assembles
//    itself -- no branch here, no field, no enum, no registration call. The harness proves
//    this by driving a name this file has never seen (`rnd_board_harness.mjs` §C).
//
// 🔴 TWO AXES, ORTHOGONAL, AND FOLDING THEM IS THE KNOWN TRAP (brief §10):
//       NAME  「어느 문맥의 마킹인가」   marking:1 (map) · marking:2 (candidates)
//       SIGN  「케이스냐 컨트롤이냐」    +1 / -1
//    Collapsing them ("marking1 = case, marking2 = control") makes case/control impossible
//    the moment there are two contexts, which is exactly the owner's screen.
//
// 🔴 THREE STATES, NOT TWO (brief §9). `-1` (looked and found nothing -- a CONTROL) and
//    ABSENT (never looked) answer different questions, and only the first can exclude a
//    factor. A flat Set collapses them into one cell and the contrast starts lying. So
//    `signOf` returns ABSENT(0) / CASE(+1) / CONTROL(-1) and never a boolean.
//
// NO DOM, NO NETWORK, NO `window`. Scored under bare node.
// ═══════════════════════════════════════════════════════════════════════════════

/** The sign axis. ABSENT is a THIRD value, not the falsy edge of a boolean. */
export const SIGN = Object.freeze({ ABSENT: 0, CASE: 1, CONTROL: -1 });

function normaliseSign(sign) {
  if (sign === SIGN.CASE || sign === SIGN.CONTROL) return sign;
  if (sign === SIGN.ABSENT || sign === null || sign === undefined) return SIGN.ABSENT;
  throw new Error(`marking sign must be +1, -1 or 0; got ${JSON.stringify(sign)}`);
}

export class MarkingStore {
  constructor() {
    // name -> Map(nodeId -> sign). Created on first WRITE or first SUBSCRIBE; never
    // declared up front, because a declared roster is the hardcoded list wearing a hat.
    this._marks = new Map();
    this._listeners = new Map();
  }

  /** `+1` | `-1` | `0`. The question every component asks, and the only one. */
  signOf(name, nodeId) {
    const set = this._marks.get(name);
    if (!set) return SIGN.ABSENT;
    const sign = set.get(nodeId);
    return sign === undefined ? SIGN.ABSENT : sign;
  }

  /** How many marks stand under this name. `0` for a name nobody has written. */
  count(name) {
    const set = this._marks.get(name);
    return set ? set.size : 0;
  }

  /** `[[nodeId, sign], ...]` -- a snapshot, so a reader cannot mutate the store by holding it. */
  entries(name) {
    const set = this._marks.get(name);
    return set ? Array.from(set.entries()) : [];
  }

  /** The names that currently carry marks. DERIVED -- there is no roster to keep in sync. */
  names() {
    const out = [];
    for (const [name, set] of this._marks) if (set.size) out.push(name);
    return out;
  }

  /** Write one mark. `SIGN.ABSENT` erases it -- that is how "unmark" is spelled. */
  set(name, nodeId, sign) {
    const next = normaliseSign(sign);
    const before = this.signOf(name, nodeId);
    if (before === next) return before;
    let set = this._marks.get(name);
    if (!set) { set = new Map(); this._marks.set(name, set); }
    if (next === SIGN.ABSENT) set.delete(nodeId);
    else set.set(nodeId, next);
    this._emit(name);
    return next;
  }

  /**
   * Click semantics, in one place rather than in each component: writing the sign a node
   * already carries clears it; writing a different one replaces it.
   */
  toggle(name, nodeId, sign) {
    const wanted = normaliseSign(sign);
    const current = this.signOf(name, nodeId);
    return this.set(name, nodeId, current === wanted ? SIGN.ABSENT : wanted);
  }

  /**
   * Write a whole marking at once, and emit ONCE. The explorer's only write.
   *
   * 🔴 WHY THIS EXISTS, MEASURED (2026-08-28). Restoring an N-node marking as `clear()` then
   * `set()` N times emits N+1 times when the name was not empty, and every subscriber sees the
   * INTERMEDIATE states -- measured sizes `[0, 1, 2, 3]` for a three-node restore. The zero is
   * the damaging one: a part reads it as 「아직 안 골랐습니다」 and re-walks, so stepping back
   * through history would redraw and refetch the screen once per node.
   *
   * 🔴 SAME GUARD AS `set()`, EXTENDED. `set()` already returns without emitting when the value
   * is unchanged; an atomic write keeps that promise for the whole set, which is what makes the
   * explorer's 「밖에서 바뀌었나」 check a VALUE comparison rather than a re-entrancy flag.
   *
   * @param {string} name
   * @param {Array<[string, number]>} entries  `[[nodeId, sign], ...]`, as `entries()` returns
   */
  replace(name, entries) {
    const next = new Map();
    for (const [nodeId, sign] of entries || []) {
      const wanted = normaliseSign(sign);
      if (wanted !== SIGN.ABSENT) next.set(nodeId, wanted);
    }
    const before = this._marks.get(name);
    if (before && before.size === next.size) {
      let same = true;
      for (const [nodeId, sign] of next) {
        if (before.get(nodeId) !== sign) { same = false; break; }
      }
      if (same) return;
    }
    if (!before && !next.size) return;
    this._marks.set(name, next);
    this._emit(name);
  }

  /** Drop every mark under one name. Other names are untouched -- see the harness §A. */
  clear(name) {
    const set = this._marks.get(name);
    if (!set || !set.size) return;
    set.clear();
    this._emit(name);
  }

  /**
   * Watch ONE name. Returns the unsubscribe -- a component that is destroyed must stop
   * hearing, or a shell that reseats panels leaks a listener per reseat.
   */
  subscribe(name, listener) {
    let set = this._listeners.get(name);
    if (!set) { set = new Set(); this._listeners.set(name, set); }
    set.add(listener);
    return () => { set.delete(listener); };
  }

  _emit(name) {
    const set = this._listeners.get(name);
    if (!set) return;
    // Snapshot: a listener that unsubscribes itself mid-notify must not skip its neighbour.
    for (const listener of Array.from(set)) listener(name, this);
  }
}
