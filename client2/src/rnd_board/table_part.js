// ═══════════════════════════════════════════════════════════════════════════════
// 표 — 부품 «하나». 구성 표도 순위 표도 이것입니다. 다른 것은 «선언»뿐입니다.
//
// 🔴 소유자 상설 ① (2026-08-24): 「모든 개발은 «근원 템플릿 요소» 개발 후 «데이터 갈아끼우기»」.
//    부품을 일곱 클래스로 나눠 놓고 그 «안»에서 표를 두 번 손으로 그렸고, 그래서 한 화면의 표
//    둘이 머리·행높이·줄수·구분선·정렬·상태 표기가 «전부» 달랐습니다. 클래스로 나눈 것만으로는
//    부족합니다 -- 부품 안에서 반복하면 바깥의 조립식이 안쪽에서 무너집니다.
//
// 🔴 선언은 컬럼입니다:  { key, label, align, width, kind }
//    kind    text · mono · number · two_line(주/부) · badge(상태) · rank
//    값      row[key].  `two_line` 은 row[key] 와 row[col.subKey] 를 함께 읽습니다
//
// 🔴 없는 값은 «없다고» 그립니다. `null`·`undefined`·`''` 는 「-」 이고 is-absent 를 답니다.
//    0 은 값입니다 -- 없는 것과 0 을 같은 픽셀로 그리는 것이 이 화면이 없애려는 오독입니다.
//
// 🔴 상태 표기도 «한 곳»입니다. `badge` 는 서버가 준 값을 그대로 찍습니다. RESOLVED 를 「해결」로
//    옮기거나 「최상위」를 대문자로 바꾸지 않습니다 -- 번역하는 순간 두 표가 다시 달라집니다.
//
// 다른 부품과 같은 계약: 자기 host, 주입된 doc/markings, 모듈 수준 상태 0.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel, markingIntent } from './panel.js';
import { SIGN } from './marking_store.js';

const ABSENT = '-';

/** `null`·`undefined`·`''` 만 부재입니다. 0 과 false 는 값입니다. */
function isAbsent(value) {
  return value === null || value === undefined || value === '';
}

export class TablePart extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    this.columns = Array.isArray(options.columns) ? options.columns.slice() : [];
    this.rows = Array.isArray(options.rows) ? options.rows.slice() : [];
    // 행 하나를 마킹 노드로 만드는 열쇠. 선언 안 하면 이 표는 «읽기 전용»입니다.
    this.rowKey = options.rowKey || null;
    this.emptyText = options.emptyText || '행이 없습니다';
    // 행 아래 «펼침». 무엇을 펼치는지는 표가 모릅니다 -- 쓰는 쪽이 요소를 만들어 줍니다.
    this.detailFor = options.detailFor || null;
    // 행을 눌렀을 때 «표가 마킹한 뒤» 부르는 것. 표는 여전히 마킹만 압니다.
    this.onRowClick = options.onRowClick || null;
  }

  /** 데이터만 갈아끼웁니다. 컬럼 선언은 그대로입니다. */
  setRows(rows) {
    this.rows = Array.isArray(rows) ? rows.slice() : [];
    this.render();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    this.host.textContent = '';
    const root = doc.createElement('div');
    root.className = 'rb-table';

    if (this.title) {
      const cap = doc.createElement('div');
      cap.className = 'rb-part-title';
      cap.textContent = this.title;
      root.appendChild(cap);
    }

    root.appendChild(this._head());

    if (!this.rows.length) {
      const empty = doc.createElement('div');
      empty.className = 'rb-table-empty';
      empty.textContent = this.emptyText;
      root.appendChild(empty);
      this.host.appendChild(root);
      return;
    }

    for (const row of this.rows) {
      root.appendChild(this._row(row));
      const detail = this.detailFor && this.rowKey ? this.detailFor(row) : null;
      if (detail) root.appendChild(detail);
    }
    this.host.appendChild(root);
  }

  /**
   * 🔴 머리와 행은 «같은 컬럼 선언»으로 그려집니다. 둘을 따로 그리면 그날부터 어긋납니다 --
   *    그게 지금 두 표가 서로 다른 이유입니다.
   */
  _template() {
    return this.columns.map((c) => c.width || 'minmax(0, 1fr)').join(' ');
  }

  _head() {
    const doc = this.doc;
    const el = doc.createElement('div');
    el.className = 'rb-table-head';
    el.style.gridTemplateColumns = this._template();
    for (const col of this.columns) el.appendChild(this._cellEl(col, col.label || '', 'head'));
    return el;
  }

  _row(row) {
    const doc = this.doc;
    const el = doc.createElement('div');
    const id = this.rowKey ? row[this.rowKey] : null;
    const sign = id ? this.signOf(id) : SIGN.ABSENT;
    el.className = 'rb-table-row'
      + (sign === SIGN.CASE ? ' is-marked-case' : '')
      + (sign === SIGN.CONTROL ? ' is-marked-control' : '');
    el.style.gridTemplateColumns = this._template();
    if (id) {
      el.setAttribute('data-row-id', String(id));
      // 마킹은 «노드»로 겁니다. 쓸 이름을 선언 안 한 표에서는 `mark` 가 그냥 돌아옵니다.
      el.addEventListener('click', (event) => {
        const intent = markingIntent(event);
        this.mark(id, intent.sign, intent.mode);
        if (this.onRowClick) this.onRowClick(id, event);
        else this.render();
      });
    }
    for (const col of this.columns) el.appendChild(this._cell(col, row));
    return el;
  }

  _cell(col, row) {
    const value = row[col.key];
    if (col.kind === 'two_line') {
      const main = isAbsent(value) ? ABSENT : String(value);
      const sub = col.subKey ? row[col.subKey] : null;
      return this._cellEl(col, main, 'two_line', isAbsent(value) ? null : sub);
    }
    const text = isAbsent(value) ? ABSENT : String(value);
    return this._cellEl(col, text, col.kind || 'text');
  }

  _cellEl(col, text, kind, sub) {
    const doc = this.doc;
    const el = doc.createElement('div');
    const absent = text === ABSENT && kind !== 'head';
    el.setAttribute('data-col', col.key || '');
    el.className = `rb-table-cell rb-table-cell--${kind}`
      + (col.align === 'right' ? ' is-right' : '')
      + (absent ? ' is-absent' : '');
    if (kind === 'two_line' && sub) {
      const main = doc.createElement('div');
      main.className = 'rb-table-main';
      main.textContent = text;
      const under = doc.createElement('div');
      under.className = 'rb-table-sub';
      under.textContent = String(sub);
      el.append(main, under);
      return el;
    }
    el.textContent = text;
    return el;
  }
}
