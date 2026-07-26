# QA 적대 검수: 대형 파일 P1 heavy 레인 분리 (working tree, 병합 전)

- 검수자: qa-reviewer / 2026-07-26
- 대상: 미커밋 working tree (docs/process/PROJECT_STATUS.md 제외 — 총괄 작업분)
- 구현 보고서: `agent_workspace/reports/Server_large_file_p1_report.md`
- 스위트 재실행 실측: **253 passed / 1 failed(`test_map_presets_api` — 기준선 허용 실패)** — 구현자 주장 재현 확인

## 1. 판정: **GO-WITH-FIXES**

상호 배제(같은 테이블 동시 업서트 불가)는 빈틈없이 성립하고 교차 워크스페이스 격리·경로 불변·WS 계약 무변경도 실증됐다. 다만 (a) FIFO 순서 보존에 마이크로초급 check-then-act 잔여 창이 있고(기존 대비 엄격한 개선이므로 비차단), (b) **30분 이상 QUEUED 상태로 대기하는 heavy 파일이 TTL로 퇴거되어 재기동 경고가 정확히 최악 시나리오(다중 heavy)에서 과소 표시**되는 결함이 있다 — (b)는 병합 전/직후 수정 권장(수정 소형).

## 2. 확인된 결함 (심각도순)

### F1 [중] QUEUED 장기 대기 heavy 엔트리의 TTL 퇴거 — 재기동 경고 과소 표시
- `server/ingestion_activity.py:25` (TTL 30분), `:116` (snapshot 시 `updated_at` 기준 퇴거)
- **실패 시나리오**: 20분짜리 heavy 파일 3개 투입 → 3번째 파일은 QUEUED 통지 1회 이후 갱신 없음 → 40분 대기 중 30분 시점에 snapshot에서 퇴거 → admin 진행 목록 2건 표시·재기동 경고 "2건" → 운영자가 3번째 파일 존재를 모른 채 재기동하면 해당 파일도 처음부터 재처리. PROCESSING 진입 시 상태 통지로 엔트리가 재생성되어 자가 치유되지만, 경고가 목적인 창(재기동 직전) 동안 부정확하다.
- **권장**: `snapshot()` 퇴거에서 `status == "QUEUED"` 엔트리는 별도(훨씬 긴) TTL 적용, 또는 watcher가 큐 대기 엔트리에 주기 하트비트 상태 통지. (수정 수 줄)

### F2 [중→낮] 순서 보존 불변식의 check-then-act 잔여 창 (observer↔스윕 동시 진입)
- `server/parsers/directory_watcher.py:577-591`(`_route_and_process`: backlog 검사→try-acquire가 비원자), `:603-609`(`_submit_to_heavy_lane`: 분류 후 backlog 증가)
- **실패 시나리오**: 같은 워크스페이스에서 ① observer 스레드가 F1(heavy) 분류 완료, backlog 증가 직전 ② 스윕 스레드가 F2(소형, F1보다 늦게 감지) 진입 → backlog==0 관측 → try-acquire 성공 → F2 인라인 처리 시작 ③ F1이 큐에 들어가 워커가 직렬화 락에서 대기 → **F2가 F1보다 먼저 업서트**. 상호 배제는 유지되나(동시 업서트는 불가) FIFO가 역전된다.
- **완화 사실**: 변경 전 기준선은 이 상황에서 락 자체가 없어 두 파일이 **완전 동시 업서트**됐다 — 본 변경은 엄격한 개선이며 잔여 창은 마이크로초급 + 스윕·이벤트 동시 유입 조건 필요. 병합 비차단.
- **권장(후속)**: 라우팅 결정(backlog 검사·증가·try-acquire)을 `_lane_state_lock` 한 임계구역으로 묶어 원자화.

### F3 [중→낮] 재처리 경로가 직렬화 락 밖 — 노출 창이 초→분 단위로 확대
- `server/run_watcher.py:198-210`(PENDING_RETRY 폴러), `server/main.py:3265-3274`(admin retry-failed) — 둘 다 `process_archived_file_sync`로 락 없이 처리.
- **실패 시나리오**: 테이블 X의 heavy 파일 7분 처리 중 운영자가 X의 실패 로그 재시도 클릭(또는 폴러가 PENDING_RETRY 소비) → heavy 업서트와 재처리 업서트가 같은 테이블에 동시 진행 → 인터리빙에 따라 나중 파일 값이 먼저 파일 값으로 덮일 수 있음.
- **판정**: 구현자 §6-5 진술("종전과 동일한 동시성 의미론") **사실로 확인** — 변경 전에도 폴러/observer 간 무락 경합 가능. 단 heavy 도입으로 경합 창이 초→분으로 커졌고, **run_watcher 폴러는 heavy 워커와 같은 프로세스**이므로 `get_workspace_serial_lock` 획득 한 줄로 결정적으로 닫을 수 있다. 후속 태스크 권장.

