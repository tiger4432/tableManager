// Mock harness — map_editor.js split registry 로직 검증 (DOM/네트워크 없이 vm 샌드박스)
// 대상: buildSplitKey / buildLegendRegistryUpdates / parseLegendRegistryRows /
//       getMissingDescValues / formatLegendMetaText / loadLegend / saveLegendToServer /
//       fetchLegendFromServer / maybeOfferLegendMigration / loadLegendFromStorage
// 실행: node client2/tests/split_registry_harness.mjs (node_modules 불필요 — vm 샌드박스)
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const SRC_PATH = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'map_editor.js');
const src = readFileSync(SRC_PATH, 'utf8');

// ── 소스에서 함수/상수 블록 추출 (brace matching) ──
function extractFunction(name) {
  const re = new RegExp(`(?:async\\s+)?function\\s+${name}\\s*\\(`);
  const m = re.exec(src);
  if (!m) throw new Error(`function ${name} not found`);
  let i = src.indexOf('{', m.index);
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    const ch = src[j];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return src.slice(m.index, j + 1);
    }
  }
  throw new Error(`unbalanced braces for ${name}`);
}
function extractConst(name) {
  const re = new RegExp(`const\\s+${name}\\s*=`);
  const m = re.exec(src);
  if (!m) throw new Error(`const ${name} not found`);
  // 배열/객체 리터럴 또는 단순 리터럴: 세미콜론 종료 지점까지 brace/bracket 균형 추적
  let depth = 0;
  for (let j = m.index; j < src.length; j++) {
    const ch = src[j];
    if (ch === '[' || ch === '{') depth++;
    else if (ch === ']' || ch === '}') depth--;
    else if (ch === ';' && depth === 0) return src.slice(m.index, j + 1);
  }
  throw new Error(`no terminator for ${name}`);
}

const extracted = [
  extractConst('SPLIT_REGISTRY_TABLE'),
  extractConst('SPLIT_KEY_SEP'),
  extractConst('DEFAULT_LEGEND'),
  'let legendMeta = {}; let legendServerSaveTimer = null;',
  'let legend = []; let activeBrush = ""; let selectedTable = "bonding_map";',
  extractFunction('buildSplitKey'),
  extractFunction('buildLegendRegistryUpdates'),
  extractFunction('parseLegendRegistryRows'),
  extractFunction('getMissingDescValues'),
  extractFunction('formatLegendMetaText'),
  extractFunction('loadLegendFromStorage'),
  extractFunction('saveLegendToStorage'),
  extractFunction('fetchLegendFromServer'),
  extractFunction('loadLegend'),
  extractFunction('saveLegendToServer'),
  extractFunction('maybeOfferLegendMigration'),
  // 샌드박스에서 상태를 읽고 쓰기 위한 액세서
  `globalThis.__h = {
     get legend() { return legend; }, set legend(v) { legend = v; },
     get legendMeta() { return legendMeta; }, set legendMeta(v) { legendMeta = v; },
     get activeBrush() { return activeBrush; },
     get selectedTable() { return selectedTable; },
     buildSplitKey, buildLegendRegistryUpdates, parseLegendRegistryRows,
     getMissingDescValues, formatLegendMetaText, loadLegend, saveLegendToServer,
     fetchLegendFromServer, maybeOfferLegendMigration, DEFAULT_LEGEND
   };`
].join('\n\n');

// ── 스텁 환경 ──
function makeLocalStorage(initial = {}) {
  const store = new Map(Object.entries(initial));
  return {
    getItem: k => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: k => store.delete(k),
    _store: store
  };
}

const calls = { fetch: [], toasts: [], confirms: [] };
let fetchImpl = async () => { throw new Error('fetch not stubbed'); };
let confirmImpl = () => true;

