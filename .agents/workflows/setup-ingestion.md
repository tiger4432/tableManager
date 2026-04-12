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
```

### 2단계: 파이싱 설정 파일 작성
`config/config.json` 파일을 작성하여 헤더 규칙과 테이블 파싱 규칙을 정의합니다.

- **`header_rules`**: 파일 상단에서 추출할 공통 정보 (파일명, 설비ID 등)
- **`rules`**: 테이블 본문의 각 행을 파싱할 규칙
- **`business_key_column`**: 중복 방지를 위한 식별 컬럼

> [!TIP]
> 기존 `inventory_master/config/config.json`을 복사하여 수정하는 것을 추천합니다.

### 3단계: 자동화 서비스 시작 (Directory Watcher)
준비가 완료되면 서버에서 감시 서비스를 실행합니다.

```powershell
cd server
python parsers/directory_watcher.py
```

### 4단계: 실시간 데이터 유입 테스트
파일을 `raws/` 폴더에 복사해 넣습니다.
- 파일이 사라지고 `archives/` 폴더로 이동되는지 확인합니다.
- 클라이언트 UI 탭에 데이터가 실시간으로 나타나는지 확인합니다.
