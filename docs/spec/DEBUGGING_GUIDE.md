# AssyManager: 트러블슈팅 및 디버깅 가이드 (The Debugger's Bible)

본 문서는 개발 및 운영 과정에서 발생할 수 있는 주요 장애 유형과 해결 방법, 그리고 디버깅을 위한 체크리스트를 제공합니다.

---

## 🛑 1. 실행 및 환경 관련 (Environment)

### 1.1 DLL 로드 에러 (Windows)
- **증상**: `ImportError: DLL load failed` 발생.
- **원인**: Conda 환경 또는 PyInstaller 빌드 시 특정 Qt/Python DLL이 격리되지 않음.
- **해결**:
  - `main.py` 상단의 `sys.path` 조작 로직이 해당 실행 환경의 `Library/bin`을 포함하는지 확인.
  - 빌드 시 `--add-binary` 플러그인을 사용하여 필수 DLL을 번들에 포함.

### 1.2 타임존(Timezone) 불일치
- **증상**: 데이터 수정 시간(`updated_at`)이 9시간 차이나게 표시됨.
- **원인**: 서버(PostgreSQL)는 UTC로 저장하고, 클라이언트는 이를 Local로 변환하지 않음.
- **해결**: `main.py`의 `to_local_str()` 함수와 `inject_system_columns()`가 명시적으로 `.astimezone()` 변환을 수행하는지 확인.

---

## 📡 2. 통신 및 네트워크 (Communication)

### 2.1 WebSocket 끊김 및 지연
- **증상**: 데이터 수정 후 다른 클라이언트에 즉시 반영되지 않음.
- **디버깅**:
  - 브라우저나 도구(wscat)를 통해 `ws://127.0.0.1:8000/ws` 접속 유지 여부 테스트.
  - 클라이언트 로그 패널에 "[WsListenerThread] Connection failed" 메시지 확인.
  - **해결**: 서버의 `active_connections` 리스트가 유실되지 않았는지, 프록시(Nginx 등)가 WebSocket 업그레이드를 차단하는지 확인.

---

## 📊 3. 데이터 및 모델링 (Data Model)

### 3.1 고스트 행 (Ghost Row) 현상
- **증상**: 스크롤을 내리면 이전에 보았던 행이 다시 나타남 (Deduplication 실패).
- **원인**: 
  1. `row_id`가 숫자로 오인되어 매핑 딕셔너리 키 매칭 실패.
  2. 서버 청크 데이터가 중복 전달됨.
- **해결**: `table_model.py` 내의 `_build_row_id_map`에서 모든 키를 `str()` 처리하고, `fetchMore` 전후로 `_fetching_row_ids`를 엄격히 관리하십시오.

### 3.2 셀 주황색(Amber) 하이라이트 누락
- **증상**: 수동 수정했는데 셀 배경색이 변하지 않음.
- **원인**: `is_overwrite` 플래그가 JSON 데이터에 반영되지 않음.
- **해결**: `crud.update_cell` 함수 내에서 `is_overwrite=True` 할당 로직을 확인하십시오.

---

## 📝 4. 로그 및 모니터링 명령
- **서버 로그**: `uvicorn main:app --log-level debug`
- **인제션 로그**: `python directory_watcher.py` 실행 후 출력되는 "New file detected" 메시지 확인.
- **클라이언트 로그**: `history_panel` 하단의 계보(Lineage) 데이터가 실제 `audit_logs` 테이블 레코드와 일치하는지 SQL 조회:
  ```sql
  SELECT * FROM audit_logs WHERE row_id = 'YOUR_ID' ORDER BY timestamp DESC;
  ```

---
*AssyManager Debugging Guide v1.1 (PostgreSQL Revision)*
