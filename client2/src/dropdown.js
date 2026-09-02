// ═══════════════════════════════════════════════════════════════════════════════
// DROPDOWN — 「버튼 아래로 열리고, 바깥을 누르면 닫힌다」의 «한 벌»
//
// 🔴 이 파일이 생긴 이유는 «둘째»가 나왔기 때문입니다 (상설: 근원 템플릿 요소 개발 후
//    데이터 갈아끼우기). 첫째는 Re-translate 드롭다운, 둘째는 필터 칩 펼침입니다.
//    비슷한 것을 하나 더 그리는 대신 «닫는 방법»을 한 곳에 둡니다.
//
// 🔴 떼는 것까지가 이 함수입니다. 안 떼면 닫힌 드롭다운이 «계속 클릭을 먹고», 그다음
//    열려 있는 것이 남의 바깥 클릭에 닫힙니다. 그 고장은 오류를 내지 않습니다.
//
// NO DOM GLOBALS, NO NETWORK. 맨 node 문서 스텁으로 채점됩니다.
// ═══════════════════════════════════════════════════════════════════════════════

/** 문서에 바깥 클릭·Esc 를 걸고, «떼는 함수»를 돌려줍니다.
 *
 * @param doc   문서 (또는 addEventListener 를 가진 스텁)
 * @param host  「안쪽」의 경계. 이 노드 «밑»을 누른 것은 바깥이 아닙니다
 * @param close 닫는 함수
 */
export function watchForDismiss(doc, host, close) {
  if (!doc || !doc.addEventListener) return null;
  const onKey = (event) => { if (event && event.key === 'Escape') close(); };
  const onDown = (event) => {
    // 자기 div 안을 누른 것은 «바깥»이 아닙니다 -- 줄을 누르는 것도 클릭이라,
    // 이 걸음이 없으면 열자마자 자기가 자기를 닫습니다.
    let node = event && event.target;
    while (node) { if (node === host) return; node = node.parentNode; }
    close();
  };
  doc.addEventListener('keydown', onKey);
  doc.addEventListener('mousedown', onDown);
  return () => {
    if (doc.removeEventListener) {
      doc.removeEventListener('keydown', onKey);
      doc.removeEventListener('mousedown', onDown);
    }
  };
}
