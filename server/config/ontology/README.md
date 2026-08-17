# Ledger v2 Ontology Config Root

> 상태: `STAGE_7_IN_REVIEW` / `MANIFEST_ACTIVE_FOR_LOT_EVENT`
> loader/compiler: `server/ledger/setup_bundle.py` → `server/ledger/cutover_v2.py`

이 디렉터리는 Ledger v2 authoring 정본의 단일 root다. `manifest.json`이 열거한 다섯 파일만
로드하며 현재 legacy Ledger 선언의 유일한 source인 `lot_event`를 v2 snapshot으로 컴파일한다.

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

운영 CLI `python -m ledger.backfill`은 이 root를 기본으로 사용한다. 실행 selector는
`dataflows/chains.json`의 `ledger_v2_execution`이며 v2 mode에는 Stage 6 parity 승인 근거가
필수다. 기존 cursor가 legacy 모양이면 Atom 0·cursor 미이동으로 reset 별도 승인을 요구한다.

`--legacy`는 데이터 reset과 legacy 은퇴가 별도 승인될 때까지 남긴 임시 compatibility
escape hatch다. 기존 `server/config/*.json`은 변경·이동·삭제하지 않았다. DB reset, cursor
reset, legacy 제거는 이 config를 로드하거나 dry-run하는 부작용으로 실행되지 않는다.

검증만 실행:

```text
conda run -n assy_manager python -m ledger.cutover_v2
```
