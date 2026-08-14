# The count was already computed, and the judge asked again

**Date:** 2026-08-13 22:50 · **Domain:** Server (얼라이너 성능) · **Status:** 착지 — `0859981`

---

## 배경 — 워크리스트 1.9 s, `limit=1`도 같은 값

같은 DB에 대고 단계별 실측: `resolve_reference_catalog`가 1,914 ms 중 1,836 ms —
**96%.** 그리고 **총괄의 가설 둘 다 반증됐고 레인이 그렇게 말했다**: 디스크 재읽기는
없었고(요청당 config 해석 1.4 ms), 의심하던 유닛별 채점 루프는 아예 돌지 않았다.
`831ab68`을 가리킨 것은 «형태»(호출자가 한 번에 낼 수 있는 항목별 비용)는 맞고
«항목»은 틀렸다.

## 원인 — 이미 벌크로 계산된 수를 후보마다 다시 셌다

카탈로그가 후보 212개를 심사하는데 201개가 `no_cells`로 거절되고, **거절마다
`core_wafer_map` 풀스캔 두 번**(없는 셀 읽기 + 카운트). `EXPLAIN`: Seq Scan, 24,749행
제거, 각 3~4 ms — 페이지당 약 400회 순차 스캔. 그런데 그 수는 이전 라운드의
`_count_cells_bulk`(전 후보 한 번의 GROUP BY)가 **이미 계산해서** `cell_count` 페이로드
필드에만 쓰고 있었다.

```python
def _cells_of(db, cfg, table, map_id, cap, known_count: int = None):
    ...
    if known_count == 0:  # 모든 raise 경로 뒤에 앉는다 — 거절 코드는 제자리에서 결정
```

`_load_reference`가 유일한 판정자로 남고, 움직인 것은 **수가 어디서 오는가**뿐이다.

| | before | after |
|---|---|---|
| worklist 기본 | 1.947 s | 276 ms build + 9 ms serialise |
| worklist `limit=1` | 1.792 s | 234 ms |
| `GET /references` | 1.847 s | 213 ms |

페이로드는 변경 전 스택 응답과 재귀 diff — `stats.build_ms` 외 **바이트 동일.**
정렬은 비용이 아니었음을 가정이 아니라 측정으로: `_cells_of` 플랜의 Sort는 0행 위,
3.00 ms 중 2.99가 Seq Scan. 빨강은 개수가 아니라 **노드 ID로 고정** — before/after
실패 목록 diff 공(72 대 73의 차는 선택 폭 차이, 구성원 고정이라 무영향).

## 에스컬레이션 넷 — 가져가지 않고 올렸다

- 🔴 카탈로그는 자기와 무관한 페이지의 96%다 — 자기 docstring이 rule·params·limit
  어느 것에도 안 변한다 하고 `GET /references`가 이미 서빙한다. 클라가 거기서 한 번
  가져오면 워크리스트는 ~65 ms — `selection.references` 경계 계약이라 총괄 판정 소관.
- `_load_metas`는 `ORDER BY` 없이 **마지막 행**이 이기고 `_meta_select`는 의도적으로
  **가장 오래된** 행 — 931행 = 931 고유쌍이라 «우연히» 합의 중. 수리는 런북 7항의
  UNIQUE 인덱스.
- `core_wafer_map` 메타 204행 중 `map_id`가 `wafer_id`로 실존하는 것 **3** — 그
  201이 곧 `no_cells` 거절이고 피커가 212 중 11층만 내놓는 이유. (이 관측의 해석은
  이후 `6fe74b4`에서 다시 뒤집힌다 — 이 커밋 시점의 서술이다.)
- 층 테이블 맵 키 컬럼에 인덱스 없음 — 구조적 수리는 마이그레이션의 것.

## 그때 남아 있던 것

- 커밋 자신은 수 하나의 출처만 옮겼다. 인덱스도 config도 이 커밋엔 없다 — 그 둘은
  다음 날 `4ed34a9`/`1f1b700`이 됐고, 96% 서사는 그 사이에 죽었다.
