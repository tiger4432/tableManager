# DT points outside valid-die map: reference declaration fix

## 증상

합성 `dt_log`를 맵 화면에 표시할 때 일부 점이 유효 다이 외부로 보였다. DB의
원시 좌표가 잘못 생성됐는지와 화면이 사용하는 유효 다이 기준이 다른지를 분리해
확인했다.

## 원인

`dt_log` job별 `wafer_map_metadata.grid_metadata`와 complete inventory의
`dt_frame/core_frame` JSON에 root floor를 가리키는 `valid_die_ref` 선언이 없었다.
따라서 화면은 `valid_die_ref` 대신 물리 원(circle) fallback을 사용했다. 원형
fallback과 사용자가 요청한 root floor(원형 + 하단 1셀 노치)는 서로 다른 집합이며,
rotation/back frame에서는 bbox 변환 차이도 생겼다.

원시 좌표 자체는 잘못되지 않았다.

- root floor를 각 job frame으로 변환한 유효 집합과 `dt_log.b_wx/b_wy` 대조: 바깥 0건
- complete 25개 job의 core frame으로 변환한 유효 집합과 `c_wx/c_wy` 대조: 바깥 0건
- 포인터가 없을 때 circle-only 기준으로는 DT 177건이 바깥으로 판정됨

## 해결

`server/scripts/seed_dt_log_from_root_refs.py`가 DT frame과 core frame 양쪽에 다음
선언을 기록하도록 보강했다.

```json
{"valid_die_ref": {"table": "valid_die_ref", "map_id": "NAB115_WF"}}
```

기존 50개 job metadata와 complete inventory 25개를 재적재했고, blank inventory의
의도된 빈 상태는 유지했다. 유효 다이 resolver가 참조 floor를 각 선언 frame으로
변환하므로 화면과 생성 좌표가 같은 기준을 사용한다.

## 검증

- `resolve_valid_die_set`: DT job 50/50 `ok`, `b_wx/b_wy` 바깥 0건
- complete core frame 25/25 `ok`, `c_wx/c_wy` 바깥 0건
- 기존 `dt_log` 3,750행 유지, `dt_map` 직접 쓰기 없음
- 단위 테스트: `test_seed_dt_log_from_root_refs.py` 3건 통과
- 재적재 후 시더 구조와 50% blank inventory 불변식 유지
