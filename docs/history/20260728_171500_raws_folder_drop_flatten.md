# raws/ 폴더 드롭 평탄화 — 다중 층위 폴더에서 파일만 승격, 계층은 폐기

**일시**: 2026-07-28
**커밋**: `0c6ac1a`
**작업자**: Server PM
**분류**: feat (사용자 지시: "파일 인제션시 raws에 파일이 다중 층위 폴더로 감싸서 들어와도 파일만 뽑아서 파서에 넣고 폴더 계층은 풀어서 없애")

## 현상

워처는 디렉토리 이벤트를 무시하고(`on_created`의 `is_directory` 필터), observer는 `recursive=False`, 스윕도 하위 디렉토리를 제외 — `raws/`에 폴더째 들어온 파일은 **영영 방치**됐다. 운영 인제션 셋업 중 실사용 시나리오(장비 덤프를 폴더째 드롭)가 막혀 있었다.

## 해결 (`server/parsers/directory_watcher.py`)

- **트리거 2경로**: ① 디렉토리 watchdog 이벤트(`on_created`/`on_moved`) ② 기동/주기 스윕(`sweep_existing_files`가 raws/ 직속 디렉토리를 만나면 위임). 둘 다 `IngestionHandler.request_flatten` 단일 진입점 — 진행 중 가드(`_flattening_dirs` + `_processing_lock`)로 멱등/재진입 안전, 정온 대기는 전용 데몬 스레드라 observer 디스패치 스레드 무차단(P1 HOL 규율).
- **정온 게이트**: 기존 파일 안정성 프리미티브((mtime, size) 시그니처 + 1초 디바운스)를 트리로 일반화 — 트리 전체 스냅샷 `{상대경로: (size, mtime)}`이 1초 간격 연속 2회 동일할 때만 착수. 최대 600초 후 미안정이면 무접촉 유예(주기 스윕 재시도). 복사 중 폴더를 반쯤 비우는 일 없음.
- **승격**: 일반 파일을 mtime 오름차순으로 raws/ 루트로 `os.rename`(덮어쓰기 불가 의미론) 후 기존 이벤트 경로(`_handle_event`)로 디스패치 — 레인 라우팅·파서·체크포인트/dedup·archives/·err/ **전부 무변경**. 대형 파일은 평탄화된 경로에서 heavy 레인으로 정상 분류.
- **충돌 규칙(절대 덮어쓰지 않음)**: 동명 존재 시 상대 경로 접두 개명 `drop/lv2/x.csv → drop~lv2~x.csv`(그것도 겹치면 `~2`…). 구분자 `~`는 의도적 — `__` 구분자는 폴더명 `force`와 접합해 강제 재처리 토큰 `__force__`를 조작한다. 폴더명 속 토큰은 중화, 파일명 자신의 토큰은 유지(사용자 의도), `user(<name>)` 업로더 접두는 앞으로 끌어올려 보존. 배치 내 이미 아카이브된 동명자는 claimed 집합으로 차단. 모든 개명 로그.
- **보수적 삭제**: `os.rmdir`만 사용(비어 있지 않으면 실패가 곧 보존 보장). 잠긴 파일 등 이동 실패 시 파일·폴더 보존 + warning, 주기 스윕이 잔여 재시도. OS 잔재(`Thumbs.db`/`desktop.ini`/`.DS_Store`/`._*`)는 폴더와 함께 폐기.
- **스위치**: `ingestion_settings.json` `"flatten_nested_dirs"`(기본 true, 트리거당 핫리로드). `.sample` 문서화.

## 검증

- 신규 `server/tests/test_flatten_nested_dirs.py` 15건: 3층 트리 전량 적재+폴더 소멸, 충돌 접두/수치 접미, `__force__` 비조작·`user()` 보존, 복사 중 대기·영구 불안정 유예, 잠금 파일 폴더 보존→해제 후 완결(Windows), 숨김 파일 정책, 스위치 off/핫 재활성, 재진입 no-op, 스윕 트리거, heavy 레인 라우팅.
- **결함 주입 2종으로 테스트 유효성 증명**(교훈 파일 규율): 정온 게이트 제거 → 2건 실패, 충돌 해석 제거 → 3건 실패. 원복 후 전체 스위트 **875 passed**.
- **독립 퀵 QA**: 핵심 시나리오 5종(중첩+충돌 · 복사 중 대기 · 잠긴 파일 · 핫 토글 off/on · `__force__` 토큰 안전) 전부 재실행 — **5/5 WORKS**. `rmdir`-only 삭제는 코드와 라이브 잠금-분기 실행 양쪽에서 확인.
- **격리(:8081) E2E**: `parts` 워크스페이스에 3층 폴더(파일 4 + Thumbs.db, 동명 충돌 1, heavy 임계 초과 1) 드롭 → 4파일 전량 적재(409행: 3+3+3+400), 충돌 파일 `drop~lv2~x.csv`로 개명돼 양쪽 내용 모두 생존, heavy.csv `lane=heavy` 라우팅, Thumbs.db 폐기, raws/ 평탄 복귀, archives/ 4파일, err/ 0건, 워처 로그에 8080 접촉 0회.

## 문서

`INGESTION_GUIDE.md` §1.9 신설(동작·충돌 규칙·숨김 파일 정책·끄는 법), `ingestion_settings.json.sample` 갱신.
