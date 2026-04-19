# AssyManager Master Technical Guide (Enterprise Edition)

본 문서는 AssyManager 프로젝트의 **최상위 마스터 기술 가이드**입니다. 시스템의 아키텍처, 데이터 흐름, 비즈니스 규칙, 그리고 트러블슈팅에 관한 모든 정보를 집대성하며, 새로운 개발자가 즉시 프로젝트에 투입되어 디버깅 및 확장을 수행할 수 있게 하는 것을 목적으로 합니다.

---

## 🗺️ 1. 시스템 아키텍처 개요

AssyManager는 반도체 및 패키징 산업의 복합 데이터를 관리하기 위해 설계된 실시간 데이터 플랫폼입니다.

- **Frontend**: PySide6 기반의 가상 로딩 테이블 및 사이드 패널 시스템.
- **Backend**: FastAPI 기반의 비동기 API 서버 및 가중치 우선순위 엔진.
- **Data**: PostgreSQL 상의 동적 JSONB 스토리지 및 GIN 색인 기반 로그 트리거 시스템.

> [!TIP]
> 상세 아키텍처 맵과 UI 제어 흐름은 **[시스템 아키텍처 분석서](../analysis/ARCHITECTURE_ANALYSIS.md)**를 참조하십시오.

---

## 🌊 2. 데이터 제어 및 무결성 (The Pulse)

시스템의 모든 데이터는 발생 시점부터 UI 반영까지 다음의 파이프라인을 거칩니다.

1. **데이터 획득**: 실시간 인제션 또는 사용자 직접 수정.
2. **우선순위 결정**: 레이어링 엔진이 `user` vs `system` 가중치를 비교하여 표시 값 결정.
3. **영속화 및 전파**: DB 저장 즉시 WebSocket(`WsListenerThread`)을 통해 모든 클라이언트에 브로드케스트.
4. **가상 렌더링**: 클라이언트가 대량의 데이터를 청킹(Chunking)하여 끊김 없이 표시. (v1.4: Search Session Guard를 통한 데이터 무결성 보장)

> [!IMPORTANT]
> 실시간 동기화와 가상 로딩 기술 명세는 **[데이터 동기화 명세서](../spec/DATA_SYNC_SPEC.md)**에서 확인할 수 있습니다.

---

## ⚡ 3. 고성능 배치 처리 엔진 (Batch Processing)

AssyManager는 수만 건의 자동화 로그를 지연 없이 처리하기 위해 배치 처리 엔진을 내장하고 있습니다.

- **Ingestion**: 50개 단위 청크 전송.
- **Floating Logic**: 업데이트된 행이 자동으로 최상단으로 부상하여 실시간성 확보.
- **Deduplication**: 중복 잔상(Ghost Row)을 완벽히 제거하는 엄격한 아이디 매핑.
- **Sync Consistency (v1.5)**: 외부 변경 시 서버 기반 Total Count 재동기화 및 **Zero-Lag(0ms) UI 동기화** 적용.
- **Precise Search**: 보이는 컬럼 및 사용자 선택 컬럼에 대한 정밀 필터링 지원.

> [!NOTE]
> 인제션 파이프라인과 배치 시퀀스는 **[배치 처리 기술 명세서](../spec/BATCH_PROCESSING_SPEC.md)**에 상술되어 있습니다.

---

## ⚖️ 4. 비즈니스 룰 및 우선순위 (The Brain)

데이터의 '진실된 값'을 결정하는 로직입니다.

- **데이터 레이어링**: 한 셀에 여러 소스의 데이터를 중첩 보관.
- **수동 고정(Pinning)**: 특정 소스의 값을 표시 값으로 강제 지정.
- **감사 추적(Audit)**: 모든 변경 이력을 보존하여 데이터 정합성 보장.

> [!TIP]
> 레이어링 엔진과 우선순위 규칙은 **[비즈니스 로직 명세서](../spec/BUSINESS_LOGIC_SPEC.md)**를 참조하십시오.

---

## 🛠️ 5. 디버깅 및 유지보수 (The Debugger's Portal)

시스템 장애 발생 시 즉시 대응할 수 있는 전문적인 가이드를 제공합니다.

- **주요 장애 유형**: DLL 로드 실패, WebSocket 끊김, 고스트 행 현상 등.
- **해결책**: 환경 설정 보정, 통신 상태 감시, PostgreSQL 쿼리를 통한 직접 검증.

> [!CAUTION]
> 장애 발생 시 당황하지 말고 **[트러블슈팅 및 디버깅 가이드](../spec/DEBUGGING_GUIDE.md)**의 체크리스트를 따르십시오.

---

## 🚀 6. 시스템 확장 가이드 (Developer's Appendix)

### 6.1 새로운 테이블 추가 시 (Step-by-Step)
1. `server/config/table_config.json`에 신규 테이블 정의 (컬럼명, 비즈니스 키 등).
2. 서버 재시작 시 자동 인식.
3. 클라이언트 실행 시 `NavigationRail`에 자동 아이콘 매핑.

### 6.2 커스텀 파서(Parser) 구현 시
- 각 워크스페이스의 `scripts/custom_parser.py`를 작성하여 `AdvancedIngester`에 플러그인 형태로 연결 가능합니다.

---
*AssyManager Enterprise Master Documentation v2.2 | 2026.04.20 (Precise Search & Zero-Lag Sync Revision)*
