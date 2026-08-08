# `no_winner`가 순번 값 부재를 말하게 함

**날짜:** 2026-08-08 15:30 KST  
**영역:** Map Alignment / 정렬기 거절 문구  
**등급:** T2

## 문제

`dt_index` 컬럼은 선택됐지만 소스 셀 값이 모두 NULL인 라이브 실행에서 순번 축은
`index_axis=absent`, 앵커는 `no_index_values`가 됐다. 기존 `no_winner` 문장은 마진 부족만
말해 문턱을 낮추라는 잘못된 다음 행동으로 이어졌다.

## 변경

- `server/map_alignment.py:compose_refusal`이 위 인과쌍일 때만 `dt_index` 값 부재와 순번
  채우기라는 수리를 반환한다.
- 다른 마진 부족·동점 `no_winner`는 기존 `_ruling_text` 경로를 유지한다.
- `server/tests/test_map_alignment.py`에 두 갈래를 함께 고정했다.
- 정본 동작 문서를 `docs/spec/MAP_ALIGNMENT_SPEC.md`에 갱신했다.

## 검증

`conda run -n assy_manager pytest server/tests/test_map_alignment.py -q`

