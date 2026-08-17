# Ledger V2 Stage 5 source preparation 구현

- 단계/상태: `STAGE_5_IN_REVIEW / NOT_APPROVED`; Stage 6 미착수
- 현상: 기존 cursor는 base relation만 읽으며 virtual-only identity를 직접 SELECT할 수 없음
- 구현: sealed DataFrame SourcePreparer, physically verified descriptor 공유, 1000-key batch read,
  output collision 방지, EventFrame right provenance와 dependency replay 후보
- 반례: join 0건/다건/결측, left output 충돌, pending/rejected nested Binding은 mapper 전에 거절
- scale: 1001 unique key fixture가 정확히 2회 query; 행별 query 없음
- R&D fixture: multi-Core→DT→Bond와 multi-Core→FinalChip을 방향 Claim으로 컴파일, same_as 0
- 경계: DB migration/write, cursor advance, gate/store transaction, 운영 config 변경 0
- 테스트: Stage 5 직접 `18 passed`; 직접 영향군 `339 passed, 1 skipped`
- 다음: exact commit 독립 Audit; 승인 전 Stage 6 금지
