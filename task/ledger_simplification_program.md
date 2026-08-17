# [Program] Ledger 단순화 — ledger_config와 mapper 함수만 보면 되게

> **상태:** 착수 승인됨 (소유자, 2026-08-18)
> **소유자 지시:** 「ledger_config랑 mapper 함수만 바라보면 되게 하고, chains는 왜 필요한지
> 검토해서 없앨 수 있으면 없애고 그냥 ledger config 활성화되게 해. explorer 개선이랑 엮어서
> 다 진행해. 저쪽에 explorer UI 감사도 지시해뒀으니 그 결과도 끝나면 같이 반영해서 하라고 해」
> **검수 등급:** T1 (QA 2인 병렬 + 독립 감사) — 데이터 경로·로더·UI가 동시에 걸린다
> **구성 과제:** `ledger_config_single_file_pending.md` ·
> `lot_event_mapper_restandardization_pending.md` · `ontology_config_authoring_mode_pending.md`

## 완수 목표 — 한 문장

셋업을 하는 사람이 **두 곳만** 본다.

1. `server/config/ontology/ledger_config.json` — 무엇을 어떻게 기록할지의 전부
2. 매퍼 함수 하나 — 그 소스의 업무 해석만. 단순 소스는 이것조차 필요 없다

manifest·chains·enrichments·virtual_joins·신뢰 목록·cutover라는 이름은 셋업하는 사람의
시야에서 사라진다.

## 기준선 — 이미 떠 뒀다

- 확정 config 스냅샷: `363c693e9fd2dfe5391fbdc67247bcd46372910bf573bae289ff788495a757b3`
- 원자 기준선: `task/evidence/ledger_atom_baseline_20260818.json`

| 사건 | 분자 | 원자 | incomplete |
|---|---|---|---|
| split (완전) | 1 | 9 | 0 |
| split (자식 결번) | 1 | 7 | 1 |
| merge (완전) | 1 | 11 | 0 |
| track_in | 1 | 7 | 0 |

**모든 단계의 합격 조건은 이 표와 파일에 대한 디프 0이다.** 숫자가 하나라도 달라지면
그 라운드는 실패다. 「더 좋아졌다」는 사유로 넘어가지 않는다. 원자 내용이 바뀌어야 하는
변경이라면 착수 전에 판정을 받는다.

떠 두는 방식(참고용, 상시 도구로 승격할 것):
`load_cutover_setup(root)` → `preview_selected_cursor_batch(...)`.
DB·gate·store·cursor를 건드리지 않는다.

## 실행 순서 — 셋이 맞물린다

### 1라운드. 자기 등록 + 단일 파일 (`ledger_config_single_file_pending.md`)

- 구현 클래스 자기 등록으로 전환, 손수 관리하는 신뢰 목록 세 곳 제거
- 잠겨 있던 `DeclarativeRoleMapper`·`DirectJoinSourcePreparer` 개통
- chains·enrichments·virtual_joins 제거, `tables`를 `ledger_config.json`의 섹션으로 흡수
- manifest 소멸, `setup_version` 3, 모듈명에서 `cutover` 제거
- 기존 5파일 루트 → 단일 파일 일회성 변환기

**이 라운드의 별도 합격 조건:** 파이썬 0줄로 단순 소스 하나가 원자를 낸다(범용 구현만
사용). 증명 없이 다음 라운드로 넘어가지 않는다.

### 2라운드. 매퍼 개주 (`lot_event_mapper_restandardization_pending.md`)

- 배선(프로필 탐색·엔터티 조립·첫 등장 중복 제거·mapping 해석)을 엔진으로 이관
- 매퍼에는 업무 해석만 남긴다 (현행 475줄 중 ~75줄)
- 죽은 `LotEventSourcePreparer` 정리
- **판정 기준: 매퍼 파일에서 `mapping_id`·`claim_ref` 문자열 0개**

### 3라운드. Explorer 작성 모드 (`ontology_config_authoring_mode_pending.md`)

- 선언 생성·삭제·이름 변경 (현재 전무 — 이것이 1순위)
- 백지 입구 (config 없을 때 500 대신 명명된 결핍 + 최초 뼈대 생성)
- 여섯 걸음 작성 흐름, 닫힌 목록은 전부 서버 공급
- 고정 철자 항목은 선택 불가 + 이유 표시
- 거짓 초록 5건 제거

## 외부 감사 결과 반영

소유자가 **다른 레인에 explorer UI 감사를 지시**해 두었다(2026-08-18). 그 결과가 도착하면
3라운드 착수 전에 지시서에 병합한다. 이미 이쪽에서 확인한 결함(생성 불가, 백지 500,
하드코딩 초록 3종, 페이지 이동 없음, 렌더 검사 테스트 0)과 **중복되면 하나로 합치고,
어긋나면 실측으로 판정**한다. 감사가 도착하기 전에 3라운드 UI 구현을 시작하지 않는다.
1·2라운드는 감사와 무관하므로 기다리지 않는다.

## 관통 규율

- **원자 디프 0**이 모든 라운드의 최상위 게이트다.
- 라운드마다 착수 전 «무엇이 바뀌고 무엇이 그대로인가»를 한 문단으로 보고한다.
- 공유 트리다. `git add`와 `git commit` **양쪽에 경로를 붙인다**. `-a`/`-A` 금지.
- 소유자가 `server/config/ontology/`를 직접 편집 중일 수 있다. 이 경로를 고쳐야 하면
  먼저 알린다. 변환기는 **원본을 지우지 않고** 새 파일을 만든 뒤 대조 결과를 보고한다.
- DB reset·커서 이동·백필 실행은 이 프로그램의 범위가 아니다. 부작용으로도 수행하지 않는다.
- 문구를 발명하지 않는다. 화면의 오류 문장은 검증기가 내는 코드와 경로를 그대로 쓴다.

## 완료 판정

- [ ] 셋업하는 사람이 `ledger_config.json`과 매퍼 함수 외의 파일을 열지 않고 소스를 세운다
- [ ] 단순 소스는 파이썬 0줄로 개통된다
- [ ] 원자 기준선 디프 0
- [ ] 매퍼 파일에 `mapping_id`·`claim_ref` 문자열 0개
- [ ] explorer에서 선언 생성·삭제가 되고, 백지 상태에서 들어갈 수 있다
- [ ] 포크(총괄)가 브라우저로 여섯 걸음을 직접 한 바퀴 돌았다
