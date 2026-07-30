# `ingestion_settings.json` 세팅 — 인제션 런타임 노브

> **Status:** 🟢 Living | **Last-verified:** 2026-07-30 (**키 2개 추가** — `enrichment_auto_confirm_enabled`/`enrichment_auto_confirm_max_keys`, ① 자동 확정) | **이전:** 2026-07-29 (**키 2개 누락 보충** — `auto_register_map_meta`(M3 `ab6ac02`)와 `flatten_nested_dirs`(`0c6ac1a`, 직전 사이클 누락분)가 sample·코드에는 있는데 이 표에 없었습니다) | **Owner:** Ingester
> 상위: [폴더 인덱스](./README.md) · 파이프라인 정본은 [INGESTION_GUIDE §1.8](../INGESTION_GUIDE.md) · 절차 요약은 [CONFIG_GUIDE §3-S5](../CONFIG_GUIDE.md)

<!-- Loader evidence (2026-07-28):
  load: server/parsers/directory_watcher.py:147 load_ingestion_settings (missing/corrupt -> {} = defaults)
  heavy_file_mb: directory_watcher.py:173 get_heavy_threshold_bytes (read per file event; bool/non-positive -> warn once + default 10)
  dedup_by_signature: directory_watcher.py:206 (default True) / resume_from_checkpoint: :214 (default True)
    both via _bool_setting :191 (non-boolean -> warn once + default)
  flatten_nested_dirs: directory_watcher.flatten_nested_dirs_enabled (via _bool_setting; read per folder trigger)
  auto_register_map_meta: map_meta_registrar.auto_register_enabled (own loader, same non-boolean warn-once posture; read per work unit)
  enrichment_auto_confirm_enabled / _max_keys: enrichment_candidates.global_auto_confirm_enabled / max_keys_per_unit (own loader, same warn-once posture; read per chain tx group)
  heavy routing proof log: directory_watcher.py:674 "🐘 Routed to heavy lane queue (...)"
-->

## 1. 언제 이 파일을 만지는가

- **대형 파일이 소형 파일 처리를 막을 때** — heavy 레인 임계(`heavy_file_mb`) 조정
- **같은 파일을 강제로 전량 재처리해야 할 때** — `dedup_by_signature`를 잠시 `false`로 (개별 파일 1건이면 파일명에 `__force__`를 넣는 편이 낫습니다: `report__force__.csv`)
- 중단 재개를 끄고 항상 처음부터 적재하게 할 때 — `resume_from_checkpoint`
- **폴더째 드롭한 것을 그대로 두고 싶을 때** — `flatten_nested_dirs`를 `false`로
- **인제션이 맵 정렬 메타를 자동으로 만드는 것을 멈추고 싶을 때** — `auto_register_map_meta`를 `false`로(§5의 주의 참조)
- **enrichment 자동 확정을 전부 멈추거나, 작업 단위당 탐색량을 조절할 때** — `enrichment_auto_confirm_enabled` / `enrichment_auto_confirm_max_keys`(정본 [config/enrichment_rules §7](./enrichment_rules.md))
- **파일이 없어도 정상입니다** — 전 항목 기본값으로 동작합니다(현 저장소 상태가 그렇습니다).

## 2. 세팅 절차

