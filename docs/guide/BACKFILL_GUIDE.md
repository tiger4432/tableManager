# 🔁 소급 적용 가이드 — 규칙을 「이미 쌓인 데이터」에 적용하는 다섯 가지 길

> **Status:** 🟢 Living | **작성:** 2026-07-31 · doc-keeper | **Last-verified:** 2026-07-31 (신설. 다섯 진입점의 argparse를 **소스 대조 + `--help` 실행**으로 전수 확인 — `server/scripts/chain_replay_cli.py` · `backfill_enrichment.py` · `enrichment_insights.py` · `graph_orphan_sweep.py`, 그리고 의미론은 `server/chain_replay.py` · `server/enrichment_analysis.py` · `server/enrichment_candidates.py` · `server/graph_orphans.py` · `server/keyset_scan.py` · `crud.SOURCE_PRIORITY`/`apply_batch_updates`)
> **대상:** 규칙을 바꿔 놓고 **「과거 데이터는 왜 그대로지?」**를 만난 운영자.
> **먼저 알아야 할 것:** 이 시스템의 규칙은 **증분(outbox) 구동**이다. 규칙은 **자기가 선언된 이후에 바뀐 행만** 본다. 규칙을 고쳐도 과거는 옛 규칙이 남긴 상태 그대로 있고, 그것을 움직이는 유일한 방법이 이 문서의 다섯 경로다.
> **관련:** 개발자 계약은 [chain_ingestion_guide §5](./chain_ingestion_guide.md) · 인리치먼트 선언은 [config/enrichment_rules §7](./config/enrichment_rules.md) · 고아 스윕의 정본은 [AUTO_UPDATE_GUIDE §4-ter](./AUTO_UPDATE_GUIDE.md)

---

## 0. 30초 — 어느 것을 써야 하나

**증상에서 출발하십시오.** 도구 이름에서 출발하면 ⓒ와 ⓓ를 반드시 헷갈립니다.

| 지금 보이는 것 | 써야 할 것 |
|---|---|
| 체인 룰을 새로 만들었거나 고쳤는데 **옛날 행에는 반영이 안 됐다** | **ⓐ R1** `chain_replay_cli.py replay <룰>` |
| 옛 룰이 만든 **틀린 값이 아직 이기고 있다**. 룰을 고쳐 재적용해도 그 칸은 안 바뀐다 | **ⓑ R2** `chain_replay_cli.py withdraw <테이블> <소스>` |
| 파생 테이블에 **행 자체가 없다**. 워크리스트에도 안 뜬다 | **ⓒ** `backfill_enrichment.py <룰>` |
| 파생 **행은 있는데** 타깃 칸이 **비어 있다**. 워크리스트에는 떠 있다 | **ⓓ** `enrichment_insights.py confirm <룰>` |
| 매핑을 바꿨더니 그래프에 **아무 데도 안 붙은 노드**가 남았다 | **ⓔ** `graph_orphan_sweep.py` |

🔴 **ⓒ와 ⓓ를 가르는 질문은 하나입니다 — 「파생 테이블에 그 행이 있습니까?」**
`ⓒ`는 **없던 파생 행을 만듭니다.** `ⓓ`는 **이미 있는 행의 빈 칸을 채웁니다.**
잘못 고르면 **에러 없이 아무 일도 안 일어나고**, 운영자는 기능이 고장 났다고 결론짓습니다. 실제로 그렇게 한 번 잃었습니다.

> ⓔ만 성격이 다릅니다. ⓐ~ⓓ가 **만들거나 고치는** 소급이라면 **ⓔ는 지우는 소급**입니다. §5에서 따로 다룹니다.

---

## 1. 다섯이 공유하는 규율 — 한 번만 말합니다

이 넷은 다섯 경로 **모두**에 해당합니다. 개별 절에서 반복하지 않습니다.

1. **기본은 dry-run입니다.** 아무 플래그 없이 돌리면 **읽기만** 합니다. 먼저 돌려서 보고서를 읽는 것이 정상 절차입니다.
2. **`--apply`만이 씁니다.** 쓰기를 시작하는 스위치는 이것 하나뿐이고, 다른 이름의 우회로는 없습니다.
3. **진짜 매퍼와 진짜 쓰기 경로를 씁니다.** 소급 전용 구현이 따로 없습니다 — 매퍼 산출물은 그대로 쓰고 provenance만 찍으며, 쓰기는 라이브와 같은 `crud.apply_batch_updates`를 지납니다. **그래서 소급 결과와 라이브 결과가 갈리지 않습니다.**
4. **페이지 단위로 커밋합니다.** 대량 실행을 중간에 끊어도 되고, 다시 돌리면 이미 처리된 것을 다시 진단해 이어서 갑니다.
   ⚠️ **ⓔ는 예외입니다** — §6.2를 보십시오.

