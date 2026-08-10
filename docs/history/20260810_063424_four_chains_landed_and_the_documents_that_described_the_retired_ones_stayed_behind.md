# 체인 넷이 착지했고, 은퇴한 규칙을 설명하던 문서들이 그 자리에 남았다

**날짜:** 2026-08-10 06:34 · **커밋:** `2ec8e24` · **레인:** 서버(체인·정렬기)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

> **이 커밋도 본문이 제목 한 줄뿐이다.** 서사는 커밋이 스스로 추가한 `docs/history/`
> 다섯 파일에만 있고 그 파일들은 해시를 달고 있지 않다. 앞 커밋의 같은 문제는
> `20260809_190335`에 적어 뒀다.

---

## 무엇이 들어왔나

체인 규칙 **넷**이 새로 생겼다. 전부 `enabled: true`다.

| 체인 id | 트리거 | 소스 | 타깃 |
|---|---|---|---|
| `dt_inventory_to_standard_dt_map` | dt_inventory | dt_log | dt_map |
| `dt_log_to_primary_core_frame` | dt_log | dt_log | dt_inventory |
| `dt_inventory_to_core_usage_map` | dt_inventory | dt_log | core_usage_map |
| `dt_log_to_core_usage_map` | dt_log | dt_log | core_usage_map |

새 모듈 `server/dt_frame_transform.py`(96줄)가 `dt_equations`·`core_equations`·
`apply_dt_equations`·`standard_meta`를 들고 있다 — **확정된 프레임을 이식 가능한 좌표
방정식으로 압축**하는 자리다.

## 무엇이 은퇴했나 — 삭제 717줄의 정체

| 분류 | 삭제 줄 |
|---|---:|
| 설정 스냅샷 재생성 | **550** |
| 클라 빌드 산출물 | 115 |
| 서버 파이썬 | 37 |
| 문서 산문 | 14 |
| 테스트 | 1 |

**대부분은 코드가 아니라 스냅샷 재생성이다.** 운영자의 라이브 설정에서 `*.json.sample`과
`docs/guide/config_reference/*.json`을 다시 만들면서 배열이 한 줄로 접히고 낡은 주석이
빠졌다. 이 커밋 시점에 다섯 쌍 전부 **바이트 동일**이다.

**실제 은퇴 항목:**

- **`dt_job_attribution_to_dt_map`과 `eqp_frame_attribution_to_dt_map`** — 둘 다
  `enabled: false`인 채로 「REVISIT RULE 1 of 2」·「2 of 2, **AND THE DANGEROUS ONE**」라는
  이름표를 달고 있었다. **재유도 팬아웃 대신 잡별 확정 방정식을 키로 쓰는**
  `dt_inventory_to_standard_dt_map` 하나로 대체됐다.
- **보강 규칙 `eqp_product_frame_attribution`** — 손으로 쓴 SQL `reference_views` 넷을
  포함해 통째로 삭제. `dt_frame_confrimation` + `core_frame_review`가 대신하고 둘 다
  **`dt_inventory`를 타깃**으로 한다.
- **설정 키 `derivation_source_table`** → `source_table`.
- **`dt_map`의 출처 컬럼** `core_wafer`·`core_lot`·`core_slot`·`core_x`·`core_y` 제거,
  `dt_index` 추가.

## 🔴 지워진 것을 설명하던 문장들이 남았다

이 커밋의 재사용 가능한 부분은 여기다. **은퇴는 코드에서 일어났고 산문은 따라가지 않았다.**

- `dt_map`의 `__comment`가 **정반대를 계속 주장한다** — 「각 셀이 자기 출처
  (core_wafer/core_lot/core_slot/core_x/core_y)를 나른다 … 그 출처가 **그릴 수 있는 맵과
  추적할 수 있는 맵의 차이**다」. **그 컬럼들을 이 커밋이 지웠다.** 문장은 이제 거짓이다.
- `docs/guide/chain_ingestion_guide.md`가 **은퇴한 두 규칙을 여전히 살아 있는 것으로
  표에 싣는다.** 같은 파일이 `server/migrations/add_dt_log_trigger_indexes.sql`을 두고
  **「아직 실행되지 않았습니다」**라고 적는데, **그 인덱스를 필요로 하던 두 규칙이 사라졌다.**
- `server/mappers/dt_map_mapper.py.sample`도 두 은퇴 규칙을 계속 문서화한다.
- `server/dt_map_derivation.py`(`SCOPE_ROW_CAP = 50000`·`frame_trigger_scope`·
  `expand_trigger`)는 그 경로에 대해 **죽은 무게**가 됐다.
- 🔴 **아키텍처 문서가 자기가 설명하는 config와 어긋난다.** `DT_CORE_FRAME_CHAINS.md`는
  체인을 `dt_log_to_alignment_metadata`·`wafer_map_metadata_to_dt_inventory`라 부르는데
  config의 이름은 `dt_log_to_dt_alignment_metadata`·`dt_metadata_to_dt_inventory`다.
  방정식 절의 컬럼명도 `b_wx`/`b_wy`·`c_wx`/`c_wy`인데 실제 컬럼은 `dt_x`/`dt_y`·
  `core_x`/`core_y`다. **인시던트 중에 문서의 낱말로 grep하면 아무것도 안 나오는 형태다.**
