# 🔁 소급 적용 가이드 — 규칙을 「이미 쌓인 데이터」에 적용하는 길들

> **Status:** 🟢 Living | **작성:** 2026-07-31 · doc-keeper | **Last-verified:** 2026-09-16 (§2.1 「이 행들만」 — `--row-ids`/`row_ids` 가 `business_keys` «옆»에 생겼고 둘 다 주면 거절 — S-254 `fe2d0c6c` · 그리드 배너는 «row_id 로» 보내고 없는 행을 이름 대며 큰 선택은 크기를 말한다 — C-112·C-113·C-114) · 직전 2026-09-15 «후속» (§1.1 — 빈 칸은 서열에 안 낀다, 판정 405 · 쌓인 NULL 층 세기 S-243-b) · 직전 2026-09-15 (§0·§2.1 — 선언된 join 은 «왼쪽 규칙»에 ⓐ R1, 보고는 «행», 오른쪽 이름은 거절 — S-242 `bd0a3db7`) · 직전 2026-09-02 (§7.6 페이싱 — `pace` 를 든 연산이 **하나에서 둘로**(`chain_replay` 합류), 읽는 쪽은 **둘에서 셋으로**, 모르는 이름의 갈림은 「둘이 다르다」가 아니라 **2 대 1**) · 직전 2026-08-31
>
> **이번 라운드 (2026-08-31 · 정비 사이클 — 🔴 «화면이 생겼습니다». 그리고 등록부에 원장 연산 둘이 들어왔습니다)**
> - 🔴 **§7 제목의 「화면은 아직 없습니다」가 «거짓이 됐습니다».** 어드민에 소급 화면이 있고(09-25 부터 **Retroactive** 탭), **도는 실행 목록 + 취소 버튼**까지 있습니다. §7.4 의 「아직 없는 것」 둘 중 **둘 다** 착지했습니다.
> - 🔴 **등록부가 넷에서 «여섯»이 됐습니다** — 원장 쪽 둘이 들어왔습니다: **ⓖ `ledger_backfill`**(선언된 소스에서 아직 원장에 없는 행을 번역한다)과 **ⓗ `ledger_rescope`**(**범위를 정해 회수 + 재생성** — 해석을 고친 뒤 «일부만» 다시 만드는 길). §0 결정표에 행 둘이 늘었습니다.
> - 🔴 **취소가 생겼고 «협조적»입니다** — 프로세스를 죽이지 않고 실행 행에 값을 세우며, 도는 쪽이 **배치 사이에서** 그것을 묻습니다. **연산마다 「멈출 수 있나」가 선언되고, 09-25 `3bf01b96` 부터 일곱 다 `true` 입니다**(종전 `false` 둘의 사유는 §7.5 의 기록). 화면은 그 값이 거짓이면 **버튼을 안 그립니다.**
> - 🆕 **`pace` 파라미터를 든 연산이 «둘»** — ⓐ `chain_replay`(R1, 2026-09-02 합류) · ⓖ `ledger_backfill`. 값이 닫혀 있어 화면이 텍스트칸이 아니라 **선택지**를 그립니다(`fast`/`slow`/`trickle`, 각 「언제 쓰나」와 함께). 목적은 **긴 작업이 도는 동안 옆 질의를 굶기지 않는 것**입니다(§7.6). CLI 는 양쪽 다 `--pace`.
> - ⚰️ ~~ⓕ(R3 `resolve`)는 «여전히» 이 표면에 없습니다~~ — 09-25 `3321158b2` 로 거짓이 됐습니다. `resolve` 는 등록부 연산입니다(§0 · §7).
> - ⚰️ **§7.1 의 `--allow-production`·격리 관문 문단은 «없어진 파일»을 서술합니다**(§7.1 안의 배너 참조).
>
> **직전 라운드 (2026-08-14 · `2ec78b9` · R-2026-08-14-H — ⓔ가 «없어졌습니다»)**
> - ⚰️ **ⓔ 그래프 고아 스윕 은퇴** — 지울 대상(`graph_nodes`/`graph_edges`/`graph_sync_state`)이 **DROP**됐습니다(약 841 MB). `server/admin/retroactive.py`의 `OPERATIONS`가 다섯에서 **넷**(`chain_replay`·`withdraw`·`enrichment_backfill`·`enrichment_confirm`)이 되어 어드민 API에서도 **등록 해제**됐고, 스케줄러의 자동 호출도 제거됐습니다.
> - 🔴 **이 문서에서 「다섯」이라 적힌 자리는 전부 「넷」으로 읽으십시오** — §5 · §6.2 · §6.3 · §7의 ⓔ 관련 서술은 접혀 있습니다. **ⓐ~ⓓ와 ⓕ는 한 줄도 영향받지 않았습니다.**
>
> **직전 라운드 (2026-08-11 2차 · `ffb23d6`+`53f9187` — ⓕ와 ⓑ가 더 이상 하류 체인을 깨우지 않습니다)**
> - 🔴 **§2.3에 ⓑ(철회)의 같은 수리를 실었습니다**(`53f9187`). **이쪽이 더 급했습니다 — 철회는 어드민 화면의 버튼에서도 돌아갑니다.** 지워지는 층은 한 줄도 달라지지 않았고(살아남은 층 집합이 바이트 단위로 동일), `user` 거절과 사람 핀 건너뛰기는 **CLI·버튼 양쪽에서** 그대로입니다.
> - 🔴 **화면 알림 4건 → 0건은 잃은 것이 아닙니다** — 그 4건은 아무도 철회하지 않은 다른 테이블의 알림이었고, **값이 바뀐 칸은 전에도 지금도 알림이 안 갑니다.** 확인하는 자리는 셀 이력 타임라인이고 변하지 않았습니다.
> - ✅ **ⓐ(재적용)도 실행당 tx 하나입니다**(d62f40730). 소급 잡 하나가 낸 이벤트는 모두 `run_id` 를 실어 체인 대기열에 한 줄로 뜹니다(총괄 b3a4334db).
> - 🔴 **§2.5에 운영자용 사실 셋 추가.** ⓕ가 내는 내부 이벤트가 **사람이 그리드에서 친 것과 똑같은 라벨**을 달고 있어서, 칸 하나를 고치면 그 테이블에 걸린 파생 규칙이 전부 돌았습니다. 지금은 **명시적으로 선언한 규칙만** 반응하고, 대량 실행이 실행당 그룹 하나로 접혀 훨씬 빨라졌습니다(종전에는 수리 행마다 직렬 그룹 — 1만 행이 한 시간을 넘겼고 그동안 정상 인제션이 뒤에 줄을 섰습니다).
> - ⚠️ **`ffb23d6`(ⓕ) / `53f9187`(ⓑ) 이전에 그 명령을 `--apply`로 돌린 적이 있으면 딸려 들어간 파생 쓰기가 있을 수 있습니다** — 그 시각의 체인 워커 로그로 확인하십시오.
>
> **직전 라운드 (2026-08-11 · 해결 순서 수리 + R3 착지)**
> - **신규 경로 ⓕ — R3 `chain_replay_cli.py resolve`**(§2.5). 같은 CLI의 **세 번째 연산**이라 **스크립트 수는 그대로 넷**이고, 결정표·§1의 공통 규율에 행이 하나 늘었습니다.
> - 🔴 **제목의 「다섯 가지 길」을 여섯으로 고치지 않고 기수를 지웠습니다** — 목록 옆의 수는 목록의 두 번째 사본이고, 이 문서에서 그 수는 **§0 결정표·§1 서두·§7 서두** 세 자리에 사본이 있었습니다. 목록이 정본입니다.
> - ⚰️ **ⓕ만 어드민 API에 없습니다** (09-25 `3321158b2` 로 거짓 — `resolve` 가 등록부 연산이 됐습니다) — `server/admin/retroactive.py`의 `OPERATIONS`는 ~~`chain_replay`·`withdraw`·`enrichment_backfill`·`enrichment_confirm`·`graph_orphans` **다섯**~~이고 R3는 등재돼 있지 않습니다(실측). §0과 §7의 「전부 어드민 API로도 됩니다」는 **ⓐ~ⓔ에 대해서만** 참입니다. → ⚠️ **[2026-08-18 정정] 지금은 `graph_orphans`가 빠져 «넷»입니다**(§5 참조). 이 줄의 「다섯」은 2026-08-11 시점의 실측이고, **현재 수는 §5가 정본**입니다.
> - **§1.1 레이어링 표 갱신** — 표시값 결정이 **등재 우선순위 → `ingested_at` 내림차순 → `source_name` 오름차순**의 전순서가 됐습니다. 종전에는 미등재 이름이 전부 99로 **동점**이었고 승자가 삽입 순서로 떨어졌습니다(ⓒ·ⓓ가 둘 다 99인 것은 그대로이며, 이제 그 둘 사이도 결정적으로 갈립니다).
> - **§6.1 갱신** — `--limit`의 뜻 표에 ⓕ 행 추가(**훑는 행 수** 상한).
>
> **직전 라운드 (2026-07-31 · `fbc1053`·`1948338`·`9c6a1c9`)**
> - **§7 재작성 — 어드민 API가 착지했습니다**(라우트 3개). 🔴 **화면(버튼)은 아직 없습니다** — 「어드민 화면에는 자리가 없다」는 종전 문장은 절반만 참이 됐습니다. 지금 쓰려면 `curl`입니다.
> - **§7.2 신설 — 카운트는 「어떤 종류의 수인지」를 함께 답합니다**(`exact`/`sample`/`upper_bound`). 다섯 중 넷은 요청 경로에서 정확할 수 없고, **어느 것도 정확하다고 주장하지 않습니다.**
> - **§3에 각주 — ⓒ의 구현이 `server/chain/enrichment/backfill.py`로 옮겨졌습니다**(`9c6a1c9`). **CLI 경로·진입점·플래그는 그대로**라 이 문서가 찍는 명령은 전부 그대로 동작합니다.
> - **§6.5·§6.6 신설** — ⓒ의 「이미 있는 정체성」 읽기가 **두 갈래**가 됐고(CLI는 전량 스냅샷, 미리보기는 표본 키만 되물음), **ⓑ R2의 카운트가 인덱스를 얻었습니다**(`1948338`). 새 DB에 반영하는 경로는 `ops_setup_db_performance.py` 하나입니다.
>
> (신설 근거: 진입점 전부의 argparse를 **소스 대조 + `--help` 실행**으로 전수 확인 — `server/scripts/chain_replay_cli.py` · `backfill_enrichment.py` · `enrichment_insights.py` · `graph_orphan_sweep.py`, 그리고 의미론은 `server/chain/replay.py` · `server/chain/enrichment/analysis.py` · `server/chain/enrichment/candidates.py` · `server/graph_orphans.py` · `server/keyset_scan.py` · `crud.SOURCE_PRIORITY`/`apply_batch_updates`)
> **대상:** 규칙을 바꿔 놓고 **「과거 데이터는 왜 그대로지?」**를 만난 운영자.
> **먼저 알아야 할 것:** 이 시스템의 규칙은 **증분(outbox) 구동**이다. 규칙은 **자기가 선언된 이후에 바뀐 행만** 본다. 규칙을 고쳐도 과거는 옛 규칙이 남긴 상태 그대로 있고, 그것을 움직이는 유일한 방법이 이 문서의 경로들이다. ⓕ가 그 원리의 가장 순수한 사례다 — **해결 규칙 자체를 고쳐도** 이미 확정된 표시값은 그대로 남는다.
> **관련:** 개발자 계약은 [chain_ingestion_guide §5](./chain_ingestion_guide.md) · 인리치먼트 선언은 [config/enrichment_rules §7](./config/enrichment_rules.md). 제거된 그래프 고아 스윕의 배경은 [archive](../_archive/retired_graph_sync/README.md)에만 남깁니다.

