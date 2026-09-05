// PROGRESS CARD — 「모르는 진행률」을 0% 로 그리지 않는지, 그리고 끝난 카드가 안 되돌아가는지.
//
// The subject is imported (owner, 2026-09-02: 잘라쓰기 하니스 절대 금지). The module touches
// the DOM inside its functions only, so a minimal `document` stub is enough to import it.
//
// 🔴 THE TWO THIS FILE EXISTS FOR:
//   ① AN UNKNOWN PERCENTAGE IS NOT ZERO. A replay can run with no total at all
//      (`retroactive_runs.total_rows` is NULL on rows that exist), and a 0% bar says
//      "nothing has happened yet" about something that may be nearly done. The bar is a
//      LENGTH: with no number there is nothing to draw, so it is not drawn.
//   ② A FINISHED CARD DOES NOT REOPEN. A late progress message must not undo a completion,
//      or the operator watches a done thing start again.
//
// Run: node client2/tests/progress_card_harness.mjs

// 최소 DOM. 부품이 «함수 안에서만» DOM 을 만지므로 이만큼이면 import 됩니다.
const byId = Object.create(null);
function makeEl(tag) {
  const el = {
    tagName: String(tag).toUpperCase(), _id: '', className: '', style: {},
    children: [], innerHTML: '', textContent: '', parentElement: null,
    get id() { return this._id; },
    set id(v) { this._id = String(v); byId[this._id] = this; },
    appendChild(c) { this.children.push(c); c.parentElement = this; return c; },
    remove() {
      const p = this.parentElement;
      if (p) p.children.splice(p.children.indexOf(this), 1);
      if (this._id) delete byId[this._id];
    },
    querySelector() { return null; },
  };
  el.classList = {
    _s: new Set(),
    add(...c) { c.forEach((x) => this._s.add(x)); },
    contains(c) { return this._s.has(c); },
  };
  return el;
}
globalThis.document = {
  __byId: byId,
  body: makeEl('body'),
  createElement: makeEl,
  getElementById: (id) => byId[id] || null,
};
const { showProgressCard } = await import('../src/progress_card.js');

let pass = 0;
const failures = [];
function ok(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS ${name}`); }
  else { failures.push(name); console.log(`  FAIL ${name} ${detail}`); }
}

const reset = () => {
  document.body.children.length = 0;
  for (const k of Object.keys(byId)) delete byId[k];
};

console.log('\n[1] an unknown percentage is not zero');
{
  reset();
  const card = showProgressCard({ key: 'r1', title: 'T', subtitle: 's', progress: null,
                                  processed: 12, total: null, statsSuffix: ' 행' });
  const html = card.innerHTML;
  ok('the percent slot is a dash, not 0%', html.includes('—') && !html.includes('>0%<'),
    html.slice(0, 160));
  // 🔴 막대는 «길이»입니다. 모르면 그릴 것이 없어서 상자째 «안 나옵니다».
  ok('the bar is not drawn at all', !html.includes('progress-bar-container'));
  ok('...and an unknown count is a dash too', html.includes('12 / —'));

  reset();
  const known = showProgressCard({ key: 'r2', title: 'T', progress: 40, processed: 4, total: 10 });
  ok('a known percentage still draws its bar', known.innerHTML.includes('width: 40%'));
  ok('...and prints the number', known.innerHTML.includes('>40%<'));
  ok('...and the bar box is back', known.innerHTML.includes('progress-bar-container'));
}

console.log('\n[2] completion is not judged from a number nobody sent');
{
  reset();
  const c = showProgressCard({ key: 'r3', title: 'T', progress: undefined,
                               processed: null, total: null });
  ok('an unknown run is not marked complete', !c.classList.contains('status-success'));
  ok('...and is not queued for dismissal', !c.classList.contains('status-auto-dismiss'));

  reset();
  const done = showProgressCard({ key: 'r4', title: 'T', progress: 100, doneTitle: 'D' });
  ok('a hundred is complete', done.classList.contains('status-success'));
  ok('...and is marked for dismissal', done.classList.contains('status-auto-dismiss'));

  // ⚠️ 전체 수를 아는 실행은 «처리 수가 전체에 닿으면» 완료입니다 (백분율이 늦어도).
  reset();
  const byRows = showProgressCard({ key: 'r6', title: 'T', progress: 90,
                                    processed: 10, total: 10 });
  ok('reaching the total is complete even below 100%',
    byRows.classList.contains('status-success'));
}

console.log('\n[3] a finished card does not reopen');
{
  reset();
  const first = showProgressCard({ key: 'r5', title: 'A', progress: 100, doneTitle: 'D' });
  const before = first.innerHTML;
  const after = showProgressCard({ key: 'r5', title: 'B', progress: 5 });
  // ⚠️ 「제목이 바뀌었나」로는 못 잽니다 — 이 스텁은 innerHTML 을 다시 파싱하지 않아
  //    그건 «스텁»을 재는 것이 됩니다. 재는 것은 「다시 그렸나」입니다.
  ok('a late progress message redraws nothing', after.innerHTML === before);
  ok('...and the card stays successful', after.classList.contains('status-success'));
}

console.log('\n[4] the part carries no domain word - and the one place that still does');
{
  const fs = await import('node:fs');
  const raw = fs.readFileSync(new URL('../src/progress_card.js', import.meta.url), 'utf-8');
  const code = raw.replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n').map((l) => l.replace(/\/\/.*$/, '')).join('\n');

  // \u26a0\ufe0f 이름 «둘»은 도메인 낱말이 아니라 «못 바꾸는 이름»입니다:
  //    `progress-filename` 은 CSS 클래스, `ingestion-progress-container` 는 DOM id 이고
  //    둘 다 스타일시트가 붙잡고 있습니다. 바꾸면 마크업이 «달라집니다» — 이 이사의 조건이
  //    「전후로 같은 것을 그린다」라서, 이름은 그대로 두는 것이 맞습니다.
  for (const word of ['tableName', '파일', '리플레이', 'replay']) {
    ok(`no "${word}" anywhere in the part's code`, !code.includes(word));
  }
  ok('the two domain-shaped names are the CSS class and the DOM id, nothing else',
    (code.match(/filename/g) || []).length === 1
    && (code.match(/ingestion/g) || []).length === 1
    && code.includes('progress-filename') && code.includes('ingestion-progress-container'));

  // \U0001f534 그리고 «하나»가 진짜로 남아 있습니다 — 접힌 카드의 요약 문구입니다.
  //    「그 외 N건 «적재» 중」은 파일 인제션의 낱말이고, 둘째 소비자가 붙으면 «틀립니다».
  //    지금은 소비자가 하나라 «거짓이 아니»지만, 고치려면 「접기 요약을 누구 말로 쓸까」를
  //    정해야 하고 그건 판정입니다. 그래서 여기서 «세어» 둡니다 — 하나보다 늘면 빨개집니다.
  ok('the overflow summary is the ONE place still speaking a domain word',
    (code.match(/적재/g) || []).length === 1 && code.includes('건 적재 중'));
}

console.log(`\n════ RESULT: ${pass} passed, ${failures.length} failed ════`);
console.log(`ASSERTIONS ${pass + failures.length} ${failures.length}`);
process.exit(failures.length === 0 ? 0 : 1);
