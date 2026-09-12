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
import { sectionsByType, sectionHeading, tableColumns, cellSource, pluralAttributes }
  from './derive.js';

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
 */
export function qualifiersByNode(edges) {
  const byNode = new Map();
  for (const edge of edges || []) {
    const quals = edge && edge.qualifiers;
    if (!quals || typeof quals !== 'object') continue;
    for (const id of [edge.target, edge.source]) {
      if (!id || !byNode.has(id)) byNode.set(id, byNode.get(id) || {});
    }
    const at = byNode.get(edge.target) || {};
    Object.assign(at, quals);
    byNode.set(edge.target, at);
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
 * @param {number} [cap]                            행 상한
 * @returns {{sections: Array, shown: number, hidden: number}}
 */
export function walkTableView(result, entities, cap = ROW_CAP) {
  const nodes = (result && result.nodes) || [];
  const shown = nodes.slice(0, cap);
  const byNode = qualifiersByNode((result && result.edges) || []);
  const sections = [];
  // C-89. 「어느 이름이 여럿인가」는 봉투가 말합니다. 노드마다 다시 묻지 않습니다 — 한 답이고,
  // 표 중간에서 답이 바뀔 수 있으면 그 자체가 결함입니다.
  const plural = pluralAttributes(result);
  for (const [type, rows] of sectionsByType(shown)) {
    const columns = tableColumns(entities, type, qualifierNamesOf(rows, byNode));
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
            cellSource(column, node, byNode.get(node.id) || {}, plural.get(node.type)));
          return { text, kind: column.kind, numeric: isNumericText(text) };
        }),
      })),
    });
  }
  // 🔴 「안 그린 수」는 «답»입니다. 0 이면 그 줄이 없어야 하고, 0 을 그리면 운영자가
  //    「상한에 걸렸다」로 읽습니다.
  return { sections, shown: shown.length, hidden: Math.max(0, nodes.length - shown.length) };
}
