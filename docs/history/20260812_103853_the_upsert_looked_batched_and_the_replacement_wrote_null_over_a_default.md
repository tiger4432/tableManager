# The upsert looked batched, and the path that replaced it wrote NULL over a default

**Date:** 2026-08-12 10:38 · **Domain:** Server (쓰기 경로 / 벌크 업서트) · **Status:** 착지 — `ab008ec` `ed11590`

> 두 커밋이 **한 이야기**다. 앞 커밋이 1년 묵은 왕복 결함을 걷어냈고, 뒤 커밋은 그 수리가
> **데이터를 조용히 손상시키던 입력 하나**를 막았다. 이 항목의 중심은 뒤쪽이다.
>
> ⚠️ **아래 모든 수치는 격리 `assy_qa`와 이 개발 워크스테이션 실측이다. 운영 수치가 아니다.**

---

## 배경 — 배치처럼 생겼고 배치가 아니었다

`db.execute(stmt, param_list)`. 파라미터 «리스트»를 넘기니 배치 전송으로 읽힌다.
아니었다.

SQLAlchemy 2.0은 파라미터 리스트를 `insertmanyvalues`로 보내는데, `insertmanyvalues`는
`excluded`를 참조하는 `ON CONFLICT DO UPDATE`를 **거절한다.** 남는 것은
`cursor.executemany`이고, psycopg2의 `executemany`는 `cursor.execute`를 도는 **파이썬
루프**다 — 행마다 서버 왕복 한 번.

**논증이 아니라 계수로** 세웠다. 드라이버 호출을 세는 `cursor_factory`로 20,000 매핑을
태웠다.

| | execute | executemany | 파라미터 세트 |
|---|---|---|---|
| `db.execute(stmt, chunk)` | 0 | 20 | **20,000** |
| 새 경로 | **20** | 0 | 0 |

그 자리의 `compiled.insertmanyvalues`는 `False`인데 dialect는 `use_insertmanyvalues`를
`True`로 광고하고 있었다. **켤 수 있다고 말하는 스위치와 실제로 켜진 문장은 다른 것이다.**
그리고 이 착각을 굳혀 준 것은 다름 아닌 **그 자리의 주석**이었다 — psycopg2가 executemany를
멀티행 INSERT로 다시 쓴다고 적혀 있었고, 그 문장이 1년 동안 그 코드를 읽은 사람마다
「여긴 이미 배치다」로 되돌려 보냈다.

## 진짜 수리는 문장 하나였다

```python
one_row = "(" + ",".join(["%s"] * len(keys)) + ")"
conn = db.connection()
for chunk in _chunks(mappings, chunk_size):
    sql = head + ",".join([one_row] * n) + tail
    flat = []
    for m in chunk:
        for k, p in zip(keys, procs):
            v = m[k]
            flat.append(p(v) if p is not None else v)
    conn.exec_driver_sql(sql, tuple(flat))
```

`procs`(컬럼별 bind processor)가 값이 «동일하게» 착지하는 유일한 이유다 —
`cell_sources.value`는 JSON 컬럼이고 그 프로세서가 없으면 생 문자열이 유효한 json이 아니라
문장 자체가 실패한다. 읽어서가 아니라 **오라클로** 확인했다: 같은 2,000 매핑(str / int /
None / 중첩 dict)을 양쪽 경로로 써서 7개 컬럼 전부, `value::text` 포함 **바이트 동일**.

| | before | after |
|---|---|---|
| `bulk_upsert_cell_sources`, 100k 매핑 | 31.221 s | 7.815 s |
| `bulk_upsert_cell_overwrites`, 동일 | 29.173 s | 6.910 s |
| `PUT /tables/dt_log/data/updates` 2,000행 (라이브 스택) | 26.149 s | 11.894 s |
| 파일 인제션 → SUCCESS, 2,000행 | 15.7 s | 7.9 s |

**HTTP 요청 «전체»에서 절반이 깎였다.** 고친 부품에서만이 아니다.

## 왜 ORM 안에 남았는가 — 그리고 그 이유가 처음엔 틀렸었다

