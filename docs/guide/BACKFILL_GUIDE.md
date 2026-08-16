# 🔁 소급 적용 가이드 — 규칙을 「이미 쌓인 데이터」에 적용하는 길들

> **Status:** 🟢 Living | **작성:** 2026-07-31 · doc-keeper | **Last-verified:** 2026-08-14
>
> **이번 라운드 (2026-08-14 · `2ec78b9` · R-2026-08-14-H — ⓔ가 «없어졌습니다»)**
> - ⚰️ **ⓔ 그래프 고아 스윕 은퇴** — 지울 대상(`graph_nodes`/`graph_edges`/`graph_sync_state`)이 **DROP**됐습니다(약 841 MB). `server/retroactive.py`의 `OPERATIONS`가 다섯에서 **넷**(`chain_replay`·`withdraw`·`enrichment_backfill`·`enrichment_confirm`)이 되어 어드민 API에서도 **등록 해제**됐고, 스케줄러의 자동 호출도 제거됐습니다.
> - 🔴 **이 문서에서 「다섯」이라 적힌 자리는 전부 「넷」으로 읽으십시오** — §5 · §6.2 · §6.3 · §7의 ⓔ 관련 서술은 접혀 있습니다. **ⓐ~ⓓ와 ⓕ는 한 줄도 영향받지 않았습니다.**
>
> **직전 라운드 (2026-08-11 2차 · `ffb23d6`+`53f9187` — ⓕ와 ⓑ가 더 이상 하류 체인을 깨우지 않습니다)**
> - 🔴 **§2.3에 ⓑ(철회)의 같은 수리를 실었습니다**(`53f9187`). **이쪽이 더 급했습니다 — 철회는 어드민 화면의 버튼에서도 돌아갑니다.** 지워지는 층은 한 줄도 달라지지 않았고(살아남은 층 집합이 바이트 단위로 동일), `user` 거절과 사람 핀 건너뛰기는 **CLI·버튼 양쪽에서** 그대로입니다.
> - 🔴 **화면 알림 4건 → 0건은 잃은 것이 아닙니다** — 그 4건은 아무도 철회하지 않은 다른 테이블의 알림이었고, **값이 바뀐 칸은 전에도 지금도 알림이 안 갑니다.** 확인하는 자리는 셀 이력 타임라인이고 변하지 않았습니다.
> - ⚠️ **ⓐ(재적용)만 아직 페이지 단위로 묶입니다** — 라벨은 원래 맞았고 그룹핑만 남았습니다(미수리).
> - 🔴 **§2.5에 운영자용 사실 셋 추가.** ⓕ가 내는 내부 이벤트가 **사람이 그리드에서 친 것과 똑같은 라벨**을 달고 있어서, 칸 하나를 고치면 그 테이블에 걸린 파생 규칙이 전부 돌았습니다. 지금은 **명시적으로 선언한 규칙만** 반응하고, 대량 실행이 실행당 그룹 하나로 접혀 훨씬 빨라졌습니다(종전에는 수리 행마다 직렬 그룹 — 1만 행이 한 시간을 넘겼고 그동안 정상 인제션이 뒤에 줄을 섰습니다).
> - ⚠️ **`ffb23d6`(ⓕ) / `53f9187`(ⓑ) 이전에 그 명령을 `--apply`로 돌린 적이 있으면 딸려 들어간 파생 쓰기가 있을 수 있습니다** — 그 시각의 체인 워커 로그로 확인하십시오.
>
> **직전 라운드 (2026-08-11 · 해결 순서 수리 + R3 착지)**
> - **신규 경로 ⓕ — R3 `chain_replay_cli.py resolve`**(§2.5). 같은 CLI의 **세 번째 연산**이라 **스크립트 수는 그대로 넷**이고, 결정표·§1의 공통 규율에 행이 하나 늘었습니다.
> - 🔴 **제목의 「다섯 가지 길」을 여섯으로 고치지 않고 기수를 지웠습니다** — 목록 옆의 수는 목록의 두 번째 사본이고, 이 문서에서 그 수는 **§0 결정표·§1 서두·§7 서두** 세 자리에 사본이 있었습니다. 목록이 정본입니다.
> - 🔴 **ⓕ만 어드민 API에 없습니다** — `server/retroactive.py`의 `OPERATIONS`는 `chain_replay`·`withdraw`·`enrichment_backfill`·`enrichment_confirm`·`graph_orphans` **다섯**이고 R3는 등재돼 있지 않습니다(실측). §0과 §7의 「전부 어드민 API로도 됩니다」는 **ⓐ~ⓔ에 대해서만** 참입니다.
> - **§1.1 레이어링 표 갱신** — 표시값 결정이 **등재 우선순위 → `ingested_at` 내림차순 → `source_name` 오름차순**의 전순서가 됐습니다. 종전에는 미등재 이름이 전부 99로 **동점**이었고 승자가 삽입 순서로 떨어졌습니다(ⓒ·ⓓ가 둘 다 99인 것은 그대로이며, 이제 그 둘 사이도 결정적으로 갈립니다).
> - **§6.1 갱신** — `--limit`의 뜻 표에 ⓕ 행 추가(**훑는 행 수** 상한).
>
> **직전 라운드 (2026-07-31 · `fbc1053`·`1948338`·`9c6a1c9`)**
> - **§7 재작성 — 어드민 API가 착지했습니다**(라우트 3개). 🔴 **화면(버튼)은 아직 없습니다** — 「어드민 화면에는 자리가 없다」는 종전 문장은 절반만 참이 됐습니다. 지금 쓰려면 `curl`입니다.
> - **§7.2 신설 — 카운트는 「어떤 종류의 수인지」를 함께 답합니다**(`exact`/`sample`/`upper_bound`). 다섯 중 넷은 요청 경로에서 정확할 수 없고, **어느 것도 정확하다고 주장하지 않습니다.**
> - **§3에 각주 — ⓒ의 구현이 `server/enrichment_backfill.py`로 옮겨졌습니다**(`9c6a1c9`). **CLI 경로·진입점·플래그는 그대로**라 이 문서가 찍는 명령은 전부 그대로 동작합니다.
> - **§6.5·§6.6 신설** — ⓒ의 「이미 있는 정체성」 읽기가 **두 갈래**가 됐고(CLI는 전량 스냅샷, 미리보기는 표본 키만 되물음), **ⓑ R2의 카운트가 인덱스를 얻었습니다**(`1948338`). 새 DB에 반영하는 경로는 `setup_db_performance.py` 하나입니다.
>
> (신설 근거: 진입점 전부의 argparse를 **소스 대조 + `--help` 실행**으로 전수 확인 — `server/scripts/chain_replay_cli.py` · `backfill_enrichment.py` · `enrichment_insights.py` · `graph_orphan_sweep.py`, 그리고 의미론은 `server/chain_replay.py` · `server/enrichment_analysis.py` · `server/enrichment_candidates.py` · `server/graph_orphans.py` · `server/keyset_scan.py` · `crud.SOURCE_PRIORITY`/`apply_batch_updates`)
> **대상:** 규칙을 바꿔 놓고 **「과거 데이터는 왜 그대로지?」**를 만난 운영자.
> **먼저 알아야 할 것:** 이 시스템의 규칙은 **증분(outbox) 구동**이다. 규칙은 **자기가 선언된 이후에 바뀐 행만** 본다. 규칙을 고쳐도 과거는 옛 규칙이 남긴 상태 그대로 있고, 그것을 움직이는 유일한 방법이 이 문서의 경로들이다. ⓕ가 그 원리의 가장 순수한 사례다 — **해결 규칙 자체를 고쳐도** 이미 확정된 표시값은 그대로 남는다.
> **관련:** 개발자 계약은 [chain_ingestion_guide §5](./chain_ingestion_guide.md) · 인리치먼트 선언은 [config/enrichment_rules §7](./config/enrichment_rules.md). 제거된 그래프 고아 스윕의 배경은 [archive](../_archive/retired_graph_sync/README.md)에만 남깁니다.

