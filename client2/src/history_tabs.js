import { elements } from './dom.js';
import { state } from './state.js';

// 사이드바 탭 «한 줄»에서 활성 표시를 정하는 좌석. 이것 하나뿐이다.
//
// 🔴 왜 좌석인가 (2026-09-22 판정, main.js 의 주석이 사고를 적어 뒀다): 갈아타기마다
//    «형제를 손으로 나열»하고 있었다. 넷째 탭이 줄에는 들어갔는데 그 목록들엔 안 들어가서
//    탭 둘이 «동시에» 켜졌다. 숨겨져 있는 동안은 무해했고, 그래서 안 들켰다.
//
// 🔵 목록을 «여기에 적지 않는다» — 버튼의 «부모 줄»에서 가져온다. 그래서 탭을 HTML 에
//    하나 더 넣으면 목록에 «자동으로» 든다. 손으로 적은 목록은 다음 탭에서 또 낡는다.
//    (같은 저장소의 선례: enrichment_reference_view.js 의 탭 띠도 children 으로 접는다)

/** 이 버튼을 켜고, 같은 줄의 나머지를 «전부» 끈다. 없으면 아무것도 안 한다. */
function activateHistoryTab(button) {
  if (!button) return;
  const bar = button.parentNode;
  const siblings = bar && bar.children ? bar.children : [button];
  for (const sibling of siblings) {
    if (sibling && sibling.classList) sibling.classList.toggle('active', sibling === button);
  }
}

// 🔴 탭마다 «켤 버튼 · 보일 창» 한 줄 (총괄 10-21, 소유자 「탭은 글로벌인데 가끔 대기열 따로 있네」): 탭 표시 ·
//    창 보이기 · state.activeHistoryTab 이 셋으로 따로 불려서, 표 바꾸기가 탭만 Global 로 켜고 대기열 창을 남겼다.
//    셋은 pickHistoryTab 하나로만 바뀐다. 창이 하나 더 생기면 고칠 자리는 이 표뿐이다.
const TABS = {
  global: [() => elements.tabGlobalBtn, () => elements.timelineContainer],
  cell: [() => elements.tabCellBtn, () => elements.timelineContainer],
  row: [() => elements.tabRowBtn, () => elements.timelineContainer],
  reference: [() => elements.tabReferenceBtn, () => elements.referenceView],
  queue: [() => elements.tabQueueBtn, () => elements.queueView],
};

/** 이 탭을 고른다 — 그 버튼을 켜고, 그 창만 보이고, state 에 적는다. @param {keyof TABS} name */
export function pickHistoryTab(name) {
  const [button, pane] = TABS[name];
  state.activeHistoryTab = name;
  activateHistoryTab(button());
  const shown = pane();
  for (const [, get] of Object.values(TABS)) {
    const el = get();
    if (el && el.style) el.style.display = (el === shown) ? '' : 'none';
  }
}
