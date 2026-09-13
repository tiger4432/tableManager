# QA 에이전트(Agent C) 인수인계 및 프로젝트 요약서

이 문서는 'assyManager' 프로젝트의 버그 해결 및 자동화 테스트 구축을 전담할 **QA 에이전트(Agent C)**를 위한 프로젝트 아키텍처 요약 및 현재 직면한 블로커(Blocker) 이슈 설명서입니다.

---

## 1. 프로젝트 아키텍처 (어디를 테스트해야 하는가?)
- **서버(Backend)**: `FastAPI` 기반으로 동작하며, DB는 `SQLite` + `SQLAlchemy`를 사용합니다. 
  - `GET /tables/{table_name}/data`: 테이블 데이터를 Chunk 단위로 읽어오는 페이징 API
  - `PUT /tables/{table_name}/cells/batch`: 다중 셀의 값을 변경하고 DB(`is_overwrite = True`)를 갱신하는 일괄 처리 API
  - `ws://.../ws`: 데이터 업데이트 발생 시 연결된 모든 클라이언트에게 신호를 뿌리는 WebSocket
- **클라이언트(Desktop GUI)**: Python 3.12 가상환경 위에서 구동되는 `PySide6` (원래 PyQt6였으나 충돌로 마이그레이션됨) 기반 `QTableView` 에디터입니다.
  - `client/main.py`: 데스크톱 앱 뼈대
  - `client/models/table_model.py`: API 호출과 GUI 렌더링(노란색 하이라이팅 등)을 동기화하는 LazyLoad 테이블 모델 클래스

## 2. 🚨 긴급 처리 블로커 (Blocker Issue)
현재 마스터/PM 에이전트에 의해 기본 코드 구현이 끝났으나, 윈도우 로컬 환경에서 클라이언트를 켤 때 아래와 같은 치명적인 DLL 오류가 반복 발생하고 있습니다.

```text
Traceback (most recent call last):
  File "C:\Users\kk980\Developments\assyManager\client\main.py", line 2, in <module>
    from PySide6.QtWidgets import QApplication, ...
ImportError: DLL load failed while importing QtWidgets: 지정된 프로시저를 찾을 수 없습니다.
```
**[PM이 추측하는 원인 단서]**
1. 아나콘다(`base`)의 `conda deactivate` 처리를 했음에도 불구하고 윈도우의 환경 변수 `PATH` 어딘가에 구버전 Qt 바이너리가 여전히 우선적으로 잡혀 로드되고 있을 가능성.
2. 혹은 윈도우 로컬 PC에 **Microsoft Visual C++ 재배포 가능 패키지(VC++ Redistributable)** 최신 버전이 설치되어 있지 않아 `PySide6` 구동에 필요한 C++ 기본 DLL(`msvcp140.dll` 등)이 누락되었을 가능성.

## 3. QA 에이전트(Agent C) 수행 목표
1. **DLL 블로커 해결 가이드 제공**: 위 `ImportError` 원인을 정확히 특정할 수 있도록 파이썬 스크립트로 `os.environ["PATH"]` 체킹 로직을 돌리거나, VC++ 재배포 패키지 다운로드 스크립트를 준비하여 로컬 구동 문제를 최우선으로 해결하십시오.
2. **Pytest 자동화 테스트 구축**:
   - `server/` 디렉토리에 `tests/` 폴더를 만들고, FastAPI `TestClient`를 이용해 DB에 읽고 쓰기(`/batch` API) 동작이 의도대로(`is_overwrite=True` 반영) 돌아가는지 테스트 코드를 짜주십시오.
3. 데스크톱 앱 이벤트 모의 테스트(`pytest-qt` 활용) 가능 여부 조사 후 시나리오 확립.