### F4 [낮] 재라우팅된 소형 파일의 교차 워크스페이스 HOL 재발 + lane 오표기
- `server/parsers/directory_watcher.py:602-625`: 큐는 전 워크스페이스 공유 단일 FIFO. try-acquire 실패/backlog로 재라우팅된 **소형** 파일이 타 워크스페이스의 7분짜리 heavy 뒤에 줄 선다(자기 워크스페이스는 수 초 내 해방됐는데도 분 단위 대기 — 격리 목표의 부분 후퇴, 발생 조건은 스윕·이벤트 동시 유입으로 드묾).
- 같은 함수 `:614` — QUEUED 통지가 `"lane": "heavy"` 하드코딩: 소형 파일이 admin에 HEAVY 배지로 표시되고 Overview/헬스의 heavy 카운트가 부풀려짐(표시 전용 오정보).
- **권장(후속)**: 통지 lane에 실제 분류값 전달. 워크스페이스별 큐/워커 승격은 escalation §6-3(P3 연계)과 함께 검토.

### F5 [낮] 상태 통지 HTTP가 라우팅 스레드/직렬화 락 하에서 최대 5초 블로킹
- `server/run_watcher.py:42-49`(`post_event` timeout=5) — QUEUED 통지는 observer 디스패치 스레드에서, PROCESSING 통지는 직렬화 락 보유 중 발신. 웹서버 다운 시 heavy 파일당 최대 ~5초 지연. 유계이고 기존 file-processed 통지도 동일 패턴 — 관찰 기록만.

### F6 [낮] 워커 스레드 BaseException 사망 시 큐 잔여 작업 정체
- `server/parsers/directory_watcher.py`(`_worker_loop`는 `Exception`만 흡수) — 비-Exception 탈출 시 스레드 사망, 큐 잔여 작업과 `processing_files` 엔트리가 **다음 heavy 제출**(`_ensure_running` 재기동)까지 정체. 파일은 raws/에 남고 스윕은 `processing_files` 가드로 재진입 불가. 발생 확률 극히 낮음(데몬 스레드 KeyboardInterrupt 등) — 관찰 기록만.

### F7 [낮] `renderActiveIngestions` filename/table_name 미이스케이프 innerHTML
- `client2/src/admin.js`(신규 렌더러) — admin.js 전반의 기존 패턴과 동일(신규 회귀 아님, 파일명은 준신뢰 입력). 전 파일 일괄 정리 시 함께.

## 3. 반증 시도했으나 안전한 항목

| 가설 | 안전 근거 |
|---|---|
| 교착: 직렬화 락+`_processing_lock`+`_sweep_lock`+워커 1 조합 순환 대기 | 워커는 직렬화 락만 대기, 락 보유자는 큐를 기다리지 않음, 인라인 블로킹 acquire(최후 폴백)는 아무 락도 안 쥔 상태에서만 — 순환 없음 |
| 스윕·이벤트 이중 처리(큐 대기 중 재감지) | `_handle_event`의 check-then-add가 `_processing_lock`으로 원자(directory_watcher.py:524-529), heavy 큐 대기 중에도 `processing_files` 유지, `_sweep_attempted` 시그니처 이중 가드 |
| 스윕 순서: 같은 워크스페이스 [heavy(구), 소형(신)] mtime 순 스윕 시 역전 | heavy 제출 즉시 backlog>0 → 소형은 크기 무관 큐 후미 — FIFO 유지 |
| backlog 카운터 누수 | 증가 경로마다 감소 짝 존재: submit 예외 시 즉시 복원, `_run_lane_job` finally는 BaseException에도 실행 |
| 임계값 파싱 함정(`True`가 int 통과) | `isinstance(val, bool)` 선차단(directory_watcher.py:155), 0/음수/문자열/리스트 전부 폴백 + 1회 경고 — 테스트 6종 parametrize 실증 |
| 구 서버 HTML-200 catch-all 함정으로 admin 파손 | 클라이언트 4개 호출부 전부 `.catch`/`res.ok`/json 실패 흡수 — 구 서버에서도 무해 |
| 5s 타이머 누수(탭 전환·숨김) | 단일 self-rescheduling setTimeout + 중복 가드, hidden/탭 이탈/목록 공백 시 체인 소멸, 30s interval(admin.js:164-171)이 복귀 시 재점화 |
| `/internal/events/broadcast` 인터셉트가 기존 흐름 파손 | 예외 격리된 추가 처리만, 캐시 무효화·created_logs·브로드캐스트 기존 순서 무변경. WS 이벤트명·페이로드 신설/변경 0건 |
| 파일명 키 불일치(고아/유령 엔트리) | 3개 유입 경로 + remove 전부 `get_basename` 정규화, main.py는 sys.path에 parsers 포함(main.py:91)이라 임베디드 폴백도 동일 |
| 확장성(1000만행) | 레지스트리 O(진행 중 파일 수)·DB 무접점, 라우팅당 설정 파일 1회 읽기는 소형 JSON, active API 무페이징이나 상시 소수 항목 — 통과 |
| 성장 중/0바이트 파일 라우팅 | normal 오분류는 레인 도입 전 인라인과 동일 동작으로 열화(순서 규칙은 여전히 적용), 주 발원지(auto_update)는 copy&rename 원자적 — 정합 무해 |

