# Agent C (QA & Debugging) 작업 보고서

**작성자**: Agent C
**대상**: PM 에이전트 (Agent A) 및 향후 개발 에이전트
**보고 내용**: `assyManager` 데스크톱 클라이언트 및 서버 통합 버그 디버깅 완료 보고

---

## 1. 긴급 블로커 (DLL 충돌) 해결 결과
- **이슈**: `venv` 파이썬이 Windows Anaconda 환경에 귀속되면서, 패키징된 `PySide6`와 OS단 라이브러리 간의 동적 링킹(DLL)이 깨져 클라이언트가 켜지지 못하던 문제를 확인했습니다.
- **조치 내역**: 윈도우 환경 구조적 한계이므로 프로젝트 소스코드단 수정이 아닌 **순수 Conda 환경(`assy_manager`)으로 마이그레이션**하여 `conda-forge::pyside6` 생태계로 일치시켰습니다.
- **PM 전달 사항**: 향후 데스크톱 앱(main.py)이나 기타 클라이언트 테스트 코드를 실행할 때는 기존 `venv` 대신 반드시 **`conda activate assy_manager`** 상태에서 구동하도록 다른 요원들에게 인계 부탁드립니다. (해당 설정을 담은 `environment.yml`을 프로젝트 Root에 추가해두었습니다.)

## 2. 클라이언트 멈춤(Freeze) 현상 최적화
- **이슈**: 클라이언트가 REST API 서버(FastAPI)에서 동기 모드로 수백 개 행의 JSON 데이터를 로드(`fetchMore`)할 때 화면이 응답 없음에 빠지던 디자인 결함.
- **조치 내역**: UI 메인 스레드에 묶여있던 통신 프로세스를 `QRunnable` 및 `QThreadPool`로 감싼 `ApiFetchWorker` 비동기 객체로 분리하여 앱 멈춤 현상을 완전히 해결했습니다. 사용자(UX)가 쾌적하게 스크롤할 수 있도록 안정성을 확보했습니다.

## 3. Pytest 기반 로컬 서버 통합 테스트 구축 
- **이슈**: 초기 테스트 DB 세션과 `FastAPI TestClient` 간의 연결 생명주기가 엇갈려 빈 테이블을 조회(`no such table: data_rows`) 하는 고질적 아키텍처 버그가 존재했습니다.
- **조치 내역**: `server/tests/conftest.py`에 `SQLAlchemy StaticPool`을 활성화하여 테스트용 인메모리 의존성을 완벽히 단일화했습니다. 
- **자동화 요약**: `GET /tables/.../data` 통신 규격 체크 방어 코드와 `PUT /batch` 일괄 업데이트 비즈니스 로직(예: `is_overwrite = True` 토글링) 테스트 환경이 마련되었으며 현재 모든 검증 스크립트가 100% PASS 됩니다.

## 4. 건의 사항
- 테이블 데이터 변경 시 WebSocket(`ws://.../ws`)을 통해 각 클라이언트에게 신호가 뿌려지는 기초 구현체가 서버 쪽 `crud.py` 하단에 탑재되어 있습니다. 향후 해당 브로드캐스트를 받아 PySide6의 UI 셀 하이라이팅을 새로고침해주는 클라이언트단 연결 작업을 PM의 차기 스프린트에 편성하는 것을 제안합니다.
