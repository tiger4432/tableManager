# Ontology Codex 단계별 실행계획

이 폴더의 지시서는 `tiger4432/tableManager`에서 온톨로지 설정을 단순화하고, 첫 제품 수락 사례로 Bonding Lot/Slot에서 DT·Core Lot/Slot을 추적하기 위한 Codex 작업 묶음이다.

## 실행 원칙

- 파일을 한 번에 전부 Codex에 주지 않는다.
- `00_MASTER_PLAN.md`로 조사 계획을 먼저 승인받는다.
- 이후 `01`부터 순서대로 한 단계씩 실행한다.
- 매 단계 시작 시 `COMMON_ARCHITECTURE_RULES.md`를 함께 제공한다.
- 이전 단계의 테스트는 다음 단계의 회귀 기준으로 유지한다.
- 첫 사용 사례는 Lot/Slot이지만 공통 Profile·compiler·trace engine은 도메인 이름을 모르게 한다.
- 각 단계 종료 후 결과를 검토하고 `APPROVAL_MESSAGES.md`의 승인 문구로 다음 단계만 허가한다.

## 실행 순서

1. `00_MASTER_PLAN.md` — 저장소 조사와 전체 실행계획, 코드 수정 없음
2. `01_LINEAGE_BASELINE.md` — 기존 이벤트로 Bonding→DT→Core 계보 증명
3. `02_PROFILE_SCHEMA.md` — 범용 Source Ontology Profile 스키마
4. `03_COMPILER_DRY_RUN.md` — Profile을 기존 translator로 컴파일하고 parity 검증
5. `04_SETUP_WIZARD.md` — 템플릿 기반 설정 마법사
6. `05_LOT_SLOT_TRACE_API.md` — 범용 trace engine 위 Lot/Slot 전용 API
7. `06_TRACE_UI_AND_ACCEPTANCE.md` — 추적 화면과 end-to-end 수락 검증

## 핵심 구조

```text
범용 기반
├─ SourceOntologyProfile
├─ TemplateRegistry
├─ CompilerRegistry
├─ SourceAdapterRegistry
├─ TraceQuery / TraceResult
├─ GenericTraceEngine
└─ TargetMatcher
        │
        └─ 첫 제품 기능
           └─ LotSlotTraceFacade
              └─ Bonding → DT/Core
```

인터페이스는 범용으로 두되, 처음 구현하는 템플릿은 `lot_lineage`와 `transfer`, 첫 수락 fixture는 Bonding→DT→Core로 제한한다.

