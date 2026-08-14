// ============================================================
// lot_reference_view.js — 랏 참조뷰(화면 ②)의 DOM
//
// FOUR SECTIONS, AND THEY ARE THE INFERENCE ORDER (brief §화면 구성):
//   ① 헤더        랏 · 버킷 · 요약 숫자 · 구조 뷰 링크
//   ② 혈통 요약    걷기 산출 + 경로 특이점 뱃지 + 홉 basis·관례 표시
//   ③ 차이점 순위표 v1  범주 + 결측 부류, 관문 열은 「실재✓ · 상류 — · 기전 —」
//   ④ 조사 이력    이 랏의 액션과 답 — 비어 있는 것이 오늘의 정상
//
// 🔴 THIS FILE NEVER TOUCHES `window`; `doc` is passed in. Scored under bare node
// by `client2/tests/lot_reference_harness.mjs`.
//
// 🔴 READ-ONLY. Not one control on this screen writes anything — the action bar
// is R6 and it is not here yet, and the screen says so rather than showing a
// button that does nothing.
// ============================================================

import {
  GATE_PASS, GATE_FAIL, lotQuery,
} from './lot_reference_core.js';
// 🔴 THE HOP RENDERER THE CONSOLE ALREADY USES — which is where `basis` is
// painted from the FIELD (가정 · <name> vs 근거 · <name>), where a continuity
// break is shown rather than bridged, and where a quantity renders as a pair.
// A second hop renderer here would let the same wire paint two ways.
import { renderTransferHop, renderRate, countText } from './case_control_view.js';

