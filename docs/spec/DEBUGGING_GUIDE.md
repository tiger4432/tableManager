# AssyManager: 트러블슈팅 및 디버깅 가이드 (The Debugger's Bible)

> **Status:** 🟢 Living | **Last-verified:** 2026-08-11 | **Owner:** Ops / QA
> 🔴 **[2026-08-06] §1–§4가 아카이브됐고 이 문서는 이제 §0(읽기 전용 진단 도구)만 담습니다** — 옛 절은 [_archive/DEBUGGING_GUIDE_pyside6_era.md](../_archive/DEBUGGING_GUIDE_pyside6_era.md). 상태 헤더가 없어 README 배지를 뒷받침할 근거가 파일 안에 없던 것도 함께 고쳤습니다.
> **[2026-08-11]** §0에 세 번째 도구 `diagnose_slow_after_ingest.py`(`2b8a5ab`+`1a1947b`) 추가 — 대량 인제션 직후 "느려졌다"의 원인을 스레드 토큰/DB 커넥션/쿼리 자체로 끊어 가르는 사다리이고, **운영 박스가 출력 복사를 금지해 결론이 한 줄로 끝난다.**

본 문서는 개발 및 운영 과정에서 발생할 수 있는 주요 장애 유형과 해결 방법, 그리고 디버깅을 위한 체크리스트를 제공합니다.

---

## 🔎 0. 먼저 도구 셋 — 전부 **읽기 전용**입니다 (2026-08-04 신설, 2026-08-11 세 번째 추가)

증상 하나에 원인이 여럿일 때, 다섯 개 명령을 치고 다섯 개 출력을 읽게 하는 것이 **엉뚱한 것을 고치는** 경로입니다. 그래서 판별을 대신 해 주는 스크립트 셋이 있습니다. **아무것도 기동하지 않고, 멈추지 않고, 쓰지 않습니다.**

| 도구 | 언제 | 무엇을 가르나 |
|---|---|---|
| `server/scripts/diagnose_socket.py` | **「소켓이 안 된다」** | 이 스택에서 그 문장의 원인은 **최소 다섯**이고 수리가 서로 반대다 — ① 런처가 둘이라 포트를 남이 쥠 ② 백엔드는 떠 있는데 WS 라우트가 아님 ③ 사내 프록시가 HTTP Upgrade를 거절 ④ 클라 번들 에셋이 404 ⑤ 브라우저가 자기 백오프를 기다리는 중 |
| `server/scripts/diagnose_db_health.py` | **「API가 예전보다 느려졌다」** | 오래 열린 트랜잭션 → xmin 지평 정체 → autovacuum이 죽은 튜플을 회수 못 함 → 블로트 → 순차 스캔 비용 증가. **점진적으로 오는 느려짐**이라 단발 타이밍 측정으로는 안 보인다. 긴 트랜잭션·블로트·블로킹을 함께 본다 |
| `server/scripts/diagnose_slow_after_ingest.py`(2026-08-11 신설, `2b8a5ab`+`1a1947b`) | **「대량 인제션 직후 화면이 느려졌다」** | 한 핸들러가 오래 잡고 있어도 **다른 요청 전부가 죽지는 않는다** — 재현되는 것은 파일업이고 그 원인은 넷 중 하나다: 스레드 토큰 소진(anyio, 기본 40) · DB 커넥션 풀 소진 · 쿼리 자체 · 직렬화 비용. §4b 사다리가 `/health`(토큰 無, DB 有) → 정적 에셋(토큰만) → sync 핸들러(토큰+DB 無 쿼리) → 같은 핸들러 limit별로 단을 쌓아, **어느 단에서 값이 뛰는지**로 원인을 하나로 좁힌다. 🔴 **운영 박스가 출력 복사를 금지하므로 결론은 한 줄**(`판정 점프 R1→R2 +390ms (12→403) = DB커넥션 | R0 14ms·최대 415ms·칸 7/7·db=ok`) — 판정불가/부분측정/점프없음은 **서로 다른 답**이고 조용한 실행이 건강한 실행으로 렌더되지 않는다 |

