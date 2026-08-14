// ============================================================
// contrast_view.js — 대조 패널을 DOM으로.
//
// `document` IS AN ARGUMENT, not a global — same contract as the other view
// modules on this page. Everything builds nodes and sets `textContent`; nothing
// touches `innerHTML`, so a field name or an equipment id out of the server can
// never become markup.
//
// 🔴 THE PANEL IS THE ANSWER TO MULTI-MARKING. Marking one lot asks for a
// picture; marking several asks a question a picture cannot answer. This panel is
// what appears in that second case, in the same screen, with no new page and no
// modal — mark, and the answer is there.
//
// 🔴 IT SCROLLS INSIDE ITSELF. The fold discipline: the candidate list gets its
// own scroll box rather than growing the page, so the table above and the answer
// below stay reachable without a 12,000px journey.
//
// 🔴 READABILITY IS A FUNCTION. Factor labels 15px, rates 15px mono, fractions
// and intervals 13px. Nothing below 13px, and the list scrolls rather than
// shrinking the type.
// ============================================================

import {
  enrichmentLabel, verdictFace, rateText, countText, fractionText,
  enrichmentText, ciText, factorSentence, gateMeaning, splitCandidates, fieldReading,
} from './contrast_core.js';
// The pair view prints the SAME numbers the table above prints, through the same
// formatter — two spellings of one value is how a screen comes to disagree with
// itself one row apart.
import { valueText } from './surprise_core.js';

