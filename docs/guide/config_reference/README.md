# 📋 config 참조 스냅샷 (시뮬레이션 환경)

> **Status:** 🟠 스냅샷(사본) | **Snapshot-taken:** 2026-08-01 (부분 재동기화: `chain_rules.json` 2026-08-11) | **Owner:** Lead / Backend
>
> ⚠️ **2026-08-11 재동기화 — `chain_rules.json` 하나만.** `68db020`이 `.sample`에 `__alignment_thresholds_derivation` 주석 키를 더했는데(트리거 ①) 이 사본이 안 따라갔다. 재복사로 고쳤다(대조: 이 실행 시점 `server/config/chain_rules.json`은 `.sample`과 바이트 동일이었다 — 나머지 9개 config는 대조하지 않았으므로 이 라운드가 "전체 재동기화"를 뜻하지 않는다).
>
> **무엇인가**: 2026-08-01 트레이스 픽스처 구축 직후, 시뮬레이션 환경의 `server/config/*.json`을 **있는 그대로 복사**한 것.
> **왜 있나**: 운영에서 **보고 따라할 수 있게**. `.sample`은 형태만 보여주지만 이쪽은 **실제로 돌아가고 있는 선언 전체**다.
> **정본 아님**: 살아 있는 config는 `server/config/`이고 그쪽은 **일부러 git 밖**이다(운영 패치 시 오염 방지). 이 폴더는 **읽는 용도의 사본**이다.
>
> ### 🔴 이것은 사본이므로 **조용히 낡는다** — 갱신 주기와 책임자
>
> 사본에는 원본과 어긋났음을 알려 줄 기계가 없다. 그래서 주기를 문서에 못박는다(2026-08-04 기록).
>
> | | |
> |---|---|
> | **책임자** | Lead / Backend — `server/config/` 소유 행과 같다 |
> | **갱신 트리거 (이벤트)** | ⓐ **`.sample` 파일이 바뀌면**(사본이 즉시 `.sample`보다 낡는다 — 실제로 `2c2a777`이 두 `.sample`을 고쳤을 때 그렇게 됐다) ⓑ **config 파일이 추가·폐지되면** ⓒ **키가 추가·개명·삭제되면** |
> | **갱신 트리거 (주기)** | 위 셋이 없어도 **정비 사이클마다 한 번** 원본과 대조한다 |
> | **갱신 방법** | 이 환경의 `server/config/*.json`을 다시 복사한다. **손으로 고치지 마라** — 손으로 고친 사본은 사본도 원본도 아니고, 어느 쪽이 참인지 다음 사람이 알 방법이 없다 |
>
> ⚠️ **낡은 것을 발견하면 그것부터 적어라.** 무엇이 낡았는지 적힌 사본은 안 적힌 사본보다 낫다.
>
> ### 🔴 알려진 고장 (2026-08-04 실측) — `transfer_plan_config.json`·`bonding_plan_config.json` 사본은 **지금 이 환경에서 해석되지 않는다**
>
> 두 가지가 겹쳐 있다. **베끼지 마라.**
>
> | | |
> |---|---|
> | **① 형태가 낡음** | `2c2a777`이 고친 `.sample`보다 낡았다(보조 역할 선택성 주석) |
> | **② 실제로 안 돈다** | `transfer_plan_config.json` 사본은 본딩 stage를 **`dt_map`에 일반명(`lot`/`slot`/`x`/`y`/`val`)으로** 선언한다. 이 환경의 `dt_map` 컬럼은 `cell_key, dt_job, dt_x, dt_y, c_bn`이고 키도 `dt_job`이라 **한 역할도 해석되지 않는다.** `bonding_plan_config.json` 사본은 **이 환경에 존재하지 않는 테이블 셋**(`wafer_process`·`core_defect_map`·`eds_fail_map`)과 `bonding_log`의 **틀린 컬럼명 넷**(`core_lot`/`core_slot`/`cx`/`cy` — 실제는 `bond_*`/`dt_*`)을 가리켜 **dt stage 전체가 배선돼 있지 않다** |
>
> 🔴 **이 사본을 읽고 그 철자를 옮겨 적는 것이 2026-08-04 라이브 사고의 원인이었다** — 사람이 테이블만 `dt_log`로 바꾸고 **컬럼명은 템플릿의 일반명(`"x": "x"`)으로 남겨** 형태 검증·필수 역할 검증을 전부 통과한 채 조회 시점에만 조용히 죽었다. 이 폴더의 JSON은 **「이 환경에서는 이렇게 선언했다」의 사본**이지 이식 가능한 기본값이 아니다.
>
> ### ✅ 2026-08-14 — `transfer_plan_config.json` 사본을 **재복사**했다 (위 ①② 중 전자를 닫음)
>
> 트리거 ⓐⓒ. `dt` stage가 `source_config_ref` 위임에서 **인라인 `source`로** 옮겨가고
> (`server/M1_SOURCE_CONFIG_REF.RETIRED.md`), `bonding.total_chips`의 `x`/`y`가 `dt_x`/`dt_y`로
> 복원됐다. 사본은 `cp`로 다시 뜼으며(손편집 아님), 재복사 직후 라이브와 파싱 동일을
> 확인했다. ⚠️ **`bonding_plan_config.json` 사본은 이미 라이브와 동일했고, 그것이 문제다** —
> 위 ②가 적은 「존재하지 않는 테이블 셋」은 사본의 낛음이 아니라 **라이브의 상태**였다.
> 그 테이블 셋은 물리적으로는 존재하며(5,152 / 2,576 / 22행) `table_config.json`에서만
> 빠져 있고, 그래서 `GET /api/bonding-plan/core-summary`가 `remaining: 0`을 낸다
> — 총괄 판정 대기 → [config/bonding_plan_config](../config/bonding_plan_config.md).

