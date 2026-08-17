# 6단계 — Shadow parity와 PostgreSQL E2E

## 목표

운영 config나 원장을 바꾸기 전에 동일 source event를 legacy와 v2 양쪽에 읽기 전용으로
통과시켜 의미 차이를 증명한다. 그 뒤 격리 PostgreSQL에서 v2의 실제 transaction을 검증한다.

## 비교 정규형

DB UUID나 코드 fingerprint처럼 실행별로 달라질 수 있는 필드는 비교 규칙을 먼저 선언한다.

필수 의미 비교:

```text
source event identity/state
subject type/keys
predicate
object kind/payload
occurred_at
source who/raw ref
derivation/epistemic class
supersedes semantics
claim count and molecule atomicity
refusal/incomplete state
```

차이는 다음 셋 중 하나로 분류한다.

- `equal`
- `explained_difference` — 사용자 승인 문구와 fixture 포함
- `regression`

설명 없는 차이는 7단계 전환을 막는다.

## Shadow 대상

최소 다음 source 모양을 포함한다.

1. 단순 한 행→Claim
2. lot split/merge/track-in 같은 다중 행 grouping
3. DT 이동: 한 job에 여러 source wafer/core, qty 포함
4. source-preparation join 0/1/다건
5. stage-local Entity의 carrier key와 grid 좌표
6. observation/finding 계열
7. missing/pending/rejected 설정
8. source 이름과 column 이름을 완전히 바꾼 동일 Pack
9. virtual join rule 상속과 잘못 기록된 left value 대 confirmed right value 대조
10. right row 늦은 도착과 성공 후 사후 수정

## PostgreSQL E2E

격리 schema에서 다음 전체 흐름을 검사한다.

```text
Bundle load/validate
→ immutable snapshot
→ dry-run EventFrame/RoleFrame/LedgerFrame
→ execute same snapshot/compiler
→ gate
→ LedgerStore
→ Atom insert + cursor advance one transaction
→ read API trace/coverage/structure
```

실패 E2E:

- pending Binding
- rejected Binding
- nested Entity key Binding 미승인
- source-preparation join 0건
- source-preparation join 다건
- inherited join rule missing/disabled/rejected
- left relation과 join rule left_table 불일치
- stage-local Entity wrong type/key/coordinate
- Pack/Vocabulary emission mismatch
- mapper crash/invalid RoleFrame
- `BaseLedgerMapper.map()` override 등재 거절
- 기본 DeclarativeRoleMapper와 등록 Python mapper의 RoleFrame 계약 동등성
- mapper emits/Profile/Pack 불일치
- gate refusal
- store failure

모든 실패는 Atom 0·cursor 미이동·source/join relation 불변이어야 한다.

## Scale 검증

- source-preparation join 1001+ unique keys batch 수 측정
- source page/group memory 상한
- 1,000만 행 기준 index 사용 EXPLAIN
- 큰 OFFSET 없음
- replay dedupe와 cursor restart
- profile/snapshot 변경 시 cursor version 충돌이 조용히 skip하지 않음
- right dependency 변경이 이미 처리한 left event의 replay worklist로 연결됨

## 회귀 판정

1. 변경 전 baseline 명령과 환경 보존
2. 실행 가능한 테스트 전부 통과
3. skip 이유 그룹화
4. baseline 대비 신규 실패 0
5. baseline 불가 영역은 미검증으로 보고
6. 기존 read API 응답 계약 diff

## 산출물

- source별 parity matrix
- explained differences 승인 목록
- PostgreSQL 성공/실패 transaction 증거
- query plan/source-preparation batch 측정
- read API regression 결과
- cutover go/no-go 자체 판정

dependency replay가 없거나 미검증이면 다른 테스트가 초록이어도 cutover 판정은 `NO-GO`다.

완료 후 멈추고 6단계 및 reset 가능 여부 승인을 기다린다.
