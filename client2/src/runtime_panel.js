// ═══════════════════════════════════════════════════════════════════════════════
// 런타임 — 아홉 고리가 «마지막으로 무엇을 했나». 값만.
//
// 🔴 소유자 2026-09-11: 「뭔지도 모르는 게 뒤에서 계속 도네」. 프로세스가 살았는지, 그
//    안의 고리가 «언제» 한 바퀴를 돌았는지, 그 바퀴가 «얼마나» 걸렸는지가 아무 화면에도
//    없었습니다. `/health` 는 «판정»을 내고 이 표는 «값»을 냅니다 — 한쪽이 다른 쪽을 대신
//    정하면 큐가 한 시간째 안 움직이는데 초록 불이 켜집니다(S-176 라우트 주석이 같은 말).
//
// 🔴 판정을 여기서 «다시 하지 않습니다». 살았나(`alive`)도 나이도 서버가 이미 잰 값이고,
//    이 파일이 더하는 것은 「어느 칸에 놓나」뿐입니다.
//
// 🔴 없는 키는 «없는 것»입니다. 0 으로 그리면 「한 번도 안 돌았다」와 「0 초 걸렸다」가 같은
//    픽셀이 되고, 그 침묵이 이 표가 없애려는 바로 그것입니다. 철자는 `absent.js` 한 곳입니다.
//
// ⛔ 설명 문구 «0» (상설). 머리에 컬럼 이름, 칸에 값. 그 밖에 문장이 없습니다.
// ═══════════════════════════════════════════════════════════════════════════════
import { ABSENT, isCount, countText } from './absent.js';

/** 살았나 — 세 상태입니다. 「모른다」를 ○ 로 그리면 죽은 것으로 읽힙니다. */
export const ALIVE = Object.freeze({ YES: '●', NO: '○', UNKNOWN: ABSENT });

/**
 * 점의 «색». 소유자 2026-09-11: 살았나는 낱말이 아니라 「색 점」입니다.
 *
 * 🔴 색을 정하는 것은 «값»이지 «칸 이름»이 아닙니다. 렌더가 `key === 'alive'` 로 갈래를 트면
 *    그 순간 표가 도메인 낱말을 하나 갖게 되고, 다음 색은 또 다른 갈래가 됩니다 (기준 ③).
 * ⚠️ 「모른다」에는 색이 «없습니다» — 회색 대시는 이미 「안 왔다」를 말하고, 거기에 색을 주면
 *    판정이 하나 생깁니다. 이 표는 판정을 하지 않습니다.
 */
export const TONE = Object.freeze({ [ALIVE.YES]: 'ok', [ALIVE.NO]: 'danger' });

/**
 * 컬럼 «선언». 라벨은 화면의 낱말이고 key 는 아래 `rowOf` 가 채우는 이름입니다.
 *
 * ⚠️ 도메인 낱말이 아닙니다 — 고리 이름도 프로세스 이름도 여기 없습니다. 그것들은
 *    «응답이» 들고 옵니다.
 */
export const COLUMNS = Object.freeze([
  { key: 'loop', label: '고리' },
  { key: 'process', label: '프로세스' },
  { key: 'alive', label: '살았나', align: 'center' },
  { key: 'age', label: '마지막 바퀴', align: 'right' },
  { key: 'seconds', label: '소요', align: 'right' },
  { key: 'depth', label: '깊이', align: 'right' },
  { key: 'pace', label: '페이스', align: 'right' },
  { key: 'knob', label: '손잡이' },
]);

/**
 * 그릴 «열». 한 행이라도 값을 가진 열만 남습니다 (소유자: 「열은 값이 있는 것만」).
 *
 * 🔴 「아무도 값이 없다」와 「이 고리에 그 값이 없다」는 다른 사실이고, 여기서 지워지는 것은
 *    «앞»의 것뿐입니다. 한 행이라도 값이 있으면 열은 남고, 값 없는 칸은 여전히 `—` 입니다 —
 *    열이 통째로 사라져 «있는 값»이 감춰지는 일은 없습니다.
 * ⚠️ 예외 열을 두지 않습니다. 「고리 이름은 언제나 그린다」 같은 단서를 달면 그 단서가
 *    다음 화면에서 또 갈래가 됩니다. 행이 없으면 열도 없고, 그때 화면이 말하는 것은 `—` 입니다.
 */
export function visibleColumns(rows) {
  const list = Array.isArray(rows) ? rows : [];
  return COLUMNS.filter((column) => list.some((row) => row && row[column.key] !== ABSENT));
}

