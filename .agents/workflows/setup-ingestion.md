---
description: 새로운 테이블에 대한 실시간 인제션 워크스페이스 구축 가이드
---

## 🚀 새로운 인제션 워크스페이스 구축하기

이 워크플로우는 새로운 데이터 소스(로그 파일 등)를 감시하여 `assyManager` 서버로 자동 업서트하는 환경을 구성하는 단계를 설명합니다.

### 1단계: 워크스페이스 구조 생성
`server/ingestion_workspace/` 하위에 새로운 테이블 이름으로 폴더를 생성합니다.

```powershell
# 예: new_sensor_data 테이블용
mkdir -p server/ingestion_workspace/new_sensor_data/raws
mkdir -p server/ingestion_workspace/new_sensor_data/config
mkdir -p server/ingestion_workspace/new_sensor_data/scripts
mkdir -p server/ingestion_workspace/new_sensor_data/archives
mkdir -p server/ingestion_workspace/new_sensor_data/auto_update
```

### 2단계: 파이싱 설정 파일 작성
`config/config.json` 파일을 작성하여 헤더 규칙과 테이블 파싱 규칙을 정의합니다.

- **`header_rules`**: 파일 상단에서 추출할 공통 정보 (파일명, 설비ID 등)
- **`rules`**: 테이블 본문의 각 행을 파싱할 규칙
- **`business_key_column`**: 중복 방지를 위한 식별 컬럼

> [!TIP]
> 기존 `inventory_master/config/config.json`을 복사하여 수정하는 것을 추천합니다.

### 3단계: 파일 자동 수집 스크립트 작성 (선택 / Auto-Update)
외부 연동망이나 웹 API로부터 파일을 주기적으로 자동 수집하고 싶다면, `auto_update/` 폴더 하위에 파이썬 스크립트(예: `fetch_sensor.py`)를 생성합니다.

* **크론 주석 설정**: 파일 상단에 스케줄 주석을 명시합니다.
  ```python
  # schedule: 0 * * * *
  # filename_prefix: sensor_data
  ```
* **결과 변수 대입**: 수집 결과를 `out` 변수에 바인딩해 두면 스케줄러가 메모리 상에서 낚아채 정규 CSV로 자동 변환 덤프합니다. (딕셔너리 리스트 혹은 Pandas DataFrame 호환)
  ```python
  out = [
      {"pkg_id": "CHIP_1", "base": "CHIP", "x": 10, "y": 20, "leg": "LEFT"}
  ]
  ```

> [!NOTE]
> 이 수집 스크립트는 **디스크 직접 읽기 방식** 및 **mtime 감지**가 걸려 있어, 파일을 에디터로 고치고 저장하자마자 어드민 버튼 없이도 스케줄과 코드가 실시간 갱신되어 다음 실행에 적용됩니다.

### 4단계: 데몬 서비스 통합 기동 (Decoupled Mode)
준비가 완료되면 프로젝트 루트에서 런처를 실행합니다. 왓처와 자동 수집 스케줄러 등 5대 데몬이 일괄 기동됩니다.

```powershell
# 프로젝트 루트 디렉토리에서 bat 실행
./run_app.bat
```

### 5단계: 실시간 데이터 유입 및 이관 테스트
수집 스크립트가 크론 주기에 맞게 기동하여 `raws/` 폴더에 CSV 파일을 꽂아주는지 관측합니다. (또는 수동으로 `raws/` 에 파일을 복사해 넣습니다.)
- 파일이 자동으로 파싱 적재된 후 사라지고 `archives/` 폴더로 이동되는지 확인합니다.
- 클라이언트 UI 탭에 데이터가 실시간으로 노출 및 리프레시되는지 최종 확인합니다.
