# 행 클릭 하나가 그 행에 쓰인 이력 전부를 불러왔고, `LIMIT`만으로는 DB에 아무 소용이 없었다

**날짜:** 2026-08-11 08:23 · **커밋:** `dab9152` · **레인:** 서버 + 클라(이력 페이징)
**측정 상자:** 이 워크스테이션의 격리 DB `assy_qa`. **운영이 아니다.**

---

## 배경

`GET /tables/{t}/rows/{id}/history`와 그 셀 버전 둘 다 `.order_by(timestamp.desc()).all()`로
끝나 있었다 — `LIMIT` 없이. 행 하나를 클릭하면 **그 행에 지금까지 쓰인 감사 이력 전부**가
로드되고 pydantic을 전부 통과했다. 클릭 한 번의 비용이 지금까지 적재된 전체 양에 비례해
자랐다. 전날(`6cc7a6e`)의 리빙 문서 동기화가 추적하기 시작한
`FETCH_AND_AUDIT_HISTORY_PERFORMANCE_PROPOSAL.md`가 이 수리의 근거다.

## 실측 — 한 행을 300,019개 감사 항목으로 부풀린 픽스처(1,131,008행 중)

```
row  history, no LIMIT : 300,019 rows, ~54 MB of column text, 3,462 ms
cell history, no LIMIT :  12,000 rows, ~2.2 MB,   218 ms
```

둘 다 **pydantic이 행 하나를 보기도 전**의 수치다.

## 핵심 발견 — `LIMIT`만으로는 데이터베이스에 아무 소용이 없다

쿼리에 `LIMIT 201`이 이미 있고 새 인덱스가 없는 상태에서, 실행 계획은 여전히
**300,019건 전체를 병렬 비트맵 힙 스캔 + top-N 정렬**했다 — 9,421 버퍼, 121.6 ms.
`LIMIT`은 와이어와 pydantic으로 넘어가는 바이트만 줄였을 뿐, **스캔 자체는 여전히
그 행의 전체 이력에 비례해 자랐다.** 인덱스를 추가하자 207 버퍼 / 0.40 ms.

```sql
-- 왜 두 번째 인덱스도 필수인가: column_name 하나만 채워진 셀이
-- 300,019행짜리 행 범위 안에서는 range 안의 Filter일 뿐이라, planner가
-- 행 인덱스를 포기하고 다시 비트맵 스캔으로 폴백한다.
--   row index only : 9,421 buffers, 117.7 ms
--   this index     :     5 buffers,   0.09 ms
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_row_history
    ON audit_logs (table_name, row_id, "timestamp", id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_cell_history
    ON audit_logs (table_name, row_id, column_name, "timestamp", id);
```

인덱스 선언은 `AuditLog.__table_args__`(`server/database/models.py`)에도 있지만,
`create_all`은 **이미 존재하는 테이블에는 인덱스를 추가하지 않는다** — 그래서 기존
DB(운영 포함)는 `server/migrations/add_audit_history_keyset_indexes.sql`을 **수동으로**
`psql -f`로 한 번 돌려야 한다. `CONCURRENTLY`라 트랜잭션 블록 안에서 실행할 수 없고,
중단되면 `INVALID` 인덱스가 남아 쓰기 비용만 지불하고 아무것도 읽지 않는다 — 마이그레이션
파일 자신이 그 확인 질의까지 적어 뒀다.

## 커서 설계에서 제안서 문구를 뒤집은 두 결정, 둘 다 실측

**OR 전개가 아니라 행-값 비교.** 논리적으로는 같지만 계획은 다르다:
`(timestamp, id) < (ts, id)`는 Index Cond, 18 버퍼 / 0.114 ms. `timestamp < ts OR
(timestamp = ts AND id < id)`는 Filter, 2,311 버퍼 / 4.949 ms — 이미 본 10,001건을
다시 훑기 때문이다.

**`DESC, id DESC`가 아니라 그냥 ASC.** 같은 플랜, 같은 Index Cond, 같은 버퍼 수를
측정했다. ASC는 `__table_args__`에 원시 SQL 없이 선언할 수 있어 PostgreSQL과 테스트용
SQLite를 하나의 선언으로 같이 덮는다.

## 응답이 봉투가 됐다

