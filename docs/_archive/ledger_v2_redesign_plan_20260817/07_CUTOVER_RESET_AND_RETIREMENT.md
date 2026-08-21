# 7단계 — Cutover, 선택적 원장 Reset, Legacy 은퇴

> 구현 상태: `COMPLETE` · 승인: `APPROVED` · exact commit `f516268eadae5505c586ce5235e76dd729c1e573`
> 비파괴 범위: manifest/config root, `lot_event` selector, dry-run·existing cursor/store 연결
> 별도 승인 대기: 운영 Ledger/cursor reset, legacy config/code 이동·삭제

## 전제

다음이 전부 충족돼야 착수한다.

- 1~6단계 사용자 승인
- source별 parity `equal` 또는 승인된 `explained_difference`
- PostgreSQL 성공/실패 E2E 초록
- baseline 대비 신규 실패 0
- `server/config/ontology/manifest.json`만 진입해 전체 source snapshot 생성 가능
- exact reset 대상과 복구 절차 승인

## 7.1 설정 전환

1. 기존 flat config를 `server/config/ontology/` 디렉터리로 변환하는 read-only report 생성
2. 자동 변환 불가 필드는 `missing/pending`으로 남김
3. v2 config validation·dry-run 재실행
4. source별 execution selector를 v2 snapshot으로 전환
5. legacy flat config는 `_archive`로 이동하되 삭제하지 않음

전환 직후에도 DB reset은 자동 수행하지 않는다.

## 7.2 Reset 사전 보고

파괴 작업 전에 다음을 사용자에게 실제 값으로 보고한다.

```text
database/server/schema
ledger table 정확한 이름과 행 수
cursor table 정확한 이름과 행 수
source/audit/enrichment/map table은 대상 아님
backup/snapshot 위치
재백필 source 순서와 예상량
중단/복구 절차
```

`DROP`, broad schema reset, source table 삭제는 허용하지 않는다. 기본 후보는 정확히 확인된
Ledger Atom 행과 Ledger cursor뿐이다.

## 7.3 별도 파괴 승인

사용자가 reset을 명시 승인한 뒤에만 실행한다. 경로·환경·대상을 다시 읽기 전용으로 확인하고,
명시된 PostgreSQL transaction 안에서 수행한다. reset 결과는 삭제 건수와 복구 가능성을
즉시 보고한다.

사용자가 reset을 승인하지 않으면 기존 원장을 보존하고 별도 격리 schema에서 v2를 운용한다.

## 7.4 재백필

- 의존 source 순서를 Bundle에서 계산
- source별 batch/cursor 진행률 기록
- gate refusal을 숨기지 않음
- source 완료마다 coverage/structure/parity 확인
- 실패 source에서 멈추고 다음 의존 source로 진행하지 않음

## 7.5 Legacy 은퇴

재백필과 read API 검수 후 다음 순서로 한다.

1. legacy 진입점 차단
2. live config/UI에서 legacy 선택지 제거
3. translator/template 코드를 archive 또는 후속 커밋에서 삭제
4. explicit historical import 문은 별도 유지
5. 문서의 기존 설정법을 v2로 교체

legacy 코드 삭제와 데이터 reset은 같은 커밋/작업으로 묶지 않는다.

## 최종 검수

- 모든 live source가 v2 snapshot 경로만 사용
- authoring root는 `server/config/ontology/` 하나이며 manifest 밖 입력 0
- Registry 등록값 code builtin 0
- direct raw Atom/payload mapper 0
- Entity/Pack/Vocabulary/Source 교차 검사 초록
- Ledger Profile/compiler DB lookup 0
- cursor와 Atom transaction 원자성 유지
- trace/coverage/structure/siblings/journey 회귀 없음
- 운영자는 `server/config/ontology/` 한 루트와 dry-run 결과만으로 source를 셋업 가능
- legacy 호출은 명확한 retired 오류를 반환

## 되돌림

- v2 selector 비활성화
- archive한 legacy config 복원
- reset을 실행했다면 승인된 backup 또는 source 재백필로 복구
- 되돌림 중 v2/legacy를 같은 cursor version으로 섞지 않음

비파괴 cutover는 독립 Audit과 사용자 상설 승인을 통과했다. 선택적 reset과 legacy 삭제는
별도 파괴 승인 없이는 실행하지 않는다.

## 현재 구현 판정

- `server/config/ontology/manifest.json`만으로 현재 live Ledger source `lot_event`의 ready
  snapshot을 만든다.
- operator CLI의 기본은 manifest selector이며 이 경로는 legacy flat config를 import/load하지
  않는다. `--config`는 명시적 `--legacy`에서만 허용된다.
- `--legacy`는 별도 은퇴 승인 전 compatibility escape hatch지만 destructive approval 경계를
  우회할 수 없다.
- physical `lot_event` 열을 `LiveLotEventSourcePreparer`가 Stage 6에서 검증된 logical
  EventFrame으로 정규화한다. compiler core에는 source 이름 분기가 없다.
- 기존 cursor가 legacy의 `{event_time}` 모양이면 v2 `{event_time, txn_seq}`와 섞지 않고
  `legacy_cursor_reset_required`로 Atom 0·cursor 미이동한다.
- cursor reset/replay 옵션은 모든 공개 CLI mode에서 v2/legacy dispatch와 config/DB/source/store
  접근 전에 `destructive_approval_required`로 차단한다.
- 기존 config 이동, legacy 코드 삭제, DB reset은 실행하지 않았다. 이 선택 항목은 정확한
  대상·백업·복구 절차에 대한 별도 승인 뒤에만 수행한다.

세부 근거는 [STAGE_7_ACCEPTANCE_EVIDENCE](./STAGE_7_ACCEPTANCE_EVIDENCE.md)와
[LEGACY_CONFIG_CONVERSION_REPORT](./LEGACY_CONFIG_CONVERSION_REPORT.md)에 있다.
