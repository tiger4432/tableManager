# DT snake index order correction

## 증상

partial DT job이 `floor[::2]` 방식으로 선택돼 화면 진행이 건너뛰는 형태였다.

## 해결

- 유효 die를 최상단 행의 우측부터 시작해 행마다 좌우 방향을 번갈아 바꾸는
  지그재그 순서로 정렬했다.
- partial job은 이 경로의 연속 half-prefix만 사용한다.
- `dt_index`는 core WF를 번갈아 배정하면서도 전체 지그재그 경로 순서를 유지한다.

## 검증

- full 34개, partial 16개 유지.
- 16개 partial job 모두 역투영 경로가 snake prefix와 일치.
- `dt_log` 11,510행, `dt_map` 합성 행 0건.
- 관련 테스트 5 passed.
