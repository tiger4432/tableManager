# 📅 AssyManager Ingestion Auto Update & Scheduler 가이드

> **Status:** 🟢 Living | **Last-verified:** 2026-07-24 | **Owner:** Ingester | **Source-of-truth:** `server/run_auto_update.py` · 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

본 디렉토리는 각 테이블별 실시간 인제션 파일 수집 및 백업 스케줄링을 독립적이고 완벽하게 관리할 수 있는 **하이브리드 동적 다중 감지 수집 시스템**입니다.

---

## 🚀 1. 디렉토리 설계 구조
각 테이블 하위에 `auto_update` 폴더를 생성하고, 파일 수집용 파이썬 스크립트(`*.py`)들을 배치하면 중앙 스케줄러(`server/run_auto_update.py`)가 이를 자동 감지(Auto-Discovery)하여 통합 기동합니다.

```
server/ingestion_workspace/
├── {table_name}/
│   ├── raws/                 # 최종 수집 파일이 안착할 폴더 (Watcher 감시 대상)
│   └── auto_update/          # 수집 자동화 스크립트 보관 폴더
│       ├── collect_sensor_a.py  # 기기 A 전용 수집기
│       └── fetch_web_data.py    # 외부 웹 API 전용 수집기
```

---

## 🔑 2. 주석 기반 제로설정 크론탭 스케줄링 (Comment-Driven Crontab)
별도의 설정 파일(`.json`)을 따로 구성할 필요 없이, 파이썬 파일(`.py`)의 **최상단 20줄 이내**에 주석으로 스케줄과 파일명 설정을 기재하면 작동합니다.

### 📝 설정 키워드 규격
* `# schedule: <cron_expression>`: 표준 크론탭 표현식으로 수집 실행 주기를 설정합니다.
  - 예: `# schedule: 0 * * * *` (매시 정각 실행)
  - 예: `# schedule: */5 * * * *` (5분마다 실행)
* `# filename_prefix: <prefix>`: `raws/` 폴더에 생성될 최종 CSV 파일의 접두사를 지정합니다.
  - 예: `# filename_prefix: sensor_a_data` -> 최종 생성 파일: `sensor_a_data_YYYYMMDD_HHMMSS.csv`

> [!NOTE]
> 만약 `# schedule:` 설정 주석이 생략되거나 누락된 스크립트의 경우, 기본 주기(매시 정각 `"0 * * * *"`)와 기본 접두사(스크립트 파일명)로 안전하게 자동 폴백(Fallback) 지정됩니다.

---

## 💾 3. 네임스페이스 `out` 변수 가로채기 (Variable Capture)
수집 스크립트 내부에서 복잡하게 파일 쓰기(I/O)를 하거나 표준 출력(`print`)으로 인한 로그 오염을 겪을 필요가 없습니다. 스크립트 마지막 시점에 **`out` 이라는 이름의 전역/로컬 변수에 데이터를 대입**해 두기만 하면 스케줄러가 메모리에서 이를 자동으로 덤프 및 CSV 변환하여 적재합니다.

### 💡 지원 가능한 `out` 변수 데이터 타입
1. **문자열 (`str`)**: CSV로 변환할 문자열 데이터를 담아둡니다.
   ```python
   out = "pkg_id,base,x,y,leg\nCHIP_1,CHIP,10,20,LEFT"
   ```
2. **딕셔너리 리스트 (`list[dict]`)**: Key-Value가 매핑된 딕셔너리의 리스트입니다. **Key 리스트를 CSV 헤더로 자동 추출 및 매핑**하여 적재합니다. (권장)
   ```python
   out = [
       {"pkg_id": "CHIP_1", "base": "CHIP", "x": 10, "y": 20, "leg": "LEFT"},
       {"pkg_id": "CHIP_2", "base": "CHIP", "x": 30, "y": 40, "leg": "RIGHT"}
   ]
   ```
3. **2차원 리스트 (`list[list]`)**: 순수 행 리스트 구조입니다. 첫 행을 헤더로 기입하여 덤프합니다.
   ```python
   out = [
       ["pkg_id", "base", "x", "y", "leg"],
       ["CHIP_1", "CHIP", 10, 20, "LEFT"]
   ]
   ```
4. **Pandas DataFrame**: `to_csv` 메서드가 내장되어 있는 판다스 데이터프레임 등의 객체입니다. `to_csv(index=False)`를 자동 호출해 덤프합니다.
   ```python
   import pandas as pd
   out = pd.DataFrame(data_list)
   ```

### 🛡️ 완충 폴백 (Stdout Capture Fallback)
스크립트 내부에 `out` 변수가 선언되어 있지 않다면, 자동으로 **자식 프로세스 표준 출력(stdout, print) 캡처 모드**로 전환하여 `print(...)`로 출력한 텍스트 전체를 낚아채 CSV로 저장해 줍니다.

---

## ⚡ 4. 실시간 무설정 핫 리로드 (Zero-Interaction Hot-Reload)
* **즉시 코드 반영**: 스케줄러가 매 크론 실행 타이밍마다 디스크에서 최신 소스 코드를 새로 읽어 실행(`exec`)하므로, **파일을 수정하고 저장하면 어드민 버튼을 누르거나 재기동할 필요 없이 다음 실행 때 즉각 반영**됩니다.
* **즉시 스케줄 반영**: 메인 데몬 루프가 파일의 수정 시각(`mtime`)을 실시간 폴링 감시합니다. 파일 상단의 `# schedule: ` 크론 설정을 수정하는 즉시 스케줄러가 이를 감지하여 다음 실행 타이밍을 동적으로 갱신하고 로깅합니다.
