// LEDGER SOURCES — 「내 소스가 원장까지 갔나」를 «번역기의 장부»로 답합니다.
//
// 읽는 것: `GET /admin/ledger/sources` 의 `ingestion`. READ ONLY — 다시 돌리는 버튼도,
// 커서를 만지는 것도 여기 없습니다.
//
// ═══ 이 파일이 지키는 네 가지 ═══════════════════════════════════════════════════════
//
// ① 상태 «넷»을 접지 않습니다. `never_ran` · `ran_and_wrote` · `ran_wrote_nothing` ·
//    `orphan` 은 서버의 낱말이고 그대로 나갑니다. 「정상/경고/오류」로 접으면 네 사실이
//    셋이 되고, 무엇보다 «어느 것이 나쁜지를 서버가 말하지 않았습니다» — 화면이 그걸
//    정하면 서버가 안 한 판단을 지어내는 것입니다. 색도 아이콘도 쓰지 않는 이유입니다.
//    (같은 판정: 대기열의 `moving` · `cancel_reaches`)
//
// ② `note` 는 «표 머리의 한 줄»입니다. 지우면 이 수가 「지금 원장에 몇 개」로
//    읽힙니다 — 그래서 남습니다. 다만 단락이 아니라 «값 옆»의 한 줄이고,
//    표가 없으면 같이 없습니다 — 수가 없는데 그 수를 설명할 일이 없습니다.
//    (소유자 상설 2026-09-04: 「ui에 설명 문구 주저리주저리 금지」)
//
// ③ `unavailable` 이면 «표를 안 그립니다». 커서 표를 못 읽은 것과 「아무것도 안 돌았다」는
//    다른 사실이고, 후자로 그리면 둘이 «같은 픽셀»이 됩니다. 서버가 그때 `sources: []` 를
//    보내는 이유도 같습니다 — 「모른다」를 「없다」로 만들지 않으려고.
//
// ④ 없는 수는 `—` 입니다. 0 이 아닙니다. 철자는 `absent.js` 하나뿐입니다.
//
//
// ⑤ 거절은 «셋»입니다 — `none` · `named` · `unknowable`. 그리고 «키가 없는» 것이 넷째입니다.
//    접으면 「모른다」와 「없다」가 같은 픽셀이 됩니다. `refusals_unaccounted` 는 «부호»가
//    뜻이고(0 보통 · >0 배포 이력 · <0 장부 결함), 그래서 부호로 갈래를 텁니다.
//
// ⑥ 🔴 C-47 — 「돌 게 있나」(인구조사)는 «다른 라우트»에서 오고 «토큰이 필요 없습니다».
//    이 표는 `/admin/ledger/sources` 를 읽고, 그것은 토큰 게이트 뒤에 있습니다. 두 반쪽의
//    «가용성이 다르다»는 것이 설계입니다 — 401 이어도 인구조사는 도착하고, 그때 화면이
//    사유 하나로 비면 «가지고 있는 답»을 버립니다. 그래서 `unavailable` 에서도 census 표를
//    그립니다. 그리고 그 수를 «읽는 쪽»은 `source_backlog.js` «하나»입니다 — 탐색기
//    인스펙터가 같은 리더를 지납니다(기준 ④: 둘이 «갈라질 수» 없어야 합니다).
// ═══ 모양 ══════════════════════════════════════════════════════════════════════════
// 여섯 칸: source · state · atoms_written · molecules_done · molecules_refused · updated_at
// 🔴 일곱째 칸을 만들지 «않습니다». 좁은 패널에서 표가 넘치는 것을 546~346px 전 구간
//    0 으로 만들어 둔 라운드가 있고(2026-09-04), 칸을 하나 더하면 그 수를 도로 씁니다.
//    `translator_ver` 와 `atoms_deduped` 는 행 «안»의 보조 줄로 갑니다.
// 클래스는 자기 mount 와 deps 를 받습니다 — 한 화면에 둘을 놓아도 서로를 안 건드립니다.

import { ABSENT, countText, localeCountText } from './absent.js';

