# 완료 보고: 워크스페이스 config.json 폐지 (레거시 정리)

- 지시서: `agent_workspace/tasks/Server_workspace_config_deprecation_task.md`
- 작업 위치: 메인 트리 (커밋 없음 — 총괄 검수 대기, 라이브 서버 무접촉)
- 히스토리: `docs/history/20260725_220619_workspace_config_deprecation.md` (+ `gen_index.py` 실행 완료)

## 판정 요약

| 요구 | 상태 |
|---|---|
| 1. 필드 흡수 (`workspace_name` / `std_parse`) | ✅ 완료 (std_parse **핫리로드화 — F4 자연 해소**) |
| 2. 자동 생성 시 config.json 신설 중단 | ✅ 완료 |
| 3. 하위호환 읽기 + deprecation 경고(1회) | ✅ 완료 (기존 파일 무삭제) |
| 4. 우선순위 규칙 명확화 | ✅ table_config.json 승리 (아래 명기) |
| 테스트 | ✅ main 기준선 **208 passed / 1 allowed fail** → 변경 후 **220 passed / 1 allowed fail** (동일 허용 실패 `test_map_presets_api`) |

## 우선순위 규칙 (명기)

핸들러(`IngestionHandler`)의 해석 순서 — **충돌 시 상위가 승리**:

1. **글로벌 `table_config.json`** — `workspace_name` 명시 별칭 매칭(테이블명 결정), 테이블 항목의 `std_parse`(옵트아웃). **파일 단위 핫리로드**: 파일 처리 시작 시 스냅샷 1회를 잡아 그 파일은 시작 시점 config로 완결되고 변경은 다음 파일부터 반영(QA D1 수정 반영 — 하단 QA 수정 섹션 참조).
2. **[deprecated] 레거시 워크스페이스 `config.json`** — `table_name`/`std_parse` 폴백(파일 파싱만 캐시).
3. **기본값** — 폴더명=테이블명 규약 / std_parse 활성(true).

