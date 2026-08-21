# Ledger v2 Legacy Config 변환 보고

> 생성: 2026-08-18 · 방식: read-only 대조 · legacy 파일 변경 0

## 실제 입력

| legacy 입력 | 실측 | v2 반영 |
|---|---|---|
| `server/config/ledger_config.json` | source `lot_event` 1개 | `ledger_config.json`의 7 section에 전환 |
| `server/config/table_config.json` | physical table 16개 | live Ledger relation `lot_event` 1개만 catalog에 반영 |
| `server/config/virtual_join_rules.json` | 파일 없음 | rules `{}` |
| `server/config/chain_rules.json` | 파일 없음 | `ledger_v2_execution` selector만 신설 |
| `server/config/enrichment_rules.json` | 빈 `{}` | enrichments `{}` |

나머지 table 15개는 인제션·맵·UI 등 다른 subsystem이 사용하는 전역 물리 선언이며 현재
legacy Ledger source가 아니다. 이를 Ledger v2 catalog에 무조건 복사하면 새 root와 전역
`table_config.json`이 같은 의미를 동시에 소유하므로 이번 cutover에서는 제외했다.

## `lot_event` 변환

| 의미 | legacy | v2 |
|---|---|---|
| physical identity | `txn_seq` | catalog business key `txn_seq` |
| physical time | `event_time`, Asia/Seoul | same, timezone explicit |
| alias | config `columns` map | `LiveLotEventSourcePreparer` output |
| event unit | lineage mapper | prepared `event_group_key` |
| Claim 조립 | chain mapper/translator | RoleEmission → Pack compiler |
| cursor | `{event_time}` | `{event_time, txn_seq}` |
| execution approval | implicit config selection | selector parity `approved` + Stage 6 exact commit |

Stage 6에서 split 10, merge 11, track-in 5 Claim의 의미 parity가 승인됐다. production legacy
config에는 raw event vocabulary로 split/merge만 적혀 있었으나 v2 mapper의 track-in 경로는
그 승인 fixture로 고정됐다. 이 차이는 새 config에서 숨기지 않고 Stage 6 approval ref로
selector에 기록한다.

## 자동 변환 불가·대기

- 기존 cursor row는 v2 cursor shape로 자동 변환하지 않는다: `pending / reset approval required`.
- 운영 Ledger Atom/cursor count·backup 위치는 안전한 DB 대상이 확정되지 않아 미측정이다.
- DT/observation은 현재 live legacy Ledger 선언에 없고 v2 Profile/실측 parity도 없어 생성하지
  않는다.
- dependency replay worklist는 해당 source가 v2로 추가될 때까지 pending이다.
- legacy config 이동/삭제는 별도 은퇴 승인 전까지 pending이다.

## 보존 증명

이번 변환은 새 root 파일만 추가했다. `server/config/ledger_config.json`,
`server/config/table_config.json`, `server/config/enrichment_rules.json`의 byte content를 수정하지
않았고 `_archive` 이동도 수행하지 않았다. reset/drop/truncate/delete 경로는 Stage 7 runtime
module에 존재하지 않는다.
