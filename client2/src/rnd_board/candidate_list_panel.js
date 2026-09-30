// ═══════════════════════════════════════════════════════════════════════════════
// 부품 F — 후보 리스트. 명세 §8.
//
// 🔴 THIS PART EXISTS TO KEEP TWO THINGS APART: a candidate an engineer can go and LOOK at,
//    and a name `mechanism_models.json` declares. Measured on the live seed that is 4 against
//    21. If they look alike the engineer walks to one of the 21 and finds nothing there, and
//    then this screen is used once and abandoned.
//
//    It is drawn TWO ways on purpose, because one of them is colour and colour dies in a theme:
//      1. every card states 「실측」 -- either what it reaches, or `-`
//      2. the name-only ones are COLLAPSED into a single card that says how many
//    The mockup does the same, and the second is the one that survives a palette change.
//
// 🔴 IT DRAWS NO CONCLUSION AND SORTS NOTHING. Rank comes from the server; `tied` rows keep the
//    same number. A part that renumbered them would invent an order nobody computed.
//
// 🔴 NO SIZE CONSTANT.
// ═══════════════════════════════════════════════════════════════════════════════

import { WalkedListPanel, markingIntent } from './panel.js';
import { SIGN } from './marking_store.js';
import { UNPICKED } from '../absent.js';
import { WALKING, SERVER_REFUSED, NO_VALUE } from '../ui_words.js';

export class CandidateListPanel extends WalkedListPanel {
  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    // 🔴 THE CURSOR MUST NOT MOVE. A re-render rebuilds this panel's box, and a rebuilt box
    //    starts at scrollTop 0 -- so the row under the pointer jumps away on the very click
    //    that opened it. The owner named this: 「접힌거 펴지면서 좌표 바껴서 마우스 위치 옮겨야」.
    //    The position is carried across; the fold stays inside this panel's own cell.
    const kept = this.host.firstElementChild;
    const scrollTop = kept ? kept.scrollTop || 0 : 0;
    const place = (node) => { this.host.appendChild(node); node.scrollTop = scrollTop; };
    this.host.textContent = '';
    const root = doc.createElement('div');
    // 🔴 ATTENUATION, not decoration (the owner's Spotfire, measured): while something is
    //    marked the rest FADES. Nothing fades while nothing is marked -- 「아직 안 골랐다」
    //    and 「이건 아니다」 are different sentences. The dimming itself is CSS, so it is one
    //    rule per part rather than a colour computed here.
    // 🔴 ATTENUATE ONLY WHEN SOMETHING OF MINE IS MARKED. A name is shared, so another
    //    panel writing an id of its own kind would otherwise fade every row here while
    //    none of them lit up.
    const mineMarked = (this.model && this.model.candidates || []).map((c) => c.id)
      .some((id) => id && this.signOf(id) !== SIGN.ABSENT);
    root.className = mineMarked ? 'rb-cand is-attenuating' : 'rb-cand';
    // 🔴 THE PANEL SAYS WHAT IT IS. The declaration carries a title and the shell hands it
    //    over; only the map drew it, so four panels stood unnamed on the screen and a
    //    reader had to infer the subject from the content. It is STICKY: a title that
    //    scrolls away is a title you cannot check while reading row 20.
    if (this.title) {
      const cap = doc.createElement('div');
      cap.className = 'rb-part-title';
      cap.textContent = this.title;
      root.appendChild(cap);
    }

    if (this.loadState !== 'ready' || !this.model || !this.model.ok) {
      root.appendChild(this._note());
      place(root);
      return;
    }

    const m = this.model;

    // ── the header count. Says what the walk found, and what it did NOT do ──────
    const head = doc.createElement('div');
    head.className = 'rb-cand-head';
    head.appendChild(this._stat(`Candidates ${m.counts.total}`, 'fact'));
    head.appendChild(this._stat(`Measured ${m.counts.measured}`, 'fact'));
    head.appendChild(this._stat(`Name only ${m.counts.nameOnly}`, 'absent'));
    // 🔴 「안 쟀다」 is not 「깨끗했다」. It is stated, in its own words, and never in red.
    if (m.contrast === 'unexamined') {
      head.appendChild(this._stat('No controls · unexamined', 'absent'));
    }
    // 🔴 `!m.complete` 는 «모름»(null)까지 「끊김」으로 만듭니다. 끊긴 것만 말합니다.
    if (m.complete === false) {
      head.appendChild(this._stat('Cut at budget · the rest not walked', 'absent'));
    }
    // 🔴 «잘렸다고 말하는 것»이 자르는 것보다 먼저입니다 (총괄 판정 2026-08-24). 지금 응답은
    //    세 웨이퍼 전부 `truncated: ['depth']` 인데 화면은 아무 말도 안 했습니다 -- 그러면
    //    「보이드 60개인 웨이퍼」와 「208개인데 60개만 실려 온 웨이퍼」가 «같아 보입니다».
    //    서버가 «어디서» 잘렸는지 말해 주므로 그 낱말을 그대로 답니다.
    // 🔴 목업은 부류를 «다섯»으로 나눕니다 (계측 · 모델 · 공정 split · 사고 · 코멘트).
    //    이 walk 은 앞의 둘만 싣습니다 -- 나머지 셋은 «없는 것»이 아니라 «안 오는 것»이고,
    //    이름을 대야 그 차이가 읽힙니다.
    head.appendChild(this._stat('Process split · incidents · comments — not in this walk', 'absent'));
    if (Array.isArray(m.truncated) && m.truncated.length) {
      head.appendChild(this._stat(`Truncated at ${m.truncated.join(' · ')} · may be more`, 'absent'));
    }

