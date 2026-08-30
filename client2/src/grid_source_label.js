// ═══════════════════════════════════════════════════════════════════════════════
// GRID SOURCE LABEL — 「이 표가 원장 소스인가」를 그리드 머리에 한 줄.
//
// 🔴 부재를 «셋»으로 말합니다 (지시서 §2, 상설 「없어서·아님·못 읽어서는 다른 사실이다」).
//       소스다      선언의 `sources` 에 이 relation 이 «있다»
//       아니다      선언을 읽었고, 그 목록에 «없다»          <- 이것도 말해야 합니다
//       못 읽었다   선언 라우트가 거절했다                    <- 위 둘과 «구별»되어야 합니다
//    셋을 「라벨 없음」 하나로 접으면 「소스가 아님」과 「못 읽음」이 같아지고, 그건 이
//    저장소가 반복해서 잡아 온 병입니다. 그래서 이 파일에 «빈 문자열»로 끝나는 갈래가 없습니다.
//
// 🔴 넷째가 하나 더 있고, 그건 «주장이 아닙니다»: 표를 아직 안 골랐을 때.
//    그때는 라벨이 아무 말도 «안 합니다» -- 주어가 없는데 술어를 그리면 그게 지어내는 것입니다.
//
// 🔴 「만드는 것」 칸은 `emits` 를 «그대로» 씁니다. 총괄 교차 검사 2026-08-31:
//    emits 에 나오는데 선언에 없는 술어가 «0» 이므로 걸러낼 것이 없습니다. 거르면 그 순간
//    화면이 선언보다 «덜» 말하게 되고, 새 술어가 오는 날 조용히 사라집니다.
//
// 🔴 조립식 (UI 상설): 생성자가 자기 host 와 deps 를 받습니다. 모듈 수준 상태 «없음».
//    라우트도 apiBase 도 모릅니다 -- `loadDeclaration` «한 함수»를 주입받습니다.
//    그래서 같은 페이지에 둘을 서로 다른 표로 앉혀도 간섭하지 않습니다.
//
// NO DOM GLOBALS, NO NETWORK. 맨 node 의 문서 스텁으로 채점됩니다.
// ═══════════════════════════════════════════════════════════════════════════════

/** 라우트가 준 것에서 이 부품이 읽는 것 «전부». 없는 칸은 지어내지 않습니다. */
function rowFor(sources, relation) {
  if (!Array.isArray(sources) || !relation) return null;
  return sources.find((row) => row && row.relation === relation) || null;
}

export class GridSourceLabel {
  constructor(host, deps) {
    const options = deps || {};
    this.host = host || null;
    this.doc = options.doc || (host && host.ownerDocument) || null;
    // 🔴 라우트가 아니라 «함수»를 받습니다. 이 부품은 apiBase 도 fetch 도 모릅니다.
    this.loadDeclaration = options.loadDeclaration || null;
    // `null` 은 「아직 안 읽음」입니다. `[]` 는 「읽었는데 소스가 하나도 없음」이고,
    // 그 둘은 다른 사실이라 같은 값으로 두지 않습니다.
    this.sources = null;
    this.loadState = 'idle';
    this.message = null;
    this.relation = null;
  }

  mount() {
    this.render();
    this.load();
  }

  destroy() {
    if (this.host) this.host.textContent = '';
  }

  async load() {
    if (!this.loadDeclaration) {
      // 주입을 안 받았으면 «읽은 적이 없습니다». 「아님」으로 그리면 거짓말입니다.
      this.loadState = 'refused';
      this.message = '선언을 받지 못했습니다';
      this.render();
      return;
    }
    this.loadState = 'loading';
    this.render();
    let got = null;
    try {
      got = await this.loadDeclaration();
    } catch (err) {
      got = null;
    }
    if (got && got.ok !== false && Array.isArray(got.sources)) {
      this.sources = got.sources;
      this.loadState = 'ready';
      this.message = null;
    } else {
      // 🔴 여기가 «못 읽음» 입니다. `sources` 를 [] 로 두면 다음 렌더가 「아님」이 되고,
      //    그 순간 라우트 실패가 «사실»로 둔갑합니다.
      this.sources = null;
      this.loadState = 'refused';
      this.message = (got && got.message) || '선언을 못 읽었습니다';
    }
    this.render();
  }

  /** 화면이 표를 바꿨다고 알려 주는 «한 자리». 부품이 표 선택을 알지 않습니다. */
  setRelation(relation) {
    const next = relation || null;
    if (next === this.relation) return;
    this.relation = next;
    this.render();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    this.host.textContent = '';
    const root = doc.createElement('div');
    root.className = 'grid-source-label';

    // 표를 안 골랐으면 «주장하지 않습니다». 부재 셋 중 어느 것도 아니고, 주어가 없는 것입니다.
    if (!this.relation) {
      root.className = 'grid-source-label is-idle';
      this.host.appendChild(root);
      return;
    }

    if (this.loadState === 'loading' || this.loadState === 'idle') {
      root.className = 'grid-source-label is-pending';
      root.textContent = '선언을 읽는 중…';
      this.host.appendChild(root);
      return;
    }

    if (this.loadState === 'refused') {
      // 🔴 셋 중 «셋째». 「아님」과 같은 문장을 쓰면 안 됩니다.
      root.className = 'grid-source-label is-unknown';
      root.textContent = `선언을 못 읽었습니다 — ${this.message || ''}`.trim();
      root.setAttribute('data-source-state', 'unknown');
      this.host.appendChild(root);
      return;
    }

    const row = rowFor(this.sources, this.relation);
    if (!row) {
      // 🔴 셋 중 «둘째». 읽었고, 목록에 없습니다 — 그건 «사실»이라 말합니다.
      root.className = 'grid-source-label is-not-source';
      root.textContent = '원장에 안 들어갑니다';
      root.setAttribute('data-source-state', 'not_source');
      this.host.appendChild(root);
      return;
    }

    root.className = 'grid-source-label is-source';
    root.setAttribute('data-source-state', 'source');
    const emits = Array.isArray(row.emits) ? row.emits : [];
    const name = doc.createElement('span');
    name.className = 'grid-source-label__name';
    name.textContent = `원장 소스 — ${row.source}`;
    root.appendChild(name);
    const makes = doc.createElement('span');
    makes.className = 'grid-source-label__emits';
    // 술어가 «없는» 소스는 오늘 없지만, 있으면 그 사실을 말합니다 — 빈 괄호로 두지 않습니다.
    makes.textContent = emits.length
      ? ` · 만드는 것: ${emits.join(' · ')}`
      : ' · 만드는 술어가 선언에 없습니다';
    root.appendChild(makes);
    this.host.appendChild(root);
  }
}
