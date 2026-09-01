// ═══════════════════════════════════════════════════════════════════════════════
// REDO BANNER — 「고른 행을 «어떤 그룹으로 묶어» 다시 돌릴 것인가」
//
// 🔴 자리가 배너인 이유 (소유자가 두 번 지적). 선택은 «그리드»에서 일어나고, 우클릭에 넣으면
//    메뉴가 길어집니다. 배너는 «선택 상태»를 보고 활성/비활성이 되므로 고른 뒤에 눈이 갑니다.
//
// 🔴 고르는 곳은 그리드, 실행하는 곳은 어드민 (총괄 판정 ⓐ, 2026-08-31 12:2x). 이 부품은
//    그룹을 «조립해서 넘길» 뿐이고 드라이런도 실행도 «안 합니다» -- 둘 다 토큰이 있는 자리의
//    일입니다. 그래서 이 파일에 `/admin/` 도 토큰도 «없습니다». 있으면 그 경계가 여기서 지워집니다.
//
// 🔴 두 버튼의 그룹은 «서로 다른 곳»이 압니다:
//       원장  scope_column 값마다   -> 선언이 주고, 그러니 «여기»서 묶습니다
//       체인  규칙마다              -> 규칙 목록이 토큰 뒤라 «어드민»이 묶습니다.
//                                  여기서는 고른 행의 업무 키만 실어 보냅니다
//    두 번째를 여기서 묶으려 하면 이 파일이 `/admin/chain/rules` 를 불러야 하고, 그 순간
//    위의 경계가 사라집니다. 무엇을 «모르는지»가 이 부품의 설계입니다.
//
// 🔴 조립식: 자기 div 하나. 남의 헤더 안을 직접 그리지 않고, 화면이 그 div 를 앉힙니다.
//    모듈 수준 상태 없음 — 같은 페이지에 둘을 앉혀도 서로를 모릅니다.
//
// NO DOM GLOBALS, NO NETWORK. 맨 node 문서 스텁으로 채점됩니다.
// ═══════════════════════════════════════════════════════════════════════════════

/** 고른 행들이 이 컬럼에서 «실제로 들고 있는» 값. 없는 값은 지어내지 않고 «셉니다».
 *
 * 🔴 «읽는 법»을 주입받습니다 (2026-08-31 라이브 실측). 이 그리드는 행을 «봉투»로 들고
 *    있어서(`row.data[col].value`) 평범한 `row[col]` 읽기는 값이 있는데도 «전부 없음»을 냅니다 --
 *    화면이 「이 값이 없습니다」라는 «거짓»을 말하게 되는 자리입니다. 부품이 봉투를 알면
 *    그리드를 아는 것이므로, 아는 쪽(화면)이 함수로 알려 줍니다.
 */
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

/** 원장 쪽 그룹: 선언된 범위 컬럼마다 하나. 값이 하나도 없는 컬럼은 «그룹이 아닙니다».
 *
 * 🔴 그 컬럼을 빈 그룹으로 넘기면 어드민이 「값 0개짜리 범위」로 400 을 받습니다. 넘길 수
 *    없는 것은 «넘기지 않고», 왜 빠졌는지는 화면이 말합니다(`dropped`).
 */
export function ledgerGroups(rows, columns, readValue) {
  const groups = [];
  const dropped = [];
  for (const column of columns || []) {
    const { values, missing } = scopeValuesFor(rows, column, readValue);
    if (!values.length) { dropped.push(column); continue; }
    // 🔴 «값이 있는 행 수»입니다. 선택 크기를 적으면 이 그룹이 «안 덮는» 행까지
    //    세고, 화면은 「3 groups from 13 rows · 7 without a value」를 냅니다 --
    //    13 과 7 이 같은 행을 두 번 세는 수라 서로 안 맞습니다. 실제로 도는 것은 6행입니다.
    //    소유자가 이 줄을 보고 「무슨 말이야」라고 물으셨고, 그것이 이 수의 판별식입니다.
    groups.push({ key: column, values, missing, rows: (rows || []).length - missing });
  }
  return { groups, dropped };
}

export class RedoBanner {
  constructor(host, deps) {
    const options = deps || {};
    this.host = host || null;
    this.doc = options.doc || (host && host.ownerDocument) || null;
    // 선언이 준 소스 행들. `null` 은 「아직/못 읽음」이고 `[]` 와 다릅니다.
    this.sources = options.sources || null;
    // 화면이 「지금 고른 행」을 주는 함수. 부품이 그리드를 «모릅니다».
    this.getSelection = options.getSelection || (() => []);
    // 「이 행의 이 컬럼 값」을 어떻게 꺼내는가. 그리드의 행 모양은 «화면»이 압니다.
    this.readValue = options.readValue || null;
    // 업무 키 «컬럼 이름». 체인은 이 값들로 고릅니다.
    this.businessKey = options.businessKey || null;
    // 조립한 것을 넘기는 «한 함수». 이 부품은 저장소도 주소도 모릅니다.
    this.handOff = options.handOff || null;
    this.relation = null;
    this.open = null;
  }

  setSources(sources) { this.sources = sources; this.render(); }

  setRelation(relation) {
    const next = relation || null;
    if (next === this.relation) return;
    this.relation = next;
    this.open = null;
    this.render();
  }

