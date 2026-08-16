# Synthetic multi-core DT log seed

## 요청과 범위

기존 root-lot별 `valid_die_ref` 합성 플로어를 기반으로 각 core WF에 결정론적
임의 bin 맵을 부여하고 DT 진행 로그를 만들었다. 현재 선언된 스키마에는 별도
`core_wafer_map` 테이블이 없으므로 core 맵은 `dt_log`의
`(core_wafer_id, c_wx, c_wy, c_bn)` 튜플로 표현했다. `dt_map`은 파생 테이블이라
직접 작성하지 않았다.

## 생성 결과

- root 5개, root당 core WF 25개를 3장/2장 반복 그룹으로 묶어 DT job 50개를 생성했다.
- 모든 DT job은 core WF 2~3장을 포함하며, 125개 core WF는 각각 정확히 한 job에 사용됐다.
- job당 60행(2 core) 또는 90행(3 core), 총 `dt_log` 3,750행을 생성했다.
- 각 core WF에는 root floor 전체에 대해 `B1`~`B4` 중 하나를 결정론적으로 선택하는
  임의 bin 맵을 만들고, job 로그에는 core당 30개 좌표를 기록했다.
- `wafer_map_metadata`에 DT job별 frame metadata 50행을 등록했다. DT/core frame은
  서로 다르고, `rot0/90/180/270` × `front/back` 8종을 모두 사용했다.
- `dt_inventory` 50행 중 25행은 frame/equation 필드를 완전히 비워 두고 identity
  (`dt_job_id`, 장비, lot, slot)만 남겼다. 나머지 25행은 frame과 12개 equation
  필드를 채워 정확히 50% 미완료 상태를 만들었다.

## 안전성과 검증

- 모든 DB 쓰기는 `crud.apply_batch_updates`, `source_name=custom_script`로 수행했다.
- `dt_log`, `dt_inventory`, metadata의 `SYN-DT-ROOT-` 소유권 충돌을 사전 거부한다.
- 동일한 composite key와 값이 이미 있는 `dt_log` 행은 재전송하지 않도록 시더를 보강해
  재실행 시 `dt_log/metadata/dt_inventory changed = 0/0/0`을 확인했다.
- 최초 적용 변경량: `dt_log` 52,500 cells, metadata 200 cells,
  `dt_inventory` 900 cells.
- DB 확인: `dt_log=3,750`, job=50, inventory=50, blank inventory=25,
  `dt_map=0`, 잘못된 bin/좌표/identity=0.
- 단위 테스트 `server/tests/test_seed_dt_log_from_root_refs.py`: 2건 통과.
