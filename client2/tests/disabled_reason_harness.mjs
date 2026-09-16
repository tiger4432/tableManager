// disabled_reason — 꺼진 컨트롤은 «자기 자리»에서 왜인지 말한다. (C-120 + C-119 발견 ②)
// Run: node client2/tests/disabled_reason_harness.mjs
//
// 🔴 이 라운드가 왜 있나. 총괄이 메인 그리드를 열어 쟀습니다: 소급 배너의 버튼 둘이 꺼져
//    있는데 `title` 이 «빈 문자열»이었습니다. 바로 옆 버튼 셋은 「뷰 — 읽기 전용」을 답니다.
//    제가 다섯 화면을 훑으니 같은 물음(「왜 못 누르나」)에 답하는 자리가 «넷»이었습니다 —
//    `title` · 옆 문구 · «다른 패널» · «없음». 기준 ④ 그대로입니다.
//
// 🔴 그래서 이 파일의 «주 단언»은 자리마다의 문장이 아니라 «성질»입니다:
//       「이 화면에 꺼진 컨트롤이 있으면, 그 컨트롤이 자기 자리에서 왜인지 말한다」
//    문장을 하나씩 세면 다섯째 컨트롤이 생기는 날 그 자리만 빠집니다 — 그리고 «없음»이
//    제일 고르기 쉽습니다(아무것도 안 적으면 되니까). 성질로 재면 새 컨트롤이 이 안으로
//    «저절로» 들어옵니다.
//
// 🔴 대조군이 절반입니다. 「꺼졌으면 말한다」만 재면 «영원히 켜 두는» 코드가 만점을 받고,
//    「사유가 붙는다」만 재면 켜진 버튼에도 사유가 남는 코드가 만점을 받습니다. 둘 다 잽니다.
//
// 주어 넷, «전부 import» 합니다 — 잘라쓰기 0:
//    disabled_reason.js         좌석 그 자체
//    redo_banner.js             C-120 의 그 배너
//    rnd_board/walk_box_panel.js  「걷기」 — 사유가 «다른 패널»에 있던 자리
//    walk/main.js               「날리기」 — 사유가 «옆 드롭다운»에 간접으로 있던 자리
// ⚠️ `write_guard.js` 는 여기서 안 잽니다 — 그 정본은 «옮긴» 것이고 그 화면의 단언은
//    `grid_view_readonly_harness` 에 있습니다. 두 하니스가 같은 것을 두 방식으로 재면
//    그 둘이 갈라집니다.

import path from 'node:path';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { loadWithProbe } from './lib/probe.mjs';
import { makeDoc } from './lib/board_dom.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.join(HERE, '..', 'src');
const SEAT = path.join(SRC, 'disabled_reason.js');
const REDO = path.join(SRC, 'redo_banner.js');
const WALKBOX = path.join(SRC, 'rnd_board', 'walk_box_panel.js');
const WALKPAGE = path.join(SRC, 'walk', 'main.js');

let pass = 0, fail = 0, quiet = false;
const failedNames = [];
function ok(cond, name, saw) {
  if (cond) { pass++; if (!quiet) console.log(`  OK   ${name}`); }
  else {
    fail++; failedNames.push(name);
    if (!quiet) console.log(`  BAD  ${name}${saw === undefined ? '' : `  -- ${JSON.stringify(saw)}`}`);
  }
  return !!cond;
}

const doc = makeDoc('light');
globalThis.document = doc;
globalThis.window = {
  location: { port: '', origin: 'http://box', href: 'http://box/', hash: '', search: '' },
  addEventListener() {}, removeEventListener() {},
};
globalThis.requestAnimationFrame = (fn) => fn();

const walk = (node, out = []) => {
  out.push(node);
  for (const kid of node.children || []) walk(kid, out);
  return out;
};
const titleOf = (n) => (n.attrs && n.attrs.title) || '';
/** 🔴 이 술어가 이 파일입니다: «꺼졌는데 말이 없는» 컨트롤. 비어 있어야 합니다. */
const mute = (root) => walk(root).filter((n) => n.disabled === true && !titleOf(n));
/** 그 반대편: «켜졌는데 사유가 남아 있는» 컨트롤. 고친 척이 아니라 고친 것임을 재는 자리. */
const stale = (root) => walk(root).filter((n) => n.disabled === false && titleOf(n)
                                                 && n.dataset && n.dataset.titleWas === '');
