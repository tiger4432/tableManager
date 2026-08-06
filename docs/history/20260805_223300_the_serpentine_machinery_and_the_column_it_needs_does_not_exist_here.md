# 순번 기계장치 — 정렬이 통계에서 정확으로 옮겨 갔다. 그리고 그것이 필요로 하는 컬럼이 이 박스에 없다

> **커밋:** `ad2855e`(2026-08-05 22:33) | **일자:** 2026-08-05 밤
> **선행:** [`20260805_155400`](./20260805_155400_nothing_scored_was_reported_as_a_tie_and_the_right_branch_was_unreachable.md) · [`20260805_202400`](./20260805_202400_the_ruling_was_unreachable_and_the_theorem_says_weights_can_never_break_it.md)(`6541f45` — **이 커밋이 대체하는 근사들의 마지막 판**)
> **후속:** [`20260806_011956`](./20260806_011956_an_absent_index_column_is_a_declared_absence_and_reading_stopped_asking_permission.md)(`74ec741` — **여기서 없다고 적힌 그 컬럼을 바인딩이 나르게 만든 커밋**)
> **담당:** **제품 소유자(방법 자체를 자기 말로 서술했다)** · server 구현
> **대상:** `server/map_alignment.py`(+270 / −11) · `server/tests/test_map_alignment.py`(+156)
> **스위트:** 커밋 메시지 기준 **서버 2,733.**
> ⚠️ **여기 나오는 픽스처는 전부 레인이 지은 합성이고 테스트 파일 머리가 그렇게 적고 있다.** 이 박스의 `dt_log` 행들도 자기 config 주석이 합성 트레이스 픽스처라고 말한다. **아래 어느 숫자도 운영 측정이 아니다.**

## 🔴 제품 소유자가 방법을 자기 말로 서술했다

> **`dt_index`가 DT 맵을 지그재그(serpentine)로 걷는다. 픽은 bin으로 묶인다.
> 순서 위반이 가장 적은 프레임이 이긴다.**

이것이 **오늘 시도한 모든 근사를 대체한다** — 점유 카운트, 값 가중, 경계 가중,
시프트 탐색.

**왜 근사가 아니라 정확인가:** **순서(ordering)는 집합(set)보다 훨씬 더 제약된
대상**이다. 그리고 **경계 접촉이 필요 없다** — 경계 접촉이 앞선 방법들이 부딪힌
바로 그 한계였다.

## ① 순번은 순수 함수이고 규칙 셋이 **따로** 못 박혔다

```python
def serpentine_index(cells, top_is_min_y: bool = True) -> dict:
```

반환은 **`{index: (x, y)}`**다 — 채점이 묻는 것은 **「k번이 어디여야 하나」**이지
그 역이 아니다.

| 규칙 | 테스트 |
|---|---|
| 교대(alternation) | `test_the_serpentine_alternates_and_starts_at_the_top_left` |
| **빈 행은 방향을 뒤집지 않는다** | `test_an_empty_row_does_not_flip_the_direction` |
| **행 안의 구멍은 순번을 소비하지 않는다** | `test_a_gap_inside_a_row_consumes_no_index` |

셋을 **한 테스트에 묶지 않았다.** 하나가 깨질 때 어느 것인지 말해야 한다.

## ② 「위」는 가정이 아니라 **기준 자신의 y반전에서 유도**한다

```python
    expected_by_index = serpentine_index(
        ref_pairs, top_is_min_y=not bool((reference_meta or {}).get("grid_y_invert")))
```

`test_top_is_derived_from_the_reference_and_not_a_constant`가 이것을 채점한다.
**실제 바닥에서 두 읽기가 마흔 행 떨어져 있기** 때문이다 — 상수로 박으면 정확한
방법이 정확하게 틀린 답을 낸다.

## 🔴 ③ 그런데 입력이 없다 — 그리고 그것을 숨기지 않았다

**`dt_index`는 이 박스에 존재하지 않는다.** 테이블 config에도, 라이브 테이블에도,
원본 이송 로그에도 없고, **저장소의 어느 파일도 그 이름을 대지 않는다.**
`event_time`은 8,700행에 걸쳐 **서로 다른 값이 여섯 개**뿐이라, 행마다 얻을 수 있는
유일한 순서는 **CSV 행 순서**다.

그래서 그것에 대고 걷기를 돌렸고, **숫자가 그것이 픽 순서가 아니라고 분명히 말한다.**

| | |
|---|---|
| 올바른 프레임이 내야 할 최대 split | **120** (bin 둘 × job 120) |
| 관측된 최선 | **2,422** |
| 두 걷기의 승자 | **서로 다르다** |
| core 쪽 스프레드 | **2%** — 잡음 |

**기계장치가 눈먼 것이 아니다** — DT 쪽에서 2.5배 스프레드를 낸다. **이 데이터에
걸을 순서가 없을 뿐이다.**

> **그 위에 얹은 채점기는 만들지 않았다.**

## ④ 기존 스위트가 이 작업의 진짜 결함을 잡았다

채점기가 **인덱스를 셀 개수만큼 `None`으로 패딩**한다. 그래서 **순번 컬럼이 없는
테이블이 「전부 `None`인 꽉 찬 리스트」로 도착하고 「인덱스 있음」으로 읽혔다.**
여덟 후보 전부 0점이 됐고, **순번 축이 다른 축들보다 서열이 높아서 그 0이 점유
판정을 밀어냈다.** **테스트 25건이 빨개졌다.**

```python
    if (source_indices and expected_by_index
            and any(k is not None for k in source_indices)):
```

> **부재가 0으로 접혔다 — 갓 만든 축에서, 그 함정을 세 번이나 경고하는 바로 그
> 모듈 안에서.**

## ⑤ 면(side)은 선언 가능하고, 좁히는 것은 **탐색**이지 **보고**가 아니다

**여덟 후보는 언제나 전부 발행된다.** 제외된 것들은 **자기 상태를 달고 「고려되지
않았다」고 말한다.**

> **한 번도 보지 않은 후보가 진 후보처럼 읽혀서는 안 된다.**
> 결과를 숨기지 않는다는 서 있는 규칙을, **넷만 보내는 것이 가장 쉬웠을 자리에**
> 적용한 것이다.

`test_a_narrowed_side_is_reported_as_unconsidered_not_as_a_loser` ·
`test_an_unconsidered_candidate_cannot_win` ·
`test_undeclared_sides_leave_the_candidate_list_exactly_as_it_was`.

## ⑥ 임계값은 넘어오지 않는다 — 단위가 다르다

기존 임계값은 **다이(dies)를 센다.** split 카운트는 **위반(violations)을 세고
작을수록 좋다.** 재사용하면 **가중 주석이 이미 경고하는 단위 표류를 반복**한다.

> 그래서 순번 경로는 **자기 선언**을 갖고, **이 커밋은 그 숫자를 하나도 발명하지
> 않았다.**

## 그때 남아 있던 것

- **정확한 방법은 서 있고 그것을 먹일 데이터가 없다.** `dt_index`를 바인딩이 나르게
  하는 것은 다음 날 `74ec741`이고, 그 커밋은 **없는 순번 컬럼을 관례 이름으로
  채우지 않는다** — 채우면 실재하지 않는 컬럼이 「선언됨」으로 서빙되고
  **조용히 0건 일치를 내며 「번호가 안 맞았다」로 읽힌다.**
- 이 시점 **순번 축은 채점기 안에 있고, 그것을 켜는 선언은 어디에도 없다.**
