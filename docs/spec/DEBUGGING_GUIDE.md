# AssyManager: 트러블슈팅 및 디버깅 가이드 (The Debugger's Bible)

본 문서는 개발 및 운영 과정에서 발생할 수 있는 주요 장애 유형과 해결 방법, 그리고 디버깅을 위한 체크리스트를 제공합니다.

---

## 🔎 0. 먼저 도구 두 개 — 둘 다 **읽기 전용**입니다 (2026-08-04 신설)

증상 하나에 원인이 여럿일 때, 다섯 개 명령을 치고 다섯 개 출력을 읽게 하는 것이 **엉뚱한 것을 고치는** 경로입니다. 그래서 판별을 대신 해 주는 스크립트 둘이 있습니다. **아무것도 기동하지 않고, 멈추지 않고, 쓰지 않습니다.**

| 도구 | 언제 | 무엇을 가르나 |
|---|---|---|
| `server/scripts/diagnose_socket.py` | **「소켓이 안 된다」** | 이 스택에서 그 문장의 원인은 **최소 다섯**이고 수리가 서로 반대다 — ① 런처가 둘이라 포트를 남이 쥠 ② 백엔드는 떠 있는데 WS 라우트가 아님 ③ 사내 프록시가 HTTP Upgrade를 거절 ④ 클라 번들 에셋이 404 ⑤ 브라우저가 자기 백오프를 기다리는 중 |
| `server/scripts/diagnose_db_health.py` | **「API가 예전보다 느려졌다」** | 오래 열린 트랜잭션 → xmin 지평 정체 → autovacuum이 죽은 튜플을 회수 못 함 → 블로트 → 순차 스캔 비용 증가. **점진적으로 오는 느려짐**이라 단발 타이밍 측정으로는 안 보인다. 긴 트랜잭션·블로트·블로킹을 함께 본다 |

```bash
conda run -n assy_manager python server/scripts/diagnose_socket.py
conda run -n assy_manager python server/scripts/diagnose_db_health.py
```

- 🔴 **소켓 진단의 모든 검사는 일부러 raw 소켓입니다.** 이 환경에는 `127.0.0.1`도 우회하지 못하는 사내 프록시가 있고, 그 「한 줄 처방」인 `NO_PROXY` 설정은 **이미 이 저장소에서 인시던트를 냈습니다**(urllib이 프록시 레지스트리를 통째로 무시). raw 소켓은 프록시 설정을 아예 참조하지 않으므로 **속을 수도, 바꿀 수도 없습니다.**
- 🔴 **DB 진단은 의도가 아니라 구조로 읽기 전용입니다** — 세션에 `transaction_read_only = on`을 먼저 박습니다. `VACUUM`·`ANALYZE`·`terminate`를 내지 않고, **볼 만한 PID를 이름만 대고 멈춥니다**(세션을 죽이는 것은 운영자의 결정이고, idle-in-transaction 하나가 편집 중인 사람일 수 있습니다).
- 🔴 **DB 진단은 앱이 해석한 접속 URL을 씁니다**(`DATABASE_URL` > `<config>/database.json` > 기본값 3단계 중 **어느 것이 답했는지**를 함께 출력). 모듈 기본값을 직접 읽으면 **개발자 DB를 찔러 놓고 운영을 보고하게** 됩니다 — 이 스크립트의 첫 실행에서 실제로 일어난 일입니다.
- 임계값은 **권위가 아니라 굵게 찍을 것을 정할 뿐**입니다(긴 트랜잭션 300초·블로트 비율 0.20). 바쁜 시스템의 5분짜리는 평범할 수 있고 1분짜리가 누수일 수 있습니다.

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
