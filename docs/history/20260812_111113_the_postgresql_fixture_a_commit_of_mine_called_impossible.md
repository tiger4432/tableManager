# The PostgreSQL fixture a commit of mine called impossible, and the baseline that hid a third of itself

**Date:** 2026-08-12 11:11 · **Domain:** Server (테스트 인프라 / 쓰기 경로 커버리지) · **Status:** 착지 — `dd21dc6`

> ⚠️ **모든 수치는 격리 `assy_qa`와 이 개발 워크스테이션 실측이다. 운영 수치가 아니다.**

---

## 배경 — 전제는 반만 맞았고 결론은 틀렸다

`ab008ec`은 **「새 경로에 닿을 수 있는 테스트가 없다」**고 적고 착지했다
([항목](./20260812_103853_the_upsert_looked_batched_and_the_replacement_wrote_null_over_a_default.md)).

앞 절반은 참이다 — SQLite 테스트는 `dialect.name != "postgresql"` 가드에 걸려 닿을 수 없다.
계수 스파이로 재 보면 그 파일 셋에서 **`entered=28 accepted=0 declined=28`**이 42개 초록
테스트를 통과하며 나온다. 새 경로의 SQL 구성, bind processor, ON CONFLICT 대상, 청크
루프 — **전부 한 번도 안 돌았다.**

뒤 절반이 틀렸다. **「그러니 아무것도 못 닿는다」는 참이 아니었다.**

`conftest.py`는 **PostgreSQL URL을 문서화해 놓고** 픽스처는 **하드코딩된 인메모리
SQLite에 묶어** 두고 있었다. `ASSY_TEST_DATABASE_URL`은 **애플리케이션**을 다시 겨누고
`db_session`은 자기 엔진에 그대로 남는다. 그러니 그 변수를 세팅하면 **스위트 전체**가
PostgreSQL로 옮겨 가고 `bootstrap_database_schema`가 그 DB의 `public`에 `create_all`을
쏜다.

필요한 것은 다른 모양이었다 — **두 번째 엔진, 스크래치 스키마, 스위트 본체는 SQLite에
그대로.** 약 **40줄**이다.

**「없다」와 「내가 안 만들었다」는 다른 문장이고, 커밋 본문은 앞의 것으로 적혔다.**

## 가드를 우회하지 않고 가드 «안»에 들어갔다

`db_safety`는 Engine **클래스**에 `engine_connect` 리스너를 건다. 그래서 pytest
프로세스에서 테스트가 만드는 비-sqlite 엔진은 **가드 자신의 변수가 그것을 정확히 지목하지
않는 한 전부 거절된다**(백엔드·호스트·포트·DB명).

픽스처는 그 가드를 **끄지 않는다.** 자기 자격증명도 안 갖는다.

```python
@contextlib.contextmanager
def _declared_as_test_database(url):
    """Declare `url` under the name `db_safety` reads, for this block only."""
```

운영자 선언(`ASSY_PG_TEST_DATABASE_URL`)을 읽어 **`db_safety.check_test_database`로 다시
검사한 뒤**(운영 DB를 선언해도 여전히 거절된다 — **선언한다고 테스트 DB가 되지 않는다**),
가드가 읽는 이름으로 **가장 좁은 창에서만** 선언한다: 픽스처 셋업, 테스트 본문, 티어다운.

그 창이 좁아야 하는 이유가 구체적이다 — `test_dev_env_isolation.py`가 **자기 실행
시점에** 그 같은 변수를 라이브 엔진과 대조한다. 창을 안 닫으면 그 테스트가 무엇을 보는지
바뀐다.

DDL은 전부 스크래치 스키마로 간다. 그리고 그 리다이렉션은 **커넥션에서** 일어나야 한다 —
ORM 모델은 스키마 없는 `Table`에 매핑돼 있고 `_pg_multirow_upsert`는
`INSERT INTO cell_sources`를 **한정 없이** 쏜다. `-csearch_path=<schema>`에서 `public`을
빼면 **한정 없는 쓰기가 진짜 표에 물리적으로 닿을 수 없다.**

## 청소는 보고가 아니라 측정이다

티어다운이 스키마를 드롭하고 **카탈로그에 물어본다.** 그리고 **그 단언 자체가 눈이 먼지
검사됐다** — 스키마를 심으면 1을 반환하고 드롭 후엔 0을 반환한다.

이 성실함에는 같은 날의 근거가 있다: **어떤 검수자의 92개 객체 스키마가 「드롭했다」는
보고를 뚫고 살아남았다.** 그래서 여기서 청소는 **주장이 아니라 측정**이다. 셋업도 같은
이름의 잔여물을 먼저 드롭한다 — 중간에 죽은 실행이 다음 실행에 회수되게.

스킵은 **세 가지 방식으로** 확인했다 — 미선언, 운영 DB 지목, 서버 도달 불가.

## 36 테스트, 그리고 가짜였던 것 둘

무방비였던 아홉 동작 전부에 테스트가 붙었다. 그중 가장 중요한 것은 **진짜 UNIQUE 인덱스
위에서, 생 psycopg2 경쟁 기록자를 다른 OS 프로세스로 띄워 놓고** 하는 업무키 복구다.
그리고 단언이 **「재시도가 일어났다」가 아니라 「병합이 승자의 `row_id`에 착지했다」**이다.

그것이 대체한 테스트는 **`rollback()`이 정수 카운터인 가짜 세션**을 쓰고 있었다.

그리고 **빠른 경로 이름을 달고 fallback을 시험하던 테스트가 둘** 있었다 —
`entered=28 accepted=0`. 각자 시험하는 것을 말하도록 개명하고 accepted 갈래의 짝을
가리키게 했다.

