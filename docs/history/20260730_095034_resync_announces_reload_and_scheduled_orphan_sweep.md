# resync가 스스로를 알린다 + 고아 스윕이 스케줄러로 — 그리고 깨끗하게 읽히던 검증 계기

> **일자:** 2026-07-30 09:50 | **커밋:** `530fdfd` | **담당:** Ontology PM
> **대상:** `server/graph_orphans.py`(신규 449줄) · `server/graph_sync_worker.py`(+90) · `server/main.py`(+160) · `server/ontology_config.py`(+53) · `server/run_auto_update.py`(+42) · `server/scripts/graph_orphan_sweep.py`(재작성) · `server/tests/test_ontology_reload_and_sweep.py`(신규 553줄, 29건)
> **관련:** `aea4700`(이 고아를 만든 개정) · `8670e3b`(이 커밋이 QA HIGH를 닫는 엔드포인트) · `46a67c7`(파일 감시자 논거의 근거)

## 현상

08:05에 매핑 config를 적용했는데 **실행 중인 materializer가 내가 교체한 선언을 40분 동안 계속 물화했다.** 파일을 감시하는 것이 없고, 루프를 리로드하는 것은 `SYSTEM_RELOAD` outbox 이벤트뿐이며, `execute_manual_sync`는 디스크에서 읽어 **루프가 절대 보지 못하는 자기 로컬**에 담는다.

## 수리 ① 파일을 효력으로 읽은 **모든** 경로가 알린다

```python
async def _announce(reason: str):
    await asyncio.to_thread(publish_system_reload, reason)
```

resync 완료 후, 그리고 **두 개의 `no_mapping` 반환 모두**에서 발행한다 — 후자가 한 칸 옆의 같은 구멍이다: 어떤 테이블의 매핑을 지우고 그 테이블을 resync하면 `no_mapping`에 도착하는데, 루프는 **내가 지운 것을 계속 물화한다.** 반대로 **존재하지 않는 테이블 이름은 아무것도 발행하지 않는다** — 읽힌 것이 없으므로 알릴 것도 없다.

**그래프 전용 레버를 만들지 않았다.** 모든 데몬(materializer 루프·체인 워커·run_watcher·auto-update 스케줄러)이 이미 `SYSTEM_RELOAD`를 구독하고 `/admin/reload-configs`가 정확히 그 행을 발행한다 — 운영자가 손으로 눌러야 했던 그것이다. 재사용하면 resync 경로와 admin 경로가 **두 기제로 갈리지 않고 하나로 수렴한다.**

**NOTIFY는 insert의 트랜잭션 *안*에서** 나간다(`database.create_outbox_event`가 하는 그대로). 커밋 뒤에 낸 NOTIFY는 새 트랜잭션에 앉아 `Session.close()`가 롤백하므로 **절대 전달되지 않고**, 폴러의 2초 fallback이 조용히 유일한 경로가 된다. 발행 실패는 로그를 남기고 `False`를 돌려준다 — 이미 써진 resync를 실패시키면 안 된다.

## 🔴 검증 계기가 결함이 살아 있는 동안 세 번 깨끗하게 읽혔다

이 항목의 진짜 기록 가치는 여기다.

| 무엇을 확인했나 | 결과 | 왜 |
|---|---|---|
| 은퇴한 **엣지 타입**이 남아 있나 | **항상 깨끗** | `_retarget_stale_edges`가 `(from_node, type, to_node)`를 로우의 현재 산출과 대조해 지운다 — **검증 대상인 그 resync가 바로 그것을 삭제한다.** 계기가 자기가 재는 것을 지운다 |
| 은퇴한 **노드 라벨**이 새로 만들어졌나 | **결함을 잡았다** | 40분 낡은 창 안에 `Chip` 노드 25개가 새로 주조됐다 |
| **타깃이 재라벨된** 엣지 | **둘 다 못 본다** | `PERFORMED_ON`은 **타입을 유지한 채 타깃이 `Wafer`→`Core`로 바뀌었다.** 타입은 은퇴하지 않았으니 첫 계기에 안 걸리고, `Wafer` 라벨도 은퇴하지 않았으니(enrichment `RESOLVED_AS`가 여전히 주조한다) 둘째 계기에도 안 걸린다. **45건**, `(type, from 라벨, to 라벨)` 삼중항을 비교해서만 나왔다 |

교훈은 계기 선택에 있다: **은퇴한 타입을 세는 검증은 그 타입을 지우는 연산 위에서 돌면 원리적으로 항상 통과한다.** 그리고 타입과 라벨을 각각 보는 것으로는 「같은 타입이 다른 것을 가리킨다」를 볼 수 없다.

## 재현 — 40분이 0이 아니라 4초가 됐다

