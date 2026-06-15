# Ingestion Workspaces, Chain Rules, and Mappers Monitoring Support in Admin Console

## 1. 개요 (Overview)
- **목적**: 어드민 콘솔 내에서 시스템의 파일 인제션 워크스페이스 정보, 연쇄 적재 규칙(체인 룰), 그리고 커스텀 맵퍼 모듈 정보를 직접 모니터링할 수 있는 UI 및 조회 API 제공
- **작성일**: 2026년 06월 16일

## 2. 변경 내용 (Changes)
### 2.1 Backend API 추가 (`server/main.py`)
- `GET /admin/file-ingestion/workspaces`: `ingestion_workspace` 내부의 하위 디렉토리를 탐색하여 대상 테이블, config 정보, raws 대기 파일 수, 커스텀 스크립트 존재 여부를 반환
- `GET /admin/chain/rules`: `chain_rules.json`의 규칙 정보를 로드하여 리턴
- `GET /admin/mappers/list`: `mappers/` 하위 모듈들을 조회하여 안전한 **AST 구문 분석**을 통해 함수 및 매핑 정보 요약을 리턴

### 2.2 Frontend UI 확장 (`client2/admin.html`, `client2/src/admin.js`)
- 어드민 페이지에 `Workspaces`, `Chain Rules`, `Mappers` 신규 탭 3개 추가
- 마스터-디테일 패턴 연동: 목록 행 클릭 시 우측 영역의 타이틀/라벨을 동적으로 수정하고 해당 설정 정보(JSON) 또는 맵퍼 함수 정의 목록을 Fira Code 기반 JSON 뷰어로 예쁘게 출력
- 페이징 컨트롤 제어: 정적 목록 조회 탭으로 전환 시 하단 페이지네이션 푸터 영역 자동 숨김 처리

### 2.3 빌드 및 안정성 검증
- `npm run build`를 구동하여 최신 UI 컴포넌트 배포 완료
- `pytest` 통합 테스트를 가동해 API 정합성 검증 완료 (13 passed)
