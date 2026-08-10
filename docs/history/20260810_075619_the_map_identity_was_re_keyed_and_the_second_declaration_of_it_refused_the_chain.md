# 맵 정체성을 웨이퍼 하나로 다시 키잡았고, 같은 선언의 두 번째 사본이 체인을 거절했다

**날짜:** 2026-08-10 07:56 · **커밋:** `7097a67` (이 시점의 HEAD) · **레인:** 서버(체인·감사)
**측정 상자:** 이 워크스테이션. **운영이 아니다.**

> **이 커밋도 본문이 제목 한 줄뿐이다.** 세 커밋 연속이다(`a501d6d` · `2ec8e24` · 이 커밋).
> 감사 캐시 절반은 `20260810_073000`에 구현 레인이 적어 둔 것이 있으나 **해시가 없다** —
> 이 항목이 그 연결을 만든다.

---

## 새 체인은 없다 — 앞 커밋이 착지시킨 것을 마감했다

- **`dt_log_to_primary_core_frame`** — 기준 정체성을 lot/slot에서 **웨이퍼 id**로 다시
  키잡고, 방정식 유도의 기준을 고쳤다.
- **`dt_inventory_to_core_usage_map`·`dt_log_to_core_usage_map`** — 둘 다
  `allow_map_metadata_upsert: true`를 받아 `core_usage_map`이 **자기 `wafer_map_metadata`
  기록을 스스로 등록**하게 됐다.

## 정체성 재키잡기

```json
"reference": { "table": "core_wafer_map",
  "map_id_template": "{core_wafer}",   // 종전 "{core_lot}_{core_slot}"
  "fields": ["core_wafer"] }           // 종전 ["core_lot","core_slot"]
```

같은 변경이 **두 곳 더** 있다 — `map_overlay_config`의 `core_wafer_map.columns.key_columns`,
`table_config`의 `core_wafer_map.map_key_columns`. 둘 다 `["core_lot","core_slot"]` →
`["wafer_id"]`.

## 🔴 세 번째 사본이 남아서 체인을 거절했다

이 커밋의 재사용 가능한 부분은 여기다. **한 정체성이 세 곳에 선언돼 있었고, 재키잡기가
그중 일부만 따라갔다.**

`docs/process/PROJECT_STATUS.md`가 이 커밋에서 그 사고를 기록한다 — `core_wafer_map`의
정체성을 `core_lot/core_slot`에서 `wafer_id`로 바꾼 뒤 **오버레이 바인딩이 남아 자동
Core-frame 체인이 `binding_unresolved`로 거절됐다.**

**중복 선언을 하나로 모으자는 제안**(`map_contracts` 단일 출처, `map_id_template`과 중복
`key_columns` 제거)이 같은 자리에 적혔고, 그 항목의 상태 줄은 **「제안 단계. 아직 제품
spec이 아니며, 승인 전에는 현 설정을 동작 정본으로 유지한다」**이다.

🔴 **그래서 이 커밋이 실제로 한 일은 중복 선언 두 개를 손으로 맞춘 것이다** — 제안이
없애려는 바로 그 중복을 통해 고쳤다. **제안은 파일로 남았고 구조는 그대로다.**

## 🔴 앞 커밋이 세운 불변식이 이 커밋에서 깨졌다

`2ec8e24`가 `server/config/*.json.sample`과 `docs/guide/config_reference/*.json`을 **바이트
동일**로 맞춰 놨다. 이 커밋은 `table_config.json.sample`과 `map_overlay_config.json.sample`을
고치면서 **그 짝을 고치지 않았다.** 동기화가 유지된 것은 `chain_rules` 쌍뿐이다.

```
server/config/table_config.json.sample:55            "map_key_columns": ["wafer_id"]
docs/guide/config_reference/table_config.json:55     "map_key_columns": ["core_lot", "core_slot"]
```

`map_overlay_config`에도 같은 형태의 한 줄 어긋남이 있다. **이 불변식을 강제하는 테스트는
없다** — `DOC_OWNERSHIP.md`의 관례일 뿐이다. 한 커밋 앞에서 세워진 규율이 **다음 커밋에서
아무 소리 없이** 깨졌다.

## 감사 캐시 — 워커가 커밋한 것이 API 프로세스에 보이지 않았다