    root.appendChild(head);

    // 🔴 «닿았는데 0» 도 말해야 합니다. state 가 ready 이고 후보만 0 이면 지금까지는 「후보 0」
    //    한 줄뿐이었는데, 그건 「씨앗이 틀렸다」와 «같아 보입니다». 실측(2026-08-24): 이 웨이퍼의
    //    walk 은 노드 386(wafer · Claim · die)에 닿고 물리량 후보만 0 입니다 -- 전혀 다른 사실입니다.
    if (m.state !== 'empty' && !m.candidates.length && m.graph) {
      root.appendChild(this._line(
        `Nodes ${m.graph.nodes} · edges ${m.graph.edges} — walked, no quantity candidate`, 'absent'));
    }
    if (m.state === 'empty') {
      // NOT 「원인 없음」. The walk did not reach a quantity; that is a fact about the walk.
      // 🔴 TWO FACTS, SEPARATELY. `ranked: []` for THIS collect is not 「nothing is here」:
      // the walk reached nodes and edges, it just found no cause candidate of this kind.
      // Saying only the second denies a transfer that actually happened.
      const reached = `Nodes ${m.graph.nodes} · edges ${m.graph.edges}`;
      root.appendChild(this._line(`${reached} — no cause candidate`, 'absent'));
      place(root);
      return;
    }

    // ── the cards. Measured ones individually; the rest folded into one ─────────
    const grid = doc.createElement('div');
    grid.className = 'rb-cand-grid';
    for (const c of m.candidates) {
      if (!c.measured) continue;
      grid.appendChild(this._card(c));
    }
    if (m.counts.nameOnly > 0) {
      grid.appendChild(this._folded(m.counts.nameOnly));
    }
    root.appendChild(grid);
    place(root);
  }

  _card(c) {
    const doc = this.doc;
    const el = doc.createElement('div');
    el.className = 'rb-cand-card';
    if (c.id) {
      el.setAttribute('data-node-id', c.id);
      const sign = this.signOf(c.id);
      if (sign === SIGN.CASE) el.classList.add('is-marked-case');
      else if (sign === SIGN.CONTROL) el.classList.add('is-marked-control');
      el.addEventListener('click', (event) => {
        const intent = markingIntent(event);
        this.mark(c.id, intent.sign, intent.mode);
      });
    }

    const top = doc.createElement('div');
    top.className = 'rb-cand-card-top';
    const rank = doc.createElement('span');
    rank.className = 'rb-cand-rank';
    rank.textContent = c.rank === null ? '-' : String(c.rank);
    top.appendChild(rank);
    // Each of these is a DIFFERENT absence/state and gets its own chip. None is an error.
    if (c.top) top.appendChild(this._tag('Top', 'top'));
    if (c.tied) top.appendChild(this._tag('Tied', 'absent'));
    // 🔴 «어느 마킹으로» 찍혔는지. 파란 배경만으로는 이름을 못 읽고, 이 화면의 요점이
    //    「마킹 1 과 마킹 2 는 다른 질문」이라는 것입니다.
    if (c.id && this.writes && this.signOf(c.id) !== SIGN.ABSENT) {
      top.appendChild(this._tag(this.writes, 'top'));
    }
    if (c.incomparable) top.appendChild(this._tag('Incomparable', 'absent'));
    el.appendChild(top);

    // 🔴 TWO LINES. Merging the quantity and the model states a claim nobody made.
    const q = doc.createElement('div');
    q.className = 'rb-cand-quantity';
    q.textContent = c.quantity;
    const mdl = doc.createElement('div');
    mdl.className = 'rb-cand-model';
    mdl.textContent = c.model || '-';
    el.append(q, mdl);
    // No measured line: only measured candidates get a card, and the head already says Measured N
    // (lead 919ccc065 - the dash arm nobody took went with it).
    return el;
  }

  _folded(count) {
    const el = this.doc.createElement('div');
    el.className = 'rb-cand-card rb-cand-card--folded';
    const t = this.doc.createElement('div');
    t.className = 'rb-cand-quantity';
    t.textContent = `Name only ${count}`;
    const d = this.doc.createElement('div');
    d.className = 'rb-cand-model';
    d.textContent = `${NO_VALUE} · no trend`;
    el.append(t, d);
    return el;
  }

  _tag(text, kind) {
    const el = this.doc.createElement('span');
    el.className = `rb-cand-tag rb-cand-tag--${kind}`;
    el.textContent = text;
    return el;
  }

  _stat(text, kind) {
    const el = this.doc.createElement('span');
    el.className = `rb-cand-stat rb-cand-stat--${kind}`;
    el.textContent = text;
    return el;
  }

  _line(text, kind) {
    const el = this.doc.createElement('div');
    el.className = `rb-cand-line rb-cand-line--${kind}`;
    el.textContent = text;
    return el;
  }

  _note() {
    const state = this.loadState;
    const refused = state === 'refused';
    const el = this.doc.createElement('div');
    el.className = refused ? 'rb-cand-line rb-cand-line--refused' : 'rb-cand-line rb-cand-line--absent';
    el.textContent = state === 'no-seed' ? UNPICKED
      : state === 'loading' ? WALKING
      : (this.model && this.model.message) || SERVER_REFUSED;
    return el;
  }
}
