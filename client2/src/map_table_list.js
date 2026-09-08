// ═══════════════════════════════════════════════════════════════════════════════
// C-44 ② — 「어느 표가 맵 표인가」. 한 응답에서.
//
// 🔴 IT USED TO COST ONE REQUEST PER TABLE. The picker walked `/tables` and asked each one for
//    its whole schema, sequentially, to read a single field — measured on this box: 45 requests
//    for a list of ten, with 34 answers thrown away, and the shape's property is that the
//    request count EQUALS the table count. `/tables` now carries `map_key_columns` (S-72), so
//    the loop is gone rather than parallelised: parallelising keeps the shape and hides it.
//
// 🔴 THE ORDER COMES FROM `tables`, NOT FROM THE MAP'S KEYS. The old loop walked `data.tables`
//    and kept the ones that qualified, so that is the order the operator has been reading. On
//    this box the two orders happen to agree, which means THIS BOX CANNOT TELL THEM APART —
//    the harness feeds a body where they differ, because a fixture both rules answer the same
//    way decides nothing.
//
// 🔴 AND THE KEY'S ABSENCE IS ITS OWN STATE. An older server sends no `map_key_columns` at
//    all, and that is 「서버가 말 안 함」, not 「맵 표가 없다」. Rendering them alike tells an
//    operator their tables are unusable when the truth is that nobody asked this server.
// ═══════════════════════════════════════════════════════════════════════════════

/** 서버가 그 칸을 «안 보냄». 낱말 하나 — 문장이 아니고, 「없음」과 다릅니다. */
export const NOT_SERVED = '미제공';

/**
 * @param {object} body `GET /tables` 응답, 그대로
 * @returns {{tables: string[], reason: string}} 못 물어본 경우에만 `reason` 이 붙습니다
 */
export function mapTablesFrom(body) {
  const all = body && Array.isArray(body.tables) ? body.tables : [];
  const declared = body && body.map_key_columns;
  // ⚠️ 「키 없음」 «만» 미제공입니다. 빈 객체는 «서버가 답했고 하나도 없다»이고, 그건 참인 답입니다.
  if (!declared || typeof declared !== 'object' || Array.isArray(declared)) {
    return { tables: [], reason: NOT_SERVED };
  }
  const keyed = (name) => {
    const cols = declared[name];
    return Array.isArray(cols) && cols.length > 0;
  };
  return { tables: all.filter(keyed), reason: '' };
}
