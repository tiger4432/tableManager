# 20260413_074500_resolve_pyside6_dll_error

## 1. 문제 현상 (Phenomenon)
PyInstaller로 빌드된 `AssyManagerClient.exe` 실행 시 `ImportError: DLL load failed while importing QtWidgets: 지정된 프로시저를 찾을 수 없습니다.` 오류가 발생하며 프로그램이 구동되지 않음.

## 2. 기술적 원인 분석 (Root Cause)
- **DLL 검색 우선순위 문제**: Windows 환경에서 빌드된 실행 파일이 자신의 번들 내에 포함된 `Qt6Gui.dll`, `Qt6Core.dll` 보다 시스템 `PATH`에 등록된 아나콘다(`Anaconda`)나 다른 환경의 Qt DLL을 먼저 발견하여 로드하려 시도함.
- **심볼 미일치**: 아나콘다의 Qt 라이브러리와 번들된 PySide6 바이너리 간의 심볼 버전 불일치로 인해 "지정된 프로시저를 찾을 수 없음" 에러가 발생함.

## 3. 해결 방안 및 코드 변경 (Solution & Code Changes)
- **PATH 격리(Isolation)**: `main.py`의 시작 부분에 `sys.frozen` 여부를 체크하여, 빌드된 환경일 경우 `os.environ["PATH"]`를 번들 폴더(`sys._MEIPASS`)와 최소한의 시스템 경로(`System32`)로만 채우도록 강제 설정함.
- **동적 DLL 경로 추가**: `os.add_dll_directory`를 사용하여 번들 내부의 `PySide6` 라이브러리 위치를 명시적으로 등록함.

## 4. 검증 결과 (Validation)
- `assy_manager` 콘다 환경에서 `--clean -y` 옵션으로 재빌드 수행.
- 외부 환경 변수의 영향을 받지 않는 독립적인 바이너리 실행 구조 확보.
- (사용자 확인 필요) 로컬 테스트 시 동일 구조에서 DLL 에러 해결 확인.