/** 초 — 수면 「12s」, 아니면 `—`. 단위를 부재에 붙이면 「—s」라는 없는 값이 생깁니다. */
export function secondsText(value) {
  return isCount(value) ? `${Number(value)}s` : ABSENT;
}

/** 살았나의 세 상태. `true`·`false` 만 표지이고 나머지는 전부 「모른다」입니다. */
export function aliveText(value) {
  if (value === true) return ALIVE.YES;
  if (value === false) return ALIVE.NO;
  return ALIVE.UNKNOWN;
}

/**
 * 응답 항목 하나 -> 그릴 칸들. 전부 «글자»입니다 — 그려질 것과 채점될 것이 같아야 합니다.
 *
 * ⚠️ `loop`·`process` 도 없을 수 있습니다. 그때도 빈 칸이 아니라 `—` 입니다: 표의 칸이
 *    비어 있으면 「값이 안 왔다」인지 「이 칸은 원래 없다」인지 읽는 쪽이 못 가릅니다.
 */
export function rowOf(item) {
  const entry = item || {};
  return {
    loop: entry.loop ? String(entry.loop) : ABSENT,
    process: entry.process ? String(entry.process) : ABSENT,
    alive: aliveText(entry.alive),
    // 🔴 「몇 초 전」과 「몇 초 걸렸다」는 다른 수입니다. 한 칸에 섞으면 오래 도는 고리와
    //    오래 «안» 돈 고리가 같아 보입니다.
    age: secondsText(entry.last_age_seconds),
    seconds: secondsText(entry.last_seconds),
    depth: countText(entry.depth),
    pace: countText(entry.pace),
    knob: entry.knob ? String(entry.knob) : ABSENT,
  };
}

/**
 * 응답 -> 뷰. DOM 이 없습니다.
 *
 * 🔴 「못 읽음」과 「고리가 없음」은 다른 상태입니다. 실패를 빈 배열로 접으면 화면이
 *    「도는 것이 없다」는 «거짓»을 말합니다 — 이 화면은 그 거짓을 없애려고 생겼습니다.
 * 🔴 순서는 «응답이» 정합니다. 아홉 이름을 여기 적으면 열 번째 고리가 생기는 날 그것이
 *    화면에서 «보이지 않고», 그것이 이 패널이 존재하는 이유 그 자체입니다.
 */
export function runtimeView(payload) {
  const loops = payload && Array.isArray(payload.loops) ? payload.loops : null;
  if (!loops) return { state: 'unread', rows: [], columns: [] };
  const rows = loops.map(rowOf);
  return { state: 'ready', rows, columns: visibleColumns(rows) };
}

export class RuntimePanel {
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('RuntimePanel needs a mount element');
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    if (!this.doc) throw new Error('RuntimePanel needs a document (deps.doc or mount.ownerDocument)');
    // 자기 div 하나. 남의 mount 안을 비우지 않습니다 (조립식 상설).
    this.root = this.doc.createElement('div');
    this.root.className = 'runtime-panel';
    this.mount.appendChild(this.root);
  }

  _cell(tag, text, align) {
    const el = this.doc.createElement(tag);
    el.textContent = text;
    if (align) el.style.textAlign = align;
    return el;
  }

  /** @param {object|null} payload `GET /runtime` 의 응답, 못 읽었으면 `null` */
  render(payload) {
    const view = runtimeView(payload);
    this.root.textContent = '';
    const table = this.doc.createElement('table');
    table.className = 'runtime-table';

    const thead = this.doc.createElement('thead');
    const hr = this.doc.createElement('tr');
    for (const column of view.columns) hr.appendChild(this._cell('th', column.label, column.align));
    thead.appendChild(hr);
    table.appendChild(thead);

    const tbody = this.doc.createElement('tbody');
    for (const row of view.rows) {
      const tr = this.doc.createElement('tr');
      for (const column of view.columns) {
        const td = this._cell('td', row[column.key], column.align);
        td.setAttribute('data-col', column.key);
        // 색은 «값»이 정합니다. 색이 없는 값에는 칸도 안 붙습니다 — 빈 속성은 상태 하나입니다.
        const tone = TONE[row[column.key]];
        if (tone) td.setAttribute('data-tone', tone);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    this.root.appendChild(table);

    // 🔴 못 읽었을 때 «빈 표»를 그리면 「고리가 하나도 없다」로 읽힙니다. 한 낱말로 가릅니다 —
    //    문장이 아니라 `absent.js` 의 그 글자입니다.
    if (view.state === 'unread') {
      this.root.appendChild(this._cell('div', ABSENT));
    }
    return view;
  }
}
