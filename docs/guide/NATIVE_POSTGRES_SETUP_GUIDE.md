# 🐘 Native PostgreSQL Setup Guide (Windows & Linux)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-06 | **Owner:** Ops
> **판정 2026-08-06 — 아카이브하지 않고 §연동만 다시 씁니다.** 설치 절차(Windows MSI · Ubuntu apt · DB 생성)는 **현행이고 낡지 않는 계급**이며 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)·[CONDA_SETUP_GUIDE](./CONDA_SETUP_GUIDE.md)·[CONFIG_GUIDE](./CONFIG_GUIDE.md)·[SERVER_STARTUP_GUIDE](./SERVER_STARTUP_GUIDE.md)·[docs/README](../README.md)가 여기로 보냅니다. 🔴 **거짓이던 것은 연동 절차 하나**였습니다 — 아래 참조.
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 운영은 [POSTGRES_OPERATIONS_GUIDE](./POSTGRES_OPERATIONS_GUIDE.md)

본 문서는 **도커(Docker)를 사용할 수 없는 환경**에서 윈도우와 리눅스 서버에 PostgreSQL을 직접 설치하고, AssyManager와 연동하기 위한 최단 경로 가이드를 제공합니다.

---

## 💰 라이선스 및 비용
- **PostgreSQL은 완전 무료(Open Source)**입니다.
- 기업 내 상업적 용도로 사용하더라도 추가 라이선스 비용이 발생하지 않습니다.

---

## 🪟 Windows 설치 (GUI 방식)

1. **인스톨러 다운로드**: 
   - [EnterpriseDB 공식 다운로드 페이지](https://www.postgresql.org/download/windows/)에서 최신 버전(v16+) MSI 인스톨러를 다운로드합니다.
2. **설치 프로세스**:
   - `Next`를 눌러 진행하시되, **Password** 설정 단계에서 사용할 비밀번호(예: `admin123`)를 반드시 메모해 두십시오.
   - 포트는 기본값인 `5432`를 유지합니다.
3. **데이터베이스 생성**:
   - 설치 완료 후 시작 메뉴에서 **pgAdmin 4**를 실행합니다.
   - 좌측 서버 목록에서 `Databases` 우클릭 -> `Create` -> `Database...` 선택.
   - 이름을 `assy_manager`로 입력하고 저장합니다.

---

## 🐧 Linux 설치 (Ubuntu/Debian 기준)

1. **패키지 설치**:
   ```bash
   sudo apt update
   sudo apt install postgresql postgresql-contrib
   ```
2. **서비스 시작**:
   ```bash
   sudo systemctl start postgresql
   sudo systemctl enable postgresql
   ```
3. **사용자 비밀번호 및 DB 설정**:
   ```bash
   # postgres 계정으로 psql 접속
   sudo -u postgres psql

   # 비밀번호 설정 (SQL문 실행)
   ALTER USER postgres PASSWORD 'your_password';

   # 데이터베이스 생성 (SQL문 실행)
   CREATE DATABASE assy_manager;

   # 종료
   \q
   ```

---

## 🔗 AssyManager 연동 설정

🔴 **[2026-08-06 정정] 종전 이 절은 「서버 코드(`server/database/database.py`)의 연결 문자열을 수정하면 된다」고 했고, SQLite를 「기존」이라 불렀습니다. 둘 다 거짓입니다** — **코드를 고치지 마십시오.** 접속은 **선언**으로 정해지고 우선순위가 있습니다:

| 순위 | 원천 | 형태 |
|---|---|---|
| 1 | 환경변수 `DATABASE_URL` | `postgresql://postgres:<비밀번호>@localhost:5432/assy_manager` |
| 2 | `<config>/database.json` | `{"host":..., "port":..., "dbname":..., "user":..., "password":...}` — **사람이 편집하는 자리** |
| 3 | 코드 기본값 | 위와 같은 형태의 로컬 기본값 |

- 🔴 **`database.json`은 핫리로드되지 않습니다 — 커넥션 문자열이라 재기동이 필요합니다**([CONFIG_GUIDE §4.1](./CONFIG_GUIDE.md)).
- ⚠️ **SQLite는 「기존」이 아닙니다.** 이 프로젝트의 저장소는 PostgreSQL이고, SQLite는 테스트 스위트 일부에서만 씁니다. 🔴 **그 둘을 같은 것으로 읽으면 위험합니다** — SQLite는 PostgreSQL이 거절하는 리터럴을 받아 주므로, 스위트는 초록인데 운영만 터지는 실패가 이 저장소에서 이미 여러 번 났습니다.
- 어느 원천이 실제로 답했는지는 `server/scripts/diagnose_db_health.py`가 출력합니다([spec/DEBUGGING_GUIDE §0](../spec/DEBUGGING_GUIDE.md)).

---

## 🚀 왜 PostgreSQL인가요? (핵심 요점)
- **행 단위 잠금(Row-level Lock)**: SQLite는 한 명이 저장하는 동안 다른 모든 사람이 대기해야 하지만(파일 잠금), Postgres는 수천 명이 동시에 수정해도 충돌이 없습니다.
- **JSONB 성능**: Postgres 전용 JSONB 형식을 사용하면, 1,000만 건 데이터 속에서도 특정 셀의 내용을 1초 미만으로 검색할 수 있는 강력한 인덱싱을 지원합니다.
- **안정성**: 갑작스러운 전원 차단이나 시스템 오류 시에도 데이터 복구 능력이 월등히 뛰어납니다.

---
> ⚠️ **[2026-08-06] 꼬리에 있던 두 번째 자기 날짜(`2026.04.18`)를 없앴습니다.** 한 문서가 헤더와 꼬리에 서로 다른 날짜를 주장하면 독자는 어느 쪽도 믿을 수 없습니다 — 날짜는 헤더의 `Last-verified` **하나**입니다(같은 결함이 `process/agentic_environment.md`에도 있었습니다).