const settle = () => new Promise((r) => setTimeout(r, 0));

// ── ① 좌석 그 자체 ────────────────────────────────────────────────────────────────────
function seatSuite(setDisabledReason) {
  const btn = () => {
    const b = doc.createElement('button');
    return b;
  };
  const a = btn();
  setDisabledReason(a, '행을 고르십시오');
  ok(a.disabled === true && titleOf(a) === '행을 고르십시오',
     'S1 사유를 주면 «끄고» 그 자리에 적는다', [a.disabled, titleOf(a)]);
  setDisabledReason(a, '');
  ok(a.disabled === false && titleOf(a) === '',
     'S2 사유가 없으면 «켜고» 자기가 적은 말을 «거둔다»', [a.disabled, titleOf(a)]);

  // 🔴 마크업이 «이미» 자기 말을 달고 있는 버튼이 있습니다(`title="Add Row"`). 덮어쓰기만
  //    하면 다시 켜졌을 때 그 버튼이 말을 «잃습니다» — C-107 이 그래서 기억을 답니다.
  const b = btn();
  b.setAttribute('title', 'Add Row');
  setDisabledReason(b, '뷰 — 읽기 전용');
  ok(titleOf(b) === '뷰 — 읽기 전용', 'S3 원래 말이 있어도 사유가 «먼저» 선다', titleOf(b));
  setDisabledReason(b, '');
  ok(b.disabled === false && titleOf(b) === 'Add Row',
     'S4 켜지면 «원래 말»이 돌아온다', [b.disabled, titleOf(b)]);
  setDisabledReason(b, '뷰 — 읽기 전용');
  setDisabledReason(b, '');
  ok(titleOf(b) === 'Add Row', 'S5 두 번 껐다 켜도 원래 말이 안 닳는다', titleOf(b));

  // ⚠️ 계측기는 자기가 진단하는 것을 죽일 수 없습니다(상설). 없는 것·모자란 스텁에 대고
  //    던지면 그 화면의 단언이 «한 줄도» 안 돕니다.
  let threw = false;
  try { setDisabledReason(null, '왜'); } catch (e) { threw = true; }
  ok(!threw, 'S6 없는 컨트롤에 대고 던지지 않는다');
  threw = false;
  try { setDisabledReason({ dataset: {} }, '왜'); } catch (e) { threw = true; }
  ok(!threw, 'S7 `getAttribute` 가 없는 스텁에도 던지지 않는다');
}

// ── ② 소급 배너 — C-120 그 자체 ──────────────────────────────────────────────────────
const SOURCES = [{ relation: 'dt_log', source: 'dt_log_src', scope_columns: ['lot_id'] }];
const ROW = { row_id: 'r1', data: { lot_id: { value: 'L1' } } };
const readValue = (row, col) => {
  const cell = row && row.data ? row.data[col] : undefined;
  if (cell && typeof cell === 'object' && 'value' in cell) return cell.value;
  return row ? row[col] : undefined;
};
function redoSuite(RedoBanner) {
  const seat = (rows) => {
    const host = doc.createElement('div');
    const part = new RedoBanner(host, {
      doc, sources: SOURCES, getSelection: () => rows, readValue, businessKey: 'lot_id',
      handOff: () => {},
    });
    part.setRelation('dt_log');
    part.render();
    return host;
  };
  const off = seat([]);
  const btns = walk(off).filter((n) => String(n.className || '').includes('redo-banner__btn'));
  ok(btns.length === 2 && btns.every((b) => b.disabled === true),
     'R1 행이 없으면 버튼 둘이 꺼진다', btns.map((b) => b.disabled));
  ok(mute(off).length === 0, 'R2 그리고 «말 없이» 꺼진 컨트롤이 하나도 없다', mute(off).length);
  ok(btns.every((b) => titleOf(b) === '행을 고르십시오'),
     'R3 사유는 「행을 고르십시오」 — 다음 행동 한 줄', btns.map(titleOf));
  const on = seat([ROW]);
  const live = walk(on).filter((n) => String(n.className || '').includes('redo-banner__btn'));
  ok(live.every((b) => b.disabled === false && titleOf(b) === ''),
     'R4 행을 고르면 켜지고 «사유도 사라진다»', live.map((b) => [b.disabled, titleOf(b)]));
  ok(stale(on).length === 0, 'R5 켜진 채 사유가 남은 컨트롤이 없다', stale(on).length);
}