---

## 0. 30초 — 어느 것을 써야 하나

**증상에서 출발하십시오.** 도구 이름에서 출발하면 ⓒ와 ⓓ를 반드시 헷갈립니다.

| 지금 보이는 것 | 써야 할 것 |
|---|---|
| 체인 룰을 새로 만들었거나 고쳤는데 **옛날 행에는 반영이 안 됐다** | **ⓐ R1** `chain_replay_cli.py replay <룰>` |
| 옛 룰이 만든 **틀린 값이 아직 이기고 있다**. 룰을 고쳐 재적용해도 그 칸은 안 바뀐다 | **ⓑ R2** `chain_replay_cli.py withdraw <테이블> <소스>` |
| 파생 테이블에 **행 자체가 없다**. 워크리스트에도 안 뜬다 | **ⓒ** `backfill_enrichment.py <룰>` |
| 파생 **행은 있는데** 타깃 칸이 **비어 있다**. 워크리스트에는 떠 있다 | **ⓓ** `enrichment_insights.py confirm <룰>` |
| ~~매핑을 바꿨더니 그래프에 **아무 데도 안 붙은 노드**가 남았다~~ | ⚰️ **[2026-08-14] ⓔ 은퇴** — 그래프 저장소가 DROP돼 이 증상이 존재하지 않습니다(§5) |
| 칸에 **여러 소스가 쌓여 있는데 옛 층이 표시되고 있다**. 소스 목록을 열면 새 값이 **저장은 돼 있다** | **ⓕ R3** `chain_replay_cli.py resolve <테이블>` |

🔴 **ⓒ와 ⓓ를 가르는 질문은 하나입니다 — 「파생 테이블에 그 행이 있습니까?」**
`ⓒ`는 **없던 파생 행을 만듭니다.** `ⓓ`는 **이미 있는 행의 빈 칸을 채웁니다.**
잘못 고르면 **에러 없이 아무 일도 안 일어나고**, 운영자는 기능이 고장 났다고 결론짓습니다. 실제로 그렇게 한 번 잃었습니다.

🔴 **ⓑ와 ⓕ를 가르는 질문도 하나입니다 — 「그 층이 *틀렸습니까*, 아니면 *지고 있습니까*?」**
`ⓑ`는 **더는 사실이 아닌 층을 걷어냅니다**(그 소스의 주장을 지웁니다). `ⓕ`는 **아무것도 걷어내지 않고**, 이미 있는 층들로 승자를 다시 계산합니다. 옛 값이 **여전히 그 소스의 정당한 값인데** 새 층에게 자리를 내주지 못하고 있는 상황이 ⓕ입니다.

> ⓔ만 성격이 다릅니다. ⓐ~ⓓ가 **만들거나 고치는** 소급이라면 **ⓔ는 지우는 소급**입니다. §5에서 따로 다룹니다.

> 📍 **ⓐ~ⓔ는 어드민 API로도 됩니다**(2026-07-31 `fbc1053` — 건수 조회 + 실행). **화면의 버튼은 `77d27d3` 기준 아직 없어**(작업 진행 중) 지금은 `curl`이고, 절차·주의는 **§7**에 있습니다. 결정표는 도구를 고르는 자리이므로 **어느 표면을 쓰든 위 표가 먼저입니다.**
> ⚠️ **ⓕ는 어드민 API에 없습니다 — CLI 전용입니다**(`server/retroactive.py`의 `OPERATIONS`에 등재돼 있지 않음, 2026-08-11 실측). `/admin/retroactive/operations`가 돌려주는 목록에 안 나오는 것이 정상입니다.

---

## 1. 전부가 공유하는 규율 — 한 번만 말합니다

이 넷은 위 결정표의 경로 **모두**에 해당합니다. 개별 절에서 반복하지 않습니다.

1. **기본은 dry-run입니다.** 아무 플래그 없이 돌리면 **읽기만** 합니다. 먼저 돌려서 보고서를 읽는 것이 정상 절차입니다.
2. **`--apply`만이 씁니다.** 쓰기를 시작하는 스위치는 이것 하나뿐이고, 다른 이름의 우회로는 없습니다.
3. **진짜 매퍼와 진짜 쓰기 경로를 씁니다.** 소급 전용 구현이 따로 없습니다 — 매퍼 산출물은 그대로 쓰고 provenance만 찍으며, 쓰기는 라이브와 같은 `crud.apply_batch_updates`를 지납니다. **그래서 소급 결과와 라이브 결과가 갈리지 않습니다.**
   ⚠️ **ⓕ는 매퍼를 부르지 않습니다** — 그 경로가 다시 돌리는 것은 매퍼가 아니라 **해결 함수**(`crud.compute_priority_value`)이고, 그것 역시 **라이브와 같은 함수**라 이 규율의 취지는 그대로입니다.
4. **페이지 단위로 커밋합니다.** 대량 실행을 중간에 끊어도 되고, 다시 돌리면 이미 처리된 것을 다시 진단해 이어서 갑니다.
   ⚠️ **ⓔ는 예외입니다** — §6.2를 보십시오.
5. **어느 것도 새 이벤트 타입이나 새 화면을 만들지 않습니다.** 결과를 설명하는 자리는 **기존 셀 이력 타임라인** 하나이고(ⓑ·ⓕ가 감사 행을 남깁니다), 소급 전용 UI는 없습니다.
   ⚠️ **「돌렸는데 화면이 안 바뀐다」면 새로고침부터** 해 보십시오 — 붙어 있는 화면이 즉시 갱신된다고 **약속하지 않습니다.**

