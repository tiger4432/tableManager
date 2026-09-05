// PLAN DRY RUN — 「내가 쓴 이 선언이 받아들여지나, 아니면 «왜» 거절되나」.
//
// 🔴 이 파일이 있는 이유: 화면이 부르는 `/api/transfer-plan/stages` 는 역할마다
//    `connected`/`missing` «한 낱말»을 냅니다. 그 낱말로는 config 를 «못 고칩니다».
//    `/admin/transfer-plan/dry-run` 이 넷을 같이 내고 있었고 소비자가 «0» 이었습니다:
//      ① 이름 붙은 거절 «사유»       ② 해석된 «실제 컬럼명»
//      ③ 그 컬럼이 «선언»에서 왔나 «유도»에서 왔나
//      ④ 틀린 선언이 유도를 지고 있으면 «지우면 무엇이 유도되는지»
//    ④ 가 「무엇을 바꾸나」이고, 한 낱말이 못 하던 일이 그것입니다.
//
// ⛔ 한 낱말짜리 답을 «지우지» 않습니다 — 다른 화면에 있고, 요약은 요약대로 씁니다.
// ⛔ 사유를 여기서 «짓지» 않습니다. `bonding_plan.explain_binding_refusal` 이 정본이라
//    문장 생성기를 두 번 쓰지 않는다고 서버가 적어 뒀습니다.
//
// ⚠️ 그리고 서버의 «버킷»을 접지 않습니다. 서버는 거절을 여러 갈래로 «따로» 세고,
//    운영자가 하는 일이 갈래마다 다릅니다 — 고치기 / 적기 / 앞을 먼저 풀기.
//    그래서 그 수들을 «훑어서» 그대로 냅니다.
//
// 🔴 그리고 그 갈래의 «이름»을 여기 적지 않습니다. 계약 INV-F9-7: 사유의 이름과 문장은
//    서버의 것이고, 클라는 응답을 «훑을» 뿐입니다. 낱말을 여기 적으면 그 순간 두 번째
//    저자가 생기고, 서버가 갈래를 하나 더하는 날 화면이 «조용히» 짧아집니다.
//    (이 파일의 첫 판이 정확히 그렇게 적었고 계약이 잡았습니다.)

/** 안 물어봤거나 못 받았습니다. 「거절」이 아닙니다. */
export const DRY_RUN_UNREAD = '진단 · 모름';

const list = (v) => (Array.isArray(v) ? v : []);
const str = (v) => (typeof v === 'string' && v ? v : '');

/** 역할 하나의 상태 — «구조»로만 가릅니다 (`accepted` · `declared` 둘 다 불리언).
 *
 * 🔴 사유 «낱말»로 안 가릅니다. 그건 서버의 어휘이고, 클라가 그 목록을 들고 있으면
 *    서버가 갈래를 더하는 날 새 갈래가 조용히 마지막 else 로 떨어집니다.
 *    갈래의 이름이 필요하면 그 행의 `reason` 을 «그대로» 보여 줍니다.
 */
function roleState(role) {
  if (role.accepted === true) return 'accepted';
  if (role.accepted !== false) return 'unknown';   // 안 실은 행은 「거절」이 아닙니다
  return role.declared === false ? 'undeclared' : 'refused';
}

/**
 * @param {object|null|undefined} payload `/admin/transfer-plan/dry-run` 의 응답
 * @param {{read?: boolean, failed?: string}} [opts] `failed` 는 못 받은 «사유»
 */
export function planDryRunView(payload, opts = {}) {
  const failed = str(opts.failed);
  if (opts.read === false || failed || !payload) {
    return { read: false, roles: [], counts: null, text: DRY_RUN_UNREAD, reason: failed };
  }
  const flat = [];
  for (const stage of list(payload.stages)) {
    for (const role of list(stage && stage.roles)) {
      flat.push({ stage: str(stage && stage.name), role });
    }
  }
  for (const role of list(payload.plan_store)) flat.push({ stage: 'plan_store', role });

  const roles = flat.map(({ stage, role }) => {
    const state = roleState(role || {});
    // 🔴 컬럼은 「이름」만이 아니라 «어디서 왔나»를 같이 냅니다. 선언에서 온 이름과 유도된
    //    이름이 같아 보이면, 지워도 되는 것과 지우면 안 되는 것이 구별되지 않습니다.
    const columns = Object.entries((role && role.columns) || {})
      .filter(([, c]) => c && typeof c === 'object')
      .map(([name, c]) => ({
        role: name,
        column: str(c.column),
        origin: str(c.origin),
        // ⚠️ `exists_on_table` 은 «세 상태»입니다 — 있음 · 없음 · «못 물어봄»(모델이 없음).
        //    못 물어본 것을 「없음」으로 그리면 멀쩡한 컬럼이 결함으로 보입니다.
        exists: typeof c.exists_on_table === 'boolean' ? c.exists_on_table : null,
        derivedFrom: str(c.derived_from),
      }));
    return {
      stage,
      role: str(role && role.role),
      where: str(role && role.where),
      state,
      table: str(role && role.table),
      // 서버의 낱말과 서버의 문장. 둘 다 그대로 나릅니다.
      reason: str(role && role.reason),
      detail: str(role && role.detail),
      columns,
      // 🔴 「무엇을 바꾸나」 — 틀린 선언을 지우면 무엇이 유도되는지.
      removable: list(role && role.removable_declarations)
        .filter((r) => r && typeof r === 'object')
        .map((r) => ({ role: str(r.role), wouldDerive: str(r.would_derive) })),
    };
  });

  // 🔴 버킷을 «훑습니다». 이름을 여기 적지 않으므로, 서버가 갈래를 더하면 그 갈래가
  //    «저절로» 화면에 섭니다. 0 인 갈래는 안 그립니다 — 아무도 안 물어본 0 입니다.
  const raw = (payload && typeof payload.counts === 'object' && payload.counts) || {};
  const counts = Object.entries(raw)
    .filter(([, v]) => Number.isInteger(v))
    .map(([name, value]) => ({ name, value }));
  const total = counts.find((x) => x.name === 'total');
  const parts = counts
    .filter((x) => x !== total && x.value > 0)
    .map((x) => `${x.name} ${x.value}`);
  return {
    read: true,
    roles,
    counts,
    configPath: str(payload.config_path),
    text: parts.length ? parts.join(' · ')
      : `역할 ${total ? total.value : roles.length}`,
    reason: '',
  };
}
