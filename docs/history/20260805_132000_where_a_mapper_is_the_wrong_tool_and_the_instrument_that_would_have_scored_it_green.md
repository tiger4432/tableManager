# 매퍼가 틀린 도구인 자리 — 그리고 그것을 초록으로 채점했을 계측기

> **커밋:** `4717429` (2026-08-05 13:20) | **일자:** 2026-08-05 오후
> **선행:** [`20260805_131200`](./20260805_131200_a_predicate_shipped_as_data_is_defined_by_whoever_applies_it.md)(`7f0a717`, **8분 전** — 이 샘플을 돌리는 테스트가 **거기** 들어가 있다)
> **담당:** 제품 소유자(요청: 자기를 부른 테이블 말고 다른 테이블을 읽는 체인 매퍼 예제) · server 문서
> **대상:** **신규** `server/mappers/cross_table_lookup_mapper.py.sample`(**+561**) · `docs/guide/chain_ingestion_guide.md`(+6 / −2) ― **2파일**
> **스위트:** 커밋 메시지에 결과 없음.

## 샘플이 「이걸 하지 말아야 할 때」로 시작한다

가상 조인이 그 필요의 대부분을 **선언적으로** 이미 답하기 때문이다. 그리고
경계선은 **실측으로 그어졌고, 내 원래 구획은 매퍼에 너무 후했다.**

가상 컬럼은 `/schema`에 **공지되고, 필터되고, 검색되고, CSV 추출에 실린다.**
빠진 것은 **정렬뿐**이다.

> 그러므로 대립은 「선언적 vs 명령적」이 아니라
> **「그대로·라이브」 vs 「계산됨·동결됨」**이다.

**매퍼가 자리를 버는 경우 넷:**

| 조건 | 이유 |
|---|---|
| 값이 **계산**돼야 한다 | expose는 컬럼을 그대로 넘긴다. 식이 없고, 집계 모양은 미구현이다 |
| 파생 시점에 **동결**돼야 한다 | 가상 조인은 볼 때마다 오른쪽 표를 **구조상 다시 읽는다** |
| 오른쪽이 조인 키로 **유일해질 수 없다** | — |
| 출력이 **아직 존재하지 않는 행**이다 | — |

샘플이 그 귀결을 적는다: **동결된 값은 일부러 낡는다. 그러므로 파생된 행은
자기가 어느 참조 값을 동결했는지 기록해야 한다.**

## 트랜잭션 규율 — 이유를 코드 자리에 붙여서

**절대 commit / rollback / close 하지 않는다.** 워커가 폴링 배치당 세션 하나를
열고 배치 전체에서 공유하기 때문이다. commit은 **실패 경로의 rollback을 빠져나가고**,
`expire_on_commit`이 **워커가 막 도장을 찍으려던 아웃박스 행을 무효화**한다.

참조 조회문마다 `begin_nested`:

```python
    nested = db.begin_nested()
    try:
        rows = query.all()
    except Exception:
        nested.rollback()
        raise
    nested.commit()
```

**격리와 저하는 서로 다른 일**이기 때문이다. 그리고 이것이 막는 사고가
**저장소에 실재한다** — `bonding_plan.py:283`이 그 자리다:

```python
    except Exception as e:      # :283 — db.rollback() 이 없다
```

잡기만 하고 되돌리지 않아 **세션이 abort된 채로 남는다.** 샘플은 그것을
「가정이 아니라 이 코드베이스의 살아 있는 결함」으로 적는다.

조회는 청크 단위이고 **키를 먼저 중복 제거**한다. 저하는 기존 닫힌 어휘를 쓰고,
`not_declared`와 `mapping_unavailable`은 **수리 방법이 다르므로** 따로 유지된다.
트리거 행은 **페이로드에서만** 읽는다.

## 🔴 초록을 만들어 줬을 계측기 — 이 커밋에서 가장 값나가는 부분

```python
# session-level ones are not: `SessionEvents.after_commit` also fires when
# `begin_nested()` releases its SAVEPOINT, so a suite built on it would read this
# mapper's containment as a commit and score the defect green.
    db.execute(text("SELECT 1")).scalar()
    db.commit()
    assert traffic.commits == 1
```

**`SessionEvents.after_commit`은 `begin_nested`가 SAVEPOINT를 놓을 때도 발화한다.**
그 위에 세운 스위트라면 **commit하는 매퍼를 초록으로 채점**한다. 테스트는
**커넥션 레벨 이벤트**를 쓰고, 자기 카운터가 1에 도달할 수 있다는 것을
**같은 자리에서 증명**한다.

## 기존 샘플들과 어긋나는 것 둘 — 다듬지 않고 보고했다

- **`silent`은 죽었다.** `chain_ingestion_worker.py:437-441`이 배치를 직접
  만들면서 `silent=False`를 **하드코딩**한다. 매퍼가 준 값은 도달하지 않는다.
- **`production_mapper.py.sample`은 라이브 파일의 거울이 아니다.** 실제 파일은
  2,257바이트에 톱레벨 `def` 둘, `.sample`은 1,134바이트에 하나다.

## ⚠️ diff가 커밋 메시지와 어긋난 자리

커밋 메시지는 「단언되는 것이 아니라 **실제로 돈다** — 테스트가 바로 그 `.sample`
텍스트를 적재해 진짜 `database_outbox` 행에서 읽은 페이로드로
`execute_custom_mapper`를 돌린다」고 적는다. **그 테스트는 이 커밋에 없다.**
`server/tests/test_mapper_sample_cross_table_lookup.py`(478줄)는 **8분 전
`7f0a717`**에 들어갔고, 그 시점에는 **여기서 추가되는 `.sample` 파일이 아직
없었다.**

## 그때 남아 있던 것

- **테스트와 그 테스트가 적재하는 파일이 서로 다른 커밋에 있다.** 둘 중 어느
  커밋에서도 그 짝이 온전하지 않다.
- `bonding_plan.py:283`의 rollback 누락은 **이 커밋에서 고쳐지지 않았다** —
  샘플이 그것을 **인용**할 뿐이다.