---

## 0. 30초 — 어느 것을 써야 하나

**증상에서 출발하십시오.** 도구 이름에서 출발하면 ⓒ와 ⓓ를 반드시 헷갈립니다.

| 지금 보이는 것 | 써야 할 것 |
|---|---|
| 체인 룰을 새로 만들었거나 고쳤는데 **옛날 행에는 반영이 안 됐다** | **ⓐ R1** `chain_replay_cli.py replay <룰>` |
| 🆕 **선언된 join**(`derive: {kind: join}`)을 켰거나 고쳤는데 옛날 행의 `into` 칸이 비어 있다 | **ⓐ R1** — 🔴 **«선언» 이름으로**(원천 `on.table` 을 트리거하는 쪽 — 09-25 `244d825dc` 부터. 전엔 「왼쪽」이었다). 짝 `<선언>:target` 을 통째로 돌리면 «이름 대고 거절»된다 — 선언 이름이 이미 하는 일을 다시 하는 것이라(행을 골랐으면 돈다). 드라이런·사전 계수는 셀이 아니라 **「다시 계산할 행」**을 말하고, 던진 페이지는 그 페이지만 잃는다(`pages_failed`) — 2026-09-15 S-242 |
| 옛 룰이 만든 **틀린 값이 아직 이기고 있다**. 룰을 고쳐 재적용해도 그 칸은 안 바뀐다 | **ⓑ R2** `chain_replay_cli.py withdraw <테이블> <소스>` |
| 파생 테이블에 **행 자체가 없다**. 워크리스트에도 안 뜬다 | **ⓒ** `backfill_enrichment.py <룰>` |
| 파생 **행은 있는데** 타깃 칸이 **비어 있다**. 워크리스트에는 떠 있다 | **ⓓ** `enrichment_insights.py confirm <룰>` |
| ~~매핑을 바꿨더니 그래프에 **아무 데도 안 붙은 노드**가 남았다~~ | ⚰️ **[2026-08-14] ⓔ 은퇴** — 그래프 저장소가 DROP돼 이 증상이 존재하지 않습니다(§5) |
| 칸에 **여러 소스가 쌓여 있는데 옛 층이 표시되고 있다**. 소스 목록을 열면 새 값이 **저장은 돼 있다** | **ⓕ R3** `chain_replay_cli.py resolve <테이블>` |
| **원장**에 이 소스의 원자가 없거나 도중에 멈춰 있다. 새 소스를 선언했는데 아무것도 안 걸린다 | **ⓖ** `python -m ledger.backfill --source <소스>` — 아직 원장에 없는 행(행 색인에 이름이 없는 행)을 번역한다. 🆕 10-04 `a9f877ed3` «그 소스만» 번역한다(전: 같은 표를 읽는 소스 «전부»가 그 행을 거두지 않고 한 번 더 썼고, 선언이 바뀐 뒤면 같은 사실이 둘로 남았다 — 이미 쌓인 것은 RUN.md 같은 절의 SQL 로 소스마다 세고 그 소스를 `--whole-source` 미리보기 → `--apply`). ⚰️ `--via-events` 는 은퇴 — 같은 일이라 이름 대어 거절된다(09-25 `a36ec7d3`: 「--via-events is the same job as the ledger backfill; run without it」) |
| 원장 **해석을 고쳤는데** 이미 적재된 원자는 옛 해석 그대로다. 전부 다시 돌리기는 너무 크다 | **ⓗ** 같은 명령에 `--scope-column <컬럼> --scope-values a,b,c` — **그 범위만 회수 + 재생성**. 🔴 **`--apply` 를 안 붙이면 드라이런이고 한 줄도 안 씁니다**. 🆕 소스 «전부»를 다시 만들려면 `--whole-source --apply`(가지를 합친 뒤 · 가지를 새로 고칠 때 — 페이지마다 제 범위, 10-01 `070a4558b`). 🆕 끝에 **표가 잃은 행의 원자도 거둡니다**(가지에도 — 가지엔 삭제 후속이 없다. 기본 세상은 후속이 놓친 삭제를 여기서 잡고, 보통 0). `--apply` 없이 `--whole-source` 를 돌리면 **표의 행 수 · 표가 잃은 행 수 · 그 원자 수**를 답합니다 — 재번역은 미리 안 보여 줍니다(그것이 곧 작업 전부라서). 소급 탭 작업 칸의 미리보기도 같은 수 (10-01 `fa41a6f25`). 가지에 대해 돌리려면 `--world <가지>`(없으면 기본 세상; 경로를 받던 `--ontology-root` 는 09-30 은퇴). 소급 탭 작업 칸도 같은 `whole_source` · `world`. 🆕 ⏱ 다시 만들기는 번역을 «두 번» 합니다 — 거둘 원자를 겨냥하는 미리보기 번역과 쓰기 번역(판정 166). 시간 어림은 «번역 × 2 + 읽기 + 거둠 · 쓰기 · 커밋»: 박스 `die_inspection` 1,000 행당 5.85 s ≈ 번역 2.16 s × 2 + 읽기 0.26 s + 1.25 s(데몬이 같이 돌던 박스 · 찬 원장, 10-02 `7d23eb172`) |
| 🆕 표 하나를 **통째로 다시 지어야** 한다 — 행 · 그 표의 칸 층 · 덮어쓰기 · 그 표를 읽는 원장 원자까지 | `python server/scripts/empty_table.py <표>`(**보고만** — 행 · 칸 층 · 그중 사람 층 · 덮어쓰기 · 원장 소스별 원자 · 그 표를 트리거로 읽는 규칙) → `--apply --confirm-rows <보고의 행 수>`(10-02 `81ffa8499`). 행 수가 그 사이 바뀌었으면 거절, 보기(`kind: view`)는 거절. 행 · 층 · 덮어쓰기를 한 트랜잭션에 지우고 감사 로그 요약 한 줄 — 🔴 **사람 층도 같이 지운다** · 아웃박스 이벤트를 안 내 **체인 규칙은 아무것도 안 깬다**. 그 뒤 그 표를 읽는 원장 소스마다 `--whole-source` 다시 읽기로 원자를 거둔다(기본 세상만 — 가지는 그 가지에서 `--whole-source --apply --world <가지>`). 거둠이 도중에 멈추면 `python -m ledger.backfill --source <소스> --whole-source --apply` 를 다시 |
| 🆕 **원장이 못 본 수정**이 있는지, 몇 행인지 알고 싶다 — 표 값이 바뀌었는데 원자가 옛 값 그대로 | `python -m ledger census --source <소스>` → 「… · 차이 X · 새 행 N · 수정 누락 D · 지워진 행 G · 지문 없음 U」(10-03 `6b698fe2d` · 🆕 10-04 `5e41fa599` 새 행 · 지워진 행 · 차이 — 차이 = 표 행 − 색인 행이라 새 행과 지워진 행이 상쇄된다, 차이 0 은 «남은 0» 이 아니다). 행 색인 줄마다 번역할 때의 행 지문(그 소스가 읽는 칸만, 빈 값은 NULL 로 접은 md5)이 있고 census 가 지금 값으로 다시 내어 견준다 — «지문 없음»은 그 전에 번역된 줄이라 따로 센다(섞으면 누락이 부풀어 보임). 고치기: 🆕 셋을 한 번에 `python -m ledger.backfill --world <세상> --catch-up`(그 세상이 읽는 소스 전부 — 새 행 · 수정 누락 · 지워진 행 차례로) · 수정 누락만 `python -m ledger.backfill --source <소스> --drifted`(미리보기) → `--drifted --apply`. 주기 census(엔진 안)는 이 수를 안 센다 — 표를 훑기 때문. 🆕 화면: 대시보드 원장 소스 패널이 소스마다 `New, not translated N · Edited, not followed N · Gone, atoms remain N · Not yet printed N · Measured <시각>`(🆕 10-04 `f36723a70` — 넷, 서버 이름표대로) 을 보이고, 새 행 · 수정 누락 · 지워진 행 중 0 보다 큰 칸이 눈에 띄고(🆕 10-04 `4b2cbc9a5` — 전엔 누락 하나, 지문 없음은 표시 없음), 그 아래에 기록이 싣는 다음 명령 한 줄(10-03 `c965f6206` · `cb9082b79` — 서버 글자 그대로). 셋째 수 칸은 `Table less indexed`(`difference` — 부호 있는 차이, «남은 수»가 아니다 · 10-04 `f36723a70`, 옛 기록의 `not_yet` 도 같은 이름 `Table less indexed` 로 — 10-06 `9ea93f6fd`, 다음 주기가 다시 찍을 때까지). 🆕 `66570d724` 주기 census 는 세지 않고, 사람이 센 수(🆕 10-04 넷 — 새 행 · 수정 누락 · 지워진 행 · 지문 없음)를 «그때 잰 시각 그대로» 잇는다(~~다음 주기가 지움~~). 기록은 다음 명령도 싣는다(`next_step`: ~~누락 > 0 → `--drifted`~~ 🆕 10-04 `5e41fa599` 새 행 · 수정 누락 · 지워진 행 중 하나라도 > 0 → `python -m ledger.backfill --world <세상> --catch-up`, 센 적 없음 → `python -m ledger census --source <소스>` — 🆕 `279d04475` 둘 다 늘 `--world <잰 세상>` 을 단다 — 🆕 10-04 `ec6874b28` 세상 하나, 이름 없으면 운영 세상). ⚠️ `--catch-up`(또는 `--drifted --apply`) 로 고친 뒤에도 기록의 수와 다음 명령은 «고치기 전» 그대로다(주기 census 는 그 넷을 잇기만 한다) — 사람이 census 를 다시 돌려야 0 이 된다 |
| 🆕 오늘 붙인 **수집기**(`# window:` 를 선언한 것)에 **지난 날들의 데이터가 없다** | **`collector_backfill`**(09-26 `9c2ebe9a`) — 파라미터 `collector`(`<표>/<스크립트.py>`) · `start`(KST `YYYY-MM-DD`, 그날 00:00 · 또는 `YYYY-MM-DD HH:MM`). **하루(24 시간 창)씩** 스크립트를 그 날의 창으로 채워 돌리고, 그 날 파일이 적재 큐를 **지난 뒤** 다음 날로 간다. 한 날의 파일이 실패하면 **그 날 이름을 대고 멈춘다**. 결과는 `days`(창 안의 날 수) · `days_done`(모은 날 수) · 🆕 `done_until`(「collected up to (KST)」 — 마지막으로 끝난 창의 끝) — 화면에서는 낱말로(`f6d64682`). 🆕 **다음 번 `start` 는 소급 목록의 그 줄 `next_start`**(09-29 `efa60fd9c`) — 끝까지 · 취소 → `done_until`, 실패 → 실패한 날의 시작, 도는 중 → null. 그대로 다시 넣으면 틈도 겹침도 없다(`start` 는 `YYYY-MM-DD HH:MM:SS` 도 읽는다). 어드민 Retroactive 탭 또는 CLI `python -c "from admin import retroactive; retroactive.run_here('collector_backfill', {'collector': '<표>/<스크립트.py>', 'start': 'YYYY-MM-DD'})"` |

