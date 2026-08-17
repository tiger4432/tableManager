# Synthetic DT/Core frames: front-side normalization

## 요청

합성 DT/Core frame의 `side`를 모두 `front`로 통일하고, 화면에서 보이던 frame/좌표
밀림을 제거했다. 첨부 이미지는 실행 지시가 아니라 좌표 표시 증상에 대한 시각 근거로
취급했다.

## 변경

- frame token 집합을 `rot0_front`, `rot90_front`, `rot180_front`, `rot270_front`로
  제한했다. DT/core rotation은 계속 섞되 `back`은 더 이상 생성하지 않는다.
- `dt_log`는 job별 `replace_map + scope(dt_job_id)`로 재기록해 이전 back-frame
  composite 좌표를 남기지 않는다.
- `dt_frame`, complete `core_frame`, job metadata의 `side`가 모두 `front`가 되도록
  재적재했다. blank inventory 25행은 의도대로 frame/equation을 비워 두었다.
- unchanged row의 `event_time`은 재전송하지 않아 datetime source 표현 차이로 인한
  replay churn을 방지했다.

## 검증

- `dt_log=3,750`, job=50, inventory=50, blank inventory=25
- DT metadata back-side 행 `0`, complete core frame back-side 행 `0`
- 모든 DT 좌표 유효 die 밖 `0`, complete core 좌표 유효 die 밖 `0`
- 저장된 core frame이 있는 1,500행의 B/C 공통 root 좌표 mismatch `0`
- `SYN-DT-ROOT-NAB539-J10`의 문제로 제시된 `C=(21,5)` 행 `0`
- 단위 테스트 3건 통과, py_compile 및 diff-check 통과
- 최종 재실행: `dt_log/metadata/dt_inventory changed = 0/0/0`
