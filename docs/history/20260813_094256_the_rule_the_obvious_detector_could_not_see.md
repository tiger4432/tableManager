# The rule its own obvious detector could not see, and why zero violations was the finding

**Date:** 2026-08-13 09:42 · **Domain:** Ops / Architecture (스키마 정준 검출기) · **Status:** 착지 — `38b078c`

> ⚠️ **이 항목의 모든 수치는 격리 `assy_qa`와 이 박스의 개발용 `assy_manager` 실측이다.
> 둘 다 개발 사본이고, 운영의 증거가 아니다.**
>
> 앞 항목: [여덟 규칙](./20260813_090958_eight_schema_rules_and_the_clause_that_binds_the_rest_of_the_day.md)

---

## 배경 — 33분 전 문서가 자기에게 건 조건

`SCHEMA_CANON.md`는 **「검출기 없는 규칙은 규칙이 아니다」**라는 절을 달고 착지했다.
이것이 그 검출기다. 읽기 전용, apply 모드 없음, 규칙 하나하나가 **스냅샷 위의 순수
함수**다 — 고장은 스냅샷에 심고 **DB에는 아무것도 쓰지 않는다.**

## 한쪽만 주입한 알람은 알람이 아니다

고장 주입 23건, 전부 실제로 빨개지는 것을 눈으로 확인했다. 그중 **다섯이 COUNTER-케이스**다
— 검출기가 **규칙 자기 예외 위에서 «조용한지»**를 단언한다.

이유는 단순하다. **모든 후보를 위반이라고 찍는 검출기는 한쪽만 주입하는 시험을 만점으로
통과한다.** 그래서 다섯 이름을 테스트가 붙잡아 둔다 — 나중 정리가 조용히 떼어 가지
못하도록.

```python
def test_the_harness_asserts_silence_as_well_as_noise():
    """Both halves, or the alarm proves nothing.
    ...
    """
    src = io.open(canon.__file__, encoding="utf-8").read()
    for name in ("R1-counter", "R6-counter", "R5-counter", "R7-counter",
                 "MISMATCH-cnt"):
        assert name in src, f"the counter-case `{name}` is gone; the alarm is now one-sided"
```

R1의 카운터가 특히 날카롭다. **같은 컬럼을 같은 방식으로 `number`로 되돌려 놓고, 데이터만
「좌표」의 모양으로 바꿔 준다.** 그러면 검출기는 **울리면 안 된다.**

## 이 항목의 중심 — R1이 «실위반 0»으로 돌아왔다

두 DB 모두에서 R1의 실위반이 **0**이다. 그리고 그것이 발견이다.

수치형 식별자처럼 «보이는» 컬럼이 여섯 개 있었고, **여섯 다 좌표 아니면 서수**였다.
그것을 갈라 준 것은 이름도 선언도 아니라 **데이터를 찔러 본 것**이다.

```python
def probe_numeric_fill(engine, candidates, sample=20000):
    """`(table, col) -> {"sampled", "filled", "min", "max", "nonintegral"}`. READ-ONLY.

    🔴 WITHOUT THIS, R1 CANNOT TELL ITS OWN INCIDENT FROM A COORDINATE, and reporting
    both as one number is the "right arithmetic on the wrong predicate" failure. Config
    says `valid_die_ref.x` and `dt_inventory.dt_lot` are the same thing - a numeric column
    that composes a key. The DATA does not: `x` is 4,598/4,598 filled over the integers
    -20..40, and `dt_lot` was **251 rows, 0 filled** ...
    """
```

**config 입장에서 그 둘은 같은 것이다.** 갈라지는 자리는 오직 데이터다 — 한쪽은
4,598/4,598이 −20..40에 앉아 있고, 다른 쪽은 251행에 **한 칸도 안 차 있다.** 이 시스템의
lot id가 `CL_2601_005_A5`인데 수치형으로 선언된 컬럼이 한 번도 안 채워졌다는 것은,
「비어서 기다리는 컬럼」이 아니라 **애초에 못 채우는 컬럼**이라는 뜻이다.

## 그리고 여기가 오늘 하루의 술어 문제다

**뻔한 검출기는 R1의 «자기 사고»를 못 본다.**

키 선언만 보고 만든 술어를 상상해 보자 — 업무키인가, 복합 키 소스에 들어 있나, 맵 키인가.
그 술어는 위의 여섯을 **전부 거짓 위반으로** 신고하고, 그보다 나쁘게 **진짜 하나를 놓친다.**

```python
def cross_table_type_conflicts(phys, decl):
    """One column NAME, two different type FAMILIES, across tables.

    🔴 THIS IS THE ARM THAT ACTUALLY CATCHES R1's OWN INCIDENT, and the key-evidence arm
    above does not. `dt_inventory.dt_lot` is not declared a business key, is not in any
    composite source, and is not a map key - nothing in the config says it is identity, so
    a detector built only from key declarations walks straight past the exact column the
    rule was written for. ...
    """
```