| 🆕 칸마다 **파일 층이 여러 겹** 쌓여 있다(같은 행을 매시간 다시 가져오는 수집기) · 헤비 레인 청크 줄의 `prefetch` 가 크다 | **`fold_file_layers`**(09-26, 총괄 225b2c658) — 파라미터 `table` · `pace`. 칸마다 같은 부류 · 같은 값의 파일 층은 **가장 새 것 하나**만 남긴다(§2.6). 쓰기 쪽은 같은 날부터 **안 쌓는다**(§1.1) |
| 🆕 사고 중 체인 대기열에 **지금 돌면 안 되는** 일이 쌓였다 / 그것을 나중에 돌린다 | **`set_aside`** · **`rerun_set_aside`**(09-26 · 09-27) — 치워 두기는 지우지 않음, 다시 돌리기는 규칙마다 한 번 · 연쇄 없음(§2.8) |
| 🆕 표기 `write` 칸을 선언했는데 **그 전에 저장된 값**이 옛 철자다 · 문자 칸에 **숫자로 저장된 층**이 있다 | **`fold_written_notation`**(09-26, 총괄 2dc2c1baf · 10-01 ㉡) — 파라미터 `table` · `pace`. 층 값 · 보이는 값 · 키를 제자리에서 접는다(§2.7). 끝나면 `fold_file_layers` → VACUUM |