1. **스냅샷**(파일이 이미 있을 때만 의미 있음): `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. 파일이 없으면 `ingestion_settings.json.sample`을 `ingestion_settings.json`으로 복사합니다.
3. 값을 수정합니다:

   ```json
   {
     "heavy_file_mb": 10,
     "dedup_by_signature": true,
     "resume_from_checkpoint": true,
     "flatten_nested_dirs": true,
     "auto_register_map_meta": true
   }
   ```

   `heavy_file_mb`는 **양수 숫자만**(bool·문자열·0 이하는 경고 1회 후 기본 10), **나머지 boolean 4개는 JSON boolean만**(문자열 `"false"`는 경고 1회 후 기본값 — 오타가 스위치를 조용히 뒤집지 않습니다).
4. 저장 — 반영은 자동입니다: **다음 작업 단위부터** 디스크에서 다시 읽습니다(재기동·reload 불필요). 단위는 키마다 다르지만 규율은 같습니다 — **한 작업 단위 안에서는 값이 갈리지 않습니다**: `heavy_file_mb`·`dedup_by_signature`·`resume_from_checkpoint`는 **다음 파일 이벤트**, `flatten_nested_dirs`는 **다음 폴더 트리거**, `auto_register_map_meta`는 **다음 파일 / 다음 체인 트랜잭션 그룹**, `enrichment_auto_confirm_*`은 **다음 체인 트랜잭션 그룹**.

## 3. 반영 확인

- **heavy 임계**: 임계 이상 파일을 `raws/`에 떨어뜨리고 **워처 프로세스 로그**에서 라우팅 줄을 확인합니다:
  ```
  [<table>] 🐘 Routed to heavy lane queue (<사유>, <크기>B): <파일명>
  ```
- **dedup**: 같은 파일을 다시 떨어뜨렸을 때 — `true`면 `GET /admin/file-ingestion/logs`에 `SKIPPED`(사유 포함)가 남고, `false`면 재적재됩니다. 스킵은 무음이 아닙니다.
- **잘못된 값**: 워처 로그에 `Ignoring invalid 'heavy_file_mb' ...` / `Ignoring non-boolean ...` 경고(값당 1회)가 뜨면 설정이 무시되고 기본값으로 돌고 있다는 뜻입니다.

## 4. 잘못됐을 때

파일을 지우면 **전 항목 기본값**(10 MB / dedup on / resume on / flatten on / 맵 메타 자동 등록 on)으로 즉시 돌아갑니다 — 이 파일에 한해서는 삭제가 가장 빠른 복구입니다. 스냅샷 복원:

```bash
conda run -n assy_manager python server/scripts/backup_config.py restore ingestion_settings_<yymmdd>.json.bak --yes
```

→ [ROLLBACK_PROCEDURE](../ROLLBACK_PROCEDURE.md)

## 5. 키 참조

| 키 | 타입 / 기본값 | 의미 |
|---|---|---|
| `heavy_file_mb` | 양수, 기본 `10` | 이 크기(MB) 이상 파일은 전용 heavy 워커로 격리 라우팅. 단, **같은 워크스페이스에 heavy 백로그가 있으면 소형 파일도 순서 보존을 위해 큐 뒤로** 갑니다 |
| `dedup_by_signature` | boolean, 기본 `true` | 동일 내용(sha256) 파일 재처리 skip. `false` = 전역 강제 재처리 스위치 |
| `resume_from_checkpoint` | boolean, 기본 `true` | 중단된 적재를 커밋된 오프셋부터 재개. 재개 불가 시 사유를 남기고 처음부터 |
| `flatten_nested_dirs` | boolean, 기본 `true` | `raws/`에 폴더(다중 층위)가 들어오면 트리가 정온해진 뒤 **파일만 루트로 승격**하고 빈 폴더를 제거. 충돌은 덮어쓰지 않고 상대경로 `~` 접두로 개명. `false` = 종전 동작(폴더 무시). 반영은 **다음 폴더 트리거부터**. 정본 [INGESTION_GUIDE §1.9](../INGESTION_GUIDE.md) |
| `auto_register_map_meta` | boolean, 기본 `true` | 인제션(**파일 워처·체인 워커 양쪽**)이 `map_key_columns` 선언 맵 테이블에 적재할 때, 그 맵 키의 `wafer_map_metadata` 행이 **없으면** 자동 생성(있으면 절대 건드리지 않음). `false` = 종전 동작(수동 에디터 push만 메타를 등록 → 미등록 맵이 '화면기준' 폴백으로 열림). 반영은 **다음 파일 / 다음 체인 트랜잭션 그룹부터**. 정본 [INGESTION_GUIDE §1.10](../INGESTION_GUIDE.md) |
| `enrichment_auto_confirm_enabled` | boolean, 기본 `true` | **전역 킬 스위치**(2026-07-30 ①). `false`면 규칙별 `auto_confirm`이 켜져 있어도 자동 확정을 전부 멈춥니다. 기본 `true`는 "막지 않는다"는 뜻일 뿐이고 **실제로 쓰려면 규칙별 옵트인이 필요**합니다(기본 OFF) — 즉 기본 상태의 동작은 종전과 같습니다. 정본 [config/enrichment_rules §7](./enrichment_rules.md) |
| `enrichment_auto_confirm_max_keys` | 양의 정수, 기본 `200` | 작업 단위(체인 트랜잭션 그룹)당 참조뷰로 **탐색할 판단키 상한**. 키 1개당 선언된 뷰 수만큼 SQL이 나가므로 대량 인제션에서 쿼리 폭주를 막는 유일한 장치입니다. 상한을 넘은 키는 **쓰지 않고 워크리스트에 그대로 남으며** 건수가 로그에 남습니다(정직한 열화 — 조용히 버리지 않음) |

(`_`로 시작하는 `_*_doc` 키는 sample의 주석용 — 코드가 읽지 않습니다.)

> **끄기 전에 알아 둘 것 (`auto_register_map_meta`)**: 이 노브를 끄면 새로 적재되는 맵은 정렬 규격 없이 쌓이고, 에디터에서 열 때마다 **좌표계 선택 모달**이 뜹니다(그것이 켜짐/꺼짐을 확인하는 가장 빠른 관찰 지점이기도 합니다). 자동 생성된 메타는 **정직한 최소치**(배치 bbox·회전 0·마스크 중립 기하)이지 계측값이 아니므로, 실제 웨이퍼 규격이 필요한 맵은 에디터에서 사람이 등록하십시오 — 사용자 등록이 항상 이깁니다(생성 소스 `auto_map_meta` = 최하위 우선순위).