`psycopg2.extras.execute_values`는 **같은 속도**(1.21 s 대 1.19 s)였고 그래도 거절됐다.
`ab008ec`이 그 거절에 붙인 이유는 둘이었고, `ed11590`이 **둘 다 실측으로 반증했다.**

- 「`apply_batch_updates`의 업무키 복구가 눈이 먼다」 — **여기서는 멀게 할 수 없다.** 이
  헬퍼는 `cell_sources`·`cell_overwrites`만 쓰고, **두 표 모두 `business_key_val` 컬럼이
  없다**(`information_schema.columns` 0행).
- 「세션이 트랜잭션이 상했다는 것을 모르게 된다」 — **고른 경로에서도 모른다.** 동일한
  NOT NULL 고장을 세 갈래에 주입해 재 봤더니 `is_active`는 계속 True이고 `db.commit()`은
  **아무것도 안 쓴 채 성공을 반환**한다.

살아남은 이유는 **하나뿐**이고 그건 측정된 것이다: 이 프로젝트에서 세 자리가
`sqlalchemy.exc.IntegrityError`를 **클래스로** 잡는데(`record_interaction_effort`,
`apply_batch_updates`, `main.py`의 배치 업데이트 엔드포인트 — 마지막 것이 이 헬퍼가 실제로
먹일 수 있는 자리이고 그 클래스를 500이 아니라 409로 바꾼다), 생 커서는
`psycopg2.errors.NotNullViolation`을 던지고 **`except IntegrityError`는 그것을 못 잡는다.**

**같은 결론에 도달한 두 개의 서로 다른 이유**이고, 앞의 둘은 거짓이었다. 거짓 근거로 옳은
결론을 지켜 두면 다음 사람이 그 근거를 반증하고 제약이 장식이라고 판정한다.

## 중심 — 기본값 컬럼에 `None`이 오면 NULL이 써졌다

`ab008ec`의 가드는 「기본값 있는 컬럼을 매핑이 **생략**했는가」만 봤다. SQLAlchemy는
**값이 `None`일 때도** 그 컬럼을 문장에서 빼서 DB가 기본값을 적용하게 한다. 새 경로는
`mappings[0]`의 키를 **전부** 이름 붙여 보내므로 그 `None`이 **리터럴 NULL**이 됐다.

```python
for k, col in zip(keys, cols):
    if col.default is None and col.server_default is None:
        continue
    if any(m[k] is None for m in mappings):
        _warn_upsert_fastpath_declined_once(
            table.name, "defaulted_column_is_none",
            f"column '{k}' carries a default and at least one mapping supplies it "
            f"as None, which the fallback stores as the DEFAULT and a raw statement "
            f"would store as NULL")
        return False
```

컬럼이 아니라 **매핑 키**를 훑는다 — 실제로 시험되는 것이 매핑 키이기 때문이다
(`Column.key`가 `Column.name`과 같을 필요가 없다). `server_default`도 센다: PostgreSQL의
`now()`는 파이썬에서 재현할 수 없으므로 **되돌려주는 것이 유일하게 성실한 답**이다.

세 가지가 이 결함의 무게를 정한다.

1. **`DO UPDATE` 갈래에서도 문다.** 삽입만이 아니다. `is_overwrite=true`로 심어 둔 행이
   NULL로 돌아왔고, `ingested_at=2020-01-01`도 NULL로 돌아왔다. **이미 저장된 참값을
   덮어썼다.**
2. **손상은 청크 단위가 아니라 «행» 단위다.** 실값 500개 사이의 `None` 하나가 정확히 그
   한 행만 망가뜨리고 나머지 500행은 멀쩡하다. **알아채기 가장 어려운 모양이다.**
3. `cell_overwrites.is_overwrite`가 NULL이면 falsy로 읽혀 **수동 정정이 자동 레이어를
   이기게 하는 표식이 조용히 은퇴한다.**

오라클 10케이스는 **시계값이 아니라 시험 대상 성질에 정규화**해서 채점했다: 이전 6/6 발산,
이후 0/10. 가드를 소스에서 지우면 10 중 8이 빨개지고 대조군 둘은 초록으로 남는다 —
**이 오라클이 이 가드에만 민감하고 아무것에나 민감한 것이 아니라는 증거다.**