- `frame_confirmation` 이력은 아키텍처 문서가 **은퇴를 선언**했지만
  (「retired … must not be reintroduced」), 모듈과 마이그레이션은 그대로 있고
  `dt_inventory_metadata_mapper.py.sample`이 **여전히 `frame_confirmation._basis_cells_for`를
  import한다.**

## 문턱이 선언됐다 — 그리고 그 근거가 합성이다

`map_overlay_config`의 `__alignment_index_comment`는 순번 문턱을 **「일부러 비워 두고
배포한다」**(축이 보고는 하되 순위는 매기지 않게)고 적고 있었다. 이 커밋이 그것을
**실제 선언으로 교체**했다.

```json
"alignment": { "min_margin_dies": 20, "min_discriminating_dies": 20,
  "index": { "min_margin_dies": 20, "min_discriminating_dies": 20 } }
```

🔴 **그런데 그 `__derivation` 주석이 스스로 밝힌다** — 「이 박스의 **합성** 데이터에서
유도했다 … **운영 측정이 아니다.**」 문턱이 비어 있다가 채워졌다는 것과 그 값이 운영에서
검증됐다는 것은 다른 문장이다.

## 기준 카탈로그 상한 50 → 500

```python
MAX_REFERENCE_CANDIDATES = 500   # 종전 50
```

**config가 아니라 파이썬 상수다.** 근거로 제시된 수는 「라이브 환경에 core-map 메타데이터
**201행**이 있고, 종전 전역 상한은 유효 다이 기준 여덟 개 뒤 **42개**만 허용했다」이다.
50 − 8 = 42는 산술적으로 맞지만 **201은 환경 측정치이고 diff로 확인되지 않는다.**

## 🔴 새 체인 셋 다 정적 호출자가 0이다

| 진입점 | 파이썬 호출자 | 테스트 호출자 | config 참조 |
|---|---:|---:|---:|
| `build_standard_dt_map_batches` | **0** | 1 | 1 |
| `build_core_frame_confirmation_batch` | **0** | **0** | 1 |
| `build_core_usage_map_batches` | **0** | **0** | 2 |

셋 다 `chain_ingestion_worker.execute_custom_mapper`의 `importlib.import_module` +
`getattr`로만 불린다. **정적 호출 그래프가 비는 것은 설계이고, 유일한 배선은 JSON 규칙이다.**
그런데 **그 JSON은 `.sample`이고 라이브 `chain_rules.json`과 매퍼 `.py`는 gitignore된다.**

즉 **저장소를 이력으로 읽는 사람에게 이 체인들은 착지·선언됐지만 정적으로 도달 불가능하다.**
(개발자의 작업 트리에는 추적되지 않는 실물이 존재하고, `test_live_mapper_and_tracked_sample_are_byte_identical`
테스트가 그 둘을 묶으려고 있다.)

**공개 진입점 둘은 추적되는 저장소 어디에서도 실행되지 않는다** —
`build_core_frame_confirmation_batch`의 모든 갈래(정렬 서비스 호출, `_placement` 가드,
`confirmed_meta_for`, `core_equations` try/except)가 미검증이다.

## 검증

- 새 테스트 파일 **6개**. `test_core_alignment_mapper`(5) · `test_core_usage_mapper`(3) ·
  `test_dt_frame_transform`(2) · `test_dt_standard_map_mapper`(1) ·
  `test_probe_core_occupancy_alignment`(2) · `test_syn_core_defect_jobs`(1).
- 동반 문서가 적은 실행: **27 passed**(5 + 22), **10 passed**(3 + 2 + 5). **둘 다 파일별
  테스트 수와 맞는다.**
- 🔴 **한 문서가 자기 안에서 어긋난다** — 같은 파일이 잡 슬라이스를 앞에서 「87다이 셋」,
  뒤에서 「61다이 셋」이라고 적는다. 61 쪽이 코드와 맞는다(183/3 = 61, `CORE_YIELD = 0.70`).
- `TODO`·`FIXME`·`pytest.mark.skip`·`skipif`는 **한 줄도 추가되지 않았다.**

## 그때 남아 있던 것

- **마이그레이션 파일이 없다.** `core_usage_map`·`dt_core_view`·`dt_inventory` 셋 다
  `table_config.json.sample`의 동적 테이블 선언으로만 존재한다.
- `dt_inventory`의 `__comment`가 **교정되지 않은 소문자 산문에 오타를 품은 채**다
  (`"…dt and core coordinatite, and including base conversion equation columns."`).
- `server/scripts/probe_core_occupancy_alignment.py`는 **스스로 배선되지 않았다고 선언한다**
  (「deliberately not a chain mapper and writes no frame」). 호출자는 자기 테스트뿐이다.
  🔴 그런데 자기 문턱 `DEFAULT_MIN_HIT_RATIO = 0.85`·`DEFAULT_MIN_MARGIN_DIES = 5`를
  들고 있다 — **어느 config에도 없는 네 번째 문턱 철자**다.
- `dt_log_to_dt_map`은 여전히 `"enabled": false`이고, 두 보강 규칙은 둘 다
  `"auto_confirm": false`다. **자동 확정은 아직 아무 데서도 켜지지 않았다.**
- `dt_log_to_dt_map`의 `__comment`에서 **「THE PURGE QUESTION IS ANSWERED, AND NOT BY
  replace_map…」으로 시작하는 문단이 통째로 삭제됐다.** 규칙은 비활성인 채로 남았으므로,
  그 판단의 근거는 이 커밋 이후 코드 안에 없다.
