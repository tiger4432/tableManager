# docs(design): DT/Tape 계층 편입 + Universal Transfer Plan / DOE 관리 단위 확정

- **일시**: 2026-07-26
- **커밋**: `63ac0c3` (스펙 §7.5b + 보드) · `437d6d5` (보드 — align/by_eqp/M1 설계 결정 + 이슈 #11 등재)
- **성격**: 설계 확정 기록(코드 변경 없음). 스펙 본문은 총괄 작성 — 이 문서는 히스토리 요약만.

## 1. DT(Die Transfer)/Tape 계층 편입 (스펙 §7.5b, 사용자 도메인 공개)

실제 물류 체인에는 코어와 본딩 사이에 **테이프 계층**이 있다: 여러 코어의 칩을 TAPE 위에 한데 모아두고(DT 공정) 본딩은 테이프에서 집는다.

- **bonding_log의 core_lot/slot은 실제로는 DT(테이프) lot/slot** — 칩의 진짜 출신 코어는 `테이프 좌표 × DT 맵(영역→코어)` 또는 칩 단위 DT 로그로 해석.
- 원천 2종: **DT 로그**(칩 단위 코어 좌표↔테이프 좌표 대응) + **DT 맵**(테이프 lot|slot 자체 맵 — 영역→코어 귀속).
- 함수형 온톨로지 확장: `DTEvent: (WaferState_in, TapeState_in) → (WaferState_out, TapeState_out)` — Tape는 동적 노드. 칩 계보는 `Base ← bonding ← TapePos ← DT ← Core`의 **2단 전사**.
- 좌표 프레임: defect/EDS는 core frame, DT 맵·bonding 좌표는 tape frame — 프레임 간 다리는 변환이 아니라 **DT 로그 조인**(칩 단위 대응이 데이터로 존재).

## 2. Universal Transfer Plan 프레임워크 (보드 — M2 재정의)

사용자 확정 2건(**테이프에도 불량 섞임** + **DT 구성도 계획 대상**)에 따라 본딩 실험계획을 단계 특화 기능이 아닌 **전사(轉寫) 프리미티브의 프레임워크**로 재정의:

- 모든 단계 = `(stage, target 맵 페인팅, assignments[소스, 소스 영역, 타깃 값(층/코어), 수량])`.
- 가용 = 총 − fail류(역할 바인딩) − 기전사(단계 전사 로그). 테이프 가용은 **코어 fail의 DT-조인 투영**으로 제외.
- 신규 단계 = config stage 선언만(코드 불변). 온톨로지는 `TransferEvent` 일반화(DTEvent/BondingEvent는 인스턴스).
- M1 산출물(Info 패널 + core-summary)은 첫 인스턴스로 흡수.

## 3. 관리 단위 = value(DOE) (사용자 확정)

"붙이는 행위"를 페인팅 **value = DOE 조건군**으로 관리: `value ↦ {소스, knob/조건, 수량, 자연어 설명}`, 페인팅 = DOE의 공간 분포.

- map_split_registry(value=실험 split)의 직계 확장 — SplitCondition 노드 = DOE로 온톨로지 정합.
- 계획 DOE vs 실제 knobs vs 불량 분포가 그래프 한 체인 → G3에서 "어느 DOE에서 불량 군집" 질의 가능.

## 4. 파급/다음 단계

- rect 영역 선택 모드 폐기(페인팅 단일 정본)의 근거 설계 — [M1 히스토리](./20260726_093200_bonding_plan_m1_info_panel_and_core_summary.md) 참조.
- M2 재설계 요구: 역할 바인딩에 dt_log/dt_map 추가, 잔여 계산 2단계(코어 잔여 vs 테이프 위 가용), 계획 페인팅은 DT 테이프 맵 위에서.
- 단계: M2(관리 테이블 2종 + 온톨로지 ExperimentPlan·PlanLayer·TransferEvent) → M3(실적 대조·중복 배정 감지·EDS 연동).
- 착수 전 사용자 확인 잔여 2건: ① defect/EDS 원천 위치 ② 실로그의 knob 형태.