// ── ③ R&D 보드의 「걷기」 — 사유가 «다른 패널»에 있던 자리 ────────────────────────────
const DECL = {
  ok: true,
  entities: [{ type: 'die@1', keys: ['die_id'] }, { type: 'wafer@1', keys: ['wafer_id'] }],
  predicates: [{ name: 'bonded_from', subjects: ['die@1'], objects: ['die@1'] }],
};
/** 같은 선언, 전선이 «응답 본문»으로 받는 모양. `ok` 는 HTTP 쪽 말이라 본문에 없습니다. */
const DECL_BODY = { entities: DECL.entities, predicates: DECL.predicates, collect: [] };
async function walkBoxSuite(WalkBoxPanel) {
  const seat = async (type) => {
    const host = doc.createElement('div');
    const part = new WalkBoxPanel(host, {
      doc, reads: 'marking:1', writes: 'marking:2',
      loadDeclaration: () => Promise.resolve(DECL),
      walk: () => Promise.resolve({ ok: true, nodes: [] }),
    });
    part.mount();
    await settle();
    if (type) { part.setType(type); await settle(); }
    return host;
  };
  const off = await seat(null);
  const go = walk(off).find((n) => String(n.className || '').includes('rb-walkbox-go'));
  ok(Boolean(go) && go.disabled === true, 'W1 타입이 없으면 「걷기」가 꺼진다', go && go.disabled);
  ok(Boolean(go) && titleOf(go) === '시작 타입을 고르십시오',
     'W2 그리고 «자기 자리»에서 무엇이 필요한지 말한다', go && titleOf(go));
  ok(mute(off).length === 0, 'W3 말 없이 꺼진 컨트롤이 하나도 없다',
     mute(off).map((n) => n.className));
  const on = await seat('die@1');
  const live = walk(on).find((n) => String(n.className || '').includes('rb-walkbox-go'));
  ok(Boolean(live) && live.disabled === false && titleOf(live) === '',
     'W4 타입을 고르면 켜지고 사유도 사라진다', live && [live.disabled, titleOf(live)]);
}

// ── ④ 걷기 페이지의 「날리기」 — 사유가 «옆 드롭다운»에 간접으로 있던 자리 ──────────────
async function walkPageSuite(boot) {
  const host = doc.createElement('div');
  // 🔴 선언이 «와야» 폼이 그려집니다. 못 읽은 화면은 실패 줄과 「다시」만 그리고, 그 화면에는
  //    「날리기」가 «없습니다» — 그걸로 재면 이 단언은 공허합니다(처음에 그렇게 썼고, 단언
  //    둘이 조용히 빨개져서 잡았습니다). 무대는 「선언은 읽혔는데 타입을 아직 안 골랐다」입니다.
  boot(doc, host, {
    apiBase: '',
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => DECL_BODY,
                              text: async () => JSON.stringify(DECL_BODY) }),
  });
  await settle();
  await settle();
  const go = walk(host).find((n) => (n.textContent || '') === '날리기');
  ok(Boolean(go) && go.disabled === true, 'K1 타입이 없으면 「날리기」가 꺼진다', go && go.disabled);
  ok(Boolean(go) && titleOf(go) === '노드 타입을 먼저 고르십시오',
     'K2 그리고 «둘 중 어느 것»을 기다리는지 말한다', go && titleOf(go));
  ok(mute(host).length === 0, 'K3 말 없이 꺼진 컨트롤이 하나도 없다',
     mute(host).map((n) => n.className));
}