```bash
conda run --no-capture-output -n assy_manager python server/scripts/diagnose_socket.py
conda run --no-capture-output -n assy_manager python server/scripts/diagnose_db_health.py
conda run --no-capture-output -n assy_manager python server/scripts/diagnose_slow_after_ingest.py
```

⚠️ **Windows에서 `--no-capture-output`은 장식이 아니다** — 없으면 `conda run`이 자식 출력을 자기 디코더(한글 Windows에서 cp949)로 통과시켜, 스크립트 자신은 UTF-8로 찍어도 한글 헤딩이 전부 mojibake로 도착한다.

- 🔴 **소켓 진단의 모든 검사는 일부러 raw 소켓입니다.** 이 환경에는 `127.0.0.1`도 우회하지 못하는 사내 프록시가 있고, 그 「한 줄 처방」인 `NO_PROXY` 설정은 **이미 이 저장소에서 인시던트를 냈습니다**(urllib이 프록시 레지스트리를 통째로 무시). raw 소켓은 프록시 설정을 아예 참조하지 않으므로 **속을 수도, 바꿀 수도 없습니다.**
- 🔴 **DB 진단은 의도가 아니라 구조로 읽기 전용입니다** — 세션에 `transaction_read_only = on`을 먼저 박습니다. `VACUUM`·`ANALYZE`·`terminate`를 내지 않고, **볼 만한 PID를 이름만 대고 멈춥니다**(세션을 죽이는 것은 운영자의 결정이고, idle-in-transaction 하나가 편집 중인 사람일 수 있습니다).
- 🔴 **DB 진단은 앱이 해석한 접속 URL을 씁니다**(`DATABASE_URL` > `<config>/database.json` > 기본값 3단계 중 **어느 것이 답했는지**를 함께 출력). 모듈 기본값을 직접 읽으면 **개발자 DB를 찔러 놓고 운영을 보고하게** 됩니다 — 이 스크립트의 첫 실행에서 실제로 일어난 일입니다.
- 임계값은 **권위가 아니라 굵게 찍을 것을 정할 뿐**입니다(긴 트랜잭션 300초·블로트 비율 0.20). 바쁜 시스템의 5분짜리는 평범할 수 있고 1분짜리가 누수일 수 있습니다.
- 🔴 **느려짐 진단도 의도가 아니라 구조로 읽기 전용입니다** — `default_transaction_read_only=on`을 **연결 옵션**으로 걸어 롤백 뒤 새로 여는 트랜잭션까지 적용받게 하고, `lock_timeout`·`statement_timeout`·`idle_in_transaction_session_timeout`도 함께 박아 **진단 자신이 struggling한 박스를 더 나쁘게 만들 수 없게** 합니다. 유일하게 쓰는 것은 이름을 직접 줬을 때만 생기는 선택적 `--json` 스냅샷 파일뿐입니다.

---

---

## 🗄️ §1–§4는 아카이브됐습니다 (2026-08-06)

종전 이 아래에는 **실행/환경 · 통신 · 데이터 모델 · 로그** 네 절이 있었고, 전부 **제거된 PySide6 클라이언트 앱**을 전제로 쓰여 있었습니다 — `sys.path`의 Qt DLL, `main.py`의 `to_local_str()`, 위젯 모델의 고스트 행처럼 **오늘 존재하지 않는 자리**를 가리킵니다.

🔴 **§0만 남긴 이유**: 그 두 진단 스크립트는 **현행이고 매일 쓸 수 있습니다.** 낡은 절과 한 파일에 두면 §0을 찾아 온 사람이 그 아래를 읽고 없는 파일을 뒤지게 됩니다.

옛 내용은 [`_archive/DEBUGGING_GUIDE_pyside6_era.md`](../_archive/DEBUGGING_GUIDE_pyside6_era.md)에 그대로 있습니다 — **삭제하지 않은 것은 증상 서술이 웹 클라에서 형태를 바꿔 재발할 수 있는 계급이기 때문**입니다.
