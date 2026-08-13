# A clean scan produced no run, because the two halves were correct apart

**Date:** 2026-08-13 13:22 · **Domain:** Server (void 스키마 / 인제션) · **Status:** 착지 — `346aa88`

> ⚠️ **실물 SAT 파일을 한 번도 본 적이 없다.** 헤더 철자는 대소문자·구분자 접기 별칭이고,
> `# key: value` 런 메타데이터 블록은 **지어낸 것**이다 — 제품 소유자가 넘긴 여덟 컬럼에
> 시각·레시피·설비가 **없기 때문**이다. 검증은 전부 격리 `assy_qa`다.

---

## 배경 — 「보이드 0건」과 「스캔 안 함」이 같은 부재였다

같은 날 12:29의 제안(`90f13a0`)이 DDL 없이 닫혀 있었고, 이 커밋이 그것을 물리 선언으로 세운다.

제품 소유자의 SAT 출력은 여덟 컬럼이다 — `base wafer id · base_x · base_y · inchip_x ·
inchip_y · gate · radius_x · radius_y`. 이 여덟은 **어디**와 **얼마나 크냐**만 말한다.
수율이 필요로 하는 셋째 것 — **분모** — 은 말하지 못한다.

그래서 테이블이 **둘**이다. `inspection_run`은 **일어난 스캔 하나당 한 행**이고,
`void_obs`는 **그 스캔이 본 보이드 하나당 한 행**이다. `bonding_log`에 `void_yn` 컬럼을
붙이는 안이 기각된 이유가 여기다 — 그 컬럼은 「스캔했는데 깨끗했다」와 「스캔한 적이
없다」를 **구별하지 못하고, 둘 다 «정상»으로 읽힌다.**

## 등급은 저장되지 않고, 이제 «물리적으로» 저장될 수 없다

두 테이블의 `column_types`를 통틀어 `grade`·`pass`·`fail`·`verdict`·`area`·`yield` 중 어떤
이름과도 맞는 컬럼이 **없다.**

```json
"void_obs": {
  "business_key": "void_uid",
  "composite_key_source": ["run_uid", "inchip_x", "inchip_y"],
  "column_types": {
    "void_uid": "string", "run_uid": "string",
    "base_wafer_id": "string", "base_x": "number", "base_y": "number",
    "stack_gate": "number", "inchip_x": "number", "inchip_y": "number",
    "radius_x": "number", "radius_y": "number", "unit": "string"
  }
}
```

합불은 `면적 > 임계값`이고 임계값은 **레시피 파라미터**다. 판정을 저장하면 임계값이 움직였을
때 과거를 재판정할 수 없고, 5% 레시피의 FAIL과 10% 레시피의 FAIL이 같은 칸에 들어간다.
면적조차 컬럼이 아니다 — 「X보다 큰 것」 질의는 **표현식 인덱스**가 받는다
(`add_void_schema_indexes.sql`의 `idx_void_obs_area`, `pi() * radius_x * radius_y`).

## 키가 «못 하는 것»을 나중에 발견하지 않고 지금 적었다

`run_uid = method|base_wafer_id|base_x|base_y|stack_gate|observed_at`.
한 패키지가 동시에 두 장비 안에 있을 수 없으므로 **물리적으로** 유일하다.
`recipe_id`/`eqp_id`는 기록되지만 **키 재료가 아니다** — 오타 난 레시피를 고쳐 재전달한
파일이 런을 **갱신**해야지, 두 번째 런을 만들어 자기 보이드들을 고아로 만들면 안 된다.

`void_uid = run_uid|inchip_x|inchip_y`. 🔴 **이 키는 런을 가로질러 같은 보이드를 재식별하지
않는다.** 알고리즘이 찾은 중심좌표가 비트 단위로 반복될 리 없으므로 두 스캔은 두 행을 만든다.
그리고 🔴 **소스의 `observed_at` 해상도가 재스캔 간격보다 거칠면 두 번째 런이 첫 번째와
충돌하고 분모가 조용히 하나를 잃는다** — 선언 안에 그렇게 적혀 있다.

`stack_gate`가 문자열이 아니라 수치인 이유는 층 순서가 산술이기 때문이다(`"10" < "3"`).
그 대가로 `double precision`은 3.5층을 금지하지 못하므로 **파서가 비정수 gate를 거절한다**
(`REFUSAL_NON_INTEGRAL_GATE`).

## 검증이 찾아낸 두 결함 — 둘 다 «성공처럼 읽혔다»

**① 깨끗한 스캔이 런을 아예 만들지 못했다.** `_package_from_header`가 헤더에서 네 키를 읽는데
`parse_run_header`가 그 넷을 **쓴 적이 없었다.** 양쪽 반쪽은 **따로 보면 각각 옳았고**, 실패는
조용했다. 그리고 이 실패의 대상이 하필 **이 두 테이블 설계가 존재하는 이유인 바로 그 행**이다.