### 1.1 무엇이 어떤 이름으로 쓰이는가 (레이어링)

표시값은 **소스 우선순위**로 결정됩니다(숫자가 낮을수록 이깁니다). 소급이 사람 값을 밀어내지 못하는 근거가 여기 있습니다.

| 경로 | 쓰기 소스명 | 우선순위 |
|---|---|---|
| ⓐ R1 | `chain_ingestion` — **라이브 워커와 같은 이름** | 4 |
| ⓑ R2 | (셀 소스를 **쓰지 않고 지웁니다**. 감사 기록만 `chain_replay_withdraw`) | — |
| ⓒ backfill | `enrichment_backfill` | 미등재 → **99** |
| ⓓ confirm | `enrichment_auto_confirm` | 미등재 → **99** |
| ⓓ confirm (부분 판단키) | `enrichment_auto_confirm_partial_key` | 미등재 → **99** (ⓓ와 **같은 서열**, 이름만 다르다 - 판단키가 일부만 있는 채로 결정된 셀을 나중에 결정된 것으로 골라내기 위한 표식이지 승격이 아니다) |
| ⓔ 고아 스윕 | (셀이 아니라 **그래프 노드**를 지웁니다) | — |
| ⓕ R3 | (셀 소스를 **쓰지도 지우지도 않습니다**. 감사 기록만 `resolution_recompute`) | — |

`SOURCE_PRIORITY`의 실제 값은 `user: 0` · `collision_merge: 1` · `pipeline_parser: 2` · `custom_script: 3` · `chain_ingestion: 4`이고, **등재되지 않은 이름은 전부 99**입니다.

🔴 **같은 우선순위 안에서는 무엇이 이깁니까 — 2026-08-11부터 답이 있습니다.** 종전에는 미등재 이름이 **전부 99로 동점**이었고 승자가 목록 조립 순서로 떨어졌습니다(그리고 그 순서는 **기존 값이 항상 이기도록** 돼 있었습니다). 지금 순서는 **① 등재 우선순위 → ② `ingested_at` 내림차순(최신 배달이 승, 날짜 없는 층은 뒤로) → ③ `source_name` 오름차순**이고, ③이 있어 **언제나 결판이 납니다.**
**소급 관점에서 이것이 뜻하는 것 둘** — ⓒ와 ⓓ는 여전히 둘 다 99지만 이제 그 **둘 사이도 결정적으로** 갈립니다(먼저 도착한 쪽이 아니라 **나중에 도착한 쪽**이 이깁니다). 그리고 **이미 확정된 칸은 이 수리로 저절로 안 움직입니다** — 그것을 움직이는 것이 **ⓕ**입니다(§2.5).
⚠️ **서열 자체는 한 칸도 안 움직였습니다** — ②③은 **한 우선순위 *안에서만*** 동점을 가르며, 낮은 서열을 높은 서열 위로 올리지 못합니다.

🔴 **`user`(0)가 사람이 직접 입력한 유일한 레이어입니다.** ⓐ는 4로, ⓒ·ⓓ는 99로 쓰므로 **어느 것도 사람 값을 표시에서 밀어내지 못합니다.** R1에 사람 값 특례 코드가 없는 이유가 이것입니다 — 레이어링이 이미 처리합니다.

> ⚠️ `table_config.json`의 테이블별 `source_priority`로 서열을 커스텀한 테이블에서는 위 숫자가 그 테이블의 맵으로 대체됩니다(`crud.resolve_priority_map`). 미등재 → 99 규칙은 어느 맵에서든 같습니다.

---

## 2. ⓐⓑⓕ 체인 리플레이 — CLI 하나, 연산 셋

```bash
conda run -n assy_manager python server/scripts/chain_replay_cli.py list
```

**먼저 이것부터 돌리십시오.** 활성 룰 목록과 **재적용 순서**, 그리고 자기 트리거 룰에 `[SELF-TRIGGERING]` 표시를 보여 줍니다.

### 2.1 ⓐ R1 — 룰을 현재 데이터 전체에 다시 적용

```bash
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <룰>
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <룰> --apply
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <룰> --limit 500
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay <룰> --chunk-size 2000

conda run -n assy_manager python server/scripts/chain_replay_cli.py replay-all
conda run -n assy_manager python server/scripts/chain_replay_cli.py replay-all --apply
```

트리거 테이블의 **현재 내용**을 키셋 페이지로 훑어 실제 매퍼로 다시 흘려보냅니다. `replay-all`은 **의존 순서대로 각 룰을 정확히 1회씩** 돌립니다(생산자가 소비자보다 먼저).

dry-run 보고서에서 볼 것:

* **`cells a human protects`** — 재적용이 자기 레이어를 쓰긴 하지만 **사람 값이 계속 이기는** 칸 수입니다. 안전성을 말이 아니라 수로 보여 주는 자리입니다.
* **`cells with NO value`** — 룰이 더는 값을 만들지 않는 칸입니다. **R1은 여기에 아무것도 쓰지 않고** 아래의 「철회 후보」로 보고만 합니다.

### 2.2 왜 여러 연산인가 — 가르는 문장 둘

> **① 「이 룰이 여기서 더는 값을 만들지 않는다」와 「값이 비었다」는 다른 진술이고, 앞엣것을 표현할 수 있는 것은 R2뿐입니다.**
> **② 「저장된 층이 틀렸다」와 「저장된 층 중 *엉뚱한 것이 이기고 있다*」도 다른 진술이고, 뒤엣것을 표현할 수 있는 것은 R3뿐입니다.**

그래서 **R1은 절대 공백을 쓰지 않습니다.** 공백을 쓰면 그것은 「값이 비었다」는 주장이 되어, 아래 레이어에 살아 있는 다른 소스의 값을 가려 버립니다. R1은 값이 사라진 칸을 **철회 후보**로 보고하고 추측을 거부합니다 — 보고서가 직접 R2 명령줄을 찍어 줍니다.

### 2.3 ⓑ R2 — 낡은 소스 철회 (**층에서** 철회, 행에서가 아니라)

```bash
conda run -n assy_manager python server/scripts/chain_replay_cli.py withdraw <테이블> <소스>
conda run -n assy_manager python server/scripts/chain_replay_cli.py withdraw <테이블> <소스> --columns col1,col2
conda run -n assy_manager python server/scripts/chain_replay_cli.py withdraw <테이블> <소스> --columns col1 --apply
```

동작은 **셀 하나당 이것뿐**입니다 — `cell_sources` 행 **하나**를 지우고, 남은 소스로 `compute_priority_value`를 다시 계산해 표시값을 되돌립니다.