🔴 **ⓒ와 ⓓ를 가르는 질문은 하나입니다 — 「파생 테이블에 그 행이 있습니까?」**
`ⓒ`는 **없던 파생 행을 만듭니다.** `ⓓ`는 **이미 있는 행의 빈 칸을 채웁니다.**
잘못 고르면 **에러 없이 아무 일도 안 일어나고**, 운영자는 기능이 고장 났다고 결론짓습니다. 실제로 그렇게 한 번 잃었습니다.

🔴 **ⓑ와 ⓕ를 가르는 질문도 하나입니다 — 「그 층이 *틀렸습니까*, 아니면 *지고 있습니까*?」**
`ⓑ`는 **더는 사실이 아닌 층을 걷어냅니다**(그 소스의 주장을 지웁니다). `ⓕ`는 **아무것도 걷어내지 않고**, 이미 있는 층들로 승자를 다시 계산합니다. 옛 값이 **여전히 그 소스의 정당한 값인데** 새 층에게 자리를 내주지 못하고 있는 상황이 ⓕ입니다.

> ⓔ만 성격이 다릅니다. ⓐ~ⓓ가 **만들거나 고치는** 소급이라면 **ⓔ는 지우는 소급**입니다. §5에서 따로 다룹니다.

🔴 **ⓖ와 ⓗ를 가르는 질문도 하나입니다 — 「아직 «안 읽은» 행입니까, 이미 읽었는데 «틀리게 읽은» 행입니까?」**
`ⓖ`는 **아직 원장에 없는 행을 번역합니다**(행 색인에 이름이 없는 행 — 화면 이름도 09-25 `a36ec7d3` 부터 「Translate the rows not yet in the ledger」, 종전 「… after the cursor」). `ⓗ`는 **커서를 안 움직이고** 이미 지나온 범위의 원자를 «회수하고 다시 만듭니다». 커서를 움직이면 이미 지나온 행을 다시 쓰면서 **진행도가 앞으로 뛰기** 때문입니다.
⚠️ **ⓗ의 `scope` 는 `limit` 이 아닙니다** — 「어느 행」이지 「몇 행」이 아니고, 페이징을 대체하지 않고 AND 로 걸립니다.

> 📍 **어드민 표면에 «화면»이 있습니다**(2026-08-31 — 종전 「버튼은 아직 없다」는 거짓이 됐습니다). 어드민 **Retroactive** 탭(09-25 `5efa71f75` 에 Overview 에서 옮겨 왔습니다)에서 연산을 고르고 파라미터를 채워 실행하며, **도는 실행 목록과 취소**도 같은 자리에 있습니다. 절차·주의는 **§7**입니다. 결정표는 도구를 고르는 자리이므로 **어느 표면을 쓰든 위 표가 먼저입니다.**
> 🆕 **ⓕ도 등록부 연산 `resolve` 입니다**(09-25 `3321158b2` — 종전 「CLI 전용」은 거짓이 됐습니다). 화면 폼의 파라미터는 `table` · `columns`, `limit` · `chunk_size` 는 CLI 옵션입니다. **취소는 페이지 사이에서 먹습니다**(`cancellable: True`, 09-25 `cb6f93657`). 이어 돌기는 없습니다 — 다시 돌리면 첫 페이지부터이고, 저장된 층에서 두 번 다시 계산해도 답은 같습니다.

---

## 1. 전부가 공유하는 규율 — 한 번만 말합니다

이 넷은 위 결정표의 경로 **모두**에 해당합니다. 개별 절에서 반복하지 않습니다.

1. **기본은 dry-run입니다.** 아무 플래그 없이 돌리면 **읽기만** 합니다. 먼저 돌려서 보고서를 읽는 것이 정상 절차입니다.
2. **`--apply`만이 씁니다.** 쓰기를 시작하는 스위치는 이것 하나뿐이고, 다른 이름의 우회로는 없습니다.
   🆕 **CLI 의 `--apply` 는 어드민 실행과 «같은 문»을 지납니다**(09-25 `9ca3633f1`) — 어드민 실행 목록에 `running` 줄이 서고(runner `retroactive/<호스트>/<pid>`), 관문이 닫혀 있으면 그 관문의 문장으로 거절되고, 화면 취소는 페이지 사이에서 멈추며, Ctrl-C 는 `cancelled` 로 끝납니다. 드라이런(`--apply` 없음)은 이 문 밖입니다.
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

🔴 **빈 칸은 이 서열에 «끼지 않습니다» (2026-09-15 판정 405 `fac454af`).** 「비웠다」를 뜻할 수 있는 저자 — 사람(`user`)과 체인(`chain_ingestion`) — 의 빈 값만 NULL 층을 세우고, 파일·스크립트·미등재 소스의 빈 값은 층을 «안 만듭니다»(있던 층은 그대로 — 어제 값을 준 파일이 오늘 빈칸이면 어제 값이 섭니다. 거두는 것은 사람 · ⓑ R2 · `replace_map` 의 일입니다). 그전에 파일이 세워 둔 NULL 층은 «남아서» 조인 값을 아직 가릴 수 있습니다 — 그 수는 `python scripts/count_absent_null_layers.py`(읽기만, `--apply` 없음)가 「NULL 층의 수」와 「그중 아래 값을 가리는 수」로 «따로» 냅니다. 답의 뜻은 `RUN.md` §1-bis, 계약은 [data_model §2.1-quater](../architecture/data_model.md).

🔴 **같은 우선순위 안에서는 무엇이 이깁니까 — 2026-08-11부터 답이 있습니다.** 종전에는 미등재 이름이 **전부 99로 동점**이었고 승자가 목록 조립 순서로 떨어졌습니다(그리고 그 순서는 **기존 값이 항상 이기도록** 돼 있었습니다). 지금 순서는 **① 등재 우선순위 → ② `ingested_at` 내림차순(최신 배달이 승, 날짜 없는 층은 뒤로) → ③ `source_name` 오름차순**이고, ③이 있어 **언제나 결판이 납니다.**
**소급 관점에서 이것이 뜻하는 것 둘** — ⓒ와 ⓓ는 여전히 둘 다 99지만 이제 그 **둘 사이도 결정적으로** 갈립니다(먼저 도착한 쪽이 아니라 **나중에 도착한 쪽**이 이깁니다). 그리고 **이미 확정된 칸은 이 수리로 저절로 안 움직입니다** — 그것을 움직이는 것이 **ⓕ**입니다(§2.5).
⚠️ **서열 자체는 한 칸도 안 움직였습니다** — ②③은 **한 우선순위 *안에서만*** 동점을 가르며, 낮은 서열을 높은 서열 위로 올리지 못합니다.