그리고 빠른 경로를 잃지 않았다. 뜨거운 생산자 둘은 dict를 만들기 **직전에**
`datetime.now()`를 넣으므로 인제션과 맵 푸시는 `None`을 싣지 않는다 — 운영 모양의 2,500
매핑에서 `accepted=2 declined=0`. `None`을 실을 수 있는 것은 `delete_cell_source_batch`
하나이고, 그 거절은 NULL `updated_at`을 `now()`로 치유하던 **커밋 이전 동작을 복원한다.**
스캔 비용 100,000 매핑당 18.8 ms.

## 조용한 거절은 조용한 붕괴다

`return False` 자리 셋에 로그가 **하나도 없었다.** 컬럼에 `default=`를 하나 붙이면 그
표의 모든 쓰기가 7.8 s에서 31.2 s로 **아무 흔적 없이** 되돌아간다. 운영자는 「인제션이 또
느려졌다」를 부하와 구별할 방법이 없다.

```python
# Once per (table, REASON CODE) per process, deliberately not per (table, column): the
# reason codes are a closed vocabulary of four, while column names come from the caller's
# mapping keys, and a registry keyed on those is the unbounded growth
# `_undeclared_column_warned` needs a budget for. The offending column is named in the
# MESSAGE, so the first announcement is still actionable; a second column failing the same
# way on the same table is silent, which is the price of the bound.
_upsert_fastpath_declined_warned = set()
```

**대가를 적어 둔 것이 중요하다** — 같은 표에서 같은 방식으로 두 번째 컬럼이 실패하면
조용하다. 그것이 무한 증식을 막는 값이다.

## 되돌린 주장 — 32,767 바인드는 이 드라이버에서 한계가 아니다

`BULK_CHUNK_SIZE` 옆에는 「와이어 프로토콜이 파라미터 개수를 int16로 실으므로 32,767을
넘길 수 없고 psycopg2가 보내기 전에 거절한다」가 적혀 있었고 **1년 동안 correctness bound로
믿어졌다.** psycopg2는 파라미터를 **클라이언트 쪽에서 보간**해 완성된 SQL 문자열 하나를
보낸다 — `cursor.mogrify("SELECT %s, %s", ("a", 1))`은 `b"SELECT 'a', 1"`이다. 바인드
파라미터가 와이어를 건너지 않으니 그 int16 한도는 **조회되지도 않는다.** 재측정: 12,000행 ×
7컬럼 = **84,000 바인드 한 문장이 수용되고 12,000행이 전부 저장됐다.**

**상수는 그대로 남았고 이유가 바뀌었다** — 문장 텍스트 크기와 `mogrify` 메모리(1,000행 =
23 KB 템플릿 → 135 KB, 12,000행 = 276 KB → 1.6 MB), 락 지속 시간과 롤백 단위(멀티행
VALUES는 실패하면 자기 청크의 **0행**을 적용하는데 그것이 대체한 executemany는 K−1행을
적용해 두었다), 그리고 SQL 캐시가 재사용할 청크 모양. 셋 다 절벽이 아니라 거래다.

## 새로 생긴 전제 — 이건 이전 전송이 참아 주던 것이다

한 문장 안에 충돌 키가 같은 매핑이 둘이면 PostgreSQL은 SQLSTATE 21000을 던지고, 그것은
`sqlalchemy.exc.ProgrammingError`(`.orig = CardinalityViolation`)로 나온다 —
**`IntegrityError`가 아니다.** 세 개의 `except IntegrityError` 자리 중 어느 것도 못 보고,
재시도도 없고, **배치 전체가 죽는다. 중복이 아니라 배치가 사라진다.**

이것이 기록할 값어치가 있는 이유는 **대체된 executemany가 중복을 조용히 참았기**(마지막
값 승) 때문이다. 즉 이 전제는 **새로 하중을 받게 됐고**, 옛 동작을 보고 작성된 호출자는
운영에서만 실패한다. 현재 두 호출자는 둘 다 `conflict_cols` 키로 dict를 다시 만들어
보내므로 도달할 수 없고, 독스트링에 **번호 붙은 CALLER OBLIGATIONS**로 적혔다 — 전제 하나만
적어 둔 목록은 완전한 목록으로 읽힌다.

## 실패 로그 273배