function el(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function attrs(node, map) {
  for (const k of Object.keys(map)) {
    const v = map[k];
    if (v === null || v === undefined) continue;
    node.setAttribute(k, String(v));
  }
  return node;
}

function clear(mount) {
  while (mount.firstChild) mount.removeChild(mount.firstChild);
}

function renderNotice(doc, { tone, title, detail }) {
  const box = el(doc, 'div', `cx-notice cx-notice--${tone}`);
  box.setAttribute('data-contrast-notice', tone);
  box.appendChild(el(doc, 'div', 'cx-notice__title', title));
  if (detail) box.appendChild(el(doc, 'pre', 'cx-notice__detail', detail));
  return box;
}

/**
 * Who is being compared with whom.
 *
 * 🔴 THE TWO POPULATIONS, WITH THEIR DENOMINATORS. Every multiple below is a
 * ratio between these two, and a reader who cannot see 75 subjects against 834
 * cannot tell a real signal from three wafers agreeing by chance.
 */
function renderScope(doc, model) {
  const box = el(doc, 'div', 'cx-scope');
  box.setAttribute('data-panel', 'contrast-scope');

  const side = (key, term, pop) => {
    const s = el(doc, 'div', `cx-pop cx-pop--${key}`);
    s.setAttribute('data-pop', key);
    s.appendChild(el(doc, 'span', 'cx-pop__term', term));
    s.appendChild(el(doc, 'span', 'cx-pop__n',
      pop.subjects === null ? '미보고' : countText(pop.subjects)));
    const unit = model.subject.unitLabel || '주어';
    s.appendChild(el(doc, 'span', 'cx-pop__unit', unit));
    if (pop.foundRate !== null) {
      const r = el(doc, 'span', 'cx-pop__rate', `발생 ${rateText(pop.foundRate)}`);
      r.setAttribute('data-found-rate', String(pop.foundRate));
      s.appendChild(r);
      if (pop.foundUnits !== null && pop.foundRateOf !== null) {
        s.appendChild(el(doc, 'span', 'cx-pop__frac',
          `${countText(pop.foundUnits)}/${countText(pop.foundRateOf)}`));
      }
    }
    box.appendChild(s);
  };
  side('case', '마킹', model.scope.case);
  side('control', '나머지', model.scope.control);

  // 🔴 AN EXCLUSION RULE THAT DID NOT RUN IS NOT AN EXCLUSION OF ZERO. A bucket
  // sitting at `discriminator_pending` means nobody was removed and the control
  // group still contains them — reading that as a clean split overstates it.
  const pending = model.scope.excluded.filter((e) => e.state !== 'measured');
  if (pending.length) {
    const note = el(doc, 'div', 'cx-scope__excluded');
    note.setAttribute('data-excluded-pending', String(pending.length));
    note.appendChild(el(doc, 'span', 'cx-scope__term', '제외 미적용'));
    for (const e of pending) {
      const chip = el(doc, 'span', 'cx-excl');
      chip.setAttribute('data-excl-bucket', e.bucket);
      chip.setAttribute('data-excl-state', e.state);
      chip.appendChild(el(doc, 'span', 'cx-excl__label', e.label));
      if (e.message) chip.appendChild(el(doc, 'span', 'cx-excl__why', e.message));
      note.appendChild(chip);
    }
    box.appendChild(note);
  }
  return box;
}

/**
 * One gate verdict, as a chip.
 *
 * 🔴 THE SYMBOL STAYS, THE LABEL BECOMES THE MEANING. 실재 · 상류 · 기전 are this
 * project's words and meant nothing to the owner; ✓ / — / ✗ beside 「우연 아님」
 * needs no glossary. The server's own sentence still rides in the title.
 */
function renderGate(doc, cell) {
  const chip = el(doc, 'span', `cx-gate cx-gate--${cell.verdict}`);
  // 🔴 THE ROW'S OWN ATTRIBUTE NAME. The legend uses `data-legend-gate` so a
  // tree-wide assertion about rows cannot be satisfied by the legend instead.
  attrs(chip, { 'data-gate': cell.id, 'data-gate-verdict': cell.verdict });
  const face = verdictFace(cell.verdict);
  chip.appendChild(el(doc, 'span', 'cx-gate__glyph', face.glyph));
  chip.appendChild(el(doc, 'span', 'cx-gate__word', gateMeaning(cell.id, cell.label)));
  if (cell.message) chip.setAttribute('title', cell.message);
  return chip;
}

/**
 * The one legend line, at the panel HEAD rather than buried under the list.
 *
 * 🔴 IT IS ONE OF ONLY TWO PLACES ON THIS PANEL ALLOWED A FULL SENTENCE (the
 * other is the factor head). The owner could not read the gates at all, and a
 * legend that arrives after the rows it explains has already failed.
 */
function renderGateLegend(doc, model) {
  const box = el(doc, 'div', 'cx-legend');
  box.setAttribute('data-panel', 'contrast-legend');
  if (!model.gates.declared) {
    box.appendChild(el(doc, 'span', 'cx-legend__term', '관문 선언 미보고 — 서버가 관문 축을 싣지 않았습니다'));
    return box;
  }
  for (const gate of model.gates.gates) {
    const item = el(doc, 'span', 'cx-legend__item');
    item.setAttribute('data-legend-gate', gate.id);
    item.appendChild(el(doc, 'span', 'cx-legend__label', gateMeaning(gate.id, gate.label)));
    box.appendChild(item);
  }
  box.appendChild(el(doc, 'span', 'cx-legend__hint',
    '✓ 둘 이상 = 원인 후보. 「물리 경로 있음」이 — 면 아직 물리 모델에 없는 요인입니다(틀렸다는 뜻이 아닙니다).'));
  return box;
}

/**
 * One candidate — A SENTENCE FIRST, numbers underneath as support.
 *
 * 🔴 THE ROW USED TO BE FIVE NUMERIC COLUMNS AND NOTHING ELSE, which is what the
 * owner meant by 「용어들이 뭔말임?」. The finding now reads as a sentence in the
 * reader's own language; the same numbers stay directly below it, so nothing was
 * removed — the table stopped being the ONLY way to get the answer.
 *
 * A card rather than a table row because this panel is a 440px rail: five columns
 * of numbers there either wrap into noise or shrink the type, and shrinking the
 * type is not available (가독성 = 기능).
 */
function renderCandidate(doc, row, model) {
  const box = el(doc, 'article', 'cx-cand');
  attrs(box, {
    'data-candidate': row.key,
    'data-enrichment-state': row.enrichmentState,
    'data-gate-code': row.gateCode || null,
    'data-bias': row.biasCandidate ? '1' : null,
  });

  // 🔴 THE SENTENCE. One of only two places on this panel allowed to be prose.
  const say = el(doc, 'p', 'cx-cand__say', factorSentence(row, model.subject));
  say.setAttribute('data-sentence', '1');
  box.appendChild(say);

  const gates = el(doc, 'div', 'cx-cand__gates');
  for (const cell of row.gates) gates.appendChild(renderGate(doc, cell));
  if (row.biasCandidate) {
    const flag = el(doc, 'span', 'cx-biasflag', '편향 후보');
    flag.setAttribute('data-bias-flag', '1');
    gates.appendChild(flag);
  }
  box.appendChild(gates);

  // 🔴 A FIELD NAME WITH NO KOREAN LABEL DEGRADES VISIBLY, NOT SILENTLY. P0-3
  // brings the declared label layer; until then an unmapped field shows its wire
  // spelling AND says that is what it is, so English machine text on screen reads
  // as a missing declaration rather than as the panel's normal voice.
  const fr = fieldReading(row.field);
  if (!fr.known && row.compare === 'distribution') {
    const flag = el(doc, 'span', 'cx-rawname', '이름 미선언');
    flag.setAttribute('data-label-source', 'wire');
    box.appendChild(flag);
  }

  // The support numbers, in noun form — no sentences below this line.
  const num = el(doc, 'div', 'cx-cand__num');

  // 🔴 THE SUPPORT NUMBERS FOLLOW THE COMPARISON KIND TOO. Printing 「마킹 100% ·
  // 나머지 99%」 under a numeric row repeats the membership/agreement confusion in
  // smaller type — those rates say who HAS A READING, which is never the finding
  // for a distribution row.
  const n = row.numeric;
  if (row.compare === 'distribution' && n) {
    const u = fr.unit ? ` ${fr.unit}` : '';
    const meanCell = (key, term, s) => {
      const cell = el(doc, 'span', `cx-num cx-num--${key}`);
      attrs(cell, { 'data-side': key, 'data-mean': s.mean === null ? null : String(s.mean) });
      cell.appendChild(el(doc, 'span', 'cx-num__term', term));
      cell.appendChild(el(doc, 'span', 'cx-rate', s.mean === null ? '미보고' : `${s.mean.toFixed(2)}${u}`));
      // The spread is what says whether two means are far apart in any real sense.
      if (s.sd !== null) cell.appendChild(el(doc, 'span', 'cx-frac', `±${s.sd.toFixed(2)}`));
      num.appendChild(cell);
    };
    meanCell('case', '마킹 평균', n.case);
    meanCell('control', '나머지 평균', n.control);
    if (n.stdDiff !== null) {
      const sd = el(doc, 'span', 'cx-num cx-num--sd');
      sd.setAttribute('data-std-diff', String(n.stdDiff));
      sd.appendChild(el(doc, 'span', 'cx-num__term', '편차 기준'));
      sd.appendChild(el(doc, 'span', 'cx-rate', `${Math.abs(n.stdDiff).toFixed(1)}σ`));
      num.appendChild(sd);
    }
  } else {
    const side = (key, term, s) => {
      const cell = el(doc, 'span', `cx-num cx-num--${key}`);
      cell.setAttribute('data-side', key);
      cell.appendChild(el(doc, 'span', 'cx-num__term', term));
      cell.appendChild(el(doc, 'span', 'cx-rate', rateText(s.rate)));
      const frac = fractionText(s);
      if (frac) {
        const f = el(doc, 'span', 'cx-frac', frac);
        attrs(f, {
          'data-numerator': s.n === null ? null : String(s.n),
          'data-denominator': s.of === null ? null : String(s.of),
        });
        cell.appendChild(f);
      }
      num.appendChild(cell);
    };
    side('case', '마킹', row.case);
    side('control', '나머지', row.control);
  }

  const lift = el(doc, 'span', 'cx-num cx-num--lift');
  const badge = el(doc, 'span', `cx-lift cx-lift--${row.enrichmentState || 'unknown'}`,
    enrichmentText(row));
  attrs(badge, {
    'data-enrichment': row.enrichment === null ? null : String(row.enrichment),
    'data-enrichment-state': row.enrichmentState,
  });
  lift.appendChild(badge);
  lift.appendChild(el(doc, 'span', 'cx-lift__word', enrichmentLabel(row.enrichmentState)));
  // 🔴 THE INTERVAL RIDES WITH THE POINT ESTIMATE, ALWAYS. On the live data the
  // top candidate has NO point estimate at all (absent from the control
  // population) and the interval is the entire finding.
  const ci = ciText(row);
  if (ci) lift.appendChild(el(doc, 'span', 'cx-ci', ci));
  num.appendChild(lift);

  if (row.evidenceCount !== null) {
    num.appendChild(el(doc, 'span', 'cx-evidence', `근거 ${countText(row.evidenceCount)}건`));
  }
  box.appendChild(num);
  return box;
}

/**
 * One named group, with its ONE explanatory line.
 *
 * 🔴 THE OWNER ASKED WHAT IS THE SAME AND WHAT IS DIFFERENT (「대체 뭐가 같다는건지
 * 다르단건지」) and the panel was one undifferentiated ranking. These are the
 * owner's own words for the two groups, and the third group exists so that a
 * factor which is neither does not get quietly dropped.
 */
function renderGroup(doc, key, title, lead, rows, model) {
  const sec = el(doc, 'section', `cx-group cx-group--${key}`);
  attrs(sec, { 'data-group': key, 'data-group-count': String(rows.length) });
  const h = el(doc, 'h4', 'cx-group__h');
  h.appendChild(el(doc, 'span', 'cx-group__title', title));
  h.appendChild(el(doc, 'span', 'cx-group__n', `${countText(rows.length)}건`));
  sec.appendChild(h);
  sec.appendChild(el(doc, 'p', 'cx-group__lead', lead));
  if (!rows.length) {
    sec.appendChild(el(doc, 'p', 'cx-empty', '해당 없음'));
    return sec;
  }
  for (const row of rows) sec.appendChild(renderCandidate(doc, row, model));
  return sec;
}

/**
 * 🔴 THE TRUNCATION NOTICE. Measured live: 20 returned, 37 scored.
 *
 * A list that shows 20 and says nothing is read as "these are all of them", which
 * is a fake reduction of surprise — the reader concludes there is less going on
 * than there is. So the real numbers go on screen in the 「아래 N건」 form, and
 * they come off the response rather than from a count of what got rendered.
 */
function renderTruncation(doc, model) {
  const p = el(doc, 'p', 'cx-truncation');
  attrs(p, {
    'data-truncated': model.truncated ? '1' : '0',
    'data-shown': String(model.shown),
    'data-scored': model.scored === null ? null : String(model.scored),
    'data-considered': model.considered === null ? null : String(model.considered),
  });
  if (!model.truncated) {
    p.className = 'cx-truncation cx-truncation--full';
    p.textContent = model.scored === null
      ? `아래 ${countText(model.shown)}건`
      : `아래 ${countText(model.shown)}건 — 채점 ${countText(model.scored)}건 전부`;
    return p;
  }
  const hidden = model.hidden === null ? null : model.hidden;
  p.textContent = `아래 ${countText(model.shown)}건 — 채점 ${countText(model.scored)}건 중`
    + (hidden === null ? ' (나머지 미표시)' : ` · ${countText(hidden)}건 미표시`)
    + (model.considered !== null && model.considered !== model.scored
      ? ` · 후보 ${countText(model.considered)}건 검토` : '');
  return p;
}

/**
 * 🔴 THE ATTRIBUTION COVERAGE. What the ranking could not see.
 *
 * A field with 0 of 75 case subjects attributed contributed nothing to the list
 * above. Without this block its absence from the ranking reads as "no difference
 * on this axis", which is the opposite of what happened.
 */
function renderFields(doc, model) {
  const box = el(doc, 'details', 'cx-fields');
  attrs(box, { 'data-panel': 'contrast-fields', 'data-field-count': String(model.fields.length) });
  const sum = el(doc, 'summary', 'cx-fields__sum');
  sum.textContent = `걷힌 필드 ${countText(model.fields.length)}개`
    + (model.blindFields.length ? ` · 그중 ${countText(model.blindFields.length)}개는 마킹 쪽 귀속 0` : '');
  box.appendChild(sum);

  const list = el(doc, 'div', 'cx-fields__list');
  for (const f of model.fields) {
    const item = el(doc, 'div', `cx-field${f.blind ? ' cx-field--blind' : ''}`);
    attrs(item, { 'data-field': f.key, 'data-blind': f.blind ? '1' : '0' });
    item.appendChild(el(doc, 'span', 'cx-field__name', f.key));
    item.appendChild(el(doc, 'span', 'cx-field__cov',
      `마킹 ${countText(f.caseN)}/${countText(f.caseOf)} · 나머지 ${countText(f.controlN)}/${countText(f.controlOf)}`));
    if (f.blind) item.appendChild(el(doc, 'span', 'cx-field__flag', '귀속 0 — 순위에 기여 못 함'));
    if (f.highCardinality) {
      item.appendChild(el(doc, 'span', 'cx-field__flag',
        `값 ${countText(f.distinctValues)}종 — 사실상 식별자`));
    }
    if (f.numericMessage) item.appendChild(el(doc, 'span', 'cx-field__note', f.numericMessage));
    list.appendChild(item);
  }
  box.appendChild(list);
  return box;
}

/**
 * A vs B — the two marked items' key metrics, side by side.
 *
 * 🔴 NO FETCH. Every number here is already in the answer the table was drawn
 * from, so the comparison is on screen the instant the second lot is ticked —
 * before the walk that fills the ranking below has returned.
 *
 * 🔴 AND EACH METRIC SAYS 공통 OR 차이 FOR ITSELF. That is the owner's framing
 * ("공통점·차이점 대조"), computed by comparing the two readings rather than
 * asserted. 미검사 on either side is neither — it is 「대조 불가」, because a
 * comparison against something nobody measured is not a finding.
 */
/**
 * THE DOOR TO THE JOURNEY VIEW.
 *
 * 🔴 A VIEW WITH NO ENTRANCE IS A VIEW NOBODY USES. The journey was reachable
 * only by typing its URL. The rail already appears at two marks and already knows
 * the pair, so it is the door — no new screen, no nav link for an address that
 * has no answer without a scope.
 *
 * 🔴 AND IT IS A REAL `href`, not a click handler. The delegated router carries it
 * without a reload, middle-click opens a tab, and the link is copyable — the same
 * rule as every other control on this console.
 *
 * 🔴 IT APPEARS ONLY WHEN THE PAIR IS A PAIR OF SUBJECTS. The journey takes
 * exactly two subjects; two marks on the LOT axis resolve to fifty wafers and the
 * route answers 422. A link that lands on a refusal is worse than no link, because
 * the refusal reads as breakage — so on any other axis this says why instead.
 */
function renderJourneyDoor(doc, pair, subjectKey) {
  const box = el(doc, 'div', 'cx-door');
  box.setAttribute('data-panel', 'journey-door');
  // Unknown subject key = the contrast has not answered yet. Say nothing rather
  // than guess: the door appears a moment later with the rest of the rail.
  if (!subjectKey) return null;

  if (pair.axis !== subjectKey) {
    box.className = 'cx-door cx-door--blocked';
    box.setAttribute('data-door', 'wrong-axis');
    box.appendChild(el(doc, 'span', 'cx-door__why',
      `여정 대조는 ${subjectKey} 축 전용 — 지금 축은 한 열이 주어 여럿입니다`));
    return box;
  }

  const a = el(doc, 'a', 'cx-door__go');
  a.setAttribute('href',
    `?view=journey&scope=${encodeURIComponent(`${pair.axis}:${pair.a.row},${pair.b.row}`)}`);
  a.setAttribute('data-door', 'journey');
  a.appendChild(el(doc, 'span', 'cx-door__label', '여정 대조'));
  a.appendChild(el(doc, 'span', 'cx-door__hint', '어디까지 같은 길, 어디서 갈림 →'));
  box.appendChild(a);
  return box;
}

function renderPair(doc, pair, subjectKey) {
  const box = el(doc, 'section', 'cx-pair');
  box.setAttribute('data-panel', 'pair');

  const head = el(doc, 'div', 'cx-pair__head');
  const name = (side, key) => {
    const s = el(doc, 'div', `cx-pair__who cx-pair__who--${key}`);
    s.setAttribute('data-pair-side', key);
    s.appendChild(el(doc, 'span', 'cx-pair__tag', key.toUpperCase()));
    s.appendChild(el(doc, 'span', 'cx-pair__lot', side.lot));
    if (side.seq !== null) s.appendChild(el(doc, 'span', 'cx-pair__seq', `#${side.seq}`));
    return s;
  };
  head.appendChild(name(pair.a, 'a'));
  head.appendChild(el(doc, 'span', 'cx-pair__vs', 'vs'));
  head.appendChild(name(pair.b, 'b'));
  box.appendChild(head);

  const table = el(doc, 'table', 'cx-pair__table');
  const tbody = el(doc, 'tbody');
  for (const m of pair.metrics) {
    const tr = el(doc, 'tr', 'cx-pair__row');
    // 🔴 COMPARABLE IS NOT THE SAME AS `measured`. A count with no denominator is
    // still a count, and 465건 vs 430건 labelled 「대조 불가」 reads as a broken
    // panel. What genuinely cannot be compared is a side with NO VALUE — 미검사,
    // 미보고, 측정 불가 — because a comparison against something nobody measured
    // is not a finding.
    const has = (r) => r && r.value !== null && r.value !== undefined
      && r.state !== 'unscanned' && r.state !== 'unreported' && r.state !== 'unmeasurable';
    const readable = has(m.a) && has(m.b);
    // Equal to the precision the screen prints, not to float identity — two rates
    // that display the same number must not be labelled 차이.
    const same = readable && valueText(m.a.value, m.valueKind) === valueText(m.b.value, m.valueKind);
    const verdict = !readable ? 'unknown' : (same ? 'common' : 'differs');
    attrs(tr, { 'data-pair-metric': m.key, 'data-pair-verdict': verdict });

    const th = el(doc, 'th', 'cx-pair__metric');
    th.setAttribute('scope', 'row');
    th.appendChild(el(doc, 'span', 'cx-pair__metricname', m.label));
    th.appendChild(el(doc, 'span', 'cx-pair__metricagg', m.agg));
    tr.appendChild(th);

    const cell = (reading) => {
      const td = el(doc, 'td', 'cx-pair__v');
      if (!has(reading)) {
        td.className = 'cx-pair__v cx-pair__v--none';
        td.textContent = reading ? reading.text : '미보고';
        td.setAttribute('data-cell-state', reading ? reading.state : 'unreported');
      } else {
        td.textContent = valueText(reading.value, m.valueKind);
        td.setAttribute('data-cell-state', reading.state);
      }
      tr.appendChild(td);
    };
    cell(m.a);
    cell(m.b);

    const v = el(doc, 'td', `cx-pair__verdict cx-pair__verdict--${verdict}`);
    v.textContent = verdict === 'common' ? '공통' : (verdict === 'differs' ? '차이' : '대조 불가');
    tr.appendChild(v);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  box.appendChild(table);
  if (!pair.metrics.length) {
    box.appendChild(el(doc, 'p', 'cx-empty', '열이 없어 비교할 지표가 없습니다'));
  }
  // The door to the fuller answer, right under the two-metric comparison.
  const door = renderJourneyDoor(doc, pair, subjectKey);
  if (door) box.appendChild(door);
  return box;
}

/**
 * 🔴 THREE OR MORE IS NOT SILENTLY SOMETHING ELSE.
 *
 * The pair view is v1 and group contrast is the next increment. A panel that
 * quietly compared the first two, or quietly showed only the group ranking under
 * a pair heading, would be the screen deciding something the reader did not ask
 * for. It says so instead — and the group ranking below is still real, so nothing
 * is hidden either.
 */
function renderTooMany(doc, n) {
  const box = el(doc, 'p', 'cx-toomany');
  box.setAttribute('data-toomany', String(n));
  box.textContent = `${countText(n)}개 선택됨 — A/B 대조는 두 개까지입니다. `
    + '두 개만 남기면 지표 비교가 나옵니다 (그룹 대조는 다음 증분).';
  return box;
}

export function renderContrast(doc, mount, model, notice, pair) {
  clear(mount);
  const root = el(doc, 'section', 'cx');
  const n = model.askedScope.values.length;
  attrs(root, {
    'data-panel': 'contrast',
    'data-state': model.state,
    'data-marks': String(n),
    'data-mode': pair ? 'pair' : (n > 2 ? 'too-many' : 'single'),
  });

  const head = el(doc, 'header', 'cx-head');
  head.appendChild(el(doc, 'h3', 'cx-head__h',
    // 🔴 THE UNIT COMES FROM THE AXIS, NEVER THE WORD 「랏」 — 「그냥 랏이란 단위를
    // 잊으라 그래」. The lot is a value here, not a unit.
    pair ? `A vs B — 두 ${model.scope.axisLabel || '주어'} 대조`
      : `마킹한 ${countText(n)}개 ${model.scope.axisLabel || '주어'} — 무엇이 다른가`));
  head.appendChild(el(doc, 'p', 'cx-head__sub',
    pair
      ? '위: 표에 있는 지표를 나란히. 아래: 둘을 묶어 나머지 전체와 걷기 대조.'
      : '마킹한 쪽과 나머지 전체를 걷어서 나온 차이를, 관문 셋으로 채점해 순위로. 마킹을 바꾸면 이 답이 바뀝니다.'));
  if (model.engine) {
    const eng = el(doc, 'span', 'cx-head__engine', `엔진 ${model.engine}`);
    eng.setAttribute('data-engine', model.engine);
    head.appendChild(eng);
  }
  root.appendChild(head);

  // The pair comparison comes FIRST and costs no request — it is on screen before
  // the walk below returns.
  if (pair) root.appendChild(renderPair(doc, pair, model.subject.key));
  else if (n > 2) root.appendChild(renderTooMany(doc, n));

  if (notice) root.appendChild(renderNotice(doc, notice));
  root.appendChild(renderScope(doc, model));
  // 🔴 THE LEGEND SITS AT THE HEAD, ABOVE THE ROWS IT EXPLAINS. It used to be at
  // the bottom, which is the same as not being there for a reader who did not
  // already know the words.
  root.appendChild(renderGateLegend(doc, model));

  // 🔴 A SAMPLED CONTROL GROUP, SAID BESIDE THE NUMBERS IT CHANGES.
  if (model.walk.controlSampled) {
    const w = el(doc, 'p', 'cx-walk');
    attrs(w, {
      'data-control-sampled': '1',
      'data-sample-step': model.walk.sampleStep === null ? null : String(model.walk.sampleStep),
    });
    w.textContent = `대조군 표본 — ${countText(model.walk.controlSubjects)}/`
      + `${countText(model.walk.controlAvailable)} 주어`
      + (model.walk.sampleStep !== null ? ` (매 ${model.walk.sampleStep}번째)` : '')
      + (model.walk.message ? ` · ${model.walk.message}` : '');
    root.appendChild(w);
  }

  root.appendChild(renderTruncation(doc, model));

  if (!model.candidates.length) {
    root.appendChild(el(doc, 'p', 'cx-empty',
      model.state === 'ready'
        ? '차이 후보 없음 — 걷어서 나온 것 중 채점을 통과한 요인이 없습니다'
        : '대조 응답 없음 — 순위를 그릴 근거가 없습니다'));
  } else {
    // The fold discipline: this box scrolls, the page does not grow.
    const listWrap = el(doc, 'div', 'cx-listwrap');
    listWrap.setAttribute('data-panel', 'contrast-list');
    const split = splitCandidates(model.candidates);
    listWrap.appendChild(renderGroup(doc, 'differs', '차이점',
      '마킹한 쪽에만 몰린 것 — 갈라놓은 후보', split.differs, model));
    listWrap.appendChild(renderGroup(doc, 'common', '공통점',
      '마킹한 것들이 똑같이 지나간 것 — 함께 의심', split.common, model));
    // Shown only when it has members: an empty third group is a heading that
    // explains nothing, but a hidden non-empty one is a dropped row.
    if (split.rest.length) {
      listWrap.appendChild(renderGroup(doc, 'rest', '그 외',
        '마킹 쪽에서 갈리지도, 전부 공유하지도 않은 것', split.rest, model));
    }
    root.appendChild(listWrap);
  }
  if (model.fields.length) root.appendChild(renderFields(doc, model));

  for (const note of model.notes) {
    const p = el(doc, 'p', 'cx-note', note.message || note.note);
    p.setAttribute('data-note', note.note);
    root.appendChild(p);
  }

  if (model.generatedAt) {
    root.appendChild(el(doc, 'p', 'cx-generated', `대조 시각 ${model.generatedAt}`));
  }
  mount.appendChild(root);
  return root;
}