## 4. 런타임 검증 필요 (코드만으로 단정 불가)

구현 보고서 §4 계획 타당 — 전부 재기동 후. 추가로:
1. **데몬 스레드 종료 의미론 변화**: 변경 전엔 observer.join이 인라인 처리 완료를 기다렸으나, 이제 heavy 처리 중 프로세스 종료 시 업서트 도중 강제 절단됨 — 부분 행 잔류 후 재인제션 업서트로 수렴하는지(멱등성) 라이브 확인 필요.
2. 다중 heavy(3개 이상) 투입 시 F1(TTL 퇴거) 실증 및 수정 후 재확인.
3. 웹서버 다운 상태에서 heavy 투입 → 통지 5초 타임아웃이 처리 자체를 막지 않는지.

## 5. 문서 정합 / 보고서 주장 대조

- 스위트 실측 **253 passed / 1 allowed fail — 보고서 주장과 일치**. `node --check admin.js` OK, dist 재빌드 정합(admin.html이 `admin-BfVuKRnT.js` 참조, 번들에 신규 엔드포인트 포함) 확인.
- 보고서 §1-3 "두 레인이 같은 테이블을 동시에 업서트하는 일 자체가 불가능" — **사실**(상호 배제 성립). 단 "워크스페이스 내 FIFO 유지"는 F2 잔여 창을 언급하지 않은 **경미한 과장** — 정확히는 "기존 대비 대폭 강화된 best-effort FIFO".
- docs/ 무수정(지시 준수), gitignored 사용자 영역(`server/config/*.json`, mappers/, ingestion_workspace/) 전수 재검색 — 신규 키/엔드포인트 소비처 누락 0건, `.sample`만 추가로 라이브 config 무접촉 확인.
- 테스트 실질성: 순서 보존·교차 격리 테스트는 실제 `HeavyIngestionLane` 스레드 + Event 게이트 기반의 결정적 인터리빙 구성 — 형식적 테스트 아님. 단 F2의 스윕↔observer 동시 진입 창은 미커버(잔여 창의 존재와 부합).

## 6. Escalation §6 항목별 타당성 판정

1. **임계 설정 위치(전용 파일)**: **타당**. `models.init_dynamic_models`가 `config_dict.items()`를 무필터 순회함을 실증(models.py:227) — `_system` 키는 실제로 물리 테이블이 된다. server/config 서브시스템별 파일 관례도 실재.
2. **REST 2종 신설**: **승인 권장**. 순수 추가분, 기존 REST/WS/셀 계약 무변경 실증. doc-keeper 반영 대상.
3. **heavy 워커 단일**: **타당**. heavy끼리 직렬화는 P1 목표(교차 격리) 미훼손. 병렬화-outbox 파도 연계 논거 건전 — P3 함께 검토 동의. 단 F4(재라우팅 소형 파일의 큐 후미 대기)가 이 설계의 숨은 비용임을 병기할 것.
4. **클라이언트 5s 폴링**: **타당한 해석**. 지시서 괄호 문구는 프로세스 간 경로 지칭이 맞고, 구현은 push. 5s 타이머는 인메모리 조회 + 3중 게이트 — 유지 권장.
5. **재처리 경로 락 밖**: 진술 **사실이나**, run_watcher 폴러는 같은 프로세스이므로 한 줄 수정으로 닫힘 — 후속 태스크로 격상 권장(F3).

## 7. 교훈 제안 (qa-reviewer.md 반영 후보 — 총괄 검수 후)

- **함정**: "backlog 카운터 + try-acquire" 식 순서 보존 장치는 검사와 획득이 별개 락이면 check-then-act 창이 남는다. **올바른 방법**: 라우팅 결정 전체(카운터 검사·증가·락 시도)를 단일 임계구역으로 검수하고, 원자화 불가하면 잔여 창을 보고서에 명시하게 한다.
- **함정**: TTL 기반 고아 정리는 "정상적으로 오래 조용한" 엔트리(큐 대기)를 함께 죽인다. **올바른 방법**: 상태별 TTL 차등 또는 하트비트 존재를 확인.
