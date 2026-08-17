# Mixed full and partial DT coverage

## 요청

합성 DT 로그를 전부 full map으로 만들지 않고 일부 job은 유효 die의 일부만
채우도록 구성했다.

## 적용

- 전체 50개 job 중 34개는 full coverage.
- 16개는 `floor_cells[::2]`로 선택한 결정론적 half-floor coverage.
- 각 job의 DT/core frame metadata에 `synthetic_coverage`를 기록했다.
- 2/3개 core WF/job, front-only frame, inventory 25 complete / 25 blank는 유지했다.
- `dt_map`은 파생 테이블이므로 계속 0건이며 직접 적재하지 않았다.

## 검증

- `dt_log`: 11,510행.
- partial job 행 수는 root floor의 정확한 절반이며 누락/초과 0건.
- synthetic `dt_map` 행 0건.
- 관련 seeder 테스트 7 passed.
