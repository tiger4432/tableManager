# Ledger v2 2단계 재승인 검증 보완

## 배경

최초 2단계 loader는 정상 Bundle 계약은 검증했지만 malformed nested JSON 일부가 semantic
교차검증에서 일반 Python 예외로 샐 수 있었고, 사용되지 않은 Vocabulary/Pack은 Profile 경로를
타지 않으면 교차검증되지 않았다.

## 해결

- 구조 검증 실패 시 semantic lookup 전에 결정적 오류 목록으로 종료
- invalid UTF-8, 문법 오류, NaN/Infinity를 `invalid_json`으로 거절
- 모든 Vocabulary/Pack 및 미사용 Profile/Mapper 참조 전수 검증
- emission subject/object/time/qualifier Role의 실재·kind·optionality 검증
- Profile packs/mapping use/Mapper emits 상호 대조
- Mapper input/Profile leaf column 및 Preparer output 충돌 검사
- Source row/group, Mapper unit, catalog key/index/UNIQUE 선언 검사

## 검증

- 2단계 전용: `63 passed, 1 skipped`
- Ledger 핵심 합산: `310 passed, 1 skipped`
- malformed node shape 전수와 node별 JSON 값 종류 6종, 총 900건 이상 대입
- 모든 거절은 `code/path/message`를 보유
- DB/runtime/compiler/translator/cursor 변경 없음

2단계는 계속 `IN_REVIEW/NOT_APPROVED`이며 3단계를 시작하지 않았다.
