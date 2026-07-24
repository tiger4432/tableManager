---
name: DataIngester
description: 다양한 원천 데이터(Raw Data)를 파이프라인 파서/체인 맵퍼로 파싱하여 assyManager 서버에 안정 적재하는 전문가 스킬
---

# DataIngester Skill

이 스킬은 외부 데이터를 `assyManager`에 안정적으로 병합하기 위한 표준 절차를 정의합니다.

> ⚠️ **현행 아키텍처**: 적재는 **파이프라인 파서(`BasePipelineParser`) + Directory Watcher + `crud.apply_batch_updates`** 경로가 표준입니다. DB는 PostgreSQL/JSONB. 기준 문서: [INGESTION_GUIDE](file:///c:/Users/kk980/Developments/assyManager/docs/guide/INGESTION_GUIDE.md) · [chain_ingestion_guide](file:///c:/Users/kk980/Developments/assyManager/docs/guide/chain_ingestion_guide.md) · [AUTO_UPDATE_GUIDE](file:///c:/Users/kk980/Developments/assyManager/docs/guide/AUTO_UPDATE_GUIDE.md) · [data_model.md](file:///c:/Users/kk980/Developments/assyManager/docs/architecture/data_model.md). 상위 규율: [StableDevelopmentProtocol](file:///c:/Users/kk980/Developments/assyManager/.agents/skills/StableDevelopmentProtocol/SKILL.md).

## 1. 데이터 업데이트 원칙 (Multi-Source Priority)
- **절대 원칙**: 모든 원천 데이터를 `CellSource`에 보존하되, 표출 우선순위는 `SOURCE_PRIORITY = {user:0, collision_merge:1, pipeline_parser:2, custom_script:3}`(낮을수록 우선)로 결정됩니다. 즉 **사용자 수동값이 파서값보다 우선**합니다.
- **Push 전략**: 파서는 자신의 `source_name`과 함께 항상 값을 밀어넣습니다. 사용자가 이미 수정한 셀이라도 파서 최신값은 `CellSource`에 별도 보관되어 유실되지 않습니다.

## 2. 적재 경로 (3택)
| 경로 | 언제 | 구현 |
|---|---|---|
| **파이프라인 파서** | 파일 드롭 기반 자동 적재 | `ingestion_workspace/{table}/scripts/*.py`에 `BasePipelineParser` 상속 클래스 작성(`match()`, `process_dataframe()`). Watcher가 자동 매칭·실행·아카이빙 |
| **체인 맵퍼** | 한 테이블 변화로 다른 테이블 파생 계산 | `server/mappers/*.py` + `config/chain_rules.json` 등록. DB 세션(`db`)으로 조인 조회 가능(단, `db.commit()` 금지 — 상위 워커가 트랜잭션 관리) |
| **수집 스케줄러** | 주기적 외부 수집 | `ingestion_workspace/{table}/auto_update/*.py`에 `# schedule:` 크론 주석 + `out` 변수 |

## 3. 배치 업서트 API 규격 (수동/외부 Push 시)
- **Endpoint**: `PUT /tables/{table_name}/data/updates` (통합 배치 업서트. 개별 셀 엔드포인트를 반복 호출하지 말 것)
- **Payload (GeneralUpdateBatch)**:
  ```json
  {
    "updates": [
      {
        "row_id": "UUID (또는 생략)",
        "business_key_val": "PART-999 (row_id 미상 시 비즈니스 키로 매칭 업서트)",
        "updates": { "col_name": "new_value", "qty": 120 },
        "source_name": "parser_a",
        "updated_by": "ingester_agent"
      }
    ]
  }
  ```
  > `row_id`와 `business_key_val` 중 최소 하나는 명시. 체인 적재 시 `source_name`은 반드시 `"chain_ingestion"`(순환 루프 차단 키).

## 4. 파싱 시 주의사항
- **Row Matching**: 원천 PK로 기존 `row_id`를 매핑. 매핑 안 되는 신규 행은 업서트 시 `business_key_val`로 자동 생성/매칭되게 합니다(또는 `POST /tables/{t}/rows`).
- **Type Casting**: `table_config.json`의 `column_types`(string/number/datetime)에 맞춰 변환 전송. `NaN`/`NaT`는 파이프라인 베이스(`clean_for_postgres`)가 `null`로 정화합니다.
- **[확장성] 대량 적재**: 1,000행 청크로 전송(`_send_to_upsert`). 맵퍼에서 매 행 `db.query()` 금지 — 룩업 대상을 초기화 시 메모리 캐시(N+1 제거). → [Scale-First](file:///c:/Users/kk980/Developments/assyManager/.agents/skills/StableDevelopmentProtocol/SKILL.md)
- **실패 격리**: 매칭 파서가 없거나 실패한 파일은 `err/`로 격리되고 `FileIngestionLog`에 기록됩니다.

## 📝 워크플로우 연동
- 작업 할당: `agent_workspace/tasks/Agent_Ingester_task.md` 우선 확인.
- 완료 후 `agent_workspace/reports/`에 핵심 코드 스니펫 포함하여 리포트.

---
*본 지침을 준수하여 데이터 무결성과 시스템 확장성을 보장하십시오.*
