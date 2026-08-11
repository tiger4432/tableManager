# 수리 패스가 아웃박스에 사람의 이름표를 달고 있었다 — 그래서 사람이 깨우는 체인을 전부 깨웠다

**날짜:** 2026-08-11 18:05 · **커밋:** `ffb23d6` · **레인:** 서버(chain_replay)
**측정 상자:** 격리 스택(`:8081` / `assy_qa`) + 브라우저. **운영이 아니다.**

---

## 배경

두 시간 전 `8024235`의 측정이 「R3는 아웃박스 이벤트를 내지 않는다」를 **뒤집었다.**
그 이벤트들이 무엇을 달고 나갔는지가 이 커밋의 문제다.

R3(`recompute_display_values`)는 **이미 이긴 레이어를 물질화한다.** 새로 쓰는 것도 없고
결정하는 것도 없다. 그런데 이벤트가 `source_name="user"`, `updated_by="system"`,
그리고 **이벤트마다 새 uuid4**를 달고 나갔다 — 하류에서 **누군가 그리드에 타이핑한 것과
구별되지 않는다.** `dt_log` 행 하나의 셀 하나를 수리하면 enrichment 매퍼 둘이 돌고,
체인 배치 업데이트가 두 테이블에 쓰이고, 자동 확정 패스가 돌았다(438 ms, 422 ms 두 번 측정).

## 무엇을 했나

`chain_ingestion`으로 라벨링해 **R1이 이미 가진 규칙별 옵트인**
(`_rule_accepts_event`, `chain_ingestion_worker.py:328`) 아래로 넣었다.

```python
    with crud.transaction_context(R3_AUDIT_SOURCE, tx_id, R1_SOURCE_NAME):
        for page in keyset_scan.iter_pages(db, model, condition=condition,
                                           chunk_size=chunk_size, limit=limit):
```

**억제가 아니라 옵트인이다** — `allow_chain_trigger`를 선언한 세 규칙은 여전히 이 이벤트를
받는다. 새 리터럴이 아니라 `R1_SOURCE_NAME`을 쓴 이유도 기록할 값이 있다: 필터가 그
문자열을 정확히 비교하므로 **두 번째 철자는 R3를 하류 규칙 전부에 조용히 다시
옵트인시킨다.**

| 같은 수리 실행 | 전 | 후 |
|---|---|---|
| 이벤트 | 5 | 5 |
| 라벨 | `user` / `system` | `chain_ingestion` / `resolution_recompute` |
| transaction id | **5개** | **1개** |
| 수락한 규칙 | 5 | **0** |
| 쓰인 타깃 테이블 | 4 | **0** |

**transaction id 붕괴가 같은 문장에서 나왔고 그것이 비싼 절반이다.** 워커가 transaction
id로 묶으므로 이벤트당 id 하나는 **수리된 N행 = 직렬화된 N개의 약 430 ms 그룹**을
뜻했다 — 10,000행이면 대략 72분이고 라이브 인제션이 그 뒤에 줄을 선다.

## 둘 다 참일 수 없어 보이던 두 사실

`_apply_replay_batch`는 **페이지당 transaction id 하나**를 세팅한다. 그런데 201개의
이벤트가 **201개의 서로 다른 uuid4**를 달고 있었다.

둘 다 정확했다. **R3는 그 헬퍼에 도달하지 않는다 — 그건 R1의 것이다.** R3는 맨몸
`setattr`으로 쓰므로 이벤트가 `database.py:127`의 **전역 `before_flush`**가
`session.dirty`를 훑으며 스테이징하고, 세 필드는 `_outbox_envelope`가 읽는 컨텍스트
기본값에서 온다. 거기의 `request_transaction_id.get() or str(uuid.uuid4())`가 **문자 그대로
이벤트마다 uuid4가 태어나는 자리**다.

**함수를 읽어서는 아무도 못 찾았을 것이다. 모순을 반올림 오차가 아니라 질문으로 취급해서
찾았다.**

## 총괄이 「여기서 멈추라」고 지목한 위험은 없었고, 없는 것이 구조적이다

`source_name`은 레이어를 **만드는** 필드다(`crud.py:2200/2225/2230`). 그래서 재라벨링이
수리된 셀마다 `chain_ingestion` 레이어를 조용히 **추가**할 수 있었다 — 원래 결함보다
나쁘고 초록 테스트에서는 보이지 않는다.

그렇지 않았고, **운이 아니다.**