`dt_inventory.dt_lot`은 **업무키가 아니고, 어떤 복합 소스에도 없고, 맵 키도 아니다.**
config 어디에도 그것이 identity라고 적혀 있지 않다. **규칙이 그 컬럼 때문에 쓰였는데,
규칙의 명시적 증거만 보는 검출기는 그 컬럼을 그냥 지나친다.**

잡아낸 것은 의미론이 아니라 **교차 테이블 타입 충돌**이었다 — 같은 컬럼 «이름»이
`bonding_log`·`dt_job_attribution`·`dt_log`에서 `character varying`이고
`dt_inventory`에서 `double precision`이다. **스키마가 한 사실을 두 종류의 것으로 들고
있고, 둘 중 하나는 반드시 틀렸다.** 이름 목록도, 도메인 지식도 필요 없다.

같은 팔이 R5의 텍스트 타임스탬프도 **독립적으로 다시 찾아냈다**(`event_time`이
`graph_edges`에선 `timestamptz`, 도메인 테이블 다섯에선 varchar).

## 이름으로 추론하는 팔을 «일부러» 안 만들었다

```python
    Anything else stays UNCLASSIFIED. There is deliberately no "it is called x so it is a
    coordinate" arm: the moment this file starts inferring meaning from spelling it can
    reach the wrong answer silently, which is the failure R1 itself is about.
```

수량의 증거도 선언에서만 가져온다 — 맵 오버레이가 선언한 축, 그리고
`<col>_base`/`_sign`/`_offset` 삼종 세트(그 자체가 `v * sign + offset`이라는 **산술
선언**이다). 나머지는 UNCLASSIFIED로 남긴다. **모르는 것을 모른다고 적는 버킷이 있는
것**이 이 검출기가 「전부 0」을 못 만드는 이유다.

## 오는 길에 잘못 신고한 것 — 이 커밋 본문 안의 오보

이 커밋 본문은 운영자 스크립트 셋이 **무장 안 된 읽기 전용 가드**로 돈다고 적었고,
스스로 재 봤다고 적었다. **그 신고가 틀렸다.** 39분 뒤 `b1dd2f0`이 뒤집는다 —
[읽기 전용 가드 항목](./20260813_102141_the_guard_was_armed_and_two_lanes_agreed_on_a_wrong_method.md).

여기 적어 두는 이유는 **이 커밋 본문이 히스토리보다 오래 남기 때문**이다. 위 문단의
측정표(`transaction_read_only = off`)는 **스크립트가 실제로 도는 모양이 아닌 배치에서
재졌다.**

## 다른 규칙들이 실제로 뭐라고 했나

| | 결과 |
|---|---|
| R7 | **살아 있는 위반.** `/view`·워크리스트 읽기 경로의 함수 일곱이 정렬 없이 상한을 건다 — 운영자가 새로고침마다 다른 셀을 보는데 **에러가 안 난다** |
| R2 | 두 DB 모두 **19/19**. 즉 마이그레이션이 여기서 한 번도 안 돌았고, **테이블별 목록은 정보를 담고 있지 않다** |
| R3 | `core_wafer_map`이 복합 소스에 없는 맵 키를 선언 — **purge가 넓어지는 모양 그대로** |
| R8 | 정준 밖 10개는 오탐이 아니라 **교차 스테이지 레지스트리**다. 정준이 안 적어 둔 예외 목록이었고, 이제 목록이 생겼다 |
| — | `assy_manager`는 아직 `dt_lot`/`dt_slot`을 안 고친 채였고 `assy_qa`는 고쳐져 있었다 — **선언만 고치고 데이터는 안 고친 상태** |

## 못 보는 절반을 «0»으로 보고하지 않았다

네 규칙은 **부분적으로만 검사 가능**하고, 리포트가 **어느 절반이 안 덮이는지**를 적는다.

- **R4**는 쓰기 «측»을 제약하지 스키마를 제약하지 않는다.
- **R5**의 뒷절반은 **config 표면이 아예 없다** — 그 부재 자체가 발견이다.
- **R7**은 AST 텍스트 스캔이라 **거짓 음성이 있다.**
- **R6**은 선언된 키는 덮지만 **파이썬에서만 필터되는 컬럼**은 못 본다.

깨끗한 0을 내는 것과 **못 보는 것을 못 본다고 적는 것**은 다른 산출물이다.

## 그때 남아 있던 것

- **R7의 위반 일곱은 이 커밋이 안 고쳤다.** 검출기는 세었을 뿐이다.
- **R2가 두 DB에서 19/19라 이 규칙의 검출기는 지금 아무것도 구별하지 못한다.**
  전부 위반이면 목록이 정보를 잃는다.
- `assy_manager`의 `dt_lot`/`dt_slot`은 이 시점에 **여전히 `double precision`**이었다.
  두 시간 뒤 `8bdc136`이 그 절반을 처리한다.
- 이 커밋의 읽기 전용 가드 신고는 **39분 뒤 뒤집혔다.** 본문은 그대로 남는다.
- `.sample`과 물리 스키마를 둘 다 판정하는데, **이 박스의 물리 스키마가 운영의 물리
  스키마라는 근거는 없다.** 이 검출기가 낸 수는 개발 두 사본의 수다.