`chain_replay`는 **체인 워커 프로세스**에서 `AuditLog` 행을 남기는데, 최근 이력 엔드포인트는
**API 프로세스에 국소적이고 한 번만 적재되는 캐시**를 돌려주고 있었다. 그래서 재생이 DB에
있고 트랜잭션 상세로는 보이는데 **최근 목록에는 없는** 상태가 가능했다.

수리는 `MAX(audit_logs.id)` 워터마크 위의 **주키 구간만 병합**한다. 회귀 테스트가 그것을
**전부 재구축하지 않는다**는 쪽으로 고정한다 — 음성 대조를 몽키패치로 심는 방식이다.

```python
    # A replay refresh must be a delta merge, never a second full history scan.
    cache.load_initial = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("refresh must not rebuild historic audit groups"))
    assert cache.refresh_if_stale(db_session) is True
    assert cache.groups[0]["transaction_id"] == "chain_replay_after"
    assert cache.groups[0]["total_count"] == 1
    assert cache.refresh_if_stale(db_session) is False
```

네 가지를 한꺼번에 건다 — 갱신이 **한 번** 발화하고, 워커의 트랜잭션이 **머리**에 오고,
병합된 로그가 **정확히 하나**이며, 두 번째 호출은 **`False`**(워터마크가 그대로면 구간
질의 없음). 🔴 **「초록」이 전체 재구축으로도 나올 수 있는 자리라 그 경로를 예외로 막았다.**

## 시드 스크립트

`--core-lot`·`--core-slot`·`--core-wafer`·`--event-time`·`--csv-dir`·`--physical-core-only`
여섯 플래그가 붙어, 두 번째 합성 웨이퍼가 **낡은 잡 정리에서 `SYN-CORE-CLUSTER`를 덮어쓰지
않고 더해지도록** 바뀌었다. 물리 코어 시드의 replace 범위도 `{"wafer_id": CORE_WAFER}`로
같이 옮겼고, 주석이 그 이유를 적는다 — **메타데이터가 같은 정체성을 쓰지 않으면 코어 정렬
규칙이 그것을 해석할 수 없다.**

## 검증

- 새 테스트 파일 1개 `test_audit_cache_cross_process.py`
  (`test_recent_projection_refreshes_after_an_external_worker_commit`),
  `test_core_alignment_mapper.py` +2, `test_core_usage_mapper.py` +2.
- 동반 문서(`20260810_073000`)가 적은 「`test_audit_cache_cross_process.py`와 `test_api.py`
  통과」는 **실행 주장이고 diff로 확인되지 않는다.** 반면 같은 문서의 「역사 그룹을 다시
  훑지 않는다 · 워터마크가 그대로면 구간 질의가 없다」는 **둘 다 코드와 테스트가 지지한다.**
- `test_core_alignment_mapper.py`의 새 독스트링이 관측을 인용한다(`SYN-CORE-WAFER-01/P3`
  에서 관측). **그 관측의 산출물은 diff에 없다.**
- `TODO`·`FIXME`·`pytest.mark.skip`은 추가되지 않았고, 새 플래그는 **전부 기본 on**이다.

## 그때 남아 있던 것 (= 이 시점의 HEAD 상태)

- 🔴 **`build_core_frame_confirmation_batch`와 `build_core_usage_map_batches`는 여전히
  정적 호출자 0, 직접 테스트 0이다.** 이 커밋이 더한 테스트 넷은 `_equation_basis`·
  `_usage_batches`·`_usage_metadata_updates`·`_standard_frame`만 만진다. 공개 진입점
  경로에서 쓰이는 `_canonical_wafer`/`notation_norm.fold_notation_sql`도 그 미검증 경로에
  있다.
- **설정 스냅샷 두 쌍이 어긋난 채**다(위 참조). 강제하는 테스트는 없다.
- **맵 정체성 선언은 여전히 여러 곳에 흩어져 있다.** 이 커밋은 사본을 줄이지 않고 맞췄다.
- `20260810_030000`·`20260810_073000` 등 08-09~08-10의 구현 레인 항목들은 **커밋 해시와
  스위트 수치를 달고 있지 않다.** 이 항목과 `20260809_190335`·`20260810_063424`가 그
  세 커밋에 대해 연결을 대신한다.
