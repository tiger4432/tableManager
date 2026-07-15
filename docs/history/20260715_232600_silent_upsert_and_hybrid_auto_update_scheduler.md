# 2026-07-15 23:26:00 - 비즈니스 키 중복 자동 병합(대안 B) 및 하이브리드 동적 다중 감지형 자동 수집 스케줄러 구축

## 1. 비즈니스 키 중복 충돌 해결 정책 적용 (대안 B: 자동 덮어쓰기)
- **배경**: 웹 UI 셀 수정 혹은 스마트 엑셀 붙여넣기 시, 변경 사항의 조합으로 생성되는 복합 비즈니스 키가 기존 DB의 다른 행과 겹치면 백엔드가 `ValueError` 예외를 발생시키며 전체 트랜잭션을 롤백시켰습니다.
- **해결 내역**:
  - **에러 우회 및 Silent Merge**: 중복 키 발생 시 예외를 던지지 않고, 해당 키를 가진 기존 행(`conflict_row`)을 가져와 사용자가 입력한 새로운 값들을 기존 행에 자동 덮어쓰는(Upsert/Merge) 방식으로 우회 구현했습니다.
  - **전체 스키마 컬럼 병합**: 사용자가 전달한 변경 사항뿐만 아니라, 임시 행이 이미 품고 있던 모든 유효한 일반 컬럼 값들을 누락 없이 충돌 행으로 이식(Copy/Merge)하는 방식을 적용했습니다.
  - **가비지 행 완전 소거 (DB Clean-up)**: 신규 추가된 임시 행에서 값을 치다가 중복이 일어난 경우, 중복되어 필요 없어진 임시 껍데기 행(`row`)을 DB 세션(`db.delete`) 및 메모리 캐시에서 흔적 없이 삭제하여 테이블 무결성을 유지했습니다.
  - **메모리 캐시/이력 주소지 마이그레이션**: 임시 행에 먼저 적재되었던 쓰기 대기 큐(cell_sources, cell_overwrites) 및 AuditLog의 `row_id` 대상을 기존 행(`conflict_row.row_id`)으로 완벽하게 주소 이전 처리하여 FK 제약 조건 위반을 방지했습니다.

---

