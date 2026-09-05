// UNIQUENESS — 「이 컬럼들이 «데이터에서» 행을 가리키나」에 대한 서버의 답을 «상태»로 읽습니다.
//
// 🔴 이 파일이 재계산하지 않습니다. 서버(`column_stats.combination_uniqueness` ·
//    `ordering_candidates`)가 «이미» 세어서 냅니다 — 여기 있는 것은 그 수를 «어느 상태로
//    그릴지»뿐이고, 화면이 순서를 다시 정하는 순간 두 번째 저자가 생깁니다.
//
// 🔴 상태가 «다섯»입니다. 서버 지시는 넷이었는데, 서버가 내는 «수»가 하나를 더 가릅니다:
//
//    아직 안 옴     묻지 않았거나 오는 중          <- 「유니크 아님」이 «아닙니다»
//    유니크         measurable && unique
//    유니크 아님     measurable && !unique && 행이 «있음»   -> 겹친 행 수를 같이 답니다
//    행 0          measurable && 행이 «없음»       <- 아래가 이 갈래의 이유입니다
//    판정 불가       measurable === false           -> 서버가 «사유»를 같이 냅니다
//
// ⚠️ 「행 0」을 왜 가르나: 서버의 `unique` 는 `rows == combinations and rows > 0` 입니다.
//    즉 «빈 표»는 `unique: false` 로 나오고 `duplicate_rows` 는 0 입니다. 그걸 그대로
//    「유니크 아님」으로 그리면 「겹치는 행 0 인데 유니크 아님」이라는 «말이 안 되는 칸»이
//    운영자 앞에 서고, 고칠 것이 없는 자리에서 고칠 것을 찾게 됩니다.
//    그 둘은 운영자가 «정반대»로 움직이는 자리입니다 — 앞은 컬럼을 바꾸는 일이고,
//    뒤는 «적재를 먼저 하는» 일입니다.

/** 묻지 않았거나 오는 중. 「없음」이 아닙니다. */
export const UNIQUENESS_UNREAD = '유니크 · 모름';

/**
 * 서버가 잰 한 조합의 판정을 «상태»로.
 *
 * @param {object|null|undefined} measured `combination_uniqueness` 또는 `declared_keys` 의 한 항목
 * @param {{read?: boolean}} [opts] `read:false` 는 「아직 안 물음」 — 응답의 «부재»와 다릅니다
 * @returns {{state: 'unread'|'unique'|'duplicated'|'empty'|'unmeasurable',
 *            columns: string[], text: string, detail: string}}
 */
export function uniquenessVerdict(measured, opts = {}) {
  const columns = measured && Array.isArray(measured.columns)
    ? measured.columns.filter((c) => typeof c === 'string') : [];
  if (opts.read === false || !measured) {
    return { state: 'unread', columns, text: UNIQUENESS_UNREAD, detail: '' };
  }
  if (measured.measurable === false) {
    // 서버의 문장을 그대로 나릅니다 — 여기서 다시 쓰면 사유가 둘이 됩니다.
    return { state: 'unmeasurable', columns, text: '판정 불가',
             detail: typeof measured.reason === 'string' ? measured.reason : '' };
  }
  const rows = Number.isFinite(measured.total_rows) ? measured.total_rows : null;
  if (rows === 0) {
    return { state: 'empty', columns, text: '행 0 · 판정 불가', detail: '' };
  }
  if (measured.unique === true) {
    return { state: 'unique', columns, text: '유니크',
             detail: rows === null ? '' : `행 ${rows.toLocaleString()}` };
  }
  if (measured.unique === false) {
    // 🔴 「몇 행이 겹치나」와 「겹침에 걸린 행이 몇이나」는 다른 수이고, 서버가 둘 다 냅니다.
    //    앞은 계약이 거절하는 수이고, 뒤는 「반올림 오차인가 표 전체인가」를 말합니다.
    const dup = Number.isFinite(measured.duplicate_rows) ? measured.duplicate_rows : null;
    const inDup = Number.isFinite(measured.rows_in_duplicated_groups)
      ? measured.rows_in_duplicated_groups : null;
    const parts = [];
    if (dup !== null) parts.push(`겹침 ${dup.toLocaleString()}`);
    if (inDup !== null) parts.push(`걸린 행 ${inDup.toLocaleString()}`);
    if (Number.isFinite(measured.null_bearing_rows) && measured.null_bearing_rows > 0) {
      // NULL 은 충돌과 «다른 결함»이라 고치는 방법도 다릅니다. 합치지 않습니다.
      parts.push(`NULL ${measured.null_bearing_rows.toLocaleString()}`);
    }
    return { state: 'duplicated', columns, text: '유니크 아님', detail: parts.join(' · ') };
  }
  // 서버가 그 칸을 안 실었습니다. 「아니다」로 읽지 않습니다.
  return { state: 'unread', columns, text: UNIQUENESS_UNREAD, detail: '' };
}

/**
 * 선언된 키들 전부의 판정과, 서버가 «고른» 추천.
 *
 * 🔴 `recommended: null` 은 «답»입니다 — 「선언만으로는 이 관계를 정렬할 수 없다」이고,
 *    그때 고르는 것은 사람의 몫입니다. 없는 것으로 그리면 그 사실이 사라집니다.
 * ⛔ 추천을 여기서 «다시 고르지» 않습니다. 서버가 「측정을 통과한 것 중 가장 짧은 것」으로
 *    이미 골랐고, 화면이 같은 규칙을 두 번째로 쓰면 두 규칙이 조용히 갈립니다.
 *
 * @param {object|null|undefined} ordering `/columns` 응답의 `ordering`
 * @param {{read?: boolean}} [opts]
 */
export function orderingVerdicts(ordering, opts = {}) {
  if (opts.read === false || !ordering) {
    return { read: false, keys: [], recommended: null, text: UNIQUENESS_UNREAD };
  }
  const declared = Array.isArray(ordering.declared_keys) ? ordering.declared_keys : [];
  const keys = declared.map((item) => uniquenessVerdict(item));
  const recommended = Array.isArray(ordering.recommended) ? ordering.recommended : null;
  return {
    read: true,
    keys,
    recommended,
    text: recommended ? recommended.join(' · ')
      : (declared.length ? '선언만으로는 못 정함' : '선언된 유니크 키 없음'),
  };
}