// ── ⑤ 전수 — 「꺼진 컨트롤 «전부»」에 대해 «사유가 있다 ∨ 틀리게 읽히지 않는다» ────────────
//
// 🔴 총괄 지시(09-16 23:2x): 「모집단을 «화면 전수»로 다시 세십시오 … 「자명」으로 넘기지 말고
//    «틀리게 읽히나»로 가르십시오」. 앞의 넷은 제가 «고친» 자리이고, 이 절은 «안 고친 자리까지»
//    포함한 전수입니다. 고친 것만 재는 게이트는 다섯째 자리에 대해 아무 말도 안 합니다.
//
// 🔴 판별식은 «자명한가»가 아니라 «틀리게 읽히나»입니다. 그 둘이 갈랐습니다 — 총괄이
//    `‹ Prev`(첫 쪽)를 「안 고친다」로 판정한 근거가 「자명하다」가 아니라 「틀리게 읽히지
//    않는다」였고, 저는 온톨로지 탐색기의 `←` `→` 를 «자명»으로 넘겼다가 지적받았습니다.
//
// ⚠️ 키는 «줄 번호»가 아닙니다 — 공유 트리의 줄 번호는 유통기한이 있습니다. 키는 «파일 +
//    대입식»이라, 코드가 옮겨도 그대로이고 «식이 바뀌면» 다시 분류하게 됩니다. 그것이 옳은
//    민감도입니다: 조건이 바뀌었으면 「틀리게 읽히나」의 답도 바뀔 수 있습니다.
//
// 분류 — 각각이 「∨」의 어느 쪽인지 말합니다:
//    SEAT         `setDisabledReason` 을 지납니다. 사유가 «있습니다»            <- 왼쪽
//    BUSY         방금 누른 것이 도는 중. 라벨이 대개 같이 바뀌고 «되돌아옵니다»  <- 오른쪽
//    END          쪽·이력의 «끝». 총괄 판정: 틀리게 읽히지 않습니다              <- 오른쪽
//    STATED       같은 렌더가 사유를 «옆에» 그립니다                            <- 오른쪽
//    PASSTHROUGH  판정이 «다른 곳»에서 왔고 그쪽이 사유를 답니다                 <- 오른쪽
//    ADJACENT     못 채운 입력이 «바로 옆»에 비어 있습니다                       <- 오른쪽
//    PATCH        결정이 아니라 «복사»입니다 (dom_patch)                        <- 해당 없음
//    🔴 CONFLICT  말이 없는데, 코드가 «일부러 그랬다»고 적어 두었습니다 -> 판정 청합니다
//    🔴 UNRULED   읽어서 못 가렸습니다 -> 정직하게 «모른다»로 둡니다
// ⛔ `SILENT`(말 없이 꺼짐, 변명 없음)은 이 표에 «있으면 안 됩니다». 있으면 고칠 자리입니다.
const CENSUS_TABLE = new Map([
  ['admin.js :: btn.disabled = true', ['BUSY', '설정 저장 중']],
  ['admin.js :: btn.disabled = false', ['BUSY', '저장이 끝나 되돌아옴']],
  ['admin.js :: countBtn.disabled = actions.count.disabled', ['BUSY', '세는 중 · buildActionsView 가 판정']],
  ['admin.js :: runBtn.disabled = actions.run.disabled', ['SEAT', '🔵 이미 title 로 blocked_reason 을 답니다 — 이 저장소의 «다섯째» 증인']],
  ['admin.js :: inputEl.disabled = true', ['BUSY', '토글 응답 전 연타 방지']],
  ['admin.js :: inputEl.disabled = false', ['BUSY', '응답 뒤 되돌아옴']],
  ['admin.js :: prevPageBtn.disabled = currentPage <= 1', ['END', '첫 쪽 — 총괄 판정']],
  ['admin.js :: nextPageBtn.disabled = currentPage >= maxPage', ['END', '끝 쪽 — 총괄 판정']],
  ['dom_patch.js :: live.disabled = next.disabled', ['PATCH', '결정이 아니라 복사']],
  ['grid.js :: elements.prevPageBtn.disabled = view.prevDisabled', ['END', '첫 쪽 — 총괄이 `‹ Prev` 로 «직접» 판정']],
  ['grid.js :: elements.nextPageBtn.disabled = view.nextDisabled', ['END', '끝 쪽']],
  ['map2/main.js :: child.disabled = opt.disabled === true', ['PASSTHROUGH', '옵션 «라벨»이 사유입니다(그 파일 주석)']],
  // 🔵 09-17 «재서» 가렸습니다(총괄 요청). 이 한 자리가 드롭다운 «여섯»(규칙·표·X·Y·값·참조)을
  //    덮고, 비는 경우마다 그 줄의 `notice` 가 사유를 «먼저» 세웁니다 — 그 파일 주석이
  //    「화면이 규칙이나 표조차 못 찾았으면, 그게 답에 대한 어떤 말보다 «앞선다»」로 적어 두었고,
  //    호출도 그렇습니다: 표 0 -> 「맵 테이블 없음」(map_editor2.js:310) · 규칙을 못 고름 ->
  //    그 사유 그대로(:211/:245) · 셋업 실패 -> 그 문장(:255/:316). 컬럼 쪽은
  //    `WORDS.columnsUnstated` 가 같은 줄에 섭니다. 즉 사유가 «옆에» 있습니다.
  ['map2/main.js :: node.disabled = options.length === 0', ['STATED', '빈 경우마다 questionNote 의 `notice` 가 그 줄에 먼저 선다 (map_editor2.js:211·245·255·310·316)']],
  ['map2/main.js :: row.disabled = single', ['STATED', '그 행이 «가진 것과 부재»를 자기가 적습니다']],
  ['map2/main.js :: cell.disabled = card.inert', ['STATED', '칸마다 data-me2-state · 「미상」을 그립니다']],
  ['map2/main.js :: el.indexToggle.disabled = !ready', ['STATED', '옆의 indexNote 가 INDEX_NOTE 를 그립니다']],
  ['map2/main.js :: btn.disabled = !vm.confirm.enabled || confirmInFlight', ['STATED', 'inertHint 가 «왜»를 말합니다 + 도는 중']],
  // 🔵 09-17 판정 455 — `el.exportBtn` 은 이 표에서 «사라졌습니다». 끄는 것이 아니라
  //    «안 내놓습니다»: `el.exportBtn.hidden = !artifactImplemented()`. 깃발이 «셸이 그것을
  //    내놓아도 되나»를 말하므로, 안 된다면 그려서도 안 됩니다. 빚의 기록은
  //    `task/FEATURE_INVENTORY_CLIENT.md` §A-4 에 살고, 운영자의 «화면»에는 안 삽니다 — 그게 그 판정의 한 줄입니다.
  ['map_editor.js :: el.btnLoadMap.disabled = true', ['BUSY', '표 목록/맵 로드 중']],
  ['map_editor.js :: el.tableSelect.disabled = true', ['BUSY', '표 목록 로드 중']],
  ['map_editor.js :: el.tableSelect.disabled = false', ['BUSY', '로드가 끝나 되돌아옴']],
  ['map_editor.js :: el.btnLoadMap.disabled = false', ['BUSY', '되돌아옴 (네 자리)']],
  ['map_editor.js :: el.btnPushMap.disabled = true', ['BUSY', '올리는 중']],
  ['map_editor.js :: el.btnPushMap.disabled = false', ['BUSY', '되돌아옴']],
  ['map_editor.js :: btn.disabled = true', ['BUSY', '저장 중 · 오버레이 재조회 중 — 라벨도 같이 바뀝니다']],
  ['map_editor.js :: btn.disabled = false', ['BUSY', '되돌아옴']],
  ['map_editor.js :: el.btnAddOverlay.disabled = true', ['BUSY', '오버레이 추가 중']],
  ['map_editor.js :: el.btnAddOverlay.disabled = false', ['BUSY', '되돌아옴']],
  ["ontology_explorer_view.js :: make.disabled = !(state.newDeclaration?.id || '').trim()", ['ADJACENT', '바로 위 입력칸이 «비어 있습니다»']],
  ['ontology_explorer_view.js :: row.disabled = !otherKey', ['STATED', '그 행이 reference_kind · status 를 적습니다']],
  ['ontology_explorer_view.js :: run.disabled = Boolean(state.testRunning)', ['BUSY', '시험 실행 중']],
  ['ontology_explorer_view.js :: back.disabled = !state.navigation.back.length', ['END', '이력의 끝 — `‹ Prev` 와 «같은 부류»입니다. 제가 「자명」으로 넘겼던 자리이고, 옳은 근거는 「틀리게 읽히지 않는다」입니다']],
  ['ontology_explorer_view.js :: forward.disabled = !state.navigation.forward.length', ['END', '이력의 끝']],
  ['timeline.js :: btn.disabled = false', ['BUSY', '되돌아옴 (세 자리)']],
  ['timeline.js :: btn.disabled = true', ['BUSY', '가져오는 중']],
  ['transfer_plan.js :: ta.disabled = na.inapplicable', ['STATED', '같은 객체의 `fix` 가 «보이는 지시»입니다(그 파일 주석)']],
  ['transfer_plan.js :: btn.disabled = true', ['BUSY', '적용 중']],
  ['transfer_plan.js :: btn.disabled = false', ['BUSY', '되돌아옴']],
]);
// 🔴 이 둘은 «허용»이 아니라 «세어 둔 빚»입니다. 늘면 빨개집니다 — 조용히 늘 길이 없습니다.
// 🔴 열쇠는 «남겨 둡니다». 0 이라도 키가 있어야 다음에 하나 생길 때 이 줄이 빨개집니다 —
//    분류를 못 한 자리를 «조용히» 둘 길이 없습니다.
const OPEN_DEBT = { CONFLICT: 0, UNRULED: 0 };

