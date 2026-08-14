// ============================================================
// case_control_view.js — the case-control console as DOM.
//
// `document` IS AN ARGUMENT, not a global — same contract as
// `ledger_trace_view.js`, so `tests/case_control_harness.mjs` drives the REAL
// renderer under bare node and asserts what reaches the screen. Everything here
// builds nodes and sets `textContent`; nothing touches `innerHTML`, so a lot id
// or an operator's note out of the ledger can never become markup.
//
// 🔴 NO FORM CONTROLS. Not one `<select>`, not one `<input>`, not one modal.
// Every navigation on this console is an ANCHOR, because this screen's answer is
// a URL: picking a kind, adding a slice and removing a slice are all links, so
// middle-click, copy-link, the back button and pasting a finding into a message
// all work with no state to serve them. That is also why the console costs the
// page zero controls — `ledger.html` still carries exactly one input, the
// lineage box it always had.
//
// 🔴 AND NO NUMBER SHIPS WITHOUT ITS DENOMINATOR. `rateReading` in the core
// cannot produce a percentage without one; this file cannot print one either —
// every rate goes through `renderRate`, which renders the refusal when the core
// returns one. There is no path from a raw count to a "%" on this screen.
// ============================================================

import {
  SLICE_PARAMS, consoleQuery, withSlice, axisTerm, percentText,
} from './case_control_core.js';

