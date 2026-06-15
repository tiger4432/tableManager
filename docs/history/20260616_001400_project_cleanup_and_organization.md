# 2026-06-16 Project File Structure Cleanup & Organization

본 문서에서는 assyManager 프로젝트의 가독성 향상과 용량 최적화를 위한 파일 구조 정리 내역을 기록합니다.

## 1. 레거시 구성요소 제거 (Legacy Cleanups)
* **PyQt 레거시 클라이언트 삭제**: 신규 웹 기반 클라이언트(`client2`) 및 PySide6 데스크톱 래퍼(`client/desktop_wrapper.py`) 도입으로 미사용 상태가 된 `client/old/` 레거시 코드 폴더를 삭제했습니다.
* **루트 파일 정리**: 레거시 단일 프로세스 실행기(`run_app.py`), 임시 테스트 데이터 파일들(`#2 wwdf.csv`, `temp.json`, `test_migrate.db`, `inventory_master.csv`)을 삭제했습니다.
* **임시 CSV 추출물 제거**: `client/downloads/` 폴더 내에 수집되어 있던 총 약 100MB 규모의 임시 CSV 다운로드 파일(28개) 및 `client/` 폴더 내의 임시 CSV 파일들을 정리했습니다.
* **루트 scratch 폴더 제거**: 이전 에이전트들이 생성했던 11개의 단건 테스트용 스크립트(`scratch/` 폴더 전체)를 삭제 처리했습니다.

## 2. 파일 재배치 및 업데이트 (Relocation & Updates)
* **기동 셸 스크립트 수정**: `run_app.bat` 파일이 레거시 `run_app.py` 대신 멀티 프로세스 분리 기동 런처인 `run_decoupled_app.py`를 실행하도록 업데이트했습니다.
* **유틸리티 스크립트 이동**: 루트에 방치되어 있던 `generate_random_rows.py`를 `server/scratch/generate_random_rows.py`로 이동했습니다.
* **서버 가이드 문서 이동**: `server/스타팅 가이드.md` 파일을 `docs/starting_guide.md`로 이동 및 포맷팅 정리했습니다.

## 3. 서버 스크립트 아카이빙 (operational scripts vs one-off scripts)
* `server/scripts/archive/` 폴더를 신설하고 일회성 쿼리 분석, 튜닝용 스크립트 14개를 해당 디렉토리로 아카이브 격리했습니다.
* `server/scripts/` 루트에는 데이터베이스 인덱스 튜닝 및 정규화 마이그레이션 등 핵심 운영 스크립트 5개만 남겨 가독성을 향상시켰습니다.