const SRC_DIR = path.join(HERE, '..', 'src');
/** 이 저장소에서 컨트롤을 끄는 «모든» 자리. 좌석을 지나는 것은 자기 파일이 답하므로 뺍니다. */
function censusSites() {
  const files = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const p = path.join(dir, name);
      if (statSync(p).isDirectory()) walk(p);
      else if (name.endsWith('.js')) files.push(p);
    }
  };
  walk(SRC_DIR);
  const seen = new Map();
  for (const file of files) {
    const rel = path.relative(SRC_DIR, file).split(path.sep).join('/');
    if (rel === 'disabled_reason.js') continue;
    for (const line of readFileSync(file, 'utf8').split('\n')) {
      const m = /([A-Za-z0-9_.[\]?$]+)\.disabled\s*=\s*([^;]+);/.exec(line);
      if (!m) continue;
      const key = `${rel} :: ${m[1]}.disabled = ${m[2].trim()}`;
      seen.set(key, (seen.get(key) || 0) + 1);
    }
  }
  return seen;
}

/**
 * @param {Map=} sitesIn  전수 결과를 «갈아 끼우는» 자리
 * @param {Map=} censusIn 표를 갈아 끼우는 자리
 * @param {object=} openIn 빚 상한
 *
 * 🔴 인자 셋이 있는 이유는 «이 절도 채점돼야» 하기 때문입니다. 전수는 디스크를 읽으므로
 *    위의 소스 변이가 여기 안 닿고, 그러면 다섯 단언이 「아무 변이도 이름 대지 않는 검사」가
 *    됩니다 — 초록인 채로 아무것도 안 지키는 그 모양입니다. 아래 CENSUS_DEFECTS 가
 *    이 인자로 «틀린 입력»을 먹여, 각 단언이 실제로 문다는 것을 보입니다.
 */