🆕 🔴 **파일 층은 «같은 값이면 안 쌓입니다»**(09-26, 총괄 225b2c658 · f224477c1 · a7d2e90ec). 파일 층 = 제품이 쓰는 기계 층 이름(`crud.machine_layer_names` — 위 표의 이름들과 `SOURCE_PRIORITY`, 상수에서 조립) **밖**의 이름 — 파일 파서는 파일 이름으로 쓰기 때문입니다.
- 새 파일 값이 같은 칸 · 같은 우선순위 부류의 **가장 새 층**(그 층이 파일 층일 때)과 같으면 **아무것도 안 씁니다.** 매시간 같은 행을 다시 가져와도 두 번째부터 `cell sources` 쓰기가 0 입니다.
- 다르면 새 층을 쓰고, 같은 부류에서 **그 값을 말한 옛 파일 층**을 지웁니다(청크 줄의 `folded layers`). 사람이 고정한 출처는 안 지웁니다. 이기는 값은 어느 쪽이든 안 움직입니다.
- 「같다」는 값 층 · 층 no-op · 접기가 **한 함수**(`crud.values_differ`)로 봅니다 — 숫자 `1` 과 글자 `'1'` 은 같은 값입니다(글자 앞뒤 공백은 원래 캐스트가 벗깁니다). 🆕 시각 칸은 «같은 순간»이면 철자가 달라도 같은 값이고(UTC 로 적든 시간대 없이 세션 시간대로 적든), 빈 값은 부재입니다 — R2/R3 도 같은 함수를 지나서 철자만 바뀐 순간이나 저장된 빈 값을 «다시 쓸 것»으로 세지 않습니다(09-30 `29b14dc21`).
- ⚠️ **한계**: 손으로 쓴 맵퍼가 제 이름으로 쓰는 층은 목록 밖이라 **파일 층으로 읽힙니다.** 지우는 것은 «더 새 층이 같은 값»일 때뿐이라 이기는 값은 안 바뀌고, 사라지는 것은 「어느 옛 작성자가 먼저 그 값을 말했나」 기록입니다. 합치기(collision merge)가 옮긴 층 `<작성자> (<키>)` 는 그 작성자의 층으로 읽힙니다(`crud.layer_writer`).

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

트리거 테이블의 **현재 내용**을 키셋 페이지로 훑어 실제 매퍼로 다시 흘려보냅니다. `replay-all`은 **의존 순서대로 각 룰을 정확히 1회씩** 돌립니다(생산자가 소비자보다 먼저 · 순환이면 «선언 순», 2026-09-15 판정 402).

🆕 **[2026-09-15 S-242] `declared:join` 규칙 — 선언된 join — 도 같은 명령입니다.** 룰 이름은 «선언» 이름(원천 `on.table` 을 트리거하는 쪽)을 주십시오 — 09-25 `244d825dc` 부터이고, 전엔 「왼쪽」이었습니다. 짝 `<선언>:target` 을 통째로 주면 「chain rule '<짝>' is the second half of declaration '<선언>'; … Replay that one instead, or pick the rows to replay this one for.」로 거절됩니다. 사전 계수의 「다시 계산할 행」은 이제 «원천» 행 수입니다. 보고서에 **`rows_written`** 이 따로 섭니다(이 종류는 셀을 «제안하지 않으므로» `cells_proposed` 는 0 이 정상) · 드라이런은 넘겨받을 «행 수» · 던진 페이지는 `pages_failed`·`page_failures` 로 세고 다음 페이지로 갑니다. 어드민 사전 계수 화면도 이 종류에는 「다시 계산할 행」을 보입니다 — 종전엔 「0 셀」이었고 그것은 «아무 일도 없다»로 읽혔습니다.

**「이 행들만」 — `--business-keys`(어드민 `business_keys`, 2026-08-31) «또는» `--row-ids`(어드민 `row_ids`, 2026-09-16 S-254 `fe2d0c6c`)**

```bash
… replay <룰> --business-keys KEY-A,KEY-B,KEY-C      # 평키 표의 운영자 · CLI — 트리거 표의 business_key_val
… replay <룰> --row-ids r1,r2,r3                     # 화면에서 — 그리드가 «모든 표»에서 든 신원 row_id
```

- 🔴 **둘은 «한 물음(어느 행)에 두 답»이라 같이 주면 거절됩니다** — 교집합을 돌리지도, 한쪽을 조용히 고르지도 않습니다. 하나만 보내십시오.
- 🔴 **왜 `row_ids` 가 생겼나:** `composite_key_source` 표의 저장 키(`business_key_val`)는 «조립된 문자열»이라 어느 컬럼에도 없습니다. 화면이 «보이는 값»을 업무 키로 보내면 한 행도 안 맞고 `rows_scanned 0` 에 «오류가 없습니다» — 그래서 그리드의 배너(C-112)는 이제 `row_ids` 만 보냅니다(누르는 줄과 「어드민에서 열기」 넘김이 같은 신원). `row_id` 없는 행은 「row_id 없는 행 N — 다시 돌릴 수 없음」으로 «이름 대고» 서고(그 줄을 누르면 첫 행을 그리드에서 보여 줍니다, C-114), 선택이 기준(기본 1000행)을 넘으면 「선택 N행 · 권장 K행 이하」 한 줄이 «막지 않고» 말합니다(C-113).
- 🔴 **`--limit` 과 «다른 축»입니다.** 이 두 옵션은 **어느 행**이고 `--limit` 은 **몇 행**입니다 — 둘은 함께 걸리고, 하나가 다른 하나를 대체하지 않습니다. 「고른 행만 돌렸는데 다 안 돌았다」면 `--limit` 이 아직 걸려 있는 것입니다.
- 🔴 **빈 목록은 「아무것도 안 함」이 아니라 «거절»입니다**(둘 다). 값 없이 이 옵션을 주면 「빈 선택은 아무것도가 아니라 «전부»를 돌리게 된다」며 이름 대어 거절합니다 — 전부를 돌리려면 **옵션을 빼야** 합니다.
- ⚠️ 업무 키는 **트리거 테이블의 `business_key_val`** 로, row id 는 **트리거 테이블의 `row_id`** 로 읽습니다(타깃이 아닙니다). 페이지마다 `WHERE` 에 들어가므로 나중에 걸러 내는 것이 아니라 **애초에 그 행만 읽습니다.**

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
- 🆕 **ⓕ도 어드민 연산 `resolve` 입니다**(09-25 `3321158b2` — 종전 「ⓕ만 어드민 API에 없다」는 거짓이 됐습니다). 취소는 페이지 사이에서 먹습니다(§0).
- ⚠️ **화면이 즉시 갱신된다고 보장하지 않습니다.** 다 돌린 뒤 새로고침해서 확인하십시오.
- 🔴 **[2026-08-11 `ffb23d6`] 이 명령은 하류 체인을 깨우지 않습니다 — 종전에는 깨웠습니다.** 수리된 행마다 나가는 내부 이벤트가 **사람이 그리드에서 친 것과 똑같은 라벨**을 달고 있어서, 칸 하나를 고치면 그 테이블에 걸린 파생 규칙이 전부 돌고 다른 테이블에 쓰기까지 했습니다. 지금은 `chain_ingestion` 라벨이라 **그 이벤트를 받겠다고 명시적으로 선언한 규칙(`allow_chain_trigger`)만** 반응합니다.
  - ⚠️ **`ffb23d6` 이전에 이 명령을 `--apply`로 돌린 적이 있으면, 그때 파생 테이블에 딸려 들어간 쓰기가 있을 수 있습니다.** 어느 테이블인지는 그 시각의 체인 워커 로그에서 확인하십시오.
  - **대량 실행이 훨씬 빨라졌습니다** — 종전에는 수리 행마다 별도 그룹으로 직렬 처리돼(그룹당 ~0.4초) 1만 행이 한 시간을 넘겼고 그동안 **정상 인제션이 뒤에 줄을 섰습니다.** 지금은 실행 전체가 그룹 하나입니다.
  - ✅ **ⓑ(철회)도 같은 날 닫혔습니다**(`53f9187` — §2.3). ⓐ(재적용)만 아직 페이지 단위로 묶여 있어 대량 실행이 여러 그룹으로 갈립니다.

