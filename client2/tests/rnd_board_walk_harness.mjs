/**
 * rnd_board — 부품 F (후보 리스트) · 부품 G (순위 리스트) 계약 채점
 *
 * Same five acceptance conditions as 공사3, plus the one this round adds:
 *
 *   Z  THE FIVE ABSENCES ARE DRAWN AS FIVE DIFFERENT THINGS, and none of them as a fault
 *      contrast:unexamined · complete:false · state:empty · tied · incomparable
 *
 * 🔴 WHY Z IS SCORED WORD BY WORD. 「대조 안 해봄」 and 「대조했는데 차이 없음」 are different
 *    answers, and this repository has shipped the confusion between them before. An assertion
 *    that only checked "something was drawn" would pass while all five rendered identically.
 *
 * 🔴 EVERY MUTANT MUST CHANGE THE SOURCE. `loadModules` throws when a mutation is inert --
 *    the first run of the sibling harness shipped two mutants that changed nothing and read as
 *    passes.
 *
 * CONSOLE OUTPUT IS ASCII ONLY (cp949-safe).
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BOARD_DIR = path.join(HERE, '..', 'src', 'rnd_board');
const dataUrl = (src) => `data:text/javascript;base64,${Buffer.from(src, 'utf8').toString('base64')}`;

// Shaped from the live response of
// `GET /api/ledger/subgraph?id=ledger-entity:v1:<wafer>&collect=quantity` (2026-08-23):
// 25 rows, ranks 1-9, tied 22, incomparable 0, measured 4. Trimmed to five rows that carry
// one of each state, so a collapse between any two shows up here.
const SEED = 'ledger-entity:v1:SEED';
const hop = (kind, label, ref) => ({ id: `${kind}:x`, node_kind: kind, label, atom: null, ref });
const row = (label, rank, extra, hops) => ({
  id: `ledger-quantity:v1:${label}`, type: 'Quantity', label, rank,
  top: false, tied: false, incomparable: false, ...extra,
  evidence: [{ seed: SEED, sign: '+', hops }],
});
const DECLARED = [hop('entity', 'W'), hop('collection', 'void'), hop('quantity', 'q', 'mechanism_models.json')];
const REACHED = [hop('entity', 'W'), hop('claim', 'BONDING', 'eqp_log:SYN-BD-04'), hop('value', '{...}'), hop('quantity', 'q', 'mechanism_models.json')];

const BODY = {
  state: 'ok',
  // The live die-seed response carries 4 nodes and 3 edges even when `collect=quantity`
  // returns `ranked: []`. That is the whole point of Z3b below.
  nodes: [1, 2, 3, 4], edges: [1, 2, 3],
  propagation: {
    collect: 'quantity', state: 'ranked', contrast: 'unexamined', complete: true, message: null,
    top_set: ['ledger-quantity:v1:delam · delam_formation'],
    ranked: [
      row('delam · delam_formation', 1, { top: true }, DECLARED),
      row('void · void_formation', 2, { tied: true }, DECLARED),
      row('die_stress · delam_formation', 2, { tied: true }, DECLARED),
      row('bond_temp · void_formation', 4, { tied: true }, REACHED),
      row('local_gap · void_formation', 5, { incomparable: true }, DECLARED),
    ],
  },
};
const bodyWith = (patch) => {
  const clone = JSON.parse(JSON.stringify(BODY));
  Object.assign(clone.propagation, patch);
  return clone;
};

async function loadModules(mutate = {}) {
  const sources = {};
  const read = (file) => {
    const text = readFileSync(path.join(BOARD_DIR, file), 'utf8');
    const fn = mutate[file];
    const out = fn ? fn(text) : text;
    if (fn && out === text) throw new Error(`mutation anchor is GONE: ${file}`);
    sources[file] = out;
    return sources[file];
  };
  const storeUrl = dataUrl(read('marking_store.js'));
  const apiUrl = dataUrl(read('api.js'));
  const panelUrl = dataUrl(read('panel.js').replaceAll("'./marking_store.js'", `'${storeUrl}'`));
  const rewire = (file) => dataUrl(read(file)
    .replaceAll("'./panel.js'", `'${panelUrl}'`)
    .replaceAll("'./marking_store.js'", `'${storeUrl}'`)
    .replaceAll("'./api.js'", `'${apiUrl}'`));
  const cand = await import(rewire('candidate_list_panel.js'));
  const rank = await import(rewire('rank_list_panel.js'));
  const store = await import(storeUrl);
  return { cand, rank, store, sources };
}

function makeNode(doc, tag) {
  const node = {
    tagName: String(tag).toUpperCase(), className: '', style: {}, children: [],
    attrs: Object.create(null), listeners: Object.create(null), _text: '', parentNode: null,
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
const serve = (body) => async () => ({ ok: true, status: 200, json: async () => body });

async function suite(mods) {
  const { cand, rank, store, sources } = mods;
  const ran = []; const failures = [];
  const eq = (name, got, want) => {
    ran.push(name);
    if (JSON.stringify(got) !== JSON.stringify(want)) failures.push(`${name}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
  };
  const truthy = (name, got) => eq(name, Boolean(got), true);
  const mk = (Cls, host, deps, body) => new Cls(host, {
    doc: deps.doc, markings: deps.markings, reads: deps.reads, writes: deps.writes,
    apiBase: '', seedNodeId: SEED, fetchImpl: serve(body || BODY),
  });

  const doc = makeDoc();
  const markings = new store.MarkingStore();

  // ── A. two instances, one screen, different names ─────────────────────────────
  const hostA = doc.createElement('div');
  const hostB = doc.createElement('div');
  const a = mk(cand.CandidateListPanel, hostA, { doc, markings, reads: 'marking:1', writes: 'marking:1' });
  const b = mk(cand.CandidateListPanel, hostB, { doc, markings, reads: 'marking:2', writes: 'marking:2' });
  a.mount(); b.mount(); await flush(); await flush();
  eq('A1 both instances drew', [byClass(hostA, 'rb-cand-card').length > 0, byClass(hostB, 'rb-cand-card').length > 0], [true, true]);
  // The discriminating click: the instance whose name is NOT the one a hardcode would pick.
  byClass(hostB, 'rb-cand-card')[0].click();
  await flush();
  eq('A2 a part writes the name IT declared', [markings.count('marking:2'), markings.count('marking:1')], [1, 0]);

  // ── Z. the five absences, each its own words ──────────────────────────────────
  const hostC = doc.createElement('div');
  const c = mk(cand.CandidateListPanel, hostC, { doc, markings, reads: 'marking:1', writes: 'marking:1' });
  c.mount(); await flush(); await flush();
  const candText = hostC.textContent;
  truthy('Z1 contrast:unexamined says nobody measured, not that it was clean', candText.includes('또래를 안 쟀'));
  eq('Z1b and it is not drawn with the refusal class', byClass(hostC, 'rb-cand-line--refused').length, 0);

  const hostD = doc.createElement('div');
  const d = mk(cand.CandidateListPanel, hostD, { doc, markings, reads: 'marking:1', writes: null }, bodyWith({ complete: false }));
  d.mount(); await flush(); await flush();
  truthy('Z2 complete:false says UNEXAMINED, not absent', hostD.textContent.includes('미검사'));

  const hostE = doc.createElement('div');
  const e = mk(cand.CandidateListPanel, hostE, { doc, markings, reads: 'marking:1', writes: null }, bodyWith({ state: 'empty', ranked: [] }));
  e.mount(); await flush(); await flush();
  // 🔴 TWO FACTS. Lead PM correction 2026-08-23: `ranked: []` under one `collect` is NOT
  // 「연결 없음」 -- the same die seed answers 2 under `collect=entity`, and 4 nodes / 3 edges
  // were there all along. A part that prints only the absence has denied a transfer.
  truthy('Z3 state:empty still states what the walk DID reach',
    hostE.textContent.includes('노드 4') && hostE.textContent.includes('엣지 3'));
  truthy('Z3c and says the absence is of CANDIDATES, not of connections',
    hostE.textContent.includes('원인 후보는 없습니다'));
  eq('Z3b and it is not a refusal', byClass(hostE, 'rb-cand-line--refused').length, 0);

  const hostR = doc.createElement('div');
  const r = mk(rank.RankListPanel, hostR, { doc, markings, reads: 'marking:1', writes: 'marking:1' });
  r.mount(); await flush(); await flush();
  const stateCells = byClass(hostR, 'rb-rank-state').map((n) => n.textContent);
  truthy('Z4 tied is a word in the state column', stateCells.some((s) => s.includes('동률')));
  truthy('Z5 incomparable is a DIFFERENT word', stateCells.some((s) => s.includes('종류 다름')));
  // 🔴 The collapse test: if a part drew tied and incomparable the same way, this fails.
  truthy('Z6 tied and incomparable are not the same string',
    stateCells.some((s) => s.includes('동률') && !s.includes('종류 다름')));

  // ── R. rank is not a verdict ──────────────────────────────────────────────────
  truthy('R1 the panel says so on itself', hostR.textContent.includes('순위는 판정이 아닙니다'));
  const ranks = byClass(hostR, 'rb-rank-n').map((n) => n.textContent);
  // The header cells carry no `rb-rank-n`, so this is the data rows only. 2 appears TWICE:
  // that is the tie surviving, and X4 (renumbering) dies right here.
  eq('R2 tied rows keep the SAME number the server gave', ranks, ['1', '2', '2', '4', '5']);

  // ── M. measured vs name-only, drawn twice ─────────────────────────────────────
  const measuredCells = byClass(hostR, 'rb-rank-measured').map((n) => n.textContent);
  eq('M1 the rank table prints `-` for a name-only candidate', measuredCells.filter((s) => s === '-').length, 4);
  eq('M2 and 있음 for the one that reaches a claim', measuredCells.filter((s) => s === '있음').length, 1);
  truthy('M3 the candidate list folds the name-only ones into one card',
    byClass(hostC, 'rb-cand-card--folded').length === 1);
  truthy('M4 and says how many', byClass(hostC, 'rb-cand-card--folded')[0].textContent.includes('4'));

  // ── L. two lines, never merged ────────────────────────────────────────────────
  eq('L1 quantity and model are separate elements',
    [byClass(hostR, 'rb-rank-quantity')[0].textContent, byClass(hostR, 'rb-rank-model')[0].textContent],
    ['delam', 'delam_formation']);

  // ── E. evidence is folded until asked ─────────────────────────────────────────
  eq('E1 no evidence is open at first', byClass(hostR, 'rb-rank-evidence').length, 0);
  byClass(hostR, 'rb-rank-row')[1].click();
  await flush();
  eq('E2 clicking a row opens exactly that one', byClass(hostR, 'rb-rank-evidence').length, 1);

  // ── D. box and module state ───────────────────────────────────────────────────
  r.resize(700, 480);
  eq('D1 the part takes the box it is handed', [r.box.width, r.box.height], [700, 480]);
  const scan = (src) => (src.match(/^(let|var)\s+\w+|^const\s+\w+\s*=\s*(\[|\{(?!\s*\})|new\s)/gm) || []);
  eq('D2 no module-level state in either part',
    [scan(sources['candidate_list_panel.js']).length, scan(sources['rank_list_panel.js']).length], [0, 0]);
  truthy('D3 POSITIVE CONTROL: the same scan finds it when planted', scan('let __x = 0;\n').length > 0);
  const px = (src) => (src.match(/\b\d{2,4}px\b/g) || []);
  eq('D4 neither part bakes a size',
    [px(sources['candidate_list_panel.js']).length, px(sources['rank_list_panel.js']).length], [0, 0]);

  return { ran, failures };
}

const MUTANTS = [
  { id: 'X1', what: 'contrast:unexamined is drawn as a refusal', catches: 'Z1b',
    mutate: { 'candidate_list_panel.js': (s) => s.replace(
      "head.appendChild(this._stat('대조군 없음 — 또래를 안 쟀습니다', 'absent'));",
      "root.appendChild(this._line('대조군 없음 — 또래를 안 쟀습니다', 'refused'));") } },
  { id: 'X2', what: 'state:empty is reported as "no cause"', catches: 'Z3',
    mutate: { 'candidate_list_panel.js': (s) => s.replace(
      '원인 후보는 없습니다', '원인 없음') } },
  { id: 'X3', what: 'incomparable is collapsed into tied', catches: 'Z5',
    mutate: { 'rank_list_panel.js': (s) => s.replace(
      "if (c.incomparable) words.push('종류 다름');", '') } },
  { id: 'X4', what: 'ties are renumbered so the order looks total', catches: 'R2',
    mutate: { 'rank_list_panel.js': (s) => s.replace(
      "rank.textContent = c.rank === null ? '-' : String(c.rank);",
      'rank.textContent = String(this._n = (this._n || 0) + 1);') } },
  { id: 'X5', what: 'a name-only candidate is shown as measured', catches: 'M1',
    mutate: { 'rank_list_panel.js': (s) => s.replace(
      "measured.textContent = c.measured ? '있음' : '-';", "measured.textContent = '있음';") } },
  { id: 'X6', what: 'quantity and model are merged into one string', catches: 'L1',
    mutate: { 'api.js': (s) => s.replace(
      "      quantity: (parts[0] || '').trim() || String(row.label || ''),",
      `      quantity: String(row.label || ''),`) } },
  { id: 'X0', what: 'the empty state denies the transfer by printing only the absence', catches: 'Z3',
    mutate: { 'candidate_list_panel.js': (s) => s.replace(
      '${reached} — 원인 후보는 없습니다', '연결 없음') } },
  { id: 'X7', what: 'all evidence is expanded by default', catches: 'E1',
    mutate: { 'rank_list_panel.js': (s) => s.replace(
      'if (c.id && this.opened.has(c.id)) wrap.appendChild(this._evidence(c));',
      'wrap.appendChild(this._evidence(c));') } },
];

const base = await loadModules();
const result = await suite(base);
console.log('-- rnd_board walk parts (F candidate list, G rank list) -------------');
console.log(`  ${result.ran.length - result.failures.length} passed, ${result.failures.length} failed`);
result.failures.forEach((f) => console.log(`  FAIL  ${f}`));

let escaped = 0;
console.log('\n-- defect mutants (each must be CAUGHT by its named line) -----------');
for (const m of MUTANTS) {
  let out;
  // 🔴 A THROW IS A HOLE, NOT A CATCH. `loadModules` throws when a mutation changes nothing,
  // and counting that as 'caught' would turn a rotted anchor into a green line -- the same
  // silent-pass this file was hardened against, wearing a different costume.
  try { out = await suite(await loadModules(m.mutate)); }
  catch (e) { escaped += 1; console.log(`  INERT   ${m.id} ${m.what}  -- ${String(e.message)}`); continue; }
  if (out.failures.some((f) => f.startsWith(m.catches))) console.log(`  caught  ${m.id} ${m.what}  (${m.catches})`);
  else { escaped += 1; console.log(`  ESCAPED ${m.id} ${m.what}  -- ${m.catches} stayed green`); }
}

const total = result.ran.length + MUTANTS.length;
const failed = result.failures.length + escaped;
console.log(`\n${result.ran.length - result.failures.length} passed, ${result.failures.length} failed; ` +
  `${MUTANTS.length - escaped}/${MUTANTS.length} defects caught, ${escaped} escaped.`);
console.log(`ASSERTIONS ${total} ${failed}`);
if (failed) process.exitCode = 1;