function el(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function clear(mount) {
  while (mount.firstChild) mount.removeChild(mount.firstChild);
}

/**
 * An integer, grouped, WITHOUT touching the locale.
 *
 * 🔴 NEVER `toLocaleString`. The lineage screen already paid for locale-dependent
 * rendering once (instants moving with whoever's laptop was open); a count that
 * groups differently per machine is the same defect with a smaller blast radius,
 * and it makes a screenshot unquotable.
 */
export function countText(n) {
  if (n === null || n === undefined || !Number.isFinite(Number(n))) return '—';
  const v = Number(n);
  const sign = v < 0 ? '-' : '';
  const digits = String(Math.abs(Math.trunc(v)));
  let out = '';
  for (let i = 0; i < digits.length; i += 1) {
    if (i > 0 && (digits.length - i) % 3 === 0) out += ',';
    out += digits[i];
  }
  return sign + out;
}

/**
 * A rate, or the reason there is not one. ONE function, and it is the only way
 * a percentage reaches this screen.
 *
 * 🔴 THE FRACTION IS NOT OPTIONAL DETAIL, IT IS PART OF THE NUMBER. "83%" over
 * six cases and "83%" over six hundred are different claims, and the reader can
 * only tell them apart if both sides are on screen. So the fraction renders
 * beside the percentage always, never behind a hover, never in a tooltip.
 */
export function renderRate(doc, reading, { size } = {}) {
  const box = el(doc, 'span', `cc-rate${size ? ` cc-rate--${size}` : ''}`);
  box.setAttribute('data-rate-ok', reading && reading.ok ? '1' : '0');
  if (reading && reading.ok) {
    const pct = el(doc, 'span', 'cc-rate__pct', percentText(reading.rate));
    pct.setAttribute('data-pct', String(reading.rate));
    box.appendChild(pct);
    const frac = el(doc, 'span', 'cc-rate__frac', `${countText(reading.n)}/${countText(reading.d)}`);
    frac.setAttribute('data-numerator', String(reading.n));
    frac.setAttribute('data-denominator', String(reading.d));
    box.appendChild(frac);
    return box;
  }
  // The refusal, as content. `n` still shows when it exists — the count is real,
  // it is the RATE that is not, and hiding the count would lose a measurement.
  if (reading && reading.n !== null && reading.n !== undefined) {
    box.appendChild(el(doc, 'span', 'cc-rate__frac', `${countText(reading.n)}건`));
  }
  const why = el(doc, 'span', 'cc-rate__why', (reading && reading.why) || '분모 없음');
  why.setAttribute('data-rate-why', (reading && reading.why) || '분모 없음');
  box.appendChild(why);
  return box;
}

/** A link that asks the same question with one thing changed. */
function queryLink(doc, className, text, question, omit) {
  const a = el(doc, 'a', className, text);
  a.setAttribute('href', `?${consoleQuery(question, omit)}`);
  return a;
}

// ── the kind picker ──────────────────────────────────────────

/**
 * The registered finding kinds, as the links they already are.
 *
 * 🔴 THE PICKER IS THE PROOF THE CONSOLE GENERALISED. It is built from the
 * catalog the server declares — not from a list in this file — so a kind
 * registered tomorrow appears without a line changing here. The atom count rides
 * along because coverage is the thing the operator actually needs: a kind with
 * no observations is declared, not populated, and a picker that hides that sends
 * them into an empty console with no explanation.
 *
 * 🔴 AND `atoms: null` RENDERS NOTHING RATHER THAN 0. An absent count is not a
 * measured zero — the same prohibition the lineage screen's coverage facts hold.
 */
export function renderKindPicker(doc, model) {
  const nav = el(doc, 'nav', 'cc-kinds');
  nav.setAttribute('data-panel', 'kinds');
  nav.setAttribute('data-kinds-state', model.catalog.state);
  nav.appendChild(el(doc, 'span', 'cc-kinds__term', '불량 종류'));

  const list = el(doc, 'div', 'cc-kinds__list');
  const kinds = Array.isArray(model.catalog.kinds) ? model.catalog.kinds : [];
  for (const row of kinds) {
    const active = row.kind === model.kind;
    const a = el(doc, 'a', `cc-kind${active ? ' cc-kind--active' : ''}`);
    a.setAttribute('href', `?${consoleQuery({ finding: row.kind, slices: {} })}`);
    a.setAttribute('data-kind', row.kind);
    if (active) a.setAttribute('aria-current', 'page');
    a.appendChild(el(doc, 'span', 'cc-kind__label', row.label));
    // Coverage, so the picker tells the operator which kinds have data.
    if (row.atoms !== null) {
      const n = el(doc, 'span', 'cc-kind__n', countText(row.atoms));
      n.setAttribute('data-kind-atoms', String(row.atoms));
      list.appendChild(a);
      a.appendChild(n);
    } else {
      list.appendChild(a);
    }
    // A kind with no declared observation method can never carry a contrast.
    // Saying so HERE costs one glyph and saves the operator a round trip.
    if (row.hasDenominator === false) {
      const mark = el(doc, 'span', 'cc-kind__nodenom', '분모없음');
      mark.setAttribute('data-kind-nodenominator', '1');
      a.appendChild(mark);
    }
  }
  if (!kinds.length) {
    // Honest degradation: the catalog could not be read, so the console says
    // that rather than presenting the one kind it fell back to as a choice.
    const note = el(doc, 'span', 'cc-kinds__none', catalogNote(model.catalog.state));
    note.setAttribute('data-kinds-none', model.catalog.state);
    list.appendChild(note);
  }
  nav.appendChild(list);
  return nav;
}

function catalogNote(state) {
  if (state === 'absent') return '어휘 미설치 — 마이그레이션 미실행';
  if (state === 'empty') return '등재된 종류 0 — 백필 미실행';
  return '종류 목록 없음 — 기본값으로 조회';
}

// ── the active slices, as removable links ────────────────────

function renderSliceChips(doc, model) {
  const bag = model.question.slices || {};
  const active = SLICE_PARAMS.filter((k) => bag[k] != null && String(bag[k]) !== '');
  if (!active.length) return null;
  const wrap = el(doc, 'div', 'cc-slicechips');
  wrap.setAttribute('data-panel', 'slicechips');
  for (const key of active) {
    const a = queryLink(doc, 'cc-slicechip',
      `${axisTerm(key)} ${bag[key]} ×`, model.question, key);
    a.setAttribute('data-slice-off', key);
    a.setAttribute('title', `${axisTerm(key)} 조건 해제`);
    wrap.appendChild(a);
  }
  return wrap;
}

// ── 현황판 ────────────────────────────────────────────────────

/**
 * The console's entry point: how often this kind happens, over what.
 *
 * 🔴 THE DENOMINATOR IS ALWAYS ON SCREEN, INCLUDING WHEN THERE ISN'T ONE. The
 * headline prints the run count and what defines it (`inspection_run` + the
 * kind's declared methods), or it prints why there is none. A rate whose
 * denominator is one click away is a rate nobody checks.
 */
export function renderStatus(doc, model) {
  const panel = el(doc, 'section', 'cc-panel');
  panel.setAttribute('data-panel', 'status');
  panel.appendChild(el(doc, 'h2', 'cc-panel__title', '현황'));

  const head = el(doc, 'div', 'cc-headline');
  head.appendChild(renderRate(doc, model.split.rate, { size: 'lead' }));

  const den = el(doc, 'div', `cc-den cc-den--${model.denominator.standing}`);
  den.setAttribute('data-denominator', model.denominator.standing);
  den.appendChild(el(doc, 'span', 'cc-den__title', model.denominator.title));
  den.appendChild(el(doc, 'span', 'cc-den__detail', model.denominator.detail));
  head.appendChild(den);
  panel.appendChild(head);

  const chips = renderSliceChips(doc, model);
  if (chips) panel.appendChild(chips);

  // 🔴 THE TWO NUMBERS ON THIS PANEL ARE NOT THE SAME KIND OF NUMBER, AND THE
  // PANEL SAYS SO. The headline is a DEFECT RATE (found over inspection_run);
  // every slice row below is a SHARE OF THE FOUND POPULATION (5 of the 6 defects
  // went through B-3). Reading a share as a rate turns "most of my defects came
  // from the busiest equipment" into "this equipment is 83% defective" — off by
  // whatever that equipment's throughput is. One caption is what keeps a reader
  // from making that substitution silently.
  const groups = Array.isArray(model.slices) ? model.slices : [];
  if (groups.length) {
    const cap = el(doc, 'p', 'cc-slices__caption', '아래는 «난 쪽 비중» — 발견 건수 대비. 위 발생률과 분모가 다릅니다.');
    cap.setAttribute('data-slices-caption', 'share-of-found');
    panel.appendChild(cap);
  }
  for (const group of groups) {
    const g = el(doc, 'div', 'cc-slice');
    g.setAttribute('data-axis', group.axis);
    const term = el(doc, 'div', 'cc-slice__term');
    term.appendChild(el(doc, 'span', 'cc-slice__name', group.term));
    if (group.about) {
      const b = el(doc, 'span', `cc-about cc-about--${group.about}`, aboutText(group.about));
      b.setAttribute('data-about', group.about);
      term.appendChild(b);
    }
    // 🔴 AN AXIS'S COVERAGE IS NOT ITS ROWS' DENOMINATOR, AND THE GAP IS INVISIBLE
    // WITHOUT THIS. Live: the bonding axes reach 44,399 of the 46,899 found packages,
    // yet every row still divides by 46,899 — so a factor present in EVERY attributable
    // package reads 94.7%, and the missing 5.3% is a data gap rendering as a measured
    // absence. Shown only when it actually differs, so it is a signal and not furniture.
    if (group.coveredFound !== null && group.coveredFound !== model.split.found) {
      const cov = el(doc, 'span', 'cc-slice__cov',
        `귀속 ${countText(group.coveredFound)}/${countText(model.split.found)}`);
      cov.setAttribute('data-axis-covered', String(group.coveredFound));
      cov.setAttribute('title', '이 축으로 귀속 가능한 발견 건수 — 아래 행의 분모와 다릅니다');
      term.appendChild(cov);
    }
    g.appendChild(term);
    const rows = el(doc, 'div', 'cc-slice__rows');
    for (const row of group.rows) {
      // 🔴 A DECLARED-BUT-UNREPORTED ROW IS STILL A LINK AND STILL NOT A ZERO.
      // The class set is closed, so a class absent from this answer is worth
      // seeing — and worth being able to ask about — but it renders muted, with
      // the refusal its rate carries, never as `0`.
      const a = queryLink(doc, `cc-slicerow${row.declared ? ' cc-slicerow--declared' : ''}`, null,
        withSlice(model.question, row.axis, row.key));
      a.setAttribute('data-slice-axis', row.axis);
      a.setAttribute('data-slice-key', row.key);
      if (row.declared) a.setAttribute('data-slice-declared', '1');
      a.appendChild(el(doc, 'span', 'cc-slicerow__key', row.label));
      a.appendChild(renderRate(doc, row.rate));
      rows.appendChild(a);
    }
    g.appendChild(rows);
    panel.appendChild(g);
  }
  if (!groups.length) {
    panel.appendChild(el(doc, 'p', 'cc-empty', '슬라이스 없음 — 응답에 축별 집계 없음'));
  }
  return panel;
}

// ── 양쪽 모집단 — THREE counts ────────────────────────────────

/**
 * found / clean-scanned / never-scanned, as three numbers.
 *
 * 🔴 NEVER-SCANNED GETS ITS OWN COUNT AND ITS OWN LINE, AND THE LINE SAYS IT IS
 * OUT OF THE DENOMINATOR. Folding it into clean would shrink every rate on this
 * screen by exactly the amount of inspection that never happened — a coverage
 * gap rendered as a quality improvement. The panel prints the arithmetic
 * (분모 = 발견 + 깨끗) so a reader can check that it was excluded rather than
 * take this comment's word for it.
 */
export function renderPopulation(doc, model) {
  const panel = el(doc, 'section', 'cc-panel');
  panel.setAttribute('data-panel', 'population');
  panel.appendChild(el(doc, 'h2', 'cc-panel__title', '모집단'));

  const grid = el(doc, 'div', 'cc-pop');
  for (const row of model.rows) {
    const cell = el(doc, 'div',
      `cc-pop__cell cc-pop__cell--${row.key}${row.inDenominator ? '' : ' cc-pop__cell--out'}`);
    cell.setAttribute('data-pop', row.key);
    cell.setAttribute('data-pop-n', row.n === null ? '' : String(row.n));
    cell.setAttribute('data-in-denominator', row.inDenominator ? '1' : '0');
    cell.appendChild(el(doc, 'div', 'cc-pop__term', row.term));
    cell.appendChild(el(doc, 'div', 'cc-pop__n', countText(row.n)));
    cell.appendChild(el(doc, 'div', 'cc-pop__note', row.note));
    grid.appendChild(cell);
  }
  panel.appendChild(grid);

  const sum = el(doc, 'p', 'cc-pop__sum');
  sum.setAttribute('data-pop-sum', model.split.denominator === null ? '' : String(model.split.denominator));
  sum.textContent = model.split.denominator === null
    ? '분모 없음 — 발견·깨끗 중 하나가 미보고'
    : `분모 ${countText(model.split.denominator)} = 발견 ${countText(model.split.found)} + 깨끗 ${countText(model.split.clean)} · 미스캔 제외`;
  panel.appendChild(sum);

  // 🔴 THE REASON THE THREE COUNTS DO NOT CLOSE. Live on this box, 2,500 runs scanned
  // something outside the declared population — so found + clean + never_scanned does
  // not equal the universe, and a reader who adds them gets a discrepancy with no
  // explanation on screen. The server names it; this prints its name and its number.
  if (model.split.outsideUniverse && model.split.outsideUniverse.count !== null) {
    const out = el(doc, 'p', 'cc-pop__outside');
    out.setAttribute('data-outside-universe', String(model.split.outsideUniverse.count));
    out.textContent = `${countText(model.split.outsideUniverse.count)} · `
      + (model.split.outsideUniverse.message || '선언된 모집단 밖을 스캔한 run');
    panel.appendChild(out);
  }
  return panel;
}

// ── 공통점 / 차이점 — two panels, one call ────────────────────

/**
 * 공통점 — what the found cases share, beside the base rate that says whether
 * sharing it is surprising.
 */
export function renderShared(doc, model) {
  const panel = el(doc, 'section', 'cc-panel');
  panel.setAttribute('data-panel', 'shared');
  panel.appendChild(el(doc, 'h2', 'cc-panel__title', '공통점'));

  if (!model.shared.length) {
    panel.appendChild(el(doc, 'p', 'cc-empty', '공통 요인 없음 — 교집합 0'));
    return panel;
  }
  const list = el(doc, 'ul', 'cc-rows');
  for (const row of model.shared) {
    const li = el(doc, 'li', 'cc-row');
    li.setAttribute('data-factor', row.key);
    li.setAttribute('data-factor-axis', row.axis);
    li.appendChild(renderFactorName(doc, row));
    const side = el(doc, 'div', 'cc-row__sides');
    side.appendChild(renderSide(doc, '난 쪽', row.inFound, 'found'));
    // 🔴 THE OTHER SIDE. 5-of-6 is not a finding if the clean packages went
    // through it just as often; without this column the panel promotes
    // coincidence to a cause.
    side.appendChild(renderSide(doc, '안 난 쪽', row.inClean, 'clean'));
    li.appendChild(side);
    list.appendChild(li);
  }
  panel.appendChild(list);
  return panel;
}

/**
 * 차이점 — the same factor's rate in the found population vs the clean one.
 *
 * 🔴 BOTH DENOMINATORS ON SCREEN, ALWAYS. That is the panel's entire claim to
 * being evidence rather than a ranking: 5/6 against 12/94 is a comparison a
 * reader can judge, "83% vs 13%" is two numbers they cannot.
 *
 * 🔴 AND WHEN THERE IS NO CLEAN POPULATION, THE PANEL RENDERS THE REASON AS ITS
 * CONTENT. A kind whose signature declares no observation method has no
 * inspection_run to contrast against — that is a fact about the kind, not a
 * failure of the console, and an empty panel would read as "no differences
 * found", the opposite of the truth.
 */
export function renderContrast(doc, model) {
  const panel = el(doc, 'section', 'cc-panel');
  panel.setAttribute('data-panel', 'contrast');
  panel.appendChild(el(doc, 'h2', 'cc-panel__title', '차이점'));

  if (!model.contrastable) {
    const box = el(doc, 'div', 'cc-nodenom');
    box.setAttribute('data-contrast', 'no-denominator');
    box.appendChild(el(doc, 'span', 'cc-nodenom__title', '분모 없음 — 대조 불가'));
    box.appendChild(el(doc, 'p', 'cc-nodenom__why', contrastRefusal(model)));
    panel.appendChild(box);
    return panel;
  }
  if (!model.contrast.length) {
    panel.appendChild(el(doc, 'p', 'cc-empty', '차이 요인 없음 — 양쪽 분포 동일'));
    return panel;
  }

  const list = el(doc, 'ul', 'cc-rows');
  for (const row of model.contrast) {
    const li = el(doc, 'li', 'cc-row');
    li.setAttribute('data-factor', row.key);
    li.setAttribute('data-factor-axis', row.axis);
    li.setAttribute('data-enrichment-state', row.state);
    li.appendChild(renderFactorName(doc, row));

    const side = el(doc, 'div', 'cc-row__sides');
    side.appendChild(renderSide(doc, '난 쪽', row.inFound, 'found'));
    side.appendChild(renderSide(doc, '안 난 쪽', row.inClean, 'clean'));
    // 🔴 THE SERVER'S VERDICT AND THE SERVER'S INTERVAL, CONSUMED. The ranking is
    // an interval lower bound computed from counts this client does not hold; a
    // point estimate rendered here would put the noisiest rows on top, which is
    // the opposite of what a surprise ranking is for.
    const lift = el(doc, 'span', `cc-lift cc-lift--${row.verdict.tone}`);
    lift.setAttribute('data-lift', row.enrichment === null ? '' : String(row.enrichment));
    lift.setAttribute('data-verdict', row.state);
    lift.appendChild(el(doc, 'span', 'cc-lift__x',
      row.enrichment === null ? row.verdict.text : `${liftText(row.enrichment)}`));
    if (row.ci) {
      el(doc, 'span', 'cc-lift__ci', `${liftText(row.ci[0])}–${liftText(row.ci[1])}`);
      lift.appendChild(el(doc, 'span', 'cc-lift__ci',
        `95% ${liftText(row.ci[0])}–${liftText(row.ci[1])}`));
    }
    side.appendChild(lift);
    if (row.reason) {
      const why = el(doc, 'span', 'cc-row__why', row.reason);
      why.setAttribute('data-row-reason', row.reason);
      side.appendChild(why);
    }
    li.appendChild(side);
    list.appendChild(li);
  }
  panel.appendChild(list);
  return panel;
}

/** A ratio, or a dash. Never `Infinity` — an unbounded estimate outranks reality. */
export function liftText(v) {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return '—';
  const n = Number(v);
  return n >= 10 ? `${Math.round(n)}×` : `${n.toFixed(1)}×`;
}

/** WHY there is no contrast — the kind's own signature, or the response. */
function contrastRefusal(model) {
  if (model.denominator.standing === 'undeclared') return model.denominator.detail;
  if (model.split.clean === null) return '안 난 쪽(깨끗-스캔됨) 수 미보고 — 대조군 없음';
  return model.denominator.detail;
}

function renderFactorName(doc, row) {
  const box = el(doc, 'div', 'cc-row__factor');
  if (row.term) box.appendChild(el(doc, 'span', 'cc-row__term', row.term));
  box.appendChild(el(doc, 'span', 'cc-row__key', row.key));
  // 🔴 A BADGE, NEVER A FILTER. `process` describes what MADE the part;
  // `inspection` describes the scan that LOOKED at it. Both are real findings and
  // they are different ones — a console that cannot tell them apart reports a
  // scanner artefact as a process cause.
  if (row.about) {
    const b = el(doc, 'span', `cc-about cc-about--${row.about}`, aboutText(row.about));
    b.setAttribute('data-about', row.about);
    box.appendChild(b);
  }
  return box;
}

const ABOUT_TEXT = { process: '공정', inspection: '검사' };
function aboutText(about) { return ABOUT_TEXT[about] || about; }

function renderSide(doc, term, reading, key) {
  const box = el(doc, 'span', 'cc-side');
  box.setAttribute('data-side', key);
  box.appendChild(el(doc, 'span', 'cc-side__term', term));
  box.appendChild(renderRate(doc, reading));
  return box;
}

// ── the unified fact chip ────────────────────────────────────

/**
 * ONE chip renderer for `measured`, `observed` and `processed_with`.
 *
 * 🔴 NOT THREE. The three predicates are one vocabulary by construction — that
 * is what the ontology bought — and three renderers would let an MI number and a
 * process condition drift into two layouts, so a reader comparing them would be
 * comparing two screens. Which field is the name and which is the value is a
 * TABLE in the core (`FACT_SPEC`), not a branch here; this function does not
 * know what a `quantity` is.
 *
 * 🔴 SPEAKER AND EVIDENCE RIDE ON EVERY CHIP. A fact chip is a number, and the
 * acceptance criterion for a number on this screen is denominator + evidence +
 * speaker. An unattributed fact renders 「출처 미상」 rather than rendering clean —
 * the missing attribution is the thing the reader must see.
 */
export function renderFactChip(doc, chip) {
  const box = el(doc, 'div', `cc-fact cc-fact--${chip.predicate || 'unknown'}`);
  box.setAttribute('data-fact', chip.predicate || '');

  const head = el(doc, 'div', 'cc-fact__head');
  head.appendChild(el(doc, 'span', 'cc-fact__term', chip.term));
  if (chip.name) head.appendChild(el(doc, 'span', 'cc-fact__name', chip.name));
  if (chip.value !== null && chip.value !== undefined) {
    const v = el(doc, 'span', 'cc-fact__value', chip.unit ? `${chip.value} ${chip.unit}` : chip.value);
    v.setAttribute('data-fact-value', chip.value);
    head.appendChild(v);
  }
  box.appendChild(head);

  if (chip.meta.length) {
    const meta = el(doc, 'div', 'cc-fact__meta');
    for (const m of chip.meta) {
      const s = el(doc, 'span', 'cc-fact__q', `${m.term} ${m.text}`);
      s.setAttribute('data-q', m.key);
      meta.appendChild(s);
    }
    box.appendChild(meta);
  }

  // 🔴 The observer's own words, verbatim and never parsed (R-C).
  if (chip.note) box.appendChild(el(doc, 'p', 'cc-fact__note', chip.note));

  const foot = el(doc, 'div', 'cc-fact__foot');
  const speaker = el(doc, 'span', `cc-speaker cc-speaker--${chip.speaker.kind}`, chip.speaker.text);
  speaker.setAttribute('data-speaker', chip.speaker.kind);
  foot.appendChild(speaker);
  if (chip.basis) {
    const basis = el(doc, 'span', `cc-basis cc-basis--${chip.basis.kind}`, chip.basis.text);
    basis.setAttribute('data-basis-kind', chip.basis.kind);
    foot.appendChild(basis);
  }
  if (chip.evidence) {
    const ev = el(doc, 'span', 'cc-evidence', chip.evidence.text);
    ev.setAttribute('data-evidence', chip.evidence.text);
    foot.appendChild(ev);
  } else {
    const ev = el(doc, 'span', 'cc-evidence cc-evidence--none', '근거 ref 없음');
    ev.setAttribute('data-evidence', '');
    foot.appendChild(ev);
  }
  if (chip.at) foot.appendChild(el(doc, 'span', 'cc-fact__at', chip.at));
  box.appendChild(foot);
  return box;
}

export function renderFacts(doc, model) {
  const panel = el(doc, 'section', 'cc-panel');
  panel.setAttribute('data-panel', 'facts');
  panel.appendChild(el(doc, 'h2', 'cc-panel__title', '자재 팩트'));
  if (!model.facts.length) {
    panel.appendChild(el(doc, 'p', 'cc-empty', '팩트 없음 — 응답에 measured·observed·processed_with 원자 없음'));
    return panel;
  }
  const wrap = el(doc, 'div', 'cc-facts');
  for (const chip of model.facts) wrap.appendChild(renderFactChip(doc, chip));
  panel.appendChild(wrap);
  return panel;
}

// ── 🔴 THE TRANSFER WALK — 보이드 → 본딩 → DT → 코어 ────────────────────

/**
 * One `transferred` hop. The list is ANY length; this renders one link of it.
 *
 * 🔴 NOT A FIXED STAGE. The walk is joined by location continuity (hop N's `to`
 * is hop N+1's `from`), so a wafer that visits DT twice produces two DT hops and
 * both must be on screen. Anything here that indexed a stage would render the
 * two-DT wafer as a one-DT wafer, and nobody would see the hop go missing.
 *
 * 🔴 THE QUANTITY PAIR IS WHAT MAKES SELECTION VISIBLE. Only some of what was
 * loaded moves on; 「8개 이송」 alone is exactly the shape forbidden everywhere
 * else on this screen, so the pair goes through `renderRate` and the numerator
 * cannot reach the screen without its denominator.
 */
export function renderTransferHop(doc, hop, ordinal) {
  const item = el(doc, 'li', `cc-hop cc-hop--${hop.state}${hop.continuous === false ? ' cc-hop--break' : ''}`);
  item.setAttribute('data-hop', String(ordinal));
  item.setAttribute('data-hop-state', hop.state);
  item.setAttribute('data-hop-continuous', hop.continuous === false ? '0' : '1');

  // 🔴 A BREAK IS SHOWN, NOT BRIDGED. Two hops that do not meet are not a chain,
  // and drawing them adjacent would assert a connection nobody recorded.
  if (hop.continuous === false) {
    const gap = el(doc, 'div', 'cc-hop__break', '위 홉의 도착지와 이 홉의 출발지가 다름 — 사슬 끊김');
    gap.setAttribute('data-hop-break', '1');
    item.appendChild(gap);
  }

  const head = el(doc, 'div', 'cc-hop__head');
  head.appendChild(el(doc, 'span', 'cc-hop__ord', String(ordinal)));
  if (hop.label) head.appendChild(el(doc, 'span', 'cc-hop__label', hop.label));
  if (hop.from) {
    const f = el(doc, 'span', 'cc-hop__from', hop.from.text);
    f.setAttribute('data-hop-from', hop.from.id);
    head.appendChild(f);
  }
  item.appendChild(head);

  const line = el(doc, 'div', 'cc-hop__line');
  line.appendChild(el(doc, 'span', 'cc-hop__arrow', '←'));
  if (hop.state === 'resolved') {
    const v = el(doc, 'span', 'cc-hop__to', hop.to.text);
    v.setAttribute('data-hop-to', hop.to.id);
    line.appendChild(v);
  } else {
    const v = el(doc, 'span', 'cc-hop__to cc-hop__to--none', '주장 없음');
    v.setAttribute('data-hop-to', '');
    line.appendChild(v);
  }

  // The SAME basis renderer the lineage hops use — read off the field, never
  // derived: a convention-backed hop carries the same state word a measured one
  // does, so the state cannot tell you which this is.
  if (hop.basis) {
    const chip = el(doc, 'span', `cc-basis cc-basis--${hop.basis.kind}`, hop.basis.text);
    chip.setAttribute('data-basis-kind', hop.basis.kind);
    line.appendChild(chip);
  }

  if (hop.quantity) {
    const q = el(doc, 'span', 'cc-qty');
    q.setAttribute('data-qty', hop.quantity.moved === null ? '' : String(hop.quantity.moved));
    q.setAttribute('data-qty-of', hop.quantity.of === null ? '' : String(hop.quantity.of));
    if (hop.quantity.verb) q.appendChild(el(doc, 'span', 'cc-qty__verb', hop.quantity.verb));
    q.appendChild(renderRate(doc, hop.quantity.reading));
    line.appendChild(q);
    // 「사용 칩 잔량」 — the container's inflow minus outflow.
    if (hop.quantity.remainder !== null) {
      const rem = el(doc, 'span', 'cc-qty__rem', `잔량 ${countText(hop.quantity.remainder)}`);
      rem.setAttribute('data-remainder', String(hop.quantity.remainder));
      rem.setAttribute('data-remainder-from', hop.quantity.remainderFrom);
      line.appendChild(rem);
    }
  }
  item.appendChild(line);

  const meta = [];
  if (hop.at) meta.push(hop.at);
  if (hop.eventId) meta.push(hop.eventId);
  if (meta.length) item.appendChild(el(doc, 'div', 'cc-hop__meta', meta.join('  ·  ')));
  if (hop.state !== 'resolved' && hop.reason) {
    item.appendChild(el(doc, 'p', 'cc-hop__reason', hop.reason));
  }
  return item;
}

export function renderTracePanel(doc, model) {
  const panel = el(doc, 'section', 'cc-panel');
  panel.setAttribute('data-panel', 'trace');
  panel.appendChild(el(doc, 'h2', 'cc-panel__title', '이송 추적 — 불량 → 본딩 → DT → 코어'));

  const chain = model.trace;
  if (!chain.present) {
    // 🔴 NOT AN EMPTY CHAIN. "the response carried no trace" and "the trace ran
    // and stopped" are different facts, and drawing the first as the second
    // would show a chain nobody walked.
    const box = el(doc, 'div', 'cc-nodenom');
    box.setAttribute('data-trace', 'absent');
    box.appendChild(el(doc, 'span', 'cc-nodenom__title', '추적 없음'));
    box.appendChild(el(doc, 'p', 'cc-nodenom__why',
      '응답에 trace 없음 — 대상 하나를 고르면 이송 사슬이 나옵니다'));
    panel.appendChild(box);
    return panel;
  }

  if (chain.subject) {
    const s = el(doc, 'div', 'cc-trace__subject', chain.subject);
    s.setAttribute('data-trace-subject', chain.subject);
    panel.appendChild(s);
  }

  if (!chain.hops.length) {
    panel.appendChild(el(doc, 'p', 'cc-empty', '이송 원자 0건 — 걸을 사슬 없음'));
  } else {
    const list = el(doc, 'ol', 'cc-hops');
    chain.hops.forEach((hop, i) => list.appendChild(renderTransferHop(doc, hop, i + 1)));
    panel.appendChild(list);
  }

  // The walk's own shape, said out loud: how many hops and how many DISTINCT
  // containers. A wafer that visits DT twice has to be visibly different from one
  // that visits once, and the hop count alone does not say that.
  const foot = el(doc, 'div', 'cc-trace__foot');
  foot.setAttribute('data-trace-hops', String(chain.hops.length));
  foot.setAttribute('data-trace-stops', String(chain.stops));
  foot.setAttribute('data-trace-breaks', String(chain.breaks));
  foot.textContent = `홉 ${chain.hops.length} · 경유 ${chain.stops}`
    + (chain.breaks ? ` · 끊김 ${chain.breaks}` : '')
    + ' · 다이 단위 바인딩 미착지';
  panel.appendChild(foot);

  // Where the walk STOPPED and why — the honest ending for a chain that does not
  // reach the core wafer. Verbatim, because it is the server's sentence.
  if (chain.terminal) {
    const term = el(doc, 'p', 'cc-trace__terminal', chain.terminal);
    term.setAttribute('data-trace-terminal', chain.terminal);
    panel.appendChild(term);
  }
  return panel;
}

// ── the whole console ────────────────────────────────────────

/**
 * Render the console into `mount`.
 *
 * The kind picker renders even when everything else refuses, because it is the
 * one thing that lets the operator leave a kind with no data — a console that
 * hides its own navigation when the answer is empty is a dead end, which is the
 * defect the lineage screen already fixed one row up.
 */
export function renderConsole(doc, mount, model, notice) {
  clear(mount);
  const wrap = el(doc, 'section', 'cc');
  wrap.setAttribute('data-answer-kind', 'console');
  wrap.setAttribute('data-finding', model.kind);

  wrap.appendChild(renderKindPicker(doc, model));

  // 🔴 A REFUSAL DOES NOT REPLACE THE PANELS, IT SITS ABOVE THEM. The panels
  // still render — every count reading 미보고, every rate reading 분모 없음 —
  // because that is the TRUE state of the answer, and a screen that shows a
  // notice instead would hide which parts of the question the server did answer.
  // The server's own words go out verbatim underneath: a refusal reworded here
  // cannot be checked against the server.
  if (notice && notice.title) {
    const box = el(doc, 'div', `cc-notice cc-notice--${notice.tone || 'gap'}`);
    box.setAttribute('data-notice-tone', notice.tone || 'gap');
    box.appendChild(el(doc, 'div', 'cc-notice__title', notice.title));
    if (notice.detail) box.appendChild(el(doc, 'p', 'cc-notice__detail', String(notice.detail)));
    wrap.appendChild(box);
  }

  // A kind the catalog does not list is still asked — the catalog can be stale
  // and refusing would hide data that exists — but the screen says so.
  if (model.standing.reason) {
    const note = el(doc, 'div', 'cc-standing');
    note.setAttribute('data-standing', 'unknown-kind');
    note.appendChild(el(doc, 'span', 'cc-standing__kind', model.kind));
    note.appendChild(el(doc, 'span', 'cc-standing__why', model.standing.reason));
    wrap.appendChild(note);
  }

  wrap.appendChild(renderStatus(doc, model));
  wrap.appendChild(renderPopulation(doc, model));
  wrap.appendChild(renderTracePanel(doc, model));
  wrap.appendChild(renderShared(doc, model));
  wrap.appendChild(renderContrast(doc, model));
  wrap.appendChild(renderFacts(doc, model));

  // Whatever the server wanted to say about this answer that is not a number —
  // an absent attribution relation, a contrast it could not run. Its own words.
  if (model.notes && model.notes.length) {
    const box = el(doc, 'div', 'cc-notes');
    box.setAttribute('data-notes', String(model.notes.length));
    for (const n of model.notes) {
      const row = el(doc, 'p', 'cc-note', n.text);
      row.setAttribute('data-note', n.note);
      box.appendChild(row);
    }
    wrap.appendChild(box);
  }

  if (model.generatedAt) {
    wrap.appendChild(el(doc, 'div', 'cc-generated', `조회 ${model.generatedAt}`));
  }
  mount.appendChild(wrap);
  return wrap;
}

/**
 * The console BEFORE the data lands, and when the data cannot land.
 *
 * 🔴 IT KEEPS THE KIND PICKER. A notice that replaces the whole console strands
 * the operator on the kind that failed; keeping the picker means the way out of
 * a broken answer is the same click as the way into a different one.
 */
export function renderConsoleNotice(doc, mount, model, { tone, title, detail }) {
  clear(mount);
  const wrap = el(doc, 'section', 'cc');
  wrap.setAttribute('data-answer-kind', 'console-notice');
  wrap.setAttribute('data-finding', model.kind);
  wrap.appendChild(renderKindPicker(doc, model));

  const box = el(doc, 'div', `cc-notice cc-notice--${tone || 'idle'}`);
  box.setAttribute('data-notice-tone', tone || 'idle');
  box.appendChild(el(doc, 'div', 'cc-notice__title', title || ''));
  if (detail) box.appendChild(el(doc, 'p', 'cc-notice__detail', String(detail)));
  wrap.appendChild(box);
  mount.appendChild(wrap);
  return wrap;
}