> 🔴 **이 명령은 「같은 값이 여러 번 쌓이는 문제」를 고치지 않습니다.** 고치는 것은 **쌓인 것 중 무엇이 이기는가**뿐입니다. 쌓인 것을 줄이는 것은 🆕 **§2.6 `fold_file_layers`** 이고, 09-26 부터 쓰기 쪽은 같은 값을 안 쌓습니다(§1.1).

### 2.6 🆕 `fold_file_layers` — 같은 값의 파일 층 접기 (**지웁니다 · 되돌릴 수 없습니다**)

```bash
python -c "from admin import retroactive; retroactive.run_here('fold_file_layers', {'table': '<표>'})"
```
어드민 **Retroactive** 탭에서는 `Fold file layers that repeat a newer one` — 파라미터 `table` · `pace`(`limit` · `chunk_size` 는 CLI).

- **하는 일**: 칸마다, 같은 우선순위 부류의 파일 층 중 **값이 같은 것**은 `compute_priority_value` 가 먼저 세우는 것(가장 새 것)과 **사람이 고정한 것**만 남기고 지웁니다. 칸의 승자는 자기 무리에서 첫째라 늘 남습니다 — **보이는 값 · 행 · 이력은 안 움직입니다.** 사람 · 체인 · 자동 확정 · 백필 층은 안 건드립니다.
- **드라이런(Count)**: 「cells in rows hold file layers that repeat a newer one: layers N -> M, the deepest cell A -> B」. 그 수가 곧 지울 수입니다.
- 🔴 **되돌릴 수 없습니다** — 사라지는 것은 「같은 값을 말한 옛 파일 이름」 기록뿐이지만 되돌릴 방법은 없습니다.
- **끝나면**: `python server/scripts/tune_layer_tables.py --table cell_sources --vacuum` — 지운 자리를 돌려받습니다(VACUUM 은 트랜잭션 밖이라 이 연산이 하지 않습니다).
- ⚠️ **R2(ⓑ)의 가장자리가 달라집니다**: 파일3 A · 파일10 A 에서 파일10 을 철회하면 접기 «전»엔 파일3 의 A 가 드러나고, 접은 «뒤»엔 그 아래 층이 드러납니다. 쓰기 쪽에서 «안 쓴» 경우(파일10 이 파일3 과 같아 층이 안 생김)도 같습니다 — 그 칸을 마지막으로 같은 값이라 말한 파일은 옛 파일로 남습니다.
- 페이지(기본 1000 행)마다 커밋 · 취소는 페이지 사이 · 다시 돌리면 남은 것만 찾습니다.

### 2.7 🆕 `fold_written_notation` — 선언 전에 저장된 값을 선언한 철자로 (**되돌릴 수 없습니다**)

```bash
python -c "from admin import retroactive; retroactive.run_here('fold_written_notation', {'table': '<표>'})"
```
어드민 **Retroactive** 탭에서는 `Fold stored values into the declared spelling` — 파라미터 `table` · `pace`(`limit` · `chunk_size` 는 CLI).

- **하는 일**: `notation_rules.json` 의 `"write": true` 칸, 그리고 🆕(10-01 ㉡) **글자 칸 전부**(number · datetime 아닌 칸)에서 모든 층 값 · 보이는 값 · 행의 키를 쓰기 문과 **같은 접기**(표기 접기 -> 글자 캐스트: 숫자는 `clean_str_value` 의 철자, 공백 trim, 빈 글자는 null)로 접습니다. 층이 접힌 칸은 보이는 값을 **접힌 층에서 다시 정합니다**(R3 과 같은 함수). 층을 다시 쓰지 않고 **값만** 바꾸므로 층의 순서가 그대로이고 **이기는 층이 안 바뀝니다**(쓰기 문으로 다시 보내면 옛 층이 가장 새 층이 되어 보이는 «값»이 바뀝니다 — 실측).
- **드라이런(Count)**: 「N cell(s) and M stored layer(s) … take the declared spelling; K row key(s) change」 + 건너뛸 행 · 또 바뀌는 값 · time 이 그대로 둔 값. `write` 칸도 글자 칸도 없는 표는 「has no "write" column ... and no text column」.
- **건너뜀**: 접은 키를 다른 행이 이미 쥐고 있으면 그 행은 **한 칸도 안 접고** 이름을 댑니다(병합은 되돌릴 수 없음). 🆕 키는 접기가 **키 부품 칸**을 바꾼 행만 바뀌고, 그 행의 **안 접은 칸이 저장 키를 그대로 짓는 때만** 바뀝니다 — 아니면(옛 구분자 · 시각 철자 등으로 이미 어긋난 키) 그 행도 한 칸도 안 접고 `keys_not_rebuilt` 로 셉니다(신원 그대로).
- **멈춤**: 한 번 더 접으면 또 바뀌는 값이 든 페이지 «앞»에서 멈춥니다 — 선언이나 별칭 행을 먼저 고칩니다.
- 🔴 **되돌릴 수 없습니다** — 저장돼 있던 철자는 칸마다 이력 줄(`notation_backfill`)의 옛 값으로 남습니다.
- **끝나면**: `fold_file_layers`(같은 표) → `python server/scripts/tune_layer_tables.py --table cell_sources --vacuum`.
- 바뀐 행은 소급 경로(`retroactive`)의 사건을 내므로 체인 규칙은 안 깨고, 원장 후속 랩은 그 사건으로 다시 번역합니다.
- 페이지마다 커밋 · 취소는 페이지 사이 · 다시 돌리면 남은 것만 접습니다.


### 2.8 🆕 `set_aside` · `rerun_set_aside` — 체인 대기열 치워 두기와 다시 돌리기 (09-26 `312e8440a` · 09-27 `91d838682`)

```bash
python server/scripts/outbox_triage.py --set-aside --tables <표> --reason "<왜>" --apply
python server/scripts/outbox_triage.py --rerun-set-aside --tables <표> --apply
```
어드민 **Retroactive** 탭에서는 `Set queued chain events aside` · `Run set-aside events again` — 파라미터 `tables` · `rules` · `transactions`(치워 두기는 `reason` 도).

- **치워 두기**: 범위의 미처리 체인 사건에 `cancelled_by = operator` 와 사유를 남기고 안 돌립니다. **지우지 않습니다.** 표 · 규칙 · 트랜잭션 중 **하나 이상**을 적어야 합니다(「대기열 전체를 한 번에」는 거절).
- **다시 돌리기**: 치운 사건이 가리키던 행을 리플레이합니다 — **규칙마다 한 번 · 연쇄 없음**(소유자 09-27 「큰 소급 치워둔거니 한번만」 — 전에는 체인처럼 연쇄). 그 쓰기는 아래 규칙을 깨우지 않습니다. 아래까지 돌려야 하면 **그리드에서 행을 찍어 리플레이**합니다(연쇄하는 것은 그 클릭뿐 — 옵트인 규칙만).
- 비상 정지 순서(멈춤 → 치워 두기 → 다시 흐름 → 나중에 다시 돌리기)는 [RUN.md](../../RUN.md) 의 비상 정지 항목.
- 🆕 10-08 **줄 하나만**: 체인 대기열 화면의 × (`POST /admin/chain/queue/cancel {"key"}`) 가 같은 치워 두기를 그 줄에만 — 도는 묶음이면 그 질의도 끊습니다. 멈춤 없이. 다시 돌리기는 위와 같습니다.

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

