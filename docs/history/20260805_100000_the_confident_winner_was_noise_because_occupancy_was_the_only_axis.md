# 자신 있는 1등은 잡음이었다 — 채점 축이 점유 하나뿐이었기 때문이다

> **커밋:** `5120e35` (2026-08-05 10:00) | **일자:** 2026-08-05 오전
> **선행:** [`20260805_074000`](./20260805_074000_a_stored_coordinate_is_bounding_box_relative_and_a_catch_turned_every_failure_into_a_plausible_wafer.md)(`cab8ed9`) · [`20260805_090800`](./20260805_090800_the_decision_screen_was_specified_and_the_setup_was_specified_by_nobody.md)(`74ce8b1`)
> **담당:** map 구현 · enrichment 구현(같은 커밋)
> **대상:** **29파일 +2,314 / −223.** `server/map_alignment.py`(327) · `server/enrichment_candidates.py`(122) · `enrichment_analysis.py`(49) · `enrichment_config.py`(68) · `client2/src/map2/`(api·main·view_model) · 신규 테스트 `test_map_alignment_single_key.py`(426) · `test_system_schema_drift.py`(247)
> **스위트:** 커밋 메시지 기준 **서버 2,492 passed**, 41 하네스 중 게이트 37 초록. **diff 안에 그 결과를 기록한 산출물은 없다.**

## 배경 — 라우트가 값을 읽어 놓고 버렸다

```python
    val_col = getattr(model, b.get("val", "val"), None) if b.get("val") else None
    cols = [x_col, y_col] + ([val_col] if val_col is not None else [])
    rows = db.query(*cols).filter(*filters).limit(cap + 1).all()
```

`_cells_of`가 값 컬럼을 **SELECT까지 하고 좌표만 돌려줬다.** 그래서
`reference.kind: "values"`는 **아무도 쓰지 않는 선언**이었고, 화면은 **잡음이 만든
자신 있는 1등**을 제시할 수 있었다.

그리고 제시했다 — **`rot90_front`가 7다이 격차로 승자.** 그 픽스처의 셀은
**여덟 프레임 전부에 대해 불변인 원형 마스크**에서 뽑힌 것이라 **점유에는 방향
신호가 아예 없다.**

## 값은 더해지지, 대체하지 않는다

```python
            hits[i] = rv is not None and sv is not None and str(rv) == str(sv)
            c["value_agreement"] = int(np.count_nonzero(c["value_member"]))
```

점유는 그대로 남는다. **값 축은 자기 판별 부분집합을 따로 갖는다** — 그래서
값이 상수인 바닥은 **완전 일치이면서 판별력 0**이 되지 승자가 되지 않는다.

## 없음은 0이 아니다 — 같은 결함의 파이썬 판본

```python
        if c["keys"] is None or not scorable_values:
            c["value_member"] = None
            c["value_agreement"] = None
            c["value_discriminating"] = None
```

주석이 그 이유를 직접 적는다 — **미선언을 0으로 접으면 「구별 못 함」이 「자신 있는
1등」이 된다.** 0으로 내보내면 **「우리는 비교했고 아무것도 안 맞았다」**를
주장하게 되는데, 실제로는 비교하지 않았다.

## 구조적 사실이 임계값보다 먼저 판정된다

```python
    if (top.get(d_key) or 0) <= 0:
        return dict(base, winner=None, reason_code="no_discrimination")
    if missing:
        return dict(base, winner=None, reason_code="no_thresholds", missing=missing)
    if (top.get(d_key) or 0) < th["min_discriminating_dies"]:
        return dict(base, winner=None, reason_code="too_few_discriminating")
    if top.get(m_key) is None or top[m_key] < max(1, th["min_margin_dies"]):
        return dict(base, winner=None, reason_code="margin_too_small")
```

**임계값은 선언되지 그냥 기본값이 되지 않는다** — 부재하거나 못 읽는 키는
페이로드에서 빠지고 판정은 `no_thresholds`다.

> 동점이거나 판별이 아예 없는 경우에 운영자를 **아무것도 안 바뀔 config 편집**으로
> 보내지 않기 위해서다.

## 결과 — 개발 4단위 전부에서 자신 있는 1등이 사라졌다

**셋이 `margin_too_small`, 하나가 정직한 동점** — 그 하나는 여덟 점유 점수가
**전부 1066으로 동일**하다.

## 선언된 포인터가 아니라 **해소되는** 참조를 서빙한다

| | 건수 |
|---|---|
| 선언된 포인터 | 8 |
| 그중 해소되는 것 | **0** |
| 실제로 조사한 것 | 5 |
| 제시된 것 | **5** |

각 항목이 **자기 종류**를 달고 온다. 그래서 picker가 **값 대 점유**를 실행 한 번
쓰기 전에 보여 준다.

규칙의 정렬 마커는 **읽지 추론하지 않는다**(`strict === true`), 그리고 누구의
config에도 **소급해 채워 넣지 않는다.**

## 같은 커밋의 enrichment 절반 — 살아남은 키로 해소한다

이제 **살아남은 키 컬럼만으로** 해소하고, 쓰기에는
`enrichment_auto_confirm_partial_key` 도장이 찍힌다. **어느 셀이 온전한 키 없이
결정됐는지가 추측이 아니라 술어 하나**가 된다.

테스트가 그 도장이 `crud.SOURCE_PRIORITY`에 **없다**는 것과, 우선순위가 **사람
편집 아래**라는 것을 단언한다.

## ⚠️ diff가 커밋 메시지와 어긋난 자리

- **「정렬 작업에 변이 36건, 전부 빨강, 그중 셋은 미검증 줄을 잡았다. enrichment
  경로에 10건 더, 테스트 둘을 추가한 뒤 10건 사망」 — 그 개수를 기록한 산출물이
  diff에 없다.** 남아 있는 흔적은 테스트 안의 산문 주석 둘뿐이다
  (`Defect injection found this gap: dropping \`& value_varies\` left the suite green.` 등).
- 서버 스위트 수와 하네스 초록 여부도 기록 산출물이 없다. `check_harnesses.mjs`
  변경은 바닥값 한 칸 상향뿐이다.
- 옛 `no_margin` 갈래가 `margin_too_small`로 대체됐는데 **`no_margin`의 문구는
  표에 그대로 남아 있다.**

## 그때 남아 있던 것

- **「아무것도 채점되지 않음」이 여전히 「동점」으로 보고된다.** 후보 여덟이 전부
  0에서 동의하면 `tie`가 `no_discrimination`보다 **먼저** 반환된다 —
  약 6시간 뒤 `2fb8fc2`가 순서를 뒤집는다.
  [`20260805_155400`](./20260805_155400_nothing_scored_was_reported_as_a_tie_and_the_right_branch_was_unreachable.md) 참조.
- 해소되는 참조가 5개 제시되지만, **선언된 8개 중 해소되는 것은 여전히 0**이다.