const sandbox = {
  console,
  clearTimeout,
  setTimeout,
  API_BASE: 'http://mock:8000',
  CURRENT_USER: 'tester',
  getLocalTimeString: () => '2026-07-25 12:00:00',
  showToast: (msg, type) => calls.toasts.push({ msg, type }),
  confirm: (msg) => { calls.confirms.push(msg); return confirmImpl(msg); },
  fetch: (...args) => { calls.fetch.push(args); return fetchImpl(...args); },
  localStorage: makeLocalStorage(),
  renderLegendMetaOnly: () => {},
  getCurrentMapKey: () => null, // saveLegendToServer의 override 없는 경로용 스텁
  encodeURIComponent,
  JSON, Map, Set, Array, Object, String, Promise, Error,
  globalThis: null
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(extracted, sandbox);
const H = sandbox.__h;

// ── 테스트 러너 ──
let pass = 0, fail = 0;
function check(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS ${name}`); }
  else { fail++; console.log(`  FAIL ${name} ${detail}`); }
}
function okJson(obj) {
  return { ok: true, status: 200, json: async () => obj };
}

// ═══ T1. buildLegendRegistryUpdates — 페이로드 형태/bk 조립 ═══
console.log('\n[T1] buildLegendRegistryUpdates');
{
  const legendArr = [
    { value: '1', desc: '  HTOL split A — 1.05V burn-in  ', color: '#10b981' },
    { value: '', desc: 'ghost', color: '#fff' },          // 빈 value 제외
    { value: 'E1', desc: '', color: '#8b5cf6' }            // 빈 desc 허용(경고는 push 관문)
  ];
  const ups = H.buildLegendRegistryUpdates('bonding_map', 'BASE01', legendArr, 'tester', '2026-07-25 12:00:00');
  check('빈 value 필터링 → 2건', ups.length === 2, JSON.stringify(ups.length));
  const u0 = ups[0];
  check('bk = ref|map|value ("|" 분리)', u0.business_key_val === 'bonding_map|BASE01|1', u0.business_key_val);
  check('split_key 컬럼 = bk 동일값', u0.updates.split_key === u0.business_key_val);
  check('desc trim 적용', u0.updates.split_desc === 'HTOL split A — 1.05V burn-in');
  check('composite 소스 3컬럼 동봉', u0.updates.ref_table === 'bonding_map' && u0.updates.map_key === 'BASE01' && u0.updates.value === '1');
  check('source_name=user / updated_by 전달', u0.source_name === 'user' && u0.updated_by === 'tester');
  check('eventtime 주입', u0.updates.eventtime === '2026-07-25 12:00:00');
  check('mapKey 없으면 빈 배열', H.buildLegendRegistryUpdates('bonding_map', null, legendArr, 'u', 'n').length === 0);
  check('refTable 없으면 빈 배열', H.buildLegendRegistryUpdates('', 'k', legendArr, 'u', 'n').length === 0);
}

// ═══ T2. parseLegendRegistryRows — 셀 계약 읽기/dedupe ═══
console.log('\n[T2] parseLegendRegistryRows');
{
  const mkRow = (value, desc, color, mapKey, by, at) => ({
    data: {
      value: { value, is_overwrite: true, updated_by: by, priority_source: 'user' },
      split_desc: { value: desc, is_overwrite: true, updated_by: by, priority_source: 'user' },
      color: { value: color, is_overwrite: false, updated_by: 'system' },
      map_key: { value: mapKey, is_overwrite: false, updated_by: 'system' },
      updated_at: { value: at, is_overwrite: false, updated_by: 'system' }
    }
  });
  const result = {
    data: [
      mkRow('1', 'old desc', '#111111', 'BASE01', 'alice', '2026-07-20 09:00:00'),
      mkRow('1', 'new desc', '#222222', 'BASE02', 'bob', '2026-07-24 18:30:00'),
      mkRow('0', 'FAIL bin', null, 'BASE01', 'alice', '2026-07-21 10:00:00'),
      mkRow('', 'no value skip', '#333333', 'BASE01', 'x', '2026-07-22 10:00:00')
    ]
  };
  const noDedupe = H.parseLegendRegistryRows(result, false);
  check('빈 value 행 스킵 → 3행', noDedupe.length === 3, String(noDedupe.length));
  const deduped = H.parseLegendRegistryRows(result, true);
  check('dedupe → 2행', deduped.length === 2, String(deduped.length));
  const v1 = deduped.find(r => r.value === '1');
  check('value 중복 시 updated_at 최신 승리', v1.desc === 'new desc' && v1.updated_by === 'bob', JSON.stringify(v1));
  const v0 = deduped.find(r => r.value === '0');
  check('color null → 폴백 #6b7280', v0.color === '#6b7280', v0.color);
  check('updated_by는 split_desc 셀에서', v0.updated_by === 'alice');
  check('빈/이상 응답 안전', H.parseLegendRegistryRows(null, true).length === 0 && H.parseLegendRegistryRows({}, false).length === 0);
}

// ═══ T3. getMissingDescValues — push 경고 관문 ═══
console.log('\n[T3] getMissingDescValues');
{
  const legendArr = [
    { value: '1', desc: 'GOOD split' },
    { value: '0', desc: '   ' },      // 공백만 → 누락
    { value: 2, desc: 'numeric legend value' } // 타입 불일치 방어(String 비교)
  ];
  const missing = H.getMissingDescValues(['1', '0', '2', '9'], legendArr);
  check('공백 desc + legend 부재 값 검출', JSON.stringify(missing) === JSON.stringify(['0', '9']), JSON.stringify(missing));
  check('빈 입력 안전', H.getMissingDescValues(null, null).length === 0);
}

// ═══ T4. formatLegendMetaText ═══
console.log('\n[T4] formatLegendMetaText');
{
  check('미저장 표기', H.formatLegendMetaText(undefined) === '서버 미저장');
  check('메타 표기', H.formatLegendMetaText({ updated_by: 'bob', updated_at: '2026-07-24 18:30:00' }) === 'bob · 2026-07-24 18:30:00');
}

// ═══ T5. loadLegend — 서버 우선 → localStorage → DEFAULT ═══
console.log('\n[T5] loadLegend 우선순위');
{
  // (a) 서버에 행 존재 → server 채택 + 캐시 동기화
  fetchImpl = async (url) => {
    check('GET registry URL/필터', url.includes('/tables/map_split_registry/data') && decodeURIComponent(url).includes('"ref_table"'), url);
    return okJson({ data: [{ data: {
      value: { value: 'S1', updated_by: 'alice' },
      split_desc: { value: 'skew high', updated_by: 'alice' },
      color: { value: '#ff0000' },
      map_key: { value: 'BASE01' },
      updated_at: { value: '2026-07-24 09:00:00' }
    } }] });
  };
  const r1 = await H.loadLegend('bonding_map', 'BASE01');
  check('서버 로드 → "server"', r1 === 'server');
  check('legend 서버 값 반영', H.legend.length === 1 && H.legend[0].value === 'S1' && H.legend[0].desc === 'skew high');
  check('activeBrush 첫 항목', H.activeBrush === 'S1');
  check('legendMeta 채움', H.legendMeta['S1'].updated_by === 'alice');
  check('localStorage 캐시 동기화', sandbox.localStorage.getItem('map_legend_bonding_map') !== null);

  // (b) 서버 접근 OK, 0행 → localStorage 폴백
  sandbox.localStorage.setItem('map_legend_bonding_map', JSON.stringify([{ value: 'L9', desc: 'local cached', color: '#00ff00' }]));
  fetchImpl = async () => okJson({ data: [] });
  const r2 = await H.loadLegend('bonding_map', 'BASE01');
  check('빈 서버 → "local" 폴백', r2 === 'local' && H.legend[0].value === 'L9', r2);

  // (c) 서버 다운(404/network) → localStorage 폴백
  fetchImpl = async () => ({ ok: false, status: 404, json: async () => ({}) });
  const r3 = await H.loadLegend('bonding_map', null);
  check('서버 실패 → "offline" 폴백', r3 === 'offline' && H.legend[0].value === 'L9', r3);

  // (d) 서버 실패 + 캐시 없음 → DEFAULT_LEGEND
  sandbox.localStorage._store.delete('map_legend_bonding_map');
  fetchImpl = async () => { throw new Error('ECONNREFUSED'); };
  const r4 = await H.loadLegend('bonding_map', 'BASE01');
  check('최후 폴백 → DEFAULT_LEGEND', r4 === 'offline' && H.legend.length === H.DEFAULT_LEGEND.length && H.legend[0].value === '1');
}

// ═══ T6. saveLegendToServer — PUT 업서트/메타 반영/실패 격리 ═══
console.log('\n[T6] saveLegendToServer');
{
  H.legend = [{ value: '1', desc: 'HTOL A', color: '#10b981' }, { value: '0', desc: 'ref', color: '#ef4444' }];
  H.legendMeta = {};
  let captured = null;
  fetchImpl = async (url, opts) => { captured = { url, opts }; return okJson({ updated_count: 2 }); };
  const ok1 = await H.saveLegendToServer('BASE01');
  check('성공 시 true', ok1 === true);
  check('PUT 제네릭 updates 경로', captured.url === 'http://mock:8000/tables/map_split_registry/data/updates' && captured.opts.method === 'PUT', captured.url);
  const body = JSON.parse(captured.opts.body);
  check('updates 2건 + bk 조립', body.updates.length === 2 && body.updates[0].business_key_val === 'bonding_map|BASE01|1');
  check('저장 후 legendMeta 즉시 갱신', H.legendMeta['1'].updated_by === 'tester' && H.legendMeta['1'].updated_at === '2026-07-25 12:00:00');

  check('mapKey 미확정 → 조용히 스킵(false)', (await H.saveLegendToServer(null)) === false);
  fetchImpl = async () => { throw new Error('ECONNREFUSED'); };
  check('네트워크 실패 → false (예외 전파 없음)', (await H.saveLegendToServer('BASE01')) === false);
}

// ═══ T7. maybeOfferLegendMigration — 1회 제안 ═══
console.log('\n[T7] maybeOfferLegendMigration');
{
  sandbox.localStorage.setItem('map_legend_bonding_map', JSON.stringify([{ value: 'M1', desc: 'legacy', color: '#123456' }]));
  H.legend = [{ value: 'M1', desc: 'legacy', color: '#123456' }];
  calls.confirms.length = 0;
  let putCount = 0;
  fetchImpl = async (url, opts) => { if (opts && opts.method === 'PUT') putCount++; return okJson({}); };
  confirmImpl = () => true;
  await H.maybeOfferLegendMigration('bonding_map', 'BASE07');
  check('제안 confirm 노출 + 업로드 실행', calls.confirms.length === 1 && putCount === 1, `confirms=${calls.confirms.length} put=${putCount}`);
  check('마이그레이션 플래그 기록', sandbox.localStorage.getItem('map_split_migrated_bonding_map|BASE07') === '1');
  await H.maybeOfferLegendMigration('bonding_map', 'BASE07');
  check('2회차는 재제안 없음', calls.confirms.length === 1);
  await H.maybeOfferLegendMigration('bonding_map', null);
  check('mapKey 없으면 무동작', calls.confirms.length === 1);
}

console.log(`\n════ RESULT: ${pass} passed, ${fail} failed ════`);
process.exit(fail === 0 ? 0 : 1);
