# Ledger v2 Ontology Config Root

> 상태: `SCHEMA_READY` / `NOT_RUNTIME_ACTIVE`
> loader: `server/ledger/setup_bundle.py`

이 디렉터리는 Ledger v2 authoring 정본이 놓일 단일 root다. 2단계에서는 schema와 strict
manifest loader만 구현했으며, 비어 있는 설정을 동작 중인 설정처럼 보이게 하지 않기 위해
아직 `manifest.json`과 하위 JSON을 만들지 않는다.

활성화 시 정확한 구조:

```text
server/config/ontology/
├─ manifest.json
├─ ledger_config.json
├─ catalog/
│  ├─ tables.json
│  └─ virtual_joins.json
└─ dataflows/
   ├─ chains.json
   └─ enrichments.json
```

- `manifest.json`: 읽을 파일을 정확히 열거한다.
- `ledger_config.json`: Vocabulary/Entity/Preparer/Mapper/Pack/Profile/Source를 함께 작성한다.
- `catalog/tables.json`: 물리 relation/column/key/index 사실만 둔다.
- `catalog/virtual_joins.json`: 물리 join 계약만 둔다.
- `dataflows/*.json`: chain과 enrichment 실행 연결을 둔다.

stage 3의 Registry/snapshot 승인 전에는 이 root를 runtime에서 읽지 않는다. 기존
`server/config/*.json`은 전환 기간 그대로 유지한다.
