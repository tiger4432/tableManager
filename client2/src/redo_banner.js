// ═══════════════════════════════════════════════════════════════════════════════
// REDO BANNER — 「고른 행을 «어떤 그룹으로 묶어» 다시 돌릴 것인가」
//
// 🔴 자리가 배너인 이유 (소유자가 두 번 지적). 선택은 «그리드»에서 일어나고, 우클릭에 넣으면
//    메뉴가 길어집니다. 배너는 «선택 상태»를 보고 활성/비활성이 되므로 고른 뒤에 눈이 갑니다.
//
// 🔴 여기서 «직접 돌립니다» (소유자 요구, 2026-09-01). 2026-08-31 의 판정 ⓐ「고르는 곳은
//    그리드, 실행하는 곳은 어드민」을 «무릅니다» -- 고른 뒤 다른 페이지로 넘어가는 것이
//    소유자에게는 한 걸음 더였습니다.
//
// 🔴 그래도 이 파일에 `/admin/` 도 fetch 도 토큰도 «없습니다». 돌리는 것은 «주입된 한 함수»
//    (`run(op, params)`) 이고, 토큰은 «있는지만» 묻습니다 (`hasToken()`). 값을 들고 있지
//    않으므로 하니스가 «진짜 토큰 없이» 이 부품을 채점할 수 있습니다 -- 그것이 이 경계의 값어치입니다.
//
// 🔴 두 버튼의 줄은 «서로 다른 것»이 정합니다:
//       원장  scope_column 값마다   -> 선언이 주고, 그러니 «여기»서 묶습니다
//       체인  규칙마다              -> 규칙 «이름 목록»을 화면이 넣어 줍니다 (`setRules`).
//                                  `null`(못 읽음)과 `[]`(선언에 없음)은 «다르게» 그립니다 --
//                                  합치면 403 과 빈 설정이 같은 픽셀이 됩니다
//
// 🔴 조립식: 자기 div 하나. 남의 헤더 안을 직접 그리지 않고, 화면이 그 div 를 앉힙니다.
//    모듈 수준 상태 없음 — 같은 페이지에 둘을 앉혀도 서로를 모릅니다.
//
// NO DOM GLOBALS, NO NETWORK. 맨 node 문서 스텁으로 채점됩니다.
// ═══════════════════════════════════════════════════════════════════════════════