1,000행 청크의 NOT NULL 위반 하나가 **25,097자** 예외 문자열을 만들었다. 그것이 대체한
행별 전송은 852자였고, `e.orig`를 통하면 92자다. 그리고 `_send_to_upsert`의 **두 자리를
다 고쳤다** — 바깥 핸들러가 같은 재발생 객체를 다시 로깅하므로 실패한 청크는 25 KB가
아니라 대략 **50 KB**를 쓰고 있었다.

이 커밋은 자기를 촉발한 검수도 정정했다: 역사적 수치는 3,031이 아니라 **852**다.
SQLAlchemy는 실패한 파라미터 세트 하나만 붙였지 1,000개를 다 붙이지 않았다. 방향은 같고
비율은 더 크다.

## 검증

- `ab008ec`: **세 갈래를 다 태웠다** — 브라우저 셀 편집(진짜 `user` 레이어 + 오버라이트
  표식 + 감사 행), 체인 발화(두 표로 투영), 파일 인제션(**가정이 아니라 단언으로**
  `SUCCESS` 도달). 초록 스위트는 쓰기 경로 변경의 증거가 아니기 때문이다.
- 가드 다섯(파이썬 기본값 생략·미지 키·SQLite·에러 클래스·autoflush)에 고장을 **주입해**
  발화를 관측했다.
- `ed11590`: 만진 것을 덮는 13개 파일 **207 테스트**.

## 🔴 이 커밋이 안고 착지한 구멍

`ab008ec`은 **새 경로에 단위 커버리지가 없다**고 적고 착지했다. 초록 68건은 SQLite에서 돌고
새 경로는 dialect 가드에서 설계대로 거절하므로, **SQLite 테스트는 이 코드에 닿을 수 없다.**
그 문장을 후속으로 미루지 않고 커밋 본문에 적은 것이 옳았다 — 이 파일 위의 초록을 본
다음 사람은 그것을 반대로 읽는다.

그 문장의 **결론 쪽은 같은 날 오후에 뒤집혔다.** 「SQLite 테스트가 닿을 수 없다」는 참이고,
그것이 초대한 읽기 「그러니 아무것도 못 닿는다」는 거짓이었다 —
[PostgreSQL 픽스처](./20260812_111113_the_postgresql_fixture_a_commit_of_mine_called_impossible.md).

## 아키텍처 영향

- 빠른 경로는 **재현할 수 없는 것을 만나면 추측하지 않고 되돌려준다.** 거절 사유는 닫힌
  어휘 넷(`dialect` / `unknown_column` / `python_default_omitted` /
  `defaulted_column_is_none`)이고 전부 로깅된다.
- `_is_executemany_safe`의 「느릴 수는 있어도 틀릴 수는 없다」는 문장이 **이 함수의 성질이
  아니라 두 함수의 성질**임이 그 독스트링에 명시됐다. 이 술어는 값이 `None`인 키에도 True를
  답하고, 그것만으로 기본값 컬럼에 NULL을 쓰기에 충분했다.
- 청크 크기는 여전히 안 움직인다. 이유가 correctness에서 메모리·롤백 단위로 바뀌었을 뿐이다.

## 그때 남아 있던 것

- **`ROOT_DEFECTS.md`는 여전히 `execute_values`를 수리법으로 권한다** — 독스트링이 거절을
  기록해 둔 바로 그 접근이다(같은 날 `dd21dc6`이 관측해 적었다).
- `ed11590`은 `test_map_alignment*` 실패 105건을 「무관하므로 돌리지도 쫓지도 않았다」고
  적었다. **그 귀속은 같은 날 오후에 틀린 것으로 드러났다** — 105 중 그 파일들의 것은
  72다(위 링크의 항목).
- 운영에서 이 경로가 실제로 얼마나 빨라졌는지는 **이 워크스테이션이 말할 수 없다.** 위 표는
  전부 격리 `assy_qa`다.
- `ab008ec` 본문이 정정한 두 선행 보고서(`Index_retirement.md`의 자동완성 편집기 혐의와
  `ix_audit_logs_business_key`의 「0 scans」)는 **보고서 파일 자체는 고쳐지지 않은 채**
  커밋 본문에만 정정이 남았다.
