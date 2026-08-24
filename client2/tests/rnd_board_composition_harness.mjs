/**
 * rnd_board — 부품 A (머리 요약) · 부품 D (구성) 계약 채점
 *
 * WHAT THIS SCORES is the five acceptance conditions the Lead PM set, and it scores them the
 * way round 1 did: every named assertion is woken by a MUTANT modelled on a real defect, so a
 * green line means "this was looked at", not "this was skipped".
 *
 *   A  two instances on one screen do not interfere
 *   B  the read name and the write name are declared SEPARATELY
 *   C  no module-level state
 *   D  the part follows the box it is handed (no baked size)
 *   E  an absence is drawn as an absence, never as a fault
 *
 * 🔴 THE POSITIVE CONTROL IS THE POINT OF SECTION C. A source scan that cannot find a defect
 *    it was written for is decoration. C2 runs the same scan over a file that HAS module-level
 *    state and requires it to be found; if C2 ever goes quiet, C1 means nothing.
 *
 * 🔴 THE SOURCES ARE CARRIED WITH THE MODULES, not re-read from disk. Round 1 learned this the
 *    hard way: a scan reading the shipped file while the suite drives a mutated copy is blind
 *    to every mutant.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BOARD_DIR = path.join(HERE, '..', 'src', 'rnd_board');
const dataUrl = (src) => `data:text/javascript;base64,${Buffer.from(src, 'utf8').toString('base64')}`;

// A trimmed copy of the live payload shape, taken from
// `GET /api/ledger/composition?final_chip_id=SYN-CX-CHIP-001` (2026-08-23).
const BODY = {
  state: 'ready',
  final_chip: { entity_id: 'final_chip:SYN-CX-CHIP-001', keys: { final_chip_id: 'SYN-CX-CHIP-001' } },
  final_subject_resolution: {
    state: 'resolved',
    basis: 'transferred.to.bond_layer.keys.bond_wafer',
    candidates: [{ wafer: 'SYN-CX-BW-001' }],
    wafer: { wafer: 'SYN-CX-BW-001', entity_id: 'wafer:SYN-CX-BW-001' },
  },
  window: { requested: null, defaulted: true, applied: { declared: true, spec: '365d', from: 'A', to: 'B' } },
  cardinality: { components: 'variable', transfer_events: 'variable', dt_collections: 'variable' },
  provenance: { source: 'ledger_events', predicate: 'transferred', ledger_backed: true },
  summary: { component_count: 10, dt_collection_count: 18, core_types: ['HBM', 'LOGIC'] },
  components: [
    { entity_id: 'component:C1', component_id: 'CHIP:L01', resolution_state: 'resolved',
      core: { wafer: 'W1', slot: '03', type: 'HBM' }, transfer_events: [1, 2, 3], dt_collections: [1, 2] },
    { entity_id: 'component:C2', component_id: 'CHIP:L02', resolution_state: 'unresolved',
      core: null, transfer_events: [], dt_collections: [] },
  ],
};

async function loadModules(mutate = {}) {
  const sources = {};
  const read = (file) => {
    const text = readFileSync(path.join(BOARD_DIR, file), 'utf8')
      .replace(new RegExp(String.fromCharCode(13, 10), 'g'), String.fromCharCode(10));
    const fn = mutate[file];
    // 🔴 A MUTATION THAT CHANGES NOTHING IS A MUTANT THAT TESTS NOTHING, and it reads as a
    // pass. The first run of this file shipped two of those. An anchor that no longer matches
    // now stops the run instead of going quietly green.
    const out = fn ? fn(text) : text;
    if (fn && out === text) throw new Error(`mutation anchor is GONE: ${file}`);
    sources[file] = out;
    return sources[file];
  };
  const storeUrl = dataUrl(read('marking_store.js'));
  const apiUrl = dataUrl(read('api.js'));
  const panelUrl = dataUrl(read('panel.js').replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  // 표 부품은 이제 «다른 부품 안»에 삽니다 -- 그래서 여기서도 배선됩니다.
  const tableUrl = dataUrl(read('table_part.js')
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  const rewire = (file) => dataUrl(read(file)
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`)
    .replaceAll("'./table_part.js'", `'${tableUrl}'`)
    .replaceAll("'./api.js'", `'${apiUrl}'`));
  const table = await import(tableUrl);
  const layer = await import(rewire('expanded_layer_panel.js'));
  const head = await import(rewire('head_summary_panel.js'));
  const comp = await import(rewire('composition_panel.js'));
  const store = await import(storeUrl);
  return { head, comp, layer, store, table, sources };
}

// ── the DOM stub. Same shape round 1 used: a part must be scorable under bare node ──
function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(),
    className: '', style: {}, children: [], attrs: Object.create(null),
    listeners: Object.create(null), _text: '', parentNode: null,
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    append(...cs) { for (const c of cs) this.appendChild(c); },
    setAttribute(k, v) { this.attrs[String(k)] = String(v); if (String(k) === 'class') this.className = String(v); },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attrs, String(k)) ? this.attrs[String(k)] : null; },
    addEventListener(t, fn) { (this.listeners[t] ||= []).push(fn); },
    click() { for (const fn of this.listeners.click || []) fn(); },
    get classList() {
      const self = this;
      return {
        add(...cs) { self.className = [...new Set(String(self.className).split(/\s+/).filter(Boolean).concat(cs))].join(' '); },
        contains(c) { return String(self.className).split(/\s+/).includes(c); },
      };
    },
    set textContent(v) { this._text = String(v); this.children.length = 0; },
    get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); },
  };
  return node;
}
const makeDoc = () => { const doc = { createElement: (t) => makeNode(doc, t) }; return doc; };
const walk = (n, out = []) => { out.push(n); for (const c of n.children || []) walk(c, out); return out; };
const byClass = (root, cls) => walk(root).filter((n) => String(n.className || '').split(/\s+/).includes(cls));
const flush = () => new Promise((r) => setTimeout(r, 0));
const okFetch = () => async () => ({ ok: true, status: 200, json: async () => BODY });
const refuseFetch = (status) => async () => ({ ok: false, status, json: async () => ({ detail: 'no' }) });

async function suite(mods) {
  const { head, comp, layer, store, table, sources } = mods;
  const ran = [];
  const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    const g = JSON.stringify(got); const w = JSON.stringify(want);
    if (g !== w) failures.push(`${name}: got ${g}, want ${w}`);
  };
  const truthy = (name, got) => eq(name, Boolean(got), true);

  // ── A. two instances, one screen ──────────────────────────────────────────────
  const doc = makeDoc();
  const markings = new store.MarkingStore();
  const hostA = doc.createElement('div');
  const hostB = doc.createElement('div');
  const a = new comp.CompositionPanel(hostA, { doc, markings, reads: 'marking:1', writes: 'marking:1', apiBase: '', finalChipId: 'CHIP-A', fetchImpl: okFetch() });
  const b = new comp.CompositionPanel(hostB, { doc, markings, reads: 'marking:2', writes: 'marking:2', apiBase: '', finalChipId: 'CHIP-B', fetchImpl: okFetch() });
  a.mount(); b.mount();
  await flush(); await flush();

  eq('A1 both instances drew their own rows', [byClass(hostA, 'rb-table-row').length, byClass(hostB, 'rb-table-row').length], [2, 2]);
  eq('A2 each kept its own subject', [a.finalChipId, b.finalChipId], ['CHIP-A', 'CHIP-B']);
  // 🔴 The interference test: marking through A must not mark B, because they declared
  // different names. Round 1's M2 (a hardcoded name) dies exactly here.
  // 🔴 CLICK THE ONE THAT WRITES `marking:2`. Clicking A proves nothing: a part with a
  // HARDCODED 'marking:1' produces the same counts, which is exactly how M1 escaped the first
  // time this suite ran. The discriminating input is the instance whose name is NOT the
  // hardcoded one.
  byClass(hostB, 'rb-table-row')[0].click();
  await flush();
  eq('A3 a part writes the name IT declared, not a fixed one',
    [markings.count('marking:2'), markings.count('marking:1')], [1, 0]);

  // ── B. read name and write name are separate ──────────────────────────────────
  // The premise, stated rather than inherited: put ONE mark under the name this part reads.
  // A3 marks `marking:2`, so leaning on it would make B2 depend on another section's side
  // effect -- and that is how an assertion quietly stops meaning what its name says.
  markings.set('marking:1', 'component:C2', 1);
  const hostRO = doc.createElement('div');
  const readOnly = new comp.CompositionPanel(hostRO, { doc, markings, reads: 'marking:1', writes: null, apiBase: '', finalChipId: 'C', fetchImpl: okFetch() });
  readOnly.mount(); await flush(); await flush();
  // 🔴 MEMBERS, NOT A COUNT. The count was a proxy and it went blind the day a click began by
  //    CLEARING the name: a rogue write that removes one mark and adds another leaves the count
  //    exactly where it was. So the row that was clicked must be absent AND the mark that was
  //    already there must still be standing.
  const row = byClass(hostRO, 'rb-table-row')[0];
  const rowNode = row.getAttribute('data-node-id');
  row.click();
  eq('B1 a part with no write name cannot write',
    [markings.signOf('marking:1', rowNode), markings.signOf('marking:1', 'component:C2')],
    [0, 1]);
  truthy('B2 but it still SEES the name it reads',
    byClass(hostRO, 'rb-table-row').some((r) => r.classList.contains('is-marked-case')));

  // ── C. no module-level state ──────────────────────────────────────────────────
  const scan = (src) => (src.match(/^(let|var)\s+\w+|^const\s+\w+\s*=\s*(\[|\{(?!\s*\})|new\s)/gm) || []);
  eq('C1 head_summary_panel.js holds no module-level state', scan(sources['head_summary_panel.js']).length, 0);
  eq('C1b composition_panel.js holds no module-level state', scan(sources['composition_panel.js']).length, 0);
  // 🔴 POSITIVE CONTROL. If this goes quiet, C1 is decoration.
  const planted = 'let __session = 0;\nexport class X {}\n';
  truthy('C2 the same scan FINDS module-level state when it is there', scan(planted).length > 0);

  // ── D. follows the box it is handed ───────────────────────────────────────────
  const hostR = doc.createElement('div');
  const r = new comp.CompositionPanel(hostR, { doc, markings, reads: 'm', writes: 'm', apiBase: '', finalChipId: 'C', fetchImpl: okFetch() });
  r.mount(); await flush(); await flush();
  eq('D1 box starts unmeasured', [r.box.width, r.box.height], [0, 0]);
  r.resize(640, 300);
  eq('D2 the shell can hand over a box', [r.box.width, r.box.height], [640, 300]);
  r.resize(981, 412);
  eq('D3 and a size it never saw at mount', [r.box.width, r.box.height], [981, 412]);
  // No literal px in either part: a baked size is what makes a drag a rewrite.
  const pxLiterals = (src) => (src.match(/\b\d{2,4}px\b/g) || []);
  eq('D4 neither part contains a px constant',
    [pxLiterals(sources['head_summary_panel.js']).length, pxLiterals(sources['composition_panel.js']).length], [0, 0]);

  // ── E. an absence is not a fault ──────────────────────────────────────────────
  const hostH = doc.createElement('div');
  const h = new head.HeadSummaryPanel(hostH, { doc, markings, reads: 'marking:1', writes: null, apiBase: '', finalChipId: 'CHIP-A', fetchImpl: okFetch() });
  h.mount(); await flush(); await flush();
  const chips = byClass(hostH, 'rb-chip');
  const absent = chips.filter((c) => c.classList.contains('rb-chip--absent'));
  truthy('E1 the defaulted window is drawn as an absence', absent.some((c) => c.textContent.includes('기본값 적용')));
  truthy('E2 cardinality stays the word the ledger chose', absent.some((c) => c.textContent.includes('variable')));
  eq('E3 no absence is drawn with the refusal class', byClass(hostH, 'rb-head-note--refused').length, 0);
  // 🔴 THE CLAIM IS UNCHANGED, THE ADDRESS MOVED. 목업 2a puts 「어떻게 정해졌나」 beside the
  //    layers it explains, so the basis is drawn by the COMPOSITION panel now. Asserting it
  //    against the identity band would have kept scoring the old arrangement.
  {
    const hostR = doc.createElement('div');
    const cp = new comp.CompositionPanel(hostR, { doc, markings, reads: 'marking:1',
      writes: 'marking:1', apiBase: '', finalChipId: 'C', fetchImpl: okFetch() });
    cp.mount(); await flush(); await flush();
    truthy('E4 the resolution BASIS is shown, not just the verdict',
      byClass(hostR, 'rb-comp-resolution-val')
        .some((v) => v.textContent.includes('transferred.to.bond_layer')));
    truthy('E5 the candidate count stands beside it',
      byClass(hostR, 'rb-comp-resolution-key').some((k) => k.textContent === 'candidates'));
  }

  // A refusal, on the other hand, says so.
  const hostX = doc.createElement('div');
  const x = new head.HeadSummaryPanel(hostX, { doc, markings, reads: null, writes: null, apiBase: '', finalChipId: 'C', fetchImpl: refuseFetch(422) });
  x.mount(); await flush(); await flush();
  truthy('E5 a server refusal is drawn as a refusal', byClass(hostX, 'rb-head-note--refused').length === 1);
  truthy('E6 and it carries the status', hostX.textContent.includes('422'));

  // ── F. counts that were not sent are `-`, not 0 ───────────────────────────────
  const thin = JSON.parse(JSON.stringify(BODY));
  delete thin.summary.component_count;
  const hostT = doc.createElement('div');
  const t = new comp.CompositionPanel(hostT, { doc, markings, reads: 'm', writes: 'm', apiBase: '', finalChipId: 'C',
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => thin }) });
  t.mount(); await flush(); await flush();
  const counts = byClass(hostT, 'rb-comp-count-value').map((n) => n.textContent);
  truthy('F1 a count the server did not send prints as a dash', counts.includes('-'));
  truthy('F2 and a count it DID send prints as itself', counts.includes('18'));

  // ── T. 표 부품 «둘»이 한 화면에서 서로를 모릅니다 (소유자 상설 ①의 시험) ──────────
  {
    const { TablePart } = table;
    const store2 = new store.MarkingStore();
    const hostT1 = doc.createElement('div');
    const hostT2 = doc.createElement('div');
    // 🔴 두 «선언». 코드는 한 벌입니다.
    const t1 = new TablePart(hostT1, { doc, markings: store2, reads: 'm:1', writes: 'm:1',
      rowKey: 'id', columns: [{ key: 'id', label: '층', kind: 'mono' },
        { key: 'state', label: '상태', kind: 'badge' }],
      rows: [{ id: 'L01', state: 'resolved' }, { id: 'L02', state: 'contested' }] });
    const t2 = new TablePart(hostT2, { doc, markings: store2, reads: 'm:2', writes: 'm:2',
      rowKey: 'id', columns: [{ key: 'rank', label: '순위', kind: 'rank' },
        { key: 'q', label: '물리량 · 모델', kind: 'two_line', subKey: 'model' },
        { key: 'seen', label: '실측' }],
      rows: [{ id: 'C1', rank: '1', q: 'bond_temp', model: 'void_formation', seen: null }] });
    t1.mount(); t2.mount();
    eq('T1 the first table drew its own declaration', byClass(hostT1, 'rb-table-row').length, 2);
    eq('T2 the second drew a different one', byClass(hostT2, 'rb-table-row').length, 1);
    eq('T3 the heads are the declarations, not one shared header',
      [byClass(hostT1, 'rb-table-head')[0].textContent,
        byClass(hostT2, 'rb-table-head')[0].textContent],
      ['층상태', '순위물리량 · 모델실측']);
    // 🔴 간섭 없음: 하나를 마킹해도 다른 하나는 «자기 이름»만 봅니다.
    byClass(hostT1, 'rb-table-row')[0].click();
    eq('T4 marking one table does not mark the other',
      [byClass(hostT1, 'rb-table-row').filter((r) => String(r.className).includes('is-marked-case')).length,
        byClass(hostT2, 'rb-table-row').filter((r) => String(r.className).includes('is-marked-case')).length],
      [1, 0]);
    // 없는 값은 «없다고». 0 과 같은 픽셀이면 이 화면이 존재할 이유가 없습니다.
    truthy('T5 an absent cell says so instead of printing nothing',
      walk(hostT2).some((n) => n.getAttribute && n.getAttribute('data-col') === 'seen'
        && n.textContent === '-' && String(n.className).includes('is-absent')));
    t1.destroy(); t2.destroy();
  }

  // ── L. 펼친 층 — «찍은 층»만 펼칩니다 ─────────────────────────────────────────
  {
    const { ExpandedLayerPanel } = layer;
    const marks = new store.MarkingStore();
    const hostL = doc.createElement('div');
    const model = {
      ok: true,
      components: [
        { id: 'CHIP:L01', entityId: 'node:l01', core: { wafer: 'CW-1' },
          steps: [{ step: 'INGOT_RELEASE' }, { step: 'WAFER_SORT' }] },
        { id: 'CHIP:L02', entityId: 'node:l02', core: { wafer: 'CW-2' },
          steps: [{ step: 'CMP_BULK' }] },
      ],
    };
    const l = new ExpandedLayerPanel(hostL, { doc, markings: marks, reads: 'm:1', writes: null,
      walk: async () => model, finalChipId: 'CHIP' });
    l.mount();
    await flush(); await flush();
    // 🔴 넷 중 «첫째» 부재입니다 -- 「없다」가 아니라 「아직 안 골랐다」.
    truthy('L1 nothing marked says so instead of drawing a layer nobody chose',
      /층을 찍으면/.test(hostL.textContent) && !/INGOT_RELEASE/.test(hostL.textContent),
      hostL.textContent.slice(0, 60));
    marks.set('m:1', 'node:l02', store.SIGN.CASE);
    truthy('L2 the marked layer is the one that opens',
      /L02/.test(hostL.textContent) && /CMP_BULK/.test(hostL.textContent)
      && !/INGOT_RELEASE/.test(hostL.textContent), hostL.textContent.slice(0, 80));
    // claims 는 «표 부품»이고, 오늘은 경계가 events 를 안 실어 비어 있습니다 -- 그 이유를 말합니다.
    truthy('L3 the claims table says WHY it is empty rather than showing an empty box',
      /claim 이 없습니다/.test(hostL.textContent), hostL.textContent.slice(-80));
    l.destroy();
  }

  // ── H9. 고정 씨앗은 «자기가 고정임을» 말합니다 ─────────────────────────────────
  {
    const hostF = doc.createElement('div');
    const f = new head.HeadSummaryPanel(hostF, { doc, markings, reads: 'marking:1', writes: null,
      apiBase: '', finalChipId: 'CHIP-A', fetchImpl: okFetch() });
    f.mount();
    await flush(); await flush();
    truthy('H9 a fixed chip seed says it does not follow the marking',
      /고정 씨앗/.test(hostF.textContent), hostF.textContent.slice(0, 90));
    f.destroy();
  }

  return { ran, failures };
}

// ── the mutation corpus ────────────────────────────────────────────────────────────
const MUTANTS = [
  // 🔴 고정 씨앗이 «고정이라고 말하지 않으면», 맵이 다른 웨이퍼를 그리는 동안 이 패널의 값이
  //    「같이 따라온 것」으로 읽힙니다 -- 둘 다 사실인 척하는 화면이 제일 나쁩니다.
  { id: 'H-M1', what: 'the head hides that its chip is a fixed seed while the maps follow the marking',
    catches: 'H9',
    mutate: { 'head_summary_panel.js': (s) => s.replace(
      "        '칩', '고정 씨앗 — 마킹을 안 따릅니다 (웨이퍼→칩 엣지 대기)', 'absent'));",
      "        '칩', '', 'absent'));") } },
  // 🔴 마킹을 안 보고 «첫 층»을 펼치면, 아무것도 안 찍은 화면이 「이 층이 답」이라고 말합니다.
  { id: 'L-M1', what: 'the expanded layer opens the first component instead of the marked one',
    catches: 'L1',
    mutate: { 'expanded_layer_panel.js': (s) => s.replace(
      '    return list.find((c) => this.signOf(c.entityId || c.id) !== SIGN.ABSENT) || null;',
      '    return list[0] || null;') } },
  { id: 'T-M1', what: 'the table draws one hardcoded header instead of the declaration',
    catches: 'T3',
    mutate: { 'table_part.js': (s) => s.replace(
      "for (const col of this.columns) el.appendChild(this._cellEl(col, col.label || '', 'head'));",
      "for (const col of [{ key: 'x', label: '층' }]) el.appendChild(this._cellEl(col, col.label, 'head'));") } },
  { id: 'T-M2', what: 'an absent cell is drawn as an empty string, so 「없음」 and 「빈 값」 look alike',
    catches: 'T5',
    mutate: { 'table_part.js': (s) => s.replace(
      "  return value === null || value === undefined || value === '';",
      '  return false;') } },
  // 🔴 THE ANCHOR MOVED WHEN THE SELECTION MODEL LANDED. A plain click no longer goes through
  //    `toggle`, so hardcoding the name THERE stopped being reachable and this mutant sailed
  //    through green -- the assertion was fine, the mutation had stopped biting. It now sits on
  //    the path a click actually takes.
  { id: 'M1', what: 'the part reads a HARDCODED marking name', catches: 'A3',
    mutate: { 'panel.js': (s) => s.replace('return this.markings.set(this.writes, nodeId, sign);',
      "return this.markings.set('marking:1', nodeId, sign);") } },
  // ONE step, deliberately: this mutant used to be three, and when the first anchor rotted the
  // other two still changed the text, so the "did anything change" check passed while the module
  // died at runtime instead -- reported as INERT, which is the honest word for tested nothing.
  { id: 'M2', what: 'a part keeps its subject at MODULE level (the ledger_map_panel defect)', catches: 'A2',
    mutate: { 'composition_panel.js': (s) => s
      .replaceAll('this.finalChipId', 'globalThis.__subject') } },
  { id: 'M3', what: 'a part ignores the box the shell hands it', catches: 'D3',
    mutate: { 'panel.js': (s) => s.replace('this.box = { width: w, height: h };', '') } },
  { id: 'M4', what: 'a missing count is defaulted to 0 instead of stated as absent', catches: 'F1',
    mutate: { 'composition_panel.js': (s) => s.replace(
      "v.textContent = typeof value === 'number' ? String(value) : '-';",
      'v.textContent = String(value || 0);') } },
  { id: 'M5', what: 'a defaulted window is drawn with the refusal styling', catches: 'E1',
    mutate: { 'head_summary_panel.js': (s) => s.replace(
      "'기간', `기본값 적용", "'기간', 'refused', `기본값 적용") } },
  { id: 'M6', what: 'the write name is ignored so a read-only part can still write', catches: 'B1',
    mutate: { 'panel.js': (s) => s.replace('if (!this.writes || !this.markings) return SIGN.ABSENT;',
      "if (!this.markings) return SIGN.ABSENT; if (!this.writes) this.writes = 'marking:1';") } },
];

const base = await loadModules();
const result = await suite(base);
console.log('-- rnd_board composition parts --------------------------------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

let escaped = 0;
console.log('\n-- defect mutants (each must be CAUGHT by its named line) -----------');
for (const m of MUTANTS) {
  let out;
  try {
    out = await suite(await loadModules(m.mutate));
  } catch (e) {
    // 🔴 A THROW IS A HOLE, NOT A CATCH -- see the walk harness for the same repair.
    escaped += 1;
    console.log(`  INERT   ${m.id} ${m.what}  -- ${String(e.message).slice(0, 60)}`);
    continue;
  }
  const hit = out.failures.some((f) => f.startsWith(m.catches));
  if (hit) console.log(`  caught  ${m.id} ${m.what}  (${m.catches})`);
  else { escaped += 1; console.log(`  ESCAPED ${m.id} ${m.what}  -- ${m.catches} stayed green`); }
}

const total = result.ran.length + MUTANTS.length;
const failed = result.failures.length + escaped;
console.log(`\n${result.ran.length - result.failures.length} passed, ${result.failures.length} failed; ` +
  `${MUTANTS.length - escaped}/${MUTANTS.length} defects caught, ${escaped} escaped.`);
console.log(`ASSERTIONS ${total} ${failed}`);
if (failed) process.exitCode = 1;
