// An element of a visual is a node or a hub (owner 10-12 「각 요소가 다 노드거나 노드 허브」, reference §7): a cross table
// cell or a legend value is the hub of the nodes it holds, marked whole, one line in the basket. A hub's id is its
// DESCRIPTION - the row type and the values it takes - so two parts that describe the same hub mark the same one.
// Until the server takes hubs as seeds (WALK_HUB_ANSWER_SHAPE), a walk from a marking opens them into their members here,
// in one place: `HubBook.open`, handed to the marking store's `seedsOf`.

const PREFIX = 'hub:';

/** A hub's id: its row type and its conditions ([[slot words, value], ...]), spelled once. */
export const hubId = (row, where) => `${PREFIX}${JSON.stringify([row, where])}`;
export const isHubId = (id) => typeof id === 'string' && id.startsWith(PREFIX);
/** A hub's description back from its id: {row, where}. */
export function hubOf(id) {
  if (!isHubId(id)) return null;
  const [row, where] = JSON.parse(id.slice(PREFIX.length));
  return { row, where };
}
/** A hub in words - «wafer · recipe = R-07 · equipment = EQ-02». */
export const hubWords = (id) => { const h = hubOf(id); return h ? [h.row, ...h.where.map(([k, v]) => `${k} = ${v}`)].join(' · ') : ''; };

/**
 * What a press on a mark stands for - THE one place that says (owner 10-14 «누르면 그 아래 행이 마킹»): one row - that
 * row's node; several - null, the hub of its rows. A value read off another node is no node of its own any more (the
 * 10-14 exception retired: the marking spreads along the page's relations, and a part whose rows are that type narrows).
 * @returns {string[]|null}
 */
export function nodesOfPress(ids) {
  return ids && ids.length === 1 ? [ids[0]] : null;
}

/** The page's hubs: each id's members as the part that drew it last counted them. Made by the page, handed to parts. */
export class HubBook {
  constructor() { this.members = new Map(); }
  put(id, members) { this.members.set(id, [...members]); return id; }
  membersOf(id) { return this.members.get(id) || []; }
  /** THE one place a marking's entry opens into nodes: a hub its members, a node itself. */
  open(id) { return isHubId(id) ? this.membersOf(id) : [id]; }
}

/** Whether a node is held by a marking - as itself or as a member of a hub it holds. */
export function holds(entries, book, nodeId) {
  return (entries || []).some(([id]) => book.open(id).includes(nodeId));
}
