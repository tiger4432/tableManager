// ============================================================
// journey_view.js — 여정 대조를 DOM으로.
//
// `document`가 인자다. 전역이 아니다 — 그래야 이 렌더러를 그대로 노드에서
// 돌려 «화면에 실제로 무엇이 닿는지»를 볼 수 있다. 여기 있는 모든 것은 노드를
// 짓고 `textContent`를 넣는다. `innerHTML`은 한 번도 쓰지 않으므로 원장에서
// 나온 장비 id가 마크업이 되는 일은 없다.
//
// 그리기만 한다 — 페치도, 상태도, 판단도 없다. 무엇이 갈라졌는지는 서버의
// 답이고(`/api/ledger/journey`), 그게 어떻게 읽히는지는 `journey_core.js`다.
//
// 🔴 링크는 진짜 `href`다. 콘솔에는 origin·pathname으로 가로채는 위임
// 라우터가 있어서, 여기서 핸들러를 달지 않아야 페이지가 리로드되지 않는다.
// 프래그먼트(`#…`)만은 라우터가 브라우저에 넘기므로 배지 → 구간 스크롤이
// 공짜로 동작한다.
// ============================================================
import './journey.css';
import {
  SIX_ORDER, sideText, gapText, gateChip, citationText, sentenceTail,
  structureHref, mechanismHref,
} from './journey_core.js';

