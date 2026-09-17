// CHAIN RULE — 체인 규칙 하나를 «제품 안에서» 등록합니다.
//
// 🔴 이 파일도 «선언»입니다 — 모양은 `raw_registry_panel.js`. 표 등록과 «같은 모양»이라고
//    지시받았고, 그래서 두 번째를 손으로 그리지 않았습니다.
//
// 읽는 것: `GET /admin/chain/rules/raw`. 쓰는 것: `POST` 같은 주소, «규칙 하나» 단위.
//
// ═══ 표 등록과 «다른» 것 하나 ═══════════════════════════════════════════════════════
//
// 🔴 저장이 «장전»까지입니다. 표는 저장해도 아무것도 «안 돌지만», 규칙은 다음 리로드에
//    «돕니다» — 그래서 서버가 «새» 규칙을 `enabled: false` 로 적어 저장합니다.
//    그 사실을 화면이 «말하지 않으면» 운영자는 「저장했는데 왜 안 도나」로 헤맵니다.
//
//    ✅ 그래서 «값»을 보여 줍니다 — `enabled` 는 서버의 낱말이고, 참/거짓은 서버의 값입니다
//    ⛔ 문장을 짓지 않습니다 (소유자 상설: 「ui에 설명 문구 주저리주저리 금지」)
//    ⛔ 「켜기」 전용 컨트롤을 만들지 «않습니다» — 원문 편집기에서 `enabled` 를 고치면
//       됩니다 (소유자 판정: 「두 번째 컨트롤을 발명하지 않는다」)
//    🔴 그리고 «세 상태»입니다: true · false · «키가 없음»(이름을 안 고른 응답).
//       없는 것을 `false` 로 그리면 「안 물어봤다」가 「꺼져 있다」가 됩니다.

import { registryView, RawRegistryPanel } from './raw_registry_panel.js';

/**
 * 저장 답이 있으면 그것이 «더 새 사실»입니다 — 방금 쓴 값이니까요.
 * 둘 다 없으면 `null` 이고, 템플릿은 그때 아무것도 안 그립니다.
 */
function enabledState(payload, opts) {
  const from = (opts && opts.saved && typeof opts.saved.enabled === 'boolean')
    ? opts.saved
    : payload;
  if (!from || typeof from.enabled !== 'boolean') return null;
  return { value: from.enabled, text: `enabled ${from.enabled}` };
}

/**
 * 목록의 두 묶음. 화면에 보이는 말이고, 이 등록부의 것입니다.
 *
 * 🔴 왜 묶나: 소유자의 물음이 「내 파일이 왜 안 보이지」였습니다(2026-09-13). 「등록된 이름」과
 *    「파일의 함수」가 한 줄에 섞이면 그 물음이 화면에서 «안 풀립니다» — 둘은 서로 다른 사실이고
 *    저장이 받아 주는 방식도 다릅니다(하나는 등록부 조회, 하나는 두 칸).
 */
export const MAPPER_GROUPS = Object.freeze({ registered: '등록 이름' });

//: 선언된 파라미터가 들어가는 칸. 🔴 이름을 «여기» 적는 이유는 이 파일이 이 문법의 낱말을
//: 아는 유일한 자리이기 때문입니다 — 템플릿은 경로를 «받아» 쓸 뿐입니다.
const PARAMS_KEY = 'params';

//: 파일 함수를 «한 칸짜리 값»으로 적는 철자. 🔴 저자가 이 파일 «하나»입니다 — 만드는 쪽
//: (`mapperChoices`)과 펴는 쪽(`splitMapper`)과 되읽는 쪽(`joinMapper`)이 나란히 있어야
//: 갈라질 수 없고, 갈라진 날 「고른 것이 아무 칸도 안 채운다」가 됩니다.
const TOKEN = ':';
const tokenOf = (module, name) => `${module}${TOKEN}${name}`;

/**
 * `GET /admin/mappers/list` → 고를 수 있는 것들. `null` 은 「못 읽음」이고 `[]` 는 「없음」입니다.
 *
 * 🔴 두 묶음이 «한 push» 를 지납니다. 서버가 `candidates` 를 싣기 전에는 오늘 있는 두 칸에서
 *    같은 모양을 만들고(다리), 두 읽기가 다른 모양을 낼 수 없습니다 (criterion ④).
 * ⚠️ 그 다리는 `candidates` 가 오면 «그 블록만» 지웁니다 — 판정 379 가 그 모양을 확정했습니다.
 */