🔴 **행을 지우거나 컬럼을 NULL로 만들지 않는 이유**: 그 두 방법은 **다른 모든 소스의 기여까지 파괴합니다.** 층에서만 걷어내면, 두 소스가 그 칸을 주장하고 있었을 때 운영자는 **구멍이 아니라 나머지 하나를 봅니다.**

보고서의 세 수가 결과를 나눕니다 — `revealed another layer`(아래 층이 드러남) / `left empty`(주장이 그것 하나뿐이었음) / `value unchanged`(표시값은 그대로).

**철회는 무음이 아닙니다.** 표시값이 바뀐 셀마다 `AuditLog`에 `withdraw:<소스명>`이 남고, 클라의 **기존 셀 이력 타임라인**이 그것을 읽습니다. 빈칸을 발견한 운영자가 셀을 눌러 「어느 소스가 사라졌는지」를 봅니다. 신규 화면도 신규 이벤트도 없습니다.

🔴 **[2026-08-11 `53f9187`] 이 명령도 더 이상 하류 체인을 깨우지 않습니다.** ⓕ와 똑같은 결함이었고, **이쪽이 더 급했습니다** — ⓕ는 사람이 CLI 앞에 앉아야 하지만 **철회는 어드민 화면의 버튼에서도 돌아갑니다**(§7). 수리 뒤 실측: 대상 테이블 4개 → **0**, 실행 하나가 그룹 하나.
- 🔴 **지워지는 층은 한 줄도 달라지지 않았습니다.** 무엇을 지울지는 **명령에 준 소스 이름**이 정하고 이번 수리가 건드린 것은 내부 이벤트의 꼬리표뿐입니다 — 같은 픽스처로 전후를 돌려 **살아남은 층 집합이 바이트 단위로 동일**함을 확인했습니다. `user` 소스 거절과 사람 핀 건너뛰기도 **CLI·어드민 버튼 양쪽에서** 그대로입니다.
- 🔴 **화면 알림이 4건에서 0건이 된 것은 잃은 것이 아닙니다.** 원래 그 4건은 **아무도 철회하지 않은 다른 테이블**의 알림이었고(딸려 돌던 파생 쓰기가 낸 것), **정작 값이 바뀐 칸은 전에도 지금도 알림이 안 갑니다.** 철회 결과를 확인하는 자리는 **셀 이력 타임라인**이고 그것은 변하지 않았습니다.
- ⚠️ **`53f9187` 이전에 철회를 `--apply`로 돌린 적이 있으면 딸려 들어간 파생 쓰기가 있을 수 있습니다** — 그 시각의 체인 워커 로그로 확인하십시오.

### 2.4 사람 값은 이 문서의 어느 경로로도 지워지지 않습니다

R2의 **거절 두 개**가 그 보장의 전부입니다.

| 거절 | 이유 |
|---|---|
| `withdraw <테이블> user` | 사람이 입력한 값입니다. 도구가 지우지 않습니다 — **셀을 편집하십시오.** 명령이 아예 거부됩니다 |
| 그 소스를 사람이 **핀**한 셀(`manual_priority_source`) | 핀은 「이 소스를 보여 달라」는 사람의 선택입니다. 조용히 철회하면 그 선택을 뒤집습니다 → `pinned_skipped`로 세고 이유를 남기며 **건너뜁니다** |

### 2.5 ⓕ R3 — 표시값 재계산 (**아무것도 지우지 않습니다**)

```bash
conda run -n assy_manager python server/scripts/chain_replay_cli.py resolve <테이블>
conda run -n assy_manager python server/scripts/chain_replay_cli.py resolve <테이블> --columns col1,col2
conda run -n assy_manager python server/scripts/chain_replay_cli.py resolve <테이블> --list-all
conda run -n assy_manager python server/scripts/chain_replay_cli.py resolve <테이블> --apply
```

플래그: `--columns` · `--limit`(훑는 **행** 수 상한) · `--chunk-size`(기본 1000) · `--list-all` · `--apply`.

**언제 이것입니까.** 칸에 소스가 **둘 이상** 쌓여 있고, 소스 모달을 열어 보면 **새 값이 저장은 돼 있는데** 화면에는 옛 값이 나옵니다. 새 배달이 도착하긴 했는데 **동점 판정에서 지고 있었던** 상황입니다. 이긴 값은 컬럼에 **박제(materialise)**되고 모든 조회가 층이 아니라 그 컬럼을 읽으므로, **판정 규칙을 고쳐도 이미 확정된 칸은 저절로 안 움직입니다.** 그것을 움직이는 것이 이 명령입니다.

- 🔴 **`cell_sources` 행을 하나도 만들지 않고 지우지 않고 고치지 않습니다.** 움직이는 것은 **화면에 보이는 값** 하나뿐입니다. ⓑ와의 차이가 여기 있습니다 — ⓑ는 층을 **없앱니다.**
- 🔴 **층이 2개 미만인 칸은 절대 건드리지 않습니다.** 층이 하나면 가를 동점이 없고, **층이 0개면 칸을 비워 버립니다**(다른 쓰기 경로가 소유한 컬럼을 이 명령이 지워 버리는 일). 그래서 전체 테이블에 돌려도 자기가 이해하지 못하는 데이터를 파괴할 수 없습니다.
- **사람의 핀은 그대로 존중됩니다.** 핀은 「어느 층을 보여 달라」이고 이 명령은 그 선택을 그대로 따릅니다 — 보고서의 `of which human-pinned`는 「핀을 무시했다」가 아니라 **「화면이 그 핀에서 벗어나 있었고 되돌렸다」**입니다.
- **dry-run이 곧 목록입니다.** `--apply` 없이 돌리면 바뀔 칸을 그대로 찍습니다(기본 20건, 전량은 `--list-all`). 두 사유를 구분해 읽으십시오 — **`tie broken by recency`**(동점이 있었다) vs **`already out of step`**(층과 화면이 애초에 어긋나 있었다).
- **바뀐 칸마다 이력이 남습니다** — `resolution_recompute` · `resolved:<이긴 소스명>` · old/new. 셀 이력 타임라인에서 그대로 보입니다. **감사 기록 없이 값만 바뀌는 일은 없습니다**(`--apply`는 둘 다 하거나 둘 다 안 합니다).
- ⚠️ **ⓕ만 어드민 API에 없습니다** — `/admin/retroactive/operations`에 안 나옵니다(§0 참조). CLI로만 돌립니다.
- ⚠️ **화면이 즉시 갱신된다고 보장하지 않습니다.** 다 돌린 뒤 새로고침해서 확인하십시오.
- 🔴 **[2026-08-11 `ffb23d6`] 이 명령은 하류 체인을 깨우지 않습니다 — 종전에는 깨웠습니다.** 수리된 행마다 나가는 내부 이벤트가 **사람이 그리드에서 친 것과 똑같은 라벨**을 달고 있어서, 칸 하나를 고치면 그 테이블에 걸린 파생 규칙이 전부 돌고 다른 테이블에 쓰기까지 했습니다. 지금은 `chain_ingestion` 라벨이라 **그 이벤트를 받겠다고 명시적으로 선언한 규칙(`allow_chain_trigger`)만** 반응합니다.
  - ⚠️ **`ffb23d6` 이전에 이 명령을 `--apply`로 돌린 적이 있으면, 그때 파생 테이블에 딸려 들어간 쓰기가 있을 수 있습니다.** 어느 테이블인지는 그 시각의 체인 워커 로그에서 확인하십시오.
  - **대량 실행이 훨씬 빨라졌습니다** — 종전에는 수리 행마다 별도 그룹으로 직렬 처리돼(그룹당 ~0.4초) 1만 행이 한 시간을 넘겼고 그동안 **정상 인제션이 뒤에 줄을 섰습니다.** 지금은 실행 전체가 그룹 하나입니다.
  - ✅ **ⓑ(철회)도 같은 날 닫혔습니다**(`53f9187` — §2.3). ⓐ(재적용)만 아직 페이지 단위로 묶여 있어 대량 실행이 여러 그룹으로 갈립니다.

