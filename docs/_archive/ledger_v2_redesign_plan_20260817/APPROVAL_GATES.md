# 단계별 승인 게이트

각 문장은 해당 단계의 실제 측정값과 파일 목록으로 채운다. 승인 전 다음 단계 작업 금지.

## 1단계 승인 요청

```text
Ledger v2 1단계 조사 완료. 하드코딩 N건을 keep/move/retire로 분류했고,
기존 Position/lookup 하드코딩 제거 대상, Pack/Vocabulary/source-event 중복 계약과 baseline을 첨부했다.
코드·DB 변경은 없다. 2단계 LedgerSetupBundle schema 구현을 승인하는가?
```

## 2단계 승인 요청

```text
단일 LedgerSetupBundle schema와 validator 완료. 최종 normalized Bundle,
오류 code/path/message, 결정성 테스트, DB write 0 근거를 첨부했다.
runtime/compiler는 아직 없다. 3단계 Registry와 교차 검증을 승인하는가?
```

## 3단계 승인 요청

```text
Vocabulary/Entity/Pack/Source Registry와 immutable snapshot 완료.
Pack↔Vocabulary, stage-local Entity exact keys, source output schema 교차 검증 결과를 첨부했다.
source row/DB 실행은 아직 없다. 4단계 RoleFrame/Pack compiler를 승인하는가?
```

## 4단계 승인 요청

```text
기본 `DeclarativeRoleMapper`와 등록 Python mapper가 공통 `BaseLedgerMapper.map()`을 통해
같은 pandas RoleFrame을 만들고 Pack compiler만 LedgerFrame을 생성한다. 개별 mapper 자유
코드는 `interpret_unit()`으로 제한한다. raw payload mapper 거절, dry-run write 0, 결정성
결과를 첨부했다.
기존 driver/store 연결은 아직 없다. 5단계 실행 연결을 승인하는가?
```

## 5단계 승인 요청

```text
기존 Ledger driver/cursor 뒤에 pandas source preparer와 stage-local Entity validator를
연결했다. verified virtual-join rule 상속, batch join 성공, 0/다건 실패 Atom0/cursor 불변,
right relation 늦은 도착·사후 수정 replay 근거를 첨부했다.
운영 전환은 아직 없다. 6단계 shadow parity/PostgreSQL E2E를 승인하는가?
```

## 6단계 승인 요청

```text
source별 legacy↔v2 parity와 PostgreSQL E2E 완료. equal N, 승인 필요 차이 N,
regression N, baseline 대비 신규 실패 N, skip 분류를 첨부했다.
운영 config 전환과 reset 가능 여부를 각각 승인하는가?
```

## 7단계 파괴 승인 요청

```text
reset 후보는 <database>.<schema>의 <ledger table N행>과 <cursor table N행>뿐이다.
source/audit/enrichment/map 데이터는 대상이 아니다. backup은 <path>, 복구는 <procedure>다.
이 정확한 대상의 reset과 v2 재백필을 승인하는가?
```

reset 승인과 legacy 코드 삭제 승인은 별개로 받는다.