export function mapperChoices(body) {
  if (!body || typeof body !== 'object') return null;
  const out = [];
  const seen = new Set();
  const push = (value, label, group, fill) => {
    if (!value || seen.has(value)) return;
    seen.add(value);
    out.push(fill ? { value, label, group, fill } : { value, label, group });
  };
  const candidates = Array.isArray(body.candidates) ? body.candidates : null;
  if (candidates) {
    for (const item of candidates) {
      if (!item || typeof item !== 'object') continue;
      const name = String(item.name || '');
      const module = String(item.module || '');
      // C-106 ⑤. 서버가 «선언된 파라미터»를 실어 주면 고르는 순간 그 행들이 따라옵니다.
      //    🔴 `null` 이면 «안 물어본» 것이라 아무것도 안 채웁니다 — 빈 목록(선언은 읽었고
      //       파라미터가 없다)과 다른 사실이고, 그 둘을 접으면 화면이 답을 지어냅니다.
      const fill = Array.isArray(item.params) ? paramFill(item.params) : undefined;
      if (item.kind === 'registered') push(name, name, MAPPER_GROUPS.registered, fill);
      // C-106 ⑦. 파일 함수는 «파일별»로 묶이고 항목은 «함수 이름»만 답니다 — 목록이 길어지면
      //    항목마다 같은 모듈 접두가 반복되고, 그 반복이 「내 파일이 어디 있나」를 다시 가립니다.
      else if (module && name) push(tokenOf(module, name), name, module, fill);
    }
    return out;
  }
  for (const name of Array.isArray(body.registered) ? body.registered : []) {
    push(String(name), String(name), MAPPER_GROUPS.registered);
  }
  for (const file of Array.isArray(body.data) ? body.data : []) {
    const module = String((file && file.module_name) || '');
    if (!module) continue;
    for (const fn of Array.isArray(file && file.functions) ? file.functions : []) {
      const name = String((fn && fn.name) || '');
      // ⚠️ 이 다리에는 `params` 가 «없습니다»(AST 가 센 def 목록이라 선언이 아닙니다).
      //    그래서 채울 것도 없습니다 — S-223 의 `candidates` 가 오면 그때 따라옵니다.
      if (name) push(tokenOf(module, name), name, module);
    }
  }
  return out;
}

/** 선언된 파라미터 이름들 → «칸 경로»와 빈 값. 경로의 저자가 이 파일 하나입니다. */
function paramFill(names) {
  const fill = {};
  for (const name of names) {
    const key = String(name || '');
    if (key) fill[`${PARAMS_KEY}.${key}`] = '';
  }
  return Object.keys(fill).length ? fill : undefined;
}

/**
 * 목록 «밖»의 한 줄들 — 「여기 있지만 고를 수 없는 것」. 사유는 «서버의 낱말»이고 이 파일은
 * 문장을 짓지 않습니다(모듈 이름 · 사유).
 *
 * 🔴 이것이 필요한 이유는 하나입니다: 없는 것과 «거절된 것»이 드롭다운에서 «같은 부재»로
 *    보입니다. 소유자가 「내 파일이 왜 안 보이지」를 두 번 묻지 않게 하는 자리입니다.
 * ⚠️ 오늘 서버는 이 칸들을 «안 냅니다»(S-223 이 실습니다). 키가 없으면 줄이 «없습니다» —
 *    빈 줄을 그리면 「못 읽음」이 「없음」이 됩니다.
 */
export function mapperNotes(body) {
  if (!body || typeof body !== 'object') return [];
  const lines = [];
  const add = (kind, entry) => {
    if (!entry || typeof entry !== 'object') return;
    const module = String(entry.module || '');
    const why = String(entry.why || '');
    if (!module && !why) return;
    lines.push({ kind, text: module && why ? `${module} · ${why}` : module || why });
  };
  for (const entry of Array.isArray(body.other) ? body.other : []) add('other', entry);
  for (const entry of Array.isArray(body.refused) ? body.refused : []) add('refused', entry);
  return lines;
}

/**
 * 고른 것이 «어느 칸들»에 적히나. `null` 이면 그 칸 하나에 그대로 적힙니다(등록된 이름).
 *
 * 🔴 파일 함수는 `mapper` 를 «비웁니다». 그 칸의 뜻은 「등록부의 이름」이고(실측:
 *    `chain_bindings.mapper_resolvable` 이 등록부만 봅니다), 토큰을 거기 적으면 문서가 다른
 *    독자에게 거짓을 말합니다 — 그리고 저장은 두 칸이 차 있으면 «그대로 받습니다».
 */
