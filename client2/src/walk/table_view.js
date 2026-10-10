// ═══════════════════════════════════════════════════════════════════════════════
// 걷기 결과 표 — «DOM 이 한 조각도 없는» 절반.
//
// 🔴 왜 자기 모듈인가 (C-72, 2026-09-10). 이 결정들은 `main.js` 의 `boot()` 안 클로저였고,
//    그래서 「이 화면이 그 함수를 부르나」를 «거동으로» 잴 자리가 없었습니다. C-70 이 구획과
//    컬럼을 `derive.js` 로 올렸지만, 그것을 «부르는 쪽»이 여전히 페이지 안이라 누가 사본을
//    다시 넣어도 빨개지는 것이 없었습니다. 상설: 「재려는 로직을 import 되는 모듈로 뺀다」.
//
// 🔴 여기서 «정하지» 않습니다. 구획은 `sectionsByType`, 머리는 `sectionHeading`, 컬럼은
//    `tableColumns`, 셀 값은 `cellSource` — 전부 `derive.js` 의 것이고 걷기 검색창이 부르는
//    바로 그 함수들입니다. 이 파일이 더하는 것은 「그 넷을 «어떤 순서로» 엮나」뿐입니다.
//
// 🔴 텍스트도 여기서 만듭니다. 빈 칸은 «빈 칸»입니다 — 「—」나 0 으로 채우면 「없다」와
//    「0 이다」가 같은 글자가 됩니다. 그 판정이 렌더러에 있으면 node 가 채점할 수 없습니다.
// ═══════════════════════════════════════════════════════════════════════════════
import { confirmedPredicates, sectionsByType, sectionHeading, tableColumns, cellSource, pluralAttributes,
  edgeQualifiers } from './derive.js';
import { typeGraph } from '../rnd_board/api.js';

/** The edges one step from a type (lead 53050a4ec): each declared predicate touching it and the type at its other
 *  end, read off the type graph the route list reads - a predicate within the type (bonded_to die -> die) included,
 *  which the route list keeps as a loop chip. The walk takes any first step. Nothing is guessed from the data. */
export function nextRoutes(declaration, type) {
  const out = [];
  for (const edge of typeGraph(declaration).edges) {
    const to = edge.from === type ? edge.to : edge.to === type ? edge.from : null;
    if (to !== null && !out.some((r) => r.predicate === edge.predicate && r.to === to)) {
      out.push({ predicate: edge.predicate, to });
    }
  }
  return out;
}

/** 한 번에 그리는 행 상한. 넘은 것은 «수»로 말합니다 — 조용히 자르지 않습니다. */
export const ROW_CAP = 200;

/** 값 -> 글자. `null`·`undefined` 만 빈 칸이고 `0` 과 `false` 는 값입니다. */
export function valueText(value) {
  return value === null || value === undefined ? '' : String(value);
}

/** 오른쪽 정렬할 수인가. 빈 칸은 수가 아닙니다. */
export function isNumericText(text) {
  return text !== '' && Number.isFinite(Number(text));
}

/**
 * 엣지가 들고 온 수식어를 «닿은» 노드에 답니다.
 *
 * 🔴 `target` 쪽에«만» 답니다. 씨앗 쪽에도 달면 씨앗 하나가 자기에게 닿은 «모든» 엣지의
 *    수식어를 다 이고 다니게 되고, 그러면 씨앗 행이 자기 것이 아닌 값을 보여 줍니다.
 * ⚠️ 양쪽 id 에 «자리»는 만듭니다 — 「닿았는데 수식어가 없다」와 「안 닿았다」는 다릅니다.
 * 🔴 한 노드에 닿은 변이 여럿이면 «덮어쓰지 않습니다»(총괄 10-09: 마지막 변의 값만 남아 틀린 수를 보였다).
 *    그 이름이 변 하나에서 오면 그 값, 여럿에서 오면 «N edges · 값 (누구의 값) · …» 한 줄입니다.
 *    누구 = 변의 출발 노드의 `label`(응답의 이름).
 */
export function qualifiersByNode(edges, nodes = []) {
  const labelOf = new Map((nodes || []).map((n) => [n.id, n.label || n.id]));
  const got = new Map();
  for (const edge of edges || []) {
    const quals = edgeQualifiers(edge);
    if (!quals) continue;
    for (const id of [edge.target, edge.source]) {
      if (id && !got.has(id)) got.set(id, new Map());
    }
    const at = got.get(edge.target);
    if (!at) continue;
    for (const [name, value] of Object.entries(quals)) {
      if (!at.has(name)) at.set(name, []);
      at.get(name).push({ value, from: labelOf.get(edge.source) || edge.source });
    }
  }
  const byNode = new Map();
  for (const [id, names] of got) {
    const said = {};
    for (const [name, list] of names) {
      said[name] = list.length === 1 ? list[0].value
        : `${list.length} edges · ${list.map((v) => `${valueText(v.value)} (${v.from})`).join(' · ')}`;
    }
    byNode.set(id, said);
  }
  return byNode;
}