function censusSuite(sitesIn, censusIn, openIn) {
  const sites = sitesIn || censusSites();
  const CENSUS = censusIn || CENSUS_TABLE;
  const OPEN = openIn || OPEN_DEBT;
  const unclassified = [...sites.keys()].filter((k) => !CENSUS.has(k));
  ok(unclassified.length === 0,
     `P1 끄는 자리가 «전부» 분류돼 있다 (미분류 ${unclassified.length})`, unclassified);
  const dead = [...CENSUS.keys()].filter((k) => !sites.has(k));
  ok(dead.length === 0, `P2 표에 «죽은 줄»이 없다 (${dead.length})`, dead);
  const classes = [...CENSUS.values()].map(([c]) => c);
  ok(!classes.includes('SILENT'),
     'P3 「말 없이 꺼짐」이 표에 하나도 없다 — 있으면 그건 분류가 아니라 «할 일»이다');
  for (const [name, limit] of Object.entries(OPEN)) {
    const n = classes.filter((c) => c === name).length;
    ok(n === limit, `P4 «세어 둔 빚» ${name} 이 ${limit} 그대로다 (본 수 ${n})`, n);
  }
  // ⚠️ 모집단이 실재한다는 것도 같이. 0 자리면 위 셋이 «전부 공허하게» 참입니다.
  const total = [...sites.values()].reduce((a, b) => a + b, 0);
  ok(total >= 40 && sites.size >= 30,
     `P5 그 성질의 모집단이 실재한다 (자리 ${total} · 서로 다른 식 ${sites.size})`,
     [total, sites.size]);
}