## 2. 하이브리드 동적 다중 감지형 자동 수집 스케줄러 (`auto_update`) 구축
- **배경**: 인제션 파일 수집용 외부 연동 스크립트들을 테이블별로 안전하게 응집 관리하면서도 백엔드에서는 단일 프로세스로 가볍게 가동할 수 있는 표준화된 자동화 스레드 파이프라인이 필요했습니다.
- **해결 내역**:
  - **분산 테이블 지향형 auto_update 신설**: 각 테이블 인제션 워크스페이스 하위에 `auto_update` 폴더를 신설하고, N개의 서로 다른 장비/원천 소스를 위한 수집 스크립트(`collect_*.py`)들을 독립 배치하여 응집성(Cohesion)을 극대화했습니다.
  - **표준 BaseCollector 구현**: 파일 수집 목적지(`../raws/`) 경로 자동 계산 기능과 복사 도중 불완전 파싱을 막는 **원자적 복사(Atomic Copy & Rename: `.tmp` 임시 저장 후 변경)** 로직을 내장한 추상 클래스를 수립했습니다.
  - **자동 감지형 중앙 스케줄러 개발 (`server/run_auto_update.py`)**: 전체 워크스페이스를 동적 스캔하여 `collect_*.py` 내부의 수집 클래스들을 리플렉션으로 자동 스캔/인스턴스화하고 10초마다 가동해 주는 단일 데몬을 개발했습니다.
  - **데몬 프로세스 통합 (`run_decoupled_app.py`)**: 중앙 런처 프로세스에 `Auto Update Scheduler`를 5번째 서비스 프로세스로 연동 기동하여, 부모 프로세스의 라이프사이클에 맞게 일괄 기동 및 우아한 종료(Terminate/Shutdown)를 수행하도록 연동을 마무리했습니다.
  - **가상 파일 수집 테스트**:
     - `bonding_map` 테이블 하위에 설비 A, B 목업 컬렉터(`collect_machine_a.py`, `collect_machine_b.py`)를 탑재하고, `inventory_master` 테이블 하위에 재고 컬렉터(`collect_inventory.py`)를 탑재했습니다.
     - 가상의 로컬 외부 연동망(`auto_update_source/`)을 기동하여 파일을 던져 넣었을 때 10초 이내에 정상 수집 감지 및 이관 전송이 안전하게 수행됨을 로깅을 통해 검증했습니다.
  - **주석 기반 제로설정 크론탭 스케줄러 (Comment-Driven Crontab)**:
     - 수집 파이썬 파일 상단에 `# schedule: * * * * *` 및 `# filename_prefix: web_bonding_data` 와 같이 주석을 한 줄 적어두기만 하면, 스케줄러가 구동 시점에 파일 상단을 분석하여 정밀 크론 연동 스케줄로 자동 로드하고 계산합니다. (의존 패키지 `croniter` 부재 시 백그라운드에서 자동 pip 설치 연동 탑재)
  - **네임스페이스 `out` 변수 가로채기 (Variable Capture)**:
     - 스크립트 내부에서 표준 출력(`print`)을 더럽히지 않고, 데이터를 담은 문자열, 2차원 리스트, 딕셔너리 리스트(키-값 매핑), Pandas DataFrame 등의 객체를 `out` 이라는 변수명으로 대입해 두면 스케줄러가 실행 컨텍스트 메모리 상에서 이를 안전하게 가로챕니다.
     - 가로챈 변수 타입에 맞춰 적절한 쉼표 구분자 CSV 파일 포맷으로 자동 변환 빌드하여 `raws/` 폴더에 안착시킵니다. (변수 `out`이 누락된 스크립트일 경우, 예외 없이 subprocess 표준 출력 캡처 모드로 자동 폴백 우회 보장)
  - **무중단 핫 리로드 (SYSTEM_RELOAD Hot-Swap) 통합**:
     - 어드민 대시보드 페이지의 `[Reload]` 혹은 `[재연동]` 버튼 클릭 시 발행되는 `SYSTEM_RELOAD` 아웃박스 이벤트를 감시하도록 `run_auto_update.py` 에 DB 폴링 감시 블록을 연동했습니다.
     - 이벤트 수신 즉시 기존 스케줄러를 재시작하지 않고 **메모리 내 파이썬 모듈 캐시(`sys.modules`)를 안전하게 초기화(Evict)한 뒤 디렉토리를 재스캔**하여 신규 스크립트 수집기 라인업을 무중단(Hot-Swap)으로 즉시 현장에 투입합니다.
  - **디스크 직접 읽기 실행 & 파일 수정 실시간 자동 반영 (Zero-Interaction Hot-Reload)**:
     - 스케줄러가 매 실행 시간마다 디스크에서 최신 파이썬 소스 파일을 새로 읽어 들여 `exec()` 방식으로 실행하게 개선하여, 파이썬 모듈 캐시(`sys.modules`)의 영향을 전혀 받지 않고 파일 저장 즉시 변경 코드가 실시간 반영됩니다.
     - 또한, 매 클록 루프 시점마다 파일 수정 시각(`mtime`)을 감지하여 스크립트 상단의 크론 주석(`# schedule: ...`) 설정이 고쳐진 즉시 스케줄링 주기가 실시간 자동 리로드 및 갱신되도록 수립했습니다. (어드민 버튼을 누르지 않아도 파일 수정 즉시 100% 자동 반영)
  - **Pandas DataFrame 참/거짓 모호성 버그(Truth Value Ambiguity) 해결**:
     - `exec()` 구동 후 `local_ns` 와 `global_ns` 딕셔너리에서 `out` 변수를 찾을 때 논리 연산자 `or`를 사용해 객체 자체의 논리 판별이 중첩 유발되어, 판다스 데이터프레임(`DataFrame`)에서 `ValueError: The truth value of a DataFrame is ambiguous` 에러가 터지고 캡처가 누락(폴백 처리)되던 결함을 해결했습니다.
     - 2대 네임스페이스 딕셔너리에서 `None` 여부를 직접 체크(`is None`)하여 DataFrame 객체를 에러 없이 온전하게 낚아채 정규 CSV로 안전 덤프하도록 로직을 철저히 튜닝 보강했습니다.
  - **셋업 워크플로우 가이드 개정**:
     - 인제션 테이블 신설 가이드인 [setup-ingestion.md](file:///c:/Users/kk980/Developments/assyManager/.agents/workflows/setup-ingestion.md) 워크플로우 파일에 `auto_update` 디렉토리 자동 생성 구조와 `# schedule` 크론 주석 작성법, `out` 변수 바인딩 사용법, 그리고 `run_app.bat` 데몬 통합 실행 방법을 전격 반영하여 기입을 업데이트했습니다.
  - **자동 워크스페이스 구축 스크립트 개정 (`setup_workspace.py`)**:
     - 새로운 테이블 인제션 환경을 일괄 생성해 주는 [setup_workspace.py](file:///c:/Users/kk980/Developments/assyManager/server/setup/setup_workspace.py) 의 하위 폴더 생성 명세(`subdirs`)에 `"auto_update"` 디렉토리명을 추가했습니다.
     - 이를 통해 앞으로 새로운 테이블 인입 설정 후 스크립트를 돌리면 `auto_update/` 폴더도 누락 없이 함께 자동 생성되도록 정렬했습니다.
  - **통합 로깅 컬러 시스템 (Unified Colored Logger System) 구축**:
     - 4대 데몬 서비스를 아우르는 통합 로깅 포맷 패키지 [logger.py](file:///c:/Users/kk980/Developments/assyManager/server/utils/logger.py)를 신설했습니다.
     - **프로세스별 시그니처 색상 매핑**: FastAPI Server(초록), Watcher(청록), Chain Worker(자주), Scheduler(노랑) 색상으로 콘솔 터미널 출력을 정렬하여 프로세스간 뒤섞임 현상을 완전 해소했습니다.
     - **에러 레벨 동적 컬러 가드**: 정상 정보(INFO, DEBUG)는 고유 색상을 따르되, 경고(WARNING)는 주황색, 에러(ERROR, CRITICAL) 상황 발생 시에는 모든 프로세스 색상을 무시하고 강렬한 빨간색(Bold Red)으로 덮어써 노출시켜 시인성을 고도화했습니다.
     - **이중 스트림 핸들러 분리**: 콘솔 스트림 출력에만 컬러 ANSI 제어 부호를 삽입하고, 파일 로깅 시에는 깨끗한 Plain Text 형태로 저장되도록 보강했습니다.
     - **전 영역 이식 리팩토링**: `main.py` (Uvicorn 내부 로거들까지 훅하여 이식), `run_watcher.py`, `chain_ingestion_worker.py`, `run_auto_update.py` 에 이 표준 로거를 전격 적용시켰습니다.
     - **중복 로깅 버그 해결 (Clean Root Handlers & Propagate Guard)**: 외부 타사 모듈의 `basicConfig` 오염으로 인해 콘솔에 동일 로그가 기본 포맷과 통합 포맷으로 이중 출력되던 문제를 해결하기 위해, 로거 이식 시점에 루트 로거의 핸들러들을 일괄 소거하고 `propagate = False` 로 제어하여 완벽하고 깨끗한 단일 로그 흐름으로 정정했습니다.
  - **서브 모듈 로깅 정렬 (Watcher Submodules Unification)**:
     - `parsers/directory_watcher.py` 내부의 독자적인 `ColorFormatter` 및 `basicConfig` 설정을 완전히 소거하여 루트 로거 오염의 근원을 차단하고, 로거명을 `Watcher.DirectoryWatcher` 로 통일하여 청록색 포맷이 자연스럽게 적용되도록 정렬했습니다.
     - `database/config_watcher.py` 내부의 밋밋하던 단순 `print`들을 모두 `logging.getLogger("Watcher.ConfigWatcher")` 로 바꾸어 청록색 컬러가 일관되게 입혀진 형태로 출력되도록 마감했습니다.
  - **로깅 주체 선두 배치 (Log Prefix Optimization)**:
     - 프로세스간 콘솔 출력의 직관적 구분을 위해 로깅 규격을 `[로깅 주체(이름)] [%(asctime)s] %(levelname)s - %(message)s` 형태로 변경하여, 로그 한 줄의 맨 처음부터 어떤 데몬이 출력한 로그인지 바로 파악할 수 있도록 편의성을 극대화했습니다.
  - **비영속성 엔티티 삭제 결함 해결 (Unpersisted db.delete Guard)**:
     - 충돌 해결(대안 B) 시 가비지가 된 임시 행(`row_to_delete`)을 DB 세션에서 날릴 때, 해당 객체가 아직 DB 세션에 등록(Pending)되거나 저장(Persistent)되지 않은 상태(Transient)일 경우 SQLAlchemy가 `Instance is not persisted` 예외를 내며 전체 인제션을 중단시키는 결함을 발견했습니다.
     - `sqlalchemy.orm.inspect`를 사용해 객체 상태가 `persistent` 또는 `pending` 상태일 때만 `db.delete()`를 시도하고 추가로 예외 처리 가드로 둘러싸는 안전장치를 `server/database/crud.py` 에 정교하게 장착했습니다.










