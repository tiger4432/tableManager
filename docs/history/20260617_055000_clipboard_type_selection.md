# Clipboard Data Type Selection Modal for Smart Paste

## 1. 개요 (Overview)
- **목적**: "스마트 붙여넣기(Smart Paste)" 기능 실행 시, 사용자가 클립보드 내에 들어있는 다양한 데이터 타입(HTML 표 서식, Rich Text, plain text 등)을 감지하고, 원하는 포맷을 명시적으로 선택해 파일 인제션 파이프라인으로 업로드 및 파싱할 수 있도록 개선
- **작성일**: 2026년 06월 17일

## 2. 변경 내용 (Changes)
### 2.1 Frontend 클립보드 다중 타입 감지 및 글래스모피즘 모달 연동 (`client2/src/main.js`)
- **Clipboard API `read()` 비동기 연동**:
  - `navigator.clipboard.read()`를 사용하여 클립보드 내의 다중 Mime-Type 목록을 실시간으로 가져옴
  - `text/` 접두사가 붙거나 `json`, `csv`를 포함하는 텍스트 기반 포맷들을 필터링하여 감지
- **Fallback 안전장치(호환성) 설계**:
  - 모바일이나 구형 브라우저, 권한 거부 등으로 `read()` 호출 시 에러가 나거나 단일 plain-text만 있을 경우에는 `navigator.clipboard.readText()`를 활용한 `text/plain` 폴백 파이프라인 기동
- **프리미엄 Glassmorphism 선택 모달 UI (`showClipboardTypeModal`)**:
  - 복수의 Mime-Type 감지 시 백드롭 블러(rgba overlay + blur 12px) 및 어두운 글래스모피즘 테마의 스타일리시한 모달 노출
  - 감지된 각 Mime-Type에 친숙한 라벨(예: HTML Table, Rich Text Format, CSV 등), 전용 이모지 아이콘, 조화로운 HSL 컬러 하이라이트를 결합하여 카드형 버튼으로 매핑
  - 마우스 호버 시의 미세한 리프트 업 및 테두리 Glow 트랜지션 애니메이션 제공
- **Mime-Type 파일 확장자 바인딩 및 업로드**:
  - 사용자가 모달에서 특정 포맷을 선택하면, 해당 `Blob` 객체를 추출하여 적절한 확장자(`.html`, `.rtf`, `.json`, `.csv`, `.txt`)의 가상 파일 객체(`File`)로 변환
  - 서버 측 파일 업로드 인제션 엔드포인트(`POST /tables/:tableName/upload`)로 전송하여, 해당 확장자에 맞는 파서 플러그인이 자동으로 동작하도록 조율

### 2.2 빌드 및 검증 완료
- Vite 빌드(`npm run build`) 수행을 통해 최신 `main.js` 및 정적 자산 컴파일 오류가 없음을 확인
- 백엔드 13개 통합/단위 API 테스트(`pytest`) 무결성 통과 완료 (13 passed)
