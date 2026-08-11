# The job column name now comes from config, and the `dt_job` default is gone

**Date:** 2026-08-11 13:10 · **Domain:** Server (chain ingestion) · **Status:** implemented, not committed

---

## 현상

운영 시스템의 `dt_log`에는 `dt_job` 컬럼이 **없다**. `dt_job_id`다. 그런데
`dt_job_id`는 이 저장소의 **어느 실행 코드에도 존재하지 않는다** — 코드가 운영의
이름을 한 번도 배운 적이 없다.

그리고 아무도 그것을 몰랐다. 이 트리의 **모든 픽스처가 `dt_job`을 쓰기 때문**이다
(`trace_fixture/world.py`, `emit.py`, 시드 스크립트, 매퍼 테스트 전부). 고친 코드와
안 고친 코드가 **같은 초록**을 냈고, 죽는 것은 운영뿐이었다.

## 근본 원인

매퍼가 잡 컬럼 이름을 두 가지 형태로 들고 있었다.

1. **리터럴** — `_value(payload, "dt_job")`, `getattr(row, "dt_job", None)`,
   `required = ("dt_job", ...)`, `"dt_job": job_id`(출력 키), `"scope": {"dt_job": job_id}`.
2. **리터럴 기본값** — `rule.get("job_column", "dt_job")`,
   `rule.get("reference_job_column", "dt_job")`, `DEFAULT_SOURCE_COLUMN = "dt_job"`.

②가 ①보다 나쁘다. 개발 박스에서 항상 맞으므로 **아무도 진짜 이름을 선언할 이유가
없고**, 그래서 운영이 다른 철자를 쓴다는 사실이 영원히 드러나지 않는다.

그리고 양쪽 끝이 전부 **조용히** 실패한다.

- **읽기** — `_value(payload, "dt_job")`는 페이로드에 없는 이름에 `None`을 준다 →
  그 행을 스킵 → **빈 배치**를 돌려주고 워커는 **SUCCESS**를 기록한다. 몇 줄 아래의
  시끄러운 `source.dt_job` `AttributeError`는 **도달하지 않는다** — 조용한 읽기가
  먼저 반환했기 때문이다.
- **쓰기** — `crud.apply_batch_updates`가 대상 테이블의 `column_types`에 없는
  `updates` 키를 **드롭하고**, `(테이블, 컬럼)`당 프로세스 1회만 경고하고,
  **쓰기는 성공을 반환한다**.

체인 셋이 에러 하나 없이 죽어 있을 수 있었다.

## 해결

**`server/chain_bindings.py` 신설**(추적됨 — `server/mappers/*.py`는 gitignore라
헬퍼를 매퍼 옆에 두면 배포에 도달하지 못한다). 우선순위 하나:

```
룰 선언  >  table_config 유도  >  이름을 대고 거절
```

관례 폴백 없음 — `68db020`이 맵 좌표 바인딩에 세운 규율과 같다.

```python
def resolve_column(rule, key: str, table: str, purpose: str) -> str:
    """The column of `table` that carries the job, for this rule. No literal default."""
    declared = rule.get(key)
    if isinstance(declared, str) and declared.strip():
        ...                                    # 선언이 이긴다 (미선언 컬럼이면 거절)
    name, origin_or_why = identity_column(table)
    if name is None:
        raise ColumnBindingRefused(
            "chain rule '%s' does not declare '%s' and it cannot be derived: %s. "
            "Declare '%s' on the rule in chain_rules.json, or give '%s' a "
            "single-column 'map_key_columns' in table_config.json. Refusing instead of "
            "assuming 'dt_job' ...")
```

유도(`identity_column`)는 **`dt_map_derivation.identity_columns`를 재사용**해
체인과 dt_map 파생이 구조적으로 같은 답을 내게 했다(두 번째 유도기를 만들지 않았다).
한 컬럼짜리 `map_key_columns` → 그것, 없으면 `composite_key_source`가 없는 테이블의
한 컬럼짜리 `business_key` → 그것. 둘 다 아니면 거절.

**테이블마다 따로 묻는다.** 매퍼 하나가 트리거 페이로드를 읽고, 소스를 쿼리하고,
타깃에 쓴다 — 테이블 셋이고 철자도 셋일 수 있다. 리터럴 하나로는 표현할 수 없던
설정이다.

```python
# dt_standard_map_mapper — 세 이름이 전부 따로 해석된다
trigger_job_column = chain_bindings.resolve_column(rule, "trigger_job_column", rule.get("trigger_table"), ...)
source_job_column  = chain_bindings.resolve_column(rule, "source_job_column",  source_table, ...)
target_job_column  = chain_bindings.resolve_column(rule, "target_job_column",  target_table, ...)
...
"scope": {target_job_column: job_id},          # 삭제를 결정하는 유일한 출력 키
```

라이브 config에서는 **어떤 선언도 추가할 필요가 없다** — 여섯 자리 전부
`table_config.json`에서 유도된다(`dt_log`/`dt_map`은 `map_key_columns`,
`dt_inventory`는 한 컬럼짜리 `business_key`). 운영은 `table_config.json`에서 이름을
**한 번** 바꾸면 네 체인이 따라온다.

## 검증

- **HEAD 기준선**(손대기 전 실측, 매퍼 관련 8파일): **2 failed / 81 passed**.
- **변경 후 같은 8파일 + 신규 파일**: **2 failed / 99 passed** — 실패 둘은 동일한
  기존 빨강(`dt_alignment_metadata_mapper` 라이브/샘플 드리프트, 샘플의 dt_map 룰
  개수). 신규 실패 0.
- **반경 18파일**: **2 failed / 291 passed / 1 skipped** — 같은 둘.
- 🔴 **변이 검사** — 리터럴 셋(`_value(payload, "dt_job")` ·
  `"dt_job": job_id` · `getattr(row, "dt_job", None)`)을 되돌리자
  `test_job_column_from_config.py`가 **6 failed / 12 passed**. 여섯 전부 다른 철자를
  쓰는 테스트다. **되돌린 코드는 예외를 던지지 않는다 — 전부 조용히 실패한다.**
- **`replace_map` 스코프 실측**(`crud.derive_replace_map_scope`, 직접 호출):
  명시 스코프에 미선언 키 → **DELETE가 조립되기 전에 `ValueError`**. 삭제 불가.
  유도 경로는 `map_key_columns`가 하나면 `None`(거절), **둘 이상이면 빠진 필터를
  조용히 빼고 나머지로 삭제한다 — 필터가 하나 모자란 것은 더 넓은 삭제다.**
  `dt_map`·`core_usage_map`은 맵 키가 하나라 해당 없음. 이번 변경 범위 밖이며 고치지
  않았다.

## 배포 주의

`server/mappers/*.py`는 운영자 자산이고 `.sample`만 배포된다. **샘플을 활성 매퍼 위에
통째로 덮어쓰면 운영자가 직접 넣은 컬럼 이름 수정이 조용히 되돌아간다.** 활성 파일이
직전 샘플과 바이트 동일한지 먼저 확인한 뒤에만 복사한다.

`server/chain_bindings.py`는 추적 파일이라 `git pull`로 도달한다.