/** 서버가 쓰는 네 낱말. 화면은 이 목록을 «늘리지도 접지도» 않습니다. */
export const STATES = Object.freeze([
  'ran_and_wrote', 'ran_wrote_nothing', 'never_ran', 'orphan',
]);

/** 사유 이름은 «서버 낱말»입니다 — 번역하지 않고, «전부» 나갑니다(자르지 않습니다). */
function reasonsOf(s) {
  const r = s && s.refusal_reasons;
  if (!r || typeof r !== 'object' || Array.isArray(r)) return [];
  return Object.keys(r).map(name => Object.freeze({
    name: String(name),
    // 수가 없으면 `—` 입니다. 0 이 아닙니다 — 이 파일의 규칙 ④ 그대로입니다.
    count: countText(r[name] && typeof r[name] === 'object' ? r[name].count : undefined),
  }));
}

/** `refusals_unaccounted` 는 «부호»가 뜻입니다. 수가 아니라 부호로 갈래를 텁니다. */
function unaccountedOf(s) {
  const v = s && s.refusals_unaccounted;
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

import { backlogCells, censusRefusal } from './source_backlog.js';

/**
 * 한 소스의 «인구조사» 칸 — 대시보드 표와 탐색기 인스펙터가 «같은 리더»를 지납니다(C-47).
 *
 * 🔴 두 화면이 같은 사실을 각자 읽으면 갈라집니다. 이미 갈라져 있었습니다 — census 가
 *    인스펙터에만 있었고 이 표는 토큰이 없으면 «아무 말도» 못 했습니다.
 * ⚠️ census 는 «공개 라우트»(선언)에서 옵니다. admin 응답이 401 이어도 이 칸들은 «옵니다» —
 *    그래서 두 반쪽의 «가용성이 다릅니다», 그리고 그 사실이 행에 그대로 드러납니다.
 */
function censusOf(census) {
  const refusal = censusRefusal(census);
  return Object.freeze({
    cells: Object.freeze(backlogCells(census).map((c) => Object.freeze({ ...c }))),
    refusedReason: refusal ? refusal.reason : '',
    refusedRemedy: refusal ? refusal.remedy : '',
  });
}

/**
 * `payload` -> 그릴 것. 순수하고 총체적입니다.
 *
 * @param {object|null} payload  `/admin/ledger/sources` 의 응답, 또는 null
 * @param {{unavailable?: string}} [opts] 응답 자체를 못 얻은 이유
 * @param {object} [census] 소스 id -> `sources[].census`, «공개 선언 라우트»의 것
 */
export function sourcesView(payload, opts = {}, census = {}) {
  const censusBy = census && typeof census === 'object' ? census : {};
  // 🔴 census 는 admin 응답과 «가용성이 다릅니다» — 토큰이 없어 위가 401 이어도 여기는 옵니다.
  //    그래서 「아무것도 못 그린다」는 이제 «틀린 답»이고, 아래 두 이른 반환이 census 를 싣습니다.
  const censusRows = Object.freeze(Object.keys(censusBy).sort().map((source) => Object.freeze({
    source, ...censusOf(censusBy[source]),
  })));
  const empty = Object.freeze({
    available: false, reason: '', note: '', rows: Object.freeze([]),
    byState: Object.freeze([]), splitByState: false, count: ABSENT,
    censusRows: Object.freeze([]),
  });
  if (opts.unavailable || !payload || typeof payload !== 'object') {
    return Object.freeze({
      ...empty,
      censusRows,
      reason: opts.unavailable || '응답을 읽지 못했습니다.',
    });
  }

  const ing = payload.ingestion && typeof payload.ingestion === 'object' ? payload.ingestion : null;
  const note = ing && ing.note ? String(ing.note) : '';

  // ── 규칙 ③ ──
  if (!ing || ing.unavailable) {
    return Object.freeze({
      ...empty,
      censusRows,
      note,
      reason: ing && ing.unavailable
        ? `번역기 장부를 읽지 못했습니다 — ${String(ing.unavailable)}`
        : '응답에 ingestion 이 없습니다.',
    });
  }

  const src = Array.isArray(ing.sources) ? ing.sources : [];
  const rows = src.map(s => Object.freeze({
    source: String((s && s.source) == null ? '' : s.source),
    // C-47: 같은 리더가 읽은 인구조사. 없는 소스는 빈 칸 — 「안 쟀다」입니다.
    census: censusOf(censusBy[String((s && s.source) == null ? '' : s.source)]),
    // 규칙 ①: 서버의 낱말 그대로. 모르는 낱말이 와도 «그대로» 보여 줍니다 —
    // 화면이 아는 넷으로 «접으면» 새 상태가 조용히 사라집니다.
    state: String((s && s.state) == null ? '' : s.state),
    declared: !!(s && s.declared),
    atomsWritten: localeCountText(s && s.atoms_written),
    moleculesDone: localeCountText(s && s.molecules_done),
    moleculesRefused: localeCountText(s && s.molecules_refused),
    updatedAt: (s && s.updated_at) ? String(s.updated_at) : ABSENT,
    // 보조 줄 — 칸을 늘리지 않기 위해 행 안에 둡니다
    translatorVer: (s && s.translator_ver) ? String(s.translator_ver) : ABSENT,
    atomsDeduped: countText(s && s.atoms_deduped),
    // 🔴 셋을 접지 «않습니다». `none`(거절이 없었다) · `named`(분해가 있다) ·
    //    `unknowable`(이 행이 컬럼보다 오래됐다) 는 서로 «다른 사실»이고, 접으면
    //    「모른다」와 「없다」가 같은 픽셀이 됩니다. 그리고 «키가 아예 없는» 것이 넷째입니다 —
    //    한 번도 안 돈 소스에는 커서 행이 없어 서버가 이 셋을 싣지 않습니다.
    refusals: (s && typeof s.refusals === 'string') ? s.refusals : '',
    refusalReasons: Object.freeze(reasonsOf(s)),
    // 🔴 0 은 보통 · >0 은 «배포 이력»(컬럼이 생기기 전에 센 거절) · <0 은 «장부 결함».
    //    서버가 그 셋을 자기 주석에 그렇게 갈라 뒀으므로 화면도 «부호»로 가릅니다.
    unaccounted: unaccountedOf(s),
    unaccountedSign: (() => {
      const n = unaccountedOf(s);
      return n === null || n === 0 ? '' : n > 0 ? 'over' : 'under';
    })(),
  }));

  // 상태별 수. 서버가 준 순서가 아니라 «나온 순서»로 세되, 아는 넷을 먼저 놓습니다.
  const seen = new Map();
  for (const r of rows) seen.set(r.state, (seen.get(r.state) || 0) + 1);
  const ordered = [...STATES.filter(s => seen.has(s)), ...[...seen.keys()].filter(s => !STATES.includes(s))];
  const byState = ordered.map(state => Object.freeze({ state, count: countText(seen.get(state)) }));

  return Object.freeze({
    available: true,
    reason: '',
    censusRows,
    note,
    rows: Object.freeze(rows),
    byState: Object.freeze(byState),
    // 🔴 상태가 «하나»뿐이면 나누지 않습니다 — 나눌 것이 없는데 나누면 머리 줄이
    //    표의 행 수를 두 번 말하게 됩니다. (대기열의 소유자 띠와 같은 규칙)
    splitByState: byState.length > 1,
    count: countText(rows.length),
  });
}

/**
 * @param {HTMLElement} mount
 * @param {{doc?: Document}} [deps]
 */
export class LedgerSourcesPanel {
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('LedgerSourcesPanel needs a mount element');
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    if (!this.doc) throw new Error('LedgerSourcesPanel needs a document (deps.doc or mount.ownerDocument)');
    this.root = this.doc.createElement('div');
    this.root.className = 'ledger-sources-panel';
    this.mount.appendChild(this.root);
  }

  _line(cls, text) {
    const el = this.doc.createElement('div');
    el.className = cls;
    el.textContent = text;
    return el;
  }

  _td(text, align) {
    const td = this.doc.createElement('td');
    td.textContent = text;
    if (align) td.style.textAlign = align;
    return td;
  }

  /**
   * 인구조사 줄 — 「표에 N 행 · 색인 M · 남음 K」, 또는 «셀 수 없다는 사유».
   *
   * 🔴 두 자리가 «같은 픽셀»을 지납니다: 표가 그려질 때는 소스 칸 안의 보조 줄로, admin 이
   *    401 일 때는 census 만의 표로. 각자 그리면 한쪽만 고쳐지는 날 두 화면이 갈라집니다.
   * 🔴 라벨은 «서버의 키 그대로»입니다(판정 177). 옮기면 서버가 키를 바꾸는 날 화면이
   *    «옛 이름으로» 옳아 보입니다.
   * ⚠️ 방법(`count(*)` · `pg_class.reltuples`)은 «툴팁»입니다 — 좁은 패널에서 칸도 줄도
   *    늘리지 않기 위해서이고, 「추정이다」라는 것만 값 옆의 `≈` 로 보입니다.
   */
  _censusLines(census) {
    const out = [];
    if (!census) return out;
    // 🔴 거절이 «먼저»입니다. 셀 수 없다는 것은 조작자가 «고칠 수 있는» 사실이고, 수 아래
    //    묻히면 「아직 안 돌았나 보다」로 읽힙니다. 고칠 문장은 문지기의 것 그대로(S-39).
    if (census.refusedReason) {
      const line = this._line('ledger-sources-census-refused', census.refusedReason);
      line.setAttribute('data-refused', census.refusedReason);
      if (census.refusedRemedy) line.title = census.refusedRemedy;
      out.push(line);
    }
    const drawn = (census.cells || []).filter((c) => c.text !== '');
    if (drawn.length) {
      const line = this._line('ledger-sources-census',
        drawn.map((c) => `${c.name} ${c.text}`).join(' · '));
      const methods = drawn.filter((c) => c.method).map((c) => `${c.name}: ${c.method}`);
      if (methods.length) line.title = methods.join('\n');
      out.push(line);
    }
    return out;
  }

  /** 소스 이름 칸 — 보조 줄과 인구조사가 «여기» 삽니다. 일곱째 칸을 만들지 않습니다. */
  _nameCell(source, census, sub) {
    const td = this.doc.createElement('td');
    td.appendChild(this._line('ledger-sources-name', source));
    if (sub) td.appendChild(this._line('ledger-sources-sub', sub));
    for (const line of this._censusLines(census)) td.appendChild(line);
    return td;
  }

  /**
   * admin 응답이 «없을 때»의 표 — 인구조사만.
   *
   * 🔴 census 는 «공개 선언 라우트»에서 옵니다. 토큰이 없어 위가 401 이어도 이 수들은
   *    도착합니다 — 그때 「아무것도 못 그린다」로 두면 «가지고 있는 답»을 버리는 것입니다.
   */
  _censusTable(rows) {
    const doc = this.doc;
    const table = doc.createElement('table');
    table.className = 'table-container ledger-sources-census-table';
    const tbody = doc.createElement('tbody');
    for (const r of rows) {
      const tr = doc.createElement('tr');
      tr.className = 'table-row';
      tr.setAttribute('data-source', r.source);
      tr.appendChild(this._nameCell(r.source, r, ''));
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    return table;
  }

  _empty(icon, text) {
    const box = this.doc.createElement('div');
    box.className = 'empty-state';
    const ic = this.doc.createElement('div');
    ic.className = 'empty-icon';
    ic.textContent = icon;
    box.appendChild(ic);
    box.appendChild(this._line('empty-text', text));
    return box;
  }

  /**
   * @param {object|null} payload @param {{unavailable?: string}} [opts]
   * @param {object} [census] 소스 id -> `sources[].census`, «공개 선언 라우트»의 것
   */
  render(payload, opts = {}, census = {}) {
    const view = sourcesView(payload, opts, census);
    const doc = this.doc;
    this.root.textContent = '';

    if (!view.available) {
      this.root.appendChild(this._empty('⚪', view.reason));
      // 🔴 두 반쪽의 «가용성이 다릅니다». 장부는 토큰이 필요하고 인구조사는 아닙니다 —
      //    그래서 사유 하나로 화면을 비우면 «도착한 답»까지 같이 지웁니다.
      if (view.censusRows.length) this.root.appendChild(this._censusTable(view.censusRows));
      return view;
    }

    if (view.splitByState) {
      const strip = doc.createElement('div');
      strip.className = 'ledger-sources-states';
      for (const s of view.byState) {
        const line = this._line('ledger-sources-state', `${s.state} · ${s.count}`);
        line.setAttribute('data-state', s.state);
        strip.appendChild(line);
      }
      this.root.appendChild(strip);
    }

    if (view.rows.length === 0) {
      this.root.appendChild(this._empty('⚪', '선언된 소스도 장부의 행도 없습니다.'));
      return view;
    }

    const table = doc.createElement('table');
    table.className = 'table-container';
    // 규칙 ② — 표 머리의 한 줄. 수가 그려질 때만 나옵니다.
    if (view.note) {
      const cap = doc.createElement('caption');
      cap.className = 'ledger-sources-note';
      cap.textContent = view.note;
      table.appendChild(cap);
    }
    const thead = doc.createElement('thead');
    thead.className = 'table-header';
    const hr = doc.createElement('tr');
    for (const [label, width, align] of [
      ['Source', '150px', ''], ['State', '130px', ''], ['원자', '80px', 'center'],
      ['분자', '80px', 'center'], ['거절', '70px', 'center'], ['마지막', '', ''],
    ]) {
      const th = doc.createElement('th');
      th.textContent = label;
      if (width) th.style.width = width;
      if (align) th.style.textAlign = align;
      hr.appendChild(th);
    }
    thead.appendChild(hr);
    table.appendChild(thead);

    const tbody = doc.createElement('tbody');
    for (const r of view.rows) {
      const tr = doc.createElement('tr');
      tr.className = 'table-row';
      tr.setAttribute('data-source', r.source);
      tr.setAttribute('data-state', r.state);

      // 보조 줄과 인구조사가 이름 칸 «안»에 삽니다 — 일곱째 칸 대신입니다
      tr.appendChild(this._nameCell(r.source, r.census,
        `translator_ver ${r.translatorVer} · atoms_deduped ${r.atomsDeduped}`));

      // 🔴 서버의 낱말 그대로. `data-state` 로 나가지만 «색은 없습니다».
      tr.appendChild(this._td(r.state));
      tr.appendChild(this._td(r.atomsWritten, 'center'));
      tr.appendChild(this._td(r.moleculesDone, 'center'));
      // 🔴 「몇 개」 옆에 「무슨 사유로 몇 개」. 수만 있으면 운영자가 수까지 가고 멈춥니다.
      //    ⚠️ 칸을 «늘리지 않습니다» — 같은 칸 안에서 줄로 쌓입니다.
      const tdRefused = this._td(r.moleculesRefused, 'center');
      for (const reason of r.refusalReasons) {
        const line = this._line('ledger-sources-reason', `${reason.name} · ${reason.count}`);
        line.setAttribute('data-reason', reason.name);
        tdRefused.appendChild(line);
      }
      // 🔴 `unknowable` 은 «수를 안 그립니다». 분해가 «불가능»한 것이지 0 이 아닙니다.
      //    서버의 낱말을 그대로 둡니다 — 화면이 이 상태에 다른 이름을 붙이지 않습니다.
      if (r.refusals === 'unknowable') {
        const line = this._line('ledger-sources-reason', 'unknowable');
        line.setAttribute('data-refusals', 'unknowable');
        tdRefused.appendChild(line);
      }
      // 🔴 부호가 다르면 «픽셀도 다릅니다». <0 은 장부 결함이고, 배포 이력과 같아 보이면
      //    안 됩니다. ⛔ 그 뜻을 «문장으로» 적지 않습니다 (소유자 상설 2026-09-04).
      if (r.unaccountedSign) {
        const line = this._line('ledger-sources-unaccounted',
          `unaccounted ${r.unaccounted > 0 ? '+' : ''}${r.unaccounted}`);
        line.setAttribute('data-sign', r.unaccountedSign);
        tdRefused.appendChild(line);
      }
      tr.appendChild(tdRefused);
      tr.appendChild(this._td(r.updatedAt));

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    this.root.appendChild(table);
    return view;
  }
}
