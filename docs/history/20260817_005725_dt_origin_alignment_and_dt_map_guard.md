# DT origin alignment and derived-map guard

## 증상

합성 root floor의 실제 최소 유효 die 좌표는 `(1,1)`인데 메타데이터 START가
`(0,0)`이라 화면에서 참조 마스크가 좌상단으로 한 칸 어긋나 보였다.

## 해결

- 다섯 root의 `valid_die_ref` 메타 START를 실제 최소 유효 die인 `(1,1)`로 정렬했다.
- 같은 기준으로 50개 DT job의 `dt_log` 좌표와 frame metadata를 재생성했다.
- B 좌표를 target frame에서 root frame으로 역투영해 모든 root floor와 일치함을 확인했다.
- `dt_map`은 계속 파생 테이블로 두고 합성 행을 쓰지 않았다.
- 기존 좌표 교체 중 outbox가 native `datetime`을 JSONB에 넣지 않도록 temporal/UUID 값을
  JSON-safe 문자열로 변환했다.

## 검증

- `dt_log` 13,700행, 50 jobs, inventory 25 complete / 25 blank.
- root별 역투영 coverage: 166/166, 210/210, 270/270, 330/330, 394/394.
- `dt_map` 합성 행: 0건.
- 관련 테스트: 6 passed.