function el(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function link(doc, className, text, href) {
  const a = doc.createElement('a');
  if (className) a.className = className;
  if (text !== undefined && text !== null) a.textContent = String(text);
  a.setAttribute('href', href);
  return a;
}

function clear(mount) {
  while (mount.firstChild) mount.removeChild(mount.firstChild);
}

/**
 * 구간 이름 — 그리고 같은 공정을 두 번 지났으면 회차까지.
 *
 * 🔴 이 두 장은 플라즈마 세정을 두 번, 본딩을 두 번 지난다. 회차 없이는 축에
 * 똑같은 줄이 두 개 서고, 조작자는 어느 본딩을 보고 있는지 알 수 없다.
 */
function stepName(doc, seg, className) {
  const wrap = el(doc, 'span', className);
  wrap.appendChild(el(doc, 'span', 'jv-step__name', seg.display));
  if (seg.runText) wrap.appendChild(el(doc, 'span', 'jv-step__run', seg.runText));
  return wrap;
}

// ── 머리 ─────────────────────────────────────────────────────

/**
 * 제목 · 두 주어 · 한 줄 요약 · 갈림 배지.
 *
 * 🔴 요약 문장은 서버의 `headline` 그대로다. 클라가 구간을 다시 세면 언젠가
 * 두 수가 어긋나고, 어긋난 날 화면 위에서는 어느 쪽이 맞는지 알 수 없다.
 */
function renderHead(doc, model) {
  const head = el(doc, 'header', 'jv-head');

  const title = el(doc, 'div', 'jv-head__title');
  title.appendChild(el(doc, 'span', 'jv-head__name', '여정 대조'));
  const sub = el(doc, 'span', 'jv-head__sub');
  const parts = [model.pairText];
  if (model.headline) parts.push(model.headline);
  sub.textContent = parts.filter(Boolean).join(' · ');
  title.appendChild(sub);
  head.appendChild(title);

  // 결과 — 두 주어가 무엇을 얼마나 맞았는지. 이 화면이 «왜» 열렸는지의 근거다.
  const outcomes = el(doc, 'div', 'jv-head__outcomes');
  let anyOutcome = false;
  for (const s of model.subjects) {
    if (!s.outcome) continue;
    anyOutcome = true;
    const chip = el(doc, 'span', 'jv-outcome');
    chip.setAttribute('data-subject', s.id);
    chip.appendChild(el(doc, 'span', 'jv-outcome__id', s.label));
    const found = s.outcome.found;
    const scanned = s.outcome.scanned;
    const text = found === null
      ? '기록 없음'
      : `${s.outcome.label} ${found}${scanned === null ? '' : ` / ${scanned}`}`;
    chip.appendChild(el(doc, 'span', found === null ? 'jv-outcome__n jv-outcome__n--none' : 'jv-outcome__n', text));
    outcomes.appendChild(chip);
  }
  if (anyOutcome) head.appendChild(outcomes);

  if (model.badges.length) {
    const row = el(doc, 'nav', 'jv-badges');
    row.setAttribute('aria-label', '갈라진 구간');
    for (const b of model.badges) {
      // 프래그먼트뿐인 href — 라우터가 손대지 않고 브라우저가 스크롤한다.
      const a = link(doc, `jv-badge jv-badge--${b.tone}`, b.text, `#${b.anchor}`);
      a.setAttribute('data-segment', b.key);
      row.appendChild(a);
    }
    head.appendChild(row);
  }
  return head;
}

// ── 접힌 줄 ──────────────────────────────────────────────────

/**
 * 같은 구간 — 회색 한 줄. 숨기는 게 아니다.
 *
 * 🔴 접힘의 기준은 «동일성 일치»(장비·레시피·rev)이고, 그 한 줄은 밑에 남은
 * 차이를 «이름으로» 말한다. 실데이터에서 바이트까지 같은 구간은 여덟 중 0개라
 * 엄밀 일치로 접으면 여덟 장이 전부 카드로 열린다 — 이 설계가 벗어나려던
 * 그 더미다. 반대로 155.712와 154.152를 「같음」이라 부르는 것은 작은
 * 거짓말이다. 그래서 접힌 줄은 «밑에 있는 것 전부를 회계하는» 한 줄이고,
 * 열면 그 회계의 낱개가 나온다 — 잘림 안내·맵 요약과 같은 규율이다.
 */
function renderFolded(doc, model, seg) {
  const box = el(doc, 'details', 'jv-fold');
  box.id = seg.anchor;
  box.setAttribute('data-segment', seg.key);
  box.setAttribute('data-shape', 'folded');

  const head = el(doc, 'summary', 'jv-fold__line');
  head.appendChild(el(doc, 'span', 'jv-dot jv-dot--same'));
  head.appendChild(stepName(doc, seg, 'jv-fold__step'));
  // 서버의 회계 문장 그대로 — 「같음: 장비 … · 레시피 rev 6 · 수치 4건 차이 (기전 2건)」
  head.appendChild(el(doc, 'span', 'jv-fold__rest',
    seg.agreement.sentence || seg.foldLine || '같음'));
  box.appendChild(head);

  const body = el(doc, 'div', 'jv-fold__body');
  if (seg.positionInferred) body.appendChild(renderInferredWarning(doc));

  // 같은 것들 — 이름과 값. 「같음」도 정보다.
  if (seg.agreement.agreeingActors.length) {
    const same = el(doc, 'div', 'jv-facts');
    same.appendChild(el(doc, 'span', 'jv-facts__term', '같음'));
    for (const a of seg.agreement.agreeingActors) {
      const chip = el(doc, 'span', 'jv-chip jv-chip--same');
      chip.appendChild(el(doc, 'span', 'jv-chip__k', a.display));
      chip.appendChild(el(doc, 'span', 'jv-chip__v', a.text));
      same.appendChild(chip);
    }
    body.appendChild(same);
  }

  // 남은 차이의 낱개 — 접힌 줄이 수로만 말한 것을 여기서 이름으로 편다.
  if (seg.cards.length) {
    const diff = el(doc, 'div', 'jv-fold__diffs');
    diff.appendChild(el(doc, 'div', 'jv-facts__term', '차이'));
    for (const item of seg.cards) diff.appendChild(renderItem(doc, model, seg, item, 'row'));
    body.appendChild(diff);
  }

  body.appendChild(renderSegmentFoot(doc, model, seg));
  box.appendChild(body);
  return box;
}

// ── 한쪽만 걸은 구간 ─────────────────────────────────────────

/**
 * 결측은 상태다 — 빈칸도, 회색 침묵도 아니다.
 *
 * 카드가 아니라 한 줄인 이유: 한쪽에 값이 없으면 «차이»가 아니다. 원인 카드와
 * 같은 크기로 그리면 없는 비교를 있는 것처럼 읽게 된다. 그래도 접힌 줄과 같은
 * 규율로 열리며, 열면 여섯 물음이 그대로 나온다.
 */
function renderMissing(doc, model, seg) {
  const box = el(doc, 'details', 'jv-miss');
  box.id = seg.anchor;
  box.setAttribute('data-segment', seg.key);
  box.setAttribute('data-shape', 'missing');

  const head = el(doc, 'summary', 'jv-miss__line');
  head.appendChild(el(doc, 'span', 'jv-dot jv-dot--miss'));
  head.appendChild(stepName(doc, seg, 'jv-fold__step'));
  // 🔴 서버의 문장, 클라의 재조립이 아니다. 이 구간의 항목은 여섯이고 그중
  // 다섯은 장비·레시피·부기다 — 카드 목록의 첫 줄을 집어 오면 줄이 「장비
  // SYN-MI-01」이 되고, 브리핑이 요구한 「#06 측정 없음 · #15 748.41µm」은
  // 사라진다(스모크에서 실제로 그렇게 났다). 서버는 이미 계측을 이름으로
  // 지목한 문장을 보내 준다.
  const tail = sentenceTail(seg);
  const rest = el(doc, 'span', 'jv-miss__rest');
  rest.appendChild(el(doc, 'span', 'jv-side', tail || '한쪽만 기록됨'));
  head.appendChild(rest);
  head.appendChild(el(doc, 'span', 'jv-tag jv-tag--miss', '결측은 상태'));
  box.appendChild(head);

  const body = el(doc, 'div', 'jv-fold__body');
  if (seg.positionInferred) body.appendChild(renderInferredWarning(doc));
  // 사실 문장은 접힌 줄이 이미 들고 있다 — 여기서 다시 쓰지 않는다. 펼침은
  // 그 한 줄이 «회계한» 낱개를 보여 주는 자리다.
  for (const item of seg.cards) body.appendChild(renderItem(doc, model, seg, item, 'row'));
  body.appendChild(renderSegmentFoot(doc, model, seg));
  box.appendChild(body);
  return box;
}

// ── 갈라진 구간 = 카드 ───────────────────────────────────────

/**
 * 카드의 첫 줄은 «언제나» 사실 문장이다 — 그리고 그 문장은 서버가 썼다.
 * 클라가 값에서 문장을 다시 조립하면 술어마다 전용 조립 코드가 생기고, 그러면
 * 처음 보는 술어에서만 못생겨진다. 부칙: 「카드는 원자 봉투의 직역이어야 한다」.
 */
function renderCard(doc, model, seg) {
  const card = el(doc, 'article', 'jv-card');
  card.id = seg.anchor;
  card.setAttribute('data-segment', seg.key);
  card.setAttribute('data-shape', 'card');
  card.appendChild(el(doc, 'span', 'jv-dot jv-dot--diverged'));

  // 어디서 — 축 위의 자리 그 자체. 클릭하면 구조 뷰의 그 술어로 간다.
  const where = el(doc, 'div', 'jv-card__where');
  const deep = structureHref(model.subjectType, seg);
  const a = link(doc, 'jv-card__step', null, deep.href);
  a.appendChild(el(doc, 'span', 'jv-step__name', seg.display));
  if (seg.runText) a.appendChild(el(doc, 'span', 'jv-step__run', seg.runText));
  a.setAttribute('data-deeplink', deep.resolved ? 'edge' : 'view');
  if (!deep.resolved) a.setAttribute('title', '구조 뷰로 이동 — 그 자리 하이라이트는 서버 필드 대기 중');
  where.appendChild(a);
  if (seg.when && seg.when.gapSeconds !== null) {
    where.appendChild(el(doc, 'span', 'jv-card__gap', gapText(seg.when.gapSeconds)));
  }
  card.appendChild(where);

  if (seg.positionInferred) card.appendChild(renderInferredWarning(doc));

  // 🔴 첫 줄 = 사실 문장.
  if (seg.sentence) card.appendChild(el(doc, 'p', 'jv-card__fact', seg.sentence));

  // 이 구간에서 «같았던» 것 — 카드 안에서도 회계는 닫힌다.
  if (seg.agreement.agreeingActors.length) {
    const same = el(doc, 'div', 'jv-card__same');
    same.appendChild(el(doc, 'span', 'jv-facts__term', '같음'));
    for (const act of seg.agreement.agreeingActors) {
      const chip = el(doc, 'span', 'jv-chip jv-chip--same');
      chip.appendChild(el(doc, 'span', 'jv-chip__k', act.display));
      chip.appendChild(el(doc, 'span', 'jv-chip__v', act.text));
      same.appendChild(chip);
    }
    card.appendChild(same);
  }

  for (const item of seg.cards) card.appendChild(renderItem(doc, model, seg, item, 'card'));
  card.appendChild(renderSegmentFoot(doc, model, seg));
  return card;
}

// ── 한 항목 ──────────────────────────────────────────────────

/**
 * 값 나란히 + 관문 + 여섯 물음.
 *
 * 🔴 편향 후보는 «절대» 원인과 같은 급으로 그리지 않는다. `rank`가 그것을
 * 맨 아래로 보내고, `data-rank="bias"`가 색을 죽이고, 「발생 아님」 꼬리표가
 * 이름으로 말한다. 셋 중 하나만으로는 부족하다 — 색만 죽이면 흑백 인쇄에서
 * 같은 급이 되고, 꼬리표만 달면 위에 있는 한 먼저 읽힌다.
 */
function renderItem(doc, model, seg, item, kind) {
  const rankName = item.rank === 2 ? 'bias' : (item.rank === 0 ? 'causal' : 'plain');
  const row = el(doc, 'div', `jv-item jv-item--${kind} jv-item--${rankName}`);
  row.setAttribute('data-rank', rankName);
  row.setAttribute('data-verdict', item.verdict);
  // 딥링크의 기계 손잡이 — 속성으로만 산다. 화면에 글자로 나가지 않는다.
  if (item.candidateKey) row.setAttribute('data-candidate', item.candidateKey);

  const top = el(doc, 'div', 'jv-item__top');
  top.appendChild(el(doc, 'span', 'jv-item__what', item.display));
  if (item.biasCandidate) top.appendChild(el(doc, 'span', 'jv-tag jv-tag--bias', '발생 아님'));
  if (item.labelState && item.labelState !== 'declared') {
    // 라벨 선언이 없으면 원시 이름이 그대로 보인다 — 정직 우선(orchard 규칙).
    top.appendChild(el(doc, 'span', 'jv-tag jv-tag--raw', '라벨 선언 없음'));
  }
  row.appendChild(top);

  // 값 — 나란히. 굵은 것은 값이지 이름이 아니다.
  const vals = el(doc, 'div', 'jv-vals');
  const sides = [
    { s: item.A, subj: model.subjects[0] },
    { s: item.B, subj: model.subjects[1] },
  ];
  for (const { s, subj } of sides) {
    const cell = el(doc, 'span', s && s.present ? 'jv-val' : 'jv-val jv-val--none');
    cell.appendChild(el(doc, 'span', 'jv-val__id', subj ? subj.label : ''));
    cell.appendChild(el(doc, 'b', 'jv-val__n', sideText(s)));
    if (s && s.present && s.claimClassLabel) {
      cell.appendChild(el(doc, 'span', 'jv-val__cls', s.claimClassLabel));
    }
    if (s && !s.present && s.message) {
      cell.appendChild(el(doc, 'span', 'jv-val__why', s.message));
    }
    vals.appendChild(cell);
  }
  row.appendChild(vals);

  // 관문 — 응답이 «선언한» 것만. n=2에 성립하는 둘뿐이고, 배수·신뢰구간·
  // 「우연 아님」은 이 화면에 아예 없다.
  const chips = el(doc, 'div', 'jv-gates');
  let anyGate = false;
  for (const axis of model.gates) {
    const chip = gateChip(axis, item.gates[axis.id]);
    if (!chip) continue;
    anyGate = true;
    const node = el(doc, 'span', `jv-gate jv-gate--${chip.tone}`, chip.text);
    node.setAttribute('data-gate', chip.id);
    node.setAttribute('data-verdict', chip.tone);
    if (chip.title) node.setAttribute('title', chip.title);
    chips.appendChild(node);
  }
  // 「물리 경로 있음」의 딥링크 — 경로를 이름으로 말하고 기전 그래프로 보낸다.
  const mech = item.gates.mechanism;
  if (mech && item.mechanismPath) {
    const target = mechanismHref(mech.model);
    const a = link(doc, 'jv-gates__link', `${item.mechanismPath} 경로 보기 →`, target.href);
    a.setAttribute('data-deeplink', 'mechanism');
    if (!target.resolved) a.setAttribute('title', '기전 그래프로 이동 — 모형 앵커는 구조 뷰 대기 중');
    chips.appendChild(a);
    anyGate = true;
  }
  if (anyGate) row.appendChild(chips);

  row.appendChild(renderSix(doc, item));
  return row;
}

// ── 육하원칙 ─────────────────────────────────────────────────

/**
 * 여섯 물음 — 답하거나, 답이 «없다»고 말하거나.
 *
 * 🔴 미답을 숨기지 않는다. 라이브 응답에서 94장 중 왜가 답하는 것은 9장뿐이고,
 * 나머지 85장은 「물리 모델에 아직 없음」이다. 그 85장을 감추면 화면이 완결돼
 * 보이지만, 완결돼 보이는 것이 이 화면의 목적이 아니다.
 *
 * 🔴 그리고 두 「없음」은 «같은 색이면 안 된다».
 *   - `missing`  : 원장의 결측 — 우리가 안 적었다.
 *   - `undeclared`: 선언의 부재 — 물리 모델이 아직 이 필드를 모른다.
 * 부칙 정정이 못박은 층 구분이 화면에서 색과 문구 둘 다로 살아 있어야 한다.
 */
function renderSix(doc, item) {
  const box = el(doc, 'details', 'jv-six');
  const head = el(doc, 'summary', 'jv-six__head');
  head.appendChild(el(doc, 'span', 'jv-six__label', '여섯 물음'));
  const missing = item.sixUnanswered.length;
  head.appendChild(el(doc, 'span', missing ? 'jv-six__n jv-six__n--gap' : 'jv-six__n',
    missing ? `답 ${6 - missing}/6` : '답 6/6'));
  box.appendChild(head);

  const list = el(doc, 'dl', 'jv-six__list');
  for (const id of SIX_ORDER) {
    const slot = item.six[id];
    if (!slot) continue;
    const term = el(doc, 'dt', 'jv-six__q', slot.question);
    if (slot.isDeclaration) term.appendChild(el(doc, 'span', 'jv-six__layer', '선언'));
    list.appendChild(term);

    const val = el(doc, 'dd', `jv-six__a jv-six__a--${slot.tone}`);
    val.setAttribute('data-slot', id);
    val.setAttribute('data-state', slot.state);
    val.setAttribute('data-tone', slot.tone);
    val.appendChild(el(doc, 'span', 'jv-six__text', slot.text || '기록 없음'));
    // 왜는 언제나 인용 표기다 — 원장 필드처럼 «사실»로 그리면 층 위반이다.
    if (slot.isDeclaration) {
      const cite = citationText(slot);
      if (cite) val.appendChild(el(doc, 'span', 'jv-six__cite', cite));
    }
    list.appendChild(val);
  }
  box.appendChild(list);
  return box;
}

// ── 구간 꼬리 ────────────────────────────────────────────────

/** 이 구간이 회계한 항목 수 — 카드에 안 뜬 것이 몇 개인지 언제나 말한다. */
function renderSegmentFoot(doc, model, seg) {
  const foot = el(doc, 'div', 'jv-seg__foot');
  const c = seg.itemCounts;
  const bits = [];
  if (c.total !== null) bits.push(`항목 ${c.total}`);
  if (c.same) bits.push(`같음 ${c.same}`);
  if (c.diverged) bits.push(`다름 ${c.diverged}`);
  if (c.oneSided) bits.push(`한쪽만 ${c.oneSided}`);
  foot.appendChild(el(doc, 'span', 'jv-seg__counts', bits.join(' · ')));
  const deep = structureHref(model.subjectType, seg);
  const a = link(doc, 'jv-seg__deep', '구조 뷰에서 보기 →', deep.href);
  a.setAttribute('data-deeplink', deep.resolved ? 'edge' : 'view');
  foot.appendChild(a);
  return foot;
}

function renderInferredWarning(doc) {
  return el(doc, 'p', 'jv-warn',
    '자리 근거: 추론 원자 — 순서를 물리 순서로 읽지 말 것');
}

// ── 알림 ─────────────────────────────────────────────────────

function renderNotice(doc, notice) {
  if (!notice) return null;
  const box = el(doc, 'div', `jv-notice jv-notice--${notice.tone || 'idle'}`);
  box.setAttribute('data-tone', notice.tone || 'idle');
  box.appendChild(el(doc, 'div', 'jv-notice__title', notice.title || ''));
  if (notice.detail) box.appendChild(el(doc, 'p', 'jv-notice__detail', String(notice.detail)));
  return box;
}

/**
 * 거절 — 그리고 이것도 «답»이다.
 *
 * 여정 대조는 주어 2개 전용이다. 마킹이 하나로 풀렸다는 사실은 감출 오류가
 * 아니라 조작자가 알아야 하는 결과이고, 서버가 «무엇으로 풀렸는지»를 이름으로
 * 말해 주므로 화면도 그 이름을 그대로 보여 준다.
 */
function renderRefusal(doc, model) {
  const box = el(doc, 'div', 'jv-notice jv-notice--gap');
  box.setAttribute('data-tone', 'gap');
  const r = model.refused;
  box.appendChild(el(doc, 'div', 'jv-notice__title', '여정 대조는 주어 2개 전용'));
  if (r.message) box.appendChild(el(doc, 'p', 'jv-notice__detail', r.message));
  if (r.arityResolved !== null) {
    const facts = el(doc, 'div', 'jv-facts');
    facts.appendChild(el(doc, 'span', 'jv-facts__term', '해결된 주어'));
    facts.appendChild(el(doc, 'span', 'jv-facts__val',
      `${r.arityResolved}${r.arityRequired === null ? '' : ` / 필요 ${r.arityRequired}`}`));
    box.appendChild(facts);
  }
  if (r.subjects.length) {
    const list = el(doc, 'div', 'jv-facts');
    list.appendChild(el(doc, 'span', 'jv-facts__term', '이름'));
    for (const s of r.subjects) list.appendChild(el(doc, 'span', 'jv-chip jv-chip--same', s));
    box.appendChild(list);
  }
  return box;
}

// ── 다리 ─────────────────────────────────────────────────────

/**
 * 화면 밑의 규율 한 줄 — 그리고 이 화면이 «하지 않는» 것의 선언.
 *
 * 🔴 집단 통계 부재를 말없이 두지 않는다. 두 장에는 배수도 신뢰구간도 없고,
 * 서버는 그것을 null이 아니라 «부재»로 보낸다. 화면이 그 사실을 한 칩으로
 * 말해야 조작자가 「왜 배수가 없지」를 결함으로 오해하지 않는다.
 */
function renderLegend(doc, model) {
  const foot = el(doc, 'footer', 'jv-legend');

  const rules = el(doc, 'p', 'jv-legend__rule',
    '같은 구간은 한 줄로 접힘 · 갈라진 구간만 카드 · 구간명 클릭 = 구조 뷰의 그 자리');
  foot.appendChild(rules);

  const chips = el(doc, 'div', 'jv-legend__chips');
  if (model.statistics.notApplicable) {
    const chip = el(doc, 'span', 'jv-legend__chip', `주어 ${model.arity === null ? 2 : model.arity} — 집단 통계 없음`);
    if (model.statistics.message) chip.setAttribute('title', model.statistics.message);
    chip.setAttribute('data-statistics', 'not_applicable');
    chips.appendChild(chip);
  }
  if (model.summary.foldBasis) {
    const seg = model.segments.find((s) => s.agreement.basisLabel);
    chips.appendChild(el(doc, 'span', 'jv-legend__chip',
      `접힘 기준 — ${seg ? seg.agreement.basisLabel : model.summary.foldBasis}`));
  }
  if (model.mechanism && model.mechanism.state) {
    chips.appendChild(el(doc, 'span', 'jv-legend__chip',
      `기전 선언 ${model.mechanism.state === 'declared' ? '있음' : model.mechanism.state}`
      + (model.mechanism.bindingCount === null ? '' : ` · 결합 ${model.mechanism.bindingCount}`)));
  }
  if (chips.childNodes.length) foot.appendChild(chips);

  // 서버가 남긴 주석 — 「자리가 추론에서 왔다」·「편향 후보를 원인으로 읽지 말 것」.
  for (const note of model.notes) {
    foot.appendChild(el(doc, 'p', 'jv-legend__note', note.message));
  }

  const twoKinds = el(doc, 'p', 'jv-legend__rule');
  twoKinds.appendChild(el(doc, 'span', 'jv-swatch jv-swatch--missing'));
  twoKinds.appendChild(el(doc, 'span', 'jv-legend__k', '기록 없음 — 원장의 결측'));
  twoKinds.appendChild(el(doc, 'span', 'jv-swatch jv-swatch--undeclared'));
  twoKinds.appendChild(el(doc, 'span', 'jv-legend__k', '선언의 부재 — 물리 모델에 아직 없음'));
  foot.appendChild(twoKinds);

  return foot;
}

// ── 진입점 ───────────────────────────────────────────────────

/**
 * @param doc     document (인자다 — 전역이 아니다)
 * @param mount   그릴 곳
 * @param model   `journeyModel` 출력
 * @param notice  `{tone, title, detail}` 또는 null
 */
export function renderJourney(doc, mount, model, notice) {
  if (!mount) return;
  clear(mount);
  const root = el(doc, 'section', 'jv');
  root.setAttribute('data-state', model ? model.state : 'absent');

  const note = renderNotice(doc, notice);
  if (note) root.appendChild(note);

  if (model && model.refused) {
    root.appendChild(renderRefusal(doc, model));
    mount.appendChild(root);
    return;
  }

  if (!model || !model.served) {
    if (!note) {
      root.appendChild(renderNotice(doc, {
        tone: 'idle',
        title: '두 장을 고르면 여정이 열립니다',
        detail: '트렌드 화면에서 웨이퍼 2장을 마킹하세요 — 여정 대조는 주어 2개 전용입니다',
      }));
    }
    mount.appendChild(root);
    return;
  }

  root.appendChild(renderHead(doc, model));

  const axis = el(doc, 'div', 'jv-axis');
  axis.setAttribute('data-segments', String(model.segments.length));
  for (const seg of model.segments) {
    if (seg.shape === 'folded') axis.appendChild(renderFolded(doc, model, seg));
    else if (seg.shape === 'missing') axis.appendChild(renderMissing(doc, model, seg));
    else axis.appendChild(renderCard(doc, model, seg));
  }
  if (!model.segments.length) {
    axis.appendChild(el(doc, 'div', 'jv-empty', '공유하는 구간 없음 — 두 주어가 겹치는 공정이 원장에 없습니다'));
  }
  root.appendChild(axis);

  root.appendChild(renderLegend(doc, model));
  mount.appendChild(root);
}
