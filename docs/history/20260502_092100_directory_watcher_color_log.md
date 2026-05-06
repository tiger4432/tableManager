# DirectoryWatcher Console Log Colorization

## 변경 개요 (Overview)
`server/parsers/directory_watcher.py` 파일의 로그 출력 방식을 개선하여, 터미널 콘솔에서 로그 레벨(DEBUG, INFO, WARNING, ERROR, CRITICAL)에 따라 색상이 구분되어 출력되도록 `ColorFormatter`를 도입하였습니다. 파일 로깅은 기존과 동일하게 색상 코드 없이 평문으로 저장됩니다.

## 주요 변경 사항 (Key Changes)
- **`ColorFormatter` 클래스 추가**: ANSI 이스케이프 코드를 사용하여 로그 레벨에 따른 색상(Blue, Green, Yellow, Red 등)을 부여하는 커스텀 포매터 구현.
- **핸들러 분리**: `StreamHandler`(콘솔용)와 `FileHandler`(파일용)에 각각 다른 포매터를 적용하도록 로깅 초기화 로직 분리.

## 코드 스니펫 (Code Snippets)

### 변경 후 (After)
```python
class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: '\033[94m', # Blue
        logging.INFO: '\033[92m', # Green
        logging.WARNING: '\033[93m', # Yellow
        logging.ERROR: '\033[91m', # Red
        logging.CRITICAL: '\033[1;91m', # Bold Red
    }
    RESET = '\033[0m'

    def format(self, record):
        log_fmt = f"{self.COLORS.get(record.levelno, self.RESET)}%(asctime)s - %(name)s - %(levelname)s - %(message)s{self.RESET}"
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

console_handler = logging.StreamHandler()
console_handler.setFormatter(ColorFormatter())

file_handler = logging.FileHandler(log_path, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler]
)
```

## 아키텍처 및 시스템 영향 (Architecture & System Impact)
- **시각적 반응성 향상**: 터미널 환경에서 백그라운드로 실행되는 인제스터의 에러나 경고를 직관적으로 파악할 수 있게 됨으로써, 개발자 및 운영자의 디버깅 속도를 향상시킵니다.
- **파일 무결성**: 파일 스트림 핸들러(`FileHandler`)에는 일반 텍스트 포매터가 유지되므로, ANSI 색상 코드가 `.log` 파일 내에 오염되는 문제를 원천 방지하였습니다.
