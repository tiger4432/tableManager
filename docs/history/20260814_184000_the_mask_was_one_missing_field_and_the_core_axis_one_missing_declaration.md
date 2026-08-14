# 마스크는 필드 하나가, 코어 축은 선언 하나가 비어 있었다

**Date:** 2026-08-14 18:40 · **Domain:** Server (원장 랏 뷰 · 밸리드다이 참조 · 축 선언) · **Status:** 착지 — `60c7c93`

---

## 죽은 경로 둘, 어느 쪽도 데이터 부족이 아니었다

데모 경로에서 밸리드다이 마스크가 한 번도 그려진 적이 없었고, 코어 축은 언제나
거절이었다. 조사 결과 두 결함 모두 **빠진 것이 데이터가 아니라 발화 한 줄**이었다.

**마스크.** 클라이언트는 이 커밋 시점에 이미 완전히 배선돼 있었다 —
`surprise_axis.resolveFloors`는 relation 이름만으로는 플로어 키를 만들기를 거부했고,
`referenceKey`는 `map_id` 없이는 빈 값을 돌려줬다. 서버가 내려보내던 것은
`{relation, present}`였는데, `present`는 「테이블이 존재한다」라는 **다른 질문의 답**이었다.
그래서 모든 프레임에서 모든 패널이 `mask_absent` 갈래로 갔다. 수리는 `_frame`이
`valid_die_ref.map_id`를 내보내는 것:

```python
# server/ledger_lots.py — before
"valid_die_ref": {"relation": VALID_DIE_RELATION,
                  "present": relation_exists(connection, VALID_DIE_RELATION)}
# after
"valid_die_ref": _valid_die_pointer(connection, rows[0][1])
```

포인터는 **파생이 아니라 선언에서 읽는다** — `grid_metadata.valid_die_ref`를 맵 에디터·
오버레이와 **같은 파서**(`map_overlay.parse_valid_die_ref`)로 읽어 셋이 선언의 의미에
대해 어긋날 수 없게 했다. 부수 정리로 이 파일의 `VALID_DIE_RELATION` 리터럴이
`map_overlay.VALID_DIE_TABLE` 참조로 바뀌었다 — 이미 소유자가 있는 이름의 둘째 철자를
지운 것.

**코어 축.** `core_lot`은 선언된 행 축 일곱에 없었고 서버는 `unknown_row_axis`로
거절하며 일곱을 나열했다 — **서버가 정직했던 것이지 고장이 아니다.**
`siblings_axes.json.sample`에 한 줄:

```json
{ "name": "core_lot", "label": "코어 랏", "column": "core_lot" }
```

코드 0줄로 `row=SYN-CL-001&by=core_lot&slot=01`이 `ready`가 됐다 — 소유자의 완성
기준(「선언 교체만으로 발화」)이 선언된 그날 스스로를 시연한 사례.

## DT 「갭」은 이름 하나를 쓴 세 가지였고, 갭은 하나뿐이었다

- `dt_lot`은 이 커밋 전부터 이미 답하고 있었다.
- `by=bond_lot` 아래의 거절은 도메인이다 — 본딩 웨이퍼 하나의 다이는 25개 DT 프레임에서
  온다(`frame_ambiguous_across_slots`).
- 진짜 구멍은 SYN DT 프레임 600장이 피치·오프셋·마진은 선언했는데 **웨이퍼 지름이
  없어서** 마스크 빌더가 올바르게 거절한 것.

## 시더의 두 규칙 — 하나는 첫 초안이 거꾸로 갔던 것

시드 풋프린트는 그린 모양이 아니라 `circle_die_mask`에 각 프레임의 등록 스펙을 먹인
결과다 — 그 바운딩 박스가 원 기반이 이미 내는 그 박스라서 `origin_box`가 전후 동일하고
좌표가 하나도 안 움직인다. 손으로 그린 플랫 있는 풋프린트였다면 y 박스가 잘려
`grid_start_y`가 모든 기존 소비자 아래에서 움직였을 것이다.

그리고 첫 초안이 거꾸로 갔던 규칙: **플로어를 세울 수 없는 프레임에는 참조를 찍지
않는다.** 닿을 수 없는 플로어를 가리키는 참조는 클라이언트가 패널 전체를
`origin_box_unknown`으로 거절하게 만든다 — 부분 답(격자만 그리고 「마스크 없음」)을
무답으로 바꾸는 것이다.

## 검증

- 터치한 테스트 88 passed, 10 skipped.
- 실데이터 무접촉: `BS-2601-*` 프레임 120장은 명시 마커로 스킵, 스킵 수는 매 실행 출력.
  쓰기 후 SYN 프레임 참조 선언 3,775 대 0, 실프레임 0 대 120.

## 그때 남아 있던 것

- 클라이언트 쪽 주석들은 아직 「마스크는 죽은 경로」라고 서술하고 있었다 — 같은 날 저녁
  `f21a916`이 이를 바로잡는다.
- 시더(`seed_syn_valid_die_floors.py`)가 만든 플로어의 방향 문제는 이 시점엔 알려지지
  않았다 — 같은 날 밤 `9657be7`의 자기 정정과 `c42ad05` 판정이 그 사실을 다룬다.
