# "아무것도 교체하지 않고 200" — replace_map이 정직해졌다

> 커밋 `deed6d2` · 2026-07-28 21:34 · 도메인 Server(crud replace_map · batch API 계약)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 계약: [data_model](../architecture/data_model.md)
> **동반 항목**: [관문 4](./20260728_213436_gate4_log_shaped_push_structural_discriminator.md) · [self-frame 유령 형제](./20260728_213700_self_frame_fail_count_only_sibling.md) · [PM 헌장 등재](./20260728_214100_pm_charters_gain_ops_docs.md)

## 배경 — 침묵하는 noop은 성공보다 나쁘다

`map_key_columns`가 선언되지 않은 테이블에 replace_map을 보내면, 종전 코드는 purge
필터를 도출하지 못한 채 **삭제를 조용히 건너뛰고 200을 반환**했다. 호출자는
"교체됐다"고 믿고, 실제로는 매 push마다 행이 누적된다 — 실패가 성공의 응답 코드를
입고 있었다. 반대 극단도 표현 불가였다: "이 범위를 비우고 싶다"(전량 삭제, 삽입 0)는
정당한 의도를 API가 말할 방법이 없었다.

## 변경 내용

### 리졸버 하나, 진실 하나

purge 범위 도출을 순수 함수 `derive_replace_map_scope`로 뽑아내고, **삭제하는 쪽(crud)과
보고하는 쪽(API 응답)이 같은 함수를 호출**하게 했다 — 클라이언트가 들은 범위가 곧
삭제된 범위다(양쪽이 따로 계산하면 언젠가 어긋난다). 범위를 도출하지 못하면 noop이
아니라 거절이다:

```python
# crud.py — apply_batch_updates, 이 커밋 시점
scope_filters = derive_replace_map_scope(table_name, batch)
if not scope_filters:
    raise ValueError(
    f"replace_map on '{table_name}' could not derive a purge scope: "
    f"declare 'map_key_columns' in table_config and send their values in the "
    f"payload (or pass an explicit 'scope' object). Refusing instead of "
    f"silently replacing nothing.")   # -> API 계층에서 400
```

**noop 감사가 착수 조건이었다**: 400 전환은 침묵-200에 의존하던 호출자가 있으면
그쪽을 깨뜨린다. 전 호출처 감사 결과 noop에 기대던 코드는 없었다 — 그래서 이 전환은
행동 변경이 아니라 결함 노출이다.

### 명시적 scope — 전량 삭제가 말할 수 있게 됐다

`batch.scope`(명시적 `{컬럼: 값}`)가 추가됐다. 명시 경로의 검증은 파생 경로보다
**일부러 엄격하다**: 선언 밖 컬럼·모델에 없는 컬럼·빈 값 전부 ValueError다 — 필터
하나를 조용히 떨어뜨리면 DELETE가 **넓어지기** 때문에, 이 경로에서는 아무것도
건너뛰지 않는다. 반면 파생 경로(updates[0]에서 도출)는 모델에 없는 config 컬럼을
종전대로 스킵한다(스키마 롤아웃 중의 일시적 불일치 허용). 같은 함수 안에서 관용의
방향이 경로별로 다른 이유가 각각 주석에 남아 있다.

명시적 scope + 빈 updates = **의도된 범위 전량 삭제** — 이제 `deleted: N, inserted: 0`
으로 정직하게 응답된다. 응답에는 `scope: {filters, deleted, inserted}`가 실려,
"교체를 기대했는데 deleted 0"을 호출자가 감지할 수 있다.

### 지나는 길에 잡힌 둘

- **순수 wipe의 카운트 캐시**: 캐시 무효화가 `if results:`(upsert 존재)에만 걸려 있어,
  삭제만 하고 삽입이 없는 wipe 후 행 수 캐시가 죽은 값을 서빙할 참이었다 —
  `deleted > 0`도 무효화 조건에 추가.
- **purge된 row id의 재바인딩**: 종전 코드는 purge 결과를 `deleted_row_ids`에 담았지만
  이후 값-삭제 경로가 같은 이름을 다시 바인딩해 반환 전에 사라졌다 — purge 결과가
  응답에 실린 적이 한 번도 없었던 것. `purged_row_ids`로 분리해 `scope.deleted`
  카운트로 보고한다.

## 검증

- 신규 `test_replace_map.py`(+155줄): 파생/명시 범위 · 검증 거절 각축 · erase-all ·
  scope 응답 · noop 400. 전체 스위트 893 passed (conda `assy_manager`).
- 같은 야간 배치에서 DB 성능 인덱스가 **로컬 라이브 DB에** 적용됐다(concurrent·멱등,
  이 커밋의 diff 밖 운영 작업) — 운영 DB 적용은 전달된 런북에 따라 미실행 상태였다.

## 그때 남아 있던 것

- purge된 행은 `scope.deleted` **카운트로만** 보고됐다 — row id 목록의 WS 브로드캐스트
  (다른 클라이언트 화면에서 교체-삭제된 행이 사라지게)는 후속 작업으로 큐에 있었다.
  즉 이 커밋 시점, replace를 수행하지 않은 클라이언트는 purge를 실시간으로 알 수 없다.
