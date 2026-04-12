# 🚀 AssyManager 콘다 환경 세팅 가이드

이 문서는 `environment.yml` 파일을 사용하여 `assyManager` 개발 환경을 구축하고 서버 및 클라이언트를 실행하는 방법을 안내합니다.

## 1. 전제 조건 (Prerequisites)

- [Miniconda](https://docs.anaconda.com/miniconda/) 또는 [Anaconda](https://www.anaconda.com/download)가 설치되어 있어야 합니다.
- 터미널(PowerShell, CMD, 또는 Git Bash)에서 `conda` 명령어가 작동해야 합니다.

## 2. 환경 생성 (Environment Creation)

프로젝트 루트 디렉토리(`assyManager/`)에서 다음 명령어를 실행하여 가상 환경을 생성합니다.

```bash
# environment.yml을 사용하여 'assy_manager' 환경 생성
conda env create -f environment.yml

# 생성된 환경 활성화
conda activate assy_manager
```

## 3. 의존성 확인 (Verify Dependencies)

이 프로젝트는 다음과 같은 핵심 패키지를 사용합니다:
- **FastAPI / Uvicorn**: 백엔드 API 서버
- **PySide6**: 데스크탑 GUI 클라이언트
- **SQLAlchemy**: 데이터베이스 ORM
- **Watchdog**: 실시간 파일 모니터링 (자동 인제션 전용)
- **Websockets**: 실시간 데이터 동기화

## 4. 시스템 실행 순서 (Execution Guide)

환경이 활성화된 상태에서 다음 순서대로 실행하십시오.

### Step 1: 서버 실행 (Start Server)
```bash
cd server
uvicorn main:app --reload
```
> 서버가 정상 구동되면 `http://127.0.0.1:8000`에서 API 문서를 확인할 수 있습니다.

### Step 2: 자동 인제션 워처 실행 (Optional)
새로운 로그 파일을 실시간으로 감지하려면 다른 터미널에서 실행하십시오.
```bash
cd server
python .\parsers\directory_watcher.py
```

### Step 3: 클라이언트 실행 (Start Client)
```bash
cd client
python main.py
```

## 💡 팁
- **DB 초기화**: `server/assy_manager.db` 파일을 삭제하고 서버를 재시작하면 데이터베이스가 초기화됩니다.
- **환경 업데이트**: 만약 `environment.yml`이 수정되었다면 아래 명령어로 기존 환경을 업데이트할 수 있습니다.
  ```bash
  conda env update -f environment.yml --prune
  ```