/**
 * 이 구획에 «실제로 온» 수식어 이름들 — 처음 나온 순서로.
 *
 * 🔴 선언이 아니라 «응답»이 정합니다. 수식어는 술어마다 다르고, 안 온 이름의 컬럼을 세우면
 *    그 열은 언제나 비어 있어 「이 걷기가 그것을 못 가져왔다」로 읽힙니다.
 */
export function qualifierNamesOf(nodes, byNode) {
  const names = [];
  for (const node of nodes || []) {
    for (const key of Object.keys((byNode && byNode.get(node.id)) || {})) {
      if (!names.includes(key)) names.push(key);
    }
  }
  return names;
}

/**
 * 걷기 결과 하나 -> 표 «전부». 구획마다 머리·컬럼·행, 그리고 못 그린 수.
 *
 * @param {{nodes?: Array, edges?: Array}} result  walk 응답
 * @param {Array} entities                          선언의 엔티티 목록
 * @param {Array} [predicates]                      선언의 술어 목록 (확인 술어를 읽는 자리, C-98)
 * @param {number} [cap]                            행 상한
 * @param {{positive?: string[], negative?: string[]}} [starts]  the walk's signed starts: with a − start the table is
 *        two zones, each the nodes that sign reached (lead 55f854fc5 ②); without, the one table it always was
 * @returns {{sections: Array, shown: number, hidden: number, zones: Array|null, unsplit: boolean}}
 */
export function walkTableView(result, entities, predicates = [], cap = ROW_CAP, starts = null) {
  const nodes = (result && result.nodes) || [];
  const byNode = qualifiersByNode((result && result.edges) || [], nodes);
  // C-89. 「어느 이름이 여럿인가」는 봉투가 말합니다. 노드마다 다시 묻지 않습니다 — 한 답이고,
  // 표 중간에서 답이 바뀔 수 있으면 그 자체가 결함입니다.
  const plural = pluralAttributes(result);
  // C-98. 「무엇이 안 보이는 것이 무슨 뜻인가」의 모집단은 «선언»이라, 한 번 읽고 모든 구획이
  // 같은 열을 씁니다 — 구획마다 다시 물으면 표 중간에서 열이 바뀔 수 있습니다.
  const confirmers = confirmedPredicates(predicates);
  /** One table of `members`: its sections by type, at most `cap` rows, its cells read off `read`. */
  const tableOf = (members, read = byNode) => {
    const shown = members.slice(0, cap);
    const sections = [];
    for (const [type, rows] of sectionsByType(shown)) {
      const columns = tableColumns(
        entities, type, qualifierNamesOf(rows, read), undefined, confirmers);
      sections.push({
        type,
        heading: sectionHeading(type, rows.length),
        columns,
        rows: rows.map((node) => ({
          id: node.id,
          // 🔴 머리와 셀이 «같은 배열»을 돕니다. 따로 돌면 그날부터 순서가 갈릴 수 있고,
          //    갈라져도 오류가 안 납니다 — 값이 옆 칸에 들어갈 뿐입니다.
          cells: columns.map((column) => {
            const text = valueText(
              cellSource(column, node, read.get(node.id) || {}, plural.get(node.type)));
            return { text, kind: column.kind, numeric: isNumericText(text) };
          }),
        })),
      });
    }
    // 🔴 「안 그린 수」는 «답»입니다. 0 이면 그 줄이 없어야 하고, 0 을 그리면 운영자가
    //    「상한에 걸렸다」로 읽습니다.
    return { sections, shown: shown.length, hidden: Math.max(0, members.length - shown.length) };
  };
  const negative = (starts && starts.negative) || [];
  const reach = negative.length ? reachBySign(result) : null;
  if (!reach) return { ...tableOf(nodes), zones: null, unsplit: negative.length > 0 };
  // A zone is its sign's starts and every node they reached; a node reached from both stands in both.
  const zones = [['+', (starts && starts.positive) || []], ['−', negative]].map(([sign, ids]) => {
    const own = new Set(ids);
    const members = nodes.filter((n) => own.has(n.id) || (reach.get(n.id) || {})[sign] > 0);
    // Its cells read the edges walked inside it - both ends in the zone - so the other sign's edge into a node both
    // reached says its value in the other zone, not here.
    const inside = new Set(members.map((n) => n.id));
    const read = qualifiersByNode(((result && result.edges) || []).filter((e) => inside.has(e.source) && inside.has(e.target)), members);
    return { sign, starts: [...ids], ...tableOf(members, read) };
  });
  return { sections: [], shown: 0, hidden: 0, zones, unsplit: false };
}

/**
 * Per node, how many starts of each sign reached it - the answer's propagation.ranked[].reach, [from +, from −]
 * (lead 55f854fc5 ②: the one seat that reads it). The starts themselves are not ranked. null when the answer ranks
 * nothing.
 */
export function reachBySign(result) {
  const ranked = result && result.propagation && result.propagation.ranked;
  if (!Array.isArray(ranked)) return null;
  return new Map(ranked.map((row) => [row.id, { '+': Number((row.reach || [])[0]) || 0, '−': Number((row.reach || [])[1]) || 0 }]));
}