export function splitMapper(value) {
  const text = String(value == null ? '' : value);
  const at = text.lastIndexOf(TOKEN);
  if (at <= 0 || at === text.length - 1) return null;
  return {
    mapper: null,
    mapper_module: text.slice(0, at),
    mapper_function: text.slice(at + 1),
  };
}

/**
 * 문서가 «어느 철자로든» 든 맵퍼를 고르개의 값으로 되읽습니다. 없으면 ''.
 *
 * 🔴 이것이 없으면 두 칸으로 적힌 규칙에서 고르개가 «빈 채»로 서고, 화면은 맵퍼가 있는 규칙을
 *    「안 골랐다」로 그립니다 — 그건 「한 응답에 상태가 둘」의 실물입니다.
 */
export function joinMapper(held) {
  const doc = held && typeof held === 'object' ? held : {};
  if (typeof doc.mapper === 'string' && doc.mapper) return doc.mapper;
  const module = typeof doc.mapper_module === 'string' ? doc.mapper_module : '';
  const name = typeof doc.mapper_function === 'string' ? doc.mapper_function : '';
  return module && name ? tokenOf(module, name) : '';
}

/** 이 등록부의 낱말. */
export const CHAIN_RULE_REGISTRY = Object.freeze({
  listKey: 'rules',
  nameKey: 'name',
  cls: 'chain-rule',
  extra: enabledState,
  // C-86 ①. 소유자: 「규칙 등록 영역에 규칙을 추가할 수가 없어」. 서버는 «이미» 새 이름을
  // 받습니다 — 새 규칙은 `enabled: false` 로 «장전»까지만 저장됩니다(위 절 참조).
  addLabel: '규칙 추가',
  // C-86 ②. 칸 이름·종류는 «서버가 실어 준» 스켈레톤에서 나옵니다(S-204). 이 파일도 칸 이름을
  // 적지 않습니다 — `chain_bindings.routing_keys()` 가 유일한 저자입니다.
  // 🔴 C-111 (S-241). 문법이 «둘»이 됐고(평면 · 통합), 서버가 몸소 둘을 다 실어
  //    보내며 «이 규칙이 어느 쪽인지»를 칸으로 말합니다(`grammar`). 화면이 그것을 다시
  //    유도하면(예: `derive` 가 있나 보기) 그 유도가 곳 둘째 저자입니다 — 서버와 화면이
  //    같은 파일을 두고 다른 문법이라 말하게 되는 날이 그러면 오류 없이 옵니다.
  formRoot: (payload) => {
    const skeleton = (payload && payload.skeleton) || {};
    const grammar = payload && typeof payload.grammar === 'string' ? payload.grammar : '';
    // 🔴 [판정 542] 「모른다」는 «평면»이 «아닙니다». 서버가 한 규칙의 문법을 못 읽으면 그 칸이
    //    «없고», 종전에는 그 없음이 falsy 라 조용히 «평면 폼»이 떴습니다 — 화면이 모르는 것을
    //    «안다고» 말한 자리입니다. 그리고 두 문법은 칸이 «27 대 7»이라, 틀리게 고르면 빈 칸이
    //    진짜 값 위에 그려집니다(판정 514).
    // ⛔ 여기서 `derive` 를 보고 «다시 유도»하지 않습니다 — 그 순간 저자가 둘이 됩니다(C-111).
    //    모르면 폼을 «안 그립니다». 원문 편집기가 그대로 서고(이 칸의 계약), 옆의 「문법 모름」
    //    표지가 «왜» 폼이 없는지 말합니다.
    if (grammar !== 'unified' && grammar !== 'flat') return null;
    return (grammar === 'unified' ? skeleton.unified_root : skeleton.root) || null;
  },
  // 🔴 계획 §9.3 ③. 화면은 «어느 문법인지»를 말합니다 — 이행 중에는 둘 다 열려
  //    있고, 그러면 같은 화면이 규칙마다 다른 칸을 내미는데 이유가 화면에 없습니다.
  //    ⚠️ 서버가 안 말했으면 «안 그립니다» — 「모름」을 「평면」으로 적으면 그것이 거짓입니다.
  grammarOf: (payload) => (payload && typeof payload.grammar === 'string'
    ? payload.grammar : ''),

  // 🔴 [판정 548] 이 문서가 «갈 수 있는» 문법과 그 컨트롤의 말. 한 라우트가 양방향이라
  //    (`to: unified|flat`) 되돌리기가 «반대 방향»일 뿐이고, 그래서 버튼이 하나입니다.
  // ⚠️ 문법을 «못 읽는» 규칙에는 «없습니다» — 추측해서 변환하지 않습니다(판정 543·548 ④).
  //    「이미 그 문법이면 아무것도 안 한다」도 여기서 갈립니다: 갈 곳이 «자기»면 컨트롤이 없습니다.
  convert: (payload) => {
    const grammar = payload && payload.grammar;
    if (grammar === 'flat') return { to: 'unified', label: '통합으로' };
    if (grammar === 'unified') return { to: 'flat', label: '평면으로' };
    return null;
  },

  // 🔴 [판정 536 ④] 이 화면이 «세어서» 말해야 하는 둘 — ㈎ 「제품이 뜻을 모르는 칸」과
  //    ㈏ 「아직 평면으로 적힌 규칙 수」. 안 말하면 이관 뒤의 «침묵»을 운영자가 「끝났다」로
  //    읽습니다. 값이지 문장이 아닙니다 — 배지 하나에 수 하나.
  marks: (payload) => {
    const out = [];
    // ㈏ — 목록 응답이 실어 주는 «이름 -> 문법» 지도(판정 540). 한 번의 요청이 «전부»에
    //    답하므로 화면이 규칙마다 묻지 않습니다.
    // 🔴 「0」도 «그립니다». 이관이 끝났는지는 운영자가 «지금» 묻는 물음이고 답이 있습니다 —
    //    배지가 사라지는 것으로 답하면 「다 됐다」와 「안 세어 봤다」가 같은 그림이 됩니다.
    const map = payload && payload.rule_grammars;
    if (map && typeof map === 'object') {
      let flat = 0;
      for (const key of Object.keys(map)) if (map[key] === 'flat') flat += 1;
      out.push({ text: `평면 ${flat}`, kind: 'flat' });
      // ⚠️ 지도에 «없는» 이름은 「모르는 것」입니다 — 서버가 「모른다」를 「평면」으로 채우지
      //    않고 «빼기» 때문입니다(판정 540·542). 그것을 평면에 더하면 그 규율이 화면에서
      //    무너지고, 운영자는 이관해야 할 수를 «틀리게» 봅니다.
      const names = Array.isArray(payload.rules) ? payload.rules.map(String) : [];
      const unknown = names.filter((n) => map[n] !== 'flat' && map[n] !== 'unified').length;
      if (unknown) out.push({ text: `문법 모름 ${unknown}`, kind: 'unknown' });
    }
    // 🔴 [판정 543] 열린 규칙의 문법을 «못 읽으면» 그 사실을 «이름 대어» 말합니다.
    //    폼이 안 그려지는 것(위 `formRoot`)만으로는 «말없이 사라진 폼»이고, 그러면 운영자는
    //    화면이 고장 났다고 읽습니다. 상설 ⑥: 「거절은 «이름»으로 — 고칠 자리를 알 수 있게」.
    // ⛔ 여기서 문법을 «추측»하지 않습니다. 못 읽은 것은 못 읽은 것입니다(판정 509).
    if (payload && payload.name
        && payload.grammar !== 'flat' && payload.grammar !== 'unified') {
      out.push({ text: `문법 못 읽음 · ${payload.name}`, kind: 'unknown' });
    }
    // ㈎ — 통합 문서가 «한 자리»에 모아 든 모르는 칸입니다(`rule_shape.to_declaration` 의
    //    `extra`: 「제품이 뜻을 모르는 칸은 한 자리에 모아 둔다」).
    // ⚠️ 평면 문서에는 그 자리가 «없습니다» — 모르는 칸이 최상위에 흩어져 있어, 화면이 세려면
    //    스켈레톤과 견줘야 하고 그 순간 이 수의 저자가 «둘»이 됩니다(서버의 `extra` 와 화면).
    //    그래서 통합일 때만 셉니다. 저자는 그 칸을 «쓴» 변환기 하나입니다.
    // 🔴 0 이면 안 그립니다 — 옆의 문법 배지가 이미 「unified」라 말하고, 그러면 배지 없음이
    //    「나른 것이 없음」으로 «유일하게» 읽힙니다. ㈏ 와 달리 이건 «진행 중인 수»가 아닙니다.
    if (payload && payload.grammar === 'unified') {
      const doc = payload.declaration;
      const held = doc && typeof doc.extra === 'object' && doc.extra ? doc.extra : null;
      const n = held ? Object.keys(held).length : 0;
      if (n) out.push({ text: `모르는 칸 ${n} · 보존`, kind: 'carried' });
    }
    return out;
  },
  // C-86 ③. 맵퍼 칸의 목록 이름. 값은 화면이 `GET /admin/mappers/list` 에서 받아 넣습니다 —
  // 이 파일은 «이름»만 대고 «목록»은 서버의 등록부입니다.
  choiceList: 'mappers',
  // C-101 ②. 표를 대는 칸들의 목록 이름. 값은 화면이 `GET /tables` 에서 받아 넣습니다 —
  // 그 라우트가 «제품이 아는 표 전부»(`crud.TABLE_CONFIG`)이고, 규칙이 읽고 쓸 수 있는 표가
  // 그 집합입니다. 🔴 실측 2026-09-13: 이 문법의 `hint: 'ref'` 리프가 일곱이고 전부 이
  // 목록을 씁니다 — 칸 이름을 여기 적지 않는 이유가 그것입니다(스켈레톤이 저자입니다).
  refList: 'tables',
  // C-95 ②. 「첫 화면」은 «필수»가 아닙니다 — 다른 물음입니다.
  //
  // 🔴 실측(2026-09-13, `chain_bindings.RULE_ROUTING_REQUIRED`): 이 문법의 required 는
  //    `name`·`trigger_table` «둘»뿐입니다. `target_table` 과 `mapper` 는 «선택»이고, 그 이유가
  //    그 파일 자기 주석에 적혀 있습니다 — 코드에 기본값이 있거나 데코레이터가 댈 수 있습니다.
  //    그래서 이 둘을 「필수」라고 적으면 «거짓»이 되고, required 를 여기 다시 적으면 저자가
  //    둘이 됩니다. 이 목록은 그 둘 중 어느 것도 아닙니다 — 「이것 없이 규칙을 읽을 수 있나」입니다.
  //    ⚠️ 규칙이 «쓰는 표»와 «도는 코드»를 안 보고는 규칙을 못 읽습니다. 그리고 맵퍼가 안 풀리면
  //       저장이 `unresolvable_mapper` 로 거절됩니다 — 첫 화면에서 보이지 않으면 그 거절이
  //       「고급」 뒤에서 옵니다.
  firstScreen: ['target_table', 'mapper'],
  // C-95 ③. 맵퍼를 대는 «두 철자». 로더가 둘 다 읽습니다(`chain_bindings.mapper_cells`) —
  // 하나가 이름 하나, 다른 하나가 module + function 입니다. 화면이 둘을 같이 내놓으면
  // 운영자가 「둘 다 적어야 하나」를 묻게 되고, 실측에서 그 셋이 한 화면에 서 있었습니다.
  // ⚠️ 가려진 철자는 「고급」에 있습니다 — 없애면 오늘 module+function 으로 적힌 규칙을
  //    한 칸짜리로 «바꿀 길»이 사라집니다.
  // C-101 ③. 그리고 그 «두 철자 사이의 번역»도 이 등록부의 것입니다 — 고르개 하나가 둘 다
  // 쓸 수 있게 되었으므로, 운영자가 「둘 중 어디에 적나」를 고를 일이 없습니다.
  oneOf: [{
    one: ['mapper'],
    other: ['mapper_module', 'mapper_function'],
    list: 'mappers',
    split: splitMapper,
    join: joinMapper,
  }],
});

/**
 * @param {object|null} payload  `/admin/chain/rules/raw` 의 응답, 또는 null
 * @param {{unavailable?: string, refusal?: object, saved?: object}} [opts]
 */
export function chainRuleView(payload, opts = {}) {
  return registryView(payload, opts, CHAIN_RULE_REGISTRY);
}

/**
 * @param {HTMLElement} mount
 * @param {{doc?: Document, onOpen?: Function, onSave?: Function}} [deps]
 */
export class ChainRulePanel extends RawRegistryPanel {
  constructor(mount, deps = {}) {
    super(mount, deps, CHAIN_RULE_REGISTRY);
  }
}