> **수리는 손편집이 아니라 재복사다**(Lead / Backend). 그전까지 이 두 파일에서 계획 config를 배우지 말고 [config/transfer_plan_config](../config/transfer_plan_config.md)를 읽어라 — 그쪽 예시는 **`GET /admin/transfer-plan/dry-run`으로 수용을 실측한 것**이다.
>
> ### 🔴 알려진 고장 (2026-08-13 · doc-keeper) — `table_config.json` 사본이 `.sample`보다 **84줄** 낡았다
>
> 트리거 ⓐ·ⓑ·ⓒ가 **셋 다** 발화했는데 사본이 안 따라갔다. **이 라운드는 재복사하지 않았다 — 손으로 고치는 것이 금지돼 있기 때문이다**(위 「갱신 방법」). Lead / Backend가 재복사할 때까지 아래를 알고 읽어라.
>
> | 무엇 | 어느 커밋 |
> |---|---|
> | **`inspection_run`·`void_obs` 두 선언이 사본에 없다**(60줄) | `346aa88` |
> | **`map_doe`·`map_doe_source` 두 선언이 사본에 «아직 있다» — 은퇴했다**(84줄 삭제) | `c0fb735` |
> | `core_wafer_map.map_key_columns`의 R3 위반 정정이 사본에 없다 | `272da5b` |
>
> ⚠️ **이 사본이 `.sample`에서 왔는지 라이브에서 왔는지는 파일 자신이 말하지 않는다** — 그리고 그 둘은 지금 **같지 않다**(라이브 `table_config.json`에는 `.sample`이 가진 선언 넷이 없다, `272da5b` 실측). **사본을 라이브의 증거로 인용하지 마라.**

---

## 🔴 그대로 복사해 덮지 말 것

현장마다 테이블·컬럼·설비 이름이 다르다. 이 파일들은 **「이 환경에서는 이렇게 선언했다」**는 예시지 배포물이 아니다. 덮어쓰면 그쪽 선언이 사라진다.

**읽는 순서**: `table_config` → `maps` / `map_overlay_config` → `chain_rules` → `enrichment_rules` → `virtual_join_rules` → `ontology_mapping` → `auto_update_control`.
선언이 **테이블 → 규칙** 순인 이유는 아래 함정 ①이다.

---

> 📘 **절차는 [CONFIG_ROLLOUT_GUIDE](../CONFIG_ROLLOUT_GUIDE.md)에 있습니다.** 이 폴더는 **무엇을 선언했나**(실제 선언 사본)이고, 그쪽은 **어떤 순서로 올리고 각 단계가 먹었음을 어떻게 증명하나**(최소 선언 · 확인 명령 · 실패 모양)입니다. 아래 세 함정은 그쪽 **§4**가 명령까지 붙여 다루므로, 여기서는 요약만 두고 **고칠 때는 그쪽을 먼저 고칩니다** ― 같은 문장을 두 곳에 두면 반드시 갈립니다.

## ⚠️ 조용히 안 먹는 세 가지 (전부 이번 구축에서 실측)

### ① 규칙이 디스크에서 유효한데 워커 안에서는 죽어 있을 수 있다

체인 워커가 **자기 `TABLE_CONFIG`가 갱신되기 전에** 새 규칙을 읽고 `source_table '...' is not registered`로 거절한 뒤 **재시도하지 않았다.** 인제션 내내 옛 규칙으로 돌았고 **재기동하고서야** 잡혔다.

→ **테이블을 먼저 선언하고, 규칙은 그다음. 그리고 핫 리로드가 먹었다고 가정하지 말고 재기동한다.**

### ② `/schema`가 200이라고 config가 먹은 게 아니다

