# 「최근」 패널이 5,000행마다 테이블 전체를 재정렬했고, 실제 일어난 변화의 정확히 두 배를 보고했다

**날짜:** 2026-08-11 09:37 · **커밋:** `2630790` · **레인:** 서버(감사 투영 성능)
**측정 상자:** 이 워크스테이션의 격리 DB `assy_qa`. **운영이 아니다.**

---

## 배경

전날 보드 판정(`3fe4438`)이 「진범 ①」로 지목했던 `/audit_logs/recent`를 직접 고치는
커밋이다. 이 경로는 앞선 `dab9152`(행/셀 이력 페이징)와는 **다른 경로**다 — 이쪽은
`table_name`/`row_id` 술어가 없어 그 두 인덱스를 planner가 그대로 무시한다.

## 문제 — 성장하는 OFFSET으로 정렬 안 된 로그를 훑는다

`load_initial`이 `audit_logs`를 최신순으로 5,000행 청크씩, **커지는 OFFSET**으로,
서로 다른 `transaction_id` 100개를 모을 때까지 걸었다. `timestamp` 선두 인덱스가
없어 청크마다 병렬 순차 스캔 + 전체 정렬:

```
Parallel Seq Scan -> Sort (timestamp DESC, id DESC)
external merge  Disk: 400,848 kB   153,307 buffers + 287,412 temp written
... 청크마다, ~41청크
```

대량 적재는 이걸 가장 나쁜 방식으로 악화시킨다 — 파일 하나 = 트랜잭션 하나라, 신선한
20만 행이 그룹을 **2개**만 가질 수 있고, 걷기는 100개를 채우려고 청크를 계속 지불해야
한다.

## 실측 — 468배

```
                            no index      with index
old (growing OFFSET)     234,399 ms       7,543 ms
new (keyset + aggregate)  17,798 ms         501 ms
```

인덱스 단독 31배, 코드 단독 13배 — 둘 다 필요했고 어느 쪽도 전체 수리가 아니었다.
최종 파일의 콜드 실행 3회: 447 / 456 / 506 ms. 이후 `Index Only Scan`, `Heap Fetches: 0`,
청크당 191 버퍼 / 7.7 ms. `idx_audit_recent_groups ON audit_logs ("timestamp", id)
INCLUDE (transaction_id)`는 166 MB, 행당 60.1 B, `CONCURRENTLY`로 4.2초에 빌드됐다.
최악의 경우도 정직하게 실었다 — 10만 행 적재 직후엔 새 페이지가 아직 all-visible이
아니라 청크당 `Heap Fetches: 20000`을 물어 콜드 호출이 1,956 ms다(`VACUUM` 후 612 ms,
같은 인덱스·같은 상한).

스캔은 이제 **경계가 있고 그 사실을 말한다** — `truncated`/`next_cursor`가
`audit_history.fetch_page`와 같은 두 뜻을 나른다(같은 `encode_cursor`·`order_desc`·
`apply_cursor` 재사용, 커서 술어의 두 번째 철자는 유지하지 않고 삭제). 다만 이번엔
본문 봉투가 아니라 헤더로 나간다:

```python
response.headers["X-Audit-Truncated"] = "true" if audit_cache.truncated else "false"
if audit_cache.next_cursor:
    response.headers["X-Audit-Next-Cursor"] = audit_cache.next_cursor
```

**본문을 그대로 둔 이유는 클라이언트다.** `client2/src/timeline.js`가
`state.globalHistoryData = await res.json()`로 받아 곧바로 순회하므로, 본문을 봉투로
바꾸면 패널이 그 자리에서 깨진다. 봉투로 뒤집는 것은 클라·서버 동시 변경이 필요한
별도 작업으로 남겨졌다 — 이 커밋은 서버만 고쳤다.

## 🔴 카운트가 두 배였다 — 비용보다 나쁜 결함

`add_logs_batch`는 워터마크를 절대 전진시킬 수 없었는데, 원인은 빠진 한 줄이 아니라
**받는 로그 dict 전부가 `"id": 0`을 리터럴로 갖고 있었다**는 것이다
(`server/database/crud.py:1222` — `bulk_insert_mappings`가 부여된 키를 다시 써 주지
않는다). 그래서 그 행들은 다음 새로고침에 **두 번 읽히기만** 한 게 아니라 **두 번
세어졌다.**

```
300 rows written, event reports 300  ->  total_count    600  (x2.00)
100,000 rows written                 ->  total_count 200,000 (x2.00)
```

수리는 새 진실원을 만드는 게 아니라 **선불(credit)** 이다 — 이벤트가 자기가 주장한
만큼을 기록해 두고, 같은 행을 DB에서 다시 읽는 새로고침이 그 선불을 상계한다.
DB는 여전히 수의 유일한 권위다.

```python
def _absorb_one(group: dict):
    """One row read back from the database: absorb against credit, else add."""
    credit = group.get("_event_credit", 0)
    if credit > 0:
        group["_event_credit"] = credit - 1
        return
    group["total_count"] += 1
```

