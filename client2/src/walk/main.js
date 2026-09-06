// 걷기 검색 — «휴대폰»에서 걷기 API 를 사람이 모는 자리.
//
// 🔴 이 파일이 «새로 만드는 것»은 페이지뿐입니다. 폼은 이미 있습니다.
//    `WalkBoxPanel` 이 타입 -> 키 -> 목적지 -> follow -> 실행 -> 결과 -> 이력을 전부 그리고,
//    `follow` 는 «선언의 술어»에서 고른 체크박스입니다 (타이핑이 아닙니다).
//    그래서 여기는 그 부품에 «자리와 재료»만 줍니다.
//
// ⚠️ R&D 보드와 «같은 부품»입니다. 이 페이지 때문에 그 파일을 고치면 그 화면이 같이 움직입니다.
//    그래서 배치는 이 페이지의 CSS 가 감싸고, 부품 파일은 안 건드립니다.
//
// 🔴 마킹은 «이 페이지의 것 하나»입니다. R&D 보드는 부품 여럿이 한 저장소를 나눠 쓰지만
//    여기는 부품이 하나라 나눌 상대가 없습니다 — 그래도 «만들어» 줍니다: 부품이 자기 이력을
//    마킹에 적기 때문입니다(`historyName()`). 안 주면 이력이 조용히 안 남습니다.

import { WalkBoxPanel } from '../rnd_board/walk_box_panel.js';
import { MarkingStore } from '../rnd_board/marking_store.js';
import { fetchDeclaration, createWalkBoxWalk } from '../rnd_board/api.js';

/**
 * @param {Document} doc
 * @param {HTMLElement} host  이 부품이 «소유»하는 div. 페이지가 만듭니다
 * @param {{apiBase?: string, fetchImpl?: Function}} [deps]
 */
export function boot(doc, host, deps) {
  const options = deps || {};
  const apiBase = options.apiBase || '';
  const fetchImpl = options.fetchImpl;

  // 🔴 선언은 «한 번만» 풉니다 — R&D 보드가 같은 이유로 그렇게 합니다. 다만 «거절은 가두지»
  //    않습니다: 선언 자체는 안 바뀌어도 「못 읽었다」는 다음 번에 읽힐 수 있고, 실패한 약속을
  //    캐시하면 이 화면은 영원히 「선언을 못 읽었습니다」가 됩니다.
  let once = null;
  const loadDeclaration = () => {
    if (!once) {
      once = fetchDeclaration({ apiBase, fetchImpl })
        .then((got) => { if (!got || !got.ok) once = null; return got; });
    }
    return once;
  };

  const panel = new WalkBoxPanel(host, {
    doc,
    markings: new MarkingStore(),
    // 이력이 사는 이름. 부품이 자기 이름을 짓지만, 읽는 쪽이 «이 페이지에 하나»뿐이라
    // 여기서 선언해 둡니다 — 부품이 옮겨 갈 때 이 줄만 바뀝니다.
    reads: 'marking:1',
    writes: 'marking:1',
    loadDeclaration,
    // 🔴 걷기 검색창은 «다른 모양의 walk» 을 받습니다. 이 부품의 collect 는 화면이 선언한
    //    질문 이름이 아니라 «서버의 노드 종류»이고, 씨앗도 마킹이 아니라 사람이 넣은 키에서
    //    만들어집니다. 같은 이름이 두 뜻이라 섞으면 오류 없이 «빈 답»이 나옵니다.
    walk: createWalkBoxWalk({ apiBase, fetchImpl }),
  });
  panel.mount();
  return panel;
}

// 🔴 부팅은 «이 파일 끝»에서만. bare node 로 이 모듈을 읽어도 DOM 을 안 건드려야
//    하니스가 붙을 수 있습니다 — R&D 보드 main.js 가 같은 규율을 씁니다.
if (typeof document !== 'undefined') {
  const host = document.getElementById('wk-host');
  if (host) {
    import('../config.js').then(({ API_BASE }) => {
      boot(document, host, { apiBase: API_BASE });
    });
  }
}