```python
_PACKAGE_KEYS = ("base_wafer_id", "base_x", "base_y", "stack_gate")

def _package_from_header(header_meta: dict, void_rows: list):
    """헤더를 먼저 보는 것이 «빈 경우»에 결정적이다 — 보이드를 못 찾은 스캔에는
    읽을 행이 없고, 그것이 바로 착지해야 하는 런이다."""
    if all(header_meta.get(k) not in (None, "") for k in _PACKAGE_KEYS):
        ...
```

수리는 `_RUN_ALIASES`가 그 네 키를 **`_ALIASES`와 같은 별칭 표에서** 가져오게 한 것이다 —
`# gate: 3`과 `gate` 컬럼이 같은 뜻이 되도록. 회귀는 이름 붙은 테스트로 고정됐다:
`test_a_scan_that_found_nothing_still_produces_a_run`.

**② 소수점 콤마가 뒤의 모든 컬럼을 한 칸씩 밀었다.** CSV에서 `1,25`는 「"1,25"를 담은 한 필드」가
아니라 **두 필드**다. 밀린 값들은 여전히 **완벽하게 유효한 숫자**라서 아무것도 raise하지 않고,
`radius_x`가 실은 `radius_y`였던 값을 들고 적재된다. **어떤 수치 검사도 여기서 울릴 수 없다.**

```python
class MisalignedRow(ValueError):
    """헤더와 필드 개수가 다른 데이터 행. 실패하는 테스트가 찾아냈다.

    🔴 문제가 되는 경우는 소수점 콤마다. ... 밀린 값들이 여전히 완벽하게 유효한
    숫자라서 아무것도 raise하지 않는다 ... arity 비교가 그것을 잡는 싼 검사이고,
    잘린 행(쓰기 중단)도 같은 테스트에서 떨어진다."""
```

## 🔴 알려진 이음새 — 보이드는 아직 자기 층의 다이에 닿지 못한다

`void_obs`는 `(base_wafer_id, base_x, base_y, stack_gate)` — **웨이퍼 정체성** — 으로 키가
잡혀 있고, `bonding_log`는 `(bond_lot, bond_slot, bond_x, bond_y)` — **카세트 위치** — 다.
**둘은 조인되지 않는다.** 총괄이 두 레인을 **서로 다른 정체성 어휘로** 내보낸 결과이고, 커밋이
그것을 자기 것으로 적었다.

## 아키텍처 영향

- 두 테이블은 이 SQL 파일이 만들지 않는다. `table_config.json` 선언 + `POST /admin/reload-configs`가
  `models.create_missing_dynamic_tables`를 돌려 만든다. 마이그레이션은 **그 «다음»**이고,
  아니면 `relation "void_obs" does not exist`로 크게 실패한다 — 손으로 여기서 만들면 config가
  이미 소유한 모양의 **두 번째, 어긋난 정의**가 생긴다.
- 모든 인덱스가 `CONCURRENTLY`다(여기서의 잠금은 인제션 레인의 정지다). 그 대가로 트랜잭션
  블록 안에서 못 돌고, 중단되면 **INVALID 인덱스**가 남아 쓰기 비용만 물고 읽기는 못 준다 —
  확인 쿼리가 파일 주석에 있다.
- 🔴 **`.sql` 파일은 잘못된 «데이터베이스»를 거절하지 못한다.** `psql`은 가리키는 곳에 붙는다.
  파일이 그 사실을 감추지 않고 적었다 — 두 문장 모두 추가·`IF NOT EXISTS`라 잘못된 대상의
  폭발 반경은 「안 쓰이는 인덱스」다.
- 로직이 gitignore되는 플러그인이 아니라 **추적되는 `void_sat_format.py`**에 산다. 수리가
  `git pull`이 되고 손복사는 3줄짜리 shim뿐이다. 레지스트리 편집은 필요 없었다 —
  워처가 `<workspace>/<table>/scripts/*.py`를 훑는다.

## 그때 남아 있던 것

- 7파일 +1,485/-0. `void_sat_format.py` 680줄, 테스트 451줄.
- **운영에는 아무것도 없다.** `server/config/*`는 설계상 gitignore라 `git pull`이 선언을
  실어오지 않는다 — 운영자가 `.sample`에서 두 선언을 **손복사**해야 테이블이 생긴다.
  절차는 같은 날 `e662ff9`의 운영 런북 4번 항목으로 들어갔다.
- `DEFAULT_UNIT`은 `None`으로 출하됐다 — 단위 없는 파일은 **추측되지 않고 거절된다.**
- 위 이음새 때문에 **보이드를 자기 층의 다이에 붙이는 일은 되지 않는다.** 커밋은 그것이
  week 2를 막고 ledger slice 1은 막지 않는다고 적었다.
- 검증: 커밋되는 트리에서 33 passed. 격리 `assy_qa`에서 실제 워처·실제 읽기 라우트를 통한
  E2E 37/37을 **연속 3회**. 소스 변이 6종 주입 6/6 빨강, 소스는 바이트 단위로 복원.
  유니크 인덱스를 떨구자 중복이 들어왔고 재생성하자 다시 거절했다.
- 위 두 결함과 「헤더 블록은 지어낸 것」이라는 사실은 같은 날 보드(`78302c8`)에도 기록됐다.