  setBusinessKey(column) { this.businessKey = column || null; this.render(); }

  /** 선택이 바뀌면 버튼의 활성/비활성이 바뀝니다. 화면이 알려 줍니다. */
  selectionChanged() { this.render(); }

  sourceRow() {
    if (!Array.isArray(this.sources) || !this.relation) return null;
    return this.sources.find((row) => row && row.relation === this.relation) || null;
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    this.host.textContent = '';
    const rows = this.getSelection() || [];
    const row = this.sourceRow();

    const bar = doc.createElement('span');
    bar.className = 'redo-banner';
    // 🔴 원장 버튼은 «이 표가 원장 소스일 때만» 존재합니다. 아닌 표에서 비활성으로 두면
    //    「행을 안 골랐다」와 「이 표는 원장이 아니다」가 같은 픽셀이 됩니다.
    if (row) bar.appendChild(this.button('ledger', 'Re-translate', rows.length > 0));
    bar.appendChild(this.button('chain', 'Replay chain', rows.length > 0));
    this.host.appendChild(bar);

    if (this.open) this.host.appendChild(this.panel(rows, row));
  }

  button(which, label, enabled) {
    const btn = this.doc.createElement('button');
    btn.type = 'button';
    btn.className = 'glass-btn redo-banner__btn';
    btn.dataset.redo = which;
    btn.textContent = label;
    // 선택이 없으면 «비활성». 눌러도 아무 일이 없는 버튼은 화면이 하는 거짓말입니다.
    btn.disabled = !enabled;
    btn.addEventListener('click', () => {
      this.open = this.open === which ? null : which;
      this.render();
    });
    return btn;
  }

  /** 「무엇이 어떻게 묶여 같이 도는가」 — 넘기기 «전»에 여기서 봅니다. 모달이 아닙니다. */
  panel(rows, sourceRow) {
    const doc = this.doc;
    const box = doc.createElement('div');
    box.className = 'redo-panel';
    box.dataset.redoPanel = this.open;

    const assembled = this.open === 'ledger'
      ? this.ledgerPayload(rows, sourceRow)
      : this.chainPayload(rows);

    if (assembled.note) {
      const note = doc.createElement('div');
      note.className = 'redo-panel__note';
      note.textContent = assembled.note;
      box.appendChild(note);
      return box;
    }

    assembled.lines.forEach((text) => {
      const line = doc.createElement('div');
      line.className = 'redo-panel__group';
      line.textContent = text;
      box.appendChild(line);
    });

    const go = doc.createElement('button');
    go.type = 'button';
    go.className = 'glass-btn btn-primary redo-panel__go';
    go.textContent = 'Open in admin';
    go.addEventListener('click', () => {
      if (this.handOff) this.handOff(assembled.payload);
    });
    box.appendChild(go);
    return box;
  }

  ledgerPayload(rows, sourceRow) {
    if (!sourceRow) return { note: 'this table is not a ledger source' };
    const columns = Array.isArray(sourceRow.scope_columns) ? sourceRow.scope_columns : [];
    if (!columns.length) return { note: 'this source declares no scope column' };
    const { groups, dropped } = ledgerGroups(rows, columns, this.readValue);
    if (!groups.length) return { note: 'no scope column has a value in the selected rows' };
    const lines = groups.map((g) => {
      const skipped = g.missing ? ` · ${g.missing} without a value` : '';
      const n = g.values.length;
      return `${g.key} — ${n} group${n === 1 ? '' : 's'} from ${g.rows} row${g.rows === 1 ? '' : 's'}${skipped}`;
    });
    // 못 넘긴 컬럼도 «말합니다». 조용히 빼면 운영자는 그 컬럼을 기다립니다.
    dropped.forEach((column) => lines.push(`${column} — no value in the selected rows`));
    return {
      lines,
      payload: {
        op: 'ledger_rescope',
        // 🔴 넘기는 이름은 «연산이 선언한 그대로»입니다. 화면이 지어내면 어드민이 그 키로
        //    400 을 받고, 운영자는 자기가 무엇을 잘못했는지 못 봅니다.
        groups: groups.map((g) => ({
          label: g.key,
          params: {
            source: sourceRow.source,
            scope_column: g.key,
            scope_values: g.values.join(','),
          },
        })),
      },
    };
  }

  chainPayload(rows) {
    if (!this.businessKey) return { note: 'this table declares no business key' };
    const { values, missing } = scopeValuesFor(rows, this.businessKey, this.readValue);
    if (!values.length) return { note: 'the selected rows carry no business key' };
    const skipped = missing ? ` · ${missing} without a value` : '';
    return {
      // 🔴 「규칙마다 한 그룹」은 «여기서» 만들지 않습니다 — 규칙 목록이 토큰 뒤라 이 페이지가
      //    모릅니다. 아는 것(고른 키)만 넘기고, 묶는 것은 아는 쪽이 합니다.
      lines: [`${values.length} key${values.length === 1 ? '' : 's'} from ${rows.length} row${rows.length === 1 ? '' : 's'}${skipped}`,
              'grouped by rule in admin, which is where the rules are'],
      payload: {
        op: 'chain_replay',
        businessKeys: values,
      },
    };
  }
}
