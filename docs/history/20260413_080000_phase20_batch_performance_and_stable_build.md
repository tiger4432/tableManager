# 20260413_080000_phase20_batch_performance_and_stable_build

## 1. 개요 (Overview)
본 문서는 `assyManager`의 성능 한계를 극복하기 위해 수행된 배치 인제션 도입, UI 성능 최적화, 그리고 클라이언트 배포 안정화 작업을 통합 기록합니다.

## 2. 주요 성과 (Key Achievements)

### 2.1 고성능 배치 인제션 (Batch Ingestion)
- **문제**: 초당 수백 건의 단일 `/upsert` 호출로 인한 서버 부하 및 UI 지연.
- **해결**: 데이터를 50행 단위로 묶어 송신하는 `/upsert/batch` 워크플로우 도입.
- **성과**: 수만 건의 데이터 인제션 시에도 시스템 안정성 및 반응성 확보.

### 2.2 UI 응답성 및 UX 개선 (UI/UX Optimization)
- **로그 서머리**: 히스토리 패널에서 10건 이상의 업데이트 발생 시 요약 로그로 전환하여 렌더링 부하 방지.
- **정밀 편집**: 셀 더블 클릭 시 기존 값 유지(`EditRole`) 및 실제 값 변경이 없는 수정 시 API 호출을 차단하여 불필요한 트래픽 억제.

### 2.3 클라이언트 배포 안정화 (Build & DLL Isolation)
- **문제**: PyInstaller 빌드 시 외부(Conda base 등) DLL 간섭으로 인한 `ImportError`.
- **해결**: 
  - `main.py`에 강력한 **원천 격리(Source Isolation)** 로직 적용.
  - 가상 환경(`assy_manager`) 내부의 PyInstaller 도구 정합성 확보.
  - `UPX` 기능을 비활성화하여 Qt DLL의 무결성 보존.

## 3. 검증 결과 (Validation)
- 배치 인제션 실시간 연동 테스트 성공 (서버 로그 확인 완료).
- `AssyManagerClient.exe` 단일 실행 파일 구동 및 DLL 로드 성공 확인.

---
*본 문서는 Phase 20의 모든 기술적 의사결정과 결과물을 공식 보존합니다.*