주장이 아니라 **실 프로세스**에 대고 재현했다. 수정 전 빌드는 편집 이후에 인제션된 행에 대해 **은퇴한 라벨을 주조**했고, 수정 후 빌드는 **4초 안에** 새 라벨을 주조했으며, 발행을 주석 처리하고 워커를 재기동하니 **resync 두 번과 25초를 지나도 부팅 시점 선언에서 움직이지 않았다.**

**40분이 4초가 됐지 0이 되지는 않았다** — resync가 백그라운드 작업으로 돌므로 잔여 창은 그 자신의 소요 시간이다.

## 파일 감시자 기각 — 내가 처음 댄 이유가 아니었다

처음 댄 이유("`config_watcher`가 원자적 쓰기를 못 다룬다")는 **틀렸다.** `46a67c7`이 실제 watchdog 테스트로 그것을 닫아 놨다.

진짜 막는 것은 **`ConfigChangeHandler`가 모든 이벤트에 대해 타이머 슬롯을 하나만 든다**는 것이다. 두 번째 파일명을 감시하면, 두 config를 1초 안에 저장할 때 앞 타이머가 취소되고 — 살아남은 것이 온톨로지 쪽이면 **DDL을 동반하는 `table_config` 리로드가 아예 돌지 않는다.** 그것이 `46a67c7`이 방금 닫은 저장 유실 계급이고, 핸들러를 일반화하는 것으로 **다시 열린다.**

## 수리 ② 고아 스윕을 스케줄러로, 라벨 단위로

`graph_materializer._retarget_stale_edges`는 **엣지**를 지우고, 엣지가 남긴 노드를 지우는 것은 아무 데도 없다. 그래서 **정체를 바꾸는 셀 편집마다 노드가 새는데** — lot 이름을 `LOT-A`→`LOT-B`로 교정하면 엣지는 충실히 재타깃되고 `Core(LOT-A|05)`가 degree 0으로 영원히 남는다. 라이브 실측 **12,761개**.

**라벨 단위인 것이 규칙이다.** 거절된 라벨이 나머지를 막으면 안 된다 — 은퇴한 `Chip` 노드 **12,468개**가 진행 중인 편집당 누수를 영원히 인질로 잡는다. 매 사이클이 **가져간 것과 물러난 것을 분수와 함께** 둘 다 로그한다. 넘긴 집합이 안 보이는 스윕은 "할 일이 없다"로 읽힌다.

고아 정의는 **두 조건 모두** 필요하다: ① 엣지 0개 **그리고** ② 현재 매핑된 어떤 테이블도 그 `(label, identity_key)`를 만들 수 없다. ②가 안전을 만든다 — 엣지 0개만으로는 고아가 아니다(`SplitCondition`의 평균 degree가 ~0.2다. DOE 어휘 대부분이 엣지가 없고, 엣지 0 스윕은 **어휘를 지운다**). 생산 가능성은 materializer가 쓰는 **바로 그 `compose_identity`**로 판정한다 — 이 모듈이 표류하는 두 번째 정체 구현이 되지 않게(이 저장소는 좌표 변환에서 그 값을 두 번 치렀다).

형태는 `config_backup`에서 복사했다 — **수집기가 아니라 유지보수 작업**이기 때문이다. 수집기는 테이블별이고 그 테이블의 `raws/`에 CSV를 쓰며, 산출이 없으면 설계상 FAIL을 보고한다.

**네 번째 가드가 load-bearing이었다**: 온톨로지 선언이 깨끗하게 로드되지 않으면 스윕은 **전면 거부한다.** 이것이 다른 두 항목이 함께 만드는 복합 실패다 — 컬럼 하나를 rename하면 그 테이블 매핑이 조용히 통째로 빠지고, 그 테이블이 만들던 모든 라벨이 생산 불가로 보이며, 분수 가드는 큰 라벨을 잡지만 `min_population` 아래 라벨은 **놓친다.** 그래서 의심스러운 선언은 결론 일부가 아니라 **판정 자격 자체를 잃는다.** 거절 수집기를 끈 변이가 테스트에서 **생산 가능한 노드 3개를 삭제했다.**

## 수리 ③ 거부된 매핑을 표면에 싣는다

로더의 계약은 "무효 테이블은 로깅 후 스킵"인데, 그 스킵이 로그에만 있으면 **컬럼 하나 rename에 그 테이블의 온톨로지가 통째로 사라지고 표면에는 아무 것도 안 나온다** — 성공 개수만 보면 "안 늘었다"와 "죽었다"가 구별되지 않는다.

`/graph/mapping-summary`에 `rejected[{scope, table, reason}]` · `rejected_count` · `source{path, exists}`를 실었다. **파일 부재는 `source.exists`로 보고하고 거부로 세지 않는다** — 정상 상태에서도 비어있지 않은 사유 목록은 일주일 안에 무시당한다. `tables`의 형태는 바뀌지 않았다(가산 필드).

