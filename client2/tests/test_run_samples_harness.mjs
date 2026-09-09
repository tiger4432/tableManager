/**
 * 🏷️ C-49 — 시험 실행의 «거절 표본»이 화면에 닿나. 뷰를 IMPORT 해서 렌더합니다.
 *
 * 🔴 THE PURE HALF IS SCORED IN `refusal_cell_harness.mjs`. This one answers the other
 *    question, and it is the one an argument cannot settle: 「그 줄이 정말 그려지나」.
 *    The response carried `refused.samples` all along and the screen drew only the count,
 *    so 「몇 건」 was visible and 「어느 행이」 was not — and no assertion noticed, because
 *    every assertion was about the count.
 *
 * 🔴 THE CONTROLS ARE THE POINT. A box that appears is not evidence that the SAMPLES made
 *    it appear, and a note that appears is not evidence that TRUNCATION put it there. Both
 *    are paired with a run that differs in exactly that one field.
 *
 * Run: node client2/tests/test_run_samples_harness.mjs
 */
let ran = 0;
let failed = 0;
const ok = (name, cond, detail = '') => {
  ran += 1;
  if (cond) console.log(`  PASS ${name}`);
  else { failed += 1; console.log(`  FAIL ${name}${detail ? ' — ' + detail : ''}`); }
};
const eq = (name, expected, actual) => ok(name, actual === expected,
  `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);

// --- the stub the view's `h()` needs, same shape the authoring harness uses ----------
function element(tag) {
  const node = {
    tagName: String(tag).toUpperCase(), children: [], attrs: Object.create(null),
    _text: '', _classes: [], dataset: Object.create(null), title: '',
    style: { setProperty() {} },
    get className() { return this._classes.join(' '); },
    set className(v) { this._classes = String(v).split(/\s+/).filter(Boolean); },
    classList: {
      add(...names) { for (const n of names) if (!node._classes.includes(n)) node._classes.push(n); },
      contains(name) { return node._classes.includes(name); },
    },
    append(...items) { for (const item of items) if (item) this.children.push(item); },
    appendChild(child) { this.children.push(child); return child; },
    replaceChildren(...items) { this.children = items.filter(Boolean); },
    setAttribute(key, value) { this.attrs[String(key)] = String(value); },
    getAttribute(key) {
      return Object.prototype.hasOwnProperty.call(this.attrs, String(key))
        ? this.attrs[String(key)] : null;
    },
    querySelector() { return null; },
    addEventListener() {},
    set textContent(value) { this._text = String(value); this.children = []; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  return node;
}
globalThis.document = { createElement: element, createDocumentFragment: () => element('#fragment') };
globalThis.requestAnimationFrame = (fn) => fn();

const { renderOntologyExplorer } = await import('../src/ontology_explorer_view.js');
const { initialExplorerState } = await import('../src/ontology_explorer_store.js');

const walk = (node, out = []) => { out.push(node); for (const c of node.children || []) walk(c, out); return out; };
const byClass = (root, name) => walk(root).filter((n) => n._classes?.includes(name));

// 🔴 THE FIXTURE IS THE SERVER'S OWN SHAPE. `config_explorer_service.py:723` builds each
//    sample from a `MoleculeRefusal` (reason · detail · rows · addresses) and
//    `source_preparation.py:991` writes the address as `event_frame.rows[N].<column>`.
//    ⚠️ THE SENTENCE HOLDS THE MOLECULE KEY and no field does — that is why it is carried
//    whole rather than parsed.
const DETAIL = "molecule ('DTJ-1',) declares 'event_time' and the row at "
  + 'event_frame.rows[3].event_time leaves it empty';
const SAMPLE = {
  reason: 'missing_occurred_at', rows: 2, detail: DETAIL,
  addresses: [{ code: 'source_preparation_incomplete',
                path: 'event_frame.rows[3].event_time' }],
};
const draw = (refused) => {
  const root = element('div');
  renderOntologyExplorer(root, {
    ...initialExplorerState,
    selection: { canonical_id: 'dt_job', kind: 'source_plan', config_path: 'sources.dt_job',
                 compile_status: 'valid', raw: {}, compiled: {} },
    testRun: { status: 'refused', relation: 'dt_job', rows_read: 200, molecules: 0,
               atoms: 0, refused },
  });
  return root;
};

console.log('\n[1] the samples reach the screen');
{
  const root = draw({ count: 2, reasons: { missing_occurred_at: 2 },
                      samples: [SAMPLE, { ...SAMPLE, reason: 'no_identity', rows: 1,
                        addresses: [{ code: 'source_preparation_incomplete',
                                      path: 'event_frame.rows[7].dt_job' }] }] });
  eq('the test run is drawn at all', 1, byClass(root, 'oe-testrun').length);
  eq('the sample box is drawn', 1, byClass(root, 'oe-testrun-samples').length);
  eq('one line per sample', 2, byClass(root, 'oe-testrun-sample').length);

  const first = byClass(root, 'oe-testrun-sample')[0];
  eq('the reason is a cell of its own', 'missing_occurred_at',
    byClass(first, 'oe-testrun-why')[0]?.textContent);
  eq('...and rides the row as data, for anything selecting on it',
    'missing_occurred_at', first.dataset.reason);
  eq('the row count is a cell of its own', '2',
    byClass(first, 'oe-testrun-rows')[0]?.textContent);
  eq('the server\'s address is a cell of its own', 'event_frame.rows[3].event_time',
    byClass(first, 'oe-testrun-path')[0]?.textContent);
  // 🔴 THE SECOND ROW HAS ITS OWN ADDRESS. One line repeated is what a loop bug looks like
  //    on screen, and it points the operator at a row that is not the broken one.
  eq('the second line points somewhere else', 'event_frame.rows[7].dt_job',
    byClass(byClass(root, 'oe-testrun-sample')[1], 'oe-testrun-path')[0]?.textContent);

  // ⛔ 문구 상설: the gatekeeper's sentence is a TOOLTIP, not a paragraph in the table.
  eq('the sentence is carried whole, in the tooltip', DETAIL, first.title);
  ok('...and is NOT spilled into the visible row',
    !first.textContent.includes('leaves it empty'), first.textContent);

  // 🔴 THE COUNT LINE SURVIVES. The table is 「어느 행이」, added BESIDE 「몇 건」 --
  //    replacing the summary would trade one half of the answer for the other.
  ok('the head still says how many, by name',
    root.textContent.includes('거절 2') && root.textContent.includes('missing_occurred_at 2'),
    root.textContent.slice(0, 120));
}

console.log('\n[2] the controls — what makes the box appear, and what makes the note appear');
{
  // 🔴 CONTROL ①: refusals counted, no samples sent. If the box still drew, block [1]
  //    would be proving that a test run renders, not that the SAMPLES render.
  const noSamples = draw({ count: 5, reasons: { missing_occurred_at: 5 }, samples: [] });
  eq('a run with no samples draws no sample box', 0,
    byClass(noSamples, 'oe-testrun-samples').length);
  ok('...though it still says how many were refused',
    noSamples.textContent.includes('거절 5'));

  // 🔴 CONTROL ②: the same two samples, `count` the only difference. 「20 이 전부」 and
  //    「20 까지만 봤다」 are different answers and the server sends no flag for it here.
  const exact = draw({ count: 1, reasons: { missing_occurred_at: 1 }, samples: [SAMPLE] });
  const capped = draw({ count: 40, reasons: { missing_occurred_at: 40 }, samples: [SAMPLE] });
  eq('an untruncated run says nothing about a cap', 1,
    byClass(exact, 'oe-testrun-samples')[0].children.length);
  eq('...and a truncated one says how far it looked, as a value', '1 건까지',
    byClass(capped, 'oe-testrun-samples')[0].children[0].textContent);
  ok('the two are different pixels',
    byClass(exact, 'oe-testrun-samples')[0].children.length
      !== byClass(capped, 'oe-testrun-samples')[0].children.length);

  // ⚠️ AN OLDER SERVER SENDS NO `refused` AT ALL. That is 「안 물어봤다」, and it must not
  //    draw an empty table that reads as 「거절 없음」.
  const older = draw(undefined);
  eq('a response with no refused key draws no sample box', 0,
    byClass(older, 'oe-testrun-samples').length);
  eq('...and the test run is still drawn', 1, byClass(older, 'oe-testrun').length);
}

console.log(`\n════ RESULT: ${ran - failed} passed, ${failed} failed ════`);
console.log(`ASSERTIONS ${ran} ${failed}`);
process.exit(failed === 0 ? 0 : 1);
