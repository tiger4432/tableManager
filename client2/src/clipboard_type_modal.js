// CLIPBOARD TYPE MODAL — 「붙여넣을 것이 여러 모양일 때 어느 것으로 받나」를 묻는 부품.
//
// 🔴 왜 파일이 하나 생겼나 (C-100). 이것은 `main.js` 안의 함수 하나였고, 겉모양을 «전부»
//    `Object.assign(el.style, {…})` 와 innerHTML 의 `style="…"` 로 지었습니다 — 클래스가 «하나도»
//    없었습니다. 그래서 시트가 이 화면에 대해 «아무 말도 할 수 없고», 테마·토큰·상태 규칙이
//    닿지 않습니다(스킬: 「인라인이 스타일시트를 이긴다」의 극단).
//    그리고 겹침이 하나 더 있었습니다: 겉 상자가 «고정 id»(`clipboard-type-modal-overlay`)를
//    달고 있어서, 같은 화면에 둘이 뜨면 둘째가 첫째를 가리키는 셀렉터를 훔칩니다.
//
// 🔴 조립식 상설 그대로입니다 (소유자 2026-08-23):
//      클래스     생성자가 «자기 mount 와 deps»를 받는다 · 모듈 수준 상태 «없음»
//      고유 div   부품이 자기 div 를 만들어 그 안에만 그린다
//      배치       어디에 뜨나는 부품 «밖»의 일이라 mount 가 정한다 (오늘은 `document.body`)
//      시험       같은 화면에 «둘»을 놓고 간섭이 «0»
//
// ⛔ 겉모양은 여기 없습니다. `style.css` 의 `.ctm-*` 가 들고 있고, 이 파일은 «구조»와
//    «약속»(고른 것 하나를 resolve)만 압니다. hover 도 CSS 입니다 — 두 리스너로 쓴 hover 는
//    키보드로 닿지 않고, 그래서 그건 스타일이 아니라 «결함»이었습니다.

/**
 * 이 화면이 아는 붙여넣기 모양들. 🔴 «값»이라 여기 삽니다 — 목록이 아니라 «이름표»입니다:
 * 서버도 선언도 이 이름을 안 주고, 브라우저가 주는 MIME 을 사람이 읽는 말로 바꾸는 것뿐입니다.
 * ⚠️ 모르는 모양이 와도 «그립니다» — MIME 그대로. 빼면 붙일 수 있는 것을 못 고르게 됩니다.
 */
export const CLIPBOARD_TYPE_LABELS = Object.freeze({
  'text/plain': { label: 'Plain Text (일반 텍스트)', icon: '📋', accent: 'var(--accent)' },
  'text/html': { label: 'HTML Table (엑셀 표 서식 포함)', icon: '🌐', accent: 'var(--success)' },
  'text/rtf': { label: 'Rich Text Format (RTF 서식)', icon: '📝', accent: 'var(--warning)' },
  'text/csv': { label: 'Comma Separated (CSV)', icon: '📊', accent: 'var(--info)' },
  'application/json': { label: 'JSON Data Object', icon: '⚙️', accent: 'var(--accent-2)' },
});

/** 사라지는 데 걸리는 시간. CSS 의 전이와 «같은 수»여야 해서 한 자리에 둡니다. */
export const CTM_CLOSE_MS = 200;

