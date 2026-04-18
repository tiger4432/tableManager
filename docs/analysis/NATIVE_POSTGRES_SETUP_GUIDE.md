# 🐘 Native PostgreSQL Setup Guide (Windows & Linux)

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

PostgreSQL 설치가 완료되면, 서버 코드(`server/database/database.py` 등)의 연결 문자열을 아래와 같이 수정하면 즉시 연동됩니다.

```python
# SQLite (기존)
SQLALCHEMY_DATABASE_URL = "sqlite:///./assy_manager.db"

# PostgreSQL (변경)
# 형식: postgresql://[사용자]:[비밀번호]@[호스트]:[포트]/[DB명]
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:your_password@localhost:5432/assy_manager"
```

---

## 🚀 왜 PostgreSQL인가요? (핵심 요점)
- **행 단위 잠금(Row-level Lock)**: SQLite는 한 명이 저장하는 동안 다른 모든 사람이 대기해야 하지만(파일 잠금), Postgres는 수천 명이 동시에 수정해도 충돌이 없습니다.
- **JSONB 성능**: Postgres 전용 JSONB 형식을 사용하면, 1,000만 건 데이터 속에서도 특정 셀의 내용을 1초 미만으로 검색할 수 있는 강력한 인덱싱을 지원합니다.
- **안정성**: 갑작스러운 전원 차단이나 시스템 오류 시에도 데이터 복구 능력이 월등히 뛰어납니다.

---
*AssyManager Scalability Engineering | 2026.04.18*
