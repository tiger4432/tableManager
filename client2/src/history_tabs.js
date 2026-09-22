// 사이드바 탭 «한 줄»에서 활성 표시를 정하는 좌석. 이것 하나뿐이다.
//
// 🔴 왜 좌석인가 (2026-09-22 판정, main.js 의 주석이 사고를 적어 뒀다): 갈아타기마다
//    «형제를 손으로 나열»하고 있었다. 넷째 탭이 줄에는 들어갔는데 그 목록들엔 안 들어가서
//    탭 둘이 «동시에» 켜졌다. 숨겨져 있는 동안은 무해했고, 그래서 안 들켰다.
//
// 🔵 목록을 «여기에 적지 않는다» — 버튼의 «부모 줄»에서 가져온다. 그래서 탭을 HTML 에
//    하나 더 넣으면 목록에 «자동으로» 든다. 손으로 적은 목록은 다음 탭에서 또 낡는다.
//    (같은 저장소의 선례: enrichment_reference_view.js 의 탭 띠도 children 으로 접는다)

/**
 * 이 버튼을 켜고, 같은 줄의 나머지를 «전부» 끈다.
 * @param {object|null|undefined} button 탭 버튼 (없으면 아무것도 안 한다)
 */
export function activateHistoryTab(button) {
  if (!button) return;
  const bar = button.parentNode;
  const siblings = bar && bar.children ? bar.children : [button];
  for (const sibling of siblings) {
    if (sibling && sibling.classList) sibling.classList.toggle('active', sibling === button);
  }
}