주의 명세: `workspace_name`은 **명시 별칭만** 글로벌 승리 대상이다. 폴더명=테이블명 "규약 해석"은 별칭이 아니므로 레거시 `table_name`을 덮지 않는다(기존 워크스페이스 동작 보존). 동일 별칭을 복수 테이블이 선언하면 첫 항목 승리 + WARNING. 경로 구분자(`/`,`\`,`..`)가 든 별칭은 자동 생성에서 무시(경로 탈출 방지, WARNING).

## 변경 파일

| 파일 | 내용 |
|---|---|
| `server/parsers/directory_watcher.py` | 핵심. 신규 헬퍼 `find_workspace_alias` / `resolve_workspace_table` / `warn_legacy_workspace_config`(경로당 1회). `table_name`·`std_parse_enabled` 프로퍼티 재작성(글로벌 우선·무캐시 → 핫리로드, 레거시만 캐시 `_load_legacy_config`). `_provision_workspaces` config.json 생성 제거 + 별칭 폴더 지원. `_register_workspace` 별칭 해석 등록 + 기동/리로드 시 deprecation 경고. 구 `_cached_table_name`/`_cached_std_parse_enabled` 제거(전수 grep 잔존 0) |
| `server/main.py` | `/admin/file-ingestion/workspaces` 표시 `table_name`에 글로벌 별칭 우선 적용(같은 우선순위 규칙). REST 경로·응답 형태 불변(경계 계약 무접촉) |
| `server/setup/setup_workspace.py` | config.json 배치 안내 문구 → deprecation 안내로 교체 |
| `server/tests/test_workspace_config_deprecation.py` | 신규 12개 (아래) |
| `server/tests/test_std_parser.py` | `test_provision_creates_missing_workspaces`의 config.json 생성 단언 → 미생성 단언으로 갱신 |
| `docs/guide/INGESTION_GUIDE.md` | §1.5 옵트아웃 위치 이관 + 핫리로드 문구 반전(F4 해소) + deprecation 블록, §1.6 config.json 생성 제거 반영 |
| `docs/history/20260725_220619_workspace_config_deprecation.md` (+README 인덱스) | 이력 기록 |

## 테스트 (신규 `test_workspace_config_deprecation.py`, 테이블명 전부 `wscfg_test_*`)

- ① **별칭 인제션**: `workspace_name` 폴더 자동 생성·감시 편입·`table_name` 해석·파일 드롭→별칭 대상 테이블 업서트 end-to-end (2건)
- ② **옵트아웃**: `std_parse:false` 차단 + **핫리로드 왕복(false→true→false) 즉시 반영**(핸들러 재생성 없음) + 부재 시 기본 true (3건)
- ③ **레거시 하위호환**: 구식 config.json 그대로 동작 + `[DEPRECATED]` 경고 **정확히 1회**, 기동(discover) 시 경고, **글로벌 승리 충돌 검증**(table_name·std_parse 동시), 글로벌 무필드 시 레거시 폴백 유지 (4건)
- ④ **자동 생성 미생성**: config/ 빈 채 생성+멱등, config 없이 규약 등록·인제션 동작, unsafe 별칭 방어 (3건)

전체 스위트: `conda run -n assy_manager python -m pytest server/tests/ -q` → **220 passed, 1 failed**(`test_api.py::test_map_presets_api` — 착수 전 main 선측정에서도 동일 실패한 기존 허용 실패).

## 교차 점검 (교훈 파일 준수 확인)

- **gitignored 사용자 영역 전수 grep**: `ingestion_workspace` 14개 워크스페이스 config 전량 열람 — **전부 폴더명=테이블명, std_parse 사용 0건** → 동작 변화 없음. `sensor_metrics/config/sensor_config.json`은 커스텀 파서 전용 규칙 파일로 스크립트가 자체 경로로 직접 읽음 + 레거시 폴백으로 핸들러 해석도 계속 동작. `mappers/`·`config/*.json`에 workspace config 소비자 없음.
- **/internal/events 발신 경로**: 본 변경은 이벤트 페이로드·발신 경로 무접촉(워처/체인 워커의 통지 계약 불변).
- **config_watcher 원자적 쓰기 함정**: 신규 필드는 비(非)스키마 필드라 물리 ALTER와 무관하며, 핫리로드는 config_watcher 발화에 **의존하지 않고** 매 접근 시 디스크 재조회로 달성(watcher 미발화여도 반영됨).
- 셀 형태·WS 이벤트·`/schema` 응답: `get_table_schema`는 필드 화이트리스트 방식이라 신규 필드가 응답에 누출되지 않음 — 경계 계약 불변.

## 적용 필요 config 전문 (총괄 적용용)

**현재 라이브 기준 필수 변경 없음.** 실사용 별칭·옵트아웃이 0건이라 `server/config/table_config.json` 수정 없이 그대로 동작한다. 선택 권장(총괄 판단): 커스텀 변환 의존 워크스페이스의 raw 적재 방지용 옵트아웃 예시 —

```json
"<테이블명>": { ...기존 필드..., "std_parse": false }
```

(별칭이 필요해지면 `"workspace_name": "<폴더명>"`을 해당 테이블 항목에 추가.)

## 미해결 / 다음 단계

- 라이브 워처/웹서버는 재기동하지 않았다 — 배포(재기동) 시 각 레거시 워크스페이스당 `[DEPRECATED]` WARNING 1회가 로그에 나타나는 것이 정상.
- 레거시 읽기 경로의 최종 제거 시점(파일 정리 캠페인 포함)은 총괄 결정 사항.
- `PROJECT_STATUS.md`·`CODE_MAP.md`·`FEATURE_CHECKLIST.md`는 지시대로 미수정 — CODE_MAP §3 `directory_watcher` 항목(프로퍼티 라인 ~147–182, `_provision_workspaces`/`_register_workspace` 라인)과 상태 보드 갱신은 통합 시 총괄/doc-keeper 일괄 반영 요망.

## QA 수정 반영 (GO-WITH-FIXES 후속, 2026-07-25)

QA 전문(`agent_workspace/reports/QA_workspace_config_deprecation_review.md`) 지적 **필수 3건 + 권장 3건 전부 수정** 완료. 스위트 재실행: **229 passed / 1 allowed fail** (기준선 220 + 신규 회귀 테스트 9개, 허용 실패 동일 `test_map_presets_api`).

| # | 결함 | 수정 내용 | 위치 |
|---|---|---|---|
| D1(중) | 파일 처리 도중 config 리로드 시 3개 스냅샷 분열 → 오배송/무음 0행 SUCCESS | `IngestionHandler._snapshot_table_context()` 신설 — **파일당 1회** `(t_name, table_info)` 스냅샷을 `process_with_retry`·`process_archived_file_sync` 진입 시 잡아 `_resolve_rows`/`_try_std_parse`/`_send_to_upsert`/로그·콜백 전 구간에 인자로 전달. 핫리로드 의미론을 "**파일 경계에서 반영**"으로 정의(문서 연동 정정). 부수: 청크당 config 디스크 로드 소멸(파일당 1회 — QA가 지적한 선형 비용도 해소) | `directory_watcher.py` |
| D2(중) | `C:evil` 드라이브 상대경로가 문자 블랙리스트 통과 → base 탈출 | **결과 기반 검사**로 교체: `normpath(join(base, alias))`가 base의 **직속 자식**이고 **basename이 별칭 원형과 일치**해야 유효(동일 드라이브에서 `C:evil`→`evil` 변형 통과도 차단). `..foo` 오차단(false positive)도 해소. 공용 함수 `resolve_workspace_root(base, table, cfg)` | `directory_watcher.py` |
| D3(중) | 별칭=실존 테이블명 섀도잉 무감지 + retry 오배송 | `find_workspace_alias`에서 ① 다른 실존 테이블명과 동명 별칭 무효(자기-별칭은 허용) ② 동일 별칭 복수 선언 전부 무효 — 각 **ERROR 1회**. retry 경로 2곳(main.py `retry-failed`, run_watcher 폴러)은 `resolve_workspace_root` **역조회**로 별칭 워크스페이스를 정확히 찾음(무효 별칭은 정방향과 대칭으로 테이블명 폴백) | `directory_watcher.py` · `main.py` · `run_watcher.py` |
| D4(낮) | 비워크스페이스 JSON(sensor_config.json)에 허위 [DEPRECATED] | 등록 시 경고를 파일명 `config.json`에 게이트. 소비 필드(table_name/std_parse)를 실제로 읽는 파일은 기존 `_load_legacy_config` 필드 게이트 경고가 처리 시점에 발화(진성 경고 유지) | `directory_watcher.py` `_register_workspace` |
| D5(낮) | 중복 별칭 경고 청크당 재발화 | 충돌 로그를 `_alias_conflict_logged` set으로 **키별 1회** dedup (D3의 ERROR로 통합) | `directory_watcher.py` |
| D6(낮) | `"std_parse": "false"`(문자열) 무경고 활성 해석 | bool 타입 검증 — 비-bool은 무시(하위 원천 폴백) + `warn_invalid_std_parse_once` 1회 경고 | `directory_watcher.py` `_std_parse_enabled_for` |

**신규 회귀 테스트 9개** (`test_workspace_config_deprecation.py`, 총 21개):
- D1: `test_snapshot_consistency_under_mid_file_config_change` — 스냅샷 이후 별칭 탈취/항목 소실 config로 플립해도 시작 시점 테이블·스키마로 완결(재조회 회귀 시 오배송 또는 0행으로 실패하는 구조).
- D2: `test_drive_relative_alias_escape_blocked`(C: 접두 차단), `test_dotted_but_safe_alias_allowed`(`..foo` 오차단 해소).
- D3: `test_alias_colliding_with_table_name_ignored`(ERROR 1회), `test_duplicate_alias_all_ignored_with_error`, `test_self_alias_is_allowed`, `test_resolve_workspace_root_reverse_alias`(유효/충돌무효/부재 3분기).
- D4: `test_no_false_deprecation_for_non_config_json`.
- D6: `test_string_false_std_parse_warns_and_stays_enabled`(경고 1회 포함).

**문서 정정** (QA §5 지적 반영): `INGESTION_GUIDE.md` §1.5 — "핫리로드 즉시 반영" → "**파일 단위 핫리로드**(다음 파일부터 반영)" + 별칭 무효 조건·std_parse bool 요건 명기. 히스토리 문서 동기 갱신. 본 보고서 우선순위 규칙 문구도 동일 정정.

**시그니처 변경 전파 확인**: `_resolve_rows`/`_try_std_parse`/`_send_to_upsert`/`_log_ingestion_*`의 신규 파라미터는 전부 기본값 있는 추가 인자(레거시 직접 호출 하위호환 — 미전달 시 그 시점 1회 스냅샷). 호출부 전수 grep — 프로덕션 호출은 전부 스냅샷 전달로 갱신, 테스트의 무인자 직접 호출은 기본 브랜치로 동작. 경계 계약(REST/WS/셀 형태) 여전히 무접촉.

## 신규 교훈 제안 (server-pm.md 반영 검토용)

- **함정**: 핸들러 프로퍼티에 config 값을 `_cached_*`로 영구 캐시하면 핫리로드가 조용히 무효화되고(F4 사례), 반대로 **매 호출 재조회**로 바꾸면 한 작업 단위(파일) 도중 재조회 지점이 2곳 이상 갈라져 서로 다른 스냅샷을 보게 된다 — 검증은 A테이블 기준, 업서트는 B테이블/빈 스키마 기준인 무음 오배송·0행 SUCCESS 창이 열린다(QA D1 실증). 또한 로더에 mtime 시그니처 캐시를 넣으면 테스트의 `builtins.open` 몽키패치(가짜 table_config 주입: `test_contention_fixes`, `test_composite_business_key`)를 우회해 가짜/실 config가 교차 오염된다.
  **올바른 방법**: **작업 단위(파일) 경계에서 1회 스냅샷**을 잡아 전 구간에 인자로 전달한다 — 핫리로드(다음 작업부터 반영)와 작업 내 정합을 동시에 만족하고, 디스크 로드도 작업당 1회로 준다. 캐시는 정적 자산(레거시 파일 등)에만 한정.
- **함정**: "경로 구분자 차단" 류 문자 블랙리스트는 Windows 드라이브 상대경로(`C:foo`)를 놓친다 — `os.path.join`이 타 드라이브 접두에서 base를 통째로 폐기하고, 같은 드라이브에선 이름이 변형(`C:evil`→`evil`)된 채 통과한다. `..` 부분문자열 검사는 안전한 이름(`..foo`)을 오차단한다.
  **올바른 방법**: 문자 검사 대신 **결과 기반 검증** — `normpath(join(base, name))`이 base의 직속 자식이고 basename이 입력 원형과 일치하는지 확인.