// 🔴 닫는 방법은 «한 벌»입니다. 필터 칩 펼침이 둘째로 같은 것을 필요로 했고, 두 번째를
//    손으로 그리는 대신 올렸습니다 (상설: 근원 템플릿 요소 개발 후 데이터 갈아끼우기).
import { watchForDismiss } from './dropdown.js';

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
  // 🔴 C-114. 세는 것만으로는 「어느 행이냐」에 답할 수 없습니다. «같은 걸음»에서 첫 행을
  //    같이 들고 나옵니다 — 밖에서 다시 걸으면 «비었다»의 판별식이 두 벌이 됩니다(기준 ④).
  let firstMissing = null;
  for (const row of rows || []) {
    const raw = read(row, column);
    if (raw === undefined || raw === null || raw === '') {
      missing += 1;
      if (firstMissing === null) firstMissing = row;
      continue;
    }
    const value = String(raw);
    if (!seen.includes(value)) seen.push(value);
  }
  return { values: seen, missing, firstMissing };
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
    // 조립한 것을 넘기는 «한 함수». 이 부품은 저장소도 주소도 모릅니다.
    this.handOff = options.handOff || null;
    // «돌리는» 한 함수. (op, params) -> Promise<{ok, state?, error?}>.
    this.run = options.run || null;
    // 토큰이 «있는지»만 묻습니다. 값을 받지 않습니다.
    this.hasToken = options.hasToken || (() => false);
    // 체인 규칙 «이름» 목록. `null` 은 「아직/못 읽음」이고 `[]` 와 다릅니다.
    this.rules = Array.isArray(options.rules) ? options.rules : null;
    // 🔴 C-113 ①. «얼마부터 큰가»는 이 부품이 정하지 않습니다 — 옵션 하나이고 기본은
    //    1000 입니다(운영 규격: 한 트랜잭션에 수천 행). 숫자를 박으면 그 숫자가
    //    다른 설치에서도 맞다고 말하는 것이 됩니다.
    this.warnAbove = typeof options.warnAbove === 'number' ? options.warnAbove : 1000;
    // 🔴 C-114. «그 행을 보여 달라»는 함수 하나를 받습니다. 이 부품은 그리드 API 를
    //    모릅니다 — `run` 과 같은 규율이고, 그래서 하니스가 진짜 그리드 없이 채점합니다.
    this.reveal = typeof options.reveal === 'function' ? options.reveal : null;
    this.relation = null;
    this.open = null;
    // 줄마다의 상태. 누른 뒤 «그 줄이» 말합니다 -- 조용히 닫으면 운영자는 두 번 누릅니다.
    this.said = {};
    // 열려 있는 동안만 걸리는 문서 리스너를 «떼는» 함수. 안 떼면 닫힌 뒤에도 클릭을 먹습니다.
    this.dismiss = null;
  }

  setRules(rules) { this.rules = Array.isArray(rules) ? rules : null; this.render(); }

  /** 바깥 클릭과 Esc 로 닫힙니다. 「없어지지도 않는다」가 소유자 지적의 절반이었습니다. */
  watchForDismiss() {
    if (this.dismiss) return;
    const detach = watchForDismiss(this.doc, this.host, () => this.close());
    if (detach) this.dismiss = () => { detach(); this.dismiss = null; };
  }

  close() {
    if (!this.open) return;
    this.open = null;
    this.said = {};
    if (this.dismiss) this.dismiss();
    this.render();
  }

  /** 한 줄을 돌립니다. 누른 «그 줄»이 답을 답니다 -- 토스트는 사라지고, 사라지면 다시 누릅니다. */
  fire(index, op, params) {
    if (!this.run || this.said[index] === 'running…') return;
    this.said[index] = 'running…';
    this.render();
    Promise.resolve(this.run(op, params)).then(
      (got) => {
        const answer = got || {};
        this.said[index] = answer.ok
          ? (answer.state || 'queued')
          : `failed — ${answer.error || 'no reason given'}`;
        this.render();
      },
      (err) => {
        this.said[index] = `failed — ${(err && err.message) || 'unreachable'}`;
        this.render();
      },
    );
  }

  setSources(sources) { this.sources = sources; this.render(); }

  setRelation(relation) {
    const next = relation || null;
    if (next === this.relation) return;
    this.relation = next;
    if (this.open) this.close();
    this.open = null;
    this.render();
  }


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

    if (this.open) {
      const box = this.panel(rows, row);
      this.host.appendChild(box);
      this.place(box, bar);
    }
  }

  /** 판을 버튼 줄 «밑»에 앉힙니다.
   *
   * 🔴 판을 버튼 줄 «안»에 넣으면 안 됩니다. 그러면 위치 조상이 그 줄이 되고, 그 줄은
   *    `overflow: hidden` 인 버튼 그룹 «안»에 있어서 판이 통째로 잘립니다 -- 박스는 있고
   *    레이아웃도 되는데 elementFromPoint 가 «뒤의 그리드»를 돌려줍니다 (실측 2026-09-02,
   *    다섯 줄 전부). 밖에 두면 위치 조상이 헤더라 안 잘리고, 그래서 «자리는 여기서» 씁니다.
   *
   * 🔴 그냥 `right: 0` 으로 두면 그 0 이 «헤더의 오른쪽 끝»입니다 -- 판이 버튼에서 660px
   *    떨어져 떴습니다 (x 1620 / 버튼 958). 오른쪽 끝을 «버튼 줄»에 맞춥니다.
   */
  place(box, bar) {
    if (!box.getBoundingClientRect || !bar.getBoundingClientRect) return;
    const anchor = bar.getBoundingClientRect();
    const parent = box.offsetParent;
    const origin = (parent && parent.getBoundingClientRect)
      ? parent.getBoundingClientRect() : { left: 0, top: 0 };
    box.style.right = 'auto';
    box.style.top = `${Math.round(anchor.bottom - origin.top + 8)}px`;
    const width = box.getBoundingClientRect().width;
    box.style.left = `${Math.round(Math.max(8, anchor.right - origin.left - width))}px`;
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
      if (this.open === which) { this.close(); return; }
      this.open = which;
      this.said = {};
      this.watchForDismiss();
      this.render();
    });
    return btn;
  }

  /** 「무엇이 어떻게 묶여 같이 도는가」 — 넘기기 «전»에 여기서 봅니다. 모달이 아닙니다. */
  panel(rows, sourceRow) {
    const doc = this.doc;
    const box = doc.createElement('div');
    // 🔴 이 화면에 «이미 있는» 드롭다운 껍데기입니다. 세로도 간격도 그림자도 거기서 옵니다.
    box.className = 'glass-dropdown-panel redo-panel';
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

    // 🔴 C-113 ①. 선택이 크면 «한 줄»로 말합니다 — 막지 않습니다(막으면 운영자가 정당하게
    //    큰 범위를 돌릴 길이 없어집니다). 수와 기준만 적고, «누를지»는 사람이 정합니다.
    const picked = this.getSelection ? (this.getSelection() || []) : [];
    if (picked.length > this.warnAbove) {
      const big = doc.createElement('div');
      big.className = 'redo-panel__warn';
      big.textContent = `선택 ${picked.length}행 · 권장 ${this.warnAbove}행 이하`;
      box.appendChild(big);
    }
    // 🔴 토큰이 없으면 «문장으로» 말합니다. 조용히 회색으로 두면 운영자는 자기 선택이
    //    잘못된 줄 알고 골랐던 것을 다시 고릅니다.
    const runnable = this.hasToken() === true && typeof this.run === 'function';
    if (!runnable) {
      const why = doc.createElement('div');
      why.className = 'redo-panel__nogo';
      why.textContent = '관리자 토큰 없음 · 어드민 한 번 열기';
      box.appendChild(why);
    }

    assembled.rows.forEach((entry, index) => {
      const pressable = runnable && !!entry.params;
      // 🔴 C-114. «돌리는 줄»과 «보여 주는 줄»은 다릅니다. 둘째는 토큰과 무관하고
      //    (읽기만 합니다), 주입된 함수가 없으면 그냥 줄입니다 — 누르면 아무 일도 안 나는
      //    버튼은 화면이 하는 거짓입니다.
      const showable = !pressable && entry.reveal != null && typeof this.reveal === 'function';
      const line = doc.createElement(pressable || showable ? 'button' : 'div');
      // 🔴 «태그가 달라도 클래스는 같습니다». 여기서 갈리면 토큰이 있을 때만 줄이 가로로
      //    흐르고, 토큰이 없는 사람은 그 결함을 «볼 수가 없습니다» (2026-09-02 소유자 지적).
      line.className = 'dropdown-item redo-panel__group';
      if (pressable) {
        line.type = 'button';
        // 확인 창은 없습니다. 줄에 «크기»가 적혀 있고, 그것을 누르는 것이 확인입니다.
        line.addEventListener('click', () => this.fire(index, assembled.op, entry.params));
      } else if (showable) {
        line.type = 'button';
        line.dataset.reveal = 'row';
        line.addEventListener('click', () => this.reveal(entry.reveal));
      }
      const said = this.said[index];
      line.textContent = said ? `${entry.text} — ${said}` : entry.text;
      // 🔴 C-109. 종류는 «한 낱말»입니다(join · decide · mapper). 글자로 잇지 않고 칸으로
      //    달아서, 누른 뒤의 답(`said`)과 한 문장이 되지 않게 합니다.
      // ⚠️ 서버가 종류를 안 말했으면 배지도 없습니다 — 지어내지 않습니다.
      if (entry.kind) {
        const kind = doc.createElement('span');
        kind.className = 'redo-panel__kind';
        kind.textContent = entry.kind;
        line.appendChild(kind);
      }
      box.appendChild(line);
    });

    // 「Open in admin」은 «남깁니다» -- 세어 보거나 규칙을 고르려면 그 자리이고, 여기서 지우면
    // rescope_handoff.js 와 admin.js 의 adoptRescopeHandoff 가 «가리키는 곳 없는» 코드가 됩니다.
    const go = doc.createElement('button');
    go.type = 'button';
    go.className = 'glass-btn redo-panel__go';
    go.textContent = '어드민에서 열기';
    go.addEventListener('click', () => {
      if (this.handOff) this.handOff(assembled.payload);
    });
    box.appendChild(go);
    return box;
  }

  ledgerPayload(rows, sourceRow) {
    if (!sourceRow) return { note: '원장 소스 아님' };
    const columns = Array.isArray(sourceRow.scope_columns) ? sourceRow.scope_columns : [];
    if (!columns.length) return { note: '범위 컬럼 선언 없음' };
    const { groups, dropped } = ledgerGroups(rows, columns, this.readValue);
    if (!groups.length) return { note: '선택 행에 범위 값 없음' };
    const lineRows = groups.map((g) => {
      const skipped = g.missing ? ` · ${g.missing} without a value` : '';
      const n = g.values.length;
      return {
        text: `${g.key} — ${n} group${n === 1 ? '' : 's'} from ${g.rows} row${g.rows === 1 ? '' : 's'}${skipped}`,
        params: {
          source: sourceRow.source,
          scope_column: g.key,
          scope_values: g.values.join(','),
        },
      };
    });
    // 못 넘긴 컬럼도 «말합니다». 조용히 빼면 운영자는 그 컬럼을 기다립니다.
    // 돌릴 것이 없으므로 `params` 가 없고, 그래서 «누르는 줄이 아닙니다».
    dropped.forEach((column) => lineRows.push({
      text: `${column} — 선택 행에 값 없음`, params: null,
    }));
    return {
      op: 'ledger_rescope',
      rows: lineRows,
      payload: {
        op: 'ledger_rescope',
        // 🔴 넘기는 이름은 «연산이 선언한 그대로»입니다. 화면이 지어내면 어드민이 그 키로
        //    400 을 받고, 운영자는 자기가 무엇을 잘못했는지 못 봅니다.
        // 🔴 그리고 «누르면 도는 것»과 «넘기는 것»이 같은 자리에서 나옵니다. 두 벌로 두었더니
        //    한쪽의 join 만 바꿔도 하니스가 초록이었습니다 (실측 2026-09-02).
        groups: lineRows.filter((entry) => entry.params)
          .map((entry) => ({ label: entry.params.scope_column, params: entry.params })),
      },
    };
  }

  chainPayload(rows) {
    // 🔴 C-112. 신원은 `row_id` 입니다 — 그리드가 «모든 표»에서 들고 있는 그것.
    //    저장된 업무 키는 composite 표에서 «조립된 문자열»이라 어느 컬럼에도 없고,
    //    화면이 «보이는 것»을 보내면 서버는 한 행도 못 찾습니다 — 박스 실측(2026-09-15):
    //    `rows_scanned 0`, 그리고 «오류는 없었습니다».
    // ⛔ 둘 다 보내지 않습니다 — 서버가 «거절»합니다(한 물음에 두 답). 그리고 평키 표만
    //    다른 길을 타면 «그 표에서만» 나는 고장이 생깁니다(기준 ④).
    const { values, missing, firstMissing } = scopeValuesFor(rows, 'row_id', this.readValue);
    if (!values.length) return { note: '선택 행에 row_id 없음' };
    // 🔴 셈은 «행 수»입니다(판정 407 ②) — row_id 는 중복이 없으므로 값의 수가 곧 행의 수입니다.
    //    종전의 「N keys from M rows」는 둘이 갈라질 수 있을 때의 문구였고, 이제 갈라지지 않습니다.
    const from = `${values.length} row${values.length === 1 ? '' : 's'}`;
    // 넘기는 모양도 같은 신원입니다 — `adoptRescopeHandoff` 가 `params` 를 그대로 앉힙니다.
    //    여기서만 업무 키를 보내면 «누르는 길»과 «넘기는 길»이 다른 것을 가리키게 됩니다.
    const payload = { op: 'chain_replay', params: { row_ids: values.join(',') } };
    // 🔴 `rule` 은 이 연산의 «필수» 파라미터라, 규칙을 모르면 돌릴 줄이 없습니다.
    //    그때 「규칙이 없다」로 그리면 «못 읽은 것»과 «선언에 비어 있는 것»이 같아집니다.
    if (!Array.isArray(this.rules)) {
      return { op: 'chain_replay', payload, rows: [
        { text: from, params: null },
        { text: '규칙 목록 못 읽음 · 어드민에서 선택', params: null },
      ] };
    }
    if (!this.rules.length) {
      // 🔴 C-109. 목록은 이제 «이 표를 트리거로 하는» 규칙만입니다. 그래서 «빈 것»의
      //    뜻도 좁아졌습니다: 「서버에 규칙이 없다」가 아니라 「이 표가 트리거인 규칙이 없다」.
      return { op: 'chain_replay', payload, rows: [
        { text: from, params: null },
        { text: '이 표를 트리거로 하는 규칙 없음', params: null },
      ] };
    }
    const keys = values.join(',');
    // 🔴 판정 407 ②. row_id 가 없는 행은 «조용히 빠지지» 않고 이름을 달고 섭니다 —
    //    그 행들은 다시 돌아가지 «않습니다», 그리고 그것이 화면에 없으면 운영자는 전부 돌았다고 읽습니다.
    const skipped = missing
      ? [{ text: `row_id 없는 행 ${missing} — 다시 돌릴 수 없음`, params: null,
           // 🔴 C-114. 수만 보여 주면 운영자는 «어느 행인지»를 모릅니다 — 그 처음 행으로
           //    그리드를 보냅니다. 돌리는 줄이 아니므로 `params` 는 그대로 `null` 입니다.
           reveal: firstMissing }] : [];
    return {
      op: 'chain_replay',
      payload,
      // 🔴 줄은 «어떤 규칙이 어디서 어디로 도는가»를 말합니다(소유자 2026-09-15:
      //    「같은 체인문이면 보여야지」). 이름만 있을 때는 같은 이름의 조인과 합성이
      //    화면에서 같아 보였습니다.
      // ⚠️ 크기(`from`)는 그대로 줄에 남습니다 — 확인 창이 없고, «그 줄을 누르는 것»이
      //    확인이기 때문입니다. 거기서 크기를 뺀다면 운영자는 무엇을 돌리는지 모르고 누릅니다.
      rows: skipped.concat(this.rules.map((rule) => {
        const name = (rule && rule.name) || '';
        // ⚠️ 구분자는 «기호»입니다. 공백 둘로 띠다가 브라우저에서 재 보니 HTML 이 그것을
        //    «하나로 접어» 이름과 트리거 표가 한 낱말처럼 붙었습니다(「lot_slot_wafer dt_lot」).
        const path = (rule && rule.trigger_table && rule.target_table)
          ? ` · ${rule.trigger_table} → ${rule.target_table}` : '';
        return {
          text: `${name}${path} — ${from}`,
          kind: (rule && rule.kind) || '',
          // 이름이 없는 규칙은 돌릴 수 없습니다(`rule` 은 필수) — 누르는 줄로 두지 않습니다.
          params: name ? { rule: name, row_ids: keys } : null,
        };
      })),
    };
  }
}