function el(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function clear(mount) {
  while (mount.firstChild) mount.removeChild(mount.firstChild);
}

/** A section shell — every panel on this screen is one, including the empty ones. */
function panel(doc, key, title, subtitle) {
  const box = el(doc, 'section', 'lr-panel');
  box.setAttribute('data-panel', key);
  const head = el(doc, 'div', 'lr-panel__head');
  head.appendChild(el(doc, 'h2', 'lr-panel__title', title));
  if (subtitle) head.appendChild(el(doc, 'span', 'lr-panel__sub', subtitle));
  box.appendChild(head);
  return box;
}

/**
 * 「서버가 말하지 않았다」 — the honest degradation, as CONTENT.
 *
 * 🔴 NOT AN ERROR BOX AND NOT A HIDDEN SECTION. Every one of these is a real
 * statement about what the machine can and cannot yet answer, and it is the
 * sentence that keeps a not-yet-deployed axis from reading as a clean result.
 */
function gapNote(doc, key, title, why) {
  const box = el(doc, 'div', 'lr-gap');
  box.setAttribute('data-gap', key);
  box.appendChild(el(doc, 'span', 'lr-gap__title', title));
  if (why) box.appendChild(el(doc, 'p', 'lr-gap__why', why));
  return box;
}

// ── ① 헤더 ───────────────────────────────────────────────────

/**
 * 🔴 THE GRAPH LINK POINTS AT `?view=structure`, THE TYPE MAP ON THIS PAGE — NOT
 * AT `graph.html`.
 *
 * The old graph branch is RETIRED (판정 R-2026-08-14-H): `/graph/stats`,
 * `/graph/neighbors`, `/graph/nodes/search`, `/graph/trace` and `/chip/trace` all
 * raise a refusal, so `graph.html` is a screen that can only fail. What survives
 * is the ledger's own generated structure view — declaration + aggregate, no
 * copy of the data — and that is what an operator following 「구조를 보고 싶다」
 * from here must land on.
 */
function renderStructureLink(doc) {
  const a = el(doc, 'a', 'lr-head__link', '구조 뷰 →');
  a.setAttribute('href', '?view=structure');
  a.setAttribute('data-structure-link', '1');
  return a;
}

function renderHeader(doc, model) {
  const box = el(doc, 'header', 'lr-head');
  box.setAttribute('data-panel', 'header');

  const line = el(doc, 'div', 'lr-head__line');
  const id = el(doc, 'span', 'lr-head__lot', model.identity.id || '랏 미지정');
  id.setAttribute('data-lot', model.identity.id || '');
  line.appendChild(id);
  if (model.identity.slot) {
    const s = el(doc, 'span', 'lr-head__slot', `슬롯 ${model.identity.slot}`);
    s.setAttribute('data-slot', model.identity.slot);
    line.appendChild(s);
  }

  // 🔴 THE BUCKET IS NOT DECORATION. A special-evaluation lot compared against a
  // production baseline is a wrong answer, and 「버킷 미보고」 is how the reader
  // learns the server has not classified it — never a silent 「양산」.
  if (model.identity.bucketDeclared) {
    const b = el(doc, 'span', `lr-bucket lr-bucket--${model.identity.bucketId || 'unknown'}`,
      model.identity.bucketText);
    b.setAttribute('data-bucket', model.identity.bucketId || 'unknown');
    line.appendChild(b);
    if (model.identity.baselineDeclared && !model.identity.countsTowardBaseline) {
      const off = el(doc, 'span', 'lr-bucket__off', '기저 제외');
      off.setAttribute('data-baseline', '0');
      line.appendChild(off);
    }
  } else {
    const b = el(doc, 'span', 'lr-bucket lr-bucket--absent', '버킷 미보고');
    b.setAttribute('data-bucket', '');
    line.appendChild(b);
  }

  if (model.kind) {
    const k = el(doc, 'span', 'lr-head__kind', model.kind);
    k.setAttribute('data-kind', model.kind);
    line.appendChild(k);
  }
  line.appendChild(renderStructureLink(doc));
  box.appendChild(line);

  // 🔴 THE SERVER ANSWERED ABOUT A DIFFERENT LOT THAN THE URL ASKED. Cheap to
  // check, and the alternative is a screen confidently describing the wrong wafer.
  if (model.identity.asked && model.identity.id && model.identity.asked !== model.identity.id) {
    const warn = el(doc, 'p', 'lr-head__mismatch',
      `URL은 ${model.identity.asked}를 물었고 응답은 ${model.identity.id}를 답했습니다`);
    warn.setAttribute('data-lot-mismatch', '1');
    box.appendChild(warn);
  }

  // 요약 숫자 — 전부 분모와 함께. 분모 없는 숫자는 이 화면을 못 떠난다.
  if (model.summary.declared && model.summary.rows.length) {
    const stats = el(doc, 'div', 'lr-stats');
    stats.setAttribute('data-summary', String(model.summary.rows.length));
    for (const row of model.summary.rows) {
      const cell = el(doc, 'div', 'lr-stat');
      cell.setAttribute('data-stat', row.key);
      cell.appendChild(el(doc, 'span', 'lr-stat__term', row.term));
      cell.appendChild(renderRate(doc, row.reading));
      if (row.note) cell.appendChild(el(doc, 'span', 'lr-stat__note', row.note));
      stats.appendChild(cell);
    }
    box.appendChild(stats);
  } else if (model.answered) {
    box.appendChild(gapNote(doc, 'summary', '요약 숫자 미보고',
      '응답에 summary 없음 — 이 랏의 발생/분모를 서버가 싣지 않았습니다'));
  }

  // 귀속 커버리지 — R1의 의무 필드. 없으면 「완전 귀속」이 아니라 「미보고」다.
  box.appendChild(renderCoverage(doc, model));

  const meta = [];
  if (model.generatedAt) meta.push(`집계 ${model.generatedAt}`);
  if (model.state !== 'unknown') meta.push(`상태 ${model.state}`);
  if (meta.length) box.appendChild(el(doc, 'div', 'lr-head__meta', meta.join('  ·  ')));
  return box;
}

function renderCoverage(doc, model) {
  const box = el(doc, 'div', 'lr-cov');
  box.setAttribute('data-coverage', model.coverage.declared ? '1' : '0');
  if (!model.coverage.declared) {
    if (!model.answered) return box;
    box.appendChild(gapNote(doc, 'coverage', '귀속 커버리지 미보고',
      '몇 건 중 몇 건이 귀속됐는지 응답에 없음 — 아래 순위표가 전수를 본 것인지 알 수 없습니다'));
    return box;
  }
  box.appendChild(el(doc, 'span', 'lr-cov__term', '귀속 커버리지'));
  if (model.coverage.overall) {
    const all = el(doc, 'span', 'lr-cov__all');
    all.setAttribute('data-coverage-axis', '*');
    all.appendChild(renderRate(doc, model.coverage.overall));
    box.appendChild(all);
  }
  for (const row of model.coverage.rows) {
    const cell = el(doc, 'span', 'lr-cov__axis');
    cell.setAttribute('data-coverage-axis', row.axis);
    cell.appendChild(el(doc, 'span', 'lr-cov__axisterm', row.term));
    cell.appendChild(renderRate(doc, row.reading));
    box.appendChild(cell);
  }
  return box;
}

// ── ② 혈통 요약 ──────────────────────────────────────────────

function renderAnomalies(doc, anomalies) {
  const box = el(doc, 'div', 'lr-anom');
  box.setAttribute('data-anomalies', anomalies.declared ? String(anomalies.items.length) : '');
  if (!anomalies.declared) {
    // 🔴 「특이점 없음」 이라고 쓰지 않는다. 서버가 안 본 것과 보고 못 찾은 것은
    // 다른 사실이고, 전자를 후자로 그리면 없는 무해함을 만들어낸다.
    // 🔴 예시조차 쓰지 않는다. 어떤 특징이 특이점인지는 «선언»이고, 여기에 예를
    // 적어 두면 그 둘이 목록처럼 읽혀 선언이 클라로 새어 나온 것과 같아진다.
    box.appendChild(gapNote(doc, 'anomalies', '경로 특이점 판정 미착지',
      '응답에 anomalies 없음 — 경로 특징 추출기(R7)가 아직 없습니다'));
    return box;
  }
  if (!anomalies.items.length) {
    const none = el(doc, 'p', 'lr-anom__none', '경로 특이점 없음 — 서버가 보고 찾지 못했습니다');
    none.setAttribute('data-anomaly-none', '1');
    box.appendChild(none);
    return box;
  }
  for (const a of anomalies.items) {
    const chip = el(doc, 'span', `lr-anom__badge lr-anom__badge--${a.severity || 'plain'}`);
    chip.setAttribute('data-anomaly', a.code);
    if (a.severity) chip.setAttribute('data-anomaly-severity', a.severity);
    chip.appendChild(el(doc, 'span', 'lr-anom__label', a.label));
    if (a.detail) chip.appendChild(el(doc, 'span', 'lr-anom__detail', a.detail));
    box.appendChild(chip);
  }
  return box;
}

function renderLineage(doc, model) {
  const box = panel(doc, 'lineage', '혈통 요약', '이 랏이 어디서 왔나');
  const chain = model.lineage;

  box.appendChild(renderAnomalies(doc, chain.anomalies));

  if (!chain.present) {
    box.appendChild(gapNote(doc, 'lineage', '혈통 걷기 없음',
      model.answered
        ? '응답에 lineage 없음 — 걸은 사슬이 실리지 않았습니다'
        : '아직 답이 오지 않았습니다'));
    return box;
  }

  if (chain.subject) {
    const s = el(doc, 'div', 'lr-lineage__subject', chain.subject);
    s.setAttribute('data-lineage-subject', chain.subject);
    box.appendChild(s);
  }

  const body = el(doc, 'div', 'lr-lineage__body');
  body.setAttribute('data-lineage-body', '1');
  if (!chain.hops.length) {
    body.appendChild(el(doc, 'p', 'lr-empty', '이송 원자 0건 — 걸을 사슬 없음'));
  } else {
    const list = el(doc, 'ol', 'cc-hops');
    // 🔴 홉 수는 고정이 아니다. DT를 두 번 거친 웨이퍼는 홉이 더 많고, 여기에
    // 고정 단계를 인덱싱하는 코드가 있으면 그 줄이 결함이다.
    chain.hops.forEach((hop, i) => list.appendChild(renderTransferHop(doc, hop, i + 1)));
    body.appendChild(list);
  }
  box.appendChild(body);

  const foot = el(doc, 'div', 'lr-lineage__foot');
  foot.setAttribute('data-lineage-hops', String(chain.hops.length));
  foot.setAttribute('data-lineage-stops', String(chain.stops));
  foot.setAttribute('data-lineage-breaks', String(chain.breaks));
  foot.textContent = `홉 ${countText(chain.hops.length)} · 경유 ${countText(chain.stops)}`
    + (chain.breaks ? ` · 끊김 ${countText(chain.breaks)}` : '');
  box.appendChild(foot);

  if (chain.terminal) {
    const term = el(doc, 'p', 'lr-lineage__terminal', chain.terminal);
    term.setAttribute('data-lineage-terminal', chain.terminal);
    box.appendChild(term);
  }
  return box;
}

// ── ③ 차이점 순위표 v1 ───────────────────────────────────────

//: 🔴 THREE WORDS, AND THE THIRD IS NOT A SOFTER SECOND. 미판정 is the state that
//: PRODUCES work (실재✓·상류✓·기전 미판정 = DOE 후보); 불통과 is a rejected
//: explanation. They share no colour, no glyph and no shape here, which is the
//: whole point of the column.
const GATE_TEXT = {
  [GATE_PASS]: { glyph: '✓', word: '통과' },
  [GATE_FAIL]: { glyph: '✗', word: '불통과' },
};
const GATE_UNJUDGED = { glyph: '—', word: '미판정' };

function renderGateCell(doc, cell) {
  const box = el(doc, 'span', `lr-gate lr-gate--${cell.state}`);
  // 🔴 THE ROW'S OWN ATTRIBUTE NAME. The legend below uses `data-legend-gate`
  // deliberately: a legend sharing this attribute would make any "sweep the tree
  // for a passing gate" assertion pass even with every row deleted.
  box.setAttribute('data-gate', cell.id);
  box.setAttribute('data-gate-state', cell.state);
  const face = GATE_TEXT[cell.state] || GATE_UNJUDGED;
  box.appendChild(el(doc, 'span', 'lr-gate__glyph', face.glyph));
  box.appendChild(el(doc, 'span', 'lr-gate__word', face.word));
  // 편향 후보 — 기전 관문이 observation_bias 모델에만 닿았을 때 서버가 다는 표시.
  // 통과를 원인으로 승격시키지 않는다 (R3).
  if (cell.flag) {
    const f = el(doc, 'span', 'lr-gate__flag', cell.flag);
    f.setAttribute('data-gate-flag', cell.flag);
    box.appendChild(f);
  }
  if (cell.reason) box.setAttribute('title', cell.reason);
  return box;
}

function renderGateLegend(doc, gates) {
  const box = el(doc, 'div', 'lr-legend');
  box.setAttribute('data-legend', '1');
  box.appendChild(el(doc, 'span', 'lr-legend__term', '관문 읽는 법'));
  const say = (state, text) => {
    const item = el(doc, 'span', `lr-legend__item lr-legend__item--${state}`);
    // NOT `data-gate-state` — see `renderGateCell`.
    item.setAttribute('data-legend-gate', state);
    const face = GATE_TEXT[state] || GATE_UNJUDGED;
    item.appendChild(el(doc, 'span', 'lr-legend__glyph', face.glyph));
    item.appendChild(el(doc, 'span', 'lr-legend__text', text));
    box.appendChild(item);
  };
  say(GATE_PASS, '통과 — 이 관문을 넘었습니다');
  say(GATE_FAIL, '불통과 — 판정했고 넘지 못했습니다');
  say('unknown', '미판정 — 아직 «판정하지 못했습니다». 불통과가 아닙니다');
  if (!gates.declared) {
    box.appendChild(el(doc, 'span', 'lr-legend__note',
      '관문 축 미선언 — 기본 세 관문으로 표시 중'));
  }
  return box;
}

function renderRankRow(doc, row) {
  const tr = el(doc, 'tr', `lr-row${row.family.gap ? ' lr-row--gap' : ''}`);
  tr.setAttribute('data-rank-row', row.key);

  const name = el(doc, 'td', 'lr-cell lr-cell--name');
  const box = el(doc, 'div', 'lr-factor');
  if (row.term) box.appendChild(el(doc, 'span', 'lr-factor__term', row.term));
  box.appendChild(el(doc, 'span', 'lr-factor__key', row.label));
  if (row.family.declared) {
    // 🔴 결측 부류는 빨강 — 「답이 아니라 구멍」. `gap` 은 서버의 플래그이지 이
    // 파일이 알아보는 낱말이 아니다.
    const f = el(doc, 'span', `lr-family${row.family.gap ? ' lr-family--gap' : ''}`, row.family.label);
    f.setAttribute('data-family', row.family.id);
    if (row.family.gap) f.setAttribute('data-family-gap', '1');
    box.appendChild(f);
  }
  if (row.about) {
    const a = el(doc, 'span', `lr-about lr-about--${row.about}`, row.about === 'process' ? '공정' : (row.about === 'inspection' ? '검사' : row.about));
    a.setAttribute('data-about', row.about);
    box.appendChild(a);
  }
  name.appendChild(box);
  tr.appendChild(name);

  const found = el(doc, 'td', 'lr-cell lr-cell--side');
  found.setAttribute('data-side', 'found');
  found.appendChild(renderRate(doc, row.inFound));
  tr.appendChild(found);

  const clean = el(doc, 'td', 'lr-cell lr-cell--side');
  clean.setAttribute('data-side', 'clean');
  clean.appendChild(renderRate(doc, row.inClean));
  tr.appendChild(clean);

  for (const cell of row.gates.cells) {
    const td = el(doc, 'td', 'lr-cell lr-cell--gate');
    td.appendChild(renderGateCell(doc, cell));
    tr.appendChild(td);
  }

  if (row.reason) {
    const why = el(doc, 'tr', 'lr-row__why');
    why.setAttribute('data-rank-why', row.key);
    const td = el(doc, 'td', 'lr-cell lr-cell--why', row.reason);
    td.setAttribute('colspan', String(3 + row.gates.cells.length));
    why.appendChild(td);
    return [tr, why];
  }
  return [tr];
}

function renderRank(doc, model) {
  const box = panel(doc, 'rank', '차이점 순위표', '설명력 순 — 서버가 매긴 순서');
  box.appendChild(renderGateLegend(doc, model.gates));

  if (!model.rank.declared) {
    box.appendChild(gapNote(doc, 'rank', '대조 결과 미착지',
      model.answered
        ? '응답에 factors 없음 — 랏 스코프 대조(R1)가 아직 이 랏을 답하지 않습니다'
        : '아직 답이 오지 않았습니다'));
    return box;
  }
  if (!model.rank.rows.length) {
    const none = el(doc, 'p', 'lr-empty', '차이 0건 — 케이스와 대조군에서 갈리는 요인을 찾지 못했습니다');
    none.setAttribute('data-rank-none', '1');
    box.appendChild(none);
    return box;
  }

  const table = el(doc, 'table', 'lr-table');
  const thead = el(doc, 'thead');
  const hr = el(doc, 'tr');
  hr.appendChild(el(doc, 'th', 'lr-th lr-th--name', '요인'));
  hr.appendChild(el(doc, 'th', 'lr-th', '난 쪽'));
  hr.appendChild(el(doc, 'th', 'lr-th', '안 난 쪽'));
  for (const gate of model.gates.gates) {
    const th = el(doc, 'th', 'lr-th lr-th--gate', gate.label);
    th.setAttribute('data-gate-col', gate.id);
    hr.appendChild(th);
  }
  thead.appendChild(hr);
  table.appendChild(thead);

  // 🔴 THE ROWS LIVE IN THEIR OWN CONTAINER, and every assertion about a gate
  // verdict is scoped to it. A sweep of the whole tree would also find the
  // legend — and would stay green with every row removed.
  const tbody = el(doc, 'tbody', 'lr-tbody');
  tbody.setAttribute('data-rank-body', String(model.rank.rows.length));
  for (const row of model.rank.rows) {
    for (const node of renderRankRow(doc, row)) tbody.appendChild(node);
  }
  table.appendChild(tbody);
  box.appendChild(table);

  const unjudged = model.rank.rows.filter((r) => r.gates.judged < r.gates.of).length;
  if (unjudged) {
    const note = el(doc, 'p', 'lr-note',
      `${countText(unjudged)}/${countText(model.rank.rows.length)}행에 미판정 관문이 있습니다 — 상류·기전 판정은 R3에서 붙습니다`);
    note.setAttribute('data-unjudged', String(unjudged));
    note.setAttribute('data-unjudged-of', String(model.rank.rows.length));
    box.appendChild(note);
  }
  return box;
}

// ── ④ 조사 이력 ──────────────────────────────────────────────

/**
 * 🔴 THIS PANEL IS NEVER HIDDEN AND NEVER EMPTY OF WORDS.
 *
 * Today it has no rows on any lot, because the write axis (R6) has not landed.
 * A section that disappears when it has nothing teaches the operator it does not
 * exist — and the reason it exists is 「같은 질문 두 번 사지 않기」, which only
 * works if the reader knows to look here BEFORE issuing one.
 */
function renderInvestigations(doc, model) {
  const box = panel(doc, 'investigations', '조사 이력', '이 랏에 이미 물어본 질문과 그 답');

  if (!model.investigations.items.length) {
    const none = el(doc, 'p', 'lr-none', '발급된 질문 없음');
    none.setAttribute('data-investigations', '0');
    box.appendChild(none);
    box.appendChild(el(doc, 'p', 'lr-none__why',
      model.investigations.declared
        ? '이 랏에 발급된 수집 요청이 없습니다'
        : '수집 요청 축(R6) 미착지 — 어느 랏에도 아직 발급된 질문이 없습니다'));
    return box;
  }

  const list = el(doc, 'ol', 'lr-log');
  list.setAttribute('data-investigations', String(model.investigations.items.length));
  for (const item of model.investigations.items) {
    const li = el(doc, 'li', `lr-log__item lr-log__item--${item.state || 'unknown'}`);
    li.setAttribute('data-request', item.id || '');
    if (item.state) li.setAttribute('data-request-state', item.state);

    const head = el(doc, 'div', 'lr-log__head');
    if (item.kindLabel) head.appendChild(el(doc, 'span', 'lr-log__kind', item.kindLabel));
    if (item.stateLabel) head.appendChild(el(doc, 'span', 'lr-log__state', item.stateLabel));
    if (item.openedAt) head.appendChild(el(doc, 'span', 'lr-log__at', item.openedAt));
    li.appendChild(head);

    if (item.question) li.appendChild(el(doc, 'p', 'lr-log__q', item.question));

    // 🔴 답이 없는 것은 답이 「없음」이 아니라 아직 «안 온» 것이다. 두 문장이 다르다.
    if (item.answer) {
      const a = el(doc, 'p', 'lr-log__a', item.answer);
      a.setAttribute('data-answer', '1');
      li.appendChild(a);
      if (item.answeredAt) li.appendChild(el(doc, 'span', 'lr-log__at', item.answeredAt));
    } else {
      const a = el(doc, 'p', 'lr-log__a lr-log__a--open', '답 미도착');
      a.setAttribute('data-answer', '0');
      li.appendChild(a);
    }

    if (item.reissueOf) {
      const r = el(doc, 'span', 'lr-log__reissue', `재발행 — 원 질문 ${item.reissueOf}`);
      r.setAttribute('data-reissue-of', item.reissueOf);
      li.appendChild(r);
    }
    list.appendChild(li);
  }
  box.appendChild(list);
  return box;
}

// ── the action bar's absence, said out loud ─────────────────

function renderActionGap(doc) {
  const box = panel(doc, 'actions', '액션', '설명이 안 서는 지점에서 다음 수집을 요청');
  box.appendChild(gapNote(doc, 'actions', '수집 요청 미착지',
    '발급 버튼은 R6에서 붙습니다 — 지금 이 화면은 읽기 전용이고, 아무것도 원장에 쓰지 않습니다'));
  return box;
}

// ── notices ──────────────────────────────────────────────────

export function renderLotNotice(doc, mount, notice) {
  if (!notice) return;
  const box = el(doc, 'div', `lr-notice lr-notice--${notice.tone || 'info'}`);
  box.setAttribute('data-notice', notice.tone || 'info');
  box.appendChild(el(doc, 'span', 'lr-notice__title', notice.title || ''));
  if (notice.detail) box.appendChild(el(doc, 'p', 'lr-notice__detail', notice.detail));
  mount.appendChild(box);
}

// ── the whole view ───────────────────────────────────────────

/**
 * Render the reference view into `mount`.
 *
 * 🔴 EVERY SECTION RENDERS ON EVERY PATH, INCLUDING THE ONES WITH NO DATA. The
 * screen's shape is the argument it makes — 혈통 → 차이 → 이력 → 액션 is the
 * inference order — and a version that drops the empty sections would be a
 * different argument depending on the day's deployment.
 */
export function renderLotReference(doc, mount, model, notice) {
  clear(mount);
  const root = el(doc, 'div', 'lr');
  root.setAttribute('data-view', 'lot');

  if (!model.asked) {
    // 랏 없는 참조뷰는 오류가 아니라 «질문이 아직 없는 상태»다.
    root.appendChild(gapNote(doc, 'no-lot', '랏이 지정되지 않았습니다',
      '주소에 lot이 없습니다 — 트렌드 화면에서 랏을 열거나 위 입력란에 랏을 넣으십시오'));
    const back = el(doc, 'a', 'lr-head__link', '← 트렌드로');
    back.setAttribute('href', '?view=surprise');
    root.appendChild(back);
    mount.appendChild(root);
    return;
  }

  renderLotNotice(doc, root, notice);
  root.appendChild(renderHeader(doc, model));
  root.appendChild(renderLineage(doc, model));
  root.appendChild(renderRank(doc, model));
  root.appendChild(renderInvestigations(doc, model));
  root.appendChild(renderActionGap(doc));

  // 이 랏의 혈통 상세로 — 같은 페이지의 조사 뷰. 링크지 임베드가 아니다.
  const foot = el(doc, 'div', 'lr-foot');
  const trace = el(doc, 'a', 'lr-head__link', '이 랏의 혈통 상세 →');
  trace.setAttribute('href', `?lot=${encodeURIComponent(model.identity.id || model.question.lot)}`);
  trace.setAttribute('data-trace-link', '1');
  foot.appendChild(trace);
  const back = el(doc, 'a', 'lr-head__link', '← 트렌드로');
  back.setAttribute('href', '?view=surprise');
  foot.appendChild(back);
  // 이 뷰 자신의 주소 — 복사해 넘길 수 있는 그 링크.
  const self = el(doc, 'a', 'lr-foot__self', `?${lotQuery(model.question)}`);
  self.setAttribute('href', `?${lotQuery(model.question)}`);
  self.setAttribute('data-self-link', '1');
  foot.appendChild(self);
  root.appendChild(foot);

  mount.appendChild(root);
}
