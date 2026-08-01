# 📋 config 참조 스냅샷 (시뮬레이션 환경)

> **무엇인가**: 2026-08-01 트레이스 픽스처 구축 직후, 시뮬레이션 환경의 `server/config/*.json`을 **있는 그대로 복사**한 것.
> **왜 있나**: 운영에서 **보고 따라할 수 있게**. `.sample`은 형태만 보여주지만 이쪽은 **실제로 돌아가고 있는 선언 전체**다.
> **정본 아님**: 살아 있는 config는 `server/config/`이고 그쪽은 **일부러 git 밖**이다(운영 패치 시 오염 방지). 이 폴더는 **읽는 용도의 사본**이다.

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
| `bonding_plan_config.json` · `transfer_plan_config.json` | 계획 화면의 역할 바인딩 |
| `auto_update_control.json` | 수집기별 on/off. **데이터를 계속 만드는 자리이자 옛 수집기를 끄는 자리** |

**제외**: `scheduler_status.json` · `supervisor_status.json` ― 런타임 상태이지 설정이 아니다.

---

## 이 스냅샷의 내용에 대해

이 환경은 **코어 자재 추적 픽스처**를 위해 구성돼 있다. 선언의 *의도*는 [`docs/spec/TRACE_FIXTURE_SPEC.md`](../../spec/TRACE_FIXTURE_SPEC.md)에 있고, 구축 중 무엇이 실패했는지는 [`agent_workspace/reports/Server_trace_fixture_environment.md`](../../../agent_workspace/reports/Server_trace_fixture_environment.md)에 있다.

📌 **`chain_rules.json`의 `dt_log_to_dt_map`은 `enabled: false`다.** 실수가 아니다 ― 체인은 맵 셀을 **upsert할 수 있어도 purge할 수 없어서**, 갱신된 작업의 옛 셀이 영원히 남는다. 켜기 전에 그 파일의 주석을 읽을 것.