> 🔴 **이 명령은 「같은 값이 여러 번 쌓이는 문제」를 고치지 않습니다.** 고치는 것은 **쌓인 것 중 무엇이 이기는가**뿐입니다. 저장량 증가는 별개의 미해결 과제입니다.

---

## 3. ⓒ backfill_enrichment — **파생 행 자체가 없을 때**

```bash
conda run -n assy_manager python server/scripts/backfill_enrichment.py <룰>
conda run -n assy_manager python server/scripts/backfill_enrichment.py <룰> --apply
conda run -n assy_manager python server/scripts/backfill_enrichment.py <룰> --apply --limit 100
conda run -n assy_manager python server/scripts/backfill_enrichment.py <룰> --force-disabled
conda run -n assy_manager python server/scripts/backfill_enrichment.py <룰> --chunk-size 2000
```

**언제**: 규칙 선언 **이전에** 적재된 소스 행은 파생 행을 만든 적이 없습니다. 워크리스트는 존재하지 않는 행을 보여 줄 수 없으므로, 운영자 눈에는 **그 데이터가 통째로 없는 것처럼** 보입니다.

**무엇을 하나**: 소스 테이블을 한 번 훑어 판단키 조합을 뽑고, 파생 테이블에 **없는 조합만** 골라 진짜 매퍼로 새 파생 행을 만듭니다.

🔴 **이미 있는 파생 행은 절대 건드리지 않습니다.** 그 행의 빈 칸은 워크리스트(그리고 ⓓ)의 일이지 이 스크립트의 일이 아닙니다. 보고서의 `already derived : N (NOT touched)`가 그 경계입니다.

**만들어진 행의 타깃 칸은 비어 있습니다.** 그것이 정상입니다 — 행이 생겼으니 이제 워크리스트가 그것을 집어 갑니다. dry-run 보고서 마지막 줄이 그렇게 말합니다.

* `--limit N`은 **새로 만들 파생 정체성의 수**를 자릅니다(스캔 행 수가 아닙니다). 잘린 만큼은 `skipped by --limit`로 보고되고 **다시 돌리면 이어서** 갑니다.
* `--force-disabled`는 `"enabled": false`인 규칙도 돌립니다. 규칙을 아직 켜지 않은 채 규모만 재 보고 싶을 때 씁니다.

> ℹ️ **2026-07-31 `9c6a1c9` — 이 도구의 알맹이는 `server/enrichment_backfill.py`로 옮겨졌고, `scripts/backfill_enrichment.py`는 그 위의 CLI가 됐습니다.** **경로·진입점·플래그는 하나도 바뀌지 않았으므로 위 명령은 전부 그대로 동작합니다.** 의미론은 `server/`에, argparse와 출력은 `server/scripts/`에 두는 분리가 `chain_replay`와 enrichment 도구에 적용됩니다.

---

## 4. ⓓ enrichment_insights confirm — **행은 있고 타깃 칸이 빌 때**

```bash
conda run -n assy_manager python server/scripts/enrichment_insights.py confirm <룰>
conda run -n assy_manager python server/scripts/enrichment_insights.py confirm <룰> --apply
conda run -n assy_manager python server/scripts/enrichment_insights.py confirm <룰> --ignore-knob
conda run -n assy_manager python server/scripts/enrichment_insights.py confirm <룰> --limit 500
conda run -n assy_manager python server/scripts/enrichment_insights.py confirm
```

**룰 이름을 생략하면 활성 규칙 전체**를 돕니다(세 서브커맨드 모두 같습니다).

**언제**: 파생 행은 이미 있고 워크리스트에도 떠 있는데, 사람이 하나씩 채우고 있는 칸이 **사실은 참조뷰가 답을 하나만 내놓는** 칸일 때. 그 경우 사람의 판단이 필요 없습니다.

**무엇을 하나**: 미해결 파생 행의 빈 타깃마다 참조뷰에 물어, **후보가 정확히 하나일 때만** 그 값을 채웁니다. 후보가 여럿이거나 없으면 채우지 않고 **사유별로 세어** 보고합니다.

같은 CLI의 나머지 둘은 소급 쓰기가 아니라 **조사 도구**입니다(둘 다 읽기 전용).

```bash
conda run -n assy_manager python server/scripts/enrichment_insights.py classify <룰> --max-keys 200
conda run -n assy_manager python server/scripts/enrichment_insights.py propose  <룰> --min-support 3
```

* `classify` — 워크리스트의 결손을 원인별로 분류합니다(**파이프라인 버그** / 기계적으로 해결 가능 / **진짜 사람 일**). 「이 워크리스트 중 사람이 꼭 봐야 하는 건 몇 건인가」에 답합니다.
* 🔴 **`--max-keys`는 「몇 개의 키를 볼까」이지 「읽기를 얼마나 넓힐까」가 아니다** (구 이름 `--probe-limit`은 별칭으로 남아 있고 경고를 냅니다). 절단(`probe_truncated`/`distinct_truncated`) 거절을 쫓는 중이라면 읽기 상한 쪽입니다: `--probe-scan-rows`(행) · `--probe-distinct-values`(distinct 값). 이 둘은 `classify`와 `confirm` **양쪽에** 있습니다 — 한쪽 상한으로 재고 다른 상한으로 쓰면 두 화면이 어긋납니다. 영구 선언은 `server/config/ingestion_settings.json`의 `enrichment_read_caps`.
* 🔴 **상한을 올리기 전에 거절 보고의 `raising it -> AMBIGUOUS` 줄을 보십시오.** 그 건수는 이미 서로 다른 값이 둘 이상 읽힌 건이라 상한을 올려도 `ambiguous`로 이름만 바뀝니다(사람이 판단할 몫). 그리고 참조뷰가 키 하나당 수천 행을 돌려준다면 문제는 상한이 아니라 **뷰가 좁혀지지 않는 것**이고, 그건 `missing_bind`와 같은 계급입니다.
* `propose` — 사람이 반복한 판단을 규칙 후보로 승격 제안합니다. **아무것도 적용하지 않고**, 붙여넣을 `reference_views` 항목을 찍어 줍니다.