> **이름이 거짓말하는 테스트는 테스트가 없는 것보다 나쁘다. 커버리지로 «세어지기»
> 때문이다.**

## 변이 둘이 코드가 아니라 «테스트»의 결함을 찾았다

변이 12개를 **함수 소스를 메모리에서 재컴파일하는 방식**으로 적용했다 — `crud.py`는 한
번도 편집되지 않았다(공유 트리에서 옆 레인이 그 파일을 쥐고 있었다).

하나가 살아남았고, **결함은 테스트 쪽이었다.**

```python
⚠️ THE ROW IDS ARE ZERO-PADDED AND THAT IS LOAD-BEARING. `bulk_upsert_*`
re-sorts its mappings by the conflict key before chunking (deadlock
ordering), and that sort is on the STRING. Unpadded, `AB_1004` sorts
between `AB_1003` and `AB_101`, i.e. into the FIRST chunk - so the test
said "poison in the last chunk" while exercising the first one, and a
`db.commit()` injected into the chunk loop left it green.
```

독스트링이 「마지막 청크에 독을 넣었다」고 말하는 동안 **문자열 정렬이 그것을 첫 청크로
옮겨 놓고 있었다.** 청크 루프에 `db.commit()`을 주입해도 초록이었다. 제로 패딩으로 이제
빨개진다 — **패딩이 독스트링을 참으로 만드는 것**이다.

같은 눈이 둘째를 찾았다: 어떤 충실도 테스트가 **자기 첫 갈래가 accepted였는지 단언하지
않았다.** 나중에 거절이 생기면 그 테스트는 **fallback을 fallback과 비교하고 통과**한다.

그리고 `None`-on-default 수리(`ed11590`)는 **세션 도중에 착지해서** 그 테스트를 살아 있는
결함에 대고 돌릴 수 없었다. 증거를 잃는 대신, 변이가 그 함수를 **`ed11590^`에서 바이트
그대로 복원**하고 발산 테스트 둘이 그것에 대고 빨개진다 — **창이 닫혀도 재현되는 증명**이다.

## 🔴 스위트 기준선이 틀렸고, 계수가 그것을 감췄다

`105 failed / 3348 passed`. 이 작업 전후로 **변함없었다.**

그런데 105가 **전부 `test_map_alignment*`가 아니다 — 그건 72다.** 나머지 33은 열 개 파일에
흩어져 있다: 추적되지 않는 셋째 레인의 `test_audit_changeset.py`에 15,
`test_dt_index_walk_core_axis.py`에 9, 그리고 `test_composite_key_prefetch_budget.py`에 1 —
**마지막 것은 이번 라운드가 편집해 온 쓰기 경로 위에 앉아 있다.**

**총계는 105에서 안 움직였는데 구성원의 3분의 1이 갈렸다.** 계수 검사는 통과하고 틀린
답이 살아남았다 — 이 저장소가 스스로 적어 둔 **「개수 말고 구성원을 고정한다」**가 하필
**기준선 자신에게** 착지한 것이다. 보드는 한 레인에게 「너는 105건을 갖고 있다」고 말해
왔는데 실제로는 72건이었다.

쓰기 경로의 그 한 건은 여기서 실제로 돌려 봤다 —
`test_inserting_new_rows_still_probes_once_per_row`가 **201 statements를 기대하고 1을
받는다.** 그것은 **알려진 결함(행마다 헛프로브 1회)에 박아 둔 핀**이고, 결함은 **핀이
갱신되지 않은 채 닫힌 것으로 보인다.**

> **「너 빨라졌다」를 뜻하는 빨강도 빨강이다.** 그리고 그것이 **아무도 분해하지 않은 수
> 안에 앉아** 있었다.

같은 테스트가 `e9fd8a6` 항목에서 「이전에도 있던 유일한 실패」로 기록됐다. **거기서는
그것이 무엇을 뜻하는지 몰랐다.**

## 아키텍처 영향

- 스위트는 **여전히 SQLite에서 돈다.** 이 픽스처는 선언이 있을 때만 살아나는 **두 번째
  엔진**이고, 없으면 **스킵하지 실패하지 않는다.** 스킵 메시지가 어느 문이 닫혔는지 말한다.
- 동적 테이블 이름은 `pgqa_` 접두를 단다 — `models.DYNAMIC_TABLES` / `Base.metadata`가
  공유 싱글턴이고 운영자의 gitignore된 config에 실재하는 표와 충돌할 수 없어야 한다.
- 스크래치 스키마는 xdist 워커 id를 접미로 단다. 병렬 워커가 서로의 스키마를 드롭할 수 없다.

## 그때 남아 있던 것

- **`ROOT_DEFECTS.md`는 여전히 `execute_values`를 수리법으로 권한다** — `ed11590`의
  독스트링이 거절을 기록해 둔 바로 그 접근이고, 이 커밋은 그것을 **관측해서 적었을 뿐
  고치지 않았다**(문서는 다른 소관).
- **기준선 105는 이 커밋 시점에도 105다.** 분해가 기록됐을 뿐 실패는 하나도 안 고쳐졌다.
- `test_inserting_new_rows_still_probes_once_per_row`의 핀은 **이 시점에 갱신되지 않았다.**
- **선언이 없으면 36 테스트는 전부 스킵된다.** 이 항목의 커버리지는 `ASSY_PG_TEST_DATABASE_URL`을
  가진 환경에서만 존재한다 — CI가 그것을 갖고 있는지는 이 커밋에 기록이 없다.
- `test_audit_changeset.py`(15 failed)는 **추적되지 않는 셋째 레인의 파일**이라 커밋된
  트리에는 없다. 그 15건은 다음 사람이 커밋 상태에서 재현할 수 없다.