// ── 채점 ──────────────────────────────────────────────────────────────────────────────
const load = (file, tag, mutate) => loadWithProbe(file, { tag, mutate });

async function suite(seat, redo, box, page) {
  const before = { pass, fail };
  seatSuite(seat.module.setDisabledReason);
  redoSuite(redo.module.RedoBanner);
  await walkBoxSuite(box.module.WalkBoxPanel);
  await walkPageSuite(page.module.boot);
  // 🔴 전수는 «디스크»를 읽습니다 — 변이는 메모리 사본에 걸리므로 이 절은 변이에 안 움직입니다.
  //    그래서 변이 채점에서는 «건너뜁니다»: 모든 변이가 이 다섯을 똑같이 통과시키면
  //    그 다섯이 변이 점수를 희석합니다(대조군이 언제나 CAUGHT 로 보이는 그 함정).
  if (!quiet) censusSuite();
  return { pass: pass - before.pass, fail: fail - before.fail };
}

const SEAT_DEFECTS = [
  ['M1 좌석이 끄기만 하고 «말을 안 한다» -> S1',
   (s) => s.replace("    if (el.setAttribute) el.setAttribute('title', reason);", '')],
  ['M2 좌석이 켜면서 사유를 «안 거둔다» -> S2',
   (s) => s.replace("  } else if (el.removeAttribute) {\n    el.removeAttribute('title');\n  }",
                    '  }')],
  ['M3 좌석이 «원래 말»을 기억하지 않는다 -> S4/S5',
   (s) => s.replace("    el.dataset.titleWas = (el.getAttribute && el.getAttribute('title')) || '';",
                    "    el.dataset.titleWas = '';")],
  ['M4 좌석이 사유가 있어도 «안 끈다» -> S1',
   (s) => s.replace('  el.disabled = Boolean(reason);', '  el.disabled = false;')],
  ['M5 좌석이 없는 컨트롤에 던진다 -> S6',
   (s) => s.replace('  if (!el) return;', '')],
];
const PART_DEFECTS = [
  ['M6 배너가 «말 없이» 끈다 (오늘의 결함 그대로) -> R2/R3', REDO,
   (s) => s.replace("    setDisabledReason(btn, enabled ? '' : NEEDS_A_ROW);",
                    '    btn.disabled = !enabled;')],
  ['M7 배너가 켜진 버튼에도 사유를 남긴다 -> R4', REDO,
   (s) => s.replace("    setDisabledReason(btn, enabled ? '' : NEEDS_A_ROW);",
                    '    setDisabledReason(btn, NEEDS_A_ROW);')],
  ['M8 「걷기」가 말 없이 꺼진다 -> W1/W2', WALKBOX,
   (s) => s.replace("    setDisabledReason(btn, this.nodeType ? '' : PICK_START_TYPE);",
                    "    if (!this.nodeType) btn.setAttribute('disabled', 'disabled');")],
  ['M9 「날리기」가 말 없이 꺼진다 -> K2/K3', WALKPAGE,
   (s) => s.replace("    setDisabledReason(go, state.run === 'running'\n      ? RUNNING\n"
                    + "      : (state.type ? '' : PICK_TYPE_FIRST));",
                    "    go.disabled = !state.type || state.run === 'running';")],
];
const CONTROLS = [
  ['좌석의 주석 한 낱말', SEAT, (s) => s.replace('넷»이었습니다', '다섯»이었습니다')],
  ['배너의 주석 한 낱말', REDO, (s) => s.replace('빈 문자열', '빈 글자')],
];

console.log('-- disabled_reason (C-120 + C-119 finding 2) -----------------------');
let tag = 0;
const nx = () => `d${tag += 1}`;
const seatBase = await load(SEAT, nx());
const redoBase = await load(REDO, nx());
const boxBase = await load(WALKBOX, nx());
const pageBase = await load(WALKPAGE, nx());
const base = await suite(seatBase, redoBase, boxBase, pageBase);

