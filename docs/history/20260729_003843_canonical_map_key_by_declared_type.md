# `LOT_01`과 `LOT_1`은 같은 웨이퍼였다 — 맵 정체성에 캐노니컬이 생겼다

> 커밋 `ab6ac02` · 2026-07-29 00:38 · 도메인 Server(맵 정체성 합성 · 가용 풀 바인드)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 선언: [transfer_plan_config](../guide/config/transfer_plan_config.md)
> **동반 항목** (같은 야간 배치의 다른 두 갈래): [transfer_log "none"](./20260729_004000_transfer_log_none_declared_untracked.md) · [인제션 맵 메타 자동 등록](./20260729_004200_ingestion_map_meta_auto_registration.md)

## 배경 — 셀 필터만 살아남은 이유

운영 실측(2026-07-28)에서 나온 결함이다. `number`로 선언된 slot 컬럼은 값을 `1`로
저장한다. 그런데 파서가 만든 자재 토큰은 `'01'`을 공급한다. 원본 값으로 맵 정체성을
합성하면 `LOT_01`이 나오는데, 메타 행은 저장값 기준으로 `LOT_1`에 등록돼 있다 —
조회는 **조용히 빗나간다**. 메타가 None이면 에러가 아니라 정렬 강등이라, 화면에는
"화면기준" 칩이 뜰 뿐이다. 같은 패딩이 가용 풀 바인드도 깨뜨려 count가 0으로 나왔다.
Float 왕복이라는 축도 있었다: number 선언 컬럼을 ORM이 `1.0`으로 돌려주면 `LOT_1.0`이
합성된다.

셀 데이터 필터만 멀쩡했다. crud가 **선언된 컬럼 타입으로 캐스팅**하기 때문이다. 즉
이 시스템은 이미 옳은 규율을 한 곳에 갖고 있었고, 정체성 합성과 풀 바인드에는 없었다.

가장 나쁜 자리는 **등록 측**이었다. 캐스팅 전 원본 `'01'`이 들어오면 메타를 `LOT_01`로
등록하는데 셀은 `1`로 캐스팅되므로, 그 맵은 그 후 **영원히 찾을 수 없다**.

## 변경 내용

### 하나의 캐노니컬 함수, 선언 타입이 지배한다

```python
# server/map_overlay.py — canonical_key_value, 이 커밋 시점
def canonical_key_value(value, col_type):
    """값 + **선언된** 컬럼 타입 -> 캐노니컬 키 문자열."""
    if value is None:
        return None
    if col_type == "number" and not isinstance(value, bool):
        ...
        s = str(value).strip()
        if _CANON_INT_RE.match(s):
            return str(int(s))
        try:
            f = float(s)
        except (TypeError, ValueError):
            return s      # 읽을 수 없으면 trim된 원본 유지 — 없는 키를 발명하지 않는다
        ...
    return str(value).strip()   # string/미선언: trim만
```

규율은 세 줄이다. `number`는 정수 파싱(`'01'` · `' 1 '` · `1.0` · `'1.0'`이 전부 `'1'`,
`'7.5'`는 보존) — 프로젝트의 단일 정수 판정 의미론을 따른다. `string`·미선언은 trim만
(문자열에서 패딩은 **데이터다**, 스펙상). 그리고 읽을 수 없는 값은 원본을 유지해
**조회가 정직하게 빗나가게** 한다 — 그럴듯한 키를 만들어 엉뚱한 행에 착지시키는 것보다
빗나가는 편이 낫다.

### 합성은 "조회 대상 테이블"의 타입으로 한다

```python
# server/map_overlay.py — compose_map_id, 이 커밋 시점
for k in identity_cols:
    v = values.get(k, "")
    if isinstance(binding, dict) and isinstance(binding.get("table"), str):
        col = (binding.get("columns") or {}).get(k, k)
        v = canonical_bind_value(binding["table"], col, v)   # 선언 타입 조회 후 캐노니컬
    parts.append("" if v is None else str(v))
return "_".join(parts)
```

