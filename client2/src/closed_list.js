// CLOSED LIST — 닫힌 목록 하나를 «어느 컨트롤»로 그릴지 정하는 자리.
//
// 🔴 이 파일이 생긴 이유 하나: **「고를 게 없는 고르개」와 「고장난 고르개」가 화면에서 똑같이
//    보인다.** 멤버가 하나뿐인 목록을 드롭다운으로 그리면 운영자는 그것이 「원래 하나」인지
//    「목록을 못 받아서 하나」인지 알 수 없고, 둘은 «정반대»로 움직여야 하는 자리다.
//
// 🔴 그리고 이건 낱개 수정이 아니라 «규칙»이라, 목록이 «어디서 오든» 이 부품이 판단한다.
//    오늘 이것을 부르는 곳이 둘이다 — 계획 행의 `candidates`(서버가 이 행에 실어 준 것)와
//    스켈레톤 잎의 `schema[node.list]`(서버가 `closed_lists()` 로 «공표»한 것).
//    한쪽만 고치면 다른 쪽에 같은 병이 남고, 그때 남은 쪽은 「이미 고쳤다」로 읽힌다.
//
// ⚠️ 상태가 «넷»이지 둘이 아니다. 목록이 «아직 안 온» 것과 「멤버 0」은 안 섞는다 —
//    앞은 「모름」이고 뒤는 「없음」이다. 이 저장소가 여러 번 닫은 부류 그대로다.

/** 목록이 아직 안 왔다. 「멤버 0」이 아니다. */
export const LIST_UNREAD = '목록 · 모름';
/** 목록은 왔는데 멤버가 없다. 「모름」이 아니다. */
export const NO_CHOICE = '선택지 없음';

/**
 * 이 칸을 값으로 그릴지, 고르개로 그릴지, 아니면 둘 다 아닌지.
 *
 * 🔴 판별식은 «하나»다: **이 컨트롤이 지금 값 말고 «다른 것»을 고를 수 있나.**
 *    없으면 컨트롤이 아니라 값이다 — 아무것도 바꿀 수 없는 컨트롤은 갚지 못할 주의를 끈다.
 *
 * 🔴 그리고 「멤버 하나 = 항상 값」이 아니다. 문서가 그 하나를 «들고 있을 때»만 값이다.
 *    비어 있으면 그 하나를 «써 넣는 유일한 길»이 이 고르개라서, 값으로 바꾸면 그 칸이
 *    영영 못 채워진다. 그 둘은 화면에서도 다르다 — 채워진 1멤버 고르개만 「고장난 것」처럼
 *    보이고, 빈 칸의 고르개는 항목이 둘(빈칸 · 그 하나)이라 그렇게 안 보인다.
 *
 * ⚠️ 현재 값은 «언제나» 항목에 남는다. 목록에 없는 값을 조용히 첫 항목으로 바꾸면 그리는
 *    것만으로 남의 파일을 고쳐 쓰는 것이 된다.
 *
 * @param {string[]|null|undefined} options 서버가 준 닫힌 목록의 멤버
 * @param {string} current 문서가 «지금» 들고 있는 값 (없으면 '')
 * @param {{loaded?: boolean, name?: string}} [opts] `loaded` 는 목록의 «도착» 여부
 * @returns {{control: 'unread'|'none'|'value'|'picker', value: string,
 *            options: string[], reason: string}}
 */
export function closedListChoice(options, current, opts = {}) {
  const value = typeof current === 'string' || typeof current === 'number' ? String(current) : '';
  const name = opts.name ? String(opts.name) : '';
  if (opts.loaded === false) {
    return { control: 'unread', value, options: [], reason: LIST_UNREAD };
  }
  const members = Array.isArray(options) ? options.filter((i) => typeof i === 'string') : [];
  if (!members.length) {
    return { control: 'none', value, options: [],
             reason: name ? `${NO_CHOICE} · ${name}` : NO_CHOICE };
  }
  const offered = members.includes(value) ? members : [value, ...members];
  if (offered.length === 1) {
    return { control: 'value', value, options: offered, reason: '' };
  }
  return { control: 'picker', value, options: offered, reason: '' };
}

/**
 * 위 판정을 «그리는» 자리. 부르는 쪽이 다른 것은 `spec` 셋뿐이다.
 *
 * @param {object} decision `closedListChoice` 의 답
 * @param {(tag: string, cls?: string, text?: string) => any} h 원소 만들기
 * @param {{action: string, path: string, label?: string}} spec 이 칸의 쓰기 주소
 */
export function renderClosedList(decision, h, spec) {
  const label = spec.label === undefined ? spec.path : spec.label;
  if (decision.control === 'picker') {
    const select = h('select', 'oe-field-select');
    select.dataset.action = spec.action;
    select.dataset.value = spec.path;
    select.setAttribute('aria-label', label);
    for (const item of decision.options) {
      const option = h('option', '', item);
      option.value = item;
      if (item === decision.value) option.selected = true;
      select.append(option);
    }
    return select;
  }
  if (decision.control === 'value') {
    const only = h('span', 'oe-field-onechoice', decision.value);
    only.setAttribute('aria-label', label);
    return only;
  }
  // 🔴 값은 «사유와 함께» 남는다. 목록이 없다고 문서가 든 것까지 사라지면, 화면이 그 값을
  //    지운 것처럼 읽힌다 — 지운 적이 없는데.
  const box = h('span', decision.control === 'unread' ? 'oe-field-unread' : 'oe-field-nochoice');
  if (decision.value) box.append(h('span', 'oe-value', decision.value));
  box.append(h('small', '', decision.reason));
  box.setAttribute('aria-label', label);
  return box;
}