const caught = [], escaped = [];
let controlsCaught = 0;
console.log('');
console.log('-- defect mutants (each must be caught by the check it names) ------');
for (const [name, mutate] of SEAT_DEFECTS) {
  quiet = true;
  const delta = await suite(await load(SEAT, nx(), mutate), redoBase, boxBase, pageBase);
  quiet = process.argv[2] === '--quiet';
  (delta.fail > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
for (const [name, file, mutate] of PART_DEFECTS) {
  quiet = true;
  const hit = await load(file, nx(), mutate);
  const delta = await suite(seatBase,
                            file === REDO ? hit : redoBase,
                            file === WALKBOX ? hit : boxBase,
                            file === WALKPAGE ? hit : pageBase);
  quiet = process.argv[2] === '--quiet';
  (delta.fail > 0 ? caught : escaped).push(name);
  console.log(`  ${delta.fail > 0 ? 'caught ' : 'ESCAPED'} ${name}`);
}
console.log('');
console.log('-- control mutants (each must ESCAPE) ------------------------------');
for (const [name, file, mutate] of CONTROLS) {
  quiet = true;
  const hit = await load(file, nx(), mutate);
  const delta = await suite(file === SEAT ? hit : seatBase,
                            file === REDO ? hit : redoBase,
                            boxBase, pageBase);
  quiet = process.argv[2] === '--quiet';
  if (delta.fail > 0) controlsCaught += 1;
  console.log(`  ${delta.fail > 0 ? 'CAUGHT ' : 'escaped'} ${name}`);
}

// 🔴 전수 절의 변이. 디스크를 안 건드리고 «입력»을 갈아 끼웁니다 — 그래야 이 다섯 단언도
//    「자기가 이름 댄 검사에 잡힌다」를 보일 수 있습니다.
const withRow = (k, v) => new Map([...CENSUS_TABLE, [k, v]]);
const CENSUS_DEFECTS = [
  ['C1 새 자리가 분류 없이 들어온다 -> P1',
   () => [new Map([...censusSites(), ['new_screen.js :: b.disabled = true', 1]]), null, null]],
  ['C2 표에 «죽은 줄»이 남는다 -> P2',
   () => [null, withRow('gone.js :: b.disabled = true', ['BUSY', '없는 파일']), null]],
  ['C3 말 없이 꺼진 자리가 표에 적힌다 -> P3',
   () => [new Map([...censusSites(), ['x.js :: b.disabled = true', 1]]),
          withRow('x.js :: b.disabled = true', ['SILENT', '아무 말 없음']), null]],
  ['C4 «세어 둔 빚»이 조용히 는다 -> P4',
   () => [new Map([...censusSites(), ['y.js :: b.disabled = true', 1]]),
          withRow('y.js :: b.disabled = true', ['CONFLICT', '둘째 빚']), null]],
  ['C5 모집단이 비면 나머지가 «공허하게» 참이 된다 -> P5',
   () => [new Map(), new Map(), null]],
];
console.log('');
console.log('-- census mutants (the roll call must bite too) --------------------');
for (const [name, make] of CENSUS_DEFECTS) {
  quiet = true;
  const before = { pass, fail };
  const [s, c, o] = make();
  censusSuite(s, c, o);
  quiet = process.argv[2] === '--quiet';
  const hit = fail > before.fail;
  // 변이가 낸 빨강은 «하니스가 돈 것»이지 이 파일의 판정이 아닙니다. 되돌립니다.
  pass = before.pass; fail = before.fail; failedNames.length = Math.min(failedNames.length, 9999);
  (hit ? caught : escaped).push(name);
  console.log(`  ${hit ? 'caught ' : 'ESCAPED'} ${name}`);
}

const DEFECTS = SEAT_DEFECTS.length + PART_DEFECTS.length + CENSUS_DEFECTS.length;
const badScore = escaped.length > 0 || controlsCaught > 0;
console.log('');
console.log(`${base.pass} passed, ${base.fail} failed; ${caught.length}/${DEFECTS} defects caught, `
  + `${escaped.length} escaped; ${CONTROLS.length - controlsCaught}/${CONTROLS.length} controls escaped.`);
console.log(`ASSERTIONS ${base.pass + base.fail} ${base.fail}`);
if (base.fail) console.log('FAILED: ' + failedNames.slice(0, base.fail).join(' | '));
if (base.fail || badScore) process.exitCode = 1;
