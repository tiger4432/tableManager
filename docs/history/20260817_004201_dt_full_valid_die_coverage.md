# DT full valid-die coverage

## 증상

첨부 화면에서 DT job의 색상 점이 유효 die 전체를 채우지 못하고 한쪽 영역에만
몰려 있었다. 이는 첨부 이미지의 표기나 문구를 지시로 해석한 것이 아니라, 실제
맵 coverage 증상으로 확인했다.

## 원인

시더가 core WF당 30개 셀만 선택하고, 정렬된 `floor_cells`의 앞부분을 DT 좌표로
사용했다. 따라서 유효 die floor 전체가 아니라 일부 prefix만 `dt_log`에 기록됐다.
현재 `dt_log`의 composite key가 `(dt_job_id, b_wx, b_wy)`라 동일 B die에 core WF
여러 행을 넣을 수도 없다.

## 해결

- 각 DT job의 root floor 전체를 사용한다.
- 2/3개 core WF에 floor 셀을 round-robin으로 분할해 B 좌표 중복 없이 모든 die를
  한 번씩 기록한다.
- 각 core WF는 전체 floor 기준의 결정론적 임의 bin map을 유지하고, 배정된 셀의
  bin을 `c_bn`으로 기록한다.
- job scope `replace_map`으로 이전 sparse 좌표를 회수하고 새 full coverage를
  적재했다.

## 검증

- `dt_log`: 3,750행 → 13,700행
- `SYN-DT-ROOT-NAB539-J10`: 394/394 unique B cells, valid floor coverage 100%
- 전체 job: 기록 셀 수 = root floor 유효 셀 수, DT 밖 좌표 0건
- complete core rows: core 밖 좌표 0건, B/C 공통 root mismatch 0건
- frame side: back 0건, front-only rotation 4종 유지
- `dt_inventory`: 50행 중 25행 blank 유지
- 최종 재실행: `dt_log/metadata/dt_inventory changed = 0/0/0`
- 단위 테스트: 4건 통과