### 4.1 🔴 「confirm을 돌렸는데 아무 일도 안 일어났다」의 세 원인

이 절이 이 문서에서 가장 자주 쓰일 자리입니다. `confirm --apply`는 **세 가지 이유로 거절**할 수 있고, 셋 다 조용한 실패가 아니라 **`REFUSED [<룰명>]:` 한 줄**로 이유를 말합니다. 그 줄을 읽으십시오.

| 원인 | 나오는 말 | 조치 |
|---|---|---|
| ① **`auto_confirm` 노브가 꺼져 있다** (기본값이 **OFF**입니다) | `rule '<룰>' has 'auto_confirm' off (default)` | `enrichment_rules.json`의 그 규칙에 `"auto_confirm": true`. 노브가 **사람의 동의 자리**라 우회로가 없습니다 |
| ② `--ignore-knob`과 `--apply`를 **같이** 줬다 | `--ignore-knob is a measurement-only flag and cannot be combined with --apply` | `--ignore-knob`은 **꺼진 규칙의 규모를 재는 용도**입니다(dry-run 전용). 쓰려면 ①을 하십시오 |
| ③ 어느 참조뷰에도 **`candidate_for` 선언이 없다** | `rule '<룰>' declares no 'candidate_for' on any reference view` | 어느 뷰 컬럼이 어느 타깃의 후보인지 **선언**하십시오. 컬럼 이름으로 유추하지 않습니다 → [config/enrichment_rules §7](./config/enrichment_rules.md) |

**그리고 네 번째 원인은 거절조차 아닙니다** — **애초에 이 도구가 아니었던 경우**입니다. 파생 행이 없으면 워크리스트가 비어 있고, `queue size : 0`으로 정상 종료합니다. 그때 필요한 것은 **ⓒ**입니다(§0 결정표).

---

## 5. ⚰️ ~~ⓔ graph_orphan_sweep~~ — **은퇴** (2026-08-14 `2ec78b9` · R-2026-08-14-H)

🔴 **ⓔ는 더 이상 소급 경로가 아닙니다 — 돌리지 마십시오.** 지울 대상(`graph_nodes`/`graph_edges`)이 은퇴하고 **DROP**됐습니다(약 841 MB).

- **어드민 API에서 «등록 해제»됐습니다.** `server/retroactive.py`의 `OPERATIONS`는 이제 `chain_replay`·`withdraw`·`enrichment_backfill`·`enrichment_confirm` **넷**입니다. `GET /admin/retroactive/operations`에 ⓔ 행이 없고, `POST /admin/retroactive/graph_orphans/run`은 미등재 연산으로 거절됩니다. 이 문서에서 **「다섯」이라 적힌 자리는 전부 「넷」으로 읽으십시오.**
- **스케줄 호출도 제거됐습니다**([AUTO_UPDATE_GUIDE §4-ter](./AUTO_UPDATE_GUIDE.md)) — 🔴 **그것은 정리가 아니라 필수였습니다**: `graph_orphans.run_scheduled`가 첫 동작으로 `ensure_graph_tables`를 불러 **DROP된 표를 되살렸을** 것입니다.
- **CLI와 런타임 모듈은 2026-08-16 트리에서 제거됐습니다.** 옛 설명과 설정 예시는 [archive](../_archive/retired_graph_sync/README.md)에만 남습니다.
- ⚠️ **§1의 「ⓔ만 페이지 커밋이 아니다」·§6.2·§6.3(종료 코드 3)·§7의 `--allow-production` 서술은 전부 이 연산에 대한 것이라 «함께 은퇴»합니다.** ⓐ~ⓓ에 대한 서술은 **한 줄도 영향받지 않았습니다.**

<details>
<summary>⚪ 이하 원문(역사 기록)</summary>

### ~~ⓔ graph_orphan_sweep — 유일하게 「지우는」 소급~~

```bash
conda run -n assy_manager python server/scripts/graph_orphan_sweep.py
conda run -n assy_manager python server/scripts/graph_orphan_sweep.py --label Wafer --label Core
conda run -n assy_manager python server/scripts/graph_orphan_sweep.py --limit-print 0
conda run -n assy_manager python server/scripts/graph_orphan_sweep.py --apply
conda run -n assy_manager python server/scripts/graph_orphan_sweep.py --apply --allow-production
conda run -n assy_manager python server/scripts/graph_orphan_sweep.py --max-fraction 1.0
conda run -n assy_manager python server/scripts/graph_orphan_sweep.py --min-population 10
conda run -n assy_manager python server/scripts/graph_orphan_sweep.py --ignore-rejected
```

**언제**: 매핑을 바꾼 **전후**로 돌려 어떤 정체성이 남는지 이름으로 봅니다.

**왜 필요한가**: 엣지 재교정은 **엣지만** 지우고 남은 노드를 지우는 코드가 없습니다. 그래서 라벨 폐기만의 문제가 아니라 **정체성을 바꾸는 셀 편집마다 노드가 하나씩 샙니다.**

🔴 **고아 판정은 두 조건 AND입니다** — ① 엣지가 0개이고 ② **현재 어떤 매핑도 그 정체성을 생산할 수 없다**. 엣지 0개만으로 지우면 정상적으로 엣지가 없는 DOE 어휘가 통째로 날아갑니다.

**이 도구의 요점은 삭제가 아니라 거절입니다.** 자세한 것은 [AUTO_UPDATE_GUIDE §4-ter](./AUTO_UPDATE_GUIDE.md)가 정본입니다(같은 모듈을 스케줄러가 하루 1회 자동으로도 돕니다). 운영자가 알아야 할 것만:

