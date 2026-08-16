# Root-lot valid-die reference seed

## 현상

Owner DB의 `lot_event`는 80행이며 wafer identity 기준 root lot은 `NAB115`,
`NAB122`, `NAB123`, `NAB163`, `NAB539` 다섯 그룹이었다. 반면
`valid_die_ref`와 `wafer_map_metadata`는 모두 0행이라 root-lot별 유효 다이 맵을
열거나 참조할 수 없었다.

`lot_event`에는 다이 좌표나 물리 규격이 없으므로 실제 형상을 복원할 근거는 없다.
제품 소유자가 실제 맵을 참고하지 않고 15~25 범위의 비정방형 x/y 격자, 원형 WF,
하단 중앙 1셀 노치를 가진 합성 플로어를 만들도록 판정했다.

## 해결

`server/scripts/seed_root_lot_valid_die_refs.py`를 추가했다. 현 DB에서 확인한 root
집합과 선언 집합이 정확히 같을 때만 진행하며, 다음 비정방형 격자를 사용한다.

| root_lot | map_id | grid | 유효 셀 | notch |
|---|---|---:|---:|---:|
| NAB115 | `NAB115_WF` | 15×17 | 166 | (7, 15) |
| NAB122 | `NAB122_WF` | 19×17 | 210 | (9, 15) |
| NAB123 | `NAB123_WF` | 19×21 | 270 | (9, 19) |
| NAB163 | `NAB163_WF` | 23×21 | 330 | (11, 19) |
| NAB539 | `NAB539_WF` | 23×25 | 394 | (11, 23) |

형상은 공용 물리 엔진 `map_overlay.circle_die_mask`로 원형 필드를 만든 뒤, 중앙
열의 가장 아래 셀 하나만 제거한다. 제거 셀 좌우와 윗줄 3셀이 모두 존재하고 제거
셀 아래가 외부인지 검사해 하단 경계가 1셀 깊이 `ㄷ`자가 아니면 쓰기를 거절한다.

```python
notch = (centre_x, max(centre_column))
boundary = {(x - 1, y), (x + 1, y),
            (x - 1, y - 1), (x, y - 1), (x + 1, y - 1)}
if not boundary.issubset(cells) or (x, y + 1) in cells:
    raise SystemExit("REFUSED: requested notch cannot be formed")
cells.remove(notch)
```

각 플로어는 `product=<root_lot>`, `type=WF`로 `valid_die_ref`에 저장했고, 같은
map id의 `wafer_map_metadata` 등록도 함께 만들었다. 모든 쓰기는
`crud.apply_batch_updates`, `source_name=custom_script`, 1,000행 청크를 사용한다.
기존 footprint 밖 행은 삭제하지 않고 보고만 하므로 가산적·멱등적이다.

## 사이드 이펙트

- 새 동적 행은 정상 outbox와 `cell_sources` 감사 이력을 생성한다.
- 메타데이터에는 `synthetic_assumption`을 기록해 실제 측정 규격으로 오인하지 않게 했다.
- 이번 DB에는 소비할 실제 map frame이 0개였으므로 다른 테이블의
  `grid_metadata.valid_die_ref` 포인터는 만들지 않았다. 플로어 자체 등록까지만 수행했다.
- 기존 사용자 작업 파일과 기존 DB 행은 수정하거나 삭제하지 않았다.

## 검증

- 드라이런: root 5개, source 80행, 모든 격자/노치 ASCII 형상 확인.
- 단위 테스트: `server/tests/test_seed_root_lot_valid_die_refs.py` 2건 통과.
- 적용: `valid_die_ref` 1,370행, `wafer_map_metadata` 5행 생성.
- 적용 후 드라이런: 각 그룹 `already_present == expected cells`, metadata 1행,
  `outside_footprint_left_alone == 0`.
- 동일 apply 재실행: `valid_die_ref cells changed == 0`, metadata changed `== 0`.
- DB 직접 확인: 지정한 notch 좌표의 저장 행 0개.
- 값 분포: edge `E1` 252셀, interior `1` 1,118셀.
- `git diff --check` 통과.