- 레이어는 `update_item.source_name` — 항목별 pydantic 필드.
- 라벨은 `request_source` — 비테스트 트리 전체에서 **유일한 독자가 `_outbox_envelope`**.
- 둘이 만나는 곳은 **정확히 한 줄**, `_apply_batch_updates_once`가 배치를 컨텍스트로
  복사하는 자리다. **R3는 그것을 호출하지 않는다.**

논증이 아니라 측정으로 닫았다 — `cell_sources` 전체 스냅샷의 **sha256이 전후 동일**하고
`test_recompute_creates_no_cell_sources_layer`가 고정한다.

컨텍스트 스코프가 커밋이 아니라 **페이지 루프**인 이유도 같은 결의 사실이다: 다음 페이지의
keyset 쿼리에서 autoflush 한 번이면 스테이징되기에 충분하다.

## 세 라이브 경로 — 새 인수 기준의 첫 적용

`d311694`가 올린 기준(브라우저 편집 · 체인을 실제로 돌리는 쓰기 · 워처를 통과하는 파일)이
실제로 돌아간 첫 레인이다.

- **브라우저 그리드 편집(8081)** — 진짜 편집: `source_name='user'`, `updated_by='kk980'`,
  `user` 레이어 하나, 체인이 375 ms에 올바르게 캐스케이드. **그게 R3가 요청받지 않고
  발화시키던 바로 그 캐스케이드다.** 셀은 복구했다.
- **인제션** — 실제 핸들러를 통과. 라벨은 파일명이고 레이어는 파일 이름을 딴다.
- **누출 테스트** — 셋을 **한 프로세스 안에서** R3를 가운데 두고 돌렸다. 운영보다
  적대적인 배치다. R3 뒤의 그리드 편집과 인제션이 동일한 라벨·레이어를 냈다.

그리고 레인이 **자기 하네스의 결함 둘을 발견으로 출하하지 않고 고쳤다.**

- 마커 위치가 **자기 시드 레이어를 R3에 귀속**시키고 있었다.
- 바이트 동일 재인제션은 signature dedup에서 no-op이 되는데 — **그것이 깨끗한 통과처럼
  읽힌다.** R3를 뺀 대조군 실행이 접미사 붙은 레이어 이름은 인제션 경로 자신의
  것임을 확인했다.

## 변이 채점 — 침묵과 동의를 가르는 테스트

M2/M3/M4가 각각 가드 하나씩을 죽인다. **두 번째 가드가 중복이 아닌 이유는 M4, 억제
변이다** — R3의 이벤트를 옵트인으로 만드는 대신 **떨어뜨리는** 「수리」는 첫 가드를
통과하고 둘째에서 죽는다. **침묵과 동의의 차이**이고, 그것을 구별할 수 있는 테스트는
하나뿐이다.

## 검증

- 신규 테스트 **4건**을 diff에서 직접 확인했다 —
  `test_recompute_events_are_labelled_so_the_loop_filter_can_see_them`,
  `test_a_rule_that_opted_in_still_consumes_a_recompute_event`,
  `test_recompute_stages_one_transaction_id_for_the_whole_run`,
  `test_recompute_creates_no_cell_sources_layer`.
- 🔴 **이 커밋의 본문은 스위트 총계를 적지 않았다.** 하네스 게이트 수치도, 서버 스위트
  전후 수치도 없다. 있는 것은 위의 라이브 경로 실측과 변이 채점이다. 나는 이 시점에
  같은 트리를 여러 레인이 잡고 있어 재실행하지 않았다.

## 그때 남아 있던 것

- **R2에 동일한 결함이 있고 여기서 고쳐지지 않았다.** 실측: 철회 4회 → 이벤트 4건,
  `user`/`system`, 각각 uuid4 하나, 같은 4개 타깃 테이블이 수락. **R3보다 중요하다** —
  R3는 CLI 앞에 사람이 필요하지만 R2는 `retroactive.py:371`의 관리자 라우트에서 도달
  가능하다. 접어 넣지 않고 판정 대기로 남겼다.
- 브라우저 편집은 **이 변경 이전에 시작된 서버 프로세스**에 대해 돌았다. 가정하지 않고
  이유를 확인했다 — 서버 쪽 호출자 중 R3에 닿는 것이 없다(`retroactive.py`는
  `replay_rule`(R1)과 `withdraw_source`(R2)를 부르지 `recompute_display_values`를
  부르지 않는다).
- R3의 수리는 **이 변경 전에도 후에도 그리드로 push되지 않는다.** 워커는 체인이 **쓴
  것**을 브로드캐스트하고, 메시지 없는 그룹은 즉시 `broadcast_at` 도장을 받는다.
</content>