* **예산 관문** — 한 라벨이 인구의 `--max-fraction`(기본 **0.5**)을 넘게 잃으면 삭제가 아니라 **`DECLINED`**입니다. **매핑 오타는 은퇴한 라벨과 겉모습이 똑같기 때문입니다.** 정말 은퇴시킨 라벨이라면 `--max-fraction 1.0`으로 다시 돌리십시오.
* **작은 라벨 면제** — 인구가 `--min-population`(기본 **10**) 미만인 라벨은 비율 검사에서 빠집니다(3개짜리 라벨은 자기 자신의 100%입니다).
* **깨끗한 선언 전제** — 온톨로지 매핑이 하나라도 깨끗하게 로드되지 않으면 **스윕 전체를 거절**합니다. 이유를 **먼저 읽고** 나서만 `--ignore-rejected`를 쓰십시오.
* **격리 관문** — `--apply`를 격리 데이터 루트 밖에서 하려면 `--allow-production`이 필요합니다. dry-run은 읽기 전용이라 어디서나 됩니다.
* `--limit-print`는 **출력 줄 수**만 자릅니다. **삭제 범위와 무관합니다**(`0`이면 전부 출력).

</details>

---

## 6. 함정 모음

### 6.1 `--limit`은 도구마다 **뜻이 다릅니다**

같은 철자에 세 가지 의미가 있습니다. 이것을 모르면 dry-run 숫자를 오독합니다.

| 명령 | `--limit N`이 자르는 것 |
|---|---|
| `chain_replay_cli.py replay` / `replay-all` | **스캔한 소스 행 수** |
| `backfill_enrichment.py` | **새로 만들 파생 정체성 수**(스캔은 계속됩니다) |
| `enrichment_insights.py` (세 서브커맨드 전부) | **검사한 행 수** |
| `graph_orphan_sweep.py` | ⚠️ `--limit`이 **없습니다.** `--limit-print`는 출력 줄 수일 뿐 삭제 범위가 아닙니다 |
| `chain_replay_cli.py resolve` (ⓕ) | **훑은 행 수**(칸 수가 아닙니다 — 한 행에 여러 칸이 바뀔 수 있습니다). 보고서의 목록 절단은 별개이며 `--list-all`이 풉니다 |

⚠️ 그리고 `replay --limit N`은 **표본이 아닙니다** — `row_id` 순으로 앞에서 N행입니다. 연기 시험(smoke test)에는 맞지만, **「전체에서 몇 건이 바뀌나」의 답으로 읽으면 틀립니다.**

### 6.2 ⓔ만 「중간에 끊어도 된다」가 성립하지 않습니다

§1의 4번(페이지 단위 커밋)은 ⓐ~ⓓ에만 해당합니다. **고아 스윕은 청크로 나눠 지우지만 커밋은 맨 끝에 한 번**입니다(`graph_orphans.apply_sweep`). 중간에 끊으면 그 실행분은 통째로 롤백됩니다 — 손상은 없지만 **이어서 가지 못하고 처음부터입니다.**

### 6.3 ⓔ의 종료 코드 `3`을 실패로 읽지 마십시오 (그리고 성공으로도 읽지 마십시오)

| 코드 | 뜻 |
|---|---|
| `0` | 할 일이 없었거나, 계획한 것을 전부 보고/적용했다 |
| `2` | **거부** — 격리 밖인데 `--apply`를 요구했다 |
| `3` | 무언가가 **`DECLINED`**됐거나 선언이 깨끗하지 않다. **통과한 라벨을 적용한 뒤에도 3입니다** — 「작업이 미완이다」는 운영자가 놓치면 안 되는 상태이기 때문입니다 |

**dry-run도 `DECLINED`가 있으면 3을 냅니다.** 자동화에서 「0이 아니면 장애」로 처리하면 정상적인 예산 거절이 알람이 됩니다.

### 6.4 `reapply_chain.py`는 **삭제됐습니다** (2026-07-31 `8f8be4b`)

옛 문서·옛 메모에서 이 이름을 보면 **따르지 마십시오.** R1과 같은 일을 하면서 `source_name="reapply_chain"`으로 썼는데, 그 이름은 `SOURCE_PRIORITY`에 없어 **99(최하위)**로 떨어졌습니다. **맞는 값을 쓰고도 다른 아무 소스에나 지는** 문이었습니다. 지금 그 자리는 **ⓐ R1**입니다.

### 6.5 ⓒ의 「이미 있는 파생 정체성」 읽기는 **두 갈래**입니다 (2026-07-31 `1948338`)

CLI로 돌리는 **완전한** 백필은 「새로운가」를 **파생 테이블 전체에 대해** 판정해야 하므로, 스캔 전에 기존 정체성을 통째로 읽어 둡니다(`derived '<테이블>': N existing identities loaded` 한 줄이 그것입니다). 어드민 **미리보기**(§7.2, `scan_limit`이 있을 때)는 그 읽기를 하지 않고 **표본이 실제로 만난 키만** 인덱스로 되물어봅니다(`bounded mode — existing identities resolved per chunk (no full read)`).

🔴 **하나로 합칠 수 없는 이유가 있습니다.** 전량 읽기는 **스캔 시작 전의 스냅샷**이라 실행 도중 자기가 만든 키를 계속 「새 것」으로 봅니다 — `--apply`가 청크마다 커밋하므로, 순진하게 되물어보면 **자기가 방금 쓴 것을 읽고** 뒤 청크의 보강을 조용히 버립니다. 그래서 되물어보는 쪽은 **없다는 답까지 기억해** 같은 성질을 재현합니다. **CLI의 의미론은 하나도 바뀌지 않았습니다.**

### 6.6 ⓑ R2의 카운트에는 **인덱스가 필요합니다** (2026-07-31 `1948338`)

「이 소스가 이 테이블에서 주장하는 셀은 몇 개인가」는 `cell_sources`를 `(table_name, source_name)`으로 좁히는 질문입니다. 그 술어를 받는 인덱스는 **`idx_sources_by_source`(`table_name, source_name, column_name, row_id`) 하나**입니다 — 기존 `idx_sources_lookup_source`는 `source_name`이 **마지막 키**라 이 술어에 쓸 수 없습니다.

- **없으면 이 카운트가 `cell_sources` 전량 스캔이 되고, 그 비용이 요청 경로에 앉습니다**(§7의 `count` 라우트). 실측 근거(행 수·소요·버퍼·플래너 판정)는 `server/database/models.py`의 `idx_sources_by_source` 주석과 `server/scripts/setup_db_performance.py` Step 3.10에 **기록돼 있습니다** — 여기 사본을 만들지 않습니다.
- **반영 경로는 하나입니다**: `conda run -n assy_manager python server/scripts/setup_db_performance.py`(Step 3.10). `create_all`은 **이미 있는 테이블에 인덱스를 추가하지 않으므로**, `models.py` 선언만으로는 기존 운영 DB에 생기지 않습니다.
- 스크립트가 만든 뒤 **플래너가 실제로 그것을 골랐는지까지 검사**합니다(Step 3.11). 표가 작으면(`WITHDRAW_PLAN_MIN_ROWS` 미만) **실패가 아니라 `NOT VERIFIED`**를 찍습니다 — 작은 표에서 Seq Scan은 옳은 계획이고, 거기서 우는 검사는 운영자가 검사를 무시하게 만듭니다.
- 운영 관점 전문은 [POSTGRES_OPERATIONS §3.1](./POSTGRES_OPERATIONS_GUIDE.md).

