# DT/Core coordinate pairing fix

## 증상

`SYN-DT-ROOT-NAB539-J10`에서 `C_X/C_Y=(21,5)`가 root floor의 0번 기준 좌표로는
유효하지 않아 보였고, `B_X/B_Y`와 `C_X/C_Y`를 같은 맵 위에 놓으면 위치가 어긋나
보였다.

## 원인

`dt_log`는 DT 좌표(`b_wx/b_wy`)와 core source 좌표(`c_wx/c_wy`)라는 독립 좌표 공간을
가지지만, 합성 시더가 두 공간의 reference cell을 독립적으로 샘플링하고 있었다.
따라서 각 행의 B/C가 같은 physical die를 가리킨다는 보장이 없었다. 해당 예시의
`C=(21,5)`는 `core_frame=rot270_back`에서 root `(5,21)`로 해석하면 유효했지만,
DT 좌표와 직접 비교하면 바깥처럼 보였다.

## 해결

`server/scripts/seed_dt_log_from_root_refs.py`를 수정해 DT floor slice를 공통
physical reference로 사용한다. 각 행은 같은 reference cell을 DT frame과 core frame에
각각 투영하고, core WF별 임의 bin 맵은 그 reference cell의 `c_bn` 선택에만 사용한다.
이제 B/C 좌표는 서로 다른 frame에 저장되지만 역변환하면 같은 root 좌표가 된다.

## 검증

- `NAB539-J10` 60행: B/C 공통 root 좌표 mismatch `0`
- DT frame 유효 다이 밖 `0`, core frame 유효 다이 밖 `0`
- `dt_log` 총 3,750행 유지, duplicate event id `0`
- 저장된 core frame이 있는 1,500행에서 B/C 공통 root 좌표 mismatch `0`; 나머지
  2,250행은 요청한 50% blank inventory 때문에 core frame 미확정 상태
- 기존 `dt_inventory` 50% blank와 8종 frame 불변
- 첫 보정 적용: `dt_log` 13,621 cells 변경(기존 행의 C 좌표/값 보정)
- 재실행: `dt_log/metadata/dt_inventory changed = 0/0/0`
- 단위 테스트 `test_seed_dt_log_from_root_refs.py`: 3건 통과
