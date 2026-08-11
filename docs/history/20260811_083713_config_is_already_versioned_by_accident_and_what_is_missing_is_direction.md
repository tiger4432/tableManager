# 정의는 이미 우연히 버전 관리되고 있었다 — 없는 건 방향과 병합 규칙이었다

**날짜:** 2026-08-11 08:37 · **커밋:** `c723585` · **레인:** 문서(연구, ontology-pm) + 서버(계측 도구)
**측정 상자:** 이 워크스테이션의 격리 DB `assy_qa`. **운영이 아니다.**

---

## 배경

테이블 스키마와 온톨로지/config 선언이 환경을 어떻게 건너가는지에 대한 연구 라운드다.
문서 자신이 상태를 명시한다: **연구·제안, 미확정. 코드·config·마이그레이션을 하나도
바꾸지 않았다.**

## 결론 — 두 문제가 아니라 같은 결함의 두 얼굴

구조 변경(스키마 컬럼, 온톨로지/config 선언)이 환경을 이동할 때, **그 변경이 무엇을
무효화했는지 말해 주는 것이 같이 이동하지 않는다.** 이 저장소는 이미 그 대조 메커니즘을
세 조각으로 갖고 있다 — 새로 발명할 게 아니라 일반화가 남았다는 것이 이 문서의 권고다.

| 이미 있는 조각 | 무엇을 하는가 | 범위 |
|---|---|---|
| `server/schema_drift.py` | 모델 기대 스키마 ↔ DB 카탈로그 대조, 부팅마다 | 26개 테이블 전부. **이름만, 타입은 안 본다** |
| `known_tables=crud.TABLE_CONFIG` | config 선언의 컬럼 참조를 `table_config`와 대조, 로드 시점 거절 | 8개 표면 중 4개 |
| `server/scripts/install_product_tables.py` | 제품 소유 선언을 gitignore된 live config에 바이트 스플라이스로 설치 | `table_config.json`의 4개 엔트리만 |

## 헤드라인 정정 — 이 문서 자신의 프레이밍에 대한 것

이 라운드의 실측: 이 박스의 live config 10개 중 **8개가 추적되는 `.sample`과 바이트
동일**하고, `table_config`는 정규화하면 **차이 0줄**, leaf 570개 중 값이 다른 것은
**0개**다. 정의는 **이미 사실상 버전 관리되고 있다 — 우연히, 보장 없이.** 없는 것은
버전 관리가 아니라 **방향(어느 쪽이 상류인가)과 병합 규칙**이다.

## 권고와 스스로 세운 반증 조건

`server/schema_drift.py`를 보고서에서 **기대 상태를 계산하는 유일한 자리**로 승격하고,
타입 비교·마이그레이션 실행 원장·config 소비자 계약으로 넓히자는 것이 권고다. 세
조각은 이미 트리에 있다고 명시한다. 스스로 세운 반증 조건: **진짜 병목이 탐지가 아니라
운영자 박스에서의 적용이라면, 더 나은 탐지기는 아무것도 사지 못한다.**

## 이 라운드가 함께 낸 두 도구 — 둘 다 읽기 전용/수동

**`server/migrations/migrate_map_meta_to_wafer_id.py`**(655줄). `core_wafer_map`의 저장된
`wafer_map_metadata` 행이 `core_lot || '_' || core_slot`으로 여전히 저장돼 있는데
identity 선언은 전날(`68db020`이 아니라 그 전 `7097a67` 라운드)이미 `wafer_id`로 바뀐
상태를 겨냥한다. **RUN MANUALLY. NEVER ON BOOT.** dry-run이 기본값이고 `--apply`가
있어야 쓴다.

```python
"""Move stored `wafer_map_metadata` map ids from the old composite spelling to `wafer_id`.
...
The lookup in map_overlay._meta_select (target_table == t AND map_id == m) misses every
time. WHY IT IS SILENT, AND WHY THAT MAKES IT WORSE: since [D5] a missing meta row is a
NORMAL state (the map borrows geometry from a neighbour and is scored anyway)."""
```

이 스크립트가 명시하는 위험은 **조용함**이다 — 예전엔 메타 부재가 `binding_unresolved`를
냈지만 `[D5]` 이후로는 조용히 이웃에서 기하를 빌려 채점당한다.

**`server/scripts/diagnose_slow_after_ingest.py`**(1,306줄). 대량 적재 뒤 페이지 로드가
느려지는 신고를 진단하는 도구다. 이 라운드에서 만든 실측이 두 커밋 뒤(`3fe4438`)
PROJECT_STATUS 판정의 근거가 되고, 그 판정이 다시 그날 뒤에 오는 `dab9152`·`2630790`
수리로 이어진다.

## 검증

이 커밋은 문서 1개(647줄)와 스크립트 2개(655 + 1,306줄) 추가뿐이다 — 코드 변경도
config 변경도 없다는 것이 이 커밋 자신의 명시적 주장이고, `git show --stat`도 그것과
일치한다(세 파일 모두 신규 추가, 삭제 0). 스위트 실행은 이 커밋의 범위 밖이다.

## 그때 남아 있던 것

- `migrate_map_meta_to_wafer_id.py`는 이 시점까지 **한 번도 `--apply`로 실행되지
  않았다** — 저장된 `wafer_map_metadata` 행은 여전히 옛 철자다.
- 권고(스키마 드리프트를 단일 대조 표면으로 승격)는 **제안일 뿐 착수되지 않았다** — 이
  문서 자신이 「제품 스펙이 아니다」라고 못박는다.
- 이 문서가 실측한 「4개 동시 편집 중인 레인」 경고(수리 레인이 `server/config/*.json`을
  같은 시각 편집 중이었다는 각주)는 이 커밋의 config 실측이 스냅샷 시점에 국한됨을
  의미한다 — 이후 라운드(`68db020`)가 그 config를 다시 바꿨다.