`binding`이 인자인 이유가 핵심이다. 메타 행은 **그 테이블의 저장값**으로 등록됐으므로,
합성도 그 테이블의 선언 타입으로 캐노니컬해야 한다. 같은 (lot, slot) 쌍이 소스 테이블마다
다르게 캐노니컬될 수 있고 그게 맞다 — `transfer_plan._origin_map_id`가 프레임 정의
테이블용과 fail 테이블용으로 각각 합성하게 바뀐 것이 그 결과다.

라우팅된 곳은 합성 4곳(`transfer_plan._origin_map_id`, `bonding_plan.get_core_summary`,
`map_meta_registrar.compose_map_id`, `map_overlay.build_key_filters`)과 가용 엔진의
`(lot, slot)` 풀 바인드 16곳이다. 등록 측(`map_meta_registrar`)이 포함된 것이 중요하다 —
같은 야간 배치의 M3 에이전트가 그 자리에 `TODO(7b)`와 **재라우팅이 무연산임을 증명하는
핀 테스트**를 남겨 두었고, 그 핸드오프대로 라우팅됐다. 이게 없었으면 인제션은 조회 측이
캐노니컬로 지워 내는 바로 그 정체성을 계속 **등록**했을 것이다.

## 아키텍처 영향

"맵 정체성이 무엇인가"의 답이 처음으로 한 곳에 모였다. 종전에는 합성 사이트마다 각자
`"_".join(str(...))`을 했고, 그래서 사이트마다 다른 정체성을 만들 수 있었다. 이제 그
질문은 `canonical_key_value` 하나로 수렴하고, 함수 주석에 "두 번째 구현을 만들지 마라"가
못 박혀 있다.

그리고 이 커밋은 **경계 계약을 지키느라 일부러 고치지 않은 자리**를 남겼다. 통째로
넘어오는 `map_key`/`target_key`(클라가 합성해 보내는 불투명 정체성)는 캐노니컬하지
않는다 — 서버가 불투명 문자열을 안전하게 분해할 수 없기 때문이다(lot 이름에 `_`가 들어갈
수 있다). 이 축의 수리는 합성 시점, 즉 클라 쪽에서 이뤄져야 한다.

## 검증

| 무엇을 | 어떻게 | 결과 |
|---|---|---|
| 신규 테스트 | `test_key_canonicalization.py` 28 + `test_transfer_untracked.py` 11 | 39건 |
| 뮤테이션 | 소스 레벨 3종 주입 후 되돌림 | 전부 검출 |
| 전체 스위트 | conda `assy_manager` | 944 passed (세션 시작 753) |
| 라이브 | 격리 포트 read-only 실측, 쓰기 0건 | 패딩 토큰 `' 01 '`이 256칩 풀을 찾음 |

**뮤테이션 축 선택이 이 라운드의 함정이었다.** SQLite의 numeric affinity가 Float 컬럼에서
`'01'`·`' 1 '`을 조용히 변환해 버린다 — 바인드 캐노니컬 뮤턴트가 SQLite의 number 컬럼에서는
**보이지 않는다**. 그래서 뮤테이션 축을 엔진 독립적인 것(합성된 정체성의 문자열 동등성,
string 선언 컬럼의 공백)으로 골라야 했다.

## 그때 남아 있던 것

- **클라가 합성해 보내는 키는 그대로였다.** 클라가 `LOT_01`을 만들어 보내면 메타
  `LOT_1`에 대해 여전히 빗나간다. 이 커밋은 서버 절반이었다.
- **표현 교차 문자열 풀**(string 선언 컬럼이 `'1'`을 저장하는데 `'01'`로 질의)은 어느
  절반으로도 고칠 수 없다 — 스펙상 문자열 패딩은 데이터이므로 선언 변경만이 해법이다.
- 이 개발 머신은 맵 키 컬럼을 전부 `string`으로 선언하고 있어 **로컬 동작 변화가 0**이었다.
  number 선언 축은 운영 사이트의 모양이고, 이 커밋 시점 그 축을 지키는 것은 라이브 관측이
  아니라 테스트다.
- `bins` lot 스코프 병합 등 일부 소비자는 이 커밋 범위 밖이었다(동반 항목 참조).