### 1.1 무엇이 어떤 이름으로 쓰이는가 (레이어링)

표시값은 **소스 우선순위**로 결정됩니다(숫자가 낮을수록 이깁니다). 소급이 사람 값을 밀어내지 못하는 근거가 여기 있습니다.

| 경로 | 쓰기 소스명 | 우선순위 |
|---|---|---|
| ⓐ R1 | `chain_ingestion` — **라이브 워커와 같은 이름** | 4 |
| ⓑ R2 | (셀 소스를 **쓰지 않고 지웁니다**. 감사 기록만 `chain_replay_withdraw`) | — |
| ⓒ backfill | `enrichment_backfill` | 미등재 → **99** |
| ⓓ confirm | `enrichment_auto_confirm` | 미등재 → **99** |
| ⓔ 고아 스윕 | (셀이 아니라 **그래프 노드**를 지웁니다) | — |

`SOURCE_PRIORITY`의 실제 값은 `user: 0` · `collision_merge: 1` · `pipeline_parser: 2` · `custom_script: 3` · `chain_ingestion: 4`이고, **등재되지 않은 이름은 전부 99**입니다.

🔴 **`user`(0)가 사람이 직접 입력한 유일한 레이어입니다.** ⓐ는 4로, ⓒ·ⓓ는 99로 쓰므로 **어느 것도 사람 값을 표시에서 밀어내지 못합니다.** R1에 사람 값 특례 코드가 없는 이유가 이것입니다 — 레이어링이 이미 처리합니다.

> ⚠️ `table_config.json`의 테이블별 `source_priority`로 서열을 커스텀한 테이블에서는 위 숫자가 그 테이블의 맵으로 대체됩니다(`crud.resolve_priority_map`). 미등재 → 99 규칙은 어느 맵에서든 같습니다.

---

## 2. ⓐⓑ 체인 리플레이 — CLI 하나, 연산 둘

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

### 2.2 왜 두 연산인가 — 가르는 문장 하나

> **「이 룰이 여기서 더는 값을 만들지 않는다」와 「값이 비었다」는 다른 진술이고, 앞엣것을 표현할 수 있는 것은 R2뿐입니다.**

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

### 2.4 사람 값은 이 문서의 어느 경로로도 지워지지 않습니다

R2의 **거절 두 개**가 그 보장의 전부입니다.

| 거절 | 이유 |
|---|---|
| `withdraw <테이블> user` | 사람이 입력한 값입니다. 도구가 지우지 않습니다 — **셀을 편집하십시오.** 명령이 아예 거부됩니다 |
| 그 소스를 사람이 **핀**한 셀(`manual_priority_source`) | 핀은 「이 소스를 보여 달라」는 사람의 선택입니다. 조용히 철회하면 그 선택을 뒤집습니다 → `pinned_skipped`로 세고 이유를 남기며 **건너뜁니다** |

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
conda run -n assy_manager python server/scripts/enrichment_insights.py classify <룰> --probe-limit 200
conda run -n assy_manager python server/scripts/enrichment_insights.py propose  <룰> --min-support 3
```

* `classify` — 워크리스트의 결손을 원인별로 분류합니다(**파이프라인 버그** / 기계적으로 해결 가능 / **진짜 사람 일**). 「이 워크리스트 중 사람이 꼭 봐야 하는 건 몇 건인가」에 답합니다.
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

## 5. ⓔ graph_orphan_sweep — 유일하게 「지우는」 소급

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

---

## 7. 아직 없는 것 (열린 항목)

**어드민 화면에는 이 다섯을 실행할 자리가 아직 없습니다.** 현재 소급 실행 경로는 **CLI뿐**입니다.

소급 항목별 건수 표시 + 실행 버튼을 어드민에 올리는 작업이 **별도 레인에서 진행 중**입니다. 착지 시점·최종 형태는 정해지지 않았으므로 **이 문서는 그것을 약속하지 않습니다.** 진행 상황은 [보드](../process/PROJECT_STATUS.md)를 보십시오. 착지하면 이 절과 §0 결정표를 함께 고쳐야 합니다.
