// ═══════════════════════════════════════════════════════════════════════════════
// GRID RESCOPE MENU — 「고른 행을 어느 컬럼으로 묶어 다시 번역할 것인가」
//
// 🔴 고르는 곳은 그리드, 실행하는 곳은 어드민 (총괄 판정 2026-08-31). 이 부품은 «범위를
//    조립해서 넘길» 뿐이고, 드라이런도 실행도 «안 합니다» -- 그 둘은 토큰이 있는 자리의 일입니다.
//    그래서 이 파일에 `/admin/` 도 토큰도 «없습니다». 있으면 그 경계가 여기서 지워집니다.
//
// 🔴 고를 수 있는 컬럼은 «서버가 준 목록»뿐입니다 (게이트 G3). 컬럼마다 한 줄이므로,
//    서버가 거절할 컬럼은 «화면에 아예 없습니다» -- 고른 뒤 400 을 받는 길이 없습니다.
//    목록은 선언의 `scope_columns` 이고, 그건 범위 읽기가 거절에 쓰는 «그 목록»입니다.
//
// 🔴 메뉴가 «없는» 것도 셋으로 갈립니다. 합치면 「이 표는 소스가 아니다」와 「행을 안 골랐다」가
//    같아지고, 운영자는 왜 메뉴가 없는지 알 수 없습니다:
//       선언 안 된 표      -> 줄이 «하나도» 없습니다 (G1)
//       고른 행이 없음     -> 「행을 고르면 여기에 나옵니다」 한 줄
//       고른 행에 그 컬럼 값이 없음 -> 그 컬럼 줄만 «비활성»이고 왜인지 말합니다
//
// 🔴 조립식: 자기 `<ul>` 하나. 남의 메뉴 안을 «직접» 그리지 않고, 화면이 그 ul 을 앉힙니다.
//    모듈 수준 상태 없음 -- 같은 페이지에 둘을 앉혀도 서로를 모릅니다.
//
// NO DOM GLOBALS, NO NETWORK. 맨 node 문서 스텁으로 채점됩니다.
// ═══════════════════════════════════════════════════════════════════════════════

/** 고른 행들이 이 컬럼에서 «실제로 들고 있는» 값. 없는 값은 지어내지 않고 «셉니다». */
// 🔴 «읽는 법»을 주입받습니다 (2026-08-31 라이브 실측). 이 그리드는 행을 «봉투»로 들고
//    있어서(`row.data[col].value`) 평범한 `row[col]` 읽기는 값이 있는데도 «전부 없음»을 냅니다 --
//    화면이 「이 값이 없습니다」라는 «거짓»을 말하게 되는 자리입니다. 부품이 봉투를 알면
//    그리드를 아는 것이므로, 아는 쪽(화면)이 함수로 알려 줍니다.
export function scopeValuesFor(rows, column, readValue) {
  const read = readValue || ((row, col) => (row ? row[col] : undefined));
  const seen = [];
  let missing = 0;
  for (const row of rows || []) {
    const raw = read(row, column);
    if (raw === undefined || raw === null || raw === '') { missing += 1; continue; }
    const value = String(raw);
    if (!seen.includes(value)) seen.push(value);
  }
  return { values: seen, missing };
}

export class GridRescopeMenu {
  constructor(host, deps) {
    const options = deps || {};
    this.host = host || null;
    this.doc = options.doc || (host && host.ownerDocument) || null;
    // 선언이 준 소스 행들. `null` 은 「아직/못 읽음」이고 `[]` 와 다릅니다.
    this.sources = options.sources || null;
    // 화면이 「지금 고른 행」을 주는 함수. 부품이 그리드를 «모릅니다».
    this.getSelection = options.getSelection || (() => []);
    // 범위를 넘기는 «한 함수». 이 부품은 저장소도 주소도 모릅니다.
    this.handOff = options.handOff || null;
    // 「이 행의 이 컬럼 값」을 어떻게 꺼내는가. 그리드의 행 모양은 «화면»이 압니다.
    this.readValue = options.readValue || null;
    this.relation = null;
  }

  setSources(sources) { this.sources = sources; this.render(); }

  setRelation(relation) {
    const next = relation || null;
    if (next === this.relation) return;
    this.relation = next;
    this.render();
  }

  /** 선언이 이 표에 대해 말하는 것 «전부». 없으면 null 이고, 그때 메뉴는 통째로 없습니다. */
  sourceRow() {
    if (!Array.isArray(this.sources) || !this.relation) return null;
    return this.sources.find((row) => row && row.relation === this.relation) || null;
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    this.host.textContent = '';
    const row = this.sourceRow();
    // 🔴 게이트 G1: 선언에 없는 표에서는 «줄이 하나도» 없습니다. 비활성 줄로 두면
    //    「눌러도 되는 것처럼 보이는 죽은 버튼」이 되고, 그건 화면이 하는 거짓말입니다.
    if (!row) return;

    const list = doc.createElement('ul');
    list.className = 'rescope-menu';
    list.setAttribute('data-rescope-relation', this.relation);

    const rows = this.getSelection() || [];
    if (!rows.length) {
      const note = doc.createElement('li');
      note.className = 'rescope-menu__note';
      note.textContent = '행을 고르면 «다시 번역»이 여기에 나옵니다';
      list.appendChild(note);
      this.host.appendChild(list);
      return;
    }

    const columns = Array.isArray(row.scope_columns) ? row.scope_columns : [];
    if (!columns.length) {
      // 소스인데 범위 컬럼이 «선언에 없습니다». 그 사실을 말하지, 아무 컬럼이나 제안하지 않습니다.
      const note = doc.createElement('li');
      note.className = 'rescope-menu__note';
      note.textContent = '이 소스는 범위 컬럼을 선언하지 않았습니다';
      list.appendChild(note);
      this.host.appendChild(list);
      return;
    }

    for (const column of columns) {
      const { values, missing } = scopeValuesFor(rows, column, this.readValue);
      const item = doc.createElement('li');
      item.setAttribute('data-rescope-column', column);
      if (!values.length) {
        // 그 컬럼 줄만 죽습니다. 지우면 「서버가 안 받는 컬럼」과 구별이 사라집니다.
        item.className = 'rescope-menu__item is-empty';
        item.textContent = `${column} — 고른 행에 이 값이 없습니다`;
        list.appendChild(item);
        continue;
      }
      item.className = 'rescope-menu__item';
      const skipped = missing ? ` · 값 없는 행 ${missing}` : '';
      item.textContent = `선택한 ${rows.length}행 → ${column} ${values.length}개로 다시 번역${skipped}`;
      item.addEventListener('click', () => {
        if (!this.handOff) return;
        // 🔴 넘기는 것은 «연산이 선언한 이름 그대로»입니다. 화면이 이름을 지어내면
        //    어드민이 그 키로 400 을 받고, 운영자는 자기가 무엇을 잘못했는지 못 봅니다.
        this.handOff({
          op: 'ledger_rescope',
          params: {
            source: row.source,
            scope_column: column,
            scope_values: values.join(','),
          },
        });
      });
      list.appendChild(item);
    }
    this.host.appendChild(list);
  }
}
