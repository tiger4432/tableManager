# V1 정본 계기의 서버 절반이 착지했다 — 미계측은 0이 아니다

> 2026-07-29 07:54 · 도메인 Server(계측·집계·설정·인덱스)
> 상위: [SYSTEM_OVERVIEW §1 핵심가치](../overview/SYSTEM_OVERVIEW.md) · 정의 [data_model §2.4](../architecture/data_model.md) · 계약 [backend](../architecture/backend.md#상호작용-점수-dashboardsummary--effort) · 설정 [config/effort_metric.md](../guide/config/effort_metric.md)
> 선행: [핵심가치 #1의 계기가 교체됐다](./20260729_014707_core_value_1_instrument_replaced.md) (`af7a1a2` — 이 커밋이 구현하는 그 결정)
> 동반: [effort meter 클라 코어](./20260729_074223_effort_meter_client_core.md) (클라 절반)

## 배경 — 계기를 UI보다 먼저 달아야 하는 이유

`af7a1a2`가 핵심가치 #1의 계기를 **완료까지의 상호작용 점수**로 교체하면서 "미구현"으로
남겨 두었다. 이 값은 **소급 산출이 불가능**하다 — 과거 세션에 클릭 로그가 없다. DOE UI
개편(대기열 1번)이 먼저 들어가면 "before"를 영영 얻지 못한다. 그래서 계측이 UI 라운드보다
앞서 머지되어야 했다.

## 구현 — 배점은 곱하지 말고 미뤄라

```
점수(tx) = key×w_key + mouse×w_mouse + nav×w_nav      (기본 1 / 3 / 5)
```

`interaction_effort_logs`에 저장되는 것은 **원시 카운트뿐**이다. 점수 컬럼은 없고, 가중치는
`crud.get_effort_stats`가 **조회 시점에** 곱한다. 점수를 굳혀 저장했다면 배점을 재조정하는
순간 과거가 옛 배점에 갇혀 before/after 비교가 불가능해진다 — 이 계기의 존재 이유가 바로
그 비교인데 말이다. 배점은 `config/effort_metric.json` 선언이고 하드코딩이 아니다.

단위는 새로 만들지 않았다. **`AuditLog.transaction_id`** — 서버가 이미 "한 번의 사람 행위"
경계로 긋고 있는 그 tx를 그대로 쓴다(재교정률도 같은 경계로 접는다). 새 상관관계 개념을
만들면 두 계기가 서로 다른 것을 세게 된다.

## 이 구현이 지켜 낸 것 — 네 가지 조용한 오답

### ① 없음 ≠ 0

`effort`는 **선택 필드**다. 워커·인제션·체인은 같은 `PUT /tables/{t}/data/updates`를 쓰지만
키보드 앞에 사람이 없다. 그런 tx는 **행 자체를 남기지 않는다.**

```python
# server/main.py — 기록 게이트
if effort_counts is not None:
    tx_for_effort = next(
        (l["transaction_id"] for l in created_logs
         if l.get("source_name") == crud.USER_SOURCE), None)
```

0으로 채웠다면 "공수 0의 완벽한 교정"이 집계에 섞여, **교정 표면이 나빠지는 동안 평균이
0으로 끌려갔을 것**이다. 계기가 개선을 보고하면서 실제로는 악화되는, 가장 나쁜 실패 양식이다.

커버리지는 숨기지 않고 `measured_ratio`(계측 tx / 창 안 전체 사람 tx)로 **항상 함께** 낸다.

### ② 세션별 평균 — tx 평균과 같은 숫자가 아니다

사용자가 지정한 집계 단위는 "세션별 평균"이다. tx를 통째로 평균하면 한 세션이 500건 처리한
날 그 세션이 전체를 지배한다 — **대량 편집이 UI 개선처럼 보인다.** 회귀 테스트가 이 축을
직접 활성화한다:

```python
# 세션1: 비싼 교정 1건(10점) · 세션2: 싼 교정 3건(각 2점)
#   세션별 평균: (10 + 2) / 2 = 6.0   ← 요구값
#   순진한 tx 평균: (10+2+2+2) / 4 = 4.0
assert s["avg_score"] == 6.0
assert s["avg_score"] != 4.0
```

### ③ 조용한 클램프 금지 — 400으로 거절한다

음수·소수·문자열·boolean은 400으로 거절하고 **클램프도 캐스팅도 하지 않는다.** 특히
파이썬에서 `bool`은 `int`의 서브클래스라 `True`가 조용히 1이 되는 길이 열려 있다:

```python
# server/main.py _validate_effort
if isinstance(v, bool) or not isinstance(v, int):
    raise HTTPException(status_code=400, detail=f"effort.{field} must be an integer ...")
```

검증은 **어떤 쓰기보다 먼저** 돈다 — 잘못된 계측 페이로드 때문에 교정이 절반만 반영되는
상태를 만들지 않기 위해서다.

### ③-bis 모르는 키는 무시하지 않고 400 — 실측된 결함이다

map-pm이 실제 경로로 확인했다: 클라가 `nav_preserved: 5`를 보냈는데 서버 스키마에 그 필드가
없자 **pydantic이 조용히 버렸다.** 에러도 422도 없고, `nav`는 여전히 정확해서 **아무것도
고장 나 보이지 않았다.** 그것이 이 결함의 본질이다.

```python
# server/main.py _validate_effort — 빠진 키는 정상, 모르는 키만 오류
unknown = sorted((effort.model_extra or {}).keys())
if unknown:
    raise HTTPException(status_code=400,
        detail=f"effort has unknown field(s): {', '.join(unknown)}. ...")
```

**조용히 버려진 값은 애초에 보내지 않은 값과 구별되지 않는다** — 이 프로젝트가 이번 주
내내 걷어낸 결함 형태다(유령 수량, 절단된 push의 성공 보고, 무동작 replace의 200). 이 계기는
소급 재계산이 불가능하므로 몇 달 뒤 발견하면 그 기간의 기준선이 이미 없다. 클라와 서버가
한 저장소에서 함께 배포되니 독립 배포 스큐도 없다 — 불일치는 곧 실수이고, 실수는 시끄러워야
한다. (pydantic의 `extra="forbid"`는 422를 내므로 계약이 요구하는 **400 + 키 이름**을 위해
`extra="allow"` + 명시 검증으로 구현했다.)

### ④ 기본은 "상실"

`context_preserving_transitions`는 유지 전이의 **선언형 허용목록**이고 **비어서 출발한다.**
선언되지 않은 전이는 전부 이동 가중치(5점)다. 반대로 잡았다면 계기가 공수를 실제보다 낮게
보고했을 것이고, 그 편향은 **계기를 소유한 쪽에 유리한 방향으로만** 작동한다. 서버는 목록을
`GET /api/effort/config`로 서빙만 하고 판정은 클라가 한다(배점도 같은 응답에 동봉 — 클라가
사본을 두면 서버 집계와 화면이 조용히 갈라진다).

**와일드카드는 거절한다.** 매칭이 정확 일치라서 `{"from":"*","to":"*"}`는 아무것도 면제하지
못하는데, 목록에 남겨 두면 config를 읽는 사람은 한 부류의 이동이 통째로 면제됐다고 믿는다 —
선언과 동작이 어긋나는데 그렇다고 말해 주는 것이 없다. 무시가 아니라 거절이라야 로그와
서빙 목록 양쪽에서 관측된다.

### ⑤ 면제한 이동도 버리지 않는다 (총괄 addendum)

처음 구현은 면제된 전이를 `nav`에 더하지 않는 것으로 끝냈다. 그러면 **면제가 저장된 숫자에
굳어** 되돌릴 수 없다. 배점을 잘못 잡은 것보다 나쁘다 — 가중치는 나중에 바꾸면 과거가 다시
읽히지만, 버린 카운트는 **다시 모을 기회가 없다**(소급 산출 불가). 그래서 `nav_preserved_count`를
따로 세고, 배점 `nav_preserved`(기본 **0**)로 해석한다. 오늘 점수는 완전히 동일하고, 분류가
틀린 것으로 밝혀지면 **숫자 하나만 올려** 과거 전체를 재채점한다.

```python
# 같은 저장 행, 다른 해석 — 테스트가 이 축을 직접 활성화한다
_effort(db, session=S1, key=2, mouse=1, nav=1, nav_preserved=4)
assert _stats(db)["avg_score"] == 10.0                                    # 기본 배점
assert _stats(db, weights={..., "nav_preserved": 5})["avg_score"] == 30.0  # 재채점
```

## 계측이 계측 대상을 깨뜨리지 않는다

공수 기록은 교정이 **이미 커밋된 뒤** 별도 트랜잭션으로 돈다. 실패하면 로그만 남기고 요청은
200으로 끝난다. 같은 tx가 재도달하면(클라 재시도) `transaction_id` UNIQUE 제약에 걸려
**첫 기록이 이긴다** — 재전송은 사람이 새로 쓴 공수가 아니다. (카운트 필드를 SET 의미론으로
두었다가 마지막 메시지가 총계를 덮어쓴 QA D-1의 재발 방지.)

집계 실패·타임아웃 시에는 재교정률과 **똑같이** 저하한다: 60초 TTL 캐시 + 1500ms
`statement_timeout`, 초과 시 `db.rollback()` 후 `avg_score=null` + 사유 문자열. 두 계기가 각자
rollback하므로 한쪽 실패가 다른 쪽을 오염시키지 않는다(테스트로 고정).

## 스케일 — models.py에만 선언한 인덱스는 운영 DB에서 Seq Scan이다

`audit_logs`가 이미 2.6M행/1.6GB이고 재교정률 집계가 순차 스캔에서 512ms였던 전례를
반복하지 않기 위해, 인덱스를 **`models.py`와 `scripts/setup_db_performance.py` 양쪽에**
같은 커밋으로 넣었다(`CREATE INDEX CONCURRENTLY IF NOT EXISTS` — 멱등·무중단).

| 인덱스 | 역할 | 없으면 |
|---|---|---|
| `uq_effort_transaction` | tx당 1행 불변식 | 재시도가 같은 공수를 두 번 세어 **세션 평균이 조용히 왜곡**(신호 없음 — 가장 위험) |
| `idx_effort_window` | 창 집계 커버링(`timestamp` + INCLUDE 5컬럼) | 집계가 Seq Scan → 그 칸이 `—`로 빔 |

`measured_ratio`의 분모는 **기존 `idx_audit_user_recorrection`을 그대로 재사용**한다
(`timestamp` + `INCLUDE transaction_id WHERE source_name='user'`) — 새 감사 인덱스 불필요.

## 검증

- **서버 스위트 전량 통과**(신규 53건 포함, 회귀 0) — `conda run -n assy_manager python -m pytest tests/ -q`
- **결함 주입으로 테스트의 실효성을 먼저 증명**(교훈: "새 코드 경로를 한 번도 실행하지 않는 검증으로 해소를 선언"):
  | 주입한 결함 | 결과 |
  |---|---|
  | 세션별 평균 → 순진한 tx 평균 | 2건 실패 ✅ |
  | 미계측을 `(unknown,0,0,0)`으로 강제 | 1건 실패 ✅ |
  | 400 거절 → `max(0, int(v))` 클램프 | 8건 실패 ✅ |
  | `extra="allow"` → `"ignore"` (실측 결함 재현) | 1건 실패 ✅ |
  | `nav_preserved_count`를 0으로 폐기 저장 | 1건 실패 ✅ |
- **DDL을 PostgreSQL 방언으로 컴파일 대조** — `models.py` 산출물이 `setup_db_performance.py`의
  SQL과 정확히 일치함을 확인(운영 DB에 돌리기 전에 문법·정의 불일치를 배제).

## 남은 것

- **운영 DB 인덱스 반영은 별도 승인 건**(대기열 5번과 같은 성격의 DB 쓰기). 신규 설치는
  `create_all`이 테이블과 함께 만들지만, **테이블만 먼저 생긴 DB**에는
  `setup_db_performance.py`(Step 3.7) 실행이 필요하다 → [POSTGRES_OPERATIONS §3.1](../guide/POSTGRES_OPERATIONS_GUIDE.md).
- **`context_preserving_transitions`는 비어 있다.** 항목은 라우팅 소유자(클라)가 제안하고
  총괄이 승인한다 — 서버가 채우지 않는다.
- **어드민 시각화는 이번 라운드 범위 밖**(응답 필드는 준비 완료).