> ℹ️ **2026-07-31 `9c6a1c9` — 이 도구의 알맹이는 `server/chain/enrichment/backfill.py`로 옮겨졌고, `scripts/backfill_enrichment.py`는 그 위의 CLI가 됐습니다.** **경로·진입점·플래그는 하나도 바뀌지 않았으므로 위 명령은 전부 그대로 동작합니다.** 의미론은 `server/`에, argparse와 출력은 `server/scripts/`에 두는 분리가 `chain_replay`와 enrichment 도구에 적용됩니다.

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
| ① **`auto_confirm` 노브가 꺼져 있다** (기본값이 **OFF**입니다) | `rule '<룰>' has 'auto_confirm' off (default)` | `chain_rules.json` 그 규칙의 `derive.decide` 에 `"auto_confirm": true`. 노브가 **사람의 동의 자리**라 우회로가 없습니다 |
| ② `--ignore-knob`과 `--apply`를 **같이** 줬다 | `--ignore-knob is a measurement-only flag and cannot be combined with --apply` | `--ignore-knob`은 **꺼진 규칙의 규모를 재는 용도**입니다(dry-run 전용). 쓰려면 ①을 하십시오 |
| ③ 어느 참조뷰에도 **`candidate_for` 선언이 없다** | `rule '<룰>' declares no 'candidate_for' on any reference view` | 어느 뷰 컬럼이 어느 타깃의 후보인지 **선언**하십시오. 컬럼 이름으로 유추하지 않습니다 → [config/enrichment_rules §7](./config/enrichment_rules.md) |

**그리고 네 번째 원인은 거절조차 아닙니다** — **애초에 이 도구가 아니었던 경우**입니다. 파생 행이 없으면 워크리스트가 비어 있고, `queue size : 0`으로 정상 종료합니다. 그때 필요한 것은 **ⓒ**입니다(§0 결정표).

---

## 5. ⚰️ ~~ⓔ graph_orphan_sweep~~ — **은퇴** (2026-08-14 `2ec78b9` · R-2026-08-14-H)

🔴 **ⓔ는 더 이상 소급 경로가 아닙니다 — 돌리지 마십시오.** 지울 대상(`graph_nodes`/`graph_edges`)이 은퇴하고 **DROP**됐습니다(약 841 MB).

- **어드민 API에서 «등록 해제»됐습니다.** `server/admin/retroactive.py`의 `OPERATIONS`는 이제 `chain_replay`·`withdraw`·`enrichment_backfill`·`enrichment_confirm` **넷**입니다. `GET /admin/retroactive/operations`에 ⓔ 행이 없고, `POST /admin/retroactive/graph_orphans/run`은 미등재 연산으로 거절됩니다. 이 문서에서 **「다섯」이라 적힌 자리는 전부 「넷」으로 읽으십시오.**
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

- **없으면 이 카운트가 `cell_sources` 전량 스캔이 되고, 그 비용이 요청 경로에 앉습니다**(§7의 `count` 라우트). 실측 근거(행 수·소요·버퍼·플래너 판정)는 `server/database/models.py`의 `idx_sources_by_source` 주석과 `server/scripts/ops_setup_db_performance.py` Step 3.10에 **기록돼 있습니다** — 여기 사본을 만들지 않습니다.
- **반영 경로는 하나입니다**: `conda run -n assy_manager python server/scripts/ops_setup_db_performance.py`(Step 3.10). `create_all`은 **이미 있는 테이블에 인덱스를 추가하지 않으므로**, `models.py` 선언만으로는 기존 운영 DB에 생기지 않습니다.
- 스크립트가 만든 뒤 **플래너가 실제로 그것을 골랐는지까지 검사**합니다(Step 3.11). 표가 작으면(`WITHDRAW_PLAN_MIN_ROWS` 미만) **실패가 아니라 `NOT VERIFIED`**를 찍습니다 — 작은 표에서 Seq Scan은 옳은 계획이고, 거기서 우는 검사는 운영자가 검사를 무시하게 만듭니다.
- 운영 관점 전문은 [POSTGRES_OPERATIONS §3.1](./POSTGRES_OPERATIONS_GUIDE.md).

---

## 7. 어드민 표면 — **화면이 있습니다** (2026-08-31 · 종전 「버튼은 아직 없다」는 거짓이 됐습니다)

어드민 **Retroactive** 탭에 소급 화면이 있습니다(09-25 `5efa71f75` 에 Overview 에서 옮겨 왔습니다). 연산을 고르고 파라미터를 채워 실행하며, **도는 실행 목록과 취소**가 같은 자리에 있습니다. `curl` 도 그대로 됩니다.
**현재 목록의 정본은 `GET /admin/retroactive/operations` 응답입니다** — 이 문서는 개수를 적지 않습니다.

> 🆕 **ⓕ(R3 `resolve`)도 이 표면에 있습니다**(09-25 `3321158b2`) — 취소는 페이지 사이에서 먹고, 이어 돌기는 없습니다(§0).

| 라우트 | 하는 일 |
|---|---|
| `GET /admin/retroactive/operations` | 등재된 연산의 목록·파라미터·**대응 CLI**·CLI에만 있는 기능. 항목마다 `deletes`·`restartable`·**`cancellable`**·`commit_granularity`. 값이 닫힌 파라미터는 **`choices`**(§7.6) |
| `GET /admin/retroactive/{op}/count` | 「몇 건인가」 — 쓰기 없음 |
| `POST /admin/retroactive/{op}/run` | 실행을 **큐에 넣고 즉시 반환**(실제 실행은 스케줄러가 집어 띄운 «자식 프로세스» — §7.3. `chain_replay` 만 체인 워커) |
| **`GET /admin/retroactive/runs`** | **[신설]** 실행 목록과 진행 — `state`·`processed_rows`/`total_rows`·시각 |
| **🔒 `POST /admin/retroactive/runs/{run_id}/cancel`** | **[신설]** 멈춤을 «부탁»한다. 죽이지 않는다(§7.5) |

```bash
curl -H "X-Admin-Token: $ASSY_ADMIN_TOKEN" http://127.0.0.1:8080/admin/retroactive/operations
curl -H "X-Admin-Token: $ASSY_ADMIN_TOKEN" "http://127.0.0.1:8080/admin/retroactive/withdraw/count?table=bonding_map&source=chain_ingestion"
curl -X POST -H "X-Admin-Token: $ASSY_ADMIN_TOKEN" -H "Content-Type: application/json" \
     -d '{"params": {"table": "bonding_map", "source": "chain_ingestion"}}' \
     http://127.0.0.1:8080/admin/retroactive/withdraw/run
```

### 7.1 CLI가 없어진 것이 아닙니다 — 버튼은 **흔한 형태**만 덮습니다

라우트는 각 연산의 **파라미터 필수분**만 받습니다. 나머지는 CLI에 남아 있고, 그 목록을 `operations` 응답의 **`cli_only`**가 직접 들고 있습니다 — `replay-all` · `--limit` · `--chunk-size` · `--force-disabled` · `--ignore-knob` · `classify`/`propose`.

> ⚰️ **[2026-08-31] 아래 문단은 «없어진 파일»을 서술합니다.** `scripts/graph_orphan_sweep.py`·`server/graph_orphans.py`는 2026-08-16에 제거됐고(그 부재를 시험이 못박고 있습니다), `--allow-production` 이라는 철자를 오늘 어느 CLI 도 들고 있지 않습니다. **기록으로만 읽으십시오.**
> ✅ **살아남는 생각** — 「어드민 버튼이 CLI 와 «같은 함수»를 부르더라도, CLI 가 «묻는 확인»까지 재현하지는 않는다」. CLI 를 아는 운영자는 물어볼 것을 기대합니다. 오늘 그 자리를 지키는 것은 확인 대화가 아니라 **`cancellable`·`deletes`·`commit_granularity` 선언**(§7.5)입니다 — 화면이 무엇을 경고할지 «추측하지 않게» 합니다.

