# Ontology Config Explorer Completion Audit round-1 보완

## 현상

전체 완료 후보 `1860714`의 독립 Audit에서 세 반례가 확인됐다. 저장한 초안을 다시 편집한 뒤
keep으로 이동하고 back하면 unsaved buffer가 서버 저장본으로 되돌아갔다. file-backed transfer
sample은 마지막이 `CoreDie→FinalChip`으로 갈라졌고, reference edge diff는 target 교체를
removed+added로만 표현했다.

## 근본 원인

- navigation checkpoint가 editor cursor만 저장하고 text/dirty/draft identity를 저장하지 않았다.
- transfer 예제의 `component_of@1` subject와 마지막 Mapping이 CoreDie를 가리켰다.
- edge ID가 target을 포함한 content identity였고 diff가 ID 집합만 비교했다.

## 수정

- checkpoint에 editor text/dirty/cursor와 draft id/revision/target을 함께 보존한다. 서버 응답 뒤
  active context token과 pinned draft identity가 모두 일치할 때만 buffer를 복원한다.
- sample의 마지막 claim/Mapping을 `BondComponent→FinalChip`으로 고쳐 전체 경로를 연속화했다.
- edge의 안정된 논리 위치(from/reference-kind/leaf pointer)와 비교 내용(target/status/normalized
  meaning)을 분리해 added/modified/removed/unchanged 네 상태를 산출한다.

## 검증

- backend 직접 범위: `165 passed`
- Explorer state harness: `35 assertions, 0 failed`
- client contracts `7/7`, clipboard convention pass, Vite 107-module production build pass
- 실제 UI: 저장→재편집→keep→이동→back→forward→back에서 marker와 cursor 바이트 동일
- full server suite/PostgreSQL E2E는 사용자 지시에 따라 미실행

## 상태와 안전

상태는 `ONTOLOGY_CONFIG_EXPLORER_COMPLETION / IN_REVIEW / NOT_APPROVED`다. 운영 config/DB,
runtime mapper/translator/cursor/gate/store, migration/reset/replay/legacy는 변경하지 않았다.
사용자 소유 task 파일 두 개도 수정·커밋하지 않았다. 후속 exact commit을 동일 Audit task에
재제출한다.