```python
def fetch_page(query, model, limit: int, cursor: str = None):
    query = apply_cursor(query, model, cursor).order_by(*order_desc(model))
    rows = query.limit(limit + 1).all()
    truncated = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].timestamp, rows[-1].id) if (truncated and rows) else None
    return rows, truncated, next_cursor
```

`limit + 1`행을 요청해 초과분 하나로 「더 있나」를 판정한다 — `count(*)`가 다시 훑는 것과
달리 정확하고 값싸다. `next_cursor`는 `truncated`가 참일 때만 non-null이라 컨트롤이
스스로 꺼진다. 디코드 실패 커서는 페이지 1로 조용히 재시작하지 않고 **400**을 낸다 —
조용한 재시작은 「더 보기」가 같은 행을 영원히 이어붙이게 만든다.

## 두 번째 `get_cell_history` — 등록됐지만 도달 불가능했던 사본

`main.py` 하단에 같은 경로로 `get_cell_history`가 **한 번 더** 정의돼 있었다. FastAPI는
첫 번째 등록만 서비스하므로 이 사본은 등록된 날부터 한 번도 실행되지 않았고,
`response_model`이 없어 `is_row_deleted`도 삭제된 행의 business-key 폴백도 없는
**진짜 부분집합**이었다. 도달 불가능함을 `app.routes`로 확인한 뒤 삭제하고,
경로당 등록이 하나뿐임을 단언하는 테스트를 추가했다.

## 클라이언트 — 새 패널이 아니라 목록 끝의 `<li>` 하나

```
일부만 (200건) · 더 보기
```

새 모드·새 패널 없이 기존 목록 끝에 한 줄. 「일부만 잘렸다」는 사실을 암시가 아니라
문장으로 말한다. 스타일은 측정 후 한 번 고쳐졌다 — `--text-muted`의 0.78rem/500은
대비가 이미 AAA인데도 0.8~0.85rem대 카드들 사이에서 **가장 가벼운 무게**였다. 대비가
문제가 아니라 이웃 대비 시각적 무게였다는 뜻이다.

세션 토큰은 요청을 보내기 **전**에 올리고 `res.json()` **이후**에 다시 확인한다 —
상태 줄만으로 확인하면 몸체가 도착하기 전에 이미 통과해 버려, 이전 행의 페이지 2가
새 행의 페이지 1에 얹힐 수 있다.

## 검증

새 하네스 `history_paging_harness.mjs`: 98 어서션, 주입된 결함 10개 전부 잡힘, 통제군
2개 모두 미발화. 이전에는 `timeline.js`를 검사하는 하네스가 없었다 — 게이트 대비 diff는
**초록 한 줄 추가**뿐이고 기존 어서션 수는 움직이지 않았다.

파이썬 쪽 신규 테스트는 `server/tests/test_audit_history_paging.py`(235줄) — 페이지가
**설정된 크기**로 잘리는지, 잘린 페이지가 `truncated: true`+`next_cursor`를 갖는지, 완전한
페이지는 커서를 **갖지 않는지**, 타임스탬프 **동점**을 넘나드는 페이징이 행을 정확히
한 번씩 방문하는지, 깨진 커서가 400인지, 경로 등록이 하나뿐인지를 각각 핀으로 고정한다.
이 커밋 본문은 이 파일에 대해 통과/실패 수를 별도로 대지 않는다 — 근거는 하네스 98개
어서션과 diff 자체다.

## 그때 남아 있던 것

- `add_audit_history_keyset_indexes.sql`은 **아직 어떤 운영 DB에도 실행되지 않았다** — 이
  트리에 그 파일을 자동으로 돌리는 부트 경로는 없고, 실행은 사람이 `psql -f`로 해야 한다.
  다음 커밋(`2630790`)의 문구가 이 사실을 재확인한다.
- 이 커밋이 손댄 `/tables/{t}/rows/{id}/history`류와, `/audit_logs/recent`(패널의 「최근」
  탭)는 **서로 다른 경로다.** 후자의 정렬·부담 문제는 이 커밋의 범위 밖이고, 같은 날 뒤에
  오는 `2630790`이 다룬다.
- `verify_upsert.py` 스크립트만 새 봉투 모양에 맞춰 고쳐졌고, 이 커밋 diff에는 이 새
  엔드포인트를 부르는 다른 운영 스크립트가 있는지에 대한 전수 조사가 없다.