~~🔴 **`--allow-production`은 CLI에만 있고, 그 사실이 중요합니다.** 격리 관문(§5)은 `scripts/graph_orphan_sweep.py` 안에 있지 `graph_orphans.run_scheduled` 안에 있지 않습니다. 어드민 버튼과 **매일 도는 스케줄러가 부르는 것은 후자**이므로, 이 라우트는 데몬이 이미 하고 있는 것 이상의 권한을 주지 않습니다 — 다만 **CLI가 묻는 확인을 재현하지도 않습니다.**~~

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

`run`은 아웃박스에 한 줄 쓰고 `{"status": "queued", "run_id": …}`를 돌려줍니다. 🆕 스케줄러가 그 행을 집어 **자식 프로세스 하나**(`python -m admin.retroactive_run <run_id>`)에서 돌립니다(09-25 `bfbe8a525`). 스케줄러 로그(`auto_update.log`)에는 「[Retroactive] run_id=… runs in its own process pid=…」 한 줄만 남고, **진행과 결과는 `retroactive.log`** 에 있습니다(자식이 print 한 것은 `retroactive_stdout.log`). `POST /admin/auto-update/run-now`와 같은 형태입니다.

- **동시 1건입니다.** 실행 중에 또 요청하면 조용히 줄 세우지 않고 **거절 + 로그**하며, 아웃박스 행은 미처리로 남아 다음 틱이 집습니다.
- **토큰이 설정돼 있지 않으면 이 라우트만 503입니다**(조회 라우트 둘은 열립니다). 코드 실행 라우트와 같은 취급인데, 코드 실행이라서가 아니라 **테이블 전체 재작성·소스 회수·노드 삭제**라는 피해 계급이 같기 때문입니다.
- **사람 값 보호는 라우트가 아니라 연산 안에 있습니다**(§2.4) — 어드민을 거쳐도 우회되지 않습니다.

### 7.4 ✅ 종전의 「아직 없는 것」 둘은 **둘 다 착지했습니다** (2026-08-31)

- ~~어드민 화면의 버튼~~ → **있습니다.** 어드민 Retroactive 탭(09-25 전에는 Overview 의 소급 블록).
- ~~실행 이력 화면~~ → **있습니다.** 도는 실행 목록 + 진행 + 취소. 다만 **끝난 실행의 «결과 본문»은 로그**(`retroactive.log` — 09-25 전에는 스케줄러 로그)에서 읽습니다 — 목록이 답하는 것은 상태와 진행이고, 트리거 응답에는 예나 지금이나 결과가 없습니다(§7.3).
- 진행 상황은 [보드](../process/PROJECT_STATUS.md)를 보십시오.

### 7.5 취소 — **죽이는 것이 아니라 «부탁»입니다** (2026-08-31 신설)

`POST /admin/retroactive/runs/{run_id}/cancel`은 프로세스를 죽이지 않습니다. 실행 행의 상태를 **`cancel_requested`로 세우고** 끝나며, 도는 쪽이 **배치/페이지 사이에서** 그것을 묻고 스스로 멈춥니다.

- 🔴 **그래서 «즉시»가 아닙니다.** 지금 도는 배치는 끝까지 갑니다. 큰 청크를 쓰는 연산일수록 반응이 늦습니다.
- 🔴 **`cancel_requested`와 `cancelled`는 다른 상태입니다** — 앞엣것은 「부탁했다」, 뒤엣것은 「멈췄다」입니다. 목록에서 그 둘을 같은 것으로 읽지 마십시오.
- 🔴 **이미 끝난 실행은 «되돌리지» 않습니다** — 🆕 10-08 거절 대신 그 상태(`run: "done"`)로 답하고, 그 실행이 넣어 두고 아직 체인이 안 먹은 사건을 빼 둡니다(`skipped_events` — 대기열 줄 × 와 같은 함수). 이미 커밋된 일은 그대로입니다. 되돌리려면 이 문서의 다른 경로(ⓑ 철회 · ⓗ 범위 재번역)를, 빼 둔 사건을 다시 돌리려면 `rerun_set_aside` 를 쓰십시오.
- 🔴 **취소를 받는지는 «선언»입니다**(`cancellable`). 화면은 거짓이면 **버튼을 아예 안 그립니다** — 눌러도 아무 일 없는 버튼보다 없는 버튼이 낫기 때문입니다. 🆕 **09-25 `3bf01b96` 부터 일곱 다 참입니다** — rescope 는 범위를 페이지로(그룹을 안 쪼갬, 페이지마다 한 커밋), confirm 은 큐를 쓰기 청크로 넘깁니다. 아래 표는 그 «전»의 사유(기록):

| 연산 | 왜 못 멈추나 |
|---|---|
| **ⓗ `ledger_rescope`** | **회수와 재생성이 «두 커밋»**이라 그 사이에서 멈추면 **원자가 빠진 채 아직 안 돌아온 상태**로 남습니다. 복구는 「**같은 범위를 다시 돌리는 것**」이고, 2026-08-31에 실제로 그 사이에서 죽어 재실행으로 끝났습니다 |
| **ⓓ `enrichment_confirm`** | 큐 «전체»를 모아 한 번에 넘기고, 커밋은 그보다 **한 층 아래**(배치 업서트의 쓰기 청크)에서 일어납니다. 이 층에 훅을 달면 **쓰기가 시작되기 «전»에만** 듣는 취소가 되고, **첫 순간에만 듣는 취소는 없는 것보다 나쁩니다** |

- ⚠️ **`total_rows`가 비어 있으면 「0」이 아니라 「모름」입니다.** 진행률이 안 그려지는 것이 정상인 연산이 있습니다.

### 7.6 페이싱 — **「도는 동안 화면이 느리다」의 노브** (2026-08-31 신설)

**`pace`** 파라미터를 든 연산은 **둘**입니다 — ⓐ `chain_replay`(R1, 2026-09-02 합류)와 ⓖ `ledger_backfill`. 값이 닫혀 있어 화면은 텍스트칸이 아니라 **선택지**를 그립니다. ⚠️ **수를 여기 핀으로 박지 마십시오** — 정본은 `server/admin/retroactive.py`의 `OPERATIONS`이고 `GET /admin/retroactive/operations`가 그대로 답합니다.

| 이름 | 언제 |
|---|---|
| `fast` | 기본. 상한 없이 계속 — **오늘까지의 행동 그대로** |
| `slow` | 옆 질의가 느려질 때 |
| `trickle` | 업무 시간에 돌려야 할 때 |

- 🔴 **선언은 `server/pacing.json` «하나»이고, 읽는 쪽이 «셋»입니다** — 원장 백필 · 체인 재적용 R1 · 파일 인제션(그쪽은 `ingestion_settings.json`의 `ingestion_pace`가 이름을 고릅니다). 노브를 작업마다 만들지 않은 것이 이 설계의 요점입니다.
- ⚠️ **한 사이클의 «단위»가 소비자마다 다릅니다** — 백필과 R1 은 **페이지**, 인제션은 **청크**입니다. 표가 정하는 것은 «리듬»이지 «양»이 아닙니다.
- ⚠️ **모르는 이름을 주면 «사람이 요청한» 경로는 거절합니다**(백필·R1 둘 다), **데몬의 기본값인** 인제션은 경고 후 전속력입니다. 갈림은 2 대 1 이고, 그 기준은 「이 이름을 방금 사람이 쳤나」입니다 — 오타를 안은 채 전속력으로 도는 것을 막기 위해서입니다.
- ⚠️ **도는 중에 `pacing.json`을 고쳐도 그 실행에는 안 듣습니다** — 읽기가 실행 시작마다 한 번입니다. 재기동은 필요 없습니다.
- 계약·소비자는 [backend §4.1](../architecture/backend.md), 재사용 관점은 [PRIMITIVES §6](../architecture/PRIMITIVES.md).