export class ClipboardTypeModal {
  /**
   * @param {HTMLElement} mount  이 부품이 자기 div 를 앉힐 자리
   * @param {{doc?: Document, labels?: object, closeMs?: number, timer?: Function}} [deps]
   */
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('ClipboardTypeModal needs a mount element');
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    if (!this.doc) throw new Error('ClipboardTypeModal needs a document');
    this.labels = deps.labels || CLIPBOARD_TYPE_LABELS;
    // ⚠️ 시간은 «주입»받습니다. 하니스가 기다리게 하지 않으려는 것이 아니라, 기다림이 부품의
    //    «성질»이 아니어서입니다 — 같은 부품이 애니메이션 없는 자리에도 섭니다.
    this.closeMs = deps.closeMs === undefined ? CTM_CLOSE_MS : deps.closeMs;
    this.timer = deps.timer || ((fn, ms) => setTimeout(fn, ms));
    this.root = null;
  }

  _el(tag, cls, text) {
    const el = this.doc.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  /**
   * 하나 고를 때까지 기다립니다.
   * @param {string[]} types  브라우저가 내놓은 MIME 들
   * @returns {Promise<string|null>} 고른 모양, 또는 취소면 `null`
   */
  open(types) {
    return new Promise((resolve) => {
      const doc = this.doc;
      const overlay = this._el('div', 'ctm-overlay');
      // 🔴 id 가 «없습니다». 종전에 고정 id 를 달고 있어서 둘째 인스턴스가 첫째의 셀렉터를
      //    훔쳤습니다 — 조립식이 막는 바로 그 겹침이고, 오류는 안 납니다.
      overlay.setAttribute('role', 'dialog');
      overlay.setAttribute('aria-modal', 'true');

      const card = this._el('div', 'ctm-card');
      const head = this._el('div', 'ctm-head');
      head.append(
        this._el('h3', 'ctm-title', '붙여넣기 형식 선택'),
        this._el('p', 'ctm-sub', '클립보드에 여러 형식이 있습니다 · 하나를 고르십시오'));
      card.append(head);

      const list = this._el('div', 'ctm-list');
      for (const type of types || []) {
        // ⚠️ 모르는 MIME 도 «고를 수 있게» 그립니다 — 이름표만 없는 것이지 못 붙이는 것이 아닙니다.
        const cfg = this.labels[type] || { label: type, icon: '📄', accent: 'var(--text)' };
        const row = this._el('button', 'ctm-row');
        row.type = 'button';
        row.setAttribute('data-type', type);
        // 🔴 색은 «데이터»라 사용자 지정 속성으로 내려갑니다 — 규칙은 CSS 에 있고 값만 여기서
        //    옵니다. 그래야 hover·focus 가 한 자리에서 그 색을 씁니다.
        row.style.setProperty('--ctm-accent', cfg.accent);
        row.append(this._el('span', 'ctm-icon', cfg.icon));
        const text = this._el('div', 'ctm-text');
        text.append(this._el('span', 'ctm-label', String(cfg.label).split(' (')[0]),
                    this._el('span', 'ctm-mime', type));
        row.append(text);
        if (row.addEventListener) row.addEventListener('click', () => close(type));
        list.append(row);
      }
      card.append(list);

      const cancel = this._el('button', 'ctm-cancel', '취소');
      cancel.type = 'button';
      cancel.setAttribute('data-action', 'cancel');
      if (cancel.addEventListener) cancel.addEventListener('click', () => close(null));
      card.append(cancel);

      overlay.append(card);
      this.mount.appendChild(overlay);
      this.root = overlay;

      // 들어오는 것은 «클래스 하나»입니다. 값은 CSS 의 것이고 이 파일은 그 이름만 압니다.
      //
      // 🔴 프레임을 «안 기다립니다». 실측 2026-09-13, 탭이 숨겨진 채로: `requestAnimationFrame`
      //    이 한 번도 안 불리고, 그러면 이 클래스가 영영 안 붙어 «보이지 않는데 클릭은 막는»
      //    상자가 남습니다. 종전 코드도 같은 모양이라 이 라운드가 만든 것이 아니라 드러난 것입니다.
      // ⚠️ 프레임을 기다린 «이유»는 「처음 상태를 한 번 그리게 해서 전이가 돌게」이고, 레이아웃을
      //    강제로 읽으면 같은 값을 얻습니다 — 그리고 그건 숨겨진 탭에서도 참입니다.
      //    (`void` 는 「읽기만 하고 버린다」를 말합니다 — 번들러가 지우지 못하게.)
      void overlay.offsetWidth;
      overlay.classList.add('is-open');

      const close = (value) => {
        overlay.classList.remove('is-open');
        this.timer(() => {
          // ⚠️ 자기 div «만» 치웁니다. 남의 것을 건드리지 않는 것이 조립식의 절반입니다.
          if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
          if (this.root === overlay) this.root = null;
          resolve(value);
        }, this.closeMs);
      };
    });
  }
}
