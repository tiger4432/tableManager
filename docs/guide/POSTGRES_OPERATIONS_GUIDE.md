# 🐘 PostgreSQL & pgAdmin4 운영 관리 가이드 (AssyManager)

본 문서는 AssyManager의 백엔드 데이터베이스인 PostgreSQL을 운영하고 pgAdmin4를 통해 데이터를 직접 관리하는 방법을 안내합니다.

---

## 1. 🛠️ pgAdmin4 서버 연결 설정

AssyManager 서버에 접속하기 위해 pgAdmin4에서 아래와 같이 서버를 등록하십시오.

- **Name**: `AssyManager_Production` (자유롭게 설정)
- **Connection Tab**:
    - **Host**: `127.0.0.1` (또는 DB 서버 IP)
    - **Port**: `5432`
    - **Maintenance database**: `assy_manager`
    - **Username**: `postgres`
    - **Password**: `admin` (또는 설정하신 비밀번호)

---

## 🔍 2. Raw 데이터 조회 및 SQL 가이드

PostgreSQL은 `data` 컬럼에 **JSONB** 형식을 사용합니다. 아래 연산자를 활용하여 데이터를 조회하십시오.

### 2.1 기본 조회 및 필터링
```sql
-- 특정 테이블의 모든 데이터 조회
SELECT * FROM data_rows 
WHERE table_name = 'raw_table_1' 
ORDER BY business_key_val ASC;

-- 특정 Row ID의 데이터 조회
SELECT * FROM data_rows WHERE row_id = 'your-uuid-here';
```

### 2.2 JSONB 데이터 세부 조회 (핵심)
PostgreSQL의 JSONB 전용 연산자를 사용하여 셀 데이터를 직접 조회할 수 있습니다.
- `->`: JSON 객체/배열 반환
- `->>` : 문자열(Text)로 결과 반환

```sql
-- 특정 컬럼('LOT_ID')의 현재 표시 값 조회
SELECT 
    row_id,
    data->'LOT_ID'->>'value' as lot_id_value,
    data->'LOT_ID'->>'updated_by' as last_editor
FROM data_rows 
WHERE table_name = 'raw_table_1';

-- 특정 소스('parser_a')에서 유입된 값만 필터링
SELECT * FROM data_rows 
WHERE data->'STATUS'->'sources'->'parser_a' IS NOT NULL;
```

### 2.3 감사 로그(Audit Log) 추적
```sql
-- 특정 행의 최근 변경 이력 5건 조회
SELECT * FROM audit_logs 
WHERE row_id = 'your-uuid' 
ORDER BY timestamp DESC 
LIMIT 5;

-- 특정 사용자가 수정한 내역 조회
SELECT * FROM audit_logs WHERE updated_by = 'user_id';
```

---

## ⚡ 3. 성능 및 유지보수

### 3.1 인덱스 상태 확인
AssyManager에는 GIN Index와 복합 색인이 설정되어 있습니다.
```sql
-- 테이블에 설정된 모든 인덱스 보기
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'data_rows';
```

### 3.2 데이터베이스 백업 및 복구 (Command Line)
pgAdmin의 [Backup/Restore] 메뉴를 사용하거나 아래 커맨드를 활용하십시오.

**백업 (Backup)**
```bash
pg_dump -U postgres -d assy_manager > assy_manager_backup.sql
```

**복구 (Restore)**
```bash
psql -U postgres -d assy_manager -f assy_manager_backup.sql
```

---

## 🛡️ 4. 주의 사항 (Best Practices)
- **Direct Update 지양**: pgAdmin에서 직접 `UPDATE` 쿼리를 실행하면 애플리케이션의 `AuditLog`가 생성되지 않아 이력 추적이 불가능해집니다. 가능한 한 서버 API를 통해 수정하십시오.
- **Large Query**: 1,000만 행 규모에서 `SELECT *` 조회 시 pgAdmin이 멈출 수 있으므로 항상 `LIMIT` 절을 사용하십시오.

---
*AssyManager Operations Guide v1.0 | 2026.04.18*
