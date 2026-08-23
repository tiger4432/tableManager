// ═══════════════════════════════════════════════════════════════════════════════
// MARKING INTERSECTION -- a LAYER ON TOP OF THE STORE, not a part and not inside one.
//
// 🔴 WHY IT LIVES HERE. The store already holds `name -> (id -> sign)` and already lets
//    anyone `subscribe(name)`. 「두 마킹이 동시에 가리킨 것」 is therefore an operation over
//    two names, which is the store's neighbourhood -- not the business of whichever panel
//    happens to want the answer. A part that computed it would have to learn the OTHER
//    part's marking name, and that is precisely the coupling this board is built to avoid.
//
// 🔴 NO NAME IS WRITTEN DOWN HERE. `sources` and `target` are arguments. The day the screen
//    has five markings, or wants 1∩3 as well as 1∩2, that is another call with other
//    strings and NOT another branch in this file. (`marking_store.js` states the same rule
//    for the same reason; a roster is a hardcoded list wearing a hat.)
//
// 🔴 THE SIGN IS PART OF THE QUESTION, AND THIS IS THE LEAD PM'S RULING. Two names holding
//    the same node with OPPOSITE signs did not agree about it -- one says 「여기서 났다」and
//    the other 「봤는데 안 났다」. Calling that an intersection would turn a CONTRADICTION
//    into a hit, and the contrast starts lying at the one place it matters. So:
//
//       every source agrees on the sign  ->  the node enters `target` WITH that sign
//       the sources disagree             ->  it does NOT enter, and it is COUNTABLE
//                                            (`conflicts()`), because a contradiction is a
//                                            finding, not a nothing
//
// 🔴 SOURCES ARE READ, NEVER WRITTEN. This layer writes exactly one name, and a screen that
//    aims `target` at one of its own sources is idempotent rather than looping: the store
//    only emits when a value actually changes.
//
// NO DOM, NO NETWORK. Scored under bare node.
// ═══════════════════════════════════════════════════════════════════════════════

import { SIGN } from './marking_store.js';

/**
 * Keep `target` equal to the intersection of `sources`, sign included.
 *
 * @param {import('./marking_store.js').MarkingStore} store
 * @param {{sources: string[], target: string}} spec  names, as DATA.
 * @returns {{refresh: Function, stop: Function, conflicts: Function, target: string}}
 *          `stop` unsubscribes -- a shell that reseats must be able to take it down.
 */
export function intersectMarkings(store, spec) {
  const sources = ((spec && spec.sources) || []).filter(Boolean);
  const target = spec && spec.target;
  if (!store || !target || sources.length < 2) {
    throw new Error('intersectMarkings needs a store, two or more sources and a target');
  }

  let conflicts = [];

  const refresh = () => {
    // The first name proposes; every other name has to agree, on the id AND on the sign.
    const [first, ...rest] = sources;
    const wanted = new Map();
    const disagreed = [];
    for (const [nodeId, sign] of store.entries(first)) {
      let agreed = true;
      let contradicted = false;
      for (const other of rest) {
        const otherSign = store.signOf(other, nodeId);
        if (otherSign === SIGN.ABSENT) { agreed = false; break; }
        if (otherSign !== sign) { agreed = false; contradicted = true; break; }
      }
      if (agreed) wanted.set(nodeId, sign);
      else if (contradicted) disagreed.push(nodeId);
    }
    conflicts = disagreed;

    // Written as a DIFF, so a node that was already in the intersection does not make the
    // store emit again -- a subscriber repainting on every recompute would flicker.
    for (const [nodeId, sign] of store.entries(target)) {
      if (wanted.get(nodeId) !== sign) store.set(target, nodeId, SIGN.ABSENT);
    }
    for (const [nodeId, sign] of wanted) store.set(target, nodeId, sign);
  };

  const unsubscribes = sources.map((name) => store.subscribe(name, refresh));
  refresh();

  return {
    target,
    refresh,
    /** Nodes two sources hold with OPPOSITE signs. A finding, not an absence. */
    conflicts: () => conflicts.slice(),
    stop: () => { for (const off of unsubscribes) off(); },
  };
}