---

## 7. 어드민 API로도 됩니다(**ⓐ~ⓔ만**) — **화면은 아직 없습니다** (2026-07-31 `fbc1053`)

ⓐ~ⓓ에 **건수 조회 라우트와 실행 라우트**가 있습니다. 현재 목록의 정본은 `GET /admin/retroactive/operations` 응답입니다.

> ⚠️ **ⓕ(R3 `resolve`)는 이 표면에 없습니다** — 등록부 `server/retroactive.py`의 `OPERATIONS`는 `chain_replay`·`withdraw`·`enrichment_backfill`·`enrichment_confirm`입니다. **CLI 전용**이고, `GET /admin/retroactive/operations`의 목록에 안 나오는 것이 정상입니다.

> ⚠️ **이 문장은 곧 낡습니다** — 화면 작업이 별도 레인에서 **진행 중**입니다. 인용하기 전에 `client2/src`에서 `retroactive`를 grep해 확인하십시오. 착지하면 **§7 서두 · §7.4 · §0 결정표 아래 안내**를 함께 고쳐야 합니다.

| 라우트 | 하는 일 |
|---|---|
| `GET /admin/retroactive/operations` | 등재된 연산(ⓐ~ⓔ)의 목록·파라미터·**대응 CLI**·CLI에만 있는 기능 |
| `GET /admin/retroactive/{op}/count` | 「몇 건인가」 — 쓰기 없음 |
| `POST /admin/retroactive/{op}/run` | 실행을 **큐에 넣고 즉시 반환**(실제 실행은 스케줄러) |

```bash
curl -H "X-Admin-Token: $ASSY_ADMIN_TOKEN" http://127.0.0.1:8080/admin/retroactive/operations
curl -H "X-Admin-Token: $ASSY_ADMIN_TOKEN" "http://127.0.0.1:8080/admin/retroactive/withdraw/count?table=bonding_map&source=chain_ingestion"
curl -X POST -H "X-Admin-Token: $ASSY_ADMIN_TOKEN" -H "Content-Type: application/json" \
     -d '{"params": {"table": "bonding_map", "source": "chain_ingestion"}}' \
     http://127.0.0.1:8080/admin/retroactive/withdraw/run
```

### 7.1 CLI가 없어진 것이 아닙니다 — 버튼은 **흔한 형태**만 덮습니다

라우트는 각 연산의 **파라미터 필수분**만 받습니다. 나머지는 CLI에 남아 있고, 그 목록을 `operations` 응답의 **`cli_only`**가 직접 들고 있습니다 — `replay-all` · `--limit` · `--chunk-size` · `--force-disabled` · `--ignore-knob` · `classify`/`propose`.

🔴 **`--allow-production`은 CLI에만 있고, 그 사실이 중요합니다.** 격리 관문(§5)은 `scripts/graph_orphan_sweep.py` 안에 있지 `graph_orphans.run_scheduled` 안에 있지 않습니다. 어드민 버튼과 **매일 도는 스케줄러가 부르는 것은 후자**이므로, 이 라우트는 데몬이 이미 하고 있는 것 이상의 권한을 주지 않습니다 — 다만 **CLI가 묻는 확인을 재현하지도 않습니다.** CLI를 아는 운영자는 물어볼 것을 기대합니다.

### 7.2 카운트는 **어떤 종류의 수인지 함께 말합니다**

「몇 건인가」는 연산에 따라 **드라이런 그 자체**(테이블 전수 + 매퍼)라 요청 경로에 앉을 수 없습니다. 그래서 응답은 수 하나가 아니라 **수 + 그 수의 종류(`count_kind`)**입니다.

| `count_kind` | 뜻 | 함께 오는 것 |
|---|---|---|
| `exact` | 값싼 질의가 전부를 답했다 | — |
| `sample` | 앞에서 `scan_limit`행까지만 봤다 | `scanned` · `truncated` |
| `upper_bound` | 값싼 질의가 **상위집합**을 답했다 | `extra.why_upper_bound`(부족분을 **말로**) |

🔴 **`sample`의 수는 테이블에 대한 수가 아니라 표본에 대한 수입니다.** 응답의 `detail` 문장이 그렇게 말하도록 서버가 씁니다 — 그 문장을 그대로 읽으십시오.
🔴 **`upper_bound`를 「이만큼 바뀐다」로 읽지 마십시오.** ⓑ R2에서 그 수는 「이 소스가 주장하는 셀 − 사람이 핀한 셀」이고, **실제로 표시값이 바뀌는 셀은 그보다 적습니다**(아래 층에 같은 값이 있으면 화면은 그대로입니다).

⚠️ **`scan_limit`은 §6.1의 어떤 `--limit`도 아닙니다** — **미리보기의 예산**입니다(기본 200 / 최대 2000). 행을 실제로 훑지 않은 연산은 응답의 `scan_limit`이 **`null`**로 옵니다: 하지 않은 표본을 했다고 말하지 않기 위해서입니다.

### 7.3 실행은 **즉시 반환**이고, 결과는 그 응답에 없습니다

`run`은 아웃박스에 한 줄 쓰고 `{"status": "queued", "run_id": …}`를 돌려줍니다. 진행과 결과는 **auto-update 스케줄러 로그**(`[Retroactive] run_id=…`)에 있습니다. `POST /admin/auto-update/run-now`와 같은 형태입니다.

- **동시 1건입니다.** 실행 중에 또 요청하면 조용히 줄 세우지 않고 **거절 + 로그**하며, 아웃박스 행은 미처리로 남아 다음 틱이 집습니다.
- **토큰이 설정돼 있지 않으면 이 라우트만 503입니다**(조회 라우트 둘은 열립니다). 코드 실행 라우트와 같은 취급인데, 코드 실행이라서가 아니라 **테이블 전체 재작성·소스 회수·노드 삭제**라는 피해 계급이 같기 때문입니다.
- **사람 값 보호는 라우트가 아니라 연산 안에 있습니다**(§2.4) — 어드민을 거쳐도 우회되지 않습니다.

### 7.4 아직 없는 것 (`77d27d3` 기준)

- **어드민 화면의 버튼**(위 API를 그리는 클라 코드) — **별도 레인에서 진행 중**입니다. 착지하면 §7 서두·이 절·§0 결정표 아래 안내를 함께 고쳐야 합니다.
- **실행 이력 화면**도 없습니다. 완료 여부와 결과는 **스케줄러 로그**에서만 읽습니다.
- 진행 상황은 [보드](../process/PROJECT_STATUS.md)를 보십시오.
