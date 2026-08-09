# DT alignment metadata chain

## 변경

`dt_log` batch를 입력으로 기존 alignment engine의 결과를 `wafer_map_metadata`에 적재하는 체인을 추가했다.
metadata의 정체성은 `target_table="dt_log"`, `map_id=dt_job`이다. `dt_map`에는 아직 쓰지 않는다.

`alignment_view_service.resolve_alignment_view()`를 추가해 public alignment route와 chain mapper가
동일한 rule/config validation 및 `map_alignment.build_alignment_view()` 결과를 사용하게 했다. mapper는
winner/placement를 다시 계산하지 않고 `map_alignment.confirmed_meta_for()`로 완전한 `grid_metadata`를
만든다.

## 안전장치

- `state=scored`, index ranking, declared threshold, non-assumed geometry, non-truncated source/reference만 자동 기록한다.
- `dt_index` 부재로 `index_axis=absent`인 경우는 no-op이다.
- batch의 decision key가 불완전하면 범위를 넓혀 추측하지 않는다.
- 쓰기 source는 `chain_ingestion`이므로 사용자 metadata가 source priority에서 우선한다.
- mapper는 map별 DB 질의를 하지 않고 target metadata를 `_load_metas`로 한 번에 읽는다.
- 유효다이 기준은 rule의 `reference_by_job_pattern`에서 선택한다. 최초 선언은 `SYN` →
  `valid_die_ref:PRD-A_DT13`이며, 미매칭 job은 no-op이다. PRD metadata의 물리 map_id가 이 underscore 표기이므로 slash 표기를 사용하지 않는다.

## 검증

`C:\Users\kk980\anaconda3\envs\assy_manager\python.exe -m pytest server/tests/test_dt_alignment_metadata_mapper.py -q --basetemp agent_workspace/_pytest_dt_alignment -p no:cacheprovider`

결과: `3 passed`. 기존 Conda wrapper는 CP949 출력 인코딩 오류가 있어 직접 환경 Python으로 실행했다.

## 후속

`dt_inventory.dt_frame`의 JSON metadata 항등 chain과 `dt_log + dt_inventory -> dt_map`의 scoped
`replace_map`은 아직 구현하지 않았다.