수집기는 **선택 인자**다. 기존 호출자(materializer·resync·고아 스윕) 전부가 시그니처와 비용을 그대로 유지하고, 표면이 있는 한 호출자만 리스트를 넘긴다.

## 수리 ④ QA HIGH — 503이 아니라 다섯 번째 다리별 상태

`8670e3b`의 chip-trace는 매핑 파일이 저장 중일 때(`json.load` 실패 → `raw_config = {}`) **200과 함께 전 다리 `not_declared`**를 답했다 — 즉 `graph_edges`에 `BONDED_TO` 엣지 3개가 앉아 있는 칩에 대해 "`BONDED_TO->BaseCell`은 더는 선언되지 않았다"고 **주장**했다. 그 창은 도달 가능하다: `main.py`의 config writer들이 temp+rename이 아니라 그냥 `open(..., "w")`를 쓴다.

**503을 쓰지 않은 이유**: 여전히 참인 절반을 버린다. 엣지는 `graph_edges`에 있고 walk는 계산 가능하며, 답할 수 없는 것은 "이 형태가 지금 선언돼 있나" 하나뿐이다. 그리고 읽기 전용 멱등 요청에서 호출자는 **무엇을 위해** 재시도할 것이 없다. 이 엔드포인트의 전제가 **닫힌 다리별 어휘**이므로, "미상"의 정직한 자리는 그 어휘 안이다.

**`not_declared` 정확히 하나만 강등된다** → `mapping_unavailable`. 그것이 **선언의 부재에 대해 주장하는 유일한 상태**다. `recorded`·`none_recorded`는 실제로 읽은 행에서 나온 결론이라 config 파일이 무엇을 하든 참으로 남는다.

죽은 앵커 뒤의 종단은 `not_reached` + `blocked_by`라고 말한다 — 종전에는 `PERFORMED_ON`을 rename하면 `events`는 옳게 `not_declared`인데 모든 종단이 `USED_KNOB: none_recorded, count 0`을 보고했다. **knob 질의가 돌지도 않았는데 "이 웨이퍼는 knob을 쓰지 않았다"**다.

절단된 스코프의 승자 선택도 닫았다 — 다리가 `(identity_key, edge id)` 순으로 cap+1을 가져오므로, `LOT-A|05`로 향한 주장 201건이 `LOT-Z|01`로 향한 주장 한 건을 읽기 전에 버퍼를 채운다: 길이 1 · 스코프 `resolved` · **웨이퍼 절반 전체가 틀린 코어로** 계산된다. 그래서 `not truncated`가 필수 연접항이 됐다.

그리고 결합된 두 cap의 관계를 **import 시점에 assert**했다 — 주석으로 두면 한 숫자만 고쳐서 깨진다.

```python
assert GRAPH_CHIP_TRACE_EVENT_CAP <= GRAPH_CHIP_TRACE_ID_CHUNK, (
    "chip-trace anchor sets must fit in one IN-list chunk, or the leg's truncation "
    "order is no longer (identity_key, edge id) - see _chip_trace_leg"
)
```

## 검증

신규 테스트 29건(`test_ontology_reload_and_sweep.py`) + `test_chip_trace_api.py`에 8건 추가. 테이블·라벨 이름은 사용자 실 config에 실존 불가능한 `sweep_test_`/`Sweep` 접두를 쓴다(conftest가 import 시점에 실 config를 선점하는 공유 sqlite 함정). enrichment 경로까지 격리 경로로 갈아끼웠다 — 안 하면 로더가 **사용자의 실 규칙 파일**을 읽어 `rejected` 목록에 실 사이트 사유가 섞인다.

스위트: 이 커밋 착지 후 **1398 passed**(직전 `6422326` 기준선 1361 + 37). 소급 확인 — HEAD(`ae2811c`, 클라 전용 커밋이라 서버 스위트 동일)에서 `conda run -n assy_manager python -m pytest server/tests/` **1398 passed / 3분 38초**.

## 그때 남아 있던 것

- 잔여 창은 resync의 백그라운드 작업 소요 시간 그대로다(실측 4초).
- 파일 감시자는 **채택되지 않은 상태로 남았다** — 진짜 블로커(`ConfigChangeHandler`의 단일 타이머 슬롯)는 이 커밋에서 손대지 않았다.
- `main.py`의 config writer가 temp+rename이 아니라 `open(..., "w")`인 것은 그대로다 — `mapping_unavailable`이 존재해야 하는 이유가 그것이다.
- 스윕 기본 주기는 24시간, 확인 주기는 30분, 끄는 스위치는 `GRAPH_ORPHAN_SWEEP_ENABLED`다. 라벨 인구의 50% 초과 삭제는 기본 거부이므로 `Chip` 12,468개 정리에는 명시적 `--max-fraction`이 필요한 상태로 남았다.