그 라우트는 **config 싱글턴**을 읽는다. 물리 반영 없이도 200이 난다.

→ 확인은 **`/tables/<테이블>/data`**로 한다. 그쪽은 실제 DB를 친다.
🔴 **정정 (2026-08-02, doc-keeper)**: 「`config_watcher`가 원자적 쓰기(temp+rename)를 감지 못한다」는 **현 트리에서 거짓**이다. `46a67c7`(2026-07-29)이 `on_moved`·`on_created`를 함께 처리하고 트레일링 엣지로 디바운스하도록 고쳤고, **세 가지 저장 형태 전부**가 잡힌다 → [CONFIG_GUIDE §4.4](../CONFIG_GUIDE.md). 다만 **watcher가 보는 파일은 `table_config.json` 하나뿐**이고, **발화했다는 것과 DDL이 성공했다는 것은 다르다** ― 물리 증거는 `information_schema`다.

### ③ 선언을 지웠는데 다른 config가 아직 가리키면 조용히 열화한다

테이블 선언을 뺄 때 `map_overlay_config` · `bonding_plan_config` · `transfer_plan_config` · `ontology_mapping` · `virtual_join_rules`가 그것을 참조하는지 확인한다. 매달린 참조는 **에러가 아니라 침묵**으로 나타난다.

### ④ 선언이 있고, 형태가 옳고, 테이블도 맞고, 역할도 다 있는데 — **컬럼 철자 하나가 틀렸다** (2026-08-04 신설)

세 개의 형제였던 목록에 넷째가 생겼다. 앞의 셋과 달리 이것은 **아무것도 비어 있지 않은** 실패다. `"columns": {"x": "x"}`에서 **왼쪽은 시스템이 정한 역할 이름이고 오른쪽은 그 테이블에 실존해야 하는 컬럼명**인데, 철자가 우연히 같으면 그 줄이 동어반복처럼 맞아 보여 검토를 통과한다. 그리고 종전에는 화면이 **「선언돼 있지 않습니다」**라고 말해 — 선언은 **있는데도** — 원인을 정반대로 가리켰다.

`12c1d2e` 이후 거절은 **자기 사유를 이름으로 말하고**, `8817dde` 이후 **`GET /admin/transfer-plan/dry-run`이 저장 전에 그 판정을 돌려준다.**

→ **이 실패 모양의 정본은 [config/transfer_plan_config §6](../config/transfer_plan_config.md)**(화면 문장 → 무엇을 고치나)다. 여기 사본을 만들지 말 것.

---

## 파일별 한 줄

| 파일 | 무엇을 선언하나 |
|---|---|
| `table_config.json` | 테이블·컬럼·타입·비즈니스 키. **모든 것의 전제** |
| `maps.json` | 맵 프리셋(격자·물리 규격) |
| `map_overlay_config.json` | 맵 오버레이 바인딩 |
| `chain_rules.json` | 한 테이블 쓰기가 다른 테이블로 파생되는 규칙 |
| `enrichment_rules.json` | 결손 보정 ― 참조뷰·후보 선언·자동확정 노브 |
| `virtual_join_rules.json` | 조회 시점 조인(저장 안 함). ⚠️ **조인 키에 UNIQUE 인덱스가 없으면 선언을 거부**하고 만들 DDL을 알려준다 |
| `ontology_mapping.json` | 행 → 그래프 노드·엣지 승격 |
| `bonding_plan_config.json` · `transfer_plan_config.json` | 계획 화면의 역할 바인딩. 🔴 **이 두 사본은 현재 해석되지 않는다**(헤더의 「알려진 고장」) · 수용 여부를 묻는 자리는 `GET /admin/transfer-plan/dry-run` |
| `auto_update_control.json` | 수집기별 on/off. **데이터를 계속 만드는 자리이자 옛 수집기를 끄는 자리** |

**제외**: `scheduler_status.json` · `supervisor_status.json` ― 런타임 상태이지 설정이 아니다.

---

## 이 스냅샷의 내용에 대해

이 환경은 **코어 자재 추적 픽스처**를 위해 구성돼 있다. 선언의 *의도*는 [`docs/spec/TRACE_FIXTURE_SPEC.md`](../../spec/TRACE_FIXTURE_SPEC.md)에 있고, 구축 중 무엇이 실패했는지는 [`agent_workspace/reports/Server_trace_fixture_environment.md`](../../../agent_workspace/reports/Server_trace_fixture_environment.md)에 있다.

📌 **`chain_rules.json`의 `dt_log_to_dt_map`은 `enabled: false`다.** 실수가 아니다 ― 체인은 맵 셀을 **upsert할 수 있어도 purge할 수 없어서**, 갱신된 작업의 옛 셀이 영원히 남는다. 켜기 전에 그 파일의 주석을 읽을 것.
