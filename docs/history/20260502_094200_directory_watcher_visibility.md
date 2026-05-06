# DirectoryWatcher Pipeline Logging Visibility Improvement

## 변경 개요 (Overview)
`DirectoryWatcher` 내부의 로깅 시, 어떤 테이블 워크스페이스에서 어떤 파이프라인(Parser)이 실행되었는지 터미널에서 즉각적으로 식별할 수 있도록 로그 포맷과 가시성을 개선했습니다.

## 주요 변경 사항 (Key Changes)
- **`IngestionHandler.table_name` 프로퍼티 추가**: 현재 워크스페이스의 테이블 이름을 안전하게 캐싱하여 반환하는 동적 프로퍼티 구현.
- **로깅 식별자 부착**: 모든 주요 로그의 앞부분에 `[{self.table_name}]` 태그를 부착하여 어떤 테이블 데이터가 처리 중인지 명확히 표시.
- **파이프라인 매칭 강조**: 매칭된 커스텀 파이프라인 클래스 이름에 굵은 청록색 ANSI 코드(`\033[1;36m`)를 적용하여 터미널 콘솔에서의 시인성을 극대화.

## 코드 스니펫 (Code Snippets)

### 변경 전 (Before)
```python
logger.info(f"Pipeline Matched: {obj.__name__} in {filename}")
```

### 변경 후 (After)
```python
logger.info(f"[{self.table_name}] 🚀 Pipeline Matched: \033[1;36m{obj.__name__}\033[0m in {filename}")
```

## 아키텍처 및 시스템 영향 (Architecture Impact)
- 데이터 파이프라인 디버깅 시 테이블별 필터링과 진행 상황 트래킹이 매우 용이해졌습니다.
- 파일 핸들러에는 ANSI 이스케이프가 제거된 평문이 저장되어 기존처럼 파일 무결성이 보호됩니다.