수리 후: 300 → 300, 100,000 → 100,000. 10만 신규 행 새로고침도 4,010 ms → 1,814 ms로
떨어졌고, `recent_refresh_max_delta_rows`를 넘으면 이제 모든 신규 행을 모델링하는
대신 경계 있는 재구축으로 넘어간다 — 기존 「재생은 이력을 다시 훑지 않는다」 테스트는
변경 없이 통과한다.

> 이 문서를 쓰는 세션의 확인: `crud.py:1222`에 `"id": 0`이 실재한다(3281에 두 번째
> 사본도). 커밋 본문은 그 위치를 `crud.py:1138`로 적었는데, 이 트리의 1138행은 무관한
> 내용(소스 우선순위 서술)이다 — 인용된 줄 번호가 실제 위치와 어긋난 사소한 오기다.

## 이 수리가 새로 만든 위험 둘, 그리고 닫은 방법

둘 다 침묵-오답 부류이고 둘 다 널 타임스탬프다. NULL에 대한 행-값 비교는 NULL이지
false가 아니라서, 첫 청크 이후 모든 청크가 그런 행을 조용히 떨어뜨렸다(첫 청크만
쥐고 있었다). PostgreSQL에서 DESC는 NULLS FIRST를 뜻해, 널 스탬프 행이 **첫 청크의
가장자리**다 — 위치를 인코딩할 수 없고, 널 커서는 「커서 없음」으로 읽혀 걷기가
맨 위에서 재시작하며 머리 행을 랩마다 한 번씩 다시 센다. 수화(hydration)는 별도로
`AuditLogResponse.timestamp: datetime`에 널을 넘겨 500을 냈을 것이다. 둘 다
`timestamp IS NOT NULL`을 술어에 암시시키지 않고 공유 헬퍼 하나에 **명시**해서
닫았다.

아홉 개 알람 중 둘은 **처음 쓰였을 때 조용했고, 테스트의 잘못이 아니었다** — ORM을
통한 `timestamp=None`은 NULL을 저장하지 않고(`server_default`가 채운다), SQLite는
NULL을 마지막에 정렬하는데 PostgreSQL은 처음에 정렬해서, 픽스처가 이 위험을 만들
수 없었다. 테스트는 이제 원시 NULL을 직접 삽입하고 PostgreSQL의 정렬 순서를 고정한다.

## 검증

주입된 결함 9개, 각각 이름 붙은 테스트가 잡음. 두 파일 모두 sha256으로 원상복구
확인. 커밋 본문의 주장: **362개 테스트가 `audit_cache`·`audit_logs`·라우트 전반에서
통과.** 이 항목은 이 수치를 diff와 대조해 재확인하지 않았다(스위트 재실행은
doc-historian의 범위 밖) — 신규 테스트 함수 자체는 diff로 셀 수 있다:
`test_audit_cache_recent_scan.py`에 7개(`test_a`~`test_g`), `test_audit_cache_cross_process.py`
에 2개 추가.

트랜잭션 분할(대량 적재를 여러 트랜잭션으로 쪼개는 방안)은 검토 후 기각됐다 —
`transaction_id`가 `/audit_logs/transaction/{tx}`·`InteractionEffortLog.transaction_id`
(UNIQUE)·아웃박스 payload·체인 재생 그룹핑의 조인 키라, 「이 파일, 변경 10만 건」
한 줄을 N줄로 바꾸는 것은 패널이 보여주려는 것 자체의 퇴행이다. 인덱스 필요성도
없애지 못했을 것이다 — 걷기는 그룹 크기와 무관하게 행마다 비쌌다.

## 그때 남아 있던 것

- `client2/src/timeline.js`는 이 커밋에서 **손대지 않았다** — `X-Audit-Truncated`/
  `X-Audit-Next-Cursor` 헤더를 읽는 클라이언트 코드는 아직 없다. 패널은 지금도 잘린
  응답과 완전한 응답을 구별하지 않는다.
- **운영에는 인덱스 마이그레이션 셋이 여전히 미적용이다** — 이 커밋의
  `add_audit_recent_groups_index.sql` 하나와, 같은 날 앞서 나온
  `add_audit_history_keyset_indexes.sql`의 둘. 이 커밋 본문이 그렇게 명시한다. 부트
  경로가 이 파일들을 자동으로 돌리지 않는다는 점은 `dab9152` 항목에서 이미 확인한
  사실이고, 여기서도 다르지 않다.
- `crud.py`의 `"id": 0` 리터럴 자체는 이 커밋에서 **고쳐지지 않았다** — 우회(선불
  메커니즘)만 됐다. `bulk_insert_mappings`가 부여된 키를 되돌려주지 않는다는 근본
  제약은 남는다.
- `recent_max_scan_rows`는 500,000으로 출하됐다 — 대량 적재 직후 패널이 보여줄 수
  있는 이력의 상한을 결정하는 값이고, 이 커밋은 이를 「제품 결정」으로 명시했을 뿐
  더 정교화하지 않았다.
