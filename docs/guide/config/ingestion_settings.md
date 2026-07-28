# `ingestion_settings.json` 세팅 — 인제션 런타임 노브

> **Status:** 🟢 Living | **Last-verified:** 2026-07-28 | **Owner:** Ingester
> 상위: [폴더 인덱스](./README.md) · 파이프라인 정본은 [INGESTION_GUIDE §1.8](../INGESTION_GUIDE.md) · 절차 요약은 [CONFIG_GUIDE §3-S5](../CONFIG_GUIDE.md)

<!-- Loader evidence (2026-07-28):
  load: server/parsers/directory_watcher.py:147 load_ingestion_settings (missing/corrupt -> {} = defaults)
  heavy_file_mb: directory_watcher.py:173 get_heavy_threshold_bytes (read per file event; bool/non-positive -> warn once + default 10)
  dedup_by_signature: directory_watcher.py:206 (default True) / resume_from_checkpoint: :214 (default True)
    both via _bool_setting :191 (non-boolean -> warn once + default)
  heavy routing proof log: directory_watcher.py:674 "🐘 Routed to heavy lane queue (...)"
-->

## 1. 언제 이 파일을 만지는가

- **대형 파일이 소형 파일 처리를 막을 때** — heavy 레인 임계(`heavy_file_mb`) 조정
- **같은 파일을 강제로 전량 재처리해야 할 때** — `dedup_by_signature`를 잠시 `false`로 (개별 파일 1건이면 파일명에 `__force__`를 넣는 편이 낫습니다: `report__force__.csv`)
- 중단 재개를 끄고 항상 처음부터 적재하게 할 때 — `resume_from_checkpoint`
- **파일이 없어도 정상입니다** — 전 항목 기본값으로 동작합니다(현 저장소 상태가 그렇습니다).

## 2. 세팅 절차

1. **스냅샷**(파일이 이미 있을 때만 의미 있음): `conda run -n assy_manager python server/scripts/backup_config.py snapshot`
2. 파일이 없으면 `ingestion_settings.json.sample`을 `ingestion_settings.json`으로 복사합니다.
3. 값을 수정합니다:

   ```json
   {
     "heavy_file_mb": 10,
     "dedup_by_signature": true,
     "resume_from_checkpoint": true
   }
   ```

   `heavy_file_mb`는 **양수 숫자만**(bool·문자열·0 이하는 경고 1회 후 기본 10), boolean 두 개는 **JSON boolean만**(문자열 `"false"`는 경고 후 기본값).
4. 저장 — 반영은 자동입니다: **다음 파일 이벤트부터** 디스크에서 다시 읽습니다(파일 경계 스냅샷 — 한 파일의 처리 도중 값이 갈리지 않음). 재기동·reload 불필요.

## 3. 반영 확인

- **heavy 임계**: 임계 이상 파일을 `raws/`에 떨어뜨리고 **워처 프로세스 로그**에서 라우팅 줄을 확인합니다:
  ```
  [<table>] 🐘 Routed to heavy lane queue (<사유>, <크기>B): <파일명>
  ```
- **dedup**: 같은 파일을 다시 떨어뜨렸을 때 — `true`면 `GET /admin/file-ingestion/logs`에 `SKIPPED`(사유 포함)가 남고, `false`면 재적재됩니다. 스킵은 무음이 아닙니다.
- **잘못된 값**: 워처 로그에 `Ignoring invalid 'heavy_file_mb' ...` / `Ignoring non-boolean ...` 경고(값당 1회)가 뜨면 설정이 무시되고 기본값으로 돌고 있다는 뜻입니다.

## 4. 잘못됐을 때

파일을 지우면 **전 항목 기본값**(10 MB / dedup on / resume on)으로 즉시 돌아갑니다 — 이 파일에 한해서는 삭제가 가장 빠른 복구입니다. 스냅샷 복원:

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

(`_`로 시작하는 `_*_doc` 키는 sample의 주석용 — 코드가 읽지 않습니다.)
